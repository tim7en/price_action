from __future__ import annotations

import argparse
import json
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, precision_score, recall_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .data import resolve_project_root
from .fundamentals_analysis import DEFAULT_OUTPUT_DIR as DEFAULT_FUNDAMENTALS_ANALYSIS_OUTPUT_DIR
from .macro_report import REPORT_LOOKBACK_YEARS, _build_regime_overview, load_model_macro_frame
from .sector_fundamentals_research import (
    DEFAULT_OUTPUT_DIR as DEFAULT_SECTOR_FUNDAMENTALS_RESEARCH_OUTPUT_DIR,
)
from .sector_fundamentals_research import build_sector_fundamentals_research
from .train import build_base_models, calendar_walk_forward_splits

DEFAULT_OUTPUT_DIR = Path("outputs") / "sector_macro_regime_research"
DEFAULT_TROUGH_LOOKBACK_QUARTERS = 4
DEFAULT_REGIME_LOOKAHEAD_QUARTERS = 2
DEFAULT_REGIME_HOLDOUT_START = "2022-01-01"
DEFAULT_REGIME_TRAIN_YEARS = 8
DEFAULT_REGIME_VALIDATION_YEARS = 2
LEAD_LAG_MAX_QUARTERS = 4
REGIME_IMPROVEMENT_THRESHOLD = 0.50

BENIGN_REGIMES: frozenset[str] = frozenset(
    {
        "Disinflationary Growth",
        "Recovery And Reflation",
        "Inflationary Boom",
        "Sideways Low-Volatility Regime",
    }
)

REGIME_MODEL_SPECS: tuple[dict[str, str], ...] = (
    {
        "key": "elastic_net",
        "label": "Elastic Net",
        "probability_column": "prob_elastic_net",
    },
    {
        "key": "extra_trees",
        "label": "Extra Trees",
        "probability_column": "prob_extra_trees",
    },
    {
        "key": "lightgbm",
        "label": "LightGBM / HistGB",
        "probability_column": "prob_lightgbm",
    },
    {
        "key": "ensemble",
        "label": "Average Ensemble",
        "probability_column": "ensemble_probability",
    },
)

