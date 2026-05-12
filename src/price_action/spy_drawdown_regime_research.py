from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .data import load_asset_daily, resolve_project_root
from .sector_fundamentals_research import SECTOR_ETF_MAP
from .spy_regime_risk_management import _causal_zscore, build_risk_management_frame
from .spy_vix_fear_greed_research import _safe_float, _signal_to_noise

DEFAULT_OUTPUT_DIR = Path("outputs") / "spy_drawdown_regime_research"
DEFAULT_FUNDAMENTALS_OUTPUT_DIR = Path("outputs") / "fundamentals_analysis"
DEFAULT_DRAWNDOWN_THRESHOLD = -0.05
DEFAULT_LOOKBACK_WINDOW = 252
DEFAULT_MIN_PERIODS = 63
SIZE_BUCKET_LABELS = ("SMALL_CAP", "MID_CAP", "LARGE_CAP")
HMM_FEATURE_COLUMNS = (
    "market_strength_score",
    "macro_fragility_score",
    "panic_score",
    "vix_pace_score",
    "credit_pace_score",
    "spot_vix_percentile_252d",
    "spy_drawdown_63d",
    "spy_ret_252d",
)


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


def _weighted_average(values: pd.Series, weights: pd.Series) -> float | None:
    pair = pd.DataFrame({"value": values, "weight": weights}).replace([np.inf, -np.inf], np.nan).dropna()
    pair = pair.loc[pair["weight"] > 0.0]
    if pair.empty:
        numeric = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        return _safe_float(numeric.mean())
    return float(np.average(pair["value"], weights=pair["weight"]))


def _assign_size_buckets(frame: pd.DataFrame) -> pd.DataFrame:
    bucketed = frame.copy()
    bucketed["market_cap"] = pd.to_numeric(bucketed["market_cap"], errors="coerce")
    valid = bucketed["market_cap"].gt(0.0) & bucketed["market_cap"].notna()
    bucketed["size_bucket"] = pd.Series(pd.NA, index=bucketed.index, dtype="object")
    if not valid.any():
        return bucketed

    percent_rank = bucketed.loc[valid, "market_cap"].rank(method="average", pct=True)
    bucketed.loc[valid & percent_rank.le(1.0 / 3.0), "size_bucket"] = SIZE_BUCKET_LABELS[0]
    bucketed.loc[valid & percent_rank.gt(1.0 / 3.0) & percent_rank.le(2.0 / 3.0), "size_bucket"] = (
        SIZE_BUCKET_LABELS[1]
    )
    bucketed.loc[valid & percent_rank.gt(2.0 / 3.0), "size_bucket"] = SIZE_BUCKET_LABELS[2]
    return bucketed


def build_size_bucket_earnings_snapshots(
    *,
    root: Path,
    event_dates: pd.DatetimeIndex,
    fundamentals_output_dir: Path = DEFAULT_FUNDAMENTALS_OUTPUT_DIR,
) -> pd.DataFrame:
    if len(event_dates) == 0:
        return pd.DataFrame()

    resolved_output_dir = _resolve_output_path(root, fundamentals_output_dir)
    quarterly_path = resolved_output_dir / "symbol_quarterly_earnings.csv"
    if not quarterly_path.exists():
        return pd.DataFrame()

    quarterly = pd.read_csv(
        quarterly_path,
        usecols=[
            "symbol",
            "reported_date",
            "surprise_pct",
            "quarterly_eps_yoy_pct",
            "beat_flag",
            "reported_eps",
            "estimated_eps",
            "market_cap",
            "eligible_for_sector_analysis",
        ],
        parse_dates=["reported_date"],
        low_memory=False,
    )
    quarterly = quarterly.loc[quarterly["eligible_for_sector_analysis"].fillna(True)].copy()
    quarterly = quarterly.dropna(subset=["symbol", "reported_date"])
    if quarterly.empty:
        return pd.DataFrame()

    for column in ("surprise_pct", "quarterly_eps_yoy_pct", "reported_eps", "estimated_eps", "market_cap"):
        quarterly[column] = pd.to_numeric(quarterly[column], errors="coerce")
    quarterly["beat_flag"] = quarterly["beat_flag"].fillna(False).astype(bool)
    quarterly = quarterly.sort_values(["reported_date", "symbol"]).reset_index(drop=True)

    rows: list[dict[str, Any]] = []
    for event_date in sorted(pd.DatetimeIndex(event_dates).dropna().unique()):
        snapshot = quarterly.loc[quarterly["reported_date"] <= event_date].copy()
        if snapshot.empty:
            continue
        snapshot = snapshot.groupby("symbol", as_index=False).tail(1)
        snapshot = _assign_size_buckets(snapshot)
        snapshot = snapshot.dropna(subset=["size_bucket"])
        if snapshot.empty:
            continue

        total_market_cap = snapshot["market_cap"].sum(min_count=1)
        for size_bucket, group in snapshot.groupby("size_bucket"):
            rows.append(
                {
                    "snapshot_date": pd.Timestamp(event_date),
                    "size_bucket": size_bucket,
                    "symbol_count": int(group["symbol"].nunique()),
                    "market_cap_share": _safe_float(group["market_cap"].sum(min_count=1) / total_market_cap)
                    if pd.notna(total_market_cap) and total_market_cap > 0.0
                    else None,
                    "avg_surprise_pct": _safe_float(group["surprise_pct"].mean()),
                    "cap_weighted_surprise_pct": _weighted_average(group["surprise_pct"], group["market_cap"]),
                    "beat_rate": _safe_float(group["beat_flag"].mean()),
                    "avg_reported_eps": _safe_float(group["reported_eps"].mean()),
                    "avg_estimated_eps": _safe_float(group["estimated_eps"].mean()),
                    "avg_quarterly_eps_yoy_pct": _safe_float(group["quarterly_eps_yoy_pct"].mean()),
                    "cap_weighted_quarterly_eps_yoy_pct": _weighted_average(
                        group["quarterly_eps_yoy_pct"], group["market_cap"]
                    ),
                }
            )

    if not rows:
        return pd.DataFrame()

    long_frame = pd.DataFrame(rows).sort_values(["snapshot_date", "size_bucket"]).reset_index(drop=True)
    wide_rows: list[dict[str, Any]] = []
    value_columns = [
        "symbol_count",
        "market_cap_share",
        "avg_surprise_pct",
        "cap_weighted_surprise_pct",
        "beat_rate",
        "avg_reported_eps",
        "avg_estimated_eps",
        "avg_quarterly_eps_yoy_pct",
        "cap_weighted_quarterly_eps_yoy_pct",
    ]
    for snapshot_date, group in long_frame.groupby("snapshot_date"):
        row: dict[str, Any] = {"snapshot_date": pd.Timestamp(snapshot_date)}
        for record in group.itertuples(index=False):
            prefix = str(record.size_bucket).lower()
            for column in value_columns:
                row[f"{prefix}_{column}"] = getattr(record, column)
        wide_rows.append(row)
    return pd.DataFrame(wide_rows).sort_values("snapshot_date").reset_index(drop=True)


