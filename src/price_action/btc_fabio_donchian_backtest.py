"""Causal higher-timeframe Donchian filters for five-minute BTC Fabio signals."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from price_action.btc_fabio_pine_v6_backtest import (
    BAR_MINUTES,
    DEFAULT_DATA,
    REFERENCE_ONE_WAY_COST_BPS,
    build_seven_day_schedule,
    load_binance_btc_5m,
)
from price_action.data import resolve_project_root
from price_action.nasdaq_fabio_pine_v6_backtest import (
    PineFabioConfig,
    _markdown_table,
    account_path,
    build_raw_signals,
    run_broker_emulator,
    summarize_path,
)


DEFAULT_OUTPUT = Path("outputs/btc_fabio_donchian_backtest")
HOLDOUT_START = pd.Timestamp("2025-01-01", tz="UTC")
DONCHIAN_LENGTH = 20
HIGHER_TIMEFRAMES = (15, 60, 240)
COSTS_BPS = (0.0, 1.0, 2.0, 3.0, 6.0)


def build_donchian_context(
    bars: pd.DataFrame,
    *,
    timeframe_minutes: int,
    length: int = DONCHIAN_LENGTH,
) -> pd.DataFrame:
    """Build a persistent breakout state from complete higher-timeframe bars.

    Channel boundaries exclude the current higher-timeframe bar.  Each state is
    timestamped at that bar's closing time, when it first becomes observable.
    """
    if timeframe_minutes <= BAR_MINUTES or timeframe_minutes % BAR_MINUTES:
        raise ValueError("Higher timeframe must be a multiple of five minutes")
    ratio = timeframe_minutes // BAR_MINUTES
    rule = f"{timeframe_minutes}min"
    counts = bars["close"].resample(rule, origin="epoch", label="left", closed="left").count()
    higher = bars.resample(rule, origin="epoch", label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    higher = higher.loc[counts.eq(ratio)].dropna().copy()
    higher["channel_upper"] = higher["high"].shift(1).rolling(
        length, min_periods=length
    ).max()
    higher["channel_lower"] = higher["low"].shift(1).rolling(
        length, min_periods=length
    ).min()
    higher["channel_mid"] = (higher["channel_upper"] + higher["channel_lower"]) / 2.0
    long_breakout = higher["close"].gt(higher["channel_upper"])
    short_breakout = higher["close"].lt(higher["channel_lower"])
    events = pd.Series(
        np.select([long_breakout, short_breakout], [1.0, -1.0], default=np.nan),
        index=higher.index,
    )
    higher["donchian_state"] = events.ffill().fillna(0.0).astype(int)
    higher["higher_bar_start"] = higher.index
    higher["available_time"] = higher.index + pd.Timedelta(minutes=timeframe_minutes)
    return higher.reset_index(drop=True)


def attach_donchian_state(
    signals: pd.DataFrame,
    context: pd.DataFrame,
) -> pd.DataFrame:
    if signals.empty:
        return signals.copy()
    columns = [
        "available_time", "higher_bar_start", "donchian_state",
        "channel_upper", "channel_lower", "channel_mid", "close",
    ]
    right = context[columns].rename(columns={"close": "higher_close"}).sort_values(
        "available_time"
    )
    attached = pd.merge_asof(
        signals.sort_values("signal_time"),
        right,
        left_on="signal_time",
        right_on="available_time",
        direction="backward",
        allow_exact_matches=True,
    )
    attached["donchian_state"] = attached["donchian_state"].fillna(0).astype(int)
    attached["donchian_aligned"] = attached["side"].eq(attached["donchian_state"])
    return attached.sort_values(["signal_bar_id", "side"], ascending=[True, False]).reset_index(drop=True)


def _scoped_metrics(path: pd.DataFrame) -> list[dict[str, Any]]:
    scopes = {
        "all": path,
        "development_2022_2024": path.loc[path["entry_time"] < HOLDOUT_START],
        "holdout_2025_plus": path.loc[path["entry_time"] >= HOLDOUT_START],
    }
    return [{"scope": name} | summarize_path(frame) for name, frame in scopes.items()]


def break_even_one_way_cost_bps(
    trades: pd.DataFrame,
    config: PineFabioConfig,
    *,
    upper_bound_bps: float = 20.0,
) -> float:
    if trades.empty:
        return np.nan
    zero = account_path(
        trades, variant="script_realistic_cost", one_way_cost_bps=0.0, config=config
    )
    if summarize_path(zero)["cumulative_net_return"] <= 0.0:
        return 0.0
    lower, upper = 0.0, upper_bound_bps
    for _ in range(45):
        middle = (lower + upper) / 2.0
        path = account_path(
            trades,
            variant="script_realistic_cost",
            one_way_cost_bps=middle,
            config=config,
        )
        if summarize_path(path)["cumulative_net_return"] > 0.0:
            lower = middle
        else:
            upper = middle
    return float((lower + upper) / 2.0)


def _audit_donchian(
    bars: pd.DataFrame,
    contexts: dict[str, pd.DataFrame],
    filtered_signals: dict[str, pd.DataFrame],
    trades: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    availability = all(
        frame.empty
        or frame["available_time"].le(frame["signal_time"]).all()
        for name, frame in filtered_signals.items()
        if name != "unfiltered"
    )
    directional = all(
        frame.empty or frame["side"].eq(frame["donchian_state"]).all()
        for name, frame in filtered_signals.items()
        if name != "unfiltered"
    )
    next_bar = all(
        frame.empty
        or frame["entry_bar_id"].eq(frame["signal_bar_id"] + 1).all()
        for frame in trades.values()
    )
    prefix_checks: dict[str, bool] = {}
    cutoff = 100_000
    prefix_bars = bars.iloc[:cutoff].copy()
    cutoff_time = prefix_bars.index.max()
    for name, context in contexts.items():
        minutes = int(name.split("_")[1].removesuffix("m"))
        prefix = build_donchian_context(
            prefix_bars, timeframe_minutes=minutes, length=DONCHIAN_LENGTH
        )
        common_full = context.loc[context["available_time"] <= cutoff_time].reset_index(drop=True)
        common_prefix = prefix.loc[prefix["available_time"] <= cutoff_time].reset_index(drop=True)
        columns = ["available_time", "channel_upper", "channel_lower", "donchian_state"]
        prefix_checks[name] = bool(
            len(common_full) == len(common_prefix)
            and common_full["available_time"].equals(common_prefix["available_time"])
            and np.allclose(
                common_full[["channel_upper", "channel_lower"]].to_numpy(dtype=float),
                common_prefix[["channel_upper", "channel_lower"]].to_numpy(dtype=float),
                equal_nan=True,
            )
            and common_full["donchian_state"].equals(common_prefix["donchian_state"])
        )
    checks = {
        "higher_timeframe_available_before_signal": bool(availability),
        "signals_match_persistent_donchian_direction": bool(directional),
        "entries_fill_on_next_five_minute_bar": bool(next_bar),
        "higher_timeframe_prefix_invariance": bool(all(prefix_checks.values())),
        "channel_excludes_current_higher_timeframe_bar": True,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "prefix_checks": prefix_checks,
        "rule": (
            "Long state begins when a completed HTF close exceeds the previous 20 complete HTF highs; "
            "short state begins below the previous 20 lows; state persists until the opposite breakout."
        ),
    }


def _report(
    summary: pd.DataFrame,
    funnel: pd.DataFrame,
    break_even: pd.DataFrame,
    audit: dict[str, Any],
    data_quality: dict[str, Any],
) -> str:
    all_reference = summary.loc[
        (summary["scope"] == "all") & summary["one_way_cost_bps"].eq(REFERENCE_ONE_WAY_COST_BPS)
    ][
        [
            "filter_variant", "trades", "win_rate", "average_net_r", "profit_factor",
            "cumulative_net_return", "annualized_net_return", "maximum_drawdown",
        ]
    ]
    all_zero = summary.loc[
        (summary["scope"] == "all") & summary["one_way_cost_bps"].eq(0.0)
    ][["filter_variant", "trades", "profit_factor", "cumulative_net_return", "maximum_drawdown"]]
    holdout = summary.loc[
        (summary["scope"] == "holdout_2025_plus")
        & summary["one_way_cost_bps"].eq(REFERENCE_ONE_WAY_COST_BPS)
    ][["filter_variant", "trades", "profit_factor", "cumulative_net_return", "maximum_drawdown"]]
    return f"""# BTC Fabio five-minute signals with higher-timeframe Donchian bias

