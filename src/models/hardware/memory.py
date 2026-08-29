"""
Project Aquila
=============

Memory Inventory Model

Data structures populated by ``hardware.memory`` (REQ-INS-003,
REQ-INS-004) and consumed by the Inspection Engine's hardware report
and REQ-PROV-005's minimum-memory validation.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Mapping, cast

from . import HardwareModelError, JSONValue, make_json_compatible, optional_string
from . import to_json as _to_json


class MemoryType(str, Enum):
    """Normalized RAM module technology."""

    DDR2 = "ddr2"
    DDR3 = "ddr3"
    DDR4 = "ddr4"
    DDR5 = "ddr5"
    LPDDR3 = "lpddr3"
    LPDDR4 = "lpddr4"
    LPDDR5 = "lpddr5"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, value: str | None) -> "MemoryType":
        """Convert a raw SMBIOS/WMI memory-type string into a normalized value."""

        if not value:
            return cls.UNKNOWN

        normalized = value.strip().lower().replace("-", "").replace(" ", "")

        aliases: dict[str, MemoryType] = {
            "ddr2": cls.DDR2,
            "ddr3": cls.DDR3,
            "ddr3l": cls.DDR3,
            "ddr4": cls.DDR4,
            "ddr5": cls.DDR5,
            "lpddr3": cls.LPDDR3,
            "lpddr4": cls.LPDDR4,
            "lpddr4x": cls.LPDDR4,
            "lpddr5": cls.LPDDR5,
            "unknown": cls.UNKNOWN,
        }

        return aliases.get(normalized, cls.UNKNOWN)


@dataclass(slots=True)
class MemoryModule:
    """A single physical memory module (one ``Win32_PhysicalMemory`` row)."""

    SCHEMA_VERSION: ClassVar[int] = 1

    slot: str = ""
    capacity_bytes: int = 0
    speed_mhz: int | None = None
    configured_speed_mhz: int | None = None
    memory_type: MemoryType = MemoryType.UNKNOWN
    manufacturer: str = ""
    part_number: str = ""
    serial_number: str = ""

    def __post_init__(self) -> None:
        if isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            self.memory_type, str
        ):
            self.memory_type = MemoryType.from_string(self.memory_type)

        self.slot = self.slot.strip()
        self.manufacturer = self.manufacturer.strip()
        self.part_number = self.part_number.strip()
        self.serial_number = self.serial_number.strip()

        if self.capacity_bytes < 0:
            raise HardwareModelError(
                "MemoryModule.capacity_bytes must not be negative."
            )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "slot": self.slot,
            "capacity_bytes": self.capacity_bytes,
            "speed_mhz": self.speed_mhz,
            "configured_speed_mhz": self.configured_speed_mhz,
            "memory_type": self.memory_type.value,
            "manufacturer": self.manufacturer,
            "part_number": self.part_number,
            "serial_number": self.serial_number,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryModule":
        return cls(
            slot=str(data.get("slot") or ""),
            capacity_bytes=int(data.get("capacity_bytes", 0)),
            speed_mhz=(
                int(data["speed_mhz"]) if data.get("speed_mhz") is not None else None
            ),
            configured_speed_mhz=(
                int(data["configured_speed_mhz"])
                if data.get("configured_speed_mhz") is not None
                else None
            ),
            memory_type=MemoryType.from_string(
                optional_string(data.get("memory_type"))
            ),
            manufacturer=str(data.get("manufacturer") or ""),
            part_number=str(data.get("part_number") or ""),
            serial_number=str(data.get("serial_number") or ""),
        )


@dataclass(slots=True)
class MemoryInfo:
    """
    System-wide memory inventory (REQ-INS-003: enumerate installed
    memory modules; REQ-INS-004: report total installed system
    memory).
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    total_capacity_bytes: int = 0
    slots_used: int = 0
    slots_total: int = 0
    modules: list[MemoryModule] = field(default_factory=lambda: [])
    extensions: dict[str, Any] = field(default_factory=lambda: {})

    def __post_init__(self) -> None:
        for count_field in ("total_capacity_bytes", "slots_used", "slots_total"):
            if getattr(self, count_field) < 0:
                raise HardwareModelError(
                    f"MemoryInfo.{count_field} must not be negative."
                )

        if self.slots_total and self.slots_used > self.slots_total:
            raise HardwareModelError(
                "MemoryInfo.slots_used cannot exceed slots_total."
            )

        self.modules = list(self.modules)
        self.extensions = dict(self.extensions)

    @property
    def modules_capacity_bytes(self) -> int:
        """Sum of every individual module's reported capacity."""

        return sum(module.capacity_bytes for module in self.modules)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "total_capacity_bytes": self.total_capacity_bytes,
            "slots_used": self.slots_used,
            "slots_total": self.slots_total,
            "modules": [module.to_dict() for module in self.modules],
            "extensions": make_json_compatible(self.extensions),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return _to_json(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryInfo":
        known_keys = {
            "schema_version",
            "total_capacity_bytes",
            "slots_used",
            "slots_total",
            "modules",
            "extensions",
        }

        extensions = {
            key: value for key, value in data.items() if key not in known_keys
        }

        raw_modules = data.get("modules", [])
        if not isinstance(raw_modules, list):
            raise HardwareModelError("MemoryInfo.modules must be a list.")
        raw_modules = cast("list[Any]", raw_modules)

        return cls(
            total_capacity_bytes=int(data.get("total_capacity_bytes", 0)),
            slots_used=int(data.get("slots_used", 0)),
            slots_total=int(data.get("slots_total", 0)),
            modules=[
                MemoryModule.from_dict(cast(Mapping[str, Any], entry))
                for entry in raw_modules
                if isinstance(entry, Mapping)
            ],
            extensions=extensions,
        )


__all__ = ["MemoryInfo", "MemoryModule", "MemoryType"]
