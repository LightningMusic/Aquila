"""
Project Aquila
=============

Filesystem Paths

Provides a centralized definition of the Project Aquila directory
structure.

No other module should construct project-relative paths manually.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from pathlib import Path

# ----------------------------------------------------------------------
# Repository Root
# ----------------------------------------------------------------------

THIS_FILE = Path(__file__).resolve()

COMMON_DIR = THIS_FILE.parent

SRC_DIR = COMMON_DIR.parent

PROJECT_ROOT = SRC_DIR.parent

# ----------------------------------------------------------------------
# Top-Level Directories
# ----------------------------------------------------------------------

ASSETS_DIR = PROJECT_ROOT / "assets"
BUILD_DIR = PROJECT_ROOT / "build"
CONFIGS_DIR = PROJECT_ROOT / "configs"
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = PROJECT_ROOT / "docs"
RELEASES_DIR = PROJECT_ROOT / "releases"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SRC_ROOT = PROJECT_ROOT / "src"
TESTS_DIR = PROJECT_ROOT / "tests"
TOOLS_DIR = PROJECT_ROOT / "tools"
USB_DIR = PROJECT_ROOT / "usb"

# ----------------------------------------------------------------------
# Assets
# ----------------------------------------------------------------------

ICONS_DIR = ASSETS_DIR / "icons"
IMAGES_DIR = ASSETS_DIR / "images"
LOGOS_DIR = ASSETS_DIR / "logos"

# ----------------------------------------------------------------------
# Documentation
# ----------------------------------------------------------------------

ADR_DIR = DOCS_DIR / "ADR"
API_DOCS_DIR = DOCS_DIR / "api"
ARCHITECTURE_DIR = DOCS_DIR / "architecture"
DIAGRAMS_DIR = DOCS_DIR / "diagrams"
MEETING_NOTES_DIR = DOCS_DIR / "meeting-notes"
SRS_DIR = DOCS_DIR / "SRS"

ROADMAP_FILE = DOCS_DIR / "ROADMAP.md"
SRS_FILE = SRS_DIR / "Project-Aquila-SRS.md"

# ----------------------------------------------------------------------
# Configuration Files
# ----------------------------------------------------------------------

BENCHMARK_CONFIG = CONFIGS_DIR / "benchmark.yaml"
CLUSTER_CONFIG = CONFIGS_DIR / "cluster.yaml"
CONTROLLER_CONFIG = CONFIGS_DIR / "controller.yaml"
DEPLOYMENT_CONFIG = CONFIGS_DIR / "deployment.yaml"
LOGGING_CONFIG = CONFIGS_DIR / "logging.yaml"
NETWORK_CONFIG = CONFIGS_DIR / "network.yaml"

#: The Deployment Controller service's own server-side configuration
#: (bind address, TLS material, database location, enrollment policy)
#: -- distinct from ``CONTROLLER_CONFIG`` above, which is the
#: *client*-facing "how do I reach the Controller" configuration
#: shipped on deployment media. See
#: ``config.schemas.controller_server_schema`` for the full rationale.
CONTROLLER_SERVER_CONFIG = CONFIGS_DIR / "controller_server.yaml"

# ----------------------------------------------------------------------
# Data (runtime, persistent service state -- not build output)
# ----------------------------------------------------------------------

#: The Deployment Controller's persistent store (Inventory System
#: records, deployment sessions/reports, benchmark results, and node
#: approval decisions -- see ``inventory.database.InventoryDatabase``).
INVENTORY_DATABASE_FILE = DATA_DIR / "inventory.db"

# ----------------------------------------------------------------------
# USB Deployment
# ----------------------------------------------------------------------

USB_PHASE1_DIR = USB_DIR / "phase1"
USB_PHASE2_DIR = USB_DIR / "phase2"

# ----------------------------------------------------------------------
# Build Output
# ----------------------------------------------------------------------

DIST_DIR = BUILD_DIR / "dist"
TEMP_DIR = BUILD_DIR / "temp"
LOG_DIR = BUILD_DIR / "logs"
CACHE_DIR = BUILD_DIR / "cache"

# ----------------------------------------------------------------------
# Repository Files
# ----------------------------------------------------------------------

README_FILE = PROJECT_ROOT / "README.md"
CHANGELOG_FILE = PROJECT_ROOT / "CHANGELOG.md"
LICENSE_FILE = PROJECT_ROOT / "LICENSE"
REQUIREMENTS_FILE = PROJECT_ROOT / "requirements.txt"
PYPROJECT_FILE = PROJECT_ROOT / "pyproject.toml"

# ----------------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------------

def ensure_directory(path: Path) -> Path:
    """
    Create a directory if it does not already exist.
    """

    path.mkdir(
        parents=True,
        exist_ok=True,
    )

    return path


def ensure_build_directories() -> None:
    """
    Create build-related directories.
    """

    directories = (
        BUILD_DIR,
        DIST_DIR,
        TEMP_DIR,
        LOG_DIR,
        CACHE_DIR,
    )

    for directory in directories:
        ensure_directory(directory)


def repository_root() -> Path:
    """
    Return the repository root.
    """

    return PROJECT_ROOT


# ----------------------------------------------------------------------
# Public Exports
# ----------------------------------------------------------------------

__all__ = [
    "PROJECT_ROOT",
    "SRC_ROOT",
    "COMMON_DIR",
    "ASSETS_DIR",
    "BUILD_DIR",
    "CONFIGS_DIR",
    "DATA_DIR",
    "DOCS_DIR",
    "RELEASES_DIR",
    "SCRIPTS_DIR",
    "TESTS_DIR",
    "TOOLS_DIR",
    "USB_DIR",
    "ICONS_DIR",
    "IMAGES_DIR",
    "LOGOS_DIR",
    "ADR_DIR",
    "API_DOCS_DIR",
    "ARCHITECTURE_DIR",
    "DIAGRAMS_DIR",
    "MEETING_NOTES_DIR",
    "SRS_DIR",
    "ROADMAP_FILE",
    "SRS_FILE",
    "BENCHMARK_CONFIG",
    "CLUSTER_CONFIG",
    "CONTROLLER_CONFIG",
    "CONTROLLER_SERVER_CONFIG",
    "DEPLOYMENT_CONFIG",
    "INVENTORY_DATABASE_FILE",
    "LOGGING_CONFIG",
    "NETWORK_CONFIG",
    "USB_PHASE1_DIR",
    "USB_PHASE2_DIR",
    "DIST_DIR",
    "TEMP_DIR",
    "LOG_DIR",
    "CACHE_DIR",
    "README_FILE",
    "CHANGELOG_FILE",
    "LICENSE_FILE",
    "REQUIREMENTS_FILE",
    "PYPROJECT_FILE",
    "ensure_directory",
    "ensure_build_directories",
    "repository_root",
]