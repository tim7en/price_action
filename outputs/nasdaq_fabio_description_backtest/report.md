# Fabio-inspired description: literal OHLCV proxy test

## What was tested

This is one frozen interpretation of the attached prose, **not Fabio Valentini's actual strategy**. It uses a causal 50-bar/24-row typical-price profile, candle-volume delta proxy, 2x-volume and 0.3-ATR absorption, three-bar accumulation, aggressive expansion, session VWAP, a 30-minute ORB, one-ATR stop, 2R target, 30-minute maximum hold, 0.25% base risk, and a three-loss daily cutoff.

Value-area and Triple-A signals are allowed throughout the regular session. ORB signals are allowed only during minutes 30–60. Signals enter at the next bar; same-bar stop/target ambiguity goes to the stop.

## Fixed-risk results at 0.50 bps per side

| bar_minutes | scope | setup | trades | sessions | win_rate | average_net_r | profit_factor | cumulative_net_return | annualized_net_return | maximum_drawdown | average_risk_fraction | average_effective_leverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | all | all | 2112 | 477 | 0.3338 | -0.1736 | 0.7774 | -0.6022 | -0.3806 | -0.6074 | 0.0025 | 4.1928 |
| 1 | development_2024 | all | 1063 | 246 | 0.3208 | -0.2205 | 0.7229 | -0.4458 | -0.4478 | -0.4472 | 0.0025 | 4.3157 |
| 1 | holdout_2025 | all | 1049 | 231 | 0.3470 | -0.1261 | 0.8356 | -0.2823 | -0.3019 | -0.2974 | 0.0025 | 4.0683 |
| 2 | all | all | 1824 | 476 | 0.3350 | -0.1770 | 0.7594 | -0.5581 | -0.3458 | -0.5585 | 0.0025 | 3.1345 |
| 2 | development_2024 | all | 960 | 245 | 0.3354 | -0.1773 | 0.7596 | -0.3499 | -0.3516 | -0.3499 | 0.0025 | 3.1697 |
| 2 | holdout_2025 | all | 864 | 231 | 0.3345 | -0.1766 | 0.7592 | -0.3203 | -0.3419 | -0.3208 | 0.0025 | 3.0955 |
| 5 | all | all | 1282 | 466 | 0.4072 | -0.0355 | 0.9392 | -0.1129 | -0.0604 | -0.1811 | 0.0025 | 1.9584 |
| 5 | development_2024 | all | 664 | 240 | 0.3886 | -0.0483 | 0.9193 | -0.0800 | -0.0805 | -0.1109 | 0.0025 | 2.0224 |
| 5 | holdout_2025 | all | 618 | 226 | 0.4272 | -0.0217 | 0.9617 | -0.0358 | -0.0387 | -0.1033 | 0.0025 | 1.8896 |

The combined strategy fails at all three frequencies. The only positive branch is ORB-only: **1.81%** on two-minute bars and **2.52%** on five-minute bars over the full sample. Those are research leads, not Fabio-scale returns or independently selected winners.

## 2025 holdout by setup

| bar_minutes | scope | setup | trades | sessions | win_rate | average_net_r | profit_factor | cumulative_net_return | annualized_net_return | maximum_drawdown | average_risk_fraction | average_effective_leverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | holdout_2025 | all | 1049 | 231 | 0.3470 | -0.1261 | 0.8356 | -0.2823 | -0.3019 | -0.2974 | 0.0025 | 4.0683 |
| 1 | holdout_2025 | opening_range_breakout | 32 | 32 | 0.3750 | 0.0184 | 1.0266 | 0.0013 | 0.0014 | -0.0234 | 0.0025 | 2.6655 |
| 1 | holdout_2025 | value_area_bounce | 1017 | 231 | 0.3461 | -0.1306 | 0.8301 | -0.2832 | -0.3029 | -0.2950 | 0.0025 | 4.1125 |
| 2 | holdout_2025 | all | 864 | 231 | 0.3345 | -0.1766 | 0.7592 | -0.3203 | -0.3419 | -0.3208 | 0.0025 | 3.0955 |
| 2 | holdout_2025 | opening_range_breakout | 83 | 75 | 0.4217 | 0.0809 | 1.1337 | 0.0164 | 0.0182 | -0.0310 | 0.0025 | 1.9990 |
| 2 | holdout_2025 | value_area_bounce | 781 | 231 | 0.3252 | -0.2039 | 0.7269 | -0.3313 | -0.3535 | -0.3318 | 0.0025 | 3.2120 |
| 5 | holdout_2025 | all | 618 | 226 | 0.4272 | -0.0217 | 0.9617 | -0.0358 | -0.0387 | -0.1033 | 0.0025 | 1.8896 |
| 5 | holdout_2025 | opening_range_breakout | 96 | 90 | 0.4896 | 0.0387 | 1.0766 | 0.0089 | 0.0097 | -0.0226 | 0.0025 | 1.5252 |
| 5 | holdout_2025 | value_area_bounce | 522 | 217 | 0.4157 | -0.0328 | 0.9432 | -0.0443 | -0.0479 | -0.1242 | 0.0025 | 1.9566 |

