from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from .data import load_asset_daily, resolve_project_root
from .sector_fundamentals_research import SECTOR_ETF_MAP

DEFAULT_OUTPUT_DIR = Path("outputs") / "news_sentiment_research"
DEFAULT_CACHE_DIR = Path("cache") / "news_sentiment" / "alpha_vantage"
DEFAULT_API_KEY_ENV = "ALPHA_VANTAGE_API_KEY"
DEFAULT_LOOKBACK_DAYS = 14
DEFAULT_FETCH_WINDOW_DAYS = 3
DEFAULT_RATE_LIMIT_SECONDS = 12.5
DEFAULT_HOLD_DAYS = 5
DEFAULT_MIN_ARTICLE_COUNT = 2
DEFAULT_SENTIMENT_THRESHOLD = 0.05
ALPHA_VANTAGE_NEWS_URL = "https://www.alphavantage.co/query"
REQUEST_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "price-action-news-sentiment/0.1",
}

PROVIDER_OPTIONS: tuple[dict[str, Any], ...] = (
    {
        "provider": "Alpha Vantage",
        "provider_key": "alpha_vantage",
        "point_in_time_articles": True,
        "ticker_mapping": True,
        "article_sentiment": True,
        "ticker_level_sentiment": True,
        "topic_tags": True,
        "repo_fit_rank": 1,
        "access_model": "API key required; free tier is tight for large history",
        "notes": "Best first build for this repo because the payload already includes tickers, topics, and sentiment.",
    },
    {
        "provider": "Tiingo News",
        "provider_key": "tiingo",
        "point_in_time_articles": True,
        "ticker_mapping": True,
        "article_sentiment": False,
        "ticker_level_sentiment": False,
        "topic_tags": True,
        "repo_fit_rank": 2,
        "access_model": "API token required; bulk export is institutional",
        "notes": "Strong coverage and ticker tagging, but sentiment must be computed locally.",
    },
    {
        "provider": "Finnhub",
        "provider_key": "finnhub",
        "point_in_time_articles": True,
        "ticker_mapping": True,
        "article_sentiment": False,
        "ticker_level_sentiment": False,
        "topic_tags": False,
        "repo_fit_rank": 3,
        "access_model": "API token required; company news free, sentiment premium",
        "notes": "Useful for company news, but the sentiment endpoint is premium and not article-granular.",
    },
    {
        "provider": "GDELT",
        "provider_key": "gdelt",
        "point_in_time_articles": True,
        "ticker_mapping": False,
        "article_sentiment": True,
        "ticker_level_sentiment": False,
        "topic_tags": True,
        "repo_fit_rank": 4,
        "access_model": "Open access",
        "notes": "Good open fallback for macro or event studies, but ticker-to-sector mapping is materially weaker.",
    },
)

SECTOR_SYMBOL_TO_NAME = {symbol: sector for sector, symbol in SECTOR_ETF_MAP.items()}
TOPIC_ALIASES = {
    "earnings": "earnings_topic_relevance",
    "technology": "technology_topic_relevance",
    "energy_transportation": "energy_topic_relevance",
    "manufacturing": "manufacturing_topic_relevance",
    "life_sciences": "life_sciences_topic_relevance",
    "real_estate": "real_estate_topic_relevance",
    "retail_wholesale": "retail_topic_relevance",
    "economy_macro": "macro_topic_relevance",
    "economy_monetary": "macro_topic_relevance",
    "economy_fiscal": "macro_topic_relevance",
    "finance": "market_topic_relevance",
    "financial_markets": "market_topic_relevance",
}
TRACKED_TOPIC_COLUMNS = tuple(
    [
        "earnings_topic_relevance",
        "technology_topic_relevance",
        "energy_topic_relevance",
        "manufacturing_topic_relevance",
        "life_sciences_topic_relevance",
        "real_estate_topic_relevance",
        "retail_topic_relevance",
        "macro_topic_relevance",
        "market_topic_relevance",
    ]
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a news-sentiment research dataset that maps article-level ticker sentiment "
            "into sector signals and tests simple sector rotation overlays versus SPY."
        )
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root. Defaults to the repository root.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for the generated news sentiment research outputs.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help="Directory for cached raw news payloads.",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="alpha_vantage",
        choices=["alpha_vantage"],
        help="News provider used for the fetch and parse step.",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Provider API key. If omitted, the value is read from --api-key-env.",
    )
    parser.add_argument(
        "--api-key-env",
        type=str,
        default=DEFAULT_API_KEY_ENV,
        help="Environment variable used when --api-key is omitted.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Fetch fresh raw news payloads before building the research outputs.",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Fetch start date in YYYY-MM-DD format. Defaults to today minus --lookback-days.",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="Fetch end date in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help="Default fetch lookback used when --start-date is omitted.",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=DEFAULT_FETCH_WINDOW_DAYS,
        help="Fetch interval size in calendar days.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=DEFAULT_RATE_LIMIT_SECONDS,
        help="Pause between provider requests when refreshing the raw cache.",
    )
    parser.add_argument(
        "--tickers",
        type=str,
        default=None,
        help="Optional comma-separated ticker filter passed to Alpha Vantage.",
    )
    parser.add_argument(
        "--topics",
        type=str,
        default=None,
        help="Optional comma-separated topic filter passed to Alpha Vantage.",
    )
    parser.add_argument(
        "--hold-days",
        type=int,
        default=DEFAULT_HOLD_DAYS,
        help="Forward holding window used for the headline sector rotation overlay.",
    )
    parser.add_argument(
        "--min-article-count",
        type=int,
        default=DEFAULT_MIN_ARTICLE_COUNT,
        help="Minimum number of distinct articles required before a sector signal can replace SPY.",
    )
    parser.add_argument(
        "--sentiment-threshold",
        type=float,
        default=DEFAULT_SENTIMENT_THRESHOLD,
        help="Minimum sector sentiment score required before a sector signal can replace SPY.",
    )
    return parser.parse_args()


