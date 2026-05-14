"""Fill simulator — separate code path that DOES see full OHLC.

Strategy decisions consume the field-restricted BarView (declared fields
only). Fill simulation runs on the side and reads the bar's full OHLC
to determine whether limit/stop orders would have hit.

Rationale: a strategy might legitimately only "decide" using close, but
to backtest order fills you still need to know the bar's range.
Separating these prevents the strategy logic from ever reading high/low
while still allowing realistic fill modeling.

For prediction-market strategies (Polymarket UP/DOWN), this module is
not needed — fills are externally simulated against a fill_mean
distribution. This is for HL perps / spot strategies with limit orders.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .bar import Bar


class Side(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


@dataclass(frozen=True)
class Order:
    side: Side
    qty: float
    order_type: OrderType
    price: Optional[float] = None  # limit/stop trigger; None for market


@dataclass(frozen=True)
class Fill:
    side: Side
    qty: float
    price: float


def simulate_fill(order: Order, bar: Bar, slippage_bps: float = 0.0) -> Optional[Fill]:
    """Determine if an order would fill against this bar.

    Pessimistic model:
      - MARKET fills at bar open ± slippage
      - BUY LIMIT fills if bar.low <= limit; price = limit (or open if open <= limit)
      - SELL LIMIT fills if bar.high >= limit; price = limit (or open if open >= limit)
      - BUY STOP fills if bar.high >= stop; price = max(stop, open) + slippage
      - SELL STOP fills if bar.low <= stop; price = min(stop, open) - slippage

    Returns None if order did not fill on this bar.
    """
    slip = slippage_bps / 10_000.0

    if order.order_type is OrderType.MARKET:
        px = bar.open * (1 + slip) if order.side is Side.BUY else bar.open * (1 - slip)
        return Fill(order.side, order.qty, px)

    if order.price is None:
        raise ValueError(f"{order.order_type} requires a price")

    if order.order_type is OrderType.LIMIT:
        if order.side is Side.BUY and bar.low <= order.price:
            px = min(order.price, bar.open)
            return Fill(order.side, order.qty, px)
        if order.side is Side.SELL and bar.high >= order.price:
            px = max(order.price, bar.open)
            return Fill(order.side, order.qty, px)
        return None

    if order.order_type is OrderType.STOP:
        if order.side is Side.BUY and bar.high >= order.price:
            px = max(order.price, bar.open) * (1 + slip)
            return Fill(order.side, order.qty, px)
        if order.side is Side.SELL and bar.low <= order.price:
            px = min(order.price, bar.open) * (1 - slip)
            return Fill(order.side, order.qty, px)
        return None

    return None
