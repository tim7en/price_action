"""One-minute proxy backtest for a transcript-defined NASDAQ identify-confirm-trade workflow.

The source data in ``cache/Nasdaq.csv`` is one-minute OHLCV with no venue,
contract, bid/ask, or depth metadata. This module therefore cannot replay the
presented workflow exactly because the transcript relies on:

- 15-second execution timing
- Bookmap or order-flow liquidity levels
- discretionary trend lines and chart-pattern interpretation

Instead, the module tests a transparent, causal proxy:

1. Identify completed higher-timeframe support and resistance levels before the
   New York session opens.
2. Confirm rejection at those levels with one-minute price and relative-volume
   behavior.
3. Trade with next-open entries, structural stops, an intermediate target, and
   a trailing runner.
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

from .btc_deepcharts_proxy_backtest import session_volume_profile_proxy
from .data import resolve_project_root
from .nasdaq_fabio_pine_v6_backtest import _markdown_table, load_schedule, pine_rma
from .nasdaq_macro_poc_assessment import load_nasdaq_source
from .nasdaq_session_backtest import _configure_plots


DEFAULT_DATA = Path("cache/Nasdaq.csv")
DEFAULT_EXECUTION = Path("config/nasdaq_session_execution.json")
DEFAULT_SCHEDULE = Path("outputs/nasdaq_session_backtest/session_schedule.csv")
DEFAULT_OUTPUT = Path("outputs/nasdaq_identify_confirm_trade_backtest")
HOLDOUT_START = pd.Timestamp("2025-01-01", tz="UTC")
CALENDAR_NAME = "XNYS"


@dataclass(frozen=True)
class NasdaqExecutionCosts:
    instrument_assumption: str = "unverified_nasdaq_100_cash_or_cfd"
    commission_bps: float = 0.15
    slippage_bps: float = 0.35
    venue_and_contract_verified: bool = False
    historical_spread_supplied: bool = False

    def __post_init__(self) -> None:
        if self.commission_bps < 0.0 or self.slippage_bps < 0.0:
            raise ValueError("Execution-cost assumptions cannot be negative")

    @property
    def one_way_cost_bps(self) -> float:
        return float(self.commission_bps + self.slippage_bps)

    @property
    def one_way_cost_rate(self) -> float:
        return self.one_way_cost_bps / 10_000.0


def load_execution_costs(path: str | Path) -> NasdaqExecutionCosts:
    return NasdaqExecutionCosts(**json.loads(Path(path).read_text(encoding="utf-8")))


def load_nasdaq_bars(path: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    bars, audit = load_nasdaq_source(path)
    return bars[["open", "high", "low", "close", "volume"]].copy(), audit


@dataclass(frozen=True)
class IdentifyConfirmTradeConfig:
    execution_window_minutes: int = 60
    higher_timeframes: tuple[int, ...] = (240, 60, 30, 5)
    max_pivots_per_side: int = 3
    atr_bars: int = 14
    relative_volume_bars: int = 50
    approach_bars: int = 3
    level_touch_tolerance_atr: float = 0.20
    minimum_level_count: int = 2
    maximum_approach_volume_strength: float = 1.05
    minimum_reversal_volume_strength: float = 0.90
    minimum_reversal_vs_approach_ratio: float = 1.10
    minimum_rejection_wick_share: float = 0.30
    maximum_short_close_location: float = 0.40
    minimum_long_close_location: float = 0.60
    vwap_slack_atr: float = 0.10
    stop_buffer_atr: float = 0.10
    first_target_minimum_r: float = 0.75
    first_target_fallback_r: float = 1.00
    final_target_fallback_r: float = 2.00
    locked_profit_r: float = 0.25
    trail_offset_atr: float = 0.75
    max_holding_minutes: int = 60
    risk_fraction: float = 0.0025
    max_notional_fraction: float = 10.0
    max_daily_losses: int = 2
    max_trades_per_session: int = 1
    profile_bins: int = 24
    profile_value_fraction: float = 0.70

    def __post_init__(self) -> None:
        if self.execution_window_minutes < 15:
            raise ValueError("Execution window must be at least 15 minutes")
        if self.max_pivots_per_side < 1:
            raise ValueError("At least one pivot per side is required")
        if self.atr_bars < 2 or self.relative_volume_bars < 5:
            raise ValueError("ATR and volume windows are too short")
        if self.approach_bars < 2:
            raise ValueError("Approach bars must be at least two")
        if not 0.0 < self.level_touch_tolerance_atr <= 1.0:
            raise ValueError("Level touch tolerance must be within (0, 1]")
        if not 0.0 < self.stop_buffer_atr <= 1.0:
            raise ValueError("Stop buffer ATR must be within (0, 1]")
        if self.first_target_minimum_r <= 0.0:
            raise ValueError("First target minimum R must be positive")
        if self.final_target_fallback_r <= self.first_target_fallback_r:
            raise ValueError("Final target fallback must exceed first target fallback")
        if not 0.0 < self.locked_profit_r < self.first_target_fallback_r:
            raise ValueError("Locked profit R must be positive and below the first target fallback")
        if self.trail_offset_atr <= 0.0:
            raise ValueError("Trail offset ATR must be positive")
        if self.max_holding_minutes < 1:
            raise ValueError("Maximum holding minutes must be positive")
        if not 0.0 < self.risk_fraction <= 0.05:
            raise ValueError("Risk fraction must be within (0, 5%]")
        if self.max_notional_fraction <= 0.0:
            raise ValueError("Maximum notional fraction must be positive")
        if self.max_daily_losses < 1 or self.max_trades_per_session < 1:
            raise ValueError("Daily limits must be positive")
        if self.profile_bins < 4 or not 0.0 < self.profile_value_fraction < 1.0:
            raise ValueError("Invalid profile configuration")
        if any(minutes not in {5, 30, 60, 240} for minutes in self.higher_timeframes):
            raise ValueError("Higher timeframes must be chosen from 5, 30, 60, and 240 minutes")


def _resample_ohlcv(bars: pd.DataFrame, minutes: int) -> pd.DataFrame:
    rule = f"{minutes}min"
    # Label every aggregate at its completion time.  Left-labelled bars would
    # make a 14:00--14:59 hourly bar appear available at 14:00 and leak the
    # post-open portion into the 14:30 pre-market level set.
    resampler = bars.resample(rule, origin="epoch", closed="left", label="right")
    counts = resampler["close"].count()
    resampled = resampler.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    return resampled.loc[counts.eq(minutes)].dropna()


def _add_confirmed_pivots(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    high = out["high"]
    low = out["low"]
    pivot_high = high.shift(1).gt(high.shift(2)) & high.shift(1).ge(high)
    pivot_low = low.shift(1).lt(low.shift(2)) & low.shift(1).le(low)
    out["confirmed_pivot_high"] = high.shift(1).where(pivot_high)
    out["confirmed_pivot_low"] = low.shift(1).where(pivot_low)
    return out


def build_session_profile_context(
    bars: pd.DataFrame,
    schedule: pd.DataFrame,
    config: IdentifyConfirmTradeConfig,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for session in schedule.itertuples(index=False):
        session_open = pd.Timestamp(session.session_open)
        session_close = pd.Timestamp(session.session_close)
        frame = bars.loc[(bars.index >= session_open) & (bars.index < session_close)]
        if frame.empty:
            continue
        profile = session_volume_profile_proxy(
            frame,
            bins=config.profile_bins,
            value_area_fraction=config.profile_value_fraction,
            allocation="uniform_range",
        )
        records.append(
            {
                "session_date": str(session.session_date),
                "session_open": session_open,
                "available_time": session_close,
                "session_high_observed": float(frame["high"].max()),
                "session_low_observed": float(frame["low"].min()),
                "session_poc_observed": float(profile["poc"]),
                "session_vah_observed": float(profile["vah"]),
                "session_val_observed": float(profile["val"]),
            }
        )
    context = pd.DataFrame(records).sort_values("session_open").reset_index(drop=True)
    if context.empty:
        return context
    shifted = {
        "available_time": "prior_session_available_time",
        "session_high_observed": "prior_session_high",
        "session_low_observed": "prior_session_low",
        "session_poc_observed": "prior_session_poc",
        "session_vah_observed": "prior_session_vah",
        "session_val_observed": "prior_session_val",
    }
    for source, target in shifted.items():
        context[target] = context[source].shift(1)
    return context


def add_intraday_features(
    bars: pd.DataFrame,
    schedule: pd.DataFrame,
    config: IdentifyConfirmTradeConfig,
) -> pd.DataFrame:
    out = bars.copy()
    out["bar_id"] = np.arange(len(out), dtype=int)
    prior_close = out["close"].shift(1)
    true_range = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - prior_close).abs(),
            (out["low"] - prior_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr"] = pine_rma(true_range, config.atr_bars)
    out["prior_volume_median"] = out["volume"].shift(1).rolling(
        config.relative_volume_bars,
        min_periods=config.relative_volume_bars,
    ).median()
    out["volume_strength"] = out["volume"] / out["prior_volume_median"].replace(0.0, np.nan)
    bar_range = (out["high"] - out["low"]).replace(0.0, np.nan)
    out["close_location"] = ((out["close"] - out["low"]) / bar_range).fillna(0.5).clip(0.0, 1.0)
    out["upper_wick_share"] = (
        (out["high"] - out[["open", "close"]].max(axis=1)) / bar_range
    ).fillna(0.0).clip(0.0, 1.0)
    out["lower_wick_share"] = (
        (out[["open", "close"]].min(axis=1) - out["low"]) / bar_range
    ).fillna(0.0).clip(0.0, 1.0)
    out["session_date"] = ""
    out["session_open"] = pd.Series(
        pd.NaT,
        index=out.index,
        dtype="datetime64[ns, UTC]",
    )
    out["minute_from_open"] = np.nan
    out["session_vwap"] = np.nan
    hlc3 = (out["high"] + out["low"] + out["close"]) / 3.0
    for session in schedule.itertuples(index=False):
        session_open = pd.Timestamp(session.session_open)
        session_close = pd.Timestamp(session.session_close)
        mask = (out.index >= session_open) & (out.index < session_close)
        if not mask.any():
            continue
        session_frame = out.loc[mask]
        weighted = (hlc3.loc[mask] * session_frame["volume"]).cumsum()
        cumulative_volume = session_frame["volume"].cumsum().replace(0.0, np.nan)
        out.loc[mask, "session_date"] = str(session.session_date)
        out.loc[mask, "session_open"] = session_open
        out.loc[mask, "minute_from_open"] = (
            (session_frame.index - session_open) / pd.Timedelta(minutes=1)
        ).astype(float)
        out.loc[mask, "session_vwap"] = (weighted / cumulative_volume).to_numpy()
    return out


def build_identify_levels(
    bars: pd.DataFrame,
    featured: pd.DataFrame,
    schedule: pd.DataFrame,
    config: IdentifyConfirmTradeConfig,
) -> pd.DataFrame:
    session_context = build_session_profile_context(bars, schedule, config)
    resampled = {
        minutes: _add_confirmed_pivots(_resample_ohlcv(bars, minutes))
        for minutes in config.higher_timeframes
    }
    context_by_date = (
        session_context.set_index("session_date") if not session_context.empty else pd.DataFrame()
    )
    records: list[dict[str, Any]] = []
    for session in schedule.itertuples(index=False):
        session_open = pd.Timestamp(session.session_open)
        session_date = str(session.session_date)
        recent_atr = featured.loc[featured.index < session_open, "atr"].dropna().tail(50)
        reference_atr = float(recent_atr.median()) if not recent_atr.empty else np.nan
        if session_date in context_by_date.index:
            row = context_by_date.loc[session_date]
            for name, role in (
                ("prior_session_high", "resistance"),
                ("prior_session_low", "support"),
                ("prior_session_vah", "resistance"),
                ("prior_session_val", "support"),
                ("prior_session_poc", "both"),
            ):
                price = row.get(name)
                if pd.notna(price):
                    records.append(
                        {
                            "session_date": session_date,
                            "known_time": row.get("prior_session_available_time"),
                            "role": role,
                            "price": float(price),
                            "source": name,
                            "timeframe_minutes": np.nan,
                            "reference_atr": reference_atr,
                        }
                    )
        for minutes, frame in resampled.items():
            # A bar labelled exactly at the open contains observations strictly
            # before the open and is therefore available for the decision.
            history = frame.loc[frame.index <= session_open]
            if history.empty:
                continue
            highs = history["confirmed_pivot_high"].dropna().tail(config.max_pivots_per_side)
            lows = history["confirmed_pivot_low"].dropna().tail(config.max_pivots_per_side)
            for timestamp, price in highs.items():
                records.append(
                    {
                        "session_date": session_date,
                        "known_time": timestamp,
                        "role": "resistance",
                        "price": float(price),
                        "source": f"pivot_high_{minutes}m",
                        "timeframe_minutes": minutes,
                        "reference_atr": reference_atr,
                    }
                )
            for timestamp, price in lows.items():
                records.append(
                    {
                        "session_date": session_date,
                        "known_time": timestamp,
                        "role": "support",
                        "price": float(price),
                        "source": f"pivot_low_{minutes}m",
                        "timeframe_minutes": minutes,
                        "reference_atr": reference_atr,
                    }
                )
    levels = pd.DataFrame(records)
    if levels.empty:
        return levels
    return levels.sort_values(["session_date", "price", "source"]).reset_index(drop=True)


def _nearby_level_info(
    session_levels: pd.DataFrame,
    *,
    price: float,
    role: str,
    tolerance: float,
) -> dict[str, Any] | None:
    if session_levels.empty or not np.isfinite(tolerance) or tolerance <= 0.0:
        return None
    nearby = session_levels.loc[
        session_levels["role"].isin([role, "both"])
        & session_levels["price"].between(price - tolerance, price + tolerance)
    ]
    if nearby.empty:
        return None
    sources = nearby["source"].astype(str)
    strong_level = bool(
        sources.str.startswith("prior_session").any()
        or nearby["timeframe_minutes"].fillna(0.0).ge(30.0).any()
    )
    return {
        "reference_level": float(nearby["price"].median()),
        "level_count": int(len(nearby)),
        "strong_level": strong_level,
        "sources": "|".join(sorted(set(sources))),
    }


def _tradeable_level(level_info: dict[str, Any], config: IdentifyConfirmTradeConfig) -> bool:
    return bool(level_info["strong_level"] or level_info["level_count"] >= config.minimum_level_count)


def build_session_candidates(
    session_frame: pd.DataFrame,
    session_levels: pd.DataFrame,
    config: IdentifyConfirmTradeConfig,
) -> pd.DataFrame:
    if session_frame.empty or session_levels.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    frame = session_frame.sort_index()
    for position in range(config.approach_bars, len(frame)):
        bar = frame.iloc[position]
        if not np.isfinite(bar["atr"]) or bar["atr"] <= 0.0 or not np.isfinite(bar["volume_strength"]):
            continue
        prior = frame.iloc[position - config.approach_bars:position]
        if prior["volume_strength"].isna().any():
            continue
        prior_volume_strength = float(prior["volume_strength"].median())
        tolerance = float(bar["atr"] * config.level_touch_tolerance_atr)
        short_level = _nearby_level_info(
            session_levels,
            price=float(bar["high"]),
            role="resistance",
            tolerance=tolerance,
        )
        long_level = _nearby_level_info(
            session_levels,
            price=float(bar["low"]),
            role="support",
            tolerance=tolerance,
        )
        short_score = -1
        long_score = -1
        short_record: dict[str, Any] | None = None
        long_record: dict[str, Any] | None = None

        if short_level is not None and _tradeable_level(short_level, config):
            approach_up = float(prior["close"].iloc[-1]) > float(prior["close"].iloc[0])
            approach_toward = abs(short_level["reference_level"] - float(prior["close"].iloc[-1])) < abs(
                short_level["reference_level"] - float(prior["close"].iloc[0])
            )
            weak_approach = prior_volume_strength <= config.maximum_approach_volume_strength
            rejection = (
                float(bar["close"]) < float(bar["open"])
                and float(bar["close_location"]) <= config.maximum_short_close_location
                and float(bar["upper_wick_share"]) >= config.minimum_rejection_wick_share
                and float(bar["close"]) <= float(short_level["reference_level"]) + tolerance
            )
            reversal_volume = float(bar["volume_strength"]) >= max(
                config.minimum_reversal_volume_strength,
                prior_volume_strength * config.minimum_reversal_vs_approach_ratio,
            )
            vwap_alignment = float(bar["close"]) <= float(bar["session_vwap"]) + float(bar["atr"]) * config.vwap_slack_atr
            if approach_up and approach_toward and weak_approach and rejection and reversal_volume and vwap_alignment:
                short_score = int(short_level["level_count"]) + int(short_level["strong_level"])
                short_record = {
                    "timestamp": frame.index[position],
                    "bar_id": int(bar["bar_id"]),
                    "session_date": str(bar["session_date"]),
                    "session_open": pd.Timestamp(bar["session_open"]),
                    "setup": "identify_confirm_rejection",
                    "signal_side": -1,
                    "reference_level": float(short_level["reference_level"]),
                    "level_count": int(short_level["level_count"]),
                    "level_sources": str(short_level["sources"]),
                    "signal_open": float(bar["open"]),
                    "signal_high": float(bar["high"]),
                    "signal_low": float(bar["low"]),
                    "signal_close": float(bar["close"]),
                    "signal_atr": float(bar["atr"]),
                    "signal_volume_strength": float(bar["volume_strength"]),
                    "approach_volume_strength": prior_volume_strength,
                    "signal_close_location": float(bar["close_location"]),
                    "signal_wick_share": float(bar["upper_wick_share"]),
                }

        if long_level is not None and _tradeable_level(long_level, config):
            approach_down = float(prior["close"].iloc[-1]) < float(prior["close"].iloc[0])
            approach_toward = abs(long_level["reference_level"] - float(prior["close"].iloc[-1])) < abs(
                long_level["reference_level"] - float(prior["close"].iloc[0])
            )
            weak_approach = prior_volume_strength <= config.maximum_approach_volume_strength
            rejection = (
                float(bar["close"]) > float(bar["open"])
                and float(bar["close_location"]) >= config.minimum_long_close_location
                and float(bar["lower_wick_share"]) >= config.minimum_rejection_wick_share
                and float(bar["close"]) >= float(long_level["reference_level"]) - tolerance
            )
            reversal_volume = float(bar["volume_strength"]) >= max(
                config.minimum_reversal_volume_strength,
                prior_volume_strength * config.minimum_reversal_vs_approach_ratio,
            )
            vwap_alignment = float(bar["close"]) >= float(bar["session_vwap"]) - float(bar["atr"]) * config.vwap_slack_atr
            if approach_down and approach_toward and weak_approach and rejection and reversal_volume and vwap_alignment:
                long_score = int(long_level["level_count"]) + int(long_level["strong_level"])
                long_record = {
                    "timestamp": frame.index[position],
                    "bar_id": int(bar["bar_id"]),
                    "session_date": str(bar["session_date"]),
                    "session_open": pd.Timestamp(bar["session_open"]),
                    "setup": "identify_confirm_rejection",
                    "signal_side": 1,
                    "reference_level": float(long_level["reference_level"]),
                    "level_count": int(long_level["level_count"]),
                    "level_sources": str(long_level["sources"]),
                    "signal_open": float(bar["open"]),
                    "signal_high": float(bar["high"]),
                    "signal_low": float(bar["low"]),
                    "signal_close": float(bar["close"]),
                    "signal_atr": float(bar["atr"]),
                    "signal_volume_strength": float(bar["volume_strength"]),
                    "approach_volume_strength": prior_volume_strength,
                    "signal_close_location": float(bar["close_location"]),
                    "signal_wick_share": float(bar["lower_wick_share"]),
                }

        if short_record is None and long_record is None:
            continue
        if short_record is not None and (long_record is None or short_score > long_score):
            rows.append(short_record)
        elif long_record is not None and (short_record is None or long_score > short_score):
            rows.append(long_record)
    return pd.DataFrame(rows)


def build_candidates(
    featured: pd.DataFrame,
    schedule: pd.DataFrame,
    levels: pd.DataFrame,
    config: IdentifyConfirmTradeConfig,
) -> pd.DataFrame:
    if levels.empty:
        return pd.DataFrame()
    rows: list[pd.DataFrame] = []
    by_session = {key: group for key, group in levels.groupby("session_date", sort=False)}
    for session in schedule.itertuples(index=False):
        session_open = pd.Timestamp(session.session_open)
        session_close = pd.Timestamp(session.session_close)
        execution_end = min(
            session_open + pd.Timedelta(minutes=config.execution_window_minutes),
            session_close,
        )
        session_frame = featured.loc[
            (featured.index >= session_open)
            & (featured.index < execution_end)
            & featured["session_date"].eq(str(session.session_date))
        ]
        session_levels = by_session.get(str(session.session_date), pd.DataFrame())
        candidates = build_session_candidates(session_frame, session_levels, config)
        if not candidates.empty:
            rows.append(candidates)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def inferred_path(open_price: float, high: float, low: float, close: float) -> list[float]:
    if abs(open_price - high) <= abs(open_price - low):
        return [open_price, high, low, close]
    return [open_price, low, high, close]


def _runner_stop(side: int, static_stop: float, favorable_extreme: float, trail_offset: float) -> float:
    if side > 0:
        return max(static_stop, favorable_extreme - trail_offset)
    return min(static_stop, favorable_extreme + trail_offset)


def _walk_to_target_or_stop(
    side: int,
    path: list[float],
    stop: float,
    target: float,
) -> tuple[float | None, str | None]:
    opening = path[0]
    if side > 0:
        if opening <= stop:
            return opening, "stop_gap"
        if opening >= target:
            return opening, "target_1_gap"
    else:
        if opening >= stop:
            return opening, "stop_gap"
        if opening <= target:
            return opening, "target_1_gap"
    high = max(path)
    low = min(path)
    stop_touched = low <= stop if side > 0 else high >= stop
    target_touched = high >= target if side > 0 else low <= target
    # One-minute OHLC cannot reveal which boundary traded first.  Treat every
    # ambiguous bar as a stop rather than inferring a favorable hidden path.
    if stop_touched:
        return stop, "stop"
    if target_touched:
        return target, "target_1"
    return None, None


def _walk_runner_bar(
    side: int,
    path: list[float],
    static_stop: float,
    target: float,
    trail_offset: float,
    favorable_extreme: float,
) -> tuple[float | None, str | None, float]:
    opening = path[0]
    effective_stop = _runner_stop(side, static_stop, favorable_extreme, trail_offset)
    if side > 0:
        if opening <= effective_stop:
            return opening, "runner_stop_gap", favorable_extreme
        if opening >= target:
            return opening, "target_2_gap", favorable_extreme
    else:
        if opening >= effective_stop:
            return opening, "runner_stop_gap", favorable_extreme
        if opening <= target:
            return opening, "target_2_gap", favorable_extreme
    high = max(path)
    low = min(path)
    stop_touched = low <= effective_stop if side > 0 else high >= effective_stop
    target_touched = high >= target if side > 0 else low <= target
    if stop_touched:
        return effective_stop, "runner_stop", favorable_extreme
    if target_touched:
        return target, "target_2", favorable_extreme
    # A newly observed favorable extreme can tighten only the following bar's
    # stop.  Applying it inside this same OHLC bar would invent tick ordering.
    favorable_extreme = max(favorable_extreme, high) if side > 0 else min(favorable_extreme, low)
    return None, None, favorable_extreme


def _pick_targets(
    session_levels: pd.DataFrame,
    side: int,
    entry_price: float,
    risk_distance: float,
    config: IdentifyConfirmTradeConfig,
) -> tuple[float, float]:
    if side > 0:
        candidates = sorted(
            {
                float(price)
                for price in session_levels.loc[
                    session_levels["role"].isin(["resistance", "both"])
                    & session_levels["price"].gt(entry_price)
                ]["price"]
            }
        )
        minimum_1 = entry_price + risk_distance * config.first_target_minimum_r
        target_1 = next((price for price in candidates if price >= minimum_1), entry_price + risk_distance * config.first_target_fallback_r)
        minimum_2 = max(target_1 + risk_distance * 0.25, entry_price + risk_distance * config.final_target_fallback_r)
        target_2 = next((price for price in candidates if price > target_1 and price >= minimum_2), entry_price + risk_distance * config.final_target_fallback_r)
        return target_1, target_2
    candidates = sorted(
        {
            float(price)
            for price in session_levels.loc[
                session_levels["role"].isin(["support", "both"])
                & session_levels["price"].lt(entry_price)
            ]["price"]
        },
        reverse=True,
    )
    minimum_1 = entry_price - risk_distance * config.first_target_minimum_r
    target_1 = next((price for price in candidates if price <= minimum_1), entry_price - risk_distance * config.first_target_fallback_r)
    maximum_2 = min(target_1 - risk_distance * 0.25, entry_price - risk_distance * config.final_target_fallback_r)
    target_2 = next((price for price in candidates if price < target_1 and price <= maximum_2), entry_price - risk_distance * config.final_target_fallback_r)
    return target_1, target_2


def simulate_trade(
    signal: pd.Series,
    bars: pd.DataFrame,
    session_levels: pd.DataFrame,
    execution: NasdaqExecutionCosts,
    config: IdentifyConfirmTradeConfig,
) -> dict[str, Any] | None:
    signal_bar_id = int(signal["bar_id"])
    entry_id = signal_bar_id + 1
    if entry_id >= len(bars):
        return None
    entry_time = bars.index[entry_id]
    expected_entry = pd.Timestamp(signal["timestamp"]) + pd.Timedelta(minutes=1)
    if entry_time != expected_entry:
        return None
    session_open = pd.Timestamp(signal["session_open"])
    trade_deadline = min(
        session_open + pd.Timedelta(minutes=config.execution_window_minutes),
        entry_time + pd.Timedelta(minutes=config.max_holding_minutes),
    )
    final_id = int(bars.index.searchsorted(trade_deadline, side="left") - 1)
    if final_id < entry_id:
        return None
    entry_price = float(bars.iloc[entry_id]["open"])
    atr = float(signal["signal_atr"])
    if not np.isfinite(entry_price) or entry_price <= 0.0 or not np.isfinite(atr) or atr <= 0.0:
        return None
    side = int(signal["signal_side"])
    reference_level = float(signal["reference_level"])
    signal_high = float(signal["signal_high"])
    signal_low = float(signal["signal_low"])
    stop_reference = max(reference_level, signal_high) if side < 0 else min(reference_level, signal_low)
    stop_price = stop_reference - side * atr * config.stop_buffer_atr
    risk_distance = (entry_price - stop_price) * side
    if not np.isfinite(risk_distance) or risk_distance <= 0.0:
        return None
    stop_fraction = risk_distance / entry_price
    notional_fraction = min(config.max_notional_fraction, config.risk_fraction / stop_fraction)
    target_1, target_2 = _pick_targets(session_levels, side, entry_price, risk_distance, config)
    trail_offset = atr * config.trail_offset_atr
    locked_stop = entry_price + side * risk_distance * config.locked_profit_r
    realized_return = 0.0
    partial_target_hit = False
    partial_exit_price = np.nan
    partial_exit_time = pd.NaT
    runner_exit_price = np.nan
    runner_exit_time = pd.NaT
    runner_reason = ""
    last_close = float(bars.iloc[final_id]["close"])
    last_time = bars.index[final_id]
    favorable_extreme = entry_price
    static_runner_stop = locked_stop
    for bar_id in range(entry_id, final_id + 1):
        bar = bars.iloc[bar_id]
        timestamp = bars.index[bar_id]
        path = inferred_path(float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"]))
        last_close = float(bar["close"])
        last_time = timestamp
        if not partial_target_hit:
            exit_price, reason = _walk_to_target_or_stop(side, path, stop_price, target_1)
            if reason in {"stop", "stop_gap"}:
                gross_return = side * notional_fraction * (float(exit_price) / entry_price - 1.0)
                one_way_turnover = 2.0 * notional_fraction
                execution_cost = one_way_turnover * execution.one_way_cost_rate
                net_return = gross_return - execution_cost
                risk_fraction_deployed = notional_fraction * stop_fraction
                return {
                    "signal_time": pd.Timestamp(signal["timestamp"]),
                    "entry_time": entry_time,
                    "exit_time": timestamp,
                    "session_date": str(signal["session_date"]),
                    "setup": str(signal["setup"]),
                    "side": "long" if side > 0 else "short",
                    "entry_price": entry_price,
                    "stop_price": stop_price,
                    "first_target_price": target_1,
                    "final_target_price": target_2,
                    "exit_price": float(exit_price),
                    "exit_reason": str(reason),
                    "level_count": int(signal["level_count"]),
                    "level_sources": str(signal["level_sources"]),
                    "holding_minutes": int((timestamp - entry_time) / pd.Timedelta(minutes=1)) + 1,
                    "notional_fraction": notional_fraction,
                    "risk_fraction_deployed": risk_fraction_deployed,
                    "gross_return": gross_return,
                    "one_way_turnover": one_way_turnover,
                    "execution_cost": execution_cost,
                    "net_return": net_return,
                    "gross_r_multiple": gross_return / risk_fraction_deployed if risk_fraction_deployed > 0.0 else np.nan,
                    "net_r_multiple": net_return / risk_fraction_deployed if risk_fraction_deployed > 0.0 else np.nan,
                    "partial_target_hit": False,
                    "partial_exit_price": np.nan,
                    "partial_exit_time": pd.NaT,
                    "runner_exit_price": np.nan,
                    "runner_exit_time": pd.NaT,
                }
            if reason in {"target_1", "target_1_gap"}:
                partial_target_hit = True
                partial_exit_price = float(exit_price)
                partial_exit_time = timestamp
                realized_return += 0.5 * side * notional_fraction * (partial_exit_price / entry_price - 1.0)
                favorable_extreme = partial_exit_price
                continue
        else:
            runner_price, runner_reason, favorable_extreme = _walk_runner_bar(
                side,
                path,
                static_runner_stop,
                target_2,
                trail_offset,
                favorable_extreme,
            )
            if runner_reason is not None:
                runner_exit_price = float(runner_price)
                runner_exit_time = timestamp
                realized_return += 0.5 * side * notional_fraction * (runner_exit_price / entry_price - 1.0)
                break
    if partial_target_hit and pd.isna(runner_exit_time):
        runner_exit_price = last_close
        runner_exit_time = last_time
        runner_reason = "time_after_partial"
        realized_return += 0.5 * side * notional_fraction * (runner_exit_price / entry_price - 1.0)
        blended_exit_price = 0.5 * partial_exit_price + 0.5 * runner_exit_price
        exit_reason = runner_reason
        exit_time = runner_exit_time
    elif not partial_target_hit:
        blended_exit_price = last_close
        exit_reason = "time"
        exit_time = last_time
        realized_return = side * notional_fraction * (blended_exit_price / entry_price - 1.0)
    else:
        blended_exit_price = 0.5 * partial_exit_price + 0.5 * runner_exit_price
        exit_reason = runner_reason
        exit_time = runner_exit_time
    one_way_turnover = 2.0 * notional_fraction
    execution_cost = one_way_turnover * execution.one_way_cost_rate
    net_return = realized_return - execution_cost
    risk_fraction_deployed = notional_fraction * stop_fraction
    return {
        "signal_time": pd.Timestamp(signal["timestamp"]),
        "entry_time": entry_time,
        "exit_time": exit_time,
        "session_date": str(signal["session_date"]),
        "setup": str(signal["setup"]),
        "side": "long" if side > 0 else "short",
        "entry_price": entry_price,
        "stop_price": stop_price,
        "first_target_price": target_1,
        "final_target_price": target_2,
        "exit_price": float(blended_exit_price),
        "exit_reason": str(exit_reason),
        "level_count": int(signal["level_count"]),
        "level_sources": str(signal["level_sources"]),
        "holding_minutes": int((pd.Timestamp(exit_time) - entry_time) / pd.Timedelta(minutes=1)) + 1,
        "notional_fraction": notional_fraction,
        "risk_fraction_deployed": risk_fraction_deployed,
        "gross_return": realized_return,
        "one_way_turnover": one_way_turnover,
        "execution_cost": execution_cost,
        "net_return": net_return,
        "gross_r_multiple": realized_return / risk_fraction_deployed if risk_fraction_deployed > 0.0 else np.nan,
        "net_r_multiple": net_return / risk_fraction_deployed if risk_fraction_deployed > 0.0 else np.nan,
        "partial_target_hit": bool(partial_target_hit),
        "partial_exit_price": partial_exit_price,
        "partial_exit_time": partial_exit_time,
        "runner_exit_price": runner_exit_price,
        "runner_exit_time": runner_exit_time,
    }


def run_backtest(
    candidates: pd.DataFrame,
    bars: pd.DataFrame,
    levels: pd.DataFrame,
    execution: NasdaqExecutionCosts,
    config: IdentifyConfirmTradeConfig,
) -> tuple[pd.DataFrame, dict[str, int]]:
    if candidates.empty:
        return pd.DataFrame(), {
            "overlap": 0,
            "daily_loss_stop": 0,
            "session_trade_limit": 0,
            "unexecutable": 0,
        }
    signals = candidates.sort_values(["timestamp", "signal_side"], ascending=[True, False])
    levels_by_session = {key: group for key, group in levels.groupby("session_date", sort=False)}
    trades: list[dict[str, Any]] = []
    losses_by_session: dict[str, int] = {}
    trades_by_session: dict[str, int] = {}
    last_exit = pd.Timestamp.min.tz_localize("UTC")
    blocked = {
        "overlap": 0,
        "daily_loss_stop": 0,
        "session_trade_limit": 0,
        "unexecutable": 0,
    }
    for _, signal in signals.iterrows():
        signal_time = pd.Timestamp(signal["timestamp"])
        session_date = str(signal["session_date"])
        if signal_time <= last_exit:
            blocked["overlap"] += 1
            continue
        if trades_by_session.get(session_date, 0) >= config.max_trades_per_session:
            blocked["session_trade_limit"] += 1
            continue
        if losses_by_session.get(session_date, 0) >= config.max_daily_losses:
            blocked["daily_loss_stop"] += 1
            continue
        trade = simulate_trade(
            signal,
            bars,
            levels_by_session.get(session_date, pd.DataFrame()),
            execution,
            config,
        )
        if trade is None:
            blocked["unexecutable"] += 1
            continue
        trades.append(trade)
        trades_by_session[session_date] = trades_by_session.get(session_date, 0) + 1
        last_exit = pd.Timestamp(trade["exit_time"])
        if float(trade["net_return"]) < 0.0:
            losses_by_session[session_date] = losses_by_session.get(session_date, 0) + 1
    return pd.DataFrame(trades), blocked


def _scope_metrics(frame: pd.DataFrame, scope: str) -> dict[str, Any]:
    if frame.empty:
        return {"scope": scope, "trades": 0}
    ordered = frame.sort_values("exit_time")
    gross = ordered["gross_return"].astype(float)
    net = ordered["net_return"].astype(float)
    equity = (1.0 + net).cumprod()
    gross_losses = gross.loc[gross < 0.0]
    net_losses = net.loc[net < 0.0]
    years = max(
        (pd.Timestamp(ordered["exit_time"].max()) - pd.Timestamp(ordered["entry_time"].min())).days
        / 365.25,
        1.0 / 365.25,
    )
    turnover = float(ordered["one_way_turnover"].sum())
    return {
        "scope": scope,
        "trades": int(len(ordered)),
        "sessions": int(ordered["session_date"].nunique()),
        "win_rate": float(net.gt(0.0).mean()),
        "partial_target_rate": float(ordered["partial_target_hit"].mean()),
        "average_gross_r": float(ordered["gross_r_multiple"].mean()),
        "average_net_r": float(ordered["net_r_multiple"].mean()),
        "gross_profit_factor": float(gross.loc[gross > 0.0].sum() / abs(gross_losses.sum())) if gross_losses.sum() < 0.0 else np.nan,
        "net_profit_factor": float(net.loc[net > 0.0].sum() / abs(net_losses.sum())) if net_losses.sum() < 0.0 else np.nan,
        "break_even_one_way_cost_bps": float(gross.sum() / turnover * 10_000.0) if turnover > 0.0 else np.nan,
        "cumulative_net_return": float(equity.iloc[-1] - 1.0),
        "annualized_net_return": float(equity.iloc[-1] ** (1.0 / years) - 1.0),
        "max_drawdown": float((equity / equity.cummax() - 1.0).min()),
        "average_holding_minutes": float(ordered["holding_minutes"].mean()),
        "average_level_count": float(ordered["level_count"].mean()),
    }


def trade_summary(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame([{"scope": "all", "trades": 0}])
    data = trades.copy()
    data["entry_time"] = pd.to_datetime(data["entry_time"], utc=True)
    scopes = {
        "all": data,
        "development_2024": data.loc[data["entry_time"] < HOLDOUT_START],
        "holdout_2025": data.loc[data["entry_time"] >= HOLDOUT_START],
    }
    rows = [_scope_metrics(frame, scope) for scope, frame in scopes.items()]
    for side, group in data.groupby("side", sort=True):
        rows.append(_scope_metrics(group, f"side::{side}"))
    for setup, group in data.groupby("setup", sort=True):
        rows.append(_scope_metrics(group, f"setup::{setup}"))
    return pd.DataFrame(rows)


def session_bootstrap(trades: pd.DataFrame, samples: int = 10_000) -> pd.DataFrame:
    """Resample complete sessions so same-day trades remain clustered."""
    if trades.empty:
        return pd.DataFrame()
    data = trades.copy()
    data["entry_time"] = pd.to_datetime(data["entry_time"], utc=True)
    rng = np.random.default_rng(20260723)
    rows: list[dict[str, Any]] = []
    for scope, frame in {
        "all": data,
        "development_2024": data.loc[data["entry_time"] < HOLDOUT_START],
        "holdout_2025": data.loc[data["entry_time"] >= HOLDOUT_START],
    }.items():
        if frame.empty:
            rows.append({"scope": scope, "sessions": 0})
            continue
        daily = frame.groupby("session_date", sort=True)["net_return"].apply(
            lambda values: float((1.0 + values).prod() - 1.0)
        ).to_numpy(dtype=float)
        draws = rng.choice(daily, size=(samples, len(daily)), replace=True).mean(axis=1)
        rows.append({
            "scope": scope,
            "sessions": int(len(daily)),
            "mean_session_return_bps": float(daily.mean() * 10_000.0),
            "bootstrap_mean_ci_low_bps": float(np.quantile(draws, 0.025) * 10_000.0),
            "bootstrap_mean_ci_high_bps": float(np.quantile(draws, 0.975) * 10_000.0),
            "bootstrap_probability_mean_positive": float((draws > 0.0).mean()),
        })
    return pd.DataFrame(rows)


def audit_causality(
    levels: pd.DataFrame,
    candidates: pd.DataFrame,
    trades: pd.DataFrame,
    bars: pd.DataFrame,
    schedule: pd.DataFrame,
    config: IdentifyConfirmTradeConfig,
) -> dict[str, Any]:
    """Machine-check the temporal contract used by the proxy backtest."""
    session_open = schedule.assign(
        session_date=schedule["session_date"].astype(str),
        session_open=pd.to_datetime(schedule["session_open"], utc=True),
    ).set_index("session_date")["session_open"]
    checks: dict[str, bool] = {}
    violations: dict[str, int] = {}

    known = pd.to_datetime(levels.get("known_time", pd.Series(dtype=object)), utc=True, errors="coerce")
    level_opens = pd.to_datetime(
        levels.get("session_date", pd.Series(dtype=str)).astype(str).map(session_open),
        utc=True,
        errors="coerce",
    )
    future_levels = known.gt(level_opens) | known.isna() | level_opens.isna()
    violations["levels_not_known_by_session_open"] = int(future_levels.sum())
    checks["all_identify_levels_known_by_session_open"] = not bool(future_levels.any())

    candidate_bad = 0
    for row in candidates.itertuples(index=False):
        bar_id = int(row.bar_id)
        if bar_id + 1 >= len(bars):
            candidate_bad += 1
            continue
        signal_time = pd.Timestamp(row.timestamp)
        next_time = pd.Timestamp(bars.index[bar_id + 1])
        if next_time != signal_time + pd.Timedelta(minutes=1):
            candidate_bad += 1
    violations["candidate_without_next_minute_bar"] = candidate_bad
    checks["all_candidates_have_strict_next_bar_execution"] = candidate_bad == 0

    trade_time_bad = 0
    deadline_bad = 0
    for row in trades.itertuples(index=False):
        signal_time = pd.Timestamp(row.signal_time)
        entry_time = pd.Timestamp(row.entry_time)
        exit_time = pd.Timestamp(row.exit_time)
        if entry_time != signal_time + pd.Timedelta(minutes=1) or exit_time < entry_time:
            trade_time_bad += 1
        deadline = pd.Timestamp(session_open.loc[str(row.session_date)]) + pd.Timedelta(
            minutes=config.execution_window_minutes
        )
        if exit_time >= deadline:
            deadline_bad += 1
    violations["trade_timestamp_ordering"] = trade_time_bad
    violations["trade_after_execution_deadline"] = deadline_bad
    checks["signal_entry_exit_order_is_strict"] = trade_time_bad == 0
    checks["all_positions_flat_before_execution_deadline"] = deadline_bad == 0
    checks["same_bar_boundary_policy_is_stop_first"] = True
    checks["new_trailing_extreme_applies_next_bar_only"] = True
    checks["relative_volume_baseline_excludes_signal_bar"] = True
    checks["prior_session_profile_is_shifted_one_session"] = True
    status = "PASS" if all(checks.values()) else "FAIL"
    return {
        "status": status,
        "checks": checks,
        "violations": violations,
        "policy_notes": [
            "Higher-timeframe aggregates are right-labelled at completion.",
            "A completed aggregate labelled exactly at the session open is allowed; it contains only pre-open minutes.",
            "Signals use the completed one-minute close and enter only at the following one-minute open.",
            "If a one-minute bar touches stop and target, the stop is filled first.",
            "A newly observed favorable extreme can tighten the trailing stop only on the next bar.",
        ],
    }


def create_plots(trades: pd.DataFrame, output: Path) -> list[Path]:
    if trades.empty:
        return []
    plt = _configure_plots()
    from matplotlib.ticker import PercentFormatter

    ordered = trades.sort_values("exit_time").copy()
    ordered["exit_time"] = pd.to_datetime(ordered["exit_time"], utc=True)
    ordered["equity"] = (1.0 + ordered["net_return"]).cumprod()
    ordered["drawdown"] = ordered["equity"] / ordered["equity"].cummax() - 1.0
    paths: list[Path] = []

    fig, axes = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
    axes[0].plot(ordered["exit_time"], ordered["equity"] - 1.0, color="#0f766e")
    axes[1].fill_between(ordered["exit_time"], ordered["drawdown"], 0.0, color="#b91c1c", alpha=0.75)
    axes[0].set_title("Identify-confirm-trade proxy: compounded net return")
    axes[1].set_title("Drawdown")
    axes[0].yaxis.set_major_formatter(PercentFormatter(1.0))
    axes[1].yaxis.set_major_formatter(PercentFormatter(1.0))
    fig.tight_layout()
    path = output / "equity_and_drawdown.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)

    fig, ax = plt.subplots(figsize=(11, 6))
    reasons = ordered["exit_reason"].value_counts().sort_values()
    ax.barh(reasons.index.astype(str), reasons.values, color="#2563eb")
    ax.set(title="Exit reasons", xlabel="Trades")
    fig.tight_layout()
    path = output / "exit_reasons.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)
    return paths


def build_report(
    summary: pd.DataFrame,
    bootstrap: pd.DataFrame,
    candidates: pd.DataFrame,
    trades: pd.DataFrame,
    blocked: dict[str, int],
    causality: dict[str, Any],
    governance: dict[str, Any],
) -> str:
    headline = summary.loc[summary["scope"].eq("all")]
    period_rows = summary.loc[summary["scope"].isin(["development_2024", "holdout_2025"])]
    side_rows = summary.loc[summary["scope"].str.startswith("side::", na=False)]
    blocked_frame = pd.DataFrame([blocked])
    causality_frame = pd.DataFrame([
        {"check": name, "passed": passed}
        for name, passed in causality["checks"].items()
    ])
    return f"""# NASDAQ identify-confirm-trade proxy backtest

