# Comprehensive Macro Regime Review

Subtitle: a principles-based macro review inspired by public debt-cycle, liquidity-cycle, and all-weather diversification frameworks, not written by or in the exact style of Ray Dalio.

Data basis: this review uses the cached macro feature store and model inventory already in this repository. The macro store was generated on 2026-05-08, while many underlying source series are marked stale in `cache/macro_features/series_health.csv`. The latest cached observations generally run from 2026-03-01 to 2026-04-09. External sources were checked for definitions and conceptual grounding on 2026-05-09, but this document does not claim the local cache has been refreshed to live market values.

This is research material, not investment advice.

## 1. Executive View

The central conclusion is simple:

VIX should not merely receive a larger manual feature weight. It should receive a larger architectural role.

VIX is not the same kind of input as RSI, volume, or a moving average. Cboe describes VIX as a measure of the market's expectation of near-term volatility implied by S&P 500 index options. That makes it a forward-looking market-implied stress variable. It tells us what option markets are charging for uncertainty over roughly the next 30 calendar days, not what price has already done.

That changes how the model should be built.

The right architecture is:

```text
Regime layer:
    VIX level
    VIX change
    VIX percentile
    VIX term structure
    realized volatility versus implied volatility
    credit stress
    rate shock
    inflation shock
    valuation fragility

Prediction layer:
    price action
    volume
    macro context
    valuation context
    sentiment and positioning when available

Decision layer:
    trade or no trade
    position size
    stop distance
    leverage
    cooldown
    strategy family
```

The goal is not to make VIX "30 percent of the model." The goal is to make VIX decide what type of world the model is operating in. A breakout in low-volatility disinflationary growth is not the same event as a breakout during high volatility, widening spreads, and rising rates. The same return pattern should not be trusted equally in every regime.

The current cached macro picture points to a fragile regime rather than a clean risk-on or clean risk-off environment. Valuation is high. Real assets are extreme. Spot volatility is elevated. Rates remain restrictive. Production is positive but soft. Credit spreads are still calm. That combination means the market has not confirmed a credit accident, but it has enough fragility that a volatility, credit, oil, or rate shock could change the regime quickly.

## 2. The Macro Machine

The economy is a transaction machine.

One person's spending is another person's income. Income supports borrowing. Borrowing creates additional spending power. That spending supports revenues, margins, employment, tax receipts, and asset prices. When credit grows faster than income, spending and asset prices can rise faster than the real economy. When the cost of money rises or lenders pull back, the process reverses. Spending slows, income slows, credit quality deteriorates, and asset prices are forced to reprice.

The big forces are:

- Growth: whether real output, employment, profits, and production are improving or deteriorating.
- Inflation: whether nominal spending is creating more real activity or mostly higher prices.
- Liquidity: whether money, credit, and balance-sheet capacity are easy or tight.
- Risk appetite: whether investors want to own uncertainty or are being paid to reduce it.
- Valuation: what future cash flows are already priced into assets.
- Policy: how central banks and governments respond to the mix of growth, inflation, debt, and stress.

Every market price is an expression of these forces.

Equities like rising growth, falling discount rates, easy liquidity, and stable risk appetite. Long-duration growth stocks like low rates and calm volatility even more. Credit likes growth and liquidity, but dislikes recession and refinancing stress. Commodities like nominal growth, supply constraints, and inflation surprises. Gold likes distrust in paper assets, negative real confidence, and policy credibility stress. The dollar often acts like a global funding and liquidity barometer. Volatility is the market's alarm system.

The mistake is to look at macro variables one by one:

```text
CPI is 2.4 percent.
VIX is 24.
CAPE is 39.
10-year yield is 4.3 percent.
High-yield spread is 3.1 percent.
```

The better question is:

```text
What do these variables say together?
```

High valuation is not a crash signal by itself. High VIX is not always bearish. Rising rates are not always fatal. But high valuation plus rising VIX plus fast rate increases plus widening credit spreads plus negative momentum is a very different animal. The true signal is often the interaction.

## 3. Current Cached Macro Snapshot

The table below summarizes the local cached macro store. Percentiles are calculated against the repository's post-1999 history, not against the full historical record available from each external source.

| Channel | Cached latest | Percentile since 1999 | Interpretation |
| --- | ---: | ---: | --- |
| Headline CPI YoY | 2.43 percent as of 2026-02-01 | 52.6 | Headline inflation is near the middle of the post-1999 range and lower than one year earlier. |
| Core CPI YoY | 2.67 percent as of 2026-03-01 | 79.1 | Sticky inflation remains elevated relative to the post-1999 sample, though it is easing. |
| Shelter CPI YoY | 3.23 percent as of 2026-03-01 | 58.0 | Shelter pressure is moderating but remains a slow-moving source of inflation. |
| Energy CPI YoY | 11.32 percent as of 2026-03-01 | 69.9 | Energy has re-accelerated sharply and can change the inflation narrative quickly. |
| Unemployment rate | 4.30 percent as of 2026-03-01 | 32.8 | Labor slack is not severe in the cache. |
| Industrial production YoY | 0.74 percent as of 2026-03-01 | 37.0 | Real activity is positive but not strong. |
| Manufacturing output YoY | 0.62 percent as of 2026-03-01 | 42.5 | The goods cycle is soft but not broken. |
| 2-year Treasury yield | 3.81 percent as of 2026-04-07 | 72.0 | Front-end policy expectations remain restrictive. |
| 10-year Treasury yield | 4.33 percent as of 2026-04-07 | 73.2 | Discount rates remain high versus the post-1999 sample. |
| 30-year Treasury yield | 4.90 percent as of 2026-04-07 | 75.4 | Long-duration assets still face rate pressure. |
| 10Y minus 2Y spread | 0.52 percent as of 2026-04-07 | 38.0 | The curve is positive, but not steep by historical standards. |
| 10Y minus 3M spread | 0.62 percent as of 2026-04-07 | 31.7 | The policy-sensitive curve has normalized but remains low. |
| High-yield spread | 3.05 percent as of 2026-04-06 | 7.2 | Credit stress is unusually contained. |
| NFCI | -0.434 as of 2026-03-27 | 57.9 | Financial conditions are not crisis-tight, though recently firmer. |
| Spot VIX | 24.17 as of 2026-04-06 | 77.1 | Immediate market stress is elevated. |
| VIX 3M | 21.91 as of 2026-04-09 | 60.7 | Medium-horizon volatility is elevated but below spot VIX. |
| DXY | 99.00 as of 2026-04-09 | 69.5 | The dollar is firm but not extreme. |
| Gold | USD 4,764.60 as of 2026-04-09 | 99.4 | Store-of-value demand is at an extreme in this sample. |
| WTI crude | USD 114.01 as of 2026-04-06 | 98.3 | Oil is in an extreme inflation-shock zone in this sample. |
| Shiller CAPE | 39.14x as of 2026-04-08 | 91.5 | Equity valuation is rich. |
| Market cap to GDP composite | 278.54 percent as of 2026-04-09 | 98.8 | Financial assets are expensive relative to the economy. |

