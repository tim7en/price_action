# One-Minute POC Asymmetric-Payoff Study

Generated 2026-07-22T03:28:29.673087+00:00.

## Decision summary

- The mechanically optimized 2024 winner is rejected: it made 8.00% in development but lost -4.45% in 2025. This is direct evidence of selection overfit.
- The broad, simpler migration runner is the best candidate for paper testing, not live trading: 82 trades, 40.2% wins, +0.313R expectancy, 2.45 net winner/loser ratio, +29.43% compounded return, and -4.52% drawdown at the unverified 0.5 bps one-way assumption.
- A 6R outcome is exceptional rather than normal. With migration and the micro stop, 38.2% of overlapping events reached 2R before -1R, but only 8.1% reached 6R. The framework earns asymmetry through scratches and selective runners, not by forcing every trade to 6R.
- The candidate's break-even one-way cost is about 2.31 bps. At the configured Binance proxy of 15.0 bps one way, the simulated return is -83.38%. Deployment therefore remains blocked.

## Selected candidate comparison

| candidate | scope | trades | sessions | win_rate | average_net_r | median_net_r | average_winner_r | average_loser_r | winner_loser_ratio | net_profit_factor | cumulative_net_return | max_drawdown | average_effective_leverage | median_stop_fraction | average_maximum_favorable_r | average_maximum_adverse_r | target_exit_rate | scratch_exit_rate | stop_exit_rate | partial_rate | break_even_one_way_cost_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| development_selected | all | 57 | 42 | 0.2632 | 0.0710 | -0.5168 | 2.3637 | -0.7478 | 3.1606 | 1.1291 | 0.0320 | -0.1007 | 6.9928 | 0.0017 | 1.2702 | 0.7562 | 0.0526 | 0.3509 | 0.3509 | 0.0000 | 1.0019 |
| development_selected | development_2024 | 22 | 16 | 0.2727 | 0.3904 | -0.2873 | 3.0943 | -0.6235 | 4.9626 | 1.8142 | 0.0800 | -0.0341 | 7.3208 | 0.0015 | 1.4898 | 0.7047 | 0.0909 | 0.4091 | 0.2727 | 0.0000 | 3.0216 |
| development_selected | evaluation_2025 | 35 | 26 | 0.2571 | -0.1298 | -0.7499 | 1.8765 | -0.8243 | 2.2764 | 0.8038 | -0.0445 | -0.1007 | 6.7867 | 0.0019 | 1.1321 | 0.7886 | 0.0286 | 0.3143 | 0.4000 | 0.0000 | -0.3675 |
| stable_5m_base | all | 89 | 41 | 0.5618 | 0.1240 | 0.1348 | 0.6023 | -0.4893 | 1.2309 | 1.5838 | 0.1149 | -0.0309 | 6.9404 | 0.0016 | 0.5887 | 0.4461 | 0.0225 | 0.0000 | 0.0899 | 0.0000 | 1.3985 |
| stable_5m_base | development_2024 | 45 | 18 | 0.5778 | 0.1407 | 0.1524 | 0.5743 | -0.4526 | 1.2688 | 1.7502 | 0.0650 | -0.0151 | 8.2122 | 0.0014 | 0.5898 | 0.4604 | 0.0222 | 0.0000 | 0.0667 | 0.0000 | 1.3659 |
| stable_5m_base | evaluation_2025 | 44 | 23 | 0.5455 | 0.1068 | 0.0796 | 0.6326 | -0.5241 | 1.2070 | 1.4484 | 0.0469 | -0.0309 | 5.6396 | 0.0020 | 0.5876 | 0.4316 | 0.0227 | 0.0000 | 0.1136 | 0.0000 | 1.4471 |
| asymmetric_30m_2r | all | 79 | 41 | 0.5063 | 0.2362 | 0.2159 | 1.4314 | -0.9897 | 1.4463 | 1.5297 | 0.2106 | -0.0468 | 8.7732 | 0.0015 | 1.1813 | 0.7957 | 0.2658 | 0.0000 | 0.4177 | 0.0000 | 1.9260 |
| asymmetric_30m_2r | development_2024 | 38 | 18 | 0.4474 | 0.0954 | -0.2487 | 1.4682 | -1.0160 | 1.4451 | 1.2361 | 0.0452 | -0.0458 | 10.9154 | 0.0011 | 1.1193 | 0.8467 | 0.2632 | 0.0000 | 0.4737 | 0.0000 | 1.0705 |
| asymmetric_30m_2r | evaluation_2025 | 41 | 23 | 0.5610 | 0.3667 | 0.7465 | 1.4043 | -0.9592 | 1.4641 | 1.8708 | 0.1582 | -0.0265 | 6.7878 | 0.0018 | 1.2388 | 0.7484 | 0.2683 | 0.0000 | 0.3659 | 0.0000 | 3.2010 |
| migration_conditional_6r | all | 82 | 41 | 0.4024 | 0.3129 | -0.2672 | 1.9689 | -0.8024 | 2.4537 | 1.7089 | 0.2943 | -0.0452 | 9.0224 | 0.0014 | 1.6272 | 0.6865 | 0.0488 | 0.2805 | 0.4268 | 0.3171 | 2.3106 |
| migration_conditional_6r | development_2024 | 42 | 18 | 0.3810 | 0.2409 | -0.2672 | 1.9980 | -0.8404 | 2.3775 | 1.5576 | 0.1146 | -0.0452 | 10.4742 | 0.0012 | 1.5995 | 0.7323 | 0.0476 | 0.2619 | 0.5000 | 0.3333 | 1.7884 |
| migration_conditional_6r | evaluation_2025 | 40 | 23 | 0.4250 | 0.3884 | -0.2688 | 1.9414 | -0.7595 | 2.5564 | 1.8848 | 0.1612 | -0.0381 | 7.4980 | 0.0017 | 1.6564 | 0.6383 | 0.0500 | 0.3000 | 0.3500 | 0.3000 | 3.0766 |
| micro_conditional_6r | all | 47 | 22 | 0.4043 | 0.3060 | -0.2245 | 1.8455 | -0.7388 | 2.4982 | 1.7883 | 0.1591 | -0.0444 | 8.5045 | 0.0015 | 1.5290 | 0.6830 | 0.0638 | 0.2979 | 0.4255 | 0.2979 | 2.4122 |
| micro_conditional_6r | development_2024 | 21 | 8 | 0.3333 | 0.1628 | -0.2423 | 2.0059 | -0.7587 | 2.6437 | 1.4724 | 0.0428 | -0.0415 | 10.3113 | 0.0012 | 1.4613 | 0.7564 | 0.0952 | 0.2857 | 0.5238 | 0.2857 | 1.5176 |
| micro_conditional_6r | evaluation_2025 | 26 | 14 | 0.4615 | 0.4216 | -0.2153 | 1.7520 | -0.7188 | 2.4375 | 2.0811 | 0.1116 | -0.0381 | 7.0452 | 0.0017 | 1.5837 | 0.6237 | 0.0385 | 0.3077 | 0.3462 | 0.3077 | 3.4696 |

