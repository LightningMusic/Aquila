"""
Project Aquila
=============

Application-wide constants.

This module contains immutable values used throughout Project Aquila.
No application logic should exist in this module.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from pathlib import Path

# =============================================================================
# General Application
# =============================================================================

APP_ENCODING: str = "utf-8"

DEFAULT_TIMEZONE: str = "UTC"

DEFAULT_DATE_FORMAT: str = "%Y-%m-%d"

DEFAULT_TIME_FORMAT: str = "%H:%M:%S"

DEFAULT_DATETIME_FORMAT: str = "%Y-%m-%d %H:%M:%S"

# =============================================================================
# Configuration
# =============================================================================

CONFIG_FILE_EXTENSION: str = ".yaml"

DEFAULT_CONFIG_DIRECTORY: str = "configs"

SUPPORTED_CONFIGURATION_VERSION: int = 1

# =============================================================================
# Logging
# =============================================================================

DEFAULT_LOG_LEVEL: str = "INFO"

DEFAULT_LOG_DIRECTORY: str = "logs"

DEFAULT_LOG_FILE: str = "aquila.log"

LOG_FILE_EXTENSION: str = ".log"

MAX_LOG_FILE_SIZE_MB: int = 25

LOG_BACKUP_COUNT: int = 10

# =============================================================================
# Deployment
# =============================================================================

DEPLOYMENT_REPORT_DIRECTORY: str = "reports"

DEPLOYMENT_TIMEOUT_SECONDS: int = 300

DEFAULT_HOSTNAME_PREFIX: str = "aquila-node"

DEFAULT_NODE_NAME_PREFIX: str = "node"

# =============================================================================
# Networking
# =============================================================================

ETHERNET_INTERFACE_PREFIXES: tuple[str, ...] = (
    "eth",
    "en",
)

NETWORK_CONNECTION_TIMEOUT_SECONDS: int = 10

NETWORK_RETRY_COUNT: int = 3

# =============================================================================
# Benchmarking
# =============================================================================

DEFAULT_BENCHMARK_DIRECTORY: str = "benchmarks"

DEFAULT_BENCHMARK_TIMEOUT_SECONDS: int = 600

# =============================================================================
# Hardware Inspection
# =============================================================================

SMART_TIMEOUT_SECONDS: int = 60

MINIMUM_SUPPORTED_MEMORY_GB: int = 4

MINIMUM_SUPPORTED_STORAGE_GB: int = 32

# =============================================================================
# Storage Preparation
# =============================================================================

MAX_CONFIRMATION_ATTEMPTS: int = 3

SANITIZATION_PASSES: int = 1

# =============================================================================
# USB Deployment
# =============================================================================

USB_PHASE1_DIRECTORY: str = "phase1"

USB_PHASE2_DIRECTORY: str = "phase2"

# =============================================================================
# Supported Platforms
# =============================================================================

SUPPORTED_PLATFORM_WINDOWS: str = "Windows"

SUPPORTED_PLATFORM_LINUX: str = "Linux"

SUPPORTED_PLATFORM_PROXMOX: str = "Proxmox"

# =============================================================================
# Proxmox
# =============================================================================

SUPPORTED_PROXMOX_MAJOR_VERSION: int = 9

SUPPORTED_PROXMOX_ISO_EXTENSION: str = ".iso"

DEFAULT_PROXMOX_ISO_DIRECTORY: str = "resources/iso"

# =============================================================================
# Build System
# =============================================================================

BUILD_DIRECTORY_NAME: str = "build"

RELEASE_DIRECTORY_NAME: str = "releases"

ASSETS_DIRECTORY_NAME: str = "assets"

TOOLS_DIRECTORY_NAME: str = "tools"

# =============================================================================
# Exit Codes
# =============================================================================

EXIT_SUCCESS: int = 0

EXIT_FAILURE: int = 1

EXIT_CONFIGURATION_ERROR: int = 10

EXIT_DEPLOYMENT_ERROR: int = 20

EXIT_NETWORK_ERROR: int = 30

EXIT_HARDWARE_ERROR: int = 40

# =============================================================================
# Common File Names
# =============================================================================

README_FILE_NAME: str = "README.md"

LICENSE_FILE_NAME: str = "LICENSE"

CHANGELOG_FILE_NAME: str = "CHANGELOG.md"

PYPROJECT_FILE_NAME: str = "pyproject.toml"

REQUIREMENTS_FILE_NAME: str = "requirements.txt"

# =============================================================================
# Common Directories
# =============================================================================

SRC_DIRECTORY_NAME: str = "src"

DOCS_DIRECTORY_NAME: str = "docs"

TESTS_DIRECTORY_NAME: str = "tests"

CONFIGS_DIRECTORY_NAME: str = "configs"

USB_DIRECTORY_NAME: str = "usb"

SCRIPTS_DIRECTORY_NAME: str = "scripts"

# =============================================================================
# Miscellaneous
# =============================================================================

EMPTY_STRING: str = ""

NEWLINE: str = "\n"

CURRENT_DIRECTORY: Path = Path(".")