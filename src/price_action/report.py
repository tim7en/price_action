from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .data import load_asset_daily
from .features import bounded_momentum_oscillator
from .panel import apply_panel_trade_schedule, summarize_panel_predictions
from .train import summarize_predictions


PAPER_BACKGROUND = "#f4edcf"
PAPER_GRID_MAJOR = "#c7ad72"
PAPER_GRID_MINOR = "#e4d5a8"
PAPER_INK = "#27313a"
PAPER_BLUE = "#185f9d"
PAPER_GREEN = "#2f7d56"
PAPER_RED = "#a74335"
PAPER_PURPLE = "#685089"
MOMENTUM_OSCILLATOR_COLUMN = "momentum_oscillator"


def _style_paper_axis(ax, *, grid: bool = True) -> None:
    ax.set_facecolor(PAPER_BACKGROUND)
    ax.tick_params(colors=PAPER_INK, labelsize=9)
    ax.title.set_color(PAPER_INK)
    ax.xaxis.label.set_color(PAPER_INK)
    ax.yaxis.label.set_color(PAPER_INK)
    for spine in ax.spines.values():
        spine.set_color("#9d8554")
        spine.set_linewidth(0.8)
    if grid:
        ax.minorticks_on()
        ax.grid(True, which="major", color=PAPER_GRID_MAJOR, linewidth=0.8, alpha=0.8)
        ax.grid(True, which="minor", color=PAPER_GRID_MINOR, linewidth=0.45, alpha=0.75)
        ax.set_axisbelow(True)


def _new_paper_figure(*args, **kwargs):
    fig, axes = plt.subplots(*args, facecolor=PAPER_BACKGROUND, **kwargs)
    axis_array = axes.ravel() if isinstance(axes, np.ndarray) else [axes]
    for ax in axis_array:
        _style_paper_axis(ax)
    return fig, axes


def load_outputs(output_dir: str | Path) -> tuple[pd.DataFrame, dict[str, Any], str]:
    output_path = Path(output_dir)
    summary_path = output_path / "summary.json"

    if (output_path / "panel_walk_forward_predictions.csv").exists():
        predictions_path = output_path / "panel_walk_forward_predictions.csv"
        mode = "panel"
    else:
        predictions_path = output_path / "walk_forward_predictions.csv"
        mode = "single"

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    predictions = pd.read_csv(predictions_path, parse_dates=["date"], low_memory=False)
    if "fold_label" in predictions.columns:
        predictions["fold_label"] = predictions["fold_label"].astype(str)
    return predictions, summary, mode


def attach_momentum_oscillator(
    predictions: pd.DataFrame,
    summary: dict[str, Any],
) -> pd.DataFrame:
    existing = pd.to_numeric(
        predictions.get(MOMENTUM_OSCILLATOR_COLUMN, pd.Series(dtype=float)),
        errors="coerce",
    )
    if existing.notna().any():
        frame = predictions.copy()
        frame[MOMENTUM_OSCILLATOR_COLUMN] = existing
        return frame

    frame = predictions.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame["_row_order"] = np.arange(len(frame))

    if "symbol" in frame.columns:
        symbols = sorted(frame["symbol"].dropna().astype(str).str.upper().unique())
        oscillator_frames: list[pd.DataFrame] = []
        for symbol in symbols:
            try:
                asset_frame = load_asset_daily(symbol)
            except FileNotFoundError:
                continue
            if "close" not in asset_frame.columns:
                continue
            oscillator = bounded_momentum_oscillator(asset_frame["close"]).rename(MOMENTUM_OSCILLATOR_COLUMN)
            symbol_frame = oscillator.reset_index()
            symbol_frame["symbol"] = symbol
            oscillator_frames.append(symbol_frame)

        if oscillator_frames:
            oscillator_panel = pd.concat(oscillator_frames, ignore_index=True)
            frame["symbol"] = frame["symbol"].astype(str).str.upper()
            frame = frame.merge(oscillator_panel, on=["date", "symbol"], how="left")
    else:
        symbol = str(summary.get("symbol", "")).upper()
        if symbol:
            try:
                asset_frame = load_asset_daily(symbol)
            except FileNotFoundError:
                asset_frame = pd.DataFrame()
            if not asset_frame.empty and "close" in asset_frame.columns:
                oscillator = bounded_momentum_oscillator(asset_frame["close"]).rename(MOMENTUM_OSCILLATOR_COLUMN)
                frame = frame.merge(oscillator.reset_index(), on="date", how="left")

    frame = frame.sort_values("_row_order").drop(columns=["_row_order"])
    return frame


