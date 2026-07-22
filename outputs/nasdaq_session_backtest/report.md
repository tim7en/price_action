# Nasdaq-100 Five-Minute New York-Open Backtest

Generated 2026-07-22T00:53:06.613223+00:00. This is a standalone strategy with no macro or hierarchical-model inputs.

> **Data identity warning:** the CSV has no venue or contract metadata, and 94.1% of one-minute closes are off CME NQ's 0.25-point grid. Results are percentage-return research on an unverified Nasdaq-100 cash/CFD-like feed, not a CME NQ execution backtest.

## Holdout decision table

| scope | trades | sessions | win_rate | target_rate | stop_rate | average_gross_r | average_net_r | average_gross_return_bps | average_net_return_bps | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_net_return | annualized_net_return | max_drawdown | average_notional_fraction | median_risk_fraction_deployed | average_holding_bars |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| holdout_2025 | 64 | 62 | 0.4688 | 0.0938 | 0.3750 | 0.0370 | -0.0264 | 3.7040 | -2.5824 | 1.0881 | 0.9429 | 0.2946 | -0.0195 | -0.0214 | -0.0697 | 6.2863 | 0.0100 | 3.1406 |
| holdout_2025::setup::balance_value_rejection | 26 | 25 | 0.3846 | 0.1154 | 0.4231 | -0.1009 | -0.1616 | -10.0871 | -16.1610 | 0.8018 | 0.7041 | -0.8304 | -0.0425 | -0.0483 | -0.0542 | 6.0739 | 0.0100 | 2.5769 |
| holdout_2025::setup::imbalance_opening_range_breakout | 38 | 37 | 0.5263 | 0.0789 | 0.3421 | 0.1314 | 0.0661 | 13.1400 | 6.7083 | 1.3654 | 1.1727 | 1.0215 | 0.0240 | 0.0264 | -0.0518 | 6.4317 | 0.0100 | 3.5263 |
| holdout_2025::regime::balance | 26 | 25 | 0.3846 | 0.1154 | 0.4231 | -0.1009 | -0.1616 | -10.0871 | -16.1610 | 0.8018 | 0.7041 | -0.8304 | -0.0425 | -0.0483 | -0.0542 | 6.0739 | 0.0100 | 2.5769 |
| holdout_2025::regime::imbalance_down | 11 | 10 | 0.3636 | 0.0909 | 0.4545 | -0.1779 | -0.2245 | -17.7890 | -22.4487 | 0.6570 | 0.5914 | -1.9088 | -0.0249 | -0.0288 | -0.0309 | 4.6597 | 0.0100 | 3.0909 |
| holdout_2025::regime::imbalance_up | 27 | 27 | 0.5926 | 0.0741 | 0.2963 | 0.2574 | 0.1845 | 25.7407 | 18.5871 | 1.8731 | 1.5760 | 1.7991 | 0.0502 | 0.0552 | -0.0302 | 7.1536 | 0.0100 | 3.7037 |

## Full decision table

