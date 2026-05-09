from __future__ import annotations

MODEL_MACRO_CONTEXT_COLUMNS: tuple[str, ...] = (
    "dxy_close",
    "gold_usd_per_oz",
    "wti_usd_per_bbl",
    "us_2y_yield",
    "us_10y_yield",
    "us_30y_yield",
    "yield_curve_10y_2y",
    "high_yield_spread",
    "spot_vix",
    "vix3m_level",
    "shiller_cape_ratio",
    "market_cap_to_gdp_proxy_pct",
    "market_cap_to_gdp_pct_patched",
    "cpi_yoy_pct",
    "core_cpi_yoy_pct",
    "energy_cpi_yoy_pct",
    "shelter_cpi_yoy_pct",
    "unemployment_rate_pct",
    "industrial_production_yoy_pct",
    "manufacturing_output_yoy_pct",
    "NFCI",
    "T10Y3M",
    "epu_level",
    "epu_5d_change",
    "epu_20d_change",
    "epu_zscore_252d",
    "epu_spike_flag",
    "consumer_sentiment_release_level",
)

MACRO_REPORT_GROUPS: tuple[dict[str, str | tuple[str, ...]], ...] = (
    {
        "slug": "inflation_breadth",
        "title": "Inflation Breadth And Labor",
        "summary": "Headline inflation is not enough. This group separates sticky inflation from commodity shocks and keeps labor slack in the same frame.",
        "series": (
            "cpi_yoy_pct",
            "core_cpi_yoy_pct",
            "energy_cpi_yoy_pct",
            "shelter_cpi_yoy_pct",
            "unemployment_rate_pct",
        ),
    },
    {
        "slug": "production_activity",
        "title": "Real Activity And Production",
        "summary": "Industrial and manufacturing output show whether growth is broadening, slowing, or rolling over beneath the market narrative.",
        "series": (
            "industrial_production_yoy_pct",
            "manufacturing_output_yoy_pct",
        ),
    },
    {
        "slug": "rates_curve",
        "title": "Rates And The Curve",
        "summary": "Policy, term premia, and curve shape define the price of money, but the speed of rate change often matters more than the static level.",
        "series": (
            "us_2y_yield",
            "us_10y_yield",
            "us_30y_yield",
            "yield_curve_10y_2y",
            "T10Y3M",
        ),
    },
    {
        "slug": "credit_conditions",
        "title": "Credit And Conditions",
        "summary": "When financing tightens, spreads widen first and the real economy usually feels it later.",
        "series": (
            "high_yield_spread",
            "NFCI",
        ),
    },
    {
        "slug": "uncertainty_sentiment",
        "title": "Policy Uncertainty And Sentiment",
        "summary": "Policy uncertainty and household sentiment help distinguish noisy slowdowns from genuine stress. The active sentiment series is aligned to ALFRED revision dates so the model only sees readings after they were publicly available.",
        "series": (
            "epu_level",
            "epu_20d_change",
            "epu_zscore_252d",
            "consumer_sentiment_release_level",
        ),
    },
    {
        "slug": "volatility_risk",
        "title": "Volatility And Risk Appetite",
        "summary": "These are not just predictors. They are regime controls that should influence participation, sizing, stops, and strategy selection.",
        "series": (
            "spot_vix",
            "vix3m_level",
        ),
    },
    {
        "slug": "dollar_real_assets",
        "title": "Dollar And Real Assets",
        "summary": "The dollar and commodity complex help frame global liquidity, inflation pass-through, and growth sensitivity.",
        "series": (
            "dxy_close",
            "gold_usd_per_oz",
            "wti_usd_per_bbl",
        ),
    },
    {
        "slug": "valuation_backdrop",
        "title": "Valuation And Debt-Cycle Backdrop",
        "summary": "These are long-duration fragility gauges. They do not tell you the day of the turn, but they matter when rates, credit, and volatility start to bite.",
        "series": (
            "shiller_cape_ratio",
            "market_cap_to_gdp_proxy_pct",
            "market_cap_to_gdp_pct_patched",
        ),
    },
)

