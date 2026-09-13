"""
Project Aquila
=============

IP Address Acquisition (DHCP / Static IPv4 / Static IPv6)

Implements REQ-NET-005 ("The Networking Engine shall acquire network
configuration according to deployment policy. Supported methods may
include: DHCP / Static IPv4 / Static IPv6") and REQ-NET-006 ("The
Networking Engine shall verify successful IP address assignment").

Scope note -- deliberate stub-plan deviation, documented per the same
convention ``bootstrap.controller_client`` used in the prior
subsystem: despite this module's stub-plan filename ("dhcp.py"), it
is the authoritative implementation of *all* of REQ-NET-005, not only
its DHCP branch. The original 8-file stub plan (ethernet.py,
cluster.py, controller.py, dhcp.py, dns.py, gateway.py,
network_manager.py, __init__.py) has no separate file for static
IPv4/IPv6 address acquisition, and "dhcp.py" is the closest-fitting
existing stub name for "IP address acquisition" as a whole.

Backends, confirmed via primary-source research before implementation
(no WMI method signature or netsh syntax here was guessed):

* DHCP and static IPv4 are configured through
  ``Win32_NetworkAdapterConfiguration``'s ``EnableDHCP()``,
  ``EnableStatic(IPAddress[], SubnetMask[])``,
  ``SetGateways(DefaultIPGateway[])``, and
  ``SetDNSServerSearchOrder(DNSServerSearchOrder[])`` WMI methods
  (confirmed against Microsoft Learn's
  ``Win32_NetworkAdapterConfiguration`` reference, including the
  shared 0/1=success, 64-100=documented-failure return code range).
* Static IPv6 is configured through ``netsh interface ipv6``, since
  ``Win32_NetworkAdapterConfiguration`` predates IPv6 and none of its
  methods accept an IPv6-shaped parameter (confirmed against the same
  reference). The exact ``add address`` / ``add route`` /
  ``add dnsservers`` syntax used below is confirmed against Microsoft
  Learn's current ``netsh interface`` command reference
  (learn.microsoft.com/windows-server/administration/windows-commands
  /netsh-interface), not the archived Windows Server 2008 copy.

Mutating a live adapter's IP configuration is exactly the kind of WMI
method invocation ``hardware.query_wmi`` refuses to make (REQ-INS-026
restricts that package to read-only SELECT/ASSOCIATORS OF queries).
This module therefore builds its own separate, narrowly-scoped
``AdapterConfigurationCaller`` -- mirroring the exact dual-backend
pattern (``wmi`` package, then raw ``win32com.client`` COM
automation) ``preparation.sanitizer.WmiMethodCaller`` already
established for ``MSFT_Disk.Clear()`` -- rather than reusing or
loosening ``hardware.query_wmi``'s read-only guarantee.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol, Sequence, cast

from common.constants.logging import NETWORK_LOGGER
from common.exceptions.networking import (
    DHCPError,
    DNSError,
    GatewayError,
    InterfaceNotFoundError,
    NetworkingConfigurationError,
    NetworkingError,
    StaticConfigurationError,
)
from config.schemas.network_schema import NetworkConfig
from hardware import is_windows
from hardware.network import NetworkDetector
from models.hardware.network import NetworkAdapter

logger = logging.getLogger(NETWORK_LOGGER)

_WMI_NAMESPACE = r"root\cimv2"

#: ``Win32_NetworkAdapterConfiguration`` method return codes, shared
#: across ``EnableDHCP``, ``EnableStatic``, ``SetGateways``, and
#: ``SetDNSServerSearchOrder`` -- confirmed against Microsoft Learn.
_WMI_RETURN_CODES: dict[int, str] = {
    0: "Successful completion, no reboot required.",
    1: "Successful completion, reboot required.",
    64: "Method not supported on this platform.",
    65: "Unknown failure.",
    66: "Invalid subnet mask.",
    67: "An error occurred while processing an instance that was returned.",
    68: "Invalid input parameter.",
    69: "More than 5 gateways specified.",
    70: "Invalid IP address.",
    71: "Invalid gateway IP address.",
    72: (
        "An error occurred while accessing the registry for the "
        "requested information."
    ),
    73: "Invalid domain name.",
    74: "Invalid host name.",
    75: "No primary/secondary WINS server defined.",
    76: "Invalid file.",
    77: "Invalid system path.",
    78: "File copy failed.",
    79: "Invalid security parameter.",
    80: "Unable to configure the TCP/IP service.",
    81: "Unable to configure the DHCP service.",
    82: "Unable to renew the DHCP lease.",
    83: "Unable to release the DHCP lease.",
    84: "IP is not enabled on the adapter.",
    85: "IPX is not enabled on the adapter.",
    91: "Access denied.",
    92: "Out of memory.",
    93: "Already exists.",
    94: "Path, file, or object not found.",
    97: "Interface is not configurable.",
    100: "DHCP is not enabled on this adapter.",
    2147786788: (
        "General failure -- a write lock could not be acquired; "
        "another process may be modifying the adapter."
    ),
}

_SUCCESS_CODES = frozenset({0, 1})


def _describe(code: int) -> str:
    return _WMI_RETURN_CODES.get(code, f"Unrecognized WMI return code {code}.")


def _run_subprocess(
    command: Sequence[str], *, timeout: float = 30.0
) -> tuple[int, str, str]:
    """
    Run ``netsh`` without a shell and capture its output.

    Deliberately a private helper local to this module rather than a
    reuse of ``hardware.run_process`` -- that helper is documented as
    read-only-only (REQ-INS-026 governs everything in the ``hardware``
    package), and ``netsh interface ipv6 add ...`` is intentionally
    mutating. Keeping this implementation local to ``networking/``
    preserves ``hardware.run_process``'s read-only guarantee for every
    other caller, the same reasoning that kept this module's WMI
    method invocation out of ``hardware.query_wmi``.
    """

    if not is_windows():
        return (
            127,
            "",
            "netsh is only available on Windows; the current platform "
            "is not supported.",
        )

    try:
        process = subprocess.run(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=timeout,
            check=False,
        )
        return (process.returncode, process.stdout, process.stderr)
    except FileNotFoundError as exc:
        return (127, "", str(exc))
    except subprocess.TimeoutExpired:
        return (124, "", "Operation timed out.")
    except (OSError, ValueError) as exc:
        return (126, "", str(exc))


@dataclass(frozen=True, slots=True)
class WmiConfigResult:
    """The outcome of one mutating ``Win32_NetworkAdapterConfiguration`` call."""

    return_code: int
    detail: str

    @property
    def succeeded(self) -> bool:
        return self.return_code in _SUCCESS_CODES


class AdapterConfigurationCaller(Protocol):
    """
    Invokes mutating ``Win32_NetworkAdapterConfiguration`` methods
    against a specific adapter (identified by its WMI ``Index``).

    Deliberately four narrow, single-purpose methods -- one per WMI
    method actually needed -- rather than a general "call any WMI
    method" helper, for the same reason
    ``preparation.sanitizer.WmiMethodCaller`` is narrow: nothing in
    this codebase should be able to invoke an arbitrary, unreviewed
    WMI method by construction.
    """

    def enable_dhcp(self, *, interface_index: int) -> WmiConfigResult: ...

    def enable_static_ipv4(
        self,
        *,
        interface_index: int,
        ip_addresses: Sequence[str],
        subnet_masks: Sequence[str],
    ) -> WmiConfigResult: ...

    def set_gateways(
        self, *, interface_index: int, gateways: Sequence[str]
    ) -> WmiConfigResult: ...

    def set_dns_servers(
        self, *, interface_index: int, dns_servers: Sequence[str]
    ) -> WmiConfigResult: ...


class _DefaultAdapterConfigurationCaller:
    """
    Real ``Win32_NetworkAdapterConfiguration`` method invocation
    against the live system.

    Tries the ``wmi`` package first, then falls back to raw
    ``win32com.client`` COM automation -- the same two backends
    ``hardware.query_wmi`` and
    ``preparation.sanitizer._DefaultWmiMethodCaller`` both use. Both
    are optional, Windows-only dependencies; on any other platform,
    or if neither is importable, this raises ``DHCPError`` rather
    than pretending to succeed.
    """

    def enable_dhcp(self, *, interface_index: int) -> WmiConfigResult:
        return self._invoke(interface_index, "EnableDHCP", {})

    def enable_static_ipv4(
        self,
        *,
        interface_index: int,
        ip_addresses: Sequence[str],
        subnet_masks: Sequence[str],
    ) -> WmiConfigResult:
        return self._invoke(
            interface_index,
            "EnableStatic",
            {
                "IPAddress": list(ip_addresses),
                "SubnetMask": list(subnet_masks),
            },
        )

    def set_gateways(
        self, *, interface_index: int, gateways: Sequence[str]
    ) -> WmiConfigResult:
        return self._invoke(
            interface_index,
            "SetGateways",
            {"DefaultIPGateway": list(gateways)},
        )

    def set_dns_servers(
        self, *, interface_index: int, dns_servers: Sequence[str]
    ) -> WmiConfigResult:
        return self._invoke(
            interface_index,
            "SetDNSServerSearchOrder",
            {"DNSServerSearchOrder": list(dns_servers)},
        )

    def _invoke(
        self,
        interface_index: int,
        method_name: str,
        params: dict[str, Any],
    ) -> WmiConfigResult:
        if not is_windows():
            raise DHCPError(
                f"{method_name} requires Windows; the current platform "
                "is not supported."
            )

        try:
            import wmi  # type: ignore[import-untyped]

            connection = wmi.WMI(namespace=_WMI_NAMESPACE)
            configs = connection.Win32_NetworkAdapterConfiguration(
                Index=interface_index
            )
            if not configs:
                raise DHCPError(
                    "Win32_NetworkAdapterConfiguration with Index="
                    f"{interface_index} was not found -- the adapter "
                    "may have been removed or renumbered since "
                    "inspection."
                )

            method = getattr(configs[0], method_name)
            raw_result: Any = method(**params) if params else method()

            if isinstance(raw_result, tuple) and len(
                cast("tuple[Any, ...]", raw_result)
            ) >= 1:
                return_code = int(cast("tuple[Any, ...]", raw_result)[0])
            else:
                return_code = int(cast(Any, raw_result))

            return WmiConfigResult(
                return_code=return_code, detail=_describe(return_code)
            )
        except ImportError:
            pass
        except DHCPError:
            raise
        except Exception as exc:
            logger.debug(
                "Python 'wmi' package %s() call failed for interface "
                "%d: %s",
                method_name,
                interface_index,
                exc,
            )
            raise DHCPError(
                f"{method_name}() failed for interface {interface_index}: "
                f"{exc}"
            ) from exc

        try:
            import win32com.client  # type: ignore[import-untyped]

            locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
            service = locator.ConnectServer(".", _WMI_NAMESPACE)
            service.Security_.ImpersonationLevel = 3

            rows = list(
                service.ExecQuery(
                    "SELECT * FROM Win32_NetworkAdapterConfiguration "
                    f"WHERE Index = {interface_index}",
                    "WQL",
                    0x10 | 0x20,
                )
            )
            if not rows:
                raise DHCPError(
                    "Win32_NetworkAdapterConfiguration with Index="
                    f"{interface_index} was not found -- the adapter "
                    "may have been removed or renumbered since "
                    "inspection."
                )

            config_object = rows[0]

            if params:
                in_params = config_object.Methods_(
                    method_name
                ).InParameters.SpawnInstance_()
                for key, value in params.items():
                    setattr(in_params, key, value)
                out_params = service.ExecMethod(
                    config_object.Path_.Path, method_name, in_params
                )
            else:
                out_params = service.ExecMethod(
                    config_object.Path_.Path, method_name
                )

            return_code = int(getattr(out_params, "ReturnValue", 65))
            return WmiConfigResult(
                return_code=return_code, detail=_describe(return_code)
            )
        except ImportError as exc:
            raise DHCPError(
                "Neither the 'wmi' package nor 'win32com.client' is "
                "available -- IP address configuration requires one of "
                "them on Windows."
            ) from exc
        except DHCPError:
            raise
        except Exception as exc:
            logger.debug(
                "COM %s() call failed for interface %d: %s",
                method_name,
                interface_index,
                exc,
            )
            raise DHCPError(
                f"{method_name}() failed for interface {interface_index}: "
                f"{exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class AddressAssignmentResult:
    """The outcome of one REQ-NET-005/006 address acquisition step."""

    method: str
    interface_name: str
    succeeded: bool
    detail: str
    assigned_ip_addresses: tuple[str, ...] = ()

    #: Populated only by :meth:`NetworkAddressAssigner.verify_assignment`
    #: (a fresh re-detection), from the adapter's
    #: ``Win32_NetworkAdapterConfiguration.DefaultIPGateway`` -- the
    #: only way to know a DHCP-assigned gateway, which is never present
    #: in ``NetworkConfig`` (unlike the static assignment methods,
    #: where the gateway is explicit configuration).
    default_gateways: tuple[str, ...] = ()


class NetworkAddressAssigner:
    """
    Acquires an IP address per ``NetworkConfig.ip_assignment_method``
    (REQ-NET-005) and verifies the result (REQ-NET-006).
    """

    def __init__(
        self,
        *,
        adapter_caller: AdapterConfigurationCaller | None = None,
        network_detector: NetworkDetector | None = None,
        command_runner: Callable[
            [Sequence[str]], tuple[int, str, str]
        ] = _run_subprocess,
    ) -> None:
        self._adapter_caller = adapter_caller or _DefaultAdapterConfigurationCaller()
        self._network_detector = network_detector or NetworkDetector()
        self._command_runner = command_runner

    def assign(
        self, config: NetworkConfig, *, adapter: NetworkAdapter
    ) -> AddressAssignmentResult:
        """REQ-NET-005: acquire an address using the configured method."""

        if config.ip_assignment_method == "dhcp":
            return self._assign_dhcp(adapter)

        if config.ip_assignment_method == "static_ipv4":
            return self._assign_static_ipv4(adapter, config)

        if config.ip_assignment_method == "static_ipv6":
            return self._assign_static_ipv6(adapter, config)

        # Unreachable in practice -- NetworkConfig.__post_init__
        # already validates ip_assignment_method against
        # IP_ASSIGNMENT_METHODS -- but this module never trusts an
        # upstream invariant it can cheaply re-check itself.
        raise NetworkingConfigurationError(
            "Unsupported ip_assignment_method: "
            f"{config.ip_assignment_method!r}."
        )

    def verify_assignment(
        self,
        adapter_name: str,
        *,
        retry_count: int,
        retry_delay_seconds: float,
        sleep: Callable[[float], None] = time.sleep,
    ) -> AddressAssignmentResult:
        """
        REQ-NET-006: verify successful IP address assignment by
        re-enumerating adapters and confirming ``adapter_name`` now
        carries at least one IP address, retrying while address
        assignment (DHCP lease acquisition in particular) settles.

        ``sleep`` is a call-time parameter, matching every other
        retry-based checker in this package.
        """

        attempts = max(1, retry_count + 1)
        last_detail = "IP address assignment was not checked."

        for attempt in range(attempts):
            adapters = self._network_detector.detect()
            matched = next(
                (a for a in adapters if a.name == adapter_name), None
            )

            if matched is not None and matched.ip_addresses:
                detail = (
                    f"'{adapter_name}' has IP address(es): "
                    f"{', '.join(matched.ip_addresses)}."
                )
                logger.info("IP address assignment verified: %s", detail)
                return AddressAssignmentResult(
                    method="verify",
                    interface_name=adapter_name,
                    succeeded=True,
                    detail=detail,
                    assigned_ip_addresses=tuple(matched.ip_addresses),
                    default_gateways=tuple(matched.default_gateways),
                )

            last_detail = (
                f"'{adapter_name}' has no assigned IP address yet."
                if matched is not None
                else f"Adapter '{adapter_name}' was not found."
            )

            if attempt < attempts - 1:
                logger.warning(
                    "IP assignment not yet verified (attempt %d/%d): "
                    "%s -- retrying in %.1fs.",
                    attempt + 1,
                    attempts,
                    last_detail,
                    retry_delay_seconds,
                )
                sleep(retry_delay_seconds)

        logger.error(
            "IP address assignment verification failed after %d "
            "attempt(s): %s",
            attempts,
            last_detail,
        )
        return AddressAssignmentResult(
            method="verify",
            interface_name=adapter_name,
            succeeded=False,
            detail=last_detail,
        )

    # ------------------------------------------------------------------
    # Assignment methods
    # ------------------------------------------------------------------

    def _assign_dhcp(self, adapter: NetworkAdapter) -> AddressAssignmentResult:
        index = self._require_index(adapter)

        result = self._adapter_caller.enable_dhcp(interface_index=index)
        if not result.succeeded:
            raise DHCPError(
                f"EnableDHCP failed for '{adapter.name}' "
                f"(code {result.return_code}): {result.detail}"
            )

        logger.info("DHCP enabled on '%s': %s", adapter.name, result.detail)
        return AddressAssignmentResult(
            method="dhcp",
            interface_name=adapter.name,
            succeeded=True,
            detail=result.detail,
        )

    def _assign_static_ipv4(
        self, adapter: NetworkAdapter, config: NetworkConfig
    ) -> AddressAssignmentResult:
        index = self._require_index(adapter)

        address = config.static_ipv4_address
        netmask = config.static_ipv4_netmask or "255.255.255.0"
        gateway = config.static_ipv4_gateway

        if not address or not gateway:
            raise StaticConfigurationError(
                "'static_ipv4_address' and 'static_ipv4_gateway' are "
                "required for static_ipv4 assignment."
            )

        static_result = self._adapter_caller.enable_static_ipv4(
            interface_index=index,
            ip_addresses=[address],
            subnet_masks=[netmask],
        )
        if not static_result.succeeded:
            raise StaticConfigurationError(
                f"EnableStatic failed for '{adapter.name}' "
                f"(code {static_result.return_code}): "
                f"{static_result.detail}"
            )

        gateway_result = self._adapter_caller.set_gateways(
            interface_index=index, gateways=[gateway]
        )
        if not gateway_result.succeeded:
            raise GatewayError(
                f"SetGateways failed for '{adapter.name}' "
                f"(code {gateway_result.return_code}): "
                f"{gateway_result.detail}"
            )

        if config.dns_servers:
            dns_result = self._adapter_caller.set_dns_servers(
                interface_index=index, dns_servers=config.dns_servers
            )
            if not dns_result.succeeded:
                raise DNSError(
                    "SetDNSServerSearchOrder failed for "
                    f"'{adapter.name}' (code {dns_result.return_code}): "
                    f"{dns_result.detail}"
                )

        detail = f"Static IPv4 {address}/{netmask} via {gateway} assigned."
        logger.info("%s on '%s'.", detail, adapter.name)
        return AddressAssignmentResult(
            method="static_ipv4",
            interface_name=adapter.name,
            succeeded=True,
            detail=detail,
            assigned_ip_addresses=(address,),
        )

    def _assign_static_ipv6(
        self, adapter: NetworkAdapter, config: NetworkConfig
    ) -> AddressAssignmentResult:
        address = config.static_ipv6_address
        prefix_length = config.static_ipv6_prefix_length
        gateway = config.static_ipv6_gateway

        if not address or gateway is None or prefix_length is None:
            raise StaticConfigurationError(
                "'static_ipv6_address', 'static_ipv6_prefix_length', "
                "and 'static_ipv6_gateway' are required for "
                "static_ipv6 assignment."
            )

        self._run_netsh(
            [
                "netsh",
                "interface",
                "ipv6",
                "add",
                "address",
                f"interface={adapter.name}",
                f"address={address}/{prefix_length}",
                "store=persistent",
            ],
            error_type=StaticConfigurationError,
            action="assign the static IPv6 address",
        )

        self._run_netsh(
            [
                "netsh",
                "interface",
                "ipv6",
                "add",
                "route",
                "prefix=::/0",
                f"interface={adapter.name}",
                f"nexthop={gateway}",
                "store=persistent",
            ],
            error_type=GatewayError,
            action="add the IPv6 default route",
        )

        for position, dns_server in enumerate(config.dns_servers, start=1):
            self._run_netsh(
                [
                    "netsh",
                    "interface",
                    "ipv6",
                    "add",
                    "dnsservers",
                    f"name={adapter.name}",
                    f"address={dns_server}",
                    f"index={position}",
                ],
                error_type=DNSError,
                action="add an IPv6 DNS server",
            )

        detail = (
            f"Static IPv6 {address}/{prefix_length} via {gateway} assigned."
        )
        logger.info("%s on '%s'.", detail, adapter.name)
        return AddressAssignmentResult(
            method="static_ipv6",
            interface_name=adapter.name,
            succeeded=True,
            detail=detail,
            assigned_ip_addresses=(address,),
        )

    def _require_index(self, adapter: NetworkAdapter) -> int:
        if adapter.interface_index is None:
            raise InterfaceNotFoundError(
                f"Adapter '{adapter.name}' has no known WMI interface "
                "index -- it may not have been sourced from a live "
                "hardware detection pass."
            )
        return adapter.interface_index

    def _run_netsh(
        self,
        command: Sequence[str],
        *,
        error_type: type[NetworkingError],
        action: str,
    ) -> None:
        # Deliberately no ``is_windows()`` guard here: that check
        # belongs to the concrete backend (``_run_subprocess``), not
        # this wrapper -- mirroring ``_DefaultAdapterConfigurationCaller
        # ._invoke``'s platform check living inside the real WMI
        # backend, not in ``NetworkAddressAssigner`` itself. Guarding
        # here would make an injected fake ``command_runner`` (used by
        # every functional test in this codebase, since no test should
        # ever depend on running on Windows) unreachable.
        return_code, stdout, stderr = self._command_runner(command)
        if return_code != 0:
            detail = (stderr or stdout or "no output").strip()
            raise error_type(
                f"Failed to {action} (netsh exit code {return_code}): "
                f"{detail}"
            )


__all__ = [
    "AdapterConfigurationCaller",
    "AddressAssignmentResult",
    "NetworkAddressAssigner",
    "WmiConfigResult",
]
