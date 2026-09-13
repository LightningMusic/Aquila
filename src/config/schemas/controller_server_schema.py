"""
Project Aquila
=============

Controller Server Configuration Schema

Defines the validated, typed structure of ``configs/controller_server.yaml``:
how the Deployment Controller *service itself* runs -- as opposed to
``config.schemas.controller_schema.ControllerConfig``, which is the
already-complete, client-facing "how does a node reach the
Controller" configuration shipped on deployment media.

Why a second schema rather than extending ``ControllerConfig``
---------------------------------------------------------------
``ControllerConfig`` is read by every deployed node (via
``bootstrap.controller_client.DeploymentControllerClient``) and by
Provisioning (``provisioning.connectivity.ConnectivityChecker``) --
its fields describe a *remote* Controller from the node's point of
view (host/port/timeout/retry). The Controller service itself needs a
disjoint set of settings that only make sense locally, on the machine
actually running ``deployment_controller.api.ControllerAPIServer``:
which local address to bind, where its TLS certificate/key and
persistent database live, and its enrollment/approval policy. Adding
these to ``ControllerConfig`` would mean every node's copy of
``controller.yaml`` carries server-only fields it can never use, and
would force every existing ``ControllerConfig`` caller
(``bootstrap.controller_client``, ``provisioning.connectivity``,
``networking.controller``) to tolerate fields irrelevant to them.
Two schemas, one per side of the connection -- the same reasoning
``config.schemas.controller_schema`` already documents for keeping
Deployment Controller settings out of ``ClusterConfig``.

Not registered with ``config.manager.ConfigurationManager`` --
that registry is for configuration every Aquila *node* (technician
console, bootstrap, provisioning) loads at deployment time. The
Controller service is a separate long-running process with its own
startup path (SRS Section 9.7: "shall operate independently of
deployment media and shall remain continuously available"), so it
loads this schema directly via :meth:`ControllerServerConfig.load`
rather than through the node-oriented manager.

See SRS Section 9.7, REQ-CTRL-001 through REQ-CTRL-021.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Mapping

from common.paths import CONTROLLER_SERVER_CONFIG, INVENTORY_DATABASE_FILE
from config.loaders.yaml_loader import YAMLConfigLoader
from config.validators.schema_validator import (
    coerce_bool,
    coerce_int,
    coerce_str,
    coerce_str_list,
    require_mapping,
    validate_range,
)

#: Default local bind port for the Controller's own HTTPS listener.
#: Matches ``ControllerConfig.DEFAULT_CONTROLLER_PORT`` -- a node's
#: default expectation of "port 443" should work out of the box
#: against a Controller running its own defaults.
DEFAULT_BIND_PORT: int = 443


@dataclass(slots=True)
class ControllerServerConfig:
    """
    The Deployment Controller service's own runtime configuration.
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    #: Local address to bind the HTTP(S) listener to. "0.0.0.0" (all
    #: interfaces) is deliberately not the default -- REQ-SEC-001
    #: ("encrypted channels") argues for an explicit, reviewed bind
    #: address rather than one that silently listens everywhere.
    bind_host: str = "127.0.0.1"
    bind_port: int = DEFAULT_BIND_PORT

    api_base_path: str = "/api/v1"

    #: REQ-SEC-001: all communication shall be encrypted. TLS is on by
    #: default; disabling it is only for local development/testing
    #: against ``bind_host="127.0.0.1"`` and is intentionally not the
    #: shipped default.
    use_tls: bool = True
    tls_certificate_path: str = ""
    tls_private_key_path: str = ""

    #: Where the Inventory System's persistent store lives (REQ-INV-*,
    #: REQ-CTRL-009/010/012). See ``inventory.database.InventoryDatabase``.
    database_path: str = str(INVENTORY_DATABASE_FILE)

    #: Name of the environment variable holding the shared enrollment
    #: secret nodes present when calling
    #: ``DeploymentControllerClient.authenticate()`` (REQ-CTRL-001/002,
    #: REQ-SEC-002). Never stored in this configuration file itself --
    #: the same env-var-indirection pattern
    #: ``ControllerConfig.authentication_token_env_var`` and
    #: ``ClusterConfig.join_token_env_var`` already establish. A
    #: comma-separated list of tokens may be present in that
    #: environment variable to support rotation (an old token keeps
    #: working until every deployment batch using it has finished).
    enrollment_token_env_var: str = "AQUILA_CONTROLLER_TOKEN"

    #: REQ-CTRL-016: whether a node that authenticates successfully is
    #: immediately Approved, or left Pending for manual approval (no
    #: operator-facing approval UI exists yet -- see
    #: ``claude/aquila-project-status.md`` -- so Pending nodes today
    #: only become Approved through a direct
    #: ``DeploymentAuthorizer.set_approval()`` call).
    auto_approve_nodes: bool = True

    #: REQ-CTRL-004: hostname prefix used when assigning a node's
    #: hostname during configuration retrieval.
    hostname_prefix: str = "aquila-node"

    #: SSH public keys installed by Bootstrap on every node
    #: (REQ-BOOT-006, part of REQ-CTRL-007's configuration payload).
    ssh_authorized_keys: list[str] = field(default_factory=lambda: [])

    #: HTTP server thread-pool sizing / socket timeout.
    max_worker_threads: int = 16
    request_timeout_seconds: int = 30

    extensions: dict[str, Any] = field(default_factory=lambda: {})

    def __post_init__(self) -> None:
        """Validate Deployment Controller server invariants."""

        validate_range(
            self.bind_port, field_name="bind_port", minimum=1, maximum=65535
        )

        validate_range(
            self.max_worker_threads,
            field_name="max_worker_threads",
            minimum=1,
        )

        validate_range(
            self.request_timeout_seconds,
            field_name="request_timeout_seconds",
            minimum=1,
        )

        if not self.api_base_path.startswith("/"):
            self.api_base_path = f"/{self.api_base_path}"

        self.ssh_authorized_keys = list(self.ssh_authorized_keys)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ControllerServerConfig:
        """Construct a validated ``ControllerServerConfig`` from a raw mapping."""

        mapping = require_mapping(data, section="controller_server")

        known_keys = {
            "schema_version",
            "bind_host",
            "bind_port",
            "api_base_path",
            "use_tls",
            "tls_certificate_path",
            "tls_private_key_path",
            "database_path",
            "enrollment_token_env_var",
            "auto_approve_nodes",
            "hostname_prefix",
            "ssh_authorized_keys",
            "max_worker_threads",
            "request_timeout_seconds",
        }

        extensions = {
            key: value for key, value in mapping.items() if key not in known_keys
        }

        return cls(
            bind_host=coerce_str(
                mapping.get("bind_host"),
                field_name="bind_host",
                default="127.0.0.1",
            ),
            bind_port=coerce_int(
                mapping.get("bind_port"),
                field_name="bind_port",
                default=DEFAULT_BIND_PORT,
            ),
            api_base_path=coerce_str(
                mapping.get("api_base_path"),
                field_name="api_base_path",
                default="/api/v1",
            ),
            use_tls=coerce_bool(
                mapping.get("use_tls"), field_name="use_tls", default=True
            ),
            tls_certificate_path=coerce_str(
                mapping.get("tls_certificate_path"),
                field_name="tls_certificate_path",
                default="",
            ),
            tls_private_key_path=coerce_str(
                mapping.get("tls_private_key_path"),
                field_name="tls_private_key_path",
                default="",
            ),
            database_path=coerce_str(
                mapping.get("database_path"),
                field_name="database_path",
                default=str(INVENTORY_DATABASE_FILE),
            ),
            enrollment_token_env_var=coerce_str(
                mapping.get("enrollment_token_env_var"),
                field_name="enrollment_token_env_var",
                default="AQUILA_CONTROLLER_TOKEN",
            ),
            auto_approve_nodes=coerce_bool(
                mapping.get("auto_approve_nodes"),
                field_name="auto_approve_nodes",
                default=True,
            ),
            hostname_prefix=coerce_str(
                mapping.get("hostname_prefix"),
                field_name="hostname_prefix",
                default="aquila-node",
            ),
            ssh_authorized_keys=coerce_str_list(
                mapping.get("ssh_authorized_keys"),
                field_name="ssh_authorized_keys",
            ),
            max_worker_threads=coerce_int(
                mapping.get("max_worker_threads"),
                field_name="max_worker_threads",
                default=16,
            ),
            request_timeout_seconds=coerce_int(
                mapping.get("request_timeout_seconds"),
                field_name="request_timeout_seconds",
                default=30,
            ),
            extensions=extensions,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a YAML/JSON-serializable dictionary representation."""

        return {
            "schema_version": self.SCHEMA_VERSION,
            "bind_host": self.bind_host,
            "bind_port": self.bind_port,
            "api_base_path": self.api_base_path,
            "use_tls": self.use_tls,
            "tls_certificate_path": self.tls_certificate_path,
            "tls_private_key_path": self.tls_private_key_path,
            "database_path": self.database_path,
            "enrollment_token_env_var": self.enrollment_token_env_var,
            "auto_approve_nodes": self.auto_approve_nodes,
            "hostname_prefix": self.hostname_prefix,
            "ssh_authorized_keys": list(self.ssh_authorized_keys),
            "max_worker_threads": self.max_worker_threads,
            "request_timeout_seconds": self.request_timeout_seconds,
            **self.extensions,
        }

    @classmethod
    def load(cls, path: Path | None = None) -> ControllerServerConfig:
        """
        Load and validate ``configs/controller_server.yaml`` (or
        ``path``) from disk. A missing file is not an error -- every
        field falls back to its documented default (GP-003), matching
        every other Aquila configuration file's own behavior.
        """

        target = path or CONTROLLER_SERVER_CONFIG
        loader = YAMLConfigLoader()

        if not target.exists():
            return cls()

        return cls.from_dict(loader.load(target))


__all__ = ["DEFAULT_BIND_PORT", "ControllerServerConfig"]
