"""
Project Aquila
=============

Workflow: Inspection Stage

Thin orchestration-layer adapter around
``inspection.inspector.InspectionManager`` (SRS Section 10.3,
REQ-INS-001 through REQ-INS-028), giving both SRS Appendix B workflows
a uniform stage boundary: own the ``Service`` lifecycle of the
underlying engine manager, announce stage start/completion through
``workflows.progress`` (REQ-TC-009), and translate the one exception
``InspectionManager.run()`` can raise into the same halted-workflow
shape every other ``workflows/*_manager.py`` adapter uses.

Why this adapter exists at all
----------------------------------
Inspection needs no operator confirmation (REQ-INS-026: inspection is
read-only) and ``InspectionManager.run()`` already does essentially
everything REQ-INS-001 through -025 require in one call -- so unlike
``workflows.preparation_manager``/``workflows.provisioning_manager``,
this adapter adds no new orchestration logic of its own. It exists so
``workflows.deployment_manager`` has exactly one uniform shape to call
for every stage (own lifecycle, ``run()`` returns a stage result,
progress events flow through the same ``WorkflowStageEvent`` channel),
rather than special-casing Inspection as the one stage that talks
directly to its engine manager while every other stage goes through an
adapter.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from common.constants.logging import WORKFLOW_LOGGER
from common.exceptions.hardware import HardwareDetectionError
from inspection.inspector import InspectionManager
from inspection.report import HardwareInspectionReport

from .progress import WorkflowProgressCallback, emit

if TYPE_CHECKING:
    # Imported only for type annotations -- this module never
    # constructs an EventBus itself, the caller owns it and passes one
    # in, matching every engine manager's own identical convention
    # (see inspection.inspector.InspectionManager's docstring).
    from common.events.bus import EventBus

logger = logging.getLogger(WORKFLOW_LOGGER)

#: This stage's identifier in every ``WorkflowStageEvent`` it emits.
STAGE_NAME = "inspection"


class InspectionWorkflowError(RuntimeError):
    """
    Raised when the Inspection stage cannot produce a hardware
    inspection report at all.

    Wraps ``common.exceptions.hardware.HardwareDetectionError`` --
    REQ-INS-025 requires a report before any deployment workflow may
    proceed, so a caller of ``workflows.deployment_manager`` needs a
    single, stage-scoped exception type to catch regardless of which
    underlying engine failed, matching the discipline every other
    ``workflows/*_manager.py`` module (``RecoveryWorkflowStage``,
    ``PreparationWorkflowStage``, ...) already follows for its own
    engine's failures.
    """


class InspectionWorkflowStage:
    """
    Runs the Inspection Engine as one stage of a deployment workflow.

    Satisfies ``interfaces.service.Service``.
    """

    def __init__(
        self,
        *,
        inspection_manager: Optional[InspectionManager] = None,
        event_bus: Optional["EventBus"] = None,
    ) -> None:
        self._manager = inspection_manager or InspectionManager(event_bus)
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
    def last_report(self) -> Optional[HardwareInspectionReport]:
        return self._manager.last_report

    # ------------------------------------------------------------------
    # Stage: Inspection (REQ-INS-001 through REQ-INS-028)
    # ------------------------------------------------------------------

    def run(
        self,
        *,
        node_name: str,
        progress_callback: Optional[WorkflowProgressCallback] = None,
    ) -> HardwareInspectionReport:
        """
        Run hardware inspection and return the resulting report.

        Args:
            node_name: Identifies the target system in emitted stage
                events, matching every other stage adapter's
                ``node_name`` convention (itself matching every
                underlying engine manager's own ``node_name``
                parameter, e.g. ``RecoveryManager.run()``).
            progress_callback: Notified at stage start/completion/
                failure.

        Raises:
            InspectionWorkflowError: If the underlying
                ``InspectionManager.run()`` could not assemble a
                report at all (a catastrophic failure -- ordinary
                per-category hardware problems degrade to a ``FAIL``
                ``CategoryAssessment`` within the report instead of
                raising, so this is genuinely rare).
        """

        if not self._initialized:
            self.initialize()

        emit(
            progress_callback,
            STAGE_NAME,
            f"Inspecting hardware for '{node_name}'.",
            logger=logger,
        )

        try:
            report = self._manager.run()
        except HardwareDetectionError as exc:
            emit(
                progress_callback,
                STAGE_NAME,
                f"Inspection failed: {exc}",
                severity="error",
                logger=logger,
            )
            raise InspectionWorkflowError(str(exc)) from exc

        if report.failure_count:
            emit(
                progress_callback,
                STAGE_NAME,
                f"Inspection completed with {report.failure_count} "
                f"failed categor(y/ies): {report.overall_result.name}.",
                severity="warning",
                logger=logger,
            )
        elif report.warning_count:
            emit(
                progress_callback,
                STAGE_NAME,
                f"Inspection completed with {report.warning_count} "
                f"warning(s): {report.overall_result.name}.",
                severity="warning",
                logger=logger,
            )
        else:
            emit(
                progress_callback,
                STAGE_NAME,
                "Inspection completed: all categories passed.",
                logger=logger,
            )

        return report

    # ------------------------------------------------------------------
    # Magic methods
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(initialized={self._initialized})"
        )


__all__ = ["STAGE_NAME", "InspectionWorkflowError", "InspectionWorkflowStage"]
