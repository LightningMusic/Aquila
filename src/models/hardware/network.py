"""
Project Aquila
=============

Network Adapter Inventory Model

Data structures populated by ``hardware.network`` (REQ-INS-009
through REQ-INS-011, REQ-INS-024) and consumed by the Inspection
Engine's hardware report and the Networking Engine (REQ-NET-001
through REQ-NET-003).

Reuses ``common.enums.EthernetStatus`` for wired link state rather
than defining a second, competing enum -- see this package's
``__init__`` docstring.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Mapping, cast

from common.enums import EthernetStatus

from . import HardwareModelError, JSONValue, coerce_bool, make_json_compatible, optional_string
from . import to_json as _to_json


class NetworkAdapterType(str, Enum):
    """Normalized network adapter category."""

    ETHERNET = "ethernet"
    WIRELESS = "wireless"
    BLUETOOTH = "bluetooth"
    VIRTUAL = "virtual"
    LOOPBACK = "loopback"
    OTHER = "other"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, value: str | None) -> "NetworkAdapterType":
        if not value:
            return cls.UNKNOWN

        normalized = value.strip().lower()

        aliases: dict[str, NetworkAdapterType] = {
            "ethernet": cls.ETHERNET,
            "wired": cls.ETHERNET,
            "wireless": cls.WIRELESS,
            "wifi": cls.WIRELESS,
            "wi-fi": cls.WIRELESS,
            "802.11": cls.WIRELESS,
            "bluetooth": cls.BLUETOOTH,
            "virtual": cls.VIRTUAL,
            "loopback": cls.LOOPBACK,
            "other": cls.OTHER,
            "unknown": cls.UNKNOWN,
        }

        return aliases.get(normalized, cls.UNKNOWN)


@dataclass(slots=True)
class NetworkAdapter:
    """
    A single network adapter enumerated by REQ-INS-009 (all
    adapters), REQ-INS-010 (wired Ethernet identification), and
    REQ-INS-011 (wireless detection).

    ``link_status`` (REQ-INS-024: verify Ethernet link status /
    REQ-NET-003) is only meaningful for
    ``adapter_type == NetworkAdapterType.ETHERNET`` -- left ``None``
    for every other adapter type.
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    name: str = ""
    description: str = ""
    adapter_type: NetworkAdapterType = NetworkAdapterType.UNKNOWN

    mac_address: str = ""
    is_physical: bool = True
    is_enabled: bool = True

    speed_mbps: int | None = None
    driver_version: str = ""

    link_status: EthernetStatus | None = None
    ip_addresses: list[str] = field(default_factory=lambda: [])

    #: ``Win32_NetworkAdapterConfiguration.DefaultIPGateway`` -- the
    #: adapter's currently assigned default gateway(s), when IP is
    #: enabled and a gateway has been assigned (by DHCP or a prior
    #: static configuration). Needed by the Networking Engine's
    #: REQ-NET-007 gateway check when the assignment method is DHCP,
    #: where no gateway is known ahead of time from configuration.
    default_gateways: list[str] = field(default_factory=lambda: [])

    #: ``Win32_NetworkAdapter.Index`` / ``Win32_NetworkAdapterConfiguration
    #: .Index`` -- the join key the Networking Engine needs to invoke a
    #: mutating configuration method (``EnableDHCP``, ``EnableStatic``,
    #: ...) against the correct adapter (REQ-NET-005). ``None`` for any
    #: adapter not sourced from a live WMI query (e.g. a test double).
    interface_index: int | None = None

    extensions: dict[str, Any] = field(default_factory=lambda: {})

    def __post_init__(self) -> None:
        if isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            self.adapter_type, str
        ):
            self.adapter_type = NetworkAdapterType.from_string(self.adapter_type)

        if isinstance(self.link_status, str):
            try:
                self.link_status = EthernetStatus[self.link_status.strip().upper()]
            except KeyError:
                self.link_status = None

        self.name = self.name.strip()
        self.description = self.description.strip()
        self.mac_address = self.mac_address.strip().upper()
        self.driver_version = self.driver_version.strip()

        if self.speed_mbps is not None and self.speed_mbps < 0:
            raise HardwareModelError(
                "NetworkAdapter.speed_mbps must not be negative."
            )

        self.ip_addresses = list(self.ip_addresses)
        self.default_gateways = list(self.default_gateways)
        self.extensions = dict(self.extensions)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "name": self.name,
            "description": self.description,
            "adapter_type": self.adapter_type.value,
            "mac_address": self.mac_address,
            "is_physical": self.is_physical,
            "is_enabled": self.is_enabled,
            "speed_mbps": self.speed_mbps,
            "driver_version": self.driver_version,
            "link_status": (
                self.link_status.name if self.link_status is not None else None
            ),
            "ip_addresses": list(self.ip_addresses),
            "default_gateways": list(self.default_gateways),
            "interface_index": self.interface_index,
            "extensions": make_json_compatible(self.extensions),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return _to_json(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "NetworkAdapter":
        known_keys = {
            "schema_version",
            "name",
            "description",
            "adapter_type",
            "mac_address",
            "is_physical",
            "is_enabled",
            "speed_mbps",
            "driver_version",
            "link_status",
            "ip_addresses",
            "default_gateways",
            "interface_index",
            "extensions",
        }

        extensions = {
            key: value for key, value in data.items() if key not in known_keys
        }

        link_status_raw = data.get("link_status")
        link_status: EthernetStatus | None = None
        if link_status_raw:
            try:
                link_status = EthernetStatus[str(link_status_raw).strip().upper()]
            except KeyError:
                link_status = None

        raw_ips = data.get("ip_addresses", [])
        if not isinstance(raw_ips, list):
            raise HardwareModelError("NetworkAdapter.ip_addresses must be a list.")
        raw_ips = cast("list[Any]", raw_ips)

        raw_gateways = data.get("default_gateways", [])
        if not isinstance(raw_gateways, list):
            raise HardwareModelError(
                "NetworkAdapter.default_gateways must be a list."
            )
        raw_gateways = cast("list[Any]", raw_gateways)

        return cls(
            name=str(data.get("name") or ""),
            description=str(data.get("description") or ""),
            adapter_type=NetworkAdapterType.from_string(
                optional_string(data.get("adapter_type"))
            ),
            mac_address=str(data.get("mac_address") or ""),
            is_physical=coerce_bool(
                data.get("is_physical", True), field_name="is_physical"
            ),
            is_enabled=coerce_bool(
                data.get("is_enabled", True), field_name="is_enabled"
            ),
            speed_mbps=(
                int(data["speed_mbps"]) if data.get("speed_mbps") is not None else None
            ),
            driver_version=str(data.get("driver_version") or ""),
            link_status=link_status,
            ip_addresses=[str(ip) for ip in raw_ips],
            default_gateways=[str(gateway) for gateway in raw_gateways],
            interface_index=(
                int(data["interface_index"])
                if data.get("interface_index") is not None
                else None
            ),
            extensions=extensions,
        )


__all__ = ["NetworkAdapter", "NetworkAdapterType"]
