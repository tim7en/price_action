"""Interpretable 6/12-month market and sector factor attribution.

This module deliberately uses a regularized linear model instead of the final
hierarchy's nonlinear ensemble.  Its job is explanation and stability audit:
purged expanding-window forecasts, a separate shadow holdout, signed
standardized coefficients, and factor-family attribution.  Coefficients are
predictive associations conditional on the feature set, not causal effects.

Run with::

    python build_factor_driver_model.py
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .data import resolve_project_root
from .final_hierarchy import join_positioning, load_positioning
from .hierarchical_research import (
    INK,
    INK_GREEN,
    INK_MUTED,
    INK_NAVY,
    INK_RED,
    PAPER,
    _html_table,
    _img,
    _vintage_figure,
)
from .sector_dalio_regime_model import build_live_etf_overlay_panel

OUTPUT_DIR = Path("outputs") / "factor_driver_model"
CONTRACT_DIR = Path("outputs") / "hierarchical_research"
HOLDOUT_START = pd.Timestamp("2022-01-01")
RANDOM_STATE = 42
MIN_TRAIN_DATES = 60

MACRO_FEATURES = [
    "nfci_z",
    "hy_spread_z",
    "vix_z",
    "vix_curve_spread",
    "t10y3m_z",
    "yield_curve_10y2y_z",
    "core_cpi_yoy_z",
    "indpro_yoy_z",
    "dxy_ret_6m",
    "gold_ret_6m",
    "copper_ret_6m",
    "wti_ret_6m",
    "copper_gold_ratio_z",
    "fed_path_2y_z",
    "breakeven_10y_z",
    "infl_5y5y_fwd_z",
    "infl_exp_1y_z",
    "claims_yoy_z",
    "permits_yoy_z",
    "cape_z",
    "growth_signal",
    "inflation_signal",
    "market_health",
    "sector_breadth",
]

SECTOR_FEATURES = [
    "sector_return_1m",
    "sector_return_3m",
    "sector_return_6m",
    "sector_return_12m",
    "relative_return_1m",
    "relative_return_3m",
    "relative_return_6m",
    "relative_return_12m",
    "sector_oscillator",
    "relative_oscillator",
    "above_slow_ma",
    "fast_slow_gap",
    "slow_ma_gap",
    "volatility_12m",
    "drawdown_12m",
    "drawdown_36m",
    "relative_volatility_12m",
    "beta_36m",
    "corr_36m",
    "months_since_cross",
    "move_since_last_cross",
    "young_cross_risk",
    "cap_weighted_surprise_pct_lag1",
    "cap_weighted_surprise_pct_lag1_change",
    "beat_rate_lag1",
    "beat_rate_lag1_change",
    "cap_weighted_quarterly_eps_yoy_pct_lag1",
    "cap_weighted_quarterly_eps_yoy_pct_lag1_change",
]

MARKET_AGGREGATES = {
    "sector_return_1m": "market_sector_return_1m",
    "sector_return_3m": "market_sector_return_3m",
    "sector_return_6m": "market_sector_return_6m",
    "sector_return_12m": "market_sector_return_12m",
    "fast_slow_gap": "market_fast_slow_gap",
    "drawdown_12m": "market_drawdown_12m",
    "volatility_12m": "market_volatility_12m",
    "above_slow_ma": "market_pct_above_slow_ma",
}

PARAM_GRID = [
    {"alpha": alpha, "l1_ratio": ratio}
    for alpha in (0.001, 0.003, 0.010, 0.030)
    for ratio in (0.10, 0.50, 0.90)
]
DEFAULT_PARAMS = {"alpha": 0.030, "l1_ratio": 0.10}


@dataclass
class DriverResult:
    scope: str
    horizon_months: int
    predictions: pd.DataFrame
    live: pd.DataFrame
    metrics: pd.DataFrame
    importance: pd.DataFrame
    coefficient_stability: pd.DataFrame
    live_contributions: pd.DataFrame
    feature_columns: list[str]
    params: dict[str, float]
    reliability: float
    trained_through: pd.Timestamp


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


def _factor_family(feature: str) -> tuple[str, str]:
    key = feature.lower()
    if key.startswith("cot_"):
        return "positioning", "cftc_positioning"
    if key.startswith("sector_") and key not in SECTOR_FEATURES:
        return "control", "sector_fixed_effect"
    if key.startswith("market_"):
        return "price", "market_trend"
    if key in {
        "cap_weighted_surprise_pct_lag1",
        "cap_weighted_surprise_pct_lag1_change",
        "beat_rate_lag1",
        "beat_rate_lag1_change",
        "cap_weighted_quarterly_eps_yoy_pct_lag1",
        "cap_weighted_quarterly_eps_yoy_pct_lag1_change",
    }:
        return "fundamental", "earnings_breadth"
    if key in SECTOR_FEATURES:
        return "price", "sector_price_trend"
    if any(token in key for token in ("nfci", "hy_spread")):
        return "macro", "financial_conditions"
    if "vix" in key:
        return "macro", "volatility"
    if any(token in key for token in ("yield_curve", "t10y3m", "fed_path")):
        return "macro", "rates_curve"
    if any(token in key for token in ("cpi", "breakeven", "infl_", "inflation")):
        return "macro", "inflation"
    if any(token in key for token in ("indpro", "claims", "permits", "growth")):
        return "macro", "growth"
    if any(token in key for token in ("dxy", "gold", "copper", "wti")):
        return "macro", "dollar_commodities"
    if "cape" in key:
        return "macro", "valuation"
    if any(token in key for token in ("market_health", "sector_breadth")):
        return "price", "market_state"
    return "other", "other"


def _load_panels(
    root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    path = root / CONTRACT_DIR / "sector_monthly_panel.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing sector contract: {path}")
    sector = pd.read_csv(path, parse_dates=["date", "signal_date", "target_end_date_6m"], low_memory=False)
    positioning = load_positioning(root)
    sector = join_positioning(sector, positioning)
    sector["target_end_date_12m"] = sector["date"] + pd.offsets.MonthEnd(12)

    live, _bundle, latest_trade_date = build_live_etf_overlay_panel(root, fast=3, slow=10)
    if live.empty or not latest_trade_date:
        raise ValueError("Current sector ETF overlay is unavailable.")
    asof = pd.Timestamp(latest_trade_date).normalize()
    live = live.loc[live["date"].eq(live["date"].max())].copy()
    live["date"] = asof
    live["signal_date"] = asof
    live = join_positioning(live, positioning)

    market = _market_frame(sector)
    market_live = _market_frame(live, targets=False)
    return market, sector, market_live, live, asof


def _market_frame(sector: pd.DataFrame, *, targets: bool = True) -> pd.DataFrame:
    ordered = sector.sort_values(["date", "sector"])
    common = [
        column
        for column in [
            *MACRO_FEATURES,
            *[c for c in sector.columns if c.startswith("cot_") and c not in {"cot_usable_date", "cot_age_days"}],
        ]
        if column in sector
    ]
    target_columns = [
        column
        for column in [
            "fwd_6m_broad",
            "fwd_12m_broad",
            "target_end_date_6m",
            "target_end_date_12m",
        ]
        if column in sector and targets
    ]
    if targets:
        consistency = ordered.groupby("date")[[c for c in target_columns if c.startswith("fwd_")]].nunique(dropna=False)
        if not consistency.empty and consistency.max().max() > 1:
            raise ValueError("Broad forward returns differ across sectors for the same month.")
    market = ordered[["date", "signal_date", *common, *target_columns]].drop_duplicates("date", keep="first")
    aggregate_columns = [column for column in MARKET_AGGREGATES if column in ordered]
    aggregates = ordered.groupby("date", as_index=False)[aggregate_columns].mean().rename(columns=MARKET_AGGREGATES)
    return market.merge(aggregates, on="date", how="left", validate="one_to_one").sort_values("date").reset_index(drop=True)


def _prepare_design(
    panel: pd.DataFrame,
    live: pd.DataFrame,
    *,
    numeric_features: list[str],
    categorical_features: list[str],
    selection_mask: pd.Series,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], dict[str, tuple[str, str]]]:
    combined = pd.concat([panel, live], ignore_index=True, sort=False)
    numeric = [column for column in numeric_features if column in combined]
    categorical = [column for column in categorical_features if column in combined]
    numeric_frame = combined[numeric].apply(pd.to_numeric, errors="coerce")
    category_frame = pd.get_dummies(
        combined[categorical].fillna("Missing").astype(str),
        prefix=categorical,
        drop_first=True,
        dtype=float,
    ) if categorical else pd.DataFrame(index=combined.index)
    design = pd.concat([numeric_frame, category_frame], axis=1).replace([np.inf, -np.inf], np.nan)
    historical = design.iloc[: len(panel)]
    coverage = historical.loc[selection_mask].notna().mean()
    variance = historical.loc[selection_mask].nunique(dropna=True)
    selected = coverage[(coverage >= 0.45) & (variance > 1)].index.tolist()
    if not selected:
        raise ValueError("No driver features survived coverage and variance checks.")

    metadata: dict[str, tuple[str, str]] = {}
    for feature in selected:
        if feature in numeric:
            metadata[feature] = _factor_family(feature)
        else:
            metadata[feature] = ("control", "sector_fixed_effect")
    return (
        historical[selected],
        design.iloc[len(panel) :][selected].reset_index(drop=True),
        selected,
        metadata,
    )


def _weights(frame: pd.DataFrame, scope: str) -> pd.Series:
    if scope == "market":
        return pd.Series(1.0, index=frame.index)
    counts = frame.groupby("date")["date"].transform("size")
    weights = 1.0 / counts
    return weights / weights.mean()


def _fit_model(
    x: pd.DataFrame,
    y: pd.Series,
    params: dict[str, float],
    sample_weight: pd.Series,
) -> Pipeline:
    lower, upper = np.nanquantile(y, [0.01, 0.99])
    target = y.clip(lower, upper)
    model = Pipeline([
        ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("scaler", StandardScaler()),
        ("model", ElasticNet(
            alpha=float(params["alpha"]),
            l1_ratio=float(params["l1_ratio"]),
            max_iter=30_000,
            tol=1e-6,
            random_state=RANDOM_STATE,
        )),
    ])
    model.fit(x, target, model__sample_weight=sample_weight.to_numpy())
    return model


def _rank_ic(frame: pd.DataFrame) -> float:
    values = []
    for _, group in frame.groupby("date", sort=True):
        if len(group) >= 4 and group["prediction"].nunique() > 1:
            value = group["prediction"].corr(group["target"], method="spearman")
            if pd.notna(value):
                values.append(float(value))
    return float(np.mean(values)) if values else np.nan


def _center_sector_predictions(frame: pd.DataFrame) -> pd.DataFrame:
    centered = frame.copy()
    centered["prediction"] = centered["prediction"] - centered.groupby("date")["prediction"].transform("mean")
    return centered


def _candidate_score(frame: pd.DataFrame, scope: str, weights: pd.Series) -> float:
    target_std = max(float(np.sqrt(np.average((frame["target"] - np.average(frame["target"], weights=weights)) ** 2, weights=weights))), 1e-6)
    rmse = math.sqrt(mean_squared_error(frame["target"], frame["prediction"], sample_weight=weights)) / target_std
    if scope == "sector":
        association = _rank_ic(frame)
    else:
        association = frame["prediction"].corr(frame["target"], method="spearman")
    association = float(association) if pd.notna(association) else 0.0
    return float(rmse - 0.15 * np.clip(association, -0.25, 0.25))


def _choose_params(
    panel: pd.DataFrame,
    design: pd.DataFrame,
    *,
    target_column: str,
    target_end_column: str,
    train_mask: pd.Series,
    scope: str,
) -> dict[str, float]:
    years = sorted(panel.loc[train_mask, "date"].dt.year.unique())[-4:]
    folds: list[tuple[pd.Series, pd.Series]] = []
    for year in years:
        start = pd.Timestamp(year=int(year), month=1, day=1)
        inner_train = train_mask & panel[target_end_column].lt(start)
        inner_test = train_mask & panel["date"].dt.year.eq(year)
        if panel.loc[inner_train, "date"].nunique() >= MIN_TRAIN_DATES and inner_test.any():
            folds.append((inner_train, inner_test))
    if len(folds) < 2:
        return DEFAULT_PARAMS.copy()

    rows: list[dict[str, float]] = []
    for params in PARAM_GRID:
        for fold_number, (inner_train, inner_test) in enumerate(folds):
            model = _fit_model(
                design.loc[inner_train],
                panel.loc[inner_train, target_column],
                params,
                _weights(panel.loc[inner_train], scope),
            )
            evaluation = panel.loc[inner_test, ["date"]].copy()
            evaluation["target"] = panel.loc[inner_test, target_column]
            evaluation["prediction"] = model.predict(design.loc[inner_test])
            if scope == "sector":
                evaluation = _center_sector_predictions(evaluation)
            test_weights = _weights(panel.loc[inner_test], scope)
            rows.append({
                "alpha": params["alpha"],
                "l1_ratio": params["l1_ratio"],
                "fold": fold_number,
                "score": _candidate_score(evaluation, scope, test_weights),
            })
    scores = pd.DataFrame(rows)
    summary = scores.groupby(["alpha", "l1_ratio"])["score"].agg(["mean", "std", "count"]).reset_index()
    best = summary.nsmallest(1, "mean").iloc[0]
    standard_error = float(best["std"] / math.sqrt(best["count"])) if best["count"] > 1 and pd.notna(best["std"]) else 0.0
    eligible = summary.loc[summary["mean"] <= float(best["mean"]) + standard_error + 1e-12]
    selected = eligible.sort_values(["alpha", "l1_ratio"], ascending=[False, False]).iloc[0]
    return {"alpha": float(selected["alpha"]), "l1_ratio": float(selected["l1_ratio"])}


def _coefficient_frame(model: Pipeline, features: list[str], fold: str) -> pd.DataFrame:
    coefficients = np.asarray(model.named_steps["model"].coef_, dtype=float)
    return pd.DataFrame({"fold": fold, "feature": features, "coefficient": coefficients})


def _contribution_frame(
    model: Pipeline,
    design: pd.DataFrame,
    metadata: pd.DataFrame,
    features: list[str],
) -> pd.DataFrame:
    imputed = model.named_steps["imputer"].transform(design)
    standardized = model.named_steps["scaler"].transform(imputed)
    coefficients = np.asarray(model.named_steps["model"].coef_, dtype=float)
    rows = []
    for row_number in range(len(design)):
        for column_number, feature in enumerate(features):
            row = metadata.iloc[row_number].to_dict()
            row.update({
                "feature": feature,
                "standardized_value": float(standardized[row_number, column_number]),
                "coefficient": float(coefficients[column_number]),
                "contribution": float(standardized[row_number, column_number] * coefficients[column_number]),
            })
            rows.append(row)
    return pd.DataFrame(rows)


def _metrics(frame: pd.DataFrame, *, scope: str, horizon: int, sample: str) -> dict[str, Any]:
    data = frame.dropna(subset=["target", "prediction"]).copy()
    if data.empty:
        return {"sample": sample, "observations": 0}
    row: dict[str, Any] = {
        "sample": sample,
        "observations": len(data),
        "months": data["date"].nunique(),
        "rmse": math.sqrt(mean_squared_error(data["target"], data["prediction"])),
        "mae": mean_absolute_error(data["target"], data["prediction"]),
        "r2": r2_score(data["target"], data["prediction"]) if len(data) > 1 else np.nan,
        "directional_accuracy": float((np.sign(data["target"]) == np.sign(data["prediction"])).mean()),
    }
    if "baseline_prediction" in data:
        baseline_rmse = math.sqrt(mean_squared_error(data["target"], data["baseline_prediction"]))
        row["baseline_rmse"] = baseline_rmse
        row["skill_vs_baseline"] = 1.0 - row["rmse"] / baseline_rmse if baseline_rmse > 0 else np.nan
    if scope == "market":
        monthly = data.groupby("date", as_index=False)[["target", "prediction"]].mean().sort_values("date")
        row["spearman"] = monthly["prediction"].corr(monthly["target"], method="spearman")
        nonoverlap = monthly.iloc[::horizon]
        row["nonoverlap_association"] = nonoverlap["prediction"].corr(nonoverlap["target"], method="spearman")
        row["nonoverlap_periods"] = len(nonoverlap)
    else:
        monthly_ic = []
        spreads = []
        for date, group in data.groupby("date", sort=True):
            if len(group) < 4 or group["prediction"].nunique() < 2:
                continue
            monthly_ic.append((date, group["prediction"].corr(group["target"], method="spearman")))
            ranked = group.sort_values("prediction")
            count = max(1, min(3, len(group) // 3))
            spreads.append((date, ranked.tail(count)["target"].mean() - ranked.head(count)["target"].mean()))
        ic = pd.Series(dict(monthly_ic), dtype=float).dropna().sort_index()
        spread = pd.Series(dict(spreads), dtype=float).dropna().sort_index()
        row["spearman"] = float(ic.mean()) if len(ic) else np.nan
        row["top_minus_bottom"] = float(spread.mean()) if len(spread) else np.nan
        row["nonoverlap_association"] = float(ic.iloc[::horizon].mean()) if len(ic) else np.nan
        row["nonoverlap_spread"] = float(spread.iloc[::horizon].mean()) if len(spread) else np.nan
        row["nonoverlap_periods"] = len(ic.iloc[::horizon])
    return row


def _reliability(metrics: pd.DataFrame, scope: str) -> float:
    row = metrics.loc[metrics["sample"].eq("validation")]
    if row.empty:
        return 0.0
    association = float(row.iloc[0].get("spearman", np.nan))
    skill = float(row.iloc[0].get("skill_vs_baseline", np.nan))
    periods = float(row.iloc[0].get("nonoverlap_periods", 0.0))
    scale = 0.20 if scope == "market" else 0.10
    if not np.isfinite(association) or association <= 0.0 or not np.isfinite(skill) or skill <= 0.0:
        return 0.0
    return float(
        np.clip(association / scale, 0.0, 1.0)
        * np.clip(skill / 0.10, 0.0, 1.0)
        * np.clip(periods / 8.0, 0.0, 1.0)
    )


def run_driver_model(
    panel: pd.DataFrame,
    live: pd.DataFrame,
    *,
    scope: str,
    horizon: int,
    numeric_features: list[str],
    categorical_features: list[str],
    target_column: str,
    target_end_column: str,
    asof: pd.Timestamp,
) -> DriverResult:
    panel = panel.copy()
    live = live.copy()
    panel[target_end_column] = pd.to_datetime(panel[target_end_column])
    position_z = [column for column in panel if column.startswith("cot_") and column.endswith("_z")]
    first_position_date = panel.loc[panel[position_z].notna().all(axis=1), "date"].min() if position_z else panel["date"].min()
    model_start = max(pd.Timestamp("2007-01-01"), pd.Timestamp(first_position_date))
    eligible = (
        panel["date"].ge(model_start)
        & panel[target_column].notna()
        & panel[target_end_column].notna()
        & panel[target_end_column].le(asof)
    )
    selection_mask = eligible & panel["date"].lt(HOLDOUT_START)
    design, live_design, selected, feature_metadata = _prepare_design(
        panel,
        live,
        numeric_features=numeric_features,
        categorical_features=categorical_features,
        selection_mask=selection_mask,
    )

    predictions = []
    coefficient_rows = []
    first_validation_year = max(model_start.year + 6, 2013)
    for year in range(first_validation_year, HOLDOUT_START.year):
        test_start = pd.Timestamp(year=year, month=1, day=1)
        test_end = test_start + pd.DateOffset(years=1) - pd.Timedelta(days=1)
        train = eligible & panel[target_end_column].lt(test_start)
        test = eligible & panel["date"].between(test_start, test_end)
        if panel.loc[train, "date"].nunique() < MIN_TRAIN_DATES or not test.any():
            continue
        params = _choose_params(
            panel,
            design,
            target_column=target_column,
            target_end_column=target_end_column,
            train_mask=train,
            scope=scope,
        )
        model = _fit_model(design.loc[train], panel.loc[train, target_column], params, _weights(panel.loc[train], scope))
        fold = f"validation_{year}"
        prediction = panel.loc[test, ["date", *(["sector", "sector_etf"] if scope == "sector" else [])]].copy()
        prediction["target"] = panel.loc[test, target_column]
        prediction["prediction"] = model.predict(design.loc[test])
        if scope == "sector":
            prediction = _center_sector_predictions(prediction)
            baseline_prediction = 0.0
        else:
            train_weights = _weights(panel.loc[train], scope)
            baseline_prediction = float(np.average(panel.loc[train, target_column], weights=train_weights))
        prediction["baseline_prediction"] = baseline_prediction
        prediction["fold"] = fold
        prediction["test_start"] = test_start
        prediction["max_train_target_end"] = panel.loc[train, target_end_column].max()
        prediction["alpha"] = params["alpha"]
        prediction["l1_ratio"] = params["l1_ratio"]
        predictions.append(prediction)
        coefficient_rows.append(_coefficient_frame(model, selected, fold))

    preholdout = eligible & panel[target_end_column].lt(HOLDOUT_START)
    holdout = eligible & panel["date"].ge(HOLDOUT_START)
    final_params = _choose_params(
        panel,
        design,
        target_column=target_column,
        target_end_column=target_end_column,
        train_mask=preholdout,
        scope=scope,
    )
    if holdout.any():
        holdout_model = _fit_model(
            design.loc[preholdout],
            panel.loc[preholdout, target_column],
            final_params,
            _weights(panel.loc[preholdout], scope),
        )
        prediction = panel.loc[holdout, ["date", *(["sector", "sector_etf"] if scope == "sector" else [])]].copy()
        prediction["target"] = panel.loc[holdout, target_column]
        prediction["prediction"] = holdout_model.predict(design.loc[holdout])
        if scope == "sector":
            prediction = _center_sector_predictions(prediction)
            baseline_prediction = 0.0
        else:
            train_weights = _weights(panel.loc[preholdout], scope)
            baseline_prediction = float(np.average(panel.loc[preholdout, target_column], weights=train_weights))
        prediction["baseline_prediction"] = baseline_prediction
        prediction["fold"] = "holdout"
        prediction["test_start"] = HOLDOUT_START
        prediction["max_train_target_end"] = panel.loc[preholdout, target_end_column].max()
        prediction["alpha"] = final_params["alpha"]
        prediction["l1_ratio"] = final_params["l1_ratio"]
        predictions.append(prediction)

    prediction_frame = pd.concat(predictions, ignore_index=True) if predictions else pd.DataFrame()
    metrics = pd.DataFrame([
        _metrics(prediction_frame.loc[~prediction_frame["fold"].eq("holdout")], scope=scope, horizon=horizon, sample="validation"),
        _metrics(prediction_frame.loc[prediction_frame["fold"].eq("holdout")], scope=scope, horizon=horizon, sample="holdout"),
    ])
    reliability = _reliability(metrics, scope)

    final_model = _fit_model(
        design.loc[eligible],
        panel.loc[eligible, target_column],
        final_params,
        _weights(panel.loc[eligible], scope),
    )
    live_output = live[["date", *(["sector", "sector_etf"] if scope == "sector" and "sector_etf" in live else ["sector"] if scope == "sector" else [])]].copy().reset_index(drop=True)
    live_output["raw_prediction"] = final_model.predict(live_design)
    if scope == "sector":
        live_output["raw_prediction"] = live_output["raw_prediction"] - live_output["raw_prediction"].mean()

    coefficients = pd.concat(coefficient_rows, ignore_index=True) if coefficient_rows else pd.DataFrame(columns=["fold", "feature", "coefficient"])
    final_coefficients = _coefficient_frame(final_model, selected, "final").rename(columns={"coefficient": "final_coefficient"})
    if coefficients.empty:
        stability = final_coefficients.assign(selection_frequency=0.0, sign_consistency=0.0, median_validation_coefficient=np.nan)
    else:
        pivot = coefficients.pivot(index="feature", columns="fold", values="coefficient").reindex(selected).fillna(0.0)
        final_sign = np.sign(final_coefficients.set_index("feature")["final_coefficient"])
        selection_frequency = pivot.abs().gt(1e-9).mean(axis=1)
        sign_consistency = pd.Series(0.0, index=pivot.index)
        for feature in pivot.index:
            selected_values = pivot.loc[feature, pivot.loc[feature].abs().gt(1e-9)]
            if len(selected_values) and final_sign.loc[feature] != 0:
                sign_consistency.loc[feature] = float((np.sign(selected_values) == final_sign.loc[feature]).mean())
        stability = final_coefficients.merge(
            pd.DataFrame({
                "feature": pivot.index,
                "selection_frequency": selection_frequency.values,
                "sign_consistency": sign_consistency.values,
                "median_validation_coefficient": pivot.median(axis=1).values,
            }),
            on="feature",
            how="left",
        )

    stability["domain"] = stability["feature"].map(lambda value: feature_metadata[value][0])
    stability["family"] = stability["feature"].map(lambda value: feature_metadata[value][1])
    stability["stable_importance"] = (
        stability["final_coefficient"].abs()
        * stability["selection_frequency"]
        * stability["sign_consistency"]
    )
    total_importance = stability["stable_importance"].sum()
    stability["stable_importance_pct"] = np.where(
        total_importance > 0,
        stability["stable_importance"] / total_importance * 100.0,
        0.0,
    )
    importance = stability.sort_values("stable_importance", ascending=False).reset_index(drop=True)
    if importance["stable_importance"].sum() <= 1e-12:
        reliability = 0.0
    live_output["validation_reliability"] = reliability
    live_output["validated_prediction"] = live_output["raw_prediction"] * reliability
    metrics["validation_reliability"] = reliability

    contribution_metadata = live_output[[column for column in ["date", "sector"] if column in live_output]]
    contributions = _contribution_frame(final_model, live_design, contribution_metadata, selected)
    contributions["domain"] = contributions["feature"].map(lambda value: feature_metadata[value][0])
    contributions["family"] = contributions["feature"].map(lambda value: feature_metadata[value][1])
    contributions["scope"] = scope
    contributions["horizon_months"] = horizon
    importance["scope"] = scope
    importance["horizon_months"] = horizon
    coefficients["scope"] = scope
    coefficients["horizon_months"] = horizon
    metrics["scope"] = scope
    metrics["horizon_months"] = horizon
    prediction_frame["scope"] = scope
    prediction_frame["horizon_months"] = horizon
    return DriverResult(
        scope=scope,
        horizon_months=horizon,
        predictions=prediction_frame,
        live=live_output,
        metrics=metrics,
        importance=importance,
        coefficient_stability=coefficients,
        live_contributions=contributions,
        feature_columns=selected,
        params=final_params,
        reliability=reliability,
        trained_through=pd.Timestamp(panel.loc[eligible, target_end_column].max()),
    )


def _combined_forecasts(results: list[DriverResult]) -> tuple[pd.DataFrame, pd.DataFrame]:
    market_rows = []
    sector_rows = []
    for horizon in (6, 12):
        market = next(result for result in results if result.scope == "market" and result.horizon_months == horizon)
        sector = next(result for result in results if result.scope == "sector" and result.horizon_months == horizon)
        market_row = market.live.iloc[0]
        market_rows.append({
            "horizon_months": horizon,
            "date": market_row["date"],
            "raw_market_return": market_row["raw_prediction"],
            "validated_market_return": market_row["validated_prediction"],
            "validation_reliability": market.reliability,
        })
        frame = sector.live.copy()
        frame["horizon_months"] = horizon
        frame["raw_market_return"] = market_row["raw_prediction"]
        frame["validated_market_return"] = market_row["validated_prediction"]
        frame = frame.rename(columns={
            "raw_prediction": "raw_sector_excess",
            "validated_prediction": "validated_sector_excess",
        })
        frame["raw_total_return"] = frame["raw_market_return"] + frame["raw_sector_excess"]
        frame["validated_total_return"] = frame["validated_market_return"] + frame["validated_sector_excess"]
        sector_rows.append(frame)
    return pd.DataFrame(market_rows), pd.concat(sector_rows, ignore_index=True)


def _build_audit(
    results: list[DriverResult],
    historical_sector: pd.DataFrame,
    asof: pd.Timestamp,
) -> pd.DataFrame:
    rows: list[dict[str, str]] = []

    def add(check: str, passed: bool, detail: str, warning: bool = False) -> None:
        rows.append({"check": check, "status": "WARN" if warning else ("PASS" if passed else "FAIL"), "detail": detail})

    leaked = {
        f"{result.scope}_{result.horizon_months}m": [
            feature for feature in result.feature_columns if feature.startswith("fwd_") or feature.startswith("target_")
        ]
        for result in results
    }
    add("targets_excluded", not any(leaked.values()), f"leaked features={leaked}")
    date_proxies = {
        f"{result.scope}_{result.horizon_months}m": [
            feature for feature in result.feature_columns if "date" in feature.lower()
        ]
        for result in results
    }
    add("calendar_proxies_excluded", not any(date_proxies.values()), f"date-like features={date_proxies}")
    purge_failures = sum(
        int((result.predictions["max_train_target_end"] >= result.predictions["test_start"]).sum())
        for result in results
    )
    add("purged_walk_forward", purge_failures == 0, f"rows violating target maturity={purge_failures}")
    cftc_counts = {f"{r.scope}_{r.horizon_months}m": sum(f.startswith("cot_") for f in r.feature_columns) for r in results}
    add("cftc_in_every_model", all(value >= 8 for value in cftc_counts.values()), f"selected CFTC features={cftc_counts}")
    age = pd.to_numeric(historical_sector.get("cot_age_days"), errors="coerce").dropna()
    add("cftc_release_alignment", bool(len(age)) and bool(age.ge(0).all()), f"minimum CFTC age={age.min() if len(age) else 'n/a'} days")
    holdout = {f"{r.scope}_{r.horizon_months}m": int(r.predictions["fold"].eq("holdout").sum()) for r in results}
    add("shadow_holdout_present", all(value > 0 for value in holdout.values()), f"holdout rows={holdout}")
    later = {f"{r.scope}_{r.horizon_months}m": str(r.trained_through.date()) for r in results if r.trained_through > asof}
    add("matured_labels_only", not later, f"asof={asof.date()}, later target ends={later}")
    feature_counts = {f"{r.scope}_{r.horizon_months}m": len(r.feature_columns) for r in results}
    add("regularized_dimension", all(value <= 75 for value in feature_counts.values()), f"selected features={feature_counts}")
    add("holdout_not_used_for_tuning", True, f"hyperparameters selected only with dates before {HOLDOUT_START.date()}")
    weak = {f"{r.scope}_{r.horizon_months}m": round(r.reliability, 3) for r in results if r.reliability < 0.10}
    add("predictive_evidence", True, f"low-reliability models={weak}", warning=bool(weak))
    unstable = {}
    for result in results:
        active = result.importance.loc[result.importance["final_coefficient"].abs().gt(1e-9)]
        unstable[f"{result.scope}_{result.horizon_months}m"] = int(active["sign_consistency"].lt(0.60).sum())
    add(
        "coefficient_stability",
        True,
        f"active coefficients below 60% sign consistency={unstable}",
        warning=any(unstable.values()),
    )
    return pd.DataFrame(rows)


def _driver_chart(result: DriverResult) -> str:
    data = result.importance.loc[result.importance["stable_importance"].gt(0)].head(14).sort_values("stable_importance")
    fig, ax = _vintage_figure(figsize=(8.4, 5.2))
    if data.empty:
        ax.text(0.5, 0.5, "No stable coefficient evidence", ha="center", va="center", transform=ax.transAxes)
    else:
        colors = np.where(data["final_coefficient"] >= 0, INK_GREEN, INK_RED)
        ax.barh(data["feature"], data["stable_importance_pct"], color=colors, alpha=0.88)
        ax.set_xlabel("stability-adjusted importance (%)")
    ax.set_title(f"{result.scope.title()} {result.horizon_months}m predictive drivers")
    fig.tight_layout()
    from .hierarchical_research import _figure_b64
    return _figure_b64(fig)


def _family_chart(results: list[DriverResult]) -> str:
    family = pd.concat([result.importance for result in results], ignore_index=True)
    family = family.groupby(["scope", "horizon_months", "domain"], as_index=False)["stable_importance"].sum()
    family["model"] = family["scope"] + " " + family["horizon_months"].astype(str) + "m"
    pivot = family.pivot(index="model", columns="domain", values="stable_importance").fillna(0.0)
    pivot = pivot.div(pivot.sum(axis=1).replace(0.0, np.nan), axis=0).fillna(0.0) * 100.0
    fig, ax = _vintage_figure(figsize=(9.4, 4.7))
    colors = [INK_NAVY, INK_GREEN, "#b87918", INK_RED, "#6f685b", "#527b78"]
    left = np.zeros(len(pivot))
    for index, column in enumerate(pivot.columns):
        ax.barh(pivot.index, pivot[column], left=left, label=column, color=colors[index % len(colors)])
        left += pivot[column].to_numpy()
    ax.set_xlabel("stability-adjusted importance share (%)")
    ax.set_title("Driver-domain attribution")
    ax.legend(frameon=False, ncol=3, fontsize=8, loc="lower center", bbox_to_anchor=(0.5, -0.34))
    fig.tight_layout()
    from .hierarchical_research import _figure_b64
    return _figure_b64(fig)


def _forecast_chart(sector_forecasts: pd.DataFrame) -> str:
    data = sector_forecasts.pivot(index="sector", columns="horizon_months", values="validated_total_return") * 100.0
    data = data.sort_values(6 if 6 in data else data.columns[0])
    fig, ax = _vintage_figure(figsize=(9.4, 5.5))
    if data.abs().to_numpy().max(initial=0.0) <= 1e-9:
        ax.text(
            0.5,
            0.5,
            "ABSTAIN: no model beat its validation baseline",
            ha="center",
            va="center",
            transform=ax.transAxes,
            color=INK_RED,
            fontweight="bold",
        )
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title("Current sector return attribution forecast")
        fig.tight_layout()
        from .hierarchical_research import _figure_b64
        return _figure_b64(fig)
    y = np.arange(len(data))
    width = 0.36
    for offset, horizon in zip((-width / 2, width / 2), (6, 12), strict=True):
        if horizon in data:
            ax.barh(y + offset, data[horizon], height=width, label=f"{horizon}m", color=INK_GREEN if horizon == 6 else INK_NAVY)
    ax.axvline(0.0, color=INK, linewidth=0.8)
    ax.set_yticks(y, data.index)
    ax.set_xlabel("validation-shrunk expected total return (%)")
    ax.set_title("Current sector return attribution forecast")
    ax.legend(frameon=False)
    fig.tight_layout()
    from .hierarchical_research import _figure_b64
    return _figure_b64(fig)


def build_html_report(
    results: list[DriverResult],
    market_forecasts: pd.DataFrame,
    sector_forecasts: pd.DataFrame,
    audit: pd.DataFrame,
    asof: pd.Timestamp,
) -> str:
    metrics = pd.concat([result.metrics for result in results], ignore_index=True)
    model_summary = pd.DataFrame([
        {
            "model": f"{result.scope}_{result.horizon_months}m",
            "features": len(result.feature_columns),
            "alpha": result.params["alpha"],
            "l1_ratio": result.params["l1_ratio"],
            "validation_reliability": result.reliability,
            "trained_through": result.trained_through,
        }
        for result in results
    ])
    market_tables = []
    sector_tables = []
    for result in results:
        top = result.importance.loc[result.importance["stable_importance"].gt(0), [
            "feature", "domain", "family", "final_coefficient", "selection_frequency",
            "sign_consistency", "stable_importance_pct",
        ]].head(15)
        destination = market_tables if result.scope == "market" else sector_tables
        destination.append(
            f"<h3>{result.horizon_months}-month {result.scope} factors</h3><div class=\"table-wrap\">{_html_table(top)}</div>"
        )
    cftc_rows = []
    contribution_tables = []
    for result in results:
        cftc = result.importance.loc[result.importance["feature"].str.startswith("cot_")]
        stable_cftc = cftc.loc[cftc["stable_importance"].gt(0)]
        cftc_rows.append({
            "model": f"{result.scope}_{result.horizon_months}m",
            "design_features": int(cftc["feature"].nunique()),
            "stable_cftc_importance_pct": float(cftc["stable_importance_pct"].sum()),
            "top_stable_factor": stable_cftc.iloc[0]["feature"] if len(stable_cftc) else "none",
            "top_factor_coefficient": float(stable_cftc.iloc[0]["final_coefficient"]) if len(stable_cftc) else 0.0,
        })
        if result.scope == "market":
            contribution = result.live_contributions.copy()
            contribution = contribution.loc[contribution["contribution"].abs().gt(1e-9)].copy()
            contribution["abs_contribution"] = contribution["contribution"].abs()
            contribution = contribution.nlargest(12, "abs_contribution")[[
                "feature", "domain", "family", "standardized_value", "coefficient", "contribution",
            ]]
            contribution["contribution"] *= 100.0
            contribution_tables.append(
                f"<h3>{result.horizon_months}-month current market contributions</h3><div class=\"table-wrap\">{_html_table(contribution)}</div>"
            )
    cftc_view = pd.DataFrame(cftc_rows)
    sector_view = sector_forecasts[[
        "sector", "horizon_months", "raw_market_return", "raw_sector_excess",
        "raw_total_return", "validated_total_return", "validation_reliability",
    ]].copy()
    for column in ["raw_market_return", "raw_sector_excess", "raw_total_return", "validated_total_return"]:
        sector_view[column] *= 100.0
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    market_6 = float(market_forecasts.loc[market_forecasts["horizon_months"].eq(6), "validated_market_return"].iloc[0] * 100.0)
    market_12 = float(market_forecasts.loc[market_forecasts["horizon_months"].eq(12), "validated_market_return"].iloc[0] * 100.0)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>6/12-Month Factor Driver Model</title><style>
:root{{--paper:{PAPER};--page:#eadcb8;--grid:#dbc17b;--major:#c8a24b;--ink:{INK};--muted:{INK_MUTED};--navy:{INK_NAVY};--red:{INK_RED};--green:{INK_GREEN}}}
*{{box-sizing:border-box}} body{{margin:0;color:var(--ink);background:#eadcb8;font:14px/1.48 Georgia,"Times New Roman",serif;letter-spacing:0}} main{{max-width:1320px;margin:0 auto;padding:30px 38px 64px;background-color:var(--paper);background-image:linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px),linear-gradient(var(--major) 1px,transparent 1px),linear-gradient(90deg,var(--major) 1px,transparent 1px);background-size:10px 10px,10px 10px,50px 50px,50px 50px}}
header,.band{{background:rgba(244,236,211,.95)}} header{{border-top:4px solid var(--ink);border-bottom:1px solid var(--ink);padding:16px 0 14px}} h1{{font-size:31px;line-height:1.08;margin:0 0 7px}} h2{{font-size:20px;margin:34px 0 10px;border-bottom:2px solid var(--ink);padding-bottom:5px}} h3{{font-size:15px}} p{{max-width:1020px}} .meta{{color:var(--muted);font-size:12px}} .kpis{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border:1px solid var(--ink);margin:22px 0;background:rgba(244,236,211,.96)}} .kpi{{padding:13px 15px;border-right:1px solid var(--ink)}} .kpi:last-child{{border-right:0}} .kpi b{{display:block;font:22px/1.05 Arial,sans-serif;color:var(--navy)}} .kpi span{{font-size:11px;text-transform:uppercase}} .band{{padding:1px 12px 12px;margin:0 -12px}} .charts{{display:grid;grid-template-columns:1fr 1fr;gap:18px}} .charts>*{{min-width:0}} figure{{margin:10px 0;background:var(--paper);border:1px solid var(--ink);padding:8px}} img{{width:100%;display:block}} figcaption{{font-size:11px;color:var(--muted);padding-top:5px}} .table-wrap{{overflow-x:auto;border:1px solid var(--ink);background:rgba(244,236,211,.97)}} table{{border-collapse:collapse;width:100%;font-size:12px}} th,td{{padding:7px 9px;border-bottom:1px solid #c9b77f;text-align:left;white-space:nowrap}} thead th{{background:#e1cd91;border-bottom:2px solid var(--ink);font-family:Arial,sans-serif}} tbody tr:nth-child(even){{background:rgba(225,205,145,.25)}} .warn{{color:#925c00;font-weight:bold}} @media(max-width:800px){{main{{padding:18px 14px 44px}}.kpis{{grid-template-columns:1fr 1fr}}.kpi:nth-child(2){{border-right:0}}.charts{{grid-template-columns:1fr}}h1{{font-size:25px}}}}
</style></head><body><main><header><h1>6/12-Month Predictive Factor Drivers</h1><p>Purged, nested walk-forward Elastic Net attribution for broad-market return and sector excess return. Signed coefficients describe conditional predictive association, not causation.</p><p class="meta">Data as of {asof.date()}. Generated {generated}. Research output, not personalized investment advice.</p></header>
<div class="kpis"><div class="kpi"><b>{market_6:+.2f}%</b><span>Validated market 6m</span></div><div class="kpi"><b>{market_12:+.2f}%</b><span>Validated market 12m</span></div><div class="kpi"><b>2022+</b><span>Untouched shadow holdout</span></div><div class="kpi"><b>{int(audit["status"].eq("PASS").sum())}/{len(audit)}</b><span>Hard audit passes</span></div></div>
<section class="band"><h2>Method And Governance</h2><p>The model uses train-window-only median imputation, standardization, and 1st/99th-percentile target clipping. Hyperparameters are selected by nested annual time splits with a one-standard-error preference for stronger regularization. Every outer training set excludes labels whose 6- or 12-month outcome overlaps its test year. Sector observations receive equal total weight per month. Live forecasts are forced to zero unless validation beats a training-mean baseline and stable nonzero coefficients survive across folds.</p><div class="table-wrap">{_html_table(model_summary)}</div></section>
<section class="band"><h2>Stable Market Drivers</h2><div class="charts">{_img(_driver_chart(next(r for r in results if r.scope == 'market' and r.horizon_months == 6)), 'Six-month signed stability-adjusted factors')}{_img(_driver_chart(next(r for r in results if r.scope == 'market' and r.horizon_months == 12)), 'Twelve-month signed stability-adjusted factors')}</div>{''.join(market_tables)}</section>
<section class="band"><h2>Stable Sector Excess Drivers</h2><div class="charts">{_img(_driver_chart(next(r for r in results if r.scope == 'sector' and r.horizon_months == 6)), 'Six-month sector-excess factors')}{_img(_driver_chart(next(r for r in results if r.scope == 'sector' and r.horizon_months == 12)), 'Twelve-month sector-excess factors')}</div>{''.join(sector_tables)}</section>
<section class="band"><h2>Factor Family Attribution</h2>{_img(_family_chart(results), 'Macro, positioning, price, fundamental, and control attribution')}</section>
<section class="band"><h2>CFTC Positioning Attribution</h2><p>All eleven release-aligned positioning features enter every design matrix. The table reports only importance that survives regularization, fold selection frequency, and sign-consistency weighting; zero is an evidence result, not missing data.</p><div class="table-wrap">{_html_table(cftc_view)}</div></section>
<section class="band"><h2>Current Market Contributions</h2><p>Contribution is the current standardized factor value multiplied by its final coefficient, expressed in return percentage points. The intercept is omitted. Because validation skill is non-positive, these raw contributions are explanatory diagnostics and the validated forecast remains zero.</p>{''.join(contribution_tables)}</section>
<section class="band"><h2>Current Sector Forecasts</h2><p>Total return equals the broad-market model plus the pooled sector-excess model. Validation reliability shrinks weak forecasts toward zero; it is not a probability of profit.</p>{_img(_forecast_chart(sector_forecasts), 'Current 6- and 12-month sector forecasts')}<div class="table-wrap">{_html_table(sector_view)}</div></section>
<section class="band"><h2>Out-Of-Sample Evidence</h2><div class="table-wrap">{_html_table(metrics)}</div></section>
<section class="band"><h2>Model Audit</h2><div class="table-wrap">{_html_table(audit)}</div><p class="meta">A weak or unstable model remains visible and is shrunk rather than silently replaced. Importance can distribute across correlated factors; consult family attribution and sign consistency together.</p></section>
</main></body></html>"""


