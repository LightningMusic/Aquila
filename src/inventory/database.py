"""
Project Aquila
=============

Inventory Database

The Deployment Controller's single persistent SQLite store: node
inventory records (REQ-INV-001/002), cluster membership history
(REQ-CTRL-007), deployment sessions (REQ-CTRL-010), deployment
completion reports (REQ-CTRL-015/REQ-INV-007), benchmark results
(REQ-INV-003), and node approval decisions (REQ-CTRL-016).

One SQLite file for the whole Controller service, not one database
engine per requirement group: REQ-INV and REQ-CTRL are two
requirement *groupings* over what is, in practice, a single
long-running service process with one obvious place to keep its
state. ``inventory.node_registry.NodeRegistry`` and
``inventory.inventory_manager.InventoryManager`` own the ``nodes``/
``cluster_memberships``/``deployment_sessions``/``deployment_reports``/
``benchmarks`` tables; ``deployment_controller.authorization.
DeploymentAuthorizer`` owns ``approvals`` -- each module queries only
the table(s) it is responsible for, through the shared
:meth:`InventoryDatabase.connection` this class provides, so the
schema itself stays centralized in one file while the query logic
for each table stays with the subsystem that understands it.

Concurrency: SQLite connections are opened fresh per call (never held
open across requests) rather than shared across the Controller's
worker threads -- ``sqlite3.Connection`` objects are not safe to use
concurrently from multiple threads, and a short-lived
connect/use/commit/close per request is both simpler to reason about
and entirely adequate at the scale this project targets (SRS Section
3, "individual laboratory deployments" through "many nodes", not an
Internet-scale service). SQLite's own WAL journal mode is enabled so
concurrent readers are never blocked by a writer.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional, Union

from common.constants.logging import INVENTORY_LOGGER
from common.exceptions.inventory import InventoryDatabaseError
from common.paths import INVENTORY_DATABASE_FILE

logger = logging.getLogger(INVENTORY_LOGGER)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS nodes (
    node_identifier TEXT PRIMARY KEY,
    hostname TEXT NOT NULL DEFAULT '',
    manufacturer TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    serial_number TEXT NOT NULL DEFAULT '',
    cpu_model TEXT NOT NULL DEFAULT '',
    cpu_core_count INTEGER NOT NULL DEFAULT 0,
    memory_total_bytes INTEGER NOT NULL DEFAULT 0,
    primary_disk_model TEXT NOT NULL DEFAULT '',
    primary_disk_capacity_bytes INTEGER NOT NULL DEFAULT 0,
    mac_address TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'PENDING',
    cluster_name TEXT NOT NULL DEFAULT '',
    node_role TEXT NOT NULL DEFAULT '',
    deployment_date TEXT NOT NULL,
    extensions_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_nodes_hostname ON nodes (hostname);
CREATE INDEX IF NOT EXISTS idx_nodes_serial_number ON nodes (serial_number);

CREATE TABLE IF NOT EXISTS cluster_memberships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_identifier TEXT NOT NULL,
    cluster_name TEXT NOT NULL,
    node_role TEXT NOT NULL,
    joined_at TEXT NOT NULL,
    FOREIGN KEY (node_identifier) REFERENCES nodes (node_identifier)
);

CREATE TABLE IF NOT EXISTS deployment_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_identifier TEXT NOT NULL,
    workflow TEXT NOT NULL DEFAULT '',
    phase TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_node
    ON deployment_sessions (node_identifier);

CREATE TABLE IF NOT EXISTS deployment_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_identifier TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    received_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reports_node
    ON deployment_reports (node_identifier);

CREATE TABLE IF NOT EXISTS benchmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_identifier TEXT NOT NULL,
    overall_score INTEGER NOT NULL DEFAULT 0,
    successful INTEGER NOT NULL DEFAULT 1,
    payload_json TEXT NOT NULL DEFAULT '{}',
    reported_at TEXT NOT NULL,
    received_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_benchmarks_node ON benchmarks (node_identifier);

CREATE TABLE IF NOT EXISTS approvals (
    node_identifier TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'PENDING',
    reason TEXT NOT NULL DEFAULT '',
    decided_by TEXT NOT NULL DEFAULT '',
    decided_at TEXT NOT NULL
);
"""


class InventoryDatabase:
    """
    Owns the Controller's SQLite schema and connection lifecycle.
    Satisfies ``interfaces.service.Service``.
    """

    def __init__(self, database_path: Optional[Union[str, Path]] = None) -> None:
        self._path = Path(database_path) if database_path else INVENTORY_DATABASE_FILE
        self._initialized = False

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """
        Create the database file and schema if they do not exist.

        Every statement in ``_SCHEMA_SQL`` is ``CREATE ... IF NOT
        EXISTS``, so calling this against a database file a previous,
        older build of Aquila already created is a safe no-op over the
        existing tables/rows rather than a destructive re-create --
        this is REQ-INV-009's "maintain inventory consistency after
        software upgrades": upgrading the Controller in place and
        restarting it (new code, same database file) never loses or
        corrupts previously-recorded inventory data.
        """

        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self.connection() as conn:
                conn.executescript(_SCHEMA_SQL)
        except sqlite3.Error as exc:
            raise InventoryDatabaseError(
                f"Could not initialize the inventory database at "
                f"'{self._path}': {exc}"
            ) from exc

        self._initialized = True
        logger.info("Inventory database ready at %s", self._path)

    def shutdown(self) -> None:
        """
        No-op beyond marking this instance uninitialized: every
        connection this class hands out is opened and closed within a
        single ``with`` block (see :meth:`connection`), so there is no
        persistent connection here to release.
        """

        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def path(self) -> Path:
        return self._path

    # ------------------------------------------------------------------
    # Connections
    # ------------------------------------------------------------------

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Open a fresh connection, yield it, and commit/rollback and
        close it on exit. Every caller (``NodeRegistry``,
        ``InventoryManager``, ``DeploymentAuthorizer``) uses this for
        every operation rather than holding a connection across calls.
        """

        try:
            conn = sqlite3.connect(str(self._path), timeout=30.0)
        except sqlite3.Error as exc:
            raise InventoryDatabaseError(
                f"Could not open the inventory database at "
                f"'{self._path}': {exc}"
            ) from exc

        conn.row_factory = sqlite3.Row

        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            yield conn
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise InventoryDatabaseError(
                f"Inventory database operation failed: {exc}"
            ) from exc
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


__all__ = ["InventoryDatabase"]
