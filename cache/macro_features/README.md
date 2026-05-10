# Macro Feature Store

Generated at: 2026-05-10T14:56:30.365826+00:00

Each feature is stored as its own CSV under `series/`, with a matching JSON summary under `summaries/`.
Freshness checks are written to `series_health.csv`.

| feature | source | history_start | history_end | frequency | coverage_ratio | stale |
| --- | --- | --- | --- | --- | ---: | --- |
| dxy_close | Yahoo Finance chart API | 1999-01-01 | 2026-04-09 | daily | 0.690 | stale |
| gold_usd_per_oz | Yahoo Finance chart API | 2000-08-30 | 2026-04-09 | daily | 0.643 | stale |
| wilshire_total_market_index | Yahoo Finance chart API | 1999-01-04 | 2026-04-08 | daily | 0.685 | stale |
| shiller_cape_ratio | Multpl | 1999-01-01 | 2026-04-08 | monthly | 0.033 | fresh |
| us_2y_yield | FRED | 1999-01-04 | 2026-04-07 | daily | 0.683 | stale |
| us_10y_yield | FRED | 1999-01-04 | 2026-04-07 | daily | 0.683 | stale |
| us_30y_yield | FRED | 1999-01-04 | 2026-04-07 | daily | 0.683 | stale |
| wti_usd_per_bbl | FRED | 1999-01-04 | 2026-04-06 | daily | 0.684 | stale |
| us_nominal_gdp_saar_bil | FRED | 1999-01-01 | 2025-10-01 | quarterly | 0.011 | stale |
| cpi_all_items_index | FRED | 1999-01-01 | 2026-02-01 | monthly | 0.033 | stale |
| cpi_mom_pct | FRED | 1999-01-01 | 2026-02-01 | monthly | 0.032 | stale |
| cpi_yoy_pct | FRED | 1999-01-01 | 2026-02-01 | monthly | 0.033 | stale |
| unemployment_rate_pct | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.033 | stale |
| market_cap_to_gdp_pct | FRED | 1999-01-01 | 2020-01-01 | annual_or_irregular | 0.002 | stale |
| xlu_close | unknown | 1999-01-04 | 2026-04-09 | daily | 0.687 | stale |
| xly_close | unknown | 1999-01-04 | 2026-04-09 | daily | 0.687 | stale |
| eem_close | unknown | 2003-04-14 | 2026-04-09 | daily | 0.579 | stale |
| efa_close | unknown | 2001-08-27 | 2026-04-09 | daily | 0.620 | stale |
| copper_usd_per_lb | unknown | 2000-08-30 | 2026-04-09 | daily | 0.644 | stale |
| vix3m_level | Yahoo Finance chart API / derived pre-launch backfill | 1999-01-01 | 2026-04-09 | daily | 0.997 | stale |
| high_yield_spread | FRED | 1999-03-10 | 2026-04-06 | daily | 0.708 | stale |
| CPIENGSL | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.033 | stale |
| CPILFESL | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.033 | stale |
| CUSR0000SAH1 | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.033 | stale |
| INDPRO | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.033 | stale |
| IPMAN | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.033 | stale |
| NFCI | FRED | 1999-03-12 | 2026-03-27 | weekly | 0.141 | stale |
| T10Y3M | FRED | 1999-03-10 | 2026-04-07 | daily | 0.678 | stale |
| UMCSENT | unknown | 1999-01-01 | 2026-03-01 | monthly | 0.033 | stale |
| consumer_sentiment_release_level | ALFRED | 1999-01-29 | 2026-03-27 | monthly | 0.010 | fresh |
| USEPUINDXD | unknown | 1999-01-01 | 2026-05-07 | daily | 1.000 | fresh |
| spot_vix | FRED | 1999-01-01 | 2026-04-06 | daily | 0.997 | stale |
| VXOCLS | FRED | 1999-01-04 | 2021-09-23 | daily | 0.573 | stale |
| yield_curve_10y_2y | derived | 1999-01-04 | 2026-04-07 | daily | 0.683 | stale |
| core_cpi_yoy_pct | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.033 | stale |
| energy_cpi_yoy_pct | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.033 | stale |
| shelter_cpi_yoy_pct | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.033 | stale |
| industrial_production_yoy_pct | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.033 | stale |
| manufacturing_output_yoy_pct | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.033 | stale |
| epu_level | FRED | 1999-01-01 | 2026-05-07 | daily | 1.000 | fresh |
| epu_5d_change | derived_from_fred | 1999-01-01 | 2026-05-07 | daily | 1.000 | fresh |
| epu_20d_change | derived_from_fred | 1999-01-01 | 2026-05-07 | daily | 1.000 | fresh |
| epu_zscore_252d | derived_from_fred | 1999-01-01 | 2026-05-07 | daily | 1.000 | fresh |
| epu_spike_flag | derived_from_fred | 1999-01-01 | 2026-05-07 | daily | 1.000 | fresh |
| consumer_sentiment_level | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.033 | stale |
| market_cap_to_gdp_proxy_pct | derived | 1999-01-01 | 2026-05-07 | daily | 1.000 | fresh |
| market_cap_to_gdp_pct_patched | derived_plus_official | 1999-01-01 | 2026-05-07 | daily | 1.000 | fresh |