def compute_daily_equity(predictions: pd.DataFrame, mode: str) -> pd.DataFrame:
    frame = predictions.copy()
    frame["date"] = pd.to_datetime(frame["date"])

    if mode == "panel":
        daily_returns = frame.groupby("date")["strategy_return"].mean().sort_index()
        active_trades = frame.groupby("date")["take_trade"].sum().sort_index()
    else:
        daily_returns = frame.groupby("date")["strategy_return"].sum().sort_index()
        active_trades = frame.groupby("date")["take_trade"].sum().sort_index()

    equity = (1.0 + daily_returns.fillna(0.0)).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    return pd.DataFrame(
        {
            "date": daily_returns.index,
            "daily_return": daily_returns.to_numpy(),
            "equity": equity.to_numpy(),
            "drawdown": drawdown.to_numpy(),
            "active_trades": active_trades.reindex(daily_returns.index, fill_value=0).to_numpy(),
        }
    )


def compute_holdout_probability_buckets(predictions: pd.DataFrame) -> pd.DataFrame:
    holdout = predictions.loc[predictions["fold_label"] == "holdout"].copy()
    if holdout.empty:
        return pd.DataFrame()

    holdout["bucket"] = pd.qcut(holdout["gated_probability"], q=6, duplicates="drop")
    bucket_stats = (
        holdout.groupby("bucket", observed=True)
        .agg(
            count=("gated_probability", "size"),
            mean_probability=("gated_probability", "mean"),
            hit_rate=("target", "mean"),
            mean_net_forward_return=("net_forward_return", "mean"),
            trade_rate=("take_trade", "mean"),
        )
        .reset_index()
    )
    bucket_stats["bucket_label"] = bucket_stats["bucket"].astype(str)
    return bucket_stats


def compute_threshold_sweep(predictions: pd.DataFrame, summary: dict[str, Any], mode: str) -> pd.DataFrame:
    holdout = predictions.loc[predictions["fold_label"] == "holdout"].copy()
    if holdout.empty:
        return pd.DataFrame()

    thresholds = np.arange(0.50, 0.81, 0.02)
    rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        if mode == "panel":
            scheduled = apply_panel_trade_schedule(
                predictions=holdout.copy(),
                probability_column="gated_probability",
                signal_threshold=float(threshold),
                cooldown_bars=int(summary.get("label_horizon", 5)),
                skip_risk_off=True,
            )
            sweep_summary = summarize_panel_predictions(scheduled, signal_threshold=float(threshold))
        else:
            scheduled = holdout.copy()
            probabilities = scheduled["gated_probability"].to_numpy(dtype=float)
            net_returns = scheduled["net_forward_return"].to_numpy(dtype=float)
            risk_off = scheduled.get("regime_risk_off", pd.Series(np.zeros(len(scheduled)))).to_numpy(dtype=float)
            take_trade = np.zeros(len(scheduled), dtype=int)
            strategy_return = np.zeros(len(scheduled), dtype=float)
            cooldown = 0
            horizon = int(summary.get("label_horizon", 5))
            for index in range(len(scheduled)):
                if cooldown > 0:
                    cooldown -= 1
                    continue
                if probabilities[index] >= threshold and risk_off[index] < 1.0:
                    take_trade[index] = 1
                    strategy_return[index] = net_returns[index]
                    cooldown = max(horizon - 1, 0)
            scheduled["take_trade"] = take_trade
            scheduled["strategy_return"] = strategy_return
            scheduled["equity_curve"] = (1.0 + scheduled["strategy_return"]).cumprod()
            sweep_summary = summarize_predictions(scheduled, signal_threshold=float(threshold))

        rows.append(
            {
                "threshold": float(threshold),
                "trade_count": int(sweep_summary.get("trade_count", 0) or 0),
                "hit_rate": sweep_summary.get("hit_rate"),
                "average_trade_return": sweep_summary.get("average_trade_return"),
                "total_return": sweep_summary.get("total_return"),
                "sharpe": sweep_summary.get("sharpe"),
            }
        )

    return pd.DataFrame(rows)


