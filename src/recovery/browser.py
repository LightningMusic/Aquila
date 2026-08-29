"""
Project Aquila
=============

Volume and Filesystem Browsing

Implements REQ-REC-002 (identify all readable storage volumes),
REQ-REC-003 (enumerate accessible file systems on each volume),
REQ-REC-004 (present discovered volumes to the technician), and
REQ-REC-005 (allow the technician to browse the contents of detected
volumes).

On the name "browser"
----------------------
This module is named ``browser.py`` after REQ-REC-004/005's own
language -- "browse the contents of detected storage volumes" -- and
implements exactly that: read-only *filesystem* browsing of the
volumes discovered on the target system. It does **not** implement
recovery of an installed web browser's own saved data (bookmarks,
saved passwords, extensions).

``common.exceptions.recovery`` does pre-define a broader vocabulary
that includes web-browser-specific exceptions
(``BrowserProfileError``, ``BrowserBookmarkError``,
``BrowserPasswordError``, ``BrowserExtensionError``) alongside
archive (``ArchiveError`` and subclasses) and restore-to-original-
location (``RestoreError`` and subclasses) exceptions. None of that
is used here, deliberately: the current SRS's REQ-REC-* section
describes only generic volume discovery, filesystem browsing, and
technician-selected file/directory copying -- it does not specify a
web-browser-profile-recovery, archiving, or restore-in-place feature.
Per GP-010 ("No production feature shall be implemented before its
behavior has been documented within this Software Requirements
Specification"), that broader exception vocabulary is left
unused/reserved rather than given a speculative implementation here;
should a future SRS revision add those requirements, the exceptions
already exist to support them without a ``common/`` change.

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
from pathlib import Path

from common.constants.logging import RECOVERY_LOGGER
from common.exceptions.recovery import RecoveryDiscoveryError
from hardware import is_windows, query_wmi_safe, safe_property_value
from models.hardware import StorageInventory

# Logs through the dedicated "aquila.recovery" logger -- see
# hardware.battery's fix (src/hardware/battery.py) for why
# logging.getLogger(__name__) would be wrong here: LogManager only
# attaches a file handler to the exact names in
# common.constants.logging, and this module's dotted name
# ("recovery.browser") is not one of them.
logger = logging.getLogger(RECOVERY_LOGGER)

_CIMV2_NAMESPACE = r"root\cimv2"

_LOGICAL_DISK_QUERY = (
    "SELECT DeviceID, DriveType, FileSystem, FreeSpace, Size, VolumeName "
    "FROM Win32_LogicalDisk"
)

# Win32_LogicalDisk.DriveType -- confirmed via Microsoft Learn
# (learn.microsoft.com/windows/win32/cimwin32prov/win32-logicaldisk):
# 0=Unknown, 1=No Root Directory, 2=Removable Disk, 3=Local Disk,
# 4=Network Drive, 5=Compact Disc, 6=RAM Disk. Recovery only ever
# reads from locally-attached, real filesystems -- network shares and
# optical media are neither "the target system's own data" nor
# writable/removable in the way REQ-REC-002 anticipates, and RAM
# disks hold nothing surviving a reboot.
_DRIVE_TYPE_REMOVABLE = 2
_DRIVE_TYPE_LOCAL_FIXED = 3
_DISCOVERABLE_DRIVE_TYPES = {_DRIVE_TYPE_REMOVABLE, _DRIVE_TYPE_LOCAL_FIXED}

_PHYSICAL_DRIVE_INDEX_PATTERN = re.compile(r"PHYSICALDRIVE(\d+)", re.IGNORECASE)


@dataclass(slots=True, frozen=True)
class RecoveryVolume:
    """
    One readable storage volume discovered on the target system.

    ``root_path`` is stored explicitly (computed once, at discovery
    time, from ``device_id``) rather than derived on demand from
    ``device_id`` -- this keeps volume construction and filesystem
    access decoupled, so tests can exercise ``VolumeBrowser.browse()``
    against a real temporary directory without needing a Windows
    drive letter to exist.
    """

    device_id: str  # e.g. "C:"
    root_path: Path
    volume_name: str
    file_system: str
    capacity_bytes: int
    free_capacity_bytes: int
    is_removable: bool
    backing_disk_is_boot_media: bool


@dataclass(slots=True, frozen=True)
class RecoveryEntry:
    """One file or directory found while browsing a volume."""

    name: str
    relative_path: str
    is_directory: bool
    size_bytes: int | None
    modified_at: datetime | None
    readable: bool


class VolumeBrowser:
    """
    Discovers readable storage volumes and browses their contents
    without modifying anything (REQ-REC-018/019/020: recovery
    operations never alter, delete, or modify the metadata of source
    files).
    """

    # ------------------------------------------------------------------
    # Volume discovery (REQ-REC-002/003/004)
    # ------------------------------------------------------------------

    def discover_volumes(
        self, storage_inventory: StorageInventory | None = None
    ) -> list[RecoveryVolume]:
        """
        Return every readable, locally-attached volume on the target
        system.

        Args:
            storage_inventory: An already-collected ``StorageInventory``
                (from ``inspection.report.HardwareInspectionReport
                .storage.data`` -- REQ-REC-001's own dependency on a
                completed Inspection pass makes this available for
                free) used to flag which volumes sit on the disk
                Aquila itself is running from, so the technician can
                see at a glance that recovering "from" that volume
                would just be reading Aquila's own deployment media,
                not the target system's data. Purely informational
                here; ``storage.eligible_for_deployment()`` is what
                actually governs REQ-PREP-012 -- recovery does not
                enforce it, since read-only browsing of the boot
                media is harmless.

        Returns an empty list -- honestly, not a fabricated volume --
        on any non-Windows platform or WMI failure.
        """

        rows = query_wmi_safe(_CIMV2_NAMESPACE, _LOGICAL_DISK_QUERY)

        boot_disk_indexes = self._boot_disk_indexes(storage_inventory)

        volumes: list[RecoveryVolume] = []
        for row in rows:
            drive_type_raw = safe_property_value(row, "DriveType")
            try:
                drive_type = int(drive_type_raw) if drive_type_raw is not None else 0
            except (TypeError, ValueError):
                drive_type = 0

            if drive_type not in _DISCOVERABLE_DRIVE_TYPES:
                continue

            device_id = str(safe_property_value(row, "DeviceID") or "")
            if not device_id:
                continue

            free_space_raw = safe_property_value(row, "FreeSpace")
            size_raw = safe_property_value(row, "Size")

            volumes.append(
                RecoveryVolume(
                    device_id=device_id,
                    root_path=Path(f"{device_id}\\"),
                    volume_name=str(safe_property_value(row, "VolumeName") or ""),
                    file_system=str(safe_property_value(row, "FileSystem") or ""),
                    capacity_bytes=int(size_raw) if size_raw else 0,
                    free_capacity_bytes=(
                        int(free_space_raw) if free_space_raw else 0
                    ),
                    is_removable=drive_type == _DRIVE_TYPE_REMOVABLE,
                    backing_disk_is_boot_media=self._backing_disk_index(device_id)
                    in boot_disk_indexes,
                )
            )

        return volumes

    @staticmethod
    def _boot_disk_indexes(storage_inventory: StorageInventory | None) -> set[int]:
        if storage_inventory is None:
            return set()

        indexes: set[int] = set()
        for device in storage_inventory.devices:
            if not device.is_boot_media:
                continue
            match = _PHYSICAL_DRIVE_INDEX_PATTERN.search(device.device_path)
            if match:
                indexes.add(int(match.group(1)))

        return indexes

    @staticmethod
    def _backing_disk_index(device_id: str) -> int | None:
        """
        Resolve the physical disk index backing a logical volume via
        the same standard WMI association chain
        ``hardware.storage.StorageDetector._detect_boot_disk_index``
        already uses in the opposite direction (system drive -> disk)
        -- confirmed via Microsoft Learn documentation for
        ``Win32_LogicalDiskToPartition``/``Win32_DiskDriveToDiskPartition``.
        Returns ``None`` -- not a guessed index -- on any platform or
        association failure.
        """

        if not is_windows():
            return None

        partition_rows = query_wmi_safe(
            _CIMV2_NAMESPACE,
            "ASSOCIATORS OF {Win32_LogicalDisk.DeviceID='"
            + device_id
            + "'} WHERE AssocClass = Win32_LogicalDiskToPartition "
            "ResultClass = Win32_DiskPartition",
        )
        if not partition_rows:
            return None

        partition_device_id = safe_property_value(partition_rows[0], "DeviceID")
        if not partition_device_id:
            return None

        disk_rows = query_wmi_safe(
            _CIMV2_NAMESPACE,
            "ASSOCIATORS OF {Win32_DiskPartition.DeviceID='"
            + str(partition_device_id)
            + "'} WHERE AssocClass = Win32_DiskDriveToDiskPartition "
            "ResultClass = Win32_DiskDrive",
        )
        if not disk_rows:
            return None

        raw_index = safe_property_value(disk_rows[0], "Index")
        try:
            return int(raw_index) if raw_index is not None else None
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Filesystem browsing (REQ-REC-005)
    # ------------------------------------------------------------------

    def browse(
        self, volume: RecoveryVolume, relative_path: str = ""
    ) -> list[RecoveryEntry]:
        """
        List the immediate contents of ``relative_path`` within
        ``volume`` (non-recursive -- the technician drills down entry
        by entry, matching REQ-REC-005's "browse the contents").

        Raises:
            RecoveryDiscoveryError: If ``relative_path`` attempts to
                escape ``volume``'s root (e.g. via ``..`` segments) or
                the target directory cannot be listed at all (does not
                exist, or is not a directory).

        Individual entries this process lacks permission to ``stat()``
        are still listed -- with ``readable=False`` and
        ``size_bytes``/``modified_at`` left ``None`` -- rather than
        silently omitted or aborting the whole listing, so the
        technician can see that something is there even if its
        details cannot be read yet.
        """

        target_directory = self._resolve_within_volume(volume, relative_path)

        try:
            if not target_directory.is_dir():
                raise RecoveryDiscoveryError(
                    f"{target_directory} is not a directory on volume "
                    f"{volume.device_id}"
                )
            children = list(target_directory.iterdir())
        except OSError as exc:
            raise RecoveryDiscoveryError(
                f"Could not list {target_directory}: {exc}"
            ) from exc

        return [self._entry_from_path(volume, child) for child in children]

    @staticmethod
    def _entry_from_path(volume: RecoveryVolume, path: Path) -> RecoveryEntry:
        try:
            relative_path = str(path.relative_to(volume.root_path))
        except ValueError:
            # Should not happen -- every ``path`` here comes from
            # iterdir() on a directory already confirmed to be under
            # ``volume.root_path`` -- but honestly falls back to the
            # absolute path rather than raising out of a listing that
            # otherwise succeeded.
            relative_path = str(path)

        try:
            stat_result = path.stat()
            is_directory = path.is_dir()
            size_bytes = None if is_directory else int(stat_result.st_size)
            modified_at = datetime.fromtimestamp(stat_result.st_mtime, tz=UTC)
            readable = True
        except OSError as exc:
            logger.debug("Could not stat %s during browsing: %s", path, exc)
            is_directory = False
            size_bytes = None
            modified_at = None
            readable = False

        return RecoveryEntry(
            name=path.name,
            relative_path=relative_path,
            is_directory=is_directory,
            size_bytes=size_bytes,
            modified_at=modified_at,
            readable=readable,
        )

    @staticmethod
    def _resolve_within_volume(volume: RecoveryVolume, relative_path: str) -> Path:
        """
        Join ``relative_path`` onto ``volume.root_path``, safely.

        Built from ``root_path``'s own ``Path`` type via ``joinpath()``
        (never a hardcoded ``PureWindowsPath``, which would silently
        mismatch a POSIX-style root used in tests, breaking the
        ``relative_to()`` safety check below by comparing paths with
        different anchors). The technician-supplied ``relative_path``
        is split on both ``/`` and ``\\`` (Windows accepts either),
        and every ``..`` segment is resolved against the segments
        collected *so far* rather than passed through to ``Path``
        directly -- a ``..`` with nothing left to pop is simply
        dropped, so the constructed path can never structurally
        reference anything above ``root_path``, regardless of how
        many leading ``..`` segments ``relative_path`` contains.
        """

        root = volume.root_path
        raw_segments = [
            segment
            for segment in relative_path.strip().replace("\\", "/").split("/")
            if segment not in ("", ".")
        ]

        segments: list[str] = []
        for segment in raw_segments:
            if segment == "..":
                if segments:
                    segments.pop()
                continue
            segments.append(segment)

        resolved = root.joinpath(*segments) if segments else root

        try:
            resolved.relative_to(root)
        except ValueError as exc:  # pragma: no cover - defense in depth
            raise RecoveryDiscoveryError(
                f"Path '{relative_path}' escapes volume {volume.device_id}"
            ) from exc

        return resolved


__all__ = ["RecoveryEntry", "RecoveryVolume", "VolumeBrowser"]
