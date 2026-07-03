"""
Project Orion
=============

Application Exceptions

Defines the base exception hierarchy for Project Orion.

Every custom exception in Orion should ultimately inherit
from OrionError.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from typing import Any


class OrionError(Exception):
    """
    Base class for every Orion exception.
    """

    def __init__(self, message: str = "An Orion error occurred.") -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


class OrionInitializationError(OrionError):
    """
    Raised when Orion cannot initialize correctly.
    """


class OrionShutdownError(OrionError):
    """
    Raised when Orion cannot shut down cleanly.
    """


class OrionConfigurationError(OrionError):
    """
    Raised when application configuration is invalid.
    """


class OrionValidationError(OrionError):
    """
    Raised when application validation fails.
    """

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.field = field
        self.value = value


class OrionStateError(OrionError):
    """
    Raised when an object is in an invalid state.
    """


class OrionTimeoutError(OrionError):
    """
    Raised when an operation exceeds its timeout.
    """


class OrionCancelledError(OrionError):
    """
    Raised when an operation is cancelled.
    """


class OrionPermissionError(OrionError):
    """
    Raised when an operation lacks required permissions.
    """


class OrionNotFoundError(OrionError):
    """
    Raised when a requested resource cannot be found.
    """


class OrionAlreadyExistsError(OrionError):
    """
    Raised when attempting to create something that
    already exists.
    """


class OrionUnsupportedError(OrionError):
    """
    Raised when a requested operation is unsupported.
    """


class OrionDependencyError(OrionError):
    """
    Raised when a required dependency is unavailable.
    """


class OrionEnvironmentError(OrionError):
    """
    Raised when the host environment does not satisfy
    Orion's requirements.
    """


class OrionOperationError(OrionError):
    """
    Raised when an operation fails.
    """

    def __init__(
        self,
        operation: str,
        message: str,
    ) -> None:
        self.operation = operation
        super().__init__(f"{operation}: {message}")


class OrionInternalError(OrionError):
    """
    Raised when Orion encounters an unexpected internal
    error.
    """


class OrionDataError(OrionError):
    """
    Raised when data is corrupt, malformed,
    or otherwise unusable.
    """


__all__ = [
    "OrionAlreadyExistsError",
    "OrionCancelledError",
    "OrionConfigurationError",
    "OrionDataError",
    "OrionDependencyError",
    "OrionEnvironmentError",
    "OrionError",
    "OrionInitializationError",
    "OrionInternalError",
    "OrionNotFoundError",
    "OrionOperationError",
    "OrionPermissionError",
    "OrionShutdownError",
    "OrionStateError",
    "OrionTimeoutError",
    "OrionUnsupportedError",
    "OrionValidationError",
]