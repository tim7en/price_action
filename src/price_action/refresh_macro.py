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

import argparse
import json
import os
import time
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode

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

# Forward-looking series (created on first refresh if absent): Fed dot-plot
# medians, effective fed funds, TIPS breakevens, and leading indicators.
EXTRA_FRED_SERIES = ["DFF", "T10YIE", "T5YIFR", "MICH", "ICSA", "PERMIT",
                     "FEDTARMD", "FEDTARMDLR"]
DEFAULT_PROGRESS_FILE = Path("outputs") / "macro_refresh_progress.json"
FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _resolve_progress_file(root: Path, progress_file: str | Path | None) -> Path | None:
    if progress_file is None:
        return None
    path = Path(progress_file)
    return path if path.is_absolute() else root / path


def _read_dotenv_value(name: str) -> str | None:
    for base in [resolve_project_root(None), Path.cwd()]:
        path = base / ".env"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            if key.startswith("export "):
                key = key.removeprefix("export ").strip()
            if key == name:
                return value.strip().strip('"').strip("'")
    return None


def _fred_api_key() -> str | None:
    value = os.environ.get("FRED_API_KEY") or _read_dotenv_value("FRED_API_KEY")
    return value.strip() if value and value.strip() else None


def _redact_url(url: str) -> str:
    if "api_key=" not in url:
        return url
    head, tail = url.split("api_key=", 1)
    if "&" in tail:
        _, rest = tail.split("&", 1)
        return f"{head}api_key=<redacted>&{rest}"
    return f"{head}api_key=<redacted>"


class ProgressTracker:
    """Small JSON + terminal progress reporter for long macro refreshes."""

    def __init__(self, root: Path, progress_file: str | Path | None = DEFAULT_PROGRESS_FILE) -> None:
        self.path = _resolve_progress_file(root, progress_file)
        self.started_at = _utc_now()
        self.total_stages = 3
        self.stage_index = 0
        self.stage = "starting"
        self.total_items = 0
        self.item_index = 0
        self.done_count = 0
        self.failed_count = 0
        self.recent: list[str] = []

    def _percent(self) -> float:
        if self.total_items <= 0:
            stage_fraction = 0.0
        else:
            stage_fraction = min(max(self.item_index / self.total_items, 0.0), 1.0)
        return round(((max(self.stage_index - 1, 0) + stage_fraction) / self.total_stages) * 100.0, 1)

    def _write(self, status: str, message: str, item: str | None = None) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "status": status,
            "started_at_utc": self.started_at,
            "updated_at_utc": _utc_now(),
            "stage": self.stage,
            "stage_index": self.stage_index,
            "total_stages": self.total_stages,
            "item": item,
            "item_index": self.item_index,
            "total_items": self.total_items,
            "done_count": self.done_count,
            "failed_count": self.failed_count,
            "percent": self._percent(),
            "message": message,
            "recent": self.recent[-20:],
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def _log(self, status: str, message: str, item: str | None = None) -> None:
        prefix = f"[macro-refresh] {self._percent():5.1f}%"
        print(f"{prefix} | {self.stage} | {message}", flush=True)
        self._write(status=status, message=message, item=item)

    def start(self) -> None:
        self._log("running", "started")

    def stage_start(self, stage: str, stage_index: int, total_items: int) -> None:
        self.stage = stage
        self.stage_index = stage_index
        self.total_items = max(total_items, 0)
        self.item_index = 0
        self.done_count = 0
        self.failed_count = 0
        self._log("running", f"stage started ({self.total_items} items)")

    def fetching(self, item: str, item_index: int | None = None) -> None:
        if item_index is not None:
            self.item_index = min(max(item_index, 0), max(self.total_items, 1))
        self._log("running", f"fetching {item}", item=item)

    def ok(self, item: str, item_index: int | None = None) -> None:
        if item_index is not None:
            self.item_index = min(max(item_index, 0), max(self.total_items, 1))
        else:
            self.item_index = min(self.item_index + 1, max(self.total_items, 1))
        self.done_count += 1
        message = f"ok {item}"
        self.recent.append(message)
        self._log("running", message, item=item)

    def warn(self, item: str, item_index: int | None = None) -> None:
        if item_index is not None:
            self.item_index = min(max(item_index, 0), max(self.total_items, 1))
        else:
            self.item_index = min(self.item_index + 1, max(self.total_items, 1))
        self.failed_count += 1
        message = f"WARN {item}"
        self.recent.append(message)
        self._log("running", message, item=item)

    def pause(self, seconds: float, reason: str) -> None:
        self._log("running", f"pacing {seconds:.0f}s: {reason}")

    def stage_complete(self) -> None:
        self.item_index = self.total_items
        self._log("running", f"stage complete ({self.done_count} ok, {self.failed_count} warnings)")

    def complete(self) -> None:
        self.stage = "complete"
        self.stage_index = self.total_stages
        self.total_items = 1
        self.item_index = 1
        self._log("complete", "refresh complete")

    def fail(self, exc: BaseException) -> None:
        self._log("failed", f"refresh failed: {exc}")


