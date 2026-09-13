"""
Project Aquila
=============

Benchmark Category Result Model

A single benchmark category's outcome (CPU, GPU, memory, storage,
network, or thermal), as produced by ``benchmark.benchmark_manager.
BenchmarkManager`` and carried inside ``benchmark.report.
BenchmarkReport``. Those already-complete modules represent each
category as a plain ``dict[str, Any]`` with (at minimum) ``"status"``
and ``"score"`` keys -- this model gives the Deployment
Controller/Inventory System a typed, validated view of that same
shape once it crosses the wire as JSON (REQ-BENCH-007: "Benchmark
results shall be submitted to the Deployment Controller"), without
requiring any change to the already-tested ``benchmark/`` package.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, cast


@dataclass(slots=True, frozen=True)
class BenchmarkCategoryResult:
    """One category's result within a submitted benchmark report."""

    status: str = "UNKNOWN"
    score: int = 0
    details: dict[str, Any] = field(default_factory=lambda: {})

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    @classmethod
    def from_dict(cls, data: Any) -> "BenchmarkCategoryResult":
        """
        Build a result from a category's raw dict.

        Never raises: a malformed or empty category (a benchmark that
        did not run, or whose output the sender truncated) becomes an
        honestly-"UNKNOWN" result rather than blocking ingestion of
        the rest of the report -- REQ-BENCH-008 already establishes
        that one benchmark's failure must not cascade into a larger
        one.
        """

        if not isinstance(data, Mapping):
            return cls()

        mapping = cast("Mapping[str, Any]", data)

        status = mapping.get("status")
        status_text = str(status) if isinstance(status, str) else "UNKNOWN"

        score_value = mapping.get("score", 0)
        try:
            score = int(score_value)
        except (TypeError, ValueError):
            score = 0

        details = {
            key: value
            for key, value in mapping.items()
            if key not in ("status", "score")
        }

        return cls(status=status_text, score=score, details=details)

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "score": self.score, **self.details}


__all__ = ["BenchmarkCategoryResult"]
