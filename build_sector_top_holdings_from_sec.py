from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from price_action.data import load_asset_daily  # noqa: E402
from price_action.update_data import refresh_asset_cache  # noqa: E402


SEC_CIK = "0001064641"
SEC_ARCHIVE_CIK = str(int(SEC_CIK))
SEC_SUBMISSIONS_URL = f"https://data.sec.gov/submissions/CIK{SEC_CIK}.json"
SEC_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data"
YAHOO_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"
USER_AGENT = "price-action research contact@example.com"

REPORT_DIR = PROJECT_ROOT / "outputs" / "sector_rotation_report"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "sector_top_holdings.csv"
DEFAULT_XML_CACHE_DIR = PROJECT_ROOT / "cache" / "sec_nport"
DEFAULT_SYMBOL_MAP_PATH = PROJECT_ROOT / "cache" / "sec_identifier_symbol_map.json"
GAP_COLUMNS = [
    "as_of_date",
    "known_from_date",
    "sector_symbol",
    "holding_name",
    "cusip",
    "isin",
    "weight",
    "val_usd",
    "source",
    "missing_reason",
]

SERIES_NAME_TO_SYMBOL = {
    "The Communication Services Select Sector SPDR Fund": "XLC",
    "The Consumer Discretionary Select Sector SPDR Fund": "XLY",
    "The Consumer Staples Select Sector SPDR Fund": "XLP",
    "The Energy Select Sector SPDR Fund": "XLE",
    "The Financial Select Sector SPDR Fund": "XLF",
    "The Health Care Select Sector SPDR Fund": "XLV",
    "The Industrial Select Sector SPDR Fund": "XLI",
    "The Materials Select Sector SPDR Fund": "XLB",
    "The Real Estate Select Sector SPDR Fund": "XLRE",
    "The Technology Select Sector SPDR Fund": "XLK",
    "The Utilities Select Sector SPDR Fund": "XLU",
}

SERIES_ID_TO_SYMBOL = {
    "S000006408": "XLY",
    "S000006409": "XLP",
    "S000006410": "XLE",
    "S000006411": "XLF",
    "S000006412": "XLV",
    "S000006413": "XLI",
    "S000006414": "XLB",
    "S000006415": "XLK",
    "S000006416": "XLU",
    "S000051152": "XLRE",
    "S000062095": "XLC",
}

SYMBOL_OVERRIDES_BY_IDENTIFIER = {
    "00507V109": "ATVI",
    "US00507V1098": "ATVI",
    "723787107": "PXD",
    "US7237871071": "PXD",
    "755111507": "RTN",
    "US7551115071": "RTN",
    "913017109": "UTX",
    "US9130171096": "UTX",
}

SYMBOL_OVERRIDES_BY_NAME = {
    "ACTIVISION BLIZZARD INC": "ATVI",
    "PIONEER NATURAL RESOURCES CO": "PXD",
    "RAYTHEON CO": "RTN",
    "UNITED TECHNOLOGIES CORP": "UTX",
}


@dataclass(frozen=True)
class Filing:
    accession: str
    filing_date: str
    report_date: str
    acceptance_datetime: str
    primary_document: str

    @property
    def archive_url(self) -> str:
        accession_path = self.accession.replace("-", "")
        return f"{SEC_ARCHIVE_URL}/{SEC_ARCHIVE_CIK}/{accession_path}/{self.raw_document_name}"

    @property
    def raw_document_name(self) -> str:
        return Path(self.primary_document).name


def _read_url_bytes(url: str, accept: str = "application/json", timeout: int = 60) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build point-in-time top sector holdings from public SEC N-PORT filings."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--xml-cache-dir", type=Path, default=DEFAULT_XML_CACHE_DIR)
    parser.add_argument("--symbol-map", type=Path, default=DEFAULT_SYMBOL_MAP_PATH)
    parser.add_argument("--start-report-date", default="2019-09-30")
    parser.add_argument("--end-report-date", default=pd.Timestamp.utcnow().strftime("%Y-%m-%d"))
    parser.add_argument("--max-holdings-per-sector", type=int, default=10)
    parser.add_argument("--known-lag-days", type=int, default=1)
    parser.add_argument("--sec-sleep", type=float, default=0.12)
    parser.add_argument("--yahoo-sleep", type=float, default=0.05)
    parser.add_argument("--refresh-prices", action="store_true")
    parser.add_argument("--price-start-date", default="1999-01-01")
    parser.add_argument("--price-end-date", default=pd.Timestamp.utcnow().strftime("%Y-%m-%d"))
    parser.add_argument(
        "--sectors",
        nargs="+",
        default=sorted(SERIES_NAME_TO_SYMBOL.values()),
        help="Sector ETF symbols to include.",
    )
    return parser.parse_args()