def attach_size_bucket_earnings_to_episodes(
    episodes: pd.DataFrame,
    *,
    size_bucket_snapshots: pd.DataFrame,
) -> pd.DataFrame:
    if episodes.empty or size_bucket_snapshots.empty:
        return episodes

    peak_snapshots = size_bucket_snapshots.rename(
        columns={
            column: f"pre_drawdown_{column}"
            for column in size_bucket_snapshots.columns
            if column != "snapshot_date"
        }
    ).sort_values("snapshot_date")

    merged = pd.merge_asof(
        episodes.sort_values("peak_date"),
        peak_snapshots,
        left_on="peak_date",
        right_on="snapshot_date",
        direction="backward",
    )
    return merged.drop(columns=["snapshot_date"], errors="ignore").sort_values("onset_date").reset_index(drop=True)


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


def build_size_bucket_effect_summary(episodes: pd.DataFrame) -> pd.DataFrame:
    if episodes.empty:
        return pd.DataFrame()

    analysis_frame = episodes.copy()
    if {
        "pre_drawdown_large_cap_cap_weighted_surprise_pct",
        "pre_drawdown_small_cap_cap_weighted_surprise_pct",
    }.issubset(analysis_frame.columns):
        analysis_frame["pre_drawdown_large_minus_small_surprise_pct"] = (
            pd.to_numeric(analysis_frame["pre_drawdown_large_cap_cap_weighted_surprise_pct"], errors="coerce")
            - pd.to_numeric(analysis_frame["pre_drawdown_small_cap_cap_weighted_surprise_pct"], errors="coerce")
        )
    if {
        "pre_drawdown_large_cap_cap_weighted_quarterly_eps_yoy_pct",
        "pre_drawdown_small_cap_cap_weighted_quarterly_eps_yoy_pct",
    }.issubset(analysis_frame.columns):
        analysis_frame["pre_drawdown_large_minus_small_eps_yoy_pct"] = (
            pd.to_numeric(
                analysis_frame["pre_drawdown_large_cap_cap_weighted_quarterly_eps_yoy_pct"],
                errors="coerce",
            )
            - pd.to_numeric(
                analysis_frame["pre_drawdown_small_cap_cap_weighted_quarterly_eps_yoy_pct"],
                errors="coerce",
            )
        )

    factor_columns = [
        column
        for column in [
            "pre_drawdown_small_cap_cap_weighted_surprise_pct",
            "pre_drawdown_mid_cap_cap_weighted_surprise_pct",
            "pre_drawdown_large_cap_cap_weighted_surprise_pct",
            "pre_drawdown_small_cap_cap_weighted_quarterly_eps_yoy_pct",
            "pre_drawdown_mid_cap_cap_weighted_quarterly_eps_yoy_pct",
            "pre_drawdown_large_cap_cap_weighted_quarterly_eps_yoy_pct",
            "pre_drawdown_large_minus_small_surprise_pct",
            "pre_drawdown_large_minus_small_eps_yoy_pct",
        ]
        if column in analysis_frame.columns
    ]
    outcome_columns = [
        "max_drawdown_abs",
        "drawdown_speed_from_peak_per_day",
        "trough_to_20d_return",
        "trough_to_60d_return",
        "recovered_within_60d",
    ]
    rows: list[dict[str, Any]] = []
    for factor_name in factor_columns:
        pair = analysis_frame[[factor_name, *outcome_columns]].dropna(subset=[factor_name])
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


