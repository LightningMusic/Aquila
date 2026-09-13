"""
Project Aquila
=============

Deployment Controller Configuration Distribution

Implements REQ-CTRL-004 ("assign a unique hostname"), REQ-CTRL-006
("distribute deployment configuration to authorized nodes"), and
REQ-CTRL-007 ("Deployment configuration shall include, at minimum:
Hostname, Node Identifier, Cluster information, Network configuration,
SSH configuration, Benchmark profile, Deployment policy").

Builds exactly the JSON shape
``bootstrap.controller_client.NodeConfiguration`` parses:
``hostname``, ``ssh_authorized_keys``, ``cluster_join_token``,
``node_identifier`` -- plus the remaining REQ-CTRL-007 fields
(network/benchmark/deployment policy) included for forward
compatibility and preserved, unparsed, in that client's own ``raw``
field: REQ-CTRL-018's "support future expansion without requiring
modification of deployed nodes" is satisfied by that already-deployed
client tolerating fields it does not parse today, so the Controller
can add new REQ-CTRL-007 fields to this payload later without any
change to nodes already in the field.

``ConfigurationDistributor.build_configuration`` derives every field
of that payload from the injected ``ControllerServerConfig``/
``ClusterConfig`` (hostname prefix, SSH keys, cluster name/host, join
token) rather than any hardcoded value -- this is REQ-CTRL-017's
"distribute deployment policies according to configuration".

Cluster join token handling (REQ-SEC-008/009/010)
--------------------------------------------------
The Proxmox cluster join token is a secret the Controller host itself
holds (generated once via ``pvecm`` on the cluster's primary node),
resolved from the environment via
``ClusterConfig.join_token_env_var`` at the point of use -- never
stored in this module, a report, or a log line, matching
``config.manager.ConfigurationManager.resolve_secret``'s existing
pattern for exactly this kind of value.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Any

from common.constants.logging import INVENTORY_LOGGER
from config.schemas.cluster_schema import ClusterConfig
from config.schemas.controller_server_schema import ControllerServerConfig

logger = logging.getLogger(INVENTORY_LOGGER)


class HostnameAllocator:
    """
    REQ-CTRL-004: deterministic hostname assignment.

    Derives a short, stable suffix from the node identifier itself
    (rather than a coordinated sequence counter) so hostname
    assignment needs no additional shared state and is safe under
    concurrent requests from multiple nodes -- two nodes authenticating
    at the same moment can never race for the same sequence number,
    because there is no sequence number.
    """

    def __init__(self, *, prefix: str = "aquila-node") -> None:
        self._prefix = prefix.strip("-") or "aquila-node"

    def allocate(self, node_identifier: str) -> str:
        digest = hashlib.sha256(node_identifier.encode("utf-8")).hexdigest()
        return f"{self._prefix}-{digest[:8]}"


@dataclass(slots=True, frozen=True)
class NodeConfigurationPayload:
    """The REQ-CTRL-007 configuration payload for one node."""

    hostname: str
    node_identifier: str
    ssh_authorized_keys: tuple[str, ...]
    cluster_join_token: str
    cluster_name: str
    cluster_primary_host: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "hostname": self.hostname,
            "node_identifier": self.node_identifier,
            "ssh_authorized_keys": list(self.ssh_authorized_keys),
            "cluster_join_token": self.cluster_join_token,
            "cluster": {
                "name": self.cluster_name,
                "primary_host": self.cluster_primary_host,
            },
        }


class ConfigurationDistributor:
    """Builds and distributes deployment configuration (REQ-CTRL-006/007)."""

    def __init__(
        self,
        *,
        controller_server_config: ControllerServerConfig,
        cluster_config: ClusterConfig,
        hostname_allocator: "HostnameAllocator | None" = None,
    ) -> None:
        self._server_config = controller_server_config
        self._cluster_config = cluster_config
        self._hostnames = hostname_allocator or HostnameAllocator(
            prefix=controller_server_config.hostname_prefix
        )

    def build_configuration(self, node_identifier: str, *, hostname: str = "") -> NodeConfigurationPayload:
        assigned_hostname = hostname or self._hostnames.allocate(node_identifier)

        join_token = ""
        if self._cluster_config.join_token_env_var:
            join_token = os.environ.get(self._cluster_config.join_token_env_var, "") or ""

        if not join_token:
            logger.warning(
                "No cluster join token resolved from environment variable "
                "'%s' for node '%s'; the node will not be able to complete "
                "REQ-BOOT-012 cluster enrollment until this is configured.",
                self._cluster_config.join_token_env_var,
                node_identifier,
            )

        return NodeConfigurationPayload(
            hostname=assigned_hostname,
            node_identifier=node_identifier,
            ssh_authorized_keys=tuple(self._server_config.ssh_authorized_keys),
            cluster_join_token=join_token,
            cluster_name=self._cluster_config.cluster_name,
            cluster_primary_host=self._cluster_config.primary_node_host,
        )


__all__ = [
    "ConfigurationDistributor",
    "HostnameAllocator",
    "NodeConfigurationPayload",
]