def _load_symbol_map(path: Path) -> dict[str, str | None]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(key): value for key, value in payload.items()}


def _write_symbol_map(path: Path, symbol_map: dict[str, str | None]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(symbol_map, indent=2, sort_keys=True), encoding="utf-8")


def _load_filings(start_report_date: pd.Timestamp, end_report_date: pd.Timestamp) -> list[Filing]:
    payload = json.loads(_read_url_bytes(SEC_SUBMISSIONS_URL).decode("utf-8"))
    recent = payload["filings"]["recent"]
    filings: list[Filing] = []
    for accession, filing_date, report_date, acceptance_datetime, form, primary_document in zip(
        recent["accessionNumber"],
        recent["filingDate"],
        recent["reportDate"],
        recent["acceptanceDateTime"],
        recent["form"],
        recent["primaryDocument"],
        strict=True,
    ):
        if form != "NPORT-P":
            continue
        report_timestamp = pd.Timestamp(report_date)
        if report_timestamp < start_report_date or report_timestamp > end_report_date:
            continue
        filings.append(
            Filing(
                accession=str(accession),
                filing_date=str(filing_date),
                report_date=str(report_date),
                acceptance_datetime=str(acceptance_datetime),
                primary_document=str(primary_document),
            )
        )
    return filings


def _filing_xml_path(cache_dir: Path, filing: Filing) -> Path:
    return cache_dir / filing.accession / filing.raw_document_name


def _load_filing_xml(cache_dir: Path, filing: Filing, sleep_seconds: float) -> bytes:
    path = _filing_xml_path(cache_dir, filing)
    if path.exists():
        return path.read_bytes()
    payload = _read_url_bytes(filing.archive_url, accept="application/xml")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    time.sleep(sleep_seconds)
    return payload


def _text(node: ET.Element | None, tag: str) -> str | None:
    if node is None:
        return None
    child = node.find(f"{{*}}{tag}")
    return child.text.strip() if child is not None and child.text else None


