from __future__ import annotations

import ast
import argparse
import html
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .data import MACRO_FEATURES_DIR, load_macro_context, resolve_project_root
from .macro_context import (
    MACRO_ARCHITECTURE_LAYERS,
    MACRO_DESIGN_PRINCIPLES,
    MACRO_INTERACTION_LIBRARY,
    MACRO_REGIME_WINDOWS,
    MACRO_REPORT_GROUPS,
    MACRO_RECOMMENDED_EXPANSIONS,
    MACRO_SCENARIO_PLAYBOOK,
    MACRO_SERIES_BRIEFS,
    MACRO_SERIES_DETAILS,
)
from .macro_features import write_macro_feature_store

PAGE_BACKGROUND = "#f7f2e8"
PANEL_BACKGROUND = "#fffdf8"
TEXT_COLOR = "#1b2430"
MUTED_TEXT_COLOR = "#5f6b76"
GRID_COLOR = "#d5cfc5"
ACCENT_COLORS = (
    "#0f4c5c",
    "#7a3e2b",
    "#4f6d3a",
    "#7f5539",
    "#4361ee",
)
REGIME_FILL = "#d8c7af"
SVG_WIDTH = 1140
SVG_PLOT_WIDTH = 980
SVG_LEFT_MARGIN = 120
SVG_RIGHT_MARGIN = 40
SVG_TOP_MARGIN = 36
SVG_BOTTOM_MARGIN = 54
SVG_ROW_HEIGHT = 180
SVG_ROW_GAP = 18


def _ensure_macro_feature_store(project_root: str | Path | None = None) -> Path:
    root = resolve_project_root(project_root)
    feature_store_dir = root / MACRO_FEATURES_DIR
    write_macro_feature_store(project_root=root)
    return feature_store_dir


def load_model_macro_inventory(project_root: str | Path | None = None) -> pd.DataFrame:
    root = resolve_project_root(project_root)
    feature_store_dir = _ensure_macro_feature_store(project_root=root)
    inventory = pd.read_csv(feature_store_dir / "feature_inventory.csv")
    inventory = inventory.loc[
        inventory["feature"].isin(
            [feature for group in MACRO_REPORT_GROUPS for feature in group["series"]]
        )
    ].copy()
    inventory = inventory.set_index("feature", drop=False)
    return inventory


def load_model_macro_frame(project_root: str | Path | None = None) -> pd.DataFrame:
    root = resolve_project_root(project_root)
    _ensure_macro_feature_store(project_root=root)
    frame = load_macro_context(project_root=root)
    selected = [feature for group in MACRO_REPORT_GROUPS for feature in group["series"] if feature in frame.columns]
    numeric = frame[selected].apply(pd.to_numeric, errors="coerce").sort_index().ffill()
    numeric.index = pd.to_datetime(numeric.index)
    return numeric


def _format_value(value: Any, units: str | None) -> str:
    if pd.isna(value):
        return "n/a"

    numeric = float(value)
    unit_text = units.lower() if isinstance(units, str) else ""
    if "usd per" in unit_text:
        return f"${numeric:,.2f}"
    if "percent" in unit_text:
        return f"{numeric:,.2f}%"
    if "ratio" in unit_text:
        return f"{numeric:,.2f}x"
    if "billions" in unit_text:
        return f"{numeric:,.0f} bn"
    if abs(numeric) >= 1000:
        return f"{numeric:,.0f}"
    if abs(numeric) >= 100:
        return f"{numeric:,.1f}"
    return f"{numeric:,.2f}"


def _render_source_link(source: str | None, source_url: str | None) -> str:
    label = "unknown" if pd.isna(source) else html.escape(str(source))
    if isinstance(source_url, str) and source_url.strip():
        return f'<a href="{html.escape(source_url)}">{label}</a>'
    return label


def _display_text(value: Any, fallback: str = "n/a") -> str:
    if value is None or pd.isna(value):
        return fallback
    return str(value)


def _coerce_text_items(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item).strip())
    if isinstance(value, str) and value.strip():
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            parsed = value
        if isinstance(parsed, (list, tuple)):
            return tuple(str(item) for item in parsed if str(item).strip())
        if str(parsed).strip() and str(parsed).strip() != "[]":
            return (str(parsed),)
    return ()


