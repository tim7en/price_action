# NASDAQ identify-confirm-trade proxy backtest

Generated 2026-07-22T18:13:07.878037+00:00. This is a causal one-minute proxy for the transcript-defined workflow, not an exact replay of discretionary 15-second and Bookmap execution. Causality audit: **PASS**.

## Translation limits

- Data is one-minute OHLCV only, with no depth, queue, or aggressor-side information.
- Bookmap liquidity levels, true absorption, and discretionary trend-line selection are unavailable.
- The proxy uses completed 4h, 1h, 30m, and 5m pivots plus prior-session profile levels as the identify layer.
- Confirmation is reduced to one-minute approach direction, weak approach volume, rejection wick, and reversal volume.
- Signals are searched throughout the full 390-minute regular session; every position remains flat by the session close.
- Trade management uses next-open entries, structural stops, a half-off first target, and a trailing runner.
- The strict A+ proxy additionally requires a strong premarket level, a sweep/reclaim, at least two defended one-minute touches, a directional approach efficiency of at least 0.60, and structural signal-close risk no wider than 1.50 ATR.
- Risk remains at 0.25% of current equity per trade, so position size automatically falls after a loss. The transcript's illustrative 10% risk was not adopted.

## Overview

Candidate bars evaluated: **138**

Executed trades: **108**

| scope | trades | sessions | win_rate | partial_target_rate | average_gross_r | average_net_r | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_net_return | annualized_net_return | max_drawdown | average_holding_minutes | average_level_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | 108 | 108 | 0.3333 | 0.3241 | -0.1490 | -0.3393 | 0.7834 | 0.5823 | -0.3850 | -0.0853 | -0.0454 | -0.1113 | 7.8241 | 1.5278 |

## Strict A+ qualification

The A+ rules are pre-declared in configuration. They are a filter on the causal baseline signals; no parameter grid or outcome optimization was run against the 2025 holdout.

| criterion | passing_candidates | total_candidates | pass_rate |
| --- | --- | --- | --- |
| strong premarket level | 132 | 138 | 0.9565 |
| liquidity sweep and reclaim | 79 | 138 | 0.5725 |
| two or more defended touches | 77 | 138 | 0.5580 |
| clear directional approach | 53 | 138 | 0.3841 |
| clean structural stop | 122 | 138 | 0.8841 |
| all A+ conditions | 17 | 138 | 0.1232 |

Strict A+ candidate bars: **17**

Executed strict A+ trades: **14**

| scope | trades | sessions | win_rate | partial_target_rate | average_gross_r | average_net_r | break_even_one_way_cost_bps | cumulative_net_return | max_drawdown | average_holding_minutes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | 14 | 14 | 0.4286 | 0.3571 | 0.3976 | 0.1452 | 0.8229 | 0.0052 | -0.0149 | 13.3571 |
| development_2024 | 7 | 7 | 0.5714 | 0.4286 | 0.2634 | -0.0005 | 0.4307 | -0.0007 | -0.0034 | 14.0000 |
| holdout_2025 | 7 | 7 | 0.2857 | 0.2857 | 0.5318 | 0.2910 | 1.2759 | 0.0059 | -0.0087 | 12.7143 |

A+ versus rejected baseline trades:

| scope | trades | win_rate | average_net_r | break_even_one_way_cost_bps | cumulative_net_return | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| strict_A_plus | 14 | 0.4286 | 0.1452 | 0.8229 | 0.0052 | -0.0149 |
| rejected_non_A_plus | 97 | 0.3196 | -0.4020 | -0.5871 | -0.0913 | -0.1045 |

## Full-session timing

| session_block | candidate_signals | executed_trades | baseline_win_rate | baseline_average_net_r | baseline_cumulative_return | a_plus_candidates | a_plus_executed_trades | a_plus_win_rate | a_plus_average_net_r | a_plus_cumulative_return |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| open_0_59 | 15 | 15 | 0.4667 | -0.1605 | -0.0060 | 3 | 3 | 0.6667 | 0.3356 | 0.0025 |
| 60_119 | 28 | 25 | 0.2800 | -0.5018 | -0.0310 | 2 | 2 | 0.0000 | -1.2611 | -0.0063 |
| 120_179 | 22 | 14 | 0.1429 | -0.9662 | -0.0333 | 3 | 3 | 0.0000 | -1.1969 | -0.0090 |
| 180_239 | 26 | 19 | 0.3684 | -0.3344 | -0.0147 | 3 | 2 | 0.5000 | -0.4989 | -0.0025 |
| 240_299 | 22 | 15 | 0.3333 | -0.4469 | -0.0146 | 4 | 3 | 0.6667 | 0.3638 | 0.0030 |
| close_300_389 | 25 | 20 | 0.4000 | 0.2448 | 0.0118 | 2 | 1 | 1.0000 | 7.0460 | 0.0176 |

