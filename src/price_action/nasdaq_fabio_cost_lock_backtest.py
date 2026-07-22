"""Cost-aware trailing-stop comparison for the NASDAQ Fabio Pine translation."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from price_action.btc_deepcharts_cost_lock_backtest import (
    _audit_cost_lock,
    _exit_diagnostics,
    run_cost_lock_broker_emulator,
)
from price_action.btc_deepcharts_proxy_backtest import (
    DeepChartsProxyConfig,
    proxy_account_path,
)
from price_action.data import resolve_project_root
from price_action.nasdaq_fabio_pine_v6_backtest import (
    DEFAULT_DATA,
    DEFAULT_SCHEDULE,
    PineFabioConfig,
    _audit_causality,
    _markdown_table,
    account_path,
    build_raw_signals,
    load_nasdaq_source,
    load_schedule,
    run_broker_emulator,
    summarize_path,
)


DEFAULT_OUTPUT = Path("outputs/nasdaq_fabio_cost_lock_backtest")
REFERENCE_ONE_WAY_COST_BPS = 0.50
LOCKED_NET_PROFIT_BPS = 0.25
COSTS_BPS = (0.0, 0.10, 0.20, 0.25, 0.30, 0.40, 0.50, 0.75, 1.0)
HOLDOUT_START = pd.Timestamp("2025-01-01", tz="UTC")


def _scope_metrics(path: pd.DataFrame) -> list[dict[str, Any]]:
    if path.empty:
        scopes = {"all": path, "development_2024": path, "holdout_2025": path}
    else:
        entry_time = pd.to_datetime(path["entry_time"], utc=True)
        scopes = {
            "all": path,
            "development_2024": path.loc[entry_time < HOLDOUT_START],
            "holdout_2025": path.loc[entry_time >= HOLDOUT_START],
        }
    return [{"scope": scope} | summarize_path(frame) for scope, frame in scopes.items()]


def _one_x_path(
    trades: pd.DataFrame,
    *,
    one_way_cost_bps: float,
    config: PineFabioConfig,
) -> pd.DataFrame:
    return account_path(
        trades,
        variant="script_realistic_cost",
        one_way_cost_bps=one_way_cost_bps,
        config=config,
    )


def _break_even_cost_bps(trades: pd.DataFrame, config: PineFabioConfig) -> float:
    if trades.empty:
        return np.nan
    if summarize_path(_one_x_path(trades, one_way_cost_bps=0.0, config=config))[
        "cumulative_net_return"
    ] <= 0.0:
        return 0.0
    lower, upper = 0.0, 5.0
    for _ in range(45):
        middle = (lower + upper) / 2.0
        metrics = summarize_path(
            _one_x_path(trades, one_way_cost_bps=middle, config=config)
        )
        if metrics["cumulative_net_return"] > 0.0:
            lower = middle
        else:
            upper = middle
    return float((lower + upper) / 2.0)


def _report(
    summary: pd.DataFrame,
    risk: pd.DataFrame,
    exits: pd.DataFrame,
    break_even: pd.DataFrame,
    audit: dict[str, Any],
    data_quality: dict[str, Any],
) -> str:
    reference = summary.loc[
        summary["one_way_cost_bps"].eq(REFERENCE_ONE_WAY_COST_BPS)
        & summary["scope"].isin(["all", "holdout_2025"]),
        [
            "exit_variant",
            "scope",
            "trades",
            "win_rate",
            "profit_factor",
            "cumulative_net_return",
            "maximum_drawdown",
        ],
    ]
    cost_curve = summary.loc[
        summary["scope"].eq("all"),
        [
            "exit_variant",
            "one_way_cost_bps",
            "trades",
            "profit_factor",
            "cumulative_net_return",
            "maximum_drawdown",
        ],
    ]
    risk_view = risk.loc[
        risk["scope"].isin(["all", "holdout_2025"]),
        [
            "exit_variant",
            "sizing_variant",
            "scope",
            "trades",
            "profit_factor",
            "cumulative_net_return",
            "maximum_drawdown",
            "average_effective_leverage",
        ],
    ]

    def result(exit_variant: str, scope: str) -> pd.Series:
        return summary.loc[
            (summary["exit_variant"] == exit_variant)
            & (summary["scope"] == scope)
            & summary["one_way_cost_bps"].eq(REFERENCE_ONE_WAY_COST_BPS)
        ].iloc[0]

    baseline_all = result("atr_trailing_baseline", "all")
    lock_all = result("cost_aware_profit_lock", "all")
    baseline_holdout = result("atr_trailing_baseline", "holdout_2025")
    lock_holdout = result("cost_aware_profit_lock", "holdout_2025")
    lock_break_even = float(
        break_even.loc[
            break_even["exit_variant"] == "cost_aware_profit_lock",
            "break_even_one_way_cost_bps",
        ].iloc[0]
    )
    baseline_exits = exits.loc[exits["exit_variant"] == "atr_trailing_baseline"].iloc[0]
    lock_exits = exits.loc[exits["exit_variant"] == "cost_aware_profit_lock"].iloc[0]
    return f"""# NASDAQ one-minute cost-aware trailing-stop comparison