REGIME_TARGET_SPECS: tuple[dict[str, str], ...] = (
    {
        "key": "macro_regime_change_next_window",
        "label": "Any Regime Change Within Next 2Q",
    },
    {
        "key": "macro_shift_to_benign_next_window",
        "label": "Shift To Benign Regime Within Next 2Q",
    },
    {
        "key": "macro_improves_next_window",
        "label": "Macro Balance Improves > 0.5 Within Next 2Q",
    },
    {
        "key": "current_regime_is_benign",
        "label": "Current Regime Is Benign",
    },
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
    has_future = combined.notna().any(axis=1)
    result = combined.ne(frame[current_column], axis=0).any(axis=1)
    return result.where(has_future)


def _future_benign_flag(frame: pd.DataFrame, column: str, lookahead_quarters: int) -> pd.Series:
    future_values = [frame[column].shift(-step) for step in range(1, lookahead_quarters + 1)]
    combined = pd.concat(future_values, axis=1)
    has_future = combined.notna().any(axis=1)
    result = combined.isin(BENIGN_REGIMES).any(axis=1)
    return result.where(has_future)


def _safe_corr(left: pd.Series, right: pd.Series) -> float | None:
    pair = pd.DataFrame({"left": left, "right": right}).dropna()
    if len(pair) < 3:
        return None
    correlation = pair["left"].corr(pair["right"])
    if pd.isna(correlation):
        return None
    return float(correlation)


def _unwrap_estimator(model: Any) -> Any:
    estimator = model.named_steps["model"] if hasattr(model, "named_steps") else model
    while hasattr(estimator, "named_steps") and "model" in estimator.named_steps:
        estimator = estimator.named_steps["model"]
    return estimator


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


def build_quarterly_sector_context(sector_panel: pd.DataFrame) -> pd.DataFrame:
    context = (
        sector_panel.groupby("fiscal_quarter")
        .agg(
            quarter_end_date=("quarter_end_date", "first"),
            eps_growth_dispersion=("cap_weighted_quarterly_eps_yoy_pct", "std"),
            surprise_dispersion=("cap_weighted_surprise_pct", "std"),
            eps_growth_spread=(
                "cap_weighted_quarterly_eps_yoy_pct",
                lambda series: float(series.max() - series.min()) if series.notna().any() else np.nan,
            ),
            surprise_spread=(
                "cap_weighted_surprise_pct",
                lambda series: float(series.max() - series.min()) if series.notna().any() else np.nan,
            ),
            relative_ret_1q_median=("relative_ret_1q", "median"),
            relative_ret_2q_median=("relative_ret_2q", "median"),
            relative_ret_1y_median=("relative_ret_1y", "median"),
            relative_drawdown_2q_median=("relative_drawdown_2q", "median"),
            etf_vol_1q_median=("etf_vol_1q", "median"),
            etf_sma_gap_median=("etf_sma_gap", "median"),
        )
        .reset_index()
        .sort_values("quarter_end_date")
        .reset_index(drop=True)
    )
    return context


def build_macro_earnings_signal_frame(
    *,
    quarterly_regime_history: pd.DataFrame,
    quarterly_earnings_breadth: pd.DataFrame,
    quarterly_sector_context: pd.DataFrame,
) -> pd.DataFrame:
    frame = quarterly_regime_history.merge(
        quarterly_earnings_breadth,
        on="fiscal_quarter",
        how="left",
        suffixes=("_macro", "_breadth"),
    ).merge(
        quarterly_sector_context,
        on="fiscal_quarter",
        how="left",
        suffixes=("", "_context"),
    )
    frame["quarter_end_date"] = frame["quarter_end_date_breadth"].combine_first(frame["quarter_end_date_macro"])
    frame["macro_balance_score"] = frame["macro_balance_score_breadth"].combine_first(frame["macro_balance_score_macro"])
    frame["growth_axis"] = frame["growth_axis_breadth"].combine_first(frame["growth_axis_macro"])
    frame["inflation_axis"] = frame["inflation_axis_breadth"].combine_first(frame["inflation_axis_macro"])
    frame["stress_axis"] = frame["stress_axis_breadth"].combine_first(frame["stress_axis_macro"])
    frame["macro_improves_next_window"] = (
        frame["macro_balance_improvement_next_window"] > REGIME_IMPROVEMENT_THRESHOLD
    ).where(frame["macro_balance_improvement_next_window"].notna())
    frame["macro_deteriorates_next_window"] = (
        frame["macro_balance_deterioration_next_window"] < -REGIME_IMPROVEMENT_THRESHOLD
    ).where(frame["macro_balance_deterioration_next_window"].notna())
    return frame.sort_values("quarter_end_date").reset_index(drop=True)


def build_macro_earnings_lead_lag_table(
    signal_frame: pd.DataFrame,
    *,
    max_lead_quarters: int = LEAD_LAG_MAX_QUARTERS,
) -> pd.DataFrame:
    pair_specs = (
        {
            "direction": "earnings_to_macro",
            "source_metric": "median_eps_growth",
            "target_metric": "macro_balance_score_change_1q",
            "relationship_label": "Median EPS Growth vs Macro Balance Change",
        },
        {
            "direction": "earnings_to_macro",
            "source_metric": "negative_eps_growth_share",
            "target_metric": "macro_balance_score_change_1q",
            "relationship_label": "Negative EPS Share vs Macro Balance Change",
        },
        {
            "direction": "earnings_to_macro",
            "source_metric": "median_surprise",
            "target_metric": "macro_balance_score_change_1q",
            "relationship_label": "Median Surprise vs Macro Balance Change",
        },
        {
            "direction": "macro_to_earnings",
            "source_metric": "macro_balance_score",
            "target_metric": "median_eps_growth",
            "relationship_label": "Macro Balance vs Median EPS Growth",
        },
        {
            "direction": "macro_to_earnings",
            "source_metric": "macro_balance_score",
            "target_metric": "negative_eps_growth_share",
            "relationship_label": "Macro Balance vs Negative EPS Share",
        },
        {
            "direction": "macro_to_earnings",
            "source_metric": "stress_axis",
            "target_metric": "median_eps_growth",
            "relationship_label": "Stress Axis vs Median EPS Growth",
        },
    )
    rows: list[dict[str, Any]] = []
    for spec in pair_specs:
        source = pd.to_numeric(signal_frame[spec["source_metric"]], errors="coerce")
        target_base = pd.to_numeric(signal_frame[spec["target_metric"]], errors="coerce")
        for lead_quarters in range(-max_lead_quarters, max_lead_quarters + 1):
            shifted_target = target_base.shift(-lead_quarters)
            pair = pd.DataFrame({"source": source, "target": shifted_target}).dropna()
            rows.append(
                {
                    **spec,
                    "lead_quarters": lead_quarters,
                    "observation_count": int(len(pair)),
                    "correlation": _safe_corr(pair["source"], pair["target"]) if not pair.empty else None,
                }
            )
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    table["abs_correlation"] = table["correlation"].abs()
    return table.sort_values(
        ["relationship_label", "lead_quarters"],
        ascending=[True, True],
    ).reset_index(drop=True)


def build_sector_macro_sensitivity_table(sector_panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for sector, group in sector_panel.groupby("sector"):
        ordered = group.sort_values("quarter_end_date").copy()
        ordered["macro_balance_next_q"] = ordered["macro_balance_score"].shift(-1)
        ordered["macro_balance_change_next_q"] = ordered["macro_balance_next_q"] - ordered["macro_balance_score"]
        rows.append(
            {
                "sector": sector,
                "quarter_count": int(len(ordered)),
                "avg_eps_growth": float(ordered["cap_weighted_quarterly_eps_yoy_pct"].mean()),
                "avg_surprise": float(ordered["cap_weighted_surprise_pct"].mean()),
                "avg_next_q_excess_return": float(ordered["target_excess_return"].mean()),
                "macro_to_current_eps_growth_corr": _safe_corr(
                    ordered["macro_balance_score"],
                    ordered["cap_weighted_quarterly_eps_yoy_pct"],
                ),
                "macro_to_current_surprise_corr": _safe_corr(
                    ordered["macro_balance_score"],
                    ordered["cap_weighted_surprise_pct"],
                ),
                "macro_to_next_excess_corr": _safe_corr(
                    ordered["macro_balance_score"],
                    ordered["target_excess_return"],
                ),
                "macro_to_next_sector_return_corr": _safe_corr(
                    ordered["macro_balance_score"],
                    ordered["sector_next_q_return"],
                ),
                "earnings_to_next_macro_change_corr": _safe_corr(
                    ordered["cap_weighted_quarterly_eps_yoy_pct"],
                    ordered["macro_balance_change_next_q"],
                ),
                "surprise_to_next_macro_change_corr": _safe_corr(
                    ordered["cap_weighted_surprise_pct"],
                    ordered["macro_balance_change_next_q"],
                ),
                "earnings_to_next_excess_corr": _safe_corr(
                    ordered["cap_weighted_quarterly_eps_yoy_pct"],
                    ordered["target_excess_return"],
                ),
            }
        )

    table = pd.DataFrame(rows)
    if table.empty:
        return table
    table["abs_macro_to_next_excess_corr"] = table["macro_to_next_excess_corr"].abs()
    table["abs_earnings_to_next_macro_change_corr"] = table["earnings_to_next_macro_change_corr"].abs()
    return table.sort_values("abs_macro_to_next_excess_corr", ascending=False).reset_index(drop=True)


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
        on="fiscal_quarter",
        how="left",
        suffixes=("_macro", "_earnings"),
    )
    transition_frame["quarter_end_date"] = transition_frame["quarter_end_date_earnings"].combine_first(
        transition_frame["quarter_end_date_macro"]
    )
    transition_frame["macro_balance_score"] = transition_frame["macro_balance_score_earnings"].combine_first(
        transition_frame["macro_balance_score_macro"]
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
        transition_frame["regime_shift_flag"]
        & transition_frame["prior_regime_label"].notna()
        & transition_frame["median_eps_growth"].notna()
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


def _build_regime_models(random_state: int) -> dict[str, Any]:
    base_models = build_base_models(random_state=random_state)
    return {
        "elastic_net": Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        solver="saga",
                        penalty="elasticnet",
                        l1_ratio=0.5,
                        C=0.5,
                        max_iter=4_000,
                        class_weight="balanced",
                        random_state=random_state,
                    ),
                ),
            ]
        ),
        "extra_trees": base_models["extra_trees"],
        "lightgbm": base_models["lightgbm"],
    }


