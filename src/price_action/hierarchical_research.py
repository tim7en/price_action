"""Canonical monthly research panels for hierarchical sector selection.

This module is the contract between the repository's macro/regime, sector,
company-quality, and trend studies.  It intentionally does not fit a model:
the first requirement for a defensible ensemble is one audited definition of
signal time, feature availability, forward targets, and walk-forward folds.

Run with::

    python build_hierarchical_research.py
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .data import resolve_project_root
from .momentum_oscillator import momentum_oscillator
from .quality_engine import FWD_DAYS, SECTOR_SPECIFICATION, load_close
from .sector_dalio_regime_model import (
    EARNINGS_FUNDAMENTAL_FEATURES,
    SECTOR_ETF_MAP,
    TARGET_COLUMNS,
    build_live_etf_overlay_panel,
    _feature_family,
    _is_excluded_predictive_feature,
)

OUTPUT_DIR = Path("outputs") / "hierarchical_research"
SECTOR_PANEL_PATH = Path("outputs") / "sector_dalio_regime_model" / "sector_regime_panel.csv"
QUALITY_DIR = Path("outputs") / "quality_engine"
HOLDINGS_PATH = Path("data") / "sector_top_holdings.csv"
HOLDOUT_START = "2025-01-01"
MIN_TRAIN_YEARS = {"macro": 8, "sector": 8, "company": 8}
TARGET_HORIZONS = {"macro": 3, "sector": 6, "company": 6}

BOOK_PARENT_SECTOR = {
    "XLB": "Materials",
    "XLC": "Communication Svcs",
    "XLE": "Energy",
    "XLF": "Financials",
    "XLI": "Industrials",
    "XLK": "Technology",
    "XLP": "Consumer Defensive",
    "XLRE": "Real Estate",
    "XLU": "Utilities",
    "XLV": "Health Care",
    "XLY": "Consumer Cyclical",
    "SEMIS": "Technology",
}
SECTOR_TO_ETF = {sector: etf for sector, etf in SECTOR_ETF_MAP.items()}

SECTOR_PRICE_FEATURES = [
    "sector_return_1m",
    "sector_return_3m",
    "sector_return_6m",
    "sector_return_12m",
    "relative_return_1m",
    "relative_return_3m",
    "relative_return_6m",
    "relative_return_12m",
    "sector_oscillator",
    "relative_oscillator",
    "above_slow_ma",
    "fast_slow_gap",
    "slow_ma_gap",
    "volatility_12m",
    "drawdown_12m",
    "drawdown_36m",
    "relative_volatility_12m",
    "beta_36m",
    "corr_36m",
    "last_cross_type",
    "months_since_cross",
    "move_since_last_cross",
    "young_cross_risk",
]

PAPER = "#f4ecd3"
GRID_MAJOR = "#c8a24b"
GRID_MINOR = "#dbc17b"
INK = "#2e2417"
INK_MUTED = "#6b5d40"
INK_NAVY = "#2e62a8"
INK_RED = "#b53517"
INK_GREEN = "#1f7a52"
INK_AMBER = "#c07f1f"


@dataclass
class BuildResult:
    macro: pd.DataFrame
    sector: pd.DataFrame
    company: pd.DataFrame
    registry: pd.DataFrame
    splits: pd.DataFrame
    audit: pd.DataFrame
    coverage: pd.DataFrame
    output_dir: Path


def _write_progress(
    output_dir: Path,
    *,
    step: int,
    total: int,
    stage: str,
    message: str,
    status: str = "running",
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "step": step,
        "total_steps": total,
        "progress_pct": round(step / total * 100.0, 1),
        "stage": stage,
        "message": message,
        "updated_at_utc": datetime.now(UTC).isoformat(),
    }
    (output_dir / "progress.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[{step}/{total}] {message}")


def _month_end_offset(series: pd.Series, months: int) -> pd.Series:
    return pd.to_datetime(series) + pd.offsets.MonthEnd(months)


def _evaluation_fold(date: pd.Series, first_validation_year: int, holdout_start: pd.Timestamp) -> pd.Series:
    date = pd.to_datetime(date)
    out = pd.Series("initial_training", index=date.index, dtype="object")
    validation = (date.dt.year >= first_validation_year) & (date < holdout_start)
    out.loc[validation] = "validation_" + date.loc[validation].dt.year.astype(str)
    out.loc[date >= holdout_start] = "holdout"
    return out


def load_sector_contract(root: Path, holdout_start: pd.Timestamp) -> pd.DataFrame:
    # The trained and live sector models must see the same instruments.  The
    # old contract trained on reconstructed stock-sector indices and predicted
    # live sector ETFs, a domain shift that its walk-forward results did not
    # validate.  Build the full contract directly from the ETF cache instead.
    panel, _macro_bundle, latest_trade_date = build_live_etf_overlay_panel(root, fast=3, slow=10)
    if panel.empty or not latest_trade_date:
        raise FileNotFoundError(
            "Historical sector ETF cache is incomplete. Refresh cache/advise before building the hierarchy."
        )

    latest_trade = pd.Timestamp(latest_trade_date).normalize()
    today = pd.Timestamp.now().normalize()
    latest_period = latest_trade.to_period("M")
    completed_period = today.to_period("M") - 1 if latest_period == today.to_period("M") else latest_period
    completed_month_end = completed_period.to_timestamp("M")
    panel = panel.loc[pd.to_datetime(panel["date"]) <= completed_month_end].copy()
    panel["price_source"] = "sector_etf_adjusted_close"

    panel = panel.sort_values(["sector", "date"]).reset_index(drop=True)
    panel["fwd_6m"] = panel.groupby("sector", sort=False)["sector_index"].transform(
        lambda values: values.shift(-6) / values - 1.0
    )
    broad_monthly_return = (
        panel.assign(
            broad_return=pd.to_numeric(panel["sector_return_1m"], errors="coerce")
            - pd.to_numeric(panel["relative_return_1m"], errors="coerce")
        )
        .groupby("date", sort=True)["broad_return"]
        .median()
    )
    broad_level = (1.0 + broad_monthly_return.fillna(0.0)).cumprod()
    broad_fwd_6m = broad_level.shift(-6) / broad_level - 1.0
    panel["fwd_6m_broad"] = panel["date"].map(broad_fwd_6m)
    panel["fwd_6m_excess"] = panel["fwd_6m"] - panel["fwd_6m_broad"]
    count_by_date = panel.groupby("date")["fwd_6m_excess"].transform("count")
    panel["leader_rank_pct"] = panel.groupby("date")["fwd_6m_excess"].rank(pct=True)
    panel["target_leader"] = (
        panel["leader_rank_pct"].ge(2.0 / 3.0)
        .where(panel["fwd_6m_excess"].notna() & count_by_date.ge(6))
        .astype("float64")
    )

    panel = panel.sort_values(["date", "sector"]).reset_index(drop=True)
    panel.insert(1, "signal_date", panel["date"])
    panel.insert(3, "sector_etf", panel["sector"].map(SECTOR_TO_ETF))
    panel["target_end_date_6m"] = _month_end_offset(panel["date"], 6)
    first_year = int(panel["date"].dt.year.min()) + MIN_TRAIN_YEARS["sector"]
    panel["evaluation_fold"] = _evaluation_fold(panel["date"], first_year, holdout_start)
    panel["source_contract"] = "sector_dalio_regime_model"
    return panel


def _macro_columns(sector: pd.DataFrame) -> list[str]:
    columns: list[str] = []
    for column in sector.columns:
        family = _feature_family(column)
        if family in {"macro_nowcast", "forward_macro"}:
            columns.append(column)
    for column in [
        "dalio_quadrant",
        "gmm_regime",
        "growth_signal",
        "inflation_signal",
        "market_health",
        "sector_breadth",
    ]:
        if column in sector.columns and column not in columns:
            columns.append(column)
    return columns


def build_macro_contract(sector: pd.DataFrame, holdout_start: pd.Timestamp) -> pd.DataFrame:
    columns = _macro_columns(sector)
    source = sector[["date", *columns]].sort_values("date")
    numeric = [column for column in columns if pd.api.types.is_numeric_dtype(source[column])]
    consistency = source.groupby("date")[numeric].nunique(dropna=False).max() if numeric else pd.Series(dtype=float)
    if len(consistency) and consistency.max() > 1:
        raise ValueError("Macro values differ across sectors for the same signal month.")

    macro = source.drop_duplicates("date", keep="first").reset_index(drop=True)
    macro.insert(1, "signal_date", macro["date"])
    macro["target_end_date_3m"] = _month_end_offset(macro["date"], 3)
    macro["target_next_quadrant_3m"] = macro["dalio_quadrant"].shift(-3)
    macro["target_regime_change_3m"] = (
        macro["target_next_quadrant_3m"].ne(macro["dalio_quadrant"])
        .where(macro["target_next_quadrant_3m"].notna())
        .astype("float64")
    )
    macro["target_growth_signal_3m"] = macro["growth_signal"].shift(-3)
    macro["target_inflation_signal_3m"] = macro["inflation_signal"].shift(-3)
    first_year = int(macro["date"].dt.year.min()) + MIN_TRAIN_YEARS["macro"]
    macro["evaluation_fold"] = _evaluation_fold(macro["date"], first_year, holdout_start)
    macro["source_contract"] = "publication-lagged macro bundle"
    return macro


def _load_sector_etf_daily(root: Path, sector: str) -> pd.Series:
    symbol = SECTOR_TO_ETF[sector]
    path = root / "cache" / "advise" / f"{symbol}_daily.csv"
    if not path.exists():
        raise FileNotFoundError(f"Parent-sector ETF cache is missing: {path}")
    frame = pd.read_csv(path, parse_dates=["date"])
    close = pd.Series(
        pd.to_numeric(frame["close"], errors="coerce").to_numpy(),
        index=pd.to_datetime(frame["date"]).dt.normalize(),
        name=symbol,
    )
    return close[~close.index.duplicated(keep="last")].dropna().sort_index()


def _asof_series(series: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    union = series.index.union(dates)
    return series.reindex(union).sort_index().ffill().reindex(dates)


def _forward_trade_frame(price: pd.Series, dates: pd.DatetimeIndex) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for date in dates:
        entry_pos = int(price.index.searchsorted(date, side="right"))
        exit_pos = entry_pos + FWD_DAYS
        if entry_pos >= len(price) or exit_pos >= len(price):
            rows.append({"date": date, "entry_date": pd.NaT, "target_end_date": pd.NaT, "return": np.nan})
            continue
        rows.append(
            {
                "date": date,
                "entry_date": price.index[entry_pos],
                "target_end_date": price.index[exit_pos],
                "return": float(price.iloc[exit_pos] / price.iloc[entry_pos] - 1.0),
            }
        )
    return pd.DataFrame(rows).set_index("date")


def _run_age(state: pd.Series) -> pd.Series:
    groups = state.ne(state.shift()).cumsum()
    return state.groupby(groups).cumcount().astype(float)


def _company_price_features(
    *,
    stock: pd.Series,
    parent: pd.Series,
    dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    stock_monthly = _asof_series(stock, dates)
    parent_monthly = _asof_series(parent, dates)
    relative = stock_monthly / parent_monthly

    out = pd.DataFrame(index=dates)
    for horizon in (1, 3, 6, 12):
        out[f"company_return_{horizon}m"] = stock_monthly / stock_monthly.shift(horizon) - 1.0
        out[f"company_relative_return_{horizon}m"] = relative / relative.shift(horizon) - 1.0
    out["company_oscillator"] = momentum_oscillator(stock_monthly)
    out["company_relative_oscillator"] = momentum_oscillator(relative)
    out["company_drawdown_12m"] = stock_monthly / stock_monthly.rolling(12, min_periods=6).max() - 1.0

    stock_daily = stock.reindex(stock.index.union(parent.index)).sort_index().ffill()
    parent_daily = parent.reindex(stock_daily.index).ffill()
    stock_return = stock_daily.pct_change(fill_method=None)
    parent_return = parent_daily.pct_change(fill_method=None)
    sma50 = stock_daily.rolling(50, min_periods=50).mean()
    sma200 = stock_daily.rolling(200, min_periods=200).mean()
    daily = pd.DataFrame(index=stock_daily.index)
    daily["company_sma50_200_gap"] = sma50 / sma200 - 1.0
    daily["company_price_sma200_gap"] = stock_daily / sma200 - 1.0
    daily["company_volatility_63d"] = stock_return.rolling(63, min_periods=42).std() * np.sqrt(252.0)
    daily["company_beta_252d"] = (
        stock_return.rolling(252, min_periods=126).cov(parent_return)
        / parent_return.rolling(252, min_periods=126).var().replace(0.0, np.nan)
    )
    daily = daily.reindex(daily.index.union(dates)).sort_index().ffill().reindex(dates)
    out = out.join(daily)
    valid_state = out["company_sma50_200_gap"].notna()
    out["company_50_200_state"] = np.where(
        ~valid_state,
        None,
        np.where(out["company_sma50_200_gap"] >= 0.0, "golden", "death"),
    )
    out["company_50_200_age_months"] = _run_age(out["company_50_200_state"])
    out["company_50_200_cross"] = out["company_50_200_state"].where(
        out["company_50_200_state"].ne(out["company_50_200_state"].shift()) & valid_state
    )

    stock_fwd = _forward_trade_frame(stock, dates).add_prefix("company_")
    parent_fwd = _forward_trade_frame(parent, dates).add_prefix("parent_")
    out = out.join(stock_fwd).join(parent_fwd)
    out["target_company_fwd_6m"] = out.pop("company_return")
    out["target_parent_sector_fwd_6m"] = out.pop("parent_return")
    aligned_window = (
        out["company_entry_date"].eq(out["parent_entry_date"])
        & out["company_target_end_date"].eq(out["parent_target_end_date"])
    )
    out["target_company_residual_6m"] = (
        out["target_company_fwd_6m"] - out["target_parent_sector_fwd_6m"]
    ).where(aligned_window)
    out["target_end_date_6m"] = pd.concat(
        [out["company_target_end_date"], out["parent_target_end_date"]], axis=1
    ).max(axis=1)
    out["entry_date"] = pd.concat(
        [out["company_entry_date"], out["parent_entry_date"]], axis=1
    ).max(axis=1)
    out.index.name = "date"
    return out


def _load_quality_panels(root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for book in SECTOR_SPECIFICATION:
        path = root / QUALITY_DIR / f"{book}_panel.csv"
        if not path.exists():
            raise FileNotFoundError(f"Quality panel is missing: {path}")
        frame = pd.read_csv(path, parse_dates=["date"])
        frame.insert(1, "book", book)
        frame.insert(2, "book_specification", SECTOR_SPECIFICATION[book])
        frame.insert(3, "parent_sector", BOOK_PARENT_SECTOR[book])
        frames.append(frame)
    quality = pd.concat(frames, ignore_index=True, sort=False)
    if quality.duplicated(["date", "book", "ticker"]).any():
        raise ValueError("Quality panels have duplicate date/book/ticker keys.")
    return quality.sort_values(["date", "book", "ticker"]).reset_index(drop=True)


def _apply_membership_flags(root: Path, company: pd.DataFrame) -> pd.DataFrame:
    holdings = pd.read_csv(
        root / HOLDINGS_PATH,
        parse_dates=["as_of_date", "known_from_date"],
    ).sort_values(["sector_symbol", "known_from_date", "holding_symbol"])
    company["membership_basis"] = "unavailable_before_first_nport_snapshot"
    company["membership_snapshot_asof"] = pd.NaT
    company["membership_known_from"] = pd.NaT
    company["pit_member"] = pd.Series(pd.NA, index=company.index, dtype="boolean")

    semis = company["book"].eq("SEMIS")
    company.loc[semis, "membership_basis"] = "dedicated_static_industry_book"

    for book in sorted(set(company["book"]) - {"SEMIS"}):
        snapshots = holdings.loc[holdings["sector_symbol"].eq(book)]
        if snapshots.empty:
            continue
        book_rows = company.index[company["book"].eq(book)]
        for date, date_index in company.loc[book_rows].groupby("date").groups.items():
            known = snapshots.loc[snapshots["known_from_date"] <= date]
            if known.empty:
                continue
            known_from = known["known_from_date"].max()
            snapshot = known.loc[known["known_from_date"].eq(known_from)]
            members = set(snapshot["holding_symbol"].astype(str))
            company.loc[date_index, "membership_basis"] = "sec_nport_point_in_time_top10"
            company.loc[date_index, "membership_snapshot_asof"] = snapshot["as_of_date"].max()
            company.loc[date_index, "membership_known_from"] = known_from
            company.loc[date_index, "pit_member"] = company.loc[date_index, "ticker"].isin(members).to_numpy()
    company["membership_age_days"] = (
        company["date"] - pd.to_datetime(company["membership_known_from"])
    ).dt.days
    return company


def _join_parent_and_macro_features(
    company: pd.DataFrame,
    sector: pd.DataFrame,
    macro: pd.DataFrame,
) -> pd.DataFrame:
    parent_columns = [
        column
        for column in [*SECTOR_PRICE_FEATURES, *EARNINGS_FUNDAMENTAL_FEATURES]
        if column in sector.columns
    ]
    parent = sector[["date", "sector", *parent_columns]].rename(
        columns={"sector": "parent_sector", **{column: f"parent_{column}" for column in parent_columns}}
    )
    company = company.merge(parent, on=["date", "parent_sector"], how="left", validate="many_to_one")

    macro_columns = [
        column
        for column in macro.columns
        if column not in {
            "signal_date",
            "target_end_date_3m",
            "target_next_quadrant_3m",
            "target_regime_change_3m",
            "target_growth_signal_3m",
            "target_inflation_signal_3m",
            "evaluation_fold",
            "source_contract",
            "gmm_regime",
        }
    ]
    macro_view = macro[macro_columns].rename(columns={"dalio_quadrant": "macro_dalio_quadrant"})
    company = company.merge(macro_view, on="date", how="left", validate="many_to_one")
    return company


def build_company_contract(
    root: Path,
    sector: pd.DataFrame,
    macro: pd.DataFrame,
    holdout_start: pd.Timestamp,
) -> pd.DataFrame:
    quality = _load_quality_panels(root)
    dates = pd.DatetimeIndex(sorted(quality["date"].unique()))
    etf_prices = {sector_name: _load_sector_etf_daily(root, sector_name) for sector_name in set(BOOK_PARENT_SECTOR.values())}
    stock_prices = {ticker: load_close(root, ticker) for ticker in sorted(quality["ticker"].unique())}

    feature_frames: list[pd.DataFrame] = []
    for (ticker, parent_sector), group in quality.groupby(["ticker", "parent_sector"], sort=True):
        group_dates = pd.DatetimeIndex(sorted(group["date"].unique()))
        features = _company_price_features(
            stock=stock_prices[ticker],
            parent=etf_prices[parent_sector],
            dates=group_dates,
        ).reset_index()
        features.insert(1, "ticker", ticker)
        features.insert(2, "parent_sector", parent_sector)
        feature_frames.append(features)
    prices = pd.concat(feature_frames, ignore_index=True)

    company = quality.merge(
        prices,
        on=["date", "ticker", "parent_sector"],
        how="left",
        validate="many_to_one",
    )
    company = company.rename(columns={"fwd_rel": "target_peer_residual_6m"})
    company = _apply_membership_flags(root, company)
    company = _join_parent_and_macro_features(company, sector, macro)
    company.insert(1, "signal_date", company["date"])
    first_year = int(company["date"].dt.year.min()) + MIN_TRAIN_YEARS["company"]
    company["evaluation_fold"] = _evaluation_fold(company["date"], first_year, holdout_start)
    company["research_eligible"] = (
        company["quality_z"].notna() & company["target_company_residual_6m"].notna()
    )
    company["strict_pit_eligible"] = company["research_eligible"] & company["pit_member"].fillna(False)
    company["source_contract"] = "SEC filed-date quality plus adjusted daily prices"
    return company.sort_values(["date", "book", "ticker"]).reset_index(drop=True)


def _role_for_column(layer: str, column: str) -> str:
    if column.startswith("target_") or column in TARGET_COLUMNS:
        return "target"
    metadata = {
        "date",
        "signal_date",
        "entry_date",
        "company_entry_date",
        "parent_entry_date",
        "company_target_end_date",
        "parent_target_end_date",
        "target_end_date_3m",
        "target_end_date_6m",
        "evaluation_fold",
        "source_contract",
        "price_source",
        "live_source",
        "sector_index",
        "sector_etf",
        "book",
        "book_specification",
        "parent_sector",
        "ticker",
        "membership_basis",
        "membership_snapshot_asof",
        "membership_known_from",
        "membership_age_days",
        "pit_member",
        "research_eligible",
        "strict_pit_eligible",
        "n_metrics",
    }
    if column in metadata or column == "gmm_regime":
        return "metadata"
    if layer == "sector" and _is_excluded_predictive_feature(column):
        return "diagnostic_only"
    return "feature"


def _family_for_column(layer: str, column: str, role: str) -> str:
    if role == "target":
        return "forward_target"
    if role in {"metadata", "diagnostic_only"}:
        return role
    key = column.lower()
    base_family = _feature_family(column)
    if column in {
        "growth_signal",
        "inflation_signal",
        "market_health",
        "sector_breadth",
        "dalio_quadrant",
        "macro_dalio_quadrant",
    }:
        return "macro_regime"
    if key.startswith("t10y3m"):
        return "macro_nowcast"
    if layer == "company" and (
        column == "quality_z"
        or column == "capex_coverage_z"
        or (
            column.endswith("_z")
            and not column.startswith("parent_")
            and base_family not in {"macro_nowcast", "forward_macro"}
        )
    ):
        return "company_fundamental"
    if layer == "company" and key.startswith("company_"):
        return "company_price_trend"
    if layer == "company" and key.startswith("parent_"):
        return "parent_sector"
    if layer == "sector" and column == "sector":
        return "sector_control"
    if layer == "sector" and column in SECTOR_PRICE_FEATURES:
        return "price_trend"
    return base_family


def build_feature_registry(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for layer, frame in frames.items():
        for column in frame.columns:
            role = _role_for_column(layer, column)
            family = _family_for_column(layer, column, role)
            availability = "known at or before signal date"
            if family == "company_fundamental":
                availability = "SEC filed date <= signal date; trade begins next close"
            elif family in {"macro_nowcast", "forward_macro", "macro_regime"}:
                availability = "publication lag applied upstream; market series known by close"
            elif role == "target":
                availability = "future outcome; forbidden from predictive matrix"
            rows.append(
                {
                    "layer": layer,
                    "column": column,
                    "role": role,
                    "family": family,
                    "availability_rule": availability,
                    "coverage_pct": round(float(frame[column].notna().mean() * 100.0), 2),
                    "dtype": str(frame[column].dtype),
                }
            )
    return pd.DataFrame(rows).sort_values(["layer", "role", "family", "column"]).reset_index(drop=True)


def _eligible_mask(layer: str, frame: pd.DataFrame) -> pd.Series:
    if layer == "macro":
        return frame["target_regime_change_3m"].notna()
    if layer == "sector":
        return frame["fwd_6m_excess"].notna()
    return frame["research_eligible"].fillna(False)


def build_walk_forward_splits(
    frames: dict[str, pd.DataFrame],
    holdout_start: pd.Timestamp,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for layer, frame in frames.items():
        dates = pd.to_datetime(frame["date"])
        horizon = TARGET_HORIZONS[layer]
        first_year = int(dates.dt.year.min()) + MIN_TRAIN_YEARS[layer]
        eligible = _eligible_mask(layer, frame)
        target_end_column = f"target_end_date_{horizon}m"
        for year in range(first_year, holdout_start.year):
            test_start = pd.Timestamp(year=year, month=1, day=1)
            test_end = test_start + pd.DateOffset(years=1) - pd.Timedelta(days=1)
            train = eligible & (pd.to_datetime(frame[target_end_column]) < test_start)
            test = eligible & dates.between(test_start, test_end)
            rows.append(
                {
                    "layer": layer,
                    "fold": f"validation_{year}",
                    "train_signal_start": dates.loc[train].min(),
                    "train_signal_end": dates.loc[train].max(),
                    "max_train_target_end": pd.to_datetime(frame.loc[train, target_end_column]).max(),
                    "test_start": test_start,
                    "test_end": test_end,
                    "label_horizon_months": horizon,
                    "train_rows": int(train.sum()),
                    "test_rows": int(test.sum()),
                    "strict_pit_train_rows": int((train & frame.get("strict_pit_eligible", False)).sum())
                    if layer == "company"
                    else np.nan,
                    "strict_pit_test_rows": int((test & frame.get("strict_pit_eligible", False)).sum())
                    if layer == "company"
                    else np.nan,
                }
            )

        test = eligible & (dates >= holdout_start)
        train = eligible & (pd.to_datetime(frame[target_end_column]) < holdout_start)
        rows.append(
            {
                "layer": layer,
                "fold": "holdout",
                "train_signal_start": dates.loc[train].min(),
                "train_signal_end": dates.loc[train].max(),
                "max_train_target_end": pd.to_datetime(frame.loc[train, target_end_column]).max(),
                "test_start": holdout_start,
                "test_end": dates.loc[test].max(),
                "label_horizon_months": horizon,
                "train_rows": int(train.sum()),
                "test_rows": int(test.sum()),
                "strict_pit_train_rows": int((train & frame.get("strict_pit_eligible", False)).sum())
                if layer == "company"
                else np.nan,
                "strict_pit_test_rows": int((test & frame.get("strict_pit_eligible", False)).sum())
                if layer == "company"
                else np.nan,
            }
        )
    return pd.DataFrame(rows).sort_values(["layer", "test_start"]).reset_index(drop=True)


def _audit_row(check: str, status: str, detail: str, failures: int = 0) -> dict[str, Any]:
    return {"check": check, "status": status, "failures": failures, "detail": detail}


def build_leakage_audit(
    macro: pd.DataFrame,
    sector: pd.DataFrame,
    company: pd.DataFrame,
    registry: pd.DataFrame,
    splits: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for layer, frame, keys in [
        ("macro", macro, ["date"]),
        ("sector", sector, ["date", "sector"]),
        ("company", company, ["date", "book", "ticker"]),
    ]:
        failures = int(frame.duplicated(keys).sum())
        rows.append(_audit_row(f"{layer}_unique_keys", "PASS" if failures == 0 else "FAIL", f"keys={keys}", failures))

    feature_names = registry.loc[registry["role"].eq("feature"), "column"].astype(str)
    leaked = feature_names[
        feature_names.str.startswith("target_")
        | feature_names.isin(TARGET_COLUMNS)
        | feature_names.str.match(r"^fwd_\d+m")
        | feature_names.eq("leader_rank_pct")
    ]
    rows.append(
        _audit_row(
            "targets_excluded_from_features",
            "PASS" if leaked.empty else "FAIL",
            "no future-return, rank, or label columns have feature role" if leaked.empty else ", ".join(sorted(leaked.unique())),
            int(len(leaked)),
        )
    )
    gmm_feature = registry["role"].eq("feature") & registry["column"].eq("gmm_regime")
    rows.append(
        _audit_row(
            "full_history_gmm_excluded",
            "PASS" if not gmm_feature.any() else "FAIL",
            "GMM state remains descriptive metadata because its historical fit uses the full sample.",
            int(gmm_feature.sum()),
        )
    )

    sector_identity = (
        sector["fwd_6m"] - sector["fwd_6m_broad"] - sector["fwd_6m_excess"]
    ).abs().dropna()
    max_sector_error = float(sector_identity.max()) if len(sector_identity) else np.nan
    rows.append(
        _audit_row(
            "sector_target_identity",
            "PASS" if np.isnan(max_sector_error) or max_sector_error < 1e-10 else "FAIL",
            f"max absolute identity error={max_sector_error:.3g}",
            int(max_sector_error >= 1e-10) if not np.isnan(max_sector_error) else 0,
        )
    )
    company_identity = (
        company["target_company_fwd_6m"]
        - company["target_parent_sector_fwd_6m"]
        - company["target_company_residual_6m"]
    ).abs().dropna()
    max_company_error = float(company_identity.max()) if len(company_identity) else np.nan
    rows.append(
        _audit_row(
            "company_target_identity",
            "PASS" if np.isnan(max_company_error) or max_company_error < 1e-10 else "FAIL",
            f"max absolute identity error={max_company_error:.3g}",
            int(max_company_error >= 1e-10) if not np.isnan(max_company_error) else 0,
        )
    )
    labeled_company = company["target_company_residual_6m"].notna()
    window_mismatches = int(
        (
            company.loc[labeled_company, "company_entry_date"].ne(
                company.loc[labeled_company, "parent_entry_date"]
            )
            | company.loc[labeled_company, "company_target_end_date"].ne(
                company.loc[labeled_company, "parent_target_end_date"]
            )
        ).sum()
    )
    rows.append(
        _audit_row(
            "company_benchmark_window_alignment",
            "PASS" if window_mismatches == 0 else "FAIL",
            "every company residual target uses identical stock and parent-ETF entry/exit dates",
            window_mismatches,
        )
    )

    chronology_failures = 0
    for frame, end_column in [
        (macro, "target_end_date_3m"),
        (sector, "target_end_date_6m"),
        (company, "target_end_date_6m"),
    ]:
        valid = pd.to_datetime(frame[end_column]).notna()
        chronology_failures += int((pd.to_datetime(frame.loc[valid, end_column]) <= frame.loc[valid, "signal_date"]).sum())
    rows.append(
        _audit_row(
            "target_dates_after_signal",
            "PASS" if chronology_failures == 0 else "FAIL",
            "every dated target ends strictly after its signal date",
            chronology_failures,
        )
    )

    split_failures = int(
        (
            splits["max_train_target_end"].notna()
            & (pd.to_datetime(splits["max_train_target_end"]) >= pd.to_datetime(splits["test_start"]))
        ).sum()
    )
    rows.append(
        _audit_row(
            "walk_forward_label_purge",
            "PASS" if split_failures == 0 else "FAIL",
            "every training label matures before its test window starts",
            split_failures,
        )
    )
    unlagged_fundamentals = [
        column
        for column in EARNINGS_FUNDAMENTAL_FEATURES
        if column in sector.columns and "lag1" not in column
    ]
    rows.append(
        _audit_row(
            "sector_fundamentals_lagged",
            "PASS" if not unlagged_fundamentals else "FAIL",
            "all predictive sector earnings fields carry lag1 naming and upstream lagging",
            len(unlagged_fundamentals),
        )
    )
    symbol_count_features = feature_names[feature_names.str.contains("symbol_count", case=False)]
    rows.append(
        _audit_row(
            "symbol_counts_excluded",
            "PASS" if symbol_count_features.empty else "FAIL",
            "coverage counts are metadata, never a fundamental signal",
            int(len(symbol_count_features)),
        )
    )
    source_features = feature_names[feature_names.str.contains(r"(?:^|_)source(?:_|$)", case=False, regex=True)]
    rows.append(
        _audit_row(
            "source_labels_excluded",
            "PASS" if source_features.empty else "FAIL",
            "data-source and extension labels are provenance metadata, not predictors",
            int(len(source_features)),
        )
    )
    future_signal_rows = sum(
        int((pd.to_datetime(frame["signal_date"]) > pd.Timestamp.now().normalize()).sum())
        for frame in (macro, sector, company)
    )
    rows.append(
        _audit_row(
            "no_future_dated_signals",
            "PASS" if future_signal_rows == 0 else "FAIL",
            "incomplete current-month ETF data are not stamped as a future month-end signal",
            future_signal_rows,
        )
    )

    first_membership = company.loc[company["membership_known_from"].notna(), "membership_known_from"].min()
    rows.append(
        _audit_row(
            "historical_constituent_coverage",
            "WARN",
            f"SEC N-PORT top-10 membership is point-in-time only from {pd.Timestamp(first_membership).date()}; earlier company rows use a static research universe.",
        )
    )
    rows.append(
        _audit_row(
            "macro_vintage_scope",
            "WARN",
            "publication lags are applied, but full ALFRED vintages are not yet available for every macro series; GMM labels are descriptive only.",
        )
    )
    rows.append(
        _audit_row(
            "company_book_overlap",
            "WARN",
            "book/ticker is the modeling key; downstream sizing must consolidate duplicate tickers across SEMIS and sector books.",
        )
    )
    return pd.DataFrame(rows)


def build_coverage_summary(frames: dict[str, pd.DataFrame], registry: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for layer, frame in frames.items():
        eligible = _eligible_mask(layer, frame)
        entity_column = {"macro": None, "sector": "sector", "company": "ticker"}[layer]
        rows.append(
            {
                "layer": layer,
                "rows": len(frame),
                "entities": 1 if entity_column is None else frame[entity_column].nunique(),
                "start": frame["date"].min(),
                "end": frame["date"].max(),
                "target_rows": int(eligible.sum()),
                "predictive_features": int(
                    ((registry["layer"] == layer) & (registry["role"] == "feature")).sum()
                ),
                "strict_pit_rows": int(frame.get("strict_pit_eligible", pd.Series(dtype=bool)).sum())
                if layer == "company"
                else np.nan,
            }
        )
    return pd.DataFrame(rows)


def _vintage_figure(figsize: tuple[float, float] = (10.5, 4.1)) -> tuple[Any, Any]:
    fig, ax = plt.subplots(figsize=figsize, facecolor=PAPER)
    ax.set_facecolor(PAPER)
    ax.grid(which="major", color=GRID_MAJOR, linewidth=0.55, alpha=0.65)
    ax.minorticks_on()
    ax.grid(which="minor", color=GRID_MINOR, linewidth=0.28, alpha=0.45)
    for spine in ax.spines.values():
        spine.set_color(INK_MUTED)
    ax.tick_params(colors=INK, labelsize=8)
    ax.title.set_color(INK)
    ax.xaxis.label.set_color(INK)
    ax.yaxis.label.set_color(INK)
    return fig, ax


def _figure_b64(fig: Any) -> str:
    buffer = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buffer, format="png", dpi=150, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _chart_target_coverage(frames: dict[str, pd.DataFrame]) -> str:
    fig, ax = _vintage_figure()
    colors = {"macro": INK_AMBER, "sector": INK_NAVY, "company": INK_GREEN}
    for layer, frame in frames.items():
        monthly = frame.assign(eligible=_eligible_mask(layer, frame)).groupby("date")["eligible"].sum()
        if monthly.max() > 0:
            monthly = monthly / monthly.max() * 100.0
        ax.plot(monthly.index, monthly, label=layer.title(), color=colors[layer], linewidth=1.35)
    ax.set_title("Forward-target coverage by layer", loc="left", fontsize=12)
    ax.set_ylabel("% of layer maximum")
    ax.legend(frameon=False, ncol=3, labelcolor=INK)
    return _figure_b64(fig)


def _chart_feature_families(registry: pd.DataFrame) -> str:
    data = (
        registry.loc[registry["role"].eq("feature")]
        .groupby(["family", "layer"])
        .size()
        .unstack(fill_value=0)
        .sort_values(list(registry["layer"].unique()), ascending=False)
    )
    fig, ax = _vintage_figure(figsize=(10.5, 5.2))
    data.plot.barh(
        stacked=True,
        ax=ax,
        color=[INK_AMBER, INK_GREEN, INK_NAVY][: len(data.columns)],
        width=0.72,
    )
    ax.set_title("Predictive feature registry", loc="left", fontsize=12)
    ax.set_xlabel("registered columns")
    ax.set_ylabel("")
    ax.legend(frameon=False, labelcolor=INK)
    return _figure_b64(fig)


def _chart_membership(company: pd.DataFrame) -> str:
    monthly = company.groupby("date").agg(
        research_rows=("research_eligible", "sum"),
        strict_pit_rows=("strict_pit_eligible", "sum"),
    )
    fig, ax = _vintage_figure()
    ax.plot(monthly.index, monthly["research_rows"], color=INK_NAVY, label="Static research universe", linewidth=1.2)
    ax.plot(monthly.index, monthly["strict_pit_rows"], color=INK_RED, label="Strict PIT N-PORT members", linewidth=1.5)
    ax.set_title("Company target rows and constituent-history constraint", loc="left", fontsize=12)
    ax.set_ylabel("eligible book-company rows")
    ax.legend(frameon=False, labelcolor=INK)
    return _figure_b64(fig)


def _html_table(frame: pd.DataFrame, max_rows: int | None = None) -> str:
    view = frame.head(max_rows).copy() if max_rows else frame.copy()
    for column in view.columns:
        if pd.api.types.is_datetime64_any_dtype(view[column]):
            view[column] = view[column].dt.strftime("%Y-%m-%d")
        elif pd.api.types.is_float_dtype(view[column]):
            view[column] = view[column].map(lambda value: "" if pd.isna(value) else f"{value:.2f}")
    headers = "".join(f"<th>{html.escape(str(column))}</th>" for column in view.columns)
    rows = []
    for _, row in view.iterrows():
        cells = "".join(f"<td>{html.escape(str(value))}</td>" for value in row)
        rows.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def _img(data: str, alt: str) -> str:
    return f'<figure><img src="data:image/png;base64,{data}" alt="{html.escape(alt)}"><figcaption>{html.escape(alt)}</figcaption></figure>'


def build_html_report(result: BuildResult) -> str:
    frames = {"macro": result.macro, "sector": result.sector, "company": result.company}
    status_counts = result.audit["status"].value_counts()
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    latest_split = result.splits.groupby("layer", as_index=False).tail(1)
    family = (
        result.registry.loc[result.registry["role"].eq("feature")]
        .groupby(["layer", "family"])
        .size()
        .rename("features")
        .reset_index()
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hierarchical Research Contract</title>
<style>
:root{{--paper:{PAPER};--page:#eadcb8;--grid:{GRID_MINOR};--major:{GRID_MAJOR};--ink:{INK};--muted:{INK_MUTED};--navy:{INK_NAVY};--red:{INK_RED};--green:{INK_GREEN};}}
*{{box-sizing:border-box}} body{{margin:0;color:var(--ink);background-color:var(--page);font:14px/1.48 Georgia,"Times New Roman",serif;letter-spacing:0}}
main{{max-width:1280px;margin:0 auto;min-height:100vh;padding:30px 38px 64px;background-color:var(--paper);background-image:linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px),linear-gradient(var(--major) 1px,transparent 1px),linear-gradient(90deg,var(--major) 1px,transparent 1px);background-size:10px 10px,10px 10px,50px 50px,50px 50px}}
header{{border-top:4px solid var(--ink);border-bottom:1px solid var(--ink);padding:16px 0 14px;background:rgba(244,236,211,.94)}}
h1{{font-size:31px;line-height:1.08;margin:0 0 7px}} h2{{font-size:20px;margin:34px 0 10px;border-bottom:2px solid var(--ink);padding:0 0 5px}} h3{{font-size:15px;margin:20px 0 7px}}
p{{max-width:920px}} .meta{{color:var(--muted);font-size:12px}} .kpis{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border:1px solid var(--ink);margin:22px 0;background:rgba(244,236,211,.95)}}
.kpi{{padding:13px 15px;border-right:1px solid var(--ink)}} .kpi:last-child{{border-right:0}} .kpi b{{display:block;font:23px/1.05 Arial,sans-serif;color:var(--navy)}} .kpi span{{font-size:11px;text-transform:uppercase}}
.band{{background:rgba(244,236,211,.94);padding:1px 12px 12px;margin:0 -12px}} .charts{{display:grid;grid-template-columns:1fr 1fr;gap:18px}} figure{{margin:10px 0;background:var(--paper);border:1px solid var(--ink);padding:8px}} img{{width:100%;display:block}} figcaption{{font-size:11px;color:var(--muted);padding:5px 2px 0}}
.table-wrap{{overflow-x:auto;border:1px solid var(--ink);background:rgba(244,236,211,.97)}} table{{border-collapse:collapse;width:100%;font-size:12px}} th,td{{padding:7px 9px;border-bottom:1px solid #c9b77f;text-align:left;white-space:nowrap}} thead th{{background:#e1cd91;border-bottom:2px solid var(--ink);font-family:Arial,sans-serif}} tbody tr:nth-child(even){{background:rgba(225,205,145,.25)}}
.pass{{color:var(--green)}} .warn{{color:#925c00}} .fail{{color:var(--red)}} code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}}
@media(max-width:800px){{main{{padding:18px 14px 44px}}.kpis{{grid-template-columns:1fr 1fr}}.kpi:nth-child(2){{border-right:0}}.kpi{{border-bottom:1px solid var(--ink)}}.charts{{grid-template-columns:1fr}}h1{{font-size:25px}}}}
</style></head><body><main>
<header><h1>Hierarchical Macro → Sector → Company Research Contract</h1><p>One audited monthly clock for regime classification, sector-relative forecasting, company residual forecasting, trend confirmation, and later risk sizing.</p><p class="meta">Generated {generated}. This dashboard describes model-ready data, not a trading recommendation.</p></header>
<div class="kpis"><div class="kpi"><b>{len(result.macro):,}</b><span>Macro months</span></div><div class="kpi"><b>{len(result.sector):,}</b><span>Sector rows</span></div><div class="kpi"><b>{len(result.company):,}</b><span>Company-book rows</span></div><div class="kpi"><b>{int(status_counts.get('PASS', 0))}/{len(result.audit)}</b><span>Audit checks passed</span></div></div>
<section class="band"><h2>Data Coverage</h2><p>The three layers have separate targets. Sector alpha is measured versus the broad sector basket; company alpha is measured versus its parent sector ETF. The semiconductor book remains a dedicated specification while its parent risk factor is Technology.</p><div class="table-wrap">{_html_table(result.coverage)}</div>{_img(_chart_target_coverage(frames), 'Forward-target coverage normalized within each layer')}</section>
<section class="band"><h2>Feature Contract</h2><p>Targets, full-history GMM labels, counts, and diagnostic-only structure fields are not allowed into predictive matrices. Sector controls, release-lagged macro, trend, and filed-date fundamentals remain separate feature families.</p><div class="charts">{_img(_chart_feature_families(result.registry), 'Registered predictive features by layer and family')}{_img(_chart_membership(result.company), 'Research-universe versus strict point-in-time constituent coverage')}</div><div class="table-wrap">{_html_table(family)}</div></section>
<section class="band"><h2>Walk-Forward Protocol</h2><p>Every training label must mature before the next test year begins. The six-month sector and company labels therefore impose a six-month purge. The 2025+ holdout remains separately identified.</p><div class="table-wrap">{_html_table(latest_split)}</div></section>
<section class="band"><h2>Leakage Audit</h2><p><span class="pass">PASS</span> is enforced. <span class="warn">WARN</span> records a known research limitation that must be conditioned on or disclosed. A failed check stops the build.</p><div class="table-wrap">{_html_table(result.audit)}</div></section>
<section class="band"><h2>Research Boundary</h2><p>SEC Company Facts are aligned by filing date and executed from the next close. Macro releases use conservative publication lags. Historical top-10 sector membership is known from N-PORT filings beginning in late 2019; older company rows are useful for exploratory pooled estimates but are not strict point-in-time constituent tests. Full ALFRED vintages and delisted-company coverage remain required before production capital allocation.</p><p>The next phase fits transparent regularized baselines first, then tree and boosting models with hierarchical partial pooling. Sizing will combine sector expected excess return and company residual alpha only after confidence shrinkage, trend-survival calibration, costs, borrow constraints, and portfolio risk limits.</p></section>
</main></body></html>"""


