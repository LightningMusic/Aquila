"""
Project Orion
=============

GPU Benchmark

Provides lightweight GPU benchmarking and capability
discovery for Project Orion.

This benchmark is designed to run before Proxmox is
installed and therefore avoids vendor-specific SDKs
such as CUDA or ROCm.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

import platform
import subprocess
import time
from typing import Any

from common.exceptions.gpu import GPUDetectionError


class GPUBenchmark:
    """
    GPU benchmark implementation.
    """

    def __init__(self) -> None:
        self.timeout = 10

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """
        Execute the GPU benchmark.
        """

        start = time.perf_counter()

        devices = self._enumerate_gpus()

        elapsed = time.perf_counter() - start

        return {
            "benchmark": "GPU",
            "gpu_count": len(devices),
            "devices": devices,
            "enumeration_seconds": round(elapsed, 4),
            "status": "PASS" if devices else "NO_GPU",
        }

    # ---------------------------------------------------------
    # Detection
    # ---------------------------------------------------------

    def _enumerate_gpus(self) -> list[dict[str, Any]]:
        """
        Enumerate installed GPUs.
        """

        system = platform.system()

        if system == "Windows":
            return self._windows()

        if system == "Linux":
            return self._linux()

        return []

    def _windows(self) -> list[dict[str, Any]]:
        """
        Enumerate GPUs using WMIC.

        Falls back gracefully if unavailable.
        """

        try:

            result = subprocess.run(
                [
                    "wmic",
                    "path",
                    "win32_VideoController",
                    "get",
                    "Name,AdapterRAM,DriverVersion",
                    "/format:csv",
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )

        except Exception as exc:
            raise GPUDetectionError(
                "Unable to enumerate GPU devices."
            ) from exc

        devices = []

        for line in result.stdout.splitlines():

            if "," not in line:
                continue

            if "Name" in line:
                continue

            parts = [p.strip() for p in line.split(",")]

            if len(parts) < 4:
                continue

            devices.append(
                {
                    "name": parts[-2],
                    "driver_version": parts[-1],
                    "memory_bytes": parts[-3],
                }
            )

        return devices

    def _linux(self) -> list[dict[str, Any]]:
        """
        Enumerate GPUs using lspci.
        """

        try:

            result = subprocess.run(
                ["lspci"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )

        except Exception as exc:
            raise GPUDetectionError(
                "Unable to enumerate GPU devices."
            ) from exc

        devices = []

        for line in result.stdout.splitlines():

            if "VGA" in line or "3D controller" in line:

                devices.append(
                    {
                        "name": line.strip(),
                    }
                )

        return devices

    # ---------------------------------------------------------
    # Convenience
    # ---------------------------------------------------------

    def has_gpu(self) -> bool:
        """
        Returns True if one or more GPUs
        are detected.
        """

        return len(self._enumerate_gpus()) > 0

    def gpu_count(self) -> int:
        """
        Returns the number of detected GPUs.
        """

        return len(self._enumerate_gpus())