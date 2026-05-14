"""Lightcone — the strict-ordering bar feed.

Rule: only the past light cone can influence the present.

Mechanism:
  1. Bars are yielded one at a time in strict timestamp order.
  2. Each yield returns an opaque token. The strategy MUST call
     confirm(token) before requesting the next bar.
  3. The yielded bar is wrapped in a BarView that exposes ONLY the
     fields declared in LightconeConfig.bar_fields. Accidental
     access to undeclared fields raises FieldNotDeclared.

Same API for backtest and live. The only thing that changes is the
data source feeding the constructor.
"""
from __future__ import annotations
from typing import Hashable, Iterator, Mapping, Sequence, Tuple

from .bar import Bar, BarView
from .config import LightconeConfig, OHLCV
from .contract import Contract
from .exceptions import FeedExhausted
from .timeline import Timeline


class Lightcone:
    """Strict-ordering bar feed for backtests and live strategies.

    Usage:
        feed = Lightcone(
            streams={("BTC", "5m"): btc_bars, ("ETH", "5m"): eth_bars},
            config=OHLCV,
        )
        while True:
            try:
                bar, key, token = feed.next_bar()
            except FeedExhausted:
                break
            # ... process bar ...
            feed.confirm(token)
    """
    def __init__(
        self,
        streams: Mapping[Hashable, Sequence[Bar]],
        config: LightconeConfig = OHLCV,
    ) -> None:
        if not streams:
            raise ValueError("Lightcone requires at least one stream")
        self._timeline = Timeline(streams)
        self._config = config
        self._contract = Contract()
        self._bars_yielded = 0
        self._bars_confirmed = 0

    @property
    def config(self) -> LightconeConfig:
        return self._config

    @property
    def stats(self) -> dict:
        return {
            "yielded": self._bars_yielded,
            "confirmed": self._bars_confirmed,
            "pending": self._bars_yielded - self._bars_confirmed,
            "state": self._contract.state.value,
        }

    def next_bar(self) -> Tuple[BarView, Hashable, bytes]:
        """Yield the next bar in strict timestamp order.

        Raises:
            NotConfirmed: if a prior bar has not been acknowledged via confirm().
            FeedExhausted: if no more bars are available.
        """
        if self._timeline.is_empty():
            raise FeedExhausted("No more bars available across any stream")
        # token issuance enforces NotConfirmed before we even touch the timeline
        token = self._contract.issue_token()
        bar, key = self._timeline.pop_next()
        view = BarView(bar, self._config.bar_fields, self._config.extras)
        self._bars_yielded += 1
        return view, key, token

    def confirm(self, token: bytes) -> None:
        """Acknowledge processing of the pending bar so the next one can be requested."""
        self._contract.confirm(token)
        self._bars_confirmed += 1

    def __iter__(self) -> Iterator[Tuple[BarView, Hashable, bytes]]:
        """NOTE: iterating still requires confirm() inside the loop body.

        This iterator does NOT auto-confirm — that would defeat the entire
        point. If you forget to confirm, the next iteration will raise.
        """
        while True:
            try:
                yield self.next_bar()
            except FeedExhausted:
                return


def from_ohlcv_rows(
    rows_by_stream: Mapping[Hashable, Sequence[Sequence]],
    config: LightconeConfig = OHLCV,
) -> Lightcone:
    """Convenience constructor from Binance/HL-style [ts,o,h,l,c,v,...] rows."""
    streams = {
        key: [Bar.from_ohlcv_row(row) for row in rows]
        for key, rows in rows_by_stream.items()
    }
    return Lightcone(streams=streams, config=config)
