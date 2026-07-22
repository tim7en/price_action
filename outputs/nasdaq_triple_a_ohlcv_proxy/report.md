# NASDAQ Triple-A OHLCV proxy

## Decision

This test approximates the supplied Triple-A workflow but does **not** reconstruct genuine order-flow absorption. At 0.50 bps per side, the staged 0.25%-risk proxy executes 323 trades and returns **-13.76%** with **-15.40%** maximum drawdown and PF **0.602**.

Development 2024 returns -4.32% on 168 trades; unchanged 2025 validation returns -9.87% on 155 trades. A positive development result without positive validation is a rejection.

Keeping only the 0.10% starter and disabling the add-on still loses -8.29%, but it is less damaging than scaling the broad proxy. Confirmation-based adding does not rescue a weak absorption approximation.

The bounded 2024-only search selected `t180_rr3_volume_long`: long-only, above-development-median volume, at least 3R structural room, and the full 30-to-180-minute window. It earned PF 1.202 and 1.33% in development, then fell to PF 0.807 and -1.21% in validation. Robust candidates with PF above one in both periods: **0**. The proxy is therefore **rejected**, not promoted.

## What was approximated

1. Prior completed-session 10/30-day trend defines direction.
2. Signals begin only after the first 30 RTH minutes and end after minute 180.
3. A swing profile is anchored causally to the overnight/opening extreme in the trend direction.
4. The absorption proxy requires above-threshold volume, a fresh adverse excursion, and a close recovering away from the extreme at VAL/VAH.
5. Entry is a stop beyond the recovery bar during the next 3 bars; a stop breach cancels the order first.
6. Structural room to the opposite value boundary must be at least 1.50R.
7. Staged management starts at 0.10% risk, halves the stop distance after confirmation, adds only within a 0.25% total-risk cap, takes one-third at POC, then trails toward the opposite value boundary.

## Performance

| variant | scope | side | trades | sessions | win_rate | profit_factor | average_net_r | cumulative_return | maximum_drawdown | average_leverage | add_rate | partial_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| static_0.25pct | all | both | 311 | 179 | 0.1768 | 0.6868 | -0.2895 | -0.2047 | -0.2187 | 3.1954 | 0.0000 | 0.0000 |
| static_0.25pct | development_2024 | both | 165 | 94 | 0.1879 | 0.7835 | -0.1961 | -0.0799 | -0.0961 | 3.1324 | 0.0000 | 0.0000 |
| static_0.25pct | validation_2025 | both | 146 | 85 | 0.1644 | 0.5819 | -0.3950 | -0.1356 | -0.1422 | 3.2666 | 0.0000 | 0.0000 |
| staged_0.25pct | all | both | 323 | 179 | 0.2477 | 0.6025 | -0.1821 | -0.1376 | -0.1540 | 1.8738 | 0.3498 | 0.2291 |
| staged_0.25pct | development_2024 | both | 168 | 94 | 0.2798 | 0.7570 | -0.1037 | -0.0432 | -0.0614 | 1.7836 | 0.3333 | 0.2560 |
| staged_0.25pct | validation_2025 | both | 155 | 85 | 0.2129 | 0.4573 | -0.2670 | -0.0987 | -0.0987 | 1.9716 | 0.3677 | 0.2000 |
| starter_only_0.10pct | all | both | 323 | 179 | 0.2508 | 0.6389 | -0.2667 | -0.0829 | -0.0901 | 1.2875 | 0.0000 | 0.2291 |
| starter_only_0.10pct | development_2024 | both | 168 | 94 | 0.2857 | 0.7805 | -0.1535 | -0.0257 | -0.0333 | 1.2583 | 0.0000 | 0.2560 |
| starter_only_0.10pct | validation_2025 | both | 155 | 85 | 0.2129 | 0.5014 | -0.3894 | -0.0587 | -0.0587 | 1.3192 | 0.0000 | 0.2000 |
| development_selected_0.25pct | all | both | 118 | 85 | 0.2373 | 1.0122 | 0.0053 | 0.0010 | -0.0434 | 1.7114 | 0.3814 | 0.1780 |
| development_selected_0.25pct | development_2024 | both | 64 | 47 | 0.2500 | 1.2021 | 0.0850 | 0.0133 | -0.0317 | 1.6670 | 0.3750 | 0.1719 |
| development_selected_0.25pct | validation_2025 | both | 54 | 38 | 0.2222 | 0.8066 | -0.0890 | -0.0121 | -0.0182 | 1.7641 | 0.3889 | 0.1852 |
| staged_2pct | all | both | 323 | 179 | 0.2477 | 0.5968 | -0.1647 | -0.6714 | -0.7028 | 12.6911 | 0.3282 | 0.2291 |
| staged_2pct | development_2024 | both | 168 | 94 | 0.2798 | 0.7351 | -0.1028 | -0.3126 | -0.3782 | 12.5759 | 0.3274 | 0.2560 |
| staged_2pct | validation_2025 | both | 155 | 85 | 0.2129 | 0.4620 | -0.2319 | -0.5220 | -0.5220 | 12.8159 | 0.3290 | 0.2000 |

## Direction attribution

