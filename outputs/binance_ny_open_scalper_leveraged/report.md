# BTCUSDT 5-Minute Major-Session Scalper

Generated 2026-07-20T18:52:48.805850+00:00. This is a standalone strategy; no macro or hierarchical model inputs are used.

## Decision summary

| scope | trades | win_rate | target_rate | stop_rate | average_gross_return_bps | average_net_return_bps | average_net_r_multiple | gross_profit_factor | profit_factor | break_even_one_way_cost_bps | cumulative_net_return | annualized_net_return | max_drawdown | annualized_one_way_turnover | total_execution_cost | average_holding_bars |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | 1153 | 0.2307 | 0.2064 | 0.4042 | 11.6076 | -115.3595 | -1.1775 | 1.2574 | 0.1282 | 1.3713 | -1.0000 | -0.9616 | -1.0000 | 2359.1475 | 14.6393 | 2.2151 |
| development_2022_2024 | 790 | 0.2228 | 0.1886 | 0.4025 | 7.2402 | -114.9673 | -1.1774 | 1.1591 | 0.1228 | 0.8887 | -0.9999 | -0.9541 | -0.9999 | 2154.7612 | 9.6544 | 2.2734 |
| holdout_2025_plus | 363 | 0.2479 | 0.2452 | 0.4077 | 21.1126 | -116.2130 | -1.1776 | 1.4777 | 0.1394 | 2.3061 | -0.9862 | -0.9763 | -0.9863 | 2903.8932 | 4.9849 | 2.0882 |
| market::New_York | 1153 | 0.2307 | 0.2064 | 0.4042 | 11.6076 | -115.3595 | -1.1775 | 1.2574 | 0.1282 | 1.3713 | -1.0000 | -0.9616 | -1.0000 | 2359.1475 | 14.6393 | 2.2151 |
| phase::opening_first_30m | 495 | 0.2000 | 0.2222 | 0.4626 | 8.0436 | -137.0692 | -1.4099 | 1.1640 | 0.0931 | 0.8314 | -0.9990 | -0.8105 | -0.9990 | 1157.5649 | 7.1831 | 1.9717 |
| phase::opening_followthrough_30m | 658 | 0.2538 | 0.1945 | 0.3602 | 14.2888 | -99.0277 | -1.0026 | 1.3391 | 0.1619 | 1.8914 | -0.9986 | -0.7982 | -0.9986 | 1204.7719 | 7.4562 | 2.3982 |
| setup::opening_range_breakout | 384 | 0.2682 | 0.2344 | 0.3750 | 18.9003 | -95.7876 | -0.9790 | 1.4447 | 0.1871 | 2.4720 | -0.9760 | -0.5961 | -0.9760 | 713.4917 | 4.4040 | 2.2969 |
| setup::value_area_bounce | 769 | 0.2120 | 0.1925 | 0.4187 | 7.9661 | -125.1327 | -1.2766 | 1.1717 | 0.1033 | 0.8978 | -0.9999 | -0.9053 | -0.9999 | 1649.4334 | 10.2353 | 2.1743 |
| market_phase::New_York::opening_first_30m | 495 | 0.2000 | 0.2222 | 0.4626 | 8.0436 | -137.0692 | -1.4099 | 1.1640 | 0.0931 | 0.8314 | -0.9990 | -0.8105 | -0.9990 | 1157.5649 | 7.1831 | 1.9717 |
| market_phase::New_York::opening_followthrough_30m | 658 | 0.2538 | 0.1945 | 0.3602 | 14.2888 | -99.0277 | -1.0026 | 1.3391 | 0.1619 | 1.8914 | -0.9986 | -0.7982 | -0.9986 | 1204.7719 | 7.4562 | 2.3982 |

## Unconditional 30-minute BTC moves

| scope | market | phase | observations | mean_return_bps | median_return_bps | positive_rate | mean_absolute_return_bps | mean_high_low_range_bps | mean_return_tstat | median_volume |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | New_York | opening_first_30m | 1038 | -2.4686 | -1.5472 | 0.4923 | 50.9033 | 105.9689 | -1.0774 | 1631.7055 |
| all | New_York | opening_followthrough_30m | 1038 | 0.1430 | 0.2748 | 0.5010 | 47.8586 | 96.7193 | 0.0679 | 1594.0355 |
| development_2022_2024 | New_York | opening_first_30m | 752 | -1.4991 | -0.8549 | 0.4973 | 49.2458 | 104.4816 | -0.5634 | 2077.8951 |
| development_2022_2024 | New_York | opening_followthrough_30m | 752 | 1.6887 | 1.7070 | 0.5146 | 46.7006 | 95.6762 | 0.6935 | 1962.4950 |
| holdout_2025_plus | New_York | opening_first_30m | 286 | -5.0177 | -4.0580 | 0.4790 | 55.2615 | 109.8796 | -1.1153 | 1056.5995 |
| holdout_2025_plus | New_York | opening_followthrough_30m | 286 | -3.9212 | -3.7675 | 0.4650 | 50.9032 | 99.4620 | -0.9395 | 897.4526 |

