"""Integration test using realistic OHLCV data.

Validates the package end-to-end on realistic-shape data with proper OHLC
relationships (high >= low, etc.), not just trivial synthetic fixtures.
"""
import random

import pytest

from lightcone import Lightcone, Bar, OHLCV, CLOSE_ONLY, FULL_TAPE, from_ohlcv_rows
from lightcone.exceptions import FieldNotDeclared


def _make_realistic_ohlcv(n_bars: int = 1000, seed: int = 7):
    """Build n bars of realistic OHLCV-shaped data with proper invariants."""
    rng = random.Random(seed)
    rows = []
    price = 50_000.0
    ts = 1_700_000_000_000
    for _ in range(n_bars):
        o = price
        c = o * (1 + rng.gauss(0, 0.002))
        spread = abs(c - o) * (1 + rng.random())
        h = max(o, c) + spread * rng.random()
        l = min(o, c) - spread * rng.random()
        v = abs(rng.gauss(100, 30)) + 10
        n_trades = int(v * 50)
        taker_buy = v * rng.uniform(0.3, 0.7)
        rows.append([str(ts), str(o), str(h), str(l), str(c), str(v),
                     str(ts + 299_999), "0", str(n_trades), str(taker_buy), "0", "0"])
        ts += 300_000
        price = c
    return rows


def test_realistic_ohlcv_round_trip():
    raw = _make_realistic_ohlcv(n_bars=2000)
    feed = from_ohlcv_rows({"BTC": raw}, config=OHLCV)
    count = 0
    prev_ts = -1
    for view, key, token in feed:
        assert view.ts > prev_ts
        assert view.high >= view.low
        assert view.high >= view.open
        assert view.high >= view.close
        assert view.low <= view.open
        assert view.low <= view.close
        assert view.volume > 0
        prev_ts = view.ts
        feed.confirm(token)
        count += 1
    assert count == 2000


def test_multi_asset_realistic():
    btc = _make_realistic_ohlcv(n_bars=500, seed=1)
    eth = _make_realistic_ohlcv(n_bars=500, seed=2)
    feed = from_ohlcv_rows({"BTC": btc, "ETH": eth}, config=OHLCV)
    prev_ts = -1
    btc_count = eth_count = 0
    for view, key, token in feed:
        assert view.ts >= prev_ts
        prev_ts = view.ts
        if key == "BTC": btc_count += 1
        else: eth_count += 1
        feed.confirm(token)
    assert btc_count == 500
    assert eth_count == 500


def test_close_only_blocks_open_on_realistic_data():
    raw = _make_realistic_ohlcv(n_bars=10)
    feed = from_ohlcv_rows({"BTC": raw}, config=CLOSE_ONLY)
    view, _, token = feed.next_bar()
    assert view.close > 0
    with pytest.raises(FieldNotDeclared):
        view.open
    feed.confirm(token)


def test_full_tape_exposes_microstructure():
    raw = _make_realistic_ohlcv(n_bars=10)
    feed = from_ohlcv_rows({"BTC": raw}, config=FULL_TAPE)
    view, _, token = feed.next_bar()
    assert view.taker_buy >= 0
    assert view.n_trades >= 0
    feed.confirm(token)


def test_no_lookahead_invariant_on_realistic_data():
    """Adding more future bars MUST NOT change past outputs."""
    raw = _make_realistic_ohlcv(n_bars=5000)
    short_count = 1000

    feed_short = from_ohlcv_rows({"BTC": raw[:short_count]}, config=OHLCV)
    feed_long  = from_ohlcv_rows({"BTC": raw[:5000]}, config=OHLCV)

    short_out = []
    for view, key, token in feed_short:
        short_out.append((view.ts, view.open, view.high, view.low, view.close, view.volume))
        feed_short.confirm(token)

    long_out_prefix = []
    for view, key, token in feed_long:
        long_out_prefix.append((view.ts, view.open, view.high, view.low, view.close, view.volume))
        feed_long.confirm(token)
        if len(long_out_prefix) == short_count:
            break

    assert short_out == long_out_prefix
