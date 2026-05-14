# API Reference

Every public name exported from `lightcone`. Anything not listed here is internal.

---

## Feed

### `Lightcone(streams, config=OHLCV)`

The strict-ordering bar feed.

**Parameters**
- `streams: Mapping[Hashable, Sequence[Bar]]` — one or more named bar sequences. Keys are arbitrary hashables (e.g., `"BTC"`, `("BTC", "5m")`). Each sequence must be strictly ascending by `ts`.
- `config: LightconeConfig = OHLCV` — which fields the strategy is permitted to read.

**Raises**
- `ValueError` if `streams` is empty or any stream is not strictly ascending.

**Properties**
- `config: LightconeConfig` — the active config (read-only).
- `stats: dict` — `{"yielded": int, "confirmed": int, "pending": int, "state": str}`. Useful for debugging.

**Methods**
- `next_bar() -> Tuple[BarView, Hashable, bytes]`
  Returns the next bar in strict timestamp order across all streams. The tuple is `(view, stream_key, token)`. Raises `NotConfirmed` if a prior bar is still pending. Raises `FeedExhausted` if no bars remain.
- `confirm(token: bytes) -> None`
  Acknowledges the pending bar so the next one can be requested. Raises `BadToken` if the token does not match or no bar is pending.
- `__iter__() -> Iterator[Tuple[BarView, Hashable, bytes]]`
  Iterates by repeatedly calling `next_bar()`. You MUST call `confirm()` inside the loop body or the next iteration raises `NotConfirmed`.

### `from_ohlcv_rows(rows_by_stream, config=OHLCV) -> Lightcone`

Convenience constructor for Binance/HL-style OHLCV rows.

**Parameters**
- `rows_by_stream: Mapping[Hashable, Sequence[Sequence]]` — each value is a list of `[ts, open, high, low, close, volume, close_ts, quote_vol, n_trades, taker_buy, taker_quote, ignore]` rows. Strings are parsed automatically.

---

## Bar data

### `Bar`

Frozen dataclass representing one OHLCV bar.

**Fields**
- `ts: int` — close timestamp in milliseconds
- `open: float`
- `high: float`
- `low: float`
- `close: float`
- `volume: float = 0.0`
- `n_trades: int = 0`
- `taker_buy: float = 0.0`
- `extras: Mapping[str, Any] = {}` — venue-specific extras, auto-frozen via `MappingProxyType` at construction

**Class methods**
- `Bar.from_ohlcv_row(row) -> Bar` — build from `[ts, o, h, l, c, v, ...]`. Accepts strings or numerics.

### `BarView`

Field-restricted read-only proxy over a `Bar`. You never construct this directly — the feed returns it from `next_bar()`.

**Behavior**
- `view.<declared_field>` returns the underlying bar's value
- `view.<undeclared_field>` raises `FieldNotDeclared`
- `view._anything` raises `AttributeError` (private state is sealed)
- `view.<field> = X` raises `AttributeError` (read-only)
- `view.ts` always works regardless of config

---

## Config

### `LightconeConfig(bar_fields, extras=frozenset())`

Frozen dataclass declaring which fields are accessible through `BarView`.

**Parameters**
- `bar_fields: FrozenSet[str]` — names from `{ts, open, high, low, close, volume, n_trades, taker_buy}`. Unknown names raise `ValueError`.
- `extras: FrozenSet[str]` — opt-in access to keys inside `Bar.extras`.

### Preset configs

- `CLOSE_ONLY` — `{ts, close}`. Discretionary / human-trader replay style.
- `OHLCV` — `{ts, open, high, low, close, volume}`. Standard algorithmic backtest.
- `FULL_TAPE` — `{ts, open, high, low, close, volume, n_trades, taker_buy}`. Microstructure / order flow.

### `custom(*field_names: str, extras: Iterable[str] = ()) -> LightconeConfig`

Build a custom config from positional field names. Equivalent to `LightconeConfig(bar_fields=frozenset(names), extras=frozenset(extras))`.

```python
cfg = custom("close", "volume", "n_trades")
cfg = custom("close", extras=["funding_rate"])
```

---

## Exceptions

All inherit from `LightconeError`.

- `LightconeError` — base class
- `NotConfirmed` — `next_bar()` called while a prior bar is still pending confirmation
- `BadToken` — wrong, malformed, or missing token passed to `confirm()`
- `FieldNotDeclared` — accessed a bar field not listed in `config.bar_fields`. Does **not** inherit from `AttributeError`, so `hasattr()` cannot silently swallow it.
- `FeedExhausted` — no more bars available across any stream

---

## Fill simulation

For strategies that place limit/stop orders (perps, spot). Polymarket-style prediction strategies don't need this.

### `Order(side, qty, order_type, price=None)`

- `side: Side.BUY | Side.SELL`
- `qty: float`
- `order_type: OrderType.MARKET | OrderType.LIMIT | OrderType.STOP`
- `price: Optional[float]` — required for `LIMIT` and `STOP`

### `Fill(side, qty, price)`

Result of a successful fill.

### `simulate_fill(order, bar, slippage_bps=0.0) -> Optional[Fill]`

Determines whether an `Order` would fill against a `Bar`. Returns `Fill` or `None`.

Fill model:
- `MARKET` → fills at `bar.open ± slippage`
- `BUY LIMIT` → fills at `min(limit, open)` if `bar.low <= limit`
- `SELL LIMIT` → fills at `max(limit, open)` if `bar.high >= limit`
- `BUY STOP` → fills at `max(stop, open) * (1 + slip)` if `bar.high >= stop`
- `SELL STOP` → fills at `min(stop, open) * (1 - slip)` if `bar.low <= stop`

The fill simulator reads `bar.open/high/low` directly, bypassing the BarView. This is intentional: the strategy's decision logic must respect declared fields, but the fill model needs the bar's range to determine realistic outcomes.

---

## Enums

- `Side.BUY`, `Side.SELL`
- `OrderType.MARKET`, `OrderType.LIMIT`, `OrderType.STOP`
