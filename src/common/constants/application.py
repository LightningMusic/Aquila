"""
Project Orion
=============

Application Constants

Defines application-wide metadata and immutable constants used
throughout Project Orion.

These values should remain constant during application runtime.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

# ----------------------------------------------------------------------
# Application Identity
# ----------------------------------------------------------------------

APPLICATION_NAME = "Project Orion"

APPLICATION_SHORT_NAME = "Orion"

APPLICATION_DESCRIPTION = (
    "Automated deployment and provisioning platform for "
    "repurposing enterprise and consumer hardware into "
    "a managed Proxmox cluster."
)

APPLICATION_AUTHOR = "Project Orion Development Team"

APPLICATION_LICENSE = "MIT"

APPLICATION_COPYRIGHT = (
    "Copyright (c) 2026 Project Orion Development Team"
)

# ----------------------------------------------------------------------
# Version Information
# ----------------------------------------------------------------------

APPLICATION_VERSION = "0.1.0"

APPLICATION_STATUS = "Development"

APPLICATION_CODENAME = "Genesis"

# ----------------------------------------------------------------------
# Repository Information
# ----------------------------------------------------------------------

REPOSITORY_NAME = "Project-Orion"

REPOSITORY_OWNER = "LightningMusic"

REPOSITORY_URL = (
    "https://github.com/LightningMusic/Project-Orion"
)

# ----------------------------------------------------------------------
# Runtime Requirements
# ----------------------------------------------------------------------

MINIMUM_PYTHON_VERSION = (3, 12)

SUPPORTED_OPERATING_SYSTEMS = (
    "Windows",
    "Linux",
)

SUPPORTED_DEPLOYMENT_TARGET = "Proxmox VE"

# ----------------------------------------------------------------------
# Default Encoding
# ----------------------------------------------------------------------

DEFAULT_TEXT_ENCODING = "utf-8"

DEFAULT_LINE_ENDING = "\n"

# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------

DEFAULT_LOGGER_NAME = "orion"

DEFAULT_TIMEZONE = "UTC"

# ----------------------------------------------------------------------
# Exit Codes
# ----------------------------------------------------------------------

EXIT_SUCCESS = 0

EXIT_FAILURE = 1

EXIT_CONFIGURATION_ERROR = 2

EXIT_DEPLOYMENT_ERROR = 3

EXIT_NETWORK_ERROR = 4

EXIT_HARDWARE_ERROR = 5

EXIT_USER_CANCELLED = 10

# ----------------------------------------------------------------------
# Feature Flags
# ----------------------------------------------------------------------

DEVELOPMENT_MODE = True

DEBUG_MODE = True

SAFE_MODE_DEFAULT = True

# ----------------------------------------------------------------------
# Public Exports
# ----------------------------------------------------------------------

__all__ = [
    "APPLICATION_AUTHOR",
    "APPLICATION_CODENAME",
    "APPLICATION_COPYRIGHT",
    "APPLICATION_DESCRIPTION",
    "APPLICATION_LICENSE",
    "APPLICATION_NAME",
    "APPLICATION_SHORT_NAME",
    "APPLICATION_STATUS",
    "APPLICATION_VERSION",
    "DEBUG_MODE",
    "DEFAULT_LINE_ENDING",
    "DEFAULT_LOGGER_NAME",
    "DEFAULT_TEXT_ENCODING",
    "DEFAULT_TIMEZONE",
    "DEVELOPMENT_MODE",
    "EXIT_CONFIGURATION_ERROR",
    "EXIT_DEPLOYMENT_ERROR",
    "EXIT_FAILURE",
    "EXIT_HARDWARE_ERROR",
    "EXIT_NETWORK_ERROR",
    "EXIT_SUCCESS",
    "EXIT_USER_CANCELLED",
    "MINIMUM_PYTHON_VERSION",
    "REPOSITORY_NAME",
    "REPOSITORY_OWNER",
    "REPOSITORY_URL",
    "SAFE_MODE_DEFAULT",
    "SUPPORTED_DEPLOYMENT_TARGET",
    "SUPPORTED_OPERATING_SYSTEMS",
]