## Cost sensitivity

| scope | setup | one_way_cost_bps | trades | win_rate | average_net_return_bps | cumulative_net_return | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- |
| all | all | 0.0000 | 1153 | 0.4536 | 11.6076 | 2.5219 | -0.1542 |
| all | all | 1.0000 | 1153 | 0.4380 | 3.1432 | 0.3277 | -0.4401 |
| all | all | 2.0000 | 1153 | 0.4267 | -5.3213 | -0.5000 | -0.6403 |
| all | all | 2.5000 | 1153 | 0.4206 | -9.5535 | -0.6933 | -0.7335 |
| all | all | 3.0000 | 1153 | 0.4137 | -13.7858 | -0.8119 | -0.8350 |
| all | all | 5.0000 | 1153 | 0.3669 | -30.7147 | -0.9735 | -0.9763 |
| all | all | 10.0000 | 1153 | 0.2940 | -73.0371 | -0.9998 | -0.9998 |
| all | all | 15.0000 | 1153 | 0.2307 | -115.3595 | -1.0000 | -1.0000 |
| all | all | 20.0000 | 1153 | 0.1717 | -157.6819 | -1.0000 | -1.0000 |
| development_2022_2024 | all | 0.0000 | 790 | 0.4354 | 7.2402 | 0.6827 | -0.1542 |
| development_2022_2024 | all | 1.0000 | 790 | 0.4152 | -0.9070 | -0.1159 | -0.4401 |
| development_2022_2024 | all | 2.0000 | 790 | 0.4063 | -9.0542 | -0.5358 | -0.6403 |
| development_2022_2024 | all | 2.5000 | 790 | 0.4000 | -13.1277 | -0.6637 | -0.7118 |
| development_2022_2024 | all | 3.0000 | 790 | 0.3924 | -17.2013 | -0.7564 | -0.7771 |
| development_2022_2024 | all | 5.0000 | 790 | 0.3430 | -33.4957 | -0.9331 | -0.9340 |
| development_2022_2024 | all | 10.0000 | 790 | 0.2797 | -74.2315 | -0.9974 | -0.9974 |
| development_2022_2024 | all | 15.0000 | 790 | 0.2228 | -114.9673 | -0.9999 | -0.9999 |
| development_2022_2024 | all | 20.0000 | 790 | 0.1658 | -155.7031 | -1.0000 | -1.0000 |
| holdout_2025_plus | all | 0.0000 | 363 | 0.4931 | 21.1126 | 1.0930 | -0.1088 |
| holdout_2025_plus | all | 1.0000 | 363 | 0.4876 | 11.9575 | 0.5017 | -0.1345 |
| holdout_2025_plus | all | 2.0000 | 363 | 0.4711 | 2.8025 | 0.0771 | -0.2414 |
| holdout_2025_plus | all | 2.5000 | 363 | 0.4656 | -1.7750 | -0.0880 | -0.3361 |
| holdout_2025_plus | all | 3.0000 | 363 | 0.4601 | -6.3525 | -0.2278 | -0.4190 |
| holdout_2025_plus | all | 5.0000 | 363 | 0.4187 | -24.6626 | -0.6035 | -0.6595 |
| holdout_2025_plus | all | 10.0000 | 363 | 0.3251 | -70.4378 | -0.9256 | -0.9298 |
| holdout_2025_plus | all | 15.0000 | 363 | 0.2479 | -116.2130 | -0.9862 | -0.9863 |
| holdout_2025_plus | all | 20.0000 | 363 | 0.1846 | -161.9881 | -0.9975 | -0.9974 |

## Holdout cost sensitivity by setup

