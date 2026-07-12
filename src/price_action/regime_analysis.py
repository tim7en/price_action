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
from dataclasses import dataclass
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


def resolve_fundamentals_dir(root: Path, fundamentals_dir: str | Path | None) -> Path:
    """Resolve the folder holding ``<SYMBOL>_<statement>.json`` files.

    ``fundamentals_dir`` may be an absolute path, a path relative to the project
    root, or a bare folder name under ``fundamentals_history/``.  ``None`` uses
    the default ``fundamentals_history/sp500_data``.
    """
    if fundamentals_dir is None:
        return root / FUNDAMENTALS_DIR
    p = Path(fundamentals_dir)
    if p.is_absolute():
        return p
    if (root / p).exists():
        return root / p
    return root / "fundamentals_history" / p


MACRO_DAILY_CSV = Path("cache") / "macro_daily_1999.csv"
FRED_DIR = Path("fred")
OUTPUT_DIR = Path("outputs") / "regime_analysis"

# Minimum companies contributing to an aggregate quarter for it to be trusted.
# Coverage is genuinely thin before ~2007, and aggregate ratios built from a
# handful of names are dominated by composition rather than the debt cycle.
MIN_COMPANIES_PER_QUARTER = 110


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

    # Forward-looking block: market-implied Fed path, inflation expectations,
    # and leading indicators (columns empty until refresh_macro fetches them).
    frame["fed_funds"] = _fred_monthly("DFF")
    frame["fed_path_2y"] = frame["us_2y"] - frame["fed_funds"]
    frame["breakeven_10y"] = _fred_monthly("T10YIE")
    frame["infl_5y5y_fwd"] = _fred_monthly("T5YIFR")
    frame["infl_exp_1y"] = _fred_monthly("MICH")
    claims = _read_fred(root, "ICSA").rolling(4, min_periods=4).mean().resample("ME").last()
    frame["claims_yoy"] = (claims / claims.shift(12) - 1.0).mul(100).reindex(frame.index)
    permits = _read_fred(root, "PERMIT").resample("ME").last()
    frame["permits_yoy"] = (permits / permits.shift(12) - 1.0).mul(100).reindex(frame.index)

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


def load_corporate_panel(root: Path, symbols: list[str] | None = None,
                         fundamentals_dir: str | Path | None = None) -> pd.DataFrame:
    """Aggregate every company's statements into one corporate-sector panel.

    Dollar amounts are summed across the universe within each calendar quarter,
    then converted into aggregate ratios.  This treats the whole universe as one
    giant company -- exactly the lens Dalio uses when he talks about the debt of
    "the economy" rather than a single borrower.
    """
    fdir = resolve_fundamentals_dir(root, fundamentals_dir)
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

    # Per-company quarterly revenue / net income, so growth can be measured on a
    # *matched* panel (cross-sectional median) instead of a composition-shifting
    # aggregate sum -- otherwise new entrants create fake triple-digit "growth".
    per_company_rev: dict[str, dict] = {}
    per_company_ni: dict[str, dict] = {}

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
        for rep in inc:
            q = _quarter_period(rep.get("fiscalDateEnding", ""))
            if q is None:
                continue
            rev = _to_float(rep.get("totalRevenue"))
            ni = _to_float(rep.get("netIncome"))
            if not np.isnan(rev):
                per_company_rev.setdefault(sym, {})[q] = rev
            if not np.isnan(ni):
                per_company_ni.setdefault(sym, {})[q] = ni
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

    def _p(name: str) -> pd.Series:
        if name in panel:
            return panel[name].astype("float64")
        return pd.Series(np.nan, index=panel.index)

    revenue_ttm = _p("revenue_ttm")
    out = pd.DataFrame(index=panel.index)
    out["n_companies"] = panel["n_companies"]
    out["leverage_debt_to_ebitda"] = panel["total_debt"] / _p("ebitda_ttm")
    out["debt_to_assets"] = panel["total_debt"] / _p("total_assets")
    out["debt_to_equity"] = panel["total_debt"] / _p("equity")
    out["interest_coverage"] = _p("ebit_ttm") / _p("interest_expense_ttm")
    out["net_margin"] = _p("net_income_ttm") / revenue_ttm * 100.0
    out["operating_margin"] = _p("operating_income_ttm") / revenue_ttm * 100.0
    out["roe"] = _p("net_income_ttm") / _p("equity") * 100.0
    out["cash_to_assets"] = _p("cash") / _p("total_assets") * 100.0

    # Composition-robust growth: median of each company's own TTM YoY growth.
    def _median_yoy(per_company: dict[str, dict]) -> pd.Series:
        if not per_company:
            return pd.Series(np.nan, index=panel.index)
        frame = pd.DataFrame(per_company).sort_index()
        ttm = frame.rolling(4, min_periods=4).sum()
        yoy = ttm.pct_change(4, fill_method=None) * 100.0
        # Ignore companies crossing zero income (unstable ratios) via clipping.
        return yoy.clip(-60, 60).median(axis=1).reindex(panel.index)

    out["revenue_yoy"] = _median_yoy(per_company_rev)
    out["earnings_yoy"] = _median_yoy(per_company_ni)
    out["capex_to_sales"] = -_p("capex_ttm") / revenue_ttm * 100.0
    out["buybacks_to_sales"] = _p("buybacks_ttm") / revenue_ttm * 100.0
    out["fcf_margin"] = (_p("operating_cash_flow_ttm") - _p("capex_ttm")) / revenue_ttm * 100.0

    # Only trust quarters whose entire trailing-twelve-month window is well
    # populated (rolling-min breadth), which removes TTM warm-up distortions.
    breadth_ok = out["n_companies"].rolling(4, min_periods=4).min() >= MIN_COMPANIES_PER_QUARTER
    out = out[breadth_ok.fillna(False)]
    return out


