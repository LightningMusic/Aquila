"""
Project Aquila
=============

Network Adapter Inspection

Wraps ``hardware.network.NetworkDetector`` (REQ-INS-009 through
REQ-INS-011, REQ-INS-024) with Aquila's Ethernet connectivity policy
(``common.constants.hardware``, REQ-NET-004: "verify that an Ethernet
cable is connected before provisioning begins") to produce a
pass/warning/fail verdict for the Inspection Engine's hardware report
(REQ-INS-025).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from common.constants.hardware import ETHERNET_REQUIRED, MINIMUM_ETHERNET_SPEED_MBPS
from common.enums import EthernetStatus, InspectionResult
from hardware.network import NetworkDetector
from models.hardware import NetworkAdapter, NetworkAdapterType

from .report import CategoryAssessment


class NetworkInspector:
    """Detects network adapters and assesses Ethernet readiness against policy."""

    def __init__(self, detector: NetworkDetector | None = None) -> None:
        self._detector = detector or NetworkDetector()

    def inspect(self) -> CategoryAssessment[list[NetworkAdapter]]:
        adapters = self._detector.detect()

        if not ETHERNET_REQUIRED:
            return CategoryAssessment(data=adapters, result=InspectionResult.PASS)

        ethernet_adapters = [
            adapter
            for adapter in adapters
            if adapter.adapter_type is NetworkAdapterType.ETHERNET
        ]

        if not ethernet_adapters:
            return CategoryAssessment(
                data=adapters,
                result=InspectionResult.FAIL,
                messages=[
                    "No Ethernet adapter was detected; Aquila Node "
                    "Provisioning (Workflow B) requires Ethernet "
                    "connectivity."
                ],
            )

        active_adapters = [
            adapter
            for adapter in ethernet_adapters
            if adapter.link_status is EthernetStatus.ACTIVE
        ]

        if active_adapters:
            messages = [
                f"{adapter.name or 'Ethernet adapter'}: link speed "
                f"{adapter.speed_mbps} Mbps is below the minimum "
                f"{MINIMUM_ETHERNET_SPEED_MBPS} Mbps."
                for adapter in active_adapters
                if adapter.speed_mbps is not None
                and adapter.speed_mbps < MINIMUM_ETHERNET_SPEED_MBPS
            ]

            result = InspectionResult.WARNING if messages else InspectionResult.PASS
            return CategoryAssessment(data=adapters, result=result, messages=messages)

        link_detected = [
            adapter
            for adapter in ethernet_adapters
            if adapter.link_status is EthernetStatus.LINK_DETECTED
        ]

        if link_detected:
            return CategoryAssessment(
                data=adapters,
                result=InspectionResult.WARNING,
                messages=[
                    "An Ethernet adapter was detected but is not yet "
                    "fully connected."
                ],
            )

        return CategoryAssessment(
            data=adapters,
            result=InspectionResult.FAIL,
            messages=[
                "No Ethernet adapter currently has an active link; "
                "verify the cable is connected (REQ-NET-004)."
            ],
        )


__all__ = ["NetworkInspector"]