MACRO_SERIES_BRIEFS: dict[str, str] = {
    "dxy_close": "The dollar is the global funding barometer. Sharp rises often coincide with tighter liquidity and more fragile risk assets.",
    "gold_usd_per_oz": "Gold tends to strengthen when investors prefer scarce stores of value over cash-flow risk and policy credibility is being tested.",
    "wti_usd_per_bbl": "Oil is a growth and inflation transmission channel. Big moves reshape margins, consumer purchasing power, and inflation expectations.",
    "us_2y_yield": "The 2-year yield is the cleanest market read on the policy path over the next several meetings.",
    "us_10y_yield": "The 10-year yield anchors discount rates across the economy and usually reflects the market's growth-plus-inflation view.",
    "us_30y_yield": "The long bond shows how investors price inflation credibility and long-duration term risk.",
    "yield_curve_10y_2y": "A flatter or inverted 10s2s curve usually signals late-cycle policy tightness and weaker future growth expectations.",
    "high_yield_spread": "Credit spreads widen when balance-sheet stress rises and lenders demand more compensation for cyclical risk.",
    "spot_vix": "Spot VIX is the market's immediate fear gauge. Spikes usually mark forced de-risking and unstable positioning.",
    "vix3m_level": "Three-month implied volatility reflects medium-horizon hedging demand and helps separate brief panic from persistent uncertainty.",
    "shiller_cape_ratio": "Shiller CAPE is a long-cycle valuation gauge. It is slow, but it matters when leverage, rates, and sentiment are stretched together.",
    "market_cap_to_gdp_pct": "This is the slow-moving official valuation backdrop: financial asset prices versus the productive economy beneath them.",
    "market_cap_to_gdp_proxy_pct": "This daily proxy keeps the Buffett-indicator logic usable between annual official prints so valuation stress can be tracked in real time.",
    "market_cap_to_gdp_pct_patched": "The patched series extends the official valuation gauge into a usable daily proxy so the model can track the backdrop in real time.",
    "cpi_yoy_pct": "Inflation tells you whether nominal growth is being driven by real expansion or by rising prices that central banks may need to restrain.",
    "core_cpi_yoy_pct": "Core CPI strips out the most volatile food and energy swings so you can see whether underlying inflation is staying sticky.",
    "energy_cpi_yoy_pct": "Energy inflation captures the fastest shock channel from commodities and geopolitics into consumer prices and margins.",
    "shelter_cpi_yoy_pct": "Shelter inflation is slow and sticky. It is one of the cleanest checks on whether inflation pressure is really fading.",
    "unemployment_rate_pct": "Unemployment is the slack gauge. It tends to bottom late in the cycle and rise after tightening starts to bite.",
    "industrial_production_yoy_pct": "Industrial production captures the broad goods-producing side of the economy and is a cleaner real-growth check than pure narrative data.",
    "manufacturing_output_yoy_pct": "Manufacturing output is the cyclically sensitive production gauge that often turns with inventories, exports, and capex expectations.",
    "NFCI": "The Chicago Fed NFCI summarizes how easy or restrictive overall financial conditions are across funding, leverage, and risk markets.",
    "T10Y3M": "The 10Y-3M slope is a more policy-sensitive curve measure that has historically mattered for recession timing.",
    "epu_level": "Economic Policy Uncertainty tracks how politically and policy-driven macro stress is becoming. Sharp rises often coincide with delayed capex, tighter risk tolerance, and noisier market reactions.",
    "epu_5d_change": "The 5-day EPU change shows whether policy uncertainty is accelerating quickly enough to matter for near-term positioning.",
    "epu_20d_change": "The 20-day EPU change distinguishes brief headline noise from a more persistent policy-uncertainty build.",
    "epu_zscore_252d": "The trailing one-year EPU z-score asks whether uncertainty is merely elevated or genuinely abnormal versus the last year of observations.",
    "epu_spike_flag": "The spike flag marks unusually large EPU stress relative to trailing history and is designed as a regime-warning feature, not a standalone trade signal.",
    "consumer_sentiment_level": "Consumer sentiment is a slow household-demand context gauge. It helps frame confidence and recession risk, but without point-in-time release timestamps it should stay contextual rather than drive precise daily timing.",
    "consumer_sentiment_release_level": "The release-aware sentiment series uses ALFRED revision dates so the model only sees the latest UMCSENT reading after it was publicly available. It is still slow-moving, but it is now safe to use as a daily step feature.",
}

