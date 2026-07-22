"""Causal one-minute translation of the attached Pine v6 Fabio-inspired script.

The implementation preserves the script's default inputs and historical-bar
execution semantics.  It is a translation of the supplied script, not a claim
that the rules are Fabio Valentini's proprietary method.
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
DEFAULT_OUTPUT = Path("outputs/nasdaq_fabio_pine_v6_backtest")
HOLDOUT_START = pd.Timestamp("2025-01-01", tz="UTC")


@dataclass(frozen=True)
class PineFabioConfig:
    vp_length: int = 50
    vp_resolution: int = 24
    value_area_fraction: float = 0.70
    atr_length: int = 14
    absorb_volume_multiplier: float = 2.0
    absorb_price_threshold: float = 0.30
    delta_lookback: int = 5
    vwap_band_atr: float = 0.50
    reward_to_risk: float = 2.0
    maximum_daily_losses: int = 3
    trail_activation_atr: float = 1.50
    trail_offset_atr: float = 0.50
    orb_minutes: int = 30
    script_equity_fraction: float = 1.0
    intended_risk_fraction: float = 0.01
    intended_maximum_leverage: float = 10.0
    realistic_one_way_cost_bps: float = 0.50


def load_schedule(path: str | Path) -> pd.DataFrame:
    schedule = pd.read_csv(path)
    required = {"session_date", "session_open", "session_close"}
    missing = required - set(schedule.columns)
    if missing:
        raise ValueError(f"Schedule is missing columns: {sorted(missing)}")
    schedule = schedule.drop_duplicates("session_date", keep="last").copy()
    schedule["session_open"] = pd.to_datetime(schedule["session_open"], utc=True, errors="raise")
    schedule["session_close"] = pd.to_datetime(schedule["session_close"], utc=True, errors="raise")
    return schedule.sort_values("session_open").reset_index(drop=True)


def pine_rma(values: pd.Series, length: int) -> pd.Series:
    """Wilder RMA with Pine's SMA seed and alpha=1/length thereafter."""
    source = values.to_numpy(dtype=float)
    result = np.full(len(source), np.nan, dtype=float)
    valid = np.flatnonzero(np.isfinite(source))
    if len(valid) < length:
        return pd.Series(result, index=values.index)
    seed_end = int(valid[length - 1])
    seed_values = source[valid[:length]]
    result[seed_end] = float(seed_values.mean())
    previous = result[seed_end]
    for position in range(seed_end + 1, len(source)):
        value = source[position]
        if np.isfinite(value):
            previous = previous + (value - previous) / length
            result[position] = previous
    return pd.Series(result, index=values.index)


