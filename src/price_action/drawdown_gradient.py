"""Drawdown gradient study: where does buying the dip pay best, and what does
it cost to survive there?

Questions answered, with realistic assumptions (next-close execution,
price-only closes disclosed, overlapping forward windows disclosed, causal
health/narrative alignment):

A. SPY forward returns by ATH-drawdown depth bucket -- the gradient -- plus
   the *additional* drawdown suffered after entering at each depth (the
   number that determines margin survival, not the entry depth itself).
B. The same gradient conditioned on market regime (health bands, trend
   state) and on the nine weekly narratives.
C. Per-sector drawdown gradients (11 SPDRs).
D. Golden-cross outcomes by macro regime (from the Dalio model's daily cross
   study -- extended vs contracted trend times).
E. Survival math for the user's plan: enter levered <=2x, add equal margin
   when threatened (which de-levers to ~1x on cost), DCA otherwise.

Run with::

    python build_drawdown_gradient.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .data import resolve_project_root

OUTPUT_DIR = Path("outputs") / "drawdown_gradient"
BUCKETS = [0.0, -0.05, -0.10, -0.15, -0.20, -0.25, -0.30, -0.40, -0.60]
BUCKET_LABELS = ["0 to -5%", "-5 to -10%", "-10 to -15%", "-15 to -20%",
                 "-20 to -25%", "-25 to -30%", "-30 to -40%", "-40% and deeper"]
SECTOR_ETFS = ["XLK", "XLF", "XLV", "XLI", "XLY", "XLP", "XLC", "XLRE", "XLB", "XLE", "XLU"]


def load_close(root: Path, symbol: str) -> pd.Series:
    px = pd.read_csv(root / "cache" / "advise" / f"{symbol}_daily.csv", parse_dates=["date"])
    s = px.set_index("date")["close"].dropna()
    s.index = s.index.normalize()
    return s


def bucket_of(dd: pd.Series) -> pd.Series:
    return pd.cut(dd, bins=BUCKETS[::-1], labels=BUCKET_LABELS[::-1], right=True)


def forward(px: pd.Series, days: int) -> pd.Series:
    return px.shift(-days) / px - 1.0


def additional_drawdown_after(px: pd.Series) -> pd.Series:
    """From each day's close: the worst further decline before the next ATH
    (or end of data). This is the pain-after-entry number."""
    ath = px.cummax()
    out = np.full(len(px), np.nan)
    values = px.to_numpy()
    ath_v = ath.to_numpy()
    # future minimum until price next exceeds the running ATH at entry
    n = len(values)
    for i in range(n):
        target = ath_v[i]
        j = i
        lo = values[i]
        while j < n and values[j] < target:
            lo = min(lo, values[j])
            j += 1
        if j >= n and values[i] >= target:  # at ATH, no episode
            out[i] = 0.0
        else:
            out[i] = lo / values[i] - 1.0
    return pd.Series(out, index=px.index)


def gradient_table(px: pd.Series, extra: dict[str, pd.Series] | None = None) -> pd.DataFrame:
    dd = px / px.cummax() - 1.0
    frame = pd.DataFrame({
        "bucket": bucket_of(dd),
        "fwd_6m": forward(px, 126),
        "fwd_12m": forward(px, 252),
        "add_dd": additional_drawdown_after(px),
    })
    if extra:
        for k, v in extra.items():
            frame[k] = v.reindex(frame.index, method="ffill")
    grouped = frame.dropna(subset=["bucket", "fwd_12m"]).groupby("bucket", observed=True)
    out = pd.DataFrame({
        "days": grouped.size(),
        "fwd6m_%": (grouped["fwd_6m"].mean() * 100).round(1),
        "fwd12m_%": (grouped["fwd_12m"].mean() * 100).round(1),
        "fwd12m_hit_%": (grouped["fwd_12m"].apply(lambda s: (s > 0).mean()) * 100).round(0),
        "fwd12m_p10_%": (grouped["fwd_12m"].quantile(0.10) * 100).round(1),
        "fwd12m_vol_%": (grouped["fwd_12m"].std() * 100).round(1),
        "med_add_dd_%": (grouped["add_dd"].median() * 100).round(1),
        "p90_add_dd_%": (grouped["add_dd"].quantile(0.10) * 100).round(1),  # 10th pct = bad tail
        "P(add_dd>20%)_%": (grouped["add_dd"].apply(lambda s: (s < -0.20).mean()) * 100).round(0),
        "P(add_dd>33%)_%": (grouped["add_dd"].apply(lambda s: (s < -0.33).mean()) * 100).round(0),
    })
    out["fwd12m_sharpe"] = (out["fwd12m_%"] / out["fwd12m_vol_%"]).round(2)
    return out.reindex(BUCKET_LABELS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=None)
    args = parser.parse_args()
    root = resolve_project_root(args.project_root)
    out_dir = root / OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    spy = load_close(root, "SPY")
    health = pd.read_csv(root / "outputs/sector_trend_report/market_health.csv",
                         parse_dates=[0], index_col=0)["health"].dropna()

    # A. Unconditional SPY gradient
    grad = gradient_table(spy)
    grad.to_csv(out_dir / "spy_gradient.csv")
    print("=== A. SPY drawdown gradient (1998-2026, next-close basis) ===")
    print(grad.to_string())

    # B1. Gradient x health band
    dd = spy / spy.cummax() - 1.0
    h = health.reindex(spy.index, method="ffill")
    frame = pd.DataFrame({"bucket": bucket_of(dd), "fwd_12m": forward(spy, 252),
                          "health_band": pd.cut(h, [0, 40, 55, 100], labels=["H<40", "H 40-55", "H>=55"])})
    xt = (frame.dropna().groupby(["bucket", "health_band"], observed=True)["fwd_12m"]
          .agg(["mean", "size"]))
    xt["mean"] = (xt["mean"] * 100).round(1)
    pivot_mean = xt["mean"].unstack()
    pivot_n = xt["size"].unstack()
    pivot_mean.to_csv(out_dir / "spy_gradient_by_health.csv")
    print("\n=== B1. Fwd 12m % by drawdown bucket x health band (n in brackets) ===")
    merged = pivot_mean.astype(str) + " (" + pivot_n.fillna(0).astype(int).astype(str) + ")"
    print(merged.reindex(BUCKET_LABELS).to_string())

    # B2. Gradient x weekly narrative (2007+, from the saved narrative panel)
    narr_path = Path("/private/tmp/claude-501/-Users-timursabitov-Dev-price-action/"
                     "6a669786-b1a4-4a6c-814e-5d1deb65b61a/scratchpad/narrative_panel.csv")
    if narr_path.exists():
        weekly = pd.read_csv(narr_path, parse_dates=[0], index_col=0)
        weekly["state"] = weekly["narrative"].str[0].astype(int)
        weekly["bucket"] = bucket_of(weekly["dd"])
        nt = (weekly.dropna(subset=["bucket", "fwd_3m"])
              .groupby(["state", "bucket"], observed=True)["fwd_3m"].agg(["mean", "size"]))
        nt["mean"] = (nt["mean"] * 100).round(1)
        view = nt[nt["size"] >= 8]  # suppress micro-samples
        view.to_csv(out_dir / "spy_gradient_by_narrative.csv")
        print("\n=== B2. Fwd 3m % by narrative state x drawdown bucket (weekly, n>=8 only) ===")
        print(view.to_string())

    # C. Sector gradients (fwd 12m by bucket)
    rows = {}
    counts = {}
    for etf in SECTOR_ETFS:
        try:
            px = load_close(root, etf)
        except FileNotFoundError:
            continue
        sdd = px / px.cummax() - 1.0
        sf = pd.DataFrame({"bucket": bucket_of(sdd), "fwd_12m": forward(px, 252)}).dropna()
        g = sf.groupby("bucket", observed=True)["fwd_12m"]
        rows[etf] = (g.mean() * 100).round(1)
        counts[etf] = g.size()
    sector_grad = pd.DataFrame(rows).reindex(BUCKET_LABELS)
    sector_n = pd.DataFrame(counts).reindex(BUCKET_LABELS)
    sector_grad.to_csv(out_dir / "sector_gradient_fwd12m.csv")
    sector_n.to_csv(out_dir / "sector_gradient_counts.csv")
    print("\n=== C. Sector fwd 12m % by own-ATH drawdown bucket ===")
    print(sector_grad.to_string())

    # D. Golden crosses by macro regime (existing Dalio daily cross study)
    cross_path = root / "outputs/sector_dalio_regime_model/daily_50_200_cross_by_regime.csv"
    if cross_path.exists():
        crosses = pd.read_csv(cross_path)
        golden = crosses[crosses["cross_type"] == "golden"].sort_values("avg_fwd_126d_%", ascending=False)
        cols = ["environment_family", "environment", "events", "whipsaw_rate_%", "avg_fwd_126d_%", "hit_fwd_126d_%"]
        print("\n=== D. Golden crosses by macro environment (Dalio daily cross study) ===")
        print(golden[cols].to_string(index=False))
        golden[cols].to_csv(out_dir / "golden_cross_by_regime.csv", index=False)

    # E. Survival math for the user's plan
    print("\n=== E. Survival math: enter 2x at depth X, 25% maintenance ===")
    print("2x liquidation needs a FURTHER -33.3% from entry; adding equal margin")
    print("de-levers to ~1x on cost (no liquidation path).")
    surv = grad[["med_add_dd_%", "p90_add_dd_%", "P(add_dd>20%)_%", "P(add_dd>33%)_%"]]
    print(surv.to_string())


if __name__ == "__main__":
    main()
