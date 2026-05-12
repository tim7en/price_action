from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .data import resolve_project_root
from .fundamentals_analysis import DEFAULT_OUTPUT_DIR as DEFAULT_FUNDAMENTALS_ANALYSIS_OUTPUT_DIR
from .macro_report import REPORT_LOOKBACK_YEARS, _build_regime_overview, load_model_macro_frame
from .sector_fundamentals_research import (
    DEFAULT_OUTPUT_DIR as DEFAULT_SECTOR_FUNDAMENTALS_RESEARCH_OUTPUT_DIR,
)
from .sector_fundamentals_research import build_sector_fundamentals_research

DEFAULT_OUTPUT_DIR = Path("outputs") / "sector_macro_regime_research"
DEFAULT_TROUGH_LOOKBACK_QUARTERS = 4
DEFAULT_REGIME_LOOKAHEAD_QUARTERS = 2

BENIGN_REGIMES: frozenset[str] = frozenset(
    {
        "Disinflationary Growth",
        "Recovery And Reflation",
        "Inflationary Boom",
        "Sideways Low-Volatility Regime",
    }
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a macro-regime x sector-earnings research dataset and write the outputs "
            "used by the integrated third research book."
        )
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root. Defaults to the repository root.",
    )
    parser.add_argument(
        "--analysis-output-dir",
        type=Path,
        default=DEFAULT_FUNDAMENTALS_ANALYSIS_OUTPUT_DIR,
        help="Directory containing the cleaned fundamentals analysis outputs.",
    )
    parser.add_argument(
        "--sector-research-output-dir",
        type=Path,
        default=DEFAULT_SECTOR_FUNDAMENTALS_RESEARCH_OUTPUT_DIR,
        help="Directory containing the sector fundamentals research outputs.",
    )
    parser.add_argument(
        "--fundamentals-data-dir",
        type=Path,
        default=None,
        help="Optional fundamentals directory used if sector research outputs need a rebuild.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for the generated regime-earnings research outputs.",
    )
    parser.add_argument(
        "--lookback-years",
        type=int,
        default=REPORT_LOOKBACK_YEARS,
        help="Macro regime lookback window used when building quarterly regime history.",
    )
    parser.add_argument(
        "--trough-lookback-quarters",
        type=int,
        default=DEFAULT_TROUGH_LOOKBACK_QUARTERS,
        help="Rolling quarter window used to identify sector earnings troughs.",
    )
    parser.add_argument(
        "--regime-lookahead-quarters",
        type=int,
        default=DEFAULT_REGIME_LOOKAHEAD_QUARTERS,
        help="Number of future quarters used when testing macro normalization after an earnings trough.",
    )
    parser.add_argument(
        "--refresh-sector-research",
        action="store_true",
        help="Force a rebuild of the sector fundamentals research outputs before this study runs.",
    )
    return parser.parse_args()


def _resolved_output_dir(root: Path, output_dir: Path) -> Path:
    return output_dir if output_dir.is_absolute() else root / output_dir


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required input not found: {path}")
    return pd.read_csv(path)


def _mode_value(series: pd.Series) -> str:
    mode = series.mode(dropna=True)
    if not mode.empty:
        return str(mode.iloc[0])
    if series.empty:
        return "UNKNOWN"
    return str(series.iloc[-1])


def _future_value_max(frame: pd.DataFrame, column: str, lookahead_quarters: int) -> pd.Series:
    future_values = [frame[column].shift(-step) for step in range(1, lookahead_quarters + 1)]
    return pd.concat(future_values, axis=1).max(axis=1)


def _future_value_min(frame: pd.DataFrame, column: str, lookahead_quarters: int) -> pd.Series:
    future_values = [frame[column].shift(-step) for step in range(1, lookahead_quarters + 1)]
    return pd.concat(future_values, axis=1).min(axis=1)


def _future_label_flag(frame: pd.DataFrame, column: str, current_column: str, lookahead_quarters: int) -> pd.Series:
    future_values = [frame[column].shift(-step) for step in range(1, lookahead_quarters + 1)]
    combined = pd.concat(future_values, axis=1)
    return combined.ne(frame[current_column], axis=0).any(axis=1)


