# Nasdaq-100 2-Minute New York-Open Backtest

Generated 2026-07-22T01:04:50.737563+00:00. This is a standalone strategy with no macro or hierarchical-model inputs.

> **Data identity warning:** the CSV has no venue or contract metadata, and 94.1% of one-minute closes are off CME NQ's 0.25-point grid. Results are percentage-return research on an unverified Nasdaq-100 cash/CFD-like feed, not a CME NQ execution backtest.

## Holdout decision table

| scope | trades | sessions | win_rate | target_rate | stop_rate | average_gross_r | average_net_r | average_gross_return_bps | average_net_return_bps | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_gross_return | cumulative_net_return | annualized_net_return | max_drawdown | average_notional_fraction | median_risk_fraction_deployed | average_holding_bars | average_holding_minutes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| holdout_2025 | 69 | 63 | 0.4348 | 0.2754 | 0.5362 | 0.1133 | 0.0319 | 12.2349 | 4.7151 | 1.2411 | 1.0854 | 0.8135 | 0.0822 | 0.0275 | 0.0305 | -0.1525 | 7.5198 | 0.0100 | 5.8696 | 11.7391 |
| holdout_2025::setup::balance_value_rejection | 27 | 25 | 0.3704 | 0.2593 | 0.5556 | 0.0105 | -0.0641 | 0.2652 | -6.8245 | 1.0048 | 0.8857 | 0.0187 | -0.0013 | -0.0203 | -0.0225 | -0.0594 | 7.0898 | 0.0100 | 4.2222 | 8.4444 |
| holdout_2025::setup::imbalance_opening_range_breakout | 42 | 38 | 0.4762 | 0.2857 | 0.5238 | 0.1795 | 0.0937 | 19.9297 | 12.1334 | 1.4157 | 1.2320 | 1.2782 | 0.0836 | 0.0487 | 0.0542 | -0.1172 | 7.7963 | 0.0100 | 6.9286 | 13.8571 |
| holdout_2025::regime::balance | 27 | 25 | 0.3704 | 0.2593 | 0.5556 | 0.0105 | -0.0641 | 0.2652 | -6.8245 | 1.0048 | 0.8857 | 0.0187 | -0.0013 | -0.0203 | -0.0225 | -0.0594 | 7.0898 | 0.0100 | 4.2222 | 8.4444 |
| holdout_2025::regime::imbalance_down | 16 | 14 | 0.5000 | 0.3750 | 0.5000 | 0.3913 | 0.3206 | 38.7655 | 32.0591 | 1.7965 | 1.6127 | 2.8902 | 0.0622 | 0.0509 | 0.0593 | -0.0423 | 6.7064 | 0.0100 | 6.0000 | 12.0000 |
| holdout_2025::regime::imbalance_up | 26 | 24 | 0.4615 | 0.2308 | 0.5385 | 0.0492 | -0.0460 | 8.3384 | -0.1286 | 1.1755 | 0.9975 | 0.4924 | 0.0202 | -0.0021 | -0.0023 | -0.0845 | 8.4670 | 0.0100 | 7.5000 | 15.0000 |

## Full decision table

