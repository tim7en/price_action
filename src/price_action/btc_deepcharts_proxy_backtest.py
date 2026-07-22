"""Causal BTC five-minute proxies for a Fabio/DeepCharts-style workflow.

These features are deliberately named ``*_proxy``.  Five-minute OHLCV cannot
reconstruct footprints, aggressor-side delta, MBO queues, absorption, or any
proprietary DeepCharts/Fabervaale calculation.  The module tests only a
transparent price/volume approximation of the workflow.
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

from price_action.btc_fabio_donchian_backtest import (
    attach_donchian_state,
    build_donchian_context,
)
from price_action.btc_fabio_pine_v6_backtest import (
    BAR_MINUTES,
    DEFAULT_DATA,
    build_seven_day_schedule,
    load_binance_btc_5m,
)
from price_action.data import resolve_project_root
from price_action.nasdaq_fabio_pine_v6_backtest import (
    PineFabioConfig,
    _markdown_table,
    add_pine_indicators,
    run_broker_emulator,
    summarize_path,
)


DEFAULT_OUTPUT = Path("outputs/btc_deepcharts_proxy_backtest")
HOLDOUT_START = pd.Timestamp("2025-01-01", tz="UTC")
COSTS_BPS = (0.0, 1.0, 2.0, 3.0, 6.0, 15.0)
REFERENCE_ONE_WAY_COST_BPS = 6.0


@dataclass(frozen=True)
class DeepChartsProxyConfig:
    """Frozen, non-optimized proxy definitions."""

    orb_bars: int = 6
    profile_bins: int = 24
    value_area_fraction: float = 0.70
    ivb_lookback_sessions: int = 60
    ivb_minimum_sessions: int = 20
    effort_lookback_bars: int = 50
    effort_quantile: float = 0.75
    vtracker_range_lookback_bars: int = 20
    delta_lookback_bars: int = 5
    donchian_timeframe_minutes: int = 240
    donchian_length: int = 20
    reward_to_risk: float = 2.0
    trail_activation_atr: float = 1.50
    trail_offset_atr: float = 0.50
    risk_target_fraction: float = 0.0025
    risk_maximum_leverage: float = 3.0
    risk_maximum_daily_losses: int = 2
    risk_maximum_daily_return_loss: float = 0.0075


def _value_area_from_bins(
    volumes: np.ndarray,
    edges: np.ndarray,
    fraction: float,
) -> tuple[float, float, float]:
    if volumes.size == 0 or not np.isfinite(volumes).all() or volumes.sum() <= 0.0:
        return np.nan, np.nan, np.nan
    poc_index = int(np.argmax(volumes))
    target = float(volumes.sum()) * fraction
    accumulated = float(volumes[poc_index])
    lower = upper = poc_index
    while accumulated < target and (lower > 0 or upper < len(volumes) - 1):
        above = float(volumes[upper + 1]) if upper < len(volumes) - 1 else -1.0
        below = float(volumes[lower - 1]) if lower > 0 else -1.0
        if above >= below and upper < len(volumes) - 1:
            upper += 1
            accumulated += max(above, 0.0)
        elif lower > 0:
            lower -= 1
            accumulated += max(below, 0.0)
        else:
            break
    poc = (float(edges[poc_index]) + float(edges[poc_index + 1])) / 2.0
    return poc, float(edges[upper + 1]), float(edges[lower])


def session_volume_profile_proxy(
    bars: pd.DataFrame,
    *,
    bins: int,
    value_area_fraction: float,
    allocation: str,
) -> dict[str, float]:
    """Approximate a session profile by close-bin or uniform range allocation."""
    low = float(bars["low"].min())
    high = float(bars["high"].max())
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        return {"poc": np.nan, "vah": np.nan, "val": np.nan, "allocated_volume": 0.0}
    edges = np.linspace(low, high, bins + 1)
    volumes = np.zeros(bins, dtype=float)
    for bar in bars.itertuples():
        volume = float(bar.volume)
        if not np.isfinite(volume) or volume <= 0.0:
            continue
        if allocation == "close":
            index = int(np.searchsorted(edges, float(bar.close), side="right") - 1)
            volumes[int(np.clip(index, 0, bins - 1))] += volume
            continue
        if allocation != "uniform_range":
            raise ValueError(f"Unknown profile allocation: {allocation}")
        bar_low, bar_high = float(bar.low), float(bar.high)
        if bar_high <= bar_low:
            index = int(np.searchsorted(edges, float(bar.close), side="right") - 1)
            volumes[int(np.clip(index, 0, bins - 1))] += volume
            continue
        overlap = np.maximum(
            0.0,
            np.minimum(edges[1:], bar_high) - np.maximum(edges[:-1], bar_low),
        )
        total_overlap = float(overlap.sum())
        if total_overlap > 0.0:
            volumes += volume * overlap / total_overlap
    poc, vah, val = _value_area_from_bins(volumes, edges, value_area_fraction)
    return {
        "poc": poc,
        "vah": vah,
        "val": val,
        "allocated_volume": float(volumes.sum()),
    }


def build_session_context_proxy(
    bars: pd.DataFrame,
    schedule: pd.DataFrame,
    config: DeepChartsProxyConfig,
) -> pd.DataFrame:
    """Build completed-session profiles and shifted IVB extension statistics."""
    records: list[dict[str, Any]] = []
    for session in schedule.itertuples(index=False):
        session_open = pd.Timestamp(session.session_open)
        session_close = pd.Timestamp(session.session_close)
        frame = bars.loc[(bars.index >= session_open) & (bars.index < session_close)]
        if len(frame) < config.orb_bars:
            continue
        defining = frame.iloc[: config.orb_bars]
        remainder = frame.iloc[config.orb_bars :]
        orb_high = float(defining["high"].max())
        orb_low = float(defining["low"].min())
        orb_width = orb_high - orb_low
        close_profile = session_volume_profile_proxy(
            frame,
            bins=config.profile_bins,
            value_area_fraction=config.value_area_fraction,
            allocation="close",
        )
        uniform_profile = session_volume_profile_proxy(
            frame,
            bins=config.profile_bins,
            value_area_fraction=config.value_area_fraction,
            allocation="uniform_range",
        )
        if orb_width > 0.0 and not remainder.empty:
            upper_extension = max(float(remainder["high"].max()) - orb_high, 0.0) / orb_width
            lower_extension = max(orb_low - float(remainder["low"].min()), 0.0) / orb_width
        else:
            upper_extension = lower_extension = np.nan
        input_volume = float(frame["volume"].clip(lower=0.0).sum())
        records.append(
            {
                "session_date": str(session.session_date),
                "session_open": session_open,
                "available_time": session_close,
                "session_bars": int(len(frame)),
                "orb_high_observed": orb_high,
                "orb_low_observed": orb_low,
                "orb_width_observed": orb_width,
                "upper_extension_observed": upper_extension,
                "lower_extension_observed": lower_extension,
                "profile_input_volume": input_volume,
                "close_profile_allocated_volume": close_profile["allocated_volume"],
                "uniform_profile_allocated_volume": uniform_profile["allocated_volume"],
                "profile_close_poc_observed": close_profile["poc"],
                "profile_close_vah_observed": close_profile["vah"],
                "profile_close_val_observed": close_profile["val"],
                "profile_uniform_poc_observed": uniform_profile["poc"],
                "profile_uniform_vah_observed": uniform_profile["vah"],
                "profile_uniform_val_observed": uniform_profile["val"],
            }
        )
    context = pd.DataFrame(records).sort_values("session_open").reset_index(drop=True)
    if context.empty:
        return context

    previous_columns = {
        "available_time": "prior_profile_available_time",
        "profile_close_poc_observed": "prior_profile_close_poc_proxy",
        "profile_close_vah_observed": "prior_profile_close_vah_proxy",
        "profile_close_val_observed": "prior_profile_close_val_proxy",
        "profile_uniform_poc_observed": "prior_profile_uniform_poc_proxy",
        "profile_uniform_vah_observed": "prior_profile_uniform_vah_proxy",
        "profile_uniform_val_observed": "prior_profile_uniform_val_proxy",
    }
    for source, target in previous_columns.items():
        context[target] = context[source].shift(1)
    context["ivb_latest_observation_time"] = context["available_time"].shift(1)
    for direction in ("upper", "lower"):
        history = context[f"{direction}_extension_observed"].shift(1)
        rolling = history.rolling(
            config.ivb_lookback_sessions,
            min_periods=config.ivb_minimum_sessions,
        )
        for quantile, suffix in ((0.25, "q25"), (0.50, "q50"), (0.75, "q75")):
            context[f"ivb_{direction}_{suffix}_proxy"] = rolling.quantile(quantile)
    return context


def build_five_minute_features_proxy(
    bars: pd.DataFrame,
    schedule: pd.DataFrame,
    session_context: pd.DataFrame,
    config: DeepChartsProxyConfig,
) -> pd.DataFrame:
    """Create causal OHLCV proxies and an exact six-bar opening range."""
    pine_config = PineFabioConfig(
        reward_to_risk=config.reward_to_risk,
        trail_activation_atr=config.trail_activation_atr,
        trail_offset_atr=config.trail_offset_atr,
        maximum_daily_losses=99,
    )
    out = add_pine_indicators(
        bars,
        schedule,
        pine_config,
        bar_minutes=BAR_MINUTES,
        vwap_timezone="UTC",
    )
    out["session_vwap_proxy"] = np.nan
    out["orb_high_proxy"] = np.nan
    out["orb_low_proxy"] = np.nan
    out["orb_width_proxy"] = np.nan
    out["orb_defined_proxy"] = False
    for session in schedule.itertuples(index=False):
        left = int(out.index.searchsorted(pd.Timestamp(session.session_open), side="left"))
        right = int(out.index.searchsorted(pd.Timestamp(session.session_close), side="left"))
        if right - left < config.orb_bars:
            continue
        defining_right = left + config.orb_bars
        defining = out.iloc[left:defining_right]
        orb_high = float(defining["high"].max())
        orb_low = float(defining["low"].min())
        out.iloc[defining_right:right, out.columns.get_loc("orb_high_proxy")] = orb_high
        out.iloc[defining_right:right, out.columns.get_loc("orb_low_proxy")] = orb_low
        out.iloc[defining_right:right, out.columns.get_loc("orb_width_proxy")] = orb_high - orb_low
        out.iloc[defining_right:right, out.columns.get_loc("orb_defined_proxy")] = True
        session_frame = out.iloc[left:right]
        typical = (session_frame["high"] + session_frame["low"] + session_frame["close"]) / 3.0
        cumulative_volume = session_frame["volume"].cumsum().replace(0.0, np.nan)
        session_vwap = (typical * session_frame["volume"]).cumsum() / cumulative_volume
        out.iloc[left:right, out.columns.get_loc("session_vwap_proxy")] = session_vwap.to_numpy()

    out["orb_long_proxy"] = (
        out["orb_defined_proxy"]
        & out["close"].gt(out["orb_high_proxy"])
        & out["close"].shift(1).le(out["orb_high_proxy"])
    )
    out["orb_short_proxy"] = (
        out["orb_defined_proxy"]
        & out["close"].lt(out["orb_low_proxy"])
        & out["close"].shift(1).ge(out["orb_low_proxy"])
    )

    if not session_context.empty:
        attached_columns = [
            "session_date",
            "prior_profile_available_time",
            "prior_profile_close_poc_proxy",
            "prior_profile_close_vah_proxy",
            "prior_profile_close_val_proxy",
            "prior_profile_uniform_poc_proxy",
            "prior_profile_uniform_vah_proxy",
            "prior_profile_uniform_val_proxy",
            "ivb_latest_observation_time",
            "ivb_upper_q25_proxy",
            "ivb_upper_q50_proxy",
            "ivb_upper_q75_proxy",
            "ivb_lower_q25_proxy",
            "ivb_lower_q50_proxy",
            "ivb_lower_q75_proxy",
        ]
        indexed = session_context[attached_columns].set_index("session_date")
        for column in attached_columns[1:]:
            out[column] = out["session_date"].map(indexed[column])

    bar_range = (out["high"] - out["low"]).replace(0.0, np.nan)
    prior_effort_threshold = out["volume"].shift(1).rolling(
        config.effort_lookback_bars,
        min_periods=config.effort_lookback_bars,
    ).quantile(config.effort_quantile)
    prior_range_median = bar_range.shift(1).rolling(
        config.vtracker_range_lookback_bars,
        min_periods=config.vtracker_range_lookback_bars,
    ).median()
    out["effort_ratio_proxy"] = out["volume"] / out["volume"].shift(1).rolling(
        config.effort_lookback_bars,
        min_periods=config.effort_lookback_bars,
    ).median().replace(0.0, np.nan)
    out["result_atr_proxy"] = (out["close"] - out["open"]) / out["atr"]
    out["close_location_proxy"] = (
        2.0 * (out["close"] - out["low"]) / bar_range - 1.0
    ).clip(-1.0, 1.0)
    out["high_effort_proxy"] = out["volume"].gt(prior_effort_threshold)
    out["range_expansion_proxy"] = bar_range.gt(prior_range_median)
    out["effort_long_proxy"] = out["high_effort_proxy"] & out["result_atr_proxy"].gt(0.0)
    out["effort_short_proxy"] = out["high_effort_proxy"] & out["result_atr_proxy"].lt(0.0)
    out["vtracker_long_proxy"] = (
        out["range_expansion_proxy"] & out["close_location_proxy"].ge(0.50)
    )
    out["vtracker_short_proxy"] = (
        out["range_expansion_proxy"] & out["close_location_proxy"].le(-0.50)
    )
    out["delta_proxy"] = out["volume"] * (
        (out["close"] - out["open"]) / bar_range
    ).clip(-1.0, 1.0).fillna(0.0)
    out["smooth_delta_proxy"] = out["delta_proxy"].rolling(
        config.delta_lookback_bars,
        min_periods=config.delta_lookback_bars,
    ).sum()
    return out


def build_raw_proxy_signals(
    features: pd.DataFrame,
    donchian_context: pd.DataFrame,
    config: DeepChartsProxyConfig,
) -> pd.DataFrame:
    """Convert exact-ORB crosses into broker-compatible signal records."""
    candidates = features.loc[features["orb_long_proxy"] | features["orb_short_proxy"]]
    records: list[dict[str, Any]] = []
    for timestamp, bar in candidates.iterrows():
        for side, active in (
            (1, bool(bar["orb_long_proxy"])),
            (-1, bool(bar["orb_short_proxy"])),
        ):
            if not active or not np.isfinite(float(bar["atr"])):
                continue
            close = float(bar["close"])
            atr = float(bar["atr"])
            static_stop = float(bar["low"] - atr) if side > 0 else float(bar["high"] + atr)
            risk = side * (close - static_stop)
            if risk <= 0.0:
                continue
            orb_high = float(bar["orb_high_proxy"])
            orb_low = float(bar["orb_low_proxy"])
            orb_width = float(bar["orb_width_proxy"])
            prefix = "upper" if side > 0 else "lower"
            ivb_quantiles = [float(bar.get(f"ivb_{prefix}_{suffix}_proxy", np.nan)) for suffix in ("q25", "q50", "q75")]
            ivb_targets = [
                (orb_high + quantile * orb_width) if side > 0 else (orb_low - quantile * orb_width)
                for quantile in ivb_quantiles
            ]
            uniform_poc = float(bar.get("prior_profile_uniform_poc_proxy", np.nan))
            close_poc = float(bar.get("prior_profile_close_poc_proxy", np.nan))
            vwap_aligned = side * (close - float(bar["session_vwap_proxy"])) > 0.0
            profile_uniform_aligned = np.isfinite(uniform_poc) and side * (close - uniform_poc) > 0.0
            profile_close_aligned = np.isfinite(close_poc) and side * (close - close_poc) > 0.0
            ivb_room = np.isfinite(ivb_targets[1]) and side * (ivb_targets[1] - close) > 0.0
            effort_aligned = bool(bar["effort_long_proxy"] if side > 0 else bar["effort_short_proxy"])
            vtracker_aligned = bool(bar["vtracker_long_proxy"] if side > 0 else bar["vtracker_short_proxy"])
            delta_aligned = side * float(bar["smooth_delta_proxy"]) > 0.0
            records.append(
                {
                    "signal_time": timestamp,
                    "signal_bar_id": int(bar["bar_id"]),
                    "session_date": str(bar["session_date"]),
                    "side": side,
                    "setup": "orb_proxy",
                    "signal_close": close,
                    "signal_high": float(bar["high"]),
                    "signal_low": float(bar["low"]),
                    "signal_atr": atr,
                    "static_stop": static_stop,
                    "static_target": close + side * risk * config.reward_to_risk,
                    "trail_activation_distance": atr * config.trail_activation_atr,
                    "trail_offset": atr * config.trail_offset_atr,
                    "session_vwap_proxy": float(bar["session_vwap_proxy"]),
                    "prior_profile_uniform_poc_proxy": uniform_poc,
                    "prior_profile_close_poc_proxy": close_poc,
                    "prior_profile_available_time": bar.get("prior_profile_available_time", pd.NaT),
                    "ivb_latest_observation_time": bar.get("ivb_latest_observation_time", pd.NaT),
                    "orb_high_proxy": orb_high,
                    "orb_low_proxy": orb_low,
                    "orb_width_proxy": orb_width,
                    "ivb_target1_proxy": ivb_targets[0],
                    "ivb_target2_proxy": ivb_targets[1],
                    "ivb_target3_proxy": ivb_targets[2],
                    "effort_ratio_proxy": float(bar["effort_ratio_proxy"]),
                    "result_atr_proxy": float(bar["result_atr_proxy"]),
                    "close_location_proxy": float(bar["close_location_proxy"]),
                    "smooth_delta_proxy": float(bar["smooth_delta_proxy"]),
                    "vwap_aligned_proxy": bool(vwap_aligned),
                    "profile_uniform_aligned_proxy": bool(profile_uniform_aligned),
                    "profile_close_aligned_proxy": bool(profile_close_aligned),
                    "ivb_room_proxy": bool(ivb_room),
                    "effort_aligned_proxy": bool(effort_aligned),
                    "vtracker_aligned_proxy": bool(vtracker_aligned),
                    "delta_aligned_proxy": bool(delta_aligned),
                }
            )
    signals = pd.DataFrame(records)
    if signals.empty:
        return signals
    signals = attach_donchian_state(signals, donchian_context)
    signals = signals.rename(columns={"donchian_aligned": "donchian_aligned_proxy"})
    return signals.sort_values(["signal_bar_id", "side"], ascending=[True, False]).reset_index(drop=True)


def select_signal_variants(signals: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Fixed ablations; no grid search or result-dependent thresholds."""
    if signals.empty:
        return {"orb_only_proxy": signals.copy()}
    base = pd.Series(True, index=signals.index)
    vp_uniform = signals["vwap_aligned_proxy"] & signals["profile_uniform_aligned_proxy"]
    vp_close = signals["vwap_aligned_proxy"] & signals["profile_close_aligned_proxy"]
    effort_vtracker = (
        signals["vwap_aligned_proxy"]
        & signals["effort_aligned_proxy"]
        & signals["vtracker_aligned_proxy"]
    )
    full_without_htf = (
        vp_uniform
        & signals["ivb_room_proxy"]
        & signals["effort_aligned_proxy"]
        & signals["vtracker_aligned_proxy"]
    )
    definitions = {
        "orb_only_proxy": base,
        "vwap_profile_uniform_proxy": vp_uniform,
        "vwap_profile_close_proxy": vp_close,
        "ivb_vwap_profile_proxy": vp_uniform & signals["ivb_room_proxy"],
        "effort_vtracker_proxy": effort_vtracker,
        "full_without_htf_proxy": full_without_htf,
        "full_no_delta_proxy": full_without_htf & signals["donchian_aligned_proxy"],
        "full_with_delta_proxy": (
            full_without_htf
            & signals["donchian_aligned_proxy"]
            & signals["delta_aligned_proxy"]
        ),
    }
    return {name: signals.loc[mask].copy() for name, mask in definitions.items()}


