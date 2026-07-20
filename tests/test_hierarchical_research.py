from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from price_action.hierarchical_research import (
    _company_price_features,
    _evaluation_fold,
    _forward_trade_frame,
    _role_for_column,
)
from price_action.final_hierarchy import (
    _classification_reliability,
    _capped_budget,
    _feasible_side_budgets,
    _regression_model_weights,
    _regression_reliability,
    join_positioning,
)
from price_action.quality_engine import FWD_DAYS


class HierarchicalResearchContractTests(unittest.TestCase):
    def test_forward_target_enters_strictly_after_signal(self) -> None:
        index = pd.bdate_range("2020-01-02", periods=FWD_DAYS + 3)
        price = pd.Series(np.arange(1.0, len(index) + 1.0), index=index)
        signal = pd.DatetimeIndex([index[0]])

        result = _forward_trade_frame(price, signal).iloc[0]

        self.assertEqual(result["entry_date"], index[1])
        self.assertEqual(result["target_end_date"], index[1 + FWD_DAYS])
        self.assertAlmostEqual(result["return"], price.iloc[1 + FWD_DAYS] / price.iloc[1] - 1.0)

    def test_company_residual_requires_matching_benchmark_window(self) -> None:
        stock_index = pd.bdate_range("2000-01-03", periods=500)
        parent_index = stock_index.delete(50)
        stock = pd.Series(np.linspace(100.0, 150.0, len(stock_index)), index=stock_index)
        parent = pd.Series(np.linspace(100.0, 130.0, len(parent_index)), index=parent_index)
        dates = pd.DatetimeIndex([stock_index[1]])

        result = _company_price_features(stock=stock, parent=parent, dates=dates).iloc[0]

        self.assertNotEqual(result["company_target_end_date"], result["parent_target_end_date"])
        self.assertTrue(pd.isna(result["target_company_residual_6m"]))

    def test_feature_roles_exclude_targets_and_provenance(self) -> None:
        self.assertEqual(_role_for_column("sector", "fwd_6m_excess"), "target")
        self.assertEqual(_role_for_column("company", "target_company_residual_6m"), "target")
        self.assertEqual(_role_for_column("sector", "price_source"), "metadata")
        self.assertEqual(_role_for_column("macro", "gmm_regime"), "metadata")

    def test_evaluation_fold_preserves_initial_training_and_holdout(self) -> None:
        dates = pd.Series(pd.to_datetime(["2017-12-31", "2018-01-31", "2025-01-31"]))

        result = _evaluation_fold(dates, 2018, pd.Timestamp("2025-01-01"))

        self.assertEqual(result.tolist(), ["initial_training", "validation_2018", "holdout"])

    def test_cftc_join_never_uses_a_future_release(self) -> None:
        frame = pd.DataFrame({"date": pd.to_datetime(["2020-01-05", "2020-01-12"])})
        positioning = pd.DataFrame(
            {"cot_signal": [1.0, 2.0], "cot_usable_date": pd.to_datetime(["2020-01-01", "2020-01-10"])}
        ).set_index("cot_usable_date", drop=False)

        result = join_positioning(frame, positioning)

        self.assertEqual(result["cot_signal"].tolist(), [1.0, 2.0])
        self.assertTrue((result["cot_age_days"] >= 0).all())

    def test_ic_weighting_excludes_negative_model(self) -> None:
        rows = []
        for date in pd.date_range("2020-01-31", periods=24, freq="ME"):
            for sector, target in zip("ABCD", [-0.2, -0.1, 0.1, 0.2], strict=True):
                rows.append({
                    "date": date,
                    "sector": sector,
                    "target": target,
                    "pred_ridge": -target,
                    "pred_extra_trees": target,
                    "pred_hist_gradient": target * 0.8,
                })
        weights = _regression_model_weights(pd.DataFrame(rows), ["date"])

        self.assertEqual(weights["ridge"], 0.0)
        self.assertAlmostEqual(weights["extra_trees"] + weights["hist_gradient"], 1.0)

    def test_regression_reliability_uses_rank_and_spread_evidence(self) -> None:
        metrics = pd.DataFrame([{
            "scope": "validation",
            "avg_cross_sectional_rank_ic": 0.05,
            "rank_ic_tstat_nonoverlap": 2.0,
            "avg_top_minus_bottom": 0.025,
            "spread_tstat_nonoverlap": 2.0,
        }])

        self.assertAlmostEqual(_regression_reliability(metrics), 0.5)

        metrics.loc[0, "spread_tstat_nonoverlap"] = -2.0
        self.assertAlmostEqual(_regression_reliability(metrics), 0.25)

    def test_classification_reliability_requires_calibrated_probability_skill(self) -> None:
        uncalibrated = pd.DataFrame([{
            "scope": "validation",
            "balanced_accuracy": 0.60,
            "log_loss_skill": -0.10,
            "brier_skill": 0.05,
        }])
        calibrated = uncalibrated.copy()
        calibrated.loc[0, ["log_loss_skill", "brier_skill"]] = [0.20, 0.10]

        self.assertEqual(_classification_reliability(uncalibrated, 5), 0.0)
        self.assertGreater(_classification_reliability(calibrated, 5), 0.0)

    def test_shared_sector_cap_includes_existing_book(self) -> None:
        scores = pd.Series([2.0, 1.0], index=[0, 1])
        sectors = pd.Series(["Technology", "Financials"], index=[0, 1])

        weights = _capped_budget(
            scores,
            sectors,
            0.20,
            max_position=0.10,
            max_sector=0.20,
            existing_sector_usage={"Technology": 0.15},
        )

        self.assertLessEqual(weights.loc[0] + 0.15, 0.20 + 1e-12)
        self.assertLessEqual(weights.max(), 0.10 + 1e-12)

    def test_side_budgets_do_not_deploy_unmatched_gross(self) -> None:
        long_budget, short_budget, feasible_net = _feasible_side_budgets(
            gross_budget=0.70,
            net_budget=0.02,
            long_capacity=0.35,
            short_capacity=0.0,
        )

        self.assertAlmostEqual(long_budget, 0.02)
        self.assertEqual(short_budget, 0.0)
        self.assertAlmostEqual(long_budget - short_budget, feasible_net)


if __name__ == "__main__":
    unittest.main()