# --------------------------------------------------------------------------- #
# 3. Composite index from the companies' own monthly prices + optional ^GSPC.
# --------------------------------------------------------------------------- #
def build_composite_index(root: Path, symbols: list[str] | None = None,
                          fundamentals_dir: str | Path | None = None) -> pd.Series:
    """Cap-weighted composite of the universe's own monthly adjusted closes.

    Weights use latest shares outstanding (a fixed-weight approximation -- the
    dataset has no historical share counts), so this is a broad-market proxy,
    not a rebalanced index.  We normalise to 100 at the first common month.
    """
    fdir = resolve_fundamentals_dir(root, fundamentals_dir)
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
    monthly_returns = prices.pct_change(fill_method=None)
    # Clip to a sane monthly band: legitimate large-cap moves stay, but data
    # glitches / unadjusted splits (which show up as +100x jumps) are removed.
    monthly_returns = monthly_returns.clip(lower=-0.85, upper=1.5)

    # Cap weight where we have shares, else equal weight; normalise per period.
    w = pd.Series(weights).reindex(prices.columns)
    latest_price = prices.ffill().iloc[-1]
    mktcap = (w * latest_price)
    mktcap = mktcap.where(mktcap > 0, np.nan)
    if mktcap.notna().sum() < 5:
        mktcap = pd.Series(1.0, index=prices.columns)
    mktcap = mktcap.fillna(mktcap.median())

    valid = monthly_returns.notna()
    breadth = valid.sum(axis=1)
    weight_matrix = valid.mul(mktcap, axis=1)
    weight_matrix = weight_matrix.div(weight_matrix.sum(axis=1), axis=0)
    index_returns = (monthly_returns * weight_matrix).sum(axis=1, min_count=1)

    # Only trust the composite once at least 20 names are present.
    index_returns = index_returns.where(breadth >= 20)
    first = index_returns.first_valid_index()
    if first is not None:
        index_returns = index_returns.loc[first:]

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


# --------------------------------------------------------------------------- #
# 4. Rules-based regime engine (Dalio quadrants + debt-cycle phase).
# --------------------------------------------------------------------------- #
def dalio_signals(macro: pd.DataFrame) -> pd.DataFrame:
    """Growth and inflation *momentum* signals underlying the quadrant.

    Growth = industrial-production YoY vs its own recent trend.
    Inflation = 6-month change in core CPI YoY.  We use *rates of change*, not
    levels, because markets discount the second derivative.
    """
    growth = macro["indpro_yoy"]
    return pd.DataFrame({
        "growth_signal": growth - growth.rolling(12, min_periods=6).mean(),
        "inflation_signal": macro["core_cpi_yoy"].diff(6),
    })


def dalio_quadrant(macro: pd.DataFrame) -> pd.Series:
    """Growth x Inflation quadrant, Dalio "four seasons" style."""
    sig = dalio_signals(macro)
    growth_signal = sig["growth_signal"]
    inflation_signal = sig["inflation_signal"]

    labels = pd.Series("Indeterminate", index=macro.index, dtype=object)
    g_up = growth_signal > 0.05
    g_dn = growth_signal < -0.05
    i_up = inflation_signal > 0.05
    i_dn = inflation_signal < -0.05
    labels[g_up & i_dn] = "Goldilocks (growth up, inflation down)"
    labels[g_up & i_up] = "Reflation (growth up, inflation up)"
    labels[g_dn & i_up] = "Stagflation (growth down, inflation up)"
    labels[g_dn & i_dn] = "Deflation (growth down, inflation down)"
    return labels


def corporate_monthly(corp: pd.DataFrame, index: pd.DatetimeIndex) -> pd.DataFrame:
    """Forward-fill the quarterly corporate panel onto a monthly index."""
    if corp.empty:
        return pd.DataFrame(index=index)
    monthly = corp.copy()
    monthly.index = _month_end(pd.DatetimeIndex(monthly.index))
    monthly = monthly.reindex(index.union(monthly.index)).sort_index().ffill(limit=3)
    return monthly.reindex(index)


def debt_cycle_phase(corp_m: pd.DataFrame, macro: pd.DataFrame) -> pd.Series:
    """Classify each month into a Dalio debt-cycle phase.

    * Leveraging up:            corporate debt/EBITDA rising.
    * Beautiful deleveraging:   leverage falling while nominal income still
                                grows and credit conditions are not blowing out
                                (debt shrinks relative to income without a bust).
    * Ugly deleveraging:        leverage falling amid falling income / spiking
                                credit spreads (deflationary debt reduction).
    * Stable / neutral:         leverage roughly flat.
    """
    idx = macro.index
    phase = pd.Series("Stable / neutral", index=idx, dtype=object)
    if corp_m.empty or "leverage_debt_to_ebitda" not in corp_m:
        return phase

    lev = corp_m["leverage_debt_to_ebitda"]
    lev_chg = lev.diff(12)  # 12-month change in leverage
    nominal_growth = corp_m.get("revenue_yoy")
    if nominal_growth is None:
        nominal_growth = macro["indpro_yoy"] + macro["core_cpi_yoy"]
    hy = macro["hy_spread"]
    hy_stress = hy > hy.rolling(36, min_periods=12).median() + 2.0

    lev_scale = lev.rolling(24, min_periods=8).std().clip(lower=0.05)
    rising = lev_chg > 0.4 * lev_scale
    falling = lev_chg < -0.4 * lev_scale

    ugly = falling & ((nominal_growth < 0) | hy_stress)
    beautiful = falling & ~ugly
    phase[rising] = "Leveraging up"
    phase[beautiful] = "Beautiful deleveraging"
    phase[ugly] = "Ugly deleveraging / deflationary"
    return phase


# --------------------------------------------------------------------------- #
# 5. Statistical latent regimes (Gaussian mixture) + Markov forecast.
# --------------------------------------------------------------------------- #
GMM_FEATURES = [
    "yield_curve_10y2y", "t10y3m", "nfci", "hy_spread", "vix",
    "core_cpi_yoy", "indpro_yoy", "cape",
]


@dataclass
class RegimeModel:
    labels: pd.Series                 # month -> regime name
    names: dict[int, str]             # cluster id -> readable name
    summary: pd.DataFrame             # per-regime feature/return stats
    transition: pd.DataFrame          # monthly transition matrix (names x names)
    forecast: pd.DataFrame            # horizon -> P(regime) from current state
    current: str
    n_components: int


