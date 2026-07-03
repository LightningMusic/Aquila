"""
Project Orion
=============

JSON Utilities

Provides standardized JSON serialization and deserialization
utilities used throughout Project Orion.

This module centralizes JSON handling to ensure consistent
encoding, formatting, and error handling.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_INDENT = 4
DEFAULT_ENCODING = "utf-8"


# ----------------------------------------------------------------------
# Reading
# ----------------------------------------------------------------------

def load_json(
    path: Path,
) -> dict[str, Any]:
    """
    Load a JSON file.
    """

    with path.open(
        "r",
        encoding=DEFAULT_ENCODING,
    ) as file:

        data: dict[str, Any] = json.load(file)

    return data


def loads(
    text: str,
) -> Any:
    """
    Deserialize a JSON string.
    """

    return json.loads(text)


# ----------------------------------------------------------------------
# Writing
# ----------------------------------------------------------------------

def save_json(
    path: Path,
    data: Any,
    *,
    indent: int = DEFAULT_INDENT,
    sort_keys: bool = True,
) -> Path:
    """
    Save an object as formatted JSON.
    """

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding=DEFAULT_ENCODING,
    ) as file:

        json.dump(
            data,
            file,
            indent=indent,
            sort_keys=sort_keys,
            ensure_ascii=False,
        )

        file.write("\n")

    return path


def dumps(
    data: Any,
    *,
    indent: int = DEFAULT_INDENT,
    sort_keys: bool = True,
) -> str:
    """
    Serialize an object into JSON.
    """

    return json.dumps(
        data,
        indent=indent,
        sort_keys=sort_keys,
        ensure_ascii=False,
    )


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------

def is_valid_json(
    text: str,
) -> bool:
    """
    Determine whether a string contains valid JSON.
    """

    try:
        json.loads(text)
        return True

    except json.JSONDecodeError:
        return False


# ----------------------------------------------------------------------
# Convenience
# ----------------------------------------------------------------------

def read_value(
    path: Path,
    key: str,
    default: Any = None,
) -> Any:
    """
    Read a single value from a JSON file.
    """

    data = load_json(path)

    return data.get(
        key,
        default,
    )


def update_json(
    path: Path,
    updates: dict[str, Any],
) -> Path:
    """
    Update a JSON file.

    Existing keys are overwritten.
    """

    data = load_json(path)

    data.update(updates)

    return save_json(
        path,
        data,
    )


# ----------------------------------------------------------------------
# Pretty Printing
# ----------------------------------------------------------------------

def pretty_print(
    data: Any,
) -> str:
    """
    Return formatted JSON.

    Useful for logging and debugging.
    """

    return dumps(
        data,
        indent=4,
        sort_keys=True,
    )


# ----------------------------------------------------------------------
# Public Exports
# ----------------------------------------------------------------------

__all__ = [
    "DEFAULT_ENCODING",
    "DEFAULT_INDENT",
    "dumps",
    "is_valid_json",
    "load_json",
    "loads",
    "pretty_print",
    "read_value",
    "save_json",
    "update_json",
]