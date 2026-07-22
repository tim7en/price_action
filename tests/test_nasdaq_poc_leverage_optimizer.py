from __future__ import annotations

import unittest

import pandas as pd

from price_action.nasdaq_poc_leverage_optimizer import (
    PocLeverageOptimizerConfig,
    _signal_mask,
)


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


if __name__ == "__main__":
    unittest.main()
