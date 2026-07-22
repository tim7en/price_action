"""Five-minute BTCUSDT test of the supplied Fabio-inspired Pine v6 script.

The primary interpretation is literal on a Binance chart: the session string
uses the exchange timezone (UTC) and applies seven days per week.  A separate
New York-clock sensitivity represents the intent suggested by the input label.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from price_action.data import resolve_project_root
from price_action.nasdaq_fabio_pine_v6_backtest import (
    PineFabioConfig,
    _audit_causality,
    _markdown_table,
    account_path,
    build_cost_sensitivity,
    build_raw_signals,
    run_broker_emulator,
    summarize_scopes,
)


DEFAULT_DATA = Path(
    "cache/cache/binance_asia_orb/BTCUSDT_2022-01-01_2026-02-25_5m.csv.gz"
)
DEFAULT_OUTPUT = Path("outputs/btc_fabio_pine_v6_backtest")
BAR_MINUTES = 5
REFERENCE_ONE_WAY_COST_BPS = 6.0
STRESS_ONE_WAY_COST_BPS = 15.0


def load_binance_btc_5m(path: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = pd.read_csv(path)
    required = {"open_time", "open", "high", "low", "close", "volume", "close_time"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"BTCUSDT file is missing columns: {sorted(missing)}")
    frame["timestamp"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True, errors="coerce")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame[["timestamp", "open", "high", "low", "close", "volume"]].isna().any().any():
        raise ValueError("BTCUSDT file contains null or unparseable required values")
    frame = frame.sort_values("timestamp")
    duplicate_count = int(frame["timestamp"].duplicated().sum())
    if duplicate_count:
        raise ValueError(f"BTCUSDT file contains {duplicate_count} duplicate timestamps")
    steps = frame["timestamp"].diff().dropna()
    expected = int(
        (frame["timestamp"].iloc[-1] - frame["timestamp"].iloc[0])
        / pd.Timedelta(minutes=BAR_MINUTES)
    ) + 1
    bars = frame.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
    return bars, {
        "input_rows": int(len(bars)),
        "first_bar_utc": bars.index.min().isoformat(),
        "last_bar_utc": bars.index.max().isoformat(),
        "expected_rows_on_complete_grid": expected,
        "missing_five_minute_bars": expected - len(bars),
        "non_five_minute_steps": int(steps.ne(pd.Timedelta(minutes=5)).sum()),
        "maximum_gap_minutes": float(steps.max() / pd.Timedelta(minutes=1)),
        "duplicate_timestamps": duplicate_count,
        "zero_volume_bars": int(bars["volume"].eq(0.0).sum()),
        "venue_product_identity": "unverified BTCUSDT klines; spot versus perpetual metadata absent",
    }


def build_seven_day_schedule(index: pd.DatetimeIndex, timezone: str) -> pd.DataFrame:
    local_start = index.min().tz_convert(timezone).date()
    local_end = index.max().tz_convert(timezone).date()
    dates = pd.date_range(local_start, local_end, freq="D")
    opens = pd.DatetimeIndex(
        [pd.Timestamp(f"{date.date()} 09:30", tz=timezone) for date in dates]
    ).tz_convert("UTC")
    closes = pd.DatetimeIndex(
        [pd.Timestamp(f"{date.date()} 16:00", tz=timezone) for date in dates]
    ).tz_convert("UTC")
    return pd.DataFrame(
        {
            "session_date": dates.strftime("%Y-%m-%d"),
            "session_open": opens,
            "session_close": closes,
        }
    )


def _paths(trades: pd.DataFrame, config: PineFabioConfig) -> pd.DataFrame:
    definitions = (
        ("script_zero_cost", 0.0),
        ("script_reference_cost", REFERENCE_ONE_WAY_COST_BPS),
        ("intended_1pct_risk_capped_10x", REFERENCE_ONE_WAY_COST_BPS),
    )
    frames: list[pd.DataFrame] = []
    for output_name, cost in definitions:
        engine_name = (
            "script_realistic_cost" if output_name == "script_reference_cost" else output_name
        )
        path = account_path(
            trades,
            variant=engine_name,
            one_way_cost_bps=cost,
            config=config,
        )
        path["variant"] = output_name
        frames.append(path)
    return pd.concat(frames, ignore_index=True)


def _report(
    summary: pd.DataFrame,
    costs: pd.DataFrame,
    execution: pd.DataFrame,
    audits: dict[str, Any],
    data_quality: dict[str, Any],
) -> str:
    overall = summary.loc[
        (summary["scope"] == "all") & (summary["setup_scope"] == "all")
    ][
        [
            "session_interpretation", "variant", "trades", "win_rate", "average_net_r",
            "profit_factor", "cumulative_net_return", "annualized_net_return", "maximum_drawdown",
            "average_effective_leverage", "average_risk_fraction",
        ]
    ]
    holdout = summary.loc[
        (summary["scope"] == "holdout_2025_plus") & (summary["setup_scope"] == "all")
    ][
        [
            "session_interpretation", "variant", "trades", "profit_factor",
            "cumulative_net_return", "maximum_drawdown",
        ]
    ]
    setup = summary.loc[
        (summary["session_interpretation"] == "literal_binance_utc")
        & (summary["variant"] == "script_reference_cost")
        & (summary["scope"] == "all")
    ][
        ["setup_scope", "trades", "win_rate", "average_net_r", "profit_factor", "cumulative_net_return"]
    ]
    cost_view = costs[
        ["session_interpretation", "one_way_cost_bps", "profit_factor", "cumulative_net_return", "maximum_drawdown"]
    ]
    return f"""# BTCUSDT Fabio Pine v6: native five-minute backtest

