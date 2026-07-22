# Session-Only POC Stop Optimizer and Leverage Survival Study

Generated 2026-07-22T02:45:56.060199+00:00.

## Central distinction

An exchange leverage setting is only a ceiling. Under risk-targeted sizing, effective notional is `risk budget / stop distance`, capped by the setting. Fully deploying 20x/40x/100x is a separate stress case that risks leverage multiplied by the stop percentage.

Deployment gate: **BLOCKED**. Reasons: Nasdaq CSV instrument and venue identity are unverified; execution venue and contract mapping are unverified; fewer than 200 naive walk-forward trades; naive expanding-quarter optimizer lost money out of sample; frozen candidate loses money under configured Binance costs.

## Frozen research candidate

The broadest positive parameter plateau was 3d/5d prior-session POC acceptance aligned with three-session POC migration, between 15 and 330 minutes after the New York open, a stop of `max(1m ATR, 0.50 × last completed 15m range)`, and a five-minute maximum hold. This specification was identified using both years and is therefore a post-study candidate for forward paper trading, not a validated production strategy.

| poc_scope | timeline | context | stop_factor_15m | holding_minutes | trades_development | cumulative_net_return_development | max_drawdown_development | trades_evaluation | cumulative_net_return_evaluation | max_drawdown_evaluation | diagnostic_stability_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3d_or_5d | rth_15_330m | poc_migration | 0.5000 | 5 | 45 | 0.0618 | -0.0173 | 44 | 0.0544 | -0.0305 | 1.7841 |
| 3d_or_5d | rth_15_330m | poc_migration | 0.2500 | 5 | 48 | 0.0986 | -0.0352 | 44 | 0.0716 | -0.0465 | 1.5394 |
| 3d_or_5d | rth_15_330m | poc_migration | 0.7500 | 5 | 45 | 0.0401 | -0.0139 | 44 | 0.0322 | -0.0270 | 1.1966 |
| 3d_or_5d | rth_15_330m | trend_10d_30d | 1.2500 | 30 | 73 | 0.0564 | -0.0493 | 59 | 0.0884 | -0.0293 | 1.1440 |
| 3d_or_5d | rth_15_330m | poc_migration | 0.2500 | 30 | 46 | 0.0806 | -0.0734 | 42 | 0.2167 | -0.0443 | 1.0975 |
| 3d_or_5d | rth_15_330m | trend_10d_30d | 0.7500 | 30 | 74 | 0.1090 | -0.0818 | 63 | 0.0879 | -0.0584 | 1.0739 |
| 3d_or_5d | rth_15_330m | trend_10d_30d | 1.0000 | 30 | 74 | 0.0829 | -0.0547 | 63 | 0.0572 | -0.0529 | 1.0441 |
| 3d_or_5d | rth_15_330m | poc_migration | 1.0000 | 5 | 45 | 0.0249 | -0.0129 | 44 | 0.0202 | -0.0216 | 0.9372 |
| 3d_or_5d | rth_15_330m | trend_3d_10d | 0.7500 | 30 | 67 | 0.0747 | -0.0596 | 54 | 0.0541 | -0.0446 | 0.9080 |
| 3d_or_5d | rth_15_330m | poc_migration | 1.2500 | 5 | 45 | 0.0159 | -0.0123 | 44 | 0.0152 | -0.0172 | 0.8834 |
| 3d_or_5d | rth_15_330m | poc_migration | 0.2500 | 15 | 47 | 0.0591 | -0.0723 | 43 | 0.1507 | -0.0466 | 0.8173 |
| focus_cluster | rth_15_330m | trend_10d_30d | 1.0000 | 30 | 46 | 0.0431 | -0.0550 | 40 | 0.0522 | -0.0375 | 0.7825 |
| focus_cluster | rth_15_330m | trend_10d_30d | 1.2500 | 30 | 45 | 0.0332 | -0.0481 | 38 | 0.0738 | -0.0216 | 0.6907 |
| 3d_or_5d | rth_15_330m | trend_3d_10d_plus_migration | 0.5000 | 5 | 25 | 0.0194 | -0.0219 | 28 | 0.0438 | -0.0305 | 0.6369 |
| 3d_or_5d | rth_15_330m | trend_10d_30d | 0.5000 | 30 | 85 | 0.1255 | -0.1112 | 65 | 0.0678 | -0.0966 | 0.6097 |

