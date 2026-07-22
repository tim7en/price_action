# Session-Only POC Stop Optimizer and Leverage Survival Study

Generated 2026-07-22T02:35:22.541467+00:00.

## Central distinction

An exchange leverage setting is only a ceiling. Under risk-targeted sizing, effective notional is `risk budget / stop distance`, capped by the setting. Fully deploying 20x/40x/100x is a separate stress case that risks leverage multiplied by the stop percentage.

## Development-selected parameter candidates

| poc_scope | timeline | context | stop_factor_15m | holding_minutes | scope | selection_score | trades | sessions | cumulative_net_return | max_drawdown | net_profit_factor | win_rate | average_net_return_bps | average_effective_leverage | median_stop_fraction | maximum_risk_fraction_deployed | liquidations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| focus_cluster | rth_15_330m | none | 0.7500 | 30 | development_2024 | 3.7498 | 118 | 49 | 0.2202 | -0.0587 | 1.4591 | 0.5254 | 17.4478 | 6.7302 | 0.0016 | 0.0100 | 0 |
| focus_cluster | rth_15_330m | none | 0.7500 | 30 | evaluation_2025 | -0.7212 | 108 | 47 | -0.0732 | -0.1015 | 0.8726 | 0.3889 | -6.4485 | 5.7854 | 0.0019 | 0.0100 | 0 |
| 3d_or_5d | rth_15_330m | poc_migration | 0.5000 | 5 | development_2024 | 3.5802 | 45 | 18 | 0.0618 | -0.0173 | 1.5857 | 0.5778 | 13.6132 | 9.6061 | 0.0011 | 0.0100 | 0 |
| 3d_or_5d | rth_15_330m | poc_migration | 0.5000 | 5 | evaluation_2025 | 1.7841 | 44 | 23 | 0.0544 | -0.0305 | 1.3891 | 0.5455 | 12.4481 | 7.3561 | 0.0014 | 0.0100 | 0 |
| 3d_or_5d | opening_15_30m | none | 0.7500 | 5 | development_2024 | 3.5088 | 20 | 16 | 0.0430 | -0.0050 | 3.6142 | 0.6500 | 21.1674 | 4.1803 | 0.0026 | 0.0100 | 0 |
| 3d_or_5d | opening_15_30m | none | 0.7500 | 5 | evaluation_2025 | -0.5006 | 38 | 26 | -0.0110 | -0.0221 | 0.7955 | 0.4737 | -2.8721 | 3.2386 | 0.0031 | 0.0100 | 0 |
| focus_cluster | rth_15_330m | none | 1.0000 | 30 | development_2024 | 3.1750 | 116 | 49 | 0.1802 | -0.0568 | 1.4734 | 0.5172 | 14.7161 | 5.0746 | 0.0022 | 0.0100 | 0 |
| focus_cluster | rth_15_330m | none | 1.0000 | 30 | evaluation_2025 | -0.6339 | 106 | 47 | -0.0542 | -0.0855 | 0.8866 | 0.3962 | -4.7853 | 4.4716 | 0.0025 | 0.0100 | 0 |
| 3d_or_5d | rth_15_330m | poc_migration | 0.7500 | 5 | development_2024 | 2.8906 | 45 | 18 | 0.0401 | -0.0139 | 1.5135 | 0.5778 | 8.8950 | 6.4577 | 0.0017 | 0.0100 | 0 |
| 3d_or_5d | rth_15_330m | poc_migration | 0.7500 | 5 | evaluation_2025 | 1.1966 | 44 | 23 | 0.0322 | -0.0270 | 1.3522 | 0.5455 | 7.3947 | 4.9781 | 0.0021 | 0.0100 | 0 |
| 3d_or_5d | rth_15_330m | poc_migration | 0.2500 | 5 | development_2024 | 2.7989 | 48 | 18 | 0.0986 | -0.0352 | 1.5355 | 0.5625 | 20.2009 | 16.1392 | 0.0006 | 0.0100 | 0 |
| 3d_or_5d | rth_15_330m | poc_migration | 0.2500 | 5 | evaluation_2025 | 1.5394 | 44 | 23 | 0.0716 | -0.0465 | 1.3716 | 0.5000 | 16.4140 | 11.2347 | 0.0009 | 0.0100 | 0 |
| 3d_or_5d | opening_15_30m | none | 1.0000 | 5 | development_2024 | 2.6218 | 20 | 16 | 0.0321 | -0.0038 | 3.6142 | 0.6500 | 15.8755 | 3.1353 | 0.0034 | 0.0100 | 0 |
| 3d_or_5d | opening_15_30m | none | 1.0000 | 5 | evaluation_2025 | -0.4980 | 38 | 26 | -0.0083 | -0.0166 | 0.7955 | 0.4737 | -2.1540 | 2.4289 | 0.0041 | 0.0100 | 0 |
| focus_cluster | rth_15_330m | none | 1.2500 | 30 | development_2024 | 2.5676 | 115 | 49 | 0.1334 | -0.0519 | 1.4472 | 0.5304 | 11.1791 | 4.0833 | 0.0027 | 0.0100 | 0 |
| focus_cluster | rth_15_330m | none | 1.2500 | 30 | evaluation_2025 | -0.3244 | 102 | 47 | -0.0239 | -0.0738 | 0.9429 | 0.4020 | -2.0024 | 3.6400 | 0.0031 | 0.0100 | 0 |
| 3d_or_5d | opening_15_30m | none | 1.2500 | 5 | development_2024 | 2.0927 | 20 | 16 | 0.0256 | -0.0030 | 3.6142 | 0.6500 | 12.7004 | 2.5082 | 0.0043 | 0.0100 | 0 |
| 3d_or_5d | opening_15_30m | none | 1.2500 | 5 | evaluation_2025 | -0.4965 | 38 | 26 | -0.0066 | -0.0133 | 0.7955 | 0.4737 | -1.7232 | 1.9432 | 0.0052 | 0.0100 | 0 |
| 3d_or_5d | rth_15_330m | none | 0.7500 | 30 | development_2024 | 1.9888 | 195 | 78 | 0.1768 | -0.0889 | 1.2141 | 0.4718 | 8.9191 | 6.3695 | 0.0017 | 0.0100 | 0 |
| 3d_or_5d | rth_15_330m | none | 0.7500 | 30 | evaluation_2025 | -0.7122 | 176 | 77 | -0.0875 | -0.1229 | 0.9042 | 0.4148 | -4.6433 | 5.5086 | 0.0020 | 0.0100 | 0 |

