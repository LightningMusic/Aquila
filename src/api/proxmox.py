"""
Project Orion
=============

Proxmox API

High-level interface for interacting with the
Proxmox VE REST API.

This module wraps the generic ApiClient and exposes
operations meaningful to Project Orion.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from typing import Any

from api.client import ApiClient
from api.endpoints import (
    CLUSTER_RESOURCES,
    CLUSTER_STATUS,
    NODES,
    VERSION,
    node,
    node_disks,
    node_network,
    node_status_current,
    node_storage,
)
from api.exceptions import (
    ApiConnectionError,
    ApiRequestError,
)


class ProxmoxApi:
    """
    High-level wrapper around the Proxmox VE API.
    """

    def __init__(
        self,
        client: ApiClient,
    ) -> None:

        self._client = client

    # ---------------------------------------------------------
    # General
    # ---------------------------------------------------------

    def get_version(self) -> dict[str, Any]:
        """
        Returns version information.
        """

        return self._client.get_json(VERSION)

    def ping(self) -> bool:
        """
        Verify the API is reachable.
        """

        try:

            self.get_version()

            return True

        except Exception:

            return False

    # ---------------------------------------------------------
    # Cluster
    # ---------------------------------------------------------

    def get_cluster_status(self) -> dict[str, Any]:
        """
        Retrieve cluster status.
        """

        return self._client.get_json(CLUSTER_STATUS)

    def get_cluster_resources(self) -> dict[str, Any]:
        """
        Retrieve cluster resources.
        """

        return self._client.get_json(CLUSTER_RESOURCES)

    # ---------------------------------------------------------
    # Nodes
    # ---------------------------------------------------------

    def get_nodes(self) -> dict[str, Any]:
        """
        Retrieve all cluster nodes.
        """

        return self._client.get_json(NODES)

    def get_node(
        self,
        node_name: str,
    ) -> dict[str, Any]:
        """
        Retrieve information for a node.
        """

        return self._client.get_json(
            node(node_name),
        )

    def get_node_status(
        self,
        node_name: str,
    ) -> dict[str, Any]:
        """
        Retrieve node status.
        """

        return self._client.get_json(
            node_status_current(node_name),
        )

    def get_node_storage(
        self,
        node_name: str,
    ) -> dict[str, Any]:
        """
        Retrieve storage devices.
        """

        return self._client.get_json(
            node_storage(node_name),
        )

    def get_node_network(
        self,
        node_name: str,
    ) -> dict[str, Any]:
        """
        Retrieve network configuration.
        """

        return self._client.get_json(
            node_network(node_name),
        )

    def get_node_disks(
        self,
        node_name: str,
    ) -> dict[str, Any]:
        """
        Retrieve disk information.
        """

        return self._client.get_json(
            node_disks(node_name),
        )

    # ---------------------------------------------------------
    # Utilities
    # ---------------------------------------------------------

    def request(
        self,
        endpoint: str,
    ) -> dict[str, Any]:
        """
        Execute a GET request against
        an arbitrary endpoint.
        """

        return self._client.get_json(endpoint)

    # ---------------------------------------------------------
    # Connection Validation
    # ---------------------------------------------------------

    def validate_connection(self) -> bool:
        """
        Ensure the API is reachable.
        """

        try:

            self.get_version()

            return True

        except Exception as exc:

            raise ApiConnectionError(
                "Unable to connect to the Proxmox API."
            ) from exc

    # ---------------------------------------------------------
    # Health Check
    # ---------------------------------------------------------

    def health_check(self) -> bool:
        """
        Perform a basic health check.
        """

        try:

            version = self.get_version()

            return "data" in version

        except Exception:

            return False

    # ---------------------------------------------------------
    # Generic Operations
    # ---------------------------------------------------------

    def get(
        self,
        endpoint: str,
    ) -> dict[str, Any]:
        """
        Execute a GET request.
        """

        try:

            return self._client.get_json(endpoint)

        except Exception as exc:

            raise ApiRequestError(
                f"GET request failed: {endpoint}"
            ) from exc

    def post(
        self,
        endpoint: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute a POST request.
        """

        try:

            return self._client.post_json(
                endpoint,
                json=payload,
            )

        except Exception as exc:

            raise ApiRequestError(
                f"POST request failed: {endpoint}"
            ) from exc