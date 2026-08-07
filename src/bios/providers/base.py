"""Base contracts and exceptions for Project Aquila BIOS providers.

This module defines the complete interface exposed by every BIOS provider.

Architecture
------------
``BIOSProvider``
    Defines the complete provider contract. Only essential identity,
    connection, detection, refresh, and firmware-information operations are
    abstract.

``DefaultProvider``
    Implements optional operations with safe fallback behavior and shared
    model-backed implementations.

Vendor providers
    Inherit from ``DefaultProvider`` and override only the capabilities
    supported by their hardware and vendor tooling.

Optional methods intentionally raise ``NotImplementedError`` here. Safe
fallback values belong in ``DefaultProvider``, not in this interface class.
"""

from __future__ import annotations
from types import TracebackType
from typing import Any, Self

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field as dataclass_field
from datetime import date
from typing import Any

from ..models import BIOSMode, BIOSVendor, BootDevice, FirmwareInformation


# =============================================================================
# Exceptions
# =============================================================================


class BIOSProviderError(Exception):
    """Base exception for all BIOS provider failures."""


class BIOSConnectionError(BIOSProviderError):
    """Raised when a provider cannot establish or maintain a connection."""


class BIOSPermissionError(BIOSProviderError):
    """Raised when an operation lacks the required system permissions."""


class BIOSUnsupportedFeatureError(BIOSProviderError):
    """Raised when a provider does not support a requested feature."""


class BIOSValidationError(BIOSProviderError):
    """Raised when provider or configuration validation cannot be completed."""


class BIOSFirmwareError(BIOSProviderError):
    """Raised when system firmware rejects or fails an operation."""


class BIOSTransactionError(BIOSProviderError):
    """Raised when a firmware configuration transaction fails."""


class BIOSUpdateError(BIOSFirmwareError):
    """Raised when a firmware update or rollback operation fails."""


class BIOSAuthenticationError(BIOSProviderError):
    """Raised when BIOS authentication or password verification fails."""


# =============================================================================
# Validation models
# =============================================================================


@dataclass(frozen=True, slots=True)
class ValidationError:
    """Describe a firmware configuration validation failure.

    Validation failures are returned as data rather than raised as exceptions.
    ``BIOSValidationError`` is reserved for cases where validation itself
    cannot be performed.

    Attributes:
        field:
            Stable setting or configuration field identifier.
        message:
            Human-readable description of the validation failure.
        code:
            Stable machine-readable error code.
        severity:
            Severity such as ``error``, ``warning``, or ``info``.
        current_value:
            Current invalid or unexpected value, when safe to expose.
        expected_value:
            Expected value or constraint, when applicable.
        metadata:
            Additional non-sensitive validation information.
    """

    field: str
    message: str
    code: str = "invalid"
    severity: str = "error"
    current_value: Any = None
    expected_value: Any = None
    metadata: dict[str, Any] = dataclass_field(default_factory=dict)


# =============================================================================
# Provider contract
# =============================================================================


