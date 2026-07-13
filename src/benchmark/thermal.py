"""
Project Orion
=============

Thermal Benchmark

Provides lightweight thermal monitoring for Project Orion.

This module samples system temperatures before and after
benchmark execution. It is intended to detect obvious
thermal problems without placing unnecessary stress on
the hardware.

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


class ThermalBenchmark:
    """
    Performs lightweight thermal monitoring.
    """

    SAMPLE_COUNT = 5
    SAMPLE_DELAY = 1.0

    def __init__(self) -> None:
        pass

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """
        Execute the thermal benchmark.
        """

        samples: list[float] = []

        for _ in range(self.SAMPLE_COUNT):

            temperature = self._read_temperature()

            if temperature is not None:
                samples.append(temperature)

            time.sleep(self.SAMPLE_DELAY)

        if not samples:

            return {
                "benchmark": "Thermal",
                "temperature_supported": False,
                "status": "UNSUPPORTED",
            }

        minimum = min(samples)
        maximum = max(samples)
        average = sum(samples) / len(samples)

        return {
            "benchmark": "Thermal",
            "temperature_supported": True,
            "samples": len(samples),
            "minimum_celsius": round(minimum, 1),
            "maximum_celsius": round(maximum, 1),
            "average_celsius": round(average, 1),
            "thermal_delta": round(maximum - minimum, 1),
            "status": self._status(maximum),
        }

    # ---------------------------------------------------------
    # Temperature Detection
    # ---------------------------------------------------------

    def _read_temperature(self) -> float | None:
        """
        Read CPU temperature.

        Returns None if unsupported.
        """

        system = platform.system()

        if system == "Windows":
            return self._windows_temperature()

        if system == "Linux":
            return self._linux_temperature()

        return None

    def _windows_temperature(self) -> float | None:
        """
        Best-effort temperature retrieval using WMI.

        Note:
            Many Windows systems do not expose CPU
            temperature through WMI.
        """

        try:

            result = subprocess.run(
                [
                    "wmic",
                    "/namespace:\\\\root\\wmi",
                    "PATH",
                    "MSAcpi_ThermalZoneTemperature",
                    "get",
                    "CurrentTemperature",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            for line in result.stdout.splitlines():

                line = line.strip()

                if not line.isdigit():
                    continue

                kelvin_tenths = int(line)

                return (kelvin_tenths / 10.0) - 273.15

        except Exception:
            pass

        return None

    def _linux_temperature(self) -> float | None:
        """
        Read temperature from the Linux thermal subsystem.
        """

        try:

            result = subprocess.run(
                ["cat", "/sys/class/thermal/thermal_zone0/temp"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            value = result.stdout.strip()

            if value.isdigit():

                return int(value) / 1000.0

        except Exception:
            pass

        return None

    # ---------------------------------------------------------
    # Status
    # ---------------------------------------------------------

    @staticmethod
    def _status(maximum: float) -> str:
        """
        Determine thermal health.
        """

        if maximum >= 90:
            return "CRITICAL"

        if maximum >= 80:
            return "WARNING"

        return "PASS"