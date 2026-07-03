"""
Project Orion
=============

Recovery Exceptions

Defines recovery-related exceptions used
throughout Project Orion.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from common.exceptions.application import OrionError


class RecoveryError(OrionError):
    """
    Base class for all recovery-related exceptions.
    """


class RecoveryInitializationError(RecoveryError):
    """
    Raised when the recovery subsystem
    cannot initialize.
    """


class RecoveryConfigurationError(RecoveryError):
    """
    Raised when recovery configuration
    is invalid.
    """


class RecoveryValidationError(RecoveryError):
    """
    Raised when recovery validation fails.
    """


class RecoveryExecutionError(RecoveryError):
    """
    Raised when a recovery operation fails.
    """


class RecoveryTimeoutError(RecoveryError):
    """
    Raised when a recovery operation
    exceeds its timeout.
    """


class RecoveryCancelledError(RecoveryError):
    """
    Raised when recovery is cancelled.
    """


# ----------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------


class RecoveryDiscoveryError(RecoveryError):
    """
    Raised when recoverable data
    cannot be discovered.
    """


class UserProfileDiscoveryError(RecoveryDiscoveryError):
    """
    Raised when user profiles
    cannot be located.
    """


class BrowserDiscoveryError(RecoveryDiscoveryError):
    """
    Raised when supported browsers
    cannot be detected.
    """


# ----------------------------------------------------------------------
# Copy Operations
# ----------------------------------------------------------------------


class CopyOperationError(RecoveryError):
    """
    Base exception for copy operations.
    """


class FileCopyError(CopyOperationError):
    """
    Raised when copying files fails.
    """


class DirectoryCopyError(CopyOperationError):
    """
    Raised when copying directories fails.
    """


class PermissionCopyError(CopyOperationError):
    """
    Raised when files cannot be copied
    due to insufficient permissions.
    """


class InsufficientStorageError(CopyOperationError):
    """
    Raised when insufficient storage
    exists for recovery.
    """


# ----------------------------------------------------------------------
# Browser Recovery
# ----------------------------------------------------------------------


class BrowserRecoveryError(RecoveryError):
    """
    Base browser recovery exception.
    """


class BrowserProfileError(BrowserRecoveryError):
    """
    Raised when browser profiles
    cannot be processed.
    """


class BrowserBookmarkError(BrowserRecoveryError):
    """
    Raised when browser bookmarks
    cannot be recovered.
    """


class BrowserPasswordError(BrowserRecoveryError):
    """
    Raised when browser password
    recovery fails.
    """


class BrowserExtensionError(BrowserRecoveryError):
    """
    Raised when browser extensions
    cannot be recovered.
    """


# ----------------------------------------------------------------------
# Archive Operations
# ----------------------------------------------------------------------


class ArchiveError(RecoveryError):
    """
    Base archive exception.
    """


class ArchiveCreationError(ArchiveError):
    """
    Raised when creating a recovery
    archive fails.
    """


class ArchiveExtractionError(ArchiveError):
    """
    Raised when extracting a recovery
    archive fails.
    """


class ArchiveVerificationError(ArchiveError):
    """
    Raised when archive integrity
    verification fails.
    """


# ----------------------------------------------------------------------
# Verification
# ----------------------------------------------------------------------


class RecoveryVerificationError(RecoveryError):
    """
    Raised when recovered data
    cannot be verified.
    """


class ChecksumVerificationError(RecoveryVerificationError):
    """
    Raised when checksum verification fails.
    """


class DataIntegrityError(RecoveryVerificationError):
    """
    Raised when recovered data
    is corrupted.
    """


# ----------------------------------------------------------------------
# Restore Operations
# ----------------------------------------------------------------------


class RestoreError(RecoveryError):
    """
    Base restore exception.
    """


class RestorePreparationError(RestoreError):
    """
    Raised while preparing
    a restore operation.
    """


class RestoreFailureError(RestoreError):
    """
    Raised when restoring data fails.
    """


class RestoreConflictError(RestoreError):
    """
    Raised when restored files
    conflict with existing files.
    """


# ----------------------------------------------------------------------
# Reports
# ----------------------------------------------------------------------


class RecoveryReportError(RecoveryError):
    """
    Raised when recovery reports
    cannot be generated.
    """


class RecoveryExportError(RecoveryError):
    """
    Raised when recovery data
    cannot be exported.
    """


__all__ = [
    "ArchiveCreationError",
    "ArchiveError",
    "ArchiveExtractionError",
    "ArchiveVerificationError",
    "BrowserBookmarkError",
    "BrowserDiscoveryError",
    "BrowserExtensionError",
    "BrowserPasswordError",
    "BrowserProfileError",
    "BrowserRecoveryError",
    "ChecksumVerificationError",
    "CopyOperationError",
    "DataIntegrityError",
    "DirectoryCopyError",
    "FileCopyError",
    "InsufficientStorageError",
    "PermissionCopyError",
    "RecoveryCancelledError",
    "RecoveryConfigurationError",
    "RecoveryDiscoveryError",
    "RecoveryError",
    "RecoveryExecutionError",
    "RecoveryExportError",
    "RecoveryInitializationError",
    "RecoveryReportError",
    "RecoveryTimeoutError",
    "RecoveryValidationError",
    "RecoveryVerificationError",
    "RestoreConflictError",
    "RestoreError",
    "RestoreFailureError",
    "RestorePreparationError",
    "UserProfileDiscoveryError",
]