from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from price_action.nasdaq_poc_asymmetric_runner import (
    AsymmetricRunnerConfig,
    signal_context_mask,
    simulate_runner_signals,
)
from price_action.nasdaq_session_backtest import NasdaqExecutionCosts


def _bars(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    index = pd.date_range("2025-01-02 14:30", periods=len(rows), freq="min", tz="UTC")
    frame = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=index)
    frame["volume"] = 100.0
    frame["atr"] = 10.0
    frame["bar_id"] = np.arange(len(frame))
    return frame


def _signals(bars: pd.DataFrame, bar_ids: list[int], *, completed_range: float = 40.0) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "timestamp": bars.index[bar_id],
            "session_date": "2025-01-02",
            "session_close": bars.index[-1] + pd.Timedelta(minutes=1),
            "side": 1,
            "bar_id": bar_id,
            "atr": float(bars.iloc[bar_id]["atr"]),
            "completed_15m_range": completed_range,
            "crossed_poc": 95.0,
            "zone_half_width": 1.0,
        }
        for bar_id in bar_ids
    ])


def _auction_state(bars: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "session_date": "2025-01-02",
            "session_vwap": 95.0,
            "developing_poc": 95.0,
        },
        index=bars.index,
    )


class NasdaqPocAsymmetricRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.execution = NasdaqExecutionCosts(commission_bps=0.0, slippage_bps=0.0)
        self.config = AsymmetricRunnerConfig()

    def test_context_requires_acceptance_composite_poc_and_migration(self) -> None:
        observations = pd.DataFrame({
            "mode": ["one_minute_acceptance"] * 3,
            "crossed_sources": ["3d", "1d", "5d"],
            "completed_15m_range": [20.0, 20.0, 20.0],
            "daily_poc_migration_aligned": [True, True, False],
            "trend_3d_10d_aligned": [True, True, True],
            "minutes_from_open": [20, 20, 20],
        })

        mask = signal_context_mask(observations, "migration_trend_rth")

        self.assertEqual(mask.tolist(), [True, False, False])

    def test_same_bar_stop_wins_over_two_r_target(self) -> None:
        bars = _bars([
            (100.0, 101.0, 99.0, 100.0),
            (100.0, 121.0, 89.0, 110.0),
        ])

        trades = simulate_runner_signals(
            _signals(bars, [0]),
            bars,
            _auction_state(bars),
            self.execution,
            self.config,
            context="migration_rth",
            stop_spec="hybrid_0.25",
            scratch_bars=0,
            maximum_holding_minutes=30,
            management_spec="full_2r",
        )

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades.iloc[0]["exit_reason"], "stop")
        self.assertAlmostEqual(trades.iloc[0]["gross_r"], -1.0)

    def test_half_at_two_r_and_half_at_six_r_realizes_four_r(self) -> None:
        bars = _bars([
            (100.0, 101.0, 99.0, 100.0),
            (100.0, 121.0, 99.0, 118.0),
            (118.0, 161.0, 105.0, 160.0),
        ])

        trades = simulate_runner_signals(
            _signals(bars, [0]),
            bars,
            _auction_state(bars),
            self.execution,
            self.config,
            context="migration_rth",
            stop_spec="hybrid_0.25",
            scratch_bars=0,
            maximum_holding_minutes=30,
            management_spec="partial_2r_to_6r",
        )

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades.iloc[0]["exit_reason"], "partial_2r+runner_target_6r")
        self.assertAlmostEqual(trades.iloc[0]["gross_r"], 4.0)

    def test_position_is_flattened_before_session_boundary(self) -> None:
        bars = _bars([
            (100.0, 101.0, 99.0, 100.0),
            (100.0, 105.0, 99.0, 104.0),
            (104.0, 106.0, 103.0, 105.0),
        ])

        trades = simulate_runner_signals(
            _signals(bars, [0]),
            bars,
            _auction_state(bars),
            self.execution,
            self.config,
            context="migration_rth",
            stop_spec="hybrid_0.25",
            scratch_bars=0,
            maximum_holding_minutes=60,
            management_spec="full_6r",
        )

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades.iloc[0]["exit_reason"], "session_close")
        self.assertLess(trades.iloc[0]["exit_time"], bars.index[-1] + pd.Timedelta(minutes=1))


if __name__ == "__main__":
    unittest.main()