## Can the signals reach 2R--6R before a 1R stop?

This is an overlapping event diagnostic, not an executable portfolio. Same-bar stop/target ambiguity is resolved as a stop.

| context | stop_spec | events | mean_mfe_before_stop_r | median_mfe_before_stop_r | stop_within_60m_rate | reach_2r_before_stop_rate | reach_3r_before_stop_rate | reach_4r_before_stop_rate | reach_6r_before_stop_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| migration_rth | micro_3bar | 123 | 2.2734 | 1.4861 | 0.5935 | 0.3821 | 0.2520 | 0.1463 | 0.0813 |
| migration_rth | hybrid_0.25 | 123 | 2.2249 | 1.4861 | 0.5854 | 0.3902 | 0.2602 | 0.1463 | 0.0732 |
| migration_rth | hybrid_0.50 | 123 | 1.8770 | 1.5048 | 0.5122 | 0.3333 | 0.2114 | 0.1138 | 0.0325 |
| migration_trend_rth | micro_3bar | 76 | 1.8707 | 1.2725 | 0.6316 | 0.3684 | 0.1974 | 0.1053 | 0.0658 |
| migration_trend_rth | hybrid_0.25 | 76 | 1.7943 | 1.2113 | 0.6316 | 0.3684 | 0.1974 | 0.0921 | 0.0526 |
| migration_trend_rth | hybrid_0.50 | 76 | 1.5121 | 1.4883 | 0.5526 | 0.2763 | 0.1447 | 0.0658 | 0.0000 |
| migration_opening_15_30m | micro_3bar | 13 | 2.7201 | 1.7047 | 0.5385 | 0.4615 | 0.3846 | 0.3077 | 0.1538 |
| migration_opening_15_30m | hybrid_0.25 | 13 | 2.4916 | 1.7047 | 0.5385 | 0.4615 | 0.3846 | 0.2308 | 0.0769 |
| migration_opening_15_30m | hybrid_0.50 | 13 | 2.1773 | 1.6793 | 0.4615 | 0.3077 | 0.3077 | 0.2308 | 0.0000 |
| opening_15_30m | micro_3bar | 69 | 1.5461 | 1.0535 | 0.5942 | 0.2609 | 0.1594 | 0.0870 | 0.0435 |
| opening_15_30m | hybrid_0.25 | 69 | 1.4397 | 1.0535 | 0.5942 | 0.2464 | 0.1449 | 0.0580 | 0.0145 |
| opening_15_30m | hybrid_0.50 | 69 | 1.3009 | 1.0547 | 0.4493 | 0.1884 | 0.0870 | 0.0435 | 0.0000 |
| migration_trend_30_40m | micro_3bar | 5 | 0.9979 | 0.8216 | 0.6000 | 0.2000 | 0.0000 | 0.0000 | 0.0000 |
| migration_trend_30_40m | hybrid_0.25 | 5 | 0.9979 | 0.8216 | 0.6000 | 0.2000 | 0.0000 | 0.0000 | 0.0000 |
| migration_trend_30_40m | hybrid_0.50 | 5 | 0.9979 | 0.8216 | 0.6000 | 0.2000 | 0.0000 | 0.0000 | 0.0000 |

