"""
Project Aquila
=============

Virtualization Capability Detection

Implements REQ-INS-012 (determine whether CPU virtualization support
is available) and REQ-INS-013 (determine whether virtualization
support is currently enabled within firmware).

This detector deliberately does not re-query ``Win32_Processor``
itself -- ``hardware.cpu.CPUDetector`` already collects
``VMMonitorModeExtensions``/``VirtualizationFirmwareEnabled`` as part
of ``REQ-INS-001``/``REQ-INS-002``'s CPU enumeration, so the CPU-level
capability fields are read directly from an already-collected
``CPUInfo`` (or a freshly detected one when none is supplied) rather
than issuing a second, duplicate WMI query for the same data -- the
same reuse-over-duplication principle documented in
``models.hardware``'s package docstring.

Firmware-level virtualization/IOMMU state (whether the capability is
actually switched on in the BIOS right now) is more authoritatively
known by the active ``bios`` provider, which already implements
``virtualization_supported()``/``virtualization_enabled()``/
``iommu_supported()`` per-vendor where a real settings interface
exists; this detector asks that subsystem directly and only falls
back to the WMI-derived value when the active provider does not
support the query (``GenericUEFIProvider``/``UnknownProvider`` raise
``NotImplementedError`` for these, honestly, since no vendor-specific
interface exists for them).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging

from common.constants.logging import HARDWARE_LOGGER
from common.enums import VirtualizationState
from models.hardware import CPUInfo, VirtualizationInfo, VirtualizationTechnology

from .cpu import CPUDetector

# Logs through the dedicated "aquila.hardware" logger -- see
# hardware.battery's identical fix for why logging.getLogger(__name__)
# is wrong here.
logger = logging.getLogger(HARDWARE_LOGGER)

_INTEL_MANUFACTURER_IDS = {"genuineintel", "intel"}
_AMD_MANUFACTURER_IDS = {"authenticamd", "amd"}


class VirtualizationDetector:
    """Detects hardware virtualization capability and firmware state."""

    def detect(self, cpu_info: CPUInfo | None = None) -> VirtualizationInfo:
        """
        Return a ``VirtualizationInfo`` record for the target system.

        Args:
            cpu_info: An already-collected ``CPUInfo`` record (from
                ``hardware.cpu.CPUDetector``) to reuse rather than
                re-querying WMI. When omitted, a fresh detection pass
                is run.
        """

        if cpu_info is None:
            cpu_info = CPUDetector().detect()

        technology = self._technology_from_manufacturer(cpu_info.manufacturer)

        firmware_state = self._firmware_state_from_bios_provider()
        if firmware_state is VirtualizationState.UNKNOWN:
            # No authoritative vendor-specific answer -- fall back to
            # the WMI-derived firmware flag CPUDetector already
            # collected (Win32_Processor.VirtualizationFirmwareEnabled).
            if cpu_info.virtualization_enabled:
                firmware_state = VirtualizationState.ENABLED
            elif cpu_info.virtualization_supported:
                # Supported by hardware but WMI reports firmware has
                # not enabled it -- honestly DISABLED, not UNKNOWN.
                firmware_state = VirtualizationState.DISABLED

        cpu_supported = cpu_info.virtualization_supported
        if firmware_state is VirtualizationState.ENABLED and not cpu_supported:
            # The BIOS provider and the WMI-derived CPU capability flag
            # disagree (a genuinely rare data-source conflict, not
            # expected in practice) -- VirtualizationInfo forbids an
            # ENABLED firmware_state when cpu_supported is False, so
            # this honestly reports UNKNOWN rather than either
            # silently trusting one disagreeing source over the other
            # or crashing.
            firmware_state = VirtualizationState.UNKNOWN

        return VirtualizationInfo(
            cpu_supported=cpu_supported,
            technology=technology,
            firmware_state=firmware_state,
            nested_virtualization_supported=None,
            iommu_supported=self._iommu_supported_from_bios_provider(),
        )

    @staticmethod
    def _technology_from_manufacturer(manufacturer: str) -> VirtualizationTechnology:
        normalized = manufacturer.strip().lower().replace(" ", "")

        if normalized in _INTEL_MANUFACTURER_IDS or "intel" in normalized:
            return VirtualizationTechnology.VT_X

        if normalized in _AMD_MANUFACTURER_IDS or "amd" in normalized:
            return VirtualizationTechnology.AMD_V

        return VirtualizationTechnology.UNKNOWN

    @staticmethod
    def _firmware_state_from_bios_provider() -> VirtualizationState:
        try:
            from bios.detection import provider

            active_provider = provider()
            supported = active_provider.virtualization_supported()
            if not supported:
                return VirtualizationState.UNKNOWN

            enabled = active_provider.virtualization_enabled()
            return (
                VirtualizationState.ENABLED
                if enabled
                else VirtualizationState.DISABLED
            )
        except Exception as exc:
            logger.debug("BIOS-level virtualization state query failed: %s", exc)
            return VirtualizationState.UNKNOWN

    @staticmethod
    def _iommu_supported_from_bios_provider() -> bool | None:
        try:
            from bios.detection import provider

            return bool(provider().iommu_supported())
        except Exception as exc:
            logger.debug("BIOS-level IOMMU capability query failed: %s", exc)
            return None


__all__ = ["VirtualizationDetector"]
