"""Standalone Nasdaq-100 New York-open auction backtest.

The supplied ``cache/Nasdaq.csv`` contains one-minute OHLCV, but no venue,
contract, bid/ask, or roll metadata.  Prices are not aligned to CME NQ's
quarter-point tick, so the feed is deliberately treated as an unverified
Nasdaq-100 cash/CFD-like series.  This module resamples it to causal five-minute
bars and tests bar-data approximations of the Direction/Location/Aggression
framework without claiming genuine order flow.
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


DEFAULT_DATA = Path("cache/Nasdaq.csv")
DEFAULT_EXECUTION = Path("config/nasdaq_session_execution.json")
DEFAULT_OUTPUT = Path("outputs/nasdaq_session_backtest")
BAR_INTERVAL = pd.Timedelta(minutes=5)
HOLDOUT_START = pd.Timestamp("2025-01-01", tz="UTC")
CALENDAR_NAME = "XNYS"


@dataclass(frozen=True)
class NasdaqExecutionCosts:
    instrument_assumption: str = "unverified_nasdaq_100_cash_or_cfd"
    commission_bps: float = 0.15
    slippage_bps: float = 0.35
    venue_and_contract_verified: bool = False
    historical_spread_supplied: bool = False

    def __post_init__(self) -> None:
        if self.commission_bps < 0.0 or self.slippage_bps < 0.0:
            raise ValueError("Execution-cost assumptions cannot be negative")

    @property
    def one_way_cost_bps(self) -> float:
        return float(self.commission_bps + self.slippage_bps)

    @property
    def one_way_cost_rate(self) -> float:
        return self.one_way_cost_bps / 10_000.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update({
            "one_way_cost_bps": self.one_way_cost_bps,
            "research_only": not (
                self.venue_and_contract_verified and self.historical_spread_supplied
            ),
            "cost_note": "Commission plus slippage is charged to entry and exit notional.",
        })
        return payload


@dataclass(frozen=True)
class NasdaqStrategyConfig:
    profile_rows: int = 24
    profile_value_fraction: float = 0.70
    atr_bars: int = 14
    average_volume_bars: int = 50
    delta_smoothing_bars: int = 5
    aggression_volume_multiplier: float = 1.25
    aggression_range_atr: float = 0.80
    absorption_volume_multiplier: float = 2.0
    absorption_range_atr: float = 0.30
    location_tolerance_atr: float = 0.20
    stop_atr: float = 1.0
    reward_to_risk: float = 2.0
    max_holding_bars: int = 6
    risk_fraction: float = 0.01
    max_notional_fraction: float = 10.0
    max_daily_losses: int = 3

    def __post_init__(self) -> None:
        if self.profile_rows < 4 or not 0.0 < self.profile_value_fraction < 1.0:
            raise ValueError("Invalid volume-profile configuration")
        if self.atr_bars < 2 or self.average_volume_bars < 2 or self.delta_smoothing_bars < 1:
            raise ValueError("Indicator windows are too short")
        if self.stop_atr <= 0.0 or self.reward_to_risk < 2.0:
            raise ValueError("Stop must be positive and reward/risk must be at least 2")
        if not 0.0 < self.risk_fraction <= 0.05:
            raise ValueError("Risk fraction must be positive and no greater than 5%")
        if self.max_notional_fraction <= 0.0 or self.max_daily_losses < 1:
            raise ValueError("Leverage and daily-loss limits must be positive")


def load_execution_costs(path: str | Path) -> NasdaqExecutionCosts:
    return NasdaqExecutionCosts(**json.loads(Path(path).read_text(encoding="utf-8")))


def load_nasdaq_bars(path: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    raw = pd.read_csv(path)
    required = {"time", "open", "high", "low", "close", "volume"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"Nasdaq CSV is missing columns: {sorted(missing)}")
    raw["time"] = pd.to_datetime(raw["time"], utc=True, errors="coerce")
    for column in ["open", "high", "low", "close", "volume"]:
        raw[column] = pd.to_numeric(raw[column], errors="coerce")
    if raw[list(required)].isna().any().any():
        raise ValueError("Nasdaq CSV contains null or unparseable required values")
    raw = raw.sort_values("time")
    duplicate_count = int(raw["time"].duplicated().sum())
    if duplicate_count:
        raise ValueError(f"Nasdaq CSV contains {duplicate_count} duplicate timestamps")
    invalid_ohlc = (
        raw["high"].lt(raw[["open", "close"]].max(axis=1))
        | raw["low"].gt(raw[["open", "close"]].min(axis=1))
        | raw["low"].gt(raw["high"])
    )
    if invalid_ohlc.any() or raw[["open", "high", "low", "close"]].le(0.0).any().any():
        raise ValueError("Nasdaq CSV contains invalid OHLC prices")
    if raw["volume"].lt(0.0).any():
        raise ValueError("Nasdaq CSV contains negative volume")
    raw = raw.set_index("time")
    minute_deltas = raw.index.to_series().diff().dropna()
    minute_counts = raw["close"].resample("5min", origin="epoch").count()
    bars = raw.resample("5min", origin="epoch").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    incomplete_groups = minute_counts.between(1, 4)
    bars = bars.loc[minute_counts.eq(5)].dropna()
    bars["bar_id"] = np.arange(len(bars), dtype=int)
    off_tick = ((raw["close"] * 4.0) - (raw["close"] * 4.0).round()).abs().gt(1e-8)
    audit = {
        "input_rows": int(len(raw)),
        "five_minute_rows": int(len(bars)),
        "first_input_bar_utc": raw.index.min().isoformat(),
        "last_input_bar_utc": raw.index.max().isoformat(),
        "duplicate_timestamps": duplicate_count,
        "zero_volume_rows": int(raw["volume"].eq(0.0).sum()),
        "non_one_minute_gap_events": int(minute_deltas.ne(pd.Timedelta(minutes=1)).sum()),
        "largest_gap_minutes": float(minute_deltas.max() / pd.Timedelta(minutes=1)),
        "incomplete_five_minute_groups_dropped": int(incomplete_groups.sum()),
        "close_not_on_nq_quarter_tick_rows": int(off_tick.sum()),
        "close_not_on_nq_quarter_tick_share": float(off_tick.mean()),
        "instrument_identity": "unverified; price grid is inconsistent with CME NQ",
        "volume_identity": "unverified; may be tick volume rather than exchange contract volume",
    }
    return bars, audit


def build_ny_schedule(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    calendar = xcals.get_calendar(CALENDAR_NAME)
    schedule = calendar.schedule.loc[str(pd.Timestamp(start).date()):str(pd.Timestamp(end).date())]
    rows: list[dict[str, Any]] = []
    for label, session in schedule.iterrows():
        session_open = pd.Timestamp(session["open"]).tz_convert("UTC")
        session_close = pd.Timestamp(session["close"]).tz_convert("UTC")
        rows.append({
            "session_date": pd.Timestamp(label).strftime("%Y-%m-%d"),
            "session_open": session_open,
            "session_close": session_close,
            "opening_start": session_open,
            "opening_end": session_open + pd.Timedelta(minutes=30),
            "execution_start": session_open + pd.Timedelta(minutes=30),
            "execution_end": session_open + pd.Timedelta(minutes=60),
            "closing_start": session_close - pd.Timedelta(minutes=30),
            "after_close_end": session_close + pd.Timedelta(minutes=30),
        })
    return pd.DataFrame(rows)


def _complete_grid(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> bool:
    expected = pd.date_range(start, end - BAR_INTERVAL, freq=BAR_INTERVAL, tz="UTC")
    actual = frame.loc[(frame.index >= start) & (frame.index < end)].index
    return bool(len(actual) == len(expected) and actual.equals(expected))


def add_indicators(frame: pd.DataFrame, config: NasdaqStrategyConfig) -> pd.DataFrame:
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
    out["absorption_proxy"] = (
        out["volume"].gt(out["average_volume"] * config.absorption_volume_multiplier)
        & out["bar_range"].lt(out["atr"] * config.absorption_range_atr)
    )
    volume_expansion = out["volume"].gt(
        out["average_volume"] * config.aggression_volume_multiplier
    )
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
    volume, _ = np.histogram(typical, bins=edges, weights=history["volume"])
    if volume.sum() <= 0.0:
        return np.nan, np.nan, np.nan
    centers = (edges[:-1] + edges[1:]) / 2.0
    poc_index = int(np.argmax(volume))
    selected = [poc_index]
    left, right = poc_index - 1, poc_index + 1
    cumulative = float(volume[poc_index])
    threshold = float(volume.sum() * value_fraction)
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
    return (
        float(centers[poc_index]),
        float(centers[min(selected)]),
        float(centers[max(selected)]),
    )


def _phase_move(
    bars: pd.DataFrame,
    session_date: str,
    phase: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any] | None:
    if not _complete_grid(bars, start, end):
        return None
    phase_bars = bars.loc[(bars.index >= start) & (bars.index < end)]
    phase_return = float(phase_bars["close"].iloc[-1] / phase_bars["open"].iloc[0] - 1.0)
    return {
        "session_date": session_date,
        "phase": phase,
        "phase_start": start,
        "phase_end": end,
        "observed_bars": int(len(phase_bars)),
        "return": phase_return,
        "absolute_return": abs(phase_return),
        "high_low_range": float(phase_bars["high"].max() / phase_bars["low"].min() - 1.0),
        "volume": float(phase_bars["volume"].sum()),
    }


def build_candidates(
    bars: pd.DataFrame,
    schedule: pd.DataFrame,
    config: NasdaqStrategyConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    indicated = add_indicators(bars, config)
    session_meta: list[dict[str, Any]] = []
    moves: list[dict[str, Any]] = []
    for row in schedule.itertuples(index=False):
        session_open = pd.Timestamp(row.session_open)
        session_close = pd.Timestamp(row.session_close)
        rth_complete = _complete_grid(indicated, session_open, session_close)
        rth = indicated.loc[(indicated.index >= session_open) & (indicated.index < session_close)]
        levels = (
            volume_profile_levels(
                rth,
                rows=config.profile_rows,
                value_fraction=config.profile_value_fraction,
            )
            if rth_complete
            else (np.nan, np.nan, np.nan)
        )
        session_meta.append({
            "session_date": row.session_date,
            "session_open": session_open,
            "session_close": session_close,
            "rth_complete": rth_complete,
            "rth_bars": int(len(rth)),
            "poc": levels[0],
            "val": levels[1],
            "vah": levels[2],
        })
        phase_bounds = {
            "opening_first_30m": (pd.Timestamp(row.opening_start), pd.Timestamp(row.opening_end)),
            "opening_followthrough_30m": (
                pd.Timestamp(row.execution_start),
                pd.Timestamp(row.execution_end),
            ),
            "closing_last_30m": (pd.Timestamp(row.closing_start), session_close),
            "after_close_30m": (session_close, pd.Timestamp(row.after_close_end)),
        }
        for phase, (start, end) in phase_bounds.items():
            move = _phase_move(indicated, row.session_date, phase, start, end)
            if move is not None:
                moves.append(move)

    candidates: list[dict[str, Any]] = []
    quality: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for current in session_meta:
        session_open = pd.Timestamp(current["session_open"])
        opening_end = session_open + pd.Timedelta(minutes=30)
        execution_end = session_open + pd.Timedelta(minutes=60)
        opening_complete = _complete_grid(indicated, session_open, opening_end)
        execution_complete = _complete_grid(indicated, opening_end, execution_end)
        prior_profile_complete = bool(previous is not None and previous["rth_complete"])
        usable = bool(opening_complete and execution_complete and prior_profile_complete)
        quality_row = {
            "session_date": current["session_date"],
            "session_open": session_open,
            "session_close": current["session_close"],
            "opening_complete": opening_complete,
            "execution_complete": execution_complete,
            "prior_rth_profile_complete": prior_profile_complete,
            "usable": usable,
            "day_regime": "unclassified",
        }
        if not usable:
            quality.append(quality_row)
            previous = current
            continue
        first_hour = indicated.loc[
            (indicated.index >= session_open) & (indicated.index < execution_end)
        ].copy()
        opening = first_hour.iloc[:6]
        execution = first_hour.iloc[6:12].copy()
        typical = (first_hour["high"] + first_hour["low"] + first_hour["close"]) / 3.0
        cumulative_volume = first_hour["volume"].cumsum()
        first_hour["session_vwap"] = (
            (typical * first_hour["volume"]).cumsum()
            / cumulative_volume.replace(0.0, np.nan)
        )
        opening = first_hour.iloc[:6]
        execution = first_hour.iloc[6:12]
        opening_high = float(opening["high"].max())
        opening_low = float(opening["low"].min())
        opening_close = float(opening["close"].iloc[-1])
        opening_open = float(opening["open"].iloc[0])
        opening_delta = float(opening["delta_proxy"].sum())
        opening_vwap = float(first_hour["session_vwap"].iloc[5])
        prior_poc = float(previous["poc"])
        prior_val = float(previous["val"])
        prior_vah = float(previous["vah"])
        if (
            opening_close > prior_vah
            and opening_close > opening_vwap
            and opening_close > opening_open
            and opening_delta > 0.0
        ):
            regime = "imbalance_up"
        elif (
            opening_close < prior_val
            and opening_close < opening_vwap
            and opening_close < opening_open
            and opening_delta < 0.0
        ):
            regime = "imbalance_down"
        else:
            regime = "balance"
        quality_row["day_regime"] = regime
        quality_row.update({
            "prior_poc": prior_poc,
            "prior_val": prior_val,
            "prior_vah": prior_vah,
            "opening_range_high": opening_high,
            "opening_range_low": opening_low,
            "opening_delta_proxy": opening_delta,
        })
        quality.append(quality_row)
        for timestamp, bar in execution.iterrows():
            prior_bar = indicated.iloc[int(bar["bar_id"]) - 1]
            tolerance = float(bar["atr"] * config.location_tolerance_atr)
            orb_long = bool(
                regime == "imbalance_up"
                and bar["aggressive_up"]
                and bar["close"] > opening_high
                and prior_bar["close"] <= opening_high
                and bar["smoothed_delta_proxy"] > 0.0
                and bar["close"] > bar["session_vwap"]
            )
            orb_short = bool(
                regime == "imbalance_down"
                and bar["aggressive_down"]
                and bar["close"] < opening_low
                and prior_bar["close"] >= opening_low
                and bar["smoothed_delta_proxy"] < 0.0
                and bar["close"] < bar["session_vwap"]
            )
            balance_long = bool(
                regime == "balance"
                and bar["aggressive_up"]
                and bar["low"] <= prior_val + tolerance
                and bar["close"] > prior_val
                and bar["smoothed_delta_proxy"] > 0.0
                and bar["close"] > bar["session_vwap"]
            )
            balance_short = bool(
                regime == "balance"
                and bar["aggressive_down"]
                and bar["high"] >= prior_vah - tolerance
                and bar["close"] < prior_vah
                and bar["smoothed_delta_proxy"] < 0.0
                and bar["close"] < bar["session_vwap"]
            )
            setup = ""
            side = 0
            if orb_long or orb_short:
                setup = "imbalance_opening_range_breakout"
                side = 1 if orb_long else -1
            elif balance_long or balance_short:
                setup = "balance_value_rejection"
                side = 1 if balance_long else -1
            payload = bar.to_dict()
            payload.update({
                "timestamp": timestamp,
                "session_date": current["session_date"],
                "session_open": session_open,
                "phase": "opening_followthrough_30m",
                "phase_end": execution_end,
                "day_regime": regime,
                "setup": setup,
                "signal_side": side,
                "opening_range_high": opening_high,
                "opening_range_low": opening_low,
                "opening_delta_proxy": opening_delta,
                "prior_poc": prior_poc,
                "prior_val": prior_val,
                "prior_vah": prior_vah,
            })
            candidates.append(payload)
        previous = current
    return pd.DataFrame(candidates), pd.DataFrame(moves), pd.DataFrame(quality)


def simulate_trade(
    signal: pd.Series,
    bars: pd.DataFrame,
    config: NasdaqStrategyConfig,
    execution: NasdaqExecutionCosts,
) -> dict[str, Any] | None:
    signal_id = int(signal["bar_id"])
    entry_id = signal_id + 1
    if entry_id >= len(bars):
        return None
    entry_time = bars.index[entry_id]
    phase_end = pd.Timestamp(signal["phase_end"])
    if entry_time != pd.Timestamp(signal["timestamp"]) + BAR_INTERVAL or entry_time >= phase_end:
        return None
    entry_price = float(bars.iloc[entry_id]["open"])
    atr = float(signal["atr"])
    if not np.isfinite(atr) or atr <= 0.0:
        return None
    stop_distance = atr * config.stop_atr
    stop_fraction = stop_distance / entry_price
    notional_fraction = min(
        config.max_notional_fraction,
        config.risk_fraction / stop_fraction,
    )
    side = int(signal["signal_side"])
    stop_price = entry_price - side * stop_distance
    target_price = entry_price + side * stop_distance * config.reward_to_risk
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
            exit_price, exit_time, exit_reason = stop_price, timestamp, "stop"
            break
        if target_hit:
            exit_price, exit_time, exit_reason = target_price, timestamp, "target"
            break
        exit_price = float(bar["close"])
        exit_time = timestamp
        exit_reason = "phase_end" if timestamp + BAR_INTERVAL >= phase_end else "max_holding"
        if timestamp + BAR_INTERVAL >= phase_end:
            break
    gross_return = side * notional_fraction * (exit_price / entry_price - 1.0)
    one_way_turnover = 2.0 * notional_fraction
    execution_cost = one_way_turnover * execution.one_way_cost_rate
    net_return = gross_return - execution_cost
    deployed_risk = notional_fraction * stop_fraction
    return {
        "signal_time": pd.Timestamp(signal["timestamp"]),
        "entry_time": entry_time,
        "exit_time": exit_time,
        "session_date": signal["session_date"],
        "phase": signal["phase"],
        "day_regime": signal["day_regime"],
        "setup": signal["setup"],
        "side": "long" if side > 0 else "short",
        "entry_price": entry_price,
        "stop_price": stop_price,
        "target_price": target_price,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "holding_bars": int((exit_time - entry_time) / BAR_INTERVAL) + 1,
        "notional_fraction": notional_fraction,
        "risk_fraction_deployed": deployed_risk,
        "gross_return": gross_return,
        "one_way_turnover": one_way_turnover,
        "execution_cost": execution_cost,
        "net_return": net_return,
        "gross_r_multiple": gross_return / deployed_risk if deployed_risk > 0.0 else np.nan,
        "net_r_multiple": net_return / deployed_risk if deployed_risk > 0.0 else np.nan,
    }


def run_backtest(
    candidates: pd.DataFrame,
    bars: pd.DataFrame,
    config: NasdaqStrategyConfig,
    execution: NasdaqExecutionCosts,
) -> tuple[pd.DataFrame, dict[str, int]]:
    signals = candidates.loc[candidates["signal_side"].ne(0)].sort_values("timestamp")
    trades: list[dict[str, Any]] = []
    losses_by_session: dict[str, int] = {}
    last_exit = pd.Timestamp.min.tz_localize("UTC")
    blocked = {"overlap": 0, "daily_loss_stop": 0, "unexecutable": 0}
    for _, signal in signals.iterrows():
        signal_time = pd.Timestamp(signal["timestamp"])
        session_date = str(signal["session_date"])
        if signal_time <= last_exit:
            blocked["overlap"] += 1
            continue
        if losses_by_session.get(session_date, 0) >= config.max_daily_losses:
            blocked["daily_loss_stop"] += 1
            continue
        trade = simulate_trade(signal, bars, config, execution)
        if trade is None:
            blocked["unexecutable"] += 1
            continue
        trades.append(trade)
        last_exit = pd.Timestamp(trade["exit_time"])
        if float(trade["net_return"]) < 0.0:
            losses_by_session[session_date] = losses_by_session.get(session_date, 0) + 1
    return pd.DataFrame(trades), blocked


def _metrics(frame: pd.DataFrame, scope: str) -> dict[str, Any]:
    if frame.empty:
        return {"scope": scope, "trades": 0}
    frame = frame.sort_values("entry_time")
    gross = frame["gross_return"].astype(float)
    net = frame["net_return"].astype(float)
    equity = (1.0 + net).cumprod()
    years = max(
        (pd.Timestamp(frame["exit_time"].max()) - pd.Timestamp(frame["entry_time"].min())).days
        / 365.25,
        1.0 / 365.25,
    )
    gross_losses = gross.loc[gross < 0.0]
    net_losses = net.loc[net < 0.0]
    turnover = float(frame["one_way_turnover"].sum())
    return {
        "scope": scope,
        "trades": int(len(frame)),
        "sessions": int(frame["session_date"].nunique()),
        "win_rate": float(net.gt(0.0).mean()),
        "target_rate": float(frame["exit_reason"].eq("target").mean()),
        "stop_rate": float(frame["exit_reason"].eq("stop").mean()),
        "average_gross_r": float(frame["gross_r_multiple"].mean()),
        "average_net_r": float(frame["net_r_multiple"].mean()),
        "average_gross_return_bps": float(gross.mean() * 10_000.0),
        "average_net_return_bps": float(net.mean() * 10_000.0),
        "gross_profit_factor": float(gross.loc[gross > 0.0].sum() / abs(gross_losses.sum()))
        if gross_losses.sum() < 0.0 else np.nan,
        "net_profit_factor": float(net.loc[net > 0.0].sum() / abs(net_losses.sum()))
        if net_losses.sum() < 0.0 else np.nan,
        "break_even_one_way_cost_bps": float(gross.sum() / turnover * 10_000.0)
        if turnover > 0.0 else np.nan,
        "cumulative_net_return": float(equity.iloc[-1] - 1.0),
        "annualized_net_return": float(equity.iloc[-1] ** (1.0 / years) - 1.0),
        "max_drawdown": float((equity / equity.cummax() - 1.0).min()),
        "average_notional_fraction": float(frame["notional_fraction"].mean()),
        "median_risk_fraction_deployed": float(frame["risk_fraction_deployed"].median()),
        "average_holding_bars": float(frame["holding_bars"].mean()),
    }


def _scopes(trades: pd.DataFrame) -> dict[str, pd.DataFrame]:
    data = trades.copy()
    if not data.empty:
        data["entry_time"] = pd.to_datetime(data["entry_time"], utc=True)
    return {
        "all": data,
        "development_2024": data.loc[data["entry_time"] < HOLDOUT_START] if not data.empty else data,
        "holdout_2025": data.loc[data["entry_time"] >= HOLDOUT_START] if not data.empty else data,
    }


def trade_summary(trades: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for scope, scoped in _scopes(trades).items():
        rows.append(_metrics(scoped, scope))
        if not scoped.empty:
            for setup, group in scoped.groupby("setup", sort=True):
                rows.append(_metrics(group, f"{scope}::setup::{setup}"))
            for regime, group in scoped.groupby("day_regime", sort=True):
                rows.append(_metrics(group, f"{scope}::regime::{regime}"))
    return pd.DataFrame(rows)


def cost_sensitivity(trades: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for scope, scoped in _scopes(trades).items():
        groups = [("all", scoped)]
        if not scoped.empty:
            groups.extend((str(name), group) for name, group in scoped.groupby("setup", sort=True))
        for setup, group in groups:
            for cost_bps in [0.0, 0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0]:
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


def phase_summary(moves: pd.DataFrame) -> pd.DataFrame:
    data = moves.copy()
    data["phase_start"] = pd.to_datetime(data["phase_start"], utc=True)
    scopes = {
        "all": data,
        "development_2024": data.loc[data["phase_start"] < HOLDOUT_START],
        "holdout_2025": data.loc[data["phase_start"] >= HOLDOUT_START],
    }
    rows: list[dict[str, Any]] = []
    for scope, scoped in scopes.items():
        for phase, group in scoped.groupby("phase", sort=True):
            values = group["return"].astype(float)
            standard_error = values.std(ddof=1) / math.sqrt(len(values)) if len(values) > 1 else np.nan
            rows.append({
                "scope": scope,
                "phase": phase,
                "observations": int(len(group)),
                "mean_return_bps": float(values.mean() * 10_000.0),
                "median_return_bps": float(values.median() * 10_000.0),
                "positive_rate": float(values.gt(0.0).mean()),
                "mean_absolute_return_bps": float(group["absolute_return"].mean() * 10_000.0),
                "mean_range_bps": float(group["high_low_range"].mean() * 10_000.0),
                "mean_return_tstat": float(values.mean() / standard_error)
                if standard_error > 0.0 else np.nan,
            })
    return pd.DataFrame(rows)


def session_bootstrap(trades: pd.DataFrame, samples: int = 5_000) -> pd.DataFrame:
    rng = np.random.default_rng(20260722)
    rows: list[dict[str, Any]] = []
    for scope, scoped in _scopes(trades).items():
        groups = [("all", scoped)]
        if not scoped.empty:
            groups.extend((str(name), group) for name, group in scoped.groupby("setup", sort=True))
        for setup, group in groups:
            if group.empty:
                rows.append({"scope": scope, "setup": setup, "sessions": 0})
                continue
            daily = group.groupby("session_date", sort=True)["net_return"].apply(
                lambda values: float((1.0 + values).prod() - 1.0)
            ).to_numpy(dtype=float)
            draws = rng.choice(daily, size=(samples, len(daily)), replace=True).mean(axis=1)
            rows.append({
                "scope": scope,
                "setup": setup,
                "sessions": int(len(daily)),
                "mean_session_return_bps": float(daily.mean() * 10_000.0),
                "bootstrap_mean_ci_low_bps": float(np.quantile(draws, 0.025) * 10_000.0),
                "bootstrap_mean_ci_high_bps": float(np.quantile(draws, 0.975) * 10_000.0),
                "bootstrap_probability_mean_positive": float((draws > 0.0).mean()),
            })
    return pd.DataFrame(rows)


def signal_funnel(candidates: pd.DataFrame) -> pd.DataFrame:
    checks = {
        "execution_window_bars": pd.Series(True, index=candidates.index),
        "imbalance_regime_bars": candidates["day_regime"].str.startswith("imbalance"),
        "balance_regime_bars": candidates["day_regime"].eq("balance"),
        "aggressive_expansion": candidates["aggressive_up"] | candidates["aggressive_down"],
        "absorption_proxy": candidates["absorption_proxy"],
        "imbalance_orb_signals": candidates["setup"].eq("imbalance_opening_range_breakout"),
        "balance_rejection_signals": candidates["setup"].eq("balance_value_rejection"),
    }
    return pd.DataFrame([
        {
            "stage": stage,
            "observations": int(mask.fillna(False).sum()),
            "share_of_execution_bars": float(mask.fillna(False).mean()),
        }
        for stage, mask in checks.items()
    ])


def regime_counts(quality: pd.DataFrame) -> pd.DataFrame:
    data = quality.loc[quality["usable"]].copy()
    data["session_date"] = pd.to_datetime(data["session_date"], utc=True)
    data["scope"] = np.where(data["session_date"] < HOLDOUT_START, "development_2024", "holdout_2025")
    return (
        data.groupby(["scope", "day_regime"], sort=True)
        .size()
        .rename("sessions")
        .reset_index()
    )


def _markdown_table(frame: pd.DataFrame, rows: int = 60) -> str:
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
    phases: pd.DataFrame,
    sensitivity: pd.DataFrame,
    bootstrap: pd.DataFrame,
    regimes: pd.DataFrame,
    funnel: pd.DataFrame,
    governance: dict[str, Any],
) -> str:
    holdout_summary = summary.loc[summary["scope"].str.startswith("holdout_2025")]
    holdout_costs = sensitivity.loc[sensitivity["scope"].eq("holdout_2025")]
    return f"""# Nasdaq-100 Five-Minute New York-Open Backtest

