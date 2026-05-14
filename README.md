# lightcone

**Strict-ordering bar feed for backtests and live trading strategies.**
**Lookahead-proof by construction.**

*Only the past light cone influences the present.*

[![tests](https://github.com/JaggerTheBoss/lightcone-feed/actions/workflows/test.yml/badge.svg)](https://github.com/JaggerTheBoss/lightcone-feed/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)
[![Zero dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen)](pyproject.toml)

---

## Why this exists

Every major Python backtest framework has known lookahead pitfalls. The classic failure mode: each bar's "scene" / "context" object holds references to mutable state. Future bars mutate that state. By the time your trading loop reads `bars[10].scene.zone.broken`, the value reflects bars 11..N — your trading decision read the future.

Tests can catch *known* lookahead patterns. They cannot catch the unknown ones.

The structural approach: **make it impossible for the strategy to see a bar before it has confirmed processing all earlier bars.** Then lookahead bugs are not testable failures — they are architectural impossibilities.

That's lightcone.

## How it works

1. Bars are delivered **one at a time** through a feed.
2. Each delivery returns an opaque **token**. The strategy MUST call `confirm(token)` before requesting the next bar.
3. Each bar is wrapped in a **BarView** that exposes only the fields the strategy declared in advance.
4. Backtest and live use the **same API**. Only the data source changes.

## Install

```bash
pip install lightcone-feed
```

Zero dependencies. Python 3.9+.

## Quick start

```python
from lightcone import Lightcone, OHLCV, FeedExhausted, from_ohlcv_rows

# Build a feed from Binance/HL-style OHLCV rows
feed = from_ohlcv_rows(
    {("BTC", "5m"): btc_rows, ("ETH", "5m"): eth_rows},
    config=OHLCV,
)

while True:
    try:
        bar, key, token = feed.next_bar()
    except FeedExhausted:
        break

    # Your strategy reads only declared fields
    if bar.close > bar.open and bar.volume > some_threshold:
        decide_long(asset=key, ts=bar.ts)

    feed.confirm(token)   # ← MUST call before requesting next bar
```

Try to peek at a field you didn't declare → `FieldNotDeclared`. Try to skip `confirm()` and request the next bar → `NotConfirmed`. Try to confirm with the wrong token → `BadToken`.

## Configuration profiles

```python
from lightcone import CLOSE_ONLY, OHLCV, FULL_TAPE, custom

CLOSE_ONLY   # → ts + close. Discretionary / human-trader replay.
OHLCV        # → ts + OHLCV. Standard algorithmic backtest.
FULL_TAPE    # → OHLCV + n_trades + taker_buy. Microstructure.

cfg = custom("close", "volume", "n_trades")
cfg = custom("close", extras=["funding_rate"])
```

## Multi-asset / multi-timeframe

```python
feed = Lightcone(streams={
    ("BTC", "5m"):  btc_5m,
    ("BTC", "15m"): btc_15m,
    ("ETH", "5m"):  eth_5m,
})
```

Bars across all streams come out in strict timestamp order via a min-heap, with deterministic tie-breaking. Same API for one stream or fifty.

## Fill simulation (for limit / stop strategies)

```python
from lightcone import Order, Side, OrderType, simulate_fill

fill = simulate_fill(
    Order(Side.BUY, qty=1.0, order_type=OrderType.LIMIT, price=97.0),
    bar,
    slippage_bps=2.0,
)
```

The fill simulator reads the bar's full OHLC range — that's separate from the strategy's declared-field view, so your decision logic can't peek at high/low while the fill logic still uses them realistically.

## Hardening

- Bars are frozen dataclasses; immutable post-construction
- `Bar.extras` is auto-frozen via `MappingProxyType` (external mutation can't leak in)
- `BarView` blocks all underscore-prefixed access — no `view._bar.high` escape hatch
- `FieldNotDeclared` does NOT inherit from `AttributeError`, so `hasattr()` cannot silently swallow it
- Tokens are 16 random bytes, compared with `secrets.compare_digest`
- Stream sequences are snapshotted to tuples — caller mutation can't affect the feed
- Strictly ascending timestamps required within each stream

## Performance

| Workload | Throughput |
|---|---|
| 1M bars, single stream | ~400k bars/sec |
| 1M bars, 10 streams via heap | ~370k bars/sec |
| Per-bar overhead | ~2.5 microseconds |
| Memory | ~80 bytes / Bar |

The feed will never be your bottleneck. Strategy logic dominates by 10-100x.

## What lightcone is NOT

- **Not a full backtest framework.** It's the data layer. Your strategy code, P&L tracking, and reporting live outside.
- **Not thread-safe.** Single-threaded use only. If parallelizing, give each thread its own feed.
- **Not a training pipeline.** Model training is offline batch work that uses the full timeline. Use lightcone for inference (backtest and live).
- **Not a sandbox.** A determined caller can read the feed's internal state. The contract catches accidents, not adversaries.

## Documentation

| Doc | Read it for |
|---|---|
| [`docs/CONTRACT.md`](docs/CONTRACT.md) | The seven protocol rules. Read first. |
| [`docs/API.md`](docs/API.md) | Reference for every public symbol. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Why the package is designed the way it is. |
| [`docs/EXAMPLES.md`](docs/EXAMPLES.md) | Backtest, multi-asset, fill sim, walk-forward recipes. |
| [`docs/LIVE.md`](docs/LIVE.md) | Wiring lightcone to a live WebSocket data source. |

## Testing

```bash
pip install -e ".[dev]"
pytest lightcone/tests/
```

95 tests, ~14s runtime, 100% line coverage on production modules.

## License

Apache-2.0. See [LICENSE](LICENSE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). lightcone is small and focused — read that first.
