"""Build the Kaggle-style notebook for sector fundamentals research.

Run:
    python notebooks/_build_sector_fundamentals_research_notebook.py
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK_PATH = PROJECT_ROOT / "notebooks" / "sector_fundamentals_research.ipynb"


def md(source: str) -> nbf.NotebookNode:
    return nbf.v4.new_markdown_cell(source)


def code(source: str) -> nbf.NotebookNode:
    return nbf.v4.new_code_cell(source)


def build_notebook() -> nbf.NotebookNode:
    nb = nbf.v4.new_notebook()
    cells: list[nbf.NotebookNode] = []

    cells.append(
        md(
            "# Sector Earnings, Market Structure, and ETF Leadership\n\n"
            "**Goal.** Build a professional research note around the cleaned `fundamentals_history` universe, "
            "aggregate it into canonical sectors, and test whether lagged sector earnings signals plus market-cap, "
            "liquidity, and price context explain next-quarter sector ETF leadership.\n\n"
            "**What changed before this notebook:**\n"
            "- Sector labels are normalized into 11 canonical buckets linked to liquid ETF proxies.\n"
            "- Ambiguous or non-primary securities such as many preferreds, warrants, units, notes, and shell-company listings are excluded from sector aggregates.\n"
            "- Surprise and EPS-growth percentages are winsorized after filtering tiny denominators, so a few near-zero EPS estimates no longer dominate the relationship tables.\n"
            "- The panel model uses **lagged** sector fundamentals to avoid reading same-quarter earnings as if they were known at quarter-end.\n\n"
            "**Notebook map**\n"
            "1. Setup and report loading\n"
            "2. Cleaning audit and universe coverage\n"
            "3. Distribution repair after clipping\n"
            "4. Cleaned sector relationship map\n"
            "5. Sector market-cap and liquidity structure\n"
            "6. Panel design and target definition\n"
            "7. Ensemble model results\n"
            "8. Feature importance and relationship takeaways\n"
            "9. Holdout quarter picks\n"
            "10. Conclusions and caveats"
        )
    )

    cells.append(md("## 1. Setup and report loading"))
    cells.append(
        code(
            "import json\n"
            "from pathlib import Path\n"
            "\n"
            "import numpy as np\n"
            "import pandas as pd\n"
            "import matplotlib.pyplot as plt\n"
            "import seaborn as sns\n"
            "from IPython.display import display\n"
            "\n"
            "plt.rcParams.update({\n"
            "    'figure.figsize': (11, 4.8),\n"
            "    'figure.dpi': 115,\n"
            "    'axes.grid': True,\n"
            "    'grid.alpha': 0.22,\n"
            "    'axes.spines.top': False,\n"
            "    'axes.spines.right': False,\n"
            "    'font.size': 10,\n"
            "})\n"
            "sns.set_theme(style='whitegrid', context='notebook')\n"
            "\n"
            "PROJECT_ROOT = Path.cwd().parent if Path.cwd().name == 'notebooks' else Path.cwd()\n"
            "ANALYSIS_DIR = PROJECT_ROOT / 'outputs' / 'fundamentals_analysis'\n"
            "RESEARCH_DIR = PROJECT_ROOT / 'outputs' / 'sector_fundamentals_research'\n"
            "print('analysis dir:', ANALYSIS_DIR)\n"
            "print('research dir:', RESEARCH_DIR)"
        )
    )
    cells.append(
        code(
            "with open(ANALYSIS_DIR / 'fundamentals_analysis_summary.json', encoding='utf-8') as f:\n"
            "    analysis_summary = json.load(f)\n"
            "with open(RESEARCH_DIR / 'sector_research_summary.json', encoding='utf-8') as f:\n"
            "    research_summary = json.load(f)\n"
            "\n"
            "sector_summary = pd.read_csv(ANALYSIS_DIR / 'sector_fundamentals_summary.csv')\n"
            "sector_surprise_pairs = pd.read_csv(ANALYSIS_DIR / 'sector_surprise_correlation_pairs.csv')\n"
            "sector_lead_lag = pd.read_csv(ANALYSIS_DIR / 'sector_surprise_lead_lag.csv')\n"
            "sector_corr = pd.read_csv(ANALYSIS_DIR / 'sector_surprise_correlation.csv', index_col=0)\n"
            "quarterly_symbol = pd.read_csv(ANALYSIS_DIR / 'symbol_quarterly_earnings.csv')\n"
            "eligible_symbols = pd.read_csv(ANALYSIS_DIR / 'sector_analysis_eligible_symbols.csv')\n"
            "excluded_symbols = pd.read_csv(ANALYSIS_DIR / 'sector_analysis_excluded_symbols.csv')\n"
            "panel = pd.read_csv(RESEARCH_DIR / 'sector_factor_panel.csv')\n"
            "metrics = pd.read_csv(RESEARCH_DIR / 'sector_model_metrics.csv')\n"
            "feature_importance = pd.read_csv(RESEARCH_DIR / 'sector_feature_importance.csv')\n"
            "market_structure = pd.read_csv(RESEARCH_DIR / 'sector_market_structure_quarterly.csv')\n"
            "validation_predictions = pd.read_csv(RESEARCH_DIR / 'sector_model_validation_predictions.csv')\n"
            "holdout_predictions = pd.read_csv(RESEARCH_DIR / 'sector_model_holdout_predictions.csv')\n"
            "validation_strategy = pd.read_csv(RESEARCH_DIR / 'sector_top3_validation_strategy.csv', parse_dates=['quarter_end_date'])\n"
            "holdout_strategy = pd.read_csv(RESEARCH_DIR / 'sector_top3_holdout_strategy.csv', parse_dates=['quarter_end_date'])\n"
            "\n"
            "print('eligible symbols :', len(eligible_symbols))\n"
            "print('excluded symbols :', len(excluded_symbols))\n"
            "print('panel rows       :', research_summary['panel_rows'])\n"
            "print('feature count    :', research_summary['feature_count'])\n"
            "print('holdout rows     :', len(holdout_predictions))"
        )
    )

    cells.append(md("## 2. Cleaning audit and universe coverage\n\nThe first pass matters because the raw universe mixes operating companies with instruments that are poor fits for sector-level earnings research. This section shows how much cleaning happened and how broad the sector coverage is through time."))
    cells.append(
        code(
            "cleaning = analysis_summary['cleaning']\n"
            "cleaning_snapshot = pd.DataFrame({\n"
            "    'metric': [\n"
            "        'overview symbols',\n"
            "        'eligible symbols',\n"
            "        'excluded symbols',\n"
            "        'raw sector labels',\n"
            "        'canonical sectors',\n"
            "        'quarters analyzed',\n"
            "    ],\n"
            "    'value': [\n"
            "        analysis_summary['overview_symbols'],\n"
            "        analysis_summary['eligible_symbols'],\n"
            "        analysis_summary['excluded_symbols'],\n"
            "        cleaning['raw_sector_count'],\n"
            "        cleaning['canonical_sector_count'],\n"
            "        analysis_summary['quarters_analyzed'],\n"
            "    ],\n"
            "})\n"
            "excluded_reasons = (\n"
            "    pd.Series(cleaning['excluded_reasons'], name='excluded_symbol_count')\n"
            "    .rename_axis('reason')\n"
            "    .reset_index()\n"
            ")\n"
            "display(cleaning_snapshot)\n"
            "display(excluded_reasons)"
        )
    )
    cells.append(
        code(
            "coverage = (\n"
            "    pd.read_csv(ANALYSIS_DIR / 'sector_quarterly_surprise.csv')\n"
            "    .groupby('fiscal_quarter')\n"
            "    .agg(sectors=('sector', 'nunique'), total_symbols=('symbol_count', 'sum'), median_symbols=('symbol_count', 'median'))\n"
            "    .reset_index()\n"
            ")\n"
            "coverage['quarter_end'] = pd.PeriodIndex(coverage['fiscal_quarter'], freq='Q').to_timestamp(how='end')\n"
            "coverage['trailing_total_symbols'] = coverage['total_symbols'].rolling(4, min_periods=4).median().shift(1)\n"
            "coverage['is_complete_quarter'] = coverage['trailing_total_symbols'].isna() | (coverage['total_symbols'] >= 0.50 * coverage['trailing_total_symbols'])\n"
            "incomplete_quarters = coverage.loc[~coverage['is_complete_quarter'], 'fiscal_quarter'].tolist()\n"
            "coverage = coverage.loc[coverage['is_complete_quarter']].copy()\n"
            "fig, ax = plt.subplots(figsize=(11, 4.4))\n"
            "ax.plot(coverage['quarter_end'], coverage['total_symbols'], color='#1d3557', linewidth=2.0, label='Total eligible symbols')\n"
            "ax.fill_between(coverage['quarter_end'], coverage['median_symbols'], color='#a8dadc', alpha=0.35, label='Median symbols per sector')\n"
            "ax.axvline(pd.Timestamp('2020-01-01'), color='#e76f51', linestyle='--', linewidth=1.2, label='2020 coverage marker')\n"
            "ax.set_title('Sector earnings coverage broadened materially into the modern sample')\n"
            "ax.set_ylabel('symbol count')\n"
            "ax.legend(frameon=False, loc='upper left')\n"
            "plt.tight_layout()\n"
            "plt.show()\n"
            "print('Filtered incomplete trailing quarters:', incomplete_quarters)"
        )
    )

    cells.append(md("## 3. Distribution repair after clipping\n\nThe raw surprise and EPS-growth fields contain pathological percentages when the estimate or prior-year EPS is near zero. The cleaned analyzer keeps those rows in the symbol output, but excludes tiny denominators and clips the usable series before sector aggregation."))
    cells.append(
        code(
            "distribution_table = pd.DataFrame({\n"
            "    'series': ['surprise_pct_raw', 'surprise_pct_clean', 'quarterly_eps_yoy_pct_raw', 'quarterly_eps_yoy_pct_clean'],\n"
            "    'p01': [\n"
            "        quarterly_symbol['surprise_pct_raw'].quantile(0.01),\n"
            "        quarterly_symbol['surprise_pct'].quantile(0.01),\n"
            "        quarterly_symbol['quarterly_eps_yoy_pct_raw'].quantile(0.01),\n"
            "        quarterly_symbol['quarterly_eps_yoy_pct'].quantile(0.01),\n"
            "    ],\n"
            "    'median': [\n"
            "        quarterly_symbol['surprise_pct_raw'].median(),\n"
            "        quarterly_symbol['surprise_pct'].median(),\n"
            "        quarterly_symbol['quarterly_eps_yoy_pct_raw'].median(),\n"
            "        quarterly_symbol['quarterly_eps_yoy_pct'].median(),\n"
            "    ],\n"
            "    'p99': [\n"
            "        quarterly_symbol['surprise_pct_raw'].quantile(0.99),\n"
            "        quarterly_symbol['surprise_pct'].quantile(0.99),\n"
            "        quarterly_symbol['quarterly_eps_yoy_pct_raw'].quantile(0.99),\n"
            "        quarterly_symbol['quarterly_eps_yoy_pct'].quantile(0.99),\n"
            "    ],\n"
            "}).round(2)\n"
            "display(distribution_table)\n"
            "\n"
            "clip_settings = pd.DataFrame(\n"
            "    {'setting': ['lower_quantile', 'upper_quantile', 'min_abs_eps_base'],\n"
            "     'value': [\n"
            "         cleaning['outlier_controls']['lower_quantile'],\n"
            "         cleaning['outlier_controls']['upper_quantile'],\n"
            "         cleaning['outlier_controls']['min_abs_eps_base'],\n"
            "     ]}\n"
            ")\n"
            "clip_series_meta = pd.DataFrame({\n"
            "    key: value\n"
            "    for key, value in cleaning['outlier_controls'].items()\n"
            "    if isinstance(value, dict)\n"
            "}).T\n"
            "display(clip_settings)\n"
            "display(clip_series_meta)"
        )
    )

    cells.append(md("## 4. Cleaned sector relationship map\n\nOnce the ambiguous buckets are removed, the sector correlation tables become much more interpretable. This section uses the cleaned cap-weighted surprise series rather than the raw universe."))
    cells.append(
        code(
            "fig, ax = plt.subplots(figsize=(8.5, 7.0))\n"
            "sns.heatmap(sector_corr, cmap='RdBu_r', center=0.0, vmin=-1.0, vmax=1.0, square=True, ax=ax)\n"
            "ax.set_title('Cleaned same-quarter sector surprise correlation matrix')\n"
            "plt.tight_layout()\n"
            "plt.show()\n"
            "\n"
            "display(sector_surprise_pairs.head(12))\n"
            "display(sector_lead_lag.head(12))"
        )
    )

    cells.append(md("## 5. Sector market-cap and liquidity structure\n\nThe panel adds a time-varying size and liquidity layer by scaling current market cap with each symbol's monthly adjusted-price path and aggregating monthly dollar volume into sector-quarter turnover proxies. This is still an approximation because share counts are not point-in-time, but it is materially better than a static 2025 snapshot."))
    cells.append(
        code(
            "market_structure['quarter_end_date'] = pd.to_datetime(market_structure['quarter_end_date'])\n"
            "latest_quarter = market_structure['fiscal_quarter'].max()\n"
            "latest_structure = market_structure.loc[market_structure['fiscal_quarter'] == latest_quarter].copy()\n"
            "latest_structure = latest_structure.sort_values('market_cap_share', ascending=False)\n"
            "display(latest_structure[['sector', 'market_cap_share', 'turnover_proxy', 'market_cap_proxy_total']].head(11))\n"
            "\n"
            "print('The raw table uses level proxies; the charts below switch to cross-sectional ranks because they are more stable than absolute proxy levels across time.')\n"
            "top_sectors = latest_structure.head(5)['sector'].tolist()\n"
            "plot_frame = market_structure.loc[\n"
            "    (market_structure['sector'].isin(top_sectors)) & (market_structure['quarter_end_date'] >= '2020-01-01')\n"
            "].copy()\n"
            "plot_frame['market_cap_share_rank'] = plot_frame.groupby('quarter_end_date')['market_cap_share'].rank(pct=True)\n"
            "plot_frame['turnover_proxy_rank'] = plot_frame.groupby('quarter_end_date')['turnover_proxy'].rank(pct=True)\n"
            "fig, axes = plt.subplots(1, 2, figsize=(14, 4.5))\n"
            "sns.lineplot(data=plot_frame, x='quarter_end_date', y='market_cap_share_rank', hue='sector', ax=axes[0])\n"
            "axes[0].set_title('2020+ market-cap share rank by sector')\n"
            "axes[0].set_ylabel('cross-sectional rank (0-1)')\n"
            "axes[0].legend(frameon=False, loc='upper left')\n"
            "sns.lineplot(data=plot_frame, x='quarter_end_date', y='turnover_proxy_rank', hue='sector', ax=axes[1])\n"
            "axes[1].set_title('2020+ turnover rank by sector')\n"
            "axes[1].set_ylabel('cross-sectional rank (0-1)')\n"
            "axes[1].legend_.remove()\n"
            "plt.tight_layout()\n"
            "plt.show()"
        )
    )

    cells.append(md("## 6. Panel design and target definition\n\nThe target is **next-quarter sector ETF excess return vs SPY**. Earnings features are lagged one quarter so the model only sees information that would have been known after the prior earnings season. Market-cap, liquidity, and ETF price-state features are measured at the current quarter-end."))
    cells.append(
        code(
            "panel['quarter_end_date'] = pd.to_datetime(panel['quarter_end_date'])\n"
            "panel['post_2020'] = panel['fiscal_quarter'] >= '2020Q1'\n"
            "panel_snapshot = pd.DataFrame({\n"
            "    'metric': ['panel rows', 'quarters', 'sectors', 'features', 'post-2020 rows', 'holdout rows'],\n"
            "    'value': [\n"
            "        research_summary['panel_rows'],\n"
            "        research_summary['quarter_count'],\n"
            "        research_summary['sector_count'],\n"
            "        research_summary['feature_count'],\n"
            "        int(panel['post_2020'].sum()),\n"
            "        int(research_summary['holdout_ensemble_metrics'].get('observations', 0)),\n"
            "    ],\n"
            "})\n"
            "display(panel_snapshot)\n"
            "\n"
            "recent = panel.loc[panel['fiscal_quarter'] >= '2020Q1'].copy()\n"
            "fig, ax = plt.subplots(figsize=(6.6, 5.1))\n"
            "sns.regplot(\n"
            "    data=recent,\n"
            "    x='cap_weighted_quarterly_eps_yoy_pct_lag1_rank',\n"
            "    y='target_excess_return',\n"
            "    scatter_kws={'alpha': 0.35, 's': 28},\n"
            "    line_kws={'color': '#1d3557'},\n"
            "    ax=ax,\n"
            ")\n"
            "ax.set_title('2020+ slice: lagged EPS-growth rank vs next-quarter excess return')\n"
            "ax.set_xlabel('Lagged cap-weighted EPS-growth rank')\n"
            "ax.set_ylabel('Next-quarter excess return vs SPY')\n"
            "plt.tight_layout()\n"
            "plt.show()"
        )
    )

    cells.append(md("## 7. Ensemble model results\n\nThe point of the model layer is not to manufacture a heroic backtest. It is to test whether the cleaned sector earnings factors still carry signal after controlling for size, liquidity, and ETF price state. Read the holdout carefully: it is only three completed quarters in the current export."))
    cells.append(
        code(
            "display(metrics)\n"
            "\n"
            "fig, axes = plt.subplots(1, 2, figsize=(12.8, 4.4), sharey=False)\n"
            "val = metrics.loc[metrics['scope'] == 'validation'].copy()\n"
            "hold = metrics.loc[metrics['scope'] == 'holdout'].copy()\n"
            "sns.barplot(data=val, x='model_label', y='roc_auc', hue='model_label', legend=False, ax=axes[0], palette='Blues_d')\n"
            "axes[0].axhline(0.5, color='#e63946', linestyle='--', linewidth=1.0)\n"
            "axes[0].set_title('Validation ROC AUC by model')\n"
            "axes[0].tick_params(axis='x', rotation=25)\n"
            "sns.barplot(data=hold, x='model_label', y='roc_auc', hue='model_label', legend=False, ax=axes[1], palette='Greens_d')\n"
            "axes[1].axhline(0.5, color='#e63946', linestyle='--', linewidth=1.0)\n"
            "axes[1].set_title('Holdout ROC AUC by model')\n"
            "axes[1].tick_params(axis='x', rotation=25)\n"
            "plt.tight_layout()\n"
            "plt.show()"
        )
    )
    cells.append(
        code(
            "fig, axes = plt.subplots(1, 2, figsize=(13.2, 4.4))\n"
            "axes[0].plot(validation_strategy['quarter_end_date'], validation_strategy['portfolio_equity'], label='Top-3 sector basket', color='#1d3557', linewidth=2.0)\n"
            "axes[0].plot(validation_strategy['quarter_end_date'], validation_strategy['spy_equity'], label='SPY', color='#6c757d', linewidth=1.6)\n"
            "axes[0].set_title('Validation ranking strategy vs SPY')\n"
            "axes[0].legend(frameon=False)\n"
            "axes[1].plot(holdout_strategy['quarter_end_date'], holdout_strategy['portfolio_equity'], label='Top-3 sector basket', color='#2a9d8f', linewidth=2.0)\n"
            "axes[1].plot(holdout_strategy['quarter_end_date'], holdout_strategy['spy_equity'], label='SPY', color='#6c757d', linewidth=1.6)\n"
            "axes[1].set_title('Holdout ranking strategy vs SPY')\n"
            "axes[1].legend(frameon=False)\n"
            "plt.tight_layout()\n"
            "plt.show()\n"
            "\n"
            "strategy_table = pd.DataFrame([\n"
            "    {'scope': 'validation', **research_summary['validation_strategy']},\n"
            "    {'scope': 'holdout', **research_summary['holdout_strategy']},\n"
            "])\n"
            "display(strategy_table)"
        )
    )

    cells.append(md("## 8. Feature importance and relationship takeaways\n\nThe strongest average features are a blend of liquidity, lagged breadth/beat-rate, EPS-growth ranks, and price-state variables. In other words: cleaned earnings matter, but they matter alongside market structure and momentum rather than in isolation."))
    cells.append(
        code(
            "ensemble_features = (\n"
            "    feature_importance.loc[feature_importance['model_label'] == 'Average Ensemble']\n"
            "    .sort_values('importance', ascending=False)\n"
            "    .head(20)\n"
            "    .copy()\n"
            ")\n"
            "def feature_bucket(name: str) -> str:\n"
            "    if 'surprise' in name or 'eps' in name or 'beat_rate' in name or 'reported_eps' in name or 'estimated_eps' in name:\n"
            "        return 'Earnings'\n"
            "    if 'market_cap' in name or 'turnover' in name or 'dollar_volume' in name:\n"
            "        return 'Structure'\n"
            "    if name.startswith('sector_'):\n"
            "        return 'Sector identity'\n"
            "    return 'Price state'\n"
            "ensemble_features['bucket'] = ensemble_features['feature'].map(feature_bucket)\n"
            "palette = {'Earnings': '#264653', 'Structure': '#2a9d8f', 'Price state': '#e9c46a', 'Sector identity': '#e76f51'}\n"
            "fig, ax = plt.subplots(figsize=(10.5, 6.0))\n"
            "sns.barplot(\n"
            "    data=ensemble_features,\n"
            "    x='importance',\n"
            "    y='feature',\n"
            "    hue='bucket',\n"
            "    dodge=False,\n"
            "    palette=palette,\n"
            "    ax=ax,\n"
            ")\n"
            "ax.set_title('Top ensemble features')\n"
            "ax.legend(frameon=False, loc='lower right')\n"
            "plt.tight_layout()\n"
            "plt.show()\n"
            "display(ensemble_features[['feature', 'bucket', 'importance']])"
        )
    )

    cells.append(md("## 9. Holdout quarter picks\n\nThe live relevance of the model is in the most recent completed quarters. This is a tiny sample, so the table below should be read as a case study rather than proof of a durable edge."))
    cells.append(
        code(
            "holdout_latest = holdout_predictions.sort_values(['fiscal_quarter', 'ensemble_probability'], ascending=[True, False]).copy()\n"
            "display(holdout_strategy)\n"
            "display(holdout_latest[['fiscal_quarter', 'sector', 'etf_symbol', 'ensemble_probability', 'target_excess_return']].head(15))"
        )
    )

    cells.append(
        md(
            "## 10. Conclusions and caveats\n\n"
            "**What the cleaned research supports**\n"
            "- The sector cleanup was worth doing. The relationship tables become much more coherent once `UNKNOWN`, `OTHER`, and non-primary securities are removed from aggregate sector statistics.\n"
            "- Earnings information still shows up in the model after the cleanup, especially lagged beat-rate and lagged EPS-growth ranks.\n"
            "- Liquidity, market-cap share, and ETF price state are just as important as the earnings fields, which argues against reading sector leadership through fundamentals alone.\n"
            "- The post-2020 slice is the richest part of the dataset by breadth and therefore the most credible place to stress-test any sector earnings thesis.\n\n"
            "**What the cleaned research does not support yet**\n"
            "- A strong, repeatable outperformance claim from the current average ensemble. Validation ROC AUC is near random and the validation top-3 basket does not beat SPY on average excess return.\n"
            "- Over-interpretation of the 2025 holdout. The current holdout export covers only three completed quarters, so the better holdout AUC can easily be noise.\n"
            "- A truly point-in-time historical market-cap panel. The size layer uses a price-scaled proxy because historical share counts are not available in the current cache.\n\n"
            "**Natural next upgrades**\n"
            "1. Re-index sector earnings by reported-date windows instead of conservative quarter lags once a release-aware sector panel is available.\n"
            "2. Add true point-in-time share counts or shares-outstanding histories so sector size is not approximated from current market cap.\n"
            "3. Test cross-sectional targets such as next-quarter top-third sector rank, not just ETF excess return vs SPY."
        )
    )

    nb["cells"] = cells
    nb["metadata"] = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.11",
        },
    }
    return nb


def main() -> None:
    notebook = build_notebook()
    NOTEBOOK_PATH.write_text(nbf.writes(notebook), encoding="utf-8")
    print(f"Wrote {NOTEBOOK_PATH}")


if __name__ == "__main__":
    main()