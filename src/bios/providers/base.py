"""
Project Orion
=============

BIOS Provider Base

Defines the abstract interface that all BIOS/UEFI
providers must implement.

Every vendor-specific provider (Dell, HP, Lenovo,
Acer, ASUS, MSI, Framework, Gigabyte, etc.) derives
from this class so the rest of Orion never needs to
know which firmware vendor is being used.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BIOSProvider(ABC):
    """
    Abstract base class for BIOS/UEFI providers.
    """

    def __init__(self) -> None:
        self.vendor: str = "Unknown"

    # =========================================================
    # Detection
    # =========================================================

    @abstractmethod
    def detect(self) -> bool:
        """
        Determine whether this provider supports the
        current system.
        """

    # =========================================================
    # Firmware Information
    # =========================================================

    @abstractmethod
    def get_vendor(self) -> str:
        """
        Return the firmware vendor.
        """

    @abstractmethod
    def get_manufacturer(self) -> str:
        """
        Return the system manufacturer.
        """

    @abstractmethod
    def get_model(self) -> str:
        """
        Return the system model.
        """

    @abstractmethod
    def get_version(self) -> str:
        """
        Return the BIOS/UEFI version.
        """

    @abstractmethod
    def get_release_date(self) -> str:
        """
        Return the BIOS release date.
        """

    @abstractmethod
    def get_serial_number(self) -> str:
        """
        Return the system serial number.
        """

    @abstractmethod
    def get_asset_tag(self) -> str:
        """
        Return the asset tag if available.
        """

    @abstractmethod
    def get_uuid(self) -> str:
        """
        Return the hardware UUID.
        """

    # =========================================================
    # Boot Configuration
    # =========================================================

    @abstractmethod
    def boot_mode_supported(self) -> bool:
        """
        Return True if boot mode is configurable.
        """

    @abstractmethod
    def get_boot_mode(self) -> str:
        """
        Return the current boot mode.

        Example:
            UEFI
            Legacy
        """

    @abstractmethod
    def set_boot_mode_uefi(self) -> bool:
        """
        Configure the firmware for UEFI boot.
        """

    @abstractmethod
    def set_boot_mode_legacy(self) -> bool:
        """
        Configure the firmware for Legacy/CSM boot.
        """

    @abstractmethod
    def get_boot_order(self) -> list[str]:
        """
        Return the firmware boot order.
        """

    @abstractmethod
    def set_boot_order(
        self,
        devices: list[str],
    ) -> bool:
        """
        Configure the firmware boot order.
        """

    @abstractmethod
    def set_usb_first(self) -> bool:
        """
        Move USB devices to the top of the boot order.
        """

    # =========================================================
    # PXE / Network Boot
    # =========================================================

    @abstractmethod
    def pxe_supported(self) -> bool:
        """
        Return True if PXE is supported.
        """

    @abstractmethod
    def enable_pxe(self) -> bool:
        """
        Enable PXE boot.
        """

    @abstractmethod
    def disable_pxe(self) -> bool:
        """
        Disable PXE boot.
        """

    # =========================================================
    # Virtualization
    # =========================================================

    @abstractmethod
    def virtualization_supported(self) -> bool:
        """
        Return True if virtualization settings
        are available.
        """

    @abstractmethod
    def virtualization_enabled(self) -> bool:
        """
        Return whether virtualization is enabled.
        """

    @abstractmethod
    def enable_virtualization(self) -> bool:
        """
        Enable Intel VT-x or AMD-V.
        """

    # =========================================================
    # IOMMU / VT-d / AMD-Vi
    # =========================================================

    @abstractmethod
    def iommu_supported(self) -> bool:
        """
        Return True if IOMMU can be configured.
        """

    @abstractmethod
    def iommu_enabled(self) -> bool:
        """
        Return whether IOMMU is enabled.
        """

    @abstractmethod
    def enable_iommu(self) -> bool:
        """
        Enable IOMMU.
        """

    # =========================================================
    # Secure Boot
    # =========================================================

    @abstractmethod
    def secure_boot_supported(self) -> bool:
        """
        Return True if Secure Boot is supported.
        """

    @abstractmethod
    def secure_boot_enabled(self) -> bool:
        """
        Return the Secure Boot state.
        """

    @abstractmethod
    def enable_secure_boot(self) -> bool:
        """
        Enable Secure Boot.
        """

    @abstractmethod
    def disable_secure_boot(self) -> bool:
        """
        Disable Secure Boot.
        """

    # =========================================================
    # TPM
    # =========================================================

    @abstractmethod
    def tpm_supported(self) -> bool:
        """
        Return True if TPM exists.
        """

    @abstractmethod
    def tpm_enabled(self) -> bool:
        """
        Return whether TPM is enabled.
        """

    @abstractmethod
    def enable_tpm(self) -> bool:
        """
        Enable TPM.
        """

    # =========================================================
    # BIOS Password
    # =========================================================

    @abstractmethod
    def bios_password_set(self) -> bool:
        """
        Return whether a BIOS administrator password
        is configured.
        """

    # =========================================================
    # Wake Features
    # =========================================================

    @abstractmethod
    def wake_on_ac_supported(self) -> bool:
        """
        Return whether Wake-on-AC is supported.
        """

    @abstractmethod
    def enable_wake_on_ac(self) -> bool:
        """
        Enable Wake-on-AC.
        """

    @abstractmethod
    def disable_wake_on_ac(self) -> bool:
        """
        Disable Wake-on-AC.
        """

    @abstractmethod
    def wake_on_lan_supported(self) -> bool:
        """
        Return whether Wake-on-LAN is supported.
        """

    @abstractmethod
    def enable_wake_on_lan(self) -> bool:
        """
        Enable Wake-on-LAN.
        """

    @abstractmethod
    def disable_wake_on_lan(self) -> bool:
        """
        Disable Wake-on-LAN.
        """

    # =========================================================
    # Power
    # =========================================================

    @abstractmethod
    def power_restore_supported(self) -> bool:
        """
        Return whether automatic AC power recovery
        is supported.
        """

    @abstractmethod
    def enable_power_restore(self) -> bool:
        """
        Automatically power on after AC power returns.
        """

    # =========================================================
    # Battery
    # =========================================================

    @abstractmethod
    def battery_settings_supported(self) -> bool:
        """
        Return True if battery firmware settings
        are available.
        """

    @abstractmethod
    def set_charge_limit(
        self,
        percent: int,
    ) -> bool:
        """
        Configure the maximum battery charge level.
        """

    @abstractmethod
    def enable_battery_health_mode(self) -> bool:
        """
        Enable battery health mode.
        """

    @abstractmethod
    def disable_battery_health_mode(self) -> bool:
        """
        Disable battery health mode.
        """

    # =========================================================
    # Thermal
    # =========================================================

    @abstractmethod
    def fan_control_supported(self) -> bool:
        """
        Return whether firmware fan control exists.
        """

    # =========================================================
    # Capabilities
    # =========================================================

    @abstractmethod
    def capabilities(self) -> dict[str, bool]:
        """
        Return a dictionary describing supported
        firmware capabilities.
        """

    # =========================================================
    # Export
    # =========================================================

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """
        Export provider information.
        """