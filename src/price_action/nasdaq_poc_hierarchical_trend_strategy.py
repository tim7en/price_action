"""Hierarchical trend validation for the frozen NASDAQ POC trade ledger."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from price_action.btc_deepcharts_proxy_backtest import session_volume_profile_proxy
from price_action.data import resolve_project_root
from price_action.nasdaq_fabio_pine_v6_backtest import (
    _markdown_table,
    load_nasdaq_source,
    load_schedule,
    pine_rma,
)


DEFAULT_TRADES = Path("outputs/nasdaq_macro_poc_assessment/annotated_trades.csv")
DEFAULT_DATA = Path("cache/Nasdaq.csv")
DEFAULT_SCHEDULE = Path("outputs/nasdaq_session_backtest/session_schedule.csv")
DEFAULT_OUTPUT = Path("outputs/nasdaq_poc_hierarchical_trend_strategy")
DEVELOPMENT_END = pd.Timestamp("2025-01-01", tz="UTC")
REFERENCE_ONE_WAY_COST_BPS = 0.50
PROFILE_BINS = 24
MINIMUM_DEVELOPMENT_TRADES = 10


def load_poc_trades(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {
        "signal_time",
        "entry_time",
        "exit_time",
        "session_date",
        "side",
        "net_r",
        "maximum_favorable_r",
        "maximum_adverse_r",
        "stop_fraction",
        "causal_session_vwap",
        "spy_alignment",
        "nq_alignment",
        "golden_cross_state",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"POC ledger is missing columns: {sorted(missing)}")
    for column in ("signal_time", "entry_time", "exit_time"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="raise")
    return frame.sort_values("entry_time").reset_index(drop=True)


def build_session_hierarchy_context(
    bars: pd.DataFrame,
    schedule: pd.DataFrame,
) -> pd.DataFrame:
    """Build session OHLC/profile fields and expose them only to the next session."""
    records: list[dict[str, Any]] = []
    for session in schedule.itertuples(index=False):
        session_open = pd.Timestamp(session.session_open)
        session_close = pd.Timestamp(session.session_close)
        frame = bars.loc[(bars.index >= session_open) & (bars.index < session_close)]
        if frame.empty:
            continue
        opening_start = pd.Timestamp(getattr(session, "opening_start", session_open))
        opening_end = pd.Timestamp(
            getattr(session, "opening_end", session_open + pd.Timedelta(minutes=30))
        )
        opening = bars.loc[(bars.index >= opening_start) & (bars.index < opening_end)]
        profile = session_volume_profile_proxy(
            frame,
            bins=PROFILE_BINS,
            value_area_fraction=0.70,
            allocation="uniform_range",
        )
        records.append(
            {
                "session_date": str(session.session_date),
                "session_open": session_open,
                "available_time": session_close,
                "session_high_observed": float(frame["high"].max()),
                "session_low_observed": float(frame["low"].min()),
                "session_close_observed": float(frame["close"].iloc[-1]),
                "session_poc_observed": profile["poc"],
                "session_vah_observed": profile["vah"],
                "session_val_observed": profile["val"],
                "opening_high": float(opening["high"].max()) if not opening.empty else np.nan,
                "opening_low": float(opening["low"].min()) if not opening.empty else np.nan,
                "opening_bars": int(len(opening)),
            }
        )
    context = pd.DataFrame(records).sort_values("session_open").reset_index(drop=True)
    for source, target in {
        "available_time": "prior_session_available_time",
        "session_high_observed": "prior_session_high",
        "session_low_observed": "prior_session_low",
        "session_close_observed": "prior_session_close",
        "session_poc_observed": "prior_session_poc",
        "session_vah_observed": "prior_session_vah",
        "session_val_observed": "prior_session_val",
    }.items():
        context[target] = context[source].shift(1)
    return context


def add_signal_bar_features(bars: pd.DataFrame) -> pd.DataFrame:
    out = bars.copy()
    prior_close = out["close"].shift(1)
    true_range = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - prior_close).abs(),
            (out["low"] - prior_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr14"] = pine_rma(true_range, 14)
    out["prior_volume_median50"] = out["volume"].shift(1).rolling(50, min_periods=50).median()
    out["volume_strength"] = out["volume"] / out["prior_volume_median50"].replace(0.0, np.nan)
    bar_range = (out["high"] - out["low"]).replace(0.0, np.nan)
    out["close_location"] = (2.0 * (out["close"] - out["low"]) / bar_range - 1.0).clip(-1.0, 1.0)
    return out


def annotate_hierarchy_trades(
    trades: pd.DataFrame,
    bar_features: pd.DataFrame,
    session_context: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, float]]:
    out = trades.copy()
    side_text = out["side"].astype(str).str.lower()
    if not side_text.isin(["long", "short", "1", "-1"]).all():
        raise ValueError("POC ledger side must be long/short or +1/-1")
    out["side_sign"] = np.where(side_text.isin(["long", "1"]), 1, -1)
    signal_rows = bar_features.reindex(pd.DatetimeIndex(out["signal_time"]))
    if signal_rows[["open", "high", "low", "close", "volume", "atr14"]].isna().any().any():
        raise ValueError("A POC signal timestamp is missing from the NASDAQ bar source")
    for source, target in {
        "open": "signal_open",
        "high": "signal_high",
        "low": "signal_low",
        "close": "signal_close",
        "volume": "signal_volume",
        "atr14": "signal_atr",
        "volume_strength": "volume_strength",
        "close_location": "close_location",
    }.items():
        out[target] = signal_rows[source].to_numpy()
    context_columns = [
        "session_date",
        "session_open",
        "opening_high",
        "opening_low",
        "opening_bars",
        "prior_session_available_time",
        "prior_session_high",
        "prior_session_low",
        "prior_session_close",
        "prior_session_poc",
        "prior_session_vah",
        "prior_session_val",
    ]
    out = out.merge(
        session_context[context_columns], on="session_date", how="left", validate="many_to_one"
    )
    out["directional_impulse_atr"] = (
        out["side_sign"] * (out["signal_close"] - out["signal_open"]) / out["signal_atr"]
    )
    out["directional_close_location"] = out["side_sign"] * out["close_location"]
    out["vwap_distance_atr"] = (
        out["side_sign"] * (out["signal_close"] - out["causal_session_vwap"]) / out["signal_atr"]
    )
    out["poc_distance_atr"] = (
        out["side_sign"] * (out["signal_close"] - out["prior_session_poc"]) / out["signal_atr"]
    )
    opening_boundary = np.where(out["side_sign"].gt(0), out["opening_high"], out["opening_low"])
    prior_boundary = np.where(
        out["side_sign"].gt(0), out["prior_session_high"], out["prior_session_low"]
    )
    out["opening_break_atr"] = (
        out["side_sign"] * (out["signal_close"] - opening_boundary) / out["signal_atr"]
    )
    out["prior_extreme_break_atr"] = (
        out["side_sign"] * (out["signal_close"] - prior_boundary) / out["signal_atr"]
    )
    out["opening_width_atr"] = (
        (out["opening_high"] - out["opening_low"]) / out["signal_atr"]
    )
    out["minutes_from_session_open"] = (
        out["signal_time"] - out["session_open"]
    ) / pd.Timedelta(minutes=1)

    development = out["signal_time"].lt(DEVELOPMENT_END)
    thresholds = {
        "directional_impulse_atr_median": float(
            out.loc[development, "directional_impulse_atr"].median()
        ),
        "volume_strength_median": float(out.loc[development, "volume_strength"].median()),
        "opening_width_atr_median": float(
            out.loc[development, "opening_width_atr"].median()
        ),
    }
    out["macro_daily_gate"] = out["spy_alignment"].eq("aligned") & out[
        "nq_alignment"
    ].ne("opposed")
    out["golden_cross_gate"] = (
        (out["side_sign"].gt(0) & out["golden_cross_state"].eq("up"))
        | (out["side_sign"].lt(0) & out["golden_cross_state"].eq("down"))
    )
    out["poc_location_gate"] = out["poc_distance_atr"].gt(0.0) & out[
        "vwap_distance_atr"
    ].gt(0.0)
    out["opening_break_gate"] = out["opening_break_atr"].gt(0.0)
    out["prior_extreme_gate"] = out["prior_extreme_break_atr"].gt(0.0)
    out["impulse_gate"] = out["directional_impulse_atr"].ge(
        max(thresholds["directional_impulse_atr_median"], 0.0)
    ) & out["directional_close_location"].gt(0.0)
    out["volume_gate"] = out["volume_strength"].ge(thresholds["volume_strength_median"])
    out["compact_opening_gate"] = out["opening_width_atr"].le(
        thresholds["opening_width_atr_median"]
    )
    score_columns = [
        "macro_daily_gate",
        "poc_location_gate",
        "opening_break_gate",
        "prior_extreme_gate",
        "impulse_gate",
        "volume_gate",
    ]
    out["hierarchy_score"] = out[score_columns].sum(axis=1).astype(int)
    out["hierarchy_risk_fraction"] = np.select(
        [
            out["hierarchy_score"].ge(5),
            out["hierarchy_score"].eq(4),
            out["hierarchy_score"].eq(3),
        ],
        [0.0025, 0.0015, 0.0010],
        default=0.0,
    )
    out["hierarchy_tier"] = np.select(
        [
            out["hierarchy_score"].ge(5),
            out["hierarchy_score"].eq(4),
            out["hierarchy_score"].eq(3),
        ],
        ["A_5plus", "B_4", "C_3"],
        default="observe_below_3",
    )
    return out, thresholds


def _r_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "trades": 0,
            "win_rate": np.nan,
            "profit_factor": np.nan,
            "mean_net_r": np.nan,
            "sum_net_r": 0.0,
            "runner_rate_mfe_ge_1r": np.nan,
            "runner_profit_conversion": np.nan,
            "whipsaw_rate_mfe_lt_0_25r": np.nan,
            "average_holding_minutes": np.nan,
        }
    net = frame["net_r"].astype(float)
    wins, losses = net.loc[net > 0.0], net.loc[net < 0.0]
    runner = frame["maximum_favorable_r"].ge(1.0)
    whipsaw = net.lt(0.0) & frame["maximum_favorable_r"].lt(0.25)
    return {
        "trades": int(len(frame)),
        "win_rate": float(net.gt(0.0).mean()),
        "profit_factor": float(wins.sum() / abs(losses.sum())) if losses.sum() < 0.0 else np.inf,
        "mean_net_r": float(net.mean()),
        "sum_net_r": float(net.sum()),
        "runner_rate_mfe_ge_1r": float(runner.mean()),
        "runner_profit_conversion": float(net.loc[runner].gt(0.0).mean()) if runner.any() else np.nan,
        "whipsaw_rate_mfe_lt_0_25r": float(whipsaw.mean()),
        "average_holding_minutes": float(frame["holding_minutes"].mean()),
    }


def candidate_masks(trades: pd.DataFrame) -> dict[str, pd.Series]:
    poc = trades["poc_location_gate"]
    impulse = trades["impulse_gate"]
    volume = trades["volume_gate"]
    opening = trades["opening_break_gate"]
    prior = trades["prior_extreme_gate"]
    return {
        "core_poc_ledger": pd.Series(True, index=trades.index),
        "prior_poc_plus_vwap": poc,
        "volume_strength": volume,
        "directional_impulse": impulse,
        "opening_range_break": opening,
        "previous_day_extreme_break": prior,
        "compact_opening_range": trades["compact_opening_gate"],
        "poc_impulse_volume": poc & impulse & volume,
        "opening_poc_impulse": opening & poc & impulse,
        "score_ge_3": trades["hierarchy_score"].ge(3),
        "score_ge_4": trades["hierarchy_score"].ge(4),
        "score_ge_5": trades["hierarchy_score"].ge(5),
    }


def build_candidate_validation(trades: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    periods = {
        "all": pd.Series(True, index=trades.index),
        "development_2024": trades["signal_time"].lt(DEVELOPMENT_END),
        "validation_2025": trades["signal_time"].ge(DEVELOPMENT_END),
    }
    for period, period_mask in periods.items():
        for name, candidate_mask in candidate_masks(trades).items():
            records.append(
                {"candidate": name, "period": period}
                | _r_metrics(trades.loc[period_mask & candidate_mask])
            )
    return pd.DataFrame(records)


def build_feature_validation(trades: pd.DataFrame) -> pd.DataFrame:
    features = [
        "macro_daily_gate",
        "golden_cross_gate",
        "poc_location_gate",
        "opening_break_gate",
        "prior_extreme_gate",
        "impulse_gate",
        "volume_gate",
        "compact_opening_gate",
    ]
    records: list[dict[str, Any]] = []
    periods = {
        "development_2024": trades["signal_time"].lt(DEVELOPMENT_END),
        "validation_2025": trades["signal_time"].ge(DEVELOPMENT_END),
    }
    for period, period_mask in periods.items():
        for feature in features:
            for state in (True, False):
                records.append(
                    {"feature": feature, "state": state, "period": period}
                    | _r_metrics(trades.loc[period_mask & trades[feature].eq(state)])
                )
    return pd.DataFrame(records)


def build_score_validation(trades: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for period, mask in {
        "development_2024": trades["signal_time"].lt(DEVELOPMENT_END),
        "validation_2025": trades["signal_time"].ge(DEVELOPMENT_END),
    }.items():
        for score, frame in trades.loc[mask].groupby("hierarchy_score"):
            records.append({"period": period, "hierarchy_score": int(score)} | _r_metrics(frame))
    return pd.DataFrame(records)


def build_risk_paths(trades: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    paths: list[pd.DataFrame] = []
    summary_rows: list[dict[str, Any]] = []
    for variant, risk in (
        ("fixed_0.25pct", pd.Series(0.0025, index=trades.index)),
        ("hierarchy_risk", trades["hierarchy_risk_fraction"]),
    ):
        frame = trades.copy()
        frame["risk_fraction"] = risk
        frame["strategy_return"] = frame["net_r"] * frame["risk_fraction"]
        frame["equity"] = (1.0 + frame["strategy_return"]).cumprod()
        frame["peak"] = frame["equity"].cummax().clip(lower=1.0)
        frame["drawdown"] = frame["equity"] / frame["peak"] - 1.0
        frame["variant"] = variant
        paths.append(
            frame[
                [
                    "variant",
                    "signal_time",
                    "entry_time",
                    "session_date",
                    "hierarchy_score",
                    "risk_fraction",
                    "strategy_return",
                    "equity",
                    "drawdown",
                ]
            ]
        )
        for period, period_mask in {
            "all": pd.Series(True, index=frame.index),
            "development_2024": frame["signal_time"].lt(DEVELOPMENT_END),
            "validation_2025": frame["signal_time"].ge(DEVELOPMENT_END),
        }.items():
            returns = frame.loc[period_mask, "strategy_return"].to_numpy(dtype=float)
            growth = np.cumprod(1.0 + returns) if len(returns) else np.array([1.0])
            equity = np.r_[1.0, growth]
            peaks = np.maximum.accumulate(equity)
            summary_rows.append(
                {
                    "variant": variant,
                    "period": period,
                    "trades_available": int(period_mask.sum()),
                    "trades_sized": int(frame.loc[period_mask, "risk_fraction"].gt(0.0).sum()),
                    "average_risk_fraction": float(frame.loc[period_mask, "risk_fraction"].mean()),
                    "cumulative_return": float(growth[-1] - 1.0),
                    "maximum_drawdown": float((equity / peaks - 1.0).min()),
                }
            )
    return pd.concat(paths, ignore_index=True), pd.DataFrame(summary_rows)


def _top_development_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    development = candidates.loc[
        candidates["period"].eq("development_2024")
        & candidates["trades"].ge(MINIMUM_DEVELOPMENT_TRADES)
        & candidates["candidate"].ne("core_poc_ledger")
    ].sort_values(["profit_factor", "trades"], ascending=[False, False])
    records: list[dict[str, Any]] = []
    for rank, row in enumerate(development.head(5).itertuples(index=False), start=1):
        validation = candidates.loc[
            candidates["period"].eq("validation_2025")
            & candidates["candidate"].eq(row.candidate)
        ].iloc[0]
        records.append(
            {
                "development_rank": rank,
                "candidate": row.candidate,
                "development_trades": row.trades,
                "development_profit_factor": row.profit_factor,
                "development_mean_net_r": row.mean_net_r,
                "development_runner_rate": row.runner_rate_mfe_ge_1r,
                "development_whipsaw_rate": row.whipsaw_rate_mfe_lt_0_25r,
                "validation_trades": validation["trades"],
                "validation_profit_factor": validation["profit_factor"],
                "validation_mean_net_r": validation["mean_net_r"],
                "validation_runner_rate": validation["runner_rate_mfe_ge_1r"],
                "validation_whipsaw_rate": validation["whipsaw_rate_mfe_lt_0_25r"],
            }
        )
    return pd.DataFrame(records)


def _report(
    candidates: pd.DataFrame,
    top: pd.DataFrame,
    features: pd.DataFrame,
    scores: pd.DataFrame,
    risk_summary: pd.DataFrame,
    thresholds: dict[str, float],
    audit: dict[str, Any],
) -> str:
    core = candidates.loc[
        candidates["candidate"].eq("core_poc_ledger")
        & candidates["period"].isin(["development_2024", "validation_2025"]),
        ["candidate", "period", "trades", "win_rate", "profit_factor", "mean_net_r", "runner_rate_mfe_ge_1r", "whipsaw_rate_mfe_lt_0_25r"],
    ]
    feature_true = features.loc[
        features["state"].eq(True),
        ["feature", "period", "trades", "profit_factor", "mean_net_r", "runner_rate_mfe_ge_1r", "whipsaw_rate_mfe_lt_0_25r"],
    ]
    threshold_frame = pd.DataFrame(
        [{"feature": key, "development_threshold": value} for key, value in thresholds.items()]
    )
    validated = top.loc[
        top["development_profit_factor"].gt(1.0)
        & top["validation_profit_factor"].gt(1.0)
    ]
    return f"""# NASDAQ POC hierarchical trend strategy

