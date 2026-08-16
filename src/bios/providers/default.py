"""Default BIOS provider implementation for Project Aquila.

``DefaultProvider`` supplies safe, concrete behavior for the complete
``BIOSProvider`` contract. Vendor-specific providers should inherit from this
class and override only the operations their hardware or tooling supports.

Default behavior follows these rules:

* Capability checks return ``False`` unless support is known.
* Unsupported state queries return safe empty values.
* Unsupported mutating operations log a warning and return ``False``.
* Reporting and serialization always return valid non-sensitive data.
* Cleanup operations are idempotent.
* BIOS passwords and other secrets are never stored or logged.
* Generic Linux firmware identity is collected from sysfs when available.

The default provider is also the generic fallback provider. Vendor providers
must override ``detect()`` when they should only match specific hardware.
"""

from __future__ import annotations

import json
import logging
import platform
from copy import deepcopy
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final
from collections.abc import Sequence

from ..models import (
    BIOSMode,
    BIOSModelError,
    BIOSVendor,
    BootDevice,
    FirmwareInformation,
    parse_firmware_date,
)
from .base import BIOSProvider, ValidationError


logger = logging.getLogger(__name__)

PROVIDER_VERSION: Final[str] = "1.0.0"
_UNKNOWN_BOOT_DEVICE_ID: Final[str] = "unknown"
_UNKNOWN_BOOT_DEVICE_NAME: Final[str] = "Unknown boot device"


