"""
Project Aquila
=============

Hardware Inventory Data Models

Vendor-neutral data structures describing the hardware inventory
collected by ``src/hardware/`` (the detection engines that populate
these models from real WMI/OS queries) and consumed by
``src/inspection/`` (the Inspection Engine that assembles them into a
hardware inspection report, REQ-INS-025) and by ``src/inventory/``
(the long-term inventory record, REQ-INV-002).

Every model here follows the same conventions established by
``bios.models`` (already the authoritative pattern for Aquila data
models): a ``SCHEMA_VERSION`` class variable, ``__post_init__``
normalization/validation, ``to_dict()``/``to_json()``/``from_dict()``
round-tripping, and an ``extensions``/``raw_data``-style escape hatch
so a newer Aquila build's fields don't break an older one reading the
same serialized record.

Where an existing model already captures a concept -- firmware
identity and TPM state are already fully modeled by ``bios.models``
-- this package reuses that model directly rather than defining a
second, competing one (the project's own recent history has a
concrete example of what happens when two representations of the same
concept are allowed to drift: ``common.enums.SanitizationMethod`` and
``config.schemas.deployment_schema.SANITIZATION_METHODS`` disagreeing
on how many sanitization methods exist).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from json import dumps
from typing import Any, Mapping, TypeAlias, cast

# ---------------------------------------------------------------------------
# Shared JSON helpers
#
# Defined here, at package-init time, rather than duplicated in each
# submodule, so every model in this package serializes identically.
# Submodules import these with ``from . import ...`` -- safe even
# though this same ``__init__.py`` later imports those submodules
# below, because Python registers this package in ``sys.modules``
# before executing the rest of this file, and everything a submodule
# needs from here is already defined above that point.
# ---------------------------------------------------------------------------

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class HardwareModelError(ValueError):
    """Base exception raised when a hardware model contains invalid data."""


def make_json_compatible(value: Any) -> JSONValue:
    """
    Recursively convert common Python values into JSON-safe values.

    Unsupported objects are represented by their string form -- this
    is intentional for provider/diagnostic metadata, where preserving
    information is preferable to failing report generation
    (REQ-INS-025: a hardware inspection report must always be
    produced).
    """

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Enum):
        return make_json_compatible(value.value)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, date):
        return value.isoformat()

    if hasattr(value, "to_dict") and callable(value.to_dict):
        return cast(JSONValue, value.to_dict())

    if isinstance(value, Mapping):
        return {
            str(key): make_json_compatible(item)
            for key, item in cast(Mapping[Any, Any], value).items()
        }

    if isinstance(value, (list, tuple, set, frozenset)):
        return [
            make_json_compatible(item)
            for item in cast(
                "list[Any] | tuple[Any, ...] | set[Any] | frozenset[Any]",
                value,
            )
        ]

    return str(value)


def coerce_bool(value: Any, *, field_name: str) -> bool:
    """Convert a supported value to a boolean without unsafe truthiness."""

    if isinstance(value, bool):
        return value

    if isinstance(value, int) and value in (0, 1):
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"true", "yes", "enabled", "on", "1"}:
            return True

        if normalized in {"false", "no", "disabled", "off", "0"}:
            return False

    raise HardwareModelError(
        f"{field_name} must contain a valid boolean value."
    )


def optional_string(value: Any) -> str | None:
    """Convert a value into a string while preserving ``None``."""

    if value is None:
        return None

    return str(value)


def to_json(data: dict[str, JSONValue], *, indent: int | None = None) -> str:
    """Serialize an already-JSON-compatible mapping to a JSON string."""

    return dumps(data, indent=indent, sort_keys=True, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Public model re-exports
# ---------------------------------------------------------------------------

from .cpu import CPUArchitecture, CPUInfo  # noqa: E402
from .memory import MemoryInfo, MemoryModule, MemoryType  # noqa: E402
from .storage import StorageDevice, StorageDeviceType, StorageInventory  # noqa: E402
from .smart import SMARTAttribute, SMARTReport  # noqa: E402
from .network import NetworkAdapter, NetworkAdapterType  # noqa: E402
from .battery import BatteryInfo  # noqa: E402
from .virtualization import VirtualizationInfo, VirtualizationTechnology  # noqa: E402
from .bios import BIOSInspectionInfo  # noqa: E402
from .gpu import GPUInfo  # noqa: E402

__all__ = [
    "HardwareModelError",
    "JSONScalar",
    "JSONValue",
    "make_json_compatible",
    "coerce_bool",
    "optional_string",
    "to_json",
    "CPUArchitecture",
    "CPUInfo",
    "MemoryInfo",
    "MemoryModule",
    "MemoryType",
    "StorageDevice",
    "StorageDeviceType",
    "StorageInventory",
    "SMARTAttribute",
    "SMARTReport",
    "NetworkAdapter",
    "NetworkAdapterType",
    "BatteryInfo",
    "VirtualizationInfo",
    "VirtualizationTechnology",
    "BIOSInspectionInfo",
    "GPUInfo",
]
