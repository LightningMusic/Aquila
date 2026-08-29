"""
Project Aquila
=============

Log Formatters

Defines the ``logging.Formatter``/``logging.Filter`` implementations
used by the Logging Engine: a plain text formatter, an optional
ANSI-colored console variant, a line-delimited JSON formatter for
machine-readable export (REQ-LOG-011), and a filter that redacts
sensitive values before they reach any handler (REQ-SEC-010's
guarantee, applied to Aquila's own logs -- see
``LoggingConfig.redact_sensitive_fields``).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any, Mapping, cast

from common.constants.logging import (
    DEBUG_LOG_FORMAT,
    DEFAULT_DATE_FORMAT,
    DEFAULT_LOG_FORMAT,
)

# ----------------------------------------------------------------------
# Plain Text
# ----------------------------------------------------------------------


class AquilaFormatter(logging.Formatter):
    """
    Standard Aquila text formatter.

    Uses :data:`common.constants.logging.DEBUG_LOG_FORMAT` (adds the
    source file and line number) when ``verbose`` is set, otherwise
    :data:`common.constants.logging.DEFAULT_LOG_FORMAT`.
    """

    def __init__(self, *, verbose: bool = False) -> None:
        super().__init__(
            fmt=DEBUG_LOG_FORMAT if verbose else DEFAULT_LOG_FORMAT,
            datefmt=DEFAULT_DATE_FORMAT,
        )


# ----------------------------------------------------------------------
# ANSI Console Colors
# ----------------------------------------------------------------------

_ANSI_RESET = "\x1b[0m"

_ANSI_COLOR_CODES: dict[str, str] = {
    "black": "\x1b[30m",
    "red": "\x1b[31m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "blue": "\x1b[34m",
    "magenta": "\x1b[35m",
    "cyan": "\x1b[36m",
    "white": "\x1b[37m",
}

#: Maps each severity to a color *name*, matching
#: ``common.constants.logging``'s ``COLOR_DEBUG``/``COLOR_INFO``/etc.
#: values. Kept as a literal dict (rather than importing those
#: constants directly) so a typo in one of them can't silently drop a
#: level's color -- ``_ANSI_COLOR_CODES.get()`` below already handles
#: an unrecognized name by falling back to no color.
_LEVEL_COLOR_NAMES: dict[int, str] = {
    logging.DEBUG: "cyan",
    logging.INFO: "green",
    logging.WARNING: "yellow",
    logging.ERROR: "red",
    logging.CRITICAL: "magenta",
}


class ColorConsoleFormatter(AquilaFormatter):
    """
    Console formatter that colors each line by severity.

    When ``use_color`` is ``False`` this behaves identically to
    :class:`AquilaFormatter`. ``logging_engine.handlers.
    create_console_handler`` decides ``use_color`` based on
    ``LoggingConfig`` *and* whether the target stream is actually a
    terminal, so a console log redirected to a file or piped to
    another process never receives raw ANSI escape codes mixed into
    it.
    """

    def __init__(
        self,
        *,
        verbose: bool = False,
        use_color: bool = True,
    ) -> None:
        super().__init__(verbose=verbose)
        self._use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)

        if not self._use_color:
            return line

        color_name = _LEVEL_COLOR_NAMES.get(record.levelno)
        color = _ANSI_COLOR_CODES.get(color_name) if color_name else None

        if color is None:
            return line

        return f"{color}{line}{_ANSI_RESET}"


# ----------------------------------------------------------------------
# Structured (line-delimited JSON)
# ----------------------------------------------------------------------


class StructuredFormatter(logging.Formatter):
    """
    Renders one JSON object per log record, on a single line.

    Produces the REQ-LOG-002 record shape (timestamp, severity,
    subsystem, event identifier, event description, result, and
    optional diagnostic information) as machine-readable JSON Lines,
    suitable for the deployment report export
    (``LogManager.export_logs()``, REQ-LOG-011) and for future
    integration with a centralized log aggregation system
    (REQ-LOG-015).
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                tz=UTC,
            ).isoformat(),
            "severity": record.levelname,
            "subsystem": record.name,
            "event_id": getattr(record, "event_id", None) or "GENERIC",
            "description": record.getMessage(),
        }

        result = getattr(record, "result", None)

        if result is not None:
            payload["result"] = result

        diagnostics = getattr(record, "diagnostics", None)

        if diagnostics:
            payload["diagnostics"] = diagnostics

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )


# ----------------------------------------------------------------------
# Redaction
# ----------------------------------------------------------------------

