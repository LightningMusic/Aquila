"""
Project Orion
=============

API Models

Defines generic models used by the API subsystem.

These models describe HTTP requests and responses and
are intentionally independent of any specific API such
as Proxmox VE.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ApiRequest:
    """
    Represents an outgoing API request.
    """

    method: str
    endpoint: str

    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    payload: Any | None = None
    timeout: int | None = None


@dataclass(slots=True)
class ApiResponse:
    """
    Represents a successful API response.
    """

    status_code: int

    headers: dict[str, str] = field(default_factory=dict)
    body: Any | None = None

    @property
    def ok(self) -> bool:
        """
        True if the response status indicates success.
        """

        return 200 <= self.status_code < 300


@dataclass(slots=True)
class ApiError:
    """
    Represents an API error returned by a server.
    """

    status_code: int
    message: str

    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AuthenticationToken:
    """
    Authentication token returned by an API.
    """

    token: str

    expires_at: str | None = None

    token_type: str = "Bearer"


@dataclass(slots=True)
class ApiConnectionSettings:
    """
    Connection settings for an API endpoint.
    """

    base_url: str

    username: str | None = None

    password: str | None = None

    verify_ssl: bool = True

    timeout: int = 30


__all__ = [
    "ApiConnectionSettings",
    "ApiError",
    "ApiRequest",
    "ApiResponse",
    "AuthenticationToken",
]