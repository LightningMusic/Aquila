"""
Project Aquila
=============

Workflows

The orchestration layer between the not-yet-built
``technician_console/``/``cli/`` front ends and every already-built
subsystem engine manager (``inspection/``, ``recovery/``,
``preparation/``, ``provisioning/``, ``bootstrap/``) plus the
Console/CLI-facing service layer (``services/``). Composes those into
SRS Appendix B's two deployment workflows -- Device Retirement
(Workflow A) and Aquila Node Provisioning (Workflow B) -- and REQ-TC-001
through REQ-TC-013's Technician Console behaviors, without either front
end needing to depend on engine internals directly (GP-004: one
clearly defined responsibility per module).

Layout
-------
* ``application_manager`` -- REQ-TC-001 through -005's bring-up and
  status-display layer.
* ``inspection_manager``, ``recovery_manager``, ``preparation_manager``,
  ``provisioning_manager``, ``bootstrap_manager`` -- one adapter per
  SRS Appendix B stage, each wrapping the correspondingly-named engine
  manager.
* ``deployment_manager`` -- sequences a full workflow run (Inspection
  through Preparation for Workflow A; through Provisioning for
  Workflow B) from those per-stage adapters.
* ``workflow_manager`` -- REQ-TC-006/007's top-level entry point
  (``start_retirement_workflow()``/``start_provisioning_workflow()``),
  the single object a Technician Console or CLI actually holds.
* ``progress`` -- the shared ``WorkflowStageEvent``/
  ``WorkflowProgressCallback`` type every stage adapter reports
  through (REQ-TC-009/010/011).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from .application_manager import ApplicationManager
from .bootstrap_manager import BootstrapWorkflowStage
from .deployment_manager import (
    DeploymentWorkflowManager,
    RecoveryDecisionProvider,
    TargetDeviceSelector,
    WorkflowSummary,
)
from .inspection_manager import InspectionWorkflowError, InspectionWorkflowStage
from .preparation_manager import (
    PreparationConfirmationProvider,
    PreparationConfirmationRequest,
    PreparationWorkflowStage,
)
from .progress import WorkflowProgressCallback, WorkflowStageEvent
from .provisioning_manager import (
    NodeIdentityRecord,
    ProvisioningProfileTemplate,
    ProvisioningWorkflowResult,
    ProvisioningWorkflowStage,
)
from .recovery_manager import RecoveryDecision, RecoveryWorkflowStage
from .workflow_manager import WorkflowAlreadyRunningError, WorkflowManager

__all__ = [
    "ApplicationManager",
    "BootstrapWorkflowStage",
    "DeploymentWorkflowManager",
    "InspectionWorkflowError",
    "InspectionWorkflowStage",
    "NodeIdentityRecord",
    "PreparationConfirmationProvider",
    "PreparationConfirmationRequest",
    "PreparationWorkflowStage",
    "ProvisioningProfileTemplate",
    "ProvisioningWorkflowResult",
    "ProvisioningWorkflowStage",
    "RecoveryDecision",
    "RecoveryDecisionProvider",
    "RecoveryWorkflowStage",
    "TargetDeviceSelector",
    "WorkflowAlreadyRunningError",
    "WorkflowManager",
    "WorkflowProgressCallback",
    "WorkflowStageEvent",
    "WorkflowSummary",
]
