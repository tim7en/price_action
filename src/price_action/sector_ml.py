from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, precision_score, recall_score, roc_auc_score

from .data import resolve_project_root
from .macro_report import REPORT_LOOKBACK_YEARS, SECTOR_BUCKETS, _build_regime_overview, load_model_macro_frame
from .train import apply_trade_schedule, build_base_models, run_walk_forward_experiment

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

DEFAULT_SECTOR_ML_CONFIG: dict[str, Any] = {
    "start_date": "2015-01-01",
    "holdout_start": "2025-01-01",
    "train_years": 5,
    "validation_years": 1,
    "label_horizon": 5,
    "signal_threshold": 0.55,
    "cost_bps": 15.0,
    "embargo_size": 5,
    "purge_size": 5,
    "feature_lag": 1,
    "random_state": 42,
    "fee_bps_base": 10.0,
    "slippage_bps_base": 5.0,
    "fee_scenarios_bps": (5.0, 10.0, 20.0),
    "slippage_scenarios_bps": (0.0, 5.0, 10.0),
}

CRISIS_REGIMES: frozenset[str] = frozenset(
    {
        "Panic Or Forced Liquidation",
        "Credit Deleveraging",
        "Rate-Shock Regime",
        "Stagflation Squeeze",
        "Fragile Late-Cycle Watch",
    }
)


def _safe_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _segment_years(index: pd.Index) -> float:
    if len(index) <= 1:
        return max(len(index) / 252.0, 1.0 / 252.0)
    date_index = pd.DatetimeIndex(index)
    span_years = (date_index.max() - date_index.min()).days / 365.25
    return max(span_years, len(date_index) / 252.0, 1.0 / 252.0)


def _classification_summary(
    frame: pd.DataFrame,
    probability_column: str,
    signal_threshold: float,
) -> dict[str, float | None]:
    if frame.empty:
        return {
            "roc_auc": None,
            "brier_score": None,
            "precision_at_threshold": None,
            "recall_at_threshold": None,
        }

    y_true = frame["target"].astype(int)
    probabilities = frame[probability_column].astype(float)
    labels = (probabilities >= signal_threshold).astype(int)
    summary: dict[str, float | None] = {}
    if y_true.nunique() == 2:
        summary["roc_auc"] = float(roc_auc_score(y_true, probabilities))
    else:
        summary["roc_auc"] = None
    summary["brier_score"] = float(brier_score_loss(y_true, probabilities))
    summary["precision_at_threshold"] = float(precision_score(y_true, labels, zero_division=0))
    summary["recall_at_threshold"] = float(recall_score(y_true, labels, zero_division=0))
    return summary


