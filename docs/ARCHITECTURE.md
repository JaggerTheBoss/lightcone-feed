# Architecture

This document explains *why* lightcone is designed the way it is. The design decisions are all consequences of one observation: **lookahead bugs in backtests are sneaky, expensive, and hard to detect after the fact.** Build the system so they can't happen.

---

## The originating problem

A common backtest pattern is:

1. Load all historical bars upfront
2. Iterate through them, calling `strategy.decide(bar_i)` at each step
3. Track P&L

This looks innocent. It hides bugs of the form:

```python
bars = load_all_bars()              # all bars loaded into memory
features = compute_features(bars)   # ← does this peek at future bars?
for i in range(len(bars)):
    decision = strategy.decide(features[i])
    pnl += simulate_pnl(decision, bars[i:i+5])   # next 5 bars used for fill
```

Subtle problems:

- `compute_features` might look 1 bar ahead by mistake (e.g., `rolling(window=20).mean()` centered instead of trailing).
- The strategy might hold a reference to a "scene" or "context" object that mutates as future bars are processed (the v1_2_1_se_r `run_strategy` bug — see `src/hl/v1_2_1_se_r/docs/CASE_STUDY_lookahead_bug.md`).
- A debug `print(bar.close, bars[i+1].close)` left in code silently uses the future.
- Reading from a global cache that was populated after-the-fact.

A passing backtest with hidden lookahead is the worst possible outcome: looks profitable in testing, blows up in live. Months of effort wasted, sometimes real money lost.

---

## The design principle: structural prevention, not testing

Tests can catch *known* lookahead patterns. They cannot catch lookahead patterns nobody thought to test for.

The structural approach: **make it impossible for the strategy to see a bar before it has confirmed processing all earlier bars.** Then lookahead bugs are not testable failures, they are architectural impossibilities.

This is the rationale for every major design decision:

| Decision | Why |
|---|---|
| One bar yielded per `next_bar()` call | The strategy literally cannot get bar i+1 until it has finished bar i |
| Random tokens required for `confirm()` | Confirming the wrong bar is detectable, not silent |
| `BarView` instead of raw `Bar` | The strategy can only see declared fields; accidental future peeks via "I'll just look at the next bar's open" become explicit failures |
| `__getattribute__` override blocking `_bar` access | No escape hatch via private attribute access |
| `MappingProxyType` for extras | External mutation of the bar's extras dict cannot leak into views |
| Tuple snapshot of input streams | Mutating the caller's list after construction does nothing |
| Strict ascending ts per stream | Data integrity violations caught at construction, not silently |

---

## Why not just deep-copy?

A common "fix" for the buffered-reference bug is to deep-copy every scene/context at yield time. This works but:

1. Deep-copy is slow — ~10-20x the per-bar cost.
2. It treats the symptom (mutable references), not the cause (buffered processing).
3. It doesn't help with the *other* lookahead patterns (centered rolling windows, debug peeks, ad-hoc caches).

The structural solution is cheaper and more general: don't allow the strategy to hold references it could later misuse.

---

## Why the token

A boolean `is_pending` flag would be enough to enforce "one bar at a time" sequencing. The random token adds two specific guarantees:

1. **You confirmed the right bar.** If you accidentally call `confirm(token)` with a stale token from a previous bar, the state machine catches it instead of silently advancing.
2. **You didn't forge a confirmation.** A buggy strategy can't fabricate `b"\x00" * 16` and bypass the check — `secrets.compare_digest` rejects mismatches.

Neither is required for correctness in a non-adversarial setting. They are defense-in-depth.

---

## Why the field declaration

Without `LightconeConfig`, a strategy could write:

```python
for view, _, t in feed:
    if view.high > my_threshold:    # silently uses high
        decide_long()
    feed.confirm(t)
```

That looks fine until you realize the strategy *claimed* to be a "close-only" strategy in its README, and now in live, the `high` of the current 5m bar isn't known until the bar closes — which is when the decision is supposed to be made. The backtest used the bar's eventual high; live can't.

By forcing the strategy to declare its inputs in advance and raising on any access outside those bounds, this bug becomes loud:

```python
feed = Lightcone(streams=..., config=CLOSE_ONLY)
for view, _, t in feed:
    if view.high > my_threshold:    # ← FieldNotDeclared
```

---

## Why ts is always allowed

Strategies need to know what time it is — to compute time-of-day features, to skip funding windows, to detect weekends. Hiding `ts` would force every strategy to declare it explicitly, with no upside. So `ts` is always available regardless of config.

---

## The time-priority heap

For multi-asset / multi-timeframe feeds, bars across different streams arrive at different timestamps. The feed must deliver them in strict timestamp order — that's what live looks like, and the backtest must match.

Implementation: a min-heap keyed by `(ts, tiebreaker, stream_key, idx)`. Each pop yields the earliest-ts bar across all streams. The tiebreaker is a monotonically increasing counter from `itertools.count()`, ensuring:

1. Two bars with the same ts come out in insertion order (deterministic replay).
2. The heap never needs to compare Bar objects directly (`Bar` is not `<` comparable).

This is `O(log N)` per pop, fast for any realistic backtest size.

---

## Live extension path

The live wrapper (not in this package yet) will be a thin subclass:

```python
class LiveLightcone(Lightcone):
    def __init__(self, ws_client, config):
        # don't load all bars upfront
        self._queue = queue.Queue()  # blocking
        self._contract = Contract()
        ws_client.on_close(lambda bar: self._queue.put(bar))

    def next_bar(self):
        token = self._contract.issue_token()
        bar, key = self._queue.get()   # blocks until next bar arrives
        view = BarView(bar, self._config.bar_fields, self._config.extras)
        return view, key, token

    def confirm(self, token):
        self._contract.confirm(token)
```

Same protocol, same `BarView`, same `Contract`. The strategy code is unchanged. **The data source is the only difference between backtest and live.** This is the property that makes lookahead-free backtests trustworthy: if the backtest passes and your strategy uses only feed outputs, live behaves identically.

---

## What lightcone deliberately does NOT do

- **Indicator computation, P&L tracking, order management, performance metrics.** These belong in the strategy or in higher-level framework code. lightcone is one layer: the data layer.
- **Training pipelines.** Model training is offline batch work that uses the full timeline (including labels at `bar[i+1]`). The contract applies to *inference*, not training.
- **Sandboxing or security.** A determined adversary can read `feed._timeline._streams` and access the full bar sequence. The contract catches accidents, not deliberate evasion.
- **Streaming from disk.** All bars are held in memory. For datasets bigger than RAM, build a generator-backed feed (not currently provided).

---

## When NOT to use lightcone

- Pure vectorized strategies (vectorbt, etc.) — they compute everything as numpy arrays at once and don't benefit from per-bar dispatch.
- Strategies that don't read OHLCV bars (e.g., orderbook-level strategies). Build a different protocol.
- Single-asset, single-bar backtests where the data layer doesn't need to be the load-bearing safety net.

For everything else — anywhere lookahead bugs would invalidate the result — use lightcone.
