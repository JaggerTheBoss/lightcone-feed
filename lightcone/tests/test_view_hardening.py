"""BarView hardening tests — no bypass via private attribute access.

A naive __getattr__ implementation lets bypass via `view._bar.high`. The
hardened __getattribute__ override blocks all single-underscore private
access from outside the class.
"""
import pytest

from lightcone import Lightcone, Bar, CLOSE_ONLY
from lightcone.exceptions import FieldNotDeclared


def make_bar():
    return Bar(ts=1_000_000, open=10.0, high=11.0, low=9.0, close=10.5, volume=100.0)


def test_cannot_access_underlying_bar_via_underscore():
    feed = Lightcone(streams={"A": [make_bar()]}, config=CLOSE_ONLY)
    bar, _, _ = feed.next_bar()
    # The obvious bypass MUST fail
    with pytest.raises(AttributeError):
        bar._bar
    with pytest.raises(AttributeError):
        bar._allowed
    with pytest.raises(AttributeError):
        bar._extras_allowed


def test_cannot_chain_underscore_bypass():
    feed = Lightcone(streams={"A": [make_bar()]}, config=CLOSE_ONLY)
    bar, _, _ = feed.next_bar()
    # This is the attack: view._bar.high to read undeclared field
    with pytest.raises(AttributeError):
        bar._bar.high
    # Even getattr() with default is blocked because we raise AttributeError
    assert getattr(bar, "_bar", "blocked") == "blocked"


def test_repr_still_works():
    feed = Lightcone(streams={"A": [make_bar()]}, config=CLOSE_ONLY)
    bar, _, _ = feed.next_bar()
    r = repr(bar)
    assert "BarView" in r
    assert "close" in r
    # repr MUST NOT leak undeclared fields
    assert "high" not in r
    assert "11.0" not in r


def test_class_lookup_still_works():
    feed = Lightcone(streams={"A": [make_bar()]}, config=CLOSE_ONLY)
    bar, _, _ = feed.next_bar()
    from lightcone import BarView
    assert isinstance(bar, BarView)
    assert bar.__class__ is BarView


def test_undeclared_raises_field_not_declared_not_attribute_error():
    """hasattr() catches AttributeError. FieldNotDeclared inherits Exception,
    not AttributeError, so accidental hasattr() guards do NOT silently hide
    the bug."""
    feed = Lightcone(streams={"A": [make_bar()]}, config=CLOSE_ONLY)
    bar, _, _ = feed.next_bar()
    with pytest.raises(FieldNotDeclared):
        bar.high
    # hasattr swallows AttributeError but NOT FieldNotDeclared:
    with pytest.raises(FieldNotDeclared):
        hasattr(bar, "high")


def test_setting_underscore_attr_blocked():
    feed = Lightcone(streams={"A": [make_bar()]}, config=CLOSE_ONLY)
    bar, _, _ = feed.next_bar()
    with pytest.raises(AttributeError):
        bar._bar = "tampered"
    with pytest.raises(AttributeError):
        bar.close = 999.0


def test_strictly_ascending_ts_within_stream():
    """Duplicate timestamps in same stream are a data integrity issue."""
    b1 = Bar(ts=1000, open=1, high=2, low=0.5, close=1.5, volume=10)
    b2 = Bar(ts=1000, open=1, high=2, low=0.5, close=1.5, volume=10)  # same ts!
    with pytest.raises(ValueError, match="strictly ascending"):
        Lightcone(streams={"A": [b1, b2]})
