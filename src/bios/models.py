"""Shared data models for the Project Aquila BIOS subsystem.

This module contains vendor-neutral data structures shared by:

* BIOSProvider
* DefaultProvider
* Vendor-specific BIOS providers
* BIOS reporting and inventory components
* Configuration and logging components

Provider interfaces should return these models rather than vendor-specific
objects. This keeps the rest of Aquila independent from Dell, HP, Lenovo, or
other firmware-management implementations.

The models intentionally include schema versions and extension dictionaries
so new fields can be introduced without immediately breaking existing
providers, reports, or stored inventory records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from json import dumps
from typing import Any, ClassVar, Mapping, TypeAlias, cast
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class BIOSModelError(ValueError):
    """Base exception raised when a BIOS model contains invalid data."""


class BIOSVendor(str, Enum):
    """Known system vendors supported or detectable by Aquila.

    Vendor-specific providers should return one of these values from
    ``BIOSProvider.vendor()``.

    ``UNKNOWN`` should be used when the system vendor cannot be determined.
    ``GENERIC`` identifies a provider that is intentionally vendor-neutral.
    """

    GENERIC = "generic"
    DELL = "dell"
    HP = "hp"
    LENOVO = "lenovo"
    ACER = "acer"
    ASUS = "asus"
    MICROSOFT = "microsoft"
    PANASONIC = "panasonic"
    SAMSUNG = "samsung"
    TOSHIBA = "toshiba"
    FUJITSU = "fujitsu"
    FRAMEWORK = "framework"
    INTEL = "intel"
    AMD = "amd"
    SUPERMICRO = "supermicro"
    GIGABYTE = "gigabyte"
    MSI = "msi"
    ASROCK = "asrock"
    APPLE = "apple"
    VMWARE = "vmware"
    QEMU = "qemu"
    XEN = "xen"
    HYPER_V = "hyper-v"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, value: str | None) -> BIOSVendor:
        """Convert a vendor name into a normalized ``BIOSVendor``.

        Manufacturer strings frequently differ between SMBIOS, operating
        systems, and vendor management tools. This method handles common
        aliases while preserving a stable set of values for the rest of
        Aquila.

        Unknown input is mapped to ``BIOSVendor.UNKNOWN`` rather than raising
        an exception.

        Args:
            value: Raw manufacturer or vendor name.

        Returns:
            The normalized BIOS vendor.
        """
        if not value:
            return cls.UNKNOWN

        normalized = " ".join(value.strip().lower().split())

        aliases: dict[str, BIOSVendor] = {
            "generic": cls.GENERIC,
            "dell": cls.DELL,
            "dell inc.": cls.DELL,
            "dell computer corporation": cls.DELL,
            "hewlett-packard": cls.HP,
            "hewlett packard": cls.HP,
            "hewlett packard enterprise": cls.HP,
            "hp": cls.HP,
            "hp inc.": cls.HP,
            "hpe": cls.HP,
            "lenovo": cls.LENOVO,
            "ibm": cls.LENOVO,
            "acer": cls.ACER,
            "acer incorporated": cls.ACER,
            "asustek computer inc.": cls.ASUS,
            "asustek computer inc": cls.ASUS,
            "asus": cls.ASUS,
            "microsoft": cls.MICROSOFT,
            "microsoft corporation": cls.MICROSOFT,
            "panasonic": cls.PANASONIC,
            "panasonic corporation": cls.PANASONIC,
            "samsung": cls.SAMSUNG,
            "samsung electronics": cls.SAMSUNG,
            "toshiba": cls.TOSHIBA,
            "dynabook": cls.TOSHIBA,
            "fujitsu": cls.FUJITSU,
            "framework": cls.FRAMEWORK,
            "framework computer inc.": cls.FRAMEWORK,
            "intel": cls.INTEL,
            "intel corporation": cls.INTEL,
            "amd": cls.AMD,
            "advanced micro devices, inc.": cls.AMD,
            "supermicro": cls.SUPERMICRO,
            "super micro computer, inc.": cls.SUPERMICRO,
            "gigabyte": cls.GIGABYTE,
            "gigabyte technology co., ltd.": cls.GIGABYTE,
            "micro-star international co., ltd.": cls.MSI,
            "msi": cls.MSI,
            "asrock": cls.ASROCK,
            "apple": cls.APPLE,
            "apple inc.": cls.APPLE,
            "vmware": cls.VMWARE,
            "vmware, inc.": cls.VMWARE,
            "qemu": cls.QEMU,
            "xen": cls.XEN,
            "microsoft hyper-v": cls.HYPER_V,
            "hyper-v": cls.HYPER_V,
            "unknown": cls.UNKNOWN,
        }

        if normalized in aliases:
            return aliases[normalized]

        # Some SMBIOS strings include extra product or organization text.
        if "dell" in normalized:
            return cls.DELL
        if normalized.startswith(("hp ", "hewlett-packard", "hewlett packard")):
            return cls.HP
        if "lenovo" in normalized:
            return cls.LENOVO
        if "supermicro" in normalized or "super micro" in normalized:
            return cls.SUPERMICRO
        if "vmware" in normalized:
            return cls.VMWARE
        if "qemu" in normalized:
            return cls.QEMU
        if "hyper-v" in normalized:
            return cls.HYPER_V

        return cls.UNKNOWN


class BIOSMode(str, Enum):
    """Firmware mode used to boot the operating system."""

    UEFI = "uefi"
    LEGACY = "legacy"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, value: str | None) -> BIOSMode:
        """Convert a raw firmware-mode value into a normalized mode."""
        if not value:
            return cls.UNKNOWN

        normalized = value.strip().lower().replace("_", "-")

        aliases: dict[str, BIOSMode] = {
            "uefi": cls.UEFI,
            "efi": cls.UEFI,
            "native-uefi": cls.UEFI,
            "legacy": cls.LEGACY,
            "bios": cls.LEGACY,
            "legacy-bios": cls.LEGACY,
            "csm": cls.LEGACY,
            "hybrid": cls.HYBRID,
            "uefi-with-csm": cls.HYBRID,
            "uefi+csm": cls.HYBRID,
            "unknown": cls.UNKNOWN,
        }

        return aliases.get(normalized, cls.UNKNOWN)


class BootDeviceType(str, Enum):
    """General category of a firmware boot device."""

    HARD_DRIVE = "hard-drive"
    SOLID_STATE_DRIVE = "solid-state-drive"
    NVME = "nvme"
    USB = "usb"
    OPTICAL = "optical"
    NETWORK = "network"
    PXE = "pxe"
    UEFI_APPLICATION = "uefi-application"
    REMOVABLE_MEDIA = "removable-media"
    FLOPPY = "floppy"
    VIRTUAL_MEDIA = "virtual-media"
    OTHER = "other"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, value: str | None) -> BootDeviceType:
        """Convert a raw boot-device type into a normalized type."""
        if not value:
            return cls.UNKNOWN

        normalized = value.strip().lower().replace("_", "-").replace(" ", "-")

        aliases: dict[str, BootDeviceType] = {
            "hdd": cls.HARD_DRIVE,
            "hard-disk": cls.HARD_DRIVE,
            "hard-drive": cls.HARD_DRIVE,
            "ssd": cls.SOLID_STATE_DRIVE,
            "solid-state-drive": cls.SOLID_STATE_DRIVE,
            "nvme": cls.NVME,
            "nvme-ssd": cls.NVME,
            "usb": cls.USB,
            "usb-storage": cls.USB,
            "cd": cls.OPTICAL,
            "cdrom": cls.OPTICAL,
            "cd-rom": cls.OPTICAL,
            "dvd": cls.OPTICAL,
            "optical": cls.OPTICAL,
            "network": cls.NETWORK,
            "network-boot": cls.NETWORK,
            "pxe": cls.PXE,
            "uefi": cls.UEFI_APPLICATION,
            "uefi-application": cls.UEFI_APPLICATION,
            "removable": cls.REMOVABLE_MEDIA,
            "removable-media": cls.REMOVABLE_MEDIA,
            "floppy": cls.FLOPPY,
            "virtual-media": cls.VIRTUAL_MEDIA,
            "virtual-cd": cls.VIRTUAL_MEDIA,
            "other": cls.OTHER,
            "unknown": cls.UNKNOWN,
        }

        return aliases.get(normalized, cls.UNKNOWN)

@dataclass(frozen=True, slots=True)
class TPMState:
    """Normalized Trusted Platform Module state."""

    present: bool = False
    enabled: bool = False
    activated: bool = False
    owned: bool = False
    spec_version: str = ""
    version: str = ""
    manufacturer: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=lambda: {})


@dataclass(slots=True)
class BootDevice:
    """Vendor-neutral representation of a firmware boot device.

    Attributes:
        identifier:
            Stable identifier used by the provider when changing boot order.
            This may be a UEFI boot number, vendor setting identifier, device
            path, or another provider-defined identifier.
        name:
            Human-readable device name displayed to operators.
        device_type:
            Normalized category of the boot device.
        enabled:
            Whether the device is enabled in the firmware boot configuration.
        priority:
            Zero-based or provider-defined position in the current boot order.
            ``None`` means the priority is unknown.
        description:
            Optional additional human-readable information.
        path:
            Optional UEFI, hardware, or vendor-specific device path.
        persistent:
            Whether the entry is part of the persistent boot configuration.
            A value of ``False`` may identify a temporary one-time boot entry.
        metadata:
            Provider-specific extension data. Consumers must not require these
            keys unless they explicitly depend on a particular provider.
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    identifier: str
    name: str
    device_type: BootDeviceType = BootDeviceType.UNKNOWN
    enabled: bool = True
    priority: int | None = None
    description: str | None = None
    path: str | None = None
    persistent: bool = True
    metadata: dict[str, Any] = field(default_factory=lambda: {})

    def __post_init__(self) -> None:
        """Normalize and validate boot-device data."""
        self.identifier = self.identifier.strip()
        self.name = self.name.strip()

        if not self.identifier:
            raise BIOSModelError("BootDevice.identifier must not be empty.")

        if not self.name:
            raise BIOSModelError("BootDevice.name must not be empty.")

        # Statically redundant given this field's declared ``BootDeviceType``
        # type, but genuinely meaningful at runtime: callers deserializing
        # a boot device from a deployment profile or an older serialized
        # record commonly construct this dataclass directly with a raw
        # string rather than going through ``from_dict()``.
        if isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            self.device_type, str
        ):
            self.device_type = BootDeviceType.from_string(self.device_type)

        if self.priority is not None and self.priority < 0:
            raise BIOSModelError("BootDevice.priority must not be negative.")

        if self.description is not None:
            self.description = self.description.strip() or None

        if self.path is not None:
            self.path = self.path.strip() or None

        # Copy caller-owned mappings so later changes to the original mapping
        # do not unexpectedly modify this model.
        self.metadata = dict(self.metadata)

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible dictionary representation."""
        return {
            "schema_version": self.SCHEMA_VERSION,
            "identifier": self.identifier,
            "name": self.name,
            "device_type": self.device_type.value,
            "enabled": self.enabled,
            "priority": self.priority,
            "description": self.description,
            "path": self.path,
            "persistent": self.persistent,
            "metadata": _make_json_compatible(self.metadata),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        """Serialize this boot device to JSON."""
        return dumps(
            self.to_dict(),
            indent=indent,
            sort_keys=True,
            ensure_ascii=False,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BootDevice:
        """Construct a boot device from a mapping.

        Unknown keys are ignored to permit newer serialized model versions to
        be read by older Aquila components.
        """
        metadata = data.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise BIOSModelError("BootDevice.metadata must be a mapping.")
        metadata = cast(Mapping[str, Any], metadata)

        priority = data.get("priority")
        if priority is not None and (
            not isinstance(priority, int) or isinstance(priority, bool)
        ):
            raise BIOSModelError(
                "BootDevice.priority must be an integer or None."
            )

        return cls(
            identifier=str(data.get("identifier", "")),
            name=str(data.get("name", "")),
            device_type=BootDeviceType.from_string(
                _optional_string(data.get("device_type"))
            ),
            enabled=_coerce_bool(data.get("enabled", True), field_name="enabled"),
            priority=priority,
            description=_optional_string(data.get("description")),
            path=_optional_string(data.get("path")),
            persistent=_coerce_bool(
                data.get("persistent", True),
                field_name="persistent",
            ),
            metadata=dict(metadata),
        )


@dataclass(slots=True)
class FirmwareInformation:
    """Vendor-neutral firmware and SMBIOS system information.

    Empty strings and ``None`` values are permitted because firmware fields
    are not guaranteed to be present on all supported hardware.

    ``extensions`` and ``raw_data`` provide controlled escape hatches for
    future information and provider-specific values:

    * ``extensions`` contains normalized data not yet represented by a formal
      model field.
    * ``raw_data`` contains unmodified or minimally processed provider output.

    Core Aquila logic should use formal model fields whenever available.
    Provider-specific data should not silently replace those fields.
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    vendor: BIOSVendor = BIOSVendor.UNKNOWN
    mode: BIOSMode = BIOSMode.UNKNOWN
    firmware_interface: str = ""

    manufacturer: str = ""
    product_name: str = ""
    model: str = ""
    serial_number: str = ""
    system_uuid: str = ""
    sku: str = ""

    bios_vendor: str = ""
    bios_version: str = ""
    bios_release_date: date | None = None
    embedded_controller_version: str = ""

    collected_at: datetime | None = None
    extensions: dict[str, Any] = field(default_factory=lambda: {})
    raw_data: dict[str, Any] = field(default_factory=lambda: {})

    def __post_init__(self) -> None:
        """Normalize and validate firmware information."""
        # Both checks are statically redundant given this dataclass's
        # declared ``BIOSVendor``/``BIOSMode`` field types, but genuinely
        # meaningful at runtime for the same reason as ``BootDevice``'s
        # ``device_type`` normalization above: direct construction with a
        # raw string is common when this model is built from deserialized
        # or externally-sourced data.
        if isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            self.vendor, str
        ):
            self.vendor = BIOSVendor.from_string(self.vendor)

        if isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            self.mode, str
        ):
            self.mode = BIOSMode.from_string(self.mode)

        self.firmware_interface = self.firmware_interface.strip()
        self.manufacturer = self.manufacturer.strip()
        self.product_name = self.product_name.strip()
        self.model = self.model.strip()
        self.serial_number = self.serial_number.strip()
        self.system_uuid = self.system_uuid.strip()
        self.sku = self.sku.strip()
        self.bios_vendor = self.bios_vendor.strip()
        self.bios_version = self.bios_version.strip()
        self.embedded_controller_version = (
            self.embedded_controller_version.strip()
        )

        if isinstance(self.bios_release_date, str):
            self.bios_release_date = parse_firmware_date(
                self.bios_release_date
            )

        if isinstance(self.collected_at, str):
            self.collected_at = _parse_datetime(self.collected_at)

        if (
            self.collected_at is not None
            and self.collected_at.tzinfo is None
        ):
            # Naive datetimes are accepted because some deployment
            # environments may not yet have reliable timezone configuration.
            # Reports should preserve that fact rather than assuming UTC.
            pass

        self.extensions = dict(self.extensions)
        self.raw_data = dict(self.raw_data)

    def to_dict(
        self,
        *,
        include_raw_data: bool = True,
    ) -> dict[str, JSONValue]:
        """Return a JSON-compatible dictionary representation.

        Args:
            include_raw_data:
                Include provider-specific raw data. Set this to ``False`` for
                concise inventory records or reports where raw provider output
                is unnecessary.

        Returns:
            A JSON-compatible mapping.
        """
        result: dict[str, JSONValue] = {
            "schema_version": self.SCHEMA_VERSION,
            "vendor": self.vendor.value,
            "mode": self.mode.value,
            "firmware_interface": self.firmware_interface,
            "manufacturer": self.manufacturer,
            "product_name": self.product_name,
            "model": self.model,
            "serial_number": self.serial_number,
            "system_uuid": self.system_uuid,
            "sku": self.sku,
            "bios_vendor": self.bios_vendor,
            "bios_version": self.bios_version,
            "bios_release_date": (
                self.bios_release_date.isoformat()
                if self.bios_release_date is not None
                else None
            ),
            "embedded_controller_version": (
                self.embedded_controller_version
            ),
            "collected_at": (
                self.collected_at.isoformat()
                if self.collected_at is not None
                else None
            ),
            "extensions": _make_json_compatible(self.extensions),
        }

        if include_raw_data:
            result["raw_data"] = _make_json_compatible(self.raw_data)

        return result

    def to_json(
        self,
        *,
        include_raw_data: bool = True,
        indent: int | None = None,
    ) -> str:
        """Serialize this firmware information to JSON."""
        return dumps(
            self.to_dict(include_raw_data=include_raw_data),
            indent=indent,
            sort_keys=True,
            ensure_ascii=False,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FirmwareInformation:
        """Construct firmware information from a mapping.

        Unknown top-level keys are preserved in ``extensions``. This allows
        older Aquila code to retain information written by a newer model
        version instead of silently discarding it.
        """
        extensions_value = data.get("extensions", {})
        raw_data_value = data.get("raw_data", {})

        if not isinstance(extensions_value, Mapping):
            raise BIOSModelError(
                "FirmwareInformation.extensions must be a mapping."
            )
        extensions_value = cast(Mapping[str, Any], extensions_value)

        if not isinstance(raw_data_value, Mapping):
            raise BIOSModelError(
                "FirmwareInformation.raw_data must be a mapping."
            )
        raw_data_value = cast(Mapping[str, Any], raw_data_value)

        known_keys = {
            "schema_version",
            "vendor",
            "mode",
            "firmware_interface",
            "manufacturer",
            "product_name",
            "model",
            "serial_number",
            "system_uuid",
            "sku",
            "bios_vendor",
            "bios_version",
            "bios_release_date",
            "embedded_controller_version",
            "collected_at",
            "extensions",
            "raw_data",
        }

        extensions = dict(extensions_value)
        for key, value in data.items():
            if key not in known_keys:
                extensions.setdefault(key, value)

        release_date_value = data.get("bios_release_date")
        collected_at_value = data.get("collected_at")

        return cls(
            vendor=BIOSVendor.from_string(
                _optional_string(data.get("vendor"))
            ),
            mode=BIOSMode.from_string(
                _optional_string(data.get("mode"))
            ),
            firmware_interface=str(
                data.get("firmware_interface") or ""
            ),
            manufacturer=str(data.get("manufacturer") or ""),
            product_name=str(data.get("product_name") or ""),
            model=str(data.get("model") or ""),
            serial_number=str(data.get("serial_number") or ""),
            system_uuid=str(data.get("system_uuid") or ""),
            sku=str(data.get("sku") or ""),
            bios_vendor=str(data.get("bios_vendor") or ""),
            bios_version=str(data.get("bios_version") or ""),
            bios_release_date=(
                parse_firmware_date(release_date_value)
                if release_date_value
                else None
            ),
            embedded_controller_version=str(
                data.get("embedded_controller_version") or ""
            ),
            collected_at=(
                _parse_datetime(str(collected_at_value))
                if collected_at_value
                else None
            ),
            extensions=extensions,
            raw_data=dict(raw_data_value),
        )

    def is_complete(self) -> bool:
        """Return whether essential firmware identity fields are populated.

        This does not imply that every optional field is available. It only
        indicates that the record has enough information for normal reporting
        and inventory use.
        """
        return bool(
            self.manufacturer
            and self.model
            and self.bios_vendor
            and self.bios_version
        )


def parse_firmware_date(value: date | str) -> date:
    """Parse a firmware release date.

    Firmware and SMBIOS tools commonly return dates in several formats.
    This helper accepts the most common representations and normalizes them
    to ``datetime.date``.

    Args:
        value: Existing date object or textual date.

    Returns:
        Parsed date.

    Raises:
        BIOSModelError: If the value is empty or cannot be parsed.
    """
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    # Statically redundant given this function's declared ``date | str``
    # signature, but genuinely meaningful at runtime: firmware and SMBIOS
    # tooling (this function's own docstring) hands back loosely-typed
    # values that Python does not check against the type hint.
    if not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
        value, str
    ):
        raise BIOSModelError(
            "Firmware date must be a date or string value."
        )

    normalized = value.strip()
    if not normalized:
        raise BIOSModelError("Firmware date must not be empty.")

    formats = (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%d.%m.%Y",
        "%Y%m%d",
    )

    for date_format in formats:
        try:
            return datetime.strptime(normalized, date_format).date()
        except ValueError:
            continue

    raise BIOSModelError(
        f"Unsupported firmware date format: {value!r}."
    )


