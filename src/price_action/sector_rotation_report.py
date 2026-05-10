from __future__ import annotations

import argparse
from collections import Counter
import html
import json
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import FuncFormatter

from .data import load_asset_daily, resolve_project_root
from .macro_report import (
    GRID_COLOR,
    MUTED_TEXT_COLOR,
    PAGE_BACKGROUND,
    PANEL_BACKGROUND,
    REGIME_COLORS,
    REPORT_LOOKBACK_YEARS,
    TEXT_COLOR,
    _build_regime_overview,
    _build_sector_rotation_view,
    _confidence_label,
    _format_probability_pct,
    _format_return_pct,
    _format_weight_pct,
    _render_data_table,
    load_model_macro_frame,
)
from .sector_ml import RESERVE_STRATEGY_LABEL, build_sector_ml_view

RESERVE_LEVERAGE_LABEL_PREFIX = f"{RESERVE_STRATEGY_LABEL} x"


def _format_decimal(value: float | int | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{digits}f}"


def _format_turnover(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.1f}/yr"


def _normalised_rank(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.dropna().nunique() <= 1:
        return pd.Series(0.5, index=numeric.index, dtype="float64")
    return numeric.rank(pct=True, method="average").fillna(0.5)


def _build_live_ml_allocation_view(
    sector_rotation_view: dict[str, Any],
    sector_ml_view: dict[str, Any],
) -> dict[str, Any]:
    rotation_view = sector_ml_view.get("holdout_rotation_view") if isinstance(sector_ml_view, dict) else None
    if not sector_rotation_view.get("available") or not sector_ml_view.get("available") or not isinstance(rotation_view, dict):
        return {"available": False, "message": "ML-adjusted allocation is unavailable."}

    current_regime_matrix = sector_rotation_view.get("current_matrix")
    current_signal_frame = rotation_view.get("current_signal_frame")
    validation_quality_frame = sector_ml_view.get("validation_quality_frame")
    sector_summary_frame = sector_ml_view.get("sector_summary_frame")
    if not isinstance(current_regime_matrix, pd.DataFrame) or current_regime_matrix.empty:
        return {"available": False, "message": "Current regime matrix is unavailable."}
    if not isinstance(current_signal_frame, pd.DataFrame) or current_signal_frame.empty:
        return {"available": False, "message": "No latest ML signal was available from the untouched holdout stream."}
    if not isinstance(validation_quality_frame, pd.DataFrame) or validation_quality_frame.empty:
        return {"available": False, "message": "Validation quality metrics are unavailable."}
    if not isinstance(sector_summary_frame, pd.DataFrame) or sector_summary_frame.empty:
        return {"available": False, "message": "Sector ML summary metrics are unavailable."}

    frame = current_regime_matrix.merge(
        current_signal_frame[
            [
                "symbol",
                "ensemble_probability",
                "quality_weighted_score",
                "validation_quality_score",
                "quality_weight",
                "recommended_quality",
            ]
        ],
        on="symbol",
        how="left",
    ).merge(
        sector_summary_frame[
            [
                "symbol",
                "best_overfit_model",
                "best_overfit_stability_score",
                "ensemble_holdout_sharpe",
                "ensemble_holdout_cagr",
            ]
        ],
        on="symbol",
        how="left",
    )

    frame["ensemble_probability"] = pd.to_numeric(frame["ensemble_probability"], errors="coerce").fillna(0.0)
    frame["quality_weighted_score"] = pd.to_numeric(frame["quality_weighted_score"], errors="coerce").fillna(0.0)
    frame["validation_quality_score"] = pd.to_numeric(frame["validation_quality_score"], errors="coerce").fillna(0.5)
    frame["best_overfit_stability_score"] = pd.to_numeric(frame["best_overfit_stability_score"], errors="coerce").fillna(50.0)
    frame["ensemble_holdout_sharpe"] = pd.to_numeric(frame["ensemble_holdout_sharpe"], errors="coerce").fillna(0.0)
    frame["recent_advance_20d"] = pd.to_numeric(frame.get("recent_advance_20d"), errors="coerce")
    frame["recent_advance_60d"] = pd.to_numeric(frame.get("recent_advance_60d"), errors="coerce")
    frame["runup_penalty"] = pd.to_numeric(frame.get("runup_penalty"), errors="coerce").fillna(1.0)

    frame["rank_regime"] = _normalised_rank(frame["entry_score"])
    frame["rank_live_probability"] = _normalised_rank(frame["ensemble_probability"])
    frame["rank_quality_weighted"] = _normalised_rank(frame["quality_weighted_score"])
    frame["rank_validation_quality"] = _normalised_rank(frame["validation_quality_score"])
    frame["rank_stability"] = _normalised_rank(frame["best_overfit_stability_score"])
    frame["rank_holdout_sharpe"] = _normalised_rank(frame["ensemble_holdout_sharpe"])
    frame["rank_runup_headroom"] = _normalised_rank(frame["runup_penalty"])
    frame["combined_live_score"] = (
        0.35 * frame["rank_regime"]
        + 0.18 * frame["rank_live_probability"]
        + 0.13 * frame["rank_quality_weighted"]
        + 0.10 * frame["rank_validation_quality"]
        + 0.09 * frame["rank_stability"]
        + 0.05 * frame["rank_holdout_sharpe"]
        + 0.10 * frame["rank_runup_headroom"]
    )

    threshold = float(sector_ml_view["config"].get("signal_threshold", 0.55))
    candidates = frame.loc[frame["ensemble_probability"] >= threshold].copy()
    if candidates.empty:
        candidates = frame.copy()

    allocation_frame = candidates.sort_values(
        ["combined_live_score", "runup_penalty", "entry_score", "ensemble_probability"],
        ascending=[False, False, False, False],
    ).head(5).copy()
    weight_base = allocation_frame["combined_live_score"] - allocation_frame["combined_live_score"].min() + 0.05
    allocation_frame["sleeve_weight"] = weight_base / weight_base.sum()
    allocation_frame["portfolio_weight"] = allocation_frame["sleeve_weight"] * 0.60
    allocation_frame = allocation_frame.sort_values("portfolio_weight", ascending=False).reset_index(drop=True)
    selected_symbols = set(allocation_frame["symbol"].tolist())
    frame["recommended_live"] = frame["symbol"].isin(selected_symbols)

    return {
        "available": True,
        "signal_date": rotation_view.get("current_signal_date"),
        "message": "This allocation blends the current regime prior with the latest complete ML holdout signal, validation-derived sector quality, and a trailing run-up guardrail so sectors that already advanced sharply into the signal date are less likely to dominate the recommendation.",
        "allocation_frame": allocation_frame,
        "full_frame": frame.sort_values("combined_live_score", ascending=False).reset_index(drop=True),
        "top_pick": allocation_frame.iloc[0].to_dict() if not allocation_frame.empty else None,
    }


def _split_sector_selection(value: Any) -> list[str]:
    if value is None or pd.isna(value):
        return []
    text = str(value).strip()
    if not text or text.lower() == "cash":
        return []
    return [token.strip() for token in text.split(",") if token.strip() and token.strip().lower() != "cash"]


def _build_sector_diagnostics_view(
    project_root: Path,
    sector_ml_view: dict[str, Any],
) -> dict[str, Any]:
    if not sector_ml_view.get("available"):
        return {"available": False, "message": "Sector ML view unavailable."}

    oos_signal_frame = sector_ml_view.get("oos_signal_frame")
    historical_rotation_view = sector_ml_view.get("historical_rotation_view")
    sector_summary_frame = sector_ml_view.get("sector_summary_frame")
    config = sector_ml_view.get("config") or {}
    if not isinstance(oos_signal_frame, pd.DataFrame) or oos_signal_frame.empty:
        return {"available": False, "message": "Historical OOS signal frame unavailable."}
    if not isinstance(historical_rotation_view, dict) or not historical_rotation_view.get("available"):
        return {"available": False, "message": "Historical rotation view unavailable."}
    if not isinstance(sector_summary_frame, pd.DataFrame) or sector_summary_frame.empty:
        return {"available": False, "message": "Sector summary frame unavailable."}

    lookback_bars = int(config.get("label_horizon", 5))
    historical_start = pd.Timestamp(str(config.get("historical_benchmark_start") or "2006-01-01"))
    cost_rate = float(config.get("cost_bps", 0.0)) / 10_000.0
    severe_drop_threshold = -0.05

    signal_frame = oos_signal_frame.copy()
    signal_frame["date"] = pd.to_datetime(signal_frame["date"])
    signal_frame = signal_frame.loc[signal_frame["date"] >= historical_start].copy()
    signal_frame["forward_return"] = pd.to_numeric(signal_frame["forward_return"], errors="coerce")
    signal_frame = signal_frame.dropna(subset=["forward_return"]).reset_index(drop=True)
    signal_frame["net_forward_return"] = signal_frame["forward_return"] - cost_rate

    prior_rows: list[pd.DataFrame] = []
    for symbol in sorted(signal_frame["symbol"].astype(str).unique().tolist()):
        close = pd.to_numeric(load_asset_daily(symbol, project_root=project_root)["close"], errors="coerce")
        prior = (close / close.shift(lookback_bars) - 1.0).rename("prior_return")
        prior_frame = prior.to_frame().reset_index(names="date")
        prior_frame.insert(1, "symbol", symbol)
        prior_rows.append(prior_frame)

    prior_return_frame = pd.concat(prior_rows, ignore_index=True) if prior_rows else pd.DataFrame(columns=["date", "symbol", "prior_return"])
    signal_frame = signal_frame.merge(prior_return_frame, on=["date", "symbol"], how="left")
    signal_frame["drop_flag"] = signal_frame["prior_return"] < 0.0
    signal_frame["severe_drop_flag"] = signal_frame["prior_return"] <= severe_drop_threshold

    summary_lookup = sector_summary_frame[
        ["symbol", "family", "ensemble_oos_cagr", "ensemble_oos_sharpe", "ensemble_holdout_turnover_per_year"]
    ].drop_duplicates(subset=["symbol"])
    signal_frame = signal_frame.merge(summary_lookup, on="symbol", how="left")

    dip_rows: list[dict[str, Any]] = []
    for (symbol, sector_label), group in signal_frame.groupby(["symbol", "sector_label"], dropna=False):
        dip_group = group.loc[group["drop_flag"]].copy()
        severe_group = group.loc[group["severe_drop_flag"]].copy()
        if dip_group.empty:
            continue

        family = str(group["family"].dropna().iloc[0]) if "family" in group and group["family"].notna().any() else "Unknown"
        dip_rows.append(
            {
                "symbol": str(symbol),
                "sector_label": str(sector_label),
                "family": family,
                "all_windows": int(len(group.index)),
                "dip_windows": int(len(dip_group.index)),
                "dip_share": float(len(dip_group.index) / len(group.index)) if len(group.index) else 0.0,
                "avg_prior_return": float(dip_group["prior_return"].mean()),
                "worst_prior_return": float(dip_group["prior_return"].min()),
                "avg_forward_return_after_drop": float(dip_group["net_forward_return"].mean()),
                "median_forward_return_after_drop": float(dip_group["net_forward_return"].median()),
                "hit_rate_after_drop": float((dip_group["net_forward_return"] > 0.0).mean()),
                "compounded_return_after_drop": float((1.0 + dip_group["net_forward_return"]).prod() - 1.0),
                "best_forward_return_after_drop": float(dip_group["net_forward_return"].max()),
                "worst_forward_return_after_drop": float(dip_group["net_forward_return"].min()),
                "severe_drop_windows": int(len(severe_group.index)),
                "avg_forward_return_after_severe_drop": float(severe_group["net_forward_return"].mean()) if not severe_group.empty else None,
                "hit_rate_after_severe_drop": float((severe_group["net_forward_return"] > 0.0).mean()) if not severe_group.empty else None,
                "oos_cagr": float(group["ensemble_oos_cagr"].dropna().iloc[0]) if group["ensemble_oos_cagr"].notna().any() else None,
                "oos_sharpe": float(group["ensemble_oos_sharpe"].dropna().iloc[0]) if group["ensemble_oos_sharpe"].notna().any() else None,
            }
        )

    dip_summary_frame = pd.DataFrame(dip_rows)
    if not dip_summary_frame.empty:
        dip_summary_frame = dip_summary_frame.sort_values(
            ["avg_forward_return_after_drop", "hit_rate_after_drop", "dip_windows"],
            ascending=[False, False, False],
        ).reset_index(drop=True)

    period_log_frame = historical_rotation_view["period_log_frame"].copy().sort_values("signal_date")
    strategy_summary_frame = historical_rotation_view["strategy_summary_frame"].copy()
    benchmark_start = pd.Timestamp(historical_rotation_view["benchmark_start"])
    benchmark_end = pd.Timestamp(historical_rotation_view["benchmark_end"])
    years = max((benchmark_end - benchmark_start).days / 365.25, 1e-9)

    base_strategy_specs = {
        "ML Probability Rotation": {"selection_column": "probability_selection", "return_column": "probability_return"},
        "ML Quality-Weighted Rotation": {"selection_column": "quality_selection", "return_column": "quality_return"},
        RESERVE_STRATEGY_LABEL: {"selection_column": "reserve_asset", "return_column": "reserve_rule_return"},
    }
    rotation_profile_rows: list[dict[str, Any]] = []
    usage_event_rows: list[dict[str, Any]] = []
    symbol_to_sector = (
        sector_summary_frame[["symbol", "sector_label"]].drop_duplicates(subset=["symbol"]).set_index("symbol")["sector_label"].to_dict()
    )

    for strategy_label, spec in base_strategy_specs.items():
        previous_selection: tuple[str, ...] | None = None
        rotation_count = 0
        selection_lengths: list[int] = []
        pattern_counter: Counter[str] = Counter()
        sector_counter: Counter[str] = Counter()
        active_windows = 0
        for row in period_log_frame.itertuples(index=False):
            selections = tuple(_split_sector_selection(getattr(row, spec["selection_column"])))
            selection_lengths.append(len(selections))
            if previous_selection is not None and selections != previous_selection:
                rotation_count += 1
            previous_selection = selections
            selection_label = ", ".join(selections) if selections else "Cash"
            pattern_counter[selection_label] += 1
            if selections:
                active_windows += 1
                strategy_return = float(getattr(row, spec["return_column"]))
                for symbol in selections:
                    sector_counter[symbol] += 1
                    usage_event_rows.append(
                        {
                            "strategy_label": strategy_label,
                            "symbol": symbol,
                            "sector_label": str(symbol_to_sector.get(symbol, symbol)),
                            "signal_date": pd.Timestamp(row.signal_date),
                            "strategy_return": strategy_return,
                            "spy_drawdown_signal": float(row.spy_drawdown_signal),
                        }
                    )

        pattern_label, pattern_count = pattern_counter.most_common(1)[0] if pattern_counter else ("Cash", 0)
        top_sector, top_sector_count = sector_counter.most_common(1)[0] if sector_counter else ("Cash", 0)
        rotation_profile_rows.append(
            {
                "strategy_label": strategy_label,
                "rotation_count": int(rotation_count),
                "rotation_per_year": float(rotation_count / years),
                "avg_selected_count": float(sum(selection_lengths) / len(selection_lengths)) if selection_lengths else 0.0,
                "cash_windows": int(sum(1 for count in selection_lengths if count == 0)),
                "active_windows": int(active_windows),
                "unique_selection_patterns": int(len(pattern_counter)),
                "most_common_selection": pattern_label,
                "most_common_selection_windows": int(pattern_count),
                "most_selected_sector": str(symbol_to_sector.get(top_sector, top_sector)),
                "most_selected_symbol": str(top_sector),
                "most_selected_sector_windows": int(top_sector_count),
            }
        )

    rotation_profile_frame = pd.DataFrame(rotation_profile_rows)
    rotation_profile_lookup = rotation_profile_frame.set_index("strategy_label").to_dict(orient="index") if not rotation_profile_frame.empty else {}

    def _rotation_profile_for_strategy(label: str) -> dict[str, Any]:
        if label.startswith("ML Probability Rotation"):
            return rotation_profile_lookup.get("ML Probability Rotation", {})
        if label.startswith("ML Quality-Weighted Rotation"):
            return rotation_profile_lookup.get("ML Quality-Weighted Rotation", {})
        if label == RESERVE_STRATEGY_LABEL or label.startswith(RESERVE_LEVERAGE_LABEL_PREFIX):
            return rotation_profile_lookup.get(RESERVE_STRATEGY_LABEL, {})
        if label.startswith("SPY Buy And Hold"):
            return {
                "rotation_count": 0,
                "rotation_per_year": 0.0,
                "avg_selected_count": 1.0,
                "cash_windows": 0,
                "active_windows": int(len(period_log_frame.index)),
                "unique_selection_patterns": 1,
                "most_common_selection": "SPY",
                "most_common_selection_windows": int(len(period_log_frame.index)),
                "most_selected_sector": "SPY",
                "most_selected_symbol": "SPY",
                "most_selected_sector_windows": int(len(period_log_frame.index)),
            }
        return {}

    strategy_detail_rows: list[dict[str, Any]] = []
    for row in strategy_summary_frame.itertuples(index=False):
        profile = _rotation_profile_for_strategy(str(row.strategy_label))
        strategy_detail_rows.append(
            {
                "strategy_label": str(row.strategy_label),
                "total_return": float(row.total_return),
                "cagr": float(row.cagr),
                "sharpe": float(row.sharpe),
                "sortino": float(row.sortino) if not pd.isna(row.sortino) else None,
                "max_drawdown": float(row.max_drawdown),
                "hit_rate": float(row.hit_rate),
                "trade_count": int(getattr(row, "trade_count", 0) or 0),
                "period_count": int(getattr(row, "period_count", 0) or 0),
                "entry_count": int(getattr(row, "entry_count", 0) or 0),
                "turnover_per_year": float(getattr(row, "turnover_per_year", 0.0) or 0.0),
                **profile,
            }
        )
    strategy_detail_frame = pd.DataFrame(strategy_detail_rows)

    strategy_usage_frame = pd.DataFrame(usage_event_rows)
    if not strategy_usage_frame.empty:
        usage_summary_frame = (
            strategy_usage_frame.groupby(["strategy_label", "symbol", "sector_label"], dropna=False)
            .agg(
                selected_windows=("signal_date", "count"),
                avg_strategy_return=("strategy_return", "mean"),
                median_strategy_return=("strategy_return", "median"),
                avg_spy_drawdown_signal=("spy_drawdown_signal", "mean"),
                latest_signal_date=("signal_date", "max"),
            )
            .reset_index()
        )
        active_window_lookup = rotation_profile_frame.set_index("strategy_label")["active_windows"].to_dict() if not rotation_profile_frame.empty else {}
        usage_summary_frame["selection_share_active"] = usage_summary_frame.apply(
            lambda row: float(row["selected_windows"] / active_window_lookup.get(str(row["strategy_label"]), 1))
            if active_window_lookup.get(str(row["strategy_label"]), 0)
            else 0.0,
            axis=1,
        )
        usage_summary_frame = usage_summary_frame.sort_values(
            ["strategy_label", "selected_windows", "avg_strategy_return"],
            ascending=[True, False, False],
        ).reset_index(drop=True)
    else:
        usage_summary_frame = pd.DataFrame()

    return {
        "available": True,
        "lookback_bars": lookback_bars,
        "severe_drop_threshold": severe_drop_threshold,
        "dip_summary_frame": dip_summary_frame,
        "rotation_profile_frame": rotation_profile_frame,
        "strategy_detail_frame": strategy_detail_frame,
        "strategy_usage_frame": usage_summary_frame,
        "top_dip_row": dip_summary_frame.iloc[0].to_dict() if not dip_summary_frame.empty else None,
        "top_severe_row": (
            dip_summary_frame.loc[dip_summary_frame["severe_drop_windows"] > 0]
            .sort_values(["avg_forward_return_after_severe_drop", "severe_drop_windows"], ascending=[False, False])
            .iloc[0]
            .to_dict()
            if not dip_summary_frame.empty and (dip_summary_frame["severe_drop_windows"] > 0).any()
            else None
        ),
    }


def _render_equity_curve_chart(period_log_frame: pd.DataFrame, leveraged: bool = False) -> str:
    if period_log_frame.empty:
        return ""

    if leveraged:
        title = "Holdout Equity Curves x3 @ 6% Financing"
        quality_column = "equity_quality_x3"
        probability_column = "equity_probability_x3"
        spy_column = "equity_spy_x3"
        reserve_leverage_column = "equity_reserve_leverage_rule"
        quality_label = "ML quality-weighted x3"
        probability_label = "ML probability-only x3"
        reserve_leverage_label = "Reserve drawdown sleeve x3"
        spy_label = "SPY x3"
    else:
        title = "Holdout Equity Curves"
        quality_column = "equity_quality"
        probability_column = "equity_probability"
        spy_column = "equity_spy"
        reserve_column = "equity_reserve_rule"
        quality_label = "ML quality-weighted"
        probability_label = "ML probability-only"
        reserve_label = "Reserve cash rule"
        spy_label = "SPY"

    plot_columns = ["exit_date", quality_column, probability_column, spy_column]
    if leveraged and reserve_leverage_column in period_log_frame.columns:
        plot_columns.insert(3, reserve_leverage_column)
    if not leveraged:
        plot_columns.insert(3, reserve_column)
    plot_frame = period_log_frame[plot_columns].copy()
    value_columns = [quality_column, probability_column, spy_column]
    if leveraged and reserve_leverage_column in plot_frame.columns:
        value_columns.append(reserve_leverage_column)
    if not leveraged:
        value_columns.append(reserve_column)
    values = plot_frame[value_columns].to_numpy(dtype=float)
    min_value = float(min(values.min(), 1.0))
    max_value = float(max(values.max(), 1.0))
    span = max(max_value - min_value, 1e-9)
    width = 960.0
    height = 280.0
    padding = 24.0

    def points(column: str) -> str:
        coordinates: list[str] = []
        total = max(len(plot_frame.index) - 1, 1)
        for position, value in enumerate(plot_frame[column].astype(float)):
            x = padding + (position / total) * (width - 2 * padding)
            y = height - padding - ((float(value) - min_value) / span) * (height - 2 * padding)
            coordinates.append(f"{x:.1f},{y:.1f}")
        return " ".join(coordinates)

    end_quality = float(plot_frame[quality_column].iloc[-1])
    end_probability = float(plot_frame[probability_column].iloc[-1])
    end_spy = float(plot_frame[spy_column].iloc[-1])
    end_reserve_leverage = float(plot_frame[reserve_leverage_column].iloc[-1]) if leveraged and reserve_leverage_column in plot_frame.columns else None
    end_reserve = float(plot_frame[reserve_column].iloc[-1]) if not leveraged else None
    return f"""
<div class=\"chart-shell\">
  <svg viewBox=\"0 0 960 280\" role=\"img\" aria-label=\"Holdout equity curves\">
    <rect x=\"0\" y=\"0\" width=\"960\" height=\"280\" rx=\"18\" fill=\"rgba(255, 253, 248, 0.92)\"></rect>
        <polyline fill=\"none\" stroke=\"#7a3e2b\" stroke-width=\"4\" points=\"{points(quality_column)}\"></polyline>
        <polyline fill=\"none\" stroke=\"#0f4c5c\" stroke-width=\"3\" stroke-dasharray=\"7 6\" points=\"{points(probability_column)}\"></polyline>
        {f'<polyline fill="none" stroke="#9c6644" stroke-width="3" points="{points(reserve_leverage_column)}"></polyline>' if leveraged and reserve_leverage_column in plot_frame.columns else ''}
        {f'<polyline fill="none" stroke="#2d6a4f" stroke-width="3" points="{points(reserve_column)}"></polyline>' if not leveraged else ''}
        <polyline fill=\"none\" stroke=\"#7d8b99\" stroke-width=\"3\" points=\"{points(spy_column)}\"></polyline>
        <text x=\"28\" y=\"34\" fill=\"#1b2430\" font-size=\"18\" font-family=\"Iowan Old Style, Georgia, serif\">{title}</text>
        <text x=\"28\" y=\"56\" fill=\"#5f6b76\" font-size=\"13\">{quality_label}: {_format_return_pct(end_quality - 1.0)} | {probability_label}: {_format_return_pct(end_probability - 1.0)}{f' | {reserve_leverage_label}: {_format_return_pct(end_reserve_leverage - 1.0)}' if leveraged and end_reserve_leverage is not None else ''}{f' | {reserve_label}: {_format_return_pct(end_reserve - 1.0)}' if not leveraged and end_reserve is not None else ''} | {spy_label}: {_format_return_pct(end_spy - 1.0)}</text>
  </svg>
</div>
"""


def _render_rebalance_tradeoff_chart(sensitivity_frame: pd.DataFrame) -> str:
    if sensitivity_frame.empty:
        return ""

    selected_frame = sensitivity_frame.loc[
        sensitivity_frame["strategy_label"].astype(str).isin(
            [
                "ML Quality-Weighted Rotation",
                RESERVE_STRATEGY_LABEL,
                "SPY Buy And Hold",
            ]
        )
        | sensitivity_frame["strategy_label"].astype(str).str.startswith(RESERVE_LEVERAGE_LABEL_PREFIX)
    ].copy()
    if selected_frame.empty:
        return ""

    colors = {
        "ML Quality-Weighted Rotation": "#7a3e2b",
        RESERVE_STRATEGY_LABEL: "#2d6a4f",
        "SPY Buy And Hold": "#7d8b99",
    }
    reserve_leverage_rows = selected_frame.loc[selected_frame["strategy_label"].astype(str).str.startswith(RESERVE_LEVERAGE_LABEL_PREFIX)]
    reserve_leverage_label = str(reserve_leverage_rows["strategy_label"].iloc[0]) if not reserve_leverage_rows.empty else None
    if reserve_leverage_label is not None:
        colors[reserve_leverage_label] = "#9c6644"

    selected_frame["turnover_per_year"] = pd.to_numeric(selected_frame["turnover_per_year"], errors="coerce").fillna(0.0)
    selected_frame["cagr"] = pd.to_numeric(selected_frame["cagr"], errors="coerce")
    x_min = float(selected_frame["turnover_per_year"].min())
    x_max = float(selected_frame["turnover_per_year"].max())
    y_min = float(min(selected_frame["cagr"].min(), 0.0))
    y_max = float(max(selected_frame["cagr"].max(), 0.0))
    x_span = max(x_max - x_min, 1e-9)
    y_span = max(y_max - y_min, 1e-9)
    width = 960.0
    height = 320.0
    left = 72.0
    right = 24.0
    top = 28.0
    bottom = 42.0

    def x_position(value: float) -> float:
        return left + ((value - x_min) / x_span) * (width - left - right)

    def y_position(value: float) -> float:
        return height - bottom - ((value - y_min) / y_span) * (height - top - bottom)

    legend_items = []
    for label, color in colors.items():
        if label not in set(selected_frame["strategy_label"].astype(str)):
            continue
        legend_items.append(f'<text x="{left + 22 + len(legend_items) * 220:.1f}" y="22" fill="#1b2430" font-size="12">{html.escape(label)}</text><circle cx="{left + 10 + len(legend_items) * 220:.1f}" cy="18" r="5" fill="{color}"></circle>')

    points_markup: list[str] = []
    for row in selected_frame.itertuples(index=False):
        label = str(row.strategy_label)
        color = colors.get(label, "#0f4c5c")
        x = x_position(float(row.turnover_per_year))
        y = y_position(float(row.cagr))
        cadence_text = f"{int(row.cadence_bars)}d"
        points_markup.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{color}"></circle>')
        points_markup.append(f'<text x="{x + 8:.1f}" y="{y - 8:.1f}" fill="#5f6b76" font-size="11">{cadence_text}</text>')

    grid_lines = []
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = top + fraction * (height - top - bottom)
        cagr_value = y_max - fraction * y_span
        grid_lines.append(f'<line x1="{left:.1f}" y1="{y:.1f}" x2="{width - right:.1f}" y2="{y:.1f}" stroke="rgba(125, 139, 153, 0.18)" stroke-width="1"></line>')
        grid_lines.append(f'<text x="12" y="{y + 4:.1f}" fill="#5f6b76" font-size="11">{_format_return_pct(cagr_value)}</text>')

    return """
<div class="chart-shell">
  <svg viewBox="0 0 960 320" role="img" aria-label="Rebalance cadence tradeoff chart">
    <rect x="0" y="0" width="960" height="320" rx="18" fill="rgba(255, 253, 248, 0.92)"></rect>
    {grid}
        <line x1="{left}" y1="{axis_bottom}" x2="{axis_right}" y2="{axis_bottom}" stroke="#b8b1a7" stroke-width="1.2"></line>
        <line x1="{left}" y1="{top}" x2="{left}" y2="{axis_bottom}" stroke="#b8b1a7" stroke-width="1.2"></line>
        <text x="{left}" y="{label_bottom}" fill="#5f6b76" font-size="12">Turnover per year</text>
    <text x="12" y="14" fill="#5f6b76" font-size="12">CAGR</text>
    <text x="{left}" y="304" fill="#5f6b76" font-size="11">Lower-left means low turnover and low CAGR. Upper-left is the efficient corner.</text>
    {legend}
    {points}
  </svg>
</div>
""".format(
        grid="".join(grid_lines),
        left=f"{left:.1f}",
        right=f"{right:.1f}",
        top=f"{top:.1f}",
        bottom=f"{bottom:.1f}",
        width=f"{width:.1f}",
        height=f"{height:.1f}",
        axis_bottom=f"{height - bottom:.1f}",
        axis_right=f"{width - right:.1f}",
        label_bottom=f"{height - 10:.1f}",
        legend="".join(legend_items),
        points="".join(points_markup),
    )


def _render_rebalance_sensitivity_section(sector_ml_view: dict[str, Any]) -> str:
    if not sector_ml_view.get("available"):
        return ""

    sensitivity_frame = sector_ml_view.get("rebalance_sensitivity_frame")
    if not isinstance(sensitivity_frame, pd.DataFrame) or sensitivity_frame.empty:
        return ""

    quality_rows = sensitivity_frame.loc[sensitivity_frame["strategy_label"] == "ML Quality-Weighted Rotation"].copy()
    reserve_rows = sensitivity_frame.loc[sensitivity_frame["strategy_label"] == RESERVE_STRATEGY_LABEL].copy()
    reserve_leverage_rows = sensitivity_frame.loc[
        sensitivity_frame["strategy_label"].astype(str).str.startswith(RESERVE_LEVERAGE_LABEL_PREFIX)
    ].copy()
    spy_rows = sensitivity_frame.loc[sensitivity_frame["strategy_label"] == "SPY Buy And Hold"].copy()

    best_quality = quality_rows.sort_values("sharpe", ascending=False).iloc[0] if not quality_rows.empty else None
    best_reserve = reserve_rows.sort_values("sharpe", ascending=False).iloc[0] if not reserve_rows.empty else None
    lowest_turnover_quality = quality_rows.sort_values("turnover_per_year", ascending=True).iloc[0] if not quality_rows.empty else None
    best_spy = spy_rows.sort_values("cagr", ascending=False).iloc[0] if not spy_rows.empty else None

    cards: list[str] = [
        _render_stat_card(
            title="Cadence overlay, not retraining",
            body="The cadence test reuses the same daily ML signal and only changes execution frequency to 5, 10, or 21 bars. This isolates turnover and holding-period effects without pretending the model was retrained for monthly horizons.",
            tag="Method",
        )
    ]
    if best_quality is not None:
        cards.append(
            _render_stat_card(
                title=f"Quality best at {int(best_quality.cadence_bars)} bars",
                body=(
                    f"Sharpe {_format_decimal(best_quality.sharpe)}, CAGR {_format_return_pct(best_quality.cagr)}, max drawdown {_format_return_pct(best_quality.max_drawdown)}, turnover {_format_turnover(best_quality.turnover_per_year)}."
                ),
                tag="Quality cadence",
            )
        )
    if best_reserve is not None:
        cards.append(
            _render_stat_card(
                title=f"Reserve rule best at {int(best_reserve.cadence_bars)} bars",
                body=(
                    f"Sharpe {_format_decimal(best_reserve.sharpe)}, CAGR {_format_return_pct(best_reserve.cagr)}, max drawdown {_format_return_pct(best_reserve.max_drawdown)}, turnover {_format_turnover(best_reserve.turnover_per_year)}."
                ),
                tag="Reserve cadence",
            )
        )
    if lowest_turnover_quality is not None:
        cards.append(
            _render_stat_card(
                title=f"Lowest-turnover quality cadence: {int(lowest_turnover_quality.cadence_bars)} bars",
                body=(
                    f"Turnover drops to {_format_turnover(lowest_turnover_quality.turnover_per_year)} with CAGR {_format_return_pct(lowest_turnover_quality.cagr)} and max drawdown {_format_return_pct(lowest_turnover_quality.max_drawdown)}."
                ),
                tag="Turnover tradeoff",
            )
        )
    if best_spy is not None:
        cards.append(
            _render_stat_card(
                title=f"SPY strongest at {int(best_spy.cadence_bars)} bars",
                body=(
                    f"CAGR {_format_return_pct(best_spy.cagr)}, Sharpe {_format_decimal(best_spy.sharpe)}, max drawdown {_format_return_pct(best_spy.max_drawdown)}."
                ),
                tag="Benchmark cadence",
            )
        )

    rows: list[tuple[str, ...]] = []
    for row in sensitivity_frame.sort_values(["cadence_bars", "strategy_label"], ascending=[True, True]).itertuples(index=False):
        rows.append(
            (
                str(row.cadence_label),
                str(row.strategy_label),
                _format_return_pct(row.total_return),
                _format_return_pct(row.cagr),
                _format_decimal(row.sharpe),
                _format_return_pct(row.max_drawdown),
                str(int(getattr(row, "trade_count", 0) or 0)),
                str(int(getattr(row, "period_count", 0) or 0)),
                _format_turnover(row.turnover_per_year),
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Execution Sensitivity</p>',
            '  <h2>How 5, 10, And 21-Bar Rebalancing Change The Result</h2>',
            '  <p>This section uses the full 2006-2026 walk-forward history and compares the same sector signal under slower execution cadences. It answers whether lower turnover can preserve enough of the edge to matter in practice.</p>',
            '  <p>Read this section row-by-row within the same cadence. A 5-bar ML result should be compared with the 5-bar SPY benchmark, not with the 21-bar SPY row, because each cadence is a different execution policy and produces a different benchmark path.</p>',
            '  <div class="card-grid">',
            "\n".join(cards),
            '  </div>',
            _render_rebalance_tradeoff_chart(sensitivity_frame),
            _render_data_table(
                headers=(
                    'Cadence',
                    'Strategy',
                    'Total Return',
                    'CAGR',
                    'Sharpe',
                    'Max DD',
                    'Trades',
                    'Windows',
                    'Turnover',
                ),
                rows=rows,
            ),
            '</section>',
        ]
    )


def _render_stat_card(title: str, body: str, tag: str) -> str:
    return "\n".join(
        [
            '<article class="stat-card">',
            f'  <p class="card-tag">{html.escape(tag)}</p>',
            f'  <h3>{html.escape(title)}</h3>',
            f'  <p>{html.escape(body)}</p>',
            '</article>',
        ]
    )


def _render_rotation_hero(
    generated_at: str,
    regime_overview: dict[str, Any],
    sector_rotation_view: dict[str, Any],
) -> str:
    current = regime_overview["current"]
    top_pick = sector_rotation_view.get("top_pick")
    top_pick_text = "n/a"
    if isinstance(top_pick, dict):
        top_pick_text = (
            f"{top_pick['sector_label']} · 1Y { _format_return_pct(float(top_pick['expected_return_12m'])) } · "
            f"confidence { _confidence_label(float(top_pick['confidence_score'])) }"
        )

    return "\n".join(
        [
            '<section class="hero">',
            '  <p class="eyebrow">Sector Rotation Report</p>',
            '  <h1>Macro-Regime Equity Rotation</h1>',
            '  <p>This report isolates the sector rotation layer from the broader macro atlas. It focuses on which equity types have historically held up best, made higher highs most often, and offered the strongest 1-year to 3-year forward return profile inside similar macro regimes.</p>',
            '  <div class="hero-meta">',
            f'    <span>{html.escape(generated_at)}</span>',
            f'    <span>Current regime: {html.escape(str(current["regime_label"]))}</span>',
            f'    <span>Quadrant: {html.escape(str(current["quadrant_label"]))}</span>',
            f'    <span>Cash rule: {html.escape(_format_weight_pct(float(sector_rotation_view["cash_weight"])))}</span>',
            f'    <span>Top entry: {html.escape(top_pick_text)}</span>',
            '  </div>',
            '</section>',
        ]
    )


def _render_overview_section(
    regime_overview: dict[str, Any],
    sector_rotation_view: dict[str, Any],
) -> str:
    current = regime_overview["current"]
    top_pick = sector_rotation_view.get("top_pick")
    defensive_pick = sector_rotation_view.get("defensive_pick")

    cards: list[str] = [
        _render_stat_card(
            title=str(current["regime_label"]),
            body=str(current["macro_narrative"]),
            tag="Current macro regime",
        ),
        _render_stat_card(
            title=str(current["quadrant_label"]),
            body=str(current["quadrant_body"]),
            tag="Growth / inflation quadrant",
        ),
        _render_stat_card(
            title=f"Cash {_format_weight_pct(float(sector_rotation_view['cash_weight']))}",
            body="The cash sleeve is fixed so the model only rotates the 60% equity bucket according to the active regime.",
            tag="Portfolio structure",
        ),
    ]

    if isinstance(top_pick, dict):
        cards.append(
            _render_stat_card(
                title=str(top_pick["sector_label"]),
                body=(
                    f"Expected 1Y {_format_return_pct(float(top_pick['expected_return_12m']))}, expected 3Y {_format_return_pct(float(top_pick['expected_return_36m']))}, "
                    f"higher-high hit rate {_format_probability_pct(float(top_pick['higher_high_rate_12m']))}, confidence {float(top_pick['confidence_score']):.0f}."
                ),
                tag="Most probable entry",
            )
        )

    if isinstance(defensive_pick, dict):
        cards.append(
            _render_stat_card(
                title=str(defensive_pick["sector_label"]),
                body=(
                    f"Defensive sleeve candidate with portfolio weight {_format_weight_pct(float(defensive_pick['portfolio_weight']))} and average future drawdown {_format_return_pct(float(defensive_pick['mean_drawdown_12m']))}."
                ),
                tag="Defensive sleeve",
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Current Outlook</p>',
            '  <h2>What The Rotation Layer Is Saying Now</h2>',
            '  <div class="card-grid">',
            "\n".join(cards),
            '  </div>',
            '</section>',
        ]
    )


def _render_sector_mapping_section(sector_rotation_view: dict[str, Any]) -> str:
    if not sector_rotation_view.get("available"):
        message = str(sector_rotation_view.get("message") or "Sector analytics unavailable.")
        return "\n".join(
            [
                '<section class="section">',
                '  <p class="eyebrow">Sector Map</p>',
                '  <h2>Equity Types</h2>',
                f'  <p>{html.escape(message)}</p>',
                '</section>',
            ]
        )

    cards = []
    for sector in sector_rotation_view["sector_cards"]:
        cards.append(
            "\n".join(
                [
                    '<article class="bucket-card">',
                    f'  <p class="card-tag">{html.escape(sector["symbol"])} · {html.escape(sector["family"])} </p>',
                    f'  <h3>{html.escape(sector["label"])}</h3>',
                    f'  <p>{html.escape(sector["earnings_proxy"])}</p>',
                    f'  <p class="subcopy">{html.escape(sector["role"])}</p>',
                    '</article>',
                ]
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Sector Map</p>',
            '  <h2>The Equity Buckets Scored In This Report</h2>',
            '  <div class="card-grid">',
            "\n".join(cards),
            '  </div>',
            '</section>',
        ]
    )


def _render_allocation_section(sector_rotation_view: dict[str, Any]) -> str:
    if not sector_rotation_view.get("available"):
        return ""

    allocation_rows: list[tuple[str, ...]] = []
    for row in sector_rotation_view["allocation_frame"].itertuples(index=False):
        allocation_rows.append(
            (
                f"{row.sector_label} ({row.symbol})",
                _format_weight_pct(row.sleeve_weight),
                _format_weight_pct(row.portfolio_weight),
                _format_return_pct(row.expected_return_12m),
                _format_return_pct(row.expected_return_36m),
                _format_probability_pct(row.higher_high_rate_12m),
                _format_return_pct(row.mean_drawdown_12m),
                f"{row.confidence_label} ({row.confidence_score:.0f})",
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Allocation</p>',
            '  <h2>Current 40 / 60 Portfolio Construction</h2>',
            '  <p>The allocation below distributes the 60% equity sleeve across the highest-scoring sector buckets under the current regime. The remaining 40% stays in cash by rule.</p>',
            _render_data_table(
                headers=(
                    'Sector',
                    'Sleeve Weight',
                    'Portfolio Weight',
                    'Expected 1Y',
                    'Expected 3Y',
                    'Higher High 12M',
                    'Avg Drawdown 12M',
                    'Confidence',
                ),
                rows=allocation_rows,
            ),
            '</section>',
        ]
    )


def _render_current_matrix_section(sector_rotation_view: dict[str, Any]) -> str:
    if not sector_rotation_view.get("available"):
        return ""

    rows: list[tuple[str, ...]] = []
    for row in sector_rotation_view["current_matrix"].itertuples(index=False):
        rows.append(
            (
                f"{row.sector_label} ({row.symbol})",
                row.family,
                _format_return_pct(row.expected_return_12m),
                _format_return_pct(row.expected_return_36m),
                _format_probability_pct(row.higher_high_rate_12m),
                _format_return_pct(row.mean_drawdown_12m),
                f"{row.confidence_label} ({row.confidence_score:.0f})",
                'Yes' if bool(row.recommended) else 'No',
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Current Regime Matrix</p>',
            '  <h2>All Sector Scores For The Active Regime</h2>',
            _render_data_table(
                headers=(
                    'Sector',
                    'Type',
                    'Expected 1Y',
                    'Expected 3Y',
                    'Higher High 12M',
                    'Avg Drawdown 12M',
                    'Confidence',
                    'Selected',
                ),
                rows=rows,
            ),
            '</section>',
        ]
    )


def _render_regime_behaviour_section(sector_rotation_view: dict[str, Any]) -> str:
    if not sector_rotation_view.get("available"):
        return ""

    cards: list[str] = []
    for item in sector_rotation_view["worst_drawdown_regimes"]:
        cards.append(
            _render_stat_card(
                title=str(item["label"]),
                body=(
                    f"Average sector drawdown {_format_return_pct(float(item['drawdown']))}. "
                    f"Higher-high rate {_format_probability_pct(float(item['higher_high']))}. "
                    f"Least-damaged sectors: {item['top_sectors']}."
                ),
                tag="Worst drawdown regime",
            )
        )

    for item in sector_rotation_view["breakout_regimes"]:
        cards.append(
            _render_stat_card(
                title=str(item["label"]),
                body=(
                    f"Higher-high hit rate {_format_probability_pct(float(item['higher_high']))}. "
                    f"Average drawdown {_format_return_pct(float(item['drawdown']))}. "
                    f"Most frequent leaders: {item['top_sectors']}."
                ),
                tag="Higher-high regime",
            )
        )

    summary_rows: list[tuple[str, ...]] = []
    for row in sector_rotation_view["regime_summary_frame"].sort_values("avg_expected_return_12m", ascending=False).itertuples(index=False):
        summary_rows.append(
            (
                str(row.regime_label),
                _format_return_pct(row.avg_expected_return_12m),
                _format_return_pct(row.avg_expected_return_36m),
                _format_probability_pct(row.avg_higher_high_rate_12m),
                _format_return_pct(row.avg_mean_drawdown_12m),
                f"{float(row.avg_confidence_score):.0f}",
                str(row.top_sectors),
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Regime Behaviour</p>',
            '  <h2>Where Drawdowns Clustered And Where Higher Highs Happened</h2>',
            '  <div class="card-grid">',
            "\n".join(cards),
            '  </div>',
            _render_data_table(
                headers=(
                    'Regime',
                    'Avg 1Y Sector Return',
                    'Avg 3Y Sector Return',
                    'Higher High 12M',
                    'Avg Drawdown 12M',
                    'Avg Confidence',
                    'Frequent Leaders',
                ),
                rows=summary_rows,
            ),
            '</section>',
        ]
    )


def _render_method_section(sector_rotation_view: dict[str, Any]) -> str:
    note = str(sector_rotation_view.get("note") or "")
    missing_symbols = sector_rotation_view.get("missing_symbols") or []
    missing_text = ""
    if missing_symbols:
        missing_text = f" Missing ETF proxies: {', '.join(str(symbol) for symbol in missing_symbols)}."
    body = (
        f"The report reuses the same monthly macro regime engine as the macro atlas, then scores sector ETF proxies by 1-year and 3-year forward returns, future drawdown, and higher-high frequency inside matching regimes. {note}{missing_text}"
    )
    return "\n".join(
        [
            '<section class="section methodology">',
            '  <p class="eyebrow">Method</p>',
            f'  <p>{html.escape(body)}</p>',
            '</section>',
        ]
    )


def _render_live_ml_allocation_section(live_ml_view: dict[str, Any]) -> str:
    if not live_ml_view.get("available"):
        message = str(live_ml_view.get("message") or "ML-adjusted allocation unavailable.")
        return "\n".join(
            [
                '<section class="section">',
                '  <p class="eyebrow">Live Rotation</p>',
                '  <h2>Current ML-Adjusted Rotation</h2>',
                f'  <p>{html.escape(message)}</p>',
                '</section>',
            ]
        )

    signal_date = pd.Timestamp(live_ml_view["signal_date"]).strftime("%Y-%m-%d") if live_ml_view.get("signal_date") is not None else "n/a"
    top_pick = live_ml_view.get("top_pick")
    cards: list[str] = [
        _render_stat_card(
            title=f"Latest complete ML signal: {signal_date}",
            body="The ML leg uses the latest fully labeled holdout signal. The historical benchmark below uses only these untouched holdout dates.",
            tag="Timing",
        ),
    ]
    if isinstance(top_pick, dict):
        cards.append(
            _render_stat_card(
                title=str(top_pick["sector_label"]),
                body=(
                    f"Combined score {_format_decimal(top_pick['combined_live_score'], 3)}, live probability {_format_probability_pct(top_pick['ensemble_probability'])}, 20D advance {_format_return_pct(top_pick['recent_advance_20d'])}, run-up guardrail {float(top_pick['runup_penalty']):.2f}x, portfolio weight {_format_weight_pct(top_pick['portfolio_weight'])}."
                ),
                tag="Top combined pick",
            )
        )

    rows: list[tuple[str, ...]] = []
    for row in live_ml_view["allocation_frame"].itertuples(index=False):
        rows.append(
            (
                f"{row.sector_label} ({row.symbol})",
                _format_decimal(row.entry_score, 3),
                _format_probability_pct(row.ensemble_probability),
                _format_return_pct(row.recent_advance_20d),
                _format_return_pct(row.recent_advance_60d),
                f"{float(row.runup_penalty):.2f}x",
                _format_decimal(row.validation_quality_score, 3),
                _format_decimal(row.best_overfit_stability_score, 1),
                _format_decimal(row.combined_live_score, 3),
                _format_weight_pct(row.sleeve_weight),
                _format_weight_pct(row.portfolio_weight),
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Live Rotation</p>',
            '  <h2>Current ML-Adjusted Rotation</h2>',
            f'  <p>{html.escape(str(live_ml_view["message"]))}</p>',
            '  <div class="card-grid">',
            "\n".join(cards),
            '  </div>',
            _render_data_table(
                headers=(
                    'Sector',
                    'Regime Score',
                    'ML Probability',
                    'Advance 20D',
                    'Advance 60D',
                    'Guardrail',
                    'Validation Quality',
                    'Stability',
                    'Combined Score',
                    'Sleeve Weight',
                    'Portfolio Weight',
                ),
                rows=rows,
            ),
            '</section>',
        ]
    )


def _render_rotation_backtest_section(
    rotation_view: dict[str, Any] | None,
    *,
    eyebrow: str,
    title: str,
) -> str:
    if not isinstance(rotation_view, dict) or not rotation_view.get("available"):
        message = str(rotation_view.get("message") if isinstance(rotation_view, dict) else "Benchmark unavailable.")
        return "\n".join(
            [
                '<section class="section">',
                f'  <p class="eyebrow">{html.escape(eyebrow)}</p>',
                f'  <h2>{html.escape(title)}</h2>',
                f'  <p>{html.escape(message)}</p>',
                '</section>',
            ]
        )

    summary_frame = rotation_view["strategy_summary_frame"].copy()
    quality_row = summary_frame.loc[summary_frame["strategy_label"] == "ML Quality-Weighted Rotation"].iloc[0]
    reserve_row = summary_frame.loc[summary_frame["strategy_label"] == RESERVE_STRATEGY_LABEL].iloc[0]
    reserve_leverage_row = summary_frame.loc[summary_frame["strategy_label"].astype(str).str.startswith(RESERVE_LEVERAGE_LABEL_PREFIX)].iloc[0]
    spy_row = summary_frame.loc[summary_frame["strategy_label"] == "SPY Buy And Hold"].iloc[0]
    quality_x3_row = summary_frame.loc[summary_frame["strategy_label"].astype(str).str.startswith("ML Quality-Weighted Rotation x")].iloc[0]
    spy_x3_row = summary_frame.loc[summary_frame["strategy_label"].astype(str).str.startswith("SPY Buy And Hold x")].iloc[0]
    signal_date = pd.Timestamp(rotation_view["current_signal_date"]).strftime("%Y-%m-%d")
    benchmark_start = pd.Timestamp(rotation_view["benchmark_start"]).strftime("%Y-%m-%d")
    benchmark_end = pd.Timestamp(rotation_view["benchmark_end"]).strftime("%Y-%m-%d")
    reserve_peak_fraction = float(rotation_view["period_log_frame"]["reserve_deployed_fraction"].max()) if not rotation_view["period_log_frame"].empty else 0.0
    spy_worst_drawdown = float(rotation_view["period_log_frame"]["spy_drawdown_signal"].min()) if not rotation_view["period_log_frame"].empty else 0.0
    scope_kind = str(rotation_view.get("scope_kind") or "")
    scope_body = (
        "This slice uses only the final untouched holdout dates after the validation years."
        if scope_kind == "holdout"
        else "This slice uses every walk-forward out-of-sample window from 2006 onward, so the major crisis regimes are visible."
    )
    reserve_tier_note = "Only the first 5% drawdown tier triggered in this slice." if reserve_peak_fraction <= 0.10 else "Multiple reserve tiers triggered in this slice."

    cards = [
        _render_stat_card(
            title=str(rotation_view.get("scope_label") or title),
            body=(
                f"{scope_body} Window range {benchmark_start} to {benchmark_end} across {int(rotation_view.get('period_count', 0) or 0)} realized five-bar holding windows."
            ),
            tag="Benchmark scope",
        ),
        _render_stat_card(
            title="ML Quality-Weighted Rotation",
            body=(
                f"CAGR {_format_return_pct(quality_row.cagr)}, Sharpe {_format_decimal(quality_row.sharpe)}, max drawdown {_format_return_pct(quality_row.max_drawdown)}, turnover {_format_turnover(quality_row.turnover_per_year)}."
            ),
            tag="Strategy",
        ),
        _render_stat_card(
            title="SPY Buy And Hold",
            body=(
                f"CAGR {_format_return_pct(spy_row.cagr)}, Sharpe {_format_decimal(spy_row.sharpe)}, max drawdown {_format_return_pct(spy_row.max_drawdown)} over the same benchmark windows."
            ),
            tag="Benchmark",
        ),
        _render_stat_card(
            title=RESERVE_STRATEGY_LABEL,
            body=(
                f"CAGR {_format_return_pct(reserve_row.cagr)}, Sharpe {_format_decimal(reserve_row.sharpe)}, max drawdown {_format_return_pct(reserve_row.max_drawdown)}, turnover {_format_turnover(reserve_row.turnover_per_year)}. The 60% core stays in the quality basket while the reserve sleeve only buys SPY during drawdowns."
            ),
            tag="Reserve rule",
        ),
        _render_stat_card(
            title=str(reserve_leverage_row.strategy_label),
            body=(
                f"CAGR {_format_return_pct(reserve_leverage_row.cagr)}, Sharpe {_format_decimal(reserve_leverage_row.sharpe)}, max drawdown {_format_return_pct(reserve_leverage_row.max_drawdown)}, turnover {_format_turnover(reserve_leverage_row.turnover_per_year)}. Only the deployed reserve sleeve is levered."
            ),
            tag="Leveraged reserve",
        ),
        _render_stat_card(
            title=f"Worst SPY signal drawdown {_format_return_pct(spy_worst_drawdown)}",
            body=(
                f"Peak reserve deployment reached {_format_weight_pct(reserve_peak_fraction)} of the reserve sleeve. {reserve_tier_note}"
            ),
            tag="Trigger depth",
        ),
        _render_stat_card(
            title=str(quality_x3_row.strategy_label),
            body=(
                f"CAGR {_format_return_pct(quality_x3_row.cagr)}, Sharpe {_format_decimal(quality_x3_row.sharpe)}, max drawdown {_format_return_pct(quality_x3_row.max_drawdown)}, turnover {_format_turnover(quality_x3_row.turnover_per_year)}."
            ),
            tag="Leveraged strategy",
        ),
        _render_stat_card(
            title=str(spy_x3_row.strategy_label),
            body=(
                f"CAGR {_format_return_pct(spy_x3_row.cagr)}, Sharpe {_format_decimal(spy_x3_row.sharpe)}, max drawdown {_format_return_pct(spy_x3_row.max_drawdown)} under the same 6% financing assumption."
            ),
            tag="Leveraged benchmark",
        ),
        _render_stat_card(
            title=f"Latest complete signal {signal_date}",
            body=(
                f"Windows count realized {int(rotation_view.get('holding_period_bars', 0) or 0)}-bar evaluation periods. Trades count actual entries or rebalances. SPY buy-and-hold therefore shows {int(spy_row.trade_count)} entry across {int(spy_row.period_count)} evaluation windows."
            ),
            tag="Metric definition",
        ),
    ]

    summary_rows: list[tuple[str, ...]] = []
    for row in summary_frame.itertuples(index=False):
        summary_rows.append(
            (
                str(row.strategy_label),
                _format_return_pct(row.total_return),
                _format_return_pct(row.cagr),
                _format_decimal(row.sharpe),
                _format_decimal(row.sortino),
                _format_return_pct(row.max_drawdown),
                _format_decimal(row.calmar),
                _format_decimal(row.profit_factor),
                _format_probability_pct(row.hit_rate),
                str(int(getattr(row, "trade_count", 0) or 0)),
                str(int(getattr(row, "period_count", 0) or 0)),
                _format_turnover(row.turnover_per_year),
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            f'  <p class="eyebrow">{html.escape(eyebrow)}</p>',
            f'  <h2>{html.escape(title)}</h2>',
            f'  <p>{html.escape(str(rotation_view["method_note"]))}</p>',
            '  <div class="card-grid">',
            "\n".join(cards),
            '  </div>',
            _render_equity_curve_chart(rotation_view["period_log_frame"]),
            _render_equity_curve_chart(rotation_view["period_log_frame"], leveraged=True),
            _render_data_table(
                headers=(
                    'Strategy',
                    'Total Return',
                    'CAGR',
                    'Sharpe',
                    'Sortino',
                    'Max DD',
                    'Calmar',
                    'Profit Factor',
                    'Hit Rate',
                    'Trades',
                    'Windows',
                    'Turnover',
                ),
                rows=summary_rows,
            ),
            '</section>',
        ]
    )


def _render_holdout_backtest_section(sector_ml_view: dict[str, Any]) -> str:
    rotation_view = sector_ml_view.get("holdout_rotation_view") if isinstance(sector_ml_view, dict) else None
    return _render_rotation_backtest_section(
        rotation_view,
        eyebrow="Holdout Benchmark",
        title="Strict Holdout: ML Rotation, SPY Reserve Sleeve, And SPY",
    )


def _render_history_backtest_section(sector_ml_view: dict[str, Any]) -> str:
    rotation_view = sector_ml_view.get("historical_rotation_view") if isinstance(sector_ml_view, dict) else None
    return _render_rotation_backtest_section(
        rotation_view,
        eyebrow="Walk-Forward History",
        title="Crisis-Inclusive History: ML Rotation, SPY Reserve Sleeve, And SPY",
    )


def _render_rotation_period_log_section(
    rotation_view: dict[str, Any] | None,
    *,
    eyebrow: str,
    title: str,
    description: str,
    sort_by: str,
    ascending: bool,
    max_rows: int,
) -> str:
    if not isinstance(rotation_view, dict) or not rotation_view.get("available"):
        return ""

    period_log = rotation_view["period_log_frame"].copy().sort_values(sort_by, ascending=ascending).head(max_rows)
    rows: list[tuple[str, ...]] = []
    for row in period_log.itertuples(index=False):
        rows.append(
            (
                pd.Timestamp(row.signal_date).strftime("%Y-%m-%d"),
                pd.Timestamp(row.entry_date).strftime("%Y-%m-%d"),
                pd.Timestamp(row.exit_date).strftime("%Y-%m-%d"),
                _format_return_pct(row.spy_drawdown_signal),
                str(row.regime_label),
                str(row.quality_selection),
                str(row.reserve_asset),
                _format_weight_pct(row.reserve_deployed_fraction),
                _format_weight_pct(row.reserve_cash_weight),
                _format_return_pct(row.quality_return),
                _format_return_pct(row.quality_return_x3),
                _format_return_pct(row.reserve_rule_return),
                _format_return_pct(row.reserve_leverage_rule_return),
                _format_return_pct(row.probability_return),
                _format_return_pct(row.spy_return),
                _format_return_pct(row.spy_return_x3),
                _format_decimal(row.quality_turnover, 2),
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            f'  <p class="eyebrow">{html.escape(eyebrow)}</p>',
            f'  <h2>{html.escape(title)}</h2>',
            f'  <p>{html.escape(description)}</p>',
            _render_data_table(
                headers=(
                    'Signal Date',
                    'Entry Date',
                    'Exit Date',
                    'SPY Drawdown',
                    'Regime',
                    'Quality Selection',
                    'Reserve Asset',
                    'Reserve Deployed',
                    'Reserve Cash',
                    'Quality Return',
                    'Quality Return x3',
                    'Reserve Rule Return',
                    'Reserve Rule x3',
                    'Probability Return',
                    'SPY Return',
                    'SPY Return x3',
                    'Turnover',
                ),
                rows=rows,
            ),
            '</section>',
        ]
    )


def _render_holdout_period_log_section(sector_ml_view: dict[str, Any]) -> str:
    rotation_view = sector_ml_view.get("holdout_rotation_view") if isinstance(sector_ml_view, dict) else None
    return _render_rotation_period_log_section(
        rotation_view,
        eyebrow="Rebalance Log",
        title="Latest Holdout Rotation Decisions",
        description="The log below shows the most recent holdout rebalance windows, the sectors selected by the quality-weighted ML score, and the realized next-window return compared with SPY.",
        sort_by="signal_date",
        ascending=False,
        max_rows=12,
    )


def _render_history_drawdown_section(sector_ml_view: dict[str, Any]) -> str:
    rotation_view = sector_ml_view.get("historical_rotation_view") if isinstance(sector_ml_view, dict) else None
    return _render_rotation_period_log_section(
        rotation_view,
        eyebrow="Stress Windows",
        title="Deep Drawdown Windows And Reserve Triggers",
        description="This table isolates the worst SPY drawdown signals inside the full 2006-2026 walk-forward history so you can see how the reserve rule behaved in the key stress episodes.",
        sort_by="spy_drawdown_signal",
        ascending=True,
        max_rows=15,
    )


def _render_sector_dip_section(sector_diagnostics_view: dict[str, Any]) -> str:
    if not isinstance(sector_diagnostics_view, dict) or not sector_diagnostics_view.get("available"):
        return ""

    dip_summary_frame = sector_diagnostics_view["dip_summary_frame"]
    if dip_summary_frame.empty:
        return ""

    lookback_bars = int(sector_diagnostics_view.get("lookback_bars", 5))
    severe_drop_threshold = float(sector_diagnostics_view.get("severe_drop_threshold", -0.05))
    top_dip = sector_diagnostics_view.get("top_dip_row") or {}
    top_severe = sector_diagnostics_view.get("top_severe_row") or {}
    rotation_profile_frame = sector_diagnostics_view.get("rotation_profile_frame")
    strategy_usage_frame = sector_diagnostics_view.get("strategy_usage_frame")

    cards: list[str] = []
    if top_dip:
        cards.append(
            _render_stat_card(
                title=f"Best after any {lookback_bars}-bar drop: {top_dip['sector_label']} ({top_dip['symbol']})",
                body=(
                    f"Average next-window return {_format_return_pct(top_dip['avg_forward_return_after_drop'])} after {int(top_dip['dip_windows'])} drop windows. "
                    f"Hit rate {_format_probability_pct(top_dip['hit_rate_after_drop'])}."
                ),
                tag="Buy-the-dip leader",
            )
        )
    if top_severe:
        cards.append(
            _render_stat_card(
                title=f"Best after {abs(severe_drop_threshold):.0%}+ drop: {top_severe['sector_label']} ({top_severe['symbol']})",
                body=(
                    f"Average next-window return {_format_return_pct(top_severe['avg_forward_return_after_severe_drop'])} across {int(top_severe['severe_drop_windows'])} severe-drop windows. "
                    f"Hit rate {_format_probability_pct(top_severe['hit_rate_after_severe_drop'])}."
                ),
                tag="Stress drop leader",
            )
        )
    if isinstance(rotation_profile_frame, pd.DataFrame) and not rotation_profile_frame.empty:
        most_rotated = rotation_profile_frame.sort_values("rotation_per_year", ascending=False).iloc[0]
        cards.append(
            _render_stat_card(
                title=f"Fastest-rotating live sleeve: {most_rotated.strategy_label}",
                body=(
                    f"About {_format_decimal(most_rotated.rotation_per_year, 1)} basket changes per year, with {int(most_rotated.rotation_count)} total changes in the 2006-2026 walk-forward history."
                ),
                tag="Rotation speed",
            )
        )
    if isinstance(strategy_usage_frame, pd.DataFrame) and not strategy_usage_frame.empty:
        quality_usage = strategy_usage_frame.loc[strategy_usage_frame["strategy_label"] == "ML Quality-Weighted Rotation"]
        if not quality_usage.empty:
            top_quality_usage = quality_usage.sort_values("selected_windows", ascending=False).iloc[0]
            cards.append(
                _render_stat_card(
                    title=f"Most-used quality sleeve sector: {top_quality_usage.sector_label} ({top_quality_usage.symbol})",
                    body=(
                        f"Selected in {int(top_quality_usage.selected_windows)} quality-rotation windows, or {_format_probability_pct(top_quality_usage.selection_share_active)} of active quality windows."
                    ),
                    tag="Selection frequency",
                )
            )

    rows: list[tuple[str, ...]] = []
    for row in dip_summary_frame.itertuples(index=False):
        rows.append(
            (
                f"{row.sector_label} ({row.symbol})",
                str(row.family),
                str(int(row.dip_windows)),
                _format_return_pct(row.avg_prior_return),
                _format_return_pct(row.avg_forward_return_after_drop),
                _format_probability_pct(row.hit_rate_after_drop),
                _format_return_pct(row.compounded_return_after_drop),
                str(int(row.severe_drop_windows)),
                _format_return_pct(row.avg_forward_return_after_severe_drop),
                _format_return_pct(row.oos_cagr),
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Sector Dip Study</p>',
            '  <h2>Which Sectors Paid Best After They Dropped</h2>',
            f'  <p>This ranking uses the full 2006-2026 out-of-sample sector signal history. A drop means the sector itself had a negative trailing {lookback_bars}-bar return on the signal date. The next-window return is the realized out-of-sample {lookback_bars}-bar forward return net of the base transaction-cost assumption.</p>',
            '  <div class="card-grid">',
            "\n".join(cards),
            '  </div>',
            _render_data_table(
                headers=(
                    'Sector',
                    'Type',
                    'Drop Windows',
                    'Avg Prior Drop',
                    'Avg Next Return',
                    'Hit Rate',
                    'Compounded Return',
                    '5%+ Drop Windows',
                    'Avg Next Return 5%+',
                    'OOS CAGR',
                ),
                rows=rows,
            ),
            '</section>',
        ]
    )


def _render_strategy_rotation_detail_section(sector_diagnostics_view: dict[str, Any]) -> str:
    if not isinstance(sector_diagnostics_view, dict) or not sector_diagnostics_view.get("available"):
        return ""

    strategy_detail_frame = sector_diagnostics_view.get("strategy_detail_frame")
    if not isinstance(strategy_detail_frame, pd.DataFrame) or strategy_detail_frame.empty:
        return ""

    rows: list[tuple[str, ...]] = []
    for row in strategy_detail_frame.itertuples(index=False):
        rows.append(
            (
                str(row.strategy_label),
                _format_return_pct(row.total_return),
                _format_return_pct(row.cagr),
                _format_decimal(row.sharpe),
                _format_return_pct(row.max_drawdown),
                _format_probability_pct(row.hit_rate),
                str(int(row.trade_count)),
                str(int(row.period_count)),
                str(int(row.rotation_count)),
                _format_decimal(row.rotation_per_year, 1),
                _format_turnover(row.turnover_per_year),
                _format_decimal(row.avg_selected_count, 1),
                str(int(row.cash_windows)),
                str(row.most_common_selection),
                str(row.most_selected_sector),
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Strategy Audit</p>',
            '  <h2>How Often Each Strategy Rotated And What It Earned</h2>',
            '  <p>This table uses the full 2006-2026 walk-forward history. Rotations count basket changes from one signal window to the next. The leveraged variants share the same underlying rotation path as their unlevered base strategy and only change the exposure profile.</p>',
            _render_data_table(
                headers=(
                    'Strategy',
                    'Total Return',
                    'CAGR',
                    'Sharpe',
                    'Max DD',
                    'Hit Rate',
                    'Trades',
                    'Windows',
                    'Rotations',
                    'Rot/Yr',
                    'Turnover',
                    'Avg Sectors Held',
                    'Cash Windows',
                    'Most Common Basket',
                    'Most Used Asset',
                ),
                rows=rows,
            ),
            '</section>',
        ]
    )


def _render_strategy_sector_usage_section(sector_diagnostics_view: dict[str, Any]) -> str:
    if not isinstance(sector_diagnostics_view, dict) or not sector_diagnostics_view.get("available"):
        return ""

    strategy_usage_frame = sector_diagnostics_view.get("strategy_usage_frame")
    if not isinstance(strategy_usage_frame, pd.DataFrame) or strategy_usage_frame.empty:
        return ""

    rows: list[tuple[str, ...]] = []
    for row in strategy_usage_frame.itertuples(index=False):
        rows.append(
            (
                str(row.strategy_label),
                f"{row.sector_label} ({row.symbol})",
                str(int(row.selected_windows)),
                _format_probability_pct(row.selection_share_active),
                _format_return_pct(row.avg_strategy_return),
                _format_return_pct(row.median_strategy_return),
                _format_return_pct(row.avg_spy_drawdown_signal),
                pd.Timestamp(row.latest_signal_date).strftime("%Y-%m-%d"),
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Constituent Usage</p>',
            '  <h2>Which Assets The Rotation Strategies Actually Used</h2>',
            '  <p>For the quality and probability strategies, the return columns below are basket returns for windows where the sector was part of the selected basket, not isolated single-sector returns. For the reserve strategy, the asset is SPY whenever the reserve sleeve is mobilized. Use the dip-study section above for isolated per-sector forward returns.</p>',
            _render_data_table(
                headers=(
                    'Strategy',
                    'Asset',
                    'Selected Windows',
                    'Share Of Active Windows',
                    'Avg Strategy Return',
                    'Median Strategy Return',
                    'Avg SPY Drawdown At Entry',
                    'Last Seen',
                ),
                rows=rows,
            ),
            '</section>',
        ]
    )


def _render_rotation_year_regime_section(
    rotation_view: dict[str, Any] | None,
    *,
    eyebrow: str,
    title: str,
    description: str,
) -> str:
    if not isinstance(rotation_view, dict) or not rotation_view.get("available"):
        return ""

    yearly_rows: list[tuple[str, ...]] = []
    yearly_frame = rotation_view["yearly_summary_frame"].sort_values(["year", "strategy_label"], ascending=[True, True])
    for row in yearly_frame.itertuples(index=False):
        yearly_rows.append(
            (
                str(row.strategy_label),
                str(int(row.year)),
                _format_return_pct(row.total_return),
                _format_return_pct(row.cagr),
                _format_decimal(row.sharpe),
                _format_return_pct(row.max_drawdown),
                str(int(getattr(row, "trade_count", 0) or 0)),
                str(int(getattr(row, "period_count", 0) or 0)),
                _format_turnover(row.turnover_per_year),
            )
        )

    regime_rows: list[tuple[str, ...]] = []
    regime_frame = rotation_view["regime_summary_frame"].sort_values(["regime_label", "strategy_label"], ascending=[True, True])
    for row in regime_frame.itertuples(index=False):
        regime_rows.append(
            (
                str(row.strategy_label),
                str(row.regime_label),
                _format_return_pct(row.total_return),
                _format_return_pct(row.cagr),
                _format_decimal(row.sharpe),
                _format_return_pct(row.max_drawdown),
                _format_probability_pct(row.hit_rate),
                str(int(getattr(row, "trade_count", 0) or 0)),
                str(int(getattr(row, "period_count", 0) or 0)),
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            f'  <p class="eyebrow">{html.escape(eyebrow)}</p>',
            f'  <h2>{html.escape(title)}</h2>',
            f'  <p>{html.escape(description)}</p>',
            _render_data_table(
                headers=(
                    'Strategy',
                    'Year',
                    'Total Return',
                    'CAGR',
                    'Sharpe',
                    'Max DD',
                    'Trades',
                    'Windows',
                    'Turnover',
                ),
                rows=yearly_rows,
            ),
            _render_data_table(
                headers=(
                    'Strategy',
                    'Signal Regime',
                    'Total Return',
                    'CAGR',
                    'Sharpe',
                    'Max DD',
                    'Hit Rate',
                    'Trades',
                    'Windows',
                ),
                rows=regime_rows,
            ),
            '</section>',
        ]
    )


def _filter_strategy_rows(frame: pd.DataFrame, label: str, *, startswith: bool = False) -> pd.DataFrame:
    strategy_labels = frame["strategy_label"].astype(str)
    if startswith:
        return frame.loc[strategy_labels.str.startswith(label)].copy()
    return frame.loc[strategy_labels == label].copy()


def _build_regime_vs_spy_frame(rotation_view: dict[str, Any] | None, *, leveraged: bool) -> pd.DataFrame:
    if not isinstance(rotation_view, dict) or not rotation_view.get("available"):
        return pd.DataFrame()

    regime_frame = rotation_view["regime_summary_frame"].copy()
    if leveraged:
        quality_frame = _filter_strategy_rows(regime_frame, "ML Quality-Weighted Rotation x", startswith=True)
        reserve_frame = _filter_strategy_rows(regime_frame, RESERVE_LEVERAGE_LABEL_PREFIX, startswith=True)
        spy_frame = _filter_strategy_rows(regime_frame, "SPY Buy And Hold x", startswith=True)
    else:
        quality_frame = _filter_strategy_rows(regime_frame, "ML Quality-Weighted Rotation")
        reserve_frame = _filter_strategy_rows(regime_frame, RESERVE_STRATEGY_LABEL)
        spy_frame = _filter_strategy_rows(regime_frame, "SPY Buy And Hold")

    if quality_frame.empty or reserve_frame.empty or spy_frame.empty:
        return pd.DataFrame()

    comparison_frame = (
        spy_frame[
            [
                "regime_label",
                "period_count",
                "total_return",
                "max_drawdown",
            ]
        ]
        .rename(
            columns={
                "period_count": "windows",
                "total_return": "spy_total_return",
                "max_drawdown": "spy_max_drawdown",
            }
        )
        .merge(
            quality_frame[["regime_label", "total_return", "max_drawdown"]].rename(
                columns={
                    "total_return": "quality_total_return",
                    "max_drawdown": "quality_max_drawdown",
                }
            ),
            on="regime_label",
            how="inner",
        )
        .merge(
            reserve_frame[["regime_label", "total_return", "max_drawdown"]].rename(
                columns={
                    "total_return": "reserve_total_return",
                    "max_drawdown": "reserve_max_drawdown",
                }
            ),
            on="regime_label",
            how="inner",
        )
    )
    if comparison_frame.empty:
        return comparison_frame

    comparison_frame["quality_minus_spy"] = (
        comparison_frame["quality_total_return"] - comparison_frame["spy_total_return"]
    )
    comparison_frame["reserve_minus_spy"] = (
        comparison_frame["reserve_total_return"] - comparison_frame["spy_total_return"]
    )
    return comparison_frame.sort_values("regime_label").reset_index(drop=True)


def _build_regime_ranking_frame(rotation_view: dict[str, Any] | None) -> pd.DataFrame:
    if not isinstance(rotation_view, dict) or not rotation_view.get("available"):
        return pd.DataFrame()

    regime_frame = rotation_view["regime_summary_frame"].copy()
    if regime_frame.empty:
        return regime_frame

    ranking_rows: list[dict[str, Any]] = []
    for strategy_label, group in regime_frame.groupby("strategy_label", sort=True):
        ranked_group = group.sort_values(
            ["total_return", "hit_rate", "max_drawdown"],
            ascending=[False, False, False],
        ).reset_index(drop=True)
        group_size = len(ranked_group.index)
        for rank, row in enumerate(ranked_group.itertuples(index=False), start=1):
            ranking_rows.append(
                {
                    "strategy_label": str(strategy_label),
                    "rank": rank,
                    "regime_label": str(row.regime_label),
                    "total_return": float(row.total_return),
                    "cagr": float(row.cagr) if not pd.isna(row.cagr) else None,
                    "max_drawdown": float(row.max_drawdown),
                    "hit_rate": float(row.hit_rate) if not pd.isna(row.hit_rate) else None,
                    "windows": int(getattr(row, "period_count", 0) or 0),
                    "is_best": rank == 1,
                    "is_worst": rank == group_size,
                }
            )

    ranking_frame = pd.DataFrame(ranking_rows)
    if not ranking_frame.empty:
        ranking_frame = ranking_frame.sort_values(["strategy_label", "rank"]).reset_index(drop=True)
    return ranking_frame


def _render_leveraged_regime_vs_spy_section(sector_ml_view: dict[str, Any]) -> str:
    rotation_view = sector_ml_view.get("historical_rotation_view") if isinstance(sector_ml_view, dict) else None
    comparison_frame = _build_regime_vs_spy_frame(rotation_view, leveraged=True)
    if comparison_frame.empty:
        return ""

    best_quality = comparison_frame.sort_values("quality_minus_spy", ascending=False).iloc[0]
    worst_quality = comparison_frame.sort_values("quality_minus_spy", ascending=True).iloc[0]
    best_reserve = comparison_frame.sort_values("reserve_minus_spy", ascending=False).iloc[0]
    worst_spy = comparison_frame.sort_values("spy_total_return", ascending=True).iloc[0]

    cards = [
        _render_stat_card(
            title=f"Best quality x3 regime: {best_quality.regime_label}",
            body=(
                f"Quality x3 beat SPY x3 by {_format_return_pct(best_quality.quality_minus_spy)} in this regime, with total return {_format_return_pct(best_quality.quality_total_return)} versus {_format_return_pct(best_quality.spy_total_return)} for SPY x3."
            ),
            tag="Leveraged edge",
        ),
        _render_stat_card(
            title=f"Worst quality x3 regime: {worst_quality.regime_label}",
            body=(
                f"Quality x3 lagged SPY x3 by {_format_return_pct(abs(worst_quality.quality_minus_spy))} here. This is the regime where leverage on the model hurt the most against leveraged SPY."
            ),
            tag="Leveraged drag",
        ),
        _render_stat_card(
            title=f"Best reserve x3 regime: {best_reserve.regime_label}",
            body=(
                f"Reserve sleeve x3 beat SPY x3 by {_format_return_pct(best_reserve.reserve_minus_spy)} in this regime, with total return {_format_return_pct(best_reserve.reserve_total_return)}."
            ),
            tag="Reserve x3",
        ),
        _render_stat_card(
            title=f"Worst leveraged SPY regime: {worst_spy.regime_label}",
            body=(
                f"SPY x3 lost {_format_return_pct(worst_spy.spy_total_return)} with max drawdown {_format_return_pct(worst_spy.spy_max_drawdown)} in this regime."
            ),
            tag="SPY x3 stress",
        ),
    ]

    rows: list[tuple[str, ...]] = []
    for row in comparison_frame.itertuples(index=False):
        rows.append(
            (
                str(row.regime_label),
                str(int(row.windows)),
                _format_return_pct(row.spy_total_return),
                _format_return_pct(row.quality_total_return),
                _format_return_pct(row.quality_minus_spy),
                _format_return_pct(row.reserve_total_return),
                _format_return_pct(row.reserve_minus_spy),
                _format_return_pct(row.spy_max_drawdown),
                _format_return_pct(row.quality_max_drawdown),
                _format_return_pct(row.reserve_max_drawdown),
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Leveraged Regime Comparison</p>',
            '  <h2>x3 Regime Comparison Versus SPY x3</h2>',
            '  <p>This is the same regime slice, but for the leveraged paths under the 6% financing assumption. It compares the quality-weighted x3 strategy and the reserve-sleeve x3 strategy against SPY x3 inside each tested regime.</p>',
            '  <div class="card-grid">',
            "\n".join(cards),
            '  </div>',
            _render_data_table(
                headers=(
                    'Regime',
                    'Windows',
                    'SPY x3',
                    'Quality x3',
                    'Quality x3 - SPY x3',
                    'Reserve x3',
                    'Reserve x3 - SPY x3',
                    'SPY x3 Max DD',
                    'Quality x3 Max DD',
                    'Reserve x3 Max DD',
                ),
                rows=rows,
            ),
            '</section>',
        ]
    )


def _render_regime_ranking_section(sector_ml_view: dict[str, Any]) -> str:
    rotation_view = sector_ml_view.get("historical_rotation_view") if isinstance(sector_ml_view, dict) else None
    ranking_frame = _build_regime_ranking_frame(rotation_view)
    if ranking_frame.empty:
        return ""

    reserve_leverage_label = str(rotation_view.get("reserve_leverage_label") or RESERVE_LEVERAGE_LABEL_PREFIX)
    strategy_list = [
        "ML Quality-Weighted Rotation",
        RESERVE_STRATEGY_LABEL,
        "SPY Buy And Hold",
        "ML Quality-Weighted Rotation x3 @ 6%",
        reserve_leverage_label,
        "SPY Buy And Hold x3 @ 6%",
    ]
    cards: list[str] = []
    for strategy_label in strategy_list:
        strategy_rows = ranking_frame.loc[ranking_frame["strategy_label"] == strategy_label]
        if strategy_rows.empty:
            continue
        best_row = strategy_rows.iloc[0]
        worst_row = strategy_rows.iloc[-1]
        cards.append(
            _render_stat_card(
                title=str(strategy_label),
                body=(
                    f"Best regime: {best_row.regime_label} at {_format_return_pct(best_row.total_return)}. "
                    f"Worst regime: {worst_row.regime_label} at {_format_return_pct(worst_row.total_return)}."
                ),
                tag="Best vs worst",
            )
        )

    rows: list[tuple[str, ...]] = []
    for row in ranking_frame.itertuples(index=False):
        rows.append(
            (
                str(row.strategy_label),
                str(int(row.rank)),
                str(row.regime_label),
                _format_return_pct(row.total_return),
                _format_return_pct(row.cagr),
                _format_return_pct(row.max_drawdown),
                _format_probability_pct(row.hit_rate),
                str(int(row.windows)),
                'Best' if bool(row.is_best) else ('Worst' if bool(row.is_worst) else ''),
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Regime Ranking</p>',
            '  <h2>Best-To-Worst Regimes For Each Strategy</h2>',
            '  <p>This table ranks every tested regime separately inside each strategy, using total return within that regime slice. It is a ranking of where each strategy historically worked best and worst, not a forecast.</p>',
            '  <div class="card-grid">',
            "\n".join(cards),
            '  </div>',
            _render_data_table(
                headers=(
                    'Strategy',
                    'Rank',
                    'Regime',
                    'Total Return',
                    'CAGR',
                    'Max DD',
                    'Hit Rate',
                    'Windows',
                    'Flag',
                ),
                rows=rows,
            ),
            '</section>',
        ]
    )


def _compound_total_return(series: pd.Series) -> float | None:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return None
    return float((1.0 + numeric).prod() - 1.0)


def _load_price_history_frame(
    symbols: list[str],
    *,
    project_root: Path,
    start_date: pd.Timestamp | None = None,
    end_date: pd.Timestamp | None = None,
) -> pd.DataFrame:
    series_rows: list[pd.Series] = []
    for symbol in symbols:
        try:
            asset_frame = load_asset_daily(symbol, project_root=project_root)
        except FileNotFoundError:
            continue
        if "close" not in asset_frame.columns:
            continue
        close = pd.to_numeric(asset_frame["close"], errors="coerce").dropna().rename(symbol)
        if close.empty:
            continue
        series_rows.append(close)

    if not series_rows:
        return pd.DataFrame()

    frame = pd.concat(series_rows, axis=1).sort_index()
    if start_date is not None:
        frame = frame.loc[frame.index >= pd.Timestamp(start_date)]
    if end_date is not None:
        frame = frame.loc[frame.index <= pd.Timestamp(end_date)]
    return frame


def _window_total_return(series: pd.Series, start_date: pd.Timestamp, end_date: pd.Timestamp) -> float | None:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    window = numeric.loc[(numeric.index >= pd.Timestamp(start_date)) & (numeric.index <= pd.Timestamp(end_date))]
    if window.empty:
        return None
    if len(window.index) == 1:
        return 0.0
    return float(window.iloc[-1] / window.iloc[0] - 1.0)


def _normalise_price_window(
    price_frame: pd.DataFrame,
    symbols: list[str],
    *,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    if price_frame.empty:
        return pd.DataFrame()

    available_symbols = [symbol for symbol in symbols if symbol in price_frame.columns]
    if not available_symbols:
        return pd.DataFrame()

    window = price_frame.loc[(price_frame.index >= pd.Timestamp(start_date)) & (price_frame.index <= pd.Timestamp(end_date)), available_symbols].copy()
    normalised: dict[str, pd.Series] = {}
    for symbol in available_symbols:
        series = pd.to_numeric(window[symbol], errors="coerce").dropna()
        if len(series.index) < 2:
            continue
        normalised[symbol] = series / float(series.iloc[0])

    if not normalised:
        return pd.DataFrame()
    return pd.DataFrame(normalised).sort_index()


def _sample_frame_rows(frame: pd.DataFrame, max_points: int) -> pd.DataFrame:
    if frame.empty or len(frame.index) <= max_points:
        return frame
    positions = np.linspace(0, len(frame.index) - 1, num=max_points, dtype=int)
    positions = np.unique(np.concatenate(([0], positions, [len(frame.index) - 1])))
    return frame.iloc[positions]


def _symbol_color_map(symbols: list[str]) -> dict[str, str]:
    palette = (
        "#7a3e2b",
        "#0f4c5c",
        "#2d6a4f",
        "#bc6c25",
        "#c1121f",
        "#4361ee",
        "#588157",
        "#9c6644",
        "#006d77",
        "#ae2012",
        "#5a189a",
        "#3a5a40",
    )
    colors = {"SPY": "#6c757d"}
    offset = 0
    for symbol in symbols:
        if symbol == "SPY":
            continue
        colors[symbol] = palette[offset % len(palette)]
        offset += 1
    return colors


def _render_regime_price_chart(
    normalised_frame: pd.DataFrame,
    *,
    title: str,
    subtitle: str,
    aria_label: str,
    color_map: dict[str, str],
    background_bands: list[dict[str, Any]] | None = None,
    highlight_symbols: set[str] | None = None,
    max_points: int = 180,
) -> str:
    if normalised_frame.empty:
        return ""

    sampled = _sample_frame_rows(normalised_frame, max_points=max_points)
    plot_symbols = [symbol for symbol in sampled.columns if symbol in color_map]
    if not plot_symbols:
        return ""
    if "SPY" in plot_symbols:
        plot_symbols = ["SPY", *[symbol for symbol in plot_symbols if symbol != "SPY"]]

    start_date = pd.Timestamp(sampled.index.min())
    end_date = pd.Timestamp(sampled.index.max())
    if end_date <= start_date:
        return ""

    numeric_values = sampled[plot_symbols].to_numpy(dtype=float)
    min_value = float(min(np.nanmin(numeric_values), 1.0))
    max_value = float(max(np.nanmax(numeric_values), 1.0))
    value_span = max(max_value - min_value, 1e-9)
    width = 960.0
    height = 320.0
    left = 64.0
    right = 24.0
    top = 34.0
    bottom = 42.0
    span_seconds = max((end_date - start_date).total_seconds(), 1.0)
    highlight_set = set(highlight_symbols or set())

    def x_position(timestamp: pd.Timestamp) -> float:
        return left + ((pd.Timestamp(timestamp) - start_date).total_seconds() / span_seconds) * (width - left - right)

    def y_position(value: float) -> float:
        return height - bottom - ((float(value) - min_value) / value_span) * (height - top - bottom)

    grid_lines: list[str] = []
    for fraction in (0.0, 0.5, 1.0):
        y = top + fraction * (height - top - bottom)
        grid_value = max_value - fraction * value_span
        grid_lines.append(
            f'<line x1="{left:.1f}" y1="{y:.1f}" x2="{width - right:.1f}" y2="{y:.1f}" stroke="rgba(125, 139, 153, 0.16)" stroke-width="1"></line>'
        )
        grid_lines.append(
            f'<text x="12" y="{y + 4:.1f}" fill="#5f6b76" font-size="11">{html.escape(_format_return_pct(grid_value - 1.0))}</text>'
        )

    band_markup: list[str] = []
    for band in background_bands or []:
        band_start = max(pd.Timestamp(band["start_date"]), start_date)
        band_end = min(pd.Timestamp(band["end_date"]), end_date)
        if band_end <= band_start:
            continue
        x_start = x_position(band_start)
        x_end = x_position(band_end)
        band_markup.append(
            f'<rect x="{x_start:.1f}" y="{top:.1f}" width="{max(x_end - x_start, 1.0):.1f}" height="{height - top - bottom:.1f}" fill="{html.escape(str(band["color"]))}" fill-opacity="0.10"></rect>'
        )
        label = str(band.get("label") or "")
        if label and (x_end - x_start) >= 94.0:
            band_markup.append(
                f'<text x="{x_start + 8.0:.1f}" y="{top + 14.0:.1f}" fill="#5f6b76" font-size="11">{html.escape(label)}</text>'
            )

    polyline_markup: list[str] = []
    legend_markup: list[str] = []
    legend_columns = 4
    legend_spacing = 205.0
    legend_row_height = 18.0
    legend_count = 0

    for symbol in plot_symbols:
        series = pd.to_numeric(sampled[symbol], errors="coerce").dropna()
        if len(series.index) < 2:
            continue
        points = " ".join(
            f"{x_position(pd.Timestamp(timestamp)):.1f},{y_position(float(value)):.1f}"
            for timestamp, value in series.items()
        )
        stroke_width = 4.0 if symbol == "SPY" else (3.0 if symbol in highlight_set else 1.8)
        opacity = 0.98 if symbol == "SPY" else (0.88 if symbol in highlight_set else 0.58)
        polyline_markup.append(
            f'<polyline fill="none" stroke="{html.escape(color_map.get(symbol, "#7d8b99"))}" stroke-width="{stroke_width:.1f}" stroke-linejoin="round" stroke-linecap="round" opacity="{opacity:.2f}" points="{points}"></polyline>'
        )
        legend_row = legend_count // legend_columns
        legend_column = legend_count % legend_columns
        legend_x = left + legend_column * legend_spacing
        legend_y = 22.0 + legend_row * legend_row_height
        legend_markup.append(
            f'<circle cx="{legend_x:.1f}" cy="{legend_y:.1f}" r="4.5" fill="{html.escape(color_map.get(symbol, "#7d8b99"))}"></circle>'
        )
        legend_markup.append(
            f'<text x="{legend_x + 10.0:.1f}" y="{legend_y + 4.0:.1f}" fill="#1b2430" font-size="11">{html.escape(symbol)}</text>'
        )
        legend_count += 1

    return "\n".join(
        [
            '<div class="chart-shell">',
            f'  <svg viewBox="0 0 960 320" role="img" aria-label="{html.escape(aria_label)}">',
            '    <rect x="0" y="0" width="960" height="320" rx="18" fill="rgba(255, 253, 248, 0.92)"></rect>',
            f'    <text x="{left:.1f}" y="20" fill="#1b2430" font-size="18" font-family="Iowan Old Style, Georgia, serif">{html.escape(title)}</text>',
            f'    <text x="{left:.1f}" y="40" fill="#5f6b76" font-size="12">{html.escape(subtitle)}</text>',
            *band_markup,
            *grid_lines,
            f'    <line x1="{left:.1f}" y1="{height - bottom:.1f}" x2="{width - right:.1f}" y2="{height - bottom:.1f}" stroke="#b8b1a7" stroke-width="1.2"></line>',
            f'    <line x1="{left:.1f}" y1="{top:.1f}" x2="{left:.1f}" y2="{height - bottom:.1f}" stroke="#b8b1a7" stroke-width="1.2"></line>',
            *polyline_markup,
            *legend_markup,
            f'    <text x="{left:.1f}" y="{height - 10.0:.1f}" fill="#5f6b76" font-size="11">{html.escape(start_date.strftime("%Y-%m-%d"))}</text>',
            f'    <text x="{width - right:.1f}" y="{height - 10.0:.1f}" fill="#5f6b76" font-size="11" text-anchor="end">{html.escape(end_date.strftime("%Y-%m-%d"))}</text>',
            '  </svg>',
            '</div>',
        ]
    )


def _build_regime_episode_view(project_root: Path, sector_ml_view: dict[str, Any]) -> dict[str, Any]:
    history_view = sector_ml_view.get("historical_rotation_view") if isinstance(sector_ml_view, dict) else None
    sector_summary_frame = sector_ml_view.get("sector_summary_frame") if isinstance(sector_ml_view, dict) else None
    if not isinstance(history_view, dict) or not history_view.get("available"):
        return {"available": False, "message": "Historical rotation view unavailable."}
    if not isinstance(sector_summary_frame, pd.DataFrame) or sector_summary_frame.empty:
        return {"available": False, "message": "Sector summary frame unavailable."}

    period_log_frame = history_view["period_log_frame"].copy().sort_values("signal_date").reset_index(drop=True)
    if period_log_frame.empty:
        return {"available": False, "message": "Historical rotation period log is empty."}

    for column in ("signal_date", "entry_date", "exit_date"):
        period_log_frame[column] = pd.to_datetime(period_log_frame[column])

    symbol_lookup = (
        sector_summary_frame[["symbol", "sector_label"]]
        .drop_duplicates(subset=["symbol"])
        .set_index("symbol")["sector_label"]
        .to_dict()
    )
    sector_symbols = sorted(symbol_lookup)
    benchmark_start = pd.Timestamp(history_view["benchmark_start"])
    benchmark_end = pd.Timestamp(history_view["benchmark_end"])
    price_frame = _load_price_history_frame(
        ["SPY", *sector_symbols],
        project_root=project_root,
        start_date=benchmark_start,
        end_date=benchmark_end,
    )
    if price_frame.empty or "SPY" not in price_frame.columns:
        return {"available": False, "message": "Price history required for regime episodes is unavailable."}

    color_map = _symbol_color_map(["SPY", *sector_symbols])
    summary_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    episodes: list[dict[str, Any]] = []
    episode_id = 0
    start_index = 0

    while start_index < len(period_log_frame.index):
        current_label = str(period_log_frame.loc[start_index, "regime_label"])
        end_index = start_index + 1
        while end_index < len(period_log_frame.index) and str(period_log_frame.loc[end_index, "regime_label"]) == current_label:
            end_index += 1

        episode_frame = period_log_frame.iloc[start_index:end_index].copy().reset_index(drop=True)
        actionable_frame = episode_frame.iloc[1:].copy()
        first_row = episode_frame.iloc[0]
        activation_row = actionable_frame.iloc[0] if not actionable_frame.empty else None
        episode_id += 1

        start_signal_date = pd.Timestamp(first_row["signal_date"])
        end_exit_date = pd.Timestamp(episode_frame["exit_date"].iloc[-1])
        activation_signal_date = pd.Timestamp(activation_row["signal_date"]) if activation_row is not None else None
        activation_entry_date = pd.Timestamp(activation_row["entry_date"]) if activation_row is not None else None

        quality_return = _compound_total_return(actionable_frame["quality_return"]) if not actionable_frame.empty else None
        probability_return = _compound_total_return(actionable_frame["probability_return"]) if not actionable_frame.empty else None
        reserve_return = _compound_total_return(actionable_frame["reserve_rule_return"]) if not actionable_frame.empty else None
        spy_strategy_return = _compound_total_return(actionable_frame["spy_return"]) if not actionable_frame.empty else None
        reserve_peak_fraction = (
            float(pd.to_numeric(actionable_frame["reserve_deployed_fraction"], errors="coerce").fillna(0.0).max())
            if not actionable_frame.empty
            else 0.0
        )

        quality_counter: Counter[str] = Counter()
        for value in actionable_frame["quality_selection"] if not actionable_frame.empty else []:
            quality_counter.update(_split_sector_selection(value))
        reserve_tokens: list[str] = []
        reserve_series = actionable_frame["reserve_asset"] if "reserve_asset" in actionable_frame.columns else actionable_frame.get("reserve_sector", pd.Series(dtype="object"))
        for value in reserve_series if not actionable_frame.empty else []:
            if value is None or pd.isna(value):
                continue
            token = str(value).strip()
            if token and token.lower() != "cash":
                reserve_tokens.append(token)
        reserve_counter: Counter[str] = Counter(reserve_tokens)
        quality_primary_symbol = quality_counter.most_common(1)[0][0] if quality_counter else None
        reserve_primary_symbol = reserve_counter.most_common(1)[0][0] if reserve_counter else None

        detail_frame = pd.DataFrame()
        best_detail: dict[str, Any] | None = None
        spy_raw_return = None
        spy_reference_return = spy_strategy_return
        chart_frame = pd.DataFrame()

        if activation_entry_date is not None:
            spy_raw_return = _window_total_return(price_frame["SPY"], activation_entry_date, end_exit_date)
            if spy_reference_return is None:
                spy_reference_return = spy_raw_return

            local_detail_rows: list[dict[str, Any]] = []
            for symbol in sector_symbols:
                if symbol not in price_frame.columns:
                    continue
                total_return = _window_total_return(price_frame[symbol], activation_entry_date, end_exit_date)
                if total_return is None:
                    continue
                local_detail_rows.append(
                    {
                        "symbol": symbol,
                        "sector_label": str(symbol_lookup.get(symbol, symbol)),
                        "total_return": total_return,
                    }
                )

            detail_frame = pd.DataFrame(local_detail_rows)
            if not detail_frame.empty:
                if spy_reference_return is None:
                    detail_frame["return_minus_spy"] = np.nan
                else:
                    detail_frame["return_minus_spy"] = detail_frame["total_return"] - float(spy_reference_return)
                detail_frame["is_quality_primary"] = detail_frame["symbol"] == quality_primary_symbol
                detail_frame["is_reserve_primary"] = detail_frame["symbol"] == reserve_primary_symbol
                detail_frame = detail_frame.sort_values(["total_return", "symbol"], ascending=[False, True]).reset_index(drop=True)
                detail_frame["rank"] = np.arange(1, len(detail_frame.index) + 1)
                best_detail = detail_frame.iloc[0].to_dict()

                chart_symbols = ["SPY", *detail_frame["symbol"].head(4).tolist()]
                for symbol in (quality_primary_symbol, reserve_primary_symbol):
                    if symbol and symbol not in chart_symbols:
                        chart_symbols.append(symbol)
                chart_frame = _normalise_price_window(
                    price_frame,
                    chart_symbols,
                    start_date=activation_entry_date,
                    end_date=end_exit_date,
                )
                if not chart_frame.empty and "SPY" in chart_frame.columns:
                    ordered_symbols = ["SPY", *[symbol for symbol in chart_symbols if symbol != "SPY" and symbol in chart_frame.columns]]
                    chart_frame = chart_frame[ordered_symbols]

                detail_export = detail_frame.copy()
                detail_export.insert(0, "episode_id", episode_id)
                detail_export.insert(1, "regime_label", current_label)
                detail_export.insert(2, "start_signal_date", start_signal_date)
                detail_export.insert(3, "activation_entry_date", activation_entry_date)
                detail_export.insert(4, "end_exit_date", end_exit_date)
                detail_rows.extend(detail_export.to_dict(orient="records"))

        summary_row = {
            "episode_id": episode_id,
            "regime_label": current_label,
            "start_signal_date": start_signal_date,
            "activation_signal_date": activation_signal_date,
            "activation_entry_date": activation_entry_date,
            "end_exit_date": end_exit_date,
            "window_count": int(len(episode_frame.index)),
            "actionable_window_count": int(len(actionable_frame.index)),
            "calendar_days": int((end_exit_date - start_signal_date).days),
            "status": "actionable" if activation_entry_date is not None else "too_short_for_5_bar_shift",
            "spy_total_return": spy_reference_return,
            "spy_raw_total_return": spy_raw_return,
            "quality_strategy_return": quality_return,
            "probability_strategy_return": probability_return,
            "reserve_rule_return": reserve_return,
            "reserve_peak_fraction": reserve_peak_fraction,
            "quality_primary_symbol": quality_primary_symbol,
            "quality_primary_sector_label": str(symbol_lookup.get(quality_primary_symbol, quality_primary_symbol)) if quality_primary_symbol else None,
            "reserve_primary_symbol": reserve_primary_symbol,
            "reserve_primary_sector_label": str(symbol_lookup.get(reserve_primary_symbol, reserve_primary_symbol)) if reserve_primary_symbol else None,
            "best_etf_symbol": best_detail.get("symbol") if isinstance(best_detail, dict) else None,
            "best_etf_sector_label": best_detail.get("sector_label") if isinstance(best_detail, dict) else None,
            "best_etf_total_return": float(best_detail["total_return"]) if isinstance(best_detail, dict) and best_detail.get("total_return") is not None else None,
            "best_etf_minus_spy": (
                float(best_detail["return_minus_spy"])
                if isinstance(best_detail, dict) and best_detail.get("return_minus_spy") is not None and not pd.isna(best_detail["return_minus_spy"])
                else None
            ),
            "quality_minus_spy": (
                float(quality_return - spy_reference_return)
                if quality_return is not None and spy_reference_return is not None
                else None
            ),
            "reserve_minus_spy": (
                float(reserve_return - spy_reference_return)
                if reserve_return is not None and spy_reference_return is not None
                else None
            ),
        }
        summary_rows.append(summary_row)
        episodes.append(
            {
                **summary_row,
                "chart_frame": chart_frame,
                "top_return_frame": detail_frame.head(5).copy() if not detail_frame.empty else pd.DataFrame(),
            }
        )

        start_index = end_index

    summary_frame = pd.DataFrame(summary_rows)
    detail_frame = pd.DataFrame(detail_rows)
    overview_frame = _normalise_price_window(
        price_frame,
        ["SPY", *sector_symbols],
        start_date=benchmark_start,
        end_date=benchmark_end,
    )
    overview_bands = [
        {
            "start_date": row["start_signal_date"],
            "end_date": row["end_exit_date"],
            "label": row["regime_label"],
            "color": REGIME_COLORS.get(str(row["regime_label"]), "#e9c46a"),
        }
        for row in summary_rows
    ]

    return {
        "available": True,
        "activation_note": (
            "Episodes are contiguous 5-bar regime windows from the walk-forward history. The ETF-versus-SPY comparison starts only after one full 5-bar confirmation window, then runs until the regime episode ends. The strategy columns keep the report's existing next-bar execution, with the reserve sleeve deploying into SPY during drawdowns and rotating back to cash at a fresh SPY high."
        ),
        "summary_frame": summary_frame,
        "detail_frame": detail_frame,
        "episodes": episodes,
        "overview_frame": overview_frame,
        "overview_bands": overview_bands,
        "color_map": color_map,
    }


def _render_regime_episode_section(regime_episode_view: dict[str, Any]) -> str:
    if not isinstance(regime_episode_view, dict) or not regime_episode_view.get("available"):
        return ""

    summary_frame = regime_episode_view.get("summary_frame")
    if not isinstance(summary_frame, pd.DataFrame) or summary_frame.empty:
        return ""

    actionable_summary = summary_frame.loc[summary_frame["actionable_window_count"] > 0].copy()
    cards: list[str] = []
    if not actionable_summary.empty:
        best_raw = actionable_summary.sort_values("best_etf_minus_spy", ascending=False).iloc[0]
        best_quality = actionable_summary.sort_values("quality_minus_spy", ascending=False).iloc[0]
        best_reserve = actionable_summary.sort_values("reserve_minus_spy", ascending=False).iloc[0]
        reserve_triggered = actionable_summary.loc[actionable_summary["reserve_peak_fraction"] > 0.0]
        reserve_focus = reserve_triggered.sort_values("reserve_peak_fraction", ascending=False).iloc[0] if not reserve_triggered.empty else None

        cards.extend(
            [
                _render_stat_card(
                    title=f"Best raw ETF lead: {best_raw.best_etf_symbol}",
                    body=(
                        f"Episode {int(best_raw.episode_id)} in {best_raw.regime_label} finished with {best_raw.best_etf_symbol} at {_format_return_pct(best_raw.best_etf_total_return)} versus SPY at {_format_return_pct(best_raw.spy_total_return)}, a lead of {_format_return_pct(best_raw.best_etf_minus_spy)}."
                    ),
                    tag="Raw ETF winner",
                ),
                _render_stat_card(
                    title=f"Best quality episode: {best_quality.regime_label}",
                    body=(
                        f"Quality rotation compounded {_format_return_pct(best_quality.quality_strategy_return)} in episode {int(best_quality.episode_id)}, beating SPY by {_format_return_pct(best_quality.quality_minus_spy)} after the one-cadence wait."
                    ),
                    tag="Quality sleeve",
                ),
                _render_stat_card(
                    title=f"Best reserve episode: {best_reserve.regime_label}",
                    body=(
                        f"The reserve rule returned {_format_return_pct(best_reserve.reserve_rule_return)} in episode {int(best_reserve.episode_id)}, a spread of {_format_return_pct(best_reserve.reserve_minus_spy)} over SPY while retaining the 40% cash sleeve logic."
                    ),
                    tag="Reserve sleeve",
                ),
            ]
        )
        if reserve_focus is not None:
            cards.append(
                _render_stat_card(
                    title=f"Largest reserve deployment: {reserve_focus.regime_label}",
                    body=(
                        f"Episode {int(reserve_focus.episode_id)} pushed the reserve sleeve to {_format_weight_pct(reserve_focus.reserve_peak_fraction)} of the reserve bucket. The associated reserve asset was {reserve_focus.reserve_primary_symbol or 'Cash'}."
                    ),
                    tag="Cash mobilization",
                )
            )
        else:
            cards.append(
                _render_stat_card(
                    title="No reserve trigger inside sampled episodes",
                    body="Across the actionable regime episodes, SPY drawdowns did not persist long enough to activate a reserve tier beyond cash retention.",
                    tag="Cash mobilization",
                )
            )

    overview_chart = _render_regime_price_chart(
        regime_episode_view["overview_frame"],
        title="SPY vs Sector ETFs With Regime Bands",
        subtitle="Normalized to 1.0 at the start of the 2006+ historical benchmark. Background bands are contiguous regime episodes from the walk-forward signal log.",
        aria_label="SPY versus sector ETFs with regime overlays",
        color_map=regime_episode_view["color_map"],
        background_bands=regime_episode_view["overview_bands"],
        max_points=360,
    )

    summary_rows: list[tuple[str, ...]] = []
    for row in summary_frame.itertuples(index=False):
        best_label = (
            f"{row.best_etf_sector_label} ({row.best_etf_symbol})"
            if getattr(row, "best_etf_symbol", None)
            else "n/a"
        )
        summary_rows.append(
            (
                str(int(row.episode_id)),
                str(row.regime_label),
                pd.Timestamp(row.start_signal_date).strftime("%Y-%m-%d"),
                pd.Timestamp(row.activation_entry_date).strftime("%Y-%m-%d") if not pd.isna(row.activation_entry_date) else "n/a",
                pd.Timestamp(row.end_exit_date).strftime("%Y-%m-%d"),
                str(int(row.window_count)),
                best_label,
                _format_return_pct(row.best_etf_total_return),
                _format_return_pct(row.spy_total_return),
                _format_return_pct(row.best_etf_minus_spy),
                _format_return_pct(row.quality_strategy_return),
                _format_return_pct(row.reserve_rule_return),
                _format_weight_pct(row.reserve_peak_fraction),
                str(row.status).replace("_", " "),
            )
        )

    episode_markup: list[str] = []
    for episode in regime_episode_view.get("episodes") or []:
        chart_frame = episode.get("chart_frame")
        top_return_frame = episode.get("top_return_frame")
        chart_html = ""
        if isinstance(chart_frame, pd.DataFrame) and not chart_frame.empty:
            highlight_symbols = {
                symbol
                for symbol in (
                    episode.get("best_etf_symbol"),
                    episode.get("quality_primary_symbol"),
                    episode.get("reserve_primary_symbol"),
                )
                if isinstance(symbol, str) and symbol
            }
            chart_html = _render_regime_price_chart(
                chart_frame,
                title=f"Episode {int(episode['episode_id'])}: {episode['regime_label']}",
                subtitle="Normalized from the first actionable entry after one full 5-bar confirmation window.",
                aria_label=f"Episode {int(episode['episode_id'])} SPY versus ETF chart",
                color_map=regime_episode_view["color_map"],
                background_bands=[
                    {
                        "start_date": chart_frame.index.min(),
                        "end_date": chart_frame.index.max(),
                        "label": str(episode["regime_label"]),
                        "color": REGIME_COLORS.get(str(episode["regime_label"]), "#e9c46a"),
                    }
                ],
                highlight_symbols=highlight_symbols,
                max_points=120,
            )

        note_parts = []
        if episode.get("best_etf_symbol"):
            note_parts.append(
                f"Best raw ETF: {episode['best_etf_symbol']} at {_format_return_pct(episode.get('best_etf_total_return'))}, {_format_return_pct(episode.get('best_etf_minus_spy'))} versus SPY"
            )
        if episode.get("quality_primary_symbol"):
            note_parts.append(
                f"Most-used quality ETF: {episode['quality_primary_symbol']}"
            )
        if episode.get("reserve_primary_symbol"):
            note_parts.append(
                f"Reserve asset: {episode['reserve_primary_symbol']}"
            )
        note_parts.append(f"Quality rotation: {_format_return_pct(episode.get('quality_strategy_return'))}")
        note_parts.append(f"Reserve rule: {_format_return_pct(episode.get('reserve_rule_return'))}")
        note_parts.append(f"Peak reserve deployed: {_format_weight_pct(episode.get('reserve_peak_fraction'))}")
        subtitle = ". ".join(note_parts) + "."

        meta_items = [
            f"Episode {int(episode['episode_id'])}",
            str(episode["regime_label"]),
            f"Start {pd.Timestamp(episode['start_signal_date']).strftime('%Y-%m-%d')}",
            (
                f"Activated {pd.Timestamp(episode['activation_entry_date']).strftime('%Y-%m-%d')}"
                if episode.get("activation_entry_date") is not None and not pd.isna(episode.get("activation_entry_date"))
                else "No actionable 5-bar shift"
            ),
            f"End {pd.Timestamp(episode['end_exit_date']).strftime('%Y-%m-%d')}",
            f"{int(episode['window_count'])} windows",
        ]

        if isinstance(top_return_frame, pd.DataFrame) and not top_return_frame.empty:
            top_rows: list[tuple[str, ...]] = []
            for row in top_return_frame.itertuples(index=False):
                role = []
                if bool(row.is_quality_primary):
                    role.append("Quality")
                if bool(row.is_reserve_primary):
                    role.append("Reserve")
                top_rows.append(
                    (
                        str(int(row.rank)),
                        f"{row.sector_label} ({row.symbol})",
                        _format_return_pct(row.total_return),
                        _format_return_pct(row.return_minus_spy),
                        ", ".join(role) if role else "",
                    )
                )
            top_table = _render_data_table(
                headers=(
                    "Rank",
                    "ETF",
                    "Total Return",
                    "Minus SPY",
                    "Role",
                ),
                rows=top_rows,
            )
        else:
            top_table = '<p class="episode-subtitle">This regime lasted only one 5-bar window, so the delayed sector-rotation rule never activated before the next regime change.</p>'

        episode_markup.append(
            "\n".join(
                [
                    '<article class="episode-card">',
                    f'  <div class="episode-meta">{"".join(f"<span>{html.escape(item)}</span>" for item in meta_items)}</div>',
                    f'  <h3>{html.escape(str(episode["regime_label"]))}</h3>',
                    f'  <p class="episode-subtitle">{html.escape(subtitle)}</p>',
                    chart_html or '<p class="episode-subtitle">No ETF price path was available for this episode window.</p>',
                    top_table,
                    '</article>',
                ]
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Regime Episodes</p>',
            '  <h2>SPY Versus ETFs After A Regime Shift</h2>',
            f'  <p>{html.escape(str(regime_episode_view.get("activation_note") or ""))}</p>',
            '  <div class="card-grid">',
            "\n".join(cards),
            '  </div>',
            overview_chart,
            _render_data_table(
                headers=(
                    'Episode',
                    'Regime',
                    'Signal Start',
                    'Action Start',
                    'Episode End',
                    'Windows',
                    'Best ETF',
                    'ETF Return',
                    'SPY',
                    'ETF - SPY',
                    'Quality',
                    'Reserve',
                    'Peak Reserve',
                    'Status',
                ),
                rows=summary_rows,
            ),
            '  <div class="episode-grid">',
            "\n".join(episode_markup),
            '  </div>',
            '</section>',
        ]
    )


def _render_holdout_year_regime_section(sector_ml_view: dict[str, Any]) -> str:
    rotation_view = sector_ml_view.get("holdout_rotation_view") if isinstance(sector_ml_view, dict) else None
    return _render_rotation_year_regime_section(
        rotation_view,
        eyebrow="Benchmark Slices",
        title="Holdout Performance By Year And Signal Regime",
        description="These slices keep only the strict 2025+ holdout windows and break them down by calendar year and signal regime.",
    )


def _render_history_year_regime_section(sector_ml_view: dict[str, Any]) -> str:
    rotation_view = sector_ml_view.get("historical_rotation_view") if isinstance(sector_ml_view, dict) else None
    return _render_rotation_year_regime_section(
        rotation_view,
        eyebrow="History Slices",
        title="2006-2026 Walk-Forward Performance By Year And Signal Regime",
        description="These slices use the full walk-forward out-of-sample history, so the year and regime tables include the major stress periods that are absent from the strict holdout alone.",
    )


def _render_ml_overview_section(sector_ml_view: dict[str, Any]) -> str:
    if not sector_ml_view.get("available"):
        message = str(sector_ml_view.get("message") or "Sector ML study unavailable.")
        return "\n".join(
            [
                '<section class="section">',
                '  <p class="eyebrow">ML Overlay</p>',
                '  <h2>Machine Learning Ensemble Audit</h2>',
                f'  <p>{html.escape(message)}</p>',
                '</section>',
            ]
        )

    config = sector_ml_view["config"]
    start_year = pd.Timestamp(str(config["start_date"])).year
    holdout_year = pd.Timestamp(str(config["holdout_start"])).year
    history_year = pd.Timestamp(str(config["historical_benchmark_start"])).year
    leader = sector_ml_view["holdout_leader"]
    winner_counts = sector_ml_view["winner_counts_frame"]
    sector_count = len(sector_ml_view["sector_summary_frame"])
    top_winner = winner_counts.iloc[0].to_dict() if not winner_counts.empty else {"model_label": "n/a", "winner_count": 0}
    cards = [
        _render_stat_card(
            title=f"{start_year}-{holdout_year - 1} walk-forward, {holdout_year}+ holdout",
            body=(
                f"Five-year expanding train windows, one-year validation windows, feature lag {int(config['feature_lag'])}, purge {int(config['purge_size'])} bars, embargo {int(config['embargo_size'])} bars. The broader benchmark section starts in {history_year} so crisis eras are visible."
            ),
            tag="Validation design",
        ),
        _render_stat_card(
            title="Probability averaging only",
            body=(
                f"Elastic Net, ExtraTrees, and {sector_ml_view['boosting_backend']} are averaged directly. The stacked gate is disabled in this study to reduce meta-model overfit risk."
            ),
            tag="Model design",
        ),
        _render_stat_card(
            title=str(top_winner["model_label"]),
            body=f"Won {int(top_winner['winner_count'])} sectors on the stability score that penalizes validation-to-holdout degradation.",
            tag="Most stable model",
        ),
        _render_stat_card(
            title=str(leader["sector_label"]),
            body=(
                f"Best ensemble holdout by Sharpe. CAGR {_format_return_pct(leader['ensemble_holdout_cagr'])}, Sharpe {_format_decimal(leader['ensemble_holdout_sharpe'])}, max drawdown {_format_return_pct(leader['ensemble_holdout_max_drawdown'])}."
            ),
            tag="Holdout leader",
        ),
        _render_stat_card(
            title=f"{int(sector_ml_view['robust_cost_sector_count'])} / {sector_count} sectors",
            body="Still positive at the worst slippage stress scenario inside the untouched holdout.",
            tag="Cost robustness",
        ),
    ]

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">ML Overlay</p>',
            '  <h2>Machine Learning Ensemble Audit</h2>',
            f'  <p>{html.escape(str(sector_ml_view["data_note"]))}</p>',
            '  <div class="card-grid">',
            "\n".join(cards),
            '  </div>',
            '</section>',
        ]
    )


