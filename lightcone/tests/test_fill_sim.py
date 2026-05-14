"""Fill simulator tests — separate code path that DOES see full OHLC."""
import pytest

from lightcone import Bar, Order, Fill, Side, OrderType, simulate_fill


def bar(o, h, l, c):
    return Bar(ts=1_000_000, open=o, high=h, low=l, close=c, volume=10.0)


def test_market_buy_fills_at_open():
    b = bar(100.0, 105.0, 95.0, 102.0)
    f = simulate_fill(Order(Side.BUY, 1.0, OrderType.MARKET), b)
    assert f is not None
    assert f.price == 100.0


def test_market_sell_fills_at_open():
    b = bar(100.0, 105.0, 95.0, 102.0)
    f = simulate_fill(Order(Side.SELL, 1.0, OrderType.MARKET), b)
    assert f.price == 100.0


def test_market_slippage_applied():
    b = bar(100.0, 105.0, 95.0, 102.0)
    f = simulate_fill(Order(Side.BUY, 1.0, OrderType.MARKET), b, slippage_bps=10)
    assert f.price == pytest.approx(100.1)  # 100 * 1.001


def test_buy_limit_fills_when_low_below_limit():
    b = bar(100.0, 105.0, 95.0, 102.0)
    f = simulate_fill(Order(Side.BUY, 1.0, OrderType.LIMIT, price=97.0), b)
    assert f is not None
    assert f.price == 97.0


def test_buy_limit_no_fill_when_low_above_limit():
    b = bar(100.0, 105.0, 95.0, 102.0)
    f = simulate_fill(Order(Side.BUY, 1.0, OrderType.LIMIT, price=90.0), b)
    assert f is None


def test_buy_limit_fills_at_open_when_open_below_limit():
    """Marketable limit: open already below limit → fill at open, not limit."""
    b = bar(96.0, 100.0, 95.0, 99.0)
    f = simulate_fill(Order(Side.BUY, 1.0, OrderType.LIMIT, price=97.0), b)
    assert f.price == 96.0  # better than 97 (limit)


def test_sell_limit_fills_when_high_above_limit():
    b = bar(100.0, 105.0, 95.0, 102.0)
    f = simulate_fill(Order(Side.SELL, 1.0, OrderType.LIMIT, price=103.0), b)
    assert f is not None
    assert f.price == 103.0


def test_sell_limit_no_fill_when_high_below_limit():
    b = bar(100.0, 105.0, 95.0, 102.0)
    f = simulate_fill(Order(Side.SELL, 1.0, OrderType.LIMIT, price=110.0), b)
    assert f is None


def test_buy_stop_fills_when_high_above_stop():
    b = bar(100.0, 110.0, 95.0, 102.0)
    f = simulate_fill(Order(Side.BUY, 1.0, OrderType.STOP, price=105.0), b)
    assert f is not None
    assert f.price == 105.0


def test_buy_stop_no_fill_when_high_below_stop():
    b = bar(100.0, 105.0, 95.0, 102.0)
    f = simulate_fill(Order(Side.BUY, 1.0, OrderType.STOP, price=110.0), b)
    assert f is None


def test_sell_stop_fills_when_low_below_stop():
    b = bar(100.0, 105.0, 90.0, 102.0)
    f = simulate_fill(Order(Side.SELL, 1.0, OrderType.STOP, price=92.0), b)
    assert f is not None


def test_stop_with_gap_open_fills_at_open():
    """Buy stop @ 105, but bar opens at 110 (gap up) → fill at 110."""
    b = bar(110.0, 115.0, 109.0, 112.0)
    f = simulate_fill(Order(Side.BUY, 1.0, OrderType.STOP, price=105.0), b)
    assert f.price == 110.0


def test_limit_without_price_raises():
    b = bar(100.0, 105.0, 95.0, 102.0)
    with pytest.raises(ValueError, match="requires a price"):
        simulate_fill(Order(Side.BUY, 1.0, OrderType.LIMIT, price=None), b)