## Cross-period stability audit

The ranking below uses both years and is diagnostic only. It is not an untouched selection procedure.

| context | stop_spec | scratch_bars | maximum_holding_minutes | management_spec | trades_development | average_net_r_development | winner_loser_ratio_development | cumulative_net_return_development | trades_evaluation | average_net_r_evaluation | winner_loser_ratio_evaluation | cumulative_net_return_evaluation | diagnostic_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| migration_rth | hybrid_0.50 | 2 | 60 | full_6r | 39 | 0.3491 | 3.2516 | 0.1389 | 38 | 0.5233 | 4.0148 | 0.2119 | 18.2875 |
| migration_rth | hybrid_0.50 | 2 | 60 | full_4r | 39 | 0.2848 | 2.9813 | 0.1121 | 38 | 0.4973 | 3.9005 | 0.2009 | 14.8223 |
| migration_trend_rth | micro_3bar | 2 | 30 | conditional_2r_to_6r | 22 | 0.2240 | 2.6894 | 0.0565 | 28 | 0.3690 | 2.6137 | 0.1049 | 14.4429 |
| migration_rth | micro_3bar | 2 | 60 | full_6r | 41 | 0.3437 | 3.3616 | 0.1530 | 39 | 0.4847 | 3.5040 | 0.1989 | 14.2203 |
| migration_trend_rth | micro_3bar | 2 | 30 | full_4r | 22 | 0.2262 | 3.9339 | 0.0546 | 28 | 0.2711 | 2.8406 | 0.0765 | 13.0287 |
| migration_rth | micro_3bar | 2 | 60 | partial_2r_to_6r | 42 | 0.2542 | 2.4190 | 0.1203 | 40 | 0.3528 | 2.4476 | 0.1455 | 12.9511 |
| migration_rth | micro_3bar | 2 | 60 | conditional_2r_to_6r | 42 | 0.2409 | 2.3775 | 0.1146 | 40 | 0.3884 | 2.5564 | 0.1612 | 12.6852 |
| migration_trend_rth | micro_3bar | 2 | 30 | partial_2r_to_4r | 22 | 0.2051 | 2.6099 | 0.0526 | 28 | 0.2904 | 2.3410 | 0.0819 | 11.8406 |
| migration_rth | micro_3bar | 1 | 60 | conditional_2r_to_6r | 42 | 0.2323 | 3.0180 | 0.1038 | 39 | 0.3154 | 2.4715 | 0.1250 | 11.8178 |
| migration_trend_rth | micro_3bar | 2 | 30 | full_6r | 22 | 0.1926 | 3.7455 | 0.0459 | 28 | 0.3390 | 3.1013 | 0.0962 | 11.7141 |
| migration_trend_rth | hybrid_0.25 | 2 | 30 | full_2r | 22 | 0.1942 | 2.5784 | 0.0487 | 28 | 0.2131 | 2.3316 | 0.0593 | 11.7000 |
| migration_rth | hybrid_0.25 | 2 | 60 | full_3r | 42 | 0.2340 | 2.8271 | 0.1061 | 39 | 0.2511 | 2.6924 | 0.0979 | 11.4279 |
| migration_trend_rth | hybrid_0.25 | 2 | 30 | partial_2r_to_4r | 22 | 0.1799 | 2.5171 | 0.0441 | 28 | 0.2474 | 2.4580 | 0.0691 | 11.4213 |
| migration_trend_rth | micro_3bar | 2 | 30 | partial_2r_to_6r | 22 | 0.1883 | 2.5394 | 0.0483 | 28 | 0.3244 | 2.4588 | 0.0919 | 11.4168 |
| migration_trend_rth | hybrid_0.25 | 2 | 30 | full_4r | 22 | 0.1655 | 3.6077 | 0.0391 | 28 | 0.2816 | 2.9056 | 0.0785 | 11.2742 |
| migration_rth | hybrid_0.50 | 2 | 60 | partial_2r_to_6r | 39 | 0.2317 | 2.7585 | 0.0903 | 39 | 0.3761 | 3.1662 | 0.1530 | 11.1593 |
| migration_trend_rth | hybrid_0.25 | 2 | 30 | full_3r | 22 | 0.1794 | 3.6867 | 0.0434 | 28 | 0.2065 | 2.6109 | 0.0568 | 10.9816 |
| migration_trend_rth | micro_3bar | 2 | 30 | full_2r | 22 | 0.1839 | 2.5213 | 0.0499 | 28 | 0.3098 | 2.4081 | 0.0866 | 10.9251 |
| migration_rth | hybrid_0.25 | 2 | 60 | full_6r | 40 | 0.2487 | 3.3212 | 0.0968 | 39 | 0.4940 | 3.5694 | 0.2020 | 10.3097 |
| migration_rth | hybrid_0.50 | 2 | 60 | conditional_2r_to_6r | 39 | 0.2178 | 2.7003 | 0.0845 | 39 | 0.3844 | 3.2143 | 0.1567 | 10.2699 |
| migration_trend_rth | micro_3bar | 2 | 30 | full_3r | 22 | 0.1806 | 3.6782 | 0.0464 | 28 | 0.3389 | 2.7696 | 0.0975 | 10.1397 |
| migration_rth | hybrid_0.25 | 1 | 60 | conditional_2r_to_6r | 42 | 0.1832 | 2.8340 | 0.0809 | 39 | 0.2806 | 2.5948 | 0.1107 | 10.0663 |
| migration_rth | micro_3bar | 2 | 60 | full_3r | 42 | 0.2249 | 2.7844 | 0.1074 | 39 | 0.3444 | 2.7619 | 0.1394 | 10.0629 |
| migration_rth | hybrid_0.25 | 2 | 60 | full_2r | 42 | 0.1844 | 2.2093 | 0.0853 | 41 | 0.1898 | 2.0097 | 0.0776 | 9.7612 |
| migration_rth | hybrid_0.50 | 0 | 60 | full_6r | 33 | 0.3562 | 1.9488 | 0.1222 | 37 | 0.6308 | 1.9988 | 0.2536 | 9.7307 |
| migration_trend_rth | micro_3bar | 2 | 60 | conditional_2r_to_6r | 21 | 0.1628 | 2.6437 | 0.0428 | 26 | 0.4216 | 2.4375 | 0.1116 | 9.5521 |
| migration_trend_rth | hybrid_0.25 | 2 | 30 | conditional_2r_to_6r | 22 | 0.1534 | 2.4041 | 0.0387 | 28 | 0.3036 | 2.6655 | 0.0857 | 9.5264 |
| migration_rth | micro_3bar | 2 | 60 | full_2r | 42 | 0.1752 | 2.1724 | 0.0874 | 41 | 0.2541 | 2.0399 | 0.1045 | 9.3821 |
| migration_rth | hybrid_0.50 | 2 | 60 | full_3r | 39 | 0.1997 | 2.6240 | 0.0770 | 38 | 0.3708 | 3.3442 | 0.1465 | 9.1473 |
| migration_rth | hybrid_0.50 | 2 | 60 | partial_2r_to_4r | 39 | 0.1995 | 2.6234 | 0.0772 | 39 | 0.3634 | 3.1134 | 0.1476 | 9.1381 |

