"""Weekly action sheet: macro regime + market health + trend signals.

Closes the loop from research to routine.  Pulls (or reads cached) daily
prices for the 11 SPDR sector ETFs, SPY, and BTC/ETH/SOL from Binance, then
combines three validated layers into one printed decision sheet:

1.  **Macro regime** -- the Dalio-style GMM latent regime from
    ``regime_analysis`` (fit on all history *up to today*, which is causal for
    today's label) plus its Markov forecast of where the regime goes next.

2.  **Market health (0-100)** -- the causal score from the sector trend study
    (breadth + NFCI + HY spreads + VIX + curve + momentum), rebuilt here on
    live ETF breadth, mapped to the study's leverage ladder and the playbook's
    crypto-sleeve ladder.

3.  **Per-asset trend states** -- true 50d/200d golden/death cross states with
    a 2% hysteresis band (the playbook's whipsaw buffer), flagging fresh
    crosses as OPEN/CLOSE actions, annotated with each sector's historical
    whipsaw rate from the (bias-fixed) trend study.

Honest limits, printed on the sheet itself: the health/ladder thresholds are
in-sample calibrations from the equity study (edge is an upper bound), the
regime label is only as fresh as the FRED store, and nothing here is validated
on crypto yet -- crypto rows use the equity-derived logic.

Run with::

    python advise.py                # fetch fresh prices, print + save sheet
    python advise.py --offline      # cached prices only (no network)
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .data import resolve_project_root
from .regime_analysis import fit_regime_model, load_macro_panel
from .sector_trend_study import _roll_z, leverage_schedule

PRICE_CACHE = Path("cache") / "advise"
OUTPUT_DIR = Path("outputs") / "advice"
STUDY_CROSS_STATS = Path("outputs") / "sector_trend_report" / "cross_stats_by_sector.csv"

SECTOR_ETFS = {
    "Technology": "XLK",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Communication Svcs": "XLC",
    "Real Estate": "XLRE",
    "Materials": "XLB",
    "Energy": "XLE",
    "Utilities": "XLU",
}
BROAD_ETF = "SPY"

# Playbook caps within the crypto sleeve (docs/binance_trend_playbook.md).
CRYPTO_ASSETS = {"BTCUSDT": 0.50, "ETHUSDT": 0.30, "SOLUSDT": 0.15}
BINANCE_HOSTS = ["https://api.binance.com", "https://api.binance.us"]

FAST_D, SLOW_D = 50, 200
HYSTERESIS_BAND = 0.02   # playbook: MA-spread must clear +/-2% to flip state
FRESH_BARS = 5           # a cross within the last 5 trading days is actionable

# Playbook crypto-sleeve ladder: health -> share of the risk sleeve deployed.
CRYPTO_LADDER = [(70, 1.0), (55, 1.0), (40, 0.6), (25, 0.25), (-1, 0.10)]


# --------------------------------------------------------------------------- #
# 1. Price data (Yahoo for ETFs, Binance for crypto), cached to CSV.
# --------------------------------------------------------------------------- #
def _cache_path(root: Path, symbol: str) -> Path:
    return root / PRICE_CACHE / f"{symbol}_daily.csv"


def _read_cache(root: Path, symbol: str) -> pd.Series | None:
    path = _cache_path(root, symbol)
    if not path.exists():
        return None
    s = pd.read_csv(path, parse_dates=["date"]).set_index("date")["close"]
    return s.sort_index()


def _write_cache(root: Path, symbol: str, s: pd.Series) -> None:
    path = _cache_path(root, symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    s.rename("close").rename_axis("date").to_csv(path)


def _fetch_etf(symbol: str) -> pd.Series:
    from .update_data import fetch_yahoo_chart
    end = (pd.Timestamp.utcnow() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    frame = fetch_yahoo_chart(symbol, "1998-01-01", end)
    return pd.Series(frame["adj_close"].to_numpy(),
                     index=pd.DatetimeIndex(frame["date"]), name="close")


def _fetch_binance(symbol: str) -> pd.Series:
    last_error: Exception | None = None
    for host in BINANCE_HOSTS:
        url = f"{host}/api/v3/klines?symbol={symbol}&interval=1d&limit=1000"
        try:
            out = subprocess.run(["curl", "-fsSL", "--max-time", "30", url],
                                 check=True, capture_output=True)
            rows = json.loads(out.stdout)
            closes = {pd.to_datetime(int(r[0]), unit="ms").normalize(): float(r[4])
                      for r in rows}
            if len(closes) >= SLOW_D + 20:
                return pd.Series(closes).sort_index()
            raise RuntimeError(f"only {len(closes)} bars from {host}")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError(f"Binance fetch failed for {symbol}: {last_error}")


def load_prices(root: Path, offline: bool) -> tuple[pd.DataFrame, list[str]]:
    """Daily closes for SPY + sector ETFs + crypto.  Returns (prices, warnings)."""
    warnings: list[str] = []
    series: dict[str, pd.Series] = {}
    etf_symbols = [BROAD_ETF, *SECTOR_ETFS.values()]
    for sym in etf_symbols + list(CRYPTO_ASSETS):
        cached = _read_cache(root, sym)
        fresh_enough = cached is not None and (
            pd.Timestamp.now() - cached.index[-1] <= pd.Timedelta(days=4))
        if offline or fresh_enough:
            if cached is None:
                warnings.append(f"{sym}: no cache and offline -- skipped")
                continue
            series[sym] = cached
            continue
        try:
            s = _fetch_etf(sym) if sym in etf_symbols else _fetch_binance(sym)
            _write_cache(root, sym, s)
            series[sym] = s
        except Exception as exc:  # noqa: BLE001
            if cached is not None:
                warnings.append(f"{sym}: fetch failed ({exc}); using cache "
                                f"through {cached.index[-1]:%Y-%m-%d}")
                series[sym] = cached
            else:
                warnings.append(f"{sym}: fetch failed and no cache ({exc})")
    if not series:
        raise RuntimeError("No price data available (all fetches failed, no cache).")
    return pd.DataFrame(series).sort_index(), warnings


# --------------------------------------------------------------------------- #
# 2. Trend state with hysteresis (the playbook's whipsaw buffer).
# --------------------------------------------------------------------------- #
@dataclass
class TrendState:
    state: str               # "UP" / "DOWN"
    since: pd.Timestamp      # date of the last state flip
    bars_since: int
    fresh: bool              # flipped within the last FRESH_BARS bars
    dist_slow_pct: float     # price vs 200d MA
    asof: pd.Timestamp


def trend_state(px: pd.Series, band: float = HYSTERESIS_BAND) -> TrendState | None:
    px = px.dropna()
    if len(px) < SLOW_D + 10:
        return None
    ma_f = px.rolling(FAST_D, min_periods=FAST_D).mean()
    ma_s = px.rolling(SLOW_D, min_periods=SLOW_D).mean()
    spread = ((ma_f - ma_s) / ma_s).dropna()

    cur = 0.0
    flip_dt = spread.index[0]
    states = pd.Series(0.0, index=spread.index)
    for dt, sp in spread.items():
        if cur == 0.0:
            cur, flip_dt = (1.0 if sp > 0 else -1.0), dt
        elif cur < 0 and sp > band:
            cur, flip_dt = 1.0, dt
        elif cur > 0 and sp < -band:
            cur, flip_dt = -1.0, dt
        states[dt] = cur

    bars_since = int((spread.index > flip_dt).sum())
    return TrendState(
        state="UP" if cur > 0 else "DOWN",
        since=flip_dt,
        bars_since=bars_since,
        fresh=bars_since < FRESH_BARS,
        dist_slow_pct=float(px.iloc[-1] / ma_s.iloc[-1] - 1.0) * 100.0,
        asof=px.index[-1],
    )


def action_for(ts: TrendState) -> str:
    if ts.state == "UP":
        return "OPEN / ADD (fresh golden cross)" if ts.fresh else "HOLD LONG"
    return "CLOSE (fresh death cross)" if ts.fresh else "STAY OUT"


# --------------------------------------------------------------------------- #
# 3. Live market-health score (ETF breadth + macro), same recipe as the study.
# --------------------------------------------------------------------------- #
def compute_health(macro: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    etfs = [v for v in SECTOR_ETFS.values() if v in prices.columns]
    ma_s = prices[etfs].rolling(SLOW_D, min_periods=SLOW_D).mean()
    above = (prices[etfs] > ma_s).astype(float).where(ma_s.notna())
    breadth = above.resample("ME").last().mean(axis=1).astype(float)

    idx = breadth.dropna().index
    m = macro.reindex(idx).ffill(limit=2)
    spy_m = prices[BROAD_ETF].resample("ME").last().reindex(idx)
    mom = spy_m / spy_m.shift(12) - 1.0

    parts = pd.DataFrame(index=idx)
    parts["breadth"] = (breadth.reindex(idx) - 0.5) * 2.0
    parts["nfci"] = -_roll_z(m["nfci"])
    parts["hy"] = -_roll_z(m["hy_spread"])
    parts["vix"] = -_roll_z(m["vix"])
    parts["curve"] = _roll_z(m["t10y3m"])
    parts["momentum"] = _roll_z(mom)

    weights = {"breadth": 1.1, "nfci": 0.8, "hy": 0.8, "vix": 0.6,
               "curve": 0.3, "momentum": 0.6}
    raw = sum(parts[k] * w for k, w in weights.items()).astype(float)
    parts["health"] = 100.0 / (1.0 + np.exp(-raw / 2.0))
    parts["breadth_frac"] = breadth.reindex(idx)
    return parts


def crypto_sleeve_exposure(health: float) -> float:
    for floor, expo in CRYPTO_LADDER:
        if health >= floor:
            return expo
    return CRYPTO_LADDER[-1][1]


# --------------------------------------------------------------------------- #
# 4. Assemble the action sheet.
# --------------------------------------------------------------------------- #
def _load_whipsaw(root: Path) -> pd.Series:
    path = root / STUDY_CROSS_STATS
    if not path.exists():
        return pd.Series(dtype="float64")
    df = pd.read_csv(path, index_col=0)
    return df["whipsaw_rate_%"]


def build_sheet(root: Path, offline: bool = False) -> str:
    prices, warnings = load_prices(root, offline)
    macro = load_macro_panel(root)
    macro_asof = macro.dropna(how="all").index[-1]
    stale_days = (pd.Timestamp.now() - macro_asof).days
    if stale_days > 45:
        warnings.append(
            f"macro/FRED store is {stale_days} days old (through {macro_asof:%Y-%m-%d}) "
            f"-- health & regime are as of then; run refresh_data.py")

    # Regime (fit on history up to now -- causal for the *current* label).
    wilshire = macro["equity_index"]
    fwd12 = wilshire.shift(-12) / wilshire - 1.0
    try:
        model = fit_regime_model(macro, fwd12)
    except Exception as exc:  # noqa: BLE001
        model = None
        warnings.append(f"regime model unavailable: {exc}")

    health_df = compute_health(macro, prices)
    h_series = health_df["health"].dropna()
    health = float(h_series.iloc[-1])
    health_asof = h_series.index[-1]
    equity_ladder = float(leverage_schedule(pd.Series([health])).iloc[0])
    crypto_expo = crypto_sleeve_exposure(health)
    whipsaw = _load_whipsaw(root)

    lines: list[str] = []
    add = lines.append
    add(f"# Weekly action sheet — {date.today():%Y-%m-%d}")
    add("")
    if warnings:
        add("## ⚠ Data warnings")
        for w in warnings:
            add(f"- {w}")
        add("")

    add("## Macro regime (Dalio-style GMM)")
    if model is not None:
        add(f"- Current regime: **{model.current}** (as of {macro_asof:%Y-%m})")
        probs = (model.forecast * 100).round(0)
        top = probs["3m"].sort_values(ascending=False).head(3)
        add("- 3-month regime odds: " +
            ", ".join(f"{name} {p:.0f}%" for name, p in top.items()))
    add("")

    add("## Market health & sizing")
    add(f"- Health score: **{health:.0f} / 100** (as of {health_asof:%Y-%m}, "
        f"breadth {health_df['breadth_frac'].dropna().iloc[-1]*100:.0f}% of sectors in uptrend)")
    comp = health_df.dropna().iloc[-1]
    add("- Components (z, + is supportive): " +
        ", ".join(f"{k} {comp[k]:+.1f}" for k in
                  ["breadth", "nfci", "hy", "vix", "curve", "momentum"]))
    add(f"- Equity-study ladder ⇒ **{equity_ladder:g}× broad-market exposure** "
        f"(3× ≥75 · 2× ≥60 · 1× ≥45 · ½× ≥30 · hedge <30)")
    add(f"- Playbook crypto sleeve ⇒ **{crypto_expo*100:.0f}% of the risk sleeve deployed**")
    add("")

    add("## Sector trend signals (50d/200d with 2% band)")
    add("")
    add("| Sector | ETF | State | Since | Px vs 200d | Study whipsaw | Action |")
    add("|---|---|---|---|---|---|---|")
    up_sectors: list[str] = []
    for sector, etf in SECTOR_ETFS.items():
        if etf not in prices.columns:
            continue
        ts = trend_state(prices[etf])
        if ts is None:
            continue
        if ts.state == "UP":
            up_sectors.append(etf)
        wr = whipsaw.get(sector)
        wr_txt = f"{wr:.0f}% fakes" if pd.notna(wr) else "–"
        add(f"| {sector} | {etf} | {ts.state} | {ts.since:%Y-%m-%d} "
            f"| {ts.dist_slow_pct:+.1f}% | {wr_txt} | **{action_for(ts)}** |")
    spy_ts = trend_state(prices[BROAD_ETF]) if BROAD_ETF in prices.columns else None
    if spy_ts is not None:
        add(f"| Broad market | {BROAD_ETF} | {spy_ts.state} | {spy_ts.since:%Y-%m-%d} "
            f"| {spy_ts.dist_slow_pct:+.1f}% | – | **{action_for(spy_ts)}** |")
    add("")
    if up_sectors:
        w_each = equity_ladder / len(up_sectors)
        add(f"- Equity sleeve template: {len(up_sectors)} sectors in uptrend → "
            f"equal-weight ≈ **{w_each*100:.0f}% × ladder each** "
            f"({', '.join(up_sectors)}); sizes scale with the {equity_ladder:g}× ladder row.")
    add("")

    add("## Crypto trend signals (playbook rules — untested on crypto, sized accordingly)")
    add("")
    add("| Asset | State | Since | Px vs 200d | Sleeve cap | Action |")
    add("|---|---|---|---|---|---|")
    crypto_up = []
    for sym, cap in CRYPTO_ASSETS.items():
        if sym not in prices.columns:
            add(f"| {sym} | n/a | – | – | {cap*100:.0f}% | no data |")
            continue
        ts = trend_state(prices[sym])
        if ts is None:
            continue
        if ts.state == "UP":
            crypto_up.append(sym)
        add(f"| {sym.replace('USDT','')} | {ts.state} | {ts.since:%Y-%m-%d} "
            f"| {ts.dist_slow_pct:+.1f}% | {cap*100:.0f}% | **{action_for(ts)}** |")
    add("")
    add(f"- Crypto sleeve: deploy **{crypto_expo*100:.0f}%** of the sleeve across "
        f"UP assets (per-asset caps above), remainder to stables yield / PAXG.")
    add("")

    add("## Caveats (printed on purpose)")
    add("- Ladder thresholds & health weights are in-sample calibrations from the "
        "equity study (honest edge over 1×: ~+1.4% CAGR, −12pp maxDD — an upper bound).")
    add("- Trend/ladder logic is validated on equities only; crypto rows are an "
        "extrapolation. 5× anything failed the backtest permanently (−100%).")
    add("- Regime & health freshness is bounded by the FRED store (see warnings).")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true",
                        help="Use cached prices only (no network).")
    parser.add_argument("--project-root", default=None)
    args = parser.parse_args()

    root = resolve_project_root(args.project_root)
    sheet = build_sheet(root, offline=args.offline)

    out_dir = root / OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"advice_{date.today():%Y-%m-%d}.md"
    out_path.write_text(sheet + "\n", encoding="utf-8")
    print(sheet)
    print(f"\n[saved to {out_path}]")


if __name__ == "__main__":
    main()
