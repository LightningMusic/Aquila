"""Acer BIOS provider for Project Aquila.

Backend reality (researched, not assumed):

Acer publishes **no** documented interface -- WMI, PowerShell, or CLI -- for
reading or writing individual BIOS settings, on either consumer or
commercial (Veriton, TravelMate) systems. This is not merely an absence of
public documentation the way it is for Gigabyte: an Acer support
representative was asked directly, on Acer's own community forum, whether
WMI classes or VBScript could reach BIOS settings on commercial Acer
desktops, and replied "This is not something that we support," followed by,
when pressed for any supported alternative, "we do not have, support, nor
can we suggest anything that would allow you to do what you have now
asked." No Acer-specific WMI class, SCCM/Intune integration, or command-line
tool for BIOS configuration exists.

Consequently this provider follows the same honesty policy as the
``MSIProvider``/``GigabyteProvider``: real, tested implementations of
everything genuinely available through vendor-neutral mechanisms (firmware
identity, boot order, TPM state, battery presence), and an honest
"unsupported" report -- via ``DefaultProvider``'s existing fallback
behavior -- for individual BIOS setting management, virtualization/IOMMU/
SR-IOV toggling, BIOS password management, wake-source configuration, and
battery charge-limit management, rather than fabricating a nonexistent
backend.

If Acer ever documents a settings interface, ``_apply_setting`` is the
extension point -- see the Lenovo/HP providers for the pattern to follow.
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


class AcerProvider(DefaultProvider):
    """Production Acer firmware provider.

    Supports Acer desktop, laptop, and commercial (Veriton, TravelMate)
    systems for firmware identity, boot-order management, TPM/battery
    presence reporting, and diagnostics. Individual BIOS setting management
    is not available -- Acer's own support has explicitly confirmed no such
    interface exists (see module docstring) -- so all setting-level methods
    honestly fall back to ``DefaultProvider``'s unsupported behavior.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize provider state without opening privileged resources."""
        super().__init__(*args, **kwargs)
        self._acer_logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._execution_lock = threading.RLock()
        self._wmi_handle: Any = None
        self._efibootmgr_path: Optional[Path] = None
        self._connected = False
        self._closed = False

    # -------------------------------------------------------------------
    # Identity, detection, and lifecycle
    # -------------------------------------------------------------------

    def vendor(self) -> BIOSVendor:
        """Return the Acer vendor identifier."""
        return BIOSVendor.ACER

    def provider_name(self) -> str:
        """Return the stable provider name."""
        return "acer"

    def provider_version(self) -> str:
        """Return the Acer provider implementation version."""
        return PROVIDER_VERSION

    def supports_windows(self) -> bool:
        """Return whether this provider supports Windows hosts."""
        return True

    def supports_linux(self) -> bool:
        """Return whether this provider supports Linux hosts.

        Support on Linux is limited to firmware identity and boot-order
        management through standard UEFI mechanisms, identical to the
        Windows-side limitations described in the module docstring.
        """
        return True

    def detect(self) -> bool:
        """Return whether this system is confidently identified as Acer."""
        return self.detection_confidence() >= 0.7

    def detection_confidence(self) -> float:
        """Calculate a confidence score from independent Acer indicators."""
        manufacturer = self._system_value("sys_vendor", "Manufacturer")
        product = self._system_value("product_name", "Model")
        board_name = self._system_value("board_name", "Product")
        combined = f"{manufacturer} {product} {board_name}".strip().lower()

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

        if normalized_vendor == "acer" or normalized_vendor.startswith("acer "):
            score += 0.55
        elif "acer" in normalized_vendor.split():
            score += 0.5

        if re.search(
            r"\b(aspire|predator|nitro|swift|spin|veriton|travelmate|"
            r"extensa|chromebook|iconia)\b",
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

        return super().firmware_interface()

    # -------------------------------------------------------------------
    # Firmware inventory
    # -------------------------------------------------------------------

    def _collect_firmware_information(self) -> FirmwareInformation:
        """Collect firmware identity information.

        On Windows this queries ``Win32_BIOS`` / ``Win32_ComputerSystem`` /
        ``Win32_ComputerSystemProduct`` -- all generic operating-system
        interfaces, not an Acer-specific one. Every other platform falls
        back to ``DefaultProvider``'s sysfs-based collection.
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

        manufacturer = self._first_property(system_rows, "Manufacturer") or "Acer"
        model = self._first_property(system_rows, "Model") or ""
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
            vendor=BIOSVendor.ACER,
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
            firmware_type = AcerProvider._windows_firmware_type()
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

    # Acer publishes no documented WMI, PowerShell, or CLI interface for
    # reading or writing individual BIOS settings -- confirmed directly by
    # Acer's own support staff on Acer's community forum, not merely an
    # absence of documentation (see module docstring). ``_apply_setting``
    # therefore intentionally returns ``False`` (the ``DefaultProvider``
    # default) rather than fabricating a nonexistent backend, and the
    # entire generic settings API honestly reports an empty, unsupported
    # registry via inherited ``DefaultProvider`` behavior.

    # -------------------------------------------------------------------
    # Boot management
    # -------------------------------------------------------------------

    def boot_order(self) -> List[BootDevice]:
        """Return the configured persistent firmware boot order.

        Boot order is read through the standard UEFI mechanism (Linux:
        ``efibootmgr``; Windows: ``bcdedit /enum firmware``) rather than a
        vendor-specific interface, since Acer does not publish one.
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
                    device_type=AcerProvider._boot_device_type(
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
        generic Windows interface, not an Acer-specific one.
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

        Queried through the standard ``Win32_Battery`` class, a generic
        Windows interface, not an Acer-specific one.
        """
        if platform.system() != "Windows":
            return super().battery_present()

        rows = self._query_wmi_safe(r"root\cimv2", "SELECT DeviceID FROM Win32_Battery")
        return bool(rows)

    # Acer does not publish a documented interface for reading or setting a
    # numeric battery charge-limit percentage, so
    # ``battery_charge_limit_supported()`` correctly falls back to
    # ``DefaultProvider``'s honest ``False``.

    # -------------------------------------------------------------------
    # Acer-specific extensions
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
        base_summary.update({"asset_tag": self.asset_tag()})
        return base_summary

    def report(self) -> Dict[str, Any]:
        """Return a detailed, non-sensitive provider and firmware report."""
        base_report = super().report()
        base_report["acer"] = {
            "asset_tag": self.asset_tag(),
            "tpm_state": self._serialize_value(self.tpm_state()),
            "bios_settings_management_available": False,
            "bios_settings_management_reason": (
                "Acer support has explicitly confirmed no WMI, scripting, "
                "or CLI interface exists for individual BIOS setting "
                "management on Acer systems."
            ),
        }
        return base_report

    def diagnostics(self) -> Dict[str, Any]:
        """Return sanitized provider diagnostic information."""
        base_diagnostics = super().diagnostics()
        base_diagnostics.update(
            {
                "efibootmgr_found": self._locate_efibootmgr() is not None,
                "bios_settings_management_available": False,
            }
        )
        return base_diagnostics

    def validate_configuration(self) -> List[ValidationError]:
        """Return validation failures for the current configuration."""
        issues = super().validate_configuration()

        issues.append(
            ValidationError(
                field="bios_settings_backend",
                message=(
                    "Acer publishes no documented interface for individual "
                    "BIOS setting management; only firmware identity, boot "
                    "order, TPM state, and battery presence are available "
                    "on this provider."
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
                self._acer_logger.debug(
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
                self._acer_logger.debug(
                    "COM WMI query failed in %s: %s", namespace, exc
                )
                return []

    def _query_wmi_safe(self, namespace: str, query: str) -> List[Any]:
        """Run a WMI query and convert backend failures to an empty result."""
        try:
            return self._query_wmi(namespace, query)
        except Exception as exc:
            self._acer_logger.debug("WMI query was unavailable: %s", exc)
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
            value = AcerProvider._safe_property_value(row, name)
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
    "AcerProvider",
    "PROVIDER_VERSION",
]