def _render_ml_sector_table_section(sector_ml_view: dict[str, Any]) -> str:
    if not sector_ml_view.get("available"):
        return ""

    rows: list[tuple[str, ...]] = []
    for row in sector_ml_view["sector_summary_frame"].sort_values("best_overfit_stability_score", ascending=False).itertuples(index=False):
        rows.append(
            (
                f"{row.sector_label} ({row.symbol})",
                str(row.best_overfit_model),
                _format_decimal(row.best_overfit_stability_score, digits=1),
                _format_return_pct(row.ensemble_holdout_cagr),
                _format_decimal(row.ensemble_holdout_sharpe),
                _format_decimal(row.ensemble_holdout_sortino),
                _format_return_pct(row.ensemble_holdout_max_drawdown),
                _format_decimal(row.ensemble_holdout_profit_factor),
                _format_probability_pct(row.ensemble_crisis_hit_rate),
                _format_turnover(row.ensemble_holdout_turnover_per_year),
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Sector ML</p>',
            '  <h2>Per-Sector Ensemble Results</h2>',
            '  <p>The table below uses the simple averaged ensemble as the live signal and separately identifies which single model preserved validation behavior into the untouched holdout best.</p>',
            _render_data_table(
                headers=(
                    'Sector',
                    'Best Anti-Overfit Model',
                    'Stability Score',
                    'Holdout CAGR',
                    'Holdout Sharpe',
                    'Holdout Sortino',
                    'Holdout Max DD',
                    'Profit Factor',
                    'Crisis Hit Rate',
                    'Turnover',
                ),
                rows=rows,
            ),
            '</section>',
        ]
    )


