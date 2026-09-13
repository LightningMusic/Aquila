"""
Project Aquila
=============

Networking Engine Orchestrator

Implements REQ-NET-011 ("if network connectivity is lost during
provisioning, Aquila shall pause deployment and attempt recovery when
practical"), REQ-NET-012 ("if communication cannot be restored, Aquila
shall terminate provisioning safely and preserve diagnostic
information"), REQ-NET-013 ("the Networking Engine shall record
network diagnostics within the deployment report"), and REQ-NET-014
("the Networking Engine shall log all network validation failures").

Orchestrates every other module in this package (``ethernet``,
``dhcp``, ``gateway``, ``dns``, ``controller``, ``cluster``) into the
single end-to-end sequence REQ-NET-001 through REQ-NET-010 describe,
mirroring the ``Service`` lifecycle and event-publishing conventions
every other Manager in this codebase (``PreparationManager``,
``ProvisioningManager``, ``BootstrapManager``) already established.

Ownership boundary (REQ-NET-012)
---------------------------------
REQ-NET-012 says Aquila "shall terminate provisioning safely" on
unrecoverable connectivity loss -- but *terminating provisioning* is
``provisioning_manager.py``'s responsibility (GP-004: modular design,
one subsystem per responsibility), not this module's. ``NetworkManager``
never calls into ``provisioning/`` itself; instead it returns a
``NetworkDiagnostics`` result whose ``.overall_ok``/``.abort_reason``
fields let a caller (a future ``provisioning_manager.py`` integration)
decide to halt, exactly like it already halts on
``MinimumRequirementsValidator``/``ConnectivityChecker`` failures
today.

Event publishing
-------------------
Only this orchestrator publishes events -- ``ethernet.py``,
``dhcp.py``, ``gateway.py``, ``dns.py``, ``controller.py``, and
``cluster.py`` stay event-free, mirroring the exact precedent
``bootstrap/``'s helper modules (``hostname.py``, ``ssh.py``,
``power.py``, ...) already set: only ``bootstrap_manager.py``
publishes events there too. REQ-NET-010's reachability check publishes
the generic ``ConnectivityTestStarted/Passed/FailedEvent`` pattern
rather than the pre-built ``ClusterJoin*`` events -- see
``networking.cluster``'s module docstring for why.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Callable, Optional

from common.constants.deployment import (
    NETWORK_RETRY_COUNT,
    NETWORK_RETRY_DELAY_SECONDS,
)
from common.constants.logging import NETWORK_LOGGER
from common.events.types.networking import (
    ConnectivityTestFailedEvent,
    ConnectivityTestPassedEvent,
    ConnectivityTestStartedEvent,
    DNSResolutionFailedEvent,
    DNSResolvedEvent,
    EthernetDetectedEvent,
    EthernetDisconnectedEvent,
    GatewayReachableEvent,
    GatewayUnreachableEvent,
    IPAddressAssignedEvent,
    IPConfigurationFailedEvent,
)
from common.exceptions.networking import NetworkingError
from config.schemas.cluster_schema import ClusterConfig
from config.schemas.controller_schema import ControllerConfig
from config.schemas.network_schema import NetworkConfig
from models.hardware.network import NetworkAdapter

from .cluster import ClusterReachabilityChecker
from .controller import ControllerReachabilityChecker, HostReachabilityResult
from .dhcp import AddressAssignmentResult, NetworkAddressAssigner
from .dns import DNSResolutionChecker, DNSResolutionResult
from .ethernet import EthernetChecker
from .gateway import GatewayChecker, GatewayReachabilityResult

if TYPE_CHECKING:
    # Imported only for type annotations -- this module never
    # constructs an EventBus itself, the caller owns it and passes one
    # in (see provisioning.provisioning_manager's identical pattern).
    from common.events.bus import EventBus

logger = logging.getLogger(NETWORK_LOGGER)


@dataclass(slots=True, frozen=True)
class NetworkDiagnostics:
    """
    REQ-NET-013: network diagnostics suitable for inclusion within the
    deployment report.

    Deliberately its own standalone report object rather than new
    fields bolted onto ``provisioning.report.ProvisioningSummary`` --
    wiring this into that dataclass is a real future integration step
    (documented, not built speculatively this session) that would
    touch ``provisioning_manager.py`` and its already-passing test
    suite.
    """

    started_at: datetime
    completed_at: datetime

    ethernet_connected: bool
    ethernet_detail: str

    ip_assignment_method: str
    ip_assignment_succeeded: bool
    ip_assignment_detail: str
    assigned_ip_addresses: tuple[str, ...] = ()

    gateway_checked: bool = False
    gateway_reachable: bool = False
    gateway_detail: str = ""

    dns_checked: bool = False
    dns_resolved: bool = False
    dns_detail: str = ""

    controller_reachable: bool = False
    controller_detail: str = ""

    cluster_checked: bool = False
    cluster_reachable: bool = False
    cluster_detail: str = ""

    #: Set only by :meth:`NetworkManager.attempt_recovery` -- how many
    #: additional full connectivity-establishment passes (beyond the
    #: first) were required before either succeeding or exhausting
    #: ``max_attempts`` (REQ-NET-011).
    recovered_after_attempts: int = 0

    aborted: bool = False
    abort_reason: str | None = None

    @property
    def overall_ok(self) -> bool:
        """
        Whether every check that actually ran succeeded. A check that
        was never required (its ``*_checked`` flag is ``False``) does
        not count against this -- REQ-NET-007/008 are conditional on
        deployment policy ("when required by deployment policy").
        """

        if self.aborted:
            return False
        if not self.ethernet_connected or not self.ip_assignment_succeeded:
            return False
        if self.gateway_checked and not self.gateway_reachable:
            return False
        if self.dns_checked and not self.dns_resolved:
            return False
        if not self.controller_reachable:
            return False
        if self.cluster_checked and not self.cluster_reachable:
            return False
        return True

    @property
    def status_message(self) -> str:
        if self.overall_ok:
            return "All required networking checks passed."
        return self.abort_reason or "One or more networking checks failed."

    def to_dict(self) -> dict[str, Any]:
        """A JSON-serializable form, for inclusion in a deployment report."""

        return {
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "ethernet_connected": self.ethernet_connected,
            "ethernet_detail": self.ethernet_detail,
            "ip_assignment_method": self.ip_assignment_method,
            "ip_assignment_succeeded": self.ip_assignment_succeeded,
            "ip_assignment_detail": self.ip_assignment_detail,
            "assigned_ip_addresses": list(self.assigned_ip_addresses),
            "gateway_checked": self.gateway_checked,
            "gateway_reachable": self.gateway_reachable,
            "gateway_detail": self.gateway_detail,
            "dns_checked": self.dns_checked,
            "dns_resolved": self.dns_resolved,
            "dns_detail": self.dns_detail,
            "controller_reachable": self.controller_reachable,
            "controller_detail": self.controller_detail,
            "cluster_checked": self.cluster_checked,
            "cluster_reachable": self.cluster_reachable,
            "cluster_detail": self.cluster_detail,
            "recovered_after_attempts": self.recovered_after_attempts,
            "aborted": self.aborted,
            "abort_reason": self.abort_reason,
            "overall_ok": self.overall_ok,
            "status_message": self.status_message,
        }


def _resolve_gateway(
    config: NetworkConfig, assignment_result: AddressAssignmentResult
) -> str:
    """
    Determine which gateway REQ-NET-007 should check.

    For a static assignment, the gateway is explicit configuration.
    For DHCP, ``NetworkConfig`` has no configured gateway at all -- the
    only way to know it is to read back what DHCP actually assigned,
    which :meth:`NetworkAddressAssigner.verify_assignment` already
    captures into ``AddressAssignmentResult.default_gateways``.
    """

    if config.ip_assignment_method == "static_ipv4" and config.static_ipv4_gateway:
        return config.static_ipv4_gateway

    if config.ip_assignment_method == "static_ipv6" and config.static_ipv6_gateway:
        return config.static_ipv6_gateway

    if assignment_result.default_gateways:
        return assignment_result.default_gateways[0]

    return ""


class NetworkManager:
    """Orchestrates the Networking Engine (REQ-NET-001 through REQ-NET-014)."""

    def __init__(
        self,
        event_bus: Optional["EventBus"] = None,
        *,
        ethernet_checker: EthernetChecker | None = None,
        address_assigner: NetworkAddressAssigner | None = None,
        gateway_checker: GatewayChecker | None = None,
        dns_checker: DNSResolutionChecker | None = None,
        controller_checker: ControllerReachabilityChecker | None = None,
        cluster_checker: ClusterReachabilityChecker | None = None,
    ) -> None:
        self._event_bus: Optional["EventBus"] = event_bus

        self._ethernet_checker = ethernet_checker or EthernetChecker()
        self._address_assigner = address_assigner or NetworkAddressAssigner()
        self._gateway_checker = gateway_checker or GatewayChecker()
        self._dns_checker = dns_checker or DNSResolutionChecker()
        self._controller_checker = (
            controller_checker or ControllerReachabilityChecker()
        )
        self._cluster_checker = cluster_checker or ClusterReachabilityChecker()

        self._last_diagnostics: NetworkDiagnostics | None = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Service lifecycle (interfaces.service.Service)
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Mark the Networking Engine ready. Idempotent."""

        self._initialized = True

    def shutdown(self) -> None:
        """Release any resources this manager holds. A documented no-op."""

        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def last_diagnostics(self) -> NetworkDiagnostics | None:
        """The most recently completed connectivity check, if any."""

        return self._last_diagnostics

    # ------------------------------------------------------------------
    # Networking (REQ-NET-001 through REQ-NET-010)
    # ------------------------------------------------------------------

    def establish_connectivity(
        self,
        config: NetworkConfig,
        *,
        controller_config: ControllerConfig,
        cluster_config: ClusterConfig | None = None,
        retry_count: int = NETWORK_RETRY_COUNT,
        retry_delay_seconds: float = NETWORK_RETRY_DELAY_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> NetworkDiagnostics:
        """
        Run the full REQ-NET-001 through REQ-NET-010 sequence once and
        return a REQ-NET-013 diagnostics record.

        Halts at the first required check that fails, matching every
        other Manager's "halt immediately" discipline in this
        codebase (``PreparationManager``, ``ProvisioningManager``): a
        later check is never spent time on once an earlier one has
        already determined the run cannot proceed.
        """

        started_at = datetime.now(UTC)
        self._publish(lambda: ConnectivityTestStartedEvent())
        logger.info("Networking Engine: connectivity establishment started.")

        aborted = False
        abort_reason: str | None = None

        # -- REQ-NET-001/002/003/004: Ethernet ---------------------------
        ethernet_result = self._ethernet_checker.check_link(
            retry_count=retry_count,
            retry_delay_seconds=retry_delay_seconds,
            sleep=sleep,
        )

        if ethernet_result.connected and ethernet_result.primary_adapter is not None:
            primary_adapter = ethernet_result.primary_adapter
            self._publish(
                lambda: EthernetDetectedEvent(
                    interface=primary_adapter.name,
                    mac_address=primary_adapter.mac_address,
                    link_up=True,
                )
            )
        else:
            primary_adapter = None
            aborted = True
            abort_reason = ethernet_result.detail
            logger.error(
                "Networking Engine halted (REQ-NET-014): %s", abort_reason
            )
            self._publish(
                lambda: EthernetDisconnectedEvent(
                    interface=(
                        ethernet_result.checked_adapter_names[0]
                        if ethernet_result.checked_adapter_names
                        else "unknown"
                    )
                )
            )

        # -- REQ-NET-005/006: IP address acquisition ---------------------
        assignment_result = self._acquire_and_verify_address(
            config,
            adapter=primary_adapter,
            aborted=aborted,
            retry_count=retry_count,
            retry_delay_seconds=retry_delay_seconds,
            sleep=sleep,
        )
        if not assignment_result.succeeded:
            if not aborted:
                aborted = True
                abort_reason = assignment_result.detail
                logger.error(
                    "Networking Engine halted (REQ-NET-014): %s", abort_reason
                )

        # -- REQ-NET-007: Gateway -----------------------------------------
        gateway_checked = False
        gateway_result = GatewayReachabilityResult(
            reachable=False, gateway="", detail="Gateway was not checked."
        )
        if not aborted and config.require_gateway_reachability:
            gateway_checked = True
            gateway = _resolve_gateway(config, assignment_result)
            gateway_result = self._gateway_checker.check(
                gateway,
                retry_count=retry_count,
                retry_delay_seconds=retry_delay_seconds,
                timeout_seconds=min(
                    2.0, float(config.connectivity_check_timeout_seconds)
                ),
                sleep=sleep,
            )
            if gateway_result.reachable:
                self._publish(
                    lambda: GatewayReachableEvent(gateway=gateway_result.gateway)
                )
            else:
                aborted = True
                abort_reason = gateway_result.detail
                logger.error(
                    "Networking Engine halted (REQ-NET-014): %s", abort_reason
                )
                self._publish(
                    lambda: GatewayUnreachableEvent(gateway=gateway_result.gateway)
                )

        # -- REQ-NET-008: DNS ----------------------------------------------
        dns_checked = False
        dns_result = DNSResolutionResult(
            resolved=False, hostname="", detail="DNS resolution was not checked."
        )
        if not aborted and config.require_dns_resolution:
            dns_checked = True
            dns_result = self._dns_checker.check(
                controller_config.host,
                retry_count=retry_count,
                retry_delay_seconds=retry_delay_seconds,
                sleep=sleep,
            )
            if dns_result.resolved:
                self._publish(
                    lambda: DNSResolvedEvent(
                        hostname=dns_result.hostname,
                        ip_address=dns_result.resolved_address,
                    )
                )
            else:
                aborted = True
                abort_reason = dns_result.detail
                logger.error(
                    "Networking Engine halted (REQ-NET-014): %s", abort_reason
                )
                self._publish(
                    lambda: DNSResolutionFailedEvent(hostname=dns_result.hostname)
                )

        # -- REQ-NET-009: Deployment Controller reachability ---------------
        controller_result = HostReachabilityResult(
            reachable=False,
            detail="Deployment Controller reachability was not checked.",
            host=controller_config.host,
            port=controller_config.port,
        )
        if not aborted:
            controller_result = self._controller_checker.check(
                controller_config.host,
                controller_config.port,
                timeout_seconds=float(controller_config.connection_timeout_seconds),
                retry_count=retry_count,
                retry_delay_seconds=retry_delay_seconds,
                sleep=sleep,
            )
            if not controller_result.reachable:
                aborted = True
                abort_reason = controller_result.detail
                logger.error(
                    "Networking Engine halted (REQ-NET-014): %s", abort_reason
                )

        # -- REQ-NET-010: Proxmox cluster reachability ----------------------
        cluster_checked = False
        cluster_result = HostReachabilityResult(
            reachable=False,
            detail="Proxmox cluster reachability was not checked.",
            host=cluster_config.primary_node_host if cluster_config else "",
            port=cluster_config.api_port if cluster_config else 0,
        )
        if (
            not aborted
            and cluster_config is not None
            and cluster_config.primary_node_host
        ):
            cluster_checked = True
            cluster_result = self._cluster_checker.check(
                cluster_config.primary_node_host,
                cluster_config.api_port,
                timeout_seconds=float(cluster_config.reachability_timeout_seconds),
                retry_count=retry_count,
                retry_delay_seconds=retry_delay_seconds,
                sleep=sleep,
            )
            if not cluster_result.reachable:
                aborted = True
                abort_reason = cluster_result.detail
                logger.error(
                    "Networking Engine halted (REQ-NET-014): %s", abort_reason
                )

        completed_at = datetime.now(UTC)

        if aborted:
            reason = abort_reason or "Unknown networking failure."
            self._publish(lambda: ConnectivityTestFailedEvent(reason=reason))
        else:
            self._publish(lambda: ConnectivityTestPassedEvent())

        diagnostics = NetworkDiagnostics(
            started_at=started_at,
            completed_at=completed_at,
            ethernet_connected=ethernet_result.connected,
            ethernet_detail=ethernet_result.detail,
            ip_assignment_method=config.ip_assignment_method,
            ip_assignment_succeeded=assignment_result.succeeded,
            ip_assignment_detail=assignment_result.detail,
            assigned_ip_addresses=assignment_result.assigned_ip_addresses,
            gateway_checked=gateway_checked,
            gateway_reachable=gateway_result.reachable,
            gateway_detail=gateway_result.detail,
            dns_checked=dns_checked,
            dns_resolved=dns_result.resolved,
            dns_detail=dns_result.detail,
            controller_reachable=controller_result.reachable,
            controller_detail=controller_result.detail,
            cluster_checked=cluster_checked,
            cluster_reachable=cluster_result.reachable,
            cluster_detail=cluster_result.detail,
            aborted=aborted,
            abort_reason=abort_reason,
        )
        self._last_diagnostics = diagnostics

        logger.info("Networking Engine finished: %s", diagnostics.status_message)

        return diagnostics

    def attempt_recovery(
        self,
        config: NetworkConfig,
        *,
        controller_config: ControllerConfig,
        cluster_config: ClusterConfig | None = None,
        max_attempts: int = 3,
        retry_count: int = NETWORK_RETRY_COUNT,
        retry_delay_seconds: float = NETWORK_RETRY_DELAY_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> NetworkDiagnostics:
        """
        REQ-NET-011: "if network connectivity is lost during
        provisioning, Aquila shall pause deployment and attempt
        recovery when practical."

        A synchronous retry-with-backoff loop -- not a background
        thread -- matching every other retry mechanism already in this
        codebase (no async/threading precedent exists anywhere else in
        Aquila). Re-runs the full :meth:`establish_connectivity`
        sequence up to ``max_attempts`` times.

        REQ-NET-012 ("preserve diagnostic information"): the final
        attempt's ``NetworkDiagnostics`` is always returned, whether or
        not it ultimately succeeded -- this method never raises on
        exhausted recovery, since the decision to actually halt (and
        how) belongs to the caller (see this module's "Ownership
        boundary" docstring).
        """

        attempts = max(1, max_attempts)

        diagnostics = self.establish_connectivity(
            config,
            controller_config=controller_config,
            cluster_config=cluster_config,
            retry_count=retry_count,
            retry_delay_seconds=retry_delay_seconds,
            sleep=sleep,
        )

        attempt = 1
        while not diagnostics.overall_ok and attempt < attempts:
            attempt += 1
            logger.warning(
                "Networking Engine: attempting connectivity recovery "
                "(attempt %d/%d) after: %s",
                attempt,
                attempts,
                diagnostics.abort_reason,
            )
            sleep(retry_delay_seconds)
            diagnostics = self.establish_connectivity(
                config,
                controller_config=controller_config,
                cluster_config=cluster_config,
                retry_count=retry_count,
                retry_delay_seconds=retry_delay_seconds,
                sleep=sleep,
            )

        final_diagnostics = replace(
            diagnostics, recovered_after_attempts=attempt - 1
        )
        self._last_diagnostics = final_diagnostics

        if final_diagnostics.overall_ok and attempt > 1:
            logger.info(
                "Networking Engine: connectivity recovered after %d "
                "attempt(s).",
                attempt - 1,
            )
        elif not final_diagnostics.overall_ok:
            # REQ-NET-012: communication could not be restored --
            # diagnostic information (``final_diagnostics``) is
            # preserved for the caller to act on; this module does not
            # itself decide to "terminate provisioning" (GP-004).
            logger.error(
                "Networking Engine: connectivity could not be restored "
                "after %d attempt(s): %s",
                attempts,
                final_diagnostics.abort_reason,
            )

        return final_diagnostics

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _acquire_and_verify_address(
        self,
        config: NetworkConfig,
        *,
        adapter: NetworkAdapter | None,
        aborted: bool,
        retry_count: int,
        retry_delay_seconds: float,
        sleep: Callable[[float], None],
    ) -> AddressAssignmentResult:
        if aborted or adapter is None:
            return AddressAssignmentResult(
                method=config.ip_assignment_method,
                interface_name=adapter.name if adapter is not None else "",
                succeeded=False,
                detail=(
                    "IP address assignment was not attempted."
                    if aborted
                    else "No Ethernet adapter was available for IP "
                    "address assignment."
                ),
            )

        try:
            result = self._address_assigner.assign(config, adapter=adapter)
        except NetworkingError as exc:
            detail = str(exc)
            logger.error("IP address assignment failed: %s", detail)
            self._publish(
                lambda: IPConfigurationFailedEvent(
                    interface=adapter.name, reason=detail
                )
            )
            return AddressAssignmentResult(
                method=config.ip_assignment_method,
                interface_name=adapter.name,
                succeeded=False,
                detail=detail,
            )

        if not result.succeeded:
            self._publish(
                lambda: IPConfigurationFailedEvent(
                    interface=adapter.name, reason=result.detail
                )
            )
            return result

        verify_result = self._address_assigner.verify_assignment(
            adapter.name,
            retry_count=retry_count,
            retry_delay_seconds=retry_delay_seconds,
            sleep=sleep,
        )
        if verify_result.succeeded:
            self._publish(
                lambda: IPAddressAssignedEvent(
                    interface=adapter.name,
                    ip_address=(
                        verify_result.assigned_ip_addresses[0]
                        if verify_result.assigned_ip_addresses
                        else ""
                    ),
                    assignment=config.ip_assignment_method,
                )
            )
        else:
            self._publish(
                lambda: IPConfigurationFailedEvent(
                    interface=adapter.name, reason=verify_result.detail
                )
            )

        return verify_result

    def _publish(self, build_event: Callable[[], Any]) -> None:
        if self._event_bus is None:
            return

        try:
            self._event_bus.publish(build_event())
        except Exception:  # pragma: no cover - event delivery is best-effort
            logger.debug("Failed to publish networking event.", exc_info=True)


__all__ = ["NetworkDiagnostics", "NetworkManager"]
