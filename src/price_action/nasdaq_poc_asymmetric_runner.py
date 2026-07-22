"""One-minute POC asymmetric-payoff and conditional-runner research.

This study deliberately remains separate from the stable POC backtest.  It
tests whether tighter causal invalidation, fast failure scratches, partial
profits, and conditional runners can create a realized right tail rather than
merely labelling every entry with an attractive 2R--6R target.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .data import resolve_project_root
from .execution_costs import load_binance_execution_costs
from .nasdaq_multitimeframe_poc_backtest import (
    MultiTimeframePocConfig,
    build_composite_poc_context,
    build_fifteen_minute_blocks,
    build_poc_signal_observations,
)
from .nasdaq_poc_leverage_optimizer import DEFAULT_BINANCE_EXECUTION
from .nasdaq_session_backtest import (
    DEFAULT_DATA,
    DEFAULT_EXECUTION,
    NasdaqExecutionCosts,
    NasdaqStrategyConfig,
    _configure_plots,
    _markdown_table,
    add_indicators,
    build_ny_schedule,
    load_execution_costs,
    load_nasdaq_bars,
    session_bootstrap,
)


DEFAULT_OUTPUT = Path("outputs/nasdaq_poc_asymmetric_runner")

STOP_SPECS = ("micro_3bar", "hybrid_0.25", "hybrid_0.50")
SIGNAL_CONTEXTS = (
    "migration_rth",
    "migration_trend_rth",
    "migration_opening_15_30m",
    "opening_15_30m",
    "migration_trend_30_40m",
)
MANAGEMENT_SPECS: dict[str, dict[str, Any]] = {
    "full_2r": {"partial_r": None, "final_r": 2.0, "conditional": False, "protect": False},
    "full_3r": {"partial_r": None, "final_r": 3.0, "conditional": False, "protect": False},
    "full_4r": {"partial_r": None, "final_r": 4.0, "conditional": False, "protect": False},
    "full_6r": {"partial_r": None, "final_r": 6.0, "conditional": False, "protect": False},
    "partial_2r_to_4r": {"partial_r": 2.0, "final_r": 4.0, "conditional": False, "protect": False},
    "partial_2r_to_6r": {"partial_r": 2.0, "final_r": 6.0, "conditional": False, "protect": False},
    "conditional_2r_to_6r": {"partial_r": 2.0, "final_r": 6.0, "conditional": True, "protect": True},
}


@dataclass(frozen=True)
class AsymmetricRunnerConfig:
    risk_fraction: float = 0.01
    leverage_ceiling: float = 20.0
    maximum_session_losses: int = 3
    stop_specs: tuple[str, ...] = STOP_SPECS
    signal_contexts: tuple[str, ...] = SIGNAL_CONTEXTS
    scratch_bars: tuple[int, ...] = (0, 1, 2)
    maximum_holding_minutes: tuple[int, ...] = (5, 10, 30, 60)
    management_specs: tuple[str, ...] = tuple(MANAGEMENT_SPECS)
    micro_lookback_bars: int = 3
    micro_buffer_atr: float = 0.05
    micro_minimum_atr: float = 0.25
    scratch_minimum_progress_r: float = 0.25
    partial_fraction: float = 0.50
    protected_stop_r: float = 0.25
    development_minimum_trades: int = 20
    cost_sensitivity_bps: tuple[float, ...] = (0.5, 1.0, 2.0, 5.0, 10.0, 15.0)

    def __post_init__(self) -> None:
        if not 0.0 < self.risk_fraction <= 0.05:
            raise ValueError("risk_fraction must be inside (0, 5%]")
        if self.leverage_ceiling <= 1.0:
            raise ValueError("leverage_ceiling must exceed one")
        if not 0.0 < self.partial_fraction < 1.0:
            raise ValueError("partial_fraction must be inside (0, 1)")
        if self.micro_lookback_bars < 1:
            raise ValueError("micro_lookback_bars must be positive")
        if not set(self.stop_specs).issubset(STOP_SPECS):
            raise ValueError("Unknown stop specification")
        if not set(self.management_specs).issubset(MANAGEMENT_SPECS):
            raise ValueError("Unknown management specification")


def build_intraday_auction_state(
    bars: pd.DataFrame,
    schedule: pd.DataFrame,
    daily_context: pd.DataFrame,
) -> pd.DataFrame:
    """Build causal session VWAP and a fixed-width developing POC proxy."""
    contexts = daily_context.set_index("session_date")
    rows: list[dict[str, Any]] = []
    for session in schedule.itertuples(index=False):
        session_date = str(session.session_date)
        if session_date not in contexts.index:
            continue
        prior_atr = float(contexts.loc[session_date, "prior_daily_atr"])
        if not np.isfinite(prior_atr) or prior_atr <= 0.0:
            continue
        session_open = pd.Timestamp(session.session_open)
        session_close = pd.Timestamp(session.session_close)
        rth = bars.loc[(bars.index >= session_open) & (bars.index < session_close)]
        if len(rth) != 390:
            continue
        width = prior_atr / 64.0
        volume_at_price: dict[int, float] = {}
        cumulative_price_volume = 0.0
        cumulative_volume = 0.0
        poc_bin = 0
        poc_volume = -np.inf
        for timestamp, bar in rth.iterrows():
            typical = float((bar["high"] + bar["low"] + bar["close"]) / 3.0)
            volume = float(bar["volume"])
            bin_id = int(np.rint(typical / width))
            volume_at_price[bin_id] = volume_at_price.get(bin_id, 0.0) + volume
            if volume_at_price[bin_id] >= poc_volume:
                poc_bin = bin_id
                poc_volume = volume_at_price[bin_id]
            cumulative_price_volume += typical * volume
            cumulative_volume += volume
            rows.append({
                "timestamp": pd.Timestamp(timestamp),
                "session_date": session_date,
                "session_vwap": (
                    cumulative_price_volume / cumulative_volume
                    if cumulative_volume > 0.0 else typical
                ),
                "developing_poc": poc_bin * width,
            })
    if not rows:
        return pd.DataFrame(columns=["session_date", "session_vwap", "developing_poc"])
    return pd.DataFrame(rows).set_index("timestamp").sort_index()


def signal_context_mask(observations: pd.DataFrame, context: str) -> pd.Series:
    mask = observations["mode"].eq("one_minute_acceptance")
    mask &= observations["crossed_sources"].str.contains("3d|5d", regex=True)
    mask &= observations["completed_15m_range"].notna()
    minute = observations["minutes_from_open"]
    if context == "migration_rth":
        mask &= observations["daily_poc_migration_aligned"]
        mask &= minute.ge(15) & minute.lt(330)
    elif context == "migration_trend_rth":
        mask &= observations["daily_poc_migration_aligned"]
        mask &= observations["trend_3d_10d_aligned"]
        mask &= minute.ge(15) & minute.lt(330)
    elif context == "migration_opening_15_30m":
        mask &= observations["daily_poc_migration_aligned"]
        mask &= minute.ge(15) & minute.lt(30)
    elif context == "opening_15_30m":
        mask &= minute.ge(15) & minute.lt(30)
    elif context == "migration_trend_30_40m":
        mask &= observations["daily_poc_migration_aligned"]
        mask &= observations["trend_3d_10d_aligned"]
        mask &= minute.ge(30) & minute.lt(40)
    else:
        raise ValueError(f"Unknown signal context: {context}")
    return mask


def _stop_distance(
    signal: Any,
    bars: pd.DataFrame,
    entry: float,
    stop_spec: str,
    config: AsymmetricRunnerConfig,
) -> tuple[float, float]:
    side = int(signal.side)
    anchor_id = int(signal.bar_id)
    start = max(0, anchor_id - config.micro_lookback_bars + 1)
    causal = bars.iloc[start:anchor_id + 1]
    atr = float(signal.atr)
    if side > 0:
        micro = entry - float(causal["low"].min()) + config.micro_buffer_atr * atr
    else:
        micro = float(causal["high"].max()) - entry + config.micro_buffer_atr * atr
    micro = max(micro, config.micro_minimum_atr * atr)
    if stop_spec == "micro_3bar":
        distance = micro
    elif stop_spec == "hybrid_0.25":
        distance = max(micro, atr, 0.25 * float(signal.completed_15m_range))
    elif stop_spec == "hybrid_0.50":
        distance = max(micro, atr, 0.50 * float(signal.completed_15m_range))
    else:
        raise ValueError(f"Unknown stop specification: {stop_spec}")
    return float(distance), float(micro)


def _auction_supports_runner(
    *,
    side: int,
    close: float,
    crossed_poc: float,
    zone_half_width: float,
    state: pd.Series,
    signal_developing_poc: float,
) -> bool:
    outside_value = (
        close > crossed_poc + zone_half_width
        if side > 0 else close < crossed_poc - zone_half_width
    )
    vwap_aligned = close > float(state["session_vwap"]) if side > 0 else close < float(state["session_vwap"])
    poc_not_adverse = side * (float(state["developing_poc"]) - signal_developing_poc) >= 0.0
    return bool(outside_value and vwap_aligned and poc_not_adverse)


def simulate_runner_signals(
    signals: pd.DataFrame,
    bars: pd.DataFrame,
    auction_state: pd.DataFrame,
    execution: NasdaqExecutionCosts,
    config: AsymmetricRunnerConfig,
    *,
    context: str,
    stop_spec: str,
    scratch_bars: int,
    maximum_holding_minutes: int,
    management_spec: str,
) -> pd.DataFrame:
    """Execute causal one-minute signals with conservative intrabar ordering."""
    management = MANAGEMENT_SPECS[management_spec]
    trades: list[dict[str, Any]] = []
    last_exit = pd.Timestamp.min.tz_localize("UTC")
    session_losses: dict[str, int] = {}
    for signal in signals.sort_values("timestamp").itertuples(index=False):
        signal_time = pd.Timestamp(signal.timestamp)
        session_date = str(signal.session_date)
        if signal_time <= last_exit:
            continue
        if session_losses.get(session_date, 0) >= config.maximum_session_losses:
            continue
        entry_id = int(signal.bar_id) + 1
        if entry_id >= len(bars):
            continue
        entry_time = pd.Timestamp(bars.index[entry_id])
        session_close = pd.Timestamp(signal.session_close)
        if entry_time != signal_time + pd.Timedelta(minutes=1) or entry_time >= session_close:
            continue
        if signal_time not in auction_state.index:
            continue
        entry = float(bars.iloc[entry_id]["open"])
        side = int(signal.side)
        distance, micro_distance = _stop_distance(signal, bars, entry, stop_spec, config)
        if not np.isfinite(distance) or distance <= 0.0:
            continue
        stop_fraction = distance / entry
        notional = min(config.leverage_ceiling, config.risk_fraction / stop_fraction)
        risk_deployed = notional * stop_fraction
        active_stop_r = -1.0
        target_r = float(management["final_r"])
        partial_r = management["partial_r"]
        remaining = 1.0
        exit_slices: list[tuple[float, float, pd.Timestamp, str]] = []
        partial_taken = False
        max_favorable_r = -np.inf
        max_adverse_r = -np.inf
        signal_developing_poc = float(auction_state.loc[signal_time, "developing_poc"])
        final_id = min(entry_id + maximum_holding_minutes - 1, len(bars) - 1)
        next_active_stop_r: float | None = None
        for bar_id in range(entry_id, final_id + 1):
            timestamp = pd.Timestamp(bars.index[bar_id])
            if timestamp >= session_close:
                break
            bar = bars.iloc[bar_id]
            favorable_r = (
                (float(bar["high"]) - entry) / distance
                if side > 0 else (entry - float(bar["low"])) / distance
            )
            adverse_r = (
                (entry - float(bar["low"])) / distance
                if side > 0 else (float(bar["high"]) - entry) / distance
            )
            max_favorable_r = max(max_favorable_r, favorable_r)
            max_adverse_r = max(max_adverse_r, adverse_r)
            stop_touched = adverse_r >= abs(active_stop_r) if active_stop_r < 0.0 else favorable_r <= active_stop_r
            if active_stop_r >= 0.0:
                protected_price = entry + side * active_stop_r * distance
                stop_touched = (
                    float(bar["low"]) <= protected_price
                    if side > 0 else float(bar["high"]) >= protected_price
                )
            if stop_touched:
                exit_r = active_stop_r
                exit_price = entry + side * exit_r * distance
                reason = "protected_stop" if active_stop_r >= 0.0 else "stop"
                exit_slices.append((remaining, exit_price, timestamp, reason))
                remaining = 0.0
                break

            took_partial_this_bar = False
            if partial_r is None:
                if favorable_r >= target_r:
                    target_price = entry + side * target_r * distance
                    exit_slices.append((remaining, target_price, timestamp, f"target_{target_r:g}r"))
                    remaining = 0.0
                    break
            elif not partial_taken and favorable_r >= float(partial_r):
                partial_price = entry + side * float(partial_r) * distance
                fraction = min(config.partial_fraction, remaining)
                exit_slices.append((fraction, partial_price, timestamp, "partial_2r"))
                remaining -= fraction
                partial_taken = True
                took_partial_this_bar = True
                if bool(management["protect"]):
                    next_active_stop_r = config.protected_stop_r
            elif partial_taken and favorable_r >= target_r:
                target_price = entry + side * target_r * distance
                exit_slices.append((remaining, target_price, timestamp, f"runner_target_{target_r:g}r"))
                remaining = 0.0
                break

            close = float(bar["close"])
            close_r = side * (close - entry) / distance
            bars_held = bar_id - entry_id + 1
            if remaining > 0.0 and not partial_taken and scratch_bars and bars_held == scratch_bars:
                reclaimed = (
                    close <= float(signal.crossed_poc) + float(signal.zone_half_width)
                    if side > 0 else close >= float(signal.crossed_poc) - float(signal.zone_half_width)
                )
                failed_progress = max_favorable_r < config.scratch_minimum_progress_r and close_r <= 0.0
                if reclaimed or failed_progress:
                    exit_slices.append((remaining, close, timestamp, "failure_scratch"))
                    remaining = 0.0
                    break

            if (
                remaining > 0.0
                and partial_taken
                and bool(management["conditional"])
                and not took_partial_this_bar
            ):
                if timestamp not in auction_state.index or not _auction_supports_runner(
                    side=side,
                    close=close,
                    crossed_poc=float(signal.crossed_poc),
                    zone_half_width=float(signal.zone_half_width),
                    state=auction_state.loc[timestamp],
                    signal_developing_poc=signal_developing_poc,
                ):
                    exit_slices.append((remaining, close, timestamp, "auction_failure"))
                    remaining = 0.0
                    break

            if remaining > 0.0 and (
                bar_id == final_id or timestamp + pd.Timedelta(minutes=1) >= session_close
            ):
                reason = "session_close" if timestamp + pd.Timedelta(minutes=1) >= session_close else "time_exit"
                exit_slices.append((remaining, close, timestamp, reason))
                remaining = 0.0
                break
            if next_active_stop_r is not None:
                active_stop_r = next_active_stop_r
                next_active_stop_r = None

        if remaining > 0.0:
            continue
        realized_price_return = sum(
            fraction * side * (price / entry - 1.0)
            for fraction, price, _, _ in exit_slices
        )
        gross_return = notional * realized_price_return
        execution_cost = 2.0 * notional * execution.one_way_cost_rate
        net_return = gross_return - execution_cost
        gross_r = realized_price_return / stop_fraction
        net_r = net_return / risk_deployed
        exit_time = max(item[2] for item in exit_slices)
        reasons = "+".join(item[3] for item in exit_slices)
        trades.append({
            "signal_time": signal_time,
            "entry_time": entry_time,
            "exit_time": exit_time,
            "session_date": session_date,
            "side": "long" if side > 0 else "short",
            "entry_price": entry,
            "crossed_poc": float(signal.crossed_poc),
            "stop_distance_points": distance,
            "micro_stop_distance_points": micro_distance,
            "stop_fraction": stop_fraction,
            "effective_leverage": notional,
            "risk_fraction_deployed": risk_deployed,
            "gross_r": gross_r,
            "net_r": net_r,
            "gross_return": gross_return,
            "execution_cost": execution_cost,
            "net_return": net_return,
            "maximum_favorable_r": max_favorable_r,
            "maximum_adverse_r": max_adverse_r,
            "exit_reason": reasons,
            "partial_taken": partial_taken,
            "holding_minutes": int((exit_time - entry_time) / pd.Timedelta(minutes=1)) + 1,
            "context": context,
            "stop_spec": stop_spec,
            "scratch_bars": scratch_bars,
            "maximum_holding_minutes": maximum_holding_minutes,
            "management_spec": management_spec,
        })
        last_exit = exit_time
        if net_return < 0.0:
            session_losses[session_date] = session_losses.get(session_date, 0) + 1
    return pd.DataFrame(trades)


def summarize_runner_trades(trades: pd.DataFrame) -> dict[str, Any]:
    if trades.empty:
        return {
            "trades": 0,
            "sessions": 0,
            "win_rate": np.nan,
            "average_net_r": np.nan,
            "average_winner_r": np.nan,
            "average_loser_r": np.nan,
            "winner_loser_ratio": np.nan,
            "net_profit_factor": np.nan,
            "cumulative_net_return": np.nan,
            "max_drawdown": np.nan,
            "break_even_one_way_cost_bps": np.nan,
        }
    frame = trades.sort_values("exit_time")
    net = frame["net_return"].astype(float)
    net_r = frame["net_r"].astype(float)
    winners_r = net_r.loc[net_r > 0.0]
    losers_r = net_r.loc[net_r < 0.0]
    winners = net.loc[net > 0.0]
    losers = net.loc[net < 0.0]
    equity = (1.0 + net).cumprod()
    turnover = 2.0 * frame["effective_leverage"].sum()
    return {
        "trades": int(len(frame)),
        "sessions": int(frame["session_date"].nunique()),
        "win_rate": float(net.gt(0.0).mean()),
        "average_net_r": float(net_r.mean()),
        "median_net_r": float(net_r.median()),
        "average_winner_r": float(winners_r.mean()) if len(winners_r) else np.nan,
        "average_loser_r": float(losers_r.mean()) if len(losers_r) else np.nan,
        "winner_loser_ratio": (
            float(winners_r.mean() / abs(losers_r.mean()))
            if len(winners_r) and len(losers_r) else np.nan
        ),
        "net_profit_factor": (
            float(winners.sum() / abs(losers.sum())) if losers.sum() < 0.0 else np.nan
        ),
        "cumulative_net_return": float(equity.iloc[-1] - 1.0),
        "max_drawdown": float((equity / equity.cummax() - 1.0).min()),
        "average_effective_leverage": float(frame["effective_leverage"].mean()),
        "median_stop_fraction": float(frame["stop_fraction"].median()),
        "average_maximum_favorable_r": float(frame["maximum_favorable_r"].mean()),
        "average_maximum_adverse_r": float(frame["maximum_adverse_r"].mean()),
        "target_exit_rate": float(frame["exit_reason"].str.contains("target").mean()),
        "scratch_exit_rate": float(frame["exit_reason"].str.contains("scratch|auction_failure", regex=True).mean()),
        "stop_exit_rate": float(frame["exit_reason"].str.contains("stop").mean()),
        "partial_rate": float(frame["partial_taken"].mean()),
        "break_even_one_way_cost_bps": (
            float(frame["gross_return"].sum() / turnover * 10_000.0)
            if turnover > 0.0 else np.nan
        ),
    }


def _selection_score(trades: pd.DataFrame, minimum_trades: int) -> float:
    if len(trades) < minimum_trades:
        return -np.inf
    metrics = summarize_runner_trades(trades)
    expectancy = float(metrics["average_net_r"])
    payoff = float(metrics["winner_loser_ratio"])
    drawdown = max(abs(float(metrics["max_drawdown"])), 0.02)
    if not np.isfinite(expectancy) or not np.isfinite(payoff) or expectancy <= 0.0:
        return -np.inf
    breadth = min(1.0, np.sqrt(len(trades) / 40.0))
    return float(expectancy * min(payoff, 3.0) / drawdown * breadth)


def runner_grid(
    observations: pd.DataFrame,
    bars: pd.DataFrame,
    auction_state: pd.DataFrame,
    execution: NasdaqExecutionCosts,
    config: AsymmetricRunnerConfig,
) -> tuple[pd.DataFrame, dict[tuple[Any, ...], pd.DataFrame]]:
    rows: list[dict[str, Any]] = []
    trades_by_key: dict[tuple[Any, ...], pd.DataFrame] = {}
    for context, stop_spec, scratch, holding, management in product(
        config.signal_contexts,
        config.stop_specs,
        config.scratch_bars,
        config.maximum_holding_minutes,
        config.management_specs,
    ):
        signals = observations.loc[signal_context_mask(observations, context)].copy()
        trades = simulate_runner_signals(
            signals,
            bars,
            auction_state,
            execution,
            config,
            context=context,
            stop_spec=stop_spec,
            scratch_bars=scratch,
            maximum_holding_minutes=holding,
            management_spec=management,
        )
        key = (context, stop_spec, scratch, holding, management)
        trades_by_key[key] = trades
        times = (
            pd.to_datetime(trades["entry_time"], utc=True)
            if not trades.empty else pd.Series([], dtype="datetime64[ns, UTC]")
        )
        scopes = {
            "all": trades,
            "development_2024": trades.loc[times < pd.Timestamp("2025-01-01", tz="UTC")],
            "evaluation_2025": trades.loc[times >= pd.Timestamp("2025-01-01", tz="UTC")],
        }
        for scope, frame in scopes.items():
            rows.append({
                "context": context,
                "stop_spec": stop_spec,
                "scratch_bars": scratch,
                "maximum_holding_minutes": holding,
                "management_spec": management,
                "scope": scope,
                "selection_score": _selection_score(frame, config.development_minimum_trades),
            } | summarize_runner_trades(frame))
    return pd.DataFrame(rows), trades_by_key


def target_opportunity_study(
    observations: pd.DataFrame,
    bars: pd.DataFrame,
    config: AsymmetricRunnerConfig,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for context, stop_spec in product(config.signal_contexts, config.stop_specs):
        signals = observations.loc[signal_context_mask(observations, context)]
        outcomes: list[dict[str, Any]] = []
        for signal in signals.itertuples(index=False):
            entry_id = int(signal.bar_id) + 1
            if entry_id >= len(bars):
                continue
            entry_time = pd.Timestamp(bars.index[entry_id])
            if entry_time != pd.Timestamp(signal.timestamp) + pd.Timedelta(minutes=1):
                continue
            entry = float(bars.iloc[entry_id]["open"])
            distance, _ = _stop_distance(signal, bars, entry, stop_spec, config)
            side = int(signal.side)
            session_close = pd.Timestamp(signal.session_close)
            reached = {target: False for target in (2.0, 3.0, 4.0, 6.0)}
            maximum_favorable = 0.0
            stopped = False
            for bar_id in range(entry_id, min(entry_id + 60, len(bars))):
                timestamp = pd.Timestamp(bars.index[bar_id])
                if timestamp >= session_close:
                    break
                bar = bars.iloc[bar_id]
                adverse = (
                    entry - float(bar["low"]) if side > 0 else float(bar["high"]) - entry
                ) / distance
                favorable = (
                    float(bar["high"]) - entry if side > 0 else entry - float(bar["low"])
                ) / distance
                if adverse >= 1.0:
                    stopped = True
                    break
                maximum_favorable = max(maximum_favorable, favorable)
                for target in reached:
                    reached[target] = reached[target] or favorable >= target
            outcomes.append({"mfe_r": maximum_favorable, "stopped": stopped} | {
                f"reached_{target:g}r": value for target, value in reached.items()
            })
        frame = pd.DataFrame(outcomes)
        row: dict[str, Any] = {
            "context": context,
            "stop_spec": stop_spec,
            "events": int(len(frame)),
            "mean_mfe_before_stop_r": float(frame["mfe_r"].mean()) if len(frame) else np.nan,
            "median_mfe_before_stop_r": float(frame["mfe_r"].median()) if len(frame) else np.nan,
            "stop_within_60m_rate": float(frame["stopped"].mean()) if len(frame) else np.nan,
        }
        for target in (2.0, 3.0, 4.0, 6.0):
            row[f"reach_{target:g}r_before_stop_rate"] = (
                float(frame[f"reached_{target:g}r"].mean()) if len(frame) else np.nan
            )
        rows.append(row)
    return pd.DataFrame(rows)


def stability_audit(grid: pd.DataFrame, minimum_trades: int) -> pd.DataFrame:
    keys = ["context", "stop_spec", "scratch_bars", "maximum_holding_minutes", "management_spec"]
    metrics = [
        "trades", "win_rate", "average_net_r", "winner_loser_ratio",
        "net_profit_factor", "cumulative_net_return", "max_drawdown",
        "break_even_one_way_cost_bps",
    ]
    development = grid.loc[grid["scope"].eq("development_2024"), keys + metrics].set_index(keys).add_suffix("_development")
    evaluation = grid.loc[grid["scope"].eq("evaluation_2025"), keys + metrics].set_index(keys).add_suffix("_evaluation")
    audit = development.join(evaluation).reset_index()
    audit["positive_both"] = (
        audit["average_net_r_development"].gt(0.0)
        & audit["average_net_r_evaluation"].gt(0.0)
    )
    audit["payoff_at_least_1_5_both"] = (
        audit["winner_loser_ratio_development"].ge(1.5)
        & audit["winner_loser_ratio_evaluation"].ge(1.5)
    )
    audit["minimum_trades_each"] = audit[["trades_development", "trades_evaluation"]].min(axis=1)
    audit["worst_expectancy_r"] = audit[["average_net_r_development", "average_net_r_evaluation"]].min(axis=1)
    audit["worst_payoff"] = audit[["winner_loser_ratio_development", "winner_loser_ratio_evaluation"]].min(axis=1)
    worst_drawdown = audit[["max_drawdown_development", "max_drawdown_evaluation"]].min(axis=1).abs().clip(lower=0.02)
    audit["diagnostic_score"] = audit["worst_expectancy_r"] * audit["worst_payoff"].clip(upper=3.0) / worst_drawdown
    audit.loc[audit["minimum_trades_each"].lt(minimum_trades), "diagnostic_score"] = np.nan
    audit["uses_evaluation_data"] = True
    return audit.sort_values(
        ["positive_both", "payoff_at_least_1_5_both", "diagnostic_score"],
        ascending=[False, False, False],
        na_position="last",
    ).reset_index(drop=True)


def cost_sensitivity(
    selected: dict[str, tuple[Any, ...]],
    observations: pd.DataFrame,
    bars: pd.DataFrame,
    auction_state: pd.DataFrame,
    config: AsymmetricRunnerConfig,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    rows: list[dict[str, Any]] = []
    baseline_trades: dict[str, pd.DataFrame] = {}
    for label, key in selected.items():
        context, stop_spec, scratch, holding, management = key
        signals = observations.loc[signal_context_mask(observations, context)]
        for cost_bps in config.cost_sensitivity_bps:
            execution = NasdaqExecutionCosts(commission_bps=cost_bps, slippage_bps=0.0)
            trades = simulate_runner_signals(
                signals,
                bars,
                auction_state,
                execution,
                config,
                context=context,
                stop_spec=stop_spec,
                scratch_bars=int(scratch),
                maximum_holding_minutes=int(holding),
                management_spec=management,
            )
            if np.isclose(cost_bps, 0.5):
                baseline_trades[label] = trades
            rows.append({"candidate": label, "one_way_cost_bps": cost_bps} | summarize_runner_trades(trades))
    return pd.DataFrame(rows), baseline_trades


def _equity_path(trades: pd.DataFrame, label: str) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    frame = trades.sort_values("exit_time").copy()
    frame["exit_time"] = pd.to_datetime(frame["exit_time"], utc=True)
    frame["candidate"] = label
    frame["equity"] = (1.0 + frame["net_return"]).cumprod()
    frame["drawdown"] = frame["equity"] / frame["equity"].cummax() - 1.0
    return frame[["candidate", "exit_time", "equity", "drawdown", "net_r"]]


def _plots(
    opportunity: pd.DataFrame,
    stability: pd.DataFrame,
    baseline_trades: dict[str, pd.DataFrame],
    sensitivity: pd.DataFrame,
    output: Path,
) -> list[Path]:
    plt = _configure_plots()
    from matplotlib.ticker import PercentFormatter

    paths: list[Path] = []
    focus = opportunity.loc[opportunity["context"].isin(["migration_rth", "migration_trend_rth"])]
    labels = focus["context"] + "\n" + focus["stop_spec"]
    fig, ax = plt.subplots(figsize=(13, 6))
    positions = np.arange(len(focus))
    width = 0.18
    for offset, target in enumerate((2, 3, 4, 6)):
        ax.bar(
            positions + (offset - 1.5) * width,
            focus[f"reach_{target}r_before_stop_rate"],
            width=width,
            label=f"{target}R",
        )
    ax.set_xticks(positions, labels, rotation=20, ha="right")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set(title="Sixty-minute target reach before a 1R stop", ylabel="Event share")
    ax.legend()
    fig.tight_layout()
    path = output / "target_reach_before_stop.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)

    equity = pd.concat(
        [_equity_path(trades, label) for label, trades in baseline_trades.items()],
        ignore_index=True,
    )
    fig, axes = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
    for label, frame in equity.groupby("candidate", sort=True):
        axes[0].plot(frame["exit_time"], frame["equity"] - 1.0, label=label)
        axes[1].plot(frame["exit_time"], frame["drawdown"], label=label)
    axes[0].set_title("Selected one-minute POC payoff candidates")
    axes[0].yaxis.set_major_formatter(PercentFormatter(1.0))
    axes[1].set_title("Drawdown")
    axes[1].yaxis.set_major_formatter(PercentFormatter(1.0))
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    path = output / "selected_equity_and_drawdown.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)

    fig, ax = plt.subplots(figsize=(12, 6))
    for candidate, frame in sensitivity.groupby("candidate", sort=True):
        ax.plot(frame["one_way_cost_bps"], frame["cumulative_net_return"], marker="o", label=candidate)
    ax.axhline(0.0, color="black", linewidth=1.0)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set(title="Asymmetric payoff versus one-way execution cost", xlabel="One-way cost (bps)", ylabel="Cumulative net return")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = output / "runner_cost_sensitivity.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)

    qualifying = stability.loc[
        stability["minimum_trades_each"].ge(20)
        & stability["average_net_r_development"].notna()
        & stability["average_net_r_evaluation"].notna()
    ]
    fig, ax = plt.subplots(figsize=(8, 8))
    colors = qualifying["payoff_at_least_1_5_both"].map({True: "#15803d", False: "#94a3b8"})
    ax.scatter(
        qualifying["average_net_r_development"],
        qualifying["average_net_r_evaluation"],
        c=colors,
        alpha=0.65,
    )
    limits = ax.get_xlim()
    lower = min(limits[0], ax.get_ylim()[0])
    upper = max(limits[1], ax.get_ylim()[1])
    ax.plot([lower, upper], [lower, upper], linestyle="--", color="#475569")
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.axvline(0.0, color="black", linewidth=0.8)
    ax.set(title="Development versus evaluation expectancy", xlabel="2024 average net R", ylabel="2025 average net R")
    fig.tight_layout()
    path = output / "expectancy_stability.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)
    return paths


def _report(
    selected_summary: pd.DataFrame,
    opportunity: pd.DataFrame,
    stable: pd.DataFrame,
    sensitivity: pd.DataFrame,
    bootstrap: pd.DataFrame,
    governance: dict[str, Any],
) -> str:
    stable_columns = [
        "context", "stop_spec", "scratch_bars", "maximum_holding_minutes",
        "management_spec", "trades_development", "average_net_r_development",
        "winner_loser_ratio_development", "cumulative_net_return_development",
        "trades_evaluation", "average_net_r_evaluation",
        "winner_loser_ratio_evaluation", "cumulative_net_return_evaluation",
        "diagnostic_score",
    ]
    cost_view = sensitivity.loc[sensitivity["one_way_cost_bps"].isin([0.5, 1.0, 2.0, 5.0, 15.0]), [
        "candidate", "one_way_cost_bps", "trades", "win_rate", "average_net_r",
        "winner_loser_ratio", "cumulative_net_return", "max_drawdown",
    ]]
    development = selected_summary.loc[
        selected_summary["candidate"].eq("development_selected")
        & selected_summary["scope"].eq("development_2024")
    ].iloc[0]
    evaluation = selected_summary.loc[
        selected_summary["candidate"].eq("development_selected")
        & selected_summary["scope"].eq("evaluation_2025")
    ].iloc[0]
    robust = selected_summary.loc[
        selected_summary["candidate"].eq("migration_conditional_6r")
        & selected_summary["scope"].eq("all")
    ].iloc[0]
    target_reach = opportunity.loc[
        opportunity["context"].eq("migration_rth")
        & opportunity["stop_spec"].eq("micro_3bar")
    ].iloc[0]
    binance_cost = float(governance["binance_execution"]["all_in_trade_cost_bps"])
    binance_stress = sensitivity.loc[
        sensitivity["candidate"].eq("migration_conditional_6r")
        & sensitivity["one_way_cost_bps"].eq(binance_cost)
    ].iloc[0]
    return f"""# One-Minute POC Asymmetric-Payoff Study

