"""
Project Aquila
=============

SMART Health Model

Data structures populated by ``hardware.smart`` (REQ-INS-007:
retrieve SMART health information for supported storage devices) and
consumed by the Inspection Engine's hardware report and the
Preparation Engine's pre-sanitization health check.

Reuses ``common.enums.SMARTStatus`` rather than defining a second,
competing pass/fail/unknown enum -- see this package's ``__init__``
docstring for why that matters.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Mapping, cast

from common.enums import SMARTStatus

from . import HardwareModelError, JSONValue, make_json_compatible
from . import to_json as _to_json


@dataclass(slots=True)
class SMARTAttribute:
    """
    A single SMART attribute reading (e.g. attribute 5, "Reallocated
    Sectors Count").

    Attribute IDs and names follow the vendor-common ATA SMART
    convention; not every device populates every field (raw SMART
    data availability varies by vendor and interface).
    """

    attribute_id: int
    name: str = ""
    raw_value: int = 0
    normalized_value: int | None = None
    worst_value: int | None = None
    threshold: int | None = None
    when_failed: bool = False

    def __post_init__(self) -> None:
        self.name = self.name.strip()

        if self.attribute_id < 0:
            raise HardwareModelError(
                "SMARTAttribute.attribute_id must not be negative."
            )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "attribute_id": self.attribute_id,
            "name": self.name,
            "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "worst_value": self.worst_value,
            "threshold": self.threshold,
            "when_failed": self.when_failed,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SMARTAttribute":
        return cls(
            attribute_id=int(data.get("attribute_id", 0)),
            name=str(data.get("name") or ""),
            raw_value=int(data.get("raw_value", 0)),
            normalized_value=(
                int(data["normalized_value"])
                if data.get("normalized_value") is not None
                else None
            ),
            worst_value=(
                int(data["worst_value"])
                if data.get("worst_value") is not None
                else None
            ),
            threshold=(
                int(data["threshold"]) if data.get("threshold") is not None else None
            ),
            when_failed=bool(data.get("when_failed", False)),
        )


@dataclass(slots=True)
class SMARTReport:
    """
    SMART health assessment for a single storage device
    (REQ-INS-007).
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    device_path: str = ""
    status: SMARTStatus = SMARTStatus.UNKNOWN
    supported: bool = False

    power_on_hours: int | None = None
    power_cycle_count: int | None = None
    temperature_celsius: float | None = None
    reallocated_sector_count: int | None = None
    pending_sector_count: int | None = None
    uncorrectable_sector_count: int | None = None

    attributes: list[SMARTAttribute] = field(default_factory=lambda: [])
    collected_at: datetime | None = None
    raw_data: dict[str, Any] = field(default_factory=lambda: {})

    def __post_init__(self) -> None:
        if isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            self.status, str
        ):
            self.status = SMARTStatus[self.status.strip().upper()]

        self.device_path = self.device_path.strip()
        self.attributes = list(self.attributes)
        self.raw_data = dict(self.raw_data)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "device_path": self.device_path,
            "status": self.status.name,
            "supported": self.supported,
            "power_on_hours": self.power_on_hours,
            "power_cycle_count": self.power_cycle_count,
            "temperature_celsius": self.temperature_celsius,
            "reallocated_sector_count": self.reallocated_sector_count,
            "pending_sector_count": self.pending_sector_count,
            "uncorrectable_sector_count": self.uncorrectable_sector_count,
            "attributes": [attribute.to_dict() for attribute in self.attributes],
            "collected_at": (
                self.collected_at.isoformat() if self.collected_at else None
            ),
            "raw_data": make_json_compatible(self.raw_data),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return _to_json(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SMARTReport":
        raw_attributes = data.get("attributes", [])
        if not isinstance(raw_attributes, list):
            raise HardwareModelError("SMARTReport.attributes must be a list.")
        raw_attributes = cast("list[Any]", raw_attributes)

        collected_at_raw = data.get("collected_at")

        status_raw = data.get("status")
        try:
            status = (
                SMARTStatus[str(status_raw).strip().upper()]
                if status_raw
                else SMARTStatus.UNKNOWN
            )
        except KeyError:
            status = SMARTStatus.UNKNOWN

        return cls(
            device_path=str(data.get("device_path") or ""),
            status=status,
            supported=bool(data.get("supported", False)),
            power_on_hours=(
                int(data["power_on_hours"])
                if data.get("power_on_hours") is not None
                else None
            ),
            power_cycle_count=(
                int(data["power_cycle_count"])
                if data.get("power_cycle_count") is not None
                else None
            ),
            temperature_celsius=(
                float(data["temperature_celsius"])
                if data.get("temperature_celsius") is not None
                else None
            ),
            reallocated_sector_count=(
                int(data["reallocated_sector_count"])
                if data.get("reallocated_sector_count") is not None
                else None
            ),
            pending_sector_count=(
                int(data["pending_sector_count"])
                if data.get("pending_sector_count") is not None
                else None
            ),
            uncorrectable_sector_count=(
                int(data["uncorrectable_sector_count"])
                if data.get("uncorrectable_sector_count") is not None
                else None
            ),
            attributes=[
                SMARTAttribute.from_dict(cast(Mapping[str, Any], entry))
                for entry in raw_attributes
                if isinstance(entry, Mapping)
            ],
            collected_at=(
                datetime.fromisoformat(str(collected_at_raw))
                if collected_at_raw
                else None
            ),
            raw_data=dict(data.get("raw_data") or {}),
        )


__all__ = ["SMARTAttribute", "SMARTReport"]
