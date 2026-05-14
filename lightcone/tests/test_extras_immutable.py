"""Extras dict must be immutable once a Bar is constructed.

Otherwise an external mutation could leak future state into past views.
"""
import pytest

from lightcone import Bar, Lightcone, LightconeConfig
from lightcone.exceptions import FieldNotDeclared


def test_extras_frozen_after_construction():
    raw = {"funding_rate": 0.0001}
    bar = Bar(ts=1_000_000, open=1, high=2, low=0.5, close=1.5, volume=10, extras=raw)
    # Mutating the original dict should NOT affect the Bar
    raw["funding_rate"] = 9999.9
    assert bar.extras["funding_rate"] == 0.0001


def test_extras_cannot_be_mutated_via_bar():
    bar = Bar(ts=1_000_000, open=1, high=2, low=0.5, close=1.5, volume=10,
              extras={"x": 1})
    with pytest.raises(TypeError):
        bar.extras["x"] = 999
    with pytest.raises(TypeError):
        bar.extras["y"] = 999


def test_extras_visible_through_view_after_external_mutation_attempt():
    raw = {"funding_rate": 0.0001}
    bar = Bar(ts=1_000_000, open=1, high=2, low=0.5, close=1.5, volume=10, extras=raw)
    raw["funding_rate"] = 9999.9
    cfg = LightconeConfig(bar_fields=frozenset({"close"}), extras=frozenset({"funding_rate"}))
    feed = Lightcone(streams={"A": [bar]}, config=cfg)
    view, _, t = feed.next_bar()
    # View MUST show the original, not the mutated value
    assert view.funding_rate == 0.0001
    feed.confirm(t)