def build_regime_ml_frame(
    signal_frame: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    frame = signal_frame.copy().sort_values("quarter_end_date").reset_index(drop=True)
    base_feature_columns = [
        "median_eps_growth",
        "mean_eps_growth",
        "median_surprise",
        "mean_surprise",
        "negative_eps_growth_share",
        "negative_surprise_share",
        "eps_growth_dispersion",
        "surprise_dispersion",
        "eps_growth_spread",
        "surprise_spread",
        "relative_ret_1q_median",
        "relative_ret_2q_median",
        "relative_ret_1y_median",
        "relative_drawdown_2q_median",
        "etf_vol_1q_median",
        "etf_sma_gap_median",
        "macro_balance_score",
        "growth_axis",
        "inflation_axis",
        "stress_axis",
    ]
    available = [column for column in base_feature_columns if column in frame.columns]
    feature_columns: list[str] = []
    engineered_features: dict[str, pd.Series] = {}
    for column in available:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        feature_columns.append(column)
        for lag in (1, 2, 4):
            lagged_name = f"{column}_lag{lag}"
            engineered_features[lagged_name] = frame[column].shift(lag)
            feature_columns.append(lagged_name)
        for change in (1, 2):
            change_name = f"{column}_chg{change}"
            engineered_features[change_name] = frame[column] - frame[column].shift(change)
            feature_columns.append(change_name)
    if engineered_features:
        frame = pd.concat([frame, pd.DataFrame(engineered_features)], axis=1)
    return frame, feature_columns


def _regime_classification_summary(frame: pd.DataFrame, probability_column: str) -> dict[str, Any]:
    if frame.empty or probability_column not in frame.columns:
        return {
            "sample_count": 0,
            "positive_rate": None,
            "roc_auc": None,
            "brier": None,
            "precision": None,
            "recall": None,
        }

    actual = frame["actual_target"].astype(int)
    probabilities = frame[probability_column].astype(float)
    predicted = (probabilities >= 0.5).astype(int)
    if actual.nunique() < 2:
        roc_auc = None
    else:
        roc_auc = float(roc_auc_score(actual, probabilities))
    return {
        "sample_count": int(len(frame)),
        "positive_rate": float(actual.mean()),
        "roc_auc": roc_auc,
        "brier": float(brier_score_loss(actual, probabilities)),
        "precision": float(precision_score(actual, predicted, zero_division=0)),
        "recall": float(recall_score(actual, predicted, zero_division=0)),
    }


def _fit_predict_regime_split(
    *,
    train_frame: pd.DataFrame,
    test_frame: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
    random_state: int,
) -> pd.DataFrame:
    x_train = train_frame[feature_columns].copy()
    x_test = test_frame[feature_columns].copy()
    y_train = train_frame[target_column].astype(int)

    predictions = test_frame[
        [
            "quarter_end_date",
            "fiscal_quarter",
            "quarter_end_regime_label",
            "macro_balance_score",
            "median_eps_growth",
            "negative_eps_growth_share",
        ]
    ].copy()
    predictions["actual_target"] = test_frame[target_column].astype(int)

    models = _build_regime_models(random_state=random_state)
    probability_columns: list[str] = []
    for spec in REGIME_MODEL_SPECS[:-1]:
        model = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("model", clone(models[spec["key"]])),
            ]
        )
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="X does not have valid feature names",
            )
            model.fit(x_train, y_train)
        predictions[spec["probability_column"]] = model.predict_proba(x_test)[:, 1]
        probability_columns.append(spec["probability_column"])

    predictions["ensemble_probability"] = predictions[probability_columns].mean(axis=1)
    return predictions


