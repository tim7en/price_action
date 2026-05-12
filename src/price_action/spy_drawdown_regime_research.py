from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .data import load_asset_daily, resolve_project_root
from .sector_fundamentals_research import SECTOR_ETF_MAP
from .spy_regime_risk_management import _causal_zscore, build_risk_management_frame
from .spy_vix_fear_greed_research import _safe_float, _signal_to_noise

DEFAULT_OUTPUT_DIR = Path("outputs") / "spy_drawdown_regime_research"
DEFAULT_DRAWNDOWN_THRESHOLD = -0.05
DEFAULT_LOOKBACK_WINDOW = 252
DEFAULT_MIN_PERIODS = 63


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Study SPY drawdown depth, pace, and recovery by regime, then map the same "
            "stress window into sector ETF drawdown ratios and stretch effects."
        )
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root. Defaults to the repository root.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated drawdown-regime research outputs.",
    )
    parser.add_argument(
        "--drawdown-threshold",
        type=float,
        default=DEFAULT_DRAWNDOWN_THRESHOLD,
        help="Threshold used to start a new SPY drawdown episode, expressed as a negative return.",
    )
    parser.add_argument(
        "--lookback-window",
        type=int,
        default=DEFAULT_LOOKBACK_WINDOW,
        help="Trailing window used for causal normalization of sector ratio features.",
    )
    parser.add_argument(
        "--min-periods",
        type=int,
        default=DEFAULT_MIN_PERIODS,
        help="Minimum trailing observations required before ratio features activate.",
    )
    return parser.parse_args()


def _resolve_output_path(root: Path, target: Path) -> Path:
    return target if target.is_absolute() else root / target


def _ratio(numerator: Any, denominator: Any) -> float | None:
    numerator_value = _safe_float(numerator)
    denominator_value = _safe_float(denominator)
    if numerator_value is None or denominator_value is None:
        return None
    if abs(denominator_value) <= 1e-12:
        return None
    value = numerator_value / denominator_value
    if not np.isfinite(value):
        return None
    return float(value)


def _market_strength_regime(row: pd.Series) -> str:
    strength_score = _safe_float(row.get("market_strength_score"))
    drawdown_63d = _safe_float(row.get("spy_drawdown_63d"))
    ret_252d = _safe_float(row.get("spy_ret_252d"))
    sma_gap_252 = _safe_float(row.get("spy_sma_252_gap"))
    fragility = _safe_float(row.get("macro_fragility_score"))
    vix_percentile = _safe_float(row.get("spot_vix_percentile_252d"))
    if strength_score is None or drawdown_63d is None:
        return "Unclassified"
    strong_long_trend = (ret_252d is None or ret_252d >= 0.08) and (sma_gap_252 is None or sma_gap_252 >= 0.0)
    weak_long_trend = (ret_252d is not None and ret_252d <= 0.0) or (sma_gap_252 is not None and sma_gap_252 <= -0.02)
    calm_backdrop = (fragility is None or fragility <= 0.20) and (vix_percentile is None or vix_percentile <= 0.60)
    fragile_backdrop = (fragility is not None and fragility >= 0.25) or (vix_percentile is not None and vix_percentile >= 0.70)

    if strength_score >= 0.60 and drawdown_63d >= -0.06 and strong_long_trend and calm_backdrop:
        return "Strong"
    if strength_score <= 0.25 or drawdown_63d <= -0.08 or weak_long_trend or fragile_backdrop:
        return "Weak"
    return "Neutral"


def _instability_regime(row: pd.Series) -> str:
    panic_score = _safe_float(row.get("panic_score"))
    fragility = _safe_float(row.get("macro_fragility_score"))
    vix_percentile = _safe_float(row.get("spot_vix_percentile_252d"))
    if bool(row.get("extreme_risk_off", False)):
        return "Stress"
    if (
        (panic_score is not None and panic_score >= 0.75)
        or (fragility is not None and fragility >= 0.50)
        or (vix_percentile is not None and vix_percentile >= 0.85)
    ):
        return "Stress"
    if bool(row.get("risk_off_gate", False)):
        return "Fragile"
    if (
        (panic_score is not None and panic_score >= 0.45)
        or (fragility is not None and fragility >= 0.10)
        or (vix_percentile is not None and vix_percentile >= 0.60)
    ):
        return "Fragile"
    return "Calm"


