from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from price_action.btc_fabio_donchian_backtest import (
    attach_donchian_state,
    build_donchian_context,
)


def synthetic_five_minute_bars() -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=22 * 3, freq="5min", tz="UTC")
    group = np.repeat(np.arange(22), 3)
    close = np.full(len(index), 99.5)
    high = np.full(len(index), 100.0)
    low = np.full(len(index), 99.0)
    close[group == 20] = 101.0
    high[group == 20] = 101.0
    close[group == 21] = 98.0
    low[group == 21] = 98.0
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": 1.0},
        index=index,
    )


class BtcFabioDonchianTests(unittest.TestCase):
    def test_channel_excludes_current_higher_timeframe_bar(self) -> None:
        context = build_donchian_context(
            synthetic_five_minute_bars(), timeframe_minutes=15, length=20
        )
        long_breakout = context.iloc[20]
        short_breakout = context.iloc[21]
        self.assertAlmostEqual(long_breakout["channel_upper"], 100.0)
        self.assertEqual(long_breakout["donchian_state"], 1)
        self.assertAlmostEqual(short_breakout["channel_lower"], 99.0)
        self.assertEqual(short_breakout["donchian_state"], -1)

    def test_state_is_not_available_before_higher_bar_close(self) -> None:
        context = build_donchian_context(
            synthetic_five_minute_bars(), timeframe_minutes=15, length=20
        )
        breakout_available = pd.Timestamp(context.iloc[20]["available_time"])
        signals = pd.DataFrame(
            [
                {"signal_time": breakout_available - pd.Timedelta(minutes=5), "signal_bar_id": 1, "side": 1},
                {"signal_time": breakout_available, "signal_bar_id": 2, "side": 1},
            ]
        )
        attached = attach_donchian_state(signals, context)
        self.assertEqual(attached.iloc[0]["donchian_state"], 0)
        self.assertFalse(attached.iloc[0]["donchian_aligned"])
        self.assertEqual(attached.iloc[1]["donchian_state"], 1)
        self.assertTrue(attached.iloc[1]["donchian_aligned"])

    def test_future_mutation_does_not_change_prior_context(self) -> None:
        bars = synthetic_five_minute_bars()
        expected = build_donchian_context(bars, timeframe_minutes=15, length=20)
        mutated = bars.copy()
        mutated.iloc[-3:, mutated.columns.get_loc("high")] = 1_000_000.0
        actual = build_donchian_context(mutated, timeframe_minutes=15, length=20)
        columns = ["channel_upper", "channel_lower", "donchian_state"]
        pd.testing.assert_frame_equal(expected.iloc[:-1][columns], actual.iloc[:-1][columns])


if __name__ == "__main__":
    unittest.main()
