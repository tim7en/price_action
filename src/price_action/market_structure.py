"""Market structure: CFTC positioning, volume-by-price, dealer gamma (live).

Three instruments with three different evidence standards, labeled accordingly:

1. **CFTC Traders-in-Financial-Futures positioning** (E-mini S&P 500) --
   leveraged funds / asset managers / dealers net positions as % of open
   interest. Weekly, free, and *backtestable*: reports are stamped Tuesday and
   published Friday ~3:30pm ET, so the study aligns each report to the
   following Monday (+6 calendar days) before touching prices -- the same
   publication-lag discipline as the macro store. ``cot_predictive_study``
   asks causally whether positioning z-scores predict forward SPY returns.

2. **Volume-by-price profile** -- SPY dollar-volume bucketed by price over a
   trailing window. High-volume nodes are prices where the market has spent
   time and found two-sided business (price tends to stick); low-volume nodes
   are air pockets (price tends to move through quickly). Descriptive map,
   not a signal -- printed as context beside the trend/ladder rules.

3. **Dealer gamma exposure (GEX)** -- naive dealer-gamma-by-strike from a
   CBOE delayed-quotes JSON. CBOE blocks non-browser clients, so this reads a
   file the user saves manually (see ``GEX_INSTRUCTIONS``). Live snapshot
   only: there is no free historical option-chain source, so GEX **cannot be
   backtested honestly here** and stays a context instrument.

Run with::

    python build_market_structure.py            # COT study + volume profile
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from .data import resolve_project_root

OUTPUT_DIR = Path("outputs") / "market_structure"
CACHE_DIR = Path("cache") / "market_structure"
COT_TFF_URL = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
COT_MARKET = "E-MINI S&P 500"
# Report stamped Tuesday, published Friday afternoon; usable the next Monday.
COT_PUBLICATION_LAG_DAYS = 6
GEX_CHAIN_FILE = Path("data") / "options" / "SPY_options.json"
GEX_INSTRUCTIONS = (
    "GEX needs a chain file CBOE won't serve to scripts: open "
    "https://cdn.cboe.com/api/global/delayed_quotes/options/SPY.json in a "
    "browser and save it to data/options/SPY_options.json, then rerun."
)


def _get_json(url: str, attempts: int = 4, timeout: int = 30):
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read())
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {attempts} attempts: {last}")


# --------------------------------------------------------------------------- #
# 1. CFTC positioning
# --------------------------------------------------------------------------- #
def fetch_cot_tff(root: Path, market: str = COT_MARKET, refresh: bool = True) -> pd.DataFrame:
    cache = root / CACHE_DIR / "cot_tff_es.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache, parse_dates=["report_date", "usable_date"]).set_index("report_date")

    fields = ",".join([
        "report_date_as_yyyy_mm_dd", "open_interest_all",
        "dealer_positions_long_all", "dealer_positions_short_all",
        "asset_mgr_positions_long", "asset_mgr_positions_short",
        "lev_money_positions_long", "lev_money_positions_short",
    ])
    where = f"contract_market_name='{market}'"
    url = (f"{COT_TFF_URL}?$select={fields}&$where={urllib.parse.quote(where)}"
           f"&$order=report_date_as_yyyy_mm_dd&$limit=5000")
    rows = _get_json(url)
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError(f"CFTC returned no rows for {market}")
    frame["report_date"] = pd.to_datetime(frame["report_date_as_yyyy_mm_dd"])
    for col in frame.columns:
        if col not in ("report_date", "report_date_as_yyyy_mm_dd"):
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.set_index("report_date").sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]

    oi = frame["open_interest_all"].replace(0.0, np.nan)
    out = pd.DataFrame(index=frame.index)
    out["lev_funds_net_pct_oi"] = (frame["lev_money_positions_long"] - frame["lev_money_positions_short"]) / oi * 100
    out["asset_mgr_net_pct_oi"] = (frame["asset_mgr_positions_long"] - frame["asset_mgr_positions_short"]) / oi * 100
    out["dealer_net_pct_oi"] = (frame["dealer_positions_long_all"] - frame["dealer_positions_short_all"]) / oi * 100
    out["open_interest"] = frame["open_interest_all"]
    # Publication-lag alignment: nothing here is knowable before the Friday
    # release; stamp each row with the first close it could have traded on.
    out["usable_date"] = out.index + pd.Timedelta(days=COT_PUBLICATION_LAG_DAYS)

    (root / CACHE_DIR).mkdir(parents=True, exist_ok=True)
    out.reset_index().to_csv(cache, index=False)
    return out


def cot_predictive_study(
    cot: pd.DataFrame,
    spy_close: pd.Series,
    z_window_weeks: int = 156,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Causal test: does release-aligned positioning predict forward returns?"""
    spy = spy_close.dropna().sort_index()
    panel = cot.copy().set_index("usable_date")
    panel = panel[~panel.index.duplicated(keep="last")]
    # Align each usable date to the first trading close at/after it.
    positions = spy.index.searchsorted(panel.index)
    valid = positions < len(spy)
    panel = panel.loc[valid]
    trade_dates = spy.index[positions[valid]]
    panel.index = trade_dates

    for group in ("lev_funds_net_pct_oi", "asset_mgr_net_pct_oi", "dealer_net_pct_oi"):
        mean = panel[group].rolling(z_window_weeks, min_periods=52).mean()
        std = panel[group].rolling(z_window_weeks, min_periods=52).std()
        panel[f"{group}_z"] = ((panel[group] - mean) / std).clip(-4, 4)

    for horizon, label in ((21, "fwd_1m"), (63, "fwd_3m")):
        px_pos = spy.index.searchsorted(panel.index)
        fwd = np.full(len(panel), np.nan)
        for i, p in enumerate(px_pos):
            if p + horizon < len(spy):
                fwd[i] = spy.iloc[p + horizon] / spy.iloc[p] - 1.0
        panel[label] = fwd

    rows = []
    for group in ("lev_funds_net_pct_oi_z", "asset_mgr_net_pct_oi_z", "dealer_net_pct_oi_z"):
        sub = panel[[group, "fwd_1m", "fwd_3m"]].dropna()
        if len(sub) < 60:
            continue
        terciles = pd.qcut(sub[group], 3, labels=["bottom", "middle", "top"])
        row = {
            "signal": group.replace("_pct_oi_z", ""),
            "weeks": len(sub),
            "ic_1m": round(float(sub[group].corr(sub["fwd_1m"], method="spearman")), 3),
            "ic_3m": round(float(sub[group].corr(sub["fwd_3m"], method="spearman")), 3),
            "fwd3m_bottom_tercile_%": round(float(sub.loc[terciles == "bottom", "fwd_3m"].mean() * 100), 2),
            "fwd3m_top_tercile_%": round(float(sub.loc[terciles == "top", "fwd_3m"].mean() * 100), 2),
            "fwd3m_z_below_-1_%": round(float(sub.loc[sub[group] < -1, "fwd_3m"].mean() * 100), 2),
            "fwd3m_z_above_+1_%": round(float(sub.loc[sub[group] > 1, "fwd_3m"].mean() * 100), 2),
            "n_extreme_low": int((sub[group] < -1).sum()),
            "n_extreme_high": int((sub[group] > 1).sum()),
        }
        rows.append(row)
    return panel, pd.DataFrame(rows).set_index("signal")


