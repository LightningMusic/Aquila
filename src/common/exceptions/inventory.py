"""
Project Aquila
=============

Inventory Exceptions

Defines exceptions raised by the Inventory System (SRS Section 9.10 /
10.9, REQ-INV-001 through REQ-INV-010).

A dedicated module rather than folding these into
``common.exceptions.deployment`` -- the Inventory System is its own
numbered subsystem (Appendix G lists ``REQ-INV`` separately from
``REQ-CTRL``/``REQ-DEPLOY``), matching how ``recovery.py``,
``provisioning.py``, and ``networking.py`` each already get their own
exception module despite all being deployment-adjacent.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from common.exceptions.application import AquilaError


class InventoryError(AquilaError):
    """
    Base class for all Inventory System exceptions.
    """


class InventoryDatabaseError(InventoryError):
    """
    Raised when the inventory database cannot be opened, migrated, or
    written to.
    """


class InventoryRecordNotFoundError(InventoryError):
    """
    Raised when a requested inventory record does not exist.
    """


class InventoryDuplicateRecordError(InventoryError):
    """
    Raised when an inventory record already exists for a given node
    identifier.
    """


class InventoryValidationError(InventoryError):
    """
    Raised when data supplied to the Inventory System is missing a
    required field or otherwise fails validation.
    """


class InventoryQueryError(InventoryError):
    """
    Raised when an inventory search or query cannot be completed.
    """


__all__ = [
    "InventoryDatabaseError",
    "InventoryDuplicateRecordError",
    "InventoryError",
    "InventoryQueryError",
    "InventoryRecordNotFoundError",
    "InventoryValidationError",
]
