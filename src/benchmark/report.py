"""
Project Aquila
=============

Benchmark Report

Defines the BenchmarkReport model used to aggregate
all benchmark results into a single object.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utcnow() -> datetime:
    """
    Timezone-aware replacement for the deprecated
    ``datetime.utcnow()`` (see Python's own
    ``datetime`` documentation: naive UTC timestamps
    are deprecated in favor of
    ``datetime.now(timezone.utc)``).
    """

    return datetime.now(timezone.utc)


@dataclass(slots=True)
class BenchmarkReport:
    """
    Represents the complete benchmark report for a
    single machine.
    """

    # ---------------------------------------------------------
    # Metadata
    # ---------------------------------------------------------

    timestamp: datetime = field(default_factory=_utcnow)

    hostname: str = ""

    benchmark_version: str = "1.0"

    successful: bool = True

    # ---------------------------------------------------------
    # Benchmark Results
    # ---------------------------------------------------------

    cpu: dict[str, Any] = field(default_factory=lambda: {})

    gpu: dict[str, Any] = field(default_factory=lambda: {})

    memory: dict[str, Any] = field(default_factory=lambda: {})

    storage: dict[str, Any] = field(default_factory=lambda: {})

    network: dict[str, Any] = field(default_factory=lambda: {})

    thermal: dict[str, Any] = field(default_factory=lambda: {})

    # ---------------------------------------------------------
    # Summary
    # ---------------------------------------------------------

    overall_score: int = 0

    notes: list[str] = field(default_factory=lambda: [])

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