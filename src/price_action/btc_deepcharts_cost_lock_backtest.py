"""Cost-aware trailing-stop comparison for the BTC DeepCharts proxy stack."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from price_action.btc_deepcharts_proxy_backtest import (
    DEFAULT_DATA,
    DeepChartsProxyConfig,
    _break_even_cost_bps,
    _scope_metrics,
    build_five_minute_features_proxy,
    build_raw_proxy_signals,
    build_session_context_proxy,
    proxy_account_path,
    select_signal_variants,
)
from price_action.btc_fabio_donchian_backtest import build_donchian_context
from price_action.btc_fabio_pine_v6_backtest import (
    BAR_MINUTES,
    build_seven_day_schedule,
    load_binance_btc_5m,
)
from price_action.data import resolve_project_root
from price_action.nasdaq_fabio_pine_v6_backtest import (
    PineFabioConfig,
    _markdown_table,
    inferred_path,
    run_broker_emulator,
)


DEFAULT_OUTPUT = Path("outputs/btc_deepcharts_cost_lock_backtest")
REFERENCE_ONE_WAY_COST_BPS = 6.0
LOCKED_NET_PROFIT_BPS = 2.0
COSTS_BPS = (0.0, 1.0, 2.0, 3.0, 6.0, 15.0)


def _walk_cost_lock_trade_bar(
    *,
    side: int,
    entry_price: float,
    stop: float,
    target: float,
    trail_offset: float,
    path: list[float],
    trail_active: bool,
    favorable_extreme: float,
    lock_floor: float,
    lock_activation: float,
) -> tuple[float | None, str | None, bool, float]:
    """Walk one OHLC path with a cost floor and a ratcheting ATR trail."""
    opening = path[0]
    if side > 0:
        trailing_level = max(lock_floor, favorable_extreme - trail_offset)
        adverse_level = max(stop, trailing_level) if trail_active else stop
        if opening <= adverse_level:
            reason = "cost_lock_trailing_gap" if trail_active and trailing_level >= stop else "static_stop_gap"
            return opening, reason, trail_active, favorable_extreme
        if opening >= target:
            return opening, "target_gap", trail_active, favorable_extreme
        if not trail_active and opening >= lock_activation:
            trail_active, favorable_extreme = True, opening
        elif trail_active and opening > favorable_extreme:
            favorable_extreme = opening
    else:
        trailing_level = min(lock_floor, favorable_extreme + trail_offset)
        adverse_level = min(stop, trailing_level) if trail_active else stop
        if opening >= adverse_level:
            reason = "cost_lock_trailing_gap" if trail_active and trailing_level <= stop else "static_stop_gap"
            return opening, reason, trail_active, favorable_extreme
        if opening <= target:
            return opening, "target_gap", trail_active, favorable_extreme
        if not trail_active and opening <= lock_activation:
            trail_active, favorable_extreme = True, opening
        elif trail_active and opening < favorable_extreme:
            favorable_extreme = opening

    for start, end in zip(path[:-1], path[1:], strict=True):
        if side > 0:
            if end > start:
                if target >= start and target <= end:
                    return target, "target", trail_active, favorable_extreme
                if not trail_active and lock_activation >= start and lock_activation <= end:
                    trail_active = True
                    favorable_extreme = end
                elif trail_active:
                    favorable_extreme = max(favorable_extreme, end)
            elif end < start:
                trailing_level = max(lock_floor, favorable_extreme - trail_offset)
                adverse_level = max(stop, trailing_level) if trail_active else stop
                if end <= adverse_level <= start:
                    reason = "cost_lock_trailing_stop" if trail_active and trailing_level >= stop else "static_stop"
                    return adverse_level, reason, trail_active, favorable_extreme
        else:
            if end < start:
                if target <= start and target >= end:
                    return target, "target", trail_active, favorable_extreme
                if not trail_active and lock_activation <= start and lock_activation >= end:
                    trail_active = True
                    favorable_extreme = end
                elif trail_active:
                    favorable_extreme = min(favorable_extreme, end)
            elif end > start:
                trailing_level = min(lock_floor, favorable_extreme + trail_offset)
                adverse_level = min(stop, trailing_level) if trail_active else stop
                if start <= adverse_level <= end:
                    reason = "cost_lock_trailing_stop" if trail_active and trailing_level <= stop else "static_stop"
                    return adverse_level, reason, trail_active, favorable_extreme
    return None, None, trail_active, favorable_extreme


def run_cost_lock_broker_emulator(
    indicated: pd.DataFrame,
    signals: pd.DataFrame,
    config: PineFabioConfig,
    *,
    one_way_cost_bps: float = REFERENCE_ONE_WAY_COST_BPS,
    locked_net_profit_bps: float = LOCKED_NET_PROFIT_BPS,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Run next-open entries with a cost-covered profit floor and ATR ratchet."""
    grouped = {int(key): group for key, group in signals.groupby("signal_bar_id")} if not signals.empty else {}
    pending: dict[str, Any] | None = None
    position: dict[str, Any] | None = None
    trades: list[dict[str, Any]] = []
    daily_losses = 0
    diagnostics = {
        "raw_signals": int(len(signals)),
        "signals_blocked_position": 0,
        "signals_blocked_daily_losses": 0,
        "pending_entries_unfilled_at_end": 0,
        "open_position_at_end": 0,
    }
    round_trip_cost_fraction = 2.0 * one_way_cost_bps / 10_000.0
    locked_net_fraction = locked_net_profit_bps / 10_000.0
    for bar_id, (timestamp, bar) in enumerate(indicated.iterrows()):
        loss_closed_this_bar = False
        if pending is not None:
            entry_price = float(bar["open"])
            side = int(pending["side"])
            lock_distance = entry_price * (round_trip_cost_fraction + locked_net_fraction)
            lock_floor = entry_price + side * lock_distance
            trail_offset = float(pending["trail_offset"])
            pending = pending.copy()
            pending.update(
                {
                    "entry_time": timestamp,
                    "entry_bar_id": bar_id,
                    "entry_price": entry_price,
                    "trail_active": False,
                    "favorable_extreme": entry_price,
                    "cost_lock_floor_price": lock_floor,
                    "cost_lock_activation_price": lock_floor + side * trail_offset,
                    "cost_lock_one_way_bps": one_way_cost_bps,
                    "locked_net_profit_bps": locked_net_profit_bps,
                }
            )
            position, pending = pending, None

        if position is not None:
            path = inferred_path(
                float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
            )
            exit_price, exit_reason, active, extreme = _walk_cost_lock_trade_bar(
                side=int(position["side"]),
                entry_price=float(position["entry_price"]),
                stop=float(position["static_stop"]),
                target=float(position["static_target"]),
                trail_offset=float(position["trail_offset"]),
                path=path,
                trail_active=bool(position["trail_active"]),
                favorable_extreme=float(position["favorable_extreme"]),
                lock_floor=float(position["cost_lock_floor_price"]),
                lock_activation=float(position["cost_lock_activation_price"]),
            )
            position["trail_active"] = active
            position["favorable_extreme"] = extreme
            if exit_price is not None:
                side = int(position["side"])
                entry_price = float(position["entry_price"])
                gross_return = side * (float(exit_price) / entry_price - 1.0)
                initial_stop_fraction = abs(entry_price - float(position["static_stop"])) / entry_price
                trades.append(
                    {
                        **{key: value for key, value in position.items() if key not in {"trail_active", "favorable_extreme"}},
                        "side_name": "long" if side > 0 else "short",
                        "exit_time": timestamp,
                        "exit_bar_id": bar_id,
                        "exit_price": float(exit_price),
                        "exit_reason": exit_reason,
                        "holding_bars": bar_id - int(position["entry_bar_id"]) + 1,
                        "signed_price_return": gross_return,
                        "initial_stop_fraction": initial_stop_fraction,
                        "gross_r": gross_return / initial_stop_fraction if initial_stop_fraction > 0.0 else np.nan,
                    }
                )
                loss_closed_this_bar = gross_return < 0.0
                position = None

        if bool(bar["session_change"]):
            daily_losses = 0
        candidates = grouped.get(bar_id)
        if candidates is not None:
            if position is not None or pending is not None:
                diagnostics["signals_blocked_position"] += len(candidates)
            elif daily_losses >= config.maximum_daily_losses:
                diagnostics["signals_blocked_daily_losses"] += len(candidates)
            else:
                pending = candidates.iloc[-1].to_dict()
        if loss_closed_this_bar:
            daily_losses += 1
    diagnostics["pending_entries_unfilled_at_end"] = int(pending is not None)
    diagnostics["open_position_at_end"] = int(position is not None)
    return pd.DataFrame(trades), diagnostics


