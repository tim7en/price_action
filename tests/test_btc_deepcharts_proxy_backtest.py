from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from price_action.btc_deepcharts_proxy_backtest import (
    DeepChartsProxyConfig,
    build_five_minute_features_proxy,
    build_session_context_proxy,
    proxy_account_path,
    session_volume_profile_proxy,
)
from price_action.btc_fabio_pine_v6_backtest import build_seven_day_schedule


def synthetic_bars(days: int = 24) -> pd.DataFrame:
    pieces: list[pd.DataFrame] = []
    for day in pd.date_range("2025-01-01", periods=days, freq="D", tz="UTC"):
        index = pd.date_range(day + pd.Timedelta(hours=9, minutes=30), periods=78, freq="5min")
        step = np.arange(len(index), dtype=float)
        base = 100.0 + float((day - pd.Timestamp("2025-01-01", tz="UTC")).days)
        close = base + 0.02 * step
        pieces.append(
            pd.DataFrame(
                {
                    "open": close - 0.01,
                    "high": close + 0.10,
                    "low": close - 0.10,
                    "close": close,
                    "volume": 10.0 + step,
                },
                index=index,
            )
        )
    return pd.concat(pieces)


class BtcDeepChartsProxyTests(unittest.TestCase):
    def test_profile_allocations_conserve_volume(self) -> None:
        bars = synthetic_bars(days=1)
        expected = float(bars["volume"].sum())
        for allocation in ("close", "uniform_range"):
            profile = session_volume_profile_proxy(
                bars, bins=24, value_area_fraction=0.70, allocation=allocation
            )
            self.assertAlmostEqual(profile["allocated_volume"], expected, places=8)
            self.assertLessEqual(profile["val"], profile["poc"])
            self.assertLessEqual(profile["poc"], profile["vah"])

    def test_profiles_and_ivb_are_shifted_to_prior_sessions(self) -> None:
        bars = synthetic_bars()
        schedule = build_seven_day_schedule(bars.index, "UTC")
        config = DeepChartsProxyConfig(ivb_minimum_sessions=3, ivb_lookback_sessions=5)
        context = build_session_context_proxy(bars, schedule, config)
        self.assertTrue(pd.isna(context.iloc[0]["prior_profile_uniform_poc_proxy"]))
        self.assertAlmostEqual(
            context.iloc[1]["prior_profile_uniform_poc_proxy"],
            context.iloc[0]["profile_uniform_poc_observed"],
        )
        self.assertEqual(
            context.iloc[1]["ivb_latest_observation_time"],
            context.iloc[0]["available_time"],
        )
        self.assertTrue(pd.isna(context.iloc[2]["ivb_upper_q50_proxy"]))
        self.assertTrue(np.isfinite(context.iloc[3]["ivb_upper_q50_proxy"]))

    def test_exact_orb_is_unavailable_until_six_bars_complete(self) -> None:
        bars = synthetic_bars(days=2)
        schedule = build_seven_day_schedule(bars.index, "UTC")
        config = DeepChartsProxyConfig(ivb_minimum_sessions=1)
        context = build_session_context_proxy(bars, schedule, config)
        features = build_five_minute_features_proxy(bars, schedule, context, config)
        first = features.loc[features["session_date"].eq("2025-01-01")]
        self.assertFalse(first.iloc[:6]["orb_defined_proxy"].any())
        self.assertTrue(first.iloc[6:]["orb_defined_proxy"].all())
        expected_high = float(first.iloc[:6]["high"].max())
        self.assertAlmostEqual(float(first.iloc[6]["orb_high_proxy"]), expected_high)

    def test_future_mutation_does_not_change_completed_session_context(self) -> None:
        bars = synthetic_bars()
        schedule = build_seven_day_schedule(bars.index, "UTC")
        config = DeepChartsProxyConfig(ivb_minimum_sessions=3, ivb_lookback_sessions=5)
        expected = build_session_context_proxy(bars, schedule, config)
        mutated = bars.copy()
        final_day = mutated.index.normalize().max()
        mutated.loc[mutated.index.normalize() == final_day, "high"] = 1_000_000.0
        actual = build_session_context_proxy(mutated, schedule, config)
        columns = [
            "profile_uniform_poc_observed",
            "prior_profile_uniform_poc_proxy",
            "ivb_upper_q50_proxy",
        ]
        pd.testing.assert_frame_equal(expected.iloc[:-1][columns], actual.iloc[:-1][columns])

    def test_risk_sizing_hits_target_without_leverage_cap(self) -> None:
        trades = pd.DataFrame(
            [
                {
                    "session_date": "2025-01-01",
                    "setup": "orb_proxy",
                    "entry_time": pd.Timestamp("2025-01-01 10:05", tz="UTC"),
                    "exit_time": pd.Timestamp("2025-01-01 10:10", tz="UTC"),
                    "initial_stop_fraction": 0.01,
                    "signed_price_return": 0.02,
                }
            ]
        )
        config = DeepChartsProxyConfig()
        path, diagnostics = proxy_account_path(
            trades,
            sizing_variant="risk_025pct_cap3x",
            one_way_cost_bps=0.0,
            config=config,
        )
        self.assertAlmostEqual(float(path.iloc[0]["effective_leverage"]), 0.25)
        self.assertAlmostEqual(float(path.iloc[0]["risk_fraction_deployed"]), 0.0025)
        self.assertEqual(diagnostics["trades_blocked_by_daily_halt_all_history"], 0)


if __name__ == "__main__":
    unittest.main()