| scope | trades | sessions | win_rate | target_rate | stop_rate | average_gross_r | average_net_r | average_gross_return_bps | average_net_return_bps | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_gross_return | cumulative_net_return | annualized_net_return | max_drawdown | average_notional_fraction | median_risk_fraction_deployed | average_holding_bars | average_holding_minutes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | 142 | 128 | 0.4437 | 0.2817 | 0.5000 | 0.1487 | 0.0672 | 15.2068 | 7.4780 | 1.3023 | 1.1367 | 0.9838 | 0.2268 | 0.0993 | 0.0508 | -0.1525 | 7.7288 | 0.0100 | 5.5070 | 11.0141 |
| all::setup::balance_value_rejection | 51 | 47 | 0.4510 | 0.3529 | 0.4706 | 0.2760 | 0.1971 | 26.5432 | 18.9787 | 1.5523 | 1.3632 | 1.7545 | 0.1397 | 0.0966 | 0.0494 | -0.0594 | 7.5645 | 0.0100 | 4.5686 | 9.1373 |
| all::setup::imbalance_opening_range_breakout | 91 | 81 | 0.4396 | 0.2418 | 0.5165 | 0.0774 | -0.0056 | 8.8534 | 1.0325 | 1.1717 | 1.0184 | 0.5660 | 0.0764 | 0.0025 | 0.0014 | -0.1172 | 7.8209 | 0.0100 | 6.0330 | 12.0659 |
| all::regime::balance | 51 | 47 | 0.4510 | 0.3529 | 0.4706 | 0.2760 | 0.1971 | 26.5432 | 18.9787 | 1.5523 | 1.3632 | 1.7545 | 0.1397 | 0.0966 | 0.0494 | -0.0594 | 7.5645 | 0.0100 | 4.5686 | 9.1373 |
| all::regime::imbalance_down | 37 | 33 | 0.4865 | 0.3243 | 0.4595 | 0.3020 | 0.2334 | 30.0463 | 23.3357 | 1.6204 | 1.4484 | 2.2387 | 0.1137 | 0.0864 | 0.0484 | -0.0423 | 6.7106 | 0.0100 | 5.6757 | 11.3514 |
| all::regime::imbalance_up | 54 | 48 | 0.4074 | 0.1852 | 0.5556 | -0.0765 | -0.1693 | -5.6676 | -14.2493 | 0.8945 | 0.7578 | -0.3302 | -0.0334 | -0.0772 | -0.0438 | -0.0944 | 8.5816 | 0.0100 | 6.2778 | 12.5556 |
| development_2024 | 73 | 65 | 0.4521 | 0.2877 | 0.4658 | 0.1822 | 0.1006 | 18.0158 | 10.0895 | 1.3611 | 1.1860 | 1.1365 | 0.1336 | 0.0699 | 0.0716 | -0.0839 | 7.9263 | 0.0100 | 5.1644 | 10.3288 |
| development_2024::setup::balance_value_rejection | 24 | 22 | 0.5417 | 0.4583 | 0.3750 | 0.5748 | 0.4910 | 56.1059 | 48.0074 | 2.3979 | 2.0943 | 3.4640 | 0.1412 | 0.1193 | 0.1346 | -0.0428 | 8.0985 | 0.0100 | 4.9583 | 9.9167 |
| development_2024::setup::imbalance_opening_range_breakout | 49 | 43 | 0.4082 | 0.2041 | 0.5102 | -0.0101 | -0.0907 | -0.6405 | -8.4825 | 0.9883 | 0.8570 | -0.0408 | -0.0066 | -0.0441 | -0.0508 | -0.1024 | 7.8420 | 0.0100 | 5.2653 | 10.5306 |
| development_2024::regime::balance | 24 | 22 | 0.5417 | 0.4583 | 0.3750 | 0.5748 | 0.4910 | 56.1059 | 48.0074 | 2.3979 | 2.0943 | 3.4640 | 0.1412 | 0.1193 | 0.1346 | -0.0428 | 8.0985 | 0.0100 | 4.9583 | 9.9167 |
| development_2024::regime::imbalance_down | 21 | 19 | 0.4762 | 0.2857 | 0.4286 | 0.2340 | 0.1669 | 23.4031 | 16.6893 | 1.4850 | 1.3220 | 1.7429 | 0.0484 | 0.0338 | 0.0393 | -0.0318 | 6.7138 | 0.0100 | 5.4286 | 10.8571 |
| development_2024::regime::imbalance_up | 28 | 24 | 0.3571 | 0.1429 | 0.5714 | -0.1932 | -0.2838 | -18.6732 | -27.3613 | 0.6860 | 0.5786 | -1.0746 | -0.0525 | -0.0753 | -0.0893 | -0.0944 | 8.6881 | 0.0100 | 5.1429 | 10.2857 |
| holdout_2025 | 69 | 63 | 0.4348 | 0.2754 | 0.5362 | 0.1133 | 0.0319 | 12.2349 | 4.7151 | 1.2411 | 1.0854 | 0.8135 | 0.0822 | 0.0275 | 0.0305 | -0.1525 | 7.5198 | 0.0100 | 5.8696 | 11.7391 |
| holdout_2025::setup::balance_value_rejection | 27 | 25 | 0.3704 | 0.2593 | 0.5556 | 0.0105 | -0.0641 | 0.2652 | -6.8245 | 1.0048 | 0.8857 | 0.0187 | -0.0013 | -0.0203 | -0.0225 | -0.0594 | 7.0898 | 0.0100 | 4.2222 | 8.4444 |
| holdout_2025::setup::imbalance_opening_range_breakout | 42 | 38 | 0.4762 | 0.2857 | 0.5238 | 0.1795 | 0.0937 | 19.9297 | 12.1334 | 1.4157 | 1.2320 | 1.2782 | 0.0836 | 0.0487 | 0.0542 | -0.1172 | 7.7963 | 0.0100 | 6.9286 | 13.8571 |
| holdout_2025::regime::balance | 27 | 25 | 0.3704 | 0.2593 | 0.5556 | 0.0105 | -0.0641 | 0.2652 | -6.8245 | 1.0048 | 0.8857 | 0.0187 | -0.0013 | -0.0203 | -0.0225 | -0.0594 | 7.0898 | 0.0100 | 4.2222 | 8.4444 |
| holdout_2025::regime::imbalance_down | 16 | 14 | 0.5000 | 0.3750 | 0.5000 | 0.3913 | 0.3206 | 38.7655 | 32.0591 | 1.7965 | 1.6127 | 2.8902 | 0.0622 | 0.0509 | 0.0593 | -0.0423 | 6.7064 | 0.0100 | 6.0000 | 12.0000 |
| holdout_2025::regime::imbalance_up | 26 | 24 | 0.4615 | 0.2308 | 0.5385 | 0.0492 | -0.0460 | 8.3384 | -0.1286 | 1.1755 | 0.9975 | 0.4924 | 0.0202 | -0.0021 | -0.0023 | -0.0845 | 8.4670 | 0.0100 | 7.5000 | 15.0000 |

