"""
Project Orion
=============

HTTP API Client

Provides a reusable HTTP client used throughout
Project Orion.

This module centralizes:

    • Session management
    • Authentication
    • Timeouts
    • SSL verification
    • JSON handling
    • Error handling

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from typing import Any

import requests
from requests import Response
from requests import Session
from requests.auth import HTTPBasicAuth
from requests.exceptions import RequestException


DEFAULT_TIMEOUT = 30


class ApiClient:
    """
    Generic HTTP API client.
    """

    def __init__(
        self,
        base_url: str,
        *,
        username: str | None = None,
        password: str | None = None,
        verify_ssl: bool = True,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:

        self._base_url = base_url.rstrip("/")
        self._verify_ssl = verify_ssl
        self._timeout = timeout

        self._session: Session = requests.Session()

        self._session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Project-Orion",
            }
        )

        if username and password:
            self._session.auth = HTTPBasicAuth(
                username,
                password,
            )

    # ---------------------------------------------------------
    # Properties
    # ---------------------------------------------------------

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def session(self) -> Session:
        return self._session

    # ---------------------------------------------------------
    # Utilities
    # ---------------------------------------------------------

    def _url(
        self,
        endpoint: str,
    ) -> str:
        endpoint = endpoint.lstrip("/")
        return f"{self._base_url}/{endpoint}"

    def close(self) -> None:
        """
        Close the HTTP session.
        """

        self._session.close()

    # ---------------------------------------------------------
    # HTTP Methods
    # ---------------------------------------------------------

    def get(
        self,
        endpoint: str,
        **kwargs: Any,
    ) -> Response:

        return self._request(
            "GET",
            endpoint,
            **kwargs,
        )

    def post(
        self,
        endpoint: str,
        **kwargs: Any,
    ) -> Response:

        return self._request(
            "POST",
            endpoint,
            **kwargs,
        )

    def put(
        self,
        endpoint: str,
        **kwargs: Any,
    ) -> Response:

        return self._request(
            "PUT",
            endpoint,
            **kwargs,
        )

    def delete(
        self,
        endpoint: str,
        **kwargs: Any,
    ) -> Response:

        return self._request(
            "DELETE",
            endpoint,
            **kwargs,
        )

    # ---------------------------------------------------------
    # JSON Helpers
    # ---------------------------------------------------------

    def get_json(
        self,
        endpoint: str,
        **kwargs: Any,
    ) -> Any:

        response = self.get(
            endpoint,
            **kwargs,
        )

        return response.json()

    def post_json(
        self,
        endpoint: str,
        **kwargs: Any,
    ) -> Any:

        response = self.post(
            endpoint,
            **kwargs,
        )

        return response.json()

    # ---------------------------------------------------------
    # Internal Request Handler
    # ---------------------------------------------------------

    def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> Response:

        timeout = kwargs.pop(
            "timeout",
            self._timeout,
        )

        try:

            response = self._session.request(
                method=method,
                url=self._url(endpoint),
                timeout=timeout,
                verify=self._verify_ssl,
                **kwargs,
            )

            response.raise_for_status()

            return response

        except RequestException:
            raise

    # ---------------------------------------------------------
    # Context Manager
    # ---------------------------------------------------------

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> None:
        self.close()