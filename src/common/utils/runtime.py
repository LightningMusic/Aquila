"""
Project Orion
=============

Runtime Utilities

Provides runtime directory management for Project Orion.

This module is responsible for creating and managing temporary
working directories, caches, reports, logs, and other runtime
resources used while Orion is executing.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

import shutil
from pathlib import Path

from common.paths import (
    BUILD_DIR,
    CACHE_DIR,
    DIST_DIR,
    LOG_DIR,
    TEMP_DIR,
    ensure_directory,
)

# ----------------------------------------------------------------------
# Runtime Directories
# ----------------------------------------------------------------------

REPORTS_DIR = BUILD_DIR / "reports"
RECOVERY_DIR = BUILD_DIR / "recovery"
DOWNLOADS_DIR = BUILD_DIR / "downloads"
INVENTORY_DIR = BUILD_DIR / "inventory"
BENCHMARK_DIR = BUILD_DIR / "benchmarks"

_RUNTIME_DIRECTORIES = (
    BUILD_DIR,
    CACHE_DIR,
    DIST_DIR,
    LOG_DIR,
    TEMP_DIR,
    REPORTS_DIR,
    RECOVERY_DIR,
    DOWNLOADS_DIR,
    INVENTORY_DIR,
    BENCHMARK_DIR,
)


# ----------------------------------------------------------------------
# Initialization
# ----------------------------------------------------------------------

def initialize_runtime() -> None:
    """
    Ensure every runtime directory exists.
    """

    for directory in _RUNTIME_DIRECTORIES:
        ensure_directory(directory)


# ----------------------------------------------------------------------
# Directory Accessors
# ----------------------------------------------------------------------

def build_directory() -> Path:
    return BUILD_DIR


def cache_directory() -> Path:
    return CACHE_DIR


def log_directory() -> Path:
    return LOG_DIR


def temp_directory() -> Path:
    return TEMP_DIR


def reports_directory() -> Path:
    return REPORTS_DIR


def recovery_directory() -> Path:
    return RECOVERY_DIR


def downloads_directory() -> Path:
    return DOWNLOADS_DIR


def inventory_directory() -> Path:
    return INVENTORY_DIR


def benchmark_directory() -> Path:
    return BENCHMARK_DIR


# ----------------------------------------------------------------------
# Cleanup
# ----------------------------------------------------------------------

def clear_temp() -> None:
    """
    Remove all temporary files.
    """

    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)

    ensure_directory(TEMP_DIR)


def clear_cache() -> None:
    """
    Remove all cached files.
    """

    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)

    ensure_directory(CACHE_DIR)


def reset_runtime() -> None:
    """
    Reset the runtime environment.

    Reports, logs, and generated artifacts are preserved.
    Only temporary and cache data are removed.
    """

    clear_temp()
    clear_cache()


# ----------------------------------------------------------------------
# Queries
# ----------------------------------------------------------------------

def runtime_exists() -> bool:
    """
    Determine whether every runtime directory exists.
    """

    return all(
        directory.exists()
        for directory in _RUNTIME_DIRECTORIES
    )


def runtime_directories() -> tuple[Path, ...]:
    """
    Return every runtime directory.
    """

    return _RUNTIME_DIRECTORIES


# ----------------------------------------------------------------------
# Public Exports
# ----------------------------------------------------------------------

__all__ = [
    "REPORTS_DIR",
    "RECOVERY_DIR",
    "DOWNLOADS_DIR",
    "INVENTORY_DIR",
    "BENCHMARK_DIR",
    "initialize_runtime",
    "build_directory",
    "cache_directory",
    "log_directory",
    "temp_directory",
    "reports_directory",
    "recovery_directory",
    "downloads_directory",
    "inventory_directory",
    "benchmark_directory",
    "clear_temp",
    "clear_cache",
    "reset_runtime",
    "runtime_exists",
    "runtime_directories",
]