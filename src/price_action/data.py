from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

MACRO_FEATURES_DIR = Path("cache") / "macro_features"


def resolve_project_root(project_root: str | Path | None = None) -> Path:
    if project_root is not None:
        return Path(project_root).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def discover_symbols(project_root: str | Path | None = None) -> list[str]:
    root = resolve_project_root(project_root)
    cache_dir = root / "cache" / "cache"
    return sorted(
        path.name.removesuffix("_daily.json")
        for path in cache_dir.glob("*_daily.json")
        if not path.name.endswith("_daily_vol.json")
    )


def _series_from_feature(payload: Mapping[str, Any], feature_name: str) -> pd.Series:
    series_values: dict[str, float] = {}
    for date_key, value in payload.items():
        if isinstance(value, Mapping):
            raw_value = value.get(feature_name)
        else:
            raw_value = value

        if raw_value is None:
            continue

        try:
            series_values[date_key] = float(raw_value)
        except (TypeError, ValueError):
            continue

    if not series_values:
        return pd.Series(dtype="float64")

    series = pd.Series(series_values, name=feature_name, dtype="float64")
    series.index = pd.to_datetime(series.index)
    return series.sort_index()


def load_asset_daily(symbol: str, project_root: str | Path | None = None) -> pd.DataFrame:
    root = resolve_project_root(project_root)
    payload_path = root / "cache" / "cache" / f"{symbol.upper()}_daily.json"
    if not payload_path.exists():
        raise FileNotFoundError(f"Asset cache not found for {symbol}: {payload_path}")

    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    feature_series = {
        feature_name: _series_from_feature(feature_payload, feature_name)
        for feature_name, feature_payload in payload.items()
        if isinstance(feature_payload, Mapping)
    }

    frame = pd.DataFrame(feature_series)
    frame.index.name = "date"
    frame = frame[~frame.index.duplicated(keep="last")]
    return frame.sort_index()


def load_macro_context(project_root: str | Path | None = None) -> pd.DataFrame:
    root = resolve_project_root(project_root)
    macro_features_dir = root / MACRO_FEATURES_DIR

    if macro_features_dir.exists():
        series_dir = macro_features_dir / "series"
        frames: list[pd.DataFrame] = []
        for series_path in sorted(series_dir.glob("*.csv")):
            series_frame = pd.read_csv(series_path, parse_dates=["date"]).set_index("date")
            value_columns = [column for column in series_frame.columns if column != "date"]
            if len(value_columns) != 1:
                continue
            feature_name = value_columns[0]
            frames.append(series_frame[[feature_name]].sort_index())

        if frames:
            context = pd.concat(frames, axis=1).sort_index()
            context.index.name = "date"
            context = context[~context.index.duplicated(keep="last")]
            return context

    frames: list[pd.DataFrame] = []

    macro_path = root / "cache" / "macro_daily_1999.csv"
    macro_frame = pd.read_csv(macro_path, parse_dates=["date"]).set_index("date").sort_index()
    frames.append(macro_frame)

    fred_dir = root / "fred"
    for fred_path in sorted(fred_dir.glob("*.csv")):
        fred_frame = pd.read_csv(fred_path, parse_dates=[0])
        fred_frame = fred_frame.rename(columns={fred_frame.columns[0]: "date"}).set_index("date")
        frames.append(fred_frame.sort_index())

    context = pd.concat(frames, axis=1).sort_index()
    context.index.name = "date"
    context = context[~context.index.duplicated(keep="last")]
    return context


def build_market_frame(symbol: str, project_root: str | Path | None = None) -> pd.DataFrame:
    asset_frame = load_asset_daily(symbol, project_root=project_root)
    macro_frame = load_macro_context(project_root=project_root)

    aligned_macro = macro_frame.reindex(asset_frame.index).ffill()
    market_frame = asset_frame.join(aligned_macro, how="left")

    if {"us_10y_yield", "us_2y_yield"}.issubset(market_frame.columns):
        market_frame["yield_curve_10y_2y"] = (
            market_frame["us_10y_yield"] - market_frame["us_2y_yield"]
        )

    if "BAMLH0A0HYM2" in market_frame.columns:
        market_frame = market_frame.rename(columns={"BAMLH0A0HYM2": "high_yield_spread"})

    if "VIXCLS" in market_frame.columns:
        market_frame = market_frame.rename(columns={"VIXCLS": "spot_vix"})

    return market_frame.sort_index()
