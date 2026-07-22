from __future__ import annotations

import unittest

import pandas as pd

from price_action.nasdaq_identify_confirm_trade_backtest import (
    NasdaqExecutionCosts,
    IdentifyConfirmTradeConfig,
    build_session_candidates,
    simulate_trade,
)


class NasdaqIdentifyConfirmTradeTests(unittest.TestCase):
    def test_build_session_candidates_flags_short_rejection(self) -> None:
        index = pd.date_range("2025-01-02 14:30", periods=5, freq="min", tz="UTC")
        session_frame = pd.DataFrame(
            {
                "open": [100.0, 100.5, 101.0, 101.3, 101.8],
                "high": [100.7, 101.2, 101.5, 102.0, 102.2],
                "low": [99.8, 100.4, 100.9, 101.2, 101.0],
                "close": [100.5, 101.0, 101.3, 101.8, 101.1],
                "bar_id": [0, 1, 2, 3, 4],
                "atr": [1.0, 1.0, 1.0, 1.0, 1.0],
                "volume_strength": [0.8, 0.8, 0.9, 0.9, 1.4],
                "close_location": [0.75, 0.80, 0.75, 0.85, 0.20],
                "upper_wick_share": [0.10, 0.10, 0.10, 0.10, 0.55],
                "lower_wick_share": [0.10, 0.10, 0.10, 0.10, 0.10],
                "session_date": ["2025-01-02"] * 5,
                "session_open": [index[0]] * 5,
                "session_vwap": [100.2, 100.6, 100.9, 101.2, 101.3],
            },
            index=index,
        )
        session_levels = pd.DataFrame(
            {
                "session_date": ["2025-01-02", "2025-01-02"],
                "price": [102.1, 102.05],
                "role": ["resistance", "resistance"],
                "source": ["prior_session_high", "pivot_high_60m"],
                "timeframe_minutes": [float("nan"), 60.0],
            }
        )
        config = IdentifyConfirmTradeConfig(approach_bars=3)
        candidates = build_session_candidates(session_frame, session_levels, config)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(int(candidates.iloc[0]["signal_side"]), -1)
        self.assertAlmostEqual(float(candidates.iloc[0]["reference_level"]), 102.075)

    def test_simulate_trade_scales_out_then_hits_second_target(self) -> None:
        index = pd.date_range("2025-01-02 14:33", periods=5, freq="min", tz="UTC")
        bars = pd.DataFrame(
            {
                "open": [101.0, 100.9, 100.2, 99.8, 99.6],
                "high": [101.2, 101.0, 100.3, 99.9, 99.7],
                "low": [100.8, 100.1, 99.6, 99.3, 99.2],
                "close": [100.9, 100.2, 99.8, 99.6, 99.4],
            },
            index=index,
        )
        bars["bar_id"] = range(len(bars))
        signal = pd.Series(
            {
                "timestamp": index[0],
                "bar_id": 0,
                "session_date": "2025-01-02",
                "session_open": pd.Timestamp("2025-01-02 14:30", tz="UTC"),
                "setup": "identify_confirm_rejection",
                "signal_side": -1,
                "reference_level": 101.0,
                "signal_high": 101.2,
                "signal_low": 100.8,
                "signal_atr": 1.0,
                "level_count": 2,
                "level_sources": "prior_session_high|pivot_high_60m",
            }
        )
        session_levels = pd.DataFrame(
            {
                "session_date": ["2025-01-02", "2025-01-02"],
                "price": [100.0, 99.4],
                "role": ["support", "support"],
                "source": ["pivot_low_30m", "prior_session_low"],
                "timeframe_minutes": [30.0, float("nan")],
            }
        )
        config = IdentifyConfirmTradeConfig(
            stop_buffer_atr=0.10,
            first_target_fallback_r=0.50,
            final_target_fallback_r=1.00,
            locked_profit_r=0.10,
            trail_offset_atr=0.25,
        )
        trade = simulate_trade(
            signal,
            bars,
            session_levels,
            NasdaqExecutionCosts(commission_bps=0.0, slippage_bps=0.0),
            config,
        )
        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertTrue(bool(trade["partial_target_hit"]))
        self.assertEqual(str(trade["exit_reason"]), "target_2")
        self.assertGreater(float(trade["gross_r_multiple"]), 0.5)


if __name__ == "__main__":
    unittest.main()