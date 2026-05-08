from __future__ import annotations

DEFAULT_PANEL_SYMBOLS: list[str] = [
    "AAPL",
    "AMZN",
    "COIN",
    "HOOD",
    "INTC",
    "MSFT",
    "MSTR",
    "NVDA",
    "PLTR",
    "QQQ",
    "SPY",
    "TSLA",
]

DEFAULT_SYMBOL_PROFILES: dict[str, dict[str, object]] = {
    "AAPL": {"market_cap_bucket": "mega", "liquidity_tier": "very_high", "shortable": True},
    "AMZN": {"market_cap_bucket": "mega", "liquidity_tier": "very_high", "shortable": True},
    "COIN": {"market_cap_bucket": "large", "liquidity_tier": "high", "shortable": True},
    "HOOD": {"market_cap_bucket": "mid", "liquidity_tier": "high", "shortable": True},
    "INTC": {"market_cap_bucket": "large", "liquidity_tier": "high", "shortable": True},
    "MSFT": {"market_cap_bucket": "mega", "liquidity_tier": "very_high", "shortable": True},
    "MSTR": {"market_cap_bucket": "mid", "liquidity_tier": "high", "shortable": True},
    "NVDA": {"market_cap_bucket": "mega", "liquidity_tier": "very_high", "shortable": True},
    "PLTR": {"market_cap_bucket": "large", "liquidity_tier": "high", "shortable": True},
    "QQQ": {"market_cap_bucket": "etf", "liquidity_tier": "very_high", "shortable": True},
    "SPY": {"market_cap_bucket": "etf", "liquidity_tier": "very_high", "shortable": True},
    "TSLA": {"market_cap_bucket": "mega", "liquidity_tier": "very_high", "shortable": True},
}


def expand_symbol_selection(symbols: list[str]) -> list[str]:
    expanded: list[str] = []
    for symbol in symbols:
        normalized = symbol.upper()
        if normalized == "PANEL":
            expanded.extend(DEFAULT_PANEL_SYMBOLS)
        else:
            expanded.append(normalized)

    deduplicated = list(dict.fromkeys(expanded))
    return deduplicated


def resolve_symbol_profile(symbol: str) -> dict[str, object]:
    return DEFAULT_SYMBOL_PROFILES.get(symbol.upper(), {}).copy()

