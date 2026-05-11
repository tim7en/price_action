from __future__ import annotations

import ast
import argparse
import html
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .data import MACRO_FEATURES_DIR, load_asset_daily, load_macro_context, resolve_project_root
from .macro_context import (
    MACRO_ARCHITECTURE_LAYERS,
    MACRO_DESIGN_PRINCIPLES,
    MACRO_INTERACTION_LIBRARY,
    MACRO_REGIME_WINDOWS,
    MACRO_REPORT_GROUPS,
    MACRO_RECOMMENDED_EXPANSIONS,
    MACRO_SCENARIO_PLAYBOOK,
    MACRO_SERIES_BRIEFS,
    MACRO_SERIES_DETAILS,
)
from .macro_features import write_macro_feature_store

PAGE_BACKGROUND = "#f7f2e8"
PANEL_BACKGROUND = "#fffdf8"
TEXT_COLOR = "#1b2430"
MUTED_TEXT_COLOR = "#5f6b76"
GRID_COLOR = "#d5cfc5"
ACCENT_COLORS = (
    "#0f4c5c",
    "#7a3e2b",
    "#4f6d3a",
    "#7f5539",
    "#4361ee",
)
REGIME_FILL = "#d8c7af"
SVG_WIDTH = 1140
SVG_PLOT_WIDTH = 980
SVG_LEFT_MARGIN = 120
SVG_RIGHT_MARGIN = 40
SVG_TOP_MARGIN = 36
SVG_BOTTOM_MARGIN = 54
SVG_ROW_HEIGHT = 180
SVG_ROW_GAP = 18
REPORT_LOOKBACK_YEARS = 20

REGIME_COLORS: dict[str, str] = {
    "Disinflationary Growth": "#5f8f5b",
    "Liquidity Bubble Or Valuation Stretch": "#d3a24c",
    "Inflationary Boom": "#b56b2d",
    "Stagflation Squeeze": "#9a4a35",
    "Rate-Shock Regime": "#4f698c",
    "Credit Deleveraging": "#6f4e7c",
    "Panic Or Forced Liquidation": "#2f3c4f",
    "Recovery And Reflation": "#3f7f78",
    "Sideways Low-Volatility Regime": "#9b8f77",
    "Fragile Late-Cycle Watch": "#8c5a43",
}

QUADRANT_LIBRARY: tuple[dict[str, str], ...] = (
    {
        "title": "Growth Up / Inflation Down",
        "subtitle": "Disinflationary growth",
        "body": "The clean all-weather backdrop: real activity is improving while inflation pressure is easing, so equities and duration can both breathe.",
    },
    {
        "title": "Growth Up / Inflation Up",
        "subtitle": "Inflationary boom",
        "body": "Nominal growth is strong, but inflation is heating up fast enough that rates and real assets start to matter more than long duration.",
    },
    {
        "title": "Growth Down / Inflation Up",
        "subtitle": "Stagflation squeeze",
        "body": "The hardest quadrant for diversified risk: growth softens while inflation stays sticky, which pressures both margins and valuation multiples.",
    },
    {
        "title": "Growth Down / Inflation Down",
        "subtitle": "Disinflationary slowdown",
        "body": "A slowdown without inflation pressure can become a recovery setup if stress variables ease, but credit and volatility have to confirm it.",
    },
)

REGIME_LIBRARY: tuple[dict[str, str], ...] = (
    {
        "title": "Disinflationary Growth",
        "summary": "Growth is healthy enough to support risk assets while inflation pressure is easing or contained.",
        "playbook": "Trend-following and normal risk budgets can work when credit and volatility stay calm.",
        "risk": "The failure mode is complacency: rich valuation plus a fresh VIX or rate shock.",
    },
    {
        "title": "Liquidity Bubble Or Valuation Stretch",
        "summary": "Valuation and momentum are running ahead of the macro margin of safety while volatility and credit still look benign.",
        "playbook": "Do not short richness on its own, but react faster to failed breakouts, VIX turns, and front-end repricing.",
        "risk": "Once liquidity conditions change, valuation can turn from tailwind to vulnerability very quickly.",
    },
    {
        "title": "Inflationary Boom",
        "summary": "Nominal growth and inflation are both strong, which tends to help real assets and cash-flow-now businesses more than long duration.",
        "playbook": "Favor price action confirmed by real activity, commodities, and sturdy balance sheets.",
        "risk": "If production weakens while inflation stays elevated, the boom usually degrades into stagflation.",
    },
    {
        "title": "Stagflation Squeeze",
        "summary": "Inflation stays stubborn while production and labor momentum soften, squeezing both margins and multiples.",
        "playbook": "Reduce broad long exposure, demand stronger confirmation, and lean toward defensive or inflation-linked exposures.",
        "risk": "Policy has little room to rescue markets without worsening inflation credibility.",
    },
    {
        "title": "Rate-Shock Regime",
        "summary": "Front-end or real-yield repricing is moving fast enough to hit long-duration assets before credit fully breaks.",
        "playbook": "Penalize duration sensitivity, reduce leverage, and watch rate-shock interactions with expensive valuation.",
        "risk": "A rate shock often becomes a credit shock with a lag.",
    },
    {
        "title": "Credit Deleveraging",
        "summary": "Credit spreads and financial conditions are tightening enough that the market is starting to transmit stress into the real economy.",
        "playbook": "Trade less, lower risk budgets, and wait for credit stabilization before re-risking.",
        "risk": "Cross-asset diversification weakens when refinancing stress turns broad.",
    },
    {
        "title": "Panic Or Forced Liquidation",
        "summary": "Immediate stress is overwhelming the system: VIX spikes, credit widens, and market liquidity thins out.",
        "playbook": "Survival matters more than signal frequency. Cut leverage and treat price moves in volatility-adjusted terms.",
        "risk": "Normal model assumptions break when price movement becomes discontinuous.",
    },
    {
        "title": "Recovery And Reflation",
        "summary": "Stress is still elevated, but the direction of stress is improving faster than the official macro data.",
        "playbook": "Allow recovery signals when VIX and credit improve together, even if growth data still looks ugly.",
        "risk": "Bear-market rallies fail when credit does not confirm the improvement.",
    },
    {
        "title": "Sideways Low-Volatility Regime",
        "summary": "Growth and inflation are stable enough that carry and mean reversion dominate while breakouts lose urgency.",
        "playbook": "Keep breakout confidence modest and watch for the first low-to-rising volatility transition.",
        "risk": "The first volatility expansion can invalidate months of low-vol assumptions.",
    },
    {
        "title": "Fragile Late-Cycle Watch",
        "summary": "Valuation is rich, volatility is elevated, and growth is no longer broad, but credit has not fully cracked yet.",
        "playbook": "Treat the market as conditionally risk-on: participate selectively, but let credit and volatility control exposure quality.",
        "risk": "A spread blowout, oil shock, or new rate repricing can harden this into a much more hostile regime.",
    },
)

SECTOR_BUCKETS: tuple[dict[str, str], ...] = (
    {
        "symbol": "XLE",
        "label": "Energy",
        "family": "Real asset cyclical",
        "earnings_proxy": "High earnings leverage to oil, capex, and nominal GDP.",
        "role": "Often benefits most when inflation and supply shocks dominate the tape.",
    },
    {
        "symbol": "XLB",
        "label": "Commodity / Materials",
        "family": "Cyclical inflation beta",
        "earnings_proxy": "Sensitive to industrial demand, pricing power, and commodity volumes.",
        "role": "Usually improves when nominal growth and input scarcity rise together.",
    },
    {
        "symbol": "XLI",
        "label": "Manufacturing / Industrials",
        "family": "Growth and capex cyclical",
        "earnings_proxy": "Leverages industrial production, capex, and freight intensity.",
        "role": "Tends to lead in recovery and reflation regimes when production broadens.",
    },
    {
        "symbol": "XLF",
        "label": "Financials",
        "family": "Credit and curve cyclical",
        "earnings_proxy": "Sensitive to credit creation, net interest margins, capital markets activity, and balance-sheet stress.",
        "role": "Usually matters most when credit conditions, the yield curve, and policy stress drive equity leadership.",
    },
    {
        "symbol": "XLY",
        "label": "Retail / Consumer Discretionary",
        "family": "Consumer cyclical",
        "earnings_proxy": "Most exposed to real income, labor resilience, and disinflation relief.",
        "role": "Usually wants falling input pressure, healthy labor, and calm credit.",
    },
    {
        "symbol": "XLK",
        "label": "Information Technology",
        "family": "Duration and innovation",
        "earnings_proxy": "Benefits from disinflation, lower discount rates, and enterprise capex strength.",
        "role": "Typically strongest in disinflationary growth or liquidity-led melt-up regimes.",
    },
    {
        "symbol": "XLP",
        "label": "Consumer Staples",
        "family": "Defensive cash flow",
        "earnings_proxy": "Lower-volatility earnings with less macro beta than cyclical retail.",
        "role": "Acts as a defensive buffer when growth is fading or rate stress rises.",
    },
    {
        "symbol": "XLV",
        "label": "Health Care",
        "family": "Defensive quality",
        "earnings_proxy": "Relatively stable earnings stream with lower sensitivity to the goods cycle.",
        "role": "Useful when the portfolio needs defense without fully abandoning equity exposure.",
    },
    {
        "symbol": "XLU",
        "label": "Utilities",
        "family": "Rate-sensitive defense",
        "earnings_proxy": "Stable regulated cash flows, but still sensitive to rate and duration pressure.",
        "role": "Can cushion drawdowns when stress rises, though not every inflation regime helps it.",
    },
)

DEFENSIVE_SECTOR_SYMBOLS: tuple[str, ...] = ("XLP", "XLV", "XLU")
DEFENSIVE_REGIMES: tuple[str, ...] = (
    "Fragile Late-Cycle Watch",
    "Stagflation Squeeze",
    "Rate-Shock Regime",
    "Credit Deleveraging",
    "Panic Or Forced Liquidation",
)


def _ensure_macro_feature_store(project_root: str | Path | None = None) -> Path:
    root = resolve_project_root(project_root)
    feature_store_dir = root / MACRO_FEATURES_DIR
    write_macro_feature_store(project_root=root)
    return feature_store_dir


def load_model_macro_inventory(project_root: str | Path | None = None) -> pd.DataFrame:
    root = resolve_project_root(project_root)
    feature_store_dir = _ensure_macro_feature_store(project_root=root)
    inventory = pd.read_csv(feature_store_dir / "feature_inventory.csv")
    inventory = inventory.loc[
        inventory["feature"].isin(
            [feature for group in MACRO_REPORT_GROUPS for feature in group["series"]]
        )
    ].copy()
    inventory = inventory.set_index("feature", drop=False)
    return inventory


def load_model_macro_frame(project_root: str | Path | None = None) -> pd.DataFrame:
    root = resolve_project_root(project_root)
    _ensure_macro_feature_store(project_root=root)
    frame = load_macro_context(project_root=root)
    selected = [feature for group in MACRO_REPORT_GROUPS for feature in group["series"] if feature in frame.columns]
    numeric = frame[selected].apply(pd.to_numeric, errors="coerce").sort_index().ffill()
    numeric.index = pd.to_datetime(numeric.index)
    return numeric


def _format_value(value: Any, units: str | None) -> str:
    if pd.isna(value):
        return "n/a"

    numeric = float(value)
    unit_text = units.lower() if isinstance(units, str) else ""
    if "usd per" in unit_text:
        return f"${numeric:,.2f}"
    if "percent" in unit_text:
        return f"{numeric:,.2f}%"
    if "ratio" in unit_text:
        return f"{numeric:,.2f}x"
    if "billions" in unit_text:
        return f"{numeric:,.0f} bn"
    if abs(numeric) >= 1000:
        return f"{numeric:,.0f}"
    if abs(numeric) >= 100:
        return f"{numeric:,.1f}"
    return f"{numeric:,.2f}"


def _render_source_link(source: str | None, source_url: str | None) -> str:
    label = "unknown" if pd.isna(source) else html.escape(str(source))
    if isinstance(source_url, str) and source_url.strip():
        return f'<a href="{html.escape(source_url)}">{label}</a>'
    return label


