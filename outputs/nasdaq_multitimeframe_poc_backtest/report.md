# One-Minute / Fifteen-Minute Composite-POC Study

Generated 2026-07-22T02:16:36.162121+00:00.

This study uses one-minute execution around POCs estimated from the previous 1, 3, and 5 complete regular sessions. It compares immediate one-minute crossing, a second one-minute acceptance close, and confirmation at a completed 15-minute auction close.

## Research conclusion

- Yesterday's isolated POC did not retain directional continuation after one-minute acceptance: its mean next-10-minute return was -0.35 bps. The 3-session and 5-session composite POCs were stronger at +1.35 and +1.61 bps. This supports treating several days of accepted value as the focus area rather than anchoring only to yesterday.
- Session timing mattered more than the minute's position inside its 15-minute block. Accepted 3d/5d crosses averaged +3.82 bps during the opening 30 minutes, -2.41 bps during minutes 30–60, and -2.71 bps in the final hour. Within a 15-minute block, early/middle/late signals averaged +1.03, +1.78, and +0.54 bps—no clean monotonic decay.
- A blanket “follow the previous 15-minute candle” rule did not help. One-minute focus acceptance plus completed-15-minute direction averaged only +0.36 bps. Waiting for the current 15-minute block itself to close accepted was better at +1.48 bps, but delays the entry and remains a small, selected subgroup.
- The raw one-minute ATR stop was the main execution weakness. On accepted 3d/5d crosses during minutes 15–30, it produced -2.91% net. Requiring stop distance of at least 0.50, 0.75, or 1.00 times the preceding completed 15-minute range produced 2.57%, 5.77%, and 3.98%. The 0.75x result used only 48 trades, returned 2.04% in 2025, and had -1.75% full-sample drawdown.
- This stop-width sweep is adaptive evidence, not a validated optimum. The 0.75x session-bootstrap 95% interval still crosses zero, and its break-even one-way cost is only 2.17 bps. It belongs in forward paper testing.

## Forward-return event study

| group | events | sessions | bootstrap_10m_ci_low_bps | bootstrap_10m_ci_high_bps | bootstrap_probability_10m_positive | mean_forward_1m_bps | median_forward_1m_bps | positive_forward_1m_share | mean_forward_2m_bps | median_forward_2m_bps | positive_forward_2m_share | mean_forward_5m_bps | median_forward_5m_bps | positive_forward_5m_share | mean_forward_10m_bps | median_forward_10m_bps | positive_forward_10m_share | mean_forward_15m_bps | median_forward_15m_bps | positive_forward_15m_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1m_cross_all | 4005 | 297 | 2.1465 | 4.9899 | 1.0000 | 0.0743 | 0.0000 | 0.4981 | 0.1254 | 0.0000 | 0.4966 | 0.1554 | 0.0000 | 0.4981 | 0.1895 | 0.0662 | 0.5021 | 0.2300 | 0.3194 | 0.5101 |
| 1m_acceptance_all | 1742 | 270 | 0.8196 | 5.4600 | 0.9964 | 0.0104 | 0.0594 | 0.5034 | 0.1713 | -0.0668 | 0.4902 | 0.1095 | -0.1373 | 0.4885 | 0.1142 | 0.0000 | 0.4994 | 0.0564 | 0.0327 | 0.5000 |
| 15m_acceptance_all | 1114 | 264 | 0.2278 | 4.1172 | 0.9840 | 0.5485 | 0.1501 | 0.5153 | 0.5236 | 0.0564 | 0.5009 | 0.3570 | -0.0546 | 0.4919 | 0.1829 | 0.3240 | 0.5108 | 0.4943 | 0.5652 | 0.5144 |
| 1m_acceptance_cross_1d | 1007 | 215 | 0.9069 | 6.5802 | 0.9944 | -0.2528 | 0.0000 | 0.4945 | -0.0619 | -0.1463 | 0.4846 | -0.2928 | -0.1409 | 0.4886 | -0.3496 | -0.1227 | 0.4926 | -0.7474 | -0.1014 | 0.4985 |
| 1m_acceptance_cross_3d | 629 | 151 | 1.8118 | 9.1746 | 0.9994 | 0.3596 | 0.2096 | 0.5231 | 0.6632 | 0.2557 | 0.5231 | 1.0407 | 0.3409 | 0.5167 | 1.3476 | 0.5864 | 0.5231 | 1.5756 | 0.6841 | 0.5199 |
| 1m_acceptance_cross_5d | 462 | 125 | 1.4073 | 10.1223 | 0.9982 | 0.6841 | 0.2314 | 0.5238 | 0.7223 | 0.0631 | 0.5043 | 1.0953 | -0.3500 | 0.4784 | 1.6113 | 0.9358 | 0.5303 | 2.1300 | 0.2723 | 0.5065 |
| 1m_acceptance_cross_3d_or_5d | 952 | 177 | 1.2532 | 7.4392 | 0.9994 | 0.3595 | 0.1641 | 0.5179 | 0.5211 | 0.1156 | 0.5095 | 0.8200 | 0.1075 | 0.5053 | 1.1177 | 0.6083 | 0.5252 | 1.3249 | 0.4584 | 0.5147 |
| 1m_acceptance_3d_or_5d_opening_0_30m | 144 | 73 | 3.0626 | 10.6199 | 0.9994 | 0.4266 | 0.3327 | 0.5278 | 0.5907 | 0.5135 | 0.5556 | 2.4499 | 2.7520 | 0.5972 | 3.8229 | 4.7869 | 0.5833 | 3.9157 | 3.5466 | 0.5417 |
| 1m_acceptance_focus_cluster | 646 | 114 | 0.9662 | 6.7294 | 0.9956 | 0.2589 | 0.1178 | 0.5108 | 0.2688 | 0.1156 | 0.5077 | 0.6529 | -0.2870 | 0.4830 | 0.8618 | 0.3867 | 0.5139 | 1.1597 | 0.1278 | 0.5031 |
| 1m_acceptance_15m_direction | 920 | 232 | -0.4724 | 4.7919 | 0.9408 | 0.0882 | 0.0000 | 0.4946 | 0.2284 | -0.1772 | 0.4761 | 0.0252 | -0.2677 | 0.4870 | 0.4557 | 0.2520 | 0.5076 | 0.0225 | -0.2515 | 0.4891 |
| 1m_acceptance_15m_impulse | 322 | 155 | -3.7024 | 3.9857 | 0.5896 | -0.6597 | -0.3111 | 0.4689 | -0.5200 | -0.4340 | 0.4658 | -0.9308 | -0.3613 | 0.4938 | 0.0479 | 0.1332 | 0.5062 | -0.8257 | -0.4618 | 0.4845 |
| 1m_acceptance_15m_poc_migration | 882 | 222 | -0.6992 | 4.3289 | 0.9020 | 0.1229 | 0.1187 | 0.5125 | 0.1868 | -0.0917 | 0.4887 | -0.1357 | -0.3797 | 0.4785 | 0.5008 | 0.4125 | 0.5170 | 0.6171 | 0.2098 | 0.5102 |
| 1m_focus_15m_direction_vwap | 343 | 92 | -3.3967 | 2.9368 | 0.4504 | 0.2362 | 0.1184 | 0.5131 | 0.0460 | -0.4323 | 0.4636 | 0.0357 | -0.5801 | 0.4665 | 0.3619 | 0.3552 | 0.5190 | 0.1865 | -0.3089 | 0.4810 |
| 15m_focus_direction_vwap | 385 | 108 | 0.7883 | 7.0824 | 0.9956 | 1.4231 | 0.7329 | 0.5740 | 1.0229 | 0.5197 | 0.5429 | 0.6022 | 0.4918 | 0.5065 | 1.4809 | 0.9362 | 0.5429 | 2.2207 | 0.7329 | 0.5403 |

