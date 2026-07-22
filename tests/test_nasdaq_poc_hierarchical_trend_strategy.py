from __future__ import annotations

import unittest

import pandas as pd

from price_action.nasdaq_poc_hierarchical_trend_strategy import (
    build_risk_paths,
    build_session_hierarchy_context,
)


class NasdaqPocHierarchicalTrendTests(unittest.TestCase):
    def test_session_context_shifts_previous_levels(self) -> None:
        index = pd.date_range("2025-01-01 14:30", periods=60, freq="min", tz="UTC").append(
            pd.date_range("2025-01-02 14:30", periods=60, freq="min", tz="UTC")
        )
        bars = pd.DataFrame(
            {
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 10.0,
            },
            index=index,
        )
        bars.loc[index[:60], "high"] = 105.0
        schedule = pd.DataFrame(
            {
                "session_date": ["2025-01-01", "2025-01-02"],
                "session_open": [index[0], index[60]],
                "session_close": [index[59] + pd.Timedelta(minutes=1), index[-1] + pd.Timedelta(minutes=1)],
                "opening_start": [index[0], index[60]],
                "opening_end": [index[0] + pd.Timedelta(minutes=30), index[60] + pd.Timedelta(minutes=30)],
            }
        )
        context = build_session_hierarchy_context(bars, schedule)
        self.assertTrue(pd.isna(context.iloc[0]["prior_session_high"]))
        self.assertAlmostEqual(float(context.iloc[1]["prior_session_high"]), 105.0)
        self.assertEqual(context.iloc[1]["prior_session_available_time"], context.iloc[0]["available_time"])

    def test_hierarchy_sizing_never_exceeds_quarter_percent(self) -> None:
        trades = pd.DataFrame(
            {
                "signal_time": pd.to_datetime(["2024-01-01", "2025-01-01"], utc=True),
                "entry_time": pd.to_datetime(["2024-01-01", "2025-01-01"], utc=True),
                "session_date": ["2024-01-01", "2025-01-01"],
                "net_r": [1.0, -1.0],
                "hierarchy_score": [6, 2],
                "hierarchy_risk_fraction": [0.0025, 0.0],
            }
        )
        _, summary = build_risk_paths(trades)
        hierarchy = summary.loc[summary["variant"].eq("hierarchy_risk")]
        self.assertTrue(hierarchy["average_risk_fraction"].le(0.0025).all())


if __name__ == "__main__":
    unittest.main()
