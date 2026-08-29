"""
Project Aquila
=============

Virtualization Capability Inspection

Wraps ``hardware.virtualization.VirtualizationDetector`` (REQ-INS-012,
REQ-INS-013) with Aquila's virtualization policy
(``common.constants.hardware.REQUIRE_VIRTUALIZATION``, REQ-PROV-005)
to produce a pass/warning/fail verdict for the Inspection Engine's
hardware report (REQ-INS-025).

Hardware that cannot support virtualization at all fails outright
(REQ-PROV-006: deployment cannot proceed); hardware that supports it
but has it disabled in firmware only warns, since a technician can fix
that without replacing the hardware (REQ-PROV-005/006's distinction
between a permanent and a recoverable provisioning failure).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from common.constants.hardware import REQUIRE_VIRTUALIZATION
from common.enums import InspectionResult, VirtualizationState
from hardware.virtualization import VirtualizationDetector
from models.hardware import CPUInfo, VirtualizationInfo

from .report import CategoryAssessment


class VirtualizationInspector:
    """Detects hardware virtualization capability and assesses it against policy."""

    def __init__(self, detector: VirtualizationDetector | None = None) -> None:
        self._detector = detector or VirtualizationDetector()

    def inspect(
        self, cpu_info: CPUInfo | None = None
    ) -> CategoryAssessment[VirtualizationInfo]:
        info = self._detector.detect(cpu_info)

        if not REQUIRE_VIRTUALIZATION:
            return CategoryAssessment(data=info, result=InspectionResult.PASS)

        if not info.cpu_supported:
            return CategoryAssessment(
                data=info,
                result=InspectionResult.FAIL,
                messages=[
                    "This CPU does not support hardware virtualization "
                    "(Intel VT-x / AMD-V)."
                ],
            )

        if info.firmware_state is not VirtualizationState.ENABLED:
            return CategoryAssessment(
                data=info,
                result=InspectionResult.WARNING,
                messages=[
                    "Hardware virtualization is supported but not "
                    "currently enabled in firmware; enable it in the "
                    "BIOS/UEFI setup before provisioning."
                ],
            )

        return CategoryAssessment(data=info, result=InspectionResult.PASS)


__all__ = ["VirtualizationInspector"]