def _format_axis_label(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value) >= 100:
        return f"{value:,.1f}"
    return f"{value:,.2f}"


def _date_position(timestamp: pd.Timestamp, start: pd.Timestamp, end: pd.Timestamp) -> float:
    total_days = max((end - start).days, 1)
    offset_days = min(max((timestamp - start).days, 0), total_days)
    return SVG_LEFT_MARGIN + (offset_days / total_days) * SVG_PLOT_WIDTH


def _value_position(value: float, lower: float, upper: float, top: float, height: float) -> float:
    if upper <= lower:
        return top + height / 2.0
    ratio = (value - lower) / (upper - lower)
    return top + height - ratio * height


def _series_bounds(series: pd.Series) -> tuple[float, float]:
    minimum = float(series.min())
    maximum = float(series.max())
    if minimum == maximum:
        pad = abs(minimum) * 0.05 or 1.0
        return minimum - pad, maximum + pad
    pad = (maximum - minimum) * 0.08
    return minimum - pad, maximum + pad


def _series_path(series: pd.Series, lower: float, upper: float, top: float, height: float, start: pd.Timestamp, end: pd.Timestamp) -> str:
    commands: list[str] = []
    for index, value in series.items():
        x_pos = _date_position(pd.Timestamp(index), start, end)
        y_pos = _value_position(float(value), lower, upper, top, height)
        command = "M" if not commands else "L"
        commands.append(f"{command}{x_pos:.2f},{y_pos:.2f}")
    return " ".join(commands)


def _render_chip_list(items: tuple[str, ...] | list[str]) -> str:
    if not items:
        return ""
    return "".join(f'<li>{html.escape(item)}</li>' for item in items)


def _render_detail_block(label: str, items: tuple[str, ...] | list[str]) -> str:
    if not items:
        return ""
    return "\n".join(
        [
            '<div class="detail-block">',
            f'  <p class="detail-label">{html.escape(label)}</p>',
            f'  <ul class="chip-list">{_render_chip_list(items)}</ul>',
            '</div>',
        ]
    )


def _render_framework_grid(
    title: str,
    eyebrow: str,
    items: tuple[dict[str, str | tuple[str, ...]], ...],
    card_class: str,
) -> str:
    cards: list[str] = []
    for item in items:
        bullet_list = "".join(f'<li>{html.escape(point)}</li>' for point in item["items"])
        cards.append(
            "\n".join(
                [
                    f'<article class="{card_class}">',
                    f'  <h3>{html.escape(str(item["title"]))}</h3>',
                    f'  <p>{html.escape(str(item["summary"]))}</p>' if "summary" in item else f'  <p>{html.escape(str(item["body"]))}</p>',
                    f'  <ul class="plain-list">{bullet_list}</ul>' if "items" in item else '',
                    '</article>',
                ]
            )
        )
    return "\n".join(
        [
            '<section class="framework-section">',
            f'  <p class="eyebrow">{html.escape(eyebrow)}</p>',
            f'  <h2>{html.escape(title)}</h2>',
            f'  <div class="framework-grid {card_class}-grid">',
            "\n".join(cards),
            '  </div>',
            '</section>',
        ]
    )


def _render_principles_section() -> str:
    cards = []
    for item in MACRO_DESIGN_PRINCIPLES:
        cards.append(
            "\n".join(
                [
                    '<article class="principle-card">',
                    f'  <h3>{html.escape(item["title"])}</h3>',
                    f'  <p>{html.escape(item["body"])}</p>',
                    '</article>',
                ]
            )
        )
    return "\n".join(
        [
            '<section class="framework-section">',
            '  <p class="eyebrow">Interpretation Guardrails</p>',
            '  <h2>How These Variables Should Be Read</h2>',
            '  <div class="framework-grid principle-grid">',
            "\n".join(cards),
            '  </div>',
            '</section>',
        ]
    )


