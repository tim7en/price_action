# Hierarchical research data contract

The macro, sector, and company studies now share one monthly signal clock and explicit forward targets.

## Coverage

| layer   |   rows |   entities | start               | end                 |   target_rows |   predictive_features |   strict_pit_rows |
|:--------|-------:|-----------:|:--------------------|:--------------------|--------------:|----------------------:|------------------:|
| macro   |    310 |          1 | 1999-12-31 00:00:00 | 2025-09-30 00:00:00 |           307 |                    50 |               nan |
| sector  |   3410 |         11 | 1999-12-31 00:00:00 | 2025-09-30 00:00:00 |          3333 |                    82 |               nan |
| company |  31269 |        181 | 2010-02-28 00:00:00 | 2025-11-30 00:00:00 |         27456 |                   115 |              7364 |

## Target definitions

- Macro: next three-month Dalio quadrant and regime-change indicator.
- Sector: forward six-month sector return minus the broad sector basket.
- Company: forward 126-trading-day stock return minus its parent sector ETF return.
- Quality-engine peer residual is retained as a secondary target, not substituted for parent-sector alpha.

## Validation

- Audit: 11 PASS, 3 WARN, 0 FAIL.
- Expanding annual walk-forward folds require every training label to mature before the test year.
- The final holdout starts 2025-01-01.

## Material limitations

- Strict point-in-time N-PORT top-10 membership starts in November 2019. Earlier company rows use the static research universe.
- The dedicated semiconductor book is a static industry specification and must be consolidated with XLK exposures during sizing.
- Publication lags are applied, but full ALFRED vintages are not yet present for every macro series.
- GMM regime labels are descriptive metadata and are forbidden from predictive features because the current fit uses full history.

## Next phase

Fit regularized macro-transition, sector-excess-return, and company-residual baselines; then add tree/boosting challengers, calibrated trend-survival confidence, and constrained portfolio sizing.
