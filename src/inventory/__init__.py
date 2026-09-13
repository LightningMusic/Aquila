"""
Project Aquila
=============

Inventory System

Implements SRS Section 9.10/10.9, REQ-INV-001 through REQ-INV-010:
the Deployment Controller's persistent record of every managed node,
its deployment history, and its benchmark results.

Public surface:
    * ``InventoryDatabase`` -- schema and connection lifecycle.
    * ``NodeRegistry`` -- node CRUD and REQ-INV-010 search.
    * ``InventoryManager`` -- the ``Service``-conforming facade every
      other subsystem (``deployment_controller``) should use.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from inventory.database import InventoryDatabase
from inventory.inventory_manager import InventoryManager
from inventory.node_registry import NodeRegistry

__all__ = ["InventoryDatabase", "InventoryManager", "NodeRegistry"]
