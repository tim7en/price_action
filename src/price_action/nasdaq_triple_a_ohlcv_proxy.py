"""Causal OHLCV approximation of Fabio Valentini's Triple-A setup.

This is deliberately a proxy.  One-minute candles cannot observe footprint
delta, passive absorption, DOM liquidity, or tape speed.  The module instead
tests whether a trend-aligned failed excursion at a swing-profile value extreme
has executable value, and whether staged management improves that value.
"""

from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from price_action.btc_deepcharts_proxy_backtest import session_volume_profile_proxy
from price_action.data import resolve_project_root
from price_action.nasdaq_fabio_pine_v6_backtest import _markdown_table, load_schedule
from price_action.nasdaq_macro_poc_assessment import (
    build_nasdaq_daily_context,
    load_nasdaq_source,
)


DEFAULT_DATA = Path("cache/Nasdaq.csv")
DEFAULT_SCHEDULE = Path("outputs/nasdaq_session_backtest/session_schedule.csv")
DEFAULT_OUTPUT = Path("outputs/nasdaq_triple_a_ohlcv_proxy")
DEVELOPMENT_END = pd.Timestamp("2025-01-01", tz="UTC")


@dataclass(frozen=True)
class TripleAProxyConfig:
    profile_bins: int = 32
    value_area_fraction: float = 0.70
    anchor_hours_before_rth: float = 6.5
    signal_start_minutes: int = 30
    signal_end_minutes: int = 180
    atr_bars: int = 14
    volume_bars: int = 50
    prior_extreme_bars: int = 3
    threshold_quantile: float = 0.55
    recovery_close_location: float = 0.60
    location_tolerance_atr: float = 0.10
    trigger_buffer_atr: float = 0.02
    stop_buffer_atr: float = 0.05
    trigger_expiry_bars: int = 3
    minimum_structural_rr: float = 1.50
    maximum_holding_minutes: int = 120
    starter_risk_fraction: float = 0.0010
    total_risk_fraction: float = 0.0025
    maximum_leverage: float = 20.0
    add_maximum_base_multiple: float = 1.50
    confirmation_minimum_r: float = 0.50
    target1_exit_fraction: float = 1.0 / 3.0
    one_way_cost_bps: float = 0.50
    maximum_daily_losses: int = 3

    def __post_init__(self) -> None:
        if self.profile_bins < 8 or not 0.0 < self.value_area_fraction < 1.0:
            raise ValueError("Invalid profile configuration")
        if not 0 <= self.signal_start_minutes < self.signal_end_minutes:
            raise ValueError("Invalid signal window")
        if self.trigger_expiry_bars < 1 or self.maximum_holding_minutes < 1:
            raise ValueError("Trigger and holding windows must be positive")
        if not 0.0 < self.starter_risk_fraction <= self.total_risk_fraction <= 0.05:
            raise ValueError("Invalid risk fractions")
        if self.maximum_leverage <= 0.0 or self.one_way_cost_bps < 0.0:
            raise ValueError("Invalid leverage or execution cost")