def _label_hmm_state(stats: pd.Series) -> str:
    mean_market_strength = _safe_float(stats.get("market_strength_score"))
    mean_fragility = _safe_float(stats.get("macro_fragility_score"))
    mean_panic = _safe_float(stats.get("panic_score"))
    mean_vix_pace = _safe_float(stats.get("vix_pace_score"))
    mean_credit_pace = _safe_float(stats.get("credit_pace_score"))

    if (
        (mean_panic is not None and mean_panic >= 0.80)
        or (mean_fragility is not None and mean_fragility >= 0.45)
        or (mean_vix_pace is not None and mean_vix_pace >= 1.10)
    ):
        return "Stress Breakdown"
    if (
        (mean_market_strength is not None and mean_market_strength >= 0.45)
        and (mean_vix_pace is not None and mean_vix_pace >= 0.40)
        and (mean_fragility is None or mean_fragility < 0.35)
    ):
        return "Shock Repricing"
    if (
        (mean_market_strength is not None and mean_market_strength >= 0.40)
        and (mean_fragility is None or mean_fragility <= 0.10)
        and (mean_panic is None or mean_panic <= 0.20)
    ):
        return "Calm Trend"
    if (
        (mean_market_strength is not None and mean_market_strength <= 0.25)
        or (mean_fragility is not None and mean_fragility >= 0.15)
        or (mean_credit_pace is not None and mean_credit_pace >= 0.35)
    ):
        return "Fragile Grind"
    return "Transition"


def build_online_hmm_episode_states(
    panel: pd.DataFrame,
    episodes: pd.DataFrame,
    *,
    feature_columns: tuple[str, ...] = HMM_FEATURE_COLUMNS,
    n_components: int = 4,
    min_train_rows: int = 756,
    random_state: int = 42,
) -> pd.DataFrame:
    if panel.empty or episodes.empty:
        return pd.DataFrame()

    feature_columns = tuple(column for column in feature_columns if column in panel.columns)
    if not feature_columns:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for episode in episodes.itertuples(index=False):
        peak_date = pd.Timestamp(episode.peak_date)
        history = panel.loc[panel.index <= peak_date, list(feature_columns)].copy()
        history = history.dropna()
        if len(history) < min_train_rows:
            continue

        mean = history.mean(numeric_only=True)
        std = history.std(ddof=0, numeric_only=True).replace(0.0, np.nan)
        normalized = ((history - mean) / std).replace([np.inf, -np.inf], np.nan).dropna()
        if len(normalized) < min_train_rows:
            continue

        aligned_raw = history.loc[normalized.index].copy()
        model = GaussianHMM(
            n_components=n_components,
            covariance_type="full",
            n_iter=250,
            random_state=random_state,
        )
        try:
            model.fit(normalized.to_numpy())
            hidden_states = model.predict(normalized.to_numpy())
            state_probabilities = model.predict_proba(normalized.to_numpy())[-1]
        except Exception:
            continue

        aligned_raw["hidden_state"] = hidden_states
        current_state = int(hidden_states[-1])
        current_stats = aligned_raw.groupby("hidden_state")[list(feature_columns)].mean().loc[current_state]
        label = _label_hmm_state(current_stats)
        row: dict[str, Any] = {
            "episode_id": int(episode.episode_id),
            "peak_date": peak_date,
            "hidden_state": current_state,
            "hidden_state_label": label,
            "hidden_state_confidence": float(np.max(state_probabilities)),
            "training_rows": int(len(normalized)),
        }
        for feature_name in feature_columns:
            row[f"state_mean_{feature_name}"] = _safe_float(current_stats.get(feature_name))
        for state_index, probability in enumerate(state_probabilities):
            row[f"hidden_state_prob_{state_index}"] = float(probability)
        rows.append(row)

    return pd.DataFrame(rows).sort_values("peak_date").reset_index(drop=True)


