from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, precision_score, recall_score, roc_auc_score

from .data import load_asset_daily, resolve_project_root
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
    "start_date": "2000-01-01",
    "holdout_start": "2025-01-01",
    "historical_benchmark_start": "2006-01-01",
    "rebalance_interval_scenarios": (5, 10, 21),
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
    "top_n": 3,
    "quality_weight": 0.25,
    "leverage_multiple": 3.0,
    "annual_financing_rate": 0.06,
    "core_sector_weight": 0.60,
    "reserve_cash_weight": 0.40,
    "cash_yield_rate": 0.05,
    "reserve_drawdown_first": 0.05,
    "reserve_drawdown_second": 0.10,
    "reserve_drawdown_full": 0.20,
    "reserve_deploy_first": 0.10,
    "reserve_deploy_second": 0.20,
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

RESERVE_STRATEGY_LABEL = "Quality Rotation + SPY Reserve Sleeve"
RESERVE_SLEEVE_SYMBOL = "SPY"


def _safe_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _normalised_rank(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.dropna().nunique() <= 1:
        return pd.Series(0.5, index=numeric.index, dtype="float64")
    return numeric.rank(pct=True, method="average").fillna(0.5)


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


def _periodic_strategy_summary(
    frame: pd.DataFrame,
    return_column: str,
    turnover_column: str | None = None,
) -> dict[str, float | int | None]:
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
            "trade_count": 0,
            "period_count": 0,
            "entry_count": 0,
            "turnover_per_year": 0.0,
        }

    returns = frame[return_column].astype(float)
    equity_curve = (1.0 + returns).cumprod()
    years = _segment_years(frame.index)
    periods_per_year = max(len(frame.index) / years, 1.0)
    final_equity = float(equity_curve.iloc[-1]) if not equity_curve.empty else 1.0
    total_return = final_equity - 1.0
    cagr = final_equity ** (1.0 / years) - 1.0 if final_equity > 0.0 else None

    volatility = float(returns.std(ddof=0))
    sharpe = float(returns.mean() / volatility * np.sqrt(periods_per_year)) if volatility > 0.0 else None

    downside = returns[returns < 0.0]
    downside_volatility = float(downside.std(ddof=0)) if not downside.empty else 0.0
    sortino = (
        float(returns.mean() / downside_volatility * np.sqrt(periods_per_year))
        if downside_volatility > 0.0
        else None
    )

    drawdown = equity_curve / equity_curve.cummax() - 1.0
    max_drawdown = float(drawdown.min()) if not drawdown.empty else 0.0
    calmar = float(cagr / abs(max_drawdown)) if cagr is not None and max_drawdown < 0.0 else None

    gross_profit = float(returns[returns > 0.0].sum())
    gross_loss = float(-returns[returns < 0.0].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0.0 else None

    turnover_series = (
        pd.to_numeric(frame[turnover_column], errors="coerce").fillna(0.0)
        if turnover_column is not None and turnover_column in frame.columns
        else pd.Series(0.0, index=frame.index, dtype="float64")
    )
    turnover = float(turnover_series.sum())
    entry_count = 0
    trade_count = int((turnover_series > 1e-12).sum())
    if turnover_column is None:
        entry_count = 1 if len(frame.index) > 0 else 0
        trade_count = entry_count

    return {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_drawdown,
        "calmar": calmar,
        "profit_factor": profit_factor,
        "hit_rate": float((returns > 0.0).mean()) if not returns.empty else None,
        "average_trade_return": float(returns.mean()) if not returns.empty else None,
        "average_win": float(returns[returns > 0.0].mean()) if (returns > 0.0).any() else None,
        "average_loss": float(returns[returns < 0.0].mean()) if (returns < 0.0).any() else None,
        "trade_count": trade_count,
        "period_count": int(len(frame.index)),
        "entry_count": entry_count,
        "turnover_per_year": float(turnover / years) if years > 0.0 else 0.0,
    }


def _validation_quality_frame(sector_summary_frame: pd.DataFrame) -> pd.DataFrame:
    frame = sector_summary_frame[
        [
            "symbol",
            "sector_label",
            "family",
            "ensemble_validation_roc_auc",
            "ensemble_validation_brier_score",
            "ensemble_validation_sharpe",
            "ensemble_validation_cagr",
        ]
    ].copy()
    frame["rank_validation_auc"] = _normalised_rank(frame["ensemble_validation_roc_auc"])
    frame["rank_validation_brier"] = _normalised_rank(-frame["ensemble_validation_brier_score"])
    frame["rank_validation_sharpe"] = _normalised_rank(frame["ensemble_validation_sharpe"])
    frame["rank_validation_cagr"] = _normalised_rank(frame["ensemble_validation_cagr"])
    frame["validation_quality_score"] = (
        0.35 * frame["rank_validation_auc"]
        + 0.25 * frame["rank_validation_brier"]
        + 0.25 * frame["rank_validation_sharpe"]
        + 0.15 * frame["rank_validation_cagr"]
    )
    return frame.sort_values("validation_quality_score", ascending=False).reset_index(drop=True)


def _build_point_in_time_quality(
    validation_predictions_by_symbol: dict[str, pd.DataFrame],
    signal_frame: pd.DataFrame,
    config: dict[str, Any],
    min_validation_folds: int = 1,
) -> pd.DataFrame:
    """Build a (signal_year, symbol) -> validation_quality_score lookup.

    For each signal year Y, the per-sector quality score is computed from
    validation folds whose calendar fold-year is strictly less than Y. Ranks
    are then taken cross-sectionally at each Y so a 2010 trade sees only
    validation evidence available before 2010. This replaces the legacy
    full-validation-window aggregate used by the historical rotation view.
    """
    empty = pd.DataFrame(columns=["signal_year", "symbol", "validation_quality_score"])
    if not validation_predictions_by_symbol or signal_frame.empty:
        return empty

    signal_years = sorted(int(year) for year in pd.to_datetime(signal_frame["date"]).dt.year.unique())
    signal_threshold = float(config["signal_threshold"])
    label_horizon = int(config["label_horizon"])
    cost_bps = float(config["cost_bps"])

    fold_year_lookup: dict[str, pd.Series] = {}
    for symbol, validation in validation_predictions_by_symbol.items():
        if validation.empty:
            continue
        fold_year_lookup[symbol] = pd.to_numeric(
            validation["fold_label"].astype(str), errors="coerce"
        )

    rows: list[dict[str, Any]] = []
    for signal_year in signal_years:
        per_sector: list[dict[str, Any]] = []
        for symbol, validation in validation_predictions_by_symbol.items():
            fold_years = fold_year_lookup.get(symbol)
            if fold_years is None:
                continue
            prior_mask = fold_years.notna() & (fold_years < signal_year)
            if int(fold_years[prior_mask].nunique()) < min_validation_folds:
                continue
            prior = validation.loc[prior_mask]
            if prior.empty:
                continue
            try:
                _, summary = _evaluate_probability_column(
                    predictions=prior,
                    probability_column="ensemble_probability",
                    signal_threshold=signal_threshold,
                    label_horizon=label_horizon,
                    cost_bps=cost_bps,
                )
            except Exception:
                continue
            per_sector.append(
                {
                    "symbol": symbol,
                    "roc_auc": summary.get("roc_auc"),
                    "brier_score": summary.get("brier_score"),
                    "sharpe": summary.get("sharpe"),
                    "cagr": summary.get("cagr"),
                }
            )
        if not per_sector:
            continue
        snapshot = pd.DataFrame(per_sector)
        snapshot["rank_auc"] = _normalised_rank(snapshot["roc_auc"])
        snapshot["rank_brier"] = _normalised_rank(-snapshot["brier_score"])
        snapshot["rank_sharpe"] = _normalised_rank(snapshot["sharpe"])
        snapshot["rank_cagr"] = _normalised_rank(snapshot["cagr"])
        snapshot["validation_quality_score"] = (
            0.35 * snapshot["rank_auc"]
            + 0.25 * snapshot["rank_brier"]
            + 0.25 * snapshot["rank_sharpe"]
            + 0.15 * snapshot["rank_cagr"]
        )
        snapshot["signal_year"] = int(signal_year)
        rows.extend(
            snapshot[["signal_year", "symbol", "validation_quality_score"]].to_dict(orient="records")
        )

    if not rows:
        return empty
    return pd.DataFrame(rows)


def _load_price_panel(symbols: list[str], project_root: Path) -> pd.DataFrame:
    close_frames: list[pd.Series] = []
    for symbol in symbols:
        close = pd.to_numeric(
            load_asset_daily(symbol, project_root=project_root)["close"],
            errors="coerce",
        ).rename(symbol)
        close_frames.append(close)
    prices = pd.concat(close_frames, axis=1).sort_index().ffill().dropna(how="all")
    return prices


def _weights_from_scores(scores: pd.Series, top_n: int) -> tuple[dict[str, float], str]:
    valid = pd.to_numeric(scores, errors="coerce").dropna()
    if valid.empty:
        return {}, "Cash"
    selected = valid.sort_values(ascending=False).head(top_n)
    if selected.empty or float(selected.sum()) <= 0.0:
        return {}, "Cash"
    weights = (selected / selected.sum()).to_dict()
    return {str(symbol): float(weight) for symbol, weight in weights.items()}, ", ".join(selected.index.tolist())


def _turnover_cost(previous: dict[str, float], current: dict[str, float], cost_rate: float) -> tuple[float, float]:
    symbols = set(previous) | set(current)
    turnover = float(sum(abs(current.get(symbol, 0.0) - previous.get(symbol, 0.0)) for symbol in symbols))
    return turnover, turnover * cost_rate


def _weighted_return(weights: dict[str, float], period_returns: pd.Series) -> float:
    if not weights:
        return 0.0
    return float(sum(weight * float(period_returns.get(symbol, 0.0)) for symbol, weight in weights.items()))


def _period_year_fraction(entry_date: pd.Timestamp, exit_date: pd.Timestamp) -> float:
    return max((pd.Timestamp(exit_date) - pd.Timestamp(entry_date)).days / 365.25, 0.0)


def _leveraged_period_return(
    gross_return: float,
    turnover_cost: float,
    period_year_fraction: float,
    leverage_multiple: float,
    annual_financing_rate: float,
) -> float:
    borrowed_multiple = max(leverage_multiple - 1.0, 0.0)
    financing_cost = borrowed_multiple * annual_financing_rate * period_year_fraction
    net_return = leverage_multiple * gross_return - leverage_multiple * turnover_cost - financing_cost
    return max(net_return, -0.999)


def _cash_period_return(cash_yield_rate: float, period_year_fraction: float) -> float:
    return float((1.0 + cash_yield_rate) ** period_year_fraction - 1.0)


def _reserve_target_fraction(
    current_drawdown: float,
    current_fraction: float,
    config: dict[str, Any],
) -> float:
    first_drawdown = float(config["reserve_drawdown_first"])
    second_drawdown = float(config["reserve_drawdown_second"])
    full_drawdown = float(config["reserve_drawdown_full"])
    first_fraction = float(config["reserve_deploy_first"])
    second_fraction = float(config["reserve_deploy_second"])

    if current_drawdown <= -full_drawdown:
        return 1.0
    if current_drawdown <= -second_drawdown:
        return max(current_fraction, second_fraction)
    if current_drawdown <= -first_drawdown:
        return max(current_fraction, first_fraction)
    if current_drawdown >= 0.0:
        return 0.0
    return current_fraction


def _summarize_period_groups(
    period_frame: pd.DataFrame,
    strategy_column: str,
    group_column: str,
    turnover_column: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for group_value, group in period_frame.groupby(group_column, dropna=False):
        summary = _periodic_strategy_summary(group.set_index("exit_date"), strategy_column, turnover_column=turnover_column)
        group_years = _segment_years(pd.DatetimeIndex(group["exit_date"]))
        if group_years < 0.5 or len(group.index) < 3:
            summary["cagr"] = None
            summary["sharpe"] = None
            summary["sortino"] = None
            summary["calmar"] = None
        rows.append({group_column: group_value, **summary})
    summary_frame = pd.DataFrame(rows)
    if not summary_frame.empty:
        summary_frame = summary_frame.sort_values(group_column).reset_index(drop=True)
    return summary_frame


def _build_rotation_backtest_view(
    signal_frame: pd.DataFrame,
    validation_quality_frame: pd.DataFrame,
    project_root: Path,
    config: dict[str, Any],
    scope_label: str,
    scope_kind: str,
    scope_note: str,
    holding_period_bars: int | None = None,
    rebalance_interval_bars: int | None = None,
    quality_lookup_frame: pd.DataFrame | None = None,
) -> dict[str, Any]:
    if signal_frame.empty:
        return {"available": False, "message": f"No predictions were available for {scope_label.lower()}."}

    signal_frame = signal_frame.copy()
    signal_frame["date"] = pd.to_datetime(signal_frame["date"])
    quality_weight = float(config["quality_weight"])
    if quality_lookup_frame is not None and not quality_lookup_frame.empty:
        signal_frame["signal_year"] = signal_frame["date"].dt.year.astype(int)
        lookup = quality_lookup_frame[
            ["signal_year", "symbol", "validation_quality_score"]
        ].copy()
        lookup["signal_year"] = lookup["signal_year"].astype(int)
        signal_frame = signal_frame.merge(
            lookup,
            on=["signal_year", "symbol"],
            how="left",
        )
        signal_frame["validation_quality_score"] = signal_frame[
            "validation_quality_score"
        ].fillna(0.5)
        signal_frame = signal_frame.drop(columns=["signal_year"])
    else:
        quality_map = validation_quality_frame.set_index("symbol")["validation_quality_score"]
        signal_frame["validation_quality_score"] = (
            signal_frame["symbol"].map(quality_map).fillna(0.5)
        )
    signal_frame["quality_weighted_score"] = (
        (1.0 - quality_weight) * signal_frame["ensemble_probability"].astype(float)
        + quality_weight * signal_frame["validation_quality_score"].astype(float)
    )

    symbols = sorted(signal_frame["symbol"].unique().tolist())
    price_panel = _load_price_panel(symbols + ["SPY"], project_root=project_root)
    trading_index = price_panel.index
    signal_dates = sorted(date for date in signal_frame["date"].unique() if date in trading_index)
    if len(signal_dates) < 3:
        return {"available": False, "message": f"Not enough signal dates were available to build {scope_label.lower()}."}

    top_n = int(config["top_n"])
    threshold = float(config["signal_threshold"])
    holding_period = int(holding_period_bars or config["label_horizon"])
    rebalance_interval = int(rebalance_interval_bars or holding_period)
    cost_rate = float(config["cost_bps"]) / 10_000.0
    leverage_multiple = float(config["leverage_multiple"])
    annual_financing_rate = float(config["annual_financing_rate"])
    core_sector_weight = float(config["core_sector_weight"])
    reserve_cash_weight = float(config["reserve_cash_weight"])
    cash_yield_rate = float(config["cash_yield_rate"])
    spy_drawdown_series = price_panel["SPY"] / price_panel["SPY"].cummax() - 1.0

    previous_weights = {
        "probability": {},
        "quality": {},
        "reserve": {},
    }
    reserve_deployed_fraction = 0.0
    period_rows: list[dict[str, Any]] = []
    signal_pointer = 0

    while signal_pointer < len(signal_dates):
        signal_date = signal_dates[signal_pointer]
        signal_slice = signal_frame.loc[signal_frame["date"] == signal_date].copy()
        signal_slice = signal_slice.loc[signal_slice["ensemble_probability"].astype(float) >= threshold].copy()

        entry_pos = trading_index.searchsorted(signal_date, side="right")
        if entry_pos >= len(trading_index):
            break
        exit_pos = min(entry_pos + holding_period, len(trading_index) - 1)
        entry_date = trading_index[entry_pos]
        exit_date = trading_index[exit_pos]
        if exit_date <= entry_date:
            break

        if signal_slice.empty:
            probability_weights, probability_labels = {}, "Cash"
            quality_weights, quality_labels = {}, "Cash"
        else:
            probability_weights, probability_labels = _weights_from_scores(
                signal_slice.set_index("symbol")["ensemble_probability"],
                top_n=top_n,
            )
            quality_weights, quality_labels = _weights_from_scores(
                signal_slice.set_index("symbol")["quality_weighted_score"],
                top_n=top_n,
            )

        period_returns = price_panel.loc[exit_date, symbols] / price_panel.loc[entry_date, symbols] - 1.0
        spy_gross_return = float(price_panel.loc[exit_date, "SPY"] / price_panel.loc[entry_date, "SPY"] - 1.0)
        period_year_fraction = _period_year_fraction(entry_date=entry_date, exit_date=exit_date)
        cash_period_return = _cash_period_return(cash_yield_rate=cash_yield_rate, period_year_fraction=period_year_fraction)
        spy_drawdown_signal = float(spy_drawdown_series.loc[signal_date])

        probability_turnover, probability_cost = _turnover_cost(previous_weights["probability"], probability_weights, cost_rate)
        quality_turnover, quality_cost = _turnover_cost(previous_weights["quality"], quality_weights, cost_rate)
        probability_gross_return = _weighted_return(probability_weights, period_returns)
        quality_gross_return = _weighted_return(quality_weights, period_returns)
        probability_return = probability_gross_return - probability_cost
        quality_return = quality_gross_return - quality_cost
        spy_return = spy_gross_return
        probability_return_x3 = _leveraged_period_return(
            gross_return=probability_gross_return,
            turnover_cost=probability_cost,
            period_year_fraction=period_year_fraction,
            leverage_multiple=leverage_multiple,
            annual_financing_rate=annual_financing_rate,
        )
        quality_return_x3 = _leveraged_period_return(
            gross_return=quality_gross_return,
            turnover_cost=quality_cost,
            period_year_fraction=period_year_fraction,
            leverage_multiple=leverage_multiple,
            annual_financing_rate=annual_financing_rate,
        )
        spy_return_x3 = _leveraged_period_return(
            gross_return=spy_gross_return,
            turnover_cost=0.0,
            period_year_fraction=period_year_fraction,
            leverage_multiple=leverage_multiple,
            annual_financing_rate=annual_financing_rate,
        )

        quality_selected = signal_slice.sort_values("quality_weighted_score", ascending=False)
        reserve_target_fraction = _reserve_target_fraction(
            current_drawdown=spy_drawdown_signal,
            current_fraction=reserve_deployed_fraction,
            config=config,
        )
        reserve_asset_symbol = RESERVE_SLEEVE_SYMBOL if reserve_target_fraction > 0.0 else None
        reserve_invested_weight = reserve_cash_weight * reserve_target_fraction if reserve_asset_symbol else 0.0
        reserve_weights = {reserve_asset_symbol: reserve_invested_weight} if reserve_invested_weight > 0.0 and reserve_asset_symbol else {}
        reserve_turnover, reserve_cost = _turnover_cost(previous_weights["reserve"], reserve_weights, cost_rate)
        reserve_spy_return = (
            reserve_invested_weight * spy_gross_return
            if reserve_asset_symbol is not None and reserve_invested_weight > 0.0
            else 0.0
        )
        reserve_leverage_notional_weight = reserve_invested_weight * leverage_multiple
        reserve_leverage_spy_return = (
            reserve_leverage_notional_weight * spy_gross_return
            if reserve_asset_symbol is not None and reserve_leverage_notional_weight > 0.0
            else 0.0
        )
        reserve_leverage_turnover = reserve_turnover * leverage_multiple
        reserve_leverage_cost = reserve_cost * leverage_multiple
        reserve_leverage_financing_cost = (
            reserve_invested_weight
            * max(leverage_multiple - 1.0, 0.0)
            * annual_financing_rate
            * period_year_fraction
        )
        reserve_cash_return = (reserve_cash_weight - reserve_invested_weight) * cash_period_return
        core_component = core_sector_weight * quality_return
        if quality_selected.empty:
            core_component += core_sector_weight * cash_period_return
        reserve_rule_return = core_component + reserve_spy_return - reserve_cost + reserve_cash_return
        reserve_leverage_rule_return = (
            core_component
            + reserve_leverage_spy_return
            - reserve_leverage_cost
            - reserve_leverage_financing_cost
            + reserve_cash_return
        )

        regime_label = str(signal_slice["regime_label"].mode().iloc[0]) if not signal_slice.empty else "Cash"
        selected_slice = quality_selected.head(top_n)
        period_rows.append(
            {
                "signal_date": signal_date,
                "entry_date": entry_date,
                "exit_date": exit_date,
                "regime_label": regime_label,
                "probability_selection": probability_labels,
                "quality_selection": quality_labels,
                "probability_weights": json.dumps(probability_weights, sort_keys=True),
                "quality_weights": json.dumps(quality_weights, sort_keys=True),
                "reserve_asset": reserve_asset_symbol or "Cash",
                "reserve_sector": reserve_asset_symbol or "Cash",
                "spy_drawdown_signal": spy_drawdown_signal,
                "period_year_fraction": period_year_fraction,
                "cash_period_return": cash_period_return,
                "probability_return": probability_return,
                "quality_return": quality_return,
                "spy_return": spy_return,
                "reserve_rule_return": reserve_rule_return,
                "reserve_leverage_rule_return": reserve_leverage_rule_return,
                "probability_return_x3": probability_return_x3,
                "quality_return_x3": quality_return_x3,
                "spy_return_x3": spy_return_x3,
                "probability_turnover": probability_turnover,
                "quality_turnover": quality_turnover,
                "reserve_turnover": reserve_turnover,
                "reserve_leverage_turnover": reserve_leverage_turnover,
                "reserve_deployed_fraction": reserve_target_fraction,
                "reserve_invested_weight": reserve_invested_weight,
                "reserve_leverage_notional_weight": reserve_leverage_notional_weight,
                "reserve_cash_weight": reserve_cash_weight - reserve_invested_weight,
                "reserve_leverage_financing_cost": reserve_leverage_financing_cost,
                "top_probability": float(signal_slice["ensemble_probability"].max()) if not signal_slice.empty else None,
                "top_quality_score": float(signal_slice["quality_weighted_score"].max()) if not signal_slice.empty else None,
                "selected_count": int(len(selected_slice.index)),
            }
        )

        previous_weights["probability"] = probability_weights
        previous_weights["quality"] = quality_weights
        previous_weights["reserve"] = reserve_weights
        reserve_deployed_fraction = reserve_target_fraction
        signal_pointer += rebalance_interval

    period_log_frame = pd.DataFrame(period_rows)
    if period_log_frame.empty:
        return {"available": False, "message": f"Signals existed for {scope_label.lower()}, but the rebalance schedule produced no completed rotation windows."}

    period_log_frame["equity_probability"] = (1.0 + period_log_frame["probability_return"]).cumprod()
    period_log_frame["equity_quality"] = (1.0 + period_log_frame["quality_return"]).cumprod()
    period_log_frame["equity_spy"] = (1.0 + period_log_frame["spy_return"]).cumprod()
    period_log_frame["equity_reserve_rule"] = (1.0 + period_log_frame["reserve_rule_return"]).cumprod()
    period_log_frame["equity_reserve_leverage_rule"] = (1.0 + period_log_frame["reserve_leverage_rule_return"]).cumprod()
    period_log_frame["equity_probability_x3"] = (1.0 + period_log_frame["probability_return_x3"]).cumprod()
    period_log_frame["equity_quality_x3"] = (1.0 + period_log_frame["quality_return_x3"]).cumprod()
    period_log_frame["equity_spy_x3"] = (1.0 + period_log_frame["spy_return_x3"]).cumprod()

    strategy_rows = []
    reserve_leverage_label = f"{RESERVE_STRATEGY_LABEL} x{leverage_multiple:.0f} Drawdown Sleeve @ {annual_financing_rate:.0%}"
    for label, return_column, turnover_column in (
        ("ML Probability Rotation", "probability_return", "probability_turnover"),
        ("ML Quality-Weighted Rotation", "quality_return", "quality_turnover"),
        (RESERVE_STRATEGY_LABEL, "reserve_rule_return", "reserve_turnover"),
        (reserve_leverage_label, "reserve_leverage_rule_return", "reserve_leverage_turnover"),
        ("SPY Buy And Hold", "spy_return", None),
        (f"ML Probability Rotation x{leverage_multiple:.0f} @ {annual_financing_rate:.0%}", "probability_return_x3", "probability_turnover"),
        (f"ML Quality-Weighted Rotation x{leverage_multiple:.0f} @ {annual_financing_rate:.0%}", "quality_return_x3", "quality_turnover"),
        (f"SPY Buy And Hold x{leverage_multiple:.0f} @ {annual_financing_rate:.0%}", "spy_return_x3", None),
    ):
        summary = _periodic_strategy_summary(
            period_log_frame.set_index("exit_date"),
            return_column,
            turnover_column=turnover_column,
        )
        strategy_rows.append({"strategy_label": label, **summary})
    strategy_summary_frame = pd.DataFrame(strategy_rows)

    yearly_rows: list[dict[str, Any]] = []
    regime_rows: list[dict[str, Any]] = []
    for label, return_column, turnover_column in (
        ("ML Probability Rotation", "probability_return", "probability_turnover"),
        ("ML Quality-Weighted Rotation", "quality_return", "quality_turnover"),
        (RESERVE_STRATEGY_LABEL, "reserve_rule_return", "reserve_turnover"),
        (reserve_leverage_label, "reserve_leverage_rule_return", "reserve_leverage_turnover"),
        ("SPY Buy And Hold", "spy_return", None),
        (f"ML Probability Rotation x{leverage_multiple:.0f} @ {annual_financing_rate:.0%}", "probability_return_x3", "probability_turnover"),
        (f"ML Quality-Weighted Rotation x{leverage_multiple:.0f} @ {annual_financing_rate:.0%}", "quality_return_x3", "quality_turnover"),
        (f"SPY Buy And Hold x{leverage_multiple:.0f} @ {annual_financing_rate:.0%}", "spy_return_x3", None),
    ):
        yearly = _summarize_period_groups(
            period_log_frame.assign(year=pd.to_datetime(period_log_frame["exit_date"]).dt.year),
            strategy_column=return_column,
            group_column="year",
            turnover_column=turnover_column or "probability_turnover",
        )
        if not yearly.empty:
            yearly.insert(0, "strategy_label", label)
            yearly_rows.extend(yearly.to_dict(orient="records"))

        regime = _summarize_period_groups(
            period_log_frame,
            strategy_column=return_column,
            group_column="regime_label",
            turnover_column=turnover_column or "probability_turnover",
        )
        if not regime.empty:
            regime.insert(0, "strategy_label", label)
            regime_rows.extend(regime.to_dict(orient="records"))

    current_signal_date = max(signal_dates)
    current_signal_frame = signal_frame.loc[signal_frame["date"] == current_signal_date].copy()
    current_signal_frame = current_signal_frame.sort_values("quality_weighted_score", ascending=False).reset_index(drop=True)
    current_signal_frame["recommended_probability"] = False
    current_signal_frame["recommended_quality"] = False
    probability_live, _ = _weights_from_scores(
        current_signal_frame.set_index("symbol")["ensemble_probability"],
        top_n=top_n,
    )
    quality_live, _ = _weights_from_scores(
        current_signal_frame.set_index("symbol")["quality_weighted_score"],
        top_n=top_n,
    )
    current_signal_frame["probability_weight"] = current_signal_frame["symbol"].map(probability_live).fillna(0.0)
    current_signal_frame["quality_weight"] = current_signal_frame["symbol"].map(quality_live).fillna(0.0)
    current_signal_frame["recommended_probability"] = current_signal_frame["probability_weight"] > 0.0
    current_signal_frame["recommended_quality"] = current_signal_frame["quality_weight"] > 0.0
    benchmark_start = pd.Timestamp(period_log_frame["signal_date"].min())
    benchmark_end = pd.Timestamp(period_log_frame["exit_date"].max())

    return {
        "available": True,
        "scope_label": scope_label,
        "scope_kind": scope_kind,
        "scope_note": scope_note,
        "benchmark_start": benchmark_start,
        "benchmark_end": benchmark_end,
        "period_count": int(len(period_log_frame.index)),
        "holding_period_bars": holding_period,
        "rebalance_interval_bars": rebalance_interval,
        "reserve_leverage_label": reserve_leverage_label,
        "period_log_frame": period_log_frame,
        "strategy_summary_frame": strategy_summary_frame,
        "yearly_summary_frame": pd.DataFrame(yearly_rows),
        "regime_summary_frame": pd.DataFrame(regime_rows),
        "current_signal_frame": current_signal_frame,
        "current_signal_date": pd.Timestamp(current_signal_date),
        "benchmark_symbol": "SPY",
        "method_note": (
            f"{scope_note} Signals are generated from walk-forward out-of-sample sector predictions, executed one bar after the signal date, and held for {holding_period} bars before the next rebalance. "
            "The quality-weighted variant mixes live ensemble probability with a sector quality prior estimated only from the pre-holdout validation window. "
            "The reserve sleeve keeps 40% of the portfolio in cash earning 5% annually, deploys 10% of that reserve into SPY after a 5% SPY drawdown, another 10% after a 10% drawdown, and the rest after a 20% drawdown, then rotates that deployed sleeve back to cash only after SPY gets back to its prior high. "
            f"The leveraged scenario applies {leverage_multiple:.0f}x gross exposure and charges {annual_financing_rate:.0%} annual interest on the borrowed {max(leverage_multiple - 1.0, 0.0):.0f}x capital over each realized holding period. "
            f"{reserve_leverage_label} only levers the deployed SPY reserve sleeve during drawdowns and rotates that sleeve back to cash once SPY returns to a fresh high."
        ),
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
    oos_signal_frames: list[pd.DataFrame] = []
    holdout_signal_frames: list[pd.DataFrame] = []
    validation_predictions_by_symbol: dict[str, pd.DataFrame] = {}

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
        validation_predictions_by_symbol[sector["symbol"]] = validation_predictions
        oos_frame = validation_predictions[
            [
                "prob_elastic_net",
                "prob_extra_trees",
                "prob_lightgbm",
                "ensemble_probability",
                "target",
                "forward_return",
                "regime_label",
                "quadrant_label",
                "fold_label",
            ]
        ].copy()
        oos_frame.insert(0, "sector_label", sector["label"])
        oos_frame.insert(0, "symbol", sector["symbol"])
        oos_signal_frames.append(oos_frame.reset_index(names="date"))
        if not holdout_predictions.empty:
            holdout_frame = holdout_predictions[
                [
                    "prob_elastic_net",
                    "prob_extra_trees",
                    "prob_lightgbm",
                    "ensemble_probability",
                    "target",
                    "forward_return",
                    "regime_label",
                    "quadrant_label",
                    "fold_label",
                ]
            ].copy()
            holdout_frame.insert(0, "sector_label", sector["label"])
            holdout_frame.insert(0, "symbol", sector["symbol"])
            holdout_signal_frames.append(holdout_frame.reset_index(names="date"))

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
                    predictions=validation_predictions,
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
                "ensemble_validation_sharpe": comparison_frame.loc[
                    comparison_frame["model_key"] == "average_ensemble", "validation_sharpe"
                ].iloc[0],
                "ensemble_validation_cagr": comparison_frame.loc[
                    comparison_frame["model_key"] == "average_ensemble", "validation_cagr"
                ].iloc[0],
                "ensemble_validation_max_drawdown": comparison_frame.loc[
                    comparison_frame["model_key"] == "average_ensemble", "validation_max_drawdown"
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

    holdout_leader_candidates = sector_summary_frame.loc[
        sector_summary_frame["ensemble_holdout_trade_count"].fillna(0) >= 3
    ]
    if holdout_leader_candidates.empty:
        holdout_leader_candidates = sector_summary_frame
    holdout_leader = (
        holdout_leader_candidates.sort_values(
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
    validation_quality_frame = _validation_quality_frame(sector_summary_frame)
    oos_signal_frame = (
        pd.concat(oos_signal_frames, ignore_index=True)
        if oos_signal_frames
        else pd.DataFrame()
    )
    holdout_signal_frame = (
        pd.concat(holdout_signal_frames, ignore_index=True)
        if holdout_signal_frames
        else pd.DataFrame()
    )
    quality_lookup_frame = _build_point_in_time_quality(
        validation_predictions_by_symbol=validation_predictions_by_symbol,
        signal_frame=oos_signal_frame,
        config=config,
    )
    holdout_rotation_view = _build_rotation_backtest_view(
        signal_frame=holdout_signal_frame,
        validation_quality_frame=validation_quality_frame,
        project_root=root,
        config=config,
        scope_label="Untouched 2025+ holdout",
        scope_kind="holdout",
        scope_note="This benchmark uses only the final untouched holdout dates after the validation years.",
        quality_lookup_frame=quality_lookup_frame,
    )
    historical_start = pd.Timestamp(str(config["historical_benchmark_start"]))
    historical_signal_frame = oos_signal_frame.copy()
    if not historical_signal_frame.empty:
        historical_signal_frame["date"] = pd.to_datetime(historical_signal_frame["date"])
        historical_signal_frame = historical_signal_frame.loc[
            historical_signal_frame["date"] >= historical_start
        ].copy()
    historical_rotation_view = _build_rotation_backtest_view(
        signal_frame=historical_signal_frame,
        validation_quality_frame=validation_quality_frame,
        project_root=root,
        config=config,
        scope_label="2006-2024 walk-forward history",
        scope_kind="walkforward_history",
        scope_note="This benchmark uses pre-holdout walk-forward out-of-sample windows from 2006 onward, including the 2008 financial crisis, the 2020 shock, and the 2022 rate-reset drawdown.",
        quality_lookup_frame=quality_lookup_frame,
    )
    rebalance_rows: list[dict[str, Any]] = []
    for cadence_bars in tuple(int(value) for value in config["rebalance_interval_scenarios"]):
        if cadence_bars == int(config["label_horizon"]):
            cadence_view = historical_rotation_view
        else:
            cadence_view = _build_rotation_backtest_view(
                signal_frame=historical_signal_frame,
                validation_quality_frame=validation_quality_frame,
                project_root=root,
                config=config,
                scope_label=f"2006-2026 walk-forward history ({cadence_bars}-bar cadence)",
                scope_kind="rebalance_sensitivity",
                scope_note=(
                    f"This benchmark reuses the same daily ML signal but only rebalances every {cadence_bars} bars, so it is an execution-cadence overlay rather than a separately retrained {cadence_bars}-bar forecast model."
                ),
                holding_period_bars=cadence_bars,
                rebalance_interval_bars=cadence_bars,
                quality_lookup_frame=quality_lookup_frame,
            )
        if not isinstance(cadence_view, dict) or not cadence_view.get("available"):
            continue
        cadence_summary = cadence_view["strategy_summary_frame"].copy()
        cadence_summary.insert(0, "cadence_label", f"{cadence_bars}-bar")
        cadence_summary.insert(0, "cadence_bars", cadence_bars)
        rebalance_rows.extend(cadence_summary.to_dict(orient="records"))
    rebalance_sensitivity_frame = pd.DataFrame(rebalance_rows)

    return {
        "available": True,
        "config": config,
        "boosting_backend": boosting_backend,
        "data_note": (
            "Features are lagged by one bar and each validation window uses a five-bar purge plus a five-bar embargo. "
            "The sector ML study now trains from 2000 onward so the walk-forward history can include 2008, 2020, and 2022 while preserving a separate untouched 2025+ holdout. "
            "Per-sector validation quality scores used in the rotation backtest are recomputed point-in-time so a signal in year Y is only weighted by validation evidence from folds strictly before Y. "
            "Macro regime attribution comes from the local macro store and is useful for regime slicing, but it is not a point-in-time macro vintage database."
        ),
        "sector_summary_frame": sector_summary_frame,
        "model_comparison_frame": model_comparison_frame,
        "yearly_performance_frame": yearly_performance_frame,
        "regime_performance_frame": regime_performance_frame,
        "cost_sensitivity_frame": cost_sensitivity_frame,
        "validation_quality_frame": validation_quality_frame,
        "quality_lookup_frame": quality_lookup_frame,
        "winner_counts_frame": winner_counts,
        "failures_frame": failures_frame,
        "holdout_leader": holdout_leader,
        "robust_cost_sector_count": robust_cost_sector_count,
        "holdout_signal_frame": holdout_signal_frame,
        "oos_signal_frame": oos_signal_frame,
        "holdout_rotation_view": holdout_rotation_view,
        "historical_rotation_view": historical_rotation_view,
        "rebalance_sensitivity_frame": rebalance_sensitivity_frame,
    }