| scope | trades | sessions | win_rate | target_rate | stop_rate | average_gross_r | average_net_r | average_gross_return_bps | average_net_return_bps | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_net_return | annualized_net_return | max_drawdown | average_notional_fraction | median_risk_fraction_deployed | average_holding_bars |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | 131 | 126 | 0.4733 | 0.1374 | 0.3740 | 0.1051 | 0.0394 | 10.6978 | 4.1875 | 1.2622 | 1.0948 | 0.8216 | 0.0486 | 0.0251 | -0.0718 | 6.5103 | 0.0100 | 2.9160 |
| all::setup::balance_value_rejection | 53 | 52 | 0.5094 | 0.2075 | 0.3774 | 0.1743 | 0.1098 | 17.4341 | 10.9845 | 1.4133 | 1.2427 | 1.3516 | 0.0562 | 0.0290 | -0.0627 | 6.4496 | 0.0100 | 2.6226 |
| all::setup::imbalance_opening_range_breakout | 78 | 74 | 0.4487 | 0.0897 | 0.3718 | 0.0581 | -0.0085 | 6.1207 | -0.4310 | 1.1535 | 0.9901 | 0.4671 | -0.0072 | -0.0038 | -0.0726 | 6.5516 | 0.0100 | 3.1154 |
| all::regime::balance | 53 | 52 | 0.5094 | 0.2075 | 0.3774 | 0.1743 | 0.1098 | 17.4341 | 10.9845 | 1.4133 | 1.2427 | 1.3516 | 0.0562 | 0.0290 | -0.0627 | 6.4496 | 0.0100 | 2.6226 |
| all::regime::imbalance_down | 29 | 27 | 0.4828 | 0.1724 | 0.3793 | 0.1876 | 0.1341 | 18.7590 | 13.4088 | 1.4439 | 1.2978 | 1.7531 | 0.0377 | 0.0219 | -0.0309 | 5.3502 | 0.0100 | 2.7931 |
| all::regime::imbalance_up | 49 | 47 | 0.4286 | 0.0408 | 0.3673 | -0.0186 | -0.0928 | -1.3592 | -8.6218 | 0.9646 | 0.7972 | -0.0936 | -0.0432 | -0.0229 | -0.1028 | 7.2627 | 0.0100 | 3.3061 |
| development_2024 | 67 | 64 | 0.4776 | 0.1791 | 0.3731 | 0.1701 | 0.1022 | 17.3785 | 10.6543 | 1.4386 | 1.2468 | 1.2922 | 0.0695 | 0.0705 | -0.0718 | 6.7243 | 0.0100 | 2.7015 |
| development_2024::setup::balance_value_rejection | 27 | 27 | 0.6296 | 0.2963 | 0.3333 | 0.4393 | 0.3712 | 43.9359 | 37.1246 | 2.3004 | 2.0241 | 3.2252 | 0.1031 | 0.1085 | -0.0257 | 6.8113 | 0.0100 | 2.6667 |
| development_2024::setup::imbalance_opening_range_breakout | 40 | 37 | 0.3750 | 0.1000 | 0.4000 | -0.0115 | -0.0793 | -0.5477 | -7.2132 | 0.9874 | 0.8492 | -0.0411 | -0.0305 | -0.0312 | -0.0726 | 6.6655 | 0.0100 | 2.7250 |
| development_2024::regime::balance | 27 | 27 | 0.6296 | 0.2963 | 0.3333 | 0.4393 | 0.3712 | 43.9359 | 37.1246 | 2.3004 | 2.0241 | 3.2252 | 0.1031 | 0.1085 | -0.0257 | 6.8113 | 0.0100 | 2.6667 |
| development_2024::regime::imbalance_down | 18 | 17 | 0.5556 | 0.2222 | 0.3333 | 0.4109 | 0.3532 | 41.0939 | 35.3217 | 2.1294 | 1.9066 | 3.5597 | 0.0642 | 0.0787 | -0.0212 | 5.7722 | 0.0100 | 2.6111 |
| development_2024::regime::imbalance_up | 22 | 20 | 0.2273 | 0.0000 | 0.4545 | -0.3572 | -0.4332 | -34.6181 | -42.0146 | 0.2999 | 0.2373 | -2.3402 | -0.0889 | -0.0924 | -0.1028 | 7.3965 | 0.0100 | 2.8182 |
| holdout_2025 | 64 | 62 | 0.4688 | 0.0938 | 0.3750 | 0.0370 | -0.0264 | 3.7040 | -2.5824 | 1.0881 | 0.9429 | 0.2946 | -0.0195 | -0.0214 | -0.0697 | 6.2863 | 0.0100 | 3.1406 |
| holdout_2025::setup::balance_value_rejection | 26 | 25 | 0.3846 | 0.1154 | 0.4231 | -0.1009 | -0.1616 | -10.0871 | -16.1610 | 0.8018 | 0.7041 | -0.8304 | -0.0425 | -0.0483 | -0.0542 | 6.0739 | 0.0100 | 2.5769 |
| holdout_2025::setup::imbalance_opening_range_breakout | 38 | 37 | 0.5263 | 0.0789 | 0.3421 | 0.1314 | 0.0661 | 13.1400 | 6.7083 | 1.3654 | 1.1727 | 1.0215 | 0.0240 | 0.0264 | -0.0518 | 6.4317 | 0.0100 | 3.5263 |
| holdout_2025::regime::balance | 26 | 25 | 0.3846 | 0.1154 | 0.4231 | -0.1009 | -0.1616 | -10.0871 | -16.1610 | 0.8018 | 0.7041 | -0.8304 | -0.0425 | -0.0483 | -0.0542 | 6.0739 | 0.0100 | 2.5769 |
| holdout_2025::regime::imbalance_down | 11 | 10 | 0.3636 | 0.0909 | 0.4545 | -0.1779 | -0.2245 | -17.7890 | -22.4487 | 0.6570 | 0.5914 | -1.9088 | -0.0249 | -0.0288 | -0.0309 | 4.6597 | 0.0100 | 3.0909 |
| holdout_2025::regime::imbalance_up | 27 | 27 | 0.5926 | 0.0741 | 0.2963 | 0.2574 | 0.1845 | 25.7407 | 18.5871 | 1.8731 | 1.5760 | 1.7991 | 0.0502 | 0.0552 | -0.0302 | 7.1536 | 0.0100 | 3.7037 |

