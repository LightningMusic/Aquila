"""
Project Aquila
=============

GPU Inspection

Wraps ``hardware.gpu.GPUDetector``. Not tied to a specific SRS
``REQ-INS-*`` requirement (see ``models.hardware.gpu``'s docstring),
so this category is always informational (``InspectionResult.PASS``)
rather than pass/fail -- GPU presence and identity are collected for
PCI/vfio passthrough planning, not as a deployment gate.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from common.enums import InspectionResult
from hardware.gpu import GPUDetector
from models.hardware import GPUInfo

from .report import CategoryAssessment


class GPUInspector:
    """Detects video controllers for the hardware inventory."""

    def __init__(self, detector: GPUDetector | None = None) -> None:
        self._detector = detector or GPUDetector()

    def inspect(self) -> CategoryAssessment[list[GPUInfo]]:
        gpus = self._detector.detect()

        messages = (
            [f"{len(gpus)} video controller(s) detected."]
            if gpus
            else ["No video controller detected."]
        )

        return CategoryAssessment(data=gpus, result=InspectionResult.PASS, messages=messages)


__all__ = ["GPUInspector"]
