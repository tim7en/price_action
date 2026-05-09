from __future__ import annotations

import argparse
import html
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .data import resolve_project_root
from .macro_report import (
    GRID_COLOR,
    MUTED_TEXT_COLOR,
    PAGE_BACKGROUND,
    PANEL_BACKGROUND,
    REPORT_LOOKBACK_YEARS,
    TEXT_COLOR,
    _build_regime_overview,
    _build_sector_rotation_view,
    _confidence_label,
    _format_probability_pct,
    _format_return_pct,
    _format_weight_pct,
    _render_data_table,
    load_model_macro_frame,
)
from .sector_ml import build_sector_ml_view


def _format_decimal(value: float | int | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{digits}f}"


def _format_turnover(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.1f}/yr"


def _render_stat_card(title: str, body: str, tag: str) -> str:
    return "\n".join(
        [
            '<article class="stat-card">',
            f'  <p class="card-tag">{html.escape(tag)}</p>',
            f'  <h3>{html.escape(title)}</h3>',
            f'  <p>{html.escape(body)}</p>',
            '</article>',
        ]
    )


def _render_rotation_hero(
    generated_at: str,
    regime_overview: dict[str, Any],
    sector_rotation_view: dict[str, Any],
) -> str:
    current = regime_overview["current"]
    top_pick = sector_rotation_view.get("top_pick")
    top_pick_text = "n/a"
    if isinstance(top_pick, dict):
        top_pick_text = (
            f"{top_pick['sector_label']} · 1Y { _format_return_pct(float(top_pick['expected_return_12m'])) } · "
            f"confidence { _confidence_label(float(top_pick['confidence_score'])) }"
        )

    return "\n".join(
        [
            '<section class="hero">',
            '  <p class="eyebrow">Sector Rotation Report</p>',
            '  <h1>Macro-Regime Equity Rotation</h1>',
            '  <p>This report isolates the sector rotation layer from the broader macro atlas. It focuses on which equity types have historically held up best, made higher highs most often, and offered the strongest 1-year to 3-year forward return profile inside similar macro regimes.</p>',
            '  <div class="hero-meta">',
            f'    <span>{html.escape(generated_at)}</span>',
            f'    <span>Current regime: {html.escape(str(current["regime_label"]))}</span>',
            f'    <span>Quadrant: {html.escape(str(current["quadrant_label"]))}</span>',
            f'    <span>Cash rule: {html.escape(_format_weight_pct(float(sector_rotation_view["cash_weight"])))}</span>',
            f'    <span>Top entry: {html.escape(top_pick_text)}</span>',
            '  </div>',
            '</section>',
        ]
    )


def _render_overview_section(
    regime_overview: dict[str, Any],
    sector_rotation_view: dict[str, Any],
) -> str:
    current = regime_overview["current"]
    top_pick = sector_rotation_view.get("top_pick")
    defensive_pick = sector_rotation_view.get("defensive_pick")

    cards: list[str] = [
        _render_stat_card(
            title=str(current["regime_label"]),
            body=str(current["macro_narrative"]),
            tag="Current macro regime",
        ),
        _render_stat_card(
            title=str(current["quadrant_label"]),
            body=str(current["quadrant_body"]),
            tag="Growth / inflation quadrant",
        ),
        _render_stat_card(
            title=f"Cash {_format_weight_pct(float(sector_rotation_view['cash_weight']))}",
            body="The cash sleeve is fixed so the model only rotates the 60% equity bucket according to the active regime.",
            tag="Portfolio structure",
        ),
    ]

    if isinstance(top_pick, dict):
        cards.append(
            _render_stat_card(
                title=str(top_pick["sector_label"]),
                body=(
                    f"Expected 1Y {_format_return_pct(float(top_pick['expected_return_12m']))}, expected 3Y {_format_return_pct(float(top_pick['expected_return_36m']))}, "
                    f"higher-high hit rate {_format_probability_pct(float(top_pick['higher_high_rate_12m']))}, confidence {float(top_pick['confidence_score']):.0f}."
                ),
                tag="Most probable entry",
            )
        )

    if isinstance(defensive_pick, dict):
        cards.append(
            _render_stat_card(
                title=str(defensive_pick["sector_label"]),
                body=(
                    f"Defensive sleeve candidate with portfolio weight {_format_weight_pct(float(defensive_pick['portfolio_weight']))} and average future drawdown {_format_return_pct(float(defensive_pick['mean_drawdown_12m']))}."
                ),
                tag="Defensive sleeve",
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Current Outlook</p>',
            '  <h2>What The Rotation Layer Is Saying Now</h2>',
            '  <div class="card-grid">',
            "\n".join(cards),
            '  </div>',
            '</section>',
        ]
    )


