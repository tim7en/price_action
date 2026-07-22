# Two-Minute Nasdaq POC, Trend, Scaling, and Trailing Study

Generated 2026-07-22T01:25:39.490792+00:00. This is a separate extension of the fixed-position New York-open baseline.

> The supplied Fabio notes document 1.5-ATR optional trailing stops and increasing risk only from the day's profits. They do not establish pyramiding into an open trade; the example payload says `pyramid: false`. The POC add-on below is our research hypothesis and is sized only from profit already locked by the raised base stop.

## Decision table

| variant | scope | trades | sessions | win_rate | target_rate | stop_rate | average_gross_r | average_net_r | average_gross_return_bps | average_net_return_bps | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_gross_return | cumulative_net_return | annualized_net_return | max_drawdown | average_notional_fraction | median_risk_fraction_deployed | average_holding_bars | average_holding_minutes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| static_10m | all | 83 | 83 | 0.4940 | 0.1084 | 0.2651 | 0.1661 | 0.0868 | 15.7669 | 8.1790 | 1.4850 | 1.2251 | 1.0390 | 0.1353 | 0.0661 | 0.0340 | -0.0478 | 7.5878 | 0.0100 | 2.7590 | 5.5181 |
| static_10m | development_2024 | 38 | 38 | 0.5000 | 0.1579 | 0.2895 | 0.1402 | 0.0608 | 13.5122 | 5.7771 | 1.3898 | 1.1497 | 0.8734 | 0.0506 | 0.0202 | 0.0207 | -0.0478 | 7.7351 | 0.0100 | 2.4474 | 4.8947 |
| static_10m | holdout_2025 | 45 | 45 | 0.4889 | 0.0667 | 0.2444 | 0.1880 | 0.1089 | 17.6708 | 10.2073 | 1.5757 | 1.2964 | 1.1838 | 0.0806 | 0.0450 | 0.0499 | -0.0415 | 7.4635 | 0.0100 | 3.0222 | 6.0444 |
| static_16m | all | 115 | 110 | 0.5217 | 0.1652 | 0.3478 | 0.2077 | 0.1280 | 19.5900 | 12.0021 | 1.5211 | 1.2919 | 1.2909 | 0.2442 | 0.1403 | 0.0711 | -0.0829 | 7.5879 | 0.0100 | 3.7565 | 7.5130 |
| static_16m | development_2024 | 58 | 56 | 0.5345 | 0.2069 | 0.3448 | 0.2659 | 0.1862 | 25.4506 | 17.7388 | 1.6836 | 1.4373 | 1.6501 | 0.1546 | 0.1042 | 0.1067 | -0.0429 | 7.7117 | 0.0100 | 3.3276 | 6.6552 |
| static_16m | holdout_2025 | 57 | 54 | 0.5088 | 0.1228 | 0.3509 | 0.1485 | 0.0689 | 13.6267 | 6.1648 | 1.3589 | 1.1479 | 0.9131 | 0.0776 | 0.0327 | 0.0363 | -0.0829 | 7.4619 | 0.0100 | 4.1930 | 8.3860 |
| static_20m | all | 122 | 116 | 0.4836 | 0.2049 | 0.4098 | 0.1798 | 0.0990 | 17.8602 | 10.1955 | 1.4217 | 1.2201 | 1.1651 | 0.2331 | 0.1231 | 0.0626 | -0.1423 | 7.6647 | 0.0100 | 4.5000 | 9.0000 |
| static_20m | development_2024 | 61 | 59 | 0.5082 | 0.2131 | 0.3934 | 0.2079 | 0.1280 | 20.4544 | 12.7096 | 1.4932 | 1.2815 | 1.3205 | 0.1281 | 0.0762 | 0.0780 | -0.0453 | 7.7448 | 0.0100 | 4.0492 | 8.0984 |
| static_20m | holdout_2025 | 61 | 57 | 0.4590 | 0.1967 | 0.4262 | 0.1517 | 0.0701 | 15.2660 | 7.6814 | 1.3531 | 1.1617 | 1.0064 | 0.0930 | 0.0436 | 0.0484 | -0.1423 | 7.5846 | 0.0100 | 4.9508 | 9.9016 |
| static_30m | all | 142 | 128 | 0.4437 | 0.2817 | 0.5000 | 0.1487 | 0.0672 | 15.2068 | 7.4780 | 1.3023 | 1.1367 | 0.9838 | 0.2268 | 0.0993 | 0.0508 | -0.1525 | 7.7288 | 0.0100 | 5.5070 | 11.0141 |
| static_30m | development_2024 | 73 | 65 | 0.4521 | 0.2877 | 0.4658 | 0.1822 | 0.1006 | 18.0158 | 10.0895 | 1.3611 | 1.1860 | 1.1365 | 0.1336 | 0.0699 | 0.0716 | -0.0839 | 7.9263 | 0.0100 | 5.1644 | 10.3288 |
| static_30m | holdout_2025 | 69 | 63 | 0.4348 | 0.2754 | 0.5362 | 0.1133 | 0.0319 | 12.2349 | 4.7151 | 1.2411 | 1.0854 | 0.8135 | 0.0822 | 0.0275 | 0.0305 | -0.1525 | 7.5198 | 0.0100 | 5.8696 | 11.7391 |
| trend_sized_16m | all | 115 | 110 | 0.5217 | 0.1652 | 0.3478 | 0.2077 | 0.1280 | 15.6487 | 9.4868 | 1.5306 | 1.2937 | 1.2698 | 0.1919 | 0.1105 | 0.0564 | -0.0620 | 6.1619 | 0.0075 | 3.7565 | 7.5130 |
| trend_sized_16m | development_2024 | 58 | 56 | 0.5345 | 0.2069 | 0.3448 | 0.2659 | 0.1862 | 18.1533 | 11.9733 | 1.6000 | 1.3633 | 1.4687 | 0.1083 | 0.0693 | 0.0710 | -0.0323 | 6.1800 | 0.0075 | 3.3276 | 6.6552 |
| trend_sized_16m | holdout_2025 | 57 | 54 | 0.5088 | 0.1228 | 0.3509 | 0.1485 | 0.0689 | 13.1001 | 6.9567 | 1.4561 | 1.2200 | 1.0662 | 0.0755 | 0.0385 | 0.0427 | -0.0620 | 6.1434 | 0.0075 | 4.1930 | 8.3860 |
| trend_trail_16m | all | 115 | 110 | 0.5217 | 0.1652 | 0.3478 | 0.1921 | 0.1125 | 14.5260 | 8.3641 | 1.4925 | 1.2590 | 1.1787 | 0.1768 | 0.0964 | 0.0493 | -0.0620 | 6.1619 | 0.0075 | 3.7304 | 7.4609 |
| trend_trail_16m | development_2024 | 58 | 56 | 0.5345 | 0.2069 | 0.3448 | 0.2385 | 0.1588 | 16.1014 | 9.9214 | 1.5322 | 1.3010 | 1.3027 | 0.0953 | 0.0568 | 0.0581 | -0.0323 | 6.1800 | 0.0075 | 3.2759 | 6.5517 |
| trend_trail_16m | holdout_2025 | 57 | 54 | 0.5088 | 0.1228 | 0.3509 | 0.1449 | 0.0653 | 12.9230 | 6.7796 | 1.4500 | 1.2144 | 1.0518 | 0.0744 | 0.0374 | 0.0415 | -0.0620 | 6.1434 | 0.0075 | 4.1930 | 8.3860 |
| trend_trail_poc_scale_16m | all | 115 | 110 | 0.5217 | 0.1652 | 0.3478 | 0.1921 | 0.1125 | 14.5260 | 8.3641 | 1.4925 | 1.2590 | 1.1787 | 0.1768 | 0.0964 | 0.0493 | -0.0620 | 6.1619 | 0.0075 | 3.7304 | 7.4609 |
| trend_trail_poc_scale_16m | development_2024 | 58 | 56 | 0.5345 | 0.2069 | 0.3448 | 0.2385 | 0.1588 | 16.1014 | 9.9214 | 1.5322 | 1.3010 | 1.3027 | 0.0953 | 0.0568 | 0.0581 | -0.0323 | 6.1800 | 0.0075 | 3.2759 | 6.5517 |
| trend_trail_poc_scale_16m | holdout_2025 | 57 | 54 | 0.5088 | 0.1228 | 0.3509 | 0.1449 | 0.0653 | 12.9230 | 6.7796 | 1.4500 | 1.2144 | 1.0518 | 0.0744 | 0.0374 | 0.0415 | -0.0620 | 6.1434 | 0.0075 | 4.1930 | 8.3860 |
| trend_trail_poc_scale_30m | all | 142 | 128 | 0.4718 | 0.2676 | 0.4789 | 0.1367 | 0.0551 | 11.5195 | 5.3160 | 1.3081 | 1.1305 | 0.9285 | 0.1694 | 0.0709 | 0.0365 | -0.1183 | 6.2034 | 0.0075 | 5.2676 | 10.5352 |
| trend_trail_poc_scale_30m | development_2024 | 73 | 65 | 0.4932 | 0.2740 | 0.4384 | 0.1723 | 0.0906 | 11.6372 | 5.2262 | 1.3128 | 1.1292 | 0.9076 | 0.0848 | 0.0352 | 0.0360 | -0.0723 | 6.4110 | 0.0075 | 4.8219 | 9.6438 |
| trend_trail_poc_scale_30m | holdout_2025 | 69 | 63 | 0.4493 | 0.2609 | 0.5217 | 0.0990 | 0.0176 | 11.3950 | 5.4111 | 1.3031 | 1.1318 | 0.9521 | 0.0780 | 0.0344 | 0.0382 | -0.1183 | 5.9839 | 0.0075 | 5.7391 | 11.4783 |
| reserved_poc_scale_16m | all | 115 | 110 | 0.5217 | 0.1652 | 0.3478 | 0.1924 | 0.1126 | 11.2680 | 6.4260 | 1.4951 | 1.2575 | 1.1636 | 0.1354 | 0.0740 | 0.0381 | -0.0509 | 4.8420 | 0.0056 | 3.7304 | 7.4609 |
| reserved_poc_scale_16m | development_2024 | 58 | 56 | 0.5345 | 0.2069 | 0.3448 | 0.2390 | 0.1591 | 12.4120 | 7.6053 | 1.5353 | 1.3009 | 1.2911 | 0.0731 | 0.0437 | 0.0447 | -0.0243 | 4.8068 | 0.0056 | 3.2759 | 6.5517 |
| reserved_poc_scale_16m | holdout_2025 | 57 | 54 | 0.5088 | 0.1228 | 0.3509 | 0.1449 | 0.0653 | 10.1040 | 5.2261 | 1.4527 | 1.2122 | 1.0357 | 0.0580 | 0.0291 | 0.0322 | -0.0509 | 4.8778 | 0.0056 | 4.1930 | 8.3860 |
| reserved_poc_scale_30m | all | 142 | 128 | 0.4718 | 0.2676 | 0.4789 | 0.1368 | 0.0552 | 8.1935 | 3.3410 | 1.2811 | 1.1051 | 0.8443 | 0.1187 | 0.0442 | 0.0229 | -0.0986 | 4.8525 | 0.0056 | 5.2676 | 10.5352 |
| reserved_poc_scale_30m | development_2024 | 73 | 65 | 0.4932 | 0.2740 | 0.4384 | 0.1726 | 0.0909 | 8.5146 | 3.5627 | 1.2982 | 1.1147 | 0.8597 | 0.0619 | 0.0242 | 0.0248 | -0.0580 | 4.9518 | 0.0056 | 4.8219 | 9.6438 |
| reserved_poc_scale_30m | holdout_2025 | 69 | 63 | 0.4493 | 0.2609 | 0.5217 | 0.0990 | 0.0176 | 7.8538 | 3.1064 | 1.2638 | 1.0954 | 0.8272 | 0.0534 | 0.0195 | 0.0216 | -0.0986 | 4.7474 | 0.0056 | 5.7391 | 11.4783 |