def _render_ml_model_comparison_section(sector_ml_view: dict[str, Any]) -> str:
    if not sector_ml_view.get("available"):
        return ""

    comparison = sector_ml_view["model_comparison_frame"].sort_values(
        ["sector_label", "stability_score", "model_label"],
        ascending=[True, False, True],
    )
    rows: list[tuple[str, ...]] = []
    for row in comparison.itertuples(index=False):
        rows.append(
            (
                f"{row.sector_label} ({row.symbol})",
                str(row.model_label),
                _format_decimal(row.stability_score, digits=1),
                _format_decimal(row.validation_roc_auc, digits=3),
                _format_decimal(row.holdout_roc_auc, digits=3),
                _format_decimal(row.validation_brier_score, digits=3),
                _format_decimal(row.holdout_brier_score, digits=3),
                _format_decimal(row.holdout_sharpe),
                _format_return_pct(row.holdout_cagr),
                str(int(row.holdout_trade_count)),
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Model Audit</p>',
            '  <h2>Validation-To-Holdout Stability By Model</h2>',
            '  <p>Higher stability scores mean the model degraded less from walk-forward validation into the untouched holdout. This is the direct overfitting check, not just a performance ranking.</p>',
            _render_data_table(
                headers=(
                    'Sector',
                    'Model',
                    'Stability',
                    'Val AUC',
                    'Holdout AUC',
                    'Val Brier',
                    'Holdout Brier',
                    'Holdout Sharpe',
                    'Holdout CAGR',
                    'Holdout Trades',
                ),
                rows=rows,
            ),
            '</section>',
        ]
    )


