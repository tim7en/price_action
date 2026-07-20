from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from price_action.binance_session_scalper import (
    ScalperConfig,
    _simulate_trade,
    build_session_schedule,
    cost_sensitivity,
    run_backtest,
    volume_profile_levels,
)
from price_action.execution_costs import BinanceExecutionCosts


class BinanceSessionScalperTests(unittest.TestCase):
    def test_exchange_schedule_handles_dst_and_tokyo_close_extension(self) -> None:
        schedule = build_session_schedule(
            pd.Timestamp("2024-11-01", tz="UTC"),
            pd.Timestamp("2024-11-06", tz="UTC"),
        )
        opens = schedule.loc[schedule["phase"].eq("opening_first_30m")]
        ny = opens.loc[opens["market"].eq("New_York")].set_index("session_date")
        tokyo = schedule.loc[
            schedule["market"].eq("Tokyo") & schedule["phase"].eq("closing_last_30m")
        ].set_index("session_date")

        self.assertEqual(ny.loc["2024-11-01", "session_open"], pd.Timestamp("2024-11-01 13:30", tz="UTC"))
        self.assertEqual(ny.loc["2024-11-04", "session_open"], pd.Timestamp("2024-11-04 14:30", tz="UTC"))
        self.assertEqual(tokyo.loc["2024-11-01", "session_close"], pd.Timestamp("2024-11-01 06:00", tz="UTC"))
        self.assertEqual(tokyo.loc["2024-11-05", "session_close"], pd.Timestamp("2024-11-05 06:30", tz="UTC"))

    def test_volume_profile_uses_only_supplied_history(self) -> None:
        history = pd.DataFrame({
            "high": np.linspace(101.0, 110.0, 50),
            "low": np.linspace(99.0, 108.0, 50),
            "close": np.linspace(100.0, 109.0, 50),
            "volume": np.linspace(10.0, 100.0, 50),
        })
        future = pd.DataFrame({"high": [1_001.0], "low": [999.0], "close": [1_000.0], "volume": [1_000_000.0]})

        before = volume_profile_levels(history, rows=24, value_fraction=0.70)
        unchanged = volume_profile_levels(pd.concat([history, future]).iloc[:-1], rows=24, value_fraction=0.70)

        self.assertEqual(before, unchanged)

    def test_same_bar_stop_and_target_resolves_to_stop_after_next_bar_entry(self) -> None:
        index = pd.date_range("2025-01-02 14:30", periods=4, freq="5min", tz="UTC")
        bars = pd.DataFrame({
            "open": [100.0, 100.0, 100.0, 100.0],
            "high": [101.0, 130.0, 101.0, 101.0],
            "low": [99.0, 80.0, 99.0, 99.0],
            "close": [100.0, 105.0, 100.0, 100.0],
        }, index=index)
        signal = pd.Series({
            "bar_id": 0,
            "timestamp": index[0],
            "phase_end": index[-1] + pd.Timedelta(minutes=5),
            "signal_side": 1,
            "atr": 10.0,
            "market": "New_York",
            "session_date": "2025-01-02",
            "phase": "opening_first_30m",
            "setup": "triple_a",
        })

        trade = _simulate_trade(
            signal,
            bars,
            ScalperConfig(),
            BinanceExecutionCosts(
                product="usd_m_perp", maker_fee_bps=0.0, taker_fee_bps=0.0, slippage_bps=0.0
            ),
        )

        self.assertIsNotNone(trade)
        self.assertEqual(trade["entry_time"], index[1])
        self.assertEqual(trade["exit_reason"], "stop")
        self.assertEqual(trade["exit_price"], 90.0)

    def test_round_trip_cost_applies_to_entry_and_exit_notional(self) -> None:
        index = pd.date_range("2025-01-02 14:30", periods=3, freq="5min", tz="UTC")
        bars = pd.DataFrame({
            "open": [100.0, 100.0, 100.0],
            "high": [100.5, 100.5, 100.5],
            "low": [99.5, 99.5, 99.5],
            "close": [100.0, 100.0, 100.0],
        }, index=index)
        signal = pd.Series({
            "bar_id": 0,
            "timestamp": index[0],
            "phase_end": index[-1] + pd.Timedelta(minutes=5),
            "signal_side": 1,
            "atr": 1.0,
            "market": "New_York",
            "session_date": "2025-01-02",
            "phase": "opening_first_30m",
            "setup": "value_area_bounce",
        })

        trade = _simulate_trade(
            signal,
            bars,
            ScalperConfig(),
            BinanceExecutionCosts(
                product="usd_m_perp", maker_fee_bps=10.0, taker_fee_bps=10.0, slippage_bps=5.0
            ),
        )

        self.assertAlmostEqual(trade["notional_fraction"], 0.25)
        self.assertAlmostEqual(trade["one_way_turnover"], 0.50)
        self.assertAlmostEqual(trade["execution_cost"], 0.50 * 15.0 / 10_000.0)

    def test_one_percent_stop_risk_can_create_leveraged_notional(self) -> None:
        index = pd.date_range("2025-01-02 14:30", periods=3, freq="5min", tz="UTC")
        bars = pd.DataFrame({
            "open": [100.0, 100.0, 100.0],
            "high": [100.05, 100.05, 100.05],
            "low": [99.95, 99.95, 99.95],
            "close": [100.0, 100.0, 100.0],
        }, index=index)
        signal = pd.Series({
            "bar_id": 0,
            "timestamp": index[0],
            "phase_end": index[-1] + pd.Timedelta(minutes=5),
            "signal_side": 1,
            "atr": 0.20,
            "market": "New_York",
            "session_date": "2025-01-02",
            "phase": "opening_first_30m",
            "setup": "value_area_bounce",
        })

        trade = _simulate_trade(
            signal,
            bars,
            ScalperConfig(risk_fraction=0.01, max_notional_fraction=10.0),
            BinanceExecutionCosts(
                product="usd_m_perp", maker_fee_bps=0.0, taker_fee_bps=0.0, slippage_bps=0.0
            ),
        )

        self.assertAlmostEqual(trade["notional_fraction"], 5.0)
        self.assertAlmostEqual(trade["risk_fraction_deployed"], 0.01)

    def test_fourth_same_day_signal_is_blocked_after_three_losses(self) -> None:
        index = pd.date_range("2025-01-02 00:00", periods=10, freq="5min", tz="UTC")
        bars = pd.DataFrame({
            "open": 100.0,
            "high": 100.5,
            "low": [100.0, 98.0, 100.0, 98.0, 100.0, 98.0, 100.0, 98.0, 100.0, 98.0],
            "close": 100.0,
        }, index=index)
        signals = []
        for bar_id in [0, 2, 4, 6]:
            signals.append({
                "bar_id": bar_id,
                "timestamp": index[bar_id],
                "phase_end": index[-1] + pd.Timedelta(minutes=5),
                "signal_side": 1,
                "atr": 1.0,
                "market": "Tokyo",
                "session_date": "2025-01-02",
                "phase": "opening_first_30m",
                "setup": "triple_a",
            })
        config = ScalperConfig(maximum_one_trade_per_phase=False)

        trades, blocked = run_backtest(
            pd.DataFrame(signals),
            bars,
            config,
            BinanceExecutionCosts(
                product="usd_m_perp", maker_fee_bps=0.0, taker_fee_bps=0.0, slippage_bps=0.0
            ),
        )

        self.assertEqual(len(trades), 3)
        self.assertEqual(blocked["daily_loss_stop"], 1)

    def test_cost_sensitivity_keeps_holdout_setups_separate(self) -> None:
        trades = pd.DataFrame({
            "entry_time": ["2025-01-02T14:35:00Z", "2025-01-03T14:35:00Z"],
            "setup": ["opening_range_breakout", "value_area_bounce"],
            "gross_return": [0.01, -0.005],
            "one_way_turnover": [2.0, 1.0],
        })

        sensitivity = cost_sensitivity(trades)
        holdout_zero_cost = sensitivity.loc[
            sensitivity["scope"].eq("holdout_2025_plus")
            & sensitivity["one_way_cost_bps"].eq(0.0)
        ].set_index("setup")

        self.assertEqual(
            set(holdout_zero_cost.index),
            {"all", "opening_range_breakout", "value_area_bounce"},
        )
        self.assertEqual(holdout_zero_cost.loc["opening_range_breakout", "trades"], 1)
        self.assertAlmostEqual(
            holdout_zero_cost.loc["value_area_bounce", "cumulative_net_return"],
            -0.005,
        )


if __name__ == "__main__":
    unittest.main()
