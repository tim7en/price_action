from __future__ import annotations

import unittest

from price_action.nasdaq_poc_scaling_backtest import (
    ManagedVariant,
    PocManagementConfig,
    crossed_prior_poc,
    financed_add_notional,
    short_trend_bias,
    trend_bias,
)


class NasdaqPocScalingBacktestTests(unittest.TestCase):
    def test_chart_scaling_requires_trailing_stop_and_exclusive_trigger(self) -> None:
        with self.assertRaises(ValueError):
            ManagedVariant("bad", 16, 16, chart_scaling=True)
        with self.assertRaises(ValueError):
            ManagedVariant(
                "bad",
                16,
                16,
                chart_scaling=True,
                poc_scaling=True,
                trailing_stop=True,
            )

    def test_trend_bias_requires_price_and_moving_average_ordering(self) -> None:
        self.assertEqual(trend_bias(110.0, 105.0, 100.0), 1)
        self.assertEqual(trend_bias(90.0, 95.0, 100.0), -1)
        self.assertEqual(trend_bias(102.0, 105.0, 100.0), 0)
        self.assertEqual(short_trend_bias(110.0, 105.0, 100.0), 1)
        self.assertEqual(short_trend_bias(90.0, 95.0, 100.0), -1)

    def test_poc_cross_requires_clearing_the_tolerance_band(self) -> None:
        levels = [100.0, 105.0, 110.0]

        self.assertEqual(crossed_prior_poc(99.0, 101.0, levels, 0.5, 1), 100.0)
        self.assertEqual(crossed_prior_poc(111.0, 109.0, levels, 0.5, -1), 110.0)
        self.assertIsNone(crossed_prior_poc(99.8, 100.2, levels, 0.5, 1))

    def test_add_on_risk_is_financed_by_locked_profit(self) -> None:
        management = PocManagementConfig(max_notional_fraction=10.0)
        add_notional, locked_profit = financed_add_notional(
            base_notional=4.0,
            base_entry=100.0,
            add_entry=101.0,
            protected_stop=100.25,
            side=1,
            cost_rate=0.0,
            management=management,
        )
        combined_stop_return = (
            4.0 * (100.25 / 100.0 - 1.0)
            + add_notional * (100.25 / 101.0 - 1.0)
        )

        self.assertGreater(add_notional, 0.0)
        self.assertAlmostEqual(locked_profit, 0.01)
        self.assertGreaterEqual(combined_stop_return, -1e-12)
        self.assertLessEqual(add_notional, management.max_add_fraction_of_base * 4.0)


if __name__ == "__main__":
    unittest.main()