MACRO_SERIES_DETAILS: dict[str, dict[str, str | tuple[str, ...]]] = {
    "dxy_close": {
        "role": "Liquidity and funding-stress gauge",
        "engineering": (
            "dxy_change_5d",
            "dxy_percentile_1y",
            "dollar_strength x credit_stress",
        ),
        "interactions": (
            "rising_dxy x widening_high_yield_spread",
            "rising_dxy x falling_risk_assets",
        ),
    },
    "gold_usd_per_oz": {
        "role": "Defensive real-asset cross-check",
        "engineering": (
            "gold_momentum_20d",
            "gold_vs_dxy_relative_strength",
            "gold_breakout x rising_vix",
        ),
        "interactions": (
            "gold_strength x falling_real_growth",
            "gold_strength x policy_credibility_stress",
        ),
    },
    "wti_usd_per_bbl": {
        "role": "Growth and inflation shock channel",
        "engineering": (
            "wti_change_20d",
            "wti_volatility_20d",
            "oil_spike x inflation_pressure",
        ),
        "interactions": (
            "oil_spike x rising_yields",
            "oil_shock x weak_equity_breadth",
        ),
    },
    "us_2y_yield": {
        "role": "Front-end rate-shock variable",
        "engineering": (
            "two_year_yield_change_1m",
            "two_year_yield_change_3m",
            "rate_acceleration",
        ),
        "interactions": (
            "fast_2y_repricing x high_valuation",
            "rate_shock x growth_stock_exposure",
        ),
    },
    "us_10y_yield": {
        "role": "Discount-rate anchor",
        "engineering": (
            "ten_year_yield_change_1m",
            "ten_year_yield_change_3m",
            "long_rate_shock_score",
        ),
        "interactions": (
            "rising_10y x stretched_valuation",
            "rising_10y x weak_momentum",
        ),
    },
    "us_30y_yield": {
        "role": "Long-duration stress barometer",
        "engineering": (
            "thirty_year_yield_change_1m",
            "curve_30y10y_proxy",
            "duration_stress_flag",
        ),
        "interactions": (
            "long_bond_selloff x expensive_equities",
            "long_bond_selloff x weak_liquidity",
        ),
    },
    "yield_curve_10y_2y": {
        "display_name": "10Y minus 2Y Treasury Spread",
        "role": "Cycle-state and inversion gauge",
        "engineering": (
            "curve_change_1m",
            "inversion_flag",
            "steepening_after_inversion",
        ),
        "interactions": (
            "curve_inversion x high_valuation",
            "curve_resteepening x widening_spreads",
        ),
    },
    "high_yield_spread": {
        "role": "Credit-stress gauge",
        "engineering": (
            "hy_spread_change_5d",
            "hy_spread_percentile_1y",
            "credit_stress_score",
        ),
        "interactions": (
            "widening_spreads x negative_momentum",
            "widening_spreads x rising_vix",
        ),
    },
    "spot_vix": {
        "display_name": "Spot VIX",
        "units_override": "index level",
        "role": "Primary regime variable",
        "engineering": (
            "vix_percentile_1y",
            "vix_change_1d",
            "vix_change_5d",
            "vix_change_20d",
            "vix_acceleration",
            "return_1d_vix_adjusted",
        ),
        "interactions": (
            "rising_vix x negative_price_momentum",
            "vix_spike x volume_spike",
        ),
    },
    "vix3m_level": {
        "display_name": "VIX 3M",
        "units_override": "index level",
        "role": "Medium-horizon stress and term-structure leg",
        "engineering": (
            "vix3m_minus_vix",
            "vix_term_structure_ratio",
            "term_structure_change_5d",
        ),
        "interactions": (
            "inverted_vix_curve x weak_trend",
            "falling_vix3m x recovery_regime",
        ),
    },
    "shiller_cape_ratio": {
        "display_name": "Shiller CAPE",
        "role": "Long-horizon valuation and earnings-cycle gauge",
        "engineering": (
            "cape_percentile_10y",
            "cape_regime_flag",
            "cape x real_yield_gap",
        ),
        "interactions": (
            "high_cape x rising_real_rates",
            "high_cape x weak_breadth",
        ),
    },
    "market_cap_to_gdp_pct": {
        "display_name": "Market Cap to GDP",
        "role": "Slow valuation-fragility backdrop",
        "engineering": (
            "valuation_percentile",
            "valuation_zscore",
            "valuation_fragility_score",
        ),
        "interactions": (
            "high_valuation x rising_vix",
            "high_valuation x fast_rate_hikes",
        ),
    },
    "market_cap_to_gdp_proxy_pct": {
        "display_name": "Market Cap to GDP, Daily Proxy",
        "role": "Continuous valuation-fragility gauge",
        "engineering": (
            "valuation_proxy_percentile",
            "valuation_proxy_trend_3m",
            "valuation_proxy x credit_stress",
        ),
        "interactions": (
            "high_valuation_proxy x rising_vix",
            "high_valuation_proxy x curve_inversion",
        ),
    },
    "market_cap_to_gdp_pct_patched": {
        "display_name": "Market Cap to GDP, Official Plus Daily Composite",
        "role": "Officially anchored daily valuation backdrop for regime-aware models",
        "engineering": (
            "daily_valuation_fragility_score",
            "valuation_trend_3m",
            "valuation x rate_shock",
        ),
        "interactions": (
            "high_valuation x curve_inversion",
            "high_valuation x widening_spreads",
        ),
    },
    "cpi_yoy_pct": {
        "display_name": "CPI YoY",
        "role": "Inflation-pressure gauge",
        "engineering": (
            "cpi_yoy_change_3m",
            "inflation_momentum",
            "inflation_shock_flag",
        ),
        "interactions": (
            "inflation_pressure x rising_long_yields",
            "inflation_pressure x falling_margins_proxy",
        ),
    },
    "core_cpi_yoy_pct": {
        "display_name": "Core CPI YoY",
        "role": "Sticky inflation gauge",
        "engineering": (
            "core_cpi_change_3m",
            "core_vs_headline_gap",
            "sticky_inflation_flag",
        ),
        "interactions": (
            "sticky_inflation x rising_2y",
            "sticky_inflation x weak_duration_assets",
        ),
    },
    "energy_cpi_yoy_pct": {
        "display_name": "Energy CPI YoY",
        "role": "Commodity-shock inflation gauge",
        "engineering": (
            "energy_cpi_change_3m",
            "energy_shock_flag",
            "headline_minus_core_inflation_gap",
        ),
        "interactions": (
            "energy_shock x falling_consumer_discretionary",
            "energy_shock x rising_long_yields",
        ),
    },
    "shelter_cpi_yoy_pct": {
        "display_name": "Shelter CPI YoY",
        "role": "Sticky housing-cost inflation gauge",
        "engineering": (
            "shelter_cpi_change_3m",
            "shelter_disinflation_flag",
            "shelter_minus_headline_gap",
        ),
        "interactions": (
            "sticky_shelter x restrictive_rates",
            "sticky_shelter x weak_homebuilder_breadth",
        ),
    },
    "unemployment_rate_pct": {
        "role": "Labor-market slack indicator",
        "engineering": (
            "unemployment_change_3m",
            "unemployment_change_12m",
            "labor_deterioration_flag",
        ),
        "interactions": (
            "rising_unemployment x widening_spreads",
            "rising_unemployment x falling_equity_momentum",
        ),
    },
    "industrial_production_yoy_pct": {
        "display_name": "Industrial Production YoY",
        "role": "Broad real-activity gauge",
        "engineering": (
            "industrial_production_change_3m",
            "production_slowdown_flag",
            "goods_cycle_score",
        ),
        "interactions": (
            "production_slowdown x curve_inversion",
            "production_slowdown x widening_spreads",
        ),
    },
    "manufacturing_output_yoy_pct": {
        "display_name": "Manufacturing Output YoY",
        "role": "Goods-cycle and inventory-turn gauge",
        "engineering": (
            "manufacturing_change_3m",
            "factory_reacceleration_flag",
            "manufacturing_vs_industrial_gap",
        ),
        "interactions": (
            "factory_rollover x cyclical_equity_weakness",
            "factory_reacceleration x copper_strength",
        ),
    },
    "NFCI": {
        "role": "Composite financial-conditions gauge",
        "engineering": (
            "nfci_change_4w",
            "tightening_flag",
            "conditions_stress_score",
        ),
        "interactions": (
            "tightening_conditions x expensive_market",
            "tightening_conditions x strong_dollar",
        ),
    },
    "epu_level": {
        "role": "Policy-uncertainty stress gauge",
        "engineering": (
            "epu_5d_change",
            "epu_20d_change",
            "epu_zscore_252d",
        ),
        "interactions": (
            "epu_spike x widening_high_yield_spread",
            "epu_spike x falling_consumer_sentiment",
        ),
    },
    "consumer_sentiment_level": {
        "role": "Household confidence context gauge",
        "engineering": (
            "consumer_sentiment_3m_change",
            "consumer_sentiment_percentile_3y",
            "sentiment_drawdown_flag",
        ),
        "interactions": (
            "low_sentiment x widening_credit_spreads",
            "low_sentiment x rising_unemployment",
        ),
    },
    "consumer_sentiment_release_level": {
        "role": "Point-in-time household confidence gauge",
        "engineering": (
            "consumer_sentiment_3m_change",
            "consumer_sentiment_percentile_3y",
            "sentiment_drawdown_flag",
        ),
        "interactions": (
            "low_sentiment x widening_credit_spreads",
            "low_sentiment x rising_unemployment",
        ),
    },
    "T10Y3M": {
        "role": "Policy-sensitive curve slope",
        "engineering": (
            "t10y3m_change_1m",
            "deep_inversion_flag",
            "curve_shock_score",
        ),
        "interactions": (
            "deep_inversion x rising_unemployment",
            "deep_inversion x high_valuation",
        ),
    },
}

