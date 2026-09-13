"""
Project Aquila
=============

Deployment Controller Inventory Intake

The HTTP-facing adapter for REQ-CTRL-009 ("register inventory") and
REQ-CTRL-013 ("receive benchmark results"): validates and translates
inbound JSON payloads (``POST inventory/nodes``, ``POST
inventory/benchmarks``) into calls against
``inventory.inventory_manager.InventoryManager``, which owns the
actual persistence (REQ-INV-001 through REQ-INV-010).

Kept separate from ``InventoryManager`` itself: this module's job is
"is this HTTP request well-formed and who is it about", while
``InventoryManager``'s job is "what does the Inventory Engine's data
model look like" -- the same request-vs-engine split
``provisioning.connectivity.ConnectivityChecker`` already draws
against ``networking.ethernet.EthernetChecker``.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from common.constants.logging import INVENTORY_LOGGER
from common.exceptions.inventory import InventoryValidationError
from inventory.inventory_manager import InventoryManager
from models.inventory.node import InventoryRecord

logger = logging.getLogger(INVENTORY_LOGGER)


@dataclass(slots=True, frozen=True)
class IntakeResult:
    """The outcome of one REQ-CTRL-009/013 intake operation."""

    accepted: bool
    detail: str = ""


class InventoryIntake:
    """Validates and forwards inventory/benchmark submissions."""

    def __init__(self, *, inventory_manager: InventoryManager) -> None:
        self._inventory_manager = inventory_manager

    def register(self, node_identifier: str, payload: Mapping[str, Any]) -> IntakeResult:
        """
        REQ-CTRL-009/REQ-INV-001/002.

        Enforces that the ``node_identifier`` used to authenticate the
        request matches the payload's own ``node_identifier`` (a node
        may only register inventory for itself), and flags -- without
        blocking registration on -- a serial number that already
        belongs to a *different* node identifier (REQ-CTRL-005/
        REQ-SEC-005's duplicate-identity concern, checked here because
        this is the first point in the request lifecycle where enough
        hardware information exists to check it at all; authentication
        itself only ever sees a bare node identifier).
        """

        merged = dict(payload)
        merged.setdefault("node_identifier", node_identifier)

        if str(merged.get("node_identifier")) != node_identifier:
            return IntakeResult(
                accepted=False,
                detail=(
                    "Inventory registration node_identifier does not match "
                    "the authenticated node."
                ),
            )

        try:
            record = InventoryRecord.from_registration_payload(merged)
        except InventoryValidationError as exc:
            return IntakeResult(accepted=False, detail=str(exc))

        existing_by_serial = self._inventory_manager.find_by_serial_number(
            record.serial_number
        )
        if (
            existing_by_serial is not None
            and existing_by_serial.node_identifier != node_identifier
        ):
            logger.warning(
                "Node '%s' registered with serial number '%s', which is "
                "already recorded under a different node identifier "
                "('%s'). Registration proceeds, but this is logged as a "
                "possible duplicate hardware identity (REQ-CTRL-005).",
                node_identifier,
                record.serial_number,
                existing_by_serial.node_identifier,
            )

        self._inventory_manager.register_node(record)
        return IntakeResult(accepted=True, detail="Inventory record registered.")

    def submit_benchmark(
        self, node_identifier: str, payload: Mapping[str, Any]
    ) -> IntakeResult:
        """REQ-CTRL-013/REQ-INV-003/REQ-BENCH-007."""

        if self._inventory_manager.find(node_identifier) is None:
            return IntakeResult(
                accepted=False,
                detail=(
                    f"Node '{node_identifier}' is not registered; submit "
                    "inventory before benchmark results."
                ),
            )

        self._inventory_manager.record_benchmark(node_identifier, payload)
        return IntakeResult(accepted=True, detail="Benchmark result recorded.")


__all__ = ["IntakeResult", "InventoryIntake"]