def _render_expansions_section() -> str:
    cards = []
    for item in MACRO_RECOMMENDED_EXPANSIONS:
        cards.append(
            "\n".join(
                [
                    '<article class="framework-card">',
                    f'  <h3>{html.escape(str(item["title"]))}</h3>',
                    f'  <ul class="plain-list">{"".join(f"<li>{html.escape(point)}</li>" for point in item["items"])} </ul>',
                    '</article>',
                ]
            )
        )
    return "\n".join(
        [
            '<section class="framework-section">',
            '  <p class="eyebrow">Engineering Blueprint</p>',
            '  <h2>Current Inputs Versus Recommended Extensions</h2>',
            '  <div class="formula-strip">',
            '    <pre class="formula-card">expected_daily_vol = spot_vix / 100 / sqrt(252)</pre>',
            '    <pre class="formula-card">vix_adjusted_move = return_1d / expected_daily_vol</pre>',
            '    <pre class="formula-card">crash_risk_score = valuation_fragility_score * volatility_stress_score * rate_shock_score</pre>',
            '  </div>',
            '  <div class="framework-grid framework-card-grid">',
            "\n".join(cards),
            '  </div>',
            '</section>',
        ]
    )


def _render_interactions_section() -> str:
    items = "".join(f'<li>{html.escape(item)}</li>' for item in MACRO_INTERACTION_LIBRARY)
    return "\n".join(
        [
            '<section class="framework-section compact-section">',
            '  <p class="eyebrow">Interaction Library</p>',
            '  <h2>Signals That Matter More Than Raw Levels</h2>',
            '  <ul class="plain-list two-column-list">',
            items,
            '  </ul>',
            '</section>',
        ]
    )


def _render_scenarios_section() -> str:
    cards = []
    for item in MACRO_SCENARIO_PLAYBOOK:
        cards.append(
            "\n".join(
                [
                    '<article class="scenario-card">',
                    f'  <h3>{html.escape(item["title"])}</h3>',
                    f'  <p>{html.escape(item["body"])}</p>',
                    '</article>',
                ]
            )
        )
    return "\n".join(
        [
            '<section class="framework-section">',
            '  <p class="eyebrow">Scenario Playbook</p>',
            '  <h2>How The Macro Stack Should Influence Trading Decisions</h2>',
            '  <div class="framework-grid scenario-grid">',
            "\n".join(cards),
            '  </div>',
            '</section>',
        ]
    )


def _series_card(feature: str, inventory: pd.DataFrame) -> str:
    row = inventory.loc[feature] if feature in inventory.index else pd.Series(dtype="object")
    detail = MACRO_SERIES_DETAILS.get(feature, {})
    units_value = detail.get("units_override") or row.get("units")
    name = html.escape(_display_text(detail.get("display_name") or row.get("name") or feature))
    brief = html.escape(MACRO_SERIES_BRIEFS.get(feature, "Macro context series used by the model."))
    role = html.escape(str(detail.get("role") or "Macro context input"))
    latest = _format_value(row.get("latest_value"), units_value if isinstance(units_value, str) else None)
    units = html.escape(_display_text(units_value))
    history_start = html.escape(_display_text(row.get("history_start")))
    history_end = html.escape(_display_text(row.get("history_end")))
    frequency = html.escape(_display_text(row.get("frequency")))
    source_html = _render_source_link(row.get("source"), row.get("source_url"))
    coverage_ratio = row.get("coverage_ratio")
    if pd.isna(coverage_ratio):
        coverage_text = "n/a"
    else:
        coverage_text = f"{float(coverage_ratio) * 100:.1f}%"
    engineering_items = tuple(str(item) for item in detail.get("engineering", ()))
    interaction_items = tuple(str(item) for item in detail.get("interactions", ()))
    note_items = _coerce_text_items(detail.get("data_notes") or row.get("notes"))

    return "\n".join(
        [
            '<article class="series-card">',
            f'  <p class="series-key">{html.escape(feature)}</p>',
            f"  <h3>{name}</h3>",
            f'  <p class="series-brief">{brief}</p>',
            '  <dl class="series-meta">',
            f"    <div><dt>Model role</dt><dd>{role}</dd></div>",
            f"    <div><dt>Latest</dt><dd>{html.escape(latest)}</dd></div>",
            f"    <div><dt>Units</dt><dd>{units}</dd></div>",
            f"    <div><dt>History</dt><dd>{history_start} to {history_end}</dd></div>",
            f"    <div><dt>Frequency</dt><dd>{frequency}</dd></div>",
            f"    <div><dt>Coverage</dt><dd>{coverage_text}</dd></div>",
            f"    <div><dt>Source</dt><dd>{source_html}</dd></div>",
            "  </dl>",
            _render_detail_block("Data Notes", note_items),
            _render_detail_block("Engineer Next", engineering_items),
            _render_detail_block("Watch With", interaction_items),
            "</article>",
        ]
    )