Generated {governance['generated_at_utc']}.

## Decision summary

- The mechanically optimized 2024 winner is rejected: it made {development['cumulative_net_return']:.2%} in development but lost {evaluation['cumulative_net_return']:.2%} in 2025. This is direct evidence of selection overfit.
- The broad, simpler migration runner is the best candidate for paper testing, not live trading: {int(robust['trades'])} trades, {robust['win_rate']:.1%} wins, {robust['average_net_r']:+.3f}R expectancy, {robust['winner_loser_ratio']:.2f} net winner/loser ratio, {robust['cumulative_net_return']:+.2%} compounded return, and {robust['max_drawdown']:.2%} drawdown at the unverified 0.5 bps one-way assumption.
- A 6R outcome is exceptional rather than normal. With migration and the micro stop, {target_reach['reach_2r_before_stop_rate']:.1%} of overlapping events reached 2R before -1R, but only {target_reach['reach_6r_before_stop_rate']:.1%} reached 6R. The framework earns asymmetry through scratches and selective runners, not by forcing every trade to 6R.
- The candidate's break-even one-way cost is about {robust['break_even_one_way_cost_bps']:.2f} bps. At the configured Binance proxy of {binance_cost:.1f} bps one way, the simulated return is {binance_stress['cumulative_net_return']:.2%}. Deployment therefore remains blocked.

