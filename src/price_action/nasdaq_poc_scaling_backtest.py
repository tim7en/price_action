"""Two-minute Nasdaq POC/trend/scaling research extension.

This module deliberately leaves the original session backtest unchanged.  It
tests shorter post-opening horizons and an auditable extension of the supplied
Direction/Location/Aggression framework: a causal daily trend bias, POCs from
the prior five complete sessions, a profit-protecting trailing stop, and at
most one add-on financed only by profit already locked on the base position.

The input remains unidentified OHLCV.  Its volume profile and delta fields are
proxies, not CME price-at-volume, bid/ask delta, or executable order flow.
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

from .data import resolve_project_root
from .nasdaq_session_backtest import (
    DEFAULT_DATA,
    DEFAULT_EXECUTION,
    HOLDOUT_START,
    NasdaqExecutionCosts,
    NasdaqStrategyConfig,
    _complete_grid,
    _markdown_table,
    add_indicators,
    build_candidates,
    build_ny_schedule,
    cost_sensitivity,
    load_execution_costs,
    load_nasdaq_bars,
    session_bootstrap,
    trade_summary,
    volume_profile_levels,
)


DEFAULT_OUTPUT = Path("outputs/nasdaq_poc_scaling_backtest")


@dataclass(frozen=True)
class ManagedVariant:
    name: str
    entry_window_minutes: int
    max_holding_minutes: int
    trend_sizing: bool = False
    trailing_stop: bool = False
    poc_scaling: bool = False
    base_risk_scale: float = 1.0
    trend_model: str = "10_30"
    signal_source: str = "base"
    chart_scaling: bool = False

    def __post_init__(self) -> None:
        if self.entry_window_minutes not in {10, 16, 20, 30}:
            raise ValueError("Entry window must be 10, 16, 20, or 30 minutes")
        if self.max_holding_minutes <= 0 or self.max_holding_minutes % 2:
            raise ValueError("Holding time must be a positive multiple of two minutes")
        if self.poc_scaling and not self.trailing_stop:
            raise ValueError("POC scaling requires a profit-protecting stop")
        if self.chart_scaling and not self.trailing_stop:
            raise ValueError("Chart scaling requires a profit-protecting stop")
        if self.chart_scaling and self.poc_scaling:
            raise ValueError("Choose one scaling trigger per variant")
        if not 0.0 < self.base_risk_scale <= 1.0:
            raise ValueError("Base-risk scale must be within (0, 1]")
        if self.trend_model not in {"10_30", "3_10"}:
            raise ValueError("Trend model must be 10_30 or 3_10")
        if self.signal_source not in {"base", "aligned_poc_immediate", "aligned_poc_acceptance"}:
            raise ValueError("Unknown signal source")


@dataclass(frozen=True)
class PocManagementConfig:
    base_risk_fraction: float = 0.01
    neutral_risk_multiplier: float = 0.75
    countertrend_risk_multiplier: float = 0.50
    max_notional_fraction: float = 10.0
    initial_stop_atr: float = 1.0
    reward_to_risk: float = 2.0
    trail_activation_r: float = 1.0
    locked_profit_r: float = 0.25
    trail_atr: float = 1.5
    poc_sessions: int = 5
    poc_cross_tolerance_atr: float = 0.10
    max_add_fraction_of_base: float = 0.50
    minimum_add_notional_fraction: float = 0.05
    max_daily_losses: int = 3

    def __post_init__(self) -> None:
        if not 0.0 < self.base_risk_fraction <= 0.05:
            raise ValueError("Base risk must be positive and no greater than 5%")
        if not 0.0 < self.countertrend_risk_multiplier <= self.neutral_risk_multiplier <= 1.0:
            raise ValueError("Trend-risk multipliers must be ordered within (0, 1]")
        if self.reward_to_risk < 2.0 or self.trail_activation_r <= 0.0:
            raise ValueError("Invalid reward/risk or trailing activation")
        if not 0.0 <= self.locked_profit_r < self.trail_activation_r:
            raise ValueError("Locked profit must be below trailing activation")
        if self.poc_sessions not in {3, 4, 5}:
            raise ValueError("POC history must use three to five sessions")


def daily_poc_context(
    bars: pd.DataFrame,
    schedule: pd.DataFrame,
    strategy: NasdaqStrategyConfig,
    management: PocManagementConfig,
) -> pd.DataFrame:
    """Build trend and POC context using completed sessions strictly before today."""
    completed: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for session in schedule.itertuples(index=False):
        session_open = pd.Timestamp(session.session_open)
        session_close = pd.Timestamp(session.session_close)
        prior = completed.copy()
        prior_closes = [float(item["rth_close"]) for item in prior]
        prior_pocs = [float(item["poc"]) for item in prior[-management.poc_sessions:]][::-1]
        poc_migration_3d = 0
        if len(prior_pocs) >= 3:
            if prior_pocs[0] > prior_pocs[1] > prior_pocs[2]:
                poc_migration_3d = 1
            elif prior_pocs[0] < prior_pocs[1] < prior_pocs[2]:
                poc_migration_3d = -1
        row: dict[str, Any] = {
            "session_date": str(session.session_date),
            "session_open": session_open,
            "session_close": session_close,
            "prior_close": prior_closes[-1] if prior_closes else np.nan,
            "sma_3d": float(np.mean(prior_closes[-3:])) if len(prior_closes) >= 3 else np.nan,
            "sma_10d": float(np.mean(prior_closes[-10:])) if len(prior_closes) >= 10 else np.nan,
            "sma_30d": float(np.mean(prior_closes[-30:])) if len(prior_closes) >= 30 else np.nan,
            "poc_migration_3d": poc_migration_3d,
            "available_prior_pocs": len(prior_pocs),
        }
        for offset in range(management.poc_sessions):
            row[f"prior_poc_{offset + 1}"] = (
                prior_pocs[offset] if offset < len(prior_pocs) else np.nan
            )
        finite_pocs = np.asarray(prior_pocs, dtype=float)
        row["prior_poc_zone_low"] = (
            float(finite_pocs.min()) if len(finite_pocs) else np.nan
        )
        row["prior_poc_zone_high"] = (
            float(finite_pocs.max()) if len(finite_pocs) else np.nan
        )
        rows.append(row)

        rth = bars.loc[(bars.index >= session_open) & (bars.index < session_close)]
        if not _complete_grid(bars, session_open, session_close, strategy.bar_interval):
            continue
        poc, _, _ = volume_profile_levels(
            rth,
            rows=strategy.profile_rows,
            value_fraction=strategy.profile_value_fraction,
        )
        if np.isfinite(poc):
            completed.append({
                "session_date": str(session.session_date),
                "poc": float(poc),
                "rth_close": float(rth["close"].iloc[-1]),
            })
    return pd.DataFrame(rows)


def trend_bias(price: float, sma_10d: float, sma_30d: float) -> int:
    """Return +1 only for price > SMA10 > SMA30 and -1 for the inverse."""
    if not all(np.isfinite(value) for value in [price, sma_10d, sma_30d]):
        return 0
    if price > sma_10d > sma_30d:
        return 1
    if price < sma_10d < sma_30d:
        return -1
    return 0


def short_trend_bias(price: float, sma_3d: float, sma_10d: float) -> int:
    """Return +1 for price > SMA3 > SMA10 and -1 for the inverse."""
    if not all(np.isfinite(value) for value in [price, sma_3d, sma_10d]):
        return 0
    if price > sma_3d > sma_10d:
        return 1
    if price < sma_3d < sma_10d:
        return -1
    return 0


def add_developing_auction_context(
    indicated_bars: pd.DataFrame,
    candidates: pd.DataFrame,
    strategy: NasdaqStrategyConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Add causal current-session developing POC estimates to execution bars."""
    indicated = indicated_bars.copy()
    candidate_frame = candidates.copy()
    indicated["developing_poc"] = np.nan
    indicated["developing_poc_change"] = np.nan
    for _, session_candidates in candidate_frame.groupby("session_date", sort=True):
        ordered = session_candidates.sort_values("timestamp")
        pocs: list[float] = []
        bar_ids: list[int] = []
        session_open = pd.Timestamp(ordered["session_open"].iloc[0])
        for row in ordered.itertuples(index=False):
            timestamp = pd.Timestamp(row.timestamp)
            history = indicated.loc[
                (indicated.index >= session_open)
                & (indicated.index <= timestamp)
            ]
            poc, _, _ = volume_profile_levels(
                history,
                rows=strategy.profile_rows,
                value_fraction=strategy.profile_value_fraction,
            )
            pocs.append(float(poc))
            bar_ids.append(int(row.bar_id))
        for offset, (bar_id, poc) in enumerate(zip(bar_ids, pocs, strict=True)):
            indicated.iloc[
                bar_id,
                indicated.columns.get_loc("developing_poc"),
            ] = poc
            change = poc - pocs[offset - 1] if offset > 0 else 0.0
            indicated.iloc[
                bar_id,
                indicated.columns.get_loc("developing_poc_change"),
            ] = change
    poc_by_bar_id = pd.Series(
        indicated["developing_poc"].to_numpy(),
        index=indicated["bar_id"].astype(int),
    )
    change_by_bar_id = pd.Series(
        indicated["developing_poc_change"].to_numpy(),
        index=indicated["bar_id"].astype(int),
    )
    candidate_frame["developing_poc"] = candidate_frame["bar_id"].map(poc_by_bar_id)
    candidate_frame["developing_poc_change"] = candidate_frame["bar_id"].map(change_by_bar_id)
    return indicated, candidate_frame