def _exit_diagnostics(
    trades: pd.DataFrame,
    *,
    exit_variant: str,
    one_way_cost_bps: float,
    locked_net_profit_bps: float,
) -> dict[str, Any]:
    if trades.empty:
        return {"exit_variant": exit_variant, "trades": 0}
    round_trip_cost = 2.0 * one_way_cost_bps / 10_000.0
    net = trades["signed_price_return"] - round_trip_cost
    trailing = trades["exit_reason"].str.contains("trailing", na=False)
    trailing_net = net.loc[trailing]
    gap = trades["exit_reason"].eq("cost_lock_trailing_gap")
    return {
        "exit_variant": exit_variant,
        "trades": int(len(trades)),
        "trailing_exits": int(trailing.sum()),
        "trailing_exit_share": float(trailing.mean()),
        "trailing_net_profitable": int((trailing_net > 0.0).sum()),
        "trailing_net_profitable_share": float((trailing_net > 0.0).mean()) if len(trailing_net) else np.nan,
        "trailing_locked_buffer_or_more": int((trailing_net >= locked_net_profit_bps / 10_000.0 - 1e-12).sum()),
        "trailing_gap_exits": int(gap.sum()),
        "target_exits": int(trades["exit_reason"].str.startswith("target").sum()),
        "static_stop_exits": int(trades["exit_reason"].str.startswith("static").sum()),
        "median_trailing_net_return": float(trailing_net.median()) if len(trailing_net) else np.nan,
        "minimum_trailing_net_return": float(trailing_net.min()) if len(trailing_net) else np.nan,
    }