def _get(url: str, timeout: int = 90, attempts: int = 3) -> bytes:
    # urllib, not curl: the sandbox/CDN path rejects curl's TLS handshake for
    # fred.stlouisfed.org (HTTP/2 INTERNAL_ERROR) while urlopen succeeds.
    # FRED throttles bursts, so retry with backoff and pace callers.
    from urllib.request import Request, urlopen
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last = RuntimeError(f"HTTP {exc.code}: {body[:500]}")
            if exc.code in {400, 401, 403, 404}:
                break
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(4.0 * (attempt + 1))
    raise RuntimeError(f"GET failed after {attempts} attempts: {_redact_url(url)}") from last


def _parse_fred_frame(frame: pd.DataFrame) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    date_col = frame.columns[0]
    idx = pd.to_datetime(frame[date_col], errors="coerce")
    for col in frame.columns[1:]:
        s = pd.Series(pd.to_numeric(frame[col], errors="coerce").to_numpy(),
                      index=idx, name=col).dropna().sort_index()
        if not s.empty:
            out[col] = s
    return out


def fetch_fred_api_series(series_id: str, api_key: str) -> pd.Series:
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": START,
        "limit": 100_000,
    }
    raw = _get(f"{FRED_API_URL}?{urlencode(params)}", timeout=60, attempts=3)
    payload = json.loads(raw.decode("utf-8"))
    if "error_code" in payload:
        raise RuntimeError(f"FRED API error for {series_id}: {payload.get('error_message')}")

    rows = payload.get("observations") or []
    values: dict[pd.Timestamp, float] = {}
    for row in rows:
        value = row.get("value")
        if value in (None, "."):
            continue
        try:
            values[pd.Timestamp(row["date"])] = float(value)
        except (KeyError, TypeError, ValueError):
            continue

    series = pd.Series(values, name=series_id, dtype="float64").sort_index()
    if series.empty:
        raise RuntimeError(f"FRED API returned no numeric observations for {series_id}")
    return series


def fetch_fred_api_batch(series_ids: list[str], api_key: str) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    for series_id in series_ids:
        out[series_id] = fetch_fred_api_series(series_id, api_key=api_key)
        time.sleep(0.2)
    return out


def fetch_fred_batch(series_ids: list[str]) -> dict[str, pd.Series]:
    """One request for many series: multi-id fredgraph returns a ZIP of CSVs
    (one per frequency group).  Sequential single requests get tarpitted by
    FRED's CDN, so batching is load-bearing here, not an optimisation."""
    api_key = _fred_api_key()
    if api_key:
        return fetch_fred_api_batch(series_ids, api_key=api_key)

    import io
    import zipfile
    raw = _get("https://fred.stlouisfed.org/graph/fredgraph.csv?id="
               + ",".join(series_ids))
    out: dict[str, pd.Series] = {}
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for name in z.namelist():
                if not name.endswith(".csv"):
                    continue
                frame = pd.read_csv(StringIO(z.read(name).decode("utf-8")))
                out.update(_parse_fred_frame(frame))
    else:
        out.update(_parse_fred_frame(pd.read_csv(StringIO(raw.decode("utf-8")))))
    missing = [sid for sid in series_ids if sid not in out]
    if missing:
        raise RuntimeError(f"FRED batch missing series: {missing}")
    return out


