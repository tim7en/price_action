from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from price_action.data import load_asset_daily  # noqa: E402
from price_action.sector_ml import (  # noqa: E402
    DEFAULT_SECTOR_ML_CONFIG,
    _build_point_in_time_quality,
    _join_daily_regimes,
    _regime_daily_map,
    _turnover_cost,
    _weights_from_scores,
)
from price_action.train import run_walk_forward_experiment  # noqa: E402


REPORT_DIR = PROJECT_ROOT / "outputs" / "sector_rotation_report"
GOLD_SYMBOL = "GLD"
GOLD_LABEL = "Gold"
STOP_LOSS = 0.10


def _load_close_panel(symbols: list[str]) -> pd.DataFrame:
    frames: list[pd.Series] = []
    for symbol in symbols:
        close = pd.to_numeric(load_asset_daily(symbol, project_root=PROJECT_ROOT)["close"], errors="coerce")
        frames.append(close.rename(symbol))
    panel = pd.concat(frames, axis=1).sort_index().ffill()
    panel.index.name = "date"
    return panel


def _gold_signal_frame(config: dict[str, Any]) -> pd.DataFrame:
    output_path = REPORT_DIR / "gold_ml_oos_signal_frame.csv"
    summary_path = REPORT_DIR / "gold_ml_summary.json"

    predictions, summary = run_walk_forward_experiment(
        symbol=GOLD_SYMBOL,
        project_root=PROJECT_ROOT,
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
    regime_map = _regime_daily_map(project_root=PROJECT_ROOT)
    predictions = _join_daily_regimes(predictions=predictions, regime_daily_map=regime_map)
    frame = predictions[
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
    frame.insert(0, "sector_label", GOLD_LABEL)
    frame.insert(0, "symbol", GOLD_SYMBOL)
    frame = frame.reset_index(names="date")
    frame.to_csv(output_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return frame


def _combined_signal_frame(config: dict[str, Any], include_gold: bool, scope: str) -> pd.DataFrame:
    sector = pd.read_csv(REPORT_DIR / "sector_ml_oos_signal_frame.csv", parse_dates=["date"])
    frames = [sector]
    if include_gold:
        frames.append(_gold_signal_frame(config))
    combined = pd.concat(frames, ignore_index=True)

    validation_predictions_by_symbol = {
        symbol: group.set_index("date").sort_index()
        for symbol, group in combined.loc[combined["fold_label"].astype(str) != "holdout"].groupby("symbol")
    }
    quality_lookup = _build_point_in_time_quality(
        validation_predictions_by_symbol=validation_predictions_by_symbol,
        signal_frame=combined,
        config=config,
    )

    if scope == "holdout":
        signal_frame = combined.loc[combined["fold_label"].astype(str) == "holdout"].copy()
    elif scope == "history":
        historical_start = pd.Timestamp(str(config["historical_benchmark_start"]))
        signal_frame = combined.loc[combined["date"] >= historical_start].copy()
    else:
        raise ValueError(f"Unknown scope: {scope}")

    signal_frame["signal_year"] = signal_frame["date"].dt.year.astype(int)
    if not quality_lookup.empty:
        signal_frame = signal_frame.merge(
            quality_lookup[["signal_year", "symbol", "validation_quality_score"]],
            on=["signal_year", "symbol"],
            how="left",
        )
    else:
        signal_frame["validation_quality_score"] = np.nan
    signal_frame["validation_quality_score"] = signal_frame["validation_quality_score"].fillna(0.5)
    quality_weight = float(config["quality_weight"])
    signal_frame["quality_weighted_score"] = (
        (1.0 - quality_weight) * signal_frame["ensemble_probability"].astype(float)
        + quality_weight * signal_frame["validation_quality_score"].astype(float)
    )
    return signal_frame.drop(columns=["signal_year"])


def _summarize_return_stream(
    frame: pd.DataFrame,
    return_column: str,
    turnover_column: str | None,
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

    returns = pd.to_numeric(frame[return_column], errors="coerce").fillna(0.0)
    equity_curve = (1.0 + returns).cumprod()
    start_date = pd.Timestamp(frame["entry_date"].min())
    end_date = pd.Timestamp(frame["exit_date"].max())
    years = max((end_date - start_date).days / 365.25, len(frame.index) / 252.0, 1.0 / 252.0)
    periods_per_year = max(len(frame.index) / years, 1.0)
    final_equity = float(equity_curve.iloc[-1])
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
    trade_count = int((turnover_series > 1e-12).sum()) if turnover_column is not None else 1
    entry_count = 1 if turnover_column is None and len(frame.index) > 0 else 0
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


def _regime_change_signal_dates(signal_frame: pd.DataFrame, signal_dates: list[pd.Timestamp]) -> list[pd.Timestamp]:
    rows: list[pd.Series] = []
    for date in signal_dates:
        date_slice = signal_frame.loc[signal_frame["date"] == date]
        if date_slice.empty:
            continue
        rows.append(
            pd.Series(
                {
                    "date": date,
                    "regime_label": str(date_slice["regime_label"].mode().iloc[0]),
                }
            )
        )
    if not rows:
        return []
    regimes = pd.DataFrame(rows)
    return regimes.loc[regimes["regime_label"].ne(regimes["regime_label"].shift(1)), "date"].tolist()


def _return_with_stop(
    price_panel: pd.DataFrame,
    weights: dict[str, float],
    entry_date: pd.Timestamp,
    exit_date: pd.Timestamp,
    cost_rate: float,
) -> tuple[float, dict[str, float], int, str]:
    gross_return = 0.0
    active_weights: dict[str, float] = {}
    stopped_symbols: list[str] = []
    for symbol, weight in weights.items():
        entry_price = price_panel.at[entry_date, symbol]
        if pd.isna(entry_price) or float(entry_price) <= 0.0:
            continue
        series = pd.to_numeric(price_panel.loc[entry_date:exit_date, symbol], errors="coerce").dropna()
        if series.empty:
            continue
        stop_price = float(entry_price) * (1.0 - STOP_LOSS)
        post_entry = series.iloc[1:]
        breach = post_entry.loc[post_entry <= stop_price]
        if breach.empty:
            active_weights[symbol] = float(weight)
            gross_return += float(weight) * (float(series.iloc[-1]) / float(entry_price) - 1.0)
        else:
            stopped_symbols.append(f"{symbol}@{breach.index[0].date()}")
            gross_return += float(weight) * -STOP_LOSS
    stop_exit_cost = (sum(weights.values()) - sum(active_weights.values())) * cost_rate
    return gross_return - stop_exit_cost, active_weights, len(stopped_symbols), "; ".join(stopped_symbols)


def _run_rotation(
    scope: str,
    mode: str,
    include_gold: bool,
    signal_frame: pd.DataFrame,
    price_panel: pd.DataFrame,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    symbols = sorted(signal_frame["symbol"].unique().tolist())
    trading_index = price_panel.index
    signal_dates = sorted(date for date in signal_frame["date"].unique() if date in trading_index)
    if not signal_dates:
        return pd.DataFrame(), pd.DataFrame()
    last_signal_entry_pos = trading_index.searchsorted(signal_dates[-1], side="right")
    last_scope_exit_pos = min(last_signal_entry_pos + int(config["label_horizon"]), len(trading_index) - 1)
    if mode == "regime_change":
        rebalance_dates = _regime_change_signal_dates(signal_frame, signal_dates)
    elif mode == "ml_5bar":
        rebalance_dates = signal_dates[:: int(config["label_horizon"])]
    else:
        raise ValueError(f"Unknown mode: {mode}")

    previous_weights: dict[str, float] = {}
    rows: list[dict[str, Any]] = []
    cost_rate = float(config["cost_bps"]) / 10_000.0
    for index, signal_date in enumerate(rebalance_dates):
        entry_pos = trading_index.searchsorted(signal_date, side="right")
        if entry_pos >= len(trading_index):
            break
        entry_date = trading_index[entry_pos]
        if mode == "regime_change" and index + 1 < len(rebalance_dates):
            next_entry_pos = trading_index.searchsorted(rebalance_dates[index + 1], side="right")
            exit_pos = min(max(next_entry_pos, entry_pos + 1), len(trading_index) - 1)
        elif mode == "regime_change":
            exit_pos = max(last_scope_exit_pos, entry_pos + 1)
        else:
            exit_pos = min(entry_pos + int(config["label_horizon"]), len(trading_index) - 1)
        exit_date = trading_index[exit_pos]
        if exit_date <= entry_date:
            continue

        signal_slice = signal_frame.loc[signal_frame["date"] == signal_date].copy()
        signal_slice = signal_slice.loc[
            signal_slice["ensemble_probability"].astype(float) >= float(config["signal_threshold"])
        ].copy()
        weights, selected = _weights_from_scores(
            signal_slice.set_index("symbol")["quality_weighted_score"],
            top_n=int(config["top_n"]),
        )
        weights = {
            symbol: weight
            for symbol, weight in weights.items()
            if symbol in price_panel.columns and pd.notna(price_panel.at[entry_date, symbol])
        }
        turnover, turnover_cost = _turnover_cost(previous_weights, weights, cost_rate)
        strategy_gross, active_weights, stop_count, stopped_symbols = _return_with_stop(
            price_panel=price_panel,
            weights=weights,
            entry_date=entry_date,
            exit_date=exit_date,
            cost_rate=cost_rate,
        )
        strategy_return = strategy_gross - turnover_cost
        spy_return = float(price_panel.at[exit_date, "SPY"] / price_panel.at[entry_date, "SPY"] - 1.0)

        rows.append(
            {
                "scope": scope,
                "mode": mode,
                "include_gold": include_gold,
                "signal_date": signal_date,
                "entry_date": entry_date,
                "exit_date": exit_date,
                "selected": selected,
                "weights": json.dumps(weights, sort_keys=True),
                "strategy_return": strategy_return,
                "spy_return": spy_return,
                "turnover": turnover,
                "turnover_cost": turnover_cost,
                "stop_count": stop_count,
                "stopped_symbols": stopped_symbols,
                "gold_weight": float(weights.get(GOLD_SYMBOL, 0.0)),
                "selected_count": len(weights),
            }
        )
        previous_weights = active_weights

    periods = pd.DataFrame(rows)
    if periods.empty:
        return periods, pd.DataFrame()
    periods["equity_strategy"] = (1.0 + periods["strategy_return"]).cumprod()
    periods["equity_spy"] = (1.0 + periods["spy_return"]).cumprod()

    label = "ETF ML Rotation + Gold Stop 10%" if include_gold else "Sector ETF ML Rotation Stop 10%"
    summary_rows = [
        {
            "scope": scope,
            "mode": mode,
            "include_gold": include_gold,
            "strategy_label": label,
            **_summarize_return_stream(periods, "strategy_return", turnover_column="turnover"),
        },
        {
            "scope": scope,
            "mode": mode,
            "include_gold": include_gold,
            "strategy_label": "SPY Buy And Hold",
            **_summarize_return_stream(periods, "spy_return", turnover_column=None),
        },
    ]
    return periods, pd.DataFrame(summary_rows)


def main() -> None:
    config = dict(DEFAULT_SECTOR_ML_CONFIG)
    all_symbols = sorted(set(pd.read_csv(REPORT_DIR / "sector_ml_oos_signal_frame.csv")["symbol"]) | {GOLD_SYMBOL, "SPY"})
    price_panel = _load_close_panel(all_symbols)

    periods: list[pd.DataFrame] = []
    summaries: list[pd.DataFrame] = []
    for include_gold in (False, True):
        for scope in ("history", "holdout"):
            signal_frame = _combined_signal_frame(config=config, include_gold=include_gold, scope=scope)
            for mode in ("ml_5bar", "regime_change"):
                period_frame, summary_frame = _run_rotation(
                    scope=scope,
                    mode=mode,
                    include_gold=include_gold,
                    signal_frame=signal_frame,
                    price_panel=price_panel,
                    config=config,
                )
                periods.append(period_frame)
                summaries.append(summary_frame)

    period_frame = pd.concat([frame for frame in periods if not frame.empty], ignore_index=True)
    summary_frame = pd.concat([frame for frame in summaries if not frame.empty], ignore_index=True)
    period_output = REPORT_DIR / "etf_gold_rotation_period_log.csv"
    summary_output = REPORT_DIR / "etf_gold_rotation_strategy_summary.csv"
    period_frame.to_csv(period_output, index=False)
    summary_frame.to_csv(summary_output, index=False)

    print(json.dumps({"period_log": str(period_output), "summary": str(summary_output)}, indent=2))
    print(
        summary_frame[
            [
                "scope",
                "mode",
                "include_gold",
                "strategy_label",
                "total_return",
                "cagr",
                "sharpe",
                "max_drawdown",
                "trade_count",
                "period_count",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