def _stretch_bucket(value: Any) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "Unknown"
    if numeric >= 1.0:
        return "Rich"
    if numeric <= -1.0:
        return "Cheap"
    return "Neutral"


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def build_drawdown_panel(
    *,
    project_root: str | Path | None = None,
    lookback_window: int = DEFAULT_LOOKBACK_WINDOW,
    min_periods: int = DEFAULT_MIN_PERIODS,
) -> pd.DataFrame:
    root = resolve_project_root(project_root)
    frame = build_risk_management_frame(
        project_root=root,
        hold_days=5,
        lookback_window=lookback_window,
        min_periods=min_periods,
    ).copy()

    close = pd.to_numeric(frame["spy_close"], errors="coerce")
    sma_252 = close.rolling(252, min_periods=126).mean()
    frame["spy_ret_252d"] = close.pct_change(252)
    frame["spy_sma_252_gap"] = close / sma_252 - 1.0
    frame["spy_trend_126d"] = close.pct_change(126)
    frame["spy_trend_126d_zscore"] = _causal_zscore(
        frame["spy_trend_126d"], window=lookback_window, min_periods=min_periods
    )
    frame["market_strength_score"] = pd.DataFrame(
        {
            "trend_20d": frame.get("spy_trend_20d_zscore"),
            "trend_63d": frame.get("spy_trend_63d_zscore"),
            "trend_126d": frame.get("spy_trend_126d_zscore"),
            "drawdown_calm": frame.get("spy_drawdown_63d_zscore"),
            "vix_calm": -_numeric_series(frame, "spot_vix_zscore_252d"),
        },
        index=frame.index,
    ).mean(axis=1)

    if "high_yield_spread" in frame.columns:
        frame["high_yield_spread_change_5d"] = pd.to_numeric(frame["high_yield_spread"], errors="coerce").diff(5)
        frame["high_yield_spread_change_20d"] = pd.to_numeric(frame["high_yield_spread"], errors="coerce").diff(20)
        frame["high_yield_spread_change_5d_zscore"] = _causal_zscore(
            frame["high_yield_spread_change_5d"], window=lookback_window, min_periods=min_periods
        )
        frame["high_yield_spread_change_20d_zscore"] = _causal_zscore(
            frame["high_yield_spread_change_20d"], window=lookback_window, min_periods=min_periods
        )
    if "NFCI" in frame.columns:
        frame["NFCI_change_5d"] = pd.to_numeric(frame["NFCI"], errors="coerce").diff(5)
        frame["NFCI_change_5d_zscore"] = _causal_zscore(
            frame["NFCI_change_5d"], window=lookback_window, min_periods=min_periods
        )

    frame["vix_pace_score"] = pd.DataFrame(
        {
            "vix_change_5d": frame.get("spot_vix_change_5d_zscore"),
            "vix_level": frame.get("spot_vix_zscore_252d"),
        },
        index=frame.index,
    ).mean(axis=1)
    frame["credit_pace_score"] = pd.DataFrame(
        {
            "hy_change_5d": frame.get("high_yield_spread_change_5d_zscore"),
            "nfci_change_5d": frame.get("NFCI_change_5d_zscore"),
            "macro_fragility": frame.get("macro_fragility_score"),
        },
        index=frame.index,
    ).mean(axis=1)

    frame["market_strength_regime"] = frame.apply(_market_strength_regime, axis=1)
    frame["instability_regime"] = frame.apply(_instability_regime, axis=1)
    frame["combined_regime"] = frame["market_strength_regime"] + " / " + frame["instability_regime"]
    running_peak = close.cummax()
    frame["spy_ath_drawdown"] = close / running_peak - 1.0
    frame["drawdown_5pct_flag"] = frame["spy_ath_drawdown"] <= -0.05
    frame["drawdown_10pct_flag"] = frame["spy_ath_drawdown"] <= -0.10
    return frame.sort_index()


