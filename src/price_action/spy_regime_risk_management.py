from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .data import load_macro_context, resolve_project_root
from .spy_vix_fear_greed_research import (
    DEFAULT_LOOKBACK_WINDOW,
    DEFAULT_MIN_PERIODS,
    _signal_to_noise,
    _safe_float,
    _t_stat,
    build_spy_vix_fear_greed_frame,
)

DEFAULT_OUTPUT_DIR = Path("outputs") / "spy_regime_risk_management"
DEFAULT_HOLD_DAYS = 5
DEFAULT_HOLDOUT_START = "2020-01-01"
CORE_WEIGHT = 0.60
TACTICAL_WEIGHT = 0.40
MIN_TRAIN_ROWS = 180


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a no-lookahead SPY regime risk-management study with a permanent 60% core "
            "and a 40% tactical sleeve activated only during extreme risk-off regimes."
        )
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root. Defaults to the repository root.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated risk-management research outputs.",
    )
    parser.add_argument(
        "--hold-days",
        type=int,
        default=DEFAULT_HOLD_DAYS,
        help="Holding window applied to the tactical sleeve.",
    )
    parser.add_argument(
        "--lookback-window",
        type=int,
        default=DEFAULT_LOOKBACK_WINDOW,
        help="Trailing window used for causal normalization.",
    )
    parser.add_argument(
        "--min-periods",
        type=int,
        default=DEFAULT_MIN_PERIODS,
        help="Minimum trailing observations required before regime features activate.",
    )
    parser.add_argument(
        "--holdout-start",
        type=str,
        default=DEFAULT_HOLDOUT_START,
        help="Date used to label the final out-of-sample holdout window.",
    )
    return parser.parse_args()


def _resolve_output_path(root: Path, target: Path) -> Path:
    return target if target.is_absolute() else root / target


def _causal_zscore(series: pd.Series, *, window: int, min_periods: int) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    rolling = numeric.rolling(window=window, min_periods=min_periods)
    mean = rolling.mean()
    std = rolling.std(ddof=0).replace(0.0, np.nan)
    zscore = (numeric - mean) / std
    return zscore.replace([np.inf, -np.inf], np.nan)


def _annualized_return(period_returns: pd.Series, *, periods_per_year: float) -> float | None:
    clean = pd.to_numeric(period_returns, errors="coerce").dropna()
    if clean.empty:
        return None
    total_equity = float((1.0 + clean).prod())
    years = len(clean) / periods_per_year
    if years <= 0.0 or total_equity <= 0.0:
        return None
    return float(total_equity ** (1.0 / years) - 1.0)


def _annualized_vol(period_returns: pd.Series, *, periods_per_year: float) -> float | None:
    clean = pd.to_numeric(period_returns, errors="coerce").dropna()
    if len(clean) < 2:
        return None
    return float(clean.std(ddof=0) * np.sqrt(periods_per_year))


def _safe_auc(y_true: pd.Series, y_score: pd.Series) -> float | None:
    clean = pd.DataFrame({"y_true": y_true, "y_score": y_score}).dropna()
    if clean.empty or clean["y_true"].nunique() < 2:
        return None
    return float(roc_auc_score(clean["y_true"], clean["y_score"]))


def _safe_brier(y_true: pd.Series, y_prob: pd.Series) -> float | None:
    clean = pd.DataFrame({"y_true": y_true, "y_prob": y_prob}).dropna()
    if clean.empty:
        return None
    return float(brier_score_loss(clean["y_true"], clean["y_prob"]))


def _extreme_state_sentiment(text: Any) -> str:
    if pd.isna(text):
        return "Unclassified"
    return str(text)


def _macro_bucket(value: Any) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "unknown"
    if numeric >= 0.75:
        return "macro_high"
    if numeric >= 0.25:
        return "macro_mid"
    return "macro_low"


def _future_is_benign(value: Any) -> bool:
    text = _extreme_state_sentiment(value)
    return text in {"Neutral", "Greed"}


def _future_is_adverse(value: Any) -> bool:
    text = _extreme_state_sentiment(value)
    return text in {"Fear", "Panic"}


