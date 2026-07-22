from __future__ import annotations

import unittest

import pandas as pd

from price_action.nasdaq_poc_leverage_optimizer import (
    PocLeverageOptimizerConfig,
    _signal_mask,
    deployment_gate,
    parameter_stability_audit,
)
from price_action.nasdaq_session_backtest import NasdaqExecutionCosts


class NasdaqPocLeverageOptimizerTests(unittest.TestCase):
    def test_invalid_fixed_leverage_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PocLeverageOptimizerConfig(fixed_leverage_levels=(1.0,))

    def test_signal_mask_combines_poc_timeline_and_context(self) -> None:
        observations = pd.DataFrame({
            "mode": ["one_minute_acceptance", "one_minute_acceptance"],
            "completed_15m_range": [40.0, 40.0],
            "crossed_sources": ["3d", "1d"],
            "focus_cluster_count": [1, 2],
            "minutes_from_open": [20, 35],
            "daily_poc_migration_aligned": [True, True],
            "trend_3d_10d_aligned": [True, False],
            "trend_10d_30d_aligned": [False, True],
        })

        mask = _signal_mask(
            observations,
            "3d_or_5d",
            "opening_15_30m",
            "trend_3d_10d_plus_migration",
        )

        self.assertEqual(mask.tolist(), [True, False])

    def test_stability_audit_requires_breadth_and_marks_evaluation_use(self) -> None:
        common = {
            "poc_scope": "3d_or_5d",
            "timeline": "rth_15_330m",
            "context": "poc_migration",
            "stop_factor_15m": 0.5,
            "holding_minutes": 5,
            "max_drawdown": -0.02,
            "net_profit_factor": 1.4,
            "average_effective_leverage": 8.0,
        }
        grid = pd.DataFrame([
            common | {
                "scope": "development_2024",
                "trades": 25,
                "cumulative_net_return": 0.06,
            },
            common | {
                "scope": "evaluation_2025",
                "trades": 22,
                "cumulative_net_return": 0.04,
            },
        ])

        audit = parameter_stability_audit(grid, minimum_trades=20)

        self.assertTrue(bool(audit.iloc[0]["positive_both_periods"]))
        self.assertTrue(bool(audit.iloc[0]["uses_evaluation_data"]))
        self.assertAlmostEqual(audit.iloc[0]["worst_period_return"], 0.04)
        self.assertGreater(audit.iloc[0]["diagnostic_stability_score"], 0.0)

    def test_gate_blocks_negative_binance_cost_stress(self) -> None:
        sensitivity = pd.DataFrame({
            "configured_binance_proxy": [True],
            "label": ["risk_targeted_20x"],
            "cumulative_net_return": [-0.2],
        })

        gate = deployment_gate(
            {"trades": 250, "cumulative_net_return": 0.05},
            {"instrument_identity": "verified"},
            NasdaqExecutionCosts(
                venue_and_contract_verified=True,
                historical_spread_supplied=True,
            ),
            sensitivity,
        )

        self.assertEqual(gate["status"], "BLOCKED")
        self.assertIn(
            "frozen candidate loses money under configured Binance costs",
            gate["reasons"],
        )


if __name__ == "__main__":
    unittest.main()
