"""
Project Aquila
=============

Logging Configuration Schema

Defines the validated, typed structure of ``configs/logging.yaml``:
verbosity, retention, and output destinations for the Logging Engine.

See SRS Section 9.9 and REQ-LOG-001 through REQ-LOG-015.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping, Optional

from config.validators.schema_validator import (
    coerce_bool,
    coerce_int,
    coerce_str,
    require_mapping,
    validate_choice,
    validate_range,
)

#: Severity levels, matching REQ-LOG-003 and ``common.enums.LogLevel``.
LOG_LEVELS: tuple[str, ...] = (
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
)


@dataclass(slots=True)
class LoggingConfig:
    """
    Logging Engine verbosity and retention policy.
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    level: str = "INFO"

    #: Directory logs are written to. ``None`` defers to
    #: ``common.paths.LOG_DIR``, keeping the default out of this
    #: schema so the two stay in sync automatically.
    log_directory: Optional[str] = None

    max_log_size_mb: int = 10
    backup_count: int = 5

    console_output: bool = True
    file_output: bool = True

    #: Whether values under keys such as ``password``, ``token``, or
    #: ``secret`` are masked before being written to a log record.
    #: Complements REQ-SEC-010 ("The Deployment Controller shall never
    #: transmit credentials in plaintext"): this is the corresponding
    #: guarantee for what Aquila writes to its own logs.
    redact_sensitive_fields: bool = True

    extensions: dict[str, Any] = field(default_factory=lambda: {})

    def __post_init__(self) -> None:
        """Validate logging policy invariants."""

        self.level = self.level.upper()

        validate_choice(
            self.level,
            LOG_LEVELS,
            field_name="level",
        )

        validate_range(
            self.max_log_size_mb,
            field_name="max_log_size_mb",
            minimum=1,
        )

        validate_range(
            self.backup_count,
            field_name="backup_count",
            minimum=0,
        )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LoggingConfig:
        """Construct a validated ``LoggingConfig`` from a raw mapping."""

        mapping = require_mapping(data, section="logging")

        known_keys = {
            "schema_version",
            "level",
            "log_directory",
            "max_log_size_mb",
            "backup_count",
            "console_output",
            "file_output",
            "redact_sensitive_fields",
        }

        extensions = {
            key: value
            for key, value in mapping.items()
            if key not in known_keys
        }

        log_directory = mapping.get("log_directory")

        return cls(
            level=coerce_str(
                mapping.get("level"),
                field_name="level",
                default="INFO",
            ),
            log_directory=(
                coerce_str(
                    log_directory,
                    field_name="log_directory",
                )
                if log_directory is not None
                else None
            ),
            max_log_size_mb=coerce_int(
                mapping.get("max_log_size_mb"),
                field_name="max_log_size_mb",
                default=10,
            ),
            backup_count=coerce_int(
                mapping.get("backup_count"),
                field_name="backup_count",
                default=5,
            ),
            console_output=coerce_bool(
                mapping.get("console_output"),
                field_name="console_output",
                default=True,
            ),
            file_output=coerce_bool(
                mapping.get("file_output"),
                field_name="file_output",
                default=True,
            ),
            redact_sensitive_fields=coerce_bool(
                mapping.get("redact_sensitive_fields"),
                field_name="redact_sensitive_fields",
                default=True,
            ),
            extensions=extensions,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a YAML/JSON-serializable dictionary representation."""

        return {
            "schema_version": self.SCHEMA_VERSION,
            "level": self.level,
            "log_directory": self.log_directory,
            "max_log_size_mb": self.max_log_size_mb,
            "backup_count": self.backup_count,
            "console_output": self.console_output,
            "file_output": self.file_output,
            "redact_sensitive_fields": self.redact_sensitive_fields,
            **self.extensions,
        }


__all__ = ["LOG_LEVELS", "LoggingConfig"]