## Holdout cost sensitivity

| scope | setup | one_way_cost_bps | trades | win_rate | average_net_return_bps | cumulative_net_return | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- |
| holdout_2025 | all | 0.0000 | 64 | 0.5000 | 3.7040 | 0.0207 | -0.0440 |
| holdout_2025 | all | 0.1000 | 64 | 0.5000 | 2.4467 | 0.0126 | -0.0491 |
| holdout_2025 | all | 0.2500 | 64 | 0.4688 | 0.5608 | 0.0004 | -0.0569 |
| holdout_2025 | all | 0.5000 | 64 | 0.4688 | -2.5824 | -0.0195 | -0.0697 |
| holdout_2025 | all | 1.0000 | 64 | 0.4688 | -8.8687 | -0.0582 | -0.0947 |
| holdout_2025 | all | 1.5000 | 64 | 0.4531 | -15.1550 | -0.0954 | -0.1191 |
| holdout_2025 | all | 2.0000 | 64 | 0.4531 | -21.4414 | -0.1311 | -0.1429 |
| holdout_2025 | all | 3.0000 | 64 | 0.3906 | -34.0141 | -0.1985 | -0.2052 |
| holdout_2025 | all | 5.0000 | 64 | 0.3281 | -59.1595 | -0.3182 | -0.3194 |
| holdout_2025 | balance_value_rejection | 0.0000 | 26 | 0.3846 | -10.0871 | -0.0273 | -0.0498 |
| holdout_2025 | balance_value_rejection | 0.1000 | 26 | 0.3846 | -11.3019 | -0.0303 | -0.0506 |
| holdout_2025 | balance_value_rejection | 0.2500 | 26 | 0.3846 | -13.1240 | -0.0349 | -0.0520 |
| holdout_2025 | balance_value_rejection | 0.5000 | 26 | 0.3846 | -16.1610 | -0.0425 | -0.0542 |
| holdout_2025 | balance_value_rejection | 1.0000 | 26 | 0.3846 | -22.2349 | -0.0576 | -0.0585 |
| holdout_2025 | balance_value_rejection | 1.5000 | 26 | 0.3462 | -28.3088 | -0.0724 | -0.0660 |
| holdout_2025 | balance_value_rejection | 2.0000 | 26 | 0.3462 | -34.3827 | -0.0870 | -0.0777 |
| holdout_2025 | balance_value_rejection | 3.0000 | 26 | 0.2692 | -46.5305 | -0.1155 | -0.1039 |
| holdout_2025 | balance_value_rejection | 5.0000 | 26 | 0.2692 | -70.8260 | -0.1700 | -0.1575 |
| holdout_2025 | imbalance_opening_range_breakout | 0.0000 | 38 | 0.5789 | 13.1400 | 0.0493 | -0.0404 |
| holdout_2025 | imbalance_opening_range_breakout | 0.1000 | 38 | 0.5789 | 11.8537 | 0.0442 | -0.0427 |
| holdout_2025 | imbalance_opening_range_breakout | 0.2500 | 38 | 0.5263 | 9.9241 | 0.0366 | -0.0461 |
| holdout_2025 | imbalance_opening_range_breakout | 0.5000 | 38 | 0.5263 | 6.7083 | 0.0240 | -0.0518 |
| holdout_2025 | imbalance_opening_range_breakout | 1.0000 | 38 | 0.5263 | 0.2766 | -0.0007 | -0.0631 |
| holdout_2025 | imbalance_opening_range_breakout | 1.5000 | 38 | 0.5263 | -6.1551 | -0.0248 | -0.0743 |
| holdout_2025 | imbalance_opening_range_breakout | 2.0000 | 38 | 0.5263 | -12.5868 | -0.0484 | -0.0853 |
| holdout_2025 | imbalance_opening_range_breakout | 3.0000 | 38 | 0.4737 | -25.4503 | -0.0939 | -0.1071 |
| holdout_2025 | imbalance_opening_range_breakout | 5.0000 | 38 | 0.3684 | -51.1771 | -0.1786 | -0.1800 |

