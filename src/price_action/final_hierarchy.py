"""Fitted macro -> sector -> company -> trend hierarchy and sizing advisor.

The hierarchy consumes ``outputs/hierarchical_research`` and preserves the
data contract established there.  CFTC positioning is release-aligned and
backtestable.  Dealer gamma is a live-only risk overlay because the repository
does not have a historical point-in-time option-chain archive.

Run with::

    python build_final_hierarchy.py
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.ensemble import (
    ExtraTreesClassifier,
    ExtraTreesRegressor,
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .data import resolve_project_root
from .execution_costs import (
    BinanceExecutionCosts,
    load_binance_execution_costs,
    simulate_rebalanced_portfolio,
)
from .hierarchical_research import (
    BOOK_PARENT_SECTOR,
    EARNINGS_FUNDAMENTAL_FEATURES,
    INK,
    INK_AMBER,
    INK_GREEN,
    INK_MUTED,
    INK_NAVY,
    INK_RED,
    OUTPUT_DIR as CONTRACT_OUTPUT_DIR,
    PAPER,
    QUALITY_DIR,
    SECTOR_PRICE_FEATURES,
    _apply_membership_flags,
    _company_price_features,
    _figure_b64,
    _html_table,
    _img,
    _load_sector_etf_daily,
    _vintage_figure,
)
from .market_structure import GEX_INSTRUCTIONS, gamma_exposure
from .quality_engine import SECTOR_SPECIFICATION, load_close
from .sector_dalio_regime_model import build_live_etf_overlay_panel

OUTPUT_DIR = Path("outputs") / "final_hierarchy"
BINANCE_EXECUTION_CONFIG = Path("config") / "binance_execution.json"
COT_CACHE = Path("cache") / "market_structure" / "cot_tff_es.csv"
CROSS_EVENTS = Path("outputs") / "sector_dalio_regime_model" / "daily_50_200_cross_events.csv"
HOLDOUT_START = pd.Timestamp("2025-01-01")
RANDOM_STATE = 42
LONG_ALPHA_HURDLE = 0.010
SHORT_ALPHA_HURDLE = 0.015

REGRESSION_MODEL_NAMES = ("ridge", "extra_trees", "hist_gradient")
CLASSIFICATION_MODEL_NAMES = ("logit", "extra_trees", "hist_gradient")
FAVORABLE_REGIMES = {
    "Goldilocks (growth up, inflation down)",
    "Reflation (growth up, inflation up)",
}
ADVERSE_REGIMES = {
    "Deflation (growth down, inflation down)",
    "Stagflation (growth down, inflation up)",
}
COMPANY_FUNDAMENTAL_FEATURES = {
    "capital_ratio_z", "capex_coverage_z", "earnings_stability_z", "fcf_margin_z",
    "gm_trend_z", "gross_margin_z", "low_leverage_z", "margin_steadiness_z",
    "net_cash_ratio_z", "ni_growth_z", "ni_margin_z", "ocf_growth_z", "ocf_margin_z",
    "ocf_stability_z", "quality_z", "rev_growth_z", "revenue_steadiness_z", "roe_z",
}

MODEL_CONFIG = {
    "macro": {
        "task": "five-class next-three-month Dalio quadrant",
        "models": list(CLASSIFICATION_MODEL_NAMES),
        "min_feature_coverage": 0.55,
        "min_train_rows": 84,
        "label_horizon_months": 3,
    },
    "sector": {
        "task": "next-six-month excess return versus broad sector basket",
        "models": list(REGRESSION_MODEL_NAMES),
        "min_feature_coverage": 0.60,
        "min_train_rows": 700,
        "label_horizon_months": 6,
    },
    "company": {
        "task": "next-126-trading-day stock return minus parent-sector ETF",
        "models": list(REGRESSION_MODEL_NAMES),
        "min_feature_coverage": 0.05,
        "min_train_rows": 5_000,
        "label_horizon_months": 6,
        "training_target_winsorization": [0.005, 0.995],
        "weighting": "equal book-month mass",
    },
    "trend": {
        "task": "50/200 cross survives 63 trading days and reaches 5% favorable excursion",
        "models": list(CLASSIFICATION_MODEL_NAMES),
        "min_feature_coverage": 0.50,
        "min_train_rows": 90,
        "label_horizon_months": 3,
    },
}


@dataclass
class RegressionResult:
    predictions: pd.DataFrame
    live: pd.DataFrame
    metrics: pd.DataFrame
    importance: pd.DataFrame
    feature_columns: list[str]
    validation_reliability: float
    trained_through: pd.Timestamp


@dataclass
class ClassificationResult:
    predictions: pd.DataFrame
    live: pd.DataFrame
    metrics: pd.DataFrame
    importance: pd.DataFrame
    feature_columns: list[str]
    classes: list[str]
    validation_reliability: float
    trained_through: pd.Timestamp


@dataclass
class FinalHierarchyResult:
    macro: ClassificationResult
    sector: RegressionResult
    company: RegressionResult
    trend: ClassificationResult
    sizing: pd.DataFrame
    positioning_snapshot: dict[str, Any]
    governance: dict[str, Any]
    audit: pd.DataFrame
    portfolio_signals: pd.DataFrame
    portfolio_targets: pd.DataFrame
    portfolio_periods: pd.DataFrame
    portfolio_summary: dict[str, Any]
    output_dir: Path


def _write_progress(
    output_dir: Path,
    *,
    step: int,
    total: int,
    stage: str,
    message: str,
    status: str = "running",
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "step": step,
        "total_steps": total,
        "progress_pct": round(step / total * 100.0, 1),
        "stage": stage,
        "message": message,
        "updated_at_utc": datetime.now(UTC).isoformat(),
    }
    (output_dir / "progress.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[{step}/{total}] {message}", flush=True)


def load_positioning(root: Path) -> pd.DataFrame:
    """Build causal CFTC features on their first usable date."""
    path = root / COT_CACHE
    if not path.exists():
        raise FileNotFoundError(f"CFTC cache is missing: {path}. Run build_market_structure.py first.")
    raw = pd.read_csv(path, parse_dates=["report_date", "usable_date"]).sort_values("usable_date")
    raw = raw.drop_duplicates("usable_date", keep="last").set_index("usable_date")
    out = pd.DataFrame(index=raw.index)
    for column in ["lev_funds_net_pct_oi", "asset_mgr_net_pct_oi", "dealer_net_pct_oi"]:
        values = pd.to_numeric(raw[column], errors="coerce")
        out[f"cot_{column}"] = values
        mean = values.rolling(156, min_periods=52).mean()
        std = values.rolling(156, min_periods=52).std()
        out[f"cot_{column}_z"] = ((values - mean) / std.replace(0.0, np.nan)).clip(-4.0, 4.0)
        out[f"cot_{column}_change_13w"] = values - values.shift(13)
    oi = pd.to_numeric(raw["open_interest"], errors="coerce")
    out["cot_open_interest_yoy"] = oi / oi.shift(52) - 1.0
    out["cot_crowding_abs_z"] = out[
        ["cot_lev_funds_net_pct_oi_z", "cot_asset_mgr_net_pct_oi_z", "cot_dealer_net_pct_oi_z"]
    ].abs().max(axis=1)
    out["cot_usable_date"] = out.index
    return out.replace([np.inf, -np.inf], np.nan)


def join_positioning(frame: pd.DataFrame, positioning: pd.DataFrame, date_column: str = "date") -> pd.DataFrame:
    left = frame.copy()
    left[date_column] = pd.to_datetime(left[date_column]).astype("datetime64[ns]")
    left["_row_order"] = np.arange(len(left))
    right = positioning.reset_index(drop=True).sort_values("cot_usable_date")
    right["cot_usable_date"] = pd.to_datetime(right["cot_usable_date"]).astype("datetime64[ns]")
    merged = pd.merge_asof(
        left.sort_values(date_column),
        right,
        left_on=date_column,
        right_on="cot_usable_date",
        direction="backward",
    )
    merged["cot_age_days"] = (merged[date_column] - merged["cot_usable_date"]).dt.days
    return merged.sort_values("_row_order").drop(columns="_row_order").reset_index(drop=True)


def _positioning_feature_columns(positioning: pd.DataFrame) -> list[str]:
    return [column for column in positioning.columns if column != "cot_usable_date"]


def _load_contract(root: Path) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    base = root / CONTRACT_OUTPUT_DIR
    required = {
        "macro": base / "macro_monthly_panel.csv",
        "sector": base / "sector_monthly_panel.csv",
        "company": base / "company_monthly_panel.csv",
    }
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Hierarchical contract is incomplete: " + ", ".join(missing))
    frames = {layer: pd.read_csv(path, low_memory=False) for layer, path in required.items()}
    for frame in frames.values():
        for column in [c for c in frame.columns if c == "date" or c.endswith("_date") or "date_" in c]:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    registry = pd.read_csv(base / "feature_registry.csv")
    splits = pd.read_csv(base / "walk_forward_splits.csv", parse_dates=[
        "train_signal_start", "train_signal_end", "max_train_target_end", "test_start", "test_end"
    ])
    return frames, registry, splits


def _registered_features(registry: pd.DataFrame, layer: str) -> list[str]:
    return registry.loc[
        registry["layer"].eq(layer) & registry["role"].eq("feature"), "column"
    ].astype(str).tolist()


def _prepare_design(
    panel: pd.DataFrame,
    live: pd.DataFrame,
    *,
    feature_columns: list[str],
    categorical: list[str],
    model_mask: pd.Series,
    min_coverage: float,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], list[str]]:
    combined = pd.concat([panel, live], ignore_index=True, sort=False)
    raw_features = [column for column in feature_columns if column in combined.columns]
    categorical = [column for column in categorical if column in raw_features]
    numeric = [column for column in raw_features if column not in categorical]

    numeric_frame = combined[numeric].apply(pd.to_numeric, errors="coerce")
    category_frame = pd.get_dummies(
        combined[categorical].fillna("Missing").astype(str),
        prefix=categorical,
        dtype=float,
    ) if categorical else pd.DataFrame(index=combined.index)
    design = pd.concat([numeric_frame, category_frame], axis=1).replace([np.inf, -np.inf], np.nan)
    # Return the complete encoded design.  Coverage and variance selection is
    # performed inside each walk-forward training fold so the holdout cannot
    # influence even unsupervised feature eligibility.
    _ = model_mask, min_coverage
    columns = design.columns.tolist()
    return design.iloc[: len(panel)][columns], design.iloc[len(panel) :][columns].reset_index(drop=True), columns, raw_features


def _select_design_columns(
    design: pd.DataFrame,
    train_mask: pd.Series,
    min_coverage: float,
) -> list[str]:
    training = design.loc[train_mask]
    coverage = training.notna().mean()
    variance = training.nunique(dropna=True)
    selected = coverage[(coverage >= min_coverage) & (variance > 1)].index.tolist()
    if not selected:
        raise ValueError("No predictive features survived fold-local coverage and variance filters.")
    return selected


def _regression_models(profile: str) -> dict[str, Pipeline]:
    leaf = {"sector": 12, "company": 45}.get(profile, 20)
    depth = {"sector": 7, "company": 10}.get(profile, 8)
    return {
        "ridge": Pipeline([
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scaler", StandardScaler()),
            ("model", Ridge(alpha=20.0)),
        ]),
        "extra_trees": Pipeline([
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("model", ExtraTreesRegressor(
                n_estimators=240,
                max_depth=depth,
                min_samples_leaf=leaf,
                max_features=0.70,
                random_state=RANDOM_STATE,
                n_jobs=-1,
            )),
        ]),
        "hist_gradient": Pipeline([
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("model", HistGradientBoostingRegressor(
                learning_rate=0.04,
                max_iter=180,
                max_leaf_nodes=15,
                min_samples_leaf=leaf,
                l2_regularization=3.0,
                random_state=RANDOM_STATE,
            )),
        ]),
    }


def _classification_models(profile: str) -> dict[str, Pipeline]:
    leaf = 8 if profile == "trend" else 10
    return {
        "logit": Pipeline([
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scaler", StandardScaler()),
            ("model", LogisticRegression(C=0.25, max_iter=2_000, random_state=RANDOM_STATE)),
        ]),
        "extra_trees": Pipeline([
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("model", ExtraTreesClassifier(
                n_estimators=240,
                max_depth=7,
                min_samples_leaf=leaf,
                max_features=0.70,
                random_state=RANDOM_STATE,
                n_jobs=-1,
            )),
        ]),
        "hist_gradient": Pipeline([
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("model", HistGradientBoostingClassifier(
                learning_rate=0.04,
                max_iter=180,
                max_leaf_nodes=15,
                min_samples_leaf=leaf,
                l2_regularization=3.0,
                random_state=RANDOM_STATE,
            )),
        ]),
    }


def _fit_regression_stack(
    x: pd.DataFrame,
    y: pd.Series,
    *,
    profile: str,
    sample_weight: pd.Series | None = None,
) -> tuple[dict[str, Pipeline], tuple[float, float]]:
    lower, upper = np.nanquantile(y, [0.005, 0.995])
    clipped = y.clip(lower, upper)
    fitted: dict[str, Pipeline] = {}
    for name, model in _regression_models(profile).items():
        kwargs = {"model__sample_weight": sample_weight.to_numpy()} if sample_weight is not None else {}
        model.fit(x, clipped, **kwargs)
        fitted[name] = model
    return fitted, (float(lower), float(upper))


def _predict_regression_stack(
    models: dict[str, Pipeline],
    x: pd.DataFrame,
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    out = pd.DataFrame(index=x.index)
    for name in REGRESSION_MODEL_NAMES:
        out[f"pred_{name}"] = models[name].predict(x)
    columns = [f"pred_{name}" for name in REGRESSION_MODEL_NAMES]
    weights = weights or {name: 1.0 / len(REGRESSION_MODEL_NAMES) for name in REGRESSION_MODEL_NAMES}
    total = sum(max(float(weights.get(name, 0.0)), 0.0) for name in REGRESSION_MODEL_NAMES)
    if total <= 0:
        weights = {name: 1.0 / len(REGRESSION_MODEL_NAMES) for name in REGRESSION_MODEL_NAMES}
    else:
        weights = {name: max(float(weights.get(name, 0.0)), 0.0) / total for name in REGRESSION_MODEL_NAMES}
    out["predicted_alpha"] = sum(out[f"pred_{name}"] * weights[name] for name in REGRESSION_MODEL_NAMES)
    out["model_dispersion"] = np.sqrt(sum(
        weights[name] * (out[f"pred_{name}"] - out["predicted_alpha"]) ** 2
        for name in REGRESSION_MODEL_NAMES
    ))
    for name in REGRESSION_MODEL_NAMES:
        out[f"ensemble_weight_{name}"] = weights[name]
    return out


def _regression_model_weights(
    predictions: pd.DataFrame,
    group_columns: list[str],
    *,
    min_dates: int = 24,
) -> dict[str, float]:
    equal = {name: 1.0 / len(REGRESSION_MODEL_NAMES) for name in REGRESSION_MODEL_NAMES}
    if predictions.empty or predictions["date"].nunique() < min_dates:
        return equal
    scores: dict[str, float] = {}
    for name in REGRESSION_MODEL_NAMES:
        column = f"pred_{name}"
        values = []
        for _, group in predictions.groupby(group_columns, sort=True):
            if len(group) < 4 or group[column].nunique() < 2:
                continue
            ic = group[column].corr(group["target"], method="spearman")
            if pd.notna(ic):
                values.append(float(ic))
        scores[name] = max(float(np.mean(values)), 0.0) if values else 0.0
    total = sum(scores.values())
    return {name: scores[name] / total for name in REGRESSION_MODEL_NAMES} if total > 0 else equal


def _class_weights(y: pd.Series) -> pd.Series:
    counts = y.value_counts()
    weights = y.map({label: len(y) / (len(counts) * count) for label, count in counts.items()})
    return weights.astype(float)


def _fit_classification_stack(
    x: pd.DataFrame,
    y: pd.Series,
    *,
    profile: str,
) -> dict[str, Pipeline]:
    weights = _class_weights(y)
    fitted: dict[str, Pipeline] = {}
    for name, model in _classification_models(profile).items():
        model.fit(x, y, model__sample_weight=weights.to_numpy())
        fitted[name] = model
    return fitted


def _predict_classification_stack(
    models: dict[str, Pipeline],
    x: pd.DataFrame,
    classes: list[str],
) -> pd.DataFrame:
    probability_sets: list[pd.DataFrame] = []
    out = pd.DataFrame(index=x.index)
    for name in CLASSIFICATION_MODEL_NAMES:
        model = models[name]
        fitted_classes = [str(value) for value in model.named_steps["model"].classes_]
        probability = pd.DataFrame(model.predict_proba(x), index=x.index, columns=fitted_classes)
        probability = probability.reindex(columns=classes, fill_value=0.0)
        probability_sets.append(probability)
        out[f"pred_{name}"] = probability.idxmax(axis=1)
    ensemble = sum(probability_sets) / len(probability_sets)
    for label in classes:
        out[f"prob::{label}"] = ensemble[label]
    out["predicted_class"] = ensemble.idxmax(axis=1)
    out["ensemble_confidence"] = ensemble.max(axis=1)
    model_votes = pd.concat([out[f"pred_{name}"] for name in CLASSIFICATION_MODEL_NAMES], axis=1)
    out["model_agreement"] = model_votes.apply(lambda row: row.value_counts(normalize=True).max(), axis=1)
    return out


def _feature_importance(models: dict[str, Pipeline], feature_columns: list[str], layer: str) -> pd.DataFrame:
    model = models["extra_trees"].named_steps["model"]
    values = getattr(model, "feature_importances_", np.zeros(len(feature_columns)))
    if len(values) != len(feature_columns):
        return pd.DataFrame(columns=["layer", "feature", "importance"])
    return pd.DataFrame({"layer": layer, "feature": feature_columns, "importance": values}).sort_values(
        "importance", ascending=False
    ).reset_index(drop=True)


def _regression_metrics(frame: pd.DataFrame, *, scope: str, group_columns: list[str], horizon: int) -> dict[str, Any]:
    data = frame.dropna(subset=["target", "predicted_alpha"]).copy()
    if data.empty:
        return {"scope": scope, "observations": 0}
    monthly_ic: list[tuple[pd.Timestamp, float]] = []
    spreads: list[tuple[pd.Timestamp, float]] = []
    for keys, group in data.groupby(group_columns, sort=True):
        if len(group) < 4 or group["predicted_alpha"].nunique() < 2:
            continue
        date = pd.Timestamp(keys[0] if isinstance(keys, tuple) else keys)
        ic = group["predicted_alpha"].corr(group["target"], method="spearman")
        if pd.notna(ic):
            monthly_ic.append((date, float(ic)))
        count = max(1, min(3, len(group) // 3))
        ranked = group.sort_values("predicted_alpha")
        spreads.append((date, float(ranked.tail(count)["target"].mean() - ranked.head(count)["target"].mean())))
    ic_series = pd.Series([value for _, value in monthly_ic], index=[date for date, _ in monthly_ic], dtype=float)
    spread_series = pd.Series([value for _, value in spreads], index=[date for date, _ in spreads], dtype=float)
    by_date_ic = ic_series.groupby(level=0).mean().sort_index() if len(ic_series) else pd.Series(dtype=float)
    by_date_spread = spread_series.groupby(level=0).mean().sort_index() if len(spread_series) else pd.Series(dtype=float)
    nonoverlap_ic = by_date_ic.iloc[::horizon]
    nonoverlap_spread = by_date_spread.iloc[::horizon]

    def tstat(series: pd.Series) -> float:
        return float(series.mean() / (series.std() / np.sqrt(len(series)))) if len(series) > 2 and series.std() > 0 else np.nan

    return {
        "scope": scope,
        "observations": len(data),
        "rmse": math.sqrt(mean_squared_error(data["target"], data["predicted_alpha"])),
        "mae": mean_absolute_error(data["target"], data["predicted_alpha"]),
        "r2": r2_score(data["target"], data["predicted_alpha"]),
        "directional_accuracy": float((np.sign(data["target"]) == np.sign(data["predicted_alpha"])).mean()),
        "avg_cross_sectional_rank_ic": float(by_date_ic.mean()) if len(by_date_ic) else np.nan,
        "rank_ic_tstat_nonoverlap": tstat(nonoverlap_ic),
        "avg_top_minus_bottom": float(by_date_spread.mean()) if len(by_date_spread) else np.nan,
        "spread_tstat_nonoverlap": tstat(nonoverlap_spread),
        "nonoverlap_periods": len(nonoverlap_spread),
    }


def _classification_metrics(
    frame: pd.DataFrame,
    *,
    scope: str,
    classes: list[str],
    positive_class: str | None = None,
) -> dict[str, Any]:
    data = frame.dropna(subset=["target", "predicted_class"]).copy()
    if data.empty:
        return {"scope": scope, "observations": 0}
    probability = data[[f"prob::{label}" for label in classes]].to_numpy()
    encoded = pd.Categorical(data["target"], categories=classes).codes
    one_hot = np.eye(len(classes))[encoded]
    class_prior = data["target"].value_counts(normalize=True).reindex(classes, fill_value=0.0).to_numpy()
    baseline_probability = np.tile(class_prior, (len(data), 1))
    model_log_loss = log_loss(data["target"], probability, labels=classes)
    baseline_log_loss = log_loss(data["target"], baseline_probability, labels=classes)
    model_brier = float(np.mean(np.sum((probability - one_hot) ** 2, axis=1)))
    baseline_brier = float(np.mean(np.sum((baseline_probability - one_hot) ** 2, axis=1)))
    row = {
        "scope": scope,
        "observations": len(data),
        "accuracy": accuracy_score(data["target"], data["predicted_class"]),
        "balanced_accuracy": float(np.mean([
            (data.loc[data["target"].eq(label), "predicted_class"] == label).mean()
            for label in sorted(data["target"].unique())
        ])),
        "log_loss": model_log_loss,
        "baseline_log_loss": baseline_log_loss,
        "log_loss_skill": 1.0 - model_log_loss / baseline_log_loss if baseline_log_loss > 0.0 else np.nan,
        "multiclass_brier": model_brier,
        "baseline_multiclass_brier": baseline_brier,
        "brier_skill": 1.0 - model_brier / baseline_brier if baseline_brier > 0.0 else np.nan,
        "mean_confidence": float(data["ensemble_confidence"].mean()),
        "model_agreement": float(data["model_agreement"].mean()),
    }
    if positive_class is not None and data["target"].nunique() == 2:
        actual = data["target"].eq(positive_class).astype(int)
        prob = data[f"prob::{positive_class}"]
        row["roc_auc"] = roc_auc_score(actual, prob)
        row["binary_brier"] = brier_score_loss(actual, prob)
    return row


def _regression_reliability(metrics: pd.DataFrame) -> float:
    """Score pre-holdout ranking and portfolio-spread evidence conservatively."""
    row = metrics.loc[metrics["scope"].eq("validation")]
    if row.empty:
        return 0.0
    ic = float(row.iloc[0].get("avg_cross_sectional_rank_ic", np.nan))
    ic_tstat = float(row.iloc[0].get("rank_ic_tstat_nonoverlap", np.nan))
    spread = float(row.iloc[0].get("avg_top_minus_bottom", np.nan))
    spread_tstat = float(row.iloc[0].get("spread_tstat_nonoverlap", np.nan))

    def positive_evidence(value: float, tstat: float, scale: float) -> float:
        if not np.isfinite(value) or not np.isfinite(tstat) or value <= 0.0 or tstat <= 0.0:
            return 0.0
        magnitude = np.clip(value / scale, 0.0, 1.0)
        significance = np.clip(tstat / 2.0, 0.0, 1.0)
        return float(magnitude * significance)

    rank_evidence = positive_evidence(ic, ic_tstat, 0.10)
    spread_evidence = positive_evidence(spread, spread_tstat, 0.05)
    return float((rank_evidence + spread_evidence) / 2.0)


def _classification_reliability(metrics: pd.DataFrame, classes: int) -> float:
    row = metrics.loc[metrics["scope"].eq("validation")]
    if row.empty:
        return 0.0
    balanced = float(row.iloc[0].get("balanced_accuracy", np.nan))
    chance = 1.0 / classes
    if not np.isfinite(balanced) or balanced <= chance:
        return 0.0
    discrimination = float(np.clip((balanced - chance) / (1.0 - chance), 0.0, 1.0))
    log_skill = float(row.iloc[0].get("log_loss_skill", np.nan))
    brier_skill = float(row.iloc[0].get("brier_skill", np.nan))
    if not np.isfinite(log_skill) or not np.isfinite(brier_skill):
        return 0.0
    probability_skill = float(np.clip(min(log_skill, brier_skill), 0.0, 1.0))
    return float(math.sqrt(discrimination * probability_skill))


def run_regression_layer(
    panel: pd.DataFrame,
    live: pd.DataFrame,
    *,
    layer: str,
    target_column: str,
    target_end_column: str,
    feature_columns: list[str],
    categorical: list[str],
    splits: pd.DataFrame,
    meta_columns: list[str],
    group_columns: list[str],
    sample_weight_fn: Callable[[pd.DataFrame], pd.Series] | None = None,
    asof_date: pd.Timestamp | None = None,
) -> RegressionResult:
    config = MODEL_CONFIG[layer]
    asof_date = pd.Timestamp(asof_date) if asof_date is not None else pd.Timestamp(live["date"].max())
    eligible = (
        panel[target_column].notna()
        & panel[target_end_column].notna()
        & panel[target_end_column].le(asof_date)
    )
    x_panel, x_live, _candidate_columns, _raw = _prepare_design(
        panel,
        live,
        feature_columns=feature_columns,
        categorical=categorical,
        model_mask=eligible,
        min_coverage=float(config["min_feature_coverage"]),
    )
    predictions: list[pd.DataFrame] = []
    layer_splits = splits.loc[splits["layer"].eq(layer)]
    for split in layer_splits.itertuples(index=False):
        train = eligible & (panel[target_end_column] < split.test_start)
        test = eligible & panel["date"].between(split.test_start, split.test_end)
        if train.sum() < int(config["min_train_rows"]) or not test.any():
            continue
        fold_features = _select_design_columns(
            x_panel,
            train,
            float(config["min_feature_coverage"]),
        )
        weights = sample_weight_fn(panel.loc[train]) if sample_weight_fn else None
        models, bounds = _fit_regression_stack(
            x_panel.loc[train, fold_features], panel.loc[train, target_column], profile=layer, sample_weight=weights
        )
        pred = panel.loc[test, meta_columns].copy()
        pred["target"] = panel.loc[test, target_column]
        pred["target_end_date"] = panel.loc[test, target_end_column]
        pred["fold"] = split.fold
        pred["train_rows"] = int(train.sum())
        pred["target_clip_lower"] = bounds[0]
        pred["target_clip_upper"] = bounds[1]
        pred["selected_feature_count"] = len(fold_features)
        prior = pd.concat(predictions, ignore_index=True) if predictions else pd.DataFrame()
        causal_weights = _regression_model_weights(prior, group_columns)
        raw_prediction = _predict_regression_stack(models, x_panel.loc[test, fold_features], causal_weights)
        pred = pred.join(raw_prediction)
        target_std = float(panel.loc[train, target_column].std())
        pred["agreement_confidence"] = (
            1.0 / (1.0 + pred["model_dispersion"] / max(target_std, 1e-9))
        ).clip(0.0, 1.0)
        predictions.append(pred)
    prediction_frame = pd.concat(predictions, ignore_index=True) if predictions else pd.DataFrame()
    metric_rows = []
    for scope, mask in {
        "validation": ~prediction_frame.get("fold", pd.Series(dtype=str)).eq("holdout"),
        "holdout": prediction_frame.get("fold", pd.Series(dtype=str)).eq("holdout"),
    }.items():
        metric_rows.append(_regression_metrics(
            prediction_frame.loc[mask] if len(prediction_frame) else prediction_frame,
            scope=scope,
            group_columns=group_columns,
            horizon=int(config["label_horizon_months"]),
        ))
    if layer == "company" and "strict_pit_eligible" in prediction_frame:
        for scope, fold_mask in {
            "validation_strict_pit": ~prediction_frame["fold"].eq("holdout"),
            "holdout_strict_pit": prediction_frame["fold"].eq("holdout"),
        }.items():
            metric_rows.append(_regression_metrics(
                prediction_frame.loc[fold_mask & prediction_frame["strict_pit_eligible"].fillna(False)],
                scope=scope,
                group_columns=group_columns,
                horizon=int(config["label_horizon_months"]),
            ))
    metrics = pd.DataFrame(metric_rows)

    final_train = eligible
    selected = _select_design_columns(
        x_panel,
        final_train,
        float(config["min_feature_coverage"]),
    )
    final_weights = sample_weight_fn(panel.loc[final_train]) if sample_weight_fn else None
    final_models, _bounds = _fit_regression_stack(
        x_panel.loc[final_train, selected], panel.loc[final_train, target_column], profile=layer, sample_weight=final_weights
    )
    live_output = live[meta_columns].copy().reset_index(drop=True)
    validation_predictions = prediction_frame.loc[~prediction_frame["fold"].eq("holdout")]
    live_weights = _regression_model_weights(validation_predictions, group_columns)
    live_output = live_output.join(_predict_regression_stack(final_models, x_live[selected], live_weights))
    target_std = float(panel.loc[final_train, target_column].std())
    live_output["agreement_confidence"] = (
        1.0 / (1.0 + live_output["model_dispersion"] / max(target_std, 1e-9))
    ).clip(0.0, 1.0)
    reliability = _regression_reliability(metrics)
    if layer == "company":
        strict = metrics.loc[metrics["scope"].eq("validation_strict_pit")].copy()
        if not strict.empty and int(strict.iloc[0].get("observations", 0)) >= 500:
            strict.loc[:, "scope"] = "validation"
            strict_reliability = _regression_reliability(strict)
            reliability = float(math.sqrt(reliability * strict_reliability))
    live_output["validation_reliability"] = reliability
    live_output["validated_alpha"] = live_output["predicted_alpha"] * reliability
    return RegressionResult(
        predictions=prediction_frame,
        live=live_output,
        metrics=metrics,
        importance=_feature_importance(final_models, selected, layer),
        feature_columns=selected,
        validation_reliability=reliability,
        trained_through=pd.Timestamp(panel.loc[final_train, target_end_column].max()),
    )


def run_classification_layer(
    panel: pd.DataFrame,
    live: pd.DataFrame,
    *,
    layer: str,
    target_column: str,
    target_end_column: str,
    feature_columns: list[str],
    categorical: list[str],
    splits: pd.DataFrame,
    meta_columns: list[str],
    positive_class: str | None = None,
    asof_date: pd.Timestamp | None = None,
) -> ClassificationResult:
    config = MODEL_CONFIG[layer]
    asof_date = pd.Timestamp(asof_date) if asof_date is not None else pd.Timestamp(live["date"].max())
    eligible = (
        panel[target_column].notna()
        & panel[target_end_column].notna()
        & panel[target_end_column].le(asof_date)
    )
    panel = panel.copy()
    live = live.copy()
    panel[target_column] = panel[target_column].astype(str)
    classes = sorted(panel.loc[eligible, target_column].unique().tolist())
    x_panel, x_live, _candidate_columns, _raw = _prepare_design(
        panel,
        live,
        feature_columns=feature_columns,
        categorical=categorical,
        model_mask=eligible,
        min_coverage=float(config["min_feature_coverage"]),
    )
    predictions: list[pd.DataFrame] = []
    layer_splits = splits.loc[splits["layer"].eq(layer)]
    for split in layer_splits.itertuples(index=False):
        train = eligible & (panel[target_end_column] < split.test_start)
        test = eligible & panel["date"].between(split.test_start, split.test_end)
        if train.sum() < int(config["min_train_rows"]) or not test.any() or panel.loc[train, target_column].nunique() < 2:
            continue
        fold_features = _select_design_columns(
            x_panel,
            train,
            float(config["min_feature_coverage"]),
        )
        models = _fit_classification_stack(
            x_panel.loc[train, fold_features], panel.loc[train, target_column], profile=layer
        )
        pred = panel.loc[test, meta_columns].copy()
        pred["target"] = panel.loc[test, target_column]
        pred["target_end_date"] = panel.loc[test, target_end_column]
        pred["fold"] = split.fold
        pred["train_rows"] = int(train.sum())
        pred["selected_feature_count"] = len(fold_features)
        pred = pred.join(_predict_classification_stack(models, x_panel.loc[test, fold_features], classes))
        predictions.append(pred)
    prediction_frame = pd.concat(predictions, ignore_index=True) if predictions else pd.DataFrame()
    metric_rows = []
    for scope, mask in {
        "validation": ~prediction_frame.get("fold", pd.Series(dtype=str)).eq("holdout"),
        "holdout": prediction_frame.get("fold", pd.Series(dtype=str)).eq("holdout"),
    }.items():
        metric_rows.append(_classification_metrics(
            prediction_frame.loc[mask] if len(prediction_frame) else prediction_frame,
            scope=scope,
            classes=classes,
            positive_class=positive_class,
        ))
    metrics = pd.DataFrame(metric_rows)

    selected = _select_design_columns(
        x_panel,
        eligible,
        float(config["min_feature_coverage"]),
    )
    final_models = _fit_classification_stack(
        x_panel.loc[eligible, selected], panel.loc[eligible, target_column], profile=layer
    )
    live_output = live[meta_columns].copy().reset_index(drop=True)
    live_output = live_output.join(_predict_classification_stack(final_models, x_live[selected], classes))
    reliability = _classification_reliability(metrics, len(classes))
    live_output["validation_reliability"] = reliability
    class_prior = panel.loc[eligible, target_column].value_counts(normalize=True).reindex(classes, fill_value=0.0)
    for label in classes:
        live_output[f"validated_prob::{label}"] = (
            float(class_prior[label])
            + reliability * (live_output[f"prob::{label}"] - float(class_prior[label]))
        )
    return ClassificationResult(
        predictions=prediction_frame,
        live=live_output,
        metrics=metrics,
        importance=_feature_importance(final_models, selected, layer),
        feature_columns=selected,
        classes=classes,
        validation_reliability=reliability,
        trained_through=pd.Timestamp(panel.loc[eligible, target_end_column].max()),
    )


def _company_weights(frame: pd.DataFrame) -> pd.Series:
    counts = frame.groupby(["date", "book"])["ticker"].transform("count").replace(0, np.nan)
    weights = 1.0 / counts
    return (weights / weights.mean()).fillna(1.0)


def build_live_frames(
    root: Path,
    positioning: pd.DataFrame,
    macro_columns: list[str],
    sector_columns: list[str],
    company_columns: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    sector_live, _bundle, latest_trade_date = build_live_etf_overlay_panel(root, fast=3, slow=10)
    if sector_live.empty or not latest_trade_date:
        raise ValueError("Current sector ETF overlay is unavailable.")
    asof = pd.Timestamp(latest_trade_date).normalize()
    latest_month_row = sector_live.loc[sector_live["date"].eq(sector_live["date"].max())].copy()
    latest_month_row["date"] = asof
    latest_month_row["signal_date"] = asof
    latest_month_row["sector_etf"] = latest_month_row["sector"].map(
        {value: key for key, value in BOOK_PARENT_SECTOR.items() if key != "SEMIS"}
    )
    latest_month_row = join_positioning(latest_month_row, positioning)
    for column in sector_columns:
        if column not in latest_month_row:
            latest_month_row[column] = np.nan

    macro_live = latest_month_row.drop_duplicates("date").copy()
    for column in macro_columns:
        if column not in macro_live:
            macro_live[column] = np.nan
    latest_position = positioning.loc[positioning.index <= asof].tail(1)
    if not latest_position.empty:
        for column in _positioning_feature_columns(positioning):
            macro_live[column] = latest_position.iloc[0][column]

    quality_rows: list[pd.DataFrame] = []
    for book in SECTOR_SPECIFICATION:
        path = root / QUALITY_DIR / f"{book}_scorecard.csv"
        score = pd.read_csv(path)
        ticker_column = score.columns[0]
        score = score.rename(columns={ticker_column: "ticker"})
        score["book"] = book
        score["book_specification"] = SECTOR_SPECIFICATION[book]
        score["parent_sector"] = BOOK_PARENT_SECTOR[book]
        quality_rows.append(score)
    quality = pd.concat(quality_rows, ignore_index=True, sort=False)
    quality["date"] = asof
    quality["signal_date"] = asof

    history_grid = pd.date_range("2000-01-31", asof.to_period("M").to_timestamp("M") - pd.offsets.MonthEnd(1), freq="ME")
    feature_grid = history_grid.append(pd.DatetimeIndex([asof])).unique().sort_values()
    etf_prices = {
        sector: _load_sector_etf_daily(root, sector) for sector in sorted(set(BOOK_PARENT_SECTOR.values()))
    }
    stock_prices = {ticker: load_close(root, ticker) for ticker in sorted(quality["ticker"].unique())}
    price_rows: list[pd.DataFrame] = []
    for ticker, parent_sector in quality[["ticker", "parent_sector"]].drop_duplicates().itertuples(index=False):
        features = _company_price_features(
            stock=stock_prices[ticker], parent=etf_prices[parent_sector], dates=feature_grid
        ).tail(1).reset_index()
        features["ticker"] = ticker
        features["parent_sector"] = parent_sector
        price_rows.append(features)
    company_live = quality.merge(
        pd.concat(price_rows, ignore_index=True),
        on=["date", "ticker", "parent_sector"],
        how="left",
        validate="many_to_one",
    )
    company_live = _apply_membership_flags(root, company_live)

    parent_columns = [
        column for column in [*SECTOR_PRICE_FEATURES, *EARNINGS_FUNDAMENTAL_FEATURES] if column in latest_month_row
    ]
    parent = latest_month_row[["sector", *parent_columns]].rename(
        columns={"sector": "parent_sector", **{column: f"parent_{column}" for column in parent_columns}}
    )
    company_live = company_live.merge(parent, on="parent_sector", how="left", validate="many_to_one")
    macro_merge_columns = [
        column
        for column in macro_columns
        if column in macro_live
        and column not in {"date", "signal_date"}
        and not column.startswith("cot_")
    ]
    macro_values = macro_live.iloc[0]
    for column in macro_merge_columns:
        target = "macro_dalio_quadrant" if column == "dalio_quadrant" else column
        company_live[target] = macro_values[column]
    company_live = join_positioning(company_live, positioning)
    company_live["research_eligible"] = company_live.get("eligible", True)
    company_live["strict_pit_eligible"] = company_live["pit_member"].fillna(False)
    for column in company_columns:
        if column not in company_live:
            company_live[column] = np.nan
    return macro_live, latest_month_row, company_live, asof


def build_trend_panel(root: Path, positioning: pd.DataFrame) -> pd.DataFrame:
    path = root / CROSS_EVENTS
    events = pd.read_csv(path, low_memory=False)
    events["date"] = pd.to_datetime(events["date"])
    events["whipsaw"] = events["whipsaw"].astype("boolean")
    events["whipsaw_censored"] = events["whipsaw_censored"].astype("boolean")
    events["target_end_date_3m"] = events["date"] + pd.offsets.MonthEnd(3)
    usable = ~events["whipsaw_censored"].fillna(True)
    survived = (
        (pd.to_numeric(events["duration_trading_days"], errors="coerce") >= 63)
        & (pd.to_numeric(events["max_favorable"], errors="coerce") >= 0.05)
        & ~events["whipsaw"].fillna(True)
    )
    events["target_cross_survives"] = np.where(usable, np.where(survived, "survives", "fails"), None)
    return join_positioning(events, positioning)


def trend_splits(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for year in range(2008, HOLDOUT_START.year):
        start = pd.Timestamp(year=year, month=1, day=1)
        rows.append({"layer": "trend", "fold": f"validation_{year}", "test_start": start, "test_end": start + pd.DateOffset(years=1) - pd.Timedelta(days=1)})
    rows.append({"layer": "trend", "fold": "holdout", "test_start": HOLDOUT_START, "test_end": events["date"].max()})
    return pd.DataFrame(rows)


def _trend_features(events: pd.DataFrame, positioning: pd.DataFrame) -> list[str]:
    excluded = {
        "date", "macro_date", "symbol", "price", "sma50", "sma200", "duration_trading_days",
        "max_favorable", "whipsaw", "whipsaw_censored", "fwd_21d", "fwd_63d", "fwd_126d",
        "fwd_252d", "gmm_regime", "target_cross_survives", "target_end_date_3m", "cot_usable_date",
        "cot_age_days",
    }
    return [column for column in events.columns if column not in excluded]


def _current_positioning_snapshot(positioning: pd.DataFrame, asof: pd.Timestamp) -> dict[str, Any]:
    latest = positioning.loc[positioning.index <= asof].tail(1)
    if latest.empty:
        return {"available": False}
    row = latest.iloc[0]
    return {
        "available": True,
        "usable_date": pd.Timestamp(latest.index[0]).strftime("%Y-%m-%d"),
        "age_days": int((asof - latest.index[0]).days),
        "asset_manager_net_pct_oi": float(row["cot_asset_mgr_net_pct_oi"]),
        "asset_manager_z": float(row["cot_asset_mgr_net_pct_oi_z"]),
        "leveraged_funds_net_pct_oi": float(row["cot_lev_funds_net_pct_oi"]),
        "leveraged_funds_z": float(row["cot_lev_funds_net_pct_oi_z"]),
        "dealer_net_pct_oi": float(row["cot_dealer_net_pct_oi"]),
        "dealer_z": float(row["cot_dealer_net_pct_oi_z"]),
        "crowding_abs_z": float(row["cot_crowding_abs_z"]),
    }


def build_model_audit(
    *,
    asof: pd.Timestamp,
    macro: ClassificationResult,
    sector: RegressionResult,
    company: RegressionResult,
    trend: ClassificationResult,
    sizing: pd.DataFrame,
    gamma: dict[str, Any] | None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    def add(check: str, passed: bool, detail: str, warning: bool = False) -> None:
        rows.append({"check": check, "status": "WARN" if warning else ("PASS" if passed else "FAIL"), "detail": detail})

    models = {"macro": macro, "sector": sector, "company": company, "trend": trend}
    leaked = {
        layer: [
            feature for feature in model.feature_columns
            if feature.startswith("target_") or feature.startswith("fwd_") or "leader_rank_pct" in feature
        ]
        for layer, model in models.items()
    }
    add("targets_excluded", not any(leaked.values()), f"leaked features={leaked}")
    cftc_counts = {
        layer: sum(feature.startswith("cot_") for feature in model.feature_columns)
        for layer, model in models.items()
    }
    add("cftc_in_all_layers", all(count > 0 for count in cftc_counts.values()), f"selected CFTC features={cftc_counts}")
    selected_fundamentals = sorted(COMPANY_FUNDAMENTAL_FEATURES.intersection(company.feature_columns))
    add(
        "sector_specific_fundamentals_retained",
        len(selected_fundamentals) == len(COMPANY_FUNDAMENTAL_FEATURES),
        f"selected {len(selected_fundamentals)}/{len(COMPANY_FUNDAMENTAL_FEATURES)} company fundamental fields",
    )
    immature = {layer: model.trained_through.strftime("%Y-%m-%d") for layer, model in models.items() if model.trained_through > asof}
    add("matured_labels_only", not immature, f"asof={asof.date()}, later cutoffs={immature}")
    holdout_counts = {
        layer: int(model.predictions.get("fold", pd.Series(dtype=str)).eq("holdout").sum())
        for layer, model in models.items()
    }
    add("holdout_present", all(count > 0 for count in holdout_counts.values()), f"holdout rows={holdout_counts}")
    missing_live = {
        layer: int(model.live["predicted_alpha" if isinstance(model, RegressionResult) else "predicted_class"].isna().sum())
        for layer, model in models.items()
    }
    add("live_predictions_complete", not any(missing_live.values()), f"missing live predictions={missing_live}")
    add("ticker_consolidation", not sizing.duplicated("ticker").any(), "one sizing row per ticker after SEMIS/sector consolidation")
    active = sizing.loc[sizing["suggested_weight"].ne(0.0)]
    cap_ok = active["suggested_weight"].abs().max() <= 0.0600001 if len(active) else True
    add("single_name_cap", cap_ok, "maximum absolute suggested weight <= 6%")
    sector_gross = active.assign(abs_weight=active["suggested_weight"].abs()).groupby("parent_sector")["abs_weight"].sum()
    sector_cap_ok = sector_gross.max() <= 0.2000001 if len(sector_gross) else True
    add("shared_sector_gross_cap", sector_cap_ok, f"maximum sector gross={sector_gross.max() if len(sector_gross) else 0.0:.3f}")
    realized_net = float(sizing["realized_net"].iloc[0]) if len(sizing) else 0.0
    feasible_net = float(sizing["feasible_net_budget"].iloc[0]) if len(sizing) else 0.0
    add(
        "net_budget_respected",
        abs(realized_net - feasible_net) <= 1e-6,
        f"realized net={realized_net:.4f}, feasible target net={feasible_net:.4f}",
    )
    add("gamma_not_trained", not any("gamma" in feature.lower() for model in models.values() for feature in model.feature_columns), "gamma is live-only")
    add(
        "sector_evidence_strength",
        True,
        f"validation reliability={sector.validation_reliability:.3f}; forecasts are strongly shrunk",
        warning=sector.validation_reliability < 0.10,
    )
    add(
        "company_universe_scope",
        True,
        "confidence requires broad and strict point-in-time validation evidence; static SEMIS/nonmember rows receive explicit haircuts",
        warning=True,
    )
    add(
        "gamma_history",
        True,
        "live gamma snapshot available" if gamma else "no historical or current chain; neutral overlay",
        warning=gamma is None,
    )
    return pd.DataFrame(rows)


def _select_primary_company_rows(company: pd.DataFrame) -> pd.DataFrame:
    frame = company.copy()
    frame["priority"] = 3
    frame.loc[frame["pit_member"].eq(True), "priority"] = 2
    frame.loc[frame["book"].eq("SEMIS"), "priority"] = 1
    frame["metric_priority"] = -pd.to_numeric(frame.get("n_metrics"), errors="coerce").fillna(0)
    return frame.sort_values(["ticker", "priority", "metric_priority", "book"]).drop_duplicates("ticker", keep="first")


def _macro_risk_probabilities(macro_live: pd.DataFrame) -> tuple[float, float]:
    row = macro_live.iloc[0]
    favorable = sum(
        float(row.get(f"validated_prob::{label}", row.get(f"prob::{label}", 0.0)))
        for label in FAVORABLE_REGIMES
    )
    adverse = sum(
        float(row.get(f"validated_prob::{label}", row.get(f"prob::{label}", 0.0)))
        for label in ADVERSE_REGIMES
    )
    return favorable, adverse


def _capped_budget(
    scores: pd.Series,
    sectors: pd.Series,
    budget: float,
    *,
    max_position: float,
    max_sector: float,
    existing_sector_usage: dict[str, float] | None = None,
) -> pd.Series:
    weights = pd.Series(0.0, index=scores.index)
    positive = scores.clip(lower=0.0)
    if budget <= 0 or positive.sum() <= 0:
        return weights
    active = positive.index[positive > 0].tolist()
    existing_sector_usage = existing_sector_usage or {}
    remaining = budget
    for _ in range(12):
        if remaining <= 1e-9 or not active:
            break
        allocation = positive.loc[active] / positive.loc[active].sum() * remaining
        added = 0.0
        next_active = []
        for index, amount in allocation.items():
            position_room = max_position - weights.loc[index]
            sector = str(sectors.loc[index])
            sector_used = float(weights.loc[sectors.eq(sectors.loc[index])].sum()) + float(
                existing_sector_usage.get(sector, 0.0)
            )
            sector_room = max_sector - sector_used
            increment = max(0.0, min(float(amount), position_room, sector_room))
            weights.loc[index] += increment
            added += increment
            if position_room - increment > 1e-9 and sector_room - increment > 1e-9:
                next_active.append(index)
        if added <= 1e-9:
            break
        remaining -= added
        active = next_active
    return weights


def _feasible_side_budgets(
    gross_budget: float,
    net_budget: float,
    long_capacity: float,
    short_capacity: float,
) -> tuple[float, float, float]:
    """Solve the largest gross book that respects signal capacity and target net."""
    long_capacity = max(float(long_capacity), 0.0)
    short_capacity = max(float(short_capacity), 0.0)
    feasible_net = float(np.clip(net_budget, -short_capacity, long_capacity))
    feasible_gross = min(
        max(float(gross_budget), 0.0),
        2.0 * long_capacity - feasible_net,
        2.0 * short_capacity + feasible_net,
    )
    feasible_gross = max(float(feasible_gross), abs(feasible_net), 0.0)
    long_budget = min((feasible_gross + feasible_net) / 2.0, long_capacity)
    short_budget = min((feasible_gross - feasible_net) / 2.0, short_capacity)
    return float(long_budget), float(short_budget), feasible_net


def build_sizing_advisor(
    macro: ClassificationResult,
    sector: RegressionResult,
    company: RegressionResult,
    trend: ClassificationResult,
    positioning: dict[str, Any],
    gamma: dict[str, Any] | None,
) -> pd.DataFrame:
    sector_live = sector.live.copy()
    survival_probability_column = (
        "validated_prob::survives"
        if "validated_prob::survives" in trend.live
        else "prob::survives"
    )
    sector_live = sector_live.merge(
        trend.live[["sector", "symbol", "date", "type", survival_probability_column]].rename(
            columns={"date": "last_sector_cross_date", "type": "last_sector_cross_type", survival_probability_column: "sector_cross_survival_probability"}
        ),
        on="sector",
        how="left",
    )
    company_live = _select_primary_company_rows(company.live)
    company_live = company_live.merge(
        sector_live[[
            "sector", "validated_alpha", "predicted_alpha", "agreement_confidence",
            "validation_reliability", "sector_cross_survival_probability", "last_sector_cross_type",
        ]].rename(columns={
            "sector": "parent_sector",
            "validated_alpha": "sector_validated_alpha",
            "predicted_alpha": "sector_predicted_alpha",
            "agreement_confidence": "sector_model_agreement",
            "validation_reliability": "sector_validation_reliability",
        }),
        on="parent_sector",
        how="left",
        validate="many_to_one",
    )
    company_live = company_live.rename(columns={
        "validated_alpha": "company_validated_alpha",
        "predicted_alpha": "company_predicted_alpha",
        "agreement_confidence": "company_model_agreement",
        "validation_reliability": "company_validation_reliability",
    })
    company_live["expected_total_alpha"] = (
        company_live["sector_validated_alpha"].fillna(0.0)
        + company_live["company_validated_alpha"].fillna(0.0)
    )
    positive = company_live["expected_total_alpha"] >= 0.0
    state = company_live["company_50_200_state"].astype(str)
    alignment = (positive & state.eq("golden")) | (~positive & state.eq("death"))
    age = pd.to_numeric(company_live["company_50_200_age_months"], errors="coerce").fillna(0.0)
    company_live["company_trend_confidence"] = np.where(
        alignment,
        0.60 + 0.40 * (age / 6.0).clip(0.0, 1.0),
        0.25,
    )
    company_live["fundamental_confidence"] = (
        pd.to_numeric(company_live["n_metrics"], errors="coerce").fillna(0.0) / 5.0
    ).clip(0.0, 1.0)
    company_live["point_in_time_confidence"] = np.where(
        company_live["pit_member"].eq(True),
        1.0,
        np.where(company_live["book"].eq("SEMIS"), 0.65, 0.40),
    )
    company_live["technical_confidence"] = (
        company_live["company_model_agreement"].fillna(0.0)
        * company_live["sector_model_agreement"].fillna(0.0)
        * company_live["company_trend_confidence"]
        * company_live["fundamental_confidence"]
        * company_live["sector_cross_survival_probability"].fillna(0.5).clip(0.25, 1.0)
        * company_live["point_in_time_confidence"]
    ).pow(1.0 / 6.0)
    sector_raw = company_live["sector_predicted_alpha"].abs().fillna(0.0)
    company_raw = company_live["company_predicted_alpha"].abs().fillna(0.0)
    evidence_denominator = sector_raw + company_raw
    company_live["model_evidence_confidence"] = np.where(
        evidence_denominator > 0.0,
        (
            sector_raw * company_live["sector_validation_reliability"].fillna(0.0)
            + company_raw * company_live["company_validation_reliability"].fillna(0.0)
        ) / evidence_denominator,
        0.0,
    )
    company_live["confidence"] = np.sqrt(
        company_live["technical_confidence"]
        * company_live["model_evidence_confidence"].clip(0.0, 1.0)
    )
    volatility = pd.to_numeric(company_live["company_volatility_63d"], errors="coerce").clip(0.12, 1.50)
    company_live["risk_score"] = company_live["expected_total_alpha"].abs() * company_live["confidence"] / volatility
    company_live["allocation_eligible"] = (
        (company_live["pit_member"].eq(True) | company_live["book"].eq("SEMIS"))
        & pd.to_numeric(company_live["n_metrics"], errors="coerce").ge(3)
        & company_live["quality_z"].notna()
    )

    favorable, adverse = _macro_risk_probabilities(macro.live)
    macro_reliability = macro.validation_reliability
    directional_conviction = (favorable - adverse) * macro_reliability
    gross_budget = float(np.clip(0.70 + 0.35 * macro_reliability, 0.60, 1.05))
    net_budget = float(np.clip(0.30 * directional_conviction, -0.25, 0.25))

    positioning_scalar = 1.0
    if positioning.get("available"):
        asset_manager_z = float(positioning.get("asset_manager_z", 0.0))
        crowding = float(positioning.get("crowding_abs_z", 0.0))
        positioning_scalar -= 0.10 * max(asset_manager_z - 1.0, 0.0)
        positioning_scalar -= 0.05 * max(crowding - 2.0, 0.0)
    positioning_scalar = float(np.clip(positioning_scalar, 0.75, 1.0))
    gamma_scalar = 0.80 if gamma and str(gamma.get("regime", "")).startswith("short gamma") else 1.0
    gross_budget *= positioning_scalar * gamma_scalar
    net_budget *= positioning_scalar * gamma_scalar
    long_budget = max(0.0, (gross_budget + net_budget) / 2.0)
    short_budget = max(0.0, (gross_budget - net_budget) / 2.0)

    long_candidates = company_live.loc[
        company_live["allocation_eligible"]
        & company_live["expected_total_alpha"].ge(LONG_ALPHA_HURDLE)
        & state.eq("golden")
    ].nlargest(18, "risk_score")
    short_candidates = company_live.loc[
        company_live["allocation_eligible"]
        & company_live["expected_total_alpha"].le(-SHORT_ALPHA_HURDLE)
        & state.eq("death")
    ].nlargest(12, "risk_score")
    long_capacity_weights = _capped_budget(
        long_candidates["risk_score"], long_candidates["parent_sector"], long_budget,
        max_position=0.06, max_sector=0.20,
    )
    short_capacity_weights = _capped_budget(
        short_candidates["risk_score"], short_candidates["parent_sector"], short_budget,
        max_position=0.05, max_sector=0.20,
    )
    feasible_long_budget, feasible_short_budget, feasible_net_budget = _feasible_side_budgets(
        gross_budget,
        net_budget,
        long_capacity_weights.sum(),
        short_capacity_weights.sum(),
    )
    target_long = feasible_long_budget
    target_short = feasible_short_budget
    for _ in range(4):
        long_weights = _capped_budget(
            long_candidates["risk_score"], long_candidates["parent_sector"], target_long,
            max_position=0.06, max_sector=0.20,
        )
        long_sector_usage = long_weights.groupby(long_candidates["parent_sector"]).sum().to_dict()
        short_weights = _capped_budget(
            short_candidates["risk_score"], short_candidates["parent_sector"], target_short,
            max_position=0.05, max_sector=0.20, existing_sector_usage=long_sector_usage,
        )
        allocated_long = float(long_weights.sum())
        allocated_short = float(short_weights.sum())
        realized_net = allocated_long - allocated_short
        if abs(realized_net - feasible_net_budget) <= 1e-9:
            break
        if realized_net > feasible_net_budget:
            target_long = max(allocated_short + feasible_net_budget, 0.0)
        else:
            target_short = max(allocated_long - feasible_net_budget, 0.0)
    company_live["suggested_weight"] = 0.0
    company_live.loc[long_weights.index, "suggested_weight"] = long_weights
    company_live.loc[short_weights.index, "suggested_weight"] = -short_weights
    company_live["side"] = np.where(
        company_live["suggested_weight"] > 0, "Long",
        np.where(company_live["suggested_weight"] < 0, "Short", "Watch"),
    )
    company_live["macro_favorable_probability"] = favorable
    company_live["macro_adverse_probability"] = adverse
    company_live["positioning_gross_scalar"] = positioning_scalar
    company_live["gamma_gross_scalar"] = gamma_scalar
    company_live["gross_budget"] = gross_budget
    company_live["net_budget"] = net_budget
    company_live["feasible_gross_budget"] = feasible_long_budget + feasible_short_budget
    company_live["feasible_net_budget"] = feasible_net_budget
    lacks_validation = (sector.validation_reliability <= 0.0) or (company.validation_reliability <= 0.0)
    if lacks_validation:
        company_live["suggested_weight"] = 0.0
        company_live["side"] = "Watch"
        company_live["feasible_gross_budget"] = 0.0
        company_live["feasible_net_budget"] = 0.0
    realized_gross = float(company_live["suggested_weight"].abs().sum())
    realized_net = float(company_live["suggested_weight"].sum())
    if lacks_validation:
        sizing_status = "ABSTAIN: one or more alpha layers lack positive validation evidence"
    elif realized_gross <= 1e-12:
        sizing_status = "NO_SIGNALS_ABOVE_HURDLE"
    elif gross_budget > 0.0 and realized_gross / gross_budget < 0.10:
        sizing_status = "ABSTAIN: insufficient balanced signal capacity"
        company_live["suggested_weight"] = 0.0
        company_live["side"] = "Watch"
        company_live["feasible_gross_budget"] = 0.0
        company_live["feasible_net_budget"] = 0.0
        realized_gross = 0.0
        realized_net = 0.0
    else:
        sizing_status = "ACTIVE_RESEARCH"
    company_live["sizing_status"] = sizing_status
    company_live["realized_gross"] = realized_gross
    company_live["realized_net"] = realized_net
    company_live["unallocated_risk_budget"] = max(gross_budget - realized_gross, 0.0)

    keep = [
        "ticker", "book", "book_specification", "parent_sector", "side", "suggested_weight",
        "sizing_status", "expected_total_alpha", "sector_predicted_alpha", "sector_validated_alpha",
        "company_predicted_alpha", "company_validated_alpha", "confidence", "technical_confidence",
        "model_evidence_confidence", "risk_score",
        "quality_z", "n_metrics", "company_50_200_state", "company_50_200_age_months",
        "point_in_time_confidence",
        "company_sma50_200_gap", "company_relative_oscillator", "company_volatility_63d",
        "company_beta_252d", "sector_cross_survival_probability", "last_sector_cross_type",
        "macro_favorable_probability", "macro_adverse_probability", "positioning_gross_scalar",
        "gamma_gross_scalar", "gross_budget", "net_budget", "pit_member",
        "feasible_gross_budget", "feasible_net_budget", "allocation_eligible",
        "realized_gross", "realized_net", "unallocated_risk_budget",
    ]
    return company_live[[column for column in keep if column in company_live]].sort_values(
        ["suggested_weight", "expected_total_alpha"], ascending=[False, False]
    ).reset_index(drop=True)


def _causal_regression_reliability(
    predictions: pd.DataFrame,
    asof: pd.Timestamp,
    *,
    group_columns: list[str],
    horizon: int,
    strict_point_in_time: bool = False,
) -> float:
    matured = predictions.loc[
        pd.to_datetime(predictions["target_end_date"]).lt(asof)
        & pd.to_datetime(predictions["date"]).lt(asof)
    ].copy()
    if matured["date"].nunique() < 24:
        return 0.0
    broad_metrics = pd.DataFrame([
        _regression_metrics(matured, scope="validation", group_columns=group_columns, horizon=horizon)
    ])
    broad = _regression_reliability(broad_metrics)
    if not strict_point_in_time:
        return broad
    strict = matured.loc[matured["strict_pit_eligible"].eq(True)]
    if len(strict) < 500 or strict["date"].nunique() < 24:
        return 0.0
    strict_metrics = pd.DataFrame([
        _regression_metrics(strict, scope="validation", group_columns=group_columns, horizon=horizon)
    ])
    return float(math.sqrt(broad * _regression_reliability(strict_metrics)))


def _causal_classification_live(
    predictions: pd.DataFrame,
    asof: pd.Timestamp,
    classes: list[str],
    *,
    positive_class: str | None = None,
) -> tuple[float, pd.Series]:
    matured = predictions.loc[
        pd.to_datetime(predictions["target_end_date"]).lt(asof)
        & pd.to_datetime(predictions["date"]).lt(asof)
    ].copy()
    if len(matured) < max(24, len(classes) * 5):
        reliability = 0.0
    else:
        metrics = pd.DataFrame([_classification_metrics(
            matured,
            scope="validation",
            classes=classes,
            positive_class=positive_class,
        )])
        reliability = _classification_reliability(metrics, len(classes))
    if matured.empty:
        prior = pd.Series(1.0 / len(classes), index=classes)
    else:
        prior = matured["target"].value_counts(normalize=True).reindex(classes, fill_value=0.0)
    return reliability, prior


def _historical_result_shell(
    *,
    live: pd.DataFrame,
    reliability: float,
    classes: list[str] | None,
    asof: pd.Timestamp,
) -> RegressionResult | ClassificationResult:
    common = {
        "predictions": pd.DataFrame(),
        "live": live,
        "metrics": pd.DataFrame(),
        "importance": pd.DataFrame(columns=["layer", "feature", "importance"]),
        "feature_columns": [],
        "validation_reliability": reliability,
        "trained_through": asof,
    }
    if classes is None:
        return RegressionResult(**common)
    return ClassificationResult(**common, classes=classes)


def build_walkforward_portfolio_targets(
    macro: ClassificationResult,
    sector: RegressionResult,
    company: RegressionResult,
    trend: ClassificationResult,
    positioning: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Replay portfolio decisions with only labels matured by each signal date."""
    dates = sorted(pd.to_datetime(company.predictions["date"].dropna().unique()))
    signal_rows: list[dict[str, Any]] = []
    target_rows: list[dict[str, Any]] = []
    for asof in dates:
        asof = pd.Timestamp(asof)
        company_live = company.predictions.loc[pd.to_datetime(company.predictions["date"]).eq(asof)].copy()
        sector_live = sector.predictions.loc[pd.to_datetime(sector.predictions["date"]).eq(asof)].copy()
        macro_candidates = macro.predictions.loc[pd.to_datetime(macro.predictions["date"]).le(asof)]
        if company_live.empty or sector_live.empty or macro_candidates.empty:
            continue
        macro_live = macro_candidates.loc[
            pd.to_datetime(macro_candidates["date"]).eq(pd.to_datetime(macro_candidates["date"]).max())
        ].tail(1).copy()

        company_reliability = _causal_regression_reliability(
            company.predictions,
            asof,
            group_columns=["date", "book"],
            horizon=6,
            strict_point_in_time=True,
        )
        sector_reliability = _causal_regression_reliability(
            sector.predictions,
            asof,
            group_columns=["date"],
            horizon=6,
        )
        company_live["validation_reliability"] = company_reliability
        company_live["validated_alpha"] = company_live["predicted_alpha"] * company_reliability
        sector_live["validation_reliability"] = sector_reliability
        sector_live["validated_alpha"] = sector_live["predicted_alpha"] * sector_reliability

        macro_reliability, macro_prior = _causal_classification_live(
            macro.predictions, asof, macro.classes
        )
        macro_live["validation_reliability"] = macro_reliability
        for label in macro.classes:
            macro_live[f"validated_prob::{label}"] = (
                float(macro_prior[label])
                + macro_reliability * (macro_live[f"prob::{label}"] - float(macro_prior[label]))
            )

        trend_candidates = trend.predictions.loc[pd.to_datetime(trend.predictions["date"]).le(asof)].copy()
        if trend_candidates.empty:
            trend_live = pd.DataFrame(columns=[
                "date", "sector", "symbol", "type", "validated_prob::survives"
            ])
            trend_reliability = 0.0
        else:
            trend_live = trend_candidates.sort_values("date").groupby("sector", as_index=False).tail(1).copy()
            trend_reliability, trend_prior = _causal_classification_live(
                trend.predictions,
                asof,
                trend.classes,
                positive_class="survives",
            )
            for label in trend.classes:
                trend_live[f"validated_prob::{label}"] = (
                    float(trend_prior[label])
                    + trend_reliability * (trend_live[f"prob::{label}"] - float(trend_prior[label]))
                )

        macro_shell = _historical_result_shell(
            live=macro_live, reliability=macro_reliability, classes=macro.classes, asof=asof
        )
        sector_shell = _historical_result_shell(
            live=sector_live, reliability=sector_reliability, classes=None, asof=asof
        )
        company_shell = _historical_result_shell(
            live=company_live, reliability=company_reliability, classes=None, asof=asof
        )
        trend_shell = _historical_result_shell(
            live=trend_live, reliability=trend_reliability, classes=trend.classes, asof=asof
        )
        sizing = build_sizing_advisor(
            macro_shell,
            sector_shell,
            company_shell,
            trend_shell,
            _current_positioning_snapshot(positioning, asof),
            None,
        )
        if sizing.empty:
            continue
        summary = sizing.iloc[0]
        signal_rows.append({
            "date": asof,
            "sizing_status": summary["sizing_status"],
            "active_names": int(sizing["suggested_weight"].ne(0.0).sum()),
            "gross_exposure": float(sizing["suggested_weight"].abs().sum()),
            "net_exposure": float(sizing["suggested_weight"].sum()),
            "macro_reliability": macro_reliability,
            "sector_reliability": sector_reliability,
            "company_reliability": company_reliability,
            "trend_reliability": trend_reliability,
        })
        for row in sizing.loc[sizing["suggested_weight"].ne(0.0), ["ticker", "suggested_weight"]].itertuples(index=False):
            target_rows.append({
                "date": asof,
                "symbol": str(row.ticker),
                "target_weight": float(row.suggested_weight),
            })
    return pd.DataFrame(signal_rows), pd.DataFrame(
        target_rows,
        columns=["date", "symbol", "target_weight"],
    )


