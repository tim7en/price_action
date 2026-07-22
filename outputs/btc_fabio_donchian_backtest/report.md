# BTC Fabio five-minute signals with higher-timeframe Donchian bias

## Test design

The lower-timeframe engine is the literal Binance-UTC Pine translation. A fixed 20-bar Donchian breakout state is calculated independently on complete 15-minute, one-hour, and four-hour bars. Long five-minute signals are allowed only in a persistent long state and shorts only in a persistent short state. The higher-timeframe bar must have closed before the five-minute signal bar opens.

This is a price-structure bias, not true order flow. The OHLCV source cannot observe bid/ask delta, footprint imbalances, resting liquidity, or tape absorption.

## Zero-cost comparison

| filter_variant | trades | profit_factor | cumulative_net_return | maximum_drawdown |
| --- | --- | --- | --- | --- |
| unfiltered | 3960 | 1.1787 | 2.1302 | -0.1410 |
| donchian_15m_20 | 2614 | 1.1437 | 0.8174 | -0.1478 |
| donchian_60m_20 | 2215 | 1.1669 | 0.8331 | -0.1028 |
| donchian_240m_20 | 2131 | 1.2110 | 1.0898 | -0.0957 |

## Reference-cost comparison: 6 bps per side

| filter_variant | trades | win_rate | average_net_r | profit_factor | cumulative_net_return | annualized_net_return | maximum_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- |
| unfiltered | 3960 | 0.5063 | -0.3777 | 0.5891 | -0.9730 | -0.5814 | -0.9743 |
| donchian_15m_20 | 2614 | 0.5000 | -0.3851 | 0.5615 | -0.9212 | -0.4582 | -0.9233 |
| donchian_60m_20 | 2215 | 0.5147 | -0.3538 | 0.5875 | -0.8716 | -0.3916 | -0.8753 |
| donchian_240m_20 | 2131 | 0.5204 | -0.3527 | 0.6172 | -0.8381 | -0.3564 | -0.8440 |

## 2025 through February 2026 holdout at reference cost

| filter_variant | trades | profit_factor | cumulative_net_return | maximum_drawdown |
| --- | --- | --- | --- | --- |
| unfiltered | 1059 | 0.4791 | -0.6786 | -0.6796 |
| donchian_15m_20 | 713 | 0.4698 | -0.5331 | -0.5331 |
| donchian_60m_20 | 602 | 0.4912 | -0.4698 | -0.4710 |
| donchian_240m_20 | 579 | 0.4943 | -0.4595 | -0.4727 |

## Signal funnel

| filter_variant | raw_signals | directionally_allowed_signals | executed_trades | signal_retention | trade_retention_vs_unfiltered |
| --- | --- | --- | --- | --- | --- |
| unfiltered | 6141 | 6141 | 3960 | 1.0000 | 1.0000 |
| donchian_15m_20 | 6141 | 3788 | 2614 | 0.6168 | 0.6601 |
| donchian_60m_20 | 6141 | 3180 | 2215 | 0.5178 | 0.5593 |
| donchian_240m_20 | 6141 | 3100 | 2131 | 0.5048 | 0.5381 |

## Cost break-even

| filter_variant | break_even_one_way_cost_bps |
| --- | --- |
| unfiltered | 1.4410 |
| donchian_15m_20 | 1.1428 |
| donchian_60m_20 | 1.3682 |
| donchian_240m_20 | 1.7297 |

## Causality and decision

- Audit status: **PASS**.
- Donchian channels exclude the current higher-timeframe bar and use a persistent breakout state.
- Context is mapped with `available_time <= signal_time`; no incomplete HTF bar is used.
- Filtering occurs before position overlap and the three-loss daily cutoff are simulated.
- Source gaps remain: 16 missing five-minute bars and a maximum 85-minute gap.
- The three timeframes are a fixed robustness comparison, not a parameter optimization. Selecting the best result after seeing the shared holdout would not constitute independent validation.

Live deployment remains blocked by execution costs, missing bid/ask data, unverified spot/perpetual identity, and absent funding history.
