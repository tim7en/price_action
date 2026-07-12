from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone

from .data import build_market_frame, discover_symbols, resolve_project_root
from .features import engineer_daily_features
from .train import build_base_models, calendar_walk_forward_splits, fit_gate_model
from .universe import DEFAULT_PANEL_SYMBOLS, expand_symbol_selection


def build_panel_dataset(
    symbols: list[str],
    label_horizon: int,
    cost_bps: float,
    project_root: str | Path | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    symbol_frames: list[pd.DataFrame] = []
    feature_sets: list[set[str]] = []

    for symbol in symbols:
        market_frame = build_market_frame(symbol=symbol, project_root=project_root)
        dataset, feature_columns = engineer_daily_features(
            market_frame=market_frame,
            label_horizon=label_horizon,
            cost_bps=cost_bps,
        )
        if dataset.empty:
            continue

        frame = dataset.copy()
        frame["symbol"] = symbol.upper()
        symbol_frames.append(frame)
        feature_sets.append(set(feature_columns))

    if not symbol_frames:
        raise ValueError("No symbol produced a usable feature dataset for the panel.")

    common_feature_columns = sorted(set.intersection(*feature_sets)) if feature_sets else []
    if not common_feature_columns:
        raise ValueError("No common feature columns were available across the requested symbols.")

    aligned_frames = [
        frame[common_feature_columns + ["target", "forward_return", "net_forward_return", "symbol"]].dropna()
        for frame in symbol_frames
    ]
    panel = pd.concat(aligned_frames).sort_index()
    panel = panel.rename_axis("date").reset_index()
    panel = panel.sort_values(["date", "symbol"]).reset_index(drop=True)
    symbol_dummies = pd.get_dummies(panel["symbol"], prefix="symbol", dtype=float)
    feature_columns = common_feature_columns + symbol_dummies.columns.tolist()
    panel = pd.concat([panel, symbol_dummies], axis=1)
    return panel, feature_columns


def apply_panel_trade_schedule(
    predictions: pd.DataFrame,
    probability_column: str,
    signal_threshold: float,
    cooldown_bars: int,
    skip_risk_off: bool,
) -> pd.DataFrame:
    scheduled_frames: list[pd.DataFrame] = []
    for symbol, symbol_frame in predictions.groupby("symbol", sort=True):
        frame = symbol_frame.sort_values("date").copy()
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
        frame["symbol_equity_curve"] = (1.0 + frame["strategy_return"]).cumprod()
        frame["symbol"] = symbol
        scheduled_frames.append(frame)

    return pd.concat(scheduled_frames).sort_values(["date", "symbol"]).reset_index(drop=True)


def summarize_panel_predictions(predictions: pd.DataFrame, signal_threshold: float) -> dict[str, Any]:
    from sklearn.metrics import brier_score_loss, precision_score, recall_score, roc_auc_score

    frame = predictions.sort_values(["date", "symbol"]).copy()
    y_true = frame["target"].astype(int)
    probabilities = frame["gated_probability"].astype(float)
    labels = (probabilities >= signal_threshold).astype(int)

    summary: dict[str, Any] = {}
    summary["roc_auc"] = float(roc_auc_score(y_true, probabilities)) if y_true.nunique() == 2 else None
    summary["brier_score"] = float(brier_score_loss(y_true, probabilities))
    summary["precision_at_threshold"] = float(precision_score(y_true, labels, zero_division=0))
    summary["recall_at_threshold"] = float(recall_score(y_true, labels, zero_division=0))

    active_trades = frame.loc[frame["take_trade"] == 1, ["strategy_return"]].copy()
    trade_returns = frame.loc[frame["take_trade"] == 1, "net_forward_return"].astype(float)
    daily_returns = active_trades.groupby(frame.loc[frame["take_trade"] == 1, "date"])["strategy_return"].mean()
    all_dates = pd.DatetimeIndex(sorted(pd.to_datetime(frame["date"]).unique()))
    daily_returns = daily_returns.reindex(all_dates, fill_value=0.0)
    equity_curve = (1.0 + daily_returns).cumprod()

    years = max((all_dates.max() - all_dates.min()).days / 365.25, len(all_dates) / 252.0)
    final_equity = float(equity_curve.iloc[-1]) if not equity_curve.empty else 1.0
    summary["total_return"] = final_equity - 1.0
    summary["cagr"] = final_equity ** (1.0 / years) - 1.0 if final_equity > 0.0 else None

    volatility = float(daily_returns.std(ddof=0))
    summary["sharpe"] = float(daily_returns.mean() / volatility * np.sqrt(252.0)) if volatility > 0.0 else None

    drawdown = equity_curve / equity_curve.cummax() - 1.0
    summary["max_drawdown"] = float(drawdown.min()) if not drawdown.empty else 0.0
    summary["trade_rate"] = float(frame["take_trade"].mean())
    summary["trade_count"] = int(frame["take_trade"].sum())
    summary["active_symbol_count"] = int(frame["symbol"].nunique())

    gross_profit = float(trade_returns[trade_returns > 0.0].sum())
    gross_loss = float(-trade_returns[trade_returns < 0.0].sum())
    summary["profit_factor"] = gross_profit / gross_loss if gross_loss > 0.0 else None
    summary["hit_rate"] = float((trade_returns > 0.0).mean()) if not trade_returns.empty else None
    summary["average_trade_return"] = float(trade_returns.mean()) if not trade_returns.empty else None
    summary["symbols"] = sorted(frame["symbol"].unique().tolist())
    return summary


def run_panel_experiment(
    symbols: list[str],
    project_root: str | Path | None = None,
    label_horizon: int = 5,
    cost_bps: float = 15.0,
    train_years: int = 5,
    validation_years: int = 1,
    embargo_size: int = 5,
    holdout_start: str | None = None,
    signal_threshold: float = 0.55,
    random_state: int = 42,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    panel, feature_columns = build_panel_dataset(
        symbols=symbols,
        label_horizon=label_horizon,
        cost_bps=cost_bps,
        project_root=project_root,
    )

    x = panel[feature_columns]
    y = panel["target"]
    splits, holdout_split = calendar_walk_forward_splits(
        index=pd.DatetimeIndex(panel["date"]),
        train_years=train_years,
        validation_years=validation_years,
        embargo_size=embargo_size,
        holdout_start=holdout_start,
        expanding_train=True,
    )
    if not splits and holdout_split is None:
        raise ValueError("No panel calendar splits were produced.")

    labeled_splits = splits + ([holdout_split] if holdout_split is not None else [])
    fold_predictions: list[pd.DataFrame] = []
    for fold_number, (train_idx, test_idx, fold_label) in enumerate(labeled_splits, start=1):
        x_train = x.iloc[train_idx]
        y_train = y.iloc[train_idx]
        x_test = x.iloc[test_idx]
        fold_frame = panel.iloc[test_idx][["date", "forward_return", "net_forward_return", "symbol"]].copy()

        if y_train.nunique() < 2:
            continue

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
            gate_features = [
                column
                for column in [
                    "prob_elastic_net",
                    "prob_extra_trees",
                    "prob_lightgbm",
                    "regime_risk_off",
                    "risk_off_score",
                    "regime_trend",
                    "trend_score",
                    "momentum_oscillator",
                ]
                if column in fold_frame.columns
            ]
            fold_frame["gated_probability"] = gate_model.predict_proba(fold_frame[gate_features])[:, 1]
        else:
            fold_frame["gated_probability"] = fold_frame["ensemble_probability"]

        fold_frame["target"] = panel.iloc[test_idx]["target"]
        fold_frame["fold"] = fold_number
        fold_frame["fold_label"] = fold_label
        fold_predictions.append(fold_frame)

    if not fold_predictions:
        raise ValueError("All panel folds were skipped because the training labels had only one class.")

    predictions = pd.concat(fold_predictions).sort_values(["date", "symbol"]).reset_index(drop=True)
    predictions = apply_panel_trade_schedule(
        predictions=predictions,
        probability_column="gated_probability",
        signal_threshold=signal_threshold,
        cooldown_bars=label_horizon,
        skip_risk_off=True,
    )
    summary = summarize_panel_predictions(predictions=predictions, signal_threshold=signal_threshold)
    summary["panel_name"] = "default_panel" if symbols == DEFAULT_PANEL_SYMBOLS else "custom_panel"
    summary["feature_count"] = len(feature_columns)
    summary["fold_count"] = int(predictions["fold"].nunique())
    summary["rows"] = int(len(predictions))
    summary["label_horizon"] = label_horizon
    summary["cost_bps"] = cost_bps
    summary["validation_mode"] = "calendar"
    summary["train_years"] = train_years
    summary["validation_years"] = validation_years
    summary["holdout_start"] = holdout_start

    holdout_predictions = predictions.loc[predictions["fold_label"] == "holdout"]
    if not holdout_predictions.empty:
        holdout_summary = summarize_panel_predictions(
            predictions=holdout_predictions,
            signal_threshold=signal_threshold,
        )
        for key, value in holdout_summary.items():
            summary[f"holdout_{key}"] = value
    return predictions, summary


def save_panel_outputs(
    predictions: pd.DataFrame,
    summary: dict[str, Any],
    panel_name: str,
    project_root: str | Path | None = None,
) -> tuple[Path, Path]:
    root = resolve_project_root(project_root)
    output_dir = root / "outputs" / panel_name
    output_dir.mkdir(parents=True, exist_ok=True)

    predictions_path = output_dir / "panel_walk_forward_predictions.csv"
    summary_path = output_dir / "summary.json"
    predictions.to_csv(predictions_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return predictions_path, summary_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a pooled panel walk-forward experiment.")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["PANEL"],
        help="Symbols to include. Use PANEL to expand to the repo's default panel universe.",
    )
    parser.add_argument("--horizon", type=int, default=5, help="Forward return horizon in bars.")
    parser.add_argument("--cost-bps", type=float, default=15.0, help="Combined fees and slippage in basis points.")
    parser.add_argument("--train-years", type=int, default=5, help="Training years for calendar validation.")
    parser.add_argument("--validation-years", type=int, default=1, help="Validation years per fold.")
    parser.add_argument("--embargo-size", type=int, default=5, help="Rows to skip between train and test.")
    parser.add_argument("--holdout-start", default="2025-01-01", help="Optional final holdout start date in YYYY-MM-DD.")
    parser.add_argument("--signal-threshold", type=float, default=0.55, help="Minimum probability to take a trade.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    symbols = expand_symbol_selection(list(args.symbols))
    predictions, summary = run_panel_experiment(
        symbols=symbols,
        label_horizon=args.horizon,
        cost_bps=args.cost_bps,
        train_years=args.train_years,
        validation_years=args.validation_years,
        embargo_size=args.embargo_size,
        holdout_start=args.holdout_start,
        signal_threshold=args.signal_threshold,
    )
    panel_name = "default_panel" if symbols == DEFAULT_PANEL_SYMBOLS else "custom_panel"
    predictions_path, summary_path = save_panel_outputs(predictions=predictions, summary=summary, panel_name=panel_name)
    print(json.dumps(summary, indent=2))
    print(f"predictions_saved={predictions_path}")
    print(f"summary_saved={summary_path}")


if __name__ == "__main__":
    main()
