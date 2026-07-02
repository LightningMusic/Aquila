"""
Project Orion
=============

Application Version Information

Provides a single source of truth for application metadata.

Every subsystem should retrieve application information from this
module rather than defining duplicate constants.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass

# ----------------------------------------------------------------------
# Version Components
# ----------------------------------------------------------------------

VERSION_MAJOR: int = 0
VERSION_MINOR: int = 1
VERSION_PATCH: int = 0

VERSION: str = (
    f"{VERSION_MAJOR}."
    f"{VERSION_MINOR}."
    f"{VERSION_PATCH}"
)

# ----------------------------------------------------------------------
# Application Metadata
# ----------------------------------------------------------------------

APPLICATION_NAME: str = "Project Orion"

APPLICATION_VERSION: str = VERSION

APPLICATION_AUTHOR: str = "LightningMusic"

APPLICATION_LICENSE: str = "MIT"

APPLICATION_DESCRIPTION: str = (
    "Automated laptop deployment, provisioning, "
    "and Proxmox cluster integration."
)

APPLICATION_REPOSITORY: str = (
    "https://github.com/LightningMusic/Project-Orion"
)

APPLICATION_COPYRIGHT: str = (
    "Copyright (c) 2026 LightningMusic"
)


# ----------------------------------------------------------------------
# Version Information
# ----------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ApplicationVersion:
    """
    Immutable application metadata.
    """

    name: str
    version: str
    author: str
    description: str
    license: str
    repository: str
    copyright: str


APPLICATION = ApplicationVersion(
    name=APPLICATION_NAME,
    version=APPLICATION_VERSION,
    author=APPLICATION_AUTHOR,
    description=APPLICATION_DESCRIPTION,
    license=APPLICATION_LICENSE,
    repository=APPLICATION_REPOSITORY,
    copyright=APPLICATION_COPYRIGHT,
)

# ----------------------------------------------------------------------
# Public Exports
# ----------------------------------------------------------------------

__all__ = [
    "VERSION_MAJOR",
    "VERSION_MINOR",
    "VERSION_PATCH",
    "VERSION",
    "APPLICATION_NAME",
    "APPLICATION_VERSION",
    "APPLICATION_AUTHOR",
    "APPLICATION_LICENSE",
    "APPLICATION_DESCRIPTION",
    "APPLICATION_REPOSITORY",
    "APPLICATION_COPYRIGHT",
    "APPLICATION",
    "ApplicationVersion",
]