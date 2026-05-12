from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .data import load_asset_daily, resolve_project_root
from .macro_report import load_model_macro_frame

DEFAULT_OUTPUT_DIR = Path("outputs") / "spy_vix_fear_greed_research"
DEFAULT_HORIZONS: tuple[int, ...] = (1, 5, 10, 20)
DEFAULT_LOOKBACK_WINDOW = 252
DEFAULT_MIN_PERIODS = 63
DEFAULT_BUCKET_COUNT = 5
DEFAULT_HOLD_DAYS = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Study SPY plus VIX fear/greed/panic states, measure signal-to-noise, "
            "and test whether the footprint looks exploitable after a one-bar implementation lag."
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
        help="Directory for the generated SPY/VIX fear-greed research outputs.",
    )
    parser.add_argument(
        "--lookback-window",
        type=int,
        default=DEFAULT_LOOKBACK_WINDOW,
        help="Trailing window used for causal z-scores and percentiles.",
    )
    parser.add_argument(
        "--min-periods",
        type=int,
        default=DEFAULT_MIN_PERIODS,
        help="Minimum trailing observations required before features become active.",
    )
    parser.add_argument(
        "--bucket-count",
        type=int,
        default=DEFAULT_BUCKET_COUNT,
        help="Number of fear-greed score buckets used in the ex-post bucket study.",
    )
    parser.add_argument(
        "--hold-days",
        type=int,
        default=DEFAULT_HOLD_DAYS,
        help="Holding window used for the simple exploitability backtests.",
    )
    parser.add_argument(
        "--horizons",
        type=int,
        nargs="+",
        default=list(DEFAULT_HORIZONS),
        help="Forward return horizons to evaluate after the one-bar implementation lag.",
    )
    return parser.parse_args()


def _resolve_output_path(root: Path, target: Path) -> Path:
    return target if target.is_absolute() else root / target


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(numeric):
        return None
    return numeric


def _causal_zscore(series: pd.Series, *, window: int, min_periods: int) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    rolling = numeric.rolling(window=window, min_periods=min_periods)
    mean = rolling.mean()
    std = rolling.std(ddof=0).replace(0.0, np.nan)
    zscore = (numeric - mean) / std
    return zscore.replace([np.inf, -np.inf], np.nan)


def _rolling_percentile(series: pd.Series, *, window: int, min_periods: int) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.rolling(window=window, min_periods=min_periods).apply(
        lambda values: float(pd.Series(values).rank(pct=True).iloc[-1]),
        raw=False,
    )


def _signal_to_noise(values: pd.Series) -> float | None:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return None
    std = float(clean.std(ddof=0))
    if std <= 0.0 or not np.isfinite(std):
        return None
    return float(clean.mean() / std)


def _t_stat(values: pd.Series) -> float | None:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if len(clean) < 2:
        return None
    std = float(clean.std(ddof=0))
    if std <= 0.0 or not np.isfinite(std):
        return None
    return float(clean.mean() / (std / np.sqrt(len(clean))))


def _return_summary(values: pd.Series) -> dict[str, float | int | str | None]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return {
            "observations": 0,
            "mean_return": None,
            "median_return": None,
            "std_return": None,
            "avg_abs_return": None,
            "positive_rate": None,
            "loss_rate": None,
            "signal_to_noise": None,
            "t_stat": None,
            "expected_direction": "flat",
        }

    mean_return = float(clean.mean())
    expected_direction = "positive" if mean_return > 0.0 else "negative" if mean_return < 0.0 else "flat"
    return {
        "observations": int(len(clean)),
        "mean_return": mean_return,
        "median_return": float(clean.median()),
        "std_return": float(clean.std(ddof=0)),
        "avg_abs_return": float(clean.abs().mean()),
        "positive_rate": float((clean > 0.0).mean()),
        "loss_rate": float((clean < 0.0).mean()),
        "signal_to_noise": _signal_to_noise(clean),
        "t_stat": _t_stat(clean),
        "expected_direction": expected_direction,
    }


