from __future__ import annotations

import unittest

import pandas as pd

from price_action.nasdaq_identify_confirm_trade_backtest import (
    NasdaqExecutionCosts,
    IdentifyConfirmTradeConfig,
    _a_plus_features,
    _resample_ohlcv,
    _walk_to_target_or_stop,
    audit_causality,
    build_session_candidates,
    simulate_trade,
)


class NasdaqIdentifyConfirmTradeTests(unittest.TestCase):
    def test_higher_timeframe_bar_is_labelled_at_completion(self) -> None:
        index = pd.date_range("2025-01-02 14:00", periods=60, freq="min", tz="UTC")
        bars = pd.DataFrame(
            {
                "open": range(60),
                "high": range(1, 61),
                "low": range(60),
                "close": range(1, 61),
                "volume": 1.0,
            },
            index=index,
        )

        resampled = _resample_ohlcv(bars, 30)

        self.assertEqual(resampled.index.tolist(), [
            pd.Timestamp("2025-01-02 14:30", tz="UTC"),
            pd.Timestamp("2025-01-02 15:00", tz="UTC"),
        ])
        self.assertEqual(float(resampled.iloc[0]["close"]), 30.0)

    def test_completed_higher_timeframe_context_is_prefix_invariant(self) -> None:
        index = pd.date_range("2025-01-02 13:00", periods=180, freq="min", tz="UTC")
        bars = pd.DataFrame(
            {
                "open": range(180),
                "high": range(1, 181),
                "low": range(180),
                "close": range(1, 181),
                "volume": [100.0] * 180,
            },
            index=index,
        )
        decision_time = pd.Timestamp("2025-01-02 14:30", tz="UTC")
        full_known = _resample_ohlcv(bars, 60).loc[:decision_time]
        prefix_known = _resample_ohlcv(bars.loc[:decision_time], 60).loc[:decision_time]

        pd.testing.assert_frame_equal(full_known, prefix_known)

    def test_ambiguous_same_bar_boundary_is_a_stop(self) -> None:
        price, reason = _walk_to_target_or_stop(
            1,
            [100.0, 106.0, 94.0, 102.0],
            stop=95.0,
            target=105.0,
        )

        self.assertEqual(price, 95.0)
        self.assertEqual(reason, "stop")

    def test_causality_audit_rejects_future_level(self) -> None:
        schedule = pd.DataFrame({
            "session_date": ["2025-01-02"],
            "session_open": [pd.Timestamp("2025-01-02 14:30", tz="UTC")],
            "session_close": [pd.Timestamp("2025-01-02 21:00", tz="UTC")],
        })
        levels = pd.DataFrame({
            "session_date": ["2025-01-02"],
            "known_time": [pd.Timestamp("2025-01-02 15:00", tz="UTC")],
        })
        bars = pd.DataFrame(index=pd.date_range(
            "2025-01-02 14:30", periods=2, freq="min", tz="UTC"
        ))

        audit = audit_causality(
            levels,
            pd.DataFrame(),
            pd.DataFrame(),
            bars,
            schedule,
            IdentifyConfirmTradeConfig(),
        )

        self.assertEqual(audit["status"], "FAIL")
        self.assertEqual(audit["violations"]["levels_not_known_by_session_open"], 1)

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
        self.assertTrue(bool(candidates.iloc[0]["a_plus_setup"]))
        self.assertEqual(int(candidates.iloc[0]["a_plus_score"]), 5)

    def test_a_plus_requires_repeated_defense_without_future_bars(self) -> None:
        index = pd.date_range("2025-01-02 14:30", periods=7, freq="min", tz="UTC")
        frame = pd.DataFrame(
            {
                "open": [102.4, 102.0, 101.7, 101.3, 100.9, 100.4, 100.8],
                "high": [102.6, 102.2, 101.9, 101.5, 101.1, 101.0, 101.2],
                "low": [102.2, 101.8, 101.5, 101.1, 100.7, 99.7, 100.5],
                "close": [102.3, 101.9, 101.6, 101.2, 100.8, 100.8, 101.0],
                "atr": [1.0] * 7,
            },
            index=index,
        )
        level = {
            "reference_level": 100.0,
            "strong_level": True,
        }
        config = IdentifyConfirmTradeConfig(a_plus_context_bars=6)

        prefix_features = _a_plus_features(frame.iloc[:6], 5, 1, level, config)
        full_features = _a_plus_features(frame, 5, 1, level, config)

        self.assertEqual(prefix_features, full_features)
        self.assertFalse(bool(full_features["a_plus_repeated_defense"]))
        self.assertFalse(bool(full_features["a_plus_setup"]))
        self.assertEqual(full_features["a_plus_context_end"], index[5])

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
