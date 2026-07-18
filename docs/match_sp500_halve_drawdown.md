# Match the S&P, halve the drawdown — the rule set

Everything this research cycle converged on one boring, robust conclusion:
you do not beat the S&P by predicting it. You match its return and cut its
pain in half by **staying invested in an uptrend and stepping aside in a
downtrend** — nothing more exotic survived honest, leakage-free testing.

All numbers below are monthly, total return (dividends reinvested), 2000–2026,
one-month execution lag, 10 bps per switch, idle cash earning the 2-year rate.

---

## The core engine (this alone hits the goal)

**Rule 1 — Trend switch.** Hold **SPY** while its price is above its
**10-month moving average** (≈ the 200-day). The month it *closes* below,
move the sleeve to **cash / T-bills** (a money-market or short-Treasury fund).
Move back when it closes back above. Check **once a month**, act at the next
month's open.

| | CAGR | Sharpe | Max drawdown | Worst year | $1 became |
|---|---|---|---|---|---|
| SPY buy & hold | 8.4% | 0.61 | **−51%** | −37% | $8.5 |
| **SPY + 10-month trend** | **8.3%** | **0.87** | **−21%** | **−19%** | $8.3 |

That is the whole headline: **−0.1% of return, −30 points of drawdown, worst
year halved.** It works because the market's worst falls are slow grinds
(2000–02, 2008) that spend months below the 10-month line — the rule is out
before the bulk of the damage. It gives back a little in fast V-shaped dips
(2020, 2018) where it sells low and rebuys higher; that whipsaw is the premium
you pay, and it is small.

**Rule 2 — DCA never stops.** Your ~$100/month contributions keep buying SPY
on schedule **regardless** of the trend switch. The switch governs the
*existing* sleeve; contributions are the compounding engine and the data said
timing entries adds nothing. Buy in every state.

---

## Optional: even smoother (slightly less return)

**Rule 3 — Health governor.** When the market-health score (weekly sheet) is
40–55, hold the trend sleeve at half size; below 40, quarter size; ≥ 55, full.
Layered on Rule 1:

| SPY + trend + health governor | CAGR 7.8% · Sharpe **0.94** · maxDD **−15%** · worst year −10% |

Use this only if a −21% drawdown still feels like too much — it buys a −15%
worst case for ~0.5% of annual return. The governor **only de-risks**; it never
adds exposure (lever-up timing failed the walk-forward test three times).

**Rule 4 — Equal-weight for a touch more return.** Swap SPY for **RSP**
(equal-weight S&P) as the core. De-concentrating from mega-cap tech added
~+0.7% CAGR historically at similar risk. One ticker, no extra work. The trend
switch (Rule 1) applies to it identically.

---

## The drawdown reserve (buys the crashes the trend rule sat out)

**Rule 5 — The ladder.** Hold **15% of the portfolio** in yield-bearing cash
as a permanent reserve. Deploy it into **SPY** on all-time-high drawdowns:
10% of the reserve at −30%, 50% at −40%, 40% at −50%. Sell those tranches back
only after price recovers to within −15% of the high with momentum
deep-overbought. Index only; **no leverage above −30%**; the reserve is the
only money this rule spends. (Full spec: `drawdown_cycle_rules.md`.) The trend
rule gets you *out*; the ladder gets you *back in at the bottom* — they are the
two halves of one cycle.

---

## If you want to BEAT the S&P, not match it (optional, higher risk)

**Rule 6 — Modest structural leverage.** Lever the trend sleeve to **1.5×**,
never more, via a daily-reset instrument (never fixed margin). This beat the
market (~+0.4% CAGR over buy & hold) while keeping drawdown *below* market
(−48% vs −60%). **2× spends the entire edge** — it takes drawdown to market
level and Sharpe *below* buy & hold. 1.5× is the ceiling; pair it with Rule 3
so the governor pulls it down in stress. Leverage converts your drawdown
cushion into return dollar-for-dollar — spend half the cushion, keep half.

---

## Hard rules (non-negotiable — the whole cycle proved each one)

1. **No shorts** except a health-floor hedge (health < 25, ≤ 3× isolated). Shorts
   subtracted in every test; "short on bad news" *lost money* (−0.65×).
2. **No leverage above 1.5×, ever, and never on fixed margin.** 3× margin blew
   up six times since 2000.
3. **Index only for tactical sleeves and the ladder.** Single sectors are
   −80% value traps (XLK 2000, XLF 2008); the index rotates leadership, sectors
   don't have to recover.
4. **Don't stack correlated filters.** Momentum + trend + VWAP + volume + health
   all measure "is the trend strong?" — stacking them cut return 2.4% and added
   only cash drag. One trend signal is enough. Sector rotation and cross-timing
   added ≈ 0.1% (noise) and are not worth the cost or tax.
5. **Monthly cadence, not daily.** The trend rule trades ~once a year. Day
   trading and news timing are the highest-cost, lowest-edge games in the data.
6. **Keep the trading/grid account ring-fenced** from this core.

---

## The weekly/monthly routine (~10 minutes)

- **Monthly**: is SPY (or RSP) above its 10-month MA? In or out. Make your DCA buy.
- **Weekly (optional)**: glance at the action sheet — health score (governor row),
  SPY drawdown (ladder triggers), the narrative state. Act only if a threshold crossed.
- **Log every switch** with the reason. The log is what keeps you mechanical when
  it counts.

---

## Caveats (printed on purpose)

- Backtests are daily/monthly, total-return, and assume you *follow the rule
  through the whipsaws* — the 2020 sell-low-rebuy-high is in the −0.1% figure,
  and it is psychologically the hardest month to obey. Obeying it is the strategy.
- ~2.5 market cycles of data; treat sub-1% CAGR differences as noise. The robust,
  replicated claims are only: **trend overlay ≈ market return at half drawdown**,
  and **de-risk beats de-concentrate beats pick-winners beats time-entries.**
- Price-only-vs-total-return, taxes on switches (a switch in a taxable account is
  a taxable event — the ~yearly frequency keeps this small but not zero), and the
  health series' currency all bound precision. None change the conclusion.
- This matches the market; it does not beat it without leverage, and leverage
  brings the drawdown back. That trade — same return, half the pain — is the
  product. It is a good product.
