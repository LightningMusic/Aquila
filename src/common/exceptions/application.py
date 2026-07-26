"""
Project Aquila
=============

Application Exceptions

Defines the base exception hierarchy for Project Aquila.

Every custom exception in Aquila should ultimately inherit
from AquilaError.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from typing import Any


class AquilaError(Exception):
    """
    Base class for every Aquila exception.
    """

    def __init__(self, message: str = "An Aquila error occurred.") -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


class AquilaInitializationError(AquilaError):
    """
    Raised when Aquila cannot initialize correctly.
    """


class AquilaShutdownError(AquilaError):
    """
    Raised when Aquila cannot shut down cleanly.
    """


class AquilaConfigurationError(AquilaError):
    """
    Raised when application configuration is invalid.
    """


class AquilaValidationError(AquilaError):
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


class AquilaStateError(AquilaError):
    """
    Raised when an object is in an invalid state.
    """


class AquilaTimeoutError(AquilaError):
    """
    Raised when an operation exceeds its timeout.
    """


class AquilaCancelledError(AquilaError):
    """
    Raised when an operation is cancelled.
    """


class AquilaPermissionError(AquilaError):
    """
    Raised when an operation lacks required permissions.
    """


class AquilaNotFoundError(AquilaError):
    """
    Raised when a requested resource cannot be found.
    """


class AquilaAlreadyExistsError(AquilaError):
    """
    Raised when attempting to create something that
    already exists.
    """


class AquilaUnsupportedError(AquilaError):
    """
    Raised when a requested operation is unsupported.
    """


class AquilaDependencyError(AquilaError):
    """
    Raised when a required dependency is unavailable.
    """


class AquilaEnvironmentError(AquilaError):
    """
    Raised when the host environment does not satisfy
    Aquila's requirements.
    """


class AquilaOperationError(AquilaError):
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


class AquilaInternalError(AquilaError):
    """
    Raised when Aquila encounters an unexpected internal
    error.
    """


class AquilaDataError(AquilaError):
    """
    Raised when data is corrupt, malformed,
    or otherwise unusable.
    """


__all__ = [
    "AquilaAlreadyExistsError",
    "AquilaCancelledError",
    "AquilaConfigurationError",
    "AquilaDataError",
    "AquilaDependencyError",
    "AquilaEnvironmentError",
    "AquilaError",
    "AquilaInitializationError",
    "AquilaInternalError",
    "AquilaNotFoundError",
    "AquilaOperationError",
    "AquilaPermissionError",
    "AquilaShutdownError",
    "AquilaStateError",
    "AquilaTimeoutError",
    "AquilaUnsupportedError",
    "AquilaValidationError",
]