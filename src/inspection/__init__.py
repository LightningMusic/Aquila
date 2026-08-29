"""
Project Aquila
=============

Inspection Engine

Orchestrates every ``hardware/*.py`` detection engine into a single
hardware inspection pass and report (SRS Section 10.3, REQ-INS-001
through REQ-INS-028). See ``inspection.inspector.InspectionManager``
for the orchestrator and ``inspection.report`` for the report data
structures; each ``inspection/<category>.py`` module wraps one
``hardware/*.py`` detector with Aquila's minimum-hardware policy
(``common.constants.hardware``).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from .battery import BatteryInspector
from .bios import BIOSInspector
from .cpu import CPUInspector
from .gpu import GPUInspector
from .inspector import InspectionManager
from .memory import MemoryInspector
from .network import NetworkInspector
from .report import CategoryAssessment, HardwareInspectionReport
from .smart import SMARTInspector
from .storage import StorageInspector
from .virtualization import VirtualizationInspector

__all__ = [
    "BatteryInspector",
    "BIOSInspector",
    "CategoryAssessment",
    "CPUInspector",
    "GPUInspector",
    "HardwareInspectionReport",
    "InspectionManager",
    "MemoryInspector",
    "NetworkInspector",
    "SMARTInspector",
    "StorageInspector",
    "VirtualizationInspector",
]
