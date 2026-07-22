# NASDAQ identify-confirm-trade proxy backtest

Generated 2026-07-22T17:52:20.065264+00:00. This is a causal one-minute proxy for the transcript-defined workflow, not an exact replay of discretionary 15-second and Bookmap execution. Causality audit: **PASS**.

## Translation limits

- Data is one-minute OHLCV only, with no depth, queue, or aggressor-side information.
- Bookmap liquidity levels, true absorption, and discretionary trend-line selection are unavailable.
- The proxy uses completed 4h, 1h, 30m, and 5m pivots plus prior-session profile levels as the identify layer.
- Confirmation is reduced to one-minute approach direction, weak approach volume, rejection wick, and reversal volume.
- Trade management uses next-open entries, structural stops, a half-off first target, and a trailing runner.

## Overview

Candidate bars evaluated: **15**  
Executed trades: **14**

| scope | trades | sessions | win_rate | partial_target_rate | average_gross_r | average_net_r | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_net_return | annualized_net_return | max_drawdown | average_holding_minutes | average_level_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | 14 | 14 | 0.5000 | 0.3571 | -0.0735 | -0.1701 | 0.8530 | 0.6873 | -0.3804 | -0.0060 | -0.0038 | -0.0111 | 3.8571 | 1.7143 |

## Development and holdout

| scope | trades | sessions | win_rate | partial_target_rate | average_gross_r | average_net_r | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_net_return | annualized_net_return | max_drawdown | average_holding_minutes | average_level_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| development_2024 | 6 | 6 | 0.6667 | 0.5000 | 0.1968 | 0.0876 | 1.5903 | 1.2429 | 0.9016 | 0.0013 | 0.0019 | -0.0054 | 4.0000 | 2.3333 |
| holdout_2025 | 8 | 8 | 0.3750 | 0.2500 | -0.2762 | -0.3634 | 0.5581 | 0.4664 | -1.5839 | -0.0073 | -0.0104 | -0.0103 | 3.7500 | 1.2500 |

## Session-block bootstrap

| scope | sessions | mean_session_return_bps | bootstrap_mean_ci_low_bps | bootstrap_mean_ci_high_bps | bootstrap_probability_mean_positive |
| --- | --- | --- | --- | --- | --- |
| all | 14 | -4.2518 | -16.6728 | 8.8135 | 0.2544 |
| development_2024 | 6 | 2.1909 | -14.9111 | 19.2079 | 0.5945 |
| holdout_2025 | 8 | -9.0838 | -23.3019 | 8.3520 | 0.1452 |

## Long and short split

| scope | trades | sessions | win_rate | partial_target_rate | average_gross_r | average_net_r | gross_profit_factor | net_profit_factor | break_even_one_way_cost_bps | cumulative_net_return | annualized_net_return | max_drawdown | average_holding_minutes | average_level_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| side::long | 9 | 9 | 0.5556 | 0.4444 | 0.0901 | -0.0036 | 1.2028 | 0.9925 | 0.4808 | -0.0001 | -0.0001 | -0.0054 | 3.4444 | 1.6667 |
| side::short | 5 | 5 | 0.4000 | 0.2000 | -0.3680 | -0.4697 | 0.3866 | 0.2872 | -1.8096 | -0.0059 | -0.0038 | -0.0082 | 4.6000 | 1.8000 |

## Blocked signals

| overlap | daily_loss_stop | session_trade_limit | unexecutable |
| --- | --- | --- | --- |
| 0 | 0 | 0 | 1 |

## Causality and leakage checks

| check | passed |
| --- | --- |
| all_identify_levels_known_by_session_open | True |
| all_candidates_have_strict_next_bar_execution | True |
| signal_entry_exit_order_is_strict | True |
| all_positions_flat_before_execution_deadline | True |
| same_bar_boundary_policy_is_stop_first | True |
| new_trailing_extreme_applies_next_bar_only | True |
| relative_volume_baseline_excludes_signal_bar | True |
| prior_session_profile_is_shifted_one_session | True |

- Higher-timeframe bars are timestamped only when the complete 5m/30m/1h/4h interval is available.
- Prior-session high, low, POC, VAH, and VAL are shifted one complete session.
- Relative-volume baselines exclude the current signal bar.
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
