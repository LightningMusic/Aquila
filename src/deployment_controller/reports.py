"""
Project Aquila
=============

Deployment Controller Report Intake

The HTTP-facing adapter for REQ-CTRL-015 ("The Deployment Controller
shall receive deployment reports") and REQ-CTRL-011 ("record
deployment failures"): validates ``POST nodes/completion`` payloads
(REQ-BOOT-016) and forwards them to
``inventory.inventory_manager.InventoryManager.record_report``, which
also closes the matching deployment session (REQ-CTRL-010) and
updates the node's inventory status (REQ-INV-004/005).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from common.constants.logging import INVENTORY_LOGGER
from inventory.inventory_manager import InventoryManager

logger = logging.getLogger(INVENTORY_LOGGER)


@dataclass(slots=True, frozen=True)
class ReportIntakeResult:
    """The outcome of one REQ-CTRL-015 completion-report intake."""

    accepted: bool
    detail: str = ""


class DeploymentReportIntake:
    """Validates and records REQ-BOOT-016 completion reports."""

    def __init__(self, *, inventory_manager: InventoryManager) -> None:
        self._inventory_manager = inventory_manager

    def record_completion(
        self, node_identifier: str, payload: Mapping[str, Any]
    ) -> ReportIntakeResult:
        status = str(payload.get("status") or "").strip()
        detail = str(payload.get("detail") or "")

        if not status:
            return ReportIntakeResult(
                accepted=False,
                detail="Completion report is missing a 'status' field.",
            )

        report = self._inventory_manager.record_report(
            node_identifier, status=status, detail=detail
        )

        if not report.successful:
            logger.warning(
                "Node '%s' reported a failed deployment: %s",
                node_identifier,
                detail or "(no detail provided)",
            )

        return ReportIntakeResult(
            accepted=True, detail="Completion report recorded."
        )


__all__ = ["DeploymentReportIntake", "ReportIntakeResult"]
