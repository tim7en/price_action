"""Separate BTCUSDT five-minute session scalper research.

This module translates the bar-data approximation described in the supplied
Fabio Valentini notes into causal, auditable rules.  It does *not* claim to
reconstruct bid/ask delta, a footprint, or true volume-at-price from OHLCV.

The study compares Tokyo, London, and New York equity-session clocks across:

* the first 30 minutes after the cash open;
* the following 30-minute opening-range-breakout window;
* the final 30 minutes before the cash close; and
* the first 30 minutes after the cash close.

Run with::

    python build_binance_session_scalper.py
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from .data import resolve_project_root
from .execution_costs import BinanceExecutionCosts, load_binance_execution_costs


DEFAULT_DATA = Path("cache/cache/binance_asia_orb/BTCUSDT_2022-01-01_2026-02-25_5m.csv.gz")
DEFAULT_EXECUTION = Path("config/binance_session_scalper_execution.json")
DEFAULT_OUTPUT = Path("outputs/binance_session_scalper")
LEVERAGED_NY_OUTPUT = Path("outputs/binance_ny_open_scalper_leveraged")
BAR_INTERVAL = pd.Timedelta(minutes=5)
PHASE_MINUTES = 30
HOLDOUT_START = pd.Timestamp("2025-01-01", tz="UTC")

SESSION_CALENDARS = {
    "Tokyo": "XTKS",
    "London": "XLON",
    "New_York": "XNYS",
}

PHASES = (
    "opening_first_30m",
    "opening_followthrough_30m",
    "closing_last_30m",
    "after_close_30m",
)


@dataclass(frozen=True)
class ScalperConfig:
    symbol: str = "BTCUSDT"
    markets: tuple[str, ...] = tuple(SESSION_CALENDARS)
    phases: tuple[str, ...] = PHASES
    profile_lookback_bars: int = 50
    profile_rows: int = 24
    profile_value_fraction: float = 0.70
    delta_smoothing_bars: int = 5
    atr_bars: int = 14
    average_volume_bars: int = 50
    absorption_volume_multiplier: float = 2.0
    absorption_range_atr: float = 0.30
    aggression_volume_multiplier: float = 1.25
    aggression_range_atr: float = 0.80
    accumulation_bars: int = 3
    accumulation_range_atr: float = 0.80
    absorption_memory_bars: int = 6
    location_tolerance_atr: float = 0.20
    stop_atr: float = 1.0
    risk_reward: float = 2.0
    max_holding_bars: int = 12
    risk_fraction: float = 0.0025
    max_notional_fraction: float = 1.0
    max_daily_losses: int = 3
    maximum_one_trade_per_phase: bool = True

    def __post_init__(self) -> None:
        if not self.markets or not set(self.markets).issubset(SESSION_CALENDARS):
            raise ValueError(f"markets must be selected from {sorted(SESSION_CALENDARS)}")
        if not self.phases or not set(self.phases).issubset(PHASES):
            raise ValueError(f"phases must be selected from {list(PHASES)}")
        if self.profile_lookback_bars < 10 or self.profile_rows < 4:
            raise ValueError("Volume-profile history and resolution are too small")
        if not 0.0 < self.profile_value_fraction < 1.0:
            raise ValueError("profile_value_fraction must be between zero and one")
        if self.stop_atr <= 0.0 or self.risk_reward <= 0.0:
            raise ValueError("Stop and reward/risk settings must be positive")
        if not 0.0 < self.risk_fraction <= 0.05:
            raise ValueError("risk_fraction must be positive and no greater than 5%")
        if self.max_notional_fraction <= 0.0:
            raise ValueError("max_notional_fraction must be positive")


def preset_config(name: str) -> ScalperConfig:
    if name == "broad_timing_research":
        return ScalperConfig()
    if name == "leveraged_new_york_open":
        return ScalperConfig(
            markets=("New_York",),
            phases=("opening_first_30m", "opening_followthrough_30m"),
            risk_fraction=0.01,
            max_notional_fraction=10.0,
            maximum_one_trade_per_phase=False,
        )
    raise ValueError(f"Unknown strategy preset: {name}")


def load_binance_klines(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"open_time", "open", "high", "low", "close", "volume", "close_time"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Kline cache is missing columns: {sorted(missing)}")
    for column in ["open", "high", "low", "close", "volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["timestamp"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp", keep="last").set_index("timestamp")
    if not frame.index.is_monotonic_increasing:
        raise ValueError("Kline timestamps are not monotonic")
    if (frame[["open", "high", "low", "close"]] <= 0.0).any().any() or (frame["volume"] < 0.0).any():
        raise ValueError("Kline prices and volume contain invalid values")
    frame["bar_id"] = np.arange(len(frame), dtype=int)
    return frame


def data_quality(frame: pd.DataFrame) -> dict[str, Any]:
    deltas = frame.index.to_series().diff().dropna()
    missing_bars = int(((deltas.loc[deltas > BAR_INTERVAL] / BAR_INTERVAL) - 1).sum())
    irregular = deltas.loc[deltas.ne(BAR_INTERVAL)]
    return {
        "rows": int(len(frame)),
        "first_bar_utc": frame.index.min().isoformat(),
        "last_bar_utc": frame.index.max().isoformat(),
        "duplicate_timestamps": int(frame.index.duplicated().sum()),
        "irregular_gap_events": int(len(irregular)),
        "missing_five_minute_bars": missing_bars,
        "largest_gap_minutes": float(deltas.max() / pd.Timedelta(minutes=1)),
    }


def build_session_schedule(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    start_date = pd.Timestamp(start).tz_convert("UTC").date()
    end_date = pd.Timestamp(end).tz_convert("UTC").date()
    rows: list[dict[str, Any]] = []
    for market, calendar_name in SESSION_CALENDARS.items():
        calendar = xcals.get_calendar(calendar_name)
        schedule = calendar.schedule.loc[str(start_date):str(end_date)]
        for session_label, session in schedule.iterrows():
            session_open = pd.Timestamp(session["open"]).tz_convert("UTC")
            session_close = pd.Timestamp(session["close"]).tz_convert("UTC")
            phase_bounds = {
                "opening_first_30m": (session_open, session_open + pd.Timedelta(minutes=30)),
                "opening_followthrough_30m": (
                    session_open + pd.Timedelta(minutes=30),
                    session_open + pd.Timedelta(minutes=60),
                ),
                "closing_last_30m": (session_close - pd.Timedelta(minutes=30), session_close),
                "after_close_30m": (session_close, session_close + pd.Timedelta(minutes=30)),
            }
            for phase, (phase_start, phase_end) in phase_bounds.items():
                rows.append({
                    "market": market,
                    "calendar": calendar_name,
                    "session_date": pd.Timestamp(session_label).strftime("%Y-%m-%d"),
                    "session_open": session_open,
                    "session_close": session_close,
                    "phase": phase,
                    "phase_start": phase_start,
                    "phase_end": phase_end,
                })
    return pd.DataFrame(rows).sort_values(["phase_start", "market", "phase"]).reset_index(drop=True)


def add_bar_indicators(frame: pd.DataFrame, config: ScalperConfig) -> pd.DataFrame:
    out = frame.copy()
    prior_close = out["close"].shift(1)
    true_range = pd.concat([
        out["high"] - out["low"],
        (out["high"] - prior_close).abs(),
        (out["low"] - prior_close).abs(),
    ], axis=1).max(axis=1)
    out["atr"] = true_range.rolling(config.atr_bars, min_periods=config.atr_bars).mean()
    out["average_volume"] = out["volume"].shift(1).rolling(
        config.average_volume_bars,
        min_periods=config.average_volume_bars,
    ).mean()
    bar_range = (out["high"] - out["low"]).replace(0.0, np.nan)
    out["bar_range"] = bar_range.fillna(0.0)
    out["close_location"] = ((out["close"] - out["low"]) / bar_range).fillna(0.5).clip(0.0, 1.0)
    out["delta_proxy"] = (
        ((2.0 * out["close"] - out["high"] - out["low"]) / bar_range).fillna(0.0)
        * out["volume"]
    )
    out["smoothed_delta_proxy"] = out["delta_proxy"].rolling(
        config.delta_smoothing_bars,
        min_periods=config.delta_smoothing_bars,
    ).sum()
    out["absorption"] = (
        out["volume"].gt(out["average_volume"] * config.absorption_volume_multiplier)
        & out["bar_range"].lt(out["atr"] * config.absorption_range_atr)
    )
    out["recent_absorption"] = out["absorption"].shift(1).rolling(
        config.absorption_memory_bars,
        min_periods=1,
    ).max().fillna(0.0).astype(bool)
    out["prior_accumulation_high"] = out["high"].shift(1).rolling(
        config.accumulation_bars,
        min_periods=config.accumulation_bars,
    ).max()
    out["prior_accumulation_low"] = out["low"].shift(1).rolling(
        config.accumulation_bars,
        min_periods=config.accumulation_bars,
    ).min()
    out["accumulation"] = (
        out["prior_accumulation_high"] - out["prior_accumulation_low"]
    ).lt(out["atr"] * config.accumulation_range_atr)
    volume_expansion = out["volume"].gt(out["average_volume"] * config.aggression_volume_multiplier)
    range_expansion = out["bar_range"].gt(out["atr"] * config.aggression_range_atr)
    out["aggressive_up"] = volume_expansion & range_expansion & out["close_location"].ge(0.75)
    out["aggressive_down"] = volume_expansion & range_expansion & out["close_location"].le(0.25)
    return out


def volume_profile_levels(
    history: pd.DataFrame,
    *,
    rows: int,
    value_fraction: float,
) -> tuple[float, float, float]:
    """Approximate POC/VAL/VAH by assigning each bar's volume to typical price."""
    if history.empty:
        return np.nan, np.nan, np.nan
    low = float(history["low"].min())
    high = float(history["high"].max())
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        return np.nan, np.nan, np.nan
    edges = np.linspace(low, high, rows + 1)
    typical = (history["high"] + history["low"] + history["close"]) / 3.0
    volume, _ = np.histogram(typical.to_numpy(), bins=edges, weights=history["volume"].to_numpy())
    centers = (edges[:-1] + edges[1:]) / 2.0
    if volume.sum() <= 0.0:
        return np.nan, np.nan, np.nan
    poc_index = int(np.argmax(volume))
    poc = float(centers[poc_index])
    selected = [poc_index]
    left = poc_index - 1
    right = poc_index + 1
    cumulative = float(volume[poc_index])
    threshold = float(volume.sum() * value_fraction)
    # Standard contiguous value-area expansion: start at POC and repeatedly
    # add the higher-volume adjacent price row until the target share is held.
    while cumulative < threshold and (left >= 0 or right < len(volume)):
        left_volume = float(volume[left]) if left >= 0 else -1.0
        right_volume = float(volume[right]) if right < len(volume) else -1.0
        if right_volume > left_volume:
            selected.append(right)
            cumulative += right_volume
            right += 1
        else:
            selected.append(left)
            cumulative += left_volume
            left -= 1
    return poc, float(centers[min(selected)]), float(centers[max(selected)])


