"""
Project Aquila
=============

Deployment Controller Authorization

Implements REQ-CTRL-016 ("The Deployment Controller shall provide
deployment approval decisions. Deployment approval may be: Approved,
Denied, Pending manual approval"), REQ-SEC-004 ("Unauthorized nodes
shall not receive deployment configuration"), and REQ-SEC-007
("Authorization failures shall be logged").

Owns the ``approvals`` table of ``inventory.database.InventoryDatabase``
directly -- a deliberately small, Controller-owned table distinct from
the Inventory Engine's own tables (``nodes``,
``deployment_sessions``/``deployment_reports``/``benchmarks``, all
owned by ``inventory.node_registry``/``inventory.inventory_manager``):
approval is a Controller policy decision (REQ-CTRL-016), not an
inventory fact, even though both live in the same physical database
file (see ``inventory.database``'s module docstring for why one file).
This persisted ``approvals`` table -- one row per node, holding its
current approve/deny/pending decision and who decided it -- is this
Controller's REQ-CTRL-008 deployment policy database.

No operator-facing approval UI exists yet (``technician_console`` is
not yet built), so today ``auto_approve_nodes`` (``ControllerServerConfig``)
is the only way a node reaches Approved; ``set_approval`` exists so a
future manual-approval workflow can override the default without
requiring a change here.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from common.constants.logging import INVENTORY_LOGGER
from common.enums import DeploymentApprovalStatus
from common.events.types.controller import NodeApprovedEvent, NodeDeniedEvent
from inventory.database import InventoryDatabase
from models.deployment.deployment import DeploymentApproval

logger = logging.getLogger(INVENTORY_LOGGER)


@dataclass(slots=True, frozen=True)
class AuthorizationResult:
    """The outcome of one REQ-CTRL-016/REQ-SEC-004 authorization check."""

    approved: bool
    status: DeploymentApprovalStatus
    detail: str = ""


class ApprovalStore:
    """CRUD over the ``approvals`` table."""

    def __init__(self, database: InventoryDatabase) -> None:
        self._database = database

    def get(self, node_identifier: str) -> Optional[DeploymentApproval]:
        with self._database.connection() as conn:
            row = conn.execute(
                "SELECT * FROM approvals WHERE node_identifier = ?",
                (node_identifier,),
            ).fetchone()

        return DeploymentApproval.from_dict(dict(row)) if row is not None else None

    def upsert(self, approval: DeploymentApproval) -> DeploymentApproval:
        with self._database.connection() as conn:
            conn.execute(
                """
                INSERT INTO approvals
                    (node_identifier, status, reason, decided_by, decided_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(node_identifier) DO UPDATE SET
                    status = excluded.status,
                    reason = excluded.reason,
                    decided_by = excluded.decided_by,
                    decided_at = excluded.decided_at
                """,
                (
                    approval.node_identifier,
                    approval.status.name,
                    approval.reason,
                    approval.decided_by,
                    approval.decided_at.isoformat(),
                ),
            )

        return approval


class DeploymentAuthorizer:
    """Authorizes deployment configuration release (REQ-CTRL-016, REQ-SEC-004)."""

    def __init__(
        self,
        *,
        store: ApprovalStore,
        auto_approve: bool = True,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._store = store
        self._auto_approve = auto_approve
        self._event_bus = event_bus

    def authorize(self, node_identifier: str) -> AuthorizationResult:
        """
        Return whether ``node_identifier`` may receive deployment
        configuration right now. Creates a fresh approval record (per
        ``auto_approve`` policy) the first time a node is seen.
        """

        existing = self._store.get(node_identifier)

        if existing is None:
            existing = self._decide_initial(node_identifier)

        if existing.status is DeploymentApprovalStatus.APPROVED:
            return AuthorizationResult(
                approved=True,
                status=existing.status,
                detail="Deployment approved.",
            )

        if existing.status is DeploymentApprovalStatus.DENIED:
            detail = f"Deployment denied: {existing.reason or 'no reason recorded'}."
        else:
            detail = "Deployment is pending manual approval."

        logger.warning(
            "Authorization failed for node '%s': %s", node_identifier, detail
        )
        return AuthorizationResult(approved=False, status=existing.status, detail=detail)

    def set_approval(
        self,
        node_identifier: str,
        status: DeploymentApprovalStatus,
        *,
        reason: str = "",
        decided_by: str = "controller",
    ) -> DeploymentApproval:
        """Manually record an approval decision (future operator UI hook)."""

        approval = DeploymentApproval(
            node_identifier=node_identifier,
            status=status,
            reason=reason,
            decided_by=decided_by,
            decided_at=datetime.now(timezone.utc),
        )
        self._store.upsert(approval)

        if status is DeploymentApprovalStatus.APPROVED:
            self._publish(lambda: NodeApprovedEvent(node_identifier))
        elif status is DeploymentApprovalStatus.DENIED:
            self._publish(lambda: NodeDeniedEvent(node_identifier, reason))

        return approval

    def is_denied(self, node_identifier: str) -> bool:
        """Used by ``NodeAuthenticator`` as its revocation check."""

        existing = self._store.get(node_identifier)
        return existing is not None and existing.status is DeploymentApprovalStatus.DENIED

    def _decide_initial(self, node_identifier: str) -> DeploymentApproval:
        status = (
            DeploymentApprovalStatus.APPROVED
            if self._auto_approve
            else DeploymentApprovalStatus.PENDING
        )
        approval = self.set_approval(
            node_identifier,
            status,
            reason=(
                "Auto-approved by Controller policy."
                if self._auto_approve
                else ""
            ),
            decided_by="controller-auto-approve" if self._auto_approve else "",
        )
        return approval

    def _publish(self, build_event: Callable[[], Any]) -> None:
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish(build_event())
        except Exception:  # pragma: no cover - event delivery is best-effort
            logger.debug("Failed to publish authorization event.", exc_info=True)


__all__ = ["ApprovalStore", "AuthorizationResult", "DeploymentAuthorizer"]