Identified A+ candidates and realized outcomes:

| timestamp | level_sources | a_plus_defended_touch_count | a_plus_approach_efficiency | a_plus_structural_risk_atr | side | exit_reason | net_r_multiple | execution_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2024-01-09 15:29:00+00:00 | pivot_low_30m|pivot_low_60m | 2 | 1.0000 | 1.1681 | long | stop | -1.1478 | executed |
| 2024-01-26 18:26:00+00:00 | pivot_high_30m | 2 | 0.8219 | 0.6787 | short | runner_stop | 0.2300 | executed |
| 2024-01-26 18:38:00+00:00 | pivot_high_30m | 4 | 0.7154 | 0.6448 | short | nan | nan | not_executed_by_portfolio_limits |
| 2024-01-30 18:31:00+00:00 | prior_session_vah | 2 | 0.7263 | 1.4108 | short | time | 0.4501 | executed |
| 2024-04-24 14:25:00+00:00 | pivot_high_240m|pivot_high_30m|pivot_high_60m | 2 | 0.6957 | 1.0845 | short | runner_stop | 0.9112 | executed |
| 2024-04-29 15:15:00+00:00 | prior_session_vah | 2 | 0.9752 | 0.7271 | short | stop | -1.2500 | executed |
| 2024-05-10 17:37:00+00:00 | pivot_high_60m | 2 | 0.7037 | 0.7698 | short | runner_stop | 2.1719 | executed |
| 2024-05-21 15:53:00+00:00 | pivot_low_60m | 2 | 0.7949 | 0.8950 | long | stop | -1.3686 | executed |
| 2024-05-21 17:12:00+00:00 | pivot_low_30m|prior_session_poc | 2 | 0.8602 | 0.7656 | long | nan | nan | not_executed_by_portfolio_limits |
| 2025-01-13 18:22:00+00:00 | pivot_low_240m | 4 | 0.8189 | 0.7465 | long | stop | -1.2278 | executed |
| 2025-01-23 19:13:00+00:00 | pivot_low_60m | 2 | 1.0000 | 0.6739 | long | stop | -1.5306 | executed |
| 2025-03-06 15:00:00+00:00 | prior_session_val | 2 | 0.6296 | 1.3840 | long | runner_stop_gap | 1.2434 | executed |
| 2025-04-25 15:30:00+00:00 | pivot_low_30m | 2 | 0.6520 | 1.1346 | long | stop | -1.1011 | executed |
| 2025-07-10 15:00:00+00:00 | pivot_high_240m | 3 | 0.8606 | 0.8384 | short | stop | -1.2721 | executed |
| 2025-07-16 15:58:00+00:00 | pivot_low_30m|pivot_low_60m | 3 | 0.6498 | 0.6897 | long | stop | -1.1211 | executed |
| 2025-07-16 18:49:00+00:00 | prior_session_low | 3 | 0.7742 | 0.9290 | long | nan | nan | not_executed_by_portfolio_limits |
| 2025-10-30 19:00:00+00:00 | pivot_high_240m | 4 | 0.7684 | 0.5788 | short | target_2_gap | 7.0460 | executed |

Strict A+ session bootstrap:

| scope | sessions | inference_reliable_20_sessions | mean_session_return_bps | bootstrap_mean_ci_low_bps | bootstrap_mean_ci_high_bps | bootstrap_probability_mean_positive |
| --- | --- | --- | --- | --- | --- | --- |
| all | 14 | False | 3.8653 | -20.3569 | 36.5390 | 0.5618 |
| development_2024 | 7 | False | -0.8891 | -21.1613 | 21.0300 | 0.4496 |
| holdout_2025 | 7 | False | 8.6196 | -29.8074 | 67.4950 | 0.5937 |

A+ sensitivity to its single best trade:

| scope | trades | win_rate | average_net_r | median_net_r | cumulative_net_return | excluded_trade | excluded_trade_net_r |
| --- | --- | --- | --- | --- | --- | --- | --- |
| all_A_plus | 14 | 0.4286 | 0.1452 | -1.1111 | 0.0052 |  | nan |
| excluding_best_trade | 13 | 0.3846 | -0.3856 | -1.1211 | -0.0122 | 2025-10-30 19:00:00+00:00 | 7.0460 |

