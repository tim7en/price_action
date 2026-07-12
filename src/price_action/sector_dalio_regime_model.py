from __future__ import annotations

import argparse
import html
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, precision_score, recall_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .data import resolve_project_root
from .momentum_oscillator import _fig_b64, _vintage_ax, _vintage_fig, momentum_oscillator
from .regime_analysis import dalio_quadrant, dalio_signals, fit_regime_model, load_macro_panel
from .sector_trend_study import (
    DEFAULT_FAST,
    DEFAULT_SLOW,
    analyse_crosses,
    build_sector_indices,
    load_sector_fundamentals,
    market_health,
)

DEFAULT_OUTPUT_DIR = Path("outputs") / "sector_dalio_regime_model"
DEFAULT_HOLDOUT_START = "2025-01-01"
DEFAULT_TRAIN_YEARS = 8
DEFAULT_LABEL_HORIZON = 6
DEFAULT_TOP_N = 3
DEFAULT_MIN_FEATURE_COVERAGE = 0.65
DAILY_FAST = 50
DAILY_SLOW = 200
DAILY_FORWARD_HORIZONS = (21, 63, 126, 252)

PAPER = "#f4ecd3"
PAGE = "#eadcb8"
GRID_MAJOR = "#c8a24b"
GRID_MINOR = "#dbc17b"
INK = "#2e2417"
INK_MUTED = "#6b5d40"
INK_NAVY = "#2e62a8"
INK_RED = "#b53517"
INK_GREEN = "#1f7a52"
INK_AMBER = "#c07f1f"

FUNDAMENTAL_SECTOR_MAP = {
    "COMMUNICATION SERVICES": "Communication Svcs",
    "CONSUMER DISCRETIONARY": "Consumer Cyclical",
    "CONSUMER STAPLES": "Consumer Defensive",
    "ENERGY": "Energy",
    "FINANCIALS": "Financials",
    "HEALTHCARE": "Health Care",
    "INDUSTRIALS": "Industrials",
    "MATERIALS": "Materials",
    "REAL ESTATE": "Real Estate",
    "TECHNOLOGY": "Technology",
    "UTILITIES": "Utilities",
}

SECTOR_ETF_MAP = {
    "Communication Svcs": "XLC",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Technology": "XLK",
    "Utilities": "XLU",
}

EARNINGS_FUNDAMENTAL_FEATURES = [
    "cap_weighted_surprise_pct_lag1",
    "cap_weighted_surprise_pct_lag1_change",
    "beat_rate_lag1",
    "beat_rate_lag1_change",
    "cap_weighted_quarterly_eps_yoy_pct_lag1",
    "cap_weighted_quarterly_eps_yoy_pct_lag1_change",
]

STRUCTURE_DIAGNOSTIC_FEATURES = [
    "market_cap_share",
    "turnover_proxy",
    "market_cap_proxy_total_qoq_pct",
    "dollar_volume_total_qoq_pct",
]

SECTOR_FACTOR_PANEL_FEATURES = EARNINGS_FUNDAMENTAL_FEATURES + STRUCTURE_DIAGNOSTIC_FEATURES

EXCLUDED_PREDICTIVE_FEATURE_PARTS = (
    "symbol_count",
    "constituent_count",
    "coverage_count",
    "monthly_observations",
    "observation_count",
    "_n_members",
    "market_cap_proxy",
    "market_cap_share",
    "turnover",
    "dollar_volume",
    "volume_total",
)

TARGET_COLUMNS = {
    "target_leader",
    "leader_rank_pct",
    "fwd_1m",
    "fwd_3m",
    "fwd_6m",
    "fwd_12m",
    "fwd_1m_broad",
    "fwd_3m_broad",
    "fwd_6m_broad",
    "fwd_12m_broad",
    "fwd_1m_excess",
    "fwd_3m_excess",
    "fwd_6m_excess",
    "fwd_12m_excess",
}


@dataclass
class MacroBundle:
    features: pd.DataFrame
    regime_model_current: str
    regime_forecast_12m: pd.Series


@dataclass
class ModelResult:
    predictions: pd.DataFrame
    holdout_predictions: pd.DataFrame
    live_rankings: pd.DataFrame
    metrics: pd.DataFrame
    feature_importance: pd.DataFrame
    feature_columns: list[str]


@dataclass
class ResearchResult:
    panel: pd.DataFrame
    trend_quality: pd.DataFrame
    fake_breakouts: pd.DataFrame
    regime_payoff: pd.DataFrame
    daily_cross_events: pd.DataFrame
    daily_cross_sector_summary: pd.DataFrame
    daily_cross_regime_summary: pd.DataFrame
    daily_cross_lead_summary: pd.DataFrame
    sizing_advisor: pd.DataFrame
    model: ModelResult
    macro_bundle: MacroBundle
    current_snapshot: dict[str, Any]
    output_dir: Path


def _month_end(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return index.to_period("M").to_timestamp("M")


def _roll_z(series: pd.Series, window: int = 120, min_periods: int = 36) -> pd.Series:
    mean = series.rolling(window, min_periods=min_periods).mean()
    std = series.rolling(window, min_periods=min_periods).std()
    return ((series - mean) / std).clip(-3.0, 3.0)


def _normalised_rank(series: pd.Series, ascending: bool = True) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.dropna().nunique() <= 1:
        return pd.Series(0.5, index=numeric.index, dtype="float64")
    return numeric.rank(pct=True, ascending=ascending).fillna(0.5)


def _is_excluded_predictive_feature(name: str) -> bool:
    key = str(name).lower()
    return any(part in key for part in EXCLUDED_PREDICTIVE_FEATURE_PARTS)


def _feature_family(name: str) -> str:
    key = str(name).lower()
    if _is_excluded_predictive_feature(key):
        return "excluded_metadata"
    if key.startswith("sector_"):
        return "sector_control"
    if key.startswith("dalio_quadrant") or key.startswith("gmm_regime") or key.startswith("last_cross_type"):
        return "regime_or_state_control"
    if any(part in key for part in ("surprise", "beat_rate", "eps_yoy", "earnings")):
        return "fundamental"
    if any(part in key for part in ("market_cap", "turnover", "dollar_volume")):
        return "market_structure"
    if any(part in key for part in ("nfci", "hy_spread", "vix", "curve", "cpi", "indpro", "dxy", "gold", "copper", "wti", "cape", "mktcap_to_gdp")):
        return "macro_nowcast"
    if any(part in key for part in ("fed_path", "breakeven", "infl_5y5y", "infl_exp", "claims", "permits")):
        return "forward_macro"
    if any(part in key for part in ("oscillator", "return", "drawdown", "volatility", "beta", "corr", "ma_gap", "slow_ma", "cross", "trend")):
        return "price_trend"
    return "other"


def _safe_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _fmt_pct(value: Any, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value) * 100.0:.{digits}f}%"


def _fmt_num(value: Any, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{digits}f}"


def _img(b64: str, caption: str) -> str:
    return (
        f'<figure class="chart"><img src="data:image/png;base64,{b64}" '
        f'alt="{html.escape(caption)}"/><figcaption>{html.escape(caption)}</figcaption></figure>'
    )


def _table(frame: pd.DataFrame, *, max_rows: int | None = None, float_fmt: str = "{:.2f}") -> str:
    if frame.empty:
        return "<p class=\"note\">No rows available.</p>"
    view = frame.copy()
    if max_rows is not None:
        view = view.head(max_rows)

    def fmt(value: Any) -> str:
        if isinstance(value, (float, np.floating)):
            return "" if pd.isna(value) else float_fmt.format(float(value))
        if isinstance(value, (int, np.integer)):
            return f"{int(value)}"
        return html.escape(str(value))

    head = "".join(f"<th>{html.escape(str(col))}</th>" for col in view.columns)
    body = []
    for idx, row in view.iterrows():
        cells = "".join(f"<td>{fmt(value)}</td>" for value in row)
        body.append(f"<tr><th>{html.escape(str(idx))}</th>{cells}</tr>")
    return f"<table><thead><tr><th></th>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _load_macro_extras(root: Path, index: pd.DatetimeIndex) -> pd.DataFrame:
    path = root / "cache" / "macro_daily_1999.csv"
    if not path.exists():
        return pd.DataFrame(index=index)
    daily = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    monthly = daily.resample("ME").last()
    extras = pd.DataFrame(index=monthly.index)
    for raw, out in {
        "wti_usd_per_bbl": "wti",
        "us_30y_yield": "us_30y",
        "xlu_close": "xlu_price_proxy",
        "xly_close": "xly_price_proxy",
        "eem_close": "eem_price_proxy",
        "efa_close": "efa_price_proxy",
    }.items():
        if raw in monthly:
            extras[out] = monthly[raw]
    return extras.reindex(index).ffill(limit=2)


def build_macro_bundle(root: Path, index: pd.DatetimeIndex, indices: pd.DataFrame, slow: int) -> MacroBundle:
    macro = load_macro_panel(root)
    macro = macro.reindex(index.union(macro.index)).sort_index()
    extras = _load_macro_extras(root, macro.index)
    macro = macro.join(extras, how="left")

    sig = dalio_signals(macro)
    macro["growth_signal"] = sig["growth_signal"]
    macro["inflation_signal"] = sig["inflation_signal"]
    macro["dalio_quadrant"] = dalio_quadrant(macro)

    broad_for_regime = indices["Broad market"].reindex(macro.index).ffill()
    fwd12 = broad_for_regime.shift(-12) / broad_for_regime - 1.0
    regime_model = fit_regime_model(macro, fwd12)
    macro["gmm_regime"] = regime_model.labels.reindex(macro.index).ffill(limit=2)

    health = market_health(macro, indices, slow)
    macro["market_health"] = health["health"].reindex(macro.index)
    macro["sector_breadth"] = health["breadth_frac"].reindex(macro.index)

    for col in [
        "nfci",
        "hy_spread",
        "vix",
        "vix3m",
        "t10y3m",
        "yield_curve_10y2y",
        "core_cpi_yoy",
        "indpro_yoy",
        "dxy",
        "gold",
        "copper",
        "wti",
        "fed_path_2y",
        "breakeven_10y",
        "infl_5y5y_fwd",
        "infl_exp_1y",
        "claims_yoy",
        "permits_yoy",
        "cape",
        "mktcap_to_gdp",
    ]:
        if col in macro:
            macro[f"{col}_z"] = _roll_z(pd.to_numeric(macro[col], errors="coerce"))

    for col in ["gold", "copper", "wti", "dxy", "equity_index"]:
        if col in macro:
            macro[f"{col}_ret_6m"] = macro[col] / macro[col].shift(6) - 1.0
            macro[f"{col}_ret_12m"] = macro[col] / macro[col].shift(12) - 1.0

    if {"vix", "vix3m"}.issubset(macro.columns):
        macro["vix_curve_spread"] = macro["vix"] - macro["vix3m"]
        macro["vix_curve_ratio"] = macro["vix"] / macro["vix3m"] - 1.0
    if {"copper", "gold"}.issubset(macro.columns):
        macro["copper_gold_ratio"] = macro["copper"] / macro["gold"]
        macro["copper_gold_ratio_z"] = _roll_z(macro["copper_gold_ratio"])

    wanted = [
        "dalio_quadrant",
        "gmm_regime",
        "growth_signal",
        "inflation_signal",
        "market_health",
        "sector_breadth",
        "nfci",
        "nfci_z",
        "hy_spread",
        "hy_spread_z",
        "vix",
        "vix_z",
        "vix3m",
        "vix_curve_spread",
        "vix_curve_ratio",
        "t10y3m",
        "t10y3m_z",
        "yield_curve_10y2y",
        "yield_curve_10y2y_z",
        "core_cpi_yoy",
        "core_cpi_yoy_z",
        "indpro_yoy",
        "indpro_yoy_z",
        "dxy",
        "dxy_z",
        "dxy_ret_6m",
        "gold",
        "gold_z",
        "gold_ret_6m",
        "copper",
        "copper_z",
        "copper_ret_6m",
        "wti",
        "wti_z",
        "wti_ret_6m",
        "copper_gold_ratio",
        "copper_gold_ratio_z",
        "fed_path_2y",
        "fed_path_2y_z",
        "breakeven_10y",
        "breakeven_10y_z",
        "infl_5y5y_fwd",
        "infl_5y5y_fwd_z",
        "infl_exp_1y",
        "infl_exp_1y_z",
        "claims_yoy",
        "claims_yoy_z",
        "permits_yoy",
        "permits_yoy_z",
        "cape",
        "cape_z",
        "mktcap_to_gdp",
        "mktcap_to_gdp_z",
    ]
    features = macro[[c for c in wanted if c in macro.columns]].reindex(index).ffill(limit=2)
    return MacroBundle(
        features=features,
        regime_model_current=regime_model.current,
        regime_forecast_12m=regime_model.forecast["12m"].sort_values(ascending=False),
    )