def build_spy_vix_fear_greed_frame(
    *,
    project_root: str | Path | None = None,
    lookback_window: int = DEFAULT_LOOKBACK_WINDOW,
    min_periods: int = DEFAULT_MIN_PERIODS,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> pd.DataFrame:
    root = resolve_project_root(project_root)
    spy = load_asset_daily("SPY", project_root=root).sort_index()
    macro = load_model_macro_frame(project_root=root).sort_index()
    macro = macro.reindex(spy.index).ffill()

    frame = pd.DataFrame(index=pd.DatetimeIndex(spy.index))
    frame.index.name = "signal_date"

    close = pd.to_numeric(spy["close"], errors="coerce")
    frame["spy_close"] = close
    frame["spot_vix"] = pd.to_numeric(macro["spot_vix"], errors="coerce") if "spot_vix" in macro.columns else np.nan
    frame["vix3m_level"] = pd.to_numeric(macro["vix3m_level"], errors="coerce") if "vix3m_level" in macro.columns else np.nan

    frame["spy_return_1d"] = close.pct_change()
    frame["spy_log_return_1d"] = np.log(close).diff()
    frame["spy_trend_5d"] = close.pct_change(5)
    frame["spy_trend_20d"] = close.pct_change(20)
    frame["spy_trend_63d"] = close.pct_change(63)
    frame["spy_drawdown_20d"] = close / close.rolling(window=20, min_periods=20).max() - 1.0
    frame["spy_drawdown_63d"] = close / close.rolling(window=63, min_periods=63).max() - 1.0
    frame["spy_realized_vol_20d"] = frame["spy_return_1d"].rolling(window=20, min_periods=20).std(ddof=0) * np.sqrt(252.0)
    frame["spot_vix_change_1d"] = frame["spot_vix"].diff(1)
    frame["spot_vix_change_5d"] = frame["spot_vix"].diff(5)
    frame["spot_vix_pct_change_5d"] = frame["spot_vix"].pct_change(5)
    frame["vix_curve_contango"] = frame["vix3m_level"] / frame["spot_vix"] - 1.0
    frame["vix_backwardation"] = frame["spot_vix"] / frame["vix3m_level"] - 1.0

    frame["spy_trend_5d_zscore"] = _causal_zscore(frame["spy_trend_5d"], window=lookback_window, min_periods=min_periods)
    frame["spy_trend_20d_zscore"] = _causal_zscore(frame["spy_trend_20d"], window=lookback_window, min_periods=min_periods)
    frame["spy_trend_63d_zscore"] = _causal_zscore(frame["spy_trend_63d"], window=lookback_window, min_periods=min_periods)
    frame["spy_drawdown_20d_zscore"] = _causal_zscore(frame["spy_drawdown_20d"], window=lookback_window, min_periods=min_periods)
    frame["spy_drawdown_63d_zscore"] = _causal_zscore(frame["spy_drawdown_63d"], window=lookback_window, min_periods=min_periods)
    frame["spy_realized_vol_20d_zscore"] = _causal_zscore(frame["spy_realized_vol_20d"], window=lookback_window, min_periods=min_periods)
    frame["spot_vix_zscore_252d"] = _causal_zscore(frame["spot_vix"], window=lookback_window, min_periods=min_periods)
    frame["spot_vix_percentile_252d"] = _rolling_percentile(frame["spot_vix"], window=lookback_window, min_periods=min_periods)
    frame["spot_vix_change_5d_zscore"] = _causal_zscore(frame["spot_vix_change_5d"], window=lookback_window, min_periods=min_periods)
    frame["vix_curve_contango_zscore"] = _causal_zscore(frame["vix_curve_contango"], window=lookback_window, min_periods=min_periods)

    greed_components = pd.DataFrame(index=frame.index)
    greed_components["trend_fast"] = frame["spy_trend_5d_zscore"]
    greed_components["trend_medium"] = frame["spy_trend_20d_zscore"]
    greed_components["trend_slow"] = frame["spy_trend_63d_zscore"]
    greed_components["drawdown_calm"] = frame["spy_drawdown_63d_zscore"]
    greed_components["vix_calm"] = -frame["spot_vix_zscore_252d"]
    greed_components["curve_calm"] = frame["vix_curve_contango_zscore"]
    greed_components["realized_vol_calm"] = -frame["spy_realized_vol_20d_zscore"]
    frame["fear_greed_score"] = greed_components.mean(axis=1)

    panic_components = pd.DataFrame(index=frame.index)
    panic_components["drawdown_shock"] = -frame["spy_drawdown_20d_zscore"]
    panic_components["drawdown_persistence"] = -frame["spy_drawdown_63d_zscore"]
    panic_components["vix_stress"] = frame["spot_vix_zscore_252d"]
    panic_components["vix_spike"] = frame["spot_vix_change_5d_zscore"]
    panic_components["curve_inversion"] = -frame["vix_curve_contango_zscore"]
    panic_components["realized_vol_stress"] = frame["spy_realized_vol_20d_zscore"]
    frame["panic_score"] = panic_components.mean(axis=1)
    frame["fear_score"] = (-frame["fear_greed_score"] + frame["panic_score"]) / 2.0

    valid_state_inputs = frame[
        [
            "fear_greed_score",
            "panic_score",
            "spot_vix_percentile_252d",
            "spy_drawdown_20d",
            "vix_curve_contango",
        ]
    ].notna().all(axis=1)
    state = pd.Series(pd.NA, index=frame.index, dtype="string")
    state.loc[valid_state_inputs] = "Neutral"

    panic_mask = (
        valid_state_inputs
        & (frame["panic_score"] >= 0.75)
        & (frame["spot_vix_percentile_252d"] >= 0.80)
        & (frame["spy_drawdown_20d"] <= -0.08)
        & (frame["vix_curve_contango"] <= 0.05)
    )
    fear_mask = (
        valid_state_inputs
        & ~panic_mask
        & (
            ((frame["fear_greed_score"] <= -0.35) & (frame["spot_vix_percentile_252d"] >= 0.55))
            | ((frame["spy_drawdown_20d"] <= -0.04) & (frame["spot_vix_zscore_252d"] >= 0.50))
        )
    )
    greed_mask = (
        valid_state_inputs
        & ~panic_mask
        & (frame["fear_greed_score"] >= 0.35)
        & (frame["spot_vix_percentile_252d"] <= 0.45)
        & (frame["spy_drawdown_20d"] >= -0.03)
        & (frame["vix_curve_contango"] >= -0.05)
    )

    state.loc[panic_mask] = "Panic"
    state.loc[fear_mask] = "Fear"
    state.loc[greed_mask] = "Greed"
    frame["sentiment_state"] = state

    frame["signal_strength"] = frame[["fear_greed_score", "panic_score"]].abs().max(axis=1)
    rank_pct = frame["fear_greed_score"].rank(pct=True, method="average")
    frame["fear_greed_rank_pct"] = rank_pct

    signal_dates = pd.Series(frame.index, index=frame.index)
    frame["entry_date"] = signal_dates.shift(-1)
    for horizon in sorted(set(int(horizon) for horizon in horizons if int(horizon) > 0)):
        frame[f"exit_date_{horizon}d"] = signal_dates.shift(-(horizon + 1))
        frame[f"forward_return_{horizon}d"] = close.shift(-(horizon + 1)) / close.shift(-1) - 1.0

    return frame.sort_index()


def build_state_summary(frame: pd.DataFrame, *, horizons: tuple[int, ...]) -> pd.DataFrame:
    valid = frame.dropna(subset=["sentiment_state"]).copy()
    if valid.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    groups: list[tuple[str, pd.DataFrame]] = [("ALL", valid)]
    groups.extend((str(state_name), group) for state_name, group in valid.groupby("sentiment_state"))

    for state_name, group in groups:
        for horizon in horizons:
            summary = _return_summary(group[f"forward_return_{horizon}d"])
            rows.append(
                {
                    "state": state_name,
                    "horizon_days": int(horizon),
                    "avg_fear_greed_score": _safe_float(group["fear_greed_score"].mean()),
                    "avg_panic_score": _safe_float(group["panic_score"].mean()),
                    "avg_signal_strength": _safe_float(group["signal_strength"].mean()),
                    **summary,
                }
            )

    return pd.DataFrame(rows).sort_values(["horizon_days", "state"]).reset_index(drop=True)


def _bucket_labels(bucket_count: int) -> list[str]:
    if bucket_count == 5:
        return ["Most Fearful", "Fearful", "Neutral", "Greedy", "Most Greedy"]
    return [f"Bucket {bucket_index}" for bucket_index in range(1, bucket_count + 1)]


def build_bucket_summary(frame: pd.DataFrame, *, horizons: tuple[int, ...], bucket_count: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    valid = frame.dropna(subset=["fear_greed_score"]).copy()
    if valid.empty or bucket_count < 2:
        return pd.DataFrame(), pd.DataFrame()

    labels = _bucket_labels(bucket_count)
    edges = np.linspace(0.0, 1.0, bucket_count + 1)
    valid["fear_greed_bucket"] = pd.cut(
        valid["fear_greed_rank_pct"],
        bins=edges,
        labels=labels,
        include_lowest=True,
    )
    valid = valid.dropna(subset=["fear_greed_bucket"])
    if valid.empty:
        return pd.DataFrame(), pd.DataFrame()

    label_order = {label: index + 1 for index, label in enumerate(labels)}
    rows: list[dict[str, Any]] = []
    for bucket_label, group in valid.groupby("fear_greed_bucket", observed=False):
        bucket_name = str(bucket_label)
        bucket_rank = label_order.get(bucket_name)
        if bucket_rank is None:
            continue
        for horizon in horizons:
            summary = _return_summary(group[f"forward_return_{horizon}d"])
            rows.append(
                {
                    "fear_greed_bucket": bucket_name,
                    "bucket_rank": int(bucket_rank),
                    "horizon_days": int(horizon),
                    "avg_fear_greed_score": _safe_float(group["fear_greed_score"].mean()),
                    "avg_panic_score": _safe_float(group["panic_score"].mean()),
                    **summary,
                }
            )

    bucket_summary = pd.DataFrame(rows).sort_values(["horizon_days", "bucket_rank"]).reset_index(drop=True)
    if bucket_summary.empty:
        return bucket_summary, pd.DataFrame()

    edge_rows: list[dict[str, Any]] = []
    for horizon in horizons:
        horizon_frame = bucket_summary.loc[bucket_summary["horizon_days"] == int(horizon)]
        if horizon_frame.empty:
            continue
        bottom = horizon_frame.sort_values("bucket_rank").iloc[0]
        top = horizon_frame.sort_values("bucket_rank").iloc[-1]
        edge_rows.append(
            {
                "horizon_days": int(horizon),
                "bottom_bucket": str(bottom["fear_greed_bucket"]),
                "top_bucket": str(top["fear_greed_bucket"]),
                "bottom_mean_return": _safe_float(bottom["mean_return"]),
                "top_mean_return": _safe_float(top["mean_return"]),
                "top_minus_bottom_return": _safe_float((top["mean_return"] or 0.0) - (bottom["mean_return"] or 0.0))
                if top["mean_return"] is not None and bottom["mean_return"] is not None
                else None,
                "top_signal_to_noise": _safe_float(top["signal_to_noise"]),
                "bottom_signal_to_noise": _safe_float(bottom["signal_to_noise"]),
            }
        )
    return bucket_summary, pd.DataFrame(edge_rows)


def build_feature_footprint(frame: pd.DataFrame, *, horizons: tuple[int, ...]) -> pd.DataFrame:
    feature_names = (
        "fear_greed_score",
        "fear_score",
        "panic_score",
        "spot_vix_percentile_252d",
        "vix_curve_contango",
        "spy_drawdown_20d",
        "spy_trend_20d",
    )
    rows: list[dict[str, Any]] = []
    for feature_name in feature_names:
        if feature_name not in frame.columns:
            continue
        for horizon in horizons:
            target_name = f"forward_return_{horizon}d"
            pair = frame[[feature_name, target_name]].dropna()
            if len(pair) < 50:
                continue
            correlation = pair[feature_name].corr(pair[target_name])
            upper_threshold = float(pair[feature_name].quantile(0.80))
            lower_threshold = float(pair[feature_name].quantile(0.20))
            upper = pair.loc[pair[feature_name] >= upper_threshold, target_name]
            lower = pair.loc[pair[feature_name] <= lower_threshold, target_name]
            rows.append(
                {
                    "feature": feature_name,
                    "horizon_days": int(horizon),
                    "observations": int(len(pair)),
                    "correlation": _safe_float(correlation),
                    "upper_bucket_mean_return": _safe_float(upper.mean()),
                    "lower_bucket_mean_return": _safe_float(lower.mean()),
                    "upper_minus_lower_mean_return": _safe_float(upper.mean() - lower.mean())
                    if not upper.empty and not lower.empty
                    else None,
                    "upper_bucket_signal_to_noise": _signal_to_noise(upper),
                    "lower_bucket_signal_to_noise": _signal_to_noise(lower),
                }
            )
    return pd.DataFrame(rows).sort_values(["horizon_days", "feature"]).reset_index(drop=True)


def build_state_inaccuracy_summary(frame: pd.DataFrame, *, horizons: tuple[int, ...]) -> pd.DataFrame:
    valid = frame.dropna(subset=["sentiment_state"]).copy()
    if valid.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for state_name, group in valid.groupby("sentiment_state"):
        for horizon in horizons:
            returns = pd.to_numeric(group[f"forward_return_{horizon}d"], errors="coerce").dropna()
            if returns.empty:
                continue
            mean_return = float(returns.mean())
            expected_direction = "positive" if mean_return > 0.0 else "negative" if mean_return < 0.0 else "flat"
            if expected_direction == "flat":
                accuracy_rate = None
                inaccuracy_rate = None
                error_returns = pd.Series(dtype="float64")
            elif expected_direction == "positive":
                accuracy_rate = float((returns > 0.0).mean())
                inaccuracy_rate = float((returns <= 0.0).mean())
                error_returns = returns.loc[returns <= 0.0]
            else:
                accuracy_rate = float((returns < 0.0).mean())
                inaccuracy_rate = float((returns >= 0.0).mean())
                error_returns = returns.loc[returns >= 0.0]

            rows.append(
                {
                    "state": str(state_name),
                    "horizon_days": int(horizon),
                    "expected_direction": expected_direction,
                    "observations": int(len(returns)),
                    "mean_return": mean_return,
                    "accuracy_rate": accuracy_rate,
                    "inaccuracy_rate": inaccuracy_rate,
                    "avg_error_return": _safe_float(error_returns.mean()),
                    "median_error_return": _safe_float(error_returns.median()),
                    "error_signal_to_noise": _signal_to_noise(error_returns),
                }
            )
    return pd.DataFrame(rows).sort_values(["horizon_days", "state"]).reset_index(drop=True)


def _strategy_is_active(row: pd.Series, strategy_name: str) -> bool:
    raw_state = row.get("sentiment_state")
    state = "" if pd.isna(raw_state) else str(raw_state)
    fear_greed_score = _safe_float(row.get("fear_greed_score"))
    panic_score = _safe_float(row.get("panic_score"))
    if strategy_name == "greed_follow":
        return state == "Greed"
    if strategy_name == "fear_panic_avoidance":
        return state not in {"Fear", "Panic", ""}
    if strategy_name == "panic_rebound":
        return state == "Panic"
    if strategy_name == "high_conviction_risk_on":
        return (fear_greed_score is not None) and (fear_greed_score >= 0.50) and state != "Panic"
    if strategy_name == "high_conviction_risk_off":
        return (panic_score is not None) and (panic_score >= 0.85)
    return False


def build_strategy_periods(
    frame: pd.DataFrame,
    *,
    hold_days: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    target_name = f"forward_return_{hold_days}d"
    valid = frame.dropna(subset=[target_name]).reset_index().rename(columns={"index": "signal_date"})
    if valid.empty:
        return pd.DataFrame(), pd.DataFrame()

    strategy_names = (
        "greed_follow",
        "fear_panic_avoidance",
        "panic_rebound",
        "high_conviction_risk_on",
        "high_conviction_risk_off",
    )
    period_rows: list[dict[str, Any]] = []

    for strategy_name in strategy_names:
        pointer = 0
        while pointer < len(valid):
            row = valid.iloc[pointer]
            benchmark_return = _safe_float(row[target_name])
            if benchmark_return is None:
                pointer += hold_days
                continue

            is_active = _strategy_is_active(row, strategy_name)
            strategy_return = benchmark_return if is_active else 0.0
            if strategy_name == "high_conviction_risk_off" and is_active:
                strategy_return = -benchmark_return

            period_rows.append(
                {
                    "strategy_name": strategy_name,
                    "signal_date": row["signal_date"],
                    "entry_date": row.get("entry_date"),
                    "exit_date": row.get(f"exit_date_{hold_days}d"),
                    "hold_days": int(hold_days),
                    "sentiment_state": row.get("sentiment_state"),
                    "fear_greed_score": _safe_float(row.get("fear_greed_score")),
                    "panic_score": _safe_float(row.get("panic_score")),
                    "is_active": bool(is_active),
                    "strategy_return": float(strategy_return),
                    "spy_return": float(benchmark_return),
                    "excess_return": float(strategy_return - benchmark_return),
                }
            )
            pointer += hold_days

    periods = pd.DataFrame(period_rows)
    if periods.empty:
        return periods, pd.DataFrame()

    periods = periods.sort_values(["strategy_name", "signal_date"]).reset_index(drop=True)
    summary_rows: list[dict[str, Any]] = []
    for strategy_name, group in periods.groupby("strategy_name"):
        strategy_equity = (1.0 + group["strategy_return"]).cumprod()
        spy_equity = (1.0 + group["spy_return"]).cumprod()
        drawdown = strategy_equity / strategy_equity.cummax() - 1.0
        summary_rows.append(
            {
                "strategy_name": str(strategy_name),
                "hold_days": int(hold_days),
                "periods": int(len(group)),
                "active_periods": int(group["is_active"].sum()),
                "total_return": float(strategy_equity.iloc[-1] - 1.0),
                "spy_total_return": float(spy_equity.iloc[-1] - 1.0),
                "avg_return": float(group["strategy_return"].mean()),
                "avg_excess_return": float(group["excess_return"].mean()),
                "hit_rate_vs_spy": float((group["excess_return"] > 0.0).mean()),
                "signal_to_noise": _signal_to_noise(group["strategy_return"]),
                "max_drawdown": float(drawdown.min()) if not drawdown.empty else None,
            }
        )
    return periods, pd.DataFrame(summary_rows).sort_values("strategy_name").reset_index(drop=True)


def build_spy_vix_fear_greed_research(
    *,
    project_root: str | Path | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    lookback_window: int = DEFAULT_LOOKBACK_WINDOW,
    min_periods: int = DEFAULT_MIN_PERIODS,
    bucket_count: int = DEFAULT_BUCKET_COUNT,
    hold_days: int = DEFAULT_HOLD_DAYS,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    resolved_output_dir = _resolve_output_path(root, output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    normalized_horizons = tuple(sorted({int(horizon) for horizon in horizons if int(horizon) > 0}))
    frame = build_spy_vix_fear_greed_frame(
        project_root=root,
        lookback_window=lookback_window,
        min_periods=min_periods,
        horizons=normalized_horizons,
    )
    frame.reset_index().to_csv(resolved_output_dir / "spy_vix_signal_panel.csv", index=False)

    state_summary = build_state_summary(frame, horizons=normalized_horizons)
    state_summary.to_csv(resolved_output_dir / "state_forward_return_summary.csv", index=False)

    bucket_summary, bucket_edge_summary = build_bucket_summary(
        frame,
        horizons=normalized_horizons,
        bucket_count=bucket_count,
    )
    bucket_summary.to_csv(resolved_output_dir / "fear_greed_bucket_summary.csv", index=False)
    bucket_edge_summary.to_csv(resolved_output_dir / "fear_greed_bucket_edge_summary.csv", index=False)

    feature_footprint = build_feature_footprint(frame, horizons=normalized_horizons)
    feature_footprint.to_csv(resolved_output_dir / "feature_footprint.csv", index=False)

    inaccuracy_summary = build_state_inaccuracy_summary(frame, horizons=normalized_horizons)
    inaccuracy_summary.to_csv(resolved_output_dir / "state_inaccuracy_summary.csv", index=False)

    strategy_periods, strategy_summary = build_strategy_periods(frame, hold_days=hold_days)
    strategy_periods.to_csv(resolved_output_dir / "strategy_periods.csv", index=False)
    strategy_summary.to_csv(resolved_output_dir / "strategy_summary.csv", index=False)

    valid_states = frame["sentiment_state"].dropna()
    state_counts = valid_states.value_counts().sort_index().to_dict()
    best_state_rows: list[dict[str, Any]] = []
    for horizon in normalized_horizons:
        horizon_state_summary = state_summary.loc[
            (state_summary["horizon_days"] == int(horizon)) & (state_summary["state"] != "ALL")
        ].copy()
        if horizon_state_summary.empty:
            continue
        ranked = horizon_state_summary.dropna(subset=["signal_to_noise"]).sort_values("signal_to_noise", ascending=False)
        if ranked.empty:
            continue
        best_row = ranked.iloc[0]
        best_state_rows.append(
            {
                "horizon_days": int(horizon),
                "state": str(best_row["state"]),
                "mean_return": _safe_float(best_row["mean_return"]),
                "signal_to_noise": _safe_float(best_row["signal_to_noise"]),
            }
        )

    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "output_dir": str(resolved_output_dir),
        "rows": int(len(frame)),
        "first_signal_date": frame.index.min().strftime("%Y-%m-%d") if not frame.empty else None,
        "last_signal_date": frame.index.max().strftime("%Y-%m-%d") if not frame.empty else None,
        "lookback_window": int(lookback_window),
        "min_periods": int(min_periods),
        "bucket_count": int(bucket_count),
        "hold_days": int(hold_days),
        "horizons": list(normalized_horizons),
        "implementation_note": (
            "Forward returns enter on the next bar after the signal date, so the study avoids same-close lookahead when SPY and VIX are used to build the signal."
        ),
        "state_counts": {key: int(value) for key, value in state_counts.items()},
        "best_state_by_signal_to_noise": best_state_rows,
        "strategy_summary": strategy_summary.to_dict(orient="records"),
    }
    (resolved_output_dir / "spy_vix_fear_greed_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    args = parse_args()
    summary = build_spy_vix_fear_greed_research(
        project_root=args.project_root,
        output_dir=args.output_dir,
        lookback_window=args.lookback_window,
        min_periods=args.min_periods,
        bucket_count=args.bucket_count,
        hold_days=args.hold_days,
        horizons=tuple(args.horizons),
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()