## One-minute timing inside the session and 15-minute block

| dimension | bucket | events | sessions | focus_cluster_share | mean_forward_1m_bps | mean_forward_5m_bps | mean_forward_10m_bps | mean_forward_15m_bps | positive_forward_10m_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| session_bucket | closing_330_390m | 140 | 63 | 0.4643 | -0.0570 | -1.6304 | -3.4463 | -3.6498 | 0.3857 |
| session_bucket | midday_180_330m | 501 | 130 | 0.3772 | 0.0612 | -0.1489 | 0.0958 | 0.3011 | 0.4731 |
| session_bucket | morning_60_180m | 582 | 166 | 0.3763 | 0.0689 | 0.4802 | 0.7892 | 0.8704 | 0.5309 |
| session_bucket | opening_0_30m | 286 | 136 | 0.3147 | -0.0478 | 1.8329 | 2.6858 | 2.5600 | 0.5420 |
| session_bucket | opening_30_60m | 233 | 109 | 0.3562 | -0.1329 | -1.3310 | -2.5492 | -3.3492 | 0.4936 |
| minute_in_15m_bucket | early_0_4m | 603 | 216 | 0.3632 | -0.0760 | 0.0426 | -0.1315 | -0.4005 | 0.4776 |
| minute_in_15m_bucket | late_10_14m | 565 | 203 | 0.3699 | 0.1766 | 0.6208 | -0.0187 | 0.0462 | 0.4938 |
| minute_in_15m_bucket | middle_5_9m | 574 | 199 | 0.3798 | -0.0624 | -0.3236 | 0.5032 | 0.5464 | 0.5279 |
| session_bucket_3d_or_5d | closing_330_390m | 82 | 41 | 0.6707 | 0.2202 | -1.5879 | -2.7111 | -2.7536 | 0.4268 |
| session_bucket_3d_or_5d | midday_180_330m | 289 | 87 | 0.5744 | 0.5675 | 0.7002 | 1.6632 | 2.5060 | 0.5156 |
| session_bucket_3d_or_5d | morning_60_180m | 315 | 103 | 0.6032 | 0.3170 | 1.7662 | 1.7415 | 1.7759 | 0.5619 |
| session_bucket_3d_or_5d | opening_0_30m | 144 | 73 | 0.5347 | 0.4266 | 2.4499 | 3.8229 | 3.9157 | 0.5833 |
| session_bucket_3d_or_5d | opening_30_60m | 122 | 63 | 0.6066 | -0.0090 | -1.6446 | -2.4051 | -2.9543 | 0.4508 |
| minute_in_15m_bucket_3d_or_5d | early_0_4m | 344 | 130 | 0.5756 | 0.4254 | 1.0574 | 1.0308 | 1.4494 | 0.4942 |
| minute_in_15m_bucket_3d_or_5d | late_10_14m | 301 | 127 | 0.5914 | 0.4610 | 0.7469 | 0.5405 | 0.1051 | 0.5116 |
| minute_in_15m_bucket_3d_or_5d | middle_5_9m | 307 | 124 | 0.6059 | 0.1862 | 0.6258 | 1.7809 | 2.3813 | 0.5733 |

## Leveraged strategy results

