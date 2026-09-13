"""
Project Aquila
=============

Benchmark Service

The Technician Console/CLI-facing facade over REQ-BENCH-010 ("Benchmark
history shall remain associated with the node inventory record"):
reads a previously-deployed node's recorded benchmark results back
from the Deployment Controller, via the same read endpoint
``services.inventory_service`` uses for search
(``DeploymentControllerClient.get_node_benchmarks``).

Distinct from ``benchmark/`` (which *runs* benchmarks, on a deployed
node, during Bootstrap -- REQ-BENCH-001 through -006) and from
``bootstrap.benchmark.BenchmarkInitiator`` (which *submits* a result --
REQ-BENCH-007): this module only reads results back, for the
Technician Console to display (for example, "this node's last
benchmark score") -- it never runs or submits one itself.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from bootstrap.controller_client import DeploymentControllerClient
from common.constants.logging import DEPLOYMENT_LOGGER
from common.exceptions.deployment import DeploymentNetworkError
from config.schemas.controller_schema import ControllerConfig

logger = logging.getLogger(DEPLOYMENT_LOGGER)

ClientFactory = Callable[[ControllerConfig], DeploymentControllerClient]


@dataclass(slots=True, frozen=True)
class BenchmarkHistory:
    """One node's recorded benchmark history, as returned to the caller."""

    node_identifier: str
    records: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    succeeded: bool = True
    detail: str = ""

    @property
    def latest(self) -> Optional[dict[str, Any]]:
        """
        The most recently reported benchmark, if any -- records are
        returned newest-first by
        ``inventory.inventory_manager.InventoryManager.get_benchmarks``.
        """

        return self.records[0] if self.records else None


class BenchmarkService:
    """
    Read-only facade over a node's recorded benchmark history.
    Satisfies ``interfaces.service.Service``.
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
        self._authorization_token = token

    # ------------------------------------------------------------------
    # REQ-BENCH-010
    # ------------------------------------------------------------------

    def get_history(self, node_identifier: str) -> BenchmarkHistory:
        """
        Retrieve ``node_identifier``'s recorded benchmark history.

        Never raises: a request failure is reported through
        ``BenchmarkHistory.succeeded``/``.detail``, matching every
        other Console-facing facade's convention.
        """

        client = self._require_client()
        if self._authorization_token:
            client.set_bearer_token(self._authorization_token)

        try:
            records = client.get_node_benchmarks(node_identifier)
        except DeploymentNetworkError as exc:
            logger.warning(
                "Could not retrieve benchmark history for node '%s': %s",
                node_identifier,
                exc,
            )
            return BenchmarkHistory(
                node_identifier=node_identifier,
                succeeded=False,
                detail=str(exc),
            )

        return BenchmarkHistory(
            node_identifier=node_identifier,
            records=tuple(records),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_client(self) -> DeploymentControllerClient:
        if self._client is None:
            self.initialize()
        assert self._client is not None
        return self._client


__all__ = ["BenchmarkHistory", "BenchmarkService", "ClientFactory"]