def _plot_group(
    frame: pd.DataFrame,
    inventory: pd.DataFrame,
    group: dict[str, str | tuple[str, ...]],
    output_path: Path,
) -> Path | None:
    features = [feature for feature in group["series"] if feature in frame.columns]
    if not features:
        return None

    first_date = pd.Timestamp(frame.index.min())
    last_date = pd.Timestamp(frame.index.max())
    total_height = SVG_TOP_MARGIN + len(features) * SVG_ROW_HEIGHT + (len(features) - 1) * SVG_ROW_GAP + SVG_BOTTOM_MARGIN

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{total_height}" viewBox="0 0 {SVG_WIDTH} {total_height}" role="img" aria-labelledby="title">',
        f'  <title>{html.escape(str(group["title"]))}</title>',
        f'  <rect x="0" y="0" width="{SVG_WIDTH}" height="{total_height}" fill="{PAGE_BACKGROUND}" />',
        f'  <text x="{SVG_LEFT_MARGIN}" y="24" fill="{TEXT_COLOR}" font-size="24" font-family="Georgia, serif" font-weight="700">{html.escape(str(group["title"]))}</text>',
    ]

    for index, feature in enumerate(features):
        series = frame[feature].dropna()
        if series.empty:
            continue

        top = SVG_TOP_MARGIN + index * (SVG_ROW_HEIGHT + SVG_ROW_GAP)
        inner_top = top + 24
        inner_height = SVG_ROW_HEIGHT - 40
        lower, upper = _series_bounds(series)
        row = inventory.loc[feature] if feature in inventory.index else pd.Series(dtype="object")
        detail = MACRO_SERIES_DETAILS.get(feature, {})
        units_value = detail.get("units_override") or row.get("units")
        display_name = html.escape(_display_text(detail.get("display_name") or row.get("name") or feature, fallback=feature))
        latest = html.escape(_format_value(row.get("latest_value"), units_value if isinstance(units_value, str) else None))

        parts.append(
            f'  <rect x="{SVG_LEFT_MARGIN}" y="{top}" width="{SVG_PLOT_WIDTH}" height="{SVG_ROW_HEIGHT}" rx="18" fill="{PANEL_BACKGROUND}" stroke="{GRID_COLOR}" />'
        )

        for regime in MACRO_REGIME_WINDOWS:
            regime_start = pd.Timestamp(regime["start"])
            regime_end = pd.Timestamp(regime["end"])
            x_start = _date_position(regime_start, first_date, last_date)
            x_end = _date_position(regime_end, first_date, last_date)
            width = max(x_end - x_start, 2.0)
            parts.append(
                f'  <rect x="{x_start:.2f}" y="{inner_top:.2f}" width="{width:.2f}" height="{inner_height:.2f}" fill="{REGIME_FILL}" opacity="0.28" />'
            )

        grid_values = [lower + step * (upper - lower) / 3.0 for step in range(4)]
        for grid_value in grid_values:
            y_pos = _value_position(grid_value, lower, upper, inner_top, inner_height)
            parts.append(
                f'  <line x1="{SVG_LEFT_MARGIN}" y1="{y_pos:.2f}" x2="{SVG_LEFT_MARGIN + SVG_PLOT_WIDTH}" y2="{y_pos:.2f}" stroke="{GRID_COLOR}" stroke-width="1" opacity="0.65" />'
            )

        path_data = _series_path(series, lower, upper, inner_top, inner_height, first_date, last_date)
        color = ACCENT_COLORS[index % len(ACCENT_COLORS)]
        parts.extend(
            [
                f'  <text x="{SVG_LEFT_MARGIN + 18}" y="{top + 20}" fill="{TEXT_COLOR}" font-size="16" font-family="Georgia, serif" font-weight="700">{display_name}</text>',
                f'  <text x="{SVG_LEFT_MARGIN + SVG_PLOT_WIDTH - 18}" y="{top + 20}" fill="{TEXT_COLOR}" font-size="12" font-family="Georgia, serif" text-anchor="end">Latest {latest}</text>',
                f'  <text x="{SVG_LEFT_MARGIN - 12}" y="{inner_top + 4:.2f}" fill="{MUTED_TEXT_COLOR}" font-size="11" font-family="Georgia, serif" text-anchor="end">{html.escape(_format_axis_label(upper))}</text>',
                f'  <text x="{SVG_LEFT_MARGIN - 12}" y="{inner_top + inner_height + 4:.2f}" fill="{MUTED_TEXT_COLOR}" font-size="11" font-family="Georgia, serif" text-anchor="end">{html.escape(_format_axis_label(lower))}</text>',
                f'  <path d="{path_data}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />',
            ]
        )

    start_year = first_date.year - (first_date.year % 4)
    end_year = last_date.year + (4 - last_date.year % 4)
    axis_y = total_height - 26
    parts.append(
        f'  <line x1="{SVG_LEFT_MARGIN}" y1="{axis_y}" x2="{SVG_LEFT_MARGIN + SVG_PLOT_WIDTH}" y2="{axis_y}" stroke="{GRID_COLOR}" stroke-width="1.2" />'
    )
    for year in range(start_year, end_year + 1, 4):
        tick_date = pd.Timestamp(year=year, month=1, day=1)
        if tick_date < first_date or tick_date > last_date:
            continue
        x_pos = _date_position(tick_date, first_date, last_date)
        parts.append(
            f'  <line x1="{x_pos:.2f}" y1="{axis_y}" x2="{x_pos:.2f}" y2="{axis_y + 8}" stroke="{GRID_COLOR}" stroke-width="1.2" />'
        )
        parts.append(
            f'  <text x="{x_pos:.2f}" y="{axis_y + 24}" fill="{MUTED_TEXT_COLOR}" font-size="11" font-family="Georgia, serif" text-anchor="middle">{year}</text>'
        )

    parts.append("</svg>")
    output_path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return output_path