class DefaultProvider(BIOSProvider):
    """Provide safe fallback behavior for BIOS providers.

    Vendor providers should override ``vendor()``, ``provider_name()``,
    ``detect()``, and any hardware-specific operations they support.

    Args:
        firmware:
            Optional initial firmware information. A defensive copy is stored.
        logger_instance:
            Optional provider logger. The module logger is used by default.
    """

    def __init__(
        self,
        firmware: FirmwareInformation | None = None,
        *,
        logger_instance: logging.Logger | None = None,
    ) -> None:
        self._logger = logger_instance or logger

        self._connected = False
        self._closed = False
        self._cache_valid = firmware is not None

        self._firmware = deepcopy(firmware) if firmware is not None else (
            FirmwareInformation()
        )

        self._boot_order: list[BootDevice] = []
        self._current_boot_device: BootDevice | None = None
        self._next_boot_device: BootDevice | None = None

        self._settings: dict[str, Any] = {}
        self._setting_defaults: dict[str, Any] = {}
        self._writable_settings: set[str] = set()
        self._setting_reboot_requirements: set[str] = set()

        self._pending_setting_values: dict[str, Any] = {}
        self._pending_original_values: dict[str, Any] = {}
        self._pending_reboot = False

        self._transaction_active = False
        self._transaction_snapshot: dict[str, Any] | None = None

        self._last_error: str | None = None
        self._last_operation = "initialize"

    # -------------------------------------------------------------------------
    # Shared protected helpers
    # -------------------------------------------------------------------------

    def _record_operation(self, operation: str) -> None:
        """Record a non-sensitive operation identifier."""
        self._last_operation = operation
        self._last_error = None

    def _record_error(self, operation: str, message: str) -> None:
        """Record a sanitized provider error."""
        self._last_operation = operation
        self._last_error = message
        self._logger.error("%s: %s", operation, message)

    def _unsupported(self, operation: str, feature: str) -> bool:
        """Record an unsupported mutating operation and return ``False``."""
        provider = self.provider_name()
        message = f"{feature} is not supported by {provider}."
        self._last_operation = operation
        self._last_error = message
        self._logger.warning("%s", message)
        return False

    def _register_setting(
        self,
        name: str,
        value: Any,
        *,
        default: Any = None,
        writable: bool = False,
        reboot_required: bool = False,
    ) -> None:
        """Register a setting exposed by a derived provider.

        Vendor providers may use this helper while loading firmware settings.
        Registering a setting does not itself write anything to firmware.
        """
        normalized_name = self._normalize_setting_name(name)

        self._settings[normalized_name] = deepcopy(value)
        self._setting_defaults[normalized_name] = deepcopy(default)

        if writable:
            self._writable_settings.add(normalized_name)
        else:
            self._writable_settings.discard(normalized_name)

        if reboot_required:
            self._setting_reboot_requirements.add(normalized_name)
        else:
            self._setting_reboot_requirements.discard(normalized_name)

    def _apply_setting(self, name: str, value: Any) -> bool:
        """Apply a setting through vendor-specific firmware tooling.

        Derived providers may override this hook instead of replacing the
        complete generic ``set_setting()`` implementation.
        """
        del name, value
        return False

    def _reset_setting_in_firmware(self, name: str) -> bool:
        """Reset a setting through vendor-specific firmware tooling."""
        default = self._setting_defaults.get(name)
        return self._apply_setting(name, deepcopy(default))

    @staticmethod
    def _normalize_setting_name(name: str) -> str:
        """Validate and normalize a firmware setting name."""
        if not isinstance(name, str):
            raise TypeError("Firmware setting names must be strings.")

        normalized = name.strip()
        if not normalized:
            raise ValueError("Firmware setting names must not be empty.")

        return normalized

    @staticmethod
    def _read_text_file(path: Path) -> str:
        """Read a small system-information file safely."""
        try:
            return path.read_text(
                encoding="utf-8",
                errors="replace",
            ).strip()
        except (OSError, PermissionError):
            return ""

    def _collect_firmware_information(self) -> FirmwareInformation:
        """Collect generic firmware identity information.

        Linux systems expose SMBIOS values under
        ``/sys/class/dmi/id``. Other operating systems retain any previously
        supplied information until a platform-specific provider overrides
        this method.
        """
        previous = self._firmware
        dmi_root = Path("/sys/class/dmi/id")

        if not dmi_root.is_dir():
            result = deepcopy(previous)
            result.collected_at = datetime.now(UTC)

            if not result.firmware_interface:
                result.firmware_interface = self.firmware_interface()

            return result

        manufacturer = self._read_text_file(dmi_root / "sys_vendor")
        product_name = self._read_text_file(dmi_root / "product_name")
        model = self._read_text_file(dmi_root / "product_version")
        serial_number = self._read_text_file(dmi_root / "product_serial")
        system_uuid = self._read_text_file(dmi_root / "product_uuid")
        sku = self._read_text_file(dmi_root / "product_sku")
        bios_vendor = self._read_text_file(dmi_root / "bios_vendor")
        bios_version = self._read_text_file(dmi_root / "bios_version")
        release_date_text = self._read_text_file(
            dmi_root / "bios_date"
        )
        embedded_controller_version = self._read_text_file(
            dmi_root / "ec_firmware_release"
        )

        release_date: date | None = None
        if release_date_text:
            try:
                release_date = parse_firmware_date(release_date_text)
            except BIOSModelError:
                self._logger.debug(
                    "Unable to normalize BIOS release date %r.",
                    release_date_text,
                )

        normalized_model = model or product_name

        return FirmwareInformation(
            vendor=BIOSVendor.from_string(manufacturer),
            mode=self._detect_bios_mode(),
            firmware_interface=self.firmware_interface(),
            manufacturer=manufacturer,
            product_name=product_name,
            model=normalized_model,
            serial_number=serial_number,
            system_uuid=system_uuid,
            sku=sku,
            bios_vendor=bios_vendor,
            bios_version=bios_version,
            bios_release_date=release_date,
            embedded_controller_version=embedded_controller_version,
            collected_at=datetime.now(UTC),
            extensions=deepcopy(previous.extensions),
            raw_data={
                "source": "linux-sysfs",
                "bios_date_raw": release_date_text,
            },
        )

    @staticmethod
    def _detect_bios_mode() -> BIOSMode:
        """Detect the current boot mode using generic operating-system data."""
        if platform.system().lower() == "linux":
            return (
                BIOSMode.UEFI
                if Path("/sys/firmware/efi").exists()
                else BIOSMode.LEGACY
            )

        return BIOSMode.UNKNOWN

    @staticmethod
    def _unknown_boot_device() -> BootDevice:
        """Create the standard placeholder used by the base contract."""
        return BootDevice(
            identifier=_UNKNOWN_BOOT_DEVICE_ID,
            name=_UNKNOWN_BOOT_DEVICE_NAME,
            enabled=False,
            persistent=False,
            metadata={"placeholder": True},
        )

    # -------------------------------------------------------------------------
    # Core identity and provider metadata
    # -------------------------------------------------------------------------

    def vendor(self) -> BIOSVendor:
        """Return the detected vendor or the generic fallback vendor."""
        if self._firmware.vendor is not BIOSVendor.UNKNOWN:
            return self._firmware.vendor

        return BIOSVendor.GENERIC

    def provider_name(self) -> str:
        """Return the default provider name."""
        return "Aquila Default BIOS Provider"

    def provider_version(self) -> str:
        """Return the default provider implementation version."""
        return PROVIDER_VERSION

    def supports_windows(self) -> bool:
        """Return whether the generic contract supports Windows providers."""
        return True

    def supports_linux(self) -> bool:
        """Return whether generic Linux firmware inspection is supported."""
        return True

    def connect(self) -> bool:
        """Initialize the provider and load firmware information."""
        self._record_operation("connect")

        if self._connected:
            return True

        if self._closed:
            self._closed = False

        try:
            if not self.detect():
                self._record_error(
                    "connect",
                    f"{self.provider_name()} does not match this system.",
                )
                return False

            self._connected = True

            if not self.refresh():
                self._connected = False
                return False

            return True
        except Exception as exc:
            self._connected = False
            self._record_error(
                "connect",
                f"Provider initialization failed: {exc}",
            )
            return False

    def disconnect(self) -> None:
        """Disconnect the provider and release transient state."""
        self._record_operation("disconnect")
        self._connected = False
        self._transaction_active = False
        self._transaction_snapshot = None

    def is_connected(self) -> bool:
        """Return whether the provider is connected."""
        return self._connected

    def detect(self) -> bool:
        """Match as the generic fallback provider.

        Vendor-specific providers must override this method with strict vendor
        and platform detection.
        """
        return True

    def refresh(self) -> bool:
        """Refresh cached firmware information."""
        self._record_operation("refresh")

        try:
            self._firmware = self._collect_firmware_information()
            self._cache_valid = True
            return True
        except Exception as exc:
            self._cache_valid = False
            self._record_error(
                "refresh",
                f"Unable to refresh firmware information: {exc}",
            )
            return False

    def firmware_interface(self) -> str:
        """Return the generic firmware interface name."""
        if platform.system().lower() == "linux":
            if Path("/sys/class/dmi/id").is_dir():
                return "linux-sysfs-smbios"

        return "generic-firmware-interface"

    # -------------------------------------------------------------------------
    # Firmware and system information
    # -------------------------------------------------------------------------

    def firmware_information(self) -> FirmwareInformation:
        """Return a defensive copy of cached firmware information."""
        if not self._cache_valid:
            self.refresh()

        return deepcopy(self._firmware)

    def bios_mode(self) -> BIOSMode:
        """Return the detected firmware boot mode."""
        if self._firmware.mode is not BIOSMode.UNKNOWN:
            return self._firmware.mode

        return self._detect_bios_mode()

    def manufacturer(self) -> str:
        return self._firmware.manufacturer

    def product_name(self) -> str:
        return self._firmware.product_name

    def model(self) -> str:
        return self._firmware.model

    def serial_number(self) -> str:
        return self._firmware.serial_number

    def system_uuid(self) -> str:
        return self._firmware.system_uuid

    def sku(self) -> str:
        return self._firmware.sku

    def bios_vendor(self) -> str:
        return self._firmware.bios_vendor

    def bios_version(self) -> str:
        return self._firmware.bios_version

    def bios_release_date(self) -> date:
        """Return the release date or ``date.min`` when unavailable."""
        return self._firmware.bios_release_date or date.min

    def embedded_controller_version(self) -> str:
        return self._firmware.embedded_controller_version

    # -------------------------------------------------------------------------
    # Capability discovery
    # -------------------------------------------------------------------------

    def supported_features(self) -> set[str]:
        """Return all capabilities positively reported by this provider."""
        checks = {
            "firmware_update": self.firmware_update_supported,
            "firmware_rollback": self.firmware_rollback_supported,
            "bios_password": self.bios_password_supported,
            "virtualization": self.virtualization_supported,
            "iommu": self.iommu_supported,
            "sriov": self.sriov_supported,
            "tpm": self.tpm_supported,
            "secure_boot": self.secure_boot_supported,
            "custom_secure_boot_keys": (
                self.custom_secure_boot_keys_supported
            ),
            "intel_boot_guard": self.intel_boot_guard_supported,
            "amd_platform_security": (
                self.amd_platform_security_supported
            ),
            "measured_boot": self.measured_boot_supported,
            "trusted_execution": self.trusted_execution_supported,
            "firmware_variables": self.firmware_variables_supported,
            "wake_on_lan": self.wake_on_lan_supported,
            "rtc_wake": self.rtc_wake_supported,
            "usb_wake": self.usb_wake_supported,
            "keyboard_wake": self.keyboard_wake_supported,
            "mouse_wake": self.mouse_wake_supported,
            "pcie_wake": self.pcie_wake_supported,
            "lid_wake": self.lid_wake_supported,
            "alarm_wake": self.alarm_wake_supported,
            "battery_charge_limit": (
                self.battery_charge_limit_supported
            ),
            "battery_health_mode": (
                self.battery_health_mode_supported
            ),
            "battery_calibration": (
                self.battery_calibration_supported
            ),
            "power_profiles": self.supports_power_profiles,
            "fast_boot": self.supports_fast_boot,
            "restore_power_on_ac": (
                self.restore_power_on_ac_supported
            ),
            "transactions": self.transactions_supported,
            "boot_menu": self.boot_menu_supported,
        }

        features = {
            name
            for name, check in checks.items()
            if self._safe_capability_check(check)
        }

        if self._settings:
            features.add("generic_settings")

        return features

    def _safe_capability_check(self, check: Any) -> bool:
        """Execute a capability check without breaking discovery."""
        try:
            return bool(check())
        except Exception:
            self._logger.debug(
                "Capability check failed.",
                exc_info=True,
            )
            return False

    def supports_feature(self, name: str) -> bool:
        """Return whether a normalized feature identifier is supported."""
        normalized = name.strip().lower().replace("-", "_")
        return normalized in self.supported_features()

    def supported_settings(self) -> list[str]:
        """Return available setting identifiers in stable order."""
        return sorted(self._settings)

    # -------------------------------------------------------------------------
    # Generic BIOS settings
    # -------------------------------------------------------------------------

    def available_settings(self) -> dict[str, Any]:
        """Return a defensive copy of currently available settings."""
        return deepcopy(self._settings)

    def setting_exists(self, name: str) -> bool:
        """Return whether a setting is registered."""
        try:
            normalized = self._normalize_setting_name(name)
        except (TypeError, ValueError):
            return False

        return normalized in self._settings

    def get_setting(self, name: str) -> Any:
        """Return a defensive copy of a setting value.

        ``None`` is returned when the setting is not available.
        """
        try:
            normalized = self._normalize_setting_name(name)
        except (TypeError, ValueError):
            return None

        if normalized not in self._settings:
            return None

        return deepcopy(self._settings[normalized])

    def set_setting(self, name: str, value: Any) -> bool:
        """Apply a registered writable setting."""
        operation = "set_setting"
        self._record_operation(operation)

        try:
            normalized = self._normalize_setting_name(name)
        except (TypeError, ValueError) as exc:
            self._record_error(operation, str(exc))
            return False

        if normalized not in self._settings:
            self._record_error(
                operation,
                f"Firmware setting {normalized!r} is unavailable.",
            )
            return False

        if normalized not in self._writable_settings:
            self._record_error(
                operation,
                f"Firmware setting {normalized!r} is read-only.",
            )
            return False

        old_value = deepcopy(self._settings[normalized])

        try:
            applied = self._apply_setting(normalized, deepcopy(value))
        except Exception as exc:
            self._record_error(
                operation,
                f"Unable to set {normalized!r}: {exc}",
            )
            return False

        if not applied:
            self._record_error(
                operation,
                f"Firmware rejected setting {normalized!r}.",
            )
            return False

        self._pending_original_values.setdefault(normalized, old_value)
        self._pending_setting_values[normalized] = deepcopy(value)
        self._settings[normalized] = deepcopy(value)

        if normalized in self._setting_reboot_requirements:
            self._pending_reboot = True

        return True

    def reset_setting(self, name: str) -> bool:
        """Reset a registered writable setting to its default."""
        operation = "reset_setting"
        self._record_operation(operation)

        try:
            normalized = self._normalize_setting_name(name)
        except (TypeError, ValueError) as exc:
            self._record_error(operation, str(exc))
            return False

        if normalized not in self._settings:
            self._record_error(
                operation,
                f"Firmware setting {normalized!r} is unavailable.",
            )
            return False

        if normalized not in self._writable_settings:
            self._record_error(
                operation,
                f"Firmware setting {normalized!r} is read-only.",
            )
            return False

        old_value = deepcopy(self._settings[normalized])

        try:
            applied = self._reset_setting_in_firmware(normalized)
        except Exception as exc:
            self._record_error(
                operation,
                f"Unable to reset {normalized!r}: {exc}",
            )
            return False

        if not applied:
            self._record_error(
                operation,
                f"Firmware rejected reset of {normalized!r}.",
            )
            return False

        default = deepcopy(self._setting_defaults.get(normalized))
        self._pending_original_values.setdefault(normalized, old_value)
        self._pending_setting_values[normalized] = deepcopy(default)
        self._settings[normalized] = default

        if normalized in self._setting_reboot_requirements:
            self._pending_reboot = True

        return True

    def restore_defaults(self) -> bool:
        """Restore all writable provider-visible settings to their defaults."""
        self._record_operation("restore_defaults")

        if not self._writable_settings:
            return self._unsupported(
                "restore_defaults",
                "BIOS settings restoration",
            )

        success = True

        for name in sorted(self._writable_settings):
            if not self.reset_setting(name):
                success = False

        self._last_operation = "restore_defaults"
        if success:
            self._last_error = None

        return success

    # -------------------------------------------------------------------------
    # Boot management
    # -------------------------------------------------------------------------

    def boot_order(self) -> list[BootDevice]:
        """Return a defensive copy of the persistent boot order."""
        return deepcopy(self._boot_order)

    def set_boot_order(self, devices: Sequence[BootDevice]) -> bool:
        """Set the persistent boot order.

        The default provider cannot modify firmware boot entries.
        """
        del devices
        return self._unsupported(
            "set_boot_order",
            "Persistent boot-order management",
        )

    def add_boot_device(self, device: BootDevice) -> bool:
        """Add a persistent boot device."""
        del device
        return self._unsupported(
            "add_boot_device",
            "Persistent boot-device management",
        )

    def remove_boot_device(self, device: BootDevice) -> bool:
        """Remove a persistent boot device."""
        del device
        return self._unsupported(
            "remove_boot_device",
            "Persistent boot-device management",
        )

    def restore_default_boot_order(self) -> bool:
        """Restore the vendor-defined default boot order."""
        return self._unsupported(
            "restore_default_boot_order",
            "Default boot-order restoration",
        )

    def current_boot_device(self) -> BootDevice:
        """Return the current boot device or a safe placeholder."""
        if self._current_boot_device is None:
            return self._unknown_boot_device()

        return deepcopy(self._current_boot_device)

    def next_boot_device(self) -> BootDevice | None:
        """Return the configured one-time boot device."""
        return deepcopy(self._next_boot_device)

    def set_next_boot_device(self, device: BootDevice) -> bool:
        """Set a one-time boot device."""
        del device
        return self._unsupported(
            "set_next_boot_device",
            "One-time boot-device management",
        )

    def clear_next_boot_device(self) -> bool:
        """Clear the configured one-time boot device."""
        if self._next_boot_device is None:
            self._record_operation("clear_next_boot_device")
            return True

        return self._unsupported(
            "clear_next_boot_device",
            "One-time boot-device management",
        )

    def boot_menu_supported(self) -> bool:
        """Return whether firmware boot-menu management is supported."""
        return False

    def restore_factory_defaults(self) -> bool:
        """Perform a complete vendor-defined firmware factory reset."""
        return self._unsupported(
            "restore_factory_defaults",
            "Firmware factory reset",
        )

    # -------------------------------------------------------------------------
    # Firmware updates
    # -------------------------------------------------------------------------

    def firmware_update_supported(self) -> bool:
        """Return whether firmware update management is supported."""
        return False

    def current_firmware_version(self) -> str:
        """Return the currently installed firmware version."""
        return self.bios_version()

    def latest_firmware_version(self) -> str | None:
        """Return the latest available firmware version, if known."""
        return None

    def check_for_firmware_updates(self) -> bool:
        """Return whether an applicable firmware update is available."""
        self._record_operation("check_for_firmware_updates")
        return False

    def install_firmware_update(self) -> bool:
        """Install an applicable firmware update."""
        return self._unsupported(
            "install_firmware_update",
            "Firmware updates",
        )

    def firmware_rollback_supported(self) -> bool:
        """Return whether firmware rollback is supported."""
        return False

    def rollback_firmware(self) -> bool:
        """Roll back the installed firmware."""
        return self._unsupported(
            "rollback_firmware",
            "Firmware rollback",
        )

    # -------------------------------------------------------------------------
    # BIOS password management
    # -------------------------------------------------------------------------

    def bios_password_supported(self) -> bool:
        """Return whether BIOS password management is supported."""
        return False

    def bios_password_configured(self) -> bool:
        """Return whether a BIOS administrator password is configured."""
        return False

    def set_bios_password(self, password: str) -> bool:
        """Attempt to set the BIOS administrator password.

        The supplied password is deliberately discarded without being logged,
        cached, serialized, or included in the provider error state.
        """
        del password
        return self._unsupported(
            "set_bios_password",
            "BIOS password management",
        )

    def clear_bios_password(self, password: str) -> bool:
        """Attempt to clear the BIOS administrator password."""
        del password
        return self._unsupported(
            "clear_bios_password",
            "BIOS password management",
        )

    def verify_bios_password(self, password: str) -> bool:
        """Return whether the supplied BIOS password can be verified."""
        del password
        self._record_operation("verify_bios_password")
        return False

    # -------------------------------------------------------------------------
    # Virtualization, IOMMU, and SR-IOV
    # -------------------------------------------------------------------------

    def virtualization_supported(self) -> bool:
        """Return whether virtualization control is supported."""
        return False

    def virtualization_enabled(self) -> bool:
        """Return whether hardware virtualization is enabled."""
        return False

    def enable_virtualization(self) -> bool:
        """Enable hardware virtualization."""
        return self._unsupported(
            "enable_virtualization",
            "Hardware virtualization control",
        )

    def disable_virtualization(self) -> bool:
        """Disable hardware virtualization."""
        return self._unsupported(
            "disable_virtualization",
            "Hardware virtualization control",
        )

    def iommu_supported(self) -> bool:
        """Return whether IOMMU control is supported."""
        return False

    def iommu_enabled(self) -> bool:
        """Return whether the IOMMU is enabled."""
        return False

    def enable_iommu(self) -> bool:
        """Enable the IOMMU."""
        return self._unsupported(
            "enable_iommu",
            "IOMMU control",
        )

    def disable_iommu(self) -> bool:
        """Disable the IOMMU."""
        return self._unsupported(
            "disable_iommu",
            "IOMMU control",
        )

    def sriov_supported(self) -> bool:
        """Return whether SR-IOV control is supported."""
        return False

    def sriov_enabled(self) -> bool:
        """Return whether SR-IOV is enabled."""
        return False

    def enable_sriov(self) -> bool:
        """Enable SR-IOV."""
        return self._unsupported(
            "enable_sriov",
            "SR-IOV control",
        )

    def disable_sriov(self) -> bool:
        """Disable SR-IOV."""
        return self._unsupported(
            "disable_sriov",
            "SR-IOV control",
        )

    # -------------------------------------------------------------------------
    # TPM, Secure Boot, and platform security
    # -------------------------------------------------------------------------

    def tpm_supported(self) -> bool:
        """Return whether TPM control is supported."""
        return False

    def tpm_enabled(self) -> bool:
        """Return whether the TPM is enabled."""
        return False

    def enable_tpm(self) -> bool:
        """Enable the TPM."""
        return self._unsupported(
            "enable_tpm",
            "TPM control",
        )

    def disable_tpm(self) -> bool:
        """Disable the TPM."""
        return self._unsupported(
            "disable_tpm",
            "TPM control",
        )

    def secure_boot_supported(self) -> bool:
        """Return whether Secure Boot control is supported."""
        return False

    def secure_boot_enabled(self) -> bool:
        """Return whether Secure Boot is enabled."""
        return False

    def enable_secure_boot(self) -> bool:
        """Enable Secure Boot."""
        return self._unsupported(
            "enable_secure_boot",
            "Secure Boot control",
        )

    def disable_secure_boot(self) -> bool:
        """Disable Secure Boot."""
        return self._unsupported(
            "disable_secure_boot",
            "Secure Boot control",
        )

    def secure_boot_keys_installed(self) -> bool:
        """Return whether standard Secure Boot keys are installed."""
        return False

    def restore_secure_boot_keys(self) -> bool:
        """Restore the platform's standard Secure Boot keys."""
        return self._unsupported(
            "restore_secure_boot_keys",
            "Secure Boot key restoration",
        )

    def custom_secure_boot_keys_supported(self) -> bool:
        """Return whether custom Secure Boot keys are supported."""
        return False

    def intel_boot_guard_supported(self) -> bool:
        """Return whether Intel Boot Guard reporting is supported."""
        return False

    def intel_boot_guard_enabled(self) -> bool:
        """Return whether Intel Boot Guard is enabled."""
        return False

    def amd_platform_security_supported(self) -> bool:
        """Return whether AMD platform-security reporting is supported."""
        return False

    def amd_platform_security_enabled(self) -> bool:
        """Return whether AMD platform security is enabled."""
        return False

    def measured_boot_supported(self) -> bool:
        """Return whether measured boot reporting is supported."""
        return False

    def trusted_execution_supported(self) -> bool:
        """Return whether trusted-execution reporting is supported."""
        return False

    # -------------------------------------------------------------------------
    # Firmware variables
    # -------------------------------------------------------------------------

    def firmware_variables_supported(self) -> bool:
        """Return whether firmware-variable management is supported."""
        return False

    def read_variable(self, name: str) -> bytes:
        """Read a firmware variable.

        The default provider returns an empty byte string because it has no
        variable-management backend.
        """
        del name
        self._record_operation("read_variable")
        return b""

    def write_variable(self, name: str, value: bytes) -> bool:
        """Write a firmware variable."""
        del name, value
        return self._unsupported(
            "write_variable",
            "Firmware-variable management",
        )

    def delete_variable(self, name: str) -> bool:
        """Delete a firmware variable."""
        del name
        return self._unsupported(
            "delete_variable",
            "Firmware-variable management",
        )

    # -------------------------------------------------------------------------
    # Wake features
    # -------------------------------------------------------------------------

    def wake_on_lan_supported(self) -> bool:
        """Return whether Wake-on-LAN control is supported."""
        return False

    def is_wake_on_lan_enabled(self) -> bool:
        """Return whether Wake-on-LAN is enabled."""
        return False

    def enable_wake_on_lan(self) -> bool:
        """Enable Wake-on-LAN."""
        return self._unsupported(
            "enable_wake_on_lan",
            "Wake-on-LAN control",
        )

    def disable_wake_on_lan(self) -> bool:
        """Disable Wake-on-LAN."""
        return self._unsupported(
            "disable_wake_on_lan",
            "Wake-on-LAN control",
        )

    def rtc_wake_supported(self) -> bool:
        """Return whether RTC wake control is supported."""
        return False

    def is_rtc_wake_enabled(self) -> bool:
        """Return whether RTC wake is enabled."""
        return False

    def enable_rtc_wake(self) -> bool:
        """Enable RTC wake."""
        return self._unsupported(
            "enable_rtc_wake",
            "RTC wake control",
        )

    def disable_rtc_wake(self) -> bool:
        """Disable RTC wake."""
        return self._unsupported(
            "disable_rtc_wake",
            "RTC wake control",
        )

    def usb_wake_supported(self) -> bool:
        """Return whether USB wake control is supported."""
        return False

    def is_usb_wake_enabled(self) -> bool:
        """Return whether USB wake is enabled."""
        return False

    def enable_usb_wake(self) -> bool:
        """Enable USB wake."""
        return self._unsupported(
            "enable_usb_wake",
            "USB wake control",
        )

    def disable_usb_wake(self) -> bool:
        """Disable USB wake."""
        return self._unsupported(
            "disable_usb_wake",
            "USB wake control",
        )

    def keyboard_wake_supported(self) -> bool:
        """Return whether keyboard wake control is supported."""
        return False

    def is_keyboard_wake_enabled(self) -> bool:
        """Return whether keyboard wake is enabled."""
        return False

    def enable_keyboard_wake(self) -> bool:
        """Enable keyboard wake."""
        return self._unsupported(
            "enable_keyboard_wake",
            "Keyboard wake control",
        )

    def disable_keyboard_wake(self) -> bool:
        """Disable keyboard wake."""
        return self._unsupported(
            "disable_keyboard_wake",
            "Keyboard wake control",
        )

    def mouse_wake_supported(self) -> bool:
        """Return whether mouse wake control is supported."""
        return False

    def is_mouse_wake_enabled(self) -> bool:
        """Return whether mouse wake is enabled."""
        return False

    def enable_mouse_wake(self) -> bool:
        """Enable mouse wake."""
        return self._unsupported(
            "enable_mouse_wake",
            "Mouse wake control",
        )

    def disable_mouse_wake(self) -> bool:
        """Disable mouse wake."""
        return self._unsupported(
            "disable_mouse_wake",
            "Mouse wake control",
        )

    def pcie_wake_supported(self) -> bool:
        """Return whether PCIe wake control is supported."""
        return False

    def is_pcie_wake_enabled(self) -> bool:
        """Return whether PCIe wake is enabled."""
        return False

    def enable_pcie_wake(self) -> bool:
        """Enable PCIe wake."""
        return self._unsupported(
            "enable_pcie_wake",
            "PCIe wake control",
        )

    def disable_pcie_wake(self) -> bool:
        """Disable PCIe wake."""
        return self._unsupported(
            "disable_pcie_wake",
            "PCIe wake control",
        )

    def lid_wake_supported(self) -> bool:
        """Return whether lid-open wake control is supported."""
        return False

    def is_lid_wake_enabled(self) -> bool:
        """Return whether lid-open wake is enabled."""
        return False

    def enable_lid_wake(self) -> bool:
        """Enable lid-open wake."""
        return self._unsupported(
            "enable_lid_wake",
            "Lid-open wake control",
        )

    def disable_lid_wake(self) -> bool:
        """Disable lid-open wake."""
        return self._unsupported(
            "disable_lid_wake",
            "Lid-open wake control",
        )

    def alarm_wake_supported(self) -> bool:
        """Return whether scheduled alarm wake control is supported."""
        return False

    def is_alarm_wake_enabled(self) -> bool:
        """Return whether scheduled alarm wake is enabled."""
        return False

    def enable_alarm_wake(self) -> bool:
        """Enable scheduled alarm wake."""
        return self._unsupported(
            "enable_alarm_wake",
            "Scheduled alarm wake control",
        )

    def disable_alarm_wake(self) -> bool:
        """Disable scheduled alarm wake."""
        return self._unsupported(
            "disable_alarm_wake",
            "Scheduled alarm wake control",
        )

    # -------------------------------------------------------------------------
    # Battery management
    # -------------------------------------------------------------------------

    def battery_present(self) -> bool:
        """Return whether a battery is known to be present."""
        return False

    def battery_charge_limit_supported(self) -> bool:
        """Return whether charge-limit management is supported."""
        return False

    def get_charge_limit(self) -> int:
        """Return the configured battery charge limit.

        Zero indicates that no charge limit could be determined.
        """
        return 0

    def set_charge_limit(self, percent: int) -> bool:
        """Set the battery charge limit."""
        if not isinstance(percent, int) or isinstance(percent, bool):
            self._record_error(
                "set_charge_limit",
                "Battery charge limit must be an integer.",
            )
            return False

        if not 0 <= percent <= 100:
            self._record_error(
                "set_charge_limit",
                "Battery charge limit must be between 0 and 100.",
            )
            return False

        return self._unsupported(
            "set_charge_limit",
            "Battery charge-limit management",
        )

    def battery_health_mode_supported(self) -> bool:
        """Return whether battery health modes are supported."""
        return False

    def get_battery_health_mode(self) -> str:
        """Return the active battery health mode."""
        return ""

    def set_battery_health_mode(self, mode: str) -> bool:
        """Set the active battery health mode."""
        del mode
        return self._unsupported(
            "set_battery_health_mode",
            "Battery health-mode management",
        )

    def battery_calibration_supported(self) -> bool:
        """Return whether battery calibration is supported."""
        return False

    def start_battery_calibration(self) -> bool:
        """Start battery calibration."""
        return self._unsupported(
            "start_battery_calibration",
            "Battery calibration",
        )

    def stop_battery_calibration(self) -> bool:
        """Stop battery calibration."""
        return self._unsupported(
            "stop_battery_calibration",
            "Battery calibration",
        )

    # -------------------------------------------------------------------------
    # Power management
    # -------------------------------------------------------------------------

    def supports_power_profiles(self) -> bool:
        """Return whether firmware power profiles are supported."""
        return False

    def get_power_profile(self) -> str:
        """Return the active firmware power profile."""
        return ""

    def set_power_profile(self, profile: str) -> bool:
        """Set the active firmware power profile."""
        del profile
        return self._unsupported(
            "set_power_profile",
            "Firmware power-profile management",
        )

    def supports_fast_boot(self) -> bool:
        """Return whether firmware fast boot is supported."""
        return False

    def fast_boot_enabled(self) -> bool:
        """Return whether firmware fast boot is enabled."""
        return False

    def enable_fast_boot(self) -> bool:
        """Enable firmware fast boot."""
        return self._unsupported(
            "enable_fast_boot",
            "Firmware fast-boot management",
        )

    def disable_fast_boot(self) -> bool:
        """Disable firmware fast boot."""
        return self._unsupported(
            "disable_fast_boot",
            "Firmware fast-boot management",
        )

    def restore_power_on_ac_supported(self) -> bool:
        """Return whether restore-on-AC-power management is supported."""
        return False

    def restore_power_on_ac_enabled(self) -> bool:
        """Return whether automatic power restoration is enabled."""
        return False

    def enable_restore_power_on_ac(self) -> bool:
        """Enable automatic power restoration when AC power returns."""
        return self._unsupported(
            "enable_restore_power_on_ac",
            "Restore-on-AC-power management",
        )

    def disable_restore_power_on_ac(self) -> bool:
        """Disable automatic power restoration when AC power returns."""
        return self._unsupported(
            "disable_restore_power_on_ac",
            "Restore-on-AC-power management",
        )

    # -------------------------------------------------------------------------
    # Transaction management
    # -------------------------------------------------------------------------

    def transactions_supported(self) -> bool:
        """Return whether genuine atomic firmware transactions are supported.

        The default provider supports only local best-effort staging, not an
        atomic firmware transaction.
        """
        return False

    def begin_transaction(self) -> bool:
        """Begin an atomic firmware configuration transaction."""
        return self._unsupported(
            "begin_transaction",
            "Atomic firmware transactions",
        )

    def commit_transaction(self) -> bool:
        """Commit an active atomic firmware transaction."""
        return self._unsupported(
            "commit_transaction",
            "Atomic firmware transactions",
        )

    def rollback_transaction(self) -> bool:
        """Roll back an active atomic firmware transaction."""
        return self._unsupported(
            "rollback_transaction",
            "Atomic firmware transactions",
        )

    def transaction_active(self) -> bool:
        """Return whether an atomic firmware transaction is active."""
        return self._transaction_active

    # -------------------------------------------------------------------------
    # Firmware synchronization and pending changes
    # -------------------------------------------------------------------------

    def sync(self) -> bool:
        """Reconcile cached provider state with the firmware interface."""
        self._record_operation("sync")
        return self.refresh()

    def sync_firmware(self) -> bool:
        """Synchronize staged configuration with system firmware.

        Generic setting changes are applied by ``set_setting()`` through the
        provider's ``_apply_setting()`` hook. The default synchronization
        operation therefore refreshes firmware state when no changes remain
        staged, or delegates to ``commit_changes()`` when changes are pending.
        """
        self._record_operation("sync_firmware")

        if self.pending_changes():
            return self.commit_changes()

        return self.refresh()

    def commit_changes(self) -> bool:
        """Finalize nontransactional changes staged by the provider.

        Changes have already been sent through ``_apply_setting()`` before
        reaching this method. This operation clears local staging metadata but
        does not claim atomic transaction semantics.
        """
        self._record_operation("commit_changes")

        if not self._pending_setting_values:
            return True

        self._pending_setting_values.clear()
        self._pending_original_values.clear()
        self._cache_valid = False
        return True

    def reload(self) -> bool:
        """Discard cached data and perform a complete provider reload."""
        self._record_operation("reload")
        self.invalidate_cache()
        return self.refresh()

    def reload_configuration(self) -> bool:
        """Discard cached configuration and reload provider information.

        Vendor providers that expose a dedicated settings backend should
        override this method to reload settings without rebuilding unrelated
        provider state.
        """
        self._record_operation("reload_configuration")

        if self.pending_changes():
            self._record_error(
                "reload_configuration",
                "Cannot reload configuration while changes are pending.",
            )
            return False

        return self.reload()

    def invalidate_cache(self) -> None:
        """Mark cached provider information as stale."""
        self._last_operation = "invalidate_cache"
        self._last_error = None
        self._cache_valid = False

    def pending_reboot_required(self) -> bool:
        """Return whether applied changes require a system reboot."""
        return self._pending_reboot

    def pending_changes(self) -> bool:
        """Return whether nontransactional configuration changes are staged."""
        return bool(self._pending_setting_values)

    def clear_pending_changes(self) -> bool:
        """Discard local staging metadata and restore cached original values.

        This restores the provider's local setting cache. It does not promise
        to reverse firmware writes that were already accepted. Providers with
        a true rollback mechanism should override this method.
        """
        self._record_operation("clear_pending_changes")

        for name, original_value in self._pending_original_values.items():
            if name in self._settings:
                self._settings[name] = deepcopy(original_value)

        self._pending_setting_values.clear()
        self._pending_original_values.clear()
        self._pending_reboot = False
        return True

    # -------------------------------------------------------------------------
    # Operation status and error reporting
    # -------------------------------------------------------------------------

    def last_error(self) -> str | None:
        """Return the sanitized description of the last provider error."""
        return self._last_error

    def last_operation(self) -> str:
        """Return the stable identifier of the last attempted operation."""
        return self._last_operation

    # -------------------------------------------------------------------------
    # Validation, reporting, and diagnostics
    # -------------------------------------------------------------------------

    def validate(self) -> bool:
        """Validate provider state and access to its firmware interface."""
        self._record_operation("validate")

        if self._closed:
            self._record_error(
                "validate",
                "The provider is closed.",
            )
            return False

        if not self.detect():
            self._record_error(
                "validate",
                "The provider does not match this system.",
            )
            return False

        return True

    def validate_configuration(self) -> list[ValidationError]:
        """Return validation issues for the current configuration."""
        issues: list[ValidationError] = []

        unknown_pending_settings = (
            set(self._pending_setting_values) - set(self._settings)
        )
        for name in sorted(unknown_pending_settings):
            issues.append(
                ValidationError(
                    field=name,
                    message="A pending value references an unavailable setting.",
                    code="unknown_pending_setting",
                )
            )

        nonwritable_pending_settings = (
            set(self._pending_setting_values) - self._writable_settings
        )
        for name in sorted(nonwritable_pending_settings):
            issues.append(
                ValidationError(
                    field=name,
                    message="A read-only setting has a pending change.",
                    code="readonly_setting_pending",
                )
            )

        if self._transaction_active and not self.transactions_supported():
            issues.append(
                ValidationError(
                    field="transaction",
                    message=(
                        "A transaction is marked active even though the "
                        "provider does not support atomic transactions."
                    ),
                    code="unsupported_transaction_active",
                )
            )

        return issues

    def summary(self) -> dict[str, Any]:
        """Return a concise, non-sensitive provider summary."""
        return {
            "provider": self.provider_name(),
            "provider_version": self.provider_version(),
            "vendor": self._enum_value(self.vendor()),
            "connected": self.is_connected(),
            "detected": self._safe_detect(),
            "firmware_interface": self.firmware_interface(),
            "bios_mode": self._enum_value(self.bios_mode()),
            "bios_version": self.bios_version(),
            "model": self.model(),
            "supported_features": sorted(self.supported_features()),
            "pending_changes": self.pending_changes(),
            "reboot_required": self.pending_reboot_required(),
        }

    def report(self) -> dict[str, Any]:
        """Return a detailed, non-sensitive provider and firmware report."""
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "summary": self.summary(),
            "system": {
                "manufacturer": self.manufacturer(),
                "product_name": self.product_name(),
                "model": self.model(),
                "serial_number": self.serial_number(),
                "system_uuid": self.system_uuid(),
                "sku": self.sku(),
            },
            "firmware": {
                "vendor": self.bios_vendor(),
                "version": self.bios_version(),
                "release_date": self._date_value(
                    self._firmware.bios_release_date
                ),
                "embedded_controller_version": (
                    self.embedded_controller_version()
                ),
                "mode": self._enum_value(self.bios_mode()),
                "interface": self.firmware_interface(),
            },
            "capabilities": {
                name: True
                for name in sorted(self.supported_features())
            },
            "settings": self.available_settings(),
            "boot": {
                "order": [
                    self._serialize_value(device)
                    for device in self.boot_order()
                ],
                "current": self._serialize_value(
                    self.current_boot_device()
                ),
                "next": self._serialize_value(self.next_boot_device()),
            },
            "state": {
                "connected": self.is_connected(),
                "closed": self._closed,
                "cache_valid": self._cache_valid,
                "pending_changes": self.pending_changes(),
                "pending_reboot_required": (
                    self.pending_reboot_required()
                ),
                "transaction_active": self.transaction_active(),
            },
            "validation": [
                self._serialize_value(issue)
                for issue in self.validate_configuration()
            ],
        }

    def health(self) -> dict[str, Any]:
        """Return provider, connection, cache, and configuration health."""
        issues = self.validate_configuration()
        healthy = (
            not self._closed
            and self._safe_detect()
            and not any(issue.severity == "error" for issue in issues)
        )

        return {
            "healthy": healthy,
            "connected": self.is_connected(),
            "closed": self._closed,
            "detected": self._safe_detect(),
            "cache_valid": self._cache_valid,
            "configuration_valid": not issues,
            "issue_count": len(issues),
            "issues": [
                self._serialize_value(issue)
                for issue in issues
            ],
            "last_operation": self.last_operation(),
            "last_error": self.last_error(),
        }

    def diagnostics(self) -> dict[str, Any]:
        """Return sanitized provider diagnostic information."""
        return {
            "provider": self.provider_name(),
            "provider_version": self.provider_version(),
            "python_version": platform.python_version(),
            "operating_system": platform.system(),
            "operating_system_release": platform.release(),
            "machine": platform.machine(),
            "firmware_interface": self.firmware_interface(),
            "connected": self.is_connected(),
            "closed": self._closed,
            "cache_valid": self._cache_valid,
            "detected": self._safe_detect(),
            "supported_features": sorted(self.supported_features()),
            "supported_settings": self.supported_settings(),
            "pending_changes": self.pending_changes(),
            "pending_change_count": len(self._pending_setting_values),
            "pending_reboot_required": self.pending_reboot_required(),
            "transaction_supported": self.transactions_supported(),
            "transaction_active": self.transaction_active(),
            "last_operation": self.last_operation(),
            "last_error": self.last_error(),
        }

    def _safe_detect(self) -> bool:
        """Run provider detection safely for reporting."""
        try:
            return bool(self.detect())
        except Exception:
            self._logger.debug(
                "Provider detection failed during reporting.",
                exc_info=True,
            )
            return False

    # -------------------------------------------------------------------------
    # Serialization and export
    # -------------------------------------------------------------------------

    @staticmethod
    def _enum_value(value: Any) -> Any:
        """Return an enum's underlying value when one is available."""
        return getattr(value, "value", value)

    @staticmethod
    def _date_value(value: date | datetime | None) -> str | None:
        """Return an ISO-formatted date or datetime."""
        return value.isoformat() if value is not None else None

    @classmethod
    def _serialize_value(cls, value: Any) -> Any:
        """Convert provider values into JSON-compatible non-sensitive data."""
        if value is None or isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, bytes):
            # Raw firmware bytes may be sensitive and should not be exported.
            return f"<{len(value)} bytes>"

        if isinstance(value, (date, datetime)):
            return value.isoformat()

        enum_value = getattr(value, "value", None)
        if enum_value is not None and not callable(enum_value):
            return cls._serialize_value(enum_value)

        if isinstance(value, dict):
            return {
                str(key): cls._serialize_value(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple, set, frozenset)):
            return [cls._serialize_value(item) for item in value]

        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            return cls._serialize_value(to_dict())

        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            return cls._serialize_value(model_dump())

        dataclass_fields = getattr(value, "__dataclass_fields__", None)
        if dataclass_fields is not None:
            return {
                name: cls._serialize_value(getattr(value, name))
                for name in dataclass_fields
            }

        public_state = getattr(value, "__dict__", None)
        if isinstance(public_state, dict):
            return {
                str(key): cls._serialize_value(item)
                for key, item in public_state.items()
                if not str(key).startswith("_")
            }

        return str(value)

    def to_dict(self) -> dict[str, Any]:
        """Serialize non-sensitive provider state to a dictionary."""
        serialized = self._serialize_value(self.report())

        if isinstance(serialized, dict):
            return serialized

        return {"report": serialized}

    def to_json(self) -> str:
        """Serialize non-sensitive provider state as formatted JSON."""
        return json.dumps(
            self.to_dict(),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )

    def export(self) -> dict[str, Any]:
        """Export provider information in its preferred structured format."""
        return self.to_dict()

    def export_yaml(self) -> str:
        """Export non-sensitive provider information as YAML.

        PyYAML is used when available. If it is not installed, the method
        returns JSON, which is valid YAML 1.2.
        """
        data = self.to_dict()

        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            return json.dumps(
                data,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )

        return str(
            yaml.safe_dump(
                data,
                sort_keys=True,
                allow_unicode=True,
                default_flow_style=False,
            )
        )

    def export_markdown(self) -> str:
        """Export non-sensitive provider information as Markdown."""
        report = self.to_dict()
        summary = report.get("summary", {})
        firmware = report.get("firmware", {})
        system = report.get("system", {})
        health = self.health()

        lines = [
            f"# BIOS Report: {self.provider_name()}",
            "",
            f"_Generated: {report.get('generated_at', '')}_",
            "",
            "## Provider",
            "",
            f"- **Name:** {summary.get('provider', '')}",
            f"- **Version:** {summary.get('provider_version', '')}",
            f"- **Vendor:** {summary.get('vendor', '')}",
            f"- **Connected:** {summary.get('connected', False)}",
            f"- **Healthy:** {health.get('healthy', False)}",
            "",
            "## System",
            "",
            f"- **Manufacturer:** {system.get('manufacturer', '')}",
            f"- **Product:** {system.get('product_name', '')}",
            f"- **Model:** {system.get('model', '')}",
            f"- **Serial number:** {system.get('serial_number', '')}",
            f"- **UUID:** {system.get('system_uuid', '')}",
            f"- **SKU:** {system.get('sku', '')}",
            "",
            "## Firmware",
            "",
            f"- **Vendor:** {firmware.get('vendor', '')}",
            f"- **Version:** {firmware.get('version', '')}",
            f"- **Release date:** {firmware.get('release_date', '')}",
            f"- **Mode:** {firmware.get('mode', '')}",
            f"- **Interface:** {firmware.get('interface', '')}",
            (
                "- **Embedded controller:** "
                f"{firmware.get('embedded_controller_version', '')}"
            ),
            "",
            "## Supported Features",
            "",
        ]

        features = summary.get("supported_features", [])
        if features:
            lines.extend(f"- `{feature}`" for feature in features)
        else:
            lines.append("- None reported")

        lines.extend(
            [
                "",
                "## Configuration",
                "",
                (
                    "- **Pending changes:** "
                    f"{summary.get('pending_changes', False)}"
                ),
                (
                    "- **Reboot required:** "
                    f"{summary.get('reboot_required', False)}"
                ),
                "",
                "## Diagnostics",
                "",
                f"- **Last operation:** {self.last_operation()}",
                f"- **Last error:** {self.last_error() or 'None'}",
                "",
            ]
        )

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Lifecycle and cleanup
    # -------------------------------------------------------------------------

    def close(self) -> None:
        """Release resources and close the provider safely.

        Repeated calls are harmless. Local pending state and cached sensitive
        operation metadata are cleared.
        """
        if self._closed:
            return

        try:
            self.disconnect()
        finally:
            self._pending_setting_values.clear()
            self._pending_original_values.clear()
            self._transaction_snapshot = None
            self._transaction_active = False
            self._pending_reboot = False
            self._connected = False
            self._closed = True
            self._last_operation = "close"
            self._last_error = None


__all__ = [
    "DefaultProvider",
    "PROVIDER_VERSION",
]
