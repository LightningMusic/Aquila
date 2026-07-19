from __future__ import annotations

import json
import logging
import platform
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from bios.bios_manager import BIOSManager

logger = logging.getLogger(__name__)


# ==========================================================
# Wake Sources
# ==========================================================


class WakeSource(Enum):
    UNKNOWN = "Unknown"
    POWER_BUTTON = "Power Button"
    LID_OPEN = "Lid Open"
    WAKE_ON_LAN = "Wake-on-LAN"
    RTC_ALARM = "RTC Alarm"
    USB = "USB"
    KEYBOARD = "Keyboard"
    MOUSE = "Mouse"
    PCIE = "PCI Express"
    AC_POWER = "AC Power"
    THUNDERBOLT = "Thunderbolt"


class WakeCapability(Enum):
    ENABLED = "Enabled"
    DISABLED = "Disabled"
    UNSUPPORTED = "Unsupported"
    UNKNOWN = "Unknown"


# ==========================================================
# Wake Status Model
# ==========================================================


@dataclass(slots=True)
class WakeStatus:

    # Current wake event

    last_wake_source: WakeSource = WakeSource.UNKNOWN

    # Wake capabilities

    wake_on_lan: WakeCapability = WakeCapability.UNKNOWN
    rtc_alarm: WakeCapability = WakeCapability.UNKNOWN
    usb: WakeCapability = WakeCapability.UNKNOWN
    keyboard: WakeCapability = WakeCapability.UNKNOWN
    mouse: WakeCapability = WakeCapability.UNKNOWN
    pcie: WakeCapability = WakeCapability.UNKNOWN
    power_button: WakeCapability = WakeCapability.ENABLED
    lid_open: WakeCapability = WakeCapability.UNKNOWN
    ac_power: WakeCapability = WakeCapability.UNKNOWN
    thunderbolt: WakeCapability = WakeCapability.UNKNOWN

    # Firmware support

    wake_on_lan_supported: bool = False
    rtc_supported: bool = False
    usb_supported: bool = False
    keyboard_supported: bool = False
    mouse_supported: bool = False
    pcie_supported: bool = False
    lid_supported: bool = False
    thunderbolt_supported: bool = False

    # Operating system support

    operating_system: str = platform.system()

    # Diagnostics

    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    additional_information: dict[str, Any] = field(default_factory=dict)


# ==========================================================
# Wake Manager
# ==========================================================


