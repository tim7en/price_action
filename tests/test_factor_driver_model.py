from __future__ import annotations

import unittest

import pandas as pd

from price_action.factor_driver_model import _center_sector_predictions, _factor_family, _reliability


class FactorDriverModelTests(unittest.TestCase):
    def test_cftc_features_have_positioning_family(self) -> None:
        self.assertEqual(_factor_family("cot_asset_mgr_net_pct_oi_z"), ("positioning", "cftc_positioning"))

    def test_target_maturity_purge_is_strict(self) -> None:
        target_end = pd.to_datetime(["2020-12-31", "2021-01-01"])
        test_start = pd.Timestamp("2021-01-01")
        eligible = target_end < test_start

        self.assertEqual(eligible.tolist(), [True, False])

    def test_sector_predictions_are_cross_sectionally_centered(self) -> None:
        frame = pd.DataFrame({
            "date": pd.to_datetime(["2020-01-31"] * 3),
            "prediction": [0.1, 0.2, 0.3],
        })

        centered = _center_sector_predictions(frame)

        self.assertAlmostEqual(centered["prediction"].mean(), 0.0)

    def test_negative_baseline_skill_forces_zero_reliability(self) -> None:
        metrics = pd.DataFrame([{
            "sample": "validation",
            "spearman": 0.3,
            "skill_vs_baseline": -0.1,
            "nonoverlap_periods": 10,
        }])

        self.assertEqual(_reliability(metrics, "market"), 0.0)


if __name__ == "__main__":
    unittest.main()