## Scaling audit

| variant | trades | trades_with_add_on | add_on_share | average_added_notional | minimum_scaled_trade_net_return |
| --- | --- | --- | --- | --- | --- |
| static_10m | 83 | 0 | 0.0000 | 0.0000 |  |
| static_16m | 115 | 0 | 0.0000 | 0.0000 |  |
| static_20m | 122 | 0 | 0.0000 | 0.0000 |  |
| static_30m | 142 | 0 | 0.0000 | 0.0000 |  |
| trend_sized_16m | 115 | 0 | 0.0000 | 0.0000 |  |
| trend_trail_16m | 115 | 0 | 0.0000 | 0.0000 |  |
| trend_trail_poc_scale_16m | 115 | 0 | 0.0000 | 0.0000 |  |
| trend_trail_poc_scale_30m | 142 | 0 | 0.0000 | 0.0000 |  |
| reserved_poc_scale_16m | 115 | 1 | 0.0087 | 0.7686 | 0.0143 |
| reserved_poc_scale_30m | 142 | 1 | 0.0070 | 0.7686 | 0.0143 |

## Scaling eligibility funnel

| variant | trades | trend_aligned_trades | trades_with_raised_stop | trades_crossing_prior_poc | aligned_trades_crossing_prior_poc | qualified_scale_signals | filled_add_ons |
| --- | --- | --- | --- | --- | --- | --- | --- |
| static_10m | 83 | 34 | 0 | 1 | 1 | 0 | 0 |
| static_16m | 115 | 42 | 0 | 6 | 3 | 0 | 0 |
| static_20m | 122 | 44 | 0 | 8 | 3 | 0 | 0 |
| static_30m | 142 | 49 | 0 | 9 | 3 | 0 | 0 |
| trend_sized_16m | 115 | 42 | 0 | 6 | 3 | 0 | 0 |
| trend_trail_16m | 115 | 42 | 24 | 6 | 3 | 0 | 0 |
| trend_trail_poc_scale_16m | 115 | 42 | 24 | 6 | 3 | 1 | 0 |
| trend_trail_poc_scale_30m | 142 | 49 | 40 | 9 | 3 | 1 | 0 |
| reserved_poc_scale_16m | 115 | 42 | 24 | 6 | 3 | 1 | 1 |
| reserved_poc_scale_30m | 142 | 49 | 40 | 9 | 3 | 1 | 1 |

