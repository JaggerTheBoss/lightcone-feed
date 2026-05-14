"""Time-priority queue tests.

Bars across multiple streams must always emerge in strict timestamp order.
Ties broken deterministically by insertion order.
"""
import pytest

from lightcone import Lightcone, Bar, OHLCV
from lightcone.exceptions import FeedExhausted


def bar(ts: int) -> Bar:
    return Bar(ts=ts, open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0)


def consume(feed):
    """Run through the feed, return [(ts, key)] list of order seen."""
    out = []
    for view, key, token in feed:
        out.append((view.ts, key))
        feed.confirm(token)
    return out


def test_single_stream_emerges_in_order():
    bars = [bar(1000), bar(2000), bar(3000)]
    feed = Lightcone(streams={"A": bars}, config=OHLCV)
    out = consume(feed)
    assert out == [(1000, "A"), (2000, "A"), (3000, "A")]


def test_two_streams_interleave_by_timestamp():
    a = [bar(1000), bar(3000), bar(5000)]
    b = [bar(2000), bar(4000), bar(6000)]
    feed = Lightcone(streams={"A": a, "B": b}, config=OHLCV)
    out = consume(feed)
    assert out == [(1000, "A"), (2000, "B"), (3000, "A"),
                   (4000, "B"), (5000, "A"), (6000, "B")]


def test_three_streams_strict_ordering():
    a = [bar(1000), bar(5000), bar(9000)]
    b = [bar(2000), bar(6000)]
    c = [bar(3000), bar(4000), bar(7000), bar(8000)]
    feed = Lightcone(streams={"A": a, "B": b, "C": c}, config=OHLCV)
    out = consume(feed)
    timestamps = [t for t, _ in out]
    assert timestamps == sorted(timestamps)
    assert len(out) == 9


def test_ties_broken_deterministically_by_insertion_order():
    """Same ts across two streams → first inserted wins."""
    a = [bar(1000)]
    b = [bar(1000)]
    feed_ab = Lightcone(streams={"A": a, "B": b}, config=OHLCV)
    feed_ba = Lightcone(streams={"B": b, "A": a}, config=OHLCV)
    out_ab = consume(feed_ab)
    out_ba = consume(feed_ba)
    # Each ordering is deterministic, even if the two differ from each other.
    assert out_ab[0][1] == "A"  # A was first in dict
    assert out_ba[0][1] == "B"  # B was first in dict
    # Both should consume both bars
    assert len(out_ab) == 2 and len(out_ba) == 2


def test_unsorted_stream_rejected_at_construction():
    bars = [bar(2000), bar(1000)]  # out of order!
    with pytest.raises(ValueError, match="strictly ascending"):
        Lightcone(streams={"A": bars}, config=OHLCV)


def test_empty_stream_dict_rejected():
    with pytest.raises(ValueError, match="at least one stream"):
        Lightcone(streams={}, config=OHLCV)


def test_one_empty_stream_alongside_nonempty():
    a = [bar(1000), bar(2000)]
    feed = Lightcone(streams={"A": a, "B": []}, config=OHLCV)
    out = consume(feed)
    assert out == [(1000, "A"), (2000, "A")]


def test_all_empty_streams_immediate_exhaustion():
    feed = Lightcone(streams={"A": [], "B": []}, config=OHLCV)
    with pytest.raises(FeedExhausted):
        feed.next_bar()


def test_uneven_stream_lengths():
    a = [bar(1000), bar(4000), bar(7000)]
    b = [bar(2000)]
    c = [bar(3000), bar(5000), bar(6000), bar(8000)]
    feed = Lightcone(streams={"A": a, "B": b, "C": c}, config=OHLCV)
    out = consume(feed)
    assert [t for t, _ in out] == [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000]


def test_many_streams_strict_order():
    """50 streams × 100 bars each, all randomly timestamped. Must come out sorted."""
    import random
    rng = random.Random(42)
    streams = {}
    all_ts = []
    for s in range(50):
        ts_list = sorted(rng.sample(range(1_000_000), 100))
        streams[f"S{s}"] = [bar(t) for t in ts_list]
        all_ts.extend(ts_list)
    feed = Lightcone(streams=streams, config=OHLCV)
    out = consume(feed)
    assert len(out) == len(all_ts)
    assert [t for t, _ in out] == sorted(all_ts)
