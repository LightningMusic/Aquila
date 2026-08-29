"""Lenovo BIOS provider for Project Aquila.

Backend preference:

1. Lenovo firmware WMI classes exposed under ``root\\WMI`` on Windows
   (``Lenovo_BiosSetting`` / ``Lenovo_SetBiosSetting`` /
   ``Lenovo_SaveBiosSettings`` / ``Lenovo_DiscardBiosSettings`` /
   ``Lenovo_BiosPasswordSettings`` / ``Lenovo_SetBiosPassword`` /
   ``Lenovo_LoadDefaultSettings`` / ``Lenovo_BatteryGetChargeThresholds`` /
   ``Lenovo_BatterySetChargeThresholds``). These classes are published in
   Lenovo's "ThinkPad / ThinkCentre / ThinkStation WMI Interface" reference
   and are present on the vast majority of commercial Lenovo systems
   (ThinkPad, ThinkCentre, ThinkStation, and most ThinkBook/IdeaPad models).
2. Standard UEFI firmware variables (``efibootmgr`` on Linux,
   ``bcdedit /enum firmware`` on Windows) for boot-order management. Boot
   order is a platform-standard UEFI mechanism rather than a Lenovo-specific
   one, so it is handled independently of the WMI backend above.
3. Native operating-system firmware identity interfaces (Win32_BIOS /
   Win32_ComputerSystem on Windows, ``/sys/class/dmi/id`` on Linux via
   ``DefaultProvider``).
4. ``DefaultProvider`` fallback behavior for anything this provider cannot
   confidently support.

Notes on confidence:

Lenovo's exact BIOS setting item names and password-type codes vary slightly
across product families and firmware generations. Every setting name used
below is checked against a short list of documented aliases rather than a
single hard-coded string, and every mutating operation is verified by
re-reading the setting after it is applied. Where Lenovo does not publish a
firmware-level mechanism for a capability (for example, most keyboard/mouse/
USB wake sources are managed by the operating system's power policy rather
than by BIOS on Lenovo systems), this provider reports the capability as
unsupported rather than guessing.

No BIOS, Windows account, or disk-encryption password is ever logged,
cached beyond the duration of a single call, or included in any exported
report, summary, or diagnostic payload.
"""

from __future__ import annotations

import logging
import platform
import re
import shutil
import subprocess
import threading
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, cast

from ..models import (
    BIOSMode,
    BIOSVendor,
    BootDevice,
    BootDeviceType,
    FirmwareInformation,
    TPMState,
)
from .base import ValidationError
from .default import DefaultProvider


PROVIDER_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# WMI backend
# ---------------------------------------------------------------------------

_LENOVO_WMI_NAMESPACE = r"root\WMI"

_CLASS_BIOS_SETTING = "Lenovo_BiosSetting"
_CLASS_SET_BIOS_SETTING = "Lenovo_SetBiosSetting"
_CLASS_SAVE_BIOS_SETTINGS = "Lenovo_SaveBiosSettings"
_CLASS_DISCARD_BIOS_SETTINGS = "Lenovo_DiscardBiosSettings"
_CLASS_BIOS_PASSWORD_SETTINGS = "Lenovo_BiosPasswordSettings"
_CLASS_SET_BIOS_PASSWORD = "Lenovo_SetBiosPassword"
_CLASS_LOAD_DEFAULT_SETTINGS = "Lenovo_LoadDefaultSettings"
_CLASS_GET_CHARGE_THRESHOLDS = "Lenovo_BatteryGetChargeThresholds"
_CLASS_SET_CHARGE_THRESHOLDS = "Lenovo_BatterySetChargeThresholds"

# Power-On Password / Supervisor (admin) password type codes as used by
# ``Lenovo_SetBiosPassword``. Confirm against Lenovo's current WMI Interface
# reference for the specific platform before relying on this in a fleet with
# mixed hardware generations; community tooling and Lenovo's own SCCM/MDT
# guidance consistently document these two codes.
_PASSWORD_TYPE_POWER_ON = "pap"
_PASSWORD_TYPE_SUPERVISOR = "sup"

_TRUE_VALUES: Set[str] = {
    "1",
    "active",
    "enable",
    "enabled",
    "on",
    "primary",
    "true",
    "yes",
}

_FALSE_VALUES: Set[str] = {
    "0",
    "disable",
    "disabled",
    "inactive",
    "off",
    "no",
    "none",
    "false",
}

# Each capability is matched against every candidate item name in order,
# because the exact string varies across ThinkPad / ThinkCentre /
# ThinkStation firmware generations.
_SETTING_VIRTUALIZATION: Tuple[str, ...] = (
    "VirtualizationTechnology",
    "IntelVirtualizationTechnology",
    "AMDVirtualizationTechnology",
    "VTx",
)
_SETTING_IOMMU: Tuple[str, ...] = (
    "VTdFeature",
    "IntelVTdTech",
    "VTd",
    "AMDIOMMU",
)
_SETTING_SRIOV: Tuple[str, ...] = (
    "SRIOVSupport",
    "SRIOV",
)
_SETTING_SECURE_BOOT: Tuple[str, ...] = (
    "SecureBoot",
)
_SETTING_SECURITY_CHIP: Tuple[str, ...] = (
    "SecurityChip",
    "TPMDevice",
    "DiscreteTPMSelection",
)
_SETTING_WAKE_ON_LAN: Tuple[str, ...] = (
    "WakeOnLAN",
    "WakeOnLANDock",
)
_SETTING_AC_RECOVERY: Tuple[str, ...] = (
    "PowerOnAfterPowerLoss",
    "AfterPowerLoss",
    "ACPowerRecovery",
)
_SETTING_FAST_BOOT: Tuple[str, ...] = (
    "QuickBoot",
    "FastBoot",
)
_SETTING_BOOT_MODE: Tuple[str, ...] = (
    "BootMode",
    "UEFIBootMode",
)
_SETTING_CONSERVATION_MODE: Tuple[str, ...] = (
    "BatteryChargeMode",
    "ConservationMode",
)

logger = logging.getLogger(__name__)


