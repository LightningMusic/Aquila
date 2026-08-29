"""
Project Aquila
=============

BIOS Manager

Coordinates firmware detection, provider selection,
and firmware configuration for supported BIOS/UEFI
vendors.

This manager acts as the single entry point for the
rest of Aquila. Individual vendor implementations are
handled by provider classes under bios.providers.

Rewrite notes (current provider architecture)
----------------------------------------------
Earlier revisions of this module were written against an older provider
contract (``get_manufacturer()``, ``get_boot_mode()``, ``capabilities()``,
``boot_mode_supported()`` / ``set_boot_mode_uefi()``, ``pxe_supported()``,
``battery_settings_supported()``, and similar) that no longer exists on
``bios.providers.base.BIOSProvider``. Every call in this module has been
re-mapped onto the current contract; three concepts had no direct current
equivalent and are handled honestly rather than papered over:

* **Boot-mode toggling** (UEFI <-> Legacy/CSM) is not exposed by any
  Version 1.0 provider -- no vendor tooling used by this project publishes
  a scriptable interface for it. ``boot_mode_supported()`` /
  ``set_boot_mode_uefi()`` / ``set_boot_mode_legacy()`` are kept for API
  compatibility but always honestly report unsupported.
* **PXE boot toggling** is explicitly out of scope for Version 1.0 (see the
  SRS, Section 5, Excluded capabilities: "PXE network deployment"). The
  ``pxe_supported()`` / ``enable_pxe()`` / ``disable_pxe()`` methods are
  kept for API compatibility but always honestly report unsupported.
* **Battery health mode** is a vendor-defined *string* setting on the
  current contract (``get_battery_health_mode()`` /
  ``set_battery_health_mode(mode: str)``), not a boolean toggle. The
  ``enable_battery_health_mode()`` / ``disable_battery_health_mode()``
  boolean convenience wrappers are kept (``bios.battery`` depends on
  them), but they now send the ``"Enable"`` / ``"Disable"`` value
  convention already used by every other boolean-style firmware setting
  in this codebase's Lenovo provider, rather than the fabricated
  placeholder the old contract implied -- see
  ``enable_battery_health_mode()``'s own docstring for the caveat. A
  caller that knows the exact vendor-reported value should call
  ``set_battery_health_mode(mode)`` directly instead.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from bios.detection import BIOSDetection
from bios.models import BIOSMode, BootDevice, BootDeviceType, FirmwareInformation

from bios.providers.base import BIOSProvider
from bios.providers.generic_uefi import GenericUEFIProvider
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
    • Expose common API to Aquila
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

        ``BIOSDetection.provider()`` both selects and connects the active
        provider, so the returned provider's own collected firmware
        information is used directly rather than being gathered a second
        time.
        """

        logger.info(
            "Initializing firmware detection..."
        )

        self.provider = self.detector.provider()

        try:
            self.firmware = self.provider.firmware_information()
        except Exception:
            logger.exception(
                "Unable to collect firmware information from provider %s.",
                self.provider.provider_name(),
            )
            self.firmware = None
            return False

        logger.info(
            "Using provider %s",
            self.provider.provider_name(),
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

        try:
            self.provider.disconnect()
        except Exception:
            logger.debug(
                "Error disconnecting previous provider before redetection.",
                exc_info=True,
            )

        self.detector = BIOSDetection()

        return self.initialize()

    def provider_name(self) -> str:
        """
        Returns the active provider's stable name (e.g. ``"dell"``).
        """

        return self.provider.provider_name()

    def provider_class_name(self) -> str:
        """
        Returns the active provider's Python class name.
        """

        return type(self.provider).__name__

    def provider_vendor(self) -> str:
        """
        Returns the vendor handled by the active provider.
        """

        return self.provider.vendor().value

    def provider_capabilities(self) -> Dict[str, bool]:
        """
        Returns the firmware capabilities confirmed supported by the
        currently selected provider.

        Built from ``supported_features()``, the current contract's
        capability-discovery method; a feature's absence from the
        returned dictionary means it is not confirmed supported, not
        that it is confirmed unsupported.
        """

        try:
            features = self.provider.supported_features()
        except Exception:
            logger.exception("Unable to read provider supported features.")
            return {}

        return {name: True for name in sorted(features)}

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

        If validation fails, Aquila automatically performs
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
        """
        Returns True when a provider object is present.

        ``self.provider`` is always a real ``BIOSProvider`` instance --
        it defaults to ``UnknownProvider`` at construction and after
        ``reset()`` rather than ever being ``None`` -- so this always
        returns True. It is kept for API compatibility; callers that
        want to know whether a *specific vendor* provider (rather than
        the generic fallback) was detected should use
        ``provider_available()`` instead.
        """

        return True

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

        return self.ensure_provider().manufacturer()

    def vendor(self) -> str:
        """
        Returns the BIOS/UEFI vendor.
        """

        return self.ensure_provider().vendor().value

    def model(self) -> str:
        """
        Returns the system model.
        """

        return self.ensure_provider().model()

    def bios_version(self) -> str:
        """
        Returns the installed BIOS version.
        """

        return self.ensure_provider().bios_version()

    def bios_release_date(self) -> str:
        """
        Returns the BIOS release date as an ISO-8601 string, or an empty
        string when unavailable.

        The current contract's ``bios_release_date()`` returns ``date.min``
        (not ``None``) as its "unavailable" sentinel, so both are treated
        as unavailable here.
        """

        release_date = self.ensure_provider().bios_release_date()

        if release_date == date.min:
            return ""

        return release_date.isoformat()

    def serial_number(self) -> str:
        """
        Returns the system serial number.
        """

        return self.ensure_provider().serial_number()

    def uuid(self) -> str:
        """
        Returns the SMBIOS UUID.
        """

        return self.ensure_provider().system_uuid()

    def asset_tag(self) -> str:
        """
        Returns the asset tag, if available.

        Asset tag reporting is a per-provider extension, not part of the
        formal ``BIOSProvider`` contract (not every provider exposes an
        SMBIOS chassis asset tag), so this degrades honestly to an empty
        string when the active provider does not implement it.
        """

        method = getattr(self.ensure_provider(), "asset_tag", None)

        if method is None:
            return ""

        try:
            return str(method())
        except Exception:
            logger.debug("asset_tag() failed on the active provider.", exc_info=True)
            return ""

    def boot_mode(self) -> str:
        """
        Returns the current firmware boot mode.
        """

        return self.ensure_provider().bios_mode().value

    # =====================================================
    # Convenience Helpers
    # =====================================================

    def is_uefi(self) -> bool:

        if self.firmware is None:
            return False

        return self.firmware.mode is BIOSMode.UEFI

    def is_legacy(self) -> bool:

        if self.firmware is None:
            return False

        return self.firmware.mode is BIOSMode.LEGACY

    def supports_secure_boot(self) -> bool:

        return self.ensure_provider().secure_boot_supported()

    def supports_virtualization(self) -> bool:

        return self.ensure_provider().virtualization_supported()

    def supports_iommu(self) -> bool:

        return self.ensure_provider().iommu_supported()

    def supports_tpm(self) -> bool:

        return self.ensure_provider().tpm_supported()

    def supports_pxe(self) -> bool:
        """
        Always returns False.

        PXE network deployment is explicitly out of scope for Version 1.0
        (SRS Section 5, Excluded capabilities), and no current provider
        implements a PXE-toggle interface. Kept for API compatibility.
        """

        return False

    def supports_wake_on_lan(self) -> bool:

        return self.ensure_provider().wake_on_lan_supported()

    def supports_wake_on_ac(self) -> bool:
        """
        Returns whether automatic power restoration on AC power return is
        supported.

        Maps onto the current contract's ``restore_power_on_ac_supported()``
        -- the old ``wake_on_ac_supported()`` name does not exist on the
        current provider contract.
        """

        return self.ensure_provider().restore_power_on_ac_supported()

    def supports_power_restore(self) -> bool:

        return self.ensure_provider().restore_power_on_ac_supported()

    def supports_battery_management(self) -> bool:
        """
        Returns True if the active provider supports either battery
        charge-limit management or battery health-mode management.
        """

        provider = self.ensure_provider()

        return (
            provider.battery_charge_limit_supported()
            or provider.battery_health_mode_supported()
        )

    def supports_fan_control(self) -> bool:
        """
        Always returns False.

        No current provider exposes a fan-control interface; no vendor
        tooling used by this project publishes one. Kept for API
        compatibility.
        """

        return False

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
        Always returns False.

        No Version 1.0 provider exposes a firmware boot-mode (UEFI versus
        Legacy/CSM) toggle interface. Kept for API compatibility.
        """

        return False

    def set_boot_mode_uefi(self) -> bool:
        """
        Configure the firmware to boot using UEFI mode.

        Always honestly reports failure -- see ``boot_mode_supported()``.
        """

        logger.warning(
            "Boot mode configuration is not supported by any Version 1.0 "
            "provider."
        )

        return False

    def set_boot_mode_legacy(self) -> bool:
        """
        Configure the firmware to boot using Legacy/CSM
        mode.

        Always honestly reports failure -- see ``boot_mode_supported()``.
        """

        logger.warning(
            "Boot mode configuration is not supported by any Version 1.0 "
            "provider."
        )

        return False

    # =====================================================
    # Boot Order
    # =====================================================

    def boot_order(self) -> List[str]:
        """
        Returns the current firmware boot order as a list of device
        identifiers.
        """

        return [device.identifier for device in self.ensure_provider().boot_order()]

    def set_boot_order(
        self,
        devices: List[str],
    ) -> bool:
        """
        Applies a new firmware boot order.

        ``devices`` is a list of boot-device identifiers, as returned by
        :meth:`boot_order`. The current contract's ``set_boot_order()``
        operates on full ``BootDevice`` objects rather than bare
        identifiers, so this reorders the provider's own currently-known
        ``BootDevice`` entries to match the requested identifier order
        rather than fabricating placeholder entries. Unknown identifiers
        are ignored and logged.
        """

        logger.info(
            "Applying boot order: %s",
            devices,
        )

        provider = self.ensure_provider()
        current = {device.identifier: device for device in provider.boot_order()}

        ordered: List[BootDevice] = []
        unknown: List[str] = []

        for identifier in devices:
            device = current.get(identifier)
            if device is None:
                unknown.append(identifier)
                continue
            ordered.append(device)

        if unknown:
            logger.warning(
                "Ignoring unknown boot device identifiers: %s", unknown
            )

        if not ordered:
            logger.warning("No known boot devices to apply an order for.")
            return False

        return provider.set_boot_order(ordered)

    def set_usb_first(self) -> bool:
        """
        Places USB devices at the top of the firmware boot
        order.

        This is used during automated Proxmox deployment. Built from the
        current contract's real ``boot_order()`` / ``set_boot_order()``
        primitives rather than a vendor-specific shortcut, since no
        provider exposes one directly.
        """

        logger.info(
            "Setting USB as first boot device..."
        )

        provider = self.ensure_provider()
        current = provider.boot_order()

        if not current:
            logger.warning("No boot devices are available to reorder.")
            return False

        usb_devices = [d for d in current if d.device_type == BootDeviceType.USB]
        other_devices = [d for d in current if d.device_type != BootDeviceType.USB]

        if not usb_devices:
            logger.warning("No USB boot devices were found.")
            return False

        result = provider.set_boot_order([*usb_devices, *other_devices])

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
        """
        Always returns False. See :meth:`supports_pxe`.
        """

        return False

    def enable_pxe(self) -> bool:
        """
        Always returns False. PXE network deployment is out of scope for
        Version 1.0 (SRS Section 5, Excluded capabilities).
        """

        logger.warning(
            "PXE boot is not supported (out of scope for Version 1.0)."
        )

        return False

    def disable_pxe(self) -> bool:
        """
        Always returns False. See :meth:`enable_pxe`.
        """

        return False

    # =====================================================
    # Deployment Preparation
    # =====================================================

    def prepare_for_proxmox_install(self) -> bool:
        """
        Performs the firmware configuration required for
        unattended Proxmox installation.

        This method is intended to be called by Aquila's
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
        for Aquila Proxmox deployments.

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

        return self.ensure_provider().restore_power_on_ac_supported()

    def enable_wake_on_ac(self) -> bool:

        provider = self.ensure_provider()

        if not provider.restore_power_on_ac_supported():

            logger.warning(
                "Restore-power-on-AC is not supported."
            )

            return False

        logger.info("Enabling restore power on AC...")

        return provider.enable_restore_power_on_ac()

    def disable_wake_on_ac(self) -> bool:

        provider = self.ensure_provider()

        if not provider.restore_power_on_ac_supported():

            return False

        logger.info("Disabling restore power on AC...")

        return provider.disable_restore_power_on_ac()

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
        """
        Returns True if the active provider supports either battery
        charge-limit management or battery health-mode management.

        Alias of :meth:`supports_battery_management`, kept for API
        compatibility.
        """

        return self.supports_battery_management()

    def set_charge_limit(
        self,
        percent: int,
    ) -> bool:
        """
        Sets the battery charging limit.

        Aquila commonly uses 80% for always-on Proxmox
        nodes to reduce long-term battery wear.
        """

        provider = self.ensure_provider()

        if not provider.battery_charge_limit_supported():

            logger.warning(
                "Battery charge-limit management is unsupported."
            )

            return False

        logger.info(
            "Setting battery charge limit to %d%%",
            percent,
        )

        return provider.set_charge_limit(percent)

    def get_charge_limit(self) -> int:
        """
        Returns the configured battery charge limit as a percentage.
        """

        return self.ensure_provider().get_charge_limit()

    def get_battery_health_mode(self) -> str:
        """
        Returns the active battery health mode, as reported by the
        vendor's own firmware setting (e.g. Lenovo Conservation Mode, HP's
        battery-health setting). Empty when unsupported or unknown.
        """

        return self.ensure_provider().get_battery_health_mode()

    def set_battery_health_mode(self, mode: str) -> bool:
        """
        Sets the active battery health mode to a vendor-reported value.

        Unlike charge-limit management, battery health mode is a
        vendor-defined string setting, not a universal boolean -- callers
        should supply a value obtained from :meth:`get_battery_health_mode`
        or the provider's own settings registry rather than a guessed
        "enabled"/"disabled" string.
        """

        provider = self.ensure_provider()

        if not provider.battery_health_mode_supported():

            logger.warning(
                "Battery health-mode management is unsupported."
            )

            return False

        logger.info(
            "Setting battery health mode to %r",
            mode,
        )

        return provider.set_battery_health_mode(mode)

    def enable_battery_health_mode(self) -> bool:
        """
        Enables the vendor's battery preservation / health mode using its
        common "Enable" convention.

        Battery health mode is a vendor-defined string setting (see
        :meth:`set_battery_health_mode`), not a formal boolean on the
        provider contract. This convenience wrapper assumes the
        ``"Enable"`` / ``"Disable"`` value convention already used by
        every other boolean-style firmware setting in this codebase's
        Lenovo provider (see ``LenovoProvider._write_bool_setting``) --
        the same convention most vendor WMI BIOS-setting interfaces of
        this style use. If a specific system's firmware uses different
        wording, call :meth:`set_battery_health_mode` directly with a
        value read from :meth:`get_battery_health_mode` or the provider's
        settings registry instead of relying on this assumption.
        """

        return self.set_battery_health_mode("Enable")

    def disable_battery_health_mode(self) -> bool:
        """
        Disables the vendor's battery preservation / health mode using its
        common "Disable" convention. See :meth:`enable_battery_health_mode`
        for the convention this assumes.
        """

        return self.set_battery_health_mode("Disable")

    # =====================================================
    # Recommended Aquila Configuration
    # =====================================================

    def apply_aquila_defaults(self) -> bool:
        """
        Applies the firmware configuration recommended
        for Aquila deployment.

        These defaults are safe for nearly every
        Proxmox node. Battery health mode is intentionally left untouched
        here even though :meth:`enable_battery_health_mode` exists --
        toggling it relies on an inferred vendor convention (see that
        method's docstring) rather than a verified one, and an unattended
        deployment default should not silently apply an assumption. Call
        :meth:`enable_battery_health_mode` (or :meth:`set_battery_health_mode`
        with a confirmed value) explicitly when appropriate.
        """

        logger.info(
            "Applying Aquila firmware defaults..."
        )

        success = True

        success &= self.prepare_for_proxmox_install()

        success &= self.prepare_virtualization_environment()

        if self.wake_on_ac_supported():
            self.enable_wake_on_ac()

        if self.wake_on_lan_supported():
            self.enable_wake_on_lan()

        if self.ensure_provider().battery_charge_limit_supported():
            self.set_charge_limit(80)

        return success

    # =====================================================
    # Reporting
    # =====================================================

    def report(self) -> Dict[str, object]:
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

    def export(self) -> Dict[str, object]:
        """
        Alias for report().

        Used by Aquila reporting components.
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

        try:
            self.provider.disconnect()
        except Exception:
            logger.debug(
                "Error disconnecting provider during reset.", exc_info=True
            )

        self.firmware = None

        self.provider = UnknownProvider()

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
