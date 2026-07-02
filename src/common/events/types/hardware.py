"""
Project Orion
=============

Hardware events.

Defines events related to hardware inspection, health monitoring,
component detection, BIOS configuration, SMART status, and battery
health.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from common.enums import EventSource, EventType
from common.events.event import Event


# =============================================================================
# Hardware Detection
# =============================================================================


class HardwareInspectionStartedEvent(Event):
    """
    Published when hardware inspection begins.
    """

    def __init__(self) -> None:
        super().__init__(
            event_type=EventType.HARDWARE_INSPECTION_STARTED.name,
            source=EventSource.INSPECTION_MANAGER.name,
        )


class HardwareInspectionCompletedEvent(Event):
    """
    Published when hardware inspection completes successfully.
    """

    def __init__(self) -> None:
        super().__init__(
            event_type=EventType.HARDWARE_INSPECTION_COMPLETED.name,
            source=EventSource.INSPECTION_MANAGER.name,
        )


class HardwareInspectionFailedEvent(Event):
    """
    Published when hardware inspection cannot be completed.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            event_type=EventType.HARDWARE_INSPECTION_FAILED.name,
            source=EventSource.INSPECTION_MANAGER.name,
            payload={
                "reason": reason,
            },
        )


# =============================================================================
# CPU
# =============================================================================


class CPUDetectedEvent(Event):
    """
    Published after CPU detection.
    """

    def __init__(
        self,
        manufacturer: str,
        model: str,
        cores: int,
        threads: int,
    ) -> None:
        super().__init__(
            event_type=EventType.CPU_DETECTED.name,
            source=EventSource.INSPECTION_MANAGER.name,
            payload={
                "manufacturer": manufacturer,
                "model": model,
                "cores": cores,
                "threads": threads,
            },
        )


# =============================================================================
# Memory
# =============================================================================


class MemoryDetectedEvent(Event):
    """
    Published after system memory detection.
    """

    def __init__(
        self,
        total_memory_gb: float,
        slot_count: int,
    ) -> None:
        super().__init__(
            event_type=EventType.MEMORY_DETECTED.name,
            source=EventSource.INSPECTION_MANAGER.name,
            payload={
                "total_memory_gb": total_memory_gb,
                "slot_count": slot_count,
            },
        )


# =============================================================================
# Storage
# =============================================================================


class StorageDetectedEvent(Event):
    """
    Published after storage devices are detected.
    """

    def __init__(
        self,
        device_count: int,
    ) -> None:
        super().__init__(
            event_type=EventType.STORAGE_DETECTED.name,
            source=EventSource.INSPECTION_MANAGER.name,
            payload={
                "device_count": device_count,
            },
        )


class SMARTCheckCompletedEvent(Event):
    """
    Published after SMART health checks complete.
    """

    def __init__(
        self,
        passed: bool,
        failed_drives: int,
    ) -> None:
        super().__init__(
            event_type=EventType.SMART_CHECK_COMPLETED.name,
            source=EventSource.INSPECTION_MANAGER.name,
            payload={
                "passed": passed,
                "failed_drives": failed_drives,
            },
        )


# =============================================================================
# Battery
# =============================================================================


class BatteryDetectedEvent(Event):
    """
    Published after battery detection.
    """

    def __init__(
        self,
        present: bool,
        health_percent: float,
    ) -> None:
        super().__init__(
            event_type=EventType.BATTERY_DETECTED.name,
            source=EventSource.INSPECTION_MANAGER.name,
            payload={
                "present": present,
                "health_percent": health_percent,
            },
        )


class BatteryHealthWarningEvent(Event):
    """
    Published when battery health falls below acceptable limits.
    """

    def __init__(
        self,
        health_percent: float,
    ) -> None:
        super().__init__(
            event_type=EventType.BATTERY_HEALTH_WARNING.name,
            source=EventSource.INSPECTION_MANAGER.name,
            payload={
                "health_percent": health_percent,
            },
        )


# =============================================================================
# BIOS
# =============================================================================


class BIOSDetectedEvent(Event):
    """
    Published after BIOS information has been collected.
    """

    def __init__(
        self,
        vendor: str,
        version: str,
    ) -> None:
        super().__init__(
            event_type=EventType.BIOS_DETECTED.name,
            source=EventSource.INSPECTION_MANAGER.name,
            payload={
                "vendor": vendor,
                "version": version,
            },
        )


class VirtualizationDetectedEvent(Event):
    """
    Published after virtualization capability has been determined.
    """

    def __init__(
        self,
        enabled: bool,
    ) -> None:
        super().__init__(
            event_type=EventType.VIRTUALIZATION_DETECTED.name,
            source=EventSource.INSPECTION_MANAGER.name,
            payload={
                "enabled": enabled,
            },
        )


# =============================================================================
# Summary
# =============================================================================


class HardwareAssessmentCompletedEvent(Event):
    """
    Published after the complete hardware assessment has finished.
    """

    def __init__(
        self,
        passed: bool,
        warnings: int,
        failures: int,
    ) -> None:
        super().__init__(
            event_type=EventType.HARDWARE_ASSESSMENT_COMPLETED.name,
            source=EventSource.INSPECTION_MANAGER.name,
            payload={
                "passed": passed,
                "warnings": warnings,
                "failures": failures,
            },
        )