## Signal funnel

| bar_minutes | setup | raw_signals | executed_trades |
| --- | --- | --- | --- |
| 1 | triple_a | 0 | 0 |
| 1 | opening_range_breakout | 127 | 89 |
| 1 | value_area_bounce | 6098 | 2023 |
| 2 | triple_a | 0 | 0 |
| 2 | opening_range_breakout | 287 | 186 |
| 2 | value_area_bounce | 3282 | 1638 |
| 5 | triple_a | 0 | 0 |
| 5 | opening_range_breakout | 249 | 178 |
| 5 | value_area_bounce | 1769 | 1104 |

## Cost sensitivity

| bar_minutes | setup | one_way_cost_bps | trades | sessions | win_rate | average_net_r | profit_factor | cumulative_net_return | annualized_net_return | maximum_drawdown | average_risk_fraction | average_effective_leverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | all | 0.0000 | 2112 | 477 | 0.3343 | -0.0042 | 0.9934 | -0.0354 | -0.0186 | -0.1597 | 0.0025 | 4.1928 |
| 1 | all | 0.2500 | 2112 | 477 | 0.3338 | -0.0889 | 0.8770 | -0.3805 | -0.2203 | -0.3985 | 0.0025 | 4.1928 |
| 1 | all | 0.5000 | 2112 | 477 | 0.3338 | -0.1736 | 0.7774 | -0.6022 | -0.3806 | -0.6074 | 0.0025 | 4.1928 |
| 1 | all | 1.0000 | 2112 | 477 | 0.3329 | -0.3430 | 0.6163 | -0.8360 | -0.6091 | -0.8362 | 0.0025 | 4.1928 |
| 1 | all | 1.5000 | 2112 | 477 | 0.3314 | -0.5125 | 0.4916 | -0.9324 | -0.7534 | -0.9324 | 0.0025 | 4.1928 |
| 1 | all | 2.0000 | 2112 | 477 | 0.3295 | -0.6819 | 0.3923 | -0.9722 | -0.8445 | -0.9722 | 0.0025 | 4.1928 |
| 1 | opening_range_breakout | 0.0000 | 89 | 86 | 0.2697 | -0.1910 | 0.7385 | -0.0421 | -0.0225 | -0.0608 | 0.0025 | 2.6987 |
| 1 | opening_range_breakout | 0.2500 | 89 | 86 | 0.2697 | -0.2450 | 0.6811 | -0.0535 | -0.0287 | -0.0678 | 0.0025 | 2.6987 |
| 1 | opening_range_breakout | 0.5000 | 89 | 86 | 0.2697 | -0.2990 | 0.6292 | -0.0648 | -0.0348 | -0.0750 | 0.0025 | 2.6987 |
| 1 | opening_range_breakout | 1.0000 | 89 | 86 | 0.2697 | -0.4069 | 0.5388 | -0.0870 | -0.0470 | -0.0911 | 0.0025 | 2.6987 |
| 1 | opening_range_breakout | 1.5000 | 89 | 86 | 0.2697 | -0.5149 | 0.4627 | -0.1087 | -0.0590 | -0.1122 | 0.0025 | 2.6987 |
| 1 | opening_range_breakout | 2.0000 | 89 | 86 | 0.2697 | -0.6228 | 0.3978 | -0.1299 | -0.0709 | -0.1330 | 0.0025 | 2.6987 |
| 2 | all | 0.0000 | 1824 | 476 | 0.3372 | -0.0515 | 0.9210 | -0.2172 | -0.1194 | -0.2653 | 0.0025 | 3.1345 |
| 2 | all | 0.2500 | 1824 | 476 | 0.3355 | -0.1143 | 0.8354 | -0.4118 | -0.2410 | -0.4254 | 0.0025 | 3.1345 |
| 2 | all | 0.5000 | 1824 | 476 | 0.3350 | -0.1770 | 0.7594 | -0.5581 | -0.3458 | -0.5585 | 0.0025 | 3.1345 |
| 2 | all | 1.0000 | 1824 | 476 | 0.3311 | -0.3024 | 0.6308 | -0.7506 | -0.5140 | -0.7507 | 0.0025 | 3.1345 |
| 2 | all | 1.5000 | 1824 | 476 | 0.3262 | -0.4278 | 0.5264 | -0.8593 | -0.6390 | -0.8593 | 0.0025 | 3.1345 |
| 2 | all | 2.0000 | 1824 | 476 | 0.3218 | -0.5532 | 0.4401 | -0.9206 | -0.7319 | -0.9206 | 0.0025 | 3.1345 |
| 2 | opening_range_breakout | 0.0000 | 186 | 170 | 0.4032 | 0.1208 | 1.2082 | 0.0566 | 0.0294 | -0.0218 | 0.0025 | 1.9973 |
| 2 | opening_range_breakout | 0.2500 | 186 | 170 | 0.4032 | 0.0809 | 1.1338 | 0.0372 | 0.0194 | -0.0264 | 0.0025 | 1.9973 |
| 2 | opening_range_breakout | 0.5000 | 186 | 170 | 0.4032 | 0.0409 | 1.0651 | 0.0181 | 0.0095 | -0.0310 | 0.0025 | 1.9973 |
| 2 | opening_range_breakout | 1.0000 | 186 | 170 | 0.3871 | -0.0390 | 0.9425 | -0.0190 | -0.0101 | -0.0401 | 0.0025 | 1.9973 |
| 2 | opening_range_breakout | 1.5000 | 186 | 170 | 0.3871 | -0.1189 | 0.8368 | -0.0548 | -0.0292 | -0.0607 | 0.0025 | 1.9973 |
| 2 | opening_range_breakout | 2.0000 | 186 | 170 | 0.3871 | -0.1987 | 0.7446 | -0.0893 | -0.0480 | -0.0936 | 0.0025 | 1.9973 |
| 5 | all | 0.0000 | 1282 | 466 | 0.4197 | 0.0429 | 1.0799 | 0.1402 | 0.0706 | -0.0661 | 0.0025 | 1.9584 |
| 5 | all | 0.2500 | 1282 | 466 | 0.4126 | 0.0037 | 1.0066 | 0.0057 | 0.0030 | -0.0903 | 0.0025 | 1.9584 |
| 5 | all | 0.5000 | 1282 | 466 | 0.4072 | -0.0355 | 0.9392 | -0.1129 | -0.0604 | -0.1811 | 0.0025 | 1.9584 |
| 5 | all | 1.0000 | 1282 | 466 | 0.3970 | -0.1138 | 0.8193 | -0.3099 | -0.1753 | -0.3524 | 0.0025 | 1.9584 |
| 5 | all | 1.5000 | 1282 | 466 | 0.3885 | -0.1921 | 0.7164 | -0.4632 | -0.2762 | -0.4907 | 0.0025 | 1.9584 |
| 5 | all | 2.0000 | 1282 | 466 | 0.3744 | -0.2705 | 0.6275 | -0.5825 | -0.3648 | -0.5998 | 0.0025 | 1.9584 |
| 5 | opening_range_breakout | 0.0000 | 178 | 169 | 0.4831 | 0.1218 | 1.2519 | 0.0548 | 0.0282 | -0.0203 | 0.0025 | 1.6019 |
| 5 | opening_range_breakout | 0.2500 | 178 | 169 | 0.4775 | 0.0898 | 1.1794 | 0.0399 | 0.0206 | -0.0215 | 0.0025 | 1.6019 |
| 5 | opening_range_breakout | 0.5000 | 178 | 169 | 0.4719 | 0.0577 | 1.1116 | 0.0252 | 0.0130 | -0.0226 | 0.0025 | 1.6019 |
| 5 | opening_range_breakout | 1.0000 | 178 | 169 | 0.4607 | -0.0064 | 0.9885 | -0.0036 | -0.0019 | -0.0249 | 0.0025 | 1.6019 |
| 5 | opening_range_breakout | 1.5000 | 178 | 169 | 0.4607 | -0.0704 | 0.8800 | -0.0317 | -0.0166 | -0.0374 | 0.0025 | 1.6019 |
| 5 | opening_range_breakout | 2.0000 | 178 | 169 | 0.4382 | -0.1345 | 0.7839 | -0.0589 | -0.0311 | -0.0610 | 0.0025 | 1.6019 |