## Holdout cost sensitivity

| scope | setup | one_way_cost_bps | trades | win_rate | average_net_return_bps | cumulative_net_return | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- |
| holdout_2025 | all | 0.0000 | 69 | 0.4348 | 12.2349 | 0.0822 | -0.1267 |
| holdout_2025 | all | 0.1000 | 69 | 0.4348 | 10.7309 | 0.0710 | -0.1317 |
| holdout_2025 | all | 0.2500 | 69 | 0.4348 | 8.4750 | 0.0545 | -0.1393 |
| holdout_2025 | all | 0.5000 | 69 | 0.4348 | 4.7151 | 0.0275 | -0.1525 |
| holdout_2025 | all | 1.0000 | 69 | 0.4203 | -2.8047 | -0.0245 | -0.1793 |
| holdout_2025 | all | 1.5000 | 69 | 0.4058 | -10.3246 | -0.0739 | -0.2052 |
| holdout_2025 | all | 2.0000 | 69 | 0.3913 | -17.8444 | -0.1208 | -0.2304 |
| holdout_2025 | all | 3.0000 | 69 | 0.3913 | -32.8840 | -0.2078 | -0.2800 |
| holdout_2025 | all | 5.0000 | 69 | 0.3478 | -62.9633 | -0.3571 | -0.3752 |
| holdout_2025 | balance_value_rejection | 0.0000 | 27 | 0.3704 | 0.2652 | -0.0013 | -0.0516 |
| holdout_2025 | balance_value_rejection | 0.1000 | 27 | 0.3704 | -1.1527 | -0.0051 | -0.0531 |
| holdout_2025 | balance_value_rejection | 0.2500 | 27 | 0.3704 | -3.2796 | -0.0108 | -0.0555 |
| holdout_2025 | balance_value_rejection | 0.5000 | 27 | 0.3704 | -6.8245 | -0.0203 | -0.0594 |
| holdout_2025 | balance_value_rejection | 1.0000 | 27 | 0.3704 | -13.9143 | -0.0389 | -0.0672 |
| holdout_2025 | balance_value_rejection | 1.5000 | 27 | 0.3704 | -21.0041 | -0.0571 | -0.0749 |
| holdout_2025 | balance_value_rejection | 2.0000 | 27 | 0.3333 | -28.0939 | -0.0751 | -0.0832 |
| holdout_2025 | balance_value_rejection | 3.0000 | 27 | 0.3333 | -42.2734 | -0.1100 | -0.1120 |
| holdout_2025 | balance_value_rejection | 5.0000 | 27 | 0.2963 | -70.6325 | -0.1760 | -0.1671 |
| holdout_2025 | imbalance_opening_range_breakout | 0.0000 | 42 | 0.4762 | 19.9297 | 0.0836 | -0.0986 |
| holdout_2025 | imbalance_opening_range_breakout | 0.1000 | 42 | 0.4762 | 18.3704 | 0.0766 | -0.1024 |
| holdout_2025 | imbalance_opening_range_breakout | 0.2500 | 42 | 0.4762 | 16.0315 | 0.0660 | -0.1080 |
| holdout_2025 | imbalance_opening_range_breakout | 0.5000 | 42 | 0.4762 | 12.1334 | 0.0487 | -0.1172 |
| holdout_2025 | imbalance_opening_range_breakout | 1.0000 | 42 | 0.4524 | 4.3371 | 0.0149 | -0.1354 |
| holdout_2025 | imbalance_opening_range_breakout | 1.5000 | 42 | 0.4286 | -3.4591 | -0.0178 | -0.1532 |
| holdout_2025 | imbalance_opening_range_breakout | 2.0000 | 42 | 0.4286 | -11.2554 | -0.0495 | -0.1707 |
| holdout_2025 | imbalance_opening_range_breakout | 3.0000 | 42 | 0.4286 | -26.8480 | -0.1099 | -0.2046 |
| holdout_2025 | imbalance_opening_range_breakout | 5.0000 | 42 | 0.3810 | -58.0330 | -0.2198 | -0.2685 |