The combined reading:

- Inflation is not a broad 2022-style wave, but it is not fully extinguished.
- Core and shelter inflation are still sticky enough to limit policy flexibility.
- Energy is the unstable inflation channel.
- Production is positive but soft.
- Rates remain restrictive.
- Valuation is extreme.
- Volatility is elevated.
- Credit has not yet confirmed a broad balance-sheet stress event.
- Gold and oil are sending scarcity, inflation, or policy credibility signals.

This is a fragile late-cycle or inflation-shock environment, not a simple expansion.

## 4. Why VIX Deserves A Structural Role

VIX is an implied volatility and stress variable. It should influence:

- Whether the model trades.
- How much the model trades.
- Which strategy family is active.
- How wide stops should be.
- Whether breakouts are trustworthy.
- Whether mean reversion is dangerous.
- Whether leverage is allowed.
- Whether a signal needs extra confirmation.

The basic reason is that VIX changes the meaning of price movement.

A 2 percent daily move when VIX is 12 is abnormal. A 2 percent daily move when VIX is 40 may be ordinary.

For an S&P-style asset:

```text
expected_daily_vol = VIX / 100 / sqrt(252)
vix_adjusted_move = daily_return / expected_daily_vol
```

Example:

```text
VIX = 16
expected_daily_vol = 16 percent / sqrt(252) = about 1.0 percent
daily_return = 2.0 percent
vix_adjusted_move = about 2.0 sigma

VIX = 40
expected_daily_vol = 40 percent / sqrt(252) = about 2.5 percent
daily_return = 2.0 percent
vix_adjusted_move = about 0.8 sigma
```

The same return has a different information value. Therefore, raw price action should be transformed into volatility-aware features:

```text
return_1d_vix_adjusted
return_5d_vix_adjusted
return_20d_vix_adjusted
breakout_strength_vix_adjusted
drawdown_vix_adjusted
range_expansion_vix_adjusted
volume_spike_x_vix_percentile
trend_strength_x_vix_regime
```

VIX also has direction and structure:

```text
vix_level
vix_percentile_1y
vix_change_1d
vix_change_5d
vix_change_20d
vix_acceleration = vix_change_5d - vix_change_20d
vix3m_minus_vix
vix_term_structure_ratio = vix3m / spot_vix
realized_vol_20d
iv_rv_spread = spot_vix - realized_vol_20d
```

Interpretation:

- Low and falling VIX usually supports trend following and risk-on exposure.
- Low but rising VIX is an early warning that complacency may be ending.
- High and rising VIX is a stress or panic regime.
- High but falling VIX is often a recovery or relief-rally setup.
- Spot VIX above VIX 3M suggests immediate stress is more urgent than medium-term stress.
- Implied volatility far above realized volatility means options price a risk premium; raw price moves must be judged carefully.

The model should not just know VIX. It should know how price behaves relative to the volatility environment.

## 5. Valuation As A Vulnerability Multiplier

Shiller CAPE and market-cap-to-GDP should not be treated as short-term sell signals. They are long-horizon valuation and fragility gauges.

Campbell and Shiller's valuation work supports the idea that valuation ratios have more power for long-horizon return expectations than for near-term earnings or dividend forecasts. In practical terms:

```text
High CAPE does not mean crash tomorrow.
High CAPE means future return expectations are lower and vulnerability is higher.
```

The market can stay expensive for years if liquidity is abundant, rates are low, credit is calm, and volatility is falling. But when expensive markets meet a liquidity shock, rate shock, credit shock, or volatility shock, the decline can become violent.

Use valuation as a multiplier:

```text
valuation_fragility_score =
    z_score(shiller_cape_ratio)
    + z_score(market_cap_to_gdp_pct_patched)
    + z_score(price_to_sales_if_available)
    + z_score(real_yield_pressure_if_available)
```

Then combine it with stress:

```text
crash_risk_score =
    valuation_fragility_score
    x volatility_stress_score
    x rate_shock_score
    x credit_stress_score
    x negative_momentum_score
```

The multiplication matters conceptually. A high CAPE market with low VIX and easy credit can keep trending. A high CAPE market with rising VIX and fast rate repricing is much more dangerous.

Current cached valuation state:

- Shiller CAPE: 39.14x, 91.5th percentile in the local post-1999 sample.
- Market cap to GDP composite: 278.54 percent, 98.8th percentile.

That is a fragile starting point. It does not force an immediate bearish signal, but it lowers the margin of safety.

## 6. Rate Pace, Not Just Rate Level

Markets care about rate levels, but they often react more sharply to the speed, surprise, and direction of rate changes.

Why?

Equities are long-duration assets. Growth stocks, technology, crypto, speculative assets, and unprofitable companies are especially long duration because much of their expected value comes from cash flows far in the future. Higher discount rates reduce the present value of those future cash flows. Fast increases in rates can also break financing structures, create forced selling, and tighten liquidity.

The model should track:

```text
fed_funds_rate_level
fed_funds_change_3m
fed_funds_change_6m
fed_funds_change_12m
fed_funds_acceleration

two_year_yield_change_1m
two_year_yield_change_3m
ten_year_yield_change_1m
ten_year_yield_change_3m
thirty_year_yield_change_1m

real_yield_level
real_yield_change_1m
breakeven_inflation_change_1m

yield_curve_10y_2y_level
yield_curve_10y_2y_change_3m
yield_curve_10y_3m_level
yield_curve_10y_3m_change_3m

market_implied_policy_path
fed_surprise_vs_expectations
```

The most important rate-shock features are likely:

- Change in the 2-year yield.
- Change in real yields.
- Change in the expected policy path.
- Rate acceleration.
- Curve flattening or post-inversion steepening.

Current cached rate state:

- 2-year yield: 3.81 percent, 72.0th percentile.
- 10-year yield: 4.33 percent, 73.2nd percentile.
- 30-year yield: 4.90 percent, 75.4th percentile.
- 10Y minus 2Y spread: 0.52 percent, 38.0th percentile.
- 10Y minus 3M spread: 0.62 percent, 31.7th percentile.

This says rates are still restrictive, while the curve is no longer deeply inverted. That can mean late-cycle normalization, but the interpretation depends on credit and labor. A curve that steepens because growth expectations improve is benign. A curve that steepens because front-end rates collapse during stress is not benign.

## 7. Credit Is The Confirmation Variable

Credit is often where the financial economy becomes the real economy.

Equities can ignore soft production for a while. They can ignore expensive valuation for a long time. They can even ignore high rates if earnings and liquidity remain resilient. But when credit spreads widen, lenders are demanding more compensation for default and refinancing risk. That changes behavior. Firms reduce investment. Households tighten spending. Investors reduce leverage. Defaults and downgrades become more likely.

The current cached high-yield spread is low:

- High-yield spread: 3.05 percent, 7.2nd percentile.

That is not a credit accident. It is actually the strongest argument against an immediate crisis reading. But low spreads are not automatically safe. They can represent genuine strength, or they can represent complacency. The change matters.

Useful credit features:

```text
hy_spread_level
hy_spread_percentile_1y
hy_spread_change_5d
hy_spread_change_20d
hy_spread_change_63d
hy_spread_acceleration

investment_grade_spread_if_available
ccc_spread_if_available
bank_lending_standards_if_available
delinquency_rates_if_available
default_rates_if_available
```

Useful interactions:

```text
widening_spreads x high_valuation
widening_spreads x rising_vix
widening_spreads x strong_dollar
widening_spreads x rising_unemployment
widening_spreads x production_slowdown
```

In the current cached regime, credit is the key watch variable. If spreads stay low, the market can remain resilient despite valuation and volatility. If spreads widen while VIX is already elevated, the regime can change quickly.

## 8. Inflation Breadth: Headline Is Not Enough

Inflation has to be decomposed.

Headline CPI can fall because energy falls, even if core and shelter remain sticky. Headline CPI can rise because energy spikes, even if underlying inflation is not broad. A model that only sees headline CPI will overreact to some shocks and underreact to others.

The local cache separates:

```text
cpi_yoy_pct
core_cpi_yoy_pct
energy_cpi_yoy_pct
shelter_cpi_yoy_pct
```

Current cached readings:

- Headline CPI YoY: 2.43 percent.
- Core CPI YoY: 2.67 percent.
- Shelter CPI YoY: 3.23 percent.
- Energy CPI YoY: 11.32 percent.

Interpretation:

Headline inflation looks manageable. Core and shelter are still sticky. Energy is the fast-moving shock channel. That is a difficult mix because it can limit central-bank flexibility while hurting household purchasing power and corporate margins.

Useful inflation features:

```text
headline_minus_core_inflation_gap
core_cpi_change_3m
shelter_cpi_change_3m
energy_cpi_change_3m
sticky_inflation_flag
energy_shock_flag
inflation_breadth_score
inflation_acceleration_score
```

Useful interactions:

```text
sticky_core_inflation x rising_2y_yield
energy_shock x falling_manufacturing_output
energy_shock x consumer_discretionary_underperformance
inflation_breadth x long_rate_selloff
inflation_shock x high_valuation
```

The dangerous inflation regime is not just "inflation is high." The dangerous regime is inflation pressure plus weakening real activity plus restrictive policy plus expensive assets.

## 9. Real Activity And Labor

Real activity tells us whether nominal spending is translating into actual production.

The cache says:

- Industrial production YoY: 0.74 percent.
- Manufacturing output YoY: 0.62 percent.
- Unemployment rate: 4.30 percent.

This is not a severe recession signal. But it is not a broad acceleration either. Production is positive but soft. Labor slack is modest. The key question is whether the next move is reacceleration or deterioration.

Useful growth features:

```text
industrial_production_change_3m
industrial_production_change_12m
manufacturing_output_change_3m
manufacturing_vs_industrial_gap
production_slowdown_flag
goods_cycle_score

unemployment_change_3m
unemployment_change_12m
sahm_rule_style_labor_stress
jobless_claims_if_available
payroll_momentum_if_available
```

Useful interactions:

```text
production_slowdown x curve_inversion
production_slowdown x widening_spreads
rising_unemployment x widening_spreads
rising_unemployment x falling_equity_momentum
soft_production x sticky_inflation
```

The model should not wait for official recession labels. Market regimes change before the label arrives.

## 10. Dollar And Real Assets

The dollar, gold, and oil are not just alternative assets. They are macro interpreters.

DXY:

- A rising dollar often tightens global financial conditions.
- It can pressure emerging markets, commodities, and dollar borrowers.
- It can signal global demand for funding liquidity.

Gold:

- Gold often responds to store-of-value demand, policy credibility stress, real-rate dynamics, and distrust of paper claims.
- Gold strength during high valuation and elevated volatility is a warning that investors are paying for alternative stores of value.

Oil:

- Oil is both a growth and inflation variable.
- Oil strength can reflect demand, supply stress, geopolitical stress, or currency effects.
- Oil shocks squeeze consumers and margins if wages and pricing power do not offset them.

