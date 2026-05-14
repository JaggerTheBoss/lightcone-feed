"""Lightcone configuration + preset profiles."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import FrozenSet, Iterable

from .bar import validate_field_names


@dataclass(frozen=True)
class LightconeConfig:
    """Declares which bar fields the strategy is permitted to read.

    The feed wraps each yielded bar in a BarView that hides fields not
    listed here. Accidental access to undeclared fields raises
    FieldNotDeclared.

    `extras` allows declaring opt-in access to keys inside Bar.extras
    (e.g., venue-specific fields like funding_rate, open_interest).
    """
    bar_fields: FrozenSet[str] = field(default_factory=lambda: frozenset({"ts", "close"}))
    extras: FrozenSet[str] = field(default_factory=frozenset)

    def __post_init__(self):
        # Validate the declared fields actually exist on Bar.
        validated = validate_field_names(self.bar_fields)
        object.__setattr__(self, "bar_fields", validated)
        object.__setattr__(self, "extras", frozenset(self.extras))


# Preset profiles — most strategies will use one of these directly.

CLOSE_ONLY = LightconeConfig(
    bar_fields=frozenset({"ts", "close"}),
)
"""Closed candle price only. Matches discretionary / human-trader replay style.
Use when the strategy decides based on confirmed candle close, nothing else."""

OHLCV = LightconeConfig(
    bar_fields=frozenset({"ts", "open", "high", "low", "close", "volume"}),
)
"""Standard algorithmic backtest view. Open/High/Low/Close + Volume.
Use for most price-action strategies, zone bouncing, breakout, etc."""

FULL_TAPE = LightconeConfig(
    bar_fields=frozenset({"ts", "open", "high", "low", "close", "volume",
                          "n_trades", "taker_buy"}),
)
"""Microstructure view. Adds trade count and taker buy volume for
order-flow analysis. Use for tape-reading / microstructure strategies."""


def custom(*field_names: str, extras: Iterable[str] = ()) -> LightconeConfig:
    """Build a custom config from explicit field names.

    Example:
        cfg = custom("close", "volume", "n_trades")
    """
    return LightconeConfig(
        bar_fields=frozenset(field_names),
        extras=frozenset(extras),
    )