MACRO_ARCHITECTURE_LAYERS: tuple[dict[str, str | tuple[str, ...]], ...] = (
    {
        "title": "Regime Layer",
        "summary": "This layer decides whether the environment is calm, stressed, panicking, recovering, or inflation-shocked before any directional forecast is trusted.",
        "items": (
            "VIX level, change, percentile, and term structure",
            "Credit and liquidity stress via high-yield spreads, NFCI, and dollar strength",
            "Rate shock via front-end repricing and curve deformation",
            "Inflation breadth and production breadth so sticky inflation is not confused with a temporary commodity shock",
        ),
    },
    {
        "title": "Prediction Layer",
        "summary": "Once regime is known, price-action and macro features forecast forward return within that environment instead of pretending all regimes behave the same way.",
        "items": (
            "Price action and volume",
            "Macro, inflation, production, and valuation context",
            "Volatility-adjusted returns and breakout strength",
            "Sentiment and liquidity inputs when available",
        ),
    },
    {
        "title": "Decision Layer",
        "summary": "The trading decision should use regime and return forecasts to decide not only direction but exposure quality.",
        "items": (
            "Trade or no trade",
            "Position size",
            "Stop distance",
            "Leverage and cooldown",
            "Which strategy family is active",
        ),
    },
)

MACRO_DESIGN_PRINCIPLES: tuple[dict[str, str], ...] = (
    {
        "title": "VIX gets a structural role, not a manual weight",
        "body": "VIX is option-implied 30-day stress, not a generic input beside RSI. It should affect participation, sizing, stops, leverage, and strategy selection, not only the probability score.",
    },
    {
        "title": "Normalize price moves by implied volatility",
        "body": "A 2% move at low VIX is abnormal; the same move at high VIX may be ordinary. Returns, breakouts, drawdowns, and volume spikes become more informative when scaled by implied volatility.",
    },
    {
        "title": "Valuation is a vulnerability multiplier",
        "body": "High CAPE or market-cap-to-GDP does not mean crash tomorrow. It lowers long-run expected return and becomes dangerous when combined with rising volatility, widening spreads, or rapid tightening.",
    },
    {
        "title": "Decompose inflation before declaring a regime",
        "body": "Headline CPI can fall because energy rolled over while shelter and core stay sticky. The regime should react to the breadth of inflation, not just the headline print.",
    },
    {
        "title": "Rate pace matters more than static levels",
        "body": "Equities usually react hardest to speed, surprise, and direction of rate change. Front-end repricing, real-yield moves, and curve change deserve their own shock variables.",
    },
    {
        "title": "Production confirms or rejects the market narrative",
        "body": "Industrial and manufacturing output tell you whether real activity is improving underneath price action. If production is rolling over while risk assets levitate, fragility is rising.",
    },
    {
        "title": "Interactions matter more than isolated readings",
        "body": "High valuation alone is not enough, and high VIX alone is not enough. The dangerous state is the interaction: high valuation plus rising VIX plus fast rate hikes plus negative momentum plus credit stress.",
    },
)

