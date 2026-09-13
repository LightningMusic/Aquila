"""
Project Aquila
=============

Deployment Report Record Model

The Inventory System's persisted representation of one REQ-BOOT-016
completion report ("The Bootstrap Engine shall report deployment
completion to the Deployment Controller"), satisfying REQ-CTRL-015
("shall receive deployment reports") and REQ-INV-007 ("shall record
deployment reports").

``status``/``detail`` are kept as the free-text strings
``bootstrap.controller_client.DeploymentControllerClient.
report_completion()`` actually sends (``status="success"`` or
``status="failed"`` today, by convention of that already-delivered
caller) rather than re-typed against ``common.enums.DeploymentStatus``
-- coercing an external caller's free text into a closed enum here
would silently drop any status value a future Bootstrap revision
introduces; the enum is only imposed at the audit-log layer (this
report also drives ``models.inventory.node.InventoryRecord.status``
via ``inventory.inventory_manager.InventoryManager``, which does that
translation deliberately and explicitly).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True, frozen=True)
class DeploymentReportRecord:
    """One recorded REQ-BOOT-016 completion report."""

    node_identifier: str
    status: str
    detail: str = ""
    id: Optional[int] = None
    received_at: datetime = field(default_factory=_utcnow)

    @property
    def successful(self) -> bool:
        return self.status.strip().lower() in ("success", "succeeded", "ok")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DeploymentReportRecord":
        raw_id = data.get("id")
        received_raw = data.get("received_at")
        received_at = _utcnow()
        if isinstance(received_raw, str) and received_raw:
            try:
                received_at = datetime.fromisoformat(received_raw)
            except ValueError:
                pass

        return cls(
            node_identifier=str(data.get("node_identifier") or ""),
            status=str(data.get("status") or ""),
            detail=str(data.get("detail") or ""),
            id=int(raw_id) if raw_id is not None else None,
            received_at=received_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "node_identifier": self.node_identifier,
            "status": self.status,
            "detail": self.detail,
            "received_at": self.received_at.isoformat(),
        }


__all__ = ["DeploymentReportRecord"]