def _render_ml_cost_section(sector_ml_view: dict[str, Any]) -> str:
    if not sector_ml_view.get("available"):
        return ""

    cost_frame = sector_ml_view["cost_sensitivity_frame"].sort_values(
        ["sector_label", "sensitivity_type", "scenario_bps"],
        ascending=[True, True, True],
    )
    rows: list[tuple[str, ...]] = []
    for row in cost_frame.itertuples(index=False):
        rows.append(
            (
                f"{row.sector_label} ({row.symbol})",
                str(row.sensitivity_type).title(),
                f"{float(row.scenario_bps):.0f} bps",
                f"{float(row.total_cost_bps):.0f} bps",
                _format_return_pct(row.cagr),
                _format_decimal(row.sharpe),
                _format_return_pct(row.max_drawdown),
                _format_probability_pct(row.hit_rate),
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Sensitivity</p>',
            '  <h2>Fee And Slippage Sensitivity On The Holdout</h2>',
            '  <p>The model is trained on a 15 bps all-in cost assumption. The table below replays the untouched holdout under separate fee and slippage stress scenarios.</p>',
            _render_data_table(
                headers=(
                    'Sector',
                    'Stress Type',
                    'Scenario',
                    'Total Cost',
                    'Holdout CAGR',
                    'Holdout Sharpe',
                    'Holdout Max DD',
                    'Holdout Hit Rate',
                ),
                rows=rows,
            ),
            '</section>',
        ]
    )


