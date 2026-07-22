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

## Hierarchical research contract

Build the shared macro, sector, and company monthly panels before training the
hierarchical ensemble:

```bash
python build_hierarchical_research.py
```

The build writes model-ready panels, annual walk-forward split metadata, a
feature-role registry, leakage checks, progress state, and a vintage
millimetre-paper dashboard under `outputs/hierarchical_research/`.

To fit the final macro -> sector -> company -> trend ensemble, incorporate
release-aligned CFTC positioning, apply the live gamma risk overlay, and write
the constrained sizing dashboard:

```bash
python build_final_hierarchy.py
```

The final dashboard and auditable model artifacts are written under
`outputs/final_hierarchy/`. The build also replays the complete sizing policy
using only causally matured outcomes and next-session prices. Binance
commission, slippage, drift-aware turnover, funding, cash carry, and terminal
liquidation come from `config/binance_execution.json`; signals, targets,
period returns, and a JSON summary are written beside the dashboard. Perpetual
results remain `RESEARCH_ONLY` until point-in-time Binance contract mapping,
mark prices, and funding histories are supplied. Dealer gamma remains a
live-only sizing overlay until a historical point-in-time options-chain archive
is available.

To fit the interpretable 6/12-month broad-market and sector factor models:

```bash
python build_factor_driver_model.py
```

This writes purged walk-forward Elastic Net forecasts, signed coefficient
stability, CFTC attribution, live factor contributions, and the millimetre-paper
dashboard under `outputs/factor_driver_model/`. The importance values are
predictive conditional associations, not causal estimates.

## Standalone Binance session scalper

Run the independent BTCUSDT five-minute session study with:

```bash
python build_binance_session_scalper.py
```

It does not consume the macro or hierarchical models. The predeclared study
compares Tokyo, London, and New York exchange calendars during the first 30
minutes, the following 30-minute opening-range window, the final 30 minutes,
and the first 30 minutes after each cash close. It implements OHLCV proxies for
the supplied Fabio-style volume profile, delta, absorption, Triple-A, ORB, and
value-area rules; signals enter on the next bar and pay the separate USD-M
execution assumptions in `config/binance_session_scalper_execution.json`.
Outputs and limitations are written under `outputs/binance_session_scalper/`.

For the Fabio-style leveraged variant—BTC only, New York's first hour, 1% stop
risk, up to 10x gross notional, repeat non-overlapping attempts, and a hard stop
after three net losses in the UTC day—run:

```bash
python build_binance_session_scalper.py --preset leveraged_new_york_open
```

This writes setup-level holdout cost sensitivity and the full audit trail under
`outputs/binance_ny_open_scalper_leveraged/`. Profit-based intraday risk scaling
remains disabled until an exact, testable sizing equation is supplied.

## Standalone Nasdaq-100 New York-open backtest

The local `cache/Nasdaq.csv` one-minute OHLCV file can be tested with:

```bash
python build_nasdaq_session_backtest.py
```

By default the strategy compares complete one-, two-, and five-minute bars,
uses the official XNYS calendar, builds the opening range and prior-session
value area causally, and separates imbalance continuation from balance
rejection. A strict absorption variant requires volume above twice its prior
50-bar average and range below 0.3 ATR before accumulation and aggressive
expansion. It enters on the next bar, risks 1% at a one-ATR stop subject to a
10x cap, targets 2R, and applies a three-loss session stop. Development is 2024
and the untouched holdout is 2025. Reports, trades, session-block bootstrap
intervals, cost sensitivity, equity/drawdown/monthly-return plots, session
high/low timing, and the data-identity audit are written under
`outputs/nasdaq_multifrequency_backtest/`. Pass `--bar-minutes 1`, `2`, or `5`
to write a single-frequency report instead.

The separate two-minute POC/trend/management extension can be run with:

```bash
python build_nasdaq_poc_scaling_backtest.py
```

It compares 10-, 16-, 20-, and 30-minute post-observation phases, then audits
incremental trend sizing, a causal 1.5-ATR profit-protecting stop, and one
profit-financed add-on through a prior-five-session POC. It never charges an
add-on's stop risk to base capital and leaves the original baseline unchanged.
Results are written under `outputs/nasdaq_poc_scaling_backtest/`.

