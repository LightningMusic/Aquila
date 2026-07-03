"""
Project Orion
=============

Networking Exceptions

Defines networking-related exceptions used
throughout Project Orion.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from common.exceptions.application import OrionError


class NetworkingError(OrionError):
    """
    Base class for all networking-related exceptions.
    """


class NetworkingInitializationError(NetworkingError):
    """
    Raised when the networking subsystem
    cannot be initialized.
    """


class NetworkingConfigurationError(NetworkingError):
    """
    Raised when networking configuration
    is invalid.
    """


class NetworkingValidationError(NetworkingError):
    """
    Raised when network configuration
    validation fails.
    """


class NetworkingTimeoutError(NetworkingError):
    """
    Raised when a networking operation
    exceeds its timeout.
    """


class NetworkingPermissionError(NetworkingError):
    """
    Raised when Orion lacks permission
    to perform a networking operation.
    """


class NetworkingUnavailableError(NetworkingError):
    """
    Raised when networking is unavailable.
    """


# ----------------------------------------------------------------------
# Interfaces
# ----------------------------------------------------------------------


class NetworkInterfaceError(NetworkingError):
    """
    Base network interface exception.
    """


class InterfaceNotFoundError(NetworkInterfaceError):
    """
    Raised when a network interface
    cannot be found.
    """


class InterfaceDisabledError(NetworkInterfaceError):
    """
    Raised when a required network
    interface is disabled.
    """


class LinkDownError(NetworkInterfaceError):
    """
    Raised when the physical network
    link is down.
    """


class EthernetConnectionError(NetworkInterfaceError):
    """
    Raised when Ethernet connectivity
    fails.
    """


class LinkSpeedError(NetworkInterfaceError):
    """
    Raised when Ethernet link speed
    does not satisfy requirements.
    """


# ----------------------------------------------------------------------
# IP Configuration
# ----------------------------------------------------------------------


class AddressConfigurationError(NetworkingError):
    """
    Base address configuration exception.
    """


class DHCPError(AddressConfigurationError):
    """
    Raised when DHCP operations fail.
    """


class StaticConfigurationError(AddressConfigurationError):
    """
    Raised when static IP configuration
    fails.
    """


class GatewayError(AddressConfigurationError):
    """
    Raised when the default gateway
    cannot be configured or reached.
    """


class DNSError(AddressConfigurationError):
    """
    Raised when DNS configuration
    or resolution fails.
    """


# ----------------------------------------------------------------------
# Connectivity
# ----------------------------------------------------------------------


class ConnectionError(NetworkingError):
    """
    Base network connection exception.
    """


class HostUnreachableError(ConnectionError):
    """
    Raised when a remote host
    cannot be reached.
    """


class PingError(ConnectionError):
    """
    Raised when connectivity tests fail.
    """


class PortUnavailableError(ConnectionError):
    """
    Raised when a required network port
    is unavailable.
    """


# ----------------------------------------------------------------------
# SSH
# ----------------------------------------------------------------------


class SSHError(NetworkingError):
    """
    Base SSH exception.
    """


class SSHConnectionError(SSHError):
    """
    Raised when an SSH connection fails.
    """


class SSHAuthenticationError(SSHError):
    """
    Raised when SSH authentication fails.
    """


class SSHCommandError(SSHError):
    """
    Raised when execution of a remote
    SSH command fails.
    """


class SSHKeyError(SSHError):
    """
    Raised when SSH keys are missing
    or invalid.
    """


# ----------------------------------------------------------------------
# Cluster Networking
# ----------------------------------------------------------------------


class ClusterNetworkingError(NetworkingError):
    """
    Base cluster networking exception.
    """


class ClusterDiscoveryError(ClusterNetworkingError):
    """
    Raised when cluster node discovery
    fails.
    """


class ClusterCommunicationError(ClusterNetworkingError):
    """
    Raised when communication between
    cluster nodes fails.
    """


class ClusterJoinError(ClusterNetworkingError):
    """
    Raised when joining a cluster fails.
    """


# ----------------------------------------------------------------------
# Proxmox API
# ----------------------------------------------------------------------


class ProxmoxApiError(NetworkingError):
    """
    Base Proxmox API exception.
    """


class ApiConnectionError(ProxmoxApiError):
    """
    Raised when the Proxmox API
    cannot be reached.
    """


class ApiAuthenticationError(ProxmoxApiError):
    """
    Raised when API authentication fails.
    """


class ApiResponseError(ProxmoxApiError):
    """
    Raised when the API returns
    an unexpected response.
    """


# ----------------------------------------------------------------------
# Reports
# ----------------------------------------------------------------------


class NetworkingReportError(NetworkingError):
    """
    Raised when networking reports
    cannot be generated.
    """


class NetworkingExportError(NetworkingError):
    """
    Raised when networking data
    cannot be exported.
    """


__all__ = [
    "AddressConfigurationError",
    "ApiAuthenticationError",
    "ApiConnectionError",
    "ApiResponseError",
    "ClusterCommunicationError",
    "ClusterDiscoveryError",
    "ClusterJoinError",
    "ClusterNetworkingError",
    "ConnectionError",
    "DHCPError",
    "DNSError",
    "EthernetConnectionError",
    "GatewayError",
    "HostUnreachableError",
    "InterfaceDisabledError",
    "InterfaceNotFoundError",
    "LinkDownError",
    "LinkSpeedError",
    "NetworkInterfaceError",
    "NetworkingConfigurationError",
    "NetworkingError",
    "NetworkingExportError",
    "NetworkingInitializationError",
    "NetworkingPermissionError",
    "NetworkingReportError",
    "NetworkingTimeoutError",
    "NetworkingUnavailableError",
    "NetworkingValidationError",
    "PingError",
    "PortUnavailableError",
    "ProxmoxApiError",
    "SSHAuthenticationError",
    "SSHCommandError",
    "SSHConnectionError",
    "SSHError",
    "SSHKeyError",
    "StaticConfigurationError",
]