def _future_benign_flag(frame: pd.DataFrame, column: str, lookahead_quarters: int) -> pd.Series:
    future_values = [frame[column].shift(-step) for step in range(1, lookahead_quarters + 1)]
    combined = pd.concat(future_values, axis=1)
    return combined.isin(BENIGN_REGIMES).any(axis=1)


def _ensure_sector_research_outputs(
    *,
    root: Path,
    analysis_output_dir: Path,
    sector_research_output_dir: Path,
    fundamentals_data_dir: Path | None,
    refresh: bool,
) -> tuple[Path, Path]:
    resolved_analysis_output_dir = _resolved_output_dir(root, analysis_output_dir)
    resolved_sector_research_output_dir = _resolved_output_dir(root, sector_research_output_dir)
    summary_path = resolved_sector_research_output_dir / "sector_research_summary.json"
    if refresh or not summary_path.exists():
        build_sector_fundamentals_research(
            project_root=root,
            analysis_output_dir=resolved_analysis_output_dir,
            fundamentals_data_dir=fundamentals_data_dir,
            output_dir=resolved_sector_research_output_dir,
        )
    return resolved_analysis_output_dir, resolved_sector_research_output_dir


def build_quarterly_regime_history(
    *,
    root: Path,
    lookback_years: int,
    lookahead_quarters: int,
) -> pd.DataFrame:
    macro_frame = load_model_macro_frame(project_root=root)
    regime_overview = _build_regime_overview(frame=macro_frame, lookback_years=lookback_years)
    regime_history = regime_overview["history_frame"].copy().reset_index(names="month_end")
    regime_history["fiscal_quarter"] = regime_history["month_end"].dt.to_period("Q").astype(str)

    quarterly = (
        regime_history.groupby("fiscal_quarter")
        .agg(
            quarter_end_month=("month_end", "max"),
            month_count=("month_end", "count"),
            dominant_regime_label=("regime_label", _mode_value),
            quarter_end_regime_label=("regime_label", "last"),
            dominant_quadrant_label=("quadrant_label", _mode_value),
            quarter_end_quadrant_label=("quadrant_label", "last"),
            growth_axis=("growth_axis", "mean"),
            inflation_axis=("inflation_axis", "mean"),
            stress_axis=("stress_axis", "mean"),
            stress_improving=("stress_improving", "mean"),
            volatility_stress=("volatility_stress", "mean"),
            credit_stress=("credit_stress", "mean"),
            rate_shock=("rate_shock", "mean"),
            valuation_fragility=("valuation_fragility", "mean"),
            spot_vix=("spot_vix", "last"),
            high_yield_spread=("high_yield_spread", "last"),
            us_2y_yield=("us_2y_yield", "last"),
            us_10y_yield=("us_10y_yield", "last"),
            wti_usd_per_bbl=("wti_usd_per_bbl", "last"),
            shiller_cape_ratio=("shiller_cape_ratio", "last"),
        )
        .reset_index()
        .sort_values("quarter_end_month")
        .reset_index(drop=True)
    )
    quarterly["quarter_end_date"] = pd.to_datetime(quarterly["quarter_end_month"], errors="coerce")
    quarterly["macro_balance_score"] = (
        quarterly["growth_axis"]
        - quarterly["stress_axis"]
        - 0.50 * quarterly["inflation_axis"]
        + 0.25 * quarterly["stress_improving"]
        - 0.25 * quarterly["valuation_fragility"]
    )
    quarterly["macro_balance_score_change_1q"] = quarterly["macro_balance_score"].diff(1)
    quarterly["growth_axis_change_1q"] = quarterly["growth_axis"].diff(1)
    quarterly["inflation_axis_change_1q"] = quarterly["inflation_axis"].diff(1)
    quarterly["stress_axis_change_1q"] = quarterly["stress_axis"].diff(1)
    quarterly["regime_shift_flag"] = quarterly["quarter_end_regime_label"].ne(
        quarterly["quarter_end_regime_label"].shift(1)
    )
    quarterly["quadrant_shift_flag"] = quarterly["quarter_end_quadrant_label"].ne(
        quarterly["quarter_end_quadrant_label"].shift(1)
    )
    quarterly["prior_regime_label"] = quarterly["quarter_end_regime_label"].shift(1)
    quarterly["prior_quadrant_label"] = quarterly["quarter_end_quadrant_label"].shift(1)
    quarterly["future_macro_balance_score_max"] = _future_value_max(
        quarterly,
        column="macro_balance_score",
        lookahead_quarters=lookahead_quarters,
    )
    quarterly["future_macro_balance_score_min"] = _future_value_min(
        quarterly,
        column="macro_balance_score",
        lookahead_quarters=lookahead_quarters,
    )
    quarterly["macro_balance_improvement_next_window"] = (
        quarterly["future_macro_balance_score_max"] - quarterly["macro_balance_score"]
    )
    quarterly["macro_balance_deterioration_next_window"] = (
        quarterly["future_macro_balance_score_min"] - quarterly["macro_balance_score"]
    )
    quarterly["macro_regime_change_next_window"] = _future_label_flag(
        quarterly,
        column="quarter_end_regime_label",
        current_column="quarter_end_regime_label",
        lookahead_quarters=lookahead_quarters,
    )
    quarterly["macro_shift_to_benign_next_window"] = _future_benign_flag(
        quarterly,
        column="quarter_end_regime_label",
        lookahead_quarters=lookahead_quarters,
    )
    quarterly["current_regime_is_benign"] = quarterly["quarter_end_regime_label"].isin(BENIGN_REGIMES)
    return quarterly