def _name_regime(centroid: pd.Series, fwd_ret: float, vol: float) -> str:
    """Human label from standardized centroid + realised forward return."""
    tags = []
    if centroid.get("hy_spread", 0) > 0.7 or centroid.get("vix", 0) > 0.7:
        tags.append("Risk-off / stress")
    if centroid.get("nfci", 0) > 0.5:
        tags.append("Tight conditions")
    elif centroid.get("nfci", 0) < -0.5:
        tags.append("Easy conditions")
    if centroid.get("core_cpi_yoy", 0) > 0.7:
        tags.append("Inflationary")
    if centroid.get("indpro_yoy", 0) > 0.5:
        tags.append("Expansion")
    elif centroid.get("indpro_yoy", 0) < -0.5:
        tags.append("Contraction")
    if centroid.get("yield_curve_10y2y", 0) < -0.5 or centroid.get("t10y3m", 0) < -0.5:
        tags.append("Inverted curve / late-cycle")
    if not tags:
        tags.append("Calm mid-cycle" if fwd_ret >= 0 else "Choppy")
    return " · ".join(dict.fromkeys(tags))[:60]


def fit_regime_model(macro: pd.DataFrame, forward_returns: pd.Series,
                     n_components: int | None = None, seed: int = 7) -> RegimeModel:
    from sklearn.mixture import GaussianMixture
    from sklearn.preprocessing import StandardScaler

    feats = [c for c in GMM_FEATURES if c in macro.columns]
    data = macro[feats].dropna()
    if len(data) < 60:
        raise ValueError("Not enough aligned macro history to fit regimes.")

    scaler = StandardScaler()
    X = scaler.fit_transform(data.to_numpy())

    if n_components is None:
        best_bic, best_k, best_model = np.inf, 4, None
        for k in range(4, 7):
            gm = GaussianMixture(n_components=k, covariance_type="full",
                                 random_state=seed, n_init=5, max_iter=300)
            gm.fit(X)
            bic = gm.bic(X)
            if bic < best_bic:
                best_bic, best_k, best_model = bic, k, gm
        model, k = best_model, best_k
    else:
        k = n_components
        model = GaussianMixture(n_components=k, covariance_type="full",
                                random_state=seed, n_init=5, max_iter=300).fit(X)

    raw = pd.Series(model.predict(X), index=data.index)

    # Characterise each cluster (standardized centroids + forward returns).
    z = pd.DataFrame(X, index=data.index, columns=feats)
    fwd = forward_returns.reindex(data.index)
    rows = {}
    names: dict[int, str] = {}
    for cid in range(k):
        mask = raw == cid
        centroid = z[mask].mean()
        ret = float(fwd[mask].mean()) if mask.any() else np.nan
        vol = float(macro["vix"].reindex(data.index)[mask].mean()) if mask.any() else np.nan
        name = _name_regime(centroid, 0 if np.isnan(ret) else ret, vol)
        # Disambiguate duplicate names.
        base, n = name, 2
        while name in names.values():
            name = f"{base} ({n})"
            n += 1
        names[cid] = name
        rows[name] = {
            "months": int(mask.sum()),
            "share_%": round(100 * mask.mean(), 1),
            "fwd_12m_ret_%": round(100 * ret, 1) if not np.isnan(ret) else np.nan,
            "avg_vix": round(vol, 1) if not np.isnan(vol) else np.nan,
            **{f: round(float(centroid[f]), 2) for f in feats},
        }
    summary = pd.DataFrame(rows).T

    labels = raw.map(names)

    # Monthly Markov transition matrix with Laplace smoothing so a recent,
    # not-yet-exited regime does not collapse to a degenerate 100% forecast.
    order = list(names.values())
    counts = pd.DataFrame(0.0, index=order, columns=order)
    seq = labels.to_numpy()
    for a, b in zip(seq[:-1], seq[1:]):
        counts.loc[a, b] += 1
    alpha = 0.5
    trans = (counts + alpha).div((counts.sum(axis=1) + alpha * len(order)), axis=0)

    # Forecast forward regime distribution from the current state.
    current = labels.iloc[-1]
    P = trans.to_numpy()
    v = np.zeros(len(order))
    v[order.index(current)] = 1.0
    horizons = [1, 3, 6, 12]
    fc = {}
    for h in horizons:
        vh = v @ np.linalg.matrix_power(P, h)
        fc[f"{h}m"] = vh
    forecast = pd.DataFrame(fc, index=order)

    return RegimeModel(labels=labels, names=names, summary=summary,
                       transition=trans, forecast=forecast,
                       current=current, n_components=k)


# --------------------------------------------------------------------------- #
# 6. Lead-lag: which drivers move returns, and with what delay.
# --------------------------------------------------------------------------- #
def lead_lag_matrix(drivers: pd.DataFrame, equity: pd.Series,
                    horizons: Iterable[int] = range(1, 25)) -> pd.DataFrame:
    """Corr between each driver's monthly change and forward cumulative returns.

    Positive horizon = driver leads returns.  The peak-|corr| horizon is our
    estimate of "how long before the effect shows up".
    """
    horizons = list(horizons)
    log_px = np.log(equity.reindex(drivers.index))
    result = pd.DataFrame(index=drivers.columns, columns=[f"+{h}m" for h in horizons],
                          dtype=float)
    for name in drivers.columns:
        d = drivers[name].diff()
        for h in horizons:
            fwd = log_px.shift(-h) - log_px           # cumulative fwd return
            pair = pd.concat([d, fwd], axis=1).dropna()
            if len(pair) > 24:
                result.loc[name, f"+{h}m"] = pair.iloc[:, 0].corr(pair.iloc[:, 1])
    return result.astype(float).dropna(how="all")


def lead_lag_summary(matrix: pd.DataFrame) -> pd.DataFrame:
    """Peak-|corr| horizon and value for each driver."""
    rows = {}
    for name, row in matrix.iterrows():
        row = row.dropna()
        if row.empty:
            continue
        peak_col = row.abs().idxmax()
        rows[name] = {
            "peak_lag": peak_col,
            "peak_corr": round(float(row[peak_col]), 2),
            "sign": "returns fall after a rise" if row[peak_col] < 0
                    else "returns rise after a rise",
        }
    return pd.DataFrame(rows).T


