# Sector Cross Book — trend-gated sector sleeve (and why 3x margin is out)

The user-proposed system tested 1999→2026 on cached SPDR data: per-sector
50d/200d golden-cross entries (2% hysteresis band), death-cross exits,
fixed weights XLK 30 / XLF 30 / XLE 10 / XLY 10 / XLP 10 / XLI 10
("defence" proxied by XLI — dedicated ITA data can be added), idle weight
earns rf, 10bps turnover cost, borrow at rf+150bps.

## Backtest (price-only closes, idle cash at rf)

| Book | Growth | CAGR | maxDD | Sharpe | Worst 63d |
|---|---|---|---|---|---|
| SPY buy & hold | 10.1x | 8.8% | −55% | 0.53 | −41% |
| Cross book 1x | 7.9x | 7.8% | **−33%** | **0.65** | −29% |
| Cross book 2x (daily-rebal) | 31.1x | 13.3% | −58% | 0.62 | −53% |
| Cross book 3x (daily-rebal) | 73.9x | 16.9% | −75% | 0.60 | −71% |
| Cross book 3x + governor | 45.5x | 14.9% | −62% | 0.60 | −37% |
| Turtle 55d-high entries, 1x | 6.5x | 7.0% | −33% | – | – |

## The verdict on 3x — read before dreaming about 74x

1. **The 74x is unimplementable.** It assumes daily-rebalanced leverage with
   no margin calls possible. With real margin, the book spent **18% of all
   days (1,264) below −33% equity drawdown** — inside the fixed-margin
   liquidation zone. The repo's SPY margin test margin-called 3x **six
   times** since 2000 (2000, 2008, 2018, 2020, 2022, 2025-04), each at
   index falls of only −14% to −19%. Death-cross exits confirm far too late
   to save a margined book.
2. **The edge is not timing.** The walk-forward regime test found *negative*
   IC for lever-up timing. What the 2x/3x rows show is constant beta
   amplification of a trend-filtered book through a 26-year sample whose
   two big bears (2000-02, 2008-09) were slow enough for the 50/200 to
   exit. A fast crash (2020 shape, −34% in a month) at 3x margin is −100%
   before the death cross prints.
3. **Allocation hindsight.** 30% XLK through two tech supercycles is a
   backward-looking pick; the leveraged rows lean on it heavily.
4. Even the idealized 3x drew down −75% — which breaches the portfolio kill
   switch (−20%) almost immediately. A rule set that violates its own risk
   rules on day one is not a rule set.

## What survives (the adopted rules)

- **The 1x cross book is genuinely good**: Sharpe 0.65 vs 0.53, max
  drawdown −33% vs −55%, cost ≈1% CAGR vs buy-and-hold. This is the repo's
  core trend finding, again.
- **Entries: golden cross (2% band), weekly check, execute next session.**
  Turtle 55d-breakout entries underperformed with identical exits (7.0% vs
  7.8% CAGR — earlier entries eat more whipsaws). Turtle's real content was
  N-based sizing and stops, not the entry; that idea lives on in the
  vol-scaling overlay of the playbook, not here.
- **Exits: death cross (2% band).** No profit targets, no discretion.
- **Weights: as chosen** (XLK 30 / XLF 30 / XLE 10 / XLY 10 / XLP 10 /
  XLI 10) — with eyes open that 60% in two sectors is a concentrated bet
  the backtest cannot bless (it can only fail to reject it). A sector whose
  state is DOWN parks its weight in yield-bearing cash.
- **Leverage: none on margin, ever.** If aggressiveness is wanted, the
  ceiling is **2x via a daily-reset instrument only** (no liquidation
  mechanics), run as a satellite capped at ≤20% of NAV, **with the health
  governor** (H<55 → half, H<40 → quarter) — the governor added no return
  (consistent with the negative timing IC) but cut the worst 63-day stretch
  from −53% to roughly −37%, which is its de-risk-only job. Accept −58%
  book drawdowns as the price or don't run it.
- **Dalio regime: context only.** The sector-Dalio model's honest holdout
  edge (top-3 excess ≈ +1.8%/6m, AUC 0.54) does not support gating entries
  or sizing by quadrant. The regime label stays on the weekly sheet as
  narrative, not as a rule input.

## Current states (2026-07 sheet)

XLK UP · XLF **DOWN** · XLE UP · XLY **DOWN** · XLP UP · XLI UP → the book
would start **60% deployed** (XLK 30 + XLE/XLP/XLI 10 each), with the XLF 30
and XLY 10 sleeves in cash until their golden crosses.

## Caveats (printed on purpose)

- Price-only closes; dividends favor buy-and-hold slightly (it is always
  invested). n ≈ 2.5 cycles; whipsaw rates 41–52% on these sectors.
- The weekly sheet already prints every input this book needs (states,
  since-dates, health); no new tooling required.
- Frozen: one calendar-scheduled review per year, written reasons.