## Session-block bootstrap

Intervals resample complete sessions, preserving clustering between trades from the same day.

| scope | sessions | mean_session_return_bps | bootstrap_mean_ci_low_bps | bootstrap_mean_ci_high_bps | bootstrap_probability_mean_positive | candidate |
| --- | --- | --- | --- | --- | --- | --- |
| all | 42 | 9.4626 | -47.2913 | 75.8365 | 0.5872 | development_selected |
| development_2024 | 16 | 50.5045 | -46.2706 | 164.9039 | 0.8222 | development_selected |
| holdout_2025 | 26 | -15.7940 | -79.5926 | 64.6547 | 0.3108 | development_selected |
| all | 41 | 27.2319 | -7.6382 | 63.0050 | 0.9380 | stable_5m_base |
| development_2024 | 18 | 35.5680 | -11.7294 | 81.9958 | 0.9260 | stable_5m_base |
| holdout_2025 | 23 | 20.7081 | -28.0788 | 73.6334 | 0.7912 | stable_5m_base |
| all | 41 | 48.5538 | -9.2429 | 108.8630 | 0.9492 | asymmetric_30m_2r |
| development_2024 | 18 | 26.4811 | -65.3385 | 113.9817 | 0.7136 | asymmetric_30m_2r |
| holdout_2025 | 23 | 65.8281 | -6.2087 | 147.5907 | 0.9632 | asymmetric_30m_2r |
| all | 41 | 65.5974 | -0.8798 | 136.4642 | 0.9732 | migration_conditional_6r |
| development_2024 | 18 | 63.2193 | -42.5637 | 171.6659 | 0.8686 | migration_conditional_6r |
| holdout_2025 | 23 | 67.4586 | -16.9728 | 155.4867 | 0.9388 | migration_conditional_6r |
| all | 22 | 69.3973 | -13.6802 | 155.8275 | 0.9456 | micro_conditional_6r |
| development_2024 | 8 | 53.5304 | -43.2371 | 161.0960 | 0.8492 | micro_conditional_6r |
| holdout_2025 | 14 | 78.4642 | -37.0448 | 204.9106 | 0.8978 | micro_conditional_6r |

