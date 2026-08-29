"""
Project Aquila
=============

Battery Inspection

Wraps ``hardware.battery.BatteryDetector`` (REQ-INS-020, REQ-INS-021)
with Aquila's battery-health policy (``common.constants.hardware``,
GP-008: Hardware Preservation) to produce a pass/warning/fail verdict
for the Inspection Engine's hardware report (REQ-INS-025).

A desktop/server system with no battery is not a failure --
``BatteryInfo(present=False)`` is the correct, complete record for
such a system (see ``models.hardware.battery``'s docstring) -- and
this inspector reports it as PASS.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from common.constants.hardware import (
    BATTERY_HEALTH_CRITICAL_PERCENT,
    BATTERY_HEALTH_WARNING_PERCENT,
)
from common.enums import InspectionResult
from hardware.battery import BatteryDetector
from models.hardware import BatteryInfo

from .report import CategoryAssessment


class BatteryInspector:
    """Detects battery presence/health and assesses it against policy."""

    def __init__(self, detector: BatteryDetector | None = None) -> None:
        self._detector = detector or BatteryDetector()

    def inspect(self) -> CategoryAssessment[BatteryInfo]:
        battery_info = self._detector.detect()

        if not battery_info.present:
            return CategoryAssessment(
                data=battery_info,
                result=InspectionResult.PASS,
                messages=["No battery present (desktop/server system)."],
            )

        health_percent = battery_info.health_percent

        if health_percent is None:
            return CategoryAssessment(
                data=battery_info,
                result=InspectionResult.WARNING,
                messages=[
                    "Battery is present but health percentage could not "
                    "be determined."
                ],
            )

        if health_percent < BATTERY_HEALTH_CRITICAL_PERCENT:
            return CategoryAssessment(
                data=battery_info,
                result=InspectionResult.FAIL,
                messages=[
                    f"Battery health is {health_percent}% of design "
                    f"capacity, below the critical threshold of "
                    f"{BATTERY_HEALTH_CRITICAL_PERCENT}%."
                ],
            )

        if health_percent < BATTERY_HEALTH_WARNING_PERCENT:
            return CategoryAssessment(
                data=battery_info,
                result=InspectionResult.WARNING,
                messages=[
                    f"Battery health is {health_percent}% of design "
                    f"capacity, below the recommended threshold of "
                    f"{BATTERY_HEALTH_WARNING_PERCENT}%."
                ],
            )

        return CategoryAssessment(data=battery_info, result=InspectionResult.PASS)


__all__ = ["BatteryInspector"]
