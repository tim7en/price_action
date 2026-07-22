# Nasdaq-100 1-Minute New York-Open Backtest

Generated 2026-07-22T01:04:43.684448+00:00. This is a standalone strategy with no macro or hierarchical-model inputs.

> **Data identity warning:** the CSV has no venue or contract metadata, and 94.1% of one-minute closes are off CME NQ's 0.25-point grid. Results are percentage-return research on an unverified Nasdaq-100 cash/CFD-like feed, not a CME NQ execution backtest.

## Holdout decision table

| scope | trades | sessions | win_rate | target_rate | stop_rate | average_gross_r | average_net_r | average_gross_return_bps | average_net_return_bps | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_gross_return | cumulative_net_return | annualized_net_return | max_drawdown | average_notional_fraction | median_risk_fraction_deployed | average_holding_bars | average_holding_minutes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| holdout_2025 | 30 | 27 | 0.4333 | 0.4333 | 0.5667 | 0.3000 | 0.1894 | 29.1245 | 20.2255 | 1.6048 | 1.3807 | 1.6364 | 0.0883 | 0.0597 | 0.0696 | -0.0373 | 8.8991 | 0.0098 | 5.0333 | 5.0333 |
| holdout_2025::setup::balance_value_rejection | 12 | 9 | 0.3333 | 0.3333 | 0.6667 | 0.0000 | -0.1108 | -1.3730 | -10.7146 | 0.9765 | 0.8338 | -0.0735 | -0.0025 | -0.0137 | -0.0192 | -0.0318 | 9.3416 | 0.0089 | 4.6667 | 4.6667 |
| holdout_2025::setup::imbalance_opening_range_breakout | 18 | 18 | 0.5000 | 0.5000 | 0.5000 | 0.5000 | 0.3896 | 49.4563 | 40.8522 | 2.1969 | 1.8968 | 2.8740 | 0.0911 | 0.0744 | 0.0868 | -0.0338 | 8.6041 | 0.0100 | 5.2778 | 5.2778 |
| holdout_2025::regime::balance | 12 | 9 | 0.3333 | 0.3333 | 0.6667 | 0.0000 | -0.1108 | -1.3730 | -10.7146 | 0.9765 | 0.8338 | -0.0735 | -0.0025 | -0.0137 | -0.0192 | -0.0318 | 9.3416 | 0.0089 | 4.6667 | 4.6667 |
| holdout_2025::regime::imbalance_down | 12 | 12 | 0.5000 | 0.5000 | 0.5000 | 0.5000 | 0.4149 | 53.0214 | 45.1152 | 2.1382 | 1.8945 | 3.3532 | 0.0642 | 0.0542 | 0.0631 | -0.0216 | 7.9062 | 0.0100 | 5.2500 | 5.2500 |
| holdout_2025::regime::imbalance_up | 6 | 6 | 0.5000 | 0.5000 | 0.5000 | 0.5000 | 0.3388 | 42.3260 | 32.3260 | 2.3747 | 1.9032 | 2.1163 | 0.0253 | 0.0192 | 0.0398 | -0.0125 | 10.0000 | 0.0067 | 5.3333 | 5.3333 |

## Full decision table

