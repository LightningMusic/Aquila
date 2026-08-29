"""
Project Aquila
=============

CPU Inventory Model

Data structure populated by ``hardware.cpu`` (REQ-INS-001, REQ-INS-002,
REQ-INS-012, REQ-INS-013) and consumed by the Inspection Engine's
hardware report and by ``deployment.DeploymentConfig`` /
REQ-PROV-005's minimum-hardware validation.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Mapping

from . import (
    HardwareModelError,
    JSONValue,
    coerce_bool,
    make_json_compatible,
    optional_string,
)
from . import to_json as _to_json


class CPUArchitecture(str, Enum):
    """Normalized processor instruction-set architecture."""

    X86 = "x86"
    X86_64 = "x86_64"
    ARM = "arm"
    ARM64 = "arm64"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, value: str | None) -> "CPUArchitecture":
        """
        Convert a raw architecture string into a normalized value.

        Handles the different spellings operating systems and WMI use
        for the same architecture (``platform.machine()``'s
        ``AMD64``/``x86_64``, WMI ``Win32_Processor.Architecture``'s
        numeric codes already translated by the caller, etc.).
        """

        if not value:
            return cls.UNKNOWN

        normalized = value.strip().lower().replace("-", "_")

        aliases: dict[str, CPUArchitecture] = {
            "x86": cls.X86,
            "i386": cls.X86,
            "i686": cls.X86,
            "32_bit": cls.X86,
            "x86_64": cls.X86_64,
            "amd64": cls.X86_64,
            "x64": cls.X86_64,
            "64_bit": cls.X86_64,
            "arm": cls.ARM,
            "arm64": cls.ARM64,
            "aarch64": cls.ARM64,
            "unknown": cls.UNKNOWN,
        }

        return aliases.get(normalized, cls.UNKNOWN)


@dataclass(slots=True)
class CPUInfo:
    """
    Vendor-neutral processor inventory record.

    ``virtualization_supported`` (REQ-INS-012, whether the CPU itself
    is capable of hardware virtualization -- Intel VT-x / AMD-V) is
    kept distinct from ``virtualization_enabled`` (REQ-INS-013,
    whether that capability is currently switched on in firmware) --
    a CPU can support virtualization while it is disabled in the
    BIOS, and REQ-PROV-005 needs to tell the two apart to give an
    accurate provisioning-failure reason.
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    manufacturer: str = ""
    model_name: str = ""
    architecture: CPUArchitecture = CPUArchitecture.UNKNOWN

    socket_count: int = 1
    physical_cores: int = 0
    logical_processors: int = 0

    base_clock_mhz: float | None = None
    max_clock_mhz: float | None = None

    l2_cache_kb: int | None = None
    l3_cache_kb: int | None = None

    virtualization_supported: bool = False
    virtualization_enabled: bool = False

    processor_id: str = ""
    family: str = ""
    model: str = ""
    stepping: str = ""

    extensions: dict[str, Any] = field(default_factory=lambda: {})

    def __post_init__(self) -> None:
        """Normalize and validate CPU inventory data."""

        if isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            self.architecture, str
        ):
            self.architecture = CPUArchitecture.from_string(self.architecture)

        self.manufacturer = self.manufacturer.strip()
        self.model_name = self.model_name.strip()
        self.processor_id = self.processor_id.strip()
        self.family = self.family.strip()
        self.model = self.model.strip()
        self.stepping = self.stepping.strip()

        for count_field in ("socket_count", "physical_cores", "logical_processors"):
            if getattr(self, count_field) < 0:
                raise HardwareModelError(
                    f"CPUInfo.{count_field} must not be negative."
                )

        if self.base_clock_mhz is not None and self.base_clock_mhz < 0:
            raise HardwareModelError(
                "CPUInfo.base_clock_mhz must not be negative."
            )

        if self.max_clock_mhz is not None and self.max_clock_mhz < 0:
            raise HardwareModelError(
                "CPUInfo.max_clock_mhz must not be negative."
            )

        if not self.virtualization_supported and self.virtualization_enabled:
            raise HardwareModelError(
                "CPUInfo.virtualization_enabled cannot be True when "
                "virtualization_supported is False."
            )

        self.extensions = dict(self.extensions)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible dictionary representation."""

        return {
            "schema_version": self.SCHEMA_VERSION,
            "manufacturer": self.manufacturer,
            "model_name": self.model_name,
            "architecture": self.architecture.value,
            "socket_count": self.socket_count,
            "physical_cores": self.physical_cores,
            "logical_processors": self.logical_processors,
            "base_clock_mhz": self.base_clock_mhz,
            "max_clock_mhz": self.max_clock_mhz,
            "l2_cache_kb": self.l2_cache_kb,
            "l3_cache_kb": self.l3_cache_kb,
            "virtualization_supported": self.virtualization_supported,
            "virtualization_enabled": self.virtualization_enabled,
            "processor_id": self.processor_id,
            "family": self.family,
            "model": self.model,
            "stepping": self.stepping,
            "extensions": make_json_compatible(self.extensions),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        """Serialize this CPU inventory record to JSON."""

        return _to_json(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CPUInfo":
        """
        Construct a ``CPUInfo`` from a raw mapping.

        Unknown top-level keys are preserved in ``extensions`` so an
        older Aquila build can round-trip a record written by a newer
        one without silently discarding it.
        """

        known_keys = {
            "schema_version",
            "manufacturer",
            "model_name",
            "architecture",
            "socket_count",
            "physical_cores",
            "logical_processors",
            "base_clock_mhz",
            "max_clock_mhz",
            "l2_cache_kb",
            "l3_cache_kb",
            "virtualization_supported",
            "virtualization_enabled",
            "processor_id",
            "family",
            "model",
            "stepping",
            "extensions",
        }

        extensions = {
            key: value for key, value in data.items() if key not in known_keys
        }

        return cls(
            manufacturer=str(data.get("manufacturer") or ""),
            model_name=str(data.get("model_name") or ""),
            architecture=CPUArchitecture.from_string(
                optional_string(data.get("architecture"))
            ),
            socket_count=int(data.get("socket_count", 1)),
            physical_cores=int(data.get("physical_cores", 0)),
            logical_processors=int(data.get("logical_processors", 0)),
            base_clock_mhz=(
                float(data["base_clock_mhz"])
                if data.get("base_clock_mhz") is not None
                else None
            ),
            max_clock_mhz=(
                float(data["max_clock_mhz"])
                if data.get("max_clock_mhz") is not None
                else None
            ),
            l2_cache_kb=(
                int(data["l2_cache_kb"])
                if data.get("l2_cache_kb") is not None
                else None
            ),
            l3_cache_kb=(
                int(data["l3_cache_kb"])
                if data.get("l3_cache_kb") is not None
                else None
            ),
            virtualization_supported=coerce_bool(
                data.get("virtualization_supported", False),
                field_name="virtualization_supported",
            ),
            virtualization_enabled=coerce_bool(
                data.get("virtualization_enabled", False),
                field_name="virtualization_enabled",
            ),
            processor_id=str(data.get("processor_id") or ""),
            family=str(data.get("family") or ""),
            model=str(data.get("model") or ""),
            stepping=str(data.get("stepping") or ""),
            extensions=extensions,
        )


__all__ = ["CPUArchitecture", "CPUInfo"]