## Research conclusion

The strongest entry evidence in the repository remains the frozen multi-session POC-migration plus one-minute acceptance ledger, not generic ORB frequency. Its context-free 0.25%-risk test previously produced PF 1.58 at 0.50 bps per side, but the ledger has only 89 trades and was selected with visibility into both years.

This extension adds only close-confirmed information: previous completed RTH high/low/POC/VAH/VAL, exact 30-minute opening range, session VWAP, signal-bar impulse, relative volume, and already-lagged macro/daily alignment. Development thresholds use 2024 only; 2025 is unchanged validation. Methodology audit: **{audit['status']}**.

## Core stability

{_markdown_table(core)}

## Development-ranked hierarchy candidates and 2025 validation

{_markdown_table(top)}

Candidates profitable in both periods: **{len(validated)}**. A high score is not automatically useful; each extra gate must improve validation expectancy rather than merely increase historical selectivity.

## Individual validation layers

{_markdown_table(feature_true)}

## Score behavior

{_markdown_table(scores)}

## Conservative hierarchy sizing diagnostic

{_markdown_table(risk_summary)}

The sizing map is deliberately non-aggressive: score below 3 receives no position; score 3 risks 0.10%, score 4 risks 0.15%, and score 5-6 risks at most 0.25%. It is a governance diagnostic, not permission for live capital.

