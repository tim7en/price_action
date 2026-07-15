# Weekly Narratives — nine market states, quantified

Each week is assigned exactly **one** narrative by priority order, from
mechanical conditions on five instruments: SPY trend state (50/200, 2% band),
market health, the momentum oscillator, ATH drawdown, and CFTC asset-manager
positioning (release-aligned z). Quantified on 996 weeks, 2007-06 → 2026-07.
Unconditional baseline: forward 3m +2.93%, 72% hit rate.

The point of a narrative is to stop you from inventing one. The story for the
week is *assigned by the data*, its historical footprint is printed next to
it, and the action column only ever points at rules that already exist.

| # | Narrative | Condition (first match wins) | Weeks | Fwd 3m | Hit | Worst |
|---|---|---|---|---|---|---|
| 1 | Panic flush | dd ≤ −30% **or** osc ≤ −0.75 | 9.3% | **+6.7%** | 74% | −21% |
| 2 | Euphoria | osc ≥ +0.75 & health ≥ 55 | 3.2% | **+5.2%** | 88% | −6.7% |
| 3 | Bear-market rally | dd ≤ −20% & +8%/20d & trend DOWN | n=1 | – | – | – |
| 4 | Confirmed bear | trend DOWN & health < 45 | 10.8% | **−0.3%** | 65% | −38% |
| 5 | Broken trend, health holding | trend DOWN & health ≥ 45 | 4.4% | +5.4% | 84% | −10% |
| 6 | Crack in the trend | trend UP & health < 55 | 14.9% | +3.2% | 69% | −17% |
| 7 | Momentum surge (the false dawn) | trend UP & osc +0.3 in 3m & osc < 0.5 | 7.6% | **+0.4%** | 66% | −28% |
| 8 | Crowded calm | trend UP & health ≥ 55 & AM z > +1 | 17.0% | +2.9% | 71% | −23% |
| 9 | Confirmed bull, clean | trend UP & health ≥ 55 & AM z ≤ +1 | 32.6% | +2.8% | 74% | −15% |

## The narratives

**1 · Panic flush — the ladder's moment.** The market is in a deep drawdown or
momentum is deeply washed out. This is the *best* forward-return state in the
sample — more than double baseline — and the worst weeks still fell another
21%, which is exactly why the ladder deploys in tranches instead of all at
once. *Action: drawdown ladder buys fire mechanically; DCA continues; nothing
is sold; ignore every headline, they are all bearish here by construction.*

**2 · Euphoria — sell inventory, not the market.** Deep-overbought momentum in
a healthy tape. The data is unambiguous: this state *continues* (88% hit, best
worst-case in the table) — it is not a top signal. The only sell it justifies
is recycling ladder inventory bought in state 1. *Action: ladder exit gates;
throttle is near max by formula; shorting here is fighting an 88% hit rate.*

**3 · Bear-market rally — the hedge-killer.** A violent bounce inside a bear
market. Too rare at this definition to quantify forward returns (n=1), but its
mechanics are proven elsewhere: bear rallies reached +14.5%/day, +19.4%/5d —
these bounces are what liquidate leveraged shorts. *Action: none. Don't chase
it, don't short into it, don't "re-test" the hedge. Wait for the golden cross.*

**4 · Confirmed bear — the only red state.** Death cross with health broken.
The single configuration with negative expected returns and a −38% worst
quarter. Everything defensive in the repo exists for this state. *Action:
cross book is in cash by rule; throttle is near zero by formula; the health
floor hedge (≤3x isolated) is legal below health 25; DCA continues — state 1
usually follows.*

**5 · Broken trend, health holding — the whipsaw tax.** Death cross but
breadth/credit/vol say fine. Historically favorable (+5.4%, 84% hit) — this is
the premium you pay for trend discipline: the filter sits out some rebounds.
*Action: none — do not front-run the golden cross. The +5.4% you forgo here
is the price of the −33% max drawdown the filter buys you elsewhere.*

**6 · Crack in the trend — cheap insurance season.** Price still trending up
but health has slipped below 55. Returns near baseline, tails fatter. *Action:
the governor's de-risk row executes on anything levered (grid bot margin
halves); unlevered sleeves unchanged.*