## Session-block bootstrap

| scope | setup | sessions | mean_session_return_bps | bootstrap_mean_ci_low_bps | bootstrap_mean_ci_high_bps | bootstrap_probability_mean_positive |
| --- | --- | --- | --- | --- | --- | --- |
| all | all | 126 | 4.3674 | -14.8470 | 23.8059 | 0.6566 |
| all | balance_value_rejection | 52 | 11.2045 | -19.5725 | 44.1522 | 0.7432 |
| all | imbalance_opening_range_breakout | 74 | -0.4371 | -23.6057 | 22.5935 | 0.4848 |
| development_2024 | all | 64 | 11.1796 | -17.4902 | 40.2903 | 0.7786 |
| development_2024 | balance_value_rejection | 27 | 37.1246 | -8.4919 | 82.5177 | 0.9438 |
| development_2024 | imbalance_opening_range_breakout | 37 | -7.7533 | -42.4600 | 28.6336 | 0.3326 |
| holdout_2025 | all | 62 | -2.6646 | -27.9097 | 22.8032 | 0.4098 |
| holdout_2025 | balance_value_rejection | 25 | -16.7893 | -58.2060 | 26.8558 | 0.2090 |
| holdout_2025 | imbalance_opening_range_breakout | 37 | 6.8791 | -23.7820 | 38.1180 | 0.6642 |

## Quarterly stability

