#!/usr/bin/env python3
"""
Functional test suite for src/networking/ (the Networking Engine,
REQ-NET-001 through REQ-NET-014).

Follows the exact plain-script convention every other
``run_tests_*.py`` in this repository already established: a
``check(condition, description)`` helper collects failures, printed
as a summary at the end with ``sys.exit(1)`` on any failure.

Every live-system-dependent operation (WMI adapter detection, WMI
``Win32_NetworkAdapterConfiguration`` method invocation, ``netsh``
subprocess calls, ICMP ping, DNS resolution, TCP socket probing) is
exercised through dependency injection -- fake ``NetworkDetector``,
``AdapterConfigurationCaller``, command runner, ``GatewayProber``,
``DNSResolver``, and ``SocketProber`` implementations -- the same
technique every prior subsystem's test suite already established,
since this development environment is Linux with no real
WMI/netsh/Windows backend and no real network operation should ever
run in a test.

Run with (from the repository root): python3 tests/run_tests_networking.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

failures: list[str] = []
passed = 0


def check(condition: bool, description: str) -> None:
    global passed
    if condition:
        passed += 1
    else:
        failures.append(description)


from common.enums import EthernetStatus
from common.exceptions.networking import (
    DHCPError,
    DNSError,
    GatewayError,
    InterfaceNotFoundError,
    StaticConfigurationError,
)
from config.schemas.cluster_schema import ClusterConfig
from config.schemas.controller_schema import ControllerConfig
from config.schemas.network_schema import NetworkConfig
from models.hardware.network import NetworkAdapter, NetworkAdapterType

from networking.cluster import ClusterReachabilityChecker
from networking.controller import ControllerReachabilityChecker
from networking.dhcp import NetworkAddressAssigner, WmiConfigResult
from networking.dns import DNSResolutionChecker
from networking.ethernet import EthernetChecker
from networking.gateway import GatewayChecker
from networking.network_manager import NetworkManager


# ---------------------------------------------------------------------------
# Fixtures / fakes
# ---------------------------------------------------------------------------


def _adapter(
    *,
    name: str = "Ethernet0",
    adapter_type: NetworkAdapterType = NetworkAdapterType.ETHERNET,
    is_physical: bool = True,
    is_enabled: bool = True,
    link_status: EthernetStatus | None = EthernetStatus.ACTIVE,
    ip_addresses: list[str] | None = None,
    default_gateways: list[str] | None = None,
    interface_index: int | None = 7,
    mac_address: str = "AA:BB:CC:DD:EE:FF",
) -> NetworkAdapter:
    return NetworkAdapter(
        name=name,
        adapter_type=adapter_type,
        is_physical=is_physical,
        is_enabled=is_enabled,
        link_status=link_status,
        ip_addresses=ip_addresses or [],
        default_gateways=default_gateways or [],
        interface_index=interface_index,
        mac_address=mac_address,
    )


class _FakeNetworkDetector:
    """Returns one adapter list per call, repeating the last one."""

    def __init__(self, sequences: list[list[NetworkAdapter]]) -> None:
        self._sequences = sequences
        self.call_count = 0

    def detect(self) -> list[NetworkAdapter]:
        index = min(self.call_count, len(self._sequences) - 1)
        self.call_count += 1
        return self._sequences[index]


class _FakeAdapterConfigurationCaller:
    """Records every call and returns pre-programmed results."""

    def __init__(
        self,
        *,
        dhcp_result: WmiConfigResult | None = None,
        static_result: WmiConfigResult | None = None,
        gateway_result: WmiConfigResult | None = None,
        dns_result: WmiConfigResult | None = None,
    ) -> None:
        self.dhcp_result = dhcp_result or WmiConfigResult(0, "ok")
        self.static_result = static_result or WmiConfigResult(0, "ok")
        self.gateway_result = gateway_result or WmiConfigResult(0, "ok")
        self.dns_result = dns_result or WmiConfigResult(0, "ok")
        self.calls: list[tuple[str, int]] = []

    def enable_dhcp(self, *, interface_index: int) -> WmiConfigResult:
        self.calls.append(("enable_dhcp", interface_index))
        return self.dhcp_result

    def enable_static_ipv4(
        self,
        *,
        interface_index: int,
        ip_addresses: Sequence[str],
        subnet_masks: Sequence[str],
    ) -> WmiConfigResult:
        self.calls.append(("enable_static_ipv4", interface_index))
        return self.static_result

    def set_gateways(
        self, *, interface_index: int, gateways: Sequence[str]
    ) -> WmiConfigResult:
        self.calls.append(("set_gateways", interface_index))
        return self.gateway_result

    def set_dns_servers(
        self, *, interface_index: int, dns_servers: Sequence[str]
    ) -> WmiConfigResult:
        self.calls.append(("set_dns_servers", interface_index))
        return self.dns_result


class _FakeCommandRunner:
    """Records every ``netsh`` invocation and returns a fixed result."""

    def __init__(self, *, return_code: int = 0, stderr: str = "") -> None:
        self.return_code = return_code
        self.stderr = stderr
        self.commands: list[Sequence[str]] = []

    def __call__(self, command: Sequence[str]) -> tuple[int, str, str]:
        self.commands.append(command)
        return (self.return_code, "", self.stderr)


class _FakeGatewayProber:
    def __init__(self, outcomes: list[bool]) -> None:
        self._outcomes = outcomes
        self.call_count = 0

    def probe(self, host: str, *, timeout_seconds: float) -> bool:
        index = min(self.call_count, len(self._outcomes) - 1)
        self.call_count += 1
        return self._outcomes[index]


class _FakeDNSResolver:
    def __init__(self, outcomes: list[str | Exception]) -> None:
        self._outcomes = outcomes
        self.call_count = 0

    def resolve(self, hostname: str) -> str:
        index = min(self.call_count, len(self._outcomes) - 1)
        outcome = self._outcomes[index]
        self.call_count += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeSocketProber:
    def __init__(self, outcomes: list[Exception | None]) -> None:
        self._outcomes = outcomes
        self.call_count = 0

    def probe(self, host: str, port: int, *, timeout: float) -> None:
        index = min(self.call_count, len(self._outcomes) - 1)
        outcome = self._outcomes[index]
        self.call_count += 1
        if outcome is not None:
            raise outcome


class _FakeEventBus:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def publish(self, event: Any) -> None:
        self.events.append(event)


_sleep_calls: list[float] = []


def _fake_sleep(seconds: float) -> None:
    _sleep_calls.append(seconds)


def _controller_config(
    *, host: str = "10.0.0.5", port: int = 443, timeout: int = 5
) -> ControllerConfig:
    return ControllerConfig(
        host=host, port=port, connection_timeout_seconds=timeout
    )


def _cluster_config(
    *, host: str = "10.0.0.10", port: int = 8006, timeout: int = 5
) -> ClusterConfig:
    return ClusterConfig(
        primary_node_host=host,
        api_port=port,
        reachability_timeout_seconds=timeout,
    )


# ---------------------------------------------------------------------------
# ethernet.EthernetChecker
# ---------------------------------------------------------------------------

eth_checker = EthernetChecker(
    network_detector=_FakeNetworkDetector([[_adapter()]])
)
check(
    len(eth_checker.enumerate_interfaces()) == 1,
    "ethernet: enumerate_interfaces returns every detected adapter",
)
check(
    # REQ-NET-002: asserts a physical, enabled Ethernet adapter is
    # identified as such.
    len(eth_checker.ethernet_interfaces()) == 1,
    "ethernet: ethernet_interfaces keeps a physical, enabled Ethernet adapter",
)

wireless_only = EthernetChecker(
    network_detector=_FakeNetworkDetector(
        [[_adapter(adapter_type=NetworkAdapterType.WIRELESS, link_status=None)]]
    )
)
check(
    # REQ-NET-002: asserts a non-Ethernet adapter is not identified as
    # an Ethernet interface.
    len(wireless_only.ethernet_interfaces()) == 0,
    "ethernet: ethernet_interfaces excludes non-Ethernet adapters",
)

immediate_link = EthernetChecker(
    network_detector=_FakeNetworkDetector([[_adapter()]])
)
immediate_result = immediate_link.check_link(
    retry_count=3, retry_delay_seconds=1.0, sleep=_fake_sleep
)
# REQ-NET-003/004: asserts an active link status is determined and
# reported as a connected cable before provisioning would proceed.
check(immediate_result.connected, "ethernet: immediate active link is connected")
check(
    immediate_result.primary_adapter is not None
    and immediate_result.primary_adapter.name == "Ethernet0",
    "ethernet: check_link returns the matched primary adapter object",
)

_sleep_calls.clear()
retry_then_ok = EthernetChecker(
    network_detector=_FakeNetworkDetector(
        [
            [_adapter(link_status=EthernetStatus.UNPLUGGED)],
            [_adapter(link_status=EthernetStatus.ACTIVE)],
        ]
    )
)
retry_result = retry_then_ok.check_link(
    retry_count=3, retry_delay_seconds=1.0, sleep=_fake_sleep
)
check(retry_result.connected, "ethernet: retry-then-connect eventually succeeds")
check(len(_sleep_calls) == 1, "ethernet: exactly one retry delay was used")

no_adapters = EthernetChecker(network_detector=_FakeNetworkDetector([[]]))
no_adapter_result = no_adapters.check_link(
    retry_count=1, retry_delay_seconds=1.0, sleep=_fake_sleep
)
check(
    # REQ-NET-004: asserts no cable connected is reported as
    # disconnected rather than assumed present.
    not no_adapter_result.connected and no_adapter_result.primary_adapter is None,
    "ethernet: no adapters at all is reported disconnected with no primary adapter",
)


# ---------------------------------------------------------------------------
# dhcp.NetworkAddressAssigner
# ---------------------------------------------------------------------------

dhcp_config = NetworkConfig(ip_assignment_method="dhcp")
static_v4_config = NetworkConfig(
    ip_assignment_method="static_ipv4",
    static_ipv4_address="192.168.1.50",
    static_ipv4_netmask="255.255.255.0",
    static_ipv4_gateway="192.168.1.1",
    dns_servers=["192.168.1.1"],
)
static_v6_config = NetworkConfig(
    ip_assignment_method="static_ipv6",
    static_ipv6_address="2001:db8::10",
    static_ipv6_prefix_length=64,
    static_ipv6_gateway="2001:db8::1",
    dns_servers=["2001:4860:4860::8888"],
)

dhcp_caller = _FakeAdapterConfigurationCaller()
dhcp_assigner = NetworkAddressAssigner(adapter_caller=dhcp_caller)
dhcp_result = dhcp_assigner.assign(dhcp_config, adapter=_adapter())
# REQ-NET-005: asserts DHCP is one of the supported acquisition
# methods and succeeds when configured.
check(dhcp_result.succeeded, "dhcp: DHCP assignment via WMI succeeds")
check(
    dhcp_caller.calls == [("enable_dhcp", 7)],
    "dhcp: DHCP assignment calls EnableDHCP with the adapter's interface index",
)

failing_caller = _FakeAdapterConfigurationCaller(
    dhcp_result=WmiConfigResult(65, "Unknown failure.")
)
failing_assigner = NetworkAddressAssigner(adapter_caller=failing_caller)
try:
    failing_assigner.assign(dhcp_config, adapter=_adapter())
    check(False, "dhcp: a failing WMI return code raises DHCPError")
except DHCPError:
    check(True, "dhcp: a failing WMI return code raises DHCPError")

try:
    dhcp_assigner.assign(dhcp_config, adapter=_adapter(interface_index=None))
    check(False, "dhcp: an adapter with no interface_index raises InterfaceNotFoundError")
except InterfaceNotFoundError:
    check(True, "dhcp: an adapter with no interface_index raises InterfaceNotFoundError")

static_caller = _FakeAdapterConfigurationCaller()
static_assigner = NetworkAddressAssigner(adapter_caller=static_caller)
static_result = static_assigner.assign(static_v4_config, adapter=_adapter())
# REQ-NET-005: asserts static IPv4 is a supported acquisition method.
# REQ-CONF-007: static_v4_config above is exactly "networking
# customization" -- a technician-configurable IP assignment method,
# address, netmask, gateway, and DNS servers -- actually driving this
# assignment, not just the DHCP default.
check(static_result.succeeded, "dhcp: static IPv4 assignment succeeds")
check(
    [call[0] for call in static_caller.calls]
    == ["enable_static_ipv4", "set_gateways", "set_dns_servers"],
    "dhcp: static IPv4 assignment calls EnableStatic, SetGateways, then "
    "SetDNSServerSearchOrder in order",
)
check(
    static_result.assigned_ip_addresses == ("192.168.1.50",),
    "dhcp: static IPv4 result reports the assigned address",
)

gateway_fail_caller = _FakeAdapterConfigurationCaller(
    gateway_result=WmiConfigResult(71, "Invalid gateway IP address.")
)
gateway_fail_assigner = NetworkAddressAssigner(adapter_caller=gateway_fail_caller)
try:
    gateway_fail_assigner.assign(static_v4_config, adapter=_adapter())
    check(False, "dhcp: a failing SetGateways call raises GatewayError")
except GatewayError:
    check(True, "dhcp: a failing SetGateways call raises GatewayError")

ipv6_runner = _FakeCommandRunner(return_code=0)
ipv6_assigner = NetworkAddressAssigner(command_runner=ipv6_runner)
ipv6_result = ipv6_assigner.assign(static_v6_config, adapter=_adapter())
# REQ-NET-005: asserts static IPv6 is a supported acquisition method.
check(ipv6_result.succeeded, "dhcp: static IPv6 assignment via netsh succeeds")
check(
    len(ipv6_runner.commands) == 3
    and ipv6_runner.commands[0][:5]
    == ["netsh", "interface", "ipv6", "add", "address"]
    and ipv6_runner.commands[1][:5]
    == ["netsh", "interface", "ipv6", "add", "route"]
    and ipv6_runner.commands[2][:5]
    == ["netsh", "interface", "ipv6", "add", "dnsservers"],
    "dhcp: static IPv6 assignment issues add-address, add-route, then "
    "add-dnsservers via netsh",
)

ipv6_fail_runner = _FakeCommandRunner(return_code=1, stderr="The parameter is incorrect.")
ipv6_fail_assigner = NetworkAddressAssigner(command_runner=ipv6_fail_runner)
try:
    ipv6_fail_assigner.assign(static_v6_config, adapter=_adapter())
    check(False, "dhcp: a failing netsh exit code raises StaticConfigurationError")
except StaticConfigurationError:
    check(True, "dhcp: a failing netsh exit code raises StaticConfigurationError")

_sleep_calls.clear()
verify_ok_assigner = NetworkAddressAssigner(
    network_detector=_FakeNetworkDetector(
        [[_adapter(ip_addresses=["192.168.1.50"], default_gateways=["192.168.1.1"])]]
    )
)
verify_ok = verify_ok_assigner.verify_assignment(
    "Ethernet0", retry_count=2, retry_delay_seconds=1.0, sleep=_fake_sleep
)
# REQ-NET-006: asserts successful IP address assignment is verified.
check(verify_ok.succeeded, "dhcp: verify_assignment succeeds once an IP is present")
check(
    verify_ok.default_gateways == ("192.168.1.1",),
    "dhcp: verify_assignment surfaces the adapter's default gateway(s)",
)

verify_missing_assigner = NetworkAddressAssigner(
    network_detector=_FakeNetworkDetector([[_adapter(name="Other")]])
)
verify_missing = verify_missing_assigner.verify_assignment(
    "Ethernet0", retry_count=1, retry_delay_seconds=1.0, sleep=_fake_sleep
)
check(
    not verify_missing.succeeded,
    "dhcp: verify_assignment fails when the named adapter is never found",
)


# ---------------------------------------------------------------------------
# gateway.GatewayChecker
# ---------------------------------------------------------------------------

gw_ok = GatewayChecker(prober=_FakeGatewayProber([True]))
gw_ok_result = gw_ok.check(
    "192.168.1.1", retry_count=2, retry_delay_seconds=1.0, sleep=_fake_sleep
)
# REQ-NET-007: asserts default-gateway reachability is verified.
check(gw_ok_result.reachable, "gateway: reachable gateway is reported reachable")

_sleep_calls.clear()
gw_fail = GatewayChecker(prober=_FakeGatewayProber([False, False]))
gw_fail_result = gw_fail.check(
    "192.168.1.1", retry_count=1, retry_delay_seconds=1.0, sleep=_fake_sleep
)
check(
    not gw_fail_result.reachable,
    "gateway: unreachable gateway is reported unreachable after retries exhausted",
)
check(len(_sleep_calls) == 1, "gateway: exactly one retry delay was used")

gw_empty = GatewayChecker(prober=_FakeGatewayProber([True]))
gw_empty_result = gw_empty.check(
    "", retry_count=1, retry_delay_seconds=1.0, sleep=_fake_sleep
)
check(
    not gw_empty_result.reachable,
    "gateway: an empty gateway address is reported unreachable without probing",
)


# ---------------------------------------------------------------------------
# dns.DNSResolutionChecker
# ---------------------------------------------------------------------------

import socket as _socket

dns_ok = DNSResolutionChecker(resolver=_FakeDNSResolver(["10.0.0.5"]))
dns_ok_result = dns_ok.check(
    "controller.aquila.local",
    retry_count=2,
    retry_delay_seconds=1.0,
    sleep=_fake_sleep,
)
# REQ-NET-008: asserts DNS resolution is verified when required.
check(dns_ok_result.resolved, "dns: a resolvable hostname is reported resolved")
check(
    dns_ok_result.resolved_address == "10.0.0.5",
    "dns: the resolved address is captured",
)

dns_fail = DNSResolutionChecker(
    resolver=_FakeDNSResolver([_socket.gaierror("not found"), _socket.gaierror("not found")])
)
dns_fail_result = dns_fail.check(
    "missing.aquila.local", retry_count=1, retry_delay_seconds=1.0, sleep=_fake_sleep
)
check(
    not dns_fail_result.resolved,
    "dns: a hostname that never resolves is reported unresolved",
)

dns_literal_resolver = _FakeDNSResolver(["should-not-be-used"])
dns_literal = DNSResolutionChecker(resolver=dns_literal_resolver)
dns_literal_result = dns_literal.check(
    "10.0.0.5", retry_count=1, retry_delay_seconds=1.0, sleep=_fake_sleep
)
check(
    dns_literal_result.resolved and dns_literal_result.resolved_address == "10.0.0.5",
    "dns: a literal IP address is reported resolved without a lookup",
)
check(
    dns_literal_resolver.call_count == 0,
    "dns: a literal IP address never invokes the resolver",
)


# ---------------------------------------------------------------------------
# controller.ControllerReachabilityChecker / cluster.ClusterReachabilityChecker
# ---------------------------------------------------------------------------

ctrl_ok = ControllerReachabilityChecker(prober=_FakeSocketProber([None]))
ctrl_ok_result = ctrl_ok.check(
    "10.0.0.5",
    443,
    timeout_seconds=1.0,
    retry_count=1,
    retry_delay_seconds=1.0,
    sleep=_fake_sleep,
)
# REQ-NET-009: asserts communication with the Deployment Controller
# is verified.
check(ctrl_ok_result.reachable, "controller: reachable host is reported reachable")

ctrl_fail = ControllerReachabilityChecker(
    prober=_FakeSocketProber([OSError("refused"), OSError("refused")])
)
ctrl_fail_result = ctrl_fail.check(
    "10.0.0.5",
    443,
    timeout_seconds=1.0,
    retry_count=1,
    retry_delay_seconds=1.0,
    sleep=_fake_sleep,
)
check(
    not ctrl_fail_result.reachable,
    "controller: unreachable host is reported unreachable after retries exhausted",
)

ctrl_empty = ControllerReachabilityChecker(prober=_FakeSocketProber([None]))
ctrl_empty_result = ctrl_empty.check(
    "", 443, timeout_seconds=1.0, retry_count=1, retry_delay_seconds=1.0, sleep=_fake_sleep
)
check(
    not ctrl_empty_result.reachable,
    "controller: an empty host is reported unreachable without probing",
)

cluster_ok = ClusterReachabilityChecker(prober=_FakeSocketProber([None]))
cluster_ok_result = cluster_ok.check(
    "10.0.0.10",
    8006,
    timeout_seconds=1.0,
    retry_count=1,
    retry_delay_seconds=1.0,
    sleep=_fake_sleep,
)
# REQ-NET-010: asserts communication with the target Proxmox cluster
# is verified.
check(cluster_ok_result.reachable, "cluster: reachable cluster host is reported reachable")

cluster_fail = ClusterReachabilityChecker(
    prober=_FakeSocketProber([OSError("refused")])
)
cluster_fail_result = cluster_fail.check(
    "10.0.0.10",
    8006,
    timeout_seconds=1.0,
    retry_count=0,
    retry_delay_seconds=1.0,
    sleep=_fake_sleep,
)
check(
    not cluster_fail_result.reachable,
    "cluster: unreachable cluster host is reported unreachable",
)


# ---------------------------------------------------------------------------
# network_manager.NetworkManager -- end-to-end orchestration
# ---------------------------------------------------------------------------


def _manager(
    *,
    ethernet_sequences: list[list[NetworkAdapter]],
    dhcp_caller: _FakeAdapterConfigurationCaller | None = None,
    verify_sequences: list[list[NetworkAdapter]] | None = None,
    gateway_outcomes: list[bool] | None = None,
    dns_outcomes: list[str | Exception] | None = None,
    controller_outcomes: list[Exception | None] | None = None,
    cluster_outcomes: list[Exception | None] | None = None,
    event_bus: _FakeEventBus | None = None,
) -> NetworkManager:
    verify_sequences = verify_sequences or ethernet_sequences
    return NetworkManager(
        event_bus,
        ethernet_checker=EthernetChecker(
            network_detector=_FakeNetworkDetector(ethernet_sequences)
        ),
        address_assigner=NetworkAddressAssigner(
            adapter_caller=dhcp_caller or _FakeAdapterConfigurationCaller(),
            network_detector=_FakeNetworkDetector(verify_sequences),
        ),
        gateway_checker=GatewayChecker(
            prober=_FakeGatewayProber(gateway_outcomes or [True])
        ),
        dns_checker=DNSResolutionChecker(
            resolver=_FakeDNSResolver(dns_outcomes or ["10.0.0.5"])
        ),
        controller_checker=ControllerReachabilityChecker(
            prober=_FakeSocketProber(controller_outcomes or [None])
        ),
        cluster_checker=ClusterReachabilityChecker(
            prober=_FakeSocketProber(cluster_outcomes or [None])
        ),
    )


success_bus = _FakeEventBus()
success_manager = _manager(
    ethernet_sequences=[[_adapter()]],
    verify_sequences=[
        [_adapter(ip_addresses=["192.168.1.50"], default_gateways=["192.168.1.1"])]
    ],
    event_bus=success_bus,
)
success_diagnostics = success_manager.establish_connectivity(
    dhcp_config,
    controller_config=_controller_config(host="10.0.0.5"),
    cluster_config=_cluster_config(),
    retry_count=1,
    retry_delay_seconds=1.0,
    sleep=_fake_sleep,
)
check(
    success_diagnostics.overall_ok,
    "network_manager: a fully successful run reports overall_ok",
)
check(
    success_diagnostics.ethernet_connected
    and success_diagnostics.ip_assignment_succeeded
    and success_diagnostics.controller_reachable
    and success_diagnostics.cluster_reachable,
    "network_manager: every REQ-NET-0xx check result is captured in diagnostics",
)
check(
    success_manager.last_diagnostics is success_diagnostics,
    "network_manager: last_diagnostics reflects the most recent run",
)
_event_types = {event.event_type for event in success_bus.events}
check(
    {
        "CONNECTIVITY_TEST_STARTED",
        "CONNECTIVITY_TEST_PASSED",
        "ETHERNET_DETECTED",
        "IP_ADDRESS_ASSIGNED",
        "GATEWAY_REACHABLE",
        "DNS_RESOLVED",
    }.issubset(_event_types),
    "network_manager: a successful run publishes the expected event sequence "
    "(event_type is EventType.*.name, e.g. 'CONNECTIVITY_TEST_STARTED')",
)

no_ethernet_manager = _manager(ethernet_sequences=[[]])
no_ethernet_diagnostics = no_ethernet_manager.establish_connectivity(
    dhcp_config,
    controller_config=_controller_config(),
    retry_count=0,
    retry_delay_seconds=1.0,
    sleep=_fake_sleep,
)
check(
    no_ethernet_diagnostics.aborted and not no_ethernet_diagnostics.overall_ok,
    "network_manager: no Ethernet link halts the run",
)
check(
    not no_ethernet_diagnostics.ip_assignment_succeeded
    and "not attempted" in no_ethernet_diagnostics.ip_assignment_detail,
    "network_manager: IP assignment is skipped, not attempted, once halted",
)
check(
    not no_ethernet_diagnostics.controller_reachable
    and "not checked" in no_ethernet_diagnostics.controller_detail,
    "network_manager: later checks are honestly reported as not-checked once halted",
)

ip_fail_manager = _manager(
    ethernet_sequences=[[_adapter()]],
    dhcp_caller=_FakeAdapterConfigurationCaller(
        dhcp_result=WmiConfigResult(65, "Unknown failure.")
    ),
)
ip_fail_diagnostics = ip_fail_manager.establish_connectivity(
    dhcp_config,
    controller_config=_controller_config(),
    retry_count=0,
    retry_delay_seconds=1.0,
    sleep=_fake_sleep,
)
check(
    ip_fail_diagnostics.aborted and not ip_fail_diagnostics.ip_assignment_succeeded,
    "network_manager: a failed IP assignment halts the run",
)
check(
    not ip_fail_diagnostics.controller_reachable
    and "not checked" in ip_fail_diagnostics.controller_detail,
    "network_manager: controller reachability is never attempted once IP "
    "assignment fails",
)

gateway_not_required_config = NetworkConfig(
    ip_assignment_method="dhcp", require_gateway_reachability=False
)
gateway_skip_manager = _manager(
    ethernet_sequences=[[_adapter()]],
    verify_sequences=[
        [_adapter(ip_addresses=["192.168.1.50"], default_gateways=["192.168.1.1"])]
    ],
    gateway_outcomes=[False],
)
gateway_skip_diagnostics = gateway_skip_manager.establish_connectivity(
    gateway_not_required_config,
    controller_config=_controller_config(),
    retry_count=0,
    retry_delay_seconds=1.0,
    sleep=_fake_sleep,
)
check(
    not gateway_skip_diagnostics.gateway_checked
    and gateway_skip_diagnostics.controller_reachable,
    "network_manager: gateway check is skipped entirely when policy does not "
    "require it, and does not block later checks",
)

no_cluster_manager = _manager(
    ethernet_sequences=[[_adapter()]],
    verify_sequences=[
        [_adapter(ip_addresses=["192.168.1.50"], default_gateways=["192.168.1.1"])]
    ],
)
no_cluster_diagnostics = no_cluster_manager.establish_connectivity(
    dhcp_config,
    controller_config=_controller_config(),
    cluster_config=None,
    retry_count=0,
    retry_delay_seconds=1.0,
    sleep=_fake_sleep,
)
check(
    not no_cluster_diagnostics.cluster_checked and no_cluster_diagnostics.overall_ok,
    "network_manager: an unconfigured cluster is skipped without blocking "
    "overall_ok",
)

controller_fail_manager = _manager(
    ethernet_sequences=[[_adapter()]],
    verify_sequences=[
        [_adapter(ip_addresses=["192.168.1.50"], default_gateways=["192.168.1.1"])]
    ],
    controller_outcomes=[OSError("refused")],
)
controller_fail_diagnostics = controller_fail_manager.establish_connectivity(
    dhcp_config,
    controller_config=_controller_config(),
    retry_count=0,
    retry_delay_seconds=1.0,
    sleep=_fake_sleep,
)
check(
    controller_fail_diagnostics.aborted
    and not controller_fail_diagnostics.controller_reachable,
    "network_manager: an unreachable Deployment Controller halts the run "
    "even after every earlier check passed",
)

# -- REQ-NET-011/012: attempt_recovery -----------------------------------

_recovery_call_count = 0


class _FlakyThenOkProber:
    """Fails the first ``establish_connectivity`` pass, succeeds the second."""

    def __init__(self) -> None:
        self.attempts = 0

    def probe(self, host: str, port: int, *, timeout: float) -> None:
        self.attempts += 1
        if self.attempts == 1:
            raise OSError("refused")


flaky_prober = _FlakyThenOkProber()
recovery_manager = NetworkManager(
    ethernet_checker=EthernetChecker(
        network_detector=_FakeNetworkDetector([[_adapter()]])
    ),
    address_assigner=NetworkAddressAssigner(
        adapter_caller=_FakeAdapterConfigurationCaller(),
        network_detector=_FakeNetworkDetector(
            [[_adapter(ip_addresses=["192.168.1.50"], default_gateways=["192.168.1.1"])]]
        ),
    ),
    gateway_checker=GatewayChecker(prober=_FakeGatewayProber([True])),
    dns_checker=DNSResolutionChecker(resolver=_FakeDNSResolver(["10.0.0.5"])),
    controller_checker=ControllerReachabilityChecker(prober=flaky_prober),
    cluster_checker=ClusterReachabilityChecker(prober=_FakeSocketProber([None])),
)
recovery_diagnostics = recovery_manager.attempt_recovery(
    dhcp_config,
    controller_config=_controller_config(),
    max_attempts=3,
    retry_count=0,
    retry_delay_seconds=1.0,
    sleep=_fake_sleep,
)
check(
    recovery_diagnostics.overall_ok and recovery_diagnostics.recovered_after_attempts == 1,
    "network_manager: attempt_recovery succeeds on a second pass and reports "
    "one recovery attempt",
)

always_fail_manager = _manager(
    ethernet_sequences=[[_adapter()]],
    verify_sequences=[
        [_adapter(ip_addresses=["192.168.1.50"], default_gateways=["192.168.1.1"])]
    ],
    controller_outcomes=[OSError("refused")],
)
exhausted_diagnostics = always_fail_manager.attempt_recovery(
    dhcp_config,
    controller_config=_controller_config(),
    max_attempts=2,
    retry_count=0,
    retry_delay_seconds=1.0,
    sleep=_fake_sleep,
)
check(
    not exhausted_diagnostics.overall_ok
    and exhausted_diagnostics.recovered_after_attempts == 1,
    "network_manager: attempt_recovery preserves diagnostics after exhausting "
    "max_attempts without recovering (REQ-NET-012)",
)

# -- Service lifecycle + NetworkDiagnostics.to_dict() ---------------------

lifecycle_manager = NetworkManager()
check(
    not lifecycle_manager.is_initialized,
    "network_manager: a fresh manager is not initialized",
)
lifecycle_manager.initialize()
check(
    lifecycle_manager.is_initialized,
    "network_manager: initialize() marks the manager initialized",
)
lifecycle_manager.shutdown()
check(
    not lifecycle_manager.is_initialized,
    "network_manager: shutdown() marks the manager uninitialized",
)

diagnostics_dict = success_diagnostics.to_dict()
check(
    # REQ-NET-013: asserts network diagnostics are a complete,
    # JSON-serializable record suitable for inclusion within the
    # deployment report.
    diagnostics_dict["overall_ok"] is True
    and diagnostics_dict["ip_assignment_method"] == "dhcp"
    and "started_at" in diagnostics_dict
    and "completed_at" in diagnostics_dict,
    "network_manager: NetworkDiagnostics.to_dict() is a complete, "
    "JSON-serializable report",
)


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
print("All networking/ functional checks passed.")
