"""
Project Orion
=============

Logging Constants

Defines logging-related constants used throughout
Project Orion.

This module centralizes logger names, log levels,
default formats, rotation settings, and log filenames.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

# ----------------------------------------------------------------------
# Logger Names
# ----------------------------------------------------------------------

ROOT_LOGGER = "orion"

APPLICATION_LOGGER = "orion.application"

DEPLOYMENT_LOGGER = "orion.deployment"

RECOVERY_LOGGER = "orion.recovery"

INSPECTION_LOGGER = "orion.inspection"

PROVISIONING_LOGGER = "orion.provisioning"

NETWORK_LOGGER = "orion.network"

BENCHMARK_LOGGER = "orion.benchmark"

HARDWARE_LOGGER = "orion.hardware"

BOOTSTRAP_LOGGER = "orion.bootstrap"

INVENTORY_LOGGER = "orion.inventory"

API_LOGGER = "orion.api"

CLI_LOGGER = "orion.cli"

GUI_LOGGER = "orion.gui"

# ----------------------------------------------------------------------
# Logging Levels
# ----------------------------------------------------------------------

LOG_LEVEL_DEBUG = "DEBUG"

LOG_LEVEL_INFO = "INFO"

LOG_LEVEL_WARNING = "WARNING"

LOG_LEVEL_ERROR = "ERROR"

LOG_LEVEL_CRITICAL = "CRITICAL"

DEFAULT_LOG_LEVEL = LOG_LEVEL_INFO

# ----------------------------------------------------------------------
# Console Logging
# ----------------------------------------------------------------------

ENABLE_CONSOLE_LOGGING = True

CONSOLE_LOG_LEVEL = LOG_LEVEL_INFO

# ----------------------------------------------------------------------
# File Logging
# ----------------------------------------------------------------------

ENABLE_FILE_LOGGING = True

DEFAULT_LOG_DIRECTORY = "logs"

APPLICATION_LOG_FILE = "application.log"

DEPLOYMENT_LOG_FILE = "deployment.log"

RECOVERY_LOG_FILE = "recovery.log"

INSPECTION_LOG_FILE = "inspection.log"

PROVISIONING_LOG_FILE = "provisioning.log"

NETWORK_LOG_FILE = "network.log"

BENCHMARK_LOG_FILE = "benchmark.log"

BOOTSTRAP_LOG_FILE = "bootstrap.log"

HARDWARE_LOG_FILE = "hardware.log"

INVENTORY_LOG_FILE = "inventory.log"

API_LOG_FILE = "api.log"

CLI_LOG_FILE = "cli.log"

GUI_LOG_FILE = "gui.log"

# ----------------------------------------------------------------------
# Formatting
# ----------------------------------------------------------------------

DEFAULT_LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)

DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

DEBUG_LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | "
    "%(filename)s:%(lineno)d | %(message)s"
)

# ----------------------------------------------------------------------
# Rotation
# ----------------------------------------------------------------------

ENABLE_ROTATION = True

MAX_LOG_SIZE_MB = 10

MAX_LOG_FILES = 10

# ----------------------------------------------------------------------
# Performance Logging
# ----------------------------------------------------------------------

ENABLE_PERFORMANCE_LOGGING = True

PERFORMANCE_LOGGER = "orion.performance"

PERFORMANCE_LOG_FILE = "performance.log"

# ----------------------------------------------------------------------
# Event Logging
# ----------------------------------------------------------------------

ENABLE_EVENT_LOGGING = True

EVENT_LOGGER = "orion.events"

EVENT_LOG_FILE = "events.log"

# ----------------------------------------------------------------------
# Exception Logging
# ----------------------------------------------------------------------

LOG_EXCEPTIONS = True

LOG_TRACEBACKS = True

# ----------------------------------------------------------------------
# Verbosity
# ----------------------------------------------------------------------

VERBOSE_MODE = False

QUIET_MODE = False

# ----------------------------------------------------------------------
# ANSI Console Colors
# ----------------------------------------------------------------------

ENABLE_CONSOLE_COLORS = True

COLOR_DEBUG = "cyan"

COLOR_INFO = "green"

COLOR_WARNING = "yellow"

COLOR_ERROR = "red"

COLOR_CRITICAL = "magenta"

# ----------------------------------------------------------------------
# Public Exports
# ----------------------------------------------------------------------

__all__ = [
    "API_LOG_FILE",
    "API_LOGGER",
    "APPLICATION_LOG_FILE",
    "APPLICATION_LOGGER",
    "BENCHMARK_LOG_FILE",
    "BENCHMARK_LOGGER",
    "BOOTSTRAP_LOG_FILE",
    "BOOTSTRAP_LOGGER",
    "CLI_LOG_FILE",
    "CLI_LOGGER",
    "COLOR_CRITICAL",
    "COLOR_DEBUG",
    "COLOR_ERROR",
    "COLOR_INFO",
    "COLOR_WARNING",
    "CONSOLE_LOG_LEVEL",
    "DEBUG_LOG_FORMAT",
    "DEFAULT_DATE_FORMAT",
    "DEFAULT_LOG_DIRECTORY",
    "DEFAULT_LOG_FORMAT",
    "DEFAULT_LOG_LEVEL",
    "DEPLOYMENT_LOG_FILE",
    "DEPLOYMENT_LOGGER",
    "ENABLE_CONSOLE_COLORS",
    "ENABLE_CONSOLE_LOGGING",
    "ENABLE_EVENT_LOGGING",
    "ENABLE_FILE_LOGGING",
    "ENABLE_PERFORMANCE_LOGGING",
    "ENABLE_ROTATION",
    "EVENT_LOG_FILE",
    "EVENT_LOGGER",
    "GUI_LOG_FILE",
    "GUI_LOGGER",
    "HARDWARE_LOG_FILE",
    "HARDWARE_LOGGER",
    "INSPECTION_LOG_FILE",
    "INSPECTION_LOGGER",
    "INVENTORY_LOG_FILE",
    "INVENTORY_LOGGER",
    "LOG_EXCEPTIONS",
    "LOG_LEVEL_CRITICAL",
    "LOG_LEVEL_DEBUG",
    "LOG_LEVEL_ERROR",
    "LOG_LEVEL_INFO",
    "LOG_LEVEL_WARNING",
    "LOG_TRACEBACKS",
    "MAX_LOG_FILES",
    "MAX_LOG_SIZE_MB",
    "NETWORK_LOG_FILE",
    "NETWORK_LOGGER",
    "PERFORMANCE_LOG_FILE",
    "PERFORMANCE_LOGGER",
    "PROVISIONING_LOG_FILE",
    "PROVISIONING_LOGGER",
    "QUIET_MODE",
    "RECOVERY_LOG_FILE",
    "RECOVERY_LOGGER",
    "ROOT_LOGGER",
    "VERBOSE_MODE",
]