def _render_ml_regime_year_section(sector_ml_view: dict[str, Any]) -> str:
    if not sector_ml_view.get("available"):
        return ""

    regime_rows: list[tuple[str, ...]] = []
    regime_frame = sector_ml_view["regime_performance_frame"].sort_values(
        ["sector_label", "regime_label"],
        ascending=[True, True],
    )
    for row in regime_frame.itertuples(index=False):
        regime_rows.append(
            (
                f"{row.sector_label} ({row.symbol})",
                str(row.regime_label),
                _format_return_pct(row.cagr),
                _format_decimal(row.sharpe),
                _format_return_pct(row.max_drawdown),
                _format_probability_pct(row.hit_rate),
                str(int(row.trade_count)),
            )
        )

    year_rows: list[tuple[str, ...]] = []
    yearly_frame = sector_ml_view["yearly_performance_frame"].sort_values(["year", "sector_label"], ascending=[True, True])
    for row in yearly_frame.itertuples(index=False):
        year_rows.append(
            (
                f"{row.sector_label} ({row.symbol})",
                str(int(row.year)),
                _format_return_pct(row.total_return),
                _format_return_pct(row.cagr),
                _format_decimal(row.sharpe),
                _format_return_pct(row.max_drawdown),
                str(int(row.trade_count)),
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Regime And Year</p>',
            '  <h2>Out-Of-Sample Performance By Regime And Year</h2>',
            '  <p>These tables use only the averaged ensemble and slice the full out-of-sample stream by macro regime and by calendar year.</p>',
            _render_data_table(
                headers=(
                    'Sector',
                    'Regime',
                    'CAGR',
                    'Sharpe',
                    'Max DD',
                    'Hit Rate',
                    'Trades',
                ),
                rows=regime_rows,
            ),
            _render_data_table(
                headers=(
                    'Sector',
                    'Year',
                    'Total Return',
                    'CAGR',
                    'Sharpe',
                    'Max DD',
                    'Trades',
                ),
                rows=year_rows,
            ),
            '</section>',
        ]
    )


def _select_strategy_row(summary_frame: pd.DataFrame, label: str, startswith: bool = False) -> pd.Series:
        if startswith:
                matches = summary_frame.loc[summary_frame["strategy_label"].astype(str).str.startswith(label)]
        else:
                matches = summary_frame.loc[summary_frame["strategy_label"] == label]
        if matches.empty:
                raise KeyError(f"Strategy row not found for {label}")
        return matches.iloc[0]


def _risk_bucket_from_row(label: str, max_drawdown: float | int | None) -> tuple[str, str, str]:
        drawdown = abs(float(max_drawdown or 0.0))
        if "SPY Buy And Hold x" in label:
                return ("Extreme risk / weak reward quality", "#8f2d1f", "Borrowing magnifies the pain faster than it improves the compounding path.")
        if "x3" in label:
                return ("High risk / high reward", "#b85c38", "Reward can be large, but the path is violent and hard to hold in live capital.")
        if drawdown <= 0.33:
                return ("Lower risk / steadier reward", "#2d6a4f", "This is the capital-preservation bucket: smoother path, smaller drawdowns, slower wealth growth.")
        if drawdown <= 0.42:
                return ("Balanced risk / strong reward", "#7a3e2b", "This is the efficient middle: meaningful compounding without borrowing and without catastrophic path risk.")
        return ("Medium risk / lower efficiency", "#6c757d", "This earns a return, but the drawdown path is harsher than the reward profile deserves.")


def _build_executive_summary_view(
    regime_overview: dict[str, Any],
    sector_ml_view: dict[str, Any],
) -> dict[str, Any]:
    history_view = sector_ml_view.get("historical_rotation_view") if isinstance(sector_ml_view, dict) else None
    holdout_view = sector_ml_view.get("holdout_rotation_view") if isinstance(sector_ml_view, dict) else None
    if not isinstance(history_view, dict) or not history_view.get("available"):
        return {"available": False, "message": "Historical strategy summary unavailable."}
    if not isinstance(holdout_view, dict) or not holdout_view.get("available"):
        return {"available": False, "message": "Holdout strategy summary unavailable."}

    history_frame = history_view["strategy_summary_frame"].copy()
    holdout_frame = holdout_view["strategy_summary_frame"].copy()
    reserve_leverage_label = str(history_view.get("reserve_leverage_label") or RESERVE_LEVERAGE_LABEL_PREFIX)
    selected_specs = [
        (RESERVE_STRATEGY_LABEL, "Reserve Rule"),
        ("ML Quality-Weighted Rotation", "Quality Rotation"),
        ("SPY Buy And Hold", "SPY"),
        (reserve_leverage_label, "Reserve x3"),
        ("ML Quality-Weighted Rotation x", "Quality x3"),
        ("SPY Buy And Hold x", "SPY x3"),
    ]

    rows: list[dict[str, Any]] = []
    for lookup_label, short_label in selected_specs:
        startswith = lookup_label.endswith("x")
        history_row = _select_strategy_row(history_frame, lookup_label, startswith=startswith)
        holdout_row = _select_strategy_row(holdout_frame, lookup_label, startswith=startswith)
        bucket_label, bucket_color, bucket_body = _risk_bucket_from_row(
            str(history_row.strategy_label),
            history_row.max_drawdown,
        )
        rows.append(
            {
                "strategy_label": str(history_row.strategy_label),
                "short_label": short_label,
                "bucket_label": bucket_label,
                "bucket_color": bucket_color,
                "bucket_body": bucket_body,
                "history_total_return": float(history_row.total_return),
                "history_cagr": float(history_row.cagr),
                "history_sharpe": float(history_row.sharpe),
                "history_max_drawdown": float(history_row.max_drawdown),
                "holdout_cagr": float(holdout_row.cagr),
                "holdout_sharpe": float(holdout_row.sharpe),
                "holdout_max_drawdown": float(holdout_row.max_drawdown),
                "trade_count": int(history_row.trade_count),
                "turnover_per_year": float(history_row.turnover_per_year),
                "cagr": float(history_row.cagr),
                "max_drawdown": float(history_row.max_drawdown),
                "total_return": float(history_row.total_return),
            }
        )

    strategy_frame = pd.DataFrame(rows)
    return {
        "available": True,
        "strategy_frame": strategy_frame,
        "current": regime_overview["current"],
        "reserve_row": strategy_frame.loc[strategy_frame["short_label"] == "Reserve Rule"].iloc[0],
        "quality_row": strategy_frame.loc[strategy_frame["short_label"] == "Quality Rotation"].iloc[0],
        "reserve_x3_row": strategy_frame.loc[strategy_frame["short_label"] == "Reserve x3"].iloc[0],
        "spy_x3_row": strategy_frame.loc[strategy_frame["short_label"] == "SPY x3"].iloc[0],
    }


