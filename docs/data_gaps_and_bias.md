# Data Gaps And Bias

## What is already covered

The current macro stack now exposes per-feature histories for:

- DXY
- gold
- WTI
- Wilshire total market index
- Shiller CAPE
- U.S. 2Y, 10Y, and 30Y yields
- 10Y minus 2Y curve
- CPI level, CPI MoM, CPI YoY
- unemployment rate
- market cap to GDP
- XLU, XLY, EEM, EFA
- copper
- VIX 3M
- spot VIX
- high-yield spread
- NFCI
- 10Y minus 3M curve

## High-value features still missing

The most important missing context features relative to the target design are:

- MOVE or another Treasury-volatility proxy
- real yields and inflation breakevens
- Fed funds expectations or policy-path proxies
- PMI, payroll, CPI-surprise, and broader economic-surprise features
- Economic Policy Uncertainty and Trade Policy Uncertainty
- Geopolitical Risk Index and conflict/news event feeds such as GDELT or ACLED
- option skew, put-call ratios, and other market-implied sentiment measures
- AAII, CFTC positioning, fund flows, and other crowding/sentiment data
- point-in-time news sentiment and event classification

## Current data quality gaps

The main quality gaps visible in the current cache are:

- `market_cap_to_gdp_pct` is stale relative to the rest of the macro set and currently ends far earlier than 2026.
- Monthly and quarterly macro series are aligned by observation date, not by publication date or first availability date.
- The asset universe is very small and mostly contains currently tradable symbols.
- The universe is not yet point-in-time; it is defined by today’s file list.

## Survivorship bias risks in the current repo

The current setup is still exposed to survivorship bias because:

- it mostly trains on symbols that are still around today
- delisted, acquired, bankrupt, and long-dead names are absent
- current symbol selection can leak future knowledge into the historical universe
- macro series are not yet lagged to their first release timestamps

## Minimum controls to reduce survivorship bias

Use these controls before trusting performance:

1. Build a point-in-time universe snapshot for each rebalance date instead of using today’s symbol list.
2. Include delisted and acquired symbols, plus their final returns and delisting events.
3. Freeze eligibility rules at the decision timestamp: market cap, liquidity, sector membership, and listing status must be evaluated using only data known then.
4. Lag macro and fundamental series to their publication date, not their observation date.
5. Distinguish clearly between feature timestamp, signal timestamp, and execution timestamp.
6. Keep a final untouched out-of-time holdout and avoid threshold tuning on it.

## Practical next build steps

The next practical sequence is:

1. keep the current macro feature store as the point of inspection
2. add stale-series checks so incomplete macro histories are obvious
3. broaden the asset universe with long-history liquid symbols first
4. add point-in-time universe membership and delisted names
5. add point-in-time news and uncertainty features