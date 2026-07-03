"""
Project Orion
=============

Networking Constants

Defines networking-related constants used throughout
Project Orion.

This module centralizes network defaults, protocols,
timeouts, ports, interface names, and cluster settings.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

# ----------------------------------------------------------------------
# Interface Names
# ----------------------------------------------------------------------

DEFAULT_INTERFACE = "eth0"

LOOPBACK_INTERFACE = "lo"

WIRELESS_INTERFACE_PREFIX = "wlan"

ETHERNET_INTERFACE_PREFIX = "eth"

# ----------------------------------------------------------------------
# Network Requirements
# ----------------------------------------------------------------------

ETHERNET_REQUIRED = True

INTERNET_REQUIRED = False

CLUSTER_NETWORK_REQUIRED = True

IPV6_ENABLED = False

# ----------------------------------------------------------------------
# DHCP
# ----------------------------------------------------------------------

DEFAULT_DHCP_TIMEOUT_SECONDS = 30

DEFAULT_DHCP_RETRIES = 5

WAIT_FOR_NETWORK_TIMEOUT_SECONDS = 60

# ----------------------------------------------------------------------
# Retry Behavior
# ----------------------------------------------------------------------

DEFAULT_RETRY_COUNT = 5

DEFAULT_RETRY_DELAY_SECONDS = 5

DEFAULT_CONNECTION_TIMEOUT_SECONDS = 10

DEFAULT_SOCKET_TIMEOUT_SECONDS = 30

# ----------------------------------------------------------------------
# Ports
# ----------------------------------------------------------------------

SSH_PORT = 22

HTTP_PORT = 80

HTTPS_PORT = 443

PROXMOX_API_PORT = 8006

DNS_PORT = 53

DHCP_SERVER_PORT = 67

DHCP_CLIENT_PORT = 68

NTP_PORT = 123

IPERF3_PORT = 5201

# ----------------------------------------------------------------------
# Hostnames
# ----------------------------------------------------------------------

DEFAULT_HOSTNAME_PREFIX = "orion-node"

MAX_HOSTNAME_LENGTH = 63

DEFAULT_DOMAIN = "local"

# ----------------------------------------------------------------------
# Cluster
# ----------------------------------------------------------------------

DEFAULT_CLUSTER_NAME = "orion-cluster"

DEFAULT_NODE_PREFIX = "node"

DEFAULT_NODE_START = 1

CLUSTER_DISCOVERY_TIMEOUT_SECONDS = 60

# ----------------------------------------------------------------------
# SSH
# ----------------------------------------------------------------------

DEFAULT_SSH_USERNAME = "root"

DEFAULT_SSH_KEY_NAME = "id_ed25519"

SSH_CONNECTION_TIMEOUT_SECONDS = 15

SSH_KEEPALIVE_SECONDS = 30

# ----------------------------------------------------------------------
# API
# ----------------------------------------------------------------------

API_PROTOCOL = "https"

API_VERSION = "v1"

API_TIMEOUT_SECONDS = 30

API_VERIFY_TLS = False

# ----------------------------------------------------------------------
# DNS
# ----------------------------------------------------------------------

DEFAULT_DNS_SERVER = "1.1.1.1"

SECONDARY_DNS_SERVER = "8.8.8.8"

# ----------------------------------------------------------------------
# Ethernet
# ----------------------------------------------------------------------

MINIMUM_LINK_SPEED_MBPS = 100

RECOMMENDED_LINK_SPEED_MBPS = 1000

AUTO_NEGOTIATION_REQUIRED = True

FULL_DUPLEX_REQUIRED = True

# ----------------------------------------------------------------------
# Benchmarking
# ----------------------------------------------------------------------

NETWORK_BENCHMARK_PORT = 5201

DEFAULT_PACKET_SIZE = 1400

DEFAULT_BANDWIDTH_TEST_SECONDS = 30

# ----------------------------------------------------------------------
# Status Values
# ----------------------------------------------------------------------

STATUS_CONNECTED = "Connected"

STATUS_DISCONNECTED = "Disconnected"

STATUS_CONNECTING = "Connecting"

STATUS_TIMEOUT = "Timeout"

STATUS_FAILED = "Failed"

STATUS_UNKNOWN = "Unknown"

# ----------------------------------------------------------------------
# Protocol Names
# ----------------------------------------------------------------------

PROTOCOL_TCP = "TCP"

PROTOCOL_UDP = "UDP"

PROTOCOL_HTTP = "HTTP"

PROTOCOL_HTTPS = "HTTPS"

PROTOCOL_SSH = "SSH"

PROTOCOL_DNS = "DNS"

# ----------------------------------------------------------------------
# Public Exports
# ----------------------------------------------------------------------

__all__ = [
    "API_PROTOCOL",
    "API_TIMEOUT_SECONDS",
    "API_VERIFY_TLS",
    "API_VERSION",
    "AUTO_NEGOTIATION_REQUIRED",
    "CLUSTER_DISCOVERY_TIMEOUT_SECONDS",
    "CLUSTER_NETWORK_REQUIRED",
    "DEFAULT_BANDWIDTH_TEST_SECONDS",
    "DEFAULT_CLUSTER_NAME",
    "DEFAULT_CONNECTION_TIMEOUT_SECONDS",
    "DEFAULT_DHCP_RETRIES",
    "DEFAULT_DHCP_TIMEOUT_SECONDS",
    "DEFAULT_DNS_SERVER",
    "DEFAULT_DOMAIN",
    "DEFAULT_HOSTNAME_PREFIX",
    "DEFAULT_INTERFACE",
    "DEFAULT_NODE_PREFIX",
    "DEFAULT_NODE_START",
    "DEFAULT_PACKET_SIZE",
    "DEFAULT_RETRY_COUNT",
    "DEFAULT_RETRY_DELAY_SECONDS",
    "DEFAULT_SOCKET_TIMEOUT_SECONDS",
    "DEFAULT_SSH_KEY_NAME",
    "DEFAULT_SSH_USERNAME",
    "DHCP_CLIENT_PORT",
    "DHCP_SERVER_PORT",
    "DNS_PORT",
    "ETHERNET_INTERFACE_PREFIX",
    "ETHERNET_REQUIRED",
    "FULL_DUPLEX_REQUIRED",
    "HTTP_PORT",
    "HTTPS_PORT",
    "INTERNET_REQUIRED",
    "IPERF3_PORT",
    "IPV6_ENABLED",
    "LOOPBACK_INTERFACE",
    "MAX_HOSTNAME_LENGTH",
    "MINIMUM_LINK_SPEED_MBPS",
    "NETWORK_BENCHMARK_PORT",
    "NTP_PORT",
    "PROTOCOL_DNS",
    "PROTOCOL_HTTP",
    "PROTOCOL_HTTPS",
    "PROTOCOL_SSH",
    "PROTOCOL_TCP",
    "PROTOCOL_UDP",
    "PROXMOX_API_PORT",
    "RECOMMENDED_LINK_SPEED_MBPS",
    "SECONDARY_DNS_SERVER",
    "SSH_CONNECTION_TIMEOUT_SECONDS",
    "SSH_KEEPALIVE_SECONDS",
    "SSH_PORT",
    "STATUS_CONNECTED",
    "STATUS_CONNECTING",
    "STATUS_DISCONNECTED",
    "STATUS_FAILED",
    "STATUS_TIMEOUT",
    "STATUS_UNKNOWN",
    "WAIT_FOR_NETWORK_TIMEOUT_SECONDS",
    "WIRELESS_INTERFACE_PREFIX",
]