| quarter | setup | trades | win_rate | average_gross_return_bps | average_net_return_bps | break_even_one_way_cost_bps | cumulative_net_return | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2024Q1 | all | 13 | 0.5385 | 33.6264 | 25.8484 | 2.1616 | 0.0333 | -0.0213 |
| 2024Q1 | balance_value_rejection | 7 | 0.5714 | 45.0680 | 37.8198 | 3.1089 | 0.0263 | -0.0128 |
| 2024Q1 | imbalance_opening_range_breakout | 6 | 0.5000 | 20.2778 | 11.8818 | 1.2076 | 0.0069 | -0.0213 |
| 2024Q2 | all | 17 | 0.4118 | -8.8373 | -15.8701 | -0.6283 | -0.0275 | -0.0419 |
| 2024Q2 | balance_value_rejection | 8 | 0.5000 | -9.8919 | -17.4507 | -0.6543 | -0.0143 | -0.0175 |
| 2024Q2 | imbalance_opening_range_breakout | 9 | 0.3333 | -7.8999 | -14.4651 | -0.6017 | -0.0134 | -0.0334 |
| 2024Q3 | all | 16 | 0.3125 | -4.2476 | -9.6969 | -0.3897 | -0.0164 | -0.0469 |
| 2024Q3 | balance_value_rejection | 5 | 0.6000 | 47.9695 | 42.5438 | 4.4206 | 0.0210 | -0.0107 |
| 2024Q3 | imbalance_opening_range_breakout | 11 | 0.1818 | -27.9826 | -33.4427 | -2.5625 | -0.0366 | -0.0402 |
| 2024Q4 | all | 21 | 0.6190 | 45.0198 | 38.2261 | 3.3134 | 0.0820 | -0.0328 |
| 2024Q4 | balance_value_rejection | 7 | 0.8571 | 101.4403 | 94.9305 | 7.7914 | 0.0680 | -0.0106 |
| 2024Q4 | imbalance_opening_range_breakout | 14 | 0.5000 | 16.8095 | 9.8739 | 1.2118 | 0.0131 | -0.0369 |
| 2025Q1 | all | 23 | 0.4783 | 8.6936 | 3.8087 | 0.8898 | 0.0077 | -0.0365 |
| 2025Q1 | balance_value_rejection | 6 | 0.3333 | -33.0265 | -36.9638 | -4.1940 | -0.0221 | -0.0180 |
| 2025Q1 | imbalance_opening_range_breakout | 17 | 0.5294 | 23.4183 | 18.1989 | 2.2434 | 0.0306 | -0.0159 |
| 2025Q2 | all | 14 | 0.4286 | 2.7821 | -3.3730 | 0.2260 | -0.0055 | -0.0436 |
| 2025Q2 | balance_value_rejection | 8 | 0.2500 | -38.4796 | -44.3449 | -3.2803 | -0.0353 | -0.0542 |
| 2025Q2 | imbalance_opening_range_breakout | 6 | 0.6667 | 57.7978 | 51.2563 | 4.4178 | 0.0309 | -0.0102 |
| 2025Q3 | all | 14 | 0.5000 | -0.9039 | -9.2863 | -0.0539 | -0.0135 | -0.0377 |
| 2025Q3 | balance_value_rejection | 6 | 0.6667 | 37.1457 | 29.3506 | 2.3826 | 0.0175 | -0.0123 |
| 2025Q3 | imbalance_opening_range_breakout | 8 | 0.3750 | -29.4412 | -38.2639 | -1.6685 | -0.0304 | -0.0375 |
| 2025Q4 | all | 13 | 0.4615 | 0.8315 | -5.8185 | 0.0625 | -0.0083 | -0.0300 |
| 2025Q4 | balance_value_rejection | 6 | 0.3333 | 3.4762 | -3.2912 | 0.2568 | -0.0025 | -0.0216 |
| 2025Q4 | imbalance_opening_range_breakout | 7 | 0.5714 | -1.4354 | -7.9847 | -0.1096 | -0.0058 | -0.0164 |

## Long/short stability

