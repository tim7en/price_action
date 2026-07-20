# BTCUSDT 5-Minute Major-Session Scalper

Generated 2026-07-20T18:43:39.834845+00:00. This is a standalone strategy; no macro or hierarchical model inputs are used.

## Decision summary

| scope | trades | win_rate | target_rate | stop_rate | average_gross_return_bps | average_net_return_bps | average_net_r_multiple | gross_profit_factor | profit_factor | break_even_one_way_cost_bps | cumulative_net_return | annualized_net_return | max_drawdown | annualized_one_way_turnover | total_execution_cost | average_holding_bars |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | 2561 | 0.1468 | 0.1636 | 0.3940 | 1.1679 | -25.6326 | -1.7783 | 1.1426 | 0.0818 | 0.6537 | -0.9986 | -0.7959 | -0.9986 | 1105.3478 | 6.8636 | 2.4159 |
| development_2022_2024 | 1842 | 0.1428 | 0.1558 | 0.3860 | 0.8131 | -25.7106 | -1.7526 | 1.0975 | 0.0803 | 0.4599 | -0.9913 | -0.7959 | -0.9913 | 1090.4308 | 4.8857 | 2.4615 |
| holdout_2025_plus | 719 | 0.1572 | 0.1836 | 0.4145 | 2.0767 | -25.4327 | -1.8442 | 1.2662 | 0.0856 | 1.1324 | -0.8400 | -0.7984 | -0.8396 | 1152.2152 | 1.9779 | 2.2990 |
| market::London | 739 | 0.0893 | 0.1313 | 0.3667 | 0.1297 | -27.4272 | -2.0942 | 1.0180 | 0.0391 | 0.0706 | -0.8688 | -0.3891 | -0.8684 | 329.4863 | 2.0365 | 2.5453 |
| market::New_York | 990 | 0.2263 | 0.2071 | 0.4091 | 2.2611 | -22.7370 | -1.1772 | 1.2289 | 0.1495 | 1.3567 | -0.8953 | -0.4205 | -0.8958 | 398.8199 | 2.4748 | 2.3313 |
| market::Tokyo | 832 | 0.1034 | 0.1406 | 0.4002 | 0.7892 | -27.4840 | -2.2129 | 1.1119 | 0.0446 | 0.4187 | -0.8989 | -0.4253 | -0.8984 | 379.0815 | 2.3523 | 2.4014 |
| phase::after_close_30m | 251 | 0.0956 | 0.0956 | 0.3267 | 0.4038 | -26.4679 | -1.9795 | 1.0592 | 0.0403 | 0.2254 | -0.4861 | -0.1506 | -0.4855 | 110.2254 | 0.6745 | 2.6773 |
| phase::closing_last_30m | 268 | 0.1119 | 0.0896 | 0.3246 | -0.7590 | -27.1135 | -1.8505 | 0.9043 | 0.0466 | -0.4320 | -0.5172 | -0.1624 | -0.5174 | 114.5796 | 0.7063 | 2.6045 |
| phase::opening_first_30m | 833 | 0.1441 | 0.1813 | 0.4454 | 1.0538 | -26.1634 | -1.8078 | 1.1223 | 0.0839 | 0.5808 | -0.8875 | -0.4102 | -0.8875 | 365.3620 | 2.2672 | 2.2713 |
| phase::opening_followthrough_30m | 1209 | 0.1671 | 0.1820 | 0.3879 | 1.8323 | -24.7651 | -1.7002 | 1.2226 | 0.0970 | 1.0333 | -0.9503 | -0.5157 | -0.9501 | 517.8599 | 3.2156 | 2.4194 |
| setup::opening_range_breakout | 781 | 0.1613 | 0.1921 | 0.4328 | 1.2310 | -25.7444 | -1.8463 | 1.1430 | 0.0941 | 0.6845 | -0.8667 | -0.3856 | -0.8667 | 339.5105 | 2.1068 | 2.2855 |
| setup::value_area_bounce | 1780 | 0.1404 | 0.1511 | 0.3770 | 1.1402 | -25.5835 | -1.7485 | 1.1425 | 0.0762 | 0.6400 | -0.9896 | -0.6682 | -0.9896 | 766.5688 | 4.7568 | 2.4730 |
| market_phase::London::after_close_30m | 65 | 0.1538 | 0.0308 | 0.3077 | -3.2066 | -26.2225 | -1.2723 | 0.6770 | 0.0627 | -2.0898 | -0.1570 | -0.0412 | -0.1539 | 24.5972 | 0.1496 | 2.9538 |
| market_phase::London::closing_last_30m | 93 | 0.2151 | 0.1290 | 0.3226 | -0.8256 | -24.1262 | -1.0404 | 0.9209 | 0.0952 | -0.5315 | -0.2014 | -0.0538 | -0.2018 | 35.5562 | 0.2167 | 2.8602 |
| market_phase::London::opening_first_30m | 205 | 0.0390 | 0.1171 | 0.3805 | 0.2457 | -28.4051 | -2.3942 | 1.0392 | 0.0266 | 0.1286 | -0.4420 | -0.1325 | -0.4402 | 95.4084 | 0.5873 | 2.4000 |
| market_phase::London::opening_followthrough_30m | 376 | 0.0745 | 0.1569 | 0.3803 | 0.8796 | -27.9187 | -2.3334 | 1.1368 | 0.0291 | 0.4581 | -0.6507 | -0.2253 | -0.6505 | 175.1933 | 1.0828 | 2.4761 |
| market_phase::New_York::after_close_30m | 56 | 0.0893 | 0.0893 | 0.2679 | 2.5317 | -23.7802 | -1.1316 | 1.3561 | 0.0518 | 1.4433 | -0.1249 | -0.0336 | -0.1251 | 25.1428 | 0.1473 | 3.0000 |
| market_phase::New_York::closing_last_30m | 66 | 0.1061 | 0.1212 | 0.2879 | -1.1546 | -27.9686 | -1.4302 | 0.8682 | 0.0546 | -0.6459 | -0.1689 | -0.0484 | -0.1666 | 31.6162 | 0.1770 | 2.3788 |
| market_phase::New_York::opening_first_30m | 405 | 0.2148 | 0.2321 | 0.4889 | 1.2911 | -24.7766 | -1.3954 | 1.1238 | 0.1273 | 0.7429 | -0.6344 | -0.2161 | -0.6369 | 170.3601 | 1.0557 | 2.0469 |
| market_phase::New_York::opening_followthrough_30m | 463 | 0.2700 | 0.2117 | 0.3737 | 3.5637 | -20.0810 | -0.9557 | 1.3602 | 0.1992 | 2.2608 | -0.6064 | -0.2023 | -0.6061 | 176.8890 | 1.0948 | 2.4924 |
| market_phase::Tokyo::after_close_30m | 130 | 0.0692 | 0.1308 | 0.3615 | 1.2924 | -27.7484 | -2.6983 | 1.2507 | 0.0249 | 0.6675 | -0.3033 | -0.0850 | -0.3010 | 61.8630 | 0.3775 | 2.4000 |
| market_phase::Tokyo::closing_last_30m | 109 | 0.0275 | 0.0367 | 0.3486 | -0.4628 | -29.1445 | -2.7962 | 0.9124 | 0.0039 | -0.2420 | -0.2726 | -0.0751 | -0.2707 | 51.1597 | 0.3126 | 2.5229 |
| market_phase::Tokyo::opening_first_30m | 223 | 0.1121 | 0.1480 | 0.4260 | 1.3658 | -26.6213 | -2.0179 | 1.1827 | 0.0591 | 0.7320 | -0.4484 | -0.1351 | -0.4480 | 101.5173 | 0.6241 | 2.5605 |
| market_phase::Tokyo::opening_followthrough_30m | 370 | 0.1324 | 0.1703 | 0.4135 | 0.6338 | -27.4218 | -1.9882 | 1.0794 | 0.0549 | 0.3388 | -0.6382 | -0.2179 | -0.6365 | 167.2843 | 1.0381 | 2.2703 |