# --------------------------------------------------------------------------- #
# 7. Charts (matplotlib -> base64 PNG embedded in the HTML report).
# --------------------------------------------------------------------------- #
def _runs(series: pd.Series):
    """Yield (start_ts, end_ts, value) contiguous runs of a categorical series."""
    s = series.dropna()
    if s.empty:
        return
    start = s.index[0]
    prev = s.iloc[0]
    idx = s.index
    for i in range(1, len(s)):
        if s.iloc[i] != prev:
            yield start, idx[i], prev
            start, prev = idx[i], s.iloc[i]
    yield start, idx[-1], prev


def _regime_palette(names: list[str]) -> dict[str, str]:
    palette = ["#0f4c5c", "#7a3e2b", "#4f6d3a", "#c9a227", "#4361ee",
               "#9a4a35", "#3f7f78", "#6f4e7c", "#9b8f77"]
    return {n: palette[i % len(palette)] for i, n in enumerate(names)}


def _new_fig(figsize):
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=figsize, dpi=130)
    fig.patch.set_facecolor(PANEL_BACKGROUND)
    return fig


def _style(ax):
    ax.set_facecolor(PANEL_BACKGROUND)
    ax.grid(True, color=GRID_COLOR, linewidth=0.6, alpha=0.7)
    for spine in ax.spines.values():
        spine.set_color(GRID_COLOR)
    ax.tick_params(colors=MUTED_TEXT_COLOR, labelsize=8)
    ax.title.set_color(TEXT_COLOR)
    ax.yaxis.label.set_color(MUTED_TEXT_COLOR)
    ax.xaxis.label.set_color(MUTED_TEXT_COLOR)


def _fig_to_b64(fig) -> str:
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def chart_regime_timeline(macro, quad, phase, composite, gspc) -> str:
    from matplotlib.gridspec import GridSpec
    from matplotlib.patches import Patch
    fig = _new_fig((12, 6))
    gs = GridSpec(2, 1, height_ratios=[6, 1], hspace=0.12, figure=fig)
    ax = fig.add_subplot(gs[0]); _style(ax)

    eq = macro["equity_index"].dropna()
    ax.plot(eq.index, eq.values, color=TEXT_COLOR, lw=1.6, label="Wilshire total market (broad)")
    if composite is not None and not composite.empty:
        c = composite / composite.iloc[0] * eq.reindex(composite.index).dropna().iloc[0]
        ax.plot(c.index, c.values, color="#7a3e2b", lw=1.0, alpha=0.8,
                label="Cap-weighted composite (survivorship-biased)")
    if gspc is not None and not gspc.empty:
        g = gspc / gspc.iloc[0] * eq.reindex(gspc.index).dropna().iloc[0]
        ax.plot(g.index, g.values, color="#4361ee", lw=0.9, alpha=0.7, label="S&P 500 (^GSPC)")
    ax.set_yscale("log")
    ax.set_ylabel("Index level (log)")
    ax.set_title("Equity market through the Dalio growth/inflation quadrants", fontsize=12, loc="left")

    for start, end, q in _runs(quad):
        ax.axvspan(start, end, color=QUADRANT_COLORS.get(q, "#ccc"), alpha=0.13, lw=0)
    handles = [Patch(facecolor=c, alpha=0.4, label=q) for q, c in QUADRANT_COLORS.items() if q != "Indeterminate"]
    leg1 = ax.legend(loc="upper left", fontsize=7.5, framealpha=0.9)
    ax.add_artist(leg1)
    ax.legend(handles=handles, loc="lower right", fontsize=7, framealpha=0.9, title="Quadrant")

    axp = fig.add_subplot(gs[1], sharex=ax); _style(axp)
    axp.set_yticks([])
    for start, end, ph in _runs(phase):
        axp.axvspan(start, end, color=DEBT_PHASE_COLORS.get(ph, "#ccc"), alpha=0.85, lw=0)
    axp.set_ylabel("Debt\ncycle", rotation=0, ha="right", va="center", fontsize=8)
    ph_handles = [Patch(facecolor=c, label=p) for p, c in DEBT_PHASE_COLORS.items()]
    axp.legend(handles=ph_handles, loc="upper center", bbox_to_anchor=(0.5, -0.35),
               ncol=4, fontsize=7, framealpha=0)
    return _fig_to_b64(fig)


def chart_debt_cycle(corp) -> str:
    from .macro_context import MACRO_REGIME_WINDOWS
    from matplotlib.gridspec import GridSpec
    fig = _new_fig((12, 6.4))
    gs = GridSpec(2, 1, height_ratios=[1, 1], hspace=0.28, figure=fig)

    def shade(ax):
        for w in MACRO_REGIME_WINDOWS:
            ax.axvspan(pd.Timestamp(w["start"]), pd.Timestamp(w["end"]),
                       color="#9a4a35", alpha=0.10, lw=0)

    ax1 = fig.add_subplot(gs[0]); _style(ax1); shade(ax1)
    lev = corp["leverage_debt_to_ebitda"].clip(upper=8)
    ax1.plot(lev.index, lev.values, color="#7a3e2b", lw=1.8, label="Aggregate debt / EBITDA (left)")
    ax1.set_ylabel("Debt / EBITDA")
    ax1.set_title("Corporate-sector debt cycle: leverage vs. ability to service it",
                  fontsize=12, loc="left")
    ax1b = ax1.twinx()
    cov = corp["interest_coverage"].clip(-5, 40)
    ax1b.plot(cov.index, cov.values, color="#0f4c5c", lw=1.4, label="Interest coverage EBIT/interest (right)")
    ax1b.set_ylabel("Interest coverage (x)", color="#0f4c5c")
    ax1b.tick_params(colors="#0f4c5c", labelsize=8)
    lines = ax1.get_lines() + ax1b.get_lines()
    ax1.legend(lines, [l.get_label() for l in lines], loc="upper left", fontsize=8, framealpha=0.9)

    ax2 = fig.add_subplot(gs[1], sharex=ax1); _style(ax2); shade(ax2)
    ax2.plot(corp.index, corp["net_margin"], color="#4f6d3a", lw=1.6, label="Net margin %")
    ax2.plot(corp.index, corp["fcf_margin"], color="#4361ee", lw=1.2, label="Free-cash-flow margin %")
    ax2.axhline(0, color=MUTED_TEXT_COLOR, lw=0.6)
    ax2.set_ylabel("Margin %")
    ax2.set_title("Profitability and cash generation (shaded = crisis windows)",
                  fontsize=11, loc="left")
    ax2.legend(loc="lower left", fontsize=8, framealpha=0.9)
    return _fig_to_b64(fig)