**7 · Momentum surge — the false dawn.** The most commonly told bullish story
("momentum is turning up!") and the data's biggest myth-bust: fast oscillator
*acceleration* from low levels carries **no edge** (+0.4% vs +2.9% baseline,
worst −28%). Momentum *level* predicts; momentum *change* seduces. *Action:
explicitly none — this narrative exists to stop a trade.*

**8 · Crowded calm — late innings. (Active as of 2026-07.)** Trend up, health
strong, but asset managers at extreme net-long (z > +1; currently the 98.9th
percentile). Conditioned on a healthy trend, crowding did *not* lower average
returns (+2.9% ≈ baseline) — but it marks a thinner cushion: the worst quarter
from this state was −23%, and the unconditional crowding tilt (1.6% vs 4.6%
per quarter) bites once trend or health crack. *Action: full size per rules —
and zero tolerance for improvisation above them. No added leverage, ladder
armed, read state 6/4 transitions promptly.*

**9 · Confirmed bull, clean positioning — the default.** A third of all
weeks. Trend up, health fine, positioning unremarkable. *Action: the boring
rules, executed borly. DCA, throttle by formula, sheet on Sundays.*

## Transitions — the early-warning map

Run-length and transition analysis of the same 996 weeks (state runs, where
each state goes when it changes, and the probability of reaching the red
state within the next quarter):

| From state | Median run | Exits to (top) | P(bear ≤ 13w) |
|---|---|---|---|
| 1 Panic flush | 4w | →6 44% · →4 44% | **44%** |
| 2 Euphoria | 9w | →6/→9/→8 even | 16% |
| 4 Confirmed bear | 6w (max 38w) | →5 60% · →1 20% | 91% (persists) |
| 5 Broken trend, health OK | 5w | →7 44% · →1 22% | 32% |
| 6 Crack in the trend | 4w | →4 25% · →1 25% · →9 25% | **29%** |
| 7 Momentum surge | 6w | →9 50% | 0% |
| 8 Crowded calm | 3w | **→9 89%** | **4%** |
| 9 Clean bull | 4w | →8 67% · →6 17% | 6% |

**The road to a bear is stereotyped.** The eight weeks before the ten bear
entries were spent in state 1 (36%), state 6 (32%), and state 9 (18%) —
almost never in crowded calm (1%) or euphoria (1%). The market does not jump
from healthy states to a bear; it walks through a **crack (6) or a flush (1)
first**. Operationally: states 8/9 need no vigilance beyond the weekly
glance; the moment the sheet prints state 6 or 1, transition risk is live
(~1-in-3 to the red state within a quarter) and the governor/ladder rules are
the response.

**Panic flushes are bimodal, which is the ladder's whole thesis:** from state
1, 44% of paths reach a bear within a quarter *and* the average forward
return is the best in the table (+6.7%). Flushes either resolve violently up
or become bears — tranching is the only honest way to hold both outcomes.

**Crowded calm (8) is benign in itself:** median 3 weeks, exits to clean bull
89% of the time, and the lowest bear-within-a-quarter probability of any
state (4%). Crowding is dry tinder, not a spark — it tells you how bad the
fire could be, not when it starts.

**Ladder cycle expectations:** from the first week of a panic flush to the
next euphoria (the ladder's exit zone), the median wait was **41 weeks**; the
longest was ~10.5 years (2008→2020). Seven of nine flush runs resolved.

## Priority order and hygiene

Conditions are evaluated 1→9; the first match is the week's narrative
(states 1/2/4 outrank the rest because their footprints are the most
distinct). During quarterly roll weeks (Mar/Jun/Sep/Dec expiry), the COT
%-of-OI wobbles mechanically — the sheet already warns; read positioning
levels, not weekly jumps. The oscillator's latest point is a partial month
until month-end.

## Caveats (printed on purpose)

- 996 weeks ≈ 2.5 cycles; states 2, 3, 5 have thin samples. Treat forward
  returns as ranks, not point forecasts.
- These narratives never override a rule; every action column points at a
  rule that existed before the narrative did. If a narrative ever seems to
  demand a trade the rules don't, the narrative is wrong.
- Definitions are frozen with the annual review, like everything else.