def load_lagged_fundamental_features(root: Path, index: pd.DatetimeIndex) -> pd.DataFrame:
    path = root / "outputs" / "sector_fundamentals_research" / "sector_factor_panel.csv"
    if not path.exists():
        return pd.DataFrame()

    raw = pd.read_csv(path)
    raw["sector"] = raw["sector"].map(lambda s: FUNDAMENTAL_SECTOR_MAP.get(str(s).upper(), str(s)))
    raw["quarter_end_date"] = pd.to_datetime(raw["quarter_end_date"], errors="coerce")
    raw["quarter_end_date"] = _month_end(pd.DatetimeIndex(raw["quarter_end_date"]))
    keep = ["sector", "quarter_end_date"] + [c for c in SECTOR_FACTOR_PANEL_FEATURES if c in raw.columns]
    raw = raw[keep].dropna(subset=["sector", "quarter_end_date"]).sort_values(["sector", "quarter_end_date"])

    rows: list[pd.DataFrame] = []
    for sector, group in raw.groupby("sector"):
        g = group.drop_duplicates("quarter_end_date", keep="last").set_index("quarter_end_date")
        g = g.drop(columns=["sector"])
        monthly = g.reindex(index.union(g.index)).sort_index().ffill(limit=6).reindex(index)
        monthly["sector"] = sector
        monthly["date"] = index
        rows.append(monthly.reset_index(drop=True))
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def load_sector_etf_indices(root: Path) -> pd.DataFrame:
    frames: dict[str, pd.Series] = {}
    latest_trade_dates: list[pd.Timestamp] = []
    for sector, symbol in SECTOR_ETF_MAP.items():
        path = root / "cache" / "advise" / f"{symbol}_daily.csv"
        if not path.exists():
            continue
        daily = pd.read_csv(path, parse_dates=["date"])
        if daily.empty or "close" not in daily.columns:
            continue
        daily = daily.dropna(subset=["date", "close"]).sort_values("date")
        latest_trade_dates.append(pd.Timestamp(daily["date"].max()))
        close = pd.Series(pd.to_numeric(daily["close"], errors="coerce").to_numpy(), index=pd.to_datetime(daily["date"]))
        monthly = close.resample("ME").last().dropna()
        if len(monthly) >= 24:
            frames[sector] = monthly / monthly.dropna().iloc[0] * 100.0

    if len(frames) < 6:
        return pd.DataFrame()
    indices = pd.DataFrame(frames).sort_index()
    broad_returns = indices.pct_change(fill_method=None).mean(axis=1, skipna=True)
    indices["Broad market"] = (1.0 + broad_returns.fillna(0.0)).cumprod() * 100.0
    indices = indices.where(indices.notna().cumsum() > 0)
    indices.index.name = "date"
    if latest_trade_dates:
        indices.attrs["latest_trade_date"] = max(latest_trade_dates).strftime("%Y-%m-%d")
    indices.attrs["source"] = "sector_etf_cache"
    return indices


def load_sector_etf_daily_prices(root: Path) -> pd.DataFrame:
    frames: dict[str, pd.Series] = {}
    latest_trade_dates: list[pd.Timestamp] = []
    for sector, symbol in SECTOR_ETF_MAP.items():
        path = root / "cache" / "advise" / f"{symbol}_daily.csv"
        if not path.exists():
            continue
        daily = pd.read_csv(path, parse_dates=["date"])
        if daily.empty or "close" not in daily.columns:
            continue
        daily = daily.dropna(subset=["date", "close"]).sort_values("date")
        daily["date"] = pd.to_datetime(daily["date"]).dt.normalize()
        close = pd.Series(pd.to_numeric(daily["close"], errors="coerce").to_numpy(), index=daily["date"])
        close = close[~close.index.duplicated(keep="last")].dropna()
        if len(close) >= DAILY_SLOW + 20:
            frames[sector] = close
            latest_trade_dates.append(pd.Timestamp(close.index.max()))

    prices = pd.DataFrame(frames).sort_index()
    prices.index.name = "date"
    if latest_trade_dates:
        prices.attrs["latest_trade_date"] = max(latest_trade_dates).strftime("%Y-%m-%d")
    return prices


def _completed_macro_month(date: pd.Timestamp) -> pd.Timestamp:
    return (pd.Timestamp(date).normalize() - pd.offsets.MonthEnd(1)).to_period("M").to_timestamp("M")


def _daily_cross_events_for_sector(
    sector: str,
    price: pd.Series,
    *,
    fast: int = DAILY_FAST,
    slow: int = DAILY_SLOW,
    whipsaw_days: int = 63,
    breakout_threshold: float = 0.05,
) -> list[dict[str, Any]]:
    price = price.dropna().sort_index()
    if len(price) < slow + 20:
        return []
    sma_fast = price.rolling(fast, min_periods=fast).mean()
    sma_slow = price.rolling(slow, min_periods=slow).mean()
    gap = sma_fast / sma_slow - 1.0
    sign = np.sign(gap.dropna())
    cross_dates: list[pd.Timestamp] = []
    cross_types: list[str] = []
    prev: float | None = None
    for dt, value in sign.items():
        if prev is not None and value != prev and value != 0:
            cross_dates.append(pd.Timestamp(dt))
            cross_types.append("golden" if value > 0 else "death")
        if value != 0:
            prev = float(value)

    events: list[dict[str, Any]] = []
    date_positions = {pd.Timestamp(dt): pos for pos, dt in enumerate(price.index)}
    for i, (dt, event_type) in enumerate(zip(cross_dates, cross_types, strict=False)):
        if dt not in date_positions:
            continue
        pos = date_positions[dt]
        p0 = float(price.iloc[pos])
        next_dt = cross_dates[i + 1] if i + 1 < len(cross_dates) else pd.Timestamp(price.index[-1])
        end_pos = date_positions.get(next_dt, len(price) - 1)
        segment = price.iloc[pos : end_pos + 1]
        direction = 1.0 if event_type == "golden" else -1.0
        directional_move = (segment / p0 - 1.0) * direction
        max_favorable = float(directional_move.max()) if not directional_move.empty else np.nan
        duration_days = int(max(end_pos - pos, 0))
        # The final cross has no closing event yet: its duration and favorable
        # excursion are right-censored, so the whipsaw verdict is only known
        # once both thresholds have been definitively cleared. Otherwise the
        # newest cross would always count as a fake breakout.
        is_final = i + 1 >= len(cross_dates)
        resolved = (not is_final) or (
            duration_days > whipsaw_days and max_favorable >= breakout_threshold
        )
        whipsaw = (
            float((duration_days <= whipsaw_days) or (max_favorable < breakout_threshold))
            if resolved
            else np.nan
        )
        row: dict[str, Any] = {
            "sector": sector,
            "symbol": SECTOR_ETF_MAP.get(sector),
            "date": dt,
            "type": event_type,
            "price": p0,
            "sma50": float(sma_fast.loc[dt]),
            "sma200": float(sma_slow.loc[dt]),
            "sma_gap": float(gap.loc[dt]),
            "macro_date": _completed_macro_month(dt),
            "duration_trading_days": duration_days,
            "max_favorable": max_favorable,
            "whipsaw": whipsaw,
            "whipsaw_censored": bool(not resolved),
        }
        for horizon in DAILY_FORWARD_HORIZONS:
            if pos + horizon < len(price):
                row[f"fwd_{horizon}d"] = float(price.iloc[pos + horizon] / p0 - 1.0)
            else:
                row[f"fwd_{horizon}d"] = np.nan
        events.append(row)
    return events


