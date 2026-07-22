# Nasdaq-100 One-, Two-, and Five-Minute Comparison

Generated 2026-07-22T01:04:58.005982+00:00. All frequencies use the same data, fixed rules, 1% stop risk, 2R target and 0.50 bps one-way execution scenario.

> These are multiple views of one unverified Nasdaq-100 cash/CFD-like feed, not independent trials. Comparing frequencies and then selecting the best holdout result would be data mining.

## Total return on equity

| bar_minutes | scope | trades | sessions | win_rate | target_rate | stop_rate | average_gross_r | average_net_r | average_gross_return_bps | average_net_return_bps | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_gross_return | cumulative_net_return | annualized_net_return | max_drawdown | average_notional_fraction | median_risk_fraction_deployed | average_holding_bars | average_holding_minutes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | all | 78 | 72 | 0.3462 | 0.3462 | 0.6538 | 0.0385 | -0.0723 | 3.8462 | -5.2372 | 1.0677 | 0.9165 | 0.2117 | 0.0241 | -0.0460 | -0.0250 | -0.1330 | 9.0834 | 0.0094 | 5.2436 | 5.2436 |
| 1 | development_2024 | 48 | 45 | 0.2917 | 0.2917 | 0.7083 | -0.1250 | -0.2358 | -11.9527 | -21.1513 | 0.8079 | 0.6924 | -0.6497 | -0.0590 | -0.0998 | -0.1030 | -0.1330 | 9.1986 | 0.0093 | 5.3750 | 5.3750 |
| 1 | holdout_2025 | 30 | 27 | 0.4333 | 0.4333 | 0.5667 | 0.3000 | 0.1894 | 29.1245 | 20.2255 | 1.6048 | 1.3807 | 1.6364 | 0.0883 | 0.0597 | 0.0696 | -0.0373 | 8.8991 | 0.0098 | 5.0333 | 5.0333 |
| 2 | all | 142 | 128 | 0.4437 | 0.2817 | 0.5000 | 0.1487 | 0.0672 | 15.2068 | 7.4780 | 1.3023 | 1.1367 | 0.9838 | 0.2268 | 0.0993 | 0.0508 | -0.1525 | 7.7288 | 0.0100 | 5.5070 | 11.0141 |
| 2 | development_2024 | 73 | 65 | 0.4521 | 0.2877 | 0.4658 | 0.1822 | 0.1006 | 18.0158 | 10.0895 | 1.3611 | 1.1860 | 1.1365 | 0.1336 | 0.0699 | 0.0716 | -0.0839 | 7.9263 | 0.0100 | 5.1644 | 10.3288 |
| 2 | holdout_2025 | 69 | 63 | 0.4348 | 0.2754 | 0.5362 | 0.1133 | 0.0319 | 12.2349 | 4.7151 | 1.2411 | 1.0854 | 0.8135 | 0.0822 | 0.0275 | 0.0305 | -0.1525 | 7.5198 | 0.0100 | 5.8696 | 11.7391 |
| 5 | all | 131 | 126 | 0.4733 | 0.1374 | 0.3740 | 0.1051 | 0.0394 | 10.6978 | 4.1875 | 1.2622 | 1.0948 | 0.8216 | 0.1419 | 0.0486 | 0.0251 | -0.0718 | 6.5103 | 0.0100 | 2.9160 | 14.5802 |
| 5 | development_2024 | 67 | 64 | 0.4776 | 0.1791 | 0.3731 | 0.1701 | 0.1022 | 17.3785 | 10.6543 | 1.4386 | 1.2468 | 1.2922 | 0.1187 | 0.0695 | 0.0705 | -0.0718 | 6.7243 | 0.0100 | 2.7015 | 13.5075 |
| 5 | holdout_2025 | 64 | 62 | 0.4688 | 0.0938 | 0.3750 | 0.0370 | -0.0264 | 3.7040 | -2.5824 | 1.0881 | 0.9429 | 0.2946 | 0.0207 | -0.0195 | -0.0214 | -0.0697 | 6.2863 | 0.0100 | 3.1406 | 15.7031 |

## Strict absorption proxy

_No rows._

