"""
Project Aquila
=============

Storage Detection

Implements REQ-INS-005 (enumerate all storage devices), REQ-INS-006
(identify storage device type: SATA HDD, SATA SSD, NVMe SSD, USB
Storage), and REQ-INS-008 (report storage capacity and available free
space).

Also implements the storage-side half of REQ-PREP-012 ("the deployment
USB shall never be eligible for sanitization") by identifying, on a
best-effort basis, which physical disk backs the drive Aquila itself
is currently running from.

WMI sources
-----------
``MSFT_PhysicalDisk`` (``root\\Microsoft\\Windows\\Storage``, the
Windows Storage Management API -- Windows 8 / Server 2012 and newer)
is the primary source: its ``BusType`` (SATA=11, USB=7, NVMe=17,
SD=12, MMC=13, ...) and ``MediaType`` (HDD=3, SSD=4) properties give a
confirmed, precise device-type classification. ``Win32_DiskDrive``
(``root\\cimv2``, universally available) supplies device identity
(model, manufacturer, serial number, firmware revision) and is the
sole classification source on older systems where the Storage
Management API namespace is unavailable.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import os
from typing import Any, Dict

from models.hardware import StorageDevice, StorageDeviceType, StorageInventory

from . import query_wmi_safe, safe_property_value

_CIMV2_NAMESPACE = r"root\cimv2"
_STORAGE_NAMESPACE = r"root\Microsoft\Windows\Storage"

_DISK_DRIVE_QUERY = (
    "SELECT DeviceID, Model, Manufacturer, SerialNumber, InterfaceType, "
    "MediaType, Size, FirmwareRevision, Index FROM Win32_DiskDrive"
)

_PHYSICAL_DISK_QUERY = (
    "SELECT DeviceId, FriendlyName, SerialNumber, BusType, MediaType, "
    "Size FROM MSFT_PhysicalDisk"
)

# MSFT_PhysicalDisk.BusType (Storage Management API) -- confirmed
# against Microsoft Learn documentation for the MSFT_PhysicalDisk/
# MSFT_Disk classes.
_BUS_TYPE_USB = 7
_BUS_TYPE_SATA = 11
_BUS_TYPE_SD = 12
_BUS_TYPE_MMC = 13
_BUS_TYPE_NVME = 17

# MSFT_PhysicalDisk.MediaType.
_MEDIA_TYPE_HDD = 3
_MEDIA_TYPE_SSD = 4

_REMOVABLE_BUS_TYPES = {_BUS_TYPE_USB, _BUS_TYPE_SD, _BUS_TYPE_MMC}


class StorageDetector:
    """Detects installed storage devices without modifying system state."""

    def detect(self) -> StorageInventory:
        """
        Return a ``StorageInventory`` record for every storage device
        enumerated on the target system.

        Returns an honestly-empty ``StorageInventory`` on any
        non-Windows platform or WMI failure, rather than raising --
        REQ-INS-025 requires an inspection report to always be
        produced.
        """

        disk_drive_rows = query_wmi_safe(_CIMV2_NAMESPACE, _DISK_DRIVE_QUERY)
        physical_disk_rows = query_wmi_safe(_STORAGE_NAMESPACE, _PHYSICAL_DISK_QUERY)

        physical_disks_by_index = self._index_physical_disks(physical_disk_rows)
        boot_disk_index = self._detect_boot_disk_index()

        def _matching_physical_disk(row: object) -> object | None:
            index = self._disk_index(row)
            return physical_disks_by_index.get(index) if index is not None else None

        devices = [
            self._device_from_row(
                row,
                _matching_physical_disk(row),
                boot_disk_index,
            )
            for row in disk_drive_rows
        ]

        return StorageInventory(devices=devices)

    # -----------------------------------------------------------------
    # Win32_DiskDrive + MSFT_PhysicalDisk merge
    # -----------------------------------------------------------------

    @staticmethod
    def _disk_index(row: object) -> int | None:
        raw_index = safe_property_value(row, "Index")
        try:
            return int(raw_index) if raw_index is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _index_physical_disks(rows: list[Any]) -> Dict[int, Any]:
        """
        Map each ``MSFT_PhysicalDisk`` row to the disk index
        ``Win32_DiskDrive`` uses, so the two WMI sources can be merged
        into one record per physical device.

        ``MSFT_PhysicalDisk.DeviceId`` is the disk number as a string
        (``"0"``, ``"1"``, ...), the same numbering
        ``Win32_DiskDrive.Index`` uses.
        """

        indexed: Dict[int, Any] = {}
        for row in rows:
            raw_device_id = safe_property_value(row, "DeviceId")
            try:
                index = int(str(raw_device_id).strip())
            except (TypeError, ValueError):
                continue
            indexed[index] = row

        return indexed

    def _device_from_row(
        self,
        disk_drive_row: object,
        physical_disk_row: object | None,
        boot_disk_index: int | None,
    ) -> StorageDevice:
        device_path = str(safe_property_value(disk_drive_row, "DeviceID") or "")
        size_raw = safe_property_value(disk_drive_row, "Size")
        interface_type = str(
            safe_property_value(disk_drive_row, "InterfaceType") or ""
        )
        media_type_string = str(
            safe_property_value(disk_drive_row, "MediaType") or ""
        )

        device_type = self._classify(
            physical_disk_row=physical_disk_row,
            interface_type=interface_type,
            media_type_string=media_type_string,
        )

        is_removable = self._is_removable(
            physical_disk_row=physical_disk_row,
            interface_type=interface_type,
            media_type_string=media_type_string,
        )

        index = self._disk_index(disk_drive_row)
        is_boot_media = boot_disk_index is not None and index == boot_disk_index

        return StorageDevice(
            device_path=device_path,
            model=str(safe_property_value(disk_drive_row, "Model") or ""),
            manufacturer=str(
                safe_property_value(disk_drive_row, "Manufacturer") or ""
            ),
            serial_number=str(
                safe_property_value(disk_drive_row, "SerialNumber")
                or (
                    safe_property_value(physical_disk_row, "SerialNumber")
                    if physical_disk_row is not None
                    else ""
                )
                or ""
            ),
            device_type=device_type,
            interface=self._interface_name(physical_disk_row, interface_type),
            capacity_bytes=int(size_raw) if size_raw else 0,
            free_capacity_bytes=None,  # No free space at the raw-device level; only partitioned volumes report free space.
            firmware_version=str(
                safe_property_value(disk_drive_row, "FirmwareRevision") or ""
            ),
            is_removable=is_removable,
            is_system_disk=is_boot_media,
            is_boot_media=is_boot_media,
        )

    @staticmethod
    def _classify(
        *,
        physical_disk_row: object | None,
        interface_type: str,
        media_type_string: str,
    ) -> StorageDeviceType:
        if physical_disk_row is not None:
            bus_type_raw = safe_property_value(physical_disk_row, "BusType")
            media_type_raw = safe_property_value(physical_disk_row, "MediaType")

            try:
                bus_type = int(bus_type_raw) if bus_type_raw is not None else None
            except (TypeError, ValueError):
                bus_type = None

            try:
                media_type = (
                    int(media_type_raw) if media_type_raw is not None else None
                )
            except (TypeError, ValueError):
                media_type = None

            if bus_type == _BUS_TYPE_NVME:
                return StorageDeviceType.NVME_SSD

            if bus_type == _BUS_TYPE_USB:
                return StorageDeviceType.USB_STORAGE

            if bus_type == _BUS_TYPE_SATA:
                if media_type == _MEDIA_TYPE_SSD:
                    return StorageDeviceType.SATA_SSD
                if media_type == _MEDIA_TYPE_HDD:
                    return StorageDeviceType.SATA_HDD
                # SATA bus confirmed but rotational/solid-state media
                # unreported -- honestly OTHER rather than guessing.
                return StorageDeviceType.OTHER

            if bus_type is not None:
                return StorageDeviceType.OTHER

        # Fallback for systems without the Storage Management API
        # namespace: classify from Win32_DiskDrive's InterfaceType and
        # free-text MediaType/Model strings.
        interface_upper = interface_type.strip().upper()
        media_lower = media_type_string.lower()

        if interface_upper == "USB":
            return StorageDeviceType.USB_STORAGE

        if "nvme" in media_lower:
            return StorageDeviceType.NVME_SSD

        if interface_upper in ("IDE", "SCSI"):
            if "ssd" in media_lower or "solid state" in media_lower:
                return StorageDeviceType.SATA_SSD
            if "fixed" in media_lower or "hard disk" in media_lower:
                return StorageDeviceType.SATA_HDD

        return StorageDeviceType.UNKNOWN

    @staticmethod
    def _is_removable(
        *,
        physical_disk_row: object | None,
        interface_type: str,
        media_type_string: str,
    ) -> bool:
        if physical_disk_row is not None:
            bus_type_raw = safe_property_value(physical_disk_row, "BusType")
            try:
                bus_type = int(bus_type_raw) if bus_type_raw is not None else None
            except (TypeError, ValueError):
                bus_type = None

            if bus_type in _REMOVABLE_BUS_TYPES:
                return True

        return (
            interface_type.strip().upper() == "USB"
            or "removable" in media_type_string.lower()
        )

    @staticmethod
    def _interface_name(physical_disk_row: object | None, interface_type: str) -> str:
        if physical_disk_row is not None:
            bus_type_raw = safe_property_value(physical_disk_row, "BusType")
            try:
                bus_type = int(bus_type_raw) if bus_type_raw is not None else None
            except (TypeError, ValueError):
                bus_type = None

            bus_type_names = {
                1: "SCSI",
                2: "ATAPI",
                3: "ATA",
                4: "1394",
                5: "SSA",
                6: "Fibre Channel",
                7: "USB",
                8: "RAID",
                9: "iSCSI",
                10: "SAS",
                11: "SATA",
                12: "SD",
                13: "MMC",
                14: "Max",
                15: "File Backed Virtual",
                16: "Storage Spaces",
                17: "NVMe",
            }
            if bus_type in bus_type_names:
                return bus_type_names[bus_type]

        return interface_type

    # -----------------------------------------------------------------
    # Boot/deployment-media detection (REQ-PREP-012 support)
    # -----------------------------------------------------------------

    def _detect_boot_disk_index(self) -> int | None:
        """
        Best-effort detection of the physical disk index backing the
        drive Aquila itself is currently running from.

        Walks the standard WMI partition/logical-disk association
        chain (``Win32_LogicalDiskToPartition`` /
        ``Win32_DiskDriveToDiskPartition``) from the ``SystemDrive``
        environment variable back to a physical ``Win32_DiskDrive``
        index. Returns ``None`` -- rather than a guessed value -- when
        the associations can't be resolved (for example, on a
        non-Windows platform, or when the environment variable is
        unavailable), matching this package's honesty-over-fabrication
        convention: REQ-PREP-012's actual enforcement belongs to the
        Preparation Engine, which can also cross-check ``is_removable``;
        this is a best-effort supporting signal, not the sole
        safeguard.
        """

        system_drive = os.environ.get("SystemDrive", "").strip()
        if not system_drive:
            return None

        if not system_drive.endswith(":"):
            system_drive = f"{system_drive}:"

        partition_rows = query_wmi_safe(
            _CIMV2_NAMESPACE,
            "ASSOCIATORS OF {Win32_LogicalDisk.DeviceID='"
            + system_drive
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

        return self._disk_index(disk_rows[0])


__all__ = ["StorageDetector"]
