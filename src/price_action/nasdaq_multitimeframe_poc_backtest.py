"""One-minute execution around causal 1/3/5-session composite POCs.

The study treats prior-session composite POCs as location and compares three
confirmation clocks: the one-minute cross, a second one-minute acceptance
close, and acceptance at the end of the current 15-minute auction block.  A
15-minute block becomes usable only when its final one-minute bar has closed.

POCs are OHLCV approximations that assign a bar's volume to typical price.
They are not CME price-at-volume, footprint order flow, or executable depth.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .data import resolve_project_root
from .nasdaq_poc_scaling_backtest import _equity_frame, _variant_summary
from .nasdaq_session_backtest import (
    DEFAULT_DATA,
    DEFAULT_EXECUTION,
    NasdaqExecutionCosts,
    NasdaqStrategyConfig,
    _complete_grid,
    _configure_plots,
    _markdown_table,
    add_indicators,
    build_ny_schedule,
    cost_sensitivity,
    load_execution_costs,
    load_nasdaq_bars,
    run_backtest,
    session_bootstrap,
    volume_profile_levels,
)


DEFAULT_OUTPUT = Path("outputs/nasdaq_multitimeframe_poc_backtest")


@dataclass(frozen=True)
class MultiTimeframePocConfig:
    profile_rows: int = 64
    profile_value_fraction: float = 0.70
    poc_zone_half_width_daily_atr: float = 0.025
    poc_cluster_distance_daily_atr: float = 0.05
    daily_atr_sessions: int = 14
    fifteen_minute_reference_blocks: int = 20

    def __post_init__(self) -> None:
        if self.profile_rows < 16:
            raise ValueError("Composite profiles require at least 16 rows")
        if not 0.0 < self.profile_value_fraction < 1.0:
            raise ValueError("Value fraction must be inside (0, 1)")
        if not 0.0 < self.poc_zone_half_width_daily_atr < 0.25:
            raise ValueError("POC zone width must be inside (0, 0.25 daily ATR)")
        if self.poc_cluster_distance_daily_atr < 2.0 * self.poc_zone_half_width_daily_atr:
            raise ValueError("Cluster distance must span at least two POC half-widths")


def _profile(history: pd.DataFrame, config: MultiTimeframePocConfig) -> tuple[float, float, float]:
    return volume_profile_levels(
        history,
        rows=config.profile_rows,
        value_fraction=config.profile_value_fraction,
    )


def build_composite_poc_context(
    bars: pd.DataFrame,
    schedule: pd.DataFrame,
    config: MultiTimeframePocConfig,
) -> pd.DataFrame:
    """Build 1/3/5-session profiles strictly from completed prior RTH sessions."""
    completed: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for session in schedule.itertuples(index=False):
        prior_ranges = [float(item["range"]) for item in completed]
        prior_atr = (
            float(np.mean(prior_ranges[-config.daily_atr_sessions:]))
            if prior_ranges
            else np.nan
        )
        payload: dict[str, Any] = {
            "session_date": str(session.session_date),
            "session_open": pd.Timestamp(session.session_open),
            "session_close": pd.Timestamp(session.session_close),
            "prior_daily_atr": prior_atr,
            "available_prior_sessions": len(completed),
        }
        for window in (1, 3, 5):
            if len(completed) < window:
                poc, val, vah = np.nan, np.nan, np.nan
            else:
                history = pd.concat(
                    [item["bars"] for item in completed[-window:]],
                    axis=0,
                )
                poc, val, vah = _profile(history, config)
            payload[f"composite_poc_{window}d"] = poc
            payload[f"composite_val_{window}d"] = val
            payload[f"composite_vah_{window}d"] = vah
        individual = [float(item["poc"]) for item in completed[-3:]]
        migration = 0
        if len(individual) == 3:
            if individual[0] < individual[1] < individual[2]:
                migration = 1
            elif individual[0] > individual[1] > individual[2]:
                migration = -1
        payload["individual_poc_migration_3d"] = migration
        rows.append(payload)

        session_open = pd.Timestamp(session.session_open)
        session_close = pd.Timestamp(session.session_close)
        rth = bars.loc[(bars.index >= session_open) & (bars.index < session_close)]
        if not _complete_grid(bars, session_open, session_close, pd.Timedelta(minutes=1)):
            continue
        poc, _, _ = _profile(rth, config)
        if np.isfinite(poc):
            completed.append({
                "session_date": str(session.session_date),
                "bars": rth[["open", "high", "low", "close", "volume"]].copy(),
                "poc": float(poc),
                "range": float(rth["high"].max() - rth["low"].min()),
            })
    return pd.DataFrame(rows)


def build_fifteen_minute_blocks(
    bars: pd.DataFrame,
    schedule: pd.DataFrame,
    config: MultiTimeframePocConfig,
) -> pd.DataFrame:
    """Summarize complete RTH 15-minute blocks with causal impulse labels."""
    blocks: list[dict[str, Any]] = []
    reference_ranges: list[float] = []
    reference_volumes: list[float] = []
    for session in schedule.itertuples(index=False):
        session_open = pd.Timestamp(session.session_open)
        session_close = pd.Timestamp(session.session_close)
        rth = bars.loc[(bars.index >= session_open) & (bars.index < session_close)]
        if len(rth) != 390:
            continue
        previous_poc = np.nan
        for block_number in range(26):
            block = rth.iloc[block_number * 15:(block_number + 1) * 15]
            if len(block) != 15:
                continue
            block_open = float(block["open"].iloc[0])
            block_close = float(block["close"].iloc[-1])
            block_high = float(block["high"].max())
            block_low = float(block["low"].min())
            block_range = block_high - block_low
            block_volume = float(block["volume"].sum())
            close_location = (block_close - block_low) / block_range if block_range > 0.0 else 0.5
            side = 1 if block_close > block_open else -1 if block_close < block_open else 0
            prior_range = (
                float(np.median(reference_ranges[-config.fifteen_minute_reference_blocks:]))
                if reference_ranges
                else np.nan
            )
            prior_volume = (
                float(np.median(reference_volumes[-config.fifteen_minute_reference_blocks:]))
                if reference_volumes
                else np.nan
            )
            poc, val, vah = _profile(block, config)
            poc_migration_side = (
                1 if np.isfinite(previous_poc) and poc > previous_poc
                else -1 if np.isfinite(previous_poc) and poc < previous_poc
                else 0
            )
            edge_aligned = close_location >= 0.70 if side > 0 else close_location <= 0.30
            impulse_side = (
                side
                if side != 0
                and np.isfinite(prior_range)
                and np.isfinite(prior_volume)
                and block_range > prior_range
                and block_volume > prior_volume
                and edge_aligned
                else 0
            )
            blocks.append({
                "session_date": str(session.session_date),
                "block_number": block_number,
                "block_start": block.index[0],
                "block_end_bar": block.index[-1],
                "open": block_open,
                "high": block_high,
                "low": block_low,
                "close": block_close,
                "volume": block_volume,
                "range": block_range,
                "close_location": close_location,
                "side": side,
                "impulse_side": impulse_side,
                "poc": poc,
                "val": val,
                "vah": vah,
                "poc_migration_side": poc_migration_side,
                "prior_median_range": prior_range,
                "prior_median_volume": prior_volume,
            })
            reference_ranges.append(block_range)
            reference_volumes.append(block_volume)
            previous_poc = poc
    return pd.DataFrame(blocks)


def _completed_block(
    blocks: pd.DataFrame,
    session_date: str,
    block_number: int,
    include_current: bool,
) -> pd.Series | None:
    completed_number = block_number if include_current else block_number - 1
    match = blocks.loc[
        blocks["session_date"].eq(session_date)
        & blocks["block_number"].eq(completed_number)
    ]
    return match.iloc[0] if len(match) else None


def _forward_payload(
    bars: pd.DataFrame,
    anchor_id: int,
    side: int,
    session_close: pd.Timestamp,
) -> dict[str, float] | None:
    payload: dict[str, float] = {}
    anchor_close = float(bars.iloc[anchor_id]["close"])
    for minutes in (1, 2, 5, 10, 15):
        future_id = anchor_id + minutes
        if future_id >= len(bars):
            return None
        future_time = pd.Timestamp(bars.index[future_id])
        if future_time != pd.Timestamp(bars.index[anchor_id]) + pd.Timedelta(minutes=minutes):
            return None
        if future_time >= session_close:
            return None
        future_close = float(bars.iloc[future_id]["close"])
        payload[f"forward_{minutes}m_bps"] = side * (future_close / anchor_close - 1.0) * 10_000.0
    return payload


def _timing_bucket(minutes_from_open: int) -> str:
    if minutes_from_open < 30:
        return "opening_0_30m"
    if minutes_from_open < 60:
        return "opening_30_60m"
    if minutes_from_open < 180:
        return "morning_60_180m"
    if minutes_from_open < 330:
        return "midday_180_330m"
    return "closing_330_390m"


def build_poc_signal_observations(
    indicated: pd.DataFrame,
    schedule: pd.DataFrame,
    daily_context: pd.DataFrame,
    blocks: pd.DataFrame,
    config: MultiTimeframePocConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create raw crosses plus causal 1-minute and 15-minute confirmations."""
    raw_events: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    context_lookup = daily_context.set_index("session_date")
    for session in schedule.itertuples(index=False):
        session_date = str(session.session_date)
        if session_date not in context_lookup.index:
            continue
        context = context_lookup.loc[session_date]
        if int(context["available_prior_sessions"]) < 5:
            continue
        daily_atr = float(context["prior_daily_atr"])
        if not np.isfinite(daily_atr) or daily_atr <= 0.0:
            continue
        levels = {
            f"{window}d": float(context[f"composite_poc_{window}d"])
            for window in (1, 3, 5)
        }
        if not all(np.isfinite(value) for value in levels.values()):
            continue
        zone_half_width = daily_atr * config.poc_zone_half_width_daily_atr
        cluster_distance = daily_atr * config.poc_cluster_distance_daily_atr
        session_open = pd.Timestamp(session.session_open)
        session_close = pd.Timestamp(session.session_close)
        rth = indicated.loc[(indicated.index >= session_open) & (indicated.index < session_close)].copy()
        if len(rth) != 390:
            continue
        typical = (rth["high"] + rth["low"] + rth["close"]) / 3.0
        cumulative_volume = rth["volume"].cumsum().replace(0.0, np.nan)
        rth["session_vwap"] = (typical * rth["volume"]).cumsum() / cumulative_volume
        for local_id in range(1, len(rth) - 15):
            previous = rth.iloc[local_id - 1]
            current = rth.iloc[local_id]
            previous_close = float(previous["close"])
            current_close = float(current["close"])
            if current_close == previous_close:
                continue
            side = 1 if current_close > previous_close else -1
            crossed_sources = []
            for source, level in levels.items():
                if side > 0 and previous_close <= level + zone_half_width < current_close:
                    crossed_sources.append(source)
                elif side < 0 and previous_close >= level - zone_half_width > current_close:
                    crossed_sources.append(source)
            if not crossed_sources:
                continue
            crossed_source = min(crossed_sources, key=lambda name: abs(levels[name] - current_close))
            crossed_level = levels[crossed_source]
            focus_sources = [
                name for name, level in levels.items()
                if abs(level - crossed_level) <= cluster_distance
            ]
            timestamp = pd.Timestamp(rth.index[local_id])
            minutes_from_open = int((timestamp - session_open) / pd.Timedelta(minutes=1))
            block_number = minutes_from_open // 15
            minute_in_block = minutes_from_open % 15
            base = {
                "raw_cross_time": timestamp,
                "raw_cross_bar_id": int(current["bar_id"]),
                "session_date": session_date,
                "session_open": session_open,
                "session_close": session_close,
                "side": side,
                "crossed_source": crossed_source,
                "crossed_sources": "+".join(sorted(crossed_sources)),
                "crossed_poc": crossed_level,
                "composite_poc_1d": levels["1d"],
                "composite_poc_3d": levels["3d"],
                "composite_poc_5d": levels["5d"],
                "focus_cluster_count": len(focus_sources),
                "focus_sources": "+".join(sorted(focus_sources)),
                "prior_daily_atr": daily_atr,
                "zone_half_width": zone_half_width,
                "individual_poc_migration_3d": int(context["individual_poc_migration_3d"]),
                "daily_poc_migration_aligned": int(context["individual_poc_migration_3d"]) == side,
                "minutes_from_open": minutes_from_open,
                "session_bucket": _timing_bucket(minutes_from_open),
                "block_number": block_number,
                "minute_in_15m_block": minute_in_block,
                "minute_in_15m_bucket": (
                    "early_0_4m" if minute_in_block < 5
                    else "middle_5_9m" if minute_in_block < 10
                    else "late_10_14m"
                ),
            }
            raw_events.append(base.copy())

            mode_anchors = [("one_minute_cross", local_id, False)]
            next_id = local_id + 1
            next_close = float(rth.iloc[next_id]["close"])
            next_vwap = float(rth.iloc[next_id]["session_vwap"])
            accepted_1m = (
                next_close > crossed_level + zone_half_width and next_close > next_vwap
                if side > 0
                else next_close < crossed_level - zone_half_width and next_close < next_vwap
            )
            if accepted_1m:
                mode_anchors.append(("one_minute_acceptance", next_id, False))

            block_end_local_id = min((block_number + 1) * 15 - 1, len(rth) - 1)
            block_end_close = float(rth.iloc[block_end_local_id]["close"])
            block_end_vwap = float(rth.iloc[block_end_local_id]["session_vwap"])
            accepted_15m = (
                block_end_close > crossed_level + zone_half_width and block_end_close > block_end_vwap
                if side > 0
                else block_end_close < crossed_level - zone_half_width and block_end_close < block_end_vwap
            )
            if accepted_15m and block_end_local_id > local_id:
                mode_anchors.append(("fifteen_minute_acceptance", block_end_local_id, True))

            for mode, anchor_local_id, include_current_block in mode_anchors:
                anchor = rth.iloc[anchor_local_id]
                anchor_id = int(anchor["bar_id"])
                forward = _forward_payload(indicated, anchor_id, side, session_close)
                if forward is None:
                    continue
                completed = _completed_block(
                    blocks,
                    session_date,
                    block_number,
                    include_current=include_current_block,
                )
                context_side = int(completed["side"]) if completed is not None else 0
                impulse_side = int(completed["impulse_side"]) if completed is not None else 0
                poc_migration_side = (
                    int(completed["poc_migration_side"]) if completed is not None else 0
                )
                anchor_vwap = float(rth.iloc[anchor_local_id]["session_vwap"])
                payload = base | {
                    "mode": mode,
                    "timestamp": pd.Timestamp(rth.index[anchor_local_id]),
                    "bar_id": anchor_id,
                    "close": float(anchor["close"]),
                    "atr": float(anchor["atr"]),
                    "session_vwap": anchor_vwap,
                    "vwap_aligned": (
                        float(anchor["close"]) > anchor_vwap
                        if side > 0 else float(anchor["close"]) < anchor_vwap
                    ),
                    "completed_15m_side": context_side,
                    "completed_15m_range": float(completed["range"]) if completed is not None else np.nan,
                    "completed_15m_direction_aligned": context_side == side,
                    "completed_15m_impulse_side": impulse_side,
                    "completed_15m_impulse_aligned": impulse_side == side,
                    "completed_15m_poc_migration_side": poc_migration_side,
                    "completed_15m_poc_migration_aligned": poc_migration_side == side,
                } | forward
                observations.append(payload)
    event_frame = pd.DataFrame(raw_events).drop_duplicates(
        subset=["raw_cross_time", "side"], keep="first"
    )
    observation_frame = pd.DataFrame(observations)
    if not observation_frame.empty:
        observation_frame = observation_frame.drop_duplicates(
            subset=["mode", "timestamp", "session_date", "side", "crossed_poc"],
            keep="first",
        ).sort_values("timestamp")
    return event_frame, observation_frame