def _chart_live_sector(sector: RegressionResult) -> str:
    view = sector.live.sort_values("validated_alpha")
    fig, ax = _vintage_figure(figsize=(10.5, 5.0))
    colors = [INK_GREEN if value >= 0 else INK_RED for value in view["validated_alpha"]]
    ax.barh(view["sector"], view["validated_alpha"] * 100.0, color=colors, alpha=0.82)
    ax.axvline(0.0, color=INK, linewidth=0.8)
    ax.set_title("Live sector excess-return forecast after validation shrinkage", loc="left", fontsize=12)
    ax.set_xlabel("six-month expected excess return (%)")
    return _figure_b64(fig)


def _chart_macro_probabilities(macro: ClassificationResult) -> str:
    row = macro.live.iloc[0]
    probabilities = pd.Series({label: float(row[f"prob::{label}"]) for label in macro.classes}).sort_values()
    fig, ax = _vintage_figure(figsize=(10.5, 4.6))
    ax.barh(probabilities.index, probabilities * 100.0, color=[INK_AMBER, INK_RED, INK_NAVY, INK_GREEN, INK_MUTED][: len(probabilities)])
    ax.set_title("Next-three-month Dalio regime probabilities", loc="left", fontsize=12)
    ax.set_xlabel("ensemble probability (%)")
    ax.set_xlim(0, max(50.0, probabilities.max() * 115.0))
    return _figure_b64(fig)