def build_sector_macro_panel(
    *,
    analysis_output_dir: Path,
    sector_research_output_dir: Path,
    quarterly_regime_history: pd.DataFrame,
) -> pd.DataFrame:
    sector_quarterly = _read_csv(analysis_output_dir / "sector_quarterly_surprise.csv")
    market_features = _read_csv(sector_research_output_dir / "sector_market_features_quarterly.csv")

    panel = sector_quarterly.merge(
        market_features,
        on=["sector", "fiscal_quarter"],
        how="inner",
        suffixes=("", "_market"),
    ).merge(
        quarterly_regime_history,
        on="fiscal_quarter",
        how="inner",
        suffixes=("", "_macro"),
    )
    panel["quarter_end_date"] = pd.to_datetime(panel["quarter_end_date"], errors="coerce")
    numeric_columns = [
        "symbol_count",
        "avg_surprise_pct",
        "median_surprise_pct",
        "cap_weighted_surprise_pct",
        "beat_rate",
        "avg_reported_eps",
        "avg_estimated_eps",
        "avg_quarterly_eps_yoy_pct",
        "cap_weighted_quarterly_eps_yoy_pct",
        "target_excess_return",
        "sector_next_q_return",
        "spy_next_q_return",
        "relative_ret_1q",
        "relative_ret_2q",
        "relative_ret_1y",
        "etf_ret_1q",
        "etf_ret_2q",
        "etf_ret_1y",
        "etf_vol_1q",
        "etf_sma_gap",
        "relative_drawdown_2q",
        "macro_balance_score",
        "macro_balance_score_change_1q",
        "growth_axis",
        "inflation_axis",
        "stress_axis",
        "stress_improving",
        "credit_stress",
        "rate_shock",
        "valuation_fragility",
    ]
    for column in numeric_columns:
        if column in panel.columns:
            panel[column] = pd.to_numeric(panel[column], errors="coerce")

    panel = panel.sort_values(["sector", "fiscal_quarter"]).reset_index(drop=True)
    panel["eps_growth_rank_in_quarter"] = panel.groupby("fiscal_quarter")[
        "cap_weighted_quarterly_eps_yoy_pct"
    ].rank(pct=True)
    panel["surprise_rank_in_quarter"] = panel.groupby("fiscal_quarter")["cap_weighted_surprise_pct"].rank(
        pct=True
    )
    panel["earnings_composite_rank_in_quarter"] = (
        panel[["eps_growth_rank_in_quarter", "surprise_rank_in_quarter"]].mean(axis=1)
    )
    return panel


