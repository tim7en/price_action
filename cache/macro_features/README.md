# Macro Feature Store

Generated at: 2026-07-12T19:43:56.669475+00:00

Each feature is stored as its own CSV under `series/`, with a matching JSON summary under `summaries/`.
Freshness checks are written to `series_health.csv`.

| feature | source | history_start | history_end | frequency | coverage_ratio | stale |
| --- | --- | --- | --- | --- | ---: | --- |
| dxy_close | Yahoo Finance chart API | 1999-01-01 | 2026-07-10 | daily | 0.692 | fresh |
| gold_usd_per_oz | Yahoo Finance chart API | 2000-08-30 | 2026-07-10 | daily | 0.645 | fresh |
| wilshire_total_market_index | Yahoo Finance chart API | 1999-01-04 | 2026-07-10 | daily | 0.681 | fresh |
| shiller_cape_ratio | Multpl | 1999-01-01 | 2026-07-10 | monthly | 0.033 | fresh |
| us_2y_yield | FRED | 1999-01-04 | 2026-07-09 | daily | 0.685 | fresh |
| us_10y_yield | FRED | 1999-01-04 | 2026-07-09 | daily | 0.685 | fresh |
| us_30y_yield | FRED | 1999-01-04 | 2026-07-09 | daily | 0.685 | fresh |
| wti_usd_per_bbl | FRED | 1999-01-04 | 2026-07-06 | daily | 0.686 | fresh |
| us_nominal_gdp_saar_bil | FRED | 1999-01-01 | 2026-01-01 | quarterly | 0.011 | stale |
| cpi_all_items_index | FRED | 1999-01-01 | 2026-05-01 | monthly | 0.033 | stale |
| cpi_mom_pct | FRED | 1999-01-01 | 2026-05-01 | monthly | 0.033 | stale |
| cpi_yoy_pct | FRED | 1999-01-01 | 2026-05-01 | monthly | 0.033 | stale |
| unemployment_rate_pct | FRED | 1999-01-01 | 2026-06-01 | monthly | 0.033 | fresh |
| market_cap_to_gdp_pct | FRED | 1999-01-01 | 2020-01-01 | annual_or_irregular | 0.002 | stale |
| xlu_close | unknown | 1999-01-04 | 2026-07-10 | daily | 0.688 | fresh |
| xly_close | unknown | 1999-01-04 | 2026-07-10 | daily | 0.688 | fresh |
| eem_close | unknown | 2003-04-14 | 2026-07-10 | daily | 0.582 | fresh |
| efa_close | unknown | 2001-08-27 | 2026-07-10 | daily | 0.622 | fresh |
| copper_usd_per_lb | unknown | 2000-08-30 | 2026-07-10 | daily | 0.646 | fresh |
| vix3m_level | Yahoo Finance chart API / derived pre-launch backfill | 2006-07-17 | 2026-07-10 | daily | 0.503 | fresh |
| high_yield_spread | FRED | 1999-03-10 | 2026-07-09 | daily | 0.710 | fresh |
| CPIENGSL | FRED | 1999-01-01 | 2026-05-01 | monthly | 0.033 | stale |
| CPILFESL | FRED | 1999-01-01 | 2026-05-01 | monthly | 0.033 | stale |
| CUSR0000SAH1 | FRED | 1999-01-01 | 2026-05-01 | monthly | 0.033 | stale |
| DFF | unknown | 1999-01-01 | 2026-07-09 | daily | 1.000 | fresh |
| FEDTARMD | unknown | 2026-01-01 | 2028-01-01 | annual_or_irregular | 0.000 | fresh |
| FEDTARMDLR | unknown | 2012-01-25 | 2026-06-17 | quarterly | 0.006 | fresh |
| ICSA | unknown | 1999-01-02 | 2026-07-04 | weekly | 0.143 | fresh |
| INDPRO | FRED | 1999-01-01 | 2026-05-01 | monthly | 0.033 | stale |
| IPMAN | FRED | 1999-01-01 | 2026-05-01 | monthly | 0.033 | stale |
| MICH | unknown | 1999-01-01 | 2026-05-01 | monthly | 0.033 | stale |
| NFCI | FRED | 1999-01-01 | 2026-07-03 | weekly | 0.143 | fresh |
| PERMIT | unknown | 1999-01-01 | 2026-05-01 | monthly | 0.033 | stale |
| T10Y3M | FRED | 1999-01-04 | 2026-07-10 | daily | 0.685 | fresh |
| T10YIE | unknown | 2003-01-02 | 2026-07-10 | daily | 0.585 | fresh |
| T5YIFR | unknown | 2003-01-02 | 2026-07-10 | daily | 0.585 | fresh |
| UMCSENT | unknown | 1999-01-01 | 2026-05-01 | monthly | 0.033 | stale |
| consumer_sentiment_release_level | ALFRED | 1999-01-29 | 2026-03-27 | monthly | 0.010 | stale |
| USEPUINDXD | unknown | 1999-01-01 | 2026-07-09 | daily | 1.000 | fresh |
| spot_vix | FRED | 1999-01-04 | 2026-07-09 | daily | 0.691 | fresh |
| VXOCLS | FRED | 1999-01-04 | 2021-09-23 | daily | 0.569 | stale |
| yield_curve_10y_2y | derived | 1999-01-04 | 2026-07-09 | daily | 0.685 | fresh |
| core_cpi_yoy_pct | FRED | 2000-01-01 | 2026-05-01 | monthly | 0.031 | stale |
| energy_cpi_yoy_pct | FRED | 2000-01-01 | 2026-05-01 | monthly | 0.031 | stale |
| shelter_cpi_yoy_pct | FRED | 2000-01-01 | 2026-05-01 | monthly | 0.031 | stale |
| industrial_production_yoy_pct | FRED | 2000-01-01 | 2026-05-01 | monthly | 0.032 | stale |
| manufacturing_output_yoy_pct | FRED | 2000-01-01 | 2026-05-01 | monthly | 0.032 | stale |
| epu_level | FRED | 1999-01-01 | 2026-07-09 | daily | 1.000 | fresh |
| epu_5d_change | derived_from_fred | 1999-01-06 | 2026-07-09 | daily | 0.999 | fresh |
| epu_20d_change | derived_from_fred | 1999-01-21 | 2026-07-09 | daily | 0.998 | fresh |
| epu_zscore_252d | derived_from_fred | 1999-09-09 | 2026-07-09 | daily | 0.975 | fresh |
| epu_spike_flag | derived_from_fred | 1999-09-09 | 2026-07-09 | daily | 0.975 | fresh |
| consumer_sentiment_level | FRED | 1999-01-01 | 2026-05-01 | monthly | 0.033 | stale |
| market_cap_to_gdp_proxy_pct | derived | 1999-01-01 | 2028-01-01 | daily | 1.000 | fresh |
| market_cap_to_gdp_pct_patched | derived_plus_official | 1999-01-01 | 2028-01-01 | daily | 1.000 | fresh |
