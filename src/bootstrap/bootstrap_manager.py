"""
Project Aquila
=============

Bootstrap Manager

The orchestrator for the Bootstrap Engine (SRS Section 10.7 /
REQ-BOOT-001 through REQ-BOOT-020) -- Phase Two's first-boot process
that converts a freshly-installed Proxmox node into a production-ready
Aquila node.

REQ-BOOT-001 ("execute automatically after the first successful
system boot") is satisfied one layer up, not by this class itself:
Proxmox's own confirmed ``[first-boot]`` answer-file mechanism (see
``provisioning.answer_file.render_answer_file`` and
``provisioning.report``'s module docstring) is what invokes whatever
script calls :meth:`BootstrapManager.run` during Phase Two's first
boot. This module is that run's implementation, not the trigger.

Known architectural gap, flagged rather than fabricated: REQ-BOOT-003
("authenticate the node") and REQ-BOOT-004 ("retrieve deployment
configuration") both require this node to already know its own
``node_identifier`` and a Controller authentication token *before*
Bootstrap's first Controller call -- but nothing in ``provisioning/``
as currently built establishes or passes either value from Phase One
into Phase Two (``provisioning.connectivity.ConnectivityChecker``
only checks reachability, it doesn't register the node or receive
credentials back). :meth:`run` therefore takes ``node_identifier`` and
``authentication_token`` as required, caller-supplied parameters
rather than inventing a retrieval mechanism this session couldn't
confirm -- see ``claude/aquila-project-status.md`` for the full note
on where that value needs to come from once ``deployment_controller/``
and a corresponding addition to ``provisioning/`` are designed.

Ordering (this session's resolved SRS ambiguity -- see
``claude/aquila-project-status.md``'s "SRS defect" note): Cluster
Enrollment, then Inventory Registration, then Benchmark -- matching
REQ-BOOT-012 through REQ-BOOT-016's numbered order and REQ-BENCH-010/
REQ-INV-003's requirement that a node's inventory record exist before
benchmark results can be associated with it, over Appendix B's
Workflow B diagram, which shows Benchmark before Inventory
Registration.

Required vs. best-effort stages (GP-008, generalized from
REQ-BOOT-010's battery-specific "if unsupported, log the limitation
and continue deployment" wording to the whole REQ-BOOT-007 through
REQ-BOOT-011 hardware/power-configuration group, as
``bootstrap.power``'s module docstring documents): sleep-target
masking, lid behavior, battery thresholds, and power-recovery policy
are all best-effort -- a failure is logged and Bootstrap continues.
Controller communication, hostname, SSH keys, cluster enrollment (and
its verification), and inventory registration are required -- a
failure there halts the run immediately, matching
``PreparationManager``/``ProvisioningManager``'s halt-immediately
discipline. Benchmark execution and its submission are best-effort,
per the Benchmark Engine's own overview: "Benchmarking shall not
prevent the node from entering operational service."

Follows the ``Service`` lifecycle / ``TYPE_CHECKING``-only
``EventBus`` / best-effort ``_publish()`` conventions
``PreparationManager``/``ProvisioningManager`` established, and
reuses ``BootstrapStartedEvent``/``BootstrapCompletedEvent`` (already
defined in ``common.events.types.deployment``, unused until now).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from json import dumps
from typing import TYPE_CHECKING, Any, ClassVar, Mapping, TypeAlias

from bootstrap.battery import (
    BatteryThresholdConfigurator,
    BatteryThresholdResult,
)
from bootstrap.benchmark import BenchmarkInitiator
from bootstrap.cleanup import ArtifactCleaner, CleanupResult
from bootstrap.cluster import (
    ClusterEnrollment,
    ClusterJoinResult,
    ClusterVerificationResult,
)
from bootstrap.controller_client import DeploymentControllerClient
from bootstrap.hostname import HostnameConfigurator, HostnameResult
from bootstrap.inventory import InventoryCollector
from bootstrap.power import (
    LidBehaviorConfigurator,
    LidBehaviorResult,
    PowerRecoveryConfigurator,
    PowerRecoveryResult,
    SleepTargetManager,
    SleepTargetResult,
)
from bootstrap.ssh import SSHKeyInstaller, SSHKeyInstallResult
from common.constants.logging import BOOTSTRAP_LOGGER
from common.events.types.deployment import (
    BootstrapCompletedEvent,
    BootstrapStartedEvent,
)
from config.schemas.cluster_schema import ClusterConfig
from config.schemas.controller_schema import ControllerConfig
from config.schemas.deployment_schema import DeploymentConfig

if TYPE_CHECKING:
    from common.events.bus import EventBus

logger = logging.getLogger(BOOTSTRAP_LOGGER)

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

#: REQ-INV-005's node-status vocabulary. Reported to the Deployment
#: Controller as a plain string, not a shared enum: the authoritative
#: home for this vocabulary is ``inventory/``/``models/inventory/``,
#: neither of which is built yet, and ``common.enums.DeploymentStatus``
#: (PENDING/RUNNING/SUCCESS/FAILED/CANCELLED) does not match
#: REQ-INV-005's specific node-lifecycle terms (Pending/Provisioning/
#: Bootstrapping/Operational/Failed/Retired) -- a gap flagged in
#: ``claude/aquila-project-status.md`` for whoever builds ``inventory/``,
#: not resolved here by redefining it out of this package's scope.
STATUS_OPERATIONAL = "operational"
STATUS_FAILED = "failed"


def _parse_datetime(value: Any, *, default: datetime) -> datetime:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return default
    return default


@dataclass(slots=True, frozen=True)
class BootstrapSummary:
    """The complete outcome of one Bootstrap Engine run (REQ-BOOT-018)."""

    SCHEMA_VERSION: ClassVar[int] = 1

    started_at: datetime
    completed_at: datetime

    node_identifier: str
    hostname: str

    controller_reachable: bool
    authenticated: bool
    configuration_retrieved: bool

    hostname_result: HostnameResult | None = None
    ssh_result: SSHKeyInstallResult | None = None
    sleep_target_result: SleepTargetResult | None = None
    lid_result: LidBehaviorResult | None = None
    battery_results: tuple[BatteryThresholdResult, ...] = ()
    power_recovery_result: PowerRecoveryResult | None = None

    cluster_join_result: ClusterJoinResult | None = None
    cluster_verification_result: ClusterVerificationResult | None = None

    inventory_registered: bool = False
    benchmark_overall_score: int | None = None
    benchmark_submitted: bool = False

    cleanup_result: CleanupResult | None = None
    completion_reported: bool = False

    aborted: bool = False
    abort_reason: str | None = None

    @property
    def duration(self) -> timedelta:
        return self.completed_at - self.started_at

    @property
    def operational(self) -> bool:
        """
        REQ-BOOT-019/020: whether every *required* stage succeeded,
        so the node should transition into normal operational status.
        Best-effort stages (sleep targets, lid, battery, power
        recovery, benchmark) do not gate this.
        """

        return (
            not self.aborted
            and self.controller_reachable
            and self.authenticated
            and self.configuration_retrieved
            and self.hostname_result is not None
            and self.hostname_result.applied
            and self.ssh_result is not None
            and self.ssh_result.installed_count > 0
            and self.cluster_join_result is not None
            and self.cluster_join_result.command_succeeded
            and self.cluster_verification_result is not None
            and self.cluster_verification_result.verified
            and self.inventory_registered
        )

    @property
    def status(self) -> str:
        return STATUS_OPERATIONAL if self.operational else STATUS_FAILED

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_seconds": self.duration.total_seconds(),
            "node_identifier": self.node_identifier,
            "hostname": self.hostname,
            "controller_reachable": self.controller_reachable,
            "authenticated": self.authenticated,
            "configuration_retrieved": self.configuration_retrieved,
            "hostname_applied": bool(
                self.hostname_result and self.hostname_result.applied
            ),
            "ssh_keys_installed": (
                self.ssh_result.installed_count if self.ssh_result else 0
            ),
            "sleep_targets_masked": bool(self.sleep_target_result),
            "lid_action_applied": bool(
                self.lid_result and self.lid_result.applied
            ),
            "battery_thresholds_applied": sum(
                1 for r in self.battery_results if r.applied
            ),
            "power_recovery_applied": bool(
                self.power_recovery_result
                and self.power_recovery_result.applied
            ),
            "cluster_joined": bool(
                self.cluster_join_result
                and self.cluster_join_result.command_succeeded
            ),
            "cluster_verified": bool(
                self.cluster_verification_result
                and self.cluster_verification_result.verified
            ),
            "inventory_registered": self.inventory_registered,
            "benchmark_overall_score": self.benchmark_overall_score,
            "benchmark_submitted": self.benchmark_submitted,
            "completion_reported": self.completion_reported,
            "aborted": self.aborted,
            "abort_reason": self.abort_reason,
            "operational": self.operational,
            "status": self.status,
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return dumps(
            self.to_dict(), indent=indent, sort_keys=True, ensure_ascii=False
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BootstrapSummary":
        now = datetime.now(UTC)
        started_at = _parse_datetime(data.get("started_at"), default=now)
        completed_at = _parse_datetime(
            data.get("completed_at"), default=started_at
        )

        return cls(
            started_at=started_at,
            completed_at=completed_at,
            node_identifier=str(data.get("node_identifier") or ""),
            hostname=str(data.get("hostname") or ""),
            controller_reachable=bool(
                data.get("controller_reachable", False)
            ),
            authenticated=bool(data.get("authenticated", False)),
            configuration_retrieved=bool(
                data.get("configuration_retrieved", False)
            ),
            inventory_registered=bool(
                data.get("inventory_registered", False)
            ),
            benchmark_submitted=bool(
                data.get("benchmark_submitted", False)
            ),
            completion_reported=bool(
                data.get("completion_reported", False)
            ),
            aborted=bool(data.get("aborted", False)),
            abort_reason=(
                str(data["abort_reason"])
                if data.get("abort_reason") is not None
                else None
            ),
        )


class BootstrapManager:
    """
    Orchestrates the Bootstrap Engine's full first-boot sequence.
    """

    def __init__(
        self,
        *,
        event_bus: "EventBus | None" = None,
        hostname_configurator: HostnameConfigurator | None = None,
        ssh_installer: SSHKeyInstaller | None = None,
        sleep_target_manager: SleepTargetManager | None = None,
        lid_configurator: LidBehaviorConfigurator | None = None,
        battery_configurator: BatteryThresholdConfigurator | None = None,
        power_recovery_configurator: (
            PowerRecoveryConfigurator | None
        ) = None,
        cluster_enrollment: ClusterEnrollment | None = None,
        inventory_collector: InventoryCollector | None = None,
        benchmark_initiator: BenchmarkInitiator | None = None,
        artifact_cleaner: ArtifactCleaner | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._is_initialized = False
        self._last_summary: BootstrapSummary | None = None

        self._hostname_configurator = (
            hostname_configurator or HostnameConfigurator()
        )
        self._ssh_installer = ssh_installer or SSHKeyInstaller()
        self._sleep_target_manager = (
            sleep_target_manager or SleepTargetManager()
        )
        self._lid_configurator = (
            lid_configurator or LidBehaviorConfigurator()
        )
        self._battery_configurator = (
            battery_configurator or BatteryThresholdConfigurator()
        )
        self._power_recovery_configurator = (
            power_recovery_configurator or PowerRecoveryConfigurator()
        )
        self._cluster_enrollment = (
            cluster_enrollment or ClusterEnrollment()
        )
        self._inventory_collector = (
            inventory_collector or InventoryCollector()
        )
        self._benchmark_initiator = (
            benchmark_initiator or BenchmarkInitiator()
        )
        self._artifact_cleaner = artifact_cleaner or ArtifactCleaner()

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    def initialize(self) -> None:
        self._is_initialized = True

    def shutdown(self) -> None:
        self._is_initialized = False

    @property
    def last_summary(self) -> BootstrapSummary | None:
        return self._last_summary

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run(
        self,
        *,
        node_identifier: str,
        authentication_token: str,
        controller_config: ControllerConfig,
        cluster_config: ClusterConfig,
        deployment_config: DeploymentConfig,
        join_secret: str,
        controller_client: DeploymentControllerClient | None = None,
    ) -> BootstrapSummary:
        """
        Execute the full first-boot sequence.

        ``node_identifier``/``authentication_token``/``join_secret``
        are required, caller-resolved parameters -- see this module's
        docstring for the flagged gap in how a real first-boot script
        currently obtains them.
        """

        started_at = datetime.now(UTC)
        self._publish(BootstrapStartedEvent(node_identifier))

        client = controller_client or DeploymentControllerClient(
            controller_config
        )

        aborted = False
        abort_reason: str | None = None
        hostname = ""

        controller_reachable = client.verify_communication()
        if not controller_reachable:
            aborted = True
            abort_reason = "Deployment Controller unreachable."

        authenticated = False
        if not aborted:
            try:
                client.authenticate(node_identifier, authentication_token)
                authenticated = True
            except Exception as exc:
                aborted = True
                abort_reason = f"Authentication failed: {exc}"

        configuration_retrieved = False
        node_config = None
        if not aborted:
            try:
                node_config = client.retrieve_configuration(
                    node_identifier
                )
                configuration_retrieved = True
                hostname = node_config.hostname
            except Exception as exc:
                aborted = True
                abort_reason = f"Configuration retrieval failed: {exc}"

        hostname_result: HostnameResult | None = None
        if not aborted and node_config is not None:
            try:
                hostname_result = self._hostname_configurator.configure(
                    node_config.hostname
                )
            except Exception as exc:
                aborted = True
                abort_reason = f"Hostname configuration failed: {exc}"

        ssh_result: SSHKeyInstallResult | None = None
        if not aborted and node_config is not None:
            try:
                ssh_result = self._ssh_installer.install(
                    node_config.ssh_authorized_keys
                )
            except Exception as exc:
                aborted = True
                abort_reason = f"SSH key installation failed: {exc}"

        # -- Best-effort hardware/power configuration (GP-008) -------
        sleep_target_result = self._try_sleep_targets(deployment_config)
        lid_result = self._try_lid(deployment_config)
        battery_results = self._try_battery(deployment_config)
        power_recovery_result = self._try_power_recovery(
            deployment_config
        )

        cluster_join_result: ClusterJoinResult | None = None
        cluster_verification_result: (
            ClusterVerificationResult | None
        ) = None
        if not aborted:
            try:
                cluster_join_result = self._cluster_enrollment.join(
                    cluster_config, join_secret
                )
                cluster_verification_result = (
                    self._cluster_enrollment.verify(hostname)
                )
            except Exception as exc:
                aborted = True
                abort_reason = f"Cluster enrollment failed: {exc}"

        inventory_registered = False
        if not aborted:
            try:
                facts = self._inventory_collector.collect()
                payload = facts.to_dict()
                payload["node_identifier"] = node_identifier
                payload["hostname"] = hostname
                client.register_inventory(payload)
                inventory_registered = True
            except Exception as exc:
                aborted = True
                abort_reason = f"Inventory registration failed: {exc}"

        benchmark_score: int | None = None
        benchmark_submitted = False
        if not aborted:
            try:
                report = self._benchmark_initiator.run()
                benchmark_score = report.overall_score
                try:
                    client.submit_benchmark(report.to_dict())
                    benchmark_submitted = True
                except Exception as exc:
                    logger.warning(
                        "Benchmark results could not be submitted: %s",
                        exc,
                    )
            except Exception as exc:
                logger.warning("Benchmark execution failed: %s", exc)

        completion_reported = False
        try:
            client.report_completion(
                node_identifier,
                status=(
                    STATUS_FAILED if aborted else STATUS_OPERATIONAL
                ),
                detail=abort_reason or "Bootstrap completed.",
            )
            completion_reported = True
        except Exception as exc:
            logger.warning(
                "Completion report could not be delivered: %s", exc
            )

        cleanup_result = self._artifact_cleaner.clean()

        if controller_client is None:
            client.close()

        completed_at = datetime.now(UTC)

        summary = BootstrapSummary(
            started_at=started_at,
            completed_at=completed_at,
            node_identifier=node_identifier,
            hostname=hostname,
            controller_reachable=controller_reachable,
            authenticated=authenticated,
            configuration_retrieved=configuration_retrieved,
            hostname_result=hostname_result,
            ssh_result=ssh_result,
            sleep_target_result=sleep_target_result,
            lid_result=lid_result,
            battery_results=battery_results,
            power_recovery_result=power_recovery_result,
            cluster_join_result=cluster_join_result,
            cluster_verification_result=cluster_verification_result,
            inventory_registered=inventory_registered,
            benchmark_overall_score=benchmark_score,
            benchmark_submitted=benchmark_submitted,
            cleanup_result=cleanup_result,
            completion_reported=completion_reported,
            aborted=aborted,
            abort_reason=abort_reason,
        )

        self._last_summary = summary
        self._publish(BootstrapCompletedEvent(node_identifier))

        return summary

    # ------------------------------------------------------------------
    # Best-effort helpers (GP-008)
    # ------------------------------------------------------------------

    def _try_sleep_targets(
        self, deployment_config: DeploymentConfig
    ) -> SleepTargetResult | None:
        if not deployment_config.disable_sleep_targets:
            return None
        try:
            return self._sleep_target_manager.mask_all()
        except Exception as exc:
            logger.warning("Sleep-target masking failed: %s", exc)
            return None

    def _try_lid(
        self, deployment_config: DeploymentConfig
    ) -> LidBehaviorResult | None:
        try:
            return self._lid_configurator.configure(
                deployment_config.lid_action
            )
        except Exception as exc:
            logger.warning("Lid-behavior configuration failed: %s", exc)
            return None

    def _try_battery(
        self, deployment_config: DeploymentConfig
    ) -> tuple[BatteryThresholdResult, ...]:
        start = deployment_config.battery_charge_start_threshold
        end = deployment_config.battery_charge_end_threshold
        if start is None or end is None:
            return ()
        try:
            return self._battery_configurator.configure(start, end)
        except Exception as exc:
            logger.warning(
                "Battery threshold configuration failed: %s", exc
            )
            return ()

    def _try_power_recovery(
        self, deployment_config: DeploymentConfig
    ) -> PowerRecoveryResult | None:
        try:
            return self._power_recovery_configurator.configure(
                deployment_config.power_recovery_policy
            )
        except Exception as exc:
            logger.warning(
                "Power-recovery policy configuration failed: %s", exc
            )
            return None

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _publish(self, event: Any) -> None:
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish(event)
        except Exception:
            logger.debug(
                "Failed to publish %s.", type(event).__name__,
                exc_info=True,
            )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"initialized={self._is_initialized})"
        )


__all__ = [
    "STATUS_FAILED",
    "STATUS_OPERATIONAL",
    "BootstrapManager",
    "BootstrapSummary",
]