## Unconditional 30-minute BTC moves

| scope | market | phase | observations | mean_return_bps | median_return_bps | positive_rate | mean_absolute_return_bps | mean_high_low_range_bps | mean_return_tstat | median_volume |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | London | after_close_30m | 1045 | 0.2346 | -0.1945 | 0.4976 | 32.9021 | 70.7336 | 0.1631 | 1074.0874 |
| all | London | closing_last_30m | 1045 | -0.9684 | -1.8942 | 0.4871 | 37.7020 | 79.7632 | -0.5966 | 1279.4183 |
| all | London | opening_first_30m | 1045 | 1.8097 | 2.5789 | 0.5330 | 24.5668 | 50.0143 | 1.5647 | 624.0577 |
| all | London | opening_followthrough_30m | 1045 | -0.8657 | -0.7185 | 0.4919 | 21.9077 | 45.5185 | -0.8742 | 671.0169 |
| all | New_York | after_close_30m | 1038 | 2.4264 | 1.6150 | 0.5202 | 29.1484 | 62.2116 | 1.8111 | 718.3484 |
| all | New_York | closing_last_30m | 1038 | -0.8334 | -0.2447 | 0.4933 | 32.1453 | 65.2137 | -0.5301 | 888.6489 |
| all | New_York | opening_first_30m | 1038 | -2.4686 | -1.5472 | 0.4923 | 50.9033 | 105.9689 | -1.0774 | 1631.7055 |
| all | New_York | opening_followthrough_30m | 1038 | 0.1430 | 0.2748 | 0.5010 | 47.8586 | 96.7193 | 0.0679 | 1594.0355 |
| all | Tokyo | after_close_30m | 1013 | 0.2307 | 0.9285 | 0.5123 | 22.7860 | 44.9462 | 0.1846 | 530.7849 |
| all | Tokyo | closing_last_30m | 1013 | 0.0201 | 0.8781 | 0.5202 | 20.2176 | 41.3482 | 0.0214 | 481.4322 |
| all | Tokyo | opening_first_30m | 1013 | -0.3636 | -1.0355 | 0.4926 | 28.2546 | 60.1439 | -0.2617 | 669.9921 |
| all | Tokyo | opening_followthrough_30m | 1013 | -1.1158 | -2.0012 | 0.4709 | 28.8169 | 58.1198 | -0.8029 | 628.4797 |
| development_2022_2024 | London | after_close_30m | 754 | 0.8559 | 0.6004 | 0.5119 | 32.9597 | 72.6860 | 0.5054 | 1446.8430 |
| development_2022_2024 | London | closing_last_30m | 754 | -0.7726 | -2.1501 | 0.4801 | 37.8004 | 81.9529 | -0.3937 | 1672.9062 |
| development_2022_2024 | London | opening_first_30m | 754 | 1.5740 | 1.6051 | 0.5252 | 25.7978 | 53.0233 | 1.0747 | 820.0401 |
| development_2022_2024 | London | opening_followthrough_30m | 754 | -0.2478 | 0.1116 | 0.5013 | 22.8688 | 48.1138 | -0.1992 | 864.1606 |
| development_2022_2024 | New_York | after_close_30m | 752 | 1.3569 | 0.4207 | 0.5053 | 30.4642 | 65.8915 | 0.8197 | 1007.9967 |
| development_2022_2024 | New_York | closing_last_30m | 752 | -0.2461 | 0.8758 | 0.5120 | 33.4425 | 68.1939 | -0.1256 | 1151.3065 |
| development_2022_2024 | New_York | opening_first_30m | 752 | -1.4991 | -0.8549 | 0.4973 | 49.2458 | 104.4816 | -0.5634 | 2077.8951 |
| development_2022_2024 | New_York | opening_followthrough_30m | 752 | 1.6887 | 1.7070 | 0.5146 | 46.7006 | 95.6762 | 0.6935 | 1962.4950 |
| development_2022_2024 | Tokyo | after_close_30m | 735 | -0.2231 | -0.2146 | 0.4980 | 23.1185 | 47.0492 | -0.1530 | 675.7740 |
| development_2022_2024 | Tokyo | closing_last_30m | 735 | 0.8852 | 1.0315 | 0.5252 | 20.4968 | 42.5880 | 0.7719 | 610.9635 |
| development_2022_2024 | Tokyo | opening_first_30m | 735 | 1.2562 | -0.3058 | 0.4952 | 29.1950 | 62.2987 | 0.7619 | 931.5256 |
| development_2022_2024 | Tokyo | opening_followthrough_30m | 735 | -1.2344 | -3.2365 | 0.4531 | 29.7993 | 60.5286 | -0.7326 | 802.3915 |
| holdout_2025_plus | London | after_close_30m | 291 | -1.3752 | -2.8406 | 0.4605 | 32.7528 | 65.6748 | -0.5043 | 543.4106 |
| holdout_2025_plus | London | closing_last_30m | 291 | -1.4759 | 1.8237 | 0.5052 | 37.4470 | 74.0894 | -0.5167 | 724.1696 |
| holdout_2025_plus | London | opening_first_30m | 291 | 2.4204 | 4.2096 | 0.5533 | 21.3770 | 42.2179 | 1.4314 | 331.3350 |
| holdout_2025_plus | London | opening_followthrough_30m | 291 | -2.4669 | -2.5718 | 0.4674 | 19.4172 | 38.7939 | -1.6415 | 355.5491 |
| holdout_2025_plus | New_York | after_close_30m | 286 | 5.2385 | 5.9477 | 0.5594 | 25.6886 | 52.5358 | 2.4221 | 349.1352 |
| holdout_2025_plus | New_York | closing_last_30m | 286 | -2.3776 | -3.2749 | 0.4441 | 28.7344 | 57.3776 | -0.9694 | 430.1348 |

