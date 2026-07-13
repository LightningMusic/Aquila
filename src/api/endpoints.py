"""
Project Orion
=============

API Endpoints

Defines endpoint constants and helper functions
used by Project Orion.

Currently these endpoints target the
Proxmox VE REST API.

Nothing outside this module should hardcode
API paths.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

# ==========================================================
# API Base
# ==========================================================

API_VERSION = "/api2/json"

# ==========================================================
# General
# ==========================================================

VERSION = f"{API_VERSION}/version"

PING = VERSION

# ==========================================================
# Authentication
# ==========================================================

ACCESS = f"{API_VERSION}/access"

TICKET = f"{ACCESS}/ticket"

USERS = f"{ACCESS}/users"

DOMAINS = f"{ACCESS}/domains"

ROLES = f"{ACCESS}/roles"

PERMISSIONS = f"{ACCESS}/permissions"

# ==========================================================
# Cluster
# ==========================================================

CLUSTER = f"{API_VERSION}/cluster"

CLUSTER_STATUS = f"{CLUSTER}/status"

CLUSTER_CONFIG = f"{CLUSTER}/config"

CLUSTER_OPTIONS = f"{CLUSTER}/options"

CLUSTER_RESOURCES = f"{CLUSTER}/resources"

CLUSTER_BACKUP = f"{CLUSTER}/backup"

CLUSTER_FIREWALL = f"{CLUSTER}/firewall"

CLUSTER_METRICS = f"{CLUSTER}/metrics"

CLUSTER_TASKS = f"{CLUSTER}/tasks"

CLUSTER_LOG = f"{CLUSTER}/log"

CLUSTER_NEXT_ID = f"{CLUSTER}/nextid"

# ==========================================================
# Nodes
# ==========================================================

NODES = f"{API_VERSION}/nodes"


def node(node_name: str) -> str:
    """
    /nodes/{node}
    """
    return f"{NODES}/{node_name}"


def node_status(node_name: str) -> str:
    return f"{node(node_name)}/status"


def node_status_current(node_name: str) -> str:
    return f"{node(node_name)}/status/current"


def node_network(node_name: str) -> str:
    return f"{node(node_name)}/network"


def node_storage(node_name: str) -> str:
    return f"{node(node_name)}/storage"


def node_disks(node_name: str) -> str:
    return f"{node(node_name)}/disks"


def node_services(node_name: str) -> str:
    return f"{node(node_name)}/services"


def node_tasks(node_name: str) -> str:
    return f"{node(node_name)}/tasks"


def node_log(node_name: str) -> str:
    return f"{node(node_name)}/log"


def node_time(node_name: str) -> str:
    return f"{node(node_name)}/time"


def node_dns(node_name: str) -> str:
    return f"{node(node_name)}/dns"


def node_firewall(node_name: str) -> str:
    return f"{node(node_name)}/firewall"


def node_capabilities(node_name: str) -> str:
    return f"{node(node_name)}/capabilities"


# ==========================================================
# Storage
# ==========================================================


def storage(node_name: str) -> str:
    return f"{node(node_name)}/storage"


def storage_content(
    node_name: str,
    storage_name: str,
) -> str:
    return f"{storage(node_name)}/{storage_name}/content"


# ==========================================================
# Virtual Machines (QEMU)
# ==========================================================


def qemu(node_name: str) -> str:
    return f"{node(node_name)}/qemu"


def qemu_vm(
    node_name: str,
    vmid: int,
) -> str:
    return f"{qemu(node_name)}/{vmid}"


def qemu_config(
    node_name: str,
    vmid: int,
) -> str:
    return f"{qemu_vm(node_name, vmid)}/config"


def qemu_status(
    node_name: str,
    vmid: int,
) -> str:
    return f"{qemu_vm(node_name, vmid)}/status/current"


def qemu_snapshot(
    node_name: str,
    vmid: int,
) -> str:
    return f"{qemu_vm(node_name, vmid)}/snapshot"


# ==========================================================
# Containers (LXC)
# ==========================================================


def lxc(node_name: str) -> str:
    return f"{node(node_name)}/lxc"


def lxc_container(
    node_name: str,
    vmid: int,
) -> str:
    return f"{lxc(node_name)}/{vmid}"


def lxc_status(
    node_name: str,
    vmid: int,
) -> str:
    return f"{lxc_container(node_name, vmid)}/status/current"


def lxc_config(
    node_name: str,
    vmid: int,
) -> str:
    return f"{lxc_container(node_name, vmid)}/config"


# ==========================================================
# Certificates
# ==========================================================

CERTIFICATES = f"{CLUSTER}/certificates"

# ==========================================================
# Backup
# ==========================================================

BACKUP = f"{API_VERSION}/cluster/backup"

# ==========================================================
# Export
# ==========================================================

__all__ = [
    "ACCESS",
    "API_VERSION",
    "BACKUP",
    "CERTIFICATES",
    "CLUSTER",
    "CLUSTER_BACKUP",
    "CLUSTER_CONFIG",
    "CLUSTER_FIREWALL",
    "CLUSTER_LOG",
    "CLUSTER_METRICS",
    "CLUSTER_NEXT_ID",
    "CLUSTER_OPTIONS",
    "CLUSTER_RESOURCES",
    "CLUSTER_STATUS",
    "CLUSTER_TASKS",
    "DOMAINS",
    "NODES",
    "PERMISSIONS",
    "PING",
    "ROLES",
    "TICKET",
    "USERS",
    "VERSION",
    "lxc",
    "lxc_config",
    "lxc_container",
    "lxc_status",
    "node",
    "node_capabilities",
    "node_disks",
    "node_dns",
    "node_firewall",
    "node_log",
    "node_network",
    "node_services",
    "node_status",
    "node_status_current",
    "node_storage",
    "node_tasks",
    "node_time",
    "qemu",
    "qemu_config",
    "qemu_snapshot",
    "qemu_status",
    "qemu_vm",
    "storage",
    "storage_content",
]