## Rule and decision

The translated Pine baseline activates a 0.5-ATR trail after a 1.5-ATR favorable move. The alternative assumes {REFERENCE_ONE_WAY_COST_BPS:.2f} bps per side, places its locked floor beyond the {2 * REFERENCE_ONE_WAY_COST_BPS:.2f}-bp round trip plus a {LOCKED_NET_PROFIT_BPS:.2f}-bp net buffer, and activates when price can support that floor plus the 0.5-ATR offset. The stop then ratchets with favorable extremes. Signal selection, static stop, 2R target, three-loss session cutoff, and next-open entry are unchanged.

At the design cost, full-history return changes from {baseline_all['cumulative_net_return']:.1%} to {lock_all['cumulative_net_return']:.1%}; holdout changes from {baseline_holdout['cumulative_net_return']:.1%} to {lock_holdout['cumulative_net_return']:.1%}. Cost-lock PF is {lock_all['profit_factor']:.3f} overall and {lock_holdout['profit_factor']:.3f} in holdout. Its break-even cost is {lock_break_even:.3f} bps per side.

**Decision: reject the earlier cost lock for the assumed 0.50-bps execution.** The original trail already leaves every observed trailing exit above costs and the requested buffer. Earlier activation raises completed trades from {int(baseline_all['trades'])} to {int(lock_all['trades'])}, while median net trailing gain falls from {baseline_exits['median_trailing_net_return']:.3%} to {lock_exits['median_trailing_net_return']:.3%}. The added turnover converts the small positive baseline holdout into a loss. The earlier lock is profitable in the full sample only below its {lock_break_even:.3f}-bps break-even estimate, which is not independent validation.

## Results at 0.50 bps per side

{_markdown_table(reference)}

## Exit behavior

{_markdown_table(exits)}

## Cost curve

{_markdown_table(cost_curve)}

## Break-even cost

{_markdown_table(break_even)}

## 0.25% stop-risk sizing, 3x cap

{_markdown_table(risk_view)}

## Audit and limits

- Underlying signal audit: **{audit['signal_engine']['status']}**.
- Cost-lock audit: **{audit['cost_lock']['status']}**.
- A normal floor fill covers modeled costs and the buffer; a gap may not.
- Intrabar order still uses the deterministic one-minute OHLC path because tick data are absent.
- Instrument identity remains unverified and {data_quality['close_not_on_nq_quarter_tick_share']:.1%} of closes are off the CME NQ quarter-point grid.
- A bps cost model is retained for comparability. Real NQ/MNQ validation requires contract-aware commissions, tick slippage, and a verified futures feed.