def build_hmm_comparison_outputs(episodes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if episodes.empty or "hidden_state_label" not in episodes.columns:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    state_summary = (
        episodes.groupby("hidden_state_label", as_index=False)
        .agg(
            episode_count=("episode_id", "count"),
            avg_max_drawdown=("max_drawdown", "mean"),
            avg_peak_to_trough_days=("peak_to_trough_days", "mean"),
            avg_drawdown_speed=("drawdown_speed_from_peak_per_day", "mean"),
            avg_trough_to_20d_return=("trough_to_20d_return", "mean"),
            avg_trough_to_60d_return=("trough_to_60d_return", "mean"),
            recovered_within_60d_rate=("recovered_within_60d", "mean"),
            avg_hidden_state_confidence=("hidden_state_confidence", "mean"),
        )
        .sort_values(["episode_count", "avg_max_drawdown"], ascending=[False, True])
        .reset_index(drop=True)
    )

    rules_crosstab = (
        episodes.groupby(["hidden_state_label", "pre_drawdown_market_strength_regime"], as_index=False)
        .agg(episode_count=("episode_id", "count"))
        .sort_values(["hidden_state_label", "episode_count"], ascending=[True, False])
        .reset_index(drop=True)
    )

    combined_crosstab = (
        episodes.groupby(["hidden_state_label", "pre_drawdown_combined_regime"], as_index=False)
        .agg(episode_count=("episode_id", "count"))
        .sort_values(["hidden_state_label", "episode_count"], ascending=[True, False])
        .reset_index(drop=True)
    )
    return state_summary, rules_crosstab, combined_crosstab


def _overlay_regime_label(row: pd.Series) -> str:
    strength_regime = str(row.get("pre_drawdown_market_strength_regime") or "")
    instability_regime = str(row.get("pre_drawdown_instability_regime") or "")
    hidden_state_label = str(row.get("hidden_state_label") or "")
    if (
        strength_regime == "Weak"
        or instability_regime in {"Fragile", "Stress"}
        or hidden_state_label in {"Fragile Grind", "Stress Breakdown"}
    ):
        return "WEAK_FRAGILE"
    if strength_regime == "Strong" or hidden_state_label in {"Calm Trend", "Shock Repricing"}:
        return "STRONG_SHOCK"
    return "TRANSITION"


def build_overlay_episode_features(episodes: pd.DataFrame) -> pd.DataFrame:
    if episodes.empty:
        return pd.DataFrame()

    frame = episodes.copy()
    if {
        "pre_drawdown_large_cap_cap_weighted_surprise_pct",
        "pre_drawdown_small_cap_cap_weighted_surprise_pct",
    }.issubset(frame.columns):
        frame["pre_drawdown_large_minus_small_surprise_pct"] = (
            pd.to_numeric(frame["pre_drawdown_large_cap_cap_weighted_surprise_pct"], errors="coerce")
            - pd.to_numeric(frame["pre_drawdown_small_cap_cap_weighted_surprise_pct"], errors="coerce")
        )
    if {
        "pre_drawdown_large_cap_cap_weighted_quarterly_eps_yoy_pct",
        "pre_drawdown_small_cap_cap_weighted_quarterly_eps_yoy_pct",
    }.issubset(frame.columns):
        frame["pre_drawdown_large_minus_small_eps_yoy_pct"] = (
            pd.to_numeric(
                frame["pre_drawdown_large_cap_cap_weighted_quarterly_eps_yoy_pct"],
                errors="coerce",
            )
            - pd.to_numeric(
                frame["pre_drawdown_small_cap_cap_weighted_quarterly_eps_yoy_pct"],
                errors="coerce",
            )
        )
    frame["overlay_regime"] = frame.apply(_overlay_regime_label, axis=1)
    frame["size_earnings_signal"] = pd.DataFrame(
        {
            "surprise_spread": pd.to_numeric(frame.get("pre_drawdown_large_minus_small_surprise_pct"), errors="coerce"),
            "eps_growth_spread": pd.to_numeric(frame.get("pre_drawdown_large_minus_small_eps_yoy_pct"), errors="coerce"),
        },
        index=frame.index,
    ).mean(axis=1)
    return frame


def build_sector_overlay_training_frame(
    sector_episode_ratios: pd.DataFrame,
    episodes: pd.DataFrame,
    *,
    sector_panel: pd.DataFrame | None = None,
    spy_close: pd.Series | None = None,
) -> pd.DataFrame:
    if sector_episode_ratios.empty or episodes.empty:
        return pd.DataFrame()

    episode_features = build_overlay_episode_features(episodes)
    merge_columns = [
        "episode_id",
        "overlay_regime",
        "hidden_state_label",
        "hidden_state_confidence",
        "vix_pace_score",
        "credit_pace_score",
        "pre_drawdown_market_strength_regime",
        "pre_drawdown_instability_regime",
        "pre_drawdown_large_minus_small_surprise_pct",
        "pre_drawdown_large_minus_small_eps_yoy_pct",
        "size_earnings_signal",
    ] + [column for column in episode_features.columns if column.startswith("hidden_state_prob_")]
    merge_columns = [column for column in merge_columns if column in episode_features.columns]
    overlay_frame = sector_episode_ratios.merge(
        episode_features[merge_columns],
        on="episode_id",
        how="left",
    )
    overlay_frame["overlay_target_score"] = (
        pd.to_numeric(overlay_frame["recovery_ratio_vs_spy"], errors="coerce").fillna(0.0)
        - pd.to_numeric(overlay_frame["sector_window_drawdown_ratio"], errors="coerce").fillna(0.0)
    )
    overlay_frame["defensive_target"] = (
        pd.to_numeric(overlay_frame["sector_window_drawdown_ratio"], errors="coerce") < 1.0
    ).astype(int)
    overlay_frame["recovery_target"] = (
        pd.to_numeric(overlay_frame["recovery_ratio_vs_spy"], errors="coerce") > 1.0
    ).astype(int)
    if sector_panel is not None and spy_close is not None and not sector_panel.empty:
        overlay_frame = _attach_overlay_horizon_returns(
            overlay_frame,
            sector_panel=sector_panel,
            spy_close=spy_close,
        )
        overlay_frame["overlay_target_score"] = pd.to_numeric(
            overlay_frame["overlay_excess_return_target"], errors="coerce"
        ).fillna(pd.to_numeric(overlay_frame["overlay_target_score"], errors="coerce"))
    return overlay_frame.sort_values(["episode_id", "sector"]).reset_index(drop=True)


def _attach_overlay_horizon_returns(
    overlay_frame: pd.DataFrame,
    *,
    sector_panel: pd.DataFrame,
    spy_close: pd.Series,
) -> pd.DataFrame:
    if overlay_frame.empty or sector_panel.empty:
        return overlay_frame

    close_wide = sector_panel.pivot(index="date", columns="sector", values="sector_close").sort_index()
    spy_close = pd.to_numeric(spy_close, errors="coerce").sort_index()
    trading_index = pd.DatetimeIndex(spy_close.index).sort_values()

    exit_dates: list[pd.Timestamp | pd.NaT] = []
    hold_days_values: list[int] = []
    sector_returns: list[float | None] = []
    spy_returns: list[float | None] = []
    excess_returns: list[float | None] = []

    for row in overlay_frame.itertuples(index=False):
        hold_days = int(_overlay_hold_days(str(getattr(row, "overlay_regime", "TRANSITION"))))
        onset_date = pd.Timestamp(row.onset_date)
        if onset_date not in trading_index:
            onset_position = int(trading_index.searchsorted(onset_date))
            if onset_position >= len(trading_index):
                exit_dates.append(pd.NaT)
                hold_days_values.append(hold_days)
                sector_returns.append(None)
                spy_returns.append(None)
                excess_returns.append(None)
                continue
            onset_date = trading_index[onset_position]

        exit_date = _resolve_overlay_exit_date(
            trading_index,
            onset_date=onset_date,
            hold_days=hold_days,
        )
        exit_dates.append(exit_date)
        hold_days_values.append(hold_days)

        spy_entry = _safe_float(spy_close.loc[onset_date]) if onset_date in spy_close.index else None
        spy_exit = _safe_float(spy_close.loc[exit_date]) if exit_date in spy_close.index else None
        spy_return = None
        if spy_entry is not None and spy_exit is not None and spy_entry > 0.0:
            spy_return = float(spy_exit / spy_entry - 1.0)

        sector_return = _basket_return(
            close_wide,
            sectors=[row.sector],
            entry_date=onset_date,
            exit_date=exit_date,
        )
        sector_returns.append(sector_return)
        spy_returns.append(spy_return)
        if sector_return is None or spy_return is None:
            excess_returns.append(None)
        else:
            excess_returns.append(float(sector_return - spy_return))

    frame = overlay_frame.copy()
    frame["overlay_exit_date"] = exit_dates
    frame["overlay_hold_days"] = hold_days_values
    frame["overlay_sector_return_target"] = sector_returns
    frame["overlay_spy_return_target"] = spy_returns
    frame["overlay_excess_return_target"] = excess_returns
    return frame


def build_overlay_rule_book(overlay_frame: pd.DataFrame) -> pd.DataFrame:
    if overlay_frame.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    target_column = "overlay_excess_return_target" if "overlay_excess_return_target" in overlay_frame.columns else "overlay_target_score"
    for overlay_regime in ("WEAK_FRAGILE", "STRONG_SHOCK", "TRANSITION"):
        subset = overlay_frame.loc[overlay_frame["overlay_regime"] == overlay_regime].copy()
        if subset.empty:
            continue
        sector_stats = (
            subset.groupby("sector", as_index=True)
            .agg(
                observations=("episode_id", "count"),
                avg_window_drawdown_ratio=("sector_window_drawdown_ratio", "mean"),
                avg_recovery_ratio_vs_spy=("recovery_ratio_vs_spy", "mean"),
                avg_overlay_excess_return=(target_column, "mean"),
                avg_overlay_target_score=("overlay_target_score", "mean"),
            )
        )
        if overlay_regime == "WEAK_FRAGILE":
            defensive_pool = sector_stats.loc[sector_stats["avg_window_drawdown_ratio"] <= 1.05].copy()
            if defensive_pool.empty:
                defensive_pool = sector_stats.copy()
            defense = defensive_pool.sort_values(
                ["avg_overlay_excess_return", "avg_window_drawdown_ratio"],
                ascending=[False, True],
            ).head(2).copy()
            defense["selection_role"] = "defense"
            defense["rule_score"] = defense["avg_overlay_excess_return"] - 0.10 * defense["avg_window_drawdown_ratio"]
            quality = (
                sector_stats.drop(index=defense.index, errors="ignore")
                .sort_values(["avg_overlay_excess_return", "avg_recovery_ratio_vs_spy"], ascending=[False, False])
                .head(1)
                .copy()
            )
            quality["selection_role"] = "quality"
            quality["rule_score"] = quality["avg_overlay_excess_return"] + 0.05 * quality["avg_recovery_ratio_vs_spy"]
            selected = pd.concat([defense, quality], axis=0)
        elif overlay_regime == "STRONG_SHOCK":
            rebound = sector_stats.sort_values(
                ["avg_overlay_excess_return", "avg_recovery_ratio_vs_spy"],
                ascending=[False, False],
            ).head(2).copy()
            rebound["selection_role"] = "rebound"
            rebound["rule_score"] = rebound["avg_overlay_excess_return"] + 0.10 * rebound["avg_recovery_ratio_vs_spy"]
            cyclical = (
                sector_stats.drop(index=rebound.index, errors="ignore")
                .sort_values(["avg_overlay_excess_return", "avg_recovery_ratio_vs_spy"], ascending=[False, False])
                .head(1)
                .copy()
            )
            cyclical["selection_role"] = "cyclical"
            cyclical["rule_score"] = cyclical["avg_overlay_excess_return"] + 0.05 * cyclical["avg_recovery_ratio_vs_spy"]
            selected = pd.concat([rebound, cyclical], axis=0)
        else:
            selected = sector_stats.copy()
            selected["selection_role"] = "balanced"
            selected["rule_score"] = (
                selected["avg_overlay_excess_return"]
                + 0.10 * selected["avg_recovery_ratio_vs_spy"]
                - 0.05 * selected["avg_window_drawdown_ratio"]
            )
            selected = selected.sort_values(["rule_score", "avg_window_drawdown_ratio"], ascending=[False, True]).head(3)

        selected = selected.reset_index(names="sector")
        selected.insert(0, "overlay_regime", overlay_regime)
        rows.extend(selected.to_dict(orient="records"))
    return pd.DataFrame(rows)


def build_overlay_ml_predictions(
    overlay_frame: pd.DataFrame,
    *,
    min_train_episodes: int = 8,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if overlay_frame.empty:
        return pd.DataFrame(), pd.DataFrame()

    categorical_columns = [
        column
        for column in [
            "sector",
            "overlay_regime",
            "hidden_state_label",
            "stretch_bucket",
            "pre_drawdown_market_strength_regime",
        ]
        if column in overlay_frame.columns
    ]
    numeric_columns = [
        column
        for column in [
            "stretch_score",
            "ratio_to_spy_zscore_252d",
            "relative_return_63d",
            "vix_pace_score",
            "credit_pace_score",
            "hidden_state_confidence",
            "pre_drawdown_large_minus_small_surprise_pct",
            "pre_drawdown_large_minus_small_eps_yoy_pct",
            "size_earnings_signal",
        ]
        if column in overlay_frame.columns
    ] + [column for column in overlay_frame.columns if column.startswith("hidden_state_prob_")]

    feature_frame = overlay_frame[categorical_columns + numeric_columns].copy()
    feature_frame = pd.get_dummies(feature_frame, columns=categorical_columns, dummy_na=False).astype(float)
    predictions: list[pd.DataFrame] = []
    target_column = "overlay_excess_return_target" if "overlay_excess_return_target" in overlay_frame.columns else "overlay_target_score"

    episode_ids = sorted(int(value) for value in overlay_frame["episode_id"].dropna().unique())
    for episode_id in episode_ids:
        train_mask = overlay_frame["episode_id"] < episode_id
        test_mask = overlay_frame["episode_id"] == episode_id
        train_frame = overlay_frame.loc[train_mask]
        test_frame = overlay_frame.loc[test_mask]
        if train_frame["episode_id"].nunique() < min_train_episodes or test_frame.empty:
            continue
        if pd.to_numeric(train_frame[target_column], errors="coerce").dropna().empty:
            continue

        model = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("model", Ridge(alpha=1.0)),
            ]
        )
        model.fit(feature_frame.loc[train_mask], pd.to_numeric(train_frame[target_column], errors="coerce"))

        fold = test_frame[
            [
                "episode_id",
                "sector",
                "overlay_regime",
                target_column,
                "sector_window_drawdown_ratio",
                "recovery_ratio_vs_spy",
            ]
        ].copy()
        fold = fold.rename(columns={target_column: "overlay_target_score"})
        fold["ml_predicted_overlay_score"] = model.predict(feature_frame.loc[test_mask])
        predictions.append(fold)

    prediction_frame = pd.concat(predictions, ignore_index=True) if predictions else pd.DataFrame()
    if prediction_frame.empty:
        return prediction_frame, pd.DataFrame()

    top_ranked = (
        prediction_frame.sort_values(["episode_id", "ml_predicted_overlay_score"], ascending=[True, False])
        .groupby("episode_id", as_index=False)
        .head(3)
    )
    metric_frame = pd.DataFrame(
        [
            {
                "observations": int(len(prediction_frame)),
                "episode_count": int(prediction_frame["episode_id"].nunique()),
                "prediction_correlation": _safe_float(
                    prediction_frame["ml_predicted_overlay_score"].corr(prediction_frame["overlay_target_score"])
                ),
                "top3_mean_actual_overlay_score": _safe_float(top_ranked["overlay_target_score"].mean()),
                "top3_mean_drawdown_ratio": _safe_float(top_ranked["sector_window_drawdown_ratio"].mean()),
                "top3_mean_recovery_ratio_vs_spy": _safe_float(top_ranked["recovery_ratio_vs_spy"].mean()),
            }
        ]
    )
    return prediction_frame, metric_frame