| variant | scope | trades | sessions | win_rate | target_rate | stop_rate | average_gross_r | average_net_r | average_gross_return_bps | average_net_return_bps | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_gross_return | cumulative_net_return | annualized_net_return | max_drawdown | average_notional_fraction | median_risk_fraction_deployed | average_holding_bars | average_holding_minutes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1m_cross_10m | all | 1094 | 297 | 0.3830 | 0.2550 | 0.5777 | 0.0377 | -0.1084 | 3.1165 | -6.3196 | 1.0724 | 0.8707 | 0.1651 | 0.3310 | -0.5261 | -0.3249 | -0.5865 | 9.4361 | 0.0074 | 4.8336 | 4.8336 |
| 1m_cross_10m | development_2024 | 556 | 154 | 0.3795 | 0.2536 | 0.5737 | 0.0338 | -0.1196 | 2.8510 | -6.8110 | 1.0687 | 0.8567 | 0.1475 | 0.1417 | -0.3329 | -0.3430 | -0.4531 | 9.6619 | 0.0071 | 4.8921 | 4.8921 |
| 1m_cross_10m | holdout_2025 | 538 | 143 | 0.3866 | 0.2565 | 0.5818 | 0.0418 | -0.0967 | 3.3909 | -5.8118 | 1.0760 | 0.8843 | 0.1842 | 0.1658 | -0.2895 | -0.3119 | -0.3676 | 9.2027 | 0.0078 | 4.7732 | 4.7732 |
| 1m_acceptance_10m | all | 832 | 270 | 0.3798 | 0.2572 | 0.5541 | 0.0527 | -0.0993 | 4.4538 | -5.0268 | 1.1094 | 0.8920 | 0.2349 | 0.3920 | -0.3675 | -0.2142 | -0.4554 | 9.4806 | 0.0072 | 5.0084 | 5.0084 |
| 1m_acceptance_10m | development_2024 | 427 | 139 | 0.3724 | 0.2436 | 0.5574 | 0.0199 | -0.1403 | 0.4978 | -9.2154 | 1.0124 | 0.7997 | 0.0256 | 0.0032 | -0.3375 | -0.3477 | -0.4554 | 9.7132 | 0.0068 | 5.1148 | 5.1148 |
| 1m_acceptance_10m | holdout_2025 | 405 | 131 | 0.3877 | 0.2716 | 0.5506 | 0.0874 | -0.0561 | 8.6247 | -0.6107 | 1.2082 | 0.9870 | 0.4669 | 0.3875 | -0.0453 | -0.0493 | -0.2428 | 9.2354 | 0.0076 | 4.8963 | 4.8963 |
| 15m_acceptance_10m | all | 732 | 264 | 0.3702 | 0.2514 | 0.5697 | 0.0225 | -0.1331 | 1.9841 | -7.4596 | 1.0482 | 0.8414 | 0.1050 | 0.1175 | -0.4404 | -0.2632 | -0.4485 | 9.4438 | 0.0071 | 5.0765 | 5.0765 |
| 15m_acceptance_10m | development_2024 | 382 | 137 | 0.3848 | 0.2592 | 0.5550 | 0.0576 | -0.1063 | 2.5249 | -7.1506 | 1.0645 | 0.8411 | 0.1305 | 0.0835 | -0.2513 | -0.2601 | -0.3382 | 9.6755 | 0.0066 | 5.1754 | 5.1754 |
| 15m_acceptance_10m | holdout_2025 | 350 | 127 | 0.3543 | 0.2429 | 0.5857 | -0.0158 | -0.1623 | 1.3940 | -7.7970 | 1.0322 | 0.8416 | 0.0758 | 0.0314 | -0.2525 | -0.2725 | -0.3615 | 9.1909 | 0.0076 | 4.9686 | 4.9686 |
| 1m_focus_acceptance_10m | all | 312 | 114 | 0.3718 | 0.2500 | 0.5641 | 0.0250 | -0.1324 | 3.1559 | -6.4256 | 1.0780 | 0.8617 | 0.1647 | 0.0877 | -0.1934 | -0.1071 | -0.1868 | 9.5815 | 0.0069 | 5.0737 | 5.0737 |
| 1m_focus_acceptance_10m | development_2024 | 158 | 58 | 0.3924 | 0.2532 | 0.5190 | 0.0782 | -0.0961 | 6.0258 | -3.7193 | 1.1758 | 0.9072 | 0.3092 | 0.0934 | -0.0626 | -0.0665 | -0.1291 | 9.7451 | 0.0059 | 5.3608 | 5.3608 |
| 1m_focus_acceptance_10m | holdout_2025 | 154 | 56 | 0.3506 | 0.2468 | 0.6104 | -0.0296 | -0.1696 | 0.2116 | -9.2022 | 1.0045 | 0.8264 | 0.0112 | -0.0052 | -0.1395 | -0.1520 | -0.1759 | 9.4138 | 0.0079 | 4.7792 | 4.7792 |
| 1m_acceptance_3d_10m | all | 399 | 151 | 0.3659 | 0.2481 | 0.5865 | -0.0063 | -0.1605 | 1.4965 | -8.0438 | 1.0358 | 0.8317 | 0.0784 | 0.0417 | -0.2882 | -0.1638 | -0.2905 | 9.5403 | 0.0071 | 4.9148 | 4.9148 |
| 1m_acceptance_3d_10m | development_2024 | 206 | 75 | 0.3883 | 0.2476 | 0.5583 | 0.0297 | -0.1401 | 3.1021 | -6.5763 | 1.0838 | 0.8462 | 0.1603 | 0.0573 | -0.1338 | -0.1418 | -0.1867 | 9.6784 | 0.0062 | 5.1602 | 5.1602 |
| 1m_acceptance_3d_10m | holdout_2025 | 193 | 76 | 0.3420 | 0.2487 | 0.6166 | -0.0446 | -0.1823 | -0.2173 | -9.6101 | 0.9954 | 0.8193 | -0.0116 | -0.0148 | -0.1783 | -0.1932 | -0.2119 | 9.3929 | 0.0079 | 4.6528 | 4.6528 |
| 1m_acceptance_5d_10m | all | 298 | 125 | 0.3725 | 0.2651 | 0.5839 | 0.0338 | -0.1155 | 1.5781 | -7.9414 | 1.0356 | 0.8420 | 0.0829 | 0.0325 | -0.2227 | -0.1278 | -0.2336 | 9.5195 | 0.0076 | 5.0403 | 5.0403 |
| 1m_acceptance_5d_10m | development_2024 | 157 | 65 | 0.3694 | 0.2675 | 0.5987 | 0.0131 | -0.1451 | -0.5745 | -10.2228 | 0.9866 | 0.7918 | -0.0298 | -0.0160 | -0.1544 | -0.1685 | -0.2105 | 9.6483 | 0.0068 | 4.9045 | 4.9045 |
| 1m_acceptance_5d_10m | holdout_2025 | 141 | 60 | 0.3759 | 0.2624 | 0.5674 | 0.0568 | -0.0824 | 3.9750 | -5.4012 | 1.0870 | 0.8952 | 0.2120 | 0.0493 | -0.0807 | -0.0879 | -0.1673 | 9.3762 | 0.0081 | 5.1915 | 5.1915 |
| 1m_acceptance_3d_or_5d_10m | all | 500 | 177 | 0.3720 | 0.2500 | 0.5800 | 0.0083 | -0.1442 | 1.1633 | -8.3638 | 1.0272 | 0.8284 | 0.0611 | 0.0345 | -0.3577 | -0.2078 | -0.3674 | 9.5272 | 0.0074 | 4.9920 | 4.9920 |
| 1m_acceptance_3d_or_5d_10m | development_2024 | 259 | 90 | 0.3822 | 0.2471 | 0.5753 | 0.0090 | -0.1598 | -0.4514 | -10.1405 | 0.9886 | 0.7768 | -0.0233 | -0.0218 | -0.2390 | -0.2468 | -0.3090 | 9.6891 | 0.0064 | 5.0347 | 5.0347 |
| 1m_acceptance_3d_or_5d_10m | holdout_2025 | 241 | 87 | 0.3610 | 0.2531 | 0.5851 | 0.0076 | -0.1274 | 2.8987 | -6.4544 | 1.0626 | 0.8766 | 0.1550 | 0.0575 | -0.1560 | -0.1692 | -0.2308 | 9.3532 | 0.0082 | 4.9461 | 4.9461 |
| 1m_acceptance_3d_or_5d_opening_10m | all | 120 | 73 | 0.4083 | 0.2667 | 0.5417 | 0.1133 | -0.0129 | 10.1984 | 0.7032 | 1.2283 | 1.0140 | 0.5370 | 0.1220 | 0.0012 | 0.0006 | -0.1025 | 9.4952 | 0.0084 | 5.3083 | 5.3083 |
| 1m_acceptance_3d_or_5d_opening_10m | development_2024 | 50 | 33 | 0.4400 | 0.2800 | 0.5400 | 0.1739 | 0.0387 | 14.7142 | 5.0758 | 1.3557 | 1.1085 | 0.7633 | 0.0733 | 0.0228 | 0.0249 | -0.0387 | 9.6385 | 0.0077 | 4.9600 | 4.9600 |
| 1m_acceptance_3d_or_5d_opening_10m | holdout_2025 | 70 | 40 | 0.3857 | 0.2571 | 0.5429 | 0.0700 | -0.0497 | 6.9728 | -2.4201 | 1.1483 | 0.9542 | 0.3712 | 0.0454 | -0.0211 | -0.0238 | -0.1025 | 9.3929 | 0.0089 | 5.5571 | 5.5571 |
| opening_3d5d_stop_0.00x_10m | all | 59 | 42 | 0.3898 | 0.2542 | 0.5932 | 0.0384 | -0.0751 | 5.0546 | -4.3341 | 1.0993 | 0.9235 | 0.2692 | 0.0262 | -0.0291 | -0.0154 | -0.0841 | 9.3887 | 0.0089 | 5.2712 | 5.2712 |
| opening_3d5d_stop_0.00x_10m | development_2024 | 20 | 16 | 0.4000 | 0.2500 | 0.6000 | 0.0843 | -0.0322 | 6.3771 | -3.2703 | 1.1237 | 0.9429 | 0.3305 | 0.0115 | -0.0079 | -0.0094 | -0.0363 | 9.6474 | 0.0084 | 5.5500 | 5.5500 |
| opening_3d5d_stop_0.00x_10m | holdout_2025 | 39 | 26 | 0.3846 | 0.2564 | 0.5897 | 0.0148 | -0.0972 | 4.3763 | -4.8796 | 1.0865 | 0.9133 | 0.2364 | 0.0146 | -0.0214 | -0.0242 | -0.0841 | 9.2560 | 0.0092 | 5.1282 | 5.1282 |
| opening_3d5d_stop_0.25x_10m | all | 59 | 42 | 0.4068 | 0.2373 | 0.5424 | 0.0835 | -0.0115 | 9.7832 | 1.1706 | 1.1902 | 1.0207 | 0.5680 | 0.0546 | 0.0024 | 0.0013 | -0.0551 | 8.6125 | 0.0100 | 6.1356 | 6.1356 |
| opening_3d5d_stop_0.25x_10m | development_2024 | 20 | 16 | 0.4000 | 0.2000 | 0.5500 | 0.0896 | -0.0120 | 7.2600 | -1.8950 | 1.1402 | 0.9665 | 0.3965 | 0.0132 | -0.0052 | -0.0062 | -0.0397 | 9.1550 | 0.0098 | 6.5500 | 6.5500 |
| opening_3d5d_stop_0.25x_10m | holdout_2025 | 39 | 26 | 0.4103 | 0.2564 | 0.5385 | 0.0805 | -0.0113 | 11.0771 | 2.7428 | 1.2162 | 1.0486 | 0.6645 | 0.0409 | 0.0077 | 0.0087 | -0.0551 | 8.3343 | 0.0100 | 5.9231 | 5.9231 |
| opening_3d5d_stop_0.50x_10m | all | 51 | 42 | 0.5294 | 0.0392 | 0.2157 | 0.1060 | 0.0525 | 10.6017 | 5.2966 | 1.3612 | 1.1670 | 0.9992 | 0.0538 | 0.0257 | 0.0134 | -0.0327 | 5.3051 | 0.0100 | 8.8039 | 8.8039 |
| opening_3d5d_stop_0.50x_10m | development_2024 | 19 | 16 | 0.4737 | 0.1053 | 0.2105 | 0.1822 | 0.1194 | 17.7769 | 11.5652 | 1.5764 | 1.3461 | 1.4309 | 0.0335 | 0.0214 | 0.0255 | -0.0169 | 6.2116 | 0.0100 | 8.5263 | 8.5263 |
| opening_3d5d_stop_0.50x_10m | holdout_2025 | 32 | 26 | 0.5625 | 0.0000 | 0.2188 | 0.0608 | 0.0128 | 6.3414 | 1.5747 | 1.2228 | 1.0513 | 0.6652 | 0.0196 | 0.0042 | 0.0047 | -0.0327 | 4.7668 | 0.0100 | 8.9688 | 8.9688 |
| opening_3d5d_stop_0.75x_10m | all | 48 | 42 | 0.5833 | 0.0208 | 0.0417 | 0.1541 | 0.1185 | 15.4112 | 11.8526 | 2.0041 | 1.7104 | 2.1654 | 0.0759 | 0.0577 | 0.0300 | -0.0175 | 3.5585 | 0.0100 | 9.8958 | 9.8958 |
| opening_3d5d_stop_0.75x_10m | development_2024 | 18 | 16 | 0.5000 | 0.0556 | 0.0000 | 0.2439 | 0.2019 | 24.3943 | 20.1946 | 2.7546 | 2.3155 | 2.9043 | 0.0444 | 0.0366 | 0.0437 | -0.0080 | 4.1997 | 0.0100 | 9.9444 | 9.9444 |
| opening_3d5d_stop_0.75x_10m | holdout_2025 | 30 | 26 | 0.6333 | 0.0000 | 0.0667 | 0.1002 | 0.0685 | 10.0213 | 6.8475 | 1.6180 | 1.3917 | 1.5788 | 0.0301 | 0.0204 | 0.0231 | -0.0175 | 3.1738 | 0.0100 | 9.8667 | 9.8667 |
| opening_3d5d_stop_1.00x_10m | all | 47 | 42 | 0.5745 | 0.0000 | 0.0213 | 0.1107 | 0.0841 | 11.0698 | 8.4061 | 1.8935 | 1.6268 | 2.0779 | 0.0529 | 0.0398 | 0.0208 | -0.0164 | 2.6638 | 0.0100 | 10.0000 | 10.0000 |
| opening_3d5d_stop_1.00x_10m | development_2024 | 18 | 16 | 0.5000 | 0.0000 | 0.0000 | 0.1866 | 0.1551 | 18.6604 | 15.5106 | 2.7895 | 2.3472 | 2.9621 | 0.0339 | 0.0281 | 0.0335 | -0.0060 | 3.1498 | 0.0100 | 10.0000 | 10.0000 |
| opening_3d5d_stop_1.00x_10m | holdout_2025 | 29 | 26 | 0.6207 | 0.0000 | 0.0345 | 0.0636 | 0.0400 | 6.3585 | 3.9964 | 1.4673 | 1.2739 | 1.3459 | 0.0184 | 0.0114 | 0.0129 | -0.0164 | 2.3621 | 0.0100 | 10.0000 | 10.0000 |
| 1m_focus_15m_context_10m | all | 216 | 92 | 0.3472 | 0.2269 | 0.5880 | -0.0530 | -0.2133 | -4.1879 | -13.7350 | 0.9009 | 0.7166 | -0.2193 | -0.0947 | -0.2635 | -0.1489 | -0.2571 | 9.5470 | 0.0066 | 4.9213 | 4.9213 |
| 1m_focus_15m_context_10m | development_2024 | 118 | 49 | 0.3729 | 0.2542 | 0.5508 | 0.0428 | -0.1312 | 2.9378 | -6.7596 | 1.0804 | 0.8408 | 0.1515 | 0.0306 | -0.0808 | -0.0858 | -0.1205 | 9.6974 | 0.0059 | 4.9831 | 4.9831 |
| 1m_focus_15m_context_10m | holdout_2025 | 98 | 43 | 0.3163 | 0.1939 | 0.6327 | -0.1685 | -0.3121 | -12.7679 | -22.1339 | 0.7405 | 0.6025 | -0.6816 | -0.1215 | -0.1987 | -0.2157 | -0.2011 | 9.3660 | 0.0077 | 4.8469 | 4.8469 |
| 1m_focus_15m_context_15m | all | 213 | 92 | 0.3192 | 0.2770 | 0.6526 | -0.0672 | -0.2272 | -4.7532 | -14.2939 | 0.8959 | 0.7258 | -0.2491 | -0.1053 | -0.2700 | -0.1528 | -0.2659 | 9.5407 | 0.0066 | 5.6056 | 5.6056 |
| 1m_focus_15m_context_15m | development_2024 | 116 | 49 | 0.3448 | 0.3017 | 0.6207 | 0.0082 | -0.1641 | 0.4959 | -9.1963 | 1.0121 | 0.8049 | 0.0256 | 0.0008 | -0.1056 | -0.1121 | -0.1293 | 9.6922 | 0.0059 | 5.7155 | 5.7155 |
| 1m_focus_15m_context_15m | holdout_2025 | 97 | 43 | 0.2887 | 0.2474 | 0.6907 | -0.1573 | -0.3028 | -11.0305 | -20.3900 | 0.7854 | 0.6490 | -0.5893 | -0.1061 | -0.1838 | -0.1997 | -0.1887 | 9.3595 | 0.0077 | 5.4742 | 5.4742 |
| 15m_focus_context_15m | all | 247 | 108 | 0.3927 | 0.3441 | 0.5870 | 0.1365 | -0.0238 | 11.4739 | 1.9372 | 1.2811 | 1.0416 | 0.6016 | 0.3097 | 0.0350 | 0.0183 | -0.1312 | 9.5368 | 0.0069 | 5.5870 | 5.5870 |
| 15m_focus_context_15m | development_2024 | 128 | 55 | 0.4375 | 0.3750 | 0.5391 | 0.2532 | 0.0843 | 17.4065 | 7.7244 | 1.4860 | 1.1875 | 0.8989 | 0.2417 | 0.0971 | 0.1037 | -0.0699 | 9.6820 | 0.0062 | 5.9609 | 5.9609 |
| 15m_focus_context_15m | holdout_2025 | 119 | 53 | 0.3445 | 0.3109 | 0.6387 | 0.0110 | -0.1402 | 5.0927 | -4.2878 | 1.1102 | 0.9180 | 0.2715 | 0.0548 | -0.0566 | -0.0619 | -0.1312 | 9.3805 | 0.0077 | 5.1849 | 5.1849 |