def _render_summary_risk_map(strategy_frame: pd.DataFrame) -> str:
        if strategy_frame.empty:
                return ""

        plot_frame = strategy_frame.copy()
        plot_frame["drawdown_abs"] = plot_frame["max_drawdown"].astype(float).abs()
        x_min = float(plot_frame["drawdown_abs"].min())
        x_max = float(plot_frame["drawdown_abs"].max())
        y_min = float(min(plot_frame["cagr"].astype(float).min(), 0.0))
        y_max = float(plot_frame["cagr"].astype(float).max())
        x_span = max(x_max - x_min, 1e-9)
        y_span = max(y_max - y_min, 1e-9)
        width = 920.0
        height = 300.0
        left = 70.0
        right = 28.0
        top = 28.0
        bottom = 42.0

        def x_pos(value: float) -> float:
                return left + ((value - x_min) / x_span) * (width - left - right)

        def y_pos(value: float) -> float:
                return height - bottom - ((value - y_min) / y_span) * (height - top - bottom)

        grid_markup: list[str] = []
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
                y = top + fraction * (height - top - bottom)
                y_value = y_max - fraction * y_span
                grid_markup.append(
                        f'<line x1="{left:.1f}" y1="{y:.1f}" x2="{width - right:.1f}" y2="{y:.1f}" stroke="rgba(125, 139, 153, 0.18)" stroke-width="1"></line>'
                )
                grid_markup.append(
                        f'<text x="12" y="{y + 4:.1f}" fill="#5f6b76" font-size="11">{_format_return_pct(y_value)}</text>'
                )

        points_markup: list[str] = []
        for row in plot_frame.itertuples(index=False):
                x = x_pos(float(row.drawdown_abs))
                y = y_pos(float(row.cagr))
                label = html.escape(str(row.short_label))
                color = str(row.bucket_color)
                points_markup.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="{color}"></circle>')
                points_markup.append(f'<text x="{x + 10:.1f}" y="{y - 10:.1f}" fill="#37404a" font-size="11">{label}</text>')

        return """
<div class="mini-chart">
    <svg viewBox="0 0 920 300" role="img" aria-label="Risk reward map">
        <rect x="0" y="0" width="920" height="300" rx="18" fill="rgba(255,253,248,0.92)"></rect>
        {grid}
        <line x1="{left}" y1="{axis_bottom}" x2="{axis_right}" y2="{axis_bottom}" stroke="#b8b1a7" stroke-width="1.2"></line>
        <line x1="{left}" y1="{top}" x2="{left}" y2="{axis_bottom}" stroke="#b8b1a7" stroke-width="1.2"></line>
        <text x="{left}" y="20" fill="#1b2430" font-size="18" font-family="Iowan Old Style, Georgia, serif">Risk / Reward Map</text>
        <text x="{left}" y="292" fill="#5f6b76" font-size="12">Left is better: smaller drawdown. Up is better: higher CAGR.</text>
        <text x="12" y="20" fill="#5f6b76" font-size="12">CAGR</text>
        <text x="{axis_right_text}" y="292" fill="#5f6b76" font-size="12">Max drawdown</text>
        {points}
    </svg>
</div>
""".format(
                grid="".join(grid_markup),
                left=f"{left:.1f}",
                top=f"{top:.1f}",
                axis_bottom=f"{height - bottom:.1f}",
                axis_right=f"{width - right:.1f}",
                axis_right_text=f"{width - right - 90:.1f}",
                points="".join(points_markup),
        )


def _render_summary_terminal_wealth_chart(strategy_frame: pd.DataFrame) -> str:
        if strategy_frame.empty:
                return ""

        plot_frame = strategy_frame.copy()
        plot_frame["terminal_wealth"] = 100.0 * (1.0 + plot_frame["total_return"].astype(float))
        max_wealth = float(plot_frame["terminal_wealth"].max())
        width = 920.0
        height = 300.0
        left = 58.0
        right = 24.0
        top = 28.0
        bottom = 54.0
        count = max(len(plot_frame.index), 1)
        slot_width = (width - left - right) / count
        bar_width = min(58.0, slot_width * 0.58)

        def bar_height(value: float) -> float:
                return ((value / max(max_wealth, 1e-9)) * (height - top - bottom))

        bars: list[str] = []
        for idx, row in enumerate(plot_frame.itertuples(index=False)):
                x = left + idx * slot_width + (slot_width - bar_width) / 2.0
                h = bar_height(float(row.terminal_wealth))
                y = height - bottom - h
                bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{h:.1f}" rx="10" fill="{row.bucket_color}"></rect>')
                bars.append(f'<text x="{x + bar_width / 2.0:.1f}" y="{y - 8:.1f}" text-anchor="middle" fill="#37404a" font-size="11">${float(row.terminal_wealth):.0f}</text>')
                bars.append(f'<text x="{x + bar_width / 2.0:.1f}" y="{height - 22:.1f}" text-anchor="middle" fill="#5f6b76" font-size="11">{html.escape(str(row.short_label))}</text>')

        return """
<div class="mini-chart">
    <svg viewBox="0 0 920 300" role="img" aria-label="Terminal wealth from 100 dollars">
        <rect x="0" y="0" width="920" height="300" rx="18" fill="rgba(255,253,248,0.92)"></rect>
        <line x1="{left}" y1="{axis_bottom}" x2="{axis_right}" y2="{axis_bottom}" stroke="#b8b1a7" stroke-width="1.2"></line>
        <text x="{left}" y="20" fill="#1b2430" font-size="18" font-family="Iowan Old Style, Georgia, serif">Terminal Wealth From $100</text>
        <text x="{left}" y="292" fill="#5f6b76" font-size="12">Full 2006-2026 walk-forward history. This is why the 2000% numbers appear in the leveraged ML rows.</text>
        {bars}
    </svg>
</div>
""".format(
                left=f"{left:.1f}",
                axis_bottom=f"{height - bottom:.1f}",
                axis_right=f"{width - right:.1f}",
                bars="".join(bars),
        )


def _render_bias_timeline_chart(config: dict[str, Any]) -> str:
        train_years = int(config.get("train_years", 5))
        validation_years = int(config.get("validation_years", 1))
        holdout_start = str(config.get("holdout_start") or "2025-01-01")
        feature_lag = int(config.get("feature_lag", 1))
        purge = int(config.get("purge_size", 5))
        embargo = int(config.get("embargo_size", 5))
        horizon = int(config.get("label_horizon", 5))
        return f"""
<div class="mini-chart">
    <svg viewBox="0 0 920 220" role="img" aria-label="Bias control timeline">
        <rect x="0" y="0" width="920" height="220" rx="18" fill="rgba(255,253,248,0.92)"></rect>
        <text x="36" y="28" fill="#1b2430" font-size="18" font-family="Iowan Old Style, Georgia, serif">Why This Is Not Forward-Looking</text>
        <rect x="36" y="58" width="220" height="72" rx="16" fill="#f3ebe1" stroke="#d5cfc5"></rect>
        <text x="52" y="86" fill="#1b2430" font-size="15">Train</text>
        <text x="52" y="108" fill="#5f6b76" font-size="12">{train_years}-year expanding window</text>
        <text x="52" y="126" fill="#5f6b76" font-size="12">features lagged {feature_lag} bar</text>

        <rect x="306" y="58" width="220" height="72" rx="16" fill="#f3ebe1" stroke="#d5cfc5"></rect>
        <text x="322" y="86" fill="#1b2430" font-size="15">Validate</text>
        <text x="322" y="108" fill="#5f6b76" font-size="12">{validation_years}-year walk-forward test</text>
        <text x="322" y="126" fill="#5f6b76" font-size="12">purge {purge} bars, embargo {embargo} bars</text>

        <rect x="576" y="58" width="308" height="72" rx="16" fill="#f3ebe1" stroke="#d5cfc5"></rect>
        <text x="592" y="86" fill="#1b2430" font-size="15">Holdout And Execution</text>
        <text x="592" y="108" fill="#5f6b76" font-size="12">untouched holdout starts {html.escape(holdout_start)}</text>
        <text x="592" y="126" fill="#5f6b76" font-size="12">trade one bar later, hold {horizon} bars</text>

        <line x1="256" y1="94" x2="306" y2="94" stroke="#7a3e2b" stroke-width="2"></line>
        <line x1="526" y1="94" x2="576" y2="94" stroke="#7a3e2b" stroke-width="2"></line>
        <text x="36" y="168" fill="#5f6b76" font-size="12">Macro regime labels are used to explain results, not to generate historical signals. Sector quality priors come only from the pre-holdout validation window.</text>
        <text x="36" y="188" fill="#5f6b76" font-size="12">Reserve deployment uses only the SPY drawdown visible on the signal date. There is no future return, future regime, or future allocation leak in the benchmark path.</text>
    </svg>
</div>
"""


def _render_executive_summary_html(
    generated_at: str,
    regime_overview: dict[str, Any],
    sector_ml_view: dict[str, Any],
) -> str:
    summary_view = _build_executive_summary_view(
        regime_overview=regime_overview,
        sector_ml_view=sector_ml_view,
    )
    if not summary_view.get("available"):
        return "<html><body><p>Executive summary unavailable.</p></body></html>"

    strategy_frame = summary_view["strategy_frame"]
    reserve_row = summary_view["reserve_row"]
    quality_row = summary_view["quality_row"]
    reserve_x3_row = summary_view["reserve_x3_row"]
    spy_x3_row = summary_view["spy_x3_row"]
    current = summary_view["current"]

    risk_cards = []
    for label in ["Reserve Rule", "Quality Rotation", "Reserve x3", "SPY x3"]:
        row = strategy_frame.loc[strategy_frame["short_label"] == label].iloc[0]
        risk_cards.append(
            "\n".join(
                [
                    '<article class="summary-card">',
                    f'  <p class="summary-tag">{html.escape(str(row.bucket_label))}</p>',
                    f'  <h3>{html.escape(str(row.short_label))}</h3>',
                    f'  <p class="tight-copy">{html.escape(str(row.bucket_body))}</p>',
                    f'  <p class="metric-line">CAGR {_format_return_pct(row.history_cagr)} | Max DD {_format_return_pct(row.history_max_drawdown)}</p>',
                    '</article>',
                ]
            )
        )

    strategy_rows: list[str] = []
    for row in strategy_frame.itertuples(index=False):
        strategy_rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.short_label))}</td>"
            f"<td>{html.escape(str(row.bucket_label))}</td>"
            f"<td>{_format_return_pct(row.history_cagr)}</td>"
            f"<td>{_format_return_pct(row.history_max_drawdown)}</td>"
            f"<td>{_format_decimal(row.history_sharpe)}</td>"
            f"<td>{_format_return_pct(row.holdout_cagr)}</td>"
            f"<td>{_format_return_pct(row.holdout_max_drawdown)}</td>"
            "</tr>"
        )

    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Sector Rotation Executive Summary</title>
                <style>
        @page {{
            size: 11in 8.5in;
            margin: 0.32in;
        }}
        :root {{
            --bg: #f4efe7;
            --sheet: #fffdf8;
            --ink: #1b2430;
            --muted: #5f6b76;
            --line: #d5cfc5;
            --accent: #7a3e2b;
            --green: #2d6a4f;
            --orange: #b85c38;
            --red: #8f2d1f;
        }}
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; background: var(--bg); color: var(--ink); font-family: "Iowan Old Style", Georgia, serif; }}
        .sheet {{ width: 10.36in; height: 7.76in; margin: 0 auto; padding: 0.28in 0.34in 0.3in; background: var(--sheet); page-break-after: always; overflow: hidden; }}
        .sheet:last-child {{ page-break-after: auto; }}
        .eyebrow {{ margin: 0 0 8px; font-size: 12px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--accent); }}
        h1, h2, h3 {{ margin: 0; line-height: 1.1; }}
        h1 {{ font-size: 40px; max-width: 11ch; }}
        h2 {{ font-size: 24px; margin-bottom: 8px; }}
        h3 {{ font-size: 16px; margin-bottom: 8px; }}
        p {{ margin: 0; color: var(--muted); line-height: 1.42; font-size: 13px; }}
        .hero {{ display: grid; grid-template-columns: 1.12fr 0.88fr; gap: 14px; align-items: start; margin-bottom: 14px; }}
        .hero-panel, .principle-panel, .summary-card, .table-panel {{ border: 1px solid var(--line); border-radius: 18px; padding: 14px; background: rgba(255,253,248,0.96); }}
        .meta-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }}
        .meta-pill {{ padding: 6px 10px; border: 1px solid rgba(122,62,43,0.14); border-radius: 999px; color: var(--ink); background: rgba(243,235,225,0.82); font-size: 12px; }}
        .principles {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 14px; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 12px 0 14px; }}
        .summary-tag {{ margin: 0 0 8px; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); }}
        .tight-copy {{ min-height: 36px; }}
        .metric-line {{ margin-top: 10px; color: var(--ink); font-size: 12px; }}
        .mini-chart {{ margin-top: 12px; border: 1px solid var(--line); border-radius: 18px; overflow: hidden; }}
        .table-panel {{ margin-top: 14px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
        th, td {{ padding: 8px 9px; text-align: left; border-bottom: 1px solid rgba(213,207,197,0.7); }}
        th {{ font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); background: rgba(244,237,225,0.75); }}
        tr:last-child td {{ border-bottom: none; }}
        .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
        .callout {{ border-left: 4px solid var(--accent); padding-left: 16px; color: var(--ink); }}
        ul {{ margin: 8px 0 0; padding-left: 18px; color: var(--muted); }}
        li {{ margin-bottom: 5px; font-size: 13px; line-height: 1.32; }}
        @media print {{
            body {{ background: white; }}
            .sheet {{ width: auto; margin: 0; box-shadow: none; }}
        }}
    </style>
</head>
<body>
    <section class=\"sheet\">
        <div class=\"hero\">
            <div class=\"hero-panel\">
                <p class=\"eyebrow\">Executive Summary</p>
                <h1>What The Backtest Is Actually Saying</h1>
                <p>This is a short decision memo, not the full report. It separates the investable core from the high-reward but hard-to-live-through ideas. The goal is simple: earn enough, survive the bad years, and avoid fooling ourselves with forward-looking bias.</p>
                <div class=\"meta-row\">
                    <span class=\"meta-pill\">{html.escape(generated_at)}</span>
                    <span class=\"meta-pill\">Current regime: {html.escape(str(current['regime_label']))}</span>
                    <span class=\"meta-pill\">Quadrant: {html.escape(str(current['quadrant_label']))}</span>
                    <span class=\"meta-pill\">History tested: 2006-2026</span>
                </div>
            </div>
            <div class=\"hero-panel\">
                <p class=\"eyebrow\">Bottom Line</p>
                <h2>Keep The Unlevered Reserve Rule As Core</h2>
                <p class=\"callout\">The best balanced engine is the unlevered quality rotation, but the most usable live portfolio is still the unlevered reserve rule. The x3 variants create big headline returns and unacceptable path risk. A 90% drawdown is not theoretical here.</p>
                <ul>
                    <li>Best unlevered growth engine: Quality Rotation, about {_format_return_pct(quality_row.history_cagr)} CAGR with {_format_return_pct(quality_row.history_max_drawdown)} max drawdown.</li>
                    <li>Best steadier-risk profile: Reserve Rule, about {_format_return_pct(reserve_row.history_cagr)} CAGR with {_format_return_pct(reserve_row.history_max_drawdown)} max drawdown.</li>
                    <li>Why the 2000% number appears: Quality x3 compounded from a much riskier path; it is a leveraged total-return figure, not an annual rate.</li>
                    <li>What not to ignore: SPY x3 still ended near {_format_return_pct(spy_x3_row.history_cagr)} CAGR but with {_format_return_pct(spy_x3_row.history_max_drawdown)} max drawdown.</li>
                </ul>
            </div>
        </div>

        <div class=\"principles\">
            <div class=\"principle-panel\">
                <p class=\"eyebrow\">Principle 1</p>
                <h3>Protect The Downside First</h3>
                <p>The reserve rule earns less than the fastest strategy, but it keeps the path smoother. That matters because strategies only work if you can hold them through the bad times.</p>
            </div>
            <div class=\"principle-panel\">
                <p class=\"eyebrow\">Principle 2</p>
                <h3>Borrow Only After You Earn The Right</h3>
                <p>Leverage is not alpha. It amplifies whatever quality already exists. In this dataset, the x3 variants raise reward and slash survivability.</p>
            </div>
            <div class=\"principle-panel\">
                <p class=\"eyebrow\">Principle 3</p>
                <h3>Separate Prediction From Proof</h3>
                <p>The model signal is one thing. The proof is the untouched holdout and the walk-forward history. They are both shown here, separately.</p>
            </div>
        </div>

                <div class=\"summary-grid\">
                    {''.join(risk_cards)}
                </div>

                {_render_summary_risk_map(strategy_frame)}
    </section>

    <section class=\"sheet\">
        <p class=\"eyebrow\">Page Two</p>
        <h2>Simple Scorecard And Bias Controls</h2>
                <p>This page answers two questions. Which ideas belong in the low-risk, balanced, and high-risk buckets? And why this is not a forward-looking backtest?</p>

                {_render_summary_terminal_wealth_chart(strategy_frame)}

                <div class=\"two-col\" style=\"margin-top: 12px;\">
            <div class=\"table-panel\">
                <p class=\"eyebrow\">Risk Ladder</p>
                <h3>High Reward Is Not The Same As High Quality</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Strategy</th>
                            <th>Bucket</th>
                            <th>History CAGR</th>
                            <th>History Max DD</th>
                            <th>Sharpe</th>
                            <th>Holdout CAGR</th>
                            <th>Holdout Max DD</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(strategy_rows)}
                    </tbody>
                </table>
            </div>
            <div class=\"table-panel\">
                <p class=\"eyebrow\">Simple Read</p>
                <h3>How To Use The Buckets</h3>
                <ul>
                    <li><strong>Lower risk / steadier reward:</strong> the reserve rule. This is the most usable sleeve for real capital because drawdown is controlled and turnover is low.</li>
                    <li><strong>Balanced risk / strong reward:</strong> the unlevered quality rotation. This is the best pure alpha engine, but it asks for more turnover and a rougher path.</li>
                    <li><strong>High risk / high reward:</strong> the reserve x3 sleeve and the quality x3 model. These are tactical ideas, not default policy portfolios.</li>
                    <li><strong>Extreme risk / weak reward quality:</strong> SPY x3. It proves that leverage alone is not a strategy.</li>
                </ul>
                <p class=\"callout\" style=\"margin-top: 12px;\">A 90% drawdown matters even if the terminal wealth looks large. The path can disqualify the strategy.</p>
            </div>
        </div>

        <div class=\"two-col\" style=\"margin-top: 12px;\">
            <div class=\"table-panel\">
                <p class=\"eyebrow\">Why This Is Not Forward-Looking</p>
                <h3>Controls Against Bias</h3>
                <ul>
                    <li>Features are lagged one bar before training and prediction.</li>
                    <li>Each walk-forward fold uses a {int(sector_ml_view['config']['purge_size'])}-bar purge and a {int(sector_ml_view['config']['embargo_size'])}-bar embargo.</li>
                    <li>The final holdout starts on {html.escape(str(sector_ml_view['config']['holdout_start']))} and is never used for model selection.</li>
                    <li>Signals are executed one bar after the signal date and held for {int(sector_ml_view['config']['label_horizon'])} bars.</li>
                    <li>Validation quality priors are estimated only from the pre-holdout window.</li>
                    <li>Macro regime labels explain the results but do not generate the historical trades.</li>
                </ul>
            </div>
            <div class=\"table-panel\">
                <p class=\"eyebrow\">Decision</p>
                <h3>What To Stick To</h3>
                <ul>
                    <li><strong>Core portfolio:</strong> unlevered reserve cash rule.</li>
                    <li><strong>Growth sleeve:</strong> unlevered quality rotation if you can tolerate higher turnover and deeper drawdowns.</li>
                    <li><strong>Tactical only:</strong> reserve x3 drawdown sleeve, and only if you explicitly accept much deeper drawdowns.</li>
                    <li><strong>Avoid as core:</strong> SPY x3 and the full x3 rotation variants. They generate striking terminal wealth and unacceptable path risk.</li>
                </ul>
                <p class=\"callout\" style=\"margin-top: 18px;\">The safest honest reading is: there is evidence of edge, there is no evidence that leverage improves the quality of that edge enough to deserve core capital.</p>
            </div>
        </div>
    </section>