def run_regime_detection_models(
    *,
    regime_ml_frame: pd.DataFrame,
    feature_columns: list[str],
    holdout_start: str = DEFAULT_REGIME_HOLDOUT_START,
    train_years: int = DEFAULT_REGIME_TRAIN_YEARS,
    validation_years: int = DEFAULT_REGIME_VALIDATION_YEARS,
    random_state: int = 7,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    base_frame = regime_ml_frame.dropna(subset=["quarter_end_date"]).sort_values("quarter_end_date").reset_index(drop=True)
    validation_predictions: list[pd.DataFrame] = []
    holdout_predictions: list[pd.DataFrame] = []
    metric_rows: list[dict[str, Any]] = []

    for target_spec in REGIME_TARGET_SPECS:
        target_column = target_spec["key"]
        modeling_frame = base_frame.loc[base_frame[target_column].notna()].copy()
        if modeling_frame.empty or modeling_frame[target_column].nunique() < 2:
            continue
        splits, holdout_split = calendar_walk_forward_splits(
            index=pd.DatetimeIndex(modeling_frame["quarter_end_date"]),
            train_years=train_years,
            validation_years=validation_years,
            embargo_size=0,
            purge_size=0,
            holdout_start=holdout_start,
            expanding_train=True,
        )
        if not splits:
            continue

        target_validation_frames: list[pd.DataFrame] = []
        for train_idx, test_idx, fold_label in splits:
            train_frame = modeling_frame.iloc[train_idx]
            test_frame = modeling_frame.iloc[test_idx]
            if train_frame[target_column].nunique() < 2:
                continue
            fold_predictions = _fit_predict_regime_split(
                train_frame=train_frame,
                test_frame=test_frame,
                feature_columns=feature_columns,
                target_column=target_column,
                random_state=random_state,
            )
            fold_predictions.insert(0, "fold_label", fold_label)
            fold_predictions.insert(1, "target_key", target_spec["key"])
            fold_predictions.insert(2, "target_label", target_spec["label"])
            target_validation_frames.append(fold_predictions)

        target_validation = (
            pd.concat(target_validation_frames, ignore_index=True) if target_validation_frames else pd.DataFrame()
        )
        if not target_validation.empty:
            validation_predictions.append(target_validation)

        target_holdout = pd.DataFrame()
        if holdout_split is not None:
            train_idx, test_idx, fold_label = holdout_split
            train_frame = modeling_frame.iloc[train_idx]
            test_frame = modeling_frame.iloc[test_idx]
            if train_frame[target_column].nunique() >= 2:
                target_holdout = _fit_predict_regime_split(
                    train_frame=train_frame,
                    test_frame=test_frame,
                    feature_columns=feature_columns,
                    target_column=target_column,
                    random_state=random_state,
                )
                target_holdout.insert(0, "fold_label", fold_label)
                target_holdout.insert(1, "target_key", target_spec["key"])
                target_holdout.insert(2, "target_label", target_spec["label"])
                holdout_predictions.append(target_holdout)

        for scope, frame in (("validation", target_validation), ("holdout", target_holdout)):
            for spec in REGIME_MODEL_SPECS:
                metric_rows.append(
                    {
                        "target_key": target_spec["key"],
                        "target_label": target_spec["label"],
                        "scope": scope,
                        "model_label": spec["label"],
                        **_regime_classification_summary(frame, spec["probability_column"]),
                    }
                )

    validation_frame = pd.concat(validation_predictions, ignore_index=True) if validation_predictions else pd.DataFrame()
    holdout_frame = pd.concat(holdout_predictions, ignore_index=True) if holdout_predictions else pd.DataFrame()
    metric_table = pd.DataFrame(metric_rows)
    return validation_frame, holdout_frame, metric_table


def build_regime_ml_feature_importance(
    *,
    regime_ml_frame: pd.DataFrame,
    feature_columns: list[str],
    holdout_start: str = DEFAULT_REGIME_HOLDOUT_START,
    random_state: int = 7,
) -> pd.DataFrame:
    pre_holdout = regime_ml_frame.loc[
        regime_ml_frame["quarter_end_date"] < pd.Timestamp(holdout_start)
    ].copy()
    if pre_holdout.empty:
        return pd.DataFrame()

    models = _build_regime_models(random_state=random_state)
    rows: list[dict[str, Any]] = []
    for target_spec in REGIME_TARGET_SPECS:
        target_column = target_spec["key"]
        target_frame = pre_holdout.loc[pre_holdout[target_column].notna()].copy()
        if target_frame.empty or target_frame[target_column].nunique() < 2:
            continue
        x_train = target_frame[feature_columns].copy()
        y_train = target_frame[target_column].astype(int)
        for spec in REGIME_MODEL_SPECS[:-1]:
            model = Pipeline(
                steps=[
                    ("imputer", SimpleImputer(strategy="median")),
                    ("model", clone(models[spec["key"]])),
                ]
            )
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="X does not have valid feature names",
                )
                model.fit(x_train, y_train)
            estimator = _unwrap_estimator(model)
            if hasattr(estimator, "coef_"):
                importance_values = np.abs(np.ravel(estimator.coef_))
            elif hasattr(estimator, "feature_importances_"):
                importance_values = np.asarray(estimator.feature_importances_, dtype="float64")
            else:
                continue
            total = float(np.nansum(importance_values))
            if total > 0.0:
                importance_values = importance_values / total
            for feature_name, importance in zip(feature_columns, importance_values, strict=False):
                rows.append(
                    {
                        "target_key": target_spec["key"],
                        "target_label": target_spec["label"],
                        "model_label": spec["label"],
                        "feature": feature_name,
                        "importance": float(importance),
                    }
                )

    table = pd.DataFrame(rows)
    if table.empty:
        return table
    ensemble = (
        table.groupby(["target_key", "target_label", "feature"], as_index=False)["importance"]
        .mean()
        .assign(model_label="Average Ensemble")
    )
    return pd.concat([table, ensemble], ignore_index=True).sort_values(
        ["target_label", "model_label", "importance", "feature"],
        ascending=[True, True, False, True],
    )


