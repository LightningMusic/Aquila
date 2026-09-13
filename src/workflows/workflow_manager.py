"""
Project Aquila
=============

Workflow Manager

REQ-TC-006/007's actual entry point: "The Technician Console shall
provide access to the Device Retirement workflow" / "...to the Aquila
Node Provisioning workflow." Where
:class:`workflows.deployment_manager.DeploymentWorkflowManager`
sequences one workflow run's stages, ``WorkflowManager`` is the
single, top-level object a Technician Console or CLI actually holds:
it exposes exactly the two verbs REQ-TC-006/007 name
(:meth:`start_retirement_workflow`, :meth:`start_provisioning_workflow`),
and adds the one piece of state neither
``DeploymentWorkflowManager`` nor any single stage adapter tracks on
its own -- whether a deployment session is currently active at all.

Why this needs to exist as its own layer
---------------------------------------------
``DeploymentWorkflowManager.run_retirement_workflow()``/
``run_provisioning_workflow()`` are blocking, synchronous calls with
no externally visible "is one already running" state -- nothing stops
a caller from invoking either method twice concurrently from two
threads, which would mean two destructive operations racing against
the same hardware. ``WorkflowManager`` tracks
``common.enums.WorkflowState`` and refuses to start a second workflow
while one is already ``RUNNING``, giving REQ-TC-012's confirmation
gate real teeth at the session level, not just within a single
stage's own confirmation prompts.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from common.constants.logging import WORKFLOW_LOGGER
from common.enums import WorkflowState
from config.schemas.cluster_schema import ClusterConfig
from config.schemas.controller_schema import ControllerConfig
from config.schemas.deployment_schema import DeploymentConfig
from config.schemas.network_schema import NetworkConfig
from models.hardware.storage import StorageDevice
from preparation.sanitizer import ProgressCallback as SanitizationProgressCallback
from provisioning.boot_handoff import DEFAULT_MANIFEST_FILENAME
from recovery.copier import ProgressCallback as RecoveryProgressCallback

from .deployment_manager import (
    DeploymentWorkflowManager,
    RecoveryDecisionProvider,
    TargetDeviceSelector,
    WorkflowSummary,
)
from .preparation_manager import PreparationConfirmationProvider
from .progress import WorkflowProgressCallback
from .provisioning_manager import ProvisioningProfileTemplate

if TYPE_CHECKING:
    from common.events.bus import EventBus

logger = logging.getLogger(WORKFLOW_LOGGER)


class WorkflowAlreadyRunningError(RuntimeError):
    """
    Raised when a workflow is requested to start while another is
    already running (REQ-TC-012's session-level confirmation gate --
    see the module docstring).
    """


class WorkflowManager:
    """
    The Technician Console/CLI's top-level workflow entry point
    (REQ-TC-006/007). Satisfies ``interfaces.service.Service``.
    """

    def __init__(
        self,
        *,
        deployment_manager: Optional[DeploymentWorkflowManager] = None,
        event_bus: Optional["EventBus"] = None,
    ) -> None:
        self._deployment_manager = deployment_manager or DeploymentWorkflowManager(
            event_bus=event_bus
        )
        self._lock = threading.Lock()
        self._state = WorkflowState.IDLE
        self._last_summary: Optional[WorkflowSummary] = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        self._deployment_manager.initialize()
        self._initialized = True

    def shutdown(self) -> None:
        self._deployment_manager.shutdown()
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def state(self) -> WorkflowState:
        return self._state

    @property
    def last_summary(self) -> Optional[WorkflowSummary]:
        return self._last_summary

    # ------------------------------------------------------------------
    # REQ-TC-006: Device Retirement
    # ------------------------------------------------------------------

    def start_retirement_workflow(
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
        Start Workflow A (Device Retirement). Every parameter is
        forwarded unchanged to
        ``DeploymentWorkflowManager.run_retirement_workflow()`` -- see
        that method's own docstring.

        Raises:
            WorkflowAlreadyRunningError: If a workflow is already
                running.
        """

        return self._run(
            lambda: self._deployment_manager.run_retirement_workflow(
                node_name=node_name,
                recovery_decision_provider=recovery_decision_provider,
                target_device_selector=target_device_selector,
                deployment_config=deployment_config,
                confirmation_provider=confirmation_provider,
                operator_identity=operator_identity,
                recovery_progress_callback=recovery_progress_callback,
                sanitization_progress_callback=sanitization_progress_callback,
                workflow_progress_callback=workflow_progress_callback,
            )
        )

    # ------------------------------------------------------------------
    # REQ-TC-007: Aquila Node Provisioning
    # ------------------------------------------------------------------

    def start_provisioning_workflow(
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
        Start Workflow B (Aquila Node Provisioning). Every parameter
        is forwarded unchanged to ``DeploymentWorkflowManager
        .run_provisioning_workflow()`` -- see that method's own
        docstring.

        Raises:
            WorkflowAlreadyRunningError: If a workflow is already
                running.
        """

        return self._run(
            lambda: self._deployment_manager.run_provisioning_workflow(
                node_name=node_name,
                recovery_decision_provider=recovery_decision_provider,
                target_device_selector=target_device_selector,
                provisioning_target_device=provisioning_target_device,
                deployment_config=deployment_config,
                confirmation_provider=confirmation_provider,
                controller_config=controller_config,
                network_config=network_config,
                cluster_config=cluster_config,
                profile_template=profile_template,
                root_password=root_password,
                phase_two_directory=phase_two_directory,
                answer_file_destination=answer_file_destination,
                identity_record_destination=identity_record_destination,
                boot_entry_id=boot_entry_id,
                manifest_filename=manifest_filename,
                trigger_handoff=trigger_handoff,
                operator_identity=operator_identity,
                recovery_progress_callback=recovery_progress_callback,
                sanitization_progress_callback=sanitization_progress_callback,
                workflow_progress_callback=workflow_progress_callback,
            )
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run(self, runner: Callable[[], WorkflowSummary]) -> WorkflowSummary:
        if not self._initialized:
            self.initialize()

        with self._lock:
            if self._state is WorkflowState.RUNNING:
                raise WorkflowAlreadyRunningError(
                    "A deployment workflow is already running -- only "
                    "one may run at a time."
                )
            self._state = WorkflowState.RUNNING

        logger.info("Workflow session starting.")

        try:
            summary = runner()
        except Exception:
            with self._lock:
                self._state = WorkflowState.FAILED
            logger.exception("Workflow session raised unexpectedly.")
            raise

        with self._lock:
            self._last_summary = summary
            self._state = (
                WorkflowState.FAILED if summary.aborted else WorkflowState.COMPLETED
            )

        logger.info("Workflow session finished: %s", summary.status_message)

        return summary

    # ------------------------------------------------------------------
    # Magic methods
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(state={self._state.name})"


__all__ = ["WorkflowAlreadyRunningError", "WorkflowManager"]