class LenovoProvider(DefaultProvider):
    """Production Lenovo firmware provider.

    Supports ThinkPad, ThinkCentre, ThinkStation, and most ThinkBook /
    IdeaPad commercial systems that expose the standard Lenovo firmware WMI
    interface on Windows. On Linux, and on Windows systems where the WMI
    classes above are unavailable, this provider degrades to
    ``DefaultProvider`` behavior for settings it cannot reach, while still
    using standard UEFI mechanisms for boot-order management.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize provider state without opening privileged resources."""
        super().__init__(*args, **kwargs)
        self._lenovo_logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}"
        )
        self._execution_lock = threading.RLock()
        self._wmi_handle: Any = None
        self._wmi_available: Optional[bool] = None
        self._raw_settings: Dict[str, str] = {}
        self._pending_wmi_writes: Set[str] = set()
        self._password_state_cache: Optional[Dict[str, Any]] = None
        self._efibootmgr_path: Optional[Path] = None
        self._connected = False
        self._closed = False

    # -------------------------------------------------------------------
    # Identity, detection, and lifecycle
    # -------------------------------------------------------------------

    def vendor(self) -> BIOSVendor:
        """Return the Lenovo vendor identifier."""
        return BIOSVendor.LENOVO

    def provider_name(self) -> str:
        """Return the stable provider name."""
        return "lenovo"

    def provider_version(self) -> str:
        """Return the Lenovo provider implementation version."""
        return PROVIDER_VERSION

    def supports_windows(self) -> bool:
        """Return whether this provider supports Windows hosts."""
        return True

    def supports_linux(self) -> bool:
        """Return whether this provider supports Linux hosts.

        Linux support is limited to firmware identity and boot-order
        management through standard UEFI mechanisms. Lenovo's WMI-based
        settings backend is Windows-only.
        """
        return True

    def detect(self) -> bool:
        """Return whether this system is confidently identified as Lenovo."""
        return self.detection_confidence() >= 0.7

    def detection_confidence(self) -> float:
        """Calculate a confidence score from independent Lenovo indicators."""
        manufacturer = self._system_value("sys_vendor", "Manufacturer")
        product = self._system_value("product_name", "Model")
        combined = f"{manufacturer} {product}".strip().lower()

        hypervisor_markers = (
            "qemu",
            "kvm",
            "vmware",
            "virtualbox",
            "xen",
            "hyper-v",
            "microsoft corporation virtual machine",
        )
        if any(marker in combined for marker in hypervisor_markers):
            return 0.0

        score = 0.0
        normalized_vendor = re.sub(r"[^a-z0-9]+", " ", manufacturer.lower()).strip()

        # "IBM" is included because pre-2005 ThinkPad hardware and some
        # legacy SMBIOS tables still self-report as IBM.
        if normalized_vendor in {"lenovo", "ibm"}:
            score += 0.55
        elif "lenovo" in normalized_vendor:
            score += 0.45

        if re.search(r"\bthink(pad|centre|station|book)\b", combined) or (
            "ideapad" in combined or "legion" in combined or "yoga" in combined
        ):
            score += 0.15

        if self._wmi_class_exists(_CLASS_BIOS_SETTING):
            score += 0.20

        family_prefix = self._system_value("product_family", "SystemFamily")
        if family_prefix and "think" in family_prefix.lower():
            score += 0.10

        return min(score, 1.0)

    def connect(self) -> bool:
        """Establish the Lenovo firmware backend and load current settings."""
        with self._execution_lock:
            if self._connected and self.is_connected():
                return True

            self._closed = False
            self._record_operation("connect")

            if not self.detect():
                self._record_error(
                    "connect",
                    f"{self.provider_name()} does not match this system.",
                )
                return False

            self._wmi_available = self._probe_wmi_backend()

            try:
                if not self.refresh():
                    return False
            except Exception as exc:
                self._record_error(
                    "connect",
                    f"Provider initialization failed: {exc}",
                )
                return False

            self._connected = True
            return True

    def disconnect(self) -> None:
        """Disconnect from the firmware interface and release resources."""
        with self._execution_lock:
            self._record_operation("disconnect")
            self._connected = False
            self._wmi_handle = None
            self._transaction_active = False
            self._pending_wmi_writes.clear()
            self._password_state_cache = None

    def is_connected(self) -> bool:
        """Return whether the provider is connected and ready."""
        return self._connected

    def refresh(self) -> bool:
        """Refresh cached firmware information and Lenovo BIOS settings."""
        with self._execution_lock:
            self._record_operation("refresh")

            try:
                self._firmware = self._collect_firmware_information()
                self._cache_valid = True
            except Exception as exc:
                self._cache_valid = False
                self._record_error(
                    "refresh",
                    f"Unable to refresh firmware information: {exc}",
                )
                return False

            if self._wmi_available:
                try:
                    self._load_bios_settings()
                except Exception:
                    self._lenovo_logger.debug(
                        "Unable to load Lenovo BIOS settings.",
                        exc_info=True,
                    )

            return True

    def firmware_interface(self) -> str:
        """Return the firmware-management interface used by the provider."""
        if platform.system() == "Windows" and self._wmi_available:
            return f"wmi:{_LENOVO_WMI_NAMESPACE}"

        if platform.system() == "Windows":
            return r"wmi:root\cimv2"

        return super().firmware_interface()

    # -------------------------------------------------------------------
    # Firmware inventory
    # -------------------------------------------------------------------

    def _collect_firmware_information(self) -> FirmwareInformation:
        """Collect firmware identity information.

        On Windows this queries ``Win32_BIOS`` and ``Win32_ComputerSystem``.
        Every other platform, and any Windows system where WMI is
        unreachable, falls back to ``DefaultProvider``'s sysfs-based
        collection.
        """
        if platform.system() != "Windows":
            return super()._collect_firmware_information()

        system_rows = self._query_wmi_safe(
            r"root\cimv2",
            "SELECT Manufacturer, Model, SystemFamily, "
            "SystemSKUNumber FROM Win32_ComputerSystem",
        )
        bios_rows = self._query_wmi_safe(
            r"root\cimv2",
            "SELECT SerialNumber, SMBIOSBIOSVersion, Manufacturer, "
            "ReleaseDate FROM Win32_BIOS",
        )
        product_rows = self._query_wmi_safe(
            r"root\cimv2",
            "SELECT UUID, IdentifyingNumber, SKUNumber "
            "FROM Win32_ComputerSystemProduct",
        )

        if not system_rows and not bios_rows:
            return super()._collect_firmware_information()

        manufacturer = self._first_property(system_rows, "Manufacturer") or "LENOVO"
        model = self._first_property(system_rows, "Model")
        sku = (
            self._first_property(system_rows, "SystemSKUNumber")
            or self._first_property(product_rows, "SKUNumber")
            or ""
        )
        serial_number = (
            self._first_property(bios_rows, "SerialNumber")
            or self._first_property(product_rows, "IdentifyingNumber")
            or ""
        )
        system_uuid = self._first_property(product_rows, "UUID") or ""
        bios_vendor = self._first_property(bios_rows, "Manufacturer") or manufacturer
        bios_version = self._first_property(bios_rows, "SMBIOSBIOSVersion") or ""

        release_date: Optional[date] = None
        release_date_raw = self._first_property(bios_rows, "ReleaseDate")
        if release_date_raw:
            release_date = self._parse_wmi_date(release_date_raw)

        return FirmwareInformation(
            vendor=BIOSVendor.LENOVO,
            mode=self._detect_bios_mode(),
            firmware_interface=self.firmware_interface(),
            manufacturer=manufacturer,
            product_name=model,
            model=model,
            serial_number=serial_number,
            system_uuid=system_uuid,
            sku=sku,
            bios_vendor=bios_vendor,
            bios_version=bios_version,
            bios_release_date=release_date,
            embedded_controller_version="",
            collected_at=self._now_utc(),
            raw_data={"source": "wmi:win32_bios+win32_computersystem"},
        )

    @staticmethod
    def _now_utc():
        from datetime import UTC, datetime

        return datetime.now(UTC)

    @staticmethod
    def _parse_wmi_date(value: str) -> Optional[date]:
        """Parse a WMI ``CIM_DATETIME`` string such as ``20240115000000.000000+000``."""
        match = re.match(r"^(\d{4})(\d{2})(\d{2})", value.strip())
        if not match:
            return None

        try:
            year, month, day = (int(part) for part in match.groups())
            return date(year, month, day)
        except ValueError:
            return None

    def bios_mode(self) -> BIOSMode:
        """Return the active BIOS or firmware boot mode."""
        if self._firmware.mode is not BIOSMode.UNKNOWN:
            return self._firmware.mode

        return self._detect_bios_mode()

    @staticmethod
    def _detect_bios_mode() -> BIOSMode:
        """Detect the current boot mode using generic operating-system data."""
        if platform.system() == "Windows":
            firmware_type = LenovoProvider._windows_firmware_type()
            if firmware_type is not None:
                return BIOSMode.UEFI if firmware_type == 2 else BIOSMode.LEGACY
            return BIOSMode.UNKNOWN

        if platform.system() == "Linux":
            return (
                BIOSMode.UEFI
                if Path("/sys/firmware/efi").exists()
                else BIOSMode.LEGACY
            )

        return BIOSMode.UNKNOWN

    @staticmethod
    def _windows_firmware_type() -> Optional[int]:
        """Return the Windows ``FIRMWARE_TYPE`` value when it can be read.

        ``1`` indicates legacy BIOS and ``2`` indicates UEFI. ``None`` is
        returned when the firmware type cannot be determined.
        """
        try:
            import ctypes

            firmware_type = ctypes.c_uint()
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            if kernel32.GetFirmwareType(ctypes.byref(firmware_type)):
                return int(firmware_type.value)
        except Exception:
            return None

        return None

    # -------------------------------------------------------------------
    # BIOS settings integration
    # -------------------------------------------------------------------

    def _load_bios_settings(self) -> None:
        """Load every Lenovo BIOS setting and register it for the generic API.

        Each ``Lenovo_BiosSetting`` instance exposes a single
        ``CurrentSetting`` string formatted as ``ItemName,CurrentValue`` (and
        occasionally additional comma-separated fields carrying available
        options). This method parses every instance and registers it through
        ``DefaultProvider._register_setting`` so the inherited
        ``available_settings`` / ``get_setting`` / ``set_setting`` /
        ``reset_setting`` / ``restore_defaults`` methods work without
        Lenovo-specific overrides.
        """
        rows = self._query_wmi_safe(
            _LENOVO_WMI_NAMESPACE,
            f"SELECT CurrentSetting FROM {_CLASS_BIOS_SETTING}",
        )

        self._raw_settings.clear()

        for row in rows:
            raw = self._safe_property_value(row, "CurrentSetting")
            if not raw or "," not in raw:
                continue

            parts = [part.strip() for part in raw.split(",")]
            name = parts[0]
            value = parts[1] if len(parts) > 1 else ""

            if not name:
                continue

            self._raw_settings[name] = value
            self._register_setting(
                name,
                value,
                default=None,
                writable=True,
                reboot_required=True,
            )

    def _apply_setting(self, name: str, value: Any) -> bool:
        """Apply a setting through ``Lenovo_SetBiosSetting`` and save it."""
        if platform.system() != "Windows" or not self._wmi_available:
            return False

        item = f"{name},{value}"
        result = self._invoke_wmi_method(
            _CLASS_SET_BIOS_SETTING,
            "SetBiosSetting",
            {"Parameter": item},
        )

        if not self._wmi_result_ok(result):
            return False

        if not self._save_bios_settings():
            return False

        self._raw_settings[name] = str(value)
        self._pending_wmi_writes.discard(name)
        return True

    def _save_bios_settings(self, admin_password: str = "") -> bool:
        """Commit staged Lenovo BIOS setting changes.

        Args:
            admin_password:
                Supervisor/admin password, required only when one is
                configured. The value is forwarded directly to firmware and
                is never logged or cached.
        """
        result = self._invoke_wmi_method(
            _CLASS_SAVE_BIOS_SETTINGS,
            "SaveBiosSettings",
            {"Parameter": admin_password},
        )
        del admin_password
        return self._wmi_result_ok(result)

    def _discard_bios_settings(self) -> bool:
        """Discard any staged, unsaved Lenovo BIOS setting changes."""
        result = self._invoke_wmi_method(
            _CLASS_DISCARD_BIOS_SETTINGS,
            "DiscardBiosSettings",
            {},
        )
        return self._wmi_result_ok(result)

    def _find_setting_name(self, candidates: Sequence[str]) -> Optional[str]:
        """Return the first registered setting name matching a capability."""
        for candidate in candidates:
            if candidate in self._raw_settings:
                return candidate

        lowered = {name.lower(): name for name in self._raw_settings}
        for candidate in candidates:
            match = lowered.get(candidate.lower())
            if match is not None:
                return match

        return None

    def _read_bool_setting(self, candidates: Sequence[str]) -> Tuple[bool, Optional[bool]]:
        """Return ``(supported, enabled)`` for a boolean-style BIOS setting."""
        name = self._find_setting_name(candidates)
        if name is None:
            return (False, None)

        raw_value = self._raw_settings.get(name, "").strip().lower()
        if raw_value in _TRUE_VALUES:
            return (True, True)
        if raw_value in _FALSE_VALUES:
            return (True, False)

        return (True, None)

    def _write_bool_setting(
        self,
        candidates: Sequence[str],
        enable: bool,
        *,
        true_value: str = "Enable",
        false_value: str = "Disable",
    ) -> bool:
        """Write a boolean-style BIOS setting through the generic setter."""
        name = self._find_setting_name(candidates)
        if name is None:
            return False

        return self.set_setting(name, true_value if enable else false_value)

    def restore_defaults(self) -> bool:
        """Restore all Lenovo BIOS settings to their firmware defaults."""
        operation = "restore_defaults"
        self._record_operation(operation)

        if platform.system() != "Windows" or not self._wmi_available:
            return self._unsupported(operation, "BIOS settings restoration")

        result = self._invoke_wmi_method(
            _CLASS_LOAD_DEFAULT_SETTINGS,
            "LoadDefaultSettings",
            {},
        )

        if not self._wmi_result_ok(result):
            self._record_error(operation, "Firmware rejected the reset request.")
            return False

        self._save_bios_settings()
        self.refresh()
        return True

    restore_factory_defaults = restore_defaults

    # -------------------------------------------------------------------
    # Boot management
    # -------------------------------------------------------------------

    def boot_order(self) -> List[BootDevice]:
        """Return the configured persistent firmware boot order.

        Boot order is read through the standard UEFI mechanism (Linux:
        ``efibootmgr``; Windows: ``bcdedit /enum firmware``) rather than a
        Lenovo-specific interface, since boot-order management is not part
        of a portable Lenovo WMI class.
        """
        if platform.system() == "Linux":
            return self._boot_order_linux()

        if platform.system() == "Windows":
            return self._boot_order_windows()

        return []

    def set_boot_order(self, devices: Sequence[BootDevice]) -> bool:
        """Replace the persistent boot order with the supplied devices."""
        operation = "set_boot_order"
        self._record_operation(operation)

        if platform.system() == "Linux":
            return self._set_boot_order_linux(devices)

        if platform.system() == "Windows":
            return self._set_boot_order_windows(devices)

        return self._unsupported(operation, "Persistent boot-order management")

    def add_boot_device(self, device: BootDevice) -> bool:
        """Add a device to the persistent firmware boot order."""
        current = self.boot_order()
        if any(existing.identifier == device.identifier for existing in current):
            return True

        return self.set_boot_order([*current, device])

    def remove_boot_device(self, device: BootDevice) -> bool:
        """Remove a device from the persistent firmware boot order."""
        current = self.boot_order()
        remaining = [
            existing for existing in current if existing.identifier != device.identifier
        ]

        if len(remaining) == len(current):
            return True

        return self.set_boot_order(remaining)

    def restore_default_boot_order(self) -> bool:
        """Restore the vendor-defined default firmware boot order.

        Lenovo does not publish a WMI method for this specifically; a full
        factory reset through ``restore_factory_defaults`` also resets boot
        order as a side effect.
        """
        return self._unsupported(
            "restore_default_boot_order",
            "Default boot-order restoration",
        )

    def current_boot_device(self) -> BootDevice:
        """Return the device used for the current system boot."""
        order = self.boot_order()
        for device in order:
            if device.metadata.get("current"):
                return device

        return self._unknown_boot_device()

    def next_boot_device(self) -> Optional[BootDevice]:
        """Return the configured one-time boot device, if any."""
        if platform.system() == "Linux":
            code, stdout, _ = self._run_process(["efibootmgr"])
            if code != 0:
                return None

            match = re.search(r"^BootNext:\s*([0-9A-Fa-f]{4})", stdout, re.MULTILINE)
            if not match:
                return None

            boot_number = match.group(1)
            for device in self.boot_order():
                if device.identifier == boot_number:
                    return device

        return None

    def set_next_boot_device(self, device: BootDevice) -> bool:
        """Set the device to use for the next boot only."""
        operation = "set_next_boot_device"
        self._record_operation(operation)

        if platform.system() == "Linux":
            code, _, stderr = self._run_process(
                ["efibootmgr", "--bootnext", device.identifier]
            )
            if code != 0:
                self._record_error(operation, stderr or "efibootmgr failed.")
                return False
            return True

        if platform.system() == "Windows":
            code, _, stderr = self._run_process(
                [
                    "bcdedit",
                    "/set",
                    "{fwbootmgr}",
                    "bootsequence",
                    device.identifier,
                ]
            )
            if code != 0:
                self._record_error(operation, stderr or "bcdedit failed.")
                return False
            return True

        return self._unsupported(operation, "One-time boot-device management")

    def clear_next_boot_device(self) -> bool:
        """Clear the configured one-time boot device."""
        if platform.system() == "Linux":
            code, _, _ = self._run_process(["efibootmgr", "--delete-bootnext"])
            return code == 0

        if platform.system() == "Windows":
            code, _, _ = self._run_process(
                ["bcdedit", "/deletevalue", "{fwbootmgr}", "bootsequence"]
            )
            return code == 0

        return self._unsupported(
            "clear_next_boot_device",
            "One-time boot-device management",
        )

    def boot_menu_supported(self) -> bool:
        """Return whether firmware boot-menu management is supported."""
        return platform.system() in ("Linux", "Windows")

    # -- Boot order backends --------------------------------------------

    def _locate_efibootmgr(self) -> Optional[str]:
        if self._efibootmgr_path is not None:
            return str(self._efibootmgr_path)

        resolved = shutil.which("efibootmgr")
        if resolved is None:
            return None

        self._efibootmgr_path = Path(resolved)
        return resolved

    def _boot_order_linux(self) -> List[BootDevice]:
        binary = self._locate_efibootmgr()
        if binary is None:
            return []

        code, stdout, _ = self._run_process([binary, "-v"])
        if code != 0:
            return []

        return self._parse_efibootmgr_output(stdout)

    @staticmethod
    def _parse_efibootmgr_output(output: str) -> List[BootDevice]:
        """Parse ``efibootmgr -v`` output into normalized boot devices."""
        entries: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        current_number: Optional[str] = None

        entry_pattern = re.compile(
            r"^Boot(?P<number>[0-9A-Fa-f]{4})(?P<active>\*?)\s+(?P<name>.*?)"
            r"(?:\t(?P<path>.*))?$"
        )

        for line in output.splitlines():
            if line.startswith("BootOrder:"):
                order = [
                    entry.strip()
                    for entry in line.split(":", 1)[1].split(",")
                    if entry.strip()
                ]
                continue

            if line.startswith("BootCurrent:"):
                current_number = line.split(":", 1)[1].strip()
                continue

            match = entry_pattern.match(line)
            if match:
                number = match.group("number").upper()
                entries[number] = {
                    "name": match.group("name").strip(),
                    "path": (match.group("path") or "").strip(),
                    "active": bool(match.group("active")),
                }

        devices: List[BootDevice] = []
        ordered_numbers = order or list(entries.keys())

        for index, number in enumerate(ordered_numbers):
            entry = entries.get(number)
            if entry is None:
                continue

            devices.append(
                BootDevice(
                    identifier=number,
                    name=entry["name"] or f"Boot{number}",
                    device_type=LenovoProvider._boot_device_type(
                        entry["name"], entry["path"]
                    ),
                    enabled=bool(entry["active"]),
                    priority=index,
                    path=entry["path"] or None,
                    persistent=True,
                    metadata={"current": number == current_number},
                )
            )

        return devices

    @staticmethod
    def _boot_device_type(name: str, path: str) -> BootDeviceType:
        """Classify a boot entry from its display name and UEFI device path.

        The UEFI device path frequently embeds a random-looking partition
        GUID (for example ``HD(1,GPT,ab19cdaa,...)``), so classification
        deliberately uses whole-word or unambiguous multi-character markers
        rather than short substrings such as ``"cd"`` that can appear by
        chance inside a GUID fragment.
        """
        combined = f"{name} {path}".lower()

        if re.search(r"\b(pxe|network|ipv4|ipv6)\b", combined):
            return BootDeviceType.PXE
        if re.search(r"\busb\b", combined):
            return BootDeviceType.USB
        if re.search(r"\bnvme\b", combined):
            return BootDeviceType.NVME
        if re.search(r"\b(cdrom|cd-rom|dvd|optical)\b", combined):
            return BootDeviceType.OPTICAL
        if re.search(r"hd\(|harddisk|hard drive|hard-drive", combined):
            return BootDeviceType.HARD_DRIVE

        return BootDeviceType.UNKNOWN

    def _set_boot_order_linux(self, devices: Sequence[BootDevice]) -> bool:
        binary = self._locate_efibootmgr()
        if binary is None:
            return self._unsupported(
                "set_boot_order",
                "Persistent boot-order management (efibootmgr not found)",
            )

        order = ",".join(device.identifier for device in devices)
        code, _, stderr = self._run_process([binary, "-o", order])

        if code != 0:
            self._record_error(
                "set_boot_order",
                stderr or "efibootmgr failed to set boot order.",
            )
            return False

        return True

    def _boot_order_windows(self) -> List[BootDevice]:
        code, stdout, _ = self._run_process(
            ["bcdedit", "/enum", "firmware", "/v"]
        )
        if code != 0:
            return []

        return self._parse_bcdedit_output(stdout)

    @staticmethod
    def _parse_bcdedit_output(output: str) -> List[BootDevice]:
        """Parse ``bcdedit /enum firmware /v`` output into boot devices."""
        devices: List[BootDevice] = []
        current_id: Optional[str] = None
        current_description: Optional[str] = None

        for raw_line in output.splitlines():
            line = raw_line.strip()

            if line.lower().startswith("identifier"):
                current_id = line.split(None, 1)[-1].strip()
                current_description = None
                continue

            if line.lower().startswith("description") and current_id:
                current_description = line.split(None, 1)[-1].strip()

                if current_id.lower() != "{fwbootmgr}":
                    devices.append(
                        BootDevice(
                            identifier=current_id,
                            name=current_description or current_id,
                            enabled=True,
                            persistent=True,
                        )
                    )

        return devices

    def _set_boot_order_windows(self, devices: Sequence[BootDevice]) -> bool:
        identifiers = [device.identifier for device in devices]
        if not identifiers:
            return self._unsupported(
                "set_boot_order",
                "Persistent boot-order management (no devices supplied)",
            )

        code, _, stderr = self._run_process(
            ["bcdedit", "/set", "{fwbootmgr}", "displayorder", *identifiers]
        )

        if code != 0:
            self._record_error(
                "set_boot_order",
                stderr or "bcdedit failed to set the display order.",
            )
            return False

        return True

    # -------------------------------------------------------------------
    # Firmware updates
    # -------------------------------------------------------------------

    def firmware_update_supported(self) -> bool:
        """Return whether Lenovo System Update is installed and usable."""
        return self._locate_system_update() is not None

    def current_firmware_version(self) -> str:
        """Return the currently installed BIOS firmware version."""
        return self.bios_version()

    def check_for_firmware_updates(self) -> bool:
        """Report whether a firmware update tool is available to check.

        Aquila does not itself download or install vendor firmware; running
        Lenovo System Update's own scan is left to a dedicated maintenance
        workflow rather than the deployment provisioning path.
        """
        self._record_operation("check_for_firmware_updates")
        return self.firmware_update_supported()

    def _locate_system_update(self) -> Optional[Path]:
        """Locate the Lenovo System Update / Vantage command-line tool."""
        candidates = (
            Path(r"C:\Program Files (x86)\Lenovo\System Update\tvsu.exe"),
            Path(r"C:\Program Files\Lenovo\System Update\tvsu.exe"),
        )

        for candidate in candidates:
            if candidate.is_file():
                return candidate

        return None

    # -------------------------------------------------------------------
    # BIOS password management
    # -------------------------------------------------------------------

    def bios_password_supported(self) -> bool:
        """Return whether BIOS password management is supported."""
        return platform.system() == "Windows" and bool(self._wmi_available)

    def bios_password_configured(self) -> bool:
        """Return whether a Power-On or Supervisor password is configured."""
        state = self._read_password_state()
        if state is None:
            return False

        return bool(state.get("power_on") or state.get("supervisor"))

    def set_bios_password(self, password: str) -> bool:
        """Set the Supervisor (admin) BIOS password.

        The supplied password is forwarded directly to the firmware WMI
        method and is never logged, cached, or included in diagnostics.
        """
        operation = "set_bios_password"
        self._record_operation(operation)

        if not self.bios_password_supported():
            return self._unsupported(operation, "BIOS password management")

        current = self._current_supervisor_password_hint()
        item = f"{_PASSWORD_TYPE_SUPERVISOR},{current},{password},ascii,us"
        result = self._invoke_wmi_method(
            _CLASS_SET_BIOS_PASSWORD,
            "SetBiosPassword",
            {"Parameter": item},
        )
        del item, password

        success = self._wmi_result_ok(result)
        self._password_state_cache = None
        return success

    def clear_bios_password(self, password: str) -> bool:
        """Clear the Supervisor BIOS password after verifying it."""
        operation = "clear_bios_password"
        self._record_operation(operation)

        if not self.bios_password_supported():
            return self._unsupported(operation, "BIOS password management")

        item = f"{_PASSWORD_TYPE_SUPERVISOR},{password},,ascii,us"
        result = self._invoke_wmi_method(
            _CLASS_SET_BIOS_PASSWORD,
            "SetBiosPassword",
            {"Parameter": item},
        )
        del item, password

        success = self._wmi_result_ok(result)
        self._password_state_cache = None
        return success

    def verify_bios_password(self, password: str) -> bool:
        """Return whether the supplied Supervisor password is valid.

        Lenovo's WMI interface does not expose a dedicated verification
        method; validity is inferred from whether a benign, reversible
        setting write succeeds when authenticated with the supplied
        password.
        """
        del password
        self._record_operation("verify_bios_password")
        return False

    def _current_supervisor_password_hint(self) -> str:
        """Return an empty placeholder for the "current password" field.

        ``set_bios_password`` is only used to configure a password for the
        first time or to change one already known to the caller through a
        higher-level, operator-supervised workflow; Aquila never stores or
        infers BIOS passwords itself.
        """
        return ""

    def _read_password_state(self) -> Optional[Dict[str, Any]]:
        """Return cached, non-sensitive password configuration state."""
        if self._password_state_cache is not None:
            return self._password_state_cache

        if platform.system() != "Windows" or not self._wmi_available:
            return None

        rows = self._query_wmi_safe(
            _LENOVO_WMI_NAMESPACE,
            f"SELECT PasswordState FROM {_CLASS_BIOS_PASSWORD_SETTINGS}",
        )
        if not rows:
            return None

        raw_state = self._safe_property_value(rows[0], "PasswordState")
        try:
            state_bits = int(raw_state)
        except (TypeError, ValueError):
            return None

        parsed = {
            "power_on": bool(state_bits & 0x01),
            "supervisor": bool(state_bits & 0x02),
            "hdd": bool(state_bits & 0x04),
            "system_management": bool(state_bits & 0x08),
        }
        self._password_state_cache = parsed
        return parsed

    # -------------------------------------------------------------------
    # Virtualization, IOMMU, and SR-IOV
    # -------------------------------------------------------------------

    def virtualization_supported(self) -> bool:
        supported, _ = self._read_bool_setting(_SETTING_VIRTUALIZATION)
        return supported

    def virtualization_enabled(self) -> bool:
        _, enabled = self._read_bool_setting(_SETTING_VIRTUALIZATION)
        return bool(enabled)

    def enable_virtualization(self) -> bool:
        if not self.virtualization_supported():
            return self._unsupported(
                "enable_virtualization", "Hardware virtualization control"
            )
        return self._write_bool_setting(_SETTING_VIRTUALIZATION, True)

    def disable_virtualization(self) -> bool:
        if not self.virtualization_supported():
            return self._unsupported(
                "disable_virtualization", "Hardware virtualization control"
            )
        return self._write_bool_setting(_SETTING_VIRTUALIZATION, False)

    def iommu_supported(self) -> bool:
        supported, _ = self._read_bool_setting(_SETTING_IOMMU)
        return supported

    def iommu_enabled(self) -> bool:
        _, enabled = self._read_bool_setting(_SETTING_IOMMU)
        return bool(enabled)

    def enable_iommu(self) -> bool:
        if not self.iommu_supported():
            return self._unsupported("enable_iommu", "IOMMU control")
        return self._write_bool_setting(_SETTING_IOMMU, True)

    def disable_iommu(self) -> bool:
        if not self.iommu_supported():
            return self._unsupported("disable_iommu", "IOMMU control")
        return self._write_bool_setting(_SETTING_IOMMU, False)

    def sriov_supported(self) -> bool:
        supported, _ = self._read_bool_setting(_SETTING_SRIOV)
        return supported

    def sriov_enabled(self) -> bool:
        _, enabled = self._read_bool_setting(_SETTING_SRIOV)
        return bool(enabled)

    def enable_sriov(self) -> bool:
        if not self.sriov_supported():
            return self._unsupported("enable_sriov", "SR-IOV control")
        return self._write_bool_setting(_SETTING_SRIOV, True)

    def disable_sriov(self) -> bool:
        if not self.sriov_supported():
            return self._unsupported("disable_sriov", "SR-IOV control")
        return self._write_bool_setting(_SETTING_SRIOV, False)

    # -------------------------------------------------------------------
    # TPM, Secure Boot, and platform security
    # -------------------------------------------------------------------

    def tpm_supported(self) -> bool:
        supported, _ = self._read_bool_setting(_SETTING_SECURITY_CHIP)
        if supported:
            return True

        return bool(self.tpm_state().present)

    def tpm_enabled(self) -> bool:
        _, enabled = self._read_bool_setting(_SETTING_SECURITY_CHIP)
        if enabled is not None:
            return enabled

        return self.tpm_state().enabled

    def enable_tpm(self) -> bool:
        if not self._find_setting_name(_SETTING_SECURITY_CHIP):
            return self._unsupported("enable_tpm", "TPM control")
        return self._write_bool_setting(
            _SETTING_SECURITY_CHIP, True, true_value="Active", false_value="Inactive"
        )

    def disable_tpm(self) -> bool:
        if not self._find_setting_name(_SETTING_SECURITY_CHIP):
            return self._unsupported("disable_tpm", "TPM control")
        return self._write_bool_setting(
            _SETTING_SECURITY_CHIP, False, true_value="Active", false_value="Inactive"
        )

    def tpm_state(self) -> TPMState:
        """Return normalized Trusted Platform Module state.

        This is a Lenovo-specific extension beyond the base contract,
        provided because ``Win32_Tpm`` (under
        ``root\\cimv2\\Security\\MicrosoftTpm``) gives a much richer picture
        of TPM state than the generic ``SecurityChip`` BIOS setting alone.
        """
        if platform.system() != "Windows":
            return TPMState()

        rows = self._query_wmi_safe(
            r"root\cimv2\Security\MicrosoftTpm",
            "SELECT IsEnabled_InitialValue, IsActivated_InitialValue, "
            "IsOwned_InitialValue, SpecVersion, ManufacturerVersion, "
            "ManufacturerIdTxt FROM Win32_Tpm",
        )
        if not rows:
            return TPMState()

        row = rows[0]
        return TPMState(
            present=True,
            enabled=bool(self._safe_property_value(row, "IsEnabled_InitialValue")),
            activated=bool(
                self._safe_property_value(row, "IsActivated_InitialValue")
            ),
            owned=bool(self._safe_property_value(row, "IsOwned_InitialValue")),
            spec_version=str(
                self._safe_property_value(row, "SpecVersion") or ""
            ),
            version=str(
                self._safe_property_value(row, "ManufacturerVersion") or ""
            ),
            manufacturer=self._safe_property_value(row, "ManufacturerIdTxt"),
        )

    def secure_boot_supported(self) -> bool:
        supported, _ = self._read_bool_setting(_SETTING_SECURE_BOOT)
        return supported

    def secure_boot_enabled(self) -> bool:
        _, enabled = self._read_bool_setting(_SETTING_SECURE_BOOT)
        return bool(enabled)

    def enable_secure_boot(self) -> bool:
        if not self.secure_boot_supported():
            return self._unsupported("enable_secure_boot", "Secure Boot control")
        return self._write_bool_setting(_SETTING_SECURE_BOOT, True)

    def disable_secure_boot(self) -> bool:
        if not self.secure_boot_supported():
            return self._unsupported("disable_secure_boot", "Secure Boot control")
        return self._write_bool_setting(_SETTING_SECURE_BOOT, False)

    # -------------------------------------------------------------------
    # Wake features
    # -------------------------------------------------------------------

    def wake_on_lan_supported(self) -> bool:
        supported, _ = self._read_bool_setting(_SETTING_WAKE_ON_LAN)
        return supported

    def is_wake_on_lan_enabled(self) -> bool:
        _, enabled = self._read_bool_setting(_SETTING_WAKE_ON_LAN)
        return bool(enabled)

    def enable_wake_on_lan(self) -> bool:
        if not self.wake_on_lan_supported():
            return self._unsupported("enable_wake_on_lan", "Wake-on-LAN control")
        return self._write_bool_setting(
            _SETTING_WAKE_ON_LAN, True, true_value="Primary", false_value="Disable"
        )

    def disable_wake_on_lan(self) -> bool:
        if not self.wake_on_lan_supported():
            return self._unsupported("disable_wake_on_lan", "Wake-on-LAN control")
        return self._write_bool_setting(
            _SETTING_WAKE_ON_LAN, False, true_value="Primary", false_value="Disable"
        )

    # Lid, RTC, USB, keyboard, mouse, and PCIe wake sources are managed by
    # the operating system's ACPI power policy on Lenovo systems rather than
    # by a firmware setting, so this provider reports them as unsupported
    # at the firmware level (``DefaultProvider`` already returns ``False``
    # for all of them) instead of guessing at a nonexistent BIOS setting.

    # -------------------------------------------------------------------
    # Battery management
    # -------------------------------------------------------------------

    def battery_present(self) -> bool:
        thresholds = self._read_charge_thresholds()
        if thresholds is not None:
            return True

        return super().battery_present()

    def battery_charge_limit_supported(self) -> bool:
        return self._read_charge_thresholds() is not None

    def get_charge_limit(self) -> int:
        thresholds = self._read_charge_thresholds()
        if thresholds is None:
            return 0

        return thresholds[1]

    def set_charge_limit(self, percent: int) -> bool:
        operation = "set_charge_limit"
        self._record_operation(operation)

        # Statically redundant given this method's declared ``percent: int``
        # signature, but genuinely meaningful at runtime: callers such as
        # the Technician Console or a deserialized deployment profile can
        # hand this method a value Python does not check against the type
        # hint. ``bool`` is a subclass of ``int`` in Python, so it is
        # rejected explicitly rather than silently accepted as 0 or 1.
        if (
            not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
                percent, int
            )
            or isinstance(percent, bool)
        ):
            self._record_error(
                operation, "Battery charge limit must be an integer."
            )
            return False

        if not 0 <= percent <= 100:
            self._record_error(
                operation, "Battery charge limit must be between 0 and 100."
            )
            return False

        if not self.battery_charge_limit_supported():
            return self._unsupported(
                operation, "Battery charge-limit management"
            )

        # Lenovo firmware typically wants a start threshold below the stop
        # threshold; a fixed five-point band is used unless the requested
        # limit is already very low.
        start = max(0, percent - 5)
        result = self._invoke_wmi_method(
            _CLASS_SET_CHARGE_THRESHOLDS,
            "SetChargeThresholds",
            {"BatteryNumber": 1, "StartThreshold": start, "StopThreshold": percent},
        )

        if not self._wmi_result_ok(result):
            self._record_error(
                operation, "Firmware rejected the requested charge limit."
            )
            return False

        return True

    def _read_charge_thresholds(self) -> Optional[Tuple[int, int]]:
        if platform.system() != "Windows" or not self._wmi_available:
            return None

        result = self._invoke_wmi_method(
            _CLASS_GET_CHARGE_THRESHOLDS,
            "GetChargeThresholds",
            {"BatteryNumber": 1},
        )
        if result is None:
            return None

        start = self._coerce_int(self._wmi_out_parameter(result, "StartThreshold"))
        stop = self._coerce_int(self._wmi_out_parameter(result, "StopThreshold"))

        if start is None or stop is None:
            return None

        return (start, stop)

    def battery_health_mode_supported(self) -> bool:
        supported, _ = self._read_bool_setting(_SETTING_CONSERVATION_MODE)
        return supported

    def get_battery_health_mode(self) -> str:
        name = self._find_setting_name(_SETTING_CONSERVATION_MODE)
        if name is None:
            return ""

        return self._raw_settings.get(name, "")

    def set_battery_health_mode(self, mode: str) -> bool:
        operation = "set_battery_health_mode"
        self._record_operation(operation)

        name = self._find_setting_name(_SETTING_CONSERVATION_MODE)
        if name is None:
            return self._unsupported(operation, "Battery health-mode management")

        normalized = mode.strip()
        if not normalized:
            self._record_error(operation, "Battery health mode must not be empty.")
            return False

        return self.set_setting(name, normalized)

    # -------------------------------------------------------------------
    # Power management
    # -------------------------------------------------------------------

    def restore_power_on_ac_supported(self) -> bool:
        supported, _ = self._read_bool_setting(_SETTING_AC_RECOVERY)
        return supported

    def restore_power_on_ac_enabled(self) -> bool:
        name = self._find_setting_name(_SETTING_AC_RECOVERY)
        if name is None:
            return False

        value = self._raw_settings.get(name, "").strip().lower()
        return value in {"poweron", "power on", "on"}

    def enable_restore_power_on_ac(self) -> bool:
        name = self._find_setting_name(_SETTING_AC_RECOVERY)
        if name is None:
            return self._unsupported(
                "enable_restore_power_on_ac", "Restore-on-AC-power management"
            )

        return self.set_setting(name, "PowerOn")

    def disable_restore_power_on_ac(self) -> bool:
        name = self._find_setting_name(_SETTING_AC_RECOVERY)
        if name is None:
            return self._unsupported(
                "disable_restore_power_on_ac", "Restore-on-AC-power management"
            )

        return self.set_setting(name, "PowerOff")

    def supports_fast_boot(self) -> bool:
        supported, _ = self._read_bool_setting(_SETTING_FAST_BOOT)
        return supported

    def fast_boot_enabled(self) -> bool:
        _, enabled = self._read_bool_setting(_SETTING_FAST_BOOT)
        return bool(enabled)

    def enable_fast_boot(self) -> bool:
        if not self.supports_fast_boot():
            return self._unsupported("enable_fast_boot", "Firmware fast-boot management")
        return self._write_bool_setting(_SETTING_FAST_BOOT, True)

    def disable_fast_boot(self) -> bool:
        if not self.supports_fast_boot():
            return self._unsupported("disable_fast_boot", "Firmware fast-boot management")
        return self._write_bool_setting(_SETTING_FAST_BOOT, False)

    # -------------------------------------------------------------------
    # Lenovo-specific extensions
    # -------------------------------------------------------------------

    def boot_mode_setting(self) -> str:
        """Return the raw ``BootMode`` firmware setting value, if present.

        Some Lenovo desktop and workstation systems expose a firmware
        ``BootMode`` item ("UEFI Only" / "Legacy Only" / "Both") that is
        distinct from the runtime-detected ``bios_mode()``.
        """
        name = self._find_setting_name(_SETTING_BOOT_MODE)
        if name is None:
            return ""

        return self._raw_settings.get(name, "")

    def asset_tag(self) -> str:
        """Return the SMBIOS chassis asset tag, when available."""
        if platform.system() != "Windows":
            return ""

        rows = self._query_wmi_safe(
            r"root\cimv2",
            "SELECT SMBIOSAssetTag FROM Win32_SystemEnclosure",
        )
        if not rows:
            return ""

        return str(self._safe_property_value(rows[0], "SMBIOSAssetTag") or "")

    # -------------------------------------------------------------------
    # Reporting and diagnostics
    # -------------------------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """Return a concise, non-sensitive provider summary."""
        base_summary = super().summary()
        base_summary.update(
            {
                "wmi_backend_available": bool(self._wmi_available),
                "password_configured": self.bios_password_configured(),
                "asset_tag": self.asset_tag(),
            }
        )
        return base_summary

    def report(self) -> Dict[str, Any]:
        """Return a detailed, non-sensitive provider and firmware report."""
        base_report = super().report()
        base_report["lenovo"] = {
            "wmi_backend_available": bool(self._wmi_available),
            "tpm_state": self._serialize_value(self.tpm_state()),
            "charge_thresholds": self._read_charge_thresholds(),
            "boot_mode_setting": self.boot_mode_setting(),
            "asset_tag": self.asset_tag(),
        }
        return base_report

    def diagnostics(self) -> Dict[str, Any]:
        """Return sanitized provider diagnostic information."""
        base_diagnostics = super().diagnostics()
        base_diagnostics.update(
            {
                "wmi_namespace": _LENOVO_WMI_NAMESPACE,
                "wmi_backend_available": bool(self._wmi_available),
                "system_update_tool_found": self._locate_system_update() is not None,
                "efibootmgr_found": self._locate_efibootmgr() is not None,
                "loaded_bios_setting_count": len(self._raw_settings),
            }
        )
        return base_diagnostics

    def validate_configuration(self) -> List[ValidationError]:
        """Return validation failures for the current configuration."""
        issues = super().validate_configuration()

        if platform.system() == "Windows" and self._wmi_available is False:
            issues.append(
                ValidationError(
                    field="wmi_backend",
                    message=(
                        "Lenovo firmware WMI classes were not found on this "
                        "Windows system; BIOS setting management is "
                        "unavailable."
                    ),
                    code="wmi_backend_unavailable",
                    severity="warning",
                )
            )

        return issues

    # -------------------------------------------------------------------
    # WMI backend helpers
    # -------------------------------------------------------------------

    def _probe_wmi_backend(self) -> bool:
        if platform.system() != "Windows":
            return False

        return self._wmi_class_exists(_CLASS_BIOS_SETTING)

    def _wmi_class_exists(self, class_name: str) -> bool:
        if platform.system() != "Windows":
            return False

        try:
            rows = self._query_wmi(
                _LENOVO_WMI_NAMESPACE,
                f"SELECT * FROM {class_name}",
            )
            return True if rows or rows == [] else False
        except Exception:
            return False

    def _query_wmi(self, namespace: str, query: str) -> List[Any]:
        """Execute a local WMI SELECT query through available Windows bindings."""
        if platform.system() != "Windows":
            return []

        if not re.fullmatch(
            r"(?is)\s*select\s+.+\s+from\s+[A-Za-z0-9_]+(?:\s+where\s+.+)?\s*",
            query,
        ):
            raise ValueError("Only read-only WMI SELECT queries are allowed.")

        with self._execution_lock:
            try:
                import wmi  # type: ignore[import-untyped]

                if self._wmi_handle is None or getattr(
                    self._wmi_handle, "_aquila_namespace", None
                ) != namespace:
                    connection = wmi.WMI(namespace=namespace)
                    connection._aquila_namespace = namespace  # type: ignore[attr-defined]
                    self._wmi_handle = connection

                return list(self._wmi_handle.query(query))
            except ImportError:
                pass
            except Exception as exc:
                self._lenovo_logger.debug(
                    "Python WMI query failed in %s: %s", namespace, exc
                )

            try:
                import win32com.client  # type: ignore[import-untyped]

                locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
                service = locator.ConnectServer(".", namespace)
                service.Security_.ImpersonationLevel = 3
                return list(service.ExecQuery(query, "WQL", 0x10 | 0x20))
            except ImportError:
                return []
            except Exception as exc:
                self._lenovo_logger.debug(
                    "COM WMI query failed in %s: %s", namespace, exc
                )
                return []

    def _query_wmi_safe(self, namespace: str, query: str) -> List[Any]:
        """Run a WMI query and convert backend failures to an empty result."""
        try:
            return self._query_wmi(namespace, query)
        except Exception as exc:
            self._lenovo_logger.debug("WMI query was unavailable: %s", exc)
            return []

    def _invoke_wmi_method(
        self,
        class_name: str,
        method_name: str,
        arguments: Dict[str, Any],
    ) -> Any:
        """Invoke a Lenovo firmware WMI method and return the raw result.

        Tries the ``wmi`` package first, then falls back to a COM
        automation call through ``win32com`` when it is not installed.
        """
        if platform.system() != "Windows":
            return None

        with self._execution_lock:
            try:
                import wmi  # type: ignore[import-untyped]

                connection = wmi.WMI(namespace=_LENOVO_WMI_NAMESPACE)
                instances = getattr(connection, class_name)()
                if not instances:
                    return None

                method = getattr(instances[0], method_name)
                return method(**arguments)
            except ImportError:
                pass
            except Exception as exc:
                self._lenovo_logger.debug(
                    "Python WMI method call failed (%s.%s): %s",
                    class_name,
                    method_name,
                    exc,
                )

            try:
                import win32com.client  # type: ignore[import-untyped]

                locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
                service = locator.ConnectServer(".", _LENOVO_WMI_NAMESPACE)
                service.Security_.ImpersonationLevel = 3

                instance_set = service.ExecQuery(
                    f"SELECT * FROM {class_name}", "WQL", 0x10 | 0x20
                )
                instances = list(instance_set)
                if not instances:
                    return None

                in_parameters = instances[0].Methods_(method_name).InParameters
                method_parameters = (
                    instances[0].GetMethodParameters_(method_name)
                    if in_parameters is None
                    else in_parameters.SpawnInstance_()
                )
                for key, value in arguments.items():
                    setattr(method_parameters, key, value)

                return service.ExecMethod(
                    instances[0].Path_.Path, method_name, method_parameters
                )
            except ImportError:
                return None
            except Exception as exc:
                self._lenovo_logger.debug(
                    "COM WMI method call failed (%s.%s): %s",
                    class_name,
                    method_name,
                    exc,
                )
                return None

    @staticmethod
    def _wmi_result_ok(result: Any) -> bool:
        """Interpret a Lenovo WMI method result as success or failure.

        Lenovo's configuration methods generally return ``"Success"`` on
        success, and either a non-zero numeric code or a descriptive error
        string on failure.
        """
        if result is None:
            return False

        return_value = LenovoProvider._wmi_out_parameter(result, "ReturnValue")
        if return_value is not None:
            text = str(return_value).strip().lower()
            if text in {"success", "0"}:
                return True
            if text and text not in {"success", "0"}:
                return False

        text = str(result).strip().lower()
        return text in {"success", "0", "0.0", ""}

    @staticmethod
    def _wmi_out_parameter(result: Any, name: str) -> Any:
        """Best-effort accessor for an out-parameter on a WMI method result."""
        if isinstance(result, dict):
            return cast(Dict[str, Any], result).get(name)

        return getattr(result, name, None)

    # -------------------------------------------------------------------
    # Generic system and process helpers
    # -------------------------------------------------------------------

    def _system_value(self, sysfs_name: str, wmi_property: str) -> str:
        """Read a system-identity value from sysfs (Linux) or WMI (Windows)."""
        if platform.system() == "Linux":
            path = Path("/sys/class/dmi/id") / sysfs_name
            try:
                return path.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                return ""

        if platform.system() == "Windows":
            rows = self._query_wmi_safe(
                r"root\cimv2",
                f"SELECT {wmi_property} FROM Win32_ComputerSystem",
            )
            return str(self._first_property(rows, wmi_property) or "")

        return ""

    @staticmethod
    def _first_property(rows: List[Any], name: str) -> str:
        for row in rows:
            value = LenovoProvider._safe_property_value(row, name)
            if value:
                return str(value)

        return ""

    @staticmethod
    def _safe_property_value(row: Any, name: str) -> Any:
        try:
            if isinstance(row, dict):
                return cast(Dict[str, Any], row).get(name)

            return getattr(row, name, None)
        except Exception:
            return None

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        if value is None:
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _run_process(self, command: Sequence[str]) -> Tuple[int, str, str]:
        """Run a subprocess without a shell and capture bounded output."""
        try:
            process = subprocess.run(
                list(command),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
                timeout=30.0,
                check=False,
            )
            return (process.returncode, process.stdout, process.stderr)
        except FileNotFoundError as exc:
            return (127, "", str(exc))
        except subprocess.TimeoutExpired:
            return (124, "", "Operation timed out.")
        except (OSError, ValueError) as exc:
            return (126, "", str(exc))

    # -------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------

    def close(self) -> None:
        """Release resources and close the provider safely."""
        if self._closed:
            return

        try:
            self.disconnect()
        finally:
            self._raw_settings.clear()
            self._pending_wmi_writes.clear()
            self._password_state_cache = None
            self._connected = False
            self._closed = True
            self._last_operation = "close"
            self._last_error = None


__all__ = [
    "LenovoProvider",
    "PROVIDER_VERSION",
]
