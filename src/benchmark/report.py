"""
Project Orion
=============

Benchmark Report

Defines the BenchmarkReport model used to aggregate
all benchmark results into a single object.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class BenchmarkReport:
    """
    Represents the complete benchmark report for a
    single machine.
    """

    # ---------------------------------------------------------
    # Metadata
    # ---------------------------------------------------------

    timestamp: datetime = field(default_factory=datetime.utcnow)

    hostname: str = ""

    benchmark_version: str = "1.0"

    successful: bool = True

    # ---------------------------------------------------------
    # Benchmark Results
    # ---------------------------------------------------------

    cpu: dict[str, Any] = field(default_factory=dict)

    gpu: dict[str, Any] = field(default_factory=dict)

    memory: dict[str, Any] = field(default_factory=dict)

    storage: dict[str, Any] = field(default_factory=dict)

    network: dict[str, Any] = field(default_factory=dict)

    thermal: dict[str, Any] = field(default_factory=dict)

    # ---------------------------------------------------------
    # Summary
    # ---------------------------------------------------------

    overall_score: int = 0

    notes: list[str] = field(default_factory=list)

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    def add_note(self, note: str) -> None:
        """
        Add a note to the report.
        """

        self.notes.append(note)

    def has_failures(self) -> bool:
        """
        Returns True if any benchmark reported a
        non-PASS status.
        """

        benchmarks = (
            self.cpu,
            self.gpu,
            self.memory,
            self.storage,
            self.network,
            self.thermal,
        )

        for benchmark in benchmarks:
            if benchmark and benchmark.get("status") != "PASS":
                return True

        return False

    def calculate_overall_score(self) -> int:
        """
        Calculate an overall benchmark score by
        summing the individual subsystem scores.
        """

        total = 0

        for benchmark in (
            self.cpu,
            self.gpu,
            self.memory,
            self.storage,
            self.network,
            self.thermal,
        ):
            if benchmark:
                total += int(benchmark.get("score", 0))

        self.overall_score = total

        return total

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the report into a serializable
        dictionary.
        """

        return {
            "timestamp": self.timestamp.isoformat(),
            "hostname": self.hostname,
            "benchmark_version": self.benchmark_version,
            "successful": self.successful,
            "cpu": self.cpu,
            "gpu": self.gpu,
            "memory": self.memory,
            "storage": self.storage,
            "network": self.network,
            "thermal": self.thermal,
            "overall_score": self.overall_score,
            "notes": list(self.notes),
        }