## Development-selected parameter candidates

| poc_scope | timeline | context | stop_factor_15m | holding_minutes | scope | selection_score | trades | sessions | cumulative_net_return | max_drawdown | net_profit_factor | win_rate | average_net_return_bps | average_effective_leverage | median_stop_fraction | median_risk_fraction_deployed | maximum_risk_fraction_deployed | median_planned_stop_loss_with_costs | maximum_planned_stop_loss_with_costs | liquidations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| focus_cluster | rth_15_330m | none | 0.7500 | 30 | development_2024 | 3.7498 | 118 | 49 | 0.2202 | -0.0587 | 1.4591 | 0.5254 | 17.4478 | 6.7302 | 0.0016 | 0.0100 | 0.0100 | 0.0106 | 0.0119 | 0 |
| focus_cluster | rth_15_330m | none | 0.7500 | 30 | evaluation_2025 | -0.7212 | 108 | 47 | -0.0732 | -0.1015 | 0.8726 | 0.3889 | -6.4485 | 5.7854 | 0.0019 | 0.0100 | 0.0100 | 0.0105 | 0.0119 | 0 |
| 3d_or_5d | rth_15_330m | poc_migration | 0.5000 | 5 | development_2024 | 3.5802 | 45 | 18 | 0.0618 | -0.0173 | 1.5857 | 0.5778 | 13.6132 | 9.6061 | 0.0011 | 0.0100 | 0.0100 | 0.0109 | 0.0129 | 0 |
| 3d_or_5d | rth_15_330m | poc_migration | 0.5000 | 5 | evaluation_2025 | 1.7841 | 44 | 23 | 0.0544 | -0.0305 | 1.3891 | 0.5455 | 12.4481 | 7.3561 | 0.0014 | 0.0100 | 0.0100 | 0.0107 | 0.0117 | 0 |
| 3d_or_5d | opening_15_30m | none | 0.7500 | 5 | development_2024 | 3.5088 | 20 | 16 | 0.0430 | -0.0050 | 3.6142 | 0.6500 | 21.1674 | 4.1803 | 0.0026 | 0.0100 | 0.0100 | 0.0104 | 0.0107 | 0 |
| 3d_or_5d | opening_15_30m | none | 0.7500 | 5 | evaluation_2025 | -0.5006 | 38 | 26 | -0.0110 | -0.0221 | 0.7955 | 0.4737 | -2.8721 | 3.2386 | 0.0031 | 0.0100 | 0.0100 | 0.0103 | 0.0107 | 0 |
| focus_cluster | rth_15_330m | none | 1.0000 | 30 | development_2024 | 3.1750 | 116 | 49 | 0.1802 | -0.0568 | 1.4734 | 0.5172 | 14.7161 | 5.0746 | 0.0022 | 0.0100 | 0.0100 | 0.0105 | 0.0115 | 0 |
| focus_cluster | rth_15_330m | none | 1.0000 | 30 | evaluation_2025 | -0.6339 | 106 | 47 | -0.0542 | -0.0855 | 0.8866 | 0.3962 | -4.7853 | 4.4716 | 0.0025 | 0.0100 | 0.0100 | 0.0104 | 0.0113 | 0 |
| 3d_or_5d | rth_15_330m | poc_migration | 0.7500 | 5 | development_2024 | 2.8906 | 45 | 18 | 0.0401 | -0.0139 | 1.5135 | 0.5778 | 8.8950 | 6.4577 | 0.0017 | 0.0100 | 0.0100 | 0.0106 | 0.0119 | 0 |
| 3d_or_5d | rth_15_330m | poc_migration | 0.7500 | 5 | evaluation_2025 | 1.1966 | 44 | 23 | 0.0322 | -0.0270 | 1.3522 | 0.5455 | 7.3947 | 4.9781 | 0.0021 | 0.0100 | 0.0100 | 0.0105 | 0.0112 | 0 |
| 3d_or_5d | rth_15_330m | poc_migration | 0.2500 | 5 | development_2024 | 2.7989 | 48 | 18 | 0.0986 | -0.0352 | 1.5355 | 0.5625 | 20.2009 | 16.1392 | 0.0006 | 0.0100 | 0.0100 | 0.0116 | 0.0133 | 0 |
| 3d_or_5d | rth_15_330m | poc_migration | 0.2500 | 5 | evaluation_2025 | 1.5394 | 44 | 23 | 0.0716 | -0.0465 | 1.3716 | 0.5000 | 16.4140 | 11.2347 | 0.0009 | 0.0100 | 0.0100 | 0.0111 | 0.0122 | 0 |
| 3d_or_5d | opening_15_30m | none | 1.0000 | 5 | development_2024 | 2.6218 | 20 | 16 | 0.0321 | -0.0038 | 3.6142 | 0.6500 | 15.8755 | 3.1353 | 0.0034 | 0.0100 | 0.0100 | 0.0103 | 0.0106 | 0 |
| 3d_or_5d | opening_15_30m | none | 1.0000 | 5 | evaluation_2025 | -0.4980 | 38 | 26 | -0.0083 | -0.0166 | 0.7955 | 0.4737 | -2.1540 | 2.4289 | 0.0041 | 0.0100 | 0.0100 | 0.0102 | 0.0105 | 0 |
| focus_cluster | rth_15_330m | none | 1.2500 | 30 | development_2024 | 2.5676 | 115 | 49 | 0.1334 | -0.0519 | 1.4472 | 0.5304 | 11.1791 | 4.0833 | 0.0027 | 0.0100 | 0.0100 | 0.0104 | 0.0112 | 0 |
| focus_cluster | rth_15_330m | none | 1.2500 | 30 | evaluation_2025 | -0.3244 | 102 | 47 | -0.0239 | -0.0738 | 0.9429 | 0.4020 | -2.0024 | 3.6400 | 0.0031 | 0.0100 | 0.0100 | 0.0103 | 0.0111 | 0 |
| 3d_or_5d | opening_15_30m | none | 1.2500 | 5 | development_2024 | 2.0927 | 20 | 16 | 0.0256 | -0.0030 | 3.6142 | 0.6500 | 12.7004 | 2.5082 | 0.0043 | 0.0100 | 0.0100 | 0.0102 | 0.0104 | 0 |
| 3d_or_5d | opening_15_30m | none | 1.2500 | 5 | evaluation_2025 | -0.4965 | 38 | 26 | -0.0066 | -0.0133 | 0.7955 | 0.4737 | -1.7232 | 1.9432 | 0.0052 | 0.0100 | 0.0100 | 0.0102 | 0.0104 | 0 |
| 3d_or_5d | rth_15_330m | none | 0.7500 | 30 | development_2024 | 1.9888 | 195 | 78 | 0.1768 | -0.0889 | 1.2141 | 0.4718 | 8.9191 | 6.3695 | 0.0017 | 0.0100 | 0.0100 | 0.0106 | 0.0119 | 0 |
| 3d_or_5d | rth_15_330m | none | 0.7500 | 30 | evaluation_2025 | -0.7122 | 176 | 77 | -0.0875 | -0.1229 | 0.9042 | 0.4148 | -4.6433 | 5.5086 | 0.0020 | 0.0100 | 0.0100 | 0.0105 | 0.0116 | 0 |

