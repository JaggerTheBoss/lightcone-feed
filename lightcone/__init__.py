"""lightcone — strict-ordering bar feed for backtests and live strategies.

Only the past light cone influences the present.

Usage:
    from lightcone import Lightcone, OHLCV, FeedExhausted

    feed = Lightcone(streams={("BTC","5m"): btc_bars}, config=OHLCV)
    while True:
        try:
            bar, key, token = feed.next_bar()
        except FeedExhausted:
            break
        # ... your strategy reads bar.close, bar.high, etc. (only declared fields)
        feed.confirm(token)

The feed will REFUSE to deliver the next bar until the previous one is
confirmed. Accidental access to undeclared fields raises FieldNotDeclared.
Lookahead is structurally impossible — the future literally does not exist
until you finish the present.
"""
from .feed import Lightcone, from_ohlcv_rows
from .bar import Bar, BarView
from .config import LightconeConfig, CLOSE_ONLY, OHLCV, FULL_TAPE, custom
from .exceptions import (
    LightconeError,
    NotConfirmed,
    BadToken,
    FieldNotDeclared,
    FeedExhausted,
)
from .fill_sim import Order, Fill, Side, OrderType, simulate_fill

__all__ = [
    "Lightcone",
    "from_ohlcv_rows",
    "Bar",
    "BarView",
    "LightconeConfig",
    "CLOSE_ONLY",
    "OHLCV",
    "FULL_TAPE",
    "custom",
    "LightconeError",
    "NotConfirmed",
    "BadToken",
    "FieldNotDeclared",
    "FeedExhausted",
    "Order",
    "Fill",
    "Side",
    "OrderType",
    "simulate_fill",
]