def build_quarterly_earnings_breadth(sector_panel: pd.DataFrame) -> pd.DataFrame:
    breadth = (
        sector_panel.groupby("fiscal_quarter")
        .agg(
            quarter_end_date=("quarter_end_date", "first"),
            regime_label=("quarter_end_regime_label", "first"),
            quadrant_label=("quarter_end_quadrant_label", "first"),
            sector_count=("sector", "nunique"),
            median_eps_growth=("cap_weighted_quarterly_eps_yoy_pct", "median"),
            mean_eps_growth=("cap_weighted_quarterly_eps_yoy_pct", "mean"),
            median_surprise=("cap_weighted_surprise_pct", "median"),
            mean_surprise=("cap_weighted_surprise_pct", "mean"),
            negative_eps_growth_share=(
                "cap_weighted_quarterly_eps_yoy_pct",
                lambda series: float((pd.to_numeric(series, errors="coerce") < 0.0).mean()),
            ),
            negative_surprise_share=(
                "cap_weighted_surprise_pct",
                lambda series: float((pd.to_numeric(series, errors="coerce") < 0.0).mean()),
            ),
            mean_next_q_excess_return=("target_excess_return", "mean"),
            hit_rate_next_q=(
                "target_excess_return",
                lambda series: float((pd.to_numeric(series, errors="coerce") > 0.0).mean()),
            ),
            macro_balance_score=("macro_balance_score", "first"),
            growth_axis=("growth_axis", "first"),
            inflation_axis=("inflation_axis", "first"),
            stress_axis=("stress_axis", "first"),
        )
        .reset_index()
        .sort_values("quarter_end_date")
        .reset_index(drop=True)
    )
    breadth["median_eps_growth_change_1q"] = breadth["median_eps_growth"].diff(1)
    breadth["negative_eps_growth_share_change_1q"] = breadth["negative_eps_growth_share"].diff(1)
    return breadth