# --------------------------------------------------------------------------- #
# 2. Volume-by-price
# --------------------------------------------------------------------------- #
def fetch_spy_ohlcv(root: Path, refresh: bool = True) -> pd.DataFrame:
    cache = root / CACHE_DIR / "SPY_ohlcv.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache, parse_dates=["date"]).set_index("date")
    url = ("https://query2.finance.yahoo.com/v8/finance/chart/SPY?"
           "period1=946684800&period2=9999999999&interval=1d")
    payload = _get_json(url)
    result = payload["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    frame = pd.DataFrame({
        "close": quote["close"], "high": quote["high"],
        "low": quote["low"], "volume": quote["volume"],
    }, index=pd.to_datetime(result["timestamp"], unit="s", utc=True).tz_convert(None).normalize())
    frame = frame.dropna(subset=["close"])
    frame.index.name = "date"
    (root / CACHE_DIR).mkdir(parents=True, exist_ok=True)
    frame.to_csv(cache)
    return frame


def volume_profile(ohlcv: pd.DataFrame, lookback_days: int = 504, bins: int = 40) -> pd.DataFrame:
    """Dollar-volume by price bucket; each day's volume spread over its H-L range."""
    window = ohlcv.tail(lookback_days).dropna(subset=["volume"])
    lo, hi = float(window["low"].min()), float(window["high"].max())
    edges = np.linspace(lo, hi, bins + 1)
    weights = np.zeros(bins)
    for _, day in window.iterrows():
        day_lo, day_hi = float(day["low"]), float(day["high"])
        dollar = float(day["volume"]) * float(day["close"])
        span = max(day_hi - day_lo, 1e-9)
        for b in range(bins):
            overlap = max(0.0, min(day_hi, edges[b + 1]) - max(day_lo, edges[b]))
            weights[b] += dollar * overlap / span
    profile = pd.DataFrame({
        "price_low": edges[:-1].round(2), "price_high": edges[1:].round(2),
        "dollar_volume": weights,
    })
    profile["share_%"] = (profile["dollar_volume"] / profile["dollar_volume"].sum() * 100).round(2)
    median_share = profile["share_%"].median()
    profile["node"] = np.where(profile["share_%"] >= 1.6 * median_share, "HVN",
                       np.where(profile["share_%"] <= 0.5 * median_share, "LVN", ""))
    return profile