def write_markdown_report(result: BuildResult) -> str:
    pass_count = int(result.audit["status"].eq("PASS").sum())
    warn_count = int(result.audit["status"].eq("WARN").sum())
    lines = [
        "# Hierarchical research data contract",
        "",
        "The macro, sector, and company studies now share one monthly signal clock and explicit forward targets.",
        "",
        "## Coverage",
        "",
        result.coverage.to_markdown(index=False),
        "",
        "## Target definitions",
        "",
        "- Macro: next three-month Dalio quadrant and regime-change indicator.",
        "- Sector: forward six-month sector return minus the broad sector basket.",
        "- Company: forward 126-trading-day stock return minus its parent sector ETF return.",
        "- Quality-engine peer residual is retained as a secondary target, not substituted for parent-sector alpha.",
        "",
        "## Validation",
        "",
        f"- Audit: {pass_count} PASS, {warn_count} WARN, 0 FAIL.",
        "- Expanding annual walk-forward folds require every training label to mature before the test year.",
        "- The final holdout starts 2025-01-01.",
        "",
        "## Material limitations",
        "",
        "- Strict point-in-time N-PORT top-10 membership starts in November 2019. Earlier company rows use the static research universe.",
        "- The dedicated semiconductor book is a static industry specification and must be consolidated with XLK exposures during sizing.",
        "- Publication lags are applied, but full ALFRED vintages are not yet present for every macro series.",
        "- GMM regime labels are descriptive metadata and are forbidden from predictive features because the current fit uses full history.",
        "",
        "## Next phase",
        "",
        "Fit regularized macro-transition, sector-excess-return, and company-residual baselines; then add tree/boosting challengers, calibrated trend-survival confidence, and constrained portfolio sizing.",
    ]
    return "\n".join(lines) + "\n"


