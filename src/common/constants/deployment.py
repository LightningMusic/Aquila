"""
Project Orion
=============

Deployment Constants

Defines deployment-wide constants used throughout
Project Orion.

These constants describe the deployment workflow, phases,
statuses, defaults, and safety limits.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

# ----------------------------------------------------------------------
# Deployment Workflow
# ----------------------------------------------------------------------

PHASE_ONE = 1
PHASE_TWO = 2

PHASE_ONE_NAME = "Recovery and Sanitization"
PHASE_TWO_NAME = "Provisioning and Cluster Enrollment"

# ----------------------------------------------------------------------
# Workflow Names
# ----------------------------------------------------------------------

WORKFLOW_INSPECTION = "inspection"
WORKFLOW_RECOVERY = "recovery"
WORKFLOW_PREPARATION = "preparation"
WORKFLOW_PROVISIONING = "provisioning"
WORKFLOW_BOOTSTRAP = "bootstrap"
WORKFLOW_BENCHMARK = "benchmark"

# ----------------------------------------------------------------------
# Deployment Status
# ----------------------------------------------------------------------

STATUS_PENDING = "pending"

STATUS_WAITING = "waiting"

STATUS_RUNNING = "running"

STATUS_COMPLETED = "completed"

STATUS_FAILED = "failed"

STATUS_CANCELLED = "cancelled"

STATUS_SKIPPED = "skipped"

STATUS_WARNING = "warning"

# ----------------------------------------------------------------------
# Confirmation Requirements
# ----------------------------------------------------------------------

MINIMUM_CONFIRMATIONS = 3

WIPE_CONFIRMATION_REQUIRED = True

RECOVERY_CONFIRMATION_REQUIRED = True

FORCE_CONFIRMATION_PHRASE = "ERASE"

# ----------------------------------------------------------------------
# Disk Operations
# ----------------------------------------------------------------------

DEFAULT_PARTITION_TABLE = "gpt"

DEFAULT_FILESYSTEM = "ext4"

BOOT_FILESYSTEM = "fat32"

EFI_PARTITION_SIZE_MB = 512

SWAP_SIZE_GB = 8

ROOT_RESERVED_PERCENT = 5

# ----------------------------------------------------------------------
# Proxmox
# ----------------------------------------------------------------------

PROXMOX_HOSTNAME_PREFIX = "orion-node"

PROXMOX_DEFAULT_USERNAME = "root"

PROXMOX_SSH_PORT = 22

PROXMOX_API_PORT = 8006

PROXMOX_CLUSTER_SERVICE = "pve-cluster"

# ----------------------------------------------------------------------
# Networking
# ----------------------------------------------------------------------

DEFAULT_INTERFACE = "eth0"

ETHERNET_REQUIRED = True

WAIT_FOR_NETWORK_SECONDS = 60

NETWORK_RETRY_COUNT = 10

NETWORK_RETRY_DELAY_SECONDS = 5

# ----------------------------------------------------------------------
# Inventory
# ----------------------------------------------------------------------

DEFAULT_NODE_PREFIX = "node"

DEFAULT_INVENTORY_FILE = "inventory.json"

DEFAULT_DEPLOYMENT_REPORT = "deployment_report.json"

DEFAULT_HARDWARE_REPORT = "hardware_report.json"

# ----------------------------------------------------------------------
# USB Deployment
# ----------------------------------------------------------------------

USB_PHASE_ONE_DIRECTORY = "phase1"

USB_PHASE_TWO_DIRECTORY = "phase2"

USB_REPORT_DIRECTORY = "reports"

USB_RECOVERY_DIRECTORY = "recovery"

USB_LOG_DIRECTORY = "logs"

# ----------------------------------------------------------------------
# Safety
# ----------------------------------------------------------------------

ALLOW_AUTOMATIC_DISK_SELECTION = False

VERIFY_TARGET_DISK = True

VERIFY_BOOT_MODE = True

VERIFY_POWER_CONNECTED = True

VERIFY_ETHERNET_CONNECTED = True

VERIFY_VIRTUALIZATION_SUPPORT = True

ABORT_ON_SMART_FAILURE = True

ABORT_ON_LOW_BATTERY = True

LOW_BATTERY_THRESHOLD = 20

# ----------------------------------------------------------------------
# Timeouts
# ----------------------------------------------------------------------

DEFAULT_OPERATION_TIMEOUT_SECONDS = 300

DEFAULT_REBOOT_TIMEOUT_SECONDS = 600

DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 120

DEFAULT_INSTALL_TIMEOUT_SECONDS = 3600

# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------

DEPLOYMENT_LOG_NAME = "deployment.log"

INSTALL_LOG_NAME = "installation.log"

RECOVERY_LOG_NAME = "recovery.log"

BENCHMARK_LOG_NAME = "benchmark.log"

# ----------------------------------------------------------------------
# Exit Codes
# ----------------------------------------------------------------------

DEPLOYMENT_SUCCESS = 0

DEPLOYMENT_WARNING = 1

DEPLOYMENT_ERROR = 2

DEPLOYMENT_ABORTED = 3

DEPLOYMENT_CANCELLED = 4

# ----------------------------------------------------------------------
# Public Exports
# ----------------------------------------------------------------------

__all__ = [
    "ABORT_ON_LOW_BATTERY",
    "ABORT_ON_SMART_FAILURE",
    "ALLOW_AUTOMATIC_DISK_SELECTION",
    "BENCHMARK_LOG_NAME",
    "BOOT_FILESYSTEM",
    "DEFAULT_DEPLOYMENT_REPORT",
    "DEFAULT_FILESYSTEM",
    "DEFAULT_HARDWARE_REPORT",
    "DEFAULT_INSTALL_TIMEOUT_SECONDS",
    "DEFAULT_INTERFACE",
    "DEFAULT_INVENTORY_FILE",
    "DEFAULT_NODE_PREFIX",
    "DEFAULT_OPERATION_TIMEOUT_SECONDS",
    "DEFAULT_PARTITION_TABLE",
    "DEFAULT_REBOOT_TIMEOUT_SECONDS",
    "DEFAULT_SHUTDOWN_TIMEOUT_SECONDS",
    "DEPLOYMENT_ABORTED",
    "DEPLOYMENT_CANCELLED",
    "DEPLOYMENT_ERROR",
    "DEPLOYMENT_LOG_NAME",
    "DEPLOYMENT_SUCCESS",
    "DEPLOYMENT_WARNING",
    "EFI_PARTITION_SIZE_MB",
    "ETHERNET_REQUIRED",
    "FORCE_CONFIRMATION_PHRASE",
    "LOW_BATTERY_THRESHOLD",
    "MINIMUM_CONFIRMATIONS",
    "NETWORK_RETRY_COUNT",
    "NETWORK_RETRY_DELAY_SECONDS",
    "PHASE_ONE",
    "PHASE_ONE_NAME",
    "PHASE_TWO",
    "PHASE_TWO_NAME",
    "PROXMOX_API_PORT",
    "PROXMOX_CLUSTER_SERVICE",
    "PROXMOX_DEFAULT_USERNAME",
    "PROXMOX_HOSTNAME_PREFIX",
    "PROXMOX_SSH_PORT",
    "RECOVERY_CONFIRMATION_REQUIRED",
    "RECOVERY_LOG_NAME",
    "ROOT_RESERVED_PERCENT",
    "STATUS_CANCELLED",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_PENDING",
    "STATUS_RUNNING",
    "STATUS_SKIPPED",
    "STATUS_WAITING",
    "STATUS_WARNING",
    "SWAP_SIZE_GB",
    "USB_LOG_DIRECTORY",
    "USB_PHASE_ONE_DIRECTORY",
    "USB_PHASE_TWO_DIRECTORY",
    "USB_RECOVERY_DIRECTORY",
    "USB_REPORT_DIRECTORY",
    "VERIFY_BOOT_MODE",
    "VERIFY_ETHERNET_CONNECTED",
    "VERIFY_POWER_CONNECTED",
    "VERIFY_TARGET_DISK",
    "VERIFY_VIRTUALIZATION_SUPPORT",
    "WAIT_FOR_NETWORK_SECONDS",
    "WIPE_CONFIRMATION_REQUIRED",
    "WORKFLOW_BENCHMARK",
    "WORKFLOW_BOOTSTRAP",
    "WORKFLOW_INSPECTION",
    "WORKFLOW_PREPARATION",
    "WORKFLOW_PROVISIONING",
    "WORKFLOW_RECOVERY",
]