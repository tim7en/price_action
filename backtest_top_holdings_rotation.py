from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
MPLCONFIGDIR = Path(tempfile.gettempdir()) / "price_action_matplotlib"
MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIGDIR))

from price_action.data import load_asset_daily  # noqa: E402
from price_action.sector_ml import (  # noqa: E402
    DEFAULT_SECTOR_ML_CONFIG,
    _build_point_in_time_quality,
    _turnover_cost,
    _weights_from_scores,
)


REPORT_DIR = PROJECT_ROOT / "outputs" / "sector_rotation_report"
DEFAULT_HOLDINGS_PATH = PROJECT_ROOT / "data" / "sector_top_holdings.csv"
STOP_LOSS = 0.10
HOLDINGS_REQUIRED_COLUMNS = {
    "as_of_date",
    "known_from_date",
    "sector_symbol",
    "holding_symbol",
    "weight",
}
BENCHMARK_STRATEGY_LABEL = "SPY Buy And Hold"
TOP5_STRATEGY_LABEL = "Top 5 Holdings ML Rotation Stop 10%"
SECTOR_ETF_STRATEGY_LABEL = "Sector ETF ML Quality Rotation"


def _load_close_panel(symbols: list[str], required_symbols: set[str] | None = None) -> pd.DataFrame:
    required = required_symbols or set()
    frames: list[pd.Series] = []
    missing_symbols: list[str] = []
    for symbol in symbols:
        try:
            close = pd.to_numeric(load_asset_daily(symbol, project_root=PROJECT_ROOT)["close"], errors="coerce")
        except FileNotFoundError:
            if symbol in required:
                raise
            missing_symbols.append(symbol)
            continue
        frames.append(close.rename(symbol))
    if missing_symbols:
        print(
            "Skipping holdings with no cached price history: "
            + ", ".join(sorted(missing_symbols)),
            file=sys.stderr,
        )
    if not frames:
        raise ValueError("No price histories were loaded.")
    panel = pd.concat(frames, axis=1).sort_index().ffill()
    panel.index.name = "date"
    return panel


def _load_point_in_time_holdings(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing point-in-time holdings file: {path}\n"
            "Create it from issuer archives, SEC N-PORT/N-Q filings, or a point-in-time vendor feed. "
            "Required columns: as_of_date, known_from_date, sector_symbol, holding_symbol, weight."
        )

    frame = pd.read_csv(path)
    missing = HOLDINGS_REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(sorted(missing))}")
    if frame.empty:
        raise ValueError(f"{path} contains no holdings rows.")

    frame = frame.copy()
    frame["as_of_date"] = pd.to_datetime(frame["as_of_date"], errors="coerce")
    frame["known_from_date"] = pd.to_datetime(frame["known_from_date"], errors="coerce")
    frame["sector_symbol"] = frame["sector_symbol"].astype(str).str.upper().str.strip()
    frame["holding_symbol"] = frame["holding_symbol"].astype(str).str.upper().str.strip()
    frame["weight"] = pd.to_numeric(frame["weight"], errors="coerce")
    frame = frame.dropna(subset=["as_of_date", "known_from_date", "sector_symbol", "holding_symbol", "weight"])
    if frame.empty:
        raise ValueError(f"{path} contains no valid holdings rows after parsing.")

    # Accept either 0.1234 or 12.34 style weights.
    if frame["weight"].max() > 1.0:
        frame["weight"] = frame["weight"] / 100.0

    if (frame["known_from_date"] < frame["as_of_date"]).any():
        raise ValueError(
            "Holdings rows cannot be known before their as_of_date. "
            "Set known_from_date to the issuer publication date, SEC acceptance date, or a conservative later date."
        )

    return frame.sort_values(["sector_symbol", "known_from_date", "as_of_date", "weight"])


def _list_csv_part_paths(path: Path) -> list[Path]:
    return sorted(path.parent.glob(f"{path.stem}.part*{path.suffix}"))


