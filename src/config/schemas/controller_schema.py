"""
Project Aquila
=============

Controller Configuration Schema

Defines the validated, typed structure of ``configs/controller.yaml``:
how Aquila deployment media and deployed nodes reach the Deployment
Controller.

See SRS Section 9.7 and REQ-CTRL-001 through REQ-CTRL-021, REQ-CONF-013.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping

from config.validators.schema_validator import (
    coerce_bool,
    coerce_float,
    coerce_int,
    coerce_str,
    require_mapping,
    validate_range,
)

#: Default Deployment Controller API port (HTTPS).
DEFAULT_CONTROLLER_PORT: int = 443


@dataclass(slots=True)
class ControllerConfig:
    """
    Deployment Controller connection policy.
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    host: str = ""
    port: int = DEFAULT_CONTROLLER_PORT
    use_tls: bool = True
    verify_tls_certificate: bool = True

    api_base_path: str = "/api/v1"

    connection_timeout_seconds: int = 10
    retry_count: int = 3
    retry_backoff_seconds: float = 2.0

    #: Name of the environment variable holding the node's Deployment
    #: Controller API credential. Never stored in this configuration
    #: file itself -- see REQ-SEC-008/REQ-SEC-009/REQ-SEC-010 and
    #: ``ClusterConfig.join_token_env_var`` for the matching pattern.
    authentication_token_env_var: str = "AQUILA_CONTROLLER_TOKEN"

    extensions: dict[str, Any] = field(default_factory=lambda: {})

    def __post_init__(self) -> None:
        """Validate Deployment Controller connection invariants."""

        validate_range(
            self.port,
            field_name="port",
            minimum=1,
            maximum=65535,
        )

        validate_range(
            self.connection_timeout_seconds,
            field_name="connection_timeout_seconds",
            minimum=1,
        )

        validate_range(
            self.retry_count,
            field_name="retry_count",
            minimum=0,
        )

        validate_range(
            self.retry_backoff_seconds,
            field_name="retry_backoff_seconds",
            minimum=0,
        )

        if not self.api_base_path.startswith("/"):
            self.api_base_path = f"/{self.api_base_path}"

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ControllerConfig:
        """Construct a validated ``ControllerConfig`` from a raw mapping."""

        mapping = require_mapping(data, section="controller")

        known_keys = {
            "schema_version",
            "host",
            "port",
            "use_tls",
            "verify_tls_certificate",
            "api_base_path",
            "connection_timeout_seconds",
            "retry_count",
            "retry_backoff_seconds",
            "authentication_token_env_var",
        }

        extensions = {
            key: value
            for key, value in mapping.items()
            if key not in known_keys
        }

        return cls(
            host=coerce_str(
                mapping.get("host"),
                field_name="host",
                default="",
            ),
            port=coerce_int(
                mapping.get("port"),
                field_name="port",
                default=DEFAULT_CONTROLLER_PORT,
            ),
            use_tls=coerce_bool(
                mapping.get("use_tls"),
                field_name="use_tls",
                default=True,
            ),
            verify_tls_certificate=coerce_bool(
                mapping.get("verify_tls_certificate"),
                field_name="verify_tls_certificate",
                default=True,
            ),
            api_base_path=coerce_str(
                mapping.get("api_base_path"),
                field_name="api_base_path",
                default="/api/v1",
            ),
            connection_timeout_seconds=coerce_int(
                mapping.get("connection_timeout_seconds"),
                field_name="connection_timeout_seconds",
                default=10,
            ),
            retry_count=coerce_int(
                mapping.get("retry_count"),
                field_name="retry_count",
                default=3,
            ),
            retry_backoff_seconds=coerce_float(
                mapping.get("retry_backoff_seconds"),
                field_name="retry_backoff_seconds",
                default=2.0,
            ),
            authentication_token_env_var=coerce_str(
                mapping.get("authentication_token_env_var"),
                field_name="authentication_token_env_var",
                default="AQUILA_CONTROLLER_TOKEN",
            ),
            extensions=extensions,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a YAML/JSON-serializable dictionary representation."""

        return {
            "schema_version": self.SCHEMA_VERSION,
            "host": self.host,
            "port": self.port,
            "use_tls": self.use_tls,
            "verify_tls_certificate": self.verify_tls_certificate,
            "api_base_path": self.api_base_path,
            "connection_timeout_seconds": (
                self.connection_timeout_seconds
            ),
            "retry_count": self.retry_count,
            "retry_backoff_seconds": self.retry_backoff_seconds,
            "authentication_token_env_var": (
                self.authentication_token_env_var
            ),
            **self.extensions,
        }


__all__ = ["DEFAULT_CONTROLLER_PORT", "ControllerConfig"]
