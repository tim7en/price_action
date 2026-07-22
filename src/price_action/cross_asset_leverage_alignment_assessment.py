"""Cross-asset leverage, trend-lock, and whipsaw attribution study."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from price_action.data import resolve_project_root
from price_action.nasdaq_fabio_pine_v6_backtest import _markdown_table


DEFAULT_BTC_TRADES = Path(
    "outputs/btc_deepcharts_cost_lock_backtest/trades_cost_aware_profit_lock.csv"
)
DEFAULT_NASDAQ_TRADES = Path(
    "outputs/nasdaq_fabio_cost_lock_backtest/trades_atr_trailing_baseline.csv"
)
DEFAULT_NASDAQ_SCHEDULE = Path("outputs/nasdaq_session_backtest/session_schedule.csv")
DEFAULT_OUTPUT = Path("outputs/cross_asset_leverage_alignment_assessment")
BTC_HOLDOUT_START = pd.Timestamp("2025-01-01", tz="UTC")
NASDAQ_HOLDOUT_START = pd.Timestamp("2025-01-01", tz="UTC")
LEVERAGES = (1.0, 20.0, 40.0)
ASSET_COSTS_BPS = {"btc": 6.0, "nasdaq": 0.50}


def load_trades(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {
        "signal_time",
        "entry_time",
        "exit_time",
        "side",
        "exit_reason",
        "holding_bars",
        "signed_price_return",
        "initial_stop_fraction",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Trade file is missing columns: {sorted(missing)}")
    for column in ("signal_time", "entry_time", "exit_time"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="raise")
    return frame.sort_values("entry_time").reset_index(drop=True)


def classify_trade_outcomes(
    trades: pd.DataFrame,
    *,
    one_way_cost_bps: float,
) -> pd.Series:
    net = trades["signed_price_return"] - 2.0 * one_way_cost_bps / 10_000.0
    trend_exit = trades["exit_reason"].str.contains("trailing|target", case=False, na=False)
    static_stop = trades["exit_reason"].str.startswith("static", na=False)
    labels = np.select(
        [
            trend_exit & net.gt(0.0),
            static_stop & trades["holding_bars"].le(3),
            static_stop & trades["holding_bars"].gt(3),
        ],
        ["trend_lock", "fast_whipsaw", "slow_stop_failure"],
        default="other",
    )
    return pd.Series(labels, index=trades.index, name="outcome_bucket")


def fixed_leverage_path(
    trades: pd.DataFrame,
    *,
    leverage: float,
    one_way_cost_bps: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Compound fixed notional leverage; stop if a trade wipes the account."""
    equity = 1.0
    peak = 1.0
    rows: list[dict[str, Any]] = []
    bankruptcy_time: pd.Timestamp | None = None
    for trade in trades.sort_values("entry_time").itertuples(index=False):
        net_unlevered = float(trade.signed_price_return) - 2.0 * one_way_cost_bps / 10_000.0
        net_levered = leverage * net_unlevered
        before = equity
        if net_levered <= -1.0:
            equity = 0.0
            bankruptcy_time = pd.Timestamp(trade.exit_time)
        else:
            equity *= 1.0 + net_levered
        peak = max(peak, equity)
        rows.append(
            {
                "entry_time": trade.entry_time,
                "exit_time": trade.exit_time,
                "session_date": trade.session_date,
                "leverage": leverage,
                "net_unlevered": net_unlevered,
                "net_levered": net_levered,
                "equity_before": before,
                "equity_after": equity,
                "drawdown": equity / peak - 1.0 if peak > 0.0 else -1.0,
                "initial_stop_risk_fraction": leverage * float(trade.initial_stop_fraction),
            }
        )
        if bankruptcy_time is not None:
            break
    path = pd.DataFrame(rows)
    net_returns = path["net_levered"] if not path.empty else pd.Series(dtype=float)
    wins = net_returns.loc[net_returns > 0.0]
    losses = net_returns.loc[net_returns < 0.0]
    terminal = float(equity)
    diagnostics = {
        "trades_available": int(len(trades)),
        "trades_completed_before_ruin": int(len(path)),
        "bankrupt": bankruptcy_time is not None,
        "bankruptcy_time": bankruptcy_time.isoformat() if bankruptcy_time is not None else None,
        "terminal_equity": terminal,
        "cumulative_return": terminal - 1.0,
        "log10_terminal_equity": float(np.log10(terminal)) if terminal > 0.0 else -np.inf,
        "maximum_drawdown": float(path["drawdown"].min()) if not path.empty else 0.0,
        "profit_factor": float(wins.sum() / abs(losses.sum())) if losses.sum() < 0.0 else np.inf,
        "win_rate": float((net_returns > 0.0).mean()) if len(net_returns) else np.nan,
        "average_stop_risk_fraction": float(path["initial_stop_risk_fraction"].mean()) if not path.empty else np.nan,
        "maximum_stop_risk_fraction": float(path["initial_stop_risk_fraction"].max()) if not path.empty else np.nan,
        "stops_risking_at_least_full_equity": int(path["initial_stop_risk_fraction"].ge(1.0).sum()) if not path.empty else 0,
        "round_trip_cost_fraction_per_trade": leverage * 2.0 * one_way_cost_bps / 10_000.0,
    }
    return path, diagnostics