## Expanding-quarter walk-forward selections

| test_quarter | poc_scope | timeline | context | stop_factor_15m | holding_minutes | training_score | training_trades | test_trades | test_return |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2024Q3 | 3d_or_5d | rth_15_330m | trend_10d_30d | 0.2500 | 30 | 6.2331 | 40 | 24 | -0.0120 |
| 2024Q4 | focus_cluster | rth_15_330m | trend_10d_30d | 0.5000 | 15 | 9.6411 | 30 | 24 | -0.1181 |
| 2025Q1 | focus_cluster | rth_15_330m | none | 0.7500 | 30 | 3.7498 | 118 | 25 | -0.0604 |
| 2025Q2 | 3d_or_5d | opening_15_30m | none | 0.7500 | 5 | 4.4632 | 28 | 10 | 0.0005 |
| 2025Q3 | 3d_or_5d | opening_15_30m | none | 0.7500 | 5 | 4.6734 | 38 | 14 | -0.0134 |
| 2025Q4 | 3d_or_5d | rth_15_330m | poc_migration | 0.2500 | 30 | 3.2564 | 86 | 2 | 0.0319 |

Walk-forward aggregate: `{"average_effective_leverage": 7.7407768513555375, "average_net_return_bps": -17.835694107631266, "cumulative_net_return": -0.16601235479526888, "liquidations": 0, "max_drawdown": -0.2439938951511832, "maximum_planned_stop_loss_with_costs": 0.012908722857142858, "maximum_risk_fraction_deployed": 0.010000000000000002, "median_planned_stop_loss_with_costs": 0.010636581635220126, "median_risk_fraction_deployed": 0.01, "median_stop_fraction": 0.0015708904320719313, "net_profit_factor": 0.647313800809219, "sessions": 46, "trades": 99, "win_rate": 0.35353535353535354}`