Generated {governance['generated_at_utc']}. This is a standalone strategy with no macro or hierarchical-model inputs.

> **Data identity warning:** the CSV has no venue or contract metadata, and {governance['data_quality']['close_not_on_nq_quarter_tick_share']:.1%} of one-minute closes are off CME NQ's 0.25-point grid. Results are percentage-return research on an unverified Nasdaq-100 cash/CFD-like feed, not a CME NQ execution backtest.

## Holdout decision table

{_markdown_table(holdout_summary)}

## Full decision table

{_markdown_table(summary)}

## Holdout cost sensitivity

{_markdown_table(holdout_costs)}

## Session-block bootstrap

{_markdown_table(bootstrap)}

## Auction-regime counts

{_markdown_table(regimes)}

## Unconditional timing audit

{_markdown_table(phases)}

## Signal funnel

{_markdown_table(funnel)}

## Predeclared causal rules

- The raw one-minute file is aggregated into complete five-minute bars; incomplete groups are dropped.
- XNYS calendars determine the 09:30 New York cash open, holidays, DST and early closes.
- The prior completed regular session supplies a 24-row, 70% typical-price volume-profile approximation.
- The first 30 minutes is observation only. An opening close outside the prior value area, aligned with opening return, session VWAP and close-location volume proxy, defines imbalance; otherwise the day is balance.
- During minutes 30-60, imbalance trades require a fresh opening-range break in the regime direction. Balance trades require rejection at the prior value-area edge.
- Both setups require aligned smoothed delta proxy, VWAP and aggressive range/volume expansion. These are OHLCV proxies, not bid/ask order flow.
- Signals enter at the next five-minute open. Stops are one ATR, targets are 2R, same-bar stop/target ambiguity resolves to the stop, and positions close no later than the end of the execution window.
- Risk is {governance['config']['risk_fraction'] * 100.0:.2f}% of current equity at the stop, capped at {governance['config']['max_notional_fraction']:.1f}x notional. Trading stops after three net losses in the session.
- 2024 is development and 2025 is the untouched temporal holdout. No parameters are selected using holdout performance.