Current cached readings:

- DXY: 99.00, 69.5th percentile.
- Gold: USD 4,764.60, 99.4th percentile.
- WTI: USD 114.01, 98.3rd percentile.

The real-asset message is loud. Gold and oil are near the top of the local post-1999 sample. That does not tell us exactly why they are strong, but it does say the macro backdrop is not a clean low-inflation, low-stress expansion.

Useful features:

```text
dxy_change_5d
dxy_change_20d
dollar_strength_percentile
gold_momentum_20d
gold_vs_dxy_relative_strength
wti_change_20d
wti_volatility_20d
oil_spike_flag
real_asset_momentum_score
```

Useful interactions:

```text
rising_dxy x widening_credit_spreads
gold_strength x rising_vix
gold_strength x policy_credibility_stress
oil_spike x sticky_inflation
oil_spike x weak_production
oil_spike x consumer_discretionary_underperformance
```

## 11. Regime Taxonomy

The model should classify the world into regimes. The exact labels can be learned or rule-assisted, but the categories should correspond to different market behavior.

### 11.1 Disinflationary Growth

Macro signature:

- Growth positive or accelerating.
- Inflation falling or contained.
- Credit spreads calm.
- VIX low or falling.
- Rates stable or falling gently.
- Dollar not creating funding stress.

Typical asset behavior:

- Equities do well.
- Growth and duration-sensitive assets can lead.
- Credit performs well.
- Bonds can diversify equity risk.
- Commodities may lag unless growth is strong.

Model behavior:

- Trend-following signals are more trustworthy.
- Breakouts can be given more room.
- Position sizes can be normal or above normal if realized drawdown risk is low.
- Mean reversion shorts should be used carefully.

Main risk:

- Complacency and valuation creep.

### 11.2 Liquidity Bubble Or Valuation Stretch

Macro signature:

- Valuation high.
- VIX low.
- Credit spreads tight.
- Momentum strong.
- Liquidity easy or perceived as easy.
- Investors extrapolate recent winners.

Typical asset behavior:

- High-duration growth leads.
- Speculative assets can outperform.
- Correlations appear low until stress begins.
- Volatility selling works until it suddenly does not.

Model behavior:

- Do not short solely because valuation is high.
- Reduce long-run expected return assumptions.
- Increase sensitivity to VIX changes, credit spread changes, and rate shocks.
- Watch for failed breakouts and distribution days.

Main risk:

- High valuation becomes dangerous only when the support system changes.

### 11.3 Inflationary Boom

Macro signature:

- Nominal growth strong.
- Inflation rising.
- Production resilient.
- Commodities strong.
- Rates rising, but not yet breaking credit.

Typical asset behavior:

- Energy, materials, value, industrials, and real assets can lead.
- Long-duration growth becomes more fragile.
- Bonds may not hedge equities well.
- Cash-flow-now businesses are preferred over cash-flow-later narratives.

Model behavior:

- Add commodity and inflation interaction features.
- Penalize duration-heavy assets when rates accelerate.
- Prefer price action confirmed by real activity and nominal revenue strength.

Main risk:

- Inflationary boom becomes stagflation if production weakens while inflation stays sticky.

### 11.4 Stagflation Squeeze

Macro signature:

- Inflation sticky or reaccelerating.
- Production slowing.
- Energy strong.
- Rates restrictive.
- Credit not necessarily broken yet.
- Consumer purchasing power under pressure.

Typical asset behavior:

- Equities struggle because margins and multiples compress.
- Bonds may fail as a hedge if inflation keeps yields high.
- Real assets can outperform, but volatility rises.
- Defensive equity sectors may help but remain equity-like in crisis.

Model behavior:

- Reduce broad long exposure.
- Require stronger confirmation for growth-stock signals.
- Increase drawdown-model importance.
- Favor assets with inflation linkage or defensive cash flows.

Main risk:

- Policy cannot easily rescue markets without worsening inflation credibility.

### 11.5 Rate-Shock Regime

Macro signature:

- Fast rise in 2-year yields or real yields.
- Front-end policy expectations reprice.
- Curve flattens or shifts abruptly.
- VIX begins rising.
- Long-duration assets underperform.

Typical asset behavior:

- Growth stocks, tech, crypto, and speculative assets are hit hardest.
- Value and cash-flow-now assets may outperform on a relative basis.
- International and emerging markets can suffer if the dollar also rises.
- Credit becomes vulnerable with a lag.

Model behavior:

- Add explicit rate_shock_score.
- Reduce leverage.
- Penalize duration-sensitive assets.
- Watch for rate_shock x high_valuation interactions.

Main risk:

- The rate shock becomes a credit shock.

### 11.6 Credit Deleveraging

Macro signature:

- High-yield spreads widen.
- NFCI tightens.
- VIX rises.
- Dollar often strengthens.
- Labor and production deteriorate with a lag.
- Refinancing stress appears.

Typical asset behavior:

- Equities and credit fall together.
- International equities provide less diversification than expected.
- Cash and high-quality liquidity become valuable.
- Gold and dollar may help, depending on whether the shock is deflationary or inflationary.

Model behavior:

- Trade less.
- Lower position sizes.
- Tighten risk budgets.
- Increase drawdown-model weight.
- Avoid leveraged longs.
- Require credit stabilization before re-risking.

Main risk:

- Correlations go to one across risky assets.

### 11.7 Panic Or Forced Liquidation

Macro signature:

- VIX spikes.
- Spot VIX rises above VIX 3M.
- Credit spreads widen fast.
- Dollar or funding stress rises.
- Risk assets gap and intraday ranges expand.
- Liquidity disappears.

Typical asset behavior:

- Risk assets sell together.
- Correlations rise.
- Volatility targeting and leverage unwind.
- Good assets may be sold to raise cash.

Model behavior:

- Priority is survival, not signal frequency.
- Cut leverage.
- Widen stops only if position size is reduced.
- Avoid mean reversion unless the recovery regime has begun.
- Use vix_adjusted_move to avoid confusing normal panic-range movement with signal.