## Historical leverage stress

These results use the frozen research candidate and the Nasdaq study's 0.5 bp one-way cost scenario.

| label | trades | cumulative_net_return | max_drawdown | win_rate | average_effective_leverage | median_stop_fraction | median_planned_stop_loss_with_costs | maximum_planned_stop_loss_with_costs | liquidations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| risk_targeted_20x | 89 | 0.1203 | -0.0305 | 0.5618 | 8.3916 | 0.0012 | 0.0108 | 0.0119 | 0 |
| risk_targeted_40x | 89 | 0.1195 | -0.0305 | 0.5618 | 8.4937 | 0.0012 | 0.0108 | 0.0129 | 0 |
| risk_targeted_100x | 89 | 0.1195 | -0.0305 | 0.5618 | 8.4937 | 0.0012 | 0.0108 | 0.0129 | 0 |
| fixed_leverage_20x | 89 | 0.4809 | -0.1865 | 0.5618 | 20.0000 | 0.0012 | 0.0263 | 0.1566 | 0 |
| fixed_leverage_40x | 89 | 1.0405 | -0.3487 | 0.5618 | 40.0000 | 0.0012 | 0.0525 | 0.3133 | 0 |
| fixed_leverage_100x | 89 | 2.4925 | -0.7087 | 0.5618 | 100.0000 | 0.0012 | 0.1313 | 0.7832 | 0 |

## Turnover and Binance-cost stress

The local Binance execution profile assumes 15.00 bps per side (configured fee plus slippage). This is a cost proxy applied to the Nasdaq path, **not** a verified Binance/Nasdaq instrument mapping.

| one_way_cost_bps | label | trades | cumulative_net_return | max_drawdown | average_effective_leverage | liquidations |
| --- | --- | --- | --- | --- | --- | --- |
| 15.0000 | risk_targeted_20x | 79 | -0.8395 | -0.8360 | 8.2495 | 0 |
| 15.0000 | risk_targeted_40x | 79 | -0.8442 | -0.8407 | 8.3646 | 0 |
| 15.0000 | risk_targeted_100x | 79 | -0.8442 | -0.8407 | 8.3646 | 0 |
| 15.0000 | fixed_leverage_20x | 79 | -0.9874 | -0.9875 | 20.0000 | 0 |
| 15.0000 | fixed_leverage_40x | 79 | -0.9999 | -0.9999 | 40.0000 | 0 |
| 15.0000 | fixed_leverage_100x | 79 | -1.0000 | -1.0000 | 100.0000 | 0 |

The complete sensitivity from 0.5 bps through the configured Binance proxy is in `execution_cost_sensitivity.csv`. The edge changing sign between cost scenarios is a deployment blocker, not a detail to optimize away.

## Session-bootstrap survival estimates

