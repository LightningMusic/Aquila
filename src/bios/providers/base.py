from __future__ import annotations

"""
Project Aquila BIOS Provider Interface

Defines the shared types used throughout the BIOS subsystem.

Every vendor implementation inherits from BIOSProvider and must
implement the complete enterprise BIOS management interface.

This file intentionally contains:

    • Enumerations
    • Dataclasses
    • Firmware models
    • Shared helper types

The abstract BIOSProvider itself is defined in later sections.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum, IntEnum, Flag, auto
from pathlib import Path
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Iterable,
    Iterator,
    Mapping,
    MutableMapping,
    MutableSequence,
    NamedTuple,
    Optional,
    Protocol,
    Sequence,
    TypeAlias,
)

from abc import ABC, abstractmethod
import logging
import platform
import uuid

logger = logging.getLogger(__name__)

# ============================================================
# Common Type Aliases
# ============================================================

JSONPrimitive: TypeAlias = (
    str
    | int
    | float
    | bool
    | None
)

JSONValue: TypeAlias = (
    JSONPrimitive
    | list["JSONValue"]
    | dict[str, "JSONValue"]
)

FirmwareValue: TypeAlias = (
    str
    | int
    | bool
    | float
    | None
)

FirmwareMap: TypeAlias = dict[str, FirmwareValue]