| scope | trades | sessions | win_rate | target_rate | stop_rate | average_gross_r | average_net_r | average_gross_return_bps | average_net_return_bps | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_gross_return | cumulative_net_return | annualized_net_return | max_drawdown | average_notional_fraction | median_risk_fraction_deployed | average_holding_bars | average_holding_minutes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | 78 | 72 | 0.3462 | 0.3462 | 0.6538 | 0.0385 | -0.0723 | 3.8462 | -5.2372 | 1.0677 | 0.9165 | 0.2117 | 0.0241 | -0.0460 | -0.0250 | -0.1330 | 9.0834 | 0.0094 | 5.2436 | 5.2436 |
| all::setup::balance_value_rejection | 28 | 25 | 0.3571 | 0.3571 | 0.6429 | 0.0714 | -0.0447 | 2.1524 | -7.3181 | 1.0385 | 0.8819 | 0.1136 | 0.0040 | -0.0223 | -0.0128 | -0.0419 | 9.4706 | 0.0088 | 5.0714 | 5.0714 |
| all::setup::imbalance_opening_range_breakout | 50 | 47 | 0.3400 | 0.3400 | 0.6600 | 0.0200 | -0.0877 | 4.7948 | -4.0718 | 1.0836 | 0.9356 | 0.2704 | 0.0200 | -0.0243 | -0.0131 | -0.1009 | 8.8666 | 0.0100 | 5.3400 | 5.3400 |
| all::regime::balance | 28 | 25 | 0.3571 | 0.3571 | 0.6429 | 0.0714 | -0.0447 | 2.1524 | -7.3181 | 1.0385 | 0.8819 | 0.1136 | 0.0040 | -0.0223 | -0.0128 | -0.0419 | 9.4706 | 0.0088 | 5.0714 | 5.0714 |
| all::regime::imbalance_down | 30 | 28 | 0.3667 | 0.3667 | 0.6333 | 0.1000 | 0.0103 | 11.6875 | 3.2032 | 1.1933 | 1.0486 | 0.6888 | 0.0326 | 0.0067 | 0.0038 | -0.0686 | 8.4843 | 0.0100 | 4.5333 | 4.5333 |
| all::regime::imbalance_up | 20 | 19 | 0.3000 | 0.3000 | 0.7000 | -0.1000 | -0.2348 | -5.5443 | -14.9844 | 0.8947 | 0.7467 | -0.2937 | -0.0122 | -0.0307 | -0.0195 | -0.0651 | 9.4401 | 0.0075 | 6.5500 | 6.5500 |
| development_2024 | 48 | 45 | 0.2917 | 0.2917 | 0.7083 | -0.1250 | -0.2358 | -11.9527 | -21.1513 | 0.8079 | 0.6924 | -0.6497 | -0.0590 | -0.0998 | -0.1030 | -0.1330 | 9.1986 | 0.0093 | 5.3750 | 5.3750 |
| development_2024::setup::balance_value_rejection | 16 | 16 | 0.3750 | 0.3750 | 0.6250 | 0.1250 | 0.0048 | 4.7965 | -4.7708 | 1.0887 | 0.9206 | 0.2507 | 0.0066 | -0.0087 | -0.0103 | -0.0392 | 9.5673 | 0.0087 | 5.3750 | 5.3750 |
| development_2024::setup::imbalance_opening_range_breakout | 32 | 29 | 0.2500 | 0.2500 | 0.7500 | -0.2500 | -0.3562 | -20.3273 | -29.3416 | 0.6935 | 0.5986 | -1.1275 | -0.0652 | -0.0918 | -0.0948 | -0.1009 | 9.0143 | 0.0099 | 5.3750 | 5.3750 |
| development_2024::regime::balance | 16 | 16 | 0.3750 | 0.3750 | 0.6250 | 0.1250 | 0.0048 | 4.7965 | -4.7708 | 1.0887 | 0.9206 | 0.2507 | 0.0066 | -0.0087 | -0.0103 | -0.0392 | 9.5673 | 0.0087 | 5.3750 | 5.3750 |
| development_2024::regime::imbalance_down | 18 | 16 | 0.2778 | 0.2778 | 0.7222 | -0.1667 | -0.2594 | -15.8684 | -24.7381 | 0.7723 | 0.6751 | -0.8945 | -0.0297 | -0.0451 | -0.0522 | -0.0686 | 8.8698 | 0.0100 | 4.0556 | 4.0556 |
| development_2024::regime::imbalance_up | 14 | 13 | 0.2143 | 0.2143 | 0.7857 | -0.3571 | -0.4806 | -26.0602 | -35.2603 | 0.5796 | 0.4903 | -1.4163 | -0.0366 | -0.0490 | -0.0520 | -0.0567 | 9.2001 | 0.0076 | 7.0714 | 7.0714 |
| holdout_2025 | 30 | 27 | 0.4333 | 0.4333 | 0.5667 | 0.3000 | 0.1894 | 29.1245 | 20.2255 | 1.6048 | 1.3807 | 1.6364 | 0.0883 | 0.0597 | 0.0696 | -0.0373 | 8.8991 | 0.0098 | 5.0333 | 5.0333 |
| holdout_2025::setup::balance_value_rejection | 12 | 9 | 0.3333 | 0.3333 | 0.6667 | 0.0000 | -0.1108 | -1.3730 | -10.7146 | 0.9765 | 0.8338 | -0.0735 | -0.0025 | -0.0137 | -0.0192 | -0.0318 | 9.3416 | 0.0089 | 4.6667 | 4.6667 |
| holdout_2025::setup::imbalance_opening_range_breakout | 18 | 18 | 0.5000 | 0.5000 | 0.5000 | 0.5000 | 0.3896 | 49.4563 | 40.8522 | 2.1969 | 1.8968 | 2.8740 | 0.0911 | 0.0744 | 0.0868 | -0.0338 | 8.6041 | 0.0100 | 5.2778 | 5.2778 |
| holdout_2025::regime::balance | 12 | 9 | 0.3333 | 0.3333 | 0.6667 | 0.0000 | -0.1108 | -1.3730 | -10.7146 | 0.9765 | 0.8338 | -0.0735 | -0.0025 | -0.0137 | -0.0192 | -0.0318 | 9.3416 | 0.0089 | 4.6667 | 4.6667 |
| holdout_2025::regime::imbalance_down | 12 | 12 | 0.5000 | 0.5000 | 0.5000 | 0.5000 | 0.4149 | 53.0214 | 45.1152 | 2.1382 | 1.8945 | 3.3532 | 0.0642 | 0.0542 | 0.0631 | -0.0216 | 7.9062 | 0.0100 | 5.2500 | 5.2500 |
| holdout_2025::regime::imbalance_up | 6 | 6 | 0.5000 | 0.5000 | 0.5000 | 0.5000 | 0.3388 | 42.3260 | 32.3260 | 2.3747 | 1.9032 | 2.1163 | 0.0253 | 0.0192 | 0.0398 | -0.0125 | 10.0000 | 0.0067 | 5.3333 | 5.3333 |

