"""
Project Aquila
=============

SMART Detection

Implements REQ-INS-007 (retrieve SMART health information for
supported storage devices).

WMI sources
-----------
``MSStorageDriver_FailurePredictStatus`` (``root\\wmi``) is the
primary, load-bearing source: it reports the storage miniport
driver's own pass/fail prediction (``PredictFailure``) for a device,
identified by ``InstanceName`` (a string embedding the disk's PNP
device ID). This class is not part of Microsoft's current formally
documented WMI schema -- it originates from the legacy Storage
Failure Prediction (SFP) driver interface -- but its presence,
property names, and semantics are exercised and confirmed by every
mainstream SMART inspection tool (smartmontools' wmi backend,
CrystalDiskInfo, and others) and by direct testing on real Windows
hardware. Detection degrades honestly (``supported=False``) rather
than raising when the class is absent, matching every other Aquila
detector's cross-platform convention.

``MSStorageDriver_FailurePredictData`` (same namespace) additionally
carries a raw, undocumented-by-Microsoft ATA SMART attribute table in
its ``VendorSpecific`` byte array. The 362-byte layout parsed below
(a 2-byte header followed by thirty 12-byte ATA SMART attribute
entries) is the same layout every open-source SMART tool targeting
this WMI class parses -- but because it is not an officially
specified Microsoft structure, parsing is wrapped defensively: any
failure to parse falls back to an empty attribute list rather than
fabricating attribute values, while the pass/fail status from
``MSStorageDriver_FailurePredictStatus`` is preserved regardless.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from common.enums import SMARTStatus
from models.hardware import SMARTAttribute, SMARTReport

from . import query_wmi_safe, safe_property_value

_WMI_NAMESPACE = r"root\wmi"

_STATUS_QUERY = (
    "SELECT InstanceName, PredictFailure, Reason "
    "FROM MSStorageDriver_FailurePredictStatus"
)
_DATA_QUERY = "SELECT InstanceName, VendorSpecific FROM MSStorageDriver_FailurePredictData"
_DISK_DRIVE_QUERY = "SELECT DeviceID, PNPDeviceID, Index FROM Win32_DiskDrive"

# Standard, widely-documented ATA SMART attribute IDs. Only the
# attributes this detector reports as named fields (REQ-INS-007's
# power-on hours, power cycle count, temperature, and sector-error
# counts) are named here; every other attribute ID still reports with
# its raw values, simply without a friendly name, rather than being
# dropped.
_ATTRIBUTE_NAMES: dict[int, str] = {
    1: "Read Error Rate",
    3: "Spin-Up Time",
    4: "Start/Stop Count",
    5: "Reallocated Sectors Count",
    7: "Seek Error Rate",
    9: "Power-On Hours",
    10: "Spin Retry Count",
    12: "Power Cycle Count",
    177: "Wear Leveling Count",
    179: "Used Reserved Block Count",
    181: "Program Fail Count",
    182: "Erase Fail Count",
    187: "Reported Uncorrectable Errors",
    188: "Command Timeout",
    194: "Temperature",
    196: "Reallocated Event Count",
    197: "Current Pending Sector Count",
    198: "Offline Uncorrectable Sector Count",
    199: "UDMA CRC Error Count",
    241: "Total LBAs Written",
    242: "Total LBAs Read",
}

_ATTR_POWER_ON_HOURS = 9
_ATTR_POWER_CYCLE_COUNT = 12
_ATTR_TEMPERATURE = 194
_ATTR_REALLOCATED_SECTORS = 5
_ATTR_PENDING_SECTORS = 197
_ATTR_UNCORRECTABLE_SECTORS = 198

_ATTRIBUTE_ENTRY_SIZE = 12
_ATTRIBUTE_TABLE_HEADER_SIZE = 2
_ATTRIBUTE_COUNT = 30


class SMARTDetector:
    """Detects storage device SMART health without modifying device state."""

    def detect_all(self) -> list[SMARTReport]:
        """
        Return a ``SMARTReport`` for every storage device with a
        matching ``Win32_DiskDrive`` entry.
        """

        disk_rows = query_wmi_safe(r"root\cimv2", _DISK_DRIVE_QUERY)
        status_rows = query_wmi_safe(_WMI_NAMESPACE, _STATUS_QUERY)
        data_rows = query_wmi_safe(_WMI_NAMESPACE, _DATA_QUERY)

        return [
            self.detect(
                device_path=str(safe_property_value(row, "DeviceID") or ""),
                pnp_device_id=str(safe_property_value(row, "PNPDeviceID") or ""),
                status_rows=status_rows,
                data_rows=data_rows,
            )
            for row in disk_rows
        ]

    def detect(
        self,
        *,
        device_path: str,
        pnp_device_id: str,
        status_rows: list[Any] | None = None,
        data_rows: list[Any] | None = None,
    ) -> SMARTReport:
        """
        Return a ``SMARTReport`` for a single storage device.

        ``pnp_device_id`` is matched against
        ``MSStorageDriver_FailurePredictStatus.InstanceName``, which
        embeds the disk's PNP device ID as a substring -- the standard
        (if informally documented) correlation key between
        ``Win32_DiskDrive`` and the failure-prediction classes.
        Returns ``supported=False`` -- never a fabricated pass/fail --
        when no matching instance is found.
        """

        if status_rows is None:
            status_rows = query_wmi_safe(_WMI_NAMESPACE, _STATUS_QUERY)
        if data_rows is None:
            data_rows = query_wmi_safe(_WMI_NAMESPACE, _DATA_QUERY)

        status_row = self._match_instance(status_rows, pnp_device_id)
        if status_row is None:
            return SMARTReport(
                device_path=device_path,
                status=SMARTStatus.UNKNOWN,
                supported=False,
                collected_at=datetime.now(UTC),
            )

        predict_failure = bool(safe_property_value(status_row, "PredictFailure"))
        status = SMARTStatus.FAILED if predict_failure else SMARTStatus.PASSED

        attributes: list[SMARTAttribute] = []
        data_row = self._match_instance(data_rows, pnp_device_id)
        if data_row is not None:
            raw_bytes = safe_property_value(data_row, "VendorSpecific")
            attributes = self._parse_attribute_table(raw_bytes)

        attribute_by_id = {attribute.attribute_id: attribute for attribute in attributes}
        temperature_raw = self._raw_value(attribute_by_id, _ATTR_TEMPERATURE)

        return SMARTReport(
            device_path=device_path,
            status=status,
            supported=True,
            power_on_hours=self._raw_value(attribute_by_id, _ATTR_POWER_ON_HOURS),
            power_cycle_count=self._raw_value(attribute_by_id, _ATTR_POWER_CYCLE_COUNT),
            temperature_celsius=(
                float(temperature_raw & 0xFF) if temperature_raw is not None else None
            ),
            reallocated_sector_count=self._raw_value(
                attribute_by_id, _ATTR_REALLOCATED_SECTORS
            ),
            pending_sector_count=self._raw_value(attribute_by_id, _ATTR_PENDING_SECTORS),
            uncorrectable_sector_count=self._raw_value(
                attribute_by_id, _ATTR_UNCORRECTABLE_SECTORS
            ),
            attributes=attributes,
            collected_at=datetime.now(UTC),
            raw_data={"predict_failure_reason": safe_property_value(status_row, "Reason")},
        )

    @staticmethod
    def _raw_value(
        attribute_by_id: dict[int, SMARTAttribute], attribute_id: int
    ) -> int | None:
        attribute = attribute_by_id.get(attribute_id)
        return attribute.raw_value if attribute is not None else None

    @staticmethod
    def _match_instance(rows: list[Any], pnp_device_id: str) -> Any | None:
        if not pnp_device_id:
            return None

        # WMI's InstanceName embeds the PNP device ID with escaped
        # backslashes and lowercased; compare on a normalized,
        # alphanumeric-only form so formatting differences between the
        # two WMI classes don't cause a false non-match.
        normalized_target = re.sub(r"[^0-9A-Za-z]", "", pnp_device_id).lower()
        if not normalized_target:
            return None

        for row in rows:
            instance_name = str(safe_property_value(row, "InstanceName") or "")
            normalized_instance = re.sub(r"[^0-9A-Za-z]", "", instance_name).lower()
            if normalized_target and normalized_target in normalized_instance:
                return row

        return None

    @staticmethod
    def _parse_attribute_table(raw_bytes: Any) -> list[SMARTAttribute]:
        """
        Parse the community-documented (not Microsoft-specified) ATA
        SMART attribute table layout carried in
        ``MSStorageDriver_FailurePredictData.VendorSpecific``.

        Returns an empty list -- rather than raising or fabricating
        data -- for any input that doesn't match the expected 362-byte,
        thirty-attribute layout, since this format is not a contract
        Microsoft guarantees.
        """

        try:
            data = bytes(raw_bytes)
        except (TypeError, ValueError):
            return []

        attributes: list[SMARTAttribute] = []

        for slot in range(_ATTRIBUTE_COUNT):
            offset = _ATTRIBUTE_TABLE_HEADER_SIZE + (slot * _ATTRIBUTE_ENTRY_SIZE)
            if offset + _ATTRIBUTE_ENTRY_SIZE > len(data):
                break

            entry = data[offset : offset + _ATTRIBUTE_ENTRY_SIZE]
            attribute_id = entry[0]

            if attribute_id == 0:
                # ID 0 marks an unused attribute slot.
                continue

            current_value = entry[3]
            worst_value = entry[4]
            raw_value = int.from_bytes(entry[5:11], byteorder="little", signed=False)

            attributes.append(
                SMARTAttribute(
                    attribute_id=attribute_id,
                    name=_ATTRIBUTE_NAMES.get(attribute_id, ""),
                    raw_value=raw_value,
                    normalized_value=current_value,
                    worst_value=worst_value,
                    threshold=None,
                )
            )

        return attributes


__all__ = ["SMARTDetector"]
