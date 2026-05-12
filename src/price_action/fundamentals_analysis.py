from __future__ import annotations

import argparse
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .data import resolve_project_root

DEFAULT_OUTPUT_DIR = Path("outputs") / "fundamentals_analysis"
NUMERIC_OVERVIEW_FIELDS = {
    "MarketCapitalization": "market_cap",
    "EBITDA": "ebitda",
    "PERatio": "pe_ratio",
    "PEGRatio": "peg_ratio",
    "BookValue": "book_value",
    "DividendPerShare": "dividend_per_share",
    "DividendYield": "dividend_yield",
    "EPS": "eps_ttm",
    "DilutedEPSTTM": "diluted_eps_ttm",
    "RevenueTTM": "revenue_ttm",
    "ProfitMargin": "profit_margin",
    "OperatingMarginTTM": "operating_margin_ttm",
    "ReturnOnAssetsTTM": "return_on_assets_ttm",
    "ReturnOnEquityTTM": "return_on_equity_ttm",
    "RevenuePerShareTTM": "revenue_per_share_ttm",
    "QuarterlyEarningsGrowthYOY": "quarterly_earnings_growth_yoy",
    "QuarterlyRevenueGrowthYOY": "quarterly_revenue_growth_yoy",
    "AnalystTargetPrice": "analyst_target_price",
    "TrailingPE": "trailing_pe",
    "ForwardPE": "forward_pe",
    "PriceToSalesRatioTTM": "price_to_sales_ratio_ttm",
    "PriceToBookRatio": "price_to_book_ratio",
    "EVToRevenue": "ev_to_revenue",
    "EVToEBITDA": "ev_to_ebitda",
    "Beta": "beta",
    "52WeekHigh": "week_52_high",
    "52WeekLow": "week_52_low",
    "50DayMovingAverage": "day_50_moving_average",
    "200DayMovingAverage": "day_200_moving_average",
    "SharesOutstanding": "shares_outstanding",
}
CANONICAL_SECTORS = frozenset(
    {
        "COMMUNICATION SERVICES",
        "CONSUMER DISCRETIONARY",
        "CONSUMER STAPLES",
        "ENERGY",
        "FINANCIALS",
        "HEALTHCARE",
        "INDUSTRIALS",
        "MATERIALS",
        "REAL ESTATE",
        "TECHNOLOGY",
        "UTILITIES",
    }
)
SECTOR_ALIASES = {
    "BASIC MATERIALS": "MATERIALS",
    "COMMUNICATION SERVICES": "COMMUNICATION SERVICES",
    "COMMUNICATIONS EQUIPMENT": "TECHNOLOGY",
    "CONSUMER CYCLICAL": "CONSUMER DISCRETIONARY",
    "CONSUMER DEFENSIVE": "CONSUMER STAPLES",
    "FINANCIAL SERVICES": "FINANCIALS",
    "INFORMATION TECHNOLOGY": "TECHNOLOGY",
}
SECTOR_KEYWORD_RULES: tuple[tuple[str, str], ...] = (
    ("COMMUNICATIONS EQUIPMENT", "TECHNOLOGY"),
    ("INFORMATION TECHNOLOGY", "TECHNOLOGY"),
    ("SEMICONDUCT", "TECHNOLOGY"),
    ("SOFTWARE", "TECHNOLOGY"),
    ("ELECTRONIC", "TECHNOLOGY"),
    ("TECHNOLOGY", "TECHNOLOGY"),
    ("TELECOM", "COMMUNICATION SERVICES"),
    ("MEDIA", "COMMUNICATION SERVICES"),
    ("ENTERTAINMENT", "COMMUNICATION SERVICES"),
    ("COMMUNICATION", "COMMUNICATION SERVICES"),
    ("CONSUMER CYCLICAL", "CONSUMER DISCRETIONARY"),
    ("DISCRETIONARY", "CONSUMER DISCRETIONARY"),
    ("AUTO", "CONSUMER DISCRETIONARY"),
    ("LEISURE", "CONSUMER DISCRETIONARY"),
    ("TRAVEL", "CONSUMER DISCRETIONARY"),
    ("CONSUMER DEFENSIVE", "CONSUMER STAPLES"),
    ("STAPLES", "CONSUMER STAPLES"),
    ("GROCERY", "CONSUMER STAPLES"),
    ("PACKAGED FOOD", "CONSUMER STAPLES"),
    ("BEVERAGE", "CONSUMER STAPLES"),
    ("HOUSEHOLD", "CONSUMER STAPLES"),
    ("HEALTH", "HEALTHCARE"),
    ("PHARMA", "HEALTHCARE"),
    ("BIOTECH", "HEALTHCARE"),
    ("MEDICAL", "HEALTHCARE"),
    ("INSURANCE", "FINANCIALS"),
    ("BANK", "FINANCIALS"),
    ("FINANCIAL", "FINANCIALS"),
    ("ASSET MANAGEMENT", "FINANCIALS"),
    ("INVESTMENT", "FINANCIALS"),
    ("REAL ESTATE", "REAL ESTATE"),
    ("REIT", "REAL ESTATE"),
    ("INDUSTRIAL", "INDUSTRIALS"),
    ("AEROSPACE", "INDUSTRIALS"),
    ("TRANSPORT", "INDUSTRIALS"),
    ("DEFENSE", "INDUSTRIALS"),
    ("UTILITY", "UTILITIES"),
    ("UTILITIES", "UTILITIES"),
    ("ENERGY", "ENERGY"),
    ("OIL", "ENERGY"),
    ("GAS", "ENERGY"),
    ("MATERIAL", "MATERIALS"),
    ("CHEMICAL", "MATERIALS"),
    ("MINING", "MATERIALS"),
    ("ALUMINUM", "MATERIALS"),
    ("GOLD", "MATERIALS"),
    ("SILVER", "MATERIALS"),
    ("STEEL", "MATERIALS"),
)
LOW_QUALITY_SECTOR_LABELS = frozenset({"UNKNOWN", "OTHER", "UNCLASSIFIED"})
LOW_QUALITY_INDUSTRIES = frozenset({"UNKNOWN", "OTHER", "SHELL COMPANIES"})
NON_PRIMARY_SECURITY_NAME_PATTERN = re.compile(
    r"\b(WARRANTS?|UNITS?|RIGHTS?|PREFERRED|DEPOSITARY|NOTES?|BONDS?)\b",
    flags=re.IGNORECASE,
)
DEFAULT_CLIP_QUANTILE_LOWER = 0.01
DEFAULT_CLIP_QUANTILE_UPPER = 0.99
DEFAULT_MIN_ABS_EPS_BASE = 0.05


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze symbol fundamentals and sector EPS/surprise relationships "
            "from Alpha Vantage-style sp500_data JSON files."
        )
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root. Defaults to the repository root.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help=(
            "Directory containing *_overview.json and *_earnings.json files. "
            "Defaults to fundamentals/sp500_data when present, otherwise "
            "fundamentals_history/sp500_data."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated CSV/JSON analysis outputs.",
    )
    parser.add_argument(
        "--min-correlation-points",
        type=int,
        default=20,
        help="Minimum overlapping quarters required for sector correlations.",
    )
    parser.add_argument(
        "--clip-quantile-lower",
        type=float,
        default=DEFAULT_CLIP_QUANTILE_LOWER,
        help="Lower winsorization quantile applied to cleaned surprise and EPS growth series.",
    )
    parser.add_argument(
        "--clip-quantile-upper",
        type=float,
        default=DEFAULT_CLIP_QUANTILE_UPPER,
        help="Upper winsorization quantile applied to cleaned surprise and EPS growth series.",
    )
    parser.add_argument(
        "--min-abs-eps-base",
        type=float,
        default=DEFAULT_MIN_ABS_EPS_BASE,
        help=(
            "Minimum absolute estimated or prior EPS used before surprise and YoY growth "
            "percentages are treated as unstable and excluded from sector aggregates."
        ),
    )
    return parser.parse_args()


