from __future__ import annotations

import unittest

from price_action.execution_costs import (
    BinanceExecutionCosts,
    cash_carry,
    funding_cost,
    one_way_turnover,
    rebalance_cost,
)


class BinanceExecutionCostTests(unittest.TestCase):
    def test_turnover_counts_crossing_through_zero(self) -> None:
        turnover = one_way_turnover({"BTC": 0.20}, {"BTC": -0.10})
        self.assertAlmostEqual(turnover, 0.30)

    def test_rebalance_charges_commission_and_slippage_per_notional(self) -> None:
        execution = BinanceExecutionCosts(
            product="spot",
            maker_fee_bps=10.0,
            taker_fee_bps=10.0,
            slippage_bps=5.0,
        )
        turnover, cost = rebalance_cost({}, {"BTC": 0.50}, execution)
        self.assertAlmostEqual(turnover, 0.50)
        self.assertAlmostEqual(cost, 0.50 * 15.0 / 10_000.0)

    def test_spot_rejects_short_weights(self) -> None:
        execution = BinanceExecutionCosts(product="spot")
        with self.assertRaises(ValueError):
            rebalance_cost({}, {"BTC": -0.10}, execution)

    def test_positive_perp_funding_is_paid_by_longs_and_earned_by_shorts(self) -> None:
        execution = BinanceExecutionCosts(product="usd_m_perp", annual_funding_bps=1_000.0)
        long_cost = funding_cost({"BTC": 0.50}, 30.0, execution)
        short_cost = funding_cost({"BTC": -0.50}, 30.0, execution)
        self.assertGreater(long_cost, 0.0)
        self.assertAlmostEqual(short_cost, -long_cost)

    def test_idle_cash_earns_configured_carry(self) -> None:
        execution = BinanceExecutionCosts(product="spot", annual_cash_yield_bps=500.0)
        self.assertAlmostEqual(cash_carry(0.40, 365.25, execution), 0.60 * 0.05)


if __name__ == "__main__":
    unittest.main()