def _zscore(series: pd.Series, min_periods: int = 24) -> pd.Series:
    """Causal expanding z-score.

    Each observation is normalized against the mean and population standard
    deviation computed strictly from prior and current values, so the
    resulting series carries no information from the future. Rows before
    ``min_periods`` observations exist, and rows where the trailing window
    is constant, fall back to 0.0 to match the previous fall-through
    behavior used by ``_classify_regime``.
    """
    numeric = pd.to_numeric(series, errors="coerce")
    mean = numeric.expanding(min_periods=min_periods).mean()
    std = numeric.expanding(min_periods=min_periods).std(ddof=0)
    z = (numeric - mean) / std.replace(0.0, np.nan)
    return z.fillna(0.0)


def _format_sigma(value: float) -> str:
    return f"{value:+.1f} sigma"


def _format_duration(months: int) -> str:
    if months >= 24:
        years = months / 12.0
        return f"{years:.1f} years"
    if months == 1:
        return "1 month"
    return f"{months} months"


def _score_direction(value: float, positive_text: str, negative_text: str, neutral_text: str) -> str:
    if value >= 0.45:
        return positive_text
    if value <= -0.45:
        return negative_text
    return neutral_text


def _current_regime_library_entry(label: str) -> dict[str, str]:
    for item in REGIME_LIBRARY:
        if item["title"] == label:
            return dict(item)
    return {
        "title": label,
        "summary": "Rule-assisted macro label derived from the current growth, inflation, rate, credit, and volatility mix.",
        "playbook": "Use the stress variables to control exposure quality.",
        "risk": "Transitions can happen faster than headline macro data suggests.",
    }


def _current_quadrant_entry(label: str) -> dict[str, str]:
    for item in QUADRANT_LIBRARY:
        if item["title"] == label:
            return dict(item)
    return {
        "title": label,
        "subtitle": "Macro quadrant",
        "body": "Growth and inflation composite inferred from the cached macro store.",
    }


def _classify_quadrant(row: pd.Series) -> str:
    growth_up = float(row["growth_axis"]) >= 0.15
    inflation_up = float(row["inflation_axis"]) >= 0.15
    if growth_up and not inflation_up:
        return "Growth Up / Inflation Down"
    if growth_up and inflation_up:
        return "Growth Up / Inflation Up"
    if not growth_up and inflation_up:
        return "Growth Down / Inflation Up"
    return "Growth Down / Inflation Down"


def _classify_regime(row: pd.Series) -> str:
    volatility_stress = float(row["volatility_stress"])
    credit_stress = float(row["credit_stress"])
    rate_shock = float(row["rate_shock"])
    valuation_fragility = float(row["valuation_fragility"])
    growth_axis = float(row["growth_axis"])
    inflation_axis = float(row["inflation_axis"])
    stress_improving = float(row["stress_improving"])
    spot_vix = float(row["spot_vix"])
    vix3m_level = float(row["vix3m_level"])

    if volatility_stress > 1.1 and credit_stress > 0.9 and spot_vix > vix3m_level:
        return "Panic Or Forced Liquidation"
    if credit_stress > 0.85 and (volatility_stress > 0.55 or growth_axis < -0.45):
        return "Credit Deleveraging"
    if stress_improving > 0.5 and (volatility_stress > 0.4 or credit_stress > 0.3):
        return "Recovery And Reflation"
    if rate_shock > 0.9 and valuation_fragility > 0.45:
        return "Rate-Shock Regime"
    if valuation_fragility > 0.8 and volatility_stress > 0.25 and credit_stress < 0.2 and growth_axis < 0.1:
        return "Fragile Late-Cycle Watch"
    if inflation_axis > 0.35 and growth_axis < -0.15:
        return "Stagflation Squeeze"
    if inflation_axis > 0.35 and growth_axis >= -0.15 and credit_stress < 0.5:
        return "Inflationary Boom"
    if valuation_fragility > 0.8 and volatility_stress < 0.15 and credit_stress < 0.0 and growth_axis > -0.2:
        return "Liquidity Bubble Or Valuation Stretch"
    if growth_axis > 0.15 and inflation_axis < 0.2 and volatility_stress < 0.45 and credit_stress < 0.35:
        return "Disinflationary Growth"
    if abs(growth_axis) < 0.2 and abs(inflation_axis) < 0.25 and volatility_stress < -0.25 and credit_stress < 0.2:
        return "Sideways Low-Volatility Regime"
    return "Fragile Late-Cycle Watch"


def _smooth_label_series(labels: pd.Series, min_persistence: int = 2) -> pd.Series:
    """Causal de-noising of regime labels via a persistence rule.

    A new label is only adopted after it has been observed for
    ``min_persistence`` consecutive periods; until then the previously
    committed label is held. Only past and current values are read, so
    the smoothed series carries no future leakage.
    """
    if min_persistence <= 1 or len(labels) == 0:
        return labels
    values = labels.astype("object").tolist()
    smoothed: list[Any] = [values[0]]
    current = values[0]
    candidate = values[0]
    streak = 1
    for index in range(1, len(values)):
        observation = values[index]
        if observation == current:
            candidate = observation
            streak = 1
        elif observation == candidate:
            streak += 1
        else:
            candidate = observation
            streak = 1
        if streak >= min_persistence:
            current = candidate
        smoothed.append(current)
    return pd.Series(smoothed, index=labels.index)


def _window_macro_summary(window_frame: pd.DataFrame) -> str:
    growth_text = _score_direction(
        float(window_frame["growth_axis"].mean()),
        positive_text="growth broadening",
        negative_text="growth fading",
        neutral_text="growth mixed",
    )
    inflation_text = _score_direction(
        float(window_frame["inflation_axis"].mean()),
        positive_text="inflation pressure elevated",
        negative_text="disinflation dominant",
        neutral_text="inflation balanced",
    )
    stress_text = _score_direction(
        float(window_frame["stress_axis"].mean()),
        positive_text="stress elevated",
        negative_text="stress calm",
        neutral_text="stress mixed",
    )
    return f"{growth_text}, {inflation_text}, and {stress_text}."


def _build_regime_windows(regime_frame: pd.DataFrame) -> list[dict[str, Any]]:
    if regime_frame.empty:
        return []

    windows: list[dict[str, Any]] = []
    start_index = regime_frame.index[0]
    current_label = str(regime_frame["regime_label"].iloc[0])

    for timestamp, label in regime_frame["regime_label"].iloc[1:].items():
        if str(label) == current_label:
            continue
        window_end = timestamp - pd.offsets.MonthEnd(1)
        window_frame = regime_frame.loc[start_index:window_end]
        if not window_frame.empty:
            dominant_quadrant = str(window_frame["quadrant_label"].mode().iloc[0])
            months = int(len(window_frame.index))
            windows.append(
                {
                    "label": current_label,
                    "color": REGIME_COLORS.get(current_label, ACCENT_COLORS[0]),
                    "start_display": pd.Timestamp(window_frame.index[0]).strftime("%b %Y"),
                    "end_display": pd.Timestamp(window_frame.index[-1]).strftime("%b %Y"),
                    "months": months,
                    "duration": _format_duration(months),
                    "quadrant": dominant_quadrant,
                    "summary": _window_macro_summary(window_frame),
                    "score_chips": (
                        f"Growth {_format_sigma(float(window_frame['growth_axis'].mean()))}",
                        f"Inflation {_format_sigma(float(window_frame['inflation_axis'].mean()))}",
                        f"Stress {_format_sigma(float(window_frame['stress_axis'].mean()))}",
                    ),
                }
            )
        start_index = timestamp
        current_label = str(label)

    final_window = regime_frame.loc[start_index:]
    if not final_window.empty:
        dominant_quadrant = str(final_window["quadrant_label"].mode().iloc[0])
        months = int(len(final_window.index))
        windows.append(
            {
                "label": current_label,
                "color": REGIME_COLORS.get(current_label, ACCENT_COLORS[0]),
                "start_display": pd.Timestamp(final_window.index[0]).strftime("%b %Y"),
                "end_display": pd.Timestamp(final_window.index[-1]).strftime("%b %Y"),
                "months": months,
                "duration": _format_duration(months),
                "quadrant": dominant_quadrant,
                "summary": _window_macro_summary(final_window),
                "score_chips": (
                    f"Growth {_format_sigma(float(final_window['growth_axis'].mean()))}",
                    f"Inflation {_format_sigma(float(final_window['inflation_axis'].mean()))}",
                    f"Stress {_format_sigma(float(final_window['stress_axis'].mean()))}",
                ),
                "is_current": True,
            }
        )

    filtered_windows = [window for window in windows if window["months"] >= 3 or window.get("is_current")]
    return filtered_windows or windows


def _build_current_watch_items(row: pd.Series) -> list[str]:
    items: list[str] = []
    if float(row["credit_stress"]) < 0.2:
        items.append("Credit is still the confirmation variable. A fast spread widening would harden this into deleveraging.")
    else:
        items.append("Credit already shows pressure. Stabilization there matters more than a single equity bounce.")

    if float(row["inflation_axis"]) > 0.25:
        items.append("Core and shelter easing, plus oil stabilization, would move the regime toward a friendlier disinflation path.")
    else:
        items.append("An energy or shelter reacceleration would push the regime back toward inflation shock.")

    if float(row["rate_shock"]) > 0.35:
        items.append("Further front-end repricing would keep long-duration assets under pressure even without a credit accident.")
    elif float(row["volatility_stress"]) > 0.35:
        items.append("A falling VIX with stable credit would improve this regime faster than headline growth data alone.")
    else:
        items.append("Low volatility is only constructive while valuation and rates remain stable enough to avoid a fresh shock.")
    return items