def chart_beautiful_deleveraging(corp_m, macro, phase) -> str:
    fig = _new_fig((12, 5))
    ax = fig.add_subplot(111); _style(ax)
    for start, end, ph in _runs(phase):
        ax.axvspan(start, end, color=DEBT_PHASE_COLORS.get(ph, "#ccc"), alpha=0.16, lw=0)
    lev = corp_m["leverage_debt_to_ebitda"].clip(upper=8)
    ax.plot(lev.index, lev.values, color="#7a3e2b", lw=1.9, label="Corporate leverage (debt/EBITDA, left)")
    ax.set_ylabel("Debt / EBITDA")
    ax.set_title("Beautiful vs. ugly deleveraging: is debt falling while income still grows?",
                 fontsize=12, loc="left")
    axb = ax.twinx()
    growth = corp_m["revenue_yoy"].clip(-30, 40)
    axb.plot(growth.index, growth.values, color="#0f4c5c", lw=1.4, label="Nominal revenue growth YoY % (right)")
    axb.axhline(0, color="#0f4c5c", lw=0.6, ls="--", alpha=0.6, label="_nolegend_")
    axb.set_ylabel("Revenue YoY %", color="#0f4c5c")
    axb.tick_params(colors="#0f4c5c", labelsize=8)
    from matplotlib.patches import Patch
    ph_handles = [Patch(facecolor=c, alpha=0.5, label=p) for p, c in DEBT_PHASE_COLORS.items()]
    lines = [l for l in ax.get_lines() + axb.get_lines() if not l.get_label().startswith("_")]
    leg = ax.legend(lines, [l.get_label() for l in lines], loc="upper right", fontsize=8, framealpha=0.9)
    ax.add_artist(leg)
    ax.legend(handles=ph_handles, loc="lower left", fontsize=7, ncol=2, framealpha=0.9)
    return _fig_to_b64(fig)


def chart_quadrant_scatter(macro, fwd12) -> str:
    sig = dalio_signals(macro)
    df = pd.concat([sig, fwd12.rename("fwd")], axis=1).dropna()
    fig = _new_fig((7.5, 6.5))
    ax = fig.add_subplot(111); _style(ax)
    sc = ax.scatter(df["growth_signal"], df["inflation_signal"],
                    c=(df["fwd"] * 100).clip(-40, 40), cmap="RdYlGn", s=22,
                    edgecolor="white", linewidth=0.3)
    ax.axhline(0, color=MUTED_TEXT_COLOR, lw=0.8)
    ax.axvline(0, color=MUTED_TEXT_COLOR, lw=0.8)
    cur = df.iloc[-1]
    ax.scatter([cur["growth_signal"]], [cur["inflation_signal"]], s=200, marker="*",
               color="#111", edgecolor="white", zorder=5)
    ax.annotate("  Now", xy=(cur["growth_signal"], cur["inflation_signal"]),
                fontsize=9, fontweight="bold", color="#111", va="center")
    ax.set_xlabel("Growth momentum  →")
    ax.set_ylabel("Inflation momentum  →")
    ax.set_title("Quadrant map, colored by forward 12m return", fontsize=12, loc="left")
    for (x, y, t, ha) in [(0.97, 0.96, "Reflation", "right"),
                          (0.03, 0.96, "Stagflation", "left"),
                          (0.97, 0.04, "Goldilocks", "right"),
                          (0.03, 0.04, "Deflation", "left")]:
        ax.annotate(t, xy=(x, y), xycoords="axes fraction", fontsize=10,
                    color=MUTED_TEXT_COLOR, ha=ha, va="center", fontweight="bold")
    cb = fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("Forward 12m return %", color=MUTED_TEXT_COLOR, fontsize=8)
    cb.ax.tick_params(colors=MUTED_TEXT_COLOR, labelsize=7)
    return _fig_to_b64(fig)


def chart_leadlag_heatmap(ll) -> str:
    import matplotlib.pyplot as plt
    fig = _new_fig((12, 4.6))
    ax = fig.add_subplot(111); _style(ax); ax.grid(False)
    data = ll.to_numpy(dtype=float)
    im = ax.imshow(data, aspect="auto", cmap="RdBu_r", vmin=-0.35, vmax=0.35)
    ax.set_yticks(range(len(ll.index)))
    ax.set_yticks(range(len(ll.index)), labels=ll.index, fontsize=9)
    step = 2
    ax.set_xticks(range(0, len(ll.columns), step))
    ax.set_xticklabels(list(ll.columns)[::step], fontsize=7)
    ax.set_xlabel("Months after the driver moves  (positive = driver leads returns)")
    ax.set_title("Lead-lag: correlation of a driver's monthly change with forward equity returns",
                 fontsize=12, loc="left")
    # Mark peak-|corr| horizon per driver.
    for i, name in enumerate(ll.index):
        row = ll.loc[name].dropna()
        if row.empty:
            continue
        j = list(ll.columns).index(row.abs().idxmax())
        ax.scatter([j], [i], s=40, facecolor="none", edgecolor="black", linewidth=1.4)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cb.set_label("Correlation", color=MUTED_TEXT_COLOR, fontsize=8)
    cb.ax.tick_params(colors=MUTED_TEXT_COLOR, labelsize=7)
    return _fig_to_b64(fig)


