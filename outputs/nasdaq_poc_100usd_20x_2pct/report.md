# NASDAQ hierarchical POC: $100 / 20x / 2% scenario

## Result

The internally consistent interpretation is **2% initial-stop risk with 20x as a leverage cap**. Starting at $100.00, the modeled account finishes at **$118.03**, a **18.03%** compounded return over 46 score-3-or-better trades. Maximum drawdown is **-3.84%**. This uses the frozen 0.50-bps-per-side cost assumption.

## Equity summary

| variant | trades | start_equity | final_equity | net_profit_dollars | cumulative_return | maximum_drawdown | profit_factor | win_rate | maximum_losing_streak | average_effective_leverage | maximum_effective_leverage | average_stop_risk_fraction | maximum_stop_risk_fraction | leverage_cap_bound_trades | worst_realized_trade_return | best_realized_trade_return | total_modeled_cost_dollars |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| risk_2pct_cap_20x | 46 | 100.0000 | 118.0278 | 18.0278 | 0.1803 | -0.0384 | 2.4261 | 0.6087 | 3 | 11.2773 | 20.0000 | 0.0194 | 0.0200 | 5 | -0.0212 | 0.0385 | 5.7522 |
| forced_20x_notional | 46 | 100.0000 | 139.2411 | 39.2411 | 0.3924 | -0.0592 | 2.3318 | 0.6087 | 3 | 20.0000 | 20.0000 | 0.0463 | 0.1546 | 0 | -0.0404 | 0.0608 | 11.1800 |

## Annual path

| variant | year | trades | start_equity | final_equity | period_return | period_maximum_drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| risk_2pct_cap_20x | 2024 | 25 | 100.0000 | 111.5865 | 0.1159 | -0.0158 |
| risk_2pct_cap_20x | 2025 | 21 | 111.5865 | 118.0278 | 0.0577 | -0.0384 |
| forced_20x_notional | 2024 | 25 | 100.0000 | 118.7297 | 0.1873 | -0.0453 |
| forced_20x_notional | 2025 | 21 | 118.7297 | 139.2411 | 0.1728 | -0.0592 |

## Cost sensitivity for the valid 2%-risk interpretation

| one_way_cost_bps | final_equity | cumulative_return | maximum_drawdown | profit_factor |
| --- | --- | --- | --- | --- |
| 0.0000 | 124.2855 | 0.2429 | -0.0344 | 3.2116 |
| 0.2500 | 121.1173 | 0.2112 | -0.0364 | 2.7935 |
| 0.5000 | 118.0278 | 0.1803 | -0.0384 | 2.4261 |
| 1.0000 | 112.0772 | 0.1208 | -0.0426 | 1.8386 |
| 1.5000 | 106.4192 | 0.0642 | -0.0472 | 1.3957 |
| 2.0000 | 101.0397 | 0.0104 | -0.0594 | 1.0691 |
| 3.0000 | 91.0634 | -0.0894 | -0.1207 | 0.6523 |
| 5.0000 | 73.9052 | -0.2609 | -0.2701 | 0.2846 |

The edge is cost-sensitive: at 2 bps per side the final balance is approximately $101.04; at 3 bps it is approximately $91.06.

## Why forced 20x is different

Forcing 20x on every trade finishes at $139.24, but it is not a 2%-risk strategy. Its average planned stop exposure is 4.63%, and its maximum is 15.46%. The extra return is purchased with materially larger tail exposure.

## Execution feasibility

| account_equity | minimum_mnq_notional_in_sample | median_mnq_notional_in_sample | maximum_mnq_notional_in_sample | minimum_equity_for_one_mnq_at_20x | median_equity_for_one_mnq_at_20x | maximum_fractional_mnq_at_100usd_and_20x | cme_mnq_contract_multiplier |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 100.0000 | 35083.6600 | 40725.8700 | 49323.6800 | 1754.1830 | 2036.2935 | 0.0570 | 2.0000 |

CME MNQ has a $2-per-index-point multiplier. At the historical entry prices, one indivisible MNQ contract is far larger than the permitted $2,000 notional for a $100 account at 20x. Therefore this curve assumes a fractional CFD, spread-bet, or synthetic instrument. It is not executable as one CME MNQ contract.

## Assumptions and limits

- Trades are the frozen hierarchical ledger with score >= 3; 25 occur in 2024 development and 21 in 2025 validation.
- Each trade compounds from current equity. Required leverage is `2% / stop distance`; actual leverage is capped at 20x.
- Costs are charged on entry and exit as 0.50 bps per side. Funding, fixed commissions, taxes, spread variation, partial-fill degradation, and liquidation penalties are excluded.
- The original 89-trade POC ledger was selected with visibility into both years, and its NASDAQ-like source has an unverified price grid. This is a scenario, not a forecast.
- The 2% setting overrides the research hierarchy's 0.10%-0.25% risk map and is eight times its maximum recommended trade risk.

Methodology audit: **PASS**.
