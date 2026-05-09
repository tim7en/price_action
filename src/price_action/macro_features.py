from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .data import MACRO_FEATURES_DIR, resolve_project_root

EXPECTED_MAX_LAG_DAYS_BY_FREQUENCY: dict[str, int] = {
    "daily": 10,
    "weekly": 21,
    "monthly": 62,
    "quarterly": 140,
    "annual_or_irregular": 550,
    "unknown": 365,
}

EXTRA_SERIES_METADATA: dict[str, dict[str, Any]] = {
    "high_yield_spread": {
        "name": "ICE BofA US High Yield Index Option-Adjusted Spread",
        "source": "FRED",
        "source_url": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2",
        "units": "percent",
        "combined_col": "high_yield_spread",
        "notes": ["Daily credit-spread proxy used for risk-off context."],
    },
    "NFCI": {
        "name": "Chicago Fed National Financial Conditions Index",
        "source": "FRED",
        "source_url": "https://fred.stlouisfed.org/series/NFCI",
        "units": "index level",
        "combined_col": "NFCI",
        "notes": ["Weekly financial conditions series."],
    },
    "T10Y3M": {
        "name": "10-Year Treasury Constant Maturity Minus 3-Month Treasury Constant Maturity",
        "source": "FRED",
        "source_url": "https://fred.stlouisfed.org/series/T10Y3M",
        "units": "percent",
        "combined_col": "T10Y3M",
        "notes": ["Yield-curve slope proxy."],
    },
    "spot_vix": {
        "name": "CBOE Volatility Index: VIX",
        "source": "FRED",
        "source_url": "https://fred.stlouisfed.org/series/VIXCLS",
        "units": "index level",
        "combined_col": "spot_vix",
        "notes": [
            "Daily spot volatility proxy.",
            "Leading 1999 gap is patched with the discontinued VXO predecessor and backfilled over the opening holiday rows so the aligned daily frame has no NaNs.",
        ],
    },
    "VXOCLS": {
        "name": "CBOE S&P 100 Volatility Index: VXO",
        "source": "FRED",
        "source_url": "https://fred.stlouisfed.org/series/VXOCLS",
        "units": "index level",
        "combined_col": "VXOCLS",
        "notes": ["Discontinued predecessor used only as a historical fallback for spot_vix."],
    },
    "vix3m_level": {
        "name": "CBOE S&P 500 3-Month Volatility Index",
        "source": "Yahoo Finance chart API / derived pre-launch backfill",
        "source_url": "https://finance.yahoo.com/quote/%5EVIX3M",
        "units": "index level",
        "combined_col": "vix3m_level",
        "notes": [
            "Official ^VIX3M history where available.",
            "Pre-launch history is backfilled from the observed spot_vix overlap regression so the aligned daily frame has no leading NaNs.",
        ],
    },
    "CPILFESL": {
        "name": "Consumer Price Index: All Items Less Food and Energy",
        "source": "FRED",
        "source_url": "https://fred.stlouisfed.org/series/CPILFESL",
        "units": "index 1982-1984=100, seasonally adjusted",
        "combined_col": "CPILFESL",
        "notes": ["Monthly core CPI index."],
    },
    "core_cpi_yoy_pct": {
        "name": "Core CPI YoY",
        "source": "FRED",
        "source_url": "https://fred.stlouisfed.org/series/CPILFESL",
        "units": "percent",
        "combined_col": "core_cpi_yoy_pct",
        "notes": ["Derived as the 12-month percent change of CPILFESL."],
    },
    "CPIENGSL": {
        "name": "Consumer Price Index: Energy",
        "source": "FRED",
        "source_url": "https://fred.stlouisfed.org/series/CPIENGSL",
        "units": "index 1982-1984=100, seasonally adjusted",
        "combined_col": "CPIENGSL",
        "notes": ["Monthly energy CPI index."],
    },
    "energy_cpi_yoy_pct": {
        "name": "Energy CPI YoY",
        "source": "FRED",
        "source_url": "https://fred.stlouisfed.org/series/CPIENGSL",
        "units": "percent",
        "combined_col": "energy_cpi_yoy_pct",
        "notes": ["Derived as the 12-month percent change of CPIENGSL."],
    },
    "CUSR0000SAH1": {
        "name": "Consumer Price Index: Shelter",
        "source": "FRED",
        "source_url": "https://fred.stlouisfed.org/series/CUSR0000SAH1",
        "units": "index 1982-1984=100",
        "combined_col": "CUSR0000SAH1",
        "notes": ["Monthly shelter CPI index."],
    },
    "shelter_cpi_yoy_pct": {
        "name": "Shelter CPI YoY",
        "source": "FRED",
        "source_url": "https://fred.stlouisfed.org/series/CUSR0000SAH1",
        "units": "percent",
        "combined_col": "shelter_cpi_yoy_pct",
        "notes": ["Derived as the 12-month percent change of CUSR0000SAH1."],
    },
    "INDPRO": {
        "name": "Industrial Production: Total Index",
        "source": "FRED",
        "source_url": "https://fred.stlouisfed.org/series/INDPRO",
        "units": "index 2017=100",
        "combined_col": "INDPRO",
        "notes": ["Monthly total industrial production index."],
    },
    "industrial_production_yoy_pct": {
        "name": "Industrial Production YoY",
        "source": "FRED",
        "source_url": "https://fred.stlouisfed.org/series/INDPRO",
        "units": "percent",
        "combined_col": "industrial_production_yoy_pct",
        "notes": ["Derived as the 12-month percent change of INDPRO."],
    },
    "IPMAN": {
        "name": "Industrial Production: Manufacturing",
        "source": "FRED",
        "source_url": "https://fred.stlouisfed.org/series/IPMAN",
        "units": "index 2017=100",
        "combined_col": "IPMAN",
        "notes": ["Monthly manufacturing output index."],
    },
    "manufacturing_output_yoy_pct": {
        "name": "Manufacturing Output YoY",
        "source": "FRED",
        "source_url": "https://fred.stlouisfed.org/series/IPMAN",
        "units": "percent",
        "combined_col": "manufacturing_output_yoy_pct",
        "notes": ["Derived as the 12-month percent change of IPMAN."],
    },
    "yield_curve_10y_2y": {
        "name": "10Y minus 2Y Treasury yield spread",
        "source": "derived",
        "source_url": None,
        "units": "percent",
        "combined_col": "yield_curve_10y_2y",
        "notes": ["Derived from us_10y_yield minus us_2y_yield."],
    },
    "market_cap_to_gdp_proxy_pct": {
        "name": "Market cap to GDP proxy",
        "source": "derived",
        "source_url": None,
        "units": "percent of GDP",
        "combined_col": "market_cap_to_gdp_proxy_pct",
        "notes": [
            "Daily proxy scaled from Wilshire and nominal GDP using the full set of official annual market_cap_to_gdp_pct anchors.",
        ],
    },
    "market_cap_to_gdp_pct_patched": {
        "name": "Market cap to GDP patched",
        "source": "derived_plus_official",
        "source_url": None,
        "units": "percent of GDP",
        "combined_col": "market_cap_to_gdp_pct_patched",
        "notes": [
            "Official annual observations when available, with the derived daily proxy filling the gaps between official prints and after the latest official date.",
        ],
    },
}