| variant | scope | side | trades | sessions | win_rate | profit_factor | average_net_r | cumulative_return | maximum_drawdown | average_leverage | add_rate | partial_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| staged_0.25pct | development_2024 | both | 168 | 94 | 0.2798 | 0.7570 | -0.1037 | -0.0432 | -0.0614 | 1.7836 | 0.3333 | 0.2560 |
| staged_0.25pct | development_2024 | long | 145 | 79 | 0.2828 | 0.7589 | -0.1021 | -0.0368 | -0.0552 | 1.8016 | 0.3379 | 0.2552 |
| staged_0.25pct | development_2024 | short | 23 | 15 | 0.2609 | 0.7455 | -0.1140 | -0.0066 | -0.0191 | 1.6701 | 0.3043 | 0.2609 |
| staged_0.25pct | validation_2025 | both | 155 | 85 | 0.2129 | 0.4573 | -0.2670 | -0.0987 | -0.0987 | 1.9716 | 0.3677 | 0.2000 |
| staged_0.25pct | validation_2025 | long | 130 | 71 | 0.2231 | 0.5200 | -0.2295 | -0.0722 | -0.0722 | 2.1137 | 0.3692 | 0.2077 |
| staged_0.25pct | validation_2025 | short | 25 | 14 | 0.1600 | 0.1812 | -0.4623 | -0.0285 | -0.0285 | 1.2331 | 0.3600 | 0.1600 |

## Signal funnel

| stage | count |
| --- | --- |
| sessions | 485 |
| sessions_with_daily_trend | 384 |
| effort_recovery_bars | 1881 |
| profile_location_bars | 585 |
| structural_room_candidates | 526 |
| stop_entries_activated | 388 |
| staged_trades_executed | 323 |

## Staged-strategy cost sensitivity

| one_way_cost_bps | trades | sessions | win_rate | profit_factor | average_net_r | cumulative_return | maximum_drawdown | average_leverage | add_rate | partial_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0000 | 323 | 179 | 0.2539 | 0.7365 | -0.1071 | -0.0838 | -0.1060 | 1.8738 | 0.3498 | 0.2291 |
| 0.2500 | 323 | 179 | 0.2539 | 0.6655 | -0.1446 | -0.1111 | -0.1303 | 1.8738 | 0.3498 | 0.2291 |
| 0.5000 | 323 | 179 | 0.2477 | 0.6025 | -0.1821 | -0.1376 | -0.1540 | 1.8738 | 0.3498 | 0.2291 |
| 1.0000 | 323 | 179 | 0.2105 | 0.4975 | -0.2570 | -0.1883 | -0.1995 | 1.8738 | 0.3498 | 0.2291 |
| 2.0000 | 323 | 179 | 0.1610 | 0.3513 | -0.4069 | -0.2809 | -0.2834 | 1.8738 | 0.3498 | 0.2291 |
| 5.0000 | 323 | 179 | 0.1176 | 0.1390 | -0.8566 | -0.5002 | -0.5002 | 1.8738 | 0.3498 | 0.2291 |

## Top 2024-ranked rule candidates and unchanged validation

| candidate | development_trades | development_profit_factor | development_average_net_r | development_return | validation_trades | validation_profit_factor | validation_average_net_r | validation_return | all_return |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| t180_rr3_volume_long | 64 | 1.2021 | 0.0850 | 0.0133 | 54 | 0.8066 | -0.0890 | -0.0121 | 0.0010 |
| t180_rr3_volume_both | 71 | 1.0900 | 0.0383 | 0.0065 | 58 | 0.8177 | -0.0844 | -0.0124 | -0.0060 |
| t120_rr3_volume_long | 28 | 1.0275 | 0.0132 | 0.0007 | 29 | 0.5868 | -0.1948 | -0.0141 | -0.0134 |
| t120_rr3_volume_both | 30 | 1.0201 | 0.0093 | 0.0005 | 29 | 0.5868 | -0.1948 | -0.0141 | -0.0136 |
| t180_rr1.5_volume_long | 85 | 1.0018 | 0.0007 | -0.0002 | 64 | 0.9229 | -0.0324 | -0.0054 | -0.0056 |
| t180_rr2_volume_long | 76 | 0.9764 | -0.0103 | -0.0023 | 62 | 0.9469 | -0.0225 | -0.0037 | -0.0060 |
| t180_rr1.5_volume_both | 93 | 0.9288 | -0.0286 | -0.0070 | 69 | 0.9118 | -0.0375 | -0.0067 | -0.0136 |
| t180_rr2_volume_both | 83 | 0.9041 | -0.0421 | -0.0091 | 67 | 0.9336 | -0.0284 | -0.0050 | -0.0140 |
| t120_rr1.5_volume_long | 44 | 0.8555 | -0.0592 | -0.0067 | 36 | 0.7040 | -0.1271 | -0.0115 | -0.0181 |
| t120_rr1.5_volume_both | 47 | 0.8535 | -0.0575 | -0.0069 | 37 | 0.6852 | -0.1351 | -0.0125 | -0.0194 |

## Frozen 2024 distribution thresholds

```json
{
  "volume_strength_minimum": 0.8743124666382058,
  "excursion_atr_minimum": 0.4566070459035039,
  "fit_start_utc": "2024-01-02T15:00:00+00:00",
  "fit_end_utc": "2024-12-31T17:29:00+00:00",
  "fit_bars": 37779
}
```

## Material limits

- High-volume failed excursion is only an OHLCV proxy for absorption. It cannot show bid/ask delta, passive iceberg orders, queue depletion, large-trade collisions, or millisecond timing.
- Volume is distributed uniformly across each candle range to estimate the profile. It is not exchange volume-at-price.
- The source instrument and venue are unverified; 94.1% of closes do not conform to CME NQ's quarter-point grid.
- Same-bar ambiguity is conservative: invalidation/stop is processed before entry/target. Management changes apply only to subsequent bars.
- The staged add is risk-capped, not a claim that Fabio uses this exact formula.
- The aggressive 2% path is included only because it was requested previously; it is eight times the 0.25% research risk and is not the primary result.

Methodology audit: **PASS**. Live deployment remains blocked without identified tick-level NQ data and a fresh holdout.
