"""
Project Orion
=============

Hardware Exceptions

Defines hardware-related exceptions used
throughout Project Orion.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from common.exceptions.application import OrionError


class HardwareError(OrionError):
    """
    Base class for all hardware-related exceptions.
    """


class HardwareInitializationError(HardwareError):
    """
    Raised when the hardware subsystem
    cannot be initialized.
    """


class HardwareDetectionError(HardwareError):
    """
    Raised when hardware detection fails.
    """


class HardwareValidationError(HardwareError):
    """
    Raised when detected hardware fails
    validation.
    """


class HardwareConfigurationError(HardwareError):
    """
    Raised when hardware configuration
    is invalid.
    """


class HardwareCommunicationError(HardwareError):
    """
    Raised when Orion cannot communicate
    with a hardware device.
    """


class HardwareUnsupportedError(HardwareError):
    """
    Raised when unsupported hardware
    is encountered.
    """


class HardwareTimeoutError(HardwareError):
    """
    Raised when a hardware operation
    exceeds its timeout.
    """


class HardwarePermissionError(HardwareError):
    """
    Raised when Orion lacks permission
    to access hardware resources.
    """


class HardwareMonitoringError(HardwareError):
    """
    Raised when hardware monitoring fails.
    """


# ----------------------------------------------------------------------
# CPU
# ----------------------------------------------------------------------


class CpuError(HardwareError):
    """
    Base CPU exception.
    """


class CpuDetectionError(CpuError):
    """
    Raised when CPU detection fails.
    """


class CpuTemperatureError(CpuError):
    """
    Raised when CPU temperature exceeds
    safe limits.
    """


class CpuBenchmarkError(CpuError):
    """
    Raised during CPU benchmarking.
    """


# ----------------------------------------------------------------------
# Memory
# ----------------------------------------------------------------------


class MemoryError(HardwareError):
    """
    Base memory exception.
    """


class MemoryDetectionError(MemoryError):
    """
    Raised when memory detection fails.
    """


class MemoryCapacityError(MemoryError):
    """
    Raised when insufficient memory
    is available.
    """


class MemoryBenchmarkError(MemoryError):
    """
    Raised during memory benchmarking.
    """


# ----------------------------------------------------------------------
# Storage
# ----------------------------------------------------------------------


class StorageError(HardwareError):
    """
    Base storage exception.
    """


class StorageDetectionError(StorageError):
    """
    Raised when storage detection fails.
    """


class StorageHealthError(StorageError):
    """
    Raised when a storage device
    fails health checks.
    """


class SmartError(StorageError):
    """
    Raised when SMART diagnostics fail.
    """


class DiskWipeError(StorageError):
    """
    Raised when disk sanitization fails.
    """


class DiskPartitionError(StorageError):
    """
    Raised when disk partitioning fails.
    """


class FilesystemError(StorageError):
    """
    Raised when filesystem operations fail.
    """


# ----------------------------------------------------------------------
# Network Hardware
# ----------------------------------------------------------------------


class NetworkHardwareError(HardwareError):
    """
    Base network hardware exception.
    """


class NetworkAdapterError(NetworkHardwareError):
    """
    Raised when a network adapter fails.
    """


class EthernetError(NetworkHardwareError):
    """
    Raised when Ethernet hardware fails.
    """


# ----------------------------------------------------------------------
# Battery
# ----------------------------------------------------------------------


class BatteryError(HardwareError):
    """
    Base battery exception.
    """


class BatteryHealthError(BatteryError):
    """
    Raised when battery health
    is below acceptable limits.
    """


class BatteryChargeError(BatteryError):
    """
    Raised when battery charge
    is insufficient.
    """


# ----------------------------------------------------------------------
# BIOS
# ----------------------------------------------------------------------


class BiosError(HardwareError):
    """
    Base BIOS exception.
    """


class BiosConfigurationError(BiosError):
    """
    Raised when BIOS configuration
    is invalid.
    """


class BiosReadError(BiosError):
    """
    Raised when BIOS information
    cannot be read.
    """


class VirtualizationDisabledError(BiosError):
    """
    Raised when virtualization support
    is disabled in firmware.
    """


class SecureBootEnabledError(BiosError):
    """
    Raised when Secure Boot is enabled
    but deployment requires it disabled.
    """


# ----------------------------------------------------------------------
# Virtualization
# ----------------------------------------------------------------------


class VirtualizationError(HardwareError):
    """
    Base virtualization exception.
    """


class VirtualizationSupportError(VirtualizationError):
    """
    Raised when CPU virtualization
    extensions are unavailable.
    """


class IommuError(VirtualizationError):
    """
    Raised when IOMMU configuration
    is invalid.
    """


# ----------------------------------------------------------------------
# Reports
# ----------------------------------------------------------------------


class HardwareReportError(HardwareError):
    """
    Raised when hardware reports
    cannot be generated.
    """


class HardwareExportError(HardwareError):
    """
    Raised when hardware information
    cannot be exported.
    """


__all__ = [
    "BatteryChargeError",
    "BatteryError",
    "BatteryHealthError",
    "BiosConfigurationError",
    "BiosError",
    "BiosReadError",
    "CpuBenchmarkError",
    "CpuDetectionError",
    "CpuError",
    "CpuTemperatureError",
    "DiskPartitionError",
    "DiskWipeError",
    "EthernetError",
    "FilesystemError",
    "HardwareCommunicationError",
    "HardwareConfigurationError",
    "HardwareDetectionError",
    "HardwareError",
    "HardwareExportError",
    "HardwareInitializationError",
    "HardwareMonitoringError",
    "HardwarePermissionError",
    "HardwareReportError",
    "HardwareTimeoutError",
    "HardwareUnsupportedError",
    "HardwareValidationError",
    "IommuError",
    "MemoryBenchmarkError",
    "MemoryCapacityError",
    "MemoryDetectionError",
    "MemoryError",
    "NetworkAdapterError",
    "NetworkHardwareError",
    "SecureBootEnabledError",
    "SmartError",
    "StorageDetectionError",
    "StorageError",
    "StorageHealthError",
    "VirtualizationDisabledError",
    "VirtualizationError",
    "VirtualizationSupportError",
]