## Session-block bootstrap

| scope | setup | sessions | mean_session_return_bps | bootstrap_mean_ci_low_bps | bootstrap_mean_ci_high_bps | bootstrap_probability_mean_positive |
| --- | --- | --- | --- | --- | --- | --- |
| all | all | 128 | 8.2854 | -14.3521 | 31.7667 | 0.7658 |
| all | balance_value_rejection | 47 | 20.5592 | -17.7909 | 58.6382 | 0.8520 |
| all | imbalance_opening_range_breakout | 81 | 1.1636 | -27.4021 | 30.9690 | 0.5142 |
| development_2024 | all | 65 | 11.3250 | -20.7771 | 45.0138 | 0.7584 |
| development_2024 | balance_value_rejection | 22 | 52.3341 | -7.4667 | 111.0934 | 0.9578 |
| development_2024 | imbalance_opening_range_breakout | 43 | -9.6565 | -47.5539 | 29.9826 | 0.3094 |
| holdout_2025 | all | 63 | 5.1493 | -26.2146 | 37.5170 | 0.6170 |
| holdout_2025 | balance_value_rejection | 25 | -7.4028 | -55.2268 | 43.4217 | 0.3828 |
| holdout_2025 | imbalance_opening_range_breakout | 38 | 13.4074 | -29.4754 | 54.9655 | 0.7330 |

## Quarterly stability

