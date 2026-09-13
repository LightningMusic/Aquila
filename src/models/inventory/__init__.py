"""
Project Aquila
=============

Inventory Data Models

Typed representations used by the Inventory System (SRS Section
9.10/10.9, REQ-INV-001 through REQ-INV-010): a node's inventory
record, its cluster membership history, and REQ-INV-010 search
query/result shapes.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from models.inventory.cluster import ClusterMembership
from models.inventory.node import REQUIRED_REGISTRATION_FIELDS, InventoryRecord
from models.inventory.registry import (
    InventorySearchCriteria,
    InventorySearchResult,
)

__all__ = [
    "REQUIRED_REGISTRATION_FIELDS",
    "ClusterMembership",
    "InventoryRecord",
    "InventorySearchCriteria",
    "InventorySearchResult",
]