def _cohort_metrics(
    trades: pd.DataFrame,
    mask: pd.Series,
    *,
    one_way_cost_bps: float,
) -> dict[str, Any]:
    selected = trades.loc[mask.fillna(False)].copy()
    if selected.empty:
        return {
            "trades": 0,
            "win_rate": np.nan,
            "profit_factor": np.nan,
            "compounded_return": 0.0,
            "average_net_bps": np.nan,
            "net_contribution_bps": 0.0,
            "trend_lock_rate": np.nan,
            "fast_whipsaw_rate": np.nan,
            "slow_stop_failure_rate": np.nan,
            "average_holding_bars": np.nan,
        }
    net = selected["signed_price_return"] - 2.0 * one_way_cost_bps / 10_000.0
    wins = net.loc[net > 0.0]
    losses = net.loc[net < 0.0]
    outcome = classify_trade_outcomes(selected, one_way_cost_bps=one_way_cost_bps)
    return {
        "trades": int(len(selected)),
        "win_rate": float((net > 0.0).mean()),
        "profit_factor": float(wins.sum() / abs(losses.sum())) if losses.sum() < 0.0 else np.inf,
        "compounded_return": float(np.prod(1.0 + net.to_numpy(dtype=float)) - 1.0),
        "average_net_bps": float(net.mean() * 10_000.0),
        "net_contribution_bps": float(net.sum() * 10_000.0),
        "trend_lock_rate": float(outcome.eq("trend_lock").mean()),
        "fast_whipsaw_rate": float(outcome.eq("fast_whipsaw").mean()),
        "slow_stop_failure_rate": float(outcome.eq("slow_stop_failure").mean()),
        "average_holding_bars": float(selected["holding_bars"].mean()),
    }


def _period_masks(trades: pd.DataFrame, holdout_start: pd.Timestamp) -> dict[str, pd.Series]:
    return {
        "all": pd.Series(True, index=trades.index),
        "development": trades["entry_time"].lt(holdout_start),
        "holdout": trades["entry_time"].ge(holdout_start),
    }


def _development_median(
    trades: pd.DataFrame,
    column: str,
    holdout_start: pd.Timestamp,
) -> float:
    values = trades.loc[trades["entry_time"] < holdout_start, column].replace([np.inf, -np.inf], np.nan).dropna()
    return float(values.median())


