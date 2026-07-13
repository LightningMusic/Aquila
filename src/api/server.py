"""
Project Orion
=============

API Server

Represents a remote API server connection.

The ApiServer class manages:

    • Server connection information
    • Connection state
    • Health checks
    • Authentication status
    • Shared API client

This module does NOT implement an HTTP server.
Project Orion is an API client.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from api.client import ApiClient


class ServerState(Enum):
    """
    Current state of the remote API server.
    """

    DISCONNECTED = "Disconnected"
    CONNECTING = "Connecting"
    CONNECTED = "Connected"
    AUTHENTICATED = "Authenticated"
    UNAVAILABLE = "Unavailable"
    ERROR = "Error"


@dataclass(slots=True)
class ServerInformation:
    """
    Basic information describing a remote server.
    """

    hostname: str
    address: str
    port: int = 8006

    verify_ssl: bool = True

    username: str | None = None
    password: str | None = None


class ApiServer:
    """
    Represents a remote API server.
    """

    def __init__(
        self,
        information: ServerInformation,
    ) -> None:

        self._information = information

        self._state = ServerState.DISCONNECTED

        self._client = ApiClient(
            base_url=f"https://{information.address}:{information.port}",
            username=information.username,
            password=information.password,
            verify_ssl=information.verify_ssl,
        )

    # ---------------------------------------------------------
    # Properties
    # ---------------------------------------------------------

    @property
    def information(self) -> ServerInformation:
        return self._information

    @property
    def client(self) -> ApiClient:
        return self._client

    @property
    def state(self) -> ServerState:
        return self._state

    @property
    def connected(self) -> bool:
        return self._state in (
            ServerState.CONNECTED,
            ServerState.AUTHENTICATED,
        )

    # ---------------------------------------------------------
    # Connection Management
    # ---------------------------------------------------------

    def connect(self) -> bool:
        """
        Attempt to contact the remote server.
        """

        self._state = ServerState.CONNECTING

        try:

            self._client.get("/version")

            self._state = ServerState.CONNECTED

            return True

        except Exception:

            self._state = ServerState.UNAVAILABLE

            return False

    def disconnect(self) -> None:
        """
        Close the connection.
        """

        self._client.close()

        self._state = ServerState.DISCONNECTED

    def authenticate(self) -> bool:
        """
        Placeholder for future authentication.
        """

        if self._state != ServerState.CONNECTED:
            return False

        self._state = ServerState.AUTHENTICATED

        return True

    def ping(self) -> bool:
        """
        Check whether the server is reachable.
        """

        try:

            self._client.get("/version")

            return True

        except Exception:

            return False

    # ---------------------------------------------------------
    # Context Manager
    # ---------------------------------------------------------

    def __enter__(self) -> "ApiServer":

        self.connect()

        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> None:

        self.disconnect()