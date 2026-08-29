"""Framework BIOS provider for Project Aquila.

Backend reality (researched, not assumed):

Framework Computer Inc. publishes **no** Windows WMI, PowerShell, or CLI
interface for reading or writing individual BIOS/UEFI settings -- no such
class or utility appears in Framework's own documentation, its Knowledge
Base, or its community forum.

On Linux, however, a real and documented mechanism exists: the kernel's
vendor-neutral ``firmware_attributes_class`` sysfs ABI, introduced upstream
in Linux 5.11 (February 2021) and documented at
``Documentation/ABI/testing/sysfs-class-firmware-attributes``. Any kernel
driver that registers with this class exposes BIOS/UEFI settings under
``/sys/class/firmware-attributes/<driver-name>/attributes/<setting-name>/``,
each with a ``type`` (``enumeration``, ``integer``, or ``string``), a
``current_value``, and usually a ``default_value``. This is the same ABI
that backs ``fwupdmgr get-bios-setting`` / ``set-bios-setting``. Whether a
given Framework unit actually has a driver registered against this class
depends on kernel version and platform support -- it is **not** assumed to
exist; this provider probes for it at runtime and reports honestly when it
is absent.

The kernel ABI also exposes a supervisor-password mechanism under
``<driver>/authentication/`` (``current_password`` / ``new_password`` /
``role`` / ``mechanism``). This provider deliberately does **not**
implement password set/clear through that interface: getting a
write-then-verify password flow wrong on hardware this project has not been
able to test against risks locking a technician out of firmware, which
would violate the project's own safety principles (GP-001, GP-002) far more
severely than declining to implement the feature. ``bios_password_set()``
therefore honestly falls back to ``DefaultProvider``'s unsupported
behavior, and ``diagnostics()`` reports whether an authentication directory
was found so a future, hardware-validated implementation has a starting
point.

Consequently this provider follows the same honesty policy as the other
vendor-thin providers for identity, boot order, TPM state, and battery
presence -- but, uniquely among Version 1.0 providers, offers a genuine,
tested read/write settings backend on Linux when the kernel exposes one.
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
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

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

logger = logging.getLogger(__name__)

_FIRMWARE_ATTRIBUTES_ROOT = Path("/sys/class/firmware-attributes")


class FrameworkProvider(DefaultProvider):
    """Production Framework firmware provider.

    Supports Framework Laptop and Desktop systems for firmware identity,
    boot-order management, TPM/battery presence reporting, and diagnostics
    on both Windows and Linux. On Linux, when the kernel exposes the
    ``firmware_attributes_class`` sysfs ABI for the installed unit,
    individual BIOS setting management is also genuinely available; on
    Windows, or when no such kernel driver is present, setting-level
    methods honestly fall back to ``DefaultProvider``'s unsupported
    behavior rather than fabricating a nonexistent backend.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize provider state without opening privileged resources."""
        super().__init__(*args, **kwargs)
        self._framework_logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}"
        )
        self._execution_lock = threading.RLock()
        self._wmi_handle: Any = None
        self._efibootmgr_path: Optional[Path] = None
        self._connected = False
        self._closed = False

        # Cache for the resolved firmware-attributes driver directory.
        # ``None`` means "not yet probed"; a sentinel path of "" (checked
        # via ``_firmware_attr_probed``) means "probed, none found".
        self._firmware_attr_dir: Optional[Path] = None
        self._firmware_attr_probed = False
        self._raw_attribute_types: Dict[str, str] = {}

    # -------------------------------------------------------------------
    # Identity, detection, and lifecycle
    # -------------------------------------------------------------------

    def vendor(self) -> BIOSVendor:
        """Return the Framework vendor identifier."""
        return BIOSVendor.FRAMEWORK

    def provider_name(self) -> str:
        """Return the stable provider name."""
        return "framework"

    def provider_version(self) -> str:
        """Return the Framework provider implementation version."""
        return PROVIDER_VERSION

    def supports_windows(self) -> bool:
        """Return whether this provider supports Windows hosts."""
        return True

    def supports_linux(self) -> bool:
        """Return whether this provider supports Linux hosts.

        Linux is where this provider offers the most functionality: when a
        ``firmware_attributes_class`` kernel driver is present, individual
        BIOS setting management is genuinely available (see module
        docstring).
        """
        return True

    def detect(self) -> bool:
        """Return whether this system is confidently identified as Framework."""
        return self.detection_confidence() >= 0.7

    def detection_confidence(self) -> float:
        """Calculate a confidence score from independent Framework indicators."""
        manufacturer = self._system_value("sys_vendor", "Manufacturer")
        product = self._system_value("product_name", "Model")
        board_name = self._system_value("board_name", "Product")
        combined = (
            f"{manufacturer} {product} {board_name}".strip().lower()
        )

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

        if normalized_vendor == "framework" or normalized_vendor.startswith(
            "framework "
        ):
            score += 0.6
        elif "framework" in normalized_vendor.split():
            score += 0.55

        if re.search(
            r"\b(laptop\s?12|laptop\s?13|laptop\s?16|framework\s?laptop|"
            r"framework\s?desktop)\b",
            combined,
        ):
            score += 0.2

        return min(score, 1.0)

    def connect(self) -> bool:
        """Establish the provider and load current firmware information."""
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

            try:
                if not self.refresh():
                    return False
            except Exception as exc:
                self._record_error(
                    "connect", f"Provider initialization failed: {exc}"
                )
                return False

            if platform.system() == "Linux":
                try:
                    self._load_firmware_attribute_settings()
                except Exception as exc:
                    self._framework_logger.debug(
                        "Unable to load firmware-attributes settings: %s", exc
                    )

            self._connected = True
            return True

    def disconnect(self) -> None:
        """Disconnect from the firmware interface and release resources."""
        with self._execution_lock:
            self._record_operation("disconnect")
            self._connected = False
            self._wmi_handle = None
            self._transaction_active = False

    def is_connected(self) -> bool:
        """Return whether the provider is connected and ready."""
        return self._connected

    def refresh(self) -> bool:
        """Refresh cached firmware information."""
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

            return True

    def firmware_interface(self) -> str:
        """Return the firmware-management interface used by the provider."""
        if platform.system() == "Windows":
            return r"wmi:root\cimv2"

        if platform.system() == "Linux" and self._firmware_attributes_driver_dir():
            return "sysfs:firmware-attributes"

        return super().firmware_interface()

    # -------------------------------------------------------------------
    # Firmware inventory
    # -------------------------------------------------------------------

    def _collect_firmware_information(self) -> FirmwareInformation:
        """Collect firmware identity information.

        On Windows this queries ``Win32_BIOS`` / ``Win32_ComputerSystem`` /
        ``Win32_ComputerSystemProduct`` -- generic operating-system
        interfaces, not a Framework-specific one. On Linux,
        ``DefaultProvider``'s existing ``/sys/class/dmi/id`` collection
        already reads every field this provider needs, including
        ``ec_firmware_release`` for the embedded-controller version, so it
        is reused directly rather than duplicated.
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
        board_rows = self._query_wmi_safe(
            r"root\cimv2",
            "SELECT Product, Manufacturer, Version FROM Win32_BaseBoard",
        )

        if not system_rows and not bios_rows:
            return super()._collect_firmware_information()

        manufacturer = self._first_property(system_rows, "Manufacturer") or "Framework"
        model = (
            self._first_property(system_rows, "Model")
            or self._first_property(board_rows, "Product")
            or ""
        )
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
            vendor=BIOSVendor.FRAMEWORK,
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
            raw_data={"source": "wmi:win32_bios+win32_computersystem+win32_baseboard"},
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
            firmware_type = FrameworkProvider._windows_firmware_type()
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
    # BIOS settings integration (Linux: real kernel firmware-attributes ABI)
    # -------------------------------------------------------------------

    def _firmware_attributes_driver_dir(self) -> Optional[Path]:
        """Locate the kernel's firmware-attributes sysfs driver directory.

        The subdirectory name under ``/sys/class/firmware-attributes/`` is
        driver-defined and not assumed in advance; this probes for whatever
        actually exists on the running kernel. Only Linux exposes this ABI.
        """
        if self._firmware_attr_probed:
            return self._firmware_attr_dir

        self._firmware_attr_probed = True
        self._firmware_attr_dir = None

        if platform.system() != "Linux":
            return None

        if not _FIRMWARE_ATTRIBUTES_ROOT.is_dir():
            return None

        try:
            candidates = sorted(
                path for path in _FIRMWARE_ATTRIBUTES_ROOT.iterdir() if path.is_dir()
            )
        except OSError:
            return None

        if not candidates:
            return None

        for candidate in candidates:
            if "framework" in candidate.name.lower():
                self._firmware_attr_dir = candidate
                return candidate

        # Only one vendor-neutral driver is normally registered per system;
        # if exactly one exists and it did not match "framework" by name,
        # it is still the only real backend available and is used as-is.
        self._firmware_attr_dir = candidates[0]
        return candidates[0]

    def _load_firmware_attribute_settings(self) -> None:
        """Load every firmware-attributes setting and register it for the
        generic API.

        Each attribute directory under ``<driver>/attributes/<name>/``
        exposes a ``type`` (``enumeration`` / ``integer`` / ``string``), a
        ``current_value``, and usually a ``default_value``. This method
        parses every attribute directory and registers it through
        ``DefaultProvider._register_setting`` so the inherited
        ``available_settings`` / ``get_setting`` / ``set_setting`` /
        ``reset_setting`` / ``restore_defaults`` methods work without
        Framework-specific overrides.
        """
        driver_dir = self._firmware_attributes_driver_dir()
        if driver_dir is None:
            return

        attributes_dir = driver_dir / "attributes"
        if not attributes_dir.is_dir():
            return

        try:
            attribute_names = sorted(
                path.name for path in attributes_dir.iterdir() if path.is_dir()
            )
        except OSError:
            return

        self._raw_attribute_types.clear()

        for name in attribute_names:
            attr_dir = attributes_dir / name
            attr_type = self._read_text_file(attr_dir / "type")
            current_value = self._read_text_file(attr_dir / "current_value")
            default_value_raw = self._read_text_file(attr_dir / "default_value")

            display_value: Any = current_value
            default_value: Any = default_value_raw or None

            if attr_type == "integer":
                try:
                    display_value = int(current_value)
                except (TypeError, ValueError):
                    display_value = current_value
                if default_value_raw:
                    try:
                        default_value = int(default_value_raw)
                    except ValueError:
                        default_value = default_value_raw

            # A writable attribute always exposes a ``current_value`` file;
            # write-only (password-type) or display-only attributes do not
            # meaningfully participate in the generic get/set/reset API.
            writable = (attr_dir / "current_value").is_file() and attr_type != ""

            self._raw_attribute_types[name] = attr_type
            self._register_setting(
                name,
                display_value,
                default=default_value,
                writable=writable,
                reboot_required=True,
            )

    def _apply_setting(self, name: str, value: Any) -> bool:
        """Write a setting's ``current_value`` through the kernel sysfs ABI."""
        driver_dir = self._firmware_attributes_driver_dir()
        if driver_dir is None:
            return False

        current_value_path = driver_dir / "attributes" / name / "current_value"
        if not current_value_path.is_file():
            return False

        try:
            current_value_path.write_text(str(value), encoding="utf-8")
        except OSError as exc:
            self._framework_logger.debug(
                "Unable to write firmware attribute %s: %s", current_value_path, exc
            )
            return False

        return True

    def _firmware_attributes_pending_reboot(self) -> Optional[bool]:
        """Return the kernel-reported pending-reboot flag, if available."""
        driver_dir = self._firmware_attributes_driver_dir()
        if driver_dir is None:
            return None

        pending_path = driver_dir / "attributes" / "pending_reboot"
        raw = self._read_text_file(pending_path)
        if raw == "":
            return None

        return raw.strip() not in ("0", "")

    def _firmware_attributes_authentication_present(self) -> bool:
        """Return whether the kernel exposes a password-authentication directory.

        Reported for diagnostics only; this provider does not implement
        password set/clear through it (see module docstring).
        """
        driver_dir = self._firmware_attributes_driver_dir()
        if driver_dir is None:
            return False

        return (driver_dir / "authentication").is_dir()

    # -------------------------------------------------------------------
    # Boot management
    # -------------------------------------------------------------------

    def boot_order(self) -> List[BootDevice]:
        """Return the configured persistent firmware boot order.

        Boot order is read through the standard UEFI mechanism (Linux:
        ``efibootmgr``; Windows: ``bcdedit /enum firmware``), not a
        vendor-specific interface.
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
        """Parse ``efibootmgr -v`` output into normalized boot devices.

        The UEFI device path frequently embeds a random-looking partition
        GUID; classification below uses whole-word or unambiguous
        multi-character markers rather than short substrings that can
        appear by chance inside a GUID fragment.
        """
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
                    device_type=FrameworkProvider._boot_device_type(
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
        """Classify a boot entry from its display name and UEFI device path."""
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
    # TPM and platform security
    # -------------------------------------------------------------------

    def tpm_supported(self) -> bool:
        return bool(self.tpm_state().present)

    def tpm_enabled(self) -> bool:
        return self.tpm_state().enabled

    def tpm_state(self) -> TPMState:
        """Return normalized Trusted Platform Module state.

        Uses ``Win32_Tpm`` (``root\\cimv2\\Security\\MicrosoftTpm``), a
        generic Windows interface, not a Framework-specific one.
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

    # -------------------------------------------------------------------
    # Battery management
    # -------------------------------------------------------------------

    def battery_present(self) -> bool:
        """Return whether a battery is physically present in the system.

        Queried through the standard ``Win32_Battery`` class on Windows, a
        generic interface, not a Framework-specific one. On Linux, falls
        back to ``DefaultProvider``'s behavior.
        """
        if platform.system() != "Windows":
            return super().battery_present()

        rows = self._query_wmi_safe(r"root\cimv2", "SELECT DeviceID FROM Win32_Battery")
        return bool(rows)

    # Framework publishes no documented interface for a numeric battery
    # charge-limit percentage independent of the generic settings backend
    # above, so ``battery_charge_limit_supported()`` correctly falls back
    # to ``DefaultProvider``'s honest ``False`` unless a future kernel
    # driver exposes it as a named attribute, in which case it would
    # already be reachable through ``get_setting`` / ``set_setting``.

    # -------------------------------------------------------------------
    # Framework-specific extensions
    # -------------------------------------------------------------------

    def asset_tag(self) -> str:
        """Return the SMBIOS chassis asset tag, when available."""
        if platform.system() == "Linux":
            path = Path("/sys/class/dmi/id/chassis_asset_tag")
            return self._read_text_file(path)

        if platform.system() != "Windows":
            return ""

        rows = self._query_wmi_safe(
            r"root\cimv2", "SELECT SMBIOSAssetTag FROM Win32_SystemEnclosure"
        )
        if not rows:
            return ""

        return str(self._safe_property_value(rows[0], "SMBIOSAssetTag") or "")

    def board_model(self) -> str:
        """Return the mainboard model reported by firmware."""
        if platform.system() == "Linux":
            return self._read_text_file(Path("/sys/class/dmi/id/board_name"))

        if platform.system() != "Windows":
            return ""

        rows = self._query_wmi_safe(
            r"root\cimv2", "SELECT Product FROM Win32_BaseBoard"
        )
        return self._first_property(rows, "Product")

    # -------------------------------------------------------------------
    # Reporting and diagnostics
    # -------------------------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """Return a concise, non-sensitive provider summary."""
        base_summary = super().summary()
        base_summary.update(
            {
                "board_model": self.board_model(),
                "asset_tag": self.asset_tag(),
                "firmware_attributes_driver_found": self._firmware_attributes_driver_dir()
                is not None,
            }
        )
        return base_summary

    def report(self) -> Dict[str, Any]:
        """Return a detailed, non-sensitive provider and firmware report."""
        base_report = super().report()
        driver_dir = self._firmware_attributes_driver_dir()
        backend_available = driver_dir is not None and bool(self._settings)

        base_report["framework"] = {
            "board_model": self.board_model(),
            "asset_tag": self.asset_tag(),
            "tpm_state": self._serialize_value(self.tpm_state()),
            "firmware_attributes_driver": (
                driver_dir.name if driver_dir is not None else None
            ),
            "bios_settings_management_available": backend_available,
            "bios_settings_management_reason": (
                "Individual BIOS settings are available through the "
                "kernel's firmware-attributes sysfs ABI."
                if backend_available
                else (
                    "No kernel firmware-attributes driver was found for "
                    "this unit; Framework publishes no Windows WMI/CLI "
                    "interface for individual BIOS setting management."
                    if platform.system() == "Linux"
                    else "Framework publishes no documented Windows "
                    "interface for individual BIOS setting management."
                )
            ),
            "pending_reboot": self._firmware_attributes_pending_reboot(),
            "authentication_directory_found": (
                self._firmware_attributes_authentication_present()
            ),
        }
        return base_report

    def diagnostics(self) -> Dict[str, Any]:
        """Return sanitized provider diagnostic information."""
        base_diagnostics = super().diagnostics()
        driver_dir = self._firmware_attributes_driver_dir()
        base_diagnostics.update(
            {
                "efibootmgr_found": self._locate_efibootmgr() is not None,
                "firmware_attributes_driver_found": driver_dir is not None,
                "firmware_attributes_driver_name": (
                    driver_dir.name if driver_dir is not None else None
                ),
                "bios_settings_management_available": (
                    driver_dir is not None and bool(self._settings)
                ),
                "authentication_directory_found": (
                    self._firmware_attributes_authentication_present()
                ),
            }
        )
        return base_diagnostics

    def validate_configuration(self) -> List[ValidationError]:
        """Return validation failures for the current configuration."""
        issues = super().validate_configuration()

        driver_dir = self._firmware_attributes_driver_dir()

        if driver_dir is not None and self._settings:
            issues.append(
                ValidationError(
                    field="bios_settings_backend",
                    message=(
                        "Individual BIOS settings are available through the "
                        f"kernel firmware-attributes driver '{driver_dir.name}'."
                    ),
                    code="bios_settings_backend_available",
                    severity="info",
                )
            )
        elif platform.system() == "Linux":
            issues.append(
                ValidationError(
                    field="bios_settings_backend",
                    message=(
                        "No kernel firmware-attributes sysfs driver was "
                        "found for this unit; only firmware identity, boot "
                        "order, TPM state, and battery presence are "
                        "available on this provider."
                    ),
                    code="bios_settings_backend_unavailable",
                    severity="info",
                )
            )
        else:
            issues.append(
                ValidationError(
                    field="bios_settings_backend",
                    message=(
                        "Framework publishes no documented Windows "
                        "interface for individual BIOS setting management; "
                        "only firmware identity, boot order, TPM state, "
                        "and battery presence are available on this "
                        "provider under Windows."
                    ),
                    code="bios_settings_backend_unavailable",
                    severity="info",
                )
            )

        return issues

    # -------------------------------------------------------------------
    # WMI backend helpers
    # -------------------------------------------------------------------

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
                self._framework_logger.debug(
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
                self._framework_logger.debug(
                    "COM WMI query failed in %s: %s", namespace, exc
                )
                return []

    def _query_wmi_safe(self, namespace: str, query: str) -> List[Any]:
        """Run a WMI query and convert backend failures to an empty result."""
        try:
            return self._query_wmi(namespace, query)
        except Exception as exc:
            self._framework_logger.debug("WMI query was unavailable: %s", exc)
            return []

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
            if sysfs_name == "board_vendor":
                rows = self._query_wmi_safe(
                    r"root\cimv2", "SELECT Manufacturer FROM Win32_BaseBoard"
                )
                return self._first_property(rows, "Manufacturer")

            if sysfs_name == "board_name":
                rows = self._query_wmi_safe(
                    r"root\cimv2", "SELECT Product FROM Win32_BaseBoard"
                )
                return self._first_property(rows, "Product")

            rows = self._query_wmi_safe(
                r"root\cimv2", f"SELECT {wmi_property} FROM Win32_ComputerSystem"
            )
            return str(self._first_property(rows, wmi_property) or "")

        return ""

    @staticmethod
    def _first_property(rows: List[Any], name: str) -> str:
        for row in rows:
            value = FrameworkProvider._safe_property_value(row, name)
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
            self._connected = False
            self._closed = True
            self._last_operation = "close"
            self._last_error = None


__all__ = [
    "FrameworkProvider",
    "PROVIDER_VERSION",
]
