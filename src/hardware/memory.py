"""
Project Aquila
=============

Memory Detection

Implements REQ-INS-003 (enumerate installed memory modules) and
REQ-INS-004 (report total installed system memory).

WMI sources: ``Win32_PhysicalMemory`` (one row per installed DIMM --
``root\\cimv2``) for per-module detail, and
``Win32_PhysicalMemoryArray`` for the motherboard's total physical
memory-slot count (``MemoryDevices``).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from models.hardware import MemoryInfo, MemoryModule, MemoryType

from . import query_wmi_safe, safe_property_value

_WMI_NAMESPACE = r"root\cimv2"

_MEMORY_QUERY = (
    "SELECT DeviceLocator, Capacity, Speed, ConfiguredClockSpeed, "
    "Manufacturer, PartNumber, SerialNumber, SMBIOSMemoryType "
    "FROM Win32_PhysicalMemory"
)

_ARRAY_QUERY = "SELECT MemoryDevices FROM Win32_PhysicalMemoryArray"

# SMBIOS "Memory Device Type" codes (DMTF SMBIOS Reference
# Specification, Type 17 structure, "Memory Type" field). Only the
# values Aquila can state with confidence are mapped; anything else
# reports MemoryType.UNKNOWN rather than guessing at a spec revision
# this code hasn't verified.
_SMBIOS_MEMORY_TYPE: dict[int, MemoryType] = {
    20: MemoryType.UNKNOWN,  # "DDR" (original) -- no matching MemoryType member
    21: MemoryType.DDR2,
    24: MemoryType.DDR3,
    26: MemoryType.DDR4,
    28: MemoryType.UNKNOWN,  # "LPDDR2" -- no matching MemoryType member
    29: MemoryType.LPDDR3,
    30: MemoryType.LPDDR4,
    34: MemoryType.DDR5,
}


class MemoryDetector:
    """Detects installed memory without modifying system state."""

    def detect(self) -> MemoryInfo:
        """
        Return a ``MemoryInfo`` record for the target system's
        installed memory.

        Returns an honestly-empty ``MemoryInfo`` (no modules, zero
        capacity) on any non-Windows platform or WMI failure, rather
        than raising -- REQ-INS-025 requires an inspection report to
        always be produced.
        """

        rows = query_wmi_safe(_WMI_NAMESPACE, _MEMORY_QUERY)

        modules = [self._module_from_row(row) for row in rows]
        total_capacity_bytes = sum(module.capacity_bytes for module in modules)

        slots_total = self._detect_slots_total()

        return MemoryInfo(
            total_capacity_bytes=total_capacity_bytes,
            slots_used=len(modules),
            slots_total=slots_total if slots_total else len(modules),
            modules=modules,
        )

    @staticmethod
    def _module_from_row(row: object) -> MemoryModule:
        capacity_raw = safe_property_value(row, "Capacity")
        speed_raw = safe_property_value(row, "Speed")
        configured_speed_raw = safe_property_value(row, "ConfiguredClockSpeed")
        smbios_type_raw = safe_property_value(row, "SMBIOSMemoryType")

        memory_type = MemoryType.UNKNOWN
        try:
            if smbios_type_raw is not None:
                memory_type = _SMBIOS_MEMORY_TYPE.get(
                    int(smbios_type_raw), MemoryType.UNKNOWN
                )
        except (TypeError, ValueError):
            memory_type = MemoryType.UNKNOWN

        return MemoryModule(
            slot=str(safe_property_value(row, "DeviceLocator") or ""),
            capacity_bytes=int(capacity_raw) if capacity_raw else 0,
            speed_mhz=int(speed_raw) if speed_raw else None,
            configured_speed_mhz=(
                int(configured_speed_raw) if configured_speed_raw else None
            ),
            memory_type=memory_type,
            manufacturer=str(safe_property_value(row, "Manufacturer") or ""),
            part_number=str(safe_property_value(row, "PartNumber") or ""),
            serial_number=str(safe_property_value(row, "SerialNumber") or ""),
        )

    @staticmethod
    def _detect_slots_total() -> int:
        rows = query_wmi_safe(_WMI_NAMESPACE, _ARRAY_QUERY)

        total = 0
        for row in rows:
            value = safe_property_value(row, "MemoryDevices")
            if value:
                try:
                    total += int(value)
                except (TypeError, ValueError):
                    continue

        return total


__all__ = ["MemoryDetector"]
