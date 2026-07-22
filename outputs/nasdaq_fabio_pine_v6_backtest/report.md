# Fabio Pine v6 scalper: causal one-minute test

## Result

The supplied Pine script was translated literally at its default inputs. Signals are calculated on confirmed one-minute bars, market entries fill at the next bar's open, and exits use TradingView's historical OHLC path assumption. The causality audit status is **PASS**.

| variant | trades | win_rate | average_net_r | profit_factor | cumulative_net_return | annualized_net_return | maximum_drawdown | average_effective_leverage | average_risk_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| script_zero_cost | 1769 | 0.5721 | 0.0302 | 1.0925 | 0.1053 | 0.0534 | -0.0428 | 1.0000 | 0.0016 |
| script_realistic_cost | 1769 | 0.5721 | -0.0588 | 0.9371 | -0.0739 | -0.0391 | -0.1087 | 1.0000 | 0.0016 |
| intended_1pct_risk_capped_10x | 1769 | 0.5721 | -0.0588 | 0.8941 | -0.5725 | -0.3570 | -0.5991 | 7.4480 | 0.0091 |

## 2025 holdout

| variant | trades | win_rate | average_net_r | profit_factor | cumulative_net_return | annualized_net_return | maximum_drawdown | average_effective_leverage | average_risk_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| script_zero_cost | 868 | 0.5818 | 0.0457 | 1.1667 | 0.0967 | 0.1052 | -0.0307 | 1.0000 | 0.0017 |
| script_realistic_cost | 868 | 0.5818 | -0.0429 | 1.0117 | 0.0055 | 0.0060 | -0.0573 | 1.0000 | 0.0017 |
| intended_1pct_risk_capped_10x | 868 | 0.5818 | -0.0429 | 0.9327 | -0.2355 | -0.2525 | -0.3829 | 7.2457 | 0.0091 |

## Realistic-cost attribution

| setup_scope | trades | win_rate | average_net_r | profit_factor | cumulative_net_return |
| --- | --- | --- | --- | --- | --- |
| all | 1769 | 0.5721 | -0.0588 | 0.9371 | -0.0739 |
| triple_a | 0 | nan | nan | nan | 0.0000 |
| orb | 1656 | 0.5743 | -0.0560 | 0.9393 | -0.0683 |
| value_area | 113 | 0.5398 | -0.1006 | 0.8920 | -0.0060 |

## Cost sensitivity

| one_way_cost_bps | profit_factor | cumulative_net_return | maximum_drawdown |
| --- | --- | --- | --- |
| 0.0000 | 1.0925 | 0.1053 | -0.0428 |
| 0.1000 | 1.0598 | 0.0669 | -0.0515 |
| 0.2000 | 1.0279 | 0.0298 | -0.0603 |
| 0.2500 | 1.0122 | 0.0117 | -0.0668 |
| 0.3000 | 0.9968 | -0.0060 | -0.0753 |
| 0.4000 | 0.9666 | -0.0406 | -0.0921 |
| 0.5000 | 0.9371 | -0.0739 | -0.1087 |
| 0.7500 | 0.8666 | -0.1523 | -0.1597 |
| 1.0000 | 0.8003 | -0.2241 | -0.2281 |

## Exit mechanics

| exit_reason | trades |
| --- | --- |
| trailing_stop | 978 |
| static_stop | 757 |
| target | 34 |

## Material script findings

- `riskPercent` is an unused input. With no `qty` in `strategy.entry`, the declaration deploys 100% of available equity, not 1% risk. The risk-sized row is a separate diagnostic and is not the supplied strategy.
- The 30-minute ORB uses `sessionBars <= 30`, so it contains 31 one-minute bars and cannot first break out until the next bar.
- Built-in `trail_points` activates 1.5 signal-bar ATR from the actual entry, then follows at 0.5 ATR. Its historical result depends on TradingView's inferred intrabar path.
- No commission or slippage is declared. `script_zero_cost` matches that omission; `script_realistic_cost` adds 0.50 bps per side.
- The default VWAP anchor is feed-dependent. This translation resets on each New York calendar date because the CSV has no TradingView symbol/session metadata.

## Research limits

- Source identity is **unverified; price grid is inconsistent with CME NQ**; 94.1% of closes are off the CME NQ quarter-point grid.
- Candle volume cannot reproduce true bid/ask order flow or footprint absorption.
- One-minute OHLC cannot verify the tick path. The test intentionally uses the Pine broker emulator's documented default path rather than choosing favorable stop/target ordering.
- Raw dual-direction signal bars: 0. Open positions at the end: 0.

This is suitable for research comparison, not live deployment.