## Cost sensitivity

| scope | one_way_cost_bps | trades | win_rate | average_net_return_bps | cumulative_net_return | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| all | 0.0000 | 2561 | 0.4420 | 1.1679 | 0.3406 | -0.0920 |
| all | 2.5000 | 2561 | 0.3776 | -3.2988 | -0.5730 | -0.5827 |
| all | 5.0000 | 2561 | 0.3147 | -7.7656 | -0.8641 | -0.8649 |
| all | 10.0000 | 2561 | 0.2191 | -16.6991 | -0.9862 | -0.9863 |
| all | 15.0000 | 2561 | 0.1468 | -25.6326 | -0.9986 | -0.9986 |
| all | 20.0000 | 2561 | 0.0972 | -34.5660 | -0.9999 | -0.9999 |
| development_2022_2024 | 0.0000 | 1842 | 0.4349 | 0.8131 | 0.1566 | -0.0920 |
| development_2022_2024 | 2.5000 | 1842 | 0.3713 | -3.6075 | -0.4877 | -0.4892 |
| development_2022_2024 | 5.0000 | 1842 | 0.3067 | -8.0281 | -0.7732 | -0.7728 |
| development_2022_2024 | 10.0000 | 1842 | 0.2177 | -16.8693 | -0.9556 | -0.9555 |
| development_2022_2024 | 15.0000 | 1842 | 0.1428 | -25.7106 | -0.9913 | -0.9913 |
| development_2022_2024 | 20.0000 | 1842 | 0.0972 | -34.5518 | -0.9983 | -0.9983 |
| holdout_2025_plus | 0.0000 | 719 | 0.4604 | 2.0767 | 0.1591 | -0.0359 |
| holdout_2025_plus | 2.5000 | 719 | 0.3936 | -2.5082 | -0.1664 | -0.1864 |
| holdout_2025_plus | 5.0000 | 719 | 0.3352 | -7.0931 | -0.4006 | -0.4049 |
| holdout_2025_plus | 10.0000 | 719 | 0.2225 | -16.2629 | -0.6903 | -0.6909 |
| holdout_2025_plus | 15.0000 | 719 | 0.1572 | -25.4327 | -0.8400 | -0.8396 |
| holdout_2025_plus | 20.0000 | 719 | 0.0974 | -34.6025 | -0.9174 | -0.9171 |

