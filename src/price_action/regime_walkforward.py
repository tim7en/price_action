"""Walk-forward test: do Dalio-style GMM macro regimes add *timing* accuracy?

The regime model in ``regime_analysis`` is fit on the full sample, so its
historical labels cannot be traded.  This module answers the open question
honestly: every month, refit the Gaussian-mixture regime model on macro data
up to that month only, characterise each regime cluster by the forward returns
*already known* at that date, and map the current month's cluster to a signed
exposure.  The result is a genuinely causal Dalio-regime timing signal, raced
head-to-head against the (also causal) market-health ladder from the sector
trend study on the same asset.

Asset: the Wilshire total-market index from the macro store -- the one
benchmark in this repo with no survivorship bias.

Pre-registered rules (fixed before looking at results, to avoid the in-sample
trap):

* k = 5 mixture components, seed 7, refit monthly on an expanding window
  (first fit after 120 months of history).
* Cluster -> exposure: rank clusters by their mean next-month return over the
  history known at the refit date; exposure is linear in rank from -1x (worst)
  to +3x (best).  No thresholds to tune.
* One-month signal lag; same carry model as the leverage study (cash earns rf,
  borrowing pays rf + 50 bps, shorts pay 100 bps/yr, trades cost 10 bps).

Run with::

    python build_regime_walkforward.py
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .data import resolve_project_root
from .regime_analysis import (
    GMM_FEATURES,
    _fig_to_b64,
    _img,
    _new_fig,
    _REPORT_CSS,
    _style,
    _table,
    load_macro_panel,
    MUTED_TEXT_COLOR,
    TEXT_COLOR,
)
from .sector_trend_study import (
    _perf,
    build_sector_indices,
    leverage_schedule,
    market_health,
    risk_free_monthly,
)

OUTPUT_DIR = Path("outputs") / "regime_walkforward"

N_COMPONENTS = 5
SEED = 7
MIN_HISTORY = 120           # months before the first fit (~10 years)
EXPO_MIN, EXPO_MAX = -1.0, 3.0

FIN_SPREAD_BPS = 50.0
SHORT_BORROW_BPS = 100.0
FEE_BPS = 10.0


# --------------------------------------------------------------------------- #
# 1. Walk-forward GMM exposure signal.
# --------------------------------------------------------------------------- #
@dataclass
class WalkForward:
    exposure: pd.Series        # signed exposure decided at each month-end
    n_refits: int
    first_signal: pd.Timestamp


def walk_forward_regime_exposure(macro: pd.DataFrame, asset: pd.Series) -> WalkForward:
    from sklearn.mixture import GaussianMixture
    from sklearn.preprocessing import StandardScaler

    feats = [c for c in GMM_FEATURES if c in macro.columns]
    X_all = macro[feats].dropna()
    if len(X_all) < MIN_HISTORY + 24:
        raise ValueError("Not enough macro history for a walk-forward regime test.")

    ret_m = asset.pct_change(fill_method=None)
    fwd1 = ret_m.shift(-1).reindex(X_all.index)   # fwd1[t] = return over month t+1

    expos: dict[pd.Timestamp, float] = {}
    n_refits = 0
    for i in range(MIN_HISTORY, len(X_all)):
        hist = X_all.iloc[: i + 1]                # features through month t (causal)
        Z = StandardScaler().fit_transform(hist.to_numpy())
        gm = GaussianMixture(n_components=N_COMPONENTS, covariance_type="full",
                             random_state=SEED, n_init=3, max_iter=200).fit(Z)
        lab = gm.predict(Z)
        n_refits += 1

        # Characterise clusters with returns known by t: month t' contributes
        # its next-month return, which is known once t' + 1 has closed -- so
        # every month except t itself qualifies.
        known = pd.Series(fwd1.iloc[:i].to_numpy(), index=hist.index[:-1])
        mu = known.groupby(pd.Series(lab[:-1], index=hist.index[:-1])).mean()
        mu = mu.dropna()
        cur = int(lab[-1])
        if cur in mu.index and len(mu) >= 2:
            rank_frac = float(mu.rank().loc[cur] - 1) / (len(mu) - 1)
            expo = EXPO_MIN + (EXPO_MAX - EXPO_MIN) * rank_frac
        else:
            expo = 1.0                            # unseen cluster: neutral
        expos[hist.index[-1]] = expo

    exposure = pd.Series(expos).sort_index()
    return WalkForward(exposure=exposure, n_refits=n_refits,
                       first_signal=exposure.index[0])


# --------------------------------------------------------------------------- #
# 2. Books with the leverage study's carry accounting.
# --------------------------------------------------------------------------- #
def run_book(E: pd.Series, r: pd.Series, rf: pd.Series) -> pd.Series:
    """One-month-lagged exposure with financing, borrow and trading costs."""
    fin = FIN_SPREAD_BPS / 1e4 / 12.0
    borrow = SHORT_BORROW_BPS / 1e4 / 12.0
    fee = FEE_BPS / 1e4
    E = E.reindex(r.index).shift(1)
    idle = 1.0 - E
    cash_rate = rf + (idle < 0).astype(float) * fin
    turnover = E.diff().abs().fillna(0)
    short_fee = E.clip(upper=0).abs() * borrow
    return E * r + idle * cash_rate - turnover * fee - short_fee


def signal_diagnostics(E: pd.Series, r: pd.Series) -> dict:
    """How much does the exposure line up with what happened next month?"""
    fwd = r.reindex(E.index).shift(-1)
    df = pd.DataFrame({"E": E, "fwd": fwd}).dropna()
    high = df[df["E"] >= 2.0]["fwd"]
    low = df[df["E"] <= 0.0]["fwd"]
    return {
        "IC (corr expo, next-month ret)": round(float(df["E"].corr(df["fwd"])), 2),
        "avg fwd 1m when expo>=2 (%)": round(100 * high.mean(), 2) if len(high) else np.nan,
        "avg fwd 1m when expo<=0 (%)": round(100 * low.mean(), 2) if len(low) else np.nan,
        "months expo>=2 (%)": round(100 * (df["E"] >= 2.0).mean(), 0),
        "months expo<=0 (%)": round(100 * (df["E"] <= 0.0).mean(), 0),
        "signal changes/yr": round(12 * (df["E"].diff().abs() > 0.01).mean(), 1),
    }


# --------------------------------------------------------------------------- #
# 3. Charts.
# --------------------------------------------------------------------------- #
_PALETTE = {
    "Wilshire 1x": "#9b8f77",
    "Walk-forward GMM ladder": "#0f4c5c",
    "Health-score ladder": "#4f6d3a",
    "Consensus (avg of both)": "#b56b2d",
}


def chart_equity(equity: pd.DataFrame) -> str:
    from matplotlib.gridspec import GridSpec
    fig = _new_fig((12, 6))
    gs = GridSpec(2, 1, height_ratios=[3, 1.3], hspace=0.15, figure=fig)
    ax = fig.add_subplot(gs[0]); _style(ax)
    for c in equity.columns:
        ax.plot(equity.index, equity[c], lw=1.5 if "GMM" in c else 1.0,
                color=_PALETTE.get(c, "#333"), label=c)
    ax.set_yscale("log"); ax.set_ylabel("Growth of $1 (log)")
    ax.set_title("Walk-forward regime timing vs health ladder (Wilshire, carry-adjusted)",
                 fontsize=12, loc="left")
    ax.legend(fontsize=8, loc="upper left")
    axd = fig.add_subplot(gs[1], sharex=ax); _style(axd)
    for c in equity.columns:
        e = equity[c]
        axd.plot(e.index, (e / e.cummax() - 1) * 100, lw=0.9, color=_PALETTE.get(c, "#333"))
    axd.set_ylabel("DD %", fontsize=8)
    return _fig_to_b64(fig)


def chart_exposures(e_gmm: pd.Series, e_health: pd.Series) -> str:
    fig = _new_fig((12, 4.4))
    ax = fig.add_subplot(211); _style(ax)
    ax.fill_between(e_gmm.index, 0, e_gmm.values, step="mid", alpha=0.55, color="#0f4c5c")
    ax.axhline(0, color=MUTED_TEXT_COLOR, lw=0.6)
    ax.set_ylabel("GMM expo", fontsize=8)
    ax.set_title("Exposure paths: walk-forward GMM (top) vs health ladder (bottom)",
                 fontsize=12, loc="left")
    ax2 = fig.add_subplot(212, sharex=ax); _style(ax2)
    ax2.fill_between(e_health.index, 0, e_health.values, step="mid", alpha=0.55, color="#4f6d3a")
    ax2.axhline(0, color=MUTED_TEXT_COLOR, lw=0.6)
    ax2.set_ylabel("Health expo", fontsize=8)
    return _fig_to_b64(fig)


def chart_bucket_returns(e_gmm: pd.Series, e_health: pd.Series, r: pd.Series) -> str:
    fig = _new_fig((11, 4.2)); ax = fig.add_subplot(111); _style(ax)
    buckets = [("expo ≤ 0", lambda E: E <= 0), ("0 < expo < 2", lambda E: (E > 0) & (E < 2)),
               ("expo ≥ 2", lambda E: E >= 2)]
    width = 0.35
    for j, (E, name, color) in enumerate(
            [(e_gmm, "GMM ladder", "#0f4c5c"), (e_health, "Health ladder", "#4f6d3a")]):
        fwd = r.reindex(E.index).shift(-1)
        vals = [100 * fwd[cond(E)].mean() for _, cond in buckets]
        ax.bar(np.arange(len(buckets)) + (j - 0.5) * width, vals, width,
               color=color, label=name)
    ax.axhline(0, color=MUTED_TEXT_COLOR, lw=0.8)
    ax.set_xticks(range(len(buckets)), labels=[b[0] for b in buckets])
    ax.set_ylabel("Avg next-month Wilshire return (%)")
    ax.set_title("Does the signal separate good months from bad? (higher right bars = yes)",
                 fontsize=12, loc="left")
    ax.legend(fontsize=8)
    return _fig_to_b64(fig)


# --------------------------------------------------------------------------- #
# 4. Report.
# --------------------------------------------------------------------------- #
def build_report(root: Path, fundamentals_dir: str | Path | None = "investme_sp500_data") -> Path:
    macro = load_macro_panel(root)
    wil = macro["equity_index"].dropna()
    r = wil.pct_change(fill_method=None)
    rf = risk_free_monthly(macro, r.index)

    wf = walk_forward_regime_exposure(macro, wil)

    indices, _ = build_sector_indices(root, fundamentals_dir)
    health = market_health(macro, indices, slow=10)["health"]
    e_health = leverage_schedule(health).reindex(r.index)

    # Common evaluation window: months where the walk-forward signal exists.
    start = wf.first_signal
    r_w = r.loc[start:]
    rf_w = rf.loc[start:]
    e_gmm = wf.exposure.reindex(r_w.index)
    e_h = e_health.loc[start:]
    e_avg = ((e_gmm + e_h) / 2.0)

    books = {
        "Wilshire 1x": run_book(pd.Series(1.0, index=r_w.index), r_w, rf_w),
        "Walk-forward GMM ladder": run_book(e_gmm, r_w, rf_w),
        "Health-score ladder": run_book(e_h, r_w, rf_w),
        "Consensus (avg of both)": run_book(e_avg, r_w, rf_w),
    }
    equity = pd.DataFrame({k: (1 + v.fillna(0)).cumprod() for k, v in books.items()})
    metrics = pd.DataFrame({k: _perf(v) for k, v in books.items()}).T

    diags = pd.DataFrame({
        "Walk-forward GMM": signal_diagnostics(e_gmm, r_w),
        "Health ladder": signal_diagnostics(e_h, r_w),
    }).T

    charts = {
        "equity": chart_equity(equity),
        "expo": chart_exposures(e_gmm.dropna(), e_h.dropna()),
        "buckets": chart_bucket_returns(e_gmm, e_h, r_w),
    }

    gmm_sharpe = float(metrics.loc["Walk-forward GMM ladder", "Sharpe"])
    h_sharpe = float(metrics.loc["Health-score ladder", "Sharpe"])
    base_sharpe = float(metrics.loc["Wilshire 1x", "Sharpe"])
    if gmm_sharpe > max(h_sharpe, base_sharpe) + 0.05:
        verdict = ("The walk-forward Dalio-regime signal <b>does</b> add timing value here: "
                   "it beats both buy-&-hold and the health ladder on risk-adjusted return.")
    elif gmm_sharpe > base_sharpe + 0.05:
        verdict = ("The walk-forward Dalio-regime signal adds value over buy-&-hold but does "
                   "<b>not</b> beat the simpler health ladder — the cheap signal wins.")
    else:
        verdict = ("The walk-forward Dalio-regime signal does <b>not</b> improve on buy-&-hold "
                   "once fit causally — its full-sample elegance does not survive real-time use. "
                   "Keep the GMM as narrative context, not as a sizing input.")

    span = f"{r_w.index[0]:%Y-%m} → {r_w.index[-1]:%Y-%m}"
    p = []
    p.append(f"""<header><h1>Walk-Forward Regime Timing Test</h1>
      <p class="subtitle">Can the Dalio-style GMM macro regimes time the market when fit
      <b>causally</b> (refit every month on an expanding window, clusters characterised only by
      returns known at the time)? Evaluated on the Wilshire total-market index — no survivorship
      bias — over {span} ({wf.n_refits} monthly refits), against the market-health ladder from the
      sector trend study, with identical carry costs.</p></header>""")

    p.append(f"""<section class="now"><h2>Verdict</h2><p>{verdict}</p></section>""")

    p.append(f"""<section><h2>1 · Equity curves</h2>
      <p>All books trade the same index with a one-month signal lag. Carry: cash earns rf,
      borrowing pays rf + {FIN_SPREAD_BPS:.0f} bps, shorts pay {SHORT_BORROW_BPS:.0f} bps/yr,
      trades cost {FEE_BPS:.0f} bps.</p>
      {_img(charts['equity'], 'Walk-forward regime timing equity curves')}
      {_table(metrics)}</section>""")

    p.append(f"""<section><h2>2 · What each signal actually did</h2>
      {_img(charts['expo'], 'Exposure paths')}
      {_img(charts['buckets'], 'Average next-month return by exposure bucket')}
      {_table(diags)}</section>""")

    p.append(f"""<section class="method"><h2>Method &amp; caveats</h2><ul>
      <li><b>Pre-registered mapping.</b> Exposure is linear in the cluster's past-performance rank,
      from −1× (worst) to +3× (best): no tunable thresholds. k={N_COMPONENTS}, seed {SEED},
      first fit after {MIN_HISTORY} months.</li>
      <li><b>Label churn is real.</b> Refitting monthly re-draws cluster boundaries; the exposure
      path (not the label names) is the tradable object, and its turnover is charged.</li>
      <li><b>The health ladder's thresholds were tuned in-sample</b> in the original study, so it
      carries a small hindsight advantage in this race; the GMM mapping does not.</li>
      <li><b>One asset, ~16 years, ~2 full cycles.</b> Statistical power is limited; treat the
      verdict as evidence, not proof.</li></ul></section>""")

    doc = (f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"/>"
           f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>"
           f"<title>Walk-Forward Regime Timing Test</title><style>{_REPORT_CSS}</style></head>"
           f"<body><main>{''.join(p)}</main></body></html>")

    out_dir = root / OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(doc, encoding="utf-8")
    metrics.to_csv(out_dir / "metrics.csv")
    diags.to_csv(out_dir / "signal_diagnostics.csv")
    pd.DataFrame({"gmm_expo": e_gmm, "health_expo": e_h}).to_csv(out_dir / "exposures.csv")
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
    print(f"Wrote walk-forward regime test to {out}")


if __name__ == "__main__":
    main()