def chart_forward_by_regime(model: RegimeModel) -> str:
    s = model.summary.sort_values("fwd_12m_ret_%")
    fig = _new_fig((10, 5))
    ax = fig.add_subplot(111); _style(ax)
    colors = ["#9a4a35" if v < 0 else "#4f6d3a" for v in s["fwd_12m_ret_%"]]
    ax.barh(range(len(s)), s["fwd_12m_ret_%"], color=colors)
    ax.set_yticks(range(len(s)), labels=s.index, fontsize=8)
    ax.axvline(0, color=MUTED_TEXT_COLOR, lw=0.8)
    ax.set_xlabel("Average forward 12-month equity return %")
    ax.set_title("What each statistical regime paid: forward 12m return by regime",
                 fontsize=12, loc="left")
    for i, (ret, vix, share) in enumerate(zip(s["fwd_12m_ret_%"], s["avg_vix"], s["share_%"])):
        ax.text(ret + (0.4 if ret >= 0 else -0.4), i,
                f"{ret:+.0f}%  (VIX~{vix:.0f}, {share:.0f}% of time)",
                va="center", ha="left" if ret >= 0 else "right", fontsize=7,
                color=MUTED_TEXT_COLOR)
    ax.margins(x=0.25)
    return _fig_to_b64(fig)


def chart_transition_and_forecast(model: RegimeModel) -> str:
    from matplotlib.gridspec import GridSpec
    fig = _new_fig((12, 5.2))
    gs = GridSpec(1, 2, width_ratios=[1.3, 1], wspace=0.45, figure=fig)
    # Compact but unique labels (first segment collides between regimes).
    short = {n: (n if len(n) <= 26 else n[:24] + "…") for n in model.transition.index}
    ax = fig.add_subplot(gs[0]); _style(ax); ax.grid(False)
    im = ax.imshow(model.transition.to_numpy(), cmap="Greens", vmin=0, vmax=1)
    labels = [short[n] for n in model.transition.index]
    ax.set_xticks(range(len(labels)), labels=labels, rotation=45, ha="right", fontsize=7)
    ax.set_yticks(range(len(labels)), labels=labels, fontsize=7)
    ax.set_title("Monthly regime transition probabilities", fontsize=11, loc="left")
    ax.set_ylabel("From"); ax.set_xlabel("To")
    for i in range(len(labels)):
        for j in range(len(labels)):
            v = model.transition.iloc[i, j]
            if v > 0.05:
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=6,
                        color="white" if v > 0.5 else TEXT_COLOR)

    ax2 = fig.add_subplot(gs[1]); _style(ax2)
    fc = model.forecast["12m"].sort_values()
    ax2.barh(range(len(fc)), fc.values * 100, color="#0f4c5c")
    ax2.set_yticks(range(len(fc)), labels=[short[n] for n in fc.index], fontsize=7)
    ax2.set_xlabel("Probability %")
    ax2.set_title(f"Where we go in 12 months\n(from: {short[model.current]})",
                  fontsize=10, loc="left")
    return _fig_to_b64(fig)


# --------------------------------------------------------------------------- #
# 8. HTML report assembly.
# --------------------------------------------------------------------------- #
def _img(b64: str, caption: str) -> str:
    return (
        f'<figure class="chart"><img src="data:image/png;base64,{b64}" alt="{html.escape(caption)}"/>'
        f'<figcaption>{html.escape(caption)}</figcaption></figure>'
    )


def _table(df: pd.DataFrame, float_fmt: str = "{:.2f}") -> str:
    def fmt(v):
        if isinstance(v, float):
            return "" if pd.isna(v) else float_fmt.format(v)
        return html.escape(str(v))
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    body = ""
    for idx, row in df.iterrows():
        cells = "".join(f"<td>{fmt(v)}</td>" for v in row)
        body += f"<tr><th>{html.escape(str(idx))}</th>{cells}</tr>"
    return f"<table><thead><tr><th></th>{head}</tr></thead><tbody>{body}</tbody></table>"


@dataclass
class Analysis:
    macro: pd.DataFrame
    corp: pd.DataFrame
    corp_m: pd.DataFrame
    composite: pd.Series
    gspc: pd.Series
    quad: pd.Series
    phase: pd.Series
    fwd12: pd.Series
    model: RegimeModel
    leadlag: pd.DataFrame
    leadlag_sum: pd.DataFrame


def run_analysis(root: Path, use_yfinance: bool = True,
                 fundamentals_dir: str | Path | None = None) -> Analysis:
    macro = load_macro_panel(root)
    corp = load_corporate_panel(root, fundamentals_dir=fundamentals_dir)
    corp_m = corporate_monthly(corp, macro.index)
    composite = build_composite_index(root, fundamentals_dir=fundamentals_dir)
    gspc = fetch_gspc() if use_yfinance else pd.Series(dtype="float64")

    quad = dalio_quadrant(macro)
    phase = debt_cycle_phase(corp_m, macro)
    eq = macro["equity_index"]
    fwd12 = eq.shift(-12) / eq - 1.0

    model = fit_regime_model(macro, fwd12)

    drivers = macro[["nfci", "hy_spread", "t10y3m", "core_cpi_yoy",
                     "policy_uncertainty", "us_2y", "vix"]].copy()
    drivers = drivers.rename(columns={
        "nfci": "Financial conditions (NFCI)",
        "hy_spread": "High-yield spread",
        "t10y3m": "Yield curve (10y-3m)",
        "core_cpi_yoy": "Core inflation YoY",
        "policy_uncertainty": "Policy uncertainty",
        "us_2y": "2y yield (policy rate)",
        "vix": "Equity volatility (VIX)",
    })
    drivers["Corporate leverage"] = corp_m["leverage_debt_to_ebitda"]
    drivers["Corporate buybacks/sales"] = corp_m["buybacks_to_sales"]
    leadlag = lead_lag_matrix(drivers, eq)
    leadlag_sum = lead_lag_summary(leadlag)

    return Analysis(macro, corp, corp_m, composite, gspc, quad, phase,
                    fwd12, model, leadlag, leadlag_sum)