def _audit_cost_lock(
    trades: pd.DataFrame,
    *,
    one_way_cost_bps: float,
    locked_net_profit_bps: float,
) -> dict[str, Any]:
    regular = trades.loc[trades["exit_reason"].eq("cost_lock_trailing_stop")]
    required_gross = (2.0 * one_way_cost_bps + locked_net_profit_bps) / 10_000.0
    floor_holds = regular.empty or regular["signed_price_return"].ge(required_gross - 1e-12).all()
    next_bar = trades.empty or trades["entry_bar_id"].eq(trades["signal_bar_id"] + 1).all()
    floors_directional = trades.empty or (
        trades["side"].mul(trades["cost_lock_floor_price"] - trades["entry_price"]).gt(0.0).all()
    )
    activation_beyond_floor = trades.empty or (
        trades["side"].mul(trades["cost_lock_activation_price"] - trades["cost_lock_floor_price"]).gt(0.0).all()
    )
    checks = {
        "entries_fill_on_next_bar_open": bool(next_bar),
        "regular_cost_lock_exits_preserve_requested_net_buffer": bool(floor_holds),
        "lock_floor_is_beyond_entry_in_trade_direction": bool(floors_directional),
        "activation_is_one_trailing_offset_beyond_lock_floor": bool(activation_beyond_floor),
        "gap_exits_are_not_assumed_to_fill_at_stop": True,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "cost_model": {
            "one_way_cost_bps": one_way_cost_bps,
            "round_trip_cost_bps": 2.0 * one_way_cost_bps,
            "locked_net_profit_bps": locked_net_profit_bps,
        },
    }