def _render_sector_mapping_section(sector_rotation_view: dict[str, Any]) -> str:
    if not sector_rotation_view.get("available"):
        message = str(sector_rotation_view.get("message") or "Sector analytics unavailable.")
        return "\n".join(
            [
                '<section class="section">',
                '  <p class="eyebrow">Sector Map</p>',
                '  <h2>Equity Types</h2>',
                f'  <p>{html.escape(message)}</p>',
                '</section>',
            ]
        )

    cards = []
    for sector in sector_rotation_view["sector_cards"]:
        cards.append(
            "\n".join(
                [
                    '<article class="bucket-card">',
                    f'  <p class="card-tag">{html.escape(sector["symbol"])} · {html.escape(sector["family"])} </p>',
                    f'  <h3>{html.escape(sector["label"])}</h3>',
                    f'  <p>{html.escape(sector["earnings_proxy"])}</p>',
                    f'  <p class="subcopy">{html.escape(sector["role"])}</p>',
                    '</article>',
                ]
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Sector Map</p>',
            '  <h2>The Equity Buckets Scored In This Report</h2>',
            '  <div class="card-grid">',
            "\n".join(cards),
            '  </div>',
            '</section>',
        ]
    )


def _render_allocation_section(sector_rotation_view: dict[str, Any]) -> str:
    if not sector_rotation_view.get("available"):
        return ""

    allocation_rows: list[tuple[str, ...]] = []
    for row in sector_rotation_view["allocation_frame"].itertuples(index=False):
        allocation_rows.append(
            (
                f"{row.sector_label} ({row.symbol})",
                _format_weight_pct(row.sleeve_weight),
                _format_weight_pct(row.portfolio_weight),
                _format_return_pct(row.expected_return_12m),
                _format_return_pct(row.expected_return_36m),
                _format_probability_pct(row.higher_high_rate_12m),
                _format_return_pct(row.mean_drawdown_12m),
                f"{row.confidence_label} ({row.confidence_score:.0f})",
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Allocation</p>',
            '  <h2>Current 40 / 60 Portfolio Construction</h2>',
            '  <p>The allocation below distributes the 60% equity sleeve across the highest-scoring sector buckets under the current regime. The remaining 40% stays in cash by rule.</p>',
            _render_data_table(
                headers=(
                    'Sector',
                    'Sleeve Weight',
                    'Portfolio Weight',
                    'Expected 1Y',
                    'Expected 3Y',
                    'Higher High 12M',
                    'Avg Drawdown 12M',
                    'Confidence',
                ),
                rows=allocation_rows,
            ),
            '</section>',
        ]
    )


def _render_current_matrix_section(sector_rotation_view: dict[str, Any]) -> str:
    if not sector_rotation_view.get("available"):
        return ""

    rows: list[tuple[str, ...]] = []
    for row in sector_rotation_view["current_matrix"].itertuples(index=False):
        rows.append(
            (
                f"{row.sector_label} ({row.symbol})",
                row.family,
                _format_return_pct(row.expected_return_12m),
                _format_return_pct(row.expected_return_36m),
                _format_probability_pct(row.higher_high_rate_12m),
                _format_return_pct(row.mean_drawdown_12m),
                f"{row.confidence_label} ({row.confidence_score:.0f})",
                'Yes' if bool(row.recommended) else 'No',
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Current Regime Matrix</p>',
            '  <h2>All Sector Scores For The Active Regime</h2>',
            _render_data_table(
                headers=(
                    'Sector',
                    'Type',
                    'Expected 1Y',
                    'Expected 3Y',
                    'Higher High 12M',
                    'Avg Drawdown 12M',
                    'Confidence',
                    'Selected',
                ),
                rows=rows,
            ),
            '</section>',
        ]
    )


