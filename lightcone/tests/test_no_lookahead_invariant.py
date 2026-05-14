"""The core invariant: adding future bars MUST NOT change past outputs.

If we run the feed twice — once with N bars and once with N+M bars — the
output sequence for the first N bars must be byte-identical (modulo the
random token bytes, which we strip before comparison).

This is the empirical proof of lookahead absence.
"""
from lightcone import Lightcone, Bar, OHLCV


def bar(ts, close):
    return Bar(ts=ts, open=close - 0.1, high=close + 0.5, low=close - 0.5, close=close, volume=10.0)


def consume_strip_tokens(feed):
    """Run feed, return [(ts, key, close)] — tokens stripped."""
    out = []
    for view, key, token in feed:
        out.append((view.ts, key, view.close))
        feed.confirm(token)
    return out


def test_prefix_invariance_single_stream():
    """Run feed on bars[0..N] and bars[0..N+M]. First N outputs identical."""
    bars = [bar(1000 + i * 1000, 100.0 + i) for i in range(50)]

    feed_short = Lightcone(streams={"A": bars[:30]}, config=OHLCV)
    feed_long  = Lightcone(streams={"A": bars[:50]}, config=OHLCV)

    out_short = consume_strip_tokens(feed_short)
    out_long_first_30 = consume_strip_tokens(feed_long)[:30]

    assert out_short == out_long_first_30


def test_prefix_invariance_multi_stream():
    """Same invariant must hold across multiple streams."""
    a = [bar(1000 + i * 1000, 100.0 + i) for i in range(20)]
    b = [bar(1500 + i * 1000, 200.0 + i) for i in range(20)]

    feed_short = Lightcone(streams={"A": a[:10], "B": b[:10]}, config=OHLCV)
    feed_long  = Lightcone(streams={"A": a[:20], "B": b[:20]}, config=OHLCV)

    out_short = consume_strip_tokens(feed_short)
    # First 20 bars from the long feed
    out_long_first_20 = consume_strip_tokens(feed_long)[:20]
    assert out_short == out_long_first_20


def test_field_values_immutable_across_runs():
    """No matter how many bars we add ahead, bar(i)'s value is the same."""
    base = [bar(1000 + i * 1000, 100.0 + i * 1.5) for i in range(100)]

    for cutoff in [10, 25, 50, 75, 100]:
        feed = Lightcone(streams={"A": base[:cutoff]}, config=OHLCV)
        seen = consume_strip_tokens(feed)
        # bar 5's close is always 100 + 5*1.5 = 107.5, no matter how many bars follow
        if cutoff > 5:
            assert seen[5] == (6000, "A", 107.5)


def test_no_state_leak_between_feeds():
    """Two feeds with same data must produce identical outputs."""
    bars = [bar(1000 + i * 1000, 100.0 + i) for i in range(20)]
    feed_a = Lightcone(streams={"A": bars}, config=OHLCV)
    feed_b = Lightcone(streams={"A": bars}, config=OHLCV)
    assert consume_strip_tokens(feed_a) == consume_strip_tokens(feed_b)


def test_view_does_not_capture_future_state():
    """If we hold a BarView reference, its values must NOT mutate when we advance."""
    bars = [bar(1000 + i * 1000, 100.0 + i) for i in range(5)]
    feed = Lightcone(streams={"A": bars}, config=OHLCV)

    view1, _, t1 = feed.next_bar()
    captured_close = view1.close
    captured_ts = view1.ts
    feed.confirm(t1)

    # Advance several more bars
    for _ in range(3):
        _, _, t = feed.next_bar()
        feed.confirm(t)

    # view1 should still show bar 0's data, not the latest bar's data
    assert view1.close == captured_close
    assert view1.ts == captured_ts
    assert view1.close == 100.0
    assert view1.ts == 1000