def _chart_company_alpha(company: RegressionResult) -> str:
    view = _select_primary_company_rows(company.live).sort_values("validated_alpha")
    view = pd.concat([view.head(12), view.tail(12)]).drop_duplicates("ticker")
    fig, ax = _vintage_figure(figsize=(10.5, 6.0))
    colors = [INK_GREEN if value >= 0 else INK_RED for value in view["validated_alpha"]]
    ax.barh(view["ticker"], view["validated_alpha"] * 100.0, color=colors, alpha=0.82)
    ax.axvline(0.0, color=INK, linewidth=0.8)
    ax.set_title("Strongest company residual forecasts after validation shrinkage", loc="left", fontsize=12)
    ax.set_xlabel("six-month expected residual return (%)")
    return _figure_b64(fig)


def _chart_oos_ic(sector: RegressionResult, company: RegressionResult) -> str:
    fig, ax = _vintage_figure(figsize=(10.5, 4.5))
    for result, label, color, groups in [
        (sector, "Sector", INK_NAVY, ["date"]),
        (company, "Company", INK_GREEN, ["date", "book"]),
    ]:
        frame = result.predictions.loc[~result.predictions["fold"].eq("holdout")]
        values = []
        for keys, group in frame.groupby(groups):
            if len(group) >= 4 and group["predicted_alpha"].nunique() > 1:
                date = pd.Timestamp(keys[0] if isinstance(keys, tuple) else keys)
                values.append((date, group["predicted_alpha"].corr(group["target"], method="spearman")))
        series = pd.DataFrame(values, columns=["date", "ic"]).groupby("date")["ic"].mean().rolling(12, min_periods=6).mean()
        ax.plot(series.index, series, color=color, linewidth=1.25, label=label)
    ax.axhline(0.0, color=INK, linewidth=0.8)
    ax.set_title("Walk-forward rank IC, trailing 12-month mean", loc="left", fontsize=12)
    ax.set_ylabel("Spearman IC")
    ax.legend(frameon=False, labelcolor=INK)
    return _figure_b64(fig)