## Session-block bootstrap

| variant | scope | setup | sessions | mean_session_return_bps | bootstrap_mean_ci_low_bps | bootstrap_mean_ci_high_bps | bootstrap_probability_mean_positive |
| --- | --- | --- | --- | --- | --- | --- | --- |
| static_10m | all | all | 83 | 8.1790 | -11.8525 | 29.4234 | 0.7802 |
| static_10m | development_2024 | all | 38 | 5.7771 | -25.7140 | 38.0152 | 0.6324 |
| static_10m | holdout_2025 | all | 45 | 10.2073 | -16.8248 | 37.3399 | 0.7678 |
| static_16m | all | all | 110 | 12.5600 | -8.1810 | 33.3459 | 0.8836 |
| static_16m | development_2024 | all | 56 | 18.3887 | -12.3231 | 48.0173 | 0.8794 |
| static_16m | holdout_2025 | all | 54 | 6.5154 | -20.8927 | 34.6779 | 0.6782 |
| static_20m | all | all | 116 | 10.7297 | -10.7480 | 32.2451 | 0.8402 |
| static_20m | development_2024 | all | 59 | 13.1516 | -16.7687 | 43.5509 | 0.8014 |
| static_20m | holdout_2025 | all | 57 | 8.2229 | -23.0010 | 38.9103 | 0.6902 |
| static_30m | all | all | 128 | 8.2854 | -14.3521 | 31.7667 | 0.7658 |
| static_30m | development_2024 | all | 65 | 11.3250 | -20.7771 | 45.0138 | 0.7584 |
| static_30m | holdout_2025 | all | 63 | 5.1493 | -26.2146 | 37.5170 | 0.6170 |
| trend_sized_16m | all | all | 110 | 9.9181 | -6.3672 | 26.2452 | 0.8858 |
| trend_sized_16m | development_2024 | all | 56 | 12.4084 | -11.9605 | 36.0456 | 0.8408 |
| trend_sized_16m | holdout_2025 | all | 54 | 7.3355 | -13.9657 | 29.5968 | 0.7430 |
| trend_trail_16m | all | all | 110 | 8.7444 | -7.5654 | 25.0094 | 0.8602 |
| trend_trail_16m | development_2024 | all | 56 | 10.2832 | -13.6522 | 33.7285 | 0.7928 |
| trend_trail_16m | holdout_2025 | all | 54 | 7.1485 | -14.0676 | 29.3312 | 0.7382 |
| trend_trail_poc_scale_16m | all | all | 110 | 8.7444 | -7.5654 | 25.0094 | 0.8602 |
| trend_trail_poc_scale_16m | development_2024 | all | 56 | 10.2832 | -13.6522 | 33.7285 | 0.7928 |
| trend_trail_poc_scale_16m | holdout_2025 | all | 54 | 7.1485 | -14.0676 | 29.3312 | 0.7382 |
| trend_trail_poc_scale_30m | all | all | 128 | 5.8737 | -11.3615 | 23.9758 | 0.7494 |
| trend_trail_poc_scale_30m | development_2024 | all | 65 | 5.8547 | -19.1502 | 30.9688 | 0.6790 |
| trend_trail_poc_scale_30m | holdout_2025 | all | 63 | 5.8933 | -18.4692 | 31.1052 | 0.6750 |
| reserved_poc_scale_16m | all | all | 110 | 6.7174 | -5.8107 | 19.1701 | 0.8566 |
| reserved_poc_scale_16m | development_2024 | all | 56 | 7.8803 | -10.5413 | 26.0578 | 0.7958 |
| reserved_poc_scale_16m | holdout_2025 | all | 54 | 5.5115 | -10.9870 | 22.8107 | 0.7356 |
| reserved_poc_scale_30m | all | all | 128 | 3.6914 | -9.5891 | 17.7264 | 0.7078 |
| reserved_poc_scale_30m | development_2024 | all | 65 | 3.9918 | -15.0971 | 23.1766 | 0.6626 |
| reserved_poc_scale_30m | holdout_2025 | all | 63 | 3.3814 | -15.7274 | 23.4143 | 0.6334 |

