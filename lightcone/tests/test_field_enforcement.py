"""BarView field-restriction tests.

Strategy declares which bar fields it will use. The view exposes only those.
Accidental access to undeclared fields raises FieldNotDeclared — this
catches debug code that accidentally peeks at high/low when the strategy
claimed it only uses close.
"""
import pytest

from lightcone import Lightcone, Bar, CLOSE_ONLY, OHLCV, FULL_TAPE, custom
from lightcone.exceptions import FieldNotDeclared


def make_bar(**kw):
    defaults = dict(ts=1_000_000, open=10.0, high=11.0, low=9.0, close=10.5, volume=100.0, n_trades=42, taker_buy=55.0)
    defaults.update(kw)
    return Bar(**defaults)


def test_close_only_exposes_close_and_ts():
    feed = Lightcone(streams={"A": [make_bar()]}, config=CLOSE_ONLY)
    bar, _, token = feed.next_bar()
    assert bar.close == 10.5
    assert bar.ts == 1_000_000


def test_close_only_hides_open_high_low():
    feed = Lightcone(streams={"A": [make_bar()]}, config=CLOSE_ONLY)
    bar, _, _ = feed.next_bar()
    with pytest.raises(FieldNotDeclared):
        bar.open
    with pytest.raises(FieldNotDeclared):
        bar.high
    with pytest.raises(FieldNotDeclared):
        bar.low


def test_close_only_hides_volume_and_microstructure():
    feed = Lightcone(streams={"A": [make_bar()]}, config=CLOSE_ONLY)
    bar, _, _ = feed.next_bar()
    with pytest.raises(FieldNotDeclared):
        bar.volume
    with pytest.raises(FieldNotDeclared):
        bar.n_trades
    with pytest.raises(FieldNotDeclared):
        bar.taker_buy


def test_ohlcv_exposes_all_basic_fields():
    feed = Lightcone(streams={"A": [make_bar()]}, config=OHLCV)
    bar, _, _ = feed.next_bar()
    assert bar.open == 10.0
    assert bar.high == 11.0
    assert bar.low == 9.0
    assert bar.close == 10.5
    assert bar.volume == 100.0


def test_ohlcv_hides_microstructure_fields():
    feed = Lightcone(streams={"A": [make_bar()]}, config=OHLCV)
    bar, _, _ = feed.next_bar()
    with pytest.raises(FieldNotDeclared):
        bar.n_trades
    with pytest.raises(FieldNotDeclared):
        bar.taker_buy


def test_full_tape_exposes_microstructure():
    feed = Lightcone(streams={"A": [make_bar()]}, config=FULL_TAPE)
    bar, _, _ = feed.next_bar()
    assert bar.n_trades == 42
    assert bar.taker_buy == 55.0


def test_custom_config_only_declared_fields():
    cfg = custom("close", "volume")
    feed = Lightcone(streams={"A": [make_bar()]}, config=cfg)
    bar, _, _ = feed.next_bar()
    assert bar.close == 10.5
    assert bar.volume == 100.0
    with pytest.raises(FieldNotDeclared):
        bar.open
    with pytest.raises(FieldNotDeclared):
        bar.high


def test_view_is_read_only():
    feed = Lightcone(streams={"A": [make_bar()]}, config=OHLCV)
    bar, _, _ = feed.next_bar()
    with pytest.raises(AttributeError):
        bar.close = 999.0


def test_unknown_field_in_config_rejected_at_construction():
    from lightcone import LightconeConfig
    with pytest.raises(ValueError, match="Unknown bar fields"):
        LightconeConfig(bar_fields=frozenset({"nonexistent", "close"}))


def test_extras_field_access():
    """Bars with extras dict + extras declared in config → accessible."""
    bar = Bar(ts=1_000_000, open=1.0, high=2.0, low=0.5, close=1.5,
              extras={"funding_rate": 0.0001})
    from lightcone import LightconeConfig
    cfg = LightconeConfig(bar_fields=frozenset({"close"}), extras=frozenset({"funding_rate"}))
    feed = Lightcone(streams={"A": [bar]}, config=cfg)
    view, _, _ = feed.next_bar()
    assert view.funding_rate == 0.0001


def test_extras_field_blocked_when_not_declared():
    bar = Bar(ts=1_000_000, open=1.0, high=2.0, low=0.5, close=1.5,
              extras={"funding_rate": 0.0001})
    feed = Lightcone(streams={"A": [bar]}, config=CLOSE_ONLY)
    view, _, _ = feed.next_bar()
    with pytest.raises(FieldNotDeclared):
        view.funding_rate


def test_undeclared_field_lookup_message_helpful():
    feed = Lightcone(streams={"A": [make_bar()]}, config=CLOSE_ONLY)
    bar, _, _ = feed.next_bar()
    with pytest.raises(FieldNotDeclared) as exc:
        bar.high
    msg = str(exc.value)
    assert "'high'" in msg
    assert "Declared" in msg
