"""
Project Aquila
=============

Storage Inspection

Wraps ``hardware.storage.StorageDetector`` (REQ-INS-005 through
REQ-INS-008) with Aquila's minimum/recommended storage policy
(``common.constants.hardware``, REQ-PROV-005) to produce a
pass/warning/fail verdict for the Inspection Engine's hardware report
(REQ-INS-025).

Only devices ``StorageInventory.eligible_for_deployment()`` considers
eligible (non-removable, non-boot-media -- REQ-PREP-012) are assessed
against capacity policy; the deployment USB Aquila itself boots from
is correctly excluded rather than counted toward available capacity.

Free-space policy (``MINIMUM_FREE_SPACE_PERCENT``) is intentionally
not evaluated here: ``hardware.storage`` reports free space only at
the partitioned-volume level, and Inspection operates on raw,
unpartitioned physical devices (REQ-INS-026 forbids any modification,
including the partition enumeration that would be needed) -- that
check belongs to the Preparation/Provisioning stages that actually
create partitions.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from common.constants.hardware import GIB, MINIMUM_STORAGE_GB, RECOMMENDED_STORAGE_GB
from common.enums import InspectionResult
from hardware.storage import StorageDetector
from models.hardware import StorageInventory

from .report import CategoryAssessment


class StorageInspector:
    """Detects installed storage devices and assesses them against policy."""

    def __init__(self, detector: StorageDetector | None = None) -> None:
        self._detector = detector or StorageDetector()

    def inspect(self) -> CategoryAssessment[StorageInventory]:
        inventory = self._detector.detect()
        eligible = inventory.eligible_for_deployment()

        if not eligible:
            return CategoryAssessment(
                data=inventory,
                result=InspectionResult.FAIL,
                messages=[
                    "No eligible (non-removable, non-boot-media) storage "
                    "device was detected."
                ],
            )

        largest = max(eligible, key=lambda device: device.capacity_bytes)
        largest_gb = largest.capacity_bytes / GIB

        if largest_gb < MINIMUM_STORAGE_GB:
            return CategoryAssessment(
                data=inventory,
                result=InspectionResult.FAIL,
                messages=[
                    f"Largest eligible storage device is {largest_gb:.1f} GB; "
                    f"at least {MINIMUM_STORAGE_GB} GB required."
                ],
            )

        if largest_gb < RECOMMENDED_STORAGE_GB:
            return CategoryAssessment(
                data=inventory,
                result=InspectionResult.WARNING,
                messages=[
                    f"Largest eligible storage device is {largest_gb:.1f} GB; "
                    f"{RECOMMENDED_STORAGE_GB} GB is recommended."
                ],
            )

        return CategoryAssessment(data=inventory, result=InspectionResult.PASS)


__all__ = ["StorageInspector"]
