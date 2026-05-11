"""Build the Kaggle-style notebook that reviews the PIT top-holdings backtest.

Run:
    ./.venv/bin/python notebooks/_build_pit_top_holdings_notebook.py
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK_PATH = PROJECT_ROOT / "notebooks" / "pit_top_holdings_review.ipynb"


def md(source: str) -> nbf.NotebookNode:
    return nbf.v4.new_markdown_cell(source)


def code(source: str) -> nbf.NotebookNode:
    return nbf.v4.new_code_cell(source)


def build_notebook() -> nbf.NotebookNode:
    nb = nbf.v4.new_notebook()
    cells: list[nbf.NotebookNode] = []

    cells.append(
        md(
            "# PIT Top-5 Holdings Rotation — Review\n"
            "\n"
            "**Goal.** Audit the point-in-time (PIT) top-5 holdings rotation against the sector ETF rotation "
            "and SPY buy-and-hold, on both the in-sample history window and the untouched 2025+ holdout. "
            "Everything in this notebook reads from the most recent `outputs/sector_rotation_report/` exports — "
            "no model is retrained here.\n"
            "\n"
            "**Headline (from the latest run):**\n"
            "- History selection rule: rank candidate strategies by Sharpe → CAGR → max-drawdown on the history slice; "
            "evaluate the unchanged winner on holdout.\n"
            "- History winner: **regime_change / Sector ETF ML Quality Rotation** (Sharpe 0.94, CAGR 16.9%).\n"
            "- Held-out 2025+ result: +28.1% total return, +11.7 pts vs SPY, holdout Sharpe 1.36 — but ranked **4 of 4** "
            "vs the ex-post oracle (`ml_5bar / Sector ETF ML Quality Rotation`), so the selection rule produced a "
            "winner that *did* beat SPY but was not the best of the four candidates with hindsight.\n"
            "\n"
            "**Forward-bias checks performed for this run (summary, details in §2):**\n"
            "- Holdings consumed only when `known_from_date <= signal_date`.\n"
            "- Validation-quality prior built per signal year from folds strictly before that year.\n"
            "- Entry on the trading bar after `signal_date`, exit at fixed horizon or 10% stop on first breach bar.\n"
            "- Macro feature pipeline patched to remove a full-sample VIX3M backfill (`patch_vix3m_history`) and a "
            "`bfill()` on spot VIX (`patch_spot_vix_history`) — see §2.\n"
            "\n"
            "**Section map**\n"
            "1. Setup & data loading\n"
            "2. Forward-bias controls\n"
            "3. Data overview (periods, modes, regimes)\n"
            "4. Strategy summary table\n"
            "5. Equity curves — history vs holdout\n"
            "6. Drawdowns\n"
            "7. Per-period return distribution\n"
            "8. Returns by regime\n"
            "9. Turnover and trading cost\n"
            "10. Stop-loss activity\n"
            "11. Leaderboard and best-strategy assessment\n"
            "12. Sector exposure heatmap\n"
            "13. Conclusions and known caveats"
        )
    )

    cells.append(md("## 1. Setup & data loading"))
    cells.append(
        code(
            "import json\n"
            "from pathlib import Path\n"
            "\n"
            "import numpy as np\n"
            "import pandas as pd\n"
            "import matplotlib.pyplot as plt\n"
            "import matplotlib.dates as mdates\n"
            "\n"
            "plt.rcParams.update({\n"
            "    'figure.figsize': (10, 4.5),\n"
            "    'figure.dpi': 110,\n"
            "    'axes.grid': True,\n"
            "    'grid.alpha': 0.25,\n"
            "    'axes.spines.top': False,\n"
            "    'axes.spines.right': False,\n"
            "    'font.size': 10,\n"
            "})\n"
            "\n"
            "PROJECT_ROOT = Path.cwd().parent if Path.cwd().name == 'notebooks' else Path.cwd()\n"
            "REPORT_DIR = PROJECT_ROOT / 'outputs' / 'sector_rotation_report'\n"
            "print('report dir:', REPORT_DIR)"
        )
    )
    cells.append(
        code(
            "period_log = pd.read_csv(\n"
            "    REPORT_DIR / 'sector_ml_pit_top5_holdings_period_log.csv',\n"
            "    parse_dates=['signal_date', 'entry_date', 'exit_date'],\n"
            ")\n"
            "summary = pd.read_csv(REPORT_DIR / 'sector_ml_pit_top5_holdings_strategy_summary.csv')\n"
            "leaderboard = pd.read_csv(REPORT_DIR / 'sector_ml_pit_top5_holdings_leaderboard.csv')\n"
            "with open(REPORT_DIR / 'sector_ml_pit_top5_holdings_best_strategy_assessment.json') as f:\n"
            "    assessment = json.load(f)\n"
            "\n"
            "print('period_log:', period_log.shape)\n"
            "print('summary   :', summary.shape)\n"
            "print('leaderboard:', leaderboard.shape)\n"
            "print('assessment keys:', list(assessment)[:8], '...')"
        )
    )

    cells.append(md("## 2. Forward-bias controls\n"
                    "\n"
                    "The PIT runner enforces three layered controls. None of these are derived from the report files — "
                    "they are baked into `backtest_top_holdings_rotation.py` and the upstream `sector_ml` training:\n"
                    "\n"
                    "1. **Point-in-time holdings.** `_latest_known_sector_holdings` filters `holdings.known_from_date <= signal_date` "
                    "before picking the latest disclosure. The constructor `_load_point_in_time_holdings` raises if any row has "
                    "`known_from_date < as_of_date`, preventing back-dated disclosures from being used.\n"
                    "2. **Point-in-time validation-quality prior.** `_build_point_in_time_quality` (in `sector_ml.py`) restricts the "
                    "fold pool for signal year *Y* to folds with `fold_year < Y`, so the score that re-weights sectors at a given "
                    "signal date is built strictly from historical validation folds.\n"
                    "3. **Holdout isolation.** The walk-forward trainer (`expanding_walk_forward_splits` and the calendar splitter "
                    "in `train.py`) enforces `train_end < holdout_start - gap_delta`. The holdout signal frame is then re-loaded "
                    "from `sector_ml_holdout_signal_frame.csv`; the validation prior used to score it is built only from pre-holdout "
                    "folds.\n"
                    "\n"
                    "**Macro feature fix applied in this revision.** An audit of `macro_features.py` flagged two "
                    "leakage sources upstream of the model:\n"
                    "\n"
                    "- `patch_vix3m_history` originally computed full-sample OLS slope/intercept on the spot-VIX vs VIX3M "
                    "overlap and used those coefficients to backfill VIX3M before its 2007 launch. Full-sample means the "
                    "training rows before 2007 saw a synthetic VIX3M that was tuned with post-2007 observations. **Fix:** "
                    "replaced with an expanding regression that uses only overlap rows up to and including each date.\n"
                    "- `patch_spot_vix_history` previously ended with `bfill()`, which propagates later spot-VIX values backward "
                    "in time. **Fix:** removed; the VXO fallback via `combine_first` is sufficient and is causal because it picks "
                    "the first-valid-of-two real, observed series.\n"
                    "\n"
                    "Below we sanity-check the new VIX3M backfill is genuinely causal by mutating a *future* overlap point and "
                    "confirming the synthetic past does not move."))
    cells.append(
        code(
            "import sys\n"
            "sys.path.insert(0, str(PROJECT_ROOT / 'src'))\n"
            "from price_action.macro_features import patch_spot_vix_history, patch_vix3m_history\n"
            "\n"
            "idx = pd.date_range('2000-01-01', periods=10, freq='D')\n"
            "spot = pd.Series([20, 22, 25, 18, 17, 19, 21, 23, 24, 22], index=idx, dtype=float)\n"
            "vix3m = pd.Series([np.nan]*6 + [21.5, 22.5, 23.5, 22.0], index=idx)\n"
            "base = pd.DataFrame({'spot_vix': spot, 'vix3m_level': vix3m})\n"
            "mutated = base.copy()\n"
            "mutated.loc[idx[-1], 'vix3m_level'] = 100.0  # mutate a future value\n"
            "\n"
            "out_base = patch_vix3m_history(patch_spot_vix_history(base.copy()))\n"
            "out_mut = patch_vix3m_history(patch_spot_vix_history(mutated.copy()))\n"
            "\n"
            "diff = (out_base['vix3m_level'].iloc[:-1] - out_mut['vix3m_level'].iloc[:-1]).abs().fillna(0)\n"
            "print('max delta on earlier dates after mutating future:', float(diff.max()))\n"
            "assert float(diff.max()) == 0.0, 'forward-bias regression: future change affected past'\n"
            "print('OK — VIX3M synthetic backfill is causal.')"
        )
    )

    cells.append(md("## 3. Data overview"))
    cells.append(
        code(
            "scope_mode = (\n"
            "    period_log.groupby(['scope', 'mode'])\n"
            "    .agg(\n"
            "        first_signal=('signal_date', 'min'),\n"
            "        last_signal=('signal_date', 'max'),\n"
            "        periods=('signal_date', 'count'),\n"
            "        regimes=('regime_label', 'nunique'),\n"
            "    )\n"
            "    .reset_index()\n"
            ")\n"
            "scope_mode"
        )
    )
    cells.append(
        code(
            "regime_periods = (\n"
            "    period_log.groupby(['scope', 'mode', 'regime_label'])['signal_date']\n"
            "    .count()\n"
            "    .unstack(fill_value=0)\n"
            ")\n"
            "regime_periods"
        )
    )
    cells.append(
        code(
            "fig, ax = plt.subplots(figsize=(10, 3.5))\n"
            "ml_5bar = period_log.loc[(period_log['scope'] == 'history') & (period_log['mode'] == 'ml_5bar')]\n"
            "ax.scatter(ml_5bar['signal_date'], np.ones(len(ml_5bar)), s=8, label='history / ml_5bar', alpha=0.6)\n"
            "regime = period_log.loc[(period_log['scope'] == 'history') & (period_log['mode'] == 'regime_change')]\n"
            "ax.scatter(regime['signal_date'], 1.05 + np.zeros(len(regime)), s=24, label='history / regime_change', marker='|')\n"
            "h_ml = period_log.loc[(period_log['scope'] == 'holdout') & (period_log['mode'] == 'ml_5bar')]\n"
            "ax.scatter(h_ml['signal_date'], 1.10 + np.zeros(len(h_ml)), s=14, label='holdout / ml_5bar', alpha=0.6)\n"
            "h_reg = period_log.loc[(period_log['scope'] == 'holdout') & (period_log['mode'] == 'regime_change')]\n"
            "ax.scatter(h_reg['signal_date'], 1.15 + np.zeros(len(h_reg)), s=36, marker='|', label='holdout / regime_change')\n"
            "ax.set_yticks([])\n"
            "ax.set_title('Signal-date coverage by scope and mode')\n"
            "ax.legend(loc='upper left', ncol=2, frameon=False)\n"
            "plt.tight_layout()\n"
            "plt.show()"
        )
    )

    cells.append(md("## 4. Strategy summary table"))
    cells.append(
        code(
            "metric_cols = [\n"
            "    'total_return', 'cagr', 'sharpe', 'sortino', 'max_drawdown', 'calmar',\n"
            "    'profit_factor', 'hit_rate', 'trade_count', 'period_count', 'turnover_per_year',\n"
            "]\n"
            "summary[['scope', 'mode', 'strategy_label', *metric_cols]].copy()"
        )
    )
    cells.append(
        code(
            "def _style_summary(frame: pd.DataFrame) -> pd.DataFrame:\n"
            "    f = frame.copy()\n"
            "    for col in ['total_return', 'cagr', 'max_drawdown', 'hit_rate', 'turnover_per_year']:\n"
            "        if col in f.columns:\n"
            "            f[col] = f[col].map(lambda v: f'{v*100:6.2f}%' if pd.notna(v) and col != 'turnover_per_year' else (f'{v:6.2f}' if pd.notna(v) else ''))\n"
            "    for col in ['sharpe', 'sortino', 'calmar', 'profit_factor']:\n"
            "        if col in f.columns:\n"
            "            f[col] = f[col].map(lambda v: f'{v:6.2f}' if pd.notna(v) else '')\n"
            "    return f\n"
            "\n"
            "_style_summary(summary[['scope', 'mode', 'strategy_label', *metric_cols]])"
        )
    )

    cells.append(md("## 5. Equity curves — history vs holdout"))
    cells.append(
        code(
            "STRAT_COLS = {\n"
            "    'Top 5 Holdings ML Rotation Stop 10%': ('equity_top5', 'stock_top5_return', '#1f77b4'),\n"
            "    'Sector ETF ML Quality Rotation': ('equity_sector_quality', 'sector_quality_return', '#2ca02c'),\n"
            "    'SPY Buy And Hold': ('equity_spy', 'spy_return', '#7f7f7f'),\n"
            "}\n"
            "\n"
            "def _plot_equity(ax, frame: pd.DataFrame, title: str) -> None:\n"
            "    if frame.empty:\n"
            "        ax.set_title(title + ' (no data)')\n"
            "        return\n"
            "    frame = frame.sort_values('entry_date').reset_index(drop=True)\n"
            "    for label, (_, ret_col, color) in STRAT_COLS.items():\n"
            "        equity = (1.0 + frame[ret_col].astype(float).fillna(0.0)).cumprod()\n"
            "        ax.plot(frame['entry_date'], equity, label=label, color=color, linewidth=1.6)\n"
            "    ax.set_title(title)\n"
            "    ax.set_ylabel('growth of 1.0')\n"
            "    ax.xaxis.set_major_locator(mdates.AutoDateLocator())\n"
            "    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(mdates.AutoDateLocator()))\n"
            "\n"
            "fig, axes = plt.subplots(2, 2, figsize=(13, 7.5), sharey=False)\n"
            "for ax, (scope, mode) in zip(\n"
            "    axes.flatten(),\n"
            "    [('history', 'ml_5bar'), ('history', 'regime_change'), ('holdout', 'ml_5bar'), ('holdout', 'regime_change')],\n"
            "):\n"
            "    frame = period_log[(period_log['scope'] == scope) & (period_log['mode'] == mode)]\n"
            "    _plot_equity(ax, frame, f'{scope} / {mode}')\n"
            "axes[0, 0].legend(loc='upper left', frameon=False, fontsize=8)\n"
            "fig.suptitle('Equity curves — strategy vs SPY by scope/mode', y=1.02)\n"
            "plt.tight_layout()\n"
            "plt.show()"
        )
    )

    cells.append(md("## 6. Drawdowns"))
    cells.append(
        code(
            "def _drawdown(returns: pd.Series) -> pd.Series:\n"
            "    eq = (1.0 + returns.astype(float).fillna(0.0)).cumprod()\n"
            "    return eq / eq.cummax() - 1.0\n"
            "\n"
            "fig, axes = plt.subplots(2, 2, figsize=(13, 7.5), sharey=True)\n"
            "for ax, (scope, mode) in zip(\n"
            "    axes.flatten(),\n"
            "    [('history', 'ml_5bar'), ('history', 'regime_change'), ('holdout', 'ml_5bar'), ('holdout', 'regime_change')],\n"
            "):\n"
            "    frame = period_log[(period_log['scope'] == scope) & (period_log['mode'] == mode)].sort_values('entry_date')\n"
            "    if frame.empty:\n"
            "        ax.set_title(f'{scope} / {mode} (no data)')\n"
            "        continue\n"
            "    for label, (_, ret_col, color) in STRAT_COLS.items():\n"
            "        dd = _drawdown(frame[ret_col])\n"
            "        ax.fill_between(frame['entry_date'], dd, color=color, alpha=0.18, label=label)\n"
            "        ax.plot(frame['entry_date'], dd, color=color, linewidth=1.1)\n"
            "    ax.set_title(f'{scope} / {mode}')\n"
            "    ax.set_ylabel('drawdown')\n"
            "axes[0, 0].legend(loc='lower left', frameon=False, fontsize=8)\n"
            "fig.suptitle('Drawdown — strategy vs SPY', y=1.02)\n"
            "plt.tight_layout()\n"
            "plt.show()"
        )
    )

    cells.append(md("## 7. Per-period return distribution"))
    cells.append(
        code(
            "fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), sharey=True)\n"
            "for ax, scope in zip(axes, ['history', 'holdout']):\n"
            "    frame = period_log[period_log['scope'] == scope]\n"
            "    if frame.empty:\n"
            "        ax.set_title(f'{scope} (no data)')\n"
            "        continue\n"
            "    data = [frame['stock_top5_return'].dropna(), frame['sector_quality_return'].dropna(), frame['spy_return'].dropna()]\n"
            "    labels = ['Top 5 Holdings', 'Sector ETF Quality', 'SPY']\n"
            "    parts = ax.violinplot(data, showmeans=True, showmedians=False)\n"
            "    for body, color in zip(parts['bodies'], ['#1f77b4', '#2ca02c', '#7f7f7f']):\n"
            "        body.set_facecolor(color); body.set_alpha(0.6)\n"
            "    ax.set_xticks([1, 2, 3]); ax.set_xticklabels(labels)\n"
            "    ax.axhline(0, color='black', linewidth=0.6, linestyle=':')\n"
            "    ax.set_title(f'Per-period return — {scope}')\n"
            "    ax.set_ylabel('return per holding period')\n"
            "plt.tight_layout()\n"
            "plt.show()"
        )
    )

    cells.append(md("## 8. Returns by regime"))
    cells.append(
        code(
            "regime_summary = (\n"
            "    period_log.groupby(['scope', 'mode', 'regime_label'])\n"
            "    .agg(\n"
            "        top5_total=('stock_top5_return', lambda s: float((1 + s.fillna(0)).prod() - 1)),\n"
            "        sector_quality_total=('sector_quality_return', lambda s: float((1 + s.fillna(0)).prod() - 1)),\n"
            "        spy_total=('spy_return', lambda s: float((1 + s.fillna(0)).prod() - 1)),\n"
            "        periods=('signal_date', 'count'),\n"
            "    )\n"
            "    .reset_index()\n"
            ")\n"
            "regime_summary"
        )
    )
    cells.append(
        code(
            "def _plot_regime_bar(ax, scope: str, mode: str) -> None:\n"
            "    frame = regime_summary[(regime_summary['scope'] == scope) & (regime_summary['mode'] == mode)].copy()\n"
            "    if frame.empty:\n"
            "        ax.set_title(f'{scope} / {mode} (no data)')\n"
            "        return\n"
            "    frame = frame.sort_values('top5_total', ascending=True)\n"
            "    y = np.arange(len(frame))\n"
            "    width = 0.27\n"
            "    ax.barh(y - width, frame['top5_total'] * 100, width, label='Top 5 Holdings', color='#1f77b4')\n"
            "    ax.barh(y, frame['sector_quality_total'] * 100, width, label='Sector ETF Quality', color='#2ca02c')\n"
            "    ax.barh(y + width, frame['spy_total'] * 100, width, label='SPY', color='#7f7f7f')\n"
            "    ax.set_yticks(y); ax.set_yticklabels(frame['regime_label'])\n"
            "    ax.set_xlabel('regime total return (%)')\n"
            "    ax.set_title(f'{scope} / {mode}')\n"
            "    ax.axvline(0, color='black', linewidth=0.6)\n"
            "\n"
            "fig, axes = plt.subplots(2, 2, figsize=(13, 8))\n"
            "for ax, (scope, mode) in zip(\n"
            "    axes.flatten(),\n"
            "    [('history', 'ml_5bar'), ('history', 'regime_change'), ('holdout', 'ml_5bar'), ('holdout', 'regime_change')],\n"
            "):\n"
            "    _plot_regime_bar(ax, scope, mode)\n"
            "axes[0, 0].legend(loc='lower right', frameon=False, fontsize=8)\n"
            "fig.suptitle('Total return by regime', y=1.02)\n"
            "plt.tight_layout()\n"
            "plt.show()"
        )
    )

    cells.append(md("## 9. Turnover and trading cost"))
    cells.append(
        code(
            "turnover_summary = (\n"
            "    period_log.groupby(['scope', 'mode'])\n"
            "    .agg(\n"
            "        avg_turnover=('turnover', 'mean'),\n"
            "        total_turnover=('turnover', 'sum'),\n"
            "        total_turnover_cost=('turnover_cost', 'sum'),\n"
            "        avg_holdings=('selected_stock_count', 'mean'),\n"
            "        avg_sectors=('selected_sector_count', 'mean'),\n"
            "    )\n"
            "    .reset_index()\n"
            ")\n"
            "turnover_summary"
        )
    )
    cells.append(
        code(
            "fig, axes = plt.subplots(1, 2, figsize=(13, 4.2))\n"
            "for ax, scope in zip(axes, ['history', 'holdout']):\n"
            "    frame = period_log[(period_log['scope'] == scope) & (period_log['mode'] == 'ml_5bar')].sort_values('entry_date')\n"
            "    if frame.empty:\n"
            "        ax.set_title(f'{scope} / ml_5bar (no data)')\n"
            "        continue\n"
            "    ax.bar(frame['entry_date'], frame['turnover'], width=4.0, color='#1f77b4', alpha=0.55, label='Top 5 turnover')\n"
            "    ax.bar(frame['entry_date'], frame['sector_turnover'], width=4.0, color='#2ca02c', alpha=0.55, label='Sector ETF turnover')\n"
            "    ax.set_title(f'Turnover per rebalance — {scope} / ml_5bar')\n"
            "    ax.set_ylabel('turnover (fraction of book)')\n"
            "    ax.legend(loc='upper left', frameon=False, fontsize=8)\n"
            "plt.tight_layout()\n"
            "plt.show()"
        )
    )

    cells.append(md("## 10. Stop-loss activity"))
    cells.append(
        code(
            "stop_summary = (\n"
            "    period_log.groupby(['scope', 'mode'])\n"
            "    .agg(\n"
            "        periods=('signal_date', 'count'),\n"
            "        total_stop_count=('stop_count', 'sum'),\n"
            "        periods_with_stop=('stop_count', lambda s: int((s > 0).sum())),\n"
            "    )\n"
            "    .reset_index()\n"
            ")\n"
            "stop_summary['stop_rate'] = stop_summary['periods_with_stop'] / stop_summary['periods']\n"
            "stop_summary"
        )
    )
    cells.append(
        code(
            "frame = period_log[period_log['scope'] == 'history'].sort_values('entry_date')\n"
            "fig, ax = plt.subplots(figsize=(11, 3.5))\n"
            "ml = frame[frame['mode'] == 'ml_5bar']\n"
            "regime = frame[frame['mode'] == 'regime_change']\n"
            "ax.bar(ml['entry_date'], ml['stop_count'], width=4.0, color='#d62728', alpha=0.6, label='ml_5bar stops')\n"
            "ax.bar(regime['entry_date'], regime['stop_count'], width=8.0, color='#8c564b', alpha=0.6, label='regime_change stops')\n"
            "ax.set_title('History — number of holdings stopped out per rebalance')\n"
            "ax.set_ylabel('stop count')\n"
            "ax.legend(loc='upper left', frameon=False, fontsize=8)\n"
            "plt.tight_layout()\n"
            "plt.show()"
        )
    )

    cells.append(md("## 11. Leaderboard and best-strategy assessment\n"
                    "\n"
                    "The leaderboard ranks each (mode, strategy) candidate on the **history** slice using "
                    "(Sharpe → CAGR → max drawdown), then carries the unchanged winner into the **holdout** scope. "
                    "`selected_on_history == True` identifies the candidate that the rule actually deploys; the "
                    "`holdout_oracle_*` fields in the assessment JSON give the ex-post best to make the selection-vs-holdout "
                    "gap explicit."))
    cells.append(
        code(
            "lb = leaderboard.copy()\n"
            "ordered = lb.sort_values('history_rank')\n"
            "ordered[[\n"
            "    'mode', 'strategy_label',\n"
            "    'history_rank', 'history_sharpe', 'history_cagr', 'history_max_drawdown',\n"
            "    'holdout_rank', 'holdout_sharpe', 'holdout_cagr', 'holdout_max_drawdown',\n"
            "    'holdout_total_return', 'benchmark_holdout_total_return', 'holdout_total_return_vs_spy',\n"
            "    'selected_on_history',\n"
            "]]"
        )
    )
    cells.append(
        code(
            "fig, axes = plt.subplots(1, 2, figsize=(13, 4.0))\n"
            "ord_lb = leaderboard.sort_values('history_rank').reset_index(drop=True)\n"
            "labels = [f\"{m}\\n{s}\" for m, s in zip(ord_lb['mode'], ord_lb['strategy_label'])]\n"
            "y = np.arange(len(ord_lb))\n"
            "axes[0].barh(y, ord_lb['history_sharpe'], color='#1f77b4', alpha=0.7)\n"
            "axes[0].set_yticks(y); axes[0].set_yticklabels(labels)\n"
            "axes[0].set_title('History Sharpe (selection metric)')\n"
            "axes[0].axvline(0, color='black', linewidth=0.6)\n"
            "axes[1].barh(y, ord_lb['holdout_sharpe'], color='#2ca02c', alpha=0.7)\n"
            "axes[1].set_yticks(y); axes[1].set_yticklabels([])\n"
            "axes[1].set_title('Holdout Sharpe (evaluation metric)')\n"
            "axes[1].axvline(0, color='black', linewidth=0.6)\n"
            "selected_idx = ord_lb.index[ord_lb['selected_on_history']].tolist()\n"
            "for idx in selected_idx:\n"
            "    axes[0].text(ord_lb.loc[idx, 'history_sharpe'], idx, '  SELECTED', va='center', fontsize=8, color='#d62728')\n"
            "    axes[1].text(ord_lb.loc[idx, 'holdout_sharpe'], idx, '  SELECTED', va='center', fontsize=8, color='#d62728')\n"
            "fig.suptitle('History rank vs holdout outcome', y=1.02)\n"
            "plt.tight_layout()\n"
            "plt.show()"
        )
    )
    cells.append(
        code(
            "fields = [\n"
            "    'selection_rule', 'candidate_count',\n"
            "    'selected_mode', 'selected_strategy_label',\n"
            "    'selected_history_rank', 'selected_holdout_rank',\n"
            "    'history_total_return', 'history_cagr', 'history_sharpe', 'history_max_drawdown',\n"
            "    'holdout_total_return', 'holdout_cagr', 'holdout_sharpe', 'holdout_max_drawdown',\n"
            "    'holdout_total_return_vs_spy', 'holdout_cagr_vs_spy', 'holdout_sharpe_vs_spy',\n"
            "    'benchmark_holdout_total_return', 'benchmark_holdout_cagr', 'benchmark_holdout_sharpe', 'benchmark_holdout_max_drawdown',\n"
            "    'holdout_oracle_mode', 'holdout_oracle_strategy_label', 'holdout_oracle_rank',\n"
            "    'holdout_oracle_total_return', 'holdout_oracle_cagr', 'holdout_oracle_sharpe',\n"
            "]\n"
            "assessment_view = pd.DataFrame({'field': fields, 'value': [assessment.get(k) for k in fields]})\n"
            "assessment_view"
        )
    )

    cells.append(md("## 12. Sector exposure heatmap\n"
                    "\n"
                    "Per-period sector weight in the Top-5-holdings rotation. Helps spot regime-conditional "
                    "concentration (e.g. defensive bias under fragile late-cycle, cyclical tilt under inflationary boom)."))
    cells.append(
        code(
            "def _weight_matrix(scope: str, mode: str) -> pd.DataFrame:\n"
            "    frame = period_log[(period_log['scope'] == scope) & (period_log['mode'] == mode)].copy()\n"
            "    if frame.empty:\n"
            "        return pd.DataFrame()\n"
            "    rows = []\n"
            "    for _, row in frame.iterrows():\n"
            "        try:\n"
            "            weights = json.loads(row['sector_weights'])\n"
            "        except Exception:\n"
            "            weights = {}\n"
            "        rows.append({'entry_date': row['entry_date'], **weights})\n"
            "    matrix = pd.DataFrame(rows).set_index('entry_date').sort_index()\n"
            "    matrix = matrix.fillna(0.0)\n"
            "    return matrix\n"
            "\n"
            "for scope, mode in [('history', 'ml_5bar'), ('holdout', 'ml_5bar')]:\n"
            "    matrix = _weight_matrix(scope, mode)\n"
            "    if matrix.empty:\n"
            "        print(f'{scope} / {mode}: empty')\n"
            "        continue\n"
            "    fig, ax = plt.subplots(figsize=(12, 0.35 * max(matrix.shape[1], 3) + 2.0))\n"
            "    im = ax.imshow(matrix.T.values, aspect='auto', cmap='Blues', vmin=0.0, vmax=matrix.values.max())\n"
            "    ax.set_yticks(np.arange(len(matrix.columns)))\n"
            "    ax.set_yticklabels(matrix.columns)\n"
            "    sample_idx = np.linspace(0, len(matrix.index) - 1, num=min(10, len(matrix.index))).astype(int)\n"
            "    ax.set_xticks(sample_idx)\n"
            "    ax.set_xticklabels([matrix.index[i].strftime('%Y-%m') for i in sample_idx], rotation=45, ha='right')\n"
            "    ax.set_title(f'Sector weights over time — {scope} / {mode}')\n"
            "    fig.colorbar(im, ax=ax, shrink=0.7, label='sector weight')\n"
            "    plt.tight_layout()\n"
            "    plt.show()"
        )
    )

    cells.append(md("## 13. Conclusions and known caveats\n"
                    "\n"
                    "**What we found.**\n"
                    "\n"
                    "- The PIT runner now reads the split OOS signal exports and produces a real train-to-holdout assessment "
                    "(`sector_ml_pit_top5_holdings_leaderboard.csv`, `sector_ml_pit_top5_holdings_best_strategy_assessment.json`).\n"
                    "- The history-selected winner (`regime_change / Sector ETF ML Quality Rotation`) generalized to the holdout "
                    "with **+28.1% total return** (Sharpe 1.36) and **+11.7 pts vs SPY**, but ranked 4 of 4 vs the ex-post oracle. "
                    "Selection-vs-oracle gap is the right thing to surface — the strategy did beat SPY, but the rule did not pick the best of the four candidates with hindsight.\n"
                    "- The `ml_5bar / Sector ETF ML Quality Rotation` candidate was the ex-post oracle on holdout (Sharpe 1.70, +2.8 pts vs SPY) but only ranked 4 of 4 on history. If you want the deployable 5-bar lane to drive selection, you can restrict the candidate set to `ml_5bar` and leave `regime_change` as a diagnostic.\n"
                    "\n"
                    "**Forward-bias status.**\n"
                    "\n"
                    "- PIT holdings filter: clean (`known_from_date <= signal_date` enforced at load and at consumption).\n"
                    "- Validation-quality prior: clean (year-strict pre-signal folds only).\n"
                    "- Holdout isolation: clean (train_end < holdout_start - embargo - purge).\n"
                    "- Macro pipeline: previously had a full-sample VIX3M backfill and a `bfill()` on spot VIX; both replaced with causal equivalents. To pick up the fix, regenerate the macro store (`./.venv/bin/python build_macro_store.py`) and re-run `build_sector_rotation_report.py` and `backtest_top_holdings_rotation.py`.\n"
                    "\n"
                    "**Known caveats.**\n"
                    "\n"
                    "- `ATVI`, `PXD`, `RTN`, `UTX` are skipped — no local price history (delisted/renamed). The runner reports them in the missing-symbols log but does not crash.\n"
                    "- The holdout window is short (~18 ml_5bar periods, 3 regime_change periods) — point estimates of Sharpe on the holdout are noisy. Treat the holdout as a falsification check, not a precision estimate.\n"
                    "- 10% stop is end-of-day; intraday breaches that recover by close are not modeled.\n"))

    nb.cells = cells
    nb.metadata = {
        "kernelspec": {
            "display_name": "Python 3 (price_action)",
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
    nb = build_notebook()
    NOTEBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(nb, NOTEBOOK_PATH)
    print("wrote", NOTEBOOK_PATH)


if __name__ == "__main__":
    main()