def _build_regime_overview(frame: pd.DataFrame, lookback_years: int = REPORT_LOOKBACK_YEARS) -> dict[str, Any]:
    monthly = frame.resample("ME").last().ffill()

    regime_frame = pd.DataFrame(index=monthly.index)
    regime_frame["spot_vix"] = monthly["spot_vix"]
    regime_frame["vix3m_level"] = monthly["vix3m_level"]
    regime_frame["high_yield_spread"] = monthly["high_yield_spread"]
    regime_frame["NFCI"] = monthly["NFCI"]
    regime_frame["us_2y_yield"] = monthly["us_2y_yield"]
    regime_frame["us_10y_yield"] = monthly["us_10y_yield"]
    regime_frame["yield_curve_10y_2y"] = monthly["yield_curve_10y_2y"]
    regime_frame["wti_usd_per_bbl"] = monthly["wti_usd_per_bbl"]
    regime_frame["shiller_cape_ratio"] = monthly["shiller_cape_ratio"]
    regime_frame["market_cap_to_gdp_pct_patched"] = monthly["market_cap_to_gdp_pct_patched"]

    growth_level = pd.concat(
        [
            _zscore(monthly["industrial_production_yoy_pct"]),
            _zscore(monthly["manufacturing_output_yoy_pct"]),
            -_zscore(monthly["unemployment_rate_pct"]),
        ],
        axis=1,
    ).mean(axis=1)
    growth_trend = pd.concat(
        [
            _zscore(monthly["industrial_production_yoy_pct"].diff(3)),
            _zscore(monthly["manufacturing_output_yoy_pct"].diff(3)),
            -_zscore(monthly["unemployment_rate_pct"].diff(3)),
        ],
        axis=1,
    ).mean(axis=1)
    inflation_level = pd.concat(
        [
            _zscore(monthly["cpi_yoy_pct"]),
            _zscore(monthly["core_cpi_yoy_pct"]),
            _zscore(monthly["shelter_cpi_yoy_pct"]),
            0.6 * _zscore(monthly["energy_cpi_yoy_pct"]),
        ],
        axis=1,
    ).mean(axis=1)
    inflation_trend = pd.concat(
        [
            _zscore(monthly["cpi_yoy_pct"].diff(3)),
            _zscore(monthly["core_cpi_yoy_pct"].diff(3)),
            _zscore(monthly["shelter_cpi_yoy_pct"].diff(3)),
            0.6 * _zscore(monthly["energy_cpi_yoy_pct"].diff(3)),
        ],
        axis=1,
    ).mean(axis=1)
    volatility_stress = pd.concat(
        [
            _zscore(monthly["spot_vix"]),
            _zscore(monthly["spot_vix"] - monthly["vix3m_level"]),
            0.7 * _zscore(monthly["spot_vix"].diff(3)),
        ],
        axis=1,
    ).mean(axis=1)
    credit_stress = pd.concat(
        [
            _zscore(monthly["high_yield_spread"]),
            _zscore(monthly["NFCI"]),
            0.6 * _zscore(monthly["high_yield_spread"].diff(3)),
        ],
        axis=1,
    ).mean(axis=1)
    rate_shock = pd.concat(
        [
            _zscore(monthly["us_2y_yield"].diff(3)),
            0.8 * _zscore(monthly["us_10y_yield"].diff(3)),
            -0.5 * _zscore(monthly["yield_curve_10y_2y"].diff(3)),
        ],
        axis=1,
    ).mean(axis=1)
    valuation_fragility = pd.concat(
        [
            _zscore(monthly["shiller_cape_ratio"]),
            _zscore(monthly["market_cap_to_gdp_pct_patched"]),
        ],
        axis=1,
    ).mean(axis=1)

    regime_frame["growth_axis"] = (0.65 * growth_level + 0.35 * growth_trend).rolling(3, min_periods=1).mean()
    regime_frame["inflation_axis"] = (0.7 * inflation_level + 0.3 * inflation_trend).rolling(3, min_periods=1).mean()
    regime_frame["volatility_stress"] = volatility_stress.rolling(3, min_periods=1).mean()
    regime_frame["credit_stress"] = credit_stress.rolling(3, min_periods=1).mean()
    regime_frame["rate_shock"] = rate_shock.rolling(3, min_periods=1).mean()
    regime_frame["valuation_fragility"] = valuation_fragility.rolling(3, min_periods=1).mean()
    regime_frame["stress_improving"] = pd.concat(
        [
            -_zscore(monthly["spot_vix"].diff(3)),
            -_zscore(monthly["high_yield_spread"].diff(3)),
            -_zscore(monthly["NFCI"].diff(3)),
        ],
        axis=1,
    ).mean(axis=1).rolling(3, min_periods=1).mean()
    regime_frame["stress_axis"] = pd.concat(
        [
            regime_frame["volatility_stress"],
            regime_frame["credit_stress"],
            0.8 * regime_frame["rate_shock"],
        ],
        axis=1,
    ).mean(axis=1)

    lookback_start = regime_frame.index.max() - pd.DateOffset(years=lookback_years)
    regime_frame = regime_frame.loc[regime_frame.index >= lookback_start].copy()
    regime_frame["quadrant_label"] = regime_frame.apply(_classify_quadrant, axis=1)
    regime_frame["regime_label"] = regime_frame.apply(_classify_regime, axis=1)
    regime_frame["regime_label"] = _smooth_label_series(regime_frame["regime_label"])

    windows = _build_regime_windows(regime_frame)
    current_row = regime_frame.iloc[-1]
    current_window = windows[-1] if windows else None
    current_regime_label = str(current_row["regime_label"])
    current_quadrant_label = str(current_row["quadrant_label"])
    current_regime_entry = _current_regime_library_entry(current_regime_label)
    current_quadrant_entry = _current_quadrant_entry(current_quadrant_label)

    quadrant_cards: list[dict[str, Any]] = []
    total_months = max(len(regime_frame.index), 1)
    quadrant_counts = regime_frame["quadrant_label"].value_counts()
    for item in QUADRANT_LIBRARY:
        months = int(quadrant_counts.get(item["title"], 0))
        quadrant_cards.append(
            {
                **item,
                "months": months,
                "share": months / total_months,
                "active": item["title"] == current_quadrant_label,
            }
        )

    taxonomy_cards = [
        {
            **item,
            "color": REGIME_COLORS.get(item["title"], ACCENT_COLORS[0]),
            "active": item["title"] == current_regime_label,
        }
        for item in REGIME_LIBRARY
    ]

    dominant_regimes = regime_frame["regime_label"].value_counts().head(4)
    dominant_cards = [
        {
            "label": str(label),
            "months": int(months),
            "share": int(round((months / total_months) * 100.0)),
            "color": REGIME_COLORS.get(str(label), ACCENT_COLORS[0]),
        }
        for label, months in dominant_regimes.items()
    ]

    timeline_segments = [
        {
            "label": window["label"],
            "color": window["color"],
            "width_pct": (window["months"] / total_months) * 100.0,
            "title": f"{window['label']}: {window['start_display']} to {window['end_display']} ({window['duration']})",
        }
        for window in windows
    ]

    return {
        "start_display": pd.Timestamp(regime_frame.index.min()).strftime("%b %Y"),
        "end_display": pd.Timestamp(regime_frame.index.max()).strftime("%b %Y"),
        "history_frame": regime_frame,
        "current": {
            "regime_label": current_regime_label,
            "regime_color": REGIME_COLORS.get(current_regime_label, ACCENT_COLORS[0]),
            "quadrant_label": current_quadrant_label,
            "quadrant_subtitle": current_quadrant_entry["subtitle"],
            "regime_summary": current_regime_entry["summary"],
            "playbook": current_regime_entry["playbook"],
            "risk": current_regime_entry["risk"],
            "quadrant_body": current_quadrant_entry["body"],
            "duration": current_window["duration"] if current_window else "n/a",
            "window_start": current_window["start_display"] if current_window else pd.Timestamp(regime_frame.index[-1]).strftime("%b %Y"),
            "macro_narrative": " ".join(
                [
                    _score_direction(float(current_row["growth_axis"]), "Growth is broadening.", "Growth is deteriorating.", "Growth is soft but not broken."),
                    _score_direction(float(current_row["inflation_axis"]), "Inflation pressure is above trend.", "Disinflation is doing most of the work.", "Inflation is near balance."),
                    _score_direction(float(current_row["valuation_fragility"]), "Valuation is rich.", "Valuation is not the main risk right now.", "Valuation is not providing much margin of safety."),
                    _score_direction(float(current_row["credit_stress"]), "Credit stress is active.", "Credit still looks calm.", "Credit is mixed rather than broken."),
                ]
            ),
            "watch_items": _build_current_watch_items(current_row),
            "score_chips": (
                f"Growth {_format_sigma(float(current_row['growth_axis']))}",
                f"Inflation {_format_sigma(float(current_row['inflation_axis']))}",
                f"Stress {_format_sigma(float(current_row['stress_axis']))}",
                f"Rates {_format_sigma(float(current_row['rate_shock']))}",
                f"Valuation {_format_sigma(float(current_row['valuation_fragility']))}",
            ),
            "market_chips": (
                f"VIX {float(current_row['spot_vix']):.1f}",
                f"HY spread {float(current_row['high_yield_spread']):.2f}%",
                f"2Y {float(current_row['us_2y_yield']):.2f}%",
                f"Oil ${float(current_row['wti_usd_per_bbl']):.0f}",
                f"CAPE {float(current_row['shiller_cape_ratio']):.1f}x",
            ),
        },
        "quadrant_cards": quadrant_cards,
        "taxonomy_cards": taxonomy_cards,
        "timeline_segments": timeline_segments,
        "window_cards": windows,
        "dominant_cards": dominant_cards,
    }


def _format_return_pct(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value) * 100:+.1f}%"


def _format_probability_pct(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value) * 100:.0f}%"


def _format_weight_pct(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value) * 100:.1f}%"


def _confidence_label(score: float) -> str:
    if score >= 75.0:
        return "High"
    if score >= 60.0:
        return "Moderate"
    return "Low"


def _future_window_extreme(series: pd.Series, months: int, mode: str) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    result = np.full(len(values), np.nan, dtype=float)
    for index in range(len(values)):
        window = values[index + 1 : index + 1 + months]
        window = window[np.isfinite(window)]
        if window.size == 0:
            continue
        result[index] = float(window.max()) if mode == "max" else float(window.min())
    return pd.Series(result, index=series.index, dtype="float64")


def _annualize_total_return(total_return: pd.Series, months: int) -> pd.Series:
    numeric = pd.to_numeric(total_return, errors="coerce")
    base = 1.0 + numeric
    base = base.where(base > 0.0)
    return np.power(base, 12.0 / months) - 1.0


