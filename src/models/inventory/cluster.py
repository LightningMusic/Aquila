"""
Project Aquila
=============

Cluster Membership Model

Records which Proxmox cluster a node belongs to, as part of its
inventory record (REQ-CTRL-007's "Cluster information" and
REQ-BOOT-012's "automatically enroll the node into the designated
Proxmox cluster"). Kept separate from ``models.inventory.node.
InventoryRecord`` -- whose ``cluster_name``/``node_role`` fields are a
denormalized summary for quick display/search -- so the Inventory
System can retain a node's full cluster membership history (a node
may be re-deployed into a different cluster over its lifetime)
without growing ``InventoryRecord`` into two responsibilities.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from common.enums import NodeRole


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True, frozen=True)
class ClusterMembership:
    """One recorded cluster-enrollment event for a node."""

    node_identifier: str
    cluster_name: str
    node_role: NodeRole = NodeRole.CLUSTER_MEMBER
    joined_at: datetime = field(default_factory=_utcnow)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ClusterMembership":
        role_name = str(data.get("node_role") or NodeRole.CLUSTER_MEMBER.name)
        try:
            role = NodeRole[role_name]
        except KeyError:
            role = NodeRole.CLUSTER_MEMBER

        joined_raw = data.get("joined_at")
        joined_at = _utcnow()
        if isinstance(joined_raw, str) and joined_raw:
            try:
                joined_at = datetime.fromisoformat(joined_raw)
            except ValueError:
                pass

        return cls(
            node_identifier=str(data.get("node_identifier") or ""),
            cluster_name=str(data.get("cluster_name") or ""),
            node_role=role,
            joined_at=joined_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_identifier": self.node_identifier,
            "cluster_name": self.cluster_name,
            "node_role": self.node_role.name,
            "joined_at": self.joined_at.isoformat(),
        }


__all__ = ["ClusterMembership"]
