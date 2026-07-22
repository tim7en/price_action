# BTC five-minute $100 / 20x-cap / 2%-risk scenario

## Decision

The system trades both directions: **340 longs** and **277 shorts**. At the frozen 6-bps-per-side design cost, neither direction is viable. Combined equity falls from $100.00 to **$8.64** (-91.36%) with -91.53% maximum drawdown.

Short-only is less damaging than long-only, but still fails: short-only ends at $47.03, versus $18.38 for long-only. These are direction-attribution paths from the existing ledger, not freshly replayed one-sided strategies.

## Direction results at 6 bps per side

| direction | trades | start_equity | final_equity | net_profit_dollars | cumulative_return | maximum_drawdown | profit_factor | win_rate | maximum_losing_streak | average_effective_leverage | maximum_effective_leverage | average_stop_risk_fraction | maximum_stop_risk_fraction | leverage_cap_bound_trades | worst_realized_trade_return | best_realized_trade_return | total_modeled_cost_dollars |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| both | 617 | 100.0000 | 8.6440 | -91.3560 | -0.9136 | -0.9153 | 0.5801 | 0.6726 | 5 | 5.4043 | 20.0000 | 0.0200 | 0.0200 | 7 | -0.0439 | 0.0369 | 161.9984 |
| long_only | 340 | 100.0000 | 18.3807 | -81.6193 | -0.8162 | -0.8277 | 0.5173 | 0.6471 | 4 | 5.9450 | 20.0000 | 0.0199 | 0.0200 | 6 | -0.0439 | 0.0359 | 109.3980 |
| short_only | 277 | 100.0000 | 47.0274 | -52.9726 | -0.5297 | -0.5561 | 0.6764 | 0.7040 | 5 | 4.7406 | 20.0000 | 0.0200 | 0.0200 | 1 | -0.0435 | 0.0369 | 123.2808 |

## Development and holdout

| direction | scope | trades | start_equity | final_equity | scope_return | maximum_drawdown | profit_factor | win_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| both | all_2022_to_2026 | 617 | 100.0000 | 8.6440 | -0.9136 | -0.9153 | 0.5801 | 0.6726 |
| both | development_pre_2025 | 455 | 100.0000 | 15.2644 | -0.8474 | -0.8525 | 0.5686 | 0.6681 |
| both | holdout_2025_plus | 162 | 15.2644 | 8.6440 | -0.4337 | -0.4376 | 0.6142 | 0.6852 |
| long_only | all_2022_to_2026 | 340 | 100.0000 | 18.3807 | -0.8162 | -0.8277 | 0.5173 | 0.6471 |
| long_only | development_pre_2025 | 256 | 100.0000 | 26.2529 | -0.7375 | -0.7471 | 0.4978 | 0.6406 |
| long_only | holdout_2025_plus | 84 | 26.2529 | 18.3807 | -0.2999 | -0.3478 | 0.5794 | 0.6667 |
| short_only | all_2022_to_2026 | 277 | 100.0000 | 47.0274 | -0.5297 | -0.5561 | 0.6764 | 0.7040 |
| short_only | development_pre_2025 | 199 | 100.0000 | 58.1436 | -0.4186 | -0.4589 | 0.6819 | 0.7035 |
| short_only | holdout_2025_plus | 78 | 58.1436 | 47.0274 | -0.1912 | -0.2077 | 0.6615 | 0.7051 |

## Cost sensitivity

| one_way_cost_bps | direction | trades | final_equity | cumulative_return | maximum_drawdown | profit_factor |
| --- | --- | --- | --- | --- | --- | --- |
| 0.0000 | both | 617 | 477.2069 | 3.7721 | -0.1432 | 1.4129 |
| 0.0000 | long_only | 340 | 209.5270 | 1.0953 | -0.1307 | 1.3347 |
| 0.0000 | short_only | 277 | 227.7544 | 1.2775 | -0.1571 | 1.5260 |
| 1.0000 | both | 617 | 245.1930 | 1.4519 | -0.1886 | 1.2316 |
| 1.0000 | long_only | 340 | 139.9043 | 0.3990 | -0.1908 | 1.1535 |
| 1.0000 | short_only | 277 | 175.2577 | 0.7526 | -0.1823 | 1.3459 |
| 2.0000 | both | 617 | 125.8515 | 0.2585 | -0.2750 | 1.0712 |
| 2.0000 | long_only | 340 | 93.3531 | -0.0665 | -0.2762 | 0.9947 |
| 2.0000 | short_only | 277 | 134.8123 | 0.3481 | -0.2426 | 1.1844 |
| 3.0000 | both | 617 | 64.5291 | -0.3547 | -0.5026 | 0.9283 |
| 3.0000 | long_only | 340 | 62.2489 | -0.3775 | -0.4384 | 0.8545 |
| 3.0000 | short_only | 277 | 103.6630 | 0.0366 | -0.3059 | 1.0388 |
| 4.0000 | both | 617 | 33.0521 | -0.6695 | -0.7005 | 0.8002 |
| 4.0000 | long_only | 340 | 41.4801 | -0.5852 | -0.6210 | 0.7297 |
| 4.0000 | short_only | 277 | 79.6818 | -0.2032 | -0.3640 | 0.9067 |
| 6.0000 | both | 617 | 8.6440 | -0.9136 | -0.9153 | 0.5801 |
| 6.0000 | long_only | 340 | 18.3807 | -0.8162 | -0.8277 | 0.5173 |
| 6.0000 | short_only | 277 | 47.0274 | -0.5297 | -0.5561 | 0.6764 |

The cost curve is the main finding. At zero cost, the combined path would finish near $477.21; at 2 bps it finishes near $125.85; at 3 bps it is already below its starting balance. The five-minute signal contains gross structure, but turnover cost consumes it.

## Leverage interpretation

Each trade targets 2% initial-stop exposure using `min(20x, 2% / stop_fraction)`. Average effective leverage for the combined path is 5.40x; the cap binds on 7 trades. Forcing 20x on every trade instead leaves approximately **$0.0100**, matching the earlier near-ruin stress result and no longer respecting 2% stop risk.

## Limits

- Signals and exits are the unchanged five-minute `full_no_delta_proxy` with the 6-bps cost-aware profit-lock trail.
- Funding, liquidation engine, maintenance margin, latency, variable spread, and nonlinear slippage are excluded.
- Long-only and short-only curves condition the already-executed ledger. A new one-sided replay could admit signals that were originally blocked by an open position.
- Five-minute OHLCV proxies are not genuine footprint delta or order-book data.
- Development ends before 2025; the 2025-plus section is unchanged holdout, but the wider research program has inspected these results.

Methodology audit: **PASS**. Status: **REJECT at 6 bps per side**.
