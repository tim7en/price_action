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
from typing import Callable, Mapping, Sequence

import numpy as np
import pandas as pd


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
    venue_instrument_mapping_supplied: bool = False

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
                "research_only": bool(
                    not self.venue_instrument_mapping_supplied
                    or (self.product != "spot" and not self.funding_history_supplied)
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


def _next_price(series: pd.Series, date: pd.Timestamp) -> tuple[pd.Timestamp, float]:
    prices = series.loc[series.index > pd.Timestamp(date)].dropna()
    if prices.empty:
        raise ValueError(f"No executable price strictly after {pd.Timestamp(date).date()}")
    return pd.Timestamp(prices.index[0]), float(prices.iloc[0])


def _portfolio_statistics(periods: pd.DataFrame, execution: BinanceExecutionCosts) -> dict[str, object]:
    if periods.empty:
        return {
            "periods": 0,
            "status": "NO_OUT_OF_SAMPLE_PERIODS",
            "execution": execution.to_dict(),
        }
    net = periods["net_return"].astype(float)
    gross = periods["gross_return_before_costs"].astype(float)
    benchmark = periods["benchmark_return"].astype(float)
    elapsed_days = max((pd.Timestamp(periods["period_end"].iloc[-1]) - pd.Timestamp(periods["period_start"].iloc[0])).days, 1)
    years = elapsed_days / 365.25
    equity = (1.0 + net).cumprod()
    benchmark_equity = (1.0 + benchmark).cumprod()
    annualized_return = float(equity.iloc[-1] ** (1.0 / years) - 1.0)
    annualized_volatility = float(net.std(ddof=1) * np.sqrt(12.0)) if len(net) > 1 else np.nan
    downside = float(net.loc[net < 0.0].std(ddof=1) * np.sqrt(12.0)) if (net < 0.0).sum() > 1 else np.nan
    return {
        "status": "RESEARCH_ONLY" if execution.to_dict()["research_only"] else "INVESTABLE_ASSUMPTIONS_SUPPLIED",
        "periods": int(len(periods)),
        "period_start": pd.Timestamp(periods["period_start"].iloc[0]).strftime("%Y-%m-%d"),
        "period_end": pd.Timestamp(periods["period_end"].iloc[-1]).strftime("%Y-%m-%d"),
        "cumulative_gross_return_before_costs": float((1.0 + gross).prod() - 1.0),
        "cumulative_net_return": float(equity.iloc[-1] - 1.0),
        "benchmark_cumulative_return": float(benchmark_equity.iloc[-1] - 1.0),
        "annualized_net_return": annualized_return,
        "annualized_volatility": annualized_volatility,
        "sharpe_zero_cash_rate": float(annualized_return / annualized_volatility) if annualized_volatility > 0.0 else None,
        "sortino_zero_cash_rate": float(annualized_return / downside) if downside > 0.0 else None,
        "max_drawdown": float((equity / equity.cummax() - 1.0).min()),
        "average_one_way_turnover": float(periods["one_way_turnover"].mean()),
        "annualized_one_way_turnover": float(periods["one_way_turnover"].sum() / years),
        "total_commission_and_slippage": float(periods["trade_cost"].sum()),
        "total_funding_paid": float(periods["funding_cost"].sum()),
        "average_gross_exposure": float(periods["gross_exposure"].mean()),
        "active_period_fraction": float(periods["gross_exposure"].gt(0.0).mean()),
        "execution": execution.to_dict(),
        "price_source_note": "Adjusted underlying closes, executed on the first observation strictly after each signal; Binance mark-price history is not present.",
    }


def simulate_rebalanced_portfolio(
    target_weights: pd.DataFrame,
    rebalance_dates: Sequence[pd.Timestamp],
    price_loader: Callable[[str], pd.Series],
    execution: BinanceExecutionCosts,
    *,
    benchmark_symbol: str = "SPY",
    annual_funding_rates: Mapping[pd.Timestamp, Mapping[str, float]] | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Simulate next-session rebalancing with drift-aware Binance costs.

    ``target_weights`` must contain ``date``, ``symbol``, and
    ``target_weight``. Empty dates are supplied separately in
    ``rebalance_dates`` so an abstaining model remains represented in the
    performance series. Historical funding maps are decimal annual rates.
    """
    required = {"date", "symbol", "target_weight"}
    missing = required - set(target_weights.columns)
    if missing:
        raise ValueError(f"Missing target-weight columns: {sorted(missing)}")
    dates = sorted({pd.Timestamp(date) for date in rebalance_dates})
    if len(dates) < 2:
        return pd.DataFrame(), _portfolio_statistics(pd.DataFrame(), execution)
    targets = target_weights.copy()
    targets["date"] = pd.to_datetime(targets["date"])
    targets["target_weight"] = pd.to_numeric(targets["target_weight"], errors="coerce").fillna(0.0)
    cache: dict[str, pd.Series] = {}

    def prices(symbol: str) -> pd.Series:
        if symbol not in cache:
            series = price_loader(symbol).dropna().astype(float).sort_index()
            series.index = pd.DatetimeIndex(series.index).tz_localize(None).normalize()
            cache[symbol] = series.loc[~series.index.duplicated(keep="last")]
        return cache[symbol]

    benchmark = prices(benchmark_symbol)
    pretrade_weights: dict[str, float] = {}
    rows: list[dict[str, object]] = []
    for start, end in zip(dates[:-1], dates[1:], strict=True):
        subset = targets.loc[targets["date"].eq(start) & targets["target_weight"].ne(0.0)]
        target = subset.groupby("symbol")["target_weight"].sum().to_dict()
        execution.validate_weights(target)
        turnover, trade_cost = rebalance_cost(pretrade_weights, target, execution)
        asset_returns: dict[str, float] = {}
        entry_dates: list[pd.Timestamp] = []
        exit_dates: list[pd.Timestamp] = []
        for symbol in target:
            entry_date, entry_price = _next_price(prices(symbol), start)
            exit_date, exit_price = _next_price(prices(symbol), end)
            if exit_date <= entry_date:
                raise ValueError(f"Non-positive holding window for {symbol} at {start.date()}")
            asset_returns[symbol] = exit_price / entry_price - 1.0
            entry_dates.append(entry_date)
            exit_dates.append(exit_date)
        benchmark_entry_date, benchmark_entry = _next_price(benchmark, start)
        benchmark_exit_date, benchmark_exit = _next_price(benchmark, end)
        holding_days = float((benchmark_exit_date - benchmark_entry_date).days)
        market_return = float(sum(target[symbol] * asset_returns[symbol] for symbol in target))
        gross_exposure = float(sum(abs(weight) for weight in target.values()))
        period_funding = funding_cost(
            target,
            holding_days,
            execution,
            (annual_funding_rates or {}).get(start),
        )
        period_carry = cash_carry(gross_exposure, holding_days, execution)
        gross_before_costs = market_return + period_carry - period_funding
        net_return = gross_before_costs - trade_cost
        nav_factor = max(1.0 + net_return, 1e-9)
        pretrade_weights = {
            symbol: target[symbol] * (1.0 + asset_returns[symbol]) / nav_factor
            for symbol in target
        }
        rows.append({
            "signal_date": start,
            "period_start": min(entry_dates) if entry_dates else benchmark_entry_date,
            "period_end": max(exit_dates) if exit_dates else benchmark_exit_date,
            "holding_days": holding_days,
            "active_names": int(len(target)),
            "gross_exposure": gross_exposure,
            "net_exposure": float(sum(target.values())),
            "one_way_turnover": turnover,
            "trade_cost": trade_cost,
            "funding_cost": period_funding,
            "cash_carry": period_carry,
            "asset_return": market_return,
            "gross_return_before_costs": gross_before_costs,
            "net_return": net_return,
            "benchmark_return": benchmark_exit / benchmark_entry - 1.0,
        })
    periods = pd.DataFrame(rows)
    if not periods.empty and pretrade_weights:
        liquidation_turnover, liquidation_cost = rebalance_cost(pretrade_weights, {}, execution)
        periods.loc[periods.index[-1], "one_way_turnover"] += liquidation_turnover
        periods.loc[periods.index[-1], "trade_cost"] += liquidation_cost
        periods.loc[periods.index[-1], "net_return"] -= liquidation_cost
        periods.loc[periods.index[-1], "terminal_liquidation_cost"] = liquidation_cost
    if "terminal_liquidation_cost" not in periods:
        periods["terminal_liquidation_cost"] = 0.0
    else:
        periods["terminal_liquidation_cost"] = periods["terminal_liquidation_cost"].fillna(0.0)
    periods["gross_equity"] = (1.0 + periods["gross_return_before_costs"]).cumprod()
    periods["net_equity"] = (1.0 + periods["net_return"]).cumprod()
    periods["benchmark_equity"] = (1.0 + periods["benchmark_return"]).cumprod()
    return periods, _portfolio_statistics(periods, execution)
