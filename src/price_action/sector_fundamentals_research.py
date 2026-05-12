from __future__ import annotations

import argparse
import json
import math
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import accuracy_score, brier_score_loss, precision_score, recall_score, roc_auc_score

from .data import load_asset_daily, resolve_project_root
from .fundamentals_analysis import DEFAULT_OUTPUT_DIR as DEFAULT_FUNDAMENTALS_ANALYSIS_OUTPUT_DIR
from .fundamentals_analysis import run_analysis as run_fundamentals_analysis
from .train import build_base_models, calendar_walk_forward_splits

DEFAULT_OUTPUT_DIR = Path("outputs") / "sector_fundamentals_research"
DEFAULT_HOLDOUT_START = "2025-01-01"
DEFAULT_START_QUARTER = "2003Q1"
DEFAULT_TRAIN_YEARS = 5
DEFAULT_VALIDATION_YEARS = 1
DEFAULT_TOP_N = 3

SECTOR_ETF_MAP: dict[str, str] = {
    "COMMUNICATION SERVICES": "XLC",
    "CONSUMER DISCRETIONARY": "XLY",
    "CONSUMER STAPLES": "XLP",
    "ENERGY": "XLE",
    "FINANCIALS": "XLF",
    "HEALTHCARE": "XLV",
    "INDUSTRIALS": "XLI",
    "MATERIALS": "XLB",
    "REAL ESTATE": "XLRE",
    "TECHNOLOGY": "XLK",
    "UTILITIES": "XLU",
}
MODEL_SPECS: tuple[dict[str, str], ...] = (
    {
        "key": "elastic_net",
        "label": "Elastic Net",
        "probability_column": "prob_elastic_net",
    },
    {
        "key": "extra_trees",
        "label": "ExtraTrees",
        "probability_column": "prob_extra_trees",
    },
    {
        "key": "lightgbm",
        "label": "LightGBM",
        "probability_column": "prob_lightgbm",
    },
    {
        "key": "average_ensemble",
        "label": "Average Ensemble",
        "probability_column": "ensemble_probability",
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a sector-level earnings research panel with ETF-relative ensemble modeling "
            "and write notebook-friendly outputs."
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
        "--fundamentals-data-dir",
        type=Path,
        default=None,
        help="Optional fundamentals history directory used when the cleaned analysis outputs need a rebuild.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for the generated sector research outputs.",
    )
    parser.add_argument(
        "--start-quarter",
        type=str,
        default=DEFAULT_START_QUARTER,
        help="First quarter kept in the panel, e.g. 2003Q1.",
    )
    parser.add_argument(
        "--holdout-start",
        type=str,
        default=DEFAULT_HOLDOUT_START,
        help="Holdout start date used for the quarterly panel walk-forward split.",
    )
    parser.add_argument(
        "--train-years",
        type=int,
        default=DEFAULT_TRAIN_YEARS,
        help="Training years used for the calendar walk-forward panel split.",
    )
    parser.add_argument(
        "--validation-years",
        type=int,
        default=DEFAULT_VALIDATION_YEARS,
        help="Validation years used for the calendar walk-forward panel split.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_TOP_N,
        help="Number of sectors selected each quarter in the ranking strategy view.",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Random state passed to the ensemble models.",
    )
    parser.add_argument(
        "--refresh-fundamentals",
        action="store_true",
        help="Force a rebuild of the cleaned fundamentals analysis outputs before the research panel runs.",
    )
    return parser.parse_args()


def _safe_float(value: Any) -> float:
    if value is None:
        return math.nan
    if isinstance(value, bool):
        return math.nan
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"none", "nan", "null", "n/a", "-", "--"}:
        return math.nan
    try:
        return float(text)
    except ValueError:
        return math.nan


def _resolved_output_dir(root: Path, output_dir: Path) -> Path:
    return output_dir if output_dir.is_absolute() else root / output_dir


def _quarter_timestamp(quarter_label: str) -> pd.Timestamp:
    return pd.Period(quarter_label, freq="Q").to_timestamp(how="end").normalize()


