"""
Project Orion
=============

CPU Benchmark

Provides CPU benchmarking for Project Orion.

This module measures processor performance using
simple, repeatable workloads that require no
external benchmarking software.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

import math
import statistics
import time
from typing import Any


class CPUBenchmark:
    """
    CPU benchmark implementation.
    """

    def __init__(self) -> None:
        self.iterations = 1_000_000
        self.samples = 3

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """
        Execute the CPU benchmark suite.
        """

        timings = []

        for _ in range(self.samples):
            timings.append(self._floating_point_test())

        average = statistics.mean(timings)

        return {
            "benchmark": "CPU",
            "samples": self.samples,
            "iterations": self.iterations,
            "average_seconds": round(average, 4),
            "minimum_seconds": round(min(timings), 4),
            "maximum_seconds": round(max(timings), 4),
            "score": self._calculate_score(average),
            "status": "PASS",
        }

    # ---------------------------------------------------------
    # Internal Benchmarks
    # ---------------------------------------------------------

    def _floating_point_test(self) -> float:
        """
        Floating-point workload.
        """

        start = time.perf_counter()

        value = 0.0

        for i in range(1, self.iterations):
            value += math.sqrt(i)

        # Prevent optimization
        _ = value

        end = time.perf_counter()

        return end - start

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    @staticmethod
    def _calculate_score(seconds: float) -> int:
        """
        Produce a simple benchmark score.

        Faster execution results in a higher score.
        """

        if seconds <= 0:
            return 0

        return int(10000 / seconds)