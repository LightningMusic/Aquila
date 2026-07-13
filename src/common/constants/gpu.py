"""
Project Orion
=============

GPU Constants

Shared constants used by the GPU subsystem.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

# ==========================================================
# Vendors
# ==========================================================

NVIDIA = "NVIDIA"

AMD = "AMD"

INTEL = "Intel"

MICROSOFT = "Microsoft"

UNKNOWN_VENDOR = "Unknown"

GPU_VENDORS = (
    NVIDIA,
    AMD,
    INTEL,
    MICROSOFT,
)

# ==========================================================
# Device Types
# ==========================================================

INTEGRATED_GPU = "Integrated"

DEDICATED_GPU = "Dedicated"

VIRTUAL_GPU = "Virtual"

EXTERNAL_GPU = "External"

UNKNOWN_GPU_TYPE = "Unknown"

# ==========================================================
# Compute APIs
# ==========================================================

CUDA = "CUDA"

OPENCL = "OpenCL"

VULKAN = "Vulkan"

DIRECTX = "DirectX"

DIRECTCOMPUTE = "DirectCompute"

ROCM = "ROCm"

ONEAPI = "oneAPI"

# ==========================================================
# Video APIs
# ==========================================================

NVENC = "NVENC"

NVDEC = "NVDEC"

VAAPI = "VAAPI"

VDPAU = "VDPAU"

VIDEO_TOOLBOX = "VideoToolbox"

QUICK_SYNC = "Quick Sync"

AMF = "AMF"

# ==========================================================
# PCI Express
# ==========================================================

PCIE_GEN1 = "PCIe Gen1"

PCIE_GEN2 = "PCIe Gen2"

PCIE_GEN3 = "PCIe Gen3"

PCIE_GEN4 = "PCIe Gen4"

PCIE_GEN5 = "PCIe Gen5"

PCIE_GEN6 = "PCIe Gen6"

# ==========================================================
# Driver Status
# ==========================================================

DRIVER_LOADED = "Loaded"

DRIVER_MISSING = "Missing"

DRIVER_UNKNOWN = "Unknown"

# ==========================================================
# Temperature
# ==========================================================

GPU_MIN_TEMPERATURE = 0

GPU_WARNING_TEMPERATURE = 80

GPU_CRITICAL_TEMPERATURE = 90

GPU_MAX_TEMPERATURE = 110

# ==========================================================
# Memory
# ==========================================================

BYTES_PER_MEGABYTE = 1024 * 1024

BYTES_PER_GIGABYTE = 1024 * 1024 * 1024

# ==========================================================
# Feature Flags
# ==========================================================

FEATURE_CUDA = "cuda"

FEATURE_OPENCL = "opencl"

FEATURE_ROCM = "rocm"

FEATURE_VULKAN = "vulkan"

FEATURE_VIDEO_ENCODE = "video_encode"

FEATURE_VIDEO_DECODE = "video_decode"

FEATURE_PASSTHROUGH = "passthrough"

FEATURE_SRIOV = "sr_iov"

FEATURE_IOMMU = "iommu"

# ==========================================================
# Export
# ==========================================================

__all__ = [
    "AMD",
    "AMF",
    "BYTES_PER_GIGABYTE",
    "BYTES_PER_MEGABYTE",
    "CUDA",
    "DEDICATED_GPU",
    "DIRECTCOMPUTE",
    "DIRECTX",
    "DRIVER_LOADED",
    "DRIVER_MISSING",
    "DRIVER_UNKNOWN",
    "EXTERNAL_GPU",
    "FEATURE_CUDA",
    "FEATURE_IOMMU",
    "FEATURE_OPENCL",
    "FEATURE_PASSTHROUGH",
    "FEATURE_ROCM",
    "FEATURE_SRIOV",
    "FEATURE_VIDEO_DECODE",
    "FEATURE_VIDEO_ENCODE",
    "FEATURE_VULKAN",
    "GPU_CRITICAL_TEMPERATURE",
    "GPU_MAX_TEMPERATURE",
    "GPU_MIN_TEMPERATURE",
    "GPU_VENDORS",
    "GPU_WARNING_TEMPERATURE",
    "INTEGRATED_GPU",
    "INTEL",
    "MICROSOFT",
    "NVDEC",
    "NVENC",
    "NVIDIA",
    "ONEAPI",
    "OPENCL",
    "PCIE_GEN1",
    "PCIE_GEN2",
    "PCIE_GEN3",
    "PCIE_GEN4",
    "PCIE_GEN5",
    "PCIE_GEN6",
    "QUICK_SYNC",
    "ROCM",
    "UNKNOWN_GPU_TYPE",
    "UNKNOWN_VENDOR",
    "VAAPI",
    "VDPAU",
    "VIDEO_TOOLBOX",
    "VIRTUAL_GPU",
    "VULKAN",
]