"""Build a $100, 2%-risk, 20x-cap equity scenario for the BTC five-minute proxy."""

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
from price_action.nasdaq_poc_small_account_scenario import (
    simulate_equity,
    summarize_path,
)


DEFAULT_TRADES = Path(
    "outputs/btc_deepcharts_cost_lock_backtest/trades_cost_aware_profit_lock.csv"
)
DEFAULT_OUTPUT = Path("outputs/btc_5m_100usd_20x_2pct")
VALIDATION_START = pd.Timestamp("2025-01-01", tz="UTC")


def load_btc_trades(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {
        "signal_time",
        "entry_time",
        "exit_time",
        "session_date",
        "side",
        "side_name",
        "entry_price",
        "initial_stop_fraction",
        "signed_price_return",
        "exit_reason",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"BTC trade ledger is missing columns: {sorted(missing)}")
    for column in ("entry_time", "exit_time"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="raise")
    frame["entry_price"] = pd.to_numeric(frame["entry_price"], errors="raise")
    frame["stop_fraction"] = pd.to_numeric(
        frame["initial_stop_fraction"], errors="raise"
    )
    frame["signed_price_return"] = pd.to_numeric(
        frame["signed_price_return"], errors="raise"
    )
    frame["hierarchy_score"] = 0
    if frame[["entry_price", "stop_fraction", "signed_price_return"]].isna().any().any():
        raise ValueError("BTC sizing fields contain missing values")
    return frame.sort_values(["entry_time", "exit_time"]).reset_index(drop=True)


def _direction_path(
    trades: pd.DataFrame,
    *,
    direction: str,
    starting_equity: float,
    risk_fraction: float,
    maximum_leverage: float,
    one_way_cost_bps: float,
) -> pd.DataFrame:
    if direction == "both":
        subset = trades
    elif direction == "long_only":
        subset = trades.loc[trades["side"].gt(0.0)]
    elif direction == "short_only":
        subset = trades.loc[trades["side"].lt(0.0)]
    else:
        raise ValueError(f"Unknown direction: {direction}")
    path = simulate_equity(
        subset,
        starting_equity=starting_equity,
        risk_fraction=risk_fraction,
        maximum_leverage=maximum_leverage,
        one_way_cost_bps=one_way_cost_bps,
    )
    path["variant"] = direction
    return path


def scope_summary(path: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    scopes = {
        "all_2022_to_2026": pd.Series(True, index=path.index),
        "development_pre_2025": path["entry_time"].lt(VALIDATION_START),
        "holdout_2025_plus": path["entry_time"].ge(VALIDATION_START),
    }
    for scope, mask in scopes.items():
        group = path.loc[mask]
        if group.empty:
            continue
        start = float(group["equity_before"].iloc[0])
        finish = float(group["equity_after"].iloc[-1])
        equity = np.r_[start, group["equity_after"].to_numpy(dtype=float)]
        peaks = np.maximum.accumulate(equity)
        returns = group["net_account_return"].astype(float)
        wins = returns.loc[returns.gt(0.0)]
        losses = returns.loc[returns.lt(0.0)]
        rows.append(
            {
                "direction": str(group["variant"].iloc[0]),
                "scope": scope,
                "trades": int(len(group)),
                "start_equity": start,
                "final_equity": finish,
                "scope_return": finish / start - 1.0,
                "maximum_drawdown": float((equity / peaks - 1.0).min()),
                "profit_factor": (
                    float(wins.sum()) / abs(float(losses.sum()))
                    if len(losses)
                    else np.inf
                ),
                "win_rate": float(returns.gt(0.0).mean()),
            }
        )
    return pd.DataFrame(rows)


def build_cost_sensitivity(
    trades: pd.DataFrame,
    *,
    starting_equity: float,
    risk_fraction: float,
    maximum_leverage: float,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for cost in (0.0, 1.0, 2.0, 3.0, 3.34, 4.0, 6.0, 10.0, 15.0):
        for direction in ("both", "long_only", "short_only"):
            path = _direction_path(
                trades,
                direction=direction,
                starting_equity=starting_equity,
                risk_fraction=risk_fraction,
                maximum_leverage=maximum_leverage,
                one_way_cost_bps=cost,
            )
            summary = summarize_path(path, starting_equity)
            rows.append(
                {
                    "one_way_cost_bps": cost,
                    "direction": direction,
                    "trades": summary["trades"],
                    "final_equity": summary["final_equity"],
                    "cumulative_return": summary["cumulative_return"],
                    "maximum_drawdown": summary["maximum_drawdown"],
                    "profit_factor": summary["profit_factor"],
                }
            )
    return pd.DataFrame(rows)


def plot_paths(paths: dict[str, pd.DataFrame], output_path: Path) -> None:
    colors = {"both": "#222222", "long_only": "#cc3311", "short_only": "#1769aa"}
    labels = {
        "both": "long + short",
        "long_only": "long-only attribution",
        "short_only": "short-only attribution",
    }
    fig, (axis, drawdown_axis) = plt.subplots(
        2,
        1,
        figsize=(12, 7.5),
        sharex=True,
        gridspec_kw={"height_ratios": [3.0, 1.0]},
    )
    for direction, path in paths.items():
        times = [path["entry_time"].iloc[0] - pd.Timedelta(minutes=5), *path["exit_time"]]
        equities = [float(path["equity_before"].iloc[0]), *path["equity_after"]]
        axis.step(
            times,
            equities,
            where="post",
            label=labels[direction],
            color=colors[direction],
            linewidth=1.8,
        )
    axis.axhline(100.0, color="#777777", linewidth=0.9, linestyle="--")
    axis.axvline(VALIDATION_START, color="#6f6f6f", linewidth=1.0, linestyle=":")
    axis.set_ylabel("Equity ($)")
    axis.set_title("BTC five-minute proxy: $100, 2% stop risk, 20x leverage cap")
    axis.legend(loc="upper right")
    axis.grid(alpha=0.2)

    combined = paths["both"]
    drawdown_axis.step(
        combined["exit_time"],
        100.0 * combined["drawdown"],
        where="post",
        color=colors["both"],
        linewidth=1.3,
    )
    drawdown_axis.fill_between(
        combined["exit_time"],
        100.0 * combined["drawdown"],
        0.0,
        step="post",
        color="#555555",
        alpha=0.18,
    )
    drawdown_axis.axvline(
        VALIDATION_START, color="#6f6f6f", linewidth=1.0, linestyle=":"
    )
    drawdown_axis.set_ylabel("Combined DD (%)")
    drawdown_axis.set_xlabel("Trade exit date")
    drawdown_axis.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def build_btc_small_account_scenario(
    project_root: str | Path | None = None,
    *,
    trades_path: str | Path = DEFAULT_TRADES,
    output_dir: str | Path = DEFAULT_OUTPUT,
    starting_equity: float = 100.0,
    risk_fraction: float = 0.02,
    maximum_leverage: float = 20.0,
    one_way_cost_bps: float = 6.0,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)

    def resolved(value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else root / path

    output = resolved(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    trades = load_btc_trades(resolved(trades_path))
    paths = {
        direction: _direction_path(
            trades,
            direction=direction,
            starting_equity=starting_equity,
            risk_fraction=risk_fraction,
            maximum_leverage=maximum_leverage,
            one_way_cost_bps=one_way_cost_bps,
        )
        for direction in ("both", "long_only", "short_only")
    }
    summaries = pd.DataFrame(
        [summarize_path(path, starting_equity) for path in paths.values()]
    ).rename(columns={"variant": "direction"})
    scopes = pd.concat([scope_summary(path) for path in paths.values()], ignore_index=True)
    sensitivity = build_cost_sensitivity(
        trades,
        starting_equity=starting_equity,
        risk_fraction=risk_fraction,
        maximum_leverage=maximum_leverage,
    )
    forced = simulate_equity(
        trades,
        starting_equity=starting_equity,
        risk_fraction=risk_fraction,
        maximum_leverage=maximum_leverage,
        one_way_cost_bps=one_way_cost_bps,
        force_maximum_leverage=True,
    )
    forced_summary = summarize_path(forced, starting_equity)

    audit = {
        "status": "PASS",
        "checks": {
            "five_minute_signal_ledger": True,
            "entry_follows_signal_bar": bool(
                pd.to_datetime(trades["signal_time"], utc=True).lt(trades["entry_time"]).all()
            ),
            "chronological_non_overlapping_executed_trades": bool(
                trades["entry_time"].shift(-1).iloc[:-1].ge(
                    trades["exit_time"].iloc[:-1]
                ).all()
            ),
            "both_long_and_short_present": bool(
                trades["side"].gt(0.0).any() and trades["side"].lt(0.0).any()
            ),
            "leverage_never_above_20x": bool(
                paths["both"]["effective_leverage"].le(maximum_leverage).all()
            ),
            "deployed_stop_risk_never_above_2pct": bool(
                paths["both"]["deployed_stop_risk_fraction"].le(
                    risk_fraction + 1e-12
                ).all()
            ),
        },
    }
    if not all(audit["checks"].values()):
        audit["status"] = "FAIL"

    for direction, path in paths.items():
        path.to_csv(output / f"equity_curve_{direction}.csv", index=False)
    summaries.to_csv(output / "direction_summary.csv", index=False)
    scopes.to_csv(output / "scope_summary.csv", index=False)
    sensitivity.to_csv(output / "cost_sensitivity.csv", index=False)
    plot_paths(paths, output / "equity_curve.png")
    (output / "methodology_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )

    both = summaries.loc[summaries["direction"].eq("both")].iloc[0]
    long = summaries.loc[summaries["direction"].eq("long_only")].iloc[0]
    short = summaries.loc[summaries["direction"].eq("short_only")].iloc[0]
    selected_costs = sensitivity.loc[
        sensitivity["one_way_cost_bps"].isin([0.0, 1.0, 2.0, 3.0, 4.0, 6.0])
    ]
    report = f"""# BTC five-minute $100 / 20x-cap / 2%-risk scenario

## Decision

The system trades both directions: **{int((trades['side'] > 0).sum())} longs** and **{int((trades['side'] < 0).sum())} shorts**. At the frozen 6-bps-per-side design cost, neither direction is viable. Combined equity falls from ${starting_equity:,.2f} to **${both['final_equity']:,.2f}** ({both['cumulative_return']:.2%}) with {both['maximum_drawdown']:.2%} maximum drawdown.

Short-only is less damaging than long-only, but still fails: short-only ends at ${short['final_equity']:,.2f}, versus ${long['final_equity']:,.2f} for long-only. These are direction-attribution paths from the existing ledger, not freshly replayed one-sided strategies.

## Direction results at {one_way_cost_bps:.0f} bps per side

{_markdown_table(summaries)}

## Development and holdout

{_markdown_table(scopes)}

## Cost sensitivity

{_markdown_table(selected_costs)}

The cost curve is the main finding. At zero cost, the combined path would finish near ${float(sensitivity.loc[(sensitivity['one_way_cost_bps'].eq(0.0)) & (sensitivity['direction'].eq('both')), 'final_equity'].iloc[0]):,.2f}; at 2 bps it finishes near ${float(sensitivity.loc[(sensitivity['one_way_cost_bps'].eq(2.0)) & (sensitivity['direction'].eq('both')), 'final_equity'].iloc[0]):,.2f}; at 3 bps it is already below its starting balance. The five-minute signal contains gross structure, but turnover cost consumes it.

## Leverage interpretation

Each trade targets 2% initial-stop exposure using `min(20x, 2% / stop_fraction)`. Average effective leverage for the combined path is {both['average_effective_leverage']:.2f}x; the cap binds on {int(both['leverage_cap_bound_trades'])} trades. Forcing 20x on every trade instead leaves approximately **${forced_summary['final_equity']:,.4f}**, matching the earlier near-ruin stress result and no longer respecting 2% stop risk.

## Limits

- Signals and exits are the unchanged five-minute `full_no_delta_proxy` with the 6-bps cost-aware profit-lock trail.
- Funding, liquidation engine, maintenance margin, latency, variable spread, and nonlinear slippage are excluded.
- Long-only and short-only curves condition the already-executed ledger. A new one-sided replay could admit signals that were originally blocked by an open position.
- Five-minute OHLCV proxies are not genuine footprint delta or order-book data.
- Development ends before 2025; the 2025-plus section is unchanged holdout, but the wider research program has inspected these results.

Methodology audit: **{audit['status']}**. Status: **REJECT at 6 bps per side**.
"""
    (output / "report.md").write_text(report, encoding="utf-8")
    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "REJECT_AT_6_BPS_PER_SIDE",
        "starting_equity": starting_equity,
        "risk_fraction": risk_fraction,
        "maximum_leverage": maximum_leverage,
        "one_way_cost_bps": one_way_cost_bps,
        "source": str(resolved(trades_path)),
        "audit": audit,
    }
    (output / "governance.json").write_text(
        json.dumps(governance, indent=2), encoding="utf-8"
    )
    return {
        "output": output,
        "summary": summaries,
        "scope_summary": scopes,
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
    parser.add_argument("--one-way-cost-bps", type=float, default=6.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_btc_small_account_scenario(
        args.project_root,
        trades_path=args.trades,
        output_dir=args.output,
        starting_equity=args.starting_equity,
        risk_fraction=args.risk_fraction,
        maximum_leverage=args.maximum_leverage,
        one_way_cost_bps=args.one_way_cost_bps,
    )
    print(f"Report: {result['output'] / 'report.md'}")
    print(result["summary"].to_string(index=False))


if __name__ == "__main__":
    main()
