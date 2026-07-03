"""
Project Orion
=============

Date and Time Utilities

Provides standardized date and time utilities used throughout
Project Orion.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from datetime import timedelta


# ----------------------------------------------------------------------
# Current Time
# ----------------------------------------------------------------------

def utc_now() -> datetime:
    """
    Return the current UTC datetime.
    """

    return datetime.now(UTC)


def local_now() -> datetime:
    """
    Return the current local datetime.
    """

    return datetime.now().astimezone()


# ----------------------------------------------------------------------
# Formatting
# ----------------------------------------------------------------------

def timestamp() -> str:
    """
    Return a filesystem-safe timestamp.

    Example:
        20260702_194530
    """

    return utc_now().strftime("%Y%m%d_%H%M%S")


def iso_timestamp() -> str:
    """
    Return an ISO-8601 UTC timestamp.
    """

    return utc_now().isoformat()


def human_timestamp() -> str:
    """
    Return a human-readable timestamp.

    Example:
        2026-07-02 19:45:30 UTC
    """

    return utc_now().strftime("%Y-%m-%d %H:%M:%S UTC")


def format_datetime(
    value: datetime,
    fmt: str = "%Y-%m-%d %H:%M:%S",
) -> str:
    """
    Format a datetime object.
    """

    return value.strftime(fmt)


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------

def parse_iso(
    value: str,
) -> datetime:
    """
    Parse an ISO-8601 datetime string.
    """

    return datetime.fromisoformat(value)


# ----------------------------------------------------------------------
# Elapsed Time
# ----------------------------------------------------------------------

def elapsed(
    start: datetime,
    end: datetime | None = None,
) -> timedelta:
    """
    Return the elapsed time between two timestamps.
    """

    if end is None:
        end = utc_now()

    return end - start


def elapsed_seconds(
    start: datetime,
    end: datetime | None = None,
) -> float:
    """
    Return elapsed time in seconds.
    """

    return elapsed(start, end).total_seconds()


# ----------------------------------------------------------------------
# Duration Formatting
# ----------------------------------------------------------------------

def format_duration(
    duration: timedelta,
) -> str:
    """
    Convert a timedelta into a human-readable string.

    Example:
        2h 14m 53s
    """

    total_seconds = int(duration.total_seconds())

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts: list[str] = []

    if hours:
        parts.append(f"{hours}h")

    if minutes:
        parts.append(f"{minutes}m")

    parts.append(f"{seconds}s")

    return " ".join(parts)


# ----------------------------------------------------------------------
# Date Comparisons
# ----------------------------------------------------------------------

def is_today(
    value: datetime,
) -> bool:
    """
    Determine whether the datetime is today.
    """

    return value.date() == local_now().date()


def is_past(
    value: datetime,
) -> bool:
    """
    Determine whether a datetime has already occurred.
    """

    return value < utc_now()


def is_future(
    value: datetime,
) -> bool:
    """
    Determine whether a datetime lies in the future.
    """

    return value > utc_now()


# ----------------------------------------------------------------------
# Public Exports
# ----------------------------------------------------------------------

__all__ = [
    "utc_now",
    "local_now",
    "timestamp",
    "iso_timestamp",
    "human_timestamp",
    "format_datetime",
    "parse_iso",
    "elapsed",
    "elapsed_seconds",
    "format_duration",
    "is_today",
    "is_past",
    "is_future",
]