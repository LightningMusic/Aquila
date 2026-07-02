"""
Project Orion
=============

Networking events.

Defines events related to network initialization, Ethernet detection,
IP configuration, connectivity testing, DNS, gateway validation,
cluster registration, and SSH connectivity.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from common.enums import EventSource, EventType
from common.events.event import Event


# =============================================================================
# Ethernet
# =============================================================================


class EthernetDetectedEvent(Event):
    """
    Published when an Ethernet interface is detected.
    """

    def __init__(
        self,
        interface: str,
        mac_address: str,
        link_up: bool,
    ) -> None:
        super().__init__(
            event_type=EventType.ETHERNET_DETECTED.name,
            source=EventSource.NETWORK_MANAGER.name,
            payload={
                "interface": interface,
                "mac_address": mac_address,
                "link_up": link_up,
            },
        )


class EthernetDisconnectedEvent(Event):
    """
    Published when Ethernet connectivity is lost.
    """

    def __init__(
        self,
        interface: str,
    ) -> None:
        super().__init__(
            event_type=EventType.ETHERNET_DISCONNECTED.name,
            source=EventSource.NETWORK_MANAGER.name,
            payload={
                "interface": interface,
            },
        )


# =============================================================================
# IP Configuration
# =============================================================================


class IPAddressAssignedEvent(Event):
    """
    Published when an IP address has been assigned.
    """

    def __init__(
        self,
        interface: str,
        ip_address: str,
        assignment: str,
    ) -> None:
        super().__init__(
            event_type=EventType.IP_ADDRESS_ASSIGNED.name,
            source=EventSource.NETWORK_MANAGER.name,
            payload={
                "interface": interface,
                "ip_address": ip_address,
                "assignment": assignment,
            },
        )


class IPConfigurationFailedEvent(Event):
    """
    Published when IP configuration fails.
    """

    def __init__(
        self,
        interface: str,
        reason: str,
    ) -> None:
        super().__init__(
            event_type=EventType.IP_CONFIGURATION_FAILED.name,
            source=EventSource.NETWORK_MANAGER.name,
            payload={
                "interface": interface,
                "reason": reason,
            },
        )


# =============================================================================
# Gateway
# =============================================================================


class GatewayReachableEvent(Event):
    """
    Published when the configured gateway is reachable.
    """

    def __init__(
        self,
        gateway: str,
    ) -> None:
        super().__init__(
            event_type=EventType.GATEWAY_REACHABLE.name,
            source=EventSource.NETWORK_MANAGER.name,
            payload={
                "gateway": gateway,
            },
        )


class GatewayUnreachableEvent(Event):
    """
    Published when the configured gateway cannot be reached.
    """

    def __init__(
        self,
        gateway: str,
    ) -> None:
        super().__init__(
            event_type=EventType.GATEWAY_UNREACHABLE.name,
            source=EventSource.NETWORK_MANAGER.name,
            payload={
                "gateway": gateway,
            },
        )


# =============================================================================
# DNS
# =============================================================================


class DNSResolvedEvent(Event):
    """
    Published after successful DNS resolution.
    """

    def __init__(
        self,
        hostname: str,
        ip_address: str,
    ) -> None:
        super().__init__(
            event_type=EventType.DNS_RESOLVED.name,
            source=EventSource.NETWORK_MANAGER.name,
            payload={
                "hostname": hostname,
                "ip_address": ip_address,
            },
        )


class DNSResolutionFailedEvent(Event):
    """
    Published when DNS resolution fails.
    """

    def __init__(
        self,
        hostname: str,
    ) -> None:
        super().__init__(
            event_type=EventType.DNS_RESOLUTION_FAILED.name,
            source=EventSource.NETWORK_MANAGER.name,
            payload={
                "hostname": hostname,
            },
        )


# =============================================================================
# Connectivity
# =============================================================================


class ConnectivityTestStartedEvent(Event):
    """
    Published before connectivity testing begins.
    """

    def __init__(self) -> None:
        super().__init__(
            event_type=EventType.CONNECTIVITY_TEST_STARTED.name,
            source=EventSource.NETWORK_MANAGER.name,
        )


class ConnectivityTestPassedEvent(Event):
    """
    Published when all connectivity tests pass.
    """

    def __init__(self) -> None:
        super().__init__(
            event_type=EventType.CONNECTIVITY_TEST_PASSED.name,
            source=EventSource.NETWORK_MANAGER.name,
        )


class ConnectivityTestFailedEvent(Event):
    """
    Published when one or more connectivity tests fail.
    """

    def __init__(
        self,
        reason: str,
    ) -> None:
        super().__init__(
            event_type=EventType.CONNECTIVITY_TEST_FAILED.name,
            source=EventSource.NETWORK_MANAGER.name,
            payload={
                "reason": reason,
            },
        )


# =============================================================================
# SSH
# =============================================================================


class SSHConnectionEstablishedEvent(Event):
    """
    Published when an SSH connection is successfully established.
    """

    def __init__(
        self,
        host: str,
    ) -> None:
        super().__init__(
            event_type=EventType.SSH_CONNECTION_ESTABLISHED.name,
            source=EventSource.NETWORK_MANAGER.name,
            payload={
                "host": host,
            },
        )


class SSHConnectionFailedEvent(Event):
    """
    Published when an SSH connection cannot be established.
    """

    def __init__(
        self,
        host: str,
        reason: str,
    ) -> None:
        super().__init__(
            event_type=EventType.SSH_CONNECTION_FAILED.name,
            source=EventSource.NETWORK_MANAGER.name,
            payload={
                "host": host,
                "reason": reason,
            },
        )


# =============================================================================
# Cluster
# =============================================================================


class ClusterJoinStartedEvent(Event):
    """
    Published when a node begins joining the cluster.
    """

    def __init__(
        self,
        node_name: str,
    ) -> None:
        super().__init__(
            event_type=EventType.CLUSTER_JOIN_STARTED.name,
            source=EventSource.NETWORK_MANAGER.name,
            payload={
                "node_name": node_name,
            },
        )


class ClusterJoinedEvent(Event):
    """
    Published when a node successfully joins the cluster.
    """

    def __init__(
        self,
        node_name: str,
        cluster_name: str,
    ) -> None:
        super().__init__(
            event_type=EventType.CLUSTER_JOINED.name,
            source=EventSource.NETWORK_MANAGER.name,
            payload={
                "node_name": node_name,
                "cluster_name": cluster_name,
            },
        )


class ClusterJoinFailedEvent(Event):
    """
    Published when a node cannot join the cluster.
    """

    def __init__(
        self,
        node_name: str,
        reason: str,
    ) -> None:
        super().__init__(
            event_type=EventType.CLUSTER_JOIN_FAILED.name,
            source=EventSource.NETWORK_MANAGER.name,
            payload={
                "node_name": node_name,
                "reason": reason,
            },
        )