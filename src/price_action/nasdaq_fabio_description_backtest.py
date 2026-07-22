"""Causal OHLCV test of the attached Fabio-inspired strategy description.

The source description is not executable code.  This module freezes one literal
interpretation of its published defaults without parameter optimization.  It is
an OHLCV proxy and must not be described as Fabio Valentini's actual strategy.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from price_action.data import resolve_project_root
from price_action.nasdaq_macro_poc_assessment import load_nasdaq_source


DEFAULT_DATA = Path("cache/Nasdaq.csv")
DEFAULT_SCHEDULE = Path("outputs/nasdaq_session_backtest/session_schedule.csv")
DEFAULT_OUTPUT = Path("outputs/nasdaq_fabio_description_backtest")
HOLDOUT_START = pd.Timestamp("2025-01-01", tz="UTC")


@dataclass(frozen=True)
class FabioProxyConfig:
    profile_lookback_bars: int = 50
    profile_rows: int = 24
    profile_value_fraction: float = 0.70
    atr_bars: int = 14
    average_volume_bars: int = 50
    delta_smoothing_bars: int = 5
    absorption_volume_multiplier: float = 2.0
    absorption_range_atr: float = 0.30
    absorption_memory_bars: int = 6
    accumulation_bars: int = 3
    accumulation_range_atr: float = 0.80
    aggression_volume_multiplier: float = 1.25
    aggression_range_atr: float = 0.80
    location_tolerance_atr: float = 0.20
    vwap_band_atr: float = 0.50
    opening_range_minutes: int = 30
    orb_entry_window_minutes: int = 30
    stop_atr: float = 1.0
    reward_to_risk: float = 2.0
    maximum_holding_minutes: int = 30
    base_risk_fraction: float = 0.0025
    maximum_risk_fraction: float = 0.0075
    profit_reinvestment_fraction: float = 0.50
    maximum_leverage: float = 10.0
    maximum_daily_losses: int = 3
    reference_one_way_cost_bps: float = 0.50
    cost_scenarios_bps: tuple[float, ...] = (0.0, 0.25, 0.50, 1.00, 1.50, 2.00)
    mnq_multiplier: float = 2.0
    mnq_round_turn_fees: float = 1.50
    mnq_round_turn_slippage_points: float = 0.50
    account_sizes: tuple[float, ...] = (25_000.0, 100_000.0)
    bootstrap_samples: int = 5_000
    bootstrap_seed: int = 29


def resample_complete_bars(raw: pd.DataFrame, bar_minutes: int) -> pd.DataFrame:
    if bar_minutes not in {1, 2, 5}:
        raise ValueError("bar_minutes must be 1, 2, or 5")
    if bar_minutes == 1:
        out = raw[["open", "high", "low", "close", "volume"]].copy()
    else:
        rule = f"{bar_minutes}min"
        counts = raw["close"].resample(rule, origin="epoch").count()
        out = raw.resample(rule, origin="epoch").agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        out = out.loc[counts.eq(bar_minutes)].dropna()
    out["bar_id"] = np.arange(len(out), dtype=int)
    return out


def add_indicators(frame: pd.DataFrame, config: FabioProxyConfig) -> pd.DataFrame:
    out = frame.copy()
    prior_close = out["close"].shift(1)
    true_range = pd.concat([
        out["high"] - out["low"],
        (out["high"] - prior_close).abs(),
        (out["low"] - prior_close).abs(),
    ], axis=1).max(axis=1)
    out["atr"] = true_range.rolling(config.atr_bars, min_periods=config.atr_bars).mean()
    out["average_volume"] = out["volume"].shift(1).rolling(
        config.average_volume_bars, min_periods=config.average_volume_bars
    ).mean()
    bar_range = (out["high"] - out["low"]).replace(0.0, np.nan)
    out["bar_range"] = bar_range.fillna(0.0)
    out["close_location"] = ((out["close"] - out["low"]) / bar_range).fillna(0.5).clip(0.0, 1.0)
    out["delta_proxy"] = (
        ((2.0 * out["close"] - out["high"] - out["low"]) / bar_range).fillna(0.0)
        * out["volume"]
    )
    out["smoothed_delta_proxy"] = out["delta_proxy"].rolling(
        config.delta_smoothing_bars, min_periods=config.delta_smoothing_bars
    ).sum()
    out["absorption"] = (
        out["volume"].gt(out["average_volume"] * config.absorption_volume_multiplier)
        & out["bar_range"].lt(out["atr"] * config.absorption_range_atr)
    )
    out["recent_absorption"] = out["absorption"].shift(1).rolling(
        config.absorption_memory_bars, min_periods=1
    ).max().fillna(0.0).astype(bool)
    out["prior_accumulation_high"] = out["high"].shift(1).rolling(
        config.accumulation_bars, min_periods=config.accumulation_bars
    ).max()
    out["prior_accumulation_low"] = out["low"].shift(1).rolling(
        config.accumulation_bars, min_periods=config.accumulation_bars
    ).min()
    out["accumulation"] = (
        out["prior_accumulation_high"] - out["prior_accumulation_low"]
    ).lt(out["atr"] * config.accumulation_range_atr)
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
    rows: int = 24,
    value_fraction: float = 0.70,
) -> tuple[float, float, float]:
    """Assign each completed bar's volume to typical price and expand from POC."""
    if history.empty:
        return np.nan, np.nan, np.nan
    low, high = float(history["low"].min()), float(history["high"].max())
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        return np.nan, np.nan, np.nan
    edges = np.linspace(low, high, rows + 1)
    typical = history[["high", "low", "close"]].mean(axis=1).to_numpy()
    volume, _ = np.histogram(typical, bins=edges, weights=history["volume"].to_numpy())
    if float(volume.sum()) <= 0.0:
        return np.nan, np.nan, np.nan
    centers = (edges[:-1] + edges[1:]) / 2.0
    poc_index = int(np.argmax(volume))
    selected = [poc_index]
    left, right = poc_index - 1, poc_index + 1
    cumulative = float(volume[poc_index])
    threshold = float(volume.sum()) * value_fraction
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
    return float(centers[poc_index]), float(centers[min(selected)]), float(centers[max(selected)])


