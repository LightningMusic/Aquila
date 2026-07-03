"""
Project Orion
=============

Filesystem Constants

Defines filesystem-related constants used throughout
Project Orion.

This module serves as the single source of truth for
directory names, filenames, file extensions, and
filesystem defaults.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

# ----------------------------------------------------------------------
# General
# ----------------------------------------------------------------------

PATH_SEPARATOR = "/"

DEFAULT_ENCODING = "utf-8"

DEFAULT_BUFFER_SIZE = 1024 * 1024  # 1 MiB

# ----------------------------------------------------------------------
# Directory Names
# ----------------------------------------------------------------------

SRC_DIRECTORY = "src"

CONFIG_DIRECTORY = "configs"

DOCS_DIRECTORY = "docs"

TEST_DIRECTORY = "tests"

BUILD_DIRECTORY = "build"

TOOLS_DIRECTORY = "tools"

USB_DIRECTORY = "usb"

RELEASE_DIRECTORY = "releases"

ASSETS_DIRECTORY = "assets"

LOG_DIRECTORY = "logs"

REPORT_DIRECTORY = "reports"

RECOVERY_DIRECTORY = "recovery"

BENCHMARK_DIRECTORY = "benchmark"

TEMP_DIRECTORY = "temp"

CACHE_DIRECTORY = ".cache"

# ----------------------------------------------------------------------
# USB Layout
# ----------------------------------------------------------------------

USB_PHASE_ONE_DIRECTORY = "phase1"

USB_PHASE_TWO_DIRECTORY = "phase2"

USB_REPORT_DIRECTORY = "reports"

USB_RECOVERY_DIRECTORY = "recovery"

USB_LOG_DIRECTORY = "logs"

# ----------------------------------------------------------------------
# Configuration Files
# ----------------------------------------------------------------------

APPLICATION_CONFIGURATION = "application.yaml"

CLUSTER_CONFIGURATION = "cluster.yaml"

CONTROLLER_CONFIGURATION = "controller.yaml"

DEPLOYMENT_CONFIGURATION = "deployment.yaml"

LOGGING_CONFIGURATION = "logging.yaml"

NETWORK_CONFIGURATION = "network.yaml"

BENCHMARK_CONFIGURATION = "benchmark.yaml"

# ----------------------------------------------------------------------
# Standard Reports
# ----------------------------------------------------------------------

HARDWARE_REPORT = "hardware_report.json"

DEPLOYMENT_REPORT = "deployment_report.json"

BENCHMARK_REPORT = "benchmark_report.json"

RECOVERY_REPORT = "recovery_report.json"

INVENTORY_REPORT = "inventory.json"

SYSTEM_REPORT = "system_report.json"

# ----------------------------------------------------------------------
# Log Files
# ----------------------------------------------------------------------

APPLICATION_LOG = "application.log"

DEPLOYMENT_LOG = "deployment.log"

INSTALLATION_LOG = "installation.log"

BENCHMARK_LOG = "benchmark.log"

RECOVERY_LOG = "recovery.log"

NETWORK_LOG = "network.log"

# ----------------------------------------------------------------------
# File Extensions
# ----------------------------------------------------------------------

JSON_EXTENSION = ".json"

YAML_EXTENSION = ".yaml"

LOG_EXTENSION = ".log"

TEXT_EXTENSION = ".txt"

MARKDOWN_EXTENSION = ".md"

CSV_EXTENSION = ".csv"

XML_EXTENSION = ".xml"

HTML_EXTENSION = ".html"

PYTHON_EXTENSION = ".py"

# ----------------------------------------------------------------------
# Common Filenames
# ----------------------------------------------------------------------

README_FILE = "README.md"

LICENSE_FILE = "LICENSE"

CHANGELOG_FILE = "CHANGELOG.md"

PYPROJECT_FILE = "pyproject.toml"

REQUIREMENTS_FILE = "requirements.txt"

GITIGNORE_FILE = ".gitignore"

# ----------------------------------------------------------------------
# Temporary Files
# ----------------------------------------------------------------------

TEMP_PREFIX = "orion_"

TEMP_SUFFIX = ".tmp"

BACKUP_SUFFIX = ".bak"

# ----------------------------------------------------------------------
# Size Constants
# ----------------------------------------------------------------------

ONE_KIB = 1024

ONE_MIB = 1024 * ONE_KIB

ONE_GIB = 1024 * ONE_MIB

ONE_TIB = 1024 * ONE_GIB

# ----------------------------------------------------------------------
# Public Exports
# ----------------------------------------------------------------------

__all__ = [
    "APPLICATION_CONFIGURATION",
    "APPLICATION_LOG",
    "ASSETS_DIRECTORY",
    "BACKUP_SUFFIX",
    "BENCHMARK_CONFIGURATION",
    "BENCHMARK_DIRECTORY",
    "BENCHMARK_LOG",
    "BENCHMARK_REPORT",
    "BUILD_DIRECTORY",
    "CACHE_DIRECTORY",
    "CHANGELOG_FILE",
    "CLUSTER_CONFIGURATION",
    "CONFIG_DIRECTORY",
    "CONTROLLER_CONFIGURATION",
    "CSV_EXTENSION",
    "DEFAULT_BUFFER_SIZE",
    "DEFAULT_ENCODING",
    "DEPLOYMENT_CONFIGURATION",
    "DEPLOYMENT_LOG",
    "DEPLOYMENT_REPORT",
    "DOCS_DIRECTORY",
    "GITIGNORE_FILE",
    "HARDWARE_REPORT",
    "HTML_EXTENSION",
    "INSTALLATION_LOG",
    "INVENTORY_REPORT",
    "JSON_EXTENSION",
    "LICENSE_FILE",
    "LOG_DIRECTORY",
    "LOG_EXTENSION",
    "LOGGING_CONFIGURATION",
    "MARKDOWN_EXTENSION",
    "NETWORK_CONFIGURATION",
    "NETWORK_LOG",
    "ONE_GIB",
    "ONE_KIB",
    "ONE_MIB",
    "ONE_TIB",
    "PATH_SEPARATOR",
    "PYPROJECT_FILE",
    "PYTHON_EXTENSION",
    "README_FILE",
    "RECOVERY_DIRECTORY",
    "RECOVERY_LOG",
    "RECOVERY_REPORT",
    "RELEASE_DIRECTORY",
    "REPORT_DIRECTORY",
    "REQUIREMENTS_FILE",
    "SRC_DIRECTORY",
    "SYSTEM_REPORT",
    "TEMP_DIRECTORY",
    "TEMP_PREFIX",
    "TEMP_SUFFIX",
    "TEST_DIRECTORY",
    "TEXT_EXTENSION",
    "TOOLS_DIRECTORY",
    "USB_DIRECTORY",
    "USB_LOG_DIRECTORY",
    "USB_PHASE_ONE_DIRECTORY",
    "USB_PHASE_TWO_DIRECTORY",
    "USB_RECOVERY_DIRECTORY",
    "USB_REPORT_DIRECTORY",
    "XML_EXTENSION",
    "YAML_EXTENSION",
]