"""Dalio-style market-regime analysis from macro data and corporate fundamentals.

This module answers three questions the existing macro report does not:

1.  Where are we in the *corporate debt cycle*?  It aggregates the balance
    sheets, income statements and cash-flow statements of every company in
    ``fundamentals_history/sp500_data`` into a single "corporate sector"
    panel (leverage, interest coverage, margins, capital-allocation choices)
    so we can see leveraging vs. de-leveraging phases the way Ray Dalio frames
    them in *Principles for Navigating Big Debt Crises*.

2.  Which regime are we in, and what is likely *next*?  It builds a
    rules-based Dalio growth/inflation quadrant, tags each de-leveraging
    episode as "beautiful" or "ugly", fits a statistical (Gaussian-mixture)
    latent-regime model on the macro/financial conditions, and turns the
    regime history into a Markov transition matrix to forecast the next state.

3.  Which decisions drove returns, and how long is the lag?  It runs a
    lead-lag study of policy / financial-condition / capital-allocation
    "drivers" against forward equity returns across 0-24 month horizons.

The output is a self-contained HTML report (with embedded PNG charts) written
to ``outputs/regime_analysis/``.

Run with::

    python build_regime_analysis.py
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
import warnings
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .data import resolve_project_root

# --------------------------------------------------------------------------- #
# Palette (kept consistent with the existing macro report aesthetic).
# --------------------------------------------------------------------------- #
PAGE_BACKGROUND = "#f7f2e8"
PANEL_BACKGROUND = "#fffdf8"
TEXT_COLOR = "#1b2430"
MUTED_TEXT_COLOR = "#5f6b76"
GRID_COLOR = "#d5cfc5"

QUADRANT_COLORS: dict[str, str] = {
    "Goldilocks (growth up, inflation down)": "#5f8f5b",
    "Reflation (growth up, inflation up)": "#b56b2d",
    "Stagflation (growth down, inflation up)": "#9a4a35",
    "Deflation (growth down, inflation down)": "#4f698c",
    "Indeterminate": "#9b8f77",
}

DEBT_PHASE_COLORS: dict[str, str] = {
    "Leveraging up": "#b56b2d",
    "Beautiful deleveraging": "#3f7f78",
    "Ugly deleveraging / deflationary": "#9a4a35",
    "Stable / neutral": "#9b8f77",
}

FUNDAMENTALS_DIR = Path("fundamentals_history") / "sp500_data"
MACRO_DAILY_CSV = Path("cache") / "macro_daily_1999.csv"
FRED_DIR = Path("fred")
OUTPUT_DIR = Path("outputs") / "regime_analysis"

# Minimum companies contributing to an aggregate quarter for it to be trusted.
MIN_COMPANIES_PER_QUARTER = 40


# --------------------------------------------------------------------------- #
# Small parsing helpers (AlphaVantage encodes missing values as "None"/"").
# --------------------------------------------------------------------------- #
def _to_float(value: object) -> float:
    if value is None:
        return np.nan
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text in {"", "None", "none", "N/A", "-", "nan"}:
        return np.nan
    try:
        return float(text)
    except ValueError:
        return np.nan


def _read_fred(root: Path, name: str) -> pd.Series:
    """Read a two-column FRED CSV into a float Series indexed by date."""
    path = root / FRED_DIR / f"{name}.csv"
    if not path.exists():
        return pd.Series(dtype="float64", name=name)
    frame = pd.read_csv(path)
    date_col, value_col = frame.columns[0], frame.columns[1]
    series = pd.Series(
        pd.to_numeric(frame[value_col], errors="coerce").to_numpy(),
        index=pd.to_datetime(frame[date_col], errors="coerce"),
        name=name,
    ).dropna()
    return series.sort_index()


def _month_end(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return index.to_period("M").to_timestamp("M")


# --------------------------------------------------------------------------- #
# 1. Macro / financial-conditions panel (monthly).
# --------------------------------------------------------------------------- #
def load_macro_panel(root: Path) -> pd.DataFrame:
    """Monthly macro panel: growth, inflation, rates, credit, valuation, risk."""
    daily = pd.read_csv(root / MACRO_DAILY_CSV, parse_dates=["date"]).set_index("date")
    daily = daily.sort_index()

    # Month-end snapshot of the daily macro store.
    monthly = daily.resample("ME").last()

    frame = pd.DataFrame(index=monthly.index)
    frame["equity_index"] = monthly["wilshire_total_market_index"]
    frame["cape"] = monthly["shiller_cape_ratio"]
    frame["mktcap_to_gdp"] = monthly["market_cap_to_gdp_pct"]
    frame["us_2y"] = monthly["us_2y_yield"]
    frame["us_10y"] = monthly["us_10y_yield"]
    frame["yield_curve_10y2y"] = monthly["us_10y_yield"] - monthly["us_2y_yield"]
    frame["cpi_yoy"] = monthly["cpi_yoy_pct"]
    frame["unemployment"] = monthly["unemployment_rate_pct"]
    frame["dxy"] = monthly["dxy_close"]
    frame["gold"] = monthly["gold_usd_per_oz"]
    frame["copper"] = monthly["copper_usd_per_lb"]
    frame["vix3m"] = monthly.get("vix3m_level")

    # FRED financial-conditions / policy series (weekly or daily) -> month end.
    def _fred_monthly(name: str) -> pd.Series:
        s = _read_fred(root, name)
        if s.empty:
            return pd.Series(index=frame.index, dtype="float64")
        return s.resample("ME").last().reindex(frame.index).ffill(limit=2)

    frame["nfci"] = _fred_monthly("NFCI")
    frame["t10y3m"] = _fred_monthly("T10Y3M")
    frame["hy_spread"] = _fred_monthly("BAMLH0A0HYM2")
    frame["policy_uncertainty"] = _fred_monthly("USEPUINDXD")
    frame["vix"] = _fred_monthly("VIXCLS")
    frame["consumer_sentiment"] = _fred_monthly("UMCSENT")

    # Core CPI YoY and industrial-production YoY, derived from FRED index levels.
    core = _read_fred(root, "CPILFESL").resample("ME").last()
    frame["core_cpi_yoy"] = (core / core.shift(12) - 1.0).mul(100).reindex(frame.index)
    indpro = _read_fred(root, "INDPRO").resample("ME").last()
    frame["indpro_yoy"] = (indpro / indpro.shift(12) - 1.0).mul(100).reindex(frame.index)

    return frame


# --------------------------------------------------------------------------- #
# 2. Aggregate corporate debt-cycle panel (quarterly -> monthly).
# --------------------------------------------------------------------------- #
# Fields summed across the whole universe each calendar quarter.
_BS_FIELDS = {
    "totalAssets": "total_assets",
    "totalLiabilities": "total_liabilities",
    "totalShareholderEquity": "equity",
    "shortLongTermDebtTotal": "debt_total_field",
    "longTermDebt": "long_term_debt",
    "currentDebt": "current_debt",
    "shortTermDebt": "short_term_debt",
    "currentLongTermDebt": "current_long_term_debt",
    "cashAndShortTermInvestments": "cash",
}
_INC_FIELDS = {
    "totalRevenue": "revenue",
    "netIncome": "net_income",
    "ebit": "ebit",
    "ebitda": "ebitda",
    "operatingIncome": "operating_income",
    "interestExpense": "interest_expense",
}
_CF_FIELDS = {
    "operatingCashflow": "operating_cash_flow",
    "capitalExpenditures": "capex",
    "dividendPayout": "dividends",
    "paymentsForRepurchaseOfCommonStock": "buybacks",
    "proceedsFromIssuanceOfLongTermDebtAndCapitalSecuritiesNet": "debt_issued",
}


def _quarter_period(date_str: str) -> pd.Timestamp | None:
    ts = pd.to_datetime(date_str, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.to_period("Q").to_timestamp("Q")


def _accumulate(reports: Iterable[dict], fields: dict[str, str], flows: dict[str, dict]):
    for rep in reports:
        q = _quarter_period(rep.get("fiscalDateEnding", ""))
        if q is None:
            continue
        bucket = flows.setdefault(q, {})
        bucket.setdefault("_n", set())
        for raw, canon in fields.items():
            val = _to_float(rep.get(raw))
            if not np.isnan(val):
                bucket[canon] = bucket.get(canon, 0.0) + val


def load_corporate_panel(root: Path, symbols: list[str] | None = None) -> pd.DataFrame:
    """Aggregate every company's statements into one corporate-sector panel.

    Dollar amounts are summed across the universe within each calendar quarter,
    then converted into aggregate ratios.  This treats the whole universe as one
    giant company -- exactly the lens Dalio uses when he talks about the debt of
    "the economy" rather than a single borrower.
    """
    fdir = root / FUNDAMENTALS_DIR
    if symbols is None:
        symbols = sorted(
            p.name[: -len("_balance_sheet.json")]
            for p in fdir.glob("*_balance_sheet.json")
        )

    flows: dict[pd.Timestamp, dict] = {}
    contributors: dict[pd.Timestamp, set] = {}

    def _load(sym: str, kind: str) -> list[dict]:
        path = fdir / f"{sym}_{kind}.json"
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return payload.get("data", {}).get("quarterlyReports", []) or []

    for sym in symbols:
        bs = _load(sym, "balance_sheet")
        inc = _load(sym, "income_statement")
        cf = _load(sym, "cash_flow")
        if not bs and not inc:
            continue
        # Track which quarters this symbol reports for (breadth / survivorship).
        for rep in bs:
            q = _quarter_period(rep.get("fiscalDateEnding", ""))
            if q is not None:
                contributors.setdefault(q, set()).add(sym)
        _accumulate(bs, _BS_FIELDS, flows)
        _accumulate(inc, _INC_FIELDS, flows)
        _accumulate(cf, _CF_FIELDS, flows)

    if not flows:
        return pd.DataFrame()

    rows = []
    for q in sorted(flows):
        d = flows[q]
        d["n_companies"] = len(contributors.get(q, set()))
        d["quarter"] = q
        rows.append(d)
    panel = pd.DataFrame(rows).set_index("quarter").sort_index()

    # Preferred total-debt measure, falling back through available components.
    def _col(name: str) -> pd.Series:
        if name in panel:
            return panel[name].astype("float64").fillna(0.0)
        return pd.Series(0.0, index=panel.index)

    debt = _col("debt_total_field")
    fallback = _col("long_term_debt") + _col("current_debt")
    panel["total_debt"] = debt.where(debt > 0, fallback)

    # Trailing-twelve-month flows for stable ratios.
    for col in ["revenue", "net_income", "ebit", "ebitda", "operating_income",
                "interest_expense", "operating_cash_flow", "capex", "dividends",
                "buybacks"]:
        if col in panel:
            panel[f"{col}_ttm"] = panel[col].rolling(4, min_periods=4).sum()

    out = pd.DataFrame(index=panel.index)
    out["n_companies"] = panel["n_companies"]
    out["leverage_debt_to_ebitda"] = panel["total_debt"] / panel["ebitda_ttm"]
    out["debt_to_assets"] = panel["total_debt"] / panel["total_assets"]
    out["debt_to_equity"] = panel["total_debt"] / panel["equity"]
    out["interest_coverage"] = panel["ebit_ttm"] / panel["interest_expense_ttm"]
    out["net_margin"] = panel["net_income_ttm"] / panel["revenue_ttm"] * 100.0
    out["operating_margin"] = panel["operating_income_ttm"] / panel["revenue_ttm"] * 100.0
    out["roe"] = panel["net_income_ttm"] / panel["equity"] * 100.0
    out["cash_to_assets"] = panel["cash"] / panel["total_assets"] * 100.0
    out["revenue_yoy"] = panel["revenue_ttm"].pct_change(4) * 100.0
    out["earnings_yoy"] = panel["net_income_ttm"].pct_change(4) * 100.0
    out["capex_to_sales"] = -panel["capex_ttm"] / panel["revenue_ttm"] * 100.0
    out["buybacks_to_sales"] = panel["buybacks_ttm"] / panel["revenue_ttm"] * 100.0
    out["fcf_margin"] = (
        (panel["operating_cash_flow_ttm"] - panel["capex_ttm"]) / panel["revenue_ttm"] * 100.0
    )

    # Only trust quarters with enough reporting breadth.
    out = out[out["n_companies"] >= MIN_COMPANIES_PER_QUARTER]
    return out


# --------------------------------------------------------------------------- #
# 3. Composite index from the companies' own monthly prices + optional ^GSPC.
# --------------------------------------------------------------------------- #
def build_composite_index(root: Path, symbols: list[str] | None = None) -> pd.Series:
    """Cap-weighted composite of the universe's own monthly adjusted closes.

    Weights use latest shares outstanding (a fixed-weight approximation -- the
    dataset has no historical share counts), so this is a broad-market proxy,
    not a rebalanced index.  We normalise to 100 at the first common month.
    """
    fdir = root / FUNDAMENTALS_DIR
    if symbols is None:
        symbols = sorted(
            p.name[: -len("_time_series_monthly.json")]
            for p in fdir.glob("*_time_series_monthly.json")
        )

    price_frames: dict[str, pd.Series] = {}
    weights: dict[str, float] = {}
    for sym in symbols:
        ts_path = fdir / f"{sym}_time_series_monthly.json"
        if not ts_path.exists():
            continue
        try:
            payload = json.loads(ts_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        data = payload.get("data", {})
        series_key = next((k for k in data if "Time Series" in k), None)
        if series_key is None:
            continue
        rows = data[series_key]
        prices = {}
        for date_str, fields in rows.items():
            adj = _to_float(fields.get("5. adjusted close") or fields.get("4. close"))
            if not np.isnan(adj) and adj > 0:
                prices[pd.to_datetime(date_str)] = adj
        if len(prices) < 24:
            continue
        s = pd.Series(prices).sort_index()
        s.index = _month_end(pd.DatetimeIndex(s.index))
        s = s[~s.index.duplicated(keep="last")]
        price_frames[sym] = s

        ov_path = fdir / f"{sym}_overview.json"
        shares = np.nan
        if ov_path.exists():
            try:
                ov = json.loads(ov_path.read_text(encoding="utf-8")).get("data", {})
                shares = _to_float(ov.get("SharesOutstanding"))
            except (json.JSONDecodeError, OSError):
                pass
        weights[sym] = shares

    if not price_frames:
        return pd.Series(dtype="float64", name="composite")

    prices = pd.DataFrame(price_frames).sort_index()
    monthly_returns = prices.pct_change()

    # Cap weight where we have shares, else equal weight; normalise per period.
    w = pd.Series(weights).reindex(prices.columns)
    latest_price = prices.ffill().iloc[-1]
    mktcap = (w * latest_price)
    mktcap = mktcap.where(mktcap > 0, np.nan)
    if mktcap.notna().sum() < 5:
        mktcap = pd.Series(1.0, index=prices.columns)
    mktcap = mktcap.fillna(mktcap.median())

    valid = monthly_returns.notna()
    weight_matrix = valid.mul(mktcap, axis=1)
    weight_matrix = weight_matrix.div(weight_matrix.sum(axis=1), axis=0)
    index_returns = (monthly_returns * weight_matrix).sum(axis=1, min_count=1)

    composite = (1.0 + index_returns.fillna(0)).cumprod()
    composite = composite / composite.iloc[0] * 100.0
    composite.name = "composite"
    return composite


def fetch_gspc(start: str = "1999-01-01") -> pd.Series:
    """Best-effort monthly ^GSPC close via yfinance (returns empty on failure)."""
    try:
        import yfinance as yf
    except ImportError:
        return pd.Series(dtype="float64", name="sp500")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            data = yf.download(
                "^GSPC", start=start, interval="1mo",
                progress=False, auto_adjust=True, threads=False,
            )
        if data is None or data.empty:
            return pd.Series(dtype="float64", name="sp500")
        close = data["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close.index = _month_end(pd.DatetimeIndex(close.index))
        close = close[~close.index.duplicated(keep="last")]
        close.name = "sp500"
        return close
    except Exception:  # noqa: BLE001 - network/library failure is non-fatal
        return pd.Series(dtype="float64", name="sp500")