## Holdout cost sensitivity

| scope | setup | one_way_cost_bps | trades | win_rate | average_net_return_bps | cumulative_net_return | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- |
| holdout_2025 | all | 0.0000 | 30 | 0.4333 | 29.1245 | 0.0883 | -0.0338 |
| holdout_2025 | all | 0.1000 | 30 | 0.4333 | 27.3447 | 0.0825 | -0.0345 |
| holdout_2025 | all | 0.2500 | 30 | 0.4333 | 24.6750 | 0.0739 | -0.0356 |
| holdout_2025 | all | 0.5000 | 30 | 0.4333 | 20.2255 | 0.0597 | -0.0373 |
| holdout_2025 | all | 1.0000 | 30 | 0.4333 | 11.3264 | 0.0318 | -0.0408 |
| holdout_2025 | all | 1.5000 | 30 | 0.4333 | 2.4273 | 0.0047 | -0.0492 |
| holdout_2025 | all | 2.0000 | 30 | 0.4333 | -6.4718 | -0.0218 | -0.0596 |
| holdout_2025 | all | 3.0000 | 30 | 0.4333 | -24.2700 | -0.0727 | -0.1005 |
| holdout_2025 | all | 5.0000 | 30 | 0.4000 | -59.8664 | -0.1670 | -0.1869 |
| holdout_2025 | balance_value_rejection | 0.0000 | 12 | 0.3333 | -1.3730 | -0.0025 | -0.0296 |
| holdout_2025 | balance_value_rejection | 0.1000 | 12 | 0.3333 | -3.2413 | -0.0048 | -0.0300 |
| holdout_2025 | balance_value_rejection | 0.2500 | 12 | 0.3333 | -6.0438 | -0.0081 | -0.0307 |
| holdout_2025 | balance_value_rejection | 0.5000 | 12 | 0.3333 | -10.7146 | -0.0137 | -0.0318 |
| holdout_2025 | balance_value_rejection | 1.0000 | 12 | 0.3333 | -20.0562 | -0.0247 | -0.0341 |
| holdout_2025 | balance_value_rejection | 1.5000 | 12 | 0.3333 | -29.3978 | -0.0356 | -0.0363 |
| holdout_2025 | balance_value_rejection | 2.0000 | 12 | 0.3333 | -38.7394 | -0.0464 | -0.0385 |
| holdout_2025 | balance_value_rejection | 3.0000 | 12 | 0.3333 | -57.4226 | -0.0676 | -0.0533 |
| holdout_2025 | balance_value_rejection | 5.0000 | 12 | 0.3333 | -94.7889 | -0.1088 | -0.0914 |
| holdout_2025 | imbalance_opening_range_breakout | 0.0000 | 18 | 0.5000 | 49.4563 | 0.0911 | -0.0302 |
| holdout_2025 | imbalance_opening_range_breakout | 0.1000 | 18 | 0.5000 | 47.7354 | 0.0877 | -0.0310 |
| holdout_2025 | imbalance_opening_range_breakout | 0.2500 | 18 | 0.5000 | 45.1542 | 0.0827 | -0.0320 |
| holdout_2025 | imbalance_opening_range_breakout | 0.5000 | 18 | 0.5000 | 40.8522 | 0.0744 | -0.0338 |
| holdout_2025 | imbalance_opening_range_breakout | 1.0000 | 18 | 0.5000 | 32.2481 | 0.0579 | -0.0374 |
| holdout_2025 | imbalance_opening_range_breakout | 1.5000 | 18 | 0.5000 | 23.6440 | 0.0417 | -0.0410 |
| holdout_2025 | imbalance_opening_range_breakout | 2.0000 | 18 | 0.5000 | 15.0399 | 0.0257 | -0.0446 |
| holdout_2025 | imbalance_opening_range_breakout | 3.0000 | 18 | 0.5000 | -2.1683 | -0.0055 | -0.0517 |
| holdout_2025 | imbalance_opening_range_breakout | 5.0000 | 18 | 0.4444 | -36.5847 | -0.0654 | -0.0877 |