def proxy_account_path(
    trades: pd.DataFrame,
    *,
    sizing_variant: str,
    one_way_cost_bps: float,
    config: DeepChartsProxyConfig,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Apply one-times or stop-risk sizing, optionally with a daily halt."""
    rows: list[dict[str, Any]] = []
    equity = 1.0
    active_session: str | None = None
    session_losses = 0
    session_net_return = 0.0
    blocked = 0
    for trade in trades.sort_values("entry_time").itertuples(index=False):
        session = str(trade.session_date)
        if session != active_session:
            active_session = session
            session_losses = 0
            session_net_return = 0.0
        use_risk_manager = sizing_variant == "risk_025pct_cap3x_daily_halt_proxy"
        if use_risk_manager and (
            session_losses >= config.risk_maximum_daily_losses
            or session_net_return <= -config.risk_maximum_daily_return_loss
        ):
            blocked += 1
            continue
        if sizing_variant == "one_x_notional":
            leverage = 1.0
        elif sizing_variant in {
            "risk_025pct_cap3x",
            "risk_025pct_cap3x_daily_halt_proxy",
        }:
            stop_fraction = float(trade.initial_stop_fraction)
            leverage = min(
                config.risk_maximum_leverage,
                config.risk_target_fraction / stop_fraction if stop_fraction > 0.0 else 0.0,
            )
        else:
            raise ValueError(f"Unknown sizing variant: {sizing_variant}")
        gross = float(trade.signed_price_return) * leverage
        cost = 2.0 * one_way_cost_bps / 10_000.0 * leverage
        net = gross - cost
        before = equity
        equity *= 1.0 + net
        session_net_return += net
        if net < 0.0:
            session_losses += 1
        risk_deployed = leverage * float(trade.initial_stop_fraction)
        rows.append(
            {
                "variant": sizing_variant,
                "session_date": session,
                "setup": trade.setup,
                "entry_time": trade.entry_time,
                "exit_time": trade.exit_time,
                "net_return": net,
                "gross_return": gross,
                "execution_cost": cost,
                "effective_leverage": leverage,
                "risk_fraction_deployed": risk_deployed,
                "net_r": net / risk_deployed if risk_deployed > 0.0 else np.nan,
                "equity_before": before,
                "equity_after": equity,
            }
        )
    return pd.DataFrame(rows), {"trades_blocked_by_daily_halt_all_history": blocked}


def _scope_metrics(path: pd.DataFrame) -> list[dict[str, Any]]:
    if path.empty:
        scopes = {"all": path, "development_2022_2024": path, "holdout_2025_plus": path}
    else:
        entry_time = pd.to_datetime(path["entry_time"], utc=True)
        scopes = {
            "all": path,
            "development_2022_2024": path.loc[entry_time < HOLDOUT_START],
            "holdout_2025_plus": path.loc[entry_time >= HOLDOUT_START],
        }
    return [{"scope": scope} | summarize_path(frame) for scope, frame in scopes.items()]


def _break_even_cost_bps(
    trades: pd.DataFrame,
    config: DeepChartsProxyConfig,
) -> float:
    if trades.empty:
        return np.nan
    zero, _ = proxy_account_path(
        trades, sizing_variant="one_x_notional", one_way_cost_bps=0.0, config=config
    )
    if summarize_path(zero)["cumulative_net_return"] <= 0.0:
        return 0.0
    lower, upper = 0.0, 25.0
    for _ in range(45):
        middle = (lower + upper) / 2.0
        path, _ = proxy_account_path(
            trades,
            sizing_variant="one_x_notional",
            one_way_cost_bps=middle,
            config=config,
        )
        if summarize_path(path)["cumulative_net_return"] > 0.0:
            lower = middle
        else:
            upper = middle
    return float((lower + upper) / 2.0)


def _audit_proxy(
    bars: pd.DataFrame,
    raw_signals: pd.DataFrame,
    signal_sets: dict[str, pd.DataFrame],
    trade_sets: dict[str, pd.DataFrame],
    session_context: pd.DataFrame,
    config: DeepChartsProxyConfig,
) -> dict[str, Any]:
    profile_time = pd.to_datetime(raw_signals["prior_profile_available_time"], utc=True)
    profile_observed = profile_time.notna()
    profile_available = raw_signals.empty or (
        profile_time.loc[profile_observed]
        .le(raw_signals.loc[profile_observed, "signal_time"])
        .all()
    )
    ivb_time = pd.to_datetime(raw_signals["ivb_latest_observation_time"], utc=True)
    ivb_observed = ivb_time.notna()
    ivb_available = raw_signals.empty or (
        ivb_time.loc[ivb_observed]
        .le(raw_signals.loc[ivb_observed, "signal_time"])
        .all()
    )
    htf_frames = [
        frame for name, frame in signal_sets.items() if name in {"full_no_delta_proxy", "full_with_delta_proxy"}
    ]
    htf_available = all(
        frame.empty or frame["available_time"].le(frame["signal_time"]).all()
        for frame in htf_frames
    )
    next_bar = all(
        frame.empty or frame["entry_bar_id"].eq(frame["signal_bar_id"] + 1).all()
        for frame in trade_sets.values()
    )
    uniform_error = (
        session_context["uniform_profile_allocated_volume"]
        - session_context["profile_input_volume"]
    ).abs()
    close_error = (
        session_context["close_profile_allocated_volume"]
        - session_context["profile_input_volume"]
    ).abs()
    volume_conserved = bool(
        np.allclose(uniform_error.to_numpy(), 0.0, atol=1e-7, rtol=1e-10)
        and np.allclose(close_error.to_numpy(), 0.0, atol=1e-7, rtol=1e-10)
    )

    cutoff = min(100_000, len(bars) - 1)
    prefix_bars = bars.iloc[:cutoff].copy()
    prefix_schedule = build_seven_day_schedule(prefix_bars.index, "UTC")
    prefix_context = build_session_context_proxy(prefix_bars, prefix_schedule, config)
    cutoff_time = prefix_bars.index.max()
    columns = [
        "session_date",
        "prior_profile_uniform_poc_proxy",
        "prior_profile_close_poc_proxy",
        "ivb_upper_q50_proxy",
        "ivb_lower_q50_proxy",
    ]
    full_common = session_context.loc[session_context["available_time"] <= cutoff_time, columns].reset_index(drop=True)
    prefix_common = prefix_context.loc[prefix_context["available_time"] <= cutoff_time, columns].reset_index(drop=True)
    prefix_invariant = bool(
        len(full_common) == len(prefix_common)
        and full_common["session_date"].equals(prefix_common["session_date"])
        and np.allclose(
            full_common[columns[1:]].to_numpy(dtype=float),
            prefix_common[columns[1:]].to_numpy(dtype=float),
            equal_nan=True,
        )
    )
    checks = {
        "prior_session_profile_available_before_signal": bool(profile_available),
        "ivb_rolling_sample_available_before_signal": bool(ivb_available),
        "completed_four_hour_context_available_before_signal": bool(htf_available),
        "entry_is_next_five_minute_open": bool(next_bar),
        "profile_allocations_conserve_session_volume": volume_conserved,
        "session_context_prefix_invariance": prefix_invariant,
        "opening_range_uses_exactly_six_completed_bars": config.orb_bars == 6,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "notes": {
            "signal_bar_timing": "OHLCV signal fields are known at bar close; fills occur at the next bar open.",
            "profile_timing": "Only the previous completed 09:30-16:00 UTC session profile is attached.",
            "ivb_timing": "Current-session targets use rolling quantiles of prior completed sessions only.",
            "warmup": "Missing prior-profile or IVB values during warmup are unavailable, never future-filled.",
        },
    }


def _report(
    summary: pd.DataFrame,
    funnel: pd.DataFrame,
    break_even: pd.DataFrame,
    risk: pd.DataFrame,
    audit: dict[str, Any],
    data_quality: dict[str, Any],
    config: DeepChartsProxyConfig,
) -> str:
    zero = summary.loc[
        (summary["scope"] == "all") & summary["one_way_cost_bps"].eq(0.0),
        ["filter_variant", "trades", "profit_factor", "cumulative_net_return", "maximum_drawdown"],
    ]
    reference = summary.loc[
        (summary["scope"] == "all") & summary["one_way_cost_bps"].eq(REFERENCE_ONE_WAY_COST_BPS),
        ["filter_variant", "trades", "win_rate", "average_net_r", "profit_factor", "cumulative_net_return", "maximum_drawdown"],
    ]
    holdout = summary.loc[
        (summary["scope"] == "holdout_2025_plus")
        & summary["one_way_cost_bps"].eq(REFERENCE_ONE_WAY_COST_BPS),
        ["filter_variant", "trades", "profit_factor", "cumulative_net_return", "maximum_drawdown"],
    ]
    risk_view = risk.loc[
        risk["scope"].isin(["all", "holdout_2025_plus"]),
        ["filter_variant", "sizing_variant", "scope", "trades", "profit_factor", "cumulative_net_return", "maximum_drawdown", "average_effective_leverage", "trades_blocked_by_daily_halt_all_history"],
    ]
    primary_costs = summary.loc[
        summary["filter_variant"].isin(["full_no_delta_proxy", "full_with_delta_proxy"])
        & summary["scope"].isin(["all", "holdout_2025_plus"]),
        ["filter_variant", "one_way_cost_bps", "scope", "trades", "profit_factor", "cumulative_net_return", "maximum_drawdown"],
    ]
    primary_zero = summary.loc[
        (summary["filter_variant"] == "full_no_delta_proxy")
        & (summary["scope"] == "all")
        & summary["one_way_cost_bps"].eq(0.0)
    ].iloc[0]
    primary_reference = summary.loc[
        (summary["filter_variant"] == "full_no_delta_proxy")
        & (summary["scope"] == "all")
        & summary["one_way_cost_bps"].eq(REFERENCE_ONE_WAY_COST_BPS)
    ].iloc[0]
    primary_holdout = summary.loc[
        (summary["filter_variant"] == "full_no_delta_proxy")
        & (summary["scope"] == "holdout_2025_plus")
        & summary["one_way_cost_bps"].eq(REFERENCE_ONE_WAY_COST_BPS)
    ].iloc[0]
    primary_break_even = float(
        break_even.loc[
            break_even["filter_variant"] == "full_no_delta_proxy",
            "break_even_one_way_cost_bps",
        ].iloc[0]
    )
    return f"""# BTC five-minute Fabio/DeepCharts-inspired proxy study

## Decision

This is an OHLCV proxy test, not a recreation of Deep Print, DeepTrades, true bid/ask delta, order-book absorption, IVB, Deep Effort, or V-Tracker. Every approximation is explicitly suffixed `proxy`. The holdout is 2025 through 25 February 2026; thresholds were fixed before that split was inspected.

The primary `full_no_delta_proxy` has a gross signal but no executable edge under the reference cost: zero-cost PF is {primary_zero['profit_factor']:.3f}, return {primary_zero['cumulative_net_return']:.1%}, and drawdown {primary_zero['maximum_drawdown']:.1%}; at 6 bps per side it returns {primary_reference['cumulative_net_return']:.1%} overall and {primary_holdout['cumulative_net_return']:.1%} in holdout. Its full-history break-even cost is only {primary_break_even:.2f} bps per side. Therefore this version is rejected for market-order deployment.

## Zero-cost one-times-notional results

{_markdown_table(zero)}

## Reference execution cost: 6 bps per side

{_markdown_table(reference)}

## Holdout at 6 bps per side

{_markdown_table(holdout)}

## Signal funnel

{_markdown_table(funnel)}

## Break-even one-way execution cost

{_markdown_table(break_even)}

## Primary-stack cost curve

{_markdown_table(primary_costs)}

## Risk sizing at 6 bps per side

{_markdown_table(risk_view)}

## Frozen workflow

1. **Macro/HTF bias proxy:** persistent 20-bar Donchian state from completed four-hour bars.
2. **Daily/session bias proxy:** price must agree with the current 09:30-16:00 UTC session VWAP.
3. **Area of interest proxy:** direction must agree with the previous completed session POC. Uniform high-low volume allocation is primary; close-bin allocation is a sensitivity.
4. **IVB proxy:** the first exactly six five-minute bars define the opening range. Targets 1/2/3 are the rolling 25th/50th/75th percentiles of same-direction session extension over the previous {config.ivb_lookback_sessions} sessions (minimum {config.ivb_minimum_sessions}). A signal is not chased beyond target 2.
5. **Effort proxy:** signal-bar volume exceeds the prior {config.effort_lookback_bars}-bar 75th percentile and its candle body agrees with direction.
6. **V-Tracker proxy:** signal-bar range exceeds the prior {config.vtracker_range_lookback_bars}-bar median and closes in the directional outer quartile.
7. **Delta proxy:** five-bar sum of `volume * (close-open)/(high-low)`. It is a candle-position proxy, not aggressor delta, so the primary full variant excludes it.
8. **Entry/risk/exit:** confirmed signal, next five-minute open, stop one ATR beyond the signal bar, 2R static target, and the supplied 1.5 ATR activation / 0.5 ATR trailing logic.
9. **Risk-manager proxy:** 0.25% equity risk per initial stop, 3x leverage cap, halt after two losses or -0.75% summed session return.

## Causality and limitations

- Audit: **{audit['status']}**.
- Profiles are previous-session estimates; five-minute bars do not reveal price-level volume.
- Synthetic delta is isolated in an ablation and must not be interpreted as order flow.
- Entries are next-bar, but stop/target ordering inside each five-minute bar still uses a deterministic OHLC path assumption.
- The file has {data_quality['missing_five_minute_bars']} missing bars and a maximum {data_quality['maximum_gap_minutes']:.0f}-minute gap.
- Venue/product identity and funding are absent; 6 bps per side is a scenario, not a verified fee quote.
- Eight fixed variants share the holdout. Picking whichever looks best after reading this report is model selection, not independent confirmation.

Research only; live deployment remains blocked without trade-level data, verified product metadata, funding, and forward/paper execution evidence.
"""


def build_btc_deepcharts_proxy_backtest(
    project_root: str | Path | None = None,
    *,
    data_path: str | Path = DEFAULT_DATA,
    output_dir: str | Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)

    def resolved(value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else root / path

    data_file = resolved(data_path)
    output = resolved(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    bars, data_quality = load_binance_btc_5m(data_file)
    schedule = build_seven_day_schedule(bars.index, "UTC")
    config = DeepChartsProxyConfig()
    pine_config = PineFabioConfig(
        reward_to_risk=config.reward_to_risk,
        trail_activation_atr=config.trail_activation_atr,
        trail_offset_atr=config.trail_offset_atr,
        maximum_daily_losses=99,
    )
    session_context = build_session_context_proxy(bars, schedule, config)
    features = build_five_minute_features_proxy(bars, schedule, session_context, config)
    donchian_context = build_donchian_context(
        bars,
        timeframe_minutes=config.donchian_timeframe_minutes,
        length=config.donchian_length,
    )
    raw_signals = build_raw_proxy_signals(features, donchian_context, config)
    signal_sets = select_signal_variants(raw_signals)

    summary_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []
    funnel_rows: list[dict[str, Any]] = []
    break_even_rows: list[dict[str, Any]] = []
    trade_sets: dict[str, pd.DataFrame] = {}
    execution_diagnostics: dict[str, Any] = {}
    for name, selected in signal_sets.items():
        trades, diagnostics = run_broker_emulator(features, selected, pine_config)
        trade_sets[name] = trades
        execution_diagnostics[name] = diagnostics
        selected.to_csv(output / f"signals_{name}.csv", index=False)
        trades.to_csv(output / f"trades_{name}.csv", index=False)
        funnel_rows.append(
            {
                "filter_variant": name,
                "raw_signals": int(len(raw_signals)),
                "selected_signals": int(len(selected)),
                "executed_trades": int(len(trades)),
                "signal_retention": float(len(selected) / len(raw_signals)) if len(raw_signals) else np.nan,
            }
        )
        for cost in COSTS_BPS:
            path, _ = proxy_account_path(
                trades,
                sizing_variant="one_x_notional",
                one_way_cost_bps=cost,
                config=config,
            )
            for metrics in _scope_metrics(path):
                summary_rows.append(
                    {"filter_variant": name, "one_way_cost_bps": cost} | metrics
                )
        break_even_rows.append(
            {
                "filter_variant": name,
                "break_even_one_way_cost_bps": _break_even_cost_bps(trades, config),
            }
        )
        if name in {"orb_only_proxy", "full_no_delta_proxy", "full_with_delta_proxy"}:
            for sizing in (
                "one_x_notional",
                "risk_025pct_cap3x",
                "risk_025pct_cap3x_daily_halt_proxy",
            ):
                path, risk_diagnostics = proxy_account_path(
                    trades,
                    sizing_variant=sizing,
                    one_way_cost_bps=REFERENCE_ONE_WAY_COST_BPS,
                    config=config,
                )
                for metrics in _scope_metrics(path):
                    risk_rows.append(
                        {
                            "filter_variant": name,
                            "sizing_variant": sizing,
                            "one_way_cost_bps": REFERENCE_ONE_WAY_COST_BPS,
                            **risk_diagnostics,
                        }
                        | metrics
                    )

    summary = pd.DataFrame(summary_rows)
    risk = pd.DataFrame(risk_rows)
    funnel = pd.DataFrame(funnel_rows)
    break_even = pd.DataFrame(break_even_rows)
    audit = _audit_proxy(
        bars, raw_signals, signal_sets, trade_sets, session_context, config
    )
    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "RESEARCH_ONLY_LIVE_DEPLOYMENT_BLOCKED",
        "data_source": str(data_file),
        "data_quality": data_quality,
        "development_period": "2022-01-01 through 2024-12-31",
        "holdout_period": "2025-01-01 through 2026-02-25",
        "session_interpretation": "09:30-16:00 UTC, seven days per week",
        "config": asdict(config),
        "costs_bps_per_side": COSTS_BPS,
        "reference_one_way_cost_bps": REFERENCE_ONE_WAY_COST_BPS,
        "execution_diagnostics": execution_diagnostics,
        "causality_audit": audit,
        "proprietary_parity_claimed": False,
    }
    raw_signals.to_csv(output / "raw_feature_signals.csv", index=False)
    session_context.to_csv(output / "session_context_proxy.csv", index=False)
    donchian_context.to_csv(output / "donchian_240m_context.csv", index=False)
    summary.to_csv(output / "summary.csv", index=False)
    risk.to_csv(output / "risk_management.csv", index=False)
    funnel.to_csv(output / "signal_funnel.csv", index=False)
    break_even.to_csv(output / "break_even_costs.csv", index=False)
    (output / "causality_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    (output / "governance.json").write_text(json.dumps(governance, indent=2), encoding="utf-8")
    report = _report(summary, funnel, break_even, risk, audit, data_quality, config)
    report_path = output / "report.md"
    report_path.write_text(report, encoding="utf-8")
    return {
        "report_path": report_path,
        "summary": summary,
        "risk": risk,
        "funnel": funnel,
        "break_even": break_even,
        "audit": audit,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root")
    parser.add_argument("--data-path", default=str(DEFAULT_DATA))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_btc_deepcharts_proxy_backtest(
        project_root=args.project_root,
        data_path=args.data_path,
        output_dir=args.output_dir,
    )
    print(f"Report: {result['report_path']}")
    print(
        result["summary"].loc[
            (result["summary"]["scope"] == "all")
            & result["summary"]["one_way_cost_bps"].eq(REFERENCE_ONE_WAY_COST_BPS)
        ].to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