def _overlay_hold_days(overlay_regime: str) -> int:
    if overlay_regime == "WEAK_FRAGILE":
        return 40
    if overlay_regime == "STRONG_SHOCK":
        return 15
    return 25


def _sector_overlay_weight(overlay_regime: str, size_signal: Any) -> float:
    numeric = _safe_float(size_signal)
    if overlay_regime == "WEAK_FRAGILE":
        return 0.25 if numeric is not None and numeric < 0.0 else 0.40
    if overlay_regime == "STRONG_SHOCK":
        return 0.50 if numeric is not None and numeric > 0.0 else 0.35
    return 0.35


def _resolve_overlay_exit_date(
    trading_index: pd.DatetimeIndex,
    *,
    onset_date: pd.Timestamp,
    hold_days: int,
) -> pd.Timestamp:
    entry_position = int(trading_index.searchsorted(onset_date))
    if entry_position >= len(trading_index):
        return trading_index[-1]
    target_position = min(entry_position + hold_days, len(trading_index) - 1)
    return trading_index[target_position]


def _basket_return(
    close_wide: pd.DataFrame,
    *,
    sectors: list[str],
    entry_date: pd.Timestamp,
    exit_date: pd.Timestamp,
) -> float | None:
    returns: list[float] = []
    for sector in sectors:
        if sector not in close_wide.columns or entry_date not in close_wide.index or exit_date not in close_wide.index:
            continue
        entry_price = _safe_float(close_wide.at[entry_date, sector])
        exit_price = _safe_float(close_wide.at[exit_date, sector])
        if entry_price is None or exit_price is None or entry_price <= 0.0:
            continue
        returns.append(float(exit_price / entry_price - 1.0))
    if not returns:
        return None
    return float(np.mean(returns))


