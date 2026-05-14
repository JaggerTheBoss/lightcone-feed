"""Adversarial tests — try to break the feed.

Each test simulates a way someone might accidentally (or deliberately)
violate the contract. Each should raise loudly or behave correctly.
"""
import pytest

from lightcone import Lightcone, Bar, OHLCV, CLOSE_ONLY, from_ohlcv_rows
from lightcone.exceptions import (
    NotConfirmed, BadToken, FieldNotDeclared, FeedExhausted,
)


def make_bars(n, start_ts=1_000_000):
    return [Bar(ts=start_ts + i * 1000, open=1.0, high=2.0, low=0.5,
                close=1.5, volume=10.0) for i in range(n)]


def test_view_remains_valid_after_feed_exhausted():
    """Holding a view past feed exhaustion: should still work."""
    feed = Lightcone(streams={"A": make_bars(2)}, config=OHLCV)
    view1, _, t1 = feed.next_bar()
    feed.confirm(t1)
    view2, _, t2 = feed.next_bar()
    feed.confirm(t2)
    with pytest.raises(FeedExhausted):
        feed.next_bar()
    # Held views still readable
    assert view1.close == 1.5
    assert view2.close == 1.5


def test_view_held_across_advancement_does_not_mutate():
    """Critical lookahead-prevention property."""
    bars = [Bar(ts=1000 + i * 1000, open=i, high=i + 1, low=i - 1,
                close=i + 0.5, volume=10) for i in range(10)]
    feed = Lightcone(streams={"A": bars}, config=OHLCV)
    view0, _, t0 = feed.next_bar()
    captured = (view0.ts, view0.open, view0.high, view0.low, view0.close)
    feed.confirm(t0)
    # Advance several bars; view0's values must remain frozen
    for _ in range(5):
        _, _, t = feed.next_bar()
        feed.confirm(t)
    assert (view0.ts, view0.open, view0.high, view0.low, view0.close) == captured


def test_binance_string_format_rows():
    """Real Binance JSON has string-typed numbers."""
    rows = [
        ["1000000", "50000.0", "50100.0", "49900.0", "50050.0", "1.5", "1000300", "75000", "10", "0.8", "40000", "0"],
        ["1300000", "50050.0", "50200.0", "50000.0", "50150.0", "2.0", "1600300", "100000", "15", "1.2", "60000", "0"],
    ]
    feed = from_ohlcv_rows({"BTC": rows}, config=OHLCV)
    view, _, t = feed.next_bar()
    assert view.ts == 1_000_000
    assert view.open == 50000.0
    assert view.close == 50050.0
    feed.confirm(t)


def test_tuple_stream_keys():
    """Real strategies use tuple keys like (asset, timeframe)."""
    bars = make_bars(5)
    feed = Lightcone(streams={("BTC", "5m"): bars, ("ETH", "5m"): bars[:3]},
                    config=OHLCV)
    keys_seen = []
    for view, key, token in feed:
        keys_seen.append(key)
        feed.confirm(token)
    assert ("BTC", "5m") in keys_seen
    assert ("ETH", "5m") in keys_seen


def test_nan_values_pass_through():
    """If the data is bad, NaN propagates — that's the strategy's problem,
    not the feed's. Don't silently clean it up."""
    import math
    bars = [Bar(ts=1000, open=math.nan, high=math.nan, low=math.nan,
                close=math.nan, volume=0.0)]
    feed = Lightcone(streams={"A": bars}, config=OHLCV)
    view, _, t = feed.next_bar()
    assert math.isnan(view.close)
    feed.confirm(t)


def test_negative_prices_pass_through():
    """Some markets do have negative prices (oil futures, etc.) — pass through."""
    bars = [Bar(ts=1000, open=-10.0, high=5.0, low=-50.0, close=-20.0, volume=100.0)]
    feed = Lightcone(streams={"A": bars}, config=OHLCV)
    view, _, t = feed.next_bar()
    assert view.close == -20.0
    feed.confirm(t)


def test_two_feeds_are_independent():
    """Mistakenly using one feed's token on another → BadToken."""
    feed_a = Lightcone(streams={"A": make_bars(3)}, config=OHLCV)
    feed_b = Lightcone(streams={"B": make_bars(3)}, config=OHLCV)
    _, _, tok_a = feed_a.next_bar()
    _, _, tok_b = feed_b.next_bar()
    with pytest.raises(BadToken):
        feed_a.confirm(tok_b)
    with pytest.raises(BadToken):
        feed_b.confirm(tok_a)


def test_view_is_not_hashable_by_default_but_does_not_crash():
    """BarView has no __hash__ defined; identity hash is used."""
    feed = Lightcone(streams={"A": make_bars(2)}, config=OHLCV)
    view, _, t = feed.next_bar()
    # Should not crash; id-based hash
    h = hash(view)
    assert isinstance(h, int)
    feed.confirm(t)


def test_decimals_preserved_in_ohlcv():
    """Critical for crypto where prices have 8 decimals."""
    bars = [Bar(ts=1000, open=0.123456789, high=0.123456800, low=0.123456700,
                close=0.123456789, volume=1000000.0)]
    feed = Lightcone(streams={"A": bars}, config=OHLCV)
    view, _, t = feed.next_bar()
    assert view.close == 0.123456789
    assert view.open == 0.123456789
    feed.confirm(t)


def test_repr_does_not_leak_undeclared_fields():
    """repr is debug-friendly but must NOT show undeclared fields,
    since debug prints could otherwise smuggle the future into a log."""
    bars = [Bar(ts=1000, open=999.0, high=1000.0, low=998.0,
                close=999.5, volume=10.0)]
    feed = Lightcone(streams={"A": bars}, config=CLOSE_ONLY)
    view, _, t = feed.next_bar()
    r = repr(view)
    assert "999.5" in r           # close IS declared
    assert "999.0" not in r       # open is NOT — must not appear
    assert "1000.0" not in r      # high is NOT
    assert "998.0" not in r       # low is NOT
    feed.confirm(t)


def test_strict_ordering_with_large_random_ts():
    """Random timestamps across 100 streams must still come out sorted."""
    import random
    rng = random.Random(7)
    streams = {}
    for s in range(100):
        ts_set = sorted(rng.sample(range(0, 10_000_000), 50))
        streams[f"S{s}"] = [Bar(ts=t, open=1, high=2, low=0.5, close=1.5, volume=10)
                            for t in ts_set]
    feed = Lightcone(streams=streams, config=OHLCV)
    prev_ts = -1
    n = 0
    for view, _, t in feed:
        assert view.ts >= prev_ts
        prev_ts = view.ts
        feed.confirm(t)
        n += 1
    assert n == 100 * 50


def test_double_iteration_safe():
    """Two for-loops on the same feed should not behave weirdly."""
    feed = Lightcone(streams={"A": make_bars(3)}, config=OHLCV)
    seen_first = 0
    for view, _, t in feed:
        feed.confirm(t)
        seen_first += 1
    # Second iteration: feed is exhausted, iterator returns immediately
    seen_second = 0
    for _ in feed:
        seen_second += 1
    assert seen_first == 3
    assert seen_second == 0
