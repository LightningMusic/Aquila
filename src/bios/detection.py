"""
Project Orion
=============

BIOS Detection

Automatically detects the firmware vendor and selects
the correct BIOS provider implementation.

This module is the entry point for every BIOS operation
performed by Orion. The rest of the application should
never instantiate vendor providers directly. Instead,
it requests the active provider through BIOSDetection.

Design Goals
------------
* Automatic firmware detection
* Vendor abstraction
* Provider registry
* Graceful fallback
* Windows-first implementation
* Linux compatibility where practical
* Extensible provider architecture

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import platform
import subprocess
from typing import Type

from bios.firmware import FirmwareInformation

from bios.providers.base import BIOSProvider
from bios.providers.acer import AcerProvider
from bios.providers.asus import ASUSProvider
from bios.providers.dell import DellProvider
from bios.providers.framework import FrameworkProvider
from bios.providers.generic_uefi import GenericUEFIProvider
from bios.providers.gigabyte import GigabyteProvider
from bios.providers.hp import HPProvider
from bios.providers.lenovo import LenovoProvider
from bios.providers.msi import MSIProvider
from bios.providers.unknown import UnknownProvider

logger = logging.getLogger(__name__)



class BIOSDetection:
    """
    Detects the correct BIOS provider.

    Only one provider should ever be active for a
    running instance of Orion.
    """

    _provider: BIOSProvider | None = None

    def __init__(self) -> None:

        self._firmware_information: FirmwareInformation | None = None

        self._provider_registry: list[Type[BIOSProvider]] = [
            DellProvider,
            HPProvider,
            LenovoProvider,
            AcerProvider,
            ASUSProvider,
            MSIProvider,
            GigabyteProvider,
            FrameworkProvider,
            GenericUEFIProvider,
        ]

    # ======================================================
    # Public API
    # ======================================================

    def provider(self) -> BIOSProvider:
        """
        Return the active BIOS provider.

        Detection is performed only once.
        """

        if self._provider is not None:
            return self._provider

        firmware = self.firmware_information()

        logger.info(
            "Detected manufacturer: %s",
            firmware.manufacturer,
        )

        logger.info(
            "Detected BIOS vendor: %s",
            firmware.vendor,
        )

        self._provider = self._select_provider(firmware)

        logger.info(
            "Using provider: %s",
            self._provider.__class__.__name__,
        )

        return self._provider

    def firmware_information(
        self,
    ) -> FirmwareInformation:
        """
        Return firmware information.

        The information is cached after the first
        collection.
        """

        if self._firmware_information is not None:
            return self._firmware_information

        self._firmware_information = FirmwareInformation(
            manufacturer=self._manufacturer(),
            vendor=self._vendor(),
            version=self._version(),
            release_date=self._release_date(),
            serial_number=self._serial_number(),
            uuid=self._uuid(),
            model=self._model(),
            bios_mode=self._bios_mode(),
        )

        return self._firmware_information

    # ======================================================
    # Provider Selection
    # ======================================================

    def _select_provider(
        self,
        firmware: FirmwareInformation,
    ) -> BIOSProvider:
        """
        Determine the correct BIOS provider.
        """

        manufacturer = firmware.manufacturer.lower()

        vendor = firmware.vendor.lower()

        for provider_type in self._provider_registry:

            provider = provider_type()

            try:

                if provider.detect():

                    logger.info(
                        "%s detected successfully.",
                        provider.__class__.__name__,
                    )

                    return provider

            except Exception as exc:

                logger.exception(
                    "%s detection failed: %s",
                    provider.__class__.__name__,
                    exc,
                )

        logger.warning(
            "No dedicated provider detected."
        )

        return UnknownProvider()
    # ======================================================
    # Firmware Discovery
    # ======================================================

    def _manufacturer(self) -> str:
        """
        Return the system manufacturer.
        """

        return self._wmic_value(
            alias="computersystem",
            property_name="manufacturer",
        )

    def _model(self) -> str:
        """
        Return the computer model.
        """

        return self._wmic_value(
            alias="computersystem",
            property_name="model",
        )

    def _vendor(self) -> str:
        """
        Return the BIOS vendor.
        """

        return self._wmic_value(
            alias="bios",
            property_name="manufacturer",
        )

    def _version(self) -> str:
        """
        Return the BIOS version.
        """

        return self._wmic_value(
            alias="bios",
            property_name="SMBIOSBIOSVersion",
        )

    def _release_date(self) -> str:
        """
        Return the BIOS release date.
        """

        raw = self._wmic_value(
            alias="bios",
            property_name="ReleaseDate",
        )

        if len(raw) >= 8 and raw[:8].isdigit():

            return (
                f"{raw[0:4]}-"
                f"{raw[4:6]}-"
                f"{raw[6:8]}"
            )

        return raw

    def _serial_number(self) -> str:
        """
        Return the system serial number.
        """

        return self._wmic_value(
            alias="bios",
            property_name="SerialNumber",
        )

    def _uuid(self) -> str:
        """
        Return the hardware UUID.
        """

        return self._wmic_value(
            alias="csproduct",
            property_name="UUID",
        )

    def _bios_mode(self) -> str:
        """
        Return the firmware boot mode.

        Possible values:

            UEFI
            Legacy
            Unknown
        """

        if platform.system() != "Windows":
            return "Unknown"

        try:

            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-ComputerInfo).BiosFirmwareType",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            value = result.stdout.strip()

            if value:

                return value

        except Exception:

            logger.exception(
                "Unable to determine BIOS mode."
            )

        return "Unknown"

    # ======================================================
    # Windows Helpers
    # ======================================================

    def _wmic_value(
        self,
        *,
        alias: str,
        property_name: str,
    ) -> str:
        """
        Execute a WMIC query and return the value.

        If the query fails, PowerShell CIM is used
        as a fallback.
        """

        if platform.system() != "Windows":
            return "Unknown"

        #
        # WMIC
        #

        try:

            result = subprocess.run(
                [
                    "wmic",
                    alias,
                    "get",
                    property_name,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:

                lines = [
                    line.strip()
                    for line in result.stdout.splitlines()
                    if line.strip()
                ]

                if len(lines) >= 2:

                    return lines[1]

        except Exception:

            logger.debug(
                "WMIC lookup failed for %s.%s",
                alias,
                property_name,
            )

        #
        # PowerShell CIM
        #

        return self._powershell_value(
            alias=alias,
            property_name=property_name,
        )

    def _powershell_value(
        self,
        *,
        alias: str,
        property_name: str,
    ) -> str:
        """
        Retrieve information using PowerShell CIM.

        Modern Windows installations no longer ship
        WMIC by default, so CIM is the preferred
        long-term solution.
        """

        class_map = {
            "bios": "Win32_BIOS",
            "computersystem": "Win32_ComputerSystem",
            "csproduct": "Win32_ComputerSystemProduct",
        }

        wmi_class = class_map.get(alias)

        if wmi_class is None:

            return "Unknown"

        command = (
            f"(Get-CimInstance {wmi_class}).{property_name}"
        )

        try:

            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    command,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            value = result.stdout.strip()

            if value:

                return value

        except Exception:

            logger.exception(
                "PowerShell lookup failed."
            )

        return "Unknown"
    # ======================================================
    # Linux Support
    # ======================================================

    def _linux_dmi_value(
        self,
        filename: str,
    ) -> str:
        """
        Read a value from Linux DMI.

        Parameters
        ----------
        filename:
            File contained within
            /sys/class/dmi/id/

        Returns
        -------
        str
            File contents or "Unknown".
        """

        if platform.system() != "Linux":
            return "Unknown"

        try:

            path = f"/sys/class/dmi/id/{filename}"

            with open(
                path,
                "r",
                encoding="utf-8",
            ) as file:

                value = file.read().strip()

                if value:

                    return value

        except Exception:

            logger.debug(
                "Unable to read DMI file: %s",
                filename,
            )

        return "Unknown"

    # ======================================================
    # Provider Registry
    # ======================================================

    def register_provider(
        self,
        provider: Type[BIOSProvider],
    ) -> None:
        """
        Register a provider.

        Providers are checked in the order
        they appear in the registry.
        """

        if provider in self._provider_registry:
            return

        self._provider_registry.append(provider)

        logger.info(
            "Registered provider: %s",
            provider.__name__,
        )

    def unregister_provider(
        self,
        provider: Type[BIOSProvider],
    ) -> None:
        """
        Remove a provider from the registry.
        """

        if provider not in self._provider_registry:
            return

        self._provider_registry.remove(provider)

        logger.info(
            "Removed provider: %s",
            provider.__name__,
        )

    def registered_providers(
        self,
    ) -> tuple[Type[BIOSProvider], ...]:
        """
        Return all registered providers.
        """

        return tuple(self._provider_registry)

    # ======================================================
    # Cache Management
    # ======================================================

    def clear_cache(self) -> None:
        """
        Clear cached firmware information.
        """

        logger.info(
            "Clearing BIOS detection cache."
        )

        self._provider = None

        self._firmware_information = None

    def refresh(self) -> BIOSProvider:
        """
        Force a fresh detection.
        """

        self.clear_cache()

        return self.provider()

    # ======================================================
    # Diagnostics
    # ======================================================

    def diagnostics(self) -> dict[str, str]:
        """
        Return firmware diagnostics.
        """

        firmware = self.firmware_information()

        provider = self.provider()

        return {
            "provider": provider.__class__.__name__,
            "manufacturer": firmware.manufacturer,
            "vendor": firmware.vendor,
            "model": firmware.model,
            "version": firmware.version,
            "release_date": firmware.release_date,
            "serial_number": firmware.serial_number,
            "uuid": firmware.uuid,
            "bios_mode": firmware.bios_mode,
        }

    def to_dict(self) -> dict[str, str]:
        """
        Alias for diagnostics().

        Allows BIOSDetection to be serialized
        consistently with the rest of Orion.
        """

        return self.diagnostics()

    # ======================================================
    # Convenience
    # ======================================================

    @property
    def provider_name(self) -> str:
        """
        Return the active provider name.
        """

        return self.provider().__class__.__name__

    @property
    def vendor_name(self) -> str:
        """
        Return the firmware vendor.
        """

        return self.firmware_information().vendor

    @property
    def manufacturer_name(self) -> str:
        """
        Return the system manufacturer.
        """

        return self.firmware_information().manufacturer

    @property
    def model_name(self) -> str:
        """
        Return the system model.
        """

        return self.firmware_information().model


# ==========================================================
# Module-Level Singleton
# ==========================================================

_detection = BIOSDetection()


def provider() -> BIOSProvider:
    """
    Return the active BIOS provider.

    This is the preferred entry point for the
    rest of Orion.
    """

    return _detection.provider()


def firmware_information() -> FirmwareInformation:
    """
    Return cached firmware information.
    """

    return _detection.firmware_information()


def diagnostics() -> dict[str, str]:
    """
    Return firmware diagnostics.
    """

    return _detection.diagnostics()


def refresh() -> BIOSProvider:
    """
    Force firmware redetection.
    """

    return _detection.refresh()


def register_provider(
    provider_type: Type[BIOSProvider],
) -> None:
    """
    Register a custom provider.
    """

    _detection.register_provider(
        provider_type,
    )


def registered_providers() -> tuple[Type[BIOSProvider], ...]:
    """
    Return all registered providers.
    """

    return _detection.registered_providers()