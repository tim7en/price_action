"""Compound the frozen hierarchical NASDAQ POC ledger in a small-account scenario."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from price_action.data import resolve_project_root
from price_action.nasdaq_fabio_pine_v6_backtest import _markdown_table


DEFAULT_TRADES = Path(
    "outputs/nasdaq_poc_hierarchical_trend_strategy/annotated_hierarchy_trades.csv"
)
DEFAULT_OUTPUT = Path("outputs/nasdaq_poc_100usd_20x_2pct")
VALIDATION_START = pd.Timestamp("2025-01-01", tz="UTC")


def load_eligible_trades(path: str | Path, minimum_score: int = 3) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {
        "entry_time",
        "exit_time",
        "session_date",
        "side",
        "entry_price",
        "stop_fraction",
        "signed_price_return",
        "hierarchy_score",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Hierarchical ledger is missing columns: {sorted(missing)}")
    for column in ("entry_time", "exit_time"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="raise")
    numeric = [
        "entry_price",
        "stop_fraction",
        "signed_price_return",
        "hierarchy_score",
    ]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="raise")
    if frame[numeric].isna().any().any():
        raise ValueError("Eligible trade fields contain missing values")
    return (
        frame.loc[frame["hierarchy_score"].ge(minimum_score)]
        .sort_values(["entry_time", "exit_time"])
        .reset_index(drop=True)
    )


def simulate_equity(
    trades: pd.DataFrame,
    *,
    starting_equity: float = 100.0,
    risk_fraction: float = 0.02,
    maximum_leverage: float = 20.0,
    one_way_cost_bps: float = 0.50,
    force_maximum_leverage: bool = False,
) -> pd.DataFrame:
    """Compound sequential trades using fractional stop-risk sizing and bps costs."""
    if starting_equity <= 0.0:
        raise ValueError("starting_equity must be positive")
    if not 0.0 < risk_fraction < 1.0:
        raise ValueError("risk_fraction must be between zero and one")
    if maximum_leverage <= 0.0 or one_way_cost_bps < 0.0:
        raise ValueError("leverage must be positive and costs cannot be negative")

    rows: list[dict[str, Any]] = []
    equity = float(starting_equity)
    peak = equity
    total_cost_dollars = 0.0
    for trade_number, trade in enumerate(
        trades.sort_values(["entry_time", "exit_time"]).itertuples(index=False), start=1
    ):
        stop_fraction = float(trade.stop_fraction)
        if stop_fraction <= 0.0:
            raise ValueError("stop_fraction must be positive")
        required_leverage = risk_fraction / stop_fraction
        leverage = (
            maximum_leverage
            if force_maximum_leverage
            else min(maximum_leverage, required_leverage)
        )
        deployed_risk = leverage * stop_fraction
        gross_return = leverage * float(trade.signed_price_return)
        cost_fraction = leverage * 2.0 * one_way_cost_bps / 10_000.0
        net_return = gross_return - cost_fraction
        if net_return <= -1.0:
            net_return = -1.0

        equity_before = equity
        cost_dollars = equity_before * cost_fraction
        net_pnl_dollars = equity_before * net_return
        equity = max(0.0, equity_before + net_pnl_dollars)
        total_cost_dollars += cost_dollars
        peak = max(peak, equity)
        rows.append(
            {
                "variant": (
                    "forced_20x_notional"
                    if force_maximum_leverage
                    else "risk_2pct_cap_20x"
                ),
                "trade_number": trade_number,
                "entry_time": trade.entry_time,
                "exit_time": trade.exit_time,
                "session_date": trade.session_date,
                "side": trade.side,
                "hierarchy_score": int(trade.hierarchy_score),
                "entry_price": float(trade.entry_price),
                "stop_fraction": stop_fraction,
                "required_leverage_for_2pct_risk": required_leverage,
                "effective_leverage": leverage,
                "leverage_cap_bound": bool(
                    not force_maximum_leverage and required_leverage > maximum_leverage
                ),
                "deployed_stop_risk_fraction": deployed_risk,
                "gross_account_return": gross_return,
                "cost_fraction": cost_fraction,
                "net_account_return": net_return,
                "equity_before": equity_before,
                "gross_pnl_dollars": equity_before * gross_return,
                "cost_dollars": cost_dollars,
                "net_pnl_dollars": net_pnl_dollars,
                "equity_after": equity,
                "cumulative_cost_dollars": total_cost_dollars,
                "drawdown": equity / peak - 1.0,
            }
        )
        if equity <= 0.0:
            break
    return pd.DataFrame(rows)


def summarize_path(path: pd.DataFrame, starting_equity: float) -> dict[str, Any]:
    if path.empty:
        raise ValueError("Cannot summarize an empty path")
    returns = path["net_account_return"].astype(float)
    wins = returns.loc[returns.gt(0.0)]
    losses = returns.loc[returns.lt(0.0)]
    loss_total = abs(float(losses.sum()))
    losing = returns.lt(0.0).astype(int)
    streak_group = losing.ne(losing.shift()).cumsum()
    maximum_losing_streak = int(
        losing.groupby(streak_group).sum().max() if len(losing) else 0
    )
    final_equity = float(path["equity_after"].iloc[-1])
    return {
        "variant": str(path["variant"].iloc[0]),
        "trades": int(len(path)),
        "start_equity": starting_equity,
        "final_equity": final_equity,
        "net_profit_dollars": final_equity - starting_equity,
        "cumulative_return": final_equity / starting_equity - 1.0,
        "maximum_drawdown": float(path["drawdown"].min()),
        "profit_factor": float(wins.sum()) / loss_total if loss_total else np.inf,
        "win_rate": float(returns.gt(0.0).mean()),
        "maximum_losing_streak": maximum_losing_streak,
        "average_effective_leverage": float(path["effective_leverage"].mean()),
        "maximum_effective_leverage": float(path["effective_leverage"].max()),
        "average_stop_risk_fraction": float(
            path["deployed_stop_risk_fraction"].mean()
        ),
        "maximum_stop_risk_fraction": float(
            path["deployed_stop_risk_fraction"].max()
        ),
        "leverage_cap_bound_trades": int(path["leverage_cap_bound"].sum()),
        "worst_realized_trade_return": float(returns.min()),
        "best_realized_trade_return": float(returns.max()),
        "total_modeled_cost_dollars": float(path["cost_dollars"].sum()),
    }


def period_summary(path: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for year, group in path.groupby(path["entry_time"].dt.year, sort=True):
        start = float(group["equity_before"].iloc[0])
        finish = float(group["equity_after"].iloc[-1])
        equity = np.r_[start, group["equity_after"].to_numpy(dtype=float)]
        peaks = np.maximum.accumulate(equity)
        rows.append(
            {
                "variant": str(group["variant"].iloc[0]),
                "year": int(year),
                "trades": int(len(group)),
                "start_equity": start,
                "final_equity": finish,
                "period_return": finish / start - 1.0,
                "period_maximum_drawdown": float((equity / peaks - 1.0).min()),
            }
        )
    return pd.DataFrame(rows)


def cost_sensitivity(
    trades: pd.DataFrame,
    *,
    starting_equity: float,
    risk_fraction: float,
    maximum_leverage: float,
) -> pd.DataFrame:
    rows = []
    for one_way_cost_bps in (0.0, 0.25, 0.50, 1.0, 1.5, 2.0, 3.0, 5.0):
        path = simulate_equity(
            trades,
            starting_equity=starting_equity,
            risk_fraction=risk_fraction,
            maximum_leverage=maximum_leverage,
            one_way_cost_bps=one_way_cost_bps,
        )
        summary = summarize_path(path, starting_equity)
        rows.append(
            {
                "one_way_cost_bps": one_way_cost_bps,
                "final_equity": summary["final_equity"],
                "cumulative_return": summary["cumulative_return"],
                "maximum_drawdown": summary["maximum_drawdown"],
                "profit_factor": summary["profit_factor"],
            }
        )
    return pd.DataFrame(rows)


def contract_feasibility(trades: pd.DataFrame, starting_equity: float) -> pd.DataFrame:
    prices = trades["entry_price"].astype(float)
    mnq_notional = 2.0 * prices
    return pd.DataFrame(
        [
            {
                "account_equity": starting_equity,
                "minimum_mnq_notional_in_sample": float(mnq_notional.min()),
                "median_mnq_notional_in_sample": float(mnq_notional.median()),
                "maximum_mnq_notional_in_sample": float(mnq_notional.max()),
                "minimum_equity_for_one_mnq_at_20x": float(mnq_notional.min() / 20.0),
                "median_equity_for_one_mnq_at_20x": float(mnq_notional.median() / 20.0),
                "maximum_fractional_mnq_at_100usd_and_20x": float(
                    starting_equity * 20.0 / mnq_notional.min()
                ),
                "cme_mnq_contract_multiplier": 2.0,
            }
        ]
    )


def plot_equity_curve(
    risk_path: pd.DataFrame, forced_path: pd.DataFrame, output_path: Path
) -> None:
    fig, (axis, drawdown_axis) = plt.subplots(
        2,
        1,
        figsize=(12, 7.5),
        sharex=True,
        gridspec_kw={"height_ratios": [3.0, 1.0]},
    )
    for path, label, color in (
        (risk_path, "2% stop risk, 20x cap", "#1769aa"),
        (forced_path, "forced 20x (not 2% risk)", "#cc3311"),
    ):
        times = [path["entry_time"].iloc[0] - pd.Timedelta(minutes=1), *path["exit_time"]]
        equities = [float(path["equity_before"].iloc[0]), *path["equity_after"]]
        axis.step(times, equities, where="post", label=label, color=color, linewidth=2.0)
    axis.axhline(100.0, color="#555555", linewidth=0.9, linestyle="--")
    axis.axvline(VALIDATION_START, color="#6f6f6f", linewidth=1.0, linestyle=":")
    axis.text(
        VALIDATION_START,
        axis.get_ylim()[1],
        " 2025 validation",
        va="top",
        color="#555555",
        fontsize=9,
    )
    axis.set_ylabel("Equity ($)")
    axis.set_title("NASDAQ hierarchical POC: $100 account scenario")
    axis.legend(loc="upper left")
    axis.grid(alpha=0.2)

    drawdown_axis.step(
        risk_path["exit_time"],
        100.0 * risk_path["drawdown"],
        where="post",
        color="#1769aa",
        linewidth=1.5,
    )
    drawdown_axis.axvline(
        VALIDATION_START, color="#6f6f6f", linewidth=1.0, linestyle=":"
    )
    drawdown_axis.fill_between(
        risk_path["exit_time"],
        100.0 * risk_path["drawdown"],
        0.0,
        step="post",
        color="#1769aa",
        alpha=0.15,
    )
    drawdown_axis.set_ylabel("DD (%)")
    drawdown_axis.set_xlabel("Trade exit date")
    drawdown_axis.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def build_small_account_scenario(
    project_root: str | Path | None = None,
    *,
    trades_path: str | Path = DEFAULT_TRADES,
    output_dir: str | Path = DEFAULT_OUTPUT,
    starting_equity: float = 100.0,
    risk_fraction: float = 0.02,
    maximum_leverage: float = 20.0,
    one_way_cost_bps: float = 0.50,
    minimum_score: int = 3,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)

    def resolved(value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else root / path

    output = resolved(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    trades = load_eligible_trades(resolved(trades_path), minimum_score)
    risk_path = simulate_equity(
        trades,
        starting_equity=starting_equity,
        risk_fraction=risk_fraction,
        maximum_leverage=maximum_leverage,
        one_way_cost_bps=one_way_cost_bps,
    )
    forced_path = simulate_equity(
        trades,
        starting_equity=starting_equity,
        risk_fraction=risk_fraction,
        maximum_leverage=maximum_leverage,
        one_way_cost_bps=one_way_cost_bps,
        force_maximum_leverage=True,
    )
    summaries = pd.DataFrame(
        [
            summarize_path(risk_path, starting_equity),
            summarize_path(forced_path, starting_equity),
        ]
    )
    periods = pd.concat(
        [period_summary(risk_path), period_summary(forced_path)], ignore_index=True
    )
    sensitivity = cost_sensitivity(
        trades,
        starting_equity=starting_equity,
        risk_fraction=risk_fraction,
        maximum_leverage=maximum_leverage,
    )
    feasibility = contract_feasibility(trades, starting_equity)

    audit = {
        "status": "PASS",
        "checks": {
            "only_hierarchy_score_ge_minimum": bool(
                trades["hierarchy_score"].ge(minimum_score).all()
            ),
            "chronological_non_overlapping_trades": bool(
                trades["entry_time"].shift(-1).iloc[:-1].ge(
                    trades["exit_time"].iloc[:-1]
                ).all()
            ),
            "risk_sized_leverage_never_above_cap": bool(
                risk_path["effective_leverage"].le(maximum_leverage).all()
            ),
            "risk_sized_stop_risk_never_above_target": bool(
                risk_path["deployed_stop_risk_fraction"].le(risk_fraction + 1e-12).all()
            ),
            "compounding_identity": bool(
                np.isclose(
                    risk_path["equity_after"].iloc[-1],
                    starting_equity
                    * np.prod(1.0 + risk_path["net_account_return"].to_numpy()),
                )
            ),
        },
    }
    if not all(audit["checks"].values()):
        audit["status"] = "FAIL"

    risk_path.to_csv(output / "equity_curve_2pct_risk_20x_cap.csv", index=False)
    forced_path.to_csv(output / "equity_curve_forced_20x.csv", index=False)
    summaries.to_csv(output / "summary.csv", index=False)
    periods.to_csv(output / "annual_breakdown.csv", index=False)
    sensitivity.to_csv(output / "cost_sensitivity.csv", index=False)
    feasibility.to_csv(output / "contract_feasibility.csv", index=False)
    plot_equity_curve(risk_path, forced_path, output / "equity_curve.png")
    (output / "methodology_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )

    primary = summaries.loc[summaries["variant"].eq("risk_2pct_cap_20x")].iloc[0]
    forced = summaries.loc[summaries["variant"].eq("forced_20x_notional")].iloc[0]
    report = f"""# NASDAQ hierarchical POC: $100 / 20x / 2% scenario

