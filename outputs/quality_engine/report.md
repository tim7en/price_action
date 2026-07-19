# Sector quality books

## Scope

- 176 unique sector names across 11 sector books.
- 13 names in the dedicated semiconductor/memory book.
- 181 distinct SEC fact payloads in scope; semiconductor extras: ADI, LRCX, SNDK, STX, WDC.
- SEC facts are aligned to filing dates. Forward returns start at the first close strictly after each score date.
- Companies need at least 3 comparable metrics to receive a quality score.
- Every book has a dedicated metric specification and separate standalone/ablation attribution.

## Book specifications

| Book | Specification | Higher-is-better metrics |
| --- | --- | --- |
| SEMIS | semiconductors_memory | fcf_margin, gm_trend, gross_margin, net_cash_ratio, rev_growth |
| XLB | materials | earnings_stability, fcf_margin, gross_margin, low_leverage, rev_growth |
| XLC | communication_services | fcf_margin, margin_steadiness, net_cash_ratio, ni_margin, rev_growth |
| XLE | energy | earnings_stability, fcf_margin, low_leverage, ocf_margin, rev_growth |
| XLF | financials | capital_ratio, earnings_stability, ni_growth, roe |
| XLI | industrials | fcf_margin, gross_margin, low_leverage, margin_steadiness, rev_growth |
| XLK | technology | earnings_stability, fcf_margin, gross_margin, net_cash_ratio, rev_growth |
| XLP | consumer_staples | earnings_stability, fcf_margin, low_leverage, margin_steadiness, ni_margin |
| XLRE | real_estate | low_leverage, ocf_growth, ocf_margin, ocf_stability |
| XLU | utilities | capex_coverage, earnings_stability, low_leverage, ocf_margin, revenue_steadiness |
| XLV | health_care | earnings_stability, fcf_margin, gross_margin, net_cash_ratio, rev_growth |
| XLY | consumer_discretionary | fcf_margin, gross_margin, low_leverage, margin_steadiness, rev_growth |

## Validation

| Book | Specification | Names | Months | Avg IC | 6m spread | N | t-stat |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SEMIS | semiconductors_memory | 13 | 188 | -0.037 | -5.51% | 32 | -1.06 |
| XLB | materials | 18 | 168 | 0.055 | -1.46% | 28 | -0.54 |
| XLC | communication_services | 12 | 175 | 0.001 | 0.90% | 30 | 0.29 |
| XLE | energy | 13 | 186 | -0.144 | -3.61% | 31 | -2.23 |
| XLF | financials | 19 | 186 | 0.050 | 2.36% | 31 | 1.25 |
| XLI | industrials | 17 | 184 | 0.021 | -0.58% | 31 | -0.32 |
| XLK | technology | 21 | 189 | 0.020 | -0.19% | 32 | -0.09 |
| XLP | consumer_staples | 14 | 185 | -0.017 | 0.34% | 31 | 0.35 |
| XLRE | real_estate | 17 | 175 | -0.027 | -1.16% | 30 | -0.87 |
| XLU | utilities | 16 | 183 | -0.028 | -1.79% | 31 | -1.44 |
| XLV | health_care | 15 | 184 | 0.018 | -0.50% | 31 | -0.39 |
| XLY | consumer_discretionary | 17 | 183 | 0.123 | 1.10% | 31 | 0.41 |

Composites reaching |t| >= 1.96: XLE (-2.23). The sign determines whether this supports or rejects the quality signal. Positive rankings without positive significance should be treated as research leads, not established alpha.

## Metric attribution

| Book | Best standalone | Worst standalone | Largest matched contribution |
| --- | --- | --- | --- |
| SEMIS | net_cash_ratio (3.42%) | gross_margin (-9.93%) | gm_trend (+3.19%) |
| XLB | fcf_margin (3.54%) | gross_margin (-1.87%) | fcf_margin (-0.62%) |
| XLC | net_cash_ratio (3.88%) | rev_growth (-3.28%) | net_cash_ratio (+1.52%) |
| XLE | rev_growth (1.91%) | earnings_stability (-2.71%) | low_leverage (-0.34%) |
| XLF | roe (2.55%) | earnings_stability (-0.88%) | capital_ratio (+2.31%) |
| XLI | low_leverage (0.10%) | gross_margin (-2.38%) | fcf_margin (+0.50%) |
| XLK | rev_growth (3.19%) | earnings_stability (-5.42%) | fcf_margin (+2.65%) |
| XLP | margin_steadiness (1.22%) | ni_margin (-1.47%) | margin_steadiness (+1.63%) |
| XLRE | ocf_growth (0.45%) | ocf_margin (-2.45%) | ocf_margin (+2.47%) |
| XLU | ocf_margin (0.40%) | low_leverage (-1.50%) | ocf_margin (+0.29%) |
| XLV | gross_margin (2.95%) | net_cash_ratio (-2.34%) | fcf_margin (+1.92%) |
| XLY | rev_growth (3.63%) | fcf_margin (-1.97%) | margin_steadiness (+1.41%) |

Standalone values are non-overlapping top-minus-bottom six-month spreads. The final column is the decline in composite spread when that metric is removed; positive values indicate that the metric helped the composite on the matched sample.

## Current scorecards

| Book | Eligible | Top three | Bottom three |
| --- | --- | --- | --- |
| SEMIS | 13/13 | MU, SNDK, NVDA | STX, TXN, INTC |
| XLB | 17/18 | NEM, ECL, LIN | DD, LYB, DOW |
| XLC | 12/12 | META, NFLX, GOOG | CHTR, WBD, TTWO |
| XLE | 11/13 | EOG, WMB, DVN | CVX, PSX, MPC |
| XLF | 16/19 | V, PGR, SPGI | JPM, BRK-B, C |
| XLI | 17/17 | ADP, GE, UBER | LMT, UPS, MMM |
| XLK | 21/21 | PLTR, NVDA, ADBE | TXN, IBM, INTC |
| XLP | 13/14 | KO, PG, COST | CL, KDP, EL |
| XLRE | 17/17 | CSGP, O, VICI | SBAC, WY, CBRE |
| XLU | 16/16 | AEP, SO, WEC | AWK, PCG, VST |
| XLV | 15/15 | LLY, ISRG, BSX | AMGN, MRK, PFE |
| XLY | 16/17 | DASH, BKNG, MCD | LOW, GM, F |

## Interpretation limits

- The sector universe is the union of names observed in SEC N-PORT top-holdings snapshots available from 2019 onward. Applying that union back to 2010 is not point-in-time constituent selection and can introduce composition/survivorship bias.
- The semiconductor book is a fixed research universe; SNDK price history begins in 2025, so it contributes only to recent cross-sections.
- Six-month monthly observations overlap. The reported t-stat uses every sixth observation to reduce that dependence.
- Metric attribution tests many sector/metric combinations and is not corrected for multiple testing; treat isolated strong values as hypotheses.
- A missing historical share count does not automatically exclude a company from the top-holdings universe; the $5B screen is enforced only when a point-in-time share count is available.
- SEC tag coverage differs by issuer. The scorecard exposes `n_metrics` and `eligible` so sparse rankings are not silently promoted.
