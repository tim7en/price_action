from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from price_action.nasdaq_fabio_pine_v6_backtest import (
    PineFabioConfig,
    _walk_trade_bar,
    account_path,
    add_pine_indicators,
    inferred_path,
    pine_rma,
    pine_volume_profile,
    run_broker_emulator,
)


class PineFabioBacktestTests(unittest.TestCase):
    def test_rma_uses_sma_seed_then_wilder_updates(self) -> None:
        values = pd.Series([1.0, 2.0, 3.0, 6.0])
        actual = pine_rma(values, 3)
        self.assertTrue(actual.iloc[:2].isna().all())
        self.assertAlmostEqual(actual.iloc[2], 2.0)
        self.assertAlmostEqual(actual.iloc[3], 10.0 / 3.0)

    def test_profile_is_inclusive_and_future_invariant(self) -> None:
        config = PineFabioConfig(vp_length=3, vp_resolution=2)
        bars = pd.DataFrame(
            {
                "open": [1.0, 1.0, 1.0, 100.0],
                "high": [2.0, 3.0, 4.0, 101.0],
                "low": [0.0, 1.0, 2.0, 99.0],
                "close": [1.0, 2.0, 3.0, 100.0],
                "volume": [10.0, 20.0, 100.0, 1e9],
            }
        )
        expected = pine_volume_profile(bars, 2, config)
        bars.loc[3, ["high", "low", "close", "volume"]] = [10_001.0, 9_999.0, 10_000.0, 1e12]
        actual = pine_volume_profile(bars, 2, config)
        np.testing.assert_allclose(expected, actual)

    def test_orb_contains_31_one_minute_bars(self) -> None:
        index = pd.date_range("2025-01-02 14:30", periods=33, freq="min", tz="UTC")
        bars = pd.DataFrame(
            {
                "open": 100.0,
                "high": 100.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 100.0,
            },
            index=index,
        )
        bars.loc[index[31], ["high", "close"]] = [101.0, 101.0]
        schedule = pd.DataFrame(
            {
                "session_date": ["2025-01-02"],
                "session_open": [index[0]],
                "session_close": [index[-1] + pd.Timedelta(minutes=1)],
            }
        )
        indicated = add_pine_indicators(bars, schedule, PineFabioConfig())
        self.assertTrue(indicated.loc[index[30], "orb_defined"])
        self.assertFalse(indicated.loc[index[30], "orb_long"])
        self.assertTrue(indicated.loc[index[31], "orb_long"])

    def test_inferred_path_uses_open_proximity(self) -> None:
        self.assertEqual(inferred_path(100.0, 101.0, 95.0, 99.0), [100.0, 101.0, 95.0, 99.0])
        self.assertEqual(inferred_path(100.0, 105.0, 99.0, 101.0), [100.0, 99.0, 105.0, 101.0])

    def test_trailing_stop_activates_and_can_exit_on_same_bar(self) -> None:
        exit_price, reason, active, extreme = _walk_trade_bar(
            side=1,
            entry_price=100.0,
            stop=95.0,
            target=110.0,
            activation_distance=3.0,
            trail_offset=1.0,
            path=[100.0, 105.0, 99.0, 101.0],
            trail_active=False,
            favorable_extreme=100.0,
        )
        self.assertEqual(reason, "trailing_stop")
        self.assertAlmostEqual(exit_price, 104.0)
        self.assertTrue(active)
        self.assertAlmostEqual(extreme, 105.0)

    def test_market_entry_fills_next_bar_open(self) -> None:
        index = pd.date_range("2025-01-02 14:30", periods=2, freq="min", tz="UTC")
        indicated = pd.DataFrame(
            {
                "open": [99.0, 100.0],
                "high": [100.0, 105.0],
                "low": [98.0, 95.0],
                "close": [99.0, 100.0],
                "session_change": [True, False],
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
                    "static_stop": 98.0,
                    "static_target": 104.0,
                    "trail_activation_distance": 10.0,
                    "trail_offset": 1.0,
                }
            ]
        )
        trades, _ = run_broker_emulator(indicated, signals, PineFabioConfig())
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades.iloc[0]["entry_bar_id"], 1)
        self.assertAlmostEqual(trades.iloc[0]["entry_price"], 100.0)
        self.assertEqual(trades.iloc[0]["exit_reason"], "target")

    def test_script_and_intended_risk_sizing_are_separate(self) -> None:
        trades = pd.DataFrame(
            [
                {
                    "entry_time": pd.Timestamp("2025-01-02 14:31", tz="UTC"),
                    "exit_time": pd.Timestamp("2025-01-02 14:32", tz="UTC"),
                    "session_date": "2025-01-02",
                    "setup": "orb",
                    "signed_price_return": 0.02,
                    "initial_stop_fraction": 0.005,
                }
            ]
        )
        script = account_path(
            trades,
            variant="script_realistic_cost",
            one_way_cost_bps=0.5,
            config=PineFabioConfig(),
        )
        intended = account_path(
            trades,
            variant="intended_1pct_risk_capped_10x",
            one_way_cost_bps=0.5,
            config=PineFabioConfig(),
        )
        self.assertAlmostEqual(script.iloc[0]["effective_leverage"], 1.0)
        self.assertAlmostEqual(script.iloc[0]["net_return"], 0.0199)
        self.assertAlmostEqual(intended.iloc[0]["effective_leverage"], 2.0)


if __name__ == "__main__":
    unittest.main()