def _render_regime_behaviour_section(sector_rotation_view: dict[str, Any]) -> str:
    if not sector_rotation_view.get("available"):
        return ""

    cards: list[str] = []
    for item in sector_rotation_view["worst_drawdown_regimes"]:
        cards.append(
            _render_stat_card(
                title=str(item["label"]),
                body=(
                    f"Average sector drawdown {_format_return_pct(float(item['drawdown']))}. "
                    f"Higher-high rate {_format_probability_pct(float(item['higher_high']))}. "
                    f"Least-damaged sectors: {item['top_sectors']}."
                ),
                tag="Worst drawdown regime",
            )
        )

    for item in sector_rotation_view["breakout_regimes"]:
        cards.append(
            _render_stat_card(
                title=str(item["label"]),
                body=(
                    f"Higher-high hit rate {_format_probability_pct(float(item['higher_high']))}. "
                    f"Average drawdown {_format_return_pct(float(item['drawdown']))}. "
                    f"Most frequent leaders: {item['top_sectors']}."
                ),
                tag="Higher-high regime",
            )
        )

    summary_rows: list[tuple[str, ...]] = []
    for row in sector_rotation_view["regime_summary_frame"].sort_values("avg_expected_return_12m", ascending=False).itertuples(index=False):
        summary_rows.append(
            (
                str(row.regime_label),
                _format_return_pct(row.avg_expected_return_12m),
                _format_return_pct(row.avg_expected_return_36m),
                _format_probability_pct(row.avg_higher_high_rate_12m),
                _format_return_pct(row.avg_mean_drawdown_12m),
                f"{float(row.avg_confidence_score):.0f}",
                str(row.top_sectors),
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Regime Behaviour</p>',
            '  <h2>Where Drawdowns Clustered And Where Higher Highs Happened</h2>',
            '  <div class="card-grid">',
            "\n".join(cards),
            '  </div>',
            _render_data_table(
                headers=(
                    'Regime',
                    'Avg 1Y Sector Return',
                    'Avg 3Y Sector Return',
                    'Higher High 12M',
                    'Avg Drawdown 12M',
                    'Avg Confidence',
                    'Frequent Leaders',
                ),
                rows=summary_rows,
            ),
            '</section>',
        ]
    )


def _render_method_section(sector_rotation_view: dict[str, Any]) -> str:
    note = str(sector_rotation_view.get("note") or "")
    missing_symbols = sector_rotation_view.get("missing_symbols") or []
    missing_text = ""
    if missing_symbols:
        missing_text = f" Missing ETF proxies: {', '.join(str(symbol) for symbol in missing_symbols)}."
    body = (
        f"The report reuses the same monthly macro regime engine as the macro atlas, then scores sector ETF proxies by 1-year and 3-year forward returns, future drawdown, and higher-high frequency inside matching regimes. {note}{missing_text}"
    )
    return "\n".join(
        [
            '<section class="section methodology">',
            '  <p class="eyebrow">Method</p>',
            f'  <p>{html.escape(body)}</p>',
            '</section>',
        ]
    )


def _render_ml_overview_section(sector_ml_view: dict[str, Any]) -> str:
    if not sector_ml_view.get("available"):
        message = str(sector_ml_view.get("message") or "Sector ML study unavailable.")
        return "\n".join(
            [
                '<section class="section">',
                '  <p class="eyebrow">ML Overlay</p>',
                '  <h2>Machine Learning Ensemble Audit</h2>',
                f'  <p>{html.escape(message)}</p>',
                '</section>',
            ]
        )

    config = sector_ml_view["config"]
    leader = sector_ml_view["holdout_leader"]
    winner_counts = sector_ml_view["winner_counts_frame"]
    sector_count = len(sector_ml_view["sector_summary_frame"])
    top_winner = winner_counts.iloc[0].to_dict() if not winner_counts.empty else {"model_label": "n/a", "winner_count": 0}
    cards = [
        _render_stat_card(
            title="2015-2024 walk-forward, 2025+ holdout",
            body=(
                f"Five-year expanding train windows, one-year validation windows, feature lag {int(config['feature_lag'])}, purge {int(config['purge_size'])} bars, embargo {int(config['embargo_size'])} bars."
            ),
            tag="Validation design",
        ),
        _render_stat_card(
            title="Probability averaging only",
            body=(
                f"Elastic Net, ExtraTrees, and {sector_ml_view['boosting_backend']} are averaged directly. The stacked gate is disabled in this study to reduce meta-model overfit risk."
            ),
            tag="Model design",
        ),
        _render_stat_card(
            title=str(top_winner["model_label"]),
            body=f"Won {int(top_winner['winner_count'])} sectors on the stability score that penalizes validation-to-holdout degradation.",
            tag="Most stable model",
        ),
        _render_stat_card(
            title=str(leader["sector_label"]),
            body=(
                f"Best ensemble holdout by Sharpe. CAGR {_format_return_pct(leader['ensemble_holdout_cagr'])}, Sharpe {_format_decimal(leader['ensemble_holdout_sharpe'])}, max drawdown {_format_return_pct(leader['ensemble_holdout_max_drawdown'])}."
            ),
            tag="Holdout leader",
        ),
        _render_stat_card(
            title=f"{int(sector_ml_view['robust_cost_sector_count'])} / {sector_count} sectors",
            body="Still positive at the worst slippage stress scenario inside the untouched holdout.",
            tag="Cost robustness",
        ),
    ]

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">ML Overlay</p>',
            '  <h2>Machine Learning Ensemble Audit</h2>',
            f'  <p>{html.escape(str(sector_ml_view["data_note"]))}</p>',
            '  <div class="card-grid">',
            "\n".join(cards),
            '  </div>',
            '</section>',
        ]
    )


