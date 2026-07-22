# Two-Minute Nasdaq POC, Trend, Scaling, and Trailing Study

Generated 2026-07-22T01:44:47.751699+00:00. This is a separate extension of the fixed-position New York-open baseline.

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
| trend_3d_10d_sized_10m | all | 83 | 83 | 0.4940 | 0.1084 | 0.2651 | 0.1661 | 0.0868 | 12.2586 | 5.7625 | 1.4513 | 1.1895 | 0.9435 | 0.1042 | 0.0462 | 0.0239 | -0.0385 | 6.4961 | 0.0075 | 2.7590 | 5.5181 |
| trend_3d_10d_sized_10m | development_2024 | 38 | 38 | 0.5000 | 0.1579 | 0.2895 | 0.1402 | 0.0608 | 8.6168 | 2.0961 | 1.2948 | 1.0644 | 0.6607 | 0.0319 | 0.0067 | 0.0069 | -0.0385 | 6.5207 | 0.0075 | 2.4474 | 4.8947 |
| trend_3d_10d_sized_10m | holdout_2025 | 45 | 45 | 0.4889 | 0.0667 | 0.2444 | 0.1880 | 0.1089 | 15.3339 | 8.8586 | 1.6031 | 1.3097 | 1.1840 | 0.0700 | 0.0393 | 0.0436 | -0.0326 | 6.4753 | 0.0075 | 3.0222 | 6.0444 |
| trend_3d_10d_sized_16m | all | 115 | 110 | 0.5217 | 0.1652 | 0.3478 | 0.2077 | 0.1280 | 13.5865 | 7.2365 | 1.4300 | 1.2094 | 1.0698 | 0.1639 | 0.0820 | 0.0421 | -0.0780 | 6.3501 | 0.0075 | 3.7565 | 7.5130 |
| trend_3d_10d_sized_16m | development_2024 | 58 | 56 | 0.5345 | 0.2069 | 0.3448 | 0.2659 | 0.1862 | 17.1995 | 10.9276 | 1.5548 | 1.3240 | 1.3712 | 0.1022 | 0.0629 | 0.0644 | -0.0368 | 6.2719 | 0.0075 | 3.3276 | 6.6552 |
| trend_3d_10d_sized_16m | holdout_2025 | 57 | 54 | 0.5088 | 0.1228 | 0.3509 | 0.1485 | 0.0689 | 9.9102 | 3.4805 | 1.3077 | 1.0983 | 0.7707 | 0.0560 | 0.0180 | 0.0200 | -0.0780 | 6.4297 | 0.0075 | 4.1930 | 8.3860 |
| aligned_poc_immediate_10m | all | 13 | 13 | 0.3846 | 0.0769 | 0.3846 | -0.0455 | -0.1217 | -3.9501 | -11.1069 | 0.9226 | 0.8000 | -0.2760 | -0.0059 | -0.0151 | -0.0108 | -0.0447 | 7.1568 | 0.0100 | 2.6923 | 5.3846 |
| aligned_poc_immediate_10m | development_2024 | 6 | 6 | 0.1667 | 0.0000 | 0.5000 | -0.6878 | -0.7849 | -65.7156 | -74.5744 | 0.0980 | 0.0684 | -3.7091 | -0.0389 | -0.0440 | -0.0767 | -0.0354 | 8.8588 | 0.0097 | 2.3333 | 4.6667 |
| aligned_poc_immediate_10m | holdout_2025 | 7 | 7 | 0.5714 | 0.1429 | 0.2857 | 0.5051 | 0.4467 | 48.9918 | 43.2939 | 2.5167 | 2.2540 | 4.2991 | 0.0343 | 0.0302 | 0.0462 | -0.0208 | 5.6980 | 0.0100 | 3.0000 | 6.0000 |
| aligned_poc_acceptance_16m | all | 8 | 8 | 0.6250 | 0.1250 | 0.3750 | 0.1720 | 0.0965 | 14.3175 | 7.6746 | 1.3818 | 1.1928 | 1.0776 | 0.0111 | 0.0057 | 0.0060 | -0.0229 | 6.6429 | 0.0100 | 3.1250 | 6.2500 |
| aligned_poc_acceptance_16m | development_2024 | 4 | 4 | 0.5000 | 0.0000 | 0.5000 | -0.2897 | -0.3968 | -34.7408 | -43.6313 | 0.3052 | 0.1904 | -1.9538 | -0.0139 | -0.0174 | -0.0464 | -0.0214 | 8.8905 | 0.0091 | 2.0000 | 4.0000 |
| aligned_poc_acceptance_16m | holdout_2025 | 4 | 4 | 0.7500 | 0.2500 | 0.2500 | 0.6338 | 0.5898 | 63.3758 | 58.9804 | 3.5350 | 3.2916 | 7.2094 | 0.0254 | 0.0236 | 0.0820 | -0.0103 | 4.3954 | 0.0100 | 4.2500 | 8.5000 |
| aligned_poc_acceptance_reserved_16m | all | 8 | 8 | 0.6250 | 0.1250 | 0.3750 | 0.1278 | 0.0523 | 9.0408 | 3.5397 | 1.3214 | 1.1185 | 0.8217 | 0.0070 | 0.0026 | 0.0027 | -0.0172 | 5.5011 | 0.0075 | 3.0000 | 6.0000 |
| aligned_poc_acceptance_reserved_16m | development_2024 | 4 | 4 | 0.5000 | 0.0000 | 0.5000 | -0.2897 | -0.3968 | -22.8233 | -30.5290 | 0.3914 | 0.2447 | -1.4809 | -0.0092 | -0.0122 | -0.0327 | -0.0161 | 7.7057 | 0.0075 | 2.0000 | 4.0000 |
| aligned_poc_acceptance_reserved_16m | holdout_2025 | 4 | 4 | 0.7500 | 0.2500 | 0.2500 | 0.5454 | 0.5014 | 40.9048 | 37.6083 | 3.1816 | 2.9483 | 6.2043 | 0.0163 | 0.0150 | 0.0516 | -0.0077 | 3.2965 | 0.0075 | 4.0000 | 8.0000 |
| aligned_poc_acceptance_chart_scale_16m | all | 8 | 8 | 0.6250 | 0.1250 | 0.3750 | 0.1326 | 0.0562 | 9.3966 | 3.8345 | 1.3341 | 1.1284 | 0.8447 | 0.0073 | 0.0028 | 0.0030 | -0.0172 | 5.5621 | 0.0075 | 3.0000 | 6.0000 |
| aligned_poc_acceptance_chart_scale_16m | development_2024 | 4 | 4 | 0.5000 | 0.0000 | 0.5000 | -0.2897 | -0.3968 | -22.8233 | -30.5290 | 0.3914 | 0.2447 | -1.4809 | -0.0092 | -0.0122 | -0.0327 | -0.0161 | 7.7057 | 0.0075 | 2.0000 | 4.0000 |
| aligned_poc_acceptance_chart_scale_16m | holdout_2025 | 4 | 4 | 0.7500 | 0.2500 | 0.2500 | 0.5549 | 0.5093 | 41.6165 | 38.1979 | 3.2195 | 2.9788 | 6.0868 | 0.0166 | 0.0152 | 0.0525 | -0.0077 | 3.4186 | 0.0075 | 4.0000 | 8.0000 |
| reserved_3d_10d_trail_16m | all | 115 | 110 | 0.5217 | 0.1652 | 0.3478 | 0.1921 | 0.1125 | 9.8876 | 4.9466 | 1.4106 | 1.1876 | 1.0006 | 0.1175 | 0.0559 | 0.0288 | -0.0617 | 4.9409 | 0.0056 | 3.7304 | 7.4609 |
| reserved_3d_10d_trail_16m | development_2024 | 58 | 56 | 0.5345 | 0.2069 | 0.3448 | 0.2385 | 0.1588 | 11.8783 | 7.0467 | 1.5053 | 1.2754 | 1.2292 | 0.0698 | 0.0403 | 0.0413 | -0.0277 | 4.8316 | 0.0056 | 3.2759 | 6.5517 |
| reserved_3d_10d_trail_16m | holdout_2025 | 57 | 54 | 0.5088 | 0.1228 | 0.3509 | 0.1449 | 0.0653 | 7.8619 | 2.8097 | 1.3187 | 1.1035 | 0.7781 | 0.0446 | 0.0149 | 0.0165 | -0.0617 | 5.0522 | 0.0056 | 4.1930 | 8.3860 |
| reserved_chart_scale_16m | all | 115 | 110 | 0.5217 | 0.1652 | 0.3478 | 0.1923 | 0.1124 | 9.8973 | 4.9421 | 1.4110 | 1.1875 | 0.9987 | 0.1177 | 0.0558 | 0.0288 | -0.0617 | 4.9552 | 0.0056 | 3.7304 | 7.4609 |
| reserved_chart_scale_16m | development_2024 | 58 | 56 | 0.5345 | 0.2069 | 0.3448 | 0.2390 | 0.1591 | 11.9122 | 7.0674 | 1.5067 | 1.2762 | 1.2294 | 0.0700 | 0.0404 | 0.0414 | -0.0277 | 4.8448 | 0.0056 | 3.2759 | 6.5517 |
| reserved_chart_scale_16m | holdout_2025 | 57 | 54 | 0.5088 | 0.1228 | 0.3509 | 0.1447 | 0.0649 | 7.8470 | 2.7795 | 1.3181 | 1.1023 | 0.7743 | 0.0445 | 0.0148 | 0.0164 | -0.0617 | 5.0675 | 0.0056 | 4.1930 | 8.3860 |
| reserved_3d_10d_trail_30m | all | 142 | 128 | 0.4718 | 0.2676 | 0.4789 | 0.1367 | 0.0551 | 6.4083 | 1.4314 | 1.2067 | 1.0424 | 0.6438 | 0.0906 | 0.0162 | 0.0084 | -0.1170 | 4.9768 | 0.0056 | 5.2676 | 10.5352 |
| reserved_3d_10d_trail_30m | development_2024 | 73 | 65 | 0.4932 | 0.2740 | 0.4384 | 0.1723 | 0.0906 | 8.1968 | 3.2392 | 1.2794 | 1.1016 | 0.8267 | 0.0594 | 0.0217 | 0.0222 | -0.0594 | 4.9576 | 0.0056 | 4.8219 | 9.6438 |
| reserved_3d_10d_trail_30m | holdout_2025 | 69 | 63 | 0.4493 | 0.2609 | 0.5217 | 0.0990 | 0.0176 | 4.5160 | -0.4811 | 1.1378 | 0.9865 | 0.4519 | 0.0294 | -0.0055 | -0.0060 | -0.1170 | 4.9971 | 0.0056 | 5.7391 | 11.4783 |
| reserved_chart_scale_30m | all | 142 | 128 | 0.4718 | 0.2676 | 0.4789 | 0.1386 | 0.0567 | 6.5564 | 1.5479 | 1.2115 | 1.0458 | 0.6545 | 0.0928 | 0.0178 | 0.0093 | -0.1160 | 5.0086 | 0.0056 | 5.2676 | 10.5352 |
| reserved_chart_scale_30m | development_2024 | 73 | 65 | 0.4932 | 0.2740 | 0.4384 | 0.1726 | 0.0909 | 8.2237 | 3.2556 | 1.2804 | 1.1021 | 0.8276 | 0.0596 | 0.0219 | 0.0224 | -0.0594 | 4.9682 | 0.0056 | 4.8219 | 9.6438 |
| reserved_chart_scale_30m | holdout_2025 | 69 | 63 | 0.4493 | 0.2609 | 0.5217 | 0.1027 | 0.0205 | 4.7925 | -0.2588 | 1.1463 | 0.9928 | 0.4744 | 0.0314 | -0.0040 | -0.0044 | -0.1160 | 5.0513 | 0.0056 | 5.7391 | 11.4783 |
| trend_trail_16m | all | 115 | 110 | 0.5217 | 0.1652 | 0.3478 | 0.1921 | 0.1125 | 14.5260 | 8.3641 | 1.4925 | 1.2590 | 1.1787 | 0.1768 | 0.0964 | 0.0493 | -0.0620 | 6.1619 | 0.0075 | 3.7304 | 7.4609 |
| trend_trail_16m | development_2024 | 58 | 56 | 0.5345 | 0.2069 | 0.3448 | 0.2385 | 0.1588 | 16.1014 | 9.9214 | 1.5322 | 1.3010 | 1.3027 | 0.0953 | 0.0568 | 0.0581 | -0.0323 | 6.1800 | 0.0075 | 3.2759 | 6.5517 |
| trend_trail_16m | holdout_2025 | 57 | 54 | 0.5088 | 0.1228 | 0.3509 | 0.1449 | 0.0653 | 12.9230 | 6.7796 | 1.4500 | 1.2144 | 1.0518 | 0.0744 | 0.0374 | 0.0415 | -0.0620 | 6.1434 | 0.0075 | 4.1930 | 8.3860 |
| trend_trail_poc_scale_16m | all | 115 | 110 | 0.5217 | 0.1652 | 0.3478 | 0.1921 | 0.1125 | 14.5260 | 8.3641 | 1.4925 | 1.2590 | 1.1787 | 0.1768 | 0.0964 | 0.0493 | -0.0620 | 6.1619 | 0.0075 | 3.7304 | 7.4609 |
| trend_trail_poc_scale_16m | development_2024 | 58 | 56 | 0.5345 | 0.2069 | 0.3448 | 0.2385 | 0.1588 | 16.1014 | 9.9214 | 1.5322 | 1.3010 | 1.3027 | 0.0953 | 0.0568 | 0.0581 | -0.0323 | 6.1800 | 0.0075 | 3.2759 | 6.5517 |
| trend_trail_poc_scale_16m | holdout_2025 | 57 | 54 | 0.5088 | 0.1228 | 0.3509 | 0.1449 | 0.0653 | 12.9230 | 6.7796 | 1.4500 | 1.2144 | 1.0518 | 0.0744 | 0.0374 | 0.0415 | -0.0620 | 6.1434 | 0.0075 | 4.1930 | 8.3860 |
| trend_trail_poc_scale_30m | all | 142 | 128 | 0.4718 | 0.2676 | 0.4789 | 0.1367 | 0.0551 | 11.5195 | 5.3160 | 1.3081 | 1.1305 | 0.9285 | 0.1694 | 0.0709 | 0.0365 | -0.1183 | 6.2034 | 0.0075 | 5.2676 | 10.5352 |
| trend_trail_poc_scale_30m | development_2024 | 73 | 65 | 0.4932 | 0.2740 | 0.4384 | 0.1723 | 0.0906 | 11.6372 | 5.2262 | 1.3128 | 1.1292 | 0.9076 | 0.0848 | 0.0352 | 0.0360 | -0.0723 | 6.4110 | 0.0075 | 4.8219 | 9.6438 |
| trend_trail_poc_scale_30m | holdout_2025 | 69 | 63 | 0.4493 | 0.2609 | 0.5217 | 0.0990 | 0.0176 | 11.3950 | 5.4111 | 1.3031 | 1.1318 | 0.9521 | 0.0780 | 0.0344 | 0.0382 | -0.1183 | 5.9839 | 0.0075 | 5.7391 | 11.4783 |
| reserved_trend_trail_16m | all | 115 | 110 | 0.5217 | 0.1652 | 0.3478 | 0.1921 | 0.1125 | 11.2510 | 6.4156 | 1.4944 | 1.2571 | 1.1634 | 0.1352 | 0.0739 | 0.0380 | -0.0509 | 4.8353 | 0.0056 | 3.7304 | 7.4609 |
| reserved_trend_trail_16m | development_2024 | 58 | 56 | 0.5345 | 0.2069 | 0.3448 | 0.2385 | 0.1588 | 12.3782 | 7.5846 | 1.5339 | 1.3001 | 1.2911 | 0.0729 | 0.0436 | 0.0446 | -0.0243 | 4.7935 | 0.0056 | 3.2759 | 6.5517 |
| reserved_trend_trail_16m | holdout_2025 | 57 | 54 | 0.5088 | 0.1228 | 0.3509 | 0.1449 | 0.0653 | 10.1040 | 5.2261 | 1.4527 | 1.2122 | 1.0357 | 0.0580 | 0.0291 | 0.0322 | -0.0509 | 4.8778 | 0.0056 | 4.1930 | 8.3860 |
| reserved_poc_scale_16m | all | 115 | 110 | 0.5217 | 0.1652 | 0.3478 | 0.1924 | 0.1126 | 11.2680 | 6.4260 | 1.4951 | 1.2575 | 1.1636 | 0.1354 | 0.0740 | 0.0381 | -0.0509 | 4.8420 | 0.0056 | 3.7304 | 7.4609 |
| reserved_poc_scale_16m | development_2024 | 58 | 56 | 0.5345 | 0.2069 | 0.3448 | 0.2390 | 0.1591 | 12.4120 | 7.6053 | 1.5353 | 1.3009 | 1.2911 | 0.0731 | 0.0437 | 0.0447 | -0.0243 | 4.8068 | 0.0056 | 3.2759 | 6.5517 |
| reserved_poc_scale_16m | holdout_2025 | 57 | 54 | 0.5088 | 0.1228 | 0.3509 | 0.1449 | 0.0653 | 10.1040 | 5.2261 | 1.4527 | 1.2122 | 1.0357 | 0.0580 | 0.0291 | 0.0322 | -0.0509 | 4.8778 | 0.0056 | 4.1930 | 8.3860 |
| reserved_trend_trail_30m | all | 142 | 128 | 0.4718 | 0.2676 | 0.4789 | 0.1367 | 0.0551 | 8.1797 | 3.3326 | 1.2806 | 1.1048 | 0.8438 | 0.1185 | 0.0441 | 0.0228 | -0.0986 | 4.8471 | 0.0056 | 5.2676 | 10.5352 |
| reserved_trend_trail_30m | development_2024 | 73 | 65 | 0.4932 | 0.2740 | 0.4384 | 0.1723 | 0.0906 | 8.4877 | 3.5463 | 1.2972 | 1.1141 | 0.8588 | 0.0617 | 0.0241 | 0.0247 | -0.0580 | 4.9413 | 0.0056 | 4.8219 | 9.6438 |
| reserved_trend_trail_30m | holdout_2025 | 69 | 63 | 0.4493 | 0.2609 | 0.5217 | 0.0990 | 0.0176 | 7.8538 | 3.1064 | 1.2638 | 1.0954 | 0.8272 | 0.0534 | 0.0195 | 0.0216 | -0.0986 | 4.7474 | 0.0056 | 5.7391 | 11.4783 |
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
| trend_3d_10d_sized_10m | 83 | 0 | 0.0000 | 0.0000 |  |
| trend_3d_10d_sized_16m | 115 | 0 | 0.0000 | 0.0000 |  |
| aligned_poc_immediate_10m | 13 | 0 | 0.0000 | 0.0000 |  |
| aligned_poc_acceptance_16m | 8 | 0 | 0.0000 | 0.0000 |  |
| aligned_poc_acceptance_reserved_16m | 8 | 0 | 0.0000 | 0.0000 |  |
| aligned_poc_acceptance_chart_scale_16m | 8 | 1 | 0.1250 | 0.4882 | 0.0149 |
| reserved_3d_10d_trail_16m | 115 | 0 | 0.0000 | 0.0000 |  |
| reserved_chart_scale_16m | 115 | 2 | 0.0174 | 0.8187 | 0.0091 |
| reserved_3d_10d_trail_30m | 142 | 0 | 0.0000 | 0.0000 |  |
| reserved_chart_scale_30m | 142 | 3 | 0.0211 | 1.5019 | 0.0143 |
| trend_trail_16m | 115 | 0 | 0.0000 | 0.0000 |  |
| trend_trail_poc_scale_16m | 115 | 0 | 0.0000 | 0.0000 |  |
| trend_trail_poc_scale_30m | 142 | 0 | 0.0000 | 0.0000 |  |
| reserved_trend_trail_16m | 115 | 0 | 0.0000 | 0.0000 |  |
| reserved_poc_scale_16m | 115 | 1 | 0.0087 | 0.7686 | 0.0143 |
| reserved_trend_trail_30m | 142 | 0 | 0.0000 | 0.0000 |  |
| reserved_poc_scale_30m | 142 | 1 | 0.0070 | 0.7686 | 0.0143 |