def build_sector_tilt_overlay_backtest(
    *,
    episodes: pd.DataFrame,
    overlay_frame: pd.DataFrame,
    sector_panel: pd.DataFrame,
    spy_close: pd.Series,
    ml_predictions: pd.DataFrame,
) -> pd.DataFrame:
    if episodes.empty or overlay_frame.empty or sector_panel.empty:
        return pd.DataFrame()

    episode_features = build_overlay_episode_features(episodes)
    close_wide = sector_panel.pivot(index="date", columns="sector", values="sector_close").sort_index()
    trading_index = pd.DatetimeIndex(spy_close.index).sort_values()
    ml_lookup = (
        ml_predictions.set_index(["episode_id", "sector"]) if not ml_predictions.empty else pd.DataFrame()
    )

    rows: list[dict[str, Any]] = []
    for episode in episode_features.sort_values("episode_id").itertuples(index=False):
        training = overlay_frame.loc[overlay_frame["episode_id"] < int(episode.episode_id)].copy()
        if training["episode_id"].nunique() < 4:
            continue
        current = overlay_frame.loc[overlay_frame["episode_id"] == int(episode.episode_id)].copy()
        if current.empty:
            continue

        rule_book = build_overlay_rule_book(training)
        candidate_rows = rule_book.loc[rule_book["overlay_regime"] == episode.overlay_regime].copy()
        if candidate_rows.empty:
            candidate_rows = build_overlay_rule_book(overlay_frame)
            candidate_rows = candidate_rows.loc[candidate_rows["overlay_regime"] == episode.overlay_regime].copy()
        if candidate_rows.empty:
            continue

        candidate_rows["rule_rank"] = np.arange(1, len(candidate_rows) + 1)
        rule_sectors = candidate_rows["sector"].head(3).tolist()

        ml_sectors = rule_sectors.copy()
        if not ml_lookup.empty and int(episode.episode_id) in ml_predictions["episode_id"].values:
            ranked = current.copy()
            ranked["ml_predicted_overlay_score"] = ranked.apply(
                lambda row: _safe_float(
                    ml_lookup.at[(int(row["episode_id"]), row["sector"]), "ml_predicted_overlay_score"]
                )
                if (int(row["episode_id"]), row["sector"]) in ml_lookup.index
                else np.nan,
                axis=1,
            )
            ranked["rule_rank"] = ranked["sector"].map(dict(zip(candidate_rows["sector"], candidate_rows["rule_rank"]))).fillna(99)
            ranked = ranked.sort_values(
                ["ml_predicted_overlay_score", "rule_rank"],
                ascending=[False, True],
                na_position="last",
            )
            if not ranked.empty:
                ml_sectors = ranked["sector"].head(3).tolist()

        onset_date = pd.Timestamp(episode.onset_date)
        if onset_date not in trading_index:
            onset_position = int(trading_index.searchsorted(onset_date))
            if onset_position >= len(trading_index):
                continue
            onset_date = trading_index[onset_position]
        exit_date = _resolve_overlay_exit_date(
            trading_index,
            onset_date=onset_date,
            hold_days=_overlay_hold_days(str(episode.overlay_regime)),
        )
        if onset_date not in spy_close.index or exit_date not in spy_close.index:
            continue
        spy_entry = _safe_float(spy_close.loc[onset_date])
        spy_exit = _safe_float(spy_close.loc[exit_date])
        if spy_entry is None or spy_exit is None or spy_entry <= 0.0:
            continue

        rule_sector_return = _basket_return(close_wide, sectors=rule_sectors, entry_date=onset_date, exit_date=exit_date)
        ml_sector_return = _basket_return(close_wide, sectors=ml_sectors, entry_date=onset_date, exit_date=exit_date)
        if rule_sector_return is None:
            continue
        if ml_sector_return is None:
            ml_sector_return = rule_sector_return

        spy_return = float(spy_exit / spy_entry - 1.0)
        sector_weight = _sector_overlay_weight(str(episode.overlay_regime), episode.size_earnings_signal)
        rows.append(
            {
                "episode_id": int(episode.episode_id),
                "overlay_regime": episode.overlay_regime,
                "onset_date": onset_date,
                "exit_date": exit_date,
                "hold_days": int(_overlay_hold_days(str(episode.overlay_regime))),
                "sector_weight": sector_weight,
                "spy_weight": 1.0 - sector_weight,
                "size_earnings_signal": _safe_float(episode.size_earnings_signal),
                "rule_selected_sectors": ", ".join(rule_sectors),
                "ml_selected_sectors": ", ".join(ml_sectors),
                "rule_sector_basket_return": rule_sector_return,
                "ml_sector_basket_return": ml_sector_return,
                "spy_return": spy_return,
                "rule_overlay_return": (1.0 - sector_weight) * spy_return + sector_weight * rule_sector_return,
                "ml_overlay_return": (1.0 - sector_weight) * spy_return + sector_weight * ml_sector_return,
            }
        )
    return pd.DataFrame(rows).sort_values("onset_date").reset_index(drop=True)


