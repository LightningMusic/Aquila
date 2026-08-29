"""
Project Aquila
=============

Benchmark Configuration Schema

Defines the validated, typed structure of ``configs/benchmark.yaml``:
which benchmark suites the Benchmark Engine runs after a successful
Bootstrap, and whether a benchmark failure is allowed to block a node
from entering operational service.

See SRS Section 9.11 and REQ-BENCH-001 through REQ-BENCH-010.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping

from config.validators.schema_validator import (
    coerce_bool,
    coerce_int,
    require_mapping,
    validate_range,
)


@dataclass(slots=True)
class BenchmarkConfig:
    """
    Benchmark Engine execution policy.
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    enabled: bool = True

    run_cpu: bool = True
    run_gpu: bool = True
    run_memory: bool = True
    run_storage: bool = True
    run_network: bool = True
    run_thermal: bool = True

    #: Per SRS Section 9.11: "Benchmarking shall not prevent the node
    #: from entering operational service unless required by
    #: deployment policy." Off by default; a deployment policy that
    #: wants benchmarking to gate production entry sets this True.
    fail_deployment_on_benchmark_failure: bool = False

    timeout_seconds: int = 300

    extensions: dict[str, Any] = field(default_factory=lambda: {})

    def __post_init__(self) -> None:
        """Validate benchmark policy invariants."""

        validate_range(
            self.timeout_seconds,
            field_name="timeout_seconds",
            minimum=1,
        )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BenchmarkConfig:
        """Construct a validated ``BenchmarkConfig`` from a raw mapping."""

        mapping = require_mapping(data, section="benchmark")

        known_keys = {
            "schema_version",
            "enabled",
            "run_cpu",
            "run_gpu",
            "run_memory",
            "run_storage",
            "run_network",
            "run_thermal",
            "fail_deployment_on_benchmark_failure",
            "timeout_seconds",
        }

        extensions = {
            key: value
            for key, value in mapping.items()
            if key not in known_keys
        }

        return cls(
            enabled=coerce_bool(
                mapping.get("enabled"),
                field_name="enabled",
                default=True,
            ),
            run_cpu=coerce_bool(
                mapping.get("run_cpu"),
                field_name="run_cpu",
                default=True,
            ),
            run_gpu=coerce_bool(
                mapping.get("run_gpu"),
                field_name="run_gpu",
                default=True,
            ),
            run_memory=coerce_bool(
                mapping.get("run_memory"),
                field_name="run_memory",
                default=True,
            ),
            run_storage=coerce_bool(
                mapping.get("run_storage"),
                field_name="run_storage",
                default=True,
            ),
            run_network=coerce_bool(
                mapping.get("run_network"),
                field_name="run_network",
                default=True,
            ),
            run_thermal=coerce_bool(
                mapping.get("run_thermal"),
                field_name="run_thermal",
                default=True,
            ),
            fail_deployment_on_benchmark_failure=coerce_bool(
                mapping.get("fail_deployment_on_benchmark_failure"),
                field_name="fail_deployment_on_benchmark_failure",
                default=False,
            ),
            timeout_seconds=coerce_int(
                mapping.get("timeout_seconds"),
                field_name="timeout_seconds",
                default=300,
            ),
            extensions=extensions,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a YAML/JSON-serializable dictionary representation."""

        return {
            "schema_version": self.SCHEMA_VERSION,
            "enabled": self.enabled,
            "run_cpu": self.run_cpu,
            "run_gpu": self.run_gpu,
            "run_memory": self.run_memory,
            "run_storage": self.run_storage,
            "run_network": self.run_network,
            "run_thermal": self.run_thermal,
            "fail_deployment_on_benchmark_failure": (
                self.fail_deployment_on_benchmark_failure
            ),
            "timeout_seconds": self.timeout_seconds,
            **self.extensions,
        }


__all__ = ["BenchmarkConfig"]