def compute_symbol_stats(predictions: pd.DataFrame) -> pd.DataFrame:
    if "symbol" not in predictions.columns:
        return pd.DataFrame()
    holdout = predictions.loc[(predictions["fold_label"] == "holdout") & (predictions["take_trade"] == 1)].copy()
    if holdout.empty:
        return pd.DataFrame()

    symbol_stats = (
        holdout.groupby("symbol", observed=True)
        .agg(
            trade_count=("symbol", "size"),
            mean_trade_return=("net_forward_return", "mean"),
            total_trade_return=("net_forward_return", "sum"),
            hit_rate=("target", "mean"),
        )
        .sort_values("total_trade_return", ascending=False)
        .reset_index()
    )
    return symbol_stats


def _analysis_sample(predictions: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    if "fold_label" in predictions.columns:
        holdout = predictions.loc[predictions["fold_label"] == "holdout"].copy()
        if not holdout.empty:
            return holdout, "holdout"
    return predictions.copy(), "all folds"


def compute_daily_momentum_oscillator(predictions: pd.DataFrame, mode: str) -> pd.DataFrame:
    if MOMENTUM_OSCILLATOR_COLUMN not in predictions.columns:
        return pd.DataFrame()

    frame = predictions[["date", MOMENTUM_OSCILLATOR_COLUMN]].copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame[MOMENTUM_OSCILLATOR_COLUMN] = pd.to_numeric(
        frame[MOMENTUM_OSCILLATOR_COLUMN],
        errors="coerce",
    ).clip(-1.0, 1.0)
    frame = frame.dropna(subset=[MOMENTUM_OSCILLATOR_COLUMN])
    if frame.empty:
        return pd.DataFrame()

    daily = frame.groupby("date")[MOMENTUM_OSCILLATOR_COLUMN].mean().sort_index()
    return pd.DataFrame({"date": daily.index, MOMENTUM_OSCILLATOR_COLUMN: daily.to_numpy()})


def compute_momentum_oscillator_research(
    predictions: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if MOMENTUM_OSCILLATOR_COLUMN not in predictions.columns:
        return pd.DataFrame(), {}

    sample, sample_label = _analysis_sample(predictions)
    needed = [
        MOMENTUM_OSCILLATOR_COLUMN,
        "net_forward_return",
        "target",
        "take_trade",
        "gated_probability",
        "strategy_return",
    ]
    missing = [column for column in needed if column not in sample.columns]
    if missing:
        return pd.DataFrame(), {}

    sample = sample.copy()
    sample[MOMENTUM_OSCILLATOR_COLUMN] = pd.to_numeric(
        sample[MOMENTUM_OSCILLATOR_COLUMN],
        errors="coerce",
    ).clip(-1.0, 1.0)
    sample = sample.dropna(subset=[MOMENTUM_OSCILLATOR_COLUMN, "net_forward_return", "target"])
    if sample.empty:
        return pd.DataFrame(), {}

    bins = [-1.000001, -0.6, -0.2, 0.2, 0.6, 1.000001]
    labels = [
        "Strong downside",
        "Downside",
        "Neutral",
        "Upside",
        "Strong upside",
    ]
    sample["oscillator_bucket"] = pd.cut(
        sample[MOMENTUM_OSCILLATOR_COLUMN],
        bins=bins,
        labels=labels,
        include_lowest=True,
    )
    research = (
        sample.groupby("oscillator_bucket", observed=False)
        .agg(
            count=(MOMENTUM_OSCILLATOR_COLUMN, "size"),
            mean_oscillator=(MOMENTUM_OSCILLATOR_COLUMN, "mean"),
            hit_rate=("target", "mean"),
            mean_net_forward_return=("net_forward_return", "mean"),
            median_net_forward_return=("net_forward_return", "median"),
            mean_probability=("gated_probability", "mean"),
            trade_rate=("take_trade", "mean"),
            trade_count=("take_trade", "sum"),
            total_strategy_return=("strategy_return", "sum"),
        )
        .reset_index()
    )
    research["bucket_label"] = research["oscillator_bucket"].astype(str)
    research = research.loc[research["count"] > 0].reset_index(drop=True)

    summary = {
        "sample_label": sample_label,
        "row_count": int(len(sample)),
        "oscillator_forward_return_corr": _safe_corr(
            sample[MOMENTUM_OSCILLATOR_COLUMN],
            sample["net_forward_return"],
        ),
        "oscillator_probability_corr": _safe_corr(
            sample[MOMENTUM_OSCILLATOR_COLUMN],
            sample["gated_probability"],
        ),
    }
    return research, summary


def _safe_corr(left: pd.Series, right: pd.Series) -> float | None:
    valid = pd.concat(
        [
            pd.to_numeric(left, errors="coerce"),
            pd.to_numeric(right, errors="coerce"),
        ],
        axis=1,
    ).dropna()
    if len(valid) < 3 or valid.iloc[:, 0].nunique() < 2 or valid.iloc[:, 1].nunique() < 2:
        return None
    return float(valid.iloc[:, 0].corr(valid.iloc[:, 1]))


def _format_optional_float(value: Any, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not np.isfinite(numeric):
        return "n/a"
    return f"{numeric:.{digits}f}"


def _format_optional_percent(value: Any, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not np.isfinite(numeric):
        return "n/a"
    return f"{numeric:.{digits}%}"


def _momentum_research_markdown(research: pd.DataFrame) -> list[str]:
    if research.empty:
        return []

    lines = [
        "| Oscillator band | Rows | Avg osc | Hit rate | Avg forward return | Trade rate | Avg probability |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in research.itertuples(index=False):
        lines.append(
            "| "
            f"{row.bucket_label} | "
            f"{int(row.count):,} | "
            f"{_format_optional_float(row.mean_oscillator, digits=2)} | "
            f"{_format_optional_percent(row.hit_rate)} | "
            f"{_format_optional_percent(row.mean_net_forward_return, digits=2)} | "
            f"{_format_optional_percent(row.trade_rate)} | "
            f"{_format_optional_float(row.mean_probability, digits=3)} |"
        )
    return lines


def build_key_observations(
    summary: dict[str, Any],
    threshold_sweep: pd.DataFrame,
    mode: str,
    momentum_summary: dict[str, Any] | None = None,
) -> list[str]:
    observations: list[str] = []

    if mode == "panel":
        observations.append(
            f"Pooled panel holdout ROC AUC is {summary.get('holdout_roc_auc', summary.get('roc_auc')):.3f}, which is above chance but still moderate."
        )
        observations.append(
            f"The holdout only fired {summary.get('holdout_trade_count', summary.get('trade_count'))} trades across {summary.get('holdout_active_symbol_count', summary.get('active_symbol_count'))} symbols, so the current threshold behaves like a selective filter, not a broad forecaster."
        )
        observations.append(
            f"Headline holdout return is {summary.get('holdout_total_return', summary.get('total_return')):.1%}, but that is under a simplified equal-weight active-signal aggregation and still needs portfolio-level risk caps before it is deployable."
        )
    else:
        observations.append(
            f"Single-name holdout ROC AUC is {summary.get('holdout_roc_auc', summary.get('roc_auc')):.3f}, which indicates weak directional edge unless used as a filter."
        )

    if not threshold_sweep.empty:
        finite_sweep = threshold_sweep.dropna(subset=["sharpe"])
        if not finite_sweep.empty:
            best_row = finite_sweep.sort_values("sharpe", ascending=False).iloc[0]
            observations.append(
                f"In the holdout threshold sweep, the best ex-post Sharpe occurred near threshold {best_row['threshold']:.2f}, which is a clue for calibration review rather than a parameter to hard-fit immediately."
            )

    if momentum_summary:
        forward_corr = momentum_summary.get("oscillator_forward_return_corr")
        probability_corr = momentum_summary.get("oscillator_probability_corr")
        sample_label = momentum_summary.get("sample_label", "sample")
        row_count = momentum_summary.get("row_count", 0)
        observations.append(
            "The bounded momentum oscillator research uses "
            f"{row_count:,} {sample_label} rows; its return correlation is "
            f"{_format_optional_float(forward_corr, digits=3)} and its model-probability correlation is "
            f"{_format_optional_float(probability_corr, digits=3)}."
        )

    return observations


def write_report_markdown(
    report_dir: Path,
    summary: dict[str, Any],
    observations: list[str],
    mode: str,
    momentum_research: pd.DataFrame | None = None,
    momentum_summary: dict[str, Any] | None = None,
) -> Path:
    lines = [
        "# Results Report",
        "",
        f"Mode: {mode}",
        "",
        "## Key metrics",
        "",
        f"- ROC AUC: {summary.get('roc_auc')}",
        f"- Holdout ROC AUC: {summary.get('holdout_roc_auc', summary.get('roc_auc'))}",
        f"- Holdout total return: {summary.get('holdout_total_return', summary.get('total_return'))}",
        f"- Holdout Sharpe: {summary.get('holdout_sharpe', summary.get('sharpe'))}",
        f"- Holdout max drawdown: {summary.get('holdout_max_drawdown', summary.get('max_drawdown'))}",
        f"- Holdout trade count: {summary.get('holdout_trade_count', summary.get('trade_count'))}",
        "",
        "## Key observations",
        "",
    ]
    lines.extend([f"- {item}" for item in observations])
    lines.extend(
        [
            "",
            "## Charts",
            "",
            "![Dashboard](dashboard.png)",
            "",
        ]
    )
    if (report_dir / "threshold_sweep.png").exists():
        lines.extend(["![Holdout threshold sweep](threshold_sweep.png)", ""])
    if (report_dir / "momentum_oscillator.png").exists():
        lines.extend(["![Momentum oscillator](momentum_oscillator.png)", ""])
    if (report_dir / "momentum_oscillator_research.png").exists():
        lines.extend(["![Momentum oscillator research](momentum_oscillator_research.png)", ""])

    if momentum_research is not None and not momentum_research.empty:
        sample_label = (momentum_summary or {}).get("sample_label", "sample")
        row_count = (momentum_summary or {}).get("row_count", int(momentum_research["count"].sum()))
        lines.extend(
            [
                "## Momentum oscillator research",
                "",
                "The oscillator is an RSI-style bounded momentum feature mapped to `-1..1`, where negative values mean downside momentum, zero is neutral, and positive values mean upside momentum.",
                "",
                f"Sample: {sample_label}, rows: {row_count:,}.",
                "",
            ]
        )
        lines.extend(_momentum_research_markdown(momentum_research))
        lines.extend(
            [
                "",
                f"- Return correlation: {_format_optional_float((momentum_summary or {}).get('oscillator_forward_return_corr'), digits=3)}",
                f"- Model-probability correlation: {_format_optional_float((momentum_summary or {}).get('oscillator_probability_corr'), digits=3)}",
                "",
            ]
        )

    report_path = report_dir / "report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def write_momentum_oscillator_chart(daily_momentum: pd.DataFrame, report_dir: Path) -> Path | None:
    if daily_momentum.empty:
        return None

    fig, ax = _new_paper_figure(figsize=(12, 4.5), constrained_layout=True)
    values = daily_momentum[MOMENTUM_OSCILLATOR_COLUMN].astype(float)
    ax.plot(daily_momentum["date"], values, color=PAPER_BLUE, linewidth=1.4)
    ax.fill_between(
        daily_momentum["date"],
        values,
        0.0,
        where=values >= 0.0,
        color=PAPER_GREEN,
        alpha=0.18,
        interpolate=True,
    )
    ax.fill_between(
        daily_momentum["date"],
        values,
        0.0,
        where=values < 0.0,
        color=PAPER_RED,
        alpha=0.18,
        interpolate=True,
    )
    ax.axhline(0.0, color=PAPER_INK, linewidth=1.0)
    ax.axhline(0.6, color=PAPER_GREEN, linewidth=0.9, linestyle="--", alpha=0.75)
    ax.axhline(-0.6, color=PAPER_RED, linewidth=0.9, linestyle="--", alpha=0.75)
    ax.set_ylim(-1.05, 1.05)
    ax.set_title("Momentum Oscillator (-1 to 1)")
    ax.set_ylabel("Oscillator")
    ax.set_xlabel("Date")
    path = report_dir / "momentum_oscillator.png"
    fig.savefig(path, dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def write_momentum_research_chart(research: pd.DataFrame, report_dir: Path) -> Path | None:
    if research.empty:
        return None

    fig, ax1 = plt.subplots(figsize=(11, 5), constrained_layout=True, facecolor=PAPER_BACKGROUND)
    _style_paper_axis(ax1)
    ax2 = ax1.twinx()
    _style_paper_axis(ax2, grid=False)
    ax2.set_facecolor("none")

    x = np.arange(len(research))
    returns = research["mean_net_forward_return"].astype(float).to_numpy()
    hit_rate = research["hit_rate"].astype(float).to_numpy()
    colors = [PAPER_GREEN if value >= 0.0 else PAPER_RED for value in returns]

    ax1.bar(x, returns, color=colors, alpha=0.72, width=0.62, label="Avg forward return")
    ax1.axhline(0.0, color=PAPER_INK, linewidth=0.9)
    ax2.plot(x, hit_rate, color=PAPER_BLUE, marker="o", linewidth=1.7, label="Hit rate")
    ax2.axhline(0.5, color=PAPER_PURPLE, linewidth=0.9, linestyle="--", alpha=0.75)

    ax1.set_xticks(x)
    ax1.set_xticklabels(research["bucket_label"], rotation=15, ha="right")
    ax1.set_title("Holdout Return By Momentum Oscillator Band")
    ax1.set_ylabel("Mean net forward return")
    ax2.set_ylabel("Hit rate")

    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc="upper left", frameon=False)

    path = report_dir / "momentum_oscillator_research.png"
    fig.savefig(path, dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def generate_plots(output_dir: str | Path) -> dict[str, str]:
    predictions, summary, mode = load_outputs(output_dir)
    predictions = attach_momentum_oscillator(predictions=predictions, summary=summary)
    report_dir = Path(output_dir) / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    equity = compute_daily_equity(predictions=predictions, mode=mode)
    holdout_start = pd.to_datetime(summary.get("holdout_start")) if summary.get("holdout_start") else None
    threshold_sweep = compute_threshold_sweep(predictions=predictions, summary=summary, mode=mode)
    bucket_stats = compute_holdout_probability_buckets(predictions=predictions)
    symbol_stats = compute_symbol_stats(predictions=predictions)
    daily_momentum = compute_daily_momentum_oscillator(predictions=predictions, mode=mode)
    momentum_research, momentum_summary = compute_momentum_oscillator_research(predictions=predictions)

    fig, axes = _new_paper_figure(2, 2, figsize=(15, 10), constrained_layout=True)
    axes[0, 0].plot(equity["date"], equity["equity"], color=PAPER_BLUE, linewidth=1.8)
    if holdout_start is not None:
        axes[0, 0].axvline(holdout_start, color=PAPER_RED, linestyle="--", linewidth=1.2)
    axes[0, 0].set_title("Equity Curve")
    axes[0, 0].set_ylabel("Equity")

    axes[0, 1].fill_between(equity["date"], equity["drawdown"], 0.0, color=PAPER_RED, alpha=0.25)
    if holdout_start is not None:
        axes[0, 1].axvline(holdout_start, color=PAPER_BLUE, linestyle="--", linewidth=1.2)
    axes[0, 1].set_title("Drawdown")
    axes[0, 1].set_ylabel("Drawdown")

    if not symbol_stats.empty:
        top_stats = symbol_stats.head(10).sort_values("total_trade_return")
        axes[1, 0].barh(top_stats["symbol"], top_stats["total_trade_return"], color=PAPER_GREEN)
        axes[1, 0].set_title("Holdout Trade Contribution By Symbol")
        axes[1, 0].set_xlabel("Total net trade return")
    else:
        axes[1, 0].text(0.5, 0.5, "No symbol-level holdout trades", ha="center", va="center")
        axes[1, 0].set_title("Holdout Trade Contribution By Symbol")

    if not bucket_stats.empty:
        axes[1, 1].bar(bucket_stats["bucket_label"], bucket_stats["mean_net_forward_return"], color=PAPER_PURPLE)
        axes[1, 1].set_title("Holdout Return By Probability Bucket")
        axes[1, 1].set_ylabel("Mean net forward return")
        axes[1, 1].tick_params(axis="x", rotation=20)
    else:
        axes[1, 1].text(0.5, 0.5, "No holdout bucket data", ha="center", va="center")
        axes[1, 1].set_title("Holdout Return By Probability Bucket")

    dashboard_path = report_dir / "dashboard.png"
    fig.savefig(dashboard_path, dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)

    if not threshold_sweep.empty:
        fig, ax1 = plt.subplots(figsize=(10, 5), constrained_layout=True, facecolor=PAPER_BACKGROUND)
        _style_paper_axis(ax1)
        ax2 = ax1.twinx()
        _style_paper_axis(ax2, grid=False)
        ax2.set_facecolor("none")
        ax1.plot(threshold_sweep["threshold"], threshold_sweep["trade_count"], color=PAPER_BLUE, marker="o", label="trade_count")
        ax2.plot(threshold_sweep["threshold"], threshold_sweep["hit_rate"], color=PAPER_GREEN, marker="s", label="hit_rate")
        ax1.set_title("Holdout Threshold Sweep")
        ax1.set_xlabel("Probability threshold")
        ax1.set_ylabel("Trade count", color=PAPER_BLUE)
        ax2.set_ylabel("Hit rate", color=PAPER_GREEN)
        threshold_path = report_dir / "threshold_sweep.png"
        fig.savefig(threshold_path, dpi=180, facecolor=fig.get_facecolor())
        plt.close(fig)
    else:
        threshold_path = report_dir / "threshold_sweep.png"

    momentum_path = write_momentum_oscillator_chart(daily_momentum=daily_momentum, report_dir=report_dir)
    momentum_research_path = write_momentum_research_chart(research=momentum_research, report_dir=report_dir)

    if not bucket_stats.empty:
        bucket_stats.to_csv(report_dir / "holdout_probability_buckets.csv", index=False)
    if not threshold_sweep.empty:
        threshold_sweep.to_csv(report_dir / "holdout_threshold_sweep.csv", index=False)
    if not symbol_stats.empty:
        symbol_stats.to_csv(report_dir / "holdout_symbol_stats.csv", index=False)
    if not momentum_research.empty:
        momentum_research.to_csv(report_dir / "holdout_momentum_oscillator_research.csv", index=False)

    observations = build_key_observations(
        summary=summary,
        threshold_sweep=threshold_sweep,
        mode=mode,
        momentum_summary=momentum_summary,
    )
    report_path = write_report_markdown(
        report_dir=report_dir,
        summary=summary,
        observations=observations,
        mode=mode,
        momentum_research=momentum_research,
        momentum_summary=momentum_summary,
    )

    generated = {
        "dashboard": str(dashboard_path),
        "threshold_sweep": str(threshold_path),
        "report": str(report_path),
    }
    if momentum_path is not None:
        generated["momentum_oscillator"] = str(momentum_path)
    if momentum_research_path is not None:
        generated["momentum_oscillator_research"] = str(momentum_research_path)
    return generated


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate plots and a summary report from saved experiment outputs.")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Experiment output directory, for example outputs/default_panel or outputs/amzn.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    generated = generate_plots(args.output_dir)
    print(json.dumps(generated, indent=2))


if __name__ == "__main__":
    main()