def build_daily_50200_cross_study(
    root: Path,
    macro_bundle: MacroBundle,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    prices = load_sector_etf_daily_prices(root)
    if prices.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    events = []
    for sector in prices.columns:
        events.extend(_daily_cross_events_for_sector(sector, prices[sector]))
    event_frame = pd.DataFrame(events)
    if event_frame.empty:
        return event_frame, pd.DataFrame(), pd.DataFrame()

    macro = macro_bundle.features.copy()
    macro.index = pd.to_datetime(macro.index)
    event_frame["date"] = pd.to_datetime(event_frame["date"])
    event_frame["macro_date"] = pd.to_datetime(event_frame["macro_date"])
    event_frame = event_frame.merge(
        macro.reset_index(names="macro_date"),
        on="macro_date",
        how="left",
    )

    sector_rows: list[dict[str, Any]] = []
    for sector, group in event_frame.groupby("sector"):
        price = prices[sector].dropna()
        years = max((price.index.max() - price.index.min()).days / 365.25, 0.25)
        golden = group[group["type"] == "golden"]
        death = group[group["type"] == "death"]
        sector_rows.append(
            {
                "sector": sector,
                "symbol": SECTOR_ETF_MAP.get(sector),
                "first_price_date": price.index.min().strftime("%Y-%m-%d"),
                "last_price_date": price.index.max().strftime("%Y-%m-%d"),
                "events": int(len(group)),
                "golden_crosses": int(len(golden)),
                "death_crosses": int(len(death)),
                "crosses_per_year": float(len(group) / years),
                "median_days_between_crosses": float(group["duration_trading_days"].median()),
                "whipsaw_rate_%": float(group["whipsaw"].mean() * 100.0),
                "golden_fwd_63d_%": float(golden["fwd_63d"].mean() * 100.0) if not golden.empty else np.nan,
                "golden_fwd_126d_%": float(golden["fwd_126d"].mean() * 100.0) if not golden.empty else np.nan,
                "death_fwd_63d_%": float(death["fwd_63d"].mean() * 100.0) if not death.empty else np.nan,
                "death_fwd_126d_%": float(death["fwd_126d"].mean() * 100.0) if not death.empty else np.nan,
            }
        )
    sector_summary = pd.DataFrame(sector_rows).set_index("sector").sort_values("crosses_per_year", ascending=False)

    regime_summary = build_daily_cross_regime_summary(event_frame)
    return event_frame.sort_values(["date", "sector"]).reset_index(drop=True), sector_summary, regime_summary


def build_daily_cross_regime_summary(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for env_col, env_label in (("dalio_quadrant", "Dalio quadrant"), ("gmm_regime", "Statistical regime")):
        if env_col not in events.columns:
            continue
        for (event_type, env), group in events.dropna(subset=[env_col]).groupby(["type", env_col]):
            rows.append(
                {
                    "environment_family": env_label,
                    "environment": str(env),
                    "cross_type": str(event_type),
                    "events": int(len(group)),
                    "whipsaw_rate_%": float(group["whipsaw"].mean() * 100.0),
                    "avg_fwd_63d_%": float(group["fwd_63d"].mean() * 100.0),
                    "hit_fwd_63d_%": float((group["fwd_63d"] > 0.0).mean() * 100.0),
                    "avg_fwd_126d_%": float(group["fwd_126d"].mean() * 100.0),
                    "hit_fwd_126d_%": float((group["fwd_126d"] > 0.0).mean() * 100.0),
                    "avg_market_health": float(group.get("market_health", pd.Series(dtype=float)).mean()),
                    "avg_vix_z": float(group.get("vix_z", pd.Series(dtype=float)).mean()),
                    "avg_hy_spread_z": float(group.get("hy_spread_z", pd.Series(dtype=float)).mean()),
                    "avg_curve_z": float(group.get("t10y3m_z", pd.Series(dtype=float)).mean()),
                }
            )
    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary
    return summary.sort_values(["environment_family", "cross_type", "events"], ascending=[True, True, False])


def latest_daily_50200_state(root: Path) -> pd.DataFrame:
    prices = load_sector_etf_daily_prices(root)
    if prices.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for sector in prices.columns:
        price = prices[sector].dropna()
        if len(price) < DAILY_SLOW:
            continue
        sma50 = price.rolling(DAILY_FAST, min_periods=DAILY_FAST).mean()
        sma200 = price.rolling(DAILY_SLOW, min_periods=DAILY_SLOW).mean()
        gap = sma50 / sma200 - 1.0
        latest = price.index[-1]
        state = "golden" if float(gap.iloc[-1]) >= 0 else "death"
        rows.append(
            {
                "sector": sector,
                "symbol": SECTOR_ETF_MAP.get(sector),
                "daily_price_date": latest.strftime("%Y-%m-%d"),
                "daily_50_200_state": state,
                "daily_sma50": float(sma50.iloc[-1]),
                "daily_sma200": float(sma200.iloc[-1]),
                "daily_50_200_gap": float(gap.iloc[-1]),
                "daily_price_vs_sma200": float(price.iloc[-1] / sma200.iloc[-1] - 1.0),
            }
        )
    return pd.DataFrame(rows)


def build_daily_cross_lead_summary(monthly_panel: pd.DataFrame, daily_cross_events: pd.DataFrame) -> pd.DataFrame:
    if monthly_panel.empty or daily_cross_events.empty:
        return pd.DataFrame()
    events = daily_cross_events[["sector", "date", "type"]].copy()
    events["event_month"] = pd.to_datetime(events["date"]).dt.to_period("M").dt.to_timestamp("M")
    events["signal_month"] = events["event_month"] - pd.offsets.MonthEnd(1)
    event_counts = (
        events.assign(any_cross=1)
        .pivot_table(
            index=["sector", "signal_month"],
            columns="type",
            values="any_cross",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
    )
    event_counts["next_any_cross"] = event_counts.get("death", 0) + event_counts.get("golden", 0)
    event_counts["next_death_cross"] = event_counts.get("death", 0)
    event_counts["next_golden_cross"] = event_counts.get("golden", 0)

    frame = monthly_panel.copy()
    frame["signal_month"] = pd.to_datetime(frame["date"]).dt.to_period("M").dt.to_timestamp("M")
    frame = frame.merge(event_counts, on=["sector", "signal_month"], how="left")
    for col in ["next_any_cross", "next_death_cross", "next_golden_cross"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0.0).clip(upper=1.0)

    rows: list[dict[str, Any]] = []
    for env_col, env_label in (("dalio_quadrant", "Dalio quadrant"), ("gmm_regime", "Statistical regime")):
        if env_col not in frame.columns:
            continue
        grouped = frame.dropna(subset=[env_col]).groupby(env_col)
        for env, group in grouped:
            rows.append(
                {
                    "environment_family": env_label,
                    "environment": str(env),
                    "sector_months": int(len(group)),
                    "next_any_cross_rate_%": float(group["next_any_cross"].mean() * 100.0),
                    "next_golden_cross_rate_%": float(group["next_golden_cross"].mean() * 100.0),
                    "next_death_cross_rate_%": float(group["next_death_cross"].mean() * 100.0),
                    "avg_market_health": float(group.get("market_health", pd.Series(dtype=float)).mean()),
                    "avg_sector_breadth_%": float(group.get("sector_breadth", pd.Series(dtype=float)).mean() * 100.0),
                    "avg_vix_z": float(group.get("vix_z", pd.Series(dtype=float)).mean()),
                    "avg_hy_spread_z": float(group.get("hy_spread_z", pd.Series(dtype=float)).mean()),
                    "avg_curve_z": float(group.get("t10y3m_z", pd.Series(dtype=float)).mean()),
                }
            )
    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary
    return summary.sort_values(["environment_family", "next_any_cross_rate_%"], ascending=[True, False])


def _last_cross_state(events: pd.DataFrame, sector: str, index: pd.DatetimeIndex, price: pd.Series) -> pd.DataFrame:
    rows = pd.DataFrame(index=index)
    rows["last_cross_type"] = "none"
    rows["months_since_cross"] = np.nan
    rows["move_since_last_cross"] = np.nan
    rows["young_cross_risk"] = 0.0
    if events.empty:
        return rows
    sec_events = events.loc[events["sector"] == sector].copy()
    if sec_events.empty:
        return rows
    sec_events["date"] = pd.to_datetime(sec_events["date"])
    sec_events = sec_events.sort_values("date")
    for i, event in sec_events.iterrows():
        dt = pd.Timestamp(event["date"])
        next_events = sec_events.loc[sec_events["date"] > dt, "date"]
        end = pd.Timestamp(next_events.iloc[0]) if not next_events.empty else index[-1]
        mask = (index >= dt) & (index <= end)
        if not mask.any() or dt not in price.index:
            continue
        p0 = float(price.loc[dt])
        direction = 1.0 if event["type"] == "golden" else -1.0
        months = [(d.to_period("M") - dt.to_period("M")).n for d in index[mask]]
        move = (price.reindex(index[mask]) / p0 - 1.0) * direction
        rows.loc[index[mask], "last_cross_type"] = str(event["type"])
        rows.loc[index[mask], "months_since_cross"] = months
        rows.loc[index[mask], "move_since_last_cross"] = move.to_numpy()
        rows.loc[index[mask], "young_cross_risk"] = ((np.array(months) <= 4) & (move.to_numpy() < 0.05)).astype(float)
    return rows


def _average_run_lengths(state: pd.Series) -> tuple[float, float, float]:
    clean = state.dropna()
    if clean.empty:
        return np.nan, np.nan, np.nan
    runs: list[tuple[float, int]] = []
    current = float(clean.iloc[0])
    length = 1
    for value in clean.iloc[1:]:
        value = float(value)
        if value == current:
            length += 1
        else:
            runs.append((current, length))
            current, length = value, 1
    runs.append((current, length))
    up = [length for value, length in runs if value > 0]
    down = [length for value, length in runs if value < 0]
    all_runs = [length for _, length in runs]
    return (
        float(np.mean(up)) if up else np.nan,
        float(np.mean(down)) if down else np.nan,
        float(max(all_runs)) if all_runs else np.nan,
    )


def build_trend_quality(indices: pd.DataFrame, cross_stats: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    sectors = [c for c in indices.columns if c != "Broad market"]
    broad_ret = indices["Broad market"].pct_change(fill_method=None)
    for sector in sectors:
        px = indices[sector].dropna()
        ret = px.pct_change(fill_method=None)
        ma_fast = px.rolling(fast, min_periods=fast).mean()
        ma_slow = px.rolling(slow, min_periods=slow).mean()
        trend_state = np.sign(ma_fast - ma_slow)
        up_run, down_run, max_run = _average_run_lengths(trend_state)
        abs_path = ret.abs().rolling(12, min_periods=12).sum()
        net_path = (px / px.shift(12) - 1.0).abs()
        efficiency = (net_path / abs_path.replace(0.0, np.nan)).clip(0.0, 1.0)
        pair = pd.concat([ret, broad_ret.reindex(ret.index)], axis=1).dropna()
        beta = np.nan
        if len(pair) >= 36 and pair.iloc[:, 1].var() > 0:
            beta = float(pair.iloc[:, 0].cov(pair.iloc[:, 1]) / pair.iloc[:, 1].var())

        cross_row = cross_stats.loc[sector] if sector in cross_stats.index else pd.Series(dtype="float64")
        rows.append(
            {
                "sector": sector,
                "crosses": _safe_float(cross_row.get("crosses")),
                "crosses_per_decade": _safe_float(cross_row.get("per_decade")),
                "fake_breakout_rate_%": _safe_float(cross_row.get("whipsaw_rate_%")),
                "median_cross_hold_m": _safe_float(cross_row.get("median_hold_m")),
                "golden_cross_fwd12_%": _safe_float(cross_row.get("golden_fwd12_%")),
                "death_cross_fwd12_%": _safe_float(cross_row.get("death_fwd12_%")),
                "uptrend_month_share_%": float((px > ma_slow).mean() * 100.0),
                "avg_uptrend_run_m": up_run,
                "avg_downtrend_run_m": down_run,
                "max_trend_run_m": max_run,
                "trend_efficiency_12m": float(efficiency.mean()),
                "ret_autocorr_1m": float(ret.autocorr(1)) if len(ret.dropna()) > 12 else np.nan,
                "ret_autocorr_3m": float(ret.autocorr(3)) if len(ret.dropna()) > 12 else np.nan,
                "beta_to_broad": beta,
            }
        )
    out = pd.DataFrame(rows).set_index("sector")
    score = (
        _normalised_rank(out["fake_breakout_rate_%"], ascending=False) * 0.25
        + _normalised_rank(out["median_cross_hold_m"], ascending=True) * 0.20
        + _normalised_rank(out["avg_uptrend_run_m"], ascending=True) * 0.15
        + _normalised_rank(out["trend_efficiency_12m"], ascending=True) * 0.20
        + _normalised_rank(out["golden_cross_fwd12_%"], ascending=True) * 0.20
    )
    out["trend_quality_score"] = score.clip(0.0, 1.0)
    return out.sort_values("trend_quality_score", ascending=False)


def build_price_feature_panel(
    *,
    indices: pd.DataFrame,
    macro_features: pd.DataFrame,
    cross_events: pd.DataFrame,
    fundamentals: pd.DataFrame,
    fast: int,
    slow: int,
    include_forward_targets: bool,
) -> pd.DataFrame:
    sectors = [c for c in indices.columns if c != "Broad market"]
    broad = indices["Broad market"]
    broad_ret = broad.pct_change(fill_method=None)
    broad_fwd = {h: broad.shift(-h) / broad - 1.0 for h in (1, 3, 6, 12)}
    rows: list[pd.DataFrame] = []

    for sector in sectors:
        px = indices[sector]
        ret = px.pct_change(fill_method=None)
        ma_fast = px.rolling(fast, min_periods=fast).mean()
        ma_slow = px.rolling(slow, min_periods=slow).mean()
        cross_state = _last_cross_state(cross_events, sector, indices.index, px)

        frame = pd.DataFrame(index=indices.index)
        frame["date"] = indices.index
        frame["sector"] = sector
        frame["sector_index"] = px
        frame["sector_return_1m"] = ret
        frame["sector_return_3m"] = px / px.shift(3) - 1.0
        frame["sector_return_6m"] = px / px.shift(6) - 1.0
        frame["sector_return_12m"] = px / px.shift(12) - 1.0
        frame["relative_return_1m"] = ret - broad_ret.reindex(ret.index)
        frame["relative_return_3m"] = frame["sector_return_3m"] - (broad / broad.shift(3) - 1.0)
        frame["relative_return_6m"] = frame["sector_return_6m"] - (broad / broad.shift(6) - 1.0)
        frame["relative_return_12m"] = frame["sector_return_12m"] - (broad / broad.shift(12) - 1.0)
        frame["sector_oscillator"] = momentum_oscillator(px)
        frame["relative_oscillator"] = momentum_oscillator(px / broad * 100.0)
        frame["above_slow_ma"] = (px > ma_slow).astype(float)
        frame["fast_slow_gap"] = ma_fast / ma_slow - 1.0
        frame["slow_ma_gap"] = px / ma_slow - 1.0
        frame["volatility_12m"] = ret.rolling(12, min_periods=6).std() * np.sqrt(12.0)
        frame["drawdown_12m"] = px / px.rolling(12, min_periods=6).max() - 1.0
        frame["drawdown_36m"] = px / px.rolling(36, min_periods=12).max() - 1.0
        frame["relative_volatility_12m"] = frame["volatility_12m"] - broad_ret.rolling(12, min_periods=6).std() * np.sqrt(12.0)
        pair_cov = ret.rolling(36, min_periods=18).cov(broad_ret)
        broad_var = broad_ret.rolling(36, min_periods=18).var()
        frame["beta_36m"] = pair_cov / broad_var.replace(0.0, np.nan)
        frame["corr_36m"] = ret.rolling(36, min_periods=18).corr(broad_ret)
        frame = frame.join(cross_state)

        if include_forward_targets:
            for h in (1, 3, 6, 12):
                frame[f"fwd_{h}m"] = px.shift(-h) / px - 1.0
                frame[f"fwd_{h}m_broad"] = broad_fwd[h]
                frame[f"fwd_{h}m_excess"] = frame[f"fwd_{h}m"] - frame[f"fwd_{h}m_broad"]

        rows.append(frame.reset_index(drop=True))

    panel = pd.concat(rows, ignore_index=True)
    panel = panel.merge(macro_features.reset_index(names="date"), on="date", how="left")
    if not fundamentals.empty:
        panel = panel.merge(fundamentals, on=["date", "sector"], how="left")
    return panel.sort_values(["date", "sector"]).reset_index(drop=True)


def build_sector_regime_panel(
    *,
    root: Path,
    fundamentals_dir: str | Path | None,
    fast: int,
    slow: int,
    refresh_sector_cache: bool,
    label_horizon: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, MacroBundle]:
    indices, _members = build_sector_indices(root, fundamentals_dir, refresh=refresh_sector_cache)
    sectors = [c for c in indices.columns if c != "Broad market"]
    macro_bundle = build_macro_bundle(root, indices.index, indices, slow)
    cross_stats = analyse_crosses(indices, fast, slow)
    trend_quality = build_trend_quality(indices, cross_stats.per_sector, fast, slow)
    fundamentals = load_lagged_fundamental_features(root, indices.index)

    panel = build_price_feature_panel(
        indices=indices,
        macro_features=macro_bundle.features,
        cross_events=cross_stats.events,
        fundamentals=fundamentals,
        fast=fast,
        slow=slow,
        include_forward_targets=True,
    )

    count_by_date = panel.groupby("date")["fwd_6m_excess"].transform("count")
    panel["leader_rank_pct"] = panel.groupby("date")["fwd_6m_excess"].rank(pct=True)
    panel["target_leader"] = (panel["leader_rank_pct"] >= (1.0 - 1.0 / 3.0)).where(
        panel["fwd_6m_excess"].notna() & (count_by_date >= max(6, len(sectors) // 2))
    )
    panel["target_leader"] = panel["target_leader"].astype("float64")
    return panel.sort_values(["date", "sector"]).reset_index(drop=True), trend_quality, cross_stats.events, macro_bundle


def build_live_etf_overlay_panel(root: Path, fast: int, slow: int) -> tuple[pd.DataFrame, MacroBundle | None, str | None]:
    indices = load_sector_etf_indices(root)
    if indices.empty:
        return pd.DataFrame(), None, None
    macro_bundle = build_macro_bundle(root, indices.index, indices, slow)
    cross_stats = analyse_crosses(indices, fast, slow)
    fundamentals = load_lagged_fundamental_features(root, indices.index)
    panel = build_price_feature_panel(
        indices=indices,
        macro_features=macro_bundle.features,
        cross_events=cross_stats.events,
        fundamentals=fundamentals,
        fast=fast,
        slow=slow,
        include_forward_targets=False,
    )
    panel["live_source"] = "sector_etf_cache"
    latest_trade_date = indices.attrs.get("latest_trade_date")
    return panel, macro_bundle, str(latest_trade_date) if latest_trade_date else None


def _build_design_matrix(panel: pd.DataFrame, min_coverage: float) -> tuple[pd.DataFrame, list[str]]:
    # gmm_regime is deliberately NOT a predictive feature: the mixture is fit
    # on the full history, so its labels would leak future information into
    # the walk-forward folds. It stays in the panel as descriptive metadata.
    categorical = [c for c in ["sector", "dalio_quadrant", "last_cross_type"] if c in panel.columns]
    numeric = []
    for col in panel.columns:
        if col in categorical or col in TARGET_COLUMNS or col in {"date", "sector_index"}:
            continue
        if _is_excluded_predictive_feature(col):
            continue
        if pd.api.types.is_numeric_dtype(panel[col]):
            numeric.append(col)
    design = panel[numeric].apply(pd.to_numeric, errors="coerce")
    if categorical:
        design = pd.concat(
            [design, pd.get_dummies(panel[categorical].astype("category"), dummy_na=True, dtype=float)],
            axis=1,
        )
    coverage = design.notna().mean()
    feature_columns = coverage[coverage >= min_coverage].index.tolist()
    return design[feature_columns], feature_columns


def _models(random_state: int) -> dict[str, Pipeline]:
    return {
        "logit": Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        solver="lbfgs",
                        max_iter=2_000,
                        class_weight="balanced",
                        random_state=random_state,
                    ),
                ),
            ]
        ),
        "extra_trees": Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    ExtraTreesClassifier(
                        n_estimators=500,
                        max_depth=7,
                        min_samples_leaf=25,
                        min_samples_split=50,
                        class_weight="balanced",
                        random_state=random_state,
                        n_jobs=-1,
                    ),
                ),
            ]
        ),
        "hist_gradient": Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    HistGradientBoostingClassifier(
                        learning_rate=0.04,
                        max_iter=250,
                        max_leaf_nodes=15,
                        min_samples_leaf=35,
                        l2_regularization=2.0,
                        random_state=random_state,
                    ),
                ),
            ]
        ),
    }