def _render_ml_sector_table_section(sector_ml_view: dict[str, Any]) -> str:
    if not sector_ml_view.get("available"):
        return ""

    rows: list[tuple[str, ...]] = []
    for row in sector_ml_view["sector_summary_frame"].sort_values("best_overfit_stability_score", ascending=False).itertuples(index=False):
        rows.append(
            (
                f"{row.sector_label} ({row.symbol})",
                str(row.best_overfit_model),
                _format_decimal(row.best_overfit_stability_score, digits=1),
                _format_return_pct(row.ensemble_holdout_cagr),
                _format_decimal(row.ensemble_holdout_sharpe),
                _format_decimal(row.ensemble_holdout_sortino),
                _format_return_pct(row.ensemble_holdout_max_drawdown),
                _format_decimal(row.ensemble_holdout_profit_factor),
                _format_probability_pct(row.ensemble_crisis_hit_rate),
                _format_turnover(row.ensemble_holdout_turnover_per_year),
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Sector ML</p>',
            '  <h2>Per-Sector Ensemble Results</h2>',
            '  <p>The table below uses the simple averaged ensemble as the live signal and separately identifies which single model preserved validation behavior into the untouched holdout best.</p>',
            _render_data_table(
                headers=(
                    'Sector',
                    'Best Anti-Overfit Model',
                    'Stability Score',
                    'Holdout CAGR',
                    'Holdout Sharpe',
                    'Holdout Sortino',
                    'Holdout Max DD',
                    'Profit Factor',
                    'Crisis Hit Rate',
                    'Turnover',
                ),
                rows=rows,
            ),
            '</section>',
        ]
    )


def _render_ml_model_comparison_section(sector_ml_view: dict[str, Any]) -> str:
    if not sector_ml_view.get("available"):
        return ""

    comparison = sector_ml_view["model_comparison_frame"].sort_values(
        ["sector_label", "stability_score", "model_label"],
        ascending=[True, False, True],
    )
    rows: list[tuple[str, ...]] = []
    for row in comparison.itertuples(index=False):
        rows.append(
            (
                f"{row.sector_label} ({row.symbol})",
                str(row.model_label),
                _format_decimal(row.stability_score, digits=1),
                _format_decimal(row.validation_roc_auc, digits=3),
                _format_decimal(row.holdout_roc_auc, digits=3),
                _format_decimal(row.validation_brier_score, digits=3),
                _format_decimal(row.holdout_brier_score, digits=3),
                _format_decimal(row.holdout_sharpe),
                _format_return_pct(row.holdout_cagr),
                str(int(row.holdout_trade_count)),
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Model Audit</p>',
            '  <h2>Validation-To-Holdout Stability By Model</h2>',
            '  <p>Higher stability scores mean the model degraded less from walk-forward validation into the untouched holdout. This is the direct overfitting check, not just a performance ranking.</p>',
            _render_data_table(
                headers=(
                    'Sector',
                    'Model',
                    'Stability',
                    'Val AUC',
                    'Holdout AUC',
                    'Val Brier',
                    'Holdout Brier',
                    'Holdout Sharpe',
                    'Holdout CAGR',
                    'Holdout Trades',
                ),
                rows=rows,
            ),
            '</section>',
        ]
    )


