"""
Project Orion
=============

API Authentication

Provides authentication management for remote
API servers used by Project Orion.

Supports:

    • API Tokens
    • Username / Password
    • Ticket Authentication

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from api.client import ApiClient


class AuthenticationMethod(Enum):
    """
    Supported authentication methods.
    """

    NONE = "None"
    PASSWORD = "Password"
    API_TOKEN = "API Token"


@dataclass(slots=True)
class AuthenticationCredentials:
    """
    Credentials used to authenticate
    against a remote API.
    """

    username: str | None = None
    password: str | None = None

    token_id: str | None = None
    token_secret: str | None = None


class AuthenticationManager:
    """
    Handles authentication for an ApiClient.
    """

    def __init__(
        self,
        client: ApiClient,
    ) -> None:

        self._client = client

        self._authenticated = False
        self._method = AuthenticationMethod.NONE

    # ---------------------------------------------------------
    # Properties
    # ---------------------------------------------------------

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    @property
    def method(self) -> AuthenticationMethod:
        return self._method

    # ---------------------------------------------------------
    # Password Authentication
    # ---------------------------------------------------------

    def authenticate_password(
        self,
        username: str,
        password: str,
    ) -> bool:
        """
        Configure username/password authentication.
        """

        session = self._client.session

        session.auth = (username, password)

        self._authenticated = True
        self._method = AuthenticationMethod.PASSWORD

        return True

    # ---------------------------------------------------------
    # API Token Authentication
    # ---------------------------------------------------------

    def authenticate_token(
        self,
        token_id: str,
        token_secret: str,
    ) -> bool:
        """
        Configure API token authentication.
        """

        authorization = (
            f"PVEAPIToken={token_id}={token_secret}"
        )

        self._client.session.headers[
            "Authorization"
        ] = authorization

        self._authenticated = True
        self._method = AuthenticationMethod.API_TOKEN

        return True

    # ---------------------------------------------------------
    # Logout
    # ---------------------------------------------------------

    def logout(self) -> None:
        """
        Remove authentication information.
        """

        session = self._client.session

        session.auth = None

        session.headers.pop(
            "Authorization",
            None,
        )

        self._authenticated = False
        self._method = AuthenticationMethod.NONE

    # ---------------------------------------------------------
    # Status
    # ---------------------------------------------------------

    def is_authenticated(self) -> bool:
        """
        Returns the current authentication state.
        """

        return self._authenticated