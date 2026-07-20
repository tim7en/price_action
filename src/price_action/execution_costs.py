"""Venue-aware execution costs used by research portfolio backtests.

The final hierarchy can be expressed through Binance spot or USD-M perpetuals,
depending on the instrument.  These products do not have the same economics:
spot pays trading commission and spread/slippage, while perpetuals also pay or
receive funding.  All rates are deliberately configurable because Binance VIP
tiers, BNB discounts, promotions, funding, and market impact change over time.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

import numpy as np


@dataclass(frozen=True)
class BinanceExecutionCosts:
    """Conservative Binance execution assumptions.

    Rates expressed in basis points are charged per unit of one-way traded
    notional.  For example, moving from a 20% long to a 10% short creates 30%
    turnover and therefore pays costs on 30% of NAV.
    """

    product: str = "tradfi_perp"
    maker_fee_bps: float = 10.0
    taker_fee_bps: float = 10.0
    maker_fill_fraction: float = 0.0
    bnb_fee_discount_fraction: float = 0.0
    slippage_bps: float = 5.0
    annual_funding_bps: float = 0.0
    annual_cash_yield_bps: float = 0.0
    funding_history_supplied: bool = False

    def __post_init__(self) -> None:
        if self.product not in {"spot", "usd_m_perp", "tradfi_perp"}:
            raise ValueError(f"Unsupported Binance product: {self.product}")
        for name in ("maker_fill_fraction", "bnb_fee_discount_fraction"):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        for name in (
            "maker_fee_bps",
            "taker_fee_bps",
            "slippage_bps",
            "annual_cash_yield_bps",
        ):
            if float(getattr(self, name)) < 0.0:
                raise ValueError(f"{name} cannot be negative")
        if self.product == "spot" and abs(float(self.annual_funding_bps)) > 1e-12:
            raise ValueError("Spot execution cannot have perpetual funding")

    @property
    def commission_bps(self) -> float:
        blended = (
            self.maker_fill_fraction * self.maker_fee_bps
            + (1.0 - self.maker_fill_fraction) * self.taker_fee_bps
        )
        return float(blended * (1.0 - self.bnb_fee_discount_fraction))

    @property
    def all_in_trade_cost_bps(self) -> float:
        return float(self.commission_bps + self.slippage_bps)

    @property
    def all_in_trade_cost_rate(self) -> float:
        return self.all_in_trade_cost_bps / 10_000.0

    def validate_weights(self, weights: Mapping[str, float]) -> None:
        if self.product == "spot" and any(float(value) < -1e-12 for value in weights.values()):
            raise ValueError("Negative target weights require a margin or perpetual product, not Binance spot")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload.update(
            {
                "commission_bps": self.commission_bps,
                "all_in_trade_cost_bps": self.all_in_trade_cost_bps,
                "turnover_definition": "sum(abs(target_weight - prior_weight))",
                "funding_note": (
                    "Funding disabled for spot."
                    if self.product == "spot"
                    else "Positive funding means longs pay and shorts receive; supply historical rates for investable results."
                ),
            }
        )
        return payload


def load_binance_execution_costs(path: str | Path) -> BinanceExecutionCosts:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return BinanceExecutionCosts(**payload)


def one_way_turnover(
    prior_weights: Mapping[str, float],
    target_weights: Mapping[str, float],
) -> float:
    symbols = set(prior_weights) | set(target_weights)
    return float(sum(abs(float(target_weights.get(symbol, 0.0)) - float(prior_weights.get(symbol, 0.0))) for symbol in symbols))


def rebalance_cost(
    prior_weights: Mapping[str, float],
    target_weights: Mapping[str, float],
    execution: BinanceExecutionCosts,
) -> tuple[float, float]:
    execution.validate_weights(target_weights)
    turnover = one_way_turnover(prior_weights, target_weights)
    return turnover, float(turnover * execution.all_in_trade_cost_rate)


def funding_cost(
    weights: Mapping[str, float],
    holding_days: float,
    execution: BinanceExecutionCosts,
    annual_funding_rates: Mapping[str, float] | None = None,
) -> float:
    """Return funding paid as a fraction of NAV; negative means funding earned.

    ``annual_funding_rates`` values are decimal annual rates, not basis points.
    With positive funding a positive (long) weight pays and a negative (short)
    weight receives.  The configured scalar scenario is used when a historical
    rate is unavailable.
    """
    if execution.product == "spot" or holding_days <= 0.0:
        return 0.0
    scenario_rate = execution.annual_funding_bps / 10_000.0
    total = 0.0
    for symbol, weight in weights.items():
        rate = float((annual_funding_rates or {}).get(symbol, scenario_rate))
        if not np.isfinite(rate):
            rate = scenario_rate
        total += float(weight) * rate * float(holding_days) / 365.25
    return float(total)


def cash_carry(gross_exposure: float, holding_days: float, execution: BinanceExecutionCosts) -> float:
    idle_fraction = max(1.0 - float(gross_exposure), 0.0)
    annual_yield = execution.annual_cash_yield_bps / 10_000.0
    return float(idle_fraction * annual_yield * float(holding_days) / 365.25)
