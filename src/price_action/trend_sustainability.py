"""Trend sustainability: do volume / VWAP confirm golden & death crosses?

Compares three ways of defining a trend on SPY and the 11 SPDR sectors, all
causal (signal at close t, act at close t+1) and realistically costed:

  1. **SMA cross** -- the 50/200 golden/death state (2% hysteresis band).
  2. **VWAP-confirmed cross** -- the same cross, but only taken when volume
     agrees (close on the trend side of the 200d rolling VWAP *and* OBV on the
     trend side of its own 50d average), and exited early when price loses the
     anchored VWAP struck at the cross. Price action / volume override.
  3. **Price-vs-VWAP** -- pure price action: long while close > 200d rolling
     VWAP, no SMA cross at all.

For every historical cross it records what volume looked like *at* the cross
(causal), how long the trend then lasted (right-censored -- the still-open
final cross gets no whipsaw verdict, matching the repo's censoring fix), its
max favorable excursion, and forward returns. Sustainability is then compared
between volume-**confirmed** and volume-**divergent** crosses via duration
distributions, whipsaw rates, survival curves, and a fair-accounting backtest.

Realism: SMA / VWAP / OBV use raw traded closes (what a trader sees); equity
and forward returns use dividend-adjusted closes (total return). 10 bps per
unit turnover; idle capital earns the 2y T-note rate. Both disclosed.

Run with::

    python build_trend_sustainability.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .data import resolve_project_root

OHLCV_DIR = Path("cache") / "market_structure"
OUTPUT_DIR = Path("outputs") / "trend_sustainability"
SYMBOLS = ["SPY", "XLK", "XLF", "XLV", "XLI", "XLY", "XLP", "XLC", "XLRE", "XLB", "XLE", "XLU"]
FAST, SLOW = 50, 200
BAND = 0.02
VWAP_WINDOW = 200
WHIPSAW_DAYS = 63
BREAKOUT = 0.05
FEE = 0.0010
BORROW_RF_ONLY = True


# --------------------------------------------------------------------------- #
# Indicators (all causal / trailing).
# --------------------------------------------------------------------------- #
def load_ohlcv(root: Path, symbol: str) -> pd.DataFrame:
    path = root / OHLCV_DIR / f"{symbol}_ohlcv.csv"
    frame = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    frame.index = frame.index.normalize()
    return frame[~frame.index.duplicated(keep="last")]


def rolling_vwap(frame: pd.DataFrame, window: int) -> pd.Series:
    typical = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    pv = (typical * frame["volume"]).rolling(window, min_periods=window).sum()
    vv = frame["volume"].rolling(window, min_periods=window).sum().replace(0.0, np.nan)
    return pv / vv


def anchored_vwap(frame: pd.DataFrame, anchor_pos: int) -> pd.Series:
    typical = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    seg_pv = (typical * frame["volume"]).iloc[anchor_pos:].cumsum()
    seg_vv = frame["volume"].iloc[anchor_pos:].cumsum().replace(0.0, np.nan)
    return seg_pv / seg_vv


def on_balance_volume(frame: pd.DataFrame) -> pd.Series:
    direction = np.sign(frame["close"].diff().fillna(0.0))
    return (direction * frame["volume"]).cumsum()


def cross_state(close: pd.Series) -> pd.Series:
    fast = close.rolling(FAST, min_periods=FAST).mean()
    slow = close.rolling(SLOW, min_periods=SLOW).mean()
    spread = fast / slow - 1.0
    state = np.full(len(close), np.nan)
    cur = np.nan
    for i, v in enumerate(spread.to_numpy()):
        if np.isnan(v):
            continue
        if v > BAND:
            cur = 1.0
        elif v < -BAND:
            cur = 0.0
        state[i] = cur
    return pd.Series(state, index=close.index)


# --------------------------------------------------------------------------- #
# Cross catalog with volume confirmation, per symbol.
# --------------------------------------------------------------------------- #
def cross_events(root: Path, symbol: str) -> pd.DataFrame:
    frame = load_ohlcv(root, symbol)
    if len(frame) < SLOW + 60:
        return pd.DataFrame()
    close = frame["close"]
    state = cross_state(close)
    vwap = rolling_vwap(frame, VWAP_WINDOW)
    obv = on_balance_volume(frame)
    obv_ma = obv.rolling(FAST, min_periods=FAST).mean()
    vol_z = ((frame["volume"] - frame["volume"].rolling(63, min_periods=63).mean())
             / frame["volume"].rolling(63, min_periods=63).std())

    changes = state.diff().fillna(0.0)
    cross_idx = [i for i in range(len(state)) if changes.iloc[i] != 0 and not np.isnan(state.iloc[i])]

    rows: list[dict] = []
    for n, pos in enumerate(cross_idx):
        is_golden = state.iloc[pos] == 1.0
        direction = 1.0 if is_golden else -1.0
        end_pos = cross_idx[n + 1] if n + 1 < len(cross_idx) else len(frame) - 1
        is_final = n + 1 >= len(cross_idx)
        p0 = float(close.iloc[pos])
        seg = close.iloc[pos:end_pos + 1]
        mfe = float(((seg / p0 - 1.0) * direction).max())
        duration = int(end_pos - pos)

        # causal confirmation, evaluated AT the cross bar
        px_vs_vwap = float(close.iloc[pos] - vwap.iloc[pos]) if not np.isnan(vwap.iloc[pos]) else np.nan
        obv_gap = float(obv.iloc[pos] - obv_ma.iloc[pos]) if not np.isnan(obv_ma.iloc[pos]) else np.nan
        volz_win = float(vol_z.iloc[max(0, pos - 5):pos + 1].mean())
        c_vwap = (np.sign(px_vs_vwap) == direction) if not np.isnan(px_vs_vwap) else np.nan
        c_obv = (np.sign(obv_gap) == direction) if not np.isnan(obv_gap) else np.nan
        confirmed = (bool(c_vwap) and bool(c_obv)) if (c_vwap is not np.nan and c_obv is not np.nan) else np.nan

        # right-censored whipsaw verdict
        resolved = (not is_final) or (duration > WHIPSAW_DAYS and mfe >= BREAKOUT)
        whipsaw = (float((duration <= WHIPSAW_DAYS) or (mfe < BREAKOUT)) if resolved else np.nan)

        row = {
            "symbol": symbol, "date": frame.index[pos], "type": "golden" if is_golden else "death",
            "price": round(p0, 2), "duration_d": duration, "mfe_%": round(mfe * 100, 1),
            "px_vs_vwap200": round(px_vs_vwap, 2) if not np.isnan(px_vs_vwap) else np.nan,
            "vol_z_at_cross": round(volz_win, 2) if not np.isnan(volz_win) else np.nan,
            "c_vwap": c_vwap, "c_obv": c_obv, "confirmed": confirmed,
            "whipsaw": whipsaw, "censored": bool(not resolved),
        }
        for h in (63, 126, 252):
            row[f"fwd_{h}d_%"] = (round((float(close.iloc[pos + h]) / p0 - 1.0) * 100, 1)
                                  if pos + h < len(close) else np.nan)
        rows.append(row)
    return pd.DataFrame(rows)


def sustainability_summary(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cross_type in ("golden", "death"):
        sub = events[events["type"] == cross_type]
        for label, mask in (("confirmed", sub["confirmed"] == True),  # noqa: E712
                            ("divergent", sub["confirmed"] == False)):  # noqa: E712
            grp = sub[mask]
            resolved = grp["whipsaw"].dropna()
            rows.append({
                "cross": cross_type, "volume": label, "events": len(grp),
                "median_duration_d": int(grp["duration_d"].median()) if len(grp) else np.nan,
                "whipsaw_rate_%": round(float(resolved.mean()) * 100, 0) if len(resolved) else np.nan,
                "median_mfe_%": round(float(grp["mfe_%"].median()), 1) if len(grp) else np.nan,
                "fwd126d_%": round(float(grp["fwd_126d_%"].mean()), 1) if len(grp) else np.nan,
                "fwd252d_%": round(float(grp["fwd_252d_%"].mean()), 1) if len(grp) else np.nan,
            })
    return pd.DataFrame(rows)


def survival_curve(events: pd.DataFrame, cross_type: str, horizon: int = 504) -> pd.DataFrame:
    """Fraction of trends still alive at day d, confirmed vs divergent."""
    out = {"day": list(range(0, horizon + 1, 21))}
    sub = events[(events["type"] == cross_type)]
    for label, mask in (("confirmed", sub["confirmed"] == True),  # noqa: E712
                        ("divergent", sub["confirmed"] == False)):  # noqa: E712
        durations = sub[mask]["duration_d"].to_numpy()
        n = len(durations)
        out[label] = [round(float((durations >= d).mean()), 3) if n else np.nan
                      for d in out["day"]]
    return pd.DataFrame(out)


# --------------------------------------------------------------------------- #
# Backtest: three trend definitions, fair accounting.
# --------------------------------------------------------------------------- #
def _rf_daily(root: Path, index: pd.DatetimeIndex) -> pd.Series:
    macro = pd.read_csv(root / "cache/macro_daily_1999.csv", parse_dates=["date"]).set_index("date")
    rf = (macro["us_2y_yield"].dropna() / 100.0 / 252.0)
    return rf.reindex(index, method="ffill").fillna(0.0)


def _book(exposure: pd.Series, ret: pd.Series, rf: pd.Series) -> pd.Series:
    E = exposure.shift(1).fillna(0.0).clip(0.0, 1.0)  # 1-bar execution lag
    turnover = E.diff().abs().fillna(0.0)
    idle = (1.0 - E).clip(lower=0.0)
    return E * ret + idle * rf - turnover * FEE


def _perf(r: pd.Series, exposure: pd.Series) -> dict:
    r = r.dropna()
    eq = (1 + r).cumprod()
    yrs = (r.index[-1] - r.index[0]).days / 365.25
    vol = float(r.std() * np.sqrt(252))
    E = exposure.shift(1).fillna(0.0)
    trades = int((E.diff().abs() > 0).sum())
    # avg holding length of long stretches
    runs, cur = [], 0
    for v in (E > 0).to_numpy():
        if v:
            cur += 1
        elif cur:
            runs.append(cur); cur = 0
    if cur:
        runs.append(cur)
    return {
        "growth": round(float(eq.iloc[-1]), 2),
        "cagr_%": round(float(eq.iloc[-1] ** (1 / yrs) - 1) * 100, 1),
        "vol_%": round(vol * 100, 1),
        "sharpe": round(float(r.mean() * 252 / vol), 2) if vol > 0 else None,
        "maxdd_%": round(float((eq / eq.cummax() - 1).min()) * 100, 0),
        "time_in_mkt_%": round(float((E > 0).mean()) * 100, 0),
        "trades": trades,
        "avg_hold_d": int(np.mean(runs)) if runs else 0,
    }


def backtest_symbol(root: Path, symbol: str) -> tuple[dict, pd.DataFrame]:
    frame = load_ohlcv(root, symbol)
    close = frame["close"]
    adj = frame["adjclose"]
    ret = adj.pct_change().fillna(0.0)
    rf = _rf_daily(root, frame.index)
    state = cross_state(close)
    vwap = rolling_vwap(frame, VWAP_WINDOW)
    obv = on_balance_volume(frame)
    obv_ma = obv.rolling(FAST, min_periods=FAST).mean()

    # Book 1: plain cross
    e_cross = state.fillna(0.0)

    # Book 3: price vs 200d VWAP
    e_vwap = (close > vwap).astype(float)

    # Book 2: enter only on a volume-confirmed golden cross; stay in that
    # regime until a death cross; but step aside (to cash) whenever price is
    # below the 200d VWAP -- the price-action / volume override -- and step
    # back in when it reclaims it. No hair-trigger anchored-VWAP exit.
    cross_set = {i for i in range(len(state))
                 if state.diff().fillna(0.0).iloc[i] != 0 and not np.isnan(state.iloc[i])}
    e_conf = np.zeros(len(frame))
    regime_on = False
    for i in range(len(frame)):
        if i in cross_set and state.iloc[i] == 1.0:
            c_vwap = (not np.isnan(vwap.iloc[i])) and close.iloc[i] > vwap.iloc[i]
            c_obv = (not np.isnan(obv_ma.iloc[i])) and obv.iloc[i] > obv_ma.iloc[i]
            if c_vwap and c_obv:
                regime_on = True
        if i in cross_set and state.iloc[i] == 0.0:
            regime_on = False
        above_vwap = (not np.isnan(vwap.iloc[i])) and close.iloc[i] >= vwap.iloc[i]
        e_conf[i] = 1.0 if (regime_on and above_vwap) else 0.0
    e_conf = pd.Series(e_conf, index=frame.index)

    # Book 2b: volume as a pure FILTER -- take the cross only when confirmed,
    # then hold to the death cross exactly like the plain cross (no VWAP
    # step-aside). Directly monetizes the sustainability finding.
    e_filter = np.zeros(len(frame))
    regime_on = False
    for i in range(len(frame)):
        if i in cross_set and state.iloc[i] == 1.0:
            c_vwap = (not np.isnan(vwap.iloc[i])) and close.iloc[i] > vwap.iloc[i]
            c_obv = (not np.isnan(obv_ma.iloc[i])) and obv.iloc[i] > obv_ma.iloc[i]
            regime_on = bool(c_vwap and c_obv)
        if i in cross_set and state.iloc[i] == 0.0:
            regime_on = False
        e_filter[i] = 1.0 if regime_on else 0.0
    e_filter = pd.Series(e_filter, index=frame.index)

    books = {
        "SMA cross": e_cross,
        "Confirmed-cross filter": e_filter,
        "Cross + VWAP step-aside": e_conf,
        "Price vs 200d VWAP": e_vwap,
        "Buy & hold": pd.Series(1.0, index=frame.index),
    }
    perf = {name: _perf(_book(E, ret, rf), E) for name, E in books.items()}
    curves = pd.DataFrame({name: (1 + _book(E, ret, rf)).cumprod() for name, E in books.items()})
    return perf, curves


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--symbol", default=None, help="Single symbol; default = all.")
    args = parser.parse_args()
    root = resolve_project_root(args.project_root)
    out_dir = root / OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    symbols = [args.symbol.upper()] if args.symbol else SYMBOLS

    all_events = []
    for s in symbols:
        try:
            ev = cross_events(root, s)
        except FileNotFoundError:
            print(f"{s}: no OHLCV cache, skipping")
            continue
        if not ev.empty:
            all_events.append(ev)
    events = pd.concat(all_events, ignore_index=True)
    events.to_csv(out_dir / "cross_events.csv", index=False)

    print("=== Sustainability: volume-confirmed vs divergent crosses (all symbols pooled) ===")
    pooled = sustainability_summary(events)
    print(pooled.to_string(index=False))
    pooled.to_csv(out_dir / "sustainability_pooled.csv", index=False)

    print("\n=== SPY only ===")
    spy_sum = sustainability_summary(events[events["symbol"] == "SPY"])
    print(spy_sum.to_string(index=False))

    surv = survival_curve(events, "golden")
    surv.to_csv(out_dir / "survival_golden.csv", index=False)
    print("\n=== Golden-cross survival (fraction still trending at day d) ===")
    print(surv.to_string(index=False))

    print("\n=== Backtest: three trend definitions (fair accounting, 1-bar lag) ===")
    perf_rows = {}
    curves_store = {}
    for s in symbols:
        try:
            perf, curves = backtest_symbol(root, s)
        except FileNotFoundError:
            continue
        for book, m in perf.items():
            perf_rows[(s, book)] = m
        curves_store[s] = curves
    perf_df = pd.DataFrame(perf_rows).T
    perf_df.index.names = ["symbol", "book"]
    perf_df.to_csv(out_dir / "backtest_by_symbol.csv")
    spy_perf = perf_df.loc["SPY"]
    print("SPY:")
    print(spy_perf.to_string())

    # pooled average metrics across symbols per book
    print("\n=== Average across all symbols, by book ===")
    avg = perf_df.groupby("book")[["cagr_%", "vol_%", "sharpe", "maxdd_%", "time_in_mkt_%", "trades", "avg_hold_d"]].mean().round(2)
    print(avg.to_string())
    avg.to_csv(out_dir / "backtest_avg.csv")
    if "SPY" in curves_store:
        curves_store["SPY"].to_csv(out_dir / "spy_equity_curves.csv")

    diag = {
        "symbols": symbols, "crosses": int(len(events)),
        "confirmed_share_%": round(float((events["confirmed"] == True).mean()) * 100, 0),  # noqa: E712
        "note": "SMA/VWAP/OBV on raw close; returns on adjclose; 10bps turnover; idle earns 2y rate; 1-bar lag.",
    }
    (out_dir / "diagnostics.json").write_text(json.dumps(diag, indent=1))
    print("\ndiagnostics:", json.dumps(diag))


if __name__ == "__main__":
    main()
