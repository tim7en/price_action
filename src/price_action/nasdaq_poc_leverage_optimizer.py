"""Session-only POC stop/timeline optimizer and leverage survival stress test.

The optimizer separates account leverage settings from effective position
leverage.  Its causal signals use prior-session POCs, completed 15-minute
structure, and next-minute execution.  Fixed 20x/40x/100x tests deliberately
model full account-level notional and are stress cases, not recommendations.
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
)


DEFAULT_OUTPUT = Path("outputs/nasdaq_poc_leverage_optimizer")
DEFAULT_BINANCE_EXECUTION = Path("config/binance_session_scalper_execution.json")

# This is a post-study stability candidate, not an untouched out-of-sample rule.
# Keeping it explicit prevents a future forward test from silently changing the
# specification after every attractive backtest cell.
STABILITY_CANDIDATE: dict[str, Any] = {
    "poc_scope": "3d_or_5d",
    "timeline": "rth_15_330m",
    "context": "poc_migration",
    "stop_factor_15m": 0.50,
    "holding_minutes": 5,
}


@dataclass(frozen=True)
class PocLeverageOptimizerConfig:
    stop_factors_15m: tuple[float, ...] = (0.0, 0.25, 0.50, 0.75, 1.00, 1.25)
    holding_minutes: tuple[int, ...] = (5, 10, 15, 30)
    poc_scopes: tuple[str, ...] = ("3d_or_5d", "focus_cluster")
    timelines: tuple[str, ...] = ("opening_15_30m", "postopen_30_45m", "rth_15_330m")
    contexts: tuple[str, ...] = (
        "none",
        "poc_migration",
        "trend_3d_10d",
        "trend_3d_10d_plus_migration",
        "trend_10d_30d",
    )
    risk_fraction: float = 0.01
    max_effective_leverage: float = 100.0
    fixed_leverage_levels: tuple[float, ...] = (20.0, 40.0, 100.0)
    maintenance_margin_proxy: float = 0.005
    max_session_losses: int = 3
    minimum_training_trades: int = 20
    bootstrap_samples: int = 20_000
    bootstrap_years: tuple[int, ...] = (1, 3)
    survival_equity_floors: tuple[float, ...] = (0.50, 0.20, 0.05)
    cost_sensitivity_bps: tuple[float, ...] = (0.5, 1.0, 2.0, 5.0, 10.0)

    def __post_init__(self) -> None:
        if not 0.0 < self.risk_fraction <= 0.05:
            raise ValueError("Risk fraction must be inside (0, 5%]")
        if min(self.fixed_leverage_levels) <= 1.0:
            raise ValueError("Fixed leverage stress levels must exceed one")
        if not 0.0 <= self.maintenance_margin_proxy < 0.02:
            raise ValueError("Maintenance-margin proxy must be inside [0, 2%)")
        if self.bootstrap_samples < 1_000:
            raise ValueError("At least 1,000 bootstrap samples are required")


def _signal_mask(
    observations: pd.DataFrame,
    poc_scope: str,
    timeline: str,
    context: str,
) -> pd.Series:
    mask = observations["mode"].eq("one_minute_acceptance")
    mask &= observations["completed_15m_range"].notna()
    if poc_scope == "3d_or_5d":
        mask &= observations["crossed_sources"].str.contains("3d|5d", regex=True)
    elif poc_scope == "focus_cluster":
        mask &= observations["focus_cluster_count"].ge(2)
    else:
        raise ValueError(f"Unknown POC scope: {poc_scope}")

    minute = observations["minutes_from_open"]
    if timeline == "opening_15_30m":
        mask &= minute.ge(15) & minute.lt(30)
    elif timeline == "postopen_30_45m":
        mask &= minute.ge(30) & minute.lt(45)
    elif timeline == "rth_15_330m":
        mask &= minute.ge(15) & minute.lt(330)
    else:
        raise ValueError(f"Unknown timeline: {timeline}")

    if context == "poc_migration":
        mask &= observations["daily_poc_migration_aligned"]
    elif context == "trend_3d_10d":
        mask &= observations["trend_3d_10d_aligned"]
    elif context == "trend_3d_10d_plus_migration":
        mask &= observations["trend_3d_10d_aligned"]
        mask &= observations["daily_poc_migration_aligned"]
    elif context == "trend_10d_30d":
        mask &= observations["trend_10d_30d_aligned"]
    elif context != "none":
        raise ValueError(f"Unknown context: {context}")
    return mask


def _simulate_signals(
    signals: pd.DataFrame,
    bars: pd.DataFrame,
    execution: NasdaqExecutionCosts,
    *,
    stop_factor: float,
    holding_minutes: int,
    sizing_mode: str,
    risk_fraction: float,
    leverage: float,
    maintenance_margin_proxy: float,
    max_session_losses: int,
) -> pd.DataFrame:
    """Simulate next-minute entries with no overlap and no overnight exposure."""
    trades: list[dict[str, Any]] = []
    last_exit = pd.Timestamp.min.tz_localize("UTC")
    losses: dict[str, int] = {}
    for signal in signals.sort_values("timestamp").itertuples(index=False):
        timestamp = pd.Timestamp(signal.timestamp)
        session_date = str(signal.session_date)
        if timestamp <= last_exit or losses.get(session_date, 0) >= max_session_losses:
            continue
        entry_id = int(signal.bar_id) + 1
        if entry_id >= len(bars):
            continue
        entry_time = pd.Timestamp(bars.index[entry_id])
        session_close = pd.Timestamp(signal.session_close)
        if entry_time != timestamp + pd.Timedelta(minutes=1) or entry_time >= session_close:
            continue
        entry = float(bars.iloc[entry_id]["open"])
        side = int(signal.side)
        stop_distance = max(
            float(signal.atr),
            stop_factor * float(signal.completed_15m_range),
        )
        if not np.isfinite(stop_distance) or stop_distance <= 0.0:
            continue
        stop_fraction = stop_distance / entry
        if sizing_mode == "risk_targeted":
            notional = min(leverage, risk_fraction / stop_fraction)
            liquidation_distance = np.inf
        elif sizing_mode == "fixed_leverage":
            notional = leverage
            liquidation_distance = max(0.0, 1.0 / leverage - maintenance_margin_proxy) * entry
        else:
            raise ValueError(f"Unknown sizing mode: {sizing_mode}")
        stop_price = entry - side * stop_distance
        target_price = entry + side * 2.0 * stop_distance
        final_id = min(entry_id + holding_minutes - 1, len(bars) - 1)
        exit_price = float(bars.iloc[final_id]["close"])
        exit_time = pd.Timestamp(bars.index[final_id])
        exit_reason = "time_exit"
        liquidation = False
        for bar_id in range(entry_id, final_id + 1):
            bar_time = pd.Timestamp(bars.index[bar_id])
            if bar_time >= session_close:
                break
            bar = bars.iloc[bar_id]
            adverse_distance = (
                entry - float(bar["low"])
                if side > 0
                else float(bar["high"]) - entry
            )
            favorable_distance = (
                float(bar["high"]) - entry
                if side > 0
                else entry - float(bar["low"])
            )
            if liquidation_distance <= stop_distance and adverse_distance >= liquidation_distance:
                liquidation = True
                exit_time = bar_time
                exit_reason = "liquidation_proxy"
                break
            if adverse_distance >= stop_distance:
                exit_price = stop_price
                exit_time = bar_time
                exit_reason = "stop"
                break
            if favorable_distance >= 2.0 * stop_distance:
                exit_price = target_price
                exit_time = bar_time
                exit_reason = "target"
                break
            exit_price = float(bar["close"])
            exit_time = bar_time
            exit_reason = "time_exit"
            if bar_time + pd.Timedelta(minutes=1) >= session_close:
                exit_reason = "session_close"
                break
        price_return = side * (exit_price / entry - 1.0)
        if liquidation:
            gross_return = -0.995
            execution_cost = 0.0
            net_return = -0.995
        else:
            gross_return = notional * price_return
            execution_cost = 2.0 * notional * execution.one_way_cost_rate
            net_return = gross_return - execution_cost
        trade = {
            "signal_time": timestamp,
            "entry_time": entry_time,
            "exit_time": exit_time,
            "session_date": session_date,
            "side": "long" if side > 0 else "short",
            "entry_price": entry,
            "exit_price": exit_price,
            "stop_price": stop_price,
            "target_price": target_price,
            "stop_distance_points": stop_distance,
            "stop_fraction": stop_fraction,
            "notional_fraction": notional,
            "effective_leverage": notional,
            "risk_fraction_deployed": notional * stop_fraction,
            "price_return": price_return,
            "gross_return": gross_return,
            "execution_cost": execution_cost,
            "net_return": net_return,
            "exit_reason": exit_reason,
            "holding_minutes": int((exit_time - entry_time) / pd.Timedelta(minutes=1)) + 1,
            "poc_scope": signal.poc_scope,
            "timeline": signal.timeline,
            "context": signal.context,
            "stop_factor_15m": stop_factor,
            "maximum_holding_minutes": holding_minutes,
            "sizing_mode": sizing_mode,
            "leverage_setting": leverage,
        }
        trades.append(trade)
        last_exit = exit_time
        if net_return < 0.0:
            losses[session_date] = losses.get(session_date, 0) + 1
    return pd.DataFrame(trades)


def _performance(trades: pd.DataFrame) -> dict[str, Any]:
    if trades.empty:
        return {
            "trades": 0,
            "sessions": 0,
            "cumulative_net_return": np.nan,
            "max_drawdown": np.nan,
            "net_profit_factor": np.nan,
            "win_rate": np.nan,
            "average_net_return_bps": np.nan,
            "average_effective_leverage": np.nan,
            "median_stop_fraction": np.nan,
            "median_risk_fraction_deployed": np.nan,
            "maximum_risk_fraction_deployed": np.nan,
            "median_planned_stop_loss_with_costs": np.nan,
            "maximum_planned_stop_loss_with_costs": np.nan,
            "liquidations": 0,
        }
    frame = trades.sort_values("exit_time")
    returns = frame["net_return"].astype(float)
    equity = (1.0 + returns).cumprod()
    losses = returns.loc[returns < 0.0]
    return {
        "trades": int(len(frame)),
        "sessions": int(frame["session_date"].nunique()),
        "cumulative_net_return": float(equity.iloc[-1] - 1.0),
        "max_drawdown": float((equity / equity.cummax() - 1.0).min()),
        "net_profit_factor": (
            float(returns.loc[returns > 0.0].sum() / abs(losses.sum()))
            if losses.sum() < 0.0 else np.nan
        ),
        "win_rate": float(returns.gt(0.0).mean()),
        "average_net_return_bps": float(returns.mean() * 10_000.0),
        "average_effective_leverage": float(frame["effective_leverage"].mean()),
        "median_stop_fraction": float(frame["stop_fraction"].median()),
        "median_risk_fraction_deployed": float(frame["risk_fraction_deployed"].median()),
        "maximum_risk_fraction_deployed": float(frame["risk_fraction_deployed"].max()),
        "median_planned_stop_loss_with_costs": float(
            (frame["risk_fraction_deployed"] + frame["execution_cost"]).median()
        ),
        "maximum_planned_stop_loss_with_costs": float(
            (frame["risk_fraction_deployed"] + frame["execution_cost"]).max()
        ),
        "liquidations": int(frame["exit_reason"].eq("liquidation_proxy").sum()),
    }


def _selection_score(trades: pd.DataFrame, minimum_trades: int) -> float:
    if len(trades) < minimum_trades:
        return -np.inf
    metrics = _performance(trades)
    if not np.isfinite(metrics["cumulative_net_return"]):
        return -np.inf
    drawdown = max(abs(float(metrics["max_drawdown"])), 0.01)
    breadth = min(1.0, np.sqrt(len(trades) / 30.0))
    return float(metrics["cumulative_net_return"] / drawdown * breadth)


def parameter_grid(
    observations: pd.DataFrame,
    bars: pd.DataFrame,
    execution: NasdaqExecutionCosts,
    config: PocLeverageOptimizerConfig,
) -> tuple[pd.DataFrame, dict[tuple[Any, ...], pd.DataFrame]]:
    rows: list[dict[str, Any]] = []
    trades_by_key: dict[tuple[Any, ...], pd.DataFrame] = {}
    for poc_scope, timeline, context, stop_factor, holding in product(
        config.poc_scopes,
        config.timelines,
        config.contexts,
        config.stop_factors_15m,
        config.holding_minutes,
    ):
        mask = _signal_mask(observations, poc_scope, timeline, context)
        signals = observations.loc[mask].copy()
        signals["poc_scope"] = poc_scope
        signals["timeline"] = timeline
        signals["context"] = context
        trades = _simulate_signals(
            signals,
            bars,
            execution,
            stop_factor=stop_factor,
            holding_minutes=holding,
            sizing_mode="risk_targeted",
            risk_fraction=config.risk_fraction,
            leverage=config.max_effective_leverage,
            maintenance_margin_proxy=config.maintenance_margin_proxy,
            max_session_losses=config.max_session_losses,
        )
        key = (poc_scope, timeline, context, stop_factor, holding)
        trades_by_key[key] = trades
        entry_time = (
            pd.to_datetime(trades["entry_time"], utc=True)
            if not trades.empty else pd.Series([], dtype="datetime64[ns, UTC]")
        )
        scopes = {
            "all": trades,
            "development_2024": trades.loc[entry_time < pd.Timestamp("2025-01-01", tz="UTC")],
            "evaluation_2025": trades.loc[entry_time >= pd.Timestamp("2025-01-01", tz="UTC")],
        }
        for scope, frame in scopes.items():
            metrics = _performance(frame)
            rows.append({
                "poc_scope": poc_scope,
                "timeline": timeline,
                "context": context,
                "stop_factor_15m": stop_factor,
                "holding_minutes": holding,
                "scope": scope,
                "selection_score": _selection_score(frame, config.minimum_training_trades),
            } | metrics)
    return pd.DataFrame(rows), trades_by_key


def parameter_stability_audit(
    grid: pd.DataFrame,
    minimum_trades: int,
) -> pd.DataFrame:
    """Compare 2024 and 2025 without pretending this is a selection holdout.

    The table is a diagnostic for broad parameter plateaus.  Because both
    periods influence its ranking, it must never be labelled out-of-sample.
    """
    keys = [
        "poc_scope",
        "timeline",
        "context",
        "stop_factor_15m",
        "holding_minutes",
    ]
    metrics = [
        "trades",
        "cumulative_net_return",
        "max_drawdown",
        "net_profit_factor",
        "average_effective_leverage",
    ]
    development = (
        grid.loc[grid["scope"].eq("development_2024"), keys + metrics]
        .set_index(keys)
        .add_suffix("_development")
    )
    evaluation = (
        grid.loc[grid["scope"].eq("evaluation_2025"), keys + metrics]
        .set_index(keys)
        .add_suffix("_evaluation")
    )
    audit = development.join(evaluation, how="inner").reset_index()
    audit["minimum_trades_each_period"] = audit[
        ["trades_development", "trades_evaluation"]
    ].min(axis=1)
    audit["positive_both_periods"] = (
        audit["cumulative_net_return_development"].gt(0.0)
        & audit["cumulative_net_return_evaluation"].gt(0.0)
    )
    audit["worst_period_return"] = audit[
        ["cumulative_net_return_development", "cumulative_net_return_evaluation"]
    ].min(axis=1)
    audit["worst_period_drawdown"] = audit[
        ["max_drawdown_development", "max_drawdown_evaluation"]
    ].min(axis=1)
    denominator = audit["worst_period_drawdown"].abs().clip(lower=0.01)
    audit["diagnostic_stability_score"] = (
        audit["worst_period_return"] / denominator
    )
    audit.loc[
        audit["minimum_trades_each_period"].lt(minimum_trades),
        "diagnostic_stability_score",
    ] = np.nan
    audit["uses_evaluation_data"] = True
    return audit.sort_values(
        ["positive_both_periods", "diagnostic_stability_score"],
        ascending=[False, False],
        na_position="last",
    ).reset_index(drop=True)


def _candidate_signals(
    observations: pd.DataFrame,
    candidate: dict[str, Any] = STABILITY_CANDIDATE,
) -> pd.DataFrame:
    mask = _signal_mask(
        observations,
        str(candidate["poc_scope"]),
        str(candidate["timeline"]),
        str(candidate["context"]),
    )
    signals = observations.loc[mask].copy()
    signals["poc_scope"] = candidate["poc_scope"]
    signals["timeline"] = candidate["timeline"]
    signals["context"] = candidate["context"]
    return signals


def expanding_quarter_walk_forward(
    trades_by_key: dict[tuple[Any, ...], pd.DataFrame],
    config: PocLeverageOptimizerConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    quarters = pd.period_range("2024Q3", "2025Q4", freq="Q")
    selections: list[dict[str, Any]] = []
    oos_trades: list[pd.DataFrame] = []
    for quarter in quarters:
        test_start = pd.Timestamp(quarter.start_time, tz="UTC")
        test_end = pd.Timestamp(quarter.end_time, tz="UTC") + pd.Timedelta(nanoseconds=1)
        best_key: tuple[Any, ...] | None = None
        best_score = -np.inf
        best_train: pd.DataFrame | None = None
        for key, trades in trades_by_key.items():
            if trades.empty:
                continue
            times = pd.to_datetime(trades["entry_time"], utc=True)
            train = trades.loc[times < test_start]
            score = _selection_score(train, config.minimum_training_trades)
            if score > best_score:
                best_key, best_score, best_train = key, score, train
        if best_key is None or best_train is None:
            continue
        chosen = trades_by_key[best_key]
        chosen_times = pd.to_datetime(chosen["entry_time"], utc=True)
        test = chosen.loc[(chosen_times >= test_start) & (chosen_times < test_end)].copy()
        poc_scope, timeline, context, stop_factor, holding = best_key
        selections.append({
            "test_quarter": str(quarter),
            "poc_scope": poc_scope,
            "timeline": timeline,
            "context": context,
            "stop_factor_15m": stop_factor,
            "holding_minutes": holding,
            "training_score": best_score,
            "training_trades": int(len(best_train)),
            "test_trades": int(len(test)),
            "test_return": _performance(test)["cumulative_net_return"],
        })
        if not test.empty:
            test["selection_quarter"] = str(quarter)
            oos_trades.append(test)
    combined = pd.concat(oos_trades, ignore_index=True) if oos_trades else pd.DataFrame()
    return pd.DataFrame(selections), combined


def session_bootstrap_survival(
    trades: pd.DataFrame,
    config: PocLeverageOptimizerConfig,
    *,
    label: str,
) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    data = trades.copy()
    data["entry_time"] = pd.to_datetime(data["entry_time"], utc=True)
    daily = data.groupby("session_date", sort=True)["net_return"].apply(
        lambda values: float((1.0 + values).prod() - 1.0)
    ).to_numpy(dtype=float)
    span_years = max(
        (data["entry_time"].max() - data["entry_time"].min()).days / 365.25,
        0.25,
    )
    sessions_per_year = max(1, int(round(len(daily) / span_years)))
    rng = np.random.default_rng(20260725)
    rows: list[dict[str, Any]] = []
    for years in config.bootstrap_years:
        periods = sessions_per_year * years
        sampled = rng.choice(
            daily,
            size=(config.bootstrap_samples, periods),
            replace=True,
        )
        equity = np.cumprod(1.0 + sampled, axis=1)
        running_peak = np.maximum.accumulate(equity, axis=1)
        drawdown = equity / running_peak - 1.0
        final = equity[:, -1]
        minimum = equity.min(axis=1)
        row: dict[str, Any] = {
            "label": label,
            "years": years,
            "source_sessions": len(daily),
            "simulated_sessions": periods,
            "median_final_equity": float(np.median(final)),
            "final_equity_p05": float(np.quantile(final, 0.05)),
            "final_equity_p95": float(np.quantile(final, 0.95)),
            "probability_finish_profitable": float((final > 1.0).mean()),
            "median_max_drawdown": float(np.median(drawdown.min(axis=1))),
        }
        for floor in config.survival_equity_floors:
            suffix = int(round((1.0 - floor) * 100.0))
            row[f"probability_{suffix}pct_capital_loss"] = float((minimum <= floor).mean())
        rows.append(row)
    return pd.DataFrame(rows)


def _equity_path(trades: pd.DataFrame, label: str) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    frame = trades.sort_values("exit_time").copy()
    frame["exit_time"] = pd.to_datetime(frame["exit_time"], utc=True)
    frame["label"] = label
    frame["equity"] = (1.0 + frame["net_return"]).cumprod()
    frame["drawdown"] = frame["equity"] / frame["equity"].cummax() - 1.0
    return frame[["label", "exit_time", "net_return", "equity", "drawdown"]]


def leverage_stress_test(
    observations: pd.DataFrame,
    bars: pd.DataFrame,
    execution: NasdaqExecutionCosts,
    config: PocLeverageOptimizerConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    signals = _candidate_signals(observations)
    summaries: list[dict[str, Any]] = []
    survival_frames: list[pd.DataFrame] = []
    equity_frames: list[pd.DataFrame] = []
    for sizing_mode, levels in (
        ("risk_targeted", config.fixed_leverage_levels),
        ("fixed_leverage", config.fixed_leverage_levels),
    ):
        for level in levels:
            trades = _simulate_signals(
                signals,
                bars,
                execution,
                stop_factor=float(STABILITY_CANDIDATE["stop_factor_15m"]),
                holding_minutes=int(STABILITY_CANDIDATE["holding_minutes"]),
                sizing_mode=sizing_mode,
                risk_fraction=config.risk_fraction,
                leverage=level,
                maintenance_margin_proxy=config.maintenance_margin_proxy,
                max_session_losses=config.max_session_losses,
            )
            label = f"{sizing_mode}_{int(level)}x"
            summaries.append({
                "label": label,
                "sizing_mode": sizing_mode,
                "leverage_setting": level,
            } | _performance(trades))
            survival_frames.append(
                session_bootstrap_survival(trades, config, label=label)
            )
            equity_frames.append(_equity_path(trades, label))
    return (
        pd.DataFrame(summaries),
        pd.concat(survival_frames, ignore_index=True),
        pd.concat(equity_frames, ignore_index=True),
    )


def execution_cost_sensitivity(
    observations: pd.DataFrame,
    bars: pd.DataFrame,
    config: PocLeverageOptimizerConfig,
    *,
    configured_binance_cost_bps: float,
) -> pd.DataFrame:
    """Stress the locked candidate across one-way cost assumptions.

    The Nasdaq price path and Binance cost proxy are intentionally not treated
    as an investable instrument mapping.  This table answers only whether the
    short-horizon edge is large enough to survive plausible turnover costs.
    """
    signals = _candidate_signals(observations)
    costs = sorted({
        *map(float, config.cost_sensitivity_bps),
        float(configured_binance_cost_bps),
    })
    rows: list[dict[str, Any]] = []
    for one_way_cost_bps in costs:
        execution = NasdaqExecutionCosts(
            commission_bps=one_way_cost_bps,
            slippage_bps=0.0,
            venue_and_contract_verified=False,
            historical_spread_supplied=False,
        )
        for sizing_mode, levels in (
            ("risk_targeted", config.fixed_leverage_levels),
            ("fixed_leverage", config.fixed_leverage_levels),
        ):
            for level in levels:
                trades = _simulate_signals(
                    signals,
                    bars,
                    execution,
                    stop_factor=float(STABILITY_CANDIDATE["stop_factor_15m"]),
                    holding_minutes=int(STABILITY_CANDIDATE["holding_minutes"]),
                    sizing_mode=sizing_mode,
                    risk_fraction=config.risk_fraction,
                    leverage=level,
                    maintenance_margin_proxy=config.maintenance_margin_proxy,
                    max_session_losses=config.max_session_losses,
                )
                rows.append({
                    "one_way_cost_bps": one_way_cost_bps,
                    "configured_binance_proxy": bool(
                        np.isclose(one_way_cost_bps, configured_binance_cost_bps)
                    ),
                    "label": f"{sizing_mode}_{int(level)}x",
                    "sizing_mode": sizing_mode,
                    "leverage_setting": level,
                } | _performance(trades))
    return pd.DataFrame(rows)


def deployment_gate(
    walk_forward_summary: dict[str, Any],
    data_audit: dict[str, Any],
    execution: NasdaqExecutionCosts,
) -> dict[str, Any]:
    reasons: list[str] = []
    if "unverified" in str(data_audit.get("instrument_identity", "")).lower():
        reasons.append("Nasdaq CSV instrument and venue identity are unverified")
    if not execution.venue_and_contract_verified:
        reasons.append("execution venue and contract mapping are unverified")
    if int(walk_forward_summary.get("trades", 0)) < 200:
        reasons.append("fewer than 200 naive walk-forward trades")
    walk_forward_return = float(
        walk_forward_summary.get("cumulative_net_return", np.nan)
    )
    if not np.isfinite(walk_forward_return) or walk_forward_return <= 0.0:
        reasons.append("naive expanding-quarter optimizer lost money out of sample")
    return {
        "status": "BLOCKED" if reasons else "FORWARD_PAPER_TEST_ONLY",
        "reasons": reasons,
        "stability_candidate": STABILITY_CANDIDATE,
        "candidate_selection_warning": (
            "The candidate uses the 2024 and 2025 stability audit and therefore "
            "requires a new untouched forward period."
        ),
        "permitted_next_step": (
            "paper trade the frozen rule with actual venue fees, fills, mark price, "
            "maintenance tiers, and exchange-native stops"
        ),
    }


def _plots(
    grid: pd.DataFrame,
    walk_forward_trades: pd.DataFrame,
    leverage_summary: pd.DataFrame,
    survival: pd.DataFrame,
    leverage_equity: pd.DataFrame,
    cost_sensitivity: pd.DataFrame,
    output: Path,
) -> list[Path]:
    plt = _configure_plots()
    from matplotlib.ticker import PercentFormatter

    paths: list[Path] = []
    reference = grid.loc[
        grid["poc_scope"].eq("3d_or_5d")
        & grid["timeline"].eq("rth_15_330m")
        & grid["context"].eq("poc_migration")
    ]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for axis, scope in zip(axes, ("development_2024", "evaluation_2025"), strict=True):
        pivot = reference.loc[reference["scope"].eq(scope)].pivot(
            index="stop_factor_15m",
            columns="holding_minutes",
            values="cumulative_net_return",
        )
        image = axis.imshow(pivot.to_numpy(), cmap="RdYlGn", aspect="auto")
        axis.set_xticks(range(len(pivot.columns)), pivot.columns)
        axis.set_yticks(range(len(pivot.index)), pivot.index)
        axis.set(xlabel="Maximum holding minutes", ylabel="Stop floor × completed 15m range", title=scope)
        for row in range(len(pivot.index)):
            for column in range(len(pivot.columns)):
                axis.text(column, row, f"{pivot.iloc[row, column]:.1%}", ha="center", va="center", fontsize=8)
        fig.colorbar(image, ax=axis, fraction=0.046)
    fig.suptitle("3d/5d POC + migration: structural-stop and holding-time sensitivity")
    fig.tight_layout()
    path = output / "stop_holding_sensitivity.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)

    fig, ax = plt.subplots(figsize=(12, 6))
    for label, frame in cost_sensitivity.groupby("label", sort=True):
        ax.plot(
            frame["one_way_cost_bps"],
            frame["cumulative_net_return"],
            marker="o",
            linewidth=1.5,
            label=label,
        )
    ax.axhline(0.0, color="black", linewidth=1.0)
    ax.set(
        title="Locked POC candidate: turnover-cost sensitivity",
        xlabel="One-way fee + spread/slippage (bps)",
        ylabel="Historical cumulative net return",
    )
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    path = output / "execution_cost_sensitivity.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)

    fig, axes = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
    for label, frame in leverage_equity.groupby("label", sort=True):
        axes[0].plot(frame["exit_time"], frame["equity"] - 1.0, label=label, linewidth=1.5)
        axes[1].plot(frame["exit_time"], frame["drawdown"], label=label, linewidth=1.3)
    axes[0].set_title("Risk-targeted caps versus fully deployed leverage")
    axes[0].yaxis.set_major_formatter(PercentFormatter(1.0))
    axes[1].set_title("Historical drawdown")
    axes[1].yaxis.set_major_formatter(PercentFormatter(1.0))
    axes[0].legend(fontsize=8, ncol=2)
    fig.tight_layout()
    path = output / "leverage_equity_and_drawdown.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)

    three_year = survival.loc[survival["years"].eq(3)].copy()
    fig, ax = plt.subplots(figsize=(12, 6))
    positions = np.arange(len(three_year))
    ax.bar(positions - 0.18, three_year["probability_50pct_capital_loss"], width=0.36, label="Lose ≥50%")
    ax.bar(positions + 0.18, three_year["probability_80pct_capital_loss"], width=0.36, label="Lose ≥80%")
    ax.set_xticks(positions, three_year["label"], rotation=25, ha="right")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set(title="Three-year session-bootstrap capital impairment", ylabel="Estimated probability")
    ax.legend()
    fig.tight_layout()
    path = output / "leverage_survival_probabilities.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)

    if not walk_forward_trades.empty:
        frame = _equity_path(walk_forward_trades, "quarterly_walk_forward")
        fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
        axes[0].plot(frame["exit_time"], frame["equity"] - 1.0, color="#2563eb")
        axes[1].plot(frame["exit_time"], frame["drawdown"], color="#be123c")
        axes[0].set_title("Expanding-quarter parameter selection: out-of-sample equity")
        axes[0].yaxis.set_major_formatter(PercentFormatter(1.0))
        axes[1].set_title("Drawdown")
        axes[1].yaxis.set_major_formatter(PercentFormatter(1.0))
        fig.tight_layout()
        path = output / "walk_forward_optimizer_equity.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        paths.append(path)
    return paths


def _report(
    top_grid: pd.DataFrame,
    stability: pd.DataFrame,
    selections: pd.DataFrame,
    walk_forward_summary: dict[str, Any],
    leverage_summary: pd.DataFrame,
    survival: pd.DataFrame,
    cost_sensitivity: pd.DataFrame,
    gate: dict[str, Any],
    governance: dict[str, Any],
) -> str:
    stable_columns = [
        "poc_scope",
        "timeline",
        "context",
        "stop_factor_15m",
        "holding_minutes",
        "trades_development",
        "cumulative_net_return_development",
        "max_drawdown_development",
        "trades_evaluation",
        "cumulative_net_return_evaluation",
        "max_drawdown_evaluation",
        "diagnostic_stability_score",
    ]
    stable_view = stability.loc[
        stability["positive_both_periods"]
        & stability["minimum_trades_each_period"].ge(
            governance["optimizer_config"]["minimum_training_trades"]
        ),
        stable_columns,
    ].head(15)
    leverage_columns = [
        "label",
        "trades",
        "cumulative_net_return",
        "max_drawdown",
        "win_rate",
        "average_effective_leverage",
        "median_stop_fraction",
        "median_planned_stop_loss_with_costs",
        "maximum_planned_stop_loss_with_costs",
        "liquidations",
    ]
    binance_cost_view = cost_sensitivity.loc[
        cost_sensitivity["configured_binance_proxy"],
        [
            "one_way_cost_bps",
            "label",
            "trades",
            "cumulative_net_return",
            "max_drawdown",
            "average_effective_leverage",
            "liquidations",
        ],
    ]
    return f"""# Session-Only POC Stop Optimizer and Leverage Survival Study

