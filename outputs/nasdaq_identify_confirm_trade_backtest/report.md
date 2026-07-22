# NASDAQ identify-confirm-trade proxy backtest

Generated 2026-07-22T18:00:43.028518+00:00. This is a causal one-minute proxy for the transcript-defined workflow, not an exact replay of discretionary 15-second and Bookmap execution. Causality audit: **PASS**.

## Translation limits

- Data is one-minute OHLCV only, with no depth, queue, or aggressor-side information.
- Bookmap liquidity levels, true absorption, and discretionary trend-line selection are unavailable.
- The proxy uses completed 4h, 1h, 30m, and 5m pivots plus prior-session profile levels as the identify layer.
- Confirmation is reduced to one-minute approach direction, weak approach volume, rejection wick, and reversal volume.
- Trade management uses next-open entries, structural stops, a half-off first target, and a trailing runner.
- The strict A+ proxy additionally requires a strong premarket level, a sweep/reclaim, at least two defended one-minute touches, a directional approach efficiency of at least 0.60, and structural signal-close risk no wider than 1.50 ATR.

## Overview

Candidate bars evaluated: **15**  
Executed trades: **14**

| scope | trades | sessions | win_rate | partial_target_rate | average_gross_r | average_net_r | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_net_return | annualized_net_return | max_drawdown | average_holding_minutes | average_level_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | 14 | 14 | 0.5000 | 0.3571 | -0.0735 | -0.1701 | 0.8530 | 0.6873 | -0.3804 | -0.0060 | -0.0038 | -0.0111 | 3.8571 | 1.7143 |

## Strict A+ qualification

The A+ rules are pre-declared in configuration. They are a filter on the causal baseline signals; no parameter grid or outcome optimization was run against the 2025 holdout.

| criterion | passing_candidates | total_candidates | pass_rate |
| --- | --- | --- | --- |
| strong premarket level | 12 | 15 | 0.8000 |
| liquidity sweep and reclaim | 11 | 15 | 0.7333 |
| two or more defended touches | 8 | 15 | 0.5333 |
| clear directional approach | 9 | 15 | 0.6000 |
| clean structural stop | 14 | 15 | 0.9333 |
| all A+ conditions | 3 | 15 | 0.2000 |

Strict A+ candidate bars: **3**

Executed strict A+ trades: **2**

| scope | trades | sessions | win_rate | partial_target_rate | average_gross_r | average_net_r | break_even_one_way_cost_bps | cumulative_net_return | max_drawdown | average_holding_minutes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | 2 | 2 | 1.0000 | 0.5000 | 0.8663 | 0.7872 | 5.4771 | 0.0039 | 0.0000 | 4.5000 |
| development_2024 | 1 | 1 | 1.0000 | 0.0000 | 0.4451 | 0.3310 | 1.9502 | 0.0008 | 0.0000 | 4.0000 |
| holdout_2025 | 1 | 1 | 1.0000 | 1.0000 | 1.2874 | 1.2434 | 14.6179 | 0.0031 | 0.0000 | 5.0000 |

Identified A+ candidates and realized outcomes:

| timestamp | level_sources | a_plus_defended_touch_count | a_plus_approach_efficiency | a_plus_structural_risk_atr | side | exit_reason | net_r_multiple | execution_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2024-01-09 15:29:00+00:00 | pivot_low_30m|pivot_low_60m | 2 | 1.0000 | 1.1681 | long | nan | nan | unexecutable_at_window_end |
| 2024-04-24 14:25:00+00:00 | pivot_high_240m|pivot_high_30m|pivot_high_60m | 2 | 0.6957 | 1.0845 | short | time | 0.3310 | executed |
| 2025-03-06 15:00:00+00:00 | prior_session_val | 2 | 0.6296 | 1.3840 | long | runner_stop_gap | 1.2434 | executed |

Strict A+ session bootstrap:

| scope | sessions | inference_reliable_20_sessions | mean_session_return_bps | bootstrap_mean_ci_low_bps | bootstrap_mean_ci_high_bps | bootstrap_probability_mean_positive |
| --- | --- | --- | --- | --- | --- | --- |
| all | 2 | False | 19.6799 | 8.2755 | 31.0843 | 1.0000 |
| development_2024 | 1 | False | 8.2755 | 8.2755 | 8.2755 | 1.0000 |
| holdout_2025 | 1 | False | 31.0843 | 31.0843 | 31.0843 | 1.0000 |

With only 2 executed A+ trades, the A+ return, win rate, bootstrap interval, and positive-mean probability are descriptive only. They are not enough to estimate a stable edge.

## Development and holdout

| scope | trades | sessions | win_rate | partial_target_rate | average_gross_r | average_net_r | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_net_return | annualized_net_return | max_drawdown | average_holding_minutes | average_level_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| development_2024 | 6 | 6 | 0.6667 | 0.5000 | 0.1968 | 0.0876 | 1.5903 | 1.2429 | 0.9016 | 0.0013 | 0.0019 | -0.0054 | 4.0000 | 2.3333 |
| holdout_2025 | 8 | 8 | 0.3750 | 0.2500 | -0.2762 | -0.3634 | 0.5581 | 0.4664 | -1.5839 | -0.0073 | -0.0104 | -0.0103 | 3.7500 | 1.2500 |

## Session-block bootstrap

| scope | sessions | inference_reliable_20_sessions | mean_session_return_bps | bootstrap_mean_ci_low_bps | bootstrap_mean_ci_high_bps | bootstrap_probability_mean_positive |
| --- | --- | --- | --- | --- | --- | --- |
| all | 14 | False | -4.2518 | -16.6728 | 8.8135 | 0.2544 |
| development_2024 | 6 | False | 2.1909 | -14.9111 | 19.2079 | 0.5945 |
| holdout_2025 | 8 | False | -9.0838 | -23.3019 | 8.3520 | 0.1452 |

## Long and short split

| scope | trades | sessions | win_rate | partial_target_rate | average_gross_r | average_net_r | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_net_return | annualized_net_return | max_drawdown | average_holding_minutes | average_level_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| side::long | 9 | 9 | 0.5556 | 0.4444 | 0.0901 | -0.0036 | 1.2028 | 0.9925 | 0.4808 | -0.0001 | -0.0001 | -0.0054 | 3.4444 | 1.6667 |
| side::short | 5 | 5 | 0.4000 | 0.2000 | -0.3680 | -0.4697 | 0.3866 | 0.2872 | -1.8096 | -0.0059 | -0.0038 | -0.0082 | 4.6000 | 1.8000 |

## Blocked signals

| overlap | daily_loss_stop | session_trade_limit | unexecutable |
| --- | --- | --- | --- |
| 0 | 0 | 0 | 1 |

Strict A+ blocked signals:

| overlap | daily_loss_stop | session_trade_limit | unexecutable |
| --- | --- | --- | --- |
| 0 | 0 | 0 | 1 |

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
