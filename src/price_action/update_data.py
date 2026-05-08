from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from .data import discover_symbols, resolve_project_root
from .macro_features import write_macro_feature_store
from .universe import DEFAULT_PANEL_SYMBOLS, expand_symbol_selection


def fetch_yahoo_chart(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    start_ts = int(pd.Timestamp(start_date, tz="UTC").timestamp())
    end_ts = int(pd.Timestamp(end_date, tz="UTC").timestamp())
    params = urlencode(
        {
            "period1": start_ts,
            "period2": end_ts,
            "interval": "1d",
            "includePrePost": "false",
            "events": "div,splits",
        }
    )
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?{params}"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        error = (payload.get("chart") or {}).get("error")
        raise RuntimeError(f"Yahoo returned no data for {symbol}: {error}")

    result_item = result[0]
    timestamps = result_item.get("timestamp") or []
    quote = ((result_item.get("indicators") or {}).get("quote") or [{}])[0]
    adj_close_values = ((result_item.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose")

    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "close": quote.get("close"),
            "volume": quote.get("volume"),
            "adj_close": adj_close_values,
        }
    )
    frame = frame.dropna(subset=["timestamp", "close", "adj_close"]).copy()
    frame["date"] = pd.to_datetime(frame["timestamp"], unit="s", utc=True).dt.tz_convert(None)

    adjustment_ratio = frame["adj_close"] / frame["close"].replace(0.0, pd.NA)
    frame["adj_open"] = frame["open"] * adjustment_ratio
    frame["adj_high"] = frame["high"] * adjustment_ratio
    frame["adj_low"] = frame["low"] * adjustment_ratio
    frame["adj_volume"] = frame["volume"] / adjustment_ratio.replace(0.0, pd.NA)
    frame = frame.drop(columns=["timestamp"])
    return frame.sort_values("date").reset_index(drop=True)


def compute_asset_feature_frame(price_frame: pd.DataFrame) -> pd.DataFrame:
    frame = price_frame.copy()
    frame["close_feature"] = frame["adj_close"]
    frame["sma"] = frame["adj_close"].rolling(window=20, min_periods=20).mean()

    previous_close = frame["adj_close"].shift(1)
    true_range = pd.concat(
        [
            frame["adj_high"] - frame["adj_low"],
            (frame["adj_high"] - previous_close).abs(),
            (frame["adj_low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    frame["atr"] = true_range.rolling(window=14, min_periods=14).mean()
    frame = frame.dropna(subset=["close_feature", "sma", "atr"]).copy()
    return frame


def build_asset_payload(feature_frame: pd.DataFrame) -> dict[str, dict[str, dict[str, float]]]:
    payload: dict[str, dict[str, dict[str, float]]] = {"close": {}, "sma": {}, "atr": {}}
    for row in feature_frame.itertuples(index=False):
        date_key = row.date.strftime("%Y-%m-%d")
        close_value = float(row.close_feature)
        payload["close"][date_key] = {"close": close_value}
        payload["sma"][date_key] = {"sma": float(row.sma), "close": close_value}
        payload["atr"][date_key] = {"atr": float(row.atr), "close": close_value}
    return payload


def refresh_asset_cache(
    symbol: str,
    start_date: str,
    end_date: str,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    price_frame = fetch_yahoo_chart(symbol=symbol, start_date=start_date, end_date=end_date)
    feature_frame = compute_asset_feature_frame(price_frame)
    payload = build_asset_payload(feature_frame)

    cache_dir = root / "cache" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload_path = cache_dir / f"{symbol.upper()}_daily.json"
    metadata_path = cache_dir / f"{symbol.upper()}_daily_metadata.json"

    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    metadata = {
        "downloaded_at_utc": datetime.now(UTC).isoformat(),
        "ticker": symbol.upper(),
        "source": "Yahoo Finance chart API",
        "source_url": f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol.upper()}",
        "start": start_date,
        "end": end_date,
        "rows": int(feature_frame.shape[0]),
        "first_date": feature_frame["date"].min().strftime("%Y-%m-%d") if not feature_frame.empty else None,
        "last_date": feature_frame["date"].max().strftime("%Y-%m-%d") if not feature_frame.empty else None,
        "feature_windows": {"sma": 20, "atr": 14},
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def run_refresh(
    symbols: list[str],
    start_date: str,
    end_date: str,
    build_macro_store: bool,
    project_root: str | Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    refreshed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for symbol in symbols:
        try:
            refreshed.append(
                refresh_asset_cache(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    project_root=project_root,
                )
            )
        except Exception as exc:  # noqa: BLE001
            failed.append({"ticker": symbol, "error": str(exc)})
        time.sleep(0.5)

    if build_macro_store:
        write_macro_feature_store(project_root=project_root)

    return {"refreshed": refreshed, "failed": failed}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh cached price history and rebuild macro inventory.")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["AMZN"],
        help="Symbols to refresh from Yahoo Finance chart API. Use PANEL to expand to the default panel universe.",
    )
    parser.add_argument(
        "--default-panel",
        action="store_true",
        help="Refresh the default panel universe defined in the repo.",
    )
    parser.add_argument(
        "--start-date",
        default="2000-01-01",
        help="Inclusive history start date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--end-date",
        default=pd.Timestamp.utcnow().strftime("%Y-%m-%d"),
        help="Inclusive history end date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--build-macro-store",
        action="store_true",
        help="Rebuild the per-feature macro store after refreshing assets.",
    )
    parser.add_argument(
        "--list-current-symbols",
        action="store_true",
        help="Print the currently discovered cached symbols and exit.",
    )
    parser.add_argument(
        "--list-default-panel",
        action="store_true",
        help="Print the default panel universe and exit.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.list_current_symbols:
        print("\n".join(discover_symbols()))
        return

    if args.list_default_panel:
        print("\n".join(DEFAULT_PANEL_SYMBOLS))
        return

    raw_symbols = list(args.symbols)
    if args.default_panel:
        raw_symbols.extend(DEFAULT_PANEL_SYMBOLS)

    summaries = run_refresh(
        symbols=expand_symbol_selection(raw_symbols),
        start_date=args.start_date,
        end_date=args.end_date,
        build_macro_store=args.build_macro_store,
    )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()