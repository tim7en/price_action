"""Assess the frozen Nasdaq POC candidate with causal risk overlays and account sizing.

This module deliberately does not search for a new entry rule.  It annotates the
previously frozen one-minute POC trade ledger with information that was available
before each session, then applies transparent risk governors and execution costs.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from price_action.data import resolve_project_root


DEFAULT_TRADES = Path("outputs/nasdaq_poc_asymmetric_runner/trades/stable_5m_base.csv")
DEFAULT_MACRO = Path("outputs/regime_analysis/regime_timeline.csv")
DEFAULT_DAILY = Path("outputs/spy_drawdown_regime_research/drawdown_daily_panel.csv")
DEFAULT_NASDAQ = Path("cache/Nasdaq.csv")
DEFAULT_OUTPUT = Path("outputs/nasdaq_macro_poc_assessment")


@dataclass(frozen=True)
class AssessmentConfig:
    base_risk_fraction: float = 0.0025
    maximum_risk_fraction: float = 0.0075
    profit_reinvestment_fraction: float = 0.50
    daily_loss_limit_fraction: float = 0.0075
    daily_loss_count_limit: int = 3
    maximum_leverage: float = 20.0
    reference_one_way_cost_bps: float = 0.50
    cost_scenarios_bps: tuple[float, ...] = (0.25, 0.50, 1.00, 1.50, 2.00)
    bootstrap_samples: int = 5_000
    bootstrap_seed: int = 17
    mnq_multiplier: float = 2.0
    mnq_base_round_turn_fees: float = 1.50
    mnq_base_round_turn_slippage_points: float = 0.50
    mnq_stress_round_turn_fees: float = 2.50
    mnq_stress_round_turn_slippage_points: float = 1.00
    account_sizes: tuple[float, ...] = (25_000.0, 100_000.0)


VARIANTS = (
    "fixed_0.25_no_overlays",
    "macro_only",
    "golden_daily_only",
    "shock_recovery_only",
    "intraday_2m_5m_only",
    "combined_governor",
    "combined_profit_financed",
    "full_stack_governor",
    "full_stack_profit_financed",
)


def _bool_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def _macro_multiplier(value: Any) -> float:
    text = str(value).lower()
    if any(token in text for token in ("risk-off", "stress", "contraction")):
        return 0.25
    if any(token in text for token in ("inflationary", "late-cycle", "stagflation")):
        return 0.50
    if "expansion" in text:
        return 1.00
    return 0.75


def build_daily_market_context(frame: pd.DataFrame) -> pd.DataFrame:
    """Build a hysteretic golden-cross state and causal shock/recovery labels."""
    out = frame.copy()
    out["signal_date"] = pd.to_datetime(out["signal_date"], errors="raise").dt.normalize()
    out = out.sort_values("signal_date").drop_duplicates("signal_date", keep="last")
    for column in (
        "spy_close",
        "spot_vix_change_5d",
        "high_yield_spread_change_5d",
        "spy_trend_5d",
    ):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out["risk_off_gate"] = _bool_series(out["risk_off_gate"])
    out["extreme_risk_off"] = _bool_series(out["extreme_risk_off"])

    out["spy_sma50"] = out["spy_close"].rolling(50, min_periods=50).mean()
    out["spy_sma200"] = out["spy_close"].rolling(200, min_periods=200).mean()
    spread = out["spy_sma50"].div(out["spy_sma200"]).sub(1.0)
    states: list[str] = []
    state = "neutral"
    for close, sma200, gap in zip(out["spy_close"], out["spy_sma200"], spread, strict=True):
        if pd.notna(sma200) and gap > 0.02 and close > sma200:
            state = "up"
        elif pd.notna(sma200) and gap < -0.02 and close < sma200:
            state = "down"
        states.append(state)
    out["golden_cross_state"] = states

    falling = out["extreme_risk_off"] | (
        out["risk_off_gate"]
        & (
            out["spot_vix_change_5d"].gt(0.0)
            | out["high_yield_spread_change_5d"].gt(0.0)
        )
    )
    combined = out["combined_regime"].fillna("").astype(str).str.lower()
    labels: list[str] = []
    multipliers: list[float] = []
    last_shock = -10_000
    for position in range(len(out)):
        if bool(falling.iloc[position]):
            last_shock = position
            label, multiplier = "falling_knife", 0.25
        else:
            recent_shock = position - last_shock <= 20
            recovery = (
                recent_shock
                and out["spot_vix_change_5d"].iloc[position] <= 0.0
                and out["high_yield_spread_change_5d"].iloc[position] <= 0.0
                and out["spy_trend_5d"].iloc[position] > 0.0
            )
            fragile = bool(out["risk_off_gate"].iloc[position]) or any(
                token in combined.iloc[position] for token in ("weak", "stress", "fragile")
            )
            if recovery:
                label, multiplier = "recovery", 0.75
            elif fragile:
                label, multiplier = "fragile", 0.50
            else:
                label, multiplier = "normal", 1.00
        labels.append(label)
        multipliers.append(multiplier)
    out["shock_recovery_state"] = labels
    out["shock_multiplier"] = multipliers
    return out


def load_nasdaq_source(path: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load the one-minute OHLCV source without requiring a calendar package."""
    raw = pd.read_csv(path)
    required = {"time", "open", "high", "low", "close", "volume"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"Nasdaq CSV is missing columns: {sorted(missing)}")
    raw["time"] = pd.to_datetime(raw["time"], utc=True, errors="coerce")
    for column in ("open", "high", "low", "close", "volume"):
        raw[column] = pd.to_numeric(raw[column], errors="coerce")
    if raw[list(required)].isna().any().any():
        raise ValueError("Nasdaq CSV contains null or unparseable required values")
    raw = raw.sort_values("time")
    duplicate_count = int(raw["time"].duplicated().sum())
    if duplicate_count:
        raise ValueError(f"Nasdaq CSV contains {duplicate_count} duplicate timestamps")
    off_tick = ((raw["close"] * 4.0) - (raw["close"] * 4.0).round()).abs().gt(1e-8)
    bars = raw.set_index("time")
    return bars, {
        "input_rows": int(len(bars)),
        "first_input_bar_utc": bars.index.min().isoformat(),
        "last_input_bar_utc": bars.index.max().isoformat(),
        "duplicate_timestamps": duplicate_count,
        "close_not_on_nq_quarter_tick_rows": int(off_tick.sum()),
        "close_not_on_nq_quarter_tick_share": float(off_tick.mean()),
        "instrument_identity": "unverified; price grid is inconsistent with CME NQ",
        "volume_identity": "unverified; may be tick volume rather than exchange contract volume",
    }


