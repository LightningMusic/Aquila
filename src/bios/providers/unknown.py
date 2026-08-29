"""Unknown BIOS provider for Project Aquila.

Role in the provider registry (the true last resort):

This is the final fallback returned directly by ``BIOSDetection`` when
every registered provider -- every vendor-specific provider *and*
``GenericUEFIProvider`` -- has failed to match. Reaching this provider
means Aquila could not confirm standards-compliant UEFI firmware (see
``GenericUEFIProvider``'s module docstring: it already claims every system
where UEFI *is* confirmed, regardless of vendor). This provider therefore
makes the fewest possible assumptions about the firmware in front of it --
it may be legacy BIOS, an unusual or emulated firmware implementation, or a
system where firmware detection itself failed.

Backend reality (researched, not assumed):

Generic, vendor-neutral operating-system interfaces that do not depend on
UEFI being active -- ``Win32_BIOS`` / ``Win32_ComputerSystem`` WMI queries
on Windows, and ``/sys/class/dmi/id`` SMBIOS data on Linux -- are still
genuinely readable here and are used for real firmware identity, TPM
presence, and battery presence, exactly as they are for
``GenericUEFIProvider``.

What is deliberately **not** attempted here is boot-order management.
``efibootmgr`` requires ``/sys/firmware/efi`` (a UEFI kernel interface) and
``bcdedit /enum firmware`` targets the UEFI firmware boot menu -- neither
is a reliable, honest mechanism on firmware this provider cannot even
confirm is UEFI. Rather than invoke a boot-order tool that may silently
fail, return misleading empty output, or (in the worst case) target the
wrong boot menu entirely, this provider leaves boot-order management to
``DefaultProvider``'s honest in-memory-only default (an empty persistent
order, with ``set_boot_order`` reporting itself unsupported). All
individual BIOS setting management, virtualization/IOMMU/SR-IOV toggling,
Secure Boot toggling, BIOS password management, wake-source configuration,
and battery charge-limit management are likewise honestly unsupported, for
the same reason every other honest-thin provider reports them unsupported:
no vendor is known, so no vendor-specific interface can exist.
"""

from __future__ import annotations

import logging
import platform
import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

from ..models import (
    BIOSVendor,
    FirmwareInformation,
    TPMState,
)
from .base import ValidationError
from .default import DefaultProvider


PROVIDER_VERSION = "1.0.0"

logger = logging.getLogger(__name__)