def _float_or_none(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _accepted_known_date(acceptance_datetime: str, lag_days: int) -> str:
    accepted = datetime.fromisoformat(acceptance_datetime.replace("Z", "+00:00")).astimezone(UTC)
    return (accepted.date() + timedelta(days=lag_days)).isoformat()


def _find_isin(investment: ET.Element) -> str | None:
    isin = investment.find(".//{*}isin")
    if isin is None:
        return None
    raw_value = isin.attrib.get("value")
    return raw_value.strip().upper() if raw_value else None


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace(".", "-")


def _yahoo_lookup_symbol(
    query: str,
    symbol_map: dict[str, str | None],
    sleep_seconds: float,
) -> str | None:
    cache_key = f"yahoo:{query.upper()}"
    if cache_key in symbol_map:
        return symbol_map[cache_key]

    params = urlencode({"q": query, "quotesCount": 8, "newsCount": 0})
    url = f"{YAHOO_SEARCH_URL}?{params}"
    try:
        payload = json.loads(_read_url_bytes(url, accept="application/json").decode("utf-8"))
    except Exception:  # noqa: BLE001
        symbol_map[cache_key] = None
        return None
    finally:
        time.sleep(sleep_seconds)

    symbol: str | None = None
    for quote in payload.get("quotes", []):
        if str(quote.get("quoteType", "")).upper() != "EQUITY":
            continue
        exchange = str(quote.get("exchange", "")).upper()
        if exchange not in {"NYQ", "NMS", "NCM", "ASE", "NGM", "PCX"}:
            continue
        raw_symbol = quote.get("symbol")
        if raw_symbol:
            symbol = _normalize_symbol(str(raw_symbol))
            break

    symbol_map[cache_key] = symbol
    return symbol


def _resolve_symbol(
    name: str,
    cusip: str | None,
    isin: str | None,
    symbol_map: dict[str, str | None],
    sleep_seconds: float,
) -> str | None:
    for identifier in (isin, cusip):
        if identifier:
            override = SYMBOL_OVERRIDES_BY_IDENTIFIER.get(identifier.upper())
            if override:
                return override
    name_override = SYMBOL_OVERRIDES_BY_NAME.get(name.upper())
    if name_override:
        return name_override

    for query in (isin, cusip, name):
        if query:
            symbol = _yahoo_lookup_symbol(query, symbol_map=symbol_map, sleep_seconds=sleep_seconds)
            if symbol:
                return symbol
    return None


def _parse_filing(
    filing: Filing,
    xml_bytes: bytes,
    sectors: set[str],
    max_holdings_per_sector: int,
    known_lag_days: int,
    symbol_map: dict[str, str | None],
    yahoo_sleep: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    root = ET.fromstring(xml_bytes)
    gen_info = root.find(".//{*}genInfo")
    series_name = _text(gen_info, "seriesName")
    series_id = _text(gen_info, "seriesId")
    sector_symbol = SERIES_ID_TO_SYMBOL.get(series_id or "") or SERIES_NAME_TO_SYMBOL.get(series_name or "")
    if sector_symbol is None or sector_symbol not in sectors:
        return [], []

    as_of_date = _text(gen_info, "repPdDate") or filing.report_date
    known_from_date = _accepted_known_date(filing.acceptance_datetime, lag_days=known_lag_days)

    candidates: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for investment in root.findall(".//{*}invstOrSec"):
        asset_category = _text(investment, "assetCat")
        payoff_profile = _text(investment, "payoffProfile")
        if asset_category != "EC" or payoff_profile != "Long":
            continue

        name = _text(investment, "name") or _text(investment, "title")
        if not name:
            continue

        pct_val = _float_or_none(_text(investment, "pctVal"))
        val_usd = _float_or_none(_text(investment, "valUSD"))
        if pct_val is None or pct_val <= 0.0 or val_usd is None or val_usd <= 0.0:
            continue

        cusip = _text(investment, "cusip")
        isin = _find_isin(investment)
        candidates.append(
            {
                "as_of_date": as_of_date,
                "known_from_date": known_from_date,
                "sector_symbol": sector_symbol,
                "holding_name": name,
                "cusip": cusip,
                "isin": isin,
                "weight": pct_val / 100.0,
                "val_usd": val_usd,
                "source": (
                    f"sec_nport:{filing.accession}:{filing.raw_document_name}:"
                    f"accepted={filing.acceptance_datetime}"
                ),
            }
        )

    rows: list[dict[str, Any]] = []
    for row in sorted(candidates, key=lambda item: float(item["weight"]), reverse=True)[:max_holdings_per_sector]:
        symbol = _resolve_symbol(
            name=str(row["holding_name"]),
            cusip=str(row["cusip"]) if row["cusip"] else None,
            isin=str(row["isin"]) if row["isin"] else None,
            symbol_map=symbol_map,
            sleep_seconds=yahoo_sleep,
        )
        if symbol is None:
            gaps.append({**row, "missing_reason": "Could not map CUSIP/ISIN/name to Yahoo symbol"})
            continue
        rows.append({"holding_symbol": symbol, **row})
    return rows, gaps


def _write_outputs(rows: list[dict[str, Any]], gaps: list[dict[str, Any]], output_path: Path) -> pd.DataFrame:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError("No sector holdings were parsed from SEC N-PORT filings.")

    frame["as_of_date"] = pd.to_datetime(frame["as_of_date"])
    frame["known_from_date"] = pd.to_datetime(frame["known_from_date"])
    frame = frame.sort_values(
        ["sector_symbol", "as_of_date", "known_from_date", "weight"],
        ascending=[True, True, True, False],
    )
    frame = frame.drop_duplicates(
        subset=["sector_symbol", "as_of_date", "holding_symbol"],
        keep="last",
    )
    frame.to_csv(output_path, index=False, date_format="%Y-%m-%d")

    gaps_frame = pd.DataFrame(gaps, columns=GAP_COLUMNS)
    gaps_output = REPORT_DIR / "sector_top_holdings_symbol_gaps.csv"
    gaps_frame.to_csv(gaps_output, index=False)

    coverage = (
        frame.groupby("sector_symbol", as_index=False)
        .agg(
            first_as_of=("as_of_date", "min"),
            last_as_of=("as_of_date", "max"),
            first_known_from=("known_from_date", "min"),
            snapshots=("as_of_date", "nunique"),
            rows=("holding_symbol", "size"),
        )
        .sort_values("sector_symbol")
    )
    coverage_output = REPORT_DIR / "sector_top_holdings_coverage.csv"
    coverage.to_csv(coverage_output, index=False, date_format="%Y-%m-%d")
    return frame


def _write_price_gap_report(frame: pd.DataFrame) -> pd.DataFrame:
    missing_symbols = sorted(
        symbol
        for symbol in set(frame["holding_symbol"])
        if not (PROJECT_ROOT / "cache" / "cache" / f"{symbol}_daily.json").exists()
    )
    if missing_symbols:
        gaps_frame = frame.loc[frame["holding_symbol"].isin(missing_symbols)].copy()
        gaps_frame["missing_reason"] = "Mapped symbol has no Yahoo price cache"
    else:
        gaps_frame = pd.DataFrame(
            columns=[
                "holding_symbol",
                "as_of_date",
                "known_from_date",
                "sector_symbol",
                "holding_name",
                "cusip",
                "isin",
                "weight",
                "val_usd",
                "source",
                "missing_reason",
            ]
        )
    gap_output = REPORT_DIR / "sector_top_holdings_price_gaps.csv"
    gaps_frame.to_csv(gap_output, index=False, date_format="%Y-%m-%d")
    return gaps_frame


def _refresh_missing_price_caches(symbols: list[str], start_date: str, end_date: str) -> dict[str, list[dict[str, Any]]]:
    refreshed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for symbol in sorted(set(symbols)):
        try:
            load_asset_daily(symbol, project_root=PROJECT_ROOT)
            continue
        except FileNotFoundError:
            pass

        try:
            refreshed.append(
                refresh_asset_cache(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    project_root=PROJECT_ROOT,
                )
            )
        except Exception as exc:  # noqa: BLE001
            failed.append({"ticker": symbol, "error": str(exc)})
        time.sleep(0.5)
    return {"refreshed": refreshed, "failed": failed}


def main() -> None:
    args = _parse_args()
    sectors = {_normalize_symbol(symbol) for symbol in args.sectors}
    start_report_date = pd.Timestamp(args.start_report_date)
    end_report_date = pd.Timestamp(args.end_report_date)

    symbol_map = _load_symbol_map(args.symbol_map)
    filings = _load_filings(start_report_date=start_report_date, end_report_date=end_report_date)

    rows: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for index, filing in enumerate(filings, start=1):
        xml_bytes = _load_filing_xml(args.xml_cache_dir, filing=filing, sleep_seconds=args.sec_sleep)
        filing_rows, filing_gaps = _parse_filing(
            filing=filing,
            xml_bytes=xml_bytes,
            sectors=sectors,
            max_holdings_per_sector=args.max_holdings_per_sector,
            known_lag_days=args.known_lag_days,
            symbol_map=symbol_map,
            yahoo_sleep=args.yahoo_sleep,
        )
        rows.extend(filing_rows)
        gaps.extend(filing_gaps)
        if index % 25 == 0:
            _write_symbol_map(args.symbol_map, symbol_map)
            print(f"Parsed {index}/{len(filings)} SEC N-PORT filings...")

    _write_symbol_map(args.symbol_map, symbol_map)
    frame = _write_outputs(rows=rows, gaps=gaps, output_path=args.output)

    price_refresh: dict[str, Any] = {"refreshed": [], "failed": []}
    if args.refresh_prices:
        symbols = sorted(set(frame["holding_symbol"]) | set(frame["sector_symbol"]) | {"SPY"})
        price_refresh = _refresh_missing_price_caches(
            symbols=symbols,
            start_date=args.price_start_date,
            end_date=args.price_end_date,
        )
    price_gaps = _write_price_gap_report(frame)

    print(
        json.dumps(
            {
                "output": str(args.output),
                "rows": int(frame.shape[0]),
                "sectors": sorted(frame["sector_symbol"].unique().tolist()),
                "first_known_from": frame["known_from_date"].min().strftime("%Y-%m-%d"),
                "last_known_from": frame["known_from_date"].max().strftime("%Y-%m-%d"),
                "symbol_gaps": len(gaps),
                "price_gaps": int(price_gaps.shape[0]),
                "coverage": str(REPORT_DIR / "sector_top_holdings_coverage.csv"),
                "gap_report": str(REPORT_DIR / "sector_top_holdings_symbol_gaps.csv"),
                "price_gap_report": str(REPORT_DIR / "sector_top_holdings_price_gaps.csv"),
                "price_refresh": {
                    "refreshed": len(price_refresh.get("refreshed", [])),
                    "failed": len(price_refresh.get("failed", [])),
                },
            },
            indent=2,
        )
    )
    if price_refresh.get("failed"):
        print(json.dumps({"price_refresh_failed": price_refresh["failed"]}, indent=2), file=sys.stderr)


if __name__ == "__main__":
    main()
