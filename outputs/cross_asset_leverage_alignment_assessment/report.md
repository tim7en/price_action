# BTC and NASDAQ leverage/alignment assessment

## Decision

Fixed 20x and 40x leverage multiplies the existing net trade return after the same per-side cost. It does not add a liquidation engine, maintenance margin, funding, contract sizing, or nonlinear slippage, so these are mathematical stress paths rather than executable account forecasts.

## Fixed-leverage paths

| asset | period | leverage | trades_completed_before_ruin | bankrupt | terminal_equity | cumulative_return | maximum_drawdown | average_stop_risk_fraction | maximum_stop_risk_fraction | round_trip_cost_fraction_per_trade |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| btc | all | 1.0000 | 617 | False | 0.7197 | -0.2803 | -0.3231 | 0.0055 | 0.0392 | 0.0012 |
| btc | all | 20.0000 | 617 | False | 0.0001 | -0.9999 | -0.9999 | 0.1095 | 0.7849 | 0.0240 |
| btc | all | 40.0000 | 617 | False | 0.0000 | -1.0000 | -1.0000 | 0.2190 | 1.5697 | 0.0480 |
| btc | holdout | 1.0000 | 162 | False | 0.9094 | -0.0906 | -0.1011 | 0.0049 | 0.0156 | 0.0012 |
| btc | holdout | 20.0000 | 162 | False | 0.0826 | -0.9174 | -0.9257 | 0.0983 | 0.3128 | 0.0240 |
| btc | holdout | 40.0000 | 162 | False | 0.0014 | -0.9986 | -0.9987 | 0.1966 | 0.6257 | 0.0480 |
| nasdaq | all | 1.0000 | 1769 | False | 0.9261 | -0.0739 | -0.1087 | 0.0016 | 0.0343 | 0.0001 |
| nasdaq | all | 20.0000 | 1769 | False | 0.0869 | -0.9131 | -0.9318 | 0.0312 | 0.6861 | 0.0020 |
| nasdaq | all | 40.0000 | 1769 | False | 0.0011 | -0.9989 | -0.9993 | 0.0624 | 1.3722 | 0.0040 |
| nasdaq | holdout | 1.0000 | 868 | False | 1.0055 | 0.0055 | -0.0573 | 0.0017 | 0.0343 | 0.0001 |
| nasdaq | holdout | 20.0000 | 868 | False | 0.6378 | -0.3622 | -0.7378 | 0.0337 | 0.6861 | 0.0020 |
| nasdaq | holdout | 40.0000 | 868 | False | 0.1206 | -0.8794 | -0.9566 | 0.0674 | 1.3722 | 0.0040 |

`round_trip_cost_fraction_per_trade` is the equity drag paid on every completed round trip before any price P&L: BTC is 2.4% at 20x and 4.8% at 40x; NASDAQ is 0.2% and 0.4%, respectively.

## Development-selected alignment candidates and untouched holdout

| asset | development_rank | candidate | development_trades | development_profit_factor | development_average_net_bps | development_trend_lock_rate | development_fast_whipsaw_rate | holdout_trades | holdout_profit_factor | holdout_average_net_bps | holdout_trend_lock_rate | holdout_fast_whipsaw_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| btc | 1 | high_effort | 228 | 0.8765 | -2.4203 | 0.7061 | 0.0395 | 102 | 0.7255 | -4.9347 | 0.7059 | 0.0588 |
| btc | 2 | strong_impulse | 228 | 0.8212 | -3.1765 | 0.7193 | 0.0307 | 87 | 0.8628 | -2.1320 | 0.7241 | 0.0460 |
| btc | 3 | delta_plus_strong_impulse | 213 | 0.8056 | -3.5729 | 0.7136 | 0.0329 | 82 | 0.8348 | -2.6575 | 0.7195 | 0.0488 |
| nasdaq | 1 | orb_vwap_breakout_early | 200 | 0.9837 | -0.1283 | 0.6300 | 0.0250 | 186 | 0.9992 | -0.0069 | 0.6183 | 0.0538 |
| nasdaq | 2 | orb_vwap_strong_breakout | 408 | 0.9393 | -0.3981 | 0.6127 | 0.0466 | 384 | 0.9779 | -0.1730 | 0.5990 | 0.0703 |
| nasdaq | 3 | strong_breakout | 416 | 0.9211 | -0.5223 | 0.6106 | 0.0457 | 389 | 0.9806 | -0.1509 | 0.5990 | 0.0720 |

