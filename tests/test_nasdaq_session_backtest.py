from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from price_action.nasdaq_session_backtest import (
    NasdaqExecutionCosts,
    NasdaqStrategyConfig,
    add_indicators,
    build_ny_schedule,
    cost_sensitivity,
    load_nasdaq_bars,
    run_backtest,
    simulate_trade,
    volume_profile_levels,
)


class NasdaqSessionBacktestTests(unittest.TestCase):
    def test_loader_keeps_only_complete_five_minute_groups(self) -> None:
        index = pd.date_range("2025-01-02 14:30", periods=12, freq="1min", tz="UTC")
        frame = pd.DataFrame({
            "time": index,
            "open": 100.01,
            "high": 100.10,
            "low": 99.90,
            "close": 100.01,
            "volume": 2,
        })
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Nasdaq.csv"
            frame.to_csv(path, index=False)
            bars, audit = load_nasdaq_bars(path)

        self.assertEqual(len(bars), 2)
        self.assertEqual(bars.iloc[0]["volume"], 10)
        self.assertEqual(audit["incomplete_aggregate_groups_dropped"], 1)
        self.assertEqual(audit["close_not_on_nq_quarter_tick_share"], 1.0)

    def test_loader_builds_complete_two_minute_bars(self) -> None:
        index = pd.date_range("2025-01-02 14:30", periods=7, freq="1min", tz="UTC")
        frame = pd.DataFrame({
            "time": index,
            "open": range(100, 107),
            "high": range(101, 108),
            "low": range(99, 106),
            "close": range(100, 107),
            "volume": 2,
        })
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Nasdaq.csv"
            frame.to_csv(path, index=False)
            bars, audit = load_nasdaq_bars(path, bar_minutes=2)

        self.assertEqual(len(bars), 3)
        self.assertEqual(bars.iloc[0]["open"], 100)
        self.assertEqual(bars.iloc[0]["close"], 101)
        self.assertEqual(bars.iloc[0]["volume"], 4)
        self.assertEqual(audit["incomplete_aggregate_groups_dropped"], 1)

    def test_strict_absorption_requires_both_volume_and_range_tests(self) -> None:
        index = pd.date_range("2025-01-02", periods=52, freq="1min", tz="UTC")
        close = pd.Series([100.0] * 52, index=index)
        frame = pd.DataFrame({
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 10.0,
        }, index=index)
        frame.loc[index[-1], ["high", "low", "volume"]] = [100.05, 99.95, 100.0]

        indicated = add_indicators(frame, NasdaqStrategyConfig(bar_minutes=1))
        strict_bar = indicated.loc[index[-1]]

        self.assertTrue(strict_bar["absorption_volume_test"])
        self.assertTrue(strict_bar["absorption_range_test"])
        self.assertTrue(strict_bar["absorption_proxy"])

    def test_new_york_schedule_handles_dst(self) -> None:
        schedule = build_ny_schedule(
            pd.Timestamp("2024-11-01", tz="UTC"),
            pd.Timestamp("2024-11-05", tz="UTC"),
        ).set_index("session_date")

        self.assertEqual(
            schedule.loc["2024-11-01", "session_open"],
            pd.Timestamp("2024-11-01 13:30", tz="UTC"),
        )
        self.assertEqual(
            schedule.loc["2024-11-04", "session_open"],
            pd.Timestamp("2024-11-04 14:30", tz="UTC"),
        )

    def test_volume_profile_uses_only_supplied_history(self) -> None:
        history = pd.DataFrame({
            "high": [101.0, 102.0, 103.0, 104.0],
            "low": [99.0, 100.0, 101.0, 102.0],
            "close": [100.0, 101.0, 102.0, 103.0],
            "volume": [10.0, 20.0, 30.0, 40.0],
        })
        levels = volume_profile_levels(history, rows=8, value_fraction=0.70)
        future = pd.DataFrame({
            "high": [1_001.0], "low": [999.0], "close": [1_000.0], "volume": [1_000_000.0]
        })

        unchanged = volume_profile_levels(
            pd.concat([history, future]).iloc[:-1],
            rows=8,
            value_fraction=0.70,
        )
        self.assertEqual(levels, unchanged)

    def test_trade_enters_next_bar_and_resolves_ambiguous_bar_to_stop(self) -> None:
        index = pd.date_range("2025-01-02 15:00", periods=4, freq="5min", tz="UTC")
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
            "session_date": "2025-01-02",
            "phase": "opening_followthrough_30m",
            "day_regime": "imbalance_up",
            "setup": "imbalance_opening_range_breakout",
        })

        trade = simulate_trade(
            signal,
            bars,
            NasdaqStrategyConfig(),
            NasdaqExecutionCosts(commission_bps=0.0, slippage_bps=0.0),
        )

        self.assertIsNotNone(trade)
        self.assertEqual(trade["entry_time"], index[1])
        self.assertEqual(trade["exit_reason"], "stop")
        self.assertEqual(trade["exit_price"], 90.0)

    def test_one_percent_risk_uses_leverage_when_stop_is_tight(self) -> None:
        index = pd.date_range("2025-01-02 15:00", periods=3, freq="5min", tz="UTC")
        bars = pd.DataFrame({
            "open": 100.0,
            "high": 100.05,
            "low": 99.95,
            "close": 100.0,
        }, index=index)
        signal = pd.Series({
            "bar_id": 0,
            "timestamp": index[0],
            "phase_end": index[-1] + pd.Timedelta(minutes=5),
            "signal_side": 1,
            "atr": 0.20,
            "session_date": "2025-01-02",
            "phase": "opening_followthrough_30m",
            "day_regime": "imbalance_up",
            "setup": "imbalance_opening_range_breakout",
        })

        trade = simulate_trade(
            signal,
            bars,
            NasdaqStrategyConfig(risk_fraction=0.01, max_notional_fraction=10.0),
            NasdaqExecutionCosts(commission_bps=0.0, slippage_bps=0.0),
        )

        self.assertAlmostEqual(trade["notional_fraction"], 5.0)
        self.assertAlmostEqual(trade["risk_fraction_deployed"], 0.01)

    def test_fourth_signal_is_blocked_after_three_same_session_losses(self) -> None:
        index = pd.date_range("2025-01-02 15:00", periods=10, freq="5min", tz="UTC")
        bars = pd.DataFrame({
            "open": 100.0,
            "high": 100.5,
            "low": [100.0, 98.0, 100.0, 98.0, 100.0, 98.0, 100.0, 98.0, 100.0, 98.0],
            "close": 100.0,
        }, index=index)
        signals = pd.DataFrame([{
            "bar_id": bar_id,
            "timestamp": index[bar_id],
            "phase_end": index[-1] + pd.Timedelta(minutes=5),
            "signal_side": 1,
            "atr": 1.0,
            "session_date": "2025-01-02",
            "phase": "opening_followthrough_30m",
            "day_regime": "imbalance_up",
            "setup": "imbalance_opening_range_breakout",
        } for bar_id in [0, 2, 4, 6]])

        trades, blocked = run_backtest(
            signals,
            bars,
            NasdaqStrategyConfig(),
            NasdaqExecutionCosts(commission_bps=0.0, slippage_bps=0.0),
        )

        self.assertEqual(len(trades), 3)
        self.assertEqual(blocked["daily_loss_stop"], 1)

    def test_cost_sensitivity_reprices_both_sides_of_notional(self) -> None:
        trades = pd.DataFrame({
            "entry_time": ["2025-01-02T15:05:00Z"],
            "setup": ["imbalance_opening_range_breakout"],
            "gross_return": [0.01],
            "one_way_turnover": [4.0],
        })
        row = cost_sensitivity(trades).loc[
            lambda frame: frame["scope"].eq("holdout_2025")
            & frame["setup"].eq("all")
            & frame["one_way_cost_bps"].eq(0.5)
        ].iloc[0]

        self.assertAlmostEqual(row["cumulative_net_return"], 0.01 - 4.0 * 0.5 / 10_000.0)


if __name__ == "__main__":
    unittest.main()
