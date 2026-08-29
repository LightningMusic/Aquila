"""
Project Aquila
=============

Preparation Reports

Implements REQ-PREP-002 ("The Preparation Engine shall display a
summary of the deployment session before any destructive operation
begins") and REQ-PREP-019 ("The Preparation Engine shall generate a
sanitization report").

``SanitizationRecord`` is the per-device REQ-PREP-019 record (storage
device sanitized, sanitization method, start/end time, verification
status). ``PreparationSummary`` is the whole-session report
``preparation.preparation_manager.PreparationManager`` assembles and
returns from ``run()`` -- it carries REQ-PREP-002's pre-flight facts
(system identity, target storage, recovery status, deployment
workflow) alongside the REQ-PREP-019 sanitization records for every
device Preparation touched.

Follows the exact ``SCHEMA_VERSION``/``to_dict()``/``to_json()``/
``from_dict()`` convention ``recovery.report.RecoverySummary``
established, including its own small, self-contained JSON helpers --
a preparation report has nothing to do with the hardware-inventory
domain ``models.hardware``'s helpers were written for.

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

from common.enums import SanitizationMethod

from .verifier import VerificationOutcome

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


def _parse_datetime(value: Any, *, default: datetime) -> datetime:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return default
    return default


def _parse_method(value: Any, *, default: SanitizationMethod) -> SanitizationMethod:
    if isinstance(value, str) and value:
        try:
            return SanitizationMethod[value]
        except KeyError:
            return default
    return default


def _parse_verification_outcome(value: Any) -> VerificationOutcome:
    if isinstance(value, str) and value:
        try:
            return VerificationOutcome(value)
        except ValueError:
            return VerificationOutcome.DEVICE_UNREADABLE
    return VerificationOutcome.DEVICE_UNREADABLE


@dataclass(slots=True)
class SanitizationRecord:
    """
    The complete REQ-PREP-019 record of sanitizing one storage device.
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    device_path: str
    device_model: str
    device_serial_number: str

    method: SanitizationMethod

    started_at: datetime
    completed_at: datetime

    execution_succeeded: bool
    execution_message: str
    return_code: int | None

    verification_outcome: VerificationOutcome
    verification_detail: str

    @property
    def duration(self) -> timedelta:
        return self.completed_at - self.started_at

    @property
    def succeeded(self) -> bool:
        """
        Whether this device's sanitization fully succeeded -- both the
        ``MSFT_Disk.Clear()`` execution itself (REQ-PREP-013 through
        -016) and its independent post-sanitization verification
        (REQ-PREP-017/018).
        """

        return self.execution_succeeded and self.verification_outcome in (
            VerificationOutcome.VERIFIED,
            VerificationOutcome.PARTIAL,
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "device_path": self.device_path,
            "device_model": self.device_model,
            "device_serial_number": self.device_serial_number,
            "method": self.method.name,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_seconds": self.duration.total_seconds(),
            "execution_succeeded": self.execution_succeeded,
            "execution_message": self.execution_message,
            "return_code": self.return_code,
            "verification_outcome": self.verification_outcome.value,
            "verification_detail": self.verification_detail,
            "succeeded": self.succeeded,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SanitizationRecord":
        now = datetime.now(UTC)
        started_at = _parse_datetime(data.get("started_at"), default=now)
        completed_at = _parse_datetime(data.get("completed_at"), default=started_at)

        raw_return_code = data.get("return_code")
        try:
            return_code = int(raw_return_code) if raw_return_code is not None else None
        except (TypeError, ValueError):
            return_code = None

        return cls(
            device_path=str(data.get("device_path") or ""),
            device_model=str(data.get("device_model") or ""),
            device_serial_number=str(data.get("device_serial_number") or ""),
            method=_parse_method(data.get("method"), default=SanitizationMethod.QUICK),
            started_at=started_at,
            completed_at=completed_at,
            execution_succeeded=bool(data.get("execution_succeeded", False)),
            execution_message=str(data.get("execution_message") or ""),
            return_code=return_code,
            verification_outcome=_parse_verification_outcome(
                data.get("verification_outcome")
            ),
            verification_detail=str(data.get("verification_detail") or ""),
        )


@dataclass(slots=True)
class PreparationSummary:
    """
    The complete outcome of one Preparation Engine run: REQ-PREP-002's
    pre-flight summary plus REQ-PREP-019's sanitization report for
    every device touched.
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    started_at: datetime
    completed_at: datetime

    # REQ-PREP-002 pre-flight facts.
    system_manufacturer: str
    system_model: str
    system_serial_number: str
    deployment_workflow: str
    recovery_status: str

    records: list[SanitizationRecord] = field(default_factory=lambda: [])

    aborted: bool = False
    abort_reason: str | None = None
    operator_identity: str | None = None

    def __post_init__(self) -> None:
        self.records = list(self.records)

    @property
    def duration(self) -> timedelta:
        return self.completed_at - self.started_at

    @property
    def all_succeeded(self) -> bool:
        """
        Whether every sanitized device both executed and verified
        successfully, and Preparation was not aborted -- the signal a
        future Provisioning Engine would check before REQ-PROV-001
        allows it to begin (REQ-PREP-023's "halt on unrecoverable
        storage errors" and REQ-PREP-024's "Preparation shall not
        automatically begin provisioning" both hold regardless of this
        value; this only records whether it *may*).
        """

        if self.aborted:
            return False

        return bool(self.records) and all(record.succeeded for record in self.records)

    @property
    def status_message(self) -> str:
        if self.aborted:
            reason = self.abort_reason or "unknown reason"
            return f"Preparation was aborted before completion: {reason}"

        if not self.records:
            return "No devices were sanitized."

        if self.all_succeeded:
            devices = ", ".join(record.device_path for record in self.records)
            return f"Preparation completed: {len(self.records)} device(s) sanitized and verified ({devices})."

        failed = [record.device_path for record in self.records if not record.succeeded]
        return (
            f"Preparation completed with issues: {len(failed)} of "
            f"{len(self.records)} device(s) failed sanitization or "
            f"verification ({', '.join(failed)})."
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
            "system_manufacturer": self.system_manufacturer,
            "system_model": self.system_model,
            "system_serial_number": self.system_serial_number,
            "deployment_workflow": self.deployment_workflow,
            "recovery_status": self.recovery_status,
            "records": [record.to_dict() for record in self.records],
            "aborted": self.aborted,
            "abort_reason": self.abort_reason,
            "operator_identity": self.operator_identity,
            "all_succeeded": self.all_succeeded,
            "status_message": self.status_message,
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return dumps(self.to_dict(), indent=indent, sort_keys=True, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PreparationSummary":
        now = datetime.now(UTC)
        started_at = _parse_datetime(data.get("started_at"), default=now)
        completed_at = _parse_datetime(data.get("completed_at"), default=started_at)

        raw_records = data.get("records", [])
        records = (
            [
                SanitizationRecord.from_dict(cast(Mapping[str, Any], entry))
                for entry in cast("list[Any]", raw_records)
                if isinstance(entry, Mapping)
            ]
            if isinstance(raw_records, list)
            else []
        )

        def _optional_str(key: str) -> str | None:
            value = data.get(key)
            return str(value) if value is not None else None

        return cls(
            started_at=started_at,
            completed_at=completed_at,
            system_manufacturer=str(data.get("system_manufacturer") or ""),
            system_model=str(data.get("system_model") or ""),
            system_serial_number=str(data.get("system_serial_number") or ""),
            deployment_workflow=str(data.get("deployment_workflow") or ""),
            recovery_status=str(data.get("recovery_status") or ""),
            records=records,
            aborted=bool(data.get("aborted", False)),
            abort_reason=_optional_str("abort_reason"),
            operator_identity=_optional_str("operator_identity"),
        )


__all__ = ["PreparationSummary", "SanitizationRecord"]