def build_nasdaq_daily_context(bars: pd.DataFrame) -> pd.DataFrame:
    """Create a prior-session 10/30 Nasdaq bias from complete regular sessions."""
    local = bars.copy()
    local.index = local.index.tz_convert("America/New_York")
    minute = local.index.hour * 60 + local.index.minute
    local = local.loc[(minute >= 9 * 60 + 30) & (minute < 16 * 60)]
    session_dates = pd.to_datetime(local.index.date)
    daily = (
        local.assign(nq_session_date=session_dates)
        .groupby("nq_session_date", as_index=False)
        .agg(nq_close=("close", "last"))
        .sort_values("nq_session_date")
    )
    daily["nq_sma10"] = daily["nq_close"].rolling(10, min_periods=10).mean()
    daily["nq_sma30"] = daily["nq_close"].rolling(30, min_periods=30).mean()
    up = daily["nq_close"].gt(daily["nq_sma30"]) & daily["nq_sma10"].gt(daily["nq_sma30"])
    down = daily["nq_close"].lt(daily["nq_sma30"]) & daily["nq_sma10"].lt(daily["nq_sma30"])
    daily["nq_daily_state"] = np.select([up, down], ["up", "down"], default="neutral")
    return daily


def add_intraday_confirmation(trades: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """Attach untuned, fully completed two- and five-minute OHLCV proxies."""
    out = trades.copy()
    two_states: list[str] = []
    five_states: list[str] = []
    session_vwaps: list[float] = []
    index = bars.index
    for trade in out.itertuples(index=False):
        entry = pd.Timestamp(trade.entry_time)
        entry = entry.tz_localize("UTC") if entry.tzinfo is None else entry.tz_convert("UTC")
        right = int(index.searchsorted(entry, side="left"))
        two = bars.iloc[max(0, right - 2):right]
        five = bars.iloc[max(0, right - 5):right]
        expected_two = pd.date_range(entry - pd.Timedelta(minutes=2), periods=2, freq="min", tz="UTC")
        expected_five = pd.date_range(entry - pd.Timedelta(minutes=5), periods=5, freq="min", tz="UTC")
        complete_two = len(two) == 2 and two.index.equals(expected_two)
        complete_five = len(five) == 5 and five.index.equals(expected_five)
        if complete_two:
            delta = float(two["close"].iloc[-1] - two["open"].iloc[0])
            two_state = "up" if delta > 0.0 else "down" if delta < 0.0 else "neutral"
        else:
            two_state = "neutral"

        local_entry = entry.tz_convert("America/New_York")
        session_open = (
            local_entry.normalize() + pd.Timedelta(hours=9, minutes=30)
        ).tz_convert("UTC")
        left = int(index.searchsorted(session_open, side="left"))
        session = bars.iloc[left:right]
        if len(session) and float(session["volume"].sum()) > 0.0:
            typical = session[["high", "low", "close"]].mean(axis=1)
            session_vwap = float((typical * session["volume"]).sum() / session["volume"].sum())
        else:
            session_vwap = np.nan
        if complete_five and pd.notna(session_vwap):
            momentum = float(five["close"].iloc[-1] - five["open"].iloc[0])
            location = float(five["close"].iloc[-1] - session_vwap)
            if momentum > 0.0 and location > 0.0:
                five_state = "up"
            elif momentum < 0.0 and location < 0.0:
                five_state = "down"
            else:
                five_state = "neutral"
        else:
            five_state = "neutral"
        two_states.append(two_state)
        five_states.append(five_state)
        session_vwaps.append(session_vwap)
    out["two_minute_state"] = two_states
    out["five_minute_auction_state"] = five_states
    out["causal_session_vwap"] = session_vwaps
    out["two_minute_alignment"] = [
        _alignment(state, side)
        for state, side in zip(out["two_minute_state"], out["side"], strict=True)
    ]
    out["five_minute_alignment"] = [
        _alignment(state, side)
        for state, side in zip(out["five_minute_auction_state"], out["side"], strict=True)
    ]
    out["intraday_multiplier"] = [
        _trend_multiplier(two, five)
        for two, five in zip(
            out["two_minute_alignment"], out["five_minute_alignment"], strict=True
        )
    ]
    return out


def strict_prior_join(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    left_on: str,
    right_on: str,
) -> pd.DataFrame:
    """As-of join that explicitly excludes same-date observations."""
    ordered = left.copy()
    ordered["_original_order"] = np.arange(len(ordered))
    ordered[left_on] = pd.to_datetime(ordered[left_on], errors="raise").dt.tz_localize(None).dt.normalize()
    context = right.copy()
    context[right_on] = pd.to_datetime(context[right_on], errors="raise").dt.tz_localize(None).dt.normalize()
    joined = pd.merge_asof(
        ordered.sort_values(left_on),
        context.sort_values(right_on),
        left_on=left_on,
        right_on=right_on,
        direction="backward",
        allow_exact_matches=False,
    )
    return joined.sort_values("_original_order").drop(columns="_original_order").reset_index(drop=True)


def _alignment(state: Any, side: Any) -> str:
    state_text = str(state).lower()
    side_text = str(side).lower()
    desired = "up" if side_text == "long" else "down"
    opposed = "down" if desired == "up" else "up"
    if state_text == desired:
        return "aligned"
    if state_text == opposed:
        return "opposed"
    return "neutral"


def _trend_multiplier(spy_alignment: str, nq_alignment: str) -> float:
    states = {spy_alignment, nq_alignment}
    if spy_alignment == "aligned" and nq_alignment == "aligned":
        return 1.00
    if spy_alignment == "opposed" and nq_alignment == "opposed":
        return 0.25
    if "opposed" in states:
        return 0.50
    return 0.75


def annotate_trades(
    trades: pd.DataFrame,
    macro: pd.DataFrame,
    daily: pd.DataFrame,
    nq_daily: pd.DataFrame,
) -> pd.DataFrame:
    required = {
        "entry_time", "session_date", "side", "entry_price", "stop_fraction",
        "stop_distance_points", "effective_leverage", "gross_return",
    }
    missing = required - set(trades.columns)
    if missing:
        raise ValueError(f"Frozen trade ledger is missing columns: {sorted(missing)}")
    out = trades.copy()
    out["entry_time"] = pd.to_datetime(out["entry_time"], utc=True, errors="raise")
    out["session_timestamp"] = pd.to_datetime(out["session_date"], errors="raise")

    macro_context = macro.copy()
    macro_context["macro_date"] = pd.to_datetime(macro_context.pop("date"), errors="raise")
    macro_context["macro_multiplier"] = macro_context["statistical_regime"].map(_macro_multiplier)
    out = strict_prior_join(out, macro_context, left_on="session_timestamp", right_on="macro_date")

    daily_columns = [
        "signal_date", "golden_cross_state", "shock_recovery_state", "shock_multiplier",
        "combined_regime", "risk_off_gate", "extreme_risk_off", "spot_vix",
        "spot_vix_change_5d", "high_yield_spread_change_5d", "spy_trend_5d",
    ]
    out = strict_prior_join(out, daily[daily_columns], left_on="session_timestamp", right_on="signal_date")
    out = strict_prior_join(out, nq_daily, left_on="session_timestamp", right_on="nq_session_date")

    out["spy_alignment"] = [
        _alignment(state, side)
        for state, side in zip(out["golden_cross_state"], out["side"], strict=True)
    ]
    out["nq_alignment"] = [
        _alignment(state, side)
        for state, side in zip(out["nq_daily_state"], out["side"], strict=True)
    ]
    out["trend_multiplier"] = [
        _trend_multiplier(spy, nq)
        for spy, nq in zip(out["spy_alignment"], out["nq_alignment"], strict=True)
    ]
    for column, default in (
        ("macro_multiplier", 0.75),
        ("trend_multiplier", 0.75),
        ("shock_multiplier", 0.75),
    ):
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(default)
    out["combined_multiplier"] = out[[
        "macro_multiplier", "trend_multiplier", "shock_multiplier"
    ]].min(axis=1)
    if "intraday_multiplier" in out.columns:
        out["full_stack_multiplier"] = out[[
            "combined_multiplier", "intraday_multiplier"
        ]].min(axis=1)
    out["signed_price_return"] = (
        pd.to_numeric(out["gross_return"], errors="raise")
        / pd.to_numeric(out["effective_leverage"], errors="raise")
    )
    return out.sort_values(["entry_time"]).reset_index(drop=True)


def variant_multiplier(row: pd.Series, variant: str) -> float:
    if variant == "fixed_0.25_no_overlays":
        return 1.0
    if variant == "macro_only":
        return float(row["macro_multiplier"])
    if variant == "golden_daily_only":
        return float(row["trend_multiplier"])
    if variant == "shock_recovery_only":
        return float(row["shock_multiplier"])
    if variant == "intraday_2m_5m_only":
        return float(row["intraday_multiplier"])
    if variant in {"combined_governor", "combined_profit_financed"}:
        return float(row["combined_multiplier"])
    if variant in {"full_stack_governor", "full_stack_profit_financed"}:
        return float(row["full_stack_multiplier"])
    raise ValueError(f"Unknown assessment variant: {variant}")


def _planned_risk_dollars(
    equity: float,
    start_of_day_equity: float,
    multiplier: float,
    variant: str,
    config: AssessmentConfig,
) -> float:
    if variant.endswith("profit_financed"):
        base = config.base_risk_fraction * start_of_day_equity
        financed = config.profit_reinvestment_fraction * max(equity - start_of_day_equity, 0.0)
        before_governor = min(base + financed, config.maximum_risk_fraction * start_of_day_equity)
    else:
        before_governor = config.base_risk_fraction * equity
    return max(0.0, multiplier * before_governor)


def simulate_fractional_account(
    trades: pd.DataFrame,
    *,
    variant: str,
    one_way_cost_bps: float,
    config: AssessmentConfig,
    starting_equity: float = 1.0,
) -> pd.DataFrame:
    """Simulate fractional sizing with daily loss limits and a leverage cap."""
    rows: list[dict[str, Any]] = []
    equity = float(starting_equity)
    current_session: str | None = None
    start_of_day = equity
    daily_losses = 0
    halted = False
    for trade in trades.sort_values("entry_time").itertuples(index=False):
        row = pd.Series(trade._asdict())
        session = str(row["session_date"])
        if session != current_session:
            current_session = session
            start_of_day = equity
            daily_losses = 0
            halted = False
        equity_before = equity
        multiplier = variant_multiplier(row, variant)
        risk_dollars = _planned_risk_dollars(
            equity, start_of_day, multiplier, variant, config
        )
        skip_reason = "daily_halt" if halted else ""
        if halted or equity <= 0.0:
            net_return = gross_account_return = cost_fraction = effective_leverage = 0.0
            deployed_risk = 0.0
            executed = False
        else:
            planned_risk_fraction = risk_dollars / equity
            stop_fraction = float(row["stop_fraction"])
            effective_leverage = min(
                config.maximum_leverage,
                planned_risk_fraction / stop_fraction,
            )
            deployed_risk = effective_leverage * stop_fraction
            gross_account_return = float(row["signed_price_return"]) * effective_leverage
            cost_fraction = effective_leverage * 2.0 * one_way_cost_bps / 10_000.0
            net_return = gross_account_return - cost_fraction
            equity *= 1.0 + net_return
            executed = True
            if net_return < 0.0:
                daily_losses += 1
            session_return = equity / start_of_day - 1.0
            halted = (
                daily_losses >= config.daily_loss_count_limit
                or session_return <= -config.daily_loss_limit_fraction
            )
        rows.append({
            "variant": variant,
            "one_way_cost_bps": one_way_cost_bps,
            "session_date": session,
            "entry_time": row["entry_time"],
            "side": row["side"],
            "executed": executed,
            "skip_reason": skip_reason,
            "risk_multiplier": multiplier,
            "planned_risk_fraction": risk_dollars / equity_before if equity_before else 0.0,
            "deployed_risk_fraction": deployed_risk,
            "effective_leverage": effective_leverage,
            "gross_account_return": gross_account_return,
            "cost_fraction": cost_fraction,
            "net_return": net_return,
            "equity_before": equity_before,
            "equity_after": equity,
        })
    return pd.DataFrame(rows)


def summarize_account(path: pd.DataFrame) -> dict[str, Any]:
    if path.empty:
        return {
            "trades_seen": 0, "trades_executed": 0, "sessions": 0,
            "cumulative_net_return": np.nan, "annualized_return": np.nan,
            "maximum_drawdown": np.nan, "win_rate": np.nan, "profit_factor": np.nan,
            "average_net_return_bps": np.nan, "average_risk_fraction": np.nan,
            "maximum_risk_fraction": np.nan, "average_effective_leverage": np.nan,
            "daily_halt_skips": 0,
        }
    executed = path.loc[path["executed"]].copy()
    start = float(path["equity_before"].iloc[0])
    finish = float(path["equity_after"].iloc[-1])
    dates = pd.to_datetime(path["session_date"])
    days = max(1, int((dates.max() - dates.min()).days))
    equity = np.r_[start, path["equity_after"].to_numpy(dtype=float)]
    peaks = np.maximum.accumulate(equity)
    drawdown = equity / peaks - 1.0
    wins = executed.loc[executed["net_return"].gt(0.0), "net_return"]
    losses = executed.loc[executed["net_return"].lt(0.0), "net_return"]
    loss_sum = abs(float(losses.sum()))
    return {
        "trades_seen": int(len(path)),
        "trades_executed": int(len(executed)),
        "sessions": int(path["session_date"].nunique()),
        "cumulative_net_return": finish / start - 1.0,
        "annualized_return": (finish / start) ** (365.25 / days) - 1.0 if finish > 0 else -1.0,
        "maximum_drawdown": float(drawdown.min()),
        "win_rate": float(executed["net_return"].gt(0.0).mean()) if len(executed) else np.nan,
        "profit_factor": float(wins.sum()) / loss_sum if loss_sum > 0 else np.inf,
        "average_net_return_bps": float(executed["net_return"].mean() * 10_000.0) if len(executed) else np.nan,
        "average_risk_fraction": float(executed["deployed_risk_fraction"].mean()) if len(executed) else np.nan,
        "maximum_risk_fraction": float(executed["deployed_risk_fraction"].max()) if len(executed) else np.nan,
        "average_effective_leverage": float(executed["effective_leverage"].mean()) if len(executed) else np.nan,
        "daily_halt_skips": int(path["skip_reason"].eq("daily_halt").sum()),
    }


def estimate_break_even_cost_bps(
    trades: pd.DataFrame,
    variant: str,
    config: AssessmentConfig,
    *,
    upper_bound_bps: float = 5.0,
) -> float:
    """Find the approximate one-way cost where compounded return reaches zero."""
    low, high = 0.0, upper_bound_bps
    high_result = summarize_account(simulate_fractional_account(
        trades, variant=variant, one_way_cost_bps=high, config=config
    ))["cumulative_net_return"]
    if high_result > 0.0:
        return np.nan
    for _ in range(40):
        midpoint = (low + high) / 2.0
        result = summarize_account(simulate_fractional_account(
            trades, variant=variant, one_way_cost_bps=midpoint, config=config
        ))["cumulative_net_return"]
        if result > 0.0:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2.0


def context_performance(trades: pd.DataFrame) -> pd.DataFrame:
    """Show whether each proposed layer separates trade expectancy."""
    dimensions = (
        "shock_recovery_state", "spy_alignment", "nq_alignment",
        "two_minute_alignment", "five_minute_alignment",
    )
    records: list[dict[str, Any]] = []
    for dimension in dimensions:
        for value, group in trades.groupby(dimension, dropna=False):
            records.append({
                "dimension": dimension,
                "state": str(value),
                "trades": int(len(group)),
                "win_rate": float(group["net_r"].gt(0.0).mean()),
                "mean_gross_r": float(group["gross_r"].mean()),
                "mean_net_r": float(group["net_r"].mean()),
                "sum_net_r": float(group["net_r"].sum()),
            })
    return pd.DataFrame(records)


def _period_summaries(paths: Iterable[pd.DataFrame]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for path in paths:
        if path.empty:
            continue
        work = path.copy()
        work["year"] = pd.to_datetime(work["session_date"]).dt.year
        work["quarter"] = pd.to_datetime(work["session_date"]).dt.to_period("Q").astype(str)
        for label, groups in (("year", work.groupby("year")), ("quarter", work.groupby("quarter"))):
            for period, group in groups:
                records.append({
                    "variant": str(group["variant"].iloc[0]),
                    "one_way_cost_bps": float(group["one_way_cost_bps"].iloc[0]),
                    "period_type": label,
                    "period": str(period),
                    "trades_executed": int(group["executed"].sum()),
                    "net_return": float(np.prod(1.0 + group["net_return"].to_numpy()) - 1.0),
                    "win_rate": float(group.loc[group["executed"], "net_return"].gt(0.0).mean()),
                })
    return pd.DataFrame(records)


def bootstrap_sessions(
    path: pd.DataFrame,
    config: AssessmentConfig,
) -> dict[str, Any]:
    session_returns = (
        path.groupby("session_date", sort=True)["net_return"]
        .apply(lambda values: float(np.prod(1.0 + values.to_numpy()) - 1.0))
        .to_numpy(dtype=float)
    )
    rng = np.random.default_rng(config.bootstrap_seed)
    finals = np.empty(config.bootstrap_samples)
    max_drawdowns = np.empty(config.bootstrap_samples)
    for sample in range(config.bootstrap_samples):
        sampled = rng.choice(session_returns, size=len(session_returns), replace=True)
        curve = np.cumprod(1.0 + sampled)
        curve_with_start = np.r_[1.0, curve]
        peaks = np.maximum.accumulate(curve_with_start)
        finals[sample] = curve[-1] - 1.0
        max_drawdowns[sample] = np.min(curve_with_start / peaks - 1.0)
    return {
        "variant": str(path["variant"].iloc[0]),
        "one_way_cost_bps": float(path["one_way_cost_bps"].iloc[0]),
        "sessions": int(len(session_returns)),
        "samples": config.bootstrap_samples,
        "return_p05": float(np.quantile(finals, 0.05)),
        "return_median": float(np.median(finals)),
        "return_p95": float(np.quantile(finals, 0.95)),
        "probability_positive": float(np.mean(finals > 0.0)),
        "maximum_drawdown_p05": float(np.quantile(max_drawdowns, 0.05)),
        "maximum_drawdown_median": float(np.median(max_drawdowns)),
    }


def simulate_mnq_account(
    trades: pd.DataFrame,
    *,
    variant: str,
    starting_equity: float,
    round_turn_fees: float,
    round_turn_slippage_points: float,
    scenario: str,
    config: AssessmentConfig,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    equity = float(starting_equity)
    current_session: str | None = None
    start_of_day = equity
    daily_losses = 0
    halted = False
    cost_per_contract = round_turn_fees + round_turn_slippage_points * config.mnq_multiplier
    for trade in trades.sort_values("entry_time").itertuples(index=False):
        row = pd.Series(trade._asdict())
        session = str(row["session_date"])
        if session != current_session:
            current_session = session
            start_of_day = equity
            daily_losses = 0
            halted = False
        equity_before = equity
        multiplier = variant_multiplier(row, variant)
        risk_dollars = _planned_risk_dollars(equity, start_of_day, multiplier, variant, config)
        stop_cost = float(row["stop_distance_points"]) * config.mnq_multiplier + cost_per_contract
        risk_contracts = int(np.floor(risk_dollars / stop_cost)) if stop_cost > 0 else 0
        notional_per_contract = float(row["entry_price"]) * config.mnq_multiplier
        leverage_contracts = int(np.floor(config.maximum_leverage * equity / notional_per_contract))
        contracts = 0 if halted else max(0, min(risk_contracts, leverage_contracts))
        if contracts == 0:
            net_pnl = gross_pnl = total_cost = net_return = 0.0
            skip_reason = "daily_halt" if halted else "zero_contracts"
            executed = False
            effective_leverage = deployed_risk = 0.0
        else:
            point_move = float(row["signed_price_return"]) * float(row["entry_price"])
            gross_pnl = point_move * config.mnq_multiplier * contracts
            total_cost = cost_per_contract * contracts
            net_pnl = gross_pnl - total_cost
            net_return = net_pnl / equity
            effective_leverage = notional_per_contract * contracts / equity
            deployed_risk = stop_cost * contracts / equity
            equity += net_pnl
            executed = True
            skip_reason = ""
            if net_pnl < 0.0:
                daily_losses += 1
            halted = (
                daily_losses >= config.daily_loss_count_limit
                or equity / start_of_day - 1.0 <= -config.daily_loss_limit_fraction
            )
        rows.append({
            "variant": variant,
            "scenario": scenario,
            "starting_equity": starting_equity,
            "session_date": session,
            "entry_time": row["entry_time"],
            "executed": executed,
            "skip_reason": skip_reason,
            "contracts": contracts,
            "risk_multiplier": multiplier,
            "planned_risk_dollars": risk_dollars,
            "deployed_risk_fraction": deployed_risk,
            "effective_leverage": effective_leverage,
            "gross_pnl": gross_pnl,
            "total_cost": total_cost,
            "net_pnl": net_pnl,
            "net_return": net_return,
            "equity_before": equity_before,
            "equity_after": equity,
        })
    return pd.DataFrame(rows)


def _markdown_table(frame: pd.DataFrame, columns: list[str] | None = None) -> str:
    view = frame if columns is None else frame[columns]
    if view.empty:
        return "_No observations._"
    headers = list(view.columns)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for values in view.itertuples(index=False, name=None):
        formatted: list[str] = []
        for value in values:
            if isinstance(value, (float, np.floating)):
                formatted.append(f"{value:.4f}")
            else:
                formatted.append(str(value))
        lines.append("| " + " | ".join(formatted) + " |")
    return "\n".join(lines)


def _display_summary(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "variant", "trades_executed", "cumulative_net_return", "annualized_return",
        "maximum_drawdown", "win_rate", "profit_factor", "average_risk_fraction",
        "average_effective_leverage", "break_even_one_way_cost_bps", "daily_halt_skips",
    ]
    out = frame[columns].copy()
    for column in (
        "cumulative_net_return", "annualized_return", "maximum_drawdown", "win_rate",
        "average_risk_fraction",
    ):
        out[column] = out[column].map(lambda value: f"{value:.2%}")
    out["profit_factor"] = out["profit_factor"].map(lambda value: f"{value:.2f}")
    out["average_effective_leverage"] = out["average_effective_leverage"].map(lambda value: f"{value:.2f}x")
    out["break_even_one_way_cost_bps"] = out["break_even_one_way_cost_bps"].map(
        lambda value: f"{value:.2f}" if pd.notna(value) else ">5.00"
    )
    return out


def _build_report(
    summary: pd.DataFrame,
    cost: pd.DataFrame,
    period: pd.DataFrame,
    bootstrap: pd.DataFrame,
    mnq_summary: pd.DataFrame,
    annotated: pd.DataFrame,
    context: pd.DataFrame,
    config: AssessmentConfig,
) -> str:
    reference = summary.loc[summary["one_way_cost_bps"].eq(config.reference_one_way_cost_bps)]
    combined = reference.loc[reference["variant"].eq("full_stack_governor")].iloc[0]
    baseline = reference.loc[reference["variant"].eq("fixed_0.25_no_overlays")].iloc[0]
    yearly = period.loc[
        period["period_type"].eq("year")
        & period["variant"].isin(["fixed_0.25_no_overlays", "full_stack_governor"])
    ].copy()
    yearly["net_return"] = yearly["net_return"].map(lambda value: f"{value:.2%}")
    macro_coverage = (
        annotated["statistical_regime"].fillna("missing").value_counts().rename_axis("regime").reset_index(name="trades")
    )
    shock_coverage = (
        annotated["shock_recovery_state"].fillna("missing").value_counts().rename_axis("state").reset_index(name="trades")
    )
    mnq_view = mnq_summary.copy()
    for column in ("cumulative_net_return", "annualized_return", "maximum_drawdown"):
        mnq_view[column] = mnq_view[column].map(lambda value: f"{value:.2%}")
    return f"""# Macro-governed Nasdaq POC return assessment

## Decision

At the reference **{config.reference_one_way_cost_bps:.2f} bps one-way cost**, the frozen POC ledger earns **{baseline['cumulative_net_return']:.2%}** with fixed 0.25% risk and a **{baseline['maximum_drawdown']:.2%}** maximum drawdown. Applying the macro, trend, shock/recovery, two-minute, and five-minute governors produces **{combined['cumulative_net_return']:.2%}** with a **{combined['maximum_drawdown']:.2%}** drawdown. The overlay is therefore a risk-control layer, not evidence of a higher-return timing edge.

This does not reproduce Fabio Valentini's public competition returns. Those headline results are not a suitable planning assumption because the public standings do not provide a complete trade ledger, leverage path, fees, or maximum drawdown. The defensible planning range is the cost- and size-adjusted result below, followed by live paper validation.

## Frozen workflow tested

1. **Macro bias:** last completed monthly statistical regime; adverse regimes only reduce risk.
2. **Golden-cross and daily bias:** prior-day SPY 50/200 state with 2% hysteresis plus prior-session Nasdaq 10/30 direction.
3. **Shock/reversal timing:** prior-day falling-knife, fragile, recovery, or normal state. A recovery requires a recent shock, falling VIX and credit-spread pace, and positive five-day SPY trend.
4. **Five-minute auction proxy:** last five completed one-minute bars must show momentum on the same side of causal session VWAP for full risk.
5. **Area of interest:** already-frozen 3-day/5-day composite POC with aligned three-session POC migration.
6. **Two-minute confirmation:** direction of the last two completed one-minute bars; it governs size and does not retrospectively remove frozen trades.
7. **Entry:** one-minute acceptance across POC, restricted to regular-session minutes 15–330.
8. **Stop:** the largest of the micro stop, one-minute ATR floor, or 0.50x preceding completed 15-minute range.
9. **Target:** the frozen five-minute, full-position 2R rule. No new target or signal was optimized here.
10. **Sizing:** 0.25% base risk, 20x notional cap, stop after three losing trades or -0.75% in a session. Profit-financed sizing is reported separately.

## Ablation at the reference cost

{_markdown_table(_display_summary(reference))}

## Calendar stability

{_markdown_table(yearly[["variant", "period", "trades_executed", "net_return", "win_rate"]])}

## Did the proposed layers separate expectancy?

The R figures use the frozen ledger's 0.50 bps one-way reference cost. They are descriptive and were not used to retune the trade rule.

{_markdown_table(context)}

## Cost sensitivity

{_markdown_table(cost[["variant", "one_way_cost_bps", "cumulative_net_return", "maximum_drawdown", "profit_factor"]])}

## Session bootstrap

The bootstrap resamples complete trading sessions. It measures path fragility inside this small historical sample; it is not an out-of-sample guarantee.

{_markdown_table(bootstrap)}

## Discrete MNQ sizing

The base fill scenario assumes ${config.mnq_base_round_turn_fees:.2f} round-turn fees plus {config.mnq_base_round_turn_slippage_points:.2f} index points of round-turn slippage per MNQ. The stress scenario assumes ${config.mnq_stress_round_turn_fees:.2f} plus {config.mnq_stress_round_turn_slippage_points:.2f} points. These are scenario inputs, not a quote from a specific broker.

{_markdown_table(mnq_view[["variant", "scenario", "starting_equity", "trades_executed", "zero_contract_skips", "cumulative_net_return", "annualized_return", "maximum_drawdown"]])}

## Regime coverage

Monthly macro coverage:

{_markdown_table(macro_coverage)}

Shock/recovery coverage:

{_markdown_table(shock_coverage)}

## Interpretation

- The monthly macro label changes too little in 2024–2025 to validate macro entry timing. It mostly reduces risk mechanically.
- Golden-cross and daily direction are priors, not triggers. A lower drawdown with proportionally lower return is useful governance, but not added alpha.
- The POC setup's best segment was the prior-day falling-knife state, not the calm state. The generic shock governor therefore reduced the strongest observed expectancy; do not promote it to a live sizing rule from this sample.
- Shock/recovery timing is fully lagged by one day. It cannot react to an intraday shock until the next session with the available panel.
- Two-minute direction aligned on every frozen entry and therefore added no information. The five-minute proxy was aligned on 82 of 89 entries and did not improve expectancy.
- The only entry edge under test remains POC migration plus one-minute acceptance. True footprint aggression, CVD, bid/ask imbalance, queue depletion, and absorption are absent from OHLCV.
- MNQ sizing exposes granularity: smaller accounts may skip valid trades because one contract exceeds the planned stop risk.

## Deployment gate

**BLOCKED for live capital.** The source CSV's contract/venue identity is unverified, 94% of closes are off the CME NQ quarter-point grid, the sample contains only 89 frozen trades, and the candidate was originally selected with visibility into both calendar years. Require contract-verified tick data, true bid/ask/order-flow fields, broker-specific costs, and a fresh forward paper sample before deployment.

## Public reference points

- Fabio Valentini's published workflow is summarized as Direction → Location → Aggression, with roughly 0.25% risk per trade, profits used to finance larger risk, a three-loss stop, scaling into winners, and a stated target of at least 2:1 reward/risk: https://www.chartacademy.com/instructors/fabio-valentini
- Public World Cup standings report +89.5% in Q1 2024, +218.3% in Q4 2024, and +169.7% in Q1 2025. These competition-account figures are not comparable to this unlevered planning return without the underlying ledger and drawdown path: https://www.worldcupchampionships.com/2024-quarterly-finals and https://www.worldcupchampionships.com/world-cup-trading-championship-standings
- CME specifies MNQ as $2 times the Nasdaq-100 Index and a 0.25-point minimum tick worth $0.50: https://www.cmegroup.com/markets/equities/nasdaq/micro-e-mini-nasdaq-100.contractSpecs.html
"""


def build_macro_poc_assessment(
    project_root: str | Path | None = None,
    *,
    trades_path: str | Path = DEFAULT_TRADES,
    macro_path: str | Path = DEFAULT_MACRO,
    daily_path: str | Path = DEFAULT_DAILY,
    nasdaq_path: str | Path = DEFAULT_NASDAQ,
    output_dir: str | Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)

    def resolved(value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else root / path

    trades_file = resolved(trades_path)
    macro_file = resolved(macro_path)
    daily_file = resolved(daily_path)
    nasdaq_file = resolved(nasdaq_path)
    output = resolved(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    config = AssessmentConfig()

    trades = pd.read_csv(trades_file)
    macro = pd.read_csv(macro_file)
    daily_raw = pd.read_csv(daily_file)
    daily = build_daily_market_context(daily_raw)
    bars, data_audit = load_nasdaq_source(nasdaq_file)
    nq_daily = build_nasdaq_daily_context(bars)
    intraday = add_intraday_confirmation(trades, bars)
    annotated = annotate_trades(intraday, macro, daily, nq_daily)

    reference_paths: list[pd.DataFrame] = []
    reference_rows: list[dict[str, Any]] = []
    for variant in VARIANTS:
        path = simulate_fractional_account(
            annotated,
            variant=variant,
            one_way_cost_bps=config.reference_one_way_cost_bps,
            config=config,
        )
        reference_paths.append(path)
        reference_rows.append({
            "variant": variant,
            "one_way_cost_bps": config.reference_one_way_cost_bps,
            "break_even_one_way_cost_bps": estimate_break_even_cost_bps(
                annotated, variant, config
            ),
        } | summarize_account(path))
    ablation = pd.DataFrame(reference_rows)
    context = context_performance(annotated)

    cost_paths: list[pd.DataFrame] = []
    cost_rows: list[dict[str, Any]] = []
    cost_variants = (
        "fixed_0.25_no_overlays", "combined_governor", "full_stack_governor",
        "full_stack_profit_financed",
    )
    for variant in cost_variants:
        for cost_bps in config.cost_scenarios_bps:
            path = simulate_fractional_account(
                annotated, variant=variant, one_way_cost_bps=cost_bps, config=config
            )
            cost_paths.append(path)
            cost_rows.append({"variant": variant, "one_way_cost_bps": cost_bps} | summarize_account(path))
    cost_sensitivity = pd.DataFrame(cost_rows)

    period = _period_summaries(reference_paths)
    bootstrap = pd.DataFrame([
        bootstrap_sessions(path, config)
        for path in reference_paths
        if str(path["variant"].iloc[0]) in {
            "fixed_0.25_no_overlays", "combined_governor", "full_stack_governor",
            "full_stack_profit_financed",
        }
    ])

    mnq_paths: list[pd.DataFrame] = []
    mnq_rows: list[dict[str, Any]] = []
    mnq_scenarios = {
        "base": (config.mnq_base_round_turn_fees, config.mnq_base_round_turn_slippage_points),
        "stress": (config.mnq_stress_round_turn_fees, config.mnq_stress_round_turn_slippage_points),
    }
    for variant in (
        "fixed_0.25_no_overlays", "combined_governor", "full_stack_governor",
        "full_stack_profit_financed",
    ):
        for starting_equity in config.account_sizes:
            for scenario, (fees, slippage) in mnq_scenarios.items():
                path = simulate_mnq_account(
                    annotated,
                    variant=variant,
                    starting_equity=starting_equity,
                    round_turn_fees=fees,
                    round_turn_slippage_points=slippage,
                    scenario=scenario,
                    config=config,
                )
                mnq_paths.append(path)
                metrics = summarize_account(path)
                mnq_rows.append({
                    "variant": variant,
                    "scenario": scenario,
                    "starting_equity": starting_equity,
                    "round_turn_fees": fees,
                    "round_turn_slippage_points": slippage,
                    "zero_contract_skips": int(path["skip_reason"].eq("zero_contracts").sum()),
                } | metrics)
    mnq_summary = pd.DataFrame(mnq_rows)

    governance = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "RESEARCH_ONLY_LIVE_DEPLOYMENT_BLOCKED",
        "signal_status": "frozen stable_5m_base ledger; no entry-rule optimization in this assessment",
        "causal_policy": "monthly, SPY daily, and Nasdaq daily context joined strictly before session date",
        "config": asdict(config),
        "inputs": {
            "trades": str(trades_file), "macro": str(macro_file),
            "daily": str(daily_file), "nasdaq": str(nasdaq_file),
        },
        "data_quality": data_audit,
        "blocking_reasons": [
            "Unverified Nasdaq CSV contract, venue, price grid, and volume identity.",
            "The frozen candidate was selected with visibility into both available years.",
            "Only 89 frozen trades and no untouched forward period.",
            "OHLCV cannot verify Fabio-style footprint aggression or absorption.",
            "MNQ fees and slippage are scenarios rather than broker-specific historical fills.",
        ],
    }

    annotated.to_csv(output / "annotated_trades.csv", index=False)
    ablation.to_csv(output / "ablation_summary.csv", index=False)
    cost_sensitivity.to_csv(output / "cost_sensitivity.csv", index=False)
    period.to_csv(output / "period_summary.csv", index=False)
    bootstrap.to_csv(output / "bootstrap.csv", index=False)
    context.to_csv(output / "context_performance.csv", index=False)
    pd.concat(reference_paths, ignore_index=True).to_csv(output / "fractional_equity_curves.csv", index=False)
    mnq_summary.to_csv(output / "mnq_account_sizing.csv", index=False)
    pd.concat(mnq_paths, ignore_index=True).to_csv(output / "mnq_equity_curves.csv", index=False)
    (output / "governance.json").write_text(json.dumps(governance, indent=2), encoding="utf-8")
    report = _build_report(
        ablation, cost_sensitivity, period, bootstrap, mnq_summary, annotated, context, config
    )
    report_path = output / "report.md"
    report_path.write_text(report, encoding="utf-8")
    return {
        "report_path": report_path,
        "ablation": ablation,
        "cost_sensitivity": cost_sensitivity,
        "period_summary": period,
        "bootstrap": bootstrap,
        "context_performance": context,
        "mnq_summary": mnq_summary,
        "governance": governance,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root")
    parser.add_argument("--trades-path", default=str(DEFAULT_TRADES))
    parser.add_argument("--macro-path", default=str(DEFAULT_MACRO))
    parser.add_argument("--daily-path", default=str(DEFAULT_DAILY))
    parser.add_argument("--nasdaq-path", default=str(DEFAULT_NASDAQ))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    results = build_macro_poc_assessment(
        project_root=args.project_root,
        trades_path=args.trades_path,
        macro_path=args.macro_path,
        daily_path=args.daily_path,
        nasdaq_path=args.nasdaq_path,
        output_dir=args.output_dir,
    )
    print(f"Report: {results['report_path']}")
    print(results["ablation"].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