The CSV is not identified as CME NQ: most prices are off NQ's quarter-point
tick grid, and volume provenance is absent. The output is therefore explicitly
research-only until venue, contract/roll, spread and commission metadata are
supplied.


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
- The macro layer now separates headline, core, energy, and shelter inflation, and adds industrial plus manufacturing output so sticky inflation and real-activity rollovers can be distinguished.
- `spot_vix` uses VXO fallback and `vix3m_level` uses a regression-backed pre-launch backfill so the aligned daily macro frame has no leading gaps.
- `market_cap_to_gdp_proxy_pct` and `market_cap_to_gdp_pct_patched` keep valuation usable at daily frequency while staying anchored to the official annual market-cap-to-GDP observations.
- The panel workflow pools common features across symbols and evaluates a calendar holdout on the combined cross-section.

## Good next steps

- add point-in-time news and sentiment context
- replace the rule-based regime filter with a learned regime model
- add purged CV for the inner gate model
- expand from single-symbol experiments to a panel across all cached assets
- add point-in-time universe snapshots and delisted assets to reduce survivorship bias


## Research notebooks

The repo ships a set of Kaggle-style research notebooks under [notebooks/](notebooks/). Each one is a narrative walkthrough — load, plot, finding — that reads pre-computed CSV/JSON exports from `outputs/`. Notebooks do not retrain models; the corresponding build script writes the inputs first, then the notebook visualizes them.

| Notebook | Topic | Build script | Reads from |
| --- | --- | --- | --- |
| [sector_strategy_review.ipynb](notebooks/sector_strategy_review.ipynb) | Macro × SPY × sector-ETF quality rotation, walk-forward fold audit, feature importance, bootstrap CIs, confidence-gated ML variant | [build_sector_rotation_report.py](build_sector_rotation_report.py) | `outputs/sector_rotation_report/`, `outputs/sector_strategy_review/` |
| [pit_top_holdings_review.ipynb](notebooks/pit_top_holdings_review.ipynb) | Point-in-time top-5 holdings rotation vs sector ETF rotation and SPY buy-and-hold; forward-bias controls, leaderboard, 2025+ holdout assessment | [build_sector_rotation_report.py](build_sector_rotation_report.py) | `outputs/sector_rotation_report/` |
| [sector_fundamentals_research.ipynb](notebooks/sector_fundamentals_research.ipynb) | Sector earnings, market structure, and ETF leadership; cleaned `fundamentals_history` universe, lagged-fundamentals panel model, holdout-quarter picks | [build_sector_fundamentals_research.py](build_sector_fundamentals_research.py) | `outputs/sector_fundamentals_research/`, `outputs/fundamentals_analysis/` |
| [sector_macro_regime_book.ipynb](notebooks/sector_macro_regime_book.ipynb) | Macro regime shifts vs sector earnings breadth, lead/lag study, quarterly ML regime screen, sector trough → reversal windows | [build_sector_macro_regime_research.py](build_sector_macro_regime_research.py) | `outputs/sector_macro_regime_research/` |
| [spy_regime_risk_management_book.ipynb](notebooks/spy_regime_risk_management_book.ipynb) | 60/40 tactical sleeve under extreme risk-off regimes; Markov, Bayesian, and walk-forward ML lenses with no-lookahead controls | [build_spy_regime_risk_management.py](build_spy_regime_risk_management.py) | `outputs/spy_regime_risk_management/` |
| [spy_drawdown_regime_book.ipynb](notebooks/spy_drawdown_regime_book.ipynb) | SPY drawdown regimes, VIX/credit pace, sector spillover, online hidden-state layer, sector-tilt overlay | [build_spy_drawdown_regime_research.py](build_spy_drawdown_regime_research.py) | `outputs/spy_drawdown_regime_research/` |

### Refresh a notebook

Each notebook has a companion builder in `notebooks/_build_*.py` that regenerates the `.ipynb` cells from the latest research outputs. Typical refresh cycle:

```powershell
# 1. regenerate the research outputs under outputs/<name>/
d:/dev/price_action/.venv/Scripts/python.exe build_spy_drawdown_regime_research.py

# 2. rebuild the notebook structure from the builder script
d:/dev/price_action/.venv/Scripts/python.exe notebooks/_build_spy_drawdown_regime_book.py

# 3. execute cells in place
d:/dev/price_action/.venv/Scripts/jupyter.exe nbconvert --to notebook --execute --inplace notebooks/spy_drawdown_regime_book.ipynb
```

Substitute the matching build script and builder for any of the notebooks in the table above.

## Research notes

See [docs/data_gaps_and_bias.md](docs/data_gaps_and_bias.md) for the current missing context features and the survivorship-bias controls this repo still needs. Supporting write-ups also live alongside the notebooks: [docs/macro_regime_chapter.md](docs/macro_regime_chapter.md) and [docs/point_in_time_holdings.md](docs/point_in_time_holdings.md).
