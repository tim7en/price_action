# BTCUSDT Fabio Pine v6: native five-minute backtest

## Primary results

The source contains 436,729 native five-minute bars from 2022-01-01 through 2026-02-25. The literal Binance interpretation uses 09:30–16:00 **UTC** on all seven days. The New York-clock result is a separate sensitivity because the Pine code never supplies the timezone promised by its input label.

| session_interpretation | variant | trades | win_rate | average_net_r | profit_factor | cumulative_net_return | annualized_net_return | maximum_drawdown | average_effective_leverage | average_risk_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| literal_binance_utc | script_zero_cost | 3960 | 0.5982 | 0.0997 | 1.1787 | 2.1302 | 0.3167 | -0.1410 | 1.0000 | 0.0044 |
| literal_binance_utc | script_reference_cost | 3960 | 0.5063 | -0.3777 | 0.5891 | -0.9730 | -0.5814 | -0.9743 | 1.0000 | 0.0044 |
| literal_binance_utc | intended_1pct_risk_capped_10x | 3960 | 0.5063 | -0.3777 | 0.4295 | -1.0000 | -0.9653 | -1.0000 | 3.6966 | 0.0099 |
| label_intended_new_york | script_zero_cost | 2852 | 0.6034 | 0.1254 | 1.2559 | 3.4005 | 0.4294 | -0.1325 | 1.0000 | 0.0054 |
| label_intended_new_york | script_reference_cost | 2852 | 0.5558 | -0.2409 | 0.7441 | -0.8564 | -0.3737 | -0.8624 | 1.0000 | 0.0054 |
| label_intended_new_york | intended_1pct_risk_capped_10x | 2852 | 0.5558 | -0.2409 | 0.5928 | -0.9985 | -0.7917 | -0.9986 | 2.8898 | 0.0099 |

`script_reference_cost` assumes 6 bps per side: a 5-bps taker commission scenario plus 1 bp slippage. It is a scenario, not an account-specific fee quote. The repository's prior conservative BTC setting is represented by the 15-bps row in the cost table. Funding is not included.

## 2025 through February 2026 holdout

| session_interpretation | variant | trades | profit_factor | cumulative_net_return | maximum_drawdown |
| --- | --- | --- | --- | --- | --- |
| literal_binance_utc | script_zero_cost | 1059 | 1.0908 | 0.1460 | -0.1198 |
| literal_binance_utc | script_reference_cost | 1059 | 0.4791 | -0.6786 | -0.6796 |
| literal_binance_utc | intended_1pct_risk_capped_10x | 1059 | 0.3279 | -0.9904 | -0.9905 |
| label_intended_new_york | script_zero_cost | 811 | 1.3373 | 0.6631 | -0.0645 |
| label_intended_new_york | script_reference_cost | 811 | 0.7669 | -0.3715 | -0.3785 |
| label_intended_new_york | intended_1pct_risk_capped_10x | 811 | 0.5834 | -0.8473 | -0.8497 |

## Literal-session setup attribution at reference cost

| setup_scope | trades | win_rate | average_net_r | profit_factor | cumulative_net_return |
| --- | --- | --- | --- | --- | --- |
| all | 3960 | 0.5063 | -0.3777 | 0.5891 | -0.9730 |
| triple_a | 0 | nan | nan | nan | 0.0000 |
| orb | 3919 | 0.5073 | -0.3729 | 0.5906 | -0.9720 |
| value_area | 42 | 0.4048 | -0.8247 | 0.3584 | -0.0366 |

## Cost sensitivity

| session_interpretation | one_way_cost_bps | profit_factor | cumulative_net_return | maximum_drawdown |
| --- | --- | --- | --- | --- |
| literal_binance_utc | 0.0000 | 1.1787 | 2.1302 | -0.1410 |
| literal_binance_utc | 1.0000 | 1.0567 | 0.4180 | -0.1894 |
| literal_binance_utc | 1.5000 | 0.9997 | -0.0457 | -0.2271 |
| literal_binance_utc | 2.0000 | 0.9453 | -0.3577 | -0.4208 |
| literal_binance_utc | 2.5000 | 0.8932 | -0.5678 | -0.6072 |
| literal_binance_utc | 3.0000 | 0.8434 | -0.7091 | -0.7336 |
| literal_binance_utc | 5.0000 | 0.6657 | -0.9404 | -0.9438 |
| literal_binance_utc | 6.0000 | 0.5891 | -0.9730 | -0.9743 |
| literal_binance_utc | 7.5000 | 0.4884 | -0.9918 | -0.9921 |
| literal_binance_utc | 10.0000 | 0.3550 | -0.9989 | -0.9989 |
| literal_binance_utc | 15.0000 | 0.1882 | -1.0000 | -1.0000 |
| label_intended_new_york | 0.0000 | 1.2559 | 3.4005 | -0.1325 |
| label_intended_new_york | 1.0000 | 1.1548 | 1.4882 | -0.1551 |
| label_intended_new_york | 1.5000 | 1.1069 | 0.8709 | -0.1757 |
| label_intended_new_york | 2.0000 | 1.0607 | 0.4067 | -0.1957 |
| label_intended_new_york | 2.5000 | 1.0161 | 0.0577 | -0.2183 |
| label_intended_new_york | 3.0000 | 0.9731 | -0.2048 | -0.3120 |
| label_intended_new_york | 5.0000 | 0.8151 | -0.7460 | -0.7585 |
| label_intended_new_york | 6.0000 | 0.7441 | -0.8564 | -0.8624 |
| label_intended_new_york | 7.5000 | 0.6472 | -0.9390 | -0.9409 |
| label_intended_new_york | 10.0000 | 0.5089 | -0.9854 | -0.9856 |
| label_intended_new_york | 15.0000 | 0.3091 | -0.9992 | -0.9992 |

## Execution diagnostics

| session_interpretation | raw_long_signals | raw_short_signals | dual_direction_signal_bars | signals_blocked_position | signals_blocked_daily_losses | pending_entries_unfilled_at_end | open_position_at_end | trades_held_at_least_8h | trades_held_at_least_24h | maximum_holding_bars | target_exits | trailing_stop_exits | static_stop_exits |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| literal_binance_utc | 3193 | 2948 | 0 | 1967 | 214 | 0 | 0 | 6 | 1 | 414 | 154 | 2215 | 1591 |
| label_intended_new_york | 2327 | 2280 | 0 | 1687 | 68 | 0 | 0 | 15 | 3 | 365 | 114 | 1607 | 1131 |

## Causality and interpretation

- Literal UTC causality audit: **PASS**.
- New York sensitivity causality audit: **PASS**.
- Signals use confirmed five-minute bars; entries use the next available bar open.
- Pine's `sessionBars <= 6` defines seven bars, or 35 elapsed minutes, on a five-minute chart.
- The session string omits days, so Pine v6 applies it seven days per week.
- `riskPercent` remains unused; the supplied strategy deploys 100% of equity. The 1% row is a separate sizing diagnostic.
- The source lacks spot/perpetual metadata. Shorts require a margin or perpetual product, and historical funding/mark prices are absent.
- There are 16 missing bars, one maximum gap of 85 minutes, and 14 zero-volume bars.

This remains research-only.
