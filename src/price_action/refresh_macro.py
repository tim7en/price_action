"""Refresh the raw macro data stores (the piece ``refresh_data.py`` lacked).

Rebuilds, from origin sources:

* ``fred/<SERIES>.csv``       -- every standalone FRED series, via the public
                                 fredgraph CSV endpoint (no API key).
* ``cache/macro_daily_1999.csv`` -- the combined daily store: Yahoo tickers
                                 (DXY, gold, copper, Wilshire, VIX3M, sector
                                 ETFs), FRED series (yields, WTI, GDP, CPI,
                                 unemployment, mktcap/GDP), and the Shiller
                                 CAPE from multpl.com (falls back to a
                                 price-scaled proxy of the last known CAPE if
                                 the scrape fails -- flagged in the output).

Afterwards it rebuilds the derived macro feature store
(``write_macro_feature_store``), so every downstream report sees fresh data.

Run with::

    python refresh_macro.py
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

from .data import resolve_project_root

YAHOO_COLS = {
    "dxy_close": "DX-Y.NYB",
    "gold_usd_per_oz": "GC=F",
    "wilshire_total_market_index": "^FTW5000",
    "xlu_close": "XLU",
    "xly_close": "XLY",
    "eem_close": "EEM",
    "efa_close": "EFA",
    "copper_usd_per_lb": "HG=F",
    "vix3m_level": "^VIX3M",
}
FRED_COLS = {
    "us_2y_yield": "DGS2",
    "us_10y_yield": "DGS10",
    "us_30y_yield": "DGS30",
    "wti_usd_per_bbl": "DCOILWTICO",
    "us_nominal_gdp_saar_bil": "GDP",
    "cpi_all_items_index": "CPIAUCSL",
    "unemployment_rate_pct": "UNRATE",
    "market_cap_to_gdp_pct": "DDDM01USA156NWDB",
}
COLUMN_ORDER = [
    "dxy_close", "gold_usd_per_oz", "wilshire_total_market_index",
    "shiller_cape_ratio", "us_2y_yield", "us_10y_yield", "us_30y_yield",
    "wti_usd_per_bbl", "us_nominal_gdp_saar_bil", "cpi_all_items_index",
    "cpi_mom_pct", "cpi_yoy_pct", "unemployment_rate_pct",
    "market_cap_to_gdp_pct", "xlu_close", "xly_close", "eem_close",
    "efa_close", "copper_usd_per_lb", "vix3m_level",
]
START = "1999-01-01"
MULTPL_URL = "https://www.multpl.com/shiller-pe/table/by-month"


def _get(url: str, timeout: int = 45) -> bytes:
    # urllib, not curl: the sandbox/CDN path rejects curl's TLS handshake for
    # fred.stlouisfed.org (HTTP/2 INTERNAL_ERROR) while urlopen succeeds.
    from urllib.request import Request, urlopen
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_fred_series(series_id: str) -> pd.Series:
    raw = _get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}")
    frame = pd.read_csv(StringIO(raw.decode("utf-8")))
    date_col, val_col = frame.columns[0], frame.columns[1]
    s = pd.Series(
        pd.to_numeric(frame[val_col], errors="coerce").to_numpy(),
        index=pd.to_datetime(frame[date_col], errors="coerce"),
        name=series_id,
    ).dropna().sort_index()
    if s.empty:
        raise RuntimeError(f"FRED returned no rows for {series_id}")
    return s


def fetch_yahoo_series(symbol: str) -> pd.Series:
    from .update_data import fetch_yahoo_chart
    end = (pd.Timestamp.utcnow() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    frame = fetch_yahoo_chart(symbol, START, end)
    s = pd.Series(frame["close"].to_numpy(),
                  index=pd.DatetimeIndex(frame["date"]).normalize(), name=symbol)
    return s[~s.index.duplicated(keep="last")].sort_index()


def fetch_multpl_cape() -> pd.Series:
    import re
    html = _get(MULTPL_URL).decode("utf-8", errors="replace")
    rows = re.findall(
        r"<td>([A-Z][a-z]{2} \d{1,2}, \d{4})</td>\s*<td>\s*(?:&#x2002;)?\s*([\d.]+)",
        html)
    if len(rows) < 100:
        raise RuntimeError(f"Multpl parse found only {len(rows)} rows")
    s = pd.Series({pd.to_datetime(d): float(v) for d, v in rows}).sort_index()
    return s[s.index >= START]


def refresh_fred_dir(root: Path) -> tuple[list[str], list[str]]:
    done, failed = [], []
    for path in sorted((root / "fred").glob("*.csv")):
        name = path.stem
        if name == "UMCSENT_RELEASE_AWARE":     # ALFRED cache, own updater
            continue
        try:
            s = fetch_fred_series(name)
            s.rename_axis("observation_date").reset_index().to_csv(path, index=False)
            done.append(f"{name} → {s.index[-1]:%Y-%m-%d}")
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{name}: {exc}")
    return done, failed


def rebuild_macro_daily(root: Path) -> tuple[list[str], list[str]]:
    done, failed = [], []
    cols: dict[str, pd.Series] = {}

    for col, sym in YAHOO_COLS.items():
        try:
            cols[col] = fetch_yahoo_series(sym)
            done.append(f"{col} ({sym}) → {cols[col].index[-1]:%Y-%m-%d}")
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{col} ({sym}): {exc}")
    for col, sid in FRED_COLS.items():
        try:
            cols[col] = fetch_fred_series(sid)
            done.append(f"{col} ({sid}) → {cols[col].index[-1]:%Y-%m-%d}")
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{col} ({sid}): {exc}")

    try:
        cols["shiller_cape_ratio"] = fetch_multpl_cape()
        done.append(f"shiller_cape_ratio (Multpl) → {cols['shiller_cape_ratio'].index[-1]:%Y-%m-%d}")
    except Exception as exc:  # noqa: BLE001
        # Proxy: extend the last known CAPE by the Wilshire price ratio
        # (earnings move slowly; flagged so nobody mistakes it for the real thing).
        old = pd.read_csv(root / "cache" / "macro_daily_1999.csv",
                          parse_dates=["date"]).set_index("date")
        cape_old = old["shiller_cape_ratio"].dropna()
        wil = cols.get("wilshire_total_market_index")
        if wil is not None and not cape_old.empty:
            anchor_date, anchor = cape_old.index[-1], float(cape_old.iloc[-1])
            wil_m = wil.astype(float).resample("MS").first()
            base = wil_m.reindex([anchor_date], method="nearest").iloc[0]
            ext = (wil_m[wil_m.index > anchor_date] / base * anchor).round(2)
            cols["shiller_cape_ratio"] = pd.concat([cape_old, ext])
            failed.append(f"shiller_cape_ratio: Multpl failed ({exc}); "
                          f"extended {len(ext)} months by Wilshire price proxy")
        else:
            failed.append(f"shiller_cape_ratio: {exc}")

    missing = [c for c in COLUMN_ORDER if c not in cols
               and c not in ("cpi_mom_pct", "cpi_yoy_pct")]
    if "wilshire_total_market_index" not in cols or "cpi_all_items_index" not in cols:
        raise RuntimeError(f"Core series failed, aborting rebuild: {failed}")

    frame = pd.DataFrame(cols).sort_index()
    frame = frame[frame.index >= pd.Timestamp(START)]
    cpi = frame["cpi_all_items_index"].dropna()
    frame["cpi_mom_pct"] = (cpi / cpi.shift(1) - 1.0).mul(100).reindex(frame.index)
    frame["cpi_yoy_pct"] = (cpi / cpi.shift(12) - 1.0).mul(100).reindex(frame.index)
    for c in missing:
        frame[c] = np.nan
    frame = frame[COLUMN_ORDER]
    frame.index.name = "date"

    out = root / "cache" / "macro_daily_1999.csv"
    frame.to_csv(out)

    meta_path = root / "cache" / "macro_daily_1999_metadata.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["downloaded_at_utc"] = datetime.now(UTC).isoformat()
        meta["end"] = f"{frame.index[-1]:%Y-%m-%d}"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return done, failed


def main() -> None:
    root = resolve_project_root(None)
    print("— FRED directory —")
    done, failed = refresh_fred_dir(root)
    for line in done:
        print(f"  ok  {line}")
    for line in failed:
        print(f"  FAIL {line}")

    print("— Combined daily macro store —")
    done, failed = rebuild_macro_daily(root)
    for line in done:
        print(f"  ok  {line}")
    for line in failed:
        print(f"  WARN {line}")

    print("— Derived feature store —")
    from .macro_features import write_macro_feature_store
    print(f"  rebuilt: {write_macro_feature_store(project_root=root)}")


if __name__ == "__main__":
    main()
