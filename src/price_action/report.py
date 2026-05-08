from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .panel import apply_panel_trade_schedule, summarize_panel_predictions
from .train import summarize_predictions


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


def build_key_observations(summary: dict[str, Any], threshold_sweep: pd.DataFrame, mode: str) -> list[str]:
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
        best_row = threshold_sweep.dropna(subset=["sharpe"]).sort_values("sharpe", ascending=False).iloc[0]
        observations.append(
            f"In the holdout threshold sweep, the best ex-post Sharpe occurred near threshold {best_row['threshold']:.2f}, which is a clue for calibration review rather than a parameter to hard-fit immediately."
        )

    return observations


def write_report_markdown(
    report_dir: Path,
    summary: dict[str, Any],
    observations: list[str],
    mode: str,
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
    report_path = report_dir / "report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def generate_plots(output_dir: str | Path) -> dict[str, str]:
    predictions, summary, mode = load_outputs(output_dir)
    report_dir = Path(output_dir) / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    equity = compute_daily_equity(predictions=predictions, mode=mode)
    holdout_start = pd.to_datetime(summary.get("holdout_start")) if summary.get("holdout_start") else None
    threshold_sweep = compute_threshold_sweep(predictions=predictions, summary=summary, mode=mode)
    bucket_stats = compute_holdout_probability_buckets(predictions=predictions)
    symbol_stats = compute_symbol_stats(predictions=predictions)

    fig, axes = plt.subplots(2, 2, figsize=(15, 10), constrained_layout=True)
    axes[0, 0].plot(equity["date"], equity["equity"], color="#0f6cbd", linewidth=1.8)
    if holdout_start is not None:
        axes[0, 0].axvline(holdout_start, color="#c50f1f", linestyle="--", linewidth=1.2)
    axes[0, 0].set_title("Equity Curve")
    axes[0, 0].set_ylabel("Equity")

    axes[0, 1].fill_between(equity["date"], equity["drawdown"], 0.0, color="#c50f1f", alpha=0.25)
    if holdout_start is not None:
        axes[0, 1].axvline(holdout_start, color="#0f6cbd", linestyle="--", linewidth=1.2)
    axes[0, 1].set_title("Drawdown")
    axes[0, 1].set_ylabel("Drawdown")

    if not symbol_stats.empty:
        top_stats = symbol_stats.head(10).sort_values("total_trade_return")
        axes[1, 0].barh(top_stats["symbol"], top_stats["total_trade_return"], color="#107c10")
        axes[1, 0].set_title("Holdout Trade Contribution By Symbol")
        axes[1, 0].set_xlabel("Total net trade return")
    else:
        axes[1, 0].text(0.5, 0.5, "No symbol-level holdout trades", ha="center", va="center")
        axes[1, 0].set_title("Holdout Trade Contribution By Symbol")

    if not bucket_stats.empty:
        axes[1, 1].bar(bucket_stats["bucket_label"], bucket_stats["mean_net_forward_return"], color="#744da9")
        axes[1, 1].set_title("Holdout Return By Probability Bucket")
        axes[1, 1].set_ylabel("Mean net forward return")
        axes[1, 1].tick_params(axis="x", rotation=20)
    else:
        axes[1, 1].text(0.5, 0.5, "No holdout bucket data", ha="center", va="center")
        axes[1, 1].set_title("Holdout Return By Probability Bucket")

    dashboard_path = report_dir / "dashboard.png"
    fig.savefig(dashboard_path, dpi=180)
    plt.close(fig)

    if not threshold_sweep.empty:
        fig, ax1 = plt.subplots(figsize=(10, 5), constrained_layout=True)
        ax2 = ax1.twinx()
        ax1.plot(threshold_sweep["threshold"], threshold_sweep["trade_count"], color="#0f6cbd", marker="o", label="trade_count")
        ax2.plot(threshold_sweep["threshold"], threshold_sweep["hit_rate"], color="#107c10", marker="s", label="hit_rate")
        ax1.set_title("Holdout Threshold Sweep")
        ax1.set_xlabel("Probability threshold")
        ax1.set_ylabel("Trade count", color="#0f6cbd")
        ax2.set_ylabel("Hit rate", color="#107c10")
        threshold_path = report_dir / "threshold_sweep.png"
        fig.savefig(threshold_path, dpi=180)
        plt.close(fig)
    else:
        threshold_path = report_dir / "threshold_sweep.png"

    if not bucket_stats.empty:
        bucket_stats.to_csv(report_dir / "holdout_probability_buckets.csv", index=False)
    if not threshold_sweep.empty:
        threshold_sweep.to_csv(report_dir / "holdout_threshold_sweep.csv", index=False)
    if not symbol_stats.empty:
        symbol_stats.to_csv(report_dir / "holdout_symbol_stats.csv", index=False)

    observations = build_key_observations(summary=summary, threshold_sweep=threshold_sweep, mode=mode)
    report_path = write_report_markdown(report_dir=report_dir, summary=summary, observations=observations, mode=mode)

    return {
        "dashboard": str(dashboard_path),
        "threshold_sweep": str(threshold_path),
        "report": str(report_path),
    }


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