Main risk:

- Price movement becomes discontinuous and model assumptions break.

### 11.8 Recovery And Reflation

Macro signature:

- VIX high but falling.
- Credit spreads wide but narrowing.
- Dollar stress easing.
- Policy support rising or expected.
- Price momentum improves before economic data recovers.

Typical asset behavior:

- Risk assets rally before macro data looks good.
- High beta can lead.
- Credit stabilization is key.
- Cyclicals recover if growth expectations improve.

Model behavior:

- Do not require macro data to be fully healthy.
- Focus on direction of stress variables.
- Allow recovery signals when VIX and credit are improving.
- Distinguish "bad but improving" from "bad and worsening."

Main risk:

- Bear-market rallies can look like recoveries if credit does not confirm.

### 11.9 Sideways Low-Volatility Regime

Macro signature:

- VIX low.
- Realized volatility low.
- Credit calm.
- Growth and inflation stable.
- Price trend not decisive.

Typical asset behavior:

- Carry and mean reversion can work.
- Breakouts often fail.
- Volatility selling appears attractive.

Model behavior:

- Lower breakout confidence unless range expansion is meaningful relative to VIX.
- Mean reversion can be allowed with disciplined stops.
- Watch for complacency transition into low-to-rising VIX.

Main risk:

- The first volatility expansion can invalidate months of low-vol assumptions.

## 12. Current Cached Regime Diagnosis

The current cached regime is best described as:

```text
Fragile late-cycle / inflation-shock watch
```

Why:

- Valuation is high: CAPE and market-cap-to-GDP are both elevated.
- Real assets are extreme: gold and oil are near the top of the local sample.
- Volatility is elevated: spot VIX is in the 77th percentile.
- Spot VIX is above VIX 3M in the cache, which points to immediate stress.
- Rates remain restrictive.
- Production is soft but not collapsing.
- Labor is not yet signaling severe slack.
- High-yield spreads are low, which argues against a confirmed credit crisis.

The most important sentence:

The market is fragile, but credit has not yet confirmed the fragility.

That means the model should not automatically shift into full bearish mode. It should shift into higher caution:

- Lower leverage.
- Reduce exposure to fragile long-duration trades.
- Demand better confirmation for breakouts.
- Increase drawdown-model importance.
- Monitor credit spread changes closely.
- Treat oil and gold strength as macro warnings, not as noise.
- Avoid static manual weights; use regime-dependent gates and sizing.

## 13. Regime Transition Watchlist

The regime can change through several paths.

### Path A: Fragile But Resilient

Conditions:

- VIX falls.
- Credit remains calm.
- Oil stabilizes.
- Core and shelter inflation continue to ease.
- Production stabilizes or improves.

Implication:

- Risk assets can continue to perform despite high valuation.
- Trend following remains viable.
- Valuation still lowers long-term return expectations but does not force a near-term exit.

### Path B: Stagflation Squeeze

Conditions:

- Oil stays high or rises further.
- Core and shelter inflation stop improving.
- Production weakens.
- Rates remain high.
- Credit begins to widen.

Implication:

- Equities face both margin and multiple pressure.
- Bonds may not hedge well.
- Real assets and defensive cash flows become more important.
- The model should reduce broad risk and require stronger signal confirmation.

### Path C: Credit Accident

Conditions:

- High-yield spreads widen rapidly.
- NFCI tightens.
- VIX remains high or rises.
- Dollar strengthens.
- Labor weakens.

Implication:

- This becomes a deleveraging regime.
- Correlations across risky assets rise.
- Position size should fall before prediction confidence collapses.
- Drawdown model becomes more important than return model.

### Path D: Recovery Reflation

Conditions:

- VIX falls from elevated levels.
- Credit spreads stop widening or tighten.
- Dollar stress eases.
- Rates stabilize.
- Production stops deteriorating.

Implication:

- The model can re-risk before the macro data looks perfect.
- Direction of stress matters more than level of stress.
- Recovery trades should be allowed if drawdown risk is improving.

## 14. Diversification: What Worked Across Regimes

Owning many things is not the same as being diversified.

True diversification means owning return streams that respond differently to different economic conditions:

- Growth up or down.
- Inflation up or down.
- Liquidity easy or tight.
- Risk appetite rising or falling.
- Dollar funding stress rising or falling.
- Policy easing or tightening.

The local regime-window analysis shows:

- SPY and QQQ were highly correlated in every regime, from 0.82 in the dot-com unwind to 0.96 in the current cached window.
- International developed equities were not independent crisis diversifiers. SPY/EFA correlation was 0.94 during the GFC and 0.94 during the pandemic shock window.
- Emerging markets were also equity-like in stress. SPY/EEM correlation was 0.91 during the GFC and 0.89 during the pandemic shock window.
- Gold was a cleaner diversifier across several regimes. SPY/gold correlation was -0.15 in the dot-com unwind, -0.06 in the GFC, near zero in the QE expansion, and 0.09 in the current cached window.
- The dollar was helpful in some stress regimes. SPY/DXY correlation was -0.19 in the GFC and -0.40 during the inflation-tightening window.
- Utilities reduced beta but were still equity-like in crises. SPY/XLU correlation was 0.79 in the GFC and 0.85 during the pandemic shock window.

The simple diversified basket tested in the local cache used U.S. equities, non-U.S. equities, emerging markets, gold, oil, the dollar, and utilities. It is not an optimal portfolio. It is a demonstration of economic diversification.

