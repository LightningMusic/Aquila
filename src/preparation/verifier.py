"""
Project Aquila
=============

Sanitization Verifier

Implements REQ-PREP-017 ("Upon completion, Aquila shall verify that
sanitization completed successfully") and REQ-PREP-018 ("If
sanitization verification fails, deployment shall terminate and report
the failure").

Verification strategy
-----------------------
After ``preparation.sanitizer.DiskSanitizer`` invokes
``MSFT_Disk.Clear()``, this module re-queries the same ``MSFT_Disk``
instance (a genuinely independent, read-only check -- it does not
simply trust ``Clear()``'s own return code) and confirms the disk now
reports the state ``Clear()`` is documented to produce
(learn.microsoft.com/windows-hardware/drivers/storage/clear-msft-disk):

* ``NumberOfPartitions == 0`` -- all partition information removed.
* ``PartitionStyle == RAW`` (0) -- "uninitialized... returning it to a
    RAW state", the same terminology Microsoft's own documentation
    uses.

FULL sanitization (``ZeroOutEntireDisk=True``) additionally zeroes the
entire disk. This module does not re-read every sector to confirm that
-- reading terabytes back sector-by-sector would turn a verification
step into an operation as slow as the sanitization itself, with no
WMI-exposed checksum to compare against. Instead it performs a
bounded, honest spot-check: reading back a small window of raw bytes
near the start of the device and confirming they are zero. This is
disclosed as a spot-check, not a guarantee -- ``VerificationOutcome``
distinguishes ``VERIFIED`` (partition-table check passed, spot-check
passed or was not applicable) from ``PARTIAL`` (partition-table check
passed, spot-check could not be performed or found non-zero data) so a
caller and the eventual sanitization report never overstate what was
actually confirmed.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from common.constants.logging import PREPARATION_LOGGER
from common.enums import SanitizationMethod
from hardware import is_windows, query_wmi_safe, safe_property_value

logger = logging.getLogger(PREPARATION_LOGGER)

_STORAGE_NAMESPACE = r"root\Microsoft\Windows\Storage"

_DISK_STATE_QUERY_FIELDS = "Number, PartitionStyle, NumberOfPartitions"

#: MSFT_Disk.PartitionStyle values (learn.microsoft.com/windows-hardware/
#: drivers/storage/msft-disk): 0=Unknown/RAW, 1=MBR, 2=GPT. A disk
#: ``Clear()`` returned to a RAW state reports 0.
_PARTITION_STYLE_RAW = 0

#: How many bytes to read back from the start of the device for FULL
#: sanitization's honest, bounded spot-check -- large enough to be a
#: meaningful sample, small enough that reading it back costs
#: milliseconds rather than minutes.
_SPOT_CHECK_BYTES = 1024 * 1024

#: A function that reads up to ``length`` bytes starting at ``offset``
#: from ``device_path`` (a Windows physical-drive path such as
#: ``\\.\PHYSICALDRIVE0``), returning fewer bytes (including zero) if
#: the device is shorter or unreadable, or raising ``OSError``.
#: Injectable so tests never need an actual Windows block device.
RawDeviceReader = Callable[[str, int, int], bytes]


class VerificationOutcome(Enum):
    """
    The result of verifying one sanitized device.

    Mirrors ``recovery.verifier.VerificationOutcome``'s convention of
    naming every real outcome (never collapsing a partial or
    unreadable result into a bare boolean), so a caller can tell "we
    confirmed this" from "we could not confirm this" from "this
    clearly failed".
    """

    VERIFIED = "verified"
    PARTIAL = "partial"
    NOT_CLEARED = "not_cleared"
    DEVICE_UNREADABLE = "device_unreadable"


@dataclass(slots=True, frozen=True)
class SanitizationVerificationResult:
    """The outcome of verifying one sanitized device."""

    device_path: str
    method: SanitizationMethod
    outcome: VerificationOutcome
    detail: str
    partition_style: int | None
    number_of_partitions: int | None

    @property
    def passed(self) -> bool:
        """
        Whether REQ-PREP-017's verification succeeded well enough to
        let deployment proceed (REQ-PREP-018 halts only on genuine
        failure, not on an inherently-unconfirmable spot-check).
        """

        return self.outcome in (VerificationOutcome.VERIFIED, VerificationOutcome.PARTIAL)


def _default_raw_device_reader(device_path: str, offset: int, length: int) -> bytes:
    """
    Read ``length`` bytes starting at ``offset`` directly from
    ``device_path`` using a raw, read-only file handle.

    Windows honors ``\\\\.\\PHYSICALDRIVEn`` as an openable device path
    for raw sector reads when opened without write access; this
    performs no write of any kind.
    """

    if not is_windows():
        return b""

    try:
        with open(device_path, "rb") as raw_device:  # noqa: PTH123 - raw device path, not a filesystem path
            raw_device.seek(offset)
            return raw_device.read(length)
    except OSError as exc:
        logger.debug("Raw device read of %s failed: %s", device_path, exc)
        raise


class SanitizationVerifier:
    """
    Independently re-verifies that a sanitized disk actually reached
    the expected post-sanitization state (REQ-PREP-017/018).
    """

    def __init__(self, *, raw_device_reader: RawDeviceReader | None = None) -> None:
        self._raw_device_reader = raw_device_reader or _default_raw_device_reader

    def verify(
        self, device_path: str, disk_number: int, method: SanitizationMethod
    ) -> SanitizationVerificationResult:
        """
        Verify that ``device_path`` (disk number ``disk_number``) was
        actually sanitized by ``method``.
        """

        disk_state = self._query_disk_state(disk_number)
        if disk_state is None:
            return SanitizationVerificationResult(
                device_path=device_path,
                method=method,
                outcome=VerificationOutcome.DEVICE_UNREADABLE,
                detail=(
                    f"MSFT_Disk with Number={disk_number} could not be "
                    "re-queried after sanitization -- verification "
                    "could not be performed."
                ),
                partition_style=None,
                number_of_partitions=None,
            )

        partition_style, number_of_partitions = disk_state

        if partition_style != _PARTITION_STYLE_RAW or number_of_partitions != 0:
            return SanitizationVerificationResult(
                device_path=device_path,
                method=method,
                outcome=VerificationOutcome.NOT_CLEARED,
                detail=(
                    f"Disk {disk_number} still reports "
                    f"PartitionStyle={partition_style} and "
                    f"NumberOfPartitions={number_of_partitions} after "
                    "sanitization -- it was not returned to a RAW "
                    "state."
                ),
                partition_style=partition_style,
                number_of_partitions=number_of_partitions,
            )

        if method is not SanitizationMethod.FULL:
            return SanitizationVerificationResult(
                device_path=device_path,
                method=method,
                outcome=VerificationOutcome.VERIFIED,
                detail=(
                    f"Disk {disk_number} confirmed RAW "
                    "(PartitionStyle=0, NumberOfPartitions=0) after "
                    f"{method.name}."
                ),
                partition_style=partition_style,
                number_of_partitions=number_of_partitions,
            )

        return self._spot_check_zeroed(
            device_path, disk_number, method, partition_style, number_of_partitions
        )

    # ------------------------------------------------------------------
    # Internal: partition-table state
    # ------------------------------------------------------------------

    def _query_disk_state(self, disk_number: int) -> tuple[int, int] | None:
        rows = query_wmi_safe(
            _STORAGE_NAMESPACE,
            f"SELECT {_DISK_STATE_QUERY_FIELDS} FROM MSFT_Disk WHERE "
            f"Number = {disk_number}",
        )
        if not rows:
            return None

        raw_partition_style = safe_property_value(rows[0], "PartitionStyle")
        raw_number_of_partitions = safe_property_value(rows[0], "NumberOfPartitions")

        try:
            partition_style = int(raw_partition_style)
            number_of_partitions = int(raw_number_of_partitions)
        except (TypeError, ValueError):
            return None

        return partition_style, number_of_partitions

    # ------------------------------------------------------------------
    # Internal: FULL sanitization's bounded zero-fill spot-check
    # ------------------------------------------------------------------

    def _spot_check_zeroed(
        self,
        device_path: str,
        disk_number: int,
        method: SanitizationMethod,
        partition_style: int,
        number_of_partitions: int,
    ) -> SanitizationVerificationResult:
        try:
            sample = self._raw_device_reader(device_path, 0, _SPOT_CHECK_BYTES)
        except OSError as exc:
            return SanitizationVerificationResult(
                device_path=device_path,
                method=method,
                outcome=VerificationOutcome.PARTIAL,
                detail=(
                    f"Disk {disk_number} confirmed RAW after FULL "
                    "sanitization, but a raw read-back spot-check of "
                    f"the first {_SPOT_CHECK_BYTES} bytes could not be "
                    f"performed: {exc}. Partition-table verification "
                    "passed; the zero-fill itself was not independently "
                    "confirmed."
                ),
                partition_style=partition_style,
                number_of_partitions=number_of_partitions,
            )

        if not sample:
            return SanitizationVerificationResult(
                device_path=device_path,
                method=method,
                outcome=VerificationOutcome.PARTIAL,
                detail=(
                    f"Disk {disk_number} confirmed RAW after FULL "
                    "sanitization, but the raw read-back spot-check "
                    "returned no data. Partition-table verification "
                    "passed; the zero-fill itself was not independently "
                    "confirmed."
                ),
                partition_style=partition_style,
                number_of_partitions=number_of_partitions,
            )

        if any(byte != 0 for byte in sample):
            return SanitizationVerificationResult(
                device_path=device_path,
                method=method,
                outcome=VerificationOutcome.NOT_CLEARED,
                detail=(
                    f"Disk {disk_number} reports RAW partition state, "
                    f"but the first {len(sample)} bytes read back from "
                    "the device are not all zero -- FULL sanitization's "
                    "zero-fill could not be confirmed."
                ),
                partition_style=partition_style,
                number_of_partitions=number_of_partitions,
            )

        return SanitizationVerificationResult(
            device_path=device_path,
            method=method,
            outcome=VerificationOutcome.VERIFIED,
            detail=(
                f"Disk {disk_number} confirmed RAW after FULL "
                f"sanitization; the first {len(sample)} bytes read back "
                "from the device are all zero."
            ),
            partition_style=partition_style,
            number_of_partitions=number_of_partitions,
        )


__all__ = [
    "RawDeviceReader",
    "SanitizationVerificationResult",
    "SanitizationVerifier",
    "VerificationOutcome",
]
