from __future__ import annotations

import unittest

import pandas as pd

from price_action.btc_deepcharts_cost_lock_backtest import run_cost_lock_broker_emulator
from price_action.nasdaq_fabio_pine_v6_backtest import PineFabioConfig


class NasdaqFabioCostLockTests(unittest.TestCase):
    def test_broker_builds_cost_floor_and_fills_next_open(self) -> None:
        index = pd.date_range("2025-01-02 14:30", periods=3, freq="min", tz="UTC")
        indicated = pd.DataFrame(
            {
                "open": [99.9, 100.0, 100.08],
                "high": [100.0, 100.10, 100.09],
                "low": [99.8, 100.00, 100.04],
                "close": [99.9, 100.10, 100.05],
                "session_change": [True, False, False],
            },
            index=index,
        )
        signals = pd.DataFrame(
            [
                {
                    "signal_time": index[0],
                    "signal_bar_id": 0,
                    "session_date": "2025-01-02",
                    "side": 1,
                    "setup": "orb",
                    "static_stop": 99.0,
                    "static_target": 102.0,
                    "trail_activation_distance": 1.5,
                    "trail_offset": 0.05,
                }
            ]
        )
        trades, _ = run_cost_lock_broker_emulator(
            indicated,
            signals,
            PineFabioConfig(maximum_daily_losses=99),
            one_way_cost_bps=0.50,
            locked_net_profit_bps=0.25,
        )
        self.assertEqual(len(trades), 1)
        trade = trades.iloc[0]
        self.assertEqual(trade["entry_bar_id"], 1)
        self.assertAlmostEqual(float(trade["entry_price"]), 100.0)
        self.assertAlmostEqual(float(trade["cost_lock_floor_price"]), 100.0125)
        self.assertAlmostEqual(float(trade["cost_lock_activation_price"]), 100.0625)
        self.assertEqual(trade["exit_reason"], "cost_lock_trailing_stop")
        self.assertGreaterEqual(float(trade["signed_price_return"]), 0.000125)


if __name__ == "__main__":
    unittest.main()
