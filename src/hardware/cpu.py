"""
Project Aquila
=============

CPU Detection

Implements REQ-INS-001 (enumerate installed processors), REQ-INS-002
(manufacturer/model/architecture/virtualization capabilities),
REQ-INS-012 (CPU virtualization support), and REQ-INS-013 (firmware
virtualization enablement).

WMI source: ``Win32_Processor`` (``root\\cimv2``). One row per logical
socket -- most systems report exactly one row; multi-socket server
boards report one row per physical socket, aggregated below.
``VMMonitorModeExtensions`` (CPU capability) and
``VirtualizationFirmwareEnabled`` (firmware state) are both real,
documented ``Win32_Processor`` properties, but neither is supported
before Windows 8 / Windows Server 2012 -- on an older target OS they
come back ``None``, honestly reported as ``False`` rather than
guessed.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import platform
import re
from typing import Any

from models.hardware import CPUArchitecture, CPUInfo

from . import first_property, query_wmi_safe, safe_property_value

_WMI_NAMESPACE = r"root\cimv2"

_CPU_QUERY = (
    "SELECT Name, Manufacturer, NumberOfCores, NumberOfLogicalProcessors, "
    "MaxClockSpeed, CurrentClockSpeed, L2CacheSize, L3CacheSize, "
    "ProcessorId, Family, Version, AddressWidth, "
    "VirtualizationFirmwareEnabled, VMMonitorModeExtensions "
    "FROM Win32_Processor"
)

_STEPPING_PATTERN = re.compile(r"Stepping\s+(\S+)", re.IGNORECASE)


class CPUDetector:
    """Detects installed processors without modifying system state."""

    def detect(self) -> CPUInfo:
        """
        Return a vendor-neutral ``CPUInfo`` record for the target
        system's installed processor(s).

        On any non-Windows platform, or when WMI is unavailable, this
        returns an honestly-empty ``CPUInfo`` (all counts zero,
        architecture ``UNKNOWN``) rather than raising -- REQ-INS-025
        requires an inspection report to always be produced, even
        when a category can't be detected.
        """

        rows = query_wmi_safe(_WMI_NAMESPACE, _CPU_QUERY)

        if not rows:
            return CPUInfo()

        socket_count = len(rows)

        physical_cores = sum(
            int(safe_property_value(row, "NumberOfCores") or 0) for row in rows
        )
        logical_processors = sum(
            int(safe_property_value(row, "NumberOfLogicalProcessors") or 0)
            for row in rows
        )

        # Clock speeds and cache sizes are per-socket in WMI; for the
        # (overwhelmingly common) single-socket case these are simply
        # that socket's values. For multi-socket systems, the first
        # socket's values are used -- REQ-PROV-005's minimum-hardware
        # check cares about "is this hardware sufficient", not a
        # precise multi-socket average, and per-socket asymmetry on
        # real hardware is effectively nonexistent.
        first_row = rows[0]

        max_clock_raw = safe_property_value(first_row, "MaxClockSpeed")
        current_clock_raw = safe_property_value(first_row, "CurrentClockSpeed")
        l2_raw = safe_property_value(first_row, "L2CacheSize")
        l3_raw = safe_property_value(first_row, "L3CacheSize")

        version_string = str(safe_property_value(first_row, "Version") or "")
        stepping_match = _STEPPING_PATTERN.search(version_string)

        address_width = safe_property_value(first_row, "AddressWidth")
        architecture = self._architecture_from_address_width(address_width)

        virtualization_enabled = bool(
            safe_property_value(first_row, "VirtualizationFirmwareEnabled")
        )
        virtualization_supported = bool(
            safe_property_value(first_row, "VMMonitorModeExtensions")
        ) or virtualization_enabled  # firmware can't enable an unsupported feature

        return CPUInfo(
            manufacturer=first_property(rows, "Manufacturer"),
            model_name=first_property(rows, "Name"),
            architecture=architecture,
            socket_count=socket_count,
            physical_cores=physical_cores,
            logical_processors=logical_processors,
            base_clock_mhz=(
                float(current_clock_raw) if current_clock_raw else None
            ),
            max_clock_mhz=float(max_clock_raw) if max_clock_raw else None,
            l2_cache_kb=int(l2_raw) if l2_raw else None,
            l3_cache_kb=int(l3_raw) if l3_raw else None,
            virtualization_supported=virtualization_supported,
            virtualization_enabled=virtualization_enabled,
            processor_id=first_property(rows, "ProcessorId"),
            family=str(safe_property_value(first_row, "Family") or ""),
            stepping=stepping_match.group(1) if stepping_match else "",
        )

    @staticmethod
    def _architecture_from_address_width(address_width: Any) -> CPUArchitecture:
        """
        Derive architecture from ``Win32_Processor.AddressWidth``
        (32/64), cross-checked against ``platform.machine()`` when
        WMI's own value is unavailable (non-Windows testing, or an
        older WMI provider that doesn't populate it).
        """

        machine = platform.machine().lower()
        is_arm = "arm" in machine or "aarch64" in machine

        width: int | None
        try:
            width = int(address_width) if address_width is not None else None
        except (TypeError, ValueError):
            width = None

        if width == 64:
            return CPUArchitecture.ARM64 if is_arm else CPUArchitecture.X86_64

        if width == 32:
            return CPUArchitecture.ARM if is_arm else CPUArchitecture.X86

        return CPUArchitecture.from_string(machine) if machine else CPUArchitecture.UNKNOWN


__all__ = ["CPUDetector"]
