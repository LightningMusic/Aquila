"""
Project Aquila
=============

Networking Engine

Implements REQ-NET-001 through REQ-NET-014 (SRS Section 9.13/11.11):
Ethernet detection, IP address acquisition, gateway/DNS verification,
Deployment Controller and Proxmox cluster reachability, connectivity
loss recovery, and network diagnostics reporting for Aquila Node
Provisioning (Workflow B). Runs entirely within Phase One (the
WinPE-hosted Technician Console) -- the same environment ``hardware/``
targets.

Consolidation note: this package supersedes the ad hoc Ethernet/
Deployment-Controller reachability checks
``provisioning.connectivity.ConnectivityChecker`` built before the
Networking Engine existed -- see that module's own "Scope note"
docstring, which flagged this exact consolidation as future work.
``ConnectivityChecker`` now delegates to :class:`networking.ethernet
.EthernetChecker` and :class:`networking.controller
.ControllerReachabilityChecker` internally, preserving its own public
API (and every existing caller/test) unchanged.

Public surface:

* :class:`networking.ethernet.EthernetChecker` -- REQ-NET-001/002/
  003/004.
* :class:`networking.dhcp.NetworkAddressAssigner` -- REQ-NET-005/006
  (DHCP, static IPv4, and static IPv6 acquisition -- despite this
  module's stub-plan filename, see ``networking.dhcp``'s own
  docstring for the documented scope).
* :class:`networking.gateway.GatewayChecker` -- REQ-NET-007.
* :class:`networking.dns.DNSResolutionChecker` -- REQ-NET-008.
* :class:`networking.controller.ControllerReachabilityChecker` --
  REQ-NET-009.
* :class:`networking.cluster.ClusterReachabilityChecker` --
  REQ-NET-010.
* :class:`networking.network_manager.NetworkManager` -- the
  orchestrator (REQ-NET-011/012/013/014); the only entry point a
  caller should normally need.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from .cluster import ClusterReachabilityChecker
from .controller import (
    ControllerReachabilityChecker,
    DefaultSocketProber,
    HostReachabilityResult,
    SocketProber,
)
from .dhcp import (
    AdapterConfigurationCaller,
    AddressAssignmentResult,
    NetworkAddressAssigner,
    WmiConfigResult,
)
from .dns import DNSResolutionChecker, DNSResolutionResult, DNSResolver
from .ethernet import EthernetChecker, EthernetLinkResult
from .gateway import GatewayChecker, GatewayProber, GatewayReachabilityResult
from .network_manager import NetworkDiagnostics, NetworkManager

__all__ = [
    "AdapterConfigurationCaller",
    "AddressAssignmentResult",
    "ClusterReachabilityChecker",
    "ControllerReachabilityChecker",
    "DNSResolutionChecker",
    "DNSResolutionResult",
    "DNSResolver",
    "DefaultSocketProber",
    "EthernetChecker",
    "EthernetLinkResult",
    "GatewayChecker",
    "GatewayProber",
    "GatewayReachabilityResult",
    "HostReachabilityResult",
    "NetworkAddressAssigner",
    "NetworkDiagnostics",
    "NetworkManager",
    "SocketProber",
    "WmiConfigResult",
]
