"""
Project Aquila
=============

Provisioning Reports

Implements REQ-PROV-011/019 (generate an installation/provisioning
summary), REQ-PROV-018 (log every provisioning operation -- via the
dedicated ``aquila.provisioning`` logger, not this module directly),
and REQ-PROV-012(v1)/-020(v2) (preserve diagnostic information when
provisioning fails).

What ``ProvisioningSummary`` can and cannot report
-------------------------------------------------------
Per this subsystem's architecture (see ``provisioning.boot_handoff``'s
module docstring), the actual Proxmox VE installation
(REQ-PROV-005(v1)/-008(v2)) runs entirely within Phase Two -- a
separate boot session into Proxmox's own official installer, outside
any Aquila Windows process's ability to observe. ``ProvisioningSummary``
therefore honestly reports only what Phase One (this WinPE-hosted
Provisioning Engine) itself did and observed: minimum-requirements
validation, live connectivity checks, answer-file generation, boot
media integrity verification, and whether the one-time boot handoff
was successfully triggered. It does not, and cannot, claim Proxmox VE
was actually installed -- that fact only becomes knowable once
Bootstrap Engine reports in (REQ-BOOT-016), which is a separate
subsystem's summary, not this one's. This is also how REQ-PROV-019(v1)
("verify successful reboot into installed OS") and REQ-PROV-020(v2)
("upon first successful boot, control shall automatically transfer to
Bootstrap Engine") end up satisfied without any code here trying to
observe them directly: Proxmox's own confirmed ``[first-boot]`` answer
-file mechanism (rendered by ``provisioning.answer_file
.render_answer_file`` when ``ProvisioningProfile.bootstrap_source_url``
is set) is what invokes Aquila's Bootstrap Engine on first boot
(REQ-BOOT-001), entirely within Phase Two.

Follows the exact ``SCHEMA_VERSION``/``to_dict()``/``to_json()``/
``from_dict()`` convention ``preparation.report.PreparationSummary``
established.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from json import dumps
from typing import Any, ClassVar, Mapping, TypeAlias

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


def _parse_datetime(value: Any, *, default: datetime) -> datetime:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return default
    return default


@dataclass(slots=True, frozen=True)
class ProvisioningSummary:
    """The complete outcome of one Phase-One Provisioning Engine run."""

    SCHEMA_VERSION: ClassVar[int] = 1

    started_at: datetime
    completed_at: datetime

    node_hostname: str
    target_device_path: str

    requirements_satisfied: bool
    requirements_detail: str

    ethernet_connected: bool
    ethernet_detail: str

    controller_reachable: bool
    controller_detail: str

    answer_file_rendered: bool
    answer_file_detail: str

    media_integrity_verified: bool
    media_integrity_detail: str

    handoff_triggered: bool = False
    handoff_detail: str = ""

    aborted: bool = False
    abort_reason: str | None = None

    @property
    def duration(self) -> timedelta:
        return self.completed_at - self.started_at

    @property
    def ready_for_handoff(self) -> bool:
        """
        Whether every Phase-One prerequisite was satisfied -- the gate
        ``provisioning.provisioning_manager.ProvisioningManager``
        checks before ever calling
        ``provisioning.boot_handoff.PhaseTwoHandoff.handoff()``.
        """

        return (
            not self.aborted
            and self.requirements_satisfied
            and self.ethernet_connected
            and self.controller_reachable
            and self.answer_file_rendered
            and self.media_integrity_verified
        )

    @property
    def status_message(self) -> str:
        if self.aborted:
            return (
                f"Provisioning was aborted: "
                f"{self.abort_reason or 'unknown reason'}"
            )

        if self.handoff_triggered:
            return (
                f"Phase One provisioning complete for "
                f"{self.node_hostname}: the one-time boot handoff to "
                "Phase Two (Proxmox VE installation) was triggered. "
                "Installation success can only be confirmed once "
                "Bootstrap Engine reports in."
            )

        if self.ready_for_handoff:
            return (
                f"Phase One provisioning checks passed for "
                f"{self.node_hostname}, but the boot handoff was not "
                "triggered."
            )

        failures = [
            label
            for label, ok in (
                ("minimum requirements", self.requirements_satisfied),
                ("Ethernet connectivity", self.ethernet_connected),
                (
                    "Deployment Controller reachability",
                    self.controller_reachable,
                ),
                ("answer file generation", self.answer_file_rendered),
                ("boot media integrity", self.media_integrity_verified),
            )
            if not ok
        ]
        return (
            f"Provisioning cannot proceed to Phase Two for "
            f"{self.node_hostname}: failed check(s) -- "
            f"{', '.join(failures)}."
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
            "node_hostname": self.node_hostname,
            "target_device_path": self.target_device_path,
            "requirements_satisfied": self.requirements_satisfied,
            "requirements_detail": self.requirements_detail,
            "ethernet_connected": self.ethernet_connected,
            "ethernet_detail": self.ethernet_detail,
            "controller_reachable": self.controller_reachable,
            "controller_detail": self.controller_detail,
            "answer_file_rendered": self.answer_file_rendered,
            "answer_file_detail": self.answer_file_detail,
            "media_integrity_verified": self.media_integrity_verified,
            "media_integrity_detail": self.media_integrity_detail,
            "handoff_triggered": self.handoff_triggered,
            "handoff_detail": self.handoff_detail,
            "aborted": self.aborted,
            "abort_reason": self.abort_reason,
            "ready_for_handoff": self.ready_for_handoff,
            "status_message": self.status_message,
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return dumps(
            self.to_dict(), indent=indent, sort_keys=True, ensure_ascii=False
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProvisioningSummary":
        now = datetime.now(UTC)
        started_at = _parse_datetime(data.get("started_at"), default=now)
        completed_at = _parse_datetime(
            data.get("completed_at"), default=started_at
        )

        def _optional_str(key: str) -> str | None:
            value = data.get(key)
            return str(value) if value is not None else None

        return cls(
            started_at=started_at,
            completed_at=completed_at,
            node_hostname=str(data.get("node_hostname") or ""),
            target_device_path=str(data.get("target_device_path") or ""),
            requirements_satisfied=bool(
                data.get("requirements_satisfied", False)
            ),
            requirements_detail=str(data.get("requirements_detail") or ""),
            ethernet_connected=bool(data.get("ethernet_connected", False)),
            ethernet_detail=str(data.get("ethernet_detail") or ""),
            controller_reachable=bool(data.get("controller_reachable", False)),
            controller_detail=str(data.get("controller_detail") or ""),
            answer_file_rendered=bool(data.get("answer_file_rendered", False)),
            answer_file_detail=str(data.get("answer_file_detail") or ""),
            media_integrity_verified=bool(
                data.get("media_integrity_verified", False)
            ),
            media_integrity_detail=str(
                data.get("media_integrity_detail") or ""
            ),
            handoff_triggered=bool(data.get("handoff_triggered", False)),
            handoff_detail=str(data.get("handoff_detail") or ""),
            aborted=bool(data.get("aborted", False)),
            abort_reason=_optional_str("abort_reason"),
        )


__all__ = ["ProvisioningSummary"]