def build_regime_earnings_summary(sector_panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for group_type, column in (
        ("regime", "quarter_end_regime_label"),
        ("quadrant", "quarter_end_quadrant_label"),
    ):
        for label, group in sector_panel.groupby(column):
            rows.append(
                {
                    "group_type": group_type,
                    "group_label": label,
                    "sector_quarter_rows": int(len(group)),
                    "quarter_count": int(group["fiscal_quarter"].nunique()),
                    "sector_count": int(group["sector"].nunique()),
                    "median_eps_growth": float(group["cap_weighted_quarterly_eps_yoy_pct"].median()),
                    "mean_eps_growth": float(group["cap_weighted_quarterly_eps_yoy_pct"].mean()),
                    "median_surprise": float(group["cap_weighted_surprise_pct"].median()),
                    "mean_surprise": float(group["cap_weighted_surprise_pct"].mean()),
                    "negative_eps_growth_share": float((group["cap_weighted_quarterly_eps_yoy_pct"] < 0.0).mean()),
                    "negative_surprise_share": float((group["cap_weighted_surprise_pct"] < 0.0).mean()),
                    "mean_next_q_excess_return": float(group["target_excess_return"].mean()),
                    "hit_rate_next_q": float((group["target_excess_return"] > 0.0).mean()),
                    "macro_balance_score": float(group["macro_balance_score"].mean()),
                }
            )

    return pd.DataFrame(rows).sort_values(
        ["group_type", "macro_balance_score", "median_eps_growth"],
        ascending=[True, False, False],
    )


def build_regime_transition_tables(
    *,
    quarterly_regime_history: pd.DataFrame,
    quarterly_earnings_breadth: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    transition_frame = quarterly_regime_history.merge(
        quarterly_earnings_breadth,
        on=["fiscal_quarter", "quarter_end_date"],
        how="left",
        suffixes=("", "_earnings"),
    )
    transition_frame["prior_median_eps_growth_1q"] = transition_frame["median_eps_growth"].shift(1)
    transition_frame["prior_median_eps_growth_2q"] = transition_frame["median_eps_growth"].shift(2)
    transition_frame["next_median_eps_growth_1q"] = transition_frame["median_eps_growth"].shift(-1)
    transition_frame["next_median_eps_growth_2q"] = transition_frame["median_eps_growth"].shift(-2)
    transition_frame["prior_negative_eps_growth_share_1q"] = transition_frame["negative_eps_growth_share"].shift(1)
    transition_frame["next_negative_eps_growth_share_1q"] = transition_frame["negative_eps_growth_share"].shift(-1)
    transition_frame["next_negative_eps_growth_share_2q"] = transition_frame["negative_eps_growth_share"].shift(-2)
    transition_frame["earnings_rebound_next_q"] = (
        transition_frame["next_median_eps_growth_1q"] > transition_frame["median_eps_growth"]
    )
    transition_frame["breadth_rebound_next_q"] = (
        transition_frame["next_negative_eps_growth_share_1q"] < transition_frame["negative_eps_growth_share"]
    )
    transition_frame["earnings_rebound_next_2q"] = (
        transition_frame[["next_median_eps_growth_1q", "next_median_eps_growth_2q"]].max(axis=1)
        > transition_frame["median_eps_growth"]
    )

    episodes = transition_frame.loc[
        transition_frame["regime_shift_flag"] & transition_frame["prior_regime_label"].notna()
    ].copy()
    episodes = episodes[
        [
            "fiscal_quarter",
            "quarter_end_date",
            "prior_regime_label",
            "quarter_end_regime_label",
            "prior_quadrant_label",
            "quarter_end_quadrant_label",
            "macro_balance_score",
            "macro_balance_score_change_1q",
            "prior_median_eps_growth_1q",
            "median_eps_growth",
            "next_median_eps_growth_1q",
            "prior_negative_eps_growth_share_1q",
            "negative_eps_growth_share",
            "next_negative_eps_growth_share_1q",
            "earnings_rebound_next_q",
            "earnings_rebound_next_2q",
            "breadth_rebound_next_q",
            "mean_next_q_excess_return",
            "hit_rate_next_q",
        ]
    ].sort_values("quarter_end_date")

    summary = (
        episodes.groupby(["prior_regime_label", "quarter_end_regime_label"])
        .agg(
            transition_count=("fiscal_quarter", "count"),
            avg_entry_macro_balance_score=("macro_balance_score", "mean"),
            avg_prior_median_eps_growth=("prior_median_eps_growth_1q", "mean"),
            avg_entry_median_eps_growth=("median_eps_growth", "mean"),
            avg_next_median_eps_growth=("next_median_eps_growth_1q", "mean"),
            earnings_rebound_next_q_rate=("earnings_rebound_next_q", "mean"),
            earnings_rebound_next_2q_rate=("earnings_rebound_next_2q", "mean"),
            breadth_rebound_next_q_rate=("breadth_rebound_next_q", "mean"),
            avg_entry_negative_eps_growth_share=("negative_eps_growth_share", "mean"),
            avg_next_negative_eps_growth_share=("next_negative_eps_growth_share_1q", "mean"),
            avg_next_q_excess_return=("mean_next_q_excess_return", "mean"),
            avg_hit_rate_next_q=("hit_rate_next_q", "mean"),
        )
        .reset_index()
        .sort_values(["transition_count", "avg_entry_median_eps_growth"], ascending=[False, True])
    )
    return episodes, summary


def build_sector_earnings_trough_tables(
    *,
    sector_panel: pd.DataFrame,
    trough_lookback_quarters: int,
    regime_lookahead_quarters: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    event_frames: list[pd.DataFrame] = []

    for sector, group in sector_panel.groupby("sector"):
        ordered = group.sort_values("quarter_end_date").copy()
        ordered["eps_growth_change_2q"] = ordered["cap_weighted_quarterly_eps_yoy_pct"].diff(2)
        ordered["rolling_eps_growth_min"] = ordered["cap_weighted_quarterly_eps_yoy_pct"].rolling(
            window=trough_lookback_quarters,
            min_periods=trough_lookback_quarters,
        ).min()
        ordered["next_eps_growth_1q"] = ordered["cap_weighted_quarterly_eps_yoy_pct"].shift(-1)
        ordered["next_eps_growth_2q"] = ordered["cap_weighted_quarterly_eps_yoy_pct"].shift(-2)
        ordered["two_quarter_excess_return"] = (
            (1.0 + ordered["target_excess_return"]) * (1.0 + ordered["target_excess_return"].shift(-1)) - 1.0
        )
        ordered["future_eps_growth_peak"] = _future_value_max(
            ordered,
            column="cap_weighted_quarterly_eps_yoy_pct",
            lookahead_quarters=regime_lookahead_quarters,
        )
        ordered["eps_trough_flag"] = (
            ordered["cap_weighted_quarterly_eps_yoy_pct"].notna()
            & ordered["rolling_eps_growth_min"].notna()
            & ordered["cap_weighted_quarterly_eps_yoy_pct"].eq(ordered["rolling_eps_growth_min"])
            & ordered["cap_weighted_quarterly_eps_yoy_pct"].lt(0.0)
            & ordered["eps_growth_change_2q"].lt(0.0)
        )
        ordered["eps_rebound_next_q"] = ordered["next_eps_growth_1q"] > ordered["cap_weighted_quarterly_eps_yoy_pct"]
        ordered["eps_rebound_next_2q"] = ordered["future_eps_growth_peak"] > ordered["cap_weighted_quarterly_eps_yoy_pct"]
        ordered["eps_normalizes_next_window"] = ordered["future_eps_growth_peak"] > 0.0
        ordered["positive_excess_return_next_q"] = ordered["target_excess_return"] > 0.0
        ordered["positive_two_quarter_excess_return"] = ordered["two_quarter_excess_return"] > 0.0

        events = ordered.loc[ordered["eps_trough_flag"]].copy()
        if events.empty:
            continue
        events["sector"] = sector
        event_frames.append(events)

    event_table = pd.concat(event_frames, ignore_index=True) if event_frames else pd.DataFrame()
    if event_table.empty:
        empty_summary = pd.DataFrame()
        return event_table, empty_summary, empty_summary

    event_columns = [
        "fiscal_quarter",
        "quarter_end_date",
        "sector",
        "etf_symbol",
        "quarter_end_regime_label",
        "quarter_end_quadrant_label",
        "cap_weighted_quarterly_eps_yoy_pct",
        "cap_weighted_surprise_pct",
        "target_excess_return",
        "two_quarter_excess_return",
        "macro_balance_score",
        "macro_balance_improvement_next_window",
        "macro_regime_change_next_window",
        "macro_shift_to_benign_next_window",
        "eps_rebound_next_q",
        "eps_rebound_next_2q",
        "eps_normalizes_next_window",
        "positive_excess_return_next_q",
        "positive_two_quarter_excess_return",
    ]
    event_table = event_table[event_columns].sort_values(["quarter_end_date", "sector"]).reset_index(drop=True)

    by_regime = (
        event_table.groupby("quarter_end_regime_label")
        .agg(
            trough_events=("sector", "count"),
            sector_count=("sector", "nunique"),
            avg_trough_eps_growth=("cap_weighted_quarterly_eps_yoy_pct", "mean"),
            avg_trough_surprise=("cap_weighted_surprise_pct", "mean"),
            eps_rebound_next_q_rate=("eps_rebound_next_q", "mean"),
            eps_rebound_next_2q_rate=("eps_rebound_next_2q", "mean"),
            eps_normalizes_next_window_rate=("eps_normalizes_next_window", "mean"),
            macro_regime_change_next_window_rate=("macro_regime_change_next_window", "mean"),
            macro_shift_to_benign_next_window_rate=("macro_shift_to_benign_next_window", "mean"),
            avg_macro_balance_improvement_next_window=("macro_balance_improvement_next_window", "mean"),
            avg_next_q_excess_return=("target_excess_return", "mean"),
            positive_next_q_excess_return_rate=("positive_excess_return_next_q", "mean"),
            avg_two_quarter_excess_return=("two_quarter_excess_return", "mean"),
            positive_two_quarter_excess_return_rate=("positive_two_quarter_excess_return", "mean"),
        )
        .reset_index()
        .sort_values(["eps_rebound_next_2q_rate", "avg_two_quarter_excess_return"], ascending=[False, False])
    )

    by_sector = (
        event_table.groupby("sector")
        .agg(
            trough_events=("fiscal_quarter", "count"),
            regimes_seen=("quarter_end_regime_label", "nunique"),
            avg_trough_eps_growth=("cap_weighted_quarterly_eps_yoy_pct", "mean"),
            eps_rebound_next_q_rate=("eps_rebound_next_q", "mean"),
            eps_normalizes_next_window_rate=("eps_normalizes_next_window", "mean"),
            avg_next_q_excess_return=("target_excess_return", "mean"),
            avg_two_quarter_excess_return=("two_quarter_excess_return", "mean"),
        )
        .reset_index()
        .sort_values(["trough_events", "avg_two_quarter_excess_return"], ascending=[False, False])
    )

    return event_table, by_regime, by_sector


def write_outputs(
    *,
    output_dir: Path,
    quarterly_regime_history: pd.DataFrame,
    sector_macro_panel: pd.DataFrame,
    quarterly_earnings_breadth: pd.DataFrame,
    regime_earnings_summary: pd.DataFrame,
    regime_transition_episodes: pd.DataFrame,
    regime_transition_summary: pd.DataFrame,
    trough_event_table: pd.DataFrame,
    trough_regime_summary: pd.DataFrame,
    trough_sector_summary: pd.DataFrame,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    quarterly_regime_history.to_csv(output_dir / "macro_regime_quarterly_history.csv", index=False)
    sector_macro_panel.to_csv(output_dir / "sector_macro_regime_panel.csv", index=False)
    quarterly_earnings_breadth.to_csv(output_dir / "quarterly_earnings_breadth.csv", index=False)
    regime_earnings_summary.to_csv(output_dir / "regime_earnings_summary.csv", index=False)
    regime_transition_episodes.to_csv(output_dir / "regime_transition_episode_table.csv", index=False)
    regime_transition_summary.to_csv(output_dir / "regime_transition_summary.csv", index=False)
    trough_event_table.to_csv(output_dir / "sector_earnings_trough_events.csv", index=False)
    trough_regime_summary.to_csv(output_dir / "sector_earnings_trough_regime_summary.csv", index=False)
    trough_sector_summary.to_csv(output_dir / "sector_earnings_trough_sector_summary.csv", index=False)

    current_regime = (
        str(quarterly_regime_history["quarter_end_regime_label"].iloc[-1])
        if not quarterly_regime_history.empty
        else None
    )
    weakest_regimes = (
        regime_earnings_summary.loc[regime_earnings_summary["group_type"] == "regime"]
        .sort_values(["median_eps_growth", "mean_next_q_excess_return"], ascending=[True, True])
        .head(5)
        .to_dict(orient="records")
        if not regime_earnings_summary.empty
        else []
    )
    trough_highlights = (
        trough_event_table.sort_values(
            ["cap_weighted_quarterly_eps_yoy_pct", "macro_balance_improvement_next_window"],
            ascending=[True, False],
        )
        .head(10)
        .to_dict(orient="records")
        if not trough_event_table.empty
        else []
    )
    output_names = sorted(path.name for path in output_dir.glob("*"))
    if "sector_macro_regime_summary.json" not in output_names:
        output_names.append("sector_macro_regime_summary.json")
        output_names.sort()

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "output_dir": str(output_dir),
        "quarter_count": int(quarterly_regime_history["fiscal_quarter"].nunique()) if not quarterly_regime_history.empty else 0,
        "sector_count": int(sector_macro_panel["sector"].nunique()) if not sector_macro_panel.empty else 0,
        "panel_rows": int(len(sector_macro_panel)),
        "current_regime": current_regime,
        "regime_transition_count": int(len(regime_transition_episodes)),
        "trough_event_count": int(len(trough_event_table)),
        "weakest_regimes": weakest_regimes,
        "deepest_trough_highlights": trough_highlights,
        "outputs": output_names,
    }
    (output_dir / "sector_macro_regime_summary.json").write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )
    return summary


def build_sector_macro_regime_research(
    *,
    project_root: Path | None = None,
    analysis_output_dir: Path = DEFAULT_FUNDAMENTALS_ANALYSIS_OUTPUT_DIR,
    sector_research_output_dir: Path = DEFAULT_SECTOR_FUNDAMENTALS_RESEARCH_OUTPUT_DIR,
    fundamentals_data_dir: Path | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    lookback_years: int = REPORT_LOOKBACK_YEARS,
    trough_lookback_quarters: int = DEFAULT_TROUGH_LOOKBACK_QUARTERS,
    regime_lookahead_quarters: int = DEFAULT_REGIME_LOOKAHEAD_QUARTERS,
    refresh_sector_research: bool = False,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    resolved_output_dir = _resolved_output_dir(root, output_dir)
    resolved_analysis_output_dir, resolved_sector_research_output_dir = _ensure_sector_research_outputs(
        root=root,
        analysis_output_dir=analysis_output_dir,
        sector_research_output_dir=sector_research_output_dir,
        fundamentals_data_dir=fundamentals_data_dir,
        refresh=refresh_sector_research,
    )

    quarterly_regime_history = build_quarterly_regime_history(
        root=root,
        lookback_years=lookback_years,
        lookahead_quarters=regime_lookahead_quarters,
    )
    sector_macro_panel = build_sector_macro_panel(
        analysis_output_dir=resolved_analysis_output_dir,
        sector_research_output_dir=resolved_sector_research_output_dir,
        quarterly_regime_history=quarterly_regime_history,
    )
    quarterly_earnings_breadth = build_quarterly_earnings_breadth(sector_macro_panel)
    regime_earnings_summary = build_regime_earnings_summary(sector_macro_panel)
    regime_transition_episodes, regime_transition_summary = build_regime_transition_tables(
        quarterly_regime_history=quarterly_regime_history,
        quarterly_earnings_breadth=quarterly_earnings_breadth,
    )
    (
        trough_event_table,
        trough_regime_summary,
        trough_sector_summary,
    ) = build_sector_earnings_trough_tables(
        sector_panel=sector_macro_panel,
        trough_lookback_quarters=trough_lookback_quarters,
        regime_lookahead_quarters=regime_lookahead_quarters,
    )
    return write_outputs(
        output_dir=resolved_output_dir,
        quarterly_regime_history=quarterly_regime_history,
        sector_macro_panel=sector_macro_panel,
        quarterly_earnings_breadth=quarterly_earnings_breadth,
        regime_earnings_summary=regime_earnings_summary,
        regime_transition_episodes=regime_transition_episodes,
        regime_transition_summary=regime_transition_summary,
        trough_event_table=trough_event_table,
        trough_regime_summary=trough_regime_summary,
        trough_sector_summary=trough_sector_summary,
    )


def main() -> None:
    args = parse_args()
    summary = build_sector_macro_regime_research(
        project_root=args.project_root,
        analysis_output_dir=args.analysis_output_dir,
        sector_research_output_dir=args.sector_research_output_dir,
        fundamentals_data_dir=args.fundamentals_data_dir,
        output_dir=args.output_dir,
        lookback_years=args.lookback_years,
        trough_lookback_quarters=args.trough_lookback_quarters,
        regime_lookahead_quarters=args.regime_lookahead_quarters,
        refresh_sector_research=args.refresh_sector_research,
    )
    print(f"Wrote sector macro-regime research outputs to {summary['output_dir']}")
    print(
        "Built macro-regime panel with "
        f"{summary['panel_rows']} rows, "
        f"{summary['quarter_count']} quarters, and "
        f"{summary['trough_event_count']} trough events."
    )


if __name__ == "__main__":
    main()