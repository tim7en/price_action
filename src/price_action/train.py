from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, precision_score, recall_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .data import build_market_frame, discover_symbols, resolve_project_root
from .features import engineer_daily_features

try:
    from lightgbm import LGBMClassifier
except (ImportError, OSError):
    LGBMClassifier = None


def expanding_walk_forward_splits(
    n_obs: int,
    min_train_size: int,
    test_size: int,
    step_size: int | None = None,
    embargo_size: int = 5,
    purge_size: int = 0,
) -> list[tuple[np.ndarray, np.ndarray]]:
    if n_obs <= 0:
        return []
    if embargo_size < 0 or purge_size < 0:
        raise ValueError("embargo_size and purge_size must be non-negative.")

    step = step_size or test_size
    train_end = min_train_size
    gap_size = embargo_size + purge_size
    splits: list[tuple[np.ndarray, np.ndarray]] = []

    while train_end + gap_size + test_size <= n_obs:
        train_idx = np.arange(0, train_end)
        test_start = train_end + gap_size
        test_end = test_start + test_size
        test_idx = np.arange(test_start, test_end)
        splits.append((train_idx, test_idx))
        train_end += step

    return splits


def calendar_walk_forward_splits(
    index: pd.DatetimeIndex,
    train_years: int,
    validation_years: int,
    embargo_size: int = 5,
    purge_size: int = 0,
    holdout_start: str | None = None,
    expanding_train: bool = True,
) -> tuple[list[tuple[np.ndarray, np.ndarray, str]], tuple[np.ndarray, np.ndarray, str] | None]:
    if index.empty:
        return [], None
    if embargo_size < 0 or purge_size < 0:
        raise ValueError("embargo_size and purge_size must be non-negative.")

    sorted_index = pd.DatetimeIndex(index).sort_values()
    years = sorted(sorted_index.year.unique())
    first_validation_year = years[0] + train_years
    holdout_timestamp = pd.Timestamp(holdout_start) if holdout_start else None
    gap_delta = pd.Timedelta(days=embargo_size + purge_size)

    splits: list[tuple[np.ndarray, np.ndarray, str]] = []
    for year in years:
        if year < first_validation_year:
            continue

        validation_start = pd.Timestamp(year=year, month=1, day=1)
        if holdout_timestamp is not None and validation_start >= holdout_timestamp:
            break

        validation_end = validation_start + pd.DateOffset(years=validation_years)
        train_start = sorted_index.min() if expanding_train else validation_start - pd.DateOffset(years=train_years)
        train_end = validation_start - gap_delta

        train_idx = np.flatnonzero((sorted_index >= train_start) & (sorted_index < train_end))
        test_idx = np.flatnonzero((sorted_index >= validation_start) & (sorted_index < validation_end))
        if len(train_idx) == 0 or len(test_idx) == 0:
            continue

        splits.append((train_idx, test_idx, str(year)))

    holdout_split: tuple[np.ndarray, np.ndarray, str] | None = None
    if holdout_timestamp is not None:
        train_idx = np.flatnonzero(sorted_index < (holdout_timestamp - gap_delta))
        test_idx = np.flatnonzero(sorted_index >= holdout_timestamp)
        if len(train_idx) and len(test_idx):
            holdout_split = (train_idx, test_idx, "holdout")

    return splits, holdout_split