## Scaling eligibility funnel

| variant | trades | trend_aligned_trades | trades_with_raised_stop | trades_crossing_prior_poc | aligned_trades_crossing_prior_poc | qualified_scale_signals | chart_acceptance_observations | filled_add_ons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| static_10m | 83 | 34 | 0 | 1 | 1 | 0 | 0 | 0 |
| static_16m | 115 | 42 | 0 | 6 | 3 | 0 | 5 | 0 |
| static_20m | 122 | 44 | 0 | 8 | 3 | 0 | 7 | 0 |
| static_30m | 142 | 49 | 0 | 9 | 3 | 0 | 9 | 0 |
| trend_sized_16m | 115 | 42 | 0 | 6 | 3 | 0 | 5 | 0 |
| trend_3d_10d_sized_10m | 83 | 38 | 0 | 1 | 0 | 0 | 0 | 0 |
| trend_3d_10d_sized_16m | 115 | 48 | 0 | 6 | 2 | 0 | 5 | 0 |
| aligned_poc_immediate_10m | 13 | 13 | 0 | 0 | 0 | 0 | 1 | 0 |
| aligned_poc_acceptance_16m | 8 | 8 | 0 | 0 | 0 | 0 | 1 | 0 |
| aligned_poc_acceptance_reserved_16m | 8 | 8 | 3 | 0 | 0 | 0 | 1 | 0 |
| aligned_poc_acceptance_chart_scale_16m | 8 | 8 | 3 | 0 | 0 | 1 | 1 | 1 |
| reserved_3d_10d_trail_16m | 115 | 48 | 24 | 6 | 2 | 0 | 5 | 0 |
| reserved_chart_scale_16m | 115 | 48 | 24 | 6 | 2 | 2 | 5 | 2 |
| reserved_3d_10d_trail_30m | 142 | 54 | 40 | 9 | 2 | 0 | 9 | 0 |
| reserved_chart_scale_30m | 142 | 54 | 40 | 9 | 2 | 3 | 9 | 3 |
| trend_trail_16m | 115 | 42 | 24 | 6 | 3 | 0 | 5 | 0 |
| trend_trail_poc_scale_16m | 115 | 42 | 24 | 6 | 3 | 1 | 5 | 0 |
| trend_trail_poc_scale_30m | 142 | 49 | 40 | 9 | 3 | 1 | 9 | 0 |
| reserved_trend_trail_16m | 115 | 42 | 24 | 6 | 3 | 0 | 5 | 0 |
| reserved_poc_scale_16m | 115 | 42 | 24 | 6 | 3 | 1 | 5 | 1 |
| reserved_trend_trail_30m | 142 | 49 | 40 | 9 | 3 | 0 | 9 | 0 |
| reserved_poc_scale_30m | 142 | 49 | 40 | 9 | 3 | 1 | 9 | 1 |