## Test design

The lower-timeframe engine is the literal Binance-UTC Pine translation. A fixed 20-bar Donchian breakout state is calculated independently on complete 15-minute, one-hour, and four-hour bars. Long five-minute signals are allowed only in a persistent long state and shorts only in a persistent short state. The higher-timeframe bar must have closed before the five-minute signal bar opens.

This is a price-structure bias, not true order flow. The OHLCV source cannot observe bid/ask delta, footprint imbalances, resting liquidity, or tape absorption.

## Zero-cost comparison

{_markdown_table(all_zero)}

## Reference-cost comparison: 6 bps per side

{_markdown_table(all_reference)}

## 2025 through February 2026 holdout at reference cost

{_markdown_table(holdout)}

## Signal funnel

{_markdown_table(funnel)}

## Cost break-even

{_markdown_table(break_even)}

## Causality and decision

- Audit status: **{audit['status']}**.
- Donchian channels exclude the current higher-timeframe bar and use a persistent breakout state.
- Context is mapped with `available_time <= signal_time`; no incomplete HTF bar is used.
- Filtering occurs before position overlap and the three-loss daily cutoff are simulated.
- Source gaps remain: {data_quality['missing_five_minute_bars']} missing five-minute bars and a maximum {data_quality['maximum_gap_minutes']:.0f}-minute gap.
- The three timeframes are a fixed robustness comparison, not a parameter optimization. Selecting the best result after seeing the shared holdout would not constitute independent validation.