def build_base_models(random_state: int) -> dict[str, Any]:
    models: dict[str, Any] = {
        "elastic_net": Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        solver="saga",
                        l1_ratio=0.5,
                        C=0.5,
                        max_iter=4_000,
                        class_weight="balanced",
                        random_state=random_state,
                    ),
                ),
            ]
        ),
        "extra_trees": ExtraTreesClassifier(
            n_estimators=400,
            max_depth=6,
            min_samples_leaf=20,
            min_samples_split=40,
            class_weight="balanced",
            random_state=random_state,
            n_jobs=-1,
        ),
    }

    if LGBMClassifier is not None:
        models["lightgbm"] = LGBMClassifier(
            objective="binary",
            n_estimators=300,
            learning_rate=0.03,
            num_leaves=15,
            max_depth=4,
            min_child_samples=40,
            subsample=0.8,
            subsample_freq=1,
            colsample_bytree=0.8,
            reg_alpha=1.0,
            reg_lambda=5.0,
            class_weight="balanced",
            random_state=random_state,
            n_jobs=-1,
            verbosity=-1,
        )
    else:
        models["lightgbm"] = HistGradientBoostingClassifier(
            learning_rate=0.03,
            max_depth=4,
            max_leaf_nodes=15,
            min_samples_leaf=40,
            l2_regularization=5.0,
            max_iter=300,
            random_state=random_state,
        )

    return models


def _gate_feature_columns(frame: pd.DataFrame) -> list[str]:
    preferred = [
        "prob_elastic_net",
        "prob_extra_trees",
        "prob_lightgbm",
        "regime_risk_off",
        "risk_off_score",
        "regime_trend",
        "trend_score",
        "momentum_oscillator",
    ]
    return [column for column in preferred if column in frame.columns]


def fit_gate_model(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    random_state: int,
) -> Pipeline | None:
    inner_splits = expanding_walk_forward_splits(
        n_obs=len(x_train),
        min_train_size=max(80, len(x_train) // 2),
        test_size=max(20, len(x_train) // 6),
        step_size=max(20, len(x_train) // 6),
        embargo_size=0,
    )

    if len(inner_splits) < 2:
        return None

    oof = pd.DataFrame(index=pd.RangeIndex(len(x_train)))
    gate_context_columns = [
        column
        for column in [
            "regime_risk_off",
            "risk_off_score",
            "regime_trend",
            "trend_score",
            "momentum_oscillator",
        ]
        if column in x_train.columns
    ]

    for split_train_idx, split_valid_idx in inner_splits:
        split_x_train = x_train.iloc[split_train_idx]
        split_y_train = y_train.iloc[split_train_idx]
        split_x_valid = x_train.iloc[split_valid_idx]

        if split_y_train.nunique() < 2:
            continue

        for name, model in build_base_models(random_state=random_state).items():
            fitted = clone(model)
            fitted.fit(split_x_train, split_y_train)
            oof.loc[split_valid_idx, f"prob_{name}"] = fitted.predict_proba(split_x_valid)[:, 1]

    for column in gate_context_columns:
        oof[column] = x_train[column].to_numpy()

    oof = oof.dropna()
    gate_features = _gate_feature_columns(oof)
    if len(oof) < 50 or len(gate_features) < 3:
        return None

    gate_target = y_train.iloc[oof.index]
    if gate_target.nunique() < 2:
        return None

    gate_model = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    C=1.0,
                    max_iter=2_000,
                    class_weight="balanced",
                    random_state=random_state,
                ),
            ),
        ]
    )
    gate_model.fit(oof[gate_features], gate_target)
    return gate_model