## Session-block bootstrap

| scope | setup | sessions | mean_session_return_bps | bootstrap_mean_ci_low_bps | bootstrap_mean_ci_high_bps | bootstrap_probability_mean_positive |
| --- | --- | --- | --- | --- | --- | --- |
| all | all | 72 | -5.6194 | -36.7092 | 25.2536 | 0.3592 |
| all | balance_value_rejection | 25 | -8.1608 | -58.6062 | 44.0518 | 0.3756 |
| all | imbalance_opening_range_breakout | 47 | -4.2675 | -43.9556 | 35.6968 | 0.4128 |
| development_2024 | all | 45 | -22.4943 | -58.4121 | 15.4157 | 0.1196 |
| development_2024 | balance_value_rejection | 16 | -4.7708 | -61.3734 | 55.2558 | 0.4352 |
| development_2024 | imbalance_opening_range_breakout | 29 | -32.2728 | -78.6245 | 17.3039 | 0.1034 |
| holdout_2025 | all | 27 | 22.5056 | -31.3853 | 75.4123 | 0.8044 |
| holdout_2025 | balance_value_rejection | 9 | -14.1875 | -109.1512 | 80.3245 | 0.3962 |
| holdout_2025 | imbalance_opening_range_breakout | 18 | 40.8522 | -20.8388 | 100.6322 | 0.9008 |

## Quarterly stability

