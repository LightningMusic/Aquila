"""
Project Aquila
=============

Inventory Service

The Technician Console/CLI-facing facade over REQ-INV-010's inventory
search, reusing the same ``bootstrap.controller_client.
DeploymentControllerClient`` (and its ``search_inventory`` method,
added alongside ``deployment_controller.controller.DeploymentController
.handle_search_inventory`` for exactly this consumer) that
``services.deployment_service`` uses for the Phase One handshake.

Distinct from ``deployment_controller.inventory.InventoryIntake``,
which is server-side (registration -- this module never writes) and
from ``inventory.inventory_manager.InventoryManager``, which is the
Controller process's own in-process persistence layer -- this module
is a Phase-One-side *read-only HTTP client* over that same data.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, cast

from bootstrap.controller_client import DeploymentControllerClient
from common.constants.logging import DEPLOYMENT_LOGGER
from common.exceptions.deployment import DeploymentNetworkError
from config.schemas.controller_schema import ControllerConfig

logger = logging.getLogger(DEPLOYMENT_LOGGER)

ClientFactory = Callable[[ControllerConfig], DeploymentControllerClient]


@dataclass(slots=True, frozen=True)
class InventorySearchQuery:
    """REQ-INV-010's search criteria, as the Technician Console collects them."""

    node_identifier: str = ""
    hostname: str = ""
    manufacturer: str = ""
    model: str = ""
    serial_number: str = ""
    status: str = ""
    limit: int = 100
    offset: int = 0

    def to_params(self) -> dict[str, str]:
        params: dict[str, str] = {}
        for key, value in (
            ("node_identifier", self.node_identifier),
            ("hostname", self.hostname),
            ("manufacturer", self.manufacturer),
            ("model", self.model),
            ("serial_number", self.serial_number),
            ("status", self.status),
        ):
            if value:
                params[key] = value

        params["limit"] = str(self.limit)
        params["offset"] = str(self.offset)
        return params


@dataclass(slots=True, frozen=True)
class InventorySearchResults:
    """A REQ-INV-010 search result, as returned to the caller."""

    records: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    total_matches: int = 0
    succeeded: bool = True
    detail: str = ""


class InventoryService:
    """
    Read-only facade over the Deployment Controller's inventory search
    endpoint. Satisfies ``interfaces.service.Service``.
    """

    def __init__(
        self,
        controller_config: ControllerConfig,
        *,
        authorization_token: str = "",
        client_factory: Optional[ClientFactory] = None,
    ) -> None:
        self._controller_config = controller_config
        self._authorization_token = authorization_token
        self._client_factory: ClientFactory = (
            client_factory or DeploymentControllerClient
        )
        self._client: Optional[DeploymentControllerClient] = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        if self._client is None:
            self._client = self._client_factory(self._controller_config)
        self._initialized = True

    def shutdown(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def set_authorization_token(self, token: str) -> None:
        """
        Set the bearer token used for every subsequent search
        (``deployment_controller.authentication.NodeAuthenticator
        .authenticate_operator`` accepts the same shared enrollment
        secret the Console used during ``DeploymentService.handshake``
        -- see that module's docstring).
        """

        self._authorization_token = token

    # ------------------------------------------------------------------
    # REQ-INV-010
    # ------------------------------------------------------------------

    def search(self, query: InventorySearchQuery) -> InventorySearchResults:
        """
        Search previously-deployed inventory records.

        Never raises: a request failure (unreachable Controller,
        missing/invalid authorization) is reported through
        ``InventorySearchResults.succeeded``/``.detail`` rather than
        propagated, matching REQ-TC-010/011's "warnings/errors are
        displayed, not crashes" convention every other Console-facing
        facade in this package follows.
        """

        client = self._require_client()
        self._apply_authorization(client)

        try:
            response = client.search_inventory(query.to_params())
        except DeploymentNetworkError as exc:
            logger.warning("Inventory search failed: %s", exc)
            return InventorySearchResults(succeeded=False, detail=str(exc))

        raw_records: Any = response.get("records") or []
        records: tuple[dict[str, Any], ...] = tuple(
            cast("dict[str, Any]", item)
            for item in cast("list[Any]", raw_records)
            if isinstance(item, dict)
        )
        total = response.get("total_matches", len(records))

        return InventorySearchResults(
            records=records,
            total_matches=int(total) if isinstance(total, (int, float)) else len(records),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_client(self) -> DeploymentControllerClient:
        if self._client is None:
            self.initialize()
        assert self._client is not None
        return self._client

    def _apply_authorization(self, client: DeploymentControllerClient) -> None:
        if self._authorization_token:
            client.set_bearer_token(self._authorization_token)


__all__ = [
    "ClientFactory",
    "InventoryService",
    "InventorySearchQuery",
    "InventorySearchResults",
]
