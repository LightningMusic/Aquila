"""
Project Aquila
=============

Common utility functions used throughout Project Aquila.

This module contains small, reusable helper functions that do not
belong to any specific subsystem.

Utility functions should remain stateless and avoid side effects
whenever practical.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import hashlib
import json
import shutil

import common.paths as paths
import common.constants as constants


# =============================================================================
# Filesystem Utilities
# =============================================================================


def ensure_directory(directory: Path) -> Path:
    """
    Ensure a directory exists.

    Args:
        directory:
            Directory to create if necessary.

    Returns:
        The directory path.
    """

    directory.mkdir(parents=True, exist_ok=True)

    return directory


def directory_exists(directory: Path) -> bool:
    """
    Determine whether a directory exists.

    Args:
        directory:
            Directory to check.

    Returns:
        True if the directory exists.
    """

    return directory.is_dir()


def file_exists(file_path: Path) -> bool:
    """
    Determine whether a file exists.

    Args:
        file_path:
            File to check.

    Returns:
        True if the file exists.
    """

    return file_path.is_file()


def delete_directory(directory: Path) -> None:
    """
    Delete a directory recursively.

    Args:
        directory:
            Directory to remove.
    """

    if directory.exists():
        shutil.rmtree(directory)


# =============================================================================
# Hash Utilities
# =============================================================================


def sha256(file_path: Path) -> str:
    """
    Compute the SHA-256 hash of a file.

    Args:
        file_path:
            File to hash.

    Returns:
        Hexadecimal SHA-256 digest.
    """

    digest = hashlib.sha256()

    with file_path.open("rb") as stream:

        while True:

            chunk = stream.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


# =============================================================================
# Time Utilities
# =============================================================================


def utc_now() -> datetime:
    """
    Return the current UTC time.

    Returns:
        Current UTC datetime.
    """

    return datetime.utcnow()


def timestamp() -> str:
    """
    Return a formatted UTC timestamp.

    Returns:
        Timestamp string.
    """

    return utc_now().strftime(constants.DEFAULT_DATETIME_FORMAT)


# =============================================================================
# JSON Utilities
# =============================================================================


def write_json(
    file_path: Path,
    data: dict[str, Any],
) -> None:
    """
    Write JSON data to disk.

    Args:
        file_path:
            Destination file.

        data:
            Serializable dictionary.
    """

    ensure_directory(file_path.parent)

    with file_path.open(
        "w",
        encoding=constants.APP_ENCODING,
    ) as stream:

        json.dump(
            data,
            stream,
            indent=4,
            sort_keys=True,
        )


def read_json(file_path: Path) -> dict[str, Any]:
    """
    Read a JSON file.

    Args:
        file_path:
            JSON file.

    Returns:
        Parsed dictionary.
    """

    with file_path.open(
        "r",
        encoding=constants.APP_ENCODING,
    ) as stream:

        return json.load(stream)


# =============================================================================
# String Utilities
# =============================================================================


def separator(
    character: str = "=",
    length: int = 80,
) -> str:
    """
    Generate a separator string.

    Args:
        character:
            Character used for the separator.

        length:
            Length of separator.

    Returns:
        Separator string.
    """

    return character * length


def title(text: str) -> str:
    """
    Format a title.

    Args:
        text:
            Title text.

    Returns:
        Centered title.
    """

    return text.strip().title()


# =============================================================================
# Formatting Utilities
# =============================================================================


def bytes_to_megabytes(size: int) -> float:
    """
    Convert bytes to megabytes.

    Args:
        size:
            Size in bytes.

    Returns:
        Size in megabytes.
    """

    return size / 1024 / 1024


def bytes_to_gigabytes(size: int) -> float:
    """
    Convert bytes to gigabytes.

    Args:
        size:
            Size in bytes.

    Returns:
        Size in gigabytes.
    """

    return size / 1024 / 1024 / 1024


# =============================================================================
# Runtime Initialization
# =============================================================================


def initialize_runtime() -> None:
    """
    Initialize the Aquila runtime environment.

    Creates all required runtime directories.
    """

    paths.ensure_runtime_directories()