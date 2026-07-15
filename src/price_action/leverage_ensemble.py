"""Leverage ensemble: can oscillator + VIX + CFTC + narratives earn 0-3x?

An ensemble of five exposure models on SPY, weekly rebalance, built to the
repo's leakage standard and designed to answer one question honestly: does
combining the session's instruments justify *accelerating* leverage above
1x, or does the walk-forward lever-up verdict (negative timing IC) survive?

Leakage controls
----------------
* Signals at week t use only data through Friday t's close; exposure is held
  over week t+1 (one-week execution lag on everything).
* CFTC positioning is release-aligned (+6 calendar days: Tuesday report,
  Friday publication, usable Monday).
* The oscillator series contains only completed month-end values, forward-
  filled; health likewise (both are causal rolling constructions).
* The narrative member is *learned walk-forward*: each week's state->exposure
  map uses only past forward returns (expanding window, min 20 obs per state).
* Sign disclosure: the fixed-form members' signs (osc +, VIX contrarian -,
  crowding contrarian -) come from earlier studies on overlapping data. That
  is prior knowledge, not in-window fitting, but it is not innocent either --
  the learned-signs variant (walk-forward OLS per signal) is run alongside as
  the robustness check.

Ensemble (all prespecified before running)
------------------------------------------
  M_osc  = clip(1 + osc_z-ish (raw osc, already bounded), 0, 2)
  M_vix  = clip(1 - 0.5 * vix_z, 0, 2)          (de-risk on vol spikes)
  M_cot  = clip(1 - 0.5 * am_z, 0, 2)           (fade asset-mgr crowding)
  M_narr = clip(past_state_mean / past_uncond_mean, 0, 2), walk-forward
  G      = health governor: 1.0 (H>=55), 0.5 (40-55), 0.25 (<40) -- de-risk only

  E_dir  = mean(M_osc, M_vix, M_cot, M_narr)
  Acceleration rule: if min(members) >= 1.25 (unanimous bullish), E_dir *= 1.5
  E      = clip(E_dir * G, 0, 3)

Costs: fees 10 bps per unit turnover, borrow (E-1)+ at rf+150bps, idle cash
earns rf. Daily-reset leverage form (no margin-call path) -- the friendliest
possible case for leverage, as in the sector-cross study.

Run with::

    python build_leverage_ensemble.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .data import resolve_project_root

OUTPUT_DIR = Path("outputs") / "leverage_ensemble"
FEE = 0.0010
BORROW_SPREAD = 0.015
MIN_TRAIN_WEEKS = 156
STATE_MIN_OBS = 20
ACCEL_THRESHOLD = 1.25
ACCEL_FACTOR = 1.5


def _roll_z(series: pd.Series, window: int = 156, min_periods: int = 52) -> pd.Series:
    mean = series.rolling(window, min_periods=min_periods).mean()
    std = series.rolling(window, min_periods=min_periods).std()
    return ((series - mean) / std).clip(-3, 3)


def build_weekly_panel(root: Path) -> pd.DataFrame:
    spy = pd.read_csv(root / "cache/advise/SPY_daily.csv", parse_dates=["date"]).set_index("date")["close"].dropna()
    spy.index = spy.index.normalize()
    osc = pd.read_csv(root / "outputs/momentum_oscillator/oscillator_series.csv",
                      parse_dates=["date"]).set_index("date")["oscillator"].dropna()
    health = pd.read_csv(root / "outputs/sector_trend_report/market_health.csv",
                         parse_dates=[0], index_col=0)["health"].dropna()
    vix = pd.read_csv(root / "fred/VIXCLS.csv", parse_dates=[0])
    vix.columns = ["date", "vix"]
    vix = vix.set_index("date")["vix"].dropna()
    cot = pd.read_csv(root / "outputs/market_structure/cot_panel.csv", parse_dates=[0], index_col=0)

    rf = (pd.read_csv(root / "cache/macro_daily_1999.csv", parse_dates=["date"]).set_index("date")["us_2y_yield"]
          .dropna() / 100.0)

    ma50 = spy.rolling(50, min_periods=50).mean()
    ma200 = spy.rolling(200, min_periods=200).mean()
    spread = ma50 / ma200 - 1.0
    state = pd.Series(np.nan, index=spy.index)
    cur = np.nan
    for i, v in enumerate(spread.to_numpy()):
        if np.isnan(v):
            continue
        if v > 0.02:
            cur = 1.0
        elif v < -0.02:
            cur = 0.0
        state.iloc[i] = cur

    dd = spy / spy.cummax() - 1.0
    ret20 = spy.pct_change(20)

    weekly = pd.DataFrame(index=spy.resample("W-FRI").last().dropna().index)
    align = lambda s: s.reindex(weekly.index, method="ffill")
    weekly["spy"] = align(spy)
    weekly["ret_next"] = weekly["spy"].shift(-1) / weekly["spy"] - 1.0  # held over week t+1
    weekly["rf_w"] = align(rf) / 52.0
    weekly["trend_up"] = align(state)
    weekly["dd"] = align(dd)
    weekly["ret20"] = align(ret20)
    weekly["osc"] = align(osc)
    weekly["osc_chg3m"] = weekly["osc"] - weekly["osc"].shift(13)
    weekly["health"] = align(health)
    weekly["vix_z"] = _roll_z(align(vix))
    weekly["am_z"] = align(cot["asset_mgr_net_pct_oi_z"])  # already release-aligned upstream
    return weekly.dropna(subset=["trend_up", "osc", "health", "vix_z", "am_z", "ret_next"])


def classify_states(weekly: pd.DataFrame) -> pd.Series:
    from .advise import classify_narrative
    return pd.Series(
        [classify_narrative(trend_up=bool(r.trend_up), dd=float(r.dd), ret20=float(r.ret20),
                            osc=float(r.osc), osc_chg3m=float(r.osc_chg3m),
                            health=float(r.health), am_z=float(r.am_z))
         for r in weekly.itertuples()],
        index=weekly.index,
    )


def narrative_member(weekly: pd.DataFrame, states: pd.Series) -> pd.Series:
    """Walk-forward state->exposure map from past state forward returns only."""
    exposures = np.full(len(weekly), 1.0)
    rets = weekly["ret_next"].to_numpy()
    arr = states.to_numpy()
    for i in range(len(weekly)):
        if i < MIN_TRAIN_WEEKS:
            continue
        past_r, past_s = rets[:i - 1], arr[:i - 1]  # -1: last week's fwd return not yet known
        uncond = np.nanmean(past_r)
        mask = past_s == arr[i]
        if mask.sum() >= STATE_MIN_OBS and uncond > 0:
            exposures[i] = float(np.clip(np.nanmean(past_r[mask]) / uncond, 0.0, 2.0))
    return pd.Series(exposures, index=weekly.index)


def learned_signs_member_panel(weekly: pd.DataFrame) -> pd.DataFrame:
    """Robustness: per-signal walk-forward OLS slope decides sign AND scale."""
    out = {}
    rets = weekly["ret_next"].to_numpy()
    for col in ("osc", "vix_z", "am_z"):
        x = weekly[col].to_numpy()
        exposure = np.full(len(weekly), 1.0)
        for i in range(MIN_TRAIN_WEEKS, len(weekly)):
            xs, ys = x[:i - 1], rets[:i - 1]
            ok = ~(np.isnan(xs) | np.isnan(ys))
            if ok.sum() < 100:
                continue
            beta = np.polyfit(xs[ok], ys[ok], 1)[0]
            resid_std = np.nanstd(ys[ok])
            tilt = beta * x[i] / resid_std if resid_std > 0 else 0.0
            exposure[i] = float(np.clip(1.0 + 10.0 * tilt, 0.0, 2.0))
        out[col] = exposure
    return pd.DataFrame(out, index=weekly.index)


def governor(health: pd.Series) -> pd.Series:
    g = pd.Series(1.0, index=health.index)
    g[health < 55] = 0.5
    g[health < 40] = 0.25
    return g


def run_book(weekly: pd.DataFrame, exposure: pd.Series) -> pd.Series:
    E = exposure.clip(0.0, 3.0)
    turnover = E.diff().abs().fillna(0.0)
    borrow = (E - 1.0).clip(lower=0.0)
    idle = (1.0 - E).clip(lower=0.0)
    return (E * weekly["ret_next"] + idle * weekly["rf_w"]
            - borrow * (weekly["rf_w"] + BORROW_SPREAD / 52.0) - turnover * FEE)


def perf(r: pd.Series) -> dict:
    r = r.dropna()
    eq = (1 + r).cumprod()
    yrs = (r.index[-1] - r.index[0]).days / 365.25
    vol = float(r.std() * np.sqrt(52))
    return {"growth": round(float(eq.iloc[-1]), 2),
            "cagr": round(float(eq.iloc[-1] ** (1 / yrs) - 1), 4),
            "vol": round(vol, 3),
            "sharpe": round(float(r.mean() * 52 / vol), 2) if vol > 0 else None,
            "maxdd": round(float((eq / eq.cummax() - 1).min()), 3)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=None)
    args = parser.parse_args()
    root = resolve_project_root(args.project_root)
    out_dir = root / OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    weekly = build_weekly_panel(root)
    states = classify_states(weekly)

    members = pd.DataFrame(index=weekly.index)
    members["m_osc"] = (1.0 + weekly["osc"]).clip(0.0, 2.0)
    members["m_vix"] = (1.0 - 0.5 * weekly["vix_z"]).clip(0.0, 2.0)
    members["m_cot"] = (1.0 - 0.5 * weekly["am_z"]).clip(0.0, 2.0)
    members["m_narr"] = narrative_member(weekly, states)
    gov = governor(weekly["health"])

    e_dir = members.mean(axis=1)
    unanimous = members.min(axis=1) >= ACCEL_THRESHOLD
    e_dir_accel = e_dir * np.where(unanimous, ACCEL_FACTOR, 1.0)
    ensemble = (e_dir_accel * gov).clip(0.0, 3.0)
    ensemble_no_accel = (e_dir * gov).clip(0.0, 3.0)

    learned = learned_signs_member_panel(weekly)
    e_learned = (learned.mean(axis=1) * gov).clip(0.0, 3.0)

    # OOS window: after every walk-forward member has warmed up.
    oos = weekly.index[MIN_TRAIN_WEEKS:]
    books = {
        "SPY buy & hold": pd.Series(1.0, index=weekly.index),
        "Throttle 0-2x (incumbent)": (1.0 + weekly["osc"]).clip(0.0, 2.0),
        "Ensemble 0-3x (accel rule)": ensemble,
        "Ensemble 0-2x (no accel)": ensemble_no_accel,
        "Learned-signs ensemble (robustness)": e_learned,
        "Constant 2x": pd.Series(2.0, index=weekly.index),
        "Constant 3x": pd.Series(3.0, index=weekly.index),
    }
    member_books = {f"member {c}": members[c] for c in members.columns}

    rows = {}
    for name, E in {**books, **member_books}.items():
        rows[name] = perf(run_book(weekly, E).loc[oos])
    summary = pd.DataFrame(rows).T

    accel_weeks = int((unanimous & (weekly.index.isin(oos))).sum())
    accel_ret = run_book(weekly, ensemble).loc[oos][unanimous.loc[oos]]
    diag = {
        "oos_window": f"{oos[0]:%Y-%m-%d} -> {oos[-1]:%Y-%m-%d}",
        "weeks_oos": int(len(oos)),
        "accel_weeks": accel_weeks,
        "accel_weeks_share": round(accel_weeks / len(oos), 3),
        "accel_weeks_avg_ret_%": round(float(accel_ret.mean() * 100), 3) if accel_weeks else None,
        "avg_exposure_ensemble": round(float(ensemble.loc[oos].mean()), 2),
        "max_exposure_ensemble": round(float(ensemble.loc[oos].max()), 2),
        "share_weeks_above_1x": round(float((ensemble.loc[oos] > 1.0).mean()), 3),
        "share_weeks_above_2x": round(float((ensemble.loc[oos] > 2.0).mean()), 3),
    }

    summary.to_csv(out_dir / "summary.csv")
    exposures_out = pd.DataFrame({"ensemble": ensemble, "e_dir": e_dir, "governor": gov,
                                  "unanimous": unanimous, "state": states, **{c: members[c] for c in members}})
    exposures_out.to_csv(out_dir / "exposures.csv")
    (out_dir / "diagnostics.json").write_text(json.dumps(diag, indent=1))

    print(f"OOS {diag['oos_window']} ({diag['weeks_oos']} weeks)")
    print(summary.to_string())
    print("\ndiagnostics:", json.dumps(diag, indent=1))
    print(f"\ncurrent ensemble exposure: {float(ensemble.iloc[-1]):.2f}x "
          f"(members: {', '.join(f'{c}={members[c].iloc[-1]:.2f}' for c in members.columns)}, "
          f"governor {float(gov.iloc[-1]):.2f}, state {int(states.iloc[-1])})")


if __name__ == "__main__":
    main()
