"""State machine + token validation invariants.

These tests prove the structural lookahead prevention works.
"""
import pytest

from lightcone import Lightcone, Bar, OHLCV
from lightcone.exceptions import NotConfirmed, BadToken, FeedExhausted


def make_bars(n, start_ts=1_000_000):
    return [Bar(ts=start_ts + i * 1000, open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0) for i in range(n)]


def test_first_call_succeeds():
    feed = Lightcone(streams={"A": make_bars(3)}, config=OHLCV)
    bar, key, token = feed.next_bar()
    assert isinstance(token, bytes) and len(token) == 16
    assert key == "A"
    assert bar.close == 1.5


def test_two_consecutive_next_bar_without_confirm_raises():
    feed = Lightcone(streams={"A": make_bars(3)}, config=OHLCV)
    feed.next_bar()
    with pytest.raises(NotConfirmed):
        feed.next_bar()


def test_confirm_with_wrong_token_raises():
    feed = Lightcone(streams={"A": make_bars(3)}, config=OHLCV)
    _, _, _real = feed.next_bar()
    fake = b"\x00" * 16
    with pytest.raises(BadToken):
        feed.confirm(fake)


def test_confirm_without_pending_bar_raises():
    feed = Lightcone(streams={"A": make_bars(3)}, config=OHLCV)
    with pytest.raises(BadToken):
        feed.confirm(b"\x00" * 16)


def test_confirm_with_correct_token_advances():
    feed = Lightcone(streams={"A": make_bars(3)}, config=OHLCV)
    _, _, t1 = feed.next_bar()
    feed.confirm(t1)
    bar2, _, t2 = feed.next_bar()
    assert t2 != t1, "tokens must be unique per bar"
    assert bar2.ts > 0
    feed.confirm(t2)


def test_double_confirm_same_token_raises():
    feed = Lightcone(streams={"A": make_bars(3)}, config=OHLCV)
    _, _, t = feed.next_bar()
    feed.confirm(t)
    with pytest.raises(BadToken):
        feed.confirm(t)  # second confirm with same token — already used


def test_stale_token_from_prior_bar_raises():
    feed = Lightcone(streams={"A": make_bars(3)}, config=OHLCV)
    _, _, t1 = feed.next_bar()
    feed.confirm(t1)
    _, _, t2 = feed.next_bar()  # pending
    with pytest.raises(BadToken):
        feed.confirm(t1)  # using OLD token for new pending bar


def test_feed_exhausted_after_all_bars():
    feed = Lightcone(streams={"A": make_bars(2)}, config=OHLCV)
    _, _, t1 = feed.next_bar(); feed.confirm(t1)
    _, _, t2 = feed.next_bar(); feed.confirm(t2)
    with pytest.raises(FeedExhausted):
        feed.next_bar()


def test_non_bytes_token_raises():
    feed = Lightcone(streams={"A": make_bars(3)}, config=OHLCV)
    feed.next_bar()
    with pytest.raises(BadToken):
        feed.confirm("not bytes")  # type: ignore


def test_wrong_length_token_raises():
    feed = Lightcone(streams={"A": make_bars(3)}, config=OHLCV)
    feed.next_bar()
    with pytest.raises(BadToken):
        feed.confirm(b"\x00" * 8)  # too short


def test_stats_tracking():
    feed = Lightcone(streams={"A": make_bars(3)}, config=OHLCV)
    assert feed.stats == {"yielded": 0, "confirmed": 0, "pending": 0, "state": "ready"}
    _, _, t = feed.next_bar()
    assert feed.stats["yielded"] == 1
    assert feed.stats["pending"] == 1
    assert feed.stats["state"] == "awaiting_confirm"
    feed.confirm(t)
    assert feed.stats["confirmed"] == 1
    assert feed.stats["pending"] == 0
    assert feed.stats["state"] == "ready"


def test_iter_requires_confirm_inside_body():
    """Iterating without confirming should fail on second iteration."""
    feed = Lightcone(streams={"A": make_bars(3)}, config=OHLCV)
    it = iter(feed)
    next(it)  # got bar 1, did not confirm
    with pytest.raises(NotConfirmed):
        next(it)


def test_iter_works_with_confirm():
    feed = Lightcone(streams={"A": make_bars(3)}, config=OHLCV)
    count = 0
    for bar, key, token in feed:
        feed.confirm(token)
        count += 1
    assert count == 3