def crossed_prior_poc(
    previous_close: float,
    current_close: float,
    prior_pocs: list[float],
    tolerance: float,
    side: int,
) -> float | None:
    """Return the first POC whose tolerance band was crossed in trade direction."""
    levels = sorted(level for level in prior_pocs if np.isfinite(level))
    if side < 0:
        levels = list(reversed(levels))
    for level in levels:
        if side > 0 and previous_close <= level - tolerance and current_close > level + tolerance:
            return float(level)
        if side < 0 and previous_close >= level + tolerance and current_close < level - tolerance:
            return float(level)
    return None


def poc_cross_event_study(
    candidates: pd.DataFrame,
    indicated_bars: pd.DataFrame,
    strategy: NasdaqStrategyConfig,
    management: PocManagementConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Measure fast continuation after causal crosses of prior-session POCs."""
    events: list[dict[str, Any]] = []
    horizon_bars = {2: 1, 4: 2, 6: 3, 10: 5}
    for row in candidates.itertuples(index=False):
        if int(row.available_prior_pocs) < 3:
            continue
        bar_id = int(row.bar_id)
        if bar_id <= 0:
            continue
        previous_close = float(indicated_bars.iloc[bar_id - 1]["close"])
        current_close = float(row.close)
        if current_close == previous_close:
            continue
        side = 1 if current_close > previous_close else -1
        pocs = [
            float(getattr(row, f"prior_poc_{offset}"))
            for offset in range(1, management.poc_sessions + 1)
            if np.isfinite(getattr(row, f"prior_poc_{offset}"))
        ]
        crossed = crossed_prior_poc(
            previous_close,
            current_close,
            pocs,
            float(row.atr) * management.poc_cross_tolerance_atr,
            side,
        )
        if crossed is None:
            continue
        bias = trend_bias(current_close, float(row.sma_10d), float(row.sma_30d))
        short_bias = short_trend_bias(current_close, float(row.sma_3d), float(row.sma_10d))
        regime_side = (
            1 if row.day_regime == "imbalance_up"
            else -1 if row.day_regime == "imbalance_down"
            else 0
        )
        execution_minute = int(
            (pd.Timestamp(row.timestamp) - pd.Timestamp(row.session_open))
            / pd.Timedelta(minutes=1)
        ) - 30
        aggressive = bool(row.aggressive_up if side > 0 else row.aggressive_down)
        delta_aligned = bool(
            row.smoothed_delta_proxy > 0.0
            if side > 0
            else row.smoothed_delta_proxy < 0.0
        )
        payload: dict[str, Any] = {
            "timestamp": pd.Timestamp(row.timestamp),
            "session_date": str(row.session_date),
            "side": "long" if side > 0 else "short",
            "crossed_poc": crossed,
            "cross_price": current_close,
            "atr": float(row.atr),
            "trend_bias": "long" if bias > 0 else "short" if bias < 0 else "neutral",
            "trend_aligned": bias == side,
            "short_trend_bias": (
                "long" if short_bias > 0 else "short" if short_bias < 0 else "neutral"
            ),
            "short_trend_aligned": short_bias == side,
            "session_regime_aligned": regime_side == side,
            "poc_migration_aligned": int(row.poc_migration_3d) == side,
            "execution_minute": execution_minute,
            "execution_bucket": (
                "first_10m" if execution_minute < 10
                else "middle_10m" if execution_minute < 20
                else "last_10m"
            ),
            "aggressive": aggressive,
            "delta_aligned": delta_aligned,
            "aggression_and_delta_aligned": aggressive and delta_aligned,
        }
        complete = True
        for minutes, offset in horizon_bars.items():
            future_id = bar_id + offset
            if future_id >= len(indicated_bars):
                complete = False
                break
            future_time = pd.Timestamp(indicated_bars.index[future_id])
            if (
                future_time != pd.Timestamp(row.timestamp) + strategy.bar_interval * offset
                or future_time >= pd.Timestamp(row.session_close)
            ):
                complete = False
                break
            future_close = float(indicated_bars.iloc[future_id]["close"])
            payload[f"forward_{minutes}m_bps"] = (
                side * (future_close / current_close - 1.0) * 10_000.0
            )
        if not complete:
            continue
        forward = indicated_bars.iloc[bar_id + 1:bar_id + horizon_bars[10] + 1]
        if side > 0:
            favorable = float(forward["high"].max() - current_close)
            adverse = float(current_close - forward["low"].min())
        else:
            favorable = float(current_close - forward["low"].min())
            adverse = float(forward["high"].max() - current_close)
        payload["max_favorable_10m_atr"] = favorable / float(row.atr)
        payload["max_adverse_10m_atr"] = adverse / float(row.atr)
        events.append(payload)

    event_frame = pd.DataFrame(events)
    if event_frame.empty:
        return event_frame, pd.DataFrame(), pd.DataFrame()
    groups = {
        "all_poc_crosses": pd.Series(True, index=event_frame.index),
        "trend_10d_30d_aligned": event_frame["trend_aligned"],
        "trend_3d_10d_aligned": event_frame["short_trend_aligned"],
        "session_regime_aligned": event_frame["session_regime_aligned"],
        "poc_migration_3d_aligned": event_frame["poc_migration_aligned"],
        "session_plus_3d_10d": (
            event_frame["session_regime_aligned"]
            & event_frame["short_trend_aligned"]
        ),
        "3d_10d_plus_poc_migration": (
            event_frame["short_trend_aligned"]
            & event_frame["poc_migration_aligned"]
        ),
        "session_trend_poc_migration": (
            event_frame["session_regime_aligned"]
            & event_frame["short_trend_aligned"]
            & event_frame["poc_migration_aligned"]
        ),
        "aggression_and_delta_aligned": event_frame["aggression_and_delta_aligned"],
        "3d_10d_plus_aggression_delta": (
            event_frame["short_trend_aligned"]
            & event_frame["aggression_and_delta_aligned"]
        ),
    }
    timing_groups = {
        "first_10m_after_observation": event_frame["execution_bucket"].eq("first_10m"),
        "middle_10m_after_observation": event_frame["execution_bucket"].eq("middle_10m"),
        "last_10m_after_observation": event_frame["execution_bucket"].eq("last_10m"),
        "first_10m_and_3d_10d_aligned": (
            event_frame["execution_bucket"].eq("first_10m")
            & event_frame["short_trend_aligned"]
        ),
        "first_10m_3d_10d_poc_migration": (
            event_frame["execution_bucket"].eq("first_10m")
            & event_frame["short_trend_aligned"]
            & event_frame["poc_migration_aligned"]
        ),
    }

    def summarize(group_masks: dict[str, pd.Series], seed: int) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        rng = np.random.default_rng(seed)
        for group_name, mask in group_masks.items():
            frame = event_frame.loc[mask].copy()
            daily_10m = frame.groupby("session_date", sort=True)["forward_10m_bps"].mean()
            if len(daily_10m):
                bootstrap_draws = rng.choice(
                    daily_10m.to_numpy(dtype=float),
                    size=(5_000, len(daily_10m)),
                    replace=True,
                ).mean(axis=1)
            else:
                bootstrap_draws = np.asarray([], dtype=float)
            row: dict[str, Any] = {
                "group": group_name,
                "events": int(len(frame)),
                "sessions": int(frame["session_date"].nunique()),
                "mean_max_favorable_10m_atr": float(frame["max_favorable_10m_atr"].mean())
                if len(frame) else np.nan,
                "mean_max_adverse_10m_atr": float(frame["max_adverse_10m_atr"].mean())
                if len(frame) else np.nan,
                "session_bootstrap_10m_ci_low_bps": float(np.quantile(bootstrap_draws, 0.025))
                if len(bootstrap_draws) else np.nan,
                "session_bootstrap_10m_ci_high_bps": float(np.quantile(bootstrap_draws, 0.975))
                if len(bootstrap_draws) else np.nan,
                "session_bootstrap_probability_10m_positive": float((bootstrap_draws > 0.0).mean())
                if len(bootstrap_draws) else np.nan,
            }
            for minutes in horizon_bars:
                values = frame[f"forward_{minutes}m_bps"]
                row[f"mean_forward_{minutes}m_bps"] = float(values.mean()) if len(frame) else np.nan
                row[f"median_forward_{minutes}m_bps"] = float(values.median()) if len(frame) else np.nan
                row[f"positive_forward_{minutes}m_share"] = float(values.gt(0.0).mean()) if len(frame) else np.nan
            rows.append(row)
        return pd.DataFrame(rows)

    return event_frame, summarize(groups, 20260722), summarize(timing_groups, 20260723)


def aligned_poc_signal_sets(
    candidates: pd.DataFrame,
    poc_events: pd.DataFrame,
    strategy: NasdaqStrategyConfig,
    management: PocManagementConfig,
) -> dict[str, pd.DataFrame]:
    """Build immediate-cross control and one-bar acceptance-confirmed POC signals."""
    if poc_events.empty:
        empty = candidates.iloc[0:0].copy()
        return {"aligned_poc_immediate": empty, "aligned_poc_acceptance": empty}
    selected_events = poc_events.loc[
        poc_events["execution_bucket"].eq("first_10m")
        & poc_events["short_trend_aligned"]
        & poc_events["poc_migration_aligned"]
    ].copy()
    candidate_lookup = candidates.set_index("timestamp", drop=False)
    immediate_rows: list[pd.Series] = []
    acceptance_rows: list[pd.Series] = []
    for event in selected_events.itertuples(index=False):
        timestamp = pd.Timestamp(event.timestamp)
        if timestamp not in candidate_lookup.index:
            continue
        side = 1 if event.side == "long" else -1
        immediate = candidate_lookup.loc[timestamp].copy()
        if isinstance(immediate, pd.DataFrame):
            immediate = immediate.iloc[0].copy()
        immediate["signal_side"] = side
        immediate["setup"] = "aligned_poc_immediate_cross"
        immediate["crossed_poc"] = float(event.crossed_poc)
        immediate_rows.append(immediate)

        confirmation_time = timestamp + strategy.bar_interval
        if confirmation_time not in candidate_lookup.index:
            continue
        confirmation = candidate_lookup.loc[confirmation_time].copy()
        if isinstance(confirmation, pd.DataFrame):
            confirmation = confirmation.iloc[0].copy()
        if str(confirmation["session_date"]) != str(event.session_date):
            continue
        tolerance = float(confirmation["atr"]) * management.poc_cross_tolerance_atr
        remains_accepted = (
            float(confirmation["close"]) > float(event.crossed_poc) + tolerance
            if side > 0
            else float(confirmation["close"]) < float(event.crossed_poc) - tolerance
        )
        vwap_aligned = (
            float(confirmation["close"]) > float(confirmation["session_vwap"])
            if side > 0
            else float(confirmation["close"]) < float(confirmation["session_vwap"])
        )
        if not remains_accepted or not vwap_aligned:
            continue
        confirmation["signal_side"] = side
        confirmation["setup"] = "aligned_poc_acceptance_confirmation"
        confirmation["crossed_poc"] = float(event.crossed_poc)
        acceptance_rows.append(confirmation)
    return {
        "aligned_poc_immediate": pd.DataFrame(immediate_rows),
        "aligned_poc_acceptance": pd.DataFrame(acceptance_rows),
    }


def financed_add_notional(
    *,
    base_notional: float,
    base_entry: float,
    add_entry: float,
    protected_stop: float,
    side: int,
    cost_rate: float,
    management: PocManagementConfig,
) -> tuple[float, float]:
    """Size an add-on so its stop loss and costs consume only locked base profit."""
    locked_base_net = (
        side * base_notional * (protected_stop / base_entry - 1.0)
        - 2.0 * base_notional * cost_rate
    )
    add_price_risk = side * (add_entry - protected_stop) / add_entry
    risk_and_cost_per_notional = add_price_risk + 2.0 * cost_rate
    if locked_base_net <= 0.0 or risk_and_cost_per_notional <= 0.0:
        return 0.0, float(locked_base_net)
    add_notional = min(
        management.max_add_fraction_of_base * base_notional,
        management.max_notional_fraction - base_notional,
        locked_base_net / risk_and_cost_per_notional,
    )
    if add_notional < management.minimum_add_notional_fraction:
        add_notional = 0.0
    return float(max(0.0, add_notional)), float(locked_base_net)


def _risk_multiplier(side: int, bias: int, variant: ManagedVariant, management: PocManagementConfig) -> float:
    if not variant.trend_sizing:
        return variant.base_risk_scale
    if bias == side:
        return variant.base_risk_scale
    if bias == 0:
        return variant.base_risk_scale * management.neutral_risk_multiplier
    return variant.base_risk_scale * management.countertrend_risk_multiplier


def _variant_trend_bias(signal: pd.Series, variant: ManagedVariant) -> int:
    if variant.trend_model == "3_10":
        return short_trend_bias(
            float(signal["close"]),
            float(signal["sma_3d"]),
            float(signal["sma_10d"]),
        )
    return trend_bias(
        float(signal["close"]),
        float(signal["sma_10d"]),
        float(signal["sma_30d"]),
    )


def simulate_managed_trade(
    signal: pd.Series,
    indicated_bars: pd.DataFrame,
    strategy: NasdaqStrategyConfig,
    execution: NasdaqExecutionCosts,
    variant: ManagedVariant,
    management: PocManagementConfig,
) -> dict[str, Any] | None:
    signal_id = int(signal["bar_id"])
    entry_id = signal_id + 1
    if entry_id >= len(indicated_bars):
        return None
    entry_time = pd.Timestamp(indicated_bars.index[entry_id])
    signal_time = pd.Timestamp(signal["timestamp"])
    window_end = pd.Timestamp(signal["session_open"]) + pd.Timedelta(
        minutes=30 + variant.entry_window_minutes
    )
    if entry_time != signal_time + strategy.bar_interval or entry_time >= window_end:
        return None
    session_close = pd.Timestamp(signal["session_close"])
    entry_price = float(indicated_bars.iloc[entry_id]["open"])
    atr = float(signal["atr"])
    if not np.isfinite(atr) or atr <= 0.0:
        return None
    side = int(signal["signal_side"])
    bias = _variant_trend_bias(signal, variant)
    risk_multiplier = _risk_multiplier(side, bias, variant, management)
    stop_distance = atr * management.initial_stop_atr
    stop_fraction = stop_distance / entry_price
    base_notional = min(
        management.max_notional_fraction,
        management.base_risk_fraction * risk_multiplier / stop_fraction,
    )
    initial_stop = entry_price - side * stop_distance
    protected_stop = initial_stop
    target_price = entry_price + side * stop_distance * management.reward_to_risk
    max_holding_bars = variant.max_holding_minutes // strategy.bar_minutes
    final_id = min(entry_id + max_holding_bars - 1, len(indicated_bars) - 1)
    exit_price = float(indicated_bars.iloc[final_id]["close"])
    exit_time = pd.Timestamp(indicated_bars.index[final_id])
    exit_reason = "max_holding"
    favorable_close = entry_price
    stop_raised = False
    pending_poc: float | None = None
    added_notional = 0.0
    add_entry_price = np.nan
    add_entry_time = pd.NaT
    add_locked_profit = 0.0
    scale_signal_time = pd.NaT
    scale_signal_poc = np.nan
    scale_poc = np.nan
    poc_cross_count = 0
    aligned_poc_cross_count = 0
    qualified_scale_signal_count = 0
    scale_rejection_reason = "not_signaled"
    scale_trigger = "none"
    chart_acceptance_count = 0
    signal_developing_poc = float(signal.get("developing_poc", np.nan))
    pocs = [
        float(signal[f"prior_poc_{offset}"])
        for offset in range(1, management.poc_sessions + 1)
        if np.isfinite(signal[f"prior_poc_{offset}"])
    ]

    for bar_id in range(entry_id, final_id + 1):
        bar = indicated_bars.iloc[bar_id]
        timestamp = pd.Timestamp(indicated_bars.index[bar_id])
        if timestamp >= session_close or timestamp >= window_end:
            break

        if pending_poc is not None and added_notional == 0.0:
            possible_add_entry = float(bar["open"])
            still_protected = (
                possible_add_entry > protected_stop if side > 0 else possible_add_entry < protected_stop
            )
            if still_protected:
                added_notional, add_locked_profit = financed_add_notional(
                    base_notional=base_notional,
                    base_entry=entry_price,
                    add_entry=possible_add_entry,
                    protected_stop=protected_stop,
                    side=side,
                    cost_rate=execution.one_way_cost_rate,
                    management=management,
                )
                if added_notional > 0.0:
                    add_entry_price = possible_add_entry
                    add_entry_time = timestamp
                    scale_poc = pending_poc
                    scale_rejection_reason = "filled"
                else:
                    scale_rejection_reason = "insufficient_locked_profit_or_capacity"
            else:
                scale_rejection_reason = "next_open_through_protected_stop"
            pending_poc = None

        stop_hit = (
            float(bar["low"]) <= protected_stop
            if side > 0
            else float(bar["high"]) >= protected_stop
        )
        target_hit = (
            float(bar["high"]) >= target_price
            if side > 0
            else float(bar["low"]) <= target_price
        )
        if stop_hit:
            exit_price = protected_stop
            exit_time = timestamp
            exit_reason = "trailing_stop" if stop_raised else "stop"
            break
        if target_hit:
            exit_price = target_price
            exit_time = timestamp
            exit_reason = "target"
            break

        current_close = float(bar["close"])
        previous_close = (
            entry_price if bar_id == entry_id else float(indicated_bars.iloc[bar_id - 1]["close"])
        )
        prior_favorable_close = favorable_close
        favorable_close = (
            max(favorable_close, current_close)
            if side > 0
            else min(favorable_close, current_close)
        )
        favorable_r = side * (favorable_close - entry_price) / stop_distance
        if variant.trailing_stop and favorable_r >= management.trail_activation_r:
            locked_stop = entry_price + side * stop_distance * management.locked_profit_r
            current_atr = float(bar["atr"])
            atr_stop = favorable_close - side * current_atr * management.trail_atr
            if side > 0:
                protected_stop = max(protected_stop, locked_stop, atr_stop)
            else:
                protected_stop = min(protected_stop, locked_stop, atr_stop)
            stop_raised = True

        tolerance = float(bar["atr"]) * management.poc_cross_tolerance_atr
        crossed = crossed_prior_poc(previous_close, current_close, pocs, tolerance, side)
        if crossed is not None:
            poc_cross_count += 1
            if bias == side:
                aligned_poc_cross_count += 1
        aggressive = bool(bar["aggressive_up"] if side > 0 else bar["aggressive_down"])
        delta_aligned = bool(
            bar["smoothed_delta_proxy"] > 0.0
            if side > 0
            else bar["smoothed_delta_proxy"] < 0.0
        )
        if (
            variant.poc_scaling
            and added_notional == 0.0
            and pending_poc is None
            and bias == side
            and stop_raised
            and crossed is not None
            and aggressive
            and delta_aligned
            and timestamp + strategy.bar_interval < window_end
        ):
            pending_poc = crossed
            scale_trigger = "prior_poc_cross"
            qualified_scale_signal_count += 1
            if pd.isna(scale_signal_time):
                scale_signal_time = timestamp
                scale_signal_poc = crossed

        prior_close_accepted = (
            side * (previous_close - entry_price) >= 0.5 * stop_distance
        )
        current_close_accepted = (
            side * (current_close - entry_price) >= 0.5 * stop_distance
        )
        developing_poc = float(bar.get("developing_poc", np.nan))
        developing_poc_migrated = bool(
            np.isfinite(developing_poc)
            and np.isfinite(signal_developing_poc)
            and side * (developing_poc - signal_developing_poc) >= 0.10 * float(bar["atr"])
        )
        new_price_displacement = side * (current_close - prior_favorable_close) > 0.0
        price_expansion = bool(
            float(bar["bar_range"]) >= 0.80 * float(bar["atr"])
            and (
                float(bar["close_location"]) >= 0.75
                if side > 0
                else float(bar["close_location"]) <= 0.25
            )
        )
        chart_acceptance = bool(
            prior_close_accepted
            and current_close_accepted
            and developing_poc_migrated
            and new_price_displacement
            and price_expansion
        )
        if chart_acceptance:
            chart_acceptance_count += 1
        if (
            variant.chart_scaling
            and added_notional == 0.0
            and pending_poc is None
            and bias == side
            and stop_raised
            and chart_acceptance
            and timestamp + strategy.bar_interval < window_end
        ):
            pending_poc = developing_poc
            scale_trigger = "chart_acceptance_and_poc_migration"
            qualified_scale_signal_count += 1
            if pd.isna(scale_signal_time):
                scale_signal_time = timestamp
                scale_signal_poc = developing_poc

        exit_price = current_close
        exit_time = timestamp
        exit_reason = (
            "window_end"
            if timestamp + strategy.bar_interval >= window_end
            else "max_holding"
        )
        if timestamp + strategy.bar_interval >= window_end:
            break

    if pending_poc is not None and added_notional == 0.0:
        scale_rejection_reason = "no_next_bar_before_window_end"

    legs = [(base_notional, entry_price)]
    if added_notional > 0.0:
        legs.append((added_notional, float(add_entry_price)))
    gross_return = float(sum(
        side * notional * (exit_price / leg_entry - 1.0)
        for notional, leg_entry in legs
    ))
    total_entry_notional = float(sum(notional for notional, _ in legs))
    turnover = 2.0 * total_entry_notional
    execution_cost = turnover * execution.one_way_cost_rate
    net_return = gross_return - execution_cost
    deployed_risk = base_notional * stop_fraction
    return {
        "variant": variant.name,
        "signal_time": signal_time,
        "entry_time": entry_time,
        "exit_time": exit_time,
        "session_date": str(signal["session_date"]),
        "phase": signal["phase"],
        "day_regime": signal["day_regime"],
        "setup": signal["setup"],
        "side": "long" if side > 0 else "short",
        "trend_bias": "long" if bias > 0 else "short" if bias < 0 else "neutral",
        "trend_model": variant.trend_model,
        "trend_risk_multiplier": risk_multiplier,
        "entry_price": entry_price,
        "initial_stop_price": initial_stop,
        "final_stop_price": protected_stop,
        "target_price": target_price,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "holding_bars": int((exit_time - entry_time) / strategy.bar_interval) + 1,
        "holding_minutes": int((exit_time - entry_time) / pd.Timedelta(minutes=1))
        + strategy.bar_minutes,
        "notional_fraction": total_entry_notional,
        "base_notional_fraction": base_notional,
        "added_notional_fraction": added_notional,
        "scale_count": int(added_notional > 0.0),
        "scale_signal_time": scale_signal_time,
        "scale_signal_poc": scale_signal_poc,
        "scale_entry_time": add_entry_time,
        "scale_entry_price": add_entry_price,
        "scale_poc": scale_poc,
        "locked_net_profit_at_scale": add_locked_profit,
        "stop_was_raised": stop_raised,
        "poc_cross_count": poc_cross_count,
        "aligned_poc_cross_count": aligned_poc_cross_count,
        "qualified_scale_signal_count": qualified_scale_signal_count,
        "scale_rejection_reason": scale_rejection_reason,
        "scale_trigger": scale_trigger,
        "chart_acceptance_count": chart_acceptance_count,
        "risk_fraction_deployed": deployed_risk,
        "gross_return": gross_return,
        "one_way_turnover": turnover,
        "execution_cost": execution_cost,
        "net_return": net_return,
        "gross_r_multiple": gross_return / deployed_risk if deployed_risk > 0.0 else np.nan,
        "net_r_multiple": net_return / deployed_risk if deployed_risk > 0.0 else np.nan,
    }


def run_managed_backtest(
    candidates: pd.DataFrame,
    indicated_bars: pd.DataFrame,
    strategy: NasdaqStrategyConfig,
    execution: NasdaqExecutionCosts,
    variant: ManagedVariant,
    management: PocManagementConfig,
) -> tuple[pd.DataFrame, dict[str, int]]:
    window_end = candidates["session_open"] + pd.to_timedelta(
        30 + variant.entry_window_minutes,
        unit="minute",
    )
    signals = candidates.loc[
        candidates["signal_side"].ne(0) & candidates["timestamp"].lt(window_end)
    ].sort_values("timestamp")
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
        if losses_by_session.get(session_date, 0) >= management.max_daily_losses:
            blocked["daily_loss_stop"] += 1
            continue
        trade = simulate_managed_trade(
            signal,
            indicated_bars,
            strategy,
            execution,
            variant,
            management,
        )
        if trade is None:
            blocked["unexecutable"] += 1
            continue
        trades.append(trade)
        last_exit = pd.Timestamp(trade["exit_time"])
        if float(trade["net_return"]) < 0.0:
            losses_by_session[session_date] = losses_by_session.get(session_date, 0) + 1
    return pd.DataFrame(trades), blocked


def _variant_summary(trades_by_variant: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for variant, trades in trades_by_variant.items():
        summary = trade_summary(trades)
        summary.insert(0, "variant", variant)
        frames.append(summary)
    return pd.concat(frames, ignore_index=True)


def _equity_frame(trades_by_variant: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for variant, trades in trades_by_variant.items():
        if trades.empty:
            continue
        frame = trades.sort_values("exit_time").copy()
        frame["exit_time"] = pd.to_datetime(frame["exit_time"], utc=True)
        frame["variant"] = variant
        frame["gross_equity"] = (1.0 + frame["gross_return"]).cumprod()
        frame["net_equity"] = (1.0 + frame["net_return"]).cumprod()
        frame["drawdown"] = frame["net_equity"] / frame["net_equity"].cummax() - 1.0
        frames.append(frame[[
            "variant", "exit_time", "gross_return", "net_return",
            "gross_equity", "net_equity", "drawdown",
        ]])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _render_plots(
    summary: pd.DataFrame,
    equity: pd.DataFrame,
    poc_event_summary: pd.DataFrame,
    poc_timing_summary: pd.DataFrame,
    output: Path,
) -> list[Path]:
    from .nasdaq_session_backtest import _configure_plots

    plt = _configure_plots()
    from matplotlib.ticker import PercentFormatter

    paths: list[Path] = []
    focus = [
        "static_30m",
        "static_16m",
        "trend_sized_16m",
        "trend_3d_10d_sized_16m",
        "aligned_poc_acceptance_16m",
        "reserved_chart_scale_16m",
    ]
    colors = ["#64748b", "#2563eb", "#d97706", "#7c3aed", "#0f766e", "#be123c"]
    fig, axes = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
    for variant, color in zip(focus, colors, strict=True):
        frame = equity.loc[equity["variant"].eq(variant)]
        if frame.empty:
            continue
        axes[0].plot(frame["exit_time"], frame["net_equity"], label=variant, color=color, linewidth=1.8)
        axes[1].plot(frame["exit_time"], frame["drawdown"], label=variant, color=color, linewidth=1.6)
    axes[0].axhline(1.0, color="#334155", linewidth=1)
    axes[0].axvline(HOLDOUT_START, color="#be123c", linestyle=":", linewidth=1.5)
    axes[0].set_title("Two-minute managed variants: net return on equity")
    axes[0].set_ylabel("Growth of $1")
    axes[0].legend(fontsize=8, ncol=2)
    axes[0].grid(alpha=0.2)
    axes[1].axvline(HOLDOUT_START, color="#be123c", linestyle=":", linewidth=1.5)
    axes[1].set_title("Net-equity drawdowns")
    axes[1].set_ylabel("Drawdown")
    axes[1].yaxis.set_major_formatter(PercentFormatter(1.0))
    axes[1].grid(alpha=0.2)
    fig.tight_layout()
    path = output / "managed_equity_and_drawdowns.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    paths.append(path)

    scopes = summary.loc[summary["scope"].isin(["development_2024", "holdout_2025"])].copy()
    horizons = scopes.loc[scopes["variant"].str.startswith("static_")].copy()
    horizons["net_return_pct"] = horizons["cumulative_net_return"] * 100.0
    pivot = horizons.pivot(index="variant", columns="scope", values="net_return_pct")
    pivot = pivot.reindex(["static_10m", "static_16m", "static_20m", "static_30m"])
    fig, axis = plt.subplots(figsize=(10, 5.5))
    x = np.arange(len(pivot))
    width = 0.36
    axis.bar(x - width / 2, pivot.get("development_2024", 0.0), width, label="2024 development", color="#64748b")
    axis.bar(x + width / 2, pivot.get("holdout_2025", 0.0), width, label="2025 evaluation", color="#d97706")
    axis.axhline(0.0, color="#334155", linewidth=1)
    axis.set_xticks(x, [name.replace("static_", "") for name in pivot.index])
    axis.set_xlabel("Entry window and maximum phase duration")
    axis.set_ylabel("Net return on equity (%)")
    axis.set_title("Does shortening the 30-minute execution phase help?")
    axis.legend()
    axis.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    path = output / "horizon_comparison.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    paths.append(path)

    if not poc_event_summary.empty:
        fig, axis = plt.subplots(figsize=(10, 5.5))
        horizons = [2, 4, 6, 10]
        plotted_groups = [
            "all_poc_crosses",
            "trend_10d_30d_aligned",
            "trend_3d_10d_aligned",
            "session_plus_3d_10d",
            "3d_10d_plus_poc_migration",
        ]
        plot_frame = poc_event_summary.loc[poc_event_summary["group"].isin(plotted_groups)]
        plot_frame = plot_frame.set_index("group").reindex(plotted_groups).reset_index()
        event_colors = ["#64748b", "#2563eb", "#d97706", "#7c3aed", "#0f766e"]
        for (_, row), color in zip(plot_frame.iterrows(), event_colors, strict=True):
            axis.plot(
                horizons,
                [row[f"mean_forward_{minutes}m_bps"] for minutes in horizons],
                marker="o",
                linewidth=2,
                color=color,
                label=f"{row['group']} (n={int(row['events'])})",
            )
        axis.axhline(0.0, color="#334155", linewidth=1)
        axis.set_xticks(horizons)
        axis.set_xlabel("Minutes after completed POC-cross bar")
        axis.set_ylabel("Mean direction-aligned return (bps)")
        axis.set_title("Do prior-session POC crosses accelerate?")
        axis.legend(fontsize=8)
        axis.grid(alpha=0.2)
        fig.tight_layout()
        path = output / "poc_cross_forward_returns.png"
        fig.savefig(path, dpi=180, bbox_inches="tight")
        plt.close(fig)
        paths.append(path)

    if not poc_timing_summary.empty:
        fig, axis = plt.subplots(figsize=(10, 5.5))
        horizons = [2, 4, 6, 10]
        timing_colors = ["#2563eb", "#d97706", "#7c3aed", "#64748b", "#0f766e"]
        for (_, row), color in zip(poc_timing_summary.iterrows(), timing_colors, strict=True):
            axis.plot(
                horizons,
                [row[f"mean_forward_{minutes}m_bps"] for minutes in horizons],
                marker="o",
                linewidth=2,
                color=color,
                label=f"{row['group']} (n={int(row['events'])})",
            )
        axis.axhline(0.0, color="#334155", linewidth=1)
        axis.set_xticks(horizons)
        axis.set_xlabel("Minutes after completed POC-cross bar")
        axis.set_ylabel("Mean direction-aligned return (bps)")
        axis.set_title("Does POC-cross impact decay through the execution phase?")
        axis.legend(fontsize=8)
        axis.grid(alpha=0.2)
        fig.tight_layout()
        path = output / "poc_cross_timing_impact.png"
        fig.savefig(path, dpi=180, bbox_inches="tight")
        plt.close(fig)
        paths.append(path)
    return paths


def _render_chart_scale_paths(
    trades: pd.DataFrame,
    indicated_bars: pd.DataFrame,
    output: Path,
) -> Path | None:
    scaled = trades.loc[trades["scale_count"].gt(0)].copy()
    if scaled.empty:
        return None
    from .nasdaq_session_backtest import _configure_plots

    plt = _configure_plots()
    fig, axes = plt.subplots(len(scaled), 1, figsize=(12, 3.6 * len(scaled)))
    if len(scaled) == 1:
        axes = [axes]
    for axis, trade in zip(axes, scaled.itertuples(index=False), strict=True):
        entry_time = pd.Timestamp(trade.entry_time)
        exit_time = pd.Timestamp(trade.exit_time)
        path = indicated_bars.loc[
            (indicated_bars.index >= entry_time)
            & (indicated_bars.index <= exit_time)
        ].copy()
        minutes = (path.index - entry_time) / pd.Timedelta(minutes=1)
        axis.plot(minutes, path["close"], color="#1d4ed8", marker="o", linewidth=2, label="Close")
        axis.plot(
            minutes,
            path["developing_poc"],
            color="#d97706",
            linestyle="--",
            linewidth=1.5,
            label="Developing POC",
        )
        axis.axhline(float(trade.entry_price), color="#334155", linewidth=1, label="Base entry")
        axis.axhline(float(trade.target_price), color="#0f766e", linestyle=":", linewidth=1.5, label="2R target")
        axis.axhline(float(trade.final_stop_price), color="#be123c", linestyle=":", linewidth=1.5, label="Final protected stop")
        scale_minutes = (
            pd.Timestamp(trade.scale_entry_time) - entry_time
        ) / pd.Timedelta(minutes=1)
        axis.scatter(
            [scale_minutes],
            [float(trade.scale_entry_price)],
            marker="^" if trade.side == "long" else "v",
            s=100,
            color="#7c3aed",
            zorder=5,
            label=f"Add {float(trade.added_notional_fraction):.2f}x",
        )
        axis.set_title(
            f"{str(trade.entry_time)[:10]} {trade.side}: chart-acceptance add-on"
        )
        axis.set_xlabel("Minutes after base entry")
        axis.set_ylabel("Price")
        axis.grid(alpha=0.2)
        axis.legend(fontsize=8, ncol=3)
    fig.tight_layout()
    path = output / "chart_scaling_event_paths.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def _report(
    summary: pd.DataFrame,
    bootstrap: pd.DataFrame,
    scaling_audit: pd.DataFrame,
    scaling_funnel: pd.DataFrame,
    poc_event_summary: pd.DataFrame,
    poc_timing_summary: pd.DataFrame,
    cost_audit: pd.DataFrame,
    governance: dict[str, Any],
) -> str:
    decision = summary.loc[summary["scope"].isin(["all", "development_2024", "holdout_2025"])]
    return f"""# Two-Minute Nasdaq POC, Trend, Scaling, and Trailing Study

Generated {governance['generated_at_utc']}. This is a separate extension of the fixed-position New York-open baseline.

> The supplied Fabio notes document 1.5-ATR optional trailing stops and increasing risk only from the day's profits. They do not establish pyramiding into an open trade; the example payload says `pyramid: false`. The POC add-on below is our research hypothesis and is sized only from profit already locked by the raised base stop.

## Decision table

{_markdown_table(decision, rows=80)}

## Scaling audit

{_markdown_table(scaling_audit)}

## Scaling eligibility funnel

{_markdown_table(scaling_funnel)}

## Prior-session POC cross event study

{_markdown_table(poc_event_summary)}

## POC crossing by execution timing

{_markdown_table(poc_timing_summary)}

## Session-block bootstrap

{_markdown_table(bootstrap, rows=40)}

## Holdout cost sensitivity

{_markdown_table(cost_audit, rows=80)}

## Plots

- [Managed equity curves and drawdowns](managed_equity_and_drawdowns.png)
- [10/16/20/30-minute horizon comparison](horizon_comparison.png)
- [POC-cross forward returns](poc_cross_forward_returns.png)
- [POC-cross timing impact](poc_cross_timing_impact.png)
- [Chart-scaling event paths](chart_scaling_event_paths.png)

## Predeclared rules

- Signals remain the causal two-minute ORB/value-rejection signals from the first-hour model. The first 30 minutes is observation only.
- Static horizons end the execution phase 10, 16, 20, or 30 minutes after the observation window; open positions are closed at that phase boundary. Sixteen minutes is used because complete two-minute bars cannot represent 15 minutes without truncation or boundary leakage.
- Trend is causal and frozen at the signal: long only when signal price > prior-session SMA10 > SMA30, short for the inverse, otherwise neutral.
- Trend sizing risks 1.00% when aligned, 0.75% when neutral, and 0.50% when countertrend, always subject to the 10x notional cap.
- The reserved-scaling diagnostic starts with 75% of those risk allocations so an aligned trade can retain leverage capacity for an add-on. It was introduced after observing that the unconstrained signal was already at 10x, so it is diagnostic rather than validated.
- The trail activates after a completed close reaches +1R, locks +0.25R, and then follows the best completed close by 1.5 ATR. Stop changes apply only to subsequent bars.
- One add-on is eligible only after the stop is raised, trend is aligned, and an aggressive, delta-aligned completed bar crosses the 0.1-ATR band around one of the prior five completed-session POCs.
- The chart-scaling extension instead requires two closes holding at least +0.5R, a new directional close, an edge close on a range-expansion bar, and current developing POC migration of at least 0.1 ATR from its signal-time value.
- The add-on enters at the next bar open, is capped at 50% of base size and the remaining 10x capacity, and its stop risk plus round-trip cost cannot exceed net base profit already locked by the protected stop.
- Same-bar stop/target ambiguity resolves to the stop. The 2R target and three-loss daily stop remain active.

## Limitations

- This evaluates several variants on the same 2024–2025 sample; 2025 is now an evaluation set, not a fresh untouched holdout.
- POCs allocate each bar's entire volume to typical price. They show estimated acceptance, not separate buyer/seller concentration.
- OHLCV cannot show aggressor side, footprint imbalance, resting liquidity, queue position, or the intrabar path. Scaling around POC therefore remains a proxy experiment.
- The feed has no verified venue or contract identity and is inconsistent with CME NQ's tick grid. The {governance['execution']['one_way_cost_bps']:.2f}-bps one-way cost is a scenario, not measured execution.
"""


def build_poc_scaling_backtest(
    project_root: str | Path | None = None,
    *,
    data_path: str | Path = DEFAULT_DATA,
    execution_path: str | Path = DEFAULT_EXECUTION,
    output_dir: str | Path = DEFAULT_OUTPUT,
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
    trade_output = output / "trades"
    trade_output.mkdir(parents=True, exist_ok=True)

    strategy = NasdaqStrategyConfig(bar_minutes=2)
    management = PocManagementConfig()
    execution = load_execution_costs(execution_file)
    bars, data_audit = load_nasdaq_bars(data_file, 2)
    indicated = add_indicators(bars, strategy)
    schedule = build_ny_schedule(bars.index.min(), bars.index.max())
    candidates, _, quality = build_candidates(bars, schedule, strategy)
    context = daily_poc_context(bars, schedule, strategy, management)
    candidates["session_date"] = candidates["session_date"].astype(str)
    candidates = candidates.merge(context, on=["session_date", "session_open"], how="left")
    candidates["timestamp"] = pd.to_datetime(candidates["timestamp"], utc=True)
    candidates["session_open"] = pd.to_datetime(candidates["session_open"], utc=True)
    candidates["session_close"] = pd.to_datetime(candidates["session_close"], utc=True)
    indicated, candidates = add_developing_auction_context(
        indicated,
        candidates,
        strategy,
    )
    poc_events, poc_event_summary, poc_timing_summary = poc_cross_event_study(
        candidates,
        indicated,
        strategy,
        management,
    )
    poc_signal_sets = aligned_poc_signal_sets(
        candidates,
        poc_events,
        strategy,
        management,
    )

    variants = [
        ManagedVariant("static_10m", 10, 10),
        ManagedVariant("static_16m", 16, 16),
        ManagedVariant("static_20m", 20, 20),
        ManagedVariant("static_30m", 30, 30),
        ManagedVariant("trend_sized_16m", 16, 16, trend_sizing=True),
        ManagedVariant(
            "trend_3d_10d_sized_10m",
            10,
            10,
            trend_sizing=True,
            trend_model="3_10",
        ),
        ManagedVariant(
            "trend_3d_10d_sized_16m",
            16,
            16,
            trend_sizing=True,
            trend_model="3_10",
        ),
        ManagedVariant(
            "aligned_poc_immediate_10m",
            10,
            10,
            trend_model="3_10",
            signal_source="aligned_poc_immediate",
        ),
        ManagedVariant(
            "aligned_poc_acceptance_16m",
            16,
            16,
            trend_model="3_10",
            signal_source="aligned_poc_acceptance",
        ),
        ManagedVariant(
            "aligned_poc_acceptance_reserved_16m",
            16,
            16,
            trailing_stop=True,
            base_risk_scale=0.75,
            trend_model="3_10",
            signal_source="aligned_poc_acceptance",
        ),
        ManagedVariant(
            "aligned_poc_acceptance_chart_scale_16m",
            16,
            16,
            trailing_stop=True,
            base_risk_scale=0.75,
            trend_model="3_10",
            signal_source="aligned_poc_acceptance",
            chart_scaling=True,
        ),
        ManagedVariant(
            "reserved_3d_10d_trail_16m",
            16,
            16,
            trend_sizing=True,
            trailing_stop=True,
            base_risk_scale=0.75,
            trend_model="3_10",
        ),
        ManagedVariant(
            "reserved_chart_scale_16m",
            16,
            16,
            trend_sizing=True,
            trailing_stop=True,
            base_risk_scale=0.75,
            trend_model="3_10",
            chart_scaling=True,
        ),
        ManagedVariant(
            "reserved_3d_10d_trail_30m",
            30,
            30,
            trend_sizing=True,
            trailing_stop=True,
            base_risk_scale=0.75,
            trend_model="3_10",
        ),
        ManagedVariant(
            "reserved_chart_scale_30m",
            30,
            30,
            trend_sizing=True,
            trailing_stop=True,
            base_risk_scale=0.75,
            trend_model="3_10",
            chart_scaling=True,
        ),
        ManagedVariant("trend_trail_16m", 16, 16, trend_sizing=True, trailing_stop=True),
        ManagedVariant(
            "trend_trail_poc_scale_16m",
            16,
            16,
            trend_sizing=True,
            trailing_stop=True,
            poc_scaling=True,
        ),
        ManagedVariant(
            "trend_trail_poc_scale_30m",
            30,
            30,
            trend_sizing=True,
            trailing_stop=True,
            poc_scaling=True,
        ),
        ManagedVariant(
            "reserved_trend_trail_16m",
            16,
            16,
            trend_sizing=True,
            trailing_stop=True,
            base_risk_scale=0.75,
        ),
        ManagedVariant(
            "reserved_poc_scale_16m",
            16,
            16,
            trend_sizing=True,
            trailing_stop=True,
            poc_scaling=True,
            base_risk_scale=0.75,
        ),
        ManagedVariant(
            "reserved_trend_trail_30m",
            30,
            30,
            trend_sizing=True,
            trailing_stop=True,
            base_risk_scale=0.75,
        ),
        ManagedVariant(
            "reserved_poc_scale_30m",
            30,
            30,
            trend_sizing=True,
            trailing_stop=True,
            poc_scaling=True,
            base_risk_scale=0.75,
        ),
    ]
    trades_by_variant: dict[str, pd.DataFrame] = {}
    blocked: dict[str, dict[str, int]] = {}
    for variant in variants:
        variant_candidates = (
            candidates
            if variant.signal_source == "base"
            else poc_signal_sets[variant.signal_source]
        )
        trades, variant_blocked = run_managed_backtest(
            variant_candidates,
            indicated,
            strategy,
            execution,
            variant,
            management,
        )
        trades_by_variant[variant.name] = trades
        blocked[variant.name] = variant_blocked
        trades.to_csv(trade_output / f"{variant.name}.csv", index=False)

    summary = _variant_summary(trades_by_variant)
    equity = _equity_frame(trades_by_variant)
    bootstrap_frames: list[pd.DataFrame] = []
    cost_frames: list[pd.DataFrame] = []
    scale_rows: list[dict[str, Any]] = []
    funnel_rows: list[dict[str, Any]] = []
    for variant in variants:
        trades = trades_by_variant[variant.name]
        boot = session_bootstrap(trades)
        boot.insert(0, "variant", variant.name)
        bootstrap_frames.append(boot.loc[boot["setup"].eq("all")])
        costs = cost_sensitivity(trades)
        costs.insert(0, "variant", variant.name)
        cost_frames.append(costs.loc[
            costs["scope"].eq("holdout_2025") & costs["setup"].eq("all")
        ])
        scaled = trades.loc[trades["scale_count"].gt(0)] if not trades.empty else trades
        scale_rows.append({
            "variant": variant.name,
            "trades": int(len(trades)),
            "trades_with_add_on": int(len(scaled)),
            "add_on_share": float(len(scaled) / len(trades)) if len(trades) else 0.0,
            "average_added_notional": float(scaled["added_notional_fraction"].mean())
            if len(scaled) else 0.0,
            "minimum_scaled_trade_net_return": float(scaled["net_return"].min())
            if len(scaled) else np.nan,
        })
        funnel_rows.append({
            "variant": variant.name,
            "trades": int(len(trades)),
            "trend_aligned_trades": int(
                (trades["trend_bias"] == trades["side"]).sum()
            ) if len(trades) else 0,
            "trades_with_raised_stop": int(trades["stop_was_raised"].sum())
            if len(trades) else 0,
            "trades_crossing_prior_poc": int(trades["poc_cross_count"].gt(0).sum())
            if len(trades) else 0,
            "aligned_trades_crossing_prior_poc": int(
                trades["aligned_poc_cross_count"].gt(0).sum()
            ) if len(trades) else 0,
            "qualified_scale_signals": int(trades["qualified_scale_signal_count"].sum())
            if len(trades) else 0,
            "chart_acceptance_observations": int(trades["chart_acceptance_count"].sum())
            if len(trades) else 0,
            "filled_add_ons": int(trades["scale_count"].sum()) if len(trades) else 0,
        })
    bootstrap = pd.concat(bootstrap_frames, ignore_index=True)
    cost_audit = pd.concat(cost_frames, ignore_index=True)
    scaling_audit = pd.DataFrame(scale_rows)
    scaling_funnel = pd.DataFrame(funnel_rows)
    plot_paths = _render_plots(
        summary,
        equity,
        poc_event_summary,
        poc_timing_summary,
        output,
    )
    scale_path = _render_chart_scale_paths(
        trades_by_variant["reserved_chart_scale_30m"],
        indicated,
        output,
    )
    if scale_path is not None:
        plot_paths.append(scale_path)
    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "strategy": "two_minute_nasdaq_poc_trend_scaling_extension",
        "data_file": str(data_file),
        "data_quality": data_audit,
        "strategy_config": asdict(strategy),
        "management_config": asdict(management),
        "variants": [asdict(variant) for variant in variants],
        "execution": execution.to_dict(),
        "blocked_signals": blocked,
        "usable_sessions": int(quality["usable"].sum()),
        "selection_warning": "All variants share the same sample; no winner is independently validated.",
        "plot_files": [path.name for path in plot_paths],
    }
    summary.to_csv(output / "variant_summary.csv", index=False)
    equity.to_csv(output / "managed_equity_curves.csv", index=False)
    context.to_csv(output / "daily_poc_trend_context.csv", index=False)
    candidates.to_csv(output / "enriched_candidates.csv", index=False)
    bootstrap.to_csv(output / "bootstrap.csv", index=False)
    cost_audit.to_csv(output / "holdout_cost_sensitivity.csv", index=False)
    scaling_audit.to_csv(output / "scaling_audit.csv", index=False)
    scaling_funnel.to_csv(output / "scaling_eligibility_funnel.csv", index=False)
    poc_events.to_csv(output / "poc_cross_events.csv", index=False)
    poc_event_summary.to_csv(output / "poc_cross_event_summary.csv", index=False)
    poc_timing_summary.to_csv(output / "poc_cross_timing_summary.csv", index=False)
    (output / "governance.json").write_text(json.dumps(governance, indent=2), encoding="utf-8")
    (output / "report.md").write_text(
        _report(
            summary,
            bootstrap,
            scaling_audit,
            scaling_funnel,
            poc_event_summary,
            poc_timing_summary,
            cost_audit,
            governance,
        ),
        encoding="utf-8",
    )
    return {
        "output_dir": output,
        "summary": summary,
        "equity": equity,
        "trades_by_variant": trades_by_variant,
        "scaling_audit": scaling_audit,
        "scaling_funnel": scaling_funnel,
        "poc_cross_events": poc_events,
        "poc_cross_event_summary": poc_event_summary,
        "poc_cross_timing_summary": poc_timing_summary,
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
    result = build_poc_scaling_backtest(
        args.project_root,
        data_path=args.data_path,
        execution_path=args.execution_path,
        output_dir=args.output_dir,
    )
    selected = result["summary"].loc[
        result["summary"]["scope"].isin(["all", "development_2024", "holdout_2025"])
    ]
    print(f"Report: {result['output_dir'] / 'report.md'}")
    print(selected.to_string(index=False))


if __name__ == "__main__":
    main()
