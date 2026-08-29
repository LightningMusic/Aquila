"""
Project Aquila
=============

Log Handlers

Factory functions that build the ``logging.Handler`` instances the
Logging Engine attaches to Aquila loggers: a console stream handler,
rotating text file handlers (log rotation driven by
``LoggingConfig.max_log_size_mb``/``backup_count``), and a rotating
structured (JSON Lines) file handler used for the deployment report
export path (REQ-LOG-011).

Kept separate from ``log_manager.py`` so a future centralized log
aggregation integration (REQ-LOG-015), or any other subsystem that
needs one more handler on a managed logger, can build one with these
same factories without needing to go through ``LogManager`` at all.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, TextIO

from common.utils.filesystem import create_directory
from logging_engine.formatter import (
    AquilaFormatter,
    ColorConsoleFormatter,
    StructuredFormatter,
)

DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 5


# ----------------------------------------------------------------------
# Console
# ----------------------------------------------------------------------

def create_console_handler(
    *,
    level: int = logging.INFO,
    verbose: bool = False,
    use_color: bool = True,
    stream: Optional[TextIO] = None,
) -> "logging.StreamHandler[TextIO]":
    """
    Build a console (stderr by default) handler.

    ``use_color`` is honored only when the target stream reports
    itself as a real terminal (``isatty()``); a console log
    redirected to a file or piped to another process never receives
    raw ANSI escape codes, regardless of what the caller requested.
    """

    target = stream if stream is not None else sys.stderr

    is_tty = bool(getattr(target, "isatty", lambda: False)())

    handler = logging.StreamHandler(target)
    handler.setLevel(level)
    handler.setFormatter(
        ColorConsoleFormatter(
            verbose=verbose,
            use_color=use_color and is_tty,
        )
    )

    return handler


# ----------------------------------------------------------------------
# Rotating Files
# ----------------------------------------------------------------------

def create_file_handler(
    path: Path,
    *,
    level: int = logging.DEBUG,
    verbose: bool = True,
    max_bytes_per_file: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> RotatingFileHandler:
    """
    Build a rotating plain-text file handler.

    The parent directory is created if it does not already exist so
    callers never need to prepare the log directory themselves.
    """

    create_directory(path.parent)

    handler = RotatingFileHandler(
        path,
        maxBytes=max_bytes_per_file,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(AquilaFormatter(verbose=verbose))

    return handler


def create_structured_file_handler(
    path: Path,
    *,
    level: int = logging.DEBUG,
    max_bytes_per_file: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> RotatingFileHandler:
    """
    Build a rotating line-delimited JSON file handler.

    Used for the machine-readable event stream
    (``common.constants.logging.EVENT_LOG_FILE``) that
    ``LogManager.export_logs()`` bundles into a deployment report
    (REQ-LOG-011).
    """

    create_directory(path.parent)

    handler = RotatingFileHandler(
        path,
        maxBytes=max_bytes_per_file,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(StructuredFormatter())

    return handler


# ----------------------------------------------------------------------
# Null
# ----------------------------------------------------------------------

def create_null_handler() -> logging.NullHandler:
    """
    Build a handler that discards every record.

    Useful as a library-safe default and for tests that want logging
    calls to execute (exercising real code paths) without producing
    any output.
    """

    return logging.NullHandler()


__all__ = [
    "DEFAULT_BACKUP_COUNT",
    "DEFAULT_MAX_BYTES",
    "create_console_handler",
    "create_file_handler",
    "create_null_handler",
    "create_structured_file_handler",
]