def _ensure_fundamentals_outputs(
    *,
    root: Path,
    analysis_output_dir: Path,
    fundamentals_data_dir: Path | None,
    refresh: bool,
) -> Path:
    resolved_analysis_output_dir = _resolved_output_dir(root, analysis_output_dir)
    summary_path = resolved_analysis_output_dir / "fundamentals_analysis_summary.json"
    if refresh or not summary_path.exists():
        run_fundamentals_analysis(
            project_root=root,
            data_dir=fundamentals_data_dir,
            output_dir=resolved_analysis_output_dir,
        )
    return resolved_analysis_output_dir


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required input not found: {path}")
    return pd.read_csv(path)


def _load_monthly_time_series(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    data = payload.get("data")
    if not isinstance(data, dict):
        return pd.DataFrame()
    time_series = data.get("Monthly Adjusted Time Series")
    if not isinstance(time_series, dict):
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for date_key, values in time_series.items():
        if not isinstance(values, dict):
            continue
        rows.append(
            {
                "date": date_key,
                "adjusted_close": _safe_float(values.get("5. adjusted close")),
                "volume": _safe_float(values.get("6. volume")),
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date")
    return frame


def build_sector_structure_features(
    *,
    root: Path,
    eligible_symbols: pd.DataFrame,
    start_quarter: str,
) -> pd.DataFrame:
    start_timestamp = _quarter_timestamp(start_quarter) - pd.DateOffset(years=1)
    monthly_frames: list[pd.DataFrame] = []
    fundamentals_dir = root / "fundamentals_history"

    for row in eligible_symbols.itertuples(index=False):
        monthly_path = fundamentals_dir / f"{row.symbol}_time_series_monthly.json"
        if not monthly_path.exists():
            continue
        monthly = _load_monthly_time_series(monthly_path)
        if monthly.empty:
            continue

        monthly = monthly.loc[monthly["date"] >= start_timestamp].copy()
        if monthly.empty:
            continue

        latest_adjusted_close = monthly["adjusted_close"].dropna()
        if latest_adjusted_close.empty:
            continue
        latest_adjusted_close_value = float(latest_adjusted_close.iloc[-1])
        if not np.isfinite(latest_adjusted_close_value) or latest_adjusted_close_value <= 0.0:
            continue

        market_cap = _safe_float(getattr(row, "market_cap", math.nan))
        monthly["symbol"] = row.symbol
        monthly["sector"] = row.sector
        monthly["fiscal_quarter"] = monthly["date"].dt.to_period("Q").astype(str)
        monthly["dollar_volume"] = monthly["adjusted_close"] * monthly["volume"]
        monthly_quarter = (
            monthly.groupby("fiscal_quarter")
            .agg(
                quarter_end_date=("date", "max"),
                adjusted_close_last=("adjusted_close", "last"),
                dollar_volume_total=("dollar_volume", "sum"),
                volume_total=("volume", "sum"),
                monthly_observations=("date", "count"),
            )
            .reset_index()
        )
        monthly_quarter["symbol"] = row.symbol
        monthly_quarter["sector"] = row.sector
        if np.isfinite(market_cap) and market_cap > 0.0:
            monthly_quarter["market_cap_proxy"] = (
                market_cap * monthly_quarter["adjusted_close_last"] / latest_adjusted_close_value
            )
        else:
            monthly_quarter["market_cap_proxy"] = math.nan
        monthly_frames.append(monthly_quarter)

    if not monthly_frames:
        return pd.DataFrame()

    symbols_quarterly = pd.concat(monthly_frames, ignore_index=True)
    grouped = symbols_quarterly.groupby(["sector", "fiscal_quarter"])
    sector_quarterly = (
        grouped.agg(
            quarter_end_date=("quarter_end_date", "max"),
            constituent_count=("symbol", "nunique"),
            market_cap_proxy_median=("market_cap_proxy", "median"),
            dollar_volume_total=("dollar_volume_total", "sum"),
            volume_total=("volume_total", "sum"),
            monthly_observations=("monthly_observations", "sum"),
        )
        .reset_index()
        .sort_values(["sector", "fiscal_quarter"])
    )
    market_cap_totals = grouped["market_cap_proxy"].sum(min_count=1).reset_index(name="market_cap_proxy_total")
    market_cap_coverage = (
        grouped["market_cap_proxy"].apply(lambda series: int(series.notna().sum())).reset_index(name="market_cap_coverage_count")
    )
    sector_quarterly = sector_quarterly.merge(market_cap_totals, on=["sector", "fiscal_quarter"], how="left")
    sector_quarterly = sector_quarterly.merge(market_cap_coverage, on=["sector", "fiscal_quarter"], how="left")
    sector_quarterly["quarter_end_date"] = pd.to_datetime(sector_quarterly["quarter_end_date"], errors="coerce")
    quarter_market_cap_total = sector_quarterly.groupby("fiscal_quarter")["market_cap_proxy_total"].transform(
        lambda series: series.sum(min_count=1)
    )
    sector_quarterly["market_cap_share"] = sector_quarterly["market_cap_proxy_total"] / quarter_market_cap_total
    sector_quarterly["turnover_proxy"] = (
        sector_quarterly["dollar_volume_total"]
        / sector_quarterly["market_cap_proxy_total"].where(sector_quarterly["market_cap_proxy_total"] > 0.0)
    )
    sector_quarterly["log_market_cap_proxy_total"] = np.log(
        sector_quarterly["market_cap_proxy_total"].where(sector_quarterly["market_cap_proxy_total"] > 0.0)
    )
    sector_quarterly["log_dollar_volume_total"] = np.log1p(sector_quarterly["dollar_volume_total"])
    for column in ("market_cap_proxy_total", "dollar_volume_total", "volume_total", "turnover_proxy"):
        sector_quarterly[f"{column}_qoq_pct"] = sector_quarterly.groupby("sector")[column].pct_change(
            fill_method=None
        )
    return sector_quarterly


def _quarterly_market_snapshot(frame: pd.DataFrame, *, prefix: str) -> pd.DataFrame:
    market = frame.sort_index().copy()
    close = pd.to_numeric(market["close"], errors="coerce")
    atr = pd.to_numeric(market.get("atr"), errors="coerce")
    sma = pd.to_numeric(market.get("sma"), errors="coerce")
    returns = close.pct_change(fill_method=None)

    quarter = pd.DataFrame(index=market.index)
    quarter[f"{prefix}_close"] = close
    quarter[f"{prefix}_ret_1q"] = close.pct_change(63, fill_method=None)
    quarter[f"{prefix}_ret_2q"] = close.pct_change(126, fill_method=None)
    quarter[f"{prefix}_ret_1y"] = close.pct_change(252, fill_method=None)
    quarter[f"{prefix}_vol_1m"] = returns.rolling(21, min_periods=15).std() * np.sqrt(252.0)
    quarter[f"{prefix}_vol_1q"] = returns.rolling(63, min_periods=40).std() * np.sqrt(252.0)
    quarter[f"{prefix}_atr_pct"] = atr / close
    quarter[f"{prefix}_sma_gap"] = close / sma - 1.0
    quarter[f"{prefix}_drawdown_2q"] = close / close.rolling(126, min_periods=63).max() - 1.0
    quarter = quarter.groupby(quarter.index.to_period("Q")).tail(1).copy()
    quarter["fiscal_quarter"] = quarter.index.to_period("Q").astype(str)
    quarter["quarter_end_date"] = quarter.index.normalize()
    return quarter.sort_values("quarter_end_date").reset_index(drop=True)


def build_sector_market_features(*, root: Path) -> pd.DataFrame:
    sector_frames: list[pd.DataFrame] = []
    for sector, symbol in SECTOR_ETF_MAP.items():
        quarter = _quarterly_market_snapshot(load_asset_daily(symbol, project_root=root), prefix="etf")
        quarter["sector"] = sector
        quarter["etf_symbol"] = symbol
        quarter["sector_next_q_return"] = quarter["etf_close"].shift(-1) / quarter["etf_close"] - 1.0
        sector_frames.append(quarter)

    sector_market = pd.concat(sector_frames, ignore_index=True)
    spy = _quarterly_market_snapshot(load_asset_daily("SPY", project_root=root), prefix="spy")
    spy["spy_next_q_return"] = spy["spy_close"].shift(-1) / spy["spy_close"] - 1.0

    merged = sector_market.merge(
        spy[
            [
                "fiscal_quarter",
                "spy_ret_1q",
                "spy_ret_2q",
                "spy_ret_1y",
                "spy_vol_1m",
                "spy_vol_1q",
                "spy_atr_pct",
                "spy_sma_gap",
                "spy_drawdown_2q",
                "spy_next_q_return",
            ]
        ],
        on="fiscal_quarter",
        how="left",
    )
    merged["relative_ret_1q"] = merged["etf_ret_1q"] - merged["spy_ret_1q"]
    merged["relative_ret_2q"] = merged["etf_ret_2q"] - merged["spy_ret_2q"]
    merged["relative_ret_1y"] = merged["etf_ret_1y"] - merged["spy_ret_1y"]
    merged["relative_vol_1q"] = merged["etf_vol_1q"] - merged["spy_vol_1q"]
    merged["relative_drawdown_2q"] = merged["etf_drawdown_2q"] - merged["spy_drawdown_2q"]
    merged["target_excess_return"] = merged["sector_next_q_return"] - merged["spy_next_q_return"]
    merged["target"] = (merged["target_excess_return"] > 0.0).astype(int)
    return merged.sort_values(["sector", "fiscal_quarter"]).reset_index(drop=True)


def build_fundamental_lag_features(sector_quarterly: pd.DataFrame) -> pd.DataFrame:
    frame = sector_quarterly.copy().sort_values(["sector", "fiscal_quarter"]).reset_index(drop=True)
    feature_columns = [
        "symbol_count",
        "avg_surprise_pct",
        "median_surprise_pct",
        "cap_weighted_surprise_pct",
        "beat_rate",
        "avg_reported_eps",
        "avg_estimated_eps",
        "avg_quarterly_eps_yoy_pct",
        "cap_weighted_quarterly_eps_yoy_pct",
    ]
    for column in feature_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    grouped = frame.groupby("sector")
    for column in feature_columns:
        lag1 = grouped[column].shift(1)
        lag2 = grouped[column].shift(2)
        frame[f"{column}_lag1"] = lag1
        frame[f"{column}_lag2"] = lag2
        frame[f"{column}_lag1_change"] = lag1 - lag2
        frame[f"{column}_lag2_mean"] = pd.concat([lag1, lag2], axis=1).mean(axis=1)

    frame["quarter_end_date"] = frame["fiscal_quarter"].map(_quarter_timestamp)
    return frame


def build_sector_panel(
    *,
    fundamentals_features: pd.DataFrame,
    structure_features: pd.DataFrame,
    market_features: pd.DataFrame,
    start_quarter: str,
) -> tuple[pd.DataFrame, list[str]]:
    panel = fundamentals_features.merge(
        structure_features,
        on=["sector", "fiscal_quarter"],
        how="left",
        suffixes=("", "_structure"),
    ).merge(
        market_features,
        on=["sector", "fiscal_quarter"],
        how="inner",
        suffixes=("", "_market"),
    )
    panel = panel.loc[panel["fiscal_quarter"] >= start_quarter].copy()
    panel["quarter_end_date"] = panel.get("quarter_end_date_market", panel.get("quarter_end_date"))
    panel["quarter_end_date"] = pd.to_datetime(panel["quarter_end_date"], errors="coerce")

    rank_candidates = [
        "cap_weighted_surprise_pct_lag1",
        "cap_weighted_quarterly_eps_yoy_pct_lag1",
        "beat_rate_lag1",
        "market_cap_share",
        "turnover_proxy",
        "relative_ret_1q",
        "relative_ret_2q",
        "etf_sma_gap",
        "etf_vol_1q",
    ]
    for column in rank_candidates:
        if column in panel.columns:
            panel[f"{column}_rank"] = panel.groupby("fiscal_quarter")[column].rank(pct=True)

    sector_dummies = pd.get_dummies(panel["sector"], prefix="sector")
    panel = pd.concat([panel, sector_dummies], axis=1)

    feature_candidates = [
        "symbol_count_lag1",
        "symbol_count_lag1_change",
        "avg_surprise_pct_lag1",
        "median_surprise_pct_lag1",
        "cap_weighted_surprise_pct_lag1",
        "cap_weighted_surprise_pct_lag1_change",
        "beat_rate_lag1",
        "beat_rate_lag1_change",
        "avg_reported_eps_lag1",
        "avg_estimated_eps_lag1",
        "avg_quarterly_eps_yoy_pct_lag1",
        "cap_weighted_quarterly_eps_yoy_pct_lag1",
        "cap_weighted_quarterly_eps_yoy_pct_lag1_change",
        "market_cap_share",
        "market_cap_proxy_total_qoq_pct",
        "dollar_volume_total_qoq_pct",
        "turnover_proxy",
        "turnover_proxy_qoq_pct",
        "log_market_cap_proxy_total",
        "log_dollar_volume_total",
        "etf_ret_1q",
        "etf_ret_2q",
        "etf_ret_1y",
        "relative_ret_1q",
        "relative_ret_2q",
        "relative_ret_1y",
        "etf_vol_1m",
        "etf_vol_1q",
        "relative_vol_1q",
        "etf_atr_pct",
        "etf_sma_gap",
        "relative_drawdown_2q",
        "spy_ret_1q",
        "spy_ret_2q",
        "spy_vol_1q",
        "cap_weighted_surprise_pct_lag1_rank",
        "cap_weighted_quarterly_eps_yoy_pct_lag1_rank",
        "beat_rate_lag1_rank",
        "market_cap_share_rank",
        "turnover_proxy_rank",
        "relative_ret_1q_rank",
        "relative_ret_2q_rank",
        "etf_sma_gap_rank",
        "etf_vol_1q_rank",
    ]
    feature_columns = [
        column
        for column in feature_candidates
        if column in panel.columns and panel[column].notna().mean() >= 0.70
    ]
    feature_columns.extend(sorted(sector_dummies.columns))
    return panel, feature_columns


def _classification_summary(frame: pd.DataFrame, probability_column: str) -> dict[str, float | int | None]:
    if frame.empty:
        return {
            "observations": 0,
            "target_rate": None,
            "roc_auc": None,
            "brier_score": None,
            "accuracy": None,
            "precision": None,
            "recall": None,
        }

    y_true = frame["target"].astype(int)
    probabilities = frame[probability_column].astype(float)
    labels = (probabilities >= 0.5).astype(int)
    summary: dict[str, float | int | None] = {
        "observations": int(len(frame)),
        "target_rate": float(y_true.mean()),
        "brier_score": float(brier_score_loss(y_true, probabilities)),
        "accuracy": float(accuracy_score(y_true, labels)),
        "precision": float(precision_score(y_true, labels, zero_division=0)),
        "recall": float(recall_score(y_true, labels, zero_division=0)),
    }
    if y_true.nunique() == 2:
        summary["roc_auc"] = float(roc_auc_score(y_true, probabilities))
    else:
        summary["roc_auc"] = None
    return summary


def _quarterly_strategy_summary(frame: pd.DataFrame) -> dict[str, float | int | None]:
    if frame.empty:
        return {
            "periods": 0,
            "total_return": 0.0,
            "cagr": None,
            "sharpe": None,
            "max_drawdown": 0.0,
            "hit_rate": None,
            "avg_excess_return": None,
        }

    returns = frame["portfolio_return"].astype(float)
    excess_returns = frame["excess_return"].astype(float)
    equity = (1.0 + returns).cumprod()
    years = max(len(frame) / 4.0, 0.25)
    total_return = float(equity.iloc[-1] - 1.0)
    cagr = float(equity.iloc[-1] ** (1.0 / years) - 1.0) if equity.iloc[-1] > 0.0 else None
    volatility = float(returns.std(ddof=0))
    sharpe = float(returns.mean() / volatility * np.sqrt(4.0)) if volatility > 0.0 else None
    drawdown = equity / equity.cummax() - 1.0
    return {
        "periods": int(len(frame)),
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.min()) if not drawdown.empty else 0.0,
        "hit_rate": float((excess_returns > 0.0).mean()) if not excess_returns.empty else None,
        "avg_excess_return": float(excess_returns.mean()) if not excess_returns.empty else None,
    }


def _fit_predict_for_split(
    *,
    train_frame: pd.DataFrame,
    test_frame: pd.DataFrame,
    feature_columns: list[str],
    random_state: int,
) -> pd.DataFrame:
    x_train = train_frame[feature_columns].copy()
    x_test = test_frame[feature_columns].copy()
    median_fill = x_train.median(numeric_only=True)
    x_train = x_train.fillna(median_fill)
    x_test = x_test.fillna(median_fill)
    y_train = train_frame["target"].astype(int)

    predictions = test_frame[
        [
            "quarter_end_date",
            "fiscal_quarter",
            "sector",
            "etf_symbol",
            "target",
            "target_excess_return",
            "sector_next_q_return",
            "spy_next_q_return",
        ]
    ].copy()

    probability_columns: list[str] = []
    for spec in MODEL_SPECS[:-1]:
        model = clone(build_base_models(random_state=random_state)[spec["key"]])
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="l1_ratio parameter is only used when penalty is 'elasticnet'",
            )
            model.fit(x_train, y_train)
        predictions[spec["probability_column"]] = model.predict_proba(x_test)[:, 1]
        probability_columns.append(spec["probability_column"])

    predictions["ensemble_probability"] = predictions[probability_columns].mean(axis=1)
    return predictions


def run_sector_panel_models(
    *,
    panel: pd.DataFrame,
    feature_columns: list[str],
    holdout_start: str,
    train_years: int,
    validation_years: int,
    random_state: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    modeling_frame = panel.dropna(
        subset=["quarter_end_date", "target", "target_excess_return", "sector_next_q_return", "spy_next_q_return"]
    ).copy()
    modeling_frame = modeling_frame.sort_values(["quarter_end_date", "sector"]).reset_index(drop=True)
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
        raise ValueError("No quarterly walk-forward splits could be constructed for the sector panel.")

    validation_predictions: list[pd.DataFrame] = []
    for train_idx, test_idx, fold_label in splits:
        train_frame = modeling_frame.iloc[train_idx]
        test_frame = modeling_frame.iloc[test_idx]
        if train_frame["target"].nunique() < 2:
            continue
        fold_predictions = _fit_predict_for_split(
            train_frame=train_frame,
            test_frame=test_frame,
            feature_columns=feature_columns,
            random_state=random_state,
        )
        fold_predictions.insert(0, "fold_label", fold_label)
        validation_predictions.append(fold_predictions)

    validation_frame = pd.concat(validation_predictions, ignore_index=True) if validation_predictions else pd.DataFrame()

    holdout_frame = pd.DataFrame()
    if holdout_split is not None:
        train_idx, test_idx, fold_label = holdout_split
        train_frame = modeling_frame.iloc[train_idx]
        test_frame = modeling_frame.iloc[test_idx]
        if train_frame["target"].nunique() >= 2:
            holdout_frame = _fit_predict_for_split(
                train_frame=train_frame,
                test_frame=test_frame,
                feature_columns=feature_columns,
                random_state=random_state,
            )
            holdout_frame.insert(0, "fold_label", fold_label)

    metric_rows: list[dict[str, Any]] = []
    for scope, frame in (("validation", validation_frame), ("holdout", holdout_frame)):
        for spec in MODEL_SPECS:
            if spec["probability_column"] not in frame.columns:
                continue
            metric_rows.append(
                {
                    "scope": scope,
                    "model_label": spec["label"],
                    **_classification_summary(frame, spec["probability_column"]),
                }
            )

    metric_table = pd.DataFrame(metric_rows)
    return modeling_frame, validation_frame, holdout_frame, metric_table


def build_quarterly_ranking_strategy(predictions: pd.DataFrame, *, top_n: int) -> pd.DataFrame:
    if predictions.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for quarter, group in predictions.groupby("fiscal_quarter"):
        ranked = group.sort_values("ensemble_probability", ascending=False).head(top_n)
        rows.append(
            {
                "fiscal_quarter": quarter,
                "quarter_end_date": ranked["quarter_end_date"].iloc[0],
                "selected_sectors": ", ".join(ranked["sector"].tolist()),
                "selected_etfs": ", ".join(ranked["etf_symbol"].tolist()),
                "portfolio_return": float(ranked["sector_next_q_return"].mean()),
                "spy_return": float(ranked["spy_next_q_return"].iloc[0]),
                "excess_return": float(ranked["target_excess_return"].mean()),
                "avg_probability": float(ranked["ensemble_probability"].mean()),
            }
        )

    strategy = pd.DataFrame(rows).sort_values("quarter_end_date").reset_index(drop=True)
    strategy["portfolio_equity"] = (1.0 + strategy["portfolio_return"]).cumprod()
    strategy["spy_equity"] = (1.0 + strategy["spy_return"]).cumprod()
    strategy["alpha_equity"] = (1.0 + strategy["excess_return"]).cumprod()
    return strategy


def build_feature_importance_table(
    *,
    modeling_frame: pd.DataFrame,
    feature_columns: list[str],
    holdout_start: str,
    random_state: int,
) -> pd.DataFrame:
    pre_holdout = modeling_frame.loc[modeling_frame["quarter_end_date"] < pd.Timestamp(holdout_start)].copy()
    if pre_holdout.empty or pre_holdout["target"].nunique() < 2:
        return pd.DataFrame()

    x_train = pre_holdout[feature_columns].copy()
    median_fill = x_train.median(numeric_only=True)
    x_train = x_train.fillna(median_fill)
    y_train = pre_holdout["target"].astype(int)

    rows: list[dict[str, Any]] = []
    for spec in MODEL_SPECS[:-1]:
        model = clone(build_base_models(random_state=random_state)[spec["key"]])
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="l1_ratio parameter is only used when penalty is 'elasticnet'",
            )
            model.fit(x_train, y_train)
        estimator = model.named_steps["model"] if hasattr(model, "named_steps") else model
        if hasattr(estimator, "coef_"):
            importance_values = np.abs(np.ravel(estimator.coef_))
        elif hasattr(estimator, "feature_importances_"):
            importance_values = np.asarray(estimator.feature_importances_, dtype="float64")
        else:
            continue

        total = float(importance_values.sum())
        if total > 0.0:
            importance_values = importance_values / total
        for feature_name, importance in zip(feature_columns, importance_values, strict=False):
            rows.append(
                {
                    "model_label": spec["label"],
                    "feature": feature_name,
                    "importance": float(importance),
                }
            )

    table = pd.DataFrame(rows)
    if table.empty:
        return table
    ensemble = (
        table.groupby("feature", as_index=False)["importance"].mean().assign(model_label="Average Ensemble")
    )
    return pd.concat([table, ensemble], ignore_index=True).sort_values(
        ["model_label", "importance", "feature"], ascending=[True, False, True]
    )


def write_outputs(
    *,
    output_dir: Path,
    panel: pd.DataFrame,
    feature_columns: list[str],
    structure_features: pd.DataFrame,
    market_features: pd.DataFrame,
    validation_predictions: pd.DataFrame,
    holdout_predictions: pd.DataFrame,
    metric_table: pd.DataFrame,
    feature_importance: pd.DataFrame,
    validation_strategy: pd.DataFrame,
    holdout_strategy: pd.DataFrame,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output_dir / "sector_factor_panel.csv", index=False)
    structure_features.to_csv(output_dir / "sector_market_structure_quarterly.csv", index=False)
    market_features.to_csv(output_dir / "sector_market_features_quarterly.csv", index=False)
    validation_predictions.to_csv(output_dir / "sector_model_validation_predictions.csv", index=False)
    holdout_predictions.to_csv(output_dir / "sector_model_holdout_predictions.csv", index=False)
    metric_table.to_csv(output_dir / "sector_model_metrics.csv", index=False)
    feature_importance.to_csv(output_dir / "sector_feature_importance.csv", index=False)
    validation_strategy.to_csv(output_dir / "sector_top3_validation_strategy.csv", index=False)
    holdout_strategy.to_csv(output_dir / "sector_top3_holdout_strategy.csv", index=False)

    validation_ensemble = metric_table.loc[
        (metric_table["scope"] == "validation") & (metric_table["model_label"] == "Average Ensemble")
    ]
    holdout_ensemble = metric_table.loc[
        (metric_table["scope"] == "holdout") & (metric_table["model_label"] == "Average Ensemble")
    ]
    top_features = (
        feature_importance.loc[feature_importance["model_label"] == "Average Ensemble", ["feature", "importance"]]
        .head(20)
        .to_dict(orient="records")
        if not feature_importance.empty
        else []
    )
    output_names = sorted(path.name for path in output_dir.glob("*"))
    if "sector_research_summary.json" not in output_names:
        output_names.append("sector_research_summary.json")
        output_names.sort()
    summary = {
        "output_dir": str(output_dir),
        "panel_rows": int(len(panel)),
        "sector_count": int(panel["sector"].nunique()) if not panel.empty else 0,
        "quarter_count": int(panel["fiscal_quarter"].nunique()) if not panel.empty else 0,
        "feature_count": int(len(feature_columns)),
        "feature_columns": feature_columns,
        "validation_ensemble_metrics": validation_ensemble.iloc[0].dropna().to_dict() if not validation_ensemble.empty else {},
        "holdout_ensemble_metrics": holdout_ensemble.iloc[0].dropna().to_dict() if not holdout_ensemble.empty else {},
        "validation_strategy": _quarterly_strategy_summary(validation_strategy),
        "holdout_strategy": _quarterly_strategy_summary(holdout_strategy),
        "top_features": top_features,
        "outputs": output_names,
    }
    (output_dir / "sector_research_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def build_sector_fundamentals_research(
    *,
    project_root: Path | None = None,
    analysis_output_dir: Path = DEFAULT_FUNDAMENTALS_ANALYSIS_OUTPUT_DIR,
    fundamentals_data_dir: Path | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    start_quarter: str = DEFAULT_START_QUARTER,
    holdout_start: str = DEFAULT_HOLDOUT_START,
    train_years: int = DEFAULT_TRAIN_YEARS,
    validation_years: int = DEFAULT_VALIDATION_YEARS,
    top_n: int = DEFAULT_TOP_N,
    random_state: int = 42,
    refresh_fundamentals: bool = False,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    resolved_output_dir = _resolved_output_dir(root, output_dir)
    resolved_analysis_output_dir = _ensure_fundamentals_outputs(
        root=root,
        analysis_output_dir=analysis_output_dir,
        fundamentals_data_dir=fundamentals_data_dir,
        refresh=refresh_fundamentals,
    )

    sector_quarterly = _read_csv(resolved_analysis_output_dir / "sector_quarterly_surprise.csv")
    eligible_symbols = _read_csv(resolved_analysis_output_dir / "sector_analysis_eligible_symbols.csv")

    fundamentals_features = build_fundamental_lag_features(sector_quarterly)
    structure_features = build_sector_structure_features(
        root=root,
        eligible_symbols=eligible_symbols,
        start_quarter=start_quarter,
    )
    market_features = build_sector_market_features(root=root)
    panel, feature_columns = build_sector_panel(
        fundamentals_features=fundamentals_features,
        structure_features=structure_features,
        market_features=market_features,
        start_quarter=start_quarter,
    )
    (
        modeling_frame,
        validation_predictions,
        holdout_predictions,
        metric_table,
    ) = run_sector_panel_models(
        panel=panel,
        feature_columns=feature_columns,
        holdout_start=holdout_start,
        train_years=train_years,
        validation_years=validation_years,
        random_state=random_state,
    )
    feature_importance = build_feature_importance_table(
        modeling_frame=modeling_frame,
        feature_columns=feature_columns,
        holdout_start=holdout_start,
        random_state=random_state,
    )
    validation_strategy = build_quarterly_ranking_strategy(validation_predictions, top_n=top_n)
    holdout_strategy = build_quarterly_ranking_strategy(holdout_predictions, top_n=top_n)
    return write_outputs(
        output_dir=resolved_output_dir,
        panel=panel,
        feature_columns=feature_columns,
        structure_features=structure_features,
        market_features=market_features,
        validation_predictions=validation_predictions,
        holdout_predictions=holdout_predictions,
        metric_table=metric_table,
        feature_importance=feature_importance,
        validation_strategy=validation_strategy,
        holdout_strategy=holdout_strategy,
    )


def main() -> None:
    args = parse_args()
    summary = build_sector_fundamentals_research(
        project_root=args.project_root,
        analysis_output_dir=args.analysis_output_dir,
        fundamentals_data_dir=args.fundamentals_data_dir,
        output_dir=args.output_dir,
        start_quarter=args.start_quarter,
        holdout_start=args.holdout_start,
        train_years=args.train_years,
        validation_years=args.validation_years,
        top_n=args.top_n,
        random_state=args.random_state,
        refresh_fundamentals=args.refresh_fundamentals,
    )
    print(f"Wrote sector fundamentals research outputs to {summary['output_dir']}")
    print(
        "Built sector panel with "
        f"{summary['panel_rows']} rows, "
        f"{summary['sector_count']} sectors, and "
        f"{summary['feature_count']} features."
    )


if __name__ == "__main__":
    main()