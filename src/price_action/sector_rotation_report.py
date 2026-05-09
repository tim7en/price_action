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


def _render_html(
    generated_at: str,
    regime_overview: dict[str, Any],
    sector_rotation_view: dict[str, Any],
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

    report_dir = Path(output_dir)
    if not report_dir.is_absolute():
        report_dir = root / report_dir
    report_dir.mkdir(parents=True, exist_ok=True)

    matrix_path = report_dir / "sector_regime_matrix.csv"
    current_path = report_dir / "sector_current_regime.csv"
    summary_path = report_dir / "summary.json"

    summary_payload: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "current_regime": regime_overview["current"]["regime_label"],
        "current_quadrant": regime_overview["current"]["quadrant_label"],
        "cash_weight": float(sector_rotation_view.get("cash_weight", 0.40)),
        "note": str(sector_rotation_view.get("note") or ""),
        "missing_symbols": list(sector_rotation_view.get("missing_symbols") or []),
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

    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    generated_at = datetime.now(UTC).strftime("Generated %Y-%m-%d %H:%M UTC")
    html_text = _render_html(
        generated_at=generated_at,
        regime_overview=regime_overview,
        sector_rotation_view=sector_rotation_view,
    )
    report_path = report_dir / "index.html"
    report_path.write_text(html_text, encoding="utf-8")

    return {
        "report": str(report_path),
        "summary": str(summary_path),
        "sector_matrix": str(matrix_path) if matrix_path.exists() else None,
        "sector_current": str(current_path) if current_path.exists() else None,
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