| Window | SPY annualized return | SPY max drawdown | Diversified basket annualized return | Diversified basket max drawdown | Lesson |
| --- | ---: | ---: | ---: | ---: | --- |
| Dot-com unwind | -13.7 percent | -47.5 percent | -10.7 percent | -36.7 percent | Diversification helped when growth equity was the epicenter. |
| Credit boom / great moderation | 13.7 percent | -13.7 percent | 18.1 percent | -12.1 percent | Multiple engines worked together. |
| GFC | -22.6 percent | -55.2 percent | -13.1 percent | -44.5 percent | Diversification helped, but risky assets still fell together. |
| QE / low-inflation expansion | 13.0 percent | -19.3 percent | 8.3 percent | -16.2 percent | Diversification reduced drawdown but lagged equities. |
| Pandemic shock | 8.3 percent | -33.7 percent | -17.5 percent | -33.6 percent | Sudden liquidation overwhelmed static diversification. |
| Inflation tightening | 9.5 percent | -24.5 percent | 5.9 percent | -20.8 percent | Real assets and dollar exposure helped cushion the regime. |
| Current cached window | 17.8 percent | -18.8 percent | 21.3 percent | -13.6 percent | Diversification helped while gold, oil, non-U.S. assets, and utilities participated. |

The lesson:

Diversification is not meant to beat the best asset in every regime. It is meant to prevent the portfolio from needing one future to happen.

## 15. Portfolio Construction Principles

A portfolio should be balanced by economic exposure, not ticker count.

The main exposure buckets are:

```text
Growth:
    equities
    cyclical sectors
    high-yield credit
    emerging markets
    growth-sensitive commodities

Inflation:
    commodities
    energy
    materials
    inflation-linked bonds when available
    selected real assets

Deflation / liquidity:
    cash
    high-quality duration when inflation is not the dominant problem
    dollar exposure in funding stress

Store of value:
    gold
    scarce real assets
    assets with policy credibility hedge characteristics

Volatility / optionality:
    explicit hedges
    volatility-aware position sizing
    drawdown controls
    regime gates
```

The current cached regime suggests:

- Do not rely only on equity diversification.
- Do not assume bonds automatically hedge if inflation or rates are the problem.
- Keep liquidity valuable.
- Treat gold and oil strength as macro information.
- Let VIX and credit decide whether to reduce or restore risk.
- Let valuation determine vulnerability, not exact timing.

## 16. Model Architecture

The strategy should be a regime-aware risk system, not a single buy/sell predictor.

### Model 1: Return Prediction

Question:

```text
Will forward return over the next N bars be positive after fees and slippage?
```

Inputs:

```text
price action
volume
trend
momentum
macro context
VIX context
rates
valuation
credit
inflation
real activity
sentiment when available
```

Output:

```text
return_probability
expected_return
```

### Model 2: Drawdown Prediction

Question:

```text
Will this trade experience unacceptable adverse movement before payoff?
```

Inputs should heavily include:

```text
spot_vix
vix_change
vix_percentile
vix_term_structure
realized_volatility
rate_shock_score
credit_stress_score
valuation_fragility_score
liquidity_stress_score
negative_momentum_score
```

Output:

```text
drawdown_probability
expected_adverse_excursion
```

### Model 3: Regime Classifier

Classes:

```text
risk_on_trend
sideways_low_vol
liquidity_bubble
inflationary_boom
stagflation_squeeze
rate_shock
credit_deleveraging
panic
recovery_reflation
```

Output:

```text
regime_label
regime_probability_vector
regime_confidence
```

### Final Decision Engine

```text
take_trade =
    return_probability > return_threshold
    and drawdown_probability < drawdown_threshold
    and regime_allows_strategy == true
    and liquidity_filter_passes == true
```

Position size:

```text
position_size =
    base_risk_budget
    x return_confidence
    x drawdown_safety
    x regime_multiplier
    x volatility_target_multiplier
    x liquidity_multiplier
```

Stop logic:

```text
stop_distance =
    base_atr_stop
    x vix_regime_multiplier
    x asset_volatility_multiplier
```

But widening stops must be paired with smaller size. Otherwise the model hides risk instead of controlling it.

## 17. Feature Blueprint

### VIX And Volatility

```text
vix_level
vix_percentile_1y
vix_percentile_5y
vix_change_1d
vix_change_5d
vix_change_20d
vix_acceleration = vix_change_5d - vix_change_20d
vix3m_minus_vix
vix_term_structure_ratio = vix3m_level / spot_vix
realized_vol_20d
realized_vol_63d
iv_rv_spread = spot_vix - realized_vol_20d
```

### Price Relative To VIX

```text
expected_daily_vol = spot_vix / 100 / sqrt(252)
return_1d_vix_adjusted = return_1d / expected_daily_vol
return_5d_vix_adjusted = return_5d / (expected_daily_vol x sqrt(5))
return_20d_vix_adjusted = return_20d / (expected_daily_vol x sqrt(20))
breakout_strength_vix_adjusted
drawdown_vix_adjusted
range_expansion_vix_adjusted
```

### Valuation

```text
cape_level
cape_percentile_10y
cape_zscore
market_cap_to_gdp_level
market_cap_to_gdp_percentile
market_cap_to_gdp_zscore
valuation_fragility_score
```

### Rates

```text
fed_funds_level
fed_funds_change_3m
fed_funds_change_6m
fed_funds_change_12m
two_year_yield_change_1m
two_year_yield_change_3m
ten_year_yield_change_1m
ten_year_yield_change_3m
real_yield_change_1m
yield_curve_change_3m
rate_acceleration
rate_shock_score
```

### Credit And Liquidity

```text
hy_spread_level
hy_spread_percentile
hy_spread_change_5d
hy_spread_change_20d
nfci_level
nfci_change_4w
credit_stress_score
liquidity_stress_score
```

### Inflation

```text
headline_cpi_yoy
core_cpi_yoy
shelter_cpi_yoy
energy_cpi_yoy
headline_minus_core_gap
shelter_minus_headline_gap
core_cpi_change_3m
shelter_cpi_change_3m
energy_cpi_change_3m
sticky_inflation_flag
energy_shock_flag
inflation_breadth_score
```

### Real Activity And Labor

```text
industrial_production_yoy
industrial_production_change_3m
manufacturing_output_yoy
manufacturing_output_change_3m
unemployment_rate
unemployment_change_3m
unemployment_change_12m
production_slowdown_score
labor_stress_score
```

### Dollar And Real Assets