## Expanding-quarter walk-forward selections

| test_quarter | poc_scope | timeline | context | stop_factor_15m | holding_minutes | training_score | training_trades | test_trades | test_return |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2024Q3 | 3d_or_5d | rth_15_330m | trend_10d_30d | 0.2500 | 30 | 6.2331 | 40 | 24 | -0.0120 |
| 2024Q4 | focus_cluster | rth_15_330m | trend_10d_30d | 0.5000 | 15 | 9.6411 | 30 | 24 | -0.1181 |
| 2025Q1 | focus_cluster | rth_15_330m | none | 0.7500 | 30 | 3.7498 | 118 | 25 | -0.0604 |
| 2025Q2 | 3d_or_5d | opening_15_30m | none | 0.7500 | 5 | 4.4632 | 28 | 10 | 0.0005 |
| 2025Q3 | 3d_or_5d | opening_15_30m | none | 0.7500 | 5 | 4.6734 | 38 | 14 | -0.0134 |
| 2025Q4 | 3d_or_5d | rth_15_330m | poc_migration | 0.2500 | 30 | 3.2564 | 86 | 2 | 0.0319 |

Walk-forward aggregate: `{"average_effective_leverage": 7.7407768513555375, "average_net_return_bps": -17.835694107631266, "cumulative_net_return": -0.16601235479526888, "liquidations": 0, "max_drawdown": -0.2439938951511832, "maximum_risk_fraction_deployed": 0.010000000000000002, "median_stop_fraction": 0.0015708904320719313, "net_profit_factor": 0.647313800809219, "sessions": 46, "trades": 99, "win_rate": 0.35353535353535354}`

## Historical leverage stress

| label | sizing_mode | leverage_setting | trades | sessions | cumulative_net_return | max_drawdown | net_profit_factor | win_rate | average_net_return_bps | average_effective_leverage | median_stop_fraction | maximum_risk_fraction_deployed | liquidations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| risk_targeted_20x | risk_targeted | 20.0000 | 48 | 42 | 0.0577 | -0.0175 | 1.7104 | 0.5833 | 11.8526 | 3.5585 | 0.0029 | 0.0100 | 0 |
| risk_targeted_40x | risk_targeted | 40.0000 | 48 | 42 | 0.0577 | -0.0175 | 1.7104 | 0.5833 | 11.8526 | 3.5585 | 0.0029 | 0.0100 | 0 |
| risk_targeted_100x | risk_targeted | 100.0000 | 48 | 42 | 0.0577 | -0.0175 | 1.7104 | 0.5833 | 11.8526 | 3.5585 | 0.0029 | 0.0100 | 0 |
| fixed_leverage_20x | fixed_leverage | 20.0000 | 48 | 42 | 0.3157 | -0.1122 | 1.5930 | 0.5833 | 63.5609 | 20.0000 | 0.0029 | 0.1501 | 0 |
| fixed_leverage_40x | fixed_leverage | 40.0000 | 48 | 42 | 0.6277 | -0.2236 | 1.5930 | 0.5833 | 127.1218 | 40.0000 | 0.0029 | 0.3003 | 0 |
| fixed_leverage_100x | fixed_leverage | 100.0000 | 48 | 42 | -0.9780 | -0.9952 | 1.3503 | 0.5833 | 221.4617 | 100.0000 | 0.0029 | 0.7507 | 1 |

