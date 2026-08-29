"""
Project Aquila
=============

BIOS Detection

Automatically detects the firmware vendor and selects
the correct BIOS provider implementation.

This module is the entry point for every BIOS operation
performed by Aquila. The rest of the application should
never instantiate vendor providers directly. Instead,
it requests the active provider through BIOSDetection.

Rewrite notes (current provider architecture)
----------------------------------------------
Earlier revisions of this module built firmware identity itself, through
fragile WMIC/PowerShell-CIM string scraping (modern Windows installations
no longer ship WMIC by default) and a legacy, now-unused
``bios.firmware.FirmwareInformation`` model, entirely independent of the
providers it was selecting. Every current-generation provider
(``bios.providers.*``) already collects its own firmware identity through
real, tested mechanisms (WMI on Windows, SMBIOS sysfs on Linux) as part of
``connect()``/``refresh()``. Detection therefore now does exactly one
thing: ask each registered provider, in priority order, whether it
recognizes the system, connect to the first one that does, and expose its
already-collected ``bios.models.FirmwareInformation`` -- rather than
duplicating that collection work through a second, less reliable path.

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
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from typing import Type

from bios.models import FirmwareInformation

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
    running instance of Aquila.
    """

    def __init__(self) -> None:

        self._provider: BIOSProvider | None = None

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
        Return the active, connected BIOS provider.

        Detection is performed only once; call :meth:`refresh` to force a
        fresh detection pass.
        """

        if self._provider is not None:
            return self._provider

        self._provider = self._select_provider()

        firmware = self._provider.firmware_information()

        logger.info(
            "Detected manufacturer: %s",
            firmware.manufacturer or "Unknown",
        )
        logger.info(
            "Detected BIOS vendor: %s",
            firmware.vendor.value,
        )
        logger.info(
            "Using provider: %s (%s)",
            self._provider.provider_name(),
            type(self._provider).__name__,
        )

        return self._provider

    def firmware_information(self) -> FirmwareInformation:
        """
        Return the active provider's firmware information.

        The information is collected once, when the provider connects, and
        cached by the provider itself; call :meth:`refresh` to force a
        fresh detection and collection pass.
        """

        return self.provider().firmware_information()

    # ======================================================
    # Provider Selection
    # ======================================================

    def _select_provider(self) -> BIOSProvider:
        """
        Determine and connect to the correct BIOS provider.

        Each registered provider is asked, in priority order, whether it
        recognizes this system. The first provider that both recognizes
        the system and connects successfully is used. If every registered
        provider fails to match, or a matching provider cannot connect,
        Aquila falls back to :class:`UnknownProvider`, the maximally
        conservative last resort.
        """

        for provider_type in self._provider_registry:

            provider = provider_type()

            try:

                if not provider.detect():
                    continue

                logger.info(
                    "%s detected successfully.",
                    type(provider).__name__,
                )

                if provider.connect():
                    return provider

                logger.warning(
                    "%s matched detection but failed to connect: %s",
                    type(provider).__name__,
                    provider.last_error(),
                )

            except Exception as exc:

                logger.exception(
                    "%s detection failed: %s",
                    type(provider).__name__,
                    exc,
                )

        logger.warning(
            "No dedicated provider detected; falling back to UnknownProvider."
        )

        fallback = UnknownProvider()
        fallback.connect()
        return fallback

    # ======================================================
    # Provider Registry
    # ======================================================

    def register_provider(
        self,
        provider: Type[BIOSProvider],
    ) -> None:
        """
        Register a custom provider.

        Providers are checked in the order they appear in the registry, so
        a provider that must take priority over a built-in vendor provider
        should be inserted, not appended, by the caller before use.
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
        Clear the cached provider selection.
        """

        logger.info(
            "Clearing BIOS detection cache."
        )

        if self._provider is not None:
            try:
                self._provider.disconnect()
            except Exception:
                logger.debug(
                    "Error disconnecting previous provider during cache clear.",
                    exc_info=True,
                )

        self._provider = None

    def refresh(self) -> BIOSProvider:
        """
        Force a fresh detection and connection pass.
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

        release_date = (
            firmware.bios_release_date.isoformat()
            if firmware.bios_release_date is not None
            else ""
        )

        return {
            "provider": provider.provider_name(),
            "provider_class": type(provider).__name__,
            "manufacturer": firmware.manufacturer,
            "vendor": firmware.vendor.value,
            "model": firmware.model,
            "version": firmware.bios_version,
            "release_date": release_date,
            "serial_number": firmware.serial_number,
            "uuid": firmware.system_uuid,
            "bios_mode": provider.bios_mode().value,
        }

    def to_dict(self) -> dict[str, str]:
        """
        Alias for diagnostics().

        Allows BIOSDetection to be serialized
        consistently with the rest of Aquila.
        """

        return self.diagnostics()

    # ======================================================
    # Convenience
    # ======================================================

    @property
    def provider_name(self) -> str:
        """
        Return the active provider's class name.
        """

        return type(self.provider()).__name__

    @property
    def vendor_name(self) -> str:
        """
        Return the firmware vendor.
        """

        return self.firmware_information().vendor.value

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
    rest of Aquila.
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
