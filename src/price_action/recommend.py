from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone

from .data import build_market_frame, load_asset_daily
from .features import build_feature_frame
from .panel import build_panel_dataset
from .train import _gate_feature_columns, build_base_models, fit_gate_model
from .universe import DEFAULT_PANEL_SYMBOLS, expand_symbol_selection, resolve_symbol_profile

LONG_THRESHOLD = 0.55
HEDGE_SHORT_UPPER = 0.50
HEDGE_SHORT_LOWER = 0.48
EXPERIMENTAL_SHORT_FLOOR = 0.46


def compute_beta_to_spy(symbol: str, lookback: int = 252) -> float:
    if symbol.upper() == "SPY":
        return 1.0

    symbol_frame = load_asset_daily(symbol)
    spy_frame = load_asset_daily("SPY")

    symbol_returns = pd.to_numeric(symbol_frame["close"], errors="coerce").pct_change().rename(symbol.upper())
    spy_returns = pd.to_numeric(spy_frame["close"], errors="coerce").pct_change().rename("SPY")
    joined = pd.concat([symbol_returns, spy_returns], axis=1).dropna().tail(lookback)
    if joined.empty:
        return float("nan")

    variance = joined["SPY"].var()
    if variance == 0.0 or pd.isna(variance):
        return float("nan")
    return float(joined[symbol.upper()].cov(joined["SPY"]) / variance)


def compute_universe_beta_stats(symbols: list[str]) -> tuple[dict[str, float], float]:
    beta_map = {symbol: compute_beta_to_spy(symbol) for symbol in symbols}
    valid_betas = pd.Series(beta_map).dropna()
    median_beta = float(valid_betas.median()) if not valid_betas.empty else 1.0
    return beta_map, median_beta


def fit_panel_models(
    training_symbols: list[str],
    label_horizon: int,
    cost_bps: float,
    random_state: int,
) -> tuple[pd.DataFrame, list[str], dict[str, Any], Any]:
    panel, feature_columns = build_panel_dataset(
        symbols=training_symbols,
        label_horizon=label_horizon,
        cost_bps=cost_bps,
    )
    x_train = panel[feature_columns]
    y_train = panel["target"]

    models: dict[str, Any] = {}
    for name, model in build_base_models(random_state=random_state).items():
        fitted = clone(model)
        fitted.fit(x_train, y_train)
        models[name] = fitted

    gate_model = fit_gate_model(x_train=x_train, y_train=y_train, random_state=random_state)
    return panel, feature_columns, models, gate_model


def build_inference_row(
    symbol: str,
    feature_columns: list[str],
    label_horizon: int,
    cost_bps: float,
) -> tuple[pd.Timestamp, pd.DataFrame, pd.Series]:
    market_frame = build_market_frame(symbol=symbol)
    feature_frame, base_feature_columns = build_feature_frame(
        market_frame=market_frame,
        label_horizon=label_horizon,
        cost_bps=cost_bps,
    )
    usable = feature_frame[base_feature_columns].dropna()
    if usable.empty:
        raise ValueError(f"No inference-ready feature row found for {symbol}.")

    latest_date = usable.index.max()
    row = usable.loc[[latest_date]].copy()
    context_row = feature_frame.loc[latest_date].copy()

    for column in feature_columns:
        if column.startswith("symbol_") and column not in row.columns:
            row[column] = 0.0

    symbol_dummy = f"symbol_{symbol.upper()}"
    if symbol_dummy in feature_columns:
        row[symbol_dummy] = 1.0

    for column in feature_columns:
        if column not in row.columns:
            row[column] = 0.0

    row = row[feature_columns].astype(float)
    return latest_date, row, context_row


def infer_profile(
    symbol: str,
    market_cap_bucket: str | None,
    liquidity_tier: str | None,
    shortable: bool | None,
) -> dict[str, Any]:
    base_profile = resolve_symbol_profile(symbol)
    return {
        "market_cap_bucket": market_cap_bucket or base_profile.get("market_cap_bucket", "unknown"),
        "liquidity_tier": liquidity_tier or base_profile.get("liquidity_tier", "unknown"),
        "shortable": shortable if shortable is not None else bool(base_profile.get("shortable", False)),
    }


