# SPY Drawdown Cycle Ladder — buy panic, sell recovered euphoria

A mechanical rule set for deploying a **bounded reserve** into deep SPY
drawdowns and recycling it out at momentum extremes after the recovery. It
sits *beside* the monthly DCA (which it never touches) and *under* the
de-risk governor (which governs leverage, not this).

Backtested 2000→2026 on the exact rules below (see §5): one reserve dollar
grew **8.45x (8.4% CAGR, −44% maxDD)** vs 8.62x (8.5%, −55%) for leaving it
permanently in SPY and 1.82x (2.3%) for leaving it in cash. The ladder
matched buy-and-hold to within rounding while holding cash optionality
2000–01 and 2021–26 — and every deep-overbought exit month in 23 years of
data (2003–04, 2010, 2020–21) sat in the recovery directly after a
ladder-triggering crash, so the entry and exit naturally pair.

---

## 1 · Structure

| Sleeve | What it is | These rules apply? |
|---|---|---|
| Core | Everything accumulated by monthly DCA | **Never sold, never paused** |
| Reserve | Fixed 15% of NAV in yield-bearing stables/T-bill-like | **The only money the ladder spends** |
| Grid bot / leverage | Governed by the health ladder | Untouched by these rules |

The reserve is replenished **only** from ladder exits (plus optionally a
slice of new savings while below target). Never topped up by selling core,
never leveraged.

## 2 · Entries — price-mechanical, no macro gate

Trigger on **SPY all-time-high drawdown, daily closes**. Signal at the
close, execute at the next close. Check weekly.

| Tranche | Trigger | Deploys (of reserve) |
|---|---|---|
| 1 (probe) | −30% | 10% |
| 2 (main) | −40% | 50% |
| 3 (tail) | −50% | 40% |

- Each tranche fires **once per episode**. An episode ends when SPY closes
  at a **new all-time high** — after that, a fresh crash re-arms all
  tranches (this re-arming is what let the ladder buy 2008 after 2002, and
  it is worth ≈ +0.9x on the terminal multiple in the backtest).
- No macro filter on buys: the drawdown research showed the best forward
  returns came from buying *during* stress, and every entry-side macro gate
  tested subtracted value.
- No stop-losses on tranches. The capped reserve **is** the stop.
- Calibration: since 1999 SPY crossed −30% in three bear markets, −50% only
  in 2008–09, and never −60% (worst: −55%). A deeper tranche would never
  fill; these three fully deploy roughly once a decade.

## 3 · Exit — momentum + macro + recovery gated; sells ladder inventory only

Sell ladder tranches when **all four** hold at a month-end check:

1. **Momentum oscillator ≥ +0.75** (deep overbought — the Wilshire monthly
   oscillator, `outputs/momentum_oscillator/`).