MACRO_RECOMMENDED_EXPANSIONS: tuple[dict[str, str | tuple[str, ...]], ...] = (
    {
        "title": "Derive Next From Current Inputs",
        "items": (
            "vix_percentile_1y, vix_change_1d, vix_change_5d, vix_change_20d, and vix_acceleration",
            "realized_vol_20d and iv_rv_spread = spot_vix minus realized_vol_20d",
            "return_1d_vix_adjusted, return_5d_vix_adjusted, breakout_strength_vix_adjusted, and drawdown_vix_adjusted",
            "headline_minus_core_inflation_gap, shelter_minus_headline_gap, sticky_inflation_flag, and energy_shock_flag",
            "industrial_production_change_3m, manufacturing_change_3m, goods_cycle_score, and production_slowdown_flag",
            "two_year_yield_change_1m, yield_curve_change_3m, credit_stress_score, valuation_fragility_score, and rate_shock_score",
        ),
    },
    {
        "title": "Added In This Macro Upgrade",
        "items": (
            "shiller_cape_ratio is now active beside market-cap-to-GDP so valuation is read as a long-cycle fragility cluster rather than a single indicator",
            "core_cpi_yoy_pct, energy_cpi_yoy_pct, and shelter_cpi_yoy_pct split sticky inflation from commodity-driven inflation",
            "industrial_production_yoy_pct and manufacturing_output_yoy_pct add real-economy breadth to the macro stack",
            "spot_vix now uses VXO fallback and vix3m_level uses a regression-backed pre-launch backfill so the aligned daily frame has no leading gaps",
        ),
    },
    {
        "title": "Open Data Worth Adding Next",
        "items": (
            "Fed funds level and 3m, 6m, and 12m change",
            "Real-yield level and change, breakevens, and expected Fed path / policy-surprise measures",
            "Senior Loan Officer Opinion Survey, bank lending standards, and delinquency / default rates",
            "PMI new orders, inventory-to-sales, freight, rail, trucking, and port activity for real-economy breadth",
            "Google Trends search intensity for layoffs, recession, housing, AI, semiconductors, and labor-market stress",
            "Patent activity, venture funding, semiconductor capex, R&D-heavy equity baskets, and IPO issuance as innovation proxies",
        ),
    },
)

