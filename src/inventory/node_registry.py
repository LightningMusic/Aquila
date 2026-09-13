"""
Project Aquila
=============

Node Registry

Owns the ``nodes`` and ``cluster_memberships`` tables of
``inventory.database.InventoryDatabase``: registration, status
updates, cluster membership, and REQ-INV-010 search.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Optional

from common.constants.logging import INVENTORY_LOGGER
from common.enums import NodeStatus
from common.exceptions.inventory import (
    InventoryDatabaseError,
    InventoryDuplicateRecordError,
    InventoryRecordNotFoundError,
)
from inventory.database import InventoryDatabase
from models.inventory.cluster import ClusterMembership
from models.inventory.node import InventoryRecord
from models.inventory.registry import (
    InventorySearchCriteria,
    InventorySearchResult,
)

logger = logging.getLogger(INVENTORY_LOGGER)


def _row_to_record(row: sqlite3.Row) -> InventoryRecord:
    try:
        extensions: dict[str, Any] = json.loads(row["extensions_json"] or "{}")
    except (TypeError, ValueError):
        extensions = {}

    payload: dict[str, Any] = {
        key: row[key] for key in row.keys() if key != "extensions_json"
    }
    payload.update(extensions)

    return InventoryRecord.from_dict(payload)


class NodeRegistry:
    """CRUD and search over the ``nodes`` table (REQ-INV-001/002/010)."""

    def __init__(self, database: InventoryDatabase) -> None:
        self._database = database

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, record: InventoryRecord) -> InventoryRecord:
        """
        Insert a new inventory record (REQ-INV-001).

        Raises:
            InventoryDuplicateRecordError:
                If a record already exists for this node identifier
                (idempotent re-registration is handled one layer up,
                by ``InventoryManager.register_node`` -- this method
                itself is strict, matching how ``NodeRegistry.register``
                and ``ClusterRegistry.register`` are named and used
                elsewhere in this project's own convention).
        """

        try:
            with self._database.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO nodes (
                        node_identifier, hostname, manufacturer, model,
                        serial_number, cpu_model, cpu_core_count,
                        memory_total_bytes, primary_disk_model,
                        primary_disk_capacity_bytes, mac_address, status,
                        cluster_name, node_role, deployment_date,
                        extensions_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.node_identifier,
                        record.hostname,
                        record.manufacturer,
                        record.model,
                        record.serial_number,
                        record.cpu_model,
                        record.cpu_core_count,
                        record.memory_total_bytes,
                        record.primary_disk_model,
                        record.primary_disk_capacity_bytes,
                        record.mac_address,
                        record.status.name,
                        record.cluster_name,
                        record.node_role,
                        record.deployment_date.isoformat(),
                        json.dumps(record.extensions),
                        record.created_at.isoformat(),
                        record.updated_at.isoformat(),
                    ),
                )
        except InventoryDatabaseError as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise InventoryDuplicateRecordError(
                    "An inventory record already exists for node "
                    f"identifier '{record.node_identifier}'."
                ) from exc
            raise

        logger.info(
            "Registered inventory record for node '%s' (%s).",
            record.node_identifier,
            record.hostname or "hostname pending",
        )

        return record

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, node_identifier: str) -> InventoryRecord:
        """
        Raises:
            InventoryRecordNotFoundError: If no record exists.
        """

        with self._database.connection() as conn:
            row = conn.execute(
                "SELECT * FROM nodes WHERE node_identifier = ?",
                (node_identifier,),
            ).fetchone()

        if row is None:
            raise InventoryRecordNotFoundError(
                f"No inventory record exists for node identifier "
                f"'{node_identifier}'."
            )

        return _row_to_record(row)

    def find(self, node_identifier: str) -> Optional[InventoryRecord]:
        """Like :meth:`get`, but returns ``None`` instead of raising."""

        try:
            return self.get(node_identifier)
        except InventoryRecordNotFoundError:
            return None

    def exists(self, node_identifier: str) -> bool:
        return self.find(node_identifier) is not None

    def find_by_serial_number(self, serial_number: str) -> Optional[InventoryRecord]:
        """
        Used to detect a possible duplicate node identity
        (REQ-CTRL-005/REQ-SEC-005) once enough hardware information is
        known to check it -- see ``deployment_controller.inventory.
        InventoryIntake`` for how this is applied.
        """

        if not serial_number:
            return None

        with self._database.connection() as conn:
            row = conn.execute(
                "SELECT * FROM nodes WHERE serial_number = ? LIMIT 1",
                (serial_number,),
            ).fetchone()

        return _row_to_record(row) if row is not None else None

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------

    def update_status(self, node_identifier: str, status: NodeStatus) -> InventoryRecord:
        """
        Raises:
            InventoryRecordNotFoundError: If no record exists.
        """

        from datetime import datetime, timezone

        record = self.get(node_identifier)
        updated_at = datetime.now(timezone.utc)

        with self._database.connection() as conn:
            conn.execute(
                "UPDATE nodes SET status = ?, updated_at = ? "
                "WHERE node_identifier = ?",
                (status.name, updated_at.isoformat(), node_identifier),
            )

        record.status = status
        record.updated_at = updated_at
        return record

    def update_hostname(self, node_identifier: str, hostname: str) -> InventoryRecord:
        from datetime import datetime, timezone

        record = self.get(node_identifier)
        updated_at = datetime.now(timezone.utc)

        with self._database.connection() as conn:
            conn.execute(
                "UPDATE nodes SET hostname = ?, updated_at = ? "
                "WHERE node_identifier = ?",
                (hostname, updated_at.isoformat(), node_identifier),
            )

        record.hostname = hostname
        record.updated_at = updated_at
        return record

    # ------------------------------------------------------------------
    # Cluster membership
    # ------------------------------------------------------------------

    def record_cluster_membership(self, membership: ClusterMembership) -> None:
        with self._database.connection() as conn:
            conn.execute(
                "INSERT INTO cluster_memberships "
                "(node_identifier, cluster_name, node_role, joined_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    membership.node_identifier,
                    membership.cluster_name,
                    membership.node_role.name,
                    membership.joined_at.isoformat(),
                ),
            )
            conn.execute(
                "UPDATE nodes SET cluster_name = ?, node_role = ? "
                "WHERE node_identifier = ?",
                (
                    membership.cluster_name,
                    membership.node_role.name,
                    membership.node_identifier,
                ),
            )

    # ------------------------------------------------------------------
    # Search (REQ-INV-010)
    # ------------------------------------------------------------------

    def search(self, criteria: InventorySearchCriteria) -> InventorySearchResult:
        clauses: list[str] = []
        params: list[object] = []

        def _like(column: str, value: Optional[str]) -> None:
            if value:
                clauses.append(f"{column} LIKE ? COLLATE NOCASE")
                params.append(f"%{value}%")

        _like("node_identifier", criteria.node_identifier)
        _like("hostname", criteria.hostname)
        _like("manufacturer", criteria.manufacturer)
        _like("model", criteria.model)
        _like("serial_number", criteria.serial_number)

        if criteria.status:
            clauses.append("status = ?")
            params.append(criteria.status)

        where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""

        with self._database.connection() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) AS count FROM nodes{where_sql}", params
            ).fetchone()["count"]

            rows = conn.execute(
                f"SELECT * FROM nodes{where_sql} "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (*params, criteria.limit, criteria.offset),
            ).fetchall()

        return InventorySearchResult(
            records=tuple(_row_to_record(row) for row in rows),
            total_matches=int(total),
        )

    def list_all(self, *, limit: int = 1000, offset: int = 0) -> tuple[InventoryRecord, ...]:
        return self.search(
            InventorySearchCriteria(limit=limit, offset=offset)
        ).records

    def count(self) -> int:
        with self._database.connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM nodes").fetchone()
        return int(row["count"])


__all__ = ["NodeRegistry"]
