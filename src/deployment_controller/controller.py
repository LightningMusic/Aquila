"""
Project Aquila
=============

Deployment Controller

The composition root for the Deployment Controller service (SRS
Section 9.7/10.8, REQ-CTRL-001 through REQ-CTRL-021). Wires together
authentication (REQ-CTRL-001/002), authorization (REQ-CTRL-016),
configuration distribution (REQ-CTRL-006/007), and the Inventory
System (REQ-INV-*), exposing one handler method per endpoint in
``bootstrap.controller_client.DeploymentControllerClient``'s API
contract for ``deployment_controller.api.ControllerAPIServer`` to
route HTTP requests to.

Every protected handler authenticates the request first
(REQ-CTRL-001/REQ-SEC-002: "authenticate all/every deployment
requests" -- not just the initial handshake), matching this
subsystem's authentication design (see ``authentication.py``'s module
docstring): the bootstrap client sends the same bearer credential on
every call, so every call is checked the same way.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

from common.constants.logging import INVENTORY_LOGGER
from common.events.types.controller import NodeConfigurationIssuedEvent
from common.exceptions.inventory import InventoryRecordNotFoundError
from config.schemas.cluster_schema import ClusterConfig
from config.schemas.controller_server_schema import ControllerServerConfig
from deployment_controller.authentication import (
    NodeAuthenticator,
    TokenValidator,
)
from deployment_controller.authorization import (
    ApprovalStore,
    DeploymentAuthorizer,
)
from deployment_controller.configuration import ConfigurationDistributor
from deployment_controller.inventory import InventoryIntake
from deployment_controller.reports import DeploymentReportIntake
from inventory.database import InventoryDatabase
from inventory.inventory_manager import InventoryManager
from models.inventory.registry import InventorySearchCriteria

logger = logging.getLogger(INVENTORY_LOGGER)

#: A handler's response: (HTTP status code, JSON-serializable body).
HandlerResponse = Tuple[int, dict[str, Any]]


@dataclass(slots=True, frozen=True)
class ControllerDependencies:
    """Fully-constructed dependency set, for tests to override piecemeal."""

    database: InventoryDatabase
    inventory_manager: InventoryManager
    authenticator: NodeAuthenticator
    authorizer: DeploymentAuthorizer
    configuration_distributor: ConfigurationDistributor
    inventory_intake: InventoryIntake
    report_intake: DeploymentReportIntake


def _resolve_enrollment_tokens(env_var_name: str) -> tuple[str, ...]:
    raw = os.environ.get(env_var_name, "") if env_var_name else ""
    return tuple(token.strip() for token in raw.split(",") if token.strip())


def _parse_int(value: Optional[str], *, default: int) -> int:
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def build_dependencies(
    *,
    controller_server_config: ControllerServerConfig,
    cluster_config: ClusterConfig,
    event_bus: Optional[Any] = None,
) -> ControllerDependencies:
    """Construct the default, real dependency graph."""

    database = InventoryDatabase(controller_server_config.database_path)
    inventory_manager = InventoryManager(database=database, event_bus=event_bus)

    tokens = _resolve_enrollment_tokens(
        controller_server_config.enrollment_token_env_var
    )
    if not tokens:
        logger.warning(
            "No Deployment Controller enrollment token(s) resolved from "
            "environment variable '%s'; every authentication request "
            "will be rejected until this is configured (REQ-SEC-008/009).",
            controller_server_config.enrollment_token_env_var,
        )

    approval_store = ApprovalStore(database)
    authorizer = DeploymentAuthorizer(
        store=approval_store,
        auto_approve=controller_server_config.auto_approve_nodes,
        event_bus=event_bus,
    )

    authenticator = NodeAuthenticator(
        token_validator=TokenValidator(tokens),
        is_revoked=authorizer.is_denied,
        event_bus=event_bus,
    )

    configuration_distributor = ConfigurationDistributor(
        controller_server_config=controller_server_config,
        cluster_config=cluster_config,
    )

    return ControllerDependencies(
        database=database,
        inventory_manager=inventory_manager,
        authenticator=authenticator,
        authorizer=authorizer,
        configuration_distributor=configuration_distributor,
        inventory_intake=InventoryIntake(inventory_manager=inventory_manager),
        report_intake=DeploymentReportIntake(inventory_manager=inventory_manager),
    )


class DeploymentController:
    """
    The Deployment Controller's request-handling core. Satisfies
    ``interfaces.service.Service``.
    """

    def __init__(
        self,
        *,
        controller_server_config: ControllerServerConfig,
        cluster_config: ClusterConfig,
        event_bus: Optional[Any] = None,
        dependencies: Optional[ControllerDependencies] = None,
    ) -> None:
        self._server_config = controller_server_config
        self._event_bus = event_bus
        self._deps = dependencies or build_dependencies(
            controller_server_config=controller_server_config,
            cluster_config=cluster_config,
            event_bus=event_bus,
        )
        self._initialized = False

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        self._deps.inventory_manager.initialize()
        self._initialized = True

    def shutdown(self) -> None:
        self._deps.inventory_manager.shutdown()
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def dependencies(self) -> ControllerDependencies:
        return self._deps

    # ------------------------------------------------------------------
    # REQ-CTRL-021: request handlers
    # ------------------------------------------------------------------

    def handle_health(self) -> HandlerResponse:
        return 200, {"status": "ok", "initialized": self._initialized}

    def handle_authenticate(
        self, payload: dict[str, Any], authorization_header: Optional[str]
    ) -> HandlerResponse:
        node_identifier = str(payload.get("node_identifier") or "")

        result = self._deps.authenticator.authenticate(
            node_identifier, authorization_header
        )
        if not result.authenticated:
            return 401, {"error": result.detail}

        authorization = self._deps.authorizer.authorize(result.node_identifier)

        self._deps.inventory_manager.open_session(result.node_identifier)

        return 200, {
            "node_identifier": result.node_identifier,
            "approval_status": authorization.status.name,
            "detail": (
                "Authenticated and approved."
                if authorization.approved
                else authorization.detail
            ),
        }

    def handle_get_configuration(
        self, node_identifier: str, authorization_header: Optional[str]
    ) -> HandlerResponse:
        auth_result = self._require_authentication(
            node_identifier, authorization_header
        )
        if auth_result is not None:
            return auth_result

        authorization = self._deps.authorizer.authorize(node_identifier)
        if not authorization.approved:
            # REQ-SEC-004: unauthorized nodes shall not receive
            # deployment configuration.
            return 403, {"error": authorization.detail}

        existing_hostname = ""
        try:
            existing_hostname = self._deps.inventory_manager.get(
                node_identifier
            ).hostname
        except InventoryRecordNotFoundError:
            pass

        configuration = self._deps.configuration_distributor.build_configuration(
            node_identifier, hostname=existing_hostname
        )

        if existing_hostname != configuration.hostname:
            try:
                self._deps.inventory_manager.update_hostname(
                    node_identifier, configuration.hostname
                )
            except InventoryRecordNotFoundError:
                # The node has not registered inventory yet
                # (REQ-CTRL-004 assigns a hostname during Provisioning,
                # before REQ-BOOT-014 inventory registration runs
                # during Bootstrap) -- the hostname is still handed
                # back to the caller; it will be recorded once
                # inventory registration occurs.
                pass

        self._publish(
            lambda: NodeConfigurationIssuedEvent(
                node_identifier, configuration.hostname
            )
        )

        return 200, configuration.to_dict()

    def handle_completion(
        self, payload: dict[str, Any], authorization_header: Optional[str]
    ) -> HandlerResponse:
        node_identifier = str(payload.get("node_identifier") or "")

        auth_result = self._require_authentication(
            node_identifier, authorization_header
        )
        if auth_result is not None:
            return auth_result

        result = self._deps.report_intake.record_completion(node_identifier, payload)
        if not result.accepted:
            return 400, {"error": result.detail}

        return 200, {"detail": result.detail}

    def handle_register_inventory(
        self, payload: dict[str, Any], authorization_header: Optional[str]
    ) -> HandlerResponse:
        node_identifier = str(payload.get("node_identifier") or "")

        auth_result = self._require_authentication(
            node_identifier, authorization_header
        )
        if auth_result is not None:
            return auth_result

        result = self._deps.inventory_intake.register(node_identifier, payload)
        if not result.accepted:
            return 400, {"error": result.detail}

        return 200, {"detail": result.detail}

    def handle_submit_benchmark(
        self, payload: dict[str, Any], authorization_header: Optional[str]
    ) -> HandlerResponse:
        node_identifier = str(payload.get("node_identifier") or "")

        auth_result = self._require_authentication(
            node_identifier, authorization_header
        )
        if auth_result is not None:
            return auth_result

        result = self._deps.inventory_intake.submit_benchmark(
            node_identifier, payload
        )
        if not result.accepted:
            return 400, {"error": result.detail}

        return 200, {"detail": result.detail}

    # ------------------------------------------------------------------
    # REQ-INV-010 / REQ-BENCH-010: operator-facing read endpoints
    #
    # Not part of ``bootstrap.controller_client``'s node-facing
    # contract -- these back ``services.inventory_service``/
    # ``services.benchmark_service`` for the Technician Console
    # (REQ-INV-010: "The Inventory System shall permit searching";
    # REQ-BENCH-010: "Benchmark history shall remain associated with
    # the node inventory record", which requires *some* consumer able
    # to read it back). Gated by ``authenticate_operator`` rather than
    # ``_require_authentication`` -- a search is not made on behalf of
    # any single node, so there is no ``node_identifier`` to validate
    # the request against.
    # ------------------------------------------------------------------

    def handle_search_inventory(
        self,
        query_params: dict[str, str],
        authorization_header: Optional[str],
    ) -> HandlerResponse:
        if not self._deps.authenticator.authenticate_operator(
            authorization_header
        ):
            return 401, {"error": "A valid Authorization bearer token is required."}

        criteria = InventorySearchCriteria(
            node_identifier=query_params.get("node_identifier") or None,
            hostname=query_params.get("hostname") or None,
            manufacturer=query_params.get("manufacturer") or None,
            model=query_params.get("model") or None,
            serial_number=query_params.get("serial_number") or None,
            status=query_params.get("status") or None,
            limit=_parse_int(query_params.get("limit"), default=100),
            offset=_parse_int(query_params.get("offset"), default=0),
        )

        result = self._deps.inventory_manager.search(criteria)

        return 200, result.to_dict()

    def handle_get_node_benchmarks(
        self,
        node_identifier: str,
        authorization_header: Optional[str],
    ) -> HandlerResponse:
        if not self._deps.authenticator.authenticate_operator(
            authorization_header
        ):
            return 401, {"error": "A valid Authorization bearer token is required."}

        if not node_identifier:
            return 400, {"error": "A node_identifier is required."}

        benchmarks = self._deps.inventory_manager.get_benchmarks(node_identifier)

        return 200, {
            "node_identifier": node_identifier,
            "benchmarks": [record.to_dict() for record in benchmarks],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_authentication(
        self, node_identifier: str, authorization_header: Optional[str]
    ) -> Optional[HandlerResponse]:
        """
        Returns an error ``HandlerResponse`` if authentication fails,
        or ``None`` when the request may proceed.
        """

        if not node_identifier:
            return 400, {"error": "A node_identifier is required."}

        result = self._deps.authenticator.authenticate(
            node_identifier, authorization_header
        )
        if not result.authenticated:
            return 401, {"error": result.detail}

        return None

    def _publish(self, build_event: Callable[[], Any]) -> None:
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish(build_event())
        except Exception:  # pragma: no cover - event delivery is best-effort
            logger.debug("Failed to publish controller event.", exc_info=True)


__all__ = [
    "ControllerDependencies",
    "DeploymentController",
    "HandlerResponse",
    "build_dependencies",
]
