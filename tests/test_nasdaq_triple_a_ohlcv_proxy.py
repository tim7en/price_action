from __future__ import annotations

import numpy as np
import pandas as pd

from price_action.nasdaq_triple_a_ohlcv_proxy import (
    TripleAProxyConfig,
    activate_stop_entries,
    build_equity_path,
    fit_development_thresholds,
)


def test_threshold_fit_excludes_2025_bars() -> None:
    index = pd.to_datetime(
        ["2024-01-02 15:00Z", "2024-01-02 15:01Z", "2025-01-02 15:00Z"],
        utc=True,
    )
    indicated = pd.DataFrame(
        {
            "volume_strength": [1.0, 2.0, 100.0],
            "down_excursion_atr": [0.5, 1.0, 100.0],
            "up_excursion_atr": [0.5, 1.0, 100.0],
        },
        index=index,
    )
    schedule = pd.DataFrame(
        {
            "session_date": ["2024-01-02", "2025-01-02"],
            "session_open": pd.to_datetime(
                ["2024-01-02 14:30Z", "2025-01-02 14:30Z"], utc=True
            ),
            "session_close": pd.to_datetime(
                ["2024-01-02 21:00Z", "2025-01-02 21:00Z"], utc=True
            ),
        }
    )
    thresholds = fit_development_thresholds(
        indicated, schedule, TripleAProxyConfig(threshold_quantile=0.5)
    )
    assert thresholds["volume_strength_minimum"] == 1.5
    assert thresholds["excursion_atr_minimum"] == 0.75
    assert pd.Timestamp(thresholds["fit_end_utc"]) < pd.Timestamp(
        "2025-01-01", tz="UTC"
    )


def test_same_bar_invalidation_cancels_stop_entry() -> None:
    index = pd.date_range("2025-01-02 15:00Z", periods=3, freq="min")
    indicated = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0],
            "high": [101.0, 102.0, 101.0],
            "low": [99.0, 98.0, 99.0],
            "close": [100.0, 100.0, 100.0],
        },
        index=index,
    )
    candidate = pd.DataFrame(
        [
                {
                    "signal_bar_id": 0,
                    "signal_available_time": pd.Timestamp("2025-01-02 15:01Z"),
                "session_close": pd.Timestamp("2025-01-02 21:00Z"),
                "side": 1,
                "trigger_price": 101.5,
                "initial_stop": 98.5,
                "target1": 104.0,
                "target2": 108.0,
            }
        ]
    )
    activated = activate_stop_entries(candidate, indicated, TripleAProxyConfig())
    assert activated.loc[0, "entry_status"] == "invalidated_before_entry"
    assert pd.isna(activated.loc[0, "entry_time"])


def test_equity_path_compounds_trade_returns() -> None:
    trades = pd.DataFrame(
        {
            "management": ["x", "x"],
            "session_date": ["2025-01-02", "2025-01-03"],
            "entry_time": pd.to_datetime(
                ["2025-01-02 15:00Z", "2025-01-03 15:00Z"], utc=True
            ),
            "exit_time": pd.to_datetime(
                ["2025-01-02 15:05Z", "2025-01-03 15:05Z"], utc=True
            ),
            "side": ["long", "long"],
            "net_account_return": [0.10, -0.05],
        }
    )
    path = build_equity_path(trades, 100.0)
    assert np.isclose(path["equity_after"].iloc[-1], 104.5)
