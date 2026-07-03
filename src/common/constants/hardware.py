"""
Project Orion
=============

Hardware Constants

Defines hardware-related constants used throughout
Project Orion.

This module centralizes default hardware limits,
thresholds, identifiers, and capability requirements.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

# ----------------------------------------------------------------------
# CPU
# ----------------------------------------------------------------------

CPU_WARNING_TEMPERATURE_C = 80

CPU_CRITICAL_TEMPERATURE_C = 90

CPU_MAX_UTILIZATION_PERCENT = 100

CPU_IDLE_PERCENT = 5

MINIMUM_CPU_CORES = 2

MINIMUM_CPU_THREADS = 2

# ----------------------------------------------------------------------
# Memory
# ----------------------------------------------------------------------

MINIMUM_MEMORY_GB = 4

RECOMMENDED_MEMORY_GB = 8

MEMORY_WARNING_PERCENT = 85

MEMORY_CRITICAL_PERCENT = 95

# ----------------------------------------------------------------------
# Storage
# ----------------------------------------------------------------------

MINIMUM_STORAGE_GB = 64

RECOMMENDED_STORAGE_GB = 128

MINIMUM_FREE_SPACE_PERCENT = 10

SECTOR_SIZE_BYTES = 512

DEFAULT_BLOCK_SIZE_KB = 1024

# ----------------------------------------------------------------------
# Battery
# ----------------------------------------------------------------------

BATTERY_LOW_PERCENT = 20

BATTERY_CRITICAL_PERCENT = 10

BATTERY_TARGET_CHARGE_PERCENT = 80

BATTERY_MINIMUM_CHARGE_PERCENT = 50

BATTERY_HEALTH_WARNING_PERCENT = 70

BATTERY_HEALTH_CRITICAL_PERCENT = 50

# ----------------------------------------------------------------------
# SMART
# ----------------------------------------------------------------------

SMART_HEALTH_PASSED = "PASSED"

SMART_HEALTH_FAILED = "FAILED"

SMART_HEALTH_UNKNOWN = "UNKNOWN"

MAX_REALLOCATED_SECTORS = 0

MAX_PENDING_SECTORS = 0

MAX_UNCORRECTABLE_SECTORS = 0

# ----------------------------------------------------------------------
# Networking
# ----------------------------------------------------------------------

MINIMUM_ETHERNET_SPEED_MBPS = 100

RECOMMENDED_ETHERNET_SPEED_MBPS = 1000

DEFAULT_NETWORK_INTERFACE = "eth0"

ETHERNET_REQUIRED = True

# ----------------------------------------------------------------------
# BIOS
# ----------------------------------------------------------------------

REQUIRE_UEFI = True

REQUIRE_VIRTUALIZATION = True

REQUIRE_SECURE_BOOT_DISABLED = True

REQUIRE_AC_POWER = True

# ----------------------------------------------------------------------
# Virtualization
# ----------------------------------------------------------------------

INTEL_VT_X = "Intel VT-x"

AMD_V = "AMD-V"

IOMMU = "IOMMU"

NESTED_VIRTUALIZATION = "Nested Virtualization"

# ----------------------------------------------------------------------
# Benchmark Requirements
# ----------------------------------------------------------------------

DEFAULT_CPU_BENCHMARK_SECONDS = 60

DEFAULT_MEMORY_BENCHMARK_SECONDS = 60

DEFAULT_STORAGE_BENCHMARK_SECONDS = 60

DEFAULT_NETWORK_BENCHMARK_SECONDS = 30

# ----------------------------------------------------------------------
# Hardware Status
# ----------------------------------------------------------------------

STATUS_UNKNOWN = "Unknown"

STATUS_HEALTHY = "Healthy"

STATUS_WARNING = "Warning"

STATUS_CRITICAL = "Critical"

STATUS_FAILED = "Failed"

# ----------------------------------------------------------------------
# Device Types
# ----------------------------------------------------------------------

DEVICE_CPU = "cpu"

DEVICE_MEMORY = "memory"

DEVICE_STORAGE = "storage"

DEVICE_NETWORK = "network"

DEVICE_BATTERY = "battery"

DEVICE_BIOS = "bios"

DEVICE_GPU = "gpu"

DEVICE_USB = "usb"

# ----------------------------------------------------------------------
# Storage Types
# ----------------------------------------------------------------------

HDD = "HDD"

SSD = "SSD"

NVME = "NVMe"

USB = "USB"

SD_CARD = "SD Card"

UNKNOWN_STORAGE = "Unknown"

# ----------------------------------------------------------------------
# Memory Units
# ----------------------------------------------------------------------

KIB = 1024

MIB = 1024 * KIB

GIB = 1024 * MIB

TIB = 1024 * GIB

# ----------------------------------------------------------------------
# Public Exports
# ----------------------------------------------------------------------

__all__ = [
    "AMD_V",
    "BATTERY_CRITICAL_PERCENT",
    "BATTERY_HEALTH_CRITICAL_PERCENT",
    "BATTERY_HEALTH_WARNING_PERCENT",
    "BATTERY_LOW_PERCENT",
    "BATTERY_MINIMUM_CHARGE_PERCENT",
    "BATTERY_TARGET_CHARGE_PERCENT",
    "CPU_CRITICAL_TEMPERATURE_C",
    "CPU_IDLE_PERCENT",
    "CPU_MAX_UTILIZATION_PERCENT",
    "CPU_WARNING_TEMPERATURE_C",
    "DEFAULT_BLOCK_SIZE_KB",
    "DEFAULT_CPU_BENCHMARK_SECONDS",
    "DEFAULT_MEMORY_BENCHMARK_SECONDS",
    "DEFAULT_NETWORK_BENCHMARK_SECONDS",
    "DEFAULT_STORAGE_BENCHMARK_SECONDS",
    "DEFAULT_NETWORK_INTERFACE",
    "DEVICE_BATTERY",
    "DEVICE_BIOS",
    "DEVICE_CPU",
    "DEVICE_GPU",
    "DEVICE_MEMORY",
    "DEVICE_NETWORK",
    "DEVICE_STORAGE",
    "DEVICE_USB",
    "ETHERNET_REQUIRED",
    "GIB",
    "HDD",
    "INTEL_VT_X",
    "IOMMU",
    "KIB",
    "MAX_PENDING_SECTORS",
    "MAX_REALLOCATED_SECTORS",
    "MAX_UNCORRECTABLE_SECTORS",
    "MEMORY_CRITICAL_PERCENT",
    "MEMORY_WARNING_PERCENT",
    "MIB",
    "MINIMUM_CPU_CORES",
    "MINIMUM_CPU_THREADS",
    "MINIMUM_ETHERNET_SPEED_MBPS",
    "MINIMUM_FREE_SPACE_PERCENT",
    "MINIMUM_MEMORY_GB",
    "MINIMUM_STORAGE_GB",
    "NESTED_VIRTUALIZATION",
    "NVME",
    "RECOMMENDED_ETHERNET_SPEED_MBPS",
    "RECOMMENDED_MEMORY_GB",
    "RECOMMENDED_STORAGE_GB",
    "REQUIRE_AC_POWER",
    "REQUIRE_SECURE_BOOT_DISABLED",
    "REQUIRE_UEFI",
    "REQUIRE_VIRTUALIZATION",
    "SD_CARD",
    "SECTOR_SIZE_BYTES",
    "SMART_HEALTH_FAILED",
    "SMART_HEALTH_PASSED",
    "SMART_HEALTH_UNKNOWN",
    "SSD",
    "STATUS_CRITICAL",
    "STATUS_FAILED",
    "STATUS_HEALTHY",
    "STATUS_UNKNOWN",
    "STATUS_WARNING",
    "TIB",
    "UNKNOWN_STORAGE",
    "USB",
]