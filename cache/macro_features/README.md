# Macro Feature Store

Generated at: 2026-05-09T08:59:33.451330+00:00

Each feature is stored as its own CSV under `series/`, with a matching JSON summary under `summaries/`.
Freshness checks are written to `series_health.csv`.

| feature | source | history_start | history_end | frequency | coverage_ratio | stale |
| --- | --- | --- | --- | --- | ---: | --- |
| dxy_close | Yahoo Finance chart API | 1999-01-01 | 2026-04-09 | daily | 0.944 | stale |
| gold_usd_per_oz | Yahoo Finance chart API | 2000-08-30 | 2026-04-09 | daily | 0.880 | stale |
| wilshire_total_market_index | Yahoo Finance chart API | 1999-01-04 | 2026-04-08 | daily | 0.938 | stale |
| shiller_cape_ratio | Multpl | 1999-01-01 | 2026-04-08 | monthly | 0.045 | fresh |
| us_2y_yield | FRED | 1999-01-04 | 2026-04-07 | daily | 0.934 | stale |
| us_10y_yield | FRED | 1999-01-04 | 2026-04-07 | daily | 0.934 | stale |
| us_30y_yield | FRED | 1999-01-04 | 2026-04-07 | daily | 0.934 | stale |
| wti_usd_per_bbl | FRED | 1999-01-04 | 2026-04-06 | daily | 0.936 | stale |
| us_nominal_gdp_saar_bil | FRED | 1999-01-01 | 2025-10-01 | quarterly | 0.015 | stale |
| cpi_all_items_index | FRED | 1999-01-01 | 2026-02-01 | monthly | 0.045 | stale |
| cpi_mom_pct | FRED | 1999-01-01 | 2026-02-01 | monthly | 0.044 | stale |
| cpi_yoy_pct | FRED | 1999-01-01 | 2026-02-01 | monthly | 0.045 | stale |
| unemployment_rate_pct | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.045 | stale |
| market_cap_to_gdp_pct | FRED | 1999-01-01 | 2020-01-01 | annual_or_irregular | 0.003 | stale |
| xlu_close | unknown | 1999-01-04 | 2026-04-09 | daily | 0.939 | stale |
| xly_close | unknown | 1999-01-04 | 2026-04-09 | daily | 0.939 | stale |
| eem_close | unknown | 2003-04-14 | 2026-04-09 | daily | 0.792 | stale |
| efa_close | unknown | 2001-08-27 | 2026-04-09 | daily | 0.848 | stale |
| copper_usd_per_lb | unknown | 2000-08-30 | 2026-04-09 | daily | 0.881 | stale |
| vix3m_level | Yahoo Finance chart API / derived pre-launch backfill | 1999-01-01 | 2026-04-09 | daily | 1.000 | stale |
| high_yield_spread | FRED | 1999-03-10 | 2026-04-06 | daily | 0.969 | stale |
| CPIENGSL | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.045 | stale |
| CPILFESL | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.045 | stale |
| CUSR0000SAH1 | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.045 | stale |
| INDPRO | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.045 | stale |
| IPMAN | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.045 | stale |
| NFCI | FRED | 1999-03-12 | 2026-03-27 | weekly | 0.193 | stale |
| T10Y3M | FRED | 1999-03-10 | 2026-04-07 | daily | 0.928 | stale |
| spot_vix | FRED | 1999-01-01 | 2026-04-06 | daily | 1.000 | stale |
| VXOCLS | FRED | 1999-01-04 | 2021-09-23 | daily | 0.783 | stale |
| yield_curve_10y_2y | derived | 1999-01-04 | 2026-04-07 | daily | 0.934 | stale |
| core_cpi_yoy_pct | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.045 | stale |
| energy_cpi_yoy_pct | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.045 | stale |
| shelter_cpi_yoy_pct | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.045 | stale |
| industrial_production_yoy_pct | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.045 | stale |
| manufacturing_output_yoy_pct | FRED | 1999-01-01 | 2026-03-01 | monthly | 0.045 | stale |
| market_cap_to_gdp_proxy_pct | derived | 1999-01-01 | 2026-04-09 | daily | 1.000 | stale |
| market_cap_to_gdp_pct_patched | derived_plus_official | 1999-01-01 | 2026-04-09 | daily | 1.000 | stale |
