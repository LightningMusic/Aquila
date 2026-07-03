"""
Project Orion
=============

Filesystem Utilities

Provides safe filesystem helper functions used throughout
Project Orion.

All filesystem operations should be routed through this module
whenever practical to ensure consistent behavior.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

import shutil
from pathlib import Path


# ----------------------------------------------------------------------
# Directory Operations
# ----------------------------------------------------------------------

def create_directory(
    path: Path,
    *,
    parents: bool = True,
    exist_ok: bool = True,
) -> Path:
    """
    Create a directory.

    Returns the created Path object.
    """

    path.mkdir(
        parents=parents,
        exist_ok=exist_ok,
    )

    return path


def remove_directory(
    path: Path,
    *,
    ignore_missing: bool = True,
) -> None:
    """
    Remove a directory recursively.
    """

    if not path.exists():

        if ignore_missing:
            return

        raise FileNotFoundError(path)

    shutil.rmtree(path)


def empty_directory(
    path: Path,
) -> None:
    """
    Remove every file inside a directory while preserving
    the directory itself.
    """

    create_directory(path)

    for child in path.iterdir():

        if child.is_dir():
            shutil.rmtree(child)

        else:
            child.unlink()


# ----------------------------------------------------------------------
# File Operations
# ----------------------------------------------------------------------

def copy_file(
    source: Path,
    destination: Path,
) -> Path:
    """
    Copy a file.

    Parent directories are automatically created.
    """

    create_directory(destination.parent)

    shutil.copy2(
        source,
        destination,
    )

    return destination


def move_file(
    source: Path,
    destination: Path,
) -> Path:
    """
    Move a file.
    """

    create_directory(destination.parent)

    shutil.move(
        str(source),
        str(destination),
    )

    return destination


def delete_file(
    path: Path,
    *,
    ignore_missing: bool = True,
) -> None:
    """
    Delete a file.
    """

    if not path.exists():

        if ignore_missing:
            return

        raise FileNotFoundError(path)

    path.unlink()


# ----------------------------------------------------------------------
# Reading / Writing
# ----------------------------------------------------------------------

def read_text(
    path: Path,
    *,
    encoding: str = "utf-8",
) -> str:
    """
    Read a UTF-8 text file.
    """

    return path.read_text(
        encoding=encoding,
    )


def write_text(
    path: Path,
    contents: str,
    *,
    encoding: str = "utf-8",
) -> Path:
    """
    Write a UTF-8 text file.

    Parent directories are automatically created.
    """

    create_directory(path.parent)

    path.write_text(
        contents,
        encoding=encoding,
    )

    return path


def append_text(
    path: Path,
    contents: str,
    *,
    encoding: str = "utf-8",
) -> Path:
    """
    Append text to a file.
    """

    create_directory(path.parent)

    with path.open(
        "a",
        encoding=encoding,
    ) as file:

        file.write(contents)

    return path


# ----------------------------------------------------------------------
# Queries
# ----------------------------------------------------------------------

def exists(
    path: Path,
) -> bool:
    """
    Determine whether a path exists.
    """

    return path.exists()


def is_file(
    path: Path,
) -> bool:
    """
    Determine whether a path is a file.
    """

    return path.is_file()


def is_directory(
    path: Path,
) -> bool:
    """
    Determine whether a path is a directory.
    """

    return path.is_dir()


def directory_size(
    path: Path,
) -> int:
    """
    Calculate the total size of a directory in bytes.
    """

    total = 0

    if not path.exists():
        return total

    for item in path.rglob("*"):

        if item.is_file():
            total += item.stat().st_size

    return total


# ----------------------------------------------------------------------
# Public Exports
# ----------------------------------------------------------------------

__all__ = [
    "append_text",
    "copy_file",
    "create_directory",
    "delete_file",
    "directory_size",
    "empty_directory",
    "exists",
    "is_directory",
    "is_file",
    "move_file",
    "read_text",
    "remove_directory",
    "write_text",
]