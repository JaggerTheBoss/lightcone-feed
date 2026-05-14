# Wiring lightcone to live data

The package does not include a live-data wrapper yet — but the protocol is designed to swap in a live feed transparently. This document shows the pattern.

---

## The core insight

`Lightcone` is a thin orchestrator around three components:

1. A **source** of bars — currently `Timeline` (in-memory queue of pre-loaded bars)
2. A **contract** (state machine + tokens)
3. A **config** (which fields are exposed)

Only the source changes between backtest and live. Everything else — the strategy code, the contract, the BarView field restrictions — stays identical.

---

## Pattern: subclass Lightcone, override the source

```python
import asyncio
import queue
import threading
from typing import Hashable, Tuple

from lightcone import Lightcone, Bar, BarView, LightconeConfig, OHLCV
from lightcone.contract import Contract
from lightcone.exceptions import FeedExhausted


class LiveLightcone:
    """Same protocol as Lightcone, but bars arrive over the wire.

    `next_bar()` blocks until the data source pushes the next bar.
    """
    def __init__(self, config: LightconeConfig = OHLCV, queue_maxsize: int = 1000):
        self._config = config
        self._contract = Contract()
        self._queue: queue.Queue = queue.Queue(maxsize=queue_maxsize)
        self._closed = False

    # --- producer side (call this from your WebSocket handler) ---
    def push_bar(self, bar: Bar, key: Hashable) -> None:
        """Called by the data source when a new closed bar arrives."""
        if self._closed:
            return
        self._queue.put((bar, key))

    def close(self) -> None:
        """Signal end-of-stream. next_bar() will raise FeedExhausted
        after the queue drains."""
        self._closed = True
        # sentinel to wake any blocked consumer
        self._queue.put((None, None))

    # --- consumer side (same API as Lightcone) ---
    @property
    def config(self) -> LightconeConfig:
        return self._config

    def next_bar(self) -> Tuple[BarView, Hashable, bytes]:
        token = self._contract.issue_token()
        bar, key = self._queue.get()  # blocks until producer pushes
        if bar is None:
            raise FeedExhausted("Stream closed by producer")
        view = BarView(bar, self._config.bar_fields, self._config.extras)
        return view, key, token

    def confirm(self, token: bytes) -> None:
        self._contract.confirm(token)
```

The strategy code that worked against `Lightcone` will work against `LiveLightcone` without modification.

---

## Wiring a WebSocket source

Sketch for Hyperliquid / Binance / Bybit-style WebSocket candle streams:

```python
import json
import threading
import websocket    # pip install websocket-client

from lightcone import Bar


def run_live_strategy():
    feed = LiveLightcone(config=OHLCV)
    threading.Thread(target=run_ws_pump, args=(feed,), daemon=True).start()
    # Hand the feed to your strategy — identical to backtest code path
    my_strategy.run(feed)


def run_ws_pump(feed: LiveLightcone):
    def on_message(ws, message):
        payload = json.loads(message)
        # ... parse your venue's format ...
        if payload.get("type") == "candle_closed":
            c = payload["candle"]
            bar = Bar(
                ts=int(c["close_ts_ms"]),
                open=float(c["open"]),
                high=float(c["high"]),
                low=float(c["low"]),
                close=float(c["close"]),
                volume=float(c["volume"]),
            )
            feed.push_bar(bar, key=(c["asset"], c["timeframe"]))

    def on_close(ws, *_):
        feed.close()

    ws = websocket.WebSocketApp(
        "wss://your-exchange/ws/candles",
        on_message=on_message,
        on_close=on_close,
    )
    ws.run_forever()
```

---

## Reconciliation: live vs backtest must produce same outputs

The point of lightcone is that backtest and live use the same code path. To verify:

```python
# 1. Run backtest over the last 24h of historical bars
hist_bars = load_last_24h(asset="BTC", timeframe="5m")
backtest_feed = Lightcone(streams={"BTC": hist_bars}, config=OHLCV)
backtest_decisions = run_strategy(backtest_feed)

# 2. In the live wrapper, replay those same bars
replay_feed = LiveLightcone(config=OHLCV)
for bar in hist_bars:
    replay_feed.push_bar(bar, key="BTC")
replay_feed.close()
live_decisions = run_strategy(replay_feed)

# 3. Compare
assert backtest_decisions == live_decisions, "Live and backtest diverged!"
```

If this assertion ever fails, you have a path divergence between live and backtest. Fix it before deploying.

---

## Operational concerns for the live wrapper

- **Bar timestamp drift**: WebSocket data may arrive seconds after the bar actually closes. Strategy code should use the *bar's* ts, never `time.time()`. lightcone enforces this because `ts` comes from the Bar, not the consumer's clock.
- **Reconnects**: when the WebSocket reconnects, you may receive a gap or a backfill burst. Decide explicitly: skip the gap (and possibly miss signals), or backfill via REST then resume WebSocket. Document the choice.
- **Out-of-order arrivals**: if a slow message arrives after a faster one, the timeline may want to enforce strict ordering. The simplest live wrapper above does NOT enforce this (it processes in arrival order). If your WebSocket source is reliable, this is fine. If not, buffer briefly and reorder before pushing.
- **Backpressure**: if the strategy is slow and bars pile up in the queue, `push_bar` will block when the queue fills. This is usually correct — better to fall behind than to drop bars silently. But surface it as a metric.
- **Confirmation latency**: the strategy must call `confirm()` before the next bar's close, or the queue will grow. For 5m bars this is ample. For sub-second strategies, watch carefully.

---

## What's NOT in this doc

- A production-grade `LiveLightcone` implementation. The sketch above is a starting point.
- WebSocket reconnect logic, heartbeats, auth, etc. — venue-specific.
- Persistence of the strategy's pending state across restarts. Handle this in your strategy code, not in the feed.

When the live wrapper is built and stabilized, it will live in `lightcone/live.py` and be exported from the package's public API.
