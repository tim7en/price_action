from __future__ import annotations

import numpy as np
import pandas as pd

from price_action.nasdaq_poc_small_account_scenario import simulate_equity


def sample_trades() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "entry_time": pd.to_datetime(
                ["2025-01-02 15:00Z", "2025-01-03 15:00Z"], utc=True
            ),
            "exit_time": pd.to_datetime(
                ["2025-01-02 15:05Z", "2025-01-03 15:05Z"], utc=True
            ),
            "session_date": ["2025-01-02", "2025-01-03"],
            "side": ["long", "short"],
            "hierarchy_score": [3, 4],
            "entry_price": [20_000.0, 20_000.0],
            "stop_fraction": [0.002, 0.0005],
            "signed_price_return": [0.002, -0.0005],
        }
    )


def test_two_percent_risk_is_capped_by_twenty_times_leverage() -> None:
    path = simulate_equity(sample_trades(), one_way_cost_bps=0.0)
    assert np.allclose(path["effective_leverage"], [10.0, 20.0])
    assert np.allclose(path["deployed_stop_risk_fraction"], [0.02, 0.01])
    assert path["leverage_cap_bound"].tolist() == [False, True]


def test_equity_compounds_after_costs() -> None:
    path = simulate_equity(sample_trades(), one_way_cost_bps=0.5)
    expected_first_return = 10.0 * 0.002 - 10.0 * 2.0 * 0.5 / 10_000.0
    expected_second_return = 20.0 * -0.0005 - 20.0 * 2.0 * 0.5 / 10_000.0
    expected = 100.0 * (1.0 + expected_first_return) * (1.0 + expected_second_return)
    assert np.isclose(path["equity_after"].iloc[-1], expected)
