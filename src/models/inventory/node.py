"""
Project Aquila
=============

Inventory Record Model

The Inventory System's central record for one Aquila-managed node
(REQ-INV-001/002): "Inventory records shall contain, at minimum:
Aquila Node Identifier, Hostname, Manufacturer, Model, Serial Number,
CPU, Memory, Storage, Ethernet MAC Address, Deployment Date."

Field names deliberately mirror
``bootstrap.inventory.NodeInventoryFacts`` one-for-one (manufacturer,
model, serial_number, cpu_model/cpu_core_count, memory_total_bytes,
primary_disk_model/primary_disk_capacity_bytes, mac_address) -- that
already-delivered module is what actually collects these fields on
each node and is the only real producer of a REQ-INV-002 registration
payload, so this model's ``from_registration_payload`` reads its
``to_dict()`` output directly rather than defining a second,
competing field-naming scheme.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Mapping, Optional

from common.enums import NodeStatus
from common.exceptions.inventory import InventoryValidationError

#: REQ-INV-002's minimum required fields for a registration payload.
REQUIRED_REGISTRATION_FIELDS: tuple[str, ...] = (
    "node_identifier",
    "manufacturer",
    "model",
    "serial_number",
    "cpu_model",
    "memory_total_bytes",
    "mac_address",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any, *, default: Optional[datetime] = None) -> datetime:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return default or _utcnow()


@dataclass(slots=True)
class InventoryRecord:
    """One node's inventory record (REQ-INV-001/002)."""

    node_identifier: str
    hostname: str = ""

    manufacturer: str = ""
    model: str = ""
    serial_number: str = ""

    cpu_model: str = ""
    cpu_core_count: int = 0

    memory_total_bytes: int = 0

    primary_disk_model: str = ""
    primary_disk_capacity_bytes: int = 0

    mac_address: str = ""

    status: NodeStatus = NodeStatus.PENDING

    cluster_name: str = ""
    node_role: str = ""

    deployment_date: date = field(default_factory=lambda: _utcnow().date())
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    #: Forward-compatible escape hatch (REQ-INV-008: "shall support
    #: future metadata expansion") -- any registration field this
    #: model does not yet know about is preserved here rather than
    #: discarded.
    extensions: dict[str, Any] = field(default_factory=lambda: {})

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_registration_payload(cls, payload: Mapping[str, Any]) -> "InventoryRecord":
        """
        Build a record from a REQ-INV-002 registration payload (the
        JSON body ``deployment_controller.inventory.InventoryIntake``
        receives at ``POST inventory/nodes``).

        Raises:
            InventoryValidationError:
                If a required REQ-INV-002 field is missing.
        """

        missing = [
            key
            for key in REQUIRED_REGISTRATION_FIELDS
            if not payload.get(key)
        ]
        if missing:
            raise InventoryValidationError(
                "Inventory registration payload is missing required "
                f"REQ-INV-002 field(s): {', '.join(sorted(missing))}."
            )

        known_keys = {
            "node_identifier",
            "hostname",
            "manufacturer",
            "model",
            "serial_number",
            "cpu_model",
            "cpu_core_count",
            "memory_total_bytes",
            "primary_disk_model",
            "primary_disk_capacity_bytes",
            "mac_address",
            "status",
            "cluster_name",
            "node_role",
            "deployment_date",
        }

        extensions = {
            key: value for key, value in payload.items() if key not in known_keys
        }

        status_name = str(payload.get("status") or NodeStatus.PENDING.name)
        try:
            status = NodeStatus[status_name]
        except KeyError:
            status = NodeStatus.PENDING

        deployment_date_value = payload.get("deployment_date")
        deployment_date = _utcnow().date()
        if isinstance(deployment_date_value, str) and deployment_date_value:
            try:
                deployment_date = date.fromisoformat(deployment_date_value)
            except ValueError:
                pass

        return cls(
            node_identifier=str(payload["node_identifier"]),
            hostname=str(payload.get("hostname") or ""),
            manufacturer=str(payload["manufacturer"]),
            model=str(payload["model"]),
            serial_number=str(payload["serial_number"]),
            cpu_model=str(payload["cpu_model"]),
            cpu_core_count=int(payload.get("cpu_core_count") or 0),
            memory_total_bytes=int(payload["memory_total_bytes"]),
            primary_disk_model=str(payload.get("primary_disk_model") or ""),
            primary_disk_capacity_bytes=int(
                payload.get("primary_disk_capacity_bytes") or 0
            ),
            mac_address=str(payload["mac_address"]),
            status=status,
            cluster_name=str(payload.get("cluster_name") or ""),
            node_role=str(payload.get("node_role") or ""),
            deployment_date=deployment_date,
            extensions=extensions,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "InventoryRecord":
        record = cls.from_registration_payload(data)

        raw_created = data.get("created_at")
        raw_updated = data.get("updated_at")
        record.created_at = _parse_datetime(raw_created)
        record.updated_at = _parse_datetime(raw_updated, default=record.created_at)

        return record

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_identifier": self.node_identifier,
            "hostname": self.hostname,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial_number": self.serial_number,
            "cpu_model": self.cpu_model,
            "cpu_core_count": self.cpu_core_count,
            "memory_total_bytes": self.memory_total_bytes,
            "primary_disk_model": self.primary_disk_model,
            "primary_disk_capacity_bytes": self.primary_disk_capacity_bytes,
            "mac_address": self.mac_address,
            "status": self.status.name,
            "cluster_name": self.cluster_name,
            "node_role": self.node_role,
            "deployment_date": self.deployment_date.isoformat(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            **self.extensions,
        }


__all__ = ["REQUIRED_REGISTRATION_FIELDS", "InventoryRecord"]
