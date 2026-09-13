"""
Project Aquila
=============

Deployment Service

The Technician Console/CLI-facing facade over the Deployment
Controller API during **Phase One** (SRS Section 10.2's Technician
Console; the same environment ``provisioning/`` runs in). Closes the
architectural gap flagged when ``bootstrap/controller_client.py`` was
built and resolved (on the Controller's side) in
``deployment_controller/authentication.py``: this is the missing
Phase-One counterpart that actually obtains, before Phase Two's first
boot, everything ``bootstrap.bootstrap_manager.BootstrapManager.run()``
requires as caller-supplied parameters (``node_identifier``,
``authentication_token``, ``join_secret``) but that nothing in
``provisioning/`` previously established.

Where the node identifier is generated
------------------------------------------
Neither ``bootstrap/`` nor ``deployment_controller/`` originates the
node identifier -- ``BootstrapManager.run()`` requires one as a
parameter, and the Controller's REQ-CTRL-003 "assignment" is
acceptance of a caller-proposed value (see
``deployment_controller.authentication``'s module docstring), not
generation of one. This module is where a real generation point
becomes concrete: :func:`generate_node_identifier` produces a UUID4
during Phase One's Provisioning workflow stage, *before* the first
Controller call -- the identifier is then used for both this
handshake and, unchanged, for Bootstrap's later calls once Phase Two
boots. Persisting it across the Phase One/Phase Two boundary (a small
node-identity file alongside the rendered answer file, read back by
whatever invokes ``BootstrapManager.run()`` during first boot) is
workflow-level orchestration, wired up in ``workflows.provisioning_
manager`` -- this module only produces the value and performs the
handshake with it.

Deliberately reuses ``bootstrap.controller_client.
DeploymentControllerClient`` rather than building a second Controller
HTTP client -- nothing about that class is actually Phase-Two-specific
(it is a thin wrapper over the generic ``api.client.ApiClient``), so
Phase One's Console/CLI code gets exactly the same, already end-to-end
-tested request/response handling for free.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Optional

from bootstrap.controller_client import (
    DeploymentControllerClient,
    NodeConfiguration,
)
from common.constants.logging import DEPLOYMENT_LOGGER
from common.exceptions.deployment import (
    DeploymentAuthenticationError,
    DeploymentConfigurationError,
)
from config.schemas.controller_schema import ControllerConfig

logger = logging.getLogger(DEPLOYMENT_LOGGER)

#: Constructs a ``DeploymentControllerClient`` (or a test double with
#: the same public surface) from a ``ControllerConfig``. Injected so
#: tests never open a real socket.
ClientFactory = Callable[[ControllerConfig], DeploymentControllerClient]


def generate_node_identifier() -> str:
    """
    Generate a new node identifier (a UUID4, matching
    ``deployment_controller.authentication.is_valid_node_identifier``'s
    accepted shape) for a node about to be provisioned.
    """

    return str(uuid.uuid4())


@dataclass(slots=True, frozen=True)
class NodeHandshakeResult:
    """
    The outcome of establishing this node's identity with the
    Deployment Controller before Phase Two's first boot.

    ``approved`` distinguishes "the Controller has authorized this
    deployment and returned configuration" from "authenticated, but
    still pending manual approval (REQ-CTRL-016)" -- the latter is not
    an error, it is REQ-TC-012's confirmation gate surfacing through
    to the technician: the workflow should halt and let the operator
    know approval is pending, not treat it as a failure.
    """

    node_identifier: str
    authentication_token: str
    reachable: bool
    authenticated: bool
    approved: bool
    hostname: str = ""
    ssh_authorized_keys: tuple[str, ...] = ()
    cluster_join_token: str = ""
    detail: str = ""


class DeploymentService:
    """
    Technician Console/CLI-facing facade over the Deployment
    Controller API. Satisfies ``interfaces.service.Service``.
    """

    def __init__(
        self,
        controller_config: ControllerConfig,
        *,
        client_factory: Optional[ClientFactory] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._controller_config = controller_config
        self._client_factory: ClientFactory = (
            client_factory or DeploymentControllerClient
        )
        self._event_bus = event_bus
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

    # ------------------------------------------------------------------
    # REQ-NET-009 / REQ-PROV-004: reachability
    # ------------------------------------------------------------------

    def check_reachable(self) -> bool:
        """Confirm the Deployment Controller is reachable."""

        return self._require_client().verify_communication()

    # ------------------------------------------------------------------
    # REQ-BOOT-002/003/004 support, performed early (Phase One)
    # ------------------------------------------------------------------

    def handshake(
        self,
        node_identifier: str,
        *,
        enrollment_token: str,
    ) -> NodeHandshakeResult:
        """
        Establish this node's identity with the Deployment Controller
        ahead of Phase Two's first boot: confirm reachability,
        authenticate using a shared enrollment secret (see
        ``deployment_controller.authentication``'s module docstring
        for why one shared secret, not a per-node credential, is what
        this authenticates with), and -- if the Controller has
        already approved this deployment (REQ-CTRL-016) -- retrieve
        the assigned hostname, SSH keys, and cluster join token.

        Never raises for an ordinary "not reachable yet" / "pending
        approval" outcome -- those are reported through the returned
        ``NodeHandshakeResult`` for the calling workflow stage to
        act on (REQ-TC-010/011: warnings are displayed, not crashes).
        A malformed ``node_identifier``/``enrollment_token`` still
        surfaces as ``authenticated=False`` the same way.
        """

        client = self._require_client()

        reachable = client.verify_communication()
        if not reachable:
            return NodeHandshakeResult(
                node_identifier=node_identifier,
                authentication_token=enrollment_token,
                reachable=False,
                authenticated=False,
                approved=False,
                detail="Deployment Controller is not reachable.",
            )

        try:
            client.authenticate(node_identifier, enrollment_token)
        except DeploymentAuthenticationError as exc:
            logger.warning(
                "Deployment Controller handshake failed for node '%s': %s",
                node_identifier,
                exc,
            )
            return NodeHandshakeResult(
                node_identifier=node_identifier,
                authentication_token=enrollment_token,
                reachable=True,
                authenticated=False,
                approved=False,
                detail=str(exc),
            )

        try:
            node_config: NodeConfiguration = client.retrieve_configuration(
                node_identifier
            )
        except DeploymentConfigurationError as exc:
            # REQ-SEC-004: the Controller refuses configuration to an
            # unapproved node (HTTP 403) -- surfaced here as "pending
            # approval", not a failure, so the caller can decide
            # whether to wait and retry.
            logger.info(
                "Node '%s' authenticated but is not yet approved: %s",
                node_identifier,
                exc,
            )
            return NodeHandshakeResult(
                node_identifier=node_identifier,
                authentication_token=enrollment_token,
                reachable=True,
                authenticated=True,
                approved=False,
                detail=str(exc),
            )

        logger.info(
            "Node '%s' handshake complete: hostname '%s' assigned.",
            node_identifier,
            node_config.hostname,
        )

        return NodeHandshakeResult(
            node_identifier=node_config.node_identifier,
            authentication_token=enrollment_token,
            reachable=True,
            authenticated=True,
            approved=True,
            hostname=node_config.hostname,
            ssh_authorized_keys=node_config.ssh_authorized_keys,
            cluster_join_token=node_config.cluster_join_token,
            detail="Approved; configuration retrieved.",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_client(self) -> DeploymentControllerClient:
        if self._client is None:
            self.initialize()
        assert self._client is not None  # narrows for the type checker
        return self._client


__all__ = [
    "ClientFactory",
    "DeploymentService",
    "NodeHandshakeResult",
    "generate_node_identifier",
]
