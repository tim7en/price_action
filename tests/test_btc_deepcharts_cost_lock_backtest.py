from __future__ import annotations

import unittest

from price_action.btc_deepcharts_cost_lock_backtest import _walk_cost_lock_trade_bar


class BtcDeepChartsCostLockTests(unittest.TestCase):
    def test_long_trail_ratchets_above_lock_floor(self) -> None:
        exit_price, reason, active, extreme = _walk_cost_lock_trade_bar(
            side=1,
            entry_price=100.0,
            stop=98.0,
            target=105.0,
            trail_offset=0.5,
            path=[100.0, 101.5, 100.0, 101.0],
            trail_active=False,
            favorable_extreme=100.0,
            lock_floor=100.14,
            lock_activation=100.64,
        )
        self.assertTrue(active)
        self.assertEqual(reason, "cost_lock_trailing_stop")
        self.assertAlmostEqual(float(exit_price), 101.0)
        self.assertAlmostEqual(extreme, 101.5)

    def test_short_trail_ratchets_below_lock_floor(self) -> None:
        exit_price, reason, active, extreme = _walk_cost_lock_trade_bar(
            side=-1,
            entry_price=100.0,
            stop=102.0,
            target=95.0,
            trail_offset=0.5,
            path=[100.0, 98.5, 100.0, 99.0],
            trail_active=False,
            favorable_extreme=100.0,
            lock_floor=99.86,
            lock_activation=99.36,
        )
        self.assertTrue(active)
        self.assertEqual(reason, "cost_lock_trailing_stop")
        self.assertAlmostEqual(float(exit_price), 99.0)
        self.assertAlmostEqual(extreme, 98.5)

    def test_gap_uses_open_instead_of_assuming_floor_fill(self) -> None:
        exit_price, reason, active, _ = _walk_cost_lock_trade_bar(
            side=1,
            entry_price=100.0,
            stop=98.0,
            target=105.0,
            trail_offset=0.5,
            path=[99.5, 100.0, 99.0, 99.8],
            trail_active=True,
            favorable_extreme=101.0,
            lock_floor=100.14,
            lock_activation=100.64,
        )
        self.assertTrue(active)
        self.assertEqual(reason, "cost_lock_trailing_gap")
        self.assertAlmostEqual(float(exit_price), 99.5)


if __name__ == "__main__":
    unittest.main()