## Session bootstrap

| bar_minutes | setup | variant | sessions | samples | return_p05 | return_median | return_p95 | probability_positive |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | all | fixed_0.25 | 477 | 5000 | -0.6862 | -0.6024 | -0.4902 | 0.0000 |
| 1 | all | profit_financed | 477 | 5000 | -0.7534 | -0.6607 | -0.5204 | 0.0000 |
| 1 | opening_range_breakout | fixed_0.25 | 86 | 5000 | -0.1108 | -0.0659 | -0.0130 | 0.0192 |
| 1 | opening_range_breakout | profit_financed | 86 | 5000 | -0.1108 | -0.0659 | -0.0130 | 0.0192 |
| 2 | all | fixed_0.25 | 476 | 5000 | -0.6452 | -0.5583 | -0.4522 | 0.0000 |
| 2 | all | profit_financed | 476 | 5000 | -0.7281 | -0.6468 | -0.5352 | 0.0000 |
| 2 | opening_range_breakout | fixed_0.25 | 170 | 5000 | -0.0568 | 0.0171 | 0.0983 | 0.6384 |
| 2 | opening_range_breakout | profit_financed | 170 | 5000 | -0.0568 | 0.0171 | 0.0984 | 0.6386 |
| 5 | all | fixed_0.25 | 466 | 5000 | -0.2656 | -0.1150 | 0.0566 | 0.1288 |
| 5 | all | profit_financed | 466 | 5000 | -0.3225 | -0.1561 | 0.0535 | 0.1032 |
| 5 | opening_range_breakout | fixed_0.25 | 169 | 5000 | -0.0384 | 0.0267 | 0.0961 | 0.7362 |
| 5 | opening_range_breakout | profit_financed | 169 | 5000 | -0.0385 | 0.0267 | 0.0961 | 0.7366 |

