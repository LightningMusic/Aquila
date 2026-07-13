"""
Project Orion
=============

GPU Exceptions

Exception hierarchy for the GPU subsystem.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from common.exceptions.application import OrionError


class GPUError(OrionError):
    """
    Base class for GPU-related exceptions.
    """


# ==========================================================
# Detection
# ==========================================================


class GPUDetectionError(GPUError):
    """
    Raised when GPU detection fails.
    """


class GPUNoDeviceError(GPUDetectionError):
    """
    Raised when no GPU devices are detected.
    """


class GPUEnumerationError(GPUDetectionError):
    """
    Raised when GPU enumeration fails.
    """


# ==========================================================
# Driver
# ==========================================================


class GPUDriverError(GPUError):
    """
    Base GPU driver exception.
    """


class GPUDriverMissingError(GPUDriverError):
    """
    Raised when no GPU driver is installed.
    """


class GPUDriverLoadError(GPUDriverError):
    """
    Raised when a GPU driver cannot be loaded.
    """


class GPUUnsupportedDriverError(GPUDriverError):
    """
    Raised when the installed driver is unsupported.
    """


# ==========================================================
# Hardware
# ==========================================================


class GPUHardwareError(GPUError):
    """
    Base hardware exception.
    """


class GPUCommunicationError(GPUHardwareError):
    """
    Raised when the GPU cannot be queried.
    """


class GPUCapabilityError(GPUHardwareError):
    """
    Raised when a required GPU capability is unavailable.
    """


class GPUNotSupportedError(GPUHardwareError):
    """
    Raised when the installed GPU is unsupported.
    """


# ==========================================================
# Monitoring
# ==========================================================


class GPUTemperatureError(GPUError):
    """
    Raised when temperature information
    cannot be retrieved.
    """


class GPUOverheatingError(GPUTemperatureError):
    """
    Raised when a GPU exceeds safe limits.
    """


class GPUPowerError(GPUError):
    """
    Raised when GPU power information
    cannot be determined.
    """


class GPUMemoryError(GPUError):
    """
    Raised when VRAM information
    cannot be retrieved.
    """


# ==========================================================
# Virtualization
# ==========================================================


class GPUPassthroughError(GPUError):
    """
    Raised when GPU passthrough fails.
    """


class GPUIOMMUError(GPUError):
    """
    Raised when IOMMU requirements
    are not satisfied.
    """


class GPUSRIOVError(GPUError):
    """
    Raised when SR-IOV configuration fails.
    """


# ==========================================================
# Export
# ==========================================================

__all__ = [
    "GPUCapabilityError",
    "GPUCommunicationError",
    "GPUDetectionError",
    "GPUDriverError",
    "GPUDriverLoadError",
    "GPUDriverMissingError",
    "GPUEnumerationError",
    "GPUError",
    "GPUHardwareError",
    "GPUIOMMUError",
    "GPUMemoryError",
    "GPUNoDeviceError",
    "GPUNotSupportedError",
    "GPUOverheatingError",
    "GPUPassthroughError",
    "GPUPowerError",
    "GPUSRIOVError",
    "GPUUnsupportedDriverError",
    "GPUTemperatureError",
]