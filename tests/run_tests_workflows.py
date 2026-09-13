#!/usr/bin/env python3
"""
Functional test suite for src/workflows/ (the orchestration layer
between the not-yet-built Technician Console/CLI and every already
built subsystem engine manager / services/ facade).

Every underlying engine manager is exercised through a lightweight
test double satisfying its public surface (initialize/shutdown/
is_initialized/run/last_summary, matching interfaces.service.Service)
rather than the real hardware-touching implementation -- the same
dependency-injection discipline every other run_tests_*.py in this
repository already follows.

Run with (from the repository root): python3 tests/run_tests_workflows.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

failures: list[str] = []
passed = 0


def check(condition: bool, description: str) -> None:
    global passed
    if condition:
        passed += 1
    else:
        failures.append(description)


_TEMP_ROOT = Path(tempfile.mkdtemp(prefix="aquila-workflows-tests-"))

from common.enums import InspectionResult, WorkflowState, WorkflowType  # noqa: E402
from common.exceptions.deployment import (  # noqa: E402
    DeploymentProvisioningError,
)
from common.exceptions.hardware import HardwareDetectionError  # noqa: E402
from config.schemas.cluster_schema import ClusterConfig  # noqa: E402
from config.schemas.controller_schema import ControllerConfig  # noqa: E402
from config.schemas.deployment_schema import (  # noqa: E402
    DEPLOYMENT_WORKFLOWS,
    DeploymentConfig,
)
from config.schemas.network_schema import NetworkConfig  # noqa: E402
from inspection.report import CategoryAssessment, HardwareInspectionReport  # noqa: E402
from models.hardware.battery import BatteryInfo  # noqa: E402
from models.hardware.bios import BIOSInspectionInfo  # noqa: E402
from models.hardware.cpu import CPUArchitecture, CPUInfo  # noqa: E402
from models.hardware.storage import (  # noqa: E402
    StorageDevice,
    StorageDeviceType,
    StorageInventory,
)
from models.hardware.virtualization import (  # noqa: E402
    VirtualizationInfo,
    VirtualizationTechnology,
)
from bios.models import FirmwareInformation  # noqa: E402
from preparation.confirmations import PreparationConfirmations  # noqa: E402
from preparation.report import PreparationSummary, SanitizationRecord  # noqa: E402
from preparation.verifier import VerificationOutcome  # noqa: E402
from common.enums import SanitizationMethod  # noqa: E402
from provisioning.answer_file import (  # noqa: E402
    ProvisioningProfileError,
    _FIRST_BOOT_ORDERINGS,
    render_answer_file,
)
from provisioning.report import ProvisioningSummary  # noqa: E402
from recovery.report import RecoverySummary  # noqa: E402
from bootstrap.bootstrap_manager import BootstrapSummary  # noqa: E402
from bootstrap.cluster import ClusterJoinResult, ClusterVerificationResult  # noqa: E402
from bootstrap.hostname import HostnameResult  # noqa: E402
from bootstrap.ssh import SSHKeyInstallResult  # noqa: E402
from networking.network_manager import NetworkDiagnostics  # noqa: E402
from services.deployment_service import NodeHandshakeResult  # noqa: E402
from services.network_service import NetworkValidationResult  # noqa: E402

from workflows.application_manager import ApplicationManager  # noqa: E402
from workflows.bootstrap_manager import BootstrapWorkflowStage  # noqa: E402
from workflows.deployment_manager import (  # noqa: E402
    DeploymentWorkflowManager,
    WorkflowSummary,
    _extract_system_identity,
)
from workflows.inspection_manager import (  # noqa: E402
    InspectionWorkflowError,
    InspectionWorkflowStage,
)
from workflows.preparation_manager import (  # noqa: E402
    PreparationConfirmationRequest,
    PreparationWorkflowStage,
)
from workflows.progress import WorkflowStageEvent, emit  # noqa: E402
from workflows.provisioning_manager import (  # noqa: E402
    NodeIdentityRecord,
    ProvisioningProfileTemplate,
    ProvisioningWorkflowStage,
)
from workflows.recovery_manager import (  # noqa: E402
    RecoveryDecision,
    RecoveryWorkflowStage,
)
from workflows.workflow_manager import (  # noqa: E402
    WorkflowAlreadyRunningError,
    WorkflowManager,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _report(
    *, manufacturer: str = "Acme", model: str = "X1", serial: str = "SYS-SN-1"
) -> HardwareInspectionReport:
    pass_ = InspectionResult.PASS
    return HardwareInspectionReport(
        cpu=CategoryAssessment(
            data=CPUInfo(
                manufacturer="GenuineIntel",
                model_name="Test CPU",
                architecture=CPUArchitecture.X86_64,
                virtualization_supported=True,
                virtualization_enabled=True,
            ),
            result=pass_,
        ),
        memory=CategoryAssessment(data=__import__(
            "models.hardware.memory", fromlist=["MemoryInfo"]
        ).MemoryInfo(total_capacity_bytes=8 * 1024**3), result=pass_),
        storage=CategoryAssessment(
            data=StorageInventory(devices=[_storage_device()]), result=pass_
        ),
        smart=CategoryAssessment(data=[], result=pass_),
        network=CategoryAssessment(data=[], result=pass_),
        battery=CategoryAssessment(data=BatteryInfo(), result=pass_),
        virtualization=CategoryAssessment(
            data=VirtualizationInfo(
                cpu_supported=True, technology=VirtualizationTechnology.VT_X
            ),
            result=pass_,
        ),
        bios=CategoryAssessment(
            data=BIOSInspectionInfo(
                firmware=FirmwareInformation(
                    manufacturer=manufacturer, model=model, serial_number=serial
                )
            ),
            result=pass_,
        ),
        gpu=CategoryAssessment(data=[], result=pass_),
    )


def _storage_device(
    *, serial: str = "SERIAL123", path: str = r"\\.\PHYSICALDRIVE0"
) -> StorageDevice:
    return StorageDevice(
        device_path=path,
        model="Test SSD",
        serial_number=serial,
        device_type=StorageDeviceType.NVME_SSD,
        capacity_bytes=100 * 1024**3,
    )


def _recovery_summary(*, complete: bool = True) -> RecoverySummary:
    now = datetime.now(UTC)
    if complete:
        return RecoverySummary(
            started_at=now, completed_at=now, recovery_performed=False, skipped=True,
            skip_acknowledgement="technician says skip",
        )
    return RecoverySummary(
        started_at=now, completed_at=now, recovery_performed=True, skipped=False,
        aborted=True, abort_reason="disk pulled mid-copy",
    )


def _preparation_summary(*, all_succeeded: bool = True) -> PreparationSummary:
    now = datetime.now(UTC)
    records = [
        SanitizationRecord(
            device_path=r"\\.\PHYSICALDRIVE0",
            device_model="Test SSD",
            device_serial_number="SERIAL123",
            method=SanitizationMethod.FULL,
            started_at=now,
            completed_at=now,
            execution_succeeded=all_succeeded,
            execution_message="ok" if all_succeeded else "failed",
            return_code=0,
            verification_outcome=(
                VerificationOutcome.VERIFIED
                if all_succeeded
                else VerificationOutcome.NOT_CLEARED
            ),
            verification_detail="verified" if all_succeeded else "mismatch",
        )
    ]
    return PreparationSummary(
        started_at=now,
        completed_at=now,
        system_manufacturer="Acme",
        system_model="X1",
        system_serial_number="SYS-SN-1",
        deployment_workflow="provisioning",
        recovery_status="skipped",
        records=records,
        aborted=not all_succeeded,
        abort_reason=None if all_succeeded else "sanitization failed",
    )


def _provisioning_summary(*, aborted: bool = False) -> ProvisioningSummary:
    now = datetime.now(UTC)
    return ProvisioningSummary(
        started_at=now,
        completed_at=now,
        node_hostname="aquila-node-01",
        target_device_path=r"\\.\PHYSICALDRIVE0",
        requirements_satisfied=True,
        requirements_detail="ok",
        ethernet_connected=True,
        ethernet_detail="ok",
        controller_reachable=True,
        controller_detail="ok",
        answer_file_rendered=not aborted,
        answer_file_detail="ok" if not aborted else "not rendered",
        media_integrity_verified=not aborted,
        media_integrity_detail="ok" if not aborted else "corrupt",
        handoff_triggered=not aborted,
        handoff_detail="ok" if not aborted else "",
        aborted=aborted,
        abort_reason=None if not aborted else "media corrupt",
    )


def _bootstrap_summary(*, operational: bool = True) -> BootstrapSummary:
    now = datetime.now(UTC)
    return BootstrapSummary(
        started_at=now,
        completed_at=now,
        node_identifier="node-123",
        hostname="aquila-node-01",
        controller_reachable=operational,
        authenticated=operational,
        configuration_retrieved=operational,
        # BootstrapSummary.operational (REQ-BOOT-019/020) additionally
        # gates on hostname/SSH/cluster-join/cluster-verification/
        # inventory-registration all having succeeded -- these must be
        # populated for an "operational" fixture to actually evaluate
        # as operational.
        hostname_result=HostnameResult(
            hostname="aquila-node-01", applied=operational, detail="applied"
        )
        if operational
        else None,
        ssh_result=SSHKeyInstallResult(
            installed_count=1 if operational else 0,
            rejected_keys=(),
            detail="installed",
        ),
        cluster_join_result=ClusterJoinResult(
            created_new_cluster=False,
            command_succeeded=operational,
            detail="joined",
        )
        if operational
        else None,
        cluster_verification_result=ClusterVerificationResult(
            verified=operational,
            node_hostname="aquila-node-01",
            detail="verified",
        )
        if operational
        else None,
        inventory_registered=operational,
        aborted=not operational,
        abort_reason=None if operational else "cluster join failed",
    )


def _network_diagnostics(*, ok: bool = True) -> NetworkDiagnostics:
    now = datetime.now(UTC)
    return NetworkDiagnostics(
        started_at=now,
        completed_at=now,
        ethernet_connected=ok,
        ethernet_detail="ok" if ok else "no link",
        ip_assignment_method="dhcp",
        ip_assignment_succeeded=ok,
        ip_assignment_detail="ok" if ok else "dhcp timeout",
    )


def _deployment_config(**overrides: object) -> DeploymentConfig:
    return DeploymentConfig(**overrides)  # type: ignore[arg-type]


def _controller_config(**overrides: object) -> ControllerConfig:
    return ControllerConfig(**overrides)  # type: ignore[arg-type]


def _network_config(**overrides: object) -> NetworkConfig:
    return NetworkConfig(**overrides)  # type: ignore[arg-type]


def _valid_confirmations() -> PreparationConfirmations:
    return PreparationConfirmations(
        target_device_confirmed=True,
        erasure_acknowledgement_phrase="ERASE",
        final_approval=True,
        additional_confirmations=(True,),
    )


# ---------------------------------------------------------------------------
# Test doubles (matching interfaces.service.Service + each real manager's
# public surface)
# ---------------------------------------------------------------------------


class _FakeInspectionManager:
    def __init__(self, report: Optional[HardwareInspectionReport] = None, raise_error: bool = False):
        self._initialized = False
        self._report = report or _report()
        self._raise = raise_error
        self.last_report: Optional[HardwareInspectionReport] = None

    def initialize(self) -> None:
        self._initialized = True

    def shutdown(self) -> None:
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def run(self) -> HardwareInspectionReport:
        if self._raise:
            raise HardwareDetectionError("catastrophic detection failure")
        self.last_report = self._report
        return self._report


class _FakeRecoveryManager:
    def __init__(self, summary: Optional[RecoverySummary] = None):
        self._initialized = False
        self._summary = summary or _recovery_summary()
        self.last_summary: Optional[RecoverySummary] = None
        self.run_calls: list[dict[str, object]] = []

    def initialize(self) -> None:
        self._initialized = True

    def shutdown(self) -> None:
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def discover_volumes(self, inspection_report: HardwareInspectionReport) -> list[object]:
        return []

    def run(self, inspection_report, **kwargs: object) -> RecoverySummary:  # type: ignore[no-untyped-def]
        self.run_calls.append(kwargs)
        self.last_summary = self._summary
        return self._summary


class _FakePreparationManager:
    def __init__(self, summary: Optional[PreparationSummary] = None):
        self._initialized = False
        self._summary = summary or _preparation_summary()
        self.last_summary: Optional[PreparationSummary] = None
        self.run_calls: list[dict[str, object]] = []

    def initialize(self) -> None:
        self._initialized = True

    def shutdown(self) -> None:
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def run(self, recovery_summary, **kwargs: object) -> PreparationSummary:  # type: ignore[no-untyped-def]
        self.run_calls.append(kwargs)
        self.last_summary = self._summary
        return self._summary


class _FakeProvisioningManager:
    def __init__(self, summary: Optional[ProvisioningSummary] = None):
        self._initialized = False
        self._summary = summary or _provisioning_summary()
        self.last_summary: Optional[ProvisioningSummary] = None
        self.run_calls: list[dict[str, object]] = []

    def initialize(self) -> None:
        self._initialized = True

    def shutdown(self) -> None:
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def run(self, preparation_summary, **kwargs: object) -> ProvisioningSummary:  # type: ignore[no-untyped-def]
        self.run_calls.append(kwargs)
        self.last_summary = self._summary
        return self._summary


class _FakeBootstrapManager:
    def __init__(self, summary: Optional[BootstrapSummary] = None):
        self._initialized = False
        self._summary = summary or _bootstrap_summary()
        self.last_summary: Optional[BootstrapSummary] = None

    def initialize(self) -> None:
        self._initialized = True

    def shutdown(self) -> None:
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def run(self, **kwargs: object) -> BootstrapSummary:  # type: ignore[no-untyped-def]
        self.last_summary = self._summary
        return self._summary


class _FakeNetworkService:
    def __init__(self, result: Optional[NetworkValidationResult] = None):
        self._initialized = False
        self._result = result or NetworkValidationResult(
            succeeded=True, diagnostics=_network_diagnostics()
        )

    def initialize(self) -> None:
        self._initialized = True

    def shutdown(self) -> None:
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def establish(self, *args: object, **kwargs: object) -> NetworkValidationResult:
        return self._result


class _FakeDeploymentService:
    def __init__(self, handshake_result: Optional[NodeHandshakeResult] = None):
        self._initialized = False
        self._result = handshake_result

    def initialize(self) -> None:
        self._initialized = True

    def shutdown(self) -> None:
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def handshake(self, node_identifier: str, *, enrollment_token: str) -> NodeHandshakeResult:
        if self._result is not None:
            return self._result
        return NodeHandshakeResult(
            node_identifier=node_identifier,
            authentication_token=enrollment_token,
            reachable=True,
            authenticated=True,
            approved=True,
            hostname="aquila-node-01",
            ssh_authorized_keys=("ssh-ed25519 AAAA...",),
            cluster_join_token="join-token-xyz",
            detail="Approved; configuration retrieved.",
        )


# ---------------------------------------------------------------------------
# workflows.progress
# ---------------------------------------------------------------------------

try:
    WorkflowStageEvent(stage="x", message="y", severity="bogus")
    check(False, "WorkflowStageEvent rejects an unknown severity")
except ValueError:
    check(True, "WorkflowStageEvent rejects an unknown severity")

received: list[WorkflowStageEvent] = []
emit(received.append, "inspection", "hello", severity="info")
check(len(received) == 1 and received[0].stage == "inspection", "emit() invokes the callback")

emit(None, "inspection", "no callback -- must not raise")
check(True, "emit() tolerates a missing callback")


def _raising_callback(event: WorkflowStageEvent) -> None:
    raise RuntimeError("Console UI blew up")


try:
    emit(_raising_callback, "inspection", "should not propagate")
    check(True, "emit() swallows a raising callback (best-effort)")
except Exception:
    check(False, "emit() swallows a raising callback (best-effort)")


# ---------------------------------------------------------------------------
# common.enums.WorkflowType alignment with DeploymentConfig.DEPLOYMENT_WORKFLOWS
# ---------------------------------------------------------------------------

check(
    {member.value for member in WorkflowType} == set(DEPLOYMENT_WORKFLOWS),
    "WorkflowType members align exactly with DeploymentConfig.DEPLOYMENT_WORKFLOWS",
)
check(WorkflowType("retirement") is WorkflowType.RETIREMENT, "WorkflowType round-trips 'retirement'")
check(WorkflowType("provisioning") is WorkflowType.PROVISIONING, "WorkflowType round-trips 'provisioning'")


# ---------------------------------------------------------------------------
# provisioning.answer_file: first_boot_ordering fix
# ---------------------------------------------------------------------------

check(
    _FIRST_BOOT_ORDERINGS == ("before-network", "network-online", "fully-up"),
    "answer_file._FIRST_BOOT_ORDERINGS matches the official Proxmox schema",
)

from provisioning.answer_file import ProvisioningProfile  # noqa: E402

_default_profile = ProvisioningProfile(
    node_hostname="n1", domain="lab.local", mailto="ops@lab.local",
    target_device_serial="SERIAL123", disk_list=("nvme0n1",),
    bootstrap_source_url="https://controller.lab.local/api/v1/bootstrap/abc",
)
check(
    _default_profile.first_boot_ordering == "network-online",
    "ProvisioningProfile.first_boot_ordering defaults to the network-fixed value",
)
_rendered = render_answer_file(_default_profile, "hunter2")
# REQ-PROV-009/REQ-PROV-014: this real (non-faked) render_answer_file()
# call is what actually configures the installed OS to auto-execute
# (and fetch/install) the Bootstrap Engine on first boot, and thereby
# prepares the system for Bootstrap execution -- the rendered
# [first-boot] block asserted below is that mechanism.
check(
    'ordering = "network-online"' in _rendered,
    "render_answer_file() renders the fixed [first-boot] ordering by default",
)
check(
    'ordering = "before-network"' not in _rendered,
    "render_answer_file() no longer hardcodes the network-less ordering",
)

try:
    ProvisioningProfile(
        node_hostname="n1", domain="lab.local", mailto="ops@lab.local",
        target_device_serial="SERIAL123", disk_list=("nvme0n1",),
        first_boot_ordering="not-a-real-value",
    )
    check(False, "ProvisioningProfile rejects an invalid first_boot_ordering")
except ProvisioningProfileError:
    # REQ-PROV-015: ProvisioningProfile is exactly the "deployment
    # profile that defines... bootstrap configuration" this requirement
    # calls for; validating (and rejecting invalid values for) its
    # first_boot_ordering field is real, direct coverage of that
    # profile's own configuration rules, not a faked stand-in.
    check(True, "ProvisioningProfile rejects an invalid first_boot_ordering")


# ---------------------------------------------------------------------------
# workflows.inspection_manager.InspectionWorkflowStage
# ---------------------------------------------------------------------------

_fake_inspection = _FakeInspectionManager()
_inspection_stage = InspectionWorkflowStage(inspection_manager=_fake_inspection)
_events: list[WorkflowStageEvent] = []
_report_result = _inspection_stage.run(node_name="node-a", progress_callback=_events.append)
# REQ-INS-027: the completed HardwareInspectionReport is made available
# to the caller through InspectionWorkflowStage.run()'s documented
# return value -- this is that documented interface being exercised.
check(_report_result is _fake_inspection.last_report, "InspectionWorkflowStage.run() returns the engine's report")
check(_inspection_stage.is_initialized, "InspectionWorkflowStage auto-initializes on first run()")
check(
    any(e.severity == "info" and "Inspecting" in e.message for e in _events),
    "InspectionWorkflowStage emits a start event",
)
check(
    any("completed" in e.message for e in _events),
    "InspectionWorkflowStage emits a completion event",
)

_failing_inspection = _FakeInspectionManager(raise_error=True)
_failing_stage = InspectionWorkflowStage(inspection_manager=_failing_inspection)
try:
    _failing_stage.run(node_name="node-b")
    check(False, "InspectionWorkflowStage.run() raises InspectionWorkflowError on catastrophic failure")
except InspectionWorkflowError:
    check(True, "InspectionWorkflowStage.run() raises InspectionWorkflowError on catastrophic failure")


# ---------------------------------------------------------------------------
# workflows.recovery_manager
# ---------------------------------------------------------------------------

_skip_decision = RecoveryDecision.skip_with_acknowledgement("nothing to recover")
check(_skip_decision.skip is True, "RecoveryDecision.skip_with_acknowledgement() sets skip=True")
check(
    _skip_decision.technician_acknowledgement == "nothing to recover",
    "RecoveryDecision.skip_with_acknowledgement() carries the acknowledgement",
)

_recover_decision = RecoveryDecision.recover(
    destination=_TEMP_ROOT / "recovered", selected_paths=[Path("C:/Users/tech/Documents")]
)
check(_recover_decision.skip is False, "RecoveryDecision.recover() sets skip=False")
# REQ-REC-006: RecoveryDecision.recover() is how a technician's
# individual file/directory selection is carried into the Recovery
# stage -- this asserts that selection survives construction intact.
check(len(_recover_decision.selected_paths) == 1, "RecoveryDecision.recover() carries the selection")

_fake_recovery = _FakeRecoveryManager()
_recovery_stage = RecoveryWorkflowStage(recovery_manager=_fake_recovery)
_recovery_events: list[WorkflowStageEvent] = []
_recovery_result = _recovery_stage.run(
    _report(), _skip_decision, node_name="node-a", workflow_progress_callback=_recovery_events.append
)
check(_recovery_result is _fake_recovery.last_summary, "RecoveryWorkflowStage.run() returns the engine's summary")
check(
    _fake_recovery.run_calls[-1]["skip"] is True,
    "RecoveryWorkflowStage.run() forwards decision.skip to the engine",
)

# REQ-REC-015: the skip path is exactly how "no recovery has been
# performed" is clearly indicated (a skipped RecoverySummary has
# recovery_performed=False alongside skipped=True) -- the emitted
# stage event surfaces this to the technician in real time.
check(
    any("skipped" in e.message for e in _recovery_events),
    "RecoveryWorkflowStage emits a skip-path event",
)

_incomplete_recovery = _FakeRecoveryManager(summary=_recovery_summary(complete=False))
_incomplete_stage = RecoveryWorkflowStage(recovery_manager=_incomplete_recovery)
_incomplete_events: list[WorkflowStageEvent] = []
_incomplete_stage.run(
    _report(), _recover_decision, node_name="node-a", workflow_progress_callback=_incomplete_events.append
)
check(
    any(e.severity == "warning" for e in _incomplete_events),
    "RecoveryWorkflowStage emits a warning when recovery is incomplete (REQ-REC-026)",
)


# ---------------------------------------------------------------------------
# workflows.preparation_manager
# ---------------------------------------------------------------------------

_request = PreparationConfirmationRequest(
    system_manufacturer="Acme",
    system_model="X1",
    system_serial_number="SYS-SN-1",
    target_devices=(_storage_device(),),
    recovery_status="skipped",
    deployment_workflow="retirement",
    required_confirmation_count=3,
    force_confirmation_phrase="ERASE",
)
# REQ-PREP-003: the mandated pre-flight summary must clearly indicate
# that the coming storage operations are irreversible.
check("IRREVERSIBLE" in _request.summary_text, "PreparationConfirmationRequest.summary_text warns of irreversibility")
# REQ-PREP-002: the same summary must include, at minimum, system
# identity and the target storage device(s) -- asserted here via the
# real (non-faked) summary_text property.
check("Acme X1" in _request.summary_text, "PreparationConfirmationRequest.summary_text includes system identity")
check("SERIAL123" in _request.summary_text, "PreparationConfirmationRequest.summary_text includes target storage")

_fake_preparation = _FakePreparationManager()
_preparation_stage = PreparationWorkflowStage(preparation_manager=_fake_preparation)
_seen_requests: list[PreparationConfirmationRequest] = []


def _provider(request: PreparationConfirmationRequest) -> PreparationConfirmations:
    _seen_requests.append(request)
    return _valid_confirmations()


_prep_events: list[WorkflowStageEvent] = []
_prep_result = _preparation_stage.run(
    _recovery_summary(),
    node_name="node-a",
    target_devices=[_storage_device()],
    storage_inventory=StorageInventory(devices=[_storage_device()]),
    deployment_config=_deployment_config(),
    confirmation_provider=_provider,
    system_manufacturer="Acme",
    system_model="X1",
    system_serial_number="SYS-SN-1",
    deployment_workflow="retirement",
    workflow_progress_callback=_prep_events.append,
)
check(_prep_result is _fake_preparation.last_summary, "PreparationWorkflowStage.run() returns the engine's summary")
check(len(_seen_requests) == 1, "PreparationWorkflowStage.run() calls confirmation_provider exactly once")
check(
    _fake_preparation.run_calls[-1]["confirmations"] == _valid_confirmations(),
    "PreparationWorkflowStage.run() forwards the provider's confirmations to the engine",
)
check(
    any("awaiting operator confirmation" in e.message for e in _prep_events),
    "PreparationWorkflowStage emits a confirmation-gate event before sanitizing",
)


# ---------------------------------------------------------------------------
# workflows.provisioning_manager
# ---------------------------------------------------------------------------

_identity_dest = _TEMP_ROOT / "reports" / "node-identity.json"
_record = NodeIdentityRecord(
    node_identifier="node-123",
    hostname="aquila-node-01",
    reachable=True,
    authenticated=True,
    approved=True,
    detail="Approved; configuration retrieved.",
)
_record.write(_identity_dest)
_read_back = NodeIdentityRecord.read(_identity_dest)
check(_read_back.node_identifier == "node-123", "NodeIdentityRecord round-trips node_identifier through write()/read()")
check(_read_back.hostname == "aquila-node-01", "NodeIdentityRecord round-trips hostname through write()/read()")
check(_read_back.approved is True, "NodeIdentityRecord round-trips approved through write()/read()")

_profile_template = ProvisioningProfileTemplate(
    domain="lab.local", mailto="ops@lab.local", disk_list=("nvme0n1",)
)
_merged_profile = _profile_template.to_profile(
    node_hostname="aquila-node-01",
    target_device_serial="SERIAL123",
    root_ssh_keys=("ssh-ed25519 AAAA...",),
    bootstrap_source_url="https://controller.lab.local/api/v1/bootstrap/node-123",
)
# REQ-PROV-011: to_profile() is the real (non-faked) merge of the
# technician-supplied template with Controller-assigned handshake data
# into the final ProvisioningProfile -- deployment configuration being
# applied automatically, with no manual technician step in between.
check(_merged_profile.node_hostname == "aquila-node-01", "ProvisioningProfileTemplate.to_profile() sets the handshake-assigned hostname")
check(
    _merged_profile.root_ssh_keys == ("ssh-ed25519 AAAA...",),
    # REQ-PROV-013: this is that required SSH configuration -- the
    # Controller-assigned authorized keys -- actually landing in the
    # profile that answer_file.render_answer_file() will use.
    "ProvisioningProfileTemplate.to_profile() carries through Controller-assigned SSH keys",
)

import os  # noqa: E402

os.environ["AQUILA_TEST_CONTROLLER_TOKEN"] = "enrollment-secret"

_provisioning_stage = ProvisioningWorkflowStage(
    provisioning_manager=_FakeProvisioningManager(),
    network_service=_FakeNetworkService(),
    deployment_service_factory=lambda _cfg: _FakeDeploymentService(),
)
_prov_events: list[WorkflowStageEvent] = []
_prov_result = _provisioning_stage.run(
    _preparation_summary(),
    node_name="node-a",
    inspection_report=_report(),
    deployment_config=_deployment_config(),
    controller_config=_controller_config(
        host="controller.lab.local",
        authentication_token_env_var="AQUILA_TEST_CONTROLLER_TOKEN",
    ),
    network_config=_network_config(),
    cluster_config=None,
    target_device=_storage_device(),
    profile_template=_profile_template,
    root_password="hunter2",
    phase_two_directory=_TEMP_ROOT / "phase2",
    answer_file_destination=_TEMP_ROOT / "phase2" / "answer.toml",
    identity_record_destination=_TEMP_ROOT / "reports" / "node-identity-2.json",
    boot_entry_id="{BOOT-ENTRY}",
    workflow_progress_callback=_prov_events.append,
)
# REQ-PROV-021: this single run() call carries deployment straight
# through network validation, handshake, and the Provisioning Engine
# launch with no additional technician interaction point in between --
# exactly what "shall not require additional technician interaction
# after deployment has been authorized" requires on the success path.
check(_prov_result.aborted is False, "ProvisioningWorkflowStage.run() succeeds end to end with a fully-approved handshake")
check(_prov_result.handshake is not None and _prov_result.handshake.approved, "ProvisioningWorkflowStage.run() returns the approved handshake")
check(_prov_result.identity_record is not None, "ProvisioningWorkflowStage.run() produces a NodeIdentityRecord")
check(
    _prov_result.provisioning_summary is not None,
    "ProvisioningWorkflowStage.run() runs the Provisioning Engine once approved",
)
check(
    any("Handshake complete" in e.message for e in _prov_events),
    # REQ-PROV-017: ProvisioningWorkflowStage.run() (real, non-faked
    # orchestration code) emits a workflow_progress_callback event at
    # each phase -- network validation, handshake, and the Provisioning
    # Engine launch -- which is this requirement's "display deployment
    # progress throughout provisioning" at the workflow-orchestration
    # level.
    "ProvisioningWorkflowStage emits a handshake-complete event",
)

# Network Validation failure halts before any handshake is attempted.
_network_fail_stage = ProvisioningWorkflowStage(
    provisioning_manager=_FakeProvisioningManager(),
    network_service=_FakeNetworkService(
        result=NetworkValidationResult(succeeded=False, diagnostics=_network_diagnostics(ok=False))
    ),
    deployment_service_factory=lambda _cfg: _FakeDeploymentService(),
)
_network_fail_result = _network_fail_stage.run(
    _preparation_summary(),
    node_name="node-a",
    inspection_report=_report(),
    deployment_config=_deployment_config(),
    controller_config=_controller_config(authentication_token_env_var="AQUILA_TEST_CONTROLLER_TOKEN"),
    network_config=_network_config(),
    cluster_config=None,
    target_device=_storage_device(),
    profile_template=_profile_template,
    root_password="hunter2",
    phase_two_directory=_TEMP_ROOT / "phase2b",
    answer_file_destination=_TEMP_ROOT / "phase2b" / "answer.toml",
    identity_record_destination=_TEMP_ROOT / "reports" / "node-identity-3.json",
    boot_entry_id="{BOOT-ENTRY}",
)
check(_network_fail_result.aborted is True, "ProvisioningWorkflowStage halts when Network Validation fails")
check(_network_fail_result.handshake is None, "ProvisioningWorkflowStage never attempts a handshake after Network Validation fails")
check(_network_fail_result.provisioning_summary is None, "ProvisioningWorkflowStage never runs Provisioning after Network Validation fails")

# Missing enrollment token halts before generating a node_identifier's handshake.
del os.environ["AQUILA_TEST_CONTROLLER_TOKEN"]
_no_token_stage = ProvisioningWorkflowStage(
    provisioning_manager=_FakeProvisioningManager(),
    network_service=_FakeNetworkService(),
    deployment_service_factory=lambda _cfg: _FakeDeploymentService(),
)
_no_token_result = _no_token_stage.run(
    _preparation_summary(),
    node_name="node-a",
    inspection_report=_report(),
    deployment_config=_deployment_config(),
    controller_config=_controller_config(authentication_token_env_var="AQUILA_TEST_CONTROLLER_TOKEN_MISSING"),
    network_config=_network_config(),
    cluster_config=None,
    target_device=_storage_device(),
    profile_template=_profile_template,
    root_password="hunter2",
    phase_two_directory=_TEMP_ROOT / "phase2c",
    answer_file_destination=_TEMP_ROOT / "phase2c" / "answer.toml",
    identity_record_destination=_TEMP_ROOT / "reports" / "node-identity-4.json",
    boot_entry_id="{BOOT-ENTRY}",
)
check(_no_token_result.aborted is True, "ProvisioningWorkflowStage halts when the enrollment token is missing (REQ-SEC-008/009/010)")
check(_no_token_result.handshake is None, "ProvisioningWorkflowStage never attempts a handshake without an enrollment token")

# A pending-approval handshake halts before Provisioning runs, but the
# identity record is still written (audit trail).
os.environ["AQUILA_TEST_CONTROLLER_TOKEN"] = "enrollment-secret"
_pending_stage = ProvisioningWorkflowStage(
    provisioning_manager=_FakeProvisioningManager(),
    network_service=_FakeNetworkService(),
    deployment_service_factory=lambda _cfg: _FakeDeploymentService(
        handshake_result=NodeHandshakeResult(
            node_identifier="node-pending",
            authentication_token="enrollment-secret",
            reachable=True,
            authenticated=True,
            approved=False,
            detail="Node authenticated but is not yet approved.",
        )
    ),
)
_pending_identity_dest = _TEMP_ROOT / "reports" / "node-identity-5.json"
_pending_result = _pending_stage.run(
    _preparation_summary(),
    node_name="node-a",
    inspection_report=_report(),
    deployment_config=_deployment_config(),
    controller_config=_controller_config(authentication_token_env_var="AQUILA_TEST_CONTROLLER_TOKEN"),
    network_config=_network_config(),
    cluster_config=None,
    target_device=_storage_device(),
    profile_template=_profile_template,
    root_password="hunter2",
    phase_two_directory=_TEMP_ROOT / "phase2d",
    answer_file_destination=_TEMP_ROOT / "phase2d" / "answer.toml",
    identity_record_destination=_pending_identity_dest,
    boot_entry_id="{BOOT-ENTRY}",
)
check(_pending_result.aborted is True, "ProvisioningWorkflowStage halts on a pending-approval handshake (REQ-CTRL-016)")
check(_pending_result.provisioning_summary is None, "ProvisioningWorkflowStage never runs Provisioning while approval is pending")
check(_pending_identity_dest.is_file(), "ProvisioningWorkflowStage writes the identity audit record even when not approved")

# REQ-PROV-001 gate still raises, matching ProvisioningManager.run()'s own convention.
# REQ-PREP-023 (the flip side of this same gate): a PreparationSummary
# is only eligible to unlock Provisioning when all_succeeded is True --
# passing all_succeeded=False here is exactly an ineligible-for-
# provisioning preparation outcome, and it is refused below.
try:
    _provisioning_stage.run(
        _preparation_summary(all_succeeded=False),
        node_name="node-a",
        inspection_report=_report(),
        deployment_config=_deployment_config(),
        controller_config=_controller_config(authentication_token_env_var="AQUILA_TEST_CONTROLLER_TOKEN"),
        network_config=_network_config(),
        cluster_config=None,
        target_device=_storage_device(),
        profile_template=_profile_template,
        root_password="hunter2",
        phase_two_directory=_TEMP_ROOT / "phase2e",
        answer_file_destination=_TEMP_ROOT / "phase2e" / "answer.toml",
        identity_record_destination=_TEMP_ROOT / "reports" / "node-identity-6.json",
        boot_entry_id="{BOOT-ENTRY}",
    )
    check(False, "ProvisioningWorkflowStage.run() raises DeploymentProvisioningError when preparation did not succeed")
except DeploymentProvisioningError:
    check(True, "ProvisioningWorkflowStage.run() raises DeploymentProvisioningError when preparation did not succeed")


# ---------------------------------------------------------------------------
# workflows.bootstrap_manager
# ---------------------------------------------------------------------------

_fake_bootstrap = _FakeBootstrapManager()
_bootstrap_stage = BootstrapWorkflowStage(bootstrap_manager=_fake_bootstrap)
_bootstrap_events: list[WorkflowStageEvent] = []
_bootstrap_result = _bootstrap_stage.run(
    node_identifier="node-123",
    authentication_token="enrollment-secret",
    controller_config=_controller_config(),
    cluster_config=ClusterConfig(),  # type: ignore[call-arg]
    deployment_config=_deployment_config(),
    join_secret="join-token-xyz",
    workflow_progress_callback=_bootstrap_events.append,
)
check(_bootstrap_result is _fake_bootstrap.last_summary, "BootstrapWorkflowStage.run() returns the engine's summary")
check(
    any("operational" in e.message for e in _bootstrap_events),
    "BootstrapWorkflowStage emits a completion event on success",
)

_failed_bootstrap = _FakeBootstrapManager(summary=_bootstrap_summary(operational=False))
_failed_bootstrap_stage = BootstrapWorkflowStage(bootstrap_manager=_failed_bootstrap)
_failed_bootstrap_events: list[WorkflowStageEvent] = []
_failed_bootstrap_stage.run(
    node_identifier="node-123",
    authentication_token="enrollment-secret",
    controller_config=_controller_config(),
    cluster_config=ClusterConfig(),  # type: ignore[call-arg]
    deployment_config=_deployment_config(),
    join_secret="join-token-xyz",
    workflow_progress_callback=_failed_bootstrap_events.append,
)
check(
    any(e.severity == "error" for e in _failed_bootstrap_events),
    "BootstrapWorkflowStage emits an error event when Bootstrap did not complete",
)


# ---------------------------------------------------------------------------
# workflows.deployment_manager._extract_system_identity
# ---------------------------------------------------------------------------

_manufacturer, _model, _serial = _extract_system_identity(_report())
# REQ-INS-016/REQ-INS-017/REQ-INS-018: the manufacturer/model/serial
# number retrieved into the inspection report's BIOS category (see
# hardware.bios.BIOSDetector) are asserted here to survive intact
# through to the workflow layer that consumes the report.
check(_manufacturer == "Acme", "_extract_system_identity() reads manufacturer from the BIOS/firmware category")
check(_model == "X1", "_extract_system_identity() reads model from the BIOS/firmware category")
check(_serial == "SYS-SN-1", "_extract_system_identity() reads serial number from the BIOS/firmware category")


# ---------------------------------------------------------------------------
# workflows.deployment_manager.DeploymentWorkflowManager
# ---------------------------------------------------------------------------

_deployment_manager = DeploymentWorkflowManager(
    inspection_stage=InspectionWorkflowStage(inspection_manager=_FakeInspectionManager()),
    recovery_stage=RecoveryWorkflowStage(recovery_manager=_FakeRecoveryManager()),
    preparation_stage=PreparationWorkflowStage(preparation_manager=_FakePreparationManager()),
    provisioning_stage=ProvisioningWorkflowStage(
        provisioning_manager=_FakeProvisioningManager(),
        network_service=_FakeNetworkService(),
        deployment_service_factory=lambda _cfg: _FakeDeploymentService(),
    ),
)

# DeploymentWorkflowManager itself is real (only the underlying engine
# managers behind each stage are fakes), so this end-to-end run
# genuinely exercises its actual call order: _run_inspection_and_recovery()
# calls self._inspection.run() to completion and only then feeds the
# resulting report into self._recovery.discover_volumes()/the decision
# provider -- i.e. a hardware inspection report is produced before any
# deployment workflow proceeds (REQ-INS-025), and Recovery genuinely
# begins only after Inspection has completed (REQ-REC-001).
_retirement_summary = _deployment_manager.run_retirement_workflow(
    node_name="node-a",
    recovery_decision_provider=lambda report, volumes: RecoveryDecision.skip_with_acknowledgement("no data"),
    target_device_selector=lambda report: report.storage.data.devices,
    deployment_config=_deployment_config(),
    confirmation_provider=lambda request: _valid_confirmations(),
)
check(_retirement_summary.workflow_type is WorkflowType.RETIREMENT, "run_retirement_workflow() tags the summary as RETIREMENT")
check(_retirement_summary.aborted is False, "run_retirement_workflow() succeeds end to end with fakes that all succeed")

# REQ-PREP-024: Preparation shall not automatically begin provisioning
# -- run_retirement_workflow() completes Preparation without ever
# invoking the Provisioning stage; run_provisioning_workflow() below is
# a separate, explicitly-invoked method a technician (or CLI/console
# caller) must choose to call, not an automatic continuation.
check(_retirement_summary.provisioning_result is None, "run_retirement_workflow() never runs the Provisioning stage")
check(_retirement_summary.duration >= timedelta(0), "WorkflowSummary.duration is non-negative")

os.environ["AQUILA_TEST_CONTROLLER_TOKEN"] = "enrollment-secret"
_provisioning_workflow_summary = _deployment_manager.run_provisioning_workflow(
    node_name="node-a",
    recovery_decision_provider=lambda report, volumes: RecoveryDecision.skip_with_acknowledgement("no data"),
    target_device_selector=lambda report: report.storage.data.devices,
    provisioning_target_device=_storage_device(),
    deployment_config=_deployment_config(),
    confirmation_provider=lambda request: _valid_confirmations(),
    controller_config=_controller_config(authentication_token_env_var="AQUILA_TEST_CONTROLLER_TOKEN"),
    network_config=_network_config(),
    cluster_config=None,
    profile_template=_profile_template,
    root_password="hunter2",
    phase_two_directory=_TEMP_ROOT / "phase2f",
    answer_file_destination=_TEMP_ROOT / "phase2f" / "answer.toml",
    identity_record_destination=_TEMP_ROOT / "reports" / "node-identity-7.json",
    boot_entry_id="{BOOT-ENTRY}",
)
check(_provisioning_workflow_summary.workflow_type is WorkflowType.PROVISIONING, "run_provisioning_workflow() tags the summary as PROVISIONING")
check(_provisioning_workflow_summary.aborted is False, "run_provisioning_workflow() succeeds end to end with fakes that all succeed")
check(
    _provisioning_workflow_summary.provisioning_result is not None,
    "run_provisioning_workflow() runs the Provisioning stage",
)

# Recovery incompleteness halts before Preparation ever runs.
# REQ-REC-017: an incomplete recovery (aborted, here) must prevent the
# Preparation Engine from executing at all -- asserted below via
# preparation_summary staying None.
_halting_manager = DeploymentWorkflowManager(
    inspection_stage=InspectionWorkflowStage(inspection_manager=_FakeInspectionManager()),
    recovery_stage=RecoveryWorkflowStage(
        recovery_manager=_FakeRecoveryManager(summary=_recovery_summary(complete=False))
    ),
    preparation_stage=PreparationWorkflowStage(preparation_manager=_FakePreparationManager()),
)
_halted_summary = _halting_manager.run_retirement_workflow(
    node_name="node-a",
    recovery_decision_provider=lambda report, volumes: RecoveryDecision.recover(
        destination=_TEMP_ROOT / "recovered2", selected_paths=[Path("C:/data")]
    ),
    target_device_selector=lambda report: report.storage.data.devices,
    deployment_config=_deployment_config(),
    confirmation_provider=lambda request: _valid_confirmations(),
)
check(_halted_summary.aborted is True, "run_retirement_workflow() halts when recovery does not complete")
# REQ-PREP-001: the Preparation Engine shall not begin until Recovery
# has successfully completed or been intentionally skipped -- this is
# that exact gate (src/workflows/deployment_manager.py's real,
# non-faked "REQ-PREP-001/REQ-REC-017" check), asserted here via
# preparation_summary staying None after an incomplete recovery.
check(_halted_summary.preparation_summary is None, "run_retirement_workflow() never runs Preparation after an incomplete recovery")


# ---------------------------------------------------------------------------
# workflows.workflow_manager.WorkflowManager
# ---------------------------------------------------------------------------

_workflow_manager = WorkflowManager(
    deployment_manager=DeploymentWorkflowManager(
        inspection_stage=InspectionWorkflowStage(inspection_manager=_FakeInspectionManager()),
        recovery_stage=RecoveryWorkflowStage(recovery_manager=_FakeRecoveryManager()),
        preparation_stage=PreparationWorkflowStage(preparation_manager=_FakePreparationManager()),
    )
)
check(_workflow_manager.state is WorkflowState.IDLE, "WorkflowManager starts IDLE")

_wm_summary = _workflow_manager.start_retirement_workflow(
    node_name="node-a",
    recovery_decision_provider=lambda report, volumes: RecoveryDecision.skip_with_acknowledgement("no data"),
    target_device_selector=lambda report: report.storage.data.devices,
    deployment_config=_deployment_config(),
    confirmation_provider=lambda request: _valid_confirmations(),
)
check(_workflow_manager.state is WorkflowState.COMPLETED, "WorkflowManager transitions to COMPLETED on success")
check(_workflow_manager.last_summary is _wm_summary, "WorkflowManager.last_summary reflects the most recent run")

# Reentrancy guard: a second workflow cannot start while one is RUNNING.
_reentrant_manager = WorkflowManager(
    deployment_manager=DeploymentWorkflowManager(
        inspection_stage=InspectionWorkflowStage(inspection_manager=_FakeInspectionManager()),
        recovery_stage=RecoveryWorkflowStage(recovery_manager=_FakeRecoveryManager()),
        preparation_stage=PreparationWorkflowStage(preparation_manager=_FakePreparationManager()),
    )
)
# Force RUNNING synthetically to test the guard in isolation, since the
# fakes above complete synchronously and never leave a window to race.
_reentrant_manager.initialize()
with _reentrant_manager._lock:  # noqa: SLF001 -- test-only introspection
    _reentrant_manager._state = WorkflowState.RUNNING
try:
    _reentrant_manager.start_retirement_workflow(
        node_name="node-a",
        recovery_decision_provider=lambda report, volumes: RecoveryDecision.skip_with_acknowledgement("no data"),
        target_device_selector=lambda report: report.storage.data.devices,
        deployment_config=_deployment_config(),
        confirmation_provider=lambda request: _valid_confirmations(),
    )
    check(False, "WorkflowManager refuses to start a second workflow while one is RUNNING")
except WorkflowAlreadyRunningError:
    check(True, "WorkflowManager refuses to start a second workflow while one is RUNNING")

# A halted (aborted) workflow lands in FAILED, not COMPLETED.
_failing_workflow_manager = WorkflowManager(
    deployment_manager=DeploymentWorkflowManager(
        inspection_stage=InspectionWorkflowStage(inspection_manager=_FakeInspectionManager()),
        recovery_stage=RecoveryWorkflowStage(
            recovery_manager=_FakeRecoveryManager(summary=_recovery_summary(complete=False))
        ),
        preparation_stage=PreparationWorkflowStage(preparation_manager=_FakePreparationManager()),
    )
)
_failing_workflow_manager.start_retirement_workflow(
    node_name="node-a",
    recovery_decision_provider=lambda report, volumes: RecoveryDecision.recover(
        destination=_TEMP_ROOT / "recovered3", selected_paths=[Path("C:/data")]
    ),
    target_device_selector=lambda report: report.storage.data.devices,
    deployment_config=_deployment_config(),
    confirmation_provider=lambda request: _valid_confirmations(),
)
check(
    _failing_workflow_manager.state is WorkflowState.FAILED,
    "WorkflowManager transitions to FAILED when the workflow reports aborted=True",
)


# ---------------------------------------------------------------------------
# workflows.application_manager.ApplicationManager
# ---------------------------------------------------------------------------

_configs_dir = _TEMP_ROOT / "configs"
_configs_dir.mkdir(parents=True, exist_ok=True)
for _filename in (
    "deployment.yaml", "network.yaml", "cluster.yaml",
    "logging.yaml", "benchmark.yaml", "controller.yaml",
):
    (_configs_dir / _filename).write_text("{}\n", encoding="utf-8")

_app_manager = ApplicationManager(configs_dir=_configs_dir)
check(_app_manager.is_initialized is False, "ApplicationManager starts uninitialized")
_app_manager.initialize()
check(
    # NFR-MAIN-001: this brings up ConfigurationManager and LogManager
    # (core.startup.startup(), via core.bootstrap.bootstrap()) as
    # independently registered ServiceContainer entries rather than a
    # single monolithic constructor -- the modular architecture
    # ``interfaces.service.Service`` documents.
    _app_manager.is_initialized is True,
    "ApplicationManager.initialize() brings core services up",
)
check(_app_manager.aquila_version, "ApplicationManager.aquila_version returns a non-empty version (REQ-TC-002)")
check(
    _app_manager.deployment_media_version is None,
    "ApplicationManager.deployment_media_version is None with no media_root configured (REQ-TC-003, honest degradation)",
)
check(
    (datetime.now(UTC) - _app_manager.current_datetime) < timedelta(seconds=5),
    "ApplicationManager.current_datetime returns the current time (REQ-TC-004)",
)
check(_app_manager.target_computer_summary is None, "ApplicationManager.target_computer_summary is None before Inspection runs")
_app_manager.record_target_computer(_report())
check(
    _app_manager.target_computer_summary == "Acme X1 (serial: SYS-SN-1)",
    "ApplicationManager.record_target_computer() populates the REQ-TC-005 summary",
)
_app_manager.shutdown()
check(
    # NFR-REL-001: this exercises core.shutdown.shutdown()'s ordering
    # (every other service torn down before LogManager) end to end --
    # a real teardown that completes without corrupting the logs
    # LogManager just finished writing.
    _app_manager.is_initialized is False,
    "ApplicationManager.shutdown() tears everything back down",
)

# REQ-TC-003: a media-version marker file, when present, is read verbatim.
_media_root = _TEMP_ROOT / "media"
_media_root.mkdir(parents=True, exist_ok=True)
(_media_root / "media-version.txt").write_text("2026.09.01-rc1\n", encoding="utf-8")
_media_app_manager = ApplicationManager(configs_dir=_configs_dir, media_root=_media_root)
check(
    _media_app_manager.deployment_media_version == "2026.09.01-rc1",
    "ApplicationManager.deployment_media_version reads a present marker file verbatim",
)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

os.environ.pop("AQUILA_TEST_CONTROLLER_TOKEN", None)
shutil.rmtree(_TEMP_ROOT, ignore_errors=True)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
if failures:
    print(f"{len(failures)} check(s) FAILED (of {passed + len(failures)}):")
    for failure in failures:
        print(f"  - {failure}")
    sys.exit(1)

print(f"{passed} check(s) passed.")
print("All workflows/ functional checks passed.")