## Limitations

- No symbol, source, venue, contract, expiry or roll metadata was supplied; futures contract sizing, tick rounding and broker margin cannot be modeled honestly.
- Volume provenance is unknown and may be CFD tick volume. Volume profile, delta and absorption are therefore proxies.
- Five-minute OHLCV cannot reveal aggressor side, resting liquidity, queue position, partial fills or true footprint/CVD.
- The configured {governance['execution']['one_way_cost_bps']:.2f} bps one-way execution cost is a scenario, not a measured spread/commission. Use the sensitivity table until actual venue costs are supplied.
- The sample spans only 2024 through 5 December 2025. Even holdout results need a fresh forward or genuinely identified NQ dataset before capital deployment.
"""


def build_nasdaq_backtest(
    project_root: str | Path | None = None,
    *,
    data_path: str | Path = DEFAULT_DATA,
    execution_path: str | Path = DEFAULT_EXECUTION,
    output_dir: str | Path = DEFAULT_OUTPUT,
    config: NasdaqStrategyConfig | None = None,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    data_file = Path(data_path)
    execution_file = Path(execution_path)
    output = Path(output_dir)
    if not data_file.is_absolute():
        data_file = root / data_file
    if not execution_file.is_absolute():
        execution_file = root / execution_file
    if not output.is_absolute():
        output = root / output
    output.mkdir(parents=True, exist_ok=True)
    strategy = config or NasdaqStrategyConfig()
    execution = load_execution_costs(execution_file)
    bars, data_audit = load_nasdaq_bars(data_file)
    schedule = build_ny_schedule(bars.index.min(), bars.index.max())
    candidates, moves, quality = build_candidates(bars, schedule, strategy)
    trades, blocked = run_backtest(candidates, bars, strategy, execution)
    summary = trade_summary(trades)
    phases = phase_summary(moves)
    sensitivity = cost_sensitivity(trades)
    bootstrap = session_bootstrap(trades)
    regimes = regime_counts(quality)
    funnel = signal_funnel(candidates)
    signals = candidates.loc[candidates["signal_side"].ne(0)].copy()
    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "strategy": "standalone_nasdaq_new_york_open_auction_proxy",
        "macro_or_hierarchy_inputs": False,
        "data_file": str(data_file),
        "data_quality": data_audit,
        "config": asdict(strategy),
        "execution": execution.to_dict(),
        "calendar": CALENDAR_NAME,
        "holdout_start": HOLDOUT_START.isoformat(),
        "usable_sessions": int(quality["usable"].sum()),
        "excluded_sessions": int((~quality["usable"]).sum()),
        "raw_signals": int(len(signals)),
        "executed_trades": int(len(trades)),
        "blocked_signals": blocked,
        "profit_scaling": "disabled: no exact auditable scaling equation supplied",
        "research_only_reasons": [
            "instrument and venue identity are absent",
            "price grid is inconsistent with CME NQ",
            "volume provenance is absent",
            "five-minute OHLCV is not genuine order flow",
        ],
    }
    schedule.to_csv(output / "session_schedule.csv", index=False)
    quality.to_csv(output / "session_quality_and_regime.csv", index=False)
    moves.to_csv(output / "phase_moves.csv", index=False)
    signal_columns = [
        "timestamp", "session_date", "day_regime", "setup", "signal_side",
        "open", "high", "low", "close", "volume", "atr", "session_vwap",
        "opening_range_high", "opening_range_low", "prior_poc", "prior_val", "prior_vah",
        "smoothed_delta_proxy", "aggressive_up", "aggressive_down", "absorption_proxy",
    ]
    signals[[column for column in signal_columns if column in signals]].to_csv(
        output / "signals.csv", index=False
    )
    trades.to_csv(output / "trades.csv", index=False)
    summary.to_csv(output / "summary.csv", index=False)
    phases.to_csv(output / "phase_summary.csv", index=False)
    sensitivity.to_csv(output / "cost_sensitivity.csv", index=False)
    bootstrap.to_csv(output / "bootstrap.csv", index=False)
    regimes.to_csv(output / "regime_counts.csv", index=False)
    funnel.to_csv(output / "signal_funnel.csv", index=False)
    (output / "governance.json").write_text(json.dumps(governance, indent=2), encoding="utf-8")
    (output / "report.md").write_text(
        build_report(summary, phases, sensitivity, bootstrap, regimes, funnel, governance),
        encoding="utf-8",
    )
    return {
        "output_dir": output,
        "trades": trades,
        "summary": summary,
        "phase_summary": phases,
        "cost_sensitivity": sensitivity,
        "bootstrap": bootstrap,
        "governance": governance,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--data-path", default=str(DEFAULT_DATA))
    parser.add_argument("--execution-path", default=str(DEFAULT_EXECUTION))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_nasdaq_backtest(
        args.project_root,
        data_path=args.data_path,
        execution_path=args.execution_path,
        output_dir=args.output_dir,
    )
    print(f"Report: {result['output_dir'] / 'report.md'}")
    print(result["summary"].to_string(index=False))


if __name__ == "__main__":
    main()
