# Macro-governed Nasdaq POC return assessment

## Decision

At the reference **0.50 bps one-way cost**, the frozen POC ledger earns **2.78%** with fixed 0.25% risk and a **-0.78%** maximum drawdown. Applying the macro, trend, shock/recovery, two-minute, and five-minute governors produces **0.76%** with a **-0.42%** drawdown. The overlay is therefore a risk-control layer, not evidence of a higher-return timing edge.

This does not reproduce Fabio Valentini's public competition returns. Those headline results are not a suitable planning assumption because the public standings do not provide a complete trade ledger, leverage path, fees, or maximum drawdown. The defensible planning range is the cost- and size-adjusted result below, followed by live paper validation.

## Frozen workflow tested

1. **Macro bias:** last completed monthly statistical regime; adverse regimes only reduce risk.
2. **Golden-cross and daily bias:** prior-day SPY 50/200 state with 2% hysteresis plus prior-session Nasdaq 10/30 direction.
3. **Shock/reversal timing:** prior-day falling-knife, fragile, recovery, or normal state. A recovery requires a recent shock, falling VIX and credit-spread pace, and positive five-day SPY trend.
4. **Five-minute auction proxy:** last five completed one-minute bars must show momentum on the same side of causal session VWAP for full risk.
5. **Area of interest:** already-frozen 3-day/5-day composite POC with aligned three-session POC migration.
6. **Two-minute confirmation:** direction of the last two completed one-minute bars; it governs size and does not retrospectively remove frozen trades.
7. **Entry:** one-minute acceptance across POC, restricted to regular-session minutes 15–330.
8. **Stop:** the largest of the micro stop, one-minute ATR floor, or 0.50x preceding completed 15-minute range.
9. **Target:** the frozen five-minute, full-position 2R rule. No new target or signal was optimized here.
10. **Sizing:** 0.25% base risk, 20x notional cap, stop after three losing trades or -0.75% in a session. Profit-financed sizing is reported separately.

## Ablation at the reference cost

| variant | trades_executed | cumulative_net_return | annualized_return | maximum_drawdown | win_rate | profit_factor | average_risk_fraction | average_effective_leverage | break_even_one_way_cost_bps | daily_halt_skips |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_0.25_no_overlays | 89 | 2.78% | 1.54% | -0.78% | 56.18% | 1.58 | 0.25% | 1.76x | 1.37 | 0 |
| macro_only | 89 | 1.51% | 0.84% | -0.39% | 56.18% | 1.63 | 0.13% | 0.88x | 1.45 | 0 |
| golden_daily_only | 89 | 2.17% | 1.20% | -0.64% | 56.18% | 1.69 | 0.17% | 1.31x | 1.41 | 0 |
| shock_recovery_only | 89 | 0.94% | 0.52% | -0.57% | 56.18% | 1.29 | 0.15% | 1.21x | 0.93 | 0 |
| intraday_2m_5m_only | 89 | 2.63% | 1.45% | -0.73% | 56.18% | 1.55 | 0.25% | 1.72x | 1.35 | 0 |
| combined_governor | 89 | 0.76% | 0.42% | -0.42% | 56.18% | 1.39 | 0.10% | 0.76x | 1.09 | 0 |
| combined_profit_financed | 89 | 0.78% | 0.43% | -0.41% | 56.18% | 1.38 | 0.10% | 0.79x | 1.09 | 0 |
| full_stack_governor | 89 | 0.76% | 0.42% | -0.42% | 56.18% | 1.39 | 0.10% | 0.76x | 1.09 | 0 |
| full_stack_profit_financed | 89 | 0.78% | 0.43% | -0.41% | 56.18% | 1.38 | 0.10% | 0.79x | 1.09 | 0 |

## Calendar stability

| variant | period | trades_executed | net_return | win_rate |
| --- | --- | --- | --- | --- |
| fixed_0.25_no_overlays | 2024 | 45 | 1.59% | 0.5778 |
| fixed_0.25_no_overlays | 2025 | 44 | 1.17% | 0.5455 |
| full_stack_governor | 2024 | 45 | 0.44% | 0.5778 |
| full_stack_governor | 2025 | 44 | 0.32% | 0.5455 |

## Did the proposed layers separate expectancy?

The R figures use the frozen ledger's 0.50 bps one-way reference cost. They are descriptive and were not used to retune the trade rule.

