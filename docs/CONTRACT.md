# The Contract

This is the protocol every consumer of lightcone MUST follow. It is short on purpose. If you understand and honor these rules, lookahead is impossible.

---

## Rule 1: One bar at a time

You request bars via `feed.next_bar()`. The feed returns exactly one bar per call. You cannot request the next bar until the current one is finished.

```python
view, key, token = feed.next_bar()    # got bar i
view2, _, _ = feed.next_bar()         # NotConfirmed — you haven't finished i yet
```

## Rule 2: You must confirm before requesting more

Each call to `next_bar()` returns a random 16-byte `token`. Pass it back via `feed.confirm(token)` to acknowledge that you have finished processing the bar. Only then can you request the next one.

```python
view, key, token = feed.next_bar()    # got bar i
# ... process view ...
feed.confirm(token)                    # done with i
view2, _, t2 = feed.next_bar()        # now bar i+1 is available
```

## Rule 3: Tokens are single-use

Each token is generated fresh, randomly, and consumed when `confirm()` succeeds. You cannot:

- reuse a token for a later bar
- confirm with a stale token from an earlier bar
- confirm without having requested a bar
- send a token you fabricated

Each of these raises `BadToken`.

## Rule 4: You read only declared fields

When constructing the feed you provide a `LightconeConfig` (or use a preset). The config declares which bar fields your strategy is permitted to read. Any access to an undeclared field raises `FieldNotDeclared`:

```python
feed = Lightcone(streams=..., config=CLOSE_ONLY)
view, _, _ = feed.next_bar()
view.close   # OK
view.high    # FieldNotDeclared — CLOSE_ONLY didn't declare it
```

`ts` is always readable regardless of config. The current time is always knowable.

## Rule 5: Views are read-only and frozen

A `BarView` returned by `next_bar()` is a read-only proxy. You cannot:

- write to its fields (`view.close = 999.0` raises)
- access its underlying bar object (`view._bar` raises)
- mutate it in any way

Holding a view past `confirm()` is safe — its values are frozen at the moment the bar was issued.

## Rule 6: Streams are immutable after construction

The `streams` mapping you pass to `Lightcone(...)` is snapshotted internally as immutable tuples. Mutating the caller-side list after construction has no effect on the feed.

## Rule 7: One bar's timestamp must be strictly greater than the previous bar's in the same stream

Within a single stream, every bar must have `ts > prev.ts`. Duplicate timestamps are rejected at construction. Across streams, timestamps may overlap or duplicate freely — they are tie-broken deterministically by insertion order.

---

## What the contract gives you

If you follow these seven rules:

1. **Your backtest cannot look ahead.** Bar i+1 literally does not exist until you confirm bar i.
2. **Your backtest and live runs use the same code path.** Only the feed source differs.
3. **Accidental future-peeking via undeclared fields is caught loudly,** not silently.
4. **External mutation cannot leak into past views.** Data isolation is structural.
5. **Protocol violations are fatal**, not silent. Mistakes show up as exceptions, not subtle wrong results.

## What the contract does NOT give you

- **It does not protect you from yourself if you keep external bar lists alongside the feed.** If your strategy code reads from `original_bars[i+1]` instead of `view`, you have bypassed the contract. Don't.
- **It does not enforce no-lookahead in training.** Model training is offline batch work that legitimately uses the full timeline. The contract applies to **inference** — backtest decisions and live decisions.
- **It is not a sandbox.** A determined caller can introspect the feed's internal `_timeline._streams` and read all bars. The contract catches accidents, not adversaries.

## In one sentence

Receive a bar → process it using only declared fields → confirm it → receive the next one.
