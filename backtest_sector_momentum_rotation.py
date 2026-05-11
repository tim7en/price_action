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


REPORT_DIR = PROJECT_ROOT / "outputs" / "sector_rotation_report"
START_DATE = pd.Timestamp("2006-01-01")
HOLDOUT_START = pd.Timestamp("2025-01-01")
COST_RATE = 15.0 / 10_000.0
STOP_LOSS = 0.10

LEGACY_SECTORS = ["XLE", "XLB", "XLI", "XLF", "XLY", "XLK", "XLP", "XLV", "XLU"]
MODERN_SECTORS = [*LEGACY_SECTORS, "XLRE", "XLC"]
GOLD = "GLD"
BENCHMARK = "SPY"

LOOKBACK_BARS = (21, 63, 126, 252)
REBALANCE_BARS = (5, 21, 63)
TOP_N_VALUES = (1, 2, 3, 5)
WEIGHTING_MODES = ("equal", "momentum")
STOP_MODES = (False, True)


def _load_close_panel(symbols: list[str]) -> pd.DataFrame:
    frames: list[pd.Series] = []
    for symbol in symbols:
        close = pd.to_numeric(load_asset_daily(symbol, project_root=PROJECT_ROOT)["close"], errors="coerce")
        frames.append(close.rename(symbol))
    panel = pd.concat(frames, axis=1).sort_index().ffill()
    panel.index.name = "date"
    return panel


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


def _rank_weights(
    trailing_returns: pd.Series,
    top_n: int,
    weighting_mode: str,
) -> tuple[dict[str, float], str]:
    valid = trailing_returns.dropna().sort_values(ascending=False).head(top_n)
    if valid.empty:
        return {}, "Cash"

    if weighting_mode == "equal":
        weights = pd.Series(1.0 / len(valid), index=valid.index)
    elif weighting_mode == "momentum":
        positive = valid.clip(lower=0.0)
        if float(positive.sum()) <= 0.0:
            weights = pd.Series(1.0 / len(valid), index=valid.index)
        else:
            weights = positive / positive.sum()
    else:
        raise ValueError(f"Unknown weighting_mode: {weighting_mode}")

    return {str(symbol): float(weight) for symbol, weight in weights.items()}, ", ".join(valid.index.tolist())


def _turnover(previous: dict[str, float], current: dict[str, float]) -> float:
    symbols = set(previous) | set(current)
    return float(sum(abs(current.get(symbol, 0.0) - previous.get(symbol, 0.0)) for symbol in symbols))