def load_schedule(path: str | Path) -> pd.DataFrame:
    schedule = pd.read_csv(path)
    required = {"session_date", "session_open", "session_close"}
    missing = required - set(schedule.columns)
    if missing:
        raise ValueError(f"Schedule is missing columns: {sorted(missing)}")
    schedule = schedule.drop_duplicates("session_date", keep="last")
    schedule["session_open"] = pd.to_datetime(schedule["session_open"], utc=True, errors="raise")
    schedule["session_close"] = pd.to_datetime(schedule["session_close"], utc=True, errors="raise")
    return schedule.sort_values("session_open").reset_index(drop=True)


def _complete_grid(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, minutes: int) -> bool:
    expected = pd.date_range(start, end - pd.Timedelta(minutes=minutes), freq=f"{minutes}min", tz="UTC")
    actual = frame.loc[(frame.index >= start) & (frame.index < end)].index
    return bool(len(actual) == len(expected) and actual.equals(expected))


def build_signals(
    bars: pd.DataFrame,
    schedule: pd.DataFrame,
    bar_minutes: int,
    config: FabioProxyConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build causal signals; rolling profiles exclude the signal bar."""
    indicated = add_indicators(bars, config)
    records: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for session in schedule.itertuples(index=False):
        session_open = pd.Timestamp(session.session_open)
        session_close = pd.Timestamp(session.session_close)
        opening_end = session_open + pd.Timedelta(minutes=config.opening_range_minutes)
        orb_end = opening_end + pd.Timedelta(minutes=config.orb_entry_window_minutes)
        complete = _complete_grid(indicated, session_open, session_close, bar_minutes)
        rth = indicated.loc[(indicated.index >= session_open) & (indicated.index < session_close)].copy()
        opening = rth.loc[rth.index < opening_end]
        opening_complete = _complete_grid(indicated, session_open, opening_end, bar_minutes)
        diagnostics.append({
            "bar_minutes": bar_minutes,
            "session_date": session.session_date,
            "rth_complete": complete,
            "opening_complete": opening_complete,
            "rth_bars": int(len(rth)),
        })
        if not complete or not opening_complete or rth.empty:
            continue
        opening_high, opening_low = float(opening["high"].max()), float(opening["low"].min())
        typical = rth[["high", "low", "close"]].mean(axis=1)
        cumulative_volume = rth["volume"].cumsum().replace(0.0, np.nan)
        rth["session_vwap"] = (typical * rth["volume"]).cumsum() / cumulative_volume
        for timestamp, bar in rth.iterrows():
            bar_id = int(bar["bar_id"])
            if bar_id < config.profile_lookback_bars or not np.isfinite(float(bar["atr"])):
                continue
            accumulation_low = float(bar["prior_accumulation_low"])
            accumulation_high = float(bar["prior_accumulation_high"])
            potential_triple_long = bool(
                bar["recent_absorption"] and bar["accumulation"]
                and bar["aggressive_up"] and bar["close"] > accumulation_high
                and bar["smoothed_delta_proxy"] > 0.0 and bar["close"] > bar["session_vwap"]
            )
            potential_triple_short = bool(
                bar["recent_absorption"] and bar["accumulation"]
                and bar["aggressive_down"] and bar["close"] < accumulation_low
                and bar["smoothed_delta_proxy"] < 0.0 and bar["close"] < bar["session_vwap"]
            )
            potential_bounce_long = bool(
                bar["close_location"] >= 0.60 and bar["smoothed_delta_proxy"] > 0.0
                and bar["volume"] > bar["average_volume"]
            )
            potential_bounce_short = bool(
                bar["close_location"] <= 0.40 and bar["smoothed_delta_proxy"] < 0.0
                and bar["volume"] > bar["average_volume"]
            )
            prior_close = float(indicated.iloc[bar_id - 1]["close"])
            orb_window = opening_end <= timestamp < orb_end
            orb_long = bool(
                orb_window and bar["aggressive_up"] and prior_close <= opening_high
                and bar["close"] > opening_high and bar["smoothed_delta_proxy"] > 0.0
                and bar["close"] > bar["session_vwap"]
            )
            orb_short = bool(
                orb_window and bar["aggressive_down"] and prior_close >= opening_low
                and bar["close"] < opening_low and bar["smoothed_delta_proxy"] < 0.0
                and bar["close"] < bar["session_vwap"]
            )
            needs_profile = any((
                potential_triple_long, potential_triple_short,
                potential_bounce_long, potential_bounce_short,
            ))
            if needs_profile:
                history = indicated.iloc[bar_id - config.profile_lookback_bars:bar_id]
                poc, val, vah = volume_profile_levels(
                    history, rows=config.profile_rows, value_fraction=config.profile_value_fraction
                )
            else:
                poc, val, vah = np.nan, np.nan, np.nan
            tolerance = float(bar["atr"]) * config.location_tolerance_atr
            location_touch = bool(
                np.isfinite(poc)
                and any(
                    accumulation_low - tolerance <= level <= accumulation_high + tolerance
                    for level in (poc, val, vah)
                )
            )
            triple_long = potential_triple_long and location_touch
            triple_short = potential_triple_short and location_touch
            bounce_long = bool(
                potential_bounce_long and np.isfinite(val)
                and bar["low"] <= val + tolerance and bar["close"] > val
            )
            bounce_short = bool(
                potential_bounce_short and np.isfinite(vah)
                and bar["high"] >= vah - tolerance and bar["close"] < vah
            )
            setup, side = "", 0
            if bounce_long or bounce_short:
                setup, side = "value_area_bounce", 1 if bounce_long else -1
            if orb_long or orb_short:
                setup, side = "opening_range_breakout", 1 if orb_long else -1
            if triple_long or triple_short:
                setup, side = "triple_a", 1 if triple_long else -1
            if side == 0:
                continue
            records.append({
                "bar_minutes": bar_minutes,
                "signal_time": timestamp,
                "session_date": str(session.session_date),
                "session_close": session_close,
                "bar_id": bar_id,
                "setup": setup,
                "side": side,
                "atr": float(bar["atr"]),
                "entry_reference_close": float(bar["close"]),
                "profile_poc": poc,
                "profile_val": val,
                "profile_vah": vah,
                "session_vwap": float(bar["session_vwap"]),
                "vwap_upper": float(bar["session_vwap"] + config.vwap_band_atr * bar["atr"]),
                "vwap_lower": float(bar["session_vwap"] - config.vwap_band_atr * bar["atr"]),
                "absorption": bool(bar["absorption"]),
                "recent_absorption": bool(bar["recent_absorption"]),
                "accumulation": bool(bar["accumulation"]),
                "smoothed_delta_proxy": float(bar["smoothed_delta_proxy"]),
            })
    return pd.DataFrame(records), pd.DataFrame(diagnostics)


def simulate_signal(
    signal: pd.Series,
    bars: pd.DataFrame,
    config: FabioProxyConfig,
) -> dict[str, Any] | None:
    bar_minutes = int(signal["bar_minutes"])
    entry_id = int(signal["bar_id"]) + 1
    if entry_id >= len(bars):
        return None
    entry_time = bars.index[entry_id]
    expected = pd.Timestamp(signal["signal_time"]) + pd.Timedelta(minutes=bar_minutes)
    session_close = pd.Timestamp(signal["session_close"])
    if entry_time != expected or entry_time >= session_close:
        return None
    entry_price = float(bars.iloc[entry_id]["open"])
    stop_distance = float(signal["atr"]) * config.stop_atr
    if stop_distance <= 0.0:
        return None
    side = int(signal["side"])
    stop_price = entry_price - side * stop_distance
    target_price = entry_price + side * stop_distance * config.reward_to_risk
    maximum_bars = max(1, config.maximum_holding_minutes // bar_minutes)
    final_id = min(entry_id + maximum_bars - 1, len(bars) - 1)
    exit_price, exit_time, exit_reason = entry_price, entry_time, "time_exit"
    for bar_id in range(entry_id, final_id + 1):
        timestamp = bars.index[bar_id]
        if timestamp >= session_close:
            break
        bar = bars.iloc[bar_id]
        stop_hit = float(bar["low"]) <= stop_price if side > 0 else float(bar["high"]) >= stop_price
        target_hit = float(bar["high"]) >= target_price if side > 0 else float(bar["low"]) <= target_price
        if stop_hit:
            exit_price, exit_time, exit_reason = stop_price, timestamp, "stop"
            break
        if target_hit:
            exit_price, exit_time, exit_reason = target_price, timestamp, "target"
            break
        exit_price, exit_time = float(bar["close"]), timestamp
        exit_reason = "session_close" if timestamp + pd.Timedelta(minutes=bar_minutes) >= session_close else "time_exit"
    signed_price_return = side * (exit_price / entry_price - 1.0)
    return {
        "bar_minutes": bar_minutes,
        "signal_time": signal["signal_time"],
        "entry_time": entry_time,
        "exit_time": exit_time,
        "session_date": signal["session_date"],
        "setup": signal["setup"],
        "side": "long" if side > 0 else "short",
        "entry_price": entry_price,
        "stop_distance_points": stop_distance,
        "stop_fraction": stop_distance / entry_price,
        "target_price": target_price,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "holding_minutes": int((pd.Timestamp(exit_time) - entry_time) / pd.Timedelta(minutes=1)) + bar_minutes,
        "signed_price_return": signed_price_return,
        "gross_r": signed_price_return / (stop_distance / entry_price),
    }


def run_trade_ledger(
    signals: pd.DataFrame,
    bars: pd.DataFrame,
    config: FabioProxyConfig,
) -> tuple[pd.DataFrame, dict[str, int]]:
    trades: list[dict[str, Any]] = []
    losses: dict[str, int] = {}
    last_exit = pd.Timestamp.min.tz_localize("UTC")
    blocked = {"overlap": 0, "daily_loss_stop": 0, "unexecutable": 0}
    for _, signal in signals.sort_values("signal_time").iterrows():
        session = str(signal["session_date"])
        if pd.Timestamp(signal["signal_time"]) <= last_exit:
            blocked["overlap"] += 1
            continue
        if losses.get(session, 0) >= config.maximum_daily_losses:
            blocked["daily_loss_stop"] += 1
            continue
        trade = simulate_signal(signal, bars, config)
        if trade is None:
            blocked["unexecutable"] += 1
            continue
        trades.append(trade)
        last_exit = pd.Timestamp(trade["exit_time"])
        if float(trade["gross_r"]) < 0.0:
            losses[session] = losses.get(session, 0) + 1
    return pd.DataFrame(trades), blocked


def account_path(
    trades: pd.DataFrame,
    config: FabioProxyConfig,
    *,
    one_way_cost_bps: float,
    profit_financed: bool = False,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    equity = 1.0
    current_session: str | None = None
    start_of_day = equity
    for trade in trades.sort_values("entry_time").itertuples(index=False):
        session = str(trade.session_date)
        if session != current_session:
            current_session, start_of_day = session, equity
        if profit_financed:
            base = config.base_risk_fraction * start_of_day
            financed = config.profit_reinvestment_fraction * max(equity - start_of_day, 0.0)
            risk_dollars = min(base + financed, config.maximum_risk_fraction * start_of_day)
        else:
            risk_dollars = config.base_risk_fraction * equity
        risk_fraction = risk_dollars / equity
        notional = min(config.maximum_leverage, risk_fraction / float(trade.stop_fraction))
        gross_return = float(trade.signed_price_return) * notional
        cost = 2.0 * one_way_cost_bps / 10_000.0 * notional
        net_return = gross_return - cost
        equity_before = equity
        equity *= 1.0 + net_return
        rows.append({
            "bar_minutes": trade.bar_minutes,
            "variant": "profit_financed" if profit_financed else "fixed_0.25",
            "one_way_cost_bps": one_way_cost_bps,
            "session_date": session,
            "entry_time": trade.entry_time,
            "setup": trade.setup,
            "net_return": net_return,
            "gross_return": gross_return,
            "execution_cost": cost,
            "net_r": net_return / (notional * float(trade.stop_fraction)),
            "risk_fraction_deployed": notional * float(trade.stop_fraction),
            "effective_leverage": notional,
            "equity_before": equity_before,
            "equity_after": equity,
        })
    return pd.DataFrame(rows)


def summarize_path(path: pd.DataFrame) -> dict[str, Any]:
    if path.empty:
        return {"trades": 0}
    dates = pd.to_datetime(path["session_date"])
    years = max((dates.max() - dates.min()).days / 365.25, 1.0 / 365.25)
    growth = np.cumprod(1.0 + path["net_return"].to_numpy(dtype=float))
    equity = np.r_[1.0, growth]
    finish = float(growth[-1])
    peaks = np.maximum.accumulate(equity)
    losses = path.loc[path["net_return"].lt(0.0), "net_return"]
    wins = path.loc[path["net_return"].gt(0.0), "net_return"]
    return {
        "trades": int(len(path)),
        "sessions": int(path["session_date"].nunique()),
        "win_rate": float(path["net_return"].gt(0.0).mean()),
        "average_net_r": float(path["net_r"].mean()),
        "profit_factor": float(wins.sum() / abs(losses.sum())) if losses.sum() < 0.0 else np.inf,
        "cumulative_net_return": finish - 1.0,
        "annualized_net_return": finish ** (1.0 / years) - 1.0 if finish > 0.0 else -1.0,
        "maximum_drawdown": float(np.min(equity / peaks - 1.0)),
        "average_risk_fraction": float(path["risk_fraction_deployed"].mean()),
        "average_effective_leverage": float(path["effective_leverage"].mean()),
    }


def scope_summary(path: pd.DataFrame) -> pd.DataFrame:
    work = path.copy()
    work["entry_time"] = pd.to_datetime(work["entry_time"], utc=True)
    scopes = {
        "all": work,
        "development_2024": work.loc[work["entry_time"] < HOLDOUT_START],
        "holdout_2025": work.loc[work["entry_time"] >= HOLDOUT_START],
    }
    records: list[dict[str, Any]] = []
    for scope, scoped in scopes.items():
        records.append({"scope": scope, "setup": "all"} | summarize_path(scoped))
        for setup, group in scoped.groupby("setup"):
            records.append({"scope": scope, "setup": setup} | summarize_path(group))
    return pd.DataFrame(records)


def bootstrap_sessions(path: pd.DataFrame, config: FabioProxyConfig) -> dict[str, Any]:
    returns = path.groupby("session_date")["net_return"].apply(
        lambda values: float(np.prod(1.0 + values.to_numpy()) - 1.0)
    ).to_numpy()
    if len(returns) == 0:
        return {"sessions": 0}
    rng = np.random.default_rng(config.bootstrap_seed)
    finals = np.empty(config.bootstrap_samples)
    for index in range(config.bootstrap_samples):
        finals[index] = np.prod(1.0 + rng.choice(returns, len(returns), replace=True)) - 1.0
    return {
        "sessions": int(len(returns)),
        "samples": config.bootstrap_samples,
        "return_p05": float(np.quantile(finals, 0.05)),
        "return_median": float(np.median(finals)),
        "return_p95": float(np.quantile(finals, 0.95)),
        "probability_positive": float(np.mean(finals > 0.0)),
    }


def simulate_mnq(
    trades: pd.DataFrame,
    config: FabioProxyConfig,
    *,
    starting_equity: float,
    profit_financed: bool,
) -> pd.DataFrame:
    equity = starting_equity
    start_of_day = equity
    current_session: str | None = None
    rows: list[dict[str, Any]] = []
    cost_per_contract = (
        config.mnq_round_turn_fees
        + config.mnq_round_turn_slippage_points * config.mnq_multiplier
    )
    for trade in trades.sort_values("entry_time").itertuples(index=False):
        session = str(trade.session_date)
        if session != current_session:
            current_session, start_of_day = session, equity
        if profit_financed:
            base = config.base_risk_fraction * start_of_day
            financed = config.profit_reinvestment_fraction * max(equity - start_of_day, 0.0)
            risk_dollars = min(base + financed, config.maximum_risk_fraction * start_of_day)
        else:
            risk_dollars = config.base_risk_fraction * equity
        stop_cost = float(trade.stop_distance_points) * config.mnq_multiplier + cost_per_contract
        risk_contracts = int(np.floor(risk_dollars / stop_cost))
        leverage_contracts = int(np.floor(
            config.maximum_leverage * equity / (float(trade.entry_price) * config.mnq_multiplier)
        ))
        contracts = max(0, min(risk_contracts, leverage_contracts))
        equity_before = equity
        if contracts:
            point_move = float(trade.signed_price_return) * float(trade.entry_price)
            net_pnl = contracts * (point_move * config.mnq_multiplier - cost_per_contract)
            equity += net_pnl
        else:
            net_pnl = 0.0
        deployed_risk = contracts * stop_cost / equity_before
        effective_leverage = (
            contracts * float(trade.entry_price) * config.mnq_multiplier / equity_before
        )
        net_return = net_pnl / equity_before
        rows.append({
            "bar_minutes": trade.bar_minutes,
            "variant": "profit_financed" if profit_financed else "fixed_0.25",
            "starting_equity": starting_equity,
            "session_date": session,
            "entry_time": trade.entry_time,
            "contracts": contracts,
            "executed": contracts > 0,
            "net_return": net_return,
            "net_r": net_return / deployed_risk if deployed_risk > 0.0 else np.nan,
            "risk_fraction_deployed": deployed_risk,
            "effective_leverage": effective_leverage,
            "net_pnl": net_pnl,
            "equity_before": equity_before,
            "equity_after": equity,
        })
    return pd.DataFrame(rows)


def competition_return_math(config: FabioProxyConfig) -> pd.DataFrame:
    targets = {"2024_Q1": 0.895, "2024_Q4": 2.183, "2025_Q1": 1.697}
    records: list[dict[str, Any]] = []
    for label, target in targets.items():
        for trades in (100, 300, 500, 1_000):
            per_trade = (1.0 + target) ** (1.0 / trades) - 1.0
            records.append({
                "competition_period": label,
                "target_return": target,
                "assumed_trades": trades,
                "required_constant_net_return_per_trade": per_trade,
                "required_average_net_r_at_0_25pct_risk": per_trade / config.base_risk_fraction,
            })
    return pd.DataFrame(records)


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    headers = list(frame.columns)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in frame.itertuples(index=False, name=None):
        values = [f"{value:.4f}" if isinstance(value, (float, np.floating)) else str(value) for value in row]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _report(
    summary: pd.DataFrame,
    cost: pd.DataFrame,
    bootstrap: pd.DataFrame,
    mnq: pd.DataFrame,
    funnel: pd.DataFrame,
    feasibility: pd.DataFrame,
    governance: dict[str, Any],
) -> str:
    totals = summary.loc[summary["setup"].eq("all")].copy()
    holdout = summary.loc[summary["scope"].eq("holdout_2025")].copy()
    orb_all = summary.loc[
        summary["scope"].eq("all") & summary["setup"].eq("opening_range_breakout")
    ].set_index("bar_minutes")
    cost_view = cost.loc[cost["setup"].isin(["all", "opening_range_breakout"])]
    bootstrap_view = bootstrap.loc[bootstrap["setup"].isin(["all", "opening_range_breakout"])]
    mnq_view = mnq.loc[mnq["setup"].isin(["all", "opening_range_breakout"])]
    return f"""# Fabio-inspired description: literal OHLCV proxy test

## What was tested

This is one frozen interpretation of the attached prose, **not Fabio Valentini's actual strategy**. It uses a causal 50-bar/24-row typical-price profile, candle-volume delta proxy, 2x-volume and 0.3-ATR absorption, three-bar accumulation, aggressive expansion, session VWAP, a 30-minute ORB, one-ATR stop, 2R target, 30-minute maximum hold, 0.25% base risk, and a three-loss daily cutoff.

Value-area and Triple-A signals are allowed throughout the regular session. ORB signals are allowed only during minutes 30–60. Signals enter at the next bar; same-bar stop/target ambiguity goes to the stop.

## Fixed-risk results at 0.50 bps per side

{_markdown_table(totals)}

The combined strategy fails at all three frequencies. The only positive branch is ORB-only: **{orb_all.loc[2, 'cumulative_net_return']:.2%}** on two-minute bars and **{orb_all.loc[5, 'cumulative_net_return']:.2%}** on five-minute bars over the full sample. Those are research leads, not Fabio-scale returns or independently selected winners.

## 2025 holdout by setup

{_markdown_table(holdout)}

## Signal funnel

{_markdown_table(funnel)}

## Cost sensitivity

{_markdown_table(cost_view)}

## Session bootstrap

{_markdown_table(bootstrap_view)}

## Discrete MNQ sizing

Assumption: ${governance['config']['mnq_round_turn_fees']:.2f} round-turn fees plus {governance['config']['mnq_round_turn_slippage_points']:.2f} index points of round-turn slippage per contract. These are scenarios, not a broker quote.

{_markdown_table(mnq_view)}

## Mathematics of the published competition returns

This table shows the constant average net R per trade required if every trade risked exactly 0.25%. Real paths are variable, and profit-financed risk changes the equation.

{_markdown_table(feasibility)}

## Why Fabio-scale returns are mathematically possible

- The public 0.25% figure is described as base risk, not necessarily the maximum risk after an early-session profit. Profit can finance later size.
- Public descriptions say he takes hundreds of trades per quarter and scales winning sequences toward 3R, 5R, and 6R outcomes. High frequency and positive skew can compound quickly.
- The quarterly competition currently permits a $2,500 minimum starting balance and low day-trading margins. A small return denominator plus futures leverage can create very large percentage returns, although Fabio's actual starting balance and leverage path are not public.
- For example, +218.3% over 500 equal-risk trades requires about +0.93R net per trade at fixed 0.25% risk. The tested five-minute ORB proxy produced only +0.058R per trade.
- Competition standings verify the account return, not that a public prose description recreates the execution. They do not disclose Fabio's complete ledger, maximum drawdown, contract path, or all accounts he controlled.

Public workflow description: https://www.chartacademy.com/instructors/fabio-valentini

Official standings and organizer disclaimer: https://www.worldcupchampionships.com/world-cup-trading-championship-standings

Quarterly contest account and margin information: https://www.worldcupchampionships.com/quarterly-futures

## Limitations and decision

- OHLCV cannot observe bid/ask delta, footprint imbalance, resting liquidity, absorption, queue position, or tape speed. The core "Aggression" input is therefore missing.
- The source instrument is unverified and {governance['data_quality']['close_not_on_nq_quarter_tick_share']:.1%} of closes are off the CME NQ quarter-point grid.
- The rules absent from the prose were fixed once, not optimized. Alternative definitions are different strategies.
- The three frequencies share the same 2025 holdout; choosing the best after viewing it is not independent validation.
- Live deployment is blocked pending identified NQ/MNQ tick data, bid/ask volume, broker-specific costs, and a new forward period.
"""


def build_fabio_description_backtest(
    project_root: str | Path | None = None,
    *,
    data_path: str | Path = DEFAULT_DATA,
    schedule_path: str | Path = DEFAULT_SCHEDULE,
    output_dir: str | Path = DEFAULT_OUTPUT,
    reuse_ledgers: bool = False,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)

    def resolved(value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else root / path

    data_file, schedule_file, output = resolved(data_path), resolved(schedule_path), resolved(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    config = FabioProxyConfig()
    raw, data_quality = load_nasdaq_source(data_file)
    schedule = load_schedule(schedule_file)

    signal_frames: list[pd.DataFrame] = []
    trade_frames: list[pd.DataFrame] = []
    diagnostic_frames: list[pd.DataFrame] = []
    blocked_by_frequency: dict[str, dict[str, Any]] = {}
    summary_frames: list[pd.DataFrame] = []
    cost_rows: list[dict[str, Any]] = []
    bootstrap_rows: list[dict[str, Any]] = []
    equity_paths: list[pd.DataFrame] = []
    mnq_rows: list[dict[str, Any]] = []
    mnq_paths: list[pd.DataFrame] = []

    for minutes in (1, 2, 5):
        signals_file = output / f"signals_{minutes}m.csv"
        trades_file = output / f"trades_{minutes}m.csv"
        if reuse_ledgers and signals_file.exists() and trades_file.exists():
            signals = pd.read_csv(signals_file)
            trades = pd.read_csv(trades_file)
            for column in ("signal_time", "session_close"):
                signals[column] = pd.to_datetime(signals[column], utc=True)
            for column in ("signal_time", "entry_time", "exit_time"):
                trades[column] = pd.to_datetime(trades[column], utc=True)
            diagnostics = pd.DataFrame()
            blocked = {
                "overlap": "not_recomputed_from_cached_ledgers",
                "daily_loss_stop": "not_recomputed_from_cached_ledgers",
                "unexecutable": "not_recomputed_from_cached_ledgers",
            }
        else:
            bars = resample_complete_bars(raw, minutes)
            signals, diagnostics = build_signals(bars, schedule, minutes, config)
            trades, blocked = run_trade_ledger(signals, bars, config)
            signals.to_csv(signals_file, index=False)
            trades.to_csv(trades_file, index=False)
        signal_frames.append(signals)
        trade_frames.append(trades)
        diagnostic_frames.append(diagnostics)
        blocked_by_frequency[str(minutes)] = blocked
        reference = account_path(
            trades, config, one_way_cost_bps=config.reference_one_way_cost_bps
        )
        reference_summary = scope_summary(reference)
        reference_summary.insert(0, "bar_minutes", minutes)
        summary_frames.append(reference_summary)
        equity_paths.append(reference)
        setup_subsets = {
            "all": trades,
            "opening_range_breakout": trades.loc[trades["setup"].eq("opening_range_breakout")],
            "value_area_bounce": trades.loc[trades["setup"].eq("value_area_bounce")],
        }
        for setup_name, setup_trades in setup_subsets.items():
            for cost_bps in config.cost_scenarios_bps:
                path = account_path(setup_trades, config, one_way_cost_bps=cost_bps)
                cost_rows.append({
                    "bar_minutes": minutes,
                    "setup": setup_name,
                    "one_way_cost_bps": cost_bps,
                } | summarize_path(path))
            for financed in (False, True):
                path = account_path(
                    setup_trades,
                    config,
                    one_way_cost_bps=config.reference_one_way_cost_bps,
                    profit_financed=financed,
                )
                if setup_name in {"all", "opening_range_breakout"}:
                    bootstrap_rows.append({
                        "bar_minutes": minutes,
                        "setup": setup_name,
                        "variant": "profit_financed" if financed else "fixed_0.25",
                    } | bootstrap_sessions(path, config))
                for account_size in config.account_sizes:
                    discrete = simulate_mnq(
                        setup_trades, config, starting_equity=account_size, profit_financed=financed
                    )
                    mnq_paths.append(discrete.assign(setup_scope=setup_name))
                    metrics = summarize_path(discrete)
                    mnq_rows.append({
                        "bar_minutes": minutes,
                        "setup": setup_name,
                        "variant": "profit_financed" if financed else "fixed_0.25",
                        "starting_equity": account_size,
                        "zero_contract_skips": int((~discrete["executed"]).sum()),
                    } | metrics)

    signals_all = pd.concat(signal_frames, ignore_index=True)
    trades_all = pd.concat(trade_frames, ignore_index=True)
    diagnostics_all = pd.concat(diagnostic_frames, ignore_index=True) if any(
        not frame.empty for frame in diagnostic_frames
    ) else pd.DataFrame()
    summary = pd.concat(summary_frames, ignore_index=True)
    cost = pd.DataFrame(cost_rows)
    bootstrap = pd.DataFrame(bootstrap_rows)
    mnq = pd.DataFrame(mnq_rows)
    feasibility = competition_return_math(config)
    funnel_records: list[dict[str, Any]] = []
    for minutes in (1, 2, 5):
        selected = signals_all.loc[signals_all["bar_minutes"].eq(minutes)]
        executed = trades_all.loc[trades_all["bar_minutes"].eq(minutes)]
        for setup in ("triple_a", "opening_range_breakout", "value_area_bounce"):
            funnel_records.append({
                "bar_minutes": minutes,
                "setup": setup,
                "raw_signals": int(selected["setup"].eq(setup).sum()),
                "executed_trades": int(executed["setup"].eq(setup).sum()),
            })
    funnel = pd.DataFrame(funnel_records)

    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "RESEARCH_ONLY_LIVE_DEPLOYMENT_BLOCKED",
        "description": "one frozen OHLCV interpretation of the attached strategy prose",
        "config": asdict(config),
        "data_quality": data_quality,
        "blocked_signals": blocked_by_frequency,
        "rule_choices_not_specified_by_source": [
            "Typical-price volume assignment and contiguous 70% value-area expansion.",
            "Fresh ORB cross restricted to minutes 30-60.",
            "Triple-A and value-area bounces allowed throughout RTH.",
            "Maximum 30-minute hold and no trailing stop.",
            "Same-bar stop/target ambiguity resolves to stop.",
            "Maximum 10x notional and no simultaneous positions.",
        ],
    }

    signals_all.to_csv(output / "signals.csv", index=False)
    trades_all.to_csv(output / "trades.csv", index=False)
    if not diagnostics_all.empty:
        diagnostics_all.to_csv(output / "session_diagnostics.csv", index=False)
    summary.to_csv(output / "summary.csv", index=False)
    cost.to_csv(output / "cost_sensitivity.csv", index=False)
    bootstrap.to_csv(output / "bootstrap.csv", index=False)
    funnel.to_csv(output / "signal_funnel.csv", index=False)
    mnq.to_csv(output / "mnq_sizing.csv", index=False)
    pd.concat(mnq_paths, ignore_index=True).to_csv(output / "mnq_paths.csv", index=False)
    pd.concat(equity_paths, ignore_index=True).to_csv(output / "equity_paths.csv", index=False)
    feasibility.to_csv(output / "competition_return_math.csv", index=False)
    (output / "governance.json").write_text(json.dumps(governance, indent=2), encoding="utf-8")
    report = _report(summary, cost, bootstrap, mnq, funnel, feasibility, governance)
    report_path = output / "report.md"
    report_path.write_text(report, encoding="utf-8")
    return {
        "report_path": report_path,
        "summary": summary,
        "cost_sensitivity": cost,
        "bootstrap": bootstrap,
        "mnq": mnq,
        "funnel": funnel,
        "governance": governance,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root")
    parser.add_argument("--data-path", default=str(DEFAULT_DATA))
    parser.add_argument("--schedule-path", default=str(DEFAULT_SCHEDULE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--reuse-ledgers", action="store_true")
    args = parser.parse_args(argv)
    result = build_fabio_description_backtest(
        project_root=args.project_root,
        data_path=args.data_path,
        schedule_path=args.schedule_path,
        output_dir=args.output_dir,
        reuse_ledgers=args.reuse_ledgers,
    )
    print(f"Report: {result['report_path']}")
    print(result["summary"].loc[result["summary"]["setup"].eq("all")].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