def build_risk_management_frame(
    *,
    project_root: str | Path | None = None,
    hold_days: int = DEFAULT_HOLD_DAYS,
    lookback_window: int = DEFAULT_LOOKBACK_WINDOW,
    min_periods: int = DEFAULT_MIN_PERIODS,
) -> pd.DataFrame:
    root = resolve_project_root(project_root)
    base = build_spy_vix_fear_greed_frame(
        project_root=root,
        lookback_window=lookback_window,
        min_periods=min_periods,
        horizons=(1, hold_days, 10, 20),
    ).copy()

    macro = load_macro_context(project_root=root).sort_index()
    macro = macro.reindex(base.index).ffill()
    frame = base.copy()

    for column in [
        "high_yield_spread",
        "NFCI",
        "T10Y3M",
        "epu_zscore_252d",
        "consumer_sentiment_release_level",
        "yield_curve_10y_2y",
    ]:
        if column in macro.columns:
            frame[column] = pd.to_numeric(macro[column], errors="coerce")

    if "high_yield_spread" in frame.columns:
        frame["high_yield_spread_zscore"] = _causal_zscore(
            frame["high_yield_spread"], window=lookback_window, min_periods=min_periods
        )
    if "NFCI" in frame.columns:
        frame["NFCI_zscore"] = _causal_zscore(
            frame["NFCI"], window=lookback_window, min_periods=min_periods
        )
    if "T10Y3M" in frame.columns:
        frame["curve_inversion_zscore"] = -_causal_zscore(
            frame["T10Y3M"], window=lookback_window, min_periods=min_periods
        )
    if "consumer_sentiment_release_level" in frame.columns:
        frame["consumer_sentiment_stress_zscore"] = -_causal_zscore(
            frame["consumer_sentiment_release_level"],
            window=lookback_window,
            min_periods=min_periods,
        )

    macro_components = pd.DataFrame(index=frame.index)
    for source_name, target_name in [
        ("high_yield_spread_zscore", "credit_spread_stress"),
        ("NFCI_zscore", "financial_conditions_stress"),
        ("curve_inversion_zscore", "curve_inversion_stress"),
        ("epu_zscore_252d", "geopolitical_policy_stress"),
        ("consumer_sentiment_stress_zscore", "household_stress"),
    ]:
        if source_name in frame.columns:
            macro_components[target_name] = pd.to_numeric(frame[source_name], errors="coerce")
    frame["macro_fragility_score"] = macro_components.mean(axis=1)

    frame["risk_off_gate"] = (
        (frame["panic_score"] >= 0.45)
        | (
            (frame["spot_vix_percentile_252d"] >= 0.75)
            & (frame["spy_drawdown_20d"] <= -0.04)
        )
        | (
            (frame["panic_score"] >= 0.35)
            & (frame["macro_fragility_score"] >= 0.40)
        )
    )
    frame["extreme_risk_off"] = (
        (frame["panic_score"] >= 0.75)
        | (
            (frame["spot_vix_percentile_252d"] >= 0.85)
            & (frame["spy_drawdown_20d"] <= -0.06)
        )
        | (
            (frame["panic_score"] >= 0.55)
            & (frame["macro_fragility_score"] >= 0.75)
            & (frame["spot_vix_percentile_252d"] >= 0.70)
        )
    )

    frame["sentiment_state_clean"] = frame["sentiment_state"].map(_extreme_state_sentiment)
    frame["macro_bucket"] = frame["macro_fragility_score"].map(_macro_bucket)
    frame["chain_state"] = frame["sentiment_state_clean"] + "|" + frame["macro_bucket"]
    frame["future_sentiment_state"] = frame["sentiment_state_clean"].shift(-hold_days)
    frame["future_chain_state"] = frame["chain_state"].shift(-hold_days)
    frame["future_is_benign"] = frame["future_sentiment_state"].map(_future_is_benign)
    frame["future_is_adverse"] = frame["future_sentiment_state"].map(_future_is_adverse)
    frame["benchmark_core_return"] = CORE_WEIGHT * frame[f"forward_return_{hold_days}d"]
    frame["benchmark_full_spy_return"] = frame[f"forward_return_{hold_days}d"]
    return frame.sort_index()