def _resolve_output_path(root: Path, target: Path) -> Path:
    return target if target.is_absolute() else root / target


def _normalize_ticker(value: Any) -> str:
    text = str(value or "").strip().upper()
    text = text.replace(".", "-")
    text = text.replace("/", "-")
    return text


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(numeric):
        return None
    return numeric


def _parse_date(value: str | None, default_value: date) -> date:
    if not value:
        return default_value
    return date.fromisoformat(value)


def _date_range_bounds(*, start_date: str | None, end_date: str | None, lookback_days: int) -> tuple[date, date]:
    today = datetime.now(UTC).date()
    end_bound = _parse_date(end_date, today)
    start_default = end_bound - timedelta(days=max(lookback_days - 1, 0))
    start_bound = _parse_date(start_date, start_default)
    if start_bound > end_bound:
        raise ValueError("start_date must be on or before end_date.")
    return start_bound, end_bound


def _iter_fetch_windows(start_bound: date, end_bound: date, window_days: int) -> list[tuple[date, date]]:
    if window_days <= 0:
        raise ValueError("window_days must be positive.")
    windows: list[tuple[date, date]] = []
    cursor = start_bound
    while cursor <= end_bound:
        window_end = min(cursor + timedelta(days=window_days - 1), end_bound)
        windows.append((cursor, window_end))
        cursor = window_end + timedelta(days=1)
    return windows


def _alpha_vantage_timestamp(value: date, *, end_of_day: bool) -> str:
    suffix = "2359" if end_of_day else "0000"
    return value.strftime("%Y%m%d") + f"T{suffix}"


def _request_json(url: str, *, timeout: int = 60) -> dict[str, Any]:
    request = Request(url, headers=REQUEST_HEADERS)
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _provider_options_table() -> pd.DataFrame:
    return pd.DataFrame(PROVIDER_OPTIONS).sort_values("repo_fit_rank").reset_index(drop=True)


def _provider_recommendation() -> dict[str, Any]:
    return {
        "preferred_provider": "Alpha Vantage",
        "provider_key": "alpha_vantage",
        "reason": (
            "Best first source for this repo because it returns point-in-time articles, article-level sentiment, "
            "topic tags, and per-ticker relevance plus ticker sentiment in a single payload."
        ),
        "main_tradeoff": "The free tier is too tight for deep history, so broader studies should use premium access or build cache incrementally.",
        "fallback_provider": "Tiingo News",
    }


