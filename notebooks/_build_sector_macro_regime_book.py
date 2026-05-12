"""Build the macro-regime x sector-earnings research notebook.

Run:
    python notebooks/_build_sector_macro_regime_book.py
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK_PATH = PROJECT_ROOT / "notebooks" / "sector_macro_regime_book.ipynb"


def md(source: str) -> nbf.NotebookNode:
    return nbf.v4.new_markdown_cell(source)


def code(source: str) -> nbf.NotebookNode:
    return nbf.v4.new_code_cell(source)


def build_notebook() -> nbf.NotebookNode:
    nb = nbf.v4.new_notebook()
    cells: list[nbf.NotebookNode] = []

    cells.append(
        md(
            "# Macro Regime Shifts, Sector Earnings Troughs, and Reversal Windows\n\n"
            "**Goal.** Build the third research book by combining the repo's existing macro regime engine with the cleaned sector earnings panel. "
            "The notebook tests three ideas: macro regime shifts tend to arrive after earnings breadth deteriorates, sector EPS troughs often create tactical reversal windows, "
            "and the best reversals happen when macro conditions normalize alongside earnings. This revision also adds a direct lead/lag study and a small quarterly ML screen for regime detection.\n\n"
            "**Research questions**\n"
            "1. Which macro regimes consistently line up with strong or weak sector earnings breadth?\n"
            "2. Does earnings breadth lead macro improvement, or mostly confirm it after the fact?\n"
            "3. Which sectors are most sensitive to macro balance, and which sectors feed back most into the next macro move?\n"
            "4. Can a small quarterly ML model detect regime changes, benign states, or broad macro improvement from lagged earnings and sector context?\n"
            "5. When sector EPS growth hits a local trough, how often do earnings, macro balance, and sector relative returns improve over the next two quarters?\n\n"
            "**Notebook map**\n"
            "1. Setup and report loading\n"
            "2. Regime scorecard\n"
            "3. Earnings breadth through time\n"
            "4. Lead/lag and sector sensitivity\n"
            "5. Regime ML screen\n"
            "6. Regime transitions and deterioration\n"
            "7. Sector troughs and reversal windows\n"
            "8. Case studies and live implications\n"
            "9. Conclusions and caveats"
        )
    )

    cells.append(md("## 1. Setup and report loading"))
    cells.append(
        code(
            "import json\n"
            "from pathlib import Path\n"
            "\n"
            "import matplotlib.pyplot as plt\n"
            "import pandas as pd\n"
            "import seaborn as sns\n"
            "from IPython.display import display\n"
            "\n"
            "plt.rcParams.update({\n"
            "    'figure.figsize': (11.5, 4.8),\n"
            "    'figure.dpi': 120,\n"
            "    'axes.grid': True,\n"
            "    'grid.alpha': 0.22,\n"
            "    'axes.spines.top': False,\n"
            "    'axes.spines.right': False,\n"
            "    'font.size': 10,\n"
            "})\n"
            "sns.set_theme(style='whitegrid', context='notebook')\n"
            "pd.options.display.float_format = '{:,.3f}'.format\n"
            "\n"
            "PROJECT_ROOT = Path.cwd().parent if Path.cwd().name == 'notebooks' else Path.cwd()\n"
            "RESEARCH_DIR = PROJECT_ROOT / 'outputs' / 'sector_macro_regime_research'\n"
            "print('research dir:', RESEARCH_DIR)"
        )
    )
    cells.append(
        code(
            "with open(RESEARCH_DIR / 'sector_macro_regime_summary.json', encoding='utf-8') as f:\n"
            "    summary = json.load(f)\n"
            "\n"
            "macro_quarters = pd.read_csv(RESEARCH_DIR / 'macro_regime_quarterly_history.csv', parse_dates=['quarter_end_month', 'quarter_end_date'])\n"
            "panel = pd.read_csv(RESEARCH_DIR / 'sector_macro_regime_panel.csv', parse_dates=['quarter_end_date'])\n"
            "breadth = pd.read_csv(RESEARCH_DIR / 'quarterly_earnings_breadth.csv', parse_dates=['quarter_end_date'])\n"
            "lead_lag = pd.read_csv(RESEARCH_DIR / 'macro_earnings_lead_lag.csv')\n"
            "sector_sensitivity = pd.read_csv(RESEARCH_DIR / 'sector_macro_sensitivity.csv')\n"
            "regime_summary = pd.read_csv(RESEARCH_DIR / 'regime_earnings_summary.csv')\n"
            "transition_summary = pd.read_csv(RESEARCH_DIR / 'regime_transition_summary.csv')\n"
            "transition_episodes = pd.read_csv(RESEARCH_DIR / 'regime_transition_episode_table.csv', parse_dates=['quarter_end_date'])\n"
            "trough_events = pd.read_csv(RESEARCH_DIR / 'sector_earnings_trough_events.csv', parse_dates=['quarter_end_date'])\n"
            "trough_regime_summary = pd.read_csv(RESEARCH_DIR / 'sector_earnings_trough_regime_summary.csv')\n"
            "trough_sector_summary = pd.read_csv(RESEARCH_DIR / 'sector_earnings_trough_sector_summary.csv')\n"
            "regime_ml_metrics = pd.read_csv(RESEARCH_DIR / 'regime_ml_metrics.csv')\n"
            "regime_ml_feature_importance = pd.read_csv(RESEARCH_DIR / 'regime_ml_feature_importance.csv')\n"
            "regime_ml_validation_predictions = pd.read_csv(RESEARCH_DIR / 'regime_ml_validation_predictions.csv', parse_dates=['quarter_end_date'])\n"
            "regime_ml_holdout_predictions = pd.read_csv(RESEARCH_DIR / 'regime_ml_holdout_predictions.csv', parse_dates=['quarter_end_date'])\n"
            "\n"
            "regime_scorecard = regime_summary.loc[regime_summary['group_type'] == 'regime'].copy()\n"
            "regime_scorecard = regime_scorecard.sort_values('macro_balance_score', ascending=False).reset_index(drop=True)\n"
            "transition_summary['transition'] = transition_summary['prior_regime_label'] + ' -> ' + transition_summary['quarter_end_regime_label']\n"
            "\n"
            "print('quarters      :', summary['quarter_count'])\n"
            "print('panel rows    :', summary['panel_rows'])\n"
            "print('sectors       :', summary['sector_count'])\n"
            "print('transitions   :', summary['regime_transition_count'])\n"
            "print('trough events :', summary['trough_event_count'])\n"
            "print('current regime:', summary['current_regime'])"
        )
    )

    cells.append(
        md(
            "## 2. Regime scorecard\n\n"
            "The macro engine already compresses growth, inflation, and stress into named regimes. "
            "This section asks whether those regimes also separate strong sector earnings environments from weak ones."
        )
    )
    cells.append(
        code(
            "headline = pd.DataFrame({\n"
            "    'metric': ['current regime', 'quarters', 'sector-quarter rows', 'regime transitions', 'trough events'],\n"
            "    'value': [\n"
            "        summary['current_regime'],\n"
            "        summary['quarter_count'],\n"
            "        summary['panel_rows'],\n"
            "        summary['regime_transition_count'],\n"
            "        summary['trough_event_count'],\n"
            "    ],\n"
            "})\n"
            "display(headline)\n"
            "\n"
            "display(\n"
            "    regime_scorecard[[\n"
            "        'group_label',\n"
            "        'macro_balance_score',\n"
            "        'median_eps_growth',\n"
            "        'negative_eps_growth_share',\n"
            "        'mean_next_q_excess_return',\n"
            "        'hit_rate_next_q',\n"
            "    ]].round(3)\n"
            ")"
        )
    )
    cells.append(
        code(
            "plot_frame = regime_scorecard.copy()\n"
            "order = plot_frame['group_label'].tolist()\n"
            "fig, axes = plt.subplots(1, 2, figsize=(15, 5.5))\n"
            "sns.barplot(\n"
            "    data=plot_frame,\n"
            "    y='group_label',\n"
            "    x='median_eps_growth',\n"
            "    hue='group_label',\n"
            "    order=order,\n"
            "    dodge=False,\n"
            "    palette='viridis',\n"
            "    legend=False,\n"
            "    ax=axes[0],\n"
            ")\n"
            "axes[0].axvline(0.0, color='black', linestyle='--', linewidth=1.0)\n"
            "axes[0].set_title('Median sector EPS growth by macro regime')\n"
            "axes[0].set_xlabel('cap-weighted EPS growth YoY (%)')\n"
            "axes[0].set_ylabel('')\n"
            "\n"
            "sns.barplot(\n"
            "    data=plot_frame,\n"
            "    y='group_label',\n"
            "    x='mean_next_q_excess_return',\n"
            "    hue='group_label',\n"
            "    order=order,\n"
            "    dodge=False,\n"
            "    palette='mako',\n"
            "    legend=False,\n"
            "    ax=axes[1],\n"
            ")\n"
            "axes[1].axvline(0.0, color='black', linestyle='--', linewidth=1.0)\n"
            "axes[1].set_title('Average next-quarter excess return by regime')\n"
            "axes[1].set_xlabel('next-quarter excess return vs SPY')\n"
            "axes[1].set_ylabel('')\n"
            "plt.tight_layout()\n"
            "plt.show()"
        )
    )

    cells.append(
        md(
            "## 3. Earnings breadth through time\n\n"
            "The regime labels are easier to trust when they line up with broad deterioration or repair in sector earnings. "
            "Here we track the quarterly median EPS-growth line, the share of sectors with negative EPS growth, and the macro balance score."
        )
    )
    cells.append(
        code(
            "breadth_plot = breadth.copy()\n"
            "breadth_plot['median_eps_growth_4q'] = breadth_plot['median_eps_growth'].rolling(4, min_periods=2).mean()\n"
            "\n"
            "fig, axes = plt.subplots(2, 1, figsize=(13.5, 8.2), sharex=True)\n"
            "axes[0].plot(breadth_plot['quarter_end_date'], breadth_plot['median_eps_growth'], color='#264653', linewidth=2.0, label='Quarterly median EPS growth')\n"
            "axes[0].plot(breadth_plot['quarter_end_date'], breadth_plot['median_eps_growth_4q'], color='#2a9d8f', linewidth=2.0, label='4-quarter mean')\n"
            "axes[0].fill_between(\n"
            "    breadth_plot['quarter_end_date'],\n"
            "    0.0,\n"
            "    breadth_plot['median_eps_growth'],\n"
            "    where=breadth_plot['median_eps_growth'] < 0.0,\n"
            "    color='#e76f51',\n"
            "    alpha=0.25,\n"
            ")\n"
            "axes[0].axhline(0.0, color='black', linestyle='--', linewidth=1.0)\n"
            "axes[0].set_title('Sector earnings breadth weakens before and during macro stress')\n"
            "axes[0].set_ylabel('median EPS growth YoY (%)')\n"
            "axes[0].legend(frameon=False, loc='upper left')\n"
            "\n"
            "axes[1].plot(breadth_plot['quarter_end_date'], breadth_plot['macro_balance_score'], color='#355070', linewidth=2.2, label='Macro balance score')\n"
            "axes[1].axhline(0.0, color='black', linestyle='--', linewidth=1.0)\n"
            "axes[1].set_ylabel('macro balance score')\n"
            "axes[1].legend(frameon=False, loc='upper left')\n"
            "\n"
            "ax_right = axes[1].twinx()\n"
            "ax_right.plot(breadth_plot['quarter_end_date'], breadth_plot['negative_eps_growth_share'], color='#e56b6f', linewidth=1.8, label='Negative EPS-growth share')\n"
            "ax_right.set_ylabel('share of sectors < 0 EPS growth')\n"
            "ax_right.set_ylim(0.0, 1.0)\n"
            "\n"
            "plt.tight_layout()\n"
            "plt.show()"
        )
    )
    cells.append(
        code(
            "worst_quarters = breadth.nsmallest(12, 'median_eps_growth')[\n"
            "    ['fiscal_quarter', 'regime_label', 'median_eps_growth', 'negative_eps_growth_share', 'mean_next_q_excess_return']\n"
            "]\n"
            "display(worst_quarters.round(3))"
        )
    )

    cells.append(
        md(
            "## 4. Lead/lag and sector sensitivity\n\n"
            "Positive lead quarters mean the source series leads the target by that many quarters. Negative lead quarters mean the source mostly trails and confirms a move that has already started. "
            "This section also checks which sectors respond most to macro balance and which sectors appear most connected to the next macro balance change."
        )
    )
    cells.append(
        code(
            "lead_lag_focus = lead_lag.loc[\n"
            "    lead_lag['relationship_label'].isin([\n"
            "        'Median EPS Growth vs Macro Balance Change',\n"
            "        'Negative EPS Share vs Macro Balance Change',\n"
            "        'Macro Balance vs Median EPS Growth',\n"
            "        'Macro Balance vs Negative EPS Share',\n"
            "        'Stress Axis vs Median EPS Growth',\n"
            "    ])\n"
            "].copy()\n"
            "heatmap = lead_lag_focus.pivot(index='relationship_label', columns='lead_quarters', values='correlation')\n"
            "fig, ax = plt.subplots(figsize=(12.5, 4.8))\n"
            "sns.heatmap(heatmap, annot=True, fmt='.2f', cmap='RdBu_r', center=0.0, ax=ax)\n"
            "ax.set_title('Lead/lag map: positive columns mean the source leads')\n"
            "ax.set_xlabel('lead quarters')\n"
            "ax.set_ylabel('')\n"
            "plt.tight_layout()\n"
            "plt.show()\n"
            "\n"
            "display(\n"
            "    lead_lag.loc[lead_lag['lead_quarters'] > 0]\n"
            "    .sort_values(['abs_correlation', 'lead_quarters'], ascending=[False, True])\n"
            "    .head(12)[['relationship_label', 'lead_quarters', 'correlation', 'observation_count']]\n"
            "    .round(3)\n"
            ")"
        )
    )
    cells.append(
        code(
            "sector_view = sector_sensitivity[[\n"
            "    'sector',\n"
            "    'macro_to_next_excess_corr',\n"
            "    'macro_to_current_eps_growth_corr',\n"
            "    'earnings_to_next_macro_change_corr',\n"
            "    'earnings_to_next_excess_corr',\n"
            "    'quarter_count',\n"
            "]].copy()\n"
            "display(sector_view.round(3))\n"
            "\n"
            "plot_macro = sector_sensitivity.sort_values('macro_to_next_excess_corr', ascending=False).copy()\n"
            "plot_feedback = sector_sensitivity.sort_values('earnings_to_next_macro_change_corr', ascending=False).copy()\n"
            "fig, axes = plt.subplots(1, 2, figsize=(15.5, 5.8))\n"
            "sns.barplot(\n"
            "    data=plot_macro,\n"
            "    y='sector',\n"
            "    x='macro_to_next_excess_corr',\n"
            "    hue='sector',\n"
            "    dodge=False,\n"
            "    palette='rocket',\n"
            "    legend=False,\n"
            "    ax=axes[0],\n"
            ")\n"
            "axes[0].axvline(0.0, color='black', linestyle='--', linewidth=1.0)\n"
            "axes[0].set_title('Current macro balance vs next-quarter sector excess return')\n"
            "axes[0].set_xlabel('correlation')\n"
            "axes[0].set_ylabel('')\n"
            "\n"
            "sns.barplot(\n"
            "    data=plot_feedback,\n"
            "    y='sector',\n"
            "    x='earnings_to_next_macro_change_corr',\n"
            "    hue='sector',\n"
            "    dodge=False,\n"
            "    palette='crest',\n"
            "    legend=False,\n"
            "    ax=axes[1],\n"
            ")\n"
            "axes[1].axvline(0.0, color='black', linestyle='--', linewidth=1.0)\n"
            "axes[1].set_title('Current sector EPS growth vs next-quarter macro balance change')\n"
            "axes[1].set_xlabel('correlation')\n"
            "axes[1].set_ylabel('')\n"
            "plt.tight_layout()\n"
            "plt.show()"
        )
    )

    cells.append(
        md(
            "## 5. Regime ML screen\n\n"
            "This is a small quarterly ML exercise, not a production regime engine. The point is to test whether lagged earnings breadth plus cross-sector context can detect exact label flips, broader macro improvement, or benign-state conditions. "
            "If exact regime-change labels stay noisy but improvement-state targets hold up, the right use is a regime-risk score rather than a label oracle."
        )
    )
    cells.append(
        code(
            "ml_validation = regime_ml_metrics.loc[regime_ml_metrics['scope'] == 'validation'].copy()\n"
            "ml_validation = ml_validation.sort_values(['roc_auc', 'target_label'], ascending=[False, True])\n"
            "display(\n"
            "    ml_validation[[\n"
            "        'target_label',\n"
            "        'model_label',\n"
            "        'sample_count',\n"
            "        'positive_rate',\n"
            "        'roc_auc',\n"
            "        'precision',\n"
            "        'recall',\n"
            "    ]].round(3)\n"
            ")\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(13.5, 5.4))\n"
            "sns.barplot(\n"
            "    data=ml_validation,\n"
            "    y='target_label',\n"
            "    x='roc_auc',\n"
            "    hue='model_label',\n"
            "    ax=ax,\n"
            ")\n"
            "ax.axvline(0.5, color='black', linestyle='--', linewidth=1.0)\n"
            "ax.set_title('Quarterly regime ML: exact label flips are noisy, macro improvement is more learnable')\n"
            "ax.set_xlabel('validation ROC AUC')\n"
            "ax.set_ylabel('')\n"
            "ax.legend(frameon=False, loc='lower right')\n"
            "plt.tight_layout()\n"
            "plt.show()"
        )
    )
    cells.append(
        code(
            "focus_targets = [\n"
            "    'Macro Balance Improves > 0.5 Within Next 2Q',\n"
            "    'Current Regime Is Benign',\n"
            "    'Any Regime Change Within Next 2Q',\n"
            "]\n"
            "feature_view = regime_ml_feature_importance.loc[\n"
            "    (regime_ml_feature_importance['model_label'] == 'Average Ensemble')\n"
            "    & (regime_ml_feature_importance['target_label'].isin(focus_targets))\n"
            "].copy()\n"
            "display(\n"
            "    feature_view.groupby('target_label').head(10)[['target_label', 'feature', 'importance']].round(4)\n"
            ")\n"
            "\n"
            "best_target = (\n"
            "    ml_validation.sort_values('roc_auc', ascending=False)\n"
            "    .loc[ml_validation['model_label'] == 'Average Ensemble']\n"
            "    .iloc[0]\n"
            ")\n"
            "best_target_key = best_target['target_key']\n"
            "best_target_label = best_target['target_label']\n"
            "best_features = regime_ml_feature_importance.loc[\n"
            "    (regime_ml_feature_importance['target_key'] == best_target_key)\n"
            "    & (regime_ml_feature_importance['model_label'] == 'Average Ensemble')\n"
            "].head(12).copy()\n"
            "fig, ax = plt.subplots(figsize=(11.8, 5.2))\n"
            "sns.barplot(\n"
            "    data=best_features,\n"
            "    y='feature',\n"
            "    x='importance',\n"
            "    hue='feature',\n"
            "    dodge=False,\n"
            "    palette='viridis',\n"
            "    legend=False,\n"
            "    ax=ax,\n"
            ")\n"
            "ax.set_title(f'Top ensemble features for {best_target_label}')\n"
            "ax.set_xlabel('normalized importance')\n"
            "ax.set_ylabel('')\n"
            "plt.tight_layout()\n"
            "plt.show()\n"
            "\n"
            "recent_holdout = regime_ml_holdout_predictions.loc[\n"
            "    regime_ml_holdout_predictions['target_key'].isin(['macro_improves_next_window', 'current_regime_is_benign'])\n"
            "].copy()\n"
            "display(\n"
            "    recent_holdout.sort_values(['target_label', 'quarter_end_date'], ascending=[True, False]).head(12)[[\n"
            "        'target_label',\n"
            "        'fiscal_quarter',\n"
            "        'quarter_end_regime_label',\n"
            "        'actual_target',\n"
            "        'ensemble_probability',\n"
            "        'macro_balance_score',\n"
            "        'median_eps_growth',\n"
            "        'negative_eps_growth_share',\n"
            "    ]].round(3)\n"
            ")"
        )
    )

    cells.append(
        md(
            "## 6. Regime transitions and deterioration\n\n"
            "The transition tables look at what earnings breadth looked like going into a new regime. "
            "If the user's thesis is right, the weakest transitions should show lower entry EPS growth and a higher share of sectors already in negative growth."
        )
    )
    cells.append(
        code(
            "plot_transitions = transition_summary.sort_values(\n"
            "    ['transition_count', 'avg_entry_median_eps_growth'],\n"
            "    ascending=[False, True],\n"
            ").head(12).copy()\n"
            "display(plot_transitions[[\n"
            "    'transition',\n"
            "    'transition_count',\n"
            "    'avg_entry_macro_balance_score',\n"
            "    'avg_entry_median_eps_growth',\n"
            "    'avg_next_median_eps_growth',\n"
            "    'earnings_rebound_next_q_rate',\n"
            "    'breadth_rebound_next_q_rate',\n"
            "]].round(3))\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(11.5, 6.5))\n"
            "scatter = ax.scatter(\n"
            "    plot_transitions['avg_entry_macro_balance_score'],\n"
            "    plot_transitions['avg_entry_median_eps_growth'],\n"
            "    s=plot_transitions['transition_count'] * 220,\n"
            "    c=plot_transitions['earnings_rebound_next_q_rate'],\n"
            "    cmap='RdYlGn',\n"
            "    edgecolor='black',\n"
            "    linewidth=0.6,\n"
            "    alpha=0.85,\n"
            ")\n"
            "for _, row in plot_transitions.iterrows():\n"
            "    ax.text(\n"
            "        row['avg_entry_macro_balance_score'] + 0.03,\n"
            "        row['avg_entry_median_eps_growth'] + 0.2,\n"
            "        row['transition'],\n"
            "        fontsize=8,\n"
            "    )\n"
            "ax.axvline(0.0, color='black', linestyle='--', linewidth=1.0)\n"
            "ax.axhline(0.0, color='black', linestyle='--', linewidth=1.0)\n"
            "ax.set_title('Frequent regime transitions cluster around weaker earnings entry points')\n"
            "ax.set_xlabel('entry macro balance score')\n"
            "ax.set_ylabel('entry median sector EPS growth YoY (%)')\n"
            "cbar = plt.colorbar(scatter, ax=ax)\n"
            "cbar.set_label('next-quarter earnings rebound rate')\n"
            "plt.tight_layout()\n"
            "plt.show()"
        )
    )
    cells.append(
        code(
            "display(\n"
            "    transition_episodes.sort_values('quarter_end_date', ascending=False).head(12)[[\n"
            "        'fiscal_quarter',\n"
            "        'prior_regime_label',\n"
            "        'quarter_end_regime_label',\n"
            "        'prior_median_eps_growth_1q',\n"
            "        'median_eps_growth',\n"
            "        'next_median_eps_growth_1q',\n"
            "        'negative_eps_growth_share',\n"
            "        'earnings_rebound_next_q',\n"
            "        'mean_next_q_excess_return',\n"
            "    ]].round(3)\n"
            ")"
        )
    )

    cells.append(
        md(
            "## 7. Sector troughs and reversal windows\n\n"
            "A trough event is defined as a sector quarter where cap-weighted EPS growth is the lowest reading in the last four quarters, still negative, and still worsening on a two-quarter delta. "
            "That isolates local capitulation points rather than every weak quarter."
        )
    )
    cells.append(
        code(
            "display(\n"
            "    trough_regime_summary[[\n"
            "        'quarter_end_regime_label',\n"
            "        'trough_events',\n"
            "        'avg_trough_eps_growth',\n"
            "        'eps_rebound_next_2q_rate',\n"
            "        'eps_normalizes_next_window_rate',\n"
            "        'macro_shift_to_benign_next_window_rate',\n"
            "        'avg_two_quarter_excess_return',\n"
            "    ]].round(3)\n"
            ")\n"
            "\n"
            "display(\n"
            "    trough_sector_summary.head(11)[[\n"
            "        'sector',\n"
            "        'trough_events',\n"
            "        'avg_trough_eps_growth',\n"
            "        'eps_rebound_next_q_rate',\n"
            "        'avg_two_quarter_excess_return',\n"
            "    ]].round(3)\n"
            ")"
        )
    )
    cells.append(
        code(
            "plot_regimes = trough_regime_summary.sort_values('eps_rebound_next_2q_rate', ascending=False).copy()\n"
            "fig, axes = plt.subplots(1, 2, figsize=(15.5, 5.8))\n"
            "sns.barplot(\n"
            "    data=plot_regimes,\n"
            "    y='quarter_end_regime_label',\n"
            "    x='eps_rebound_next_2q_rate',\n"
            "    hue='quarter_end_regime_label',\n"
            "    dodge=False,\n"
            "    palette='crest',\n"
            "    legend=False,\n"
            "    ax=axes[0],\n"
            ")\n"
            "axes[0].set_title('How often troughs rebound within two quarters')\n"
            "axes[0].set_xlabel('EPS rebound rate')\n"
            "axes[0].set_ylabel('')\n"
            "\n"
            "sns.barplot(\n"
            "    data=plot_regimes,\n"
            "    y='quarter_end_regime_label',\n"
            "    x='avg_two_quarter_excess_return',\n"
            "    hue='quarter_end_regime_label',\n"
            "    dodge=False,\n"
            "    palette='flare',\n"
            "    legend=False,\n"
            "    ax=axes[1],\n"
            ")\n"
            "axes[1].axvline(0.0, color='black', linestyle='--', linewidth=1.0)\n"
            "axes[1].set_title('Average two-quarter excess return after a trough')\n"
            "axes[1].set_xlabel('two-quarter excess return vs SPY')\n"
            "axes[1].set_ylabel('')\n"
            "plt.tight_layout()\n"
            "plt.show()"
        )
    )
    cells.append(
        code(
            "fig, ax = plt.subplots(figsize=(11.2, 6.2))\n"
            "scatter = ax.scatter(\n"
            "    trough_events['cap_weighted_quarterly_eps_yoy_pct'],\n"
            "    trough_events['two_quarter_excess_return'],\n"
            "    c=trough_events['macro_balance_improvement_next_window'],\n"
            "    s=85,\n"
            "    cmap='RdYlGn',\n"
            "    alpha=0.82,\n"
            "    edgecolors='white',\n"
            "    linewidths=0.5,\n"
            ")\n"
            "ax.axvline(0.0, color='black', linestyle='--', linewidth=1.0)\n"
            "ax.axhline(0.0, color='black', linestyle='--', linewidth=1.0)\n"
            "ax.set_title('Deeper troughs need macro improvement to turn into durable excess return')\n"
            "ax.set_xlabel('trough EPS growth YoY (%)')\n"
            "ax.set_ylabel('two-quarter excess return vs SPY')\n"
            "cbar = plt.colorbar(scatter, ax=ax)\n"
            "cbar.set_label('macro balance improvement over next two quarters')\n"
            "plt.tight_layout()\n"
            "plt.show()\n"
            "\n"
            "display(\n"
            "    trough_events.nsmallest(12, 'cap_weighted_quarterly_eps_yoy_pct')[[\n"
            "        'fiscal_quarter',\n"
            "        'sector',\n"
            "        'quarter_end_regime_label',\n"
            "        'cap_weighted_quarterly_eps_yoy_pct',\n"
            "        'target_excess_return',\n"
            "        'two_quarter_excess_return',\n"
            "        'macro_balance_improvement_next_window',\n"
            "        'eps_rebound_next_2q',\n"
            "        'macro_regime_change_next_window',\n"
            "    ]].round(3)\n"
            ")"
        )
    )

    cells.append(
        md(
            "## 8. Case studies and live implications\n\n"
            "The deepest troughs are concentrated in familiar stress episodes. "
            "Looking at them directly is useful because the timing problem is not simply about buying the worst print; it is about buying when earnings and macro conditions begin to repair together."
        )
    )
    cells.append(
        code(
            "spotlight_quarters = ['2008Q4', '2015Q4', '2020Q2', '2022Q4']\n"
            "spotlight_events = trough_events.loc[trough_events['fiscal_quarter'].isin(spotlight_quarters)].copy()\n"
            "spotlight_events = spotlight_events.sort_values(['fiscal_quarter', 'sector'])\n"
            "display(\n"
            "    spotlight_events[[\n"
            "        'fiscal_quarter',\n"
            "        'sector',\n"
            "        'quarter_end_regime_label',\n"
            "        'cap_weighted_quarterly_eps_yoy_pct',\n"
            "        'target_excess_return',\n"
            "        'two_quarter_excess_return',\n"
            "        'macro_balance_improvement_next_window',\n"
            "        'macro_shift_to_benign_next_window',\n"
            "    ]].round(3)\n"
            ")\n"
            "\n"
            "recent_transitions = transition_episodes.sort_values('quarter_end_date', ascending=False).head(10)\n"
            "display(\n"
            "    recent_transitions[[\n"
            "        'fiscal_quarter',\n"
            "        'prior_regime_label',\n"
            "        'quarter_end_regime_label',\n"
            "        'prior_median_eps_growth_1q',\n"
            "        'median_eps_growth',\n"
            "        'next_median_eps_growth_1q',\n"
            "        'earnings_rebound_next_q',\n"
            "        'mean_next_q_excess_return',\n"
            "    ]].round(3)\n"
            ")"
        )
    )
    cells.append(
        code(
            "weakest_regime = regime_scorecard.nsmallest(1, 'median_eps_growth').iloc[0]\n"
            "best_reversal_regime = trough_regime_summary.sort_values(\n"
            "    ['eps_rebound_next_2q_rate', 'avg_two_quarter_excess_return'],\n"
            "    ascending=[False, False],\n"
            ").iloc[0]\n"
            "most_common_transition = transition_summary.sort_values('transition_count', ascending=False).iloc[0]\n"
            "\n"
            "print('Weakest regime by median EPS growth:', weakest_regime['group_label'])\n"
            "print('  median EPS growth        :', round(float(weakest_regime['median_eps_growth']), 3))\n"
            "print('  negative EPS-growth share:', round(float(weakest_regime['negative_eps_growth_share']), 3))\n"
            "print()\n"
            "print('Best trough-reversal regime:', best_reversal_regime['quarter_end_regime_label'])\n"
            "print('  EPS rebound rate over next 2Q :', round(float(best_reversal_regime['eps_rebound_next_2q_rate']), 3))\n"
            "print('  avg 2Q excess return          :', round(float(best_reversal_regime['avg_two_quarter_excess_return']), 3))\n"
            "print()\n"
            "print('Most common transition:', most_common_transition['transition'])\n"
            "print('  transition count             :', int(most_common_transition['transition_count']))\n"
            "print('  entry median EPS growth      :', round(float(most_common_transition['avg_entry_median_eps_growth']), 3))\n"
            "print('  next-quarter rebound rate    :', round(float(most_common_transition['earnings_rebound_next_q_rate']), 3))"
        )
    )

    cells.append(
        md(
            "## 9. Conclusions and caveats\n\n"
            "**Takeaways**\n"
            "- The regime engine does separate earnings environments: the weakest macro states carry lower median EPS growth and far more sectors in negative growth.\n"
            "- The lead/lag map says earnings are not a clean one-quarter regime oracle. Macro balance and sector earnings mostly move together, while the strongest forward-looking signal is broader macro improvement rather than exact label flips.\n"
            "- The small quarterly ML block can rank macro improvement and benign-state conditions better than it can guess every exact regime change. That is useful, but it argues for a risk score rather than a hard switch model.\n"
            "- Sector troughs often do rebound in earnings terms, but price follow-through is selective. The better reversal windows are the ones where the macro balance score improves or the regime shifts into a more benign state within the next two quarters.\n\n"
            "**Caveats**\n"
            "- The study uses sector ETF returns as liquid implementation proxies, not direct sector baskets built from every underlying security.\n"
            "- Trough detection is intentionally simple and rule-based. It is designed for robust screening, not for proving a structural turning-point model.\n"
            "- Macro regimes are monthly and sector earnings are quarterly, so timing is necessarily coarse. The right operational use is regime-aware ranking and sizing, not precise day-level entry timing.\n"
            "- The ML sample is only about two decades of quarterly history. Any useful result here should be treated as directional evidence, not as a stable production estimate."
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
            "pygments_lexer": "ipython3",
        },
    }
    return nb


def main() -> None:
    NOTEBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    notebook = build_notebook()
    nbf.write(notebook, NOTEBOOK_PATH)
    print(f"Wrote notebook to {NOTEBOOK_PATH}")


if __name__ == "__main__":
    main()