def _render_ml_cost_section(sector_ml_view: dict[str, Any]) -> str:
    if not sector_ml_view.get("available"):
        return ""

    cost_frame = sector_ml_view["cost_sensitivity_frame"].sort_values(
        ["sector_label", "sensitivity_type", "scenario_bps"],
        ascending=[True, True, True],
    )
    rows: list[tuple[str, ...]] = []
    for row in cost_frame.itertuples(index=False):
        rows.append(
            (
                f"{row.sector_label} ({row.symbol})",
                str(row.sensitivity_type).title(),
                f"{float(row.scenario_bps):.0f} bps",
                f"{float(row.total_cost_bps):.0f} bps",
                _format_return_pct(row.cagr),
                _format_decimal(row.sharpe),
                _format_return_pct(row.max_drawdown),
                _format_probability_pct(row.hit_rate),
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Sensitivity</p>',
            '  <h2>Fee And Slippage Sensitivity On The Holdout</h2>',
            '  <p>The model is trained on a 15 bps all-in cost assumption. The table below replays the untouched holdout under separate fee and slippage stress scenarios.</p>',
            _render_data_table(
                headers=(
                    'Sector',
                    'Stress Type',
                    'Scenario',
                    'Total Cost',
                    'Holdout CAGR',
                    'Holdout Sharpe',
                    'Holdout Max DD',
                    'Holdout Hit Rate',
                ),
                rows=rows,
            ),
            '</section>',
        ]
    )


def _render_ml_regime_year_section(sector_ml_view: dict[str, Any]) -> str:
    if not sector_ml_view.get("available"):
        return ""

    regime_rows: list[tuple[str, ...]] = []
    regime_frame = sector_ml_view["regime_performance_frame"].sort_values(
        ["sector_label", "regime_label"],
        ascending=[True, True],
    )
    for row in regime_frame.itertuples(index=False):
        regime_rows.append(
            (
                f"{row.sector_label} ({row.symbol})",
                str(row.regime_label),
                _format_return_pct(row.cagr),
                _format_decimal(row.sharpe),
                _format_return_pct(row.max_drawdown),
                _format_probability_pct(row.hit_rate),
                str(int(row.trade_count)),
            )
        )

    year_rows: list[tuple[str, ...]] = []
    yearly_frame = sector_ml_view["yearly_performance_frame"].sort_values(["year", "sector_label"], ascending=[True, True])
    for row in yearly_frame.itertuples(index=False):
        year_rows.append(
            (
                f"{row.sector_label} ({row.symbol})",
                str(int(row.year)),
                _format_return_pct(row.total_return),
                _format_return_pct(row.cagr),
                _format_decimal(row.sharpe),
                _format_return_pct(row.max_drawdown),
                str(int(row.trade_count)),
            )
        )

    return "\n".join(
        [
            '<section class="section">',
            '  <p class="eyebrow">Regime And Year</p>',
            '  <h2>Out-Of-Sample Performance By Regime And Year</h2>',
            '  <p>These tables use only the averaged ensemble and slice the full out-of-sample stream by macro regime and by calendar year.</p>',
            _render_data_table(
                headers=(
                    'Sector',
                    'Regime',
                    'CAGR',
                    'Sharpe',
                    'Max DD',
                    'Hit Rate',
                    'Trades',
                ),
                rows=regime_rows,
            ),
            _render_data_table(
                headers=(
                    'Sector',
                    'Year',
                    'Total Return',
                    'CAGR',
                    'Sharpe',
                    'Max DD',
                    'Trades',
                ),
                rows=year_rows,
            ),
            '</section>',
        ]
    )