def _predict_with_models(models: dict[str, Pipeline], x: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=x.index)
    prob_cols = []
    for key, model in models.items():
        col = f"prob_{key}"
        out[col] = model.predict_proba(x)[:, 1]
        prob_cols.append(col)
    out["ensemble_probability"] = out[prob_cols].mean(axis=1)
    return out


def _fit_model_stack(x_train: pd.DataFrame, y_train: pd.Series, random_state: int) -> dict[str, Pipeline] | None:
    if y_train.nunique(dropna=True) < 2:
        return None
    fitted = _models(random_state)
    for model in fitted.values():
        model.fit(x_train, y_train.astype(int))
    return fitted


def _classification_metrics(frame: pd.DataFrame, label: str) -> dict[str, Any]:
    if frame.empty:
        return {
            "sample": label,
            "rows": 0,
            "months": 0,
            "target_rate": np.nan,
            "roc_auc": np.nan,
            "brier": np.nan,
            "precision_at_50": np.nan,
            "recall_at_50": np.nan,
        }
    y = frame["target_leader"].astype(int)
    p = frame["ensemble_probability"].astype(float)
    pred = (p >= 0.50).astype(int)
    return {
        "sample": label,
        "rows": int(len(frame)),
        "months": int(frame["date"].nunique()),
        "target_rate": float(y.mean()),
        "roc_auc": float(roc_auc_score(y, p)) if y.nunique() == 2 else np.nan,
        "brier": float(brier_score_loss(y, p)),
        "precision_at_50": float(precision_score(y, pred, zero_division=0)),
        "recall_at_50": float(recall_score(y, pred, zero_division=0)),
    }


def _topn_forward_summary(frame: pd.DataFrame, label: str, top_n: int) -> dict[str, Any]:
    if frame.empty:
        return {
            "sample": label,
            "top_n": top_n,
            "signal_months": 0,
            "topn_fwd6": np.nan,
            "broad_fwd6": np.nan,
            "topn_excess": np.nan,
            "excess_hit_rate": np.nan,
            "leader_capture_rate": np.nan,
        }
    rows = []
    for date, group in frame.groupby("date"):
        selected = group.sort_values("ensemble_probability", ascending=False).head(top_n)
        rows.append(
            {
                "date": date,
                "topn_fwd6": selected["fwd_6m"].mean(),
                "broad_fwd6": selected["fwd_6m_broad"].mean(),
                "topn_excess": selected["fwd_6m_excess"].mean(),
                "leader_capture_rate": selected["target_leader"].mean(),
            }
        )
    out = pd.DataFrame(rows).dropna(subset=["topn_excess"])
    return {
        "sample": label,
        "top_n": top_n,
        "signal_months": int(len(out)),
        "topn_fwd6": float(out["topn_fwd6"].mean()) if not out.empty else np.nan,
        "broad_fwd6": float(out["broad_fwd6"].mean()) if not out.empty else np.nan,
        "topn_excess": float(out["topn_excess"].mean()) if not out.empty else np.nan,
        "excess_hit_rate": float((out["topn_excess"] > 0.0).mean()) if not out.empty else np.nan,
        "leader_capture_rate": float(out["leader_capture_rate"].mean()) if not out.empty else np.nan,
    }


def run_walk_forward_model(
    panel: pd.DataFrame,
    *,
    live_panel: pd.DataFrame | None = None,
    holdout_start: str,
    train_years: int,
    label_horizon: int,
    top_n: int,
    min_feature_coverage: float,
    random_state: int = 42,
) -> ModelResult:
    live_panel = live_panel if live_panel is not None else pd.DataFrame()
    combined = pd.concat([panel, live_panel], ignore_index=True, sort=False) if not live_panel.empty else panel.copy()
    design_all, _all_feature_columns = _build_design_matrix(combined, min_coverage=0.0)
    model_mask = panel["target_leader"].notna() & panel["fwd_6m_excess"].notna()
    model_frame = panel.loc[model_mask].copy()
    coverage = design_all.loc[model_frame.index].notna().mean()
    feature_columns = coverage[coverage >= min_feature_coverage].index.tolist()
    model_x = design_all.loc[model_frame.index, feature_columns]
    holdout_ts = pd.Timestamp(holdout_start)

    predictions: list[pd.DataFrame] = []
    first_year = int(model_frame["date"].dt.year.min()) + train_years
    last_validation_year = holdout_ts.year - 1
    for year in range(first_year, last_validation_year + 1):
        validation_start = pd.Timestamp(year=year, month=1, day=1)
        validation_end = validation_start + pd.DateOffset(years=1)
        train_end = validation_start - pd.DateOffset(months=label_horizon)
        train_idx = model_frame.index[model_frame["date"] < train_end]
        test_idx = model_frame.index[
            (model_frame["date"] >= validation_start) & (model_frame["date"] < validation_end)
        ]
        if len(train_idx) < 300 or len(test_idx) == 0:
            continue
        fitted = _fit_model_stack(model_x.loc[train_idx], model_frame.loc[train_idx, "target_leader"], random_state)
        if fitted is None:
            continue
        pred = panel.loc[
            test_idx,
            [
                "date",
                "sector",
                "target_leader",
                "leader_rank_pct",
                "fwd_6m",
                "fwd_6m_broad",
                "fwd_6m_excess",
                "dalio_quadrant",
                "gmm_regime",
            ],
        ].copy()
        pred["fold"] = str(year)
        pred = pred.join(_predict_with_models(fitted, design_all.loc[test_idx, feature_columns]))
        predictions.append(pred)

    validation_predictions = pd.concat(predictions, ignore_index=True) if predictions else pd.DataFrame()

    holdout_train_end = holdout_ts - pd.DateOffset(months=label_horizon)
    holdout_train_idx = model_frame.index[model_frame["date"] < holdout_train_end]
    holdout_idx = model_frame.index[model_frame["date"] >= holdout_ts]
    holdout_predictions = pd.DataFrame()
    if len(holdout_train_idx) >= 300 and len(holdout_idx) > 0:
        fitted_holdout = _fit_model_stack(
            model_x.loc[holdout_train_idx],
            model_frame.loc[holdout_train_idx, "target_leader"],
            random_state,
        )
        if fitted_holdout is not None:
            holdout_predictions = panel.loc[
                holdout_idx,
                [
                    "date",
                    "sector",
                    "target_leader",
                    "leader_rank_pct",
                    "fwd_6m",
                    "fwd_6m_broad",
                    "fwd_6m_excess",
                    "dalio_quadrant",
                    "gmm_regime",
                ],
            ].copy()
            holdout_predictions["fold"] = "holdout"
            holdout_predictions = holdout_predictions.join(
                _predict_with_models(fitted_holdout, design_all.loc[holdout_idx, feature_columns])
            )

    train_all_idx = model_frame.index[model_frame["target_leader"].notna()]
    final_models = _fit_model_stack(model_x.loc[train_all_idx], model_frame.loc[train_all_idx, "target_leader"], random_state)
    if final_models is None:
        raise ValueError("Unable to fit final model stack: target has one class.")

    live_source = live_panel if not live_panel.empty else panel
    live_offset = len(panel) if not live_panel.empty else 0
    latest_date = pd.Timestamp(live_source["date"].max())
    if not live_panel.empty:
        live_idx = live_offset + live_panel.index[live_panel["date"] == latest_date]
    else:
        live_idx = panel.index[panel["date"] == latest_date]
    live_meta_cols = [
        "date",
        "sector",
        "sector_return_6m",
        "relative_return_6m",
        "sector_oscillator",
        "relative_oscillator",
        "above_slow_ma",
        "fast_slow_gap",
        "slow_ma_gap",
        "volatility_12m",
        "drawdown_12m",
        "beta_36m",
        "young_cross_risk",
        "dalio_quadrant",
        "gmm_regime",
        "market_health",
        "sector_breadth",
        "cap_weighted_quarterly_eps_yoy_pct_lag1",
        "cap_weighted_surprise_pct_lag1",
        "beat_rate_lag1",
    ]
    live_rankings = combined.loc[live_idx, [c for c in live_meta_cols if c in combined.columns]].copy()
    live_rankings = live_rankings.join(_predict_with_models(final_models, design_all.loc[live_idx, feature_columns]))

    extra = final_models["extra_trees"].named_steps["model"]
    importance = pd.DataFrame(
        {
            "feature": feature_columns,
            "importance": extra.feature_importances_,
        }
    ).sort_values("importance", ascending=False)
    importance["family"] = importance["feature"].map(_feature_family)

    metric_rows = [_classification_metrics(validation_predictions, "validation")]
    if not holdout_predictions.empty:
        metric_rows.append(_classification_metrics(holdout_predictions, "holdout"))
    metric_rows.append(_topn_forward_summary(validation_predictions, "validation_topn", top_n))
    if not holdout_predictions.empty:
        metric_rows.append(_topn_forward_summary(holdout_predictions, "holdout_topn", top_n))
    metrics = pd.DataFrame(metric_rows).set_index("sample")
    return ModelResult(
        predictions=validation_predictions,
        holdout_predictions=holdout_predictions,
        live_rankings=live_rankings,
        metrics=metrics,
        feature_importance=importance,
        feature_columns=feature_columns,
    )


