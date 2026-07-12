# Results Report

Mode: panel

## Key metrics

- ROC AUC: 0.5276524589359288
- Holdout ROC AUC: 0.5747976287568015
- Holdout total return: 0.0
- Holdout Sharpe: None
- Holdout max drawdown: 0.0
- Holdout trade count: 0

## Key observations

- Pooled panel holdout ROC AUC is 0.575, which is above chance but still moderate.
- The holdout only fired 0 trades across 12 symbols, so the current threshold behaves like a selective filter, not a broad forecaster.
- Headline holdout return is 0.0%, but that is under a simplified equal-weight active-signal aggregation and still needs portfolio-level risk caps before it is deployable.
- In the holdout threshold sweep, the best ex-post Sharpe occurred near threshold 0.50, which is a clue for calibration review rather than a parameter to hard-fit immediately.
- The bounded momentum oscillator research uses 1,292 holdout rows; its return correlation is 0.074 and its model-probability correlation is 0.100.

## Charts

![Dashboard](dashboard.png)

![Holdout threshold sweep](threshold_sweep.png)

![Momentum oscillator](momentum_oscillator.png)

![Momentum oscillator research](momentum_oscillator_research.png)

## Momentum oscillator research

The oscillator is an RSI-style bounded momentum feature mapped to `-1..1`, where negative values mean downside momentum, zero is neutral, and positive values mean upside momentum.

Sample: holdout, rows: 1,292.

| Oscillator band | Rows | Avg osc | Hit rate | Avg forward return | Trade rate | Avg probability |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Strong downside | 4 | -0.67 | 0.0% | -4.66% | 0.0% | 0.538 |
| Downside | 130 | -0.31 | 43.8% | -0.88% | 0.0% | 0.489 |
| Neutral | 648 | 0.01 | 53.9% | 1.09% | 0.0% | 0.484 |
| Upside | 509 | 0.36 | 63.1% | 1.32% | 0.0% | 0.493 |
| Strong upside | 1 | 0.62 | 0.0% | -5.29% | 0.0% | 0.512 |

- Return correlation: 0.074
- Model-probability correlation: 0.100