## Holdout cost sensitivity

| variant | scope | setup | one_way_cost_bps | trades | win_rate | average_net_return_bps | cumulative_net_return | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| static_10m | holdout_2025 | all | 0.0000 | 45 | 0.4889 | 17.6708 | 0.0806 | -0.0362 |
| static_10m | holdout_2025 | all | 0.1000 | 45 | 0.4889 | 16.1781 | 0.0734 | -0.0373 |
| static_10m | holdout_2025 | all | 0.2500 | 45 | 0.4889 | 13.9391 | 0.0626 | -0.0389 |
| static_10m | holdout_2025 | all | 0.5000 | 45 | 0.4889 | 10.2073 | 0.0450 | -0.0415 |
| static_10m | holdout_2025 | all | 1.0000 | 45 | 0.4889 | 2.7438 | 0.0105 | -0.0557 |
| static_10m | holdout_2025 | all | 1.5000 | 45 | 0.4667 | -4.7197 | -0.0229 | -0.0767 |
| static_10m | holdout_2025 | all | 2.0000 | 45 | 0.4222 | -12.1833 | -0.0552 | -0.0987 |
| static_10m | holdout_2025 | all | 3.0000 | 45 | 0.3556 | -27.1103 | -0.1168 | -0.1413 |
| static_10m | holdout_2025 | all | 5.0000 | 45 | 0.3333 | -56.9644 | -0.2283 | -0.2348 |
| static_16m | holdout_2025 | all | 0.0000 | 57 | 0.5263 | 13.6267 | 0.0776 | -0.0605 |
| static_16m | holdout_2025 | all | 0.1000 | 57 | 0.5263 | 12.1343 | 0.0685 | -0.0650 |
| static_16m | holdout_2025 | all | 0.2500 | 57 | 0.5263 | 9.8957 | 0.0549 | -0.0717 |
| static_16m | holdout_2025 | all | 0.5000 | 57 | 0.5088 | 6.1648 | 0.0327 | -0.0829 |
| static_16m | holdout_2025 | all | 1.0000 | 57 | 0.4912 | -1.2971 | -0.0103 | -0.1048 |
| static_16m | holdout_2025 | all | 1.5000 | 57 | 0.4912 | -8.7590 | -0.0515 | -0.1262 |
| static_16m | holdout_2025 | all | 2.0000 | 57 | 0.4386 | -16.2209 | -0.0911 | -0.1472 |
| static_16m | holdout_2025 | all | 3.0000 | 57 | 0.4211 | -31.1448 | -0.1655 | -0.1921 |
| static_16m | holdout_2025 | all | 5.0000 | 57 | 0.3333 | -60.9924 | -0.2967 | -0.3016 |
| static_20m | holdout_2025 | all | 0.0000 | 61 | 0.4754 | 15.2660 | 0.0930 | -0.1180 |
| static_20m | holdout_2025 | all | 0.1000 | 61 | 0.4754 | 13.7491 | 0.0830 | -0.1229 |
| static_20m | holdout_2025 | all | 0.2500 | 61 | 0.4754 | 11.4737 | 0.0681 | -0.1302 |
| static_20m | holdout_2025 | all | 0.5000 | 61 | 0.4590 | 7.6814 | 0.0436 | -0.1423 |
| static_20m | holdout_2025 | all | 1.0000 | 61 | 0.4262 | 0.0968 | -0.0036 | -0.1660 |
| static_20m | holdout_2025 | all | 1.5000 | 61 | 0.4098 | -7.4878 | -0.0487 | -0.1890 |
| static_20m | holdout_2025 | all | 2.0000 | 61 | 0.4098 | -15.0725 | -0.0918 | -0.2114 |
| static_20m | holdout_2025 | all | 3.0000 | 61 | 0.3607 | -30.2417 | -0.1723 | -0.2545 |
| static_20m | holdout_2025 | all | 5.0000 | 61 | 0.3279 | -60.5802 | -0.3129 | -0.3435 |
| static_30m | holdout_2025 | all | 0.0000 | 69 | 0.4348 | 12.2349 | 0.0822 | -0.1267 |
| static_30m | holdout_2025 | all | 0.1000 | 69 | 0.4348 | 10.7309 | 0.0710 | -0.1317 |
| static_30m | holdout_2025 | all | 0.2500 | 69 | 0.4348 | 8.4750 | 0.0545 | -0.1393 |
| static_30m | holdout_2025 | all | 0.5000 | 69 | 0.4348 | 4.7151 | 0.0275 | -0.1525 |
| static_30m | holdout_2025 | all | 1.0000 | 69 | 0.4203 | -2.8047 | -0.0245 | -0.1793 |
| static_30m | holdout_2025 | all | 1.5000 | 69 | 0.4058 | -10.3246 | -0.0739 | -0.2052 |
| static_30m | holdout_2025 | all | 2.0000 | 69 | 0.3913 | -17.8444 | -0.1208 | -0.2304 |
| static_30m | holdout_2025 | all | 3.0000 | 69 | 0.3913 | -32.8840 | -0.2078 | -0.2800 |
| static_30m | holdout_2025 | all | 5.0000 | 69 | 0.3478 | -62.9633 | -0.3571 | -0.3752 |
| trend_sized_16m | holdout_2025 | all | 0.0000 | 57 | 0.5263 | 13.1001 | 0.0755 | -0.0437 |
| trend_sized_16m | holdout_2025 | all | 0.1000 | 57 | 0.5263 | 11.8714 | 0.0680 | -0.0474 |
| trend_sized_16m | holdout_2025 | all | 0.2500 | 57 | 0.5263 | 10.0284 | 0.0568 | -0.0529 |
| trend_sized_16m | holdout_2025 | all | 0.5000 | 57 | 0.5088 | 6.9567 | 0.0385 | -0.0620 |
| trend_sized_16m | holdout_2025 | all | 1.0000 | 57 | 0.4912 | 0.8133 | 0.0028 | -0.0799 |
| trend_sized_16m | holdout_2025 | all | 1.5000 | 57 | 0.4912 | -5.3302 | -0.0318 | -0.0975 |
| trend_sized_16m | holdout_2025 | all | 2.0000 | 57 | 0.4386 | -11.4736 | -0.0651 | -0.1148 |
| trend_sized_16m | holdout_2025 | all | 3.0000 | 57 | 0.4211 | -23.7604 | -0.1285 | -0.1519 |
| trend_sized_16m | holdout_2025 | all | 5.0000 | 57 | 0.3333 | -48.3341 | -0.2429 | -0.2455 |
| trend_trail_16m | holdout_2025 | all | 0.0000 | 57 | 0.5263 | 12.9230 | 0.0744 | -0.0437 |
| trend_trail_16m | holdout_2025 | all | 0.1000 | 57 | 0.5263 | 11.6943 | 0.0669 | -0.0474 |
| trend_trail_16m | holdout_2025 | all | 0.2500 | 57 | 0.5263 | 9.8513 | 0.0557 | -0.0529 |
| trend_trail_16m | holdout_2025 | all | 0.5000 | 57 | 0.5088 | 6.7796 | 0.0374 | -0.0620 |
| trend_trail_16m | holdout_2025 | all | 1.0000 | 57 | 0.4912 | 0.6361 | 0.0017 | -0.0799 |
| trend_trail_16m | holdout_2025 | all | 1.5000 | 57 | 0.4912 | -5.5073 | -0.0327 | -0.0975 |
| trend_trail_16m | holdout_2025 | all | 2.0000 | 57 | 0.4211 | -11.6507 | -0.0661 | -0.1148 |
| trend_trail_16m | holdout_2025 | all | 3.0000 | 57 | 0.4035 | -23.9375 | -0.1294 | -0.1525 |
| trend_trail_16m | holdout_2025 | all | 5.0000 | 57 | 0.3333 | -48.5112 | -0.2437 | -0.2463 |
| trend_trail_poc_scale_16m | holdout_2025 | all | 0.0000 | 57 | 0.5263 | 12.9230 | 0.0744 | -0.0437 |
| trend_trail_poc_scale_16m | holdout_2025 | all | 0.1000 | 57 | 0.5263 | 11.6943 | 0.0669 | -0.0474 |
| trend_trail_poc_scale_16m | holdout_2025 | all | 0.2500 | 57 | 0.5263 | 9.8513 | 0.0557 | -0.0529 |
| trend_trail_poc_scale_16m | holdout_2025 | all | 0.5000 | 57 | 0.5088 | 6.7796 | 0.0374 | -0.0620 |
| trend_trail_poc_scale_16m | holdout_2025 | all | 1.0000 | 57 | 0.4912 | 0.6361 | 0.0017 | -0.0799 |
| trend_trail_poc_scale_16m | holdout_2025 | all | 1.5000 | 57 | 0.4912 | -5.5073 | -0.0327 | -0.0975 |
| trend_trail_poc_scale_16m | holdout_2025 | all | 2.0000 | 57 | 0.4211 | -11.6507 | -0.0661 | -0.1148 |
| trend_trail_poc_scale_16m | holdout_2025 | all | 3.0000 | 57 | 0.4035 | -23.9375 | -0.1294 | -0.1525 |
| trend_trail_poc_scale_16m | holdout_2025 | all | 5.0000 | 57 | 0.3333 | -48.5112 | -0.2437 | -0.2463 |
| trend_trail_poc_scale_30m | holdout_2025 | all | 0.0000 | 69 | 0.4493 | 11.3950 | 0.0780 | -0.0980 |
| trend_trail_poc_scale_30m | holdout_2025 | all | 0.1000 | 69 | 0.4493 | 10.1982 | 0.0692 | -0.1019 |
| trend_trail_poc_scale_30m | holdout_2025 | all | 0.2500 | 69 | 0.4493 | 8.4030 | 0.0560 | -0.1078 |
| trend_trail_poc_scale_30m | holdout_2025 | all | 0.5000 | 69 | 0.4493 | 5.4111 | 0.0344 | -0.1183 |
| trend_trail_poc_scale_30m | holdout_2025 | all | 1.0000 | 69 | 0.4348 | -0.5728 | -0.0074 | -0.1398 |
| trend_trail_poc_scale_30m | holdout_2025 | all | 1.5000 | 69 | 0.4203 | -6.5567 | -0.0476 | -0.1609 |
| trend_trail_poc_scale_30m | holdout_2025 | all | 2.0000 | 69 | 0.3768 | -12.5406 | -0.0862 | -0.1814 |
| trend_trail_poc_scale_30m | holdout_2025 | all | 3.0000 | 69 | 0.3768 | -24.5083 | -0.1588 | -0.2228 |
| trend_trail_poc_scale_30m | holdout_2025 | all | 5.0000 | 69 | 0.3188 | -48.4438 | -0.2874 | -0.3087 |
| reserved_poc_scale_16m | holdout_2025 | all | 0.0000 | 57 | 0.5263 | 10.1040 | 0.0580 | -0.0361 |
| reserved_poc_scale_16m | holdout_2025 | all | 0.1000 | 57 | 0.5263 | 9.1284 | 0.0522 | -0.0391 |
| reserved_poc_scale_16m | holdout_2025 | all | 0.2500 | 57 | 0.5263 | 7.6650 | 0.0434 | -0.0435 |
| reserved_poc_scale_16m | holdout_2025 | all | 0.5000 | 57 | 0.5088 | 5.2261 | 0.0291 | -0.0509 |
| reserved_poc_scale_16m | holdout_2025 | all | 1.0000 | 57 | 0.4912 | 0.3483 | 0.0008 | -0.0655 |
| reserved_poc_scale_16m | holdout_2025 | all | 1.5000 | 57 | 0.4912 | -4.5296 | -0.0266 | -0.0799 |
| reserved_poc_scale_16m | holdout_2025 | all | 2.0000 | 57 | 0.4211 | -9.4074 | -0.0533 | -0.0941 |
| reserved_poc_scale_16m | holdout_2025 | all | 3.0000 | 57 | 0.4035 | -19.1631 | -0.1046 | -0.1226 |