def build_regime_payoff(panel: pd.DataFrame) -> pd.DataFrame:
    data = panel.dropna(subset=["gmm_regime", "fwd_6m_excess"])
    payoff = data.pivot_table(
        index="sector",
        columns="gmm_regime",
        values="fwd_6m_excess",
        aggfunc="mean",
    )
    payoff = payoff * 100.0
    col_order = payoff.mean(axis=0).sort_values().index.tolist()
    return payoff[col_order].sort_index()


def enrich_live_rankings(
    live: pd.DataFrame,
    trend_quality: pd.DataFrame,
    regime_payoff: pd.DataFrame,
) -> pd.DataFrame:
    out = live.copy()
    out = out.merge(
        trend_quality[["trend_quality_score", "fake_breakout_rate_%", "avg_uptrend_run_m", "trend_efficiency_12m"]],
        left_on="sector",
        right_index=True,
        how="left",
    )
    current_regime = str(out["gmm_regime"].dropna().iloc[0]) if out["gmm_regime"].notna().any() else None
    if current_regime and current_regime in regime_payoff.columns:
        out["current_regime_fwd6_excess_%"] = out["sector"].map(regime_payoff[current_regime])
    else:
        out["current_regime_fwd6_excess_%"] = np.nan

    fundamental = pd.concat(
        [
            _normalised_rank(out.get("cap_weighted_quarterly_eps_yoy_pct_lag1", pd.Series(index=out.index)), True),
            _normalised_rank(out.get("cap_weighted_surprise_pct_lag1", pd.Series(index=out.index)), True),
            _normalised_rank(out.get("beat_rate_lag1", pd.Series(index=out.index)), True),
        ],
        axis=1,
    ).mean(axis=1)
    out["fundamental_rank"] = fundamental.fillna(0.5)
    out["regime_payoff_rank"] = _normalised_rank(out["current_regime_fwd6_excess_%"], True)
    out["oscillator_rank"] = _normalised_rank(out["relative_oscillator"], True)
    out["trend_rank"] = out["trend_quality_score"].fillna(0.5)
    out["final_score"] = (
        0.45 * _normalised_rank(out["ensemble_probability"], True)
        + 0.20 * out["regime_payoff_rank"]
        + 0.15 * out["trend_rank"]
        + 0.10 * out["oscillator_rank"]
        + 0.10 * out["fundamental_rank"]
    ).clip(0.0, 1.0)
    out = out.sort_values("final_score", ascending=False).reset_index(drop=True)
    out["rank"] = np.arange(1, len(out) + 1)
    top_cut = min(3, max(1, len(out) // 3))
    bottom_cut = min(3, max(1, len(out) // 3))
    out["verdict"] = "Neutral"
    out.loc[out.index < top_cut, "verdict"] = "Favored"
    out.loc[out.index >= len(out) - bottom_cut, "verdict"] = "Avoid"
    return out


def build_sizing_advisor(live: pd.DataFrame, *, top_n: int = DEFAULT_TOP_N) -> pd.DataFrame:
    if live.empty:
        return pd.DataFrame()
    frame = live.copy().sort_values("rank").reset_index(drop=True)
    health = float(frame["market_health"].dropna().iloc[0]) if frame["market_health"].notna().any() else 50.0
    if health >= 75.0:
        long_gross, short_gross = 0.85, 0.15
        regime_risk = "risk-on"
    elif health >= 60.0:
        long_gross, short_gross = 0.70, 0.25
        regime_risk = "constructive"
    elif health >= 45.0:
        long_gross, short_gross = 0.50, 0.35
        regime_risk = "balanced"
    elif health >= 30.0:
        long_gross, short_gross = 0.30, 0.55
        regime_risk = "defensive"
    else:
        long_gross, short_gross = 0.15, 0.75
        regime_risk = "risk-off"

    frame["side"] = "Flat"
    frame.loc[frame["rank"] <= top_n, "side"] = "Long"
    frame.loc[frame["rank"] > len(frame) - top_n, "side"] = "Short"

    frame["confidence"] = (frame["final_score"] - 0.50).abs().mul(2.0).clip(0.10, 1.00)
    frame["trend_multiplier"] = 1.0
    if "daily_50_200_state" in frame.columns:
        long_bad = (frame["side"] == "Long") & frame["daily_50_200_state"].eq("death")
        short_bad = (frame["side"] == "Short") & frame["daily_50_200_state"].eq("golden")
        frame.loc[long_bad | short_bad, "trend_multiplier"] = 0.50
    if "daily_50_200_gap" in frame.columns:
        near_cross = frame["daily_50_200_gap"].abs() < 0.015
        frame.loc[near_cross, "trend_multiplier"] *= 0.80

    frame["risk_unit"] = frame["confidence"] * frame["trend_multiplier"]
    volatility = pd.to_numeric(frame.get("volatility_12m", pd.Series(index=frame.index)), errors="coerce")
    frame["volatility_scalar"] = (volatility.median() / volatility).replace([np.inf, -np.inf], np.nan).clip(0.50, 1.50).fillna(1.0)
    frame["risk_unit"] *= frame["volatility_scalar"]

    frame["advisor_weight"] = 0.0
    long_mask = frame["side"].eq("Long")
    short_mask = frame["side"].eq("Short")
    if long_mask.any():
        units = frame.loc[long_mask, "risk_unit"].clip(lower=0.05)
        frame.loc[long_mask, "advisor_weight"] = long_gross * units / units.sum()
    if short_mask.any():
        units = frame.loc[short_mask, "risk_unit"].clip(lower=0.05)
        frame.loc[short_mask, "advisor_weight"] = -short_gross * units / units.sum()

    frame["advisor_weight_%"] = frame["advisor_weight"] * 100.0
    frame["portfolio_role"] = regime_risk
    frame["action_note"] = "Hold flat"
    frame.loc[long_mask, "action_note"] = "Long candidate"
    frame.loc[short_mask, "action_note"] = "Short/hedge candidate"
    if "daily_50_200_state" in frame.columns:
        frame.loc[long_mask & frame["daily_50_200_state"].eq("death"), "action_note"] = "Long watchlist; below 50/200 trend"
        frame.loc[short_mask & frame["daily_50_200_state"].eq("golden"), "action_note"] = "Hedge only; above 50/200 trend"

    cols = [
        "rank",
        "sector",
        "symbol",
        "side",
        "advisor_weight_%",
        "portfolio_role",
        "final_score",
        "ensemble_probability",
        "daily_50_200_state",
        "daily_50_200_gap",
        "relative_oscillator",
        "current_regime_fwd6_excess_%",
        "fake_breakout_rate_%",
        "trend_quality_score",
        "action_note",
    ]
    return frame[[c for c in cols if c in frame.columns]].sort_values("advisor_weight_%", ascending=False)


def build_feature_family_summary(feature_importance: pd.DataFrame) -> pd.DataFrame:
    if feature_importance.empty or "family" not in feature_importance:
        return pd.DataFrame()
    summary = (
        feature_importance.groupby("family")
        .agg(
            feature_count=("feature", "count"),
            total_importance=("importance", "sum"),
            mean_importance=("importance", "mean"),
        )
        .sort_values("total_importance", ascending=False)
    )
    total = float(summary["total_importance"].sum())
    summary["importance_share_%"] = summary["total_importance"] / total * 100.0 if total > 0 else np.nan
    return summary


def build_fundamental_feature_audit(feature_importance: pd.DataFrame) -> pd.DataFrame:
    rows = []
    audited = [
        ("cap_weighted_surprise_pct_lag1", "earnings_surprise", "allowed", "Prior-quarter cap-weighted EPS surprise."),
        ("cap_weighted_surprise_pct_lag1_change", "earnings_surprise", "allowed", "Change in prior-quarter cap-weighted EPS surprise versus the quarter before it."),
        ("beat_rate_lag1", "earnings_quality", "allowed", "Prior-quarter share of reporting companies that beat estimates."),
        ("beat_rate_lag1_change", "earnings_quality", "allowed", "Change in prior-quarter beat rate versus the quarter before it."),
        ("cap_weighted_quarterly_eps_yoy_pct_lag1", "earnings_growth", "allowed", "Prior-quarter cap-weighted YoY EPS growth."),
        ("cap_weighted_quarterly_eps_yoy_pct_lag1_change", "earnings_growth", "allowed", "Change in prior-quarter cap-weighted YoY EPS growth versus the quarter before it."),
        ("symbol_count_lag1", "coverage_metadata", "excluded", "Coverage/composition count; not an economic signal."),
        ("market_cap_share", "market_structure", "excluded", "Sector size/composition proxy; useful diagnostic, not earnings fundamental."),
        ("market_cap_proxy_total_qoq_pct", "market_structure", "excluded", "Current-market-cap-scaled proxy; can encode composition and price effects."),
        ("turnover_proxy", "market_structure", "excluded", "Liquidity/turnover proxy; not earnings fundamental."),
        ("dollar_volume_total_qoq_pct", "market_structure", "excluded", "Trading-volume proxy; not earnings fundamental."),
    ]
    importance = feature_importance.set_index("feature")["importance"] if not feature_importance.empty else pd.Series(dtype=float)
    for feature, family, status, reason in audited:
        rows.append(
            {
                "feature": feature,
                "family": family,
                "training_status": status,
                "in_model": bool(feature in importance.index),
                "importance": float(importance.get(feature, np.nan)) if feature in importance.index else np.nan,
                "reason": reason,
            }
        )
    return pd.DataFrame(rows)


def _topn_signal_series(predictions: pd.DataFrame, top_n: int) -> pd.DataFrame:
    if predictions.empty:
        return pd.DataFrame()
    rows = []
    for date, group in predictions.groupby("date"):
        selected = group.sort_values("ensemble_probability", ascending=False).head(top_n)
        rows.append(
            {
                "date": date,
                "topn_excess": selected["fwd_6m_excess"].mean(),
                "topn_fwd6": selected["fwd_6m"].mean(),
                "broad_fwd6": selected["fwd_6m_broad"].mean(),
                "leader_capture": selected["target_leader"].mean(),
            }
        )
    out = pd.DataFrame(rows).sort_values("date")
    out["rolling_12_signal_excess"] = out["topn_excess"].rolling(12, min_periods=6).mean()
    return out


def chart_live_rankings(live: pd.DataFrame) -> str:
    view = live.sort_values("final_score", ascending=True)
    fig = _vintage_fig((12, 5.8))
    ax = fig.add_subplot(111)
    _vintage_ax(ax)
    colors = [INK_GREEN if v == "Favored" else INK_RED if v == "Avoid" else INK_NAVY for v in view["verdict"]]
    y = np.arange(len(view))
    ax.barh(y, view["final_score"] * 100.0, color=colors, alpha=0.82)
    ax.set_yticks(y, labels=view["sector"], fontsize=8)
    ax.set_xlabel("Composite live score (0-100)", color=INK)
    ax.set_title("Live sector ranking: model probability + regime payoff + trend quality", loc="left", color=INK)
    for i, row in enumerate(view.itertuples(index=False)):
        ax.text(
            float(row.final_score) * 100.0 + 1.0,
            i,
            f"{row.verdict}  p={row.ensemble_probability:.2f}",
            va="center",
            fontsize=7,
            color=INK_MUTED,
        )
    ax.set_xlim(0, max(105, float(view["final_score"].max() * 115.0)))
    return _fig_b64(fig)


def chart_fake_breakouts(trend_quality: pd.DataFrame) -> str:
    view = trend_quality.sort_values("fake_breakout_rate_%", ascending=True)
    fig = _vintage_fig((12, 5.6))
    ax = fig.add_subplot(111)
    _vintage_ax(ax)
    y = np.arange(len(view))
    ax.barh(y, view["fake_breakout_rate_%"], color=INK_RED, alpha=0.80)
    ax.set_yticks(y, labels=view.index, fontsize=8)
    ax.set_xlabel("Fake breakout / whipsaw rate (% of crosses)", color=INK)
    ax.set_title("Where sector breakouts fail most often", loc="left", color=INK)
    for i, (_, row) in enumerate(view.iterrows()):
        ax.text(
            float(row["fake_breakout_rate_%"]) + 1.0,
            i,
            f"{float(row['crosses_per_decade']):.1f} crosses/decade",
            va="center",
            fontsize=7,
            color=INK_MUTED,
        )
    ax.margins(x=0.18)
    return _fig_b64(fig)


def chart_trend_quality(trend_quality: pd.DataFrame) -> str:
    view = trend_quality.dropna(subset=["fake_breakout_rate_%", "avg_uptrend_run_m", "trend_quality_score"])
    fig = _vintage_fig((9.2, 6.2))
    ax = fig.add_subplot(111)
    _vintage_ax(ax)
    sizes = 90 + 280 * view["trend_quality_score"].clip(0, 1)
    ax.scatter(
        view["fake_breakout_rate_%"],
        view["avg_uptrend_run_m"],
        s=sizes,
        c=view["trend_efficiency_12m"],
        cmap="viridis",
        edgecolor=INK,
        linewidth=0.7,
        alpha=0.85,
    )
    for sector, row in view.iterrows():
        ax.annotate(sector, (row["fake_breakout_rate_%"], row["avg_uptrend_run_m"]), xytext=(4, 4), textcoords="offset points", fontsize=7, color=INK)
    ax.set_xlabel("Fake breakout rate % (lower is cleaner)", color=INK)
    ax.set_ylabel("Average uptrend run, months", color=INK)
    ax.set_title("Which sectors trend cleanly vs chop", loc="left", color=INK)
    return _fig_b64(fig)


def chart_regime_heatmap(regime_payoff: pd.DataFrame, current_regime: str | None) -> str:
    view = regime_payoff.copy()
    fig = _vintage_fig((13, 6.2))
    ax = fig.add_subplot(111)
    _vintage_ax(ax)
    ax.grid(False)
    im = ax.imshow(view.to_numpy(), aspect="auto", cmap="RdYlGn", vmin=-8, vmax=8)
    labels = [c if len(c) < 24 else c[:22] + ".." for c in view.columns]
    ax.set_xticks(range(len(labels)), labels=labels, rotation=30, ha="right", fontsize=7)
    ax.set_yticks(range(len(view.index)), labels=view.index, fontsize=8)
    ax.set_title("Sector 6m excess return by macro regime", loc="left", color=INK)
    for i in range(view.shape[0]):
        for j in range(view.shape[1]):
            val = view.iloc[i, j]
            if pd.notna(val):
                ax.text(j, i, f"{val:+.1f}", ha="center", va="center", fontsize=6.5, color=INK)
    if current_regime in view.columns:
        j = list(view.columns).index(current_regime)
        ax.axvline(j - 0.5, color=INK, lw=1.2)
        ax.axvline(j + 0.5, color=INK, lw=1.2)
    cb = fig.colorbar(im, ax=ax, fraction=0.024, pad=0.02)
    cb.set_label("Avg fwd 6m excess return, pp", color=INK, fontsize=8)
    cb.ax.tick_params(colors=INK, labelsize=7)
    return _fig_b64(fig)


def chart_walkforward(predictions: pd.DataFrame, top_n: int) -> str:
    signal = _topn_signal_series(predictions, top_n)
    fig = _vintage_fig((12, 5.5))
    ax = fig.add_subplot(111)
    _vintage_ax(ax)
    if signal.empty:
        ax.text(0.5, 0.5, "No walk-forward predictions available", ha="center", va="center", color=INK)
    else:
        colors = np.where(signal["topn_excess"] >= 0, INK_GREEN, INK_RED)
        ax.bar(signal["date"], signal["topn_excess"] * 100.0, width=25, color=colors, alpha=0.42, label="Signal-month fwd 6m excess")
        ax.plot(signal["date"], signal["rolling_12_signal_excess"] * 100.0, color=INK_NAVY, lw=1.4, label="12-signal rolling mean")
        ax.axhline(0, color=INK, lw=0.8)
        ax.legend(fontsize=7, facecolor=PAPER, edgecolor=GRID_MAJOR)
    ax.set_ylabel("Forward 6m excess return, pp", color=INK)
    ax.set_title(f"Walk-forward top-{top_n} sector basket: out-of-sample excess return", loc="left", color=INK)
    return _fig_b64(fig)


def chart_feature_importance(feature_importance: pd.DataFrame) -> str:
    view = feature_importance.head(20).sort_values("importance", ascending=True)
    fig = _vintage_fig((12, 6.2))
    ax = fig.add_subplot(111)
    _vintage_ax(ax)
    y = np.arange(len(view))
    ax.barh(y, view["importance"] * 100.0, color=INK_AMBER, alpha=0.85)
    ax.set_yticks(y, labels=view["feature"], fontsize=7)
    ax.set_xlabel("ExtraTrees importance x 100", color=INK)
    ax.set_title("Top model inputs: what the classifier used", loc="left", color=INK)
    return _fig_b64(fig)


def chart_oscillators(live: pd.DataFrame) -> str:
    view = live.sort_values("relative_oscillator", ascending=True)
    fig = _vintage_fig((12, 5.4))
    ax = fig.add_subplot(111)
    _vintage_ax(ax)
    colors = [INK_GREEN if v >= 0 else INK_RED for v in view["relative_oscillator"]]
    y = np.arange(len(view))
    ax.barh(y, view["relative_oscillator"], color=colors, alpha=0.80)
    ax.set_yticks(y, labels=view["sector"], fontsize=8)
    ax.axvline(0, color=INK, lw=0.8)
    ax.set_xlim(-1.05, 1.05)
    ax.set_xlabel("Relative sector momentum oscillator (-1 to +1)", color=INK)
    ax.set_title("Current sector momentum oscillation versus broad market", loc="left", color=INK)
    return _fig_b64(fig)


def chart_daily_cross_frequency(summary: pd.DataFrame) -> str:
    if summary.empty:
        fig = _vintage_fig((10, 4))
        ax = fig.add_subplot(111)
        _vintage_ax(ax)
        ax.text(0.5, 0.5, "No daily 50/200 cross data available", ha="center", va="center", color=INK)
        return _fig_b64(fig)
    view = summary.sort_values("crosses_per_year", ascending=True)
    fig = _vintage_fig((12, 5.8))
    ax = fig.add_subplot(111)
    _vintage_ax(ax)
    y = np.arange(len(view))
    ax.barh(y, view["crosses_per_year"], color=INK_AMBER, alpha=0.86)
    ax.set_yticks(y, labels=view.index, fontsize=8)
    ax.set_xlabel("Daily 50/200 crosses per year", color=INK)
    ax.set_title("How often true daily 50/200 sector crosses happen", loc="left", color=INK)
    for i, (_, row) in enumerate(view.iterrows()):
        ax.text(
            float(row["crosses_per_year"]) + 0.02,
            i,
            f"{float(row['events']):.0f} events · {float(row['whipsaw_rate_%']):.0f}% fakes",
            va="center",
            fontsize=7,
            color=INK_MUTED,
        )
    ax.margins(x=0.22)
    return _fig_b64(fig)


def chart_cross_lead_summary(summary: pd.DataFrame) -> str:
    if summary.empty:
        fig = _vintage_fig((10, 4))
        ax = fig.add_subplot(111)
        _vintage_ax(ax)
        ax.text(0.5, 0.5, "No cross lead summary available", ha="center", va="center", color=INK)
        return _fig_b64(fig)
    view = summary[summary["environment_family"].eq("Dalio quadrant")].copy()
    if view.empty:
        view = summary.copy()
    view = view.sort_values("next_any_cross_rate_%", ascending=True)
    fig = _vintage_fig((12, 5.4))
    ax = fig.add_subplot(111)
    _vintage_ax(ax)
    y = np.arange(len(view))
    ax.barh(y - 0.18, view["next_golden_cross_rate_%"], height=0.36, color=INK_GREEN, alpha=0.78, label="Next-month golden")
    ax.barh(y + 0.18, view["next_death_cross_rate_%"], height=0.36, color=INK_RED, alpha=0.78, label="Next-month death")
    labels = [str(v)[:38] for v in view["environment"]]
    ax.set_yticks(y, labels=labels, fontsize=7)
    ax.set_xlabel("Next-month cross rate across sector-months (%)", color=INK)
    ax.set_title("Which Dalio environments lead to 50/200 cross events", loc="left", color=INK)
    ax.legend(fontsize=7, facecolor=PAPER, edgecolor=GRID_MAJOR)
    return _fig_b64(fig)


def chart_sizing_advisor(advisor: pd.DataFrame) -> str:
    if advisor.empty:
        fig = _vintage_fig((10, 4))
        ax = fig.add_subplot(111)
        _vintage_ax(ax)
        ax.text(0.5, 0.5, "No sizing advisor rows available", ha="center", va="center", color=INK)
        return _fig_b64(fig)
    view = advisor.sort_values("advisor_weight_%", ascending=True)
    fig = _vintage_fig((12, 5.4))
    ax = fig.add_subplot(111)
    _vintage_ax(ax)
    colors = [INK_GREEN if value > 0 else INK_RED if value < 0 else INK_MUTED for value in view["advisor_weight_%"]]
    y = np.arange(len(view))
    ax.barh(y, view["advisor_weight_%"], color=colors, alpha=0.84)
    ax.set_yticks(y, labels=view["sector"], fontsize=8)
    ax.axvline(0, color=INK, lw=0.8)
    ax.set_xlabel("Suggested portfolio weight (%)", color=INK)
    ax.set_title("Sizing advisor: long/short sector sleeve", loc="left", color=INK)
    for i, (_, row) in enumerate(view.iterrows()):
        weight = float(row["advisor_weight_%"])
        ax.text(
            weight + (0.35 if weight >= 0 else -0.35),
            i,
            str(row["side"]),
            va="center",
            ha="left" if weight >= 0 else "right",
            fontsize=7,
            color=INK_MUTED,
        )
    ax.margins(x=0.18)
    return _fig_b64(fig)


def _build_current_snapshot(
    panel: pd.DataFrame,
    live_rankings: pd.DataFrame,
    trend_quality: pd.DataFrame,
    macro_bundle: MacroBundle,
    *,
    history_through: str | None = None,
    live_price_through: str | None = None,
    live_source: str | None = None,
) -> dict[str, Any]:
    latest = pd.Timestamp(panel["date"].max())
    as_of = live_price_through or latest.strftime("%Y-%m-%d")
    latest_panel = panel.loc[panel["date"] == latest]
    best = live_rankings.head(3)
    avoid = live_rankings.tail(3).sort_values("final_score")
    fake = trend_quality.sort_values("fake_breakout_rate_%", ascending=False).head(3)
    trending = trend_quality.sort_values("trend_quality_score", ascending=False).head(3)
    forecast = macro_bundle.regime_forecast_12m.head(3)
    return {
        "as_of": as_of,
        "signal_month": latest.strftime("%Y-%m"),
        "current_gmm_regime": str(latest_panel["gmm_regime"].dropna().iloc[0]) if latest_panel["gmm_regime"].notna().any() else "Unknown",
        "current_dalio_quadrant": str(latest_panel["dalio_quadrant"].dropna().iloc[0]) if latest_panel["dalio_quadrant"].notna().any() else "Unknown",
        "market_health": _safe_float(latest_panel["market_health"].dropna().iloc[0]) if latest_panel["market_health"].notna().any() else None,
        "sector_breadth": _safe_float(latest_panel["sector_breadth"].dropna().iloc[0]) if latest_panel["sector_breadth"].notna().any() else None,
        "favored_sectors": best["sector"].tolist(),
        "avoid_sectors": avoid["sector"].tolist(),
        "most_fake_breakouts": fake.index.tolist(),
        "cleanest_trending": trending.index.tolist(),
        "regime_forecast_12m": {str(k): float(v) for k, v in forecast.items()},
        "history_through": history_through,
        "live_price_through": live_price_through,
        "live_source": live_source,
    }


def _css() -> str:
    return f"""
:root {{
  --paper: {PAPER};
  --page: {PAGE};
  --ink: {INK};
  --muted: {INK_MUTED};
  --navy: {INK_NAVY};
  --red: {INK_RED};
  --green: {INK_GREEN};
  --amber: {INK_AMBER};
  --grid-major: {GRID_MAJOR};
  --grid-minor: {GRID_MINOR};
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  color: var(--ink);
  font-family: Georgia, "Times New Roman", serif;
  background-color: var(--page);
  background-image:
    linear-gradient(var(--grid-minor) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid-minor) 1px, transparent 1px),
    linear-gradient(var(--grid-major) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid-major) 1px, transparent 1px);
  background-size: 12px 12px, 12px 12px, 60px 60px, 60px 60px;
  background-position: -1px -1px;
}}
main {{
  max-width: 1240px;
  margin: 0 auto;
  padding: 30px 18px 48px;
}}
header, section {{
  background: rgba(244, 236, 211, 0.94);
  border: 1px solid rgba(46, 36, 23, 0.28);
  box-shadow: 0 10px 26px rgba(46, 36, 23, 0.10);
  margin: 0 0 18px;
  padding: 22px;
}}
h1, h2 {{
  margin: 0 0 10px;
  line-height: 1.08;
  letter-spacing: 0;
}}
h1 {{ font-size: clamp(30px, 5vw, 58px); }}
h2 {{ font-size: 24px; }}
p {{ margin: 8px 0 12px; color: var(--muted); line-height: 1.52; }}
.subtitle {{ font-size: 17px; max-width: 980px; color: var(--ink); }}
.meta, .note {{ font-size: 13px; color: var(--muted); }}
.kv-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 10px;
  margin-top: 14px;
}}
.kv {{
  border-top: 1px solid rgba(46, 36, 23, 0.22);
  padding-top: 8px;
}}
.k {{ display: block; font-size: 12px; color: var(--muted); }}
.v {{ display: block; font-size: 18px; color: var(--ink); font-weight: 700; margin-top: 3px; }}
.chart {{ margin: 16px 0; }}
.chart img {{ width: 100%; display: block; border: 1px solid rgba(46, 36, 23, 0.26); }}
figcaption {{ color: var(--muted); font-size: 12px; margin-top: 6px; }}
table {{
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 12px;
  background: rgba(244, 236, 211, 0.7);
}}
th, td {{
  border-bottom: 1px solid rgba(46, 36, 23, 0.18);
  padding: 7px 8px;
  text-align: right;
  vertical-align: top;
}}
th:first-child, td:first-child {{ text-align: left; }}
thead th {{
  color: var(--ink);
  border-bottom: 2px solid rgba(46, 36, 23, 0.35);
}}
.split {{
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
}}
@media (max-width: 850px) {{
  .split {{ grid-template-columns: 1fr; }}
  header, section {{ padding: 16px; }}
}}
"""


def build_html_report(result: ResearchResult, top_n: int) -> str:
    live = result.model.live_rankings
    snapshot = result.current_snapshot
    top3 = ", ".join(snapshot["favored_sectors"])
    avoid3 = ", ".join(snapshot["avoid_sectors"])
    fake3 = ", ".join(snapshot["most_fake_breakouts"])
    trend3 = ", ".join(snapshot["cleanest_trending"])
    metrics_view = result.model.metrics.copy()
    for col in ["target_rate", "roc_auc", "brier", "precision_at_50", "recall_at_50", "topn_fwd6", "broad_fwd6", "topn_excess", "excess_hit_rate", "leader_capture_rate"]:
        if col in metrics_view:
            metrics_view[col] = pd.to_numeric(metrics_view[col], errors="coerce")

    charts = {
        "live": chart_live_rankings(live),
        "fake": chart_fake_breakouts(result.trend_quality),
        "trend": chart_trend_quality(result.trend_quality),
        "regime": chart_regime_heatmap(result.regime_payoff, snapshot["current_gmm_regime"]),
        "wf": chart_walkforward(result.model.predictions, top_n),
        "imp": chart_feature_importance(result.model.feature_importance),
        "osc": chart_oscillators(live),
        "daily_cross": chart_daily_cross_frequency(result.daily_cross_sector_summary),
        "cross_lead": chart_cross_lead_summary(result.daily_cross_lead_summary),
        "sizing": chart_sizing_advisor(result.sizing_advisor),
    }

    now_rows = {
        "As of": snapshot["as_of"],
        "Signal month": snapshot.get("signal_month") or snapshot["as_of"][:7],
        "Live price source": snapshot.get("live_source") or "stock sector panel",
        "Live prices through": snapshot.get("live_price_through") or snapshot["as_of"],
        "Historical panel through": snapshot.get("history_through") or snapshot["as_of"],
        "Macro regime": snapshot["current_gmm_regime"],
        "Dalio quadrant": snapshot["current_dalio_quadrant"],
        "Market health": _fmt_num(snapshot["market_health"], 1),
        "Sector breadth": _fmt_pct(snapshot["sector_breadth"], 0),
        "Favored sectors": top3,
        "Avoid sectors": avoid3,
        "Most fake breakouts": fake3,
        "Cleanest trends": trend3,
        "Daily 50/200 events": f"{len(result.daily_cross_events):,}",
        "Features in model": f"{len(result.model.feature_columns)}",
    }
    now_html = "".join(
        f'<div class="kv"><span class="k">{html.escape(k)}</span><span class="v">{html.escape(str(v))}</span></div>'
        for k, v in now_rows.items()
    )

    live_table = live[
        [
            "rank",
            "verdict",
            "sector",
            "final_score",
            "ensemble_probability",
            "current_regime_fwd6_excess_%",
            "sector_oscillator",
            "relative_oscillator",
            "daily_50_200_state",
            "daily_50_200_gap",
            "fake_breakout_rate_%",
            "trend_quality_score",
            "young_cross_risk",
        ]
    ].set_index("rank")
    live_table[["final_score", "ensemble_probability", "trend_quality_score", "young_cross_risk"]] = live_table[
        ["final_score", "ensemble_probability", "trend_quality_score", "young_cross_risk"]
    ].astype(float)

    forecast_table = result.macro_bundle.regime_forecast_12m.head(6).rename("probability").to_frame()
    sizing_table = result.sizing_advisor.set_index("rank") if not result.sizing_advisor.empty else pd.DataFrame()
    cross_sector_table = result.daily_cross_sector_summary.copy()
    cross_regime_table = result.daily_cross_regime_summary.copy()
    cross_lead_table = result.daily_cross_lead_summary.copy()
    family_summary = build_feature_family_summary(result.model.feature_importance)
    fundamental_audit = build_fundamental_feature_audit(result.model.feature_importance)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Sector Dalio Regime Model</title>
  <style>{_css()}</style>
</head>
<body>
<main>
  <header>
    <h1>Sector Regime Research</h1>
    <p class="subtitle">Dalio-style growth, inflation, liquidity, credit, volatility, commodities, forward macro and lagged sector fundamentals joined into a walk-forward sector leadership classifier.</p>
    <p class="meta">Target: top-tercile next-6-month sector excess return versus the broad sector basket. Validation is expanding walk-forward with a {DEFAULT_LABEL_HORIZON}-month label embargo. Sector indices are built from the available current universe, so absolute long-run index levels remain survivorship-biased; the research emphasis is cross-sector behavior, fake breakouts, trend persistence and regime-conditioned leadership. The live row uses sector ETF prices when they are newer than the stock-built sector panel.</p>
  </header>

  <section>
    <h2>Current Read</h2>
    <div class="kv-grid">{now_html}</div>
    {_img(charts["live"], "Live sector ranking")}
    {_table(live_table, float_fmt="{:.3f}")}
  </section>

  <section>
    <h2>Sizing Advisor</h2>
    <p>The advisor converts the live ensemble ranking into a long/short sector sleeve. Gross long and short exposure come from market health; sector weights are scaled by ensemble confidence, volatility, and the true daily 50/200 trend state. It is an allocation guide, not an execution order.</p>
    {_img(charts["sizing"], "Long/short sizing advisor")}
    {_table(sizing_table, float_fmt="{:.3f}")}
  </section>

  <section>
    <h2>Momentum Oscillation</h2>
    <p>Each sector has a bounded oscillator from -1 to +1, computed from 3, 6 and 12 month causal momentum z-scores. The chart below uses relative sector price versus the broad sector basket, so it shows leadership momentum rather than market beta alone.</p>
    {_img(charts["osc"], "Current relative momentum oscillators")}
  </section>

  <section>
    <h2>Daily 50/200 Crosses</h2>
    <p>This section uses true daily sector ETF prices, not the monthly stock-built sector panel. A golden cross is SMA50 moving above SMA200; a death cross is SMA50 moving below SMA200. Each event is tagged with the last completed macro month to avoid using future same-month macro data.</p>
    {_img(charts["daily_cross"], "Daily 50/200 cross frequency by sector")}
    {_table(cross_sector_table, float_fmt="{:.2f}")}
  </section>

  <section>
    <h2>Which Environments Lead Crosses</h2>
    <p>The lead table asks which completed macro environments are followed by sector 50/200 crosses in the next month. This is the direct answer to whether crosses happen after expansion, reflation, stagflation, stress, or late-cycle conditions.</p>
    {_img(charts["cross_lead"], "Next-month 50/200 cross rate by environment")}
    {_table(cross_lead_table, max_rows=24, float_fmt="{:.2f}")}
  </section>

  <section>
    <h2>Cross Outcomes By Regime</h2>
    <p>After detecting each daily event, the report measures what happened over the following 63 and 126 trading days and flags whipsaws. This verifies whether the Dalio matrix and statistical regimes historically supported or punished the cross.</p>
    {_table(cross_regime_table, max_rows=36, float_fmt="{:.2f}")}
  </section>

  <section>
    <h2>Regime Payoff Map</h2>
    <p>The heatmap shows average forward 6-month sector excess return by statistical macro regime. The current regime column is boxed. This is the Dalio-style layer: growth/inflation/liquidity/credit state first, sector response second.</p>
    {_img(charts["regime"], "Sector payoff by macro regime")}
    {_table(result.regime_payoff, float_fmt="{:.1f}")}
  </section>

  <section>
    <h2>Fake Breakouts</h2>
    <p>A fake breakout is a golden/death cross that reverses within four months or never travels a 5% favorable move before the opposite cross. This identifies where trend signals are most likely to be noise.</p>
    {_img(charts["fake"], "Fake breakout rate by sector")}
    {_table(result.trend_quality.sort_values("fake_breakout_rate_%", ascending=False), float_fmt="{:.2f}")}
  </section>

  <section>
    <h2>Trend Quality</h2>
    <p>The cleanest-trending sectors combine lower whipsaw rate, longer trend runs, better 12-month path efficiency and stronger forward returns after golden crosses.</p>
    {_img(charts["trend"], "Trend quality scatter")}
  </section>

  <section>
    <h2>Walk-Forward Model</h2>
    <p>The classifier is not selected on the holdout. The validation stream fits only on prior months and predicts the next calendar year. The plotted bar is what the top-{top_n} predicted sectors went on to earn versus the broad sector basket over the following six months.</p>
    {_img(charts["wf"], "Walk-forward top sector excess return")}
    {_table(metrics_view, float_fmt="{:.3f}")}
  </section>

  <section>
    <h2>Model Inputs</h2>
    <p>ExtraTrees importance from the final model stack shows which features carried the most splitting power. Coverage/count metadata and market-structure proxies such as symbol counts, market-cap share, turnover, and dollar-volume are excluded from the predictive feature space; sector dummies are retained as sector controls, not interpreted as fundamentals.</p>
    {_img(charts["imp"], "Top feature importance")}
    {_table(family_summary, float_fmt="{:.4f}")}
    {_table(fundamental_audit.set_index("feature"), float_fmt="{:.4f}")}
    {_table(result.model.feature_importance.set_index("feature").head(35), float_fmt="{:.4f}")}
  </section>

  <section>
    <h2>Regime Forecast</h2>
    <p>The macro-state forecast is the Markov transition forecast from the current statistical macro regime. It is a state-prior, not a price target.</p>
    {_table(forecast_table, float_fmt="{:.3f}")}
  </section>

  <section>
    <h2>Research Controls</h2>
    <p>Features use information available at the signal month. Forward macro series with history, VIX, credit, liquidity, rates, commodities, curve and inflation expectations are model inputs. Fed dot-plot levels are intentionally not backtested here because the local FRED series exposes the current vintage, not a historical vintage trail. Lagged fundamentals from the quarterly sector factor panel are used where available; current snapshot fundamentals are reserved for live context.</p>
  </section>
</main>
</body>
</html>"""


def build_research(
    *,
    project_root: str | Path | None = None,
    fundamentals_dir: str | Path | None = "investme_sp500_data",
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    fast: int = DEFAULT_FAST,
    slow: int = DEFAULT_SLOW,
    refresh_sector_cache: bool = False,
    holdout_start: str = DEFAULT_HOLDOUT_START,
    train_years: int = DEFAULT_TRAIN_YEARS,
    label_horizon: int = DEFAULT_LABEL_HORIZON,
    top_n: int = DEFAULT_TOP_N,
    min_feature_coverage: float = DEFAULT_MIN_FEATURE_COVERAGE,
) -> Path:
    root = resolve_project_root(project_root)
    out_dir = Path(output_dir)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("[1/7] Building sector/month regime panel...")
    panel, trend_quality, cross_events, macro_bundle = build_sector_regime_panel(
        root=root,
        fundamentals_dir=fundamentals_dir,
        fast=fast,
        slow=slow,
        refresh_sector_cache=refresh_sector_cache,
        label_horizon=label_horizon,
    )
    print(f"      panel rows={len(panel):,}, sectors={panel['sector'].nunique()}, months={panel['date'].nunique()}")

    print("[1b/7] Building current sector ETF live overlay...")
    live_overlay, live_macro_bundle, live_price_through = build_live_etf_overlay_panel(root, fast, slow)
    if not live_overlay.empty and live_overlay["date"].max() > panel["date"].max():
        live_macro = live_macro_bundle or macro_bundle
        live_source = "sector_etf_cache"
        print(
            "      live overlay rows="
            f"{len(live_overlay):,}, months={live_overlay['date'].nunique()}, "
            f"latest_month={pd.Timestamp(live_overlay['date'].max()).strftime('%Y-%m')}, "
            f"prices_through={live_price_through}"
        )
    else:
        live_overlay = pd.DataFrame()
        live_macro = macro_bundle
        live_source = "stock_sector_panel"
        live_price_through = panel["date"].max().strftime("%Y-%m-%d")
        print("      no newer ETF overlay available; using stock sector panel for live row")

    print("[2/8] Running daily 50/200 sector ETF crossover study...")
    daily_cross_events, daily_cross_sector_summary, daily_cross_regime_summary = build_daily_50200_cross_study(root, live_macro)
    daily_cross_lead_summary = build_daily_cross_lead_summary(live_overlay, daily_cross_events) if not live_overlay.empty else pd.DataFrame()
    print(
        "      daily cross events="
        f"{len(daily_cross_events):,}, sectors={daily_cross_events['sector'].nunique() if not daily_cross_events.empty else 0}"
    )

    print("[3/8] Running walk-forward sector leadership model...")
    model = run_walk_forward_model(
        panel,
        live_panel=live_overlay,
        holdout_start=holdout_start,
        train_years=train_years,
        label_horizon=label_horizon,
        top_n=top_n,
        min_feature_coverage=min_feature_coverage,
    )
    print(f"      features={len(model.feature_columns)}, validation rows={len(model.predictions):,}, holdout rows={len(model.holdout_predictions):,}")

    print("[4/8] Building regime payoff, daily trend state, and sizing advisor...")
    regime_payoff = build_regime_payoff(panel)
    live_rankings = enrich_live_rankings(model.live_rankings, trend_quality, regime_payoff)
    daily_state = latest_daily_50200_state(root)
    if not daily_state.empty:
        live_rankings = live_rankings.merge(daily_state, on="sector", how="left", suffixes=("", "_daily"))
    model.live_rankings = live_rankings
    sizing_advisor = build_sizing_advisor(live_rankings, top_n=top_n)
    snapshot_panel = live_overlay if not live_overlay.empty else panel
    snapshot = _build_current_snapshot(
        snapshot_panel,
        live_rankings,
        trend_quality,
        live_macro,
        history_through=panel["date"].max().strftime("%Y-%m-%d"),
        live_price_through=live_price_through,
        live_source=live_source,
    )

    print("[5/8] Writing CSV/JSON research outputs...")
    panel.to_csv(out_dir / "sector_regime_panel.csv", index=False)
    trend_quality.to_csv(out_dir / "sector_trend_quality.csv")
    trend_quality.sort_values("fake_breakout_rate_%", ascending=False).to_csv(out_dir / "fake_breakouts_by_sector.csv")
    cross_events.to_csv(out_dir / "cross_events.csv", index=False)
    daily_cross_events.to_csv(out_dir / "daily_50_200_cross_events.csv", index=False)
    daily_cross_sector_summary.to_csv(out_dir / "daily_50_200_cross_by_sector.csv")
    daily_cross_regime_summary.to_csv(out_dir / "daily_50_200_cross_by_regime.csv", index=False)
    daily_cross_lead_summary.to_csv(out_dir / "daily_50_200_cross_lead_environments.csv", index=False)
    sizing_advisor.to_csv(out_dir / "sizing_advisor.csv", index=False)
    regime_payoff.to_csv(out_dir / "sector_regime_payoff.csv")
    model.predictions.to_csv(out_dir / "walkforward_predictions.csv", index=False)
    model.holdout_predictions.to_csv(out_dir / "holdout_predictions.csv", index=False)
    model.live_rankings.to_csv(out_dir / "live_sector_rankings.csv", index=False)
    model.metrics.to_csv(out_dir / "model_metrics.csv")
    model.feature_importance.to_csv(out_dir / "feature_importance.csv", index=False)
    build_feature_family_summary(model.feature_importance).to_csv(out_dir / "feature_family_importance.csv")
    build_fundamental_feature_audit(model.feature_importance).to_csv(out_dir / "fundamental_feature_audit.csv", index=False)
    model_config = {
        "target": "top-tercile next-6-month sector excess return",
        "ensemble": {
            "logit": {
                "model": "LogisticRegression",
                "solver": "lbfgs",
                "max_iter": 2000,
                "class_weight": "balanced",
            },
            "extra_trees": {
                "model": "ExtraTreesClassifier",
                "n_estimators": 500,
                "max_depth": 7,
                "min_samples_leaf": 25,
                "min_samples_split": 50,
                "class_weight": "balanced",
            },
            "hist_gradient": {
                "model": "HistGradientBoostingClassifier",
                "learning_rate": 0.04,
                "max_iter": 250,
                "max_leaf_nodes": 15,
                "min_samples_leaf": 35,
                "l2_regularization": 2.0,
            },
        },
        "ensemble_combination": "simple average of model probabilities",
        "train_years": train_years,
        "label_horizon_months": label_horizon,
        "holdout_start": holdout_start,
        "min_feature_coverage": min_feature_coverage,
        "earnings_fundamental_features": EARNINGS_FUNDAMENTAL_FEATURES,
        "structure_diagnostic_features": STRUCTURE_DIAGNOSTIC_FEATURES,
        "excluded_predictive_feature_parts": list(EXCLUDED_PREDICTIVE_FEATURE_PARTS),
        "note": "Coverage/count metadata and market-structure proxies are excluded from predictive features; they can be used for diagnostics only.",
    }
    (out_dir / "model_config.json").write_text(json.dumps(model_config, indent=2), encoding="utf-8")
    (out_dir / "current_regime_snapshot.json").write_text(
        json.dumps(
            {
                **snapshot,
                "generated_at": datetime.now(UTC).isoformat(),
                "holdout_start": holdout_start,
                "label_horizon_months": label_horizon,
                "top_n": top_n,
                "daily_cross_events": int(len(daily_cross_events)),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print("[6/8] Rendering plotting-paper HTML report...")
    result = ResearchResult(
        panel=panel,
        trend_quality=trend_quality,
        fake_breakouts=trend_quality.sort_values("fake_breakout_rate_%", ascending=False),
        regime_payoff=regime_payoff,
        daily_cross_events=daily_cross_events,
        daily_cross_sector_summary=daily_cross_sector_summary,
        daily_cross_regime_summary=daily_cross_regime_summary,
        daily_cross_lead_summary=daily_cross_lead_summary,
        sizing_advisor=sizing_advisor,
        model=model,
        macro_bundle=live_macro,
        current_snapshot=snapshot,
        output_dir=out_dir,
    )
    html_doc = build_html_report(result, top_n)
    out_path = out_dir / "index.html"
    out_path.write_text(html_doc, encoding="utf-8")
    print(f"[7/8] Wrote {out_path}")
    print("[8/8] Done.")
    return out_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the sector Dalio-style regime classifier and research report.")
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--fundamentals-dir", default="investme_sp500_data")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--fast", type=int, default=DEFAULT_FAST)
    parser.add_argument("--slow", type=int, default=DEFAULT_SLOW)
    parser.add_argument("--refresh-sector-cache", action="store_true")
    parser.add_argument("--holdout-start", default=DEFAULT_HOLDOUT_START)
    parser.add_argument("--train-years", type=int, default=DEFAULT_TRAIN_YEARS)
    parser.add_argument("--label-horizon", type=int, default=DEFAULT_LABEL_HORIZON)
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    parser.add_argument("--min-feature-coverage", type=float, default=DEFAULT_MIN_FEATURE_COVERAGE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_research(
        project_root=args.project_root,
        fundamentals_dir=args.fundamentals_dir,
        output_dir=args.output_dir,
        fast=args.fast,
        slow=args.slow,
        refresh_sector_cache=args.refresh_sector_cache,
        holdout_start=args.holdout_start,
        train_years=args.train_years,
        label_horizon=args.label_horizon,
        top_n=args.top_n,
        min_feature_coverage=args.min_feature_coverage,
    )


if __name__ == "__main__":
    main()
