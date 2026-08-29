"""
Project Aquila
=============

Cluster Configuration Schema

Defines the validated, typed structure of ``configs/cluster.yaml``:
which Proxmox cluster a node joins during Bootstrap and how it
authenticates to it.

See SRS Section 9.7/9.13, REQ-BOOT-012, REQ-BOOT-013, and
REQ-NET-010.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping, Optional

from config.validators.schema_validator import (
    coerce_bool,
    coerce_int,
    coerce_str,
    require_mapping,
    validate_choice,
    validate_range,
)

#: Node roles a deployed system may join as, matching
#: ``common.enums.NodeRole``.
NODE_ROLES: tuple[str, ...] = (
    "standalone",
    "cluster_member",
    "cluster_master",
)

#: Default Proxmox VE API port.
DEFAULT_API_PORT: int = 8006


@dataclass(slots=True)
class ClusterConfig:
    """
    Target Proxmox cluster identity and join policy.
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    cluster_name: str = ""
    primary_node_host: str = ""
    api_port: int = DEFAULT_API_PORT

    node_role: str = "cluster_member"
    shared_storage_name: Optional[str] = None

    verify_tls: bool = True
    reachability_timeout_seconds: int = 30

    #: Name of the environment variable holding the cluster join
    #: token/password. The token itself is intentionally never stored
    #: in this configuration file (REQ-SEC-008: "Sensitive
    #: configuration values shall not be stored in source code" --
    #: applied here to configuration data as well, on the same
    #: least-privilege principle).
    join_token_env_var: str = "AQUILA_CLUSTER_JOIN_TOKEN"

    extensions: dict[str, Any] = field(default_factory=lambda: {})

    def __post_init__(self) -> None:
        """Validate cluster policy invariants."""

        validate_choice(
            self.node_role,
            NODE_ROLES,
            field_name="node_role",
        )

        validate_range(
            self.api_port,
            field_name="api_port",
            minimum=1,
            maximum=65535,
        )

        validate_range(
            self.reachability_timeout_seconds,
            field_name="reachability_timeout_seconds",
            minimum=1,
        )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ClusterConfig:
        """Construct a validated ``ClusterConfig`` from a raw mapping."""

        mapping = require_mapping(data, section="cluster")

        known_keys = {
            "schema_version",
            "cluster_name",
            "primary_node_host",
            "api_port",
            "node_role",
            "shared_storage_name",
            "verify_tls",
            "reachability_timeout_seconds",
            "join_token_env_var",
        }

        extensions = {
            key: value
            for key, value in mapping.items()
            if key not in known_keys
        }

        shared_storage_name = mapping.get("shared_storage_name")

        return cls(
            cluster_name=coerce_str(
                mapping.get("cluster_name"),
                field_name="cluster_name",
                default="",
            ),
            primary_node_host=coerce_str(
                mapping.get("primary_node_host"),
                field_name="primary_node_host",
                default="",
            ),
            api_port=coerce_int(
                mapping.get("api_port"),
                field_name="api_port",
                default=DEFAULT_API_PORT,
            ),
            node_role=coerce_str(
                mapping.get("node_role"),
                field_name="node_role",
                default="cluster_member",
            ),
            shared_storage_name=(
                coerce_str(
                    shared_storage_name,
                    field_name="shared_storage_name",
                )
                if shared_storage_name is not None
                else None
            ),
            verify_tls=coerce_bool(
                mapping.get("verify_tls"),
                field_name="verify_tls",
                default=True,
            ),
            reachability_timeout_seconds=coerce_int(
                mapping.get("reachability_timeout_seconds"),
                field_name="reachability_timeout_seconds",
                default=30,
            ),
            join_token_env_var=coerce_str(
                mapping.get("join_token_env_var"),
                field_name="join_token_env_var",
                default="AQUILA_CLUSTER_JOIN_TOKEN",
            ),
            extensions=extensions,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a YAML/JSON-serializable dictionary representation."""

        return {
            "schema_version": self.SCHEMA_VERSION,
            "cluster_name": self.cluster_name,
            "primary_node_host": self.primary_node_host,
            "api_port": self.api_port,
            "node_role": self.node_role,
            "shared_storage_name": self.shared_storage_name,
            "verify_tls": self.verify_tls,
            "reachability_timeout_seconds": (
                self.reachability_timeout_seconds
            ),
            "join_token_env_var": self.join_token_env_var,
            **self.extensions,
        }


__all__ = ["DEFAULT_API_PORT", "NODE_ROLES", "ClusterConfig"]