def _json_payload(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}") from exc


def _payload_data(path: Path) -> dict[str, Any]:
    payload = _json_payload(path)
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _symbol_from_path(path: Path, suffix: str) -> str:
    return path.name.removesuffix(suffix).upper()


def _clean_label(value: Any, default: str = "UNKNOWN") -> str:
    if value is None:
        return default
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "null", "-"}:
        return default
    return text.upper()


def _canonicalize_sector(sector_value: Any, industry_value: Any) -> tuple[str, str]:
    sector_raw = _clean_label(sector_value)
    industry_raw = _clean_label(industry_value)

    if sector_raw in CANONICAL_SECTORS:
        return sector_raw, "sector_direct"
    if sector_raw in SECTOR_ALIASES:
        return SECTOR_ALIASES[sector_raw], "sector_alias"
    if industry_raw in CANONICAL_SECTORS:
        return industry_raw, "industry_direct"
    if industry_raw in SECTOR_ALIASES:
        return SECTOR_ALIASES[industry_raw], "industry_alias"

    for label_name, label_value in (("sector", sector_raw), ("industry", industry_raw)):
        if label_value in LOW_QUALITY_SECTOR_LABELS:
            continue
        for keyword, canonical_sector in SECTOR_KEYWORD_RULES:
            if keyword in label_value:
                return canonical_sector, f"{label_name}_keyword"

    return "UNCLASSIFIED", "unclassified"


def _analysis_exclusion_reasons(
    *,
    name: Any,
    asset_type: Any,
    sector: str,
    industry: str,
) -> list[str]:
    reasons: list[str] = []
    if _clean_label(asset_type) != "COMMON STOCK":
        reasons.append("non_common_stock")
    if sector == "UNCLASSIFIED":
        reasons.append("unclassified_sector")
    if industry in LOW_QUALITY_INDUSTRIES:
        reasons.append("low_quality_industry")
    name_text = str(name or "")
    if NON_PRIMARY_SECURITY_NAME_PATTERN.search(name_text):
        reasons.append("non_primary_security_name")
    return reasons