def write_outputs(
    *,
    output_dir: Path,
    quarterly_regime_history: pd.DataFrame,
    sector_macro_panel: pd.DataFrame,
    quarterly_earnings_breadth: pd.DataFrame,
    quarterly_sector_context: pd.DataFrame,
    macro_earnings_lead_lag: pd.DataFrame,
    sector_macro_sensitivity: pd.DataFrame,
    regime_earnings_summary: pd.DataFrame,
    regime_transition_episodes: pd.DataFrame,
    regime_transition_summary: pd.DataFrame,
    trough_event_table: pd.DataFrame,
    trough_regime_summary: pd.DataFrame,
    trough_sector_summary: pd.DataFrame,
    regime_ml_validation_predictions: pd.DataFrame,
    regime_ml_holdout_predictions: pd.DataFrame,
    regime_ml_metrics: pd.DataFrame,
    regime_ml_feature_importance: pd.DataFrame,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    quarterly_regime_history.to_csv(output_dir / "macro_regime_quarterly_history.csv", index=False)
    sector_macro_panel.to_csv(output_dir / "sector_macro_regime_panel.csv", index=False)
    quarterly_earnings_breadth.to_csv(output_dir / "quarterly_earnings_breadth.csv", index=False)
    quarterly_sector_context.to_csv(output_dir / "quarterly_sector_context.csv", index=False)
    macro_earnings_lead_lag.to_csv(output_dir / "macro_earnings_lead_lag.csv", index=False)
    sector_macro_sensitivity.to_csv(output_dir / "sector_macro_sensitivity.csv", index=False)
    regime_earnings_summary.to_csv(output_dir / "regime_earnings_summary.csv", index=False)
    regime_transition_episodes.to_csv(output_dir / "regime_transition_episode_table.csv", index=False)
    regime_transition_summary.to_csv(output_dir / "regime_transition_summary.csv", index=False)
    trough_event_table.to_csv(output_dir / "sector_earnings_trough_events.csv", index=False)
    trough_regime_summary.to_csv(output_dir / "sector_earnings_trough_regime_summary.csv", index=False)
    trough_sector_summary.to_csv(output_dir / "sector_earnings_trough_sector_summary.csv", index=False)
    regime_ml_validation_predictions.to_csv(output_dir / "regime_ml_validation_predictions.csv", index=False)
    regime_ml_holdout_predictions.to_csv(output_dir / "regime_ml_holdout_predictions.csv", index=False)
    regime_ml_metrics.to_csv(output_dir / "regime_ml_metrics.csv", index=False)
    regime_ml_feature_importance.to_csv(output_dir / "regime_ml_feature_importance.csv", index=False)

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
    lead_lag_highlights = (
        macro_earnings_lead_lag.loc[macro_earnings_lead_lag["lead_quarters"] > 0]
        .sort_values(["abs_correlation", "lead_quarters"], ascending=[False, True])
        .head(10)
        .to_dict(orient="records")
        if not macro_earnings_lead_lag.empty
        else []
    )
    sector_sensitivity_highlights = (
        sector_macro_sensitivity.sort_values(
            ["abs_macro_to_next_excess_corr", "abs_earnings_to_next_macro_change_corr"],
            ascending=[False, False],
        )
        .head(10)
        .to_dict(orient="records")
        if not sector_macro_sensitivity.empty
        else []
    )
    regime_ml_best_results = (
        regime_ml_metrics.loc[regime_ml_metrics["scope"] == "validation"]
        .sort_values(["roc_auc", "sample_count"], ascending=[False, False])
        .head(10)
        .to_dict(orient="records")
        if not regime_ml_metrics.empty
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
        "lead_lag_highlights": lead_lag_highlights,
        "sector_sensitivity_highlights": sector_sensitivity_highlights,
        "regime_ml_best_results": regime_ml_best_results,
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
    quarterly_sector_context = build_quarterly_sector_context(sector_macro_panel)
    signal_frame = build_macro_earnings_signal_frame(
        quarterly_regime_history=quarterly_regime_history,
        quarterly_earnings_breadth=quarterly_earnings_breadth,
        quarterly_sector_context=quarterly_sector_context,
    )
    macro_earnings_lead_lag = build_macro_earnings_lead_lag_table(signal_frame)
    sector_macro_sensitivity = build_sector_macro_sensitivity_table(sector_macro_panel)
    regime_ml_frame, regime_ml_feature_columns = build_regime_ml_frame(signal_frame)
    (
        regime_ml_validation_predictions,
        regime_ml_holdout_predictions,
        regime_ml_metrics,
    ) = run_regime_detection_models(
        regime_ml_frame=regime_ml_frame,
        feature_columns=regime_ml_feature_columns,
    )
    regime_ml_feature_importance = build_regime_ml_feature_importance(
        regime_ml_frame=regime_ml_frame,
        feature_columns=regime_ml_feature_columns,
    )
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
        quarterly_sector_context=quarterly_sector_context,
        macro_earnings_lead_lag=macro_earnings_lead_lag,
        sector_macro_sensitivity=sector_macro_sensitivity,
        regime_earnings_summary=regime_earnings_summary,
        regime_transition_episodes=regime_transition_episodes,
        regime_transition_summary=regime_transition_summary,
        trough_event_table=trough_event_table,
        trough_regime_summary=trough_regime_summary,
        trough_sector_summary=trough_sector_summary,
        regime_ml_validation_predictions=regime_ml_validation_predictions,
        regime_ml_holdout_predictions=regime_ml_holdout_predictions,
        regime_ml_metrics=regime_ml_metrics,
        regime_ml_feature_importance=regime_ml_feature_importance,
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