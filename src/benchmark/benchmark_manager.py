"""
Project Aquila
=============

Benchmark Manager

Coordinates all benchmark modules and produces a
single benchmark report for Project Aquila.

Every category benchmark's own ``run()`` result already carries its
own elapsed-time measurement (CPU's ``average_seconds``, memory's
``*_seconds``, storage's ``sequential_write``/``sequential_read``/
``random_access`` seconds, GPU's ``enumeration_seconds``, network's
``latency_ms``) -- ``BenchmarkReport`` persists each of those results
unchanged, so REQ-BENCH-006 ("The Benchmark Engine shall record
benchmark duration.") is satisfied per-category rather than by a
single top-level timer here.

The ``run_cpu``/``run_gpu``/``run_memory``/``run_storage``/
``run_network``/``run_thermal`` methods below let a caller execute
only a subset of categories instead of the full ``run()`` suite --
this is REQ-BENCH-009's "Benchmark execution shall be configurable.":
which categories actually run for a given deployment is a decision
made by the caller (per deployment/benchmark policy), not hardcoded
here.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import socket
from typing import Any

from benchmark.cpu import CPUBenchmark
from benchmark.gpu import GPUBenchmark
from benchmark.memory import MemoryBenchmark
from benchmark.network import NetworkBenchmark
from benchmark.report import BenchmarkReport
from benchmark.storage import StorageBenchmark
from benchmark.thermal import ThermalBenchmark


class BenchmarkManager:
    """
    Coordinates execution of the benchmark subsystem.
    """

    def __init__(self) -> None:

        self.cpu = CPUBenchmark()
        self.gpu = GPUBenchmark()
        self.memory = MemoryBenchmark()
        self.storage = StorageBenchmark()
        self.network = NetworkBenchmark()
        self.thermal = ThermalBenchmark()

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def run(self) -> BenchmarkReport:
        """
        Execute every benchmark and return the final report.
        """

        report = BenchmarkReport()

        report.hostname = socket.gethostname()

        report.cpu = self._execute(self.cpu)

        report.gpu = self._execute(self.gpu)

        report.memory = self._execute(self.memory)

        report.storage = self._execute(self.storage)

        report.network = self._execute(self.network)

        report.thermal = self._execute(self.thermal)

        report.calculate_overall_score()

        report.successful = not report.has_failures()

        return report

    # ---------------------------------------------------------
    # Individual Benchmarks
    # ---------------------------------------------------------

    def run_cpu(self) -> dict[str, Any]:
        return self.cpu.run()

    def run_gpu(self) -> dict[str, Any]:
        return self.gpu.run()

    def run_memory(self) -> dict[str, Any]:
        return self.memory.run()

    def run_storage(self) -> dict[str, Any]:
        return self.storage.run()

    def run_network(self) -> dict[str, Any]:
        return self.network.run()

    def run_thermal(self) -> dict[str, Any]:
        return self.thermal.run()

    # ---------------------------------------------------------
    # Internal Helpers
    # ---------------------------------------------------------

    @staticmethod
    def _execute(
        benchmark: Any,
    ) -> dict[str, Any]:
        """
        Execute a benchmark safely.

        Any exception is converted into a benchmark
        failure so that the remaining benchmarks
        continue executing.
        """

        try:

            return benchmark.run()

        except Exception as exc:

            return {
                "benchmark": benchmark.__class__.__name__,
                "status": "FAILED",
                "error": str(exc),
                "score": 0,
            }