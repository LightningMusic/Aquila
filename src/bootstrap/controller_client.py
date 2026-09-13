"""
Project Aquila
=============

Deployment Controller Client (Bootstrap side)

Implements REQ-BOOT-002 (verify communication with the Deployment
Controller), REQ-BOOT-003 (authenticate the node), REQ-BOOT-004
(retrieve deployment configuration), and REQ-BOOT-016 (report
deployment completion).

Not part of the original ``bootstrap/`` stub layout (``battery.py``,
``benchmark.py``, ``bootstrap_manager.py``, ``cleanup.py``,
``cluster.py``, ``hostname.py``, ``inventory.py``, ``power.py``,
``ssh.py``) -- that set had no file for Controller-communication
itself. Rather than cram session/auth/config-retrieval/completion-
reporting into ``bootstrap_manager.py`` (violating GP-004's one-
responsibility-per-module principle) or silently duplicate this
concern inside ``inventory.py``, this is a new, clearly-named file --
the same kind of documented deviation ``provisioning/`` already made
when its stub layout didn't match the subsystem's real shape.

Deliberately reuses ``api.client.ApiClient`` -- the already-complete,
generic HTTP client -- rather than building a second one. ``api/``'s
existing ``ApiServer``/``ProxmoxApi`` wrap *Proxmox's own* REST API
specifically (cluster/nodes/qemu/lxc endpoints); the Deployment
Controller is a different, Aquila-defined API (SRS Section 11.8, not
yet built as ``deployment_controller/``), so this module is a thin,
Controller-specific wrapper around the same generic ``ApiClient``,
exactly analogous to how ``api.proxmox.ProxmoxApi`` wraps it for
Proxmox.

REQ-SEC-014 ("Bootstrap shall verify the authenticity of Deployment
Controller responses") is satisfied at the transport layer:
``ApiClient(verify_ssl=controller_config.verify_tls_certificate)``
performs standard TLS certificate verification on every request, the
same mechanism REQ-SEC-001 ("encrypted channels") already relies on
elsewhere in this project -- no additional response-signing scheme is
invented here.

Since ``deployment_controller/`` itself is not yet built, the exact
JSON request/response shapes below are this client's own proposed
contract, not a confirmed server implementation -- flagged in
``claude/aquila-project-status.md`` for reconciliation once that
subsystem is built.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, cast

from api.client import ApiClient
from common.constants.controller_api import (
    AUTHENTICATE_ENDPOINT as _AUTHENTICATE_ENDPOINT,
)
from common.constants.controller_api import (
    BENCHMARK_ENDPOINT as _BENCHMARK_ENDPOINT,
)
from common.constants.controller_api import (
    COMPLETION_ENDPOINT as _COMPLETION_ENDPOINT,
)
from common.constants.controller_api import (
    CONFIGURATION_ENDPOINT as _CONFIGURATION_ENDPOINT,
)
from common.constants.controller_api import HEALTH_ENDPOINT as _HEALTH_ENDPOINT
from common.constants.controller_api import (
    INVENTORY_ENDPOINT as _INVENTORY_ENDPOINT,
)
from common.constants.logging import BOOTSTRAP_LOGGER
from common.exceptions.deployment import (
    DeploymentAuthenticationError,
    DeploymentConfigurationError,
    DeploymentNetworkError,
    DeploymentReportError,
)
from config.schemas.controller_schema import ControllerConfig

logger = logging.getLogger(BOOTSTRAP_LOGGER)

#: This client's proposed Deployment Controller API surface -- see
#: this module's docstring. Route paths themselves now come from
#: ``common.constants.controller_api``, the single source of truth
#: both this client and ``deployment_controller.api`` (the server)
#: import from, so the two sides of the contract cannot silently
#: drift apart (see that module's docstring for the fix rationale).
#: Aliased with a leading underscore on import above to keep every
#: call site below unchanged.


@dataclass(slots=True, frozen=True)
class NodeConfiguration:
    """
    The subset of REQ-CTRL-007's deployment configuration Bootstrap
    itself applies: hostname, SSH keys, and cluster join
    parameters. Everything else the Controller may return is kept,
    unparsed, in ``raw`` for forward compatibility.
    """

    hostname: str
    ssh_authorized_keys: tuple[str, ...]
    cluster_join_token: str
    node_identifier: str
    raw: dict[str, Any] = field(default_factory=lambda: {})


class DeploymentControllerClient:
    """
    Bootstrap's client for the Aquila Deployment Controller API.
    """

    def __init__(
        self,
        controller_config: ControllerConfig,
        *,
        api_client: ApiClient | None = None,
    ) -> None:
        self._config = controller_config
        self._client = api_client or ApiClient(
            base_url=(
                f"{'https' if controller_config.use_tls else 'http'}"
                f"://{controller_config.host}:{controller_config.port}"
                f"{controller_config.api_base_path}"
            ),
            verify_ssl=controller_config.verify_tls_certificate,
            timeout=controller_config.connection_timeout_seconds,
        )

    def close(self) -> None:
        """
        Close the underlying ``ApiClient`` session.

        REQ-SEC-013: the bearer token this client authenticates with
        (``authenticate()``/``set_bearer_token()``) is held only as an
        in-memory ``Authorization`` header on ``self._client.session``
        -- never written to disk -- so closing that session once a
        deployment completes is this client's whole part in "removing"
        the temporary credential: nothing outlives the process to
        clean up afterward.
        """

        self._client.close()

    # ------------------------------------------------------------------
    # REQ-BOOT-002
    # ------------------------------------------------------------------

    def verify_communication(self) -> bool:
        """Confirm the Deployment Controller is reachable."""

        try:
            self._client.get(_HEALTH_ENDPOINT)
            return True
        except Exception as exc:
            logger.error(
                "Deployment Controller unreachable at %s: %s",
                self._client.base_url,
                exc,
            )
            return False

    # ------------------------------------------------------------------
    # REQ-BOOT-003
    # ------------------------------------------------------------------

    def set_bearer_token(self, token: str) -> None:
        """
        Set the ``Authorization: Bearer`` header directly, without
        performing a node-scoped ``authenticate()`` call.

        Used by ``services.inventory_service``/``services.
        benchmark_service`` for the Technician Console's REQ-INV-010/
        REQ-BENCH-010 read requests, which are not made on behalf of
        any single node (see ``deployment_controller.authentication
        .NodeAuthenticator.authenticate_operator``'s docstring) and so
        have no ``node_identifier`` to pass through ``authenticate()``
        -- but still need the same shared enrollment secret attached.
        """

        self._client.session.headers["Authorization"] = f"Bearer {token}"

    def authenticate(
        self, node_identifier: str, authentication_token: str
    ) -> None:
        """
        Authenticate this node with the Deployment Controller.

        Raises:
            DeploymentAuthenticationError: If authentication is
                rejected or the request otherwise fails.
        """

        if not authentication_token:
            raise DeploymentAuthenticationError(
                "No Deployment Controller authentication token was "
                f"resolved from "
                f"'{self._config.authentication_token_env_var}'."
            )

        self._client.session.headers["Authorization"] = (
            f"Bearer {authentication_token}"
        )

        try:
            self._client.post_json(
                _AUTHENTICATE_ENDPOINT,
                json={"node_identifier": node_identifier},
            )
        except Exception as exc:
            raise DeploymentAuthenticationError(
                f"Deployment Controller authentication failed for "
                f"node '{node_identifier}': {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # REQ-BOOT-004
    # ------------------------------------------------------------------

    def retrieve_configuration(
        self, node_identifier: str
    ) -> NodeConfiguration:
        """
        Retrieve the deployment configuration assigned to this node.

        Raises:
            DeploymentConfigurationError: If the configuration cannot
                be retrieved or is missing required fields.
        """

        try:
            payload = self._client.get_json(
                _CONFIGURATION_ENDPOINT,
                params={"node_identifier": node_identifier},
            )
        except Exception as exc:
            raise DeploymentConfigurationError(
                "Could not retrieve deployment configuration for "
                f"node '{node_identifier}': {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise DeploymentConfigurationError(
                "Deployment Controller returned a non-object "
                "configuration response."
            )

        config: dict[str, Any] = cast("dict[str, Any]", payload)

        hostname = str(config.get("hostname") or "")
        if not hostname:
            raise DeploymentConfigurationError(
                "Deployment Controller did not assign a hostname "
                f"(REQ-CTRL-004) for node '{node_identifier}'."
            )

        raw_keys_value: Any = config.get("ssh_authorized_keys") or []
        ssh_keys = tuple(
            str(key) for key in raw_keys_value if isinstance(key, str)
        )

        return NodeConfiguration(
            hostname=hostname,
            ssh_authorized_keys=ssh_keys,
            cluster_join_token=str(
                config.get("cluster_join_token") or ""
            ),
            node_identifier=str(
                config.get("node_identifier") or node_identifier
            ),
            raw=config,
        )

    # ------------------------------------------------------------------
    # REQ-BOOT-016
    # ------------------------------------------------------------------

    def report_completion(
        self,
        node_identifier: str,
        *,
        status: str,
        detail: str,
    ) -> None:
        """
        Report deployment completion (or failure) to the Deployment
        Controller.

        Raises:
            DeploymentReportError: If the report could not be
                delivered.
        """

        try:
            self._client.post_json(
                _COMPLETION_ENDPOINT,
                json={
                    "node_identifier": node_identifier,
                    "status": status,
                    "detail": detail,
                },
            )
        except Exception as exc:
            raise DeploymentReportError(
                f"Could not report completion for node "
                f"'{node_identifier}' to the Deployment Controller: "
                f"{exc}"
            ) from exc

    # ------------------------------------------------------------------
    # REQ-BOOT-014 / REQ-BOOT-015 support
    # ------------------------------------------------------------------

    def register_inventory(self, payload: dict[str, Any]) -> None:
        """Submit an inventory registration payload (REQ-BOOT-014)."""

        try:
            self._client.post_json(_INVENTORY_ENDPOINT, json=payload)
        except Exception as exc:
            raise DeploymentNetworkError(
                f"Could not register inventory: {exc}"
            ) from exc

    def submit_benchmark(self, payload: dict[str, Any]) -> None:
        """Submit benchmark results (REQ-BOOT-015, REQ-BENCH-007)."""

        try:
            self._client.post_json(_BENCHMARK_ENDPOINT, json=payload)
        except Exception as exc:
            raise DeploymentNetworkError(
                f"Could not submit benchmark results: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # REQ-INV-010 / REQ-BENCH-010: operator-facing reads
    #
    # Not used by Bootstrap itself -- these back
    # ``services.inventory_service``/``services.benchmark_service``
    # for the Technician Console, which reuses this same client rather
    # than a second one (this class has no Phase-Two-specific state;
    # it is simply "the" client for the Deployment Controller API).
    # ------------------------------------------------------------------

    def search_inventory(self, criteria: dict[str, Any]) -> dict[str, Any]:
        """
        Search previously-registered inventory records (REQ-INV-010).

        ``criteria`` is sent as query parameters, matching
        ``deployment_controller.controller.DeploymentController
        .handle_search_inventory``'s accepted keys (``node_identifier``,
        ``hostname``, ``manufacturer``, ``model``, ``serial_number``,
        ``status``, ``limit``, ``offset``).

        Raises:
            DeploymentNetworkError: If the search request fails.
        """

        try:
            result: Any = self._client.get_json(
                _INVENTORY_ENDPOINT, params=criteria
            )
        except Exception as exc:
            raise DeploymentNetworkError(
                f"Could not search inventory: {exc}"
            ) from exc

        if not isinstance(result, dict):
            raise DeploymentNetworkError(
                "Deployment Controller returned a non-object inventory "
                "search response."
            )

        return cast("dict[str, Any]", result)

    def get_node_benchmarks(self, node_identifier: str) -> list[dict[str, Any]]:
        """
        Retrieve one node's recorded benchmark history (REQ-BENCH-010).

        Raises:
            DeploymentNetworkError: If the request fails.
        """

        try:
            result: Any = self._client.get_json(
                _BENCHMARK_ENDPOINT,
                params={"node_identifier": node_identifier},
            )
        except Exception as exc:
            raise DeploymentNetworkError(
                f"Could not retrieve benchmark history for node "
                f"'{node_identifier}': {exc}"
            ) from exc

        if not isinstance(result, dict):
            raise DeploymentNetworkError(
                "Deployment Controller returned a non-object benchmark "
                "response."
            )

        response_body = cast("dict[str, Any]", result)
        benchmarks_value: Any = response_body.get("benchmarks") or []
        if not isinstance(benchmarks_value, list):
            return []

        return [
            cast("dict[str, Any]", item)
            for item in cast("list[Any]", benchmarks_value)
            if isinstance(item, dict)
        ]

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "DeploymentControllerClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


__all__ = ["DeploymentControllerClient", "NodeConfiguration"]