## Selected candidate comparison

{_markdown_table(selected_summary, rows=30)}

## Can the signals reach 2R--6R before a 1R stop?

This is an overlapping event diagnostic, not an executable portfolio. Same-bar stop/target ambiguity is resolved as a stop.

{_markdown_table(opportunity, rows=30)}

## Cross-period stability audit

The ranking below uses both years and is diagnostic only. It is not an untouched selection procedure.

{_markdown_table(stable[stable_columns], rows=30)}

## Session-block bootstrap

Intervals resample complete sessions, preserving clustering between trades from the same day.

{_markdown_table(bootstrap, rows=30)}

## Execution-cost sensitivity

{_markdown_table(cost_view, rows=40)}

## Causal management contract

- Context uses only completed prior-session 3d/5d composite POCs, three-session POC migration, prior daily closes, and completed 15-minute ranges.
- Signals require a second one-minute acceptance close and enter only at the next one-minute open.
- `micro_3bar` uses the last three completed one-minute bars plus a 0.05 ATR buffer and a 0.25 ATR disaster floor. Hybrid stops add a one-ATR and 0.25x or 0.50x completed-15-minute range floor.
- Failure scratches occur after one or two complete entry bars when price reclaims the POC zone or never achieves +0.25R and closes non-positive.
- Partial variants exit half at +2R. The conditional runner then protects +0.25R on the remainder and exits if price loses the crossed POC, session VWAP, or causal developing-POC alignment.
- Stops are checked before targets inside each bar. Newly protected stops apply only to subsequent bars.
- Position size is `1% / stop percentage`, capped at 20x. Trading halts after three net losses in a session, and every position exits before the regular-session close.

