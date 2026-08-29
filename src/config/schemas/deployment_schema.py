"""
Project Aquila
=============

Deployment Configuration Schema

Defines the validated, typed structure of ``configs/deployment.yaml``:
deployment-workflow policy, the Preparation Engine's confirmation and
sanitization defaults, and the minimum hardware Provisioning will
accept.

See SRS Section 9.8 (Configuration System), REQ-CONF-006,
REQ-PREP-007, REQ-PREP-014, and REQ-PROV-005.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping

from common.enums import SanitizationMethod
from common.exceptions.configuration import ConfigurationValueError
from config.validators.schema_validator import (
    coerce_bool,
    coerce_int,
    coerce_str,
    require_mapping,
    validate_choice,
    validate_range,
)

# ---------------------------------------------------------------------------
# Allowed values
# ---------------------------------------------------------------------------

#: Workflow names, matching SRS Section 9.5 (Workflow A / Workflow B).
DEPLOYMENT_WORKFLOWS: tuple[str, ...] = ("retirement", "provisioning")

#: Sanitization methods, matching REQ-PREP-014. Derived directly from
#: ``common.enums.SanitizationMethod`` -- the enum is the single
#: source of truth for which methods exist; this is only its
#: lowercase, YAML-friendly string form (``ATA_SECURE_ERASE`` ->
#: ``"ata_secure_erase"``), so the two can never drift out of sync
#: the way they previously did (the enum once had 3 members while
#: this list had 4).
SANITIZATION_METHODS: tuple[str, ...] = tuple(
    method.name.lower() for method in SanitizationMethod
)

#: The minimum confirmation count REQ-PREP-007 permits Aquila to be
#: configured down to. The requirement's own *default* is 3; this
#: floor of 1 keeps "configurable" from being read as "disableable" --
#: an operator can shorten the confirmation sequence but can never
#: configure Preparation to require zero operator confirmations.
MINIMUM_CONFIRMATION_COUNT: int = 1


@dataclass(slots=True)
class DeploymentConfig:
    """
    Deployment-workflow and Preparation/Provisioning policy.
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    default_workflow: str = "provisioning"

    confirmation_count: int = 3
    sanitization_method: str = "full"

    require_recovery_acknowledgement: bool = True
    allow_recovery_skip: bool = True

    deployment_profile: str = "default"
    auto_reboot_after_provisioning: bool = True

    minimum_memory_gb: int = 4
    minimum_storage_gb: int = 32
    require_virtualization_support: bool = True

    extensions: dict[str, Any] = field(default_factory=lambda: {})

    def __post_init__(self) -> None:
        """Validate deployment policy invariants."""

        validate_choice(
            self.default_workflow,
            DEPLOYMENT_WORKFLOWS,
            field_name="default_workflow",
        )

        validate_choice(
            self.sanitization_method,
            SANITIZATION_METHODS,
            field_name="sanitization_method",
        )

        if self.confirmation_count < MINIMUM_CONFIRMATION_COUNT:
            raise ConfigurationValueError(
                "'confirmation_count' must be >= "
                f"{MINIMUM_CONFIRMATION_COUNT} (SRS REQ-PREP-007 "
                "requires explicit operator confirmation before any "
                "irreversible operation)."
            )

        validate_range(
            self.minimum_memory_gb,
            field_name="minimum_memory_gb",
            minimum=0,
        )

        validate_range(
            self.minimum_storage_gb,
            field_name="minimum_storage_gb",
            minimum=0,
        )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DeploymentConfig:
        """
        Construct a validated ``DeploymentConfig`` from a raw mapping.

        Unknown top-level keys are preserved in ``extensions`` so an
        older Aquila build can round-trip a configuration file written
        by a newer one without silently discarding it.
        """

        mapping = require_mapping(data, section="deployment")

        known_keys = {
            "schema_version",
            "default_workflow",
            "confirmation_count",
            "sanitization_method",
            "require_recovery_acknowledgement",
            "allow_recovery_skip",
            "deployment_profile",
            "auto_reboot_after_provisioning",
            "minimum_memory_gb",
            "minimum_storage_gb",
            "require_virtualization_support",
        }

        extensions = {
            key: value
            for key, value in mapping.items()
            if key not in known_keys
        }

        return cls(
            default_workflow=coerce_str(
                mapping.get("default_workflow"),
                field_name="default_workflow",
                default="provisioning",
            ),
            confirmation_count=coerce_int(
                mapping.get("confirmation_count"),
                field_name="confirmation_count",
                default=3,
            ),
            sanitization_method=coerce_str(
                mapping.get("sanitization_method"),
                field_name="sanitization_method",
                default="full",
            ),
            require_recovery_acknowledgement=coerce_bool(
                mapping.get("require_recovery_acknowledgement"),
                field_name="require_recovery_acknowledgement",
                default=True,
            ),
            allow_recovery_skip=coerce_bool(
                mapping.get("allow_recovery_skip"),
                field_name="allow_recovery_skip",
                default=True,
            ),
            deployment_profile=coerce_str(
                mapping.get("deployment_profile"),
                field_name="deployment_profile",
                default="default",
            ),
            auto_reboot_after_provisioning=coerce_bool(
                mapping.get("auto_reboot_after_provisioning"),
                field_name="auto_reboot_after_provisioning",
                default=True,
            ),
            minimum_memory_gb=coerce_int(
                mapping.get("minimum_memory_gb"),
                field_name="minimum_memory_gb",
                default=4,
            ),
            minimum_storage_gb=coerce_int(
                mapping.get("minimum_storage_gb"),
                field_name="minimum_storage_gb",
                default=32,
            ),
            require_virtualization_support=coerce_bool(
                mapping.get("require_virtualization_support"),
                field_name="require_virtualization_support",
                default=True,
            ),
            extensions=extensions,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a YAML/JSON-serializable dictionary representation."""

        return {
            "schema_version": self.SCHEMA_VERSION,
            "default_workflow": self.default_workflow,
            "confirmation_count": self.confirmation_count,
            "sanitization_method": self.sanitization_method,
            "require_recovery_acknowledgement": (
                self.require_recovery_acknowledgement
            ),
            "allow_recovery_skip": self.allow_recovery_skip,
            "deployment_profile": self.deployment_profile,
            "auto_reboot_after_provisioning": (
                self.auto_reboot_after_provisioning
            ),
            "minimum_memory_gb": self.minimum_memory_gb,
            "minimum_storage_gb": self.minimum_storage_gb,
            "require_virtualization_support": (
                self.require_virtualization_support
            ),
            **self.extensions,
        }


__all__ = [
    "DEPLOYMENT_WORKFLOWS",
    "MINIMUM_CONFIRMATION_COUNT",
    "SANITIZATION_METHODS",
    "DeploymentConfig",
]