Live deployment remains blocked by execution costs, missing bid/ask data, unverified spot/perpetual identity, and absent funding history.
"""


def build_btc_fabio_donchian_backtest(
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
    config = PineFabioConfig(realistic_one_way_cost_bps=REFERENCE_ONE_WAY_COST_BPS)
    schedule = build_seven_day_schedule(bars.index, "UTC")
    indicated, raw_signals = build_raw_signals(
        bars,
        schedule,
        config,
        bar_minutes=BAR_MINUTES,
        vwap_timezone="UTC",
    )

    contexts: dict[str, pd.DataFrame] = {}
    signal_sets: dict[str, pd.DataFrame] = {"unfiltered": raw_signals.copy()}
    for timeframe in HIGHER_TIMEFRAMES:
        name = f"donchian_{timeframe}m_20"
        context = build_donchian_context(
            bars, timeframe_minutes=timeframe, length=DONCHIAN_LENGTH
        )
        attached = attach_donchian_state(raw_signals, context)
        contexts[name] = context
        signal_sets[name] = attached.loc[attached["donchian_aligned"]].copy()
        context.to_csv(output / f"context_{timeframe}m.csv", index=False)

    trade_sets: dict[str, pd.DataFrame] = {}
    summary_rows: list[dict[str, Any]] = []
    funnel_rows: list[dict[str, Any]] = []
    break_even_rows: list[dict[str, Any]] = []
    execution_diagnostics: dict[str, Any] = {}
    for name, selected in signal_sets.items():
        trades, diagnostics = run_broker_emulator(indicated, selected, config)
        trade_sets[name] = trades
        execution_diagnostics[name] = diagnostics
        selected.to_csv(output / f"signals_{name}.csv", index=False)
        trades.to_csv(output / f"trades_{name}.csv", index=False)
        funnel_rows.append(
            {
                "filter_variant": name,
                "raw_signals": int(len(raw_signals)),
                "directionally_allowed_signals": int(len(selected)),
                "executed_trades": int(len(trades)),
                "signal_retention": float(len(selected) / len(raw_signals)),
                "trade_retention_vs_unfiltered": np.nan,
            }
        )
        for cost in COSTS_BPS:
            path = account_path(
                trades,
                variant="script_realistic_cost",
                one_way_cost_bps=cost,
                config=config,
            )
            for metrics in _scoped_metrics(path):
                summary_rows.append(
                    {"filter_variant": name, "one_way_cost_bps": cost} | metrics
                )
        break_even_rows.append(
            {
                "filter_variant": name,
                "break_even_one_way_cost_bps": break_even_one_way_cost_bps(trades, config),
            }
        )

    unfiltered_trades = max(len(trade_sets["unfiltered"]), 1)
    funnel = pd.DataFrame(funnel_rows)
    funnel["trade_retention_vs_unfiltered"] = funnel["executed_trades"] / unfiltered_trades
    summary = pd.DataFrame(summary_rows)
    break_even = pd.DataFrame(break_even_rows)
    audit = _audit_donchian(bars, contexts, signal_sets, trade_sets)
    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "RESEARCH_ONLY_LIVE_DEPLOYMENT_BLOCKED",
        "data_source": str(data_file),
        "data_quality": data_quality,
        "config": asdict(config),
        "donchian_length": DONCHIAN_LENGTH,
        "higher_timeframes_minutes": HIGHER_TIMEFRAMES,
        "costs_bps_per_side": COSTS_BPS,
        "reference_one_way_cost_bps": REFERENCE_ONE_WAY_COST_BPS,
        "execution_diagnostics": execution_diagnostics,
        "causality_audit": audit,
    }
    summary.to_csv(output / "summary.csv", index=False)
    funnel.to_csv(output / "signal_funnel.csv", index=False)
    break_even.to_csv(output / "break_even_costs.csv", index=False)
    (output / "causality_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    (output / "governance.json").write_text(json.dumps(governance, indent=2), encoding="utf-8")
    report = _report(summary, funnel, break_even, audit, data_quality)
    report_path = output / "report.md"
    report_path.write_text(report, encoding="utf-8")
    return {
        "report_path": report_path,
        "summary": summary,
        "funnel": funnel,
        "break_even": break_even,
        "audit": audit,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root")
    parser.add_argument("--data-path", default=str(DEFAULT_DATA))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_btc_fabio_donchian_backtest(
        project_root=args.project_root,
        data_path=args.data_path,
        output_dir=args.output_dir,
    )
    print(f"Report: {result['report_path']}")
    print(
        result["summary"].loc[
            (result["summary"]["scope"] == "all")
            & result["summary"]["one_way_cost_bps"].eq(REFERENCE_ONE_WAY_COST_BPS)
        ].to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
