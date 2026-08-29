"""
Project Aquila
=============

CPU Inspection

Wraps ``hardware.cpu.CPUDetector`` (REQ-INS-001, REQ-INS-002) with
Aquila's minimum-hardware policy (``common.constants.hardware``,
REQ-PROV-005) to produce a pass/warning/fail verdict for the
Inspection Engine's hardware report (REQ-INS-025).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from common.constants.hardware import MINIMUM_CPU_CORES, MINIMUM_CPU_THREADS
from common.enums import InspectionResult
from hardware.cpu import CPUDetector
from models.hardware import CPUInfo

from .report import CategoryAssessment


class CPUInspector:
    """Detects installed processors and assesses them against policy."""

    def __init__(self, detector: CPUDetector | None = None) -> None:
        self._detector = detector or CPUDetector()

    def inspect(self) -> CategoryAssessment[CPUInfo]:
        cpu_info = self._detector.detect()

        if cpu_info.physical_cores == 0 and cpu_info.logical_processors == 0:
            return CategoryAssessment(
                data=cpu_info,
                result=InspectionResult.FAIL,
                messages=["No processor could be detected."],
            )

        messages: list[str] = []
        result = InspectionResult.PASS

        if cpu_info.physical_cores < MINIMUM_CPU_CORES:
            result = InspectionResult.FAIL
            messages.append(
                f"{cpu_info.physical_cores} physical core(s) detected; "
                f"at least {MINIMUM_CPU_CORES} required."
            )

        if cpu_info.logical_processors < MINIMUM_CPU_THREADS:
            result = InspectionResult.FAIL
            messages.append(
                f"{cpu_info.logical_processors} logical processor(s) "
                f"detected; at least {MINIMUM_CPU_THREADS} required."
            )

        return CategoryAssessment(data=cpu_info, result=result, messages=messages)


__all__ = ["CPUInspector"]