def _normalised_rank(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.dropna().nunique() <= 1:
        return pd.Series(0.5, index=numeric.index, dtype="float64")
    return numeric.rank(pct=True, method="average").fillna(0.5)


def _latest_sector_extension_metrics(close: pd.Series) -> dict[str, float]:
    daily_close = pd.to_numeric(close, errors="coerce").dropna().sort_index()
    if daily_close.empty:
        return {
            "recent_advance_20d": float("nan"),
            "recent_advance_60d": float("nan"),
            "drawdown_from_252d_high": float("nan"),
            "rebound_from_252d_low": float("nan"),
        }

    recent_advance_20d = daily_close.pct_change(20)
    recent_advance_60d = daily_close.pct_change(60)
    rolling_high_252d = daily_close.rolling(252, min_periods=63).max()
    rolling_low_252d = daily_close.rolling(252, min_periods=63).min()
    latest_close = float(daily_close.iloc[-1])
    latest_high = rolling_high_252d.iloc[-1]
    latest_low = rolling_low_252d.iloc[-1]

    drawdown_from_252d_high = float(latest_close / latest_high - 1.0) if pd.notna(latest_high) and latest_high else float("nan")
    rebound_from_252d_low = float(latest_close / latest_low - 1.0) if pd.notna(latest_low) and latest_low else float("nan")

    return {
        "recent_advance_20d": float(recent_advance_20d.iloc[-1]) if pd.notna(recent_advance_20d.iloc[-1]) else float("nan"),
        "recent_advance_60d": float(recent_advance_60d.iloc[-1]) if pd.notna(recent_advance_60d.iloc[-1]) else float("nan"),
        "drawdown_from_252d_high": drawdown_from_252d_high,
        "rebound_from_252d_low": rebound_from_252d_low,
    }


def _render_data_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    if not rows:
        return ""
    header_html = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body_html = []
    for row in rows:
        body_html.append("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>")
    return "\n".join(
        [
            '<div class="table-shell">',
            '  <table class="data-table">',
            f'    <thead><tr>{header_html}</tr></thead>',
            f'    <tbody>{"".join(body_html)}</tbody>',
            '  </table>',
            '</div>',
        ]
    )


def _build_sector_rotation_view(
    project_root: str | Path | None,
    regime_overview: dict[str, Any],
) -> dict[str, Any]:
    regime_history = regime_overview.get("history_frame")
    if not isinstance(regime_history, pd.DataFrame) or regime_history.empty:
        return {
            "available": False,
            "message": "Regime history is unavailable, so sector rotation analytics were skipped.",
            "missing_symbols": [],
        }

    close_frames: list[pd.Series] = []
    available_cards: list[dict[str, str]] = []
    missing_symbols: list[str] = []
    for sector in SECTOR_BUCKETS:
        symbol = sector["symbol"]
        try:
            asset_frame = load_asset_daily(symbol, project_root=project_root)
        except FileNotFoundError:
            missing_symbols.append(symbol)
            continue

        close = pd.to_numeric(asset_frame.get("close"), errors="coerce").dropna()
        if close.empty:
            missing_symbols.append(symbol)
            continue

        monthly_close = close.resample("ME").last().rename(symbol).dropna()
        if monthly_close.empty:
            missing_symbols.append(symbol)
            continue

        close_frames.append(monthly_close)
        available_cards.append(dict(sector))

    if not close_frames:
        return {
            "available": False,
            "message": "No sector ETF histories were available in the local cache.",
            "missing_symbols": missing_symbols,
        }

    sector_prices = pd.concat(close_frames, axis=1).sort_index().ffill()
    common_index = regime_history.index.intersection(sector_prices.index)
    regime_history = regime_history.loc[common_index].copy()
    sector_prices = sector_prices.loc[common_index].copy()

    rows: list[dict[str, Any]] = []
    for sector in available_cards:
        symbol = sector["symbol"]
        series = pd.to_numeric(sector_prices[symbol], errors="coerce").dropna()
        if len(series) < 60:
            continue

        latest_extension_metrics = _latest_sector_extension_metrics(close=load_asset_daily(symbol, project_root=project_root)["close"])

        sector_frame = regime_history.join(series.rename("close"), how="inner")
        if sector_frame.empty:
            continue

        sector_frame["forward_return_12m"] = sector_frame["close"].shift(-12) / sector_frame["close"] - 1.0
        sector_frame["forward_return_36m"] = sector_frame["close"].shift(-36) / sector_frame["close"] - 1.0
        sector_frame["expected_return_12m"] = _annualize_total_return(sector_frame["forward_return_12m"], months=12)
        sector_frame["expected_return_36m"] = _annualize_total_return(sector_frame["forward_return_36m"], months=36)
        sector_frame["prior_high_12m"] = sector_frame["close"].rolling(12, min_periods=6).max().shift(1)
        sector_frame["future_high_12m"] = _future_window_extreme(sector_frame["close"], months=12, mode="max")
        sector_frame["future_low_12m"] = _future_window_extreme(sector_frame["close"], months=12, mode="min")
        sector_frame["higher_high_12m"] = sector_frame["future_high_12m"] > sector_frame["prior_high_12m"]
        sector_frame["future_drawdown_12m"] = sector_frame["future_low_12m"] / sector_frame["close"] - 1.0

        for regime_label, group in sector_frame.groupby("regime_label"):
            expected_12m = group["expected_return_12m"].dropna()
            expected_36m = group["expected_return_36m"].dropna()
            forward_12m = group["forward_return_12m"].dropna()
            forward_36m = group["forward_return_36m"].dropna()
            higher_high = group["higher_high_12m"].dropna()
            drawdown = group["future_drawdown_12m"].dropna()
            sample_months = int(min(len(expected_12m), len(drawdown)))
            if sample_months < 6:
                continue

            win_rate_12m = float((forward_12m > 0.0).mean()) if not forward_12m.empty else 0.0
            win_rate_36m = float((forward_36m > 0.0).mean()) if not forward_36m.empty else 0.0
            higher_high_rate_12m = float(higher_high.mean()) if not higher_high.empty else 0.0
            mean_drawdown_12m = float(drawdown.mean()) if not drawdown.empty else 0.0
            worst_drawdown_12m = float(drawdown.min()) if not drawdown.empty else 0.0
            sample_strength = min(sample_months / 24.0, 1.0)
            consistency_strength = 0.50 * win_rate_12m + 0.20 * win_rate_36m + 0.30 * higher_high_rate_12m
            risk_strength = 1.0 - min(abs(mean_drawdown_12m) / 0.35, 1.0)
            confidence_score = float(np.clip(100.0 * (0.35 * sample_strength + 0.45 * consistency_strength + 0.20 * risk_strength), 0.0, 100.0))
            dominant_quadrant = str(group["quadrant_label"].mode().iloc[0])

            rows.append(
                {
                    "symbol": symbol,
                    "sector_label": sector["label"],
                    "family": sector["family"],
                    "earnings_proxy": sector["earnings_proxy"],
                    "role": sector["role"],
                    "regime_label": str(regime_label),
                    "quadrant_label": dominant_quadrant,
                    "sample_months": sample_months,
                    "expected_return_12m": float(expected_12m.mean()) if not expected_12m.empty else float("nan"),
                    "expected_return_36m": float(expected_36m.mean()) if not expected_36m.empty else float("nan"),
                    "win_rate_12m": win_rate_12m,
                    "win_rate_36m": win_rate_36m,
                    "higher_high_rate_12m": higher_high_rate_12m,
                    "mean_drawdown_12m": mean_drawdown_12m,
                    "worst_drawdown_12m": worst_drawdown_12m,
                    "confidence_score": confidence_score,
                    "confidence_label": _confidence_label(confidence_score),
                    **latest_extension_metrics,
                }
            )

    matrix_frame = pd.DataFrame(rows)
    if matrix_frame.empty:
        return {
            "available": False,
            "message": "Sector ETF histories were present, but there were not enough matching regime observations to build rotation analytics.",
            "missing_symbols": missing_symbols,
        }

    current_regime = str(regime_overview["current"]["regime_label"])
    current_matrix = matrix_frame.loc[matrix_frame["regime_label"] == current_regime].copy()
    if current_matrix.empty:
        current_matrix = matrix_frame.copy()

    current_matrix["rank_return_12m"] = _normalised_rank(current_matrix["expected_return_12m"])
    current_matrix["rank_return_36m"] = _normalised_rank(current_matrix["expected_return_36m"])
    current_matrix["rank_higher_high"] = _normalised_rank(current_matrix["higher_high_rate_12m"])
    current_matrix["rank_drawdown"] = _normalised_rank(current_matrix["mean_drawdown_12m"])
    current_matrix["rank_confidence"] = _normalised_rank(current_matrix["confidence_score"])
    current_matrix["rank_recent_advance_20d"] = _normalised_rank(current_matrix["recent_advance_20d"])
    current_matrix["rank_recent_advance_60d"] = _normalised_rank(current_matrix["recent_advance_60d"])
    current_matrix["rank_drawdown_from_252d_high"] = _normalised_rank(current_matrix["drawdown_from_252d_high"])
    current_matrix["rank_rebound_from_252d_low"] = _normalised_rank(current_matrix["rebound_from_252d_low"])
    current_matrix["overextension_score"] = (
        0.35 * current_matrix["rank_recent_advance_20d"]
        + 0.35 * current_matrix["rank_recent_advance_60d"]
        + 0.15 * current_matrix["rank_drawdown_from_252d_high"]
        + 0.15 * current_matrix["rank_rebound_from_252d_low"]
    )
    current_matrix["runup_penalty"] = 1.0 - 0.30 * np.clip(
        (current_matrix["overextension_score"] - 0.55) / 0.45,
        0.0,
        1.0,
    )
    current_matrix["entry_score_raw"] = (
        0.30 * current_matrix["rank_return_12m"]
        + 0.20 * current_matrix["rank_return_36m"]
        + 0.20 * current_matrix["rank_higher_high"]
        + 0.15 * current_matrix["rank_drawdown"]
        + 0.15 * current_matrix["rank_confidence"]
    )
    current_matrix["entry_score"] = current_matrix["entry_score_raw"]
    current_matrix.loc[current_matrix["expected_return_12m"] < 0.0, "entry_score"] *= 0.70
    current_matrix.loc[current_matrix["expected_return_36m"] < 0.0, "entry_score"] *= 0.85
    current_matrix["entry_score"] *= current_matrix["runup_penalty"]
    current_matrix = current_matrix.sort_values(
        ["entry_score", "runup_penalty", "confidence_score", "expected_return_12m"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)

    allocation_frame = current_matrix.head(5).copy()
    if current_regime in DEFENSIVE_REGIMES and not allocation_frame["symbol"].isin(DEFENSIVE_SECTOR_SYMBOLS).any():
        defensive_candidate = current_matrix.loc[current_matrix["symbol"].isin(DEFENSIVE_SECTOR_SYMBOLS)].head(1)
        if not defensive_candidate.empty:
            allocation_frame = pd.concat([allocation_frame, defensive_candidate], ignore_index=True)
            allocation_frame = allocation_frame.drop_duplicates(subset=["symbol"]).head(5)

    if len(allocation_frame.index) < 4:
        allocation_frame = current_matrix.head(min(4, len(current_matrix.index))).copy()

    weight_base = allocation_frame["entry_score"] - allocation_frame["entry_score"].min() + 0.05
    allocation_frame["sleeve_weight"] = weight_base / weight_base.sum()
    allocation_frame["portfolio_weight"] = allocation_frame["sleeve_weight"] * 0.60
    allocation_frame = allocation_frame.sort_values("portfolio_weight", ascending=False).reset_index(drop=True)
    allocation_symbols = set(allocation_frame["symbol"].tolist())
    current_matrix["recommended"] = current_matrix["symbol"].isin(allocation_symbols)

    top_pick = allocation_frame.iloc[0].to_dict() if not allocation_frame.empty else None
    defensive_pick_frame = allocation_frame.loc[allocation_frame["symbol"].isin(DEFENSIVE_SECTOR_SYMBOLS)]
    defensive_pick = defensive_pick_frame.iloc[0].to_dict() if not defensive_pick_frame.empty else None

    regime_summary = (
        matrix_frame.groupby("regime_label", as_index=False)
        .agg(
            sectors_covered=("symbol", "count"),
            avg_expected_return_12m=("expected_return_12m", "mean"),
            avg_expected_return_36m=("expected_return_36m", "mean"),
            avg_higher_high_rate_12m=("higher_high_rate_12m", "mean"),
            avg_mean_drawdown_12m=("mean_drawdown_12m", "mean"),
            avg_confidence_score=("confidence_score", "mean"),
        )
    )

    top_sector_map = (
        matrix_frame.sort_values(
            ["regime_label", "expected_return_12m", "higher_high_rate_12m"],
            ascending=[True, False, False],
        )
        .groupby("regime_label")
        .head(3)
        .groupby("regime_label")["sector_label"]
        .apply(lambda items: ", ".join(items))
        .to_dict()
    )
    regime_summary["top_sectors"] = regime_summary["regime_label"].map(top_sector_map).fillna("n/a")

    worst_drawdown_regimes = []
    for row in regime_summary.sort_values("avg_mean_drawdown_12m").head(3).itertuples(index=False):
        worst_drawdown_regimes.append(
            {
                "label": str(row.regime_label),
                "drawdown": float(row.avg_mean_drawdown_12m),
                "higher_high": float(row.avg_higher_high_rate_12m),
                "top_sectors": str(row.top_sectors),
            }
        )

    breakout_regimes = []
    for row in regime_summary.sort_values(
        ["avg_higher_high_rate_12m", "avg_expected_return_12m"],
        ascending=[False, False],
    ).head(3).itertuples(index=False):
        breakout_regimes.append(
            {
                "label": str(row.regime_label),
                "drawdown": float(row.avg_mean_drawdown_12m),
                "higher_high": float(row.avg_higher_high_rate_12m),
                "top_sectors": str(row.top_sectors),
            }
        )

    note = (
        "No point-in-time analyst EPS feed exists in this repo. The sector entry calls below therefore use earnings-sensitivity proxies plus realized 1-year and 3-year forward returns from historically similar macro regimes."
    )

    return {
        "available": True,
        "message": "",
        "missing_symbols": missing_symbols,
        "sector_cards": available_cards,
        "current_regime": current_regime,
        "current_matrix": current_matrix,
        "allocation_frame": allocation_frame,
        "matrix_frame": matrix_frame,
        "regime_summary_frame": regime_summary,
        "top_pick": top_pick,
        "defensive_pick": defensive_pick,
        "cash_weight": 0.40,
        "worst_drawdown_regimes": worst_drawdown_regimes,
        "breakout_regimes": breakout_regimes,
        "note": note,
    }


def _render_sector_bucket_section(sector_rotation_view: dict[str, Any]) -> str:
    if not sector_rotation_view.get("available"):
        message = str(sector_rotation_view.get("message") or "Sector rotation analytics are unavailable.")
        return "\n".join(
            [
                '<section id="sector_buckets" class="framework-section">',
                '  <p class="eyebrow">Sector Mapping</p>',
                '  <h2>Equity Types Mapped To ETF Proxies</h2>',
                f'  <p>{html.escape(message)}</p>',
                '</section>',
            ]
        )

    cards = []
    for sector in sector_rotation_view["sector_cards"]:
        cards.append(
            "\n".join(
                [
                    '<article class="rotation-card">',
                    f'  <p class="regime-tag">{html.escape(sector["symbol"])} · {html.escape(sector["family"])} </p>',
                    f'  <h3>{html.escape(sector["label"])}</h3>',
                    f'  <p>{html.escape(sector["earnings_proxy"])}</p>',
                    f'  <p class="regime-subcopy">{html.escape(sector["role"])}</p>',
                    '</article>',
                ]
            )
        )

    return "\n".join(
        [
            '<section id="sector_buckets" class="framework-section">',
            '  <p class="eyebrow">Sector Mapping</p>',
            '  <h2>Equity Types Used For Rotation</h2>',
            '  <p>The sector layer uses liquid ETF proxies for the equity groups you asked about, plus a defensive sleeve for hostile regimes.</p>',
            '  <div class="rotation-grid">',
            "\n".join(cards),
            '  </div>',
            '</section>',
        ]
    )


def _render_sector_rotation_section(sector_rotation_view: dict[str, Any]) -> str:
    if not sector_rotation_view.get("available"):
        message = str(sector_rotation_view.get("message") or "Sector rotation analytics are unavailable.")
        return "\n".join(
            [
                '<section id="sector_rotation" class="framework-section">',
                '  <p class="eyebrow">Rotation Call</p>',
                '  <h2>Current Sector Rotation</h2>',
                f'  <p>{html.escape(message)}</p>',
                '</section>',
            ]
        )

    allocation_frame = sector_rotation_view["allocation_frame"]
    top_pick = sector_rotation_view.get("top_pick")
    defensive_pick = sector_rotation_view.get("defensive_pick")
    note = str(sector_rotation_view.get("note") or "")

    allocation_rows: list[tuple[str, ...]] = []
    for row in allocation_frame.itertuples(index=False):
        allocation_rows.append(
            (
                f"{row.sector_label} ({row.symbol})",
                _format_weight_pct(row.sleeve_weight),
                _format_weight_pct(row.portfolio_weight),
                _format_return_pct(row.recent_advance_20d),
                _format_return_pct(row.recent_advance_60d),
                f"{float(row.runup_penalty):.2f}x",
                _format_return_pct(row.expected_return_12m),
                _format_return_pct(row.expected_return_36m),
                _format_probability_pct(row.higher_high_rate_12m),
                _format_return_pct(row.mean_drawdown_12m),
                f"{row.confidence_label} ({row.confidence_score:.0f})",
            )
        )

    cash_card = "\n".join(
        [
            '<article class="rotation-card rotation-card-highlight">',
            '  <p class="regime-tag">Portfolio rule</p>',
            f'  <h3>Cash {html.escape(_format_weight_pct(sector_rotation_view["cash_weight"]))}</h3>',
            '  <p>The cash sleeve stays fixed so the sector model only decides how the 60% equity risk bucket rotates.</p>',
            '</article>',
        ]
    )

    top_pick_card = ""
    if isinstance(top_pick, dict):
        top_pick_card = "\n".join(
            [
                '<article class="rotation-card rotation-card-highlight">',
                '  <p class="regime-tag">Most probable entry</p>',
                f'  <h3>{html.escape(str(top_pick["sector_label"]))}</h3>',
                f'  <p>{html.escape(str(top_pick["earnings_proxy"]))}</p>',
                f'  <p class="regime-subcopy">Expected 1Y {html.escape(_format_return_pct(float(top_pick["expected_return_12m"])))}, 3Y {html.escape(_format_return_pct(float(top_pick["expected_return_36m"])))}, 20D advance {html.escape(_format_return_pct(float(top_pick["recent_advance_20d"])))}, run-up guardrail {float(top_pick["runup_penalty"]):.2f}x, confidence {html.escape(_confidence_label(float(top_pick["confidence_score"]))) } ({float(top_pick["confidence_score"]):.0f}).</p>',
                '</article>',
            ]
        )

    defensive_card = ""
    if isinstance(defensive_pick, dict):
        defensive_card = "\n".join(
            [
                '<article class="rotation-card">',
                '  <p class="regime-tag">Defensive sleeve</p>',
                f'  <h3>{html.escape(str(defensive_pick["sector_label"]))}</h3>',
                f'  <p>{html.escape(str(defensive_pick["role"]))}</p>',
                f'  <p class="regime-subcopy">Portfolio weight {html.escape(_format_weight_pct(float(defensive_pick["portfolio_weight"])))}, average future drawdown {html.escape(_format_return_pct(float(defensive_pick["mean_drawdown_12m"])))}, confidence {html.escape(_confidence_label(float(defensive_pick["confidence_score"]))) }.</p>',
                '</article>',
            ]
        )

    note_card = "\n".join(
        [
            '<article class="rotation-card">',
            '  <p class="regime-tag">Earnings note</p>',
            f'  <p>{html.escape(note)}</p>',
            '</article>',
        ]
    )

    return "\n".join(
        [
            '<section id="sector_rotation" class="framework-section">',
            '  <p class="eyebrow">Rotation Call</p>',
            '  <h2>Current Sector Rotation For The Active Regime</h2>',
            f'  <p>The active macro regime is {html.escape(str(sector_rotation_view["current_regime"]))}. The equity sleeve below distributes 60% of the portfolio across sectors using historically similar regime months, while keeping 40% in cash. A trailing run-up guardrail now cuts a sector score when the sector has already advanced sharply into the signal date.</p>',
            '  <div class="rotation-grid">',
            cash_card,
            top_pick_card,
            defensive_card,
            note_card,
            '  </div>',
            _render_data_table(
                headers=(
                    'Sector',
                    'Sleeve Weight',
                    'Portfolio Weight',
                    'Advance 20D',
                    'Advance 60D',
                    'Guardrail',
                    'Expected 1Y',
                    'Expected 3Y',
                    'Higher High 12M',
                    'Avg Drawdown 12M',
                    'Confidence',
                ),
                rows=allocation_rows,
            ),
            '</section>',
        ]
    )


def _render_sector_regime_section(sector_rotation_view: dict[str, Any]) -> str:
    if not sector_rotation_view.get("available"):
        return ""

    current_rows: list[tuple[str, ...]] = []
    for row in sector_rotation_view["current_matrix"].itertuples(index=False):
        flag = "Yes" if bool(row.recommended) else "No"
        current_rows.append(
            (
                f"{row.sector_label} ({row.symbol})",
                row.family,
                _format_return_pct(row.recent_advance_20d),
                _format_return_pct(row.recent_advance_60d),
                f"{float(row.runup_penalty):.2f}x",
                _format_return_pct(row.expected_return_12m),
                _format_return_pct(row.expected_return_36m),
                _format_probability_pct(row.higher_high_rate_12m),
                _format_return_pct(row.mean_drawdown_12m),
                f"{row.confidence_label} ({row.confidence_score:.0f})",
                flag,
            )
        )

    regime_summary_rows: list[tuple[str, ...]] = []
    for row in sector_rotation_view["regime_summary_frame"].sort_values("avg_expected_return_12m", ascending=False).itertuples(index=False):
        regime_summary_rows.append(
            (
                str(row.regime_label),
                _format_return_pct(row.avg_expected_return_12m),
                _format_return_pct(row.avg_expected_return_36m),
                _format_probability_pct(row.avg_higher_high_rate_12m),
                _format_return_pct(row.avg_mean_drawdown_12m),
                f"{float(row.avg_confidence_score):.0f}",
                str(row.top_sectors),
            )
        )

    drawdown_cards = []
    for item in sector_rotation_view["worst_drawdown_regimes"]:
        drawdown_cards.append(
            "\n".join(
                [
                    '<article class="rotation-card">',
                    '  <p class="regime-tag">Worst drawdown regime</p>',
                    f'  <h3>{html.escape(item["label"])}</h3>',
                    f'  <p>Average sector drawdown over the next 12 months: {html.escape(_format_return_pct(item["drawdown"]))}. Higher-high hit rate: {html.escape(_format_probability_pct(item["higher_high"]))}.</p>',
                    f'  <p class="regime-subcopy">Historically least-damaged sectors: {html.escape(item["top_sectors"])}.</p>',
                    '</article>',
                ]
            )
        )

    breakout_cards = []
    for item in sector_rotation_view["breakout_regimes"]:
        breakout_cards.append(
            "\n".join(
                [
                    '<article class="rotation-card">',
                    '  <p class="regime-tag">Higher-high regime</p>',
                    f'  <h3>{html.escape(item["label"])}</h3>',
                    f'  <p>Average higher-high hit rate over the next 12 months: {html.escape(_format_probability_pct(item["higher_high"]))}. Average drawdown: {html.escape(_format_return_pct(item["drawdown"]))}.</p>',
                    f'  <p class="regime-subcopy">Most frequent leaders: {html.escape(item["top_sectors"])}.</p>',
                    '</article>',
                ]
            )
        )

    return "\n".join(
        [
            '<section id="sector_regimes" class="framework-section">',
            '  <p class="eyebrow">Sector Evidence</p>',
            '  <h2>Drawdown Regimes, Breakout Regimes, And Sector Evidence</h2>',
            '  <p>The cards below identify which regimes historically produced the broadest sector drawdowns and which ones most often led to higher highs. The tables underneath show the current-regime evidence used for the allocation call.</p>',
            '  <div class="rotation-grid">',
            "\n".join(drawdown_cards + breakout_cards),
            '  </div>',
            _render_data_table(
                headers=(
                    'Sector',
                    'Type',
                    'Advance 20D',
                    'Advance 60D',
                    'Guardrail',
                    'Expected 1Y',
                    'Expected 3Y',
                    'Higher High 12M',
                    'Avg Drawdown 12M',
                    'Confidence',
                    'In 60% Sleeve',
                ),
                rows=current_rows,
            ),
            _render_data_table(
                headers=(
                    'Regime',
                    'Avg 1Y Sector Return',
                    'Avg 3Y Sector Return',
                    'Higher High 12M',
                    'Avg Drawdown 12M',
                    'Avg Confidence',
                    'Most Frequent Leaders',
                ),
                rows=regime_summary_rows,
            ),
            '</section>',
        ]
    )


def _render_chip_list_html(items: tuple[str, ...] | list[str], extra_class: str = "") -> str:
    class_attr = f' class="chip-list {extra_class}"' if extra_class else ' class="chip-list"'
    return f"<ul{class_attr}>{_render_chip_list(tuple(items))}</ul>"


def _render_current_regime_section(regime_overview: dict[str, Any]) -> str:
    current = regime_overview["current"]
    watch_list = "".join(f"<li>{html.escape(item)}</li>" for item in current["watch_items"])
    return "\n".join(
        [
            '<section id="regime_overview" class="framework-section">',
            '  <p class="eyebrow">Current Diagnosis</p>',
            '  <h2>Where The Macro Machine Sits Now</h2>',
            f'  <p>This rule-assisted regime engine compresses the last {REPORT_LOOKBACK_YEARS} years of growth, inflation, credit, volatility, rates, and valuation into a current diagnosis and transition watchlist.</p>',
            '  <div class="regime-grid">',
            '    <article class="regime-card regime-card-primary">',
            f'      <p class="regime-tag"><span class="swatch" style="background:{html.escape(current["regime_color"])}"></span>Current regime</p>',
            f'      <h3>{html.escape(current["regime_label"])}</h3>',
            f'      <p>{html.escape(current["regime_summary"])}</p>',
            f'      <p class="regime-subcopy">Active since {html.escape(current["window_start"])} · current window {html.escape(current["duration"])}.</p>',
            f'      {_render_chip_list_html(current["score_chips"], extra_class="chip-list-tight")}',
            '    </article>',
            '    <article class="regime-card">',
            '      <p class="regime-tag">Dalio-style quadrant</p>',
            f'      <h3>{html.escape(current["quadrant_label"])}</h3>',
            f'      <p class="regime-subcopy">{html.escape(current["quadrant_subtitle"])}</p>',
            f'      <p>{html.escape(current["quadrant_body"])}</p>',
            f'      {_render_chip_list_html(current["market_chips"], extra_class="chip-list-tight")}',
            '    </article>',
            '    <article class="regime-card">',
            '      <p class="regime-tag">Macro read</p>',
            f'      <p>{html.escape(current["macro_narrative"])}</p>',
            f'      <p class="regime-subcopy">{html.escape(current["playbook"])}</p>',
            f'      <p class="regime-subcopy">Main risk: {html.escape(current["risk"])}</p>',
            '    </article>',
            '    <article class="regime-card">',
            '      <p class="regime-tag">Transition watch</p>',
            '      <ul class="plain-list">',
            watch_list,
            '      </ul>',
            '    </article>',
            '  </div>',
            '</section>',
        ]
    )


def _render_quadrant_section(regime_overview: dict[str, Any]) -> str:
    cards = []
    for item in regime_overview["quadrant_cards"]:
        active_class = " quadrant-card-active" if item["active"] else ""
        cards.append(
            "\n".join(
                [
                    f'<article class="quadrant-card{active_class}">',
                    f'  <p class="regime-tag">{int(round(float(item["share"]) * 100.0))}% of sample · {int(item["months"])} months</p>',
                    f'  <h3>{html.escape(str(item["title"]))}</h3>',
                    f'  <p class="regime-subcopy">{html.escape(str(item["subtitle"]))}</p>',
                    f'  <p>{html.escape(str(item["body"]))}</p>',
                    '</article>',
                ]
            )
        )
    return "\n".join(
        [
            '<section id="quadrant_map" class="framework-section">',
            '  <p class="eyebrow">All-Weather Lens</p>',
            '  <h2>Dalio-Style Growth And Inflation Quadrants</h2>',
            '  <p>The quadrant view is a proxy, not a forecast-surprise model. Growth uses production and labor breadth, while inflation uses CPI breadth and recent inflation impulse from the cached feature store.</p>',
            '  <div class="quadrant-grid">',
            "\n".join(cards),
            '  </div>',
            '</section>',
        ]
    )


def _render_regime_taxonomy_section(regime_overview: dict[str, Any]) -> str:
    cards = []
    for item in regime_overview["taxonomy_cards"]:
        active_class = " taxonomy-card-active" if item["active"] else ""
        cards.append(
            "\n".join(
                [
                    f'<article class="taxonomy-card{active_class}">',
                    f'  <p class="regime-tag"><span class="swatch" style="background:{html.escape(str(item["color"]))}"></span>Regime label</p>',
                    f'  <h3>{html.escape(str(item["title"]))}</h3>',
                    f'  <p>{html.escape(str(item["summary"]))}</p>',
                    f'  <p class="regime-subcopy">Playbook: {html.escape(str(item["playbook"]))}</p>',
                    f'  <p class="regime-subcopy">Failure mode: {html.escape(str(item["risk"]))}</p>',
                    '</article>',
                ]
            )
        )
    return "\n".join(
        [
            '<section id="regime_taxonomy" class="framework-section">',
            '  <p class="eyebrow">Regime Taxonomy</p>',
            '  <h2>The Labels This Macro App Watches</h2>',
            '  <div class="taxonomy-grid">',
            "\n".join(cards),
            '  </div>',
            '</section>',
        ]
    )


def _render_regime_timeline_section(regime_overview: dict[str, Any]) -> str:
    timeline_html = "".join(
        f'<span class="timeline-segment" style="width:{segment["width_pct"]:.2f}%; background:{html.escape(segment["color"])}" title="{html.escape(segment["title"])}"></span>'
        for segment in regime_overview["timeline_segments"]
    )
    dominant_html = "".join(
        f'<li><span class="swatch" style="background:{html.escape(item["color"])}"></span>{html.escape(item["label"])} · {int(item["share"])}% of sample</li>'
        for item in regime_overview["dominant_cards"]
    )
    windows_html = []
    for window in regime_overview["window_cards"]:
        current_class = " window-card-current" if window.get("is_current") else ""
        windows_html.append(
            "\n".join(
                [
                    f'<article class="window-card{current_class}">',
                    f'  <p class="regime-tag"><span class="swatch" style="background:{html.escape(window["color"])}"></span>{html.escape(window["label"])} · {html.escape(window["duration"])} </p>',
                    f'  <h3>{html.escape(window["start_display"])} to {html.escape(window["end_display"])}</h3>',
                    f'  <p>{html.escape(window["summary"])}</p>',
                    f'  <p class="regime-subcopy">Dominant quadrant: {html.escape(window["quadrant"])}.</p>',
                    f'  {_render_chip_list_html(window["score_chips"], extra_class="chip-list-tight")}',
                    '</article>',
                ]
            )
        )
    return "\n".join(
        [
            '<section id="regime_timeline" class="framework-section">',
            '  <p class="eyebrow">Twenty-Year Timeline</p>',
            '  <h2>How The Regime Engine Moved Across The Last Twenty Years</h2>',
            '  <p>The timeline compresses monthly regime calls into contiguous windows. The summary below keeps the major phases readable while still grounding them in the underlying macro composites.</p>',
            '  <div class="timeline-shell">',
            '    <div class="timeline-meta">',
            f'      <span>{html.escape(regime_overview["start_display"])}</span>',
            f'      <span>{html.escape(regime_overview["end_display"])}</span>',
            '    </div>',
            f'    <div class="timeline-bar">{timeline_html}</div>',
            '  </div>',
            '  <div class="timeline-legend">',
            '    <p class="regime-tag">Dominant labels over the sample</p>',
            f'    <ul class="legend-list">{dominant_html}</ul>',
            '  </div>',
            '  <div class="window-grid">',
            "\n".join(windows_html),
            '  </div>',
            '</section>',
        ]
    )


def _display_text(value: Any, fallback: str = "n/a") -> str:
    if value is None or pd.isna(value):
        return fallback
    return str(value)


def _coerce_text_items(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item).strip())
    if isinstance(value, str) and value.strip():
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            parsed = value
        if isinstance(parsed, (list, tuple)):
            return tuple(str(item) for item in parsed if str(item).strip())
        if str(parsed).strip() and str(parsed).strip() != "[]":
            return (str(parsed),)
    return ()


def _format_axis_label(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value) >= 100:
        return f"{value:,.1f}"
    return f"{value:,.2f}"


def _date_position(timestamp: pd.Timestamp, start: pd.Timestamp, end: pd.Timestamp) -> float:
    total_days = max((end - start).days, 1)
    offset_days = min(max((timestamp - start).days, 0), total_days)
    return SVG_LEFT_MARGIN + (offset_days / total_days) * SVG_PLOT_WIDTH


def _value_position(value: float, lower: float, upper: float, top: float, height: float) -> float:
    if upper <= lower:
        return top + height / 2.0
    ratio = (value - lower) / (upper - lower)
    return top + height - ratio * height


def _series_bounds(series: pd.Series) -> tuple[float, float]:
    minimum = float(series.min())
    maximum = float(series.max())
    if minimum == maximum:
        pad = abs(minimum) * 0.05 or 1.0
        return minimum - pad, maximum + pad
    pad = (maximum - minimum) * 0.08
    return minimum - pad, maximum + pad


def _series_path(series: pd.Series, lower: float, upper: float, top: float, height: float, start: pd.Timestamp, end: pd.Timestamp) -> str:
    commands: list[str] = []
    for index, value in series.items():
        x_pos = _date_position(pd.Timestamp(index), start, end)
        y_pos = _value_position(float(value), lower, upper, top, height)
        command = "M" if not commands else "L"
        commands.append(f"{command}{x_pos:.2f},{y_pos:.2f}")
    return " ".join(commands)


def _render_chip_list(items: tuple[str, ...] | list[str]) -> str:
    if not items:
        return ""
    return "".join(f'<li>{html.escape(item)}</li>' for item in items)


def _render_detail_block(label: str, items: tuple[str, ...] | list[str]) -> str:
    if not items:
        return ""
    return "\n".join(
        [
            '<div class="detail-block">',
            f'  <p class="detail-label">{html.escape(label)}</p>',
            f'  <ul class="chip-list">{_render_chip_list(items)}</ul>',
            '</div>',
        ]
    )


def _render_framework_grid(
    title: str,
    eyebrow: str,
    items: tuple[dict[str, str | tuple[str, ...]], ...],
    card_class: str,
) -> str:
    cards: list[str] = []
    for item in items:
        bullet_list = "".join(f'<li>{html.escape(point)}</li>' for point in item["items"])
        cards.append(
            "\n".join(
                [
                    f'<article class="{card_class}">',
                    f'  <h3>{html.escape(str(item["title"]))}</h3>',
                    f'  <p>{html.escape(str(item["summary"]))}</p>' if "summary" in item else f'  <p>{html.escape(str(item["body"]))}</p>',
                    f'  <ul class="plain-list">{bullet_list}</ul>' if "items" in item else '',
                    '</article>',
                ]
            )
        )
    return "\n".join(
        [
            '<section class="framework-section">',
            f'  <p class="eyebrow">{html.escape(eyebrow)}</p>',
            f'  <h2>{html.escape(title)}</h2>',
            f'  <div class="framework-grid {card_class}-grid">',
            "\n".join(cards),
            '  </div>',
            '</section>',
        ]
    )


def _render_principles_section() -> str:
    cards = []
    for item in MACRO_DESIGN_PRINCIPLES:
        cards.append(
            "\n".join(
                [
                    '<article class="principle-card">',
                    f'  <h3>{html.escape(item["title"])}</h3>',
                    f'  <p>{html.escape(item["body"])}</p>',
                    '</article>',
                ]
            )
        )
    return "\n".join(
        [
            '<section class="framework-section">',
            '  <p class="eyebrow">Interpretation Guardrails</p>',
            '  <h2>How These Variables Should Be Read</h2>',
            '  <div class="framework-grid principle-grid">',
            "\n".join(cards),
            '  </div>',
            '</section>',
        ]
    )


def _render_expansions_section() -> str:
    cards = []
    for item in MACRO_RECOMMENDED_EXPANSIONS:
        cards.append(
            "\n".join(
                [
                    '<article class="framework-card">',
                    f'  <h3>{html.escape(str(item["title"]))}</h3>',
                    f'  <ul class="plain-list">{"".join(f"<li>{html.escape(point)}</li>" for point in item["items"])} </ul>',
                    '</article>',
                ]
            )
        )
    return "\n".join(
        [
            '<section class="framework-section">',
            '  <p class="eyebrow">Engineering Blueprint</p>',
            '  <h2>Current Inputs Versus Recommended Extensions</h2>',
            '  <div class="formula-strip">',
            '    <pre class="formula-card">expected_daily_vol = spot_vix / 100 / sqrt(252)</pre>',
            '    <pre class="formula-card">vix_adjusted_move = return_1d / expected_daily_vol</pre>',
            '    <pre class="formula-card">crash_risk_score = valuation_fragility_score * volatility_stress_score * rate_shock_score</pre>',
            '  </div>',
            '  <div class="framework-grid framework-card-grid">',
            "\n".join(cards),
            '  </div>',
            '</section>',
        ]
    )


def _render_interactions_section() -> str:
    items = "".join(f'<li>{html.escape(item)}</li>' for item in MACRO_INTERACTION_LIBRARY)
    return "\n".join(
        [
            '<section class="framework-section compact-section">',
            '  <p class="eyebrow">Interaction Library</p>',
            '  <h2>Signals That Matter More Than Raw Levels</h2>',
            '  <ul class="plain-list two-column-list">',
            items,
            '  </ul>',
            '</section>',
        ]
    )


def _render_scenarios_section() -> str:
    cards = []
    for item in MACRO_SCENARIO_PLAYBOOK:
        cards.append(
            "\n".join(
                [
                    '<article class="scenario-card">',
                    f'  <h3>{html.escape(item["title"])}</h3>',
                    f'  <p>{html.escape(item["body"])}</p>',
                    '</article>',
                ]
            )
        )
    return "\n".join(
        [
            '<section class="framework-section">',
            '  <p class="eyebrow">Scenario Playbook</p>',
            '  <h2>How The Macro Stack Should Influence Trading Decisions</h2>',
            '  <div class="framework-grid scenario-grid">',
            "\n".join(cards),
            '  </div>',
            '</section>',
        ]
    )


def _series_card(feature: str, inventory: pd.DataFrame) -> str:
    row = inventory.loc[feature] if feature in inventory.index else pd.Series(dtype="object")
    detail = MACRO_SERIES_DETAILS.get(feature, {})
    units_value = detail.get("units_override") or row.get("units")
    name = html.escape(_display_text(detail.get("display_name") or row.get("name") or feature))
    brief = html.escape(MACRO_SERIES_BRIEFS.get(feature, "Macro context series used by the model."))
    role = html.escape(str(detail.get("role") or "Macro context input"))
    latest = _format_value(row.get("latest_value"), units_value if isinstance(units_value, str) else None)
    units = html.escape(_display_text(units_value))
    history_start = html.escape(_display_text(row.get("history_start")))
    history_end = html.escape(_display_text(row.get("history_end")))
    frequency = html.escape(_display_text(row.get("frequency")))
    source_html = _render_source_link(row.get("source"), row.get("source_url"))
    coverage_ratio = row.get("coverage_ratio")
    if pd.isna(coverage_ratio):
        coverage_text = "n/a"
    else:
        coverage_text = f"{float(coverage_ratio) * 100:.1f}%"
    engineering_items = tuple(str(item) for item in detail.get("engineering", ()))
    interaction_items = tuple(str(item) for item in detail.get("interactions", ()))
    note_items = _coerce_text_items(detail.get("data_notes") or row.get("notes"))

    return "\n".join(
        [
            '<article class="series-card">',
            f'  <p class="series-key">{html.escape(feature)}</p>',
            f"  <h3>{name}</h3>",
            f'  <p class="series-brief">{brief}</p>',
            '  <dl class="series-meta">',
            f"    <div><dt>Model role</dt><dd>{role}</dd></div>",
            f"    <div><dt>Latest</dt><dd>{html.escape(latest)}</dd></div>",
            f"    <div><dt>Units</dt><dd>{units}</dd></div>",
            f"    <div><dt>History</dt><dd>{history_start} to {history_end}</dd></div>",
            f"    <div><dt>Frequency</dt><dd>{frequency}</dd></div>",
            f"    <div><dt>Coverage</dt><dd>{coverage_text}</dd></div>",
            f"    <div><dt>Source</dt><dd>{source_html}</dd></div>",
            "  </dl>",
            _render_detail_block("Data Notes", note_items),
            _render_detail_block("Engineer Next", engineering_items),
            _render_detail_block("Watch With", interaction_items),
            "</article>",
        ]
    )


def _plot_group(
    frame: pd.DataFrame,
    inventory: pd.DataFrame,
    group: dict[str, str | tuple[str, ...]],
    output_path: Path,
) -> Path | None:
    features = [feature for feature in group["series"] if feature in frame.columns]
    if not features:
        return None

    first_date = pd.Timestamp(frame.index.min())
    last_date = pd.Timestamp(frame.index.max())
    total_height = SVG_TOP_MARGIN + len(features) * SVG_ROW_HEIGHT + (len(features) - 1) * SVG_ROW_GAP + SVG_BOTTOM_MARGIN

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{total_height}" viewBox="0 0 {SVG_WIDTH} {total_height}" role="img" aria-labelledby="title">',
        f'  <title>{html.escape(str(group["title"]))}</title>',
        f'  <rect x="0" y="0" width="{SVG_WIDTH}" height="{total_height}" fill="{PAGE_BACKGROUND}" />',
        f'  <text x="{SVG_LEFT_MARGIN}" y="24" fill="{TEXT_COLOR}" font-size="24" font-family="Georgia, serif" font-weight="700">{html.escape(str(group["title"]))}</text>',
    ]

    for index, feature in enumerate(features):
        series = frame[feature].dropna()
        if series.empty:
            continue

        top = SVG_TOP_MARGIN + index * (SVG_ROW_HEIGHT + SVG_ROW_GAP)
        inner_top = top + 24
        inner_height = SVG_ROW_HEIGHT - 40
        lower, upper = _series_bounds(series)
        row = inventory.loc[feature] if feature in inventory.index else pd.Series(dtype="object")
        detail = MACRO_SERIES_DETAILS.get(feature, {})
        units_value = detail.get("units_override") or row.get("units")
        display_name = html.escape(_display_text(detail.get("display_name") or row.get("name") or feature, fallback=feature))
        latest = html.escape(_format_value(row.get("latest_value"), units_value if isinstance(units_value, str) else None))

        parts.append(
            f'  <rect x="{SVG_LEFT_MARGIN}" y="{top}" width="{SVG_PLOT_WIDTH}" height="{SVG_ROW_HEIGHT}" rx="18" fill="{PANEL_BACKGROUND}" stroke="{GRID_COLOR}" />'
        )

        for regime in MACRO_REGIME_WINDOWS:
            regime_start = pd.Timestamp(regime["start"])
            regime_end = pd.Timestamp(regime["end"])
            x_start = _date_position(regime_start, first_date, last_date)
            x_end = _date_position(regime_end, first_date, last_date)
            width = max(x_end - x_start, 2.0)
            parts.append(
                f'  <rect x="{x_start:.2f}" y="{inner_top:.2f}" width="{width:.2f}" height="{inner_height:.2f}" fill="{REGIME_FILL}" opacity="0.28" />'
            )

        grid_values = [lower + step * (upper - lower) / 3.0 for step in range(4)]
        for grid_value in grid_values:
            y_pos = _value_position(grid_value, lower, upper, inner_top, inner_height)
            parts.append(
                f'  <line x1="{SVG_LEFT_MARGIN}" y1="{y_pos:.2f}" x2="{SVG_LEFT_MARGIN + SVG_PLOT_WIDTH}" y2="{y_pos:.2f}" stroke="{GRID_COLOR}" stroke-width="1" opacity="0.65" />'
            )

        path_data = _series_path(series, lower, upper, inner_top, inner_height, first_date, last_date)
        color = ACCENT_COLORS[index % len(ACCENT_COLORS)]
        parts.extend(
            [
                f'  <text x="{SVG_LEFT_MARGIN + 18}" y="{top + 20}" fill="{TEXT_COLOR}" font-size="16" font-family="Georgia, serif" font-weight="700">{display_name}</text>',
                f'  <text x="{SVG_LEFT_MARGIN + SVG_PLOT_WIDTH - 18}" y="{top + 20}" fill="{TEXT_COLOR}" font-size="12" font-family="Georgia, serif" text-anchor="end">Latest {latest}</text>',
                f'  <text x="{SVG_LEFT_MARGIN - 12}" y="{inner_top + 4:.2f}" fill="{MUTED_TEXT_COLOR}" font-size="11" font-family="Georgia, serif" text-anchor="end">{html.escape(_format_axis_label(upper))}</text>',
                f'  <text x="{SVG_LEFT_MARGIN - 12}" y="{inner_top + inner_height + 4:.2f}" fill="{MUTED_TEXT_COLOR}" font-size="11" font-family="Georgia, serif" text-anchor="end">{html.escape(_format_axis_label(lower))}</text>',
                f'  <path d="{path_data}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />',
            ]
        )

    start_year = first_date.year - (first_date.year % 4)
    end_year = last_date.year + (4 - last_date.year % 4)
    axis_y = total_height - 26
    parts.append(
        f'  <line x1="{SVG_LEFT_MARGIN}" y1="{axis_y}" x2="{SVG_LEFT_MARGIN + SVG_PLOT_WIDTH}" y2="{axis_y}" stroke="{GRID_COLOR}" stroke-width="1.2" />'
    )
    for year in range(start_year, end_year + 1, 4):
        tick_date = pd.Timestamp(year=year, month=1, day=1)
        if tick_date < first_date or tick_date > last_date:
            continue
        x_pos = _date_position(tick_date, first_date, last_date)
        parts.append(
            f'  <line x1="{x_pos:.2f}" y1="{axis_y}" x2="{x_pos:.2f}" y2="{axis_y + 8}" stroke="{GRID_COLOR}" stroke-width="1.2" />'
        )
        parts.append(
            f'  <text x="{x_pos:.2f}" y="{axis_y + 24}" fill="{MUTED_TEXT_COLOR}" font-size="11" font-family="Georgia, serif" text-anchor="middle">{year}</text>'
        )

    parts.append("</svg>")
    output_path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return output_path


