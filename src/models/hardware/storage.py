"""
Project Aquila
=============

Storage Inventory Model

Data structures populated by ``hardware.storage`` (REQ-INS-005
through REQ-INS-008) and consumed by the Inspection Engine's hardware
report, the Recovery Engine (REQ-REC-002), and the Preparation
Engine's target-device verification (REQ-PREP-010).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Mapping, cast

from . import HardwareModelError, JSONValue, coerce_bool, make_json_compatible, optional_string
from . import to_json as _to_json


class StorageDeviceType(str, Enum):
    """
    Normalized storage device category.

    Values match REQ-INS-006's literal examples: SATA HDD, SATA SSD,
    NVMe SSD, USB Storage.
    """

    SATA_HDD = "sata_hdd"
    SATA_SSD = "sata_ssd"
    NVME_SSD = "nvme_ssd"
    USB_STORAGE = "usb_storage"
    OTHER = "other"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, value: str | None) -> "StorageDeviceType":
        if not value:
            return cls.UNKNOWN

        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")

        aliases: dict[str, StorageDeviceType] = {
            "sata_hdd": cls.SATA_HDD,
            "sata_ssd": cls.SATA_SSD,
            "nvme_ssd": cls.NVME_SSD,
            "nvme": cls.NVME_SSD,
            "usb_storage": cls.USB_STORAGE,
            "usb": cls.USB_STORAGE,
            "other": cls.OTHER,
            "unknown": cls.UNKNOWN,
        }

        return aliases.get(normalized, cls.UNKNOWN)


@dataclass(slots=True)
class StorageDevice:
    """
    A single physical storage device enumerated by REQ-INS-005.

    ``device_path`` is the stable OS handle used by every later
    destructive stage (``\\\\.\\PhysicalDrive0`` on Windows) --
    REQ-PREP-010 verifies storage identity using this value together
    with capacity/manufacturer/model/serial_number, so it must be
    populated whenever the device is discoverable at all, even when
    every other field ends up empty.
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    device_path: str = ""
    model: str = ""
    manufacturer: str = ""
    serial_number: str = ""
    device_type: StorageDeviceType = StorageDeviceType.UNKNOWN
    interface: str = ""

    capacity_bytes: int = 0
    free_capacity_bytes: int | None = None

    firmware_version: str = ""
    is_removable: bool = False
    is_system_disk: bool = False
    is_boot_media: bool = False

    extensions: dict[str, Any] = field(default_factory=lambda: {})

    def __post_init__(self) -> None:
        if isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            self.device_type, str
        ):
            self.device_type = StorageDeviceType.from_string(self.device_type)

        self.device_path = self.device_path.strip()
        self.model = self.model.strip()
        self.manufacturer = self.manufacturer.strip()
        self.serial_number = self.serial_number.strip()
        self.interface = self.interface.strip()
        self.firmware_version = self.firmware_version.strip()

        if self.capacity_bytes < 0:
            raise HardwareModelError(
                "StorageDevice.capacity_bytes must not be negative."
            )

        if self.free_capacity_bytes is not None and self.free_capacity_bytes < 0:
            raise HardwareModelError(
                "StorageDevice.free_capacity_bytes must not be negative."
            )

        self.extensions = dict(self.extensions)

    def matches_identity(
        self,
        *,
        device_path: str | None = None,
        capacity_bytes: int | None = None,
        manufacturer: str | None = None,
        model: str | None = None,
        serial_number: str | None = None,
    ) -> bool:
        """
        Return whether every supplied identifier matches this device.

        Implements REQ-PREP-010's "verify storage device identity
        using all available identifiers" and REQ-PREP-008/009's
        "storage device has not changed since inspection" check.
        Identifiers left as ``None`` are not compared, so a caller can
        check only the identifiers it actually has available.
        """

        checks = (
            (device_path, self.device_path),
            (capacity_bytes, self.capacity_bytes),
            (manufacturer, self.manufacturer),
            (model, self.model),
            (serial_number, self.serial_number),
        )

        for expected, actual in checks:
            if expected is None:
                continue

            if isinstance(expected, str):
                if expected.strip().lower() != str(actual).strip().lower():
                    return False
            elif expected != actual:
                return False

        return True

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "device_path": self.device_path,
            "model": self.model,
            "manufacturer": self.manufacturer,
            "serial_number": self.serial_number,
            "device_type": self.device_type.value,
            "interface": self.interface,
            "capacity_bytes": self.capacity_bytes,
            "free_capacity_bytes": self.free_capacity_bytes,
            "firmware_version": self.firmware_version,
            "is_removable": self.is_removable,
            "is_system_disk": self.is_system_disk,
            "is_boot_media": self.is_boot_media,
            "extensions": make_json_compatible(self.extensions),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "StorageDevice":
        known_keys = {
            "schema_version",
            "device_path",
            "model",
            "manufacturer",
            "serial_number",
            "device_type",
            "interface",
            "capacity_bytes",
            "free_capacity_bytes",
            "firmware_version",
            "is_removable",
            "is_system_disk",
            "is_boot_media",
            "extensions",
        }

        extensions = {
            key: value for key, value in data.items() if key not in known_keys
        }

        return cls(
            device_path=str(data.get("device_path") or ""),
            model=str(data.get("model") or ""),
            manufacturer=str(data.get("manufacturer") or ""),
            serial_number=str(data.get("serial_number") or ""),
            device_type=StorageDeviceType.from_string(
                optional_string(data.get("device_type"))
            ),
            interface=str(data.get("interface") or ""),
            capacity_bytes=int(data.get("capacity_bytes", 0)),
            free_capacity_bytes=(
                int(data["free_capacity_bytes"])
                if data.get("free_capacity_bytes") is not None
                else None
            ),
            firmware_version=str(data.get("firmware_version") or ""),
            is_removable=coerce_bool(
                data.get("is_removable", False), field_name="is_removable"
            ),
            is_system_disk=coerce_bool(
                data.get("is_system_disk", False), field_name="is_system_disk"
            ),
            is_boot_media=coerce_bool(
                data.get("is_boot_media", False), field_name="is_boot_media"
            ),
            extensions=extensions,
        )


@dataclass(slots=True)
class StorageInventory:
    """Every storage device enumerated on the target system."""

    SCHEMA_VERSION: ClassVar[int] = 1

    devices: list[StorageDevice] = field(default_factory=lambda: [])

    def __post_init__(self) -> None:
        self.devices = list(self.devices)

    @property
    def total_capacity_bytes(self) -> int:
        return sum(device.capacity_bytes for device in self.devices)

    def eligible_for_deployment(self) -> list[StorageDevice]:
        """
        Return devices REQ-PREP-012 permits selecting as a
        sanitization/deployment target -- excludes removable/boot
        media (the deployment USB itself must never be eligible for
        sanitization).
        """

        return [
            device
            for device in self.devices
            if not device.is_removable and not device.is_boot_media
        ]

    def find_by_path(self, device_path: str) -> StorageDevice | None:
        for device in self.devices:
            if device.device_path == device_path:
                return device

        return None

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "devices": [device.to_dict() for device in self.devices],
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return _to_json(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "StorageInventory":
        raw_devices = data.get("devices", [])
        if not isinstance(raw_devices, list):
            raise HardwareModelError("StorageInventory.devices must be a list.")
        raw_devices = cast("list[Any]", raw_devices)

        return cls(
            devices=[
                StorageDevice.from_dict(cast(Mapping[str, Any], entry))
                for entry in raw_devices
                if isinstance(entry, Mapping)
            ]
        )


__all__ = ["StorageDevice", "StorageDeviceType", "StorageInventory"]