def derive_yoy_pct(series: pd.Series) -> pd.Series:
    observed = pd.to_numeric(series, errors="coerce").dropna()
    if observed.empty:
        return pd.Series(index=series.index, dtype="float64")

    yoy = observed.pct_change(12) * 100.0
    return yoy.reindex(series.index)


def build_macro_open_data_derivatives(combined: pd.DataFrame) -> pd.DataFrame:
    derived_sources = {
        "core_cpi_yoy_pct": "CPILFESL",
        "energy_cpi_yoy_pct": "CPIENGSL",
        "shelter_cpi_yoy_pct": "CUSR0000SAH1",
        "industrial_production_yoy_pct": "INDPRO",
        "manufacturing_output_yoy_pct": "IPMAN",
    }
    for derived_col, source_col in derived_sources.items():
        if source_col in combined.columns:
            combined[derived_col] = derive_yoy_pct(combined[source_col])
    return combined


def patch_spot_vix_history(combined: pd.DataFrame) -> pd.DataFrame:
    if "spot_vix" not in combined.columns:
        return combined

    spot_vix = pd.to_numeric(combined["spot_vix"], errors="coerce")
    if "VXOCLS" in combined.columns:
        vxo = pd.to_numeric(combined["VXOCLS"], errors="coerce")
        spot_vix = spot_vix.combine_first(vxo)

    combined["spot_vix"] = spot_vix.bfill()
    return combined


def patch_vix3m_history(combined: pd.DataFrame) -> pd.DataFrame:
    required = {"spot_vix", "vix3m_level"}
    if not required.issubset(combined.columns):
        return combined

    spot_vix = pd.to_numeric(combined["spot_vix"], errors="coerce")
    vix3m = pd.to_numeric(combined["vix3m_level"], errors="coerce")
    overlap = pd.DataFrame({"spot_vix": spot_vix, "vix3m": vix3m}).dropna()
    if overlap.empty:
        combined["vix3m_level"] = vix3m.bfill()
        return combined

    spot_mean = float(overlap["spot_vix"].mean())
    vix3m_mean = float(overlap["vix3m"].mean())
    spot_variance = float(((overlap["spot_vix"] - spot_mean) ** 2).mean())
    if spot_variance == 0.0:
        slope = 1.0
        intercept = float((overlap["vix3m"] - overlap["spot_vix"]).median())
    else:
        covariance = float(
            ((overlap["spot_vix"] - spot_mean) * (overlap["vix3m"] - vix3m_mean)).mean()
        )
        slope = covariance / spot_variance
        intercept = vix3m_mean - slope * spot_mean

    synthetic_vix3m = (spot_vix * slope + intercept).clip(lower=0.01)
    combined["vix3m_level"] = vix3m.combine_first(synthetic_vix3m).bfill()
    return combined