Generated {governance['generated_at_utc']}.

## Central distinction

An exchange leverage setting is only a ceiling. Under risk-targeted sizing, effective notional is `risk budget / stop distance`, capped by the setting. Fully deploying 20x/40x/100x is a separate stress case that risks leverage multiplied by the stop percentage.

Deployment gate: **{gate['status']}**. Reasons: {'; '.join(gate['reasons'])}.

## Frozen research candidate

The broadest positive parameter plateau was 3d/5d prior-session POC acceptance aligned with three-session POC migration, between 15 and 330 minutes after the New York open, a stop of `max(1m ATR, 0.50 × last completed 15m range)`, and a five-minute maximum hold. This specification was identified using both years and is therefore a post-study candidate for forward paper trading, not a validated production strategy.

{_markdown_table(stable_view, rows=15)}

## Development-selected parameter candidates

{_markdown_table(top_grid, rows=30)}

## Expanding-quarter walk-forward selections

{_markdown_table(selections, rows=20)}

Walk-forward aggregate: `{json.dumps(walk_forward_summary, sort_keys=True)}`

## Historical leverage stress

These results use the frozen research candidate and the Nasdaq study's 0.5 bp one-way cost scenario.

{_markdown_table(leverage_summary[leverage_columns], rows=20)}

## Turnover and Binance-cost stress

