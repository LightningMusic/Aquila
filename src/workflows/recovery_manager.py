"""
Project Aquila
=============

Workflow: Recovery Stage

Thin orchestration-layer adapter around
``recovery.recovery_manager.RecoveryManager`` (SRS Section 10.4,
REQ-REC-001 through REQ-REC-026) for SRS Appendix B, Workflow A
(Device Retirement).

What this adapter adds beyond a pass-through
-------------------------------------------------
``RecoveryManager.run()`` already enforces REQ-REC-016 (skipping
requires a non-empty technician acknowledgement) and REQ-REC-006
(recovering requires a non-empty selection) structurally, at the
engine layer -- this adapter does not re-implement that validation.
What it adds is :class:`RecoveryDecision`: a small, explicit value
type with one constructor per branch (:meth:`RecoveryDecision.skip`
and :meth:`RecoveryDecision.recover`), so a caller (eventually the
Technician Console/CLI) cannot accidentally construct an ambiguous
call -- for example, passing ``skip=False`` with no
``selected_paths`` by omission, which today only fails *inside*
``RecoveryManager.run()`` after the stage has already announced it
started. Requiring a ``RecoveryDecision`` up front makes that
mistake a construction-time error instead, and gives
``workflows.deployment_manager`` (and a future Console) one
unambiguous object to build from a volume-browser session
(REQ-REC-004/005/006) before calling this stage's ``run()`` at all.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from common.constants.logging import WORKFLOW_LOGGER
from inspection.report import HardwareInspectionReport
from recovery.browser import RecoveryVolume
from recovery.copier import ProgressCallback as RecoveryProgressCallback
from recovery.recovery_manager import RecoveryManager
from recovery.report import RecoverySummary

from .progress import WorkflowProgressCallback, emit

if TYPE_CHECKING:
    from common.events.bus import EventBus

logger = logging.getLogger(WORKFLOW_LOGGER)

STAGE_NAME = "recovery"


@dataclass(slots=True, frozen=True)
class RecoveryDecision:
    """
    The technician's explicit recovery decision (REQ-REC-015/016),
    constructed through one of the two named factories below rather
    than directly -- see the module docstring for why.
    """

    skip: bool
    technician_acknowledgement: Optional[str] = None
    destination: Optional[Path] = None
    selected_paths: list[Path] = field(default_factory=list[Path])

    @classmethod
    def recover(
        cls, *, destination: Path, selected_paths: list[Path]
    ) -> "RecoveryDecision":
        """REQ-REC-006: the technician's file/directory selection."""

        return cls(
            skip=False,
            destination=destination,
            selected_paths=list(selected_paths),
        )

    @classmethod
    def skip_with_acknowledgement(cls, acknowledgement: str) -> "RecoveryDecision":
        """REQ-REC-016: recovery intentionally skipped."""

        return cls(skip=True, technician_acknowledgement=acknowledgement)


class RecoveryWorkflowStage:
    """
    Runs the Recovery Engine as one stage of Workflow A (Device
    Retirement).

    Satisfies ``interfaces.service.Service``.
    """

    def __init__(
        self,
        *,
        recovery_manager: Optional[RecoveryManager] = None,
        event_bus: Optional["EventBus"] = None,
    ) -> None:
        self._manager = recovery_manager or RecoveryManager(event_bus)
        self._initialized = False

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        self._manager.initialize()
        self._initialized = True

    def shutdown(self) -> None:
        self._manager.shutdown()
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def last_summary(self) -> Optional[RecoverySummary]:
        return self._manager.last_summary

    # ------------------------------------------------------------------
    # REQ-REC-004/005: volume discovery, for the Console/CLI's browser
    # ------------------------------------------------------------------

    def discover_volumes(
        self, inspection_report: HardwareInspectionReport
    ) -> list[RecoveryVolume]:
        """
        Discover readable volumes so a caller can present them
        (REQ-REC-004) before building a :class:`RecoveryDecision`.
        """

        if not self._initialized:
            self.initialize()

        return self._manager.discover_volumes(inspection_report)

    # ------------------------------------------------------------------
    # Stage: Recovery (REQ-REC-001 through REQ-REC-026)
    # ------------------------------------------------------------------

    def run(
        self,
        inspection_report: HardwareInspectionReport,
        decision: RecoveryDecision,
        *,
        node_name: str,
        progress_callback: Optional[RecoveryProgressCallback] = None,
        workflow_progress_callback: Optional[WorkflowProgressCallback] = None,
    ) -> RecoverySummary:
        """
        Run (or explicitly skip) recovery for ``decision``.

        Args:
            inspection_report: The completed inspection report proving
                REQ-REC-001's dependency, forwarded unchanged to
                ``RecoveryManager.run()``.
            decision: What the technician chose -- built via
                :meth:`RecoveryDecision.recover` or
                :meth:`RecoveryDecision.skip_with_acknowledgement`.
            node_name: Identifies the target system in emitted events.
            progress_callback: ``recovery.copier.ProgressCallback`` --
                forwarded straight through to
                ``RecoveryManager.run()`` for REQ-REC-011's
                file-level copy progress.
            workflow_progress_callback: Notified at this stage's
                start/completion (REQ-TC-009), a coarser signal than
                ``progress_callback`` above -- see ``workflows.progress``'s
                module docstring for the distinction.

        Raises:
            RecoveryValidationError: Propagated unchanged from
                ``RecoveryManager.run()`` -- structurally unreachable
                through a validly-constructed ``RecoveryDecision``, but
                not suppressed here in case a caller constructs one
                directly rather than through the named factories.
        """

        if not self._initialized:
            self.initialize()

        if decision.skip:
            emit(
                workflow_progress_callback,
                STAGE_NAME,
                "Recovery skipped by technician acknowledgement.",
                logger=logger,
            )
        else:
            emit(
                workflow_progress_callback,
                STAGE_NAME,
                f"Recovering {len(decision.selected_paths)} selected "
                f"path(s) to {decision.destination}.",
                logger=logger,
            )

        summary = self._manager.run(
            inspection_report,
            node_name=node_name,
            skip=decision.skip,
            technician_acknowledgement=decision.technician_acknowledgement,
            destination=decision.destination,
            selected_paths=decision.selected_paths or None,
            progress_callback=progress_callback,
        )

        if summary.is_complete:
            emit(
                workflow_progress_callback,
                STAGE_NAME,
                f"Recovery stage complete: {summary.status_message}",
                logger=logger,
            )
        else:
            # REQ-REC-026: the technician must be informed of any
            # incomplete recovery before Preparation (a destructive
            # stage) may begin.
            emit(
                workflow_progress_callback,
                STAGE_NAME,
                f"Recovery stage INCOMPLETE: {summary.status_message}",
                severity="warning",
                logger=logger,
            )

        return summary

    # ------------------------------------------------------------------
    # Magic methods
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(initialized={self._initialized})"
        )


__all__ = [
    "STAGE_NAME",
    "RecoveryDecision",
    "RecoveryWorkflowStage",
]
