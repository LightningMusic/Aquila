"""
Project Aquila
=============

Workflow: Provisioning Stage

Thin orchestration-layer adapter around
``provisioning.provisioning_manager.ProvisioningManager`` (SRS Section
10.6, REQ-PROV-001 through REQ-PROV-021) for SRS Appendix B, Workflow
B (Aquila Node Provisioning) -- the stage that closes the
node-identity gap flagged since ``bootstrap/`` was built and left
explicitly unresolved by ``services.deployment_service``'s own
docstring: "persisting [the node identifier] across the Phase
One/Phase Two boundary ... is workflow-level orchestration, wired up
in ``workflows.provisioning_manager`` -- this module only produces the
value and performs the handshake with it." This is that module.

What this adapter adds beyond a pass-through
-------------------------------------------------
``ProvisioningManager.run()`` only ever performs a bare ethernet/
controller-reachability *check* -- it never runs ``services
.network_service.NetworkService``'s fuller REQ-NET validation (with a
recovery attempt), and it never performs
``services.deployment_service.DeploymentService``'s Controller
handshake at all (see that module's own "What it does NOT do" note).
This adapter performs both, in order, before ``ProvisioningManager
.run()`` is ever called:

1. Network Validation (REQ-NET-001 through -010, one recovery attempt)
   via ``NetworkService.establish()``.
2. Node identity generation (:func:`services.deployment_service
   .generate_node_identifier`) and the Controller handshake
   (``DeploymentService.handshake()``) -- REQ-BOOT-002/003/004,
   performed early, and REQ-CTRL-016's approval gate, surfaced as a
   halted (not crashed) workflow outcome exactly like every other
   REQ-TC-012 confirmation/approval gate in this package.

Only once both succeed does this adapter build the final
``ProvisioningProfile`` (merging the technician-supplied
:class:`ProvisioningProfileTemplate` with the Controller-assigned
hostname/SSH keys from the handshake) and call ``ProvisioningManager
.run()`` -- which still performs its own REQ-PROV-002/004 reachability
checks immediately before the irreversible reboot, as one more
defense-in-depth pass, not a redundant one: connectivity can change in
the interval between this stage's own checks and the actual handoff.

The still-open gap this stage does not fabricate
------------------------------------------------------
Everything ``bootstrap.bootstrap_manager.BootstrapManager.run()``
needs (``node_identifier``, ``authentication_token``, ``join_secret``)
is now genuinely produced and validated here -- but Phase Two's
``[first-boot]`` hook (``provisioning.answer_file``) only ever *fetches
a URL*; nothing survives the reboot from Phase One's own boot media in
the general case (see :class:`NodeIdentityRecord`'s docstring for why).
This stage therefore points ``ProvisioningProfile.bootstrap_source_url``
at what a per-node Deployment Controller endpoint *would* look like,
following this project's existing ``/api/v1/...`` REST convention
(``{api_base_path}/bootstrap/{node_identifier}``), but
``deployment_controller/`` does not yet implement that route --
serving a script that embeds ``authentication_token``/``join_secret``
for a fetching, not-yet-authenticated Proxmox first-boot process is
new server-side design (which secrets a per-node script may safely
embed, how the Controller looks them up, how the response is signed)
this session's scope does not cover. Flagged here rather than
fabricated, matching ``provisioning.boot_handoff``'s own precedent of
consuming a not-yet-built dependency's well-defined contract instead
of guessing its internals (that module: the Build System's BCD boot
entry; this one: the Controller's per-node bootstrap-script route).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional

from common.constants.deployment import DEFAULT_FILESYSTEM
from common.constants.logging import WORKFLOW_LOGGER
from common.exceptions.deployment import DeploymentProvisioningError
from config.manager import ConfigurationManager
from config.schemas.cluster_schema import ClusterConfig
from config.schemas.controller_schema import ControllerConfig
from config.schemas.deployment_schema import DeploymentConfig
from config.schemas.network_schema import NetworkConfig
from inspection.report import HardwareInspectionReport
from models.hardware.storage import StorageDevice
from preparation.report import PreparationSummary
from provisioning.answer_file import ProvisioningProfile
from provisioning.boot_handoff import DEFAULT_MANIFEST_FILENAME
from provisioning.provisioning_manager import ProvisioningManager
from provisioning.report import ProvisioningSummary
from services.deployment_service import (
    DeploymentService,
    NodeHandshakeResult,
    generate_node_identifier,
)
from services.network_service import NetworkService, NetworkValidationResult

from .progress import WorkflowProgressCallback, emit

if TYPE_CHECKING:
    from common.events.bus import EventBus

logger = logging.getLogger(WORKFLOW_LOGGER)

STAGE_NAME = "provisioning"

#: Constructs a ``DeploymentService`` from a ``ControllerConfig``.
#: Injected so tests never open a real socket -- mirrors every other
#: ``*ServiceFactory``/``ClientFactory`` in ``services/``.
DeploymentServiceFactory = Callable[[ControllerConfig], DeploymentService]


def _default_deployment_service_factory(
    controller_config: ControllerConfig,
) -> DeploymentService:
    return DeploymentService(controller_config)


@dataclass(slots=True, frozen=True)
class ProvisioningProfileTemplate:
    """
    Every node-specific ``ProvisioningProfile`` field the technician
    supplies directly -- everything else (``node_hostname``,
    ``root_ssh_keys``, ``target_device_serial``,
    ``bootstrap_source_url``) is filled in by this stage from the
    Controller handshake result and ``target_device``, once both are
    available (see the module docstring).
    """

    domain: str
    mailto: str

    disk_list: tuple[str, ...] = ()
    disk_filter: Optional[Mapping[str, tuple[str, ...]]] = None
    disk_filter_match: str = "any"
    filesystem: str = DEFAULT_FILESYSTEM

    keyboard: str = "en-us"
    country: str = "us"
    timezone: str = "UTC"

    root_password_env_var: str = "AQUILA_NODE_ROOT_PASSWORD"
    root_password_is_hashed: bool = False

    reboot_on_error: bool = False
    reboot_mode: str = "reboot"
    subscription_key: Optional[str] = None

    ip_assignment_method: str = "dhcp"
    static_cidr: Optional[str] = None
    static_gateway: Optional[str] = None
    static_dns_servers: tuple[str, ...] = ()

    first_boot_ordering: str = "network-online"
    bootstrap_cert_fingerprint: Optional[str] = None

    def to_profile(
        self,
        *,
        node_hostname: str,
        target_device_serial: str,
        root_ssh_keys: tuple[str, ...],
        bootstrap_source_url: str,
    ) -> ProvisioningProfile:
        """
        Merge in the fields only known once the Controller handshake
        and target-device selection have completed.
        """

        return ProvisioningProfile(
            node_hostname=node_hostname,
            domain=self.domain,
            mailto=self.mailto,
            target_device_serial=target_device_serial,
            disk_list=self.disk_list,
            disk_filter=self.disk_filter,
            disk_filter_match=self.disk_filter_match,
            filesystem=self.filesystem,
            keyboard=self.keyboard,
            country=self.country,
            timezone=self.timezone,
            root_password_env_var=self.root_password_env_var,
            root_password_is_hashed=self.root_password_is_hashed,
            root_ssh_keys=root_ssh_keys,
            reboot_on_error=self.reboot_on_error,
            reboot_mode=self.reboot_mode,
            subscription_key=self.subscription_key,
            ip_assignment_method=self.ip_assignment_method,
            static_cidr=self.static_cidr,
            static_gateway=self.static_gateway,
            static_dns_servers=self.static_dns_servers,
            bootstrap_source_url=bootstrap_source_url,
            bootstrap_cert_fingerprint=self.bootstrap_cert_fingerprint,
            first_boot_ordering=self.first_boot_ordering,
        )


@dataclass(slots=True, frozen=True)
class NodeIdentityRecord:
    """
    Phase One's local audit record of the node identity/handshake
    outcome established before Phase Two's first boot.

    This file is deliberately NOT the mechanism Phase Two uses to
    retrieve ``node_identifier``/``authentication_token``/
    ``join_secret`` -- Phase One's boot media (where this record is
    written, alongside the rendered answer file) is a separate device
    from the target disk Proxmox VE is installed to; once the machine
    reboots into that freshly-installed OS, nothing guarantees Phase
    One's own media is still mounted or even still connected. Relying
    on it would silently break on exactly the unattended, zero-touch
    deployments this project exists to support. What Phase Two
    actually retrieves its identity from is
    ``ProvisioningProfile.bootstrap_source_url`` (see the module
    docstring's "still-open gap" note).

    This record exists for: (a) the Technician Console's REQ-TC-013
    deployment summary and REQ-TC-009 progress display, (b) local
    troubleshooting if a deployment fails partway through Phase One,
    and (c) an on-media paper trail matching REQ-LOG-004's
    "deployment lifecycle events" -- written under
    ``common.constants.deployment.USB_REPORT_DIRECTORY``, the same
    directory every other REQ-TC-013 deployment report already lives
    in.
    """

    node_identifier: str
    hostname: str
    reachable: bool
    authenticated: bool
    approved: bool
    detail: str
    recorded_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_handshake(cls, handshake: NodeHandshakeResult) -> "NodeIdentityRecord":
        return cls(
            node_identifier=handshake.node_identifier,
            hostname=handshake.hostname,
            reachable=handshake.reachable,
            authenticated=handshake.authenticated,
            approved=handshake.approved,
            detail=handshake.detail,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_identifier": self.node_identifier,
            "hostname": self.hostname,
            "reachable": self.reachable,
            "authenticated": self.authenticated,
            "approved": self.approved,
            "detail": self.detail,
            "recorded_at": self.recorded_at.isoformat(),
        }

    def write(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.to_dict(), indent=2), encoding="utf-8"
        )

    @classmethod
    def read(cls, source: Path) -> "NodeIdentityRecord":
        data = json.loads(source.read_text(encoding="utf-8"))
        return cls(
            node_identifier=str(data["node_identifier"]),
            hostname=str(data["hostname"]),
            reachable=bool(data["reachable"]),
            authenticated=bool(data["authenticated"]),
            approved=bool(data["approved"]),
            detail=str(data["detail"]),
            recorded_at=datetime.fromisoformat(str(data["recorded_at"])),
        )


@dataclass(slots=True, frozen=True)
class ProvisioningWorkflowResult:
    """
    The full outcome of this stage: which of Network Validation,
    Handshake, and Provisioning ran and how each concluded.

    ``aborted``/``abort_reason`` reflect the *first* stage that halted
    the run -- Network Validation and Handshake failures never reach
    ``ProvisioningManager.run()`` at all, so ``provisioning_summary``
    is ``None`` in that case (not a summary full of "not checked"
    placeholders).
    """

    network_result: Optional[NetworkValidationResult]
    handshake: Optional[NodeHandshakeResult]
    identity_record: Optional[NodeIdentityRecord]
    provisioning_summary: Optional[ProvisioningSummary]
    aborted: bool
    abort_reason: Optional[str] = None

    @property
    def ready_for_handoff(self) -> bool:
        return (
            not self.aborted
            and self.provisioning_summary is not None
            and self.provisioning_summary.ready_for_handoff
        )

    @property
    def status_message(self) -> str:
        if self.aborted:
            return f"Provisioning stage halted: {self.abort_reason}"
        if self.provisioning_summary is not None:
            return self.provisioning_summary.status_message
        return "Provisioning stage did not run."

    def to_dict(self) -> dict[str, Any]:
        """
        A JSON-serializable rendering of this result. Added this
        session alongside ``workflows.deployment_manager.WorkflowSummary
        .to_dict()`` for ``cli/``'s ``--json`` output mode -- see that
        method's own docstring for why this lives here rather than in
        ``cli/``.

        Deliberately excludes every secret ``NodeHandshakeResult``
        carries (``authentication_token``, ``cluster_join_token``,
        ``ssh_authorized_keys``) -- this dict is meant to be safe to
        print, log, or write to a report file (REQ-SEC-008/009/010:
        the same "never surfaced outside the environment-variable
        secret path" discipline already applied to the Controller
        enrollment token and cluster join token everywhere else in
        this codebase).
        """

        return {
            "aborted": self.aborted,
            "abort_reason": self.abort_reason,
            "status_message": self.status_message,
            "ready_for_handoff": self.ready_for_handoff,
            "network_result": (
                {
                    "succeeded": self.network_result.succeeded,
                    "recovered": self.network_result.recovered,
                    "status_message": self.network_result.status_message,
                }
                if self.network_result is not None
                else None
            ),
            "handshake": (
                {
                    "node_identifier": self.handshake.node_identifier,
                    "hostname": self.handshake.hostname,
                    "reachable": self.handshake.reachable,
                    "authenticated": self.handshake.authenticated,
                    "approved": self.handshake.approved,
                }
                if self.handshake is not None
                else None
            ),
            "identity_record": (
                self.identity_record.to_dict()
                if self.identity_record is not None
                else None
            ),
            "provisioning_summary": (
                self.provisioning_summary.to_dict()
                if self.provisioning_summary is not None
                else None
            ),
        }


class ProvisioningWorkflowStage:
    """
    Runs Network Validation, the Deployment Controller handshake, and
    the Provisioning Engine as one stage of Workflow B (Aquila Node
    Provisioning).

    Satisfies ``interfaces.service.Service``.
    """

    def __init__(
        self,
        *,
        provisioning_manager: Optional[ProvisioningManager] = None,
        network_service: Optional[NetworkService] = None,
        deployment_service_factory: Optional[DeploymentServiceFactory] = None,
        event_bus: Optional["EventBus"] = None,
    ) -> None:
        self._manager = provisioning_manager or ProvisioningManager(event_bus)
        self._network_service = network_service or NetworkService(event_bus)
        self._deployment_service_factory = (
            deployment_service_factory or _default_deployment_service_factory
        )
        self._initialized = False

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        self._manager.initialize()
        self._network_service.initialize()
        self._initialized = True

    def shutdown(self) -> None:
        self._manager.shutdown()
        self._network_service.shutdown()
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def last_summary(self) -> Optional[ProvisioningSummary]:
        return self._manager.last_summary

    # ------------------------------------------------------------------
    # Stage: Network Validation + Handshake + Provisioning
    # ------------------------------------------------------------------

    def run(
        self,
        preparation_summary: PreparationSummary,
        *,
        node_name: str,
        inspection_report: HardwareInspectionReport,
        deployment_config: DeploymentConfig,
        controller_config: ControllerConfig,
        network_config: NetworkConfig,
        cluster_config: Optional[ClusterConfig],
        target_device: StorageDevice,
        profile_template: ProvisioningProfileTemplate,
        root_password: str,
        phase_two_directory: Path,
        answer_file_destination: Path,
        identity_record_destination: Path,
        boot_entry_id: str,
        manifest_filename: str = DEFAULT_MANIFEST_FILENAME,
        trigger_handoff: bool = True,
        connectivity_retry_count: Optional[int] = None,
        connectivity_retry_delay_seconds: Optional[float] = None,
        connectivity_sleep: Optional[Callable[[float], None]] = None,
        network_max_recovery_attempts: int = 1,
        workflow_progress_callback: Optional[WorkflowProgressCallback] = None,
    ) -> ProvisioningWorkflowResult:
        """
        Validate the network, establish this node's identity with the
        Deployment Controller, and (if both succeed) run Provisioning.

        Args:
            preparation_summary, node_name, inspection_report,
            deployment_config, controller_config, target_device,
            root_password, phase_two_directory, answer_file_destination,
            boot_entry_id, manifest_filename, trigger_handoff,
            connectivity_retry_count, connectivity_retry_delay_seconds,
            connectivity_sleep: Forwarded to ``ProvisioningManager
                .run()`` -- see that method's own docstring.
            network_config, cluster_config: REQ-NET-001 through -010's
                connectivity policy, passed to ``NetworkService
                .establish()``.
            profile_template: The technician-supplied, node-specific
                answer-file fields not derived from the handshake.
            identity_record_destination: Where this stage writes its
                :class:`NodeIdentityRecord` audit trail (typically
                under ``common.constants.deployment
                .USB_REPORT_DIRECTORY``).
            network_max_recovery_attempts: Forwarded to
                ``NetworkService.establish()``.
            workflow_progress_callback: Notified at each of this
                stage's three phases (REQ-TC-009).

        Raises:
            DeploymentProvisioningError: If ``preparation_summary`` is
                not ``all_succeeded`` (REQ-PROV-001) -- checked here,
                before any network call is made, for symmetry with
                ``ProvisioningManager.run()``'s own identical check.
        """

        if not self._initialized:
            self.initialize()

        if not preparation_summary.all_succeeded:
            raise DeploymentProvisioningError(
                "Provisioning cannot begin: preparation has not "
                "completed successfully (REQ-PROV-001). Preparation "
                f"status: {preparation_summary.status_message}"
            )

        # ------------------------------------------------------------
        # 1. Network Validation (REQ-NET-001 through -010)
        # ------------------------------------------------------------

        emit(
            workflow_progress_callback,
            STAGE_NAME,
            "Validating network connectivity.",
            logger=logger,
        )

        network_result = self._network_service.establish(
            network_config,
            controller_config=controller_config,
            cluster_config=cluster_config,
            max_recovery_attempts=network_max_recovery_attempts,
        )

        if not network_result.succeeded:
            emit(
                workflow_progress_callback,
                STAGE_NAME,
                f"Network Validation failed: {network_result.status_message}",
                severity="error",
                logger=logger,
            )
            return ProvisioningWorkflowResult(
                network_result=network_result,
                handshake=None,
                identity_record=None,
                provisioning_summary=None,
                aborted=True,
                abort_reason=network_result.status_message,
            )

        emit(
            workflow_progress_callback,
            STAGE_NAME,
            f"Network Validation passed: {network_result.status_message}",
            logger=logger,
        )

        # ------------------------------------------------------------
        # 2. Node identity + Deployment Controller handshake
        #    (REQ-BOOT-002/003/004, REQ-CTRL-016)
        # ------------------------------------------------------------

        enrollment_token = ConfigurationManager.resolve_secret(
            controller_config.authentication_token_env_var
        )
        if not enrollment_token:
            reason = (
                "Deployment Controller enrollment token not found in "
                f"environment variable "
                f"'{controller_config.authentication_token_env_var}' "
                "(REQ-SEC-008/009/010)."
            )
            emit(
                workflow_progress_callback,
                STAGE_NAME,
                reason,
                severity="error",
                logger=logger,
            )
            return ProvisioningWorkflowResult(
                network_result=network_result,
                handshake=None,
                identity_record=None,
                provisioning_summary=None,
                aborted=True,
                abort_reason=reason,
            )

        node_identifier = generate_node_identifier()

        emit(
            workflow_progress_callback,
            STAGE_NAME,
            f"Establishing identity with the Deployment Controller "
            f"(node_identifier={node_identifier}).",
            logger=logger,
        )

        deployment_service = self._deployment_service_factory(controller_config)
        deployment_service.initialize()
        try:
            handshake = deployment_service.handshake(
                node_identifier, enrollment_token=enrollment_token
            )
        finally:
            deployment_service.shutdown()

        identity_record = NodeIdentityRecord.from_handshake(handshake)
        identity_record.write(identity_record_destination)

        if not handshake.approved:
            emit(
                workflow_progress_callback,
                STAGE_NAME,
                f"Handshake did not complete: {handshake.detail}",
                severity="error" if handshake.authenticated else "warning",
                logger=logger,
            )
            return ProvisioningWorkflowResult(
                network_result=network_result,
                handshake=handshake,
                identity_record=identity_record,
                provisioning_summary=None,
                aborted=True,
                abort_reason=handshake.detail,
            )

        emit(
            workflow_progress_callback,
            STAGE_NAME,
            f"Handshake complete: hostname '{handshake.hostname}' assigned.",
            logger=logger,
        )

        # ------------------------------------------------------------
        # 3. Provisioning (REQ-PROV-001 through -021)
        # ------------------------------------------------------------

        scheme = "https" if controller_config.use_tls else "http"
        bootstrap_source_url = (
            f"{scheme}://{controller_config.host}:{controller_config.port}"
            f"{controller_config.api_base_path}/bootstrap/{node_identifier}"
        )

        profile = profile_template.to_profile(
            node_hostname=handshake.hostname,
            target_device_serial=target_device.serial_number,
            root_ssh_keys=handshake.ssh_authorized_keys,
            bootstrap_source_url=bootstrap_source_url,
        )

        emit(
            workflow_progress_callback,
            STAGE_NAME,
            "Running Provisioning Engine.",
            logger=logger,
        )

        summary = self._manager.run(
            preparation_summary,
            node_name=node_name,
            inspection_report=inspection_report,
            deployment_config=deployment_config,
            controller_config=controller_config,
            target_device=target_device,
            profile=profile,
            root_password=root_password,
            phase_two_directory=phase_two_directory,
            answer_file_destination=answer_file_destination,
            boot_entry_id=boot_entry_id,
            manifest_filename=manifest_filename,
            trigger_handoff=trigger_handoff,
            connectivity_retry_count=connectivity_retry_count,
            connectivity_retry_delay_seconds=connectivity_retry_delay_seconds,
            connectivity_sleep=connectivity_sleep,
        )

        if summary.aborted:
            emit(
                workflow_progress_callback,
                STAGE_NAME,
                f"Provisioning stage FAILED: {summary.status_message}",
                severity="error",
                logger=logger,
            )
        else:
            emit(
                workflow_progress_callback,
                STAGE_NAME,
                f"Provisioning stage complete: {summary.status_message}",
                logger=logger,
            )

        return ProvisioningWorkflowResult(
            network_result=network_result,
            handshake=handshake,
            identity_record=identity_record,
            provisioning_summary=summary,
            aborted=summary.aborted,
            abort_reason=summary.abort_reason,
        )

    # ------------------------------------------------------------------
    # Magic methods
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(initialized={self._initialized})"
        )


__all__ = [
    "STAGE_NAME",
    "DeploymentServiceFactory",
    "NodeIdentityRecord",
    "ProvisioningProfileTemplate",
    "ProvisioningWorkflowResult",
    "ProvisioningWorkflowStage",
]