# --------------------------------------------------------------------------- #
# 3. Dealer gamma (live snapshot from a user-saved CBOE chain file)
# --------------------------------------------------------------------------- #
def gamma_exposure(root: Path) -> dict | None:
    path = root / GEX_CHAIN_FILE
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    data = payload.get("data", {})
    spot = float(data.get("current_price") or data.get("close") or 0.0)
    rows = []
    for opt in data.get("options", []):
        sym = opt.get("option", "")
        gamma = opt.get("gamma")
        oi = opt.get("open_interest")
        if gamma is None or not oi or len(sym) < 15 or not spot:
            continue
        # OCC symbol: root + yymmdd + C/P + strike*1000 (8 digits)
        kind = sym[-9]
        strike = int(sym[-8:]) / 1000.0
        # Naive dealer book: short customer puts (dealer long gamma), long
        # customer calls sold to dealers... standard naive GEX convention:
        # calls contribute +gamma, puts -gamma, per 1% move, notional-scaled.
        sign = 1.0 if kind == "C" else -1.0
        rows.append({"strike": strike, "gex": sign * float(gamma) * float(oi) * 100.0 * spot * spot * 0.01})
    if not rows:
        return None
    frame = pd.DataFrame(rows).groupby("strike")["gex"].sum().sort_index()
    cumulative = frame.cumsum()
    flip_candidates = cumulative[cumulative.ge(cumulative.iloc[-1] * 0.5)]
    net = float(frame.sum())
    near = frame[(frame.index > spot * 0.9) & (frame.index < spot * 1.1)]
    return {
        "spot": spot,
        "net_gex_usd_bn_per_1pct": round(net / 1e9, 2),
        "regime": "long gamma (pinning, mean-reverting)" if net > 0 else "short gamma (amplifying, fast moves)",
        "top_pin_strikes": [float(s) for s in near.abs().nlargest(3).index],
        "flip_zone_est": float(flip_candidates.index[0]) if len(flip_candidates) else None,
        "as_of_file_mtime": pd.Timestamp(path.stat().st_mtime, unit="s").strftime("%Y-%m-%d %H:%M"),
    }


# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--offline", action="store_true", help="Use cached COT/OHLCV only.")
    args = parser.parse_args()
    root = resolve_project_root(args.project_root)
    out_dir = root / OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    cot = fetch_cot_tff(root, refresh=not args.offline)
    spy = pd.read_csv(root / "cache" / "advise" / "SPY_daily.csv", parse_dates=["date"]).set_index("date")["close"].dropna()
    spy.index = spy.index.normalize()
    panel, study = cot_predictive_study(cot, spy)
    panel.to_csv(out_dir / "cot_panel.csv")
    study.to_csv(out_dir / "cot_study.csv")
    print("=== CFTC TFF positioning study (release-aligned, E-mini S&P 500) ===")
    print(study.to_string())

    try:
        ohlcv = fetch_spy_ohlcv(root, refresh=not args.offline)
        profile = volume_profile(ohlcv)
        profile.to_csv(out_dir / "volume_profile_2y.csv", index=False)
        spot = float(ohlcv["close"].iloc[-1])
        here = profile[(profile["price_low"] <= spot) & (profile["price_high"] > spot)]
        print("\n=== SPY volume-by-price, trailing 2y ===")
        print(f"spot {spot:.0f} sits in a {'/'.join(here['node'].tolist()) or 'mid'}-volume bucket")
        print(profile.loc[profile["node"] != "", ["price_low", "price_high", "share_%", "node"]].to_string(index=False))
    except Exception as exc:  # noqa: BLE001
        print(f"\nvolume profile skipped: {exc}")

    gex = gamma_exposure(root)
    print("\n=== Dealer gamma (live snapshot) ===")
    if gex is None:
        print(GEX_INSTRUCTIONS)
    else:
        print(json.dumps(gex, indent=1))

    latest = cot.iloc[-1]
    print(f"\nLatest COT ({cot.index[-1]:%Y-%m-%d}, usable {latest['usable_date']:%Y-%m-%d}): "
          f"lev funds {latest['lev_funds_net_pct_oi']:+.1f}% OI, "
          f"asset mgrs {latest['asset_mgr_net_pct_oi']:+.1f}%, dealers {latest['dealer_net_pct_oi']:+.1f}%")


if __name__ == "__main__":
    main()
