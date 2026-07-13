"""
Project Orion
=============

BIOS Manager

Coordinates firmware detection, provider selection,
and firmware configuration for supported BIOS/UEFI
vendors.

This manager acts as the single entry point for the
rest of Orion. Individual vendor implementations are
handled by provider classes under bios.providers.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Type

from bios.detection import BIOSDetection
from bios.firmware import FirmwareInformation

from bios.providers.base import BIOSProvider
from bios.providers.unknown import UnknownProvider

logger = logging.getLogger(__name__)


class BIOSManager:
    """
    Central firmware manager.

    Responsibilities
    ----------------
    • Detect firmware
    • Select correct provider
    • Configure firmware
    • Expose common API to Orion
    • Generate firmware reports
    """

    def __init__(self) -> None:

        logger.info("Initializing BIOS Manager...")

        self.detector = BIOSDetection()

        self.firmware: FirmwareInformation | None = None

        self.provider: BIOSProvider = UnknownProvider()

        logger.info(
            "BIOS Manager initialized."
        )

    # =====================================================
    # Initialization
    # =====================================================

    def initialize(self) -> bool:
        """
        Detect firmware and select the correct provider.
        """

        logger.info(
            "Initializing firmware detection..."
        )

        self.firmware = self.detector.firmware_information()

        self.provider = self.detector.provider()

        if self.firmware is None:

            logger.error(
                "Unable to detect firmware."
            )

            return False

        logger.info(
            "Using provider %s",
            self.provider.__class__.__name__,
        )

        return True

    # =====================================================
    # Detection
    # =====================================================

    def redetect(self) -> bool:
        """
        Performs firmware detection again.
        """

        logger.info(
            "Re-detecting firmware..."
        )

        self.detector = BIOSDetection()

        return self.initialize()

    def provider_name(self) -> str:
        """
        Returns the active provider name.
        """

        return self.provider.__class__.__name__

    def provider_vendor(self) -> str:
        """
        Returns the vendor handled by the active provider.
        """

        return self.provider.get_vendor()

    def provider_capabilities(self) -> dict[str, bool]:
        """
        Returns all firmware capabilities supported by the
        currently selected provider.
        """

        return self.provider.capabilities()

    def provider_available(self) -> bool:
        """
        Returns True when a valid provider has been
        selected.
        """

        return not isinstance(
            self.provider,
            UnknownProvider,
        )

    # =====================================================
    # Validation
    # =====================================================

    def validate_provider(self) -> bool:
        """
        Confirms that the active provider still matches the
        detected firmware.
        """

        if self.firmware is None:

            return False

        try:

            return self.provider.detect()

        except Exception:

            logger.exception(
                "Provider validation failed."
            )

            return False

    def ensure_provider(self) -> BIOSProvider:
        """
        Returns a valid provider.

        If validation fails, Orion automatically performs
        another firmware detection.
        """

        if not self.validate_provider():

            logger.warning(
                "Provider validation failed. "
                "Attempting recovery..."
            )

            self.redetect()

        return self.provider

    # =====================================================
    # Information
    # =====================================================

    def firmware_detected(self) -> bool:

        return self.firmware is not None

    def provider_loaded(self) -> bool:

        return self.provider is not None

    def supported_vendor(self) -> bool:
        """
        Returns True if the firmware vendor is explicitly
        supported rather than falling back to the generic
        provider.
        """

        return not isinstance(
            self.provider,
            (UnknownProvider, GenericUEFIProvider),
        )

    def is_unknown(self) -> bool:

        return isinstance(
            self.provider,
            UnknownProvider,
        )

    def is_generic_uefi(self) -> bool:

        return isinstance(
            self.provider,
            GenericUEFIProvider,
        )
    
    # =====================================================
    # Firmware Information Accessors
    # =====================================================

    def firmware_information(self) -> Optional[FirmwareInformation]:
        """
        Returns the complete firmware information object.
        """

        return self.firmware

    def manufacturer(self) -> str:
        """
        Returns the system manufacturer.
        """

        return self.ensure_provider().get_manufacturer()

    def vendor(self) -> str:
        """
        Returns the BIOS/UEFI vendor.
        """

        return self.ensure_provider().get_vendor()

    def model(self) -> str:
        """
        Returns the system model.
        """

        return self.ensure_provider().get_model()

    def bios_version(self) -> str:
        """
        Returns the installed BIOS version.
        """

        return self.ensure_provider().get_version()

    def bios_release_date(self) -> str:
        """
        Returns the BIOS release date.
        """

        return self.ensure_provider().get_release_date()

    def serial_number(self) -> str:
        """
        Returns the system serial number.
        """

        return self.ensure_provider().get_serial_number()

    def uuid(self) -> str:
        """
        Returns the SMBIOS UUID.
        """

        return self.ensure_provider().get_uuid()

    def asset_tag(self) -> str:
        """
        Returns the asset tag, if available.
        """

        return self.ensure_provider().get_asset_tag()

    def boot_mode(self) -> str:
        """
        Returns the current firmware boot mode.
        """

        return self.ensure_provider().get_boot_mode()

    # =====================================================
    # Convenience Helpers
    # =====================================================

    def is_uefi(self) -> bool:

        if self.firmware is None:
            return False

        return self.firmware.is_uefi

    def is_legacy(self) -> bool:

        if self.firmware is None:
            return False

        return self.firmware.is_legacy

    def supports_secure_boot(self) -> bool:

        return self.ensure_provider().secure_boot_supported()

    def supports_virtualization(self) -> bool:

        return self.ensure_provider().virtualization_supported()

    def supports_iommu(self) -> bool:

        return self.ensure_provider().iommu_supported()

    def supports_tpm(self) -> bool:

        return self.ensure_provider().tpm_supported()

    def supports_pxe(self) -> bool:

        return self.ensure_provider().pxe_supported()

    def supports_wake_on_lan(self) -> bool:

        return self.ensure_provider().wake_on_lan_supported()

    def supports_wake_on_ac(self) -> bool:

        return self.ensure_provider().wake_on_ac_supported()

    def supports_power_restore(self) -> bool:

        return self.ensure_provider().power_restore_supported()

    def supports_battery_management(self) -> bool:

        return self.ensure_provider().battery_settings_supported()

    def supports_fan_control(self) -> bool:

        return self.ensure_provider().fan_control_supported()

    # =====================================================
    # Export
    # =====================================================

    def information_dict(self) -> Dict[str, object]:
        """
        Returns all firmware information as a dictionary.
        """

        return {
            "provider": self.provider_name(),
            "vendor": self.vendor(),
            "manufacturer": self.manufacturer(),
            "model": self.model(),
            "bios_version": self.bios_version(),
            "bios_release_date": self.bios_release_date(),
            "serial_number": self.serial_number(),
            "asset_tag": self.asset_tag(),
            "uuid": self.uuid(),
            "boot_mode": self.boot_mode(),
            "capabilities": self.provider_capabilities(),
        }

    def save_information(
        self,
        destination: str | Path,
    ) -> Path:
        """
        Saves the firmware information as a JSON report.
        """

        import json

        destination = Path(destination)

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with destination.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                self.information_dict(),
                file,
                indent=4,
                sort_keys=True,
            )

        logger.info(
            "Firmware report written to %s",
            destination,
        )

        return destination
    
    # =====================================================
    # Boot Configuration
    # =====================================================

    def boot_mode_supported(self) -> bool:
        """
        Returns True if the active provider supports
        changing the firmware boot mode.
        """

        return self.ensure_provider().boot_mode_supported()

    def set_boot_mode_uefi(self) -> bool:
        """
        Configure the firmware to boot using UEFI mode.
        """

        provider = self.ensure_provider()

        if not provider.boot_mode_supported():

            logger.warning(
                "Boot mode configuration is not supported."
            )

            return False

        logger.info(
            "Configuring firmware for UEFI boot..."
        )

        result = provider.set_boot_mode_uefi()

        if result:

            logger.info(
                "UEFI boot mode configured successfully."
            )

        else:

            logger.warning(
                "Failed to configure UEFI boot mode."
            )

        return result

    def set_boot_mode_legacy(self) -> bool:
        """
        Configure the firmware to boot using Legacy/CSM
        mode.
        """

        provider = self.ensure_provider()

        if not provider.boot_mode_supported():

            logger.warning(
                "Boot mode configuration is not supported."
            )

            return False

        logger.info(
            "Configuring firmware for Legacy boot..."
        )

        result = provider.set_boot_mode_legacy()

        if result:

            logger.info(
                "Legacy boot mode configured successfully."
            )

        else:

            logger.warning(
                "Failed to configure Legacy boot mode."
            )

        return result

    # =====================================================
    # Boot Order
    # =====================================================

    def boot_order(self) -> list[str]:
        """
        Returns the current firmware boot order.
        """

        return self.ensure_provider().get_boot_order()

    def set_boot_order(
        self,
        devices: list[str],
    ) -> bool:
        """
        Applies a new firmware boot order.
        """

        logger.info(
            "Applying boot order: %s",
            devices,
        )

        return self.ensure_provider().set_boot_order(
            devices,
        )

    def set_usb_first(self) -> bool:
        """
        Places USB devices at the top of the firmware boot
        order.

        This is used during automated Proxmox deployment.
        """

        logger.info(
            "Setting USB as first boot device..."
        )

        result = self.ensure_provider().set_usb_first()

        if result:

            logger.info(
                "USB boot configured successfully."
            )

        else:

            logger.warning(
                "Unable to configure USB boot."
            )

        return result

    # =====================================================
    # PXE Boot
    # =====================================================

    def pxe_supported(self) -> bool:

        return self.ensure_provider().pxe_supported()

    def enable_pxe(self) -> bool:
        """
        Enables PXE/network boot.
        """

        provider = self.ensure_provider()

        if not provider.pxe_supported():

            logger.warning(
                "PXE boot is not supported."
            )

            return False

        logger.info(
            "Enabling PXE boot..."
        )

        return provider.enable_pxe()

    def disable_pxe(self) -> bool:
        """
        Disables PXE/network boot.
        """

        provider = self.ensure_provider()

        if not provider.pxe_supported():

            return False

        logger.info(
            "Disabling PXE boot..."
        )

        return provider.disable_pxe()

    # =====================================================
    # Deployment Preparation
    # =====================================================

    def prepare_for_proxmox_install(self) -> bool:
        """
        Performs the firmware configuration required for
        unattended Proxmox installation.

        This method is intended to be called by Orion's
        deployment workflow before the machine reboots
        into the installer.
        """

        logger.info(
            "Preparing firmware for Proxmox deployment..."
        )

        success = True

        if self.boot_mode_supported():
            success &= self.set_boot_mode_uefi()

        if self.pxe_supported():
            self.disable_pxe()

        success &= self.set_usb_first()

        return success
    
    # =====================================================
    # Virtualization
    # =====================================================

    def virtualization_supported(self) -> bool:
        """
        Returns True if the active firmware supports
        hardware virtualization.
        """

        return self.ensure_provider().virtualization_supported()

    def virtualization_enabled(self) -> bool:
        """
        Returns True if virtualization is currently enabled.
        """

        return self.ensure_provider().virtualization_enabled()

    def enable_virtualization(self) -> bool:
        """
        Enables Intel VT-x or AMD-V in firmware.

        Required for Proxmox virtualization.
        """

        provider = self.ensure_provider()

        if not provider.virtualization_supported():

            logger.warning(
                "Virtualization is not supported."
            )

            return False

        logger.info(
            "Enabling CPU virtualization..."
        )

        result = provider.enable_virtualization()

        if result:

            logger.info(
                "Virtualization enabled."
            )

        else:

            logger.warning(
                "Unable to enable virtualization."
            )

        return result

    # =====================================================
    # IOMMU / VT-d / AMD-Vi
    # =====================================================

    def iommu_supported(self) -> bool:

        return self.ensure_provider().iommu_supported()

    def iommu_enabled(self) -> bool:

        return self.ensure_provider().iommu_enabled()

    def enable_iommu(self) -> bool:
        """
        Enables IOMMU (VT-d / AMD-Vi).

        Required for PCI passthrough and GPU assignment.
        """

        provider = self.ensure_provider()

        if not provider.iommu_supported():

            logger.warning(
                "IOMMU is not supported."
            )

            return False

        logger.info(
            "Enabling IOMMU..."
        )

        result = provider.enable_iommu()

        if result:

            logger.info(
                "IOMMU enabled."
            )

        else:

            logger.warning(
                "Unable to enable IOMMU."
            )

        return result

    # =====================================================
    # TPM
    # =====================================================

    def tpm_supported(self) -> bool:

        return self.ensure_provider().tpm_supported()

    def tpm_enabled(self) -> bool:

        return self.ensure_provider().tpm_enabled()

    def enable_tpm(self) -> bool:
        """
        Enables TPM if available.
        """

        provider = self.ensure_provider()

        if not provider.tpm_supported():

            logger.warning(
                "TPM is not supported."
            )

            return False

        logger.info(
            "Enabling TPM..."
        )

        result = provider.enable_tpm()

        if result:

            logger.info(
                "TPM enabled."
            )

        else:

            logger.warning(
                "Unable to enable TPM."
            )

        return result

    # =====================================================
    # Secure Boot
    # =====================================================

    def secure_boot_supported(self) -> bool:

        return self.ensure_provider().secure_boot_supported()

    def secure_boot_enabled(self) -> bool:

        return self.ensure_provider().secure_boot_enabled()

    def enable_secure_boot(self) -> bool:
        """
        Enables Secure Boot.
        """

        provider = self.ensure_provider()

        if not provider.secure_boot_supported():

            logger.warning(
                "Secure Boot is not supported."
            )

            return False

        logger.info(
            "Enabling Secure Boot..."
        )

        result = provider.enable_secure_boot()

        if result:

            logger.info(
                "Secure Boot enabled."
            )

        else:

            logger.warning(
                "Unable to enable Secure Boot."
            )

        return result

    def disable_secure_boot(self) -> bool:
        """
        Disables Secure Boot.

        Proxmox installations often require this depending
        on the deployment configuration.
        """

        provider = self.ensure_provider()

        if not provider.secure_boot_supported():

            return False

        logger.info(
            "Disabling Secure Boot..."
        )

        result = provider.disable_secure_boot()

        if result:

            logger.info(
                "Secure Boot disabled."
            )

        else:

            logger.warning(
                "Unable to disable Secure Boot."
            )

        return result

    # =====================================================
    # Deployment Virtualization Profile
    # =====================================================

    def prepare_virtualization_environment(self) -> bool:
        """
        Configures firmware with the settings recommended
        for Orion Proxmox deployments.

        This prepares the system for:
            • Proxmox VE
            • Nested virtualization
            • PCI passthrough
            • Future GPU assignment
            • Local AI workloads
        """

        logger.info(
            "Preparing virtualization environment..."
        )

        success = True

        if self.virtualization_supported():
            success &= self.enable_virtualization()

        if self.iommu_supported():
            success &= self.enable_iommu()

        if self.tpm_supported():
            self.enable_tpm()

        # Secure Boot is intentionally disabled for
        # maximum deployment compatibility.
        if self.secure_boot_supported():
            self.disable_secure_boot()

        return success
    
    # =====================================================
    # Wake Features
    # =====================================================

    def wake_on_ac_supported(self) -> bool:
        """
        Returns True if the firmware supports restoring
        power automatically when AC power is connected.
        """

        return self.ensure_provider().wake_on_ac_supported()

    def enable_wake_on_ac(self) -> bool:

        provider = self.ensure_provider()

        if not provider.wake_on_ac_supported():

            logger.warning(
                "Wake-on-AC is not supported."
            )

            return False

        logger.info("Enabling Wake-on-AC...")

        return provider.enable_wake_on_ac()

    def disable_wake_on_ac(self) -> bool:

        provider = self.ensure_provider()

        if not provider.wake_on_ac_supported():

            return False

        logger.info("Disabling Wake-on-AC...")

        return provider.disable_wake_on_ac()

    def wake_on_lan_supported(self) -> bool:

        return self.ensure_provider().wake_on_lan_supported()

    def enable_wake_on_lan(self) -> bool:

        provider = self.ensure_provider()

        if not provider.wake_on_lan_supported():

            logger.warning(
                "Wake-on-LAN is not supported."
            )

            return False

        logger.info("Enabling Wake-on-LAN...")

        return provider.enable_wake_on_lan()

    def disable_wake_on_lan(self) -> bool:

        provider = self.ensure_provider()

        if not provider.wake_on_lan_supported():

            return False

        logger.info("Disabling Wake-on-LAN...")

        return provider.disable_wake_on_lan()

    # =====================================================
    # Battery Management
    # =====================================================

    def battery_settings_supported(self) -> bool:

        return self.ensure_provider().battery_settings_supported()

    def set_charge_limit(
        self,
        percent: int,
    ) -> bool:
        """
        Sets the battery charging limit.

        Orion commonly uses 80% for always-on Proxmox
        nodes to reduce long-term battery wear.
        """

        provider = self.ensure_provider()

        if not provider.battery_settings_supported():

            logger.warning(
                "Battery management unsupported."
            )

            return False

        logger.info(
            "Setting battery charge limit to %d%%",
            percent,
        )

        return provider.set_charge_limit(percent)

    def enable_battery_health_mode(self) -> bool:

        provider = self.ensure_provider()

        if not provider.battery_settings_supported():
            return False

        logger.info(
            "Enabling battery health mode..."
        )

        return provider.enable_battery_health_mode()

    def disable_battery_health_mode(self) -> bool:

        provider = self.ensure_provider()

        if not provider.battery_settings_supported():
            return False

        logger.info(
            "Disabling battery health mode..."
        )

        return provider.disable_battery_health_mode()

    # =====================================================
    # Recommended Orion Configuration
    # =====================================================

    def apply_orion_defaults(self) -> bool:
        """
        Applies the firmware configuration recommended
        for Orion deployment.

        These defaults are safe for nearly every
        Proxmox node.
        """

        logger.info(
            "Applying Orion firmware defaults..."
        )

        success = True

        success &= self.prepare_for_proxmox_install()

        success &= self.prepare_virtualization_environment()

        if self.wake_on_ac_supported():
            self.enable_wake_on_ac()

        if self.wake_on_lan_supported():
            self.enable_wake_on_lan()

        if self.battery_settings_supported():

            self.enable_battery_health_mode()

            self.set_charge_limit(80)

        return success

    # =====================================================
    # Reporting
    # =====================================================

    def report(self) -> dict[str, object]:
        """
        Returns a complete BIOS report suitable for
        logging or serialization.
        """

        report = self.information_dict()

        report.update(
            {
                "provider_loaded": self.provider_loaded(),
                "supported_vendor": self.supported_vendor(),
                "virtualization_supported": self.virtualization_supported(),
                "virtualization_enabled": self.virtualization_enabled(),
                "iommu_supported": self.iommu_supported(),
                "iommu_enabled": self.iommu_enabled(),
                "secure_boot_supported": self.secure_boot_supported(),
                "secure_boot_enabled": self.secure_boot_enabled(),
                "tpm_supported": self.tpm_supported(),
                "tpm_enabled": self.tpm_enabled(),
                "wake_on_lan_supported": self.wake_on_lan_supported(),
                "wake_on_ac_supported": self.wake_on_ac_supported(),
                "battery_supported": self.battery_settings_supported(),
            }
        )

        return report

    # =====================================================
    # Export
    # =====================================================

    def export(self) -> dict[str, object]:
        """
        Alias for report().

        Used by Orion reporting components.
        """

        return self.report()

    # =====================================================
    # Cleanup
    # =====================================================

    def reset(self) -> None:
        """
        Clears cached firmware information and returns
        the manager to its initial state.
        """

        logger.info(
            "Resetting BIOS Manager..."
        )

        self.firmware = None

        self.provider = UnknownProvider(None)

    def shutdown(self) -> None:
        """
        Releases resources held by the BIOS Manager.

        Reserved for future firmware SDK integrations.
        """

        logger.info(
            "Shutting down BIOS Manager..."
        )

        self.reset()

    # =====================================================
    # Representation
    # =====================================================

    def __repr__(self) -> str:

        return (
            f"{self.__class__.__name__}("
            f"provider={self.provider_name()}, "
            f"vendor={self.vendor()}, "
            f"model={self.model()})"
        )

    def __str__(self) -> str:

        return (
            f"{self.vendor()} "
            f"{self.model()} "
            f"({self.provider_name()})"
        )