"""Lightcone protocol violations.

These should NEVER occur in correctly-written strategy code. Each one indicates
a contract bug, not a runtime failure to handle.
"""


class LightconeError(Exception):
    """Base for all lightcone protocol violations."""


class NotConfirmed(LightconeError):
    """Called next_bar() while a previously yielded bar was not yet confirmed.

    Fix: every bar yielded by the feed MUST be acknowledged via confirm(token)
    before another bar can be requested.
    """


class BadToken(LightconeError):
    """confirm(token) received a token that does not match the pending bar.

    Indicates one of:
      - confirming with a stale token from a previous bar
      - tampering with the token
      - confirming when no bar is pending
    """


class FieldNotDeclared(LightconeError):
    """Strategy accessed a bar field that was not in LightconeConfig.bar_fields.

    Catches accidental future-peeking: if your strategy claims it only uses
    close, but somewhere a debug line reads bar.high, that's silently broken
    in live (the high isn't known yet at decision time). This exception makes
    that bug loud.
    """


class FeedExhausted(LightconeError):
    """No more bars available across any stream."""