## Primary results

The source contains {data_quality['input_rows']:,} native five-minute bars from {data_quality['first_bar_utc'][:10]} through {data_quality['last_bar_utc'][:10]}. The literal Binance interpretation uses 09:30–16:00 **UTC** on all seven days. The New York-clock result is a separate sensitivity because the Pine code never supplies the timezone promised by its input label.

{_markdown_table(overall)}

`script_reference_cost` assumes 6 bps per side: a 5-bps taker commission scenario plus 1 bp slippage. It is a scenario, not an account-specific fee quote. The repository's prior conservative BTC setting is represented by the 15-bps row in the cost table. Funding is not included.

## 2025 through February 2026 holdout

{_markdown_table(holdout)}

## Literal-session setup attribution at reference cost

{_markdown_table(setup)}

## Cost sensitivity

{_markdown_table(cost_view)}

## Execution diagnostics

{_markdown_table(execution)}

## Causality and interpretation

- Literal UTC causality audit: **{audits['literal_binance_utc']['status']}**.
- New York sensitivity causality audit: **{audits['label_intended_new_york']['status']}**.
- Signals use confirmed five-minute bars; entries use the next available bar open.
- Pine's `sessionBars <= 6` defines seven bars, or 35 elapsed minutes, on a five-minute chart.
- The session string omits days, so Pine v6 applies it seven days per week.
- `riskPercent` remains unused; the supplied strategy deploys 100% of equity. The 1% row is a separate sizing diagnostic.
- The source lacks spot/perpetual metadata. Shorts require a margin or perpetual product, and historical funding/mark prices are absent.
- There are {data_quality['missing_five_minute_bars']} missing bars, one maximum gap of {data_quality['maximum_gap_minutes']:.0f} minutes, and {data_quality['zero_volume_bars']} zero-volume bars.

