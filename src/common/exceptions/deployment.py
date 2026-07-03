"""
Project Orion
=============

Deployment Exceptions

Defines deployment-related exceptions used
throughout Project Orion.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from common.exceptions.application import OrionError


class DeploymentError(OrionError):
    """
    Base class for all deployment-related exceptions.
    """


class DeploymentInitializationError(DeploymentError):
    """
    Raised when the deployment system cannot initialize.
    """


class DeploymentConfigurationError(DeploymentError):
    """
    Raised when deployment configuration is invalid.
    """


class DeploymentValidationError(DeploymentError):
    """
    Raised when deployment validation fails.
    """


class DeploymentExecutionError(DeploymentError):
    """
    Raised when a deployment operation fails.
    """


class DeploymentCancelledError(DeploymentError):
    """
    Raised when a deployment is cancelled.
    """


class DeploymentTimeoutError(DeploymentError):
    """
    Raised when a deployment exceeds its timeout.
    """


class DeploymentPreparationError(DeploymentError):
    """
    Raised during deployment preparation.
    """


class DeploymentSanitizationError(DeploymentError):
    """
    Raised while sanitizing the target system.
    """


class DeploymentRecoveryError(DeploymentError):
    """
    Raised while performing recovery operations.
    """


class DeploymentProvisioningError(DeploymentError):
    """
    Raised while provisioning the operating system.
    """


class DeploymentInstallationError(DeploymentError):
    """
    Raised while installing Proxmox VE.
    """


class DeploymentVerificationError(DeploymentError):
    """
    Raised when deployment verification fails.
    """


class DeploymentRebootError(DeploymentError):
    """
    Raised when a reboot operation fails.
    """


class DeploymentClusterError(DeploymentError):
    """
    Raised while joining or configuring
    the Proxmox cluster.
    """


class DeploymentNetworkError(DeploymentError):
    """
    Raised when deployment networking fails.
    """


class DeploymentStorageError(DeploymentError):
    """
    Raised when deployment storage operations fail.
    """


class DeploymentAuthenticationError(DeploymentError):
    """
    Raised when deployment authentication fails.
    """


class DeploymentAuthorizationError(DeploymentError):
    """
    Raised when deployment authorization fails.
    """


class DeploymentNodeError(DeploymentError):
    """
    Raised when operating on a deployment node fails.
    """


class DeploymentReportError(DeploymentError):
    """
    Raised when deployment reports cannot
    be generated.
    """


class DeploymentExportError(DeploymentError):
    """
    Raised when deployment results cannot
    be exported.
    """


class DeploymentRollbackError(DeploymentError):
    """
    Raised when deployment rollback fails.
    """


class DeploymentStateError(DeploymentError):
    """
    Raised when the deployment state
    becomes invalid.
    """


class DeploymentSessionError(DeploymentError):
    """
    Raised when a deployment session
    cannot be created or resumed.
    """


__all__ = [
    "DeploymentAuthenticationError",
    "DeploymentAuthorizationError",
    "DeploymentCancelledError",
    "DeploymentClusterError",
    "DeploymentConfigurationError",
    "DeploymentError",
    "DeploymentExecutionError",
    "DeploymentExportError",
    "DeploymentInitializationError",
    "DeploymentInstallationError",
    "DeploymentNetworkError",
    "DeploymentNodeError",
    "DeploymentPreparationError",
    "DeploymentProvisioningError",
    "DeploymentRecoveryError",
    "DeploymentRebootError",
    "DeploymentReportError",
    "DeploymentRollbackError",
    "DeploymentSanitizationError",
    "DeploymentSessionError",
    "DeploymentStateError",
    "DeploymentStorageError",
    "DeploymentTimeoutError",
    "DeploymentValidationError",
    "DeploymentVerificationError",
]