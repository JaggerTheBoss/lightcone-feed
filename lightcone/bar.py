"""Immutable bar dataclass + field-restricted view."""
from __future__ import annotations
from dataclasses import dataclass, field, fields as dc_fields
from types import MappingProxyType
from typing import Any, FrozenSet, Mapping

from .exceptions import FieldNotDeclared


_EMPTY_EXTRAS: Mapping[str, Any] = MappingProxyType({})


@dataclass(frozen=True)
class Bar:
    """One OHLCV bar. Immutable.

    Strategies should NOT receive this directly — they receive a BarView
    that restricts which fields are readable. The raw Bar is for internal
    use by the feed and fill simulator.

    `ts` is the bar's CLOSE timestamp in milliseconds (when the bar finalizes
    and its data becomes known). Convention: bar with ts=T contains data
    aggregated up to and including time T.
    """
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    n_trades: int = 0
    taker_buy: float = 0.0
    extras: Mapping[str, Any] = field(default_factory=lambda: _EMPTY_EXTRAS)

    def __post_init__(self):
        # Freeze extras dict so external mutation cannot leak into views.
        if not isinstance(self.extras, MappingProxyType):
            frozen = MappingProxyType(dict(self.extras))
            object.__setattr__(self, "extras", frozen)

    @classmethod
    def from_ohlcv_row(cls, row) -> "Bar":
        """Build from a [ts, o, h, l, c, v, ...] list/tuple (Binance/HL format).

        Accepts strings (Binance JSON) or numerics. ts must be milliseconds.
        """
        return cls(
            ts=int(row[0]),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]) if len(row) > 5 else 0.0,
            n_trades=int(float(row[8])) if len(row) > 8 else 0,
            taker_buy=float(row[9]) if len(row) > 9 else 0.0,
        )


_DECLARABLE_FIELDS: FrozenSet[str] = frozenset(
    f.name for f in dc_fields(Bar) if f.name != "extras"
)


class BarView:
    """Field-restricted read-only proxy over a Bar.

    Accessing a field that was NOT declared in LightconeConfig.bar_fields
    raises FieldNotDeclared. The wrapped Bar object is NOT accessible
    via the view — there is no escape hatch like `view._bar.high`.

    `ts` is ALWAYS readable — every strategy needs to know what time it is.
    """
    __slots__ = ("_bar", "_allowed", "_extras_allowed")

    def __init__(self, bar: Bar, allowed: FrozenSet[str], extras_allowed: FrozenSet[str] = frozenset()):
        object.__setattr__(self, "_bar", bar)
        object.__setattr__(self, "_allowed", frozenset(allowed) | {"ts"})
        object.__setattr__(self, "_extras_allowed", frozenset(extras_allowed))

    def __getattribute__(self, name: str):
        # Dunder access (repr, copy, class, etc.) passes through normally.
        if name.startswith("__") and name.endswith("__"):
            return object.__getattribute__(self, name)
        # Single-underscore private state is NOT accessible from outside.
        # This blocks the obvious bypass `view._bar.high`.
        if name.startswith("_"):
            raise AttributeError(f"BarView has no attribute {name!r}")
        # Public name → look up the declared field
        bar = object.__getattribute__(self, "_bar")
        allowed = object.__getattribute__(self, "_allowed")
        extras_allowed = object.__getattribute__(self, "_extras_allowed")
        if name in allowed:
            return getattr(bar, name)
        if name in extras_allowed:
            return bar.extras.get(name)
        raise FieldNotDeclared(
            f"Field {name!r} was not declared in LightconeConfig.bar_fields. "
            f"Declared: {sorted(allowed)}. Extras: {sorted(extras_allowed)}."
        )

    def __setattr__(self, name, value):
        raise AttributeError("BarView is read-only")

    def __repr__(self):
        bar = object.__getattribute__(self, "_bar")
        allowed = object.__getattribute__(self, "_allowed")
        visible = {k: getattr(bar, k) for k in sorted(allowed) if hasattr(bar, k)}
        return f"BarView({visible})"


def validate_field_names(names) -> FrozenSet[str]:
    """Validate that requested field names exist on Bar. Returns the validated set."""
    names = frozenset(names)
    unknown = names - _DECLARABLE_FIELDS
    if unknown:
        raise ValueError(
            f"Unknown bar fields: {sorted(unknown)}. "
            f"Available: {sorted(_DECLARABLE_FIELDS)}."
        )
    return names