## Result

The internally consistent interpretation is **2% initial-stop risk with 20x as a leverage cap**. Starting at ${starting_equity:,.2f}, the modeled account finishes at **${primary['final_equity']:,.2f}**, a **{primary['cumulative_return']:.2%}** compounded return over {int(primary['trades'])} score-{minimum_score}-or-better trades. Maximum drawdown is **{primary['maximum_drawdown']:.2%}**. This uses the frozen {one_way_cost_bps:.2f}-bps-per-side cost assumption.

## Equity summary

{_markdown_table(summaries)}

## Annual path

{_markdown_table(periods)}

## Cost sensitivity for the valid 2%-risk interpretation

{_markdown_table(sensitivity)}

The edge is cost-sensitive: at 2 bps per side the final balance is approximately ${float(sensitivity.loc[sensitivity['one_way_cost_bps'].eq(2.0), 'final_equity'].iloc[0]):,.2f}; at 3 bps it is approximately ${float(sensitivity.loc[sensitivity['one_way_cost_bps'].eq(3.0), 'final_equity'].iloc[0]):,.2f}.

## Why forced 20x is different

Forcing 20x on every trade finishes at ${forced['final_equity']:,.2f}, but it is not a 2%-risk strategy. Its average planned stop exposure is {forced['average_stop_risk_fraction']:.2%}, and its maximum is {forced['maximum_stop_risk_fraction']:.2%}. The extra return is purchased with materially larger tail exposure.