```text
dxy_level
dxy_change_5d
dxy_change_20d
dollar_strength_score
gold_momentum_20d
gold_vs_dxy_relative_strength
wti_change_20d
wti_volatility_20d
oil_shock_score
real_asset_momentum_score
```

## 18. Interaction Features

The most useful features are likely interactions:

```text
high_cape x rising_vix
high_cape x fast_rate_hikes
high_cape x yield_curve_inversion
high_cape x widening_credit_spreads

rising_vix x negative_price_momentum
vix_spike x volume_spike
spot_vix_above_vix3m x negative_momentum

rate_shock x growth_stock_exposure
rate_shock x high_valuation
rate_shock x dollar_strength

credit_stress x dollar_strength
credit_stress x weak_production
credit_stress x rising_unemployment

energy_shock x sticky_core_inflation
energy_shock x falling_manufacturing_output
energy_shock x consumer_discretionary_underperformance

gold_strength x rising_vix
gold_strength x policy_credibility_stress
```

The model should learn:

```text
High CAPE alone is not enough.
High VIX alone is not enough.
Fast rate shock alone is not always enough.

High CAPE + rising VIX + fast rates + negative momentum + widening spreads is dangerous.
```

## 19. Practical Regime Rules

These are not final trading rules. They are scaffolding for model design and diagnostics.

### High CAPE, Low VIX

Meaning:

- Market is expensive but not stressed.
- Long-run expected return is lower.
- Shorting purely on valuation is usually premature.

Model action:

- Keep trading if trend and drawdown models allow it.
- Reduce long-term return assumptions.
- Watch VIX, rates, and credit for activation.

### High CAPE, Rising VIX

Meaning:

- Fragility is activating.
- Investors are paying more for protection.

Model action:

- Reduce long exposure.
- Tighten risk budgets.
- Require stronger confirmation.
- Increase drawdown-model influence.

### High CAPE, Rising VIX, Fast Rate Shock

Meaning:

- Crash-risk ingredients are present.
- Long-duration assets are vulnerable.

Model action:

- Avoid leveraged longs.
- Reduce position size.
- Penalize growth-stock signals.
- Prefer defensive or hedged exposures.

### High VIX, Falling VIX

Meaning:

- Stress remains elevated, but direction is improving.
- Could be recovery or relief rally.

Model action:

- Allow recovery trades if credit confirms.
- Use smaller size than normal.
- Watch for failed rallies.

### Low VIX, Strong Trend

Meaning:

- Trend-following regime can work.
- Complacency risk rises if valuation is high.

Model action:

- Let winners run if drawdown risk is low.
- Track low-to-rising VIX transition.
- Avoid overfitting to calm volatility.

### Oil Spike, Sticky Core, Weak Production

Meaning:

- Stagflation squeeze risk.

Model action:

- Reduce broad equity beta.
- Penalize consumer discretionary and long-duration exposure.
- Watch credit and labor for confirmation.

### Credit Widening From Low Spreads

Meaning:

- Complacency may be breaking.
- The absolute spread can still look low while the direction is dangerous.

Model action:

- Treat spread change as more important than spread level.
- Reduce risk before the level becomes obviously distressed.

## 20. How To Validate This In ML

The main risk is not building too few features. The main risk is building features that leak future information or do not respect regime timing.

Validation principles:

- Use walk-forward validation.
- Use calendar splits with untouched holdout periods.
- Add embargoes around labels to reduce leakage.
- Align mixed-frequency macro data exactly as it would have been known in real time.
- Lag macro releases if release calendars are not modeled.
- Track stale features explicitly.
- Test feature value by regime, not just globally.
- Test drawdown reduction, not only ROC AUC.
- Evaluate trade frequency because regime filters often improve quality by reducing activity.
- Compare raw returns to VIX-adjusted returns.
- Compare raw valuation to valuation x stress interactions.

Key metrics:

```text
holdout_roc_auc
holdout_brier_score
precision_at_threshold
recall_at_threshold
profit_factor
hit_rate
average_trade_return
max_drawdown
expected_adverse_excursion
trade_rate_by_regime
return_by_regime
drawdown_by_regime
false_positive_rate_by_regime
```

The improvement should show up less as "the model predicts every move" and more as:

- Fewer trades in hostile regimes.
- Smaller drawdowns.
- Better sizing.
- Less damage from false positives.
- Higher return per unit of risk.

## 21. Current Repo Alignment

This repository already contains many of the necessary building blocks:

Current macro groups:

- Inflation breadth and labor.
- Real activity and production.
- Rates and the curve.
- Credit and conditions.
- Volatility and risk appetite.
- Dollar and real assets.
- Valuation and debt-cycle backdrop.

Current useful series:

```text
spot_vix
vix3m_level
high_yield_spread
NFCI
us_2y_yield
us_10y_yield
us_30y_yield
yield_curve_10y_2y
T10Y3M
cpi_yoy_pct
core_cpi_yoy_pct
energy_cpi_yoy_pct
shelter_cpi_yoy_pct
industrial_production_yoy_pct
manufacturing_output_yoy_pct
unemployment_rate_pct
dxy_close
gold_usd_per_oz
wti_usd_per_bbl
shiller_cape_ratio
market_cap_to_gdp_pct_patched
```

The next improvement is not more raw macro series by itself. The next improvement is better transforms:

- Percentiles.
- Changes.
- Accelerations.
- Regime labels.
- VIX-adjusted price features.
- Stress scores.
- Interaction terms.
- Decision-layer risk gates.

## 22. Recommended Implementation Roadmap

### Phase 1: Add VIX-Adjusted Price Features

Implement:

```text
expected_daily_vol
return_1d_vix_adjusted
return_5d_vix_adjusted
return_20d_vix_adjusted
breakout_strength_vix_adjusted
drawdown_vix_adjusted
range_expansion_vix_adjusted
```

Reason:

This directly changes the meaning of price movement and should improve signal quality across regimes.

### Phase 2: Add Stress Scores

Implement:

```text
volatility_stress_score
valuation_fragility_score
rate_shock_score
credit_stress_score
inflation_shock_score
production_slowdown_score
liquidity_stress_score
```

Reason:

Scores create compact, interpretable regime inputs while still allowing tree models to learn nonlinear thresholds.

### Phase 3: Add Regime Classifier

Implement classes:

```text
risk_on_trend
sideways_low_vol
liquidity_bubble
inflationary_boom
stagflation_squeeze
rate_shock
credit_deleveraging
panic
recovery_reflation
```

Reason:

The model should know which playbook is active before trusting price action.

### Phase 4: Add Drawdown Model

Predict:

```text
expected_adverse_excursion
max_drawdown_before_exit
probability_of_stop_before_target
```

Reason:

The biggest compounding improvement often comes from avoiding bad drawdown regimes, not from predicting slightly more winners.

### Phase 5: Add Portfolio-Level Risk Controls

Implement:

```text
max_exposure_by_regime
max_sector_beta_by_regime
max_correlation_cluster_exposure
volatility_targeting
drawdown_based_deleveraging
credit_stress_deleveraging
panic_cooldown
```

Reason:

Single-trade signals can be good while the aggregate portfolio is making one concentrated macro bet.

## 23. Missing Data Worth Adding

Priority additions:

- Fed funds effective rate and changes.
- Real yields.
- Breakeven inflation.
- Fed policy expectations.
- Fed surprise versus market expectations.
- Treasury liquidity measures.
- Investment-grade spreads.
- CCC spreads.
- Bank lending standards.
- Delinquency and default rates.
- PMI new orders.
- Inventory-to-sales.
- Jobless claims.
- Payroll momentum.
- Balance-sheet liquidity: reserves, reverse repo, Fed assets.
- Global dollar funding stress.
- Sector valuation and sector duration proxies.
- Earnings revision breadth.
- Market breadth.
- Put-call ratios and option skew.
- Dealer gamma or options positioning if available.

The most valuable additions are likely real yields, Fed path expectations, lending standards, credit quality details, and market breadth. They directly improve regime classification.

## 24. What The Model Should Do Right Now Under The Cached Data

Given the local cache:

```text
Regime: fragile late-cycle / inflation-shock watch
Credit: calm but critical
Volatility: elevated
Valuation: high
Rates: restrictive
Real assets: extreme
Production: soft positive
Labor: not yet distressed
```

Recommended model posture:

- Trade, but selectively.
- Reduce leverage relative to a low-VIX risk-on regime.
- Use VIX-adjusted move features before trusting breakouts.
- Increase drawdown-model influence.
- Penalize long-duration growth exposure if rates are accelerating.
- Watch high-yield spreads and NFCI for confirmation.
- Treat oil strength as a possible inflation shock.
- Treat gold strength as a policy credibility or store-of-value warning.
- Do not short solely because CAPE is high.
- Do not ignore valuation because credit is calm.

Current regime rule of thumb:

```text
If VIX falls and credit stays calm:
    allow selective risk-on continuation

If VIX rises and credit widens:
    shift toward risk-off / deleveraging logic

If oil rises while production weakens:
    shift toward stagflation-squeeze logic

If VIX is high but falling and credit improves:
    allow recovery-reflation logic
```

## 25. Final Principle

Macro data is not a crystal ball. It is a map of pressures.

The best use of macro is not to say:

```text
VIX is high, therefore sell.
CAPE is high, therefore crash.
Rates are high, therefore short.
Oil is high, therefore inflation.
```

The best use is to ask:

```text
What is growth doing?
What is inflation doing?
What is liquidity doing?
What is credit doing?
What is volatility doing?
What is valuation assuming?
What happens to the portfolio if those assumptions are wrong?
```

Diversification is humility built into the portfolio. Regime awareness is humility built into the process. Together, they turn macro data from a prediction contest into a survival and compounding system.

The largest improvement to compounding will probably not come from manually giving VIX a bigger model weight. It will come from building a model architecture where VIX, valuation, rates, credit, inflation, liquidity, and price action each do their correct job:

```text
VIX = market-implied stress and volatility regime
Shiller CAPE = valuation fragility
Rate pace = liquidity and discount-rate shock
Credit spreads = balance-sheet stress confirmation
Inflation breadth = policy flexibility and margin pressure
Production = real-economy confirmation
Price relative to VIX = whether movement is abnormal or expected
Diversification = protection against needing one future to happen
```

## Source Appendix

- Cboe VIX overview: https://www.cboe.com/tradable-products/volatility-trading/
- Robert Shiller online data: https://www.econ.yale.edu/~shiller/data.htm
- Campbell and Shiller, "Valuation Ratios and the Long-Run Stock Market Outlook": https://www.nber.org/papers/w8221
- World Bank paper on rising U.S. interest rates and emerging/developing economies: https://documents1.worldbank.org/curated/en/099036212082239238/pdf/IDU032d1feef0db0d0480e0b3190f92d87c50de8.pdf
- FRED DGS2, 2-year Treasury yield: https://fred.stlouisfed.org/series/DGS2
- FRED DGS10, 10-year Treasury yield: https://fred.stlouisfed.org/series/DGS10
- FRED DGS30, 30-year Treasury yield: https://fred.stlouisfed.org/series/DGS30
- FRED T10Y3M, 10-year minus 3-month Treasury spread: https://fred.stlouisfed.org/series/T10Y3M
- FRED BAMLH0A0HYM2, ICE BofA U.S. High Yield Option-Adjusted Spread: https://fred.stlouisfed.org/series/BAMLH0A0HYM2
- FRED NFCI, Chicago Fed National Financial Conditions Index: https://fred.stlouisfed.org/series/NFCI
- FRED CPILFESL, core CPI: https://fred.stlouisfed.org/series/CPILFESL
- FRED CPIENGSL, energy CPI: https://fred.stlouisfed.org/series/CPIENGSL
- FRED CUSR0000SAH1, shelter CPI: https://fred.stlouisfed.org/series/CUSR0000SAH1
- FRED INDPRO, industrial production: https://fred.stlouisfed.org/series/INDPRO
- FRED IPMAN, manufacturing output: https://fred.stlouisfed.org/series/IPMAN
