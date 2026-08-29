"""
Project Aquila
=============

BIOS/Firmware Inspection

Wraps ``hardware.bios.BIOSDetector`` (REQ-INS-014 through REQ-INS-019,
REQ-INS-022, REQ-INS-023) with Aquila's firmware policy
(``common.constants.hardware``: ``REQUIRE_UEFI``,
``REQUIRE_SECURE_BOOT_DISABLED``) to produce a pass/warning/fail
verdict for the Inspection Engine's hardware report (REQ-INS-025).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from bios.models import BIOSMode

from common.constants.hardware import REQUIRE_SECURE_BOOT_DISABLED, REQUIRE_UEFI
from common.enums import InspectionResult
from hardware.bios import BIOSDetector
from models.hardware import BIOSInspectionInfo

from .report import CategoryAssessment


class BIOSInspector:
    """Detects firmware/BIOS facts and assesses them against policy."""

    def __init__(self, detector: BIOSDetector | None = None) -> None:
        self._detector = detector or BIOSDetector()

    def inspect(self) -> CategoryAssessment[BIOSInspectionInfo]:
        info = self._detector.detect()
        messages: list[str] = []
        result = InspectionResult.PASS

        if REQUIRE_UEFI and info.firmware.mode is not BIOSMode.UEFI:
            result = InspectionResult.FAIL
            messages.append(
                f"Firmware boot mode is '{info.firmware.mode.value}'; "
                f"UEFI boot is required."
            )

        if REQUIRE_SECURE_BOOT_DISABLED:
            if info.secure_boot_enabled is True:
                result = InspectionResult.FAIL
                messages.append(
                    "Secure Boot is enabled; deployment policy requires "
                    "it disabled."
                )
            elif info.secure_boot_enabled is None and result is InspectionResult.PASS:
                result = InspectionResult.WARNING
                messages.append("Secure Boot status could not be determined.")

        return CategoryAssessment(data=info, result=result, messages=messages)


__all__ = ["BIOSInspector"]
