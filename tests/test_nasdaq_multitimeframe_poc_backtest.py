from __future__ import annotations

import unittest

import pandas as pd

from price_action.nasdaq_multitimeframe_poc_backtest import (
    MultiTimeframePocConfig,
    build_composite_poc_context,
    build_fifteen_minute_blocks,
    strategy_signal_sets,
)


class NasdaqMultitimeframePocBacktestTests(unittest.TestCase):
    def test_structural_stop_uses_only_completed_fifteen_minute_range(self) -> None:
        observations = pd.DataFrame([{
            "mode": "one_minute_acceptance",
            "crossed_sources": "3d",
            "session_bucket": "opening_0_30m",
            "focus_cluster_count": 1,
            "completed_15m_direction_aligned": False,
            "vwap_aligned": True,
            "completed_15m_range": 40.0,
            "atr": 10.0,
            "side": 1,
            "session_close": pd.Timestamp("2025-01-02 21:00", tz="UTC"),
            "completed_15m_side": 1,
        }])

        signals = strategy_signal_sets(observations)

        self.assertEqual(signals["opening_3d5d_structural_stop_0.00"]["atr"].iloc[0], 10.0)
        self.assertEqual(signals["opening_3d5d_structural_stop_0.75"]["atr"].iloc[0], 30.0)

    def test_invalid_cluster_width_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            MultiTimeframePocConfig(
                poc_zone_half_width_daily_atr=0.05,
                poc_cluster_distance_daily_atr=0.05,
            )

    def test_fifteen_minute_context_uses_complete_blocks(self) -> None:
        index = pd.date_range("2025-01-02 14:30", periods=390, freq="1min", tz="UTC")
        bars = pd.DataFrame({
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10.0,
            "bar_id": range(390),
        }, index=index)
        schedule = pd.DataFrame([{
            "session_date": "2025-01-02",
            "session_open": index[0],
            "session_close": index[-1] + pd.Timedelta(minutes=1),
        }])

        blocks = build_fifteen_minute_blocks(
            bars,
            schedule,
            MultiTimeframePocConfig(),
        )

        self.assertEqual(len(blocks), 26)
        self.assertEqual(blocks.iloc[0]["block_end_bar"], index[14])
        self.assertEqual(blocks.iloc[1]["block_start"], index[15])

    def test_composite_context_does_not_use_current_session(self) -> None:
        first = pd.date_range("2025-01-02 14:30", periods=390, freq="1min", tz="UTC")
        second = pd.date_range("2025-01-03 14:30", periods=390, freq="1min", tz="UTC")
        index = first.append(second)
        bars = pd.DataFrame({
            "open": [100.0] * 390 + [1_000.0] * 390,
            "high": [101.0] * 390 + [1_001.0] * 390,
            "low": [99.0] * 390 + [999.0] * 390,
            "close": [100.0] * 390 + [1_000.0] * 390,
            "volume": 10.0,
        }, index=index)
        schedule = pd.DataFrame([
            {"session_date": "2025-01-02", "session_open": first[0], "session_close": first[-1] + pd.Timedelta(minutes=1)},
            {"session_date": "2025-01-03", "session_open": second[0], "session_close": second[-1] + pd.Timedelta(minutes=1)},
        ])

        context = build_composite_poc_context(
            bars,
            schedule,
            MultiTimeframePocConfig(),
        ).set_index("session_date")

        self.assertTrue(pd.isna(context.loc["2025-01-02", "composite_poc_1d"]))
        self.assertLess(context.loc["2025-01-03", "composite_poc_1d"], 200.0)


if __name__ == "__main__":
    unittest.main()
