"""
Project Aquila
=============

Deployment Session Model

Represents one recorded attempt at deploying a node (REQ-CTRL-010:
"The Deployment Controller shall record every deployment session").
A session is opened when a node first authenticates and is updated as
it progresses through ``common.enums.DeploymentPhase`` -- distinct
from ``models.inventory.node.InventoryRecord.status``
(``common.enums.NodeStatus``), which tracks the *node's* current
lifecycle state rather than one historical attempt; a node retains
one inventory record but may accumulate many session records across
redeployments.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from common.enums import DeploymentPhase, DeploymentStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_optional_timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


@dataclass(slots=True)
class DeploymentSessionRecord:
    """One recorded deployment session (REQ-CTRL-010/011/012)."""

    node_identifier: str
    workflow: str = "provisioning"
    phase: str = DeploymentPhase.PROVISIONING.name
    status: str = DeploymentStatus.RUNNING.name
    detail: str = ""

    id: Optional[int] = None
    started_at: datetime = field(default_factory=_utcnow)
    completed_at: Optional[datetime] = None

    def mark_completed(self, *, status: DeploymentStatus, detail: str = "") -> None:
        """Close out this session with a terminal status."""

        self.status = status.name
        self.detail = detail
        self.completed_at = _utcnow()

    @property
    def is_open(self) -> bool:
        return self.completed_at is None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DeploymentSessionRecord":
        raw_id = data.get("id")
        return cls(
            node_identifier=str(data.get("node_identifier") or ""),
            workflow=str(data.get("workflow") or "provisioning"),
            phase=str(data.get("phase") or DeploymentPhase.PROVISIONING.name),
            status=str(data.get("status") or DeploymentStatus.RUNNING.name),
            detail=str(data.get("detail") or ""),
            id=int(raw_id) if raw_id is not None else None,
            started_at=_parse_optional_timestamp(data.get("started_at"))
            or _utcnow(),
            completed_at=_parse_optional_timestamp(data.get("completed_at")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "node_identifier": self.node_identifier,
            "workflow": self.workflow,
            "phase": self.phase,
            "status": self.status,
            "detail": self.detail,
            "started_at": self.started_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
        }


__all__ = ["DeploymentSessionRecord"]