def fetch_fred_series(series_id: str) -> pd.Series:
    return fetch_fred_batch([series_id])[series_id]


def fetch_yahoo_series(symbol: str) -> pd.Series:
    # Direct chart call (not fetch_yahoo_chart): indices like ^FTW5000 have no
    # adjclose, which fetch_yahoo_chart's dropna would discard entirely.
    from urllib.parse import quote, urlencode
    params = urlencode({
        "period1": int(pd.Timestamp(START, tz="UTC").timestamp()),
        "period2": int((pd.Timestamp.utcnow() + pd.Timedelta(days=1)).timestamp()),
        "interval": "1d", "includePrePost": "false",
    })
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?{params}"
    payload = json.loads(_get(url))
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo returned no data for {symbol}")
    ts = result.get("timestamp") or []
    close = ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    adj = (((result.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose")
           or [None] * len(ts))
    vals = [a if a is not None else c for a, c in zip(adj, close)]
    idx = pd.to_datetime(ts, unit="s", utc=True).tz_convert(None).normalize()
    s = pd.Series(vals, index=idx, name=symbol, dtype=float).dropna()
    if s.empty:
        raise RuntimeError(f"Yahoo returned only nulls for {symbol}")
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


def refresh_fred_dir(
    root: Path,
    only: list[str] | None = None,
    progress: ProgressTracker | None = None,
) -> tuple[list[str], list[str]]:
    done, failed = [], []
    existing = {p.stem for p in (root / "fred").glob("*.csv")}
    names = sorted((existing | set(EXTRA_FRED_SERIES)) - {"UMCSENT_RELEASE_AWARE"})
    if only is not None:
        names = [n for n in names if n in only]
    if progress is not None:
        progress.stage_start("FRED directory", 1, len(names))
    for i in range(0, len(names), 10):           # batches of <=10 ids
        chunk = names[i:i + 10]
        if progress is not None:
            progress.fetching(
                f"batch {i // 10 + 1}/{max((len(names) + 9) // 10, 1)}: {', '.join(chunk)}",
                item_index=i,
            )
        try:
            series_map = fetch_fred_batch(chunk)
        except Exception as exc:  # noqa: BLE001
            for offset, n in enumerate(chunk, start=1):
                item = f"{n}: {exc}"
                failed.append(item)
                if progress is not None:
                    progress.warn(item, item_index=i + offset)
            continue
        for name in chunk:
            s = series_map[name]
            s.rename_axis("observation_date").reset_index().to_csv(
                root / "fred" / f"{name}.csv", index=False)
            item = f"{name} → {s.index[-1]:%Y-%m-%d}"
            done.append(item)
            if progress is not None:
                progress.ok(item, item_index=len(done) + len(failed))
        if i + 10 < len(names):
            if progress is not None:
                progress.pause(2.0, "FRED batch throttle")
            time.sleep(2.0)
    if progress is not None:
        progress.stage_complete()
    return done, failed


def rebuild_macro_daily(
    root: Path,
    progress: ProgressTracker | None = None,
) -> tuple[list[str], list[str]]:
    done, failed = [], []
    cols: dict[str, pd.Series] = {}
    total_items = len(YAHOO_COLS) + len(FRED_COLS) + 1
    item_index = 0
    if progress is not None:
        progress.stage_start("Combined daily macro store", 2, total_items)

    for col, sym in YAHOO_COLS.items():
        item_index += 1
        if progress is not None:
            progress.fetching(f"{col} ({sym})", item_index=item_index - 1)
        try:
            cols[col] = fetch_yahoo_series(sym)
            item = f"{col} ({sym}) → {cols[col].index[-1]:%Y-%m-%d}"
            done.append(item)
            if progress is not None:
                progress.ok(item, item_index=item_index)
        except Exception as exc:  # noqa: BLE001
            item = f"{col} ({sym}): {exc}"
            failed.append(item)
            if progress is not None:
                progress.warn(item, item_index=item_index)
    if progress is not None:
        progress.fetching(
            f"FRED batch for daily store: {', '.join(FRED_COLS.values())}",
            item_index=item_index,
        )
    try:
        fred_map = fetch_fred_batch(list(FRED_COLS.values()))
        for col, sid in FRED_COLS.items():
            item_index += 1
            cols[col] = fred_map[sid]
            item = f"{col} ({sid}) → {cols[col].index[-1]:%Y-%m-%d}"
            done.append(item)
            if progress is not None:
                progress.ok(item, item_index=item_index)
    except Exception as exc:  # noqa: BLE001
        for col, sid in FRED_COLS.items():
            item_index += 1
            item = f"{col} ({sid}): {exc}"
            failed.append(item)
            if progress is not None:
                progress.warn(item, item_index=item_index)

    item_index += 1
    if progress is not None:
        progress.fetching("shiller_cape_ratio (Multpl)", item_index=item_index - 1)
    try:
        cols["shiller_cape_ratio"] = fetch_multpl_cape()
        item = f"shiller_cape_ratio (Multpl) → {cols['shiller_cape_ratio'].index[-1]:%Y-%m-%d}"
        done.append(item)
        if progress is not None:
            progress.ok(item, item_index=item_index)
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
            item = (f"shiller_cape_ratio: Multpl failed ({exc}); "
                    f"extended {len(ext)} months by Wilshire price proxy")
            failed.append(item)
            if progress is not None:
                progress.warn(item, item_index=item_index)
        else:
            item = f"shiller_cape_ratio: {exc}"
            failed.append(item)
            if progress is not None:
                progress.warn(item, item_index=item_index)

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
    if progress is not None:
        progress.stage_complete()
    return done, failed


def _print_progress_status(root: Path, progress_file: str | Path | None) -> None:
    path = _resolve_progress_file(root, progress_file)
    if path is None or not path.exists():
        print(f"No progress file found at {path or '<disabled>'}.")
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    percent = payload.get("percent")
    try:
        percent_text = f"{float(percent):.1f}%"
    except (TypeError, ValueError):
        percent_text = "n/a"
    print(
        f"{payload.get('status', 'unknown')} | "
        f"{percent_text} | "
        f"{payload.get('stage', 'unknown')} "
        f"({payload.get('stage_index', 0)}/{payload.get('total_stages', 0)}) | "
        f"item {payload.get('item_index', 0)}/{payload.get('total_items', 0)}"
    )
    print(f"updated: {payload.get('updated_at_utc')}")
    print(f"message: {payload.get('message')}")
    print(f"done={payload.get('done_count', 0)} failed={payload.get('failed_count', 0)}")
    recent = payload.get("recent") or []
    if recent:
        print("recent:")
        for line in recent[-8:]:
            print(f"  {line}")
    print(f"path: {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=None)
    parser.add_argument(
        "--progress-file",
        default=str(DEFAULT_PROGRESS_FILE),
        help="JSON progress file, relative to project root unless absolute.",
    )
    parser.add_argument(
        "--no-progress-file",
        action="store_true",
        help="Print progress to the terminal but do not write a JSON progress file.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Read and print the current progress file, then exit.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    root = resolve_project_root(args.project_root)
    progress_file = None if args.no_progress_file else args.progress_file

    if args.status:
        _print_progress_status(root, progress_file)
        return

    tracker = ProgressTracker(root=root, progress_file=progress_file)
    tracker.start()
    try:
        done, failed = refresh_fred_dir(root, progress=tracker)
        print(f"— FRED directory summary: {len(done)} ok, {len(failed)} failed —", flush=True)

        done, failed = rebuild_macro_daily(root, progress=tracker)
        print(f"— Combined daily macro store summary: {len(done)} ok, {len(failed)} warnings —", flush=True)

        tracker.stage_start("Derived feature store", 3, 1)
        tracker.fetching("write_macro_feature_store", item_index=0)
        from .macro_features import write_macro_feature_store
        feature_store = write_macro_feature_store(project_root=root)
        tracker.ok(f"rebuilt {feature_store}", item_index=1)
        tracker.stage_complete()
        tracker.complete()
        print(f"Progress file: {_resolve_progress_file(root, progress_file) or '<disabled>'}", flush=True)
    except Exception as exc:  # noqa: BLE001
        tracker.fail(exc)
        raise


if __name__ == "__main__":
    main()