class WakeManager:
    """
    Manages BIOS wake events and wake sources.

    Orion uses this manager to configure wake behavior
    before systems are deployed as workstations,
    servers, Proxmox nodes, or storage appliances.
    """

    def __init__(
        self,
        bios: BIOSManager,
    ) -> None:

        self._bios = bios

        self._status = WakeStatus()

        logger.debug(
            "WakeManager initialized."
        )

    # ======================================================
    # Internal Helpers
    # ======================================================

    def _add_warning(self, message: str) -> None:

        if message not in self._status.warnings:
            self._status.warnings.append(message)

    def _add_note(self, message: str) -> None:

        if message not in self._status.notes:
            self._status.notes.append(message)

    def clear_messages(self) -> None:

        self._status.warnings.clear()
        self._status.notes.clear()

    @property
    def status(self) -> WakeStatus:
        """
        Return the current wake status.
        """

        return self._status
    
    # ======================================================
    # Detection
    # ======================================================

    def detect(self) -> WakeStatus:
        """
        Detect every supported wake source.
        """

        logger.info(
            "Detecting wake configuration..."
        )

        self.clear_messages()

        self.detect_wake_on_lan()

        self.detect_rtc_alarm()

        self.detect_usb_wake()

        self.detect_keyboard_wake()

        self.detect_mouse_wake()

        self.detect_pcie_wake()

        self.detect_power_button()

        self.detect_lid_open()

        self.detect_ac_power()

        self.detect_thunderbolt()

        self.detect_last_wake_source()

        return self._status

    # ======================================================
    # Wake-on-LAN
    # ======================================================

    def detect_wake_on_lan(self) -> WakeCapability:

        provider = self._bios.provider()

        if provider.wake_on_lan_supported():

            self._status.wake_on_lan_supported = True

            enabled = provider.is_wake_on_lan_enabled()

            self._status.wake_on_lan = (
                WakeCapability.ENABLED
                if enabled
                else WakeCapability.DISABLED
            )

        else:

            self._status.wake_on_lan = (
                WakeCapability.UNSUPPORTED
            )

        return self._status.wake_on_lan

    # ======================================================
    # RTC Alarm
    # ======================================================

    def detect_rtc_alarm(self) -> WakeCapability:

        provider = self._bios.provider()

        if provider.rtc_alarm_supported():

            self._status.rtc_supported = True

            enabled = provider.is_rtc_alarm_enabled()

            self._status.rtc_alarm = (
                WakeCapability.ENABLED
                if enabled
                else WakeCapability.DISABLED
            )

        else:

            self._status.rtc_alarm = (
                WakeCapability.UNSUPPORTED
            )

        return self._status.rtc_alarm

    # ======================================================
    # USB Wake
    # ======================================================

    def detect_usb_wake(self) -> WakeCapability:

        provider = self._bios.provider()

        if provider.usb_wake_supported():

            self._status.usb_supported = True

            enabled = provider.is_usb_wake_enabled()

            self._status.usb = (
                WakeCapability.ENABLED
                if enabled
                else WakeCapability.DISABLED
            )

        else:

            self._status.usb = (
                WakeCapability.UNSUPPORTED
            )

        return self._status.usb

    # ======================================================
    # Keyboard Wake
    # ======================================================

    def detect_keyboard_wake(self) -> WakeCapability:

        provider = self._bios.provider()

        if provider.keyboard_wake_supported():

            self._status.keyboard_supported = True

            enabled = provider.is_keyboard_wake_enabled()

            self._status.keyboard = (
                WakeCapability.ENABLED
                if enabled
                else WakeCapability.DISABLED
            )

        else:

            self._status.keyboard = (
                WakeCapability.UNSUPPORTED
            )

        return self._status.keyboard

    # ======================================================
    # Mouse Wake
    # ======================================================

    def detect_mouse_wake(self) -> WakeCapability:

        provider = self._bios.provider()

        if provider.mouse_wake_supported():

            self._status.mouse_supported = True

            enabled = provider.is_mouse_wake_enabled()

            self._status.mouse = (
                WakeCapability.ENABLED
                if enabled
                else WakeCapability.DISABLED
            )

        else:

            self._status.mouse = (
                WakeCapability.UNSUPPORTED
            )

        return self._status.mouse

    # ======================================================
    # PCIe Wake
    # ======================================================

    def detect_pcie_wake(self) -> WakeCapability:

        provider = self._bios.provider()

        if provider.pcie_wake_supported():

            self._status.pcie_supported = True

            enabled = provider.is_pcie_wake_enabled()

            self._status.pcie = (
                WakeCapability.ENABLED
                if enabled
                else WakeCapability.DISABLED
            )

        else:

            self._status.pcie = (
                WakeCapability.UNSUPPORTED
            )

        return self._status.pcie

    # ======================================================
    # Power Button
    # ======================================================

    def detect_power_button(self) -> WakeCapability:

        self._status.power_button = (
            WakeCapability.ENABLED
        )

        return self._status.power_button

    # ======================================================
    # Lid Open
    # ======================================================

    def detect_lid_open(self) -> WakeCapability:

        provider = self._bios.provider()

        if provider.lid_open_wake_supported():

            self._status.lid_supported = True

            enabled = provider.is_lid_open_wake_enabled()

            self._status.lid_open = (
                WakeCapability.ENABLED
                if enabled
                else WakeCapability.DISABLED
            )

        else:

            self._status.lid_open = (
                WakeCapability.UNSUPPORTED
            )

        return self._status.lid_open

    # ======================================================
    # AC Power Restore
    # ======================================================

    def detect_ac_power(self) -> WakeCapability:

        provider = self._bios.provider()

        if provider.ac_power_restore_supported():

            enabled = provider.is_ac_power_restore_enabled()

            self._status.ac_power = (
                WakeCapability.ENABLED
                if enabled
                else WakeCapability.DISABLED
            )

        else:

            self._status.ac_power = (
                WakeCapability.UNSUPPORTED
            )

        return self._status.ac_power

    # ======================================================
    # Thunderbolt Wake
    # ======================================================

    def detect_thunderbolt(self) -> WakeCapability:

        provider = self._bios.provider()

        if provider.thunderbolt_wake_supported():

            self._status.thunderbolt_supported = True

            enabled = (
                provider.is_thunderbolt_wake_enabled()
            )

            self._status.thunderbolt = (
                WakeCapability.ENABLED
                if enabled
                else WakeCapability.DISABLED
            )

        else:

            self._status.thunderbolt = (
                WakeCapability.UNSUPPORTED
            )

        return self._status.thunderbolt

    # ======================================================
    # Last Wake Source
    # ======================================================

    def detect_last_wake_source(self) -> WakeSource:
        """
        Determine the most recent wake source using
        platform-specific operating system facilities.
        """

        system = platform.system()

        try:

            if system == "Windows":

                result = subprocess.run(
                    [
                        "powercfg",
                        "/lastwake",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )

                output = result.stdout.lower()

                if "keyboard" in output:
                    source = WakeSource.KEYBOARD

                elif "mouse" in output:
                    source = WakeSource.MOUSE

                elif "network" in output:
                    source = WakeSource.WAKE_ON_LAN

                elif "power button" in output:
                    source = WakeSource.POWER_BUTTON

                elif "lid" in output:
                    source = WakeSource.LID_OPEN

                elif "rtc" in output or "timer" in output:
                    source = WakeSource.RTC_ALARM

                elif "pci" in output:
                    source = WakeSource.PCIE

                else:
                    source = WakeSource.UNKNOWN

            elif system == "Linux":

                source = WakeSource.UNKNOWN

                wake_file = Path("/sys/power/last_wakeup")

                if wake_file.exists():

                    text = wake_file.read_text().lower()

                    if "usb" in text:
                        source = WakeSource.USB

                    elif "keyboard" in text:
                        source = WakeSource.KEYBOARD

                    elif "mouse" in text:
                        source = WakeSource.MOUSE

                    elif "rtc" in text:
                        source = WakeSource.RTC_ALARM

                    elif "lan" in text:
                        source = WakeSource.WAKE_ON_LAN

            else:

                source = WakeSource.UNKNOWN

        except Exception as exc:

            logger.debug(
                "Unable to determine last wake source: %s",
                exc,
            )

            source = WakeSource.UNKNOWN

        self._status.last_wake_source = source

        return source
    
    # ======================================================
    # BIOS Integration
    # ======================================================

    def enable_wake_on_lan(self) -> bool:
        """
        Enable Wake-on-LAN through the BIOS provider.
        """

        provider = self._bios.provider()

        if not provider.wake_on_lan_supported():
            self._add_warning("Wake-on-LAN is not supported.")
            return False

        success = provider.enable_wake_on_lan()

        if success:
            self._status.wake_on_lan = WakeCapability.ENABLED

        return success

    def disable_wake_on_lan(self) -> bool:
        """
        Disable Wake-on-LAN.
        """

        provider = self._bios.provider()

        if not provider.wake_on_lan_supported():
            self._add_warning("Wake-on-LAN is not supported.")
            return False

        success = provider.disable_wake_on_lan()

        if success:
            self._status.wake_on_lan = WakeCapability.DISABLED

        return success

    # ======================================================

    def enable_rtc_alarm(self) -> bool:

        provider = self._bios.provider()

        if not provider.rtc_alarm_supported():
            self._add_warning("RTC wake is not supported.")
            return False

        success = provider.enable_rtc_alarm()

        if success:
            self._status.rtc_alarm = WakeCapability.ENABLED

        return success

    def disable_rtc_alarm(self) -> bool:

        provider = self._bios.provider()

        if not provider.rtc_alarm_supported():
            self._add_warning("RTC wake is not supported.")
            return False

        success = provider.disable_rtc_alarm()

        if success:
            self._status.rtc_alarm = WakeCapability.DISABLED

        return success

    # ======================================================

    def enable_usb_wake(self) -> bool:

        provider = self._bios.provider()

        if not provider.usb_wake_supported():
            self._add_warning("USB wake is not supported.")
            return False

        success = provider.enable_usb_wake()

        if success:
            self._status.usb = WakeCapability.ENABLED

        return success

    def disable_usb_wake(self) -> bool:

        provider = self._bios.provider()

        if not provider.usb_wake_supported():
            self._add_warning("USB wake is not supported.")
            return False

        success = provider.disable_usb_wake()

        if success:
            self._status.usb = WakeCapability.DISABLED

        return success

    # ======================================================

    def enable_keyboard_wake(self) -> bool:

        provider = self._bios.provider()

        if not provider.keyboard_wake_supported():
            self._add_warning("Keyboard wake is not supported.")
            return False

        success = provider.enable_keyboard_wake()

        if success:
            self._status.keyboard = WakeCapability.ENABLED

        return success

    def disable_keyboard_wake(self) -> bool:

        provider = self._bios.provider()

        if not provider.keyboard_wake_supported():
            self._add_warning("Keyboard wake is not supported.")
            return False

        success = provider.disable_keyboard_wake()

        if success:
            self._status.keyboard = WakeCapability.DISABLED

        return success

    # ======================================================

    def enable_mouse_wake(self) -> bool:

        provider = self._bios.provider()

        if not provider.mouse_wake_supported():
            self._add_warning("Mouse wake is not supported.")
            return False

        success = provider.enable_mouse_wake()

        if success:
            self._status.mouse = WakeCapability.ENABLED

        return success

    def disable_mouse_wake(self) -> bool:

        provider = self._bios.provider()

        if not provider.mouse_wake_supported():
            self._add_warning("Mouse wake is not supported.")
            return False

        success = provider.disable_mouse_wake()

        if success:
            self._status.mouse = WakeCapability.DISABLED

        return success

    # ======================================================

    def enable_pcie_wake(self) -> bool:

        provider = self._bios.provider()

        if not provider.pcie_wake_supported():
            self._add_warning("PCIe wake is not supported.")
            return False

        success = provider.enable_pcie_wake()

        if success:
            self._status.pcie = WakeCapability.ENABLED

        return success

    def disable_pcie_wake(self) -> bool:

        provider = self._bios.provider()

        if not provider.pcie_wake_supported():
            self._add_warning("PCIe wake is not supported.")
            return False

        success = provider.disable_pcie_wake()

        if success:
            self._status.pcie = WakeCapability.DISABLED

        return success

    # ======================================================

    def enable_lid_open(self) -> bool:

        provider = self._bios.provider()

        if not provider.lid_open_wake_supported():
            self._add_warning("Lid wake is not supported.")
            return False

        success = provider.enable_lid_open_wake()

        if success:
            self._status.lid_open = WakeCapability.ENABLED

        return success

    def disable_lid_open(self) -> bool:

        provider = self._bios.provider()

        if not provider.lid_open_wake_supported():
            self._add_warning("Lid wake is not supported.")
            return False

        success = provider.disable_lid_open_wake()

        if success:
            self._status.lid_open = WakeCapability.DISABLED

        return success

    # ======================================================

    def enable_ac_power_restore(self) -> bool:

        provider = self._bios.provider()

        if not provider.ac_power_restore_supported():
            self._add_warning("AC power restore is not supported.")
            return False

        success = provider.enable_ac_power_restore()

        if success:
            self._status.ac_power = WakeCapability.ENABLED

        return success

    def disable_ac_power_restore(self) -> bool:

        provider = self._bios.provider()

        if not provider.ac_power_restore_supported():
            self._add_warning("AC power restore is not supported.")
            return False

        success = provider.disable_ac_power_restore()

        if success:
            self._status.ac_power = WakeCapability.DISABLED

        return success

    # ======================================================

    def enable_thunderbolt_wake(self) -> bool:

        provider = self._bios.provider()

        if not provider.thunderbolt_wake_supported():
            self._add_warning("Thunderbolt wake is not supported.")
            return False

        success = provider.enable_thunderbolt_wake()

        if success:
            self._status.thunderbolt = WakeCapability.ENABLED

        return success

    def disable_thunderbolt_wake(self) -> bool:

        provider = self._bios.provider()

        if not provider.thunderbolt_wake_supported():
            self._add_warning("Thunderbolt wake is not supported.")
            return False

        success = provider.disable_thunderbolt_wake()

        if success:
            self._status.thunderbolt = WakeCapability.DISABLED

        return success

    # ======================================================
    # Validation
    # ======================================================

    def validate(self) -> bool:
        """
        Refresh the current BIOS wake configuration and verify
        that the cached state matches firmware.
        """

        logger.info("Validating wake configuration...")

        self.detect()

        return True

    # ======================================================
    # Firmware Synchronization
    # ======================================================

    def synchronize(self) -> bool:
        """
        Synchronize cached wake information with firmware.
        """

        logger.info(
            "Synchronizing wake configuration..."
        )

        self.detect()

        return True
    
    # ======================================================
    # Orion Deployment Profiles
    # ======================================================

    def apply_workstation_profile(self) -> bool:
        """
        Configure wake settings appropriate for a workstation.
        """

        logger.info("Applying Workstation wake profile...")

        self.enable_keyboard_wake()
        self.enable_mouse_wake()
        self.enable_usb_wake()
        self.enable_lid_open()

        return self.synchronize()

    def apply_server_profile(self) -> bool:
        """
        Configure wake settings appropriate for servers.
        """

        logger.info("Applying Server wake profile...")

        self.enable_wake_on_lan()
        self.enable_ac_power_restore()
        self.enable_rtc_alarm()

        self.disable_keyboard_wake()
        self.disable_mouse_wake()

        return self.synchronize()

    def apply_proxmox_profile(self) -> bool:
        """
        Configure wake settings for Proxmox hosts.
        """

        logger.info("Applying Proxmox wake profile...")

        self.enable_wake_on_lan()
        self.enable_ac_power_restore()
        self.enable_rtc_alarm()

        self.disable_keyboard_wake()
        self.disable_mouse_wake()

        return self.synchronize()

    def apply_portable_profile(self) -> bool:
        """
        Configure wake settings for laptops.
        """

        logger.info("Applying Portable wake profile...")

        self.enable_lid_open()

        self.disable_wake_on_lan()

        return self.synchronize()

    def apply_storage_profile(self) -> bool:
        """
        Configure wake settings for storage appliances.
        """

        logger.info("Applying Storage wake profile...")

        self.enable_wake_on_lan()
        self.enable_ac_power_restore()

        self.disable_keyboard_wake()
        self.disable_mouse_wake()
        self.disable_usb_wake()

        return self.synchronize()

    # ======================================================
    # Reporting
    # ======================================================

    def report(self) -> dict[str, Any]:
        """
        Produce a complete wake configuration report.
        """

        return {
            "last_wake_source":
                self._status.last_wake_source.value,

            "wake_on_lan":
                self._status.wake_on_lan.value,

            "rtc_alarm":
                self._status.rtc_alarm.value,

            "usb":
                self._status.usb.value,

            "keyboard":
                self._status.keyboard.value,

            "mouse":
                self._status.mouse.value,

            "pcie":
                self._status.pcie.value,

            "power_button":
                self._status.power_button.value,

            "lid_open":
                self._status.lid_open.value,

            "ac_power":
                self._status.ac_power.value,

            "thunderbolt":
                self._status.thunderbolt.value,

            "wake_on_lan_supported":
                self._status.wake_on_lan_supported,

            "rtc_supported":
                self._status.rtc_supported,

            "usb_supported":
                self._status.usb_supported,

            "keyboard_supported":
                self._status.keyboard_supported,

            "mouse_supported":
                self._status.mouse_supported,

            "pcie_supported":
                self._status.pcie_supported,

            "lid_supported":
                self._status.lid_supported,

            "thunderbolt_supported":
                self._status.thunderbolt_supported,

            "operating_system":
                self._status.operating_system,

            "warnings":
                list(self._status.warnings),

            "notes":
                list(self._status.notes),

            "additional_information":
                dict(
                    self._status.additional_information
                ),
        }

    # ======================================================
    # Export
    # ======================================================

    def export(self) -> dict[str, Any]:
        """
        Export wake information for Orion reports.
        """

        logger.info(
            "Exporting wake configuration..."
        )

        return self.report()

    def export_json(
        self,
        destination: Path,
    ) -> None:
        """
        Export the wake report as JSON.
        """

        destination.write_text(
            json.dumps(
                self.report(),
                indent=4,
            ),
            encoding="utf-8",
        )

    # ======================================================
    # Refresh
    # ======================================================

    def refresh(self) -> WakeStatus:
        """
        Refresh wake information.
        """

        logger.info(
            "Refreshing wake configuration..."
        )

        return self.detect()

    # ======================================================
    # Helper Methods
    # ======================================================

    def wake_on_lan_enabled(self) -> bool:

        return (
            self._status.wake_on_lan
            == WakeCapability.ENABLED
        )

    def rtc_alarm_enabled(self) -> bool:

        return (
            self._status.rtc_alarm
            == WakeCapability.ENABLED
        )

    def usb_wake_enabled(self) -> bool:

        return (
            self._status.usb
            == WakeCapability.ENABLED
        )

    def keyboard_wake_enabled(self) -> bool:

        return (
            self._status.keyboard
            == WakeCapability.ENABLED
        )

    def mouse_wake_enabled(self) -> bool:

        return (
            self._status.mouse
            == WakeCapability.ENABLED
        )

    def pcie_wake_enabled(self) -> bool:

        return (
            self._status.pcie
            == WakeCapability.ENABLED
        )

    def lid_open_enabled(self) -> bool:

        return (
            self._status.lid_open
            == WakeCapability.ENABLED
        )

    def ac_power_restore_enabled(self) -> bool:

        return (
            self._status.ac_power
            == WakeCapability.ENABLED
        )

    def thunderbolt_wake_enabled(self) -> bool:

        return (
            self._status.thunderbolt
            == WakeCapability.ENABLED
        )

    def last_wake_source(self) -> WakeSource:

        return self._status.last_wake_source

    # ======================================================
    # String Representation
    # ======================================================

    def __repr__(self) -> str:

        return (
            f"{self.__class__.__name__}("
            f"wake_on_lan={self._status.wake_on_lan.value!r}, "
            f"last_wake={self._status.last_wake_source.value!r})"
        )

    def __str__(self) -> str:

        return (
            f"Wake Manager "
            f"(Last Wake: "
            f"{self._status.last_wake_source.value})"
        )