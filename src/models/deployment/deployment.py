"""
Project Aquila
=============

Deployment Approval Model

Represents the Deployment Controller's REQ-CTRL-016 authorization
decision for one node: "Deployment approval may be: Approved, Denied,
Pending manual approval." Consumed by
``deployment_controller.authorization.DeploymentAuthorizer`` and
persisted by ``inventory.database.InventoryDatabase``'s ``approvals``
table.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from common.enums import DeploymentApprovalStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class DeploymentApproval:
    """One node's deployment approval decision (REQ-CTRL-016)."""

    node_identifier: str
    status: DeploymentApprovalStatus = DeploymentApprovalStatus.PENDING
    reason: str = ""
    decided_by: str = ""
    decided_at: datetime = field(default_factory=_utcnow)

    @property
    def approved(self) -> bool:
        return self.status is DeploymentApprovalStatus.APPROVED

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DeploymentApproval":
        status_name = str(
            data.get("status") or DeploymentApprovalStatus.PENDING.name
        )
        try:
            status = DeploymentApprovalStatus[status_name]
        except KeyError:
            status = DeploymentApprovalStatus.PENDING

        decided_raw = data.get("decided_at")
        decided_at = _utcnow()
        if isinstance(decided_raw, str) and decided_raw:
            try:
                decided_at = datetime.fromisoformat(decided_raw)
            except ValueError:
                pass

        return cls(
            node_identifier=str(data.get("node_identifier") or ""),
            status=status,
            reason=str(data.get("reason") or ""),
            decided_by=str(data.get("decided_by") or ""),
            decided_at=decided_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_identifier": self.node_identifier,
            "status": self.status.name,
            "reason": self.reason,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at.isoformat(),
        }


__all__ = ["DeploymentApproval"]