| quarter | setup | trades | win_rate | average_gross_return_bps | average_net_return_bps | break_even_one_way_cost_bps | cumulative_net_return | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2024Q1 | all | 12 | 0.1667 | -40.8406 | -50.3873 | -2.1390 | -0.0594 | -0.0634 |
| 2024Q1 | balance_value_rejection | 4 | 0.0000 | -88.7544 | -98.6961 | -4.4637 | -0.0389 | -0.0282 |
| 2024Q1 | imbalance_opening_range_breakout | 8 | 0.2500 | -16.8837 | -26.2329 | -0.9030 | -0.0214 | -0.0255 |
| 2024Q2 | all | 6 | 0.5000 | 27.8989 | 17.8989 | 1.3949 | 0.0104 | -0.0167 |
| 2024Q2 | balance_value_rejection | 5 | 0.6000 | 51.7783 | 41.7783 | 2.5889 | 0.0208 | -0.0105 |
| 2024Q2 | imbalance_opening_range_breakout | 1 | 0.0000 | -91.4980 | -101.4980 | -4.5749 | -0.0101 | 0.0000 |
| 2024Q3 | all | 19 | 0.2105 | -35.7933 | -44.2861 | -2.1073 | -0.0820 | -0.0870 |
| 2024Q3 | balance_value_rejection | 4 | 0.2500 | -26.0829 | -35.3384 | -1.4090 | -0.0143 | -0.0216 |
| 2024Q3 | imbalance_opening_range_breakout | 15 | 0.2000 | -38.3828 | -46.6722 | -2.3152 | -0.0687 | -0.0669 |
| 2024Q4 | all | 11 | 0.4545 | 39.0035 | 29.4025 | 2.0312 | 0.0319 | -0.0314 |
| 2024Q4 | balance_value_rejection | 3 | 0.6667 | 92.4005 | 83.6379 | 5.2724 | 0.0250 | -0.0104 |
| 2024Q4 | imbalance_opening_range_breakout | 8 | 0.3750 | 18.9796 | 9.0642 | 0.9571 | 0.0067 | -0.0314 |
| 2025Q1 | all | 7 | 0.4286 | 32.8585 | 24.7423 | 2.0242 | 0.0167 | -0.0295 |
| 2025Q1 | balance_value_rejection | 1 | 0.0000 | -91.0446 | -101.0446 | -4.5522 | -0.0101 | 0.0000 |
| 2025Q1 | imbalance_opening_range_breakout | 6 | 0.5000 | 53.5091 | 45.7067 | 3.4290 | 0.0271 | -0.0196 |
| 2025Q2 | all | 11 | 0.6364 | 73.3960 | 64.3362 | 4.0506 | 0.0721 | -0.0318 |
| 2025Q2 | balance_value_rejection | 7 | 0.4286 | 24.0943 | 15.2230 | 1.3580 | 0.0101 | -0.0214 |
| 2025Q2 | imbalance_opening_range_breakout | 4 | 1.0000 | 159.6739 | 150.2842 | 8.5026 | 0.0614 | 0.0000 |
| 2025Q3 | all | 8 | 0.3750 | 22.3695 | 13.0682 | 1.2025 | 0.0099 | -0.0283 |
| 2025Q3 | balance_value_rejection | 1 | 1.0000 | 148.4931 | 138.4931 | 7.4247 | 0.0138 | 0.0000 |
| 2025Q3 | imbalance_opening_range_breakout | 7 | 0.2857 | 4.3518 | -4.8497 | 0.2365 | -0.0039 | -0.0283 |
| 2025Q4 | all | 4 | 0.0000 | -85.6462 | -94.6688 | -4.7462 | -0.0373 | -0.0300 |
| 2025Q4 | balance_value_rejection | 3 | 0.0000 | -80.8616 | -90.8616 | -4.0431 | -0.0270 | -0.0196 |
| 2025Q4 | imbalance_opening_range_breakout | 1 | 0.0000 | -100.0000 | -106.0905 | -8.2096 | -0.0106 | 0.0000 |

## Long/short stability