</body>
</html>
"""


def _wrap_pdf_paragraph(text: str, width: int) -> str:
    return textwrap.fill(str(text), width=width)


def _wrap_pdf_bullets(items: list[str], width: int) -> str:
    return "\n".join(
        textwrap.fill(item, width=width, initial_indent="• ", subsequent_indent="  ")
        for item in items
    )


def _pdf_add_panel(
    axis: Any,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    eyebrow: str | None = None,
    title: str | None = None,
    body: str | None = None,
    title_size: float = 13.0,
    body_size: float = 9.5,
    facecolor: str = PANEL_BACKGROUND,
    accent: bool = False,
) -> None:
    panel = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.012,rounding_size=0.02",
        linewidth=1.0,
        edgecolor=GRID_COLOR,
        facecolor=facecolor,
        transform=axis.transAxes,
    )
    axis.add_patch(panel)

    text_x = x + 0.018
    if accent:
        axis.plot(
            [x + 0.015, x + 0.015],
            [y + 0.028, y + height - 0.028],
            color="#7a3e2b",
            linewidth=2.4,
            solid_capstyle="round",
            transform=axis.transAxes,
        )
        text_x = x + 0.03

    cursor_y = y + height - 0.028
    if eyebrow:
        axis.text(
            text_x,
            cursor_y,
            eyebrow.upper(),
            transform=axis.transAxes,
            fontsize=8.2,
            fontweight="bold",
            color="#7a3e2b",
            va="top",
            family="serif",
        )
        cursor_y -= 0.042
    if title:
        axis.text(
            text_x,
            cursor_y,
            title,
            transform=axis.transAxes,
            fontsize=title_size,
            fontweight="bold",
            color=TEXT_COLOR,
            va="top",
            family="serif",
        )
        cursor_y -= 0.053 if title_size >= 18 else 0.046
    if body:
        axis.text(
            text_x,
            cursor_y,
            body,
            transform=axis.transAxes,
            fontsize=body_size,
            color=MUTED_TEXT_COLOR,
            va="top",
            family="serif",
            linespacing=1.35,
        )


def _draw_pdf_risk_map(axis: Any, strategy_frame: pd.DataFrame) -> None:
    plot_frame = strategy_frame.copy()
    plot_frame["drawdown_abs"] = plot_frame["max_drawdown"].astype(float).abs()

    axis.set_facecolor(PANEL_BACKGROUND)
    axis.scatter(
        plot_frame["drawdown_abs"],
        plot_frame["cagr"],
        s=70,
        c=plot_frame["bucket_color"],
        zorder=3,
    )
    for row in plot_frame.itertuples(index=False):
        axis.annotate(
            str(row.short_label),
            (float(row.drawdown_abs), float(row.cagr)),
            textcoords="offset points",
            xytext=(7, 5),
            fontsize=8.5,
            color=TEXT_COLOR,
            family="serif",
        )

    axis.set_title("Risk / Reward Map", loc="left", fontsize=14, color=TEXT_COLOR, family="serif", pad=10)
    axis.grid(color=GRID_COLOR, alpha=0.55, linewidth=0.8)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.spines["left"].set_color(GRID_COLOR)
    axis.spines["bottom"].set_color(GRID_COLOR)
    axis.tick_params(colors=MUTED_TEXT_COLOR, labelsize=8.5)
    axis.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.0%}"))
    axis.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.0%}"))
    axis.set_xlabel("Max drawdown", color=MUTED_TEXT_COLOR, fontsize=9)
    axis.set_ylabel("CAGR", color=MUTED_TEXT_COLOR, fontsize=9)
    axis.text(
        0.0,
        -0.24,
        "Left is better. Up is better. Full 2006-2026 walk-forward history only.",
        transform=axis.transAxes,
        fontsize=8.5,
        color=MUTED_TEXT_COLOR,
        family="serif",
    )


def _draw_pdf_terminal_wealth(axis: Any, strategy_frame: pd.DataFrame) -> None:
    plot_frame = strategy_frame.copy()
    plot_frame["terminal_wealth"] = 100.0 * (1.0 + plot_frame["total_return"].astype(float))

    bars = axis.bar(
        plot_frame["short_label"],
        plot_frame["terminal_wealth"],
        color=plot_frame["bucket_color"],
        width=0.62,
        zorder=3,
    )
    for bar, row in zip(bars, plot_frame.itertuples(index=False), strict=False):
        axis.text(
            bar.get_x() + bar.get_width() / 2.0,
            float(row.terminal_wealth) * 1.02,
            f"${float(row.terminal_wealth):,.0f}",
            ha="center",
            va="bottom",
            fontsize=8.3,
            color=TEXT_COLOR,
            family="serif",
        )

    axis.set_facecolor(PANEL_BACKGROUND)
    axis.set_title("Terminal Wealth From $100", loc="left", fontsize=14, color=TEXT_COLOR, family="serif", pad=10)
    axis.grid(axis="y", color=GRID_COLOR, alpha=0.55, linewidth=0.8)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.spines["left"].set_color(GRID_COLOR)
    axis.spines["bottom"].set_color(GRID_COLOR)
    axis.tick_params(axis="x", labelrotation=0, labelsize=8.5, colors=MUTED_TEXT_COLOR)
    axis.tick_params(axis="y", labelsize=8.5, colors=MUTED_TEXT_COLOR)
    axis.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"${value:,.0f}"))
    axis.set_ylabel("Terminal wealth", color=MUTED_TEXT_COLOR, fontsize=9)
    axis.text(
        0.0,
        -0.20,
        "This is why the leveraged rows show 2000%+ total return while still carrying severe path risk.",
        transform=axis.transAxes,
        fontsize=8.5,
        color=MUTED_TEXT_COLOR,
        family="serif",
    )


def _render_executive_summary_pdf(
    pdf_path: Path,
    generated_at: str,
    regime_overview: dict[str, Any],
    sector_ml_view: dict[str, Any],
) -> bool:
    summary_view = _build_executive_summary_view(
        regime_overview=regime_overview,
        sector_ml_view=sector_ml_view,
    )
    if not summary_view.get("available"):
        return False

    strategy_frame = summary_view["strategy_frame"]
    reserve_row = summary_view["reserve_row"]
    quality_row = summary_view["quality_row"]
    reserve_x3_row = summary_view["reserve_x3_row"]
    spy_x3_row = summary_view["spy_x3_row"]
    current = summary_view["current"]
    config = sector_ml_view["config"]

    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    with PdfPages(pdf_path) as pdf:
        page_one = plt.figure(figsize=(11.0, 8.5), facecolor=PAGE_BACKGROUND)
        canvas_one = page_one.add_axes([0.0, 0.0, 1.0, 1.0])
        canvas_one.axis("off")

        hero_body = "\n\n".join(
            [
                _wrap_pdf_paragraph(
                    "This is a short decision memo, not the full report. It separates the investable core from the eye-catching but hard-to-survive ideas.",
                    66,
                ),
                _wrap_pdf_paragraph(
                    f"{generated_at} | Current regime: {current['regime_label']} | Quadrant: {current['quadrant_label']} | History tested: 2006-2026.",
                    74,
                ),
            ]
        )
        bottom_line = _wrap_pdf_bullets(
            [
                f"Best unlevered growth engine: Quality Rotation at about {_format_return_pct(quality_row.history_cagr)} CAGR with {_format_return_pct(quality_row.history_max_drawdown)} max drawdown.",
                f"Best steadier live profile: Reserve Rule at about {_format_return_pct(reserve_row.history_cagr)} CAGR with {_format_return_pct(reserve_row.history_max_drawdown)} max drawdown.",
                "The 2000% number is total return in the leveraged ML path, not an annual rate.",
                f"SPY x3 shows why leverage alone is dangerous: {_format_return_pct(spy_x3_row.history_cagr)} CAGR with {_format_return_pct(spy_x3_row.history_max_drawdown)} max drawdown.",
            ],
            45,
        )
        _pdf_add_panel(
            canvas_one,
            0.04,
            0.75,
            0.54,
            0.19,
            eyebrow="Executive Summary",
            title="What The Backtest Is Actually Saying",
            body=hero_body,
            title_size=22,
            body_size=10,
        )
        _pdf_add_panel(
            canvas_one,
            0.61,
            0.75,
            0.35,
            0.19,
            eyebrow="Bottom Line",
            title="Keep The Unlevered Reserve Rule As Core",
            body=bottom_line,
            title_size=15,
            body_size=9.2,
            accent=True,
        )

        principle_specs = [
            ("Principle 1", "Protect The Downside First", "The reserve rule earns less than the fastest strategy, but it keeps the path smoother. That matters because strategies only work if you can hold them."),
            ("Principle 2", "Borrow Only After You Earn The Right", "Leverage is not alpha. It amplifies whatever quality already exists. Here it raises reward and cuts survivability."),
            ("Principle 3", "Separate Prediction From Proof", "The model signal is one thing. The proof is the untouched holdout and the walk-forward history. They are separate on purpose."),
        ]
        for idx, (eyebrow, title, body) in enumerate(principle_specs):
            _pdf_add_panel(
                canvas_one,
                0.04 + idx * 0.31,
                0.58,
                0.27,
                0.12,
                eyebrow=eyebrow,
                title=title,
                body=_wrap_pdf_paragraph(body, 32),
                title_size=12.5,
                body_size=8.8,
            )

        for idx, label in enumerate(["Reserve Rule", "Quality Rotation", "Reserve x3", "SPY x3"]):
            row = strategy_frame.loc[strategy_frame["short_label"] == label].iloc[0]
            body = "\n".join(
                [
                    _wrap_pdf_paragraph(str(row.bucket_body), 28),
                    f"CAGR {_format_return_pct(row.history_cagr)} | Max DD {_format_return_pct(row.history_max_drawdown)}",
                ]
            )
            _pdf_add_panel(
                canvas_one,
                0.04 + idx * 0.23,
                0.41,
                0.20,
                0.12,
                eyebrow=str(row.bucket_label),
                title=str(row.short_label),
                body=body,
                title_size=12.5,
                body_size=8.5,
                facecolor="#fffaf2",
            )

        risk_axis = page_one.add_axes([0.06, 0.08, 0.88, 0.24])
        _draw_pdf_risk_map(risk_axis, strategy_frame)
        pdf.savefig(page_one, facecolor=page_one.get_facecolor())
        plt.close(page_one)

        page_two = plt.figure(figsize=(11.0, 8.5), facecolor=PAGE_BACKGROUND)
        canvas_two = page_two.add_axes([0.0, 0.0, 1.0, 1.0])
        canvas_two.axis("off")
        canvas_two.text(0.04, 0.95, "Simple Scorecard And Bias Controls", fontsize=22, fontweight="bold", color=TEXT_COLOR, family="serif", va="top")
        canvas_two.text(
            0.04,
            0.91,
            "Which ideas belong in the low-risk, balanced, and high-risk buckets? And why this is not a forward-looking backtest?",
            fontsize=10,
            color=MUTED_TEXT_COLOR,
            family="serif",
            va="top",
        )

        wealth_axis = page_two.add_axes([0.06, 0.57, 0.88, 0.24])
        _draw_pdf_terminal_wealth(wealth_axis, strategy_frame)

        _pdf_add_panel(
            canvas_two,
            0.04,
            0.10,
            0.55,
            0.36,
            eyebrow="Risk Ladder",
            title="High Reward Is Not The Same As High Quality",
            body="",
            title_size=15,
        )
        table_axis = page_two.add_axes([0.06, 0.14, 0.51, 0.26])
        table_axis.axis("off")
        table_rows = [
            [
                str(row.short_label),
                str(row.bucket_label),
                _format_return_pct(row.history_cagr),
                _format_return_pct(row.history_max_drawdown),
                _format_return_pct(row.holdout_cagr),
                _format_return_pct(row.holdout_max_drawdown),
            ]
            for row in strategy_frame.itertuples(index=False)
        ]
        table = table_axis.table(
            cellText=table_rows,
            colLabels=["Strategy", "Bucket", "Hist CAGR", "Hist DD", "Holdout CAGR", "Holdout DD"],
            loc="center",
            cellLoc="left",
            colWidths=[0.16, 0.30, 0.10, 0.10, 0.12, 0.12],
        )
        table.auto_set_font_size(False)
        table.set_fontsize(8.0)
        table.scale(1.0, 1.45)
        for (row_idx, col_idx), cell in table.get_celld().items():
            cell.set_edgecolor(GRID_COLOR)
            if row_idx == 0:
                cell.set_facecolor("#f4ede1")
                cell.set_text_props(color=MUTED_TEXT_COLOR, weight="bold")
            else:
                cell.set_facecolor(PANEL_BACKGROUND)
                if col_idx == 0:
                    cell.set_text_props(color=TEXT_COLOR, weight="bold")
                else:
                    cell.set_text_props(color=MUTED_TEXT_COLOR)

        bias_body = _wrap_pdf_bullets(
            [
                f"Features are lagged {int(config['feature_lag'])} bar before training and prediction.",
                f"Each fold uses a {int(config['purge_size'])}-bar purge and {int(config['embargo_size'])}-bar embargo.",
                f"The final holdout starts on {config['holdout_start']} and is never used for model selection.",
                f"Signals execute one bar later and hold {int(config['label_horizon'])} bars.",
                "Macro regime labels explain results but do not generate the historical trades.",
            ],
            34,
        )
        _pdf_add_panel(
            canvas_two,
            0.64,
            0.26,
            0.31,
            0.20,
            eyebrow="Why This Is Not Forward-Looking",
            title="Controls Against Bias",
            body=bias_body,
            title_size=14,
            body_size=8.8,
        )

        decision_body = _wrap_pdf_bullets(
            [
                "Core portfolio: unlevered reserve cash rule.",
                "Growth sleeve: unlevered quality rotation if you can tolerate the deeper drawdown path.",
                "Tactical only: reserve x3 sleeve, and only if you explicitly accept much deeper drawdowns.",
                "Avoid as core: SPY x3 and the full x3 rotation variants.",
            ],
            34,
        )
        _pdf_add_panel(
            canvas_two,
            0.64,
            0.10,
            0.31,
            0.12,
            eyebrow="Decision",
            title="What To Stick To",
            body=decision_body,
            title_size=14,
            body_size=8.8,
            accent=True,
        )
        canvas_two.text(
            0.64,
            0.06,
            _wrap_pdf_paragraph(
                "The safest honest reading is: there is evidence of edge, but no evidence that leverage improves the quality of that edge enough to deserve core capital.",
                54,
            ),
            fontsize=8.8,
            color=MUTED_TEXT_COLOR,
            family="serif",
            va="top",
        )

        pdf.savefig(page_two, facecolor=page_two.get_facecolor())
        plt.close(page_two)

    return True


def _render_rotation_playbook_html(
        generated_at: str,
        regime_overview: dict[str, Any],
        sector_ml_view: dict[str, Any],
        live_ml_view: dict[str, Any],
) -> str:
        current = regime_overview["current"]
        current_regime = str(current["regime_label"])
        current_quadrant = str(current["quadrant_label"])
        config = sector_ml_view.get("config") or {}
        signal_date = (
                pd.Timestamp(live_ml_view["signal_date"]).strftime("%Y-%m-%d")
                if live_ml_view.get("signal_date") is not None
                else "n/a"
        )
        threshold = float(config.get("signal_threshold", 0.55))
        hold_bars = int(config.get("label_horizon", 5))
        feature_lag = int(config.get("feature_lag", 1))
        top_n = int(config.get("top_n", 3))
        cash_weight = float(config.get("reserve_cash_weight", 0.40))
        core_weight = float(config.get("core_sector_weight", 0.60))
        first_drawdown = float(config.get("reserve_drawdown_first", 0.05))
        second_drawdown = float(config.get("reserve_drawdown_second", 0.10))
        full_drawdown = float(config.get("reserve_drawdown_full", 0.20))
        first_deploy = float(config.get("reserve_deploy_first", 0.10))
        second_deploy = float(config.get("reserve_deploy_second", 0.20))
        full_deploy = max(0.0, 1.0 - first_deploy - second_deploy)

        allocation_frame = live_ml_view.get("allocation_frame")
        full_frame = live_ml_view.get("full_frame")

        cards: list[str] = [
                _render_stat_card(
                        title="Current macro state",
                        body=(
                                f"Regime: {current_regime}. Quadrant: {current_quadrant}. The live rotation page uses the latest complete signal dated {signal_date}."
                        ),
                        tag="Now",
                ),
                _render_stat_card(
                        title="Core portfolio rule",
                        body=(
                                f"Keep {_format_weight_pct(cash_weight)} in cash by rule. Only the {_format_weight_pct(core_weight)} equity sleeve rotates across sectors."
                        ),
                        tag="Sizing",
                ),
                _render_stat_card(
                        title="When to rotate",
                        body=(
                                f"Re-evaluate every {hold_bars} trading bars, using features lagged {feature_lag} bar and executing one bar after the signal."
                        ),
                        tag="Timing",
                ),
                _render_stat_card(
                        title="Eligibility rule",
                        body=(
                                f"A sector qualifies for the live basket only if its ensemble probability is at least {_format_probability_pct(threshold)}. If nothing qualifies, the page falls back to the top combined scores."
                        ),
                        tag="Filter",
                ),
        ]

        current_rows: list[tuple[str, ...]] = []
        instruction_lines: list[str] = []
        if isinstance(allocation_frame, pd.DataFrame) and not allocation_frame.empty:
                for row in allocation_frame.itertuples(index=False):
                        current_rows.append(
                                (
                                        f"{row.sector_label} ({row.symbol})",
                                        str(row.family),
                                        _format_weight_pct(row.portfolio_weight),
                                        _format_weight_pct(row.sleeve_weight),
                                        _format_probability_pct(row.ensemble_probability),
                                    _format_return_pct(row.recent_advance_20d),
                                    _format_return_pct(row.recent_advance_60d),
                                    f"{float(row.runup_penalty):.2f}x",
                                        _format_decimal(row.combined_live_score, 3),
                                        _format_decimal(row.entry_score, 3),
                                        _format_decimal(row.validation_quality_score, 3),
                                )
                        )
                        instruction_lines.append(
                                f"Rotate {_format_weight_pct(row.portfolio_weight)} of the full portfolio into {row.sector_label} ({row.symbol})."
                        )
                selected_count = len(allocation_frame.index)
                cards.append(
                        _render_stat_card(
                                title="Where to rotate now",
                                body=(
                                        " ".join(instruction_lines)
                                        if instruction_lines
                                        else "No sector currently qualifies, so the equity sleeve should stay out of rotation until the next signal."
                                ),
                                tag="Action",
                        )
                )
                cards.append(
                        _render_stat_card(
                                title="Basket breadth",
                                body=(
                                        f"{selected_count} sector{'s' if selected_count != 1 else ''} currently pass the live filter, versus a nominal target basket size of up to {top_n} primary sectors."
                                ),
                                tag="Breadth",
                        )
                )
        else:
                cards.append(
                        _render_stat_card(
                                title="Where to rotate now",
                                body="No eligible live basket was available from the current signal, so no rotation instruction can be issued from this report build.",
                                tag="Action",
                        )
                )

        watch_rows: list[tuple[str, ...]] = []
        if isinstance(full_frame, pd.DataFrame) and not full_frame.empty:
                watch_frame = full_frame.head(6).copy()
                for row in watch_frame.itertuples(index=False):
                        watch_rows.append(
                                (
                                        f"{row.sector_label} ({row.symbol})",
                                        "Yes" if bool(row.recommended_live) else "No",
                                        _format_probability_pct(row.ensemble_probability),
                                    _format_return_pct(row.recent_advance_20d),
                                    f"{float(row.runup_penalty):.2f}x",
                                        _format_decimal(row.combined_live_score, 3),
                                        _format_decimal(row.entry_score, 3),
                                        _format_decimal(row.best_overfit_stability_score, 1),
                                        _format_decimal(row.ensemble_holdout_sharpe, 2),
                                )
                        )

        reserve_rows = [
                (
                        f"SPY drawdown at least {_format_return_pct(-first_drawdown)}",
                        f"Deploy {_format_weight_pct(first_deploy * cash_weight)} of the full portfolio from reserve cash.",
                        "Keep the rest of the reserve in cash until a deeper drawdown appears.",
                ),
                (
                        f"SPY drawdown at least {_format_return_pct(-second_drawdown)}",
                        f"Deploy another {_format_weight_pct(second_deploy * cash_weight)} of the full portfolio.",
                        "This is cumulative on top of the first tier.",
                ),
                (
                        f"SPY drawdown at least {_format_return_pct(-full_drawdown)}",
                        f"Deploy the remaining {_format_weight_pct(full_deploy * cash_weight)} of the full portfolio.",
                        "The reserve sleeve is fully mobilized only at deep stress.",
                ),
                (
                        "SPY returns to a fresh high",
                    "Rotate the deployed SPY reserve sleeve back to cash.",
                        "The reserve bucket rebuilds only after the drawdown is fully repaired.",
                ),
        ]

        rules_rows = [
                (
                        "Step 1",
                        "Classify the macro regime",
                        f"Use the current regime and quadrant as the macro prior. Right now that is {current_regime} in {current_quadrant}.",
                ),
                (
                        "Step 2",
                        "Read the latest complete ML signal",
                        f"Only the fully known signal dated {signal_date} is allowed into the live basket. There is no intraperiod look-ahead refresh.",
                ),
                (
                        "Step 3",
                        "Filter sectors by live probability",
                        f"Require ensemble probability >= {_format_probability_pct(threshold)} before a sector can enter the live basket.",
                ),
                (
                        "Step 4",
                        "Rank the eligible sectors",
                        "Score sectors with 35% macro regime rank, 18% live probability rank, 13% quality-weighted ML rank, 10% validation quality, 9% model stability, 5% holdout Sharpe, and 10% run-up headroom so already-extended sectors are less likely to dominate the basket.",
                ),
                (
                        "Step 5",
                        "Allocate the equity sleeve",
                        f"Spread the {_format_weight_pct(core_weight)} equity sleeve across the highest combined scores. The rest stays in cash by design.",
                ),
                (
                        "Step 6",
                        "Use reserve deployment only in drawdowns",
                        "The reserve rule is separate from the sector basket. It reacts only to visible SPY drawdowns, buys SPY with the reserve sleeve, and moves back to cash after a new high.",
                ),
        ]

        current_table = ""
        if current_rows:
                current_table = _render_data_table(
                        headers=(
                                "Current sector",
                                "Role",
                                "Portfolio weight",
                                "Within 60% sleeve",
                                "ML probability",
                            "Advance 20D",
                            "Advance 60D",
                            "Guardrail",
                                "Combined score",
                                "Regime score",
                                "Validation quality",
                        ),
                        rows=current_rows,
                )

        watch_table = ""
        if watch_rows:
                watch_table = _render_data_table(
                        headers=(
                                "Sector",
                                "In live basket",
                                "ML probability",
                            "Advance 20D",
                            "Guardrail",
                                "Combined score",
                                "Regime score",
                                "Stability",
                                "Holdout Sharpe",
                        ),
                        rows=watch_rows,
                )

        return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Sector Rotation Playbook</title>
    <style>
        :root {{
            --bg: {PAGE_BACKGROUND};
            --panel: {PANEL_BACKGROUND};
            --ink: {TEXT_COLOR};
            --muted: {MUTED_TEXT_COLOR};
            --line: {GRID_COLOR};
            --accent: #7a3e2b;
            --accent-two: #154c5c;
            --shadow: 0 24px 48px rgba(27, 36, 48, 0.08);
            --radius: 18px;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            font-family: \"Iowan Old Style\", \"Palatino Linotype\", \"Book Antiqua\", Georgia, serif;
            background:
                radial-gradient(circle at top left, rgba(122, 62, 43, 0.10), transparent 28%),
                radial-gradient(circle at 85% 0%, rgba(21, 76, 92, 0.10), transparent 26%),
                var(--bg);
            color: var(--ink);
            line-height: 1.6;
        }}
        .page {{ max-width: 1180px; margin: 0 auto; padding: 42px 24px 72px; }}
        .hero, .section {{
            background: rgba(255, 253, 248, 0.94);
            border: 1px solid rgba(213, 207, 197, 0.9);
            border-radius: 24px;
            box-shadow: var(--shadow);
            padding: 28px;
            margin-bottom: 24px;
        }}
        .hero {{ padding: 36px; }}
        .eyebrow {{
            margin: 0 0 10px;
            text-transform: uppercase;
            letter-spacing: 0.14em;
            font-size: 0.78rem;
            color: var(--accent);
        }}
        h1, h2, h3 {{ line-height: 1.12; margin: 0; }}
        h1 {{ font-size: clamp(2.2rem, 4vw, 3.8rem); max-width: 12ch; }}
        h2 {{ font-size: clamp(1.4rem, 2.5vw, 2.1rem); margin-bottom: 8px; }}
        p {{ color: var(--muted); }}
        .hero-grid {{ display: grid; grid-template-columns: 1.4fr 1fr; gap: 18px; align-items: start; }}
        .hero-meta {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 18px; }}
        .hero-meta span {{
            display: inline-flex;
            align-items: center;
            padding: 9px 14px;
            border-radius: 999px;
            background: rgba(233, 220, 200, 0.78);
            color: var(--ink);
            border: 1px solid rgba(122, 62, 43, 0.12);
            font-size: 0.92rem;
        }}
        .focus-box {{
            background: linear-gradient(160deg, rgba(122, 62, 43, 0.08), rgba(21, 76, 92, 0.08));
            border: 1px solid rgba(122, 62, 43, 0.14);
            border-radius: 20px;
            padding: 20px;
        }}
        .focus-box h3 {{ font-size: 1.15rem; margin-bottom: 8px; }}
        .card-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-top: 18px;
        }}
        .stat-card {{
            background: var(--panel);
            border-radius: 18px;
            border: 1px solid rgba(213, 207, 197, 0.95);
            padding: 18px;
            min-height: 100%;
        }}
        .card-tag {{
            margin: 0 0 10px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.74rem;
            color: var(--accent);
        }}
        .split {{ display: grid; grid-template-columns: 1.05fr 0.95fr; gap: 18px; }}
        .table-shell {{
            margin-top: 18px;
            overflow-x: auto;
            border-radius: 18px;
            border: 1px solid rgba(213, 207, 197, 0.9);
            background: rgba(255, 253, 248, 0.9);
        }}
        .data-table {{ width: 100%; border-collapse: collapse; min-width: 740px; }}
        .data-table th,
        .data-table td {{
            padding: 12px 14px;
            text-align: left;
            border-bottom: 1px solid rgba(213, 207, 197, 0.65);
            vertical-align: top;
        }}
        .data-table th {{
            background: rgba(244, 237, 225, 0.82);
            color: var(--ink);
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }}
        .data-table tr:last-child td {{ border-bottom: none; }}
        ul.simple {{ margin: 14px 0 0; padding-left: 18px; color: var(--muted); }}
        @media (max-width: 920px) {{
            .hero-grid, .split {{ grid-template-columns: 1fr; }}
        }}
        @media (max-width: 720px) {{
            .page {{ padding: 24px 16px 56px; }}
            .hero, .section {{ padding: 22px; }}
        }}
    </style>
</head>
<body>
    <main class=\"page\">
        <section class=\"hero\">
            <div class=\"hero-grid\">
                <div>
                    <p class=\"eyebrow\">Rotation Playbook</p>
                    <h1>What To Rotate Into, And When</h1>
                    <p>This page translates the sector rotation model into operating rules. It tells you the current destination for the rotating equity sleeve, the conditions that trigger a change, and the separate reserve-cash drawdown rule.</p>
                    <div class=\"hero-meta\">
                        <span>{html.escape(generated_at)}</span>
                        <span>Current regime: {html.escape(current_regime)}</span>
                        <span>Quadrant: {html.escape(current_quadrant)}</span>
                        <span>Latest complete signal: {html.escape(signal_date)}</span>
                    </div>
                </div>
                <aside class=\"focus-box\">
                    <p class=\"eyebrow\">Plain English</p>
                    <h3>Current instruction</h3>
                    <p>{html.escape(' '.join(instruction_lines) if instruction_lines else 'No sector currently clears the live entry filter, so wait for the next complete signal rather than forcing a rotation.')}</p>
                    <ul class=\"simple\">
                        <li>Keep {html.escape(_format_weight_pct(cash_weight))} in cash by rule.</li>
                        <li>Rotate only the {html.escape(_format_weight_pct(core_weight))} equity sleeve.</li>
                        <li>Use the reserve sleeve only when SPY drawdown thresholds are hit.</li>
                    </ul>
                </aside>
            </div>
        </section>

        <section class=\"section\">
            <p class=\"eyebrow\">Operating Rules</p>
            <h2>How The Rotation Decision Is Made</h2>
            <p>The rotation is rule-based. The page below is not discretionary commentary. It is a direct translation of the live sector ranking and the reserve cash trigger logic already used in the report.</p>
            <div class=\"card-grid\">
                {'\n'.join(cards)}
            </div>
            {_render_data_table(headers=("Step", "Rule", "What it means"), rows=rules_rows)}
        </section>

        <section class=\"section\">
            <p class=\"eyebrow\">Current Rotation</p>
            <h2>Where The Equity Sleeve Should Sit Now</h2>
            <p>The live basket only includes sectors that clear the probability filter on the latest complete signal. If the filter is tight, the basket can shrink below the normal target breadth rather than forcing weak ideas into the portfolio.</p>
            {current_table}
        </section>

        <section class=\"section\">
            <p class=\"eyebrow\">Watchlist</p>
            <h2>Nearest Alternatives If The Basket Changes</h2>
            <p>These are the highest-scoring sectors after applying the macro prior and the ML overlays. A sector can rank well and still stay out of the live basket if it does not clear the probability threshold.</p>
            {watch_table}
        </section>

        <section class=\"section\">
            <div class=\"split\">
                <div>
                    <p class=\"eyebrow\">Reserve Sleeve</p>
                    <h2>Drawdown Deployment Rules</h2>
                    <p>This is separate from the rotating sector basket. The reserve sleeve is a cash buffer that only becomes active when SPY is already in drawdown on the signal date, then stays in SPY until SPY gets back to a fresh high.</p>
                    {_render_data_table(headers=("Trigger", "Action", "Comment"), rows=reserve_rows)}
                </div>
                <div>
                    <p class=\"eyebrow\">Bias Controls</p>
                    <h2>Why This Is Not Forward Looking</h2>
                    <p>The live page uses the same no-leak controls as the benchmark report.</p>
                    <ul class=\"simple\">
                        <li>Features are lagged by {feature_lag} bar before training and prediction.</li>
                        <li>The signal executes one bar after it is observed and then holds for {hold_bars} bars.</li>
                        <li>The model used a five-year expanding train and one-year validation with purge and embargo controls already baked into the report engine.</li>
                        <li>The current rotation instruction comes from the latest complete holdout signal, not from future returns or revised macro labels.</li>
                    </ul>
                </div>
            </div>
        </section>
    </main>
</body>
</html>
"""


