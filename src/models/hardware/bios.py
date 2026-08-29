"""
Project Aquila
=============

BIOS/Firmware Inspection Model

Data structure populated by ``hardware.bios`` (REQ-INS-014 through
REQ-INS-019, REQ-INS-022, REQ-INS-023) and consumed by the Inspection
Engine's hardware report.

Firmware identity (manufacturer, model, serial number, BIOS
vendor/version, UEFI vs. Legacy mode) and TPM state are already fully
modeled by ``bios.models.FirmwareInformation`` and
``bios.models.TPMState`` -- the ``bios`` subsystem's own detection
code (``bios.detection.BIOSDetection``, run during Inspection to
select a ``BIOSProvider``) already builds these. This model wraps
those two directly rather than re-deriving a second, competing
firmware-identity representation (see this package's ``__init__``
docstring), and adds only what Inspection needs that firmware
identity alone does not cover: Secure Boot state (REQ-INS-015), lid
switch presence (REQ-INS-022), and which BIOS management interface,
if any, was detected (REQ-INS-023).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping, cast

from bios.models import FirmwareInformation, TPMState

from . import HardwareModelError, JSONValue, coerce_bool, make_json_compatible


@dataclass(slots=True)
class BIOSInspectionInfo:
    """
    Firmware/BIOS facts collected during hardware inspection.

    ``secure_boot_enabled`` is ``None`` when Secure Boot status could
    not be determined at all (for example, on Legacy/CSM boot, where
    Secure Boot is not applicable) -- distinct from ``False``, which
    means Secure Boot support was confirmed present but currently
    switched off.
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    firmware: FirmwareInformation = field(default_factory=FirmwareInformation)
    tpm: TPMState = field(default_factory=TPMState)

    secure_boot_enabled: bool | None = None
    lid_switch_present: bool | None = None
    management_interface_detected: str = ""

    def __post_init__(self) -> None:
        self.management_interface_detected = (
            self.management_interface_detected.strip()
        )

    def to_dict(self) -> dict[str, JSONValue]:
        # ``bios.models.TPMState`` has no ``to_dict()`` of its own (it
        # is a plain data holder, not a full model like
        # ``FirmwareInformation``/``BootDevice``), so
        # ``make_json_compatible()`` can't serialize it structurally --
        # it would fall through to that helper's final "unsupported
        # object" fallback and stringify the whole object, which is
        # not JSON round-trippable. Serialized by hand here instead,
        # mirroring the exact field set ``from_dict()`` below reads
        # back.
        tpm_dict: dict[str, JSONValue] = {
            "present": self.tpm.present,
            "enabled": self.tpm.enabled,
            "activated": self.tpm.activated,
            "owned": self.tpm.owned,
            "spec_version": self.tpm.spec_version,
            "version": self.tpm.version,
            "manufacturer": self.tpm.manufacturer,
            "metadata": make_json_compatible(self.tpm.metadata),
        }

        result: dict[str, JSONValue] = {
            "schema_version": self.SCHEMA_VERSION,
            "firmware": self.firmware.to_dict(),
            "tpm": tpm_dict,
            "secure_boot_enabled": self.secure_boot_enabled,
            "lid_switch_present": self.lid_switch_present,
            "management_interface_detected": self.management_interface_detected,
        }
        return result

    def to_json(self, *, indent: int | None = None) -> str:
        from . import to_json as _to_json

        return _to_json(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BIOSInspectionInfo":
        firmware_raw = data.get("firmware", {})
        if not isinstance(firmware_raw, Mapping):
            raise HardwareModelError(
                "BIOSInspectionInfo.firmware must be a mapping."
            )
        firmware_raw = cast(Mapping[str, Any], firmware_raw)

        tpm_raw = data.get("tpm", {})
        if not isinstance(tpm_raw, Mapping):
            raise HardwareModelError("BIOSInspectionInfo.tpm must be a mapping.")
        tpm_raw = cast(Mapping[str, Any], tpm_raw)

        secure_boot = data.get("secure_boot_enabled")
        lid_switch = data.get("lid_switch_present")

        return cls(
            firmware=FirmwareInformation.from_dict(firmware_raw),
            tpm=TPMState(
                present=coerce_bool(
                    tpm_raw.get("present", False), field_name="tpm.present"
                ),
                enabled=coerce_bool(
                    tpm_raw.get("enabled", False), field_name="tpm.enabled"
                ),
                activated=coerce_bool(
                    tpm_raw.get("activated", False), field_name="tpm.activated"
                ),
                owned=coerce_bool(
                    tpm_raw.get("owned", False), field_name="tpm.owned"
                ),
                spec_version=str(tpm_raw.get("spec_version") or ""),
                version=str(tpm_raw.get("version") or ""),
                manufacturer=(
                    str(tpm_raw["manufacturer"])
                    if tpm_raw.get("manufacturer") is not None
                    else None
                ),
                metadata=dict(tpm_raw.get("metadata") or {}),
            ),
            secure_boot_enabled=(
                coerce_bool(secure_boot, field_name="secure_boot_enabled")
                if secure_boot is not None
                else None
            ),
            lid_switch_present=(
                coerce_bool(lid_switch, field_name="lid_switch_present")
                if lid_switch is not None
                else None
            ),
            management_interface_detected=str(
                data.get("management_interface_detected") or ""
            ),
        )


__all__ = ["BIOSInspectionInfo"]
