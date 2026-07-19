# Sector quality books

## Scope

- 176 unique sector names across 11 sector books.
- 13 names in the dedicated semiconductor/memory book.
- 181 distinct SEC fact payloads in scope; semiconductor extras: ADI, LRCX, SNDK, STX, WDC.
- SEC facts are aligned to filing dates. Forward returns start at the first close strictly after each score date.
- Companies need at least 3 comparable metrics to receive a quality score.

## Validation

| Book | Archetype | Names | Months | Avg IC | 6m spread | N | t-stat |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SEMIS | semis | 13 | 188 | -0.037 | -5.51% | 32 | -1.06 |
| XLB | cyclical | 18 | 170 | 0.032 | -2.42% | 29 | -0.80 |
| XLC | asset_light | 12 | 174 | 0.008 | -0.22% | 29 | -0.10 |
| XLE | cyclical | 13 | 186 | -0.161 | -1.87% | 31 | -1.09 |
| XLF | financial | 19 | 186 | 0.050 | 2.36% | 31 | 1.25 |
| XLI | cyclical | 17 | 186 | 0.020 | -0.94% | 31 | -0.51 |
| XLK | asset_light | 21 | 189 | 0.020 | -0.19% | 32 | -0.09 |
| XLP | defensive | 14 | 185 | -0.017 | 0.34% | 31 | 0.35 |
| XLRE | reit | 17 | 175 | -0.027 | -1.16% | 30 | -0.87 |
| XLU | defensive | 16 | 177 | -0.079 | -2.02% | 30 | -1.32 |
| XLV | defensive | 15 | 184 | -0.022 | 0.35% | 31 | 0.26 |
| XLY | cyclical | 17 | 183 | 0.013 | -2.33% | 31 | -0.94 |

No book reaches |t| >= 1.96 on the non-overlapping test. Positive rankings should therefore be treated as research leads, not established alpha.

## Current scorecards

| Book | Eligible | Top three | Bottom three |
| --- | --- | --- | --- |
| SEMIS | 13/13 | MU, SNDK, NVDA | STX, TXN, INTC |
| XLB | 17/18 | NEM, MLM, LIN | LYB, DOW, DD |
| XLC | 12/12 | META, NFLX, EA | TTWO, CHTR, WBD |
| XLE | 11/13 | EOG, WMB, KMI | PSX, CVX, MPC |
| XLF | 16/19 | V, PGR, SPGI | JPM, BRK-B, C |
| XLI | 17/17 | GE, ADP, UBER | FDX, UPS, BA |
| XLK | 21/21 | PLTR, NVDA, ADBE | TXN, IBM, INTC |
| XLP | 13/14 | KO, PG, COST | CL, KDP, EL |
| XLRE | 17/17 | CSGP, O, VICI | SBAC, WY, CBRE |
| XLU | 13/16 | AWK, PEG, AEP | SRE, PCG, VST |
| XLV | 14/15 | ISRG, DHR, LLY | BMY, PFE, MRK |
| XLY | 16/17 | BKNG, MCD, ABNB | LOW, GM, F |

## Interpretation limits

- The sector universe is the union of names observed in SEC N-PORT top-holdings snapshots available from 2019 onward. Applying that union back to 2010 is not point-in-time constituent selection and can introduce composition/survivorship bias.
- The semiconductor book is a fixed research universe; SNDK price history begins in 2025, so it contributes only to recent cross-sections.
- Six-month monthly observations overlap. The reported t-stat uses every sixth observation to reduce that dependence.
- A missing historical share count does not automatically exclude a company from the top-holdings universe; the $5B screen is enforced only when a point-in-time share count is available.
- SEC tag coverage differs by issuer. The scorecard exposes `n_metrics` and `eligible` so sparse rankings are not silently promoted.