This remains research-only.
"""


def build_btc_fabio_pine_v6_backtest(
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
    interpretations = {
        "literal_binance_utc": "UTC",
        "label_intended_new_york": "America/New_York",
    }
    summary_frames: list[pd.DataFrame] = []
    cost_frames: list[pd.DataFrame] = []
    execution_rows: list[dict[str, Any]] = []
    audits: dict[str, Any] = {}

    for name, session_timezone in interpretations.items():
        subdir = output / name
        subdir.mkdir(parents=True, exist_ok=True)
        schedule = build_seven_day_schedule(bars.index, session_timezone)
        indicated, signals = build_raw_signals(
            bars,
            schedule,
            config,
            bar_minutes=BAR_MINUTES,
            vwap_timezone="UTC",
        )
        trades, diagnostics = run_broker_emulator(indicated, signals, config)
        diagnostics.update(
            {
                "trades_held_at_least_8h": int(trades["holding_bars"].ge(96).sum()),
                "trades_held_at_least_24h": int(trades["holding_bars"].ge(288).sum()),
                "maximum_holding_bars": int(trades["holding_bars"].max()),
                "target_exits": int(trades["exit_reason"].str.startswith("target").sum()),
                "trailing_stop_exits": int(trades["exit_reason"].str.startswith("trailing").sum()),
                "static_stop_exits": int(trades["exit_reason"].str.startswith("static").sum()),
            }
        )
        paths = _paths(trades, config)
        summary = summarize_scopes(paths)
        summary["scope"] = summary["scope"].replace(
            {"development_2024": "development_2022_2024", "holdout_2025": "holdout_2025_plus"}
        )
        summary.insert(0, "session_interpretation", name)
        costs = build_cost_sensitivity(
            trades,
            config,
            one_way_costs_bps=(0.0, 1.0, 1.5, 2.0, 2.5, 3.0, 5.0, 6.0, 7.5, 10.0, 15.0),
        )
        costs.insert(0, "session_interpretation", name)
        audit = _audit_causality(
            bars,
            schedule,
            indicated,
            signals,
            trades,
            config,
            bar_minutes=BAR_MINUTES,
            vwap_timezone="UTC",
        )
        audits[name] = audit
        execution_rows.append({"session_interpretation": name} | diagnostics)
        summary_frames.append(summary)
        cost_frames.append(costs)
        schedule.to_csv(subdir / "session_schedule.csv", index=False)
        signals.to_csv(subdir / "signals.csv", index=False)
        trades.to_csv(subdir / "trades.csv", index=False)
        paths.to_csv(subdir / "equity_paths.csv", index=False)
        (subdir / "causality_audit.json").write_text(
            json.dumps(audit, indent=2), encoding="utf-8"
        )

    summary_all = pd.concat(summary_frames, ignore_index=True)
    costs_all = pd.concat(cost_frames, ignore_index=True)
    execution = pd.DataFrame(execution_rows)
    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "RESEARCH_ONLY_LIVE_DEPLOYMENT_BLOCKED",
        "source": str(data_file),
        "bar_minutes": BAR_MINUTES,
        "config": asdict(config),
        "reference_one_way_cost_bps": REFERENCE_ONE_WAY_COST_BPS,
        "stress_one_way_cost_bps": STRESS_ONE_WAY_COST_BPS,
        "data_quality": data_quality,
        "interpretations": {
            "literal_binance_utc": "Pine session in Binance exchange timezone UTC; VWAP UTC day.",
            "label_intended_new_york": "Session forced to America/New_York as suggested by label; VWAP remains UTC day.",
        },
        "funding": "not modeled; historical rates and product identity absent",
        "audits": audits,
    }
    summary_all.to_csv(output / "summary.csv", index=False)
    costs_all.to_csv(output / "cost_sensitivity.csv", index=False)
    execution.to_csv(output / "execution_diagnostics.csv", index=False)
    (output / "governance.json").write_text(json.dumps(governance, indent=2), encoding="utf-8")
    report = _report(summary_all, costs_all, execution, audits, data_quality)
    report_path = output / "report.md"
    report_path.write_text(report, encoding="utf-8")
    return {
        "report_path": report_path,
        "summary": summary_all,
        "cost_sensitivity": costs_all,
        "execution": execution,
        "governance": governance,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root")
    parser.add_argument("--data-path", default=str(DEFAULT_DATA))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_btc_fabio_pine_v6_backtest(
        project_root=args.project_root,
        data_path=args.data_path,
        output_dir=args.output_dir,
    )
    print(f"Report: {result['report_path']}")
    print(
        result["summary"].loc[
            (result["summary"]["scope"] == "all")
            & (result["summary"]["setup_scope"] == "all")
        ].to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
