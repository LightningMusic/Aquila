"""
Project Aquila
=============

GPU Detection

Not tied to a specific SRS ``REQ-INS-*`` requirement (see
``models.hardware.gpu``'s docstring), but collected as part of
REQ-INS-025's overall hardware inspection report -- GPU presence and
identity inform PCI/vfio passthrough planning for VM workloads on the
deployed node.

WMI source: ``Win32_VideoController`` (``root\\cimv2``).

Video memory caveat (documented, not silently "fixed")
--------------------------------------------------------
``Win32_VideoController.AdapterRAM`` is a 32-bit field and is known to
wrap or misreport on GPUs with 4 GiB or more of video memory on many
Windows/driver combinations -- this is a long-standing, widely
reported limitation of the property itself, not a bug in this
detector. When available, this detector prefers the 64-bit
``HardwareInformation.qwMemorySize`` value stored by the display
driver under each adapter's registry subkey (the same registry value
GPU diagnostic tools such as GPU-Z read for this reason), falling back
to ``AdapterRAM`` when that registry value is unavailable -- never
fabricating a corrected figure when neither source is trustworthy.

``is_integrated`` is a best-effort heuristic based on adapter
name/vendor text (no generic, vendor-neutral WMI property reliably
distinguishes integrated from discrete GPUs) and is documented as such
rather than presented as an authoritative fact.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import platform
import re

from common.constants.logging import HARDWARE_LOGGER
from models.hardware import GPUInfo

from . import query_wmi_safe, safe_property_value

# Logs through the dedicated "aquila.hardware" logger -- see
# hardware.battery's identical fix for why logging.getLogger(__name__)
# is wrong here.
logger = logging.getLogger(HARDWARE_LOGGER)

_WMI_NAMESPACE = r"root\cimv2"
_VIDEO_CONTROLLER_QUERY = (
    "SELECT Name, AdapterCompatibility, DriverVersion, AdapterRAM, "
    "PNPDeviceID FROM Win32_VideoController"
)

_PCI_ID_PATTERN = re.compile(r"VEN_([0-9A-Fa-f]{4})&DEV_([0-9A-Fa-f]{4})")

_DISPLAY_CLASS_REGISTRY_GUID = r"{4d36e968-e325-11ce-bfc1-08002be10318}"

# Best-effort vendor/model text heuristic for integrated-vs-discrete
# classification -- see module docstring.
_INTEGRATED_NAME_MARKERS = (
    "intel(r) uhd",
    "intel(r) hd graphics",
    "intel(r) iris",
    "intel uhd",
    "intel hd graphics",
    "intel iris",
    "amd radeon(tm) graphics",
    "amd radeon graphics",
    "radeon vega",
    "apple m",
)


class GPUDetector:
    """Detects video controllers without modifying system state."""

    def detect(self) -> list[GPUInfo]:
        """
        Return every video controller enumerated on the target system.

        Returns an empty list -- honestly, not a fabricated adapter --
        on any non-Windows platform or WMI failure.
        """

        rows = query_wmi_safe(_WMI_NAMESPACE, _VIDEO_CONTROLLER_QUERY)
        return [self._gpu_from_row(row) for row in rows]

    def _gpu_from_row(self, row: object) -> GPUInfo:
        name = str(safe_property_value(row, "Name") or "")
        vendor = str(safe_property_value(row, "AdapterCompatibility") or "")
        pnp_device_id = str(safe_property_value(row, "PNPDeviceID") or "")

        adapter_ram_raw = safe_property_value(row, "AdapterRAM")
        video_memory_bytes: int | None = (
            int(adapter_ram_raw) if adapter_ram_raw else None
        )

        registry_memory_bytes = self._registry_memory_bytes(pnp_device_id)
        if registry_memory_bytes is not None:
            video_memory_bytes = registry_memory_bytes

        pci_match = _PCI_ID_PATTERN.search(pnp_device_id)
        pci_device_id = (
            f"VEN_{pci_match.group(1)}&DEV_{pci_match.group(2)}"
            if pci_match
            else ""
        )

        return GPUInfo(
            name=name,
            vendor=vendor,
            driver_version=str(safe_property_value(row, "DriverVersion") or ""),
            video_memory_bytes=video_memory_bytes,
            is_integrated=self._is_integrated(name),
            pci_device_id=pci_device_id,
        )

    @staticmethod
    def _is_integrated(name: str) -> bool:
        normalized = name.strip().lower()
        return any(marker in normalized for marker in _INTEGRATED_NAME_MARKERS)

    @staticmethod
    def _registry_memory_bytes(pnp_device_id: str) -> int | None:
        """
        Best-effort read of the display driver's own 64-bit VRAM-size
        value from the registry, keyed to this adapter's PNP device ID
        under the display device-class registry key.

        Returns ``None`` -- never a guessed value -- on any platform,
        permission, or matching failure.
        """

        if platform.system() != "Windows" or not pnp_device_id:
            return None

        try:
            import winreg  # Windows-only stdlib module; imported lazily so this module still imports cleanly on non-Windows development/test platforms.
        except ImportError:
            return None

        normalized_target = re.sub(r"[^0-9A-Za-z]", "", pnp_device_id).lower()
        if not normalized_target:
            return None

        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                rf"SYSTEM\CurrentControlSet\Control\Class\{_DISPLAY_CLASS_REGISTRY_GUID}",
            ) as class_key:
                index = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(class_key, index)
                    except OSError:
                        break
                    index += 1

                    if not subkey_name.isdigit():
                        continue

                    try:
                        with winreg.OpenKey(class_key, subkey_name) as subkey:
                            matched_device_id, _ = winreg.QueryValueEx(
                                subkey, "MatchingDeviceId"
                            )
                            normalized_match = re.sub(
                                r"[^0-9A-Za-z]", "", str(matched_device_id)
                            ).lower()

                            if normalized_match not in normalized_target and (
                                normalized_target not in normalized_match
                            ):
                                continue

                            memory_size, _ = winreg.QueryValueEx(
                                subkey, "HardwareInformation.qwMemorySize"
                            )
                            return int(memory_size)
                    except (OSError, FileNotFoundError, ValueError):
                        continue
        except (OSError, FileNotFoundError) as exc:
            logger.debug("GPU memory-size registry read failed: %s", exc)
            return None

        return None


__all__ = ["GPUDetector"]