No strict setup row means the rule generated no executable signal. The component audit below distinguishes the 2x-volume test, the 0.3-ATR range test, and their required intersection.

| bar_minutes | scope | bars | indicator_eligible_bars | volume_above_2x_average | range_below_0_3_atr | strict_absorption_intersection | absorption_given_volume_share | absorption_given_narrow_range_share | recent_absorption | three_bar_accumulation | recent_absorption_and_accumulation | aggressive_expansion | strict_signals |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | all_feed_bars | 681646 | 681596 | 32299 | 2242 | 3 | 0.0001 | 0.0013 | 18 | 8456 | 7 | 72816 | 0 |
| 1 | complete_regular_session_bars | 185130 | 185130 | 11309 | 30 | 0 | 0.0000 | 0.0000 | 0 | 838 | 0 | 17288 | 0 |
| 1 | first_30m_bars | 14310 | 14310 | 7577 | 1 | 0 | 0.0000 | 0.0000 | 0 | 39 | 0 | 5708 | 0 |
| 1 | execution_30m_bars | 14220 | 14220 | 168 | 1 | 0 | 0.0000 | 0.0000 | 0 | 63 | 0 | 1030 | 0 |
| 2 | all_feed_bars | 340741 | 340691 | 22042 | 1256 | 0 | 0.0000 | 0.0000 | 0 | 5327 | 0 | 40411 | 0 |
| 2 | complete_regular_session_bars | 92565 | 92565 | 9506 | 7 | 0 | 0.0000 | 0.0000 | 0 | 446 | 0 | 10369 | 0 |
| 2 | first_30m_bars | 7155 | 7155 | 6138 | 0 | 0 | 0.0000 | 0.0000 | 0 | 6 | 0 | 3463 | 0 |
| 2 | execution_30m_bars | 7110 | 7110 | 1280 | 1 | 0 | 0.0000 | 0.0000 | 0 | 37 | 0 | 2064 | 0 |
| 5 | all_feed_bars | 136298 | 136248 | 14330 | 1116 | 0 | 0.0000 | 0.0000 | 0 | 3383 | 0 | 17673 | 0 |
| 5 | complete_regular_session_bars | 37026 | 37026 | 7417 | 8 | 0 | 0.0000 | 0.0000 | 0 | 284 | 0 | 5821 | 0 |
| 5 | first_30m_bars | 2862 | 2862 | 2852 | 0 | 0 | 0.0000 | 0.0000 | 0 | 25 | 0 | 1630 | 0 |
| 5 | execution_30m_bars | 2844 | 2844 | 2614 | 0 | 0 | 0.0000 | 0.0000 | 0 | 0 | 0 | 1318 | 0 |

## Session high/low timing

| metric | value |
| --- | --- |
| sessions | 477.0000 |
| median_high_minute_from_open | 144.0000 |
| median_low_minute_from_open | 86.0000 |
| high_low_timing_correlation | -0.5391 |
| median_absolute_high_low_gap_minutes | 239.0000 |
| high_low_within_30m_share | 0.0126 |
| high_low_within_60m_share | 0.0482 |
| high_in_first_30m_share | 0.2767 |
| low_in_first_30m_share | 0.3333 |
| high_in_last_30m_share | 0.1845 |
| low_in_last_30m_share | 0.1174 |
| high_before_low_share | 0.4528 |

## Plots

- [Gross and net equity curves](equity_curves.png)
- [Net-equity drawdowns](drawdowns.png)
- [Trade return distributions](trade_return_distributions.png)
- [Monthly net returns](monthly_returns.png)
- [Session high/low timing](session_high_low_timing.png)

## Interpretation guardrails

- Gross return is before the configured spread/commission/slippage scenario; net return is after costs on both entry and exit notional.
- Total return on equity compounds every executed trade at its risk-sized notional. It is not the return of an unleveraged index position.
- The strict absorption rule is unchanged across frequencies: volume above 2x its prior 50-bar mean, range below 0.3 ATR, recent absorption, three-bar accumulation at a key level, and aggressive directional expansion.
- The high/low analysis uses complete native one-minute XNYS regular sessions and records the first minute containing each session extreme.
- Confidence remains limited by two years of unidentified OHLCV and by evaluating three frequencies on the same 2025 holdout.
