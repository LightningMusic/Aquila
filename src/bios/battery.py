"""
Project Orion
=============

BIOS Battery Manager

Provides battery- and power-related firmware
configuration for Project Orion.

This module is responsible for querying and
configuring BIOS/UEFI battery settings where
supported by the system firmware.

NOTE:
Actual capabilities depend on the hardware vendor.
Many consumer systems expose little or no programmatic
firmware configuration.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class BatteryConfiguration:
    """
    Represents firmware battery settings.
    """

    ac_power_recovery: bool = False
    battery_charge_limit: int | None = None
    battery_health_mode: bool = False
    adaptive_charging: bool = False
    peak_shift_enabled: bool = False
    wake_on_ac: bool = False


class BIOSBatteryManager:
    """
    Manages battery-related BIOS/UEFI settings.
    """

    def __init__(self) -> None:
        self._configuration = BatteryConfiguration()

    # ---------------------------------------------------------
    # Discovery
    # ---------------------------------------------------------

    def detect(self) -> BatteryConfiguration:
        """
        Detect current firmware battery settings.

        Returns:
            BatteryConfiguration
        """

        #
        # Vendor-specific implementation will be added
        # in future versions.
        #

        return self._configuration

    # ---------------------------------------------------------
    # Configuration
    # ---------------------------------------------------------

    def configure(
        self,
        configuration: BatteryConfiguration,
    ) -> None:
        """
        Apply battery firmware configuration.

        Currently a placeholder.
        """

        self._configuration = configuration

    # ---------------------------------------------------------
    # Individual Settings
    # ---------------------------------------------------------

    def enable_wake_on_ac(self) -> None:
        """
        Enable automatic boot when AC power is connected.
        """

        self._configuration.wake_on_ac = True

    def disable_wake_on_ac(self) -> None:
        """
        Disable Wake-on-AC.
        """

        self._configuration.wake_on_ac = False

    def enable_health_mode(self) -> None:
        """
        Enable battery health mode.
        """

        self._configuration.battery_health_mode = True

    def disable_health_mode(self) -> None:
        """
        Disable battery health mode.
        """

        self._configuration.battery_health_mode = False

    def set_charge_limit(
        self,
        percent: int,
    ) -> None:
        """
        Configure maximum battery charge percentage.

        Raises:
            ValueError
                If percent is outside 50–100.
        """

        if not 50 <= percent <= 100:
            raise ValueError(
                "Charge limit must be between 50 and 100."
            )

        self._configuration.battery_charge_limit = percent

    def enable_peak_shift(self) -> None:
        """
        Enable Peak Shift if supported.
        """

        self._configuration.peak_shift_enabled = True

    def disable_peak_shift(self) -> None:
        """
        Disable Peak Shift.
        """

        self._configuration.peak_shift_enabled = False

    # ---------------------------------------------------------
    # Export
    # ---------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """
        Return configuration as a dictionary.
        """

        return {
            "ac_power_recovery": self._configuration.ac_power_recovery,
            "battery_charge_limit": self._configuration.battery_charge_limit,
            "battery_health_mode": self._configuration.battery_health_mode,
            "adaptive_charging": self._configuration.adaptive_charging,
            "peak_shift_enabled": self._configuration.peak_shift_enabled,
            "wake_on_ac": self._configuration.wake_on_ac,
        }