## Session bootstrap

| variant | scope | setup | sessions | mean_session_return_bps | bootstrap_mean_ci_low_bps | bootstrap_mean_ci_high_bps | bootstrap_probability_mean_positive |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1m_cross_10m | all | all | 297 | -23.4388 | -44.3818 | -1.3415 | 0.0178 |
| 1m_cross_10m | development_2024 | all | 154 | -24.3302 | -55.7428 | 8.2798 | 0.0660 |
| 1m_cross_10m | holdout_2025 | all | 143 | -22.4789 | -49.4312 | 6.0035 | 0.0592 |
| 1m_acceptance_10m | all | all | 270 | -15.3808 | -36.6596 | 5.6799 | 0.0760 |
| 1m_acceptance_10m | development_2024 | all | 139 | -28.0321 | -58.2842 | 1.3693 | 0.0316 |
| 1m_acceptance_10m | holdout_2025 | all | 131 | -1.9570 | -31.4056 | 28.2865 | 0.4404 |
| 15m_acceptance_10m | all | all | 264 | -20.6728 | -40.0577 | -0.4886 | 0.0228 |
| 15m_acceptance_10m | development_2024 | all | 137 | -19.8164 | -46.6310 | 7.5010 | 0.0718 |
| 15m_acceptance_10m | holdout_2025 | all | 127 | -21.5967 | -49.1517 | 7.4017 | 0.0716 |
| 1m_focus_acceptance_10m | all | all | 114 | -17.3664 | -48.7107 | 14.5754 | 0.1390 |
| 1m_focus_acceptance_10m | development_2024 | all | 58 | -9.9248 | -50.1271 | 29.9317 | 0.3140 |
| 1m_focus_acceptance_10m | holdout_2025 | all | 56 | -25.0737 | -70.7142 | 26.7568 | 0.1604 |
| 1m_acceptance_3d_10m | all | all | 151 | -21.0394 | -47.9602 | 7.2999 | 0.0652 |
| 1m_acceptance_3d_10m | development_2024 | all | 75 | -17.6940 | -56.0247 | 21.1131 | 0.1894 |
| 1m_acceptance_3d_10m | holdout_2025 | all | 76 | -24.3408 | -59.7913 | 16.1363 | 0.1144 |
| 1m_acceptance_5d_10m | all | all | 125 | -18.8737 | -44.9486 | 9.5377 | 0.0916 |
| 1m_acceptance_5d_10m | development_2024 | all | 65 | -24.4064 | -63.9798 | 16.5832 | 0.1184 |
| 1m_acceptance_5d_10m | holdout_2025 | all | 60 | -12.8799 | -49.8744 | 24.9326 | 0.2514 |
| 1m_acceptance_3d_or_5d_10m | all | all | 177 | -23.4616 | -49.0299 | 2.6967 | 0.0388 |
| 1m_acceptance_3d_or_5d_10m | development_2024 | all | 90 | -28.7135 | -65.3474 | 8.9133 | 0.0628 |
| 1m_acceptance_3d_or_5d_10m | holdout_2025 | all | 87 | -18.0287 | -52.3827 | 18.5879 | 0.1642 |
| 1m_acceptance_3d_or_5d_opening_10m | all | all | 73 | 1.1608 | -31.8090 | 32.6720 | 0.5262 |
| 1m_acceptance_3d_or_5d_opening_10m | development_2024 | all | 33 | 7.7790 | -39.2520 | 55.0178 | 0.6284 |
| 1m_acceptance_3d_or_5d_opening_10m | holdout_2025 | all | 40 | -4.2993 | -51.2703 | 38.6293 | 0.4364 |
| opening_3d5d_stop_0.00x_10m | all | all | 42 | -6.0735 | -47.8660 | 35.6912 | 0.3980 |
| opening_3d5d_stop_0.00x_10m | development_2024 | all | 16 | -4.0688 | -68.8834 | 61.1311 | 0.4576 |
| opening_3d5d_stop_0.00x_10m | holdout_2025 | all | 26 | -7.3071 | -62.3684 | 46.0148 | 0.3898 |
| opening_3d5d_stop_0.25x_10m | all | all | 42 | 1.6459 | -43.8591 | 45.4264 | 0.5342 |
| opening_3d5d_stop_0.25x_10m | development_2024 | all | 16 | -2.4197 | -66.1305 | 62.6315 | 0.4740 |
| opening_3d5d_stop_0.25x_10m | holdout_2025 | all | 26 | 4.1478 | -57.3291 | 62.3852 | 0.5546 |
| opening_3d5d_stop_0.50x_10m | all | all | 42 | 6.4616 | -21.0976 | 34.5108 | 0.6694 |
| opening_3d5d_stop_0.50x_10m | development_2024 | all | 16 | 13.6919 | -33.0238 | 61.6353 | 0.6982 |
| opening_3d5d_stop_0.50x_10m | holdout_2025 | all | 26 | 2.0122 | -32.0757 | 35.0230 | 0.5416 |
| opening_3d5d_stop_0.75x_10m | all | all | 42 | 13.5496 | -4.2749 | 31.9229 | 0.9272 |
| opening_3d5d_stop_0.75x_10m | development_2024 | all | 16 | 22.7125 | -8.2708 | 56.8996 | 0.9112 |
| opening_3d5d_stop_0.75x_10m | holdout_2025 | all | 26 | 7.9109 | -13.6654 | 28.2335 | 0.7668 |
| opening_3d5d_stop_1.00x_10m | all | all | 42 | 9.4105 | -4.6116 | 23.9406 | 0.8972 |
| opening_3d5d_stop_1.00x_10m | development_2024 | all | 16 | 17.4458 | -6.2005 | 43.6042 | 0.9132 |
| opening_3d5d_stop_1.00x_10m | holdout_2025 | all | 26 | 4.4656 | -13.5026 | 20.8220 | 0.6946 |
| 1m_focus_15m_context_10m | all | all | 92 | -32.3340 | -59.0121 | -6.2509 | 0.0100 |