def add_btc_alignment_features(trades: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    out = trades.copy()
    out["directional_impulse"] = out["side"] * out["result_atr_proxy"]
    out["directional_close_location"] = out["side"] * out["close_location_proxy"]
    out["ivb_room_atr"] = (
        out["side"] * (out["ivb_target2_proxy"] - out["signal_close"]) / out["signal_atr"]
    )
    out["orb_width_atr"] = out["orb_width_proxy"] / out["signal_atr"]
    session_open = pd.to_datetime(out["session_date"] + " 09:30:00", utc=True)
    out["minutes_from_session_open"] = (
        out["signal_time"] - session_open
    ) / pd.Timedelta(minutes=1)
    thresholds = {
        name: _development_median(out, column, BTC_HOLDOUT_START)
        for name, column in {
            "impulse_median": "directional_impulse",
            "ivb_room_median": "ivb_room_atr",
            "effort_median": "effort_ratio_proxy",
            "orb_width_atr_median": "orb_width_atr",
        }.items()
    }
    return out, thresholds


def add_nasdaq_alignment_features(
    trades: pd.DataFrame,
    schedule: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, float]]:
    out = trades.copy()
    session_opens = schedule.set_index("session_date")["session_open"]
    out["session_open"] = out["session_date"].map(session_opens)
    out["minutes_from_session_open"] = (
        out["signal_time"] - out["session_open"]
    ) / pd.Timedelta(minutes=1)
    out["vwap_distance_atr"] = out["side"] * (out["signal_close"] - out["vwap"]) / out["signal_atr"]
    boundary = np.where(out["side"].gt(0), out["orb_high"], out["orb_low"])
    out["breakout_strength_atr"] = out["side"] * (out["signal_close"] - boundary) / out["signal_atr"]
    out["orb_width_atr"] = (out["orb_high"] - out["orb_low"]) / out["signal_atr"]
    thresholds = {
        name: _development_median(out, column, NASDAQ_HOLDOUT_START)
        for name, column in {
            "breakout_strength_median": "breakout_strength_atr",
            "vwap_distance_median": "vwap_distance_atr",
            "orb_width_atr_median": "orb_width_atr",
        }.items()
    }
    return out, thresholds


def btc_candidate_masks(
    trades: pd.DataFrame,
    thresholds: dict[str, float],
) -> dict[str, pd.Series]:
    strong_impulse = trades["directional_impulse"].ge(thresholds["impulse_median"])
    ample_room = trades["ivb_room_atr"].ge(thresholds["ivb_room_median"])
    high_effort = trades["effort_ratio_proxy"].ge(thresholds["effort_median"])
    delta = trades["delta_aligned_proxy"].astype(bool)
    early = trades["minutes_from_session_open"].le(90.0)
    return {
        "all_primary": pd.Series(True, index=trades.index),
        "delta_confirmed": delta,
        "strong_impulse": strong_impulse,
        "ample_ivb_room": ample_room,
        "high_effort": high_effort,
        "early_90m": early,
        "delta_plus_strong_impulse": delta & strong_impulse,
        "delta_impulse_plus_room": delta & strong_impulse & ample_room,
        "delta_impulse_room_early": delta & strong_impulse & ample_room & early,
        "delta_impulse_room_effort": delta & strong_impulse & ample_room & high_effort,
    }


def nasdaq_candidate_masks(
    trades: pd.DataFrame,
    thresholds: dict[str, float],
) -> dict[str, pd.Series]:
    orb = trades["orb"].astype(bool)
    vwap_aligned = trades["vwap_distance_atr"].gt(0.0)
    strong_breakout = trades["breakout_strength_atr"].ge(
        thresholds["breakout_strength_median"]
    )
    wide_orb = trades["orb_width_atr"].ge(thresholds["orb_width_atr_median"])
    compact_orb = trades["orb_width_atr"].lt(thresholds["orb_width_atr_median"])
    early = trades["minutes_from_session_open"].le(120.0)
    return {
        "all_script": pd.Series(True, index=trades.index),
        "orb_only": orb,
        "vwap_directional": vwap_aligned,
        "strong_breakout": orb & strong_breakout,
        "wide_orb": orb & wide_orb,
        "compact_orb": orb & compact_orb,
        "early_120m": early,
        "orb_plus_vwap": orb & vwap_aligned,
        "orb_vwap_strong_breakout": orb & vwap_aligned & strong_breakout,
        "orb_vwap_breakout_early": orb & vwap_aligned & strong_breakout & early,
    }