## Prior-session POC cross event study

| group | events | sessions | mean_max_favorable_10m_atr | mean_max_adverse_10m_atr | session_bootstrap_10m_ci_low_bps | session_bootstrap_10m_ci_high_bps | session_bootstrap_probability_10m_positive | mean_forward_2m_bps | median_forward_2m_bps | positive_forward_2m_share | mean_forward_4m_bps | median_forward_4m_bps | positive_forward_4m_share | mean_forward_6m_bps | median_forward_6m_bps | positive_forward_6m_share | mean_forward_10m_bps | median_forward_10m_bps | positive_forward_10m_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all_poc_crosses | 332 | 154 | 1.0047 | 1.0257 | -5.4013 | 3.1549 | 0.4586 | 0.7785 | 0.4124 | 0.5151 | 0.3284 | -0.0254 | 0.4970 | -0.6897 | -0.6390 | 0.4849 | -1.2306 | -0.5347 | 0.4880 |
| trend_10d_30d_aligned | 103 | 72 | 1.0221 | 0.9428 | -1.6580 | 5.1837 | 0.8534 | 0.4109 | 1.1602 | 0.5437 | 0.1512 | 0.9608 | 0.5534 | -0.7253 | 1.2826 | 0.5340 | 2.0866 | 3.1712 | 0.5728 |
| trend_3d_10d_aligned | 85 | 54 | 1.0692 | 0.9254 | -0.4527 | 7.5390 | 0.9580 | 0.7929 | 0.1336 | 0.5059 | 1.2813 | 0.2897 | 0.5294 | 2.1790 | 1.6698 | 0.5412 | 3.5105 | 4.8999 | 0.6000 |
| session_regime_aligned | 43 | 32 | 0.9742 | 0.8318 | -3.0509 | 7.3542 | 0.7900 | 1.0395 | 1.4164 | 0.5814 | 2.2158 | 2.8206 | 0.6744 | 1.8116 | 2.2507 | 0.6512 | 2.1576 | 3.5345 | 0.5581 |
| poc_migration_3d_aligned | 66 | 48 | 1.1356 | 0.8771 | 0.3840 | 10.3182 | 0.9836 | 1.0515 | 0.6676 | 0.5455 | 2.4640 | 0.2966 | 0.5303 | 3.5176 | 1.7621 | 0.6061 | 4.8602 | 4.6885 | 0.6212 |
| session_plus_3d_10d | 19 | 13 | 0.9716 | 0.7167 | -2.8222 | 10.1587 | 0.8478 | 0.5975 | 1.1602 | 0.5789 | 2.4110 | 2.8206 | 0.7368 | 2.6969 | 2.2507 | 0.6842 | 2.7687 | 3.5345 | 0.5789 |
| 3d_10d_plus_poc_migration | 32 | 23 | 1.0710 | 0.9084 | -0.2409 | 11.3935 | 0.9682 | 0.7024 | 0.6676 | 0.5312 | 0.8384 | 0.0666 | 0.5000 | 3.2392 | 2.9800 | 0.6250 | 5.4907 | 5.2038 | 0.6875 |
| session_trend_poc_migration | 4 | 3 | 1.0561 | 0.5306 | -0.7341 | 34.1129 | 0.9630 | 0.1699 | 0.5801 | 0.5000 | 3.7365 | 4.3184 | 1.0000 | 8.2813 | 2.9800 | 1.0000 | 9.3861 | 5.2038 | 0.7500 |
| aggression_and_delta_aligned | 150 | 101 | 1.0130 | 1.0686 | -11.0017 | 1.7805 | 0.1466 | -0.1573 | -1.0797 | 0.4667 | -0.0110 | 0.0461 | 0.5000 | -1.2356 | 0.5571 | 0.5133 | -2.7179 | -1.1934 | 0.4667 |
| 3d_10d_plus_aggression_delta | 43 | 32 | 1.2205 | 0.9307 | -3.4823 | 7.9593 | 0.8080 | 1.1843 | 1.2012 | 0.5349 | 1.1021 | 1.8877 | 0.5814 | 2.7204 | 5.5403 | 0.6279 | 3.0496 | 4.8999 | 0.5814 |