## Execution-cost sensitivity

| candidate | one_way_cost_bps | trades | win_rate | average_net_r | winner_loser_ratio | cumulative_net_return | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- |
| development_selected | 0.5000 | 57 | 0.2632 | 0.0710 | 3.1606 | 0.0320 | -0.1007 |
| development_selected | 1.0000 | 57 | 0.2632 | -0.0010 | 2.7955 | -0.0083 | -0.1192 |
| development_selected | 2.0000 | 57 | 0.2456 | -0.1448 | 2.4478 | -0.0843 | -0.1550 |
| development_selected | 5.0000 | 57 | 0.2456 | -0.5764 | 1.3739 | -0.2797 | -0.2666 |
| development_selected | 15.0000 | 57 | 0.1053 | -2.0151 | 0.7778 | -0.6796 | -0.6664 |
| stable_5m_base | 0.5000 | 89 | 0.5618 | 0.1240 | 1.2309 | 0.1149 | -0.0309 |
| stable_5m_base | 1.0000 | 88 | 0.5455 | 0.0575 | 1.0278 | 0.0513 | -0.0397 |
| stable_5m_base | 2.0000 | 87 | 0.4598 | -0.0877 | 0.8571 | -0.0724 | -0.0979 |
| stable_5m_base | 5.0000 | 82 | 0.2439 | -0.4891 | 0.6092 | -0.3268 | -0.3284 |
| stable_5m_base | 15.0000 | 79 | 0.0253 | -1.8948 | 0.3280 | -0.7749 | -0.7721 |
| asymmetric_30m_2r | 0.5000 | 79 | 0.5063 | 0.2362 | 1.4463 | 0.2106 | -0.0468 |
| asymmetric_30m_2r | 1.0000 | 79 | 0.5063 | 0.1444 | 1.2356 | 0.1295 | -0.0627 |
| asymmetric_30m_2r | 2.0000 | 79 | 0.4937 | -0.0392 | 0.9633 | -0.0169 | -0.0937 |
| asymmetric_30m_2r | 5.0000 | 78 | 0.4231 | -0.5643 | 0.5609 | -0.3360 | -0.3401 |
| asymmetric_30m_2r | 15.0000 | 75 | 0.1733 | -2.2844 | 0.1271 | -0.8141 | -0.8112 |
| migration_conditional_6r | 0.5000 | 82 | 0.4024 | 0.3129 | 2.4537 | 0.2943 | -0.0452 |
| migration_conditional_6r | 1.0000 | 82 | 0.4024 | 0.2176 | 2.0847 | 0.2022 | -0.0624 |
| migration_conditional_6r | 2.0000 | 82 | 0.4024 | 0.0269 | 1.5457 | 0.0369 | -0.0974 |
| migration_conditional_6r | 5.0000 | 81 | 0.3580 | -0.5436 | 0.8586 | -0.3317 | -0.3457 |
| migration_conditional_6r | 15.0000 | 79 | 0.1646 | -2.3303 | 0.2743 | -0.8338 | -0.8345 |
| micro_conditional_6r | 0.5000 | 47 | 0.4043 | 0.3060 | 2.4982 | 0.1591 | -0.0444 |
| micro_conditional_6r | 1.0000 | 47 | 0.4043 | 0.2129 | 2.1072 | 0.1138 | -0.0624 |
| micro_conditional_6r | 2.0000 | 47 | 0.4043 | 0.0268 | 1.5390 | 0.0284 | -0.0974 |
| micro_conditional_6r | 5.0000 | 46 | 0.3261 | -0.5287 | 0.9654 | -0.1862 | -0.2335 |
| micro_conditional_6r | 15.0000 | 44 | 0.1591 | -2.1708 | 0.3281 | -0.5944 | -0.5993 |