def _return_with_optional_stop(
    price_panel: pd.DataFrame,
    weights: dict[str, float],
    entry_date: pd.Timestamp,
    exit_date: pd.Timestamp,
    use_stop: bool,
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

        if use_stop:
            stop_price = float(entry_price) * (1.0 - STOP_LOSS)
            breach = series.iloc[1:].loc[series.iloc[1:] <= stop_price]
            if not breach.empty:
                stopped_symbols.append(f"{symbol}@{breach.index[0].date()}")
                gross_return += float(weight) * -STOP_LOSS
                continue

        active_weights[symbol] = float(weight)
        gross_return += float(weight) * (float(series.iloc[-1]) / float(entry_price) - 1.0)

    stop_exit_cost = (sum(weights.values()) - sum(active_weights.values())) * COST_RATE
    return gross_return - stop_exit_cost, active_weights, len(stopped_symbols), "; ".join(stopped_symbols)


def _run_config(
    price_panel: pd.DataFrame,
    universe_name: str,
    symbols: list[str],
    include_gold: bool,
    lookback_bars: int,
    rebalance_bars: int,
    top_n: int,
    weighting_mode: str,
    use_stop: bool,
) -> pd.DataFrame:
    trading_index = price_panel.index
    start_pos = trading_index.searchsorted(START_DATE)
    previous_weights: dict[str, float] = {}
    rows: list[dict[str, Any]] = []

    pointer = max(start_pos, lookback_bars)
    while pointer + 1 < len(trading_index):
        signal_date = trading_index[pointer]
        entry_pos = pointer + 1
        exit_pos = min(entry_pos + rebalance_bars, len(trading_index) - 1)
        entry_date = trading_index[entry_pos]
        exit_date = trading_index[exit_pos]
        lookback_date = trading_index[pointer - lookback_bars]

        current_prices = price_panel.loc[signal_date, symbols]
        lookback_prices = price_panel.loc[lookback_date, symbols]
        trailing_returns = current_prices / lookback_prices - 1.0
        trailing_returns = trailing_returns.replace([np.inf, -np.inf], np.nan).dropna()

        weights, selected = _rank_weights(
            trailing_returns=trailing_returns,
            top_n=top_n,
            weighting_mode=weighting_mode,
        )
        weights = {
            symbol: weight
            for symbol, weight in weights.items()
            if symbol in price_panel.columns and pd.notna(price_panel.at[entry_date, symbol])
        }
        turnover = _turnover(previous_weights, weights)
        strategy_gross, active_weights, stop_count, stopped_symbols = _return_with_optional_stop(
            price_panel=price_panel,
            weights=weights,
            entry_date=entry_date,
            exit_date=exit_date,
            use_stop=use_stop,
        )
        strategy_return = strategy_gross - turnover * COST_RATE
        spy_return = float(price_panel.at[exit_date, BENCHMARK] / price_panel.at[entry_date, BENCHMARK] - 1.0)

        rows.append(
            {
                "universe": universe_name,
                "include_gold": include_gold,
                "lookback_bars": lookback_bars,
                "rebalance_bars": rebalance_bars,
                "top_n": top_n,
                "weighting_mode": weighting_mode,
                "stop_loss": STOP_LOSS if use_stop else 0.0,
                "signal_date": signal_date,
                "entry_date": entry_date,
                "exit_date": exit_date,
                "lookback_date": lookback_date,
                "selected": selected,
                "weights": json.dumps(weights, sort_keys=True),
                "strategy_return": strategy_return,
                "spy_return": spy_return,
                "turnover": turnover,
                "turnover_cost": turnover * COST_RATE,
                "stop_count": stop_count,
                "stopped_symbols": stopped_symbols,
                "gold_weight": float(weights.get(GOLD, 0.0)),
                "selected_count": len(weights),
            }
        )
        previous_weights = active_weights
        pointer += rebalance_bars

    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["config_id"] = (
            universe_name
            + "|gold="
            + frame["include_gold"].astype(str)
            + "|lb="
            + frame["lookback_bars"].astype(str)
            + "|rb="
            + frame["rebalance_bars"].astype(str)
            + "|top="
            + frame["top_n"].astype(str)
            + "|w="
            + frame["weighting_mode"].astype(str)
            + "|stop="
            + frame["stop_loss"].astype(str)
        )
        frame["equity_strategy"] = (1.0 + frame["strategy_return"]).cumprod()
        frame["equity_spy"] = (1.0 + frame["spy_return"]).cumprod()
    return frame


def _summaries_for_config(periods: pd.DataFrame) -> list[dict[str, Any]]:
    if periods.empty:
        return []
    rows: list[dict[str, Any]] = []
    base = {
        "config_id": str(periods["config_id"].iloc[0]),
        "universe": str(periods["universe"].iloc[0]),
        "include_gold": bool(periods["include_gold"].iloc[0]),
        "lookback_bars": int(periods["lookback_bars"].iloc[0]),
        "rebalance_bars": int(periods["rebalance_bars"].iloc[0]),
        "top_n": int(periods["top_n"].iloc[0]),
        "weighting_mode": str(periods["weighting_mode"].iloc[0]),
        "stop_loss": float(periods["stop_loss"].iloc[0]),
    }

    for scope, frame in (
        ("history", periods),
        ("pre_holdout", periods.loc[periods["entry_date"] < HOLDOUT_START]),
        ("holdout", periods.loc[periods["entry_date"] >= HOLDOUT_START]),
    ):
        if frame.empty:
            continue
        rows.append(
            {
                **base,
                "scope": scope,
                "strategy_label": "Top Performer Sector Momentum",
                **_summarize_return_stream(frame, "strategy_return", turnover_column="turnover"),
                "gold_periods": int((frame["gold_weight"] > 0.0).sum()),
                "average_gold_weight": float(frame["gold_weight"].mean()),
            }
        )
        rows.append(
            {
                **base,
                "scope": scope,
                "strategy_label": "SPY Buy And Hold",
                **_summarize_return_stream(frame, "spy_return", turnover_column=None),
                "gold_periods": 0,
                "average_gold_weight": 0.0,
            }
        )
    return rows


def main() -> None:
    universes = {
        "legacy_9": LEGACY_SECTORS,
        "modern_11_dynamic": MODERN_SECTORS,
    }
    all_symbols = sorted({symbol for symbols in universes.values() for symbol in symbols} | {GOLD, BENCHMARK})
    price_panel = _load_close_panel(all_symbols)
    price_panel = price_panel.loc[price_panel.index >= pd.Timestamp("2000-01-01")].copy()

    all_periods: list[pd.DataFrame] = []
    summary_rows: list[dict[str, Any]] = []
    for universe_name, base_symbols in universes.items():
        for include_gold in (False, True):
            symbols = [*base_symbols, GOLD] if include_gold else list(base_symbols)
            for lookback_bars in LOOKBACK_BARS:
                for rebalance_bars in REBALANCE_BARS:
                    for top_n in TOP_N_VALUES:
                        for weighting_mode in WEIGHTING_MODES:
                            for use_stop in STOP_MODES:
                                periods = _run_config(
                                    price_panel=price_panel,
                                    universe_name=universe_name,
                                    symbols=symbols,
                                    include_gold=include_gold,
                                    lookback_bars=lookback_bars,
                                    rebalance_bars=rebalance_bars,
                                    top_n=top_n,
                                    weighting_mode=weighting_mode,
                                    use_stop=use_stop,
                                )
                                all_periods.append(periods)
                                summary_rows.extend(_summaries_for_config(periods))

    period_frame = pd.concat([frame for frame in all_periods if not frame.empty], ignore_index=True)
    summary_frame = pd.DataFrame(summary_rows)
    period_output = REPORT_DIR / "sector_momentum_rotation_period_log.csv"
    summary_output = REPORT_DIR / "sector_momentum_rotation_strategy_summary.csv"
    leaderboard_output = REPORT_DIR / "sector_momentum_rotation_leaderboard.csv"
    period_frame.to_csv(period_output, index=False)
    summary_frame.to_csv(summary_output, index=False)

    leaderboard = summary_frame.loc[
        summary_frame["strategy_label"].eq("Top Performer Sector Momentum")
        & summary_frame["scope"].eq("pre_holdout")
    ].copy()
    holdout = summary_frame.loc[
        summary_frame["strategy_label"].eq("Top Performer Sector Momentum")
        & summary_frame["scope"].eq("holdout")
    ][["config_id", "total_return", "cagr", "sharpe", "max_drawdown"]].rename(
        columns={
            "total_return": "holdout_total_return",
            "cagr": "holdout_cagr",
            "sharpe": "holdout_sharpe",
            "max_drawdown": "holdout_max_drawdown",
        }
    )
    leaderboard = leaderboard.merge(holdout, on="config_id", how="left")
    leaderboard = leaderboard.sort_values(
        ["sharpe", "cagr", "max_drawdown"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    leaderboard.to_csv(leaderboard_output, index=False)

    print(
        json.dumps(
            {
                "period_log": str(period_output),
                "summary": str(summary_output),
                "leaderboard": str(leaderboard_output),
            },
            indent=2,
        )
    )
    printable = leaderboard[
        [
            "universe",
            "include_gold",
            "lookback_bars",
            "rebalance_bars",
            "top_n",
            "weighting_mode",
            "stop_loss",
            "cagr",
            "sharpe",
            "max_drawdown",
            "holdout_cagr",
            "holdout_sharpe",
            "holdout_max_drawdown",
        ]
    ].head(20)
    print(printable.to_string(index=False))


if __name__ == "__main__":
    main()