## Plots

- [Managed equity curves and drawdowns](managed_equity_and_drawdowns.png)
- [10/16/20/30-minute horizon comparison](horizon_comparison.png)

## Predeclared rules

- Signals remain the causal two-minute ORB/value-rejection signals from the first-hour model. The first 30 minutes is observation only.
- Static horizons end the execution phase 10, 16, 20, or 30 minutes after the observation window; open positions are closed at that phase boundary. Sixteen minutes is used because complete two-minute bars cannot represent 15 minutes without truncation or boundary leakage.
- Trend is causal and frozen at the signal: long only when signal price > prior-session SMA10 > SMA30, short for the inverse, otherwise neutral.
- Trend sizing risks 1.00% when aligned, 0.75% when neutral, and 0.50% when countertrend, always subject to the 10x notional cap.
- The reserved-scaling diagnostic starts with 75% of those risk allocations so an aligned trade can retain leverage capacity for an add-on. It was introduced after observing that the unconstrained signal was already at 10x, so it is diagnostic rather than validated.
- The trail activates after a completed close reaches +1R, locks +0.25R, and then follows the best completed close by 1.5 ATR. Stop changes apply only to subsequent bars.
- One add-on is eligible only after the stop is raised, trend is aligned, and an aggressive, delta-aligned completed bar crosses the 0.1-ATR band around one of the prior five completed-session POCs.
- The add-on enters at the next bar open, is capped at 50% of base size and the remaining 10x capacity, and its stop risk plus round-trip cost cannot exceed net base profit already locked by the protected stop.
- Same-bar stop/target ambiguity resolves to the stop. The 2R target and three-loss daily stop remain active.

## Limitations

- This evaluates several variants on the same 2024–2025 sample; 2025 is now an evaluation set, not a fresh untouched holdout.
- POCs allocate each bar's entire volume to typical price. They show estimated acceptance, not separate buyer/seller concentration.
- OHLCV cannot show aggressor side, footprint imbalance, resting liquidity, queue position, or the intrabar path. Scaling around POC therefore remains a proxy experiment.
- The feed has no verified venue or contract identity and is inconsistent with CME NQ's tick grid. The 0.50-bps one-way cost is a scenario, not measured execution.
