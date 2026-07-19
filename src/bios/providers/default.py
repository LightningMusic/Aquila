"""
Project Orion
=============

Default BIOS Provider

Provides a complete default implementation of the
BIOSProvider interface.

All operations are implemented with safe fallback
behavior. Vendor-specific providers should inherit
from this class and override only the methods they
support.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from typing import Any

from bios.firmware import FirmwareInformation

from bios.providers.base import BIOSProvider


class DefaultBIOSProvider(BIOSProvider):
    """
    Safe default BIOS provider.

    This provider assumes no firmware features are
    available. It serves as the common base class for
    all vendor-specific providers.
    """

    def __init__(
        self,
        firmware_information: FirmwareInformation | None = None,
    ) -> None:

        super().__init__()

        self.vendor = "Unknown"

        self.firmware_information = firmware_information

    # =========================================================
    # Detection
    # =========================================================

    def detect(self) -> bool:
        """
        Default providers never positively identify
        themselves.
        """

        return False

    # =========================================================
    # Firmware Information
    # =========================================================

    def get_vendor(self) -> str:
        return self.vendor

    def get_manufacturer(self) -> str:
        return "Unknown"

    def get_model(self) -> str:
        return "Unknown"

    def get_version(self) -> str:
        return "Unknown"

    def get_release_date(self) -> str:
        return "Unknown"

    def get_serial_number(self) -> str:
        return "Unknown"

    def get_asset_tag(self) -> str:
        return "Unknown"

    def get_uuid(self) -> str:
        return "Unknown"

    # =========================================================
    # Boot Configuration
    # =========================================================

    def boot_mode_supported(self) -> bool:
        return False

    def get_boot_mode(self) -> str:
        return "Unknown"

    def set_boot_mode_uefi(self) -> bool:
        return False

    def set_boot_mode_legacy(self) -> bool:
        return False

    def get_boot_order(self) -> list[str]:
        return []

    def set_boot_order(
        self,
        devices: list[str],
    ) -> bool:
        return False

    def set_usb_first(self) -> bool:
        return False

    # =========================================================
    # PXE
    # =========================================================

    def pxe_supported(self) -> bool:
        return False

    def enable_pxe(self) -> bool:
        return False

    def disable_pxe(self) -> bool:
        return False

    # =========================================================
    # Virtualization
    # =========================================================

    def virtualization_supported(self) -> bool:
        return False

    def virtualization_enabled(self) -> bool:
        return False

    def enable_virtualization(self) -> bool:
        return False

    # =========================================================
    # IOMMU
    # =========================================================

    def iommu_supported(self) -> bool:
        return False

    def iommu_enabled(self) -> bool:
        return False

    def enable_iommu(self) -> bool:
        return False
    # =========================================================
    # Secure Boot
    # =========================================================

    def secure_boot_supported(self) -> bool:
        """
        Return whether Secure Boot is supported.
        """

        return False

    def secure_boot_enabled(self) -> bool:
        """
        Return whether Secure Boot is enabled.
        """

        return False

    def enable_secure_boot(self) -> bool:
        """
        Enable Secure Boot.
        """

        return False

    def disable_secure_boot(self) -> bool:
        """
        Disable Secure Boot.
        """

        return False

    # =========================================================
    # TPM
    # =========================================================

    def tpm_supported(self) -> bool:
        """
        Return whether a TPM is present.
        """

        return False

    def tpm_enabled(self) -> bool:
        """
        Return whether TPM is enabled.
        """

        return False

    def enable_tpm(self) -> bool:
        """
        Enable TPM.
        """

        return False

    # =========================================================
    # BIOS Password
    # =========================================================

    def bios_password_set(self) -> bool:
        """
        Return whether a BIOS administrator password
        is configured.
        """

        return False

    # =========================================================
    # Wake Features
    # =========================================================

    def wake_on_ac_supported(self) -> bool:
        """
        Return whether Wake-on-AC is supported.
        """

        return False

    def enable_wake_on_ac(self) -> bool:
        """
        Enable Wake-on-AC.
        """

        return False

    def disable_wake_on_ac(self) -> bool:
        """
        Disable Wake-on-AC.
        """

        return False

    def wake_on_lan_supported(self) -> bool:
        """
        Return whether Wake-on-LAN is supported.
        """

        return False

    def enable_wake_on_lan(self) -> bool:
        """
        Enable Wake-on-LAN.
        """

        return False

    def disable_wake_on_lan(self) -> bool:
        """
        Disable Wake-on-LAN.
        """

        return False

    # =========================================================
    # Power
    # =========================================================

    def power_restore_supported(self) -> bool:
        """
        Return whether automatic AC power recovery
        is supported.
        """

        return False

    def enable_power_restore(self) -> bool:
        """
        Enable automatic recovery after AC power loss.
        """

        return False

    # =========================================================
    # Battery
    # =========================================================

    def get_charge_limit(self) -> int | None:
        """
        Returns the current battery charge limit.

        Returns None if the firmware does not expose one.
        """

        return None

    def battery_settings_supported(self) -> bool:
        """
        Return whether battery firmware settings are
        available.
        """

        return False

    def set_charge_limit(
        self,
        percent: int,
    ) -> bool:
        """
        Configure the battery charge limit.
        """

        return False

    def enable_battery_health_mode(self) -> bool:
        """
        Enable battery health mode.
        """

        return False

    def disable_battery_health_mode(self) -> bool:
        """
        Disable battery health mode.
        """

        return False

    # =========================================================
    # Thermal
    # =========================================================

    def fan_control_supported(self) -> bool:
        """
        Return whether firmware fan control exists.
        """

        return False

    # =========================================================
    # Capabilities
    # =========================================================

    def capabilities(self) -> dict[str, bool]:
        """
        Return the firmware capabilities supported by
        this provider.
        """

        return {
            "boot_mode": self.boot_mode_supported(),
            "boot_order": False,
            "usb_boot": False,
            "pxe": self.pxe_supported(),
            "virtualization": self.virtualization_supported(),
            "iommu": self.iommu_supported(),
            "secure_boot": self.secure_boot_supported(),
            "tpm": self.tpm_supported(),
            "wake_on_ac": self.wake_on_ac_supported(),
            "wake_on_lan": self.wake_on_lan_supported(),
            "power_restore": self.power_restore_supported(),
            "battery": self.battery_settings_supported(),
            "fan_control": self.fan_control_supported(),
        }

    # =========================================================
    # Export
    # =========================================================

    def to_dict(self) -> dict[str, Any]:
        """
        Export provider information.
        """

        return {
            "provider": self.__class__.__name__,
            "vendor": self.get_vendor(),
            "manufacturer": self.get_manufacturer(),
            "model": self.get_model(),
            "version": self.get_version(),
            "release_date": self.get_release_date(),
            "serial_number": self.get_serial_number(),
            "asset_tag": self.get_asset_tag(),
            "uuid": self.get_uuid(),
            "boot_mode": self.get_boot_mode(),
            "capabilities": self.capabilities(),
        }