"""
Project Orion
=============

Proxmox Constants

Defines Proxmox VE related constants used throughout
Project Orion.

This module centralizes API endpoints, default ports,
cluster defaults, filesystem locations, package names,
service names, and installation defaults.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

# ----------------------------------------------------------------------
# Product Information
# ----------------------------------------------------------------------

PROXMOX_NAME = "Proxmox Virtual Environment"

PROXMOX_SHORT_NAME = "Proxmox VE"

PROXMOX_DEFAULT_VERSION = "9"

PROXMOX_DEFAULT_BRANCH = "stable"

# ----------------------------------------------------------------------
# Network
# ----------------------------------------------------------------------

PROXMOX_DEFAULT_HOSTNAME_PREFIX = "orion-node"

PROXMOX_DEFAULT_DOMAIN = "local"

PROXMOX_DEFAULT_USERNAME = "root"

PROXMOX_SSH_PORT = 22

PROXMOX_WEB_PORT = 8006

PROXMOX_API_PORT = 8006

# ----------------------------------------------------------------------
# API
# ----------------------------------------------------------------------

API_PROTOCOL = "https"

API_VERSION = "v2"

API_BASE_PATH = "/api2/json"

API_TIMEOUT_SECONDS = 30

VERIFY_TLS = False

# ----------------------------------------------------------------------
# Cluster
# ----------------------------------------------------------------------

DEFAULT_CLUSTER_NAME = "orion-cluster"

DEFAULT_NODE_PREFIX = "node"

DEFAULT_START_NODE_NUMBER = 1

MAX_CLUSTER_NODES = 32

# ----------------------------------------------------------------------
# Services
# ----------------------------------------------------------------------

SERVICE_CLUSTER = "pve-cluster"

SERVICE_PROXY = "pveproxy"

SERVICE_DAEMON = "pvedaemon"

SERVICE_COROSYNC = "corosync"

SERVICE_FIREWALL = "pve-firewall"

SERVICE_STATISTICS = "pvestatd"

SERVICE_SSH = "ssh"

# ----------------------------------------------------------------------
# Filesystem
# ----------------------------------------------------------------------

PVE_DIRECTORY = "/etc/pve"

NETWORK_CONFIGURATION = "/etc/network/interfaces"

HOSTS_FILE = "/etc/hosts"

RESOLV_CONF = "/etc/resolv.conf"

STORAGE_CONFIGURATION = "/etc/pve/storage.cfg"

CLUSTER_CONFIGURATION = "/etc/pve/corosync.conf"

SSH_DIRECTORY = "/root/.ssh"

AUTHORIZED_KEYS = "/root/.ssh/authorized_keys"

# ----------------------------------------------------------------------
# Storage
# ----------------------------------------------------------------------

DEFAULT_STORAGE_NAME = "local-lvm"

LOCAL_STORAGE = "local"

LOCAL_LVM_STORAGE = "local-lvm"

DEFAULT_FILESYSTEM = "ext4"

# ----------------------------------------------------------------------
# Installation
# ----------------------------------------------------------------------

INSTALLER_LABEL = "Proxmox VE Installer"

ISO_FILENAME = "proxmox.iso"

BOOT_MODE_UEFI = "UEFI"

BOOT_MODE_BIOS = "Legacy BIOS"

# ----------------------------------------------------------------------
# Packages
# ----------------------------------------------------------------------

PACKAGE_PVE = "proxmox-ve"

PACKAGE_QEMU = "qemu-server"

PACKAGE_LXC = "pve-container"

PACKAGE_BACKUP = "proxmox-backup-client"

PACKAGE_OPENVSWITCH = "openvswitch-switch"

# ----------------------------------------------------------------------
# Virtualization
# ----------------------------------------------------------------------

KVM = "kvm"

LXC = "lxc"

QEMU = "qemu"

DEFAULT_MACHINE_TYPE = "q35"

DEFAULT_CPU_TYPE = "host"

# ----------------------------------------------------------------------
# Networking
# ----------------------------------------------------------------------

DEFAULT_BRIDGE = "vmbr0"

DEFAULT_PHYSICAL_INTERFACE = "eth0"

DEFAULT_BRIDGE_ADDRESS = "dhcp"

# ----------------------------------------------------------------------
# Timeouts
# ----------------------------------------------------------------------

DEFAULT_BOOT_TIMEOUT_SECONDS = 300

DEFAULT_INSTALL_TIMEOUT_SECONDS = 3600

DEFAULT_REBOOT_TIMEOUT_SECONDS = 600

DEFAULT_API_TIMEOUT_SECONDS = 30

# ----------------------------------------------------------------------
# Status
# ----------------------------------------------------------------------

STATUS_ONLINE = "online"

STATUS_OFFLINE = "offline"

STATUS_UNKNOWN = "unknown"

STATUS_INSTALLING = "installing"

STATUS_REBOOTING = "rebooting"

STATUS_FAILED = "failed"

# ----------------------------------------------------------------------
# Public Exports
# ----------------------------------------------------------------------

__all__ = [
    "API_BASE_PATH",
    "API_PROTOCOL",
    "API_TIMEOUT_SECONDS",
    "API_VERSION",
    "AUTHORIZED_KEYS",
    "BOOT_MODE_BIOS",
    "BOOT_MODE_UEFI",
    "CLUSTER_CONFIGURATION",
    "DEFAULT_API_TIMEOUT_SECONDS",
    "DEFAULT_BOOT_TIMEOUT_SECONDS",
    "DEFAULT_BRIDGE",
    "DEFAULT_BRIDGE_ADDRESS",
    "DEFAULT_CLUSTER_NAME",
    "DEFAULT_CPU_TYPE",
    "DEFAULT_FILESYSTEM",
    "DEFAULT_INSTALL_TIMEOUT_SECONDS",
    "DEFAULT_MACHINE_TYPE",
    "DEFAULT_NODE_PREFIX",
    "DEFAULT_PHYSICAL_INTERFACE",
    "DEFAULT_REBOOT_TIMEOUT_SECONDS",
    "DEFAULT_START_NODE_NUMBER",
    "DEFAULT_STORAGE_NAME",
    "HOSTS_FILE",
    "INSTALLER_LABEL",
    "ISO_FILENAME",
    "KVM",
    "LOCAL_LVM_STORAGE",
    "LOCAL_STORAGE",
    "LXC",
    "MAX_CLUSTER_NODES",
    "NETWORK_CONFIGURATION",
    "PACKAGE_BACKUP",
    "PACKAGE_LXC",
    "PACKAGE_OPENVSWITCH",
    "PACKAGE_PVE",
    "PACKAGE_QEMU",
    "PROXMOX_API_PORT",
    "PROXMOX_DEFAULT_BRANCH",
    "PROXMOX_DEFAULT_DOMAIN",
    "PROXMOX_DEFAULT_HOSTNAME_PREFIX",
    "PROXMOX_DEFAULT_USERNAME",
    "PROXMOX_DEFAULT_VERSION",
    "PROXMOX_NAME",
    "PROXMOX_SHORT_NAME",
    "PROXMOX_SSH_PORT",
    "PROXMOX_WEB_PORT",
    "PVE_DIRECTORY",
    "QEMU",
    "RESOLV_CONF",
    "SERVICE_CLUSTER",
    "SERVICE_COROSYNC",
    "SERVICE_DAEMON",
    "SERVICE_FIREWALL",
    "SERVICE_PROXY",
    "SERVICE_SSH",
    "SERVICE_STATISTICS",
    "SSH_DIRECTORY",
    "STATUS_FAILED",
    "STATUS_INSTALLING",
    "STATUS_OFFLINE",
    "STATUS_ONLINE",
    "STATUS_REBOOTING",
    "STATUS_UNKNOWN",
    "STORAGE_CONFIGURATION",
    "VERIFY_TLS",
]