MACRO_INTERACTION_LIBRARY: tuple[str, ...] = (
    "high_valuation x rising_vix",
    "high_cape x rising_real_rates",
    "high_valuation x fast_rate_hikes",
    "high_valuation x yield_curve_inversion",
    "rising_vix x negative_price_momentum",
    "rate_shock x growth_stock_exposure",
    "vix_spike x volume_spike",
    "credit_stress x dollar_strength",
    "energy_shock x falling_manufacturing_output",
    "sticky_inflation x weak_industrial_production",
)

MACRO_SCENARIO_PLAYBOOK: tuple[dict[str, str], ...] = (
    {
        "title": "High valuation, low VIX",
        "body": "The market is expensive but not yet stressed. Lower long-run expected return, but do not force a short solely because valuation is rich.",
    },
    {
        "title": "High valuation, rising VIX",
        "body": "Fragility is starting to activate. Reduce long exposure, tighten risk, and demand stronger confirmation before trusting breakouts.",
    },
    {
        "title": "High valuation, rising VIX, fast rate hikes",
        "body": "This is closer to a crash-risk regime. Avoid leveraged longs, prefer defense, and treat liquidity-sensitive assets as vulnerable.",
    },
    {
        "title": "High VIX but falling",
        "body": "Stress is still elevated, but the direction of stress is improving. This can be a recovery or relief-rally regime rather than a pure panic regime.",
    },
    {
        "title": "Low VIX, strong trend",
        "body": "Trend following can work well, but complacency risk rises if valuation is stretched and the front end starts repricing higher.",
    },
    {
        "title": "Sticky core and shelter inflation, weakening production",
        "body": "This is the stagflation squeeze. Growth assets lose support, duration can struggle, and risk control matters more than chasing nominal rebounds.",
    },
    {
        "title": "Energy spike, stable core, resilient production",
        "body": "Treat this as a commodity shock first, not an automatic persistent inflation regime. Watch whether the shock bleeds into core and labor before overreacting.",
    },
)

MACRO_REGIME_WINDOWS: tuple[dict[str, str], ...] = (
    {"label": "Dot-com unwind", "start": "2000-03-01", "end": "2002-10-31"},
    {"label": "GFC", "start": "2007-10-01", "end": "2009-06-30"},
    {"label": "Pandemic shock", "start": "2020-02-15", "end": "2020-08-31"},
    {"label": "Inflation tightening", "start": "2021-03-01", "end": "2023-12-31"},
)

__all__ = [
    "MACRO_REGIME_WINDOWS",
    "MACRO_ARCHITECTURE_LAYERS",
    "MACRO_DESIGN_PRINCIPLES",
    "MACRO_INTERACTION_LIBRARY",
    "MACRO_REPORT_GROUPS",
    "MACRO_RECOMMENDED_EXPANSIONS",
    "MACRO_SCENARIO_PLAYBOOK",
    "MACRO_SERIES_BRIEFS",
    "MACRO_SERIES_DETAILS",
    "MODEL_MACRO_CONTEXT_COLUMNS",
]