#: Substrings (case-insensitive) that mark a field name or
#: ``key=value`` token as sensitive. Deliberately broad -- a false
#: positive just redacts something harmless, a false negative leaks a
#: secret into a log file, so this errs toward over-redacting.
SENSITIVE_FIELD_MARKERS: tuple[str, ...] = (
    "password",
    "passwd",
    "token",
    "secret",
    "credential",
    "api_key",
    "apikey",
    "private_key",
    "authorization",
)

_REDACTED = "***REDACTED***"

#: Deliberately has no leading ``\b``: real-world keys are commonly
#: compound identifiers like ``join_token`` or ``auth_token`` where
#: the marker doesn't start at a word boundary (``_`` is itself a
#: word character, so ``\btoken`` would never match inside
#: ``join_token``). A trailing boundary isn't needed either -- the
#: delimiter group immediately following the marker already rejects
#: a longer word like "tokenizer" (nothing after "token" in
#: "tokenizer=x" satisfies ``[:=]`` immediately, with only optional
#: quote/whitespace in between).
_INLINE_SECRET_PATTERN = re.compile(
    r"(?i)("
    + "|".join(re.escape(marker) for marker in SENSITIVE_FIELD_MARKERS)
    + r")([\"']?\s*[:=]\s*)([^\s,;\"']+)"
)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()

    return any(marker in lowered for marker in SENSITIVE_FIELD_MARKERS)


def _redact_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}

    for key, value in data.items():

        if _is_sensitive_key(key):
            redacted[key] = _REDACTED

        elif isinstance(value, Mapping):
            # Same narrowing quirk as above: ``value`` is ``Any``
            # (from ``data: Mapping[str, Any]``), and the
            # ``isinstance`` check narrows it to a bare
            # ``Mapping[Unknown, Unknown]`` rather than preserving
            # ``Any``.
            redacted[key] = _redact_mapping(cast(Mapping[str, Any], value))

        else:
            redacted[key] = value

    return redacted


def redact_text(text: str) -> str:
    """
    Mask ``key=value``/``key: value`` tokens whose key looks
    sensitive.
    """

    return _INLINE_SECRET_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{_REDACTED}",
        text,
    )


class RedactingFilter(logging.Filter):
    """
    Masks sensitive values before a record reaches its handler.

    Attached directly to each handler (not to a ``Logger``) by
    ``LogManager.initialize()`` whenever
    ``LoggingConfig.redact_sensitive_fields`` is ``True`` (the
    default): a :class:`logging.Handler` re-checks its own filters
    for every record it emits regardless of which logger originated
    it, which is what makes a single shared instance, attached to
    every managed handler, the correct place to guarantee this runs
    for every Aquila log line -- console, rotating file, and
    structured export alike -- and not only for records logged
    directly against the root logger.

    This is defense in depth, not the primary safeguard: Aquila's own
    configuration model never stores a secret value in the first
    place (``ConfigurationManager.resolve_secret``, REQ-SEC-008/009),
    so this filter exists to catch the case where a secret a caller
    resolved for its own use is accidentally interpolated into a log
    message, not to be the only thing standing between a credential
    and a log file.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # A %-style record's raw ``msg`` still has unfilled
        # placeholders (e.g. "token=%s") and the actual value lives
        # separately in ``record.args`` -- so scanning ``msg`` alone
        # can never see "token=<secret>" together, and redacting each
        # arg in isolation can't either, since the arg by itself is
        # just "<secret>" with no key attached to tell it apart from
        # an ordinary value. The reliable fix is to resolve the
        # record down to its final text with ``record.getMessage()``
        # (stdlib's own ``msg % args`` substitution) *before*
        # redacting, then store that already-redacted, already-final
        # string back as ``msg`` with ``args`` cleared -- every
        # formatter downstream calls ``getMessage()`` too, so this
        # runs once, here, rather than duplicating the substitution
        # logic per formatter.
        record.msg = redact_text(record.getMessage())
        record.args = None

        diagnostics = getattr(record, "diagnostics", None)

        if isinstance(diagnostics, Mapping):
            # ``diagnostics`` comes from ``getattr(record, ..., None)``
            # (type ``Any``); same narrowing quirk as ``record.args``
            # above.
            record.diagnostics = _redact_mapping(
                cast(Mapping[str, Any], diagnostics)
            )

        return True


__all__ = [
    "AquilaFormatter",
    "ColorConsoleFormatter",
    "RedactingFilter",
    "SENSITIVE_FIELD_MARKERS",
    "StructuredFormatter",
    "redact_text",
]