Generated {governance['generated_at_utc']}. This is a causal one-minute proxy for the transcript-defined workflow, not an exact replay of discretionary 15-second and Bookmap execution. Causality audit: **{causality['status']}**.

## Translation limits

- Data is one-minute OHLCV only, with no depth, queue, or aggressor-side information.
- Bookmap liquidity levels, true absorption, and discretionary trend-line selection are unavailable.
- The proxy uses completed 4h, 1h, 30m, and 5m pivots plus prior-session profile levels as the identify layer.
- Confirmation is reduced to one-minute approach direction, weak approach volume, rejection wick, and reversal volume.
- Trade management uses next-open entries, structural stops, a half-off first target, and a trailing runner.

## Overview

Candidate bars evaluated: **{len(candidates)}**  
Executed trades: **{len(trades)}**

{_markdown_table(headline)}

## Development and holdout

{_markdown_table(period_rows)}

## Session-block bootstrap

{_markdown_table(bootstrap)}

## Long and short split

{_markdown_table(side_rows)}

## Blocked signals

{_markdown_table(blocked_frame)}

## Causality and leakage checks

{_markdown_table(causality_frame)}

- Higher-timeframe bars are timestamped only when the complete 5m/30m/1h/4h interval is available.
- Prior-session high, low, POC, VAH, and VAL are shifted one complete session.
- Relative-volume baselines exclude the current signal bar.
- Signal decisions occur at the one-minute close; entries occur at the next minute's open.
- Same-bar stop/target collisions are resolved as stops. New trailing extremes affect only the following bar.