## Session-bootstrap survival estimates

| label | years | source_sessions | simulated_sessions | median_final_equity | final_equity_p05 | final_equity_p95 | probability_finish_profitable | median_max_drawdown | probability_50pct_capital_loss | probability_80pct_capital_loss | probability_95pct_capital_loss |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| risk_targeted_20x | 1 | 42 | 22 | 1.0295 | 0.9837 | 1.0804 | 0.8488 | -0.0159 | 0.0000 | 0.0000 | 0.0000 |
| risk_targeted_20x | 3 | 42 | 66 | 1.0914 | 1.0084 | 1.1849 | 0.9657 | -0.0263 | 0.0000 | 0.0000 | 0.0000 |
| risk_targeted_40x | 1 | 42 | 22 | 1.0295 | 0.9837 | 1.0804 | 0.8488 | -0.0159 | 0.0000 | 0.0000 | 0.0000 |
| risk_targeted_40x | 3 | 42 | 66 | 1.0914 | 1.0084 | 1.1849 | 0.9657 | -0.0263 | 0.0000 | 0.0000 | 0.0000 |
| risk_targeted_100x | 1 | 42 | 22 | 1.0295 | 0.9837 | 1.0804 | 0.8488 | -0.0159 | 0.0000 | 0.0000 | 0.0000 |
| risk_targeted_100x | 3 | 42 | 66 | 1.0914 | 1.0084 | 1.1849 | 0.9657 | -0.0263 | 0.0000 | 0.0000 | 0.0000 |
| fixed_leverage_20x | 1 | 42 | 22 | 1.1576 | 0.8582 | 1.5409 | 0.7897 | -0.1065 | 0.0000 | 0.0000 | 0.0000 |
| fixed_leverage_20x | 3 | 42 | 66 | 1.5377 | 0.9268 | 2.5343 | 0.9181 | -0.1770 | 0.0004 | 0.0000 | 0.0000 |
| fixed_leverage_40x | 1 | 42 | 22 | 1.3004 | 0.7094 | 2.2972 | 0.7641 | -0.2130 | 0.0105 | 0.0000 | 0.0000 |
| fixed_leverage_40x | 3 | 42 | 66 | 2.1493 | 0.7738 | 5.8392 | 0.8914 | -0.3374 | 0.0376 | 0.0003 | 0.0000 |
| fixed_leverage_100x | 1 | 42 | 22 | 1.0140 | 0.0000 | 6.2468 | 0.5024 | -0.5075 | 0.4526 | 0.4087 | 0.4074 |
| fixed_leverage_100x | 3 | 42 | 66 | 0.0093 | 0.0000 | 26.4868 | 0.1978 | -0.9981 | 0.8185 | 0.7925 | 0.7530 |

## Plots

- [Stop and holding-time sensitivity](stop_holding_sensitivity.png)
- [Risk-targeted versus fixed-leverage equity](leverage_equity_and_drawdown.png)
- [Leverage survival probabilities](leverage_survival_probabilities.png)
- [Walk-forward optimizer equity](walk_forward_optimizer_equity.png)

## Automation contract

- Signals are restricted to the regular New York session and all positions close before the session ends.
- Only completed prior-session profiles and completed 15-minute blocks may influence a signal or stop.
- The grid searches POC scope, session timeline, 3d/10d or 10d/30d context, three-session POC migration, stop width, and maximum holding time.
- Parameter selection uses only data before each test quarter. The score is cumulative return divided by drawdown, discounted when fewer than 30 trades are available and rejected below 20 training trades.
- Risk-targeted variants risk at most 1.00% before gaps and slippage, regardless of whether the leverage cap is 20x, 40x, or 100x.
- Fixed-leverage stress tests deploy the full account-level notional. They use a simplified liquidation-distance proxy of `1/leverage - 0.50%`; it is not Binance's symbol-, tier-, margin-mode-, or account-specific liquidation calculation.
- Survival probabilities resample complete trading sessions. They are conditional on this short, selected 2024–2025 history and are not real probabilities of future survival.

## Material limitations

- The Nasdaq CSV has unverified venue/contract identity and cannot be treated as executable Binance, CME NQ, or MNQ data.
- Historical bars assume stop fills at the stop unless the liquidation proxy is closer. Real gaps, latency, mark-price liquidation, spread widening, rejected orders, and partial fills can make outcomes worse.
- The grid creates substantial multiple-testing risk. The quarterly walk-forward is more relevant than the best full-sample cell, but also has little history.
- A stop-loss order cannot guarantee its intended loss during discontinuous markets. High leverage therefore cannot be made safe merely by placing a stop.
