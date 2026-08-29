"""
Project Aquila
=============

Recovery Summary

Implements REQ-REC-014 ("The Recovery Engine shall generate a recovery
summary upon completion") and REQ-REC-015 ("The Recovery Engine shall
clearly indicate when no recovery has been performed").

``RecoverySummary`` is assembled by ``recovery.recovery_manager
.RecoveryManager`` from the results ``recovery.copier.RecoveryCopier``
and ``recovery.verifier.RecoveryVerifier`` produce, and is what
``recovery_manager`` returns from ``run()``. It follows the same
``SCHEMA_VERSION``/``to_dict()``/``to_json()``/``from_dict()``
round-tripping convention already established by ``bios.models`` and
``models.hardware`` -- but, unlike ``inspection.report
.HardwareInspectionReport``, this module defines its own small,
self-contained JSON helpers rather than importing ``models.hardware``'s:
a recovery summary has nothing to do with the hardware-inventory domain
those helpers were written for, and ``bios.models`` already established
that a package with its own narrow serialization needs defines its own
helpers rather than reaching into an unrelated package for them.

REQ-REC-026 ("The technician shall be informed of any incomplete
recovery before destructive operations may begin") is implemented here
as the :attr:`RecoverySummary.is_complete` property -- the signal the
(not yet built) Preparation Engine must check before REQ-PREP-001/
REQ-REC-017 allow it to proceed.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from json import dumps
from typing import Any, ClassVar, Mapping, TypeAlias, cast

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


def _parse_datetime(value: Any, *, default: datetime) -> datetime:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return default
    return default


@dataclass(slots=True)
class RecoverySummary:
    """
    The complete outcome of one Recovery Engine run (REQ-REC-014).

    ``recovery_performed`` / ``skipped`` are mutually exclusive and
    together cover every path REQ-REC-015/016/017 describe: recovery
    actually ran (``recovery_performed=True``), the technician
    explicitly and acknowledgedly skipped it (``skipped=True``,
    ``skip_acknowledgement`` set -- REQ-REC-016), or recovery was
    aborted partway through (``recovery_performed=True`` but
    ``aborted=True``, e.g. REQ-REC-025's "destination became
    unavailable" case).
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    started_at: datetime
    completed_at: datetime

    recovery_performed: bool
    skipped: bool
    aborted: bool = False
    skip_acknowledgement: str | None = None
    abort_reason: str | None = None

    files_recovered: int = 0
    directories_recovered: int = 0
    total_bytes_copied: int = 0
    files_skipped: int = 0
    files_failed_verification: int = 0

    failure_messages: list[str] = field(default_factory=lambda: [])

    def __post_init__(self) -> None:
        self.failure_messages = list(self.failure_messages)

    # ------------------------------------------------------------------
    # Derived facts
    # ------------------------------------------------------------------

    @property
    def duration(self) -> timedelta:
        return self.completed_at - self.started_at

    @property
    def is_complete(self) -> bool:
        """
        Whether this recovery reached a fully resolved state -- the
        condition REQ-REC-017 requires before Preparation may begin,
        and REQ-REC-026 requires the technician be warned about when
        it does *not* hold.

        An intentionally, acknowledgedly skipped recovery
        (REQ-REC-016) counts as complete: nothing was left half done.
        An aborted recovery (REQ-REC-025) never does, regardless of
        how many files it managed to copy before the destination
        disappeared. A recovery that ran to its natural end is
        complete only if every selected file both copied and
        verified successfully.
        """

        if self.aborted:
            return False

        if self.skipped:
            return True

        return (
            self.recovery_performed
            and self.files_skipped == 0
            and self.files_failed_verification == 0
        )

    @property
    def status_message(self) -> str:
        """
        A short, technician-facing summary (REQ-REC-015: "clearly
        indicate when no recovery has been performed").
        """

        if self.skipped:
            reason = self.skip_acknowledgement or "no reason recorded"
            return f"Recovery was skipped by technician acknowledgement: {reason}"

        if not self.recovery_performed:
            return "No recovery was performed."

        if self.aborted:
            reason = self.abort_reason or "unknown reason"
            return f"Recovery was aborted before completion: {reason}"

        if self.is_complete:
            return (
                f"Recovery completed: {self.files_recovered} file(s), "
                f"{self.directories_recovered} directory(ies), "
                f"{self.total_bytes_copied} byte(s) copied and verified."
            )

        return (
            f"Recovery completed with issues: {self.files_skipped} file(s) "
            f"skipped, {self.files_failed_verification} file(s) failed "
            f"verification. See failure_messages for details."
        )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_seconds": self.duration.total_seconds(),
            "recovery_performed": self.recovery_performed,
            "skipped": self.skipped,
            "aborted": self.aborted,
            "skip_acknowledgement": self.skip_acknowledgement,
            "abort_reason": self.abort_reason,
            "files_recovered": self.files_recovered,
            "directories_recovered": self.directories_recovered,
            "total_bytes_copied": self.total_bytes_copied,
            "files_skipped": self.files_skipped,
            "files_failed_verification": self.files_failed_verification,
            "failure_messages": list(self.failure_messages),
            "is_complete": self.is_complete,
            "status_message": self.status_message,
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return dumps(self.to_dict(), indent=indent, sort_keys=True, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RecoverySummary":
        now = datetime.now(UTC)
        started_at = _parse_datetime(data.get("started_at"), default=now)
        completed_at = _parse_datetime(data.get("completed_at"), default=started_at)

        failure_messages_raw = data.get("failure_messages", [])
        failure_messages = (
            [str(message) for message in cast("list[Any]", failure_messages_raw)]
            if isinstance(failure_messages_raw, list)
            else []
        )

        def _int(key: str) -> int:
            try:
                return int(data.get(key, 0) or 0)
            except (TypeError, ValueError):
                return 0

        def _optional_str(key: str) -> str | None:
            value = data.get(key)
            return str(value) if value is not None else None

        return cls(
            started_at=started_at,
            completed_at=completed_at,
            recovery_performed=bool(data.get("recovery_performed", False)),
            skipped=bool(data.get("skipped", False)),
            aborted=bool(data.get("aborted", False)),
            skip_acknowledgement=_optional_str("skip_acknowledgement"),
            abort_reason=_optional_str("abort_reason"),
            files_recovered=_int("files_recovered"),
            directories_recovered=_int("directories_recovered"),
            total_bytes_copied=_int("total_bytes_copied"),
            files_skipped=_int("files_skipped"),
            files_failed_verification=_int("files_failed_verification"),
            failure_messages=failure_messages,
        )


__all__ = ["RecoverySummary"]