## 2025 cost sensitivity

| variant | scope | setup | one_way_cost_bps | trades | win_rate | average_net_return_bps | cumulative_net_return | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1m_cross_10m | holdout_2025 | all | 0.0000 | 538 | 0.3941 | 3.3909 | 0.1658 | -0.1891 |
| 1m_cross_10m | holdout_2025 | all | 0.1000 | 538 | 0.3941 | 1.5503 | 0.0559 | -0.2033 |
| 1m_cross_10m | holdout_2025 | all | 0.2500 | 538 | 0.3903 | -1.2105 | -0.0898 | -0.2466 |
| 1m_cross_10m | holdout_2025 | all | 0.5000 | 538 | 0.3866 | -5.8118 | -0.2895 | -0.3676 |
| 1m_cross_10m | holdout_2025 | all | 1.0000 | 538 | 0.3848 | -15.0146 | -0.5672 | -0.5807 |
| 1m_cross_10m | holdout_2025 | all | 1.5000 | 538 | 0.3680 | -24.2173 | -0.7365 | -0.7351 |
| 1m_cross_10m | holdout_2025 | all | 2.0000 | 538 | 0.3532 | -33.4200 | -0.8396 | -0.8381 |
| 1m_cross_10m | holdout_2025 | all | 3.0000 | 538 | 0.3253 | -51.8254 | -0.9407 | -0.9398 |
| 1m_cross_10m | holdout_2025 | all | 5.0000 | 538 | 0.2584 | -88.6363 | -0.9919 | -0.9918 |
| 1m_acceptance_10m | holdout_2025 | all | 0.0000 | 405 | 0.3926 | 8.6247 | 0.3875 | -0.0903 |
| 1m_acceptance_10m | holdout_2025 | all | 0.1000 | 405 | 0.3926 | 6.7776 | 0.2876 | -0.0955 |
| 1m_acceptance_10m | holdout_2025 | all | 0.2500 | 405 | 0.3901 | 4.0070 | 0.1510 | -0.1527 |
| 1m_acceptance_10m | holdout_2025 | all | 0.5000 | 405 | 0.3877 | -0.6107 | -0.0453 | -0.2428 |
| 1m_acceptance_10m | holdout_2025 | all | 1.0000 | 405 | 0.3852 | -9.8462 | -0.3434 | -0.4203 |
| 1m_acceptance_10m | holdout_2025 | all | 1.5000 | 405 | 0.3704 | -19.0816 | -0.5486 | -0.5840 |
| 1m_acceptance_10m | holdout_2025 | all | 2.0000 | 405 | 0.3654 | -28.3171 | -0.6897 | -0.7016 |
| 1m_acceptance_10m | holdout_2025 | all | 3.0000 | 405 | 0.3481 | -46.7879 | -0.8536 | -0.8517 |
| 1m_acceptance_10m | holdout_2025 | all | 5.0000 | 405 | 0.2716 | -83.7297 | -0.9675 | -0.9670 |
| 15m_acceptance_10m | holdout_2025 | all | 0.0000 | 350 | 0.3714 | 1.3940 | 0.0314 | -0.2147 |
| 15m_acceptance_10m | holdout_2025 | all | 0.1000 | 350 | 0.3686 | -0.4442 | -0.0329 | -0.2458 |
| 15m_acceptance_10m | holdout_2025 | all | 0.2500 | 350 | 0.3629 | -3.2015 | -0.1219 | -0.2901 |
| 15m_acceptance_10m | holdout_2025 | all | 0.5000 | 350 | 0.3543 | -7.7970 | -0.2525 | -0.3615 |
| 15m_acceptance_10m | holdout_2025 | all | 1.0000 | 350 | 0.3371 | -16.9879 | -0.4584 | -0.5124 |
| 15m_acceptance_10m | holdout_2025 | all | 1.5000 | 350 | 0.3286 | -26.1788 | -0.6077 | -0.6277 |
| 15m_acceptance_10m | holdout_2025 | all | 2.0000 | 350 | 0.3171 | -35.3698 | -0.7159 | -0.7164 |
| 15m_acceptance_10m | holdout_2025 | all | 3.0000 | 350 | 0.2914 | -53.7516 | -0.8512 | -0.8496 |
| 15m_acceptance_10m | holdout_2025 | all | 5.0000 | 350 | 0.2400 | -90.5154 | -0.9593 | -0.9587 |
| 1m_focus_acceptance_10m | holdout_2025 | all | 0.0000 | 154 | 0.3506 | 0.2116 | -0.0052 | -0.1072 |
| 1m_focus_acceptance_10m | holdout_2025 | all | 0.1000 | 154 | 0.3506 | -1.6712 | -0.0336 | -0.1194 |
| 1m_focus_acceptance_10m | holdout_2025 | all | 0.2500 | 154 | 0.3506 | -4.4953 | -0.0748 | -0.1389 |
| 1m_focus_acceptance_10m | holdout_2025 | all | 0.5000 | 154 | 0.3506 | -9.2022 | -0.1395 | -0.1759 |
| 1m_focus_acceptance_10m | holdout_2025 | all | 1.0000 | 154 | 0.3506 | -18.6160 | -0.2558 | -0.2571 |
| 1m_focus_acceptance_10m | holdout_2025 | all | 1.5000 | 154 | 0.3442 | -28.0297 | -0.3565 | -0.3558 |
| 1m_focus_acceptance_10m | holdout_2025 | all | 2.0000 | 154 | 0.3442 | -37.4435 | -0.4436 | -0.4419 |
| 1m_focus_acceptance_10m | holdout_2025 | all | 3.0000 | 154 | 0.3247 | -56.2710 | -0.5842 | -0.5813 |
| 1m_focus_acceptance_10m | holdout_2025 | all | 5.0000 | 154 | 0.2532 | -93.9261 | -0.7682 | -0.7651 |
| 1m_acceptance_3d_10m | holdout_2025 | all | 0.0000 | 193 | 0.3420 | -0.2173 | -0.0148 | -0.1209 |
| 1m_acceptance_3d_10m | holdout_2025 | all | 0.1000 | 193 | 0.3420 | -2.0958 | -0.0499 | -0.1391 |
| 1m_acceptance_3d_10m | holdout_2025 | all | 0.2500 | 193 | 0.3420 | -4.9137 | -0.1002 | -0.1656 |
| 1m_acceptance_3d_10m | holdout_2025 | all | 0.5000 | 193 | 0.3420 | -9.6101 | -0.1783 | -0.2119 |
| 1m_acceptance_3d_10m | holdout_2025 | all | 1.0000 | 193 | 0.3420 | -19.0030 | -0.3147 | -0.3236 |
| 1m_acceptance_3d_10m | holdout_2025 | all | 1.5000 | 193 | 0.3316 | -28.3959 | -0.4286 | -0.4311 |
| 1m_acceptance_3d_10m | holdout_2025 | all | 2.0000 | 193 | 0.3316 | -37.7887 | -0.5237 | -0.5222 |
| 1m_acceptance_3d_10m | holdout_2025 | all | 3.0000 | 193 | 0.3264 | -56.5745 | -0.6691 | -0.6668 |
| 1m_acceptance_3d_10m | holdout_2025 | all | 5.0000 | 193 | 0.2332 | -94.1459 | -0.8407 | -0.8385 |
| 1m_acceptance_5d_10m | holdout_2025 | all | 0.0000 | 141 | 0.3830 | 3.9750 | 0.0493 | -0.1043 |
| 1m_acceptance_5d_10m | holdout_2025 | all | 0.1000 | 141 | 0.3830 | 2.0998 | 0.0219 | -0.1105 |
| 1m_acceptance_5d_10m | holdout_2025 | all | 0.2500 | 141 | 0.3830 | -0.7131 | -0.0179 | -0.1304 |
| 1m_acceptance_5d_10m | holdout_2025 | all | 0.5000 | 141 | 0.3759 | -5.4012 | -0.0807 | -0.1673 |
| 1m_acceptance_5d_10m | holdout_2025 | all | 1.0000 | 141 | 0.3759 | -14.7774 | -0.1947 | -0.2525 |
| 1m_acceptance_5d_10m | holdout_2025 | all | 1.5000 | 141 | 0.3546 | -24.1536 | -0.2946 | -0.3301 |
| 1m_acceptance_5d_10m | holdout_2025 | all | 2.0000 | 141 | 0.3546 | -33.5298 | -0.3822 | -0.3997 |
| 1m_acceptance_5d_10m | holdout_2025 | all | 3.0000 | 141 | 0.3404 | -52.2822 | -0.5263 | -0.5307 |
| 1m_acceptance_5d_10m | holdout_2025 | all | 5.0000 | 141 | 0.2766 | -89.7870 | -0.7220 | -0.7217 |
| 1m_acceptance_3d_or_5d_10m | holdout_2025 | all | 0.0000 | 241 | 0.3651 | 2.8987 | 0.0575 | -0.1216 |
| 1m_acceptance_3d_or_5d_10m | holdout_2025 | all | 0.1000 | 241 | 0.3651 | 1.0281 | 0.0109 | -0.1425 |
| 1m_acceptance_3d_or_5d_10m | holdout_2025 | all | 0.2500 | 241 | 0.3651 | -1.7778 | -0.0552 | -0.1743 |
| 1m_acceptance_3d_or_5d_10m | holdout_2025 | all | 0.5000 | 241 | 0.3610 | -6.4544 | -0.1560 | -0.2308 |
| 1m_acceptance_3d_or_5d_10m | holdout_2025 | all | 1.0000 | 241 | 0.3610 | -15.8076 | -0.3265 | -0.3650 |
| 1m_acceptance_3d_or_5d_10m | holdout_2025 | all | 1.5000 | 241 | 0.3402 | -25.1607 | -0.4627 | -0.4828 |
| 1m_acceptance_3d_or_5d_10m | holdout_2025 | all | 2.0000 | 241 | 0.3402 | -34.5139 | -0.5714 | -0.5798 |
| 1m_acceptance_3d_or_5d_10m | holdout_2025 | all | 3.0000 | 241 | 0.3320 | -53.2202 | -0.7275 | -0.7279 |
| 1m_acceptance_3d_or_5d_10m | holdout_2025 | all | 5.0000 | 241 | 0.2614 | -90.6328 | -0.8902 | -0.8887 |
| 1m_acceptance_3d_or_5d_opening_10m | holdout_2025 | all | 0.0000 | 70 | 0.3857 | 6.9728 | 0.0454 | -0.0655 |
| 1m_acceptance_3d_or_5d_opening_10m | holdout_2025 | all | 0.1000 | 70 | 0.3857 | 5.0942 | 0.0318 | -0.0727 |
| 1m_acceptance_3d_or_5d_opening_10m | holdout_2025 | all | 0.2500 | 70 | 0.3857 | 2.2764 | 0.0116 | -0.0834 |
| 1m_acceptance_3d_or_5d_opening_10m | holdout_2025 | all | 0.5000 | 70 | 0.3857 | -2.4201 | -0.0211 | -0.1025 |
| 1m_acceptance_3d_or_5d_opening_10m | holdout_2025 | all | 1.0000 | 70 | 0.3857 | -11.8130 | -0.0835 | -0.1434 |
| 1m_acceptance_3d_or_5d_opening_10m | holdout_2025 | all | 1.5000 | 70 | 0.3714 | -21.2060 | -0.1419 | -0.1841 |
| 1m_acceptance_3d_or_5d_opening_10m | holdout_2025 | all | 2.0000 | 70 | 0.3714 | -30.5989 | -0.1966 | -0.2228 |
| 1m_acceptance_3d_or_5d_opening_10m | holdout_2025 | all | 3.0000 | 70 | 0.3714 | -49.3848 | -0.2960 | -0.3028 |
| 1m_acceptance_3d_or_5d_opening_10m | holdout_2025 | all | 5.0000 | 70 | 0.2714 | -86.9565 | -0.4598 | -0.4554 |
| opening_3d5d_stop_0.00x_10m | holdout_2025 | all | 0.0000 | 39 | 0.3846 | 4.3763 | 0.0146 | -0.0679 |
| opening_3d5d_stop_0.00x_10m | holdout_2025 | all | 0.1000 | 39 | 0.3846 | 2.5251 | 0.0073 | -0.0691 |
| opening_3d5d_stop_0.00x_10m | holdout_2025 | all | 0.2500 | 39 | 0.3846 | -0.2516 | -0.0036 | -0.0718 |
| opening_3d5d_stop_0.00x_10m | holdout_2025 | all | 0.5000 | 39 | 0.3846 | -4.8796 | -0.0214 | -0.0841 |
| opening_3d5d_stop_0.00x_10m | holdout_2025 | all | 1.0000 | 39 | 0.3846 | -14.1356 | -0.0562 | -0.1083 |
| opening_3d5d_stop_0.00x_10m | holdout_2025 | all | 1.5000 | 39 | 0.3590 | -23.3916 | -0.0897 | -0.1319 |
| opening_3d5d_stop_0.00x_10m | holdout_2025 | all | 2.0000 | 39 | 0.3590 | -32.6476 | -0.1221 | -0.1548 |
| opening_3d5d_stop_0.00x_10m | holdout_2025 | all | 3.0000 | 39 | 0.3590 | -51.1596 | -0.1835 | -0.2032 |