## Execution feasibility

{_markdown_table(feasibility)}

CME MNQ has a $2-per-index-point multiplier. At the historical entry prices, one indivisible MNQ contract is far larger than the permitted $2,000 notional for a $100 account at 20x. Therefore this curve assumes a fractional CFD, spread-bet, or synthetic instrument. It is not executable as one CME MNQ contract.

## Assumptions and limits

- Trades are the frozen hierarchical ledger with score >= {minimum_score}; 25 occur in 2024 development and 21 in 2025 validation.
- Each trade compounds from current equity. Required leverage is `2% / stop distance`; actual leverage is capped at 20x.
- Costs are charged on entry and exit as {one_way_cost_bps:.2f} bps per side. Funding, fixed commissions, taxes, spread variation, partial-fill degradation, and liquidation penalties are excluded.
- The original 89-trade POC ledger was selected with visibility into both years, and its NASDAQ-like source has an unverified price grid. This is a scenario, not a forecast.
- The 2% setting overrides the research hierarchy's 0.10%-0.25% risk map and is eight times its maximum recommended trade risk.

Methodology audit: **{audit['status']}**.
"""
    (output / "report.md").write_text(report, encoding="utf-8")

    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "SCENARIO_ONLY_NOT_LIVE_DEPLOYABLE",
        "starting_equity": starting_equity,
        "risk_fraction": risk_fraction,
        "maximum_leverage": maximum_leverage,
        "one_way_cost_bps": one_way_cost_bps,
        "minimum_hierarchy_score": minimum_score,
        "audit": audit,
    }
    (output / "governance.json").write_text(
        json.dumps(governance, indent=2), encoding="utf-8"
    )
    return {
        "output": output,
        "summary": summaries,
        "annual": periods,
        "audit": audit,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--trades", type=Path, default=DEFAULT_TRADES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--starting-equity", type=float, default=100.0)
    parser.add_argument("--risk-fraction", type=float, default=0.02)
    parser.add_argument("--maximum-leverage", type=float, default=20.0)
    parser.add_argument("--one-way-cost-bps", type=float, default=0.50)
    parser.add_argument("--minimum-score", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_small_account_scenario(
        args.project_root,
        trades_path=args.trades,
        output_dir=args.output,
        starting_equity=args.starting_equity,
        risk_fraction=args.risk_fraction,
        maximum_leverage=args.maximum_leverage,
        one_way_cost_bps=args.one_way_cost_bps,
        minimum_score=args.minimum_score,
    )
    print(f"Report: {result['output'] / 'report.md'}")
    print(result["summary"].to_string(index=False))


if __name__ == "__main__":
    main()
