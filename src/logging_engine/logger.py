"""
Project Aquila
=============

Logger Access

Thin, centralized entry point applications and subsystems use to
obtain a properly namespaced ``logging.Logger`` and to record
structured log events (SRS Section 9.9, REQ-LOG-001, REQ-LOG-002).

This module never configures handlers or formatters itself -- that
is ``log_manager.LogManager``'s responsibility (SRS Section 10.12).
Every function here only creates/returns stdlib ``logging.Logger``
instances and enriches individual log records, so a logger obtained
before ``LogManager.initialize()`` has run behaves exactly like any
other unconfigured Python logger (it simply has no handlers attached
yet, per stdlib's own default behavior) -- import order never
matters.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from common.constants.logging import ROOT_LOGGER

_DEFAULT_EVENT_ID = "GENERIC"


# ----------------------------------------------------------------------
# Logger Access
# ----------------------------------------------------------------------

def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Return an Aquila logger.

    ``name`` may be a bare subsystem name (``"deployment"``), an
    already-namespaced name (``"aquila.deployment"``), or omitted
    entirely to return the root Aquila logger. All three forms end up
    nested under :data:`common.constants.logging.ROOT_LOGGER`, so
    every Aquila logger -- however it was requested -- responds to
    ``LogManager.set_level()`` calls against the root and propagates
    into the root's handlers (REQ-LOG-001).
    """

    if name is None or name == "":
        return logging.getLogger(ROOT_LOGGER)

    if name == ROOT_LOGGER or name.startswith(f"{ROOT_LOGGER}."):
        return logging.getLogger(name)

    return logging.getLogger(f"{ROOT_LOGGER}.{name}")


# ----------------------------------------------------------------------
# Structured Logging (REQ-LOG-002)
# ----------------------------------------------------------------------

def log_event(
    logger: logging.Logger,
    level: int,
    event_id: str,
    description: str,
    *,
    result: Optional[str] = None,
    **diagnostics: Any,
) -> None:
    """
    Record a fully structured Aquila log event (REQ-LOG-002).

    Every Aquila log entry is required, at minimum, to carry a
    timestamp, severity, subsystem, event identifier, and event
    description. The first three come for free from any ordinary
    ``logging.Logger`` call (timestamp/severity from the log record
    itself, subsystem from the logger's name); this helper adds the
    two fields stdlib logging has no native concept of -- ``event_id``
    and an optional ``result`` -- plus any free-form keyword
    diagnostics, all carried on the record via ``extra`` so
    :class:`logging_engine.formatter.StructuredFormatter` can render
    them without every call site needing to build a dict by hand.

    Ordinary ``logger.info("message")``-style calls remain completely
    valid throughout Aquila; this helper exists for call sites that
    specifically need the full REQ-LOG-002 shape (for example,
    Preparation logging a sanitization outcome, or the Deployment
    Controller logging an authentication result).
    """

    logger.log(
        level,
        description,
        extra={
            "event_id": event_id or _DEFAULT_EVENT_ID,
            "result": result,
            "diagnostics": diagnostics or None,
        },
    )


def log_operator_confirmation(
    logger: logging.Logger,
    prompt: str,
    confirmed: bool,
    **diagnostics: Any,
) -> None:
    """
    Record an operator confirmation decision (REQ-LOG-005,
    REQ-PREP-021).

    Every confirmation Aquila requests before an irreversible
    operation (SRS Section 9.14, Safety Architecture) is logged
    through this single helper so every confirmation in the
    deployment history has the same recognizable shape: ``INFO`` for
    an approval, ``WARNING`` for a decline -- a decline is never an
    error, refusing a destructive action is the safety mechanism
    working as intended.
    """

    log_event(
        logger,
        logging.INFO if confirmed else logging.WARNING,
        "OPERATOR_CONFIRMATION",
        prompt,
        result="confirmed" if confirmed else "declined",
        **diagnostics,
    )


__all__ = [
    "get_logger",
    "log_event",
    "log_operator_confirmation",
]