def _render_html(
    generated_at: str,
    regime_overview: dict[str, Any],
    sector_rotation_view: dict[str, Any],
    sector_ml_view: dict[str, Any],
    live_ml_view: dict[str, Any],
    sector_diagnostics_view: dict[str, Any],
    regime_episode_view: dict[str, Any],
) -> str:
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Sector Rotation Report</title>
  <style>
    :root {{
      --bg: {PAGE_BACKGROUND};
      --panel: {PANEL_BACKGROUND};
      --ink: {TEXT_COLOR};
      --muted: {MUTED_TEXT_COLOR};
      --line: {GRID_COLOR};
      --accent: #7a3e2b;
      --shadow: 0 20px 45px rgba(27, 36, 48, 0.08);
      --radius: 18px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
      background:
        radial-gradient(circle at top left, rgba(122, 62, 43, 0.10), transparent 28%),
        radial-gradient(circle at top right, rgba(15, 76, 92, 0.08), transparent 24%),
        var(--bg);
      color: var(--ink);
      line-height: 1.6;
    }}
    .page {{ max-width: 1220px; margin: 0 auto; padding: 48px 24px 80px; }}
    .hero, .section {{
      background: rgba(255, 253, 248, 0.92);
      border: 1px solid rgba(213, 207, 197, 0.9);
      border-radius: 24px;
      box-shadow: var(--shadow);
      padding: 28px;
      margin-bottom: 28px;
    }}
    .hero {{ padding: 40px; }}
    .eyebrow {{
      margin: 0 0 10px;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      font-size: 0.78rem;
      color: var(--accent);
    }}
    h1, h2, h3 {{ line-height: 1.15; margin: 0; }}
    h1 {{ font-size: clamp(2.4rem, 4vw, 4rem); max-width: 12ch; }}
    h2 {{ font-size: clamp(1.5rem, 2.5vw, 2.2rem); margin-bottom: 8px; }}
    h3 {{ font-size: 1.15rem; margin-bottom: 10px; }}
    p {{ color: var(--muted); }}
    .hero-meta {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 24px; }}
    .hero-meta span {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 9px 14px;
      border-radius: 999px;
      background: rgba(233, 220, 200, 0.75);
      color: var(--ink);
      border: 1px solid rgba(122, 62, 43, 0.12);
      font-size: 0.92rem;
    }}
    .card-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 16px;
      margin-top: 18px;
    }}
    .stat-card, .bucket-card {{
      background: var(--panel);
      border-radius: 18px;
      border: 1px solid rgba(213, 207, 197, 0.95);
      padding: 18px;
      min-height: 100%;
    }}
    .card-tag {{
      margin: 0 0 10px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.74rem;
      color: var(--accent);
    }}
    .subcopy {{ color: var(--muted); }}
    .methodology p {{ margin: 0; }}
    .table-shell {{
      margin-top: 18px;
      overflow-x: auto;
      border-radius: 18px;
      border: 1px solid rgba(213, 207, 197, 0.9);
      background: rgba(255, 253, 248, 0.9);
    }}
    .data-table {{ width: 100%; border-collapse: collapse; min-width: 780px; }}
    .data-table th,
    .data-table td {{
      padding: 12px 14px;
      text-align: left;
      border-bottom: 1px solid rgba(213, 207, 197, 0.65);
      vertical-align: top;
    }}
    .data-table th {{
      background: rgba(244, 237, 225, 0.82);
      color: var(--ink);
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .data-table tr:last-child td {{ border-bottom: none; }}
        .chart-shell {{ margin-top: 18px; overflow-x: auto; }}
        .episode-grid {{ display: grid; gap: 20px; margin-top: 18px; }}
        .episode-card {{
            background: rgba(255, 253, 248, 0.88);
            border: 1px solid rgba(213, 207, 197, 0.88);
            border-radius: 22px;
            padding: 22px;
            box-shadow: 0 14px 34px rgba(27, 36, 48, 0.06);
        }}
        .episode-meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }}
        .episode-meta span {{
            display: inline-flex;
            align-items: center;
            padding: 6px 10px;
            border-radius: 999px;
            background: rgba(244, 237, 225, 0.88);
            color: var(--muted);
            border: 1px solid rgba(122, 62, 43, 0.10);
            font-size: 0.78rem;
        }}
        .episode-subtitle {{ margin: 0 0 14px; color: var(--muted); }}
    @media (max-width: 720px) {{
      .page {{ padding: 24px 16px 56px; }}
      .hero, .section {{ padding: 22px; }}
    }}
  </style>
</head>
<body>
  <main class=\"page\">
    {_render_rotation_hero(generated_at=generated_at, regime_overview=regime_overview, sector_rotation_view=sector_rotation_view)}
    {_render_method_section(sector_rotation_view=sector_rotation_view)}
    {_render_overview_section(regime_overview=regime_overview, sector_rotation_view=sector_rotation_view)}
        {_render_ml_overview_section(sector_ml_view=sector_ml_view)}
        {_render_live_ml_allocation_section(live_ml_view=live_ml_view)}
        {_render_holdout_backtest_section(sector_ml_view=sector_ml_view)}
        {_render_history_backtest_section(sector_ml_view=sector_ml_view)}
        {_render_sector_dip_section(sector_diagnostics_view=sector_diagnostics_view)}
        {_render_strategy_rotation_detail_section(sector_diagnostics_view=sector_diagnostics_view)}
        {_render_strategy_sector_usage_section(sector_diagnostics_view=sector_diagnostics_view)}
        {_render_rebalance_sensitivity_section(sector_ml_view=sector_ml_view)}
        {_render_holdout_year_regime_section(sector_ml_view=sector_ml_view)}
        {_render_history_year_regime_section(sector_ml_view=sector_ml_view)}
        {_render_regime_episode_section(regime_episode_view=regime_episode_view)}
        {_render_leveraged_regime_vs_spy_section(sector_ml_view=sector_ml_view)}
        {_render_regime_ranking_section(sector_ml_view=sector_ml_view)}
        {_render_history_drawdown_section(sector_ml_view=sector_ml_view)}
        {_render_holdout_period_log_section(sector_ml_view=sector_ml_view)}
    {_render_sector_mapping_section(sector_rotation_view=sector_rotation_view)}
    {_render_allocation_section(sector_rotation_view=sector_rotation_view)}
    {_render_current_matrix_section(sector_rotation_view=sector_rotation_view)}
    {_render_regime_behaviour_section(sector_rotation_view=sector_rotation_view)}
        {_render_ml_sector_table_section(sector_ml_view=sector_ml_view)}
        {_render_ml_model_comparison_section(sector_ml_view=sector_ml_view)}
        {_render_ml_cost_section(sector_ml_view=sector_ml_view)}
        {_render_ml_regime_year_section(sector_ml_view=sector_ml_view)}
  </main>
</body>
</html>
"""


def generate_sector_rotation_report(
    output_dir: str | Path = "outputs/sector_rotation_report",
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    frame = load_model_macro_frame(project_root=root)
    regime_overview = _build_regime_overview(frame=frame, lookback_years=REPORT_LOOKBACK_YEARS)
    sector_rotation_view = _build_sector_rotation_view(project_root=root, regime_overview=regime_overview)
    sector_ml_view = build_sector_ml_view(project_root=root)
    sector_diagnostics_view = _build_sector_diagnostics_view(project_root=root, sector_ml_view=sector_ml_view)
    regime_episode_view = _build_regime_episode_view(project_root=root, sector_ml_view=sector_ml_view)
    live_ml_view = _build_live_ml_allocation_view(
        sector_rotation_view=sector_rotation_view,
        sector_ml_view=sector_ml_view,
    )

    report_dir = Path(output_dir)
    if not report_dir.is_absolute():
        report_dir = root / report_dir
    report_dir.mkdir(parents=True, exist_ok=True)

    matrix_path = report_dir / "sector_regime_matrix.csv"
    current_path = report_dir / "sector_current_regime.csv"
    summary_path = report_dir / "summary.json"
    ml_sector_summary_path = report_dir / "sector_ml_sector_summary.csv"
    ml_model_comparison_path = report_dir / "sector_ml_model_comparison.csv"
    ml_yearly_path = report_dir / "sector_ml_yearly_performance.csv"
    ml_regime_path = report_dir / "sector_ml_regime_performance.csv"
    ml_cost_path = report_dir / "sector_ml_cost_sensitivity.csv"
    ml_validation_quality_path = report_dir / "sector_ml_validation_quality.csv"
    ml_holdout_summary_path = report_dir / "sector_ml_holdout_strategy_summary.csv"
    ml_holdout_period_log_path = report_dir / "sector_ml_holdout_period_log.csv"
    ml_holdout_yearly_path = report_dir / "sector_ml_holdout_yearly_summary.csv"
    ml_holdout_regime_path = report_dir / "sector_ml_holdout_regime_summary.csv"
    ml_history_summary_path = report_dir / "sector_ml_history_strategy_summary.csv"
    ml_history_period_log_path = report_dir / "sector_ml_history_period_log.csv"
    ml_history_yearly_path = report_dir / "sector_ml_history_yearly_summary.csv"
    ml_history_regime_path = report_dir / "sector_ml_history_regime_summary.csv"
    ml_history_regime_vs_spy_x3_path = report_dir / "sector_ml_history_regime_vs_spy_x3.csv"
    ml_history_regime_ranking_path = report_dir / "sector_ml_history_regime_rankings.csv"
    ml_rebalance_sensitivity_path = report_dir / "sector_ml_rebalance_sensitivity.csv"
    ml_live_allocation_path = report_dir / "sector_ml_live_allocation.csv"
    ml_dip_summary_path = report_dir / "sector_ml_dip_summary.csv"
    ml_strategy_detail_path = report_dir / "sector_ml_strategy_detail.csv"
    ml_strategy_usage_path = report_dir / "sector_ml_strategy_sector_usage.csv"
    ml_regime_episode_summary_path = report_dir / "sector_ml_regime_episode_summary.csv"
    ml_regime_episode_detail_path = report_dir / "sector_ml_regime_episode_detail.csv"
    executive_summary_path = report_dir / "executive_summary.html"
    executive_summary_pdf_path = report_dir / "executive_summary.pdf"
    rotation_playbook_path = report_dir / "rotation_playbook.html"

    summary_payload: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "current_regime": regime_overview["current"]["regime_label"],
        "current_quadrant": regime_overview["current"]["quadrant_label"],
        "cash_weight": float(sector_rotation_view.get("cash_weight", 0.40)),
        "note": str(sector_rotation_view.get("note") or ""),
        "missing_symbols": list(sector_rotation_view.get("missing_symbols") or []),
        "ml": {
            "available": bool(sector_ml_view.get("available")),
            "boosting_backend": sector_ml_view.get("boosting_backend"),
            "data_note": sector_ml_view.get("data_note"),
            "live_allocation_available": bool(live_ml_view.get("available")),
        },
    }

    if sector_rotation_view.get("available"):
        sector_rotation_view["matrix_frame"].to_csv(matrix_path, index=False)
        sector_rotation_view["current_matrix"].to_csv(current_path, index=False)
        summary_payload.update(
            {
                "top_pick": sector_rotation_view.get("top_pick"),
                "defensive_pick": sector_rotation_view.get("defensive_pick"),
                "allocation": json.loads(sector_rotation_view["allocation_frame"].to_json(orient="records")),
                "worst_drawdown_regimes": sector_rotation_view.get("worst_drawdown_regimes"),
                "breakout_regimes": sector_rotation_view.get("breakout_regimes"),
            }
        )
    else:
        summary_payload["message"] = str(sector_rotation_view.get("message") or "Sector analytics unavailable.")

    if sector_ml_view.get("available"):
        sector_ml_view["sector_summary_frame"].to_csv(ml_sector_summary_path, index=False)
        sector_ml_view["model_comparison_frame"].to_csv(ml_model_comparison_path, index=False)
        sector_ml_view["yearly_performance_frame"].to_csv(ml_yearly_path, index=False)
        sector_ml_view["regime_performance_frame"].to_csv(ml_regime_path, index=False)
        sector_ml_view["cost_sensitivity_frame"].to_csv(ml_cost_path, index=False)
        sector_ml_view["validation_quality_frame"].to_csv(ml_validation_quality_path, index=False)
        summary_payload["ml"].update(
            {
                "config": sector_ml_view.get("config"),
                "holdout_leader": json.loads(
                    pd.DataFrame([sector_ml_view.get("holdout_leader")]).to_json(orient="records")
                )[0],
                "winner_counts": json.loads(sector_ml_view["winner_counts_frame"].to_json(orient="records")),
                "robust_cost_sector_count": int(sector_ml_view.get("robust_cost_sector_count", 0)),
            }
        )
        rotation_view = sector_ml_view.get("holdout_rotation_view")
        if isinstance(rotation_view, dict) and rotation_view.get("available"):
            rotation_view["strategy_summary_frame"].to_csv(ml_holdout_summary_path, index=False)
            rotation_view["period_log_frame"].to_csv(ml_holdout_period_log_path, index=False)
            rotation_view["yearly_summary_frame"].to_csv(ml_holdout_yearly_path, index=False)
            rotation_view["regime_summary_frame"].to_csv(ml_holdout_regime_path, index=False)
            summary_payload["ml"]["holdout_rotation"] = {
                "available": True,
                "current_signal_date": str(rotation_view.get("current_signal_date")),
                "method_note": rotation_view.get("method_note"),
                "strategy_summary": json.loads(rotation_view["strategy_summary_frame"].to_json(orient="records")),
            }
        history_view = sector_ml_view.get("historical_rotation_view")
        if isinstance(history_view, dict) and history_view.get("available"):
            history_view["strategy_summary_frame"].to_csv(ml_history_summary_path, index=False)
            history_view["period_log_frame"].to_csv(ml_history_period_log_path, index=False)
            history_view["yearly_summary_frame"].to_csv(ml_history_yearly_path, index=False)
            history_view["regime_summary_frame"].to_csv(ml_history_regime_path, index=False)
            regime_vs_spy_x3_frame = _build_regime_vs_spy_frame(history_view, leveraged=True)
            if not regime_vs_spy_x3_frame.empty:
                regime_vs_spy_x3_frame.to_csv(ml_history_regime_vs_spy_x3_path, index=False)
            regime_ranking_frame = _build_regime_ranking_frame(history_view)
            if not regime_ranking_frame.empty:
                regime_ranking_frame.to_csv(ml_history_regime_ranking_path, index=False)
            summary_payload["ml"]["historical_rotation"] = {
                "available": True,
                "scope_label": history_view.get("scope_label"),
                "benchmark_start": str(history_view.get("benchmark_start")),
                "benchmark_end": str(history_view.get("benchmark_end")),
                "method_note": history_view.get("method_note"),
                "strategy_summary": json.loads(history_view["strategy_summary_frame"].to_json(orient="records")),
            }
        rebalance_sensitivity_frame = sector_ml_view.get("rebalance_sensitivity_frame")
        if isinstance(rebalance_sensitivity_frame, pd.DataFrame) and not rebalance_sensitivity_frame.empty:
            rebalance_sensitivity_frame.to_csv(ml_rebalance_sensitivity_path, index=False)
            summary_payload["ml"]["rebalance_sensitivity"] = {
                "available": True,
                "cadences": sorted(rebalance_sensitivity_frame["cadence_bars"].dropna().astype(int).unique().tolist()),
                "strategy_summary": json.loads(rebalance_sensitivity_frame.to_json(orient="records")),
            }
        if sector_diagnostics_view.get("available"):
            sector_diagnostics_view["dip_summary_frame"].to_csv(ml_dip_summary_path, index=False)
            sector_diagnostics_view["strategy_detail_frame"].to_csv(ml_strategy_detail_path, index=False)
            sector_diagnostics_view["strategy_usage_frame"].to_csv(ml_strategy_usage_path, index=False)
            summary_payload["ml"]["sector_diagnostics"] = {
                "available": True,
                "lookback_bars": int(sector_diagnostics_view.get("lookback_bars", 5)),
                "top_dip_sector": sector_diagnostics_view.get("top_dip_row"),
                "top_severe_drop_sector": sector_diagnostics_view.get("top_severe_row"),
            }
    else:
        summary_payload["ml"]["message"] = str(sector_ml_view.get("message") or "Sector ML study unavailable.")

    if regime_episode_view.get("available"):
        regime_episode_view["summary_frame"].to_csv(ml_regime_episode_summary_path, index=False)
        regime_episode_view["detail_frame"].to_csv(ml_regime_episode_detail_path, index=False)
        summary_payload["ml"]["regime_episodes"] = {
            "available": True,
            "episode_count": int(len(regime_episode_view["summary_frame"].index)),
            "activation_note": regime_episode_view.get("activation_note"),
        }
    else:
        summary_payload["ml"]["regime_episodes"] = {
            "available": False,
            "message": str(regime_episode_view.get("message") or "Regime episode view unavailable."),
        }

    if live_ml_view.get("available"):
        live_ml_view["allocation_frame"].to_csv(ml_live_allocation_path, index=False)
        summary_payload["ml"]["live_allocation"] = {
            "signal_date": str(live_ml_view.get("signal_date")),
            "top_pick": json.loads(pd.DataFrame([live_ml_view.get("top_pick")]).to_json(orient="records"))[0],
            "allocation": json.loads(live_ml_view["allocation_frame"].to_json(orient="records")),
        }
    else:
        summary_payload["ml"]["live_allocation_message"] = str(live_ml_view.get("message") or "Live ML allocation unavailable.")

    summary_payload["executive_summary"] = {
        "html": str(executive_summary_path),
        "pdf": str(executive_summary_pdf_path),
    }
    summary_payload["rotation_playbook"] = {
        "html": str(rotation_playbook_path),
    }

    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    generated_at = datetime.now(UTC).strftime("Generated %Y-%m-%d %H:%M UTC")
    html_text = _render_html(
        generated_at=generated_at,
        regime_overview=regime_overview,
        sector_rotation_view=sector_rotation_view,
        sector_ml_view=sector_ml_view,
        live_ml_view=live_ml_view,
        sector_diagnostics_view=sector_diagnostics_view,
        regime_episode_view=regime_episode_view,
    )
    executive_summary_html = _render_executive_summary_html(
        generated_at=generated_at,
        regime_overview=regime_overview,
        sector_ml_view=sector_ml_view,
    )
    rotation_playbook_html = _render_rotation_playbook_html(
        generated_at=generated_at,
        regime_overview=regime_overview,
        sector_ml_view=sector_ml_view,
        live_ml_view=live_ml_view,
    )
    _render_executive_summary_pdf(
        pdf_path=executive_summary_pdf_path,
        generated_at=generated_at,
        regime_overview=regime_overview,
        sector_ml_view=sector_ml_view,
    )
    report_path = report_dir / "index.html"
    report_path.write_text(html_text, encoding="utf-8")
    executive_summary_path.write_text(executive_summary_html, encoding="utf-8")
    rotation_playbook_path.write_text(rotation_playbook_html, encoding="utf-8")

    return {
        "report": str(report_path),
        "executive_summary": str(executive_summary_path),
        "executive_summary_pdf": str(executive_summary_pdf_path),
        "rotation_playbook": str(rotation_playbook_path),
        "summary": str(summary_path),
        "sector_matrix": str(matrix_path) if matrix_path.exists() else None,
        "sector_current": str(current_path) if current_path.exists() else None,
        "ml_sector_summary": str(ml_sector_summary_path) if ml_sector_summary_path.exists() else None,
        "ml_model_comparison": str(ml_model_comparison_path) if ml_model_comparison_path.exists() else None,
        "ml_yearly": str(ml_yearly_path) if ml_yearly_path.exists() else None,
        "ml_regime": str(ml_regime_path) if ml_regime_path.exists() else None,
        "ml_cost": str(ml_cost_path) if ml_cost_path.exists() else None,
        "ml_validation_quality": str(ml_validation_quality_path) if ml_validation_quality_path.exists() else None,
        "ml_holdout_summary": str(ml_holdout_summary_path) if ml_holdout_summary_path.exists() else None,
        "ml_holdout_period_log": str(ml_holdout_period_log_path) if ml_holdout_period_log_path.exists() else None,
        "ml_holdout_yearly": str(ml_holdout_yearly_path) if ml_holdout_yearly_path.exists() else None,
        "ml_holdout_regime": str(ml_holdout_regime_path) if ml_holdout_regime_path.exists() else None,
        "ml_history_summary": str(ml_history_summary_path) if ml_history_summary_path.exists() else None,
        "ml_history_period_log": str(ml_history_period_log_path) if ml_history_period_log_path.exists() else None,
        "ml_history_yearly": str(ml_history_yearly_path) if ml_history_yearly_path.exists() else None,
        "ml_history_regime": str(ml_history_regime_path) if ml_history_regime_path.exists() else None,
        "ml_history_regime_vs_spy_x3": str(ml_history_regime_vs_spy_x3_path) if ml_history_regime_vs_spy_x3_path.exists() else None,
        "ml_history_regime_rankings": str(ml_history_regime_ranking_path) if ml_history_regime_ranking_path.exists() else None,
        "ml_rebalance_sensitivity": str(ml_rebalance_sensitivity_path) if ml_rebalance_sensitivity_path.exists() else None,
        "ml_live_allocation": str(ml_live_allocation_path) if ml_live_allocation_path.exists() else None,
        "ml_dip_summary": str(ml_dip_summary_path) if ml_dip_summary_path.exists() else None,
        "ml_strategy_detail": str(ml_strategy_detail_path) if ml_strategy_detail_path.exists() else None,
        "ml_strategy_usage": str(ml_strategy_usage_path) if ml_strategy_usage_path.exists() else None,
        "ml_regime_episode_summary": str(ml_regime_episode_summary_path) if ml_regime_episode_summary_path.exists() else None,
        "ml_regime_episode_detail": str(ml_regime_episode_detail_path) if ml_regime_episode_detail_path.exists() else None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a dedicated sector rotation report.")
    parser.add_argument(
        "--output-dir",
        default="outputs/sector_rotation_report",
        help="Directory where the sector rotation HTML report and companion files will be written.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    generated = generate_sector_rotation_report(output_dir=args.output_dir)
    print(json.dumps(generated, indent=2))


if __name__ == "__main__":
    main()