def build_drift_summary(frame: pd.DataFrame, *, hold_days: int) -> pd.DataFrame:
    target_name = f"forward_return_{hold_days}d"
    groups = {
        "all_dates": frame[target_name],
        "risk_off_dates": frame.loc[frame["risk_off_gate"], target_name],
        "extreme_risk_off_dates": frame.loc[frame["extreme_risk_off"], target_name],
        "non_risk_off_dates": frame.loc[~frame["risk_off_gate"], target_name],
    }
    rows: list[dict[str, Any]] = []
    for name, values in groups.items():
        clean = pd.to_numeric(values, errors="coerce").dropna()
        rows.append(
            {
                "group": name,
                "observations": int(len(clean)),
                "mean_return": _safe_float(clean.mean()),
                "median_return": _safe_float(clean.median()),
                "positive_rate": _safe_float((clean > 0.0).mean()) if not clean.empty else None,
                "signal_to_noise": _signal_to_noise(clean),
                "t_stat": _t_stat(clean),
            }
        )
    return pd.DataFrame(rows)


def build_event_frame(frame: pd.DataFrame, *, hold_days: int) -> pd.DataFrame:
    target_name = f"forward_return_{hold_days}d"
    events = frame.loc[
        frame["extreme_risk_off"]
        & frame[target_name].notna()
        & frame["future_sentiment_state"].notna()
        & frame["chain_state"].notna()
    ].copy()
    if events.empty:
        return events

    events = events.reset_index().rename(columns={"index": "signal_date"})
    events["event_id"] = np.arange(len(events))
    events["source_state"] = events["chain_state"].astype("string")
    events["prev_source_state"] = events["source_state"].shift(1).fillna("START")
    events["source_key"] = events["prev_source_state"] + " -> " + events["source_state"]
    events["positive_return_target"] = events[target_name] > 0.0
    events["negative_return_target"] = events[target_name] < 0.0
    events["event_return"] = events[target_name]
    return events


