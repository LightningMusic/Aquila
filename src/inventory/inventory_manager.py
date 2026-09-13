"""
Project Aquila
=============

Inventory Manager

The Inventory Engine's ``Service``-conforming facade (SRS Section
9.10/10.9, REQ-INV-001 through REQ-INV-010). Composes
``InventoryDatabase`` and ``NodeRegistry`` for node records, and owns
the ``deployment_sessions``/``deployment_reports``/``benchmarks``
tables directly (REQ-CTRL-010/011/012/015, REQ-INV-003/006/007) --
this is the single entry point ``deployment_controller``'s modules
call into; nothing outside ``inventory/`` talks to
``InventoryDatabase`` or ``NodeRegistry`` directly (NFR-MAIN-002,
documented interfaces).

Session tracking is deliberately lightweight: REQ-CTRL-010 asks that
every deployment session be recorded, but no endpoint in
``bootstrap.controller_client``'s API contract exists to open/close a
session explicitly. A session is opened when a node authenticates
(``open_session``, called from ``deployment_controller.controller``'s
authenticate handler) and closed by the next completion report for
that node (``close_session``) -- the two points in the existing
client contract that actually correspond to "a deployment attempt
began" and "a deployment attempt ended".

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional

from common.constants.logging import INVENTORY_LOGGER
from common.enums import DeploymentPhase, DeploymentStatus, NodeStatus
from common.events.types.controller import (
    BenchmarkRecordedEvent,
    DeploymentReportRecordedEvent,
    NodeRegisteredEvent,
    NodeStatusChangedEvent,
)
from common.exceptions.inventory import InventoryRecordNotFoundError
from inventory.database import InventoryDatabase
from inventory.node_registry import NodeRegistry
from models.benchmark.benchmark import BenchmarkRecord
from models.deployment.report import DeploymentReportRecord
from models.deployment.session import DeploymentSessionRecord
from models.inventory.cluster import ClusterMembership
from models.inventory.node import InventoryRecord
from models.inventory.registry import (
    InventorySearchCriteria,
    InventorySearchResult,
)

logger = logging.getLogger(INVENTORY_LOGGER)


class InventoryManager:
    """
    Composition root for the Inventory Engine. Satisfies
    ``interfaces.service.Service``.
    """

    def __init__(
        self,
        *,
        database: Optional[InventoryDatabase] = None,
        node_registry: Optional[NodeRegistry] = None,
        event_bus: "Optional[Any]" = None,
    ) -> None:
        self._database = database or InventoryDatabase()
        self._node_registry = node_registry or NodeRegistry(self._database)
        self._event_bus = event_bus
        self._initialized = False

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        self._database.initialize()
        self._initialized = True

    def shutdown(self) -> None:
        self._database.shutdown()
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def node_registry(self) -> NodeRegistry:
        return self._node_registry

    # ------------------------------------------------------------------
    # Node registration (REQ-INV-001/002)
    # ------------------------------------------------------------------

    def register_node(self, record: InventoryRecord) -> InventoryRecord:
        """
        Register a node, or update its existing record.

        Idempotent by design: REQ-BOOT-014 registration can legitimately
        be retried (a network interruption, a re-run bootstrap), so a
        second registration for the same node identifier updates the
        existing record's hardware facts rather than raising -- true
        duplicate *identity* rejection (REQ-CTRL-005/REQ-SEC-005) is a
        judgment call made one layer up, by
        ``deployment_controller.inventory.InventoryIntake``, which has
        the context (the authenticated request) to tell "the same node
        re-registering" apart from "a different node claiming an
        identifier it doesn't own".
        """

        existing = self._node_registry.find(record.node_identifier)

        if existing is None:
            self._node_registry.register(record)
            self._publish(
                lambda: NodeRegisteredEvent(
                    record.node_identifier, record.hostname
                )
            )
            return record

        # Preserve the existing record's status/hostname/cluster
        # assignment -- those are the Controller's own decisions, not
        # something a re-submitted hardware-facts payload should
        # silently overwrite.
        record.status = existing.status
        record.hostname = record.hostname or existing.hostname
        record.cluster_name = existing.cluster_name
        record.node_role = existing.node_role
        record.created_at = existing.created_at

        with self._database.connection() as conn:
            conn.execute(
                """
                UPDATE nodes SET
                    hostname = ?, manufacturer = ?, model = ?,
                    serial_number = ?, cpu_model = ?, cpu_core_count = ?,
                    memory_total_bytes = ?, primary_disk_model = ?,
                    primary_disk_capacity_bytes = ?, mac_address = ?,
                    extensions_json = ?, updated_at = ?
                WHERE node_identifier = ?
                """,
                (
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
                    json.dumps(record.extensions),
                    datetime.now(timezone.utc).isoformat(),
                    record.node_identifier,
                ),
            )

        logger.info(
            "Updated inventory record for existing node '%s'.",
            record.node_identifier,
        )

        return record

    def get(self, node_identifier: str) -> InventoryRecord:
        return self._node_registry.get(node_identifier)

    def find(self, node_identifier: str) -> Optional[InventoryRecord]:
        return self._node_registry.find(node_identifier)

    def find_by_serial_number(self, serial_number: str) -> Optional[InventoryRecord]:
        return self._node_registry.find_by_serial_number(serial_number)

    def search(self, criteria: InventorySearchCriteria) -> InventorySearchResult:
        return self._node_registry.search(criteria)

    def update_status(self, node_identifier: str, status: NodeStatus) -> InventoryRecord:
        previous = self._node_registry.get(node_identifier)
        updated = self._node_registry.update_status(node_identifier, status)

        if previous.status is not status:
            self._publish(
                lambda: NodeStatusChangedEvent(
                    node_identifier, previous.status.name, status.name
                )
            )

        return updated

    def update_hostname(self, node_identifier: str, hostname: str) -> InventoryRecord:
        return self._node_registry.update_hostname(node_identifier, hostname)

    def record_cluster_membership(self, membership: ClusterMembership) -> None:
        self._node_registry.record_cluster_membership(membership)

    # ------------------------------------------------------------------
    # Deployment sessions (REQ-CTRL-010/011/012)
    #
    # get_sessions() returns every session recorded for one node, most
    # recent first -- this is REQ-CTRL-012's "maintain deployment
    # history for each node" (and, from the Inventory System's own
    # side of the same table, REQ-INV-006's "record deployment
    # history").
    # ------------------------------------------------------------------

    def open_session(
        self, node_identifier: str, *, workflow: str = "provisioning"
    ) -> DeploymentSessionRecord:
        session = DeploymentSessionRecord(
            node_identifier=node_identifier,
            workflow=workflow,
            phase=DeploymentPhase.BOOTSTRAP.name,
            status=DeploymentStatus.RUNNING.name,
        )

        with self._database.connection() as conn:
            cursor = conn.execute(
                "INSERT INTO deployment_sessions "
                "(node_identifier, workflow, phase, status, detail, "
                "started_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, NULL)",
                (
                    session.node_identifier,
                    session.workflow,
                    session.phase,
                    session.status,
                    session.detail,
                    session.started_at.isoformat(),
                ),
            )
            session.id = cursor.lastrowid

        return session

    def close_session(
        self, node_identifier: str, *, status: DeploymentStatus, detail: str = ""
    ) -> Optional[DeploymentSessionRecord]:
        """
        Close the most recent open session for ``node_identifier``, if
        any. Returns ``None`` (rather than raising) when no open
        session exists -- a completion report arriving without a
        matching ``open_session`` call (for example, a Controller
        restart between the two) should still be recorded by
        ``record_report``, just without a session to close.
        """

        with self._database.connection() as conn:
            row = conn.execute(
                "SELECT * FROM deployment_sessions WHERE node_identifier = ? "
                "AND completed_at IS NULL ORDER BY started_at DESC LIMIT 1",
                (node_identifier,),
            ).fetchone()

            if row is None:
                return None

            completed_at = datetime.now(timezone.utc)
            conn.execute(
                "UPDATE deployment_sessions SET status = ?, detail = ?, "
                "completed_at = ? WHERE id = ?",
                (status.name, detail, completed_at.isoformat(), row["id"]),
            )

        session = DeploymentSessionRecord.from_dict(dict(row))
        session.status = status.name
        session.detail = detail
        session.completed_at = completed_at
        return session

    def get_sessions(self, node_identifier: str) -> tuple[DeploymentSessionRecord, ...]:
        with self._database.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM deployment_sessions WHERE node_identifier = ? "
                "ORDER BY started_at DESC",
                (node_identifier,),
            ).fetchall()

        return tuple(DeploymentSessionRecord.from_dict(dict(row)) for row in rows)

    # ------------------------------------------------------------------
    # Deployment reports (REQ-CTRL-015, REQ-INV-007, REQ-BOOT-016)
    # ------------------------------------------------------------------

    def record_report(
        self, node_identifier: str, *, status: str, detail: str = ""
    ) -> DeploymentReportRecord:
        report = DeploymentReportRecord(
            node_identifier=node_identifier, status=status, detail=detail
        )

        with self._database.connection() as conn:
            cursor = conn.execute(
                "INSERT INTO deployment_reports "
                "(node_identifier, status, detail, received_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    report.node_identifier,
                    report.status,
                    report.detail,
                    report.received_at.isoformat(),
                ),
            )
            report_id = cursor.lastrowid

        self.close_session(
            node_identifier,
            status=(
                DeploymentStatus.SUCCESS
                if report.successful
                else DeploymentStatus.FAILED
            ),
            detail=detail,
        )

        try:
            self.update_status(
                node_identifier,
                NodeStatus.OPERATIONAL if report.successful else NodeStatus.FAILED,
            )
        except InventoryRecordNotFoundError:
            logger.warning(
                "Received a completion report for unregistered node '%s'.",
                node_identifier,
            )

        self._publish(
            lambda: DeploymentReportRecordedEvent(node_identifier, status)
        )

        return DeploymentReportRecord(
            node_identifier=report.node_identifier,
            status=report.status,
            detail=report.detail,
            id=report_id,
            received_at=report.received_at,
        )

    def get_reports(self, node_identifier: str) -> tuple[DeploymentReportRecord, ...]:
        with self._database.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM deployment_reports WHERE node_identifier = ? "
                "ORDER BY received_at DESC",
                (node_identifier,),
            ).fetchall()

        return tuple(DeploymentReportRecord.from_dict(dict(row)) for row in rows)

    # ------------------------------------------------------------------
    # Benchmarks (REQ-INV-003, REQ-BENCH-007/010)
    #
    # record_benchmark()/get_benchmarks() are also this Controller's
    # REQ-CTRL-014 "store benchmark history": every submitted result is
    # appended to the ``benchmarks`` table (never overwritten), and
    # get_benchmarks() returns the full history for a node, newest
    # first.
    # ------------------------------------------------------------------

    def record_benchmark(
        self, node_identifier: str, payload: Mapping[str, Any]
    ) -> BenchmarkRecord:
        record = BenchmarkRecord.from_payload(node_identifier, payload)

        with self._database.connection() as conn:
            conn.execute(
                "INSERT INTO benchmarks (node_identifier, overall_score, "
                "successful, payload_json, reported_at, received_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.node_identifier,
                    record.overall_score,
                    1 if record.successful else 0,
                    json.dumps(dict(payload)),
                    record.reported_at.isoformat(),
                    record.received_at.isoformat(),
                ),
            )

        self._publish(
            lambda: BenchmarkRecordedEvent(node_identifier, record.overall_score)
        )

        return record

    def get_benchmarks(self, node_identifier: str) -> tuple[BenchmarkRecord, ...]:
        with self._database.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM benchmarks WHERE node_identifier = ? "
                "ORDER BY received_at DESC",
                (node_identifier,),
            ).fetchall()

        results: list[BenchmarkRecord] = []
        for row in rows:
            try:
                payload: dict[str, Any] = json.loads(row["payload_json"])
            except (TypeError, ValueError):
                payload = {}
            record = BenchmarkRecord.from_payload(row["node_identifier"], payload)
            record.received_at = datetime.fromisoformat(row["received_at"])
            results.append(record)

        return tuple(results)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _publish(self, build_event: Callable[[], Any]) -> None:
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish(build_event())
        except Exception:  # pragma: no cover - event delivery is best-effort
            logger.debug("Failed to publish inventory event.", exc_info=True)


__all__ = ["InventoryManager"]