def _strategy_summary(frame: pd.DataFrame) -> dict[str, float | int | None]:
    if frame.empty:
        return {
            "total_return": 0.0,
            "cagr": None,
            "sharpe": None,
            "sortino": None,
            "max_drawdown": 0.0,
            "calmar": None,
            "profit_factor": None,
            "hit_rate": None,
            "average_trade_return": None,
            "average_win": None,
            "average_loss": None,
            "trade_rate": 0.0,
            "trade_count": 0,
            "turnover_per_year": 0.0,
        }

    strategy_returns = frame["strategy_return"].astype(float)
    trade_returns = frame.loc[frame["take_trade"] == 1, "net_forward_return"].astype(float)
    equity_curve = frame["equity_curve"].astype(float)
    years = _segment_years(frame.index)

    final_equity = float(equity_curve.iloc[-1]) if not equity_curve.empty else 1.0
    total_return = final_equity - 1.0
    cagr = final_equity ** (1.0 / years) - 1.0 if final_equity > 0.0 else None

    volatility = float(strategy_returns.std(ddof=0))
    sharpe = float(strategy_returns.mean() / volatility * np.sqrt(252.0)) if volatility > 0.0 else None

    downside_returns = strategy_returns[strategy_returns < 0.0]
    downside_volatility = float(downside_returns.std(ddof=0)) if not downside_returns.empty else 0.0
    sortino = (
        float(strategy_returns.mean() / downside_volatility * np.sqrt(252.0))
        if downside_volatility > 0.0
        else None
    )

    drawdown = equity_curve / equity_curve.cummax() - 1.0
    max_drawdown = float(drawdown.min()) if not drawdown.empty else 0.0
    calmar = float(cagr / abs(max_drawdown)) if cagr is not None and max_drawdown < 0.0 else None

    gross_profit = float(trade_returns[trade_returns > 0.0].sum())
    gross_loss = float(-trade_returns[trade_returns < 0.0].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0.0 else None

    trade_count = int(frame["take_trade"].sum())
    return {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_drawdown,
        "calmar": calmar,
        "profit_factor": profit_factor,
        "hit_rate": float((trade_returns > 0.0).mean()) if not trade_returns.empty else None,
        "average_trade_return": float(trade_returns.mean()) if not trade_returns.empty else None,
        "average_win": float(trade_returns[trade_returns > 0.0].mean()) if (trade_returns > 0.0).any() else None,
        "average_loss": float(trade_returns[trade_returns < 0.0].mean()) if (trade_returns < 0.0).any() else None,
        "trade_rate": float(frame["take_trade"].mean()),
        "trade_count": trade_count,
        "turnover_per_year": float(trade_count / years) if years > 0.0 else 0.0,
    }


def _evaluate_probability_column(
    predictions: pd.DataFrame,
    probability_column: str,
    signal_threshold: float,
    label_horizon: int,
    cost_bps: float,
) -> tuple[pd.DataFrame, dict[str, float | int | None]]:
    frame = predictions.copy().sort_index()
    frame["net_forward_return"] = frame["forward_return"].astype(float) - cost_bps / 10_000.0
    scheduled = apply_trade_schedule(
        predictions=frame,
        probability_column=probability_column,
        signal_threshold=signal_threshold,
        cooldown_bars=label_horizon,
        skip_risk_off=True,
    )
    scheduled["year"] = scheduled.index.year
    scheduled["is_crisis_period"] = scheduled["regime_label"].isin(CRISIS_REGIMES)
    summary = {
        **_classification_summary(
            frame=scheduled,
            probability_column=probability_column,
            signal_threshold=signal_threshold,
        ),
        **_strategy_summary(scheduled),
    }
    return scheduled, summary


def _summarize_grouped_strategy(frame: pd.DataFrame, group_column: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for group_value, group in frame.groupby(group_column, dropna=False):
        summary = _strategy_summary(group)
        rows.append(
            {
                group_column: group_value,
                **summary,
            }
        )

    summary_frame = pd.DataFrame(rows)
    if not summary_frame.empty:
        summary_frame = summary_frame.sort_values(group_column).reset_index(drop=True)
    return summary_frame


def _stability_score(
    validation_summary: dict[str, float | int | None],
    holdout_summary: dict[str, float | int | None],
) -> float:
    validation_brier = _safe_float(validation_summary.get("brier_score")) or 0.25
    holdout_brier = _safe_float(holdout_summary.get("brier_score")) or 0.25
    validation_auc = _safe_float(validation_summary.get("roc_auc")) or 0.5
    holdout_auc = _safe_float(holdout_summary.get("roc_auc")) or 0.5
    validation_sharpe = _safe_float(validation_summary.get("sharpe")) or 0.0
    holdout_sharpe = _safe_float(holdout_summary.get("sharpe")) or 0.0
    validation_cagr = _safe_float(validation_summary.get("cagr")) or 0.0
    holdout_cagr = _safe_float(holdout_summary.get("cagr")) or 0.0
    validation_drawdown = abs(_safe_float(validation_summary.get("max_drawdown")) or 0.0)
    holdout_drawdown = abs(_safe_float(holdout_summary.get("max_drawdown")) or 0.0)
    validation_trade_rate = _safe_float(validation_summary.get("trade_rate")) or 0.0
    holdout_trade_rate = _safe_float(holdout_summary.get("trade_rate")) or 0.0

    penalties = [
        min(max(holdout_brier - validation_brier, 0.0) / 0.08, 1.0),
        min(max(validation_auc - holdout_auc, 0.0) / 0.15, 1.0),
        min(max(validation_sharpe - holdout_sharpe, 0.0) / 1.5, 1.0),
        min(max(validation_cagr - holdout_cagr, 0.0) / 0.25, 1.0),
        min(max(holdout_drawdown - validation_drawdown, 0.0) / 0.15, 1.0),
        min(abs(validation_trade_rate - holdout_trade_rate) / 0.15, 1.0),
    ]
    return round(max(0.0, 100.0 * (1.0 - float(np.mean(penalties)))), 1)


def _best_model_row(comparison_frame: pd.DataFrame) -> dict[str, Any]:
    ranked = comparison_frame.copy()
    ranked["_holdout_sharpe"] = ranked["holdout_sharpe"].fillna(-99.0)
    ranked["_holdout_brier_score"] = ranked["holdout_brier_score"].fillna(1.0)
    ranked = ranked.sort_values(
        ["stability_score", "_holdout_sharpe", "_holdout_brier_score"],
        ascending=[False, False, True],
    )
    return ranked.iloc[0].to_dict()


def _regime_daily_map(project_root: Path) -> pd.DataFrame:
    macro_frame = load_model_macro_frame(project_root=project_root)
    regime_overview = _build_regime_overview(frame=macro_frame, lookback_years=REPORT_LOOKBACK_YEARS)
    return regime_overview["history_frame"][["regime_label", "quadrant_label"]].copy()


def _join_daily_regimes(predictions: pd.DataFrame, regime_daily_map: pd.DataFrame) -> pd.DataFrame:
    daily = regime_daily_map.reindex(predictions.index, method="ffill")
    frame = predictions.join(daily, how="left")
    frame["regime_label"] = frame["regime_label"].fillna("Unknown")
    frame["quadrant_label"] = frame["quadrant_label"].fillna("Unknown")
    return frame


def _cost_sensitivity_rows(
    holdout_predictions: pd.DataFrame,
    sector: dict[str, str],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    signal_threshold = float(config["signal_threshold"])
    label_horizon = int(config["label_horizon"])
    base_slippage = float(config["slippage_bps_base"])
    base_fee = float(config["fee_bps_base"])

    for fee_bps in config["fee_scenarios_bps"]:
        total_cost_bps = float(fee_bps) + base_slippage
        _, metrics = _evaluate_probability_column(
            predictions=holdout_predictions,
            probability_column="ensemble_probability",
            signal_threshold=signal_threshold,
            label_horizon=label_horizon,
            cost_bps=total_cost_bps,
        )
        rows.append(
            {
                "symbol": sector["symbol"],
                "sector_label": sector["label"],
                "sensitivity_type": "fee",
                "scenario_bps": float(fee_bps),
                "total_cost_bps": total_cost_bps,
                **metrics,
            }
        )

    for slippage_bps in config["slippage_scenarios_bps"]:
        total_cost_bps = base_fee + float(slippage_bps)
        _, metrics = _evaluate_probability_column(
            predictions=holdout_predictions,
            probability_column="ensemble_probability",
            signal_threshold=signal_threshold,
            label_horizon=label_horizon,
            cost_bps=total_cost_bps,
        )
        rows.append(
            {
                "symbol": sector["symbol"],
                "sector_label": sector["label"],
                "sensitivity_type": "slippage",
                "scenario_bps": float(slippage_bps),
                "total_cost_bps": total_cost_bps,
                **metrics,
            }
        )

    return rows


def build_sector_ml_view(project_root: str | Path | None = None) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    config = dict(DEFAULT_SECTOR_ML_CONFIG)
    regime_daily_map = _regime_daily_map(project_root=root)
    boosting_backend = build_base_models(int(config["random_state"]))["lightgbm"].__class__.__name__

    sector_rows: list[dict[str, Any]] = []
    comparison_rows: list[dict[str, Any]] = []
    yearly_rows: list[dict[str, Any]] = []
    regime_rows: list[dict[str, Any]] = []
    cost_rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    for sector in SECTOR_BUCKETS:
        try:
            predictions, summary = run_walk_forward_experiment(
                symbol=sector["symbol"],
                project_root=root,
                start_date=str(config["start_date"]),
                label_horizon=int(config["label_horizon"]),
                cost_bps=float(config["cost_bps"]),
                embargo_size=int(config["embargo_size"]),
                purge_size=int(config["purge_size"]),
                signal_threshold=float(config["signal_threshold"]),
                random_state=int(config["random_state"]),
                validation_mode="calendar",
                train_years=int(config["train_years"]),
                validation_years=int(config["validation_years"]),
                holdout_start=str(config["holdout_start"]),
                feature_lag=int(config["feature_lag"]),
                use_gate_model=False,
            )
        except Exception as exc:
            failures.append(
                {
                    "symbol": sector["symbol"],
                    "sector_label": sector["label"],
                    "message": str(exc),
                }
            )
            continue

        predictions = _join_daily_regimes(predictions=predictions, regime_daily_map=regime_daily_map)
        validation_predictions = predictions.loc[predictions["fold_label"].astype(str) != "holdout"].copy()
        holdout_predictions = predictions.loc[predictions["fold_label"].astype(str) == "holdout"].copy()

        model_frame_rows: list[dict[str, Any]] = []
        ensemble_all_summary: dict[str, Any] | None = None
        ensemble_holdout_summary: dict[str, Any] | None = None
        ensemble_crisis_summary: dict[str, Any] | None = None

        for spec in MODEL_SPECS:
            _, validation_summary = _evaluate_probability_column(
                predictions=validation_predictions,
                probability_column=spec["probability_column"],
                signal_threshold=float(config["signal_threshold"]),
                label_horizon=int(config["label_horizon"]),
                cost_bps=float(config["cost_bps"]),
            )
            holdout_scheduled, holdout_summary = _evaluate_probability_column(
                predictions=holdout_predictions,
                probability_column=spec["probability_column"],
                signal_threshold=float(config["signal_threshold"]),
                label_horizon=int(config["label_horizon"]),
                cost_bps=float(config["cost_bps"]),
            )
            stability_score = _stability_score(
                validation_summary=validation_summary,
                holdout_summary=holdout_summary,
            )
            row = {
                "symbol": sector["symbol"],
                "sector_label": sector["label"],
                "family": sector["family"],
                "model_key": spec["key"],
                "model_label": spec["label"],
                "validation_roc_auc": validation_summary.get("roc_auc"),
                "validation_brier_score": validation_summary.get("brier_score"),
                "validation_sharpe": validation_summary.get("sharpe"),
                "validation_cagr": validation_summary.get("cagr"),
                "validation_max_drawdown": validation_summary.get("max_drawdown"),
                "validation_trade_rate": validation_summary.get("trade_rate"),
                "validation_trade_count": validation_summary.get("trade_count"),
                "holdout_roc_auc": holdout_summary.get("roc_auc"),
                "holdout_brier_score": holdout_summary.get("brier_score"),
                "holdout_sharpe": holdout_summary.get("sharpe"),
                "holdout_sortino": holdout_summary.get("sortino"),
                "holdout_cagr": holdout_summary.get("cagr"),
                "holdout_max_drawdown": holdout_summary.get("max_drawdown"),
                "holdout_calmar": holdout_summary.get("calmar"),
                "holdout_profit_factor": holdout_summary.get("profit_factor"),
                "holdout_hit_rate": holdout_summary.get("hit_rate"),
                "holdout_average_win": holdout_summary.get("average_win"),
                "holdout_average_loss": holdout_summary.get("average_loss"),
                "holdout_turnover_per_year": holdout_summary.get("turnover_per_year"),
                "holdout_trade_rate": holdout_summary.get("trade_rate"),
                "holdout_trade_count": holdout_summary.get("trade_count"),
                "stability_score": stability_score,
                "feature_count": summary["feature_count"],
                "fold_count": summary["fold_count"],
            }
            model_frame_rows.append(row)

            if spec["key"] == "average_ensemble":
                ensemble_all_scheduled, ensemble_all_summary = _evaluate_probability_column(
                    predictions=predictions,
                    probability_column=spec["probability_column"],
                    signal_threshold=float(config["signal_threshold"]),
                    label_horizon=int(config["label_horizon"]),
                    cost_bps=float(config["cost_bps"]),
                )
                ensemble_holdout_summary = holdout_summary
                ensemble_crisis_summary = _strategy_summary(
                    ensemble_all_scheduled.loc[ensemble_all_scheduled["is_crisis_period"]]
                )
                yearly_frame = _summarize_grouped_strategy(ensemble_all_scheduled, "year")
                yearly_frame.insert(0, "sector_label", sector["label"])
                yearly_frame.insert(0, "symbol", sector["symbol"])
                yearly_rows.extend(yearly_frame.to_dict(orient="records"))

                regime_frame = _summarize_grouped_strategy(ensemble_all_scheduled, "regime_label")
                regime_frame.insert(0, "sector_label", sector["label"])
                regime_frame.insert(0, "symbol", sector["symbol"])
                regime_rows.extend(regime_frame.to_dict(orient="records"))

                cost_rows.extend(
                    _cost_sensitivity_rows(
                        holdout_predictions=holdout_predictions,
                        sector=sector,
                        config=config,
                    )
                )

        comparison_frame = pd.DataFrame(model_frame_rows)
        best_model = _best_model_row(comparison_frame)
        comparison_rows.extend(comparison_frame.to_dict(orient="records"))

        ensemble_all_summary = ensemble_all_summary or {}
        ensemble_holdout_summary = ensemble_holdout_summary or {}
        ensemble_crisis_summary = ensemble_crisis_summary or {}
        sector_rows.append(
            {
                "symbol": sector["symbol"],
                "sector_label": sector["label"],
                "family": sector["family"],
                "best_overfit_model": best_model["model_label"],
                "best_overfit_stability_score": best_model["stability_score"],
                "ensemble_validation_roc_auc": comparison_frame.loc[
                    comparison_frame["model_key"] == "average_ensemble", "validation_roc_auc"
                ].iloc[0],
                "ensemble_validation_brier_score": comparison_frame.loc[
                    comparison_frame["model_key"] == "average_ensemble", "validation_brier_score"
                ].iloc[0],
                "ensemble_holdout_roc_auc": comparison_frame.loc[
                    comparison_frame["model_key"] == "average_ensemble", "holdout_roc_auc"
                ].iloc[0],
                "ensemble_holdout_brier_score": comparison_frame.loc[
                    comparison_frame["model_key"] == "average_ensemble", "holdout_brier_score"
                ].iloc[0],
                "ensemble_holdout_cagr": ensemble_holdout_summary.get("cagr"),
                "ensemble_holdout_sharpe": ensemble_holdout_summary.get("sharpe"),
                "ensemble_holdout_sortino": ensemble_holdout_summary.get("sortino"),
                "ensemble_holdout_max_drawdown": ensemble_holdout_summary.get("max_drawdown"),
                "ensemble_holdout_calmar": ensemble_holdout_summary.get("calmar"),
                "ensemble_holdout_profit_factor": ensemble_holdout_summary.get("profit_factor"),
                "ensemble_holdout_hit_rate": ensemble_holdout_summary.get("hit_rate"),
                "ensemble_holdout_average_win": ensemble_holdout_summary.get("average_win"),
                "ensemble_holdout_average_loss": ensemble_holdout_summary.get("average_loss"),
                "ensemble_holdout_turnover_per_year": ensemble_holdout_summary.get("turnover_per_year"),
                "ensemble_holdout_trade_count": ensemble_holdout_summary.get("trade_count"),
                "ensemble_oos_cagr": ensemble_all_summary.get("cagr"),
                "ensemble_oos_sharpe": ensemble_all_summary.get("sharpe"),
                "ensemble_crisis_total_return": ensemble_crisis_summary.get("total_return"),
                "ensemble_crisis_hit_rate": ensemble_crisis_summary.get("hit_rate"),
                "ensemble_crisis_trade_count": ensemble_crisis_summary.get("trade_count"),
                "feature_count": summary["feature_count"],
                "fold_count": summary["fold_count"],
            }
        )

    sector_summary_frame = pd.DataFrame(sector_rows)
    model_comparison_frame = pd.DataFrame(comparison_rows)
    yearly_performance_frame = pd.DataFrame(yearly_rows)
    regime_performance_frame = pd.DataFrame(regime_rows)
    cost_sensitivity_frame = pd.DataFrame(cost_rows)
    failures_frame = pd.DataFrame(failures)

    if sector_summary_frame.empty:
        return {
            "available": False,
            "message": "No sector ML results could be produced.",
            "failures_frame": failures_frame,
        }

    winner_counts = (
        sector_summary_frame["best_overfit_model"]
        .value_counts()
        .rename_axis("model_label")
        .reset_index(name="winner_count")
        .sort_values(["winner_count", "model_label"], ascending=[False, True])
        .reset_index(drop=True)
    )

    holdout_leader = (
        sector_summary_frame.sort_values(
            ["ensemble_holdout_sharpe", "ensemble_holdout_cagr"],
            ascending=[False, False],
        )
        .iloc[0]
        .to_dict()
    )

    robust_cost_rows = cost_sensitivity_frame.loc[
        (cost_sensitivity_frame["sensitivity_type"] == "slippage")
        & (cost_sensitivity_frame["scenario_bps"] == max(config["slippage_scenarios_bps"]))
    ]
    robust_cost_sector_count = int((robust_cost_rows["cagr"].fillna(-1.0) > 0.0).sum()) if not robust_cost_rows.empty else 0

    return {
        "available": True,
        "config": config,
        "boosting_backend": boosting_backend,
        "data_note": (
            "Features are lagged by one bar and each validation window uses a five-bar purge plus a five-bar embargo. "
            "Macro regime attribution comes from the local macro store and is useful for regime slicing, but it is not a point-in-time macro vintage database."
        ),
        "sector_summary_frame": sector_summary_frame,
        "model_comparison_frame": model_comparison_frame,
        "yearly_performance_frame": yearly_performance_frame,
        "regime_performance_frame": regime_performance_frame,
        "cost_sensitivity_frame": cost_sensitivity_frame,
        "winner_counts_frame": winner_counts,
        "failures_frame": failures_frame,
        "holdout_leader": holdout_leader,
        "robust_cost_sector_count": robust_cost_sector_count,
    }