def summarize_signal_observations(observations: pd.DataFrame) -> pd.DataFrame:
    if observations.empty:
        return pd.DataFrame()
    groups = {
        "1m_cross_all": observations["mode"].eq("one_minute_cross"),
        "1m_acceptance_all": observations["mode"].eq("one_minute_acceptance"),
        "15m_acceptance_all": observations["mode"].eq("fifteen_minute_acceptance"),
        "1m_acceptance_cross_1d": observations["mode"].eq("one_minute_acceptance") & observations["crossed_sources"].str.contains("1d"),
        "1m_acceptance_cross_3d": observations["mode"].eq("one_minute_acceptance") & observations["crossed_sources"].str.contains("3d"),
        "1m_acceptance_cross_5d": observations["mode"].eq("one_minute_acceptance") & observations["crossed_sources"].str.contains("5d"),
        "1m_acceptance_cross_3d_or_5d": observations["mode"].eq("one_minute_acceptance") & observations["crossed_sources"].str.contains("3d|5d", regex=True),
        "1m_acceptance_3d_or_5d_opening_0_30m": observations["mode"].eq("one_minute_acceptance") & observations["crossed_sources"].str.contains("3d|5d", regex=True) & observations["session_bucket"].eq("opening_0_30m"),
        "1m_acceptance_focus_cluster": observations["mode"].eq("one_minute_acceptance") & observations["focus_cluster_count"].ge(2),
        "1m_acceptance_15m_direction": observations["mode"].eq("one_minute_acceptance") & observations["completed_15m_direction_aligned"],
        "1m_acceptance_15m_impulse": observations["mode"].eq("one_minute_acceptance") & observations["completed_15m_impulse_aligned"],
        "1m_acceptance_15m_poc_migration": observations["mode"].eq("one_minute_acceptance") & observations["completed_15m_poc_migration_aligned"],
        "1m_focus_15m_direction_vwap": observations["mode"].eq("one_minute_acceptance") & observations["focus_cluster_count"].ge(2) & observations["completed_15m_direction_aligned"] & observations["vwap_aligned"],
        "15m_focus_direction_vwap": observations["mode"].eq("fifteen_minute_acceptance") & observations["focus_cluster_count"].ge(2) & observations["completed_15m_direction_aligned"] & observations["vwap_aligned"],
    }
    rng = np.random.default_rng(20260724)
    rows: list[dict[str, Any]] = []
    for group_name, mask in groups.items():
        frame = observations.loc[mask]
        daily = frame.groupby("session_date", sort=True)["forward_10m_bps"].mean()
        if len(daily):
            draws = rng.choice(
                daily.to_numpy(dtype=float),
                size=(5_000, len(daily)),
                replace=True,
            ).mean(axis=1)
        else:
            draws = np.asarray([], dtype=float)
        row: dict[str, Any] = {
            "group": group_name,
            "events": int(len(frame)),
            "sessions": int(frame["session_date"].nunique()),
            "bootstrap_10m_ci_low_bps": float(np.quantile(draws, 0.025)) if len(draws) else np.nan,
            "bootstrap_10m_ci_high_bps": float(np.quantile(draws, 0.975)) if len(draws) else np.nan,
            "bootstrap_probability_10m_positive": float((draws > 0.0).mean()) if len(draws) else np.nan,
        }
        for minutes in (1, 2, 5, 10, 15):
            values = frame[f"forward_{minutes}m_bps"]
            row[f"mean_forward_{minutes}m_bps"] = float(values.mean()) if len(values) else np.nan
            row[f"median_forward_{minutes}m_bps"] = float(values.median()) if len(values) else np.nan
            row[f"positive_forward_{minutes}m_share"] = float(values.gt(0.0).mean()) if len(values) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def timing_summary(observations: pd.DataFrame) -> pd.DataFrame:
    frame = observations.loc[observations["mode"].eq("one_minute_acceptance")].copy()
    rows: list[dict[str, Any]] = []
    dimensions = {
        "session_bucket": ("session_bucket", pd.Series(True, index=frame.index)),
        "minute_in_15m_bucket": ("minute_in_15m_bucket", pd.Series(True, index=frame.index)),
        "session_bucket_3d_or_5d": ("session_bucket", frame["crossed_sources"].str.contains("3d|5d", regex=True)),
        "minute_in_15m_bucket_3d_or_5d": ("minute_in_15m_bucket", frame["crossed_sources"].str.contains("3d|5d", regex=True)),
    }
    for dimension, (source_column, mask) in dimensions.items():
        for bucket, group in frame.loc[mask].groupby(source_column, sort=True):
            rows.append({
                "dimension": dimension,
                "bucket": str(bucket),
                "events": int(len(group)),
                "sessions": int(group["session_date"].nunique()),
                "focus_cluster_share": float(group["focus_cluster_count"].ge(2).mean()),
                "mean_forward_1m_bps": float(group["forward_1m_bps"].mean()),
                "mean_forward_5m_bps": float(group["forward_5m_bps"].mean()),
                "mean_forward_10m_bps": float(group["forward_10m_bps"].mean()),
                "mean_forward_15m_bps": float(group["forward_15m_bps"].mean()),
                "positive_forward_10m_share": float(group["forward_10m_bps"].gt(0.0).mean()),
            })
    return pd.DataFrame(rows)