## Discrete MNQ sizing

Assumption: $1.50 round-turn fees plus 0.50 index points of round-turn slippage per contract. These are scenarios, not a broker quote.

| bar_minutes | setup | variant | starting_equity | zero_contract_skips | trades | sessions | win_rate | average_net_r | profit_factor | cumulative_net_return | annualized_net_return | maximum_drawdown | average_risk_fraction | average_effective_leverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | all | fixed_0.25 | 25000.0000 | 379 | 2112 | 477 | 0.2704 | -0.1180 | 0.8255 | -0.3257 | -0.1851 | -0.3288 | 0.0016 | 2.6929 |
| 1 | all | fixed_0.25 | 100000.0000 | 0 | 2112 | 477 | 0.3338 | -0.0943 | 0.8504 | -0.3838 | -0.2224 | -0.3939 | 0.0023 | 3.4740 |
| 1 | all | profit_financed | 25000.0000 | 303 | 2112 | 477 | 0.2860 | -0.1029 | 0.8803 | -0.3117 | -0.1764 | -0.3277 | 0.0022 | 3.5757 |
| 1 | all | profit_financed | 100000.0000 | 0 | 2112 | 477 | 0.3338 | -0.0943 | 0.8741 | -0.4209 | -0.2471 | -0.4510 | 0.0030 | 4.5239 |
| 1 | opening_range_breakout | fixed_0.25 | 25000.0000 | 13 | 89 | 86 | 0.2360 | -0.2312 | 0.7048 | -0.0291 | -0.0155 | -0.0375 | 0.0016 | 1.6800 |
| 1 | opening_range_breakout | fixed_0.25 | 100000.0000 | 0 | 89 | 86 | 0.2697 | -0.2462 | 0.6511 | -0.0507 | -0.0271 | -0.0618 | 0.0023 | 2.3015 |
| 1 | opening_range_breakout | profit_financed | 25000.0000 | 13 | 89 | 86 | 0.2360 | -0.2312 | 0.7048 | -0.0291 | -0.0155 | -0.0375 | 0.0016 | 1.6800 |
| 1 | opening_range_breakout | profit_financed | 100000.0000 | 0 | 89 | 86 | 0.2697 | -0.2462 | 0.6511 | -0.0507 | -0.0271 | -0.0618 | 0.0023 | 2.3015 |
| 2 | all | fixed_0.25 | 25000.0000 | 535 | 1824 | 476 | 0.2314 | -0.1414 | 0.7885 | -0.2950 | -0.1661 | -0.3013 | 0.0014 | 1.8434 |
| 2 | all | fixed_0.25 | 100000.0000 | 5 | 1824 | 476 | 0.3344 | -0.1196 | 0.8095 | -0.3987 | -0.2323 | -0.4030 | 0.0022 | 2.5953 |
| 2 | all | profit_financed | 25000.0000 | 543 | 1824 | 476 | 0.2341 | -0.1252 | 0.7729 | -0.3790 | -0.2192 | -0.3891 | 0.0017 | 2.2729 |
| 2 | all | profit_financed | 100000.0000 | 6 | 1824 | 476 | 0.3344 | -0.1191 | 0.8068 | -0.4812 | -0.2889 | -0.4900 | 0.0028 | 3.2690 |
| 2 | opening_range_breakout | fixed_0.25 | 25000.0000 | 67 | 186 | 170 | 0.2527 | 0.0414 | 1.0800 | 0.0103 | 0.0054 | -0.0215 | 0.0012 | 1.0567 |
| 2 | opening_range_breakout | fixed_0.25 | 100000.0000 | 1 | 186 | 170 | 0.3978 | 0.0599 | 1.0875 | 0.0203 | 0.0106 | -0.0234 | 0.0022 | 1.6906 |
| 2 | opening_range_breakout | profit_financed | 25000.0000 | 67 | 186 | 170 | 0.2527 | 0.0414 | 1.0800 | 0.0103 | 0.0054 | -0.0215 | 0.0012 | 1.0567 |
| 2 | opening_range_breakout | profit_financed | 100000.0000 | 1 | 186 | 170 | 0.3978 | 0.0599 | 1.0875 | 0.0203 | 0.0106 | -0.0234 | 0.0022 | 1.6906 |
| 5 | all | fixed_0.25 | 25000.0000 | 626 | 1282 | 466 | 0.2020 | -0.0275 | 0.9628 | -0.0281 | -0.0147 | -0.0718 | 0.0010 | 0.9485 |
| 5 | all | fixed_0.25 | 100000.0000 | 9 | 1282 | 466 | 0.4080 | -0.0038 | 0.9826 | -0.0296 | -0.0155 | -0.1042 | 0.0021 | 1.6365 |
| 5 | all | profit_financed | 25000.0000 | 587 | 1282 | 466 | 0.2090 | -0.0505 | 0.9040 | -0.0829 | -0.0440 | -0.0986 | 0.0012 | 1.1179 |
| 5 | all | profit_financed | 100000.0000 | 7 | 1282 | 466 | 0.4080 | -0.0053 | 0.9728 | -0.0528 | -0.0278 | -0.1336 | 0.0026 | 1.9244 |
| 5 | opening_range_breakout | fixed_0.25 | 25000.0000 | 105 | 178 | 169 | 0.1910 | 0.0408 | 1.1144 | 0.0087 | 0.0045 | -0.0168 | 0.0009 | 0.6698 |
| 5 | opening_range_breakout | fixed_0.25 | 100000.0000 | 2 | 178 | 169 | 0.4719 | 0.0720 | 1.1833 | 0.0333 | 0.0172 | -0.0160 | 0.0021 | 1.3335 |
| 5 | opening_range_breakout | profit_financed | 25000.0000 | 105 | 178 | 169 | 0.1910 | 0.0408 | 1.1144 | 0.0087 | 0.0045 | -0.0168 | 0.0009 | 0.6698 |
| 5 | opening_range_breakout | profit_financed | 100000.0000 | 2 | 178 | 169 | 0.4719 | 0.0720 | 1.1833 | 0.0333 | 0.0172 | -0.0160 | 0.0021 | 1.3335 |

