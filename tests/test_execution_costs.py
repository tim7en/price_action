from __future__ import annotations

import unittest

import pandas as pd

from price_action.execution_costs import (
    BinanceExecutionCosts,
    cash_carry,
    funding_cost,
    one_way_turnover,
    rebalance_cost,
    simulate_rebalanced_portfolio,
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

    def test_portfolio_replay_executes_next_session_and_charges_exit(self) -> None:
        price_data = {
            "AAA": pd.Series(
                [100.0, 110.0, 121.0],
                index=pd.to_datetime(["2020-01-02", "2020-02-03", "2020-03-02"]),
            ),
            "SPY": pd.Series(
                [100.0, 100.0, 100.0],
                index=pd.to_datetime(["2020-01-02", "2020-02-03", "2020-03-02"]),
            ),
        }
        targets = pd.DataFrame({
            "date": pd.to_datetime(["2020-01-01", "2020-02-01"]),
            "symbol": ["AAA", "AAA"],
            "target_weight": [0.5, 0.5],
        })
        execution = BinanceExecutionCosts(
            product="spot", maker_fee_bps=10.0, taker_fee_bps=10.0, slippage_bps=5.0
        )

        periods, summary = simulate_rebalanced_portfolio(
            targets,
            pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01"]),
            lambda symbol: price_data[symbol],
            execution,
        )

        self.assertEqual(periods.loc[0, "period_start"], pd.Timestamp("2020-01-02"))
        self.assertGreater(periods["terminal_liquidation_cost"].iloc[-1], 0.0)
        self.assertLess(periods["net_equity"].iloc[-1], periods["gross_equity"].iloc[-1])
        self.assertEqual(summary["periods"], 2)

    def test_all_cash_replay_has_zero_costs(self) -> None:
        spy = pd.Series(
            [100.0, 101.0, 102.0],
            index=pd.to_datetime(["2020-01-02", "2020-02-03", "2020-03-02"]),
        )
        periods, summary = simulate_rebalanced_portfolio(
            pd.DataFrame(columns=["date", "symbol", "target_weight"]),
            pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01"]),
            lambda _symbol: spy,
            BinanceExecutionCosts(product="spot"),
        )

        self.assertTrue(periods["trade_cost"].eq(0.0).all())
        self.assertTrue(periods["net_return"].eq(0.0).all())
        self.assertEqual(summary["active_period_fraction"], 0.0)


if __name__ == "__main__":
    unittest.main()