| quarter | setup | trades | win_rate | average_gross_return_bps | average_net_return_bps | break_even_one_way_cost_bps | cumulative_net_return | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2024Q1 | all | 13 | 0.5385 | 34.0977 | 25.8774 | 2.0740 | 0.0330 | -0.0406 |
| 2024Q1 | balance_value_rejection | 5 | 0.4000 | 20.0000 | 11.4100 | 1.1641 | 0.0052 | -0.0324 |
| 2024Q1 | imbalance_opening_range_breakout | 8 | 0.6250 | 42.9088 | 34.9195 | 2.6854 | 0.0277 | -0.0195 |
| 2024Q2 | all | 13 | 0.4615 | 20.0747 | 11.4309 | 1.1612 | 0.0139 | -0.0334 |
| 2024Q2 | balance_value_rejection | 9 | 0.4444 | 16.5975 | 7.8561 | 0.9494 | 0.0064 | -0.0262 |
| 2024Q2 | imbalance_opening_range_breakout | 4 | 0.5000 | 27.8984 | 19.4741 | 1.6558 | 0.0075 | -0.0108 |
| 2024Q3 | all | 20 | 0.3000 | -22.7302 | -29.7220 | -1.6255 | -0.0588 | -0.0613 |
| 2024Q3 | balance_value_rejection | 3 | 0.6667 | 123.7982 | 115.3758 | 7.3493 | 0.0348 | -0.0036 |
| 2024Q3 | imbalance_opening_range_breakout | 17 | 0.2353 | -48.5882 | -55.3275 | -3.6048 | -0.0905 | -0.0807 |
| 2024Q4 | all | 27 | 0.5185 | 39.4637 | 31.3321 | 2.4266 | 0.0854 | -0.0385 |
| 2024Q4 | balance_value_rejection | 7 | 0.7143 | 103.6812 | 96.8991 | 7.6437 | 0.0692 | -0.0108 |
| 2024Q4 | imbalance_opening_range_breakout | 20 | 0.4500 | 16.9875 | 8.3836 | 0.9872 | 0.0151 | -0.0385 |
| 2025Q1 | all | 14 | 0.6429 | 65.7213 | 59.6070 | 5.3744 | 0.0855 | -0.0211 |
| 2025Q1 | balance_value_rejection | 5 | 0.4000 | 4.5068 | -1.7387 | 0.3608 | -0.0012 | -0.0106 |
| 2025Q1 | imbalance_opening_range_breakout | 9 | 0.7778 | 99.7294 | 93.6880 | 8.2539 | 0.0868 | -0.0106 |
| 2025Q2 | all | 15 | 0.6667 | 75.7006 | 69.4446 | 6.0503 | 0.1081 | -0.0203 |
| 2025Q2 | balance_value_rejection | 8 | 0.5000 | 43.8201 | 39.1195 | 4.6611 | 0.0310 | -0.0270 |
| 2025Q2 | imbalance_opening_range_breakout | 7 | 0.8571 | 112.1354 | 104.1019 | 6.9792 | 0.0748 | -0.0109 |
| 2025Q3 | all | 25 | 0.3600 | -2.1148 | -11.1871 | -0.1165 | -0.0294 | -0.0736 |
| 2025Q3 | balance_value_rejection | 9 | 0.4444 | 13.8761 | 4.7900 | 0.7636 | 0.0036 | -0.0266 |
| 2025Q3 | imbalance_opening_range_breakout | 16 | 0.3125 | -11.1096 | -20.1742 | -0.6128 | -0.0328 | -0.0832 |
| 2025Q4 | all | 15 | 0.1333 | -77.2354 | -84.7434 | -5.1436 | -0.1200 | -0.1110 |
| 2025Q4 | balance_value_rejection | 5 | 0.0000 | -98.1637 | -106.3270 | -6.0125 | -0.0520 | -0.0424 |
| 2025Q4 | imbalance_opening_range_breakout | 10 | 0.2000 | -66.7713 | -73.9516 | -4.6496 | -0.0717 | -0.0631 |

## Long/short stability

| scope | trades | sessions | win_rate | target_rate | stop_rate | average_gross_r | average_net_r | average_gross_return_bps | average_net_return_bps | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_gross_return | cumulative_net_return | annualized_net_return | max_drawdown | average_notional_fraction | median_risk_fraction_deployed | average_holding_bars | average_holding_minutes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all::side::long | 80 | 71 | 0.3875 | 0.2125 | 0.5750 | -0.0631 | -0.1510 | -4.3961 | -12.6053 | 0.9218 | 0.7943 | -0.2678 | -0.0399 | -0.1010 | -0.0542 | -0.1390 | 8.2092 | 0.0100 | 5.6875 | 11.3750 |
| all::side::short | 62 | 57 | 0.5161 | 0.3710 | 0.4032 | 0.4221 | 0.3488 | 40.5009 | 33.3919 | 1.9489 | 1.7224 | 2.8486 | 0.2778 | 0.2229 | 0.1213 | -0.0537 | 7.1090 | 0.0100 | 5.2742 | 10.5484 |
| development_2024::side::long | 41 | 36 | 0.3902 | 0.1951 | 0.5366 | -0.0568 | -0.1461 | -4.7080 | -13.3057 | 0.9161 | 0.7831 | -0.2738 | -0.0219 | -0.0558 | -0.0588 | -0.1287 | 8.5977 | 0.0100 | 5.3902 | 10.7805 |
| development_2024::side::short | 32 | 29 | 0.5312 | 0.4062 | 0.3750 | 0.4884 | 0.4167 | 47.1308 | 40.0646 | 2.1239 | 1.8879 | 3.3350 | 0.1590 | 0.1332 | 0.1555 | -0.0318 | 7.0662 | 0.0100 | 4.8750 | 9.7500 |
| holdout_2025::side::long | 39 | 35 | 0.3846 | 0.2308 | 0.6154 | -0.0698 | -0.1561 | -4.0683 | -11.8690 | 0.9278 | 0.8061 | -0.2608 | -0.0185 | -0.0479 | -0.0530 | -0.1065 | 7.8008 | 0.0100 | 6.0000 | 12.0000 |
| holdout_2025::side::short | 30 | 28 | 0.5000 | 0.3333 | 0.4333 | 0.3514 | 0.2764 | 33.4290 | 26.2744 | 1.7688 | 1.5543 | 2.3362 | 0.1025 | 0.0792 | 0.0924 | -0.0537 | 7.1546 | 0.0100 | 5.7000 | 11.4000 |

