from __future__ import annotations

import unittest

import pandas as pd

from price_action.btc_fabio_pine_v6_backtest import build_seven_day_schedule


class BtcFabioPineBacktestTests(unittest.TestCase):
    def test_schedule_includes_weekends(self) -> None:
        index = pd.date_range("2025-01-03", "2025-01-06", freq="5min", tz="UTC")
        schedule = build_seven_day_schedule(index, "UTC")
        self.assertEqual(schedule["session_date"].tolist(), [
            "2025-01-03", "2025-01-04", "2025-01-05", "2025-01-06"
        ])

    def test_new_york_schedule_observes_dst(self) -> None:
        index = pd.date_range("2025-03-08", "2025-03-10 23:55", freq="5min", tz="UTC")
        schedule = build_seven_day_schedule(index, "America/New_York").set_index("session_date")
        self.assertEqual(schedule.loc["2025-03-08", "session_open"].hour, 14)
        self.assertEqual(schedule.loc["2025-03-10", "session_open"].hour, 13)


if __name__ == "__main__":
    unittest.main()