## Signal funnel

| stage | observations | share_of_phase_bars |
| --- | --- | --- |
| phase_bars | 74304 | 1.0000 |
| absorption_bar | 1 | 0.0000 |
| recent_absorption | 22 | 0.0003 |
| accumulation | 1057 | 0.0142 |
| recent_absorption_and_accumulation | 1 | 0.0000 |
| aggressive_expansion | 12679 | 0.1706 |
| triple_a_signal | 0 | 0.0000 |
| opening_range_breakout_signal | 1543 | 0.0208 |
| value_area_bounce_signal | 2871 | 0.0386 |

## Predeclared rules

- Exchange calendars: XTKS, XLON, and XNYS, including holidays, DST, early closes, and Tokyo's November 2024 close extension.
- OHLCV approximation: 50-bar, 24-bin typical-price volume profile; five-bar close-location delta proxy; 2x-volume/0.3-ATR absorption; accumulation then aggressive expansion; session VWAP alignment.
- The first 30 minutes defines the opening range. ORB entries are allowed only in the following 30 minutes. Triple-A and value-area reactions are evaluated in all phase buckets.
- Signals are confirmed at a bar close and entered at the next five-minute open. Both stop and target touching in one bar is resolved as a stop.
- Risk is 0.25% of equity per trade subject to a 1x notional cap, 2R target, one trade per market-phase, one position globally, and three net losses per UTC day.
- Development period: 2022-2024. Untuned holdout: 2025 onward.

## Important limitations

- Aggregated five-minute OHLCV cannot reveal bid/ask aggressor side, resting liquidity, stacked imbalance, or true footprint/CVD. “Delta,” absorption, and volume profile are proxies.
- The cache has no venue/product metadata. It is treated as BTCUSDT trade-price data, while short trades are costed as Binance USD-M perpetual research.
- Historical funding, mark price, queue position, latency, partial fills, and liquidation are unavailable. Funding is set to zero because trades are capped at 30 minutes, but a funding timestamp can still matter.
- The cached history has one 80-minute outage. Any affected full session-prefix or phase is excluded rather than filled.
- Multiple timing buckets and setup families are reported separately; do not select the best row and call it validated without a fresh holdout.