The local Binance execution profile assumes {governance['binance_execution']['all_in_trade_cost_bps']:.2f} bps per side (configured fee plus slippage). This is a cost proxy applied to the Nasdaq path, **not** a verified Binance/Nasdaq instrument mapping.

{_markdown_table(binance_cost_view, rows=20)}

The complete sensitivity from 0.5 bps through the configured Binance proxy is in `execution_cost_sensitivity.csv`. The edge changing sign between cost scenarios is a deployment blocker, not a detail to optimize away.

## Session-bootstrap survival estimates

{_markdown_table(survival, rows=30)}

## Plots

- [Stop and holding-time sensitivity](stop_holding_sensitivity.png)
- [Execution-cost sensitivity](execution_cost_sensitivity.png)
- [Risk-targeted versus fixed-leverage equity](leverage_equity_and_drawdown.png)
- [Leverage survival probabilities](leverage_survival_probabilities.png)
- [Walk-forward optimizer equity](walk_forward_optimizer_equity.png)

## Automation contract

- Signals are restricted to the regular New York session and all positions close before the session ends.
- Only completed prior-session profiles and completed 15-minute blocks may influence a signal or stop.
- The research candidate is frozen in code; changing it creates a new model version and requires a new forward test.
- The grid searches POC scope, session timeline, 3d/10d or 10d/30d context, three-session POC migration, stop width, and maximum holding time.
- Parameter selection uses only data before each test quarter. The score is cumulative return divided by drawdown, discounted when fewer than 30 trades are available and rejected below {governance['optimizer_config']['minimum_training_trades']} training trades.
- Risk-targeted variants risk at most {governance['optimizer_config']['risk_fraction']:.2%} before gaps and slippage, regardless of whether the leverage cap is 20x, 40x, or 100x.
- Fixed-leverage stress tests deploy the full account-level notional. They use a simplified liquidation-distance proxy of `1/leverage - {governance['optimizer_config']['maintenance_margin_proxy']:.2%}`; it is not Binance's symbol-, tier-, margin-mode-, or account-specific liquidation calculation.
- Survival probabilities resample complete trading sessions. They are conditional on this short, selected 2024–2025 history and are not real probabilities of future survival.