def _json_value(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    return value


def build_research_contract(
    project_root: str | Path | None = None,
    *,
    output_dir: str | Path = OUTPUT_DIR,
    holdout_start: str = HOLDOUT_START,
) -> BuildResult:
    root = resolve_project_root(project_root)
    out = root / output_dir
    holdout_ts = pd.Timestamp(holdout_start)
    total_steps = 7

    _write_progress(out, step=1, total=total_steps, stage="sector", message="Loading canonical sector panel")
    sector = load_sector_contract(root, holdout_ts)
    _write_progress(out, step=2, total=total_steps, stage="macro", message="Building release-aware macro regime contract")
    macro = build_macro_contract(sector, holdout_ts)
    _write_progress(out, step=3, total=total_steps, stage="company", message="Building company residual and trend features")
    company = build_company_contract(root, sector, macro, holdout_ts)

    frames = {"macro": macro, "sector": sector, "company": company}
    _write_progress(out, step=4, total=total_steps, stage="registry", message="Registering features, targets, and availability rules")
    registry = build_feature_registry(frames)
    splits = build_walk_forward_splits(frames, holdout_ts)
    _write_progress(out, step=5, total=total_steps, stage="audit", message="Running leakage and point-in-time audits")
    audit = build_leakage_audit(macro, sector, company, registry, splits)
    failures = audit.loc[audit["status"].eq("FAIL")]
    if not failures.empty:
        _write_progress(out, step=5, total=total_steps, stage="audit", message="Leakage audit failed", status="failed")
        raise ValueError("Leakage audit failed:\n" + failures.to_string(index=False))
    coverage = build_coverage_summary(frames, registry)
    result = BuildResult(macro, sector, company, registry, splits, audit, coverage, out)

    _write_progress(out, step=6, total=total_steps, stage="write", message="Writing panels and audit artifacts")
    out.mkdir(parents=True, exist_ok=True)
    macro.to_csv(out / "macro_monthly_panel.csv", index=False)
    sector.to_csv(out / "sector_monthly_panel.csv", index=False)
    company.to_csv(out / "company_monthly_panel.csv", index=False)
    registry.to_csv(out / "feature_registry.csv", index=False)
    splits.to_csv(out / "walk_forward_splits.csv", index=False)
    audit.to_csv(out / "leakage_audit.csv", index=False)
    coverage.to_csv(out / "coverage_summary.csv", index=False)

    manifest = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "holdout_start": holdout_start,
        "target_horizons_months": TARGET_HORIZONS,
        "rows": {layer: len(frame) for layer, frame in frames.items()},
        "date_ranges": {
            layer: {"start": _json_value(frame["date"].min()), "end": _json_value(frame["date"].max())}
            for layer, frame in frames.items()
        },
        "predictive_features": {
            layer: registry.loc[
                registry["layer"].eq(layer) & registry["role"].eq("feature"), "column"
            ].tolist()
            for layer in frames
        },
        "target_columns": {
            layer: registry.loc[
                registry["layer"].eq(layer) & registry["role"].eq("target"), "column"
            ].tolist()
            for layer in frames
        },
        "audit_status": audit["status"].value_counts().to_dict(),
    }
    (out / "data_contract.json").write_text(json.dumps(manifest, indent=2, default=_json_value), encoding="utf-8")

    _write_progress(out, step=7, total=total_steps, stage="report", message="Rendering vintage research dashboard")
    (out / "report.md").write_text(write_markdown_report(result), encoding="utf-8")
    (out / "index.html").write_text(build_html_report(result), encoding="utf-8")
    _write_progress(out, step=7, total=total_steps, stage="complete", message="Hierarchical research contract complete", status="complete")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--holdout-start", default=HOLDOUT_START)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_research_contract(
        args.project_root,
        output_dir=args.output_dir,
        holdout_start=args.holdout_start,
    )
    print(f"Dashboard: {result.output_dir / 'index.html'}")


if __name__ == "__main__":
    main()
