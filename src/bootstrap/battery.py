"""
Project Aquila
=============

Battery Charge Threshold Configuration

Implements REQ-BOOT-009 ("attempt to configure supported firmware
battery charging thresholds") and REQ-BOOT-010 ("if unsupported, log
the limitation and continue deployment").

Research basis (this session, primary source: the Linux kernel's own
documentation, ``Documentation/admin-guide/laptops/thinkpad-acpi.rst``,
which explicitly states the exact semantics live in the generic kernel
ABI file ``testing/sysfs-class-power``): ``charge_control_start_
threshold``/``charge_control_end_threshold`` under
``/sys/class/power_supply/BAT*/`` are part of the generic Linux
``power_supply`` sysfs ABI, not a thinkpad_acpi-specific interface --
other laptop-vendor drivers (dell-laptop, ideapad-laptop, etc.)
implement the same attribute names when their hardware supports charge
limiting. Values are integer percentages: start 0-99, end 1-100.

Runs entirely within Phase Two (the freshly-installed Linux node).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from common.constants.logging import BOOTSTRAP_LOGGER

logger = logging.getLogger(BOOTSTRAP_LOGGER)

_START_ATTRIBUTE = "charge_control_start_threshold"
_END_ATTRIBUTE = "charge_control_end_threshold"

_DEFAULT_POWER_SUPPLY_ROOT = Path("/sys/class/power_supply")


@dataclass(slots=True, frozen=True)
class BatteryThresholdResult:
    """REQ-BOOT-009/010's outcome for a single battery."""

    battery_name: str
    supported: bool
    applied: bool
    detail: str


class BatteryThresholdConfigurator:
    """
    Applies battery charge-limiting thresholds to every battery that
    exposes the generic ``power_supply`` charge-control sysfs
    attributes (REQ-BOOT-009), honestly reporting -- never raising --
    on batteries that don't (REQ-BOOT-010).
    """

    def __init__(
        self, *, power_supply_root: Path | None = None
    ) -> None:
        self._power_supply_root = (
            power_supply_root or _DEFAULT_POWER_SUPPLY_ROOT
        )

    def discover_batteries(self) -> tuple[Path, ...]:
        """Every ``BAT*`` entry under the power-supply sysfs root."""

        if not self._power_supply_root.is_dir():
            return ()

        return tuple(
            sorted(
                entry
                for entry in self._power_supply_root.glob("BAT*")
                if entry.is_dir()
            )
        )

    def configure(
        self, start_threshold: int, end_threshold: int
    ) -> tuple[BatteryThresholdResult, ...]:
        """
        Apply ``start_threshold``/``end_threshold`` (percent) to
        every discovered battery.

        Returns one :class:`BatteryThresholdResult` per battery. A
        system with no batteries at all (a desktop, or a laptop
        reporting no ``BAT*`` entries) returns an empty tuple -- that
        is itself a normal, honest outcome, not an error.
        """

        results: list[BatteryThresholdResult] = []

        for battery_path in self.discover_batteries():
            results.append(
                self._configure_one(
                    battery_path, start_threshold, end_threshold
                )
            )

        return tuple(results)

    def _configure_one(
        self,
        battery_path: Path,
        start_threshold: int,
        end_threshold: int,
    ) -> BatteryThresholdResult:
        name = battery_path.name
        start_attr = battery_path / _START_ATTRIBUTE
        end_attr = battery_path / _END_ATTRIBUTE

        if not start_attr.exists() or not end_attr.exists():
            detail = (
                f"{name} does not expose charge-threshold control "
                "(no charge_control_start_threshold/"
                "charge_control_end_threshold attributes) -- "
                "unsupported on this hardware, continuing "
                "(REQ-BOOT-010)."
            )
            logger.info(detail)
            return BatteryThresholdResult(
                battery_name=name,
                supported=False,
                applied=False,
                detail=detail,
            )

        try:
            start_attr.write_text(str(start_threshold))
            end_attr.write_text(str(end_threshold))
        except OSError as exc:
            detail = (
                f"{name} exposes charge-threshold control but "
                f"writing the new thresholds failed: {exc} -- "
                "continuing (REQ-BOOT-010)."
            )
            logger.warning(detail)
            return BatteryThresholdResult(
                battery_name=name,
                supported=True,
                applied=False,
                detail=detail,
            )

        detail = (
            f"{name} charge thresholds set to "
            f"{start_threshold}%-{end_threshold}%."
        )
        logger.info(detail)
        return BatteryThresholdResult(
            battery_name=name,
            supported=True,
            applied=True,
            detail=detail,
        )


__all__ = ["BatteryThresholdConfigurator", "BatteryThresholdResult"]
