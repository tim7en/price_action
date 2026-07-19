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

Sector metric sets (all computed trailing-twelve-months, point-in-time):

  Financials  : ROE, capital ratio (equity/assets), earnings stability,
                TTM net-income growth.
  Technology  : gross margin, FCF margin, revenue growth, net-cash ratio,
                earnings stability.

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
# the dedicated semiconductor/memory book. Sector archetype decides metrics.
SEMIS = ["NVDA", "AMD", "AVGO", "MU", "INTC", "TXN", "QCOM", "AMAT",
         "LRCX", "ADI", "WDC", "STX", "SNDK"]
SECTOR_ARCHETYPE = {
    "XLF": "financial",
    "XLK": "asset_light", "XLC": "asset_light",
    "XLP": "defensive", "XLU": "defensive", "XLV": "defensive",
    "XLI": "cyclical", "XLB": "cyclical", "XLE": "cyclical", "XLY": "cyclical",
    "XLRE": "reit",
    "SEMIS": "semis",
}
MIN_MARKET_CAP = 5e9
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
        c = load_asset_daily(ticker)["close"].astype(float)
    except FileNotFoundError:
        c = (pd.read_csv(root / OHLCV_DIR / f"{ticker}_ohlcv.csv",
                         parse_dates=["date"]).set_index("date")["close"].astype(float))
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
    "ocf": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
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
    restatement lookahead). Q4 derived as FY minus the three known quarters."""
    rows = {}
    annual = {}
    for e in entries:
        if e.get("form") not in ("10-Q", "10-K") or "start" not in e:
            continue
        start, end = pd.Timestamp(e["start"]), pd.Timestamp(e["end"])
        dur = (end - start).days
        filed = pd.Timestamp(e["filed"])
        if 60 <= dur <= 120:
            if end not in rows or filed < rows[end][1]:
                rows[end] = (float(e["val"]), filed)
        elif 340 <= dur <= 380:
            if end not in annual or filed < annual[end][1]:
                annual[end] = (float(e["val"]), filed, start)
    # derive missing Q4s
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
def metrics_financials(f: dict, asof: pd.Timestamp) -> dict[str, float]:
    ni, ni_ago = _ttm(f["net_income"], asof), _ttm_ago(f["net_income"], asof)
    eq, assets = _latest(f["equity"], asof), _latest(f["assets"], asof)
    return {
        "roe": ni / eq if eq and eq > 0 and not np.isnan(ni) else np.nan,
        "capital_ratio": eq / assets if assets and assets > 0 and eq else np.nan,
        "stability": _stability(f["net_income"], asof),
        "ni_growth": (ni / ni_ago - 1.0) if ni_ago and ni_ago > 0 and not np.isnan(ni) else np.nan,
    }


def metrics_technology(f: dict, asof: pd.Timestamp) -> dict[str, float]:
    rev, rev_ago = _ttm(f["revenue"], asof), _ttm_ago(f["revenue"], asof)
    gp = _ttm(f["gross_profit"], asof)
    if np.isnan(gp):
        cor = _ttm(f["cost_of_revenue"], asof)
        gp = rev - cor if not (np.isnan(rev) or np.isnan(cor)) else np.nan
    ocf, capex = _ttm(f["ocf"], asof), _ttm(f["capex"], asof)
    fcf = ocf - capex if not (np.isnan(ocf) or np.isnan(capex)) else np.nan
    cash, debt = _latest(f["cash"], asof), _latest(f["lt_debt"], asof)
    assets = _latest(f["assets"], asof)
    return {
        "gross_margin": gp / rev if rev and rev > 0 and not np.isnan(gp) else np.nan,
        "fcf_margin": fcf / rev if rev and rev > 0 and not np.isnan(fcf) else np.nan,
        "rev_growth": (rev / rev_ago - 1.0) if rev_ago and rev_ago > 0 and not np.isnan(rev) else np.nan,
        "net_cash_ratio": ((cash if not np.isnan(cash) else 0.0)
                           - (debt if not np.isnan(debt) else 0.0)) / assets
                          if assets and assets > 0 else np.nan,
        "stability": _stability(f["net_income"], asof),
    }


def _ni_margin_series(f: dict, asof: pd.Timestamp) -> pd.Series:
    ni = _known(f["net_income"], asof).tail(12)["val"]
    rev = _known(f["revenue"], asof).tail(12)["val"]
    joined = pd.concat([ni.rename("ni"), rev.rename("rev")], axis=1).dropna()
    joined = joined[joined["rev"] > 0]
    return joined["ni"] / joined["rev"]


def metrics_defensive(f: dict, asof: pd.Timestamp) -> dict[str, float]:
    """Staples / Utilities / Health Care: steadiness over growth (Graham's
    defensive tests): margin level AND margin stability, cash conversion,
    conservative leverage, unbroken earnings."""
    rev = _ttm(f["revenue"], asof)
    ni = _ttm(f["net_income"], asof)
    ocf, capex = _ttm(f["ocf"], asof), _ttm(f["capex"], asof)
    fcf = ocf - capex if not (np.isnan(ocf) or np.isnan(capex)) else np.nan
    debt, assets = _latest(f["lt_debt"], asof), _latest(f["assets"], asof)
    margins = _ni_margin_series(f, asof)
    return {
        "ni_margin": ni / rev if rev and rev > 0 and not np.isnan(ni) else np.nan,
        "margin_steadiness": -float(margins.std()) if len(margins) >= 8 else np.nan,
        "fcf_margin": fcf / rev if rev and rev > 0 and not np.isnan(fcf) else np.nan,
        "low_leverage": -(debt / assets) if assets and assets > 0 and not np.isnan(debt) else np.nan,
        "stability": _stability(f["net_income"], asof),
    }


def metrics_cyclical(f: dict, asof: pd.Timestamp) -> dict[str, float]:
    """Industrials / Materials / Energy / Cons-Cyclical: survivability first
    (leverage), cash through the cycle, then growth."""
    rev, rev_ago = _ttm(f["revenue"], asof), _ttm_ago(f["revenue"], asof)
    ni = _ttm(f["net_income"], asof)
    ocf, capex = _ttm(f["ocf"], asof), _ttm(f["capex"], asof)
    fcf = ocf - capex if not (np.isnan(ocf) or np.isnan(capex)) else np.nan
    debt, assets = _latest(f["lt_debt"], asof), _latest(f["assets"], asof)
    return {
        "fcf_margin": fcf / rev if rev and rev > 0 and not np.isnan(fcf) else np.nan,
        "ni_margin": ni / rev if rev and rev > 0 and not np.isnan(ni) else np.nan,
        "low_leverage": -(debt / assets) if assets and assets > 0 and not np.isnan(debt) else np.nan,
        "rev_growth": (rev / rev_ago - 1.0) if rev_ago and rev_ago > 0 and not np.isnan(rev) else np.nan,
        "stability": _stability(f["net_income"], asof),
    }


def metrics_reit(f: dict, asof: pd.Timestamp) -> dict[str, float]:
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
    rev, rev_ago = _ttm(f["revenue"], asof), _ttm_ago(f["revenue"], asof)
    gp = _ttm(f["gross_profit"], asof)
    if np.isnan(gp):
        cor = _ttm(f["cost_of_revenue"], asof)
        gp = rev - cor if not (np.isnan(rev) or np.isnan(cor)) else np.nan
    gp_ago = _ttm_ago(f["gross_profit"], asof)
    if np.isnan(gp_ago):
        cor_ago = _ttm_ago(f["cost_of_revenue"], asof)
        gp_ago = rev_ago - cor_ago if not (np.isnan(rev_ago) or np.isnan(cor_ago)) else np.nan
    gm = gp / rev if rev and rev > 0 and not np.isnan(gp) else np.nan
    gm_ago = gp_ago / rev_ago if rev_ago and rev_ago > 0 and not np.isnan(gp_ago) else np.nan
    ocf, capex = _ttm(f["ocf"], asof), _ttm(f["capex"], asof)
    fcf = ocf - capex if not (np.isnan(ocf) or np.isnan(capex)) else np.nan
    cash, debt = _latest(f["cash"], asof), _latest(f["lt_debt"], asof)
    assets = _latest(f["assets"], asof)
    return {
        "gross_margin": gm,
        "gm_trend": gm - gm_ago if not (np.isnan(gm) or np.isnan(gm_ago)) else np.nan,
        "rev_growth": (rev / rev_ago - 1.0) if rev_ago and rev_ago > 0 and not np.isnan(rev) else np.nan,
        "fcf_margin": fcf / rev if rev and rev > 0 and not np.isnan(fcf) else np.nan,
        "net_cash_ratio": ((cash if not np.isnan(cash) else 0.0)
                           - (debt if not np.isnan(debt) else 0.0)) / assets
                          if assets and assets > 0 else np.nan,
    }


ARCHETYPE_METRICS = {
    "financial": metrics_financials,
    "asset_light": metrics_technology,
    "defensive": metrics_defensive,
    "cyclical": metrics_cyclical,
    "reit": metrics_reit,
    "semis": metrics_semis,
}


def quality_scores(sector: str, funds: dict[str, dict], asof: pd.Timestamp,
                   prices: dict[str, pd.Series]) -> pd.DataFrame:
    """Cross-sectional z-scored quality within the sector, point-in-time."""
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
        rows[t] = SECTOR_METRICS[sector](f, asof)
    frame = pd.DataFrame(rows).T
    if frame.empty:
        return frame
    z = frame.apply(lambda col: (col - col.mean()) / col.std() if col.std() and col.notna().sum() >= 4 else col * np.nan)
    frame["quality_z"] = z.mean(axis=1)
    frame["n_metrics"] = z.notna().sum(axis=1)
    return frame


# --------------------------------------------------------------------------- #
# Event study.
# --------------------------------------------------------------------------- #
def event_study(sector: str, root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    tickers = SECTOR_UNIVERSE[sector]
    funds = {t: load_fundamentals(root, t) for t in tickers}
    prices = {}
    for t in tickers:
        c = load_asset_daily(t)["close"].astype(float)
        prices[t] = c[~c.index.duplicated(keep="last")].sort_index()
    grid = pd.date_range("2010-01-31", "2025-11-30", freq="ME")
    obs = []
    for asof in grid:
        scores = quality_scores(sector, funds, asof, prices)
        if len(scores) < 5 or scores["quality_z"].notna().sum() < 5:
            continue
        fwd = {}
        for t in scores.index:
            px = prices[t]
            pos = px.index.searchsorted(asof)
            if pos >= len(px) or pos + FWD_DAYS >= len(px):
                fwd[t] = np.nan
            else:
                fwd[t] = float(px.iloc[pos + FWD_DAYS] / px.iloc[pos] - 1.0)
        fwd = pd.Series(fwd)
        peer = fwd.mean()
        for t in scores.index:
            obs.append({"date": asof, "ticker": t, "quality_z": scores.loc[t, "quality_z"],
                        "fwd_rel": fwd[t] - peer if not np.isnan(fwd[t]) else np.nan})
    panel = pd.DataFrame(obs)
    # summary
    clean = panel.dropna()
    months = clean.groupby("date")
    ics = months.apply(lambda g: g["quality_z"].corr(g["fwd_rel"], method="spearman"),
                       include_groups=False).dropna()
    # top-half minus bottom-half, monthly then averaged; plus non-overlapping semiannual
    def spread(g):
        med = g["quality_z"].median()
        return g.loc[g["quality_z"] >= med, "fwd_rel"].mean() - g.loc[g["quality_z"] < med, "fwd_rel"].mean()
    spreads = months.apply(spread, include_groups=False).dropna()
    semi = spreads[::6]
    summary = pd.DataFrame([{
        "sector": sector,
        "months": len(ics),
        "avg_monthly_IC": round(float(ics.mean()), 3),
        "IC_pos_share_%": round(float((ics > 0).mean()) * 100, 0),
        "avg_6m_top_minus_bottom_%": round(float(spreads.mean()) * 100, 2),
        "nonoverlap_spread_%": round(float(semi.mean()) * 100, 2),
        "nonoverlap_n": len(semi),
        "spread_tstat_nonoverlap": round(float(semi.mean() / (semi.std() / np.sqrt(len(semi)))), 2)
        if len(semi) > 2 and semi.std() > 0 else np.nan,
    }])
    return panel, summary


def current_scorecard(sector: str, root: Path) -> pd.DataFrame:
    tickers = SECTOR_UNIVERSE[sector]
    funds = {t: load_fundamentals(root, t) for t in tickers}
    prices = {t: load_asset_daily(t)["close"].astype(float).sort_index() for t in tickers}
    asof = max(px.index[-1] for px in prices.values())
    scores = quality_scores(sector, funds, asof, prices)
    return scores.sort_values("quality_z", ascending=False).round(3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=None)
    args = parser.parse_args()
    root = resolve_project_root(args.project_root)
    out = root / OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)

    summaries = []
    for sector in SECTOR_UNIVERSE:
        panel, summary = event_study(sector, root)
        panel.to_csv(out / f"{sector}_panel.csv", index=False)
        summaries.append(summary)
        print(f"=== {sector}: quality (point-in-time, filed-date aligned) -> fwd 6m vs peers ===")
        print(summary.to_string(index=False))
        card = current_scorecard(sector, root)
        card.to_csv(out / f"{sector}_scorecard.csv")
        print(f"\n--- {sector} current scorecard ---")
        print(card.to_string())
        print()
    pd.concat(summaries).to_csv(out / "summary.csv", index=False)


if __name__ == "__main__":
    main()
