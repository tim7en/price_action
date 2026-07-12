"""Momentum oscillator (−1 … +1) research on the Wilshire index.

The oscillator is a bounded, causal composite of medium-term momentum:

    z_h  = causal rolling z-score (120m window, min 36) of the h-month return
    osc  = tanh( mean(z_3, z_6, z_12) / 1.5 )          # smooth, saturates at ±1

Pre-registered evaluation (no tuned thresholds), on the survivorship-free
Wilshire total-market index with the leverage study's carry accounting and a
one-month signal lag:

* **Predictive**: information coefficient, forward returns by oscillator zone
  (deep oversold … deep overbought), continuation-vs-reversal at the extremes.
* **Tradable**: exposure maps that follow directly from the oscillator --
  long/short E = osc, long-only E = max(osc, 0), scaled E = (1+osc)/2, and a
  trend-gated variant (long-only oscillator, but only above the 10m MA).

Charts render in a vintage millimetre-graph-paper style (aged paper, amber
grid rules, drafting-ink line colours).

Run with::

    python build_momentum_oscillator.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .data import resolve_project_root
from .regime_analysis import _img, _REPORT_CSS, _table, load_macro_panel
from .regime_walkforward import run_book
from .sector_trend_study import _perf, _roll_z, risk_free_monthly

OUTPUT_DIR = Path("outputs") / "momentum_oscillator"

MOM_HORIZONS = (3, 6, 12)
Z_WINDOW, Z_MIN = 120, 36
TANH_SCALE = 1.5
TREND_MA = 10                     # months, the study's slow MA

ZONE_EDGES = [-1.01, -0.75, -0.25, 0.25, 0.75, 1.01]
ZONE_NAMES = ["Deep oversold (≤−0.75)", "Oversold (−0.75…−0.25)",
              "Neutral (−0.25…0.25)", "Overbought (0.25…0.75)",
              "Deep overbought (≥0.75)"]

# Vintage millimetre-paper theme.  Ink palette validated for CVD separation
# and contrast against the paper surface (amber carries a contrast WARN --
# relieved by direct labels and the metrics tables).
PAPER = "#f4ecd3"
PAGE = "#e9dcba"
GRID_MAJOR = "#c8a24b"
GRID_MINOR = "#d9bc7a"
INK = "#2e2417"
INK_MUTED = "#6b5d40"
INK_NAVY = "#2e62a8"
INK_VERMILION = "#b53517"
INK_GREEN = "#1f7a52"
INK_AMBER = "#c07f1f"

BOOK_STYLE = {
    "Wilshire 1x (buy & hold)": dict(color=INK, ls="--", lw=1.1),
    "Oscillator long/short": dict(color=INK_VERMILION, ls="-", lw=1.3),
    "Oscillator long-only": dict(color=INK_NAVY, ls="-", lw=1.6),
    "Oscillator-scaled (0…1)": dict(color=INK_AMBER, ls="-", lw=1.3),
    "Trend-gated oscillator": dict(color=INK_GREEN, ls="-", lw=1.6),
}


# --------------------------------------------------------------------------- #
# 1. The oscillator.
# --------------------------------------------------------------------------- #
def momentum_oscillator(price: pd.Series) -> pd.Series:
    zs = []
    for h in MOM_HORIZONS:
        mom = price / price.shift(h) - 1.0
        zs.append(_roll_z(mom, window=Z_WINDOW, min_p=Z_MIN))
    z = pd.concat(zs, axis=1).mean(axis=1)
    return np.tanh(z / TANH_SCALE)


def zone_of(osc: pd.Series) -> pd.Series:
    return pd.cut(osc, bins=ZONE_EDGES, labels=ZONE_NAMES)


# --------------------------------------------------------------------------- #
# 2. Diagnostics: does the level predict, do extremes continue or revert?
# --------------------------------------------------------------------------- #
def zone_table(osc: pd.Series, price: pd.Series) -> pd.DataFrame:
    r = price.pct_change(fill_method=None)
    zones = zone_of(osc)
    rows = {}
    for name in ZONE_NAMES:
        mask = zones == name
        if not mask.any():
            continue
        fwd1 = r.shift(-1)[mask]
        fwd3 = (price.shift(-3) / price - 1.0)[mask]
        fwd12 = (price.shift(-12) / price - 1.0)[mask]
        rows[name] = {
            "months": int(mask.sum()),
            "share_%": round(100 * mask.mean(), 0),
            "fwd_1m_ann_%": round(100 * fwd1.mean() * 12, 1),
            "fwd_3m_ann_%": round(100 * fwd3.mean() * 4, 1),
            "fwd_12m_%": round(100 * fwd12.mean(), 1),
            "hit_1m_%": round(100 * (fwd1 > 0).mean(), 0),
        }
    return pd.DataFrame(rows).T


def headline_stats(osc: pd.Series, price: pd.Series) -> dict:
    r = price.pct_change(fill_method=None)
    df = pd.DataFrame({"osc": osc, "fwd": r.shift(-1)}).dropna()
    ic = float(df["osc"].corr(df["fwd"]))
    ic_rank = float(df["osc"].corr(df["fwd"], method="spearman"))
    return {"ic": ic, "ic_rank": ic_rank, "n": len(df)}


# --------------------------------------------------------------------------- #
# 3. Vintage millimetre-paper chart helpers.
# --------------------------------------------------------------------------- #
def _vintage_fig(size: tuple[float, float]):
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "serif"
    fig = plt.figure(figsize=size, dpi=125)
    fig.patch.set_facecolor(PAPER)
    return fig


def _vintage_ax(ax, minor: bool = True) -> None:
    from matplotlib.ticker import AutoMinorLocator
    ax.set_facecolor(PAPER)
    ax.grid(which="major", color=GRID_MAJOR, lw=0.55, alpha=0.65)
    if minor:
        try:
            ax.xaxis.set_minor_locator(AutoMinorLocator(5))
            ax.yaxis.set_minor_locator(AutoMinorLocator(5))
        except Exception:  # noqa: BLE001  (log/date axes bring their own minors)
            pass
        ax.grid(which="minor", color=GRID_MINOR, lw=0.3, alpha=0.5)
    for spine in ax.spines.values():
        spine.set_color(INK)
        spine.set_linewidth(0.9)
    ax.tick_params(colors=INK, labelsize=7.5, which="both")
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_fontfamily("serif")


def _fig_b64(fig) -> str:
    import base64
    from io import BytesIO
    buf = BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor(),
                bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def chart_oscillator(price: pd.Series, osc: pd.Series) -> str:
    from matplotlib.gridspec import GridSpec
    fig = _vintage_fig((12, 6))
    gs = GridSpec(2, 1, height_ratios=[2.4, 1.4], hspace=0.13, figure=fig)
    ax = fig.add_subplot(gs[0]); _vintage_ax(ax, minor=False)
    px = price.dropna()
    ax.plot(px.index, px.values, color=INK, lw=1.3)
    ax.set_yscale("log")
    ax.set_ylabel("Wilshire (log)", color=INK, fontsize=9, fontfamily="serif")
    ax.set_title("Momentum oscillator against the market", loc="left",
                 fontsize=13, color=INK, fontfamily="serif")
    axo = fig.add_subplot(gs[1], sharex=ax); _vintage_ax(axo)
    o = osc.dropna()
    axo.fill_between(o.index, 0, o.values, where=(o.values >= 0),
                     color=INK_NAVY, alpha=0.45, interpolate=True)
    axo.fill_between(o.index, 0, o.values, where=(o.values < 0),
                     color=INK_VERMILION, alpha=0.45, interpolate=True)
    axo.plot(o.index, o.values, color=INK, lw=0.8)
    for level in (-0.75, 0.75):
        axo.axhline(level, color=INK_MUTED, lw=0.7, ls=":")
    axo.axhline(0, color=INK, lw=0.7)
    axo.set_ylim(-1.05, 1.05)
    axo.set_ylabel("osc (−1…+1)", color=INK, fontsize=8, fontfamily="serif")
    return _fig_b64(fig)


def chart_equity(equity: pd.DataFrame) -> str:
    from matplotlib.gridspec import GridSpec
    fig = _vintage_fig((12, 6.4))
    gs = GridSpec(2, 1, height_ratios=[3, 1.3], hspace=0.14, figure=fig)
    ax = fig.add_subplot(gs[0]); _vintage_ax(ax, minor=False)
    for col in equity.columns:
        style = BOOK_STYLE.get(col, dict(color=INK, ls="-", lw=1.0))
        ax.plot(equity.index, equity[col], label=col, **style)
    # Direct labels at the right edge, staggered when endpoints nearly coincide.
    finals = {col: float(equity[col].iloc[-1]) for col in equity.columns}
    stagger, prev = {}, None
    for col in sorted(finals, key=finals.get):
        stagger[col] = stagger[prev] + 9 if prev and finals[col] / finals[prev] < 1.25 else 0
        prev = col
    for col, off in stagger.items():
        ax.annotate(f" {col}", xy=(equity.index[-1], finals[col]),
                    xytext=(4, off), textcoords="offset points",
                    fontsize=6.5, color=BOOK_STYLE[col]["color"],
                    fontfamily="serif", va="center")
    ax.set_yscale("log")
    ax.set_ylabel("Growth of $1 (log)", color=INK, fontsize=9, fontfamily="serif")
    ax.set_title("Oscillator books vs buy & hold (carry-adjusted, 1-month lag)",
                 loc="left", fontsize=13, color=INK, fontfamily="serif")
    ax.legend(fontsize=7, loc="upper left", facecolor=PAPER, edgecolor=GRID_MAJOR,
              labelcolor=INK)
    ax.margins(x=0.14)
    axd = fig.add_subplot(gs[1], sharex=ax); _vintage_ax(axd)
    for col in equity.columns:
        style = BOOK_STYLE.get(col, dict(color=INK, ls="-", lw=1.0))
        e = equity[col]
        axd.plot(e.index, (e / e.cummax() - 1) * 100, lw=0.8,
                 color=style["color"], ls=style["ls"])
    axd.set_ylabel("Drawdown %", color=INK, fontsize=8, fontfamily="serif")
    return _fig_b64(fig)


def chart_zones(zt: pd.DataFrame) -> str:
    fig = _vintage_fig((11, 4.6)); ax = fig.add_subplot(111); _vintage_ax(ax)
    x = np.arange(len(zt))
    width = 0.38
    b1 = ax.bar(x - width / 2, zt["fwd_1m_ann_%"], width, color=INK_NAVY,
                label="Next month (annualised)")
    b2 = ax.bar(x + width / 2, zt["fwd_12m_%"], width, color=INK_AMBER,
                label="Next 12 months")
    for bars in (b1, b2):
        for rect in bars:
            v = rect.get_height()
            ax.text(rect.get_x() + rect.get_width() / 2, v + (0.6 if v >= 0 else -1.8),
                    f"{v:.0f}", ha="center", fontsize=7, color=INK, fontfamily="serif")
    ax.axhline(0, color=INK, lw=0.8)
    ax.set_xticks(x, labels=[n.split(" (")[0] for n in zt.index], fontsize=8)
    ax.set_ylabel("Avg forward return (%)", color=INK, fontsize=9, fontfamily="serif")
    ax.set_title("Forward returns by oscillator zone — continuation or reversal?",
                 loc="left", fontsize=13, color=INK, fontfamily="serif")
    ax.legend(fontsize=8, facecolor=PAPER, edgecolor=GRID_MAJOR, labelcolor=INK)
    return _fig_b64(fig)


def chart_scatter(osc: pd.Series, price: pd.Series) -> str:
    fwd3 = (price.shift(-3) / price - 1.0) * 100
    df = pd.DataFrame({"osc": osc, "fwd": fwd3}).dropna()
    fig = _vintage_fig((10, 4.8)); ax = fig.add_subplot(111); _vintage_ax(ax)
    ax.scatter(df["osc"], df["fwd"], s=14, color=INK_NAVY, alpha=0.55,
               edgecolors=PAPER, linewidths=0.4)
    coeffs = np.polyfit(df["osc"], df["fwd"], 1)
    xs = np.linspace(-1, 1, 50)
    ax.plot(xs, np.polyval(coeffs, xs), color=INK_VERMILION, lw=1.4, ls="--",
            label=f"fit: {coeffs[0]:+.1f} %·osc {coeffs[1]:+.1f}")
    ax.axhline(0, color=INK, lw=0.7); ax.axvline(0, color=INK, lw=0.7)
    ax.set_xlabel("Oscillator (month-end)", color=INK, fontsize=9, fontfamily="serif")
    ax.set_ylabel("Next 3-month return (%)", color=INK, fontsize=9, fontfamily="serif")
    ax.set_title("Each month since 2003: oscillator level vs what came next",
                 loc="left", fontsize=13, color=INK, fontfamily="serif")
    ax.legend(fontsize=8, facecolor=PAPER, edgecolor=GRID_MAJOR, labelcolor=INK)
    return _fig_b64(fig)


# --------------------------------------------------------------------------- #
# 4. Report.
# --------------------------------------------------------------------------- #
_VINTAGE_CSS = f"""
body {{ background: {PAGE}; color: {INK}; }}
main {{ background: {PAPER}; box-shadow: 0 2px 14px rgba(60,45,20,.25);
       border: 1px solid {GRID_MAJOR}; }}
