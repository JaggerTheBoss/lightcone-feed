"""Time-priority queue over multiple streams.

When the feed has multiple streams (e.g., BTC 5m + ETH 5m + BTC 15m),
this heap delivers bars in strict timestamp order regardless of
which stream they came from. Ties broken by insertion order for
deterministic replay.
"""
from __future__ import annotations
import heapq
import itertools
from typing import Any, Hashable, List, Mapping, Sequence, Tuple

from .bar import Bar


class Timeline:
    """Heap-backed multi-stream iterator. Strict timestamp ordering.

    Not a public class — used internally by Lightcone. The feed asks
    `pop_next()` for the next-in-time bar across all streams.
    """
    def __init__(self, streams: Mapping[Hashable, Sequence[Bar]]) -> None:
        # Validate each stream is strictly ascending by ts. Duplicate
        # timestamps in the same stream are a data integrity issue.
        for key, bars in streams.items():
            if not bars:
                continue
            prev = bars[0].ts
            for b in bars[1:]:
                if b.ts <= prev:
                    raise ValueError(
                        f"Stream {key!r} is not strictly ascending by ts "
                        f"(got {b.ts} after {prev})"
                    )
                prev = b.ts

        # tiebreaker so heap is fully deterministic without comparing Bar
        self._counter = itertools.count()
        # heap items: (ts, tiebreaker, key, idx)
        self._heap: List[Tuple[int, int, Any, int]] = []
        # Snapshot the streams to tuples so external mutation of the caller's
        # list cannot leak future state into past views.
        self._streams = {k: tuple(v) for k, v in streams.items()}
        for key, bars in self._streams.items():
            if bars:
                heapq.heappush(
                    self._heap,
                    (bars[0].ts, next(self._counter), key, 0),
                )

    def is_empty(self) -> bool:
        return not self._heap

    def pop_next(self) -> Tuple[Bar, Hashable]:
        """Pop the earliest-timestamp bar and queue this stream's next."""
        if not self._heap:
            raise StopIteration
        ts, _tb, key, idx = heapq.heappop(self._heap)
        bar = self._streams[key][idx]
        nxt = idx + 1
        if nxt < len(self._streams[key]):
            heapq.heappush(
                self._heap,
                (self._streams[key][nxt].ts, next(self._counter), key, nxt),
            )
        return bar, key