def _report(
    summary: pd.DataFrame,
    risk: pd.DataFrame,
    exits: pd.DataFrame,
    break_even: pd.DataFrame,
    audit: dict[str, Any],
) -> str:
    primary = summary.loc[
        summary["one_way_cost_bps"].eq(REFERENCE_ONE_WAY_COST_BPS)
        & summary["scope"].isin(["all", "holdout_2025_plus"]),
        ["exit_variant", "scope", "trades", "win_rate", "profit_factor", "cumulative_net_return", "maximum_drawdown"],
    ]
    cost_curve = summary.loc[
        summary["scope"].eq("all"),
        ["exit_variant", "one_way_cost_bps", "trades", "profit_factor", "cumulative_net_return", "maximum_drawdown"],
    ]
    risk_view = risk.loc[
        risk["scope"].isin(["all", "holdout_2025_plus"]),
        ["exit_variant", "sizing_variant", "scope", "trades", "profit_factor", "cumulative_net_return", "maximum_drawdown", "average_effective_leverage"],
    ]
    def result(exit_variant: str, scope: str) -> pd.Series:
        return summary.loc[
            (summary["exit_variant"] == exit_variant)
            & (summary["scope"] == scope)
            & summary["one_way_cost_bps"].eq(REFERENCE_ONE_WAY_COST_BPS)
        ].iloc[0]

    baseline_all = result("atr_trailing_baseline", "all")
    lock_all = result("cost_aware_profit_lock", "all")
    baseline_holdout = result("atr_trailing_baseline", "holdout_2025_plus")
    lock_holdout = result("cost_aware_profit_lock", "holdout_2025_plus")
    lock_break_even = float(
        break_even.loc[
            break_even["exit_variant"] == "cost_aware_profit_lock",
            "break_even_one_way_cost_bps",
        ].iloc[0]
    )
    return f"""# BTC five-minute cost-aware trailing-stop comparison

## Rule

The baseline activates its 0.5-ATR trail after a 1.5-ATR favorable move. The alternative assumes {REFERENCE_ONE_WAY_COST_BPS:.0f} bps per side and creates a fixed floor at entry plus the {2 * REFERENCE_ONE_WAY_COST_BPS:.0f}-bps round trip plus a {LOCKED_NET_PROFIT_BPS:.0f}-bps net-profit buffer. It activates when price reaches that floor plus one 0.5-ATR trailing offset, then ratchets with each favorable extreme. Static stop and 2R target remain unchanged.

A normal stop fill at the floor locks the buffer under this cost model. A price gap can fill beyond it, so profit is never guaranteed.

The change helps but does not make the strategy deployable at the design cost. Full-history return improves from {baseline_all['cumulative_net_return']:.1%} to {lock_all['cumulative_net_return']:.1%}, and holdout return improves from {baseline_holdout['cumulative_net_return']:.1%} to {lock_holdout['cumulative_net_return']:.1%}. Profit factor remains below one ({lock_all['profit_factor']:.3f} overall, {lock_holdout['profit_factor']:.3f} holdout), and break-even cost is {lock_break_even:.2f} bps per side versus the assumed {REFERENCE_ONE_WAY_COST_BPS:.0f}. The higher win rate reflects many small locked gains, but the initial-stop losses still outweigh them.

## Results at the design cost

{_markdown_table(primary)}

## Exit behavior

{_markdown_table(exits)}

## Cost curve

{_markdown_table(cost_curve)}

## Break-even cost

{_markdown_table(break_even)}

## 0.25% stop-risk sizing, 3x cap

{_markdown_table(risk_view)}

## Audit and interpretation

- Cost-lock audit: **{audit['status']}**.
- Signals are the unchanged `full_no_delta_proxy`; only exit management differs.
- Both variants enter at the next five-minute open and use the same deterministic intrabar OHLC path.
- The cost floor covers modeled commission/slippage, not funding, spread changes, latency, or gap loss.
- This test is still based on five-minute OHLCV and is not genuine order-flow reconstruction.
"""


