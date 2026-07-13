"""
Project Orion
=============

Unknown BIOS Provider

Fallback provider used when Orion cannot determine the
firmware vendor or firmware type.

This provider intentionally makes no assumptions about
firmware capabilities. It serves as a safe fallback so
deployment can continue while avoiding vendor-specific
operations that could damage firmware configuration.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from bios.firmware import FirmwareInformation
from bios.providers.default import DefaultBIOSProvider


class UnknownProvider(DefaultBIOSProvider):
    """
    Generic fallback BIOS provider.

    Used whenever no supported firmware vendor can be
    positively identified.
    """

    def __init__(
        self,
        firmware_information: FirmwareInformation | None = None,
    ) -> None:

        super().__init__(firmware_information)

        self.vendor = "Unknown"

    # =====================================================
    # Detection
    # =====================================================

    def detect(self) -> bool:
        """
        This provider is selected only if every other
        provider fails.
        """

        return True

    # =====================================================
    # Firmware Information
    # =====================================================

    def get_vendor(self) -> str:

        return "Unknown"

    def get_manufacturer(self) -> str:

        if self.firmware_information is None:
            return "Unknown"

        return self.firmware_information.manufacturer

    def get_model(self) -> str:

        if self.firmware_information is None:
            return "Unknown"

        return self.firmware_information.model

    def get_version(self) -> str:

        if self.firmware_information is None:
            return "Unknown"

        return self.firmware_information.version

    def get_release_date(self) -> str:

        if self.firmware_information is None:
            return "Unknown"

        return self.firmware_information.release_date

    def get_serial_number(self) -> str:

        if self.firmware_information is None:
            return "Unknown"

        return self.firmware_information.serial_number

    def get_asset_tag(self) -> str:

        return "Unknown"

    def get_uuid(self) -> str:

        if self.firmware_information is None:
            return "Unknown"

        return self.firmware_information.uuid

    # =====================================================
    # Boot Configuration
    # =====================================================

    def boot_mode_supported(self) -> bool:

        return False

    def get_boot_mode(self) -> str:

        if self.firmware_information is None:
            return "Unknown"

        return self.firmware_information.bios_mode

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
    
    # =====================================================
    # PXE
    # =====================================================

    def pxe_supported(self) -> bool:

        return False

    def enable_pxe(self) -> bool:

        return False

    def disable_pxe(self) -> bool:

        return False

    # =====================================================
    # Virtualization
    # =====================================================

    def virtualization_supported(self) -> bool:

        return False

    def virtualization_enabled(self) -> bool:

        return False

    def enable_virtualization(self) -> bool:

        return False

    # =====================================================
    # IOMMU
    # =====================================================

    def iommu_supported(self) -> bool:

        return False

    def iommu_enabled(self) -> bool:

        return False

    def enable_iommu(self) -> bool:

        return False

    # =====================================================
    # Secure Boot
    # =====================================================

    def secure_boot_supported(self) -> bool:

        return False

    def secure_boot_enabled(self) -> bool:

        return False

    def enable_secure_boot(self) -> bool:

        return False

    def disable_secure_boot(self) -> bool:

        return False

    # =====================================================
    # TPM
    # =====================================================

    def tpm_supported(self) -> bool:

        return False

    def tpm_enabled(self) -> bool:

        return False

    def enable_tpm(self) -> bool:

        return False

    # =====================================================
    # BIOS Password
    # =====================================================

    def bios_password_set(self) -> bool:

        return False

    # =====================================================
    # Wake Features
    # =====================================================

    def wake_on_ac_supported(self) -> bool:

        return False

    def enable_wake_on_ac(self) -> bool:

        return False

    def disable_wake_on_ac(self) -> bool:

        return False

    def wake_on_lan_supported(self) -> bool:

        return False

    def enable_wake_on_lan(self) -> bool:

        return False

    def disable_wake_on_lan(self) -> bool:

        return False

    # =====================================================
    # Power
    # =====================================================

    def power_restore_supported(self) -> bool:

        return False

    def enable_power_restore(self) -> bool:

        return False

    # =====================================================
    # Battery
    # =====================================================

    def battery_settings_supported(self) -> bool:

        return False

    def set_charge_limit(
        self,
        percent: int,
    ) -> bool:

        return False

    def enable_battery_health_mode(self) -> bool:

        return False

    def disable_battery_health_mode(self) -> bool:

        return False

    # =====================================================
    # Thermal
    # =====================================================

    def fan_control_supported(self) -> bool:

        return False

    # =====================================================
    # Capabilities
    # =====================================================

    def capabilities(self) -> dict[str, bool]:

        capabilities = super().capabilities()

        capabilities.update(
            {
                "boot_mode": False,
                "pxe": False,
                "virtualization": False,
                "iommu": False,
                "secure_boot": False,
                "tpm": False,
                "wake_on_ac": False,
                "wake_on_lan": False,
                "power_restore": False,
                "battery": False,
            }
        )

        return capabilities

    # =====================================================
    # Export
    # =====================================================

    def to_dict(self) -> dict[str, object]:

        data = super().to_dict()

        data["provider"] = "UnknownProvider"
        data["vendor"] = "Unknown"

        return data