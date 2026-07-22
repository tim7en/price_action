# BTC five-minute Fabio/DeepCharts-inspired proxy study

## Decision

This is an OHLCV proxy test, not a recreation of Deep Print, DeepTrades, true bid/ask delta, order-book absorption, IVB, Deep Effort, or V-Tracker. Every approximation is explicitly suffixed `proxy`. The holdout is 2025 through 25 February 2026; thresholds were fixed before that split was inspected.

## Zero-cost one-times-notional results

| filter_variant | trades | profit_factor | cumulative_net_return | maximum_drawdown |
| --- | --- | --- | --- | --- |
| orb_only_proxy | 5126 | 1.1440 | 2.2649 | -0.2555 |
| vwap_profile_uniform_proxy | 2767 | 1.1686 | 1.1341 | -0.1670 |
| vwap_profile_close_proxy | 2728 | 1.1857 | 1.2807 | -0.1504 |
| ivb_vwap_profile_proxy | 2689 | 1.1372 | 0.8073 | -0.1841 |
| effort_vtracker_proxy | 1915 | 1.1956 | 0.9879 | -0.1444 |
| full_without_htf_proxy | 1121 | 1.1436 | 0.3488 | -0.1036 |
| full_no_delta_proxy | 613 | 1.2703 | 0.3538 | -0.0613 |
| full_with_delta_proxy | 556 | 1.2192 | 0.2531 | -0.0730 |

## Reference execution cost: 6 bps per side

| filter_variant | trades | win_rate | average_net_r | profit_factor | cumulative_net_return | maximum_drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| orb_only_proxy | 5126 | 0.4977 | -0.4027 | 0.5659 | -0.9931 | -0.9933 |
| vwap_profile_uniform_proxy | 2767 | 0.5034 | -0.3823 | 0.5872 | -0.9230 | -0.9256 |
| vwap_profile_close_proxy | 2728 | 0.5044 | -0.3727 | 0.5986 | -0.9137 | -0.9162 |
| ivb_vwap_profile_proxy | 2689 | 0.4946 | -0.3969 | 0.5624 | -0.9284 | -0.9285 |
| effort_vtracker_proxy | 1915 | 0.5572 | -0.2605 | 0.6520 | -0.8004 | -0.8043 |
| full_without_htf_proxy | 1121 | 0.5504 | -0.2630 | 0.6229 | -0.6488 | -0.6505 |
| full_no_delta_proxy | 613 | 0.5808 | -0.2052 | 0.7018 | -0.3513 | -0.3601 |
| full_with_delta_proxy | 556 | 0.5773 | -0.2236 | 0.6699 | -0.3571 | -0.3728 |

## Holdout at 6 bps per side

| filter_variant | trades | profit_factor | cumulative_net_return | maximum_drawdown |
| --- | --- | --- | --- | --- |
| orb_only_proxy | 1442 | 0.5085 | -0.7568 | -0.7575 |
| vwap_profile_uniform_proxy | 775 | 0.5119 | -0.5335 | -0.5335 |
| vwap_profile_close_proxy | 767 | 0.5331 | -0.5100 | -0.5100 |
| ivb_vwap_profile_proxy | 758 | 0.4918 | -0.5418 | -0.5427 |
| effort_vtracker_proxy | 532 | 0.6208 | -0.3525 | -0.3525 |
| full_without_htf_proxy | 304 | 0.6094 | -0.2252 | -0.2275 |
| full_no_delta_proxy | 164 | 0.6052 | -0.1284 | -0.1345 |
| full_with_delta_proxy | 149 | 0.6244 | -0.1097 | -0.1202 |

## Signal funnel

| filter_variant | raw_signals | selected_signals | executed_trades | signal_retention |
| --- | --- | --- | --- | --- |
| orb_only_proxy | 7938 | 7938 | 5126 | 1.0000 |
| vwap_profile_uniform_proxy | 7938 | 4005 | 2767 | 0.5045 |
| vwap_profile_close_proxy | 7938 | 3967 | 2728 | 0.4997 |
| ivb_vwap_profile_proxy | 7938 | 3893 | 2689 | 0.4904 |
| effort_vtracker_proxy | 7938 | 2154 | 1915 | 0.2714 |
| full_without_htf_proxy | 7938 | 1233 | 1121 | 0.1553 |
| full_no_delta_proxy | 7938 | 681 | 613 | 0.0858 |
| full_with_delta_proxy | 7938 | 600 | 556 | 0.0756 |

## Break-even one-way execution cost

| filter_variant | break_even_one_way_cost_bps |
| --- | --- |
| orb_only_proxy | 1.1543 |
| vwap_profile_uniform_proxy | 1.3699 |
| vwap_profile_close_proxy | 1.5114 |
| ivb_vwap_profile_proxy | 1.1006 |
| effort_vtracker_proxy | 1.7942 |
| full_without_htf_proxy | 1.3349 |
| full_no_delta_proxy | 2.4712 |
| full_with_delta_proxy | 2.0296 |

## Risk sizing at 6 bps per side