def build_transition_summary(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    summary = (
        events.groupby(["source_state", "future_sentiment_state"], as_index=False)
        .agg(
            transition_count=("event_id", "count"),
            mean_event_return=("event_return", "mean"),
            positive_rate=("positive_return_target", "mean"),
            avg_panic_score=("panic_score", "mean"),
            avg_macro_fragility_score=("macro_fragility_score", "mean"),
        )
        .sort_values(["source_state", "transition_count"], ascending=[True, False])
        .reset_index(drop=True)
    )
    return summary


def build_event_state_summary(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    summary = (
        events.groupby("source_state", as_index=False)
        .agg(
            events=("event_id", "count"),
            mean_event_return=("event_return", "mean"),
            median_event_return=("event_return", "median"),
            positive_rate=("positive_return_target", "mean"),
            avg_panic_score=("panic_score", "mean"),
            avg_macro_fragility_score=("macro_fragility_score", "mean"),
            benign_transition_rate=("future_is_benign", "mean"),
            adverse_transition_rate=("future_is_adverse", "mean"),
        )
        .sort_values(["events", "mean_event_return"], ascending=[False, False])
        .reset_index(drop=True)
    )
    summary["signal_to_noise"] = summary["mean_event_return"] / summary["median_event_return"].abs().replace(0.0, np.nan)
    return summary


def build_online_state_models(
    events: pd.DataFrame,
    *,
    hold_days: int,
    min_train_rows: int = MIN_TRAIN_ROWS,
    prior_strength: float = 24.0,
    min_state_count: int = 18,
) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()

    target_name = f"forward_return_{hold_days}d"
    future_labels = ("Fear", "Greed", "Neutral", "Panic")
    rows: list[dict[str, Any]] = []
    laplace = 1.0

    for position, row in events.iterrows():
        training = events.iloc[:position].copy()
        if len(training) < min_train_rows:
            continue

        overall_mean = float(training[target_name].mean())
        overall_positive_rate = float(training["positive_return_target"].mean())
        overall_std = float(training[target_name].std(ddof=0))
        if not np.isfinite(overall_std) or overall_std <= 0.0:
            overall_std = 1.0

        source_key_group = training.loc[training["source_key"] == row["source_key"]].copy()
        if len(source_key_group) >= min_state_count:
            markov_source_group = source_key_group
            markov_source_used = "source_key"
        else:
            markov_source_group = training.loc[training["source_state"] == row["source_state"]].copy()
            markov_source_used = "source_state"
            if markov_source_group.empty:
                markov_source_group = training.copy()
                markov_source_used = "global"

        transition_counts = markov_source_group["future_sentiment_state"].value_counts()
        state_return_means = training.groupby("future_sentiment_state")[target_name].mean()
        transition_denom = float(transition_counts.sum() + laplace * len(future_labels))

        markov_expected_return = 0.0
        for future_label in future_labels:
            probability = (transition_counts.get(future_label, 0.0) + laplace) / transition_denom
            markov_expected_return += probability * float(state_return_means.get(future_label, overall_mean))

        markov_positive_prob = (
            prior_strength * overall_positive_rate + float(markov_source_group["positive_return_target"].sum())
        ) / (prior_strength + len(markov_source_group))
        markov_benign_prob = (
            transition_counts.get("Greed", 0.0)
            + transition_counts.get("Neutral", 0.0)
            + 2.0 * laplace
        ) / transition_denom
        markov_adverse_prob = (
            transition_counts.get("Fear", 0.0)
            + transition_counts.get("Panic", 0.0)
            + 2.0 * laplace
        ) / transition_denom

        bayes_source_group = training.loc[training["source_state"] == row["source_state"]].copy()
        if bayes_source_group.empty:
            bayes_source_group = training.copy()
        bayes_positive_prob = (
            prior_strength * overall_positive_rate + float(bayes_source_group["positive_return_target"].sum())
        ) / (prior_strength + len(bayes_source_group))
        bayes_expected_return = (
            prior_strength * overall_mean + len(bayes_source_group) * float(bayes_source_group[target_name].mean())
        ) / (prior_strength + len(bayes_source_group))

        rows.append(
            {
                "event_id": int(row["event_id"]),
                "signal_date": row["signal_date"],
                "markov_source_used": markov_source_used,
                "markov_training_rows": int(len(markov_source_group)),
                "markov_expected_return": float(markov_expected_return),
                "markov_positive_prob": float(markov_positive_prob),
                "markov_benign_prob": float(markov_benign_prob),
                "markov_adverse_prob": float(markov_adverse_prob),
                "markov_training_mean_return": float(overall_mean),
                "markov_training_positive_rate": float(overall_positive_rate),
                "bayesian_training_rows": int(len(bayes_source_group)),
                "bayesian_expected_return": float(bayes_expected_return),
                "bayesian_positive_prob": float(bayes_positive_prob),
                "bayesian_training_mean_return": float(overall_mean),
                "bayesian_training_positive_rate": float(overall_positive_rate),
            }
        )

    predictions = pd.DataFrame(rows)
    if predictions.empty:
        return predictions
    return predictions.sort_values("signal_date").reset_index(drop=True)


def _expanding_splits(n_obs: int, *, min_train_size: int, test_size: int) -> list[tuple[np.ndarray, np.ndarray]]:
    splits: list[tuple[np.ndarray, np.ndarray]] = []
    train_end = min_train_size
    while train_end < n_obs:
        test_end = min(train_end + test_size, n_obs)
        if test_end <= train_end:
            break
        train_idx = np.arange(0, train_end)
        test_idx = np.arange(train_end, test_end)
        splits.append((train_idx, test_idx))
        train_end = test_end
    return splits


def build_ml_predictions(
    events: pd.DataFrame,
    *,
    hold_days: int,
    min_train_rows: int = MIN_TRAIN_ROWS,
) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()

    target_name = f"forward_return_{hold_days}d"
    feature_candidates = [
        "fear_greed_score",
        "fear_score",
        "panic_score",
        "signal_strength",
        "spot_vix",
        "spot_vix_percentile_252d",
        "spot_vix_zscore_252d",
        "spot_vix_change_5d_zscore",
        "vix_curve_contango",
        "vix_curve_contango_zscore",
        "spy_trend_5d",
        "spy_trend_20d",
        "spy_trend_63d",
        "spy_drawdown_20d",
        "spy_drawdown_63d",
        "spy_realized_vol_20d",
        "macro_fragility_score",
        "high_yield_spread_zscore",
        "NFCI_zscore",
        "curve_inversion_zscore",
        "epu_zscore_252d",
        "consumer_sentiment_stress_zscore",
    ]
    feature_names = [name for name in feature_candidates if name in events.columns]
    model_frame = events.copy()
    features = model_frame[feature_names].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    positive_target = model_frame["positive_return_target"].astype(int)
    regression_target = pd.to_numeric(model_frame[target_name], errors="coerce")

    min_train_size = min(max(min_train_rows, len(model_frame) // 3), max(40, len(model_frame) - 20))
    test_size = max(20, len(model_frame) // 8)
    splits = _expanding_splits(len(model_frame), min_train_size=min_train_size, test_size=test_size)

    probability_predictions = pd.Series(np.nan, index=model_frame.index, dtype="float64")
    expected_return_predictions = pd.Series(np.nan, index=model_frame.index, dtype="float64")
    training_mean_returns = pd.Series(np.nan, index=model_frame.index, dtype="float64")
    training_positive_rates = pd.Series(np.nan, index=model_frame.index, dtype="float64")

    logistic = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    solver="lbfgs",
                    max_iter=2000,
                    class_weight="balanced",
                    random_state=7,
                ),
            ),
        ]
    )
    regressor = HistGradientBoostingRegressor(
        loss="squared_error",
        learning_rate=0.03,
        max_depth=3,
        max_iter=250,
        min_samples_leaf=20,
        random_state=7,
    )

    for train_idx, test_idx in splits:
        x_train = features.iloc[train_idx]
        x_test = features.iloc[test_idx]
        y_train_positive = positive_target.iloc[train_idx]
        y_train_return = regression_target.iloc[train_idx]

        if y_train_positive.nunique() < 2:
            continue

        logistic.fit(x_train, y_train_positive)
        regressor.fit(x_train, y_train_return)

        positive_probability = logistic.predict_proba(x_test)[:, 1]
        train_mean_return = float(y_train_return.mean())
        train_positive_rate = float(y_train_positive.mean())
        positive_returns = y_train_return.loc[y_train_return > 0.0]
        non_positive_returns = y_train_return.loc[y_train_return <= 0.0]
        avg_gain = float(positive_returns.mean()) if not positive_returns.empty else max(train_mean_return, 0.0)
        avg_loss = float(non_positive_returns.mean()) if not non_positive_returns.empty else min(train_mean_return, 0.0)
        expected_from_probability = positive_probability * avg_gain + (1.0 - positive_probability) * avg_loss
        regression_prediction = regressor.predict(x_test)
        ml_expected_return = np.nanmean(
            np.vstack([expected_from_probability, regression_prediction]),
            axis=0,
        )

        probability_predictions.iloc[test_idx] = positive_probability
        expected_return_predictions.iloc[test_idx] = ml_expected_return
        training_mean_returns.iloc[test_idx] = train_mean_return
        training_positive_rates.iloc[test_idx] = train_positive_rate

    predictions = model_frame[["event_id", "signal_date"]].copy()
    predictions["ml_positive_prob"] = probability_predictions
    predictions["ml_expected_return"] = expected_return_predictions
    predictions["ml_training_mean_return"] = training_mean_returns
    predictions["ml_training_positive_rate"] = training_positive_rates
    predictions = predictions.dropna(subset=["ml_expected_return", "ml_positive_prob"])
    return predictions.sort_values("signal_date").reset_index(drop=True)


def build_model_metrics(
    prediction_frame: pd.DataFrame,
    *,
    hold_days: int,
    holdout_start: str,
) -> pd.DataFrame:
    target_name = f"forward_return_{hold_days}d"
    holdout_timestamp = pd.Timestamp(holdout_start)
    rows: list[dict[str, Any]] = []
    models = ("markov", "bayesian", "ml", "ensemble")

    scored = prediction_frame.dropna(subset=[target_name]).copy()
    scored["scope"] = np.where(scored["signal_date"] >= holdout_timestamp, "holdout", "validation")

    for scope_name, scope_frame in [("all", scored), *list(scored.groupby("scope"))]:
        for model_name in models:
            prob_column = f"{model_name}_positive_prob"
            return_column = f"{model_name}_expected_return"
            if prob_column not in scope_frame.columns or return_column not in scope_frame.columns:
                continue
            pair = scope_frame[[target_name, "positive_return_target", prob_column, return_column]].dropna()
            if pair.empty:
                continue
            top_cut = float(pair[return_column].quantile(0.80))
            bottom_cut = float(pair[return_column].quantile(0.20))
            top_bucket = pair.loc[pair[return_column] >= top_cut, target_name]
            bottom_bucket = pair.loc[pair[return_column] <= bottom_cut, target_name]
            rows.append(
                {
                    "scope": str(scope_name),
                    "model_name": model_name,
                    "observations": int(len(pair)),
                    "roc_auc": _safe_auc(pair["positive_return_target"], pair[prob_column]),
                    "brier_score": _safe_brier(pair["positive_return_target"], pair[prob_column]),
                    "prediction_return_corr": _safe_float(pair[return_column].corr(pair[target_name])),
                    "mean_predicted_return": _safe_float(pair[return_column].mean()),
                    "mean_actual_return": _safe_float(pair[target_name].mean()),
                    "top_quintile_mean_return": _safe_float(top_bucket.mean()),
                    "bottom_quintile_mean_return": _safe_float(bottom_bucket.mean()),
                    "top_quintile_signal_to_noise": _signal_to_noise(top_bucket),
                    "bottom_quintile_signal_to_noise": _signal_to_noise(bottom_bucket),
                    "positive_rate": _safe_float(pair["positive_return_target"].mean()),
                    "sign_accuracy": _safe_float(
                        ((pair[return_column] > 0.0) == pair["positive_return_target"]).mean()
                    ),
                }
            )

    return pd.DataFrame(rows).sort_values(["scope", "roc_auc", "model_name"], ascending=[True, False, True])


def _tactical_weight(row: pd.Series, strategy_name: str) -> float:
    extreme_risk_off = bool(row.get("extreme_risk_off", False))
    panic_score = _safe_float(row.get("panic_score")) or 0.0
    vix_percentile = _safe_float(row.get("spot_vix_percentile_252d")) or 0.0
    training_mean = _safe_float(row.get("training_mean_return"))
    if training_mean is None:
        training_mean = 0.0

    if strategy_name == "core_60_only":
        return 0.0
    if strategy_name == "full_spy_100":
        return TACTICAL_WEIGHT
    if strategy_name == "heuristic_panic_rebound":
        return TACTICAL_WEIGHT if extreme_risk_off and panic_score >= 0.75 and vix_percentile >= 0.80 else 0.0

    model_prefix_map = {
        "markov_mobilized": "markov",
        "bayesian_mobilized": "bayesian",
        "ml_mobilized": "ml",
        "ensemble_mobilized": "ensemble",
        "ensemble_long_short": "ensemble",
    }
    model_prefix = model_prefix_map.get(strategy_name)
    if model_prefix is None or not extreme_risk_off:
        return 0.0

    expected_return = _safe_float(row.get(f"{model_prefix}_expected_return"))
    positive_prob = _safe_float(row.get(f"{model_prefix}_positive_prob"))
    if expected_return is None or positive_prob is None:
        return 0.0

    if expected_return >= max(training_mean, 0.0) and positive_prob >= 0.55:
        return TACTICAL_WEIGHT

    if strategy_name == "ensemble_long_short" and expected_return <= min(-0.01, training_mean - 0.01) and positive_prob <= 0.40:
        return -TACTICAL_WEIGHT

    return 0.0


def build_strategy_periods(
    frame: pd.DataFrame,
    prediction_frame: pd.DataFrame,
    *,
    hold_days: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    target_name = f"forward_return_{hold_days}d"
    merged = frame.reset_index().merge(
        prediction_frame,
        on="signal_date",
        how="left",
        suffixes=("", "_prediction"),
    )
    merged = merged.dropna(subset=[target_name]).reset_index(drop=True)
    if merged.empty:
        return pd.DataFrame(), pd.DataFrame()

    strategy_names = (
        "core_60_only",
        "full_spy_100",
        "heuristic_panic_rebound",
        "markov_mobilized",
        "bayesian_mobilized",
        "ml_mobilized",
        "ensemble_mobilized",
        "ensemble_long_short",
    )
    periods: list[dict[str, Any]] = []
    periods_per_year = 252.0 / float(hold_days)

    pointer = 0
    while pointer < len(merged):
        row = merged.iloc[pointer]
        spy_return = _safe_float(row[target_name])
        if spy_return is None:
            pointer += hold_days
            continue
        core_return = CORE_WEIGHT * spy_return
        for strategy_name in strategy_names:
            sleeve_weight = _tactical_weight(row, strategy_name)
            strategy_return = core_return + sleeve_weight * spy_return
            periods.append(
                {
                    "strategy_name": strategy_name,
                    "signal_date": row["signal_date"],
                    "entry_date": row.get("entry_date"),
                    "exit_date": row.get(f"exit_date_{hold_days}d"),
                    "hold_days": int(hold_days),
                    "extreme_risk_off": bool(row.get("extreme_risk_off", False)),
                    "sentiment_state": row.get("sentiment_state_clean"),
                    "sleeve_weight": float(sleeve_weight),
                    "gross_exposure": float(CORE_WEIGHT + abs(sleeve_weight)),
                    "strategy_return": float(strategy_return),
                    "spy_return": float(spy_return),
                    "core_return": float(core_return),
                    "excess_return_vs_spy": float(strategy_return - spy_return),
                    "excess_return_vs_core": float(strategy_return - core_return),
                }
            )
        pointer += hold_days

    period_frame = pd.DataFrame(periods).sort_values(["strategy_name", "signal_date"]).reset_index(drop=True)
    summary_rows: list[dict[str, Any]] = []
    for strategy_name, group in period_frame.groupby("strategy_name"):
        returns = group["strategy_return"]
        equity = (1.0 + returns).cumprod()
        drawdown = equity / equity.cummax() - 1.0
        summary_rows.append(
            {
                "strategy_name": str(strategy_name),
                "hold_days": int(hold_days),
                "periods": int(len(group)),
                "active_periods": int((group["sleeve_weight"] != 0.0).sum()),
                "total_return": float(equity.iloc[-1] - 1.0),
                "avg_return": float(returns.mean()),
                "avg_excess_return_vs_spy": float(group["excess_return_vs_spy"].mean()),
                "avg_excess_return_vs_core": float(group["excess_return_vs_core"].mean()),
                "annualized_return": _annualized_return(returns, periods_per_year=periods_per_year),
                "annualized_vol": _annualized_vol(returns, periods_per_year=periods_per_year),
                "signal_to_noise": _signal_to_noise(returns),
                "hit_rate_vs_spy": _safe_float((group["excess_return_vs_spy"] > 0.0).mean()),
                "hit_rate_vs_core": _safe_float((group["excess_return_vs_core"] > 0.0).mean()),
                "max_drawdown": float(drawdown.min()) if not drawdown.empty else None,
            }
        )
    summary = pd.DataFrame(summary_rows).sort_values("strategy_name").reset_index(drop=True)
    return period_frame, summary


def build_prediction_frame(
    events: pd.DataFrame,
    online_models: pd.DataFrame,
    ml_predictions: pd.DataFrame,
) -> pd.DataFrame:
    prediction_frame = events[["event_id", "signal_date"]].copy()
    if not online_models.empty:
        prediction_frame = prediction_frame.merge(online_models, on=["event_id", "signal_date"], how="left")
    if not ml_predictions.empty:
        prediction_frame = prediction_frame.merge(ml_predictions, on=["event_id", "signal_date"], how="left")

    training_mean_columns = [
        column
        for column in [
            "markov_training_mean_return",
            "bayesian_training_mean_return",
            "ml_training_mean_return",
        ]
        if column in prediction_frame.columns
    ]
    training_positive_rate_columns = [
        column
        for column in [
            "markov_training_positive_rate",
            "bayesian_training_positive_rate",
            "ml_training_positive_rate",
        ]
        if column in prediction_frame.columns
    ]
    if training_mean_columns:
        prediction_frame["training_mean_return"] = prediction_frame[training_mean_columns].mean(axis=1)
    if training_positive_rate_columns:
        prediction_frame["training_positive_rate"] = prediction_frame[training_positive_rate_columns].mean(axis=1)

    expected_columns = [
        column
        for column in [
            "markov_expected_return",
            "bayesian_expected_return",
            "ml_expected_return",
        ]
        if column in prediction_frame.columns
    ]
    probability_columns = [
        column
        for column in [
            "markov_positive_prob",
            "bayesian_positive_prob",
            "ml_positive_prob",
        ]
        if column in prediction_frame.columns
    ]
    if expected_columns:
        prediction_frame["ensemble_expected_return"] = prediction_frame[expected_columns].mean(axis=1)
    if probability_columns:
        prediction_frame["ensemble_positive_prob"] = prediction_frame[probability_columns].mean(axis=1)
    return prediction_frame.sort_values("signal_date").reset_index(drop=True)


def build_spy_regime_risk_management(
    *,
    project_root: str | Path | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    hold_days: int = DEFAULT_HOLD_DAYS,
    lookback_window: int = DEFAULT_LOOKBACK_WINDOW,
    min_periods: int = DEFAULT_MIN_PERIODS,
    holdout_start: str = DEFAULT_HOLDOUT_START,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    resolved_output_dir = _resolve_output_path(root, output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    frame = build_risk_management_frame(
        project_root=root,
        hold_days=hold_days,
        lookback_window=lookback_window,
        min_periods=min_periods,
    )
    frame.reset_index().to_csv(resolved_output_dir / "risk_management_signal_panel.csv", index=False)

    drift_summary = build_drift_summary(frame, hold_days=hold_days)
    drift_summary.to_csv(resolved_output_dir / "drift_summary.csv", index=False)

    events = build_event_frame(frame, hold_days=hold_days)
    events.to_csv(resolved_output_dir / "extreme_risk_off_events.csv", index=False)

    transition_summary = build_transition_summary(events)
    transition_summary.to_csv(resolved_output_dir / "markov_transition_summary.csv", index=False)

    event_state_summary = build_event_state_summary(events)
    event_state_summary.to_csv(resolved_output_dir / "event_state_summary.csv", index=False)

    online_models = build_online_state_models(events, hold_days=hold_days)
    online_models.to_csv(resolved_output_dir / "online_state_model_predictions.csv", index=False)

    ml_predictions = build_ml_predictions(events, hold_days=hold_days)
    ml_predictions.to_csv(resolved_output_dir / "ml_predictions.csv", index=False)

    prediction_frame = build_prediction_frame(events, online_models, ml_predictions)
    prediction_frame.to_csv(resolved_output_dir / "event_model_predictions.csv", index=False)

    scored_events = events.merge(prediction_frame, on=["event_id", "signal_date"], how="left")
    model_metrics = build_model_metrics(scored_events, hold_days=hold_days, holdout_start=holdout_start)
    model_metrics.to_csv(resolved_output_dir / "model_metrics.csv", index=False)

    strategy_periods, strategy_summary = build_strategy_periods(frame, prediction_frame, hold_days=hold_days)
    strategy_periods.to_csv(resolved_output_dir / "strategy_periods.csv", index=False)
    strategy_summary.to_csv(resolved_output_dir / "strategy_summary.csv", index=False)

    best_strategy = strategy_summary.sort_values(
        ["avg_excess_return_vs_core", "signal_to_noise", "max_drawdown"],
        ascending=[False, False, False],
    ).head(1)

    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "output_dir": str(resolved_output_dir),
        "rows": int(len(frame)),
        "extreme_risk_off_events": int(len(events)),
        "prediction_rows": int(len(prediction_frame)),
        "hold_days": int(hold_days),
        "core_weight": CORE_WEIGHT,
        "tactical_weight": TACTICAL_WEIGHT,
        "lookback_window": int(lookback_window),
        "min_periods": int(min_periods),
        "holdout_start": holdout_start,
        "leakage_guardrails": [
            "All regime features are computed from current and trailing history only.",
            "The tactical sleeve enters on the next bar after the signal date.",
            "Markov and Bayesian estimates use expanding history only; ML predictions are walk-forward and never see future labels in training.",
            "Strategy periods are sampled on a non-overlapping hold-day schedule.",
        ],
        "drift_summary": drift_summary.to_dict(orient="records"),
        "best_strategy": best_strategy.to_dict(orient="records"),
    }
    (resolved_output_dir / "spy_regime_risk_management_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    args = parse_args()
    summary = build_spy_regime_risk_management(
        project_root=args.project_root,
        output_dir=args.output_dir,
        hold_days=args.hold_days,
        lookback_window=args.lookback_window,
        min_periods=args.min_periods,
        holdout_start=args.holdout_start,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()