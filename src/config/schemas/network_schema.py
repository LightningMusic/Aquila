"""
Project Aquila
=============

Network Configuration Schema

Defines the validated, typed structure of ``configs/network.yaml``:
how the Networking Engine acquires an IP address and which
connectivity checks must pass before Aquila Node Provisioning
(Workflow B) is allowed to proceed.

See SRS Section 9.13 (Networking) and REQ-NET-001 through REQ-NET-014.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping, Optional

from common.exceptions.configuration import ConfigurationValueError
from config.validators.schema_validator import (
    coerce_bool,
    coerce_int,
    coerce_str,
    coerce_str_list,
    require_mapping,
    validate_choice,
    validate_range,
)

#: IP assignment methods, matching REQ-NET-005.
IP_ASSIGNMENT_METHODS: tuple[str, ...] = (
    "dhcp",
    "static_ipv4",
    "static_ipv6",
)


@dataclass(slots=True)
class NetworkConfig:
    """
    Networking Engine connectivity policy.
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    ip_assignment_method: str = "dhcp"

    static_ipv4_address: Optional[str] = None
    static_ipv4_netmask: Optional[str] = None
    static_ipv4_gateway: Optional[str] = None

    static_ipv6_address: Optional[str] = None
    static_ipv6_prefix_length: Optional[int] = None
    static_ipv6_gateway: Optional[str] = None

    dns_servers: list[str] = field(default_factory=lambda: [])

    require_ethernet_link: bool = True
    require_gateway_reachability: bool = True
    require_dns_resolution: bool = True

    connectivity_check_timeout_seconds: int = 30
    connectivity_check_retry_count: int = 3

    extensions: dict[str, Any] = field(default_factory=lambda: {})

    def __post_init__(self) -> None:
        """Validate networking policy invariants."""

        validate_choice(
            self.ip_assignment_method,
            IP_ASSIGNMENT_METHODS,
            field_name="ip_assignment_method",
        )

        if self.ip_assignment_method == "static_ipv4" and not (
            self.static_ipv4_address and self.static_ipv4_gateway
        ):
            raise ConfigurationValueError(
                "'static_ipv4_address' and 'static_ipv4_gateway' are "
                "required when 'ip_assignment_method' is "
                "'static_ipv4'."
            )

        if self.ip_assignment_method == "static_ipv6" and not (
            self.static_ipv6_address and self.static_ipv6_gateway
        ):
            raise ConfigurationValueError(
                "'static_ipv6_address' and 'static_ipv6_gateway' are "
                "required when 'ip_assignment_method' is "
                "'static_ipv6'."
            )

        validate_range(
            self.connectivity_check_timeout_seconds,
            field_name="connectivity_check_timeout_seconds",
            minimum=1,
        )

        validate_range(
            self.connectivity_check_retry_count,
            field_name="connectivity_check_retry_count",
            minimum=0,
        )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> NetworkConfig:
        """Construct a validated ``NetworkConfig`` from a raw mapping."""

        mapping = require_mapping(data, section="network")

        known_keys = {
            "schema_version",
            "ip_assignment_method",
            "static_ipv4_address",
            "static_ipv4_netmask",
            "static_ipv4_gateway",
            "static_ipv6_address",
            "static_ipv6_prefix_length",
            "static_ipv6_gateway",
            "dns_servers",
            "require_ethernet_link",
            "require_gateway_reachability",
            "require_dns_resolution",
            "connectivity_check_timeout_seconds",
            "connectivity_check_retry_count",
        }

        extensions = {
            key: value
            for key, value in mapping.items()
            if key not in known_keys
        }

        static_ipv6_prefix_length = mapping.get(
            "static_ipv6_prefix_length"
        )

        return cls(
            ip_assignment_method=coerce_str(
                mapping.get("ip_assignment_method"),
                field_name="ip_assignment_method",
                default="dhcp",
            ),
            static_ipv4_address=_optional_str(
                mapping.get("static_ipv4_address")
            ),
            static_ipv4_netmask=_optional_str(
                mapping.get("static_ipv4_netmask")
            ),
            static_ipv4_gateway=_optional_str(
                mapping.get("static_ipv4_gateway")
            ),
            static_ipv6_address=_optional_str(
                mapping.get("static_ipv6_address")
            ),
            static_ipv6_prefix_length=(
                coerce_int(
                    static_ipv6_prefix_length,
                    field_name="static_ipv6_prefix_length",
                    default=0,
                )
                if static_ipv6_prefix_length is not None
                else None
            ),
            static_ipv6_gateway=_optional_str(
                mapping.get("static_ipv6_gateway")
            ),
            dns_servers=coerce_str_list(
                mapping.get("dns_servers"),
                field_name="dns_servers",
            ),
            require_ethernet_link=coerce_bool(
                mapping.get("require_ethernet_link"),
                field_name="require_ethernet_link",
                default=True,
            ),
            require_gateway_reachability=coerce_bool(
                mapping.get("require_gateway_reachability"),
                field_name="require_gateway_reachability",
                default=True,
            ),
            require_dns_resolution=coerce_bool(
                mapping.get("require_dns_resolution"),
                field_name="require_dns_resolution",
                default=True,
            ),
            connectivity_check_timeout_seconds=coerce_int(
                mapping.get("connectivity_check_timeout_seconds"),
                field_name="connectivity_check_timeout_seconds",
                default=30,
            ),
            connectivity_check_retry_count=coerce_int(
                mapping.get("connectivity_check_retry_count"),
                field_name="connectivity_check_retry_count",
                default=3,
            ),
            extensions=extensions,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a YAML/JSON-serializable dictionary representation."""

        return {
            "schema_version": self.SCHEMA_VERSION,
            "ip_assignment_method": self.ip_assignment_method,
            "static_ipv4_address": self.static_ipv4_address,
            "static_ipv4_netmask": self.static_ipv4_netmask,
            "static_ipv4_gateway": self.static_ipv4_gateway,
            "static_ipv6_address": self.static_ipv6_address,
            "static_ipv6_prefix_length": (
                self.static_ipv6_prefix_length
            ),
            "static_ipv6_gateway": self.static_ipv6_gateway,
            "dns_servers": list(self.dns_servers),
            "require_ethernet_link": self.require_ethernet_link,
            "require_gateway_reachability": (
                self.require_gateway_reachability
            ),
            "require_dns_resolution": self.require_dns_resolution,
            "connectivity_check_timeout_seconds": (
                self.connectivity_check_timeout_seconds
            ),
            "connectivity_check_retry_count": (
                self.connectivity_check_retry_count
            ),
            **self.extensions,
        }


def _optional_str(value: Any) -> Optional[str]:
    """Return a stripped string, or ``None`` when the value is absent."""

    if value is None:
        return None

    text = str(value).strip()

    return text or None


__all__ = ["IP_ASSIGNMENT_METHODS", "NetworkConfig"]