class BIOSProvider(ABC):
    """Complete interface contract for BIOS and firmware providers."""

    # -------------------------------------------------------------------------
    # Core identity and provider metadata
    # -------------------------------------------------------------------------

    @abstractmethod
    def vendor(self) -> BIOSVendor:
        """Return the normalized hardware vendor represented by the provider."""
        raise NotImplementedError

    @abstractmethod
    def provider_name(self) -> str:
        """Return the human-readable provider implementation name."""
        raise NotImplementedError

    @abstractmethod
    def provider_version(self) -> str:
        """Return the provider implementation version."""
        raise NotImplementedError

    def supports_windows(self) -> bool:
        """Return whether this provider supports Windows hosts."""
        raise NotImplementedError

    def supports_linux(self) -> bool:
        """Return whether this provider supports Linux hosts."""
        raise NotImplementedError

    @abstractmethod
    def connect(self) -> bool:
        """Initialize the provider and connect to its firmware interface."""
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the firmware interface and release resources."""
        raise NotImplementedError

    @abstractmethod
    def is_connected(self) -> bool:
        """Return whether the provider is connected and ready."""
        raise NotImplementedError

    @abstractmethod
    def detect(self) -> bool:
        """Return whether this provider applies to the current system."""
        raise NotImplementedError

    @abstractmethod
    def refresh(self) -> bool:
        """Refresh ordinary cached firmware and system information."""
        raise NotImplementedError

    @abstractmethod
    def firmware_interface(self) -> str:
        """Return the firmware-management interface used by the provider."""
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Firmware and system information
    # -------------------------------------------------------------------------

    @abstractmethod
    def firmware_information(self) -> FirmwareInformation:
        """Return normalized firmware and system information."""
        raise NotImplementedError

    @abstractmethod
    def bios_mode(self) -> BIOSMode:
        """Return the active BIOS or firmware boot mode."""
        raise NotImplementedError

    def manufacturer(self) -> str:
        """Return the system manufacturer."""
        raise NotImplementedError

    def product_name(self) -> str:
        """Return the system product name."""
        raise NotImplementedError

    def model(self) -> str:
        """Return the system model."""
        raise NotImplementedError

    def serial_number(self) -> str:
        """Return the system serial number."""
        raise NotImplementedError

    def system_uuid(self) -> str:
        """Return the system UUID."""
        raise NotImplementedError

    def sku(self) -> str:
        """Return the system stock-keeping unit."""
        raise NotImplementedError

    def bios_vendor(self) -> str:
        """Return the firmware-reported BIOS vendor."""
        raise NotImplementedError

    def bios_version(self) -> str:
        """Return the installed BIOS version."""
        raise NotImplementedError

    def bios_release_date(self) -> date:
        """Return the installed BIOS release date."""
        raise NotImplementedError

    def embedded_controller_version(self) -> str:
        """Return the embedded-controller firmware version."""
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Capability discovery
    # -------------------------------------------------------------------------

    def supported_features(self) -> set[str]:
        """Return stable lowercase identifiers for supported features."""
        raise NotImplementedError

    def supports_feature(self, name: str) -> bool:
        """Return whether the named feature is supported."""
        raise NotImplementedError

    def supported_settings(self) -> list[str]:
        """Return stable names for BIOS settings exposed by the provider."""
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Generic BIOS settings
    # -------------------------------------------------------------------------

    def available_settings(self) -> dict[str, Any]:
        """Return all BIOS settings visible through the provider."""
        raise NotImplementedError

    def setting_exists(self, name: str) -> bool:
        """Return whether a named BIOS setting is available."""
        raise NotImplementedError

    def get_setting(self, name: str) -> Any:
        """Return the current value of a named BIOS setting."""
        raise NotImplementedError

    def set_setting(self, name: str, value: Any) -> bool:
        """Set a named BIOS setting to the supplied value."""
        raise NotImplementedError

    def reset_setting(self, name: str) -> bool:
        """Reset one BIOS setting to its firmware-defined default."""
        raise NotImplementedError

    def restore_defaults(self) -> bool:
        """Restore provider-visible BIOS settings to their defaults."""
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Boot management
    # -------------------------------------------------------------------------

    def boot_order(self) -> list[BootDevice]:
        """Return the configured persistent firmware boot order."""
        raise NotImplementedError

    def set_boot_order(self, devices: Sequence[BootDevice]) -> bool:
        """Replace the persistent boot order with the supplied devices."""
        raise NotImplementedError

    def add_boot_device(self, device: BootDevice) -> bool:
        """Add a device to the persistent firmware boot order."""
        raise NotImplementedError

    def remove_boot_device(self, device: BootDevice) -> bool:
        """Remove a device from the persistent firmware boot order."""
        raise NotImplementedError

    def restore_default_boot_order(self) -> bool:
        """Restore the vendor-defined default firmware boot order."""
        raise NotImplementedError

    def current_boot_device(self) -> BootDevice:
        """Return the device used for the current system boot."""
        raise NotImplementedError

    def next_boot_device(self) -> BootDevice | None:
        """Return the configured one-time boot device, if any."""
        raise NotImplementedError

    def set_next_boot_device(self, device: BootDevice) -> bool:
        """Set the device to use for the next boot only."""
        raise NotImplementedError

    def clear_next_boot_device(self) -> bool:
        """Clear the configured one-time boot device."""
        raise NotImplementedError

    def boot_menu_supported(self) -> bool:
        """Return whether firmware boot-menu management is supported."""
        raise NotImplementedError

    def restore_factory_defaults(self) -> bool:
        """Perform the vendor-defined complete firmware factory reset."""
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Firmware updates
    # -------------------------------------------------------------------------

    def firmware_update_supported(self) -> bool:
        """Return whether firmware update management is supported."""
        raise NotImplementedError

    def current_firmware_version(self) -> str:
        """Return the currently installed system firmware version."""
        raise NotImplementedError

    def latest_firmware_version(self) -> str | None:
        """Return the latest available firmware version, if known."""
        raise NotImplementedError

    def check_for_firmware_updates(self) -> bool:
        """Check for updates and return whether an update is available."""
        raise NotImplementedError

    def install_firmware_update(self) -> bool:
        """Install the currently applicable firmware update."""
        raise NotImplementedError

    def firmware_rollback_supported(self) -> bool:
        """Return whether installed firmware can be rolled back."""
        raise NotImplementedError

    def rollback_firmware(self) -> bool:
        """Roll back to the previous supported firmware version."""
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # BIOS password management
    # -------------------------------------------------------------------------

    def bios_password_supported(self) -> bool:
        """Return whether BIOS password management is supported."""
        raise NotImplementedError

    def bios_password_configured(self) -> bool:
        """Return whether a BIOS administrator password is configured."""
        raise NotImplementedError

    def set_bios_password(self, password: str) -> bool:
        """Set the BIOS administrator password.

        Implementations must never log, serialize, cache, or expose the
        supplied password.
        """
        raise NotImplementedError

    def clear_bios_password(self, password: str) -> bool:
        """Clear the BIOS password after verifying the current password.

        Implementations must never log, serialize, cache, or expose the
        supplied password.
        """
        raise NotImplementedError

    def verify_bios_password(self, password: str) -> bool:
        """Return whether the supplied BIOS password is valid.

        Implementations must never log, serialize, cache, or expose the
        supplied password.
        """
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Virtualization, IOMMU, and SR-IOV
    # -------------------------------------------------------------------------

    def virtualization_supported(self) -> bool:
        """Return whether hardware virtualization is supported."""
        raise NotImplementedError

    def virtualization_enabled(self) -> bool:
        """Return whether hardware virtualization is enabled."""
        raise NotImplementedError

    def enable_virtualization(self) -> bool:
        """Enable hardware virtualization."""
        raise NotImplementedError

    def disable_virtualization(self) -> bool:
        """Disable hardware virtualization."""
        raise NotImplementedError

    def iommu_supported(self) -> bool:
        """Return whether an IOMMU is supported."""
        raise NotImplementedError

    def iommu_enabled(self) -> bool:
        """Return whether the IOMMU is enabled."""
        raise NotImplementedError

    def enable_iommu(self) -> bool:
        """Enable the IOMMU."""
        raise NotImplementedError

    def disable_iommu(self) -> bool:
        """Disable the IOMMU."""
        raise NotImplementedError

    def sriov_supported(self) -> bool:
        """Return whether SR-IOV is supported."""
        raise NotImplementedError

    def sriov_enabled(self) -> bool:
        """Return whether SR-IOV is enabled."""
        raise NotImplementedError

    def enable_sriov(self) -> bool:
        """Enable SR-IOV."""
        raise NotImplementedError

    def disable_sriov(self) -> bool:
        """Disable SR-IOV."""
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # TPM, Secure Boot, and platform security
    # -------------------------------------------------------------------------

    def tpm_supported(self) -> bool:
        """Return whether a TPM is supported."""
        raise NotImplementedError

    def tpm_enabled(self) -> bool:
        """Return whether the TPM is enabled."""
        raise NotImplementedError

    def enable_tpm(self) -> bool:
        """Enable the TPM."""
        raise NotImplementedError

    def disable_tpm(self) -> bool:
        """Disable the TPM."""
        raise NotImplementedError

    def secure_boot_supported(self) -> bool:
        """Return whether Secure Boot is supported."""
        raise NotImplementedError

    def secure_boot_enabled(self) -> bool:
        """Return whether Secure Boot is enabled."""
        raise NotImplementedError

    def enable_secure_boot(self) -> bool:
        """Enable Secure Boot."""
        raise NotImplementedError

    def disable_secure_boot(self) -> bool:
        """Disable Secure Boot."""
        raise NotImplementedError

    def secure_boot_keys_installed(self) -> bool:
        """Return whether standard Secure Boot keys are installed."""
        raise NotImplementedError

    def restore_secure_boot_keys(self) -> bool:
        """Restore the platform's standard Secure Boot keys."""
        raise NotImplementedError

    def custom_secure_boot_keys_supported(self) -> bool:
        """Return whether custom Secure Boot key management is supported."""
        raise NotImplementedError

    def intel_boot_guard_supported(self) -> bool:
        """Return whether Intel Boot Guard is supported."""
        raise NotImplementedError

    def intel_boot_guard_enabled(self) -> bool:
        """Return whether Intel Boot Guard is enabled."""
        raise NotImplementedError

    def amd_platform_security_supported(self) -> bool:
        """Return whether AMD platform security is supported."""
        raise NotImplementedError

    def amd_platform_security_enabled(self) -> bool:
        """Return whether AMD platform security is enabled."""
        raise NotImplementedError

    def measured_boot_supported(self) -> bool:
        """Return whether measured boot is supported."""
        raise NotImplementedError

    def trusted_execution_supported(self) -> bool:
        """Return whether trusted execution is supported."""
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Firmware variables
    # -------------------------------------------------------------------------

    def firmware_variables_supported(self) -> bool:
        """Return whether firmware variable management is supported."""
        raise NotImplementedError

    def read_variable(self, name: str) -> bytes:
        """Read and return a named firmware variable."""
        raise NotImplementedError

    def write_variable(self, name: str, value: bytes) -> bool:
        """Write a named firmware variable."""
        raise NotImplementedError

    def delete_variable(self, name: str) -> bool:
        """Delete a named firmware variable."""
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Wake features
    # -------------------------------------------------------------------------

    def wake_on_lan_supported(self) -> bool:
        """Return whether Wake-on-LAN is supported."""
        raise NotImplementedError

    def is_wake_on_lan_enabled(self) -> bool:
        """Return whether Wake-on-LAN is enabled."""
        raise NotImplementedError

    def enable_wake_on_lan(self) -> bool:
        """Enable Wake-on-LAN."""
        raise NotImplementedError

    def disable_wake_on_lan(self) -> bool:
        """Disable Wake-on-LAN."""
        raise NotImplementedError

    def rtc_wake_supported(self) -> bool:
        """Return whether RTC wake is supported."""
        raise NotImplementedError

    def is_rtc_wake_enabled(self) -> bool:
        """Return whether RTC wake is enabled."""
        raise NotImplementedError

    def enable_rtc_wake(self) -> bool:
        """Enable RTC wake."""
        raise NotImplementedError

    def disable_rtc_wake(self) -> bool:
        """Disable RTC wake."""
        raise NotImplementedError

    def usb_wake_supported(self) -> bool:
        """Return whether USB wake is supported."""
        raise NotImplementedError

    def is_usb_wake_enabled(self) -> bool:
        """Return whether USB wake is enabled."""
        raise NotImplementedError

    def enable_usb_wake(self) -> bool:
        """Enable USB wake."""
        raise NotImplementedError

    def disable_usb_wake(self) -> bool:
        """Disable USB wake."""
        raise NotImplementedError

    def keyboard_wake_supported(self) -> bool:
        """Return whether keyboard wake is supported."""
        raise NotImplementedError

    def is_keyboard_wake_enabled(self) -> bool:
        """Return whether keyboard wake is enabled."""
        raise NotImplementedError

    def enable_keyboard_wake(self) -> bool:
        """Enable keyboard wake."""
        raise NotImplementedError

    def disable_keyboard_wake(self) -> bool:
        """Disable keyboard wake."""
        raise NotImplementedError

    def mouse_wake_supported(self) -> bool:
        """Return whether mouse wake is supported."""
        raise NotImplementedError

    def is_mouse_wake_enabled(self) -> bool:
        """Return whether mouse wake is enabled."""
        raise NotImplementedError

    def enable_mouse_wake(self) -> bool:
        """Enable mouse wake."""
        raise NotImplementedError

    def disable_mouse_wake(self) -> bool:
        """Disable mouse wake."""
        raise NotImplementedError

    def pcie_wake_supported(self) -> bool:
        """Return whether PCIe wake is supported."""
        raise NotImplementedError

    def is_pcie_wake_enabled(self) -> bool:
        """Return whether PCIe wake is enabled."""
        raise NotImplementedError

    def enable_pcie_wake(self) -> bool:
        """Enable PCIe wake."""
        raise NotImplementedError

    def disable_pcie_wake(self) -> bool:
        """Disable PCIe wake."""
        raise NotImplementedError

    def lid_wake_supported(self) -> bool:
        """Return whether lid-open wake is supported."""
        raise NotImplementedError

    def is_lid_wake_enabled(self) -> bool:
        """Return whether lid-open wake is enabled."""
        raise NotImplementedError

    def enable_lid_wake(self) -> bool:
        """Enable lid-open wake."""
        raise NotImplementedError

    def disable_lid_wake(self) -> bool:
        """Disable lid-open wake."""
        raise NotImplementedError

    def alarm_wake_supported(self) -> bool:
        """Return whether scheduled alarm wake is supported."""
        raise NotImplementedError

    def is_alarm_wake_enabled(self) -> bool:
        """Return whether scheduled alarm wake is enabled."""
        raise NotImplementedError

    def enable_alarm_wake(self) -> bool:
        """Enable scheduled alarm wake."""
        raise NotImplementedError

    def disable_alarm_wake(self) -> bool:
        """Disable scheduled alarm wake."""
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Battery management
    # -------------------------------------------------------------------------

    def battery_present(self) -> bool:
        """Return whether a battery is present in the system."""
        raise NotImplementedError

    def battery_charge_limit_supported(self) -> bool:
        """Return whether battery charge-limit management is supported."""
        raise NotImplementedError

    def get_charge_limit(self) -> int:
        """Return the configured battery charge limit as a percentage."""
        raise NotImplementedError

    def set_charge_limit(self, percent: int) -> bool:
        """Set the battery charge limit as a percentage.

        Providers should validate both the range from 0 through 100 and any
        narrower range imposed by the hardware vendor.
        """
        raise NotImplementedError

    def battery_health_mode_supported(self) -> bool:
        """Return whether battery health-mode management is supported."""
        raise NotImplementedError

    def get_battery_health_mode(self) -> str:
        """Return the active battery health mode."""
        raise NotImplementedError

    def set_battery_health_mode(self, mode: str) -> bool:
        """Set the active battery health mode."""
        raise NotImplementedError

    def battery_calibration_supported(self) -> bool:
        """Return whether battery calibration is supported."""
        raise NotImplementedError

    def start_battery_calibration(self) -> bool:
        """Start battery calibration."""
        raise NotImplementedError

    def stop_battery_calibration(self) -> bool:
        """Stop an active battery calibration operation."""
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Power management
    # -------------------------------------------------------------------------

    def supports_power_profiles(self) -> bool:
        """Return whether firmware power profiles are supported."""
        raise NotImplementedError

    def get_power_profile(self) -> str:
        """Return the active firmware power profile."""
        raise NotImplementedError

    def set_power_profile(self, profile: str) -> bool:
        """Set the active firmware power profile."""
        raise NotImplementedError

    def supports_fast_boot(self) -> bool:
        """Return whether firmware fast boot is supported."""
        raise NotImplementedError

    def fast_boot_enabled(self) -> bool:
        """Return whether firmware fast boot is enabled."""
        raise NotImplementedError

    def enable_fast_boot(self) -> bool:
        """Enable firmware fast boot."""
        raise NotImplementedError

    def disable_fast_boot(self) -> bool:
        """Disable firmware fast boot."""
        raise NotImplementedError

    def restore_power_on_ac_supported(self) -> bool:
        """Return whether restore-on-AC-power management is supported."""
        raise NotImplementedError

    def restore_power_on_ac_enabled(self) -> bool:
        """Return whether automatic power restoration after AC loss is enabled."""
        raise NotImplementedError

    def enable_restore_power_on_ac(self) -> bool:
        """Enable automatic power restoration when AC power returns."""
        raise NotImplementedError

    def disable_restore_power_on_ac(self) -> bool:
        """Disable automatic power restoration when AC power returns."""
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Transaction management
    # -------------------------------------------------------------------------

    def transactions_supported(self) -> bool:
        """Return whether atomic firmware transactions are supported.

        Providers must return ``True`` only when all staged changes can be
        committed together or reliably discarded together. Best-effort
        staging must not be presented as an atomic transaction.
        """
        raise NotImplementedError

    def begin_transaction(self) -> bool:
        """Begin a firmware configuration transaction.

        Providers should reject nested transactions unless the underlying
        firmware-management interface explicitly supports them.
        """
        raise NotImplementedError

    def commit_transaction(self) -> bool:
        """Atomically commit all changes in the active transaction."""
        raise NotImplementedError

    def rollback_transaction(self) -> bool:
        """Discard all changes in the active configuration transaction.

        This is distinct from ``rollback_firmware()``, which rolls back the
        installed firmware image or version.
        """
        raise NotImplementedError

    def transaction_active(self) -> bool:
        """Return whether a firmware configuration transaction is active."""
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Firmware synchronization and pending changes
    # -------------------------------------------------------------------------

    def sync(self) -> bool:
        """Reconcile provider state with the underlying firmware interface."""
        raise NotImplementedError

    def sync_firmware(self) -> bool:
        """Synchronize staged configuration with the system firmware.

        This method may stage or transfer changes to firmware without implying
        atomic transaction semantics.
        """
        raise NotImplementedError

    def commit_changes(self) -> bool:
        """Apply nontransactional changes staged by the provider.

        This operation must not be represented as atomic unless
        ``transactions_supported()`` returns ``True`` and an actual
        transaction is used.
        """
        raise NotImplementedError

    def reload(self) -> bool:
        """Discard all cached state and perform a complete firmware reload."""
        raise NotImplementedError

    def reload_configuration(self) -> bool:
        """Discard and reload configurable firmware settings."""
        raise NotImplementedError

    def invalidate_cache(self) -> None:
        """Mark all cached provider information as stale.

        This operation should not need to perform immediate firmware I/O.
        """
        raise NotImplementedError

    def pending_reboot_required(self) -> bool:
        """Return whether applied or staged changes require a system reboot."""
        raise NotImplementedError

    def pending_changes(self) -> bool:
        """Return whether the provider currently has staged changes."""
        raise NotImplementedError

    def clear_pending_changes(self) -> bool:
        """Discard nontransactional changes staged by the provider."""
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Operation status and error reporting
    # -------------------------------------------------------------------------

    def last_error(self) -> str | None:
        """Return a sanitized description of the last provider error.

        The result must not expose passwords, credentials, key material,
        firmware-variable contents, or other sensitive values.
        """
        raise NotImplementedError

    def last_operation(self) -> str:
        """Return the stable name of the last attempted provider operation.

        The result should contain only an operation identifier, such as
        ``set_boot_order``. It must not contain arguments or sensitive values.
        """
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Validation, reporting, and diagnostics
    # -------------------------------------------------------------------------

    def validate(self) -> bool:
        """Validate provider operation and firmware-interface access."""
        raise NotImplementedError

    def validate_configuration(self) -> list[ValidationError]:
        """Return validation failures for the current configuration.

        An empty list indicates that no configuration validation failures were
        found. ``BIOSValidationError`` should be raised only when validation
        itself cannot be completed.
        """
        raise NotImplementedError

    def summary(self) -> dict[str, Any]:
        """Return a concise, non-sensitive provider and firmware summary."""
        raise NotImplementedError

    def report(self) -> dict[str, Any]:
        """Return a detailed, non-sensitive provider and firmware report."""
        raise NotImplementedError

    def health(self) -> dict[str, Any]:
        """Return provider, connection, and firmware health information."""
        raise NotImplementedError

    def diagnostics(self) -> dict[str, Any]:
        """Return sanitized provider diagnostic information.

        Diagnostics may include connection state, interface availability,
        command availability, and non-sensitive error details. They must not
        expose credentials, passwords, private key material, or secret
        firmware-variable data.
        """
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Serialization and export
    # -------------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize non-sensitive provider state to a dictionary."""
        raise NotImplementedError

    def to_json(self) -> str:
        """Serialize non-sensitive provider state to JSON."""
        raise NotImplementedError

    def export(self) -> dict[str, Any]:
        """Export provider and firmware information as structured data."""
        raise NotImplementedError

    def export_yaml(self) -> str:
        """Export non-sensitive provider information as YAML.

        Implementations may use an optional YAML library. The base interface
        does not require a specific serialization dependency.
        """
        raise NotImplementedError

    def export_markdown(self) -> str:
        """Export non-sensitive provider information as Markdown."""
        raise NotImplementedError
    
    # -------------------------------------------------------------------------
    # Context-manager lifecycle
    # -------------------------------------------------------------------------

    def __enter__(self) -> Self:
        """Connect the provider and return it as a context manager.

        If the provider is already connected, no additional connection
        attempt is made.

        Raises:
            BIOSConnectionError:
                If the provider cannot establish a connection.
        """
        if not self.is_connected() and not self.connect():
            raise BIOSConnectionError(
                f"Unable to connect BIOS provider {self.provider_name()!r}."
            )

        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the provider when leaving a context-manager block.

        Exceptions raised inside the managed block are not suppressed.
        """
        del exception_type, exception, traceback
        self.close()

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def close(self) -> None:
        """Release resources and close the provider.

        Implementations should make repeated calls safe. This method may
        delegate to ``disconnect()`` when appropriate.
        """
        raise NotImplementedError


__all__ = [
    "BIOSAuthenticationError",
    "BIOSConnectionError",
    "BIOSFirmwareError",
    "BIOSPermissionError",
    "BIOSProvider",
    "BIOSProviderError",
    "BIOSTransactionError",
    "BIOSUnsupportedFeatureError",
    "BIOSUpdateError",
    "BIOSValidationError",
    "ValidationError",
]