2. **Market health ≥ 55** (the weekly sheet's number — "favorable macro").
3. **Inventory in profit** (price above blended ladder cost).
4. **The crash has retraced: ATH drawdown better than −15%** ("we went back
   above"). This gate is load-bearing: without it the ladder exits into the
   first euphoria bounce (2004, 2010) and forfeits ~2% CAGR; with it, exits
   only fire near new highs (Jan–Feb 2021 in the backtest).

Execute in **two halves** across consecutive qualifying month-ends.
Proceeds refill the reserve to its 15% target; the surplus flows into core.

**Expectations:** the exit fires in ~5% of months with multi-year silences.
Tranches can sit underwater for years (2002 cost ~55, exit 2021 at ~342 —
a 6x, but two decades). If that holding period is intolerable, shrink the
reserve; don't loosen the gates.

## 4 · Priority order

1. Playbook hard risk rules (kill switch, no leverage, venue caps) outrank all.
2. The health governor manages *leveraged* exposure; it does **not** block
   ladder buys — the ladder exists to buy exactly when health is bad.
3. DCA continues in all states; the ladder is additive.

## 5 · Backtest (2000-01 → 2026-07, ex-dividend closes, rf on idle cash)

| Variant | Growth | CAGR | maxDD | Trades |
|---|---|---|---|---|
| **These rules (ATH-reset + retrace gate)** | **8.45x** | **8.4%** | **−44%** | 7 |
| No episode re-arm (single 20y hold) | 7.60x | 8.0% | −38% | 5 |
| No retrace gate (exits 2004/2010 bounces) | 5.12x | 6.4% | −21% | 10 |
| Reserve left in SPY buy-and-hold | 8.62x | 8.5% | −55% | 0 |
| Reserve left in cash (rf) | 1.82x | 2.3% | 0% | 0 |

Trade log for the chosen rules: BUY −31% Sep-2001 @66, BUY −41% Jul-2002
@55, BUY −32% Oct-2008 @72, BUY −41% Oct-2008 @64, BUY −51% Nov-2008 @58
(residual cash), SELL Jan/Feb-2021 @342/349 (osc 0.81/0.77, health 77/71).

Honest read: the ladder is **not alpha** — it ties buy-and-hold over the
sample. Its value is (a) turning reserve cash from 1.8x into 8.5x, (b) a
shallower worst drawdown, (c) a pre-committed plan for crashes that would
otherwise be panic. The no-retrace variant buys a much softer ride (−21%
maxDD) for ~2% CAGR — a legitimate preference, documented so future-you
doesn't "discover" it in-sample.

## 6 · Depth-gated leverage (2026-07 gradient study, outputs/drawdown_gradient/)

The forward-return gradient by ATH-drawdown depth (SPY daily, 1998–2026) is
**not monotone**: the −10%…−30% zone is the falling-knife trap (fwd 12m
3.7–8.4%, Sharpe 0.23–0.45 — *worse* than buying at all-time highs), while
−30…−40% pays +14.4% (93% hit, Sharpe 1.41) and −40%+ pays +33.8% (100% hit
across its ~2 episodes, worst decile still +21%).

The survival column decides where leverage may live. After entering at a
−5…−20% dip, the further fall exceeded −33% (the 2x liquidation line at 25%
maintenance) in **13–25% of cases** (p90 further drawdown −43…−48%). After
entering below −30%, the further fall **never** exceeded −23% in the sample.

Amendment, consistent with the user's mandate (max 2x, equal-margin top-up
reserve available):

- Above −30% drawdown: **no leverage, ever** — this includes the tempting
  −10…−20% "big dip" zone, which is statistically the worst place to add.
- T1 (−30%) and T2 (−40%): cash tranches at 1x, as specified.
- T3 (−50%): may deploy at up to **2x**, with the equal-margin top-up
  reserved for it (topping up de-levers to ~1x on cost — no liquidation
  path). Historically no entry below −30% ever faced a further −33% fall;
  this rule is calibrated to that, on ~2–3 independent episodes — treat it
  as a survivable bet, not a certainty.
- Sector dips are excluded from the ladder entirely: deep-drawdown buying
  paid +34…+51% for cyclicals but **+1.5% for XLK after 2000 and +8% for
  XLF after 2008** — the crash's epicenter sector is the value trap, and
  you cannot know the epicenter ex-ante. The index rotates leadership;
  single sectors don't have to recover. Ladder the index only.

## 7 · Frozen

One calendar-scheduled review per year, written reasons for any change.
Log every action: date, drawdown at fire, price, tranche, blended cost,
oscillator, health.

## Caveats (printed on purpose)

- **n ≈ 2.5 cycles.** The variant ranking above rests on a handful of
  decisions; treat differences under ~1% CAGR as noise. The robust claims
  are only: ladder ≫ cash, ladder ≈ buy-and-hold, retrace gate changes the
  *character* (few huge harvests vs many small ones).
- Dividends are excluded on both sides; including them favors buy-and-hold
  (it is always invested; the ladder ~75% of the time). Expect the true gap
  to be modestly wider than the table shows.
- Oscillator ≥0.75, health ≥55, and −15% retrace are in-sample calibrations;
  approximate thresholds, not laws.
- The July oscillator value is partial-month until month-end; never act
  intramonth.
- Current state (2026-07): SPY is −1% from ATH — the ladder is **dormant**.
  The only live task is building the 15% reserve.