def build_market_cap_to_gdp_proxy(combined: pd.DataFrame) -> pd.DataFrame:
    required = {"market_cap_to_gdp_pct", "wilshire_total_market_index", "us_nominal_gdp_saar_bil"}
    if not required.issubset(combined.columns):
        return combined

    official_series = pd.to_numeric(combined["market_cap_to_gdp_pct"], errors="coerce")
    official_series = official_series.dropna()
    if official_series.empty:
        return combined

    wilshire = pd.to_numeric(combined["wilshire_total_market_index"], errors="coerce").ffill()
    gdp = pd.to_numeric(combined["us_nominal_gdp_saar_bil"], errors="coerce").ffill()

    base_ratio = wilshire / gdp
    anchor_scale = (official_series / base_ratio.reindex(official_series.index)).replace([float("inf"), float("-inf")], pd.NA)
    anchor_scale = pd.to_numeric(anchor_scale, errors="coerce").dropna()
    if anchor_scale.empty:
        return combined

    scale = anchor_scale.reindex(combined.index).interpolate(method="time").ffill().bfill()
    proxy = (base_ratio * scale).where(base_ratio.notna()).bfill()
    patched = pd.to_numeric(combined["market_cap_to_gdp_pct"], errors="coerce").combine_first(proxy)

    combined["market_cap_to_gdp_proxy_pct"] = proxy
    combined["market_cap_to_gdp_pct_patched"] = patched
    return combined


def load_macro_combined_frame(project_root: str | Path | None = None) -> pd.DataFrame:
    root = resolve_project_root(project_root)
    macro_path = root / "cache" / "macro_daily_1999.csv"
    macro_frame = pd.read_csv(macro_path, parse_dates=["date"]).set_index("date").sort_index()

    fred_frames: list[pd.DataFrame] = []
    for fred_path in sorted((root / "fred").glob("*.csv")):
        fred_frame = pd.read_csv(fred_path, parse_dates=[0])
        fred_frame = fred_frame.rename(columns={fred_frame.columns[0]: "date"}).set_index("date")
        fred_frames.append(fred_frame.sort_index())

    combined = pd.concat([macro_frame, *fred_frames], axis=1).sort_index()
    combined.index.name = "date"
    combined = combined[~combined.index.duplicated(keep="last")]

    if {"us_10y_yield", "us_2y_yield"}.issubset(combined.columns):
        combined["yield_curve_10y_2y"] = combined["us_10y_yield"] - combined["us_2y_yield"]

    if "BAMLH0A0HYM2" in combined.columns:
        combined = combined.rename(columns={"BAMLH0A0HYM2": "high_yield_spread"})

    if "VIXCLS" in combined.columns:
        combined = combined.rename(columns={"VIXCLS": "spot_vix"})

    combined = build_macro_open_data_derivatives(combined)
    combined = patch_spot_vix_history(combined)
    combined = patch_vix3m_history(combined)
    combined = build_market_cap_to_gdp_proxy(combined)
    combined = combined.loc[combined.index >= macro_frame.index.min()].copy()

    return combined


def load_macro_feature_metadata(project_root: str | Path | None = None) -> dict[str, dict[str, Any]]:
    root = resolve_project_root(project_root)
    metadata_path = root / "cache" / "macro_daily_1999_metadata.json"
    metadata_payload = json.loads(metadata_path.read_text(encoding="utf-8"))

    feature_metadata: dict[str, dict[str, Any]] = {}
    for series_name, details in metadata_payload.get("series", {}).items():
        combined_col = details.get("combined_col")
        if combined_col:
            feature_metadata[combined_col] = {
                "series_key": series_name,
                "name": details.get("name") or series_name,
                "source": details.get("source"),
                "source_url": details.get("source_url"),
                "units": details.get("units"),
                "notes": [],
            }

        for derived_col in (details.get("derived_combined_cols") or {}).values():
            feature_metadata[derived_col] = {
                "series_key": series_name,
                "name": derived_col,
                "source": details.get("source"),
                "source_url": details.get("source_url"),
                "units": "percent",
                "notes": [f"Derived from {series_name}."],
            }

    for feature_name, details in EXTRA_SERIES_METADATA.items():
        feature_metadata.setdefault(feature_name, details.copy())

    return feature_metadata