def _parse_datetime(value: str) -> datetime:
    """Parse an ISO 8601 datetime used by serialized model data."""
    normalized = value.strip()

    if not normalized:
        raise BIOSModelError("Datetime value must not be empty.")

    # Python versions differ in how they handle the ISO ``Z`` suffix.
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise BIOSModelError(
            f"Unsupported datetime format: {value!r}."
        ) from exc


def _optional_string(value: Any) -> str | None:
    """Convert a value into a string while preserving ``None``."""
    if value is None:
        return None

    return str(value)


def _coerce_bool(value: Any, *, field_name: str) -> bool:
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

    raise BIOSModelError(
        f"{field_name} must contain a valid boolean value."
    )


def _make_json_compatible(value: Any) -> JSONValue:
    """Recursively convert common Python values into JSON-safe values.

    Unsupported objects are represented by their string form. This behavior
    is intentional for provider metadata and raw firmware output, where
    preserving diagnostic information is preferable to failing report
    generation.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Enum):
        return _make_json_compatible(value.value)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, BootDevice):
        return value.to_dict()

    if isinstance(value, FirmwareInformation):
        return value.to_dict()

    if isinstance(value, Mapping):
        return {
            str(key): _make_json_compatible(item)
            for key, item in cast(Mapping[Any, Any], value).items()
        }

    if isinstance(value, (list, tuple, set, frozenset)):
        return [
            _make_json_compatible(item)
            for item in cast(
                "list[Any] | tuple[Any, ...] | set[Any] | frozenset[Any]",
                value,
            )
        ]

    return str(value)


__all__ = [
    "BIOSMode",
    "BIOSModelError",
    "BIOSVendor",
    "BootDevice",
    "BootDeviceType",
    "FirmwareInformation",
    "JSONScalar",
    "JSONValue",
    "parse_firmware_date",
]