| scope | trades | sessions | win_rate | target_rate | stop_rate | average_gross_r | average_net_r | average_gross_return_bps | average_net_return_bps | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_gross_return | cumulative_net_return | annualized_net_return | max_drawdown | average_notional_fraction | median_risk_fraction_deployed | average_holding_bars | average_holding_minutes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all::side::long | 30 | 28 | 0.3000 | 0.3000 | 0.7000 | -0.1000 | -0.2301 | -6.7936 | -16.4125 | 0.8767 | 0.7344 | -0.3531 | -0.0220 | -0.0499 | -0.0319 | -0.0795 | 9.6189 | 0.0081 | 7.2333 | 7.2333 |
| all::side::short | 48 | 44 | 0.3750 | 0.3750 | 0.6250 | 0.1250 | 0.0263 | 10.4961 | 1.7474 | 1.1813 | 1.0276 | 0.5999 | 0.0471 | 0.0041 | 0.0023 | -0.0723 | 8.7487 | 0.0100 | 4.0000 | 4.0000 |
| development_2024::side::long | 20 | 19 | 0.2000 | 0.2000 | 0.8000 | -0.4000 | -0.5224 | -31.3212 | -40.7496 | 0.5185 | 0.4386 | -1.6610 | -0.0618 | -0.0794 | -0.0843 | -0.0712 | 9.4284 | 0.0087 | 7.8500 | 7.8500 |
| development_2024::side::short | 28 | 26 | 0.3571 | 0.3571 | 0.6429 | 0.0714 | -0.0311 | 1.8819 | -7.1526 | 1.0312 | 0.8917 | 0.1042 | 0.0029 | -0.0221 | -0.0256 | -0.0723 | 9.0345 | 0.0100 | 3.6071 | 3.6071 |
| holdout_2025::side::long | 10 | 9 | 0.5000 | 0.5000 | 0.5000 | 0.5000 | 0.3547 | 42.2616 | 32.2616 | 2.2006 | 1.8025 | 2.1131 | 0.0424 | 0.0320 | 0.0669 | -0.0125 | 10.0000 | 0.0077 | 6.0000 | 6.0000 |
| holdout_2025::side::short | 20 | 18 | 0.4000 | 0.4000 | 0.6000 | 0.2000 | 0.1068 | 22.5560 | 14.2074 | 1.4129 | 1.2384 | 1.3509 | 0.0441 | 0.0268 | 0.0311 | -0.0373 | 8.3486 | 0.0100 | 4.5500 | 4.5500 |

## Auction-regime counts

| scope | day_regime | sessions |
| --- | --- | --- |
| development_2024 | balance | 158 |
| development_2024 | imbalance_down | 31 |
| development_2024 | imbalance_up | 55 |
| holdout_2025 | balance | 150 |
| holdout_2025 | imbalance_down | 28 |
| holdout_2025 | imbalance_up | 52 |

## Unconditional timing audit

| scope | phase | observations | mean_return_bps | median_return_bps | positive_rate | mean_absolute_return_bps | mean_range_bps | mean_return_tstat |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | after_close_30m | 479 | 0.3482 | -0.7362 | 0.4843 | 12.0515 | 25.8007 | 0.3745 |
| all | closing_last_30m | 484 | 0.5236 | 0.7991 | 0.5186 | 18.9998 | 37.4942 | 0.3998 |
| all | opening_first_30m | 484 | -0.9836 | 0.3190 | 0.5000 | 31.0501 | 58.5452 | -0.5190 |
| all | opening_followthrough_30m | 484 | 1.1718 | 2.9429 | 0.5393 | 24.5875 | 50.7071 | 0.7652 |
| development_2024 | after_close_30m | 248 | 0.1309 | -0.3368 | 0.4919 | 11.7179 | 24.2994 | 0.1101 |
| development_2024 | closing_last_30m | 251 | -0.3725 | 0.3050 | 0.5100 | 17.5075 | 34.7606 | -0.2191 |
| development_2024 | opening_first_30m | 251 | -2.3128 | -1.6405 | 0.4661 | 27.3944 | 52.8350 | -0.9955 |
| development_2024 | opening_followthrough_30m | 251 | 0.2518 | 1.1886 | 0.5139 | 23.6060 | 47.2250 | 0.1286 |
| holdout_2025 | after_close_30m | 231 | 0.5814 | -1.0603 | 0.4762 | 12.4097 | 27.4125 | 0.4017 |
| holdout_2025 | closing_last_30m | 233 | 1.4890 | 0.8802 | 0.5279 | 20.6074 | 40.4390 | 0.7396 |
| holdout_2025 | opening_first_30m | 233 | 0.4482 | 4.3184 | 0.5365 | 34.9883 | 64.6966 | 0.1474 |
| holdout_2025 | opening_followthrough_30m | 233 | 2.1628 | 4.2087 | 0.5665 | 25.6449 | 54.4582 | 0.9072 |

