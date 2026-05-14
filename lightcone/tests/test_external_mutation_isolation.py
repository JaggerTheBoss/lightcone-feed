"""External mutation of input data must not affect feed output.

If the caller mutates their bar list AFTER constructing the feed, the
feed should still produce the original sequence. Otherwise an attacker
(or just a buggy caller) could leak future state into past views.
"""
from lightcone import Lightcone, Bar, OHLCV


def make(ts, c):
    return Bar(ts=ts, open=c - 0.1, high=c + 0.1, low=c - 0.2, close=c, volume=10)


def test_mutating_caller_list_does_not_affect_feed():
    bars = [make(1000, 100.0), make(2000, 101.0), make(3000, 102.0)]
    feed = Lightcone(streams={"A": bars}, config=OHLCV)
    # Mutate caller's list
    bars[1] = make(2000, 999.0)
    bars.append(make(4000, 9999.0))
    # Feed still produces ORIGINAL sequence
    seq = []
    for view, _, t in feed:
        seq.append(view.close)
        feed.confirm(t)
    assert seq == [100.0, 101.0, 102.0]


def test_clearing_caller_list_does_not_affect_feed():
    bars = [make(1000, 100.0), make(2000, 101.0)]
    feed = Lightcone(streams={"A": bars}, config=OHLCV)
    bars.clear()  # caller wipes the list
    seq = []
    for view, _, t in feed:
        seq.append(view.close)
        feed.confirm(t)
    assert seq == [100.0, 101.0]


def test_mutating_outer_dict_does_not_affect_feed():
    streams = {"A": [make(1000, 100.0), make(2000, 101.0)]}
    feed = Lightcone(streams=streams, config=OHLCV)
    streams.pop("A")
    streams["A"] = [make(1000, 999.0)]  # replace
    seq = []
    for view, _, t in feed:
        seq.append(view.close)
        feed.confirm(t)
    assert seq == [100.0, 101.0]
