from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from price_action.nasdaq_fabio_description_backtest import (
    FabioProxyConfig,
    account_path,
    simulate_signal,
    volume_profile_levels,
)


class NasdaqFabioDescriptionBacktestTests(unittest.TestCase):
    def test_profile_uses_only_supplied_history(self) -> None:
        history = pd.DataFrame({
            "high": np.linspace(101.0, 110.0, 50),
            "low": np.linspace(99.0, 108.0, 50),
            "close": np.linspace(100.0, 109.0, 50),
            "volume": np.linspace(10.0, 100.0, 50),
        })
        future = pd.DataFrame({"high": [1_001.0], "low": [999.0], "close": [1_000.0], "volume": [1e6]})

        expected = volume_profile_levels(history)
        actual = volume_profile_levels(pd.concat([history, future]).iloc[:-1])

        self.assertEqual(expected, actual)

    def test_same_bar_stop_and_target_resolves_to_stop(self) -> None:
        index = pd.date_range("2025-01-02 14:30", periods=3, freq="min", tz="UTC")
        bars = pd.DataFrame({
            "open": [100.0, 100.0, 100.0],
            "high": [101.0, 130.0, 101.0],
            "low": [99.0, 80.0, 99.0],
            "close": [100.0, 105.0, 100.0],
        }, index=index)
        signal = pd.Series({
            "bar_minutes": 1,
            "bar_id": 0,
            "signal_time": index[0],
            "session_close": index[-1] + pd.Timedelta(minutes=1),
            "session_date": "2025-01-02",
            "setup": "triple_a",
            "side": 1,
            "atr": 10.0,
        })

        trade = simulate_signal(signal, bars, FabioProxyConfig())

        self.assertIsNotNone(trade)
        self.assertEqual(trade["exit_reason"], "stop")
        self.assertAlmostEqual(trade["gross_r"], -1.0)

    def test_account_cost_is_charged_on_round_trip_notional(self) -> None:
        trades = pd.DataFrame([{
            "bar_minutes": 1,
            "entry_time": pd.Timestamp("2025-01-02 14:31", tz="UTC"),
            "session_date": "2025-01-02",
            "setup": "opening_range_breakout",
            "stop_fraction": 0.01,
            "signed_price_return": 0.02,
        }])

        path = account_path(trades, FabioProxyConfig(), one_way_cost_bps=1.0)

        self.assertAlmostEqual(path.iloc[0]["effective_leverage"], 0.25)
        self.assertAlmostEqual(path.iloc[0]["gross_return"], 0.005)
        self.assertAlmostEqual(path.iloc[0]["execution_cost"], 0.00005)
        self.assertAlmostEqual(path.iloc[0]["net_return"], 0.00495)


if __name__ == "__main__":
    unittest.main()