## Material limitations

- The Nasdaq CSV has unverified venue/contract identity and cannot be treated as executable Binance, CME NQ, or MNQ data.
- Binance fees vary by product, maker/taker status, VIP tier, discounts, and realized slippage. The configured cost is deliberately a scenario, not the user's live fee schedule.
- Historical bars assume stop fills at the stop unless the liquidation proxy is closer. Real gaps, latency, mark-price liquidation, spread widening, rejected orders, and partial fills can make outcomes worse.
- The grid creates substantial multiple-testing risk. The quarterly walk-forward is more relevant than the best full-sample cell, but also has little history.
- A stop-loss order cannot guarantee its intended loss during discontinuous markets. High leverage therefore cannot be made safe merely by placing a stop.
"""


def build_poc_leverage_optimizer(
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

    config = PocLeverageOptimizerConfig()
    execution = load_execution_costs(execution_file)
    bars, data_audit = load_nasdaq_bars(data_file, 1)
    strategy = NasdaqStrategyConfig(bar_minutes=1)
    indicated = add_indicators(bars, strategy)
    schedule = build_ny_schedule(bars.index.min(), bars.index.max())
    research = MultiTimeframePocConfig()
    daily_context = build_composite_poc_context(indicated, schedule, research)
    blocks = build_fifteen_minute_blocks(indicated, schedule, research)
    _, observations = build_poc_signal_observations(
        indicated,
        schedule,
        daily_context,
        blocks,
        research,
    )

    grid, trades_by_key = parameter_grid(observations, indicated, execution, config)
    development = grid.loc[
        grid["scope"].eq("development_2024")
        & grid["trades"].ge(config.minimum_training_trades)
    ].sort_values("selection_score", ascending=False)
    top_development = development.head(10).copy()
    keys = [
        (
            row.poc_scope,
            row.timeline,
            row.context,
            row.stop_factor_15m,
            row.holding_minutes,
        )
        for row in top_development.itertuples(index=False)
    ]
    top_rows: list[pd.DataFrame] = []
    for key in keys:
        match = grid.loc[
            grid["poc_scope"].eq(key[0])
            & grid["timeline"].eq(key[1])
            & grid["context"].eq(key[2])
            & grid["stop_factor_15m"].eq(key[3])
            & grid["holding_minutes"].eq(key[4])
            & grid["scope"].isin(["development_2024", "evaluation_2025"])
        ]
        top_rows.append(match)
    top_grid = pd.concat(top_rows, ignore_index=True) if top_rows else pd.DataFrame()

    selections, walk_forward_trades = expanding_quarter_walk_forward(
        trades_by_key,
        config,
    )
    walk_forward_summary = _performance(walk_forward_trades)
    leverage_summary, survival, leverage_equity = leverage_stress_test(
        observations,
        indicated,
        execution,
        config,
    )
    plot_paths = _plots(
        grid,
        walk_forward_trades,
        leverage_summary,
        survival,
        leverage_equity,
        output,
    )
    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "data_file": str(data_file),
        "data_quality": data_audit,
        "execution": execution.to_dict(),
        "research_config": asdict(research),
        "optimizer_config": asdict(config),
        "plot_files": [path.name for path in plot_paths],
        "status": "RESEARCH_ONLY",
    }
    grid.to_csv(output / "parameter_grid.csv", index=False)
    top_grid.to_csv(output / "top_development_parameters.csv", index=False)
    selections.to_csv(output / "walk_forward_selections.csv", index=False)
    walk_forward_trades.to_csv(output / "walk_forward_trades.csv", index=False)
    leverage_summary.to_csv(output / "leverage_historical_summary.csv", index=False)
    survival.to_csv(output / "leverage_survival_bootstrap.csv", index=False)
    leverage_equity.to_csv(output / "leverage_equity_curves.csv", index=False)
    (output / "governance.json").write_text(json.dumps(governance, indent=2), encoding="utf-8")
    report = _report(
        top_grid,
        selections,
        walk_forward_summary,
        leverage_summary,
        survival,
        governance,
    )
    (output / "report.md").write_text(report, encoding="utf-8")
    return {
        "report_path": output / "report.md",
        "grid": grid,
        "top_grid": top_grid,
        "selections": selections,
        "walk_forward_summary": walk_forward_summary,
        "leverage_summary": leverage_summary,
        "survival": survival,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root")
    parser.add_argument("--data-path", default=str(DEFAULT_DATA))
    parser.add_argument("--execution-path", default=str(DEFAULT_EXECUTION))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    results = build_poc_leverage_optimizer(
        project_root=args.project_root,
        data_path=args.data_path,
        execution_path=args.execution_path,
        output_dir=args.output_dir,
    )
    print(f"Report: {results['report_path']}")
    print(results["leverage_summary"].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