## Auction-regime counts

| scope | day_regime | sessions |
| --- | --- | --- |
| development_2024 | balance | 157 |
| development_2024 | imbalance_down | 31 |
| development_2024 | imbalance_up | 56 |
| holdout_2025 | balance | 146 |
| holdout_2025 | imbalance_down | 28 |
| holdout_2025 | imbalance_up | 56 |

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
| execution_window_bars | 7110 | 1.0000 |
| imbalance_regime_bars | 2565 | 0.3608 |
| balance_regime_bars | 4545 | 0.6392 |
| aggressive_expansion | 2064 | 0.2903 |
| absorption_proxy | 0 | 0.0000 |
| recent_absorption_proxy | 0 | 0.0000 |
| accumulation_proxy | 37 | 0.0052 |
| recent_absorption_and_accumulation | 0 | 0.0000 |
| strict_absorption_signals | 0 | 0.0000 |
| imbalance_orb_signals | 101 | 0.0142 |
| balance_rejection_signals | 62 | 0.0087 |

## Strict absorption diagnostics

| scope | bars | indicator_eligible_bars | volume_above_2x_average | range_below_0_3_atr | strict_absorption_intersection | absorption_given_volume_share | absorption_given_narrow_range_share | recent_absorption | three_bar_accumulation | recent_absorption_and_accumulation | aggressive_expansion | strict_signals |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all_feed_bars | 340741 | 340691 | 22042 | 1256 | 0 | 0.0000 | 0.0000 | 0 | 5327 | 0 | 40411 | 0 |
| complete_regular_session_bars | 92565 | 92565 | 9506 | 7 | 0 | 0.0000 | 0.0000 | 0 | 446 | 0 | 10369 | 0 |
| first_30m_bars | 7155 | 7155 | 6138 | 0 | 0 | 0.0000 | 0.0000 | 0 | 6 | 0 | 3463 | 0 |
| execution_30m_bars | 7110 | 7110 | 1280 | 1 | 0 | 0.0000 | 0.0000 | 0 | 37 | 0 | 2064 | 0 |

## Predeclared causal rules

- The raw one-minute file is aggregated into complete 2-minute bars; incomplete groups are dropped.
- XNYS calendars determine the 09:30 New York cash open, holidays, DST and early closes.
- The prior completed regular session supplies a 24-row, 70% typical-price volume-profile approximation.
- The first 30 minutes is observation only. An opening close outside the prior value area, aligned with opening return, session VWAP and close-location volume proxy, defines imbalance; otherwise the day is balance.
- During minutes 30-60, imbalance trades require a fresh opening-range break in the regime direction. Balance trades require rejection at the prior value-area edge.
- The strict Triple-A proxy requires prior 2x-volume/0.3-ATR absorption, three-bar accumulation at a prior-session or opening-range level, then aligned aggressive expansion through that accumulation.
- Both setups require aligned smoothed delta proxy, VWAP and aggressive range/volume expansion. These are OHLCV proxies, not bid/ask order flow.
- Signals enter at the next 2-minute open. Stops are one ATR, targets are 2R, same-bar stop/target ambiguity resolves to the stop, and positions close no later than the end of the execution window.
- Risk is 1.00% of current equity at the stop, capped at 10.0x notional. Trading stops after three net losses in the session.
- 2024 is development and 2025 is the untouched temporal holdout. No parameters are selected using holdout performance.

## Limitations

- No symbol, source, venue, contract, expiry or roll metadata was supplied; futures contract sizing, tick rounding and broker margin cannot be modeled honestly.
- Volume provenance is unknown and may be CFD tick volume. Volume profile, delta and absorption are therefore proxies.
- 2-minute OHLCV cannot reveal aggressor side, resting liquidity, queue position, partial fills or true footprint/CVD.
- The configured 0.50 bps one-way execution cost is a scenario, not a measured spread/commission. Use the sensitivity table until actual venue costs are supplied.
- The sample spans only 2024 through 5 December 2025. Even holdout results need a fresh forward or genuinely identified NQ dataset before capital deployment.