def build_spy_drawdown_episodes(
    frame: pd.DataFrame,
    *,
    drawdown_threshold: float = DEFAULT_DRAWNDOWN_THRESHOLD,
) -> pd.DataFrame:
    close = pd.to_numeric(frame["spy_close"], errors="coerce")
    valid = frame.loc[close.notna()].copy()
    close = close.loc[valid.index]
    if valid.empty:
        return pd.DataFrame()

    date_index = list(valid.index)
    episodes: list[dict[str, Any]] = []
    peak_price = float(close.iloc[0])
    peak_date = date_index[0]
    peak_position = 0
    active_episode: dict[str, Any] | None = None

    for position, date in enumerate(date_index):
        price = float(close.iloc[position])
        if active_episode is None:
            if price >= peak_price:
                peak_price = price
                peak_date = date
                peak_position = position

            current_drawdown = price / peak_price - 1.0
            if current_drawdown <= drawdown_threshold:
                onset_row = valid.loc[date]
                peak_row = valid.loc[peak_date]
                active_episode = {
                    "peak_date": peak_date,
                    "peak_position": peak_position,
                    "peak_price": peak_price,
                    "onset_date": date,
                    "onset_position": position,
                    "onset_price": price,
                    "onset_drawdown": current_drawdown,
                    "trough_date": date,
                    "trough_position": position,
                    "trough_price": price,
                    "max_drawdown": current_drawdown,
                    "pre_drawdown_market_strength_regime": peak_row.get("market_strength_regime"),
                    "pre_drawdown_instability_regime": peak_row.get("instability_regime"),
                    "pre_drawdown_combined_regime": peak_row.get("combined_regime"),
                    "pre_drawdown_sentiment_state": peak_row.get("sentiment_state_clean"),
                    "pre_drawdown_macro_bucket": peak_row.get("macro_bucket"),
                    "pre_drawdown_panic_score": _safe_float(peak_row.get("panic_score")),
                    "pre_drawdown_fear_greed_score": _safe_float(peak_row.get("fear_greed_score")),
                    "pre_drawdown_macro_fragility_score": _safe_float(peak_row.get("macro_fragility_score")),
                    "pre_drawdown_spot_vix_percentile_252d": _safe_float(peak_row.get("spot_vix_percentile_252d")),
                    "pre_drawdown_market_strength_score": _safe_float(peak_row.get("market_strength_score")),
                    "onset_market_strength_regime": onset_row.get("market_strength_regime"),
                    "onset_instability_regime": onset_row.get("instability_regime"),
                    "onset_combined_regime": onset_row.get("combined_regime"),
                    "onset_sentiment_state": onset_row.get("sentiment_state_clean"),
                    "onset_macro_bucket": onset_row.get("macro_bucket"),
                    "panic_score": _safe_float(onset_row.get("panic_score")),
                    "fear_greed_score": _safe_float(onset_row.get("fear_greed_score")),
                    "macro_fragility_score": _safe_float(onset_row.get("macro_fragility_score")),
                    "spot_vix_percentile_252d": _safe_float(onset_row.get("spot_vix_percentile_252d")),
                    "spot_vix_change_5d_zscore": _safe_float(onset_row.get("spot_vix_change_5d_zscore")),
                    "vix_pace_score": _safe_float(onset_row.get("vix_pace_score")),
                    "high_yield_spread_change_5d_zscore": _safe_float(onset_row.get("high_yield_spread_change_5d_zscore")),
                    "credit_pace_score": _safe_float(onset_row.get("credit_pace_score")),
                    "market_strength_score": _safe_float(onset_row.get("market_strength_score")),
                }
            continue

        current_drawdown = price / float(active_episode["peak_price"]) - 1.0
        if current_drawdown < float(active_episode["max_drawdown"]):
            active_episode["max_drawdown"] = current_drawdown
            active_episode["trough_date"] = date
            active_episode["trough_position"] = position
            active_episode["trough_price"] = price

        if price >= float(active_episode["peak_price"]):
            active_episode["recovery_date"] = date
            active_episode["recovery_position"] = position
            episodes.append(active_episode)
            active_episode = None
            peak_price = price
            peak_date = date
            peak_position = position

    if active_episode is not None:
        active_episode["recovery_date"] = pd.NaT
        active_episode["recovery_position"] = None
        episodes.append(active_episode)

    if not episodes:
        return pd.DataFrame()

    episode_frame = pd.DataFrame(episodes)
    episode_frame["episode_id"] = np.arange(len(episode_frame))

    close_values = close.reset_index(drop=True)
    for column_name, source_column in [
        ("peak_to_trough_days", "trough_position"),
        ("onset_to_trough_days", "trough_position"),
    ]:
        if column_name == "peak_to_trough_days":
            episode_frame[column_name] = episode_frame[source_column] - episode_frame["peak_position"]
        else:
            episode_frame[column_name] = episode_frame[source_column] - episode_frame["onset_position"]

    episode_frame["peak_to_recovery_days"] = episode_frame["recovery_position"] - episode_frame["peak_position"]
    episode_frame["trough_to_recovery_days"] = episode_frame["recovery_position"] - episode_frame["trough_position"]
    episode_frame["drawdown_speed_from_peak_per_day"] = (
        episode_frame["max_drawdown"].abs() / episode_frame["peak_to_trough_days"].clip(lower=1)
    )
    episode_frame["drawdown_speed_from_onset_per_day"] = (
        (episode_frame["max_drawdown"] - episode_frame["onset_drawdown"]).abs()
        / episode_frame["onset_to_trough_days"].clip(lower=1)
    )

    trough_to_20d: list[float | None] = []
    trough_to_60d: list[float | None] = []
    onset_to_20d: list[float | None] = []
    recovered_within_20d: list[bool | None] = []
    recovered_within_60d: list[bool | None] = []
    for _, row in episode_frame.iterrows():
        trough_position = int(row["trough_position"])
        onset_position = int(row["onset_position"])
        trough_price = float(row["trough_price"])
        onset_price = float(row["onset_price"])
        if trough_position + 20 < len(close_values):
            trough_to_20d.append(float(close_values.iloc[trough_position + 20] / trough_price - 1.0))
        else:
            trough_to_20d.append(np.nan)
        if trough_position + 60 < len(close_values):
            trough_to_60d.append(float(close_values.iloc[trough_position + 60] / trough_price - 1.0))
        else:
            trough_to_60d.append(np.nan)
        if onset_position + 20 < len(close_values):
            onset_to_20d.append(float(close_values.iloc[onset_position + 20] / onset_price - 1.0))
        else:
            onset_to_20d.append(np.nan)
        recovery_days = _safe_float(row.get("trough_to_recovery_days"))
        recovered_within_20d.append((recovery_days is not None) and (recovery_days <= 20))
        recovered_within_60d.append((recovery_days is not None) and (recovery_days <= 60))

    episode_frame["trough_to_20d_return"] = trough_to_20d
    episode_frame["trough_to_60d_return"] = trough_to_60d
    episode_frame["onset_to_20d_return"] = onset_to_20d
    episode_frame["recovered_within_20d"] = recovered_within_20d
    episode_frame["recovered_within_60d"] = recovered_within_60d
    episode_frame["max_drawdown_abs"] = episode_frame["max_drawdown"].abs()
    episode_frame["drawdown_to_20d_recovery_ratio"] = episode_frame.apply(
        lambda row: _ratio(row.get("trough_to_20d_return"), row.get("max_drawdown_abs")),
        axis=1,
    )
    return episode_frame.sort_values("onset_date").reset_index(drop=True)


