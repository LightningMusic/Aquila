"""
Project Aquila
=============

Formatting Utilities

Provides standardized formatting helpers used throughout
Project Aquila.

This module contains presentation utilities only. It should never
contain business logic.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from textwrap import fill

# ----------------------------------------------------------------------
# Byte Formatting
# ----------------------------------------------------------------------

#: Binary (IEC) units, matching the /1024 division below -- see the
#: fix note in this function's own docstring for why these replaced
#: the previous "KB"/"MB"/... labels.
_BYTE_UNITS = (
    "B",
    "KiB",
    "MiB",
    "GiB",
    "TiB",
    "PiB",
)


def format_bytes(size: int) -> str:
    """
    Format a byte count into a human-readable string, using binary
    (1024-based) units.

    Fixed root-cause duplication bug: this function and
    ``technician_console.progress.format_bytes`` were two independent
    implementations of the same concern, and had drifted -- this one
    divided by 1024 (binary math) while labeling the result with
    decimal unit names ("KB"/"MB"/...), which is simply an incorrect
    label for that math (1024 bytes is 1 KiB, not 1.00 KB); the other
    used the correct "KiB"/"MiB"/... labels. Latent-drift-risk category
    already fixed elsewhere in this project (``common/constants/filesystem.py``
    re-declaring ``deployment.py``'s USB-layout constants,
    ``bootstrap/controller_client.py``/``deployment_controller/api.py``
    re-declaring the same route paths) -- one public byte-formatting
    helper producing different operator-facing text than another with
    the same name is the same class of defect. This is now the single
    implementation; ``technician_console.progress.format_bytes``
    re-exports it rather than re-declaring it.
    """

    value = float(size)

    for unit in _BYTE_UNITS:
        if value < 1024 or unit == _BYTE_UNITS[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024

    return f"{size} B"


# ----------------------------------------------------------------------
# Percentages
# ----------------------------------------------------------------------

def format_percent(
    value: float,
    *,
    decimals: int = 1,
) -> str:
    """
    Format a percentage.
    """

    return f"{value:.{decimals}f}%"


# ----------------------------------------------------------------------
# Durations
# ----------------------------------------------------------------------

def format_duration(
    duration: timedelta,
) -> str:
    """
    Format a timedelta.

    Example:
        2h 15m 04s
    """

    total_seconds = int(duration.total_seconds())

    hours, remainder = divmod(total_seconds, 3600)

    minutes, seconds = divmod(remainder, 60)

    parts: list[str] = []

    if hours:
        parts.append(f"{hours}h")

    if minutes or hours:
        parts.append(f"{minutes}m")

    parts.append(f"{seconds}s")

    return " ".join(parts)


# ----------------------------------------------------------------------
# Numbers
# ----------------------------------------------------------------------

def format_number(
    value: int | float,
) -> str:
    """
    Format a number with thousands separators.
    """

    return f"{value:,}"


def format_float(
    value: float,
    *,
    decimals: int = 2,
) -> str:
    """
    Format a floating-point value.
    """

    return f"{value:.{decimals}f}"


# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------

def format_path(
    path: Path,
) -> str:
    """
    Return a normalized path string.
    """

    return str(path.resolve())


# ----------------------------------------------------------------------
# Strings
# ----------------------------------------------------------------------

def title(text: str) -> str:
    """
    Convert text to title case.
    """

    return text.title()


def uppercase(text: str) -> str:
    """
    Convert text to uppercase.
    """

    return text.upper()


def lowercase(text: str) -> str:
    """
    Convert text to lowercase.
    """

    return text.lower()


def wrap(
    text: str,
    *,
    width: int = 80,
) -> str:
    """
    Wrap text to a specified width.
    """

    return fill(
        text,
        width=width,
    )


# ----------------------------------------------------------------------
# Report Formatting
# ----------------------------------------------------------------------

def divider(
    *,
    character: str = "-",
    width: int = 80,
) -> str:
    """
    Create a divider line.
    """

    return character * width


def heading(
    text: str,
    *,
    character: str = "=",
    width: int = 80,
) -> str:
    """
    Create a formatted heading.
    """

    line = character * width

    return (
        f"{line}\n"
        f"{text}\n"
        f"{line}"
    )


def key_value(
    key: str,
    value: object,
    *,
    width: int = 30,
) -> str:
    """
    Format a key/value pair.

    Example:
        CPU Model................Intel Core i7
    """

    return f"{key:<{width}} {value}"


# ----------------------------------------------------------------------
# Collections
# ----------------------------------------------------------------------

def bullet_list(
    items: list[str],
    *,
    bullet: str = "-",
) -> str:
    """
    Format a bullet list.
    """

    return "\n".join(
        f"{bullet} {item}"
        for item in items
    )


# ----------------------------------------------------------------------
# Public Exports
# ----------------------------------------------------------------------

__all__ = [
    "bullet_list",
    "divider",
    "format_bytes",
    "format_duration",
    "format_float",
    "format_number",
    "format_path",
    "format_percent",
    "heading",
    "key_value",
    "lowercase",
    "title",
    "uppercase",
    "wrap",
]