def _to_float(value: Any) -> float:
    if value is None:
        return math.nan
    if isinstance(value, bool):
        return math.nan
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"none", "nan", "null", "n/a", "-", "--"}:
        return math.nan
    if text.endswith("%"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return math.nan


def _signed_pct_change(current: float, previous: float) -> float:
    if not np.isfinite(current) or not np.isfinite(previous) or abs(previous) < 1e-12:
        return math.nan
    return ((current - previous) / abs(previous)) * 100.0


def _weighted_average(values: pd.Series, weights: pd.Series) -> float:
    frame = pd.DataFrame({"value": values, "weight": weights}).replace([np.inf, -np.inf], np.nan).dropna()
    frame = frame[frame["weight"] > 0]
    if frame.empty:
        return float(values.replace([np.inf, -np.inf], np.nan).mean())
    return float(np.average(frame["value"], weights=frame["weight"]))


def _clip_outlier_series(
    series: pd.Series,
    *,
    lower_quantile: float,
    upper_quantile: float,
) -> tuple[pd.Series, pd.Series, dict[str, float | int | None]]:
    numeric = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
    finite = numeric.dropna()
    if finite.empty:
        empty_flag = pd.Series(False, index=series.index, dtype="bool")
        return numeric, empty_flag, {
            "eligible_rows": 0,
            "clipped_rows": 0,
            "lower_bound": None,
            "upper_bound": None,
        }

    lower_bound = float(finite.quantile(lower_quantile))
    upper_bound = float(finite.quantile(upper_quantile))
    clipped = numeric.clip(lower=lower_bound, upper=upper_bound)
    clipped_flag = numeric.notna() & ((numeric < lower_bound) | (numeric > upper_bound))
    return clipped, clipped_flag, {
        "eligible_rows": int(numeric.notna().sum()),
        "clipped_rows": int(clipped_flag.sum()),
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
    }


def _eligible_symbols(symbols: pd.DataFrame) -> pd.DataFrame:
    if symbols.empty or "eligible_for_sector_analysis" not in symbols.columns:
        return symbols
    return symbols[symbols["eligible_for_sector_analysis"]].copy()


def clean_earnings_outliers(
    annual: pd.DataFrame,
    quarterly: pd.DataFrame,
    *,
    lower_quantile: float = DEFAULT_CLIP_QUANTILE_LOWER,
    upper_quantile: float = DEFAULT_CLIP_QUANTILE_UPPER,
    min_abs_eps_base: float = DEFAULT_MIN_ABS_EPS_BASE,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    annual = annual.copy()
    quarterly = quarterly.copy()
    metadata: dict[str, Any] = {
        "lower_quantile": float(lower_quantile),
        "upper_quantile": float(upper_quantile),
        "min_abs_eps_base": float(min_abs_eps_base),
    }

    if not quarterly.empty:
        estimated_eps = pd.to_numeric(quarterly["estimated_eps"], errors="coerce").abs()
        quarterly["surprise_pct_low_estimate_flag"] = estimated_eps.notna() & estimated_eps.lt(min_abs_eps_base)
        quarterly["surprise_pct_raw"] = quarterly["surprise_pct"]
        cleaned_surprise_source = quarterly["surprise_pct_raw"].where(~quarterly["surprise_pct_low_estimate_flag"])
        quarterly["surprise_pct"], quarterly["surprise_pct_clipped_flag"], surprise_meta = _clip_outlier_series(
            cleaned_surprise_source,
            lower_quantile=lower_quantile,
            upper_quantile=upper_quantile,
        )
        metadata["surprise_pct"] = {
            **surprise_meta,
            "low_base_rows": int(quarterly["surprise_pct_low_estimate_flag"].sum()),
        }

        prior_year_eps = pd.to_numeric(quarterly["prior_year_reported_eps"], errors="coerce").abs()
        quarterly["quarterly_eps_yoy_low_base_flag"] = prior_year_eps.notna() & prior_year_eps.lt(min_abs_eps_base)
        quarterly["quarterly_eps_yoy_pct_raw"] = quarterly["quarterly_eps_yoy_pct"]
        cleaned_quarterly_yoy_source = quarterly["quarterly_eps_yoy_pct_raw"].where(
            ~quarterly["quarterly_eps_yoy_low_base_flag"]
        )
        (
            quarterly["quarterly_eps_yoy_pct"],
            quarterly["quarterly_eps_yoy_pct_clipped_flag"],
            quarterly_yoy_meta,
        ) = _clip_outlier_series(
            cleaned_quarterly_yoy_source,
            lower_quantile=lower_quantile,
            upper_quantile=upper_quantile,
        )
        metadata["quarterly_eps_yoy_pct"] = {
            **quarterly_yoy_meta,
            "low_base_rows": int(quarterly["quarterly_eps_yoy_low_base_flag"].sum()),
        }

    if not annual.empty:
        previous_annual_eps = pd.to_numeric(annual["previous_annual_reported_eps"], errors="coerce").abs()
        annual["annual_eps_yoy_low_base_flag"] = previous_annual_eps.notna() & previous_annual_eps.lt(min_abs_eps_base)
        annual["annual_eps_yoy_pct_raw"] = annual["annual_eps_yoy_pct"]
        cleaned_annual_yoy_source = annual["annual_eps_yoy_pct_raw"].where(~annual["annual_eps_yoy_low_base_flag"])
        annual["annual_eps_yoy_pct"], annual["annual_eps_yoy_pct_clipped_flag"], annual_yoy_meta = (
            _clip_outlier_series(
                cleaned_annual_yoy_source,
                lower_quantile=lower_quantile,
                upper_quantile=upper_quantile,
            )
        )
        metadata["annual_eps_yoy_pct"] = {
            **annual_yoy_meta,
            "low_base_rows": int(annual["annual_eps_yoy_low_base_flag"].sum()),
        }

    return annual, quarterly, metadata


def build_cleaning_summary(symbols: pd.DataFrame, clipping_metadata: dict[str, Any]) -> dict[str, Any]:
    eligible_symbols = _eligible_symbols(symbols)
    excluded_symbols = symbols[~symbols["eligible_for_sector_analysis"]].copy()

    excluded_reason_counts: dict[str, int] = {}
    for value in excluded_symbols.get("analysis_exclusion_reason", pd.Series(dtype="object")).dropna():
        for reason in str(value).split(";"):
            excluded_reason_counts[reason] = excluded_reason_counts.get(reason, 0) + 1

    return {
        "eligible_symbol_count": int(eligible_symbols["symbol"].nunique()) if not eligible_symbols.empty else 0,
        "excluded_symbol_count": int(excluded_symbols["symbol"].nunique()) if not excluded_symbols.empty else 0,
        "raw_sector_count": int(symbols["sector_raw"].nunique()) if "sector_raw" in symbols.columns else 0,
        "canonical_sector_count": int(eligible_symbols["sector"].nunique()) if not eligible_symbols.empty else 0,
        "excluded_reasons": dict(sorted(excluded_reason_counts.items(), key=lambda item: (-item[1], item[0]))),
        "sector_normalization_methods": symbols.get(
            "sector_normalization_method", pd.Series(dtype="object")
        ).value_counts().to_dict(),
        "raw_sector_labels": symbols.get("sector_raw", pd.Series(dtype="object")).value_counts().head(20).to_dict(),
        "clean_sector_labels": eligible_symbols.get("sector", pd.Series(dtype="object")).value_counts().to_dict(),
        "outlier_controls": clipping_metadata,
    }


def _resolve_data_dir(project_root: Path, data_dir: Path | None) -> Path:
    if data_dir is not None:
        path = data_dir if data_dir.is_absolute() else project_root / data_dir
        return path.resolve()

    candidates = (
        project_root / "fundamentals",
        project_root / "fundamentals_history",
        project_root / "fundamentals" / "sp500_data",
        project_root / "fundamentals_history" / "sp500_data",
    )
    for candidate in candidates:
        if candidate.exists() and any(candidate.glob("*_overview.json")):
            return candidate.resolve()

    return candidates[-1].resolve()


def load_overviews(data_dir: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path in sorted(data_dir.glob("*_overview.json")):
        data = _payload_data(path)
        symbol = str(data.get("Symbol") or _symbol_from_path(path, "_overview.json")).upper()
        sector_raw = _clean_label(data.get("Sector"))
        industry_raw = _clean_label(data.get("Industry"))
        sector, sector_normalization_method = _canonicalize_sector(sector_raw, industry_raw)
        exclusion_reasons = _analysis_exclusion_reasons(
            name=data.get("Name"),
            asset_type=data.get("AssetType"),
            sector=sector,
            industry=industry_raw,
        )
        row: dict[str, Any] = {
            "symbol": symbol,
            "name": data.get("Name"),
            "sector": sector,
            "sector_raw": sector_raw,
            "sector_normalization_method": sector_normalization_method,
            "industry": industry_raw,
            "industry_raw": industry_raw,
            "asset_type": data.get("AssetType"),
            "exchange": data.get("Exchange"),
            "currency": data.get("Currency"),
            "country": data.get("Country"),
            "fiscal_year_end": data.get("FiscalYearEnd"),
            "latest_quarter": data.get("LatestQuarter"),
            "eligible_for_sector_analysis": not exclusion_reasons,
            "analysis_exclusion_reason": ";".join(exclusion_reasons) if exclusion_reasons else None,
        }
        for source_name, output_name in NUMERIC_OVERVIEW_FIELDS.items():
            row[output_name] = _to_float(data.get(source_name))
        rows.append(row)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).drop_duplicates("symbol", keep="last")


def load_earnings(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    annual_rows: list[dict[str, Any]] = []
    quarterly_rows: list[dict[str, Any]] = []

    for path in sorted(data_dir.glob("*_earnings.json")):
        data = _payload_data(path)
        symbol = str(data.get("symbol") or _symbol_from_path(path, "_earnings.json")).upper()

        annual_earnings = data.get("annualEarnings")
        if isinstance(annual_earnings, list):
            for row in annual_earnings:
                if not isinstance(row, dict):
                    continue
                annual_rows.append(
                    {
                        "symbol": symbol,
                        "fiscal_date": row.get("fiscalDateEnding"),
                        "reported_eps": _to_float(row.get("reportedEPS")),
                    }
                )

        quarterly_earnings = data.get("quarterlyEarnings")
        if isinstance(quarterly_earnings, list):
            for row in quarterly_earnings:
                if not isinstance(row, dict):
                    continue
                reported_eps = _to_float(row.get("reportedEPS"))
                estimated_eps = _to_float(row.get("estimatedEPS"))
                surprise = _to_float(row.get("surprise"))
                surprise_pct = _to_float(row.get("surprisePercentage"))
                if not np.isfinite(surprise_pct) and np.isfinite(reported_eps) and np.isfinite(estimated_eps):
                    surprise_pct = _signed_pct_change(reported_eps, estimated_eps)
                quarterly_rows.append(
                    {
                        "symbol": symbol,
                        "fiscal_date": row.get("fiscalDateEnding"),
                        "reported_date": row.get("reportedDate"),
                        "reported_eps": reported_eps,
                        "estimated_eps": estimated_eps,
                        "surprise": surprise,
                        "surprise_pct": surprise_pct,
                        "report_time": row.get("reportTime"),
                    }
                )

    annual = pd.DataFrame(annual_rows)
    quarterly = pd.DataFrame(quarterly_rows)

    if not annual.empty:
        annual["fiscal_date"] = pd.to_datetime(annual["fiscal_date"], errors="coerce")
        annual = annual.dropna(subset=["symbol", "fiscal_date"]).sort_values(["symbol", "fiscal_date"])
        annual["fiscal_year"] = annual["fiscal_date"].dt.year
        annual["previous_annual_reported_eps"] = annual.groupby("symbol")["reported_eps"].shift(1)
        annual["annual_eps_yoy_pct"] = [
            _signed_pct_change(current, previous)
            for current, previous in zip(
                annual["reported_eps"],
                annual["previous_annual_reported_eps"],
                strict=False,
            )
        ]

    if not quarterly.empty:
        quarterly["fiscal_date"] = pd.to_datetime(quarterly["fiscal_date"], errors="coerce")
        quarterly["reported_date"] = pd.to_datetime(quarterly["reported_date"], errors="coerce")
        quarterly = quarterly.dropna(subset=["symbol", "fiscal_date"]).sort_values(["symbol", "fiscal_date"])
        quarterly["fiscal_quarter"] = quarterly["fiscal_date"].dt.to_period("Q").astype(str)
        quarterly["fiscal_year"] = quarterly["fiscal_date"].dt.year
        quarterly["quarter_number"] = quarterly["fiscal_date"].dt.quarter
        quarterly["beat_flag"] = quarterly["surprise"].gt(0)
        quarterly["prior_year_reported_eps"] = quarterly.groupby("symbol")["reported_eps"].shift(4)
        quarterly["quarterly_eps_yoy_pct"] = [
            _signed_pct_change(current, previous)
            for current, previous in zip(
                quarterly["reported_eps"],
                quarterly["prior_year_reported_eps"],
                strict=False,
            )
        ]
        quarterly["surprise_pct_raw"] = quarterly["surprise_pct"]

    return annual, quarterly


def build_symbol_summary(overviews: pd.DataFrame, annual: pd.DataFrame, quarterly: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if not overviews.empty:
        frames.append(overviews.set_index("symbol"))

    if not annual.empty:
        latest_annual = (
            annual.sort_values(["symbol", "fiscal_date"])
            .dropna(subset=["reported_eps"])
            .groupby("symbol")
            .tail(1)
            .set_index("symbol")
        )
        previous_annual = (
            annual.sort_values(["symbol", "fiscal_date"])
            .dropna(subset=["reported_eps"])
            .groupby("symbol")
            .nth(-2)
        )
        annual_summary = pd.DataFrame(index=latest_annual.index)
        annual_summary["latest_annual_fiscal_date"] = latest_annual["fiscal_date"]
        annual_summary["latest_annual_eps"] = latest_annual["reported_eps"]
        annual_summary["latest_annual_eps_yoy_pct"] = latest_annual["annual_eps_yoy_pct"]
        annual_summary["previous_annual_eps"] = previous_annual["reported_eps"]
        annual_summary["annual_eps_observations"] = annual.groupby("symbol")["reported_eps"].count()
        frames.append(annual_summary)

    if not quarterly.empty:
        latest_quarter = (
            quarterly.sort_values(["symbol", "fiscal_date"])
            .dropna(subset=["reported_eps"])
            .groupby("symbol")
            .tail(1)
            .set_index("symbol")
        )
        quarterly_group = quarterly.groupby("symbol")
        quarterly_summary = pd.DataFrame(index=quarterly_group.size().index)
        quarterly_summary["quarterly_earnings_observations"] = quarterly_group["reported_eps"].count()
        quarterly_summary["latest_quarter_fiscal_date"] = latest_quarter["fiscal_date"]
        quarterly_summary["latest_quarter_reported_date"] = latest_quarter["reported_date"]
        quarterly_summary["latest_quarter_reported_eps"] = latest_quarter["reported_eps"]
        quarterly_summary["latest_quarter_estimated_eps"] = latest_quarter["estimated_eps"]
        quarterly_summary["latest_quarter_surprise"] = latest_quarter["surprise"]
        quarterly_summary["latest_quarter_surprise_pct"] = latest_quarter["surprise_pct"]
        quarterly_summary["latest_quarter_eps_yoy_pct"] = latest_quarter["quarterly_eps_yoy_pct"]
        quarterly_summary["avg_surprise_pct"] = quarterly_group["surprise_pct"].mean()
        quarterly_summary["median_surprise_pct"] = quarterly_group["surprise_pct"].median()
        quarterly_summary["surprise_pct_volatility"] = quarterly_group["surprise_pct"].std()
        quarterly_summary["beat_rate"] = quarterly_group["beat_flag"].mean()
        frames.append(quarterly_summary)

    if not frames:
        return pd.DataFrame()

    summary = pd.concat(frames, axis=1).reset_index(names="symbol")
    summary = summary.sort_values(["sector", "symbol"] if "sector" in summary.columns else ["symbol"])
    return summary


def build_sector_summary(symbols: pd.DataFrame) -> pd.DataFrame:
    eligible_symbols = _eligible_symbols(symbols)
    if eligible_symbols.empty or "sector" not in eligible_symbols.columns:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    metric_columns = [
        "avg_surprise_pct",
        "median_surprise_pct",
        "latest_quarter_surprise_pct",
        "latest_quarter_eps_yoy_pct",
        "latest_annual_eps_yoy_pct",
        "quarterly_earnings_growth_yoy",
        "quarterly_revenue_growth_yoy",
        "eps_ttm",
        "pe_ratio",
        "forward_pe",
        "peg_ratio",
        "profit_margin",
        "operating_margin_ttm",
        "return_on_equity_ttm",
        "return_on_assets_ttm",
        "beta",
    ]

    for sector, group in eligible_symbols.groupby("sector", dropna=False):
        row: dict[str, Any] = {
            "sector": sector,
            "symbol_count": int(group["symbol"].nunique()),
            "market_cap_total": group.get("market_cap", pd.Series(dtype="float64")).sum(min_count=1),
            "market_cap_median": group.get("market_cap", pd.Series(dtype="float64")).median(),
            "beat_rate_avg": group.get("beat_rate", pd.Series(dtype="float64")).mean(),
            "surprise_pct_volatility_median": group.get(
                "surprise_pct_volatility", pd.Series(dtype="float64")
            ).median(),
        }
        market_cap = group.get("market_cap", pd.Series(np.nan, index=group.index))
        for column in metric_columns:
            if column not in group.columns:
                continue
            row[f"{column}_mean"] = group[column].mean()
            row[f"{column}_median"] = group[column].median()
            row[f"{column}_cap_weighted"] = _weighted_average(group[column], market_cap)
        rows.append(row)

    return pd.DataFrame(rows).sort_values("market_cap_total", ascending=False, na_position="last")


def attach_sector(frame: pd.DataFrame, symbols: pd.DataFrame, *, eligible_only: bool = False) -> pd.DataFrame:
    if frame.empty or symbols.empty:
        return frame
    sector_map = symbols[
        [
            "symbol",
            "sector",
            "sector_raw",
            "industry",
            "market_cap",
            "eligible_for_sector_analysis",
            "analysis_exclusion_reason",
        ]
    ].drop_duplicates("symbol")
    if eligible_only:
        sector_map = sector_map[sector_map["eligible_for_sector_analysis"]]
    return frame.merge(sector_map, on="symbol", how="left")


def build_quarterly_sector_series(quarterly: pd.DataFrame, symbols: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if quarterly.empty:
        return pd.DataFrame(), pd.DataFrame()

    enriched = attach_sector(quarterly, symbols, eligible_only=True)
    enriched = enriched.dropna(subset=["sector", "fiscal_quarter"])
    if enriched.empty:
        return pd.DataFrame(), pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for (sector, quarter), group in enriched.groupby(["sector", "fiscal_quarter"]):
        row = {
            "sector": sector,
            "fiscal_quarter": quarter,
            "symbol_count": int(group["symbol"].nunique()),
            "avg_surprise_pct": group["surprise_pct"].mean(),
            "median_surprise_pct": group["surprise_pct"].median(),
            "cap_weighted_surprise_pct": _weighted_average(group["surprise_pct"], group["market_cap"]),
            "beat_rate": group["beat_flag"].mean(),
            "avg_reported_eps": group["reported_eps"].mean(),
            "avg_estimated_eps": group["estimated_eps"].mean(),
            "avg_quarterly_eps_yoy_pct": group["quarterly_eps_yoy_pct"].mean(),
            "cap_weighted_quarterly_eps_yoy_pct": _weighted_average(
                group["quarterly_eps_yoy_pct"], group["market_cap"]
            ),
        }
        rows.append(row)

    sector_quarterly = pd.DataFrame(rows).sort_values(["sector", "fiscal_quarter"])

    eps_growth = (
        sector_quarterly[
            [
                "sector",
                "fiscal_quarter",
                "symbol_count",
                "avg_quarterly_eps_yoy_pct",
                "cap_weighted_quarterly_eps_yoy_pct",
            ]
        ]
        .dropna(subset=["avg_quarterly_eps_yoy_pct"], how="all")
        .copy()
    )
    return sector_quarterly, eps_growth


def _correlation_matrix(series: pd.DataFrame, min_periods: int) -> pd.DataFrame:
    if series.empty:
        return pd.DataFrame()
    matrix = series.corr(min_periods=min_periods).sort_index().reindex(sorted(series.columns), axis=1)
    matrix.index.name = "sector"
    return matrix


def build_same_period_correlation_pairs(series: pd.DataFrame, min_points: int) -> pd.DataFrame:
    if series.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    sectors = list(series.columns)
    for index, source in enumerate(sectors):
        for target in sectors[index + 1 :]:
            pair = series[[source, target]].dropna()
            if len(pair) < min_points:
                continue
            correlation = pair[source].corr(pair[target])
            rows.append(
                {
                    "source_sector": source,
                    "target_sector": target,
                    "relationship": "same_quarter",
                    "correlation": correlation,
                    "overlap_quarters": int(len(pair)),
                    "abs_correlation": abs(correlation),
                }
            )

    table = pd.DataFrame(rows)
    if table.empty:
        return table
    return table.sort_values(["abs_correlation", "overlap_quarters"], ascending=[False, False])


def build_lead_lag_table(series: pd.DataFrame, min_points: int) -> pd.DataFrame:
    if series.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    sectors = list(series.columns)
    for source in sectors:
        for target in sectors:
            if source == target:
                continue
            pair = pd.DataFrame(
                {
                    "source": series[source],
                    "target_next_quarter": series[target].shift(-1),
                    "target_previous_quarter": series[target].shift(1),
                }
            )
            lead_pair = pair[["source", "target_next_quarter"]].dropna()
            lag_pair = pair[["source", "target_previous_quarter"]].dropna()
            if len(lead_pair) >= min_points:
                rows.append(
                    {
                        "source_sector": source,
                        "target_sector": target,
                        "relationship": "source_surprise_leads_target_by_1q",
                        "correlation": lead_pair["source"].corr(lead_pair["target_next_quarter"]),
                        "overlap_quarters": int(len(lead_pair)),
                    }
                )
            if len(lag_pair) >= min_points:
                rows.append(
                    {
                        "source_sector": source,
                        "target_sector": target,
                        "relationship": "source_surprise_lags_target_by_1q",
                        "correlation": lag_pair["source"].corr(lag_pair["target_previous_quarter"]),
                        "overlap_quarters": int(len(lag_pair)),
                    }
                )

    table = pd.DataFrame(rows)
    if table.empty:
        return table
    table["abs_correlation"] = table["correlation"].abs()
    return table.sort_values(["abs_correlation", "overlap_quarters"], ascending=[False, False])


def build_sector_metric_correlation(sector_summary: pd.DataFrame) -> pd.DataFrame:
    if sector_summary.empty:
        return pd.DataFrame()

    candidate_columns = [
        "avg_surprise_pct_cap_weighted",
        "latest_quarter_surprise_pct_cap_weighted",
        "latest_quarter_eps_yoy_pct_cap_weighted",
        "latest_annual_eps_yoy_pct_cap_weighted",
        "quarterly_earnings_growth_yoy_cap_weighted",
        "quarterly_revenue_growth_yoy_cap_weighted",
        "beat_rate_avg",
        "profit_margin_cap_weighted",
        "return_on_equity_ttm_cap_weighted",
        "pe_ratio_cap_weighted",
        "forward_pe_cap_weighted",
        "beta_cap_weighted",
    ]
    columns = [column for column in candidate_columns if column in sector_summary.columns]
    if len(columns) < 2:
        return pd.DataFrame()
    frame = sector_summary.set_index("sector")[columns]
    matrix = frame.corr(min_periods=3)
    matrix.index.name = "metric"
    return matrix


def _write_csv(frame: pd.DataFrame, path: Path, *, index: bool = False) -> None:
    if frame.empty:
        path.write_text("", encoding="utf-8")
        return
    frame.to_csv(path, index=index)


def write_outputs(
    output_dir: Path,
    data_dir: Path,
    overviews: pd.DataFrame,
    annual: pd.DataFrame,
    quarterly: pd.DataFrame,
    symbols: pd.DataFrame,
    sector_summary: pd.DataFrame,
    sector_quarterly: pd.DataFrame,
    sector_eps_growth: pd.DataFrame,
    surprise_corr: pd.DataFrame,
    surprise_corr_pairs: pd.DataFrame,
    surprise_lead_lag: pd.DataFrame,
    eps_growth_corr: pd.DataFrame,
    eps_growth_corr_pairs: pd.DataFrame,
    sector_metric_corr: pd.DataFrame,
    cleaning_summary: dict[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    enriched_quarterly = attach_sector(quarterly, symbols)
    enriched_annual = attach_sector(annual, symbols)
    eligible_symbols = _eligible_symbols(symbols)
    excluded_symbols = symbols[~symbols["eligible_for_sector_analysis"]].copy()

    _write_csv(overviews, output_dir / "symbol_overviews.csv")
    _write_csv(enriched_annual, output_dir / "symbol_annual_earnings.csv")
    _write_csv(enriched_quarterly, output_dir / "symbol_quarterly_earnings.csv")
    _write_csv(symbols, output_dir / "symbol_fundamentals.csv")
    _write_csv(eligible_symbols, output_dir / "sector_analysis_eligible_symbols.csv")
    _write_csv(excluded_symbols, output_dir / "sector_analysis_excluded_symbols.csv")
    _write_csv(sector_summary, output_dir / "sector_fundamentals_summary.csv")
    _write_csv(sector_quarterly, output_dir / "sector_quarterly_surprise.csv")
    _write_csv(sector_eps_growth, output_dir / "sector_quarterly_eps_growth.csv")
    _write_csv(surprise_corr, output_dir / "sector_surprise_correlation.csv", index=True)
    _write_csv(surprise_corr_pairs, output_dir / "sector_surprise_correlation_pairs.csv")
    _write_csv(surprise_lead_lag, output_dir / "sector_surprise_lead_lag.csv")
    _write_csv(eps_growth_corr, output_dir / "sector_eps_growth_correlation.csv", index=True)
    _write_csv(eps_growth_corr_pairs, output_dir / "sector_eps_growth_correlation_pairs.csv")
    _write_csv(sector_metric_corr, output_dir / "sector_metric_correlation.csv", index=True)

    latest_sector_snapshot = (
        sector_summary[
            [
                column
                for column in (
                    "sector",
                    "symbol_count",
                    "avg_surprise_pct_cap_weighted",
                    "latest_quarter_surprise_pct_cap_weighted",
                    "latest_quarter_eps_yoy_pct_cap_weighted",
                    "quarterly_revenue_growth_yoy_cap_weighted",
                    "beat_rate_avg",
                )
                if column in sector_summary.columns
            ]
        ]
        .head(20)
        .replace({np.nan: None})
        .to_dict(orient="records")
    )

    top_lead_lag = (
        surprise_lead_lag.head(20).replace({np.nan: None}).to_dict(orient="records")
        if not surprise_lead_lag.empty
        else []
    )
    top_same_quarter_surprise = (
        surprise_corr_pairs.head(20).replace({np.nan: None}).to_dict(orient="records")
        if not surprise_corr_pairs.empty
        else []
    )
    top_same_quarter_eps_growth = (
        eps_growth_corr_pairs.head(20).replace({np.nan: None}).to_dict(orient="records")
        if not eps_growth_corr_pairs.empty
        else []
    )
    output_names = sorted(path.name for path in output_dir.glob("*"))
    if "fundamentals_analysis_summary.json" not in output_names:
        output_names.append("fundamentals_analysis_summary.json")
        output_names.sort()

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "data_dir": str(data_dir),
        "output_dir": str(output_dir),
        "overview_symbols": int(overviews["symbol"].nunique()) if not overviews.empty else 0,
        "eligible_symbols": int(eligible_symbols["symbol"].nunique()) if not eligible_symbols.empty else 0,
        "excluded_symbols": int(excluded_symbols["symbol"].nunique()) if not excluded_symbols.empty else 0,
        "annual_earnings_rows": int(len(annual)),
        "quarterly_earnings_rows": int(len(quarterly)),
        "sector_count": int(sector_summary["sector"].nunique()) if not sector_summary.empty else 0,
        "quarters_analyzed": int(sector_quarterly["fiscal_quarter"].nunique()) if not sector_quarterly.empty else 0,
        "cleaning": cleaning_summary,
        "latest_sector_snapshot": latest_sector_snapshot,
        "strongest_same_quarter_surprise_relationships": top_same_quarter_surprise,
        "strongest_same_quarter_eps_growth_relationships": top_same_quarter_eps_growth,
        "strongest_surprise_lead_lag_relationships": top_lead_lag,
        "outputs": output_names,
    }
    (output_dir / "fundamentals_analysis_summary.json").write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )
    return summary


def run_analysis(
    project_root: Path | None = None,
    data_dir: Path | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    min_correlation_points: int = 20,
    clip_quantile_lower: float = DEFAULT_CLIP_QUANTILE_LOWER,
    clip_quantile_upper: float = DEFAULT_CLIP_QUANTILE_UPPER,
    min_abs_eps_base: float = DEFAULT_MIN_ABS_EPS_BASE,
) -> dict[str, Any]:
    if not 0.0 <= clip_quantile_lower < clip_quantile_upper <= 1.0:
        raise ValueError("clip quantiles must satisfy 0 <= lower < upper <= 1")

    root = resolve_project_root(project_root)
    resolved_data_dir = _resolve_data_dir(root, data_dir)
    resolved_output_dir = output_dir if output_dir.is_absolute() else root / output_dir

    if not resolved_data_dir.exists():
        raise FileNotFoundError(f"Fundamentals data directory not found: {resolved_data_dir}")

    overviews = load_overviews(resolved_data_dir)
    annual, quarterly = load_earnings(resolved_data_dir)
    annual, quarterly, clipping_metadata = clean_earnings_outliers(
        annual,
        quarterly,
        lower_quantile=clip_quantile_lower,
        upper_quantile=clip_quantile_upper,
        min_abs_eps_base=min_abs_eps_base,
    )
    symbols = build_symbol_summary(overviews, annual, quarterly)
    sector_summary = build_sector_summary(symbols)
    sector_quarterly, sector_eps_growth = build_quarterly_sector_series(quarterly, symbols)
    cleaning_summary = build_cleaning_summary(symbols, clipping_metadata)

    surprise_pivot = pd.DataFrame()
    if not sector_quarterly.empty:
        surprise_pivot = sector_quarterly.pivot(
            index="fiscal_quarter",
            columns="sector",
            values="cap_weighted_surprise_pct",
        ).sort_index()
    surprise_corr = _correlation_matrix(surprise_pivot, min_correlation_points)
    surprise_corr_pairs = build_same_period_correlation_pairs(surprise_pivot, min_correlation_points)
    surprise_lead_lag = build_lead_lag_table(surprise_pivot, min_correlation_points)

    eps_growth_pivot = pd.DataFrame()
    if not sector_eps_growth.empty:
        eps_growth_pivot = sector_eps_growth.pivot(
            index="fiscal_quarter",
            columns="sector",
            values="cap_weighted_quarterly_eps_yoy_pct",
        ).sort_index()
    eps_growth_corr = _correlation_matrix(eps_growth_pivot, min_correlation_points)
    eps_growth_corr_pairs = build_same_period_correlation_pairs(eps_growth_pivot, min_correlation_points)
    sector_metric_corr = build_sector_metric_correlation(sector_summary)

    return write_outputs(
        resolved_output_dir,
        resolved_data_dir,
        overviews,
        annual,
        quarterly,
        symbols,
        sector_summary,
        sector_quarterly,
        sector_eps_growth,
        surprise_corr,
        surprise_corr_pairs,
        surprise_lead_lag,
        eps_growth_corr,
        eps_growth_corr_pairs,
        sector_metric_corr,
        cleaning_summary,
    )


def main() -> None:
    args = parse_args()
    summary = run_analysis(
        project_root=args.project_root,
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        min_correlation_points=args.min_correlation_points,
        clip_quantile_lower=args.clip_quantile_lower,
        clip_quantile_upper=args.clip_quantile_upper,
        min_abs_eps_base=args.min_abs_eps_base,
    )

    print(f"Wrote fundamentals analysis to {summary['output_dir']}")
    print(
        "Analyzed "
        f"{summary['overview_symbols']} symbols, "
        f"{summary['sector_count']} sectors, "
        f"{summary['quarterly_earnings_rows']} quarterly earnings rows."
    )


if __name__ == "__main__":
    main()