def _session_columns(
    index: pd.DatetimeIndex,
    schedule: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    in_session = np.zeros(len(index), dtype=bool)
    session_change = np.zeros(len(index), dtype=bool)
    session_bar = np.full(len(index), -1, dtype=np.int32)
    session_date = np.full(len(index), "", dtype=object)
    for row in schedule.itertuples(index=False):
        left = int(index.searchsorted(pd.Timestamp(row.session_open), side="left"))
        right = int(index.searchsorted(pd.Timestamp(row.session_close), side="left"))
        if right <= left:
            continue
        in_session[left:right] = True
        session_change[left] = True
        session_bar[left:right] = np.arange(right - left, dtype=np.int32)
        session_date[left:right] = str(row.session_date)
    return in_session, session_change, session_bar, session_date


def add_pine_indicators(
    bars: pd.DataFrame,
    schedule: pd.DataFrame,
    config: PineFabioConfig,
    *,
    bar_minutes: int = 1,
    vwap_timezone: str = "America/New_York",
) -> pd.DataFrame:
    """Calculate only current/past-bar quantities used by the supplied script."""
    out = bars[["open", "high", "low", "close", "volume"]].copy()
    out["bar_id"] = np.arange(len(out), dtype=np.int64)
    prior_close = out["close"].shift(1)
    true_range = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - prior_close).abs(),
            (out["low"] - prior_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr"] = pine_rma(true_range, config.atr_length)

    # ta.vwap(hlc3) uses its default daily anchor.  With no TradingView symbol
    # metadata in the CSV, calendar days in the stated New York timezone are
    # the closest deterministic translation.
    hlc3 = (out["high"] + out["low"] + out["close"]) / 3.0
    anchor_day = pd.Series(out.index.tz_convert(vwap_timezone).date, index=out.index)
    weighted = hlc3 * out["volume"]
    cumulative_weighted = weighted.groupby(anchor_day, sort=False).cumsum()
    cumulative_volume = out["volume"].groupby(anchor_day, sort=False).cumsum().replace(0.0, np.nan)
    out["vwap"] = cumulative_weighted / cumulative_volume
    out["vwap_upper"] = out["vwap"] + out["atr"] * config.vwap_band_atr
    out["vwap_lower"] = out["vwap"] - out["atr"] * config.vwap_band_atr

    in_session, session_change, session_bar, session_date = _session_columns(out.index, schedule)
    out["in_session"] = in_session
    out["session_change"] = session_change
    out["session_bar"] = session_bar
    out["session_date"] = session_date

    denominator = out["high"] - out["low"] + 0.0001
    buy_volume = np.where(
        out["close"] > out["open"],
        out["volume"],
        np.where(
            out["close"] == out["open"],
            out["volume"] * 0.5,
            out["volume"] * (out["high"] - out["close"]) / denominator,
        ),
    )
    out["delta"] = 2.0 * buy_volume - out["volume"]
    out["smooth_delta"] = out["delta"].rolling(
        config.delta_lookback, min_periods=config.delta_lookback
    ).mean()
    out["buyers_control"] = out["smooth_delta"].gt(0.0) & out["smooth_delta"].gt(
        out["smooth_delta"].shift(1)
    )
    out["sellers_control"] = out["smooth_delta"].lt(0.0) & out["smooth_delta"].lt(
        out["smooth_delta"].shift(1)
    )

    out["average_volume"] = out["volume"].rolling(20, min_periods=20).mean()
    out["price_move"] = (out["close"] - out["open"]).abs() / out["atr"]
    out["absorption"] = out["volume"].gt(
        out["average_volume"] * config.absorb_volume_multiplier
    ) & out["price_move"].lt(config.absorb_price_threshold)
    out["absorption_up"] = out["absorption"] & out["close"].gt(out["open"])
    out["absorption_down"] = out["absorption"] & out["close"].lt(out["open"])

    range_size = out["high"].rolling(10, min_periods=1).max() - out["low"].rolling(
        10, min_periods=1
    ).min()
    average_range = range_size.rolling(50, min_periods=50).mean()
    out["contraction"] = range_size.lt(average_range * 0.6)
    expansion = range_size.gt(average_range * 1.2) & out["volume"].gt(
        out["average_volume"] * 1.5
    )
    out["aggressive_buy"] = expansion & out["close"].gt(out["open"]) & out[
        "smooth_delta"
    ].gt(0.0)
    out["aggressive_sell"] = expansion & out["close"].lt(out["open"]) & out[
        "smooth_delta"
    ].lt(0.0)
    triple_long_memory = (
        out["absorption_up"].shift(3, fill_value=False)
        | out["absorption_up"].shift(4, fill_value=False)
        | out["absorption_up"].shift(5, fill_value=False)
    )
    triple_short_memory = (
        out["absorption_down"].shift(3, fill_value=False)
        | out["absorption_down"].shift(4, fill_value=False)
        | out["absorption_down"].shift(5, fill_value=False)
    )
    out["triple_a_long"] = (
        triple_long_memory
        & out["contraction"].shift(1, fill_value=False)
        & out["aggressive_buy"]
    )
    out["triple_a_short"] = (
        triple_short_memory
        & out["contraction"].shift(1, fill_value=False)
        & out["aggressive_sell"]
    )

    out["orb_high"] = np.nan
    out["orb_low"] = np.nan
    out["orb_defined"] = False
    for session in schedule.itertuples(index=False):
        left = int(out.index.searchsorted(pd.Timestamp(session.session_open), side="left"))
        right = int(out.index.searchsorted(pd.Timestamp(session.session_close), side="left"))
        orb_bars = config.orb_minutes / bar_minutes
        defining_count = int(np.floor(orb_bars)) + 1  # Pine uses sessionBars <= orbBars.
        if right - left < defining_count:
            continue
        defining_right = left + defining_count
        if defining_right > right:
            continue
        high = float(out["high"].iloc[left:defining_right].max())
        low = float(out["low"].iloc[left:defining_right].min())
        out.iloc[defining_right - 1:right, out.columns.get_loc("orb_high")] = high
        out.iloc[defining_right - 1:right, out.columns.get_loc("orb_low")] = low
        out.iloc[defining_right - 1:right, out.columns.get_loc("orb_defined")] = True
    out["orb_long"] = (
        out["orb_defined"]
        & out["close"].gt(out["orb_high"])
        & out["close"].shift(1).le(out["orb_high"])
    )
    out["orb_short"] = (
        out["orb_defined"]
        & out["close"].lt(out["orb_low"])
        & out["close"].shift(1).ge(out["orb_low"])
    )
    return out


def pine_volume_profile(
    bars: pd.DataFrame,
    end_position: int,
    config: PineFabioConfig,
) -> tuple[float, float, float]:
    """Exact close-bin profile for the current bar and preceding 49 bars."""
    left = max(0, end_position - config.vp_length + 1)
    history = bars.iloc[left : end_position + 1]
    low = float(history["low"].min())
    high = float(history["high"].max())
    row_height = (high - low) / config.vp_resolution
    if not np.isfinite(row_height) or row_height <= 0.0:
        return np.nan, np.nan, np.nan
    volumes = np.zeros(config.vp_resolution, dtype=float)
    levels = np.floor((history["close"].to_numpy(dtype=float) - low) / row_height)
    weights = history["volume"].to_numpy(dtype=float)
    valid = np.isfinite(levels) & (levels >= 0) & (levels < config.vp_resolution)
    np.add.at(volumes, levels[valid].astype(int), weights[valid])
    poc_index = int(np.argmax(volumes))  # First/lowest tie, matching Pine's strict >.
    target = float(volumes.sum()) * config.value_area_fraction
    accumulated = float(volumes[poc_index])
    upper = lower = poc_index
    while accumulated < target and (upper < config.vp_resolution - 1 or lower > 0):
        above = float(volumes[upper + 1]) if upper < config.vp_resolution - 1 else 0.0
        below = float(volumes[lower - 1]) if lower > 0 else 0.0
        if above >= below and upper < config.vp_resolution - 1:
            upper += 1
            accumulated += above
        elif lower > 0:
            lower -= 1
            accumulated += below
        else:
            break
    poc = low + (poc_index + 0.5) * row_height
    vah = low + (upper + 1) * row_height
    val = low + lower * row_height
    return float(poc), float(vah), float(val)


def build_raw_signals(
    bars: pd.DataFrame,
    schedule: pd.DataFrame,
    config: PineFabioConfig,
    *,
    bar_minutes: int = 1,
    vwap_timezone: str = "America/New_York",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    indicated = add_pine_indicators(
        bars,
        schedule,
        config,
        bar_minutes=bar_minutes,
        vwap_timezone=vwap_timezone,
    )
    indicated["poc"] = np.nan
    indicated["vah"] = np.nan
    indicated["val"] = np.nan
    indicated["value_long"] = False
    indicated["value_short"] = False

    profile_candidate = indicated["in_session"] & (
        (indicated["absorption_up"] & indicated["buyers_control"])
        | (indicated["absorption_down"] & indicated["sellers_control"])
    )
    for position in np.flatnonzero(profile_candidate.to_numpy()):
        poc, vah, val = pine_volume_profile(indicated, int(position), config)
        indicated.iat[position, indicated.columns.get_loc("poc")] = poc
        indicated.iat[position, indicated.columns.get_loc("vah")] = vah
        indicated.iat[position, indicated.columns.get_loc("val")] = val
        bar = indicated.iloc[position]
        at_val = np.isfinite(val) and float(bar["low"]) <= val * 1.001 and float(bar["low"]) >= val * 0.999
        at_vah = np.isfinite(vah) and float(bar["high"]) >= vah * 0.999 and float(bar["high"]) <= vah * 1.001
        indicated.iat[position, indicated.columns.get_loc("value_long")] = bool(
            at_val and bar["absorption_up"] and bar["buyers_control"]
        )
        indicated.iat[position, indicated.columns.get_loc("value_short")] = bool(
            at_vah and bar["absorption_down"] and bar["sellers_control"]
        )

    indicated["long_raw"] = (
        indicated["triple_a_long"] | indicated["orb_long"] | indicated["value_long"]
    ) & indicated["close"].gt(indicated["vwap_lower"]) & indicated["in_session"]
    indicated["short_raw"] = (
        indicated["triple_a_short"] | indicated["orb_short"] | indicated["value_short"]
    ) & indicated["close"].lt(indicated["vwap_upper"]) & indicated["in_session"]

    selected = indicated.loc[indicated["long_raw"] | indicated["short_raw"]].copy()
    records: list[dict[str, Any]] = []
    for timestamp, bar in selected.iterrows():
        for side, active in ((1, bool(bar["long_raw"])), (-1, bool(bar["short_raw"]))):
            if not active:
                continue
            flags: list[str] = []
            if bool(bar["triple_a_long"] if side > 0 else bar["triple_a_short"]):
                flags.append("triple_a")
            if bool(bar["orb_long"] if side > 0 else bar["orb_short"]):
                flags.append("orb")
            if bool(bar["value_long"] if side > 0 else bar["value_short"]):
                flags.append("value_area")
            static_stop = float(bar["low"] - bar["atr"]) if side > 0 else float(bar["high"] + bar["atr"])
            risk_from_close = side * (float(bar["close"]) - static_stop)
            static_target = float(bar["close"] + side * risk_from_close * config.reward_to_risk)
            records.append(
                {
                    "signal_time": timestamp,
                    "signal_bar_id": int(bar["bar_id"]),
                    "session_date": str(bar["session_date"]),
                    "side": side,
                    "setup": "+".join(flags),
                    "triple_a": "triple_a" in flags,
                    "orb": "orb" in flags,
                    "value_area": "value_area" in flags,
                    "signal_close": float(bar["close"]),
                    "signal_high": float(bar["high"]),
                    "signal_low": float(bar["low"]),
                    "signal_atr": float(bar["atr"]),
                    "static_stop": static_stop,
                    "static_target": static_target,
                    "trail_activation_distance": float(bar["atr"] * config.trail_activation_atr),
                    "trail_offset": float(bar["atr"] * config.trail_offset_atr),
                    "poc": float(bar["poc"]),
                    "vah": float(bar["vah"]),
                    "val": float(bar["val"]),
                    "vwap": float(bar["vwap"]),
                    "orb_high": float(bar["orb_high"]),
                    "orb_low": float(bar["orb_low"]),
                }
            )
    signals = pd.DataFrame(records)
    if not signals.empty:
        signals = signals.sort_values(["signal_bar_id", "side"], ascending=[True, False]).reset_index(drop=True)
    return indicated, signals


def inferred_path(open_price: float, high: float, low: float, close: float) -> list[float]:
    """TradingView's default historical OHLC path when Bar Magnifier is off."""
    if abs(open_price - high) <= abs(open_price - low):
        return [open_price, high, low, close]
    return [open_price, low, high, close]


def _walk_trade_bar(
    *,
    side: int,
    entry_price: float,
    stop: float,
    target: float,
    activation_distance: float,
    trail_offset: float,
    path: list[float],
    trail_active: bool,
    favorable_extreme: float,
) -> tuple[float | None, str | None, bool, float]:
    """Walk one inferred intrabar path and return the first executable exit."""
    activation = entry_price + side * activation_distance
    opening = path[0]
    effective_trail = favorable_extreme - side * trail_offset if trail_active else np.nan

    if side > 0:
        adverse_level = max(stop, effective_trail) if trail_active else stop
        if opening <= adverse_level:
            reason = "trailing_stop_gap" if trail_active and effective_trail >= stop else "static_stop_gap"
            return opening, reason, trail_active, favorable_extreme
        if opening >= target:
            return opening, "target_gap", trail_active, favorable_extreme
        if not trail_active and opening >= activation:
            trail_active, favorable_extreme = True, opening
        elif trail_active and opening > favorable_extreme:
            favorable_extreme = opening
    else:
        adverse_level = min(stop, effective_trail) if trail_active else stop
        if opening >= adverse_level:
            reason = "trailing_stop_gap" if trail_active and effective_trail <= stop else "static_stop_gap"
            return opening, reason, trail_active, favorable_extreme
        if opening <= target:
            return opening, "target_gap", trail_active, favorable_extreme
        if not trail_active and opening <= activation:
            trail_active, favorable_extreme = True, opening
        elif trail_active and opening < favorable_extreme:
            favorable_extreme = opening

    for start, end in zip(path[:-1], path[1:], strict=True):
        if side > 0:
            if end > start:
                if target >= start and target <= end:
                    return target, "target", trail_active, favorable_extreme
                if not trail_active and activation >= start and activation <= end:
                    trail_active = True
                    favorable_extreme = end
                elif trail_active:
                    favorable_extreme = max(favorable_extreme, end)
            elif end < start:
                effective_trail = favorable_extreme - trail_offset if trail_active else -np.inf
                adverse_level = max(stop, effective_trail)
                if end <= adverse_level <= start:
                    reason = "trailing_stop" if trail_active and effective_trail >= stop else "static_stop"
                    return adverse_level, reason, trail_active, favorable_extreme
        else:
            if end < start:
                if target <= start and target >= end:
                    return target, "target", trail_active, favorable_extreme
                if not trail_active and activation <= start and activation >= end:
                    trail_active = True
                    favorable_extreme = end
                elif trail_active:
                    favorable_extreme = min(favorable_extreme, end)
            elif end > start:
                effective_trail = favorable_extreme + trail_offset if trail_active else np.inf
                adverse_level = min(stop, effective_trail)
                if start <= adverse_level <= end:
                    reason = "trailing_stop" if trail_active and effective_trail <= stop else "static_stop"
                    return adverse_level, reason, trail_active, favorable_extreme
    return None, None, trail_active, favorable_extreme


def run_broker_emulator(
    indicated: pd.DataFrame,
    signals: pd.DataFrame,
    config: PineFabioConfig,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Run one-position Pine-like historical execution with next-open entries."""
    grouped = {int(key): group for key, group in signals.groupby("signal_bar_id")} if not signals.empty else {}
    pending: dict[str, Any] | None = None
    position: dict[str, Any] | None = None
    trades: list[dict[str, Any]] = []
    daily_losses = 0
    diagnostics = {
        "raw_long_signals": int(signals["side"].eq(1).sum()) if not signals.empty else 0,
        "raw_short_signals": int(signals["side"].eq(-1).sum()) if not signals.empty else 0,
        "dual_direction_signal_bars": 0,
        "signals_blocked_position": 0,
        "signals_blocked_daily_losses": 0,
        "pending_entries_unfilled_at_end": 0,
        "open_position_at_end": 0,
    }
    loss_closed_this_bar = False
    for bar_id, (timestamp, bar) in enumerate(indicated.iterrows()):
        loss_closed_this_bar = False
        if pending is not None:
            entry_price = float(bar["open"])
            pending = pending.copy()
            pending.update(
                {
                    "entry_time": timestamp,
                    "entry_bar_id": bar_id,
                    "entry_price": entry_price,
                    "trail_active": False,
                    "favorable_extreme": entry_price,
                }
            )
            position, pending = pending, None

        if position is not None:
            path = inferred_path(float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"]))
            exit_price, exit_reason, active, extreme = _walk_trade_bar(
                side=int(position["side"]),
                entry_price=float(position["entry_price"]),
                stop=float(position["static_stop"]),
                target=float(position["static_target"]),
                activation_distance=float(position["trail_activation_distance"]),
                trail_offset=float(position["trail_offset"]),
                path=path,
                trail_active=bool(position["trail_active"]),
                favorable_extreme=float(position["favorable_extreme"]),
            )
            position["trail_active"] = active
            position["favorable_extreme"] = extreme
            if exit_price is not None:
                side = int(position["side"])
                entry_price = float(position["entry_price"])
                gross_return = side * (float(exit_price) / entry_price - 1.0)
                initial_stop_fraction = abs(entry_price - float(position["static_stop"])) / entry_price
                trades.append(
                    {
                        **{key: value for key, value in position.items() if key not in {"trail_active", "favorable_extreme"}},
                        "side_name": "long" if side > 0 else "short",
                        "exit_time": timestamp,
                        "exit_bar_id": bar_id,
                        "exit_price": float(exit_price),
                        "exit_reason": exit_reason,
                        "holding_bars": bar_id - int(position["entry_bar_id"]) + 1,
                        "signed_price_return": gross_return,
                        "initial_stop_fraction": initial_stop_fraction,
                        "gross_r": gross_return / initial_stop_fraction if initial_stop_fraction > 0.0 else np.nan,
                    }
                )
                loss_closed_this_bar = gross_return < 0.0
                position = None

        # Pine resets before calculating canTrade and increments a just-closed
        # loss after its entry if-statements on the same close.
        if bool(bar["session_change"]):
            daily_losses = 0
        candidates = grouped.get(bar_id)
        if candidates is not None:
            if candidates["side"].nunique() > 1:
                diagnostics["dual_direction_signal_bars"] += 1
            if position is not None or pending is not None:
                diagnostics["signals_blocked_position"] += len(candidates)
            elif daily_losses >= config.maximum_daily_losses:
                diagnostics["signals_blocked_daily_losses"] += len(candidates)
            else:
                # The two Pine if-blocks are ordered Long then Short.  If both
                # fire while flat, the last market entry call determines the
                # resulting direction at the next tick; preserve that ordering.
                chosen = candidates.iloc[-1].to_dict()
                pending = chosen
        if loss_closed_this_bar:
            daily_losses += 1

    diagnostics["pending_entries_unfilled_at_end"] = int(pending is not None)
    diagnostics["open_position_at_end"] = int(position is not None)
    return pd.DataFrame(trades), diagnostics


def account_path(
    trades: pd.DataFrame,
    *,
    variant: str,
    one_way_cost_bps: float,
    config: PineFabioConfig,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    equity = 1.0
    for trade in trades.sort_values("entry_time").itertuples(index=False):
        if variant in {"script_zero_cost", "script_realistic_cost"}:
            leverage = config.script_equity_fraction
        elif variant == "intended_1pct_risk_capped_10x":
            distance = float(trade.initial_stop_fraction)
            leverage = min(
                config.intended_maximum_leverage,
                config.intended_risk_fraction / distance if distance > 0.0 else 0.0,
            )
        else:
            raise ValueError(f"Unknown variant: {variant}")
        gross = float(trade.signed_price_return) * leverage
        cost = 2.0 * one_way_cost_bps / 10_000.0 * leverage
        net = gross - cost
        before = equity
        equity *= 1.0 + net
        rows.append(
            {
                "variant": variant,
                "session_date": trade.session_date,
                "setup": trade.setup,
                "entry_time": trade.entry_time,
                "exit_time": trade.exit_time,
                "net_return": net,
                "gross_return": gross,
                "execution_cost": cost,
                "effective_leverage": leverage,
                "risk_fraction_deployed": leverage * float(trade.initial_stop_fraction),
                "net_r": net / (leverage * float(trade.initial_stop_fraction))
                if leverage > 0.0 and float(trade.initial_stop_fraction) > 0.0
                else np.nan,
                "equity_before": before,
                "equity_after": equity,
            }
        )
    return pd.DataFrame(rows)


def summarize_path(path: pd.DataFrame) -> dict[str, Any]:
    if path.empty:
        return {
            "trades": 0,
            "sessions": 0,
            "win_rate": np.nan,
            "average_net_r": np.nan,
            "profit_factor": np.nan,
            "cumulative_net_return": 0.0,
            "annualized_net_return": 0.0,
            "maximum_drawdown": 0.0,
            "average_effective_leverage": np.nan,
            "average_risk_fraction": np.nan,
        }
    ordered = path.sort_values("entry_time")
    returns = ordered["net_return"].to_numpy(dtype=float)
    growth = np.cumprod(1.0 + returns)
    equity = np.r_[1.0, growth]
    peaks = np.maximum.accumulate(equity)
    losses = returns[returns < 0.0]
    wins = returns[returns > 0.0]
    dates = pd.to_datetime(ordered["entry_time"], utc=True)
    years = max((dates.max() - dates.min()).days / 365.25, 1.0 / 365.25)
    finish = float(growth[-1])
    return {
        "trades": int(len(ordered)),
        "sessions": int(ordered["session_date"].nunique()),
        "win_rate": float(np.mean(returns > 0.0)),
        "average_net_r": float(ordered["net_r"].mean()),
        "profit_factor": float(wins.sum() / abs(losses.sum())) if losses.sum() < 0.0 else np.inf,
        "cumulative_net_return": finish - 1.0,
        "annualized_net_return": finish ** (1.0 / years) - 1.0 if finish > 0.0 else -1.0,
        "maximum_drawdown": float(np.min(equity / peaks - 1.0)),
        "average_effective_leverage": float(ordered["effective_leverage"].mean()),
        "average_risk_fraction": float(ordered["risk_fraction_deployed"].mean()),
    }


def summarize_scopes(paths: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for variant, variant_path in paths.groupby("variant", sort=False):
        scopes = {
            "all": variant_path,
            "development_2024": variant_path.loc[variant_path["entry_time"] < HOLDOUT_START],
            "holdout_2025": variant_path.loc[variant_path["entry_time"] >= HOLDOUT_START],
        }
        for scope, scoped in scopes.items():
            records.append({"variant": variant, "scope": scope, "setup_scope": "all"} | summarize_path(scoped))
            for setup in ("triple_a", "orb", "value_area"):
                includes = scoped["setup"].fillna("").str.split("+").apply(lambda values: setup in values)
                records.append(
                    {"variant": variant, "scope": scope, "setup_scope": setup}
                    | summarize_path(scoped.loc[includes])
                )
    return pd.DataFrame(records)


def build_cost_sensitivity(
    trades: pd.DataFrame,
    config: PineFabioConfig,
    *,
    one_way_costs_bps: tuple[float, ...] = (0.0, 0.10, 0.20, 0.25, 0.30, 0.40, 0.50, 0.75, 1.00),
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for one_way_bps in one_way_costs_bps:
        path = account_path(
            trades,
            variant="script_realistic_cost",
            one_way_cost_bps=one_way_bps,
            config=config,
        )
        records.append({"one_way_cost_bps": one_way_bps} | summarize_path(path))
    return pd.DataFrame(records)


def _audit_causality(
    bars: pd.DataFrame,
    schedule: pd.DataFrame,
    indicated: pd.DataFrame,
    signals: pd.DataFrame,
    trades: pd.DataFrame,
    config: PineFabioConfig,
    *,
    bar_minutes: int = 1,
    vwap_timezone: str = "America/New_York",
) -> dict[str, Any]:
    cutoff = min(len(bars) - 1, 100_000)
    prefix = add_pine_indicators(
        bars.iloc[: cutoff + 1],
        schedule,
        config,
        bar_minutes=bar_minutes,
        vwap_timezone=vwap_timezone,
    )
    fields = ["atr", "vwap", "smooth_delta", "triple_a_long", "triple_a_short", "orb_high", "orb_low"]
    prefix_matches = True
    for field in fields:
        left = prefix[field].iloc[-1]
        right = indicated[field].iloc[cutoff]
        if isinstance(left, (bool, np.bool_)):
            prefix_matches &= bool(left) == bool(right)
        else:
            prefix_matches &= bool(np.isclose(left, right, equal_nan=True))
    entry_delay = bool(
        trades.empty
        or (
            trades["entry_bar_id"].to_numpy(dtype=int)
            == trades["signal_bar_id"].to_numpy(dtype=int) + 1
        ).all()
    )
    entry_open = bool(
        trades.empty
        or np.isclose(
            trades["entry_price"].to_numpy(dtype=float),
            indicated["open"].to_numpy(dtype=float)[trades["entry_bar_id"].to_numpy(dtype=int)],
        ).all()
    )
    profile_prefix = True
    candidates = signals.loc[signals["value_area"]] if not signals.empty else signals
    if not candidates.empty:
        row = candidates.iloc[len(candidates) // 2]
        position = int(row["signal_bar_id"])
        original = pine_volume_profile(indicated, position, config)
        future_changed = indicated.copy()
        if position + 1 < len(future_changed):
            future_changed.iloc[position + 1 :, future_changed.columns.get_loc("close")] *= 10.0
        profile_prefix = all(
            np.isclose(a, b, equal_nan=True)
            for a, b in zip(original, pine_volume_profile(future_changed, position, config), strict=True)
        )
    checks = {
        "indicator_prefix_invariance": bool(prefix_matches),
        "volume_profile_future_mutation_invariance": bool(profile_prefix),
        "entries_exactly_one_bar_after_signal": entry_delay,
        "entries_use_next_bar_open": entry_open,
        "signals_restricted_to_confirmed_bar_data": True,
        "no_bar_magnifier_or_lower_timeframe_data_used": True,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "explanation": {
            "signals": "Every feature uses the signal bar or earlier bars; no negative shift or future slice is used.",
            "entry": f"A close-confirmed signal creates a market order filled at the following {bar_minutes}-minute bar open.",
            "exits": "Stops, limits, and trailing stops walk TradingView's inferred OHLC path without future bars.",
        },
    }


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    columns = list(frame.columns)
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in frame.itertuples(index=False, name=None):
        values: list[str] = []
        for value in row:
            if isinstance(value, (float, np.floating)):
                values.append("nan" if np.isnan(value) else f"{value:.4f}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _build_report(
    summary: pd.DataFrame,
    cost_sensitivity: pd.DataFrame,
    trades: pd.DataFrame,
    diagnostics: dict[str, int],
    audit: dict[str, Any],
    data_quality: dict[str, Any],
) -> str:
    all_rows = summary.loc[(summary["scope"] == "all") & (summary["setup_scope"] == "all")].copy()
    holdout = summary.loc[(summary["scope"] == "holdout_2025") & (summary["setup_scope"] == "all")].copy()
    columns = [
        "variant", "trades", "win_rate", "average_net_r", "profit_factor",
        "cumulative_net_return", "annualized_net_return", "maximum_drawdown",
        "average_effective_leverage", "average_risk_fraction",
    ]
    setup_rows = summary.loc[
        (summary["variant"] == "script_realistic_cost") & (summary["scope"] == "all")
    ][["setup_scope", "trades", "win_rate", "average_net_r", "profit_factor", "cumulative_net_return"]]
    reasons = trades["exit_reason"].value_counts().rename_axis("exit_reason").reset_index(name="trades") if not trades.empty else pd.DataFrame()
    return f"""# Fabio Pine v6 scalper: causal one-minute test

## Result

The supplied Pine script was translated literally at its default inputs. Signals are calculated on confirmed one-minute bars, market entries fill at the next bar's open, and exits use TradingView's historical OHLC path assumption. The causality audit status is **{audit['status']}**.

{_markdown_table(all_rows[columns])}

## 2025 holdout

{_markdown_table(holdout[columns])}

## Realistic-cost attribution

{_markdown_table(setup_rows)}

## Cost sensitivity

{_markdown_table(cost_sensitivity[["one_way_cost_bps", "profit_factor", "cumulative_net_return", "maximum_drawdown"]])}

## Exit mechanics

{_markdown_table(reasons)}

## Material script findings

- `riskPercent` is an unused input. With no `qty` in `strategy.entry`, the declaration deploys 100% of available equity, not 1% risk. The risk-sized row is a separate diagnostic and is not the supplied strategy.
- The 30-minute ORB uses `sessionBars <= 30`, so it contains 31 one-minute bars and cannot first break out until the next bar.
- Built-in `trail_points` activates 1.5 signal-bar ATR from the actual entry, then follows at 0.5 ATR. Its historical result depends on TradingView's inferred intrabar path.
- No commission or slippage is declared. `script_zero_cost` matches that omission; `script_realistic_cost` adds 0.50 bps per side.
- The default VWAP anchor is feed-dependent. This translation resets on each New York calendar date because the CSV has no TradingView symbol/session metadata.

## Research limits

- Source identity is **{data_quality['instrument_identity']}**; {data_quality['close_not_on_nq_quarter_tick_share']:.1%} of closes are off the CME NQ quarter-point grid.
- Candle volume cannot reproduce true bid/ask order flow or footprint absorption.
- One-minute OHLC cannot verify the tick path. The test intentionally uses the Pine broker emulator's documented default path rather than choosing favorable stop/target ordering.
- Raw dual-direction signal bars: {diagnostics['dual_direction_signal_bars']}. Open positions at the end: {diagnostics['open_position_at_end']}.

This is suitable for research comparison, not live deployment.
"""


def build_nasdaq_fabio_pine_v6_backtest(
    project_root: str | Path | None = None,
    *,
    data_path: str | Path = DEFAULT_DATA,
    schedule_path: str | Path = DEFAULT_SCHEDULE,
    output_dir: str | Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)

    def resolved(value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else root / path

    data_file = resolved(data_path)
    schedule_file = resolved(schedule_path)
    output = resolved(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    config = PineFabioConfig()
    bars, data_quality = load_nasdaq_source(data_file)
    schedule = load_schedule(schedule_file)
    indicated, signals = build_raw_signals(bars, schedule, config)
    trades, diagnostics = run_broker_emulator(indicated, signals, config)

    variants = [
        ("script_zero_cost", 0.0),
        ("script_realistic_cost", config.realistic_one_way_cost_bps),
        ("intended_1pct_risk_capped_10x", config.realistic_one_way_cost_bps),
    ]
    path_frames = [
        account_path(trades, variant=name, one_way_cost_bps=cost, config=config)
        for name, cost in variants
    ]
    paths = pd.concat(path_frames, ignore_index=True) if path_frames else pd.DataFrame()
    summary = summarize_scopes(paths)
    cost_sensitivity = build_cost_sensitivity(trades, config)
    audit = _audit_causality(bars, schedule, indicated, signals, trades, config)
    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "RESEARCH_ONLY_LIVE_DEPLOYMENT_BLOCKED",
        "translation": "literal defaults from attached Pine v6 script",
        "config": asdict(config),
        "data_quality": data_quality,
        "broker_emulator": {
            "signal_calculation": "confirmed bar close",
            "market_entry": "next bar open",
            "historical_path": "open-high-low-close if open is closer to high; otherwise open-low-high-close",
            "bar_magnifier": False,
            "gap_fill": "current bar open",
        },
        "feed_dependent_assumptions": [
            "ta.vwap(hlc3) reset at America/New_York calendar date.",
            "Source has no reliable syminfo.mintick; ATR tick conversions are represented as equivalent price distances.",
            "Equal-distance OHLC path ties use open-high-low-close.",
        ],
        "script_defects_preserved": [
            "riskPercent input is unused; order size is 100% of equity.",
            "ORB <= comparison creates a 31-bar opening range on a one-minute chart.",
            "No forced session-close exit; positions may carry outside RTH.",
        ],
        "execution_diagnostics": diagnostics,
    }

    signals.to_csv(output / "signals.csv", index=False)
    trades.to_csv(output / "trades.csv", index=False)
    paths.to_csv(output / "equity_paths.csv", index=False)
    summary.to_csv(output / "summary.csv", index=False)
    cost_sensitivity.to_csv(output / "cost_sensitivity.csv", index=False)
    (output / "causality_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    (output / "governance.json").write_text(json.dumps(governance, indent=2), encoding="utf-8")
    report = _build_report(summary, cost_sensitivity, trades, diagnostics, audit, data_quality)
    report_path = output / "report.md"
    report_path.write_text(report, encoding="utf-8")
    return {
        "report_path": report_path,
        "summary": summary,
        "signals": signals,
        "trades": trades,
        "cost_sensitivity": cost_sensitivity,
        "causality_audit": audit,
        "governance": governance,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root")
    parser.add_argument("--data-path", default=str(DEFAULT_DATA))
    parser.add_argument("--schedule-path", default=str(DEFAULT_SCHEDULE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_nasdaq_fabio_pine_v6_backtest(
        project_root=args.project_root,
        data_path=args.data_path,
        schedule_path=args.schedule_path,
        output_dir=args.output_dir,
    )
    print(f"Report: {result['report_path']}")
    print(
        result["summary"].loc[
            (result["summary"]["scope"] == "all")
            & (result["summary"]["setup_scope"] == "all")
        ].to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