def strategy_signal_sets(observations: pd.DataFrame) -> dict[str, pd.DataFrame]:
    masks = {
        "one_minute_cross": observations["mode"].eq("one_minute_cross"),
        "one_minute_acceptance": observations["mode"].eq("one_minute_acceptance"),
        "fifteen_minute_acceptance": observations["mode"].eq("fifteen_minute_acceptance"),
        "one_minute_focus_acceptance": observations["mode"].eq("one_minute_acceptance") & observations["focus_cluster_count"].ge(2),
        "one_minute_acceptance_3d": observations["mode"].eq("one_minute_acceptance") & observations["crossed_sources"].str.contains("3d"),
        "one_minute_acceptance_5d": observations["mode"].eq("one_minute_acceptance") & observations["crossed_sources"].str.contains("5d"),
        "one_minute_acceptance_3d_or_5d": observations["mode"].eq("one_minute_acceptance") & observations["crossed_sources"].str.contains("3d|5d", regex=True),
        "one_minute_acceptance_3d_or_5d_opening": observations["mode"].eq("one_minute_acceptance") & observations["crossed_sources"].str.contains("3d|5d", regex=True) & observations["session_bucket"].eq("opening_0_30m"),
        "one_minute_focus_15m": observations["mode"].eq("one_minute_acceptance") & observations["focus_cluster_count"].ge(2) & observations["completed_15m_direction_aligned"] & observations["vwap_aligned"],
        "fifteen_minute_focus_15m": observations["mode"].eq("fifteen_minute_acceptance") & observations["focus_cluster_count"].ge(2) & observations["completed_15m_direction_aligned"] & observations["vwap_aligned"],
    }
    outputs: dict[str, pd.DataFrame] = {}
    for name, mask in masks.items():
        frame = observations.loc[mask].copy()
        frame["signal_side"] = frame["side"].astype(int)
        frame["phase"] = "regular_session"
        frame["phase_end"] = frame["session_close"]
        frame["day_regime"] = np.where(
            frame["completed_15m_side"].gt(0),
            "completed_15m_up",
            np.where(frame["completed_15m_side"].lt(0), "completed_15m_down", "unclassified"),
        )
        frame["setup"] = name
        outputs[name] = frame
    structural_mask = (
        observations["mode"].eq("one_minute_acceptance")
        & observations["crossed_sources"].str.contains("3d|5d", regex=True)
        & observations["session_bucket"].eq("opening_0_30m")
        & observations["completed_15m_range"].notna()
    )
    for factor in (0.0, 0.25, 0.50, 0.75, 1.00):
        name = f"opening_3d5d_structural_stop_{factor:.2f}"
        frame = observations.loc[structural_mask].copy()
        frame["one_minute_atr"] = frame["atr"]
        frame["atr"] = np.maximum(
            frame["atr"].to_numpy(dtype=float),
            frame["completed_15m_range"].to_numpy(dtype=float) * factor,
        )
        frame["signal_side"] = frame["side"].astype(int)
        frame["phase"] = "regular_session"
        frame["phase_end"] = frame["session_close"]
        frame["day_regime"] = np.where(
            frame["completed_15m_side"].gt(0),
            "completed_15m_up",
            np.where(frame["completed_15m_side"].lt(0), "completed_15m_down", "unclassified"),
        )
        frame["setup"] = name
        outputs[name] = frame
    return outputs