def _render_html(
    inventory: pd.DataFrame,
    generated_at: str,
    group_plot_paths: dict[str, str],
    regime_overview: dict[str, Any],
    sector_rotation_view: dict[str, Any],
) -> str:
    group_sections: list[str] = []
    toc_links: list[str] = [
        '<a href="#regime_overview">Current Diagnosis</a>',
        '<a href="#quadrant_map">Growth And Inflation Quadrants</a>',
        '<a href="#regime_taxonomy">Regime Taxonomy</a>',
        '<a href="#regime_timeline">Twenty-Year Timeline</a>',
        '<a href="#sector_buckets">Sector Buckets</a>',
        '<a href="#sector_rotation">Current Rotation</a>',
        '<a href="#sector_regimes">Sector Evidence</a>',
    ]
    regime_text = " | ".join(
        f"{window['label']}: {window['start'][:4]}-{window['end'][:4]}" for window in MACRO_REGIME_WINDOWS
    )
    architecture_section = _render_framework_grid(
        title="A Better Macro Architecture",
        eyebrow="System Design",
        items=MACRO_ARCHITECTURE_LAYERS,
        card_class="framework-card",
    )
    principles_section = _render_principles_section()
    expansions_section = _render_expansions_section()
    interactions_section = _render_interactions_section()
    scenarios_section = _render_scenarios_section()
    current_regime_section = _render_current_regime_section(regime_overview)
    quadrant_section = _render_quadrant_section(regime_overview)
    taxonomy_section = _render_regime_taxonomy_section(regime_overview)
    regime_timeline_section = _render_regime_timeline_section(regime_overview)
    sector_bucket_section = _render_sector_bucket_section(sector_rotation_view)
    sector_rotation_section = _render_sector_rotation_section(sector_rotation_view)
    sector_regime_section = _render_sector_regime_section(sector_rotation_view)

    for group in MACRO_REPORT_GROUPS:
        slug = str(group["slug"])
        title = html.escape(str(group["title"]))
        summary = html.escape(str(group["summary"]))
        plot_path = group_plot_paths.get(slug)
        features = [feature for feature in group["series"] if feature in inventory.index]
        if not features or plot_path is None:
            continue

        toc_links.append(f'<a href="#{slug}">{title}</a>')
        cards_html = "\n".join(_series_card(feature, inventory) for feature in features)
        group_sections.append(
            "\n".join(
                [
                    f'<section id="{slug}" class="group-section">',
                    '  <div class="section-copy">',
                    f'    <p class="eyebrow">Macro Channel</p>',
                    f"    <h2>{title}</h2>",
                    f"    <p>{summary}</p>",
                    "  </div>",
                    '  <figure class="plot-frame">',
                    f'    <img src="{html.escape(plot_path)}" alt="{title} timeline plots" />',
                    "  </figure>",
                    '  <div class="series-grid">',
                    cards_html,
                    "  </div>",
                    "</section>",
                ]
            )
        )

    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Macro Regime Atlas</title>
  <style>
    :root {{
      --bg: {PAGE_BACKGROUND};
      --panel: {PANEL_BACKGROUND};
      --ink: {TEXT_COLOR};
      --muted: {MUTED_TEXT_COLOR};
      --line: {GRID_COLOR};
      --accent: #7a3e2b;
      --accent-soft: #e9dcc8;
      --shadow: 0 20px 45px rgba(27, 36, 48, 0.08);
      --radius: 18px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
      background:
        radial-gradient(circle at top left, rgba(122, 62, 43, 0.10), transparent 28%),
        radial-gradient(circle at top right, rgba(15, 76, 92, 0.08), transparent 24%),
        var(--bg);
      color: var(--ink);
      line-height: 1.6;
    }}
    a {{ color: #0f4c5c; }}
    .page {{ max-width: 1220px; margin: 0 auto; padding: 48px 24px 80px; }}
    .hero {{
      background: linear-gradient(135deg, rgba(255, 253, 248, 0.96), rgba(247, 242, 232, 0.96));
      border: 1px solid rgba(213, 207, 197, 0.9);
      border-radius: 28px;
      box-shadow: var(--shadow);
      padding: 40px;
      margin-bottom: 28px;
    }}
    .eyebrow {{
      margin: 0 0 10px;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      font-size: 0.78rem;
      color: var(--accent);
    }}
    h1, h2, h3 {{ line-height: 1.15; margin: 0; }}
    h1 {{ font-size: clamp(2.4rem, 4vw, 4.2rem); max-width: 12ch; }}
    h2 {{ font-size: clamp(1.5rem, 2.5vw, 2.2rem); margin-bottom: 8px; }}
    h3 {{ font-size: 1.15rem; margin-bottom: 10px; }}
    .hero p {{ max-width: 68ch; color: var(--muted); font-size: 1.02rem; }}
    .hero-meta {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 24px; }}
    .hero-meta span {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 9px 14px;
      border-radius: 999px;
      background: rgba(233, 220, 200, 0.75);
      color: var(--ink);
      border: 1px solid rgba(122, 62, 43, 0.12);
      font-size: 0.92rem;
    }}
    .toc {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 12px;
      margin-bottom: 28px;
    }}
    .toc a {{
      text-decoration: none;
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid rgba(213, 207, 197, 0.9);
      background: rgba(255, 253, 248, 0.8);
      color: var(--ink);
      box-shadow: 0 10px 24px rgba(27, 36, 48, 0.04);
    }}
    .methodology {{
      background: rgba(255, 253, 248, 0.88);
      border-radius: 22px;
      border: 1px solid rgba(213, 207, 197, 0.9);
      padding: 26px 28px;
      margin-bottom: 28px;
    }}
        .rotation-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 16px;
            margin-top: 18px;
        }}
        .rotation-card {{
            background: var(--panel);
            border-radius: 18px;
            border: 1px solid rgba(213, 207, 197, 0.95);
            padding: 18px;
            min-height: 100%;
        }}
        .rotation-card-highlight {{
            background: linear-gradient(180deg, rgba(244, 237, 225, 0.92), rgba(255, 253, 248, 0.94));
        }}
        .table-shell {{
            margin-top: 18px;
            overflow-x: auto;
            border-radius: 18px;
            border: 1px solid rgba(213, 207, 197, 0.9);
            background: rgba(255, 253, 248, 0.88);
        }}
        .data-table {{
            width: 100%;
            border-collapse: collapse;
            min-width: 780px;
        }}
        .data-table th,
        .data-table td {{
            padding: 12px 14px;
            text-align: left;
            border-bottom: 1px solid rgba(213, 207, 197, 0.65);
            vertical-align: top;
        }}
        .data-table th {{
            background: rgba(244, 237, 225, 0.82);
            color: var(--ink);
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }}
        .data-table tr:last-child td {{ border-bottom: none; }}
        .regime-grid, .quadrant-grid, .taxonomy-grid, .window-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 16px;
            margin-top: 18px;
        }}
        .regime-card, .quadrant-card, .taxonomy-card, .window-card {{
            background: var(--panel);
            border-radius: 18px;
            border: 1px solid rgba(213, 207, 197, 0.95);
            padding: 18px;
            min-height: 100%;
        }}
        .regime-card-primary {{
            background: linear-gradient(180deg, rgba(244, 237, 225, 0.92), rgba(255, 253, 248, 0.94));
        }}
        .quadrant-card-active, .taxonomy-card-active, .window-card-current {{
            border-color: rgba(122, 62, 43, 0.35);
            box-shadow: 0 12px 28px rgba(27, 36, 48, 0.07);
        }}
        .regime-tag {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin: 0 0 10px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.74rem;
            color: var(--accent);
        }}
        .swatch {{
            width: 10px;
            height: 10px;
            border-radius: 999px;
            display: inline-block;
            flex: 0 0 auto;
        }}
        .regime-subcopy {{ margin-top: 10px; color: var(--muted); }}
        .chip-list-tight {{ margin-top: 14px; }}
        .timeline-shell {{
            margin-top: 22px;
            padding: 18px;
            border-radius: 18px;
            background: rgba(247, 242, 232, 0.78);
            border: 1px solid rgba(213, 207, 197, 0.85);
        }}
        .timeline-meta {{
            display: flex;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 10px;
            color: var(--muted);
            font-size: 0.9rem;
        }}
        .timeline-bar {{
            display: flex;
            width: 100%;
            min-height: 28px;
            border-radius: 999px;
            overflow: hidden;
            background: rgba(213, 207, 197, 0.55);
        }}
        .timeline-segment {{ min-height: 28px; }}
        .timeline-legend {{ margin-top: 18px; }}
        .legend-list {{
            list-style: none;
            padding: 0;
            margin: 12px 0 0;
            display: flex;
            flex-wrap: wrap;
            gap: 12px 18px;
            color: var(--muted);
        }}
        .legend-list li {{ display: inline-flex; align-items: center; gap: 8px; }}
        .framework-section {{
            background: rgba(255, 253, 248, 0.88);
            border-radius: 22px;
            border: 1px solid rgba(213, 207, 197, 0.9);
            padding: 26px 28px;
            margin-bottom: 28px;
        }}
        .compact-section {{ padding-bottom: 20px; }}
        .framework-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 16px;
            margin-top: 18px;
        }}
        .framework-card, .principle-card, .scenario-card {{
            background: var(--panel);
            border-radius: 18px;
            border: 1px solid rgba(213, 207, 197, 0.95);
            padding: 18px;
            min-height: 100%;
        }}
        .framework-card p, .principle-card p, .scenario-card p {{ margin: 10px 0 0; color: var(--muted); }}
        .plain-list {{ margin: 12px 0 0; padding-left: 18px; color: var(--muted); }}
        .plain-list li + li {{ margin-top: 8px; }}
        .two-column-list {{ columns: 2; column-gap: 28px; }}
        .formula-strip {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 12px;
            margin-top: 18px;
            margin-bottom: 18px;
        }}
        .formula-card {{
            margin: 0;
            padding: 14px 16px;
            background: #f4ede1;
            border: 1px solid rgba(122, 62, 43, 0.14);
            border-radius: 14px;
            overflow-x: auto;
            color: var(--ink);
            font-size: 0.9rem;
            font-family: "SFMono-Regular", Menlo, Consolas, monospace;
        }}
    .group-section {{
      margin-bottom: 34px;
      padding: 28px;
      border-radius: 24px;
      background: rgba(255, 253, 248, 0.9);
      border: 1px solid rgba(213, 207, 197, 0.92);
      box-shadow: var(--shadow);
    }}
    .section-copy p {{ margin-top: 0; color: var(--muted); max-width: 72ch; }}
    .plot-frame {{
      margin: 24px 0 22px;
      padding: 16px;
      background: rgba(247, 242, 232, 0.75);
      border-radius: 18px;
      border: 1px solid rgba(213, 207, 197, 0.85);
    }}
    .plot-frame img {{ display: block; width: 100%; border-radius: 10px; }}
    .series-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; }}
    .series-card {{
      background: var(--panel);
      border-radius: var(--radius);
      border: 1px solid rgba(213, 207, 197, 0.95);
      padding: 18px 18px 16px;
      min-height: 100%;
    }}
    .series-key {{
      margin: 0 0 8px;
      font-family: "SFMono-Regular", Menlo, Consolas, monospace;
      font-size: 0.75rem;
      letter-spacing: 0.04em;
      color: var(--accent);
    }}
    .series-brief {{ margin: 0 0 16px; color: var(--muted); }}
    .series-meta {{ margin: 0; display: grid; gap: 10px; }}
    .series-meta div {{
      display: grid;
      grid-template-columns: 82px 1fr;
      gap: 8px;
      align-items: start;
      padding-top: 10px;
      border-top: 1px solid rgba(213, 207, 197, 0.6);
    }}
    .series-meta dt {{ font-weight: 600; color: var(--ink); }}
    .series-meta dd {{ margin: 0; color: var(--muted); }}
        .detail-block {{ margin-top: 14px; }}
        .detail-label {{
            margin: 0 0 8px;
            font-size: 0.76rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--accent);
        }}
        .chip-list {{
            list-style: none;
            margin: 0;
            padding: 0;
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .chip-list li {{
            padding: 7px 10px;
            border-radius: 999px;
            background: rgba(233, 220, 200, 0.55);
            border: 1px solid rgba(122, 62, 43, 0.1);
            color: var(--ink);
            font-size: 0.84rem;
            line-height: 1.3;
        }}
    @media (max-width: 720px) {{
      .page {{ padding: 24px 16px 56px; }}
            .hero, .methodology, .framework-section, .group-section {{ padding: 22px; }}
      .series-meta div {{ grid-template-columns: 1fr; }}
            .two-column-list {{ columns: 1; }}
    }}
  </style>
</head>
<body>
  <main class=\"page\">
    <section class=\"hero\">
    <p class=\"eyebrow\">Macro Regime Atlas</p>
    <h1>Twenty Years Of Macro Regimes</h1>
                <p>This report shifts the macro app from a flat variable inventory toward a Dalio-style regime map: growth and inflation quadrants, stress overlays, and the specific model inputs that matter inside each environment. The goal is to show how the macro machine has moved across the last twenty years, not just list the features beside price action.</p>
      <div class=\"hero-meta\">
        <span>{generated_at}</span>
        <span>{len(inventory.index)} base macro series</span>
            <span>Lookback window: {html.escape(regime_overview['start_display'])} to {html.escape(regime_overview['end_display'])}</span>
            <span>Current regime: {html.escape(regime_overview['current']['regime_label'])}</span>
      </div>
    </section>

    <nav class=\"toc\">
      {' '.join(toc_links)}
    </nav>

    <section class=\"methodology\">
      <p class=\"eyebrow\">Method</p>
        <p>The report rebuilds the macro feature store from raw inputs when it runs, then aligns each selected series to the daily market frame the same way the models consume it. For the regime engine, the page compresses the last {REPORT_LOOKBACK_YEARS} years into monthly growth, inflation, credit, volatility, rate-shock, and valuation composites. Those composites drive a rule-assisted quadrant map and regime labels. Crisis windows are still shaded on the raw macro charts for fast cross-cycle comparison: {html.escape(regime_text)}.</p>
    </section>

        {current_regime_section}

        {quadrant_section}

        {taxonomy_section}

        {regime_timeline_section}

        {sector_bucket_section}

        {sector_rotation_section}

        {sector_regime_section}

        {architecture_section}

        {principles_section}

        {expansions_section}

        {interactions_section}

        {scenarios_section}

    {' '.join(group_sections)}
  </main>
</body>
</html>
"""


def generate_macro_report(
    output_dir: str | Path,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    inventory = load_model_macro_inventory(project_root=root)
    frame = load_model_macro_frame(project_root=root)
    report_start = frame.index.max() - pd.DateOffset(years=REPORT_LOOKBACK_YEARS)
    report_frame = frame.loc[frame.index >= report_start].copy()
    regime_overview = _build_regime_overview(frame=frame, lookback_years=REPORT_LOOKBACK_YEARS)
    sector_rotation_view = _build_sector_rotation_view(project_root=root, regime_overview=regime_overview)

    report_dir = Path(output_dir)
    if not report_dir.is_absolute():
        report_dir = root / report_dir
    plots_dir = report_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    filtered_inventory = inventory.loc[[column for column in report_frame.columns if column in inventory.index]].copy()
    filtered_inventory.to_csv(report_dir / "model_macro_inventory.csv", index=False)

    sector_matrix_path = report_dir / "sector_regime_matrix.csv"
    current_sector_path = report_dir / "sector_current_regime.csv"
    sector_allocation_path = report_dir / "sector_allocation.json"
    if sector_rotation_view.get("available"):
        sector_rotation_view["matrix_frame"].to_csv(sector_matrix_path, index=False)
        sector_rotation_view["current_matrix"].to_csv(current_sector_path, index=False)
        allocation_records = json.loads(sector_rotation_view["allocation_frame"].to_json(orient="records"))
        top_pick = allocation_records[0] if allocation_records else None
        allocation_payload = {
            "cash_weight": float(sector_rotation_view["cash_weight"]),
            "current_regime": str(sector_rotation_view["current_regime"]),
            "note": str(sector_rotation_view["note"]),
            "top_pick": top_pick,
            "allocation": allocation_records,
        }
        sector_allocation_path.write_text(json.dumps(allocation_payload, indent=2), encoding="utf-8")

    group_plot_paths: dict[str, str] = {}
    for group in MACRO_REPORT_GROUPS:
        slug = str(group["slug"])
        plot_path = plots_dir / f"{slug}.svg"
        saved_path = _plot_group(frame=report_frame, inventory=filtered_inventory, group=group, output_path=plot_path)
        if saved_path is not None:
            group_plot_paths[slug] = str(saved_path.relative_to(report_dir))

    generated_at = datetime.now(UTC).strftime("Generated %Y-%m-%d %H:%M UTC")
    html_text = _render_html(
        inventory=filtered_inventory,
        generated_at=generated_at,
        group_plot_paths=group_plot_paths,
        regime_overview=regime_overview,
        sector_rotation_view=sector_rotation_view,
    )
    report_path = report_dir / "index.html"
    report_path.write_text(html_text, encoding="utf-8")

    return {
        "report": str(report_path),
        "plots_dir": str(plots_dir),
        "inventory": str(report_dir / "model_macro_inventory.csv"),
        "sector_matrix": str(sector_matrix_path) if sector_matrix_path.exists() else None,
        "sector_current": str(current_sector_path) if current_sector_path.exists() else None,
        "sector_allocation": str(sector_allocation_path) if sector_allocation_path.exists() else None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a grouped macro report for the model context variables.")
    parser.add_argument(
        "--output-dir",
        default="outputs/macro_report",
        help="Directory where the HTML document and grouped timeline plots will be written.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    generated = generate_macro_report(output_dir=args.output_dir)
    print(json.dumps(generated, indent=2))


if __name__ == "__main__":
    main()