| dimension | state | trades | win_rate | mean_gross_r | mean_net_r | sum_net_r |
| --- | --- | --- | --- | --- | --- | --- |
| shock_recovery_state | falling_knife | 33 | 0.6667 | 0.3257 | 0.2833 | 9.3498 |
| shock_recovery_state | fragile | 11 | 0.4545 | 0.0297 | -0.0614 | -0.6759 |
| shock_recovery_state | normal | 30 | 0.4667 | 0.0783 | 0.0022 | 0.0667 |
| shock_recovery_state | recovery | 15 | 0.6000 | 0.2584 | 0.1528 | 2.2913 |
| spy_alignment | aligned | 51 | 0.6078 | 0.2676 | 0.1855 | 9.4588 |
| spy_alignment | opposed | 38 | 0.5000 | 0.0961 | 0.0414 | 1.5731 |
| nq_alignment | aligned | 50 | 0.5600 | 0.1835 | 0.1072 | 5.3604 |
| nq_alignment | neutral | 26 | 0.6154 | 0.2559 | 0.1997 | 5.1920 |
| nq_alignment | opposed | 13 | 0.4615 | 0.1131 | 0.0369 | 0.4796 |
| two_minute_alignment | aligned | 89 | 0.5618 | 0.1944 | 0.1240 | 11.0319 |
| five_minute_alignment | aligned | 82 | 0.5366 | 0.1749 | 0.1057 | 8.6694 |
| five_minute_alignment | neutral | 7 | 0.8571 | 0.4225 | 0.3375 | 2.3626 |

## Cost sensitivity

| variant | one_way_cost_bps | cumulative_net_return | maximum_drawdown | profit_factor |
| --- | --- | --- | --- | --- |
| fixed_0.25_no_overlays | 0.2500 | 0.0359 | -0.0076 | 1.8007 |
| fixed_0.25_no_overlays | 0.5000 | 0.0278 | -0.0078 | 1.5781 |
| fixed_0.25_no_overlays | 1.0000 | 0.0126 | -0.0104 | 1.2334 |
| fixed_0.25_no_overlays | 1.5000 | -0.0040 | -0.0153 | 0.9368 |
| fixed_0.25_no_overlays | 2.0000 | -0.0210 | -0.0279 | 0.7005 |
| combined_governor | 0.2500 | 0.0111 | -0.0036 | 1.6060 |
| combined_governor | 0.5000 | 0.0076 | -0.0042 | 1.3872 |
| combined_governor | 1.0000 | 0.0012 | -0.0054 | 1.0553 |
| combined_governor | 1.5000 | -0.0060 | -0.0081 | 0.7718 |
| combined_governor | 2.0000 | -0.0124 | -0.0136 | 0.5846 |
| full_stack_governor | 0.2500 | 0.0111 | -0.0036 | 1.6060 |
| full_stack_governor | 0.5000 | 0.0076 | -0.0042 | 1.3872 |
| full_stack_governor | 1.0000 | 0.0012 | -0.0054 | 1.0553 |
| full_stack_governor | 1.5000 | -0.0060 | -0.0081 | 0.7718 |
| full_stack_governor | 2.0000 | -0.0124 | -0.0136 | 0.5846 |
| full_stack_profit_financed | 0.2500 | 0.0113 | -0.0035 | 1.5902 |
| full_stack_profit_financed | 0.5000 | 0.0078 | -0.0041 | 1.3788 |
| full_stack_profit_financed | 1.0000 | 0.0013 | -0.0054 | 1.0552 |
| full_stack_profit_financed | 1.5000 | -0.0060 | -0.0082 | 0.7768 |
| full_stack_profit_financed | 2.0000 | -0.0124 | -0.0135 | 0.5915 |

## Session bootstrap

The bootstrap resamples complete trading sessions. It measures path fragility inside this small historical sample; it is not an out-of-sample guarantee.

| variant | one_way_cost_bps | sessions | samples | return_p05 | return_median | return_p95 | probability_positive | maximum_drawdown_p05 | maximum_drawdown_median |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_0.25_no_overlays | 0.5000 | 41 | 5000 | -0.0017 | 0.0273 | 0.0592 | 0.9368 | -0.0208 | -0.0101 |
| combined_governor | 0.5000 | 41 | 5000 | -0.0028 | 0.0076 | 0.0182 | 0.8808 | -0.0087 | -0.0042 |
| full_stack_governor | 0.5000 | 41 | 5000 | -0.0028 | 0.0076 | 0.0182 | 0.8808 | -0.0087 | -0.0042 |
| full_stack_profit_financed | 0.5000 | 41 | 5000 | -0.0029 | 0.0078 | 0.0188 | 0.8804 | -0.0088 | -0.0042 |

## Discrete MNQ sizing

The base fill scenario assumes $1.50 round-turn fees plus 0.50 index points of round-turn slippage per MNQ. The stress scenario assumes $2.50 plus 1.00 points. These are scenario inputs, not a quote from a specific broker.