## Material limitations

- One-minute OHLCV cannot observe footprint delta, queue depletion, stacked imbalance, passive absorption, or tape speed. The developing POC is a causal fixed-width typical-price proxy.
- The CSV's instrument and venue identity remain unverified and inconsistent with CME NQ's quarter-point tick. This is not a Binance execution backtest.
- The grid is adaptive and creates multiple-testing risk. A high 6R reach rate or a strong full-sample curve is not validation.
- The configured Binance cost scenario is shown only as turnover stress on this Nasdaq path. A BTCUSDT implementation requires Binance one-minute and trade-side data.

## Plots

- [Target reach before stop](target_reach_before_stop.png)
- [Selected equity and drawdown](selected_equity_and_drawdown.png)
- [Execution-cost sensitivity](runner_cost_sensitivity.png)
- [Expectancy stability](expectancy_stability.png)
"""


def build_asymmetric_runner_study(
    project_root: str | Path | None = None,
    *,
    data_path: str | Path = DEFAULT_DATA,
    execution_path: str | Path = DEFAULT_EXECUTION,
    binance_execution_path: str | Path = DEFAULT_BINANCE_EXECUTION,
    output_dir: str | Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    data_file = Path(data_path)
    execution_file = Path(execution_path)
    binance_file = Path(binance_execution_path)
    output = Path(output_dir)
    for name, value in (("data", data_file), ("execution", execution_file), ("binance", binance_file)):
        if not value.is_absolute():
            resolved = root / value
            if name == "data":
                data_file = resolved
            elif name == "execution":
                execution_file = resolved
            else:
                binance_file = resolved
    if not output.is_absolute():
        output = root / output
    output.mkdir(parents=True, exist_ok=True)

    config = AsymmetricRunnerConfig()
    execution = load_execution_costs(execution_file)
    binance_execution = load_binance_execution_costs(binance_file)
    bars, data_audit = load_nasdaq_bars(data_file, 1)
    indicated = add_indicators(bars, NasdaqStrategyConfig(bar_minutes=1))
    schedule = build_ny_schedule(indicated.index.min(), indicated.index.max())
    research = MultiTimeframePocConfig()
    daily_context = build_composite_poc_context(indicated, schedule, research)
    blocks = build_fifteen_minute_blocks(indicated, schedule, research)
    _, observations = build_poc_signal_observations(indicated, schedule, daily_context, blocks, research)
    auction_state = build_intraday_auction_state(indicated, schedule, daily_context)

    grid, trades_by_key = runner_grid(observations, indicated, auction_state, execution, config)
    stable = stability_audit(grid, config.development_minimum_trades)
    opportunity = target_opportunity_study(observations, indicated, config)
    development = grid.loc[
        grid["scope"].eq("development_2024")
        & grid["trades"].ge(config.development_minimum_trades)
    ].sort_values("selection_score", ascending=False)
    top_key = tuple(development.iloc[0][[
        "context", "stop_spec", "scratch_bars", "maximum_holding_minutes", "management_spec"
    ]])
    top_key = (top_key[0], top_key[1], int(top_key[2]), int(top_key[3]), top_key[4])
    selected = {
        "development_selected": top_key,
        "stable_5m_base": ("migration_rth", "hybrid_0.50", 0, 5, "full_2r"),
        "asymmetric_30m_2r": ("migration_rth", "hybrid_0.25", 0, 30, "full_2r"),
        "migration_conditional_6r": ("migration_rth", "micro_3bar", 2, 60, "conditional_2r_to_6r"),
        "micro_conditional_6r": ("migration_trend_rth", "micro_3bar", 2, 60, "conditional_2r_to_6r"),
    }
    sensitivity, baseline_trades = cost_sensitivity(
        selected,
        observations,
        indicated,
        auction_state,
        config,
    )
    selected_rows: list[dict[str, Any]] = []
    for label, key in selected.items():
        trades = trades_by_key[key]
        times = pd.to_datetime(trades["entry_time"], utc=True)
        for scope, frame in {
            "all": trades,
            "development_2024": trades.loc[times < pd.Timestamp("2025-01-01", tz="UTC")],
            "evaluation_2025": trades.loc[times >= pd.Timestamp("2025-01-01", tz="UTC")],
        }.items():
            selected_rows.append({"candidate": label, "scope": scope} | summarize_runner_trades(frame))
    selected_summary = pd.DataFrame(selected_rows)
    bootstrap_frames: list[pd.DataFrame] = []
    for label, trades in baseline_trades.items():
        boot = session_bootstrap(trades.assign(setup=label))
        boot = boot.loc[boot["setup"].eq("all")].drop(columns="setup")
        bootstrap_frames.append(boot.assign(candidate=label))
    bootstrap = pd.concat(bootstrap_frames, ignore_index=True)
    plot_paths = _plots(opportunity, stable, baseline_trades, sensitivity, output)
    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "RESEARCH_ONLY",
        "data_file": str(data_file),
        "data_quality": data_audit,
        "execution": execution.to_dict(),
        "binance_execution": binance_execution.to_dict(),
        "config": asdict(config),
        "research_config": asdict(research),
        "selected_candidates": {label: list(key) for label, key in selected.items()},
        "plot_files": [path.name for path in plot_paths],
    }
    configured_binance_cost = float(binance_execution.all_in_trade_cost_bps)
    binance_stress = sensitivity.loc[
        sensitivity["one_way_cost_bps"].eq(configured_binance_cost)
    ]
    deployment_gate = {
        "status": "BLOCKED",
        "reasons": [
            "The Nasdaq CSV venue, contract, price grid, and volume identity are unverified.",
            "Historical bid/ask spreads and market-impact fills are unavailable.",
            "The configured Binance instrument mapping and historical funding are unavailable.",
            "Every selected candidate loses money at the configured Binance all-in one-way cost stress."
            if not binance_stress.empty and binance_stress["cumulative_net_return"].lt(0.0).all()
            else "The Binance execution stress has not established positive net expectancy for every candidate.",
            "A Nasdaq-derived POC signal cannot be transferred to BTCUSDT without a separate Binance one-minute and trade-side backtest.",
        ],
        "configured_binance_one_way_cost_bps": configured_binance_cost,
    }

    grid.to_csv(output / "runner_grid.csv", index=False)
    stable.to_csv(output / "stability_audit.csv", index=False)
    opportunity.to_csv(output / "target_opportunity.csv", index=False)
    selected_summary.to_csv(output / "selected_summary.csv", index=False)
    sensitivity.to_csv(output / "cost_sensitivity.csv", index=False)
    bootstrap.to_csv(output / "bootstrap.csv", index=False)
    pd.concat([_equity_path(trades, label) for label, trades in baseline_trades.items()], ignore_index=True).to_csv(
        output / "selected_equity_curves.csv", index=False
    )
    trades_output = output / "trades"
    trades_output.mkdir(exist_ok=True)
    for label, trades in baseline_trades.items():
        trades.to_csv(trades_output / f"{label}.csv", index=False)
    (output / "governance.json").write_text(json.dumps(governance, indent=2), encoding="utf-8")
    (output / "deployment_gate.json").write_text(json.dumps(deployment_gate, indent=2), encoding="utf-8")
    report = _report(selected_summary, opportunity, stable, sensitivity, bootstrap, governance)
    (output / "report.md").write_text(report, encoding="utf-8")
    return {
        "report_path": output / "report.md",
        "grid": grid,
        "stability": stable,
        "opportunity": opportunity,
        "selected_summary": selected_summary,
        "cost_sensitivity": sensitivity,
        "bootstrap": bootstrap,
        "deployment_gate": deployment_gate,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root")
    parser.add_argument("--data-path", default=str(DEFAULT_DATA))
    parser.add_argument("--execution-path", default=str(DEFAULT_EXECUTION))
    parser.add_argument("--binance-execution-path", default=str(DEFAULT_BINANCE_EXECUTION))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    results = build_asymmetric_runner_study(
        project_root=args.project_root,
        data_path=args.data_path,
        execution_path=args.execution_path,
        binance_execution_path=args.binance_execution_path,
        output_dir=args.output_dir,
    )
    print(f"Report: {results['report_path']}")
    print(results["selected_summary"].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
