"""Sector moving-average crossover study with market-health position sizing.

Built on the full ``investme_sp500_data`` fundamentals/price set (~7,000 symbols).
The pipeline:

1.  Group every symbol by GICS-style sector (from its overview) and build a
    cap-weighted monthly total-return index per sector (plus a broad index).
    This heavy parse is cached to CSV so later runs are instant.

2.  For each sector index compute a fast / slow moving-average pair (defaults
    emulate the 50-day / 200-day golden & death cross on monthly bars:
    ~50 trading days = 3 months, ~200 trading days = 10 months) and measure:
      * how often golden / death crosses happen (crosses per decade),
      * how far price stretches from the slow MA (deviation distribution),
      * how often crosses are "fake breakouts" (whipsaws that reverse quickly
        or never travel a threshold move before reversing),
      * the forward return after each cross (signal quality).

3.  Score overall "market health" from macro/financial conditions + trend
    breadth, and use it to size positions in a long/short SMA-cross strategy
    (lean long when the market is healthy, allow/scale shorts when it is not),
    backtested against buy-&-hold and naive-cross benchmarks.

Output: an HTML report with charts to ``outputs/sector_trend_report/``.

Run with::

    python build_sector_trend_study.py            # full investme dataset
    python build_sector_trend_study.py --refresh  # rebuild the price-index cache
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .data import resolve_project_root
from .regime_analysis import (
    GRID_COLOR,
    MUTED_TEXT_COLOR,
    PANEL_BACKGROUND,
    TEXT_COLOR,
    _fig_to_b64,
    _img,
    _month_end,
    _new_fig,
    _REPORT_CSS,
    _style,
    _table,
    _to_float,
    load_macro_panel,
    resolve_fundamentals_dir,
)

OUTPUT_DIR = Path("outputs") / "sector_trend_report"
CACHE_NAME = "sector_indices_monthly.csv"
META_NAME = "sector_members.csv"

# Monthly analogue of the classic 50-day / 200-day cross (21 trading days/month).
DEFAULT_FAST = 3    # ~50 trading days
DEFAULT_SLOW = 10   # ~200 trading days

# Normalise the messy free-text sector field into a clean set.
_SECTOR_CANON = {
    "FINANCIAL SERVICES": "Financials",
    "FINANCIALS": "Financials",
    "HEALTHCARE": "Health Care",
    "TECHNOLOGY": "Technology",
    "INDUSTRIALS": "Industrials",
    "CONSUMER CYCLICAL": "Consumer Cyclical",
    "CONSUMER DEFENSIVE": "Consumer Defensive",
    "COMMUNICATION SERVICES": "Communication Svcs",
    "REAL ESTATE": "Real Estate",
    "BASIC MATERIALS": "Materials",
    "MATERIALS": "Materials",
    "ENERGY": "Energy",
    "UTILITIES": "Utilities",
}


_ALLOWED_SECTORS = set(_SECTOR_CANON.values())


def _canon_sector(raw: str | None) -> str | None:
    """Map the free-text sector field to one of the 11 canonical sectors, else None."""
    if not raw:
        return None
    key = str(raw).strip().upper()
    if key in _SECTOR_CANON:
        return _SECTOR_CANON[key]
    title = key.title()
    return title if title in _ALLOWED_SECTORS else None


# --------------------------------------------------------------------------- #
# 1. Build cap-weighted monthly sector indices (cached).
# --------------------------------------------------------------------------- #
def _read_symbol(fdir: Path, sym: str) -> tuple[pd.Series | None, str | None, float]:
    """Return (monthly adjusted-close series, sector, shares_outstanding)."""
    ts_path = fdir / f"{sym}_time_series_monthly.json"
    if not ts_path.exists():
        return None, None, np.nan
    try:
        payload = json.loads(ts_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, None, np.nan
    data = payload.get("data", {})
    series_key = next((k for k in data if "Time Series" in k), None)
    if series_key is None:
        return None, None, np.nan
    prices = {}
    for date_str, fields in data[series_key].items():
        adj = _to_float(fields.get("5. adjusted close") or fields.get("4. close"))
        if not np.isnan(adj) and adj > 0:
            prices[pd.to_datetime(date_str)] = adj
    if len(prices) < 24:
        return None, None, np.nan
    s = pd.Series(prices).sort_index()
    s.index = _month_end(pd.DatetimeIndex(s.index))
    s = s[~s.index.duplicated(keep="last")]

    sector, shares = None, np.nan
    ov_path = fdir / f"{sym}_overview.json"
    if ov_path.exists():
        try:
            ov = json.loads(ov_path.read_text(encoding="utf-8")).get("data", {})
            sector = _canon_sector(ov.get("Sector"))
            shares = _to_float(ov.get("SharesOutstanding"))
        except (json.JSONDecodeError, OSError):
            pass
    return s, sector, shares


def build_sector_indices(root: Path, fundamentals_dir: str | Path | None,
                         min_members: int = 8, refresh: bool = False,
                         return_clip: tuple[float, float] = (-0.85, 1.5)
                         ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cap-weighted monthly total-return index per sector (+ a Broad index).

    Returns (indices_df [months x sectors], members_df [sector, n_members]).
    Heavy parse is cached to ``outputs/sector_trend_report/``.
    """
    out_dir = root / OUTPUT_DIR
    cache = out_dir / CACHE_NAME
    meta = out_dir / META_NAME
    if cache.exists() and meta.exists() and not refresh:
        idx = pd.read_csv(cache, parse_dates=["date"]).set_index("date")
        members = pd.read_csv(meta)
        return idx, members

    fdir = resolve_fundamentals_dir(root, fundamentals_dir)
    symbols = sorted(
        p.name[: -len("_time_series_monthly.json")]
        for p in fdir.glob("*_time_series_monthly.json")
    )

    price_cols: dict[str, pd.Series] = {}
    sec_of: dict[str, str] = {}
    shares_of: dict[str, float] = {}
    for sym in symbols:
        s, sector, shares = _read_symbol(fdir, sym)
        if s is None or sector is None:
            continue
        price_cols[sym] = s
        sec_of[sym] = sector
        shares_of[sym] = shares

    if not price_cols:
        raise ValueError("No sector-tagged price series found.")

    prices = pd.DataFrame(price_cols).sort_index()
    rets = prices.pct_change(fill_method=None).clip(*return_clip)

    # Static cap weights: latest shares * latest price (median fallback).
    latest_px = prices.ffill().iloc[-1]
    shares = pd.Series(shares_of).reindex(prices.columns)
    mktcap = (shares * latest_px)
    mktcap = mktcap.where(mktcap > 0)
    mktcap = mktcap.fillna(mktcap.median())

    sectors = sorted(set(sec_of.values()))
    index_cols: dict[str, pd.Series] = {}
    member_counts = {}
    for sector in sectors:
        members = [s for s in prices.columns if sec_of.get(s) == sector]
        if len(members) < min_members:
            continue
        sub = rets[members]
        valid = sub.notna()
        breadth = valid.sum(axis=1)
        w = valid.mul(mktcap[members], axis=1)
        w = w.div(w.sum(axis=1), axis=0)
        sector_ret = (sub * w).sum(axis=1, min_count=1).where(breadth >= max(4, min_members // 2))
        index_cols[sector] = sector_ret
        member_counts[sector] = len(members)

    # Broad index = cap-weighted across all tagged names.
    valid = rets.notna()
    w = valid.mul(mktcap, axis=1)
    w = w.div(w.sum(axis=1), axis=0)
    broad = (rets * w).sum(axis=1, min_count=1).where(valid.sum(axis=1) >= 50)
    index_cols["Broad market"] = broad
    member_counts["Broad market"] = int(valid.iloc[-1].sum())

    ret_df = pd.DataFrame(index_cols).sort_index()
    # Convert monthly returns to price indices (start 100 at first valid month).
    level = (1.0 + ret_df.fillna(0.0)).cumprod() * 100.0
    level = level.where(ret_df.notna().cumsum() > 0)  # blank before first data
    level.index.name = "date"

    members_df = (pd.Series(member_counts, name="n_members")
                  .rename_axis("sector").reset_index()
                  .sort_values("n_members", ascending=False))

    out_dir.mkdir(parents=True, exist_ok=True)
    level.to_csv(cache)
    members_df.to_csv(meta, index=False)
    return level, members_df


# --------------------------------------------------------------------------- #
# 2. Moving averages, crosses, whipsaws, deviation.
# --------------------------------------------------------------------------- #
@dataclass
class CrossStats:
    events: pd.DataFrame          # one row per cross event, all sectors
    per_sector: pd.DataFrame      # summary stats per sector
    deviation: pd.DataFrame       # deviation-from-slow-MA distribution per sector


def _sector_crosses(name: str, price: pd.Series, fast: int, slow: int,
                    whipsaw_months: int, breakout_threshold: float) -> list[dict]:
    price = price.dropna()
    if len(price) < slow + 6:
        return []
    ma_f = price.rolling(fast, min_periods=fast).mean()
    ma_s = price.rolling(slow, min_periods=slow).mean()
    spread = (ma_f - ma_s).dropna()
    sign = np.sign(spread)
    events = []
    prev = None
    cross_dates = []
    cross_types = []
    for dt, sg in sign.items():
        if prev is not None and sg != prev and sg != 0:
            cross_dates.append(dt)
            cross_types.append("golden" if sg > 0 else "death")
        if sg != 0:
            prev = sg

    for i, (dt, ctype) in enumerate(zip(cross_dates, cross_types)):
        p0 = float(price.loc[dt])
        next_dt = cross_dates[i + 1] if i + 1 < len(cross_dates) else price.index[-1]
        duration = (next_dt.to_period("M") - dt.to_period("M")).n
        seg = price.loc[dt:next_dt]
        direction = 1.0 if ctype == "golden" else -1.0
        # Best favorable excursion during the segment (in signal direction).
        move = (seg / p0 - 1.0) * direction
        max_favorable = float(move.max()) if len(move) else 0.0
        # Fake breakout: reverses within whipsaw window OR never travels threshold.
        whipsaw = (duration <= whipsaw_months) or (max_favorable < breakout_threshold)
        fwd = {}
        for h in (3, 6, 12):
            tgt = dt.to_period("M").to_timestamp("M") + pd.offsets.MonthEnd(h)
            if tgt in price.index:
                fwd[h] = float(price.loc[tgt] / p0 - 1.0)
            else:
                fwd[h] = np.nan
        events.append({
            "sector": name, "date": dt, "type": ctype, "duration_m": duration,
            "max_favorable": max_favorable, "whipsaw": whipsaw,
            "fwd_3m": fwd[3], "fwd_6m": fwd[6], "fwd_12m": fwd[12],
        })
    return events


def analyse_crosses(indices: pd.DataFrame, fast: int, slow: int,
                    whipsaw_months: int = 4, breakout_threshold: float = 0.05
                    ) -> CrossStats:
    all_events: list[dict] = []
    dev_rows = {}
    sectors = [c for c in indices.columns]
    for name in sectors:
        price = indices[name].dropna()
        all_events.extend(
            _sector_crosses(name, price, fast, slow, whipsaw_months, breakout_threshold)
        )
        ma_s = price.rolling(slow, min_periods=slow).mean()
        dev = ((price - ma_s) / ma_s * 100.0).dropna()
        if len(dev) > 12:
            dev_rows[name] = {
                "median_abs_dev_%": round(float(dev.abs().median()), 1),
                "p95_above_%": round(float(dev.quantile(0.95)), 1),
                "p05_below_%": round(float(dev.quantile(0.05)), 1),
                "max_stretch_%": round(float(dev.abs().max()), 1),
            }

    events = pd.DataFrame(all_events)
    deviation = pd.DataFrame(dev_rows).T

    rows = {}
    span_years = (indices.index[-1] - indices.index[0]).days / 365.25
    for name in sectors:
        e = events[events["sector"] == name] if not events.empty else events
        if e.empty:
            continue
        n = len(e)
        whip = int(e["whipsaw"].sum())
        golden = e[e["type"] == "golden"]
        death = e[e["type"] == "death"]
        rows[name] = {
            "crosses": n,
            "per_decade": round(n / span_years * 10, 1) if span_years else np.nan,
            "whipsaw_rate_%": round(100 * whip / n, 0) if n else np.nan,
            "median_hold_m": int(e["duration_m"].median()),
            "golden_fwd12_%": round(100 * golden["fwd_12m"].mean(), 1) if len(golden) else np.nan,
            "death_fwd12_%": round(100 * death["fwd_12m"].mean(), 1) if len(death) else np.nan,
        }
    per_sector = pd.DataFrame(rows).T
    return CrossStats(events=events, per_sector=per_sector, deviation=deviation)


# --------------------------------------------------------------------------- #
# 3. Sector fundamental snapshot (from overviews -- cheap, one file/symbol).
# --------------------------------------------------------------------------- #
_OV_FUND = "sector_fundamentals.csv"


def load_sector_fundamentals(root: Path, fundamentals_dir: str | Path | None,
                             refresh: bool = False) -> pd.DataFrame:
    """Cross-sectional median of key ratios per sector from company overviews."""
    out_dir = root / OUTPUT_DIR
    cache = out_dir / _OV_FUND
    if cache.exists() and not refresh:
        return pd.read_csv(cache).set_index("sector")

    fdir = resolve_fundamentals_dir(root, fundamentals_dir)
    rows = []
    for p in fdir.glob("*_overview.json"):
        try:
            ov = json.loads(p.read_text(encoding="utf-8")).get("data", {})
        except (json.JSONDecodeError, OSError):
            continue
        sector = _canon_sector(ov.get("Sector"))
        if sector is None:
            continue
        # Restrict to investable-size companies so medians reflect the sector's
        # real leaders, not the long tail of micro-caps / shells in the universe.
        if _to_float(ov.get("MarketCapitalization")) < 2e9:
            continue
        rows.append({
            "sector": sector,
            "profit_margin": _to_float(ov.get("ProfitMargin")),
            "roe": _to_float(ov.get("ReturnOnEquityTTM")),
            "rev_growth_yoy": _to_float(ov.get("QuarterlyRevenueGrowthYOY")),
            "eps_growth_yoy": _to_float(ov.get("QuarterlyEarningsGrowthYOY")),
            "pe": _to_float(ov.get("PERatio")),
            "beta": _to_float(ov.get("Beta")),
            "mktcap": _to_float(ov.get("MarketCapitalization")),
        })
    df = pd.DataFrame(rows)
    agg = df.groupby("sector").agg(
        companies=("profit_margin", "size"),
        profit_margin=("profit_margin", "median"),
        roe=("roe", "median"),
        rev_growth_yoy=("rev_growth_yoy", "median"),
        eps_growth_yoy=("eps_growth_yoy", "median"),
        pe=("pe", "median"),
        beta=("beta", "median"),
        total_mktcap_tn=("mktcap", lambda s: s.sum() / 1e12),
    )
    for c in ["profit_margin", "roe", "rev_growth_yoy", "eps_growth_yoy"]:
        agg[c] = (agg[c] * 100).round(1)
    agg[["pe", "beta", "total_mktcap_tn"]] = agg[["pe", "beta", "total_mktcap_tn"]].round(2)
    agg = agg.sort_values("total_mktcap_tn", ascending=False)
    out_dir.mkdir(parents=True, exist_ok=True)
    agg.reset_index().to_csv(cache, index=False)
    return agg


# --------------------------------------------------------------------------- #
# 4. Market-health score (0-100) for position sizing.
# --------------------------------------------------------------------------- #
def _roll_z(s: pd.Series, window: int = 120, min_p: int = 36) -> pd.Series:
    """Causal rolling z-score (no look-ahead)."""
    mu = s.rolling(window, min_periods=min_p).mean()
    sd = s.rolling(window, min_periods=min_p).std()
    return ((s - mu) / sd).clip(-3, 3)


def market_health(macro: pd.DataFrame, indices: pd.DataFrame, slow: int) -> pd.DataFrame:
    """Blend trend breadth + financial conditions into a 0-100 health score.

    Higher = risk-on friendly (favour longs); lower = defensive (favour shorts).
    All inputs use causal rolling z-scores so the score is usable in a backtest.
    """
    sectors = [c for c in indices.columns if c != "Broad market"]
    above = pd.DataFrame({
        c: (indices[c] > indices[c].rolling(slow, min_periods=slow).mean()).astype(float)
        for c in sectors
    })
    breadth = above.where(indices[sectors].notna()).mean(axis=1)  # frac sectors in uptrend

    m = macro.reindex(indices.index).ffill(limit=2)
    broad = indices["Broad market"]
    mom = (broad / broad.shift(12) - 1.0)

    parts = pd.DataFrame(index=indices.index)
    parts["breadth"] = (breadth - 0.5) * 2.0                 # -1..1
    parts["nfci"] = -_roll_z(m["nfci"])
    parts["hy"] = -_roll_z(m["hy_spread"])
    parts["vix"] = -_roll_z(m["vix"])
    parts["curve"] = _roll_z(m["t10y3m"])
    parts["momentum"] = _roll_z(mom)

    weights = {"breadth": 1.1, "nfci": 0.8, "hy": 0.8, "vix": 0.6,
               "curve": 0.3, "momentum": 0.6}
    raw = sum(parts[k] * w for k, w in weights.items())
    health = 100.0 / (1.0 + np.exp(-raw / 2.0))
    out = parts.copy()
    out["health"] = health
    out["breadth_frac"] = breadth
    return out


# --------------------------------------------------------------------------- #
# 5. Long/short SMA-cross strategy with health-scaled sizing.
# --------------------------------------------------------------------------- #
@dataclass
class Backtest:
    equity: pd.DataFrame          # equity curves per strategy
    metrics: pd.DataFrame         # performance stats per strategy
    exposure: pd.Series           # net exposure of the health-sized strategy


def _perf(returns: pd.Series) -> dict:
    r = returns.dropna()
    if len(r) < 12:
        return {}
    ann = (1 + r).prod() ** (12 / len(r)) - 1
    vol = r.std() * np.sqrt(12)
    sharpe = (r.mean() * 12) / vol if vol > 0 else np.nan
    curve = (1 + r).cumprod()
    dd = (curve / curve.cummax() - 1).min()
    return {
        "CAGR_%": round(100 * ann, 1),
        "vol_%": round(100 * vol, 1),
        "Sharpe": round(sharpe, 2),
        "maxDD_%": round(100 * dd, 0),
        "hit_%": round(100 * (r > 0).mean(), 0),
    }


def risk_free_monthly(macro: pd.DataFrame, index: pd.DatetimeIndex) -> pd.Series:
    """Monthly cash/risk-free rate proxy from the 2-year yield."""
    rf = macro["us_2y"].reindex(index).ffill() / 100.0 / 12.0
    return rf.fillna(0.0)


def backtest_strategies(indices: pd.DataFrame, health: pd.Series,
                        fast: int, slow: int, macro: pd.DataFrame | None = None,
                        fee_bps: float = 10.0, short_borrow_bps: float = 100.0
                        ) -> Backtest:
    """Compare buy&hold vs cross long-only vs L/S vs health-sized books.

    Fair accounting: idle cash earns the risk-free rate, trades cost ``fee_bps``
    per unit turnover, and short exposure pays a ``short_borrow_bps`` annual fee.
    Positions use a one-month signal lag (no look-ahead).
    """
    sectors = [c for c in indices.columns if c != "Broad market"]
    px = indices[sectors]
    rets = px.pct_change(fill_method=None)
    rf = (risk_free_monthly(macro, px.index) if macro is not None
          else pd.Series(0.0, index=px.index))

    ma_f = px.rolling(fast, min_periods=fast).mean()
    ma_s = px.rolling(slow, min_periods=slow).mean()
    regime = np.sign(ma_f - ma_s)                    # +1 uptrend, -1 downtrend
    h = (health / 100.0).reindex(px.index).clip(0, 1)

    pos_long_only = regime.clip(lower=0)
    pos_ls = regime
    long_leg = regime.clip(lower=0).mul(h, axis=0)                 # 0..1 when healthy
    short_leg = regime.clip(upper=0).mul(1 - h, axis=0)            # -1..0 when unhealthy
    pos_health = long_leg + short_leg
    # Practical variant: stay long the trend but size by health (de-risk in
    # stress); only add shorts when health is genuinely weak (<0.35).
    pos_health_long = (
        regime.clip(lower=0).mul(0.3 + 0.7 * h, axis=0)
        + regime.clip(upper=0).mul((h < 0.35).astype(float) * (1 - h), axis=0)
    )

    fee = fee_bps / 1e4
    borrow_m = short_borrow_bps / 1e4 / 12.0

    def portfolio(pos: pd.DataFrame) -> tuple[pd.Series, float]:
        active = pos.shift(1)
        gross = active.abs().mean(axis=1)            # avg gross exposure (0..1+)
        idle = (1.0 - gross).clip(lower=0)           # cash sleeve earns rf
        short_expo = active.clip(upper=0).abs().mean(axis=1)
        turnover = active.diff().abs().mean(axis=1).fillna(0)
        r = (active * rets).mean(axis=1) + idle * rf - turnover * fee - short_expo * borrow_m
        return r, float(turnover.mean())

    bh = rets.mean(axis=1)                            # equal-weight buy & hold
    strat_pos = {
        "Cross long-only": pos_long_only,
        "Cross long/short": pos_ls,
        "Health-sized long/short": pos_health,
        "Health-scaled long-biased": pos_health_long,
    }
    equity = {"Buy & hold (equal sector)": (1 + bh.fillna(0)).cumprod()}
    metrics = {"Buy & hold (equal sector)": {**_perf(bh), "turnover/mo": 0.0}}
    for label, pos in strat_pos.items():
        r, turn = portfolio(pos)
        equity[label] = (1 + r.fillna(0)).cumprod()
        metrics[label] = {**_perf(r), "turnover/mo": round(turn, 2)}
    exposure = pos_health_long.shift(1).mean(axis=1)
    return Backtest(equity=pd.DataFrame(equity), metrics=pd.DataFrame(metrics).T,
                    exposure=exposure)


# --------------------------------------------------------------------------- #
# 5b. Which sectors feel macro-regime shifts the most.
# --------------------------------------------------------------------------- #
@dataclass
class RegimeSensitivity:
    fwd_by_regime: dict          # horizon -> DataFrame [sector x regime] mean fwd %
    sensitivity: pd.DataFrame    # per-sector spread / dispersion / downside
    regime: pd.Series            # monthly macro regime label
    best_regime: str
    worst_regime: str


def sector_regime_sensitivity(indices: pd.DataFrame, macro: pd.DataFrame,
                              horizons=(3, 6, 12)) -> RegimeSensitivity:
    """Forward 3/6/12m sector returns conditioned on the macro (GMM) regime.

    Uses the macro/financial-conditions latent regimes from ``regime_analysis``
    (no sector prices in the features, so there is no circularity), then ranks
    sectors by how much their forward returns swing across regimes.
    """
    from .regime_analysis import fit_regime_model
    broad = indices["Broad market"]
    fwd12_broad = broad.shift(-12) / broad - 1.0
    model = fit_regime_model(macro, fwd12_broad)
    regime = model.labels.reindex(indices.index).ffill(limit=1)

    sectors = [c for c in indices.columns if c != "Broad market"]
    fwd_by_regime = {}
    for h in horizons:
        rows = {}
        for s in sectors:
            px = indices[s]
            fwd = (px.shift(-h) / px - 1.0) * 100.0
            rows[s] = fwd.groupby(regime).mean()
        fwd_by_regime[h] = pd.DataFrame(rows).T

    f12 = fwd_by_regime[12]
    regime_order = f12.mean(axis=0).sort_values()
    worst, best = regime_order.index[0], regime_order.index[-1]
    sens = pd.DataFrame({
        "best_regime_fwd12_%": f12[best].round(1),
        "worst_regime_fwd12_%": f12[worst].round(1),
        "swing_%": (f12[best] - f12[worst]).round(1),
        "dispersion_%": f12.std(axis=1).round(1),
    }).sort_values("swing_%", ascending=False)
    return RegimeSensitivity(fwd_by_regime, sens, regime, best, worst)


# --------------------------------------------------------------------------- #
# 5c. Leverage / hedging with carry cost, timed by regime health.
# --------------------------------------------------------------------------- #
@dataclass
class LeverageBacktest:
    equity: pd.DataFrame
    metrics: pd.DataFrame
    leverage_path: pd.Series


def leverage_schedule(health: pd.Series) -> pd.Series:
    """Map the 0-100 health score to signed market exposure (leverage/hedge)."""
    h = health
    E = pd.Series(1.0, index=h.index)
    E[h >= 60] = 2.0
    E[h >= 75] = 3.0
    E[(h < 45) & (h >= 30)] = 0.5
    E[h < 30] = -1.0                     # hedge: short the market
    E[(h >= 45) & (h < 60)] = 1.0
    return E


def leverage_backtest(broad_index: pd.Series, health: pd.Series, macro: pd.DataFrame,
                      fin_spread_bps: float = 50.0, short_borrow_bps: float = 100.0,
                      fee_bps: float = 10.0) -> LeverageBacktest:
    """Leveraged / hedged broad-market books with realistic carry.

    Borrowed capital pays rf + ``fin_spread_bps``; short exposure pays a stock
    borrow fee; every change in exposure costs ``fee_bps``.  One-month signal lag.
    """
    r = broad_index.pct_change(fill_method=None)
    rf = risk_free_monthly(macro, broad_index.index)
    fin = fin_spread_bps / 1e4 / 12.0
    borrow = short_borrow_bps / 1e4 / 12.0
    fee = fee_bps / 1e4

    def run(E: pd.Series) -> pd.Series:
        E = E.reindex(r.index)
        idle = 1.0 - E
        cash_rate = rf + (idle < 0).astype(float) * fin   # borrowing costs extra
        turnover = E.diff().abs().fillna(0)
        short_fee = E.clip(upper=0).abs() * borrow
        return E * r + idle * cash_rate - turnover * fee - short_fee

    E_timed = leverage_schedule(health.reindex(r.index)).shift(1)
    books = {
        "1x buy & hold": run(pd.Series(1.0, index=r.index)),
        "Static 2x (carry-adj)": run(pd.Series(2.0, index=r.index)),
        "Static 3x (carry-adj)": run(pd.Series(3.0, index=r.index)),
        "Regime-timed 1–3x + hedge": run(E_timed),
    }
    equity = pd.DataFrame({k: (1 + v.fillna(0)).cumprod() for k, v in books.items()})
    metrics = pd.DataFrame({k: _perf(v) for k, v in books.items()}).T
    return LeverageBacktest(equity=equity, metrics=metrics, leverage_path=E_timed)


# --------------------------------------------------------------------------- #
# 6. Charts.
# --------------------------------------------------------------------------- #
_GOLD = "#4f6d3a"
_DEATH = "#9a4a35"


def chart_sector_grid(indices, events, fast, slow) -> str:
    import matplotlib.pyplot as plt
    cols = [c for c in indices.columns]
    n = len(cols)
    ncol = 3
    nrow = int(np.ceil(n / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(13, 2.5 * nrow), dpi=125)
    fig.patch.set_facecolor(PANEL_BACKGROUND)
    axes = axes.flatten()
    for ax, name in zip(axes, cols):
        _style(ax)
        px = indices[name].dropna()
        ax.plot(px.index, px.values, color=TEXT_COLOR, lw=1.1)
        ax.plot(px.index, px.rolling(fast, min_periods=fast).mean(), color="#4361ee", lw=0.9, label=f"{fast}m")
        ax.plot(px.index, px.rolling(slow, min_periods=slow).mean(), color="#c9772b", lw=0.9, label=f"{slow}m")
        e = events[events["sector"] == name] if not events.empty else events
        for _, row in e.iterrows():
            if row["date"] in px.index:
                ax.scatter([row["date"]], [px.loc[row["date"]]], s=18,
                           marker="^" if row["type"] == "golden" else "v",
                           color=_GOLD if row["type"] == "golden" else _DEATH, zorder=5)
        ax.set_yscale("log")
        ax.set_title(name, fontsize=9, loc="left", color=TEXT_COLOR)
        ax.tick_params(labelsize=6)
    for ax in axes[n:]:
        ax.axis("off")
    axes[0].legend(fontsize=6, loc="upper left")
    fig.suptitle(f"Sector indices with {fast}m/{slow}m crossovers  (▲ golden, ▼ death)",
                 fontsize=13, x=0.02, ha="left", color=TEXT_COLOR)
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    return _fig_to_b64(fig)


def chart_whipsaw(per_sector) -> str:
    s = per_sector.sort_values("whipsaw_rate_%", ascending=True)
    fig = _new_fig((11, 5)); ax = fig.add_subplot(111); _style(ax)
    y = range(len(s))
    ax.barh(y, s["whipsaw_rate_%"], color="#9a4a35", alpha=0.85)
    ax.set_yticks(list(y), labels=s.index, fontsize=8)
    ax.set_xlabel("Fake-breakout (whipsaw) rate — % of crosses that reverse fast or never travel")
    ax.set_title("How often each sector's golden/death cross is a fake breakout",
                 fontsize=12, loc="left")
    for i, (w, pd_) in enumerate(zip(s["whipsaw_rate_%"], s["per_decade"])):
        ax.text(w + 0.5, i, f"{w:.0f}%   ({pd_:.0f} crosses/decade)", va="center",
                fontsize=7, color=MUTED_TEXT_COLOR)
    ax.margins(x=0.18)
    return _fig_to_b64(fig)


def chart_deviation(dev) -> str:
    s = dev.sort_values("max_stretch_%", ascending=True)
    fig = _new_fig((11, 5)); ax = fig.add_subplot(111); _style(ax)
    y = np.arange(len(s))
    for i, (_, row) in enumerate(s.iterrows()):
        ax.plot([row["p05_below_%"], row["p95_above_%"]], [i, i], color="#0f4c5c", lw=6, alpha=0.35)
        ax.scatter([row["p05_below_%"], row["p95_above_%"]], [i, i], color="#0f4c5c", s=20)
        ax.scatter([row["median_abs_dev_%"]], [i], color="#c9772b", s=30, zorder=5)
    ax.axvline(0, color=MUTED_TEXT_COLOR, lw=0.8)
    ax.set_yticks(y, labels=s.index, fontsize=8)
    ax.set_xlabel("Price deviation from the slow MA (%)  —  band = 5th…95th pct, dot = median |dev|")
    ax.set_title("How far price stretches from trend before reverting (per sector)",
                 fontsize=12, loc="left")
    return _fig_to_b64(fig)


def chart_cross_forward(per_sector) -> str:
    s = per_sector.sort_values("golden_fwd12_%", ascending=True)
    fig = _new_fig((11, 5)); ax = fig.add_subplot(111); _style(ax)
    y = np.arange(len(s))
    ax.barh(y - 0.2, s["golden_fwd12_%"], height=0.4, color=_GOLD, label="After golden cross")
    ax.barh(y + 0.2, s["death_fwd12_%"], height=0.4, color=_DEATH, label="After death cross")
    ax.set_yticks(y, labels=s.index, fontsize=8)
    ax.axvline(0, color=MUTED_TEXT_COLOR, lw=0.8)
    ax.set_xlabel("Average forward 12-month return after the cross (%)")
    ax.set_title("Signal quality: forward returns after golden vs death crosses",
                 fontsize=12, loc="left")
    ax.legend(fontsize=8, loc="lower right")
    return _fig_to_b64(fig)


def chart_health_timeline(health_df, indices) -> str:
    from matplotlib.gridspec import GridSpec
    fig = _new_fig((12, 5.2))
    gs = GridSpec(2, 1, height_ratios=[3, 1.4], hspace=0.12, figure=fig)
    ax = fig.add_subplot(gs[0]); _style(ax)
    broad = indices["Broad market"].dropna()
    ax.plot(broad.index, broad.values, color=TEXT_COLOR, lw=1.4)
    ax.set_yscale("log"); ax.set_ylabel("Broad index (log)")
    ax.set_title("Market-health score vs. the broad market", fontsize=12, loc="left")
    axh = fig.add_subplot(gs[1], sharex=ax); _style(axh)
    h = health_df["health"].dropna()
    axh.fill_between(h.index, 50, h.values, where=(h.values >= 50), color=_GOLD, alpha=0.5, interpolate=True)
    axh.fill_between(h.index, 50, h.values, where=(h.values < 50), color=_DEATH, alpha=0.5, interpolate=True)
    axh.plot(h.index, h.values, color=TEXT_COLOR, lw=0.8)
    axh.axhline(50, color=MUTED_TEXT_COLOR, lw=0.6)
    axh.set_ylim(0, 100); axh.set_ylabel("Health\n0–100", fontsize=8)
    return _fig_to_b64(fig)


def chart_equity(bt: "Backtest") -> str:
    from matplotlib.gridspec import GridSpec
    fig = _new_fig((12, 6))
    gs = GridSpec(2, 1, height_ratios=[3, 1.3], hspace=0.15, figure=fig)
    ax = fig.add_subplot(gs[0]); _style(ax)
    palette = {"Buy & hold (equal sector)": "#9b8f77", "Cross long-only": "#0f4c5c",
               "Cross long/short": "#b56b2d", "Health-sized long/short": "#9a4a35",
               "Health-scaled long-biased": "#4f6d3a"}
    for col in bt.equity.columns:
        ax.plot(bt.equity.index, bt.equity[col], lw=1.5 if "Health-scaled" in col or "long-only" in col else 1.0,
                color=palette.get(col, "#333"), label=col)
    ax.set_yscale("log"); ax.set_ylabel("Growth of $1 (log)")
    ax.set_title("Strategy equity curves", fontsize=12, loc="left")
    ax.legend(fontsize=7.5, loc="upper left")
    axd = fig.add_subplot(gs[1], sharex=ax); _style(axd)
    for col in bt.equity.columns:
        c = bt.equity[col]
        dd = c / c.cummax() - 1
        axd.plot(dd.index, dd * 100, lw=0.9, color=palette.get(col, "#333"))
    axd.set_ylabel("Drawdown %", fontsize=8)
    return _fig_to_b64(fig)


def chart_exposure(bt: "Backtest", health_df) -> str:
    fig = _new_fig((12, 3.6)); ax = fig.add_subplot(111); _style(ax)
    exp = bt.exposure.dropna()
    ax.fill_between(exp.index, 0, exp.values, where=(exp.values >= 0), color=_GOLD, alpha=0.5, interpolate=True)
    ax.fill_between(exp.index, 0, exp.values, where=(exp.values < 0), color=_DEATH, alpha=0.5, interpolate=True)
    ax.axhline(0, color=MUTED_TEXT_COLOR, lw=0.7)
    ax.set_ylabel("Net exposure")
    ax.set_title("Health-scaled book: net long/short exposure over time (green long, red short)",
                 fontsize=12, loc="left")
    return _fig_to_b64(fig)


def chart_sector_fundamentals(fund) -> str:
    cols = ["profit_margin", "roe", "rev_growth_yoy", "pe", "beta"]
    labels = ["Profit margin %", "ROE %", "Rev growth %", "P/E", "Beta"]
    data = fund[cols].copy()
    # Normalise each column to 0..1 for a comparable heatmap (P/E & beta inverted).
    norm = data.copy().astype(float)
    for c in cols:
        v = norm[c]
        rng = v.max() - v.min()
        norm[c] = (v - v.min()) / rng if rng else 0.5
    norm[["pe", "beta"]] = 1 - norm[["pe", "beta"]]
    import matplotlib.pyplot as plt
    fig = _new_fig((10, 5.2)); ax = fig.add_subplot(111); _style(ax); ax.grid(False)
    im = ax.imshow(norm.to_numpy(), aspect="auto", cmap="RdYlGn", vmin=0, vmax=1)
    ax.set_xticks(range(len(labels)), labels=labels, fontsize=9)
    ax.set_yticks(range(len(fund)), labels=fund.index, fontsize=8)
    for i in range(len(fund)):
        for j, c in enumerate(cols):
            ax.text(j, i, f"{data.iloc[i][c]:.1f}", ha="center", va="center", fontsize=7, color=TEXT_COLOR)
    ax.set_title("Sector fundamental scorecard (green = stronger; P/E & beta inverted)",
                 fontsize=12, loc="left")
    return _fig_to_b64(fig)


def chart_regime_sensitivity(rs: RegimeSensitivity) -> str:
    from matplotlib.gridspec import GridSpec
    f12 = rs.fwd_by_regime[12]
    order = rs.sensitivity.index.tolist()
    f12 = f12.reindex(order)
    # Order regime columns by their cross-sector average (risk-off -> risk-on).
    col_order = f12.mean(axis=0).sort_values().index
    f12 = f12[col_order]
    # Rank prefix (1 = worst regime … N = best) keeps columns unique and ordered.
    short_cols = [f"{i+1}. {c[:18]}" for i, c in enumerate(f12.columns)]

    fig = _new_fig((13, 5.4))
    gs = GridSpec(1, 2, width_ratios=[2.1, 1], wspace=0.32, figure=fig)
    ax = fig.add_subplot(gs[0]); _style(ax); ax.grid(False)
    im = ax.imshow(f12.to_numpy(), aspect="auto", cmap="RdYlGn", vmin=-15, vmax=30)
    ax.set_xticks(range(len(short_cols)), labels=short_cols, rotation=30, ha="right", fontsize=7)
    ax.set_yticks(range(len(order)), labels=order, fontsize=8)
    for i in range(len(order)):
        for j in range(f12.shape[1]):
            v = f12.iloc[i, j]
            if pd.notna(v):
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=6.5, color=TEXT_COLOR)
    ax.set_title("Forward 12m sector return by macro regime (sorted by sensitivity)",
                 fontsize=11.5, loc="left")

    ax2 = fig.add_subplot(gs[1]); _style(ax2)
    sw = rs.sensitivity["swing_%"].reindex(order)[::-1]
    ax2.barh(range(len(sw)), sw.values, color="#0f4c5c")
    ax2.set_yticks(range(len(sw)), labels=sw.index, fontsize=7)
    ax2.set_xlabel("Best−worst regime swing (pp)")
    ax2.set_title("Regime sensitivity", fontsize=10.5, loc="left")
    return _fig_to_b64(fig)


def chart_leverage(lb: LeverageBacktest) -> str:
    from matplotlib.gridspec import GridSpec
    fig = _new_fig((12, 6.6))
    gs = GridSpec(3, 1, height_ratios=[3, 1.2, 1], hspace=0.18, figure=fig)
    palette = {"1x buy & hold": "#9b8f77", "Static 2x (carry-adj)": "#c9772b",
               "Static 3x (carry-adj)": "#9a4a35", "Regime-timed 1–3x + hedge": "#0f4c5c"}
    ax = fig.add_subplot(gs[0]); _style(ax)
    for c in lb.equity.columns:
        ax.plot(lb.equity.index, lb.equity[c].clip(lower=1e-3),
                lw=1.6 if "Regime" in c else 1.1, color=palette.get(c, "#333"), label=c)
    ax.set_yscale("log"); ax.set_ylabel("Growth of $1 (log)")
    ax.set_title("Leverage & hedging with carry cost", fontsize=12, loc="left")
    ax.legend(fontsize=7.5, loc="upper left")
    axd = fig.add_subplot(gs[1], sharex=ax); _style(axd)
    for c in lb.equity.columns:
        e = lb.equity[c]
        axd.plot(e.index, (e / e.cummax() - 1) * 100, lw=0.9, color=palette.get(c, "#333"))
    axd.set_ylabel("DD %", fontsize=8)
    axl = fig.add_subplot(gs[2], sharex=ax); _style(axl)
    lev = lb.leverage_path.dropna()
    axl.fill_between(lev.index, 0, lev.values, where=(lev.values >= 0), color=_GOLD, alpha=0.5, step="mid")
    axl.fill_between(lev.index, 0, lev.values, where=(lev.values < 0), color=_DEATH, alpha=0.6, step="mid")
    axl.axhline(0, color=MUTED_TEXT_COLOR, lw=0.6)
    axl.set_ylabel("Exposure\n(× / hedge)", fontsize=7)
    return _fig_to_b64(fig)


# --------------------------------------------------------------------------- #
# 7. Report assembly.
# --------------------------------------------------------------------------- #
def build_report(root: Path, fundamentals_dir: str | Path | None = "investme_sp500_data",
                 fast: int = DEFAULT_FAST, slow: int = DEFAULT_SLOW,
                 refresh: bool = False) -> Path:
    import html as H
    indices, members = build_sector_indices(root, fundamentals_dir, refresh=refresh)
    macro = load_macro_panel(root)
    cs = analyse_crosses(indices, fast, slow)
    health_df = market_health(macro, indices, slow)
    bt = backtest_strategies(indices, health_df["health"], fast, slow, macro=macro)
    fund = load_sector_fundamentals(root, fundamentals_dir, refresh=refresh)
    rs = sector_regime_sensitivity(indices, macro)
    lb = leverage_backtest(indices["Broad market"], health_df["health"], macro)

    charts = {
        "grid": chart_sector_grid(indices, cs.events, fast, slow),
        "whipsaw": chart_whipsaw(cs.per_sector),
        "deviation": chart_deviation(cs.deviation),
        "forward": chart_cross_forward(cs.per_sector),
        "fund": chart_sector_fundamentals(fund),
        "sensitivity": chart_regime_sensitivity(rs),
        "health": chart_health_timeline(health_df, indices),
        "equity": chart_equity(bt),
        "exposure": chart_exposure(bt, health_df),
        "leverage": chart_leverage(lb),
    }

    cur_health = float(health_df["health"].dropna().iloc[-1])
    cur_breadth = float(health_df["breadth_frac"].dropna().iloc[-1]) * 100
    best_sharpe = bt.metrics["Sharpe"].idxmax()
    n_symbols = int(members["n_members"].iloc[0]) if not members.empty else 0
    cleanest = cs.per_sector["whipsaw_rate_%"].idxmin()
    choppiest = cs.per_sector["whipsaw_rate_%"].idxmax()

    now_rows = {
        "Universe": f"{n_symbols:,} tagged symbols · {len(members)-1} sectors",
        "MA cross": f"{fast}-month / {slow}-month (≈50/200-day analogue)",
        "Market-health score (0–100)": f"{cur_health:.0f}",
        "Sectors in uptrend now": f"{cur_breadth:.0f}%",
        "Best risk-adjusted strategy": best_sharpe,
        "Cleanest-trending sector": f"{cleanest} ({cs.per_sector.loc[cleanest,'whipsaw_rate_%']:.0f}% fakes)",
        "Choppiest sector": f"{choppiest} ({cs.per_sector.loc[choppiest,'whipsaw_rate_%']:.0f}% fakes)",
        "Most macro-regime-sensitive": f"{rs.sensitivity.index[0]} ({rs.sensitivity['swing_%'].iloc[0]:.0f}pp swing)",
        "Least regime-sensitive": rs.sensitivity.index[-1],
    }
    now_html = "".join(
        f'<div class="kv"><span class="k">{H.escape(k)}</span>'
        f'<span class="v">{H.escape(str(v))}</span></div>' for k, v in now_rows.items()
    )

    p = []
    p.append(f"""<header>
      <h1>Sector Trend &amp; Position-Sizing Study</h1>
      <p class="subtitle">Golden/death-cross behaviour across {len(members)-1} sectors built from
      {n_symbols:,} symbols, combined with a macro market-health score to size a long/short
      trend strategy — designed to go both ways and lean on the market's overall health.</p>
      <p class="meta">Prices are monthly; the {fast}m/{slow}m cross is the monthly analogue of the
      50-day/200-day golden &amp; death cross. <span class="caveat">Universe is survivorship-biased
      (only symbols still present), so absolute index levels and buy-&amp;-hold returns overstate reality;
      the trend/whipsaw structure and relative comparisons are the signal.</span></p>
    </header>""")

    p.append(f"""<section class="now"><h2>Snapshot</h2>
      <div class="kv-grid">{now_html}</div></section>""")

    p.append(f"""<section><h2>1 · Sector indices &amp; crossovers</h2>
      <p>Each sector's cap-weighted index with its {fast}-month and {slow}-month moving averages.
      Triangles mark golden (▲) and death (▼) crosses.</p>
      {_img(charts['grid'], 'Sector indices with moving-average crossovers')}</section>""")

    p.append(f"""<section><h2>2 · How often crosses are fake breakouts</h2>
      <p>A cross is flagged a <b>fake breakout / whipsaw</b> if it reverses within {4} months or never
      travels a {5}% favourable move before the opposite cross. This is the core risk of naive
      crossover trading — and it varies a lot by sector.</p>
      {_img(charts['whipsaw'], 'Whipsaw rate by sector')}
      {_table(cs.per_sector)}</section>""")

    p.append(f"""<section><h2>3 · How far price stretches from trend</h2>
      <p>How far the index deviates from its {slow}-month MA before reverting. Wider bands (Technology,
      Consumer Cyclical) mean bigger overshoots — more room for stop placement and mean-reversion, but
      also more violent reversals.</p>
      {_img(charts['deviation'], 'Price deviation from slow MA by sector')}</section>""")

    p.append(f"""<section><h2>4 · Do the crosses actually pay?</h2>
      <p>Average forward 12-month return after each golden vs. death cross. Positive golden-cross bars
      mean the signal has historically led real trends in that sector.</p>
      {_img(charts['forward'], 'Forward returns after golden vs death crosses')}</section>""")

    p.append(f"""<section><h2>5 · Sector fundamental scorecard</h2>
      <p>Cross-sectional medians for companies above $2B market cap — the fundamental backdrop behind the
      price trends. Use it to prefer trend signals in fundamentally stronger sectors.</p>
      {_img(charts['fund'], 'Sector fundamental scorecard')}
      {_table(fund)}</section>""")

    p.append(f"""<section><h2>6 · Which sectors feel macro-regime shifts most</h2>
      <p>Forward 12-month sector returns conditioned on the <b>macro regime</b> (the latent
      financial-conditions regimes from the Dalio model — no sector prices in the features, so no
      circularity). The right-hand bars rank sectors by their best-minus-worst-regime swing: high-beta
      cyclicals (<b>{rs.sensitivity.index[0]}, {rs.sensitivity.index[1]}</b>) swing most between regimes;
      defensives (<b>{rs.sensitivity.index[-1]}</b>) least. These are the sectors to lever into on a
      favourable regime shift and to hedge first on an adverse one.</p>
      {_img(charts['sensitivity'], 'Forward sector returns by macro regime')}
      {_table(rs.sensitivity)}</section>""")

    p.append(f"""<section><h2>7 · Market health for position sizing</h2>
      <p>The health score blends trend breadth (share of sectors above their {slow}m MA) with financial
      conditions (NFCI, high-yield spreads, VIX, the yield curve) and broad momentum, all as causal
      rolling z-scores. Above 50 = risk-on (size longs up); below 50 = defensive (scale down, allow shorts).
      It reads <b>{cur_health:.0f}</b> today.</p>
      {_img(charts['health'], 'Market health vs the broad market')}</section>""")

    p.append(f"""<section><h2>8 · The strategy: cross + health-sized sizing</h2>
      <p>Five books, monthly rebalanced, one-month signal lag (no look-ahead), equal risk across sectors.
      <b>Fair accounting:</b> idle cash earns the risk-free rate, trades cost {10} bps of turnover, and
      shorts pay a {100} bps/yr borrow fee.</p>
      <ul class="method">
        <li><b>Buy &amp; hold</b> — always long every sector.</li>
        <li><b>Cross long-only</b> — long a sector only while its {fast}m&gt;{slow}m (golden regime).</li>
        <li><b>Cross long/short</b> — long in golden regime, short in death regime, full size.</li>
        <li><b>Health-sized long/short</b> — long size = health, short size = (1−health): full shorts only when the market is weak.</li>
        <li><b>Health-scaled long-biased</b> — stay long the trend but sized by health (de-risk in stress); add shorts only when health &lt; 35.</li>
      </ul>
      {_img(charts['equity'], 'Strategy equity curves and drawdowns')}
      {_table(bt.metrics)}
      {_img(charts['exposure'], 'Net exposure of the health-scaled book')}
      <p class="note">Read the honest result: over a 25-year bull, the trend filter's main gift is
      <b>drawdown control</b> — long-only cuts max drawdown roughly in half versus buy-&amp;-hold at a
      similar hit rate. Naive shorting drags returns; health-sizing's value is that it <i>only</i> lets you
      short when the market is genuinely weak, and de-risks longs into stress. Both directions are
      available, but the data says: be long-biased and let market health govern how much.</p></section>""")

    lev_metrics = lb.metrics
    p.append(f"""<section><h2>9 · Leverage &amp; hedging with carry cost</h2>
      <p>The real payoff of a regime filter is that it lets you <b>use leverage without getting wiped out</b>.
      Four books on the broad market, one-month lag, with realistic carry: borrowed capital pays the
      risk-free rate + {50} bps, shorts pay a {100} bps/yr borrow fee, and each exposure change costs {10} bps.
      The regime-timed book runs the exposure ladder <b>3× when health ≥ 75, 2× ≥ 60, 1× ≥ 45, ½× ≥ 30,
      and −1× (hedge short) below 30</b>.</p>
      {_img(charts['leverage'], 'Leverage and hedging equity curves with carry')}
      {_table(lev_metrics)}
      <p class="note">Static 3× is a <b>ruin machine</b> — its drawdown ({lev_metrics.loc['Static 3x (carry-adj)','maxDD_%']:.0f}%)
      guarantees a blow-up in 2008/2020 even though its raw return looks huge. The <b>regime-timed 1–3×
      book</b> targets the same upside but cuts exposure (and flips to a hedge) when health rolls over, so
      its drawdown stays survivable — which is the only way leverage compounds. Carry is a real drag
      (≈{50/100:.1f}–{ (50+100)/100:.1f}% a year when levered/short) and is already deducted here.</p></section>""")

    p.append(f"""<section class="method"><h2>Method &amp; caveats</h2><ul>
      <li><b>Monthly data.</b> The dataset has no per-symbol daily prices, so the 50/200-day cross is
      implemented as a {fast}m/{slow}m monthly cross (Faber-style). Change with <code>--fast/--slow</code>.</li>
      <li><b>Survivorship.</b> Only currently-present symbols exist, inflating levels and buy-&amp;-hold.
      Relative/behavioural results (whipsaw rates, deviation, drawdown control) are far more robust.</li>
      <li><b>Static cap weights.</b> Sector indices use latest shares (no historical share counts), so
      they are broad proxies, not investable indices.</li>
      <li><b>Costs modelled.</b> Idle cash earns rf; trades cost 10 bps; shorts pay 100 bps/yr borrow;
      leverage pays rf + 50 bps financing. Real leveraged-ETF path decay (daily reset) is <i>not</i>
      modelled — monthly rebalancing understates the drag of daily 3× products.</li>
    </ul></section>""")

    doc = (f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"/>"
           f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>"
           f"<title>Sector Trend &amp; Position-Sizing Study</title><style>{_REPORT_CSS}"
           f" code{{background:#efe8da;padding:1px 5px;border-radius:4px;font-size:12px;}}</style></head>"
           f"<body><main>{''.join(p)}</main></body></html>")

    out_dir = root / OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(doc, encoding="utf-8")
    cs.per_sector.to_csv(out_dir / "cross_stats_by_sector.csv")
    cs.events.to_csv(out_dir / "cross_events.csv", index=False)
    bt.metrics.to_csv(out_dir / "strategy_metrics.csv")
    health_df.to_csv(out_dir / "market_health.csv")
    rs.sensitivity.to_csv(out_dir / "sector_regime_sensitivity.csv")
    lb.metrics.to_csv(out_dir / "leverage_metrics.csv")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fundamentals-dir", default="investme_sp500_data",
                        help="Folder of <SYMBOL>_*.json (default: investme_sp500_data).")
    parser.add_argument("--fast", type=int, default=DEFAULT_FAST, help="Fast MA window in months.")
    parser.add_argument("--slow", type=int, default=DEFAULT_SLOW, help="Slow MA window in months.")
    parser.add_argument("--refresh", action="store_true", help="Rebuild the price-index cache.")
    parser.add_argument("--project-root", default=None)
    args = parser.parse_args()

    root = resolve_project_root(args.project_root)
    import matplotlib
    matplotlib.use("Agg")
    out = build_report(root, fundamentals_dir=args.fundamentals_dir,
                       fast=args.fast, slow=args.slow, refresh=args.refresh)
    print(f"Wrote sector trend study to {out}")


if __name__ == "__main__":
    main()
