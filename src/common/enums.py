"""
Project Orion
=============

Application-wide enumerations.

This module defines strongly typed enumerations used throughout
Project Orion. Enums eliminate "magic strings", improve readability,
and provide better IDE support.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from enum import Enum, auto


# =============================================================================
# Application
# =============================================================================


class ApplicationState(Enum):
    """
    Orion application lifecycle states.
    """

    STARTING = auto()
    INITIALIZING = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()
    FAILED = auto()


# =============================================================================
# Deployment
# =============================================================================


class DeploymentPhase(Enum):
    """
    High-level deployment phases.
    """

    RECOVERY = auto()
    PREPARATION = auto()
    PROVISIONING = auto()
    BOOTSTRAP = auto()
    COMPLETE = auto()


class DeploymentStatus(Enum):
    """
    Deployment execution status.
    """

    PENDING = auto()
    RUNNING = auto()
    SUCCESS = auto()
    FAILED = auto()
    CANCELLED = auto()


# =============================================================================
# Workflow
# =============================================================================


class WorkflowState(Enum):
    """
    Technician workflow state.
    """

    IDLE = auto()
    WAITING = auto()
    RUNNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()


# =============================================================================
# Logging
# =============================================================================


class LogLevel(Enum):
    """
    Orion logging levels.
    """

    DEBUG = auto()
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


# =============================================================================
# Hardware
# =============================================================================


class HardwareHealth(Enum):
    """
    Hardware health assessment.
    """

    UNKNOWN = auto()
    HEALTHY = auto()
    WARNING = auto()
    CRITICAL = auto()
    FAILED = auto()


class SMARTStatus(Enum):
    """
    SMART device health.
    """

    UNKNOWN = auto()
    PASSED = auto()
    FAILED = auto()


class BatteryHealth(Enum):
    """
    Battery condition.
    """

    UNKNOWN = auto()
    GOOD = auto()
    FAIR = auto()
    POOR = auto()
    REPLACE = auto()


# =============================================================================
# Networking
# =============================================================================


class NetworkStatus(Enum):
    """
    Network connection state.
    """

    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    FAILED = auto()


class EthernetStatus(Enum):
    """
    Ethernet cable state.
    """

    UNPLUGGED = auto()
    LINK_DETECTED = auto()
    ACTIVE = auto()


# =============================================================================
# Inspection
# =============================================================================


class InspectionResult(Enum):
    """
    Hardware inspection outcome.
    """

    PASS = auto()
    WARNING = auto()
    FAIL = auto()


# =============================================================================
# Benchmark
# =============================================================================


class BenchmarkStatus(Enum):
    """
    Benchmark execution state.
    """

    NOT_STARTED = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()


# =============================================================================
# Event System
# =============================================================================


class EventType(Enum):
    """
    Standard Orion event types.
    """

    APPLICATION_STARTING = auto()
    APPLICATION_STARTED = auto()
    APPLICATION_STOPPING = auto()
    APPLICATION_STOPPED = auto()

    INITIALIZATION_STARTED = auto()
    INITIALIZATION_COMPLETED = auto()
    INITIALIZATION_FAILED = auto()

    SHUTDOWN_STARTED = auto()
    SHUTDOWN_COMPLETED = auto()
    SHUTDOWN_FAILED = auto()

    CONFIGURATION_LOADED = auto()

    SERVICE_REGISTERED = auto()

    DEPLOYMENT_STARTED = auto()
    DEPLOYMENT_COMPLETED = auto()

    CONFIGURATION_LOADING = auto()
    CONFIGURATION_LOAD_FAILED = auto()

    CONFIGURATION_VALIDATION_STARTED = auto()
    CONFIGURATION_VALIDATED = auto()
    CONFIGURATION_VALIDATION_FAILED = auto()

    CONFIGURATION_CHANGED = auto()
    CONFIGURATION_SAVED = auto()

    DEPLOYMENT_FAILED = auto()
    DEPLOYMENT_CANCELLED = auto()

    RECOVERY_STARTED = auto()
    RECOVERY_COMPLETED = auto()

    PREPARATION_STARTED = auto()
    PREPARATION_COMPLETED = auto()

    PROVISIONING_STARTED = auto()
    PROVISIONING_COMPLETED = auto()

    BOOTSTRAP_STARTED = auto()
    BOOTSTRAP_COMPLETED = auto()

    HARDWARE_INSPECTION_STARTED = auto()
    HARDWARE_INSPECTION_COMPLETED = auto()
    HARDWARE_INSPECTION_FAILED = auto()

    CPU_DETECTED = auto()
    MEMORY_DETECTED = auto()
    STORAGE_DETECTED = auto()

    SMART_CHECK_COMPLETED = auto()

    BATTERY_DETECTED = auto()
    BATTERY_HEALTH_WARNING = auto()

    BIOS_DETECTED = auto()
    VIRTUALIZATION_DETECTED = auto()

    HARDWARE_ASSESSMENT_COMPLETED = auto()

    ERROR = auto()

    # =============================================================================
    # Networking Events
    # =============================================================================

    ETHERNET_DETECTED = auto()
    ETHERNET_DISCONNECTED = auto()

    IP_ADDRESS_ASSIGNED = auto()
    IP_CONFIGURATION_FAILED = auto()

    GATEWAY_REACHABLE = auto()
    GATEWAY_UNREACHABLE = auto()

    DNS_RESOLVED = auto()
    DNS_RESOLUTION_FAILED = auto()

    CONNECTIVITY_TEST_STARTED = auto()
    CONNECTIVITY_TEST_PASSED = auto()
    CONNECTIVITY_TEST_FAILED = auto()

    SSH_CONNECTION_ESTABLISHED = auto()
    SSH_CONNECTION_FAILED = auto()

    CLUSTER_JOIN_STARTED = auto()
    CLUSTER_JOINED = auto()
    CLUSTER_JOIN_FAILED = auto()
class EventSource(Enum):
    """
    Known Orion event publishers.
    """

    CORE_APPLICATION = auto()
    CORE_STARTUP = auto()
    CORE_SHUTDOWN = auto()

    CONFIG_MANAGER = auto()

    SERVICE_CONTAINER = auto()

    DEPLOYMENT_MANAGER = auto()

    INSPECTION_MANAGER = auto()

    RECOVERY_MANAGER = auto()

    PREPARATION_MANAGER = auto()

    PROVISIONING_MANAGER = auto()

    BOOTSTRAP_MANAGER = auto()

    NETWORK_MANAGER = auto()

    TECHNICIAN_CONSOLE = auto()


# =============================================================================
# Proxmox
# =============================================================================


class NodeRole(Enum):
    """
    Proxmox node role.
    """

    STANDALONE = auto()
    CLUSTER_MEMBER = auto()
    CLUSTER_MASTER = auto()


# =============================================================================
# BIOS
# =============================================================================


class VirtualizationState(Enum):
    """
    CPU virtualization state.
    """

    ENABLED = auto()
    DISABLED = auto()
    UNKNOWN = auto()


# =============================================================================
# Storage
# =============================================================================


class DiskHealth(Enum):
    """
    Overall disk health.
    """

    UNKNOWN = auto()
    GOOD = auto()
    WARNING = auto()
    FAILED = auto()


class SanitizationMethod(Enum):
    """
    Supported disk sanitization methods.
    """

    QUICK = auto()
    FULL = auto()
    SECURE_ERASE = auto()