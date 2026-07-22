from __future__ import annotations

import unittest

import pandas as pd

from price_action.cross_asset_leverage_alignment_assessment import (
    classify_trade_outcomes,
    fixed_leverage_path,
)


def sample_trade(
    *,
    signed_return: float,
    reason: str,
    holding_bars: int,
) -> dict[str, object]:
    return {
        "signal_time": pd.Timestamp("2025-01-01 10:00", tz="UTC"),
        "entry_time": pd.Timestamp("2025-01-01 10:05", tz="UTC"),
        "exit_time": pd.Timestamp("2025-01-01 10:10", tz="UTC"),
        "session_date": "2025-01-01",
        "side": 1,
        "exit_reason": reason,
        "holding_bars": holding_bars,
        "signed_price_return": signed_return,
        "initial_stop_fraction": 0.01,
    }


class CrossAssetLeverageAlignmentTests(unittest.TestCase):
    def test_fixed_leverage_multiplies_return_and_cost(self) -> None:
        trades = pd.DataFrame(
            [sample_trade(signed_return=0.01, reason="trailing_stop", holding_bars=5)]
        )
        path, diagnostics = fixed_leverage_path(
            trades, leverage=20.0, one_way_cost_bps=5.0
        )
        self.assertAlmostEqual(float(path.iloc[0]["net_unlevered"]), 0.009)
        self.assertAlmostEqual(float(path.iloc[0]["net_levered"]), 0.18)
        self.assertAlmostEqual(diagnostics["terminal_equity"], 1.18)
        self.assertAlmostEqual(diagnostics["round_trip_cost_fraction_per_trade"], 0.02)

    def test_fixed_leverage_stops_at_account_wipeout(self) -> None:
        trades = pd.DataFrame(
            [
                sample_trade(signed_return=-0.03, reason="static_stop", holding_bars=1),
                sample_trade(signed_return=0.10, reason="target", holding_bars=5),
            ]
        )
        path, diagnostics = fixed_leverage_path(
            trades, leverage=40.0, one_way_cost_bps=0.0
        )
        self.assertEqual(len(path), 1)
        self.assertTrue(diagnostics["bankrupt"])
        self.assertEqual(diagnostics["terminal_equity"], 0.0)

    def test_outcome_definitions_are_cost_aware(self) -> None:
        trades = pd.DataFrame(
            [
                sample_trade(signed_return=0.002, reason="trailing_stop", holding_bars=5),
                sample_trade(signed_return=-0.001, reason="static_stop", holding_bars=2),
                sample_trade(signed_return=-0.001, reason="static_stop", holding_bars=8),
                sample_trade(signed_return=0.0005, reason="target", holding_bars=5),
            ]
        )
        actual = classify_trade_outcomes(trades, one_way_cost_bps=5.0)
        self.assertEqual(
            actual.tolist(),
            ["trend_lock", "fast_whipsaw", "slow_stop_failure", "other"],
        )


if __name__ == "__main__":
    unittest.main()
