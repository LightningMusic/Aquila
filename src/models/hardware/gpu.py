"""
Project Aquila
=============

GPU Inventory Model

Data structure populated by ``hardware.gpu``. Not explicitly required
by an SRS ``REQ-INS-*`` requirement (Section 11.3's Inspection Engine
requirements predate this file), but relevant to a Proxmox
provisioning target: GPU presence and identity inform PCI/vfio
passthrough planning for VM workloads on the deployed node, and
belong in the same hardware inventory as everything else REQ-INS-025's
inspection report collects.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping

from . import HardwareModelError, JSONValue, coerce_bool, make_json_compatible
from . import to_json as _to_json


@dataclass(slots=True)
class GPUInfo:
    """A single video controller/GPU enumerated on the system."""

    SCHEMA_VERSION: ClassVar[int] = 1

    name: str = ""
    vendor: str = ""
    driver_version: str = ""
    video_memory_bytes: int | None = None
    is_integrated: bool = False
    pci_device_id: str = ""

    extensions: dict[str, Any] = field(default_factory=lambda: {})

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.vendor = self.vendor.strip()
        self.driver_version = self.driver_version.strip()
        self.pci_device_id = self.pci_device_id.strip()

        if self.video_memory_bytes is not None and self.video_memory_bytes < 0:
            raise HardwareModelError(
                "GPUInfo.video_memory_bytes must not be negative."
            )

        self.extensions = dict(self.extensions)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "name": self.name,
            "vendor": self.vendor,
            "driver_version": self.driver_version,
            "video_memory_bytes": self.video_memory_bytes,
            "is_integrated": self.is_integrated,
            "pci_device_id": self.pci_device_id,
            "extensions": make_json_compatible(self.extensions),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return _to_json(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GPUInfo":
        known_keys = {
            "schema_version",
            "name",
            "vendor",
            "driver_version",
            "video_memory_bytes",
            "is_integrated",
            "pci_device_id",
            "extensions",
        }

        extensions = {
            key: value for key, value in data.items() if key not in known_keys
        }

        return cls(
            name=str(data.get("name") or ""),
            vendor=str(data.get("vendor") or ""),
            driver_version=str(data.get("driver_version") or ""),
            video_memory_bytes=(
                int(data["video_memory_bytes"])
                if data.get("video_memory_bytes") is not None
                else None
            ),
            is_integrated=coerce_bool(
                data.get("is_integrated", False), field_name="is_integrated"
            ),
            pci_device_id=str(data.get("pci_device_id") or ""),
            extensions=extensions,
        )


__all__ = ["GPUInfo"]
