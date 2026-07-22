# NASDAQ POC hierarchical trend strategy

## Research conclusion

The strongest entry evidence in the repository remains the frozen multi-session POC-migration plus one-minute acceptance ledger, not generic ORB frequency. Its context-free 0.25%-risk test previously produced PF 1.58 at 0.50 bps per side, but the ledger has only 89 trades and was selected with visibility into both years.

This extension adds only close-confirmed information: previous completed RTH high/low/POC/VAH/VAL, exact 30-minute opening range, session VWAP, signal-bar impulse, relative volume, and already-lagged macro/daily alignment. Development thresholds use 2024 only; 2025 is unchanged validation. Methodology audit: **PASS**.

## Core stability

| candidate | period | trades | win_rate | profit_factor | mean_net_r | runner_rate_mfe_ge_1r | whipsaw_rate_mfe_lt_0_25r |
| --- | --- | --- | --- | --- | --- | --- | --- |
| core_poc_ledger | development_2024 | 45 | 0.5778 | 1.7362 | 0.1407 | 0.1778 | 0.2444 |
| core_poc_ledger | validation_2025 | 44 | 0.5455 | 1.4484 | 0.1068 | 0.2273 | 0.2500 |

## Development-ranked hierarchy candidates and 2025 validation

| development_rank | candidate | development_trades | development_profit_factor | development_mean_net_r | development_runner_rate | development_whipsaw_rate | validation_trades | validation_profit_factor | validation_mean_net_r | validation_runner_rate | validation_whipsaw_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | opening_range_break | 19 | 4.8806 | 0.2706 | 0.1579 | 0.1053 | 16 | 1.1651 | 0.0454 | 0.1875 | 0.3125 |
| 2 | directional_impulse | 23 | 3.3593 | 0.2674 | 0.1739 | 0.2174 | 20 | 1.1046 | 0.0217 | 0.2000 | 0.1500 |
| 3 | score_ge_4 | 15 | 3.2726 | 0.2115 | 0.1333 | 0.1333 | 7 | 1.4348 | 0.1054 | 0.2857 | 0.2857 |
| 4 | score_ge_3 | 25 | 2.6476 | 0.2109 | 0.1600 | 0.2000 | 21 | 1.8709 | 0.1368 | 0.1429 | 0.2381 |
| 5 | prior_poc_plus_vwap | 27 | 1.6043 | 0.1067 | 0.1481 | 0.2593 | 26 | 1.6551 | 0.1391 | 0.1923 | 0.1923 |

Candidates profitable in both periods: **5**. A high score is not automatically useful; each extra gate must improve validation expectancy rather than merely increase historical selectivity.

## Individual validation layers

| feature | period | trades | profit_factor | mean_net_r | runner_rate_mfe_ge_1r | whipsaw_rate_mfe_lt_0_25r |
| --- | --- | --- | --- | --- | --- | --- |
| macro_daily_gate | development_2024 | 30 | 2.6669 | 0.2328 | 0.1667 | 0.1667 |
| golden_cross_gate | development_2024 | 32 | 2.8482 | 0.2478 | 0.1875 | 0.1875 |
| poc_location_gate | development_2024 | 27 | 1.6043 | 0.1067 | 0.1481 | 0.2593 |
| opening_break_gate | development_2024 | 19 | 4.8806 | 0.2706 | 0.1579 | 0.1053 |
| prior_extreme_gate | development_2024 | 2 | 9.7725 | 0.4441 | 0.5000 | 0.5000 |
| impulse_gate | development_2024 | 23 | 3.3593 | 0.2674 | 0.1739 | 0.2174 |
| volume_gate | development_2024 | 23 | 0.7617 | -0.0675 | 0.0870 | 0.3478 |
| compact_opening_gate | development_2024 | 23 | 1.4326 | 0.0923 | 0.1739 | 0.3043 |
| macro_daily_gate | validation_2025 | 13 | 1.8989 | 0.1915 | 0.1538 | 0.3846 |
| golden_cross_gate | validation_2025 | 19 | 1.2859 | 0.0804 | 0.1579 | 0.3158 |
| poc_location_gate | validation_2025 | 26 | 1.6551 | 0.1391 | 0.1923 | 0.1923 |
| opening_break_gate | validation_2025 | 16 | 1.1651 | 0.0454 | 0.1875 | 0.3125 |
| prior_extreme_gate | validation_2025 | 0 | nan | nan | nan | nan |
| impulse_gate | validation_2025 | 20 | 1.1046 | 0.0217 | 0.2000 | 0.1500 |
| volume_gate | validation_2025 | 32 | 1.3835 | 0.0795 | 0.1562 | 0.3125 |
| compact_opening_gate | validation_2025 | 31 | 1.6833 | 0.1385 | 0.2258 | 0.2903 |

## Score behavior

