"""
Project Aquila
=============

Virtualization Capability Model

Data structure populated by ``hardware.virtualization`` (REQ-INS-012,
REQ-INS-013) and consumed by the Inspection Engine's hardware report
and REQ-PROV-005's "hardware virtualization support" minimum
deployment requirement.

Reuses ``common.enums.VirtualizationState`` (already used by the
``bios`` subsystem for the same concept) for the firmware-enabled
tri-state rather than defining a second, competing enum -- see this
package's ``__init__`` docstring.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar, Mapping

from common.enums import VirtualizationState

from . import HardwareModelError, JSONValue, coerce_bool


class VirtualizationTechnology(str, Enum):
    """Normalized hardware virtualization extension technology."""

    VT_X = "vt_x"
    AMD_V = "amd_v"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, value: str | None) -> "VirtualizationTechnology":
        if not value:
            return cls.UNKNOWN

        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")

        aliases: dict[str, VirtualizationTechnology] = {
            "vt_x": cls.VT_X,
            "vtx": cls.VT_X,
            "intel_vt": cls.VT_X,
            "intel_vt_x": cls.VT_X,
            "amd_v": cls.AMD_V,
            "amdv": cls.AMD_V,
            "svm": cls.AMD_V,
            "unknown": cls.UNKNOWN,
        }

        return aliases.get(normalized, cls.UNKNOWN)


@dataclass(slots=True)
class VirtualizationInfo:
    """
    CPU/firmware virtualization capability record.

    ``cpu_supported`` (REQ-INS-012, a physical capability of the
    installed CPU) is intentionally independent of ``firmware_state``
    (REQ-INS-013, whether that capability is currently switched on in
    firmware) -- REQ-PROV-005/REQ-PROV-006 need to distinguish
    "this hardware can never support virtualization" (deployment
    fails permanently) from "this hardware supports virtualization
    but it's off in the BIOS" (deployment fails, but the technician
    can fix it and retry).
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    cpu_supported: bool = False
    technology: VirtualizationTechnology = VirtualizationTechnology.UNKNOWN
    firmware_state: VirtualizationState = VirtualizationState.UNKNOWN
    nested_virtualization_supported: bool | None = None
    iommu_supported: bool | None = None

    def __post_init__(self) -> None:
        if isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            self.technology, str
        ):
            self.technology = VirtualizationTechnology.from_string(self.technology)

        if isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            self.firmware_state, str
        ):
            try:
                self.firmware_state = VirtualizationState[
                    self.firmware_state.strip().upper()
                ]
            except KeyError:
                self.firmware_state = VirtualizationState.UNKNOWN

        if not self.cpu_supported and self.firmware_state is VirtualizationState.ENABLED:
            raise HardwareModelError(
                "VirtualizationInfo.firmware_state cannot be ENABLED when "
                "cpu_supported is False."
            )

    @property
    def is_usable(self) -> bool:
        """
        Whether virtualization is actually usable right now -- both
        supported by the CPU and confirmed enabled in firmware. This
        is what REQ-PROV-006's minimum-requirements check should test,
        not ``cpu_supported`` alone.
        """

        return self.cpu_supported and self.firmware_state is VirtualizationState.ENABLED

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "cpu_supported": self.cpu_supported,
            "technology": self.technology.value,
            "firmware_state": self.firmware_state.name,
            "nested_virtualization_supported": self.nested_virtualization_supported,
            "iommu_supported": self.iommu_supported,
            "is_usable": self.is_usable,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VirtualizationInfo":
        firmware_state_raw = data.get("firmware_state")
        try:
            firmware_state = (
                VirtualizationState[str(firmware_state_raw).strip().upper()]
                if firmware_state_raw
                else VirtualizationState.UNKNOWN
            )
        except KeyError:
            firmware_state = VirtualizationState.UNKNOWN

        nested = data.get("nested_virtualization_supported")
        iommu = data.get("iommu_supported")

        return cls(
            cpu_supported=coerce_bool(
                data.get("cpu_supported", False), field_name="cpu_supported"
            ),
            technology=VirtualizationTechnology.from_string(
                str(data.get("technology")) if data.get("technology") else None
            ),
            firmware_state=firmware_state,
            nested_virtualization_supported=(
                coerce_bool(nested, field_name="nested_virtualization_supported")
                if nested is not None
                else None
            ),
            iommu_supported=(
                coerce_bool(iommu, field_name="iommu_supported")
                if iommu is not None
                else None
            ),
        )


__all__ = ["VirtualizationInfo", "VirtualizationTechnology"]