| scope | setup | one_way_cost_bps | trades | win_rate | average_net_return_bps | cumulative_net_return | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- |
| holdout_2025_plus | opening_range_breakout | 0.0000 | 116 | 0.4914 | 26.6700 | 0.3508 | -0.0550 |
| holdout_2025_plus | opening_range_breakout | 1.0000 | 116 | 0.4914 | 19.2264 | 0.2392 | -0.0631 |
| holdout_2025_plus | opening_range_breakout | 2.0000 | 116 | 0.4914 | 11.7829 | 0.1368 | -0.0738 |
| holdout_2025_plus | opening_range_breakout | 2.5000 | 116 | 0.4741 | 8.0611 | 0.0887 | -0.0930 |
| holdout_2025_plus | opening_range_breakout | 3.0000 | 116 | 0.4655 | 4.3394 | 0.0427 | -0.1140 |
| holdout_2025_plus | opening_range_breakout | 5.0000 | 116 | 0.4483 | -10.5477 | -0.1229 | -0.2056 |
| holdout_2025_plus | opening_range_breakout | 10.0000 | 116 | 0.3534 | -47.7654 | -0.4316 | -0.4518 |
| holdout_2025_plus | opening_range_breakout | 15.0000 | 116 | 0.2931 | -84.9831 | -0.6324 | -0.6373 |
| holdout_2025_plus | opening_range_breakout | 20.0000 | 116 | 0.2586 | -122.2008 | -0.7627 | -0.7626 |
| holdout_2025_plus | value_area_bounce | 0.0000 | 247 | 0.4939 | 18.5026 | 0.5494 | -0.1170 |
| holdout_2025_plus | value_area_bounce | 1.0000 | 247 | 0.4858 | 8.5438 | 0.2118 | -0.1680 |
| holdout_2025_plus | value_area_bounce | 2.0000 | 247 | 0.4615 | -1.4150 | -0.0525 | -0.2488 |
| holdout_2025_plus | value_area_bounce | 2.5000 | 247 | 0.4615 | -6.3944 | -0.1623 | -0.3011 |
| holdout_2025_plus | value_area_bounce | 3.0000 | 247 | 0.4575 | -11.3738 | -0.2594 | -0.3671 |
| holdout_2025_plus | value_area_bounce | 5.0000 | 247 | 0.4049 | -31.2914 | -0.5479 | -0.5800 |
| holdout_2025_plus | value_area_bounce | 10.0000 | 247 | 0.3117 | -81.0855 | -0.8691 | -0.8752 |
| holdout_2025_plus | value_area_bounce | 15.0000 | 247 | 0.2267 | -130.8796 | -0.9624 | -0.9632 |
| holdout_2025_plus | value_area_bounce | 20.0000 | 247 | 0.1498 | -180.6737 | -0.9893 | -0.9892 |

## Signal funnel

| stage | observations | share_of_phase_bars |
| --- | --- | --- |
| phase_bars | 12456 | 1.0000 |
| absorption_bar | 0 | 0.0000 |
| recent_absorption | 0 | 0.0000 |
| accumulation | 92 | 0.0074 |
| recent_absorption_and_accumulation | 0 | 0.0000 |
| aggressive_expansion | 4384 | 0.3520 |
| triple_a_signal | 0 | 0.0000 |
| opening_range_breakout_signal | 661 | 0.0531 |
| value_area_bounce_signal | 1054 | 0.0846 |

## Predeclared rules

- Exchange calendars: XTKS, XLON, and XNYS, including holidays, DST, early closes, and Tokyo's November 2024 close extension.
- OHLCV approximation: 50-bar, 24-bin typical-price volume profile; five-bar close-location delta proxy; 2x-volume/0.3-ATR absorption; accumulation then aggressive expansion; session VWAP alignment.
- The first 30 minutes defines the opening range. ORB entries are allowed only in the following 30 minutes. Triple-A and value-area reactions are evaluated in all phase buckets.
- Signals are confirmed at a bar close and entered at the next five-minute open. Both stop and target touching in one bar is resolved as a stop.
- Risk is 1.00% of current equity per trade, subject to a 10.0x gross-notional cap, 2R target, one position globally, and three net losses per UTC day. Repeated non-overlapping attempts are permitted within the selected session until the loss stop is reached.
- Profit-based intraday risk scaling is disabled because the source describes the principle but does not supply an auditable scaling equation.
- Development period: 2022-2024. Untuned holdout: 2025 onward.

## Important limitations

- Aggregated five-minute OHLCV cannot reveal bid/ask aggressor side, resting liquidity, stacked imbalance, or true footprint/CVD. “Delta,” absorption, and volume profile are proxies.
- The cache has no venue/product metadata. It is treated as BTCUSDT trade-price data, while short trades are costed as Binance USD-M perpetual research.
- Historical funding, mark price, queue position, latency, partial fills, and liquidation are unavailable. Funding is set to zero because trades are capped at 30 minutes, but a funding timestamp can still matter.
- The cached history has one 80-minute outage. Any affected full session-prefix or phase is excluded rather than filled.
- Multiple timing buckets and setup families are reported separately; do not select the best row and call it validated without a fresh holdout.