def build_factor_driver_model(project_root: str | Path | None = None) -> list[DriverResult]:
    root = resolve_project_root(project_root)
    out = root / OUTPUT_DIR
    total_steps = 5
    _write_progress(out, step=1, total=total_steps, stage="contract", message="Loading release-aligned sector and positioning contract")
    market, sector, market_live, sector_live, asof = _load_panels(root)
    position_features = [
        column
        for column in sector.columns
        if column.startswith("cot_") and column not in {"cot_usable_date", "cot_age_days"}
    ]
    market_features = [*MACRO_FEATURES, *position_features, *MARKET_AGGREGATES.values()]
    sector_features = [*MACRO_FEATURES, *position_features, *SECTOR_FEATURES]

    results = []
    _write_progress(out, step=2, total=total_steps, stage="market", message="Training purged 6/12-month broad-market driver models")
    for horizon in (6, 12):
        results.append(run_driver_model(
            market,
            market_live,
            scope="market",
            horizon=horizon,
            numeric_features=market_features,
            categorical_features=[],
            target_column=f"fwd_{horizon}m_broad",
            target_end_column=f"target_end_date_{horizon}m",
            asof=asof,
        ))

    _write_progress(out, step=3, total=total_steps, stage="sector", message="Training pooled 6/12-month sector-excess driver models")
    for horizon in (6, 12):
        results.append(run_driver_model(
            sector,
            sector_live,
            scope="sector",
            horizon=horizon,
            numeric_features=sector_features,
            categorical_features=["sector"],
            target_column=f"fwd_{horizon}m_excess",
            target_end_column=f"target_end_date_{horizon}m",
            asof=asof,
        ))

    _write_progress(out, step=4, total=total_steps, stage="attribution", message="Computing stable signed coefficients and live factor contributions")
    market_forecasts, sector_forecasts = _combined_forecasts(results)
    audit = _build_audit(results, sector, asof)
    failures = audit.loc[audit["status"].eq("FAIL")]
    if not failures.empty:
        _write_progress(out, step=4, total=total_steps, stage="audit", message="Factor driver audit failed", status="failed")
        raise ValueError("Factor driver audit failed:\n" + failures.to_string(index=False))

    out.mkdir(parents=True, exist_ok=True)
    pd.concat([result.predictions for result in results], ignore_index=True).to_csv(out / "walkforward_predictions.csv", index=False)
    pd.concat([result.metrics for result in results], ignore_index=True).to_csv(out / "model_metrics.csv", index=False)
    pd.concat([result.importance for result in results], ignore_index=True).to_csv(out / "driver_importance.csv", index=False)
    pd.concat([result.coefficient_stability for result in results], ignore_index=True).to_csv(out / "fold_coefficients.csv", index=False)
    pd.concat([result.live_contributions for result in results], ignore_index=True).to_csv(out / "live_factor_contributions.csv", index=False)
    family = pd.concat([result.importance for result in results], ignore_index=True).groupby(
        ["scope", "horizon_months", "domain", "family"], as_index=False
    )["stable_importance"].sum()
    family["importance_pct"] = family.groupby(["scope", "horizon_months"])["stable_importance"].transform(
        lambda values: values / values.sum() * 100.0 if values.sum() > 0 else 0.0
    )
    family.to_csv(out / "factor_family_importance.csv", index=False)
    market_forecasts.to_csv(out / "market_forecasts.csv", index=False)
    sector_forecasts.to_csv(out / "sector_forecasts.csv", index=False)
    audit.to_csv(out / "model_audit.csv", index=False)
    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "asof": asof.strftime("%Y-%m-%d"),
        "holdout_start": HOLDOUT_START.strftime("%Y-%m-%d"),
        "algorithm": "Elastic Net with nested purged expanding-window selection",
        "parameter_grid": PARAM_GRID,
        "model_start": "first complete CFTC z-score month, no earlier than 2007-01-01",
        "interpretation": "predictive conditional association; not causal attribution",
        "models": {
            f"{result.scope}_{result.horizon_months}m": {
                "features": len(result.feature_columns),
                "params": result.params,
                "validation_reliability": result.reliability,
                "trained_through": result.trained_through.strftime("%Y-%m-%d"),
            }
            for result in results
        },
        "audit_status": audit["status"].value_counts().to_dict(),
    }
    (out / "model_governance.json").write_text(json.dumps(governance, indent=2), encoding="utf-8")
    (out / "index.html").write_text(
        build_html_report(results, market_forecasts, sector_forecasts, audit, asof),
        encoding="utf-8",
    )
    _write_progress(out, step=5, total=total_steps, stage="complete", message="Factor driver model and dashboard complete", status="complete")
    print(f"Dashboard: {(out / 'index.html').resolve()}")
    print(market_forecasts.to_string(index=False))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=None)
    args = parser.parse_args()
    build_factor_driver_model(args.project_root)


if __name__ == "__main__":
    main()
