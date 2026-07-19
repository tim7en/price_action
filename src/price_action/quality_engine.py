"""Sector-specific quality engine: does reported quality predict 6-month
performance vs sector peers?

Ben Graham's defensive-investor tests (Intelligent Investor ch. 14) adapted
per sector, on point-in-time SEC XBRL data — each quarter's numbers become
usable only on the day the 10-Q/10-K was **filed** (release-alignment, the
repo's standard). Scores are z-scored *within the sector cross-section*, so
quality is always "vs the peers and the business," never an absolute yardstick.

Factor choices anchor to the literature rather than in-sample search:

* Graham (1949/73): earnings stability, conservative leverage, growth.
* Piotroski (2000, F-Score): profitability + leverage + efficiency deltas.
* Novy-Marx (2013): gross profitability is the quality signal for
  asset-light firms — hence gross margin for Technology, where banks do not
  even report a GrossProfit concept.
* Sloan (1996): cash earnings beat accrual earnings — hence the FCF margin.
* Asness-Frazzini-Pedersen (2014, QMJ): profitable, stable, conservatively
  financed names outperform junk.

Each of the 11 sectors plus the semiconductor/memory book has its own explicit
metric specification. Metrics may overlap where the economics genuinely do,
but no sector inherits a generic "cyclical" or "defensive" composite. The
report includes standalone metric attribution and leave-one-metric-out
ablation for every book.

Universe rule: market cap >= $5B at observation (shares x price).

Event study: monthly cross-sections; score at month-end from data *filed* by
then -> forward 126-trading-day return MINUS the equal-weight sector peer
return (market and sector cancel; pure peer-relative). Overlapping windows
are disclosed; a non-overlapping 6-month spread is reported alongside the IC.

Run with::

    python build_quality_engine.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .data import load_asset_daily, resolve_project_root

SEC_DIR = Path("data") / "sec_facts"
OHLCV_DIR = Path("cache") / "market_structure"
OUTPUT_DIR = Path("outputs") / "quality_engine"
# Every name that ever appeared in a top-10 sector snapshot (with data), plus
# the dedicated semiconductor/memory book. Every book has its own metric spec.
SEMIS = ["NVDA", "AMD", "AVGO", "MU", "INTC", "TXN", "QCOM", "AMAT",
         "LRCX", "ADI", "WDC", "STX", "SNDK"]
SECTOR_SPECIFICATION = {
    "XLB": "materials",
    "XLC": "communication_services",
    "XLE": "energy",
    "XLF": "financials",
    "XLI": "industrials",
    "XLK": "technology",
    "XLP": "consumer_staples",
    "XLRE": "real_estate",
    "XLU": "utilities",
    "XLV": "health_care",
    "XLY": "consumer_discretionary",
    "SEMIS": "semiconductors_memory",
}
MIN_MARKET_CAP = 5e9
MIN_METRICS = 3
FWD_DAYS = 126
STALE_DAYS = 200


def build_universes(root: Path) -> dict[str, list[str]]:
    """Sector -> tickers with both SEC facts and price data."""
    holdings = pd.read_csv(root / "data" / "sector_top_holdings.csv")
    have_facts = {p.stem for p in (root / SEC_DIR).glob("*.json")}
    universes: dict[str, list[str]] = {}
    for etf, group in holdings.groupby("sector_symbol"):
        names = sorted(set(group.holding_symbol) & have_facts)
        names = [t for t in names if _has_price(root, t)]
        if len(names) >= 8:
            universes[etf] = names
    semis = [t for t in SEMIS if t in have_facts and _has_price(root, t)]
    if len(semis) >= 8:
        universes["SEMIS"] = semis
    return universes


def _has_price(root: Path, ticker: str) -> bool:
    return ((root / "cache" / "cache" / f"{ticker}_daily.json").exists()
            or (root / OHLCV_DIR / f"{ticker}_ohlcv.csv").exists())


def load_close(root: Path, ticker: str) -> pd.Series:
    try:
        c = load_asset_daily(ticker, project_root=root)["close"].astype(float)
    except FileNotFoundError:
        frame = pd.read_csv(root / OHLCV_DIR / f"{ticker}_ohlcv.csv",
                            parse_dates=["date"]).set_index("date")
        # Match the main asset cache, whose `close` feature is dividend/split
        # adjusted. WDC/SNDK currently enter through this OHLCV fallback.
        price_col = "adjclose" if "adjclose" in frame.columns else "close"
        c = frame[price_col].astype(float)
    c.index = pd.DatetimeIndex(c.index).normalize()
    return c[~c.index.duplicated(keep="last")].sort_index()

ALIASES = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "SalesRevenueNet", "RevenuesNetOfInterestExpense"],
    "net_income": ["NetIncomeLoss"],
    "equity": ["StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "assets": ["Assets"],
    "gross_profit": ["GrossProfit"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
            "NetCashProvidedByUsedInContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment",
              "PaymentsToAcquireProductiveAssets",
              "PaymentsToAcquireOtherProductiveAssets"],
    "lt_debt": ["LongTermDebt", "LongTermDebtNoncurrent"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
}
FLOWS = {"revenue", "net_income", "gross_profit", "cost_of_revenue", "ocf", "capex"}


# --------------------------------------------------------------------------- #
# Point-in-time extraction.
# --------------------------------------------------------------------------- #
def _fact_entries(gaap: dict, names: list[str]) -> list[dict]:
    """Merge entries across alias tags: companies switch tags over time
    (e.g. Revenues -> RevenueFromContractWithCustomer... after ASC 606), so
    first-hit selection silently truncates history. Later dedup by period end
    keeps the earliest filing."""
    merged: list[dict] = []
    for name in names:
        node = gaap.get(name)
        if not node:
            continue
        units = node.get("units", {})
        merged.extend(units.get("USD") or units.get("USD/shares") or [])
    return merged


def _quarterly_flow(entries: list[dict]) -> pd.DataFrame:
    """Quarterly flow values with the EARLIEST filing date per period (no
    restatement lookahead).

    SEC cash-flow facts are normally cumulative year-to-date in 10-Qs. Convert
    six- and nine-month values into discrete Q2/Q3 observations before forming
    TTM metrics; otherwise most OCF/capex histories contain only Q1 and FY.
    """
    rows: dict[pd.Timestamp, tuple[float, pd.Timestamp]] = {}
    annual: dict[pd.Timestamp, tuple[float, pd.Timestamp, pd.Timestamp]] = {}
    by_start: dict[pd.Timestamp, dict[pd.Timestamp, tuple[float, pd.Timestamp, int]]] = {}
    for e in entries:
        if e.get("form") not in ("10-Q", "10-K") or "start" not in e:
            continue
        start, end = pd.Timestamp(e["start"]), pd.Timestamp(e["end"])
        dur = (end - start).days
        filed = pd.Timestamp(e["filed"])
        if 60 <= dur <= 120:
            if end not in rows or filed < rows[end][1]:
                rows[end] = (float(e["val"]), filed)
            points = by_start.setdefault(start, {})
            if end not in points or filed < points[end][1]:
                points[end] = (float(e["val"]), filed, dur)
        elif 150 <= dur <= 330:
            points = by_start.setdefault(start, {})
            if end not in points or filed < points[end][1]:
                points[end] = (float(e["val"]), filed, dur)
        elif 340 <= dur <= 380:
            if end not in annual or filed < annual[end][1]:
                annual[end] = (float(e["val"]), filed, start)
            points = by_start.setdefault(start, {})
            if end not in points or filed < points[end][1]:
                points[end] = (float(e["val"]), filed, dur)

    # De-cumulate adjacent Q1 -> H1 -> 9M -> FY points sharing a fiscal start.
    for points in by_start.values():
        ordered = sorted(points.items())
        for (_, (prev_val, prev_filed, prev_dur)), \
                (end, (value, filed, dur)) in zip(ordered, ordered[1:]):
            if not 55 <= dur - prev_dur <= 125 or end in rows:
                continue
            rows[end] = (value - prev_val, max(filed, prev_filed))

    # Fallback for issuers whose cumulative start dates do not match exactly.
    q_ends = sorted(rows)
    for fy_end, (fy_val, fy_filed, fy_start) in annual.items():
        if fy_end in rows:
            continue
        in_fy = [q for q in q_ends if fy_start <= q < fy_end]
        if len(in_fy) == 3:
            q4 = fy_val - sum(rows[q][0] for q in in_fy)
            rows[fy_end] = (q4, fy_filed)
    if not rows:
        return pd.DataFrame(columns=["val", "filed"])
    out = pd.DataFrame(
        {"val": [rows[k][0] for k in sorted(rows)],
         "filed": [rows[k][1] for k in sorted(rows)]},
        index=pd.DatetimeIndex(sorted(rows), name="period_end"))
    return out


def _instant(entries: list[dict]) -> pd.DataFrame:
    rows = {}
    for e in entries:
        if e.get("form") not in ("10-Q", "10-K") or "start" in e:
            continue
        end, filed = pd.Timestamp(e["end"]), pd.Timestamp(e["filed"])
        if end not in rows or filed < rows[end][1]:
            rows[end] = (float(e["val"]), filed)
    if not rows:
        return pd.DataFrame(columns=["val", "filed"])
    return pd.DataFrame(
        {"val": [rows[k][0] for k in sorted(rows)],
         "filed": [rows[k][1] for k in sorted(rows)]},
        index=pd.DatetimeIndex(sorted(rows), name="period_end"))


def load_fundamentals(root: Path, ticker: str) -> dict[str, pd.DataFrame]:
    payload = json.loads((root / SEC_DIR / f"{ticker}.json").read_text())
    gaap = payload["facts"].get("us-gaap", {})
    out = {}
    for key, names in ALIASES.items():
        entries = _fact_entries(gaap, names)
        out[key] = _quarterly_flow(entries) if key in FLOWS else _instant(entries)
    dei = payload["facts"].get("dei", {})
    sh = dei.get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares", [])
    if not sh:
        sh = gaap.get("CommonStockSharesOutstanding", {}).get("units", {}).get("shares", [])
    rows = {}
    for e in sh:
        end, filed = pd.Timestamp(e["end"]), pd.Timestamp(e["filed"])
        if end not in rows or filed < rows[end][1]:
            rows[end] = (float(e["val"]), filed)
    out["shares"] = (pd.DataFrame(
        {"val": [rows[k][0] for k in sorted(rows)],
         "filed": [rows[k][1] for k in sorted(rows)]},
        index=pd.DatetimeIndex(sorted(rows))) if rows else pd.DataFrame(columns=["val", "filed"]))
    return out


def _known(frame: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    if frame.empty:
        return frame
    known = frame[frame["filed"] <= asof]
    return known


def _ttm(frame: pd.DataFrame, asof: pd.Timestamp) -> float:
    known = _known(frame, asof)
    if len(known) < 4:
        return np.nan
    last4 = known.tail(4)
    if (asof - last4.index[-1]).days > STALE_DAYS:
        return np.nan
    return float(last4["val"].sum())


def _ttm_ago(frame: pd.DataFrame, asof: pd.Timestamp) -> float:
    known = _known(frame, asof)
    if len(known) < 8:
        return np.nan
    return float(known.tail(8).head(4)["val"].sum())


def _latest(frame: pd.DataFrame, asof: pd.Timestamp) -> float:
    known = _known(frame, asof)
    if known.empty or (asof - known.index[-1]).days > STALE_DAYS + 100:
        return np.nan
    return float(known["val"].iloc[-1])


def _stability(frame: pd.DataFrame, asof: pd.Timestamp) -> float:
    known = _known(frame, asof)
    if len(known) < 8:
        return np.nan
    return float((known.tail(12)["val"] > 0).mean())


# --------------------------------------------------------------------------- #
# Sector-specific metrics (all point-in-time as of `asof`).
# --------------------------------------------------------------------------- #
def _operating_snapshot(f: dict, asof: pd.Timestamp) -> dict[str, float]:
    rev, rev_ago = _ttm(f["revenue"], asof), _ttm_ago(f["revenue"], asof)
    gp = _ttm(f["gross_profit"], asof)
    if np.isnan(gp):
        cor = _ttm(f["cost_of_revenue"], asof)
        gp = rev - cor if not (np.isnan(rev) or np.isnan(cor)) else np.nan
    gp_ago = _ttm_ago(f["gross_profit"], asof)
    if np.isnan(gp_ago):
        cor_ago = _ttm_ago(f["cost_of_revenue"], asof)
        gp_ago = rev_ago - cor_ago if not (np.isnan(rev_ago) or np.isnan(cor_ago)) else np.nan
    ni, ni_ago = _ttm(f["net_income"], asof), _ttm_ago(f["net_income"], asof)
    ocf, capex = _ttm(f["ocf"], asof), _ttm(f["capex"], asof)
    fcf = ocf - capex if not (np.isnan(ocf) or np.isnan(capex)) else np.nan
    cash, debt = _latest(f["cash"], asof), _latest(f["lt_debt"], asof)
    assets = _latest(f["assets"], asof)
    equity = _latest(f["equity"], asof)
    return {
        "rev": rev, "rev_ago": rev_ago, "gp": gp, "gp_ago": gp_ago,
        "ni": ni, "ni_ago": ni_ago, "ocf": ocf, "capex": capex,
        "fcf": fcf, "cash": cash, "debt": debt, "assets": assets,
        "equity": equity,
    }


def _ni_margin_series(f: dict, asof: pd.Timestamp) -> pd.Series:
    ni = _known(f["net_income"], asof).tail(12)["val"]
    rev = _known(f["revenue"], asof).tail(12)["val"]
    joined = pd.concat([ni.rename("ni"), rev.rename("rev")], axis=1).dropna()
    joined = joined[joined["rev"] > 0]
    return joined["ni"] / joined["rev"]


def _revenue_steadiness(f: dict, asof: pd.Timestamp) -> float:
    revenue = _known(f["revenue"], asof).tail(16)["val"]
    yoy = revenue.pct_change(4, fill_method=None).replace([np.inf, -np.inf], np.nan).dropna()
    return -float(yoy.tail(8).std()) if len(yoy) >= 4 else np.nan


def _common_quality(s: dict, f: dict, asof: pd.Timestamp) -> dict[str, float]:
    margins = _ni_margin_series(f, asof)
    return {
        "gross_margin": s["gp"] / s["rev"]
                        if s["rev"] and s["rev"] > 0 and not np.isnan(s["gp"]) else np.nan,
        "ni_margin": s["ni"] / s["rev"]
                     if s["rev"] and s["rev"] > 0 and not np.isnan(s["ni"]) else np.nan,
        "ocf_margin": s["ocf"] / s["rev"]
                      if s["rev"] and s["rev"] > 0 and not np.isnan(s["ocf"]) else np.nan,
        "fcf_margin": s["fcf"] / s["rev"]
                      if s["rev"] and s["rev"] > 0 and not np.isnan(s["fcf"]) else np.nan,
        "rev_growth": (s["rev"] / s["rev_ago"] - 1.0)
                      if s["rev_ago"] and s["rev_ago"] > 0 and not np.isnan(s["rev"]) else np.nan,
        "margin_steadiness": -float(margins.std()) if len(margins) >= 8 else np.nan,
        "low_leverage": -(s["debt"] / s["assets"])
                        if s["assets"] and s["assets"] > 0 and not np.isnan(s["debt"]) else np.nan,
        "net_cash_ratio": ((s["cash"] if not np.isnan(s["cash"]) else 0.0)
                           - (s["debt"] if not np.isnan(s["debt"]) else 0.0)) / s["assets"]
                          if s["assets"] and s["assets"] > 0 else np.nan,
        "earnings_stability": _stability(f["net_income"], asof),
    }


def metrics_financials(f: dict, asof: pd.Timestamp) -> dict[str, float]:
    s = _operating_snapshot(f, asof)
    return {
        "roe": s["ni"] / s["equity"]
               if s["equity"] and s["equity"] > 0 and not np.isnan(s["ni"]) else np.nan,
        "capital_ratio": s["equity"] / s["assets"]
                         if s["assets"] and s["assets"] > 0 and s["equity"] else np.nan,
        "earnings_stability": _stability(f["net_income"], asof),
        "ni_growth": (s["ni"] / s["ni_ago"] - 1.0)
                     if s["ni_ago"] and s["ni_ago"] > 0 and not np.isnan(s["ni"]) else np.nan,
    }


def metrics_technology(f: dict, asof: pd.Timestamp) -> dict[str, float]:
    q = _common_quality(_operating_snapshot(f, asof), f, asof)
    return {k: q[k] for k in (
        "gross_margin", "fcf_margin", "rev_growth", "net_cash_ratio", "earnings_stability"
    )}


def metrics_communication_services(f: dict, asof: pd.Timestamp) -> dict[str, float]:
    q = _common_quality(_operating_snapshot(f, asof), f, asof)
    return {k: q[k] for k in (
        "ni_margin", "fcf_margin", "rev_growth", "net_cash_ratio", "margin_steadiness"
    )}


def metrics_consumer_staples(f: dict, asof: pd.Timestamp) -> dict[str, float]:
    q = _common_quality(_operating_snapshot(f, asof), f, asof)
    return {k: q[k] for k in (
        "ni_margin", "margin_steadiness", "fcf_margin", "low_leverage", "earnings_stability"
    )}


def metrics_utilities(f: dict, asof: pd.Timestamp) -> dict[str, float]:
    s = _operating_snapshot(f, asof)
    q = _common_quality(s, f, asof)
    capex_coverage = (s["ocf"] / s["capex"]
                      if s["capex"] and s["capex"] > 0 and not np.isnan(s["ocf"]) else np.nan)
    return {
        "ocf_margin": q["ocf_margin"],
        "capex_coverage": capex_coverage,
        "low_leverage": q["low_leverage"],
        "revenue_steadiness": _revenue_steadiness(f, asof),
        "earnings_stability": q["earnings_stability"],
    }


def metrics_health_care(f: dict, asof: pd.Timestamp) -> dict[str, float]:
    q = _common_quality(_operating_snapshot(f, asof), f, asof)
    return {k: q[k] for k in (
        "gross_margin", "fcf_margin", "rev_growth", "net_cash_ratio", "earnings_stability"
    )}


def metrics_industrials(f: dict, asof: pd.Timestamp) -> dict[str, float]:
    q = _common_quality(_operating_snapshot(f, asof), f, asof)
    return {k: q[k] for k in (
        "gross_margin", "fcf_margin", "rev_growth", "low_leverage", "margin_steadiness"
    )}


def metrics_materials(f: dict, asof: pd.Timestamp) -> dict[str, float]:
    q = _common_quality(_operating_snapshot(f, asof), f, asof)
    return {k: q[k] for k in (
        "gross_margin", "fcf_margin", "low_leverage", "rev_growth", "earnings_stability"
    )}


def metrics_energy(f: dict, asof: pd.Timestamp) -> dict[str, float]:
    q = _common_quality(_operating_snapshot(f, asof), f, asof)
    return {k: q[k] for k in (
        "ocf_margin", "fcf_margin", "low_leverage", "rev_growth", "earnings_stability"
    )}


def metrics_consumer_discretionary(f: dict, asof: pd.Timestamp) -> dict[str, float]:
    q = _common_quality(_operating_snapshot(f, asof), f, asof)
    return {k: q[k] for k in (
        "gross_margin", "fcf_margin", "rev_growth", "low_leverage", "margin_steadiness"
    )}


def metrics_real_estate(f: dict, asof: pd.Timestamp) -> dict[str, float]:
    """Real estate: GAAP net income is depreciation-distorted (FFO is the
    industry metric but not a standard XBRL tag), so quality is read off
    operating cash flow and leverage. Disclosed caveat."""
    rev = _ttm(f["revenue"], asof)
    ocf, ocf_ago = _ttm(f["ocf"], asof), _ttm_ago(f["ocf"], asof)
    debt, assets = _latest(f["lt_debt"], asof), _latest(f["assets"], asof)
    known_ocf = _known(f["ocf"], asof).tail(12)["val"]
    return {
        "ocf_margin": ocf / rev if rev and rev > 0 and not np.isnan(ocf) else np.nan,
        "ocf_growth": (ocf / ocf_ago - 1.0) if ocf_ago and ocf_ago > 0 and not np.isnan(ocf) else np.nan,
        "low_leverage": -(debt / assets) if assets and assets > 0 and not np.isnan(debt) else np.nan,
        "ocf_stability": float((known_ocf > 0).mean()) if len(known_ocf) >= 8 else np.nan,
    }


def metrics_semis(f: dict, asof: pd.Timestamp) -> dict[str, float]:
    """Semiconductors / memory: deep cyclicals where the CYCLE dominates.
    Margin LEVEL rewards stable franchises (TXN/ADI); margin TREND (gross
    margin now vs a year ago) is the cycle-turn signal the DRAM names live
    and die by. Both included so the study can say which one pays."""
    s = _operating_snapshot(f, asof)
    q = _common_quality(s, f, asof)
    gm = q["gross_margin"]
    gm_ago = (s["gp_ago"] / s["rev_ago"]
              if s["rev_ago"] and s["rev_ago"] > 0 and not np.isnan(s["gp_ago"]) else np.nan)
    return {
        "gross_margin": gm,
        "gm_trend": gm - gm_ago if not (np.isnan(gm) or np.isnan(gm_ago)) else np.nan,
        "rev_growth": q["rev_growth"],
        "fcf_margin": q["fcf_margin"],
        "net_cash_ratio": q["net_cash_ratio"],
    }


BOOK_METRICS = {
    "XLB": metrics_materials,
    "XLC": metrics_communication_services,
    "XLE": metrics_energy,
    "XLF": metrics_financials,
    "XLI": metrics_industrials,
    "XLK": metrics_technology,
    "XLP": metrics_consumer_staples,
    "XLRE": metrics_real_estate,
    "XLU": metrics_utilities,
    "XLV": metrics_health_care,
    "XLY": metrics_consumer_discretionary,
    "SEMIS": metrics_semis,
}


def quality_scores(sector: str, funds: dict[str, dict], asof: pd.Timestamp,
                   prices: dict[str, pd.Series]) -> pd.DataFrame:
    """Cross-sectional z-scored quality within the sector, point-in-time."""
    metric_fn = BOOK_METRICS[sector]
    rows = {}
    for t, f in funds.items():
        px = prices[t]
        px_asof = px[px.index <= asof]
        if px_asof.empty:
            continue
        shares = _latest(f["shares"], asof)
        mcap = shares * float(px_asof.iloc[-1]) if not np.isnan(shares) else np.nan
        if not np.isnan(mcap) and mcap < MIN_MARKET_CAP:
            continue
        rows[t] = metric_fn(f, asof)
    frame = pd.DataFrame(rows).T
    if frame.empty:
        return frame
    metric_columns = list(frame.columns)
    z = frame[metric_columns].apply(
        lambda col: (col - col.mean()) / col.std()
        if col.std() and col.notna().sum() >= 4 else col * np.nan
    )
    for metric in metric_columns:
        frame[f"{metric}_z"] = z[metric]
    frame["n_metrics"] = z.notna().sum(axis=1)
    frame["quality_z"] = z.mean(axis=1).where(frame["n_metrics"] >= MIN_METRICS)
    frame["eligible"] = frame["quality_z"].notna()
    return frame


# --------------------------------------------------------------------------- #
# Event study.
# --------------------------------------------------------------------------- #
def _signal_stats(panel: pd.DataFrame, signal_col: str) -> dict[str, float | int]:
    clean = panel[["date", signal_col, "fwd_rel"]].dropna().sort_values("date")
    ics: list[tuple[pd.Timestamp, float]] = []
    spreads: list[tuple[pd.Timestamp, float]] = []
    for date, group in clean.groupby("date", sort=True):
        if len(group) < 4 or group[signal_col].nunique() < 2:
            continue
        ic = group[signal_col].corr(group["fwd_rel"], method="spearman")
        if not np.isnan(ic):
            ics.append((pd.Timestamp(date), float(ic)))
        median = group[signal_col].median()
        high = group.loc[group[signal_col] >= median, "fwd_rel"]
        low = group.loc[group[signal_col] < median, "fwd_rel"]
        if len(high) and len(low):
            spreads.append((pd.Timestamp(date), float(high.mean() - low.mean())))

    ic_values = pd.Series(dict(ics), dtype="float64").sort_index()
    spread_values = pd.Series(dict(spreads), dtype="float64").sort_index()
    nonoverlap = spread_values.iloc[::6]
    tstat = (float(nonoverlap.mean() / (nonoverlap.std() / np.sqrt(len(nonoverlap))))
             if len(nonoverlap) > 2 and nonoverlap.std() > 0 else np.nan)
    return {
        "observations": int(len(clean)),
        "months": int(len(ic_values)),
        "avg_monthly_IC": float(ic_values.mean()) if len(ic_values) else np.nan,
        "IC_pos_share_%": float((ic_values > 0).mean() * 100) if len(ic_values) else np.nan,
        "avg_6m_top_minus_bottom_%": float(spread_values.mean() * 100)
                                      if len(spread_values) else np.nan,
        "nonoverlap_spread_%": float(nonoverlap.mean() * 100) if len(nonoverlap) else np.nan,
        "nonoverlap_n": int(len(nonoverlap)),
        "spread_tstat_nonoverlap": tstat,
    }


def _rounded_stats(stats: dict[str, float | int]) -> dict[str, float | int]:
    return {
        "observations": int(stats["observations"]),
        "months": int(stats["months"]),
        "avg_monthly_IC": round(float(stats["avg_monthly_IC"]), 3),
        "IC_pos_share_%": round(float(stats["IC_pos_share_%"]), 0),
        "avg_6m_top_minus_bottom_%": round(float(stats["avg_6m_top_minus_bottom_%"]), 2),
        "nonoverlap_spread_%": round(float(stats["nonoverlap_spread_%"]), 2),
        "nonoverlap_n": int(stats["nonoverlap_n"]),
        "spread_tstat_nonoverlap": round(float(stats["spread_tstat_nonoverlap"]), 2),
    }


def event_study(sector: str, tickers: list[str], root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    funds = {t: load_fundamentals(root, t) for t in tickers}
    prices = {t: load_close(root, t) for t in tickers}
    grid = pd.date_range("2010-01-31", "2025-11-30", freq="ME")
    obs = []
    for asof in grid:
        scores = quality_scores(sector, funds, asof, prices)
        if len(scores) < 5 or scores["quality_z"].notna().sum() < 5:
            continue
        fwd = {}
        for t in scores.index:
            px = prices[t]
            # SEC Company Facts provides a filing date but not a safely usable
            # market timestamp. Trade from the first close strictly after the
            # score date so an after-close filing cannot enter at that close.
            pos = px.index.searchsorted(asof, side="right")
            if pos >= len(px) or pos + FWD_DAYS >= len(px):
                fwd[t] = np.nan
            else:
                fwd[t] = float(px.iloc[pos + FWD_DAYS] / px.iloc[pos] - 1.0)
        fwd = pd.Series(fwd)
        peer = fwd.mean()
        metric_z_cols = [c for c in scores.columns if c.endswith("_z") and c != "quality_z"]
        for t in scores.index:
            row = {
                "date": asof,
                "ticker": t,
                "quality_z": scores.loc[t, "quality_z"],
                "n_metrics": scores.loc[t, "n_metrics"],
                "fwd_rel": fwd[t] - peer if not np.isnan(fwd[t]) else np.nan,
            }
            row.update({column: scores.loc[t, column] for column in metric_z_cols})
            obs.append(row)
    panel = pd.DataFrame(obs)
    summary = pd.DataFrame([{"sector": sector, **_rounded_stats(_signal_stats(panel, "quality_z"))}])
    return panel, summary


def metric_attribution(sector: str, panel: pd.DataFrame) -> pd.DataFrame:
    metric_z_cols = sorted(c for c in panel.columns if c.endswith("_z") and c != "quality_z")
    rows = []
    for signal_col in ["quality_z", *metric_z_cols]:
        metric = "composite" if signal_col == "quality_z" else signal_col.removesuffix("_z")
        rows.append({
            "sector": sector,
            "specification": SECTOR_SPECIFICATION[sector],
            "metric": metric,
            "kind": "composite" if signal_col == "quality_z" else "standalone_metric",
            **_rounded_stats(_signal_stats(panel, signal_col)),
        })
    return pd.DataFrame(rows)


def metric_ablation(sector: str, panel: pd.DataFrame) -> pd.DataFrame:
    metric_z_cols = sorted(c for c in panel.columns if c.endswith("_z") and c != "quality_z")
    rows = []
    for excluded in metric_z_cols:
        remaining = [column for column in metric_z_cols if column != excluded]
        minimum = min(MIN_METRICS, len(remaining))
        without = panel[remaining].mean(axis=1).where(panel[remaining].notna().sum(axis=1) >= minimum)
        sample = panel.loc[panel["quality_z"].notna() & without.notna()].copy()
        sample["without_metric_z"] = without.loc[sample.index]
        baseline = _signal_stats(sample, "quality_z")
        ablated = _signal_stats(sample, "without_metric_z")
        rows.append({
            "sector": sector,
            "specification": SECTOR_SPECIFICATION[sector],
            "excluded_metric": excluded.removesuffix("_z"),
            "observations": int(baseline["observations"]),
            "baseline_IC": round(float(baseline["avg_monthly_IC"]), 3),
            "without_metric_IC": round(float(ablated["avg_monthly_IC"]), 3),
            "metric_IC_contribution": round(
                float(baseline["avg_monthly_IC"] - ablated["avg_monthly_IC"]), 3),
            "baseline_nonoverlap_spread_%": round(float(baseline["nonoverlap_spread_%"]), 2),
            "without_metric_nonoverlap_spread_%": round(float(ablated["nonoverlap_spread_%"]), 2),
            "metric_spread_contribution_%": round(
                float(baseline["nonoverlap_spread_%"] - ablated["nonoverlap_spread_%"]), 2),
        })
    return pd.DataFrame(rows)


def current_scorecard(sector: str, tickers: list[str], root: Path) -> pd.DataFrame:
    funds = {t: load_fundamentals(root, t) for t in tickers}
    prices = {t: load_close(root, t) for t in tickers}
    asof = max(px.index[-1] for px in prices.values())
    scores = quality_scores(sector, funds, asof, prices)
    return scores.sort_values("quality_z", ascending=False).round(3)


def _markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    def clean(value: object) -> str:
        return str(value).replace("|", "\\|")

    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(clean(v) for v in row) + " |" for row in rows)
    return "\n".join(lines)


def write_report(out: Path, summary: pd.DataFrame,
                 universes: dict[str, list[str]],
                 cards: dict[str, pd.DataFrame],
                 attribution: pd.DataFrame,
                 ablation: pd.DataFrame) -> None:
    leadership_rows = []
    specification_rows = []
    driver_rows = []
    for row in summary.itertuples(index=False):
        card = cards[row.sector]
        eligible = card[card["eligible"]]
        top = ", ".join(eligible.index[:3]) or "n/a"
        bottom = ", ".join(eligible.index[-3:]) or "n/a"
        leadership_rows.append([
            row.sector, f"{len(eligible)}/{len(card)}", top, bottom,
        ])
        sector_attr = attribution[
            (attribution["sector"] == row.sector)
            & (attribution["kind"] == "standalone_metric")
        ].dropna(subset=["nonoverlap_spread_%"])
        metrics = ", ".join(sector_attr["metric"])
        specification_rows.append([row.sector, row.specification, metrics])
        if sector_attr.empty:
            best_metric = worst_metric = "n/a"
        else:
            best = sector_attr.loc[sector_attr["nonoverlap_spread_%"].idxmax()]
            worst = sector_attr.loc[sector_attr["nonoverlap_spread_%"].idxmin()]
            best_metric = f'{best["metric"]} ({best["nonoverlap_spread_%"]:.2f}%)'
            worst_metric = f'{worst["metric"]} ({worst["nonoverlap_spread_%"]:.2f}%)'
        sector_ablation = ablation[ablation["sector"] == row.sector].dropna(
            subset=["metric_spread_contribution_%"])
        if sector_ablation.empty:
            helpful = "n/a"
        else:
            contribution = sector_ablation.loc[
                sector_ablation["metric_spread_contribution_%"].idxmax()]
            helpful = (f'{contribution["excluded_metric"]} '
                       f'({contribution["metric_spread_contribution_%"]:+.2f}%)')
        driver_rows.append([row.sector, best_metric, worst_metric, helpful])

    spread_col = "nonoverlap_spread_%"
    validation_rows = []
    for _, row in summary.iterrows():
        validation_rows.append([
            row["sector"], row["specification"], int(row["names"]), int(row["months"]),
            f'{row["avg_monthly_IC"]:.3f}', f'{row[spread_col]:.2f}%',
            int(row["nonoverlap_n"]), f'{row["spread_tstat_nonoverlap"]:.2f}',
        ])

    sector_names = set().union(*(
        set(names) for sector, names in universes.items() if sector != "SEMIS"
    ))
    semis_extras = sorted(set(universes.get("SEMIS", [])) - sector_names)
    unique_sector_names = len(sector_names)
    strong = summary[summary["spread_tstat_nonoverlap"].abs() >= 1.96]
    evidence = ("No book reaches |t| >= 1.96 on the non-overlapping test."
                if strong.empty else
                "Books reaching |t| >= 1.96: " + ", ".join(strong["sector"]))
    text = f"""# Sector quality books

