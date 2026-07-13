"""
Project Orion
=============

Firmware Information

Defines the immutable data structures used to describe
the firmware and system information discovered during
BIOS detection.

This module intentionally contains only data models.
It has no dependencies on provider implementations or
hardware detection logic, allowing it to be safely
shared throughout the BIOS subsystem.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class FirmwareInformation:
    """
    Immutable snapshot of firmware information.

    This object is created once during BIOS detection
    and then shared with all BIOS providers.

    Providers should treat this object as read-only.
    """

    manufacturer: str = "Unknown"

    vendor: str = "Unknown"

    model: str = "Unknown"

    version: str = "Unknown"

    release_date: str = "Unknown"

    serial_number: str = "Unknown"

    asset_tag: str = "Unknown"

    uuid: str = "Unknown"

    bios_mode: str = "Unknown"

    architecture: str = "Unknown"

    firmware_type: str = "Unknown"

    secure_boot: bool = False

    tpm_present: bool = False

    virtualization_supported: bool = False

    virtualization_enabled: bool = False

    iommu_supported: bool = False

    iommu_enabled: bool = False

    pxe_supported: bool = False

    battery_present: bool = False

    ac_connected: bool = False

    def to_dict(self) -> dict[str, Any]:
        """
        Convert this object into a dictionary.
        """

        return asdict(self)

    @classmethod
    def unknown(cls) -> "FirmwareInformation":
        """
        Construct an empty firmware snapshot.
        """

        return cls()

    @property
    def is_uefi(self) -> bool:
        """
        True if the firmware is operating in UEFI mode.
        """

        return self.bios_mode.lower() == "uefi"

    @property
    def is_legacy(self) -> bool:
        """
        True if the firmware is operating in Legacy BIOS
        mode.
        """

        return self.bios_mode.lower() == "legacy"

    @property
    def is_dell(self) -> bool:
        manufacturer = self.manufacturer.lower()
        vendor = self.vendor.lower()

        return (
            "dell" in manufacturer
            or "dell" in vendor
        )

    @property
    def is_hp(self) -> bool:
        manufacturer = self.manufacturer.lower()
        vendor = self.vendor.lower()

        return (
            "hp" in manufacturer
            or "hewlett" in manufacturer
            or "hp" in vendor
        )

    @property
    def is_lenovo(self) -> bool:
        manufacturer = self.manufacturer.lower()
        vendor = self.vendor.lower()

        return (
            "lenovo" in manufacturer
            or "lenovo" in vendor
        )

    @property
    def is_acer(self) -> bool:
        manufacturer = self.manufacturer.lower()
        vendor = self.vendor.lower()

        return (
            "acer" in manufacturer
            or "acer" in vendor
        )

    @property
    def is_asus(self) -> bool:
        manufacturer = self.manufacturer.lower()
        vendor = self.vendor.lower()

        return (
            "asus" in manufacturer
            or "asus" in vendor
        )

    @property
    def is_msi(self) -> bool:
        manufacturer = self.manufacturer.lower()
        vendor = self.vendor.lower()

        return (
            "msi" in manufacturer
            or "micro-star" in manufacturer
            or "msi" in vendor
        )

    @property
    def is_gigabyte(self) -> bool:
        manufacturer = self.manufacturer.lower()
        vendor = self.vendor.lower()

        return (
            "gigabyte" in manufacturer
            or "gigabyte" in vendor
        )

    @property
    def is_framework(self) -> bool:
        manufacturer = self.manufacturer.lower()
        vendor = self.vendor.lower()

        return (
            "framework" in manufacturer
            or "framework" in vendor
        )

    def __str__(self) -> str:
        return (
            f"{self.manufacturer} "
            f"{self.model} "
            f"({self.version})"
        )