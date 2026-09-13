"""
Project Aquila
=============

Benchmark Record Model

The Inventory System's persisted representation of one submitted
benchmark report (REQ-INV-003: "The Inventory System shall record
benchmark results", REQ-BENCH-007/010). Built from the JSON payload
``bootstrap.benchmark.BenchmarkInitiator``/``benchmark.report.
BenchmarkReport.to_dict()`` produces and
``bootstrap.controller_client.DeploymentControllerClient.
submit_benchmark()`` transmits -- this model is the receiving side of
that same contract, deliberately tolerant of the payload's exact
shape (REQ-INV-008: "The Inventory System shall support future
metadata expansion") since the sender is a separately-versioned
subsystem this model does not import from.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, cast

from models.benchmark.result import BenchmarkCategoryResult

_CATEGORIES = ("cpu", "gpu", "memory", "storage", "network", "thermal")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return _utcnow()


@dataclass(slots=True)
class BenchmarkRecord:
    """A stored benchmark result, associated with one inventory node."""

    node_identifier: str
    reported_at: datetime = field(default_factory=_utcnow)
    received_at: datetime = field(default_factory=_utcnow)

    hostname: str = ""
    benchmark_version: str = ""
    successful: bool = True
    overall_score: int = 0
    notes: list[str] = field(default_factory=lambda: [])

    categories: dict[str, BenchmarkCategoryResult] = field(
        default_factory=lambda: {}
    )

    def category(self, name: str) -> BenchmarkCategoryResult:
        """Return one category's result, or an empty/unknown one."""

        return self.categories.get(name, BenchmarkCategoryResult())

    @classmethod
    def from_payload(
        cls, node_identifier: str, payload: Mapping[str, Any]
    ) -> "BenchmarkRecord":
        """
        Build a record from a submitted ``BenchmarkReport.to_dict()``
        payload (REQ-BENCH-007).

        Missing or malformed fields degrade to safe defaults rather
        than raising -- REQ-CTRL-010/011 require every deployment
        session (including a benchmark submission with an unexpected
        shape) to be recorded, not silently dropped over a formatting
        surprise.
        """

        categories: dict[str, BenchmarkCategoryResult] = {
            name: BenchmarkCategoryResult.from_dict(payload.get(name))
            for name in _CATEGORIES
            if name in payload
        }

        overall_score = payload.get("overall_score", 0)
        try:
            score = int(overall_score)
        except (TypeError, ValueError):
            score = 0

        notes_value: Any = payload.get("notes") or []
        notes: list[str] = (
            [str(note) for note in cast("list[Any]", notes_value)]
            if isinstance(notes_value, list)
            else []
        )

        return cls(
            node_identifier=node_identifier,
            reported_at=_parse_timestamp(payload.get("timestamp")),
            hostname=str(payload.get("hostname") or ""),
            benchmark_version=str(payload.get("benchmark_version") or ""),
            successful=bool(payload.get("successful", True)),
            overall_score=score,
            notes=notes,
            categories=categories,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_identifier": self.node_identifier,
            "reported_at": self.reported_at.isoformat(),
            "received_at": self.received_at.isoformat(),
            "hostname": self.hostname,
            "benchmark_version": self.benchmark_version,
            "successful": self.successful,
            "overall_score": self.overall_score,
            "notes": list(self.notes),
            **{
                name: result.to_dict()
                for name, result in self.categories.items()
            },
        }


__all__ = ["BenchmarkRecord"]
