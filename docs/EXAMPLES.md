# Examples & Recipes

Concrete patterns for common strategy shapes. Copy + adapt.

---

## 1. Minimal backtest (single asset, close-only)

```python
from lightcone import Lightcone, Bar, CLOSE_ONLY, FeedExhausted

bars = [
    Bar(ts=1000, open=100, high=101, low=99, close=100.5, volume=10),
    Bar(ts=2000, open=100.5, high=102, low=100, close=101.5, volume=12),
    # ...
]

feed = Lightcone(streams={"BTC": bars}, config=CLOSE_ONLY)
bankroll = 1000.0
position = 0  # +1 long, -1 short, 0 flat
last_close = None

while True:
    try:
        view, key, token = feed.next_bar()
    except FeedExhausted:
        break

    if last_close is not None:
        # If we had a position, settle P&L using this bar's close vs last
        if position != 0:
            bankroll += position * (view.close - last_close) * 10  # toy size

    # Decide for next bar
    position = 1 if view.close > (last_close or 0) else -1

    last_close = view.close
    feed.confirm(token)

print(f"Final bankroll: ${bankroll:.2f}")
```

---

## 2. Multi-asset prediction market backtest

```python
from lightcone import Lightcone, Bar, OHLCV, FeedExhausted
import uuid

feed = Lightcone(
    streams={
        ("BTC", "5m"): btc_bars,
        ("ETH", "5m"): eth_bars,
        ("BTC", "15m"): btc_15m_bars,
    },
    config=OHLCV,
)

# Track open prediction bets. Each entry: bet_id -> (resolves_at_ts, asset, direction, stake)
pending_bets = {}
bankroll = 1000.0

while True:
    try:
        view, key, token = feed.next_bar()
    except FeedExhausted:
        break

    asset, timeframe = key
    bar_duration_ms = 300_000 if timeframe == "5m" else 900_000

    # 1. Resolve any pending bets that resolve at THIS bar's close
    for bet_id in list(pending_bets):
        bet = pending_bets[bet_id]
        if bet["resolves_at_ts"] == view.ts and bet["asset"] == asset:
            # Win = bar closed in predicted direction
            close_above_open = view.close >= view.open
            won = (bet["direction"] == 1 and close_above_open) or \
                  (bet["direction"] == -1 and not close_above_open)
            if won:
                bankroll += bet["stake"] * 0.92    # ~92% payout
            else:
                bankroll -= bet["stake"]
            del pending_bets[bet_id]

    # 2. Compute signal for NEXT bar (using only past + current bar info)
    signal = my_model.predict(asset, timeframe, view.close, view.volume)
    if signal is not None:
        direction = 1 if signal > 0.55 else (-1 if signal < 0.45 else 0)
        if direction != 0:
            pending_bets[uuid.uuid4().hex] = {
                "resolves_at_ts": view.ts + bar_duration_ms,
                "asset": asset,
                "direction": direction,
                "stake": min(bankroll * 0.05, 50),  # 5% Kelly, capped
            }

    feed.confirm(token)

print(f"Bankroll: ${bankroll:.2f}, open bets: {len(pending_bets)}")
```

---

## 3. Limit-order spot strategy with fill simulator

```python
from lightcone import (
    Lightcone, Bar, OHLCV,
    Order, Side, OrderType, simulate_fill,
)

feed = Lightcone(streams={"BTC": bars}, config=OHLCV)

position_qty = 0.0
cash = 10_000.0
pending_orders = []

# CAUTION: simulate_fill takes a raw Bar, not a BarView. To bridge them,
# we'd ideally rework the feed to expose a fill-sim hook. For now, attach
# the raw bar list to a side-channel keyed by ts (NOT used by strategy
# decision logic, only by fill simulator).
raw_lookup = {b.ts: b for b in bars}

while True:
    try:
        view, _, token = feed.next_bar()
    except FeedExhausted:
        break

    raw_bar = raw_lookup[view.ts]   # for fill sim only

    # Resolve pending orders against this bar
    still_pending = []
    for order in pending_orders:
        fill = simulate_fill(order, raw_bar, slippage_bps=2)
        if fill:
            if fill.side == Side.BUY:
                cash -= fill.qty * fill.price
                position_qty += fill.qty
            else:
                cash += fill.qty * fill.price
                position_qty -= fill.qty
        else:
            still_pending.append(order)
    pending_orders = still_pending

    # Decide: only use view (declared fields), not raw_bar
    if view.close > 100 and position_qty == 0:
        pending_orders.append(Order(Side.BUY, 1.0, OrderType.LIMIT, price=view.close - 0.5))

    feed.confirm(token)
```

**Important caveat**: the fill simulator needs the bar's full OHLC range, but the strategy must not. The side-channel `raw_lookup` is a workaround. A cleaner pattern is to wire `simulate_fill` directly via the feed in a future helper.

---

## 4. Stateful streaming feature engine

The model needs features that accumulate over time. Build state incrementally:

```python
from collections import deque
from lightcone import Lightcone, OHLCV, FeedExhausted
import numpy as np

class StreamingFeatures:
    def __init__(self, lookback=200):
        self.closes = deque(maxlen=lookback)
        self.volumes = deque(maxlen=lookback)

    def update(self, view):
        self.closes.append(view.close)
        self.volumes.append(view.volume)

    def current(self):
        if len(self.closes) < 20:
            return None
        c = np.array(self.closes)
        v = np.array(self.volumes)
        return {
            "rsi_14":     compute_rsi(c, 14),
            "ema_20":     c[-20:].mean(),
            "vol_z":      (v[-1] - v.mean()) / v.std(),
            "ret_5":      (c[-1] - c[-5]) / c[-5],
        }


feat = StreamingFeatures()
feed = Lightcone(streams={"BTC": bars}, config=OHLCV)

while True:
    try:
        view, _, token = feed.next_bar()
    except FeedExhausted:
        break

    feat.update(view)
    f = feat.current()
    if f is not None:
        decide(f)
    feed.confirm(token)
```

The feature engine sees one bar at a time, in order. No way to peek ahead.

---

## 5. Walk-forward training + lightcone-mediated inference

Models train on history (full timeline allowed), then run inference through lightcone (strict ordering enforced).

```python
from lightcone import Lightcone, OHLCV
from sklearn.linear_model import LogisticRegression

# OFFLINE: training is allowed to look ahead, because labels live at bar i+1
X_train, y_train = build_features_and_labels(train_bars)  # full batch
model = LogisticRegression().fit(X_train, y_train)

# INFERENCE: through lightcone, bar by bar, no lookahead
feed = Lightcone(streams={"BTC": test_bars}, config=OHLCV)
feat_engine = StreamingFeatures()

decisions = []
while True:
    try:
        view, _, token = feed.next_bar()
    except FeedExhausted:
        break
    feat_engine.update(view)
    f = feat_engine.current()
    if f is not None:
        p = model.predict_proba([list(f.values())])[0, 1]
        decisions.append({"ts": view.ts, "p": float(p)})
    feed.confirm(token)
```

The split is:
- **Training** uses the full timeline (offline, batch, look-ahead OK)
- **Inference** uses lightcone (online, strict, no look-ahead)

This is the same separation that exists in production: you train a model once, then deploy it; the deployed model only sees one bar at a time.

---

## 6. Resolving lagged outcomes (Polymarket-style)

Polymarket UP/DOWN markets settle on the next bar's close. Make a prediction at bar i, log it as "pending", resolve when bar i+1 arrives.

```python
from lightcone import Lightcone, OHLCV, FeedExhausted
import uuid

feed = Lightcone(streams={"BTC": bars}, config=OHLCV)

pending = {}     # bet_id -> {resolves_at_ts, direction, stake}
wins = losses = 0

while True:
    try:
        view, _, token = feed.next_bar()
    except FeedExhausted:
        break

    # First, resolve any bets whose resolution bar is THIS bar
    for bet_id in list(pending):
        bet = pending[bet_id]
        if bet["resolves_at_ts"] == view.ts:
            won = (view.close > view.open) == (bet["direction"] == 1)
            wins += int(won); losses += int(not won)
            del pending[bet_id]

    # Then, place new bets for the NEXT bar
    if my_signal_says_long(view):
        pending[uuid.uuid4().hex] = {
            "resolves_at_ts": view.ts + 300_000,   # 5m later
            "direction": 1, "stake": 50.0,
        }

    feed.confirm(token)

print(f"WR: {wins / (wins+losses) * 100:.1f}%")
```

---

## 7. Random sanity test: prefix invariance

Convince yourself nothing in your pipeline leaks the future:

```python
def collect(bars):
    feed = Lightcone(streams={"A": bars}, config=OHLCV)
    out = []
    feat = StreamingFeatures()
    while True:
        try:
            view, _, t = feed.next_bar()
        except FeedExhausted: break
        feat.update(view)
        out.append(feat.current())
        feed.confirm(t)
    return out

short = collect(bars[:1000])
long  = collect(bars[:2000])

assert short == long[:1000], "Feature engine has lookahead!"
```

If the assertion holds for arbitrary cutoffs, your pipeline is lookahead-free for *those* features. (Necessary but not sufficient — see ARCHITECTURE.md for why prefix invariance can have false passes for buffer-reference bugs.)

---

## Common pitfalls

| Pitfall | Symptom | Fix |
|---|---|---|
| Forgot `confirm()` inside loop | `NotConfirmed` on second iteration | Always call `feed.confirm(token)` before requesting next bar |
| Accessing undeclared field | `FieldNotDeclared` | Add the field to your `LightconeConfig` |
| Holding view past confirm and expecting it to update | View values stay frozen at issuance | Build fresh features each bar |
| Trying `view._bar` to bypass restriction | `AttributeError` | Declare the field properly |
| Bar list has duplicate timestamps | `ValueError: not strictly ascending` | De-duplicate at the data layer |
| Strategy reads from an external bar list alongside the feed | Backtest passes, live fails | Read from the view only |
