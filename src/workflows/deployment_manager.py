"""
Project Aquila
=============

Workflow: Deployment Sequencer

Sequences SRS Appendix B's two deployment workflows -- Device
Retirement (Workflow A) and Aquila Node Provisioning (Workflow B) --
by composing the per-stage adapters this package defines
(:mod:`workflows.inspection_manager`, :mod:`workflows.recovery_manager`,
:mod:`workflows.preparation_manager`, :mod:`workflows.provisioning_manager`).
Both workflows share Inspection, Recovery, and Preparation as their
first three stages (Appendix B: Workflow A ends after Preparation;
Workflow B continues into Provisioning and, eventually, the separate
Phase Two Bootstrap stage) -- one class, ``DeploymentWorkflowManager``,
owns both sequences rather than two unrelated classes duplicating the
first three stages, matching this package's own prior planning note
(see ``claude/aquila-project-status.md``'s "Next up" section) that a
single sequencer, parameterized by which workflow is running, is the
right shape.

Refinement over that original plan: rather than one polymorphic
``run()`` method accepting a pile of workflow-specific optional
parameters (most of them meaningless for whichever workflow isn't
running), this module exposes two clearly-named, fully-typed methods
-- :meth:`DeploymentWorkflowManager.run_retirement_workflow` and
:meth:`DeploymentWorkflowManager.run_provisioning_workflow` -- sharing
the same instance, the same underlying stage adapters, and the same
``WorkflowSummary`` result type. This keeps every parameter concretely
typed and required exactly where it is actually used, at a small cost
in duplication between the two methods' shared first-three-stage
sequencing.

Mid-workflow technician decisions
--------------------------------------
Exactly like ``workflows.preparation_manager``'s
``confirmation_provider`` callback, the points in a deployment
workflow that need a technician's real-time input (which volumes to
recover, which storage device(s) to sanitize) are represented as
callbacks this sequencer invokes with the data the technician needs to
decide, rather than parameters the caller must have already resolved
before calling in. This keeps ``run_retirement_workflow``/
``run_provisioning_workflow`` a single synchronous call a Console/CLI
can drive end-to-end, while still giving the technician a real
decision point at each REQ-REC-004/005/REQ-PREP-005 juncture.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from common.constants.logging import WORKFLOW_LOGGER
from common.enums import WorkflowType
from config.schemas.cluster_schema import ClusterConfig
from config.schemas.controller_schema import ControllerConfig
from config.schemas.deployment_schema import DeploymentConfig
from config.schemas.network_schema import NetworkConfig
from inspection.report import HardwareInspectionReport
from models.hardware.storage import StorageDevice
from preparation.report import PreparationSummary
from preparation.sanitizer import ProgressCallback as SanitizationProgressCallback
from provisioning.boot_handoff import DEFAULT_MANIFEST_FILENAME
from recovery.browser import RecoveryVolume
from recovery.copier import ProgressCallback as RecoveryProgressCallback
from recovery.report import RecoverySummary

from .inspection_manager import InspectionWorkflowStage
from .preparation_manager import (
    PreparationConfirmationProvider,
    PreparationWorkflowStage,
)
from .progress import WorkflowProgressCallback, emit
from .provisioning_manager import (
    ProvisioningProfileTemplate,
    ProvisioningWorkflowResult,
    ProvisioningWorkflowStage,
)
from .recovery_manager import RecoveryDecision, RecoveryWorkflowStage

if TYPE_CHECKING:
    from common.events.bus import EventBus

logger = logging.getLogger(WORKFLOW_LOGGER)

STAGE_NAME = "deployment"

#: Given the completed inspection report, returns the technician's
#: recovery decision -- typically built from a UI session that first
#: called ``RecoveryWorkflowStage.discover_volumes()`` and let the
#: technician browse/select.
RecoveryDecisionProvider = Callable[
    [HardwareInspectionReport, list[RecoveryVolume]], RecoveryDecision
]

#: Given the completed inspection report, returns the storage
#: device(s) selected for sanitization (REQ-PREP-005) --
#: ``inspection_report.storage.data.eligible_for_deployment()`` is
#: what a caller should present as the candidate list.
TargetDeviceSelector = Callable[[HardwareInspectionReport], list[StorageDevice]]


@dataclass(slots=True, frozen=True)
class WorkflowSummary:
    """
    The full outcome of one deployment workflow run (REQ-TC-013:
    "generate a deployment summary upon completion of every deployment
    session").
    """

    workflow_type: WorkflowType
    node_name: str
    started_at: datetime
    completed_at: datetime
    inspection_report: Optional[HardwareInspectionReport]
    recovery_summary: Optional[RecoverySummary]
    preparation_summary: Optional[PreparationSummary]
    provisioning_result: Optional[ProvisioningWorkflowResult] = None
    aborted: bool = False
    abort_reason: Optional[str] = None

    @property
    def duration(self) -> timedelta:
        return self.completed_at - self.started_at

    @property
    def status_message(self) -> str:
        if self.aborted:
            return (
                f"{self.workflow_type.value} workflow halted: "
                f"{self.abort_reason}"
            )
        return f"{self.workflow_type.value} workflow completed successfully."

    def to_dict(self) -> dict[str, Any]:
        """
        A JSON-serializable rendering of this summary, composing every
        stage's own ``to_dict()`` where one already exists
        (``HardwareInspectionReport``, ``RecoverySummary``,
        ``PreparationSummary``, ``ProvisioningWorkflowResult``) rather
        than re-deriving their fields here.

        Added this session for ``cli/``'s ``--json`` output mode (a
        Technician Console does not need this -- it renders
        ``WorkflowSummary`` straight to Tk widgets), but kept here
        rather than in ``cli/`` since nothing about it is CLI-specific
        and every sibling summary type in this codebase already
        follows this same "the type that owns the data owns its
        ``to_dict()``" convention.
        """

        return {
            "workflow_type": self.workflow_type.value,
            "node_name": self.node_name,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_seconds": self.duration.total_seconds(),
            "aborted": self.aborted,
            "abort_reason": self.abort_reason,
            "status_message": self.status_message,
            "inspection_report": (
                self.inspection_report.to_dict()
                if self.inspection_report is not None
                else None
            ),
            "recovery_summary": (
                self.recovery_summary.to_dict()
                if self.recovery_summary is not None
                else None
            ),
            "preparation_summary": (
                self.preparation_summary.to_dict()
                if self.preparation_summary is not None
                else None
            ),
            "provisioning_result": (
                self.provisioning_result.to_dict()
                if self.provisioning_result is not None
                else None
            ),
        }


def _extract_system_identity(
    inspection_report: HardwareInspectionReport,
) -> tuple[str, str, str]:
    """
    REQ-PREP-002's system-identity fields, read from the BIOS/firmware
    category Inspection already collected (REQ-INS-016 through -019)
    rather than re-detected here.
    """

    firmware = inspection_report.bios.data.firmware
    return firmware.manufacturer, firmware.model, firmware.serial_number


class DeploymentWorkflowManager:
    """
    Sequences a full deployment session -- Device Retirement or Aquila
    Node Provisioning -- by composing this package's per-stage
    adapters. Satisfies ``interfaces.service.Service``.
    """

    def __init__(
        self,
        *,
        inspection_stage: Optional[InspectionWorkflowStage] = None,
        recovery_stage: Optional[RecoveryWorkflowStage] = None,
        preparation_stage: Optional[PreparationWorkflowStage] = None,
        provisioning_stage: Optional[ProvisioningWorkflowStage] = None,
        event_bus: Optional["EventBus"] = None,
    ) -> None:
        self._inspection = inspection_stage or InspectionWorkflowStage(
            event_bus=event_bus
        )
        self._recovery = recovery_stage or RecoveryWorkflowStage(event_bus=event_bus)
        self._preparation = preparation_stage or PreparationWorkflowStage(
            event_bus=event_bus
        )
        self._provisioning = provisioning_stage or ProvisioningWorkflowStage(
            event_bus=event_bus
        )
        self._initialized = False

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        self._inspection.initialize()
        self._recovery.initialize()
        self._preparation.initialize()
        self._provisioning.initialize()
        self._initialized = True

    def shutdown(self) -> None:
        self._inspection.shutdown()
        self._recovery.shutdown()
        self._preparation.shutdown()
        self._provisioning.shutdown()
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    # ------------------------------------------------------------------
    # Shared first three stages (Inspection -> Recovery -> Preparation)
    # ------------------------------------------------------------------

    def _run_inspection_and_recovery(
        self,
        *,
        node_name: str,
        recovery_decision_provider: RecoveryDecisionProvider,
        recovery_progress_callback: Optional[RecoveryProgressCallback],
        workflow_progress_callback: Optional[WorkflowProgressCallback],
    ) -> tuple[HardwareInspectionReport, RecoverySummary]:
        inspection_report = self._inspection.run(
            node_name=node_name,
            progress_callback=workflow_progress_callback,
        )

        volumes = self._recovery.discover_volumes(inspection_report)
        decision = recovery_decision_provider(inspection_report, volumes)

        recovery_summary = self._recovery.run(
            inspection_report,
            decision,
            node_name=node_name,
            progress_callback=recovery_progress_callback,
            workflow_progress_callback=workflow_progress_callback,
        )

        return inspection_report, recovery_summary

    def _run_preparation(
        self,
        *,
        recovery_summary: RecoverySummary,
        node_name: str,
        target_devices: list[StorageDevice],
        inspection_report: HardwareInspectionReport,
        deployment_config: DeploymentConfig,
        confirmation_provider: PreparationConfirmationProvider,
        workflow_type: WorkflowType,
        operator_identity: Optional[str],
        sanitization_progress_callback: Optional[SanitizationProgressCallback],
        workflow_progress_callback: Optional[WorkflowProgressCallback],
    ) -> PreparationSummary:
        manufacturer, model, serial = _extract_system_identity(inspection_report)

        return self._preparation.run(
            recovery_summary,
            node_name=node_name,
            target_devices=target_devices,
            storage_inventory=inspection_report.storage.data,
            deployment_config=deployment_config,
            confirmation_provider=confirmation_provider,
            system_manufacturer=manufacturer,
            system_model=model,
            system_serial_number=serial,
            deployment_workflow=workflow_type.value,
            operator_identity=operator_identity,
            progress_callback=sanitization_progress_callback,
            workflow_progress_callback=workflow_progress_callback,
        )

    # ------------------------------------------------------------------
    # Workflow A: Device Retirement (Appendix B)
    # ------------------------------------------------------------------

    def run_retirement_workflow(
        self,
        *,
        node_name: str,
        recovery_decision_provider: RecoveryDecisionProvider,
        target_device_selector: TargetDeviceSelector,
        deployment_config: DeploymentConfig,
        confirmation_provider: PreparationConfirmationProvider,
        operator_identity: Optional[str] = None,
        recovery_progress_callback: Optional[RecoveryProgressCallback] = None,
        sanitization_progress_callback: Optional[SanitizationProgressCallback] = None,
        workflow_progress_callback: Optional[WorkflowProgressCallback] = None,
    ) -> WorkflowSummary:
        """
        Run Workflow A end to end: Inspection -> Recovery -> Review ->
        Operator Approval -> Storage Sanitization -> Verification ->
        Retirement Complete.
        """

        if not self._initialized:
            self.initialize()

        started_at = datetime.now(UTC)
        emit(
            workflow_progress_callback,
            STAGE_NAME,
            f"Device Retirement workflow started for '{node_name}'.",
            logger=logger,
        )

        inspection_report, recovery_summary = self._run_inspection_and_recovery(
            node_name=node_name,
            recovery_decision_provider=recovery_decision_provider,
            recovery_progress_callback=recovery_progress_callback,
            workflow_progress_callback=workflow_progress_callback,
        )

        if not recovery_summary.is_complete:
            completed_at = datetime.now(UTC)
            emit(
                workflow_progress_callback,
                STAGE_NAME,
                "Device Retirement workflow halted: recovery did not "
                "complete (REQ-PREP-001/REQ-REC-017).",
                severity="error",
                logger=logger,
            )
            return WorkflowSummary(
                workflow_type=WorkflowType.RETIREMENT,
                node_name=node_name,
                started_at=started_at,
                completed_at=completed_at,
                inspection_report=inspection_report,
                recovery_summary=recovery_summary,
                preparation_summary=None,
                aborted=True,
                abort_reason=recovery_summary.status_message,
            )

        target_devices = target_device_selector(inspection_report)

        preparation_summary = self._run_preparation(
            recovery_summary=recovery_summary,
            node_name=node_name,
            target_devices=target_devices,
            inspection_report=inspection_report,
            deployment_config=deployment_config,
            confirmation_provider=confirmation_provider,
            workflow_type=WorkflowType.RETIREMENT,
            operator_identity=operator_identity,
            sanitization_progress_callback=sanitization_progress_callback,
            workflow_progress_callback=workflow_progress_callback,
        )

        completed_at = datetime.now(UTC)
        aborted = not preparation_summary.all_succeeded
        summary = WorkflowSummary(
            workflow_type=WorkflowType.RETIREMENT,
            node_name=node_name,
            started_at=started_at,
            completed_at=completed_at,
            inspection_report=inspection_report,
            recovery_summary=recovery_summary,
            preparation_summary=preparation_summary,
            aborted=aborted,
            abort_reason=(
                preparation_summary.status_message if aborted else None
            ),
        )

        emit(
            workflow_progress_callback,
            STAGE_NAME,
            summary.status_message,
            severity="error" if aborted else "info",
            logger=logger,
        )

        return summary

    # ------------------------------------------------------------------
    # Workflow B: Aquila Node Provisioning (Appendix B)
    # ------------------------------------------------------------------

    def run_provisioning_workflow(
        self,
        *,
        node_name: str,
        recovery_decision_provider: RecoveryDecisionProvider,
        target_device_selector: TargetDeviceSelector,
        provisioning_target_device: StorageDevice,
        deployment_config: DeploymentConfig,
        confirmation_provider: PreparationConfirmationProvider,
        controller_config: ControllerConfig,
        network_config: NetworkConfig,
        cluster_config: Optional[ClusterConfig],
        profile_template: ProvisioningProfileTemplate,
        root_password: str,
        phase_two_directory: Path,
        answer_file_destination: Path,
        identity_record_destination: Path,
        boot_entry_id: str,
        manifest_filename: str = DEFAULT_MANIFEST_FILENAME,
        trigger_handoff: bool = True,
        operator_identity: Optional[str] = None,
        recovery_progress_callback: Optional[RecoveryProgressCallback] = None,
        sanitization_progress_callback: Optional[SanitizationProgressCallback] = None,
        workflow_progress_callback: Optional[WorkflowProgressCallback] = None,
    ) -> WorkflowSummary:
        """
        Run Workflow B end to end: Inspection -> Hardware Validation ->
        Network Validation -> Operator Approval -> Proxmox Installation
        -> First Reboot (Bootstrap continues separately, in Phase Two
        -- see :mod:`workflows.bootstrap_manager`).

        Args:
            provisioning_target_device: The single storage device
                Proxmox VE is installed to -- must be one of the
                devices ``target_device_selector`` selects for
                sanitization; Preparation may sanitize more than one
                device (REQ-PREP-013), but Provisioning installs to
                exactly one (``ProvisioningManager.run()``'s
                ``target_device`` parameter).
            Every other parameter is forwarded to
                ``ProvisioningWorkflowStage.run()`` -- see that
                method's own docstring.
        """

        if not self._initialized:
            self.initialize()

        started_at = datetime.now(UTC)
        emit(
            workflow_progress_callback,
            STAGE_NAME,
            f"Aquila Node Provisioning workflow started for '{node_name}'.",
            logger=logger,
        )

        inspection_report, recovery_summary = self._run_inspection_and_recovery(
            node_name=node_name,
            recovery_decision_provider=recovery_decision_provider,
            recovery_progress_callback=recovery_progress_callback,
            workflow_progress_callback=workflow_progress_callback,
        )

        if not recovery_summary.is_complete:
            completed_at = datetime.now(UTC)
            emit(
                workflow_progress_callback,
                STAGE_NAME,
                "Provisioning workflow halted: recovery did not "
                "complete (REQ-PREP-001/REQ-REC-017).",
                severity="error",
                logger=logger,
            )
            return WorkflowSummary(
                workflow_type=WorkflowType.PROVISIONING,
                node_name=node_name,
                started_at=started_at,
                completed_at=completed_at,
                inspection_report=inspection_report,
                recovery_summary=recovery_summary,
                preparation_summary=None,
                aborted=True,
                abort_reason=recovery_summary.status_message,
            )

        target_devices = target_device_selector(inspection_report)

        preparation_summary = self._run_preparation(
            recovery_summary=recovery_summary,
            node_name=node_name,
            target_devices=target_devices,
            inspection_report=inspection_report,
            deployment_config=deployment_config,
            confirmation_provider=confirmation_provider,
            workflow_type=WorkflowType.PROVISIONING,
            operator_identity=operator_identity,
            sanitization_progress_callback=sanitization_progress_callback,
            workflow_progress_callback=workflow_progress_callback,
        )

        if not preparation_summary.all_succeeded:
            completed_at = datetime.now(UTC)
            emit(
                workflow_progress_callback,
                STAGE_NAME,
                f"Provisioning workflow halted: "
                f"{preparation_summary.status_message}",
                severity="error",
                logger=logger,
            )
            return WorkflowSummary(
                workflow_type=WorkflowType.PROVISIONING,
                node_name=node_name,
                started_at=started_at,
                completed_at=completed_at,
                inspection_report=inspection_report,
                recovery_summary=recovery_summary,
                preparation_summary=preparation_summary,
                aborted=True,
                abort_reason=preparation_summary.status_message,
            )

        provisioning_result = self._provisioning.run(
            preparation_summary,
            node_name=node_name,
            inspection_report=inspection_report,
            deployment_config=deployment_config,
            controller_config=controller_config,
            network_config=network_config,
            cluster_config=cluster_config,
            target_device=provisioning_target_device,
            profile_template=profile_template,
            root_password=root_password,
            phase_two_directory=phase_two_directory,
            answer_file_destination=answer_file_destination,
            identity_record_destination=identity_record_destination,
            boot_entry_id=boot_entry_id,
            manifest_filename=manifest_filename,
            trigger_handoff=trigger_handoff,
            workflow_progress_callback=workflow_progress_callback,
        )

        completed_at = datetime.now(UTC)
        summary = WorkflowSummary(
            workflow_type=WorkflowType.PROVISIONING,
            node_name=node_name,
            started_at=started_at,
            completed_at=completed_at,
            inspection_report=inspection_report,
            recovery_summary=recovery_summary,
            preparation_summary=preparation_summary,
            provisioning_result=provisioning_result,
            aborted=provisioning_result.aborted,
            abort_reason=provisioning_result.abort_reason,
        )

        emit(
            workflow_progress_callback,
            STAGE_NAME,
            summary.status_message,
            severity="error" if summary.aborted else "info",
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
    "DeploymentWorkflowManager",
    "RecoveryDecisionProvider",
    "TargetDeviceSelector",
    "WorkflowSummary",
]