def build_html_report(result: FinalHierarchyResult) -> str:
    sizing = result.sizing
    active = sizing.loc[sizing["suggested_weight"].ne(0.0)]
    macro_view = result.macro.live[["predicted_class", "ensemble_confidence", "model_agreement", "validation_reliability"]]
    metrics = pd.concat([
        result.macro.metrics.assign(layer="macro"),
        result.sector.metrics.assign(layer="sector"),
        result.company.metrics.assign(layer="company"),
        result.trend.metrics.assign(layer="trend"),
    ], ignore_index=True, sort=False)
    def sizing_view(frame: pd.DataFrame) -> pd.DataFrame:
        columns = [
            "ticker", "book", "parent_sector", "side", "suggested_weight",
            "expected_total_alpha", "quality_z", "n_metrics", "company_50_200_state",
        ]
        view = frame[[column for column in columns if column in frame]].copy()
        view["suggested_weight"] = view["suggested_weight"] * 100.0
        view["expected_total_alpha"] = view["expected_total_alpha"] * 100.0
        return view.rename(columns={
            "suggested_weight": "weight_pct",
            "expected_total_alpha": "expected_6m_alpha_pct",
            "n_metrics": "fundamental_metrics",
            "company_50_200_state": "50_200_state",
        })

    top_sizing = sizing_view(sizing.sort_values("expected_total_alpha", ascending=False).head(20))
    bottom_sizing = sizing_view(sizing.sort_values("expected_total_alpha").head(12))
    positioning = result.positioning_snapshot
    cftc = positioning.get("cftc", {})
    gex = positioning.get("gamma", {})
    positioning_view = pd.DataFrame([
        {
            "participant": "Asset managers",
            "net_pct_open_interest": cftc.get("asset_manager_net_pct_oi"),
            "rolling_z_score": cftc.get("asset_manager_z"),
        },
        {
            "participant": "Leveraged funds",
            "net_pct_open_interest": cftc.get("leveraged_funds_net_pct_oi"),
            "rolling_z_score": cftc.get("leveraged_funds_z"),
        },
        {
            "participant": "Dealers",
            "net_pct_open_interest": cftc.get("dealer_net_pct_oi"),
            "rolling_z_score": cftc.get("dealer_z"),
        },
    ])
    cftc_attribution_rows = []
    for model in [result.macro, result.sector, result.company, result.trend]:
        selected = model.importance.loc[model.importance["feature"].str.startswith("cot_")]
        cftc_attribution_rows.append({
            "layer": selected["layer"].iloc[0] if len(selected) else "unknown",
            "selected_features": int(selected["feature"].nunique()),
            "importance_pct": float(selected["importance"].sum() * 100.0),
            "top_feature": selected.nlargest(1, "importance")["feature"].iloc[0] if len(selected) else "none",
        })
    cftc_attribution = pd.DataFrame(cftc_attribution_rows)
    governance_view = pd.DataFrame(result.governance["layers"]).T.reset_index(names="layer")
    governance_view["features"] = pd.to_numeric(governance_view["features"], errors="coerce").astype("Int64")
    governance_view["validation_reliability"] = pd.to_numeric(
        governance_view["validation_reliability"], errors="coerce"
    )
    portfolio_summary_view = pd.DataFrame([{
        key: value
        for key, value in result.portfolio_summary.items()
        if not isinstance(value, (dict, list))
    }])
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    status = sizing["sizing_status"].iloc[0] if len(sizing) else "NO_OUTPUT"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Final Hierarchical Research Model</title><style>
:root{{--paper:{PAPER};--page:#eadcb8;--grid:#dbc17b;--major:#c8a24b;--ink:{INK};--muted:{INK_MUTED};--navy:{INK_NAVY};--red:{INK_RED};--green:{INK_GREEN}}}
*{{box-sizing:border-box}} body{{margin:0;color:var(--ink);background:#eadcb8;font:14px/1.48 Georgia,"Times New Roman",serif;letter-spacing:0}} main{{max-width:1320px;margin:0 auto;padding:30px 38px 64px;background-color:var(--paper);background-image:linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px),linear-gradient(var(--major) 1px,transparent 1px),linear-gradient(90deg,var(--major) 1px,transparent 1px);background-size:10px 10px,10px 10px,50px 50px,50px 50px}}
header,.band{{background:rgba(244,236,211,.95)}} header{{border-top:4px solid var(--ink);border-bottom:1px solid var(--ink);padding:16px 0 14px}} h1{{font-size:31px;line-height:1.08;margin:0 0 7px}} h2{{font-size:20px;margin:34px 0 10px;border-bottom:2px solid var(--ink);padding-bottom:5px}} p{{max-width:980px}} .meta{{color:var(--muted);font-size:12px}} .kpis{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border:1px solid var(--ink);margin:22px 0;background:rgba(244,236,211,.96)}} .kpi{{padding:13px 15px;border-right:1px solid var(--ink)}} .kpi:last-child{{border-right:0}} .kpi b{{display:block;font:22px/1.05 Arial,sans-serif;color:var(--navy)}} .kpi span{{font-size:11px;text-transform:uppercase}} .band{{padding:1px 12px 12px;margin:0 -12px}} .charts{{display:grid;grid-template-columns:1fr 1fr;gap:18px}} .charts>*{{min-width:0}} figure{{margin:10px 0;background:var(--paper);border:1px solid var(--ink);padding:8px}} img{{width:100%;display:block}} figcaption{{font-size:11px;color:var(--muted);padding-top:5px}} .table-wrap{{overflow-x:auto;border:1px solid var(--ink);background:rgba(244,236,211,.97)}} table{{border-collapse:collapse;width:100%;font-size:12px}} th,td{{padding:7px 9px;border-bottom:1px solid #c9b77f;text-align:left;white-space:nowrap}} thead th{{background:#e1cd91;border-bottom:2px solid var(--ink);font-family:Arial,sans-serif}} tbody tr:nth-child(even){{background:rgba(225,205,145,.25)}} .warn{{color:#925c00;font-weight:bold}} .active{{color:var(--green);font-weight:bold}} code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}} @media(max-width:800px){{main{{padding:18px 14px 44px}}.kpis{{grid-template-columns:1fr 1fr}}.kpi:nth-child(2){{border-right:0}}.charts{{grid-template-columns:1fr}}h1{{font-size:25px}}}}
</style></head><body><main><header><h1>Final Hierarchical Macro -> Sector -> Company Model</h1><p>Walk-forward regime probabilities, sector excess-return forecasts, company residual alpha, trend survival, positioning, and constrained long/short sizing.</p><p class="meta">Data as of {positioning.get('asof', 'n/a')}. Generated {generated}. Research output, not personalized investment advice. <a href="../factor_driver_model/index.html">Open 6/12-month factor attribution</a>.</p></header>
<div class="kpis"><div class="kpi"><b>{result.macro.live.iloc[0]['predicted_class'].split(' ')[0]}</b><span>Forecast regime</span></div><div class="kpi"><b>{result.sector.validation_reliability:.2f}</b><span>Sector reliability</span></div><div class="kpi"><b>{result.company.validation_reliability:.2f}</b><span>Company reliability</span></div><div class="kpi"><b>{float(sizing['realized_gross'].iloc[0]) * 100.0 if len(sizing) else 0.0:.2f}%</b><span>Realized gross / {len(active)} names</span></div></div>
<section class="band"><h2>Decision State</h2><p class="{'active' if status == 'ACTIVE_RESEARCH' else 'warn'}">{status}</p><div class="table-wrap">{_html_table(macro_view)}</div><div class="charts">{_img(_chart_macro_probabilities(result.macro), 'Macro regime probability ensemble')}{_img(_chart_live_sector(result.sector), 'Sector forecasts after validation shrinkage')}</div></section>
<section class="band"><h2>Company Selection And Sizing</h2><p>Expected alpha is sector excess alpha plus company residual alpha. Nonzero weights require current point-in-time book membership or the dedicated SEMIS specification, at least three fundamentals, directional 50/200 confirmation, a 1.0% long or 1.5% short six-month alpha hurdle, volatility scaling, 6% long-name caps, 5% short-name caps, and one shared 20% gross sector cap. Long and short sleeves are solved jointly so missing signals cannot violate the macro net target; unused risk budget stays unallocated.</p>{_img(_chart_company_alpha(result.company), 'Company residual forecasts after validation shrinkage')}<h3>Highest expected alpha</h3><div class="table-wrap">{_html_table(top_sizing)}</div><h3>Lowest expected alpha</h3><div class="table-wrap">{_html_table(bottom_sizing)}</div></section>
<section class="band"><h2>Out-Of-Sample Validation</h2>{_img(_chart_oos_ic(result.sector, result.company), 'Walk-forward cross-sectional information coefficients')}<div class="table-wrap">{_html_table(metrics)}</div></section>
<section class="band"><h2>Net Portfolio Replay</h2><p>Each historical recommendation is rebuilt from walk-forward predictions using only outcomes whose target window had finished before that signal. Trades execute on the next available close. Turnover compares the new target with drifted pre-trade weights; commission, slippage, perpetual funding, idle-cash carry, and final liquidation are accounted for separately. A <b>RESEARCH_ONLY</b> result means Binance instrument mapping, mark-price history, or funding history is still missing and the figures must not be treated as executable evidence.</p><div class="table-wrap">{_html_table(portfolio_summary_view)}</div></section>
<section class="band"><h2>Positioning And Gamma</h2><p>CFTC positioning enters all four trained layers only after each report's public usable date. The current release is usable from {cftc.get('usable_date', 'n/a')} and applies a {float(sizing['positioning_gross_scalar'].iloc[0]) if len(sizing) else 1.0:.2f} gross-risk scalar. Dealer gamma status: <b>{gex.get('status', 'unavailable')}</b>; its current gross-risk scalar is {float(sizing['gamma_gross_scalar'].iloc[0]) if len(sizing) else 1.0:.2f}. Gamma is never injected into historical features without a point-in-time chain archive.</p><div class="charts"><div><h3>Current CFTC snapshot</h3><div class="table-wrap">{_html_table(positioning_view)}</div></div><div><h3>CFTC model attribution</h3><div class="table-wrap">{_html_table(cftc_attribution)}</div></div></div><p class="meta">{gex.get('detail', GEX_INSTRUCTIONS)}</p></section>
<section class="band"><h2>Governance</h2><p>The 2025+ holdout is reported separately and never selects hyperparameters. Final live models refit on matured labels only after validation reporting. Regression confidence combines non-overlapping rank-IC and top-minus-bottom spread evidence. Company confidence is the geometric mean of broad and strict point-in-time validation scores; static SEMIS and nonmember rows receive explicit haircuts. A zero reliability score forces sizing abstention.</p><div class="table-wrap">{_html_table(governance_view)}</div><h3>Model audit</h3><div class="table-wrap">{_html_table(result.audit)}</div></section>
</main></body></html>"""


def _write_outputs(result: FinalHierarchyResult) -> None:
    out = result.output_dir
    out.mkdir(parents=True, exist_ok=True)
    for layer, model in {
        "macro": result.macro,
        "sector": result.sector,
        "company": result.company,
        "trend": result.trend,
    }.items():
        model.predictions.to_csv(out / f"{layer}_walkforward_predictions.csv", index=False)
        model.live.to_csv(out / f"{layer}_live.csv", index=False)
        model.metrics.to_csv(out / f"{layer}_metrics.csv", index=False)
        model.importance.to_csv(out / f"{layer}_feature_importance.csv", index=False)
    positioning_importance = pd.concat([
        model.importance.loc[model.importance["feature"].str.startswith("cot_")]
        for model in [result.macro, result.sector, result.company, result.trend]
    ], ignore_index=True)
    positioning_importance.to_csv(out / "cftc_feature_importance.csv", index=False)
    family_rows = []
    for model in [result.macro, result.sector, result.company, result.trend]:
        for row in model.importance.itertuples(index=False):
            feature = str(row.feature)
            if feature.startswith("cot_"):
                family = "cftc_positioning"
            elif feature in COMPANY_FUNDAMENTAL_FEATURES:
                family = "company_fundamental"
            elif feature.startswith("company_"):
                family = "company_price_trend"
            elif feature.startswith("parent_"):
                family = "parent_sector"
            elif feature.startswith("book_") or feature.startswith("sector_"):
                family = "cross_section_control"
            elif any(token in feature for token in ["vix", "nfci", "spread", "yield_curve", "cpi", "indpro", "gold", "copper", "wti", "dxy", "cape", "fed_path", "breakeven", "infl_"]):
                family = "macro_market"
            else:
                family = "other"
            family_rows.append({"layer": row.layer, "family": family, "importance": row.importance})
    pd.DataFrame(family_rows).groupby(["layer", "family"], as_index=False)["importance"].sum().to_csv(
        out / "feature_family_importance.csv", index=False
    )
    result.sizing.to_csv(out / "sizing_advisor.csv", index=False)
    result.portfolio_signals.to_csv(out / "portfolio_walkforward_signals.csv", index=False)
    result.portfolio_targets.to_csv(out / "portfolio_walkforward_targets.csv", index=False)
    result.portfolio_periods.to_csv(out / "portfolio_walkforward_periods.csv", index=False)
    (out / "portfolio_backtest_summary.json").write_text(
        json.dumps(result.portfolio_summary, indent=2), encoding="utf-8"
    )
    result.audit.to_csv(out / "model_audit.csv", index=False)
    (out / "positioning_snapshot.json").write_text(json.dumps(result.positioning_snapshot, indent=2), encoding="utf-8")
    (out / "model_governance.json").write_text(json.dumps(result.governance, indent=2), encoding="utf-8")
    (out / "index.html").write_text(build_html_report(result), encoding="utf-8")


def build_final_hierarchy(
    project_root: str | Path | None = None,
    *,
    output_dir: str | Path = OUTPUT_DIR,
) -> FinalHierarchyResult:
    root = resolve_project_root(project_root)
    out = root / output_dir
    total_steps = 8
    _write_progress(out, step=1, total=total_steps, stage="contract", message="Loading audited hierarchical contract")
    frames, registry, splits = _load_contract(root)
    positioning = load_positioning(root)
    position_features = _positioning_feature_columns(positioning)
    for layer in frames:
        frames[layer] = join_positioning(frames[layer], positioning)

    macro_features = _registered_features(registry, "macro") + position_features
    sector_features = _registered_features(registry, "sector") + position_features
    company_features = _registered_features(registry, "company") + ["book", "parent_sector"] + position_features
    _write_progress(out, step=2, total=total_steps, stage="live", message="Building current macro, sector, and company rows")
    macro_live, sector_live, company_live, asof = build_live_frames(
        root, positioning, macro_features, sector_features, company_features
    )

    _write_progress(out, step=3, total=total_steps, stage="macro", message="Training walk-forward macro regime ensemble")
    macro = run_classification_layer(
        frames["macro"], macro_live,
        layer="macro",
        target_column="target_next_quadrant_3m",
        target_end_column="target_end_date_3m",
        feature_columns=macro_features,
        categorical=["dalio_quadrant"],
        splits=splits,
        meta_columns=["date", "dalio_quadrant"],
    )

    _write_progress(out, step=4, total=total_steps, stage="sector", message="Training walk-forward sector excess-return ensemble")
    sector = run_regression_layer(
        frames["sector"], sector_live,
        layer="sector",
        target_column="fwd_6m_excess",
        target_end_column="target_end_date_6m",
        feature_columns=sector_features,
        categorical=["sector", "dalio_quadrant", "last_cross_type"],
        splits=splits,
        meta_columns=["date", "sector", "sector_etf", "dalio_quadrant", "relative_oscillator", "above_slow_ma", "fast_slow_gap"],
        group_columns=["date"],
    )

    _write_progress(out, step=5, total=total_steps, stage="company", message="Training pooled company residual ensemble")
    company = run_regression_layer(
        frames["company"], company_live,
        layer="company",
        target_column="target_company_residual_6m",
        target_end_column="target_end_date_6m",
        feature_columns=company_features,
        categorical=[
            "book", "parent_sector", "company_50_200_state", "company_50_200_cross",
            "macro_dalio_quadrant", "parent_last_cross_type",
        ],
        splits=splits,
        meta_columns=[
            "date", "ticker", "book", "book_specification", "parent_sector", "quality_z", "n_metrics",
            "pit_member", "strict_pit_eligible", "company_50_200_state", "company_50_200_age_months",
            "company_sma50_200_gap", "company_relative_oscillator", "company_volatility_63d", "company_beta_252d",
        ],
        group_columns=["date", "book"],
        sample_weight_fn=_company_weights,
    )

    _write_progress(out, step=6, total=total_steps, stage="trend", message="Training 50/200 cross-survival ensemble")
    trend_panel = build_trend_panel(root, positioning)
    latest_events = trend_panel.sort_values("date").groupby("sector", as_index=False).tail(1).reset_index(drop=True)
    trend = run_classification_layer(
        trend_panel,
        latest_events,
        layer="trend",
        target_column="target_cross_survives",
        target_end_column="target_end_date_3m",
        feature_columns=_trend_features(trend_panel, positioning),
        categorical=["sector", "type", "dalio_quadrant"],
        splits=trend_splits(trend_panel),
        meta_columns=["date", "sector", "symbol", "type", "sma_gap"],
        positive_class="survives",
        asof_date=asof,
    )

    cftc_snapshot = _current_positioning_snapshot(positioning, asof)
    gamma = gamma_exposure(root)
    gamma_snapshot = (
        {"status": "available_live_only", "detail": "Live snapshot only; excluded from model training.", **gamma}
        if gamma
        else {"status": "unavailable_neutral", "detail": GEX_INSTRUCTIONS}
    )
    positioning_snapshot = {"asof": asof.strftime("%Y-%m-%d"), "cftc": cftc_snapshot, "gamma": gamma_snapshot}
    _write_progress(out, step=7, total=total_steps, stage="sizing", message="Applying confidence shrinkage, portfolio constraints, and execution costs")
    sizing = build_sizing_advisor(macro, sector, company, trend, cftc_snapshot, gamma)
    portfolio_signals, portfolio_targets = build_walkforward_portfolio_targets(
        macro, sector, company, trend, positioning
    )
    execution = load_binance_execution_costs(root / BINANCE_EXECUTION_CONFIG)
    portfolio_periods, portfolio_summary = simulate_rebalanced_portfolio(
        portfolio_targets,
        portfolio_signals["date"].tolist(),
        lambda symbol: load_close(root, symbol),
        execution,
    )
    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "asof": asof.strftime("%Y-%m-%d"),
        "holdout_start": HOLDOUT_START.strftime("%Y-%m-%d"),
        "models": MODEL_CONFIG,
        "layers": {
            "macro": {"features": len(macro.feature_columns), "validation_reliability": macro.validation_reliability, "trained_through": macro.trained_through.strftime("%Y-%m-%d")},
            "sector": {"features": len(sector.feature_columns), "validation_reliability": sector.validation_reliability, "trained_through": sector.trained_through.strftime("%Y-%m-%d")},
            "company": {"features": len(company.feature_columns), "validation_reliability": company.validation_reliability, "trained_through": company.trained_through.strftime("%Y-%m-%d")},
            "trend": {"features": len(trend.feature_columns), "validation_reliability": trend.validation_reliability, "trained_through": trend.trained_through.strftime("%Y-%m-%d")},
        },
        "cftc": {"included_in_training": True, "publication_aligned": True, "latest": cftc_snapshot},
        "gamma": {"included_in_training": False, "live_risk_overlay": True, "status": gamma_snapshot["status"]},
        "execution": portfolio_summary,
        "reliability_policy": {
            "regression": "mean of positive validation rank-IC and top-minus-bottom spread evidence, sampled at non-overlapping horizons",
            "company": "geometric mean of broad-universe and strict point-in-time regression reliability",
            "holdout_use": "reporting only; never used for model weighting, calibration, or sizing confidence",
        },
        "known_limitations": [
            "Company universe before November 2019 is not strict point-in-time constituent history.",
            "The dedicated semiconductor book overlaps XLK and is consolidated by a predeclared priority rule.",
            "Gamma has no historical point-in-time chain archive and is not a trained feature.",
            "Monthly six-month targets overlap; inference uses non-overlapping IC and spread samples.",
            "The portfolio replay uses adjusted underlying closes, not Binance mark prices; it remains research-only until venue symbols and historical funding are supplied.",
        ],
    }
    audit = build_model_audit(
        asof=asof,
        macro=macro,
        sector=sector,
        company=company,
        trend=trend,
        sizing=sizing,
        gamma=gamma,
    )
    failures = audit.loc[audit["status"].eq("FAIL")]
    if not failures.empty:
        _write_progress(out, step=7, total=total_steps, stage="audit", message="Final model audit failed", status="failed")
        raise ValueError("Final model audit failed:\n" + failures.to_string(index=False))
    governance["audit_status"] = audit["status"].value_counts().to_dict()
    result = FinalHierarchyResult(
        macro=macro,
        sector=sector,
        company=company,
        trend=trend,
        sizing=sizing,
        positioning_snapshot=positioning_snapshot,
        governance=governance,
        audit=audit,
        portfolio_signals=portfolio_signals,
        portfolio_targets=portfolio_targets,
        portfolio_periods=portfolio_periods,
        portfolio_summary=portfolio_summary,
        output_dir=out,
    )
    _write_progress(out, step=8, total=total_steps, stage="report", message="Writing final hierarchy dashboard and outputs")
    _write_outputs(result)
    _write_progress(out, step=8, total=total_steps, stage="complete", message="Final hierarchy complete", status="complete")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_final_hierarchy(args.project_root, output_dir=args.output_dir)
    print(f"Dashboard: {result.output_dir / 'index.html'}")
    print(result.sizing.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