def _read_csv_output(path: Path, **kwargs: Any) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path, **kwargs)

    part_paths = _list_csv_part_paths(path)
    if not part_paths:
        raise FileNotFoundError(f"Missing CSV export: {path}")

    frames = [pd.read_csv(part_path, **kwargs) for part_path in part_paths]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _rank_strategy_frame(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
    if frame.empty:
        ranked = frame.copy()
        ranked[f"{prefix}_rank"] = pd.Series(dtype="Int64")
        return ranked

    sharpe_column = f"{prefix}_sharpe"
    cagr_column = f"{prefix}_cagr"
    drawdown_column = f"{prefix}_max_drawdown"
    ranked = frame.copy()
    ranked["_rank_sharpe"] = pd.to_numeric(ranked[sharpe_column], errors="coerce").fillna(float("-inf"))
    ranked["_rank_cagr"] = pd.to_numeric(ranked[cagr_column], errors="coerce").fillna(float("-inf"))
    ranked["_rank_drawdown"] = pd.to_numeric(ranked[drawdown_column], errors="coerce").fillna(float("-inf"))
    ranked = ranked.sort_values(
        ["_rank_sharpe", "_rank_cagr", "_rank_drawdown"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    ranked[f"{prefix}_rank"] = pd.Series(np.arange(1, len(ranked.index) + 1), dtype="int64")
    return ranked.drop(columns=["_rank_sharpe", "_rank_cagr", "_rank_drawdown"])


def _json_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        if pd.isna(value):
            return None
        return float(value)
    return value


def _build_holdout_leaderboard(summary_frame: pd.DataFrame) -> pd.DataFrame:
    if summary_frame.empty:
        return pd.DataFrame()

    metric_columns = [
        "total_return",
        "cagr",
        "sharpe",
        "sortino",
        "max_drawdown",
        "calmar",
        "profit_factor",
        "hit_rate",
        "average_trade_return",
        "average_win",
        "average_loss",
        "trade_count",
        "period_count",
        "entry_count",
        "turnover_per_year",
    ]
    selection_keys = ["mode", "strategy_label"]
    candidate_frame = summary_frame.loc[summary_frame["strategy_label"].ne(BENCHMARK_STRATEGY_LABEL)].copy()
    if candidate_frame.empty:
        return pd.DataFrame()

    history_frame = candidate_frame.loc[
        candidate_frame["scope"].eq("history"),
        selection_keys + metric_columns,
    ].rename(columns={column: f"history_{column}" for column in metric_columns})
    if history_frame.empty:
        return pd.DataFrame()

    holdout_frame = candidate_frame.loc[
        candidate_frame["scope"].eq("holdout"),
        selection_keys + metric_columns,
    ].rename(columns={column: f"holdout_{column}" for column in metric_columns})

    leaderboard = _rank_strategy_frame(history_frame, prefix="history")
    if not holdout_frame.empty:
        leaderboard = leaderboard.merge(holdout_frame, on=selection_keys, how="left")
        holdout_rank_frame = _rank_strategy_frame(
            holdout_frame[[*selection_keys, "holdout_sharpe", "holdout_cagr", "holdout_max_drawdown"]],
            prefix="holdout",
        )[[*selection_keys, "holdout_rank"]]
        leaderboard = leaderboard.merge(holdout_rank_frame, on=selection_keys, how="left")

    benchmark_holdout = summary_frame.loc[
        summary_frame["scope"].eq("holdout") & summary_frame["strategy_label"].eq(BENCHMARK_STRATEGY_LABEL),
        ["mode", "total_return", "cagr", "sharpe", "max_drawdown"],
    ].rename(
        columns={
            "total_return": "benchmark_holdout_total_return",
            "cagr": "benchmark_holdout_cagr",
            "sharpe": "benchmark_holdout_sharpe",
            "max_drawdown": "benchmark_holdout_max_drawdown",
        }
    )
    if not benchmark_holdout.empty:
        leaderboard = leaderboard.merge(benchmark_holdout, on="mode", how="left")

    leaderboard["selection_scope"] = "history"
    leaderboard["evaluation_scope"] = "holdout"
    leaderboard["selected_on_history"] = leaderboard["history_rank"].eq(1)
    leaderboard["holdout_total_return_vs_spy"] = (
        pd.to_numeric(leaderboard.get("holdout_total_return"), errors="coerce")
        - pd.to_numeric(leaderboard.get("benchmark_holdout_total_return"), errors="coerce")
    )
    leaderboard["holdout_cagr_vs_spy"] = (
        pd.to_numeric(leaderboard.get("holdout_cagr"), errors="coerce")
        - pd.to_numeric(leaderboard.get("benchmark_holdout_cagr"), errors="coerce")
    )
    leaderboard["holdout_sharpe_vs_spy"] = (
        pd.to_numeric(leaderboard.get("holdout_sharpe"), errors="coerce")
        - pd.to_numeric(leaderboard.get("benchmark_holdout_sharpe"), errors="coerce")
    )
    return leaderboard.sort_values("history_rank").reset_index(drop=True)


def _build_best_strategy_assessment(leaderboard: pd.DataFrame) -> dict[str, Any]:
    if leaderboard.empty:
        return {}

    selected = leaderboard.sort_values("history_rank").iloc[0]
    assessment: dict[str, Any] = {
        "selection_rule": "Rank candidate PIT strategies by history Sharpe, then CAGR, then max_drawdown, and evaluate the unchanged winner on holdout.",
        "candidate_count": int(len(leaderboard.index)),
        "selected_mode": str(selected["mode"]),
        "selected_strategy_label": str(selected["strategy_label"]),
        "selected_history_rank": _json_scalar(selected.get("history_rank")),
        "selected_holdout_rank": _json_scalar(selected.get("holdout_rank")),
        "history_total_return": _json_scalar(selected.get("history_total_return")),
        "history_cagr": _json_scalar(selected.get("history_cagr")),
        "history_sharpe": _json_scalar(selected.get("history_sharpe")),
        "history_max_drawdown": _json_scalar(selected.get("history_max_drawdown")),
        "holdout_total_return": _json_scalar(selected.get("holdout_total_return")),
        "holdout_cagr": _json_scalar(selected.get("holdout_cagr")),
        "holdout_sharpe": _json_scalar(selected.get("holdout_sharpe")),
        "holdout_max_drawdown": _json_scalar(selected.get("holdout_max_drawdown")),
        "holdout_total_return_vs_spy": _json_scalar(selected.get("holdout_total_return_vs_spy")),
        "holdout_cagr_vs_spy": _json_scalar(selected.get("holdout_cagr_vs_spy")),
        "holdout_sharpe_vs_spy": _json_scalar(selected.get("holdout_sharpe_vs_spy")),
        "benchmark_holdout_total_return": _json_scalar(selected.get("benchmark_holdout_total_return")),
        "benchmark_holdout_cagr": _json_scalar(selected.get("benchmark_holdout_cagr")),
        "benchmark_holdout_sharpe": _json_scalar(selected.get("benchmark_holdout_sharpe")),
        "benchmark_holdout_max_drawdown": _json_scalar(selected.get("benchmark_holdout_max_drawdown")),
    }

    holdout_ranked = leaderboard.dropna(subset=["holdout_rank"]).sort_values("holdout_rank")
    if not holdout_ranked.empty:
        holdout_winner = holdout_ranked.iloc[0]
        assessment.update(
            {
                "holdout_oracle_mode": str(holdout_winner["mode"]),
                "holdout_oracle_strategy_label": str(holdout_winner["strategy_label"]),
                "holdout_oracle_rank": _json_scalar(holdout_winner.get("holdout_rank")),
                "holdout_oracle_total_return": _json_scalar(holdout_winner.get("holdout_total_return")),
                "holdout_oracle_cagr": _json_scalar(holdout_winner.get("holdout_cagr")),
                "holdout_oracle_sharpe": _json_scalar(holdout_winner.get("holdout_sharpe")),
                "holdout_oracle_max_drawdown": _json_scalar(holdout_winner.get("holdout_max_drawdown")),
            }
        )
    return assessment


def _latest_known_sector_holdings(
    holdings: pd.DataFrame,
    sector_symbol: str,
    signal_date: pd.Timestamp,
    top_n: int,
) -> pd.DataFrame:
    eligible = holdings.loc[
        (holdings["sector_symbol"] == sector_symbol)
        & (holdings["known_from_date"] <= signal_date)
    ].copy()
    if eligible.empty:
        return eligible

    latest_known = eligible["known_from_date"].max()
    latest = eligible.loc[eligible["known_from_date"] == latest_known].copy()
    latest_as_of = latest["as_of_date"].max()
    latest = latest.loc[latest["as_of_date"] == latest_as_of].copy()
    return latest.sort_values("weight", ascending=False).head(top_n)


def _prepare_signal_frame(scope: str, config: dict[str, Any]) -> pd.DataFrame:
    oos = _read_csv_output(REPORT_DIR / "sector_ml_oos_signal_frame.csv", parse_dates=["date"])
    validation_predictions_by_symbol = {
        symbol: group.set_index("date").sort_index()
        for symbol, group in oos.loc[oos["fold_label"].astype(str) != "holdout"].groupby("symbol")
    }
    quality_lookup = _build_point_in_time_quality(
        validation_predictions_by_symbol=validation_predictions_by_symbol,
        signal_frame=oos,
        config=config,
    )

    if scope == "holdout":
        signal_frame = _read_csv_output(REPORT_DIR / "sector_ml_holdout_signal_frame.csv", parse_dates=["date"])
    elif scope == "history":
        historical_start = pd.Timestamp(str(config["historical_benchmark_start"]))
        signal_frame = oos.loc[oos["date"] >= historical_start].copy()
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


def _sector_weights_for_signal(signal_frame: pd.DataFrame, signal_date: pd.Timestamp, config: dict[str, Any]) -> dict[str, float]:
    signal_slice = signal_frame.loc[signal_frame["date"] == signal_date].copy()
    if signal_slice.empty:
        return {}
    signal_slice = signal_slice.loc[
        signal_slice["ensemble_probability"].astype(float) >= float(config["signal_threshold"])
    ].copy()
    if signal_slice.empty:
        return {}
    weights, _ = _weights_from_scores(
        signal_slice.set_index("symbol")["quality_weighted_score"],
        top_n=int(config["top_n"]),
    )
    return weights


def _constituent_weights(
    sector_weights: dict[str, float],
    holdings: pd.DataFrame,
    signal_date: pd.Timestamp,
    entry_date: pd.Timestamp,
    price_panel: pd.DataFrame,
    top_n_holdings: int = 5,
) -> tuple[dict[str, float], dict[str, str], dict[str, str]]:
    weights: dict[str, float] = {}
    sectors_used: dict[str, str] = {}
    missing_top_holdings: dict[str, str] = {}
    for sector_symbol, sector_weight in sector_weights.items():
        sector_holdings = _latest_known_sector_holdings(
            holdings=holdings,
            sector_symbol=sector_symbol,
            signal_date=signal_date,
            top_n=top_n_holdings,
        )
        if sector_holdings.empty:
            sectors_used[sector_symbol] = "Missing point-in-time holdings"
            continue
        available: list[tuple[str, float]] = []
        missing_symbols: list[str] = []
        for row in sector_holdings.itertuples(index=False):
            symbol = str(row.holding_symbol)
            holding_weight = float(row.weight)
            if symbol in price_panel.columns and pd.notna(price_panel.at[entry_date, symbol]):
                available.append((symbol, holding_weight))
            else:
                missing_symbols.append(symbol)
        if missing_symbols:
            missing_top_holdings[sector_symbol] = ", ".join(missing_symbols)
        total_holding_weight = sum(holding_weight for _, holding_weight in available)
        if total_holding_weight <= 0.0:
            sectors_used[sector_symbol] = "Cash"
            continue
        sectors_used[sector_symbol] = ", ".join(symbol for symbol, _ in available)
        for symbol, holding_weight in available:
            weights[symbol] = weights.get(symbol, 0.0) + float(sector_weight) * float(holding_weight / total_holding_weight)
    return weights, sectors_used, missing_top_holdings


def _period_return_with_stops(
    price_panel: pd.DataFrame,
    weights: dict[str, float],
    entry_date: pd.Timestamp,
    exit_date: pd.Timestamp,
    cost_rate: float,
) -> tuple[float, dict[str, float], int, str]:
    gross_return = 0.0
    stopped_weights: dict[str, float] = {}
    stopped_symbols: list[str] = []

    for symbol, weight in weights.items():
        entry_price = float(price_panel.at[entry_date, symbol])
        if not np.isfinite(entry_price) or entry_price <= 0.0:
            continue
        series = pd.to_numeric(price_panel.loc[entry_date:exit_date, symbol], errors="coerce").dropna()
        if series.empty:
            continue

        stop_price = entry_price * (1.0 - STOP_LOSS)
        post_entry = series.iloc[1:]
        breach = post_entry.loc[post_entry <= stop_price]
        if not breach.empty:
            position_return = -STOP_LOSS
            stopped_weights[symbol] = weight
            stopped_symbols.append(f"{symbol}@{breach.index[0].date()}")
        else:
            exit_price = float(series.iloc[-1])
            position_return = exit_price / entry_price - 1.0
        gross_return += float(weight) * float(position_return)

    stop_exit_cost = sum(stopped_weights.values()) * cost_rate
    active_weights = {symbol: weight for symbol, weight in weights.items() if symbol not in stopped_weights}
    net_return = gross_return - stop_exit_cost
    return net_return, active_weights, len(stopped_weights), "; ".join(stopped_symbols)


def _weighted_return(
    price_panel: pd.DataFrame,
    weights: dict[str, float],
    entry_date: pd.Timestamp,
    exit_date: pd.Timestamp,
) -> tuple[float, dict[str, float]]:
    gross_return = 0.0
    active_weights: dict[str, float] = {}
    for symbol, weight in weights.items():
        if symbol not in price_panel.columns:
            continue
        entry_price = price_panel.at[entry_date, symbol]
        exit_price = price_panel.at[exit_date, symbol]
        if pd.isna(entry_price) or pd.isna(exit_price) or float(entry_price) <= 0.0:
            continue
        active_weights[symbol] = float(weight)
        gross_return += float(weight) * (float(exit_price) / float(entry_price) - 1.0)
    return gross_return, active_weights


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


def _build_regime_change_periods(period_log: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if period_log.empty:
        return period_log.copy()

    starts = period_log.loc[
        period_log["regime_label"].ne(period_log["regime_label"].shift(1))
    ].copy()
    start_indices = starts.index.tolist()
    for position, row_index in enumerate(start_indices):
        source_row = period_log.loc[row_index].copy()
        if position + 1 < len(start_indices):
            next_row = period_log.loc[start_indices[position + 1]]
            source_row["exit_date"] = next_row["entry_date"]
        else:
            source_row["exit_date"] = period_log.iloc[-1]["exit_date"]
        if pd.Timestamp(source_row["exit_date"]) > pd.Timestamp(source_row["entry_date"]):
            rows.append(source_row.to_dict())
    return pd.DataFrame(rows)


def _run_scope(
    scope: str,
    mode: str,
    holdings: pd.DataFrame,
    price_panel: pd.DataFrame,
    config: dict[str, Any],
    coverage_start: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    period_path = REPORT_DIR / (
        "sector_ml_holdout_period_log.csv" if scope == "holdout" else "sector_ml_history_period_log.csv"
    )
    period_log = pd.read_csv(period_path, parse_dates=["signal_date", "entry_date", "exit_date"])
    if mode == "regime_change":
        period_log = _build_regime_change_periods(period_log)
    elif mode != "ml_5bar":
        raise ValueError(f"Unknown mode: {mode}")

    signal_frame = _prepare_signal_frame(scope=scope, config=config)
    cost_rate = float(config["cost_bps"]) / 10_000.0

    previous_weights: dict[str, float] = {}
    previous_sector_weights: dict[str, float] = {}
    rows: list[dict[str, Any]] = []
    for source_row in period_log.itertuples(index=False):
        signal_date = pd.Timestamp(source_row.signal_date)
        entry_date = pd.Timestamp(source_row.entry_date)
        exit_date = pd.Timestamp(source_row.exit_date)
        if signal_date < coverage_start:
            continue
        if entry_date not in price_panel.index or exit_date not in price_panel.index or exit_date <= entry_date:
            continue

        sector_weights = _sector_weights_for_signal(signal_frame, signal_date, config=config)
        target_weights, sectors_used, missing_top_holdings = _constituent_weights(
            sector_weights=sector_weights,
            holdings=holdings,
            signal_date=signal_date,
            entry_date=entry_date,
            price_panel=price_panel,
        )
        turnover, turnover_cost = _turnover_cost(previous_weights, target_weights, cost_rate)
        sector_gross_return, active_sector_weights = _weighted_return(
            price_panel=price_panel,
            weights=sector_weights,
            entry_date=entry_date,
            exit_date=exit_date,
        )
        sector_turnover, sector_turnover_cost = _turnover_cost(
            previous_sector_weights,
            active_sector_weights,
            cost_rate,
        )
        sector_quality_return = sector_gross_return - sector_turnover_cost
        stock_return_before_entry_cost, active_weights, stop_count, stopped_symbols = _period_return_with_stops(
            price_panel=price_panel,
            weights=target_weights,
            entry_date=entry_date,
            exit_date=exit_date,
            cost_rate=cost_rate,
        )
        stock_return = stock_return_before_entry_cost - turnover_cost
        spy_return = float(price_panel.at[exit_date, "SPY"] / price_panel.at[entry_date, "SPY"] - 1.0)

        rows.append(
            {
                "scope": scope,
                "mode": mode,
                "signal_date": signal_date,
                "entry_date": entry_date,
                "exit_date": exit_date,
                "regime_label": source_row.regime_label,
                "sector_weights": json.dumps(sector_weights, sort_keys=True),
                "constituent_weights": json.dumps(target_weights, sort_keys=True),
                "sectors_used": json.dumps(sectors_used, sort_keys=True),
                "missing_top_holding_symbols": json.dumps(missing_top_holdings, sort_keys=True),
                "holding_source": "point_in_time_holdings",
                "stock_top5_return": stock_return,
                "spy_return": spy_return,
                "sector_quality_return": sector_quality_return,
                "source_sector_quality_return": float(getattr(source_row, "quality_return", np.nan)),
                "turnover": turnover,
                "turnover_cost": turnover_cost,
                "sector_turnover": sector_turnover,
                "sector_turnover_cost": sector_turnover_cost,
                "stop_count": stop_count,
                "stopped_symbols": stopped_symbols,
                "selected_sector_count": len(sector_weights),
                "selected_stock_count": len(target_weights),
            }
        )
        previous_weights = active_weights
        previous_sector_weights = active_sector_weights

    result = pd.DataFrame(rows)
    if result.empty:
        summary = pd.DataFrame()
        return result, summary

    result["equity_top5"] = (1.0 + result["stock_top5_return"]).cumprod()
    result["equity_spy"] = (1.0 + result["spy_return"]).cumprod()
    result["equity_sector_quality"] = (1.0 + result["sector_quality_return"].fillna(0.0)).cumprod()

    summary_rows = []
    for label, return_column, turnover_column in (
        (TOP5_STRATEGY_LABEL, "stock_top5_return", "turnover"),
        (SECTOR_ETF_STRATEGY_LABEL, "sector_quality_return", "sector_turnover"),
        (BENCHMARK_STRATEGY_LABEL, "spy_return", None),
    ):
        summary = _summarize_return_stream(result, return_column, turnover_column=turnover_column)
        summary_rows.append({"scope": scope, "mode": mode, "strategy_label": label, **summary})
    summary_frame = pd.DataFrame(summary_rows)
    return result, summary_frame


def main() -> None:
    config = dict(DEFAULT_SECTOR_ML_CONFIG)
    holdings = _load_point_in_time_holdings(DEFAULT_HOLDINGS_PATH)
    coverage_start = pd.Timestamp(holdings["known_from_date"].min())
    symbols = sorted(set(holdings["holding_symbol"]) | set(holdings["sector_symbol"]) | {"SPY"})
    required_symbols = set(holdings["sector_symbol"]) | {"SPY"}
    price_panel = _load_close_panel(symbols, required_symbols=required_symbols)

    period_logs: list[pd.DataFrame] = []
    summaries: list[pd.DataFrame] = []
    for scope in ("history", "holdout"):
        for mode in ("ml_5bar", "regime_change"):
            periods, summary = _run_scope(
                scope=scope,
                mode=mode,
                holdings=holdings,
                price_panel=price_panel,
                config=config,
                coverage_start=coverage_start,
            )
            period_logs.append(periods)
            summaries.append(summary)

    non_empty_period_logs = [frame for frame in period_logs if not frame.empty]
    non_empty_summaries = [frame for frame in summaries if not frame.empty]
    period_log_rows = [
        row
        for frame in non_empty_period_logs
        for row in frame.to_dict(orient="records")
    ]
    summary_rows = [
        row
        for frame in non_empty_summaries
        for row in frame.to_dict(orient="records")
    ]
    period_log_frame = pd.DataFrame(period_log_rows)
    summary_frame = pd.DataFrame(summary_rows)
    leaderboard_frame = _build_holdout_leaderboard(summary_frame)
    best_strategy_assessment = _build_best_strategy_assessment(leaderboard_frame)

    period_output = REPORT_DIR / "sector_ml_pit_top5_holdings_period_log.csv"
    summary_output = REPORT_DIR / "sector_ml_pit_top5_holdings_strategy_summary.csv"
    leaderboard_output = REPORT_DIR / "sector_ml_pit_top5_holdings_leaderboard.csv"
    assessment_output = REPORT_DIR / "sector_ml_pit_top5_holdings_best_strategy_assessment.json"
    period_log_frame.to_csv(period_output, index=False)
    summary_frame.to_csv(summary_output, index=False)
    leaderboard_frame.to_csv(leaderboard_output, index=False)
    assessment_output.write_text(json.dumps(best_strategy_assessment, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "period_log": str(period_output),
                "summary": str(summary_output),
                "leaderboard": str(leaderboard_output),
                "best_strategy_assessment": str(assessment_output),
            },
            indent=2,
        )
    )
    if not summary_frame.empty:
        printable = summary_frame[
            [
                "scope",
                "mode",
                "strategy_label",
                "total_return",
                "cagr",
                "sharpe",
                "max_drawdown",
                "trade_count",
                "period_count",
            ]
        ].copy()
        print(printable.to_string(index=False))
    if not leaderboard_frame.empty:
        selected_printable = leaderboard_frame.loc[
            leaderboard_frame["selected_on_history"],
            [
                "mode",
                "strategy_label",
                "history_rank",
                "history_sharpe",
                "history_cagr",
                "history_max_drawdown",
                "holdout_rank",
                "holdout_sharpe",
                "holdout_cagr",
                "holdout_max_drawdown",
                "holdout_total_return_vs_spy",
            ],
        ].copy()
        print(selected_printable.to_string(index=False))


if __name__ == "__main__":
    main()