| label | years | source_sessions | simulated_sessions | median_final_equity | final_equity_p05 | final_equity_p95 | probability_finish_profitable | median_max_drawdown | probability_50pct_capital_loss | probability_80pct_capital_loss | probability_95pct_capital_loss |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| risk_targeted_20x | 1 | 41 | 23 | 1.0631 | 0.9558 | 1.1963 | 0.8205 | -0.0379 | 0.0000 | 0.0000 | 0.0000 |
| risk_targeted_20x | 3 | 41 | 69 | 1.2089 | 1.0013 | 1.4754 | 0.9508 | -0.0620 | 0.0000 | 0.0000 | 0.0000 |
| risk_targeted_40x | 1 | 41 | 23 | 1.0628 | 0.9552 | 1.1961 | 0.8192 | -0.0382 | 0.0000 | 0.0000 | 0.0000 |
| risk_targeted_40x | 3 | 41 | 69 | 1.2075 | 1.0000 | 1.4744 | 0.9500 | -0.0623 | 0.0000 | 0.0000 | 0.0000 |
| risk_targeted_100x | 1 | 41 | 23 | 1.0628 | 0.9552 | 1.1961 | 0.8192 | -0.0382 | 0.0000 | 0.0000 | 0.0000 |
| risk_targeted_100x | 3 | 41 | 69 | 1.2075 | 1.0000 | 1.4744 | 0.9500 | -0.0623 | 0.0000 | 0.0000 | 0.0000 |
| fixed_leverage_20x | 1 | 41 | 23 | 1.2389 | 0.8348 | 1.8743 | 0.8142 | -0.1296 | 0.0001 | 0.0000 | 0.0000 |
| fixed_leverage_20x | 3 | 41 | 69 | 1.9326 | 0.9675 | 3.9399 | 0.9412 | -0.2082 | 0.0026 | 0.0000 | 0.0000 |
| fixed_leverage_40x | 1 | 41 | 23 | 1.4785 | 0.6706 | 3.3444 | 0.7939 | -0.2524 | 0.0269 | 0.0001 | 0.0000 |
| fixed_leverage_40x | 3 | 41 | 69 | 3.3201 | 0.8376 | 13.5185 | 0.9231 | -0.3865 | 0.0604 | 0.0015 | 0.0000 |
| fixed_leverage_100x | 1 | 41 | 23 | 2.0361 | 0.2575 | 14.6922 | 0.7177 | -0.5758 | 0.2895 | 0.0639 | 0.0042 |
| fixed_leverage_100x | 3 | 41 | 69 | 8.4189 | 0.2471 | 271.7579 | 0.8390 | -0.7625 | 0.3923 | 0.1441 | 0.0264 |

## Plots

- [Stop and holding-time sensitivity](stop_holding_sensitivity.png)
- [Execution-cost sensitivity](execution_cost_sensitivity.png)
- [Risk-targeted versus fixed-leverage equity](leverage_equity_and_drawdown.png)
- [Leverage survival probabilities](leverage_survival_probabilities.png)
- [Walk-forward optimizer equity](walk_forward_optimizer_equity.png)

## Automation contract

- Signals are restricted to the regular New York session and all positions close before the session ends.
- Only completed prior-session profiles and completed 15-minute blocks may influence a signal or stop.
- The research candidate is frozen in code; changing it creates a new model version and requires a new forward test.
- The grid searches POC scope, session timeline, 3d/10d or 10d/30d context, three-session POC migration, stop width, and maximum holding time.
- Parameter selection uses only data before each test quarter. The score is cumulative return divided by drawdown, discounted when fewer than 30 trades are available and rejected below 20 training trades.
- Risk-targeted variants risk at most 1.00% before gaps and slippage, regardless of whether the leverage cap is 20x, 40x, or 100x.
- Fixed-leverage stress tests deploy the full account-level notional. They use a simplified liquidation-distance proxy of `1/leverage - 0.50%`; it is not Binance's symbol-, tier-, margin-mode-, or account-specific liquidation calculation.
- Survival probabilities resample complete trading sessions. They are conditional on this short, selected 2024–2025 history and are not real probabilities of future survival.

## Material limitations

- The Nasdaq CSV has unverified venue/contract identity and cannot be treated as executable Binance, CME NQ, or MNQ data.
- Binance fees vary by product, maker/taker status, VIP tier, discounts, and realized slippage. The configured cost is deliberately a scenario, not the user's live fee schedule.
- Historical bars assume stop fills at the stop unless the liquidation proxy is closer. Real gaps, latency, mark-price liquidation, spread widening, rejected orders, and partial fills can make outcomes worse.
- The grid creates substantial multiple-testing risk. The quarterly walk-forward is more relevant than the best full-sample cell, but also has little history.
- A stop-loss order cannot guarantee its intended loss during discontinuous markets. High leverage therefore cannot be made safe merely by placing a stop.
