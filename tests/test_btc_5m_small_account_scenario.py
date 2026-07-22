from __future__ import annotations

import pandas as pd

from price_action.btc_5m_small_account_scenario import _direction_path


def sample_btc_trades() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "entry_time": pd.to_datetime(
                ["2025-01-02 10:05Z", "2025-01-03 10:05Z"], utc=True
            ),
            "exit_time": pd.to_datetime(
                ["2025-01-02 10:10Z", "2025-01-03 10:10Z"], utc=True
            ),
            "session_date": ["2025-01-02", "2025-01-03"],
            "side": [1, -1],
            "hierarchy_score": [0, 0],
            "entry_price": [50_000.0, 50_000.0],
            "stop_fraction": [0.01, 0.01],
            "signed_price_return": [0.01, 0.01],
        }
    )


def test_direction_paths_include_the_requested_sides() -> None:
    trades = sample_btc_trades()
    both = _direction_path(
        trades,
        direction="both",
        starting_equity=100.0,
        risk_fraction=0.02,
        maximum_leverage=20.0,
        one_way_cost_bps=6.0,
    )
    long_only = _direction_path(
        trades,
        direction="long_only",
        starting_equity=100.0,
        risk_fraction=0.02,
        maximum_leverage=20.0,
        one_way_cost_bps=6.0,
    )
    short_only = _direction_path(
        trades,
        direction="short_only",
        starting_equity=100.0,
        risk_fraction=0.02,
        maximum_leverage=20.0,
        one_way_cost_bps=6.0,
    )
    assert len(both) == 2
    assert long_only["side"].tolist() == [1]
    assert short_only["side"].tolist() == [-1]
    assert both["effective_leverage"].tolist() == [2.0, 2.0]
