"""
Project Orion
=============

API Exceptions

Defines exceptions used throughout the
Project Orion API subsystem.

These exceptions cover:

    • HTTP communication
    • Authentication
    • Downloads
    • Connection management
    • Timeouts
    • SSL verification
    • Remote server failures

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from common.exceptions.application import OrionError


class ApiError(OrionError):
    """
    Base class for all API-related exceptions.
    """


# ==========================================================
# Connection
# ==========================================================


class ApiConnectionError(ApiError):
    """
    Raised when a connection to a remote API
    cannot be established.
    """


class ApiDisconnectedError(ApiConnectionError):
    """
    Raised when an operation is attempted while
    the client is disconnected.
    """


class ApiUnavailableError(ApiConnectionError):
    """
    Raised when the remote API is unavailable.
    """


class ApiTimeoutError(ApiConnectionError):
    """
    Raised when an API request times out.
    """


class ApiSSLError(ApiConnectionError):
    """
    Raised when SSL verification fails.
    """


# ==========================================================
# Authentication
# ==========================================================


class ApiAuthenticationError(ApiError):
    """
    Base authentication exception.
    """


class InvalidCredentialsError(ApiAuthenticationError):
    """
    Raised when supplied credentials
    are invalid.
    """


class AuthenticationRequiredError(ApiAuthenticationError):
    """
    Raised when authentication is required
    before performing an operation.
    """


class AuthenticationExpiredError(ApiAuthenticationError):
    """
    Raised when authentication has expired.
    """


class ApiTokenError(ApiAuthenticationError):
    """
    Raised when an API token is invalid.
    """


# ==========================================================
# Requests
# ==========================================================


class ApiRequestError(ApiError):
    """
    Raised when an HTTP request fails.
    """


class ApiResponseError(ApiError):
    """
    Raised when an invalid response
    is returned.
    """


class ApiStatusCodeError(ApiResponseError):
    """
    Raised when an unexpected HTTP status
    code is received.
    """

    def __init__(
        self,
        status_code: int,
        message: str = "",
    ) -> None:

        self.status_code = status_code

        if not message:
            message = f"Unexpected HTTP status code: {status_code}"

        super().__init__(message)


class ApiSerializationError(ApiError):
    """
    Raised when request serialization fails.
    """


class ApiDeserializationError(ApiError):
    """
    Raised when response deserialization fails.
    """


# ==========================================================
# Downloads
# ==========================================================


class DownloadError(ApiError):
    """
    Base download exception.
    """


class DownloadFailedError(DownloadError):
    """
    Raised when a download fails.
    """


class DownloadCancelledError(DownloadError):
    """
    Raised when a download is cancelled.
    """


class DownloadVerificationError(DownloadError):
    """
    Raised when a downloaded file
    fails verification.
    """


class ChecksumMismatchError(DownloadVerificationError):
    """
    Raised when a SHA256 checksum
    does not match the expected value.
    """


# ==========================================================
# Server
# ==========================================================


class ServerError(ApiError):
    """
    Base server exception.
    """


class ServerNotFoundError(ServerError):
    """
    Raised when the configured server
    cannot be found.
    """


class ServerConfigurationError(ServerError):
    """
    Raised when the server configuration
    is invalid.
    """


class ServerStateError(ServerError):
    """
    Raised when the server is in an
    invalid state.
    """


# ==========================================================
# Proxmox
# ==========================================================


class ProxmoxApiError(ApiError):
    """
    Base exception for Proxmox API failures.
    """


class ProxmoxVersionError(ProxmoxApiError):
    """
    Raised when the connected Proxmox version
    is unsupported.
    """


class ProxmoxPermissionError(ProxmoxApiError):
    """
    Raised when the authenticated user
    lacks sufficient permissions.
    """


# ==========================================================
# Export
# ==========================================================

__all__ = [
    "ApiAuthenticationError",
    "ApiConnectionError",
    "ApiDeserializationError",
    "ApiDisconnectedError",
    "ApiError",
    "ApiRequestError",
    "ApiResponseError",
    "ApiSSLError",
    "ApiSerializationError",
    "ApiStatusCodeError",
    "ApiTimeoutError",
    "ApiTokenError",
    "ApiUnavailableError",
    "AuthenticationExpiredError",
    "AuthenticationRequiredError",
    "ChecksumMismatchError",
    "DownloadCancelledError",
    "DownloadError",
    "DownloadFailedError",
    "DownloadVerificationError",
    "InvalidCredentialsError",
    "ProxmoxApiError",
    "ProxmoxPermissionError",
    "ProxmoxVersionError",
    "ServerConfigurationError",
    "ServerError",
    "ServerNotFoundError",
    "ServerStateError",
]