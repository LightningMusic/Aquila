"""
Project Orion
=============

Provisioning Exceptions

Defines provisioning-related exceptions used
throughout Project Orion.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from common.exceptions.application import OrionError


class ProvisioningError(OrionError):
    """
    Base class for all provisioning-related exceptions.
    """


class ProvisioningInitializationError(ProvisioningError):
    """
    Raised when the provisioning subsystem
    cannot initialize.
    """


class ProvisioningConfigurationError(ProvisioningError):
    """
    Raised when provisioning configuration
    is invalid.
    """


class ProvisioningValidationError(ProvisioningError):
    """
    Raised when provisioning validation fails.
    """


class ProvisioningExecutionError(ProvisioningError):
    """
    Raised when a provisioning operation fails.
    """


class ProvisioningTimeoutError(ProvisioningError):
    """
    Raised when a provisioning operation
    exceeds its timeout.
    """


class ProvisioningCancelledError(ProvisioningError):
    """
    Raised when provisioning is cancelled.
    """


# ----------------------------------------------------------------------
# Disk Operations
# ----------------------------------------------------------------------


class DiskProvisioningError(ProvisioningError):
    """
    Base disk provisioning exception.
    """


class DiskDetectionError(DiskProvisioningError):
    """
    Raised when target disks cannot be detected.
    """


class DiskPartitionError(DiskProvisioningError):
    """
    Raised when partition creation fails.
    """


class DiskFormattingError(DiskProvisioningError):
    """
    Raised when filesystem formatting fails.
    """


class DiskMountError(DiskProvisioningError):
    """
    Raised when mounting a filesystem fails.
    """


# ----------------------------------------------------------------------
# Installation
# ----------------------------------------------------------------------


class InstallationError(ProvisioningError):
    """
    Base installation exception.
    """


class IsoNotFoundError(InstallationError):
    """
    Raised when the required installation
    ISO cannot be located.
    """


class InstallationMediaError(InstallationError):
    """
    Raised when installation media is invalid
    or corrupted.
    """


class ProxmoxInstallationError(InstallationError):
    """
    Raised when Proxmox VE installation fails.
    """


class BootloaderError(InstallationError):
    """
    Raised when bootloader installation fails.
    """


# ----------------------------------------------------------------------
# Packages
# ----------------------------------------------------------------------


class PackageError(ProvisioningError):
    """
    Base package exception.
    """


class PackageInstallationError(PackageError):
    """
    Raised when package installation fails.
    """


class PackageVerificationError(PackageError):
    """
    Raised when installed packages cannot
    be verified.
    """


class RepositoryError(PackageError):
    """
    Raised when package repositories
    are unavailable or invalid.
    """


# ----------------------------------------------------------------------
# Network
# ----------------------------------------------------------------------


class ProvisioningNetworkError(ProvisioningError):
    """
    Base provisioning networking exception.
    """


class NetworkConfigurationError(ProvisioningNetworkError):
    """
    Raised when network configuration
    during provisioning fails.
    """


class HostnameConfigurationError(ProvisioningNetworkError):
    """
    Raised when hostname configuration fails.
    """


class DNSConfigurationError(ProvisioningNetworkError):
    """
    Raised when DNS configuration fails.
    """


# ----------------------------------------------------------------------
# System Configuration
# ----------------------------------------------------------------------


class SystemConfigurationError(ProvisioningError):
    """
    Raised when system configuration fails.
    """


class UserConfigurationError(SystemConfigurationError):
    """
    Raised when creating or configuring
    users fails.
    """


class ServiceConfigurationError(SystemConfigurationError):
    """
    Raised when configuring system services
    fails.
    """


# ----------------------------------------------------------------------
# Reboot
# ----------------------------------------------------------------------


class RebootError(ProvisioningError):
    """
    Raised when the provisioned system
    cannot reboot successfully.
    """


class BootVerificationError(ProvisioningError):
    """
    Raised when the newly provisioned
    system fails to boot correctly.
    """


# ----------------------------------------------------------------------
# Verification
# ----------------------------------------------------------------------


class ProvisioningVerificationError(ProvisioningError):
    """
    Raised when post-install verification fails.
    """


class ProvisioningHealthCheckError(ProvisioningError):
    """
    Raised when post-install health checks fail.
    """


# ----------------------------------------------------------------------
# Reports
# ----------------------------------------------------------------------


class ProvisioningReportError(ProvisioningError):
    """
    Raised when provisioning reports
    cannot be generated.
    """


class ProvisioningExportError(ProvisioningError):
    """
    Raised when provisioning results
    cannot be exported.
    """


__all__ = [
    "BootVerificationError",
    "BootloaderError",
    "DNSConfigurationError",
    "DiskDetectionError",
    "DiskFormattingError",
    "DiskMountError",
    "DiskPartitionError",
    "DiskProvisioningError",
    "HostnameConfigurationError",
    "InstallationError",
    "InstallationMediaError",
    "IsoNotFoundError",
    "NetworkConfigurationError",
    "PackageError",
    "PackageInstallationError",
    "PackageVerificationError",
    "ProvisioningCancelledError",
    "ProvisioningConfigurationError",
    "ProvisioningError",
    "ProvisioningExecutionError",
    "ProvisioningExportError",
    "ProvisioningHealthCheckError",
    "ProvisioningInitializationError",
    "ProvisioningNetworkError",
    "ProvisioningReportError",
    "ProvisioningTimeoutError",
    "ProvisioningValidationError",
    "ProvisioningVerificationError",
    "ProxmoxInstallationError",
    "RebootError",
    "RepositoryError",
    "ServiceConfigurationError",
    "SystemConfigurationError",
    "UserConfigurationError",
]