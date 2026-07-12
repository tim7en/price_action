"""Dalio-style market-conditions dashboard: macro + regimes + sectors, one page.

Combines every validated layer in this repo into a single vintage-styled
report (``outputs/market_conditions/index.html``):

1.  **Dalio quadrant** -- growth impulse x inflation impulse (6-month change in
    industrial-production YoY vs core-CPI YoY), the market's trailing path
    through the four quadrants, and historical forward equity returns per
    quadrant.
2.  **Overall verdict** -- RISK-ON / NEUTRAL / RISK-OFF from four
    pre-registered votes: market-health ladder, momentum oscillator, Dalio
    quadrant, and the GMM macro regime (fit causally for today's label).
    Valuation (CAPE, market-cap/GDP) is shown as slow-cycle context, not a vote.
3.  **The macro instrument panel** -- everything in the macro store (gold,
    DXY, VIX, HY spreads, NFCI, curve, CPI, INDPRO, sentiment, copper/gold...)
    as signed "supportive for risk assets" z-scores, plus small-multiple
    history charts.
4.  **Per-sector conditions board** -- each sector's momentum oscillator,
    trend state, earnings fundamentals (margins, ROE, growth, P/E), macro
    regime sensitivity and whipsaw rate, folded into a Favoured / Neutral /
    Avoid call.

All signals are causal (trailing windows, current-date model fits); the only
full-sample tables are explicitly-labelled historical context (quadrant
forward returns, regime sensitivity).

Run with::

    python build_market_conditions.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .data import resolve_project_root
from .momentum_oscillator import (
    _fig_b64,
    _vintage_ax,
    _vintage_fig,
    _VINTAGE_CSS,
    GRID_MAJOR,
    INK,
    INK_AMBER,
    INK_GREEN,
    INK_MUTED,
    INK_NAVY,
    INK_VERMILION,
    momentum_oscillator,
    PAPER,
)
from .regime_analysis import _img, _REPORT_CSS, _table, fit_regime_model, load_macro_panel
from .sector_trend_study import (
    _roll_z,
    build_sector_indices,
    load_sector_fundamentals,
    market_health,
)

OUTPUT_DIR = Path("outputs") / "market_conditions"
STUDY_DIR = Path("outputs") / "sector_trend_report"

QUADRANTS = {
    (1, 0): "Disinflationary boom",
    (1, 1): "Inflationary boom",
    (0, 0): "Deflationary bust",
    (0, 1): "Stagflation",
}
QUADRANT_STANCE = {
    "Disinflationary boom": "risk-on (equities)",
    "Inflationary boom": "real assets / commodities",
    "Deflationary bust": "risk-off (bonds, cash)",
    "Stagflation": "gold / cash",
}
QUADRANT_VOTE = {"Disinflationary boom": 1, "Inflationary boom": 0,
                 "Deflationary bust": -1, "Stagflation": -1}

# The macro instrument panel: column -> (label, sign for "supportive of risk").
PANEL_SPEC = {
    "nfci": ("Financial conditions (NFCI)", -1),
    "hy_spread": ("High-yield spread", -1),
    "vix": ("VIX", -1),
    "t10y3m": ("Curve 10y–3m", +1),
    "yield_curve_10y2y": ("Curve 10y–2y", +1),
    "core_cpi_yoy": ("Core CPI YoY", -1),
    "cpi_yoy": ("Headline CPI YoY", -1),
    "indpro_yoy": ("Industrial production YoY", +1),
    "unemployment": ("Unemployment", -1),
    "dxy": ("Dollar (DXY)", -1),
    "copper_gold": ("Copper/gold ratio", +1),
    "consumer_sentiment": ("Consumer sentiment", +1),
    "policy_uncertainty": ("Policy uncertainty", -1),
    "cape": ("Valuation: CAPE", -1),
    "mktcap_to_gdp": ("Valuation: mktcap/GDP", -1),
}

SPARK_COLS = ["gold", "dxy", "vix", "hy_spread", "nfci", "t10y3m",
              "core_cpi_yoy", "indpro_yoy", "cape"]
SPARK_LABELS = {"gold": "Gold ($/oz)", "dxy": "Dollar index", "vix": "VIX",
                "hy_spread": "HY spread (%)", "nfci": "NFCI",
                "t10y3m": "10y–3m curve", "core_cpi_yoy": "Core CPI YoY (%)",
                "indpro_yoy": "INDPRO YoY (%)", "cape": "Shiller CAPE"}


# --------------------------------------------------------------------------- #
# 1. Dalio quadrant.
# --------------------------------------------------------------------------- #
def quadrant_series(macro: pd.DataFrame) -> pd.DataFrame:
    infl = macro["core_cpi_yoy"].fillna(macro["cpi_yoy"])
    g = macro["indpro_yoy"] - macro["indpro_yoy"].shift(6)
    i = infl - infl.shift(6)
    df = pd.DataFrame({"growth_impulse": g, "inflation_impulse": i}).dropna()
    df["quadrant"] = [QUADRANTS[(int(gv > 0), int(iv > 0))]
                      for gv, iv in zip(df["growth_impulse"], df["inflation_impulse"])]
    return df


def quadrant_history(quads: pd.DataFrame, price: pd.Series) -> pd.DataFrame:
    fwd12 = (price.shift(-12) / price - 1.0) * 100
    rows = {}
    for name in QUADRANTS.values():
        mask = quads["quadrant"] == name
        if not mask.any():
            continue
        rows[name] = {
            "months": int(mask.sum()),
            "share_%": round(100 * mask.mean(), 0),
            "fwd_12m_equity_%": round(float(fwd12.reindex(quads.index)[mask].mean()), 1),
            "playbook stance": QUADRANT_STANCE[name],
        }
    return pd.DataFrame(rows).T


def chart_quadrant(quads: pd.DataFrame, months: int = 36) -> str:
    recent = quads.tail(months)
    fig = _vintage_fig((9.5, 7.6)); ax = fig.add_subplot(111); _vintage_ax(ax)
    lim_x = max(4.0, recent["growth_impulse"].abs().max() * 1.25)
    lim_y = max(2.0, recent["inflation_impulse"].abs().max() * 1.25)
    ax.set_xlim(-lim_x, lim_x); ax.set_ylim(-lim_y, lim_y)
    # Pale quadrant tints + labels.
    tints = {(1, 0): INK_GREEN, (1, 1): INK_AMBER, (0, 0): INK_NAVY, (0, 1): INK_VERMILION}
    for (gq, iq), name in QUADRANTS.items():
        x0, x1 = (0, lim_x) if gq else (-lim_x, 0)
        y0, y1 = (0, lim_y) if iq else (-lim_y, 0)
        ax.fill_between([x0, x1], y0, y1, color=tints[(gq, iq)], alpha=0.07)
        ax.text(x0 + (x1 - x0) * 0.5, y0 + (y1 - y0) * 0.9,
                f"{name}\n({QUADRANT_STANCE[name]})", ha="center", va="top",
                fontsize=8.5, color=INK_MUTED, fontfamily="serif", style="italic")
    ax.axhline(0, color=INK, lw=1.0); ax.axvline(0, color=INK, lw=1.0)
    xs, ys = recent["growth_impulse"].to_numpy(), recent["inflation_impulse"].to_numpy()
    # Unconnected dots; age shown by fading alpha (older = fainter).
    ages = np.linspace(0.25, 0.8, len(xs) - 1)
    ax.scatter(xs[:-1], ys[:-1], s=20, color=INK_NAVY, alpha=ages, zorder=4,
               edgecolors=PAPER, linewidths=0.4)
    ax.scatter([xs[-1]], [ys[-1]], s=130, color=INK_VERMILION, zorder=5,
               edgecolors=INK, linewidths=1.0, marker="o")
    ax.annotate(f"  now ({recent.index[-1]:%Y-%m})", xy=(xs[-1], ys[-1]),
                fontsize=9, color=INK_VERMILION, fontfamily="serif", fontweight="bold")
    for k in (11, 23):
        if len(xs) > k:
            ax.annotate(f"{recent.index[-1 - k]:%Y-%m}", xy=(xs[-1 - k], ys[-1 - k]),
                        fontsize=6.5, color=INK_MUTED, fontfamily="serif")
    ax.set_xlabel("Growth impulse — 6m change in INDPRO YoY (pp)",
                  color=INK, fontsize=9.5, fontfamily="serif")
    ax.set_ylabel("Inflation impulse — 6m change in core CPI YoY (pp)",
                  color=INK, fontsize=9.5, fontfamily="serif")
    ax.set_title(f"Dalio quadrant — the market's path, last {months} months",
                 loc="left", fontsize=13, color=INK, fontfamily="serif")
    return _fig_b64(fig)


# --------------------------------------------------------------------------- #
# 2. Macro instrument panel.
# --------------------------------------------------------------------------- #
def instrument_panel(macro: pd.DataFrame) -> pd.DataFrame:
    m = macro.copy()
    m["copper_gold"] = m["copper"] / m["gold"]
    rows = {}
    for col, (label, sign) in PANEL_SPEC.items():
        if col not in m.columns or m[col].dropna().empty:
            continue
        s = m[col].dropna()
        z = _roll_z(s)
        cur_z = float(z.dropna().iloc[-1]) if not z.dropna().empty else np.nan
        rows[label] = {
            "latest": round(float(s.iloc[-1]), 2),
            "asof": f"{s.index[-1]:%Y-%m}",
            "z_120m": round(cur_z, 2),
            "supportive_z": round(sign * cur_z, 2),
            "chg_12m": round(float(s.iloc[-1] - s.reindex([s.index[-1] - pd.offsets.MonthEnd(12)]).iloc[0]), 2)
            if (s.index[-1] - pd.offsets.MonthEnd(12)) in s.index else np.nan,
        }
    df = pd.DataFrame(rows).T
    return df.sort_values("supportive_z", ascending=False)


def chart_panel(panel: pd.DataFrame) -> str:
    s = panel["supportive_z"].dropna().astype(float).sort_values()
    fig = _vintage_fig((10.5, 6)); ax = fig.add_subplot(111); _vintage_ax(ax)
    colors = [INK_NAVY if v >= 0 else INK_VERMILION for v in s]
    ax.barh(range(len(s)), s.values, color=colors, alpha=0.85, height=0.62)
    for i, v in enumerate(s.values):
        ax.text(v + (0.06 if v >= 0 else -0.06), i, f"{v:+.1f}",
                va="center", ha="left" if v >= 0 else "right",
                fontsize=7, color=INK, fontfamily="serif")
    ax.set_yticks(range(len(s)), labels=s.index, fontsize=8)
    ax.axvline(0, color=INK, lw=1.0)
    ax.set_xlabel("Supportive of risk assets ←→ hostile   (causal 120m z-score, signed)",
                  color=INK, fontsize=9, fontfamily="serif")
    ax.set_title("The macro instrument panel — every gauge, one direction convention",
                 loc="left", fontsize=13, color=INK, fontfamily="serif")
    ax.margins(x=0.14)
    return _fig_b64(fig)


def chart_sparks(macro: pd.DataFrame, years: int = 15) -> str:
    import matplotlib.pyplot as plt
    cols = [c for c in SPARK_COLS if c in macro.columns and not macro[c].dropna().empty]
    nrow = int(np.ceil(len(cols) / 3))
    fig = _vintage_fig((12, 2.3 * nrow))
    cutoff = macro.index[-1] - pd.offsets.MonthEnd(12 * years)
    for j, col in enumerate(cols):
        ax = fig.add_subplot(nrow, 3, j + 1); _vintage_ax(ax, minor=False)
        s = macro[col].dropna()
        s = s[s.index >= cutoff]
        ax.plot(s.index, s.values, color=INK, lw=1.0)
        ax.scatter([s.index[-1]], [s.iloc[-1]], s=26, color=INK_VERMILION, zorder=5)
        ax.set_title(f"{SPARK_LABELS.get(col, col)}   ({s.iloc[-1]:,.1f})",
                     loc="left", fontsize=8.5, color=INK, fontfamily="serif")
        ax.tick_params(labelsize=6)
    fig.suptitle(f"Macro history, last {years} years (red dot = latest)",
                 x=0.02, ha="left", fontsize=12, color=INK, fontfamily="serif")
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    return _fig_b64(fig)


# --------------------------------------------------------------------------- #
# 3. Per-sector conditions board.
# --------------------------------------------------------------------------- #
def sector_board(root: Path, indices: pd.DataFrame,
                 fundamentals_dir: str | Path | None) -> pd.DataFrame:
    fund = load_sector_fundamentals(root, fundamentals_dir)
    whip_path = root / STUDY_DIR / "cross_stats_by_sector.csv"
    whip = (pd.read_csv(whip_path, index_col=0)["whipsaw_rate_%"]
            if whip_path.exists() else pd.Series(dtype="float64"))
    sens_path = root / STUDY_DIR / "sector_regime_sensitivity.csv"
    sens = (pd.read_csv(sens_path, index_col=0)["swing_%"]
            if sens_path.exists() else pd.Series(dtype="float64"))

    sectors = [c for c in indices.columns if c != "Broad market"]
    rows = {}
    for sec in sectors:
        px = indices[sec].dropna()
        osc = momentum_oscillator(px).dropna()
        ma_f = px.rolling(3, min_periods=3).mean()
        ma_s = px.rolling(10, min_periods=10).mean()
        trend = 1.0 if ma_f.iloc[-1] > ma_s.iloc[-1] else -1.0
        rows[sec] = {
            "oscillator": round(float(osc.iloc[-1]), 2) if len(osc) else np.nan,
            "trend": "UP" if trend > 0 else "DOWN",
            "_trend_num": trend,
            "margin_%": fund["profit_margin"].get(sec, np.nan),
            "roe_%": fund["roe"].get(sec, np.nan),
            "eps_growth_%": fund["eps_growth_yoy"].get(sec, np.nan),
            "pe": fund["pe"].get(sec, np.nan),
            "regime_swing_pp": sens.get(sec, np.nan),
            "whipsaw_%": whip.get(sec, np.nan),
        }
    board = pd.DataFrame(rows).T

    # Composite: momentum + trend + fundamentals (cross-sectional ranks -1..1).
    def rank_pm1(s: pd.Series, invert: bool = False) -> pd.Series:
        r = s.rank(pct=True) * 2 - 1
        return -r if invert else r

    score = pd.concat([
        board["oscillator"].astype(float),
        board["_trend_num"].astype(float),
        rank_pm1(board["margin_%"].astype(float)),
        rank_pm1(board["roe_%"].astype(float)),
        rank_pm1(board["eps_growth_%"].astype(float)),
        rank_pm1(board["pe"].astype(float), invert=True),
    ], axis=1).mean(axis=1)
    board["score"] = score.round(2)
    board["verdict"] = np.select(
        [score >= 0.33, score <= -0.33], ["Favoured", "Avoid"], default="Neutral")
    board = board.sort_values("score", ascending=False).drop(columns="_trend_num")
    return board


def chart_board(board: pd.DataFrame) -> str:
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list(
        "vintage_div", [INK_VERMILION, PAPER, INK_GREEN])
    cols = ["oscillator", "margin_%", "roe_%", "eps_growth_%", "pe", "score"]
    labels = ["Oscillator", "Margin %", "ROE %", "EPS gr %", "P/E", "Score"]
    data = board[cols].astype(float)
    norm = data.copy()
    for c in cols:
        v = norm[c]
        rng = v.max() - v.min()
        norm[c] = (v - v.min()) / rng if rng else 0.5
    norm["pe"] = 1 - norm["pe"]
    fig = _vintage_fig((10.5, 5.6)); ax = fig.add_subplot(111)
    ax.set_facecolor(PAPER); ax.grid(False)
    ax.imshow(norm.to_numpy(), aspect="auto", cmap=cmap, vmin=0, vmax=1)
    ax.set_xticks(range(len(labels)), labels=labels, fontsize=9, color=INK)
    verdicts = [f"{s}   [{v}]" for s, v in zip(board.index, board["verdict"])]
    ax.set_yticks(range(len(board)), labels=verdicts, fontsize=8.5, color=INK)
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_fontfamily("serif")
    for i in range(len(board)):
        for j, c in enumerate(cols):
            v = data.iloc[i][c]
            if pd.notna(v):
                ax.text(j, i, f"{v:.1f}", ha="center", va="center",
                        fontsize=7.5, color=INK, fontfamily="serif")
    for spine in ax.spines.values():
        spine.set_color(INK)
    ax.set_title("Sector conditions board (green = favourable; P/E inverted)",
                 loc="left", fontsize=13, color=INK, fontfamily="serif")
    return _fig_b64(fig)


# --------------------------------------------------------------------------- #
# 4. The verdict.
# --------------------------------------------------------------------------- #
def overall_verdict(health: float, osc_now: float, quadrant: str,
                    regime_name: str) -> tuple[str, pd.DataFrame]:
    votes = {}
    votes["Market health"] = (1 if health >= 55 else (0 if health >= 45 else -1),
                              f"{health:.0f}/100")
    votes["Momentum oscillator"] = (1 if osc_now > 0.25 else (-1 if osc_now < -0.25 else 0),
                                    f"{osc_now:+.2f}")
    votes["Dalio quadrant"] = (QUADRANT_VOTE[quadrant], quadrant)
    low = regime_name.lower()
    r_vote = -1 if ("stress" in low or "contraction" in low) else (
        1 if ("expansion" in low or "easy" in low) else 0)
    votes["GMM macro regime"] = (r_vote, regime_name)
    total = sum(v for v, _ in votes.values())
    call = "RISK-ON" if total >= 2 else ("RISK-OFF" if total <= -2 else "NEUTRAL")
    table = pd.DataFrame(
        {k: {"vote": f"{v:+d}", "reading": r} for k, (v, r) in votes.items()}).T
    table.loc["TOTAL"] = [f"{total:+d}", call]
    return call, table


# --------------------------------------------------------------------------- #
# 5. Report.
# --------------------------------------------------------------------------- #
def build_report(root: Path,
                 fundamentals_dir: str | Path | None = "investme_sp500_data") -> Path:
    macro = load_macro_panel(root)
    macro_asof = macro.dropna(how="all").index[-1]
    price = macro["equity_index"].dropna()
    indices, _ = build_sector_indices(root, fundamentals_dir)

    quads = quadrant_series(macro)
    q_now = str(quads["quadrant"].iloc[-1])
    q_hist = quadrant_history(quads, price)

    panel = instrument_panel(macro)
    health = float(market_health(macro, indices, slow=10)["health"].dropna().iloc[-1])
    osc_broad = momentum_oscillator(price).dropna()
    osc_now = float(osc_broad.iloc[-1])

    fwd12 = price.shift(-12) / price - 1.0
    model = fit_regime_model(macro, fwd12)
    regime_probs = (model.forecast["3m"].sort_values(ascending=False) * 100).head(3)

    board = sector_board(root, indices, fundamentals_dir)
    call, votes = overall_verdict(health, osc_now, q_now, str(model.current))

    cape_now = float(macro["cape"].dropna().iloc[-1])
    cape_pct = float((macro["cape"].dropna() <= cape_now).mean() * 100)
    mc_gdp = float(macro["mktcap_to_gdp"].dropna().iloc[-1])

    charts = {
        "quadrant": chart_quadrant(quads),
        "panel": chart_panel(panel),
        "sparks": chart_sparks(macro),
        "board": chart_board(board),
    }

    stale_days = (pd.Timestamp.now() - macro_asof).days
    stale_note = (f'<p class="caveat">⚠ Macro store is {stale_days} days old '
                  f'(through {macro_asof:%Y-%m-%d}); run <code>refresh_data.py</code> '
                  f'before acting on this page.</p>' if stale_days > 45 else "")

    fav = board[board["verdict"] == "Favoured"].index.tolist()
    avoid = board[board["verdict"] == "Avoid"].index.tolist()

    call_color = {"RISK-ON": INK_GREEN, "NEUTRAL": INK_AMBER, "RISK-OFF": INK_VERMILION}[call]
    p = []
    p.append(f"""<header><h1>Market Conditions — Dalio-Style Review</h1>
      <p class="subtitle">Macro instruments, the growth×inflation quadrant, latent regimes,
      momentum, and sector earnings — every layer of this repo folded into one reading.
      All signals causal; historical tables labelled as context.</p>{stale_note}</header>""")

    p.append(f"""<section class="now">
      <h2>Verdict: <span style="color:{call_color}">{call}</span></h2>
      <div class="kv-grid">
      <div class="kv"><span class="k">Dalio quadrant</span><span class="v">{q_now} — {QUADRANT_STANCE[q_now]}</span></div>
      <div class="kv"><span class="k">GMM macro regime</span><span class="v">{model.current}</span></div>
      <div class="kv"><span class="k">Market health</span><span class="v">{health:.0f} / 100</span></div>
      <div class="kv"><span class="k">Momentum oscillator</span><span class="v">{osc_now:+.2f}</span></div>
      <div class="kv"><span class="k">Valuation context</span><span class="v">CAPE {cape_now:.0f} ({cape_pct:.0f}th pct since '99) · mktcap/GDP {mc_gdp:.0f}%</span></div>
      <div class="kv"><span class="k">Sectors favoured / avoid</span><span class="v">{", ".join(fav) or "—"} / {", ".join(avoid) or "—"}</span></div>
      </div>
      {_table(votes)}
      <p class="note">Votes are pre-registered: health ≥55/&lt;45, oscillator ±0.25, quadrant
      stance, regime keywords. Total ≥+2 → risk-on, ≤−2 → risk-off. Valuation is slow-cycle
      context, not a vote. Per the walk-forward test, a risk-on call means <b>full normal
      exposure — never leverage</b>; risk-off means de-risk per the ladder.</p></section>""")

    p.append(f"""<section><h2>1 · The Dalio quadrant</h2>
      <p>Growth impulse vs inflation impulse (6-month changes). Each dot is a month; the red dot
      is now. Quadrant forward returns below are full-history context (1999→).</p>
      {_img(charts['quadrant'], 'Dalio growth-inflation quadrant')}
      {_table(q_hist)}</section>""")

    p.append(f"""<section><h2>2 · The macro instrument panel</h2>
      <p>Every gauge in the store, expressed as a causal 120-month z-score and signed so that
      <b>right = supportive of risk assets, left = hostile</b>. Valuation gauges are structurally
      stretched and read as long-cycle headwinds, not timing signals.</p>
      {_img(charts['panel'], 'Signed macro z-scores')}
      {_img(charts['sparks'], 'Macro history small multiples')}
      {_table(panel)}</section>""")

    p.append(f"""<section><h2>3 · Latent regime (GMM)</h2>
      <p>Current regime: <b>{model.current}</b>. Three-month odds from the Markov transition
      matrix: {"; ".join(f"{n} {v:.0f}%" for n, v in regime_probs.items())}. Fit on all history
      up to today (causal for the current label); per the walk-forward test this layer informs
      the narrative and the de-risk vote — it is never a lever-up signal.</p></section>""")

    p.append(f"""<section><h2>4 · Sector conditions board</h2>
      <p>Per sector: momentum oscillator (−1…+1 on the sector index), 3m/10m trend state,
      earnings fundamentals (medians of &gt;$2B companies), macro-regime sensitivity and
      historical whipsaw rate. The composite score averages momentum, trend and fundamental
      ranks; verdicts at ±0.33.</p>
      {_img(charts['board'], 'Sector conditions heatmap')}
      {_table(board)}</section>""")

    p.append(f"""<section class="method"><h2>Method &amp; caveats</h2><ul>
      <li><b>Causal:</b> z-scores are trailing 120m; the oscillator and trend use trailing
      windows; the GMM is fit through today only for today's label.</li>
      <li><b>Context tables are in-sample:</b> quadrant forward returns and regime sensitivity
      describe history, they are not validated timing rules.</li>
      <li><b>Sector indices</b> are point-in-time cap-weighted but survivorship-biased;
      fundamentals are a current snapshot (no history).</li>
      <li><b>The verdict maps to the de-risk ladder only</b> — risk-on ⇒ 1× at most.</li>
      </ul></section>""")

    doc = (f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"/>"
           f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>"
           f"<title>Market Conditions — Dalio-Style Review</title>"
           f"<style>{_REPORT_CSS}{_VINTAGE_CSS}"
           f" code{{background:#ecdfbc;padding:1px 5px;border-radius:4px;font-size:12px;}}"
           f"</style></head><body><main>{''.join(p)}</main></body></html>")

    out_dir = root / OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(doc, encoding="utf-8")
    panel.to_csv(out_dir / "instrument_panel.csv")
    board.to_csv(out_dir / "sector_board.csv")
    q_hist.to_csv(out_dir / "quadrant_history.csv")
    votes.to_csv(out_dir / "verdict_votes.csv")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fundamentals-dir", default="investme_sp500_data")
    parser.add_argument("--project-root", default=None)
    args = parser.parse_args()

    root = resolve_project_root(args.project_root)
    import matplotlib
    matplotlib.use("Agg")
    out = build_report(root, fundamentals_dir=args.fundamentals_dir)
    print(f"Wrote market conditions review to {out}")


if __name__ == "__main__":
    main()