| variant | scenario | starting_equity | trades_executed | zero_contract_skips | cumulative_net_return | annualized_return | maximum_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_0.25_no_overlays | base | 25000.0000 | 41 | 48 | 1.50% | 0.83% | -0.39% |
| fixed_0.25_no_overlays | stress | 25000.0000 | 35 | 54 | 0.75% | 0.42% | -0.37% |
| fixed_0.25_no_overlays | base | 100000.0000 | 88 | 1 | 2.82% | 1.56% | -0.56% |
| fixed_0.25_no_overlays | stress | 100000.0000 | 88 | 1 | 2.03% | 1.12% | -0.54% |
| combined_governor | base | 25000.0000 | 4 | 85 | 0.16% | 0.09% | -0.10% |
| combined_governor | stress | 25000.0000 | 2 | 87 | -0.12% | -0.07% | -0.12% |
| combined_governor | base | 100000.0000 | 58 | 31 | 0.45% | 0.25% | -0.32% |
| combined_governor | stress | 100000.0000 | 53 | 36 | 0.18% | 0.10% | -0.36% |
| full_stack_governor | base | 25000.0000 | 4 | 85 | 0.16% | 0.09% | -0.10% |
| full_stack_governor | stress | 25000.0000 | 2 | 87 | -0.12% | -0.07% | -0.12% |
| full_stack_governor | base | 100000.0000 | 58 | 31 | 0.45% | 0.25% | -0.32% |
| full_stack_governor | stress | 100000.0000 | 53 | 36 | 0.18% | 0.10% | -0.36% |
| full_stack_profit_financed | base | 25000.0000 | 4 | 85 | 0.16% | 0.09% | -0.10% |
| full_stack_profit_financed | stress | 25000.0000 | 2 | 87 | -0.12% | -0.07% | -0.12% |
| full_stack_profit_financed | base | 100000.0000 | 58 | 31 | 0.41% | 0.23% | -0.32% |
| full_stack_profit_financed | stress | 100000.0000 | 53 | 36 | 0.13% | 0.07% | -0.36% |

## Regime coverage

Monthly macro coverage:

| regime | trades |
| --- | --- |
| Inflationary · Inverted curve / late-cycle | 87 |
| missing | 2 |

Shock/recovery coverage:

| state | trades |
| --- | --- |
| falling_knife | 33 |
| normal | 30 |
| recovery | 15 |
| fragile | 11 |

## Interpretation

- The monthly macro label changes too little in 2024–2025 to validate macro entry timing. It mostly reduces risk mechanically.
- Golden-cross and daily direction are priors, not triggers. A lower drawdown with proportionally lower return is useful governance, but not added alpha.
- The POC setup's best segment was the prior-day falling-knife state, not the calm state. The generic shock governor therefore reduced the strongest observed expectancy; do not promote it to a live sizing rule from this sample.
- Shock/recovery timing is fully lagged by one day. It cannot react to an intraday shock until the next session with the available panel.
- Two-minute direction aligned on every frozen entry and therefore added no information. The five-minute proxy was aligned on 82 of 89 entries and did not improve expectancy.
- The only entry edge under test remains POC migration plus one-minute acceptance. True footprint aggression, CVD, bid/ask imbalance, queue depletion, and absorption are absent from OHLCV.
- MNQ sizing exposes granularity: smaller accounts may skip valid trades because one contract exceeds the planned stop risk.

## Deployment gate

**BLOCKED for live capital.** The source CSV's contract/venue identity is unverified, 94% of closes are off the CME NQ quarter-point grid, the sample contains only 89 frozen trades, and the candidate was originally selected with visibility into both calendar years. Require contract-verified tick data, true bid/ask/order-flow fields, broker-specific costs, and a fresh forward paper sample before deployment.

## Public reference points

- Fabio Valentini's published workflow is summarized as Direction → Location → Aggression, with roughly 0.25% risk per trade, profits used to finance larger risk, a three-loss stop, scaling into winners, and a stated target of at least 2:1 reward/risk: https://www.chartacademy.com/instructors/fabio-valentini
- Public World Cup standings report +89.5% in Q1 2024, +218.3% in Q4 2024, and +169.7% in Q1 2025. These competition-account figures are not comparable to this unlevered planning return without the underlying ledger and drawdown path: https://www.worldcupchampionships.com/2024-quarterly-finals and https://www.worldcupchampionships.com/world-cup-trading-championship-standings
- CME specifies MNQ as $2 times the Nasdaq-100 Index and a 0.25-point minimum tick worth $0.50: https://www.cmegroup.com/markets/equities/nasdaq/micro-e-mini-nasdaq-100.contractSpecs.html