def _complete_grid(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> bool:
    expected = pd.date_range(start, end - BAR_INTERVAL, freq=BAR_INTERVAL, tz="UTC")
    actual = frame.loc[(frame.index >= start) & (frame.index < end)].index
    return len(actual) == len(expected) and actual.equals(expected)


def build_phase_candidates(
    frame: pd.DataFrame,
    schedule: pd.DataFrame,
    config: ScalperConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    indicated = add_bar_indicators(frame, config)
    profile_cache: dict[int, tuple[float, float, float]] = {}
    candidates: list[dict[str, Any]] = []
    moves: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    grouped = schedule.groupby(["market", "session_date"], sort=False)
    for (market, session_date), phases in grouped:
        session_open = pd.Timestamp(phases["session_open"].iloc[0])
        session_close = pd.Timestamp(phases["session_close"].iloc[0])
        session_end = session_close + pd.Timedelta(minutes=30)
        session_bars = indicated.loc[(indicated.index >= session_open) & (indicated.index < session_end)].copy()
        session_complete = _complete_grid(indicated, session_open, session_end)
        if not session_bars.empty:
            typical = (session_bars["high"] + session_bars["low"] + session_bars["close"]) / 3.0
            cumulative_volume = session_bars["volume"].cumsum()
            session_bars["session_vwap"] = (
                (typical * session_bars["volume"]).cumsum() / cumulative_volume.replace(0.0, np.nan)
            )
        opening_end = session_open + pd.Timedelta(minutes=30)
        opening_bars = indicated.loc[(indicated.index >= session_open) & (indicated.index < opening_end)]
        opening_complete = _complete_grid(indicated, session_open, opening_end)
        opening_high = float(opening_bars["high"].max()) if opening_complete else np.nan
        opening_low = float(opening_bars["low"].min()) if opening_complete else np.nan
        for phase in phases.itertuples(index=False):
            phase_start = pd.Timestamp(phase.phase_start)
            phase_end = pd.Timestamp(phase.phase_end)
            phase_bars = session_bars.loc[
                (session_bars.index >= phase_start) & (session_bars.index < phase_end)
            ].copy()
            phase_complete = _complete_grid(indicated, phase_start, phase_end)
            usable = bool(phase_complete and opening_complete and session_complete and len(phase_bars) == 6)
            quality_rows.append({
                "market": market,
                "session_date": session_date,
                "phase": phase.phase,
                "phase_complete": phase_complete,
                "opening_range_complete": opening_complete,
                "session_prefix_complete": session_complete,
                "usable": usable,
            })
            if not usable:
                continue
            phase_return = float(phase_bars["close"].iloc[-1] / phase_bars["open"].iloc[0] - 1.0)
            moves.append({
                "market": market,
                "session_date": session_date,
                "phase": phase.phase,
                "phase_start": phase_start,
                "phase_end": phase_end,
                "return": phase_return,
                "absolute_return": abs(phase_return),
                "high_low_range": float(phase_bars["high"].max() / phase_bars["low"].min() - 1.0),
                "volume": float(phase_bars["volume"].sum()),
            })
            for timestamp, bar in phase_bars.iterrows():
                bar_id = int(bar["bar_id"])
                if bar_id not in profile_cache:
                    profile_start = max(0, bar_id - config.profile_lookback_bars)
                    history = indicated.iloc[profile_start:bar_id]
                    profile_cache[bar_id] = volume_profile_levels(
                        history,
                        rows=config.profile_rows,
                        value_fraction=config.profile_value_fraction,
                    ) if len(history) == config.profile_lookback_bars else (np.nan, np.nan, np.nan)
                poc, val, vah = profile_cache[bar_id]
                payload = bar.to_dict()
                payload.update({
                    "timestamp": timestamp,
                    "market": market,
                    "session_date": session_date,
                    "session_open": session_open,
                    "session_close": session_close,
                    "phase": phase.phase,
                    "phase_start": phase_start,
                    "phase_end": phase_end,
                    "session_vwap": float(bar["session_vwap"]),
                    "opening_range_high": opening_high,
                    "opening_range_low": opening_low,
                    "profile_poc": poc,
                    "profile_val": val,
                    "profile_vah": vah,
                })
                candidates.append(payload)
    candidate_frame = pd.DataFrame(candidates)
    if not candidate_frame.empty:
        candidate_frame = classify_setups(candidate_frame, config)
    return candidate_frame, pd.DataFrame(moves), pd.DataFrame(quality_rows)


def classify_setups(candidates: pd.DataFrame, config: ScalperConfig) -> pd.DataFrame:
    out = candidates.copy()
    tolerance = out["atr"] * config.location_tolerance_atr
    location_touch = (
        out["profile_poc"].between(out["prior_accumulation_low"] - tolerance, out["prior_accumulation_high"] + tolerance)
        | out["profile_val"].between(out["prior_accumulation_low"] - tolerance, out["prior_accumulation_high"] + tolerance)
        | out["profile_vah"].between(out["prior_accumulation_low"] - tolerance, out["prior_accumulation_high"] + tolerance)
    )
    triple_long = (
        out["recent_absorption"] & out["accumulation"] & location_touch
        & out["aggressive_up"]
        & out["close"].gt(out["prior_accumulation_high"])
        & out["smoothed_delta_proxy"].gt(0.0)
        & out["close"].gt(out["session_vwap"])
    )
    triple_short = (
        out["recent_absorption"] & out["accumulation"] & location_touch
        & out["aggressive_down"]
        & out["close"].lt(out["prior_accumulation_low"])
        & out["smoothed_delta_proxy"].lt(0.0)
        & out["close"].lt(out["session_vwap"])
    )
    orb_phase = out["phase"].eq("opening_followthrough_30m")
    orb_long = (
        orb_phase & out["aggressive_up"]
        & out["close"].gt(out["opening_range_high"])
        & out["smoothed_delta_proxy"].gt(0.0)
        & out["close"].gt(out["session_vwap"])
    )
    orb_short = (
        orb_phase & out["aggressive_down"]
        & out["close"].lt(out["opening_range_low"])
        & out["smoothed_delta_proxy"].lt(0.0)
        & out["close"].lt(out["session_vwap"])
    )
    bounce_long = (
        out["low"].le(out["profile_val"] + tolerance)
        & out["close"].gt(out["profile_val"])
        & out["close_location"].ge(0.60)
        & out["smoothed_delta_proxy"].gt(0.0)
        & out["volume"].gt(out["average_volume"])
    )
    bounce_short = (
        out["high"].ge(out["profile_vah"] - tolerance)
        & out["close"].lt(out["profile_vah"])
        & out["close_location"].le(0.40)
        & out["smoothed_delta_proxy"].lt(0.0)
        & out["volume"].gt(out["average_volume"])
    )
    out["setup"] = ""
    out["signal_side"] = 0
    for setup, long_mask, short_mask in [
        ("value_area_bounce", bounce_long, bounce_short),
        ("opening_range_breakout", orb_long, orb_short),
        ("triple_a", triple_long, triple_short),
    ]:
        out.loc[long_mask, ["setup", "signal_side"]] = [setup, 1]
        out.loc[short_mask, ["setup", "signal_side"]] = [setup, -1]
    return out


def _simulate_trade(
    signal: pd.Series,
    bars: pd.DataFrame,
    config: ScalperConfig,
    execution: BinanceExecutionCosts,
) -> dict[str, Any] | None:
    signal_id = int(signal["bar_id"])
    entry_id = signal_id + 1
    if entry_id >= len(bars):
        return None
    entry_bar = bars.iloc[entry_id]
    entry_time = bars.index[entry_id]
    phase_end = pd.Timestamp(signal["phase_end"])
    if entry_time != pd.Timestamp(signal["timestamp"]) + BAR_INTERVAL or entry_time >= phase_end:
        return None
    entry_price = float(entry_bar["open"])
    atr = float(signal["atr"])
    if not np.isfinite(atr) or atr <= 0.0:
        return None
    stop_distance = atr * config.stop_atr
    stop_fraction = stop_distance / entry_price
    notional = min(config.max_notional_fraction, config.risk_fraction / stop_fraction)
    side = int(signal["signal_side"])
    stop_price = entry_price - side * stop_distance
    target_price = entry_price + side * stop_distance * config.risk_reward
    final_id = min(entry_id + config.max_holding_bars - 1, len(bars) - 1)
    exit_price = float(bars.iloc[final_id]["close"])
    exit_time = bars.index[final_id]
    exit_reason = "max_holding"
    for bar_id in range(entry_id, final_id + 1):
        bar = bars.iloc[bar_id]
        timestamp = bars.index[bar_id]
        if timestamp >= phase_end:
            break
        stop_hit = float(bar["low"]) <= stop_price if side > 0 else float(bar["high"]) >= stop_price
        target_hit = float(bar["high"]) >= target_price if side > 0 else float(bar["low"]) <= target_price
        if stop_hit:
            exit_price = stop_price
            exit_time = timestamp
            exit_reason = "stop"
            break
        if target_hit:
            exit_price = target_price
            exit_time = timestamp
            exit_reason = "target"
            break
        exit_price = float(bar["close"])
        exit_time = timestamp
        exit_reason = "phase_end" if timestamp + BAR_INTERVAL >= phase_end else "max_holding"
        if timestamp + BAR_INTERVAL >= phase_end:
            break
    gross_return = side * notional * (exit_price / entry_price - 1.0)
    turnover = 2.0 * notional
    cost = turnover * execution.all_in_trade_cost_rate
    net_return = gross_return - cost
    risk_fraction_deployed = notional * stop_fraction
    return {
        "signal_time": pd.Timestamp(signal["timestamp"]),
        "entry_time": entry_time,
        "exit_time": exit_time,
        "market": signal["market"],
        "session_date": signal["session_date"],
        "phase": signal["phase"],
        "setup": signal["setup"],
        "side": "long" if side > 0 else "short",
        "entry_price": entry_price,
        "stop_price": stop_price,
        "target_price": target_price,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "holding_bars": int((exit_time - entry_time) / BAR_INTERVAL) + 1,
        "notional_fraction": notional,
        "risk_fraction_deployed": risk_fraction_deployed,
        "gross_return": gross_return,
        "one_way_turnover": turnover,
        "execution_cost": cost,
        "net_return": net_return,
        "gross_r_multiple": gross_return / risk_fraction_deployed if risk_fraction_deployed > 0.0 else np.nan,
        "net_r_multiple": net_return / risk_fraction_deployed if risk_fraction_deployed > 0.0 else np.nan,
    }


def run_backtest(
    candidates: pd.DataFrame,
    bars: pd.DataFrame,
    config: ScalperConfig,
    execution: BinanceExecutionCosts,
) -> tuple[pd.DataFrame, dict[str, int]]:
    signals = candidates.loc[candidates["signal_side"].ne(0)].sort_values(
        ["timestamp", "market", "phase", "setup"]
    )
    trades: list[dict[str, Any]] = []
    losses_by_utc_date: dict[str, int] = {}
    used_phases: set[tuple[str, str, str]] = set()
    last_exit = pd.Timestamp.min.tz_localize("UTC")
    blocked = {"overlap": 0, "daily_loss_stop": 0, "phase_limit": 0, "unexecutable": 0}
    for _, signal in signals.iterrows():
        signal_time = pd.Timestamp(signal["timestamp"])
        if signal_time <= last_exit:
            blocked["overlap"] += 1
            continue
        utc_date = signal_time.strftime("%Y-%m-%d")
        if losses_by_utc_date.get(utc_date, 0) >= config.max_daily_losses:
            blocked["daily_loss_stop"] += 1
            continue
        phase_key = (str(signal["market"]), str(signal["session_date"]), str(signal["phase"]))
        if config.maximum_one_trade_per_phase and phase_key in used_phases:
            blocked["phase_limit"] += 1
            continue
        trade = _simulate_trade(signal, bars, config, execution)
        if trade is None:
            blocked["unexecutable"] += 1
            continue
        trades.append(trade)
        used_phases.add(phase_key)
        last_exit = pd.Timestamp(trade["exit_time"])
        if float(trade["net_return"]) < 0.0:
            losses_by_utc_date[utc_date] = losses_by_utc_date.get(utc_date, 0) + 1
    return pd.DataFrame(trades), blocked


def _trade_metrics(frame: pd.DataFrame, label: str) -> dict[str, Any]:
    if frame.empty:
        return {"scope": label, "trades": 0}
    net = frame["net_return"].astype(float)
    gross = frame["gross_return"].astype(float)
    equity = (1.0 + net).cumprod()
    years = max((pd.Timestamp(frame["exit_time"].max()) - pd.Timestamp(frame["entry_time"].min())).days / 365.25, 1 / 365.25)
    wins = net.loc[net > 0.0]
    losses = net.loc[net < 0.0]
    gross_wins = gross.loc[gross > 0.0]
    gross_losses = gross.loc[gross < 0.0]
    turnover = float(frame["one_way_turnover"].sum())
    return {
        "scope": label,
        "trades": int(len(frame)),
        "win_rate": float(net.gt(0.0).mean()),
        "target_rate": float(frame["exit_reason"].eq("target").mean()),
        "stop_rate": float(frame["exit_reason"].eq("stop").mean()),
        "average_gross_return_bps": float(gross.mean() * 10_000.0),
        "average_net_return_bps": float(net.mean() * 10_000.0),
        "average_net_r_multiple": float(frame["net_r_multiple"].mean()),
        "gross_profit_factor": float(gross_wins.sum() / abs(gross_losses.sum())) if gross_losses.sum() < 0.0 else np.nan,
        "profit_factor": float(wins.sum() / abs(losses.sum())) if losses.sum() < 0.0 else np.nan,
        "break_even_one_way_cost_bps": float(gross.sum() / turnover * 10_000.0) if turnover > 0.0 else np.nan,
        "cumulative_net_return": float(equity.iloc[-1] - 1.0),
        "annualized_net_return": float(equity.iloc[-1] ** (1.0 / years) - 1.0),
        "max_drawdown": float((equity / equity.cummax() - 1.0).min()),
        "annualized_one_way_turnover": float(frame["one_way_turnover"].sum() / years),
        "total_execution_cost": float(frame["execution_cost"].sum()),
        "average_holding_bars": float(frame["holding_bars"].mean()),
    }


def trade_summary(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame([{"scope": "all", "trades": 0}])
    frame = trades.sort_values("entry_time").copy()
    frame["entry_time"] = pd.to_datetime(frame["entry_time"], utc=True)
    rows = [
        _trade_metrics(frame, "all"),
        _trade_metrics(frame.loc[frame["entry_time"] < HOLDOUT_START], "development_2022_2024"),
        _trade_metrics(frame.loc[frame["entry_time"] >= HOLDOUT_START], "holdout_2025_plus"),
    ]
    for columns, prefix in [
        (["market"], "market"),
        (["phase"], "phase"),
        (["setup"], "setup"),
        (["market", "phase"], "market_phase"),
    ]:
        group_key: str | list[str] = columns[0] if len(columns) == 1 else columns
        for keys, group in frame.groupby(group_key, sort=True):
            values = keys if isinstance(keys, tuple) else (keys,)
            label = prefix + "::" + "::".join(str(value) for value in values)
            rows.append(_trade_metrics(group, label))
    return pd.DataFrame(rows)


def phase_move_summary(moves: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    data = moves.copy()
    data["phase_start"] = pd.to_datetime(data["phase_start"], utc=True)
    scopes = {
        "all": data,
        "development_2022_2024": data.loc[data["phase_start"] < HOLDOUT_START],
        "holdout_2025_plus": data.loc[data["phase_start"] >= HOLDOUT_START],
    }
    for scope, scoped in scopes.items():
        for keys, group in scoped.groupby(["market", "phase"], sort=True):
            values = group["return"].astype(float)
            standard_error = values.std(ddof=1) / math.sqrt(len(values)) if len(values) > 1 else np.nan
            rows.append({
                "scope": scope,
                "market": keys[0],
                "phase": keys[1],
                "observations": int(len(group)),
                "mean_return_bps": float(values.mean() * 10_000.0),
                "median_return_bps": float(values.median() * 10_000.0),
                "positive_rate": float(values.gt(0.0).mean()),
                "mean_absolute_return_bps": float(group["absolute_return"].mean() * 10_000.0),
                "mean_high_low_range_bps": float(group["high_low_range"].mean() * 10_000.0),
                "mean_return_tstat": float(values.mean() / standard_error) if standard_error > 0.0 else np.nan,
                "median_volume": float(group["volume"].median()),
            })
    return pd.DataFrame(rows)


def cost_sensitivity(trades: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    data = trades.copy()
    if not data.empty:
        data["entry_time"] = pd.to_datetime(data["entry_time"], utc=True)
    scopes = {
        "all": data,
        "development_2022_2024": data.loc[data["entry_time"] < HOLDOUT_START] if not data.empty else data,
        "holdout_2025_plus": data.loc[data["entry_time"] >= HOLDOUT_START] if not data.empty else data,
    }
    for scope, scoped in scopes.items():
        setup_groups = [("all", scoped)]
        if not scoped.empty:
            setup_groups.extend(
                (str(setup), group) for setup, group in scoped.groupby("setup", sort=True)
            )
        for setup, group in setup_groups:
            for cost_bps in [0.0, 1.0, 2.0, 2.5, 3.0, 5.0, 10.0, 15.0, 20.0]:
                if group.empty:
                    rows.append({
                        "scope": scope,
                        "setup": setup,
                        "one_way_cost_bps": cost_bps,
                        "trades": 0,
                    })
                    continue
                net = group["gross_return"] - group["one_way_turnover"] * cost_bps / 10_000.0
                equity = (1.0 + net).cumprod()
                rows.append({
                    "scope": scope,
                    "setup": setup,
                    "one_way_cost_bps": cost_bps,
                    "trades": int(len(group)),
                    "win_rate": float(net.gt(0.0).mean()),
                    "average_net_return_bps": float(net.mean() * 10_000.0),
                    "cumulative_net_return": float(equity.iloc[-1] - 1.0),
                    "max_drawdown": float((equity / equity.cummax() - 1.0).min()),
                })
    return pd.DataFrame(rows)


def signal_funnel(candidates: pd.DataFrame) -> pd.DataFrame:
    checks = {
        "phase_bars": pd.Series(True, index=candidates.index),
        "absorption_bar": candidates["absorption"],
        "recent_absorption": candidates["recent_absorption"],
        "accumulation": candidates["accumulation"],
        "recent_absorption_and_accumulation": candidates["recent_absorption"] & candidates["accumulation"],
        "aggressive_expansion": candidates["aggressive_up"] | candidates["aggressive_down"],
        "triple_a_signal": candidates["setup"].eq("triple_a"),
        "opening_range_breakout_signal": candidates["setup"].eq("opening_range_breakout"),
        "value_area_bounce_signal": candidates["setup"].eq("value_area_bounce"),
    }
    return pd.DataFrame([
        {"stage": stage, "observations": int(mask.fillna(False).sum()), "share_of_phase_bars": float(mask.fillna(False).mean())}
        for stage, mask in checks.items()
    ])


def _markdown_table(frame: pd.DataFrame, rows: int = 30) -> str:
    if frame.empty:
        return "_No rows._"
    view = frame.head(rows).copy()
    for column in view.select_dtypes(include=["float"]).columns:
        view[column] = view[column].map(lambda value: f"{value:.4f}" if pd.notna(value) else "")
    headers = [str(column) for column in view.columns]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in view.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def build_report(
    summary: pd.DataFrame,
    phase_summary: pd.DataFrame,
    sensitivity: pd.DataFrame,
    funnel: pd.DataFrame,
    governance: dict[str, Any],
) -> str:
    overall_sensitivity = sensitivity.loc[sensitivity["setup"].eq("all")]
    holdout_setup_sensitivity = sensitivity.loc[
        sensitivity["scope"].eq("holdout_2025_plus")
        & sensitivity["setup"].ne("all")
    ]
    return f"""# BTCUSDT 5-Minute Major-Session Scalper

Generated {governance['generated_at_utc']}. This is a standalone strategy; no macro or hierarchical model inputs are used.

## Decision summary

{_markdown_table(summary)}

## Unconditional 30-minute BTC moves

{_markdown_table(phase_summary)}

## Cost sensitivity

{_markdown_table(overall_sensitivity)}

## Holdout cost sensitivity by setup

{_markdown_table(holdout_setup_sensitivity)}

## Signal funnel

{_markdown_table(funnel)}

## Predeclared rules

- Exchange calendars: XTKS, XLON, and XNYS, including holidays, DST, early closes, and Tokyo's November 2024 close extension.
- OHLCV approximation: 50-bar, 24-bin typical-price volume profile; five-bar close-location delta proxy; 2x-volume/0.3-ATR absorption; accumulation then aggressive expansion; session VWAP alignment.
- The first 30 minutes defines the opening range. ORB entries are allowed only in the following 30 minutes. Triple-A and value-area reactions are evaluated in all phase buckets.
- Signals are confirmed at a bar close and entered at the next five-minute open. Both stop and target touching in one bar is resolved as a stop.
- Risk is {governance['config']['risk_fraction'] * 100.0:.2f}% of current equity per trade, subject to a {governance['config']['max_notional_fraction']:.1f}x gross-notional cap, 2R target, one position globally, and three net losses per UTC day. {'Only one trade is permitted per market-phase.' if governance['config']['maximum_one_trade_per_phase'] else 'Repeated non-overlapping attempts are permitted within the selected session until the loss stop is reached.'}
- Profit-based intraday risk scaling is disabled because the source describes the principle but does not supply an auditable scaling equation.
- Development period: 2022-2024. Untuned holdout: 2025 onward.

## Important limitations

- Aggregated five-minute OHLCV cannot reveal bid/ask aggressor side, resting liquidity, stacked imbalance, or true footprint/CVD. “Delta,” absorption, and volume profile are proxies.
- The cache has no venue/product metadata. It is treated as BTCUSDT trade-price data, while short trades are costed as Binance USD-M perpetual research.
- Historical funding, mark price, queue position, latency, partial fills, and liquidation are unavailable. Funding is set to zero because trades are capped at 30 minutes, but a funding timestamp can still matter.
- The cached history has one 80-minute outage. Any affected full session-prefix or phase is excluded rather than filled.
- Multiple timing buckets and setup families are reported separately; do not select the best row and call it validated without a fresh holdout.
"""


def build_session_scalper(
    project_root: str | Path | None = None,
    *,
    data_path: str | Path = DEFAULT_DATA,
    execution_path: str | Path = DEFAULT_EXECUTION,
    output_dir: str | Path = DEFAULT_OUTPUT,
    config: ScalperConfig | None = None,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    data_file = Path(data_path)
    if not data_file.is_absolute():
        data_file = root / data_file
    execution_file = Path(execution_path)
    if not execution_file.is_absolute():
        execution_file = root / execution_file
    out = Path(output_dir)
    if not out.is_absolute():
        out = root / out
    out.mkdir(parents=True, exist_ok=True)
    strategy = config or ScalperConfig()
    execution = load_binance_execution_costs(execution_file)
    if execution.product != "usd_m_perp":
        raise ValueError("This long/short BTCUSDT study requires a USD-M perpetual execution profile")
    bars = load_binance_klines(data_file)
    schedule = build_session_schedule(bars.index.min(), bars.index.max())
    schedule = schedule.loc[
        schedule["market"].isin(strategy.markets)
        & schedule["phase"].isin(strategy.phases)
    ].reset_index(drop=True)
    candidates, moves, phase_quality = build_phase_candidates(bars, schedule, strategy)
    trades, blocked = run_backtest(candidates, bars, strategy, execution)
    summary = trade_summary(trades)
    phase_summary = phase_move_summary(moves)
    sensitivity = cost_sensitivity(trades)
    funnel = signal_funnel(candidates)
    signal_view = candidates.loc[candidates["signal_side"].ne(0)].copy()
    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "strategy": "standalone_fabio_inspired_ohlcv_proxy",
        "macro_or_hierarchy_inputs": False,
        "data_file": str(data_file),
        "data_quality": data_quality(bars),
        "config": asdict(strategy),
        "execution": execution.to_dict(),
        "holdout_start": HOLDOUT_START.isoformat(),
        "calendar_library": "exchange_calendars",
        "session_calendars": {
            market: SESSION_CALENDARS[market] for market in strategy.markets
        },
        "phases": list(strategy.phases),
        "profit_scaling": "disabled: no exact public sizing formula supplied",
        "usable_phases": int(phase_quality["usable"].sum()),
        "excluded_phases": int((~phase_quality["usable"]).sum()),
        "raw_signals": int(len(signal_view)),
        "signal_counts": signal_view["setup"].value_counts().to_dict(),
        "executed_trades": int(len(trades)),
        "blocked_signals": blocked,
        "research_only_reasons": [
            "five-minute OHLCV is not true order flow",
            "cache venue/product metadata is absent",
            "historical perpetual mark price and funding are absent",
        ],
    }
    schedule.to_csv(out / "session_schedule.csv", index=False)
    phase_quality.to_csv(out / "phase_data_quality.csv", index=False)
    moves.to_csv(out / "phase_moves.csv", index=False)
    signal_columns = [
        "timestamp", "market", "session_date", "phase", "setup", "signal_side",
        "open", "high", "low", "close", "volume", "atr", "session_vwap",
        "opening_range_high", "opening_range_low", "profile_poc", "profile_val", "profile_vah",
        "smoothed_delta_proxy", "absorption", "recent_absorption", "aggressive_up", "aggressive_down",
    ]
    signal_view[[column for column in signal_columns if column in signal_view]].to_csv(
        out / "signals.csv", index=False
    )
    trades.to_csv(out / "trades.csv", index=False)
    summary.to_csv(out / "summary.csv", index=False)
    phase_summary.to_csv(out / "phase_summary.csv", index=False)
    sensitivity.to_csv(out / "cost_sensitivity.csv", index=False)
    funnel.to_csv(out / "signal_funnel.csv", index=False)
    (out / "governance.json").write_text(json.dumps(governance, indent=2), encoding="utf-8")
    (out / "report.md").write_text(
        build_report(summary, phase_summary, sensitivity, funnel, governance), encoding="utf-8"
    )
    return {
        "output_dir": out,
        "trades": trades,
        "summary": summary,
        "phase_summary": phase_summary,
        "cost_sensitivity": sensitivity,
        "signal_funnel": funnel,
        "governance": governance,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--data-path", default=str(DEFAULT_DATA))
    parser.add_argument("--execution-path", default=str(DEFAULT_EXECUTION))
    parser.add_argument(
        "--preset",
        choices=["broad_timing_research", "leveraged_new_york_open"],
        default="broad_timing_research",
    )
    parser.add_argument("--output-dir", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir or (
        str(LEVERAGED_NY_OUTPUT)
        if args.preset == "leveraged_new_york_open"
        else str(DEFAULT_OUTPUT)
    )
    result = build_session_scalper(
        args.project_root,
        data_path=args.data_path,
        execution_path=args.execution_path,
        output_dir=output_dir,
        config=preset_config(args.preset),
    )
    print(f"Report: {result['output_dir'] / 'report.md'}")
    print(result["summary"].head(12).to_string(index=False))


if __name__ == "__main__":
    main()
