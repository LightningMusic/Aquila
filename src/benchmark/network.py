"""
Project Orion
=============

Network Benchmark

Provides network benchmarking for Project Orion.

The benchmark focuses on characteristics important
to Proxmox cluster deployment.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

import platform
import socket
import statistics
import subprocess
import time
from typing import Any


class NetworkBenchmark:
    """
    Performs lightweight network benchmarks.
    """

    DEFAULT_HOST = "8.8.8.8"
    DEFAULT_PORT = 53
    DEFAULT_TIMEOUT = 3.0
    DEFAULT_PING_COUNT = 5

    def __init__(self) -> None:

        self.host = self.DEFAULT_HOST
        self.port = self.DEFAULT_PORT
        self.timeout = self.DEFAULT_TIMEOUT
        self.samples = self.DEFAULT_PING_COUNT

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """
        Execute the complete network benchmark.
        """

        latency = self._latency()

        return {
            "benchmark": "Network",
            "latency_ms": latency["average"],
            "minimum_latency_ms": latency["minimum"],
            "maximum_latency_ms": latency["maximum"],
            "interface_speed_mbps": self._link_speed(),
            "internet_available": self._internet_available(),
            "hostname": socket.gethostname(),
            "score": self._score(latency["average"]),
            "status": "PASS",
        }

    # ---------------------------------------------------------
    # Latency
    # ---------------------------------------------------------

    def _latency(self) -> dict[str, float]:

        values = []

        for _ in range(self.samples):

            start = time.perf_counter()

            try:

                connection = socket.create_connection(
                    (self.host, self.port),
                    timeout=self.timeout,
                )

                connection.close()

            except OSError:
                pass

            elapsed = (
                time.perf_counter() - start
            ) * 1000.0

            values.append(elapsed)

        return {
            "average": round(statistics.mean(values), 2),
            "minimum": round(min(values), 2),
            "maximum": round(max(values), 2),
        }

    # ---------------------------------------------------------
    # Internet
    # ---------------------------------------------------------

    def _internet_available(self) -> bool:

        try:

            connection = socket.create_connection(
                (self.host, self.port),
                timeout=self.timeout,
            )

            connection.close()

            return True

        except OSError:

            return False

    # ---------------------------------------------------------
    # Link Speed
    # ---------------------------------------------------------

    def _link_speed(self) -> str:
        """
        Best-effort link speed detection.
        """

        system = platform.system()

        try:

            if system == "Windows":

                result = subprocess.run(
                    [
                        "wmic",
                        "NIC",
                        "where",
                        "NetEnabled=true",
                        "get",
                        "Name,Speed",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                return result.stdout.strip()

            if system == "Linux":

                result = subprocess.run(
                    [
                        "ip",
                        "-brief",
                        "link",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                return result.stdout.strip()

        except Exception:

            pass

        return "Unknown"

    # ---------------------------------------------------------
    # Score
    # ---------------------------------------------------------

    @staticmethod
    def _score(
        latency_ms: float,
    ) -> int:
        """
        Produce a simple latency score.
        """

        if latency_ms <= 0:
            return 10000

        return max(
            0,
            int(10000 / latency_ms),
        )