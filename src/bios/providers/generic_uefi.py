"""Generic UEFI BIOS provider for Project Aquila.

Role in the provider registry (not a vendor guess):

This provider is the second-to-last entry tried by ``BIOSDetection`` --
after every vendor-specific provider (Dell, HP, Lenovo, Acer, ASUS, MSI,
Gigabyte, Framework) has failed to match, and before ``UnknownProvider``,
the true last resort. It is selected whenever Aquila can positively confirm
the system boots through standards-compliant UEFI firmware but cannot
identify a supported vendor -- for example, a system from a smaller or
unlisted manufacturer (Supermicro, ASRock, Fujitsu, Panasonic, Samsung,
Toshiba, and similar all have ``BIOSVendor`` entries but no dedicated
provider in Version 1.0).

Backend reality (researched, not assumed):

By definition this provider has **no** vendor-specific settings interface
to call -- if one were known, a dedicated vendor provider would exist
instead. Earlier revisions of this file (see the old
``bios.providers.generic_uefi`` stub) claimed unconditional support for
virtualization, IOMMU, Secure Boot, TPM, wake-on-LAN, power restore, and
battery-settings toggling on *any* unrecognized UEFI system. That was never
true -- those capabilities depend entirely on vendor firmware tooling this
provider cannot possibly have, since the vendor is unknown by construction.
This rewrite follows the same honesty policy as every other Version 1.0
provider: real, tested implementations of what is genuinely available
through standards-based, vendor-neutral mechanisms (firmware identity via
generic SMBIOS/WMI, standard UEFI boot-order management, generic-interface
TPM and battery presence), and an honest "unsupported" report for
individual BIOS setting management, virtualization/IOMMU/SR-IOV toggling,
Secure Boot toggling, BIOS password management, wake-source configuration,
and battery charge-limit management, rather than fabricating a backend
that cannot exist without knowing the vendor.
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


class GenericUEFIProvider(DefaultProvider):
    """Vendor-neutral fallback provider for standards-compliant UEFI firmware.

    Selected only after every vendor-specific provider has failed to match
    and the system can still be confirmed to boot through UEFI. Supports
    firmware identity, boot-order management, and best-effort TPM/battery
    presence reporting through generic, standards-based mechanisms.
    Individual BIOS setting management is never available here, because by
    definition no vendor-specific interface is known; all setting-level
    methods honestly fall back to ``DefaultProvider``'s unsupported
    behavior.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize provider state without opening privileged resources."""
        super().__init__(*args, **kwargs)
        self._generic_logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}"
        )
        self._execution_lock = threading.RLock()
        self._wmi_handle: Any = None
        self._efibootmgr_path: Optional[Path] = None
        self._connected = False
        self._closed = False

    # -------------------------------------------------------------------
    # Identity, detection, and lifecycle
    # -------------------------------------------------------------------

    def vendor(self) -> BIOSVendor:
        """Return the generic (vendor-neutral) provider identifier.

        This intentionally always returns ``BIOSVendor.GENERIC`` regardless
        of the actual system manufacturer -- the real manufacturer string,
        when known, is still preserved in ``firmware_information().manufacturer``
        and ``firmware_information().vendor`` (via ``BIOSVendor.from_string``).
        """
        return BIOSVendor.GENERIC

    def provider_name(self) -> str:
        """Return the stable provider name."""
        return "generic_uefi"

    def provider_version(self) -> str:
        """Return the Generic UEFI provider implementation version."""
        return PROVIDER_VERSION

    def supports_windows(self) -> bool:
        """Return whether this provider supports Windows hosts."""
        return True

    def supports_linux(self) -> bool:
        """Return whether this provider supports Linux hosts."""
        return True

    def detect(self) -> bool:
        """Return whether this system boots through standards-compliant UEFI.

        Unlike vendor providers, detection here has nothing to do with
        manufacturer strings -- only whether UEFI firmware, as opposed to
        legacy BIOS, is confirmed. This provider is tried only after every
        vendor-specific provider has already failed to match (see the
        module docstring), so no vendor-confusion risk exists here.
        """
        return self._detect_bios_mode() == BIOSMode.UEFI

    def detection_confidence(self) -> float:
        """Return ``1.0`` when UEFI is confirmed, ``0.0`` otherwise."""
        return 1.0 if self.detect() else 0.0

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
                    "No standards-compliant UEFI firmware was detected on "
                    "this system.",
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
        ``Win32_ComputerSystemProduct`` -- entirely generic operating-system
        interfaces available regardless of manufacturer. On Linux,
        ``DefaultProvider``'s existing ``/sys/class/dmi/id`` collection is
        reused directly, since it is already vendor-neutral.
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

        manufacturer = self._first_property(system_rows, "Manufacturer") or ""
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
            vendor=BIOSVendor.from_string(manufacturer),
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
            firmware_type = GenericUEFIProvider._windows_firmware_type()
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

    # No vendor is known for this provider by definition, so there is no
    # possible vendor-specific settings interface to call.
    # ``_apply_setting`` intentionally returns ``False`` (the
    # ``DefaultProvider`` default) and the generic settings API honestly
    # reports an empty, unsupported registry via inherited
    # ``DefaultProvider`` behavior.

    # -------------------------------------------------------------------
    # Boot management
    # -------------------------------------------------------------------

    def boot_order(self) -> List[BootDevice]:
        """Return the configured persistent firmware boot order.

        Boot order is read through the standard UEFI mechanism (Linux:
        ``efibootmgr``; Windows: ``bcdedit /enum firmware``), which is
        available on any standards-compliant UEFI system regardless of
        manufacturer.
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
                    device_type=GenericUEFIProvider._boot_device_type(
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
        """Return best-effort, normalized Trusted Platform Module state.

        On Windows, uses ``Win32_Tpm`` (``root\\cimv2\\Security\\MicrosoftTpm``),
        a generic operating-system interface available regardless of
        manufacturer. On Linux, presence of a bound kernel TPM driver at
        ``/sys/class/tpm/tpm0`` is used -- also a generic, standards-based
        signal, not a vendor-specific one; ownership/activation state is
        not reliably readable from sysfs alone and is left at its honest
        default (``False``) rather than guessed.
        """
        if platform.system() == "Windows":
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
                enabled=bool(
                    self._safe_property_value(row, "IsEnabled_InitialValue")
                ),
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

        if platform.system() == "Linux":
            tpm_dir = Path("/sys/class/tpm/tpm0")
            if not tpm_dir.is_dir():
                return TPMState()

            version_major = self._read_text_file(tpm_dir / "tpm_version_major")
            return TPMState(
                present=True,
                enabled=True,
                spec_version=version_major or "",
            )

        return TPMState()

    # -------------------------------------------------------------------
    # Battery management
    # -------------------------------------------------------------------

    def battery_present(self) -> bool:
        """Return whether a battery is physically present in the system.

        On Windows, queried through the standard ``Win32_Battery`` class,
        a generic interface. On Linux, falls back to ``DefaultProvider``'s
        behavior, which checks ``/sys/class/power_supply``.
        """
        if platform.system() != "Windows":
            return super().battery_present()

        rows = self._query_wmi_safe(r"root\cimv2", "SELECT DeviceID FROM Win32_Battery")
        return bool(rows)

    # -------------------------------------------------------------------
    # Generic-provider extensions
    # -------------------------------------------------------------------

    def asset_tag(self) -> str:
        """Return the SMBIOS chassis asset tag, when available."""
        if platform.system() == "Linux":
            return self._read_text_file(Path("/sys/class/dmi/id/chassis_asset_tag"))

        if platform.system() != "Windows":
            return ""

        rows = self._query_wmi_safe(
            r"root\cimv2", "SELECT SMBIOSAssetTag FROM Win32_SystemEnclosure"
        )
        if not rows:
            return ""

        return str(self._safe_property_value(rows[0], "SMBIOSAssetTag") or "")

    def board_model(self) -> str:
        """Return the motherboard model reported by firmware."""
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
                "detected_manufacturer": self._firmware.manufacturer,
            }
        )
        return base_summary

    def report(self) -> Dict[str, Any]:
        """Return a detailed, non-sensitive provider and firmware report."""
        base_report = super().report()
        base_report["generic_uefi"] = {
            "board_model": self.board_model(),
            "asset_tag": self.asset_tag(),
            "detected_manufacturer": self._firmware.manufacturer,
            "tpm_state": self._serialize_value(self.tpm_state()),
            "bios_settings_management_available": False,
            "bios_settings_management_reason": (
                "No vendor-specific BIOS settings interface can exist for "
                "an unrecognized manufacturer; only firmware identity, "
                "standard UEFI boot order, and generic-interface TPM/"
                "battery presence are available on this provider."
            ),
        }
        return base_report

    def diagnostics(self) -> Dict[str, Any]:
        """Return sanitized provider diagnostic information."""
        base_diagnostics = super().diagnostics()
        base_diagnostics.update(
            {
                "efibootmgr_found": self._locate_efibootmgr() is not None,
                "detected_manufacturer": self._firmware.manufacturer,
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
                    "No vendor-specific provider matched this system, so "
                    "no BIOS settings management interface is available; "
                    "only firmware identity, standard UEFI boot order, "
                    "and generic-interface TPM/battery presence are "
                    "available on this provider."
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
                self._generic_logger.debug(
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
                self._generic_logger.debug(
                    "COM WMI query failed in %s: %s", namespace, exc
                )
                return []

    def _query_wmi_safe(self, namespace: str, query: str) -> List[Any]:
        """Run a WMI query and convert backend failures to an empty result."""
        try:
            return self._query_wmi(namespace, query)
        except Exception as exc:
            self._generic_logger.debug("WMI query was unavailable: %s", exc)
            return []

    # -------------------------------------------------------------------
    # Generic system and process helpers
    # -------------------------------------------------------------------

    @staticmethod
    def _first_property(rows: List[Any], name: str) -> str:
        for row in rows:
            value = GenericUEFIProvider._safe_property_value(row, name)
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
    "GenericUEFIProvider",
    "PROVIDER_VERSION",
]
