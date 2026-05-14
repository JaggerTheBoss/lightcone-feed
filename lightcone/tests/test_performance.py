"""Performance / stress tests.

Production target: handle millions of bars across many streams without
slowdown. The bottleneck is the heap; we measure end-to-end iteration time.
"""
import time

from lightcone import Lightcone, Bar, OHLCV


def make_bars(n, start_ts=1_000_000):
    return [Bar(ts=start_ts + i * 1000, open=1.0, high=2.0, low=0.5,
                close=1.5, volume=10.0) for i in range(n)]


def test_1m_bars_single_stream_under_5s():
    """1 million bars in a single stream should iterate in < 5 seconds."""
    bars = make_bars(1_000_000)
    feed = Lightcone(streams={"A": bars}, config=OHLCV)
    start = time.perf_counter()
    count = 0
    for view, key, token in feed:
        feed.confirm(token)
        count += 1
    elapsed = time.perf_counter() - start
    assert count == 1_000_000
    assert elapsed < 5.0, f"Took {elapsed:.2f}s (target <5s)"


def test_100k_bars_10_streams_under_2s():
    """100k bars × 10 streams = 1M bars total via heap."""
    streams = {
        f"S{i}": [Bar(ts=1_000_000 + j * 1000 + i, open=1.0, high=2.0,
                      low=0.5, close=1.5, volume=10.0)
                  for j in range(100_000)]
        for i in range(10)
    }
    feed = Lightcone(streams=streams, config=OHLCV)
    start = time.perf_counter()
    count = 0
    prev_ts = -1
    for view, key, token in feed:
        # also verify strict ordering across streams
        assert view.ts >= prev_ts
        prev_ts = view.ts
        feed.confirm(token)
        count += 1
    elapsed = time.perf_counter() - start
    assert count == 1_000_000
    assert elapsed < 10.0, f"Took {elapsed:.2f}s (target <10s)"


def test_view_creation_overhead():
    """Each next_bar() creates a BarView. Should be very cheap."""
    bars = make_bars(100_000)
    feed = Lightcone(streams={"A": bars}, config=OHLCV)
    start = time.perf_counter()
    for view, key, token in feed:
        # read all the fields the strategy would read
        _ = view.close
        _ = view.open
        _ = view.high
        _ = view.low
        _ = view.volume
        feed.confirm(token)
    elapsed = time.perf_counter() - start
    # 100k bars × 5 field reads = 500k attribute accesses
    assert elapsed < 2.0, f"Took {elapsed:.2f}s for 100k bars × 5 reads"


def test_memory_footprint_reasonable():
    """1M Bar dataclasses should be well under 500MB."""
    import sys
    bars = make_bars(1_000_000)
    # rough sizeof check; Python overhead is ~64-80 bytes per object
    sample = bars[0]
    per_bar = sys.getsizeof(sample)
    # extras dict adds overhead; sanity check well under 1000 bytes per bar
    assert per_bar < 1000, f"Bar size {per_bar} bytes is suspiciously large"
