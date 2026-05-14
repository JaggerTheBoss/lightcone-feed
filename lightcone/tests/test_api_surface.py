"""API surface tests — every public name must be reachable and behave."""
import pytest

import lightcone
from lightcone import (
    Lightcone, LightconeConfig, Bar, BarView,
    CLOSE_ONLY, OHLCV, FULL_TAPE, custom,
    LightconeError, NotConfirmed, BadToken, FieldNotDeclared, FeedExhausted,
    Order, Fill, Side, OrderType, simulate_fill,
    from_ohlcv_rows,
)


def test_all_exports_match_init():
    expected = {
        "Lightcone", "from_ohlcv_rows",
        "Bar", "BarView",
        "LightconeConfig", "CLOSE_ONLY", "OHLCV", "FULL_TAPE", "custom",
        "LightconeError", "NotConfirmed", "BadToken", "FieldNotDeclared", "FeedExhausted",
        "Order", "Fill", "Side", "OrderType", "simulate_fill",
    }
    assert set(lightcone.__all__) == expected


def test_config_accessible_on_feed():
    bars = [Bar(ts=1000, open=1, high=2, low=0.5, close=1.5, volume=10)]
    feed = Lightcone(streams={"A": bars}, config=CLOSE_ONLY)
    assert feed.config is CLOSE_ONLY


def test_exception_hierarchy():
    """All custom exceptions inherit from LightconeError."""
    assert issubclass(NotConfirmed, LightconeError)
    assert issubclass(BadToken, LightconeError)
    assert issubclass(FieldNotDeclared, LightconeError)
    assert issubclass(FeedExhausted, LightconeError)


def test_field_not_declared_is_NOT_attribute_error():
    """Defense in depth: hasattr() must not silently swallow FieldNotDeclared."""
    assert not issubclass(FieldNotDeclared, AttributeError)


def test_all_preset_configs_have_ts():
    """Strategy always needs to know what time it is."""
    for cfg in (CLOSE_ONLY, OHLCV, FULL_TAPE):
        assert "ts" in cfg.bar_fields


def test_custom_config_construction():
    cfg = custom("close", "volume", extras=["funding_rate"])
    assert "close" in cfg.bar_fields
    assert "volume" in cfg.bar_fields
    assert "funding_rate" in cfg.extras


def test_config_is_frozen():
    """LightconeConfig is immutable post-construction."""
    cfg = CLOSE_ONLY
    with pytest.raises((AttributeError, Exception)):
        cfg.bar_fields = frozenset()


def test_bar_is_frozen():
    bar = Bar(ts=1000, open=1, high=2, low=0.5, close=1.5, volume=10)
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        bar.close = 999