def build_report(root: Path, use_yfinance: bool = True,
                 fundamentals_dir: str | Path | None = None) -> Path:
    an = run_analysis(root, use_yfinance=use_yfinance, fundamentals_dir=fundamentals_dir)
    m, corp = an.macro, an.corp

    charts = {
        "timeline": chart_regime_timeline(m, an.quad, an.phase, an.composite, an.gspc),
        "debt": chart_debt_cycle(corp),
        "beautiful": chart_beautiful_deleveraging(an.corp_m, m, an.phase),
        "scatter": chart_quadrant_scatter(m, an.fwd12),
        "leadlag": chart_leadlag_heatmap(an.leadlag),
        "regime_ret": chart_forward_by_regime(an.model),
        "transition": chart_transition_and_forecast(an.model),
    }

    # --- Current-state read-out ------------------------------------------- #
    last = m.dropna(subset=["core_cpi_yoy", "indpro_yoy"]).index[-1]
    cur_quad = an.quad.loc[last]
    cur_phase = an.phase.loc[last]
    fc12 = an.model.forecast["12m"].sort_values(ascending=False)
    top_next = fc12.index[0]
    stay_prob = an.model.forecast.loc[an.model.current, "12m"]

    now_rows = {
        "As of": last.strftime("%Y-%m"),
        "Growth/inflation quadrant": cur_quad,
        "Corporate debt-cycle phase": cur_phase,
        "Statistical regime (now)": an.model.current,
        "Most likely regime in 12m": f"{top_next} ({fc12.iloc[0]*100:.0f}%)",
        "Prob. still in current regime (12m)": f"{stay_prob*100:.0f}%",
        "Core CPI YoY": f"{m['core_cpi_yoy'].loc[last]:.1f}%",
        "Industrial prod. YoY": f"{m['indpro_yoy'].loc[last]:.1f}%",
        "Yield curve 10y-3m": f"{m['t10y3m'].loc[last]:.2f}",
        "High-yield spread": f"{m['hy_spread'].loc[last]:.2f}",
        "Financial conditions (NFCI)": f"{m['nfci'].loc[last]:.2f}",
        "Corporate debt/EBITDA": f"{an.corp['leverage_debt_to_ebitda'].dropna().iloc[-1]:.2f}",
        "Interest coverage (x)": f"{an.corp['interest_coverage'].dropna().iloc[-1]:.1f}",
    }
    now_table = "".join(
        f'<div class="kv"><span class="k">{html.escape(k)}</span>'
        f'<span class="v">{html.escape(str(v))}</span></div>'
        for k, v in now_rows.items()
    )

    ll_sorted = an.leadlag_sum.copy()
    def _lagnum(x):
        try:
            return int(str(x).strip("+m"))
        except ValueError:
            return 999
    ll_sorted["_n"] = ll_sorted["peak_lag"].map(_lagnum)
    ll_sorted = ll_sorted.sort_values("_n").drop(columns="_n")

    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    css = _REPORT_CSS
    parts: list[str] = []
    parts.append(f"""<header>
      <h1>Market-Regime &amp; Debt-Cycle Analysis</h1>
      <p class="subtitle">A Ray-Dalio-style reading of U.S. corporate fundamentals and the macro machine —
      where we are in the growth, inflation and debt cycles, what drives returns, and how long the lags are.</p>
      <p class="meta">Generated {generated} · Macro history from {m.index.min():%Y} ·
      {int(an.corp['n_companies'].max())} companies aggregated · {an.model.n_components} statistical regimes</p>
    </header>""")

    parts.append(f"""<section class="now">
      <h2>Where we are now</h2>
      <div class="kv-grid">{now_table}</div>
    </section>""")

    parts.append(f"""<section>
      <h2>1 · The market through the regimes</h2>
      <p>The broad market (Wilshire) is shown on a log scale, with the background shaded by the
      <b>growth/inflation quadrant</b> and a ribbon underneath marking the <b>corporate debt-cycle phase</b>.
      The cap-weighted composite built from the 257 companies' own prices, and the S&amp;P 500, are overlaid
      for cross-checking. <span class="caveat">The composite is survivorship-biased (only today's
      constituents) so it overstates long-run returns; treat the Wilshire line as the honest benchmark.</span></p>
      {_img(charts['timeline'], 'Equity market with growth/inflation quadrant shading and debt-cycle ribbon')}
    </section>""")

    parts.append(f"""<section>
      <h2>2 · The corporate debt cycle</h2>
      <p>Aggregating every company into one “corporate sector”, this is Dalio's debt lens applied bottom-up:
      how much leverage the corporate sector carries (debt / EBITDA), whether it can service that debt
      (interest coverage), and whether profits and cash flow are expanding or contracting. Leverage that
      rises for years and then rolls over is the classic setup before a de-leveraging.</p>
      {_img(charts['debt'], 'Aggregate leverage, interest coverage, margins and cash generation over time')}
    </section>""")

    parts.append(f"""<section>
      <h2>3 · Beautiful vs. ugly deleveraging</h2>
      <p>Dalio's central distinction: a de-leveraging is <b>beautiful</b> when debt falls relative to income
      while the economy keeps growing (debt/income down, nominal growth positive, credit conditions calm),
      and <b>ugly / deflationary</b> when debt only falls through defaults and contraction. Here we track
      corporate leverage against nominal revenue growth, with the phase shaded behind.</p>
      {_img(charts['beautiful'], 'Corporate leverage vs. nominal revenue growth, colored by deleveraging phase')}
    </section>""")

    parts.append(f"""<section>
      <h2>4 · The quadrant map, paid by forward returns</h2>
      <p>Every month plotted by its growth momentum (x) and inflation momentum (y), colored by the equity
      return over the <i>next</i> 12 months. Green clusters show which corner of the machine has historically
      rewarded risk; the star is today.</p>
      {_img(charts['scatter'], 'Growth vs inflation momentum scatter, colored by forward 12-month return')}
    </section>""")

    parts.append(f"""<section>
      <h2>5 · Which decisions drive returns — and the lag</h2>
      <p>For each policy / financial-condition / capital-allocation driver, we correlate its monthly
      <i>change</i> with the equity return over the following 1–24 months. The ringed cell is the horizon of
      peak effect — our estimate of “how long before we see it”. Red = a rise in the driver is followed by
      <i>weaker</i> returns; blue = stronger.</p>
      {_img(charts['leadlag'], 'Lead-lag heatmap of drivers versus forward returns')}
      <h3>Peak-effect horizon by driver</h3>
      {_table(ll_sorted)}
      <p class="note">Read this as: tightening financial conditions and widening credit spreads bite
      fastest (a few months), while inflation and rate shocks work with much longer lags. This is the
      empirical version of “policy changes affect future returns, with a delay.”</p>
    </section>""")

    parts.append(f"""<section>
      <h2>6 · Statistical regimes and what they pay</h2>
      <p>A Gaussian-mixture model clusters the macro/financial-conditions history into
      {an.model.n_components} latent regimes with no labels imposed; we then read off the average forward
      12-month return of each. This is the data's own answer to “what regime is this, and is it worth
      owning risk?”</p>
      {_img(charts['regime_ret'], 'Average forward 12-month return by statistical regime')}
      <h3>Regime characteristics (standardized centroids)</h3>
      {_table(an.model.summary)}
    </section>""")

    parts.append(f"""<section>
      <h2>7 · Predicting the next regime</h2>
      <p>Turning the regime history into a Markov chain gives the monthly probability of moving from one
      regime to another (left), and propagating today's state forward gives the distribution of where we are
      likely to be in 12 months (right). Transitions are Laplace-smoothed so a recent regime does not falsely
      look permanent.</p>
      {_img(charts['transition'], 'Regime transition matrix and 12-month-ahead forecast')}
    </section>""")

    parts.append(f"""<section class="method">
      <h2>Method &amp; caveats</h2>
      <ul>
        <li><b>Data.</b> Macro from the local FRED/daily store (1999–present); corporate aggregates summed
        across {int(an.corp['n_companies'].max())} companies' quarterly filings, trailing-twelve-month.</li>
        <li><b>Survivorship.</b> The fundamentals set is today's constituents, so the composite index and
        early aggregate ratios are upward-biased. The Wilshire index is used as the unbiased market benchmark.</li>
        <li><b>Reporting breadth.</b> Aggregate ratios use only quarters with ≥{MIN_COMPANIES_PER_QUARTER}
        reporting companies; early-2000s coverage is thin.</li>
        <li><b>Regimes are descriptive, not causal.</b> Lead-lag correlations are associations; the peak-lag
        horizons are robust in sign but should not be traded mechanically.</li>
      </ul>
    </section>""")

    body = "\n".join(parts)
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Market-Regime &amp; Debt-Cycle Analysis</title><style>{css}</style></head>
<body><main>{body}</main></body></html>"""

    out_dir = root / OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(doc, encoding="utf-8")

    # Also persist the machine-readable panels for downstream use.
    an.macro.to_csv(out_dir / "macro_panel_monthly.csv")
    an.corp.to_csv(out_dir / "corporate_debt_cycle_quarterly.csv")
    pd.DataFrame({"quadrant": an.quad, "debt_phase": an.phase,
                  "statistical_regime": an.model.labels}).to_csv(out_dir / "regime_timeline.csv")
    an.leadlag.to_csv(out_dir / "lead_lag_correlations.csv")
    an.model.summary.to_csv(out_dir / "regime_summary.csv")
    return out_path


_REPORT_CSS = f"""
:root {{ color-scheme: light; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:{PAGE_BACKGROUND}; color:{TEXT_COLOR};
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height:1.5; }}
main {{ max-width: 1120px; margin: 0 auto; padding: 32px 20px 80px; }}
header h1 {{ font-size: 30px; margin: 0 0 6px; letter-spacing:-0.5px; }}
.subtitle {{ font-size: 16px; color:{TEXT_COLOR}; max-width: 820px; }}
.meta {{ color:{MUTED_TEXT_COLOR}; font-size: 12.5px; }}
section {{ background:{PANEL_BACKGROUND}; border:1px solid {GRID_COLOR}; border-radius:14px;
  padding: 22px 24px; margin: 20px 0; box-shadow: 0 1px 2px rgba(0,0,0,0.03); }}
