"""
Project Aquila
=============

Workflow: Preparation Stage

Thin orchestration-layer adapter around
``preparation.preparation_manager.PreparationManager`` (SRS Section
10.5, REQ-PREP-001 through REQ-PREP-024) for SRS Appendix B, Workflow
A (Device Retirement) and Workflow B (Aquila Node Provisioning) --
both share Preparation as a stage.

What this adapter adds beyond a pass-through
-------------------------------------------------
``PreparationManager.run()`` already validates confirmations against
REQ-PREP-004 through -007 before sanitizing anything -- this adapter
does not re-implement that check. What it adds is the REQ-PREP-002/003
mandated sequencing REQ-TC-012 ("prevent destructive operations from
beginning until all required operator confirmations have been
completed") actually requires at the *workflow* level: the technician
must see the pre-flight summary (REQ-PREP-002: manufacturer, model,
serial, target storage, capacity, recovery status, workflow) and the
irreversibility notice (REQ-PREP-003) *before* being asked to confirm
anything, not as a side-effect the caller has to remember to display
separately. :class:`PreparationConfirmationRequest` bundles exactly
that mandated summary; :meth:`PreparationWorkflowStage.run` accepts a
``confirmation_provider`` callback that receives it and must return
the technician's completed ``PreparationConfirmations`` -- a single
call boundary that structurally enforces "summary shown, then
confirmed", the same kind of safety improvement
``workflows.recovery_manager.RecoveryDecision`` makes for Recovery.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional

from common.constants.deployment import FORCE_CONFIRMATION_PHRASE
from common.constants.logging import WORKFLOW_LOGGER
from config.schemas.deployment_schema import DeploymentConfig
from models.hardware.storage import StorageDevice, StorageInventory
from preparation.confirmations import PreparationConfirmations
from preparation.preparation_manager import PreparationManager
from preparation.report import PreparationSummary
from preparation.sanitizer import ProgressCallback as SanitizationProgressCallback
from recovery.report import RecoverySummary

from .progress import WorkflowProgressCallback, emit

if TYPE_CHECKING:
    from common.events.bus import EventBus

logger = logging.getLogger(WORKFLOW_LOGGER)

STAGE_NAME = "preparation"


@dataclass(slots=True, frozen=True)
class PreparationConfirmationRequest:
    """
    REQ-PREP-002/003's mandated pre-flight summary, shown to the
    technician before any confirmation is collected.
    """

    system_manufacturer: str
    system_model: str
    system_serial_number: str
    target_devices: tuple[StorageDevice, ...]
    recovery_status: str
    deployment_workflow: str
    required_confirmation_count: int
    force_confirmation_phrase: str

    @property
    def target_storage_summary(self) -> str:
        return ", ".join(
            f"{device.model or 'Unknown model'} "
            f"({device.device_path}, {device.serial_number or 'no serial'})"
            for device in self.target_devices
        )

    @property
    def summary_text(self) -> str:
        """
        REQ-PREP-002's summary and REQ-PREP-003's irreversibility
        notice, rendered as one block of text -- the single source of
        truth every caller (Technician Console, CLI, functional tests)
        should display verbatim rather than re-deriving its own
        wording.
        """

        return (
            f"System: {self.system_manufacturer} {self.system_model} "
            f"(serial: {self.system_serial_number or 'unknown'})\n"
            f"Target storage device(s): {self.target_storage_summary}\n"
            f"Recovery status: {self.recovery_status}\n"
            f"Deployment workflow: {self.deployment_workflow}\n"
            f"Confirmations required: {self.required_confirmation_count}\n"
            "\n"
            "WARNING: every operation from this point forward is "
            "IRREVERSIBLE. The selected storage device(s) will be "
            "PERMANENTLY ERASED. This cannot be undone."
        )


#: Given the mandated summary, returns the technician's completed
#: confirmations. Raising is a valid way to represent "the technician
#: declined" -- ``PreparationManager.run()`` will surface an
#: incomplete/empty ``PreparationConfirmations`` as a
#: ``DeploymentValidationError`` either way.
PreparationConfirmationProvider = Callable[
    [PreparationConfirmationRequest], PreparationConfirmations
]


class PreparationWorkflowStage:
    """
    Runs the Preparation Engine as one stage of a deployment workflow.

    Satisfies ``interfaces.service.Service``.
    """

    def __init__(
        self,
        *,
        preparation_manager: Optional[PreparationManager] = None,
        event_bus: Optional["EventBus"] = None,
    ) -> None:
        self._manager = preparation_manager or PreparationManager(event_bus)
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
    def last_summary(self) -> Optional[PreparationSummary]:
        return self._manager.last_summary

    # ------------------------------------------------------------------
    # Stage: Preparation (REQ-PREP-001 through REQ-PREP-024)
    # ------------------------------------------------------------------

    def run(
        self,
        recovery_summary: RecoverySummary,
        *,
        node_name: str,
        target_devices: list[StorageDevice],
        storage_inventory: StorageInventory,
        deployment_config: DeploymentConfig,
        confirmation_provider: PreparationConfirmationProvider,
        system_manufacturer: str = "",
        system_model: str = "",
        system_serial_number: str = "",
        deployment_workflow: str = "",
        operator_identity: Optional[str] = None,
        progress_callback: Optional[SanitizationProgressCallback] = None,
        workflow_progress_callback: Optional[WorkflowProgressCallback] = None,
    ) -> PreparationSummary:
        """
        Build the REQ-PREP-002/003 mandated summary, obtain the
        technician's confirmations through ``confirmation_provider``,
        and (if REQ-PREP-004 through -007 are satisfied) sanitize
        every device in ``target_devices``.

        Args:
            recovery_summary, node_name, target_devices,
            storage_inventory, deployment_config, system_manufacturer,
            system_model, system_serial_number, deployment_workflow,
            operator_identity, progress_callback: Forwarded to
                ``PreparationManager.run()`` unchanged -- see that
                method's own docstring.
            confirmation_provider: Receives the mandated pre-flight
                summary (REQ-PREP-002/003) and must return the
                technician's completed confirmations.
            workflow_progress_callback: Notified at this stage's
                start/completion (REQ-TC-009).

        Raises:
            DeploymentPreparationError, DeploymentValidationError,
            DeploymentConfigurationError: Propagated unchanged from
                ``PreparationManager.run()``.
        """

        if not self._initialized:
            self.initialize()

        request = PreparationConfirmationRequest(
            system_manufacturer=system_manufacturer,
            system_model=system_model,
            system_serial_number=system_serial_number,
            target_devices=tuple(target_devices),
            recovery_status=recovery_summary.status_message,
            deployment_workflow=deployment_workflow,
            required_confirmation_count=deployment_config.confirmation_count,
            force_confirmation_phrase=FORCE_CONFIRMATION_PHRASE,
        )

        emit(
            workflow_progress_callback,
            STAGE_NAME,
            "Preparation summary presented; awaiting operator confirmation "
            "(REQ-TC-012).",
            logger=logger,
        )

        confirmations = confirmation_provider(request)

        emit(
            workflow_progress_callback,
            STAGE_NAME,
            f"Sanitizing {len(target_devices)} target device(s).",
            logger=logger,
        )

        summary = self._manager.run(
            recovery_summary,
            node_name=node_name,
            target_devices=target_devices,
            storage_inventory=storage_inventory,
            deployment_config=deployment_config,
            confirmations=confirmations,
            system_manufacturer=system_manufacturer,
            system_model=system_model,
            system_serial_number=system_serial_number,
            deployment_workflow=deployment_workflow,
            operator_identity=operator_identity,
            progress_callback=progress_callback,
        )

        if summary.all_succeeded:
            emit(
                workflow_progress_callback,
                STAGE_NAME,
                f"Preparation stage complete: {summary.status_message}",
                logger=logger,
            )
        else:
            emit(
                workflow_progress_callback,
                STAGE_NAME,
                f"Preparation stage FAILED: {summary.status_message}",
                severity="error",
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
    "PreparationConfirmationProvider",
    "PreparationConfirmationRequest",
    "PreparationWorkflowStage",
]