def _overlay_strategy_summary(periods: pd.DataFrame, *, return_column: str, strategy_label: str) -> dict[str, Any]:
    if periods.empty or return_column not in periods.columns:
        return {
            "strategy_label": strategy_label,
            "episodes": 0,
            "total_return": 0.0,
            "cagr": None,
            "max_drawdown": 0.0,
            "hit_rate_vs_spy": None,
            "avg_excess_return": None,
        }

    returns = pd.to_numeric(periods[return_column], errors="coerce").dropna()
    if returns.empty:
        return {
            "strategy_label": strategy_label,
            "episodes": 0,
            "total_return": 0.0,
            "cagr": None,
            "max_drawdown": 0.0,
            "hit_rate_vs_spy": None,
            "avg_excess_return": None,
        }

    equity = (1.0 + returns).cumprod()
    total_return = float(equity.iloc[-1] - 1.0)
    drawdown = equity / equity.cummax() - 1.0
    total_days = float(
        periods.loc[returns.index, ["onset_date", "exit_date"]]
        .assign(days=lambda frame: (frame["exit_date"] - frame["onset_date"]).dt.days.clip(lower=1))
        ["days"]
        .sum()
    )
    years = max(total_days / 365.25, 0.25)
    cagr = float(equity.iloc[-1] ** (1.0 / years) - 1.0) if equity.iloc[-1] > 0.0 else None
    excess = pd.to_numeric(periods.loc[returns.index, return_column], errors="coerce") - pd.to_numeric(
        periods.loc[returns.index, "spy_return"], errors="coerce"
    )
    return {
        "strategy_label": strategy_label,
        "episodes": int(len(returns)),
        "total_return": total_return,
        "cagr": cagr,
        "max_drawdown": float(drawdown.min()) if not drawdown.empty else 0.0,
        "hit_rate_vs_spy": _safe_float((excess > 0.0).mean()),
        "avg_excess_return": _safe_float(excess.mean()),
    }


