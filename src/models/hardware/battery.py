"""
Project Aquila
=============

Battery Inventory Model

Data structure populated by ``hardware.battery`` (REQ-INS-020,
REQ-INS-021) and consumed by the Inspection Engine's hardware report
and Bootstrap's battery-threshold configuration (REQ-BOOT-009,
GP-008).

Reuses ``common.enums.BatteryHealth`` rather than defining a second,
competing health enum -- see this package's ``__init__`` docstring.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping

from common.enums import BatteryHealth

from . import HardwareModelError, JSONValue, coerce_bool, make_json_compatible
from . import to_json as _to_json


@dataclass(slots=True)
class BatteryInfo:
    """
    Battery presence, health, and capability record for portable
    systems.

    ``present=False`` (the default) is the correct, complete record
    for any desktop or server system -- REQ-INS-020/021 apply only to
    "supported portable systems", and every other field is
    meaningless when no battery exists.
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    present: bool = False

    manufacturer: str = ""
    serial_number: str = ""
    chemistry: str = ""

    design_capacity_mwh: int | None = None
    full_charge_capacity_mwh: int | None = None
    current_capacity_mwh: int | None = None
    cycle_count: int | None = None

    health: BatteryHealth = BatteryHealth.UNKNOWN

    charge_threshold_supported: bool = False

    extensions: dict[str, Any] = field(default_factory=lambda: {})

    def __post_init__(self) -> None:
        if isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            self.health, str
        ):
            try:
                self.health = BatteryHealth[self.health.strip().upper()]
            except KeyError:
                self.health = BatteryHealth.UNKNOWN

        self.manufacturer = self.manufacturer.strip()
        self.serial_number = self.serial_number.strip()
        self.chemistry = self.chemistry.strip()

        for capacity_field in (
            "design_capacity_mwh",
            "full_charge_capacity_mwh",
            "current_capacity_mwh",
        ):
            value = getattr(self, capacity_field)
            if value is not None and value < 0:
                raise HardwareModelError(
                    f"BatteryInfo.{capacity_field} must not be negative."
                )

        if self.cycle_count is not None and self.cycle_count < 0:
            raise HardwareModelError(
                "BatteryInfo.cycle_count must not be negative."
            )

        self.extensions = dict(self.extensions)

    @property
    def health_percent(self) -> float | None:
        """
        Ratio of full-charge capacity to design capacity, as a
        percentage -- the standard "battery wear level" figure.
        Returns ``None`` when either capacity is unavailable or the
        design capacity is zero.
        """

        if not self.design_capacity_mwh or self.full_charge_capacity_mwh is None:
            return None

        return round(
            (self.full_charge_capacity_mwh / self.design_capacity_mwh) * 100, 1
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "present": self.present,
            "manufacturer": self.manufacturer,
            "serial_number": self.serial_number,
            "chemistry": self.chemistry,
            "design_capacity_mwh": self.design_capacity_mwh,
            "full_charge_capacity_mwh": self.full_charge_capacity_mwh,
            "current_capacity_mwh": self.current_capacity_mwh,
            "cycle_count": self.cycle_count,
            "health": self.health.name,
            "health_percent": self.health_percent,
            "charge_threshold_supported": self.charge_threshold_supported,
            "extensions": make_json_compatible(self.extensions),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return _to_json(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BatteryInfo":
        known_keys = {
            "schema_version",
            "present",
            "manufacturer",
            "serial_number",
            "chemistry",
            "design_capacity_mwh",
            "full_charge_capacity_mwh",
            "current_capacity_mwh",
            "cycle_count",
            "health",
            "health_percent",
            "charge_threshold_supported",
        }

        extensions = {
            key: value for key, value in data.items() if key not in known_keys
        }

        health_raw = data.get("health")
        try:
            health = (
                BatteryHealth[str(health_raw).strip().upper()]
                if health_raw
                else BatteryHealth.UNKNOWN
            )
        except KeyError:
            health = BatteryHealth.UNKNOWN

        return cls(
            present=coerce_bool(data.get("present", False), field_name="present"),
            manufacturer=str(data.get("manufacturer") or ""),
            serial_number=str(data.get("serial_number") or ""),
            chemistry=str(data.get("chemistry") or ""),
            design_capacity_mwh=(
                int(data["design_capacity_mwh"])
                if data.get("design_capacity_mwh") is not None
                else None
            ),
            full_charge_capacity_mwh=(
                int(data["full_charge_capacity_mwh"])
                if data.get("full_charge_capacity_mwh") is not None
                else None
            ),
            current_capacity_mwh=(
                int(data["current_capacity_mwh"])
                if data.get("current_capacity_mwh") is not None
                else None
            ),
            cycle_count=(
                int(data["cycle_count"]) if data.get("cycle_count") is not None else None
            ),
            health=health,
            charge_threshold_supported=coerce_bool(
                data.get("charge_threshold_supported", False),
                field_name="charge_threshold_supported",
            ),
            extensions=extensions,
        )


__all__ = ["BatteryInfo"]
