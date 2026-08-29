"""HP BIOS provider for Project Aquila.

Backend preference:

1. HP's firmware WMI interface exposed under ``root\\hp\\instrumentedBIOS``
   on Windows (``HP_BIOSSetting`` for reading every exposed setting,
   ``HP_BIOSSettingInterface.SetBIOSSetting(Name, Value, Password)`` for
   writing, and ``HP_BIOSPassword`` for password configuration state). This
   interface is documented in HP's "BIOS Settings via WMI" client-management
   reference and is present on essentially every commercial HP system
   (EliteBook, ProBook, ZBook, EliteDesk, ProDesk, Z-series workstations).
2. Standard UEFI firmware variables (``efibootmgr`` on Linux,
   ``bcdedit /enum firmware`` on Windows) for boot-order management, for the
   same reason the Lenovo provider uses them: boot order is a
   platform-standard UEFI mechanism, not a vendor-specific one.
3. Native operating-system firmware identity interfaces (Win32_BIOS /
   Win32_ComputerSystem on Windows, ``/sys/class/dmi/id`` on Linux via
   ``DefaultProvider``).
4. ``DefaultProvider`` fallback behavior for anything this provider cannot
   confidently support (HP does not expose a numeric battery charge-limit
   percentage on most models the way Dell and Lenovo do, for example).

Settings that require authentication (most do, once a Setup Password is
configured) must have their ``Value`` and ``Password`` arguments prefixed
with the literal string ``<utf-16/>`` per HP's documented WMI scripting
convention; ``_encode_password`` centralizes that so no BIOS password is
ever logged, cached beyond the duration of a single call, or included in
any exported report, summary, or diagnostic payload.
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
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

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

_HP_WMI_NAMESPACE = r"root\hp\instrumentedBIOS"

_CLASS_BIOS_SETTING = "HP_BIOSSetting"
_CLASS_BIOS_SETTING_INTERFACE = "HP_BIOSSettingInterface"
_CLASS_BIOS_PASSWORD = "HP_BIOSPassword"

_UTF16_PASSWORD_PREFIX = "<utf-16/>"

_PASSWORD_NAME_SETUP = "Setup Password"
_PASSWORD_NAME_POWER_ON = "Power-On Password"

_TRUE_VALUES: Set[str] = {
    "1",
    "active",
    "enable",
    "enabled",
    "on",
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

# HP setting item names vary by model family; every capability is matched
# against a short candidate list rather than a single hard-coded string.
_SETTING_VIRTUALIZATION: Tuple[str, ...] = (
    "Virtualization Technology (VTx)",
    "Virtualization Technology",
    "VTx",
)
_SETTING_IOMMU: Tuple[str, ...] = (
    "Virtualization Technology for Directed I/O (VTd)",
    "Virtualization Technology for Directed I/O",
    "VTd",
)
_SETTING_SRIOV: Tuple[str, ...] = (
    "SR-IOV Support",
    "SR-IOV",
)
_SETTING_SECURE_BOOT: Tuple[str, ...] = (
    "Secure Boot",
)
_SETTING_TPM_ACTIVATION: Tuple[str, ...] = (
    "TPM State",
    "TPM Device",
    "Embedded Security Device Availability",
)
_SETTING_WAKE_ON_LAN: Tuple[str, ...] = (
    "Wake On LAN",
    "S5 Wake on LAN",
    "Remote Wakeup Boot Source",
)
_SETTING_AC_RECOVERY: Tuple[str, ...] = (
    "After Power Loss",
    "AC Power Recovery",
    "Power Loss Recovery",
)
_SETTING_FAST_BOOT: Tuple[str, ...] = (
    "Fast Boot",
)
_SETTING_BATTERY_HEALTH: Tuple[str, ...] = (
    "Battery Health Manager",
)

logger = logging.getLogger(__name__)


class HPProvider(DefaultProvider):
    """Production HP firmware provider.

    Supports EliteBook, ProBook, ZBook, EliteDesk, ProDesk, and Z-series
    workstation systems that expose HP's standard firmware WMI interface on
    Windows. On Linux, and on Windows systems where that interface is
    unavailable, this provider degrades to ``DefaultProvider`` behavior for
    settings it cannot reach, while still using standard UEFI mechanisms for
    boot-order management.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize provider state without opening privileged resources."""
        super().__init__(*args, **kwargs)
        self._hp_logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._execution_lock = threading.RLock()
        self._wmi_handle: Any = None
        self._wmi_available: Optional[bool] = None
        self._raw_settings: Dict[str, str] = {}
        self._password_state_cache: Optional[Dict[str, bool]] = None
        self._efibootmgr_path: Optional[Path] = None
        self._connected = False
        self._closed = False

    # -------------------------------------------------------------------
    # Identity, detection, and lifecycle
    # -------------------------------------------------------------------

    def vendor(self) -> BIOSVendor:
        """Return the HP vendor identifier."""
        return BIOSVendor.HP

    def provider_name(self) -> str:
        """Return the stable provider name."""
        return "hp"

    def provider_version(self) -> str:
        """Return the HP provider implementation version."""
        return PROVIDER_VERSION

    def supports_windows(self) -> bool:
        """Return whether this provider supports Windows hosts."""
        return True

    def supports_linux(self) -> bool:
        """Return whether this provider supports Linux hosts.

        Linux support is limited to firmware identity and boot-order
        management through standard UEFI mechanisms. HP's WMI-based
        settings backend is Windows-only.
        """
        return True

    def detect(self) -> bool:
        """Return whether this system is confidently identified as HP."""
        return self.detection_confidence() >= 0.7

    def detection_confidence(self) -> float:
        """Calculate a confidence score from independent HP indicators."""
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

        if normalized_vendor in {"hp", "hp inc", "hewlett packard", "hewlett-packard", "hewlett packard enterprise", "hpe"}:
            score += 0.55
        elif "hewlett" in normalized_vendor or re.search(r"\bhp\b", normalized_vendor):
            score += 0.45

        if re.search(
            r"\b(elitebook|probook|zbook|elitedesk|prodesk|elite\s?desk|"
            r"z2|z4|z6|z8|omen|spectre|envy)\b",
            combined,
        ):
            score += 0.15

        if self._wmi_class_exists(_CLASS_BIOS_SETTING):
            score += 0.20

        return min(score, 1.0)

    def connect(self) -> bool:
        """Establish the HP firmware backend and load current settings."""
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
                    "connect", f"Provider initialization failed: {exc}"
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
            self._password_state_cache = None

    def is_connected(self) -> bool:
        """Return whether the provider is connected and ready."""
        return self._connected

    def refresh(self) -> bool:
        """Refresh cached firmware information and HP BIOS settings."""
        with self._execution_lock:
            self._record_operation("refresh")

            try:
                self._firmware = self._collect_firmware_information()
                self._cache_valid = True
            except Exception as exc:
                self._cache_valid = False
                self._record_error(
                    "refresh", f"Unable to refresh firmware information: {exc}"
                )
                return False

            if self._wmi_available:
                try:
                    self._load_bios_settings()
                except Exception:
                    self._hp_logger.debug(
                        "Unable to load HP BIOS settings.", exc_info=True
                    )

            return True

    def firmware_interface(self) -> str:
        """Return the firmware-management interface used by the provider."""
        if platform.system() == "Windows" and self._wmi_available:
            return f"wmi:{_HP_WMI_NAMESPACE}"

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

        manufacturer = self._first_property(system_rows, "Manufacturer") or "HP"
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
            vendor=BIOSVendor.HP,
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
            firmware_type = HPProvider._windows_firmware_type()
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
        """Return the Windows ``FIRMWARE_TYPE`` value when it can be read."""
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
        """Load every HP BIOS setting and register it for the generic API.

        Each ``HP_BIOSSetting`` instance exposes ``Name`` and ``Value``
        properties directly (unlike Lenovo's combined ``CurrentSetting``
        string), along with ``IsReadOnly``. Settings are registered through
        ``DefaultProvider._register_setting`` so the inherited
        ``available_settings`` / ``get_setting`` / ``set_setting`` /
        ``reset_setting`` / ``restore_defaults`` methods work without
        HP-specific overrides.
        """
        rows = self._query_wmi_safe(
            _HP_WMI_NAMESPACE,
            f"SELECT Name, Value, IsReadOnly FROM {_CLASS_BIOS_SETTING}",
        )

        self._raw_settings.clear()

        for row in rows:
            name = self._safe_property_value(row, "Name")
            value = self._safe_property_value(row, "Value")
            read_only = bool(self._safe_property_value(row, "IsReadOnly"))

            if not name:
                continue

            name = str(name)
            value = "" if value is None else str(value)

            self._raw_settings[name] = value
            self._register_setting(
                name,
                value,
                default=None,
                writable=not read_only,
                reboot_required=True,
            )

    def _apply_setting(self, name: str, value: Any) -> bool:
        """Apply a setting through ``HP_BIOSSettingInterface.SetBIOSSetting``."""
        if platform.system() != "Windows" or not self._wmi_available:
            return False

        password = self._encode_password_argument(
            self._current_setup_password_hint()
        )
        encoded_value = self._maybe_encode_value(str(value))

        result = self._invoke_wmi_method(
            _CLASS_BIOS_SETTING_INTERFACE,
            "SetBIOSSetting",
            {"Name": name, "Value": encoded_value, "Password": password},
        )
        del password

        if not self._wmi_result_ok(result):
            return False

        self._raw_settings[name] = str(value)
        return True

    def _current_setup_password_hint(self) -> str:
        """Return an empty placeholder for the "current password" argument.

        Aquila never stores or infers BIOS passwords itself; if a Setup
        Password is configured, applying a protected setting must be done
        through a higher-level, operator-supervised workflow that supplies
        the current password explicitly.
        """
        return ""

    @staticmethod
    def _encode_password_argument(password: str) -> str:
        """Encode a password argument using HP's documented UTF-16 prefix."""
        if not password:
            return ""

        return f"{_UTF16_PASSWORD_PREFIX}{password}"

    def _maybe_encode_value(self, value: str) -> str:
        """Return a setting value, UTF-16-prefixed only if a Setup Password
        is configured, per HP's WMI scripting convention for protected
        settings.
        """
        state = self._read_password_state()
        if state and state.get("setup"):
            return f"{_UTF16_PASSWORD_PREFIX}{value}"

        return value

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

    def _read_bool_setting(
        self, candidates: Sequence[str]
    ) -> Tuple[bool, Optional[bool]]:
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

    # HP does not publish a documented WMI "load factory defaults" method,
    # so ``restore_defaults()``/``restore_factory_defaults()`` fall back to
    # ``DefaultProvider``'s honest unsupported behavior rather than guessing
    # at an undocumented mechanism.

    # -------------------------------------------------------------------
    # Boot management
    # -------------------------------------------------------------------

    def boot_order(self) -> List[BootDevice]:
        """Return the configured persistent firmware boot order.

        Boot order is read through the standard UEFI mechanism (Linux:
        ``efibootmgr``; Windows: ``bcdedit /enum firmware``) rather than a
        vendor-specific interface, since boot-order management is not part
        of a portable HP WMI class.
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
        """Restore the vendor-defined default firmware boot order."""
        return self._unsupported(
            "restore_default_boot_order", "Default boot-order restoration"
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
                ["bcdedit", "/set", "{fwbootmgr}", "bootsequence", device.identifier]
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
            "clear_next_boot_device", "One-time boot-device management"
        )

    def boot_menu_supported(self) -> bool:
        """Return whether firmware boot-menu management is supported."""
        return platform.system() in ("Linux", "Windows")

    # -- Boot order backends (standard UEFI, vendor-neutral) -------------

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
                    device_type=HPProvider._boot_device_type(
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
        GUID, so classification uses whole-word or unambiguous
        multi-character markers rather than short substrings that can
        appear by chance inside a GUID fragment.
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
                "set_boot_order", stderr or "efibootmgr failed to set boot order."
            )
            return False

        return True

    def _boot_order_windows(self) -> List[BootDevice]:
        code, stdout, _ = self._run_process(["bcdedit", "/enum", "firmware", "/v"])
        if code != 0:
            return []

        return self._parse_bcdedit_output(stdout)

    @staticmethod
    def _parse_bcdedit_output(output: str) -> List[BootDevice]:
        """Parse ``bcdedit /enum firmware /v`` output into boot devices."""
        devices: List[BootDevice] = []
        current_id: Optional[str] = None

        for raw_line in output.splitlines():
            line = raw_line.strip()

            if line.lower().startswith("identifier"):
                current_id = line.split(None, 1)[-1].strip()
                continue

            if line.lower().startswith("description") and current_id:
                description = line.split(None, 1)[-1].strip()

                if current_id.lower() != "{fwbootmgr}":
                    devices.append(
                        BootDevice(
                            identifier=current_id,
                            name=description or current_id,
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
                "set_boot_order", stderr or "bcdedit failed to set the display order."
            )
            return False

        return True

    # -------------------------------------------------------------------
    # Firmware updates
    # -------------------------------------------------------------------

    def firmware_update_supported(self) -> bool:
        """Return whether HP Image Assistant is installed and usable.

        Confidence is moderate: HP's exact CLI invocation for a scripted
        firmware check varies by HPIA release, so this only reports
        *availability* of the tool rather than attempting to invoke it.
        """
        return self._locate_hp_image_assistant() is not None

    def current_firmware_version(self) -> str:
        """Return the currently installed BIOS firmware version."""
        return self.bios_version()

    def check_for_firmware_updates(self) -> bool:
        """Report whether a firmware update tool is available to check.

        Aquila does not itself download or install vendor firmware; running
        HP Image Assistant's own scan is left to a dedicated maintenance
        workflow rather than the deployment provisioning path.
        """
        self._record_operation("check_for_firmware_updates")
        return self.firmware_update_supported()

    def _locate_hp_image_assistant(self) -> Optional[Path]:
        """Locate HP Image Assistant, when installed."""
        candidates = (
            Path(r"C:\Program Files\HP\HPIA\HPImageAssistant.exe"),
            Path(r"C:\SWSetup\HPIA\HPImageAssistant.exe"),
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
        """Return whether a Setup or Power-On password is configured."""
        state = self._read_password_state()
        if state is None:
            return False

        return bool(state.get("setup") or state.get("power_on"))

    def set_bios_password(self, password: str) -> bool:
        """Set the Setup (admin) BIOS password.

        The supplied password is forwarded directly to the firmware WMI
        method and is never logged, cached, or included in diagnostics.
        """
        operation = "set_bios_password"
        self._record_operation(operation)

        if not self.bios_password_supported():
            return self._unsupported(operation, "BIOS password management")

        current = self._encode_password_argument(
            self._current_setup_password_hint()
        )
        new_value = self._encode_password_argument(password)

        result = self._invoke_wmi_method(
            _CLASS_BIOS_SETTING_INTERFACE,
            "SetBIOSSetting",
            {
                "Name": _PASSWORD_NAME_SETUP,
                "Value": new_value,
                "Password": current,
            },
        )
        del current, new_value, password

        success = self._wmi_result_ok(result)
        self._password_state_cache = None
        return success

    def clear_bios_password(self, password: str) -> bool:
        """Clear the Setup BIOS password after verifying it."""
        operation = "clear_bios_password"
        self._record_operation(operation)

        if not self.bios_password_supported():
            return self._unsupported(operation, "BIOS password management")

        current = self._encode_password_argument(password)

        result = self._invoke_wmi_method(
            _CLASS_BIOS_SETTING_INTERFACE,
            "SetBIOSSetting",
            {"Name": _PASSWORD_NAME_SETUP, "Value": "", "Password": current},
        )
        del current, password

        success = self._wmi_result_ok(result)
        self._password_state_cache = None
        return success

    def verify_bios_password(self, password: str) -> bool:
        """Return whether the supplied Setup password is valid.

        HP's WMI interface does not expose a dedicated verification
        method; validity would need to be inferred from whether an
        authenticated, reversible setting write succeeds, which this
        provider deliberately does not attempt automatically.
        """
        del password
        self._record_operation("verify_bios_password")
        return False

    def _read_password_state(self) -> Optional[Dict[str, bool]]:
        """Return cached, non-sensitive password configuration state."""
        if self._password_state_cache is not None:
            return self._password_state_cache

        if platform.system() != "Windows" or not self._wmi_available:
            return None

        rows = self._query_wmi_safe(
            _HP_WMI_NAMESPACE, f"SELECT Name, IsSet FROM {_CLASS_BIOS_PASSWORD}"
        )
        if not rows:
            return None

        parsed = {"setup": False, "power_on": False}
        for row in rows:
            name = str(self._safe_property_value(row, "Name") or "")
            is_set = bool(self._safe_property_value(row, "IsSet"))

            if name == _PASSWORD_NAME_SETUP:
                parsed["setup"] = is_set
            elif name == _PASSWORD_NAME_POWER_ON:
                parsed["power_on"] = is_set

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
        supported, _ = self._read_bool_setting(_SETTING_TPM_ACTIVATION)
        if supported:
            return True

        return bool(self.tpm_state().present)

    def tpm_enabled(self) -> bool:
        _, enabled = self._read_bool_setting(_SETTING_TPM_ACTIVATION)
        if enabled is not None:
            return enabled

        return self.tpm_state().enabled

    def enable_tpm(self) -> bool:
        if not self._find_setting_name(_SETTING_TPM_ACTIVATION):
            return self._unsupported("enable_tpm", "TPM control")
        return self._write_bool_setting(_SETTING_TPM_ACTIVATION, True)

    def disable_tpm(self) -> bool:
        if not self._find_setting_name(_SETTING_TPM_ACTIVATION):
            return self._unsupported("disable_tpm", "TPM control")
        return self._write_bool_setting(_SETTING_TPM_ACTIVATION, False)

    def tpm_state(self) -> TPMState:
        """Return normalized Trusted Platform Module state.

        This is a provider-specific extension beyond the base contract,
        provided because ``Win32_Tpm`` (under
        ``root\\cimv2\\Security\\MicrosoftTpm``) gives a much richer picture
        of TPM state than the generic firmware TPM setting alone.
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
            spec_version=str(self._safe_property_value(row, "SpecVersion") or ""),
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
        return self._write_bool_setting(_SETTING_WAKE_ON_LAN, True)

    def disable_wake_on_lan(self) -> bool:
        if not self.wake_on_lan_supported():
            return self._unsupported("disable_wake_on_lan", "Wake-on-LAN control")
        return self._write_bool_setting(_SETTING_WAKE_ON_LAN, False)

    # Lid, RTC, USB, keyboard, mouse, and PCIe wake sources are managed by
    # the operating system's ACPI power policy on HP systems rather than by
    # a firmware setting, so this provider reports them as unsupported at
    # the firmware level (``DefaultProvider`` already returns ``False`` for
    # all of them) instead of guessing at a nonexistent BIOS setting.

    # -------------------------------------------------------------------
    # Battery management
    # -------------------------------------------------------------------

    # HP does not expose a numeric battery charge-limit percentage on most
    # commercial models the way Dell and Lenovo do; charge behavior is
    # instead controlled through the "Battery Health Manager" mode below.
    # ``battery_charge_limit_supported`` therefore correctly falls back to
    # ``DefaultProvider``'s honest ``False`` rather than a fabricated
    # percentage mapping.

    def battery_present(self) -> bool:
        """Return whether a battery is physically present in the system.

        Queried through the standard ``Win32_Battery`` class rather than a
        firmware setting, since HP does not expose battery presence through
        the settings interface and ``Win32_Battery`` is a reliable,
        vendor-neutral source available on any Windows system with a
        battery installed.
        """
        if platform.system() != "Windows":
            return super().battery_present()

        rows = self._query_wmi_safe(r"root\cimv2", "SELECT DeviceID FROM Win32_Battery")
        return bool(rows)

    def battery_health_mode_supported(self) -> bool:
        return self._find_setting_name(_SETTING_BATTERY_HEALTH) is not None

    def get_battery_health_mode(self) -> str:
        name = self._find_setting_name(_SETTING_BATTERY_HEALTH)
        if name is None:
            return ""

        return self._raw_settings.get(name, "")

    def set_battery_health_mode(self, mode: str) -> bool:
        operation = "set_battery_health_mode"
        self._record_operation(operation)

        name = self._find_setting_name(_SETTING_BATTERY_HEALTH)
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
        return value in {"power on", "poweron", "on"}

    def enable_restore_power_on_ac(self) -> bool:
        name = self._find_setting_name(_SETTING_AC_RECOVERY)
        if name is None:
            return self._unsupported(
                "enable_restore_power_on_ac", "Restore-on-AC-power management"
            )

        return self.set_setting(name, "Power On")

    def disable_restore_power_on_ac(self) -> bool:
        name = self._find_setting_name(_SETTING_AC_RECOVERY)
        if name is None:
            return self._unsupported(
                "disable_restore_power_on_ac", "Restore-on-AC-power management"
            )

        return self.set_setting(name, "Power Off")

    def supports_fast_boot(self) -> bool:
        supported, _ = self._read_bool_setting(_SETTING_FAST_BOOT)
        return supported

    def fast_boot_enabled(self) -> bool:
        _, enabled = self._read_bool_setting(_SETTING_FAST_BOOT)
        return bool(enabled)

    def enable_fast_boot(self) -> bool:
        if not self.supports_fast_boot():
            return self._unsupported(
                "enable_fast_boot", "Firmware fast-boot management"
            )
        return self._write_bool_setting(_SETTING_FAST_BOOT, True)

    def disable_fast_boot(self) -> bool:
        if not self.supports_fast_boot():
            return self._unsupported(
                "disable_fast_boot", "Firmware fast-boot management"
            )
        return self._write_bool_setting(_SETTING_FAST_BOOT, False)

    # -------------------------------------------------------------------
    # HP-specific extensions
    # -------------------------------------------------------------------

    def asset_tag(self) -> str:
        """Return the SMBIOS chassis asset tag, when available."""
        if platform.system() != "Windows":
            return ""

        rows = self._query_wmi_safe(
            r"root\cimv2", "SELECT SMBIOSAssetTag FROM Win32_SystemEnclosure"
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
        base_report["hp"] = {
            "wmi_backend_available": bool(self._wmi_available),
            "tpm_state": self._serialize_value(self.tpm_state()),
            "battery_health_mode": self.get_battery_health_mode(),
            "asset_tag": self.asset_tag(),
        }
        return base_report

    def diagnostics(self) -> Dict[str, Any]:
        """Return sanitized provider diagnostic information."""
        base_diagnostics = super().diagnostics()
        base_diagnostics.update(
            {
                "wmi_namespace": _HP_WMI_NAMESPACE,
                "wmi_backend_available": bool(self._wmi_available),
                "hp_image_assistant_found": self._locate_hp_image_assistant()
                is not None,
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
                        "HP firmware WMI classes were not found on this "
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
            rows = self._query_wmi(_HP_WMI_NAMESPACE, f"SELECT * FROM {class_name}")
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
                self._hp_logger.debug(
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
                self._hp_logger.debug(
                    "COM WMI query failed in %s: %s", namespace, exc
                )
                return []

    def _query_wmi_safe(self, namespace: str, query: str) -> List[Any]:
        """Run a WMI query and convert backend failures to an empty result."""
        try:
            return self._query_wmi(namespace, query)
        except Exception as exc:
            self._hp_logger.debug("WMI query was unavailable: %s", exc)
            return []

    def _invoke_wmi_method(
        self, class_name: str, method_name: str, arguments: Dict[str, Any]
    ) -> Any:
        """Invoke an HP firmware WMI method and return the raw result.

        Tries the ``wmi`` package first, then falls back to a COM
        automation call through ``win32com`` when it is not installed.
        """
        if platform.system() != "Windows":
            return None

        with self._execution_lock:
            try:
                import wmi  # type: ignore[import-untyped]

                connection = wmi.WMI(namespace=_HP_WMI_NAMESPACE)
                instances = getattr(connection, class_name)()
                if not instances:
                    return None

                method = getattr(instances[0], method_name)
                return method(**arguments)
            except ImportError:
                pass
            except Exception as exc:
                self._hp_logger.debug(
                    "Python WMI method call failed (%s.%s): %s",
                    class_name,
                    method_name,
                    exc,
                )

            try:
                import win32com.client  # type: ignore[import-untyped]

                locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
                service = locator.ConnectServer(".", _HP_WMI_NAMESPACE)
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
                self._hp_logger.debug(
                    "COM WMI method call failed (%s.%s): %s",
                    class_name,
                    method_name,
                    exc,
                )
                return None

    @staticmethod
    def _wmi_result_ok(result: Any) -> bool:
        """Interpret an HP WMI method result as success or failure.

        ``SetBIOSSetting`` returns ``0`` on success and a non-zero HP error
        code otherwise.
        """
        if result is None:
            return False

        return_value = HPProvider._wmi_out_parameter(result, "ReturnValue")
        if return_value is not None:
            try:
                return int(return_value) == 0
            except (TypeError, ValueError):
                text = str(return_value).strip().lower()
                return text in {"success", "0"}

        text = str(result).strip().lower()
        return text in {"success", "0", "0.0", ""}

    @staticmethod
    def _wmi_out_parameter(result: Any, name: str) -> Any:
        """Best-effort accessor for an out-parameter on a WMI method result."""
        if isinstance(result, dict):
            return result.get(name)

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
                r"root\cimv2", f"SELECT {wmi_property} FROM Win32_ComputerSystem"
            )
            return str(self._first_property(rows, wmi_property) or "")

        return ""

    @staticmethod
    def _first_property(rows: List[Any], name: str) -> str:
        for row in rows:
            value = HPProvider._safe_property_value(row, name)
            if value:
                return str(value)

        return ""

    @staticmethod
    def _safe_property_value(row: Any, name: str) -> Any:
        try:
            if isinstance(row, dict):
                return row.get(name)

            return getattr(row, name, None)
        except Exception:
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
            self._password_state_cache = None
            self._connected = False
            self._closed = True
            self._last_operation = "close"
            self._last_error = None


__all__ = [
    "HPProvider",
    "PROVIDER_VERSION",
]