h1, h2 {{ font-family: Georgia, 'Times New Roman', serif; color: {INK}; }}
p, li, td, th {{ color: {INK}; }}
table {{ border-color: {GRID_MAJOR}; }}
th {{ background: #ecdfbc; }}
.caveat, .note {{ color: {INK_MUTED}; }}
"""


def build_report(root: Path) -> Path:
    macro = load_macro_panel(root)
    price = macro["equity_index"].dropna()
    r = price.pct_change(fill_method=None)
    rf = risk_free_monthly(macro, price.index)

    osc = momentum_oscillator(price)
    start = osc.dropna().index[0]
    r_w, rf_w = r.loc[start:], rf.loc[start:]
    o = osc.loc[start:]

    ma = price.rolling(TREND_MA, min_periods=TREND_MA).mean()
    trend_up = (price > ma).astype(float).loc[start:]

    exposures = {
        "Oscillator long/short": o,
        "Oscillator long-only": o.clip(lower=0),
        "Oscillator-scaled (0…1)": (1.0 + o) / 2.0,
        "Trend-gated oscillator": o.clip(lower=0) * trend_up,
    }
    books = {"Wilshire 1x (buy & hold)": run_book(pd.Series(1.0, index=r_w.index), r_w, rf_w)}
    for name, E in exposures.items():
        books[name] = run_book(E, r_w, rf_w)
    equity = pd.DataFrame({k: (1 + v.fillna(0)).cumprod() for k, v in books.items()})
    metrics = pd.DataFrame({k: _perf(v) for k, v in books.items()}).T

    zt = zone_table(o, price.loc[start:])
    hs = headline_stats(o, price.loc[start:])

    charts = {
        "osc": chart_oscillator(price, osc),
        "equity": chart_equity(equity),
        "zones": chart_zones(zt),
        "scatter": chart_scatter(o, price.loc[start:]),
    }

    cur = float(o.dropna().iloc[-1])
    cur_zone = str(zone_of(pd.Series([cur])).iloc[0])
    best = metrics["Sharpe"].astype(float).idxmax()
    span = f"{r_w.index[0]:%Y-%m} → {r_w.index[-1]:%Y-%m}"

    deep_ob = zt.iloc[-1] if len(zt) == 5 else None
    deep_os = zt.iloc[0] if len(zt) == 5 else None
    extremes_note = ""
    if deep_ob is not None and deep_os is not None:
        extremes_note = (
            f"At the extremes the data favours <b>continuation, not reversal</b>: "
            f"deep-overbought months went on to average {deep_ob['fwd_12m_%']:.0f}% over the "
            f"next year, deep-oversold {deep_os['fwd_12m_%']:.0f}%."
            if deep_ob["fwd_12m_%"] > deep_os["fwd_12m_%"] else
            f"At the extremes the data favours <b>mean-reversion</b>: deep-oversold months "
            f"averaged {deep_os['fwd_12m_%']:.0f}% over the next year vs "
            f"{deep_ob['fwd_12m_%']:.0f}% after deep-overbought.")

    p = []
    p.append(f"""<header><h1>Momentum Oscillator Study</h1>
      <p class="subtitle">A bounded momentum oscillator — tanh of the average causal z-score of
      3/6/12-month returns, oscillating −1…+1 — evaluated on the survivorship-free Wilshire index,
      {span}. Pre-registered exposure maps, one-month lag, full carry costs. The window includes
      2008, which the walk-forward regime test's window did not.</p></header>""")

    p.append(f"""<section class="now"><h2>Snapshot</h2>
      <div class="kv-grid">
      <div class="kv"><span class="k">Oscillator today</span><span class="v">{cur:+.2f} — {cur_zone}</span></div>
      <div class="kv"><span class="k">IC (osc → next month)</span><span class="v">{hs['ic']:+.2f} (rank {hs['ic_rank']:+.2f}, n={hs['n']})</span></div>
      <div class="kv"><span class="k">Best book by Sharpe</span><span class="v">{best}</span></div>
      </div></section>""")

    p.append(f"""<section><h2>1 · The oscillator</h2>
      <p>Positive = medium-term momentum above its own history; ±0.75 marks the "deep" zones
      (dotted rules). It saturates rather than clips, so extreme readings stay comparable
      across eras.</p>
      {_img(charts['osc'], 'Momentum oscillator vs the Wilshire index')}</section>""")

    p.append(f"""<section><h2>2 · Does the level predict?</h2>
      <p>Forward returns by oscillator zone. {extremes_note}</p>
      {_img(charts['zones'], 'Forward returns by oscillator zone')}
      {_table(zt)}
      {_img(charts['scatter'], 'Oscillator level vs next-3-month return')}</section>""")

    p.append(f"""<section><h2>3 · Trading it</h2>
      <p>Four exposure maps that follow mechanically from the oscillator (no thresholds to tune),
      with the usual fair accounting — cash earns rf, borrowing pays rf+50bps, shorts pay
      100bps/yr, trades cost 10bps, one-month lag.</p>
      {_img(charts['equity'], 'Oscillator strategy equity curves')}
      {_table(metrics)}</section>""")

    p.append(f"""<section class="method"><h2>Method &amp; caveats</h2><ul>
      <li><b>Causal by construction</b>: rolling z-scores ({Z_WINDOW}m window), tanh squash, no
      fitted parameters, no thresholds chosen after seeing results.</li>
      <li><b>Monthly, one asset.</b> ~23 years ≈ 2–3 full cycles; treat zone estimates
      (especially the thin extreme zones) as noisy.</li>
      <li><b>The trend gate is redundant:</b> months with a positive oscillator sit above the
      10-month MA in all but a handful of cases, so "trend-gated" and "long-only" are nearly the
      same book — the oscillator's positive side <i>is</i> the trend filter, expressed
      continuously.</li>
      <li><b>Relation to the de-risk rule:</b> the oscillator is a <i>momentum</i> signal
      (continuation), not a stress gauge — it complements, not replaces, the health governor.
      Where it goes short (osc &lt; 0), remember the long/short book's verdict below before
      trusting shorts.</li></ul></section>""")

    doc = (f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"/>"
           f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>"
           f"<title>Momentum Oscillator Study</title>"
           f"<style>{_REPORT_CSS}{_VINTAGE_CSS}</style></head>"
           f"<body><main>{''.join(p)}</main></body></html>")

    out_dir = root / OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(doc, encoding="utf-8")
    metrics.to_csv(out_dir / "metrics.csv")
    zt.to_csv(out_dir / "zone_table.csv")
    osc.rename("oscillator").to_csv(out_dir / "oscillator_series.csv")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=None)
    args = parser.parse_args()

    root = resolve_project_root(args.project_root)
    import matplotlib
    matplotlib.use("Agg")
    out = build_report(root)
    print(f"Wrote momentum oscillator study to {out}")


if __name__ == "__main__":
    main()
