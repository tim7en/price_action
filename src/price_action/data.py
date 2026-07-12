from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

MACRO_FEATURES_DIR = Path("cache") / "macro_features"

# Economic releases are stamped at their observation date in the cache, not at
# the date the public first saw them. Shift each series forward by a
# conservative publication delay so a backtest row only sees released data.
# Market-price series (yields, VIX, DXY, gold, ...) are known at the close and
# carry no entry here. Keys cover both raw FRED ids and derived feature names.
MACRO_PUBLICATION_LAG_DAYS: dict[str, int] = {
    # Monthly prints stamped at month start, released the following month.
    "cpi_all_items_index": 45,
    "cpi_mom_pct": 45,
    "cpi_yoy_pct": 45,
    "core_cpi_yoy_pct": 45,
    "energy_cpi_yoy_pct": 45,
    "shelter_cpi_yoy_pct": 45,
    "CPILFESL": 45,
    "CPIENGSL": 45,
    "CUSR0000SAH1": 45,
    "unemployment_rate_pct": 35,
    "UNRATE": 35,
    "industrial_production_yoy_pct": 45,
    "manufacturing_output_yoy_pct": 45,
    "INDPRO": 45,
    "IPMAN": 45,
    "PERMIT": 48,
    "market_cap_to_gdp_pct": 95,
    # Survey levels stamped at the reference month start; final prints land
    # near month end. The ALFRED release-aware sentiment series needs no lag.
    "UMCSENT": 30,
    "MICH": 30,
    "consumer_sentiment_level": 30,
    # Weekly series stamped at week end, released a few days later.
    "NFCI": 5,
    "ICSA": 5,
    # Daily indices computed after the close and published the next morning.
    "BAMLH0A0HYM2": 1,
    "high_yield_spread": 1,
    "USEPUINDXD": 1,
    "epu_level": 1,
    "epu_5d_change": 1,
    "epu_20d_change": 1,
    "epu_zscore_252d": 1,
    "epu_spike_flag": 1,
    "DFF": 1,
}


def apply_publication_lags(
    frame: pd.DataFrame,
    lag_days: Mapping[str, int] | None = None,
) -> pd.DataFrame:
    """Shift observation-stamped series so values appear only after release."""
    lags = MACRO_PUBLICATION_LAG_DAYS if lag_days is None else lag_days
    adjusted: dict[str, pd.Series] = {}
    for column in frame.columns:
        series = frame[column].dropna()
        lag = int(lags.get(column, 0))
        if lag:
            series = series.copy()
            series.index = series.index + pd.Timedelta(days=lag)
        adjusted[column] = series
    out = pd.DataFrame(adjusted)
    out.index.name = frame.index.name
    return out.sort_index()


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
    macro_frame = apply_publication_lags(macro_frame)

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