h2 {{ font-size: 20px; margin: 0 0 10px; }}
h3 {{ font-size: 15px; margin: 20px 0 8px; color:{MUTED_TEXT_COLOR}; }}
p {{ font-size: 14.5px; max-width: 900px; }}
.caveat, .note {{ color:{MUTED_TEXT_COLOR}; font-size: 13px; }}
.note {{ border-left:3px solid {GRID_COLOR}; padding-left:12px; margin-top:14px; }}
figure.chart {{ margin: 16px 0 4px; }}
figure.chart img {{ width:100%; height:auto; border-radius:10px; border:1px solid {GRID_COLOR}; }}
figcaption {{ font-size:12px; color:{MUTED_TEXT_COLOR}; margin-top:6px; }}
.now {{ background: linear-gradient(180deg,#fffdf8,#f4efe4); }}
.kv-grid {{ display:grid; grid-template-columns: repeat(auto-fit,minmax(230px,1fr)); gap:10px; }}
.kv {{ display:flex; justify-content:space-between; gap:10px; padding:9px 12px;
  background:{PANEL_BACKGROUND}; border:1px solid {GRID_COLOR}; border-radius:9px; }}
.kv .k {{ color:{MUTED_TEXT_COLOR}; font-size:12.5px; }}
.kv .v {{ font-weight:600; font-size:13px; text-align:right; }}
table {{ border-collapse: collapse; width:100%; font-size:12.5px; margin-top:8px;
  display:block; overflow-x:auto; }}
th, td {{ border:1px solid {GRID_COLOR}; padding:5px 9px; text-align:right; white-space:nowrap; }}
thead th {{ background:#efe8da; color:{TEXT_COLOR}; }}
tbody th {{ text-align:left; background:#f6f1e6; font-weight:600; }}
.method ul {{ font-size:13.5px; color:{TEXT_COLOR}; }}
.method li {{ margin:6px 0; }}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-yfinance", action="store_true",
                        help="Skip the ^GSPC download (offline mode).")
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--fundamentals-dir", default=None,
                        help="Folder of <SYMBOL>_<statement>.json files (name under "
                             "fundamentals_history/, or a path). Default: sp500_data. "
                             "Use investme_sp500_data for the full 7,000-symbol set.")
    args = parser.parse_args()

    root = resolve_project_root(args.project_root)
    import matplotlib
    matplotlib.use("Agg")
    out = build_report(root, use_yfinance=not args.no_yfinance,
                       fundamentals_dir=args.fundamentals_dir)
    print(f"Wrote regime analysis report to {out}")


if __name__ == "__main__":
    main()
