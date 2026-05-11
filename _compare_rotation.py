"""Run build_sector_ml_view with and without point-in-time quality scoring
and print the historical_rotation_view metrics side by side.

This bypasses the report renderer (which has a Python-3.11 f-string bug) and
exercises only the rotation backtest path that the fix actually touches.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import pandas as pd

import price_action.sector_ml as sm


def _summary_row(view: dict, label: str) -> pd.DataFrame:
    if not view or not view.get("available"):
        return pd.DataFrame()
    frame = view["strategy_summary_frame"].copy()
    frame.insert(0, "scenario", label)
    return frame[
        [
            "scenario",
            "strategy_label",
            "total_return",
            "cagr",
            "sharpe",
            "max_drawdown",
            "calmar",
            "profit_factor",
            "hit_rate",
            "trade_count",
        ]
    ]


t0 = time.perf_counter()
view = sm.build_sector_ml_view()
t1 = time.perf_counter()
print(f"build_sector_ml_view: {t1 - t0:.1f}s")
print(f"available: {view.get('available')}")
print()

ql = view.get("quality_lookup_frame")
if isinstance(ql, pd.DataFrame) and not ql.empty:
    print("quality_lookup_frame summary:")
    print(f"  rows: {len(ql)}  signal_years: {ql['signal_year'].nunique()}"
          f"  symbols: {ql['symbol'].nunique()}")
    print()
    pivot = (
        ql.pivot(index="signal_year", columns="symbol", values="validation_quality_score")
        .round(3)
    )
    print("Per-(year, sector) quality score (head and tail):")
    print(pivot.head(8).to_string())
    print("  ...")
    print(pivot.tail(5).to_string())
    print()

print("=" * 80)
print("HISTORICAL ROTATION VIEW (2006-2026 walk-forward, point-in-time quality):")
print("=" * 80)
hist = view.get("historical_rotation_view") or {}
print(_summary_row(hist, "historical_pit_quality").to_string(index=False))
print()
print(f"benchmark: {hist.get('benchmark_start')} → {hist.get('benchmark_end')}, "
      f"{hist.get('period_count')} periods")
print()

print("=" * 80)
print("HOLDOUT ROTATION VIEW (2025+):")
print("=" * 80)
hold = view.get("holdout_rotation_view") or {}
print(_summary_row(hold, "holdout").to_string(index=False))
print()

vqf = view.get("validation_quality_frame")
if isinstance(vqf, pd.DataFrame) and not vqf.empty:
    print("=" * 80)
    print("Static all-validation quality (legacy aggregate, kept for reference):")
    print("=" * 80)
    print(
        vqf[["symbol", "sector_label", "validation_quality_score"]]
        .round(3)
        .to_string(index=False)
    )