def _render_html(
    inventory: pd.DataFrame,
    generated_at: str,
    group_plot_paths: dict[str, str],
) -> str:
    group_sections: list[str] = []
    toc_links: list[str] = []
    regime_text = " | ".join(
        f"{window['label']}: {window['start'][:4]}-{window['end'][:4]}" for window in MACRO_REGIME_WINDOWS
    )
    architecture_section = _render_framework_grid(
        title="A Better Macro Architecture",
        eyebrow="System Design",
        items=MACRO_ARCHITECTURE_LAYERS,
        card_class="framework-card",
    )
    principles_section = _render_principles_section()
    expansions_section = _render_expansions_section()
    interactions_section = _render_interactions_section()
    scenarios_section = _render_scenarios_section()

    for group in MACRO_REPORT_GROUPS:
        slug = str(group["slug"])
        title = html.escape(str(group["title"]))
        summary = html.escape(str(group["summary"]))
        plot_path = group_plot_paths.get(slug)
        features = [feature for feature in group["series"] if feature in inventory.index]
        if not features or plot_path is None:
            continue

        toc_links.append(f'<a href="#{slug}">{title}</a>')
        cards_html = "\n".join(_series_card(feature, inventory) for feature in features)
        group_sections.append(
            "\n".join(
                [
                    f'<section id="{slug}" class="group-section">',
                    '  <div class="section-copy">',
                    f'    <p class="eyebrow">Macro Channel</p>',
                    f"    <h2>{title}</h2>",
                    f"    <p>{summary}</p>",
                    "  </div>",
                    '  <figure class="plot-frame">',
                    f'    <img src="{html.escape(plot_path)}" alt="{title} timeline plots" />',
                    "  </figure>",
                    '  <div class="series-grid">',
                    cards_html,
                    "  </div>",
                    "</section>",
                ]
            )
        )

    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Macro Variables Used By The Models</title>
  <style>
    :root {{
      --bg: {PAGE_BACKGROUND};
      --panel: {PANEL_BACKGROUND};
      --ink: {TEXT_COLOR};
      --muted: {MUTED_TEXT_COLOR};
      --line: {GRID_COLOR};
      --accent: #7a3e2b;
      --accent-soft: #e9dcc8;
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
    a {{ color: #0f4c5c; }}
    .page {{ max-width: 1220px; margin: 0 auto; padding: 48px 24px 80px; }}
    .hero {{
      background: linear-gradient(135deg, rgba(255, 253, 248, 0.96), rgba(247, 242, 232, 0.96));
      border: 1px solid rgba(213, 207, 197, 0.9);
      border-radius: 28px;
      box-shadow: var(--shadow);
      padding: 40px;
      margin-bottom: 28px;
    }}
    .eyebrow {{
      margin: 0 0 10px;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      font-size: 0.78rem;
      color: var(--accent);
    }}
    h1, h2, h3 {{ line-height: 1.15; margin: 0; }}
    h1 {{ font-size: clamp(2.4rem, 4vw, 4.2rem); max-width: 12ch; }}
    h2 {{ font-size: clamp(1.5rem, 2.5vw, 2.2rem); margin-bottom: 8px; }}
    h3 {{ font-size: 1.15rem; margin-bottom: 10px; }}
    .hero p {{ max-width: 68ch; color: var(--muted); font-size: 1.02rem; }}
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
    .toc {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 12px;
      margin-bottom: 28px;
    }}
    .toc a {{
      text-decoration: none;
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid rgba(213, 207, 197, 0.9);
      background: rgba(255, 253, 248, 0.8);
      color: var(--ink);
      box-shadow: 0 10px 24px rgba(27, 36, 48, 0.04);
    }}
    .methodology {{
      background: rgba(255, 253, 248, 0.88);
      border-radius: 22px;
      border: 1px solid rgba(213, 207, 197, 0.9);
      padding: 26px 28px;
      margin-bottom: 28px;
    }}
        .framework-section {{
            background: rgba(255, 253, 248, 0.88);
            border-radius: 22px;
            border: 1px solid rgba(213, 207, 197, 0.9);
            padding: 26px 28px;
            margin-bottom: 28px;
        }}
        .compact-section {{ padding-bottom: 20px; }}
        .framework-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 16px;
            margin-top: 18px;
        }}
        .framework-card, .principle-card, .scenario-card {{
            background: var(--panel);
            border-radius: 18px;
            border: 1px solid rgba(213, 207, 197, 0.95);
            padding: 18px;
            min-height: 100%;
        }}
        .framework-card p, .principle-card p, .scenario-card p {{ margin: 10px 0 0; color: var(--muted); }}
        .plain-list {{ margin: 12px 0 0; padding-left: 18px; color: var(--muted); }}
        .plain-list li + li {{ margin-top: 8px; }}
        .two-column-list {{ columns: 2; column-gap: 28px; }}
        .formula-strip {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 12px;
            margin-top: 18px;
            margin-bottom: 18px;
        }}
        .formula-card {{
            margin: 0;
            padding: 14px 16px;
            background: #f4ede1;
            border: 1px solid rgba(122, 62, 43, 0.14);
            border-radius: 14px;
            overflow-x: auto;
            color: var(--ink);
            font-size: 0.9rem;
            font-family: "SFMono-Regular", Menlo, Consolas, monospace;
        }}
    .group-section {{
      margin-bottom: 34px;
      padding: 28px;
      border-radius: 24px;
      background: rgba(255, 253, 248, 0.9);
      border: 1px solid rgba(213, 207, 197, 0.92);
      box-shadow: var(--shadow);
    }}
    .section-copy p {{ margin-top: 0; color: var(--muted); max-width: 72ch; }}
    .plot-frame {{
      margin: 24px 0 22px;
      padding: 16px;
      background: rgba(247, 242, 232, 0.75);
      border-radius: 18px;
      border: 1px solid rgba(213, 207, 197, 0.85);
    }}
    .plot-frame img {{ display: block; width: 100%; border-radius: 10px; }}
    .series-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; }}
    .series-card {{
      background: var(--panel);
      border-radius: var(--radius);
      border: 1px solid rgba(213, 207, 197, 0.95);
      padding: 18px 18px 16px;
      min-height: 100%;
    }}
    .series-key {{
      margin: 0 0 8px;
      font-family: "SFMono-Regular", Menlo, Consolas, monospace;
      font-size: 0.75rem;
      letter-spacing: 0.04em;
      color: var(--accent);
    }}
    .series-brief {{ margin: 0 0 16px; color: var(--muted); }}
    .series-meta {{ margin: 0; display: grid; gap: 10px; }}
    .series-meta div {{
      display: grid;
      grid-template-columns: 82px 1fr;
      gap: 8px;
      align-items: start;
      padding-top: 10px;
      border-top: 1px solid rgba(213, 207, 197, 0.6);
    }}
    .series-meta dt {{ font-weight: 600; color: var(--ink); }}
    .series-meta dd {{ margin: 0; color: var(--muted); }}
        .detail-block {{ margin-top: 14px; }}
        .detail-label {{
            margin: 0 0 8px;
            font-size: 0.76rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--accent);
        }}
        .chip-list {{
            list-style: none;
            margin: 0;
            padding: 0;
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .chip-list li {{
            padding: 7px 10px;
            border-radius: 999px;
            background: rgba(233, 220, 200, 0.55);
            border: 1px solid rgba(122, 62, 43, 0.1);
            color: var(--ink);
            font-size: 0.84rem;
            line-height: 1.3;
        }}
    @media (max-width: 720px) {{
      .page {{ padding: 24px 16px 56px; }}
            .hero, .methodology, .framework-section, .group-section {{ padding: 22px; }}
      .series-meta div {{ grid-template-columns: 1fr; }}
            .two-column-list {{ columns: 1; }}
    }}
  </style>
</head>
<body>
  <main class=\"page\">
    <section class=\"hero\">
      <p class=\"eyebrow\">Model Macro Atlas</p>
      <h1>Macro Variables Used By The Models</h1>
                        <p>This document groups the macro variables currently fed into the price-action models into a cycle map: inflation breadth, real activity, policy, credit, volatility, real assets, and valuation fragility. The intent is closer to a macro playbook than a loose factor list, so each block is shown in the context where it matters rather than as an interchangeable input beside price action.</p>
      <div class=\"hero-meta\">
        <span>{generated_at}</span>
        <span>{len(inventory.index)} base macro series</span>
                <span>Current live transforms: level, 63-day z-score, 5-day delta</span>
      </div>
    </section>

    <nav class=\"toc\">
      {' '.join(toc_links)}
    </nav>

    <section class=\"methodology\">
      <p class=\"eyebrow\">Method</p>
        <p>The report rebuilds the macro feature store from raw inputs when it runs, then aligns each selected series to the daily market frame the same way the models consume it. Mixed-frequency indicators are derived before alignment, while patched VIX term-structure history and the daily market-cap-to-GDP proxy remove leading gaps from the regime-critical rows. Crisis windows are shaded to make cross-cycle comparisons easier: {html.escape(regime_text)}. The cards below add model-role guidance so the report treats inflation breadth, production, valuation, credit, and volatility as distinct macro channels rather than a flat list.</p>
    </section>

        {architecture_section}

        {principles_section}

        {expansions_section}

        {interactions_section}

        {scenarios_section}

    {' '.join(group_sections)}
  </main>
</body>
</html>
"""


def generate_macro_report(
    output_dir: str | Path,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    inventory = load_model_macro_inventory(project_root=root)
    frame = load_model_macro_frame(project_root=root)

    report_dir = Path(output_dir)
    if not report_dir.is_absolute():
        report_dir = root / report_dir
    plots_dir = report_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    filtered_inventory = inventory.loc[[column for column in frame.columns if column in inventory.index]].copy()
    filtered_inventory.to_csv(report_dir / "model_macro_inventory.csv", index=False)

    group_plot_paths: dict[str, str] = {}
    for group in MACRO_REPORT_GROUPS:
        slug = str(group["slug"])
        plot_path = plots_dir / f"{slug}.svg"
        saved_path = _plot_group(frame=frame, inventory=filtered_inventory, group=group, output_path=plot_path)
        if saved_path is not None:
            group_plot_paths[slug] = str(saved_path.relative_to(report_dir))

    generated_at = datetime.now(UTC).strftime("Generated %Y-%m-%d %H:%M UTC")
    html_text = _render_html(
        inventory=filtered_inventory,
        generated_at=generated_at,
        group_plot_paths=group_plot_paths,
    )
    report_path = report_dir / "index.html"
    report_path.write_text(html_text, encoding="utf-8")

    return {
        "report": str(report_path),
        "plots_dir": str(plots_dir),
        "inventory": str(report_dir / "model_macro_inventory.csv"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a grouped macro report for the model context variables.")
    parser.add_argument(
        "--output-dir",
        default="outputs/macro_report",
        help="Directory where the HTML document and grouped timeline plots will be written.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    generated = generate_macro_report(output_dir=args.output_dir)
    print(json.dumps(generated, indent=2))


if __name__ == "__main__":
    main()