def build_candidate_table(
    asset: str,
    trades: pd.DataFrame,
    candidates: dict[str, pd.Series],
    *,
    holdout_start: pd.Timestamp,
    one_way_cost_bps: float,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for period, period_mask in _period_masks(trades, holdout_start).items():
        for name, candidate_mask in candidates.items():
            records.append(
                {"asset": asset, "candidate": name, "period": period}
                | _cohort_metrics(
                    trades,
                    period_mask & candidate_mask,
                    one_way_cost_bps=one_way_cost_bps,
                )
            )
    return pd.DataFrame(records)


def _attribute_masks(
    asset: str,
    trades: pd.DataFrame,
    thresholds: dict[str, float],
) -> dict[str, pd.Series]:
    masks: dict[str, pd.Series] = {
        "side=long": trades["side"].eq(1),
        "side=short": trades["side"].eq(-1),
    }
    if asset == "btc":
        masks.update(
            {
                "delta=aligned": trades["delta_aligned_proxy"].astype(bool),
                "delta=not_aligned": ~trades["delta_aligned_proxy"].astype(bool),
                "session=first_90m": trades["minutes_from_session_open"].le(90.0),
                "session=after_90m": trades["minutes_from_session_open"].gt(90.0),
                "impulse=high": trades["directional_impulse"].ge(thresholds["impulse_median"]),
                "impulse=low": trades["directional_impulse"].lt(thresholds["impulse_median"]),
                "ivb_room=high": trades["ivb_room_atr"].ge(thresholds["ivb_room_median"]),
                "ivb_room=low": trades["ivb_room_atr"].lt(thresholds["ivb_room_median"]),
                "effort=high": trades["effort_ratio_proxy"].ge(thresholds["effort_median"]),
                "effort=low": trades["effort_ratio_proxy"].lt(thresholds["effort_median"]),
                "orb_width=wide": trades["orb_width_atr"].ge(thresholds["orb_width_atr_median"]),
                "orb_width=compact": trades["orb_width_atr"].lt(thresholds["orb_width_atr_median"]),
            }
        )
    else:
        masks.update(
            {
                "setup=orb": trades["orb"].astype(bool),
                "setup=value_area": trades["value_area"].astype(bool),
                "vwap=aligned": trades["vwap_distance_atr"].gt(0.0),
                "vwap=not_aligned": trades["vwap_distance_atr"].le(0.0),
                "session=first_120m": trades["minutes_from_session_open"].le(120.0),
                "session=after_120m": trades["minutes_from_session_open"].gt(120.0),
                "breakout=strong": trades["breakout_strength_atr"].ge(thresholds["breakout_strength_median"]),
                "breakout=weak": trades["breakout_strength_atr"].lt(thresholds["breakout_strength_median"]),
                "orb_width=wide": trades["orb_width_atr"].ge(thresholds["orb_width_atr_median"]),
                "orb_width=compact": trades["orb_width_atr"].lt(thresholds["orb_width_atr_median"]),
            }
        )
    return masks


def build_attribute_table(
    asset: str,
    trades: pd.DataFrame,
    thresholds: dict[str, float],
    *,
    holdout_start: pd.Timestamp,
    one_way_cost_bps: float,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    masks = _attribute_masks(asset, trades, thresholds)
    for period, period_mask in _period_masks(trades, holdout_start).items():
        for name, attribute_mask in masks.items():
            records.append(
                {"asset": asset, "attribute_group": name, "period": period}
                | _cohort_metrics(
                    trades,
                    period_mask & attribute_mask,
                    one_way_cost_bps=one_way_cost_bps,
                )
            )
    return pd.DataFrame(records)


def build_outcome_table(
    asset: str,
    trades: pd.DataFrame,
    *,
    holdout_start: pd.Timestamp,
    one_way_cost_bps: float,
) -> pd.DataFrame:
    outcomes = classify_trade_outcomes(trades, one_way_cost_bps=one_way_cost_bps)
    records: list[dict[str, Any]] = []
    for period, period_mask in _period_masks(trades, holdout_start).items():
        total = int(period_mask.sum())
        for bucket in ("trend_lock", "fast_whipsaw", "slow_stop_failure", "other"):
            mask = period_mask & outcomes.eq(bucket)
            metrics = _cohort_metrics(
                trades, mask, one_way_cost_bps=one_way_cost_bps
            )
            records.append(
                {
                    "asset": asset,
                    "period": period,
                    "outcome_bucket": bucket,
                    "trade_share": metrics["trades"] / total if total else np.nan,
                }
                | metrics
            )
    return pd.DataFrame(records)


def _top_candidate_comparison(candidates: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    minimum = {"btc": 60, "nasdaq": 150}
    baseline = {"btc": "all_primary", "nasdaq": "all_script"}
    for asset in ("btc", "nasdaq"):
        development = candidates.loc[
            (candidates["asset"] == asset)
            & candidates["period"].eq("development")
            & candidates["trades"].ge(minimum[asset])
            & candidates["candidate"].ne(baseline[asset])
        ].sort_values(["profit_factor", "trades"], ascending=[False, False])
        for rank, row in enumerate(development.head(3).itertuples(index=False), start=1):
            holdout = candidates.loc[
                (candidates["asset"] == asset)
                & candidates["period"].eq("holdout")
                & candidates["candidate"].eq(row.candidate)
            ].iloc[0]
            records.append(
                {
                    "asset": asset,
                    "development_rank": rank,
                    "candidate": row.candidate,
                    "development_trades": row.trades,
                    "development_profit_factor": row.profit_factor,
                    "development_average_net_bps": row.average_net_bps,
                    "development_trend_lock_rate": row.trend_lock_rate,
                    "development_fast_whipsaw_rate": row.fast_whipsaw_rate,
                    "holdout_trades": holdout["trades"],
                    "holdout_profit_factor": holdout["profit_factor"],
                    "holdout_average_net_bps": holdout["average_net_bps"],
                    "holdout_trend_lock_rate": holdout["trend_lock_rate"],
                    "holdout_fast_whipsaw_rate": holdout["fast_whipsaw_rate"],
                }
            )
    return pd.DataFrame(records)


def _worst_attribute_comparison(attributes: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    minimum = {"btc": 50, "nasdaq": 100}
    for asset in ("btc", "nasdaq"):
        development = attributes.loc[
            (attributes["asset"] == asset)
            & attributes["period"].eq("development")
            & attributes["trades"].ge(minimum[asset])
        ].sort_values(["average_net_bps", "fast_whipsaw_rate"], ascending=[True, False])
        for rank, row in enumerate(development.head(4).itertuples(index=False), start=1):
            holdout = attributes.loc[
                (attributes["asset"] == asset)
                & attributes["period"].eq("holdout")
                & attributes["attribute_group"].eq(row.attribute_group)
            ].iloc[0]
            records.append(
                {
                    "asset": asset,
                    "development_damage_rank": rank,
                    "attribute_group": row.attribute_group,
                    "development_trades": row.trades,
                    "development_average_net_bps": row.average_net_bps,
                    "development_fast_whipsaw_rate": row.fast_whipsaw_rate,
                    "holdout_trades": holdout["trades"],
                    "holdout_average_net_bps": holdout["average_net_bps"],
                    "holdout_fast_whipsaw_rate": holdout["fast_whipsaw_rate"],
                }
            )
    return pd.DataFrame(records)


def _report(
    leverage: pd.DataFrame,
    top_candidates: pd.DataFrame,
    worst_attributes: pd.DataFrame,
    outcomes: pd.DataFrame,
    thresholds: dict[str, dict[str, float]],
) -> str:
    leverage_view = leverage.loc[
        leverage["period"].isin(["all", "holdout"]),
        [
            "asset",
            "period",
            "leverage",
            "trades_completed_before_ruin",
            "bankrupt",
            "terminal_equity",
            "cumulative_return",
            "maximum_drawdown",
            "average_stop_risk_fraction",
            "maximum_stop_risk_fraction",
            "round_trip_cost_fraction_per_trade",
        ],
    ]
    outcome_view = outcomes.loc[
        outcomes["period"].isin(["all", "holdout"])
        & outcomes["outcome_bucket"].isin(["trend_lock", "fast_whipsaw", "slow_stop_failure"]),
        [
            "asset",
            "period",
            "outcome_bucket",
            "trades",
            "trade_share",
            "average_net_bps",
            "net_contribution_bps",
            "average_holding_bars",
        ],
    ]
    threshold_rows = [
        {"asset": asset, "feature": feature, "development_median": value}
        for asset, values in thresholds.items()
        for feature, value in values.items()
    ]
    return f"""# BTC and NASDAQ leverage/alignment assessment

## Decision

Fixed 20x and 40x leverage multiplies the existing net trade return after the same per-side cost. It does not add a liquidation engine, maintenance margin, funding, contract sizing, or nonlinear slippage, so these are mathematical stress paths rather than executable account forecasts.

## Fixed-leverage paths

{_markdown_table(leverage_view)}

`round_trip_cost_fraction_per_trade` is the equity drag paid on every completed round trip before any price P&L: BTC is 2.4% at 20x and 4.8% at 40x; NASDAQ is 0.2% and 0.4%, respectively.

## Development-selected alignment candidates and untouched holdout

{_markdown_table(top_candidates)}

Candidates are overlapping attribution cohorts, not independently replayed strategies. Ranking uses development PF subject to minimum samples (BTC 60, NASDAQ 150); the holdout columns are never used for selection.

## Trend locks versus damaging failures

{_markdown_table(outcome_view)}

- `trend_lock`: target/trailing exit with positive return after costs.
- `fast_whipsaw`: static-stop exit within three bars.
- `slow_stop_failure`: static-stop exit after more than three bars.

## Development-period damage signatures checked in holdout

{_markdown_table(worst_attributes)}

## Frozen distribution thresholds

{_markdown_table(pd.DataFrame(threshold_rows))}

## Limits

- BTC uses the cost-aware full non-delta proxy at 6 bps per side; NASDAQ uses the original ATR trail at 0.5 bps per side.
- Leverage paths use fixed notional exposure with no dynamic risk reduction. They are intentionally harsh stress tests.
- Alignment cohorts condition executed trades after the fact. Because removing a trade could free later overlapping signals, they are diagnostic and must be broker-replayed before becoming strategy rules.
- BTC lacks verified spot/perpetual identity and funding. NASDAQ identity is unverified and its price grid is inconsistent with CME NQ.
- Five-minute BTC and one-minute NASDAQ bars cannot reveal true order-book sequence or intrabar whipsaw paths.
"""


def build_cross_asset_leverage_alignment_assessment(
    project_root: str | Path | None = None,
    *,
    btc_trades_path: str | Path = DEFAULT_BTC_TRADES,
    nasdaq_trades_path: str | Path = DEFAULT_NASDAQ_TRADES,
    nasdaq_schedule_path: str | Path = DEFAULT_NASDAQ_SCHEDULE,
    output_dir: str | Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)

    def resolved(value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else root / path

    output = resolved(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    btc = load_trades(resolved(btc_trades_path))
    nasdaq = load_trades(resolved(nasdaq_trades_path))
    schedule = pd.read_csv(resolved(nasdaq_schedule_path))
    schedule["session_open"] = pd.to_datetime(schedule["session_open"], utc=True, errors="raise")
    btc, btc_thresholds = add_btc_alignment_features(btc)
    nasdaq, nasdaq_thresholds = add_nasdaq_alignment_features(nasdaq, schedule)

    assets = {
        "btc": (btc, BTC_HOLDOUT_START, ASSET_COSTS_BPS["btc"]),
        "nasdaq": (nasdaq, NASDAQ_HOLDOUT_START, ASSET_COSTS_BPS["nasdaq"]),
    }
    path_frames: list[pd.DataFrame] = []
    leverage_rows: list[dict[str, Any]] = []
    for asset, (trades, holdout_start, cost) in assets.items():
        for period, mask in _period_masks(trades, holdout_start).items():
            scoped = trades.loc[mask].copy()
            for leverage_value in LEVERAGES:
                path, diagnostics = fixed_leverage_path(
                    scoped,
                    leverage=leverage_value,
                    one_way_cost_bps=cost,
                )
                path.insert(0, "asset", asset)
                path.insert(1, "period", period)
                path_frames.append(path)
                leverage_rows.append(
                    {
                        "asset": asset,
                        "period": period,
                        "one_way_cost_bps": cost,
                        "leverage": leverage_value,
                    }
                    | diagnostics
                )
    leverage_summary = pd.DataFrame(leverage_rows)
    leverage_paths = pd.concat(path_frames, ignore_index=True)

    btc_candidates = build_candidate_table(
        "btc",
        btc,
        btc_candidate_masks(btc, btc_thresholds),
        holdout_start=BTC_HOLDOUT_START,
        one_way_cost_bps=ASSET_COSTS_BPS["btc"],
    )
    nasdaq_candidates = build_candidate_table(
        "nasdaq",
        nasdaq,
        nasdaq_candidate_masks(nasdaq, nasdaq_thresholds),
        holdout_start=NASDAQ_HOLDOUT_START,
        one_way_cost_bps=ASSET_COSTS_BPS["nasdaq"],
    )
    candidates = pd.concat([btc_candidates, nasdaq_candidates], ignore_index=True)
    top_candidates = _top_candidate_comparison(candidates)

    btc_attributes = build_attribute_table(
        "btc",
        btc,
        btc_thresholds,
        holdout_start=BTC_HOLDOUT_START,
        one_way_cost_bps=ASSET_COSTS_BPS["btc"],
    )
    nasdaq_attributes = build_attribute_table(
        "nasdaq",
        nasdaq,
        nasdaq_thresholds,
        holdout_start=NASDAQ_HOLDOUT_START,
        one_way_cost_bps=ASSET_COSTS_BPS["nasdaq"],
    )
    attributes = pd.concat([btc_attributes, nasdaq_attributes], ignore_index=True)
    worst_attributes = _worst_attribute_comparison(attributes)
    outcomes = pd.concat(
        [
            build_outcome_table(
                "btc",
                btc,
                holdout_start=BTC_HOLDOUT_START,
                one_way_cost_bps=ASSET_COSTS_BPS["btc"],
            ),
            build_outcome_table(
                "nasdaq",
                nasdaq,
                holdout_start=NASDAQ_HOLDOUT_START,
                one_way_cost_bps=ASSET_COSTS_BPS["nasdaq"],
            ),
        ],
        ignore_index=True,
    )
    thresholds = {"btc": btc_thresholds, "nasdaq": nasdaq_thresholds}
    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "RESEARCH_ONLY_FIXED_LEVERAGE_STRESS_TEST",
        "source_trades": {
            "btc": str(resolved(btc_trades_path)),
            "nasdaq": str(resolved(nasdaq_trades_path)),
        },
        "costs_bps_per_side": ASSET_COSTS_BPS,
        "leverages": LEVERAGES,
        "holdout_start": "2025-01-01T00:00:00+00:00",
        "thresholds_from_development_distribution_only": thresholds,
        "trend_lock_definition": "positive after-cost target or trailing exit",
        "fast_whipsaw_definition": "static-stop exit within three bars",
        "leverage_limitations": [
            "fixed notional multiplication",
            "no maintenance-margin or liquidation-price model",
            "no funding",
            "no nonlinear slippage",
        ],
    }
    leverage_summary.to_csv(output / "leverage_summary.csv", index=False)
    leverage_paths.to_csv(output / "leverage_paths.csv", index=False)
    candidates.to_csv(output / "alignment_candidates.csv", index=False)
    top_candidates.to_csv(output / "top_alignment_holdout.csv", index=False)
    attributes.to_csv(output / "attribute_diagnostics.csv", index=False)
    worst_attributes.to_csv(output / "worst_attribute_holdout.csv", index=False)
    outcomes.to_csv(output / "outcome_attribution.csv", index=False)
    (output / "governance.json").write_text(json.dumps(governance, indent=2), encoding="utf-8")
    report = _report(
        leverage_summary,
        top_candidates,
        worst_attributes,
        outcomes,
        thresholds,
    )
    report_path = output / "report.md"
    report_path.write_text(report, encoding="utf-8")
    return {
        "report_path": report_path,
        "leverage": leverage_summary,
        "candidates": candidates,
        "top_candidates": top_candidates,
        "attributes": attributes,
        "worst_attributes": worst_attributes,
        "outcomes": outcomes,
        "governance": governance,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root")
    parser.add_argument("--btc-trades-path", default=str(DEFAULT_BTC_TRADES))
    parser.add_argument("--nasdaq-trades-path", default=str(DEFAULT_NASDAQ_TRADES))
    parser.add_argument("--nasdaq-schedule-path", default=str(DEFAULT_NASDAQ_SCHEDULE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_cross_asset_leverage_alignment_assessment(
        project_root=args.project_root,
        btc_trades_path=args.btc_trades_path,
        nasdaq_trades_path=args.nasdaq_trades_path,
        nasdaq_schedule_path=args.nasdaq_schedule_path,
        output_dir=args.output_dir,
    )
    print(f"Report: {result['report_path']}")
    print(
        result["leverage"].loc[
            result["leverage"]["period"].isin(["all", "holdout"])
        ].to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