## Mathematics of the published competition returns

This table shows the constant average net R per trade required if every trade risked exactly 0.25%. Real paths are variable, and profit-financed risk changes the equation.

| competition_period | target_return | assumed_trades | required_constant_net_return_per_trade | required_average_net_r_at_0_25pct_risk |
| --- | --- | --- | --- | --- |
| 2024_Q1 | 0.8950 | 100 | 0.0064 | 2.5651 |
| 2024_Q1 | 0.8950 | 300 | 0.0021 | 0.8532 |
| 2024_Q1 | 0.8950 | 500 | 0.0013 | 0.5117 |
| 2024_Q1 | 0.8950 | 1000 | 0.0006 | 0.2558 |
| 2024_Q4 | 2.1830 | 100 | 0.0116 | 4.6582 |
| 2024_Q4 | 2.1830 | 300 | 0.0039 | 1.5467 |
| 2024_Q4 | 2.1830 | 500 | 0.0023 | 0.9273 |
| 2024_Q4 | 2.1830 | 1000 | 0.0012 | 0.4634 |
| 2025_Q1 | 1.6970 | 100 | 0.0100 | 3.9883 |
| 2025_Q1 | 1.6970 | 300 | 0.0033 | 1.3250 |
| 2025_Q1 | 1.6970 | 500 | 0.0020 | 0.7945 |
| 2025_Q1 | 1.6970 | 1000 | 0.0010 | 0.3971 |

