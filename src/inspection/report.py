"""
Project Aquila
=============

Hardware Inspection Report

Data structures assembled by ``inspection.inspector.InspectionManager``
(REQ-INS-025: "The Inspection Engine shall generate a hardware
inspection report before any deployment workflow proceeds"). Every
per-category ``inspection/*.py`` module (``cpu``, ``memory``,
``storage``, ``smart``, ``network``, ``battery``, ``virtualization``,
``bios``, ``gpu``) returns a ``CategoryAssessment`` wrapping the raw
``models.hardware`` record for that category together with Aquila's
pass/warning/fail verdict (``common.enums.InspectionResult``) and the
human-readable reasons behind it; ``HardwareInspectionReport``
aggregates all nine into the single report REQ-INS-025 requires.

Follows the same ``SCHEMA_VERSION``/``to_dict()``/``to_json()``/
``from_dict()`` conventions established by ``bios.models`` and
``models.hardware`` (see that package's ``__init__`` docstring) rather
than defining a second, competing serialization convention.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, ClassVar, Generic, Mapping, TypeVar, cast

from common.enums import InspectionResult
from models.hardware import (
    BatteryInfo,
    BIOSInspectionInfo,
    CPUInfo,
    GPUInfo,
    JSONValue,
    MemoryInfo,
    NetworkAdapter,
    SMARTReport,
    StorageInventory,
    VirtualizationInfo,
    make_json_compatible,
)
from models.hardware import to_json as _to_json

_DataT = TypeVar("_DataT")


def _serialize_data(data: Any) -> JSONValue:
    """
    Serialize a category's collected data, whether it is a single
    model instance (``CPUInfo``, ``MemoryInfo``, ...) or a list of
    them (SMART reports, network adapters, GPUs).
    """

    if isinstance(data, list):
        return [_serialize_data(item) for item in cast("list[Any]", data)]

    to_dict = getattr(data, "to_dict", None)
    if callable(to_dict):
        return cast(JSONValue, to_dict())

    return make_json_compatible(data)


@dataclass(slots=True)
class CategoryAssessment(Generic[_DataT]):
    """
    One hardware category's collected data plus Aquila's verdict on
    it.

    ``result`` is never fabricated as a default -- every
    ``inspection/*.py`` category module must explicitly decide
    PASS/WARNING/FAIL from the data it collected (see each module's
    ``inspect()``), since a silently-defaulted verdict would be
    exactly the kind of guessed value this project's hardware
    detectors deliberately avoid.
    """

    data: _DataT
    result: InspectionResult
    messages: list[str] = field(default_factory=lambda: [])

    def __post_init__(self) -> None:
        self.messages = list(self.messages)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "result": self.result.name,
            "messages": list(self.messages),
            "data": _serialize_data(self.data),
        }

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        data_factory: Callable[[Any], _DataT],
    ) -> "CategoryAssessment[_DataT]":
        """
        Reconstruct a ``CategoryAssessment`` from its serialized form.

        ``data_factory`` converts the raw ``"data"`` value back into
        the category's real model type (or list of them) -- the
        caller (``HardwareInspectionReport.from_dict``) supplies the
        correct factory per field, since this generic class has no
        way to know which concrete type ``_DataT`` is at runtime.
        """

        result_raw = data.get("result")
        try:
            result = (
                InspectionResult[str(result_raw).strip().upper()]
                if result_raw
                else InspectionResult.WARNING
            )
        except KeyError:
            # InspectionResult has no "UNKNOWN" member (only
            # PASS/WARNING/FAIL) -- an unrecognized or missing stored
            # verdict is treated as WARNING rather than silently
            # upgraded to PASS or downgraded to FAIL, since neither of
            # those would honestly reflect "this could not be read
            # back".
            result = InspectionResult.WARNING

        messages_raw = data.get("messages", [])
        messages = (
            [str(message) for message in cast("list[Any]", messages_raw)]
            if isinstance(messages_raw, list)
            else []
        )

        return cls(
            data=data_factory(data.get("data")),
            result=result,
            messages=messages,
        )


def _list_factory(item_type: type[Any]) -> Callable[[Any], list[Any]]:
    """Build a ``data_factory`` for a category whose data is a list of models."""

    def factory(raw: Any) -> list[Any]:
        if not isinstance(raw, list):
            return []

        return [
            item_type.from_dict(entry)
            for entry in cast("list[Any]", raw)
            if isinstance(entry, Mapping)
        ]

    return factory


@dataclass(slots=True)
class HardwareInspectionReport:
    """
    Complete hardware inspection report (REQ-INS-025), assembled from
    every category's ``CategoryAssessment``.

    Retained by ``InspectionManager.last_report`` for the duration of
    the deployment session (REQ-INS-028) and made available to other
    subsystems (REQ-INS-027) -- the Preparation Engine's pre-flight
    summary (REQ-PREP-002) and the Provisioning Engine's minimum
    deployment requirements check (REQ-PROV-005) both read from an
    already-completed report rather than re-running detection.
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    cpu: CategoryAssessment[CPUInfo]
    memory: CategoryAssessment[MemoryInfo]
    storage: CategoryAssessment[StorageInventory]
    smart: CategoryAssessment[list[SMARTReport]]
    network: CategoryAssessment[list[NetworkAdapter]]
    battery: CategoryAssessment[BatteryInfo]
    virtualization: CategoryAssessment[VirtualizationInfo]
    bios: CategoryAssessment[BIOSInspectionInfo]
    gpu: CategoryAssessment[list[GPUInfo]]

    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # ------------------------------------------------------------------
    # Aggregate verdict
    # ------------------------------------------------------------------

    def _assessments(self) -> tuple[CategoryAssessment[Any], ...]:
        return (
            self.cpu,
            self.memory,
            self.storage,
            self.smart,
            self.network,
            self.battery,
            self.virtualization,
            self.bios,
            self.gpu,
        )

    @property
    def overall_result(self) -> InspectionResult:
        """
        The single worst verdict across every category -- FAIL if any
        category failed, else WARNING if any warned, else PASS.
        """

        assessments = self._assessments()

        if any(a.result is InspectionResult.FAIL for a in assessments):
            return InspectionResult.FAIL

        if any(a.result is InspectionResult.WARNING for a in assessments):
            return InspectionResult.WARNING

        return InspectionResult.PASS

    @property
    def warning_count(self) -> int:
        return sum(
            1 for a in self._assessments() if a.result is InspectionResult.WARNING
        )

    @property
    def failure_count(self) -> int:
        return sum(
            1 for a in self._assessments() if a.result is InspectionResult.FAIL
        )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "generated_at": self.generated_at.isoformat(),
            "overall_result": self.overall_result.name,
            "warning_count": self.warning_count,
            "failure_count": self.failure_count,
            "cpu": self.cpu.to_dict(),
            "memory": self.memory.to_dict(),
            "storage": self.storage.to_dict(),
            "smart": self.smart.to_dict(),
            "network": self.network.to_dict(),
            "battery": self.battery.to_dict(),
            "virtualization": self.virtualization.to_dict(),
            "bios": self.bios.to_dict(),
            "gpu": self.gpu.to_dict(),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return _to_json(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HardwareInspectionReport":
        def _section(name: str) -> Mapping[str, Any]:
            raw = data.get(name)
            if isinstance(raw, Mapping):
                return cast(Mapping[str, Any], raw)
            return {}

        generated_at_raw = data.get("generated_at")

        # Each call below explicitly parameterizes
        # ``CategoryAssessment[...]`` rather than letting pyright infer
        # it from ``data_factory`` alone -- pyright's TypeVar solver
        # does not infer a generic classmethod's type parameter from a
        # `Callable[[Any], _T]`-typed keyword argument (confirmed by
        # isolated reproduction against pyright 1.1.409), so leaving it
        # implicit collapses every field below to
        # ``CategoryAssessment[Unknown]`` under --strict.
        return cls(
            cpu=CategoryAssessment[CPUInfo].from_dict(
                _section("cpu"), data_factory=CPUInfo.from_dict
            ),
            memory=CategoryAssessment[MemoryInfo].from_dict(
                _section("memory"), data_factory=MemoryInfo.from_dict
            ),
            storage=CategoryAssessment[StorageInventory].from_dict(
                _section("storage"), data_factory=StorageInventory.from_dict
            ),
            smart=CategoryAssessment[list[SMARTReport]].from_dict(
                _section("smart"), data_factory=_list_factory(SMARTReport)
            ),
            network=CategoryAssessment[list[NetworkAdapter]].from_dict(
                _section("network"), data_factory=_list_factory(NetworkAdapter)
            ),
            battery=CategoryAssessment[BatteryInfo].from_dict(
                _section("battery"), data_factory=BatteryInfo.from_dict
            ),
            virtualization=CategoryAssessment[VirtualizationInfo].from_dict(
                _section("virtualization"), data_factory=VirtualizationInfo.from_dict
            ),
            bios=CategoryAssessment[BIOSInspectionInfo].from_dict(
                _section("bios"), data_factory=BIOSInspectionInfo.from_dict
            ),
            gpu=CategoryAssessment[list[GPUInfo]].from_dict(
                _section("gpu"), data_factory=_list_factory(GPUInfo)
            ),
            generated_at=(
                datetime.fromisoformat(str(generated_at_raw))
                if generated_at_raw
                else datetime.now(UTC)
            ),
        )


__all__ = ["CategoryAssessment", "HardwareInspectionReport"]
