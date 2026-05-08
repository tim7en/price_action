# Price Action ML Starter

This repo now includes a minimal walk-forward modeling pipeline built around the practical setup you described:

- baseline model: Elastic Net Logistic Regression
- main model: LightGBM
- robustness model: ExtraTrees
- context layer: daily macro and FRED risk series joined onto each asset
- regime filter: simple risk-off and trend regime features
- validation: row-based or calendar walk-forward split with an embargo and a non-overlapping trade schedule

The current implementation is designed for the cached daily data already present in this repository.

## What it does

For a symbol such as `AMZN`, the pipeline will:

1. load the cached daily asset JSON from `cache/cache/`
2. join it with macro context from `cache/macro_features/series/` when present, otherwise from `cache/macro_daily_1999.csv` and `fred/*.csv`
3. engineer price-action, volatility, macro, and regime features
4. train Logistic Regression, ExtraTrees, and LightGBM in walk-forward fashion
5. average model probabilities and optionally gate them through a small logistic meta-model
6. take only signals above a probability threshold and skip trades during the `risk_off` regime

## Macro feature store

Macro features are now exportable into a dedicated feature store:

- `cache/macro_features/series/<feature>.csv`
- `cache/macro_features/summaries/<feature>.json`
- `cache/macro_features/feature_inventory.csv`
- `cache/macro_features/series_health.csv`
- `cache/macro_features/README.md`

Each summary includes:

- feature name and source
- units
- history start date
- history end date
- row count and coverage ratio
- inferred frequency
- latest value

The health report adds:

- days since last update
- expected maximum lag by frequency
- stale flag
- stale status

Build or rebuild that store with:

```powershell
d:/dev/price_action/.venv/Scripts/python.exe build_macro_store.py
```

Or through the refresh command below.

## Refresh data

To refresh asset history from Yahoo Finance and rebuild the macro feature store:

```powershell
d:/dev/price_action/.venv/Scripts/python.exe refresh_data.py --symbols AMZN --start-date 2000-01-01 --build-macro-store
```

To refresh the repo's default multi-symbol panel universe and rebuild macro health outputs:

```powershell
d:/dev/price_action/.venv/Scripts/python.exe refresh_data.py --default-panel --start-date 2000-01-01 --build-macro-store
```

This path is useful for extending daily history to the last 20-plus years when the symbol has that much trading history available.

The root runner scripts avoid any need to install the package into the environment first.


## Run it

From the repo root:

```powershell
d:/dev/price_action/.venv/Scripts/python.exe run_walk_forward.py --symbol AMZN
```

You can tune the main experiment settings from the command line:

```powershell
d:/dev/price_action/.venv/Scripts/python.exe run_walk_forward.py --symbol AMZN --horizon 5 --cost-bps 15 --min-train-size 160 --test-size 40 --step-size 40 --embargo-size 5 --signal-threshold 0.55
```

To run the stricter calendar walk-forward setup with a final untouched holdout:

```powershell
d:/dev/price_action/.venv/Scripts/python.exe run_walk_forward.py --symbol AMZN --validation-mode calendar --train-years 5 --validation-years 1 --holdout-start 2025-01-01 --signal-threshold 0.55
```

To run the pooled panel experiment on the refreshed default panel universe:

```powershell
d:/dev/price_action/.venv/Scripts/python.exe run_panel_walk_forward.py --symbols PANEL --train-years 5 --validation-years 1 --holdout-start 2025-01-01 --signal-threshold 0.55
```

The command writes:

- `outputs/<symbol>/walk_forward_predictions.csv`
- `outputs/<symbol>/summary.json`

## Current design choices

- The label is a simple tradable target: forward return over `N` bars after a fee/slippage haircut.
- The trade schedule is non-overlapping: once a trade is taken, the strategy waits `N` bars before considering the next one.
- Sparse context columns are pruned automatically so mixed-frequency macro data does not collapse the whole sample.
- The regime filter is intentionally simple and inspectable. It is a starter context layer, not a final macro engine.
- `market_cap_to_gdp_pct_patched` extends the stale annual market-cap-to-GDP series with a daily proxy anchored to the last official observation.
- The panel workflow pools common features across symbols and evaluates a calendar holdout on the combined cross-section.

## Good next steps

- add point-in-time news and sentiment context
- replace the rule-based regime filter with a learned regime model
- add purged CV for the inner gate model
- expand from single-symbol experiments to a panel across all cached assets
- add point-in-time universe snapshots and delisted assets to reduce survivorship bias


## Research notes

See [docs/data_gaps_and_bias.md](docs/data_gaps_and_bias.md) for the current missing context features and the survivorship-bias controls this repo still needs.