Candidates are overlapping attribution cohorts, not independently replayed strategies. Ranking uses development PF subject to minimum samples (BTC 60, NASDAQ 150); the holdout columns are never used for selection.

## Trend locks versus damaging failures

| asset | period | outcome_bucket | trades | trade_share | average_net_bps | net_contribution_bps | average_holding_bars |
| --- | --- | --- | --- | --- | --- | --- | --- |
| btc | all | trend_lock | 415 | 0.6726 | 20.3050 | 8426.5882 | 6.4506 |
| btc | all | fast_whipsaw | 33 | 0.0535 | -55.9230 | -1845.4595 | 2.2424 |
| btc | all | slow_stop_failure | 169 | 0.2739 | -58.0324 | -9807.4828 | 14.0473 |
| btc | holdout | trend_lock | 111 | 0.6852 | 18.0367 | 2002.0746 | 6.9459 |
| btc | holdout | fast_whipsaw | 7 | 0.0432 | -52.5977 | -368.1839 | 2.2857 |
| btc | holdout | slow_stop_failure | 44 | 0.2716 | -58.3871 | -2569.0326 | 11.4091 |
| nasdaq | all | trend_lock | 1012 | 0.5721 | 10.9546 | 11086.0182 | 9.3834 |
| nasdaq | all | fast_whipsaw | 158 | 0.0893 | -13.9310 | -2201.0929 | 2.2722 |
| nasdaq | all | slow_stop_failure | 599 | 0.3386 | -16.0756 | -9629.2685 | 13.4758 |
| nasdaq | holdout | trend_lock | 505 | 0.5818 | 11.9976 | 6058.7920 | 9.5921 |
| nasdaq | holdout | fast_whipsaw | 80 | 0.0922 | -14.3451 | -1147.6101 | 2.2125 |
| nasdaq | holdout | slow_stop_failure | 283 | 0.3260 | -17.1067 | -4841.2017 | 12.4346 |

- `trend_lock`: target/trailing exit with positive return after costs.
- `fast_whipsaw`: static-stop exit within three bars.
- `slow_stop_failure`: static-stop exit after more than three bars.

## Development-period damage signatures checked in holdout

| asset | development_damage_rank | attribute_group | development_trades | development_average_net_bps | development_fast_whipsaw_rate | holdout_trades | holdout_average_net_bps | holdout_fast_whipsaw_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| btc | 1 | orb_width=wide | 228 | -11.0964 | 0.0921 | 69 | -6.4414 | 0.0580 |
| btc | 2 | ivb_room=high | 228 | -11.0066 | 0.0833 | 80 | -3.8858 | 0.0500 |
| btc | 3 | effort=low | 227 | -7.6625 | 0.0749 | 60 | -7.1966 | 0.0167 |
| btc | 4 | side=long | 256 | -7.5476 | 0.0781 | 84 | -5.6803 | 0.0357 |
| nasdaq | 1 | breakout=weak | 428 | -1.2604 | 0.1005 | 436 | 0.3964 | 0.0917 |
| nasdaq | 2 | orb_width=compact | 428 | -1.2012 | 0.0701 | 348 | 0.6191 | 0.0833 |
| nasdaq | 3 | session=after_120m | 438 | -1.1783 | 0.0822 | 431 | 0.0795 | 0.0951 |
| nasdaq | 4 | side=short | 395 | -1.0983 | 0.0709 | 372 | 0.8140 | 0.0887 |

## Frozen distribution thresholds

| asset | feature | development_median |
| --- | --- | --- |
| btc | impulse_median | 1.3822 |
| btc | ivb_room_median | 2.7095 |
| btc | effort_median | 2.2883 |
| btc | orb_width_atr_median | 2.1060 |
| nasdaq | breakout_strength_median | 0.3329 |
| nasdaq | vwap_distance_median | 3.5766 |
| nasdaq | orb_width_atr_median | 7.9834 |

## Limits

- BTC uses the cost-aware full non-delta proxy at 6 bps per side; NASDAQ uses the original ATR trail at 0.5 bps per side.
- Leverage paths use fixed notional exposure with no dynamic risk reduction. They are intentionally harsh stress tests.
- Alignment cohorts condition executed trades after the fact. Because removing a trade could free later overlapping signals, they are diagnostic and must be broker-replayed before becoming strategy rules.
- BTC lacks verified spot/perpetual identity and funding. NASDAQ identity is unverified and its price grid is inconsistent with CME NQ.
- Five-minute BTC and one-minute NASDAQ bars cannot reveal true order-book sequence or intrabar whipsaw paths.