def run_walk_forward_experiment(
    symbol: str,
    project_root: str | Path | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    label_horizon: int = 5,
    cost_bps: float = 15.0,
    min_train_size: int = 160,
    test_size: int = 40,
    step_size: int | None = None,
    embargo_size: int = 5,
    purge_size: int = 0,
    signal_threshold: float = 0.55,
    random_state: int = 42,
    validation_mode: str = "row",
    train_years: int = 5,
    validation_years: int = 1,
    holdout_start: str | None = None,
    expanding_train: bool = True,
    feature_lag: int = 0,
    use_gate_model: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    market_frame = build_market_frame(symbol=symbol, project_root=project_root)
    dataset, feature_columns = engineer_daily_features(
        market_frame=market_frame,
        label_horizon=label_horizon,
        cost_bps=cost_bps,
        feature_lag=feature_lag,
    )

    if start_date is not None:
        dataset = dataset.loc[dataset.index >= pd.Timestamp(start_date)]
    if end_date is not None:
        dataset = dataset.loc[dataset.index <= pd.Timestamp(end_date)]
    if dataset.empty:
        raise ValueError("No rows remain after applying the requested date filters.")

    x = dataset[feature_columns]
    y = dataset["target"]

    if validation_mode == "calendar":
        splits, holdout_split = calendar_walk_forward_splits(
            index=dataset.index,
            train_years=train_years,
            validation_years=validation_years,
            embargo_size=embargo_size,
            purge_size=purge_size,
            holdout_start=holdout_start,
            expanding_train=expanding_train,
        )
        if not splits and holdout_split is None:
            raise ValueError("No calendar walk-forward splits were produced. Relax the year settings.")
        labeled_splits = splits + ([holdout_split] if holdout_split is not None else [])
    else:
        if len(dataset) < min_train_size + embargo_size + purge_size + test_size:
            raise ValueError(
                "Not enough rows after feature engineering for the requested walk-forward setup."
            )

        row_splits = expanding_walk_forward_splits(
            n_obs=len(dataset),
            min_train_size=min_train_size,
            test_size=test_size,
            step_size=step_size,
            embargo_size=embargo_size,
            purge_size=purge_size,
        )
        if not row_splits:
            raise ValueError("No walk-forward splits were produced. Relax the split settings.")
        labeled_splits = [
            (train_idx, test_idx, str(fold_number))
            for fold_number, (train_idx, test_idx) in enumerate(row_splits, start=1)
        ]

    fold_predictions: list[pd.DataFrame] = []
    for fold_number, (train_idx, test_idx, fold_label) in enumerate(labeled_splits, start=1):
        x_train = x.iloc[train_idx]
        y_train = y.iloc[train_idx]
        x_test = x.iloc[test_idx]
        fold_frame = dataset.iloc[test_idx][["forward_return", "net_forward_return"]].copy()

        if y_train.nunique() < 2:
            continue

        gate_model = None
        if use_gate_model:
            gate_model = fit_gate_model(x_train=x_train, y_train=y_train, random_state=random_state)
        probability_frame = pd.DataFrame(index=x_test.index)

        for name, model in build_base_models(random_state=random_state).items():
            fitted = clone(model)
            fitted.fit(x_train, y_train)
            probability_frame[f"prob_{name}"] = fitted.predict_proba(x_test)[:, 1]

        fold_frame = fold_frame.join(probability_frame)
        fold_frame["ensemble_probability"] = probability_frame.mean(axis=1)

        for column in [
            "regime_risk_off",
            "risk_off_score",
            "regime_trend",
            "trend_score",
            "momentum_oscillator",
        ]:
            if column in x_test.columns:
                fold_frame[column] = x_test[column]

        if gate_model is not None:
            gate_features = _gate_feature_columns(fold_frame)
            fold_frame["gated_probability"] = gate_model.predict_proba(fold_frame[gate_features])[:, 1]
        else:
            fold_frame["gated_probability"] = fold_frame["ensemble_probability"]

        fold_frame["target"] = dataset.iloc[test_idx]["target"]
        fold_frame["fold"] = fold_number
        fold_frame["fold_label"] = fold_label
        fold_frame["split_mode"] = validation_mode
        fold_predictions.append(fold_frame)

    if not fold_predictions:
        raise ValueError("All folds were skipped because the training labels had only one class.")

    predictions = pd.concat(fold_predictions).sort_index()
    predictions = apply_trade_schedule(
        predictions=predictions,
        probability_column="gated_probability",
        signal_threshold=signal_threshold,
        cooldown_bars=label_horizon,
        skip_risk_off=True,
    )
    summary = summarize_predictions(predictions=predictions, signal_threshold=signal_threshold)
    summary["symbol"] = symbol.upper()
    summary["feature_count"] = len(feature_columns)
    summary["fold_count"] = int(predictions["fold"].nunique())
    summary["rows"] = int(len(predictions))
    summary["label_horizon"] = label_horizon
    summary["cost_bps"] = cost_bps
    summary["start_date"] = start_date
    summary["end_date"] = end_date
    summary["purge_size"] = purge_size
    summary["feature_lag"] = feature_lag
    summary["use_gate_model"] = use_gate_model
    summary["validation_mode"] = validation_mode
    if validation_mode == "calendar":
        summary["train_years"] = train_years
        summary["validation_years"] = validation_years
        summary["holdout_start"] = holdout_start
        holdout_predictions = predictions.loc[predictions["fold_label"] == "holdout"]
        if not holdout_predictions.empty:
            holdout_summary = summarize_predictions(
                predictions=holdout_predictions,
                signal_threshold=signal_threshold,
            )
            for key, value in holdout_summary.items():
                summary[f"holdout_{key}"] = value
    return predictions, summary


def apply_trade_schedule(
    predictions: pd.DataFrame,
    probability_column: str,
    signal_threshold: float,
    cooldown_bars: int,
    skip_risk_off: bool,
) -> pd.DataFrame:
    frame = predictions.copy().sort_index()
    probabilities = frame[probability_column].to_numpy(dtype=float)
    net_returns = frame["net_forward_return"].to_numpy(dtype=float)
    risk_off = (
        frame["regime_risk_off"].fillna(0.0).to_numpy(dtype=float)
        if "regime_risk_off" in frame.columns
        else np.zeros(len(frame), dtype=float)
    )

    take_trade = np.zeros(len(frame), dtype=bool)
    strategy_return = np.zeros(len(frame), dtype=float)
    cooldown = 0

    for index in range(len(frame)):
        if cooldown > 0:
            cooldown -= 1
            continue

        blocked = skip_risk_off and risk_off[index] >= 1.0
        if probabilities[index] >= signal_threshold and not blocked:
            take_trade[index] = True
            strategy_return[index] = net_returns[index]
            cooldown = max(cooldown_bars - 1, 0)

    frame["take_trade"] = take_trade.astype(int)
    frame["strategy_return"] = strategy_return
    frame["equity_curve"] = (1.0 + frame["strategy_return"]).cumprod()
    return frame


def summarize_predictions(predictions: pd.DataFrame, signal_threshold: float) -> dict[str, Any]:
    frame = predictions.copy().sort_index()
    y_true = frame["target"].astype(int)
    probabilities = frame["gated_probability"].astype(float)
    labels = (probabilities >= signal_threshold).astype(int)

    summary: dict[str, Any] = {}
    if y_true.nunique() == 2:
        summary["roc_auc"] = float(roc_auc_score(y_true, probabilities))
    else:
        summary["roc_auc"] = None

    summary["brier_score"] = float(brier_score_loss(y_true, probabilities))
    summary["precision_at_threshold"] = float(
        precision_score(y_true, labels, zero_division=0)
    )
    summary["recall_at_threshold"] = float(recall_score(y_true, labels, zero_division=0))

    strategy_returns = frame["strategy_return"].astype(float)
    trade_returns = frame.loc[frame["take_trade"] == 1, "net_forward_return"].astype(float)
    equity_curve = frame["equity_curve"].astype(float)
    years = max((frame.index.max() - frame.index.min()).days / 365.25, len(frame) / 252.0)

    final_equity = float(equity_curve.iloc[-1]) if not equity_curve.empty else 1.0
    summary["total_return"] = final_equity - 1.0
    summary["cagr"] = final_equity ** (1.0 / years) - 1.0 if final_equity > 0.0 else None

    volatility = float(strategy_returns.std(ddof=0))
    summary["sharpe"] = (
        float(strategy_returns.mean() / volatility * np.sqrt(252.0)) if volatility > 0.0 else None
    )

    drawdown = equity_curve / equity_curve.cummax() - 1.0
    summary["max_drawdown"] = float(drawdown.min()) if not drawdown.empty else 0.0
    summary["trade_rate"] = float(frame["take_trade"].mean())
    summary["trade_count"] = int(frame["take_trade"].sum())

    gross_profit = float(trade_returns[trade_returns > 0.0].sum())
    gross_loss = float(-trade_returns[trade_returns < 0.0].sum())
    summary["profit_factor"] = (
        gross_profit / gross_loss if gross_loss > 0.0 else None
    )
    summary["hit_rate"] = float((trade_returns > 0.0).mean()) if not trade_returns.empty else None
    summary["average_trade_return"] = float(trade_returns.mean()) if not trade_returns.empty else None
    return summary


def save_outputs(
    predictions: pd.DataFrame,
    summary: dict[str, Any],
    symbol: str,
    project_root: str | Path | None = None,
) -> tuple[Path, Path]:
    root = resolve_project_root(project_root)
    output_dir = root / "outputs" / symbol.lower()
    output_dir.mkdir(parents=True, exist_ok=True)

    predictions_path = output_dir / "walk_forward_predictions.csv"
    summary_path = output_dir / "summary.json"
    predictions.to_csv(predictions_path, index_label="date")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return predictions_path, summary_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a starter walk-forward ML experiment.")
    parser.add_argument("--symbol", required=True, choices=discover_symbols(), help="Ticker symbol to train on.")
    parser.add_argument("--start-date", default=None, help="Optional earliest date to keep after feature engineering, in YYYY-MM-DD.")
    parser.add_argument("--end-date", default=None, help="Optional latest date to keep after feature engineering, in YYYY-MM-DD.")
    parser.add_argument("--horizon", type=int, default=5, help="Forward return horizon in bars.")
    parser.add_argument("--cost-bps", type=float, default=15.0, help="Combined fees and slippage in basis points.")
    parser.add_argument("--min-train-size", type=int, default=160, help="Minimum observations in the first train window.")
    parser.add_argument("--test-size", type=int, default=40, help="Observations in each out-of-sample fold.")
    parser.add_argument("--step-size", type=int, default=40, help="Rows to advance after each fold.")
    parser.add_argument("--embargo-size", type=int, default=5, help="Rows to skip between train and test.")
    parser.add_argument("--purge-size", type=int, default=0, help="Additional rows or days to purge before each test window.")
    parser.add_argument("--feature-lag", type=int, default=0, help="Bars to lag all features before modeling.")
    parser.add_argument("--signal-threshold", type=float, default=0.55, help="Minimum probability to take a trade.")
    parser.add_argument(
        "--validation-mode",
        choices=["row", "calendar"],
        default="row",
        help="Row-count walk-forward or calendar-year walk-forward validation.",
    )
    parser.add_argument("--train-years", type=int, default=5, help="Training years for calendar validation mode.")
    parser.add_argument(
        "--validation-years",
        type=int,
        default=1,
        help="Validation window length in years for calendar validation mode.",
    )
    parser.add_argument(
        "--holdout-start",
        default=None,
        help="Optional final holdout start date in YYYY-MM-DD for calendar validation mode.",
    )
    parser.add_argument(
        "--rolling-train-window",
        action="store_true",
        help="Use a rolling instead of expanding training window in calendar validation mode.",
    )
    parser.add_argument(
        "--no-gate-model",
        action="store_true",
        help="Disable the logistic gate model and use plain probability averaging instead.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    predictions, summary = run_walk_forward_experiment(
        symbol=args.symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        label_horizon=args.horizon,
        cost_bps=args.cost_bps,
        min_train_size=args.min_train_size,
        test_size=args.test_size,
        step_size=args.step_size,
        embargo_size=args.embargo_size,
        purge_size=args.purge_size,
        feature_lag=args.feature_lag,
        signal_threshold=args.signal_threshold,
        validation_mode=args.validation_mode,
        train_years=args.train_years,
        validation_years=args.validation_years,
        holdout_start=args.holdout_start,
        expanding_train=not args.rolling_train_window,
        use_gate_model=not args.no_gate_model,
    )
    predictions_path, summary_path = save_outputs(predictions=predictions, summary=summary, symbol=args.symbol)

    print(json.dumps(summary, indent=2))
    print(f"predictions_saved={predictions_path}")
    print(f"summary_saved={summary_path}")


if __name__ == "__main__":
    main()