| filter_variant | sizing_variant | scope | trades | profit_factor | cumulative_net_return | maximum_drawdown | average_effective_leverage | trades_blocked_by_daily_halt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| orb_only_proxy | one_x_notional | all | 5126 | 0.5659 | -0.9931 | -0.9933 | 1.0000 | 0 |
| orb_only_proxy | one_x_notional | holdout_2025_plus | 1442 | 0.5085 | -0.7568 | -0.7575 | 1.0000 | 0 |
| orb_only_proxy | risk_025pct_cap3x | all | 5126 | 0.4046 | -0.9923 | -0.9924 | 0.9556 | 0 |
| orb_only_proxy | risk_025pct_cap3x | holdout_2025_plus | 1442 | 0.3388 | -0.7919 | -0.7922 | 1.0237 | 0 |
| orb_only_proxy | risk_025pct_cap3x_daily_halt_proxy | all | 3711 | 0.3880 | -0.9763 | -0.9764 | 0.9670 | 1415 |
| orb_only_proxy | risk_025pct_cap3x_daily_halt_proxy | holdout_2025_plus | 1003 | 0.3230 | -0.6837 | -0.6839 | 1.0739 | 1415 |
| full_no_delta_proxy | one_x_notional | all | 613 | 0.7018 | -0.3513 | -0.3601 | 1.0000 | 0 |
| full_no_delta_proxy | one_x_notional | holdout_2025_plus | 164 | 0.6052 | -0.1284 | -0.1345 | 1.0000 | 0 |
| full_no_delta_proxy | risk_025pct_cap3x | all | 613 | 0.5765 | -0.2647 | -0.2654 | 0.6904 | 0 |
| full_no_delta_proxy | risk_025pct_cap3x | holdout_2025_plus | 164 | 0.5490 | -0.0801 | -0.0813 | 0.7501 | 0 |
| full_no_delta_proxy | risk_025pct_cap3x_daily_halt_proxy | all | 607 | 0.5761 | -0.2631 | -0.2637 | 0.6920 | 6 |
| full_no_delta_proxy | risk_025pct_cap3x_daily_halt_proxy | holdout_2025_plus | 163 | 0.5575 | -0.0775 | -0.0787 | 0.7532 | 6 |
| full_with_delta_proxy | one_x_notional | all | 556 | 0.6699 | -0.3571 | -0.3728 | 1.0000 | 0 |
| full_with_delta_proxy | one_x_notional | holdout_2025_plus | 149 | 0.6244 | -0.1097 | -0.1202 | 1.0000 | 0 |
| full_with_delta_proxy | risk_025pct_cap3x | all | 556 | 0.5484 | -0.2619 | -0.2624 | 0.6942 | 0 |
| full_with_delta_proxy | risk_025pct_cap3x | holdout_2025_plus | 149 | 0.5708 | -0.0683 | -0.0698 | 0.7596 | 0 |
| full_with_delta_proxy | risk_025pct_cap3x_daily_halt_proxy | all | 551 | 0.5485 | -0.2599 | -0.2605 | 0.6960 | 5 |
| full_with_delta_proxy | risk_025pct_cap3x_daily_halt_proxy | holdout_2025_plus | 148 | 0.5807 | -0.0657 | -0.0672 | 0.7631 | 5 |

## Frozen workflow

1. **Macro/HTF bias proxy:** persistent 20-bar Donchian state from completed four-hour bars.
2. **Daily/session bias proxy:** price must agree with the current 09:30-16:00 UTC session VWAP.
3. **Area of interest proxy:** direction must agree with the previous completed session POC. Uniform high-low volume allocation is primary; close-bin allocation is a sensitivity.
4. **IVB proxy:** the first exactly six five-minute bars define the opening range. Targets 1/2/3 are the rolling 25th/50th/75th percentiles of same-direction session extension over the previous 60 sessions (minimum 20). A signal is not chased beyond target 2.
5. **Effort proxy:** signal-bar volume exceeds the prior 50-bar 75th percentile and its candle body agrees with direction.
6. **V-Tracker proxy:** signal-bar range exceeds the prior 20-bar median and closes in the directional outer quartile.
7. **Delta proxy:** five-bar sum of `volume * (close-open)/(high-low)`. It is a candle-position proxy, not aggressor delta, so the primary full variant excludes it.
8. **Entry/risk/exit:** confirmed signal, next five-minute open, stop one ATR beyond the signal bar, 2R static target, and the supplied 1.5 ATR activation / 0.5 ATR trailing logic.
9. **Risk-manager proxy:** 0.25% equity risk per initial stop, 3x leverage cap, halt after two losses or -0.75% summed session return.

## Causality and limitations

- Audit: **FAIL**.
- Profiles are previous-session estimates; five-minute bars do not reveal price-level volume.
- Synthetic delta is isolated in an ablation and must not be interpreted as order flow.
- Entries are next-bar, but stop/target ordering inside each five-minute bar still uses a deterministic OHLC path assumption.
- The file has 16 missing bars and a maximum 85-minute gap.
- Venue/product identity and funding are absent; 6 bps per side is a scenario, not a verified fee quote.
- Eight fixed variants share the holdout. Picking whichever looks best after reading this report is model selection, not independent confirmation.

Research only; live deployment remains blocked without trade-level data, verified product metadata, funding, and forward/paper execution evidence.