| scope | trades | sessions | win_rate | target_rate | stop_rate | average_gross_r | average_net_r | average_gross_return_bps | average_net_return_bps | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_net_return | annualized_net_return | max_drawdown | average_notional_fraction | median_risk_fraction_deployed | average_holding_bars |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all::side::long | 77 | 74 | 0.4545 | 0.0909 | 0.3636 | 0.0408 | -0.0288 | 4.4018 | -2.4577 | 1.1115 | 0.9430 | 0.3209 | -0.0224 | -0.0117 | -0.1169 | 6.8595 | 0.0100 | 3.1299 |
| all::side::short | 54 | 52 | 0.5000 | 0.2037 | 0.3889 | 0.1968 | 0.1366 | 19.6756 | 13.6631 | 1.4607 | 1.2990 | 1.6362 | 0.0726 | 0.0403 | -0.0715 | 6.0124 | 0.0100 | 2.6111 |
| development_2024::side::long | 37 | 35 | 0.3784 | 0.1081 | 0.4324 | -0.0977 | -0.1719 | -9.1144 | -16.4079 | 0.8002 | 0.6723 | -0.6248 | -0.0606 | -0.0625 | -0.1169 | 7.2935 | 0.0100 | 2.9459 |
| development_2024::side::short | 30 | 29 | 0.6000 | 0.2667 | 0.3000 | 0.5005 | 0.4403 | 50.0532 | 44.0310 | 2.5523 | 2.2708 | 4.1557 | 0.1385 | 0.1564 | -0.0212 | 6.0222 | 0.0100 | 2.4000 |
| holdout_2025::side::long | 40 | 39 | 0.5250 | 0.0750 | 0.3000 | 0.1690 | 0.1036 | 16.9043 | 10.4463 | 1.5004 | 1.2848 | 1.3088 | 0.0408 | 0.0448 | -0.0296 | 6.4580 | 0.0100 | 3.3000 |
| holdout_2025::side::short | 24 | 23 | 0.3750 | 0.1250 | 0.5000 | -0.1830 | -0.2430 | -18.2965 | -24.2967 | 0.6720 | 0.5918 | -1.5246 | -0.0579 | -0.0668 | -0.0715 | 6.0003 | 0.0100 | 2.8750 |

## Auction-regime counts

| scope | day_regime | sessions |
| --- | --- | --- |
| development_2024 | balance | 148 |
| development_2024 | imbalance_down | 36 |
| development_2024 | imbalance_up | 60 |
| holdout_2025 | balance | 146 |
| holdout_2025 | imbalance_down | 30 |
| holdout_2025 | imbalance_up | 54 |

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
| execution_window_bars | 2844 | 1.0000 |
| imbalance_regime_bars | 1080 | 0.3797 |
| balance_regime_bars | 1764 | 0.6203 |
| aggressive_expansion | 1318 | 0.4634 |
| absorption_proxy | 0 | 0.0000 |
| imbalance_orb_signals | 84 | 0.0295 |
| balance_rejection_signals | 72 | 0.0253 |

## Predeclared causal rules

- The raw one-minute file is aggregated into complete five-minute bars; incomplete groups are dropped.
- XNYS calendars determine the 09:30 New York cash open, holidays, DST and early closes.
- The prior completed regular session supplies a 24-row, 70% typical-price volume-profile approximation.
- The first 30 minutes is observation only. An opening close outside the prior value area, aligned with opening return, session VWAP and close-location volume proxy, defines imbalance; otherwise the day is balance.
- During minutes 30-60, imbalance trades require a fresh opening-range break in the regime direction. Balance trades require rejection at the prior value-area edge.
- Both setups require aligned smoothed delta proxy, VWAP and aggressive range/volume expansion. These are OHLCV proxies, not bid/ask order flow.
- Signals enter at the next five-minute open. Stops are one ATR, targets are 2R, same-bar stop/target ambiguity resolves to the stop, and positions close no later than the end of the execution window.
- Risk is 1.00% of current equity at the stop, capped at 10.0x notional. Trading stops after three net losses in the session.
- 2024 is development and 2025 is the untouched temporal holdout. No parameters are selected using holdout performance.

## Limitations

- No symbol, source, venue, contract, expiry or roll metadata was supplied; futures contract sizing, tick rounding and broker margin cannot be modeled honestly.
- Volume provenance is unknown and may be CFD tick volume. Volume profile, delta and absorption are therefore proxies.
- Five-minute OHLCV cannot reveal aggressor side, resting liquidity, queue position, partial fills or true footprint/CVD.
- The configured 0.50 bps one-way execution cost is a scenario, not a measured spread/commission. Use the sensitivity table until actual venue costs are supplied.
- The sample spans only 2024 through 5 December 2025. Even holdout results need a fresh forward or genuinely identified NQ dataset before capital deployment.