def infer_frequency(non_null_index: pd.DatetimeIndex) -> str:
    if len(non_null_index) < 3:
        return "unknown"

    day_deltas = non_null_index.to_series().diff().dropna().dt.days
    median_gap = float(day_deltas.median())

    if median_gap <= 2:
        return "daily"
    if median_gap <= 10:
        return "weekly"
    if median_gap <= 40:
        return "monthly"
    if median_gap <= 120:
        return "quarterly"
    return "annual_or_irregular"


def summarize_feature(
    feature_name: str,
    series: pd.Series,
    metadata: dict[str, dict[str, Any]],
    as_of_date: pd.Timestamp,
) -> dict[str, Any]:
    numeric = pd.to_numeric(series, errors="coerce")
    non_null = numeric.dropna()
    base = metadata.get(feature_name, {}).copy()
    frequency = infer_frequency(non_null.index)
    history_end = non_null.index.max() if not non_null.empty else None
    days_since_update = int((as_of_date - history_end).days) if history_end is not None else None
    expected_max_lag_days = EXPECTED_MAX_LAG_DAYS_BY_FREQUENCY.get(frequency, 365)
    stale = bool(days_since_update is not None and days_since_update > expected_max_lag_days)

    summary = {
        "feature": feature_name,
        "name": base.get("name") or feature_name,
        "source": base.get("source") or "unknown",
        "source_url": base.get("source_url"),
        "units": base.get("units"),
        "history_start": str(non_null.index.min().date()) if not non_null.empty else None,
        "history_end": str(history_end.date()) if history_end is not None else None,
        "rows_with_values": int(non_null.shape[0]),
        "total_rows": int(numeric.shape[0]),
        "missing_rows": int(numeric.isna().sum()),
        "coverage_ratio": float(non_null.shape[0] / numeric.shape[0]) if numeric.shape[0] else 0.0,
        "frequency": frequency,
        "latest_value": float(non_null.iloc[-1]) if not non_null.empty else None,
        "days_since_update": days_since_update,
        "expected_max_lag_days": expected_max_lag_days,
        "stale": stale,
        "stale_status": "stale" if stale else "fresh",
        "notes": list(base.get("notes") or []),
    }
    return summary


def write_macro_feature_store(project_root: str | Path | None = None) -> Path:
    root = resolve_project_root(project_root)
    feature_store_dir = root / MACRO_FEATURES_DIR
    series_dir = feature_store_dir / "series"
    summaries_dir = feature_store_dir / "summaries"
    series_dir.mkdir(parents=True, exist_ok=True)
    summaries_dir.mkdir(parents=True, exist_ok=True)

    combined = load_macro_combined_frame(project_root=project_root)
    metadata = load_macro_feature_metadata(project_root=project_root)
    as_of_date = pd.Timestamp(datetime.now(UTC)).tz_localize(None)

    inventory_rows: list[dict[str, Any]] = []
    for feature_name in combined.columns:
        series = combined[feature_name]
        feature_frame = series.rename(feature_name).to_frame().reset_index()
        feature_frame.to_csv(series_dir / f"{feature_name}.csv", index=False)

        summary = summarize_feature(
            feature_name=feature_name,
            series=series,
            metadata=metadata,
            as_of_date=as_of_date,
        )
        inventory_rows.append(summary)
        (summaries_dir / f"{feature_name}.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )

    inventory = pd.DataFrame(inventory_rows).sort_values(["history_start", "feature"])
    inventory.to_csv(feature_store_dir / "feature_inventory.csv", index=False)
    inventory.sort_values(["stale", "days_since_update", "feature"], ascending=[False, False, True]).to_csv(
        feature_store_dir / "series_health.csv",
        index=False,
    )
    (feature_store_dir / "feature_inventory.json").write_text(
        json.dumps(inventory_rows, indent=2),
        encoding="utf-8",
    )

    readme_lines = [
        "# Macro Feature Store",
        "",
        f"Generated at: {datetime.now(UTC).isoformat()}",
        "",
        "Each feature is stored as its own CSV under `series/`, with a matching JSON summary under `summaries/`.",
        "Freshness checks are written to `series_health.csv`.",
        "",
        "| feature | source | history_start | history_end | frequency | coverage_ratio | stale |",
        "| --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for row in inventory_rows:
        readme_lines.append(
            "| {feature} | {source} | {history_start} | {history_end} | {frequency} | {coverage_ratio:.3f} | {stale_status} |".format(
                **row
            )
        )
    (feature_store_dir / "README.md").write_text("\n".join(readme_lines) + "\n", encoding="utf-8")
    return feature_store_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export macro features into a dedicated store.")
    return parser


def main() -> None:
    build_parser().parse_args()
    output_dir = write_macro_feature_store()
    print(output_dir)


if __name__ == "__main__":
    main()