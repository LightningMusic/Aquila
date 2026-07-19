"""
Project Orion
=============

Power Management

Provides operating system power configuration for Orion.

Unlike BIOSManager, which controls firmware settings,
PowerManager configures the operating system after it
boots.

Supported Platforms
-------------------
• Windows
• Linux

Responsibilities
----------------
• Power plans
• Sleep / Hibernate
• Lid switch behavior
• CPU power policy
• USB selective suspend
• PCIe power management
• Network adapter power
• Deployment profiles
"""

from __future__ import annotations

import logging
import platform
import subprocess

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from bios.battery import BatteryManager
from bios.bios_manager import BIOSManager

logger = logging.getLogger(__name__)


# ==========================================================
# Enumerations
# ==========================================================

class OperatingSystem(Enum):
    WINDOWS = "windows"
    LINUX = "linux"
    UNKNOWN = "unknown"


class PowerProfile(Enum):
    BALANCED = "balanced"
    HIGH_PERFORMANCE = "high_performance"
    POWER_SAVER = "power_saver"

    ORION_DEPLOYMENT = "orion_deployment"
    ORION_SERVER = "orion_server"
    ORION_PORTABLE = "orion_portable"
    ORION_STORAGE = "orion_storage"


class LidAction(Enum):
    DO_NOTHING = "do_nothing"
    SLEEP = "sleep"
    HIBERNATE = "hibernate"
    SHUTDOWN = "shutdown"


