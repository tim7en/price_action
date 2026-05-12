"""Backtest leveraged drawdown-deployment strategies versus buy-and-hold SPY.

Strategies tested
-----------------
1. ``BH``               : Buy-and-hold 100% SPY, no leverage.
2. ``Reserve_3x``       : Hold 60% SPY + 40% cash. On a -5% drawdown from the
                          trailing peak deploy the 40% cash at 3x SPY leverage.
                          De-lever the leveraged sleeve back to 1x once SPY
                          recovers to the prior peak.
3. ``Flip_3x``          : Hold 100% SPY. On a -5% drawdown sell SPY and re-enter
                          the entire equity at 3x SPY leverage. Drop back to 1x
                          once SPY recovers to the prior peak.

Sensitivity variants run the same playbook at 1.5x, 2x, 2.5x and 3x.

Realism layers
--------------
- Daily mark-to-market using SPY adjusted close.
- Borrow cost on the leveraged sleeve at ``BORROW_RATE`` (annualised, applied
  daily). Default 5%/yr - representative of recent broker margin rates.
- Margin call: if equity in the leveraged sleeve falls below
  ``MAINTENANCE_MARGIN`` (default 25%) of the position notional, the position
  is force-liquidated at that day's close (sleeve equity goes to zero, the
  remaining cash sleeve is preserved). After a margin call the strategy holds
  cash for the rest of that drawdown episode and re-arms when SPY makes a new
  all-time high.
- No taxes, no slippage, no commissions.

Outputs land in ``outputs/spy_drawdown_leverage_backtest/``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
SPY_PATH = PROJECT_ROOT / "cache" / "cache" / "SPY_daily.parquet"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "spy_drawdown_leverage_backtest"

DRAWDOWN_TRIGGER = -0.05
BORROW_RATE = 0.05
MAINTENANCE_MARGIN = 0.25
TRADING_DAYS = 252


def load_spy() -> pd.DataFrame:
    df = pd.read_parquet(SPY_PATH)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df = df[["date", "adj_c"]].rename(columns={"adj_c": "price"}).copy()
    df["ret"] = df["price"].pct_change().fillna(0.0)
    df["running_peak"] = df["price"].cummax()
    df["drawdown"] = df["price"] / df["running_peak"] - 1.0
    return df


@dataclass
class BacktestResult:
    label: str
    leverage: float
    equity: pd.Series
    margin_calls: int
    episodes_triggered: int
    final_equity: float
    cagr: float
    max_drawdown: float
    annualised_vol: float
    sharpe: float
    calmar: float
    blowup_episodes: list = field(default_factory=list)


def summarise(equity: pd.Series, label: str, leverage: float, episodes_triggered: int,
              margin_calls: int, blowups: list[dict]) -> BacktestResult:
    rets = equity.pct_change().fillna(0.0)
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    final = float(equity.iloc[-1])
    cagr = final ** (1.0 / years) - 1.0 if final > 0 and years > 0 else -1.0
    running_peak = equity.cummax()
    dd = (equity / running_peak - 1.0)
    max_dd = float(dd.min())
    vol = float(rets.std() * np.sqrt(TRADING_DAYS))
    sharpe = float(rets.mean() * TRADING_DAYS / vol) if vol > 0 else 0.0
    calmar = float(cagr / abs(max_dd)) if max_dd < 0 else float("nan")
    return BacktestResult(
        label=label,
        leverage=leverage,
        equity=equity,
        margin_calls=margin_calls,
        episodes_triggered=episodes_triggered,
        final_equity=final,
        cagr=cagr,
        max_drawdown=max_dd,
        annualised_vol=vol,
        sharpe=sharpe,
        calmar=calmar,
        blowup_episodes=blowups,
    )


def run_buy_and_hold(spy: pd.DataFrame) -> BacktestResult:
    equity = (1.0 + spy["ret"]).cumprod()
    equity.index = spy["date"].values
    return summarise(equity, "BH", 1.0, 0, 0, [])


def run_strategy(
    spy: pd.DataFrame,
    label: str,
    base_allocation: float,
    deploy_share: float,
    leverage: float,
    borrow_rate: float = BORROW_RATE,
    maint_margin: float = MAINTENANCE_MARGIN,
    trigger: float = DRAWDOWN_TRIGGER,
) -> BacktestResult:
    """Simulate one of the leveraged-deployment strategies.

    Parameters
    ----------
    base_allocation : float
        Share of equity always invested in unlevered SPY (e.g. 0.6 for the
        reserve strategy, 1.0 for the flip strategy before trigger).
    deploy_share : float
        Share of equity that gets mobilised at the drawdown trigger and run at
        the elevated leverage. For ``Reserve_3x`` this is 0.4 (the cash sleeve).
        For ``Flip_3x`` this is 1.0 (the whole portfolio swaps from 1x to ``leverage``).
    leverage : float
        Multiplier applied to the deployed sleeve while in drawdown mode.
    """
    dates = spy["date"].values
    prices = spy["price"].values
    rets = spy["ret"].values
    peaks = spy["running_peak"].values
    drawdowns = spy["drawdown"].values

    # State: 'normal' or 'in_drawdown'
    state = "normal"
    blown_this_episode = False
    base_units = 1.0  # SPY units (in equity terms) held in the unlevered sleeve
    sleeve_equity = 0.0  # equity inside the deployed/levered sleeve
    sleeve_notional = 0.0  # gross long $ exposure inside the sleeve
    cash = 0.0  # cash reserves (uninvested)
    daily_borrow = borrow_rate / TRADING_DAYS

    # Initial allocation: base_allocation in SPY, (1 - base_allocation) in cash
    initial_equity = 1.0
    base_units = base_allocation
    cash = 1.0 - base_allocation
    sleeve_equity = 0.0
    sleeve_notional = 0.0

    equity_series = np.empty(len(spy))
    margin_calls = 0
    episodes_triggered = 0
    blowups: list[dict] = []
    current_episode_peak = peaks[0]

    for i in range(len(spy)):
        r = rets[i] if i > 0 else 0.0
        # Apply daily PnL to existing positions
        base_units_value = base_units * (1.0 + r)
        if sleeve_notional > 0:
            sleeve_pnl = sleeve_notional * r
            sleeve_equity += sleeve_pnl
            borrow_amt = max(sleeve_notional - sleeve_equity, 0.0) * daily_borrow
            sleeve_equity -= borrow_amt
            # Update notional: notional drifts with price moves (no rebal intraday)
            sleeve_notional *= (1.0 + r)
            # Margin call check
            if sleeve_equity / sleeve_notional < maint_margin:
                # Liquidate sleeve at this day's close. Cash recovered = sleeve_equity (residual).
                cash += max(sleeve_equity, 0.0)
                margin_calls += 1
                blowups.append({
                    "date": pd.Timestamp(dates[i]).strftime("%Y-%m-%d"),
                    "drawdown_at_blowup": float(drawdowns[i]),
                })
                sleeve_equity = 0.0
                sleeve_notional = 0.0
                blown_this_episode = True

        base_units = base_units_value
        total_equity = base_units + sleeve_equity + cash
        equity_series[i] = total_equity

        # State transitions evaluated at end of day on current drawdown
        dd = drawdowns[i]
        if state == "normal":
            # New peak reached -> reset episode flag
            if peaks[i] > current_episode_peak + 1e-12:
                current_episode_peak = peaks[i]
                blown_this_episode = False
            # Trigger entry: drawdown crosses below trigger
            if dd <= trigger and not blown_this_episode:
                episodes_triggered += 1
                # Deploy: move ``deploy_share`` of TOTAL EQUITY into the levered sleeve.
                deploy_capital = deploy_share * total_equity
                # If deploy_share covers the base sleeve too (flip strategy),
                # liquidate base SPY units first into cash, then redeploy.
                if deploy_share >= base_allocation - 1e-9:
                    # Sell base SPY: cash += base_units (since base_units are
                    # measured in equity dollars after the daily mark).
                    cash += base_units
                    base_units = 0.0
                    deploy_capital = deploy_share * (cash if deploy_share >= 1.0 else total_equity)
                # Use up to ``deploy_capital`` from cash for sleeve equity.
                use_cash = min(cash, deploy_capital)
                cash -= use_cash
                sleeve_equity = use_cash
                sleeve_notional = sleeve_equity * leverage
                state = "in_drawdown"
        else:  # in_drawdown
            # Exit: SPY recovers to the prior peak (drawdown back to ~0).
            if prices[i] >= current_episode_peak * (1.0 - 1e-6):
                # De-lever sleeve back to 1x: sleeve_notional becomes sleeve_equity,
                # then merge sleeve back into base allocation.
                if sleeve_notional > 0:
                    # Settle leverage: cash needed to pay down borrow = sleeve_notional - sleeve_equity
                    # We assume the sleeve continues as 1x SPY exposure equal to sleeve_equity.
                    sleeve_notional = sleeve_equity  # 1x post-exit
                base_units += sleeve_equity
                sleeve_equity = 0.0
                sleeve_notional = 0.0
                # Rebalance back to target: base_allocation of equity in SPY, rest in cash.
                # (If Flip strategy, base_allocation = 1.0, so all cash goes to SPY.)
                total_after = base_units + cash
                target_base = base_allocation * total_after
                if target_base > base_units:
                    need = target_base - base_units
                    take = min(cash, need)
                    base_units += take
                    cash -= take
                else:
                    free = base_units - target_base
                    base_units -= free
                    cash += free
                state = "normal"
                current_episode_peak = peaks[i]

    equity_idx = pd.DatetimeIndex(pd.to_datetime(spy["date"].values))
    equity = pd.Series(equity_series, index=equity_idx)
    return summarise(equity, label, leverage, episodes_triggered, margin_calls, blowups)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    spy = load_spy()

    results: list[BacktestResult] = []
    results.append(run_buy_and_hold(spy))

    # Reserve strategy across leverage ladder
    for lev in [1.5, 2.0, 2.5, 3.0]:
        results.append(
            run_strategy(
                spy,
                label=f"Reserve_{lev:g}x",
                base_allocation=0.6,
                deploy_share=0.4,
                leverage=lev,
            )
        )

    # Flip strategy across leverage ladder (100% SPY -> all-in at leverage X)
    for lev in [1.5, 2.0, 2.5, 3.0]:
        results.append(
            run_strategy(
                spy,
                label=f"Flip_{lev:g}x",
                base_allocation=1.0,
                deploy_share=1.0,
                leverage=lev,
            )
        )

    # Build summary table
    rows = []
    for r in results:
        rows.append({
            "strategy": r.label,
            "leverage": r.leverage,
            "final_equity_per_$1": round(r.final_equity, 4),
            "cagr": round(r.cagr, 4),
            "max_drawdown": round(r.max_drawdown, 4),
            "ann_vol": round(r.annualised_vol, 4),
            "sharpe": round(r.sharpe, 3),
            "calmar": round(r.calmar, 3) if not np.isnan(r.calmar) else None,
            "episodes_triggered": r.episodes_triggered,
            "margin_calls": r.margin_calls,
            "blowup_dates": "; ".join(b["date"] for b in r.blowup_episodes),
        })
    summary = pd.DataFrame(rows)
    summary.to_csv(OUTPUT_DIR / "strategy_summary.csv", index=False)

    # Equity curves
    eq_df = pd.DataFrame({r.label: r.equity for r in results})
    eq_df.index.name = "date"
    eq_df.to_csv(OUTPUT_DIR / "equity_curves.csv")

    # Blowup detail JSON
    blowup_payload = {
        r.label: r.blowup_episodes for r in results if r.blowup_episodes
    }
    with open(OUTPUT_DIR / "blowups.json", "w", encoding="utf-8") as f:
        json.dump(blowup_payload, f, indent=2, default=str)

    # Plots
    try:
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(15.5, 5.5), dpi=120)
        plot_labels_left = ["BH", "Reserve_1.5x", "Reserve_2x", "Reserve_2.5x", "Reserve_3x"]
        plot_labels_right = ["BH", "Flip_1.5x", "Flip_2x", "Flip_2.5x", "Flip_3x"]
        for label in plot_labels_left:
            axes[0].plot(eq_df.index, eq_df[label], label=label, linewidth=1.4)
        axes[0].set_title("Reserve sleeve (60% SPY + 40% deployed at -5% DD)")
        axes[0].set_yscale("log")
        axes[0].set_ylabel("Equity (log, $1 start)")
        axes[0].legend(loc="upper left", fontsize=9)
        axes[0].grid(True, alpha=0.3)

        for label in plot_labels_right:
            axes[1].plot(eq_df.index, eq_df[label], label=label, linewidth=1.4)
        axes[1].set_title("Flip sleeve (100% SPY -> all-in at leverage on -5% DD)")
        axes[1].set_yscale("log")
        axes[1].legend(loc="upper left", fontsize=9)
        axes[1].grid(True, alpha=0.3)

        plt.tight_layout()
        plot_path = OUTPUT_DIR / "equity_curves.png"
        plt.savefig(plot_path)
        plt.close(fig)

        # Drawdown chart for BH vs Reserve_3x vs Flip_3x
        fig2, ax2 = plt.subplots(figsize=(13.0, 5.0), dpi=120)
        for label, color in [("BH", "#1f77b4"), ("Reserve_3x", "#2ca02c"), ("Flip_3x", "#d62728")]:
            series = eq_df[label]
            dd = series / series.cummax() - 1.0
            ax2.plot(dd.index, dd.values, label=label, linewidth=1.3, color=color)
        ax2.set_title("Drawdown comparison: BH vs Reserve_3x vs Flip_3x")
        ax2.set_ylabel("Drawdown")
        ax2.axhline(0.0, linewidth=0.8, color="black")
        ax2.legend(loc="lower right")
        ax2.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / "drawdowns.png")
        plt.close(fig2)
    except Exception as exc:  # plotting is best-effort
        print(f"plotting skipped: {exc}")

    # Print summary
    print("\n=== Strategy summary (1999-03-10 -> 2026-04-09, SPY adj-close) ===\n")
    print(summary.to_string(index=False))
    print("\nOutputs:")
    print(f"  {OUTPUT_DIR / 'strategy_summary.csv'}")
    print(f"  {OUTPUT_DIR / 'equity_curves.csv'}")
    print(f"  {OUTPUT_DIR / 'blowups.json'}")
    print(f"  {OUTPUT_DIR / 'equity_curves.png'}")
    print(f"  {OUTPUT_DIR / 'drawdowns.png'}")


if __name__ == "__main__":
    main()
