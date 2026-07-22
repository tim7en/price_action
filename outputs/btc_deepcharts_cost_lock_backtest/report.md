# BTC five-minute cost-aware trailing-stop comparison

## Rule

The baseline activates its 0.5-ATR trail after a 1.5-ATR favorable move. The alternative assumes 6 bps per side and creates a fixed floor at entry plus the 12-bps round trip plus a 2-bps net-profit buffer. It activates when price reaches that floor plus one 0.5-ATR trailing offset, then ratchets with each favorable extreme. Static stop and 2R target remain unchanged.

A normal stop fill at the floor locks the buffer under this cost model. A price gap can fill beyond it, so profit is never guaranteed.

The change helps but does not make the strategy deployable at the design cost. Full-history return improves from -35.1% to -28.0%, and holdout return improves from -12.8% to -9.1%. Profit factor remains below one (0.723 overall, 0.682 holdout), and break-even cost is 3.34 bps per side versus the assumed 6. The higher win rate reflects many small locked gains, but the initial-stop losses still outweigh them.

## Results at the design cost

| exit_variant | scope | trades | win_rate | profit_factor | cumulative_net_return | maximum_drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| atr_trailing_baseline | all | 613 | 0.5808 | 0.7018 | -0.3513 | -0.3601 |
| atr_trailing_baseline | holdout_2025_plus | 164 | 0.5854 | 0.6052 | -0.1284 | -0.1345 |
| cost_aware_profit_lock | all | 617 | 0.6726 | 0.7231 | -0.2803 | -0.3231 |
| cost_aware_profit_lock | holdout_2025_plus | 162 | 0.6852 | 0.6816 | -0.0906 | -0.1011 |

## Exit behavior

| exit_variant | trades | trailing_exits | trailing_exit_share | trailing_net_profitable | trailing_net_profitable_share | trailing_locked_buffer_or_more | trailing_gap_exits | target_exits | static_stop_exits | median_trailing_net_return | minimum_trailing_net_return |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| atr_trailing_baseline | 613 | 391 | 0.6378 | 344 | 0.8798 | 331 | 0 | 12 | 210 | 0.0016 | -0.0010 |
| cost_aware_profit_lock | 617 | 399 | 0.6467 | 399 | 1.0000 | 399 | 1 | 16 | 202 | 0.0012 | 0.0002 |

## Cost curve

| exit_variant | one_way_cost_bps | trades | profit_factor | cumulative_net_return | maximum_drawdown |
| --- | --- | --- | --- | --- | --- |
| atr_trailing_baseline | 0.0000 | 613 | 1.2703 | 0.3538 | -0.0613 |
| atr_trailing_baseline | 1.0000 | 613 | 1.1583 | 0.1976 | -0.0649 |
| atr_trailing_baseline | 2.0000 | 613 | 1.0539 | 0.0595 | -0.0847 |
| atr_trailing_baseline | 3.0000 | 613 | 0.9564 | -0.0628 | -0.1351 |
| atr_trailing_baseline | 6.0000 | 613 | 0.7018 | -0.3513 | -0.3601 |
| atr_trailing_baseline | 15.0000 | 613 | 0.2503 | -0.7852 | -0.7852 |
| cost_aware_profit_lock | 0.0000 | 617 | 1.4527 | 0.5090 | -0.0345 |
| cost_aware_profit_lock | 1.0000 | 617 | 1.3056 | 0.3339 | -0.0543 |
| cost_aware_profit_lock | 2.0000 | 617 | 1.1703 | 0.1791 | -0.0858 |
| cost_aware_profit_lock | 3.0000 | 617 | 1.0456 | 0.0422 | -0.1219 |
| cost_aware_profit_lock | 6.0000 | 617 | 0.7231 | -0.2803 | -0.3231 |
| cost_aware_profit_lock | 15.0000 | 617 | 0.1921 | -0.7633 | -0.7657 |

## Break-even cost

| exit_variant | break_even_one_way_cost_bps |
| --- | --- |
| atr_trailing_baseline | 2.4712 |
| cost_aware_profit_lock | 3.3352 |

## 0.25% stop-risk sizing, 3x cap

| exit_variant | sizing_variant | scope | trades | profit_factor | cumulative_net_return | maximum_drawdown | average_effective_leverage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| atr_trailing_baseline | risk_025pct_cap3x | all | 613 | 0.5765 | -0.2647 | -0.2654 | 0.6904 |
| atr_trailing_baseline | risk_025pct_cap3x | holdout_2025_plus | 164 | 0.5490 | -0.0801 | -0.0813 | 0.7501 |
| atr_trailing_baseline | risk_025pct_cap3x_daily_halt_proxy | all | 607 | 0.5761 | -0.2631 | -0.2637 | 0.6920 |
| atr_trailing_baseline | risk_025pct_cap3x_daily_halt_proxy | holdout_2025_plus | 163 | 0.5575 | -0.0775 | -0.0787 | 0.7532 |
| cost_aware_profit_lock | risk_025pct_cap3x | all | 617 | 0.5774 | -0.2577 | -0.2596 | 0.6785 |
| cost_aware_profit_lock | risk_025pct_cap3x | holdout_2025_plus | 162 | 0.6103 | -0.0669 | -0.0677 | 0.7354 |
| cost_aware_profit_lock | risk_025pct_cap3x_daily_halt_proxy | all | 611 | 0.5746 | -0.2582 | -0.2601 | 0.6800 |
| cost_aware_profit_lock | risk_025pct_cap3x_daily_halt_proxy | holdout_2025_plus | 161 | 0.6100 | -0.0670 | -0.0678 | 0.7385 |

## Audit and interpretation

- Cost-lock audit: **PASS**.
- Signals are the unchanged `full_no_delta_proxy`; only exit management differs.
- Both variants enter at the next five-minute open and use the same deterministic intrabar OHLC path.
- The cost floor covers modeled commission/slippage, not funding, spread changes, latency, or gap loss.
- This test is still based on five-minute OHLCV and is not genuine order-flow reconstruction.