## Causal management contract

- Context uses only completed prior-session 3d/5d composite POCs, three-session POC migration, prior daily closes, and completed 15-minute ranges.
- Signals require a second one-minute acceptance close and enter only at the next one-minute open.
- `micro_3bar` uses the last three completed one-minute bars plus a 0.05 ATR buffer and a 0.25 ATR disaster floor. Hybrid stops add a one-ATR and 0.25x or 0.50x completed-15-minute range floor.
- Failure scratches occur after one or two complete entry bars when price reclaims the POC zone or never achieves +0.25R and closes non-positive.
- Partial variants exit half at +2R. The conditional runner then protects +0.25R on the remainder and exits if price loses the crossed POC, session VWAP, or causal developing-POC alignment.
- Stops are checked before targets inside each bar. Newly protected stops apply only to subsequent bars.
- Position size is `1% / stop percentage`, capped at 20x. Trading halts after three net losses in a session, and every position exits before the regular-session close.

## Material limitations

- One-minute OHLCV cannot observe footprint delta, queue depletion, stacked imbalance, passive absorption, or tape speed. The developing POC is a causal fixed-width typical-price proxy.
- The CSV's instrument and venue identity remain unverified and inconsistent with CME NQ's quarter-point tick. This is not a Binance execution backtest.
- The grid is adaptive and creates multiple-testing risk. A high 6R reach rate or a strong full-sample curve is not validation.
- The configured Binance cost scenario is shown only as turnover stress on this Nasdaq path. A BTCUSDT implementation requires Binance one-minute and trade-side data.

## Plots

- [Target reach before stop](target_reach_before_stop.png)
- [Selected equity and drawdown](selected_equity_and_drawdown.png)
- [Execution-cost sensitivity](runner_cost_sensitivity.png)
- [Expectancy stability](expectancy_stability.png)