def _plots(
    observations: pd.DataFrame,
    event_summary: pd.DataFrame,
    timing: pd.DataFrame,
    equity: pd.DataFrame,
    indicated: pd.DataFrame,
    output: Path,
) -> list[Path]:
    plt = _configure_plots()
    from matplotlib.ticker import PercentFormatter

    paths: list[Path] = []
    selected = [
        "1m_cross_all",
        "1m_acceptance_all",
        "15m_acceptance_all",
        "1m_acceptance_cross_3d_or_5d",
        "1m_acceptance_3d_or_5d_opening_0_30m",
        "15m_focus_direction_vwap",
    ]
    fig, ax = plt.subplots(figsize=(12, 6))
    for group in selected:
        row = event_summary.loc[event_summary["group"].eq(group)]
        if row.empty:
            continue
        values = [float(row[f"mean_forward_{minute}m_bps"].iloc[0]) for minute in (1, 2, 5, 10, 15)]
        ax.plot((1, 2, 5, 10, 15), values, marker="o", linewidth=2, label=f"{group} (n={int(row['events'].iloc[0])})")
    ax.axhline(0.0, color="#334155", linewidth=1)
    ax.set(title="One-minute versus completed 15-minute POC confirmation", xlabel="Minutes after causal signal", ylabel="Direction-aligned return (bps)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = output / "confirmation_clock_forward_returns.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)

    timing_order = {
        "session_bucket_3d_or_5d": ["opening_0_30m", "opening_30_60m", "morning_60_180m", "midday_180_330m", "closing_330_390m"],
        "minute_in_15m_bucket_3d_or_5d": ["early_0_4m", "middle_5_9m", "late_10_14m"],
    }
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for axis, dimension in zip(axes, timing_order, strict=True):
        frame = timing.loc[timing["dimension"].eq(dimension)].set_index("bucket")
        frame = frame.reindex(timing_order[dimension]).dropna(subset=["events"])
        axis.bar(frame.index, frame["mean_forward_10m_bps"], color="#2563eb")
        axis.axhline(0.0, color="#334155", linewidth=1)
        axis.set_title("Session segment" if dimension.startswith("session_bucket") else "Position inside 15-minute block")
        axis.set_ylabel("Mean next-10m return (bps)")
        axis.tick_params(axis="x", rotation=25)
        for index, (_, row) in enumerate(frame.iterrows()):
            axis.text(index, row["mean_forward_10m_bps"], f" n={int(row['events'])}", ha="center", va="bottom" if row["mean_forward_10m_bps"] >= 0 else "top", fontsize=8)
    fig.suptitle("Where does one-minute acceptance of a 3d/5d composite POC retain impact?")
    fig.tight_layout()
    path = output / "one_minute_acceptance_timing.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)

    focus_variants = [
        "1m_acceptance_10m",
        "1m_acceptance_3d_or_5d_opening_10m",
        "opening_3d5d_stop_0.25x_10m",
        "opening_3d5d_stop_0.50x_10m",
        "opening_3d5d_stop_0.75x_10m",
        "opening_3d5d_stop_1.00x_10m",
        "15m_focus_context_15m",
    ]
    variants = [
        variant for variant in focus_variants
        if not equity.empty and equity["variant"].eq(variant).any()
    ]
    colors = plt.cm.tab10(np.linspace(0, 1, max(len(variants), 1)))
    fig, axes = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
    for variant, color in zip(variants, colors, strict=False):
        frame = equity.loc[equity["variant"].eq(variant)]
        axes[0].plot(frame["exit_time"], frame["net_equity"] - 1.0, label=variant, color=color, linewidth=1.6)
        axes[1].plot(frame["exit_time"], frame["drawdown"], label=variant, color=color, linewidth=1.3)
    axes[0].set_title("One-minute composite-POC strategy return on equity")
    axes[0].yaxis.set_major_formatter(PercentFormatter(1.0))
    axes[1].set_title("Drawdown")
    axes[1].yaxis.set_major_formatter(PercentFormatter(1.0))
    axes[0].legend(fontsize=7, ncol=2)
    fig.tight_layout()
    path = output / "strategy_equity_and_drawdown.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)

    case_candidates = observations.loc[
        observations["mode"].eq("one_minute_acceptance")
        & observations["focus_cluster_count"].ge(2)
    ].copy()
    if len(case_candidates) >= 4:
        cases = pd.concat([
            case_candidates.nlargest(2, "forward_10m_bps"),
            case_candidates.nsmallest(2, "forward_10m_bps"),
        ]).drop_duplicates("timestamp")
        fig, axes = plt.subplots(len(cases), 1, figsize=(14, 3.5 * len(cases)), squeeze=False)
        for axis, event in zip(axes[:, 0], cases.itertuples(index=False), strict=True):
            timestamp = pd.Timestamp(event.timestamp)
            frame = indicated.loc[
                (indicated.index >= timestamp - pd.Timedelta(minutes=20))
                & (indicated.index <= timestamp + pd.Timedelta(minutes=20))
            ]
            axis.plot(frame.index, frame["close"], color="#2563eb", marker=".", linewidth=1.3, label="1m close")
            for window, color in zip((1, 3, 5), ("#dc2626", "#d97706", "#7c3aed"), strict=True):
                axis.axhline(getattr(event, f"composite_poc_{window}d"), color=color, linestyle="--", linewidth=1.1, label=f"prior {window}d composite POC")
            axis.axvline(timestamp, color="#0f766e", linewidth=1.5, label="1m acceptance")
            for boundary in pd.date_range(frame.index.min().ceil("15min"), frame.index.max(), freq="15min"):
                axis.axvline(boundary, color="#94a3b8", linewidth=0.6, alpha=0.5)
            axis.set_title(f"{event.session_date} {'long' if event.side > 0 else 'short'} | next 10m {event.forward_10m_bps:+.1f} bps | focus={event.focus_sources}")
            axis.legend(fontsize=7, ncol=3)
        fig.tight_layout()
        path = output / "one_minute_poc_case_studies.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        paths.append(path)
    return paths


