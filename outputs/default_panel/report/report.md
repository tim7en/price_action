# Results Report

Mode: panel

## Key metrics

- ROC AUC: 0.5438683832406997
- Holdout ROC AUC: 0.5627383491224965
- Holdout total return: 0.31122882984550015
- Holdout Sharpe: 1.2207797327615661
- Holdout max drawdown: -0.002123013469624291
- Holdout trade count: 19

## Key observations

- Pooled panel holdout ROC AUC is 0.563, which is above chance but still moderate.
- The holdout only fired 19 trades across 12 symbols, so the current threshold behaves like a selective filter, not a broad forecaster.
- Headline holdout return is 31.1%, but that is under a simplified equal-weight active-signal aggregation and still needs portfolio-level risk caps before it is deployable.
- In the holdout threshold sweep, the best ex-post Sharpe occurred near threshold 0.54, which is a clue for calibration review rather than a parameter to hard-fit immediately.