## Scope

- {unique_sector_names} unique sector names across 11 sector books.
- {len(universes.get('SEMIS', []))} names in the dedicated semiconductor/memory book.
- {unique_sector_names + len(semis_extras)} distinct SEC fact payloads in scope; semiconductor extras: {', '.join(semis_extras)}.
- SEC facts are aligned to filing dates. Forward returns start at the first close strictly after each score date.
- Companies need at least {MIN_METRICS} comparable metrics to receive a quality score.
- Every book has a dedicated metric specification and separate standalone/ablation attribution.

## Book specifications

{_markdown_table(
    ["Book", "Specification", "Higher-is-better metrics"],
    specification_rows,
)}

## Validation

{_markdown_table(
    ["Book", "Specification", "Names", "Months", "Avg IC", "6m spread", "N", "t-stat"],
    validation_rows,
)}

{evidence} Positive rankings should therefore be treated as research leads, not established alpha.

## Metric attribution

{_markdown_table(
    ["Book", "Best standalone", "Worst standalone", "Most helpful in composite"],
    driver_rows,
)}

Standalone values are non-overlapping top-minus-bottom six-month spreads. The final column is the decline in composite spread when that metric is removed; positive values indicate that the metric helped the composite on the matched sample.

## Current scorecards

{_markdown_table(
    ["Book", "Eligible", "Top three", "Bottom three"],
    leadership_rows,
)}