class UnknownProvider(DefaultProvider):
    """Last-resort, maximally conservative BIOS provider.

    Selected only when no vendor-specific provider and not even
    ``GenericUEFIProvider`` could positively match the system. Supports
    real, vendor-neutral firmware identity and TPM/battery presence
    reporting; deliberately does not attempt boot-order management or any
    form of BIOS setting management, since no interface can be assumed
    safe or even applicable without knowing whether UEFI firmware is
    active at all.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize provider state without opening privileged resources."""
        super().__init__(*args, **kwargs)
        self._unknown_logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}"
        )
        self._wmi_handle: Any = None
        self._connected = False
        self._closed = False

    # -------------------------------------------------------------------
    # Identity, detection, and lifecycle
    # -------------------------------------------------------------------

    def vendor(self) -> BIOSVendor:
        """Return ``BIOSVendor.UNKNOWN`` unconditionally.

        This intentionally does not defer to a manufacturer string that
        may have been read from DMI/WMI (unlike ``DefaultProvider.vendor()``,
        which would happily report a real vendor if one happens to be
        readable) -- if a vendor were confidently known, a more specific
        provider would already have matched instead of this one. The raw
        manufacturer string, when available, remains visible through
        ``firmware_information().manufacturer``.
        """
        return BIOSVendor.UNKNOWN

    def provider_name(self) -> str:
        """Return the stable provider name."""
        return "unknown"

    def provider_version(self) -> str:
        """Return the Unknown provider implementation version."""
        return PROVIDER_VERSION

    def supports_windows(self) -> bool:
        """Return whether this provider supports Windows hosts."""
        return True

    def supports_linux(self) -> bool:
        """Return whether this provider supports Linux hosts."""
        return True

    def detect(self) -> bool:
        """Always match.

        This provider is the registry's final fallback and is only ever
        instantiated directly by ``BIOSDetection`` after every other
        provider, including ``GenericUEFIProvider``, has failed to match.
        """
        return True

    def detection_confidence(self) -> float:
        """Return a fixed, minimal confidence value.

        Present for interface symmetry with other providers; Aquila's
        detection logic does not rank ``UnknownProvider`` against
        anything else since it is never part of the ranked registry.
        """
        return 0.0

    def connect(self) -> bool:
        """Establish the provider and load current firmware information."""
        self._closed = False
        self._record_operation("connect")

        try:
            self._firmware = self._collect_firmware_information()
            self._cache_valid = True
        except Exception as exc:
            self._cache_valid = False
            self._record_error(
                "connect", f"Unable to collect firmware information: {exc}"
            )
            self._connected = False
            return False

        self._connected = True
        return True

    def disconnect(self) -> None:
        """Disconnect from the firmware interface and release resources."""
        self._record_operation("disconnect")
        self._connected = False
        self._wmi_handle = None
        self._transaction_active = False

    def is_connected(self) -> bool:
        """Return whether the provider is connected and ready."""
        return self._connected

    def refresh(self) -> bool:
        """Refresh cached firmware information."""
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
        """Collect whatever generic firmware identity information is available.

        On Windows this queries ``Win32_BIOS`` / ``Win32_ComputerSystem`` --
        generic operating-system interfaces available regardless of
        firmware type. On Linux, ``DefaultProvider``'s existing
        ``/sys/class/dmi/id`` collection is reused directly. In both cases
        the resulting ``vendor`` field is forced to ``BIOSVendor.UNKNOWN``
        (see ``vendor()``); the raw manufacturer string is preserved
        unmodified for inventory purposes.
        """
        if platform.system() != "Windows":
            info = super()._collect_firmware_information()
            info.vendor = BIOSVendor.UNKNOWN
            return info

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

        manufacturer = self._first_property(system_rows, "Manufacturer") or ""
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
            vendor=BIOSVendor.UNKNOWN,
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

    # -------------------------------------------------------------------
    # Boot management
    # -------------------------------------------------------------------

    # Deliberately not overridden -- see the module docstring. Boot-order
    # management through ``efibootmgr``/``bcdedit`` assumes UEFI firmware,
    # which this provider cannot confirm; ``DefaultProvider``'s honest
    # empty/in-memory-only default is used unmodified.

    # -------------------------------------------------------------------
    # TPM and platform security
    # -------------------------------------------------------------------

    def tpm_supported(self) -> bool:
        return bool(self.tpm_state().present)

    def tpm_enabled(self) -> bool:
        return self.tpm_state().enabled

    def tpm_state(self) -> TPMState:
        """Return best-effort, normalized Trusted Platform Module state.

        Uses ``Win32_Tpm`` on Windows and presence of a bound kernel TPM
        driver at ``/sys/class/tpm/tpm0`` on Linux -- both generic,
        standards-based signals independent of firmware type or vendor.
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

        On Windows, queried through the standard ``Win32_Battery`` class.
        On Linux, falls back to ``DefaultProvider``'s behavior, which
        checks ``/sys/class/power_supply``.
        """
        if platform.system() != "Windows":
            return super().battery_present()

        rows = self._query_wmi_safe(r"root\cimv2", "SELECT DeviceID FROM Win32_Battery")
        return bool(rows)

    # -------------------------------------------------------------------
    # Reporting and diagnostics
    # -------------------------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """Return a concise, non-sensitive provider summary."""
        base_summary = super().summary()
        base_summary.update(
            {
                "detected_manufacturer": self._firmware.manufacturer,
                "confirmed_uefi": False,
            }
        )
        return base_summary

    def report(self) -> Dict[str, Any]:
        """Return a detailed, non-sensitive provider and firmware report."""
        base_report = super().report()
        base_report["unknown"] = {
            "detected_manufacturer": self._firmware.manufacturer,
            "tpm_state": self._serialize_value(self.tpm_state()),
            "boot_order_management_available": False,
            "boot_order_management_reason": (
                "Standards-compliant UEFI firmware could not be confirmed "
                "for this system, so no boot-order management tool "
                "(efibootmgr / bcdedit firmware entries) can be safely "
                "assumed to apply."
            ),
            "bios_settings_management_available": False,
            "bios_settings_management_reason": (
                "No vendor could be identified for this system, so no "
                "BIOS settings management interface is available."
            ),
        }
        return base_report

    def diagnostics(self) -> Dict[str, Any]:
        """Return sanitized provider diagnostic information."""
        base_diagnostics = super().diagnostics()
        base_diagnostics.update(
            {
                "detected_manufacturer": self._firmware.manufacturer,
                "confirmed_uefi": False,
                "boot_order_management_available": False,
                "bios_settings_management_available": False,
            }
        )
        return base_diagnostics

    def validate_configuration(self) -> List[ValidationError]:
        """Return validation failures for the current configuration."""
        issues = super().validate_configuration()

        issues.append(
            ValidationError(
                field="firmware_vendor",
                message=(
                    "No supported firmware vendor could be identified, "
                    "and standards-compliant UEFI firmware could not be "
                    "confirmed; only best-effort firmware identity and "
                    "TPM/battery presence are available on this provider."
                ),
                code="firmware_vendor_unidentified",
                severity="warning",
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
            self._unknown_logger.debug(
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
            self._unknown_logger.debug(
                "COM WMI query failed in %s: %s", namespace, exc
            )
            return []

    def _query_wmi_safe(self, namespace: str, query: str) -> List[Any]:
        """Run a WMI query and convert backend failures to an empty result."""
        try:
            return self._query_wmi(namespace, query)
        except Exception as exc:
            self._unknown_logger.debug("WMI query was unavailable: %s", exc)
            return []

    # -------------------------------------------------------------------
    # Generic system helpers
    # -------------------------------------------------------------------

    @staticmethod
    def _first_property(rows: List[Any], name: str) -> str:
        for row in rows:
            value = UnknownProvider._safe_property_value(row, name)
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
        """Run a subprocess without a shell and capture bounded output.

        Provided for interface symmetry with other providers; this
        provider does not currently invoke any external process itself.
        """
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
    "UnknownProvider",
    "PROVIDER_VERSION",
]