def _report(
    event_summary: pd.DataFrame,
    timing: pd.DataFrame,
    strategy_summary: pd.DataFrame,
    bootstrap: pd.DataFrame,
    cost_audit: pd.DataFrame,
    governance: dict[str, Any],
) -> str:
    decision = strategy_summary.loc[strategy_summary["scope"].isin(["all", "development_2024", "holdout_2025"])]

    def event_value(group: str, column: str) -> float:
        match = event_summary.loc[event_summary["group"].eq(group), column]
        return float(match.iloc[0]) if len(match) else np.nan

    def timing_value(dimension: str, bucket: str, column: str) -> float:
        match = timing.loc[
            timing["dimension"].eq(dimension) & timing["bucket"].eq(bucket),
            column,
        ]
        return float(match.iloc[0]) if len(match) else np.nan

    def strategy_value(variant: str, scope: str, column: str) -> float:
        match = decision.loc[
            decision["variant"].eq(variant) & decision["scope"].eq(scope),
            column,
        ]
        return float(match.iloc[0]) if len(match) else np.nan

    structural_variant = "opening_3d5d_stop_0.75x_10m"
    return f"""# One-Minute / Fifteen-Minute Composite-POC Study

Generated {governance['generated_at_utc']}.

This study uses one-minute execution around POCs estimated from the previous 1, 3, and 5 complete regular sessions. It compares immediate one-minute crossing, a second one-minute acceptance close, and confirmation at a completed 15-minute auction close.

## Research conclusion

- Yesterday's isolated POC did not retain directional continuation after one-minute acceptance: its mean next-10-minute return was {event_value('1m_acceptance_cross_1d', 'mean_forward_10m_bps'):+.2f} bps. The 3-session and 5-session composite POCs were stronger at {event_value('1m_acceptance_cross_3d', 'mean_forward_10m_bps'):+.2f} and {event_value('1m_acceptance_cross_5d', 'mean_forward_10m_bps'):+.2f} bps. This supports treating several days of accepted value as the focus area rather than anchoring only to yesterday.
- Session timing mattered more than the minute's position inside its 15-minute block. Accepted 3d/5d crosses averaged {timing_value('session_bucket_3d_or_5d', 'opening_0_30m', 'mean_forward_10m_bps'):+.2f} bps during the opening 30 minutes, {timing_value('session_bucket_3d_or_5d', 'opening_30_60m', 'mean_forward_10m_bps'):+.2f} bps during minutes 30–60, and {timing_value('session_bucket_3d_or_5d', 'closing_330_390m', 'mean_forward_10m_bps'):+.2f} bps in the final hour. Within a 15-minute block, early/middle/late signals averaged {timing_value('minute_in_15m_bucket_3d_or_5d', 'early_0_4m', 'mean_forward_10m_bps'):+.2f}, {timing_value('minute_in_15m_bucket_3d_or_5d', 'middle_5_9m', 'mean_forward_10m_bps'):+.2f}, and {timing_value('minute_in_15m_bucket_3d_or_5d', 'late_10_14m', 'mean_forward_10m_bps'):+.2f} bps—no clean monotonic decay.
- A blanket “follow the previous 15-minute candle” rule did not help. One-minute focus acceptance plus completed-15-minute direction averaged only {event_value('1m_focus_15m_direction_vwap', 'mean_forward_10m_bps'):+.2f} bps. Waiting for the current 15-minute block itself to close accepted was better at {event_value('15m_focus_direction_vwap', 'mean_forward_10m_bps'):+.2f} bps, but delays the entry and remains a small, selected subgroup.
- The raw one-minute ATR stop was the main execution weakness. On accepted 3d/5d crosses during minutes 15–30, it produced {strategy_value('opening_3d5d_stop_0.00x_10m', 'all', 'cumulative_net_return'):.2%} net. Requiring stop distance of at least 0.50, 0.75, or 1.00 times the preceding completed 15-minute range produced {strategy_value('opening_3d5d_stop_0.50x_10m', 'all', 'cumulative_net_return'):.2%}, {strategy_value(structural_variant, 'all', 'cumulative_net_return'):.2%}, and {strategy_value('opening_3d5d_stop_1.00x_10m', 'all', 'cumulative_net_return'):.2%}. The 0.75x result used only {int(strategy_value(structural_variant, 'all', 'trades'))} trades, returned {strategy_value(structural_variant, 'holdout_2025', 'cumulative_net_return'):.2%} in 2025, and had {strategy_value(structural_variant, 'all', 'max_drawdown'):.2%} full-sample drawdown.
- This stop-width sweep is adaptive evidence, not a validated optimum. The 0.75x session-bootstrap 95% interval still crosses zero, and its break-even one-way cost is only {strategy_value(structural_variant, 'all', 'break_even_one_way_cost_bps'):.2f} bps. It belongs in forward paper testing.

## Forward-return event study

{_markdown_table(event_summary, rows=40)}

## One-minute timing inside the session and 15-minute block

{_markdown_table(timing, rows=40)}

## Leveraged strategy results

{_markdown_table(decision, rows=80)}

## Session bootstrap

{_markdown_table(bootstrap, rows=40)}

## 2025 cost sensitivity

{_markdown_table(cost_audit, rows=80)}

## Plots

- [Confirmation-clock forward returns](confirmation_clock_forward_returns.png)
- [One-minute acceptance timing](one_minute_acceptance_timing.png)
- [Strategy return curves and drawdowns](strategy_equity_and_drawdown.png)
- [One-minute POC case studies](one_minute_poc_case_studies.png)

## Causal contract

- Each 1d/3d/5d composite profile contains only complete sessions before the current session.
- A POC focus cluster means at least two composite POCs lie within {governance['research_config']['poc_cluster_distance_daily_atr']:.3f} prior daily ATR of the crossed POC.
- The POC zone half-width is {governance['research_config']['poc_zone_half_width_daily_atr']:.3f} prior daily ATR; these width choices are research assumptions, not fitted support/resistance facts.
- One-minute acceptance requires the next completed close to remain outside the POC band and on the directional side of session VWAP.
- Fifteen-minute acceptance is timestamped only on the block's final one-minute close. Entry is the following minute, so no unfinished 15-minute information is used.
- Completed 15-minute impulse requires above-median range and volume, plus a close in the directional 30% of the bar. Its references use prior complete blocks only.
- Trades enter on the next one-minute open, risk at most 1% at a one-minute ATR stop, are capped at 10x, target 2R, resolve same-bar ambiguity to the stop, and stop after three net losses in a session.
- The structural-stop sensitivity uses the larger of one-minute ATR and 0.00/0.25/0.50/0.75/1.00 times the previous completed 15-minute range. It applies only after that 15-minute bar is complete and is reported as an adaptive sweep.

## Limitations

- POC is approximated by assigning each one-minute bar's full volume to typical price. This is not true price-at-volume or order flow.
- Reusing 2024–2025 for multiple filters makes every subgroup exploratory; 2025 is no longer an untouched holdout.
- One-minute OHLC does not reveal whether the stop or target traded first, queue position, spreads, partial fills, or market impact. Stop-first resolution is conservative, but does not reconstruct the path.
- The instrument and venue are unverified and the price grid is inconsistent with CME NQ. The {governance['execution']['one_way_cost_bps']:.2f}-bps one-way cost remains a scenario.
"""