## Interpretation limits

- The sector universe is the union of names observed in SEC N-PORT top-holdings snapshots available from 2019 onward. Applying that union back to 2010 is not point-in-time constituent selection and can introduce composition/survivorship bias.
- The semiconductor book is a fixed research universe; SNDK price history begins in 2025, so it contributes only to recent cross-sections.
- Six-month monthly observations overlap. The reported t-stat uses every sixth observation to reduce that dependence.
- Metric attribution tests many sector/metric combinations and is not corrected for multiple testing; treat isolated strong values as hypotheses.
- A missing historical share count does not automatically exclude a company from the top-holdings universe; the $5B screen is enforced only when a point-in-time share count is available.
- SEC tag coverage differs by issuer. The scorecard exposes `n_metrics` and `eligible` so sparse rankings are not silently promoted.
"""
    (out / "report.md").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--sector", default=None, help="Run a single book (e.g. SEMIS).")
    args = parser.parse_args()
    root = resolve_project_root(args.project_root)
    out = root / OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)

    universes = build_universes(root)
    if args.sector:
        universes = {args.sector.upper(): universes[args.sector.upper()]}
    summaries = []
    cards = {}
    attributions = []
    ablations = []
    for sector, tickers in sorted(universes.items()):
        panel, summary = event_study(sector, tickers, root)
        summary.insert(1, "specification", SECTOR_SPECIFICATION[sector])
        summary.insert(2, "names", len(tickers))
        panel.to_csv(out / f"{sector}_panel.csv", index=False)
        summaries.append(summary)
        attribution = metric_attribution(sector, panel)
        attribution.to_csv(out / f"{sector}_metric_attribution.csv", index=False)
        attributions.append(attribution)
        ablation = metric_ablation(sector, panel)
        ablation.to_csv(out / f"{sector}_metric_ablation.csv", index=False)
        ablations.append(ablation)
        card = current_scorecard(sector, tickers, root)
        card.to_csv(out / f"{sector}_scorecard.csv")
        cards[sector] = card
        eligible = card[card["eligible"]]
        top = ", ".join(eligible.index[:3])
        bottom = ", ".join(eligible.index[-3:])
        print(f"{sector}: top = {top} | bottom = {bottom}")
    combined = pd.concat(summaries)
    combined_attribution = pd.concat(attributions, ignore_index=True)
    combined_ablation = pd.concat(ablations, ignore_index=True)
    combined.to_csv(out / "summary.csv", index=False)
    combined_attribution.to_csv(out / "metric_attribution.csv", index=False)
    combined_ablation.to_csv(out / "metric_ablation.csv", index=False)
    specifications = (combined_attribution[combined_attribution["kind"] == "standalone_metric"]
                      .groupby(["sector", "specification"], as_index=False)["metric"]
                      .agg(", ".join))
    specifications.to_csv(out / "book_specifications.csv", index=False)
    write_report(out, combined, universes, cards, combined_attribution, combined_ablation)
    print("\n=== Quality -> forward 6m vs sector peers (point-in-time, filed-date aligned) ===")
    print(combined.to_string(index=False))


if __name__ == "__main__":
    main()