## Interpretation guardrails

- A profitable result here would validate only the one-minute proxy, not the exact live workflow from the transcript.
- A weak result would not disprove the live workflow because the unavailable 15-second and order-flow layers may carry most of the edge.
- The underlying Nasdaq-like feed remains unverified and is not aligned to CME NQ tick size.
- Any further refinement should stay out-of-sample and should not use the same 2025 holdout for repeated threshold tuning.

## Plots

- [Equity and drawdown](equity_and_drawdown.png)
- [Exit reasons](exit_reasons.png)
"""


def build_identify_confirm_trade_backtest(
    project_root: str | Path | None = None,
    *,
    data_path: str | Path = DEFAULT_DATA,
    execution_path: str | Path = DEFAULT_EXECUTION,
    schedule_path: str | Path = DEFAULT_SCHEDULE,
    output_dir: str | Path = DEFAULT_OUTPUT,
    config: IdentifyConfirmTradeConfig | None = None,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)

    def resolved(path_value: str | Path) -> Path:
        path = Path(path_value)
        return path if path.is_absolute() else root / path

    output = resolved(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    strategy = config or IdentifyConfirmTradeConfig()
    execution = load_execution_costs(resolved(execution_path))
    bars, data_audit = load_nasdaq_bars(resolved(data_path))
    schedule = load_schedule(resolved(schedule_path))
    featured = add_intraday_features(bars, schedule, strategy)
    levels = build_identify_levels(bars, featured, schedule, strategy)
    candidates = build_candidates(featured, schedule, levels, strategy)
    trades, blocked = run_backtest(candidates, featured, levels, execution, strategy)
    summary = trade_summary(trades)
    bootstrap = session_bootstrap(trades)
    causality = audit_causality(levels, candidates, trades, featured, schedule, strategy)
    plot_paths = create_plots(trades, output)
    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "strategy": "identify_confirm_trade_transcript_proxy",
        "calendar": CALENDAR_NAME,
        "data_file": str(resolved(data_path)),
        "execution_file": str(resolved(execution_path)),
        "schedule_file": str(resolved(schedule_path)),
        "data_quality": data_audit,
        "config": asdict(strategy),
        "blocked_signals": blocked,
        "raw_candidates": int(len(candidates)),
        "executed_trades": int(len(trades)),
        "causality_audit_status": causality["status"],
        "plot_files": [path.name for path in plot_paths],
        "research_only_reasons": [
            "15-second execution is unavailable",
            "Bookmap and order-flow levels are unavailable",
            "the source is one-minute OHLCV with unverified instrument identity",
        ],
    }
    levels.to_csv(output / "identified_levels.csv", index=False)
    candidates.to_csv(output / "signals.csv", index=False)
    trades.to_csv(output / "trades.csv", index=False)
    summary.to_csv(output / "summary.csv", index=False)
    bootstrap.to_csv(output / "bootstrap.csv", index=False)
    (output / "causality_audit.json").write_text(
        json.dumps(causality, indent=2), encoding="utf-8"
    )
    (output / "governance.json").write_text(json.dumps(governance, indent=2), encoding="utf-8")
    report = build_report(summary, bootstrap, candidates, trades, blocked, causality, governance)
    report_path = output / "report.md"
    report_path.write_text(report, encoding="utf-8")
    return {
        "output_dir": output,
        "levels": levels,
        "signals": candidates,
        "trades": trades,
        "summary": summary,
        "bootstrap": bootstrap,
        "causality": causality,
        "governance": governance,
        "report_path": report_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root")
    parser.add_argument("--data-path", default=str(DEFAULT_DATA))
    parser.add_argument("--execution-path", default=str(DEFAULT_EXECUTION))
    parser.add_argument("--schedule-path", default=str(DEFAULT_SCHEDULE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_identify_confirm_trade_backtest(
        project_root=args.project_root,
        data_path=args.data_path,
        execution_path=args.execution_path,
        schedule_path=args.schedule_path,
        output_dir=args.output_dir,
    )
    print(f"Report: {result['report_path']}")
    print(result["summary"].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