def build_multitimeframe_poc_backtest(
    project_root: str | Path | None = None,
    *,
    data_path: str | Path = DEFAULT_DATA,
    execution_path: str | Path = DEFAULT_EXECUTION,
    output_dir: str | Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    data_file = Path(data_path)
    execution_file = Path(execution_path)
    output = Path(output_dir)
    if not data_file.is_absolute():
        data_file = root / data_file
    if not execution_file.is_absolute():
        execution_file = root / execution_file
    if not output.is_absolute():
        output = root / output
    output.mkdir(parents=True, exist_ok=True)
    trade_output = output / "trades"
    trade_output.mkdir(parents=True, exist_ok=True)

    research = MultiTimeframePocConfig()
    execution = load_execution_costs(execution_file)
    strategy_base = NasdaqStrategyConfig(bar_minutes=1)
    bars, data_audit = load_nasdaq_bars(data_file, 1)
    indicated = add_indicators(bars, strategy_base)
    schedule = build_ny_schedule(bars.index.min(), bars.index.max())
    daily_context = build_composite_poc_context(indicated, schedule, research)
    blocks = build_fifteen_minute_blocks(indicated, schedule, research)
    raw_events, observations = build_poc_signal_observations(
        indicated,
        schedule,
        daily_context,
        blocks,
        research,
    )
    event_summary = summarize_signal_observations(observations)
    timing = timing_summary(observations)
    signal_sets = strategy_signal_sets(observations)

    variants = {
        "1m_cross_10m": ("one_minute_cross", 10),
        "1m_acceptance_10m": ("one_minute_acceptance", 10),
        "15m_acceptance_10m": ("fifteen_minute_acceptance", 10),
        "1m_focus_acceptance_10m": ("one_minute_focus_acceptance", 10),
        "1m_acceptance_3d_10m": ("one_minute_acceptance_3d", 10),
        "1m_acceptance_5d_10m": ("one_minute_acceptance_5d", 10),
        "1m_acceptance_3d_or_5d_10m": ("one_minute_acceptance_3d_or_5d", 10),
        "1m_acceptance_3d_or_5d_opening_10m": ("one_minute_acceptance_3d_or_5d_opening", 10),
        "opening_3d5d_stop_0.00x_10m": ("opening_3d5d_structural_stop_0.00", 10),
        "opening_3d5d_stop_0.25x_10m": ("opening_3d5d_structural_stop_0.25", 10),
        "opening_3d5d_stop_0.50x_10m": ("opening_3d5d_structural_stop_0.50", 10),
        "opening_3d5d_stop_0.75x_10m": ("opening_3d5d_structural_stop_0.75", 10),
        "opening_3d5d_stop_1.00x_10m": ("opening_3d5d_structural_stop_1.00", 10),
        "1m_focus_15m_context_10m": ("one_minute_focus_15m", 10),
        "1m_focus_15m_context_15m": ("one_minute_focus_15m", 15),
        "15m_focus_context_15m": ("fifteen_minute_focus_15m", 15),
    }
    trades_by_variant: dict[str, pd.DataFrame] = {}
    blocked: dict[str, dict[str, int]] = {}
    for variant, (signal_name, holding_minutes) in variants.items():
        strategy = NasdaqStrategyConfig(bar_minutes=1, max_holding_minutes=holding_minutes)
        trades, variant_blocked = run_backtest(
            signal_sets[signal_name],
            indicated,
            strategy,
            execution,
        )
        trades_by_variant[variant] = trades
        blocked[variant] = variant_blocked
        trades.to_csv(trade_output / f"{variant}.csv", index=False)
    summary = _variant_summary(trades_by_variant)
    equity = _equity_frame(trades_by_variant)

    bootstrap_frames: list[pd.DataFrame] = []
    cost_frames: list[pd.DataFrame] = []
    for variant, trades in trades_by_variant.items():
        boot = session_bootstrap(trades)
        boot.insert(0, "variant", variant)
        bootstrap_frames.append(boot.loc[boot["setup"].eq("all")])
        costs = cost_sensitivity(trades)
        costs.insert(0, "variant", variant)
        cost_frames.append(costs.loc[costs["scope"].eq("holdout_2025") & costs["setup"].eq("all")])
    bootstrap = pd.concat(bootstrap_frames, ignore_index=True)
    cost_audit = pd.concat(cost_frames, ignore_index=True)
    plot_paths = _plots(observations, event_summary, timing, equity, indicated, output)
    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "strategy": "one_minute_execution_fifteen_minute_composite_poc_context",
        "data_file": str(data_file),
        "data_quality": data_audit,
        "research_config": asdict(research),
        "execution": execution.to_dict(),
        "variants": variants,
        "blocked_signals": blocked,
        "plot_files": [path.name for path in plot_paths],
        "selection_warning": "All rules share the same 2024-2025 sample and are exploratory.",
    }
    daily_context.to_csv(output / "daily_composite_poc_context.csv", index=False)
    blocks.to_csv(output / "fifteen_minute_blocks.csv", index=False)
    raw_events.to_csv(output / "raw_poc_cross_events.csv", index=False)
    observations.to_csv(output / "signal_observations.csv", index=False)
    event_summary.to_csv(output / "event_summary.csv", index=False)
    timing.to_csv(output / "timing_summary.csv", index=False)
    summary.to_csv(output / "strategy_summary.csv", index=False)
    equity.to_csv(output / "equity_curves.csv", index=False)
    bootstrap.to_csv(output / "bootstrap.csv", index=False)
    cost_audit.to_csv(output / "holdout_cost_sensitivity.csv", index=False)
    (output / "governance.json").write_text(json.dumps(governance, indent=2), encoding="utf-8")
    report = _report(event_summary, timing, summary, bootstrap, cost_audit, governance)
    (output / "report.md").write_text(report, encoding="utf-8")
    return {
        "report_path": output / "report.md",
        "event_summary": event_summary,
        "timing_summary": timing,
        "strategy_summary": summary,
        "trades": trades_by_variant,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root")
    parser.add_argument("--data-path", default=str(DEFAULT_DATA))
    parser.add_argument("--execution-path", default=str(DEFAULT_EXECUTION))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    results = build_multitimeframe_poc_backtest(
        project_root=args.project_root,
        data_path=args.data_path,
        execution_path=args.execution_path,
        output_dir=args.output_dir,
    )
    print(f"Report: {results['report_path']}")
    print(results["strategy_summary"].loc[
        results["strategy_summary"]["scope"].isin(["all", "development_2024", "holdout_2025"])
    ].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