## Plots

- [Confirmation-clock forward returns](confirmation_clock_forward_returns.png)
- [One-minute acceptance timing](one_minute_acceptance_timing.png)
- [Strategy return curves and drawdowns](strategy_equity_and_drawdown.png)
- [One-minute POC case studies](one_minute_poc_case_studies.png)

## Causal contract

- Each 1d/3d/5d composite profile contains only complete sessions before the current session.
- A POC focus cluster means at least two composite POCs lie within 0.050 prior daily ATR of the crossed POC.
- The POC zone half-width is 0.025 prior daily ATR; these width choices are research assumptions, not fitted support/resistance facts.
- One-minute acceptance requires the next completed close to remain outside the POC band and on the directional side of session VWAP.
- Fifteen-minute acceptance is timestamped only on the block's final one-minute close. Entry is the following minute, so no unfinished 15-minute information is used.
- Completed 15-minute impulse requires above-median range and volume, plus a close in the directional 30% of the bar. Its references use prior complete blocks only.
- Trades enter on the next one-minute open, risk at most 1% at a one-minute ATR stop, are capped at 10x, target 2R, resolve same-bar ambiguity to the stop, and stop after three net losses in a session.
- The structural-stop sensitivity uses the larger of one-minute ATR and 0.00/0.25/0.50/0.75/1.00 times the previous completed 15-minute range. It applies only after that 15-minute bar is complete and is reported as an adaptive sweep.

## Limitations

- POC is approximated by assigning each one-minute bar's full volume to typical price. This is not true price-at-volume or order flow.
- Reusing 2024–2025 for multiple filters makes every subgroup exploratory; 2025 is no longer an untouched holdout.
- One-minute OHLC does not reveal whether the stop or target traded first, queue position, spreads, partial fills, or market impact. Stop-first resolution is conservative, but does not reconstruct the path.
- The instrument and venue are unverified and the price grid is inconsistent with CME NQ. The 0.50-bps one-way cost remains a scenario.
