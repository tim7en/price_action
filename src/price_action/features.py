from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from .macro_context import MODEL_MACRO_CONTEXT_COLUMNS


def rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window=window, min_periods=window).mean()
    std = series.rolling(window=window, min_periods=window).std().replace(0.0, np.nan)
    return (series - mean) / std


def bounded_momentum_oscillator(close: pd.Series, window: int = 14) -> pd.Series:
    close = pd.to_numeric(close, errors="coerce")
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    average_gain = gain.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()
    average_loss = loss.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()
    rs = average_gain / average_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    rsi = rsi.mask((average_loss == 0.0) & (average_gain > 0.0), 100.0)
    rsi = rsi.mask((average_gain == 0.0) & (average_loss > 0.0), 0.0)
    rsi = rsi.mask((average_gain == 0.0) & (average_loss == 0.0), 50.0)

    oscillator = (rsi / 50.0 - 1.0).clip(lower=-1.0, upper=1.0)
    oscillator.name = "momentum_oscillator"
    return oscillator


def _existing(columns: Iterable[str], frame: pd.DataFrame) -> list[str]:
    return [column for column in columns if column in frame.columns]


def build_feature_frame(
    market_frame: pd.DataFrame,
    label_horizon: int = 5,
    cost_bps: float = 15.0,
    feature_lag: int = 0,
) -> tuple[pd.DataFrame, list[str]]:
    if "close" not in market_frame.columns:
        raise ValueError("Expected a 'close' column in the market frame.")
    if feature_lag < 0:
        raise ValueError("feature_lag must be non-negative.")

    frame = market_frame.copy().sort_index()
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")

    if "sma" in frame.columns:
        frame["sma"] = pd.to_numeric(frame["sma"], errors="coerce")
    else:
        frame["sma"] = frame["close"].rolling(window=20, min_periods=20).mean()

    if "atr" in frame.columns:
        frame["atr"] = pd.to_numeric(frame["atr"], errors="coerce")

    frame["ret_1d"] = frame["close"].pct_change(1)
    frame["ret_5d"] = frame["close"].pct_change(5)
    frame["ret_20d"] = frame["close"].pct_change(20)
    frame["vol_20d"] = frame["ret_1d"].rolling(window=20, min_periods=20).std()
    frame["vol_60d"] = frame["ret_1d"].rolling(window=60, min_periods=60).std()
    frame["sma_gap"] = frame["close"] / frame["sma"] - 1.0
    frame["distance_to_20d_high"] = frame["close"] / frame["close"].rolling(20, min_periods=20).max() - 1.0
    frame["distance_to_20d_low"] = frame["close"] / frame["close"].rolling(20, min_periods=20).min() - 1.0
    frame["range_20d"] = (
        frame["close"].rolling(20, min_periods=20).max()
        / frame["close"].rolling(20, min_periods=20).min()
        - 1.0
    )
    frame["trend_strength"] = frame["ret_20d"] / frame["vol_20d"].replace(0.0, np.nan)
    frame["momentum_oscillator"] = bounded_momentum_oscillator(frame["close"])

    if "atr" in frame.columns:
        frame["atr_pct"] = frame["atr"] / frame["close"]

    context_columns = _existing(MODEL_MACRO_CONTEXT_COLUMNS, frame)
    if context_columns:
        context_features: dict[str, pd.Series] = {}
        for column in context_columns:
            normalized = pd.to_numeric(frame[column], errors="coerce").ffill()
            context_features[column] = normalized
            context_features[f"{column}_z63"] = rolling_zscore(normalized, window=63)
            context_features[f"{column}_delta5"] = normalized.diff(5)

        frame = pd.concat(
            [
                frame.drop(columns=context_columns, errors="ignore"),
                pd.DataFrame(context_features, index=frame.index),
            ],
            axis=1,
        ).copy()

    risk_votes: list[pd.Series] = []
    if "spot_vix_z63" in frame.columns:
        risk_votes.append((frame["spot_vix_z63"] > 1.0).astype(float))
    elif "vix3m_level_z63" in frame.columns:
        risk_votes.append((frame["vix3m_level_z63"] > 1.0).astype(float))

    if "high_yield_spread_z63" in frame.columns:
        risk_votes.append((frame["high_yield_spread_z63"] > 0.75).astype(float))

    if "dxy_close_delta5" in frame.columns:
        risk_votes.append((frame["dxy_close_delta5"] > 0.0).astype(float))

    if "yield_curve_10y_2y" in frame.columns:
        risk_votes.append((frame["yield_curve_10y_2y"] < 0.0).astype(float))
    elif "T10Y3M" in frame.columns:
        risk_votes.append((frame["T10Y3M"] < 0.0).astype(float))

    if risk_votes:
        frame["risk_off_score"] = pd.concat(risk_votes, axis=1).sum(axis=1)
        frame["regime_risk_off"] = (frame["risk_off_score"] >= 2.0).astype(float)
    else:
        frame["risk_off_score"] = 0.0
        frame["regime_risk_off"] = 0.0

    trend_votes = [
        (frame["close"] > frame["sma"]).astype(float),
        (frame["ret_20d"] > 0.0).astype(float),
    ]
    if "spot_vix_z63" in frame.columns:
        trend_votes.append((frame["spot_vix_z63"] < 0.5).astype(float))
    elif "vix3m_level_z63" in frame.columns:
        trend_votes.append((frame["vix3m_level_z63"] < 0.5).astype(float))

    frame["trend_score"] = pd.concat(trend_votes, axis=1).sum(axis=1)
    frame["regime_trend"] = (frame["trend_score"] >= 2.0).astype(float)

    fee_rate = cost_bps / 10_000.0
    frame["forward_return"] = frame["close"].shift(-label_horizon) / frame["close"] - 1.0
    frame["net_forward_return"] = frame["forward_return"] - fee_rate
    frame["target"] = (frame["net_forward_return"] > 0.0).astype(int)

    engineered = _existing(
        [
            "ret_1d",
            "ret_5d",
            "ret_20d",
            "vol_20d",
            "vol_60d",
            "sma_gap",
            "atr_pct",
            "distance_to_20d_high",
            "distance_to_20d_low",
            "range_20d",
            "trend_strength",
            "momentum_oscillator",
            "risk_off_score",
            "regime_risk_off",
            "trend_score",
            "regime_trend",
            *context_columns,
        ],
        frame,
    )

    derived_context = [
        column
        for column in frame.columns
        if column.endswith("_z63") or column.endswith("_delta5")
    ]
    feature_columns = engineered + derived_context
    feature_frame = frame[feature_columns].copy()
    min_coverage = max(int(len(feature_frame) * 0.7), 1)
    feature_columns = [
        column
        for column in feature_columns
        if feature_frame[column].notna().sum() >= min_coverage
    ]

    if feature_lag:
        frame.loc[:, feature_columns] = frame.loc[:, feature_columns].shift(feature_lag)

    return frame, feature_columns


def engineer_daily_features(
    market_frame: pd.DataFrame,
    label_horizon: int = 5,
    cost_bps: float = 15.0,
    feature_lag: int = 0,
) -> tuple[pd.DataFrame, list[str]]:
    frame, feature_columns = build_feature_frame(
        market_frame=market_frame,
        label_horizon=label_horizon,
        cost_bps=cost_bps,
        feature_lag=feature_lag,
    )

    dataset = frame[feature_columns + ["target", "forward_return", "net_forward_return"]].dropna()
    return dataset, feature_columns
