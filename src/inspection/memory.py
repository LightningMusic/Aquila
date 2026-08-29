"""
Project Aquila
=============

Memory Inspection

Wraps ``hardware.memory.MemoryDetector`` (REQ-INS-003, REQ-INS-004)
with Aquila's minimum/recommended memory policy
(``common.constants.hardware``, REQ-PROV-005) to produce a
pass/warning/fail verdict for the Inspection Engine's hardware report
(REQ-INS-025).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from common.constants.hardware import GIB, MINIMUM_MEMORY_GB, RECOMMENDED_MEMORY_GB
from common.enums import InspectionResult
from hardware.memory import MemoryDetector
from models.hardware import MemoryInfo

from .report import CategoryAssessment


class MemoryInspector:
    """Detects installed memory and assesses it against policy."""

    def __init__(self, detector: MemoryDetector | None = None) -> None:
        self._detector = detector or MemoryDetector()

    def inspect(self) -> CategoryAssessment[MemoryInfo]:
        memory_info = self._detector.detect()

        total_gb = memory_info.total_capacity_bytes / GIB

        if total_gb < MINIMUM_MEMORY_GB:
            return CategoryAssessment(
                data=memory_info,
                result=InspectionResult.FAIL,
                messages=[
                    f"{total_gb:.1f} GB of memory detected; at least "
                    f"{MINIMUM_MEMORY_GB} GB required."
                ],
            )

        if total_gb < RECOMMENDED_MEMORY_GB:
            return CategoryAssessment(
                data=memory_info,
                result=InspectionResult.WARNING,
                messages=[
                    f"{total_gb:.1f} GB of memory detected; "
                    f"{RECOMMENDED_MEMORY_GB} GB is recommended."
                ],
            )

        return CategoryAssessment(data=memory_info, result=InspectionResult.PASS)


__all__ = ["MemoryInspector"]
