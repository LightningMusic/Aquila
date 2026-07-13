"""
Project Orion
=============

Memory Benchmark

Provides memory benchmarking for Project Orion.

This benchmark measures memory allocation,
sequential access, random access, and copy
performance using only the Python standard library.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

import random
import statistics
import time
from typing import Any


class MemoryBenchmark:
    """
    Executes lightweight RAM benchmarks.
    """

    DEFAULT_BLOCK_SIZE = 32 * 1024 * 1024  # 32 MiB
    DEFAULT_SAMPLES = 3

    def __init__(
        self,
        block_size: int = DEFAULT_BLOCK_SIZE,
        samples: int = DEFAULT_SAMPLES,
    ) -> None:

        self.block_size = block_size
        self.samples = samples

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """
        Execute all memory benchmarks.
        """

        allocation = self._benchmark(self._allocation_test)
        sequential = self._benchmark(self._sequential_test)
        random_access = self._benchmark(self._random_access_test)
        copy = self._benchmark(self._copy_test)

        return {
            "benchmark": "Memory",
            "block_size_bytes": self.block_size,
            "samples": self.samples,
            "allocation_seconds": round(allocation["average"], 4),
            "sequential_seconds": round(sequential["average"], 4),
            "random_access_seconds": round(random_access["average"], 4),
            "copy_seconds": round(copy["average"], 4),
            "score": self._score(
                allocation["average"],
                sequential["average"],
                random_access["average"],
                copy["average"],
            ),
            "status": "PASS",
        }

    # ---------------------------------------------------------
    # Benchmark Helpers
    # ---------------------------------------------------------

    def _benchmark(self, func) -> dict[str, float]:
        """
        Execute a benchmark multiple times.
        """

        timings = []

        for _ in range(self.samples):
            timings.append(func())

        return {
            "average": statistics.mean(timings),
            "minimum": min(timings),
            "maximum": max(timings),
        }

    # ---------------------------------------------------------
    # Tests
    # ---------------------------------------------------------

    def _allocation_test(self) -> float:
        """
        Allocate a large memory block.
        """

        start = time.perf_counter()

        data = bytearray(self.block_size)

        _ = len(data)

        end = time.perf_counter()

        return end - start

    def _sequential_test(self) -> float:
        """
        Sequential write benchmark.
        """

        data = bytearray(self.block_size)

        start = time.perf_counter()

        for i in range(len(data)):
            data[i] = i & 0xFF

        end = time.perf_counter()

        return end - start

    def _random_access_test(self) -> float:
        """
        Random write benchmark.
        """

        data = bytearray(self.block_size)

        indices = random.sample(
            range(len(data)),
            min(100_000, len(data)),
        )

        start = time.perf_counter()

        for index in indices:
            data[index] = index & 0xFF

        end = time.perf_counter()

        return end - start

    def _copy_test(self) -> float:
        """
        Memory copy benchmark.
        """

        source = bytearray(self.block_size)

        start = time.perf_counter()

        destination = source[:]

        _ = len(destination)

        end = time.perf_counter()

        return end - start

    # ---------------------------------------------------------
    # Scoring
    # ---------------------------------------------------------

    @staticmethod
    def _score(
        allocation: float,
        sequential: float,
        random_access: float,
        copy: float,
    ) -> int:
        """
        Produce a simple performance score.
        """

        total = (
            allocation
            + sequential
            + random_access
            + copy
        )

        if total <= 0:
            return 0

        return int(40000 / total)