## POC crossing by execution timing

| group | events | sessions | mean_max_favorable_10m_atr | mean_max_adverse_10m_atr | session_bootstrap_10m_ci_low_bps | session_bootstrap_10m_ci_high_bps | session_bootstrap_probability_10m_positive | mean_forward_2m_bps | median_forward_2m_bps | positive_forward_2m_share | mean_forward_4m_bps | median_forward_4m_bps | positive_forward_4m_share | mean_forward_6m_bps | median_forward_6m_bps | positive_forward_6m_share | mean_forward_10m_bps | median_forward_10m_bps | positive_forward_10m_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| first_10m_after_observation | 131 | 92 | 1.1535 | 0.9978 | -0.2412 | 6.5495 | 0.9662 | 1.8519 | 1.2012 | 0.5802 | 0.9856 | 1.0368 | 0.5496 | -0.0911 | 0.7670 | 0.5115 | 1.3888 | 0.8051 | 0.5191 |
| middle_10m_after_observation | 99 | 67 | 0.9018 | 1.1311 | -17.3294 | 0.3997 | 0.0378 | -0.7188 | -0.3650 | 0.4646 | -0.1555 | -0.3981 | 0.4545 | -2.8709 | -1.6018 | 0.4646 | -6.1272 | -2.2362 | 0.4343 |
| last_10m_after_observation | 102 | 73 | 0.9133 | 0.9591 | -1.3260 | 5.1855 | 0.8714 | 0.8531 | -0.2531 | 0.4804 | -0.0458 | -0.4227 | 0.4706 | 0.6585 | -0.8695 | 0.4706 | 0.1581 | 0.0349 | 0.5000 |
| first_10m_and_3d_10d_aligned | 36 | 33 | 1.3398 | 0.9097 | -0.5173 | 10.7642 | 0.9632 | 2.5321 | 1.2513 | 0.5556 | 2.4455 | 0.8821 | 0.5556 | 2.5444 | 1.8138 | 0.5278 | 5.4306 | 6.2608 | 0.6667 |
| first_10m_3d_10d_poc_migration | 14 | 14 | 1.2947 | 1.0018 | -1.7822 | 14.6489 | 0.9380 | 1.3853 | 1.0347 | 0.5714 | -0.6444 | -1.2782 | 0.4286 | 1.7018 | 0.4338 | 0.5000 | 6.4313 | 5.2038 | 0.6429 |

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
| trend_3d_10d_sized_10m | all | all | 83 | 5.7625 | -10.8225 | 22.8747 | 0.7454 |
| trend_3d_10d_sized_10m | development_2024 | all | 38 | 2.0961 | -23.4146 | 28.5262 | 0.5576 |
| trend_3d_10d_sized_10m | holdout_2025 | all | 45 | 8.8586 | -14.0466 | 31.6199 | 0.7796 |
| trend_3d_10d_sized_16m | all | all | 110 | 7.5705 | -9.3372 | 24.1503 | 0.8136 |
| trend_3d_10d_sized_16m | development_2024 | all | 56 | 11.3254 | -13.4594 | 34.8990 | 0.8168 |
| trend_3d_10d_sized_16m | holdout_2025 | all | 54 | 3.6765 | -18.8639 | 26.5249 | 0.6260 |
| aligned_poc_immediate_10m | all | all | 13 | -11.1069 | -66.6259 | 48.9121 | 0.3420 |
| aligned_poc_immediate_10m | development_2024 | all | 6 | -74.5744 | -101.4364 | -30.8710 | 0.0006 |
| aligned_poc_immediate_10m | holdout_2025 | all | 7 | 43.2939 | -41.2745 | 123.6992 | 0.8484 |
| aligned_poc_acceptance_16m | all | all | 8 | 7.6746 | -60.0959 | 82.4176 | 0.5798 |
| aligned_poc_acceptance_16m | development_2024 | all | 4 | -43.6313 | -107.7810 | 20.5184 | 0.0580 |
| aligned_poc_acceptance_16m | holdout_2025 | all | 4 | 58.9804 | -54.9392 | 160.0042 | 0.8652 |
| aligned_poc_acceptance_reserved_16m | all | all | 8 | 3.5397 | -44.7531 | 58.9616 | 0.5436 |
| aligned_poc_acceptance_reserved_16m | development_2024 | all | 4 | -30.5290 | -80.8357 | 19.7778 | 0.0580 |
| aligned_poc_acceptance_reserved_16m | holdout_2025 | all | 4 | 37.6083 | -41.2044 | 113.3762 | 0.8482 |
| aligned_poc_acceptance_chart_scale_16m | all | all | 8 | 3.8345 | -44.7531 | 59.8460 | 0.5448 |
| aligned_poc_acceptance_chart_scale_16m | development_2024 | all | 4 | -30.5290 | -80.8357 | 19.7778 | 0.0580 |
| aligned_poc_acceptance_chart_scale_16m | holdout_2025 | all | 4 | 38.1979 | -41.2044 | 115.1451 | 0.8482 |
| reserved_3d_10d_trail_16m | all | all | 110 | 5.1740 | -7.7187 | 17.7735 | 0.7874 |
| reserved_3d_10d_trail_16m | development_2024 | all | 56 | 7.3019 | -11.0546 | 25.1917 | 0.7780 |
| reserved_3d_10d_trail_16m | holdout_2025 | all | 54 | 2.9673 | -14.5307 | 20.6252 | 0.6312 |
| reserved_chart_scale_16m | all | all | 110 | 5.1692 | -7.7195 | 17.7695 | 0.7880 |
| reserved_chart_scale_16m | development_2024 | all | 56 | 7.3232 | -11.0463 | 25.2558 | 0.7792 |
| reserved_chart_scale_16m | holdout_2025 | all | 54 | 2.9354 | -14.5405 | 20.5704 | 0.6290 |
| reserved_3d_10d_trail_30m | all | all | 128 | 1.5809 | -12.0126 | 16.3013 | 0.5942 |

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
| trend_3d_10d_sized_10m | holdout_2025 | all | 0.0000 | 45 | 0.4889 | 15.3339 | 0.0700 | -0.0284 |
| trend_3d_10d_sized_10m | holdout_2025 | all | 0.1000 | 45 | 0.4889 | 14.0389 | 0.0638 | -0.0292 |
| trend_3d_10d_sized_10m | holdout_2025 | all | 0.2500 | 45 | 0.4889 | 12.0963 | 0.0545 | -0.0305 |
| trend_3d_10d_sized_10m | holdout_2025 | all | 0.5000 | 45 | 0.4889 | 8.8586 | 0.0393 | -0.0326 |
| trend_3d_10d_sized_10m | holdout_2025 | all | 1.0000 | 45 | 0.4889 | 2.3833 | 0.0094 | -0.0467 |
| trend_3d_10d_sized_10m | holdout_2025 | all | 1.5000 | 45 | 0.4667 | -4.0920 | -0.0196 | -0.0672 |
| trend_3d_10d_sized_10m | holdout_2025 | all | 2.0000 | 45 | 0.4222 | -10.5674 | -0.0478 | -0.0872 |
| trend_3d_10d_sized_10m | holdout_2025 | all | 3.0000 | 45 | 0.3556 | -23.5180 | -0.1018 | -0.1261 |
| trend_3d_10d_sized_10m | holdout_2025 | all | 5.0000 | 45 | 0.3333 | -49.4193 | -0.2010 | -0.2089 |
| trend_3d_10d_sized_16m | holdout_2025 | all | 0.0000 | 57 | 0.5263 | 9.9102 | 0.0560 | -0.0581 |
| trend_3d_10d_sized_16m | holdout_2025 | all | 0.1000 | 57 | 0.5263 | 8.6242 | 0.0483 | -0.0621 |
| trend_3d_10d_sized_16m | holdout_2025 | all | 0.2500 | 57 | 0.5263 | 6.6953 | 0.0368 | -0.0681 |
| trend_3d_10d_sized_16m | holdout_2025 | all | 0.5000 | 57 | 0.5088 | 3.4805 | 0.0180 | -0.0780 |
| trend_3d_10d_sized_16m | holdout_2025 | all | 1.0000 | 57 | 0.4912 | -2.9491 | -0.0186 | -0.0975 |
| trend_3d_10d_sized_16m | holdout_2025 | all | 1.5000 | 57 | 0.4912 | -9.3788 | -0.0540 | -0.1166 |
| trend_3d_10d_sized_16m | holdout_2025 | all | 2.0000 | 57 | 0.4386 | -15.8084 | -0.0881 | -0.1353 |
| trend_3d_10d_sized_16m | holdout_2025 | all | 3.0000 | 57 | 0.4211 | -28.6677 | -0.1528 | -0.1793 |
| trend_3d_10d_sized_16m | holdout_2025 | all | 5.0000 | 57 | 0.3333 | -54.3863 | -0.2689 | -0.2745 |
| aligned_poc_immediate_10m | holdout_2025 | all | 0.0000 | 7 | 0.5714 | 48.9918 | 0.0343 | -0.0199 |
| aligned_poc_immediate_10m | holdout_2025 | all | 0.1000 | 7 | 0.5714 | 47.8522 | 0.0335 | -0.0201 |
| aligned_poc_immediate_10m | holdout_2025 | all | 0.2500 | 7 | 0.5714 | 46.1428 | 0.0323 | -0.0204 |
| aligned_poc_immediate_10m | holdout_2025 | all | 0.5000 | 7 | 0.5714 | 43.2939 | 0.0302 | -0.0208 |
| aligned_poc_immediate_10m | holdout_2025 | all | 1.0000 | 7 | 0.5714 | 37.5959 | 0.0262 | -0.0217 |
| aligned_poc_immediate_10m | holdout_2025 | all | 1.5000 | 7 | 0.5714 | 31.8979 | 0.0221 | -0.0227 |
| aligned_poc_immediate_10m | holdout_2025 | all | 2.0000 | 7 | 0.5714 | 26.1999 | 0.0180 | -0.0236 |
| aligned_poc_immediate_10m | holdout_2025 | all | 3.0000 | 7 | 0.5714 | 14.8040 | 0.0100 | -0.0254 |
| aligned_poc_immediate_10m | holdout_2025 | all | 5.0000 | 7 | 0.5714 | -7.9880 | -0.0060 | -0.0291 |
| aligned_poc_acceptance_16m | holdout_2025 | all | 0.0000 | 4 | 0.7500 | 63.3758 | 0.0254 | -0.0100 |
| aligned_poc_acceptance_16m | holdout_2025 | all | 0.1000 | 4 | 0.7500 | 62.4967 | 0.0250 | -0.0101 |
| aligned_poc_acceptance_16m | holdout_2025 | all | 0.2500 | 4 | 0.7500 | 61.1781 | 0.0245 | -0.0101 |
| aligned_poc_acceptance_16m | holdout_2025 | all | 0.5000 | 4 | 0.7500 | 58.9804 | 0.0236 | -0.0103 |
| aligned_poc_acceptance_16m | holdout_2025 | all | 1.0000 | 4 | 0.7500 | 54.5851 | 0.0218 | -0.0106 |
| aligned_poc_acceptance_16m | holdout_2025 | all | 1.5000 | 4 | 0.7500 | 50.1897 | 0.0200 | -0.0109 |
| aligned_poc_acceptance_16m | holdout_2025 | all | 2.0000 | 4 | 0.7500 | 45.7944 | 0.0182 | -0.0112 |
| aligned_poc_acceptance_16m | holdout_2025 | all | 3.0000 | 4 | 0.7500 | 37.0037 | 0.0147 | -0.0118 |