def build_drawdown_regime_summary(episodes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if episodes.empty:
        return pd.DataFrame(), pd.DataFrame()

    strength_summary = (
        episodes.groupby("pre_drawdown_market_strength_regime", as_index=False)
        .agg(
            episode_count=("episode_id", "count"),
            avg_max_drawdown=("max_drawdown", "mean"),
            median_max_drawdown=("max_drawdown", "median"),
            avg_peak_to_trough_days=("peak_to_trough_days", "mean"),
            avg_drawdown_speed=("drawdown_speed_from_peak_per_day", "mean"),
            avg_trough_to_20d_return=("trough_to_20d_return", "mean"),
            avg_trough_to_60d_return=("trough_to_60d_return", "mean"),
            recovered_within_20d_rate=("recovered_within_20d", "mean"),
            recovered_within_60d_rate=("recovered_within_60d", "mean"),
            avg_trough_to_recovery_days=("trough_to_recovery_days", "mean"),
        )
        .sort_values("pre_drawdown_market_strength_regime")
        .reset_index(drop=True)
    )

    combined_summary = (
        episodes.groupby(["pre_drawdown_market_strength_regime", "pre_drawdown_combined_regime"], as_index=False)
        .agg(
            episode_count=("episode_id", "count"),
            avg_max_drawdown=("max_drawdown", "mean"),
            avg_peak_to_trough_days=("peak_to_trough_days", "mean"),
            avg_drawdown_speed=("drawdown_speed_from_peak_per_day", "mean"),
            avg_trough_to_20d_return=("trough_to_20d_return", "mean"),
            avg_trough_to_60d_return=("trough_to_60d_return", "mean"),
            recovered_within_60d_rate=("recovered_within_60d", "mean"),
        )
        .sort_values(["pre_drawdown_market_strength_regime", "episode_count"], ascending=[True, False])
        .reset_index(drop=True)
    )
    return strength_summary, combined_summary


def build_hypothesis_test_summary(episodes: pd.DataFrame) -> pd.DataFrame:
    if episodes.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    strong = episodes.loc[episodes["pre_drawdown_market_strength_regime"] == "Strong"]
    weak = episodes.loc[episodes["pre_drawdown_market_strength_regime"] == "Weak"]

    if not strong.empty and not weak.empty:
        rows.extend(
            [
                {
                    "hypothesis": "Weak-market drawdowns are deeper than strong-market drawdowns",
                    "left_group": "Weak",
                    "right_group": "Strong",
                    "metric": "abs(max_drawdown)",
                    "left_value": _safe_float(weak["max_drawdown_abs"].mean()),
                    "right_value": _safe_float(strong["max_drawdown_abs"].mean()),
                    "supports_hypothesis": bool(weak["max_drawdown_abs"].mean() > strong["max_drawdown_abs"].mean()),
                },
                {
                    "hypothesis": "Weak-market drawdowns unfold faster than strong-market drawdowns",
                    "left_group": "Weak",
                    "right_group": "Strong",
                    "metric": "drawdown_speed_from_peak_per_day",
                    "left_value": _safe_float(weak["drawdown_speed_from_peak_per_day"].mean()),
                    "right_value": _safe_float(strong["drawdown_speed_from_peak_per_day"].mean()),
                    "supports_hypothesis": bool(
                        weak["drawdown_speed_from_peak_per_day"].mean()
                        > strong["drawdown_speed_from_peak_per_day"].mean()
                    ),
                },
                {
                    "hypothesis": "Weak-market drawdowns recover more slowly than strong-market drawdowns",
                    "left_group": "Weak",
                    "right_group": "Strong",
                    "metric": "recovered_within_60d_rate",
                    "left_value": _safe_float(weak["recovered_within_60d"].mean()),
                    "right_value": _safe_float(strong["recovered_within_60d"].mean()),
                    "supports_hypothesis": bool(weak["recovered_within_60d"].mean() < strong["recovered_within_60d"].mean()),
                },
            ]
        )

    return pd.DataFrame(rows)


def build_pace_factor_summary(episodes: pd.DataFrame) -> pd.DataFrame:
    if episodes.empty:
        return pd.DataFrame()
    factor_columns = (
        "vix_pace_score",
        "spot_vix_change_5d_zscore",
        "credit_pace_score",
        "high_yield_spread_change_5d_zscore",
    )
    outcome_columns = (
        "max_drawdown_abs",
        "drawdown_speed_from_peak_per_day",
        "trough_to_20d_return",
        "trough_to_60d_return",
        "recovered_within_60d",
    )
    rows: list[dict[str, Any]] = []
    for factor_name in factor_columns:
        if factor_name not in episodes.columns:
            continue
        pair = episodes[[factor_name, *outcome_columns]].dropna(subset=[factor_name])
        if pair.empty:
            continue
        upper_cut = float(pair[factor_name].quantile(0.80))
        lower_cut = float(pair[factor_name].quantile(0.20))
        high_bucket = pair.loc[pair[factor_name] >= upper_cut]
        low_bucket = pair.loc[pair[factor_name] <= lower_cut]
        for outcome_name in outcome_columns:
            rows.append(
                {
                    "factor": factor_name,
                    "outcome": outcome_name,
                    "observations": int(pair[outcome_name].notna().sum()),
                    "correlation": _safe_float(pair[factor_name].corr(pair[outcome_name])),
                    "high_bucket_mean": _safe_float(high_bucket[outcome_name].mean()),
                    "low_bucket_mean": _safe_float(low_bucket[outcome_name].mean()),
                    "high_minus_low": _safe_float(high_bucket[outcome_name].mean() - low_bucket[outcome_name].mean())
                    if not high_bucket.empty and not low_bucket.empty
                    else None,
                }
            )
    return pd.DataFrame(rows).sort_values(["factor", "outcome"]).reset_index(drop=True)


def build_sector_ratio_panel(
    *,
    root: Path,
    dates: pd.DatetimeIndex,
    spy_close: pd.Series,
    lookback_window: int,
    min_periods: int,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for sector, symbol in SECTOR_ETF_MAP.items():
        asset = load_asset_daily(symbol, project_root=root).sort_index()
        close = pd.to_numeric(asset["close"], errors="coerce").reindex(dates)
        ratio_to_spy = close / spy_close
        relative_return_63d = close.pct_change(63) - spy_close.pct_change(63)
        ratio_log = pd.Series(
            np.log(ratio_to_spy.where(ratio_to_spy > 0.0)),
            index=dates,
            dtype=float,
        )
        ratio_zscore = _causal_zscore(ratio_log, window=lookback_window, min_periods=min_periods)
        relative_return_63d_zscore = _causal_zscore(
            relative_return_63d, window=lookback_window, min_periods=min_periods
        )
        stretch_score = pd.DataFrame(
            {
                "ratio_zscore": ratio_zscore,
                "relative_return_63d_zscore": relative_return_63d_zscore,
            },
            index=dates,
        ).mean(axis=1)

        frame = pd.DataFrame(
            {
                "date": dates,
                "sector": sector,
                "etf_symbol": symbol,
                "sector_close": close.to_numpy(),
                "ratio_to_spy": ratio_to_spy.to_numpy(),
                "ratio_to_spy_zscore_252d": ratio_zscore.to_numpy(),
                "relative_return_63d": relative_return_63d.to_numpy(),
                "stretch_score": stretch_score.to_numpy(),
            }
        )
        frame["stretch_bucket"] = frame["stretch_score"].map(_stretch_bucket)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def build_sector_episode_ratios(
    episodes: pd.DataFrame,
    *,
    sector_panel: pd.DataFrame,
    spy_close: pd.Series,
) -> pd.DataFrame:
    if episodes.empty or sector_panel.empty:
        return pd.DataFrame()

    sector_close_wide = sector_panel.pivot(index="date", columns="sector", values="sector_close").sort_index()
    stretch_score_wide = sector_panel.pivot(index="date", columns="sector", values="stretch_score").sort_index()
    stretch_bucket_wide = sector_panel.pivot(index="date", columns="sector", values="stretch_bucket").sort_index()
    ratio_zscore_wide = sector_panel.pivot(index="date", columns="sector", values="ratio_to_spy_zscore_252d").sort_index()
    relative_return_wide = sector_panel.pivot(index="date", columns="sector", values="relative_return_63d").sort_index()
    spy_close = pd.to_numeric(spy_close, errors="coerce").sort_index()

    rows: list[dict[str, Any]] = []
    for _, episode in episodes.iterrows():
        peak_date = pd.Timestamp(episode["peak_date"])
        onset_date = pd.Timestamp(episode["onset_date"])
        trough_date = pd.Timestamp(episode["trough_date"])
        recovery_date = pd.Timestamp(episode["recovery_date"]) if pd.notna(episode["recovery_date"]) else pd.NaT

        if peak_date not in spy_close.index or trough_date not in spy_close.index:
            continue

        spy_peak_price = float(spy_close.loc[peak_date])
        spy_trough_price = float(spy_close.loc[trough_date])
        spy_trough_return = spy_trough_price / spy_peak_price - 1.0
        spy_recovery_return = None
        if pd.notna(recovery_date) and recovery_date in spy_close.index:
            spy_recovery_return = float(spy_close.loc[recovery_date] / spy_trough_price - 1.0)

        for sector in sector_close_wide.columns:
            if peak_date not in sector_close_wide.index or trough_date not in sector_close_wide.index:
                continue
            sector_peak_price = _safe_float(sector_close_wide.at[peak_date, sector])
            sector_trough_price = _safe_float(sector_close_wide.at[trough_date, sector])
            if sector_peak_price is None or sector_trough_price is None or sector_peak_price <= 0.0:
                continue

            sector_same_trough_return = float(sector_trough_price / sector_peak_price - 1.0)
            window = sector_close_wide.loc[peak_date:trough_date, sector].dropna()
            if window.empty:
                continue
            sector_window_min_price = float(window.min())
            sector_window_min_return = float(sector_window_min_price / sector_peak_price - 1.0)
            sector_recovery_return = None
            if pd.notna(recovery_date) and recovery_date in sector_close_wide.index:
                recovery_price = _safe_float(sector_close_wide.at[recovery_date, sector])
                if recovery_price is not None and sector_trough_price > 0.0:
                    sector_recovery_return = float(recovery_price / sector_trough_price - 1.0)

            stretch_score = _safe_float(stretch_score_wide.at[onset_date, sector]) if onset_date in stretch_score_wide.index else None
            rows.append(
                {
                    "episode_id": int(episode["episode_id"]),
                    "peak_date": peak_date,
                    "onset_date": onset_date,
                    "trough_date": trough_date,
                    "recovery_date": recovery_date,
                    "pre_drawdown_market_strength_regime": episode["pre_drawdown_market_strength_regime"],
                    "pre_drawdown_combined_regime": episode["pre_drawdown_combined_regime"],
                    "onset_market_strength_regime": episode["onset_market_strength_regime"],
                    "onset_combined_regime": episode["onset_combined_regime"],
                    "sector": sector,
                    "etf_symbol": SECTOR_ETF_MAP[sector],
                    "stretch_score": stretch_score,
                    "stretch_bucket": stretch_bucket_wide.at[onset_date, sector] if onset_date in stretch_bucket_wide.index else "Unknown",
                    "ratio_to_spy_zscore_252d": _safe_float(ratio_zscore_wide.at[onset_date, sector]) if onset_date in ratio_zscore_wide.index else None,
                    "relative_return_63d": _safe_float(relative_return_wide.at[onset_date, sector]) if onset_date in relative_return_wide.index else None,
                    "spy_peak_to_trough_return": spy_trough_return,
                    "sector_peak_to_spy_trough_return": sector_same_trough_return,
                    "sector_window_min_return": sector_window_min_return,
                    "sector_same_date_drawdown_ratio": _ratio(sector_same_trough_return, spy_trough_return),
                    "sector_window_drawdown_ratio": _ratio(sector_window_min_return, spy_trough_return),
                    "spy_recovery_return": spy_recovery_return,
                    "sector_recovery_return": sector_recovery_return,
                    "recovery_ratio_vs_spy": _ratio(sector_recovery_return, spy_recovery_return),
                }
            )
    return pd.DataFrame(rows).sort_values(["episode_id", "sector"]).reset_index(drop=True)


def build_sector_ratio_summary(sector_episode_ratios: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if sector_episode_ratios.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    regime_summary = (
        sector_episode_ratios.groupby(["sector", "pre_drawdown_market_strength_regime"], as_index=False)
        .agg(
            observations=("episode_id", "count"),
            avg_same_date_drawdown_ratio=("sector_same_date_drawdown_ratio", "mean"),
            avg_window_drawdown_ratio=("sector_window_drawdown_ratio", "mean"),
            avg_recovery_ratio_vs_spy=("recovery_ratio_vs_spy", "mean"),
            avg_relative_return_63d=("relative_return_63d", "mean"),
        )
        .sort_values(["pre_drawdown_market_strength_regime", "avg_window_drawdown_ratio"], ascending=[True, False])
        .reset_index(drop=True)
    )

    stretch_summary = (
        sector_episode_ratios.groupby(["sector", "stretch_bucket"], as_index=False)
        .agg(
            observations=("episode_id", "count"),
            avg_stretch_score=("stretch_score", "mean"),
            avg_same_date_drawdown_ratio=("sector_same_date_drawdown_ratio", "mean"),
            avg_window_drawdown_ratio=("sector_window_drawdown_ratio", "mean"),
            avg_recovery_ratio_vs_spy=("recovery_ratio_vs_spy", "mean"),
        )
        .sort_values(["sector", "stretch_bucket"])
        .reset_index(drop=True)
    )

    stretch_effect = (
        sector_episode_ratios.groupby("sector", as_index=False)
        .agg(
            observations=("episode_id", "count"),
            stretch_to_drawdown_corr=("stretch_score", lambda values: np.nan),
        )
        .drop(columns=["stretch_to_drawdown_corr"])
    )
    correlations: list[dict[str, Any]] = []
    for sector, subset in sector_episode_ratios.groupby("sector"):
        pair = subset[["stretch_score", "sector_window_drawdown_ratio", "recovery_ratio_vs_spy"]].dropna()
        if pair.empty:
            correlations.append(
                {
                    "sector": sector,
                    "observations": int(len(subset)),
                    "stretch_to_drawdown_corr": None,
                    "stretch_to_recovery_corr": None,
                }
            )
            continue
        correlations.append(
            {
                "sector": sector,
                "observations": int(len(pair)),
                "stretch_to_drawdown_corr": _safe_float(pair["stretch_score"].corr(pair["sector_window_drawdown_ratio"])),
                "stretch_to_recovery_corr": _safe_float(pair["stretch_score"].corr(pair["recovery_ratio_vs_spy"])),
            }
        )
    stretch_effect = pd.DataFrame(correlations).sort_values("stretch_to_drawdown_corr", ascending=False).reset_index(drop=True)
    return regime_summary, stretch_summary, stretch_effect


def build_spy_drawdown_regime_research(
    *,
    project_root: str | Path | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    drawdown_threshold: float = DEFAULT_DRAWNDOWN_THRESHOLD,
    lookback_window: int = DEFAULT_LOOKBACK_WINDOW,
    min_periods: int = DEFAULT_MIN_PERIODS,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    resolved_output_dir = _resolve_output_path(root, output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    panel = build_drawdown_panel(
        project_root=root,
        lookback_window=lookback_window,
        min_periods=min_periods,
    )
    panel.reset_index().to_csv(resolved_output_dir / "drawdown_daily_panel.csv", index=False)

    episodes = build_spy_drawdown_episodes(panel, drawdown_threshold=drawdown_threshold)
    episodes.to_csv(resolved_output_dir / "spy_drawdown_episodes.csv", index=False)

    strength_summary, combined_summary = build_drawdown_regime_summary(episodes)
    strength_summary.to_csv(resolved_output_dir / "drawdown_strength_summary.csv", index=False)
    combined_summary.to_csv(resolved_output_dir / "drawdown_combined_regime_summary.csv", index=False)

    hypothesis_summary = build_hypothesis_test_summary(episodes)
    hypothesis_summary.to_csv(resolved_output_dir / "hypothesis_test_summary.csv", index=False)

    pace_summary = build_pace_factor_summary(episodes)
    pace_summary.to_csv(resolved_output_dir / "pace_factor_summary.csv", index=False)

    sector_panel = build_sector_ratio_panel(
        root=root,
        dates=pd.DatetimeIndex(panel.index),
        spy_close=pd.to_numeric(panel["spy_close"], errors="coerce"),
        lookback_window=lookback_window,
        min_periods=min_periods,
    )
    sector_panel.to_csv(resolved_output_dir / "sector_ratio_daily_panel.csv", index=False)

    sector_episode_ratios = build_sector_episode_ratios(
        episodes,
        sector_panel=sector_panel,
        spy_close=pd.to_numeric(panel["spy_close"], errors="coerce"),
    )
    sector_episode_ratios.to_csv(resolved_output_dir / "sector_drawdown_episode_ratios.csv", index=False)

    sector_regime_summary, sector_stretch_summary, sector_stretch_effect = build_sector_ratio_summary(
        sector_episode_ratios
    )
    sector_regime_summary.to_csv(resolved_output_dir / "sector_regime_ratio_summary.csv", index=False)
    sector_stretch_summary.to_csv(resolved_output_dir / "sector_stretch_summary.csv", index=False)
    sector_stretch_effect.to_csv(resolved_output_dir / "sector_stretch_effect_summary.csv", index=False)

    worst_sectors = sector_regime_summary.sort_values("avg_window_drawdown_ratio", ascending=False).head(10)
    strongest_sectors = sector_regime_summary.sort_values("avg_window_drawdown_ratio", ascending=True).head(10)

    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "output_dir": str(resolved_output_dir),
        "rows": int(len(panel)),
        "episode_count": int(len(episodes)),
        "drawdown_threshold": float(drawdown_threshold),
        "lookback_window": int(lookback_window),
        "min_periods": int(min_periods),
        "hypotheses": [
            "Strong markets should have shallower and slower drawdowns than weak markets.",
            "Faster VIX and credit deterioration at onset should coincide with deeper drawdowns and slower recovery.",
            "Sectors stretched rich versus SPY should suffer larger relative drawdowns during SPY stress windows.",
        ],
        "worst_sector_regime_ratios": worst_sectors.to_dict(orient="records"),
        "best_sector_regime_ratios": strongest_sectors.to_dict(orient="records"),
    }
    (resolved_output_dir / "spy_drawdown_regime_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    args = parse_args()
    summary = build_spy_drawdown_regime_research(
        project_root=args.project_root,
        output_dir=args.output_dir,
        drawdown_threshold=args.drawdown_threshold,
        lookback_window=args.lookback_window,
        min_periods=args.min_periods,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()