def _render_html(
    generated_at: str,
    regime_overview: dict[str, Any],
    sector_rotation_view: dict[str, Any],
    sector_ml_view: dict[str, Any],
) -> str:
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Sector Rotation Report</title>
  <style>
    :root {{
      --bg: {PAGE_BACKGROUND};
      --panel: {PANEL_BACKGROUND};
      --ink: {TEXT_COLOR};
      --muted: {MUTED_TEXT_COLOR};
      --line: {GRID_COLOR};
      --accent: #7a3e2b;
      --shadow: 0 20px 45px rgba(27, 36, 48, 0.08);
      --radius: 18px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
      background:
        radial-gradient(circle at top left, rgba(122, 62, 43, 0.10), transparent 28%),
        radial-gradient(circle at top right, rgba(15, 76, 92, 0.08), transparent 24%),
        var(--bg);
      color: var(--ink);
      line-height: 1.6;
    }}
    .page {{ max-width: 1220px; margin: 0 auto; padding: 48px 24px 80px; }}
    .hero, .section {{
      background: rgba(255, 253, 248, 0.92);
      border: 1px solid rgba(213, 207, 197, 0.9);
      border-radius: 24px;
      box-shadow: var(--shadow);
      padding: 28px;
      margin-bottom: 28px;
    }}
    .hero {{ padding: 40px; }}
    .eyebrow {{
      margin: 0 0 10px;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      font-size: 0.78rem;
      color: var(--accent);
    }}
    h1, h2, h3 {{ line-height: 1.15; margin: 0; }}
    h1 {{ font-size: clamp(2.4rem, 4vw, 4rem); max-width: 12ch; }}
    h2 {{ font-size: clamp(1.5rem, 2.5vw, 2.2rem); margin-bottom: 8px; }}
    h3 {{ font-size: 1.15rem; margin-bottom: 10px; }}
    p {{ color: var(--muted); }}
    .hero-meta {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 24px; }}
    .hero-meta span {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 9px 14px;
      border-radius: 999px;
      background: rgba(233, 220, 200, 0.75);
      color: var(--ink);
      border: 1px solid rgba(122, 62, 43, 0.12);
      font-size: 0.92rem;
    }}
    .card-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 16px;
      margin-top: 18px;
    }}
    .stat-card, .bucket-card {{
      background: var(--panel);
      border-radius: 18px;
      border: 1px solid rgba(213, 207, 197, 0.95);
      padding: 18px;
      min-height: 100%;
    }}
    .card-tag {{
      margin: 0 0 10px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.74rem;
      color: var(--accent);
    }}
    .subcopy {{ color: var(--muted); }}
    .methodology p {{ margin: 0; }}
    .table-shell {{
      margin-top: 18px;
      overflow-x: auto;
      border-radius: 18px;
      border: 1px solid rgba(213, 207, 197, 0.9);
      background: rgba(255, 253, 248, 0.9);
    }}
    .data-table {{ width: 100%; border-collapse: collapse; min-width: 780px; }}
    .data-table th,
    .data-table td {{
      padding: 12px 14px;
      text-align: left;
      border-bottom: 1px solid rgba(213, 207, 197, 0.65);
      vertical-align: top;
    }}
    .data-table th {{
      background: rgba(244, 237, 225, 0.82);
      color: var(--ink);
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .data-table tr:last-child td {{ border-bottom: none; }}
    @media (max-width: 720px) {{
      .page {{ padding: 24px 16px 56px; }}
      .hero, .section {{ padding: 22px; }}
    }}
  </style>
</head>
<body>
  <main class=\"page\">
    {_render_rotation_hero(generated_at=generated_at, regime_overview=regime_overview, sector_rotation_view=sector_rotation_view)}
    {_render_method_section(sector_rotation_view=sector_rotation_view)}
    {_render_overview_section(regime_overview=regime_overview, sector_rotation_view=sector_rotation_view)}
    {_render_sector_mapping_section(sector_rotation_view=sector_rotation_view)}
    {_render_allocation_section(sector_rotation_view=sector_rotation_view)}
    {_render_current_matrix_section(sector_rotation_view=sector_rotation_view)}
    {_render_regime_behaviour_section(sector_rotation_view=sector_rotation_view)}
        {_render_ml_overview_section(sector_ml_view=sector_ml_view)}
        {_render_ml_sector_table_section(sector_ml_view=sector_ml_view)}
        {_render_ml_model_comparison_section(sector_ml_view=sector_ml_view)}
        {_render_ml_cost_section(sector_ml_view=sector_ml_view)}
        {_render_ml_regime_year_section(sector_ml_view=sector_ml_view)}
  </main>
</body>
</html>
"""


def generate_sector_rotation_report(
    output_dir: str | Path = "outputs/sector_rotation_report",
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    frame = load_model_macro_frame(project_root=root)
    regime_overview = _build_regime_overview(frame=frame, lookback_years=REPORT_LOOKBACK_YEARS)
    sector_rotation_view = _build_sector_rotation_view(project_root=root, regime_overview=regime_overview)
    sector_ml_view = build_sector_ml_view(project_root=root)

    report_dir = Path(output_dir)
    if not report_dir.is_absolute():
        report_dir = root / report_dir
    report_dir.mkdir(parents=True, exist_ok=True)

    matrix_path = report_dir / "sector_regime_matrix.csv"
    current_path = report_dir / "sector_current_regime.csv"
    summary_path = report_dir / "summary.json"
    ml_sector_summary_path = report_dir / "sector_ml_sector_summary.csv"
    ml_model_comparison_path = report_dir / "sector_ml_model_comparison.csv"
    ml_yearly_path = report_dir / "sector_ml_yearly_performance.csv"
    ml_regime_path = report_dir / "sector_ml_regime_performance.csv"
    ml_cost_path = report_dir / "sector_ml_cost_sensitivity.csv"

    summary_payload: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "current_regime": regime_overview["current"]["regime_label"],
        "current_quadrant": regime_overview["current"]["quadrant_label"],
        "cash_weight": float(sector_rotation_view.get("cash_weight", 0.40)),
        "note": str(sector_rotation_view.get("note") or ""),
        "missing_symbols": list(sector_rotation_view.get("missing_symbols") or []),
        "ml": {
            "available": bool(sector_ml_view.get("available")),
            "boosting_backend": sector_ml_view.get("boosting_backend"),
            "data_note": sector_ml_view.get("data_note"),
        },
    }

    if sector_rotation_view.get("available"):
        sector_rotation_view["matrix_frame"].to_csv(matrix_path, index=False)
        sector_rotation_view["current_matrix"].to_csv(current_path, index=False)
        summary_payload.update(
            {
                "top_pick": sector_rotation_view.get("top_pick"),
                "defensive_pick": sector_rotation_view.get("defensive_pick"),
                "allocation": json.loads(sector_rotation_view["allocation_frame"].to_json(orient="records")),
                "worst_drawdown_regimes": sector_rotation_view.get("worst_drawdown_regimes"),
                "breakout_regimes": sector_rotation_view.get("breakout_regimes"),
            }
        )
    else:
        summary_payload["message"] = str(sector_rotation_view.get("message") or "Sector analytics unavailable.")

    if sector_ml_view.get("available"):
        sector_ml_view["sector_summary_frame"].to_csv(ml_sector_summary_path, index=False)
        sector_ml_view["model_comparison_frame"].to_csv(ml_model_comparison_path, index=False)
        sector_ml_view["yearly_performance_frame"].to_csv(ml_yearly_path, index=False)
        sector_ml_view["regime_performance_frame"].to_csv(ml_regime_path, index=False)
        sector_ml_view["cost_sensitivity_frame"].to_csv(ml_cost_path, index=False)
        summary_payload["ml"].update(
            {
                "config": sector_ml_view.get("config"),
                "holdout_leader": json.loads(
                    pd.DataFrame([sector_ml_view.get("holdout_leader")]).to_json(orient="records")
                )[0],
                "winner_counts": json.loads(sector_ml_view["winner_counts_frame"].to_json(orient="records")),
                "robust_cost_sector_count": int(sector_ml_view.get("robust_cost_sector_count", 0)),
            }
        )
    else:
        summary_payload["ml"]["message"] = str(sector_ml_view.get("message") or "Sector ML study unavailable.")

    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    generated_at = datetime.now(UTC).strftime("Generated %Y-%m-%d %H:%M UTC")
    html_text = _render_html(
        generated_at=generated_at,
        regime_overview=regime_overview,
        sector_rotation_view=sector_rotation_view,
        sector_ml_view=sector_ml_view,
    )
    report_path = report_dir / "index.html"
    report_path.write_text(html_text, encoding="utf-8")

    return {
        "report": str(report_path),
        "summary": str(summary_path),
        "sector_matrix": str(matrix_path) if matrix_path.exists() else None,
        "sector_current": str(current_path) if current_path.exists() else None,
        "ml_sector_summary": str(ml_sector_summary_path) if ml_sector_summary_path.exists() else None,
        "ml_model_comparison": str(ml_model_comparison_path) if ml_model_comparison_path.exists() else None,
        "ml_yearly": str(ml_yearly_path) if ml_yearly_path.exists() else None,
        "ml_regime": str(ml_regime_path) if ml_regime_path.exists() else None,
        "ml_cost": str(ml_cost_path) if ml_cost_path.exists() else None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a dedicated sector rotation report.")
    parser.add_argument(
        "--output-dir",
        default="outputs/sector_rotation_report",
        help="Directory where the sector rotation HTML report and companion files will be written.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    generated = generate_sector_rotation_report(output_dir=args.output_dir)
    print(json.dumps(generated, indent=2))


if __name__ == "__main__":
    main()