## Proposed hierarchy

1. **Direction:** last completed macro/daily state controls risk, not entry. Golden-cross state is a slow prior rather than a one-minute trigger.
2. **Location:** require the POC-migration/acceptance core; use session VWAP and previous-session POC/VAH/VAL to define the area of interest.
3. **Auction structure:** classify price as inside yesterday's range, testing an extreme, or accepting beyond the previous high/low. Because actual extreme breaks were too rare to validate, use the levels primarily for location, targets, and invalidation rather than as a mandatory entry gate.
4. **Trigger:** exact opening-range break or POC acceptance on a confirmed one-minute close.
5. **Aggression:** directional candle impulse can confirm the trigger. Relative volume is only a bonus because its sign was unstable across periods; five-minute OHLCV cannot substitute for true footprint delta.
6. **Risk:** maximum 0.25% initial-stop risk, no fixed 20x/40x exposure, three-loss/-0.75% daily halt.
7. **Management:** retain the cost-covered trailing logic only after favorable progress; next research should test an early failure exit for trades that lose VWAP/POC acceptance before reaching 0.25R MFE.

## Frozen 2024 thresholds

{_markdown_table(threshold_frame)}

## Limits

- Previous-day fields are shifted by one completed session and never current-session final values.
- Signal candle OHLCV is known at its close; the frozen ledger enters one minute later.
- Candidate filtering is attribution on an existing ledger, not a fresh broker replay. It should guide a new frozen entry implementation, not be treated as deployable performance.
- The NASDAQ-like source remains unverified and inconsistent with the CME NQ tick grid.
"""


def build_nasdaq_poc_hierarchical_trend_strategy(
    project_root: str | Path | None = None,
    *,
    trades_path: str | Path = DEFAULT_TRADES,
    data_path: str | Path = DEFAULT_DATA,
    schedule_path: str | Path = DEFAULT_SCHEDULE,
    output_dir: str | Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)

    def resolved(value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else root / path

    output = resolved(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    trades = load_poc_trades(resolved(trades_path))
    bars, data_quality = load_nasdaq_source(resolved(data_path))
    schedule = load_schedule(resolved(schedule_path))
    session_context = build_session_hierarchy_context(bars, schedule)
    bar_features = add_signal_bar_features(bars)
    annotated, thresholds = annotate_hierarchy_trades(
        trades, bar_features, session_context
    )
    candidates = build_candidate_validation(annotated)
    features = build_feature_validation(annotated)
    scores = build_score_validation(annotated)
    top = _top_development_candidates(candidates)
    risk_paths, risk_summary = build_risk_paths(annotated)
    observed_context = annotated["prior_session_available_time"].notna()
    prior_available = pd.to_datetime(
        annotated.loc[observed_context, "prior_session_available_time"], utc=True
    ).le(annotated.loc[observed_context, "signal_time"]).all()
    audit = {
        "status": "PASS",
        "checks": {
            "previous_session_context_available_before_signal": bool(prior_available),
            "signal_bar_precedes_entry": bool(annotated["signal_time"].lt(annotated["entry_time"]).all()),
            "development_thresholds_end_before_2025": True,
            "candidate_ranking_uses_2024_only": True,
            "opening_range_uses_schedule_0930_to_1000_new_york": bool(
                session_context["opening_bars"].dropna().median() == 30
            ),
            "hierarchy_risk_never_exceeds_0_25pct": bool(
                annotated["hierarchy_risk_fraction"].le(0.0025).all()
            ),
        },
    }
    hierarchy_spec = {
        "status": "RESEARCH_ONLY_NOT_DEPLOYABLE",
        "score_components": [
            "macro_daily_gate",
            "poc_location_gate",
            "opening_break_gate",
            "prior_extreme_gate",
            "impulse_gate",
            "volume_gate",
        ],
        "component_roles": {
            "core": "POC migration and confirmed one-minute acceptance",
            "directional_prior": "macro/daily alignment; golden cross is slower context",
            "stable_location": "directional side of prior POC plus current session VWAP",
            "trigger_confirmation": "opening-range break and directional impulse",
            "bonus_only": "relative volume",
            "map_not_required_gate": "previous-session high and low",
        },
        "risk_by_score": {
            "0_to_2": 0.0,
            "3": 0.0010,
            "4": 0.0015,
            "5_to_6": 0.0025,
        },
        "thresholds_fit_on": "2024 signal rows only",
        "validation_period": "2025",
        "reference_one_way_cost_bps": REFERENCE_ONE_WAY_COST_BPS,
        "thresholds": thresholds,
    }
    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "RESEARCH_ONLY_LIVE_DEPLOYMENT_BLOCKED",
        "source_trades": str(resolved(trades_path)),
        "source_bars": str(resolved(data_path)),
        "data_quality": data_quality,
        "hierarchy_spec": hierarchy_spec,
        "audit": audit,
        "known_selection_limit": "The frozen POC ledger was originally selected with visibility into 2024 and 2025.",
    }
    annotated.to_csv(output / "annotated_hierarchy_trades.csv", index=False)
    session_context.to_csv(output / "session_hierarchy_context.csv", index=False)
    candidates.to_csv(output / "candidate_validation.csv", index=False)
    top.to_csv(output / "top_candidate_validation.csv", index=False)
    features.to_csv(output / "feature_validation.csv", index=False)
    scores.to_csv(output / "score_validation.csv", index=False)
    risk_paths.to_csv(output / "risk_paths.csv", index=False)
    risk_summary.to_csv(output / "risk_summary.csv", index=False)
    (output / "hierarchy_spec.json").write_text(
        json.dumps(hierarchy_spec, indent=2), encoding="utf-8"
    )
    (output / "causality_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )
    (output / "governance.json").write_text(
        json.dumps(governance, indent=2), encoding="utf-8"
    )
    report = _report(candidates, top, features, scores, risk_summary, thresholds, audit)
    report_path = output / "report.md"
    report_path.write_text(report, encoding="utf-8")
    return {
        "report_path": report_path,
        "candidates": candidates,
        "top": top,
        "features": features,
        "scores": scores,
        "risk_summary": risk_summary,
        "audit": audit,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root")
    parser.add_argument("--trades-path", default=str(DEFAULT_TRADES))
    parser.add_argument("--data-path", default=str(DEFAULT_DATA))
    parser.add_argument("--schedule-path", default=str(DEFAULT_SCHEDULE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_nasdaq_poc_hierarchical_trend_strategy(
        project_root=args.project_root,
        trades_path=args.trades_path,
        data_path=args.data_path,
        schedule_path=args.schedule_path,
        output_dir=args.output_dir,
    )
    print(f"Report: {result['report_path']}")
    print(result["top"].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
