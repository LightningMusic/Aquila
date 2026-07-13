"""
Project Orion
=============

Dell BIOS Provider

Provides BIOS and firmware support for Dell systems.

This provider detects Dell firmware and exposes
firmware capabilities through the common BIOSProvider
interface.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from bios.firmware import FirmwareInformation
from bios.providers.default import DefaultBIOSProvider


class DellProvider(DefaultBIOSProvider):
    """
    Dell BIOS provider.
    """

    def __init__(
        self,
        firmware_information: FirmwareInformation | None = None,
    ) -> None:

        super().__init__(firmware_information)

        self.vendor = "Dell"

    # =====================================================
    # Detection
    # =====================================================

    def detect(self) -> bool:

        if self.firmware_information is None:
            return False

        manufacturer = (
            self.firmware_information.manufacturer.lower()
        )

        vendor = (
            self.firmware_information.vendor.lower()
        )

        return (
            "dell" in manufacturer
            or "dell" in vendor
        )

    # =====================================================
    # Firmware Information
    # =====================================================

    def get_vendor(self) -> str:

        return "Dell"

    def get_manufacturer(self) -> str:

        if self.firmware_information is None:
            return "Dell"

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

        return True

    def get_boot_mode(self) -> str:

        if self.firmware_information is None:
            return "Unknown"

        return self.firmware_information.bios_mode

    def set_boot_mode_uefi(self) -> bool:

        #
        # TODO:
        # Dell Command | Configure
        #

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
        """
        Dell systems generally support PXE boot.
        """

        return True

    def enable_pxe(self) -> bool:
        """
        Enable PXE boot.

        Implementation will use Dell Command |
        Configure or Dell WMI providers.
        """

        return False

    def disable_pxe(self) -> bool:

        return False

    # =====================================================
    # Virtualization
    # =====================================================

    def virtualization_supported(self) -> bool:

        return True

    def virtualization_enabled(self) -> bool:
        """
        TODO:
            Query Dell firmware.
        """

        return False

    def enable_virtualization(self) -> bool:
        """
        TODO:
            Enable Intel VT-x / AMD-V.
        """

        return False

    # =====================================================
    # IOMMU
    # =====================================================

    def iommu_supported(self) -> bool:

        return True

    def iommu_enabled(self) -> bool:

        return False

    def enable_iommu(self) -> bool:

        return False

    # =====================================================
    # Secure Boot
    # =====================================================

    def secure_boot_supported(self) -> bool:

        return True

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

        return True

    def tpm_enabled(self) -> bool:

        return False

    def enable_tpm(self) -> bool:

        return False

    # =====================================================
    # BIOS Password
    # =====================================================

    def bios_password_set(self) -> bool:
        """
        TODO:
            Query Dell firmware password state.
        """

        return False

    # =====================================================
    # Wake Features
    # =====================================================

    def wake_on_ac_supported(self) -> bool:

        return True

    def enable_wake_on_ac(self) -> bool:

        return False

    def disable_wake_on_ac(self) -> bool:

        return False

    def wake_on_lan_supported(self) -> bool:

        return True

    def enable_wake_on_lan(self) -> bool:

        return False

    def disable_wake_on_lan(self) -> bool:

        return False

    # =====================================================
    # Power
    # =====================================================

    def power_restore_supported(self) -> bool:

        return True

    def enable_power_restore(self) -> bool:

        return False

    # =====================================================
    # Battery
    # =====================================================

    def battery_settings_supported(self) -> bool:

        return True

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
        """
        Most Dell consumer and enterprise laptops do
        not expose direct firmware fan control through
        public interfaces.
        """

        return False

    # =====================================================
    # Capabilities
    # =====================================================

    def capabilities(self) -> dict[str, bool]:
        """
        Return Dell firmware capability information.
        """

        capabilities = super().capabilities()

        capabilities.update(
            {
                "boot_mode": True,
                "pxe": True,
                "virtualization": True,
                "iommu": True,
                "secure_boot": True,
                "tpm": True,
                "wake_on_ac": True,
                "wake_on_lan": True,
                "power_restore": True,
                "battery": True,
            }
        )

        return capabilities

    # =====================================================
    # Export
    # =====================================================

    def to_dict(self) -> dict[str, object]:
        """
        Export Dell provider information.
        """

        data = super().to_dict()

        data["provider"] = "DellProvider"
        data["vendor"] = "Dell"

        return data