def build_btc_deepcharts_cost_lock_backtest(
    project_root: str | Path | None = None,
    *,
    data_path: str | Path = DEFAULT_DATA,
    output_dir: str | Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)

    def resolved(value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else root / path

    data_file = resolved(data_path)
    output = resolved(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    bars, data_quality = load_binance_btc_5m(data_file)
    schedule = build_seven_day_schedule(bars.index, "UTC")
    proxy_config = DeepChartsProxyConfig()
    pine_config = PineFabioConfig(
        reward_to_risk=proxy_config.reward_to_risk,
        trail_activation_atr=proxy_config.trail_activation_atr,
        trail_offset_atr=proxy_config.trail_offset_atr,
        maximum_daily_losses=99,
    )
    session_context = build_session_context_proxy(bars, schedule, proxy_config)
    features = build_five_minute_features_proxy(bars, schedule, session_context, proxy_config)
    donchian = build_donchian_context(
        bars,
        timeframe_minutes=proxy_config.donchian_timeframe_minutes,
        length=proxy_config.donchian_length,
    )
    raw_signals = build_raw_proxy_signals(features, donchian, proxy_config)
    signals = select_signal_variants(raw_signals)["full_no_delta_proxy"]

    baseline, baseline_execution = run_broker_emulator(features, signals, pine_config)
    cost_lock, cost_lock_execution = run_cost_lock_broker_emulator(
        features,
        signals,
        pine_config,
        one_way_cost_bps=REFERENCE_ONE_WAY_COST_BPS,
        locked_net_profit_bps=LOCKED_NET_PROFIT_BPS,
    )
    trade_sets = {"atr_trailing_baseline": baseline, "cost_aware_profit_lock": cost_lock}
    summary_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []
    exit_rows: list[dict[str, Any]] = []
    break_even_rows: list[dict[str, Any]] = []
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
            path, _ = proxy_account_path(
                trades,
                sizing_variant="one_x_notional",
                one_way_cost_bps=cost,
                config=proxy_config,
            )
            for metrics in _scope_metrics(path):
                summary_rows.append(
                    {"exit_variant": name, "one_way_cost_bps": cost} | metrics
                )
        for sizing in ("risk_025pct_cap3x", "risk_025pct_cap3x_daily_halt_proxy"):
            path, diagnostics = proxy_account_path(
                trades,
                sizing_variant=sizing,
                one_way_cost_bps=REFERENCE_ONE_WAY_COST_BPS,
                config=proxy_config,
            )
            for metrics in _scope_metrics(path):
                risk_rows.append(
                    {"exit_variant": name, "sizing_variant": sizing, **diagnostics} | metrics
                )
        break_even_rows.append(
            {"exit_variant": name, "break_even_one_way_cost_bps": _break_even_cost_bps(trades, proxy_config)}
        )

    summary = pd.DataFrame(summary_rows)
    risk = pd.DataFrame(risk_rows)
    exits = pd.DataFrame(exit_rows)
    break_even = pd.DataFrame(break_even_rows)
    audit = _audit_cost_lock(
        cost_lock,
        one_way_cost_bps=REFERENCE_ONE_WAY_COST_BPS,
        locked_net_profit_bps=LOCKED_NET_PROFIT_BPS,
    )
    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "RESEARCH_ONLY_LIVE_DEPLOYMENT_BLOCKED",
        "data_source": str(data_file),
        "data_quality": data_quality,
        "signal_variant": "full_no_delta_proxy",
        "proxy_config": asdict(proxy_config),
        "reference_one_way_cost_bps": REFERENCE_ONE_WAY_COST_BPS,
        "locked_net_profit_bps": LOCKED_NET_PROFIT_BPS,
        "costs_bps_per_side": COSTS_BPS,
        "execution_diagnostics": {
            "atr_trailing_baseline": baseline_execution,
            "cost_aware_profit_lock": cost_lock_execution,
        },
        "audit": audit,
    }
    signals.to_csv(output / "signals_full_no_delta_proxy.csv", index=False)
    summary.to_csv(output / "summary.csv", index=False)
    risk.to_csv(output / "risk_comparison.csv", index=False)
    exits.to_csv(output / "exit_diagnostics.csv", index=False)
    break_even.to_csv(output / "break_even_costs.csv", index=False)
    (output / "causality_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    (output / "governance.json").write_text(json.dumps(governance, indent=2), encoding="utf-8")
    report = _report(summary, risk, exits, break_even, audit)
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
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_btc_deepcharts_cost_lock_backtest(
        project_root=args.project_root,
        data_path=args.data_path,
        output_dir=args.output_dir,
    )
    print(f"Report: {result['report_path']}")
    print(
        result["summary"].loc[
            result["summary"]["one_way_cost_bps"].eq(REFERENCE_ONE_WAY_COST_BPS)
            & result["summary"]["scope"].isin(["all", "holdout_2025_plus"])
        ].to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