def build_ticker_sector_map(*, root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    analysis_dir = root / "outputs" / "fundamentals_analysis"
    for filename, priority in (
        ("sector_analysis_eligible_symbols.csv", 1),
        ("sector_analysis_excluded_symbols.csv", 2),
    ):
        path = analysis_dir / filename
        if not path.exists():
            continue
        frame = pd.read_csv(path, usecols=["symbol", "sector"], dtype={"symbol": "string", "sector": "string"})
        frame = frame.rename(columns={"sector": "sector_name"})
        frame["symbol"] = frame["symbol"].map(_normalize_ticker)
        frame["sector_name"] = frame["sector_name"].astype("string").str.strip().str.upper()
        frame["sector_symbol"] = frame["sector_name"].map(SECTOR_ETF_MAP)
        frame["mapping_source"] = filename.replace(".csv", "")
        frame["mapping_priority"] = priority
        frames.append(frame)

    holdings_path = root / "data" / "sector_top_holdings.csv"
    if holdings_path.exists():
        holdings = pd.read_csv(
            holdings_path,
            usecols=["holding_symbol", "sector_symbol", "weight", "known_from_date"],
            dtype={"holding_symbol": "string", "sector_symbol": "string"},
        )
        holdings["holding_symbol"] = holdings["holding_symbol"].map(_normalize_ticker)
        holdings["sector_symbol"] = holdings["sector_symbol"].astype("string").str.strip().str.upper()
        holdings["known_from_date"] = pd.to_datetime(holdings["known_from_date"], errors="coerce")
        holdings["weight"] = pd.to_numeric(holdings["weight"], errors="coerce")
        holdings = holdings.sort_values(["holding_symbol", "known_from_date", "weight"], ascending=[True, False, False])
        latest_holdings = holdings.drop_duplicates(subset=["holding_symbol"], keep="first")
        latest_holdings = latest_holdings.rename(columns={"holding_symbol": "symbol"})
        latest_holdings["sector_name"] = latest_holdings["sector_symbol"].map(SECTOR_SYMBOL_TO_NAME)
        latest_holdings["mapping_source"] = "sector_top_holdings"
        latest_holdings["mapping_priority"] = 0
        frames.append(latest_holdings[["symbol", "sector_name", "sector_symbol", "mapping_source", "mapping_priority"]])

    sector_rows = pd.DataFrame(
        {
            "symbol": list(SECTOR_SYMBOL_TO_NAME.keys()),
            "sector_name": list(SECTOR_SYMBOL_TO_NAME.values()),
            "sector_symbol": list(SECTOR_SYMBOL_TO_NAME.keys()),
            "mapping_source": "sector_etf_map",
            "mapping_priority": -1,
        }
    )
    frames.append(sector_rows)

    if not frames:
        raise FileNotFoundError("No ticker-to-sector sources were found. Expected fundamentals outputs or sector holdings data.")

    ticker_map = pd.concat(frames, ignore_index=True)
    ticker_map = ticker_map.dropna(subset=["symbol", "sector_name", "sector_symbol"]).copy()
    ticker_map["symbol"] = ticker_map["symbol"].map(_normalize_ticker)
    ticker_map["sector_name"] = ticker_map["sector_name"].astype("string").str.strip().str.upper()
    ticker_map["sector_symbol"] = ticker_map["sector_symbol"].astype("string").str.strip().str.upper()
    ticker_map = ticker_map.sort_values(["symbol", "mapping_priority"]).drop_duplicates(subset=["symbol"], keep="first")
    return ticker_map.reset_index(drop=True)


def fetch_alpha_vantage_news_cache(
    *,
    cache_dir: Path,
    api_key: str,
    start_bound: date,
    end_bound: date,
    window_days: int,
    sleep_seconds: float,
    tickers: str | None,
    topics: str | None,
) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    fetch_rows: list[dict[str, Any]] = []
    demo_mode = api_key.strip().lower() == "demo"
    windows = [(end_bound, end_bound)] if demo_mode else _iter_fetch_windows(start_bound, end_bound, window_days)
    for window_start, window_end in windows:
        cache_name = f"news_{window_start:%Y%m%d}_{window_end:%Y%m%d}"
        if tickers:
            cache_name += f"_tickers_{tickers.replace(',', '-') }"
        if topics:
            cache_name += f"_topics_{topics.replace(',', '-') }"
        cache_path = cache_dir / f"{cache_name}.json"
        if cache_path.exists():
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            fetch_rows.append(
                {
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                    "cache_path": str(cache_path),
                    "article_count": len((payload.get("feed") or [])),
                    "status": "cached",
                }
            )
            continue

        params = {
            "function": "NEWS_SENTIMENT",
            "apikey": api_key,
        }
        if demo_mode:
            params = {
                "function": "NEWS_SENTIMENT",
                "apikey": api_key,
            }
        else:
            params["sort"] = "EARLIEST"
            params["limit"] = 1000
            params["time_from"] = _alpha_vantage_timestamp(window_start, end_of_day=False)
            params["time_to"] = _alpha_vantage_timestamp(window_end, end_of_day=True)
        if tickers:
            params["tickers"] = tickers
        if topics:
            params["topics"] = topics
        if demo_mode:
            ordered_pairs = [("function", "NEWS_SENTIMENT")]
            if tickers:
                ordered_pairs.append(("tickers", tickers))
            if topics:
                ordered_pairs.append(("topics", topics))
            ordered_pairs.append(("apikey", api_key))
            ordered_query = "&".join(f"{key}={quote_plus(str(value))}" for key, value in ordered_pairs)
            query_url = f"{ALPHA_VANTAGE_NEWS_URL}?{ordered_query}"
        else:
            query_url = f"{ALPHA_VANTAGE_NEWS_URL}?{urlencode(params)}"
        payload = _request_json(query_url)

        provider_error = payload.get("Error Message") or payload.get("Information") or payload.get("Note")
        if provider_error and "feed" not in payload:
            raise RuntimeError(f"Alpha Vantage news request failed for {window_start}..{window_end}: {provider_error}")

        wrapped_payload = {
            "provider": "alpha_vantage",
            "fetched_at_utc": datetime.now(UTC).isoformat(),
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "tickers": tickers,
            "topics": topics,
            "payload": payload,
        }
        _write_json(cache_path, wrapped_payload)
        fetch_rows.append(
            {
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "cache_path": str(cache_path),
                "article_count": len((payload.get("feed") or [])),
                "status": "fetched",
            }
        )
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return pd.DataFrame(fetch_rows)


def _parse_alpha_vantage_timestamp(value: Any) -> pd.Timestamp | pd.NaT:
    text = str(value or "").strip()
    if not text:
        return pd.NaT
    try:
        return pd.Timestamp(datetime.strptime(text, "%Y%m%dT%H%M"), tz="UTC")
    except ValueError:
        return pd.NaT


def _topic_feature_values(raw_topics: Any) -> dict[str, float]:
    topic_values = {column: 0.0 for column in TRACKED_TOPIC_COLUMNS}
    if not isinstance(raw_topics, list):
        return topic_values
    for item in raw_topics:
        if not isinstance(item, dict):
            continue
        raw_topic = str(item.get("topic") or "").strip().lower()
        column = TOPIC_ALIASES.get(raw_topic)
        score = _safe_float(item.get("relevance_score")) or 0.0
        if column is None:
            continue
        topic_values[column] = max(topic_values[column], score)
    return topic_values


def parse_alpha_vantage_cache(
    *,
    cache_dir: Path,
    ticker_sector_map: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sector_lookup = ticker_sector_map.set_index("symbol")[["sector_name", "sector_symbol", "mapping_source"]].to_dict("index")

    article_rows: list[dict[str, Any]] = []
    mention_rows: list[dict[str, Any]] = []
    unmapped_rows: list[dict[str, Any]] = []
    seen_articles: set[str] = set()
    seen_mentions: set[tuple[str, str]] = set()

    for path in sorted(cache_dir.glob("*.json")):
        wrapped_payload = json.loads(path.read_text(encoding="utf-8"))
        payload = wrapped_payload.get("payload") if isinstance(wrapped_payload.get("payload"), dict) else wrapped_payload
        feed = payload.get("feed") or []
        for article in feed:
            if not isinstance(article, dict):
                continue

            published_at = _parse_alpha_vantage_timestamp(article.get("time_published"))
            published_date = published_at.tz_convert(None).normalize() if not pd.isna(published_at) else pd.NaT
            url = str(article.get("url") or "").strip()
            title = str(article.get("title") or "").strip()
            article_key = f"{published_at.isoformat() if not pd.isna(published_at) else ''}|{url}|{title}"
            article_id = hashlib.sha1(article_key.encode("utf-8")).hexdigest()[:16]
            topic_values = _topic_feature_values(article.get("topics"))
            overall_sentiment_score = _safe_float(article.get("overall_sentiment_score")) or 0.0

            if article_id not in seen_articles:
                article_rows.append(
                    {
                        "article_id": article_id,
                        "published_at_utc": published_at.tz_convert(None) if not pd.isna(published_at) else pd.NaT,
                        "article_date": published_date,
                        "title": title,
                        "url": url,
                        "source": str(article.get("source") or "").strip(),
                        "source_domain": str(article.get("source_domain") or "").strip(),
                        "category_within_source": str(article.get("category_within_source") or "").strip(),
                        "overall_sentiment_score": overall_sentiment_score,
                        "overall_sentiment_label": str(article.get("overall_sentiment_label") or "").strip(),
                        "author_count": len(article.get("authors") or []),
                        **topic_values,
                        "cache_file": path.name,
                    }
                )
                seen_articles.add(article_id)

            for mention in article.get("ticker_sentiment") or []:
                if not isinstance(mention, dict):
                    continue
                ticker = _normalize_ticker(mention.get("ticker"))
                if not ticker:
                    continue
                mention_key = (article_id, ticker)
                if mention_key in seen_mentions:
                    continue
                seen_mentions.add(mention_key)

                relevance_score = _safe_float(mention.get("relevance_score")) or 0.0
                ticker_sentiment_score = _safe_float(mention.get("ticker_sentiment_score")) or 0.0
                sector_info = sector_lookup.get(ticker)

                row = {
                    "article_id": article_id,
                    "published_at_utc": published_at.tz_convert(None) if not pd.isna(published_at) else pd.NaT,
                    "article_date": published_date,
                    "ticker": ticker,
                    "relevance_score": relevance_score,
                    "ticker_sentiment_score": ticker_sentiment_score,
                    "ticker_sentiment_label": str(mention.get("ticker_sentiment_label") or "").strip(),
                    "overall_sentiment_score": overall_sentiment_score,
                    "weighted_ticker_sentiment": relevance_score * ticker_sentiment_score,
                    "weighted_abs_sentiment": relevance_score * abs(ticker_sentiment_score),
                    "weighted_overall_sentiment": relevance_score * overall_sentiment_score,
                    "bullish_relevance": relevance_score if ticker_sentiment_score >= 0.15 else 0.0,
                    "bearish_relevance": relevance_score if ticker_sentiment_score <= -0.15 else 0.0,
                    **topic_values,
                }

                for topic_column in TRACKED_TOPIC_COLUMNS:
                    row[f"weighted_{topic_column}"] = relevance_score * row[topic_column]

                if sector_info is None:
                    unmapped_rows.append(
                        {
                            "ticker": ticker,
                            "article_id": article_id,
                            "article_date": published_date,
                            "relevance_score": relevance_score,
                            "ticker_sentiment_score": ticker_sentiment_score,
                        }
                    )
                    continue

                row["sector"] = sector_info["sector_name"]
                row["sector_symbol"] = sector_info["sector_symbol"]
                row["mapping_source"] = sector_info["mapping_source"]
                mention_rows.append(row)

    articles = pd.DataFrame(article_rows)
    mentions = pd.DataFrame(mention_rows)
    unmapped = pd.DataFrame(unmapped_rows)
    if not articles.empty:
        articles = articles.sort_values(["published_at_utc", "article_id"]).reset_index(drop=True)
    if not mentions.empty:
        mentions = mentions.sort_values(["published_at_utc", "article_id", "ticker"]).reset_index(drop=True)
    if not unmapped.empty:
        unmapped = (
            unmapped.groupby("ticker", as_index=False)
            .agg(
                mentions=("article_id", "count"),
                avg_relevance_score=("relevance_score", "mean"),
                avg_ticker_sentiment_score=("ticker_sentiment_score", "mean"),
            )
            .sort_values(["mentions", "ticker"], ascending=[False, True])
            .reset_index(drop=True)
        )
    return articles, mentions, unmapped


def _signal_date_mapping(article_dates: pd.Series, trading_dates: pd.DatetimeIndex) -> pd.DataFrame:
    unique_dates = pd.Series(pd.to_datetime(article_dates, errors="coerce").dropna().dt.normalize().unique())
    if unique_dates.empty:
        return pd.DataFrame(columns=["article_date", "signal_date"])

    lookup = pd.DataFrame({"article_date": unique_dates.sort_values().reset_index(drop=True)})
    lookup["lookup_date"] = lookup["article_date"] + pd.Timedelta(days=1)
    calendar = pd.DataFrame({"signal_date": pd.DatetimeIndex(trading_dates).normalize().unique()}).sort_values("signal_date")
    mapping = pd.merge_asof(
        lookup.sort_values("lookup_date"),
        calendar,
        left_on="lookup_date",
        right_on="signal_date",
        direction="forward",
    )
    return mapping[["article_date", "signal_date"]]


def build_sector_daily_sentiment(*, mentions: pd.DataFrame, trading_dates: pd.DatetimeIndex) -> pd.DataFrame:
    if mentions.empty:
        return pd.DataFrame()

    mapping = _signal_date_mapping(mentions["article_date"], trading_dates)
    enriched = mentions.merge(mapping, on="article_date", how="left")
    enriched = enriched.dropna(subset=["signal_date", "sector", "sector_symbol"]).copy()
    if enriched.empty:
        return pd.DataFrame()

    aggregation_kwargs: dict[str, tuple[str, str]] = {
        "article_count": ("article_id", "nunique"),
        "mention_count": ("ticker", "size"),
        "total_relevance": ("relevance_score", "sum"),
        "weighted_ticker_sentiment_sum": ("weighted_ticker_sentiment", "sum"),
        "weighted_abs_sentiment_sum": ("weighted_abs_sentiment", "sum"),
        "weighted_overall_sentiment_sum": ("weighted_overall_sentiment", "sum"),
        "bullish_relevance_sum": ("bullish_relevance", "sum"),
        "bearish_relevance_sum": ("bearish_relevance", "sum"),
        "article_date_min": ("article_date", "min"),
        "article_date_max": ("article_date", "max"),
    }
    for topic_column in TRACKED_TOPIC_COLUMNS:
        aggregation_kwargs[f"weighted_{topic_column}_sum"] = (f"weighted_{topic_column}", "sum")

    grouped = enriched.groupby(["signal_date", "sector", "sector_symbol"], as_index=False)
    sector_daily = grouped.agg(**aggregation_kwargs)
    valid_relevance = sector_daily["total_relevance"].where(sector_daily["total_relevance"] > 0.0)

    sector_daily["sector_sentiment"] = sector_daily["weighted_ticker_sentiment_sum"] / valid_relevance
    sector_daily["sector_abs_sentiment"] = sector_daily["weighted_abs_sentiment_sum"] / valid_relevance
    sector_daily["article_overall_sentiment"] = sector_daily["weighted_overall_sentiment_sum"] / valid_relevance
    sector_daily["bullish_relevance_share"] = sector_daily["bullish_relevance_sum"] / valid_relevance
    sector_daily["bearish_relevance_share"] = sector_daily["bearish_relevance_sum"] / valid_relevance
    sector_daily["signal_strength"] = sector_daily["sector_sentiment"] * np.log1p(sector_daily["article_count"])

    for topic_column in TRACKED_TOPIC_COLUMNS:
        sector_daily[topic_column] = sector_daily[f"weighted_{topic_column}_sum"] / valid_relevance

    sector_daily["sector_sentiment_rank_pct"] = sector_daily.groupby("signal_date")["sector_sentiment"].rank(pct=True)
    sector_daily["signal_strength_rank_pct"] = sector_daily.groupby("signal_date")["signal_strength"].rank(pct=True)

    def _zscore(series: pd.Series) -> pd.Series:
        std = float(series.std(ddof=0))
        if std <= 0.0 or not np.isfinite(std):
            return pd.Series(np.zeros(len(series)), index=series.index, dtype="float64")
        return (series - float(series.mean())) / std

    sector_daily["sector_sentiment_zscore"] = sector_daily.groupby("signal_date")["sector_sentiment"].transform(_zscore)
    sector_daily["signal_strength_zscore"] = sector_daily.groupby("signal_date")["signal_strength"].transform(_zscore)

    sort_columns = ["signal_date", "sector"]
    return sector_daily.sort_values(sort_columns).reset_index(drop=True)


def build_sector_return_panel(*, root: Path, horizons: list[int]) -> pd.DataFrame:
    sector_frames: list[pd.DataFrame] = []
    for sector, symbol in SECTOR_ETF_MAP.items():
        asset = load_asset_daily(symbol, project_root=root).sort_index().copy()
        close = pd.to_numeric(asset["close"], errors="coerce")
        sector_frame = pd.DataFrame(
            {
                "trade_date": asset.index.normalize(),
                "sector": sector,
                "sector_symbol": symbol,
                "sector_close": close,
            }
        )
        for horizon in horizons:
            sector_frame[f"sector_forward_return_{horizon}d"] = close.shift(-horizon) / close - 1.0
        sector_frames.append(sector_frame)

    sector_panel = pd.concat(sector_frames, ignore_index=True)

    spy_asset = load_asset_daily("SPY", project_root=root).sort_index().copy()
    spy_close = pd.to_numeric(spy_asset["close"], errors="coerce")
    spy = pd.DataFrame({"trade_date": spy_asset.index.normalize(), "spy_close": spy_close})
    for horizon in horizons:
        spy[f"spy_forward_return_{horizon}d"] = spy_close.shift(-horizon) / spy_close - 1.0

    merged = sector_panel.merge(spy, on="trade_date", how="left")
    for horizon in horizons:
        merged[f"sector_excess_forward_return_{horizon}d"] = (
            merged[f"sector_forward_return_{horizon}d"] - merged[f"spy_forward_return_{horizon}d"]
        )
    return merged.sort_values(["trade_date", "sector"]).reset_index(drop=True)


def build_sector_sentiment_panel(*, sector_daily: pd.DataFrame, returns_panel: pd.DataFrame) -> pd.DataFrame:
    if sector_daily.empty:
        return pd.DataFrame()
    panel = sector_daily.merge(
        returns_panel,
        left_on=["signal_date", "sector", "sector_symbol"],
        right_on=["trade_date", "sector", "sector_symbol"],
        how="left",
    )
    return panel.sort_values(["signal_date", "sector"]).reset_index(drop=True)


def _safe_corr(left: pd.Series, right: pd.Series) -> float | None:
    pair = pd.DataFrame({"left": left, "right": right}).dropna()
    if len(pair) < 5:
        return None
    correlation = pair["left"].corr(pair["right"])
    if pd.isna(correlation):
        return None
    return float(correlation)


def build_event_study(panel: pd.DataFrame, *, horizons: list[int], sentiment_threshold: float) -> pd.DataFrame:
    if panel.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    buckets: list[tuple[str, pd.DataFrame]] = [("ALL", panel)]
    buckets.extend((sector, group) for sector, group in panel.groupby("sector"))

    for sector_name, frame in buckets:
        row: dict[str, Any] = {
            "sector": sector_name,
            "observations": int(len(frame)),
            "avg_article_count": float(frame["article_count"].mean()) if not frame.empty else None,
            "avg_sector_sentiment": float(frame["sector_sentiment"].mean()) if not frame.empty else None,
            "avg_signal_strength": float(frame["signal_strength"].mean()) if not frame.empty else None,
        }
        for horizon in horizons:
            target_column = f"sector_excess_forward_return_{horizon}d"
            row[f"corr_sentiment_excess_{horizon}d"] = _safe_corr(frame["sector_sentiment"], frame[target_column])
            positive_frame = frame.loc[frame["sector_sentiment"] >= sentiment_threshold, target_column]
            negative_frame = frame.loc[frame["sector_sentiment"] <= -sentiment_threshold, target_column]
            row[f"positive_signal_avg_excess_{horizon}d"] = float(positive_frame.mean()) if not positive_frame.empty else None
            row[f"negative_signal_avg_excess_{horizon}d"] = float(negative_frame.mean()) if not negative_frame.empty else None
            if len(frame) >= 10:
                upper_threshold = float(frame["sector_sentiment"].quantile(0.80))
                lower_threshold = float(frame["sector_sentiment"].quantile(0.20))
                top_bucket = frame.loc[frame["sector_sentiment"] >= upper_threshold, target_column]
                bottom_bucket = frame.loc[frame["sector_sentiment"] <= lower_threshold, target_column]
                row[f"top_bucket_avg_excess_{horizon}d"] = float(top_bucket.mean()) if not top_bucket.empty else None
                row[f"bottom_bucket_avg_excess_{horizon}d"] = float(bottom_bucket.mean()) if not bottom_bucket.empty else None
                if not top_bucket.empty and not bottom_bucket.empty:
                    row[f"top_minus_bottom_excess_{horizon}d"] = float(top_bucket.mean() - bottom_bucket.mean())
                else:
                    row[f"top_minus_bottom_excess_{horizon}d"] = None
            else:
                row[f"top_bucket_avg_excess_{horizon}d"] = None
                row[f"bottom_bucket_avg_excess_{horizon}d"] = None
                row[f"top_minus_bottom_excess_{horizon}d"] = None
        rows.append(row)

    return pd.DataFrame(rows)


def build_rotation_strategy(
    *,
    panel: pd.DataFrame,
    returns_panel: pd.DataFrame,
    top_n: int,
    hold_days: int,
    min_article_count: int,
    sentiment_threshold: float,
) -> pd.DataFrame:
    if panel.empty or returns_panel.empty:
        return pd.DataFrame()

    trade_dates = pd.DatetimeIndex(sorted(pd.to_datetime(returns_panel["trade_date"], errors="coerce").dropna().unique()))
    if trade_dates.empty:
        return pd.DataFrame()

    panel_by_date: dict[pd.Timestamp, pd.DataFrame] = {
        pd.Timestamp(signal_date): group.sort_values(["signal_strength", "sector_sentiment", "article_count"], ascending=False)
        for signal_date, group in panel.groupby("signal_date")
    }
    spy_by_date = (
        returns_panel[["trade_date", f"spy_forward_return_{hold_days}d"]]
        .drop_duplicates(subset=["trade_date"])
        .rename(columns={f"spy_forward_return_{hold_days}d": "benchmark_return"})
        .set_index("trade_date")
    )

    rows: list[dict[str, Any]] = []
    index_position = 0
    while index_position < len(trade_dates):
        trade_date = pd.Timestamp(trade_dates[index_position]).normalize()
        day_panel = panel_by_date.get(trade_date)
        benchmark_return = None
        if trade_date in spy_by_date.index:
            benchmark_value = spy_by_date.loc[trade_date, "benchmark_return"]
            benchmark_return = float(benchmark_value) if pd.notna(benchmark_value) else None

        selected_sectors = ""
        selected_symbols = ""
        signal_mode = "spy_fallback"
        signal_score = None
        portfolio_return = benchmark_return
        if day_panel is not None:
            eligible = day_panel.loc[
                (day_panel["article_count"] >= min_article_count)
                & (day_panel["sector_sentiment"] >= sentiment_threshold)
            ].copy()
            if not eligible.empty:
                selected = eligible.head(top_n)
                return_column = f"sector_forward_return_{hold_days}d"
                if selected[return_column].notna().any():
                    portfolio_return = float(selected[return_column].mean())
                    selected_sectors = ", ".join(selected["sector"].tolist())
                    selected_symbols = ", ".join(selected["sector_symbol"].tolist())
                    signal_mode = "sector_rotation"
                    signal_score = float(selected["signal_strength"].mean())

        if portfolio_return is None or benchmark_return is None:
            index_position += hold_days
            continue

        rows.append(
            {
                "trade_date": trade_date,
                "hold_days": hold_days,
                "top_n": top_n,
                "signal_mode": signal_mode,
                "selected_sectors": selected_sectors,
                "selected_symbols": selected_symbols,
                "signal_strength": signal_score,
                "portfolio_return": float(portfolio_return),
                "spy_return": float(benchmark_return),
                "excess_return": float(portfolio_return - benchmark_return),
            }
        )
        index_position += hold_days

    strategy = pd.DataFrame(rows)
    if strategy.empty:
        return strategy
    strategy = strategy.sort_values("trade_date").reset_index(drop=True)
    strategy["portfolio_equity"] = (1.0 + strategy["portfolio_return"]).cumprod()
    strategy["spy_equity"] = (1.0 + strategy["spy_return"]).cumprod()
    strategy["alpha_equity"] = (1.0 + strategy["excess_return"]).cumprod()
    return strategy


def summarize_strategy(strategy: pd.DataFrame) -> dict[str, float | int | None]:
    if strategy.empty:
        return {
            "periods": 0,
            "rotation_periods": 0,
            "total_return": None,
            "spy_total_return": None,
            "avg_excess_return": None,
            "hit_rate_vs_spy": None,
            "max_drawdown": None,
        }

    portfolio_equity = strategy["portfolio_equity"].astype(float)
    spy_equity = strategy["spy_equity"].astype(float)
    drawdown = portfolio_equity / portfolio_equity.cummax() - 1.0
    return {
        "periods": int(len(strategy)),
        "rotation_periods": int((strategy["signal_mode"] == "sector_rotation").sum()),
        "total_return": float(portfolio_equity.iloc[-1] - 1.0),
        "spy_total_return": float(spy_equity.iloc[-1] - 1.0),
        "avg_excess_return": float(strategy["excess_return"].mean()),
        "hit_rate_vs_spy": float((strategy["excess_return"] > 0.0).mean()),
        "max_drawdown": float(drawdown.min()) if not drawdown.empty else None,
    }


def build_news_sentiment_research(
    *,
    project_root: str | Path | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    provider: str = "alpha_vantage",
    api_key: str | None = None,
    api_key_env: str = DEFAULT_API_KEY_ENV,
    refresh_cache: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    window_days: int = DEFAULT_FETCH_WINDOW_DAYS,
    sleep_seconds: float = DEFAULT_RATE_LIMIT_SECONDS,
    tickers: str | None = None,
    topics: str | None = None,
    hold_days: int = DEFAULT_HOLD_DAYS,
    min_article_count: int = DEFAULT_MIN_ARTICLE_COUNT,
    sentiment_threshold: float = DEFAULT_SENTIMENT_THRESHOLD,
) -> dict[str, Any]:
    if provider != "alpha_vantage":
        raise ValueError(f"Unsupported provider: {provider}")

    root = resolve_project_root(project_root)
    resolved_output_dir = _resolve_output_path(root, output_dir)
    resolved_cache_dir = _resolve_output_path(root, cache_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    resolved_cache_dir.mkdir(parents=True, exist_ok=True)

    provider_options = _provider_options_table()
    provider_options.to_csv(resolved_output_dir / "news_provider_options.csv", index=False)

    recommendation = _provider_recommendation()
    _write_json(resolved_output_dir / "provider_recommendation.json", recommendation)

    ticker_sector_map = build_ticker_sector_map(root=root)
    ticker_sector_map.to_csv(resolved_output_dir / "ticker_sector_map.csv", index=False)

    requested_api_key = api_key or None
    effective_api_key = requested_api_key or os.environ.get(api_key_env)
    start_bound, end_bound = _date_range_bounds(start_date=start_date, end_date=end_date, lookback_days=lookback_days)

    cache_refresh_table = pd.DataFrame()
    if refresh_cache:
        if not effective_api_key:
            raise ValueError(f"No API key was provided. Set --api-key or environment variable {api_key_env}.")
        cache_refresh_table = fetch_alpha_vantage_news_cache(
            cache_dir=resolved_cache_dir,
            api_key=effective_api_key,
            start_bound=start_bound,
            end_bound=end_bound,
            window_days=window_days,
            sleep_seconds=sleep_seconds,
            tickers=tickers,
            topics=topics,
        )
        cache_refresh_table.to_csv(resolved_output_dir / "cache_refresh_log.csv", index=False)

    cache_files = sorted(resolved_cache_dir.glob("*.json"))
    if not cache_files:
        summary = {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "status": "no_cached_news",
            "provider": provider,
            "cache_dir": str(resolved_cache_dir),
            "output_dir": str(resolved_output_dir),
            "provider_recommendation": recommendation,
            "ticker_sector_map_rows": int(len(ticker_sector_map)),
            "query_filters": {"tickers": tickers, "topics": topics},
            "date_range": {"start_date": start_bound.isoformat(), "end_date": end_bound.isoformat()},
            "message": "No cached raw news payloads were found. Refresh the cache with an API key before running the full research pipeline.",
        }
        _write_json(resolved_output_dir / "news_sentiment_summary.json", summary)
        return summary

    articles, mentions, unmapped = parse_alpha_vantage_cache(cache_dir=resolved_cache_dir, ticker_sector_map=ticker_sector_map)
    articles.to_csv(resolved_output_dir / "alpha_vantage_articles.csv", index=False)
    mentions.to_csv(resolved_output_dir / "alpha_vantage_ticker_mentions.csv", index=False)
    unmapped.to_csv(resolved_output_dir / "unmapped_ticker_mentions.csv", index=False)

    if mentions.empty:
        summary = {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "status": "no_mapped_mentions",
            "provider": provider,
            "cache_file_count": int(len(cache_files)),
            "article_count": int(len(articles)),
            "mapped_ticker_mentions": 0,
            "unmapped_ticker_count": int(len(unmapped)),
            "provider_recommendation": recommendation,
            "query_filters": {"tickers": tickers, "topics": topics},
            "message": "Cached news was found, but none of the ticker mentions mapped into the current sector universe.",
        }
        _write_json(resolved_output_dir / "news_sentiment_summary.json", summary)
        return summary

    trading_dates = pd.DatetimeIndex(load_asset_daily("SPY", project_root=root).sort_index().index)
    horizons = sorted({1, 5, hold_days})
    sector_daily = build_sector_daily_sentiment(mentions=mentions, trading_dates=trading_dates)
    sector_daily.to_csv(resolved_output_dir / "sector_daily_sentiment.csv", index=False)

    returns_panel = build_sector_return_panel(root=root, horizons=horizons)
    panel = build_sector_sentiment_panel(sector_daily=sector_daily, returns_panel=returns_panel)
    panel.to_csv(resolved_output_dir / "sector_sentiment_panel.csv", index=False)

    event_study = build_event_study(panel=panel, horizons=horizons, sentiment_threshold=sentiment_threshold)
    event_study.to_csv(resolved_output_dir / "sector_sentiment_event_study.csv", index=False)

    strategy_top1 = build_rotation_strategy(
        panel=panel,
        returns_panel=returns_panel,
        top_n=1,
        hold_days=hold_days,
        min_article_count=min_article_count,
        sentiment_threshold=sentiment_threshold,
    )
    strategy_top3 = build_rotation_strategy(
        panel=panel,
        returns_panel=returns_panel,
        top_n=3,
        hold_days=hold_days,
        min_article_count=min_article_count,
        sentiment_threshold=sentiment_threshold,
    )
    strategy_top1.to_csv(resolved_output_dir / f"sentiment_rotation_strategy_top1_{hold_days}d.csv", index=False)
    strategy_top3.to_csv(resolved_output_dir / f"sentiment_rotation_strategy_top3_{hold_days}d.csv", index=False)

    strategy_summary = pd.DataFrame(
        [
            {"strategy_name": f"top1_sector_or_spy_{hold_days}d", **summarize_strategy(strategy_top1)},
            {"strategy_name": f"top3_sector_or_spy_{hold_days}d", **summarize_strategy(strategy_top3)},
        ]
    )
    strategy_summary.to_csv(resolved_output_dir / "strategy_summary.csv", index=False)

    if sector_daily.empty:
        sector_coverage = pd.DataFrame(columns=["sector", "sector_symbol", "signal_dates", "article_count", "avg_sentiment"])
    else:
        sector_coverage = (
            sector_daily.groupby(["sector", "sector_symbol"], as_index=False)
            .agg(
                signal_dates=("signal_date", "nunique"),
                article_count=("article_count", "sum"),
                avg_sentiment=("sector_sentiment", "mean"),
            )
            .sort_values(["article_count", "sector"], ascending=[False, True])
        )
    sector_coverage.to_csv(resolved_output_dir / "sector_signal_coverage.csv", index=False)

    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "ok",
        "provider": provider,
        "provider_recommendation": recommendation,
        "cache_dir": str(resolved_cache_dir),
        "output_dir": str(resolved_output_dir),
        "cache_file_count": int(len(cache_files)),
        "cache_refresh_rows": int(len(cache_refresh_table)),
        "date_range": {"start_date": start_bound.isoformat(), "end_date": end_bound.isoformat()},
        "query_filters": {"tickers": tickers, "topics": topics},
        "article_count": int(len(articles)),
        "mapped_ticker_mentions": int(len(mentions)),
        "unmapped_ticker_count": int(len(unmapped)),
        "sector_daily_rows": int(len(sector_daily)),
        "sector_count": int(sector_daily["sector"].nunique()) if not sector_daily.empty else 0,
        "event_study_rows": int(len(event_study)),
        "strategy_summary": strategy_summary.to_dict(orient="records"),
    }
    _write_json(resolved_output_dir / "news_sentiment_summary.json", summary)
    return summary


def main() -> None:
    args = parse_args()
    summary = build_news_sentiment_research(
        project_root=args.project_root,
        output_dir=args.output_dir,
        cache_dir=args.cache_dir,
        provider=args.provider,
        api_key=args.api_key,
        api_key_env=args.api_key_env,
        refresh_cache=args.refresh_cache,
        start_date=args.start_date,
        end_date=args.end_date,
        lookback_days=args.lookback_days,
        window_days=args.window_days,
        sleep_seconds=args.sleep_seconds,
        tickers=args.tickers,
        topics=args.topics,
        hold_days=args.hold_days,
        min_article_count=args.min_article_count,
        sentiment_threshold=args.sentiment_threshold,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()