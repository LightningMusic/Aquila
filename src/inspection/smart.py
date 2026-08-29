"""
Project Aquila
=============

SMART Inspection

Wraps ``hardware.smart.SMARTDetector`` (REQ-INS-007) with Aquila's
sector-error policy (``common.constants.hardware``, all three
thresholds are zero-tolerance) to produce a pass/warning/fail verdict
for the Inspection Engine's hardware report (REQ-INS-025).

A device the underlying driver does not support SMART for at all
(``SMARTReport.supported is False``) is not counted as a failure --
REQ-INS-007 only requires retrieving SMART information "for supported
storage devices" -- but does downgrade the overall category verdict to
WARNING, since health could not be confirmed either way for that
device.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from common.constants.hardware import (
    MAX_PENDING_SECTORS,
    MAX_REALLOCATED_SECTORS,
    MAX_UNCORRECTABLE_SECTORS,
)
from common.enums import InspectionResult, SMARTStatus
from hardware.smart import SMARTDetector
from models.hardware import SMARTReport

from .report import CategoryAssessment


class SMARTInspector:
    """Detects storage SMART health and assesses it against policy."""

    def __init__(self, detector: SMARTDetector | None = None) -> None:
        self._detector = detector or SMARTDetector()

    def inspect(self) -> CategoryAssessment[list[SMARTReport]]:
        reports = self._detector.detect_all()

        if not reports:
            return CategoryAssessment(
                data=reports,
                result=InspectionResult.WARNING,
                messages=[
                    "No storage devices were available for SMART health "
                    "evaluation."
                ],
            )

        messages: list[str] = []
        result = InspectionResult.PASS
        unsupported_count = 0

        for report in reports:
            if not report.supported:
                unsupported_count += 1
                continue

            if self._is_failing(report):
                result = InspectionResult.FAIL
                messages.append(
                    f"{report.device_path or 'unknown device'}: SMART "
                    f"health check failed (status={report.status.name}, "
                    f"reallocated={report.reallocated_sector_count}, "
                    f"pending={report.pending_sector_count}, "
                    f"uncorrectable={report.uncorrectable_sector_count})."
                )

        if unsupported_count and result is InspectionResult.PASS:
            result = InspectionResult.WARNING
            messages.append(
                f"SMART health could not be verified for "
                f"{unsupported_count} of {len(reports)} storage device(s)."
            )

        return CategoryAssessment(data=reports, result=result, messages=messages)

    @staticmethod
    def _is_failing(report: SMARTReport) -> bool:
        if report.status is SMARTStatus.FAILED:
            return True

        return any(
            count is not None and count > limit
            for count, limit in (
                (report.reallocated_sector_count, MAX_REALLOCATED_SECTORS),
                (report.pending_sector_count, MAX_PENDING_SECTORS),
                (report.uncorrectable_sector_count, MAX_UNCORRECTABLE_SECTORS),
            )
        )


__all__ = ["SMARTInspector"]