## Plots

- [Managed equity curves and drawdowns](managed_equity_and_drawdowns.png)
- [10/16/20/30-minute horizon comparison](horizon_comparison.png)
- [POC-cross forward returns](poc_cross_forward_returns.png)
- [POC-cross timing impact](poc_cross_timing_impact.png)
- [Chart-scaling event paths](chart_scaling_event_paths.png)

## Predeclared rules

- Signals remain the causal two-minute ORB/value-rejection signals from the first-hour model. The first 30 minutes is observation only.
- Static horizons end the execution phase 10, 16, 20, or 30 minutes after the observation window; open positions are closed at that phase boundary. Sixteen minutes is used because complete two-minute bars cannot represent 15 minutes without truncation or boundary leakage.
- Trend is causal and frozen at the signal: long only when signal price > prior-session SMA10 > SMA30, short for the inverse, otherwise neutral.
- Trend sizing risks 1.00% when aligned, 0.75% when neutral, and 0.50% when countertrend, always subject to the 10x notional cap.
- The reserved-scaling diagnostic starts with 75% of those risk allocations so an aligned trade can retain leverage capacity for an add-on. It was introduced after observing that the unconstrained signal was already at 10x, so it is diagnostic rather than validated.
- The trail activates after a completed close reaches +1R, locks +0.25R, and then follows the best completed close by 1.5 ATR. Stop changes apply only to subsequent bars.
- One add-on is eligible only after the stop is raised, trend is aligned, and an aggressive, delta-aligned completed bar crosses the 0.1-ATR band around one of the prior five completed-session POCs.
- The chart-scaling extension instead requires two closes holding at least +0.5R, a new directional close, an edge close on a range-expansion bar, and current developing POC migration of at least 0.1 ATR from its signal-time value.
- The add-on enters at the next bar open, is capped at 50% of base size and the remaining 10x capacity, and its stop risk plus round-trip cost cannot exceed net base profit already locked by the protected stop.
- Same-bar stop/target ambiguity resolves to the stop. The 2R target and three-loss daily stop remain active.

## Limitations

- This evaluates several variants on the same 2024–2025 sample; 2025 is now an evaluation set, not a fresh untouched holdout.
- POCs allocate each bar's entire volume to typical price. They show estimated acceptance, not separate buyer/seller concentration.
- OHLCV cannot show aggressor side, footprint imbalance, resting liquidity, queue position, or the intrabar path. Scaling around POC therefore remains a proxy experiment.
- The feed has no verified venue or contract identity and is inconsistent with CME NQ's tick grid. The 0.50-bps one-way cost is a scenario, not measured execution.