Research only.
"""


def build_nasdaq_fabio_cost_lock_backtest(
    project_root: str | Path | None = None,
    *,
    data_path: str | Path = DEFAULT_DATA,
    schedule_path: str | Path = DEFAULT_SCHEDULE,
    output_dir: str | Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)

    def resolved(value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else root / path

    data_file = resolved(data_path)
    schedule_file = resolved(schedule_path)
    output = resolved(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    bars, data_quality = load_nasdaq_source(data_file)
    schedule = load_schedule(schedule_file)
    config = PineFabioConfig(realistic_one_way_cost_bps=REFERENCE_ONE_WAY_COST_BPS)
    indicated, signals = build_raw_signals(bars, schedule, config)
    baseline, baseline_execution = run_broker_emulator(indicated, signals, config)
    cost_lock, cost_lock_execution = run_cost_lock_broker_emulator(
        indicated,
        signals,
        config,
        one_way_cost_bps=REFERENCE_ONE_WAY_COST_BPS,
        locked_net_profit_bps=LOCKED_NET_PROFIT_BPS,
    )
    trade_sets = {
        "atr_trailing_baseline": baseline,
        "cost_aware_profit_lock": cost_lock,
    }

    summary_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []
    exit_rows: list[dict[str, Any]] = []
    break_even_rows: list[dict[str, Any]] = []
    risk_config = DeepChartsProxyConfig(
        risk_target_fraction=0.0025,
        risk_maximum_leverage=3.0,
        risk_maximum_daily_losses=2,
        risk_maximum_daily_return_loss=0.0075,
    )
    for name, trades in trade_sets.items():
        trades.to_csv(output / f"trades_{name}.csv", index=False)
        exit_rows.append(
            _exit_diagnostics(
                trades,
                exit_variant=name,
                one_way_cost_bps=REFERENCE_ONE_WAY_COST_BPS,
                locked_net_profit_bps=LOCKED_NET_PROFIT_BPS,
            )
        )
        for cost in COSTS_BPS:
            path = _one_x_path(trades, one_way_cost_bps=cost, config=config)
            for metrics in _scope_metrics(path):
                summary_rows.append(
                    {"exit_variant": name, "one_way_cost_bps": cost} | metrics
                )
        for sizing in ("risk_025pct_cap3x", "risk_025pct_cap3x_daily_halt_proxy"):
            path, diagnostics = proxy_account_path(
                trades,
                sizing_variant=sizing,
                one_way_cost_bps=REFERENCE_ONE_WAY_COST_BPS,
                config=risk_config,
            )
            for metrics in _scope_metrics(path):
                risk_rows.append(
                    {"exit_variant": name, "sizing_variant": sizing, **diagnostics} | metrics
                )
        break_even_rows.append(
            {
                "exit_variant": name,
                "break_even_one_way_cost_bps": _break_even_cost_bps(trades, config),
            }
        )

    summary = pd.DataFrame(summary_rows)
    risk = pd.DataFrame(risk_rows)
    exits = pd.DataFrame(exit_rows)
    break_even = pd.DataFrame(break_even_rows)
    signal_audit = _audit_causality(
        bars, schedule, indicated, signals, baseline, config
    )
    cost_lock_audit = _audit_cost_lock(
        cost_lock,
        one_way_cost_bps=REFERENCE_ONE_WAY_COST_BPS,
        locked_net_profit_bps=LOCKED_NET_PROFIT_BPS,
    )
    audit = {"signal_engine": signal_audit, "cost_lock": cost_lock_audit}
    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "RESEARCH_ONLY_LIVE_DEPLOYMENT_BLOCKED",
        "data_source": str(data_file),
        "schedule_source": str(schedule_file),
        "data_quality": data_quality,
        "pine_config": asdict(config),
        "reference_one_way_cost_bps": REFERENCE_ONE_WAY_COST_BPS,
        "locked_net_profit_bps": LOCKED_NET_PROFIT_BPS,
        "costs_bps_per_side": COSTS_BPS,
        "risk_config": asdict(risk_config),
        "execution_diagnostics": {
            "atr_trailing_baseline": baseline_execution,
            "cost_aware_profit_lock": cost_lock_execution,
        },
        "audit": audit,
    }
    signals.to_csv(output / "signals.csv", index=False)
    summary.to_csv(output / "summary.csv", index=False)
    risk.to_csv(output / "risk_comparison.csv", index=False)
    exits.to_csv(output / "exit_diagnostics.csv", index=False)
    break_even.to_csv(output / "break_even_costs.csv", index=False)
    (output / "causality_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    (output / "governance.json").write_text(json.dumps(governance, indent=2), encoding="utf-8")
    report = _report(summary, risk, exits, break_even, audit, data_quality)
    report_path = output / "report.md"
    report_path.write_text(report, encoding="utf-8")
    return {
        "report_path": report_path,
        "summary": summary,
        "risk": risk,
        "exits": exits,
        "break_even": break_even,
        "audit": audit,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root")
    parser.add_argument("--data-path", default=str(DEFAULT_DATA))
    parser.add_argument("--schedule-path", default=str(DEFAULT_SCHEDULE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_nasdaq_fabio_cost_lock_backtest(
        project_root=args.project_root,
        data_path=args.data_path,
        schedule_path=args.schedule_path,
        output_dir=args.output_dir,
    )
    print(f"Report: {result['report_path']}")
    print(
        result["summary"].loc[
            result["summary"]["one_way_cost_bps"].eq(REFERENCE_ONE_WAY_COST_BPS)
            & result["summary"]["scope"].isin(["all", "holdout_2025"])
        ].to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