def score_symbol(
    symbol: str,
    training_symbols: list[str],
    market_cap_bucket: str | None = None,
    liquidity_tier: str | None = None,
    shortable: bool | None = None,
    label_horizon: int = 5,
    cost_bps: float = 15.0,
    random_state: int = 42,
) -> dict[str, Any]:
    symbol = symbol.upper()
    panel_symbols = expand_symbol_selection(training_symbols)
    if symbol not in panel_symbols:
        panel_symbols.append(symbol)

    _, feature_columns, models, gate_model = fit_panel_models(
        training_symbols=panel_symbols,
        label_horizon=label_horizon,
        cost_bps=cost_bps,
        random_state=random_state,
    )
    as_of_date, feature_row, context_row = build_inference_row(
        symbol=symbol,
        feature_columns=feature_columns,
        label_horizon=label_horizon,
        cost_bps=cost_bps,
    )

    base_probabilities = {
        f"prob_{name}": float(model.predict_proba(feature_row)[0, 1]) for name, model in models.items()
    }
    ensemble_probability = float(np.mean(list(base_probabilities.values())))

    gate_input = pd.DataFrame([base_probabilities])
    for column in ["regime_risk_off", "risk_off_score", "regime_trend", "trend_score"]:
        gate_input[column] = float(context_row.get(column, 0.0))

    if gate_model is not None:
        gated_probability = float(gate_model.predict_proba(gate_input[_gate_feature_columns(gate_input)])[0, 1])
    else:
        gated_probability = ensemble_probability

    beta_map, median_beta = compute_universe_beta_stats(panel_symbols)
    beta_to_spy = float(beta_map.get(symbol, float("nan")))
    beta_bucket = "above_median_beta" if beta_to_spy > median_beta else "below_or_equal_beta"

    profile = infer_profile(
        symbol=symbol,
        market_cap_bucket=market_cap_bucket,
        liquidity_tier=liquidity_tier,
        shortable=shortable,
    )

    regime_risk_off = float(context_row.get("regime_risk_off", 0.0)) >= 1.0
    risk_off_score = float(context_row.get("risk_off_score", 0.0))
    trend_score = float(context_row.get("trend_score", 0.0))
    supports_hedge_short = (
        beta_bucket == "above_median_beta"
        and profile["shortable"]
        and profile["liquidity_tier"] in {"high", "very_high"}
    )

    eligible_actions = ["long", "skip"]
    if supports_hedge_short:
        eligible_actions = ["long", "hedge_short", "skip"]

    recommendation = "skip"
    confidence_band = "neutral"
    size_band = "none"
    target_beta_fraction = 0.0
    rationale: list[str] = []

    if gated_probability >= LONG_THRESHOLD and not regime_risk_off:
        recommendation = "long"
        if gated_probability >= 0.59:
            confidence_band = "strong"
            size_band = "full"
            target_beta_fraction = 0.30
        elif gated_probability >= 0.57:
            confidence_band = "moderate"
            size_band = "base"
            target_beta_fraction = 0.20
        else:
            confidence_band = "weak"
            size_band = "starter"
            target_beta_fraction = 0.10
        rationale.append("Model probability cleared the long threshold and the regime filter is not blocking longs.")
    elif supports_hedge_short and HEDGE_SHORT_LOWER <= gated_probability <= HEDGE_SHORT_UPPER:
        recommendation = "hedge_short"
        if gated_probability <= 0.49:
            confidence_band = "moderate"
            size_band = "base_hedge"
            target_beta_fraction = 0.10
        else:
            confidence_band = "weak"
            size_band = "starter_hedge"
            target_beta_fraction = 0.05
        rationale.append(
            "Low probability falls inside the validated hedge-short band for higher-beta names."
        )
    elif supports_hedge_short and gated_probability < HEDGE_SHORT_LOWER:
        rationale.append(
            "Score is below the hedge-short band, but conviction shorts are still disabled because the current proxy short edge degrades below about 0.48."
        )
    else:
        rationale.append("Score did not clear the current long threshold or hedge-short eligibility band.")

    if regime_risk_off:
        rationale.append(f"Risk-off regime is active with score {risk_off_score:.1f}, which blocks long recommendations.")
    else:
        rationale.append(f"Risk-off regime is inactive with score {risk_off_score:.1f}.")

    if beta_bucket == "above_median_beta":
        rationale.append(
            f"Beta to SPY is {beta_to_spy:.2f}, above the universe median {median_beta:.2f}; hedge shorts are eligible if other constraints allow them."
        )
    else:
        rationale.append(
            f"Beta to SPY is {beta_to_spy:.2f}, below or equal to the universe median {median_beta:.2f}; short recommendations stay disabled in the current policy."
        )

    if profile["market_cap_bucket"] in {"mega", "large", "etf"}:
        rationale.append(
            f"Market-cap bucket is {profile['market_cap_bucket']}, so this name is treated as part of the core long/skip sleeve unless beta and shortability clearly justify a hedge role."
        )
    else:
        rationale.append(
            f"Market-cap bucket is {profile['market_cap_bucket']}, which is compatible with the more tactical hedge sleeve if beta and shortability also align."
        )

    suggested_notional_pct_nav = 0.0
    if target_beta_fraction > 0.0 and not np.isnan(beta_to_spy) and beta_to_spy > 0.0:
        suggested_notional_pct_nav = float(target_beta_fraction / beta_to_spy * 100.0)

    output = {
        "symbol": symbol,
        "as_of_date": as_of_date.strftime("%Y-%m-%d"),
        "training_symbols": panel_symbols,
        "label_horizon": label_horizon,
        "cost_bps": cost_bps,
        "probabilities": {
            **base_probabilities,
            "ensemble_probability": ensemble_probability,
            "gated_probability": gated_probability,
        },
        "profile": {
            **profile,
            "beta_to_spy": beta_to_spy,
            "beta_bucket": beta_bucket,
            "beta_median_threshold": median_beta,
        },
        "regime": {
            "regime_risk_off": bool(regime_risk_off),
            "risk_off_score": risk_off_score,
            "regime_trend": bool(float(context_row.get("regime_trend", 0.0)) >= 1.0),
            "trend_score": trend_score,
        },
        "policy": {
            "eligible_actions": eligible_actions,
            "conviction_short_supported": False,
            "long_threshold": LONG_THRESHOLD,
            "hedge_short_band": [HEDGE_SHORT_LOWER, HEDGE_SHORT_UPPER],
            "experimental_short_floor": EXPERIMENTAL_SHORT_FLOOR,
        },
        "recommendation": {
            "action": recommendation,
            "confidence_band": confidence_band,
            "size_band": size_band,
            "suggested_beta_fraction": target_beta_fraction,
            "suggested_notional_pct_nav": suggested_notional_pct_nav,
            "rationale": rationale,
        },
    }
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Score one symbol and emit a cap/beta-aware recommendation.")
    parser.add_argument("--symbol", required=True, help="Symbol to score using the current panel model.")
    parser.add_argument(
        "--training-symbols",
        nargs="+",
        default=["PANEL"],
        help="Training universe. Use PANEL to expand to the repo default panel.",
    )
    parser.add_argument(
        "--market-cap-bucket",
        choices=["mega", "large", "mid", "small", "micro", "etf", "unknown"],
        default=None,
        help="Optional market-cap bucket override.",
    )
    parser.add_argument(
        "--liquidity-tier",
        choices=["very_high", "high", "medium", "low", "unknown"],
        default=None,
        help="Optional liquidity-tier override.",
    )
    shortability = parser.add_mutually_exclusive_group()
    shortability.add_argument("--shortable", dest="shortable", action="store_true")
    shortability.add_argument("--not-shortable", dest="shortable", action="store_false")
    parser.set_defaults(shortable=None)
    parser.add_argument("--horizon", type=int, default=5, help="Forward return horizon in bars.")
    parser.add_argument("--cost-bps", type=float, default=15.0, help="Combined fees and slippage in basis points.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    recommendation = score_symbol(
        symbol=args.symbol,
        training_symbols=list(args.training_symbols),
        market_cap_bucket=args.market_cap_bucket,
        liquidity_tier=args.liquidity_tier,
        shortable=args.shortable,
        label_horizon=args.horizon,
        cost_bps=args.cost_bps,
    )
    print(json.dumps(recommendation, indent=2))


if __name__ == "__main__":
    main()
