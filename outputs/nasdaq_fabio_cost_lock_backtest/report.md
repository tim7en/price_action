# NASDAQ one-minute cost-aware trailing-stop comparison

## Rule and decision

The translated Pine baseline activates a 0.5-ATR trail after a 1.5-ATR favorable move. The alternative assumes 0.50 bps per side, places its locked floor beyond the 1.00-bp round trip plus a 0.25-bp net buffer, and activates when price can support that floor plus the 0.5-ATR offset. The stop then ratchets with favorable extremes. Signal selection, static stop, 2R target, three-loss session cutoff, and next-open entry are unchanged.

At the design cost, full-history return changes from -7.4% to -8.1%; holdout changes from 0.6% to -1.3%. Cost-lock PF is 0.907 overall and 0.972 in holdout. Its break-even cost is 0.316 bps per side.

**Decision: reject the earlier cost lock for the assumed 0.50-bps execution.** The original trail already leaves every observed trailing exit above costs and the requested buffer. Earlier activation raises completed trades from 1769 to 2280, while median net trailing gain falls from 0.085% to 0.030%. The added turnover converts the small positive baseline holdout into a loss. The earlier lock is profitable in the full sample only below its 0.316-bps break-even estimate, which is not independent validation.

## Results at 0.50 bps per side

| exit_variant | scope | trades | win_rate | profit_factor | cumulative_net_return | maximum_drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| atr_trailing_baseline | all | 1769 | 0.5721 | 0.9371 | -0.0739 | -0.1087 |
| atr_trailing_baseline | holdout_2025 | 868 | 0.5818 | 1.0117 | 0.0055 | -0.0573 |
| cost_aware_profit_lock | all | 2280 | 0.7307 | 0.9074 | -0.0805 | -0.0937 |
| cost_aware_profit_lock | holdout_2025 | 1105 | 0.7348 | 0.9724 | -0.0128 | -0.0639 |

## Exit behavior

| exit_variant | trades | trailing_exits | trailing_exit_share | trailing_net_profitable | trailing_net_profitable_share | trailing_locked_buffer_or_more | trailing_gap_exits | target_exits | static_stop_exits | median_trailing_net_return | minimum_trailing_net_return |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| atr_trailing_baseline | 1769 | 978 | 0.5529 | 978 | 1.0000 | 978 | 0 | 34 | 757 | 0.0009 | 0.0001 |
| cost_aware_profit_lock | 2280 | 1649 | 0.7232 | 1649 | 1.0000 | 1649 | 0 | 17 | 614 | 0.0003 | 0.0000 |

## Cost curve

| exit_variant | one_way_cost_bps | trades | profit_factor | cumulative_net_return | maximum_drawdown |
| --- | --- | --- | --- | --- | --- |
| atr_trailing_baseline | 0.0000 | 1769 | 1.0925 | 0.1053 | -0.0428 |
| atr_trailing_baseline | 0.1000 | 1769 | 1.0598 | 0.0669 | -0.0515 |
| atr_trailing_baseline | 0.2000 | 1769 | 1.0279 | 0.0298 | -0.0603 |
| atr_trailing_baseline | 0.2500 | 1769 | 1.0122 | 0.0117 | -0.0668 |
| atr_trailing_baseline | 0.3000 | 1769 | 0.9968 | -0.0060 | -0.0753 |
| atr_trailing_baseline | 0.4000 | 1769 | 0.9666 | -0.0406 | -0.0921 |
| atr_trailing_baseline | 0.5000 | 1769 | 0.9371 | -0.0739 | -0.1087 |
| atr_trailing_baseline | 0.7500 | 1769 | 0.8666 | -0.1523 | -0.1597 |
| atr_trailing_baseline | 1.0000 | 1769 | 0.8003 | -0.2241 | -0.2281 |
| cost_aware_profit_lock | 0.0000 | 2280 | 1.1750 | 0.1549 | -0.0244 |
| cost_aware_profit_lock | 0.1000 | 2280 | 1.1184 | 0.1035 | -0.0318 |
| cost_aware_profit_lock | 0.2000 | 2280 | 1.0634 | 0.0543 | -0.0419 |
| cost_aware_profit_lock | 0.2500 | 2280 | 1.0365 | 0.0305 | -0.0469 |
| cost_aware_profit_lock | 0.3000 | 2280 | 1.0099 | 0.0073 | -0.0521 |
| cost_aware_profit_lock | 0.4000 | 2280 | 0.9580 | -0.0376 | -0.0724 |
| cost_aware_profit_lock | 0.5000 | 2280 | 0.9074 | -0.0805 | -0.0937 |
| cost_aware_profit_lock | 0.7500 | 2280 | 0.7872 | -0.1796 | -0.1805 |
| cost_aware_profit_lock | 1.0000 | 2280 | 0.6781 | -0.2680 | -0.2683 |

## Break-even cost

| exit_variant | break_even_one_way_cost_bps |
| --- | --- |
| atr_trailing_baseline | 0.2829 |
| cost_aware_profit_lock | 0.3159 |

## 0.25% stop-risk sizing, 3x cap

| exit_variant | sizing_variant | scope | trades | profit_factor | cumulative_net_return | maximum_drawdown | average_effective_leverage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| atr_trailing_baseline | risk_025pct_cap3x | all | 1769 | 0.8895 | -0.1967 | -0.2103 | 1.9981 |
| atr_trailing_baseline | risk_025pct_cap3x | holdout_2025 | 868 | 0.9262 | -0.0679 | -0.1207 | 1.9505 |
| atr_trailing_baseline | risk_025pct_cap3x_daily_halt_proxy | all | 1451 | 0.9191 | -0.1226 | -0.1337 | 1.9427 |
| atr_trailing_baseline | risk_025pct_cap3x_daily_halt_proxy | holdout_2025 | 714 | 0.9399 | -0.0463 | -0.0984 | 1.8961 |
| cost_aware_profit_lock | risk_025pct_cap3x | all | 2280 | 0.8406 | -0.2232 | -0.2237 | 2.0239 |
| cost_aware_profit_lock | risk_025pct_cap3x | holdout_2025 | 1105 | 0.8607 | -0.0989 | -0.1446 | 1.9482 |
| cost_aware_profit_lock | risk_025pct_cap3x_daily_halt_proxy | all | 1943 | 0.8335 | -0.2033 | -0.2039 | 1.9882 |
| cost_aware_profit_lock | risk_025pct_cap3x_daily_halt_proxy | holdout_2025 | 946 | 0.8729 | -0.0784 | -0.1276 | 1.8990 |

## Audit and limits

- Underlying signal audit: **PASS**.
- Cost-lock audit: **PASS**.
- A normal floor fill covers modeled costs and the buffer; a gap may not.
- Intrabar order still uses the deterministic one-minute OHLC path because tick data are absent.
- Instrument identity remains unverified and 94.1% of closes are off the CME NQ quarter-point grid.
- A bps cost model is retained for comparability. Real NQ/MNQ validation requires contract-aware commissions, tick slippage, and a verified futures feed.

Research only.
