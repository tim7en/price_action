# Binance Trend & Regime Playbook

A trading playbook translating the sector-trend study's **robust** findings to a
universe tradable on Binance: crypto spot/perps, tokenized ETFs / trad-fi assets,
gold (PAXG), and yield-bearing stablecoins as the cash sleeve.

It deliberately keeps only the conclusions that survived the leakage review of
`sector_trend_study.py` and drops the ones that didn't.

---

## 0 · What the study actually proved (and didn't)

**Carries over (relative results, robust to the index-construction bias):**

1. **A slow trend filter's main gift is drawdown control, not extra return.**
   Long-only above trend cut max drawdown roughly in half vs buy & hold at a
   similar hit rate.
2. **Naive symmetric shorting drags.** Shorts only paid when the market was
   *measurably* unhealthy.
3. **Leverage without a regime governor is a ruin machine** (static 3× → −91% DD).
   Leverage is only compoundable when exposure is cut *before* stress peaks.
4. **Whipsaw rate varies hugely by asset.** Choppy assets destroy crossover
   systems; trade trend only on the cleanest-trending instruments.
5. **Costs and carry matter** and must be in every estimate before believing it.

**Does NOT carry over:**

- Absolute CAGRs (indices used today's cap weights + survivorship → inflated).
- The exact health-score weights and the 30/45/60/75 leverage ladder
  (hand-fit in-sample). Here they are re-used only as *shapes*, deliberately
  de-tuned and made more conservative.
- "Regime-timed 3×" upside. In crypto vol, 3× is never on the menu.

---

## 1 · Universe and roles

| Sleeve | Instruments (Binance) | Role | Cap |
|---|---|---|---|
| Core trend | BTC, ETH (spot) | The "cleanest-trending sectors" — the only assets that get full trend treatment | BTC ≤ 50% NAV, ETH ≤ 30% |
| Satellite trend | SOL, BNB (spot) | Higher-beta trend, half-size | each ≤ 10% |
| Trad-fi risk | Tokenized equity-index exposure (S&P/Nasdaq-type ETF tokens) | Diversifying risk asset; runs the *same* trend rule | combined ≤ 30% |
| Defensive | PAXG (gold) | Risk-off ballast; own it when it's above ITS OWN trend and health is weak | ≤ 20% |
| Cash | USDT/USDC in Simple Earn / flexible yield | The rf sleeve — idle cash must earn; this was material in the study's accounting | unlimited |
| Shorts/hedge | BTC or ETH USDT-margined perps | Hedge ONLY, activated by the health floor | ≤ 25% NAV notional |

**Explicitly excluded:** individual alts below top-10 liquidity, leveraged
tokens (daily-reset decay — the study's caveat about 3× products applies
doubly in crypto vol), and trend-trading any asset with a whipsaw history you
haven't measured. Alts were the "Energy/Materials" of this universe: the
choppiest names, where crossovers are mostly fake breakouts.

---

## 2 · Signals (all causal — trailing windows only)

Weekly cadence. Compute everything on **Sunday 23:59 UTC close**, execute
**Monday** (the study's one-bar lag, kept).

**Per-asset trend state** (the 50d/200d analogue, on daily closes):

- `UP`: price > 200d MA **and** 50d MA > 200d MA
- `DOWN`: price < 200d MA **and** 50d MA < 200d MA
- Otherwise: keep previous state (hysteresis).
- **Whipsaw buffer:** a state flip requires the crossing to exceed a ±2% band
  on the MA spread. The study's #1 failure mode was fake breakouts; the band
  trades slightly late entries for far fewer round trips.

**Market-health score H (0–100), crypto-adapted.** Same construction as
`market_health()` — equal-ish weights, causal rolling z-scores (120d window),
squashed through a logistic. Components:

| Component | Signal | Direction |
|---|---|---|
| Breadth | share of universe (BTC, ETH, SOL, BNB, ETF tokens) above 200d MA | + |
| Momentum | BTC 90d return, z-scored | + |
| Funding | avg BTC+ETH perp funding rate (7d mean), z-scored | − when extreme positive (froth), − when deeply negative only counts half |
| Stablecoin bid | stablecoin dominance 30d change | − (rising dominance = de-risking) |
| Macro risk | VIX z and HY-spread z (reuse the repo's FRED panel) | − |
| Dollar | DXY vs its own 200d MA | − when above |

Weight breadth highest (as in the study), everything else roughly equal. Do
**not** re-tune weights on backtest results you run this year — that's the
in-sample trap identified in the review. Change weights only for a-priori
reasons, then leave them alone.

---

## 3 · Sizing ladder (the leverage schedule, de-tuned for crypto vol)

Gross exposure of the risk sleeves, applied ONLY to assets whose own trend
state is `UP`:

| Health H | Risk-sleeve exposure | Notes |
|---|---|---|
| ≥ 70 | 100% + optional 1.25× on BTC/ETH only (perp overlay) | Leverage cap is 1.25×, not 3×. BTC at 1.25× ≈ S&P at 3× in vol terms |
| 55–70 | 100%, no leverage | Base case |
| 40–55 | 60% risk / 40% cash+PAXG | De-risk *early* — this is where the study's governor earned its keep |
| 25–40 | 25% risk / 75% cash+PAXG | Survive mode |
| < 25 | 0–10% risk; optional BTC perp short ≤ 25% NAV | Shorts exist ONLY here (the "h < 0.35" lesson, made stricter) |

Overlay: **volatility scaling.** Multiply each asset's weight by
`min(1, 40% / realized 30d vol)`. Crypto vol regimes shift violently; the
monthly-equity ladder alone under-reacts.

**Downgrades in the ladder execute immediately (next weekly rebalance).
Upgrades require H to hold above the threshold for 2 consecutive weeks** —
asymmetry is cheap insurance against health-score whipsaw.

---

## 4 · Costs and carry (believe nothing before deducting these)

- Spot fees ~7.5–10 bps/side (BNB discount on). Weekly cadence + hysteresis
  keeps turnover near the study's ~0.1×/month; at that rate fees cost
  ~0.5%/yr. Fine. If your turnover is 3× that, your signal is too fast.
- **Perp funding is the carry:** long overlay in bull markets historically pays
  5–15%/yr — treat it exactly like the study's financing spread. If 30d avg
  funding annualizes above ~15%, the 1.25× overlay is OFF regardless of H.
- Short hedge usually *earns* funding in stress — a tailwind the study's
  borrow-fee model didn't have, but never a reason to short above the H floor.
- Stablecoin yield is the rf leg. Idle cash earning 3–5% was a real
  contributor in the study's fair accounting; leave no idle USDT unstaked
  (subject to your counterparty comfort — see risks).

---

## 5 · Hard risk rules (non-negotiable, checked before anything else)

1. **Kill switch:** portfolio DD > 20% from high-water mark → cut to the
   25–40 ladder row minimum, stay there until H > 55 for 2 weeks.
2. Never leveraged while H < 70. Never any leverage + short simultaneously.
3. Per-asset caps from the table in §1, enforced at rebalance.
4. Perps for hedge/overlay only — position notional, margin ring-fenced,
   isolated margin, no cross.
5. Venue risk is real: Binance is a single counterparty for everything here.
   Keep a defined fraction (your call, e.g. long-term core) in self-custody;
   the playbook operates on the exchange-resident fraction.

---

## 6 · Weekly routine (≈15 minutes, Sundays)

1. Pull daily closes; update 50d/200d states per asset (with the 2% band).
2. Compute H (breadth, momentum, funding, stablecoin dominance, VIX/HY, DXY).
3. Read the ladder row; apply the 2-week rule for upgrades.
4. Vol-scale weights; check caps; check kill switch.
5. Check 30d avg funding → overlay on/off.
6. Place orders Monday; log H, states, exposure, and *why* — the log is what
   lets you audit yourself out of discretionary drift.

---

## 7 · What would falsify this / monitoring

- **Whipsaw audit (quarterly):** fraction of trend flips per asset that
  reversed within 4 weeks or never traveled 5% — the study's exact metric.
  If BTC/ETH start printing sector-worst whipsaw rates (>60%), the regime
  has changed and the trend leg deserves a smaller weight.
- **Health-score hit rate:** average forward 4-week return of the risk sleeve
  when H≥55 vs H<40. If the spread goes ≤ 0 over a rolling 2-year window,
  the score is dead weight — revert to plain trend + fixed 60/40.
- **Do not iterate parameters on live-period results.** One change list per
  year, pre-registered, or you rebuild the in-sample trap this playbook was
  written to avoid.

---

## Caveats

Crypto's usable history is ~2 full cycles — thinner evidence than even the
study's biased 25 years. Correlations between BTC, ETH, and equity ETF tokens
converge toward 1 in stress, so the "diversification" between sleeves is
mostly a calm-market property; the health governor, not diversification, is
the actual risk control. Tokenized ETF liquidity/spreads on Binance can be
materially worse than the underlying — size accordingly.
