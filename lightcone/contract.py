"""Strict state-machine + token validation.

Enforces: every yielded bar MUST be acknowledged via confirm(token)
before another bar can be requested.

This is the lookahead-prevention mechanism. If your strategy
accidentally tries to peek at bar N+1 without finishing bar N,
the feed refuses — the future literally does not exist until
the present is acknowledged.
"""
from __future__ import annotations
import secrets
from enum import Enum
from typing import Optional

from .exceptions import NotConfirmed, BadToken


class State(Enum):
    READY = "ready"
    AWAITING_CONFIRM = "awaiting_confirm"


class Contract:
    """State machine for one feed.

    Owns the protocol state and the opaque token for the pending bar.
    Separated from the feed so the same enforcement logic can be reused
    by sub-feeds or live wrappers.
    """
    def __init__(self) -> None:
        self._state: State = State.READY
        self._pending_token: Optional[bytes] = None

    @property
    def state(self) -> State:
        return self._state

    def issue_token(self) -> bytes:
        """Issue a token for a bar about to be yielded.

        Raises NotConfirmed if a prior bar is still pending.
        """
        if self._state is not State.READY:
            raise NotConfirmed(
                "Cannot request next bar while previous bar is pending confirmation. "
                "Call feed.confirm(token) before requesting the next bar."
            )
        token = secrets.token_bytes(16)
        self._pending_token = token
        self._state = State.AWAITING_CONFIRM
        return token

    def confirm(self, token: bytes) -> None:
        """Acknowledge processing of the pending bar.

        Raises BadToken if `token` does not match the pending token, or
        if no bar is currently pending.
        """
        if self._state is not State.AWAITING_CONFIRM:
            raise BadToken("confirm() called but no bar is pending")
        if not isinstance(token, (bytes, bytearray)) or len(token) != 16:
            raise BadToken("token must be 16 bytes")
        # Constant-time comparison — not strictly required for correctness
        # (tokens are random + internal-only) but cheap defense-in-depth.
        if not secrets.compare_digest(bytes(token), self._pending_token):
            raise BadToken("token does not match the pending bar")
        self._pending_token = None
        self._state = State.READY
