from __future__ import annotations

import unittest

import pandas as pd

from price_action.nasdaq_macro_poc_assessment import (
    AssessmentConfig,
    _trend_multiplier,
    add_intraday_confirmation,
    build_daily_market_context,
    simulate_fractional_account,
    strict_prior_join,
)


class NasdaqMacroPocAssessmentTests(unittest.TestCase):
    def test_strict_prior_join_excludes_same_day_context(self) -> None:
        trades = pd.DataFrame({"session": pd.to_datetime(["2025-01-02", "2025-01-03"])})
        context = pd.DataFrame({
            "date": pd.to_datetime(["2025-01-01", "2025-01-02"]),
            "value": [1, 2],
        })

        joined = strict_prior_join(trades, context, left_on="session", right_on="date")

        self.assertEqual(joined["value"].tolist(), [1, 2])

    def test_golden_cross_requires_two_percent_hysteresis(self) -> None:
        prices = [100.0] * 200 + [101.0] * 50 + [110.0] * 50
        frame = pd.DataFrame({
            "signal_date": pd.date_range("2024-01-01", periods=len(prices)),
            "spy_close": prices,
            "spot_vix_change_5d": 0.0,
            "high_yield_spread_change_5d": 0.0,
            "spy_trend_5d": 1.0,
            "risk_off_gate": False,
            "extreme_risk_off": False,
            "combined_regime": "Strong / Calm",
            "spot_vix": 15.0,
        })

        result = build_daily_market_context(frame)

        self.assertEqual(result.iloc[205]["golden_cross_state"], "neutral")
        self.assertEqual(result.iloc[-1]["golden_cross_state"], "up")

    def test_trend_multiplier_is_a_risk_governor(self) -> None:
        self.assertEqual(_trend_multiplier("aligned", "aligned"), 1.0)
        self.assertEqual(_trend_multiplier("opposed", "opposed"), 0.25)
        self.assertEqual(_trend_multiplier("aligned", "opposed"), 0.50)
        self.assertEqual(_trend_multiplier("neutral", "aligned"), 0.75)

    def test_intraday_confirmation_excludes_entry_bar(self) -> None:
        index = pd.date_range("2025-01-02 14:30", periods=6, freq="min", tz="UTC")
        bars = pd.DataFrame({
            "open": [100, 101, 102, 103, 104, 200],
            "high": [102, 103, 104, 105, 106, 201],
            "low": [99, 100, 101, 102, 103, 49],
            "close": [101, 102, 103, 104, 105, 50],
            "volume": [10, 10, 10, 10, 10, 10],
        }, index=index)
        trades = pd.DataFrame({
            "entry_time": [index[-1]],
            "side": ["long"],
        })

        result = add_intraday_confirmation(trades, bars)

        self.assertEqual(result.iloc[0]["two_minute_state"], "up")
        self.assertEqual(result.iloc[0]["five_minute_auction_state"], "up")
        self.assertEqual(result.iloc[0]["intraday_multiplier"], 1.0)

    def test_fractional_cost_is_round_trip_notional_cost(self) -> None:
        trades = pd.DataFrame([{
            "entry_time": pd.Timestamp("2025-01-02 15:00", tz="UTC"),
            "session_date": "2025-01-02",
            "side": "long",
            "stop_fraction": 0.01,
            "signed_price_return": 0.02,
            "macro_multiplier": 1.0,
            "trend_multiplier": 1.0,
            "shock_multiplier": 1.0,
            "combined_multiplier": 1.0,
        }])
        config = AssessmentConfig(base_risk_fraction=0.0025)

        path = simulate_fractional_account(
            trades,
            variant="fixed_0.25_no_overlays",
            one_way_cost_bps=1.0,
            config=config,
        )

        self.assertAlmostEqual(path.iloc[0]["effective_leverage"], 0.25)
        self.assertAlmostEqual(path.iloc[0]["gross_account_return"], 0.005)
        self.assertAlmostEqual(path.iloc[0]["cost_fraction"], 0.00005)
        self.assertAlmostEqual(path.iloc[0]["net_return"], 0.00495)


if __name__ == "__main__":
    unittest.main()
