"""
Project Aquila
=============

Inventory Search Models

Supports REQ-INV-010: "The Inventory System shall permit searching by:
Hostname, Node Identifier, Manufacturer, Model, Serial Number." These
are plain query/result value objects -- the actual search
implementation lives in ``inventory.node_registry.NodeRegistry``,
which accepts an ``InventorySearchCriteria`` and returns an
``InventorySearchResult``.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from models.inventory.node import InventoryRecord


@dataclass(slots=True, frozen=True)
class InventorySearchCriteria:
    """
    REQ-INV-010 search criteria. Every field is optional and
    combined with AND semantics; a field left as ``None`` is not
    filtered on. String fields match case-insensitively and as a
    substring (a technician searching "Dell" should find "Dell Inc."),
    matching how every other Aquila search-style filter in this
    project already behaves (for example ``config.manager``'s
    tolerant coercions).
    """

    node_identifier: str | None = None
    hostname: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    status: str | None = None

    limit: int = 100
    offset: int = 0

    def is_empty(self) -> bool:
        return not any(
            (
                self.node_identifier,
                self.hostname,
                self.manufacturer,
                self.model,
                self.serial_number,
                self.status,
            )
        )


@dataclass(slots=True, frozen=True)
class InventorySearchResult:
    """The outcome of one REQ-INV-010 search."""

    records: tuple[InventoryRecord, ...] = field(default_factory=tuple)
    total_matches: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": [record.to_dict() for record in self.records],
            "total_matches": self.total_matches,
        }


__all__ = ["InventorySearchCriteria", "InventorySearchResult"]