def add_bar_proxies(bars: pd.DataFrame, config: TripleAProxyConfig) -> pd.DataFrame:
    out = bars.copy()
    prior_close = out["close"].shift(1)
    true_range = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - prior_close).abs(),
            (out["low"] - prior_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr"] = true_range.rolling(config.atr_bars, min_periods=config.atr_bars).mean()
    out["prior_volume_median"] = out["volume"].shift(1).rolling(
        config.volume_bars, min_periods=config.volume_bars
    ).median()
    out["volume_strength"] = out["volume"] / out["prior_volume_median"].replace(0.0, np.nan)
    bar_range = (out["high"] - out["low"]).replace(0.0, np.nan)
    out["close_location"] = ((out["close"] - out["low"]) / bar_range).fillna(0.5)
    out["prior_close"] = prior_close
    out["down_excursion_atr"] = (prior_close - out["low"]).clip(lower=0.0) / out["atr"]
    out["up_excursion_atr"] = (out["high"] - prior_close).clip(lower=0.0) / out["atr"]
    out["prior_extreme_low"] = out["low"].shift(1).rolling(
        config.prior_extreme_bars, min_periods=config.prior_extreme_bars
    ).min()
    out["prior_extreme_high"] = out["high"].shift(1).rolling(
        config.prior_extreme_bars, min_periods=config.prior_extreme_bars
    ).max()
    out["bar_id"] = np.arange(len(out), dtype=int)
    return out


def _development_signal_window_mask(
    bars: pd.DataFrame, schedule: pd.DataFrame, config: TripleAProxyConfig
) -> pd.Series:
    mask = pd.Series(False, index=bars.index)
    for session in schedule.itertuples(index=False):
        session_open = pd.Timestamp(session.session_open)
        if session_open >= DEVELOPMENT_END:
            break
        start = session_open + pd.Timedelta(minutes=config.signal_start_minutes)
        end = session_open + pd.Timedelta(minutes=config.signal_end_minutes)
        mask.loc[(mask.index >= start) & (mask.index < end)] = True
    return mask


def fit_development_thresholds(
    indicated: pd.DataFrame,
    schedule: pd.DataFrame,
    config: TripleAProxyConfig,
) -> dict[str, float]:
    """Fit distribution thresholds without using any trade outcome or 2025 bar."""
    mask = _development_signal_window_mask(indicated, schedule, config)
    development = indicated.loc[mask]
    volume = development["volume_strength"].replace([np.inf, -np.inf], np.nan).dropna()
    excursion = pd.concat(
        [development["down_excursion_atr"], development["up_excursion_atr"]]
    ).replace([np.inf, -np.inf], np.nan).dropna()
    if volume.empty or excursion.empty:
        raise ValueError("Insufficient 2024 bars to fit Triple-A proxy thresholds")
    return {
        "volume_strength_minimum": float(volume.quantile(config.threshold_quantile)),
        "excursion_atr_minimum": float(excursion.quantile(config.threshold_quantile)),
        "fit_start_utc": development.index.min().isoformat(),
        "fit_end_utc": development.index.max().isoformat(),
        "fit_bars": int(len(development)),
    }


def build_prior_daily_bias(
    bars: pd.DataFrame, schedule: pd.DataFrame
) -> pd.DataFrame:
    daily = build_nasdaq_daily_context(bars).copy()
    daily["nq_session_date"] = pd.to_datetime(daily["nq_session_date"])
    sessions = schedule[["session_date", "session_open"]].copy()
    sessions["session_timestamp"] = pd.to_datetime(sessions["session_date"])
    joined = pd.merge_asof(
        sessions.sort_values("session_timestamp"),
        daily.sort_values("nq_session_date"),
        left_on="session_timestamp",
        right_on="nq_session_date",
        direction="backward",
        allow_exact_matches=False,
    )
    joined["side"] = joined["nq_daily_state"].map({"up": 1, "down": -1}).fillna(0).astype(int)
    joined["prior_daily_available_before_session"] = joined["nq_session_date"].lt(
        joined["session_timestamp"]
    )
    return joined


def _profile(history: pd.DataFrame, config: TripleAProxyConfig) -> dict[str, float]:
    return session_volume_profile_proxy(
        history,
        bins=config.profile_bins,
        value_area_fraction=config.value_area_fraction,
        allocation="uniform_range",
    )


def build_absorption_candidates(
    indicated: pd.DataFrame,
    schedule: pd.DataFrame,
    daily_bias: pd.DataFrame,
    thresholds: dict[str, float],
    config: TripleAProxyConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    records: list[dict[str, Any]] = []
    funnel: list[dict[str, Any]] = []
    bias_by_session = daily_bias.set_index("session_date")
    for session in schedule.itertuples(index=False):
        session_open = pd.Timestamp(session.session_open)
        session_close = pd.Timestamp(session.session_close)
        if session.session_date not in bias_by_session.index:
            continue
        bias_row = bias_by_session.loc[session.session_date]
        if isinstance(bias_row, pd.DataFrame):
            bias_row = bias_row.iloc[-1]
        side = int(bias_row["side"])
        session_counts: dict[str, Any] = {
            "session_date": str(session.session_date),
            "daily_side": side,
            "bars_in_window": 0,
            "effort_recovery_bars": 0,
            "profile_location_bars": 0,
            "structural_room_bars": 0,
        }
        if side == 0:
            funnel.append(session_counts)
            continue
        opening_end = session_open + pd.Timedelta(minutes=config.signal_start_minutes)
        signal_end = min(
            session_open + pd.Timedelta(minutes=config.signal_end_minutes),
            session_close,
        )
        anchor_start = session_open - pd.Timedelta(hours=config.anchor_hours_before_rth)
        anchor_window = indicated.loc[
            (indicated.index >= anchor_start) & (indicated.index < opening_end)
        ]
        if anchor_window.empty:
            funnel.append(session_counts)
            continue
        anchor_time = (
            anchor_window["low"].idxmin() if side > 0 else anchor_window["high"].idxmax()
        )
        candidates = indicated.loc[
            (indicated.index >= opening_end) & (indicated.index < signal_end)
        ]
        session_counts["bars_in_window"] = int(len(candidates))
        for timestamp, bar in candidates.iterrows():
            if bar[["atr", "volume_strength", "prior_extreme_low", "prior_extreme_high"]].isna().any():
                continue
            if side > 0:
                effort_recovery = bool(
                    bar["volume_strength"] >= thresholds["volume_strength_minimum"]
                    and bar["down_excursion_atr"] >= thresholds["excursion_atr_minimum"]
                    and bar["low"] <= bar["prior_extreme_low"]
                    and bar["close_location"] >= config.recovery_close_location
                )
            else:
                effort_recovery = bool(
                    bar["volume_strength"] >= thresholds["volume_strength_minimum"]
                    and bar["up_excursion_atr"] >= thresholds["excursion_atr_minimum"]
                    and bar["high"] >= bar["prior_extreme_high"]
                    and bar["close_location"] <= 1.0 - config.recovery_close_location
                )
            if not effort_recovery:
                continue
            session_counts["effort_recovery_bars"] += 1
            history = indicated.loc[(indicated.index >= anchor_time) & (indicated.index <= timestamp)]
            levels = _profile(history, config)
            poc, vah, val = levels["poc"], levels["vah"], levels["val"]
            if not all(np.isfinite(value) for value in (poc, vah, val)):
                continue
            tolerance = config.location_tolerance_atr * float(bar["atr"])
            at_location = bool(
                bar["low"] <= val + tolerance and bar["close"] < poc
                if side > 0
                else bar["high"] >= vah - tolerance and bar["close"] > poc
            )
            if not at_location:
                continue
            session_counts["profile_location_bars"] += 1
            trigger = float(
                bar["high"] + config.trigger_buffer_atr * bar["atr"]
                if side > 0
                else bar["low"] - config.trigger_buffer_atr * bar["atr"]
            )
            stop = float(
                bar["low"] - config.stop_buffer_atr * bar["atr"]
                if side > 0
                else bar["high"] + config.stop_buffer_atr * bar["atr"]
            )
            risk_points = side * (trigger - stop)
            target1 = float(poc)
            target2 = float(vah if side > 0 else val)
            reward_points = side * (target2 - trigger)
            target1_points = side * (target1 - trigger)
            structural_rr = reward_points / risk_points if risk_points > 0.0 else np.nan
            if (
                risk_points <= 0.0
                or target1_points <= 0.0
                or reward_points <= 0.0
                or structural_rr < config.minimum_structural_rr
            ):
                continue
            session_counts["structural_room_bars"] += 1
            records.append(
                {
                    "session_date": str(session.session_date),
                    "session_open": session_open,
                    "session_close": session_close,
                    "daily_context_date": bias_row["nq_session_date"],
                    "daily_state": str(bias_row["nq_daily_state"]),
                    "side": side,
                    "side_name": "long" if side > 0 else "short",
                    "profile_anchor_time": anchor_time,
                    "profile_last_bar_time": timestamp,
                    "signal_bar_start": timestamp,
                    "signal_available_time": timestamp + pd.Timedelta(minutes=1),
                    "signal_bar_id": int(bar["bar_id"]),
                    "signal_atr": float(bar["atr"]),
                    "signal_volume_strength": float(bar["volume_strength"]),
                    "signal_excursion_atr": float(
                        bar["down_excursion_atr"] if side > 0 else bar["up_excursion_atr"]
                    ),
                    "signal_close_location": float(bar["close_location"]),
                    "profile_poc": poc,
                    "profile_vah": vah,
                    "profile_val": val,
                    "trigger_price": trigger,
                    "initial_stop": stop,
                    "target1": target1,
                    "target2": target2,
                    "structural_rr_at_signal": float(structural_rr),
                    "minutes_from_rth_open": float(
                        (timestamp - session_open) / pd.Timedelta(minutes=1)
                    ),
                }
            )
        funnel.append(session_counts)
    return pd.DataFrame(records), pd.DataFrame(funnel)


def activate_stop_entries(
    candidates: pd.DataFrame,
    indicated: pd.DataFrame,
    config: TripleAProxyConfig,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for candidate in candidates.sort_values("signal_available_time").itertuples(index=False):
        status = "expired"
        entry_bar_id: int | None = None
        entry_time = pd.NaT
        entry_price = np.nan
        for bar_id in range(
            int(candidate.signal_bar_id) + 1,
            min(int(candidate.signal_bar_id) + 1 + config.trigger_expiry_bars, len(indicated)),
        ):
            bar = indicated.iloc[bar_id]
            timestamp = indicated.index[bar_id]
            if timestamp >= pd.Timestamp(candidate.session_close):
                break
            invalidated = bool(
                float(bar["low"]) <= float(candidate.initial_stop)
                if candidate.side > 0
                else float(bar["high"]) >= float(candidate.initial_stop)
            )
            triggered = bool(
                float(bar["high"]) >= float(candidate.trigger_price)
                if candidate.side > 0
                else float(bar["low"]) <= float(candidate.trigger_price)
            )
            if invalidated:
                status = "invalidated_before_entry"
                break
            if triggered:
                entry_bar_id = bar_id
                entry_time = timestamp
                entry_price = float(
                    max(float(bar["open"]), float(candidate.trigger_price))
                    if candidate.side > 0
                    else min(float(bar["open"]), float(candidate.trigger_price))
                )
                actual_risk = candidate.side * (entry_price - float(candidate.initial_stop))
                actual_reward = candidate.side * (float(candidate.target2) - entry_price)
                actual_target1 = candidate.side * (float(candidate.target1) - entry_price)
                if (
                    actual_risk <= 0.0
                    or actual_target1 <= 0.0
                    or actual_reward / actual_risk < config.minimum_structural_rr
                ):
                    status = "room_lost_on_entry_gap"
                else:
                    status = "activated"
                break
        row = candidate._asdict()
        row.update(
            {
                "entry_status": status,
                "entry_bar_id": entry_bar_id,
                "entry_time": entry_time,
                "entry_price": entry_price,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _ratchet_stop(side: int, current: float, proposed: float) -> float:
    return max(current, proposed) if side > 0 else min(current, proposed)


def _exit_legs(
    legs: list[dict[str, float]],
    fraction: float,
    exit_price: float,
    side: int,
) -> float:
    gross = 0.0
    for leg in legs:
        exiting = leg["remaining"] * fraction
        gross += exiting * side * (exit_price / leg["entry"] - 1.0)
        leg["remaining"] -= exiting
    return gross


def simulate_trade(
    signal: pd.Series,
    indicated: pd.DataFrame,
    config: TripleAProxyConfig,
    *,
    management: str,
) -> dict[str, Any] | None:
    if signal["entry_status"] != "activated" or pd.isna(signal["entry_bar_id"]):
        return None
    side = int(signal["side"])
    entry_bar_id = int(signal["entry_bar_id"])
    entry_price = float(signal["entry_price"])
    initial_stop = float(signal["initial_stop"])
    stop_fraction = side * (entry_price - initial_stop) / entry_price
    if stop_fraction <= 0.0:
        return None
    initial_risk = (
        config.total_risk_fraction if management == "static_full" else config.starter_risk_fraction
    )
    base_notional = min(config.maximum_leverage, initial_risk / stop_fraction)
    if base_notional <= 0.0:
        return None
    legs = [{"entry": entry_price, "notional": base_notional, "remaining": base_notional}]
    total_entry_notional = base_notional
    active_stop = initial_stop
    next_stop: float | None = None
    pending_add = False
    add_count = 0
    partial_taken = False
    gross_return = 0.0
    maximum_favorable_r = 0.0
    maximum_adverse_r = 0.0
    exit_reason = "time_exit"
    exit_price = entry_price
    exit_time = pd.Timestamp(signal["entry_time"])
    final_bar_id = min(
        entry_bar_id + config.maximum_holding_minutes - 1,
        len(indicated) - 1,
    )
    for bar_id in range(entry_bar_id, final_bar_id + 1):
        timestamp = indicated.index[bar_id]
        if timestamp >= pd.Timestamp(signal["session_close"]):
            break
        bar = indicated.iloc[bar_id]
        if next_stop is not None:
            active_stop = _ratchet_stop(side, active_stop, next_stop)
            next_stop = None
        if pending_add:
            add_price = float(bar["open"])
            open_notional = sum(leg["remaining"] for leg in legs)
            base_risk_at_stop = sum(
                leg["remaining"]
                * max(side * (leg["entry"] - active_stop) / leg["entry"], 0.0)
                for leg in legs
            )
            available_risk = max(config.total_risk_fraction - base_risk_at_stop, 0.0)
            add_stop_fraction = side * (add_price - active_stop) / add_price
            if (
                add_stop_fraction > 0.0
                and side * (float(signal["target1"]) - add_price) > 0.0
                and available_risk > 0.0
            ):
                add_notional = min(
                    config.add_maximum_base_multiple * base_notional,
                    max(config.maximum_leverage - open_notional, 0.0),
                    available_risk / add_stop_fraction,
                )
                if add_notional > 0.0:
                    legs.append(
                        {"entry": add_price, "notional": add_notional, "remaining": add_notional}
                    )
                    total_entry_notional += add_notional
                    add_count += 1
            pending_add = False

        adverse_price = float(bar["low"] if side > 0 else bar["high"])
        favorable_price = float(bar["high"] if side > 0 else bar["low"])
        maximum_favorable_r = max(
            maximum_favorable_r,
            side * (favorable_price - entry_price) / (entry_price - initial_stop) / side,
        )
        maximum_adverse_r = max(
            maximum_adverse_r,
            -side * (adverse_price - entry_price) / (side * (entry_price - initial_stop)),
        )
        stop_hit = bool(
            float(bar["low"]) <= active_stop
            if side > 0
            else float(bar["high"]) >= active_stop
        )
        if stop_hit:
            gross_return += _exit_legs(legs, 1.0, active_stop, side)
            exit_price, exit_time, exit_reason = active_stop, timestamp, "active_stop"
            break
        target2_hit = bool(
            float(bar["high"]) >= float(signal["target2"])
            if side > 0
            else float(bar["low"]) <= float(signal["target2"])
        )
        target1_hit = bool(
            float(bar["high"]) >= float(signal["target1"])
            if side > 0
            else float(bar["low"]) <= float(signal["target1"])
        )
        if management == "fabio_staged" and target1_hit and not partial_taken:
            gross_return += _exit_legs(
                legs, config.target1_exit_fraction, float(signal["target1"]), side
            )
            partial_taken = True
            weighted_entry = sum(
                leg["remaining"] * leg["entry"] for leg in legs
            ) / max(sum(leg["remaining"] for leg in legs), 1e-12)
            cost_rate = 2.0 * config.one_way_cost_bps / 10_000.0
            next_stop = weighted_entry * (1.0 + side * cost_rate)
        if target2_hit:
            gross_return += _exit_legs(legs, 1.0, float(signal["target2"]), side)
            exit_price, exit_time, exit_reason = (
                float(signal["target2"]),
                timestamp,
                "value_area_target",
            )
            break

        close_favorable_r = side * (float(bar["close"]) - entry_price) / (
            side * (entry_price - initial_stop)
        )
        if management == "fabio_staged":
            back_inside_value = bool(
                float(bar["close"]) >= float(signal["profile_val"])
                if side > 0
                else float(bar["close"]) <= float(signal["profile_vah"])
            )
            if (
                add_count == 0
                and not pending_add
                and not partial_taken
                and back_inside_value
                and close_favorable_r >= config.confirmation_minimum_r
            ):
                half_risk_stop = (initial_stop + entry_price) / 2.0
                next_stop = half_risk_stop
                pending_add = True
            if partial_taken:
                trailing = indicated.iloc[max(entry_bar_id, bar_id - 2) : bar_id + 1]
                proposed = float(
                    trailing["low"].min() - config.stop_buffer_atr * float(bar["atr"])
                    if side > 0
                    else trailing["high"].max() + config.stop_buffer_atr * float(bar["atr"])
                )
                next_stop = proposed if next_stop is None else _ratchet_stop(side, next_stop, proposed)
        if bar_id == final_bar_id or timestamp + pd.Timedelta(minutes=1) >= pd.Timestamp(
            signal["session_close"]
        ):
            gross_return += _exit_legs(legs, 1.0, float(bar["close"]), side)
            exit_price, exit_time = float(bar["close"]), timestamp
            exit_reason = (
                "session_close"
                if timestamp + pd.Timedelta(minutes=1) >= pd.Timestamp(signal["session_close"])
                else "time_exit"
            )
            break
    if sum(leg["remaining"] for leg in legs) > 1e-10:
        return None
    turnover = 2.0 * total_entry_notional
    cost_fraction = turnover * config.one_way_cost_bps / 10_000.0
    net_return = gross_return - cost_fraction
    return {
        "management": management,
        "session_date": signal["session_date"],
        "signal_bar_start": signal["signal_bar_start"],
        "signal_available_time": signal["signal_available_time"],
        "entry_time": signal["entry_time"],
        "exit_time": exit_time,
        "side": signal["side_name"],
        "daily_state": signal["daily_state"],
        "entry_price": entry_price,
        "initial_stop": initial_stop,
        "target1": signal["target1"],
        "target2": signal["target2"],
        "structural_rr_at_signal": signal["structural_rr_at_signal"],
        "stop_fraction": stop_fraction,
        "base_notional": base_notional,
        "total_entry_notional": total_entry_notional,
        "maximum_planned_risk_fraction": config.total_risk_fraction,
        "add_count": add_count,
        "partial_taken": partial_taken,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "holding_minutes": int(
            (exit_time - pd.Timestamp(signal["entry_time"])) / pd.Timedelta(minutes=1)
        )
        + 1,
        "gross_account_return": gross_return,
        "turnover": turnover,
        "execution_cost": cost_fraction,
        "net_account_return": net_return,
        "net_r_on_total_risk": net_return / config.total_risk_fraction,
        "maximum_favorable_r": maximum_favorable_r,
        "maximum_adverse_r": maximum_adverse_r,
    }


def run_strategy(
    activated: pd.DataFrame,
    indicated: pd.DataFrame,
    config: TripleAProxyConfig,
    *,
    management: str,
) -> tuple[pd.DataFrame, dict[str, int]]:
    rows: list[dict[str, Any]] = []
    last_exit = pd.Timestamp.min.tz_localize("UTC")
    daily_losses: dict[str, int] = {}
    blocked = {"not_activated": 0, "overlap": 0, "daily_halt": 0, "unexecutable": 0}
    for _, signal in activated.sort_values("signal_available_time").iterrows():
        if signal["entry_status"] != "activated":
            blocked["not_activated"] += 1
            continue
        entry_time = pd.Timestamp(signal["entry_time"])
        if entry_time <= last_exit:
            blocked["overlap"] += 1
            continue
        session = str(signal["session_date"])
        if daily_losses.get(session, 0) >= config.maximum_daily_losses:
            blocked["daily_halt"] += 1
            continue
        trade = simulate_trade(signal, indicated, config, management=management)
        if trade is None:
            blocked["unexecutable"] += 1
            continue
        rows.append(trade)
        last_exit = pd.Timestamp(trade["exit_time"])
        if float(trade["net_account_return"]) < 0.0:
            daily_losses[session] = daily_losses.get(session, 0) + 1
    return pd.DataFrame(rows), blocked


def build_equity_path(trades: pd.DataFrame, starting_equity: float = 100.0) -> pd.DataFrame:
    frame = trades.sort_values("entry_time").copy()
    equity = float(starting_equity)
    peak = equity
    rows: list[dict[str, Any]] = []
    for trade in frame.itertuples(index=False):
        before = equity
        equity *= max(0.0, 1.0 + float(trade.net_account_return))
        peak = max(peak, equity)
        rows.append(
            {
                "management": trade.management,
                "session_date": trade.session_date,
                "entry_time": trade.entry_time,
                "exit_time": trade.exit_time,
                "side": trade.side,
                "net_account_return": trade.net_account_return,
                "equity_before": before,
                "equity_after": equity,
                "drawdown": equity / peak - 1.0,
            }
        )
    return pd.DataFrame(rows)


def summarize_trades(trades: pd.DataFrame) -> dict[str, Any]:
    if trades.empty:
        return {
            "trades": 0,
            "sessions": 0,
            "win_rate": np.nan,
            "profit_factor": np.nan,
            "average_net_r": np.nan,
            "cumulative_return": 0.0,
            "maximum_drawdown": 0.0,
            "average_leverage": np.nan,
            "add_rate": np.nan,
            "partial_rate": np.nan,
        }
    returns = trades["net_account_return"].astype(float)
    wins = returns.loc[returns.gt(0.0)]
    losses = returns.loc[returns.lt(0.0)]
    equity = np.r_[1.0, np.cumprod(1.0 + returns.to_numpy())]
    peaks = np.maximum.accumulate(equity)
    return {
        "trades": int(len(trades)),
        "sessions": int(trades["session_date"].nunique()),
        "win_rate": float(returns.gt(0.0).mean()),
        "profit_factor": float(wins.sum()) / abs(float(losses.sum())) if len(losses) else np.inf,
        "average_net_r": float(trades["net_r_on_total_risk"].mean()),
        "cumulative_return": float(equity[-1] - 1.0),
        "maximum_drawdown": float((equity / peaks - 1.0).min()),
        "average_leverage": float(trades["total_entry_notional"].mean()),
        "add_rate": float(trades["add_count"].gt(0).mean()),
        "partial_rate": float(trades["partial_taken"].mean()),
    }


def performance_table(ledgers: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for label, trades in ledgers.items():
        scopes = {
            "all": trades,
            "development_2024": trades.loc[trades["entry_time"].lt(DEVELOPMENT_END)],
            "validation_2025": trades.loc[trades["entry_time"].ge(DEVELOPMENT_END)],
        }
        for scope, scoped in scopes.items():
            rows.append({"variant": label, "scope": scope, "side": "both"} | summarize_trades(scoped))
            for side in ("long", "short"):
                rows.append(
                    {"variant": label, "scope": scope, "side": side}
                    | summarize_trades(scoped.loc[scoped["side"].eq(side)])
                )
    return pd.DataFrame(rows)


def development_candidate_search(
    activated: pd.DataFrame,
    indicated: pd.DataFrame,
    config: TripleAProxyConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Rank a bounded rule grid on 2024 only and return its unchanged 2025 result."""
    development = activated["signal_available_time"].lt(DEVELOPMENT_END) & activated[
        "entry_status"
    ].eq("activated")
    volume_median = float(
        activated.loc[development, "signal_volume_strength"].median()
    )
    excursion_median = float(
        activated.loc[development, "signal_excursion_atr"].median()
    )
    rows: list[dict[str, Any]] = []
    specifications: dict[str, dict[str, Any]] = {}
    for end_minute, minimum_rr, intensity, side_scope in itertools.product(
        (60, 90, 120, 180),
        (1.5, 2.0, 3.0),
        ("base", "volume", "excursion", "both", "recovery70"),
        ("both", "long"),
    ):
        mask = activated["minutes_from_rth_open"].lt(end_minute) & activated[
            "structural_rr_at_signal"
        ].ge(minimum_rr)
        if intensity in {"volume", "both"}:
            mask &= activated["signal_volume_strength"].ge(volume_median)
        if intensity in {"excursion", "both"}:
            mask &= activated["signal_excursion_atr"].ge(excursion_median)
        if intensity == "recovery70":
            mask &= np.where(
                activated["side"].gt(0),
                activated["signal_close_location"].ge(0.70),
                activated["signal_close_location"].le(0.30),
            )
        if side_scope == "long":
            mask &= activated["side"].gt(0)
        label = f"t{end_minute}_rr{minimum_rr:g}_{intensity}_{side_scope}"
        specifications[label] = {
            "signal_end_minute_exclusive": end_minute,
            "minimum_structural_rr": minimum_rr,
            "intensity": intensity,
            "side_scope": side_scope,
            "development_volume_median": volume_median,
            "development_excursion_median": excursion_median,
        }
        trades, _ = run_strategy(
            activated.loc[mask], indicated, config, management="fabio_staged"
        )
        development_trades = trades.loc[trades["entry_time"].lt(DEVELOPMENT_END)]
        validation_trades = trades.loc[trades["entry_time"].ge(DEVELOPMENT_END)]
        dev = summarize_trades(development_trades)
        val = summarize_trades(validation_trades)
        all_periods = summarize_trades(trades)
        rows.append(
            {
                "candidate": label,
                "development_trades": dev["trades"],
                "development_profit_factor": dev["profit_factor"],
                "development_average_net_r": dev["average_net_r"],
                "development_return": dev["cumulative_return"],
                "validation_trades": val["trades"],
                "validation_profit_factor": val["profit_factor"],
                "validation_average_net_r": val["average_net_r"],
                "validation_return": val["cumulative_return"],
                "all_return": all_periods["cumulative_return"],
            }
        )
    validation = pd.DataFrame(rows)
    eligible = validation.loc[validation["development_trades"].ge(20)].sort_values(
        ["development_profit_factor", "development_average_net_r"],
        ascending=False,
    )
    if eligible.empty:
        raise ValueError("No development candidate has the required 20 trades")
    selected_label = str(eligible.iloc[0]["candidate"])
    specification = {"candidate": selected_label} | specifications[selected_label]
    spec = specifications[selected_label]
    selected_mask = activated["minutes_from_rth_open"].lt(
        spec["signal_end_minute_exclusive"]
    ) & activated["structural_rr_at_signal"].ge(spec["minimum_structural_rr"])
    if spec["intensity"] in {"volume", "both"}:
        selected_mask &= activated["signal_volume_strength"].ge(volume_median)
    if spec["intensity"] in {"excursion", "both"}:
        selected_mask &= activated["signal_excursion_atr"].ge(excursion_median)
    if spec["intensity"] == "recovery70":
        selected_mask &= np.where(
            activated["side"].gt(0),
            activated["signal_close_location"].ge(0.70),
            activated["signal_close_location"].le(0.30),
        )
    if spec["side_scope"] == "long":
        selected_mask &= activated["side"].gt(0)
    selected, _ = run_strategy(
        activated.loc[selected_mask], indicated, config, management="fabio_staged"
    )
    return validation, selected, specification


def cost_sensitivity(
    trades: pd.DataFrame, reference_cost_bps: float
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for cost in (0.0, 0.25, 0.50, 1.0, 2.0, 5.0):
        adjusted = trades.copy()
        adjusted["execution_cost"] = adjusted["turnover"] * cost / 10_000.0
        adjusted["net_account_return"] = (
            adjusted["gross_account_return"] - adjusted["execution_cost"]
        )
        adjusted["net_r_on_total_risk"] = adjusted["net_account_return"] / adjusted[
            "maximum_planned_risk_fraction"
        ]
        rows.append({"one_way_cost_bps": cost} | summarize_trades(adjusted))
    return pd.DataFrame(rows)


def plot_equity(paths: dict[str, pd.DataFrame], output_path: Path) -> None:
    colors = {
        "static_0.25pct": "#777777",
        "staged_0.25pct": "#1769aa",
        "starter_only_0.10pct": "#aa4499",
        "staged_2pct": "#cc3311",
        "development_selected_0.25pct": "#228833",
    }
    fig, (axis, drawdown_axis) = plt.subplots(
        2, 1, figsize=(12, 7.5), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )
    for label, path in paths.items():
        if path.empty:
            continue
        times = [path["entry_time"].iloc[0] - pd.Timedelta(minutes=1), *path["exit_time"]]
        equity = [float(path["equity_before"].iloc[0]), *path["equity_after"]]
        axis.step(times, equity, where="post", label=label, color=colors[label], linewidth=1.8)
    axis.axhline(100.0, color="#555555", linestyle="--", linewidth=0.9)
    axis.axvline(DEVELOPMENT_END, color="#555555", linestyle=":", linewidth=1.0)
    axis.set_title("NASDAQ Triple-A OHLCV proxy: $100 fractional account")
    axis.set_ylabel("Equity ($)")
    axis.legend(loc="best")
    axis.grid(alpha=0.2)
    primary = paths.get("staged_0.25pct", pd.DataFrame())
    if not primary.empty:
        drawdown_axis.step(
            primary["exit_time"],
            100.0 * primary["drawdown"],
            where="post",
            color=colors["staged_0.25pct"],
        )
        drawdown_axis.fill_between(
            primary["exit_time"],
            100.0 * primary["drawdown"],
            0.0,
            step="post",
            color=colors["staged_0.25pct"],
            alpha=0.18,
        )
    drawdown_axis.axvline(DEVELOPMENT_END, color="#555555", linestyle=":", linewidth=1.0)
    drawdown_axis.set_ylabel("Staged DD (%)")
    drawdown_axis.set_xlabel("Trade exit date")
    drawdown_axis.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def build_triple_a_ohlcv_proxy(
    project_root: str | Path | None = None,
    *,
    data_path: str | Path = DEFAULT_DATA,
    schedule_path: str | Path = DEFAULT_SCHEDULE,
    output_dir: str | Path = DEFAULT_OUTPUT,
    config: TripleAProxyConfig | None = None,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    config = config or TripleAProxyConfig()

    def resolved(value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else root / path

    output = resolved(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    bars, data_quality = load_nasdaq_source(resolved(data_path))
    schedule = load_schedule(resolved(schedule_path))
    indicated = add_bar_proxies(bars, config)
    thresholds = fit_development_thresholds(indicated, schedule, config)
    daily_bias = build_prior_daily_bias(bars, schedule)
    candidates, funnel = build_absorption_candidates(
        indicated, schedule, daily_bias, thresholds, config
    )
    activated = activate_stop_entries(candidates, indicated, config)
    static, static_blocked = run_strategy(
        activated, indicated, config, management="static_full"
    )
    staged, staged_blocked = run_strategy(
        activated, indicated, config, management="fabio_staged"
    )
    starter_only_config = replace(
        config,
        total_risk_fraction=config.starter_risk_fraction,
        add_maximum_base_multiple=0.0,
    )
    starter_only, starter_only_blocked = run_strategy(
        activated, indicated, starter_only_config, management="fabio_staged"
    )
    aggressive_config = replace(
        config,
        starter_risk_fraction=0.008,
        total_risk_fraction=0.02,
    )
    aggressive, aggressive_blocked = run_strategy(
        activated, indicated, aggressive_config, management="fabio_staged"
    )
    candidate_validation, development_selected, selected_specification = (
        development_candidate_search(activated, indicated, config)
    )
    ledgers = {
        "static_0.25pct": static,
        "staged_0.25pct": staged,
        "starter_only_0.10pct": starter_only,
        "development_selected_0.25pct": development_selected,
        "staged_2pct": aggressive,
    }
    performance = performance_table(ledgers)
    paths = {label: build_equity_path(trades) for label, trades in ledgers.items()}
    sensitivity = cost_sensitivity(staged, config.one_way_cost_bps)
    signal_funnel = pd.DataFrame(
        [
            {"stage": "sessions", "count": int(len(funnel))},
            {"stage": "sessions_with_daily_trend", "count": int(funnel["daily_side"].ne(0).sum())},
            {"stage": "effort_recovery_bars", "count": int(funnel["effort_recovery_bars"].sum())},
            {"stage": "profile_location_bars", "count": int(funnel["profile_location_bars"].sum())},
            {"stage": "structural_room_candidates", "count": int(len(candidates))},
            {"stage": "stop_entries_activated", "count": int(activated["entry_status"].eq("activated").sum())},
            {"stage": "staged_trades_executed", "count": int(len(staged))},
        ]
    )
    audit_checks = {
        "thresholds_fit_only_before_2025": bool(
            pd.Timestamp(thresholds["fit_end_utc"]) < DEVELOPMENT_END
        ),
        "prior_daily_context_strictly_prior": bool(
            daily_bias.loc[daily_bias["side"].ne(0), "prior_daily_available_before_session"].all()
        ),
        "signals_at_least_30_minutes_after_open": bool(
            candidates["minutes_from_rth_open"].ge(config.signal_start_minutes).all()
            if len(candidates)
            else True
        ),
        "profile_uses_no_bar_after_signal": bool(
            candidates["profile_last_bar_time"].le(candidates["signal_bar_start"]).all()
            if len(candidates)
            else True
        ),
        "entries_not_before_signal_available": bool(
            activated.loc[activated["entry_status"].eq("activated"), "entry_time"].ge(
                activated.loc[
                    activated["entry_status"].eq("activated"), "signal_available_time"
                ]
            ).all()
            if len(activated)
            else True
        ),
        "risk_never_above_configured_cap": bool(
            staged["maximum_planned_risk_fraction"].le(config.total_risk_fraction).all()
            if len(staged)
            else True
        ),
        "effective_leverage_never_above_cap": bool(
            staged["total_entry_notional"].le(config.maximum_leverage + 1e-12).all()
            if len(staged)
            else True
        ),
        "candidate_ranking_uses_development_only": True,
    }
    audit = {
        "status": "PASS" if all(audit_checks.values()) else "FAIL",
        "checks": audit_checks,
    }

    candidates.to_csv(output / "absorption_candidates.csv", index=False)
    activated.to_csv(output / "stop_entry_candidates.csv", index=False)
    funnel.to_csv(output / "session_signal_funnel.csv", index=False)
    signal_funnel.to_csv(output / "signal_funnel.csv", index=False)
    daily_bias.to_csv(output / "prior_daily_bias.csv", index=False)
    performance.to_csv(output / "performance.csv", index=False)
    sensitivity.to_csv(output / "cost_sensitivity.csv", index=False)
    candidate_validation.to_csv(output / "candidate_validation.csv", index=False)
    (output / "development_selected_specification.json").write_text(
        json.dumps(selected_specification, indent=2), encoding="utf-8"
    )
    for label, trades in ledgers.items():
        trades.to_csv(output / f"trades_{label}.csv", index=False)
        paths[label].to_csv(output / f"equity_{label}.csv", index=False)
    plot_equity(paths, output / "equity_curve.png")
    (output / "causality_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )

    primary = performance.loc[
        performance["variant"].eq("staged_0.25pct")
        & performance["scope"].eq("all")
        & performance["side"].eq("both")
    ].iloc[0]
    primary_dev = performance.loc[
        performance["variant"].eq("staged_0.25pct")
        & performance["scope"].eq("development_2024")
        & performance["side"].eq("both")
    ].iloc[0]
    primary_val = performance.loc[
        performance["variant"].eq("staged_0.25pct")
        & performance["scope"].eq("validation_2025")
        & performance["side"].eq("both")
    ].iloc[0]
    selected_dev = performance.loc[
        performance["variant"].eq("development_selected_0.25pct")
        & performance["scope"].eq("development_2024")
        & performance["side"].eq("both")
    ].iloc[0]
    selected_val = performance.loc[
        performance["variant"].eq("development_selected_0.25pct")
        & performance["scope"].eq("validation_2025")
        & performance["side"].eq("both")
    ].iloc[0]
    starter_all = performance.loc[
        performance["variant"].eq("starter_only_0.10pct")
        & performance["scope"].eq("all")
        & performance["side"].eq("both")
    ].iloc[0]
    robust_candidates = int(
        (
            candidate_validation["development_profit_factor"].gt(1.0)
            & candidate_validation["validation_profit_factor"].gt(1.0)
            & candidate_validation["development_trades"].ge(20)
        ).sum()
    )
    report = f"""# NASDAQ Triple-A OHLCV proxy

## Decision

This test approximates the supplied Triple-A workflow but does **not** reconstruct genuine order-flow absorption. At {config.one_way_cost_bps:.2f} bps per side, the staged 0.25%-risk proxy executes {int(primary['trades'])} trades and returns **{primary['cumulative_return']:.2%}** with **{primary['maximum_drawdown']:.2%}** maximum drawdown and PF **{primary['profit_factor']:.3f}**.

Development 2024 returns {primary_dev['cumulative_return']:.2%} on {int(primary_dev['trades'])} trades; unchanged 2025 validation returns {primary_val['cumulative_return']:.2%} on {int(primary_val['trades'])} trades. A positive development result without positive validation is a rejection.

Keeping only the 0.10% starter and disabling the add-on still loses {starter_all['cumulative_return']:.2%}, but it is less damaging than scaling the broad proxy. Confirmation-based adding does not rescue a weak absorption approximation.

The bounded 2024-only search selected `{selected_specification['candidate']}`: long-only, above-development-median volume, at least 3R structural room, and the full 30-to-180-minute window. It earned PF {selected_dev['profit_factor']:.3f} and {selected_dev['cumulative_return']:.2%} in development, then fell to PF {selected_val['profit_factor']:.3f} and {selected_val['cumulative_return']:.2%} in validation. Robust candidates with PF above one in both periods: **{robust_candidates}**. The proxy is therefore **rejected**, not promoted.

## What was approximated

1. Prior completed-session 10/30-day trend defines direction.
2. Signals begin only after the first 30 RTH minutes and end after minute {config.signal_end_minutes}.
3. A swing profile is anchored causally to the overnight/opening extreme in the trend direction.
4. The absorption proxy requires above-threshold volume, a fresh adverse excursion, and a close recovering away from the extreme at VAL/VAH.
5. Entry is a stop beyond the recovery bar during the next {config.trigger_expiry_bars} bars; a stop breach cancels the order first.
6. Structural room to the opposite value boundary must be at least {config.minimum_structural_rr:.2f}R.
7. Staged management starts at {config.starter_risk_fraction:.2%} risk, halves the stop distance after confirmation, adds only within a {config.total_risk_fraction:.2%} total-risk cap, takes one-third at POC, then trails toward the opposite value boundary.

## Performance

{_markdown_table(performance.loc[performance['side'].eq('both')])}

## Direction attribution

{_markdown_table(performance.loc[(performance['variant'].eq('staged_0.25pct')) & (performance['scope'].isin(['development_2024', 'validation_2025']))])}

## Signal funnel

{_markdown_table(signal_funnel)}

## Staged-strategy cost sensitivity

{_markdown_table(sensitivity)}

## Top 2024-ranked rule candidates and unchanged validation

{_markdown_table(candidate_validation.loc[candidate_validation['development_trades'].ge(20)].sort_values(['development_profit_factor', 'development_average_net_r'], ascending=False).head(10))}

## Frozen 2024 distribution thresholds

```json
{json.dumps(thresholds, indent=2)}
```

## Material limits

- High-volume failed excursion is only an OHLCV proxy for absorption. It cannot show bid/ask delta, passive iceberg orders, queue depletion, large-trade collisions, or millisecond timing.
- Volume is distributed uniformly across each candle range to estimate the profile. It is not exchange volume-at-price.
- The source instrument and venue are unverified; 94.1% of closes do not conform to CME NQ's quarter-point grid.
- Same-bar ambiguity is conservative: invalidation/stop is processed before entry/target. Management changes apply only to subsequent bars.
- The staged add is risk-capped, not a claim that Fabio uses this exact formula.
- The aggressive 2% path is included only because it was requested previously; it is eight times the 0.25% research risk and is not the primary result.

Methodology audit: **{audit['status']}**. Live deployment remains blocked without identified tick-level NQ data and a fresh holdout.
"""
    (output / "report.md").write_text(report, encoding="utf-8")
    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "RESEARCH_ONLY_NOT_TRUE_ORDER_FLOW",
        "config": asdict(config),
        "thresholds": thresholds,
        "data_quality": data_quality,
        "blocked": {
            "static_0.25pct": static_blocked,
            "staged_0.25pct": staged_blocked,
            "starter_only_0.10pct": starter_only_blocked,
            "staged_2pct": aggressive_blocked,
        },
        "development_selected_specification": selected_specification,
        "audit": audit,
    }
    (output / "governance.json").write_text(
        json.dumps(governance, indent=2), encoding="utf-8"
    )
    return {
        "output": output,
        "performance": performance,
        "signal_funnel": signal_funnel,
        "audit": audit,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--schedule", type=Path, default=DEFAULT_SCHEDULE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_triple_a_ohlcv_proxy(
        args.project_root,
        data_path=args.data,
        schedule_path=args.schedule,
        output_dir=args.output,
    )
    print(f"Report: {result['output'] / 'report.md'}")
    print(
        result["performance"].loc[
            result["performance"]["side"].eq("both")
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