## Signal funnel

| stage | observations | share_of_execution_bars |
| --- | --- | --- |
| execution_window_bars | 14220 | 1.0000 |
| imbalance_regime_bars | 4980 | 0.3502 |
| balance_regime_bars | 9240 | 0.6498 |
| aggressive_expansion | 1030 | 0.0724 |
| absorption_proxy | 0 | 0.0000 |
| recent_absorption_proxy | 0 | 0.0000 |
| accumulation_proxy | 63 | 0.0044 |
| recent_absorption_and_accumulation | 0 | 0.0000 |
| strict_absorption_signals | 0 | 0.0000 |
| imbalance_orb_signals | 50 | 0.0035 |
| balance_rejection_signals | 32 | 0.0023 |

## Strict absorption diagnostics

| scope | bars | indicator_eligible_bars | volume_above_2x_average | range_below_0_3_atr | strict_absorption_intersection | absorption_given_volume_share | absorption_given_narrow_range_share | recent_absorption | three_bar_accumulation | recent_absorption_and_accumulation | aggressive_expansion | strict_signals |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all_feed_bars | 681646 | 681596 | 32299 | 2242 | 3 | 0.0001 | 0.0013 | 18 | 8456 | 7 | 72816 | 0 |
| complete_regular_session_bars | 185130 | 185130 | 11309 | 30 | 0 | 0.0000 | 0.0000 | 0 | 838 | 0 | 17288 | 0 |
| first_30m_bars | 14310 | 14310 | 7577 | 1 | 0 | 0.0000 | 0.0000 | 0 | 39 | 0 | 5708 | 0 |
| execution_30m_bars | 14220 | 14220 | 168 | 1 | 0 | 0.0000 | 0.0000 | 0 | 63 | 0 | 1030 | 0 |

## Predeclared causal rules

- The raw one-minute file is aggregated into complete 1-minute bars; incomplete groups are dropped.
- XNYS calendars determine the 09:30 New York cash open, holidays, DST and early closes.
- The prior completed regular session supplies a 24-row, 70% typical-price volume-profile approximation.
- The first 30 minutes is observation only. An opening close outside the prior value area, aligned with opening return, session VWAP and close-location volume proxy, defines imbalance; otherwise the day is balance.
- During minutes 30-60, imbalance trades require a fresh opening-range break in the regime direction. Balance trades require rejection at the prior value-area edge.
- The strict Triple-A proxy requires prior 2x-volume/0.3-ATR absorption, three-bar accumulation at a prior-session or opening-range level, then aligned aggressive expansion through that accumulation.
- Both setups require aligned smoothed delta proxy, VWAP and aggressive range/volume expansion. These are OHLCV proxies, not bid/ask order flow.
- Signals enter at the next 1-minute open. Stops are one ATR, targets are 2R, same-bar stop/target ambiguity resolves to the stop, and positions close no later than the end of the execution window.
- Risk is 1.00% of current equity at the stop, capped at 10.0x notional. Trading stops after three net losses in the session.
- 2024 is development and 2025 is the untouched temporal holdout. No parameters are selected using holdout performance.

## Limitations

- No symbol, source, venue, contract, expiry or roll metadata was supplied; futures contract sizing, tick rounding and broker margin cannot be modeled honestly.
- Volume provenance is unknown and may be CFD tick volume. Volume profile, delta and absorption are therefore proxies.
- 1-minute OHLCV cannot reveal aggressor side, resting liquidity, queue position, partial fills or true footprint/CVD.
- The configured 0.50 bps one-way execution cost is a scenario, not a measured spread/commission. Use the sensitivity table until actual venue costs are supplied.
- The sample spans only 2024 through 5 December 2025. Even holdout results need a fresh forward or genuinely identified NQ dataset before capital deployment.