class SleepState(Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"


# ==========================================================
# Power Configuration
# ==========================================================

@dataclass(slots=True)
class PowerConfiguration:
    """
    Represents the current operating-system power policy.
    """

    operating_system: OperatingSystem

    profile: PowerProfile = PowerProfile.BALANCED

    sleep: SleepState = SleepState.ENABLED

    hibernate_enabled: bool = True

    lid_action_ac: LidAction = LidAction.SLEEP
    lid_action_battery: LidAction = LidAction.SLEEP

    display_timeout_ac: int = 30
    display_timeout_battery: int = 10

    sleep_timeout_ac: int = 30
    sleep_timeout_battery: int = 15

    cpu_minimum_percent: int = 5
    cpu_maximum_percent: int = 100

    usb_selective_suspend: bool = True

    pcie_link_state_management: bool = True

    wake_on_lan: bool = False

    fast_startup: bool = True

    additional_settings: dict[str, Any] = field(
        default_factory=dict
    )


# ==========================================================
# Power Manager
# ==========================================================

class PowerManager:
    """
    Controls operating-system power configuration.

    BIOSManager
        ↓
    Firmware

    BatteryManager
        ↓
    Battery Health

    PowerManager
        ↓
    Operating System
    """

    def __init__(
        self,
        bios_manager: BIOSManager,
        battery_manager: BatteryManager,
    ) -> None:

        self._bios = bios_manager

        self._battery = battery_manager

        self._configuration = PowerConfiguration(
            operating_system=self._detect_os(),
        )

        logger.info(
            "Power Manager initialized."
        )

    # ======================================================
    # Initialization
    # ======================================================

    def initialize(self) -> bool:
        """
        Detect the current operating-system power
        configuration.
        """

        logger.info(
            "Initializing power manager..."
        )

        if (
            self._configuration.operating_system
            == OperatingSystem.WINDOWS
        ):

            return self._initialize_windows()

        if (
            self._configuration.operating_system
            == OperatingSystem.LINUX
        ):

            return self._initialize_linux()

        logger.warning(
            "Unsupported operating system."
        )

        return False

    # ======================================================
    # Helpers
    # ======================================================

    def _detect_os(self) -> OperatingSystem:

        system = platform.system().lower()

        if system == "windows":
            return OperatingSystem.WINDOWS

        if system == "linux":
            return OperatingSystem.LINUX

        return OperatingSystem.UNKNOWN

    @property
    def configuration(self) -> PowerConfiguration:

        return self._configuration

    @property
    def bios(self) -> BIOSManager:

        return self._bios

    @property
    def battery(self) -> BatteryManager:

        return self._battery
    
    # ======================================================
    # Windows Initialization
    # ======================================================

    def _initialize_windows(self) -> bool:
        """
        Detect the active Windows power configuration.
        """

        logger.info(
            "Detecting Windows power configuration..."
        )

        try:

            result = subprocess.run(
                [
                    "powercfg",
                    "/GETACTIVESCHEME",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            output = result.stdout.lower()

            if "high performance" in output:

                self._configuration.profile = (
                    PowerProfile.HIGH_PERFORMANCE
                )

            elif "power saver" in output:

                self._configuration.profile = (
                    PowerProfile.POWER_SAVER
                )

            else:

                self._configuration.profile = (
                    PowerProfile.BALANCED
                )

        except Exception:

            logger.exception(
                "Unable to detect Windows power plan."
            )

            return False

        logger.info(
            "Detected power profile: %s",
            self._configuration.profile.value,
        )

        return True

    # ======================================================
    # Linux Initialization
    # ======================================================

    def _initialize_linux(self) -> bool:
        """
        Detect Linux power configuration.
        """

        logger.info(
            "Detecting Linux power configuration..."
        )

        governor = Path(
            "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
        )

        if governor.exists():

            try:

                value = governor.read_text().strip()

                if value == "performance":

                    self._configuration.profile = (
                        PowerProfile.HIGH_PERFORMANCE
                    )

                elif value == "powersave":

                    self._configuration.profile = (
                        PowerProfile.POWER_SAVER
                    )

                else:

                    self._configuration.profile = (
                        PowerProfile.BALANCED
                    )

            except Exception:

                logger.exception(
                    "Unable to read CPU governor."
                )

        logger.info(
            "Detected power profile: %s",
            self._configuration.profile.value,
        )

        return True

    # ======================================================
    # Sleep Management
    # ======================================================

    def enable_sleep(self) -> bool:
        """
        Enables sleep.
        """

        logger.info(
            "Enabling sleep..."
        )

        self._configuration.sleep = (
            SleepState.ENABLED
        )

        if (
            self._configuration.operating_system
            == OperatingSystem.WINDOWS
        ):

            subprocess.run(
                [
                    "powercfg",
                    "/CHANGE",
                    "standby-timeout-ac",
                    "30",
                ],
                check=False,
            )

            subprocess.run(
                [
                    "powercfg",
                    "/CHANGE",
                    "standby-timeout-dc",
                    "15",
                ],
                check=False,
            )

        return True

    def disable_sleep(self) -> bool:
        """
        Disables sleep.
        """

        logger.info(
            "Disabling sleep..."
        )

        self._configuration.sleep = (
            SleepState.DISABLED
        )

        if (
            self._configuration.operating_system
            == OperatingSystem.WINDOWS
        ):

            subprocess.run(
                [
                    "powercfg",
                    "/CHANGE",
                    "standby-timeout-ac",
                    "0",
                ],
                check=False,
            )

            subprocess.run(
                [
                    "powercfg",
                    "/CHANGE",
                    "standby-timeout-dc",
                    "0",
                ],
                check=False,
            )

        return True

    # ======================================================
    # Hibernate
    # ======================================================

    def enable_hibernate(self) -> bool:

        logger.info(
            "Enabling hibernate..."
        )

        self._configuration.hibernate_enabled = True

        if (
            self._configuration.operating_system
            == OperatingSystem.WINDOWS
        ):

            subprocess.run(
                [
                    "powercfg",
                    "/hibernate",
                    "on",
                ],
                check=False,
            )

        return True

    def disable_hibernate(self) -> bool:

        logger.info(
            "Disabling hibernate..."
        )

        self._configuration.hibernate_enabled = False

        if (
            self._configuration.operating_system
            == OperatingSystem.WINDOWS
        ):

            subprocess.run(
                [
                    "powercfg",
                    "/hibernate",
                    "off",
                ],
                check=False,
            )

        return True

    # ======================================================
    # Lid Switch
    # ======================================================

    def set_lid_action(
        self,
        action: LidAction,
    ) -> bool:
        """
        Sets the default lid behavior.

        Windows implementation uses powercfg.

        Linux implementation is deferred to
        systemd-logind configuration.
        """

        logger.info(
            "Setting lid action to %s",
            action.value,
        )

        self._configuration.lid_action_ac = action
        self._configuration.lid_action_battery = action

        if (
            self._configuration.operating_system
            == OperatingSystem.WINDOWS
        ):

            action_map = {
                LidAction.DO_NOTHING: "0",
                LidAction.SLEEP: "1",
                LidAction.HIBERNATE: "2",
                LidAction.SHUTDOWN: "3",
            }

            value = action_map[action]

            subprocess.run(
                [
                    "powercfg",
                    "/SETACVALUEINDEX",
                    "SCHEME_CURRENT",
                    "SUB_BUTTONS",
                    "LIDACTION",
                    value,
                ],
                check=False,
            )

            subprocess.run(
                [
                    "powercfg",
                    "/SETDCVALUEINDEX",
                    "SCHEME_CURRENT",
                    "SUB_BUTTONS",
                    "LIDACTION",
                    value,
                ],
                check=False,
            )

        return True

    def lid_action(self) -> LidAction:

        return self._configuration.lid_action_ac
    
    # ======================================================
    # CPU Power Management
    # ======================================================

    def set_cpu_power_limits(
        self,
        minimum_percent: int,
        maximum_percent: int,
    ) -> bool:
        """
        Configure CPU minimum and maximum processor state.

        Windows:
            Uses powercfg processor power management.

        Linux:
            Records desired values. CPU governors are managed
            separately through set_cpu_governor().
        """

        minimum_percent = max(0, min(100, minimum_percent))
        maximum_percent = max(minimum_percent, min(100, maximum_percent))

        logger.info(
            "Setting CPU limits: %d%% - %d%%",
            minimum_percent,
            maximum_percent,
        )

        self._configuration.cpu_minimum_percent = minimum_percent
        self._configuration.cpu_maximum_percent = maximum_percent

        if (
            self._configuration.operating_system
            == OperatingSystem.WINDOWS
        ):

            subprocess.run(
                [
                    "powercfg",
                    "/SETACVALUEINDEX",
                    "SCHEME_CURRENT",
                    "SUB_PROCESSOR",
                    "PROCTHROTTLEMIN",
                    str(minimum_percent),
                ],
                check=False,
            )

            subprocess.run(
                [
                    "powercfg",
                    "/SETACVALUEINDEX",
                    "SCHEME_CURRENT",
                    "SUB_PROCESSOR",
                    "PROCTHROTTLEMAX",
                    str(maximum_percent),
                ],
                check=False,
            )

        return True

    def set_cpu_governor(
        self,
        governor: str,
    ) -> bool:
        """
        Linux CPU governor.

        Common governors:

            performance
            powersave
            ondemand
            conservative
            schedutil
        """

        logger.info(
            "Setting CPU governor to %s",
            governor,
        )

        if (
            self._configuration.operating_system
            != OperatingSystem.LINUX
        ):
            return True

        governor_root = Path(
            "/sys/devices/system/cpu"
        )

        try:

            for cpu in governor_root.glob("cpu[0-9]*"):

                governor_file = (
                    cpu
                    / "cpufreq"
                    / "scaling_governor"
                )

                if governor_file.exists():

                    governor_file.write_text(governor)

            return True

        except Exception:

            logger.exception(
                "Unable to set CPU governor."
            )

            return False

    # ======================================================
    # PCI Express Power Management
    # ======================================================

    def enable_pcie_power_management(self) -> bool:
        """
        Enable PCIe Link State Power Management.
        """

        logger.info(
            "Enabling PCIe power management."
        )

        self._configuration.pcie_link_state_management = True

        if (
            self._configuration.operating_system
            == OperatingSystem.WINDOWS
        ):

            subprocess.run(
                [
                    "powercfg",
                    "/SETACVALUEINDEX",
                    "SCHEME_CURRENT",
                    "SUB_PCIEXPRESS",
                    "ASPM",
                    "1",
                ],
                check=False,
            )

        return True

    def disable_pcie_power_management(self) -> bool:
        """
        Disable PCIe Link State Power Management.
        """

        logger.info(
            "Disabling PCIe power management."
        )

        self._configuration.pcie_link_state_management = False

        if (
            self._configuration.operating_system
            == OperatingSystem.WINDOWS
        ):

            subprocess.run(
                [
                    "powercfg",
                    "/SETACVALUEINDEX",
                    "SCHEME_CURRENT",
                    "SUB_PCIEXPRESS",
                    "ASPM",
                    "0",
                ],
                check=False,
            )

        return True

    # ======================================================
    # USB Selective Suspend
    # ======================================================

    def enable_usb_selective_suspend(self) -> bool:
        """
        Enable USB selective suspend.
        """

        logger.info(
            "Enabling USB selective suspend."
        )

        self._configuration.usb_selective_suspend = True

        if (
            self._configuration.operating_system
            == OperatingSystem.WINDOWS
        ):

            subprocess.run(
                [
                    "powercfg",
                    "/SETACVALUEINDEX",
                    "SCHEME_CURRENT",
                    "SUB_USB",
                    "USBSELECTIVESUSPEND",
                    "1",
                ],
                check=False,
            )

        return True

    def disable_usb_selective_suspend(self) -> bool:
        """
        Disable USB selective suspend.
        """

        logger.info(
            "Disabling USB selective suspend."
        )

        self._configuration.usb_selective_suspend = False

        if (
            self._configuration.operating_system
            == OperatingSystem.WINDOWS
        ):

            subprocess.run(
                [
                    "powercfg",
                    "/SETACVALUEINDEX",
                    "SCHEME_CURRENT",
                    "SUB_USB",
                    "USBSELECTIVESUSPEND",
                    "0",
                ],
                check=False,
            )

        return True

    # ======================================================
    # Network Adapter Power
    # ======================================================

    def enable_wake_on_lan(self) -> bool:
        """
        Enable Wake-on-LAN.

        Firmware support is handled separately through
        BIOSManager when available.
        """

        logger.info(
            "Enabling Wake-on-LAN."
        )

        self._configuration.wake_on_lan = True

        if self._bios.provider.wake_on_lan_supported():

            self._bios.provider.enable_wake_on_lan()

        return True

    def disable_wake_on_lan(self) -> bool:
        """
        Disable Wake-on-LAN.
        """

        logger.info(
            "Disabling Wake-on-LAN."
        )

        self._configuration.wake_on_lan = False

        if self._bios.provider.wake_on_lan_supported():

            self._bios.provider.disable_wake_on_lan()

        return True

    def wake_on_lan_enabled(self) -> bool:
        """
        Returns the cached Wake-on-LAN state.
        """

        return self._configuration.wake_on_lan

    # ======================================================
    # Status Helpers
    # ======================================================

    def cpu_limits(self) -> tuple[int, int]:
        """
        Returns the configured CPU minimum and maximum
        processor percentages.
        """

        return (
            self._configuration.cpu_minimum_percent,
            self._configuration.cpu_maximum_percent,
        )

    def usb_selective_suspend_enabled(self) -> bool:
        """
        Returns True if USB selective suspend is enabled.
        """

        return self._configuration.usb_selective_suspend

    def pcie_power_management_enabled(self) -> bool:
        """
        Returns True if PCIe Link State Power Management
        is enabled.
        """

        return self._configuration.pcie_link_state_management
    
    # ======================================================
    # Orion Deployment Profiles
    # ======================================================

    def apply_deployment_profile(self) -> bool:
        """
        Temporary profile used while Orion is imaging,
        benchmarking, and configuring a machine.
        """

        logger.info(
            "Applying Orion Deployment profile..."
        )

        self._configuration.profile = (
            PowerProfile.ORION_DEPLOYMENT
        )

        self.disable_sleep()
        self.disable_hibernate()

        self.set_lid_action(
            LidAction.DO_NOTHING
        )

        self.set_cpu_power_limits(
            100,
            100,
        )

        self.disable_usb_selective_suspend()
        self.disable_pcie_power_management()

        self.enable_wake_on_lan()

        return True

    def apply_server_profile(self) -> bool:
        """
        Power profile for permanent Proxmox servers.
        """

        logger.info(
            "Applying Orion Server profile..."
        )

        self._configuration.profile = (
            PowerProfile.ORION_SERVER
        )

        self.disable_sleep()
        self.disable_hibernate()

        self.set_lid_action(
            LidAction.DO_NOTHING
        )

        self.set_cpu_power_limits(
            100,
            100,
        )

        self.disable_usb_selective_suspend()
        self.disable_pcie_power_management()

        self.enable_wake_on_lan()

        return True

    def apply_portable_profile(self) -> bool:
        """
        Standard laptop configuration.
        """

        logger.info(
            "Applying Orion Portable profile..."
        )

        self._configuration.profile = (
            PowerProfile.ORION_PORTABLE
        )

        self.enable_sleep()
        self.enable_hibernate()

        self.set_lid_action(
            LidAction.SLEEP
        )

        self.set_cpu_power_limits(
            5,
            100,
        )

        self.enable_usb_selective_suspend()
        self.enable_pcie_power_management()

        self.disable_wake_on_lan()

        return True

    def apply_storage_profile(self) -> bool:
        """
        Long-term storage profile for spare systems.
        """

        logger.info(
            "Applying Orion Storage profile..."
        )

        self._configuration.profile = (
            PowerProfile.ORION_STORAGE
        )

        self.enable_sleep()
        self.enable_hibernate()

        self.set_lid_action(
            LidAction.HIBERNATE
        )

        self.set_cpu_power_limits(
            5,
            25,
        )

        self.enable_usb_selective_suspend()
        self.enable_pcie_power_management()

        self.disable_wake_on_lan()

        return True

    # ======================================================
    # Reporting
    # ======================================================

    def report(self) -> dict[str, Any]:
        """
        Returns a snapshot of the current power
        configuration.
        """

        config = self._configuration

        return {
            "operating_system": config.operating_system.value,
            "profile": config.profile.value,
            "sleep": config.sleep.value,
            "hibernate_enabled": config.hibernate_enabled,
            "lid_action_ac": config.lid_action_ac.value,
            "lid_action_battery": config.lid_action_battery.value,
            "display_timeout_ac": config.display_timeout_ac,
            "display_timeout_battery": config.display_timeout_battery,
            "sleep_timeout_ac": config.sleep_timeout_ac,
            "sleep_timeout_battery": config.sleep_timeout_battery,
            "cpu_minimum_percent": config.cpu_minimum_percent,
            "cpu_maximum_percent": config.cpu_maximum_percent,
            "usb_selective_suspend": config.usb_selective_suspend,
            "pcie_link_state_management": config.pcie_link_state_management,
            "wake_on_lan": config.wake_on_lan,
            "fast_startup": config.fast_startup,
            "additional_settings": dict(
                config.additional_settings
            ),
        }

    def export(self) -> dict[str, Any]:
        """
        Export the current configuration.

        Used by Orion reporting and deployment logs.
        """

        logger.info(
            "Exporting power configuration..."
        )

        return self.report()

    # ======================================================
    # Refresh / Reset
    # ======================================================

    def refresh(self) -> bool:
        """
        Re-read the operating system configuration.
        """

        logger.info(
            "Refreshing power configuration..."
        )

        return self.initialize()

    def reset(self) -> None:
        """
        Reset cached configuration to defaults.
        """

        logger.info(
            "Resetting power manager..."
        )

        self._configuration = PowerConfiguration(
            operating_system=self._detect_os(),
        )

    # ======================================================
    # Helper Methods
    # ======================================================

    def profile(self) -> PowerProfile:
        """
        Returns the active Orion power profile.
        """

        return self._configuration.profile

    def profile_name(self) -> str:
        """
        Returns the profile name.
        """

        return self._configuration.profile.value

    def sleep_enabled(self) -> bool:
        """
        Returns True if sleep is enabled.
        """

        return (
            self._configuration.sleep
            == SleepState.ENABLED
        )

    def hibernate_enabled(self) -> bool:
        """
        Returns True if hibernation is enabled.
        """

        return self._configuration.hibernate_enabled

    def is_server_profile(self) -> bool:

        return (
            self._configuration.profile
            == PowerProfile.ORION_SERVER
        )

    def is_portable_profile(self) -> bool:

        return (
            self._configuration.profile
            == PowerProfile.ORION_PORTABLE
        )

    def is_storage_profile(self) -> bool:

        return (
            self._configuration.profile
            == PowerProfile.ORION_STORAGE
        )

    def is_deployment_profile(self) -> bool:

        return (
            self._configuration.profile
            == PowerProfile.ORION_DEPLOYMENT
        )

    # ======================================================
    # String Representation
    # ======================================================

    def __repr__(self) -> str:

        return (
            f"{self.__class__.__name__}("
            f"profile={self.profile_name()!r}, "
            f"os={self._configuration.operating_system.value!r})"
        )

    def __str__(self) -> str:

        return (
            f"{self.profile_name()} "
            f"({self._configuration.operating_system.value})"
        )