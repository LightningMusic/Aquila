"""
Project Aquila
=============

Disk Sanitizer

Implements REQ-PREP-008 through REQ-PREP-018 -- the actual storage
sanitization operation, its immediately-preceding safety checks, and
its progress/result reporting.

Sanitization mechanism (QUICK / FULL)
--------------------------------------
Both methods invoke ``MSFT_Disk.Clear(RemoveData, RemoveOEM,
ZeroOutEntireDisk)`` in the ``root\\Microsoft\\Windows\\Storage``
namespace (the Windows Storage Management API, Windows 8 / Server 2012
and newer) -- the same namespace ``hardware.storage.StorageDetector``
already queries via ``MSFT_PhysicalDisk``. Per Microsoft's documented
behavior (learn.microsoft.com/windows-hardware/drivers/storage/
clear-msft-disk):

* ``ZeroOutEntireDisk=False`` (QUICK) zeroes only the first and last
  megabyte of the disk and removes partition information -- the same
  semantics as ``diskpart clean``.
* ``ZeroOutEntireDisk=True`` (FULL) additionally zeroes the entire
  disk -- the same semantics as ``diskpart clean all``.

This is a genuine, Microsoft-documented disk-management API, not a
best-effort heuristic: ``Clear()`` returns a ``UInt32`` result code
(0 = Success) plus an ``ExtendedStatus`` string, both of which this
module inspects and reports rather than assuming success.

Why the WMI *method* call never goes through ``hardware.query_wmi``
---------------------------------------------------------------------
``hardware.query_wmi``/``query_wmi_safe`` are deliberately restricted
(REQ-INS-026) to read-only ``SELECT``/``ASSOCIATORS OF`` statements --
raising ``ValueError`` on anything else. Invoking ``MSFT_Disk.Clear()``
is not a query at all; it is a WMI *method call* against a specific
object instance, and it is the single most destructive operation this
codebase performs. Reusing or relaxing the Inspection Engine's
read-only helper to allow it would silently weaken REQ-INS-026's
guarantee for every other caller of that helper. This module therefore
defines its own, separate, clearly-labeled ``WmiMethodCaller`` --
scoped to this file, used nowhere else -- and still uses
``hardware.query_wmi_safe`` (unmodified) for every genuinely read-only
step (looking up the target ``MSFT_Disk`` instance, re-verifying its
identity, and reading back its state for the Preparation Verifier).

ATA / NVMe hardware Secure Erase
----------------------------------
REQ-PREP-014 lists ATA Secure Erase and NVMe Secure Erase as supported
methods "when supported". Research against Microsoft's own driver
documentation found that Windows itself restricts both to WinPE:

* ATA Security Group commands (the SECURITY ERASE UNIT command
  SECURE ERASE relies on) have been blocked outside WinPE since
  Windows 8 -- see learn.microsoft.com/windows-hardware/drivers/
  storage/security-group-commands -- and require a specific
  precondition sequence (no SECURITY FREEZE LOCK issued, AHCI mode)
  that only a WinPE-hosted tool can arrange.
* NVMe Sanitize/Format via ``IOCTL_STORAGE_PROTOCOL_COMMAND`` is
  documented as WinPE-only prior to Windows 11 / Server 2022.
* Neither ``MSFT_Disk`` nor ``MSFT_PhysicalDisk`` exposes a secure-
  erase method at all -- the only path is the raw
  ``IOCTL_ATA_PASS_THROUGH_DIRECT`` / ``IOCTL_STORAGE_PROTOCOL_COMMAND``
  kernel IOCTLs, built from C struct layouts (``ATA_PASS_THROUGH_
  DIRECT``, ``NVME_CDW10_FORMAT_NVM``) whose precise numeric
  ``CTL_CODE`` values are defined in the Windows Driver Kit's C
  headers, not in any Microsoft Learn page this module's research
  could reach.

Given GP-001 ("Automation shall never perform irreversible actions
without explicit operator authorization") and the fact that a wrong
IOCTL layout on a *destructive* disk command is not a bug that fails
safely, this module implements genuine, honest capability detection
for both methods (bus-type classification, WinPE-environment
detection) but the erase attempt itself always raises
``DeploymentSanitizationError`` naming the specific Windows-imposed
restriction, rather than shipping an unverified raw-IOCTL
implementation against real customer hardware. This is the same
"detect and report the real limitation, never fabricate" convention
``bios.py`` (Secure Boot status on Legacy BIOS) and ``smart.py``
(unsupported SMART attributes) already follow -- it is honest
degradation, not a stub: QUICK and FULL are fully implemented and
always available, and every REQ-PREP-014 method is genuinely detected
and truthfully reported.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Protocol, cast

from common.constants.logging import PREPARATION_LOGGER
from common.enums import SanitizationMethod
from common.exceptions.deployment import DeploymentSanitizationError
from hardware import is_windows, query_wmi_safe, safe_property_value
from hardware.storage import StorageDetector
from models.hardware.storage import StorageDevice

#: Logs through the dedicated "aquila.preparation" logger -- see
#: recovery.recovery_manager's identical rationale: a future LogManager
#: will only attach a file handler to the exact names defined in
#: common.constants.logging, never to logging.getLogger(__name__).
logger = logging.getLogger(PREPARATION_LOGGER)

_STORAGE_NAMESPACE = r"root\Microsoft\Windows\Storage"

_DISK_QUERY_FIELDS = (
    "Number, Path, UniqueId, Size, PartitionStyle, NumberOfPartitions, "
    "IsOffline, IsReadOnly, IsBoot, IsSystem, BusType"
)

#: Matches the physical-drive index out of a Windows device path such
#: as ``\\.\PHYSICALDRIVE0``. The same pattern
#: ``recovery.browser._PHYSICAL_DRIVE_INDEX_PATTERN`` uses, kept as
#: its own copy here rather than imported -- that name is private to
#: ``recovery.browser`` (not exported), and each subsystem already
#: owns its own device-path parsing (``hardware.storage`` does too).
_PHYSICAL_DRIVE_INDEX_PATTERN = re.compile(r"PHYSICALDRIVE(\d+)", re.IGNORECASE)

#: MSFT_Disk.BusType values relevant to ATA/NVMe capability detection
#: (learn.microsoft.com/windows-hardware/drivers/storage/msft-disk) --
#: the same numbering ``hardware.storage`` already uses for
#: MSFT_PhysicalDisk.BusType.
_BUS_TYPE_ATA = 3
_BUS_TYPE_SATA = 11
_BUS_TYPE_NVME = 17

#: MSFT_Disk.Clear() UInt32 return codes, confirmed against
#: learn.microsoft.com/windows-hardware/drivers/storage/clear-msft-disk.
_CLEAR_RETURN_CODES: dict[int, str] = {
    0: "Success",
    1: "Not supported",
    2: "Unspecified error",
    3: "Timeout",
    4: "Failed",
    5: "Invalid parameter",
    6: "Disk is in use",
    40001: "Access denied",
    40002: "There are not enough resources to complete the operation",
    40003: "Cache out of date",
    41000: "The disk has not been initialized",
    41002: "The disk is read only",
    41003: "The disk is offline",
    41007: (
        "Cannot clear with OEM partitions present "
        "(RemoveOEM was not honored)"
    ),
    41008: (
        "Cannot clear with data partitions present "
        "(RemoveData was not honored)"
    ),
    41009: "Operation not supported on a critical disk",
    41015: "There is no media in the device",
    41019: (
        "The disk is managed by Microsoft Failover Clustering and must "
        "be removed from the cluster first"
    ),
}


class DiskSanitizerError(DeploymentSanitizationError):
    """Raised for any Preparation-stage sanitization failure."""


def resolve_disk_number(device_path: str) -> int:
    """
    Resolve the ``MSFT_Disk``/``Win32_DiskDrive`` disk number out of a
    Windows physical-drive device path (``\\\\.\\PHYSICALDRIVEn``).

    A module-level function -- rather than a private method -- so
    ``preparation.preparation_manager`` can resolve the same disk
    number ``DiskSanitizer`` used internally (for example, to hand it
    to ``preparation.verifier.SanitizationVerifier``) without
    duplicating this parsing logic a third time.

    Raises:
        DiskSanitizerError: If ``device_path`` does not contain a
            recognizable ``PHYSICALDRIVEn`` segment.
    """

    match = _PHYSICAL_DRIVE_INDEX_PATTERN.search(device_path)
    if match is None:
        raise DiskSanitizerError(
            f"Could not resolve a physical disk number from device "
            f"path '{device_path}' -- expected a path of the form "
            r"\\.\PHYSICALDRIVEn."
        )
    return int(match.group(1))


# ---------------------------------------------------------------------------
# Progress reporting
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class SanitizationProgress:
    """
    A single progress update emitted while sanitizing one device
    (REQ-PREP-015).

    ``percent_complete`` is deliberately ``None`` for every stage:
    ``MSFT_Disk.Clear()`` is a single, synchronous, blocking WMI call
    with no native progress-percentage channel (unlike, for example, a
    chunked file copy). Reporting a fabricated percentage here would
    violate this project's honesty-over-fabrication convention just as
    surely as reporting a fabricated success would; REQ-PREP-016's
    "estimated completion time whenever practical" is satisfied by
    ``stage``/``message`` marking real transitions (started, WMI call
    issued, completed) rather than an invented ETA.
    """

    device_path: str
    stage: str
    message: str


ProgressCallback = Callable[[SanitizationProgress], None]


# ---------------------------------------------------------------------------
# WMI method invocation (dangerous by design -- see module docstring)
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class WmiClearResult:
    """The raw result of one ``MSFT_Disk.Clear()`` invocation."""

    return_code: int
    extended_status: str


class WmiMethodCaller(Protocol):
    """
    Invokes a mutating WMI method against a specific ``MSFT_Disk``
    instance.

    Deliberately a narrow, single-purpose interface (one method, one
    WMI call) rather than a general "run any WMI method" helper --
    the entire point of keeping this separate from
    ``hardware.query_wmi`` is that nothing in this codebase should be
    able to invoke an arbitrary, unreviewed WMI method by construction.
    """

    def clear_disk(
        self,
        *,
        disk_number: int,
        remove_data: bool,
        remove_oem: bool,
        zero_out_entire_disk: bool,
    ) -> WmiClearResult:
        ...


class _DefaultWmiMethodCaller:
    """
    Real ``MSFT_Disk.Clear()`` invocation against the live system.

    Tries the ``wmi`` package first, then falls back to raw
    ``win32com.client`` COM automation -- the same two backends
    ``hardware.query_wmi`` uses, so any system that can run Aquila's
    other WMI-dependent detectors can run this too. Both are optional,
    Windows-only dependencies; on any other platform this raises
    ``DiskSanitizerError`` rather than pretending to succeed, since
    silently no-op'ing a sanitization request would be far more
    dangerous than failing loudly.
    """

    def clear_disk(
        self,
        *,
        disk_number: int,
        remove_data: bool,
        remove_oem: bool,
        zero_out_entire_disk: bool,
    ) -> WmiClearResult:
        if not is_windows():
            raise DiskSanitizerError(
                "Disk sanitization requires Windows; the current "
                "platform is not supported."
            )

        try:
            import wmi  # type: ignore[import-untyped]

            connection = wmi.WMI(namespace=_STORAGE_NAMESPACE)
            disks = connection.MSFT_Disk(Number=disk_number)
            if not disks:
                raise DiskSanitizerError(
                    f"MSFT_Disk with Number={disk_number} was not found "
                    "-- it may have been removed or renumbered since "
                    "inspection."
                )

            raw_result: Any = disks[0].Clear(
                RemoveData=remove_data,
                RemoveOEM=remove_oem,
                ZeroOutEntireDisk=zero_out_entire_disk,
            )
            # The ``wmi`` package returns method out-parameters as a
            # tuple in declaration order: (ReturnValue, ExtendedStatus).
            if isinstance(raw_result, tuple) and len(cast("tuple[Any, ...]", raw_result)) >= 1:
                result_tuple = cast("tuple[Any, ...]", raw_result)
                return_code = int(result_tuple[0])
                extended_status = (
                    str(result_tuple[1]) if len(result_tuple) > 1 else ""
                )
            else:
                return_code = int(cast(Any, raw_result))
                extended_status = ""

            return WmiClearResult(
                return_code=return_code, extended_status=extended_status
            )
        except ImportError:
            pass
        except DiskSanitizerError:
            raise
        except Exception as exc:
            logger.debug(
                "Python 'wmi' package Clear() call failed for disk %d: %s",
                disk_number,
                exc,
            )
            raise DiskSanitizerError(
                f"MSFT_Disk.Clear() failed for disk {disk_number}: {exc}"
            ) from exc

        try:
            import win32com.client  # type: ignore[import-untyped]

            locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
            service = locator.ConnectServer(".", _STORAGE_NAMESPACE)
            service.Security_.ImpersonationLevel = 3

            rows = list(
                service.ExecQuery(
                    "SELECT * FROM MSFT_Disk WHERE Number = " f"{disk_number}",
                    "WQL",
                    0x10 | 0x20,
                )
            )
            if not rows:
                raise DiskSanitizerError(
                    f"MSFT_Disk with Number={disk_number} was not found "
                    "-- it may have been removed or renumbered since "
                    "inspection."
                )

            disk_object = rows[0]
            in_params = disk_object.Methods_("Clear").InParameters.SpawnInstance_()
            in_params.RemoveData = remove_data
            in_params.RemoveOEM = remove_oem
            in_params.ZeroOutEntireDisk = zero_out_entire_disk

            out_params = service.ExecMethod(
                disk_object.Path_.Path, "Clear", in_params
            )
            return_code = int(getattr(out_params, "ReturnValue", 2))
            extended_status = str(getattr(out_params, "ExtendedStatus", "") or "")
            return WmiClearResult(
                return_code=return_code, extended_status=extended_status
            )
        except ImportError as exc:
            raise DiskSanitizerError(
                "Neither the 'wmi' package nor 'win32com.client' is "
                "available -- disk sanitization requires one of them "
                "on Windows."
            ) from exc
        except DiskSanitizerError:
            raise
        except Exception as exc:
            logger.debug(
                "COM Clear() call failed for disk %d: %s", disk_number, exc
            )
            raise DiskSanitizerError(
                f"MSFT_Disk.Clear() failed for disk {disk_number}: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Execution result
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class SanitizationExecutionResult:
    """The outcome of one ``DiskSanitizer.sanitize()`` call."""

    device_path: str
    method: SanitizationMethod
    started_at: datetime
    completed_at: datetime
    succeeded: bool
    return_code: int | None
    extended_status: str
    message: str

    @property
    def duration_seconds(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()


# ---------------------------------------------------------------------------
# Disk sanitizer
# ---------------------------------------------------------------------------


class DiskSanitizer:
    """
    Sanitizes a single, previously-verified target storage device
    (REQ-PREP-013 through REQ-PREP-018).
    """

    def __init__(
        self,
        *,
        method_caller: WmiMethodCaller | None = None,
        storage_detector: StorageDetector | None = None,
    ) -> None:
        self._method_caller: WmiMethodCaller = method_caller or _DefaultWmiMethodCaller()
        self._storage_detector = storage_detector or StorageDetector()

    def sanitize(
        self,
        device: StorageDevice,
        method: SanitizationMethod,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> SanitizationExecutionResult:
        """
        Sanitize ``device`` using ``method``.

        Raises:
            DiskSanitizerError: If ``device`` is removable/boot media
                (REQ-PREP-012, defense in depth), if its identity
                cannot be freshly re-verified immediately before
                sanitizing (REQ-PREP-008/009/010/011), if the disk
                number cannot be resolved from ``device.device_path``,
                or if the underlying WMI operation itself fails or
                reports a non-success return code.
            DeploymentSanitizationError: For ATA_SECURE_ERASE /
                NVME_SECURE_ERASE, always -- see the module docstring's
                "ATA / NVMe hardware Secure Erase" section.
        """

        self._report(progress_callback, device.device_path, "starting", (
            f"Preparing to sanitize {device.device_path} "
            f"using {method.name}."
        ))

        # REQ-PREP-012, defense in depth: StorageInventory.
        # eligible_for_deployment() should already have excluded this
        # device upstream (in PreparationManager), but sanitization is
        # irreversible enough to re-check here too rather than trust a
        # single call site.
        if device.is_removable or device.is_boot_media:
            raise DiskSanitizerError(
                f"Refusing to sanitize {device.device_path}: it is "
                "flagged as removable or boot media, and the "
                "deployment USB must never be eligible for "
                "sanitization (REQ-PREP-012)."
            )

        fresh_device = self._reverify_identity(device)

        if method in (SanitizationMethod.QUICK, SanitizationMethod.FULL):
            return self._clear(fresh_device, method, progress_callback)

        # ATA_SECURE_ERASE / NVME_SECURE_ERASE.
        self._refuse_unsupported_secure_erase(fresh_device, method)
        raise AssertionError("unreachable")  # pragma: no cover

    # ------------------------------------------------------------------
    # REQ-PREP-008/009/010/011: fresh identity re-verification
    # ------------------------------------------------------------------

    def _reverify_identity(self, device: StorageDevice) -> StorageDevice:
        """
        Re-query storage immediately before sanitizing and confirm
        ``device`` still matches what Inspection/Preparation originally
        selected.

        Reuses ``hardware.storage.StorageDetector`` (the exact same
        detector Inspection uses) rather than a second, parallel
        storage-enumeration implementation -- REQ-PREP-008/009 require
        detecting *changes since inspection*, and re-running the
        identical detection pass is the most direct way to detect one.
        """

        fresh_inventory = self._storage_detector.detect()
        fresh_device = fresh_inventory.find_by_path(device.device_path)

        if fresh_device is None:
            raise DiskSanitizerError(
                f"Target storage device {device.device_path} could not "
                "be found on a fresh re-scan -- sanitization cannot "
                "begin (REQ-PREP-009: storage configuration changed "
                "since inspection; a new inspection is required)."
            )

        identity_matches = device.matches_identity(
            device_path=fresh_device.device_path,
            capacity_bytes=fresh_device.capacity_bytes,
            manufacturer=fresh_device.manufacturer,
            model=fresh_device.model,
            serial_number=fresh_device.serial_number,
        )
        if not identity_matches:
            # REQ-PREP-011 ("If storage identity cannot be verified,
            # sanitization shall not begin"): this is that refusal --
            # an identity mismatch against REQ-PREP-010's identifiers
            # raises before ``_clear``/``_refuse_unsupported_secure_erase``
            # (the actual destructive calls) is ever reached.
            raise DiskSanitizerError(
                f"Target storage device {device.device_path} no longer "
                "matches its previously verified identity (capacity, "
                "manufacturer, model, or serial number changed) -- "
                "sanitization cannot begin (REQ-PREP-010/011)."
            )

        if fresh_device.is_removable or fresh_device.is_boot_media:
            raise DiskSanitizerError(
                f"Refusing to sanitize {fresh_device.device_path}: a "
                "fresh re-scan flags it as removable or boot media "
                "(REQ-PREP-012)."
            )

        return fresh_device

    # ------------------------------------------------------------------
    # QUICK / FULL: MSFT_Disk.Clear()
    # ------------------------------------------------------------------

    def _clear(
        self,
        device: StorageDevice,
        method: SanitizationMethod,
        progress_callback: ProgressCallback | None,
    ) -> SanitizationExecutionResult:
        disk_number = resolve_disk_number(device.device_path)
        zero_out_entire_disk = method is SanitizationMethod.FULL

        started_at = datetime.now(UTC)
        # REQ-PREP-020 ("shall log every sanitization operation"): start,
        # failure, and completion of this MSFT_Disk.Clear() call are all
        # logged below, not just the final outcome.
        logger.info(
            "Sanitizing %s (disk %d) using %s (ZeroOutEntireDisk=%s).",
            device.device_path,
            disk_number,
            method.name,
            zero_out_entire_disk,
        )
        self._report(
            progress_callback,
            device.device_path,
            "clearing",
            (
                f"Invoking MSFT_Disk.Clear() on disk {disk_number} "
                f"({method.name}). This call blocks until Windows "
                "reports completion; no incremental progress is "
                "available from this API."
            ),
        )

        try:
            result = self._method_caller.clear_disk(
                disk_number=disk_number,
                remove_data=True,
                remove_oem=True,
                zero_out_entire_disk=zero_out_entire_disk,
            )
        except DiskSanitizerError as exc:
            completed_at = datetime.now(UTC)
            logger.error(
                "Sanitization of %s failed: %s", device.device_path, exc
            )
            self._report(
                progress_callback, device.device_path, "failed", str(exc)
            )
            return SanitizationExecutionResult(
                device_path=device.device_path,
                method=method,
                started_at=started_at,
                completed_at=completed_at,
                succeeded=False,
                return_code=None,
                extended_status="",
                message=str(exc),
            )

        completed_at = datetime.now(UTC)
        succeeded = result.return_code == 0
        description = _CLEAR_RETURN_CODES.get(
            result.return_code, f"Unrecognized return code {result.return_code}"
        )
        message = (
            f"MSFT_Disk.Clear() returned {result.return_code} "
            f"({description})."
        )
        if result.extended_status:
            message = f"{message} ExtendedStatus: {result.extended_status}"

        if succeeded:
            logger.info("Sanitization of %s completed: %s", device.device_path, message)
            self._report(progress_callback, device.device_path, "completed", message)
        else:
            logger.error("Sanitization of %s failed: %s", device.device_path, message)
            self._report(progress_callback, device.device_path, "failed", message)

        return SanitizationExecutionResult(
            device_path=device.device_path,
            method=method,
            started_at=started_at,
            completed_at=completed_at,
            succeeded=succeeded,
            return_code=result.return_code,
            extended_status=result.extended_status,
            message=message,
        )

    # ------------------------------------------------------------------
    # ATA_SECURE_ERASE / NVME_SECURE_ERASE: honest refusal
    # ------------------------------------------------------------------

    def _refuse_unsupported_secure_erase(
        self, device: StorageDevice, method: SanitizationMethod
    ) -> None:
        """
        Always raises -- see the module docstring's "ATA / NVMe
        hardware Secure Erase" section for why. Still performs genuine
        capability detection so the raised message tells the
        technician exactly what was found and why it changes nothing,
        rather than a single generic refusal for every drive.
        """

        disk_number = resolve_disk_number(device.device_path)
        bus_type = self._query_bus_type(disk_number)
        winpe = _is_winpe()

        if method is SanitizationMethod.ATA_SECURE_ERASE:
            if bus_type not in (_BUS_TYPE_ATA, _BUS_TYPE_SATA):
                raise DiskSanitizerError(
                    f"{device.device_path} does not report an ATA/SATA "
                    f"bus (detected MSFT_Disk.BusType={bus_type}) -- "
                    "ATA Secure Erase is not applicable to this device."
                )
            raise DiskSanitizerError(
                f"{device.device_path} is an ATA/SATA device, but "
                "Windows has restricted the ATA Security Group "
                "commands SECURE ERASE relies on to WinPE-hosted tools "
                "since Windows 8, and requires a specific precondition "
                "sequence (no SECURITY FREEZE LOCK issued, AHCI mode) "
                "that this build does not implement via raw "
                "IOCTL_ATA_PASS_THROUGH_DIRECT calls. "
                f"Current environment {'is' if winpe else 'is not'} "
                "WinPE. Use FULL sanitization instead, which is fully "
                "supported and available on every device."
            )

        if bus_type != _BUS_TYPE_NVME:
            raise DiskSanitizerError(
                f"{device.device_path} does not report an NVMe bus "
                f"(detected MSFT_Disk.BusType={bus_type}) -- NVMe "
                "Secure Erase is not applicable to this device."
            )
        raise DiskSanitizerError(
            f"{device.device_path} is an NVMe device, but the NVMe "
            "Format/Sanitize command Windows exposes via "
            "IOCTL_STORAGE_PROTOCOL_COMMAND is documented as WinPE-only "
            "prior to Windows 11 / Server 2022, and no MSFT_Disk or "
            "MSFT_PhysicalDisk WMI method performs it -- only a raw "
            "IOCTL with an NVME_CDW10_FORMAT_NVM struct layout this "
            f"build does not implement. Current environment "
            f"{'is' if winpe else 'is not'} WinPE. Use FULL "
            "sanitization instead, which is fully supported and "
            "available on every device."
        )

    def _query_bus_type(self, disk_number: int) -> int | None:
        rows = query_wmi_safe(
            _STORAGE_NAMESPACE,
            f"SELECT {_DISK_QUERY_FIELDS} FROM MSFT_Disk WHERE Number = "
            f"{disk_number}",
        )
        if not rows:
            return None

        raw_bus_type = safe_property_value(rows[0], "BusType")
        try:
            return int(raw_bus_type) if raw_bus_type is not None else None
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _report(
        progress_callback: ProgressCallback | None,
        device_path: str,
        stage: str,
        message: str,
    ) -> None:
        if progress_callback is None:
            return

        try:
            progress_callback(
                SanitizationProgress(
                    device_path=device_path, stage=stage, message=message
                )
            )
        except Exception:  # pragma: no cover - progress reporting is best-effort
            logger.debug("Sanitization progress callback raised.", exc_info=True)


def _is_winpe() -> bool:
    """
    Best-effort detection of whether the current environment is
    Windows PE.

    Checks for ``HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion
    \\WinPE`` -- the registry key Microsoft's own documentation
    directs administrators to for identifying a running WinPE instance
    (learn.microsoft.com/windows-hardware/manufacture/desktop/
    whats-new-in-windows-pe). Returns ``False`` -- rather than raising
    -- on any non-Windows platform, missing ``winreg``, or registry
    access failure; this is diagnostic context for an already-refused
    operation (see ``_refuse_unsupported_secure_erase``), never a gate
    that changes what this module allows.
    """

    if not is_windows():
        return False

    try:
        import winreg  # type: ignore[import-not-found]

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\WinPE",
        ):
            return True
    except Exception:
        return False


__all__ = [
    "DiskSanitizer",
    "DiskSanitizerError",
    "ProgressCallback",
    "SanitizationExecutionResult",
    "SanitizationProgress",
    "WmiClearResult",
    "WmiMethodCaller",
    "resolve_disk_number",
]