| period | hierarchy_score | trades | win_rate | profit_factor | mean_net_r | sum_net_r | runner_rate_mfe_ge_1r | runner_profit_conversion | whipsaw_rate_mfe_lt_0_25r | average_holding_minutes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| development_2024 | 0 | 2 | 0.5000 | 2.0415 | 0.1694 | 0.3388 | 0.5000 | 1.0000 | 0.0000 | 5.0000 |
| development_2024 | 1 | 4 | 0.5000 | 1.2012 | 0.0825 | 0.3300 | 0.2500 | 1.0000 | 0.2500 | 5.0000 |
| development_2024 | 2 | 14 | 0.5714 | 1.1135 | 0.0278 | 0.3898 | 0.1429 | 1.0000 | 0.3571 | 4.7857 |
| development_2024 | 3 | 10 | 0.4000 | 2.1643 | 0.2101 | 2.1012 | 0.2000 | 1.0000 | 0.3000 | 4.5000 |
| development_2024 | 4 | 13 | 0.6923 | 2.9903 | 0.2137 | 2.7778 | 0.1538 | 1.0000 | 0.1538 | 5.0000 |
| development_2024 | 5 | 2 | 1.0000 | inf | 0.1970 | 0.3940 | 0.0000 | nan | 0.0000 | 5.0000 |
| validation_2025 | 0 | 3 | 1.0000 | inf | 0.9468 | 2.8404 | 1.0000 | 1.0000 | 0.0000 | 5.0000 |
| validation_2025 | 1 | 3 | 0.0000 | 0.0000 | -0.8276 | -2.4829 | 0.0000 | nan | 0.3333 | 3.0000 |
| validation_2025 | 2 | 17 | 0.4706 | 1.3128 | 0.0865 | 1.4707 | 0.2353 | 1.0000 | 0.2941 | 4.7647 |
| validation_2025 | 3 | 14 | 0.6429 | 2.3328 | 0.1525 | 2.1346 | 0.0714 | 1.0000 | 0.2143 | 5.0000 |
| validation_2025 | 4 | 7 | 0.5714 | 1.4348 | 0.1054 | 0.7375 | 0.2857 | 1.0000 | 0.2857 | 4.8571 |

## Conservative hierarchy sizing diagnostic

| variant | period | trades_available | trades_sized | average_risk_fraction | cumulative_return | maximum_drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| fixed_0.25pct | all | 89 | 89 | 0.0025 | 0.0278 | -0.0078 |
| fixed_0.25pct | development_2024 | 45 | 45 | 0.0025 | 0.0159 | -0.0057 |
| fixed_0.25pct | validation_2025 | 44 | 44 | 0.0025 | 0.0117 | -0.0078 |
| hierarchy_risk | all | 89 | 46 | 0.0007 | 0.0105 | -0.0025 |
| hierarchy_risk | development_2024 | 45 | 25 | 0.0008 | 0.0073 | -0.0014 |
| hierarchy_risk | validation_2025 | 44 | 21 | 0.0006 | 0.0032 | -0.0025 |

The sizing map is deliberately non-aggressive: score below 3 receives no position; score 3 risks 0.10%, score 4 risks 0.15%, and score 5-6 risks at most 0.25%. It is a governance diagnostic, not permission for live capital.

## Proposed hierarchy

1. **Direction:** last completed macro/daily state controls risk, not entry. Golden-cross state is a slow prior rather than a one-minute trigger.
2. **Location:** require the POC-migration/acceptance core; use session VWAP and previous-session POC/VAH/VAL to define the area of interest.
3. **Auction structure:** classify price as inside yesterday's range, testing an extreme, or accepting beyond the previous high/low. Because actual extreme breaks were too rare to validate, use the levels primarily for location, targets, and invalidation rather than as a mandatory entry gate.
4. **Trigger:** exact opening-range break or POC acceptance on a confirmed one-minute close.
5. **Aggression:** directional candle impulse can confirm the trigger. Relative volume is only a bonus because its sign was unstable across periods; five-minute OHLCV cannot substitute for true footprint delta.
6. **Risk:** maximum 0.25% initial-stop risk, no fixed 20x/40x exposure, three-loss/-0.75% daily halt.
7. **Management:** retain the cost-covered trailing logic only after favorable progress; next research should test an early failure exit for trades that lose VWAP/POC acceptance before reaching 0.25R MFE.

## Frozen 2024 thresholds

| feature | development_threshold |
| --- | --- |
| directional_impulse_atr_median | 0.3306 |
| volume_strength_median | 1.0025 |
| opening_width_atr_median | 8.6828 |

## Limits

- Previous-day fields are shifted by one completed session and never current-session final values.
- Signal candle OHLCV is known at its close; the frozen ledger enters one minute later.
- Candidate filtering is attribution on an existing ledger, not a fresh broker replay. It should guide a new frozen entry implementation, not be treated as deployable performance.
- The NASDAQ-like source remains unverified and inconsistent with the CME NQ tick grid.