## Why Fabio-scale returns are mathematically possible

- The public 0.25% figure is described as base risk, not necessarily the maximum risk after an early-session profit. Profit can finance later size.
- Public descriptions say he takes hundreds of trades per quarter and scales winning sequences toward 3R, 5R, and 6R outcomes. High frequency and positive skew can compound quickly.
- The quarterly competition currently permits a $2,500 minimum starting balance and low day-trading margins. A small return denominator plus futures leverage can create very large percentage returns, although Fabio's actual starting balance and leverage path are not public.
- For example, +218.3% over 500 equal-risk trades requires about +0.93R net per trade at fixed 0.25% risk. The tested five-minute ORB proxy produced only +0.058R per trade.
- Competition standings verify the account return, not that a public prose description recreates the execution. They do not disclose Fabio's complete ledger, maximum drawdown, contract path, or all accounts he controlled.

Public workflow description: https://www.chartacademy.com/instructors/fabio-valentini

Official standings and organizer disclaimer: https://www.worldcupchampionships.com/world-cup-trading-championship-standings

Quarterly contest account and margin information: https://www.worldcupchampionships.com/quarterly-futures

## Limitations and decision

- OHLCV cannot observe bid/ask delta, footprint imbalance, resting liquidity, absorption, queue position, or tape speed. The core "Aggression" input is therefore missing.
- The source instrument is unverified and 94.1% of closes are off the CME NQ quarter-point grid.
- The rules absent from the prose were fixed once, not optimized. Alternative definitions are different strategies.
- The three frequencies share the same 2025 holdout; choosing the best after viewing it is not independent validation.
- Live deployment is blocked pending identified NQ/MNQ tick data, bid/ask volume, broker-specific costs, and a new forward period.