def build_sector_tilt_overlay_summary(periods: pd.DataFrame) -> pd.DataFrame:
    if periods.empty:
        return pd.DataFrame()
    rows = [
        _overlay_strategy_summary(periods, return_column="spy_return", strategy_label="SPY Benchmark"),
        _overlay_strategy_summary(periods, return_column="rule_overlay_return", strategy_label="Rule-Based Sector Tilt Overlay"),
        _overlay_strategy_summary(periods, return_column="ml_overlay_return", strategy_label="ML-Refined Sector Tilt Overlay"),
    ]
    return pd.DataFrame(rows)


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
    size_bucket_snapshots = build_size_bucket_earnings_snapshots(
        root=root,
        event_dates=pd.DatetimeIndex(episodes["peak_date"]) if not episodes.empty else pd.DatetimeIndex([]),
    )
    size_bucket_snapshots.to_csv(resolved_output_dir / "size_bucket_earnings_snapshots.csv", index=False)
    episodes = attach_size_bucket_earnings_to_episodes(
        episodes,
        size_bucket_snapshots=size_bucket_snapshots,
    )

    hmm_states = build_online_hmm_episode_states(panel, episodes)
    hmm_states.to_csv(resolved_output_dir / "hmm_episode_states.csv", index=False)
    if not hmm_states.empty:
        episodes = episodes.merge(hmm_states, on=["episode_id", "peak_date"], how="left")
    episodes.to_csv(resolved_output_dir / "spy_drawdown_episodes.csv", index=False)

    strength_summary, combined_summary = build_drawdown_regime_summary(episodes)
    strength_summary.to_csv(resolved_output_dir / "drawdown_strength_summary.csv", index=False)
    combined_summary.to_csv(resolved_output_dir / "drawdown_combined_regime_summary.csv", index=False)

    hypothesis_summary = build_hypothesis_test_summary(episodes)
    hypothesis_summary.to_csv(resolved_output_dir / "hypothesis_test_summary.csv", index=False)

    pace_summary = build_pace_factor_summary(episodes)
    pace_summary.to_csv(resolved_output_dir / "pace_factor_summary.csv", index=False)

    size_bucket_summary = build_size_bucket_effect_summary(episodes)
    size_bucket_summary.to_csv(resolved_output_dir / "size_bucket_effect_summary.csv", index=False)

    hmm_state_summary, hmm_rules_crosstab, hmm_combined_crosstab = build_hmm_comparison_outputs(episodes)
    hmm_state_summary.to_csv(resolved_output_dir / "hmm_state_summary.csv", index=False)
    hmm_rules_crosstab.to_csv(resolved_output_dir / "hmm_vs_rules_strength_crosstab.csv", index=False)
    hmm_combined_crosstab.to_csv(resolved_output_dir / "hmm_vs_rules_combined_crosstab.csv", index=False)

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

    overlay_frame = build_sector_overlay_training_frame(
        sector_episode_ratios,
        episodes,
        sector_panel=sector_panel,
        spy_close=pd.to_numeric(panel["spy_close"], errors="coerce"),
    )
    overlay_frame.to_csv(resolved_output_dir / "sector_tilt_overlay_training_frame.csv", index=False)

    overlay_rule_book = build_overlay_rule_book(overlay_frame)
    overlay_rule_book.to_csv(resolved_output_dir / "sector_tilt_overlay_rule_book.csv", index=False)

    overlay_ml_predictions, overlay_ml_metrics = build_overlay_ml_predictions(overlay_frame)
    overlay_ml_predictions.to_csv(resolved_output_dir / "sector_tilt_overlay_ml_predictions.csv", index=False)
    overlay_ml_metrics.to_csv(resolved_output_dir / "sector_tilt_overlay_ml_metrics.csv", index=False)

    overlay_periods = build_sector_tilt_overlay_backtest(
        episodes=episodes,
        overlay_frame=overlay_frame,
        sector_panel=sector_panel,
        spy_close=pd.to_numeric(panel["spy_close"], errors="coerce"),
        ml_predictions=overlay_ml_predictions,
    )
    overlay_periods.to_csv(resolved_output_dir / "sector_tilt_overlay_periods.csv", index=False)

    overlay_summary = build_sector_tilt_overlay_summary(overlay_periods)
    overlay_summary.to_csv(resolved_output_dir / "sector_tilt_overlay_summary.csv", index=False)

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
            "Large-minus-small earnings strength should help separate faster recoveries from persistent drawdowns.",
            "An online HMM should separate shock repricing from fragile breakdowns more cleanly than the rules-only split.",
        ],
        "worst_sector_regime_ratios": worst_sectors.to_dict(orient="records"),
        "best_sector_regime_ratios": strongest_sectors.to_dict(orient="records"),
        "overlay_rule_book": overlay_rule_book.to_dict(orient="records"),
        "overlay_strategy_summary": overlay_summary.to_dict(orient="records"),
        "overlay_ml_metrics": overlay_ml_metrics.to_dict(orient="records"),
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