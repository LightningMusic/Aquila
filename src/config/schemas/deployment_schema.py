"""
Project Aquila
=============

Deployment Configuration Schema

Defines the validated, typed structure of ``configs/deployment.yaml``:
deployment-workflow policy, the Preparation Engine's confirmation and
sanitization defaults, the minimum hardware Provisioning will accept,
and the Bootstrap Engine's power/lid/battery/power-recovery policy.

See SRS Section 9.8 (Configuration System), REQ-CONF-006,
REQ-CONF-011, REQ-CONF-012, REQ-PREP-007, REQ-PREP-014, REQ-PROV-005,
REQ-BOOT-007 through REQ-BOOT-011.

Power/lid/battery/recovery fields live here rather than in a new
schema file: REQ-CONF-011/012 explicitly ask for this policy to be
configurable, but no dedicated schema existed for it (the earlier
planning pass that produced the six ``configs/*.yaml`` files didn't
anticipate it), and ``DeploymentConfig`` is already this project's
general "deployment policy" bucket -- extending it keeps one
schema/YAML pair per concern rather than adding a seventh.

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

#: Lid-switch actions Bootstrap may configure (REQ-BOOT-008), matching
#: systemd-logind's own ``HandleLidSwitch=`` values one-for-one
#: (confirmed against systemd's logind.conf documentation). Aquila
#: nodes are servers, not laptops in active use, so "ignore" is the
#: only value REQ-BOOT-008 actually calls for ("prevent unintended
#: suspend during server operation") -- the rest are exposed for
#: completeness/future flexibility, not because Bootstrap recommends
#: them.
LID_ACTIONS: tuple[str, ...] = (
    "ignore",
    "poweroff",
    "reboot",
    "halt",
    "suspend",
    "hibernate",
    "hybrid-sleep",
    "lock",
)

#: Firmware/BMC power-restore policies Bootstrap may configure
#: (REQ-BOOT-011), matching ``ipmitool chassis policy``'s own
#: values one-for-one (confirmed against the openbmc/ipmitool
#: documentation): power on when AC power returns, restore whatever
#: state the node was in before the outage, or stay off.
POWER_RECOVERY_POLICIES: tuple[str, ...] = (
    "always-on",
    "previous",
    "always-off",
)


@dataclass(slots=True)
class DeploymentConfig:
    """
    Deployment-workflow and Preparation/Provisioning policy.
    """

    #: REQ-CONF-003: every configuration file this project ships
    #: carries a version identifier, serialized as ``schema_version``
    #: in :meth:`to_dict` -- a future incompatible field change bumps
    #: this rather than leaving readers to guess a file's shape.
    SCHEMA_VERSION: ClassVar[int] = 1

    default_workflow: str = "provisioning"

    #: REQ-CONF-008: Preparation's storage-sanitization policy
    #: (confirmation count and erasure method) is configuration, not
    #: a hardcoded constant -- see ``SANITIZATION_METHODS`` above.
    confirmation_count: int = 3
    sanitization_method: str = "full"

    require_recovery_acknowledgement: bool = True
    allow_recovery_skip: bool = True

    deployment_profile: str = "default"
    auto_reboot_after_provisioning: bool = True

    minimum_memory_gb: int = 4
    minimum_storage_gb: int = 32
    require_virtualization_support: bool = True

    #: REQ-BOOT-007/REQ-BOOT-008/GP-008: mask systemd's sleep/suspend/
    #: hibernate targets and set the lid-switch action, so a deployed
    #: node never unexpectedly suspends.
    disable_sleep_targets: bool = True
    lid_action: str = "ignore"

    #: REQ-BOOT-009/REQ-BOOT-010: battery charge-limiting thresholds
    #: (percent). ``None`` means "don't configure this" -- Bootstrap
    #: leaves the firmware/kernel default alone. When set, Bootstrap
    #: applies it only on hardware that exposes the corresponding
    #: sysfs attribute, and logs (never fails deployment over) any
    #: battery that doesn't support it (NFR-PORT-002: hardware-
    #: specific functionality degrades gracefully rather than failing
    #: deployment when the underlying capability is absent).
    battery_charge_start_threshold: int | None = None
    battery_charge_end_threshold: int | None = None

    #: REQ-BOOT-011: firmware/BMC power-restore policy. Only applied
    #: when Bootstrap detects a local IPMI/BMC interface; absent on
    #: most commodity laptops/desktops, which is expected, not a
    #: failure (REQ-BOOT-010's same non-fatal-when-unsupported
    #: principle, generalized per GP-008; also NFR-PORT-003: an
    #: unsupported firmware capability like this one must not fail
    #: deployment unless that capability were required for safe
    #: operation, which power-recovery policy is not).
    power_recovery_policy: str = "always-on"

    #: REQ-PROV: the pre-registered BCD boot-entry identifier
    #: ``provisioning.boot_handoff.PhaseTwoHandoff`` hands to
    #: ``bcdedit /bootsequence`` -- see that module's own docstring for
    #: why it never creates this entry itself. This split between a
    #: WinPE Phase One and a Proxmox-VE Phase Two referenced by this
    #: field is a significant architectural decision, documented per
    #: NFR-MAIN-005 in ``docs/ADR/ADR-0003-Two-Phase-Deployment.md``.
    #: Stamped onto this
    #: media's ``configs/deployment.yaml`` by the not-yet-built Build
    #: System at USB-build time (one identifier per media build, not
    #: per node -- GP-009's "no permanently assigned *deployment*
    #: identities" is about per-node identity, not this fixed,
    #: build-time boot-entry reference). Empty by default: rather than
    #: fabricating a placeholder value, an empty
    #: ``boot_entry_id`` is treated by ``technician_console/`` as "not
    #: yet configured for this media" and reported to the technician
    #: as a clear, actionable error before Provisioning ever reaches
    #: the boot-handoff stage -- the same "record the limitation,
    #: don't fabricate" convention ``workflows.application_manager
    #: .deployment_media_version`` already established.
    boot_entry_id: str = ""

    #: REQ-PROV-015: the Proxmox VE installer's required
    #: ``[global].fqdn``-forming domain suffix and ``[global].mailto``
    #: notification address (``provisioning.answer_file
    #: .ProvisioningProfile.domain``/``.mailto`` -- both required
    #: there, with no default, since the installer refuses an answer
    #: file missing either). These are deployment-wide policy, not a
    #: per-node fact: every node this media provisions joins the same
    #: DNS domain and reports installer notifications to the same
    #: mailbox, exactly like ``ClusterConfig.cluster_name`` is one
    #: value shared by every node that joins that cluster. Empty by
    #: default: ``technician_console/`` treats an empty
    #: ``provisioning_domain``/``provisioning_notification_email`` as
    #: "not yet configured" and refuses to start the Provisioning
    #: workflow with a clear, actionable error, rather than fabricating
    #: a placeholder domain or email address that would silently end up
    #: in a real Proxmox installation's system configuration.
    provisioning_domain: str = ""
    provisioning_notification_email: str = ""

    #: REQ-CONF-014: any top-level key ``from_dict`` doesn't recognize
    #: (written by a newer Aquila build, or hand-added by a
    #: technician) is preserved here rather than discarded, so an
    #: older build round-trips a newer configuration file without
    #: invalidating it, and ``to_dict`` writes these keys straight
    #: back out.
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

        validate_choice(
            self.lid_action,
            LID_ACTIONS,
            field_name="lid_action",
        )

        validate_choice(
            self.power_recovery_policy,
            POWER_RECOVERY_POLICIES,
            field_name="power_recovery_policy",
        )

        if self.battery_charge_start_threshold is not None:
            validate_range(
                self.battery_charge_start_threshold,
                field_name="battery_charge_start_threshold",
                minimum=0,
                maximum=99,
            )

        if self.battery_charge_end_threshold is not None:
            validate_range(
                self.battery_charge_end_threshold,
                field_name="battery_charge_end_threshold",
                minimum=1,
                maximum=100,
            )

        if (
            self.battery_charge_start_threshold is not None
            and self.battery_charge_end_threshold is not None
            and self.battery_charge_start_threshold
            >= self.battery_charge_end_threshold
        ):
            raise ConfigurationValueError(
                "'battery_charge_start_threshold' "
                f"({self.battery_charge_start_threshold}) must be < "
                "'battery_charge_end_threshold' "
                f"({self.battery_charge_end_threshold})."
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
            "disable_sleep_targets",
            "lid_action",
            "battery_charge_start_threshold",
            "battery_charge_end_threshold",
            "power_recovery_policy",
            "boot_entry_id",
            "provisioning_domain",
            "provisioning_notification_email",
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
            disable_sleep_targets=coerce_bool(
                mapping.get("disable_sleep_targets"),
                field_name="disable_sleep_targets",
                default=True,
            ),
            lid_action=coerce_str(
                mapping.get("lid_action"),
                field_name="lid_action",
                default="ignore",
            ),
            battery_charge_start_threshold=(
                coerce_int(
                    mapping.get("battery_charge_start_threshold"),
                    field_name="battery_charge_start_threshold",
                    default=0,
                )
                if mapping.get("battery_charge_start_threshold") is not None
                else None
            ),
            battery_charge_end_threshold=(
                coerce_int(
                    mapping.get("battery_charge_end_threshold"),
                    field_name="battery_charge_end_threshold",
                    default=0,
                )
                if mapping.get("battery_charge_end_threshold") is not None
                else None
            ),
            power_recovery_policy=coerce_str(
                mapping.get("power_recovery_policy"),
                field_name="power_recovery_policy",
                default="always-on",
            ),
            boot_entry_id=coerce_str(
                mapping.get("boot_entry_id"),
                field_name="boot_entry_id",
                default="",
            ),
            provisioning_domain=coerce_str(
                mapping.get("provisioning_domain"),
                field_name="provisioning_domain",
                default="",
            ),
            provisioning_notification_email=coerce_str(
                mapping.get("provisioning_notification_email"),
                field_name="provisioning_notification_email",
                default="",
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
            "disable_sleep_targets": self.disable_sleep_targets,
            "lid_action": self.lid_action,
            "battery_charge_start_threshold": (
                self.battery_charge_start_threshold
            ),
            "battery_charge_end_threshold": (
                self.battery_charge_end_threshold
            ),
            "power_recovery_policy": self.power_recovery_policy,
            "boot_entry_id": self.boot_entry_id,
            "provisioning_domain": self.provisioning_domain,
            "provisioning_notification_email": (
                self.provisioning_notification_email
            ),
            **self.extensions,
        }


__all__ = [
    "DEPLOYMENT_WORKFLOWS",
    "LID_ACTIONS",
    "MINIMUM_CONFIRMATION_COUNT",
    "POWER_RECOVERY_POLICIES",
    "SANITIZATION_METHODS",
    "DeploymentConfig",
]