With only 14 executed A+ trades, the A+ return, win rate, bootstrap interval, and positive-mean probability are descriptive only. They are not enough to estimate a stable edge.

## Development and holdout

| scope | trades | sessions | win_rate | partial_target_rate | average_gross_r | average_net_r | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_net_return | annualized_net_return | max_drawdown | average_holding_minutes | average_level_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| development_2024 | 58 | 58 | 0.2414 | 0.2241 | -0.4341 | -0.6450 | 0.4339 | 0.3071 | -1.0337 | -0.0873 | -0.0895 | -0.0862 | 6.0000 | 1.6897 |
| holdout_2025 | 50 | 50 | 0.4400 | 0.4400 | 0.1816 | 0.0154 | 1.3313 | 1.0329 | 0.5651 | 0.0022 | 0.0025 | -0.0262 | 9.9400 | 1.3400 |

## Session-block bootstrap

| scope | sessions | inference_reliable_20_sessions | mean_session_return_bps | bootstrap_mean_ci_low_bps | bootstrap_mean_ci_high_bps | bootstrap_probability_mean_positive |
| --- | --- | --- | --- | --- | --- | --- |
| all | 108 | True | -8.1919 | -14.3892 | -1.2867 | 0.0113 |
| development_2024 | 58 | True | -15.7089 | -22.2816 | -8.5004 | 0.0000 |
| holdout_2025 | 50 | True | 0.5279 | -9.9164 | 12.3559 | 0.5259 |

## Long and short split

| scope | trades | sessions | win_rate | partial_target_rate | average_gross_r | average_net_r | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_net_return | annualized_net_return | max_drawdown | average_holding_minutes | average_level_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| side::long | 65 | 65 | 0.2923 | 0.2923 | -0.3010 | -0.4764 | 0.5855 | 0.4475 | -0.8571 | -0.0717 | -0.0397 | -0.0891 | 8.2154 | 1.4154 |
| side::short | 43 | 43 | 0.3953 | 0.3721 | 0.0808 | -0.1320 | 1.1279 | 0.8146 | 0.1826 | -0.0147 | -0.0078 | -0.0347 | 7.2326 | 1.6977 |

## Blocked signals

| overlap | daily_loss_stop | session_trade_limit | unexecutable |
| --- | --- | --- | --- |
| 3 | 0 | 27 | 0 |

Strict A+ blocked signals:

| overlap | daily_loss_stop | session_trade_limit | unexecutable |
| --- | --- | --- | --- |
| 0 | 0 | 3 | 0 |

## Causality and leakage checks

| check | passed |
| --- | --- |
| all_identify_levels_known_by_session_open | True |
| all_candidates_have_strict_next_bar_execution | True |
| a_plus_context_ends_at_signal_bar | True |
| signal_entry_exit_order_is_strict | True |
| all_positions_flat_before_execution_deadline | True |
| same_bar_boundary_policy_is_stop_first | True |
| new_trailing_extreme_applies_next_bar_only | True |
| relative_volume_baseline_excludes_signal_bar | True |
| prior_session_profile_is_shifted_one_session | True |

- Higher-timeframe bars are timestamped only when the complete 5m/30m/1h/4h interval is available.
- Prior-session high, low, POC, VAH, and VAL are shifted one complete session.
- Relative-volume baselines exclude the current signal bar.
- A+ retest, clarity, sweep, and structural-risk features end at the signal bar; no post-signal confirmation is used.
- Signal decisions occur at the one-minute close; entries occur at the next minute's open.
- Same-bar stop/target collisions are resolved as stops. New trailing extremes affect only the following bar.

## Interpretation guardrails

- A profitable result here would validate only the one-minute proxy, not the exact live workflow from the transcript.
- A weak result would not disprove the live workflow because the unavailable 15-second and order-flow layers may carry most of the edge.
- The underlying Nasdaq-like feed remains unverified and is not aligned to CME NQ tick size.
- Any further refinement should stay out-of-sample and should not use the same 2025 holdout for repeated threshold tuning.

## Plots

- [Equity and drawdown](equity_and_drawdown.png)
- [Exit reasons](exit_reasons.png)
- [Baseline versus strict A+](a_plus_comparison.png)
