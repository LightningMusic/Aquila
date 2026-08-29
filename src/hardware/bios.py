"""
Project Aquila
=============

BIOS/Firmware Detection

Implements REQ-INS-014 (detect UEFI firmware), REQ-INS-015 (determine
Secure Boot status), REQ-INS-016 through REQ-INS-019 (system
manufacturer/model/serial/BIOS version identity), REQ-INS-022 (detect
lid switch support on portable systems), and REQ-INS-023 (detect
supported firmware management interfaces).

This detector does not re-implement firmware identity or TPM
detection -- ``bios.detection`` (the ``BIOSDetection``/``BIOSProvider``
machinery) already collects both as part of selecting the correct
vendor provider for the system, and is asked directly here rather than
re-derived (see ``models.hardware.bios``'s docstring). It supplies
only what that subsystem does not already cover: Secure Boot state and
lid-switch presence, neither of which any current ``BIOSProvider``
implements (confirmed by inspection: ``secure_boot_supported()``/
``secure_boot_enabled()`` fall back to ``DefaultProvider``'s honest
``False`` on every registered provider, and no provider queries for a
lid device at all).

Secure Boot detection
----------------------
The documented, Microsoft-supported mechanism is the
``Confirm-SecureBootUEFI`` PowerShell cmdlet (confirmed via Microsoft
Learn: used throughout Microsoft's own Secure Boot troubleshooting
documentation). It raises "Cmdlet not supported on this platform" on
Legacy BIOS systems -- exactly the case where Secure Boot is not
applicable -- which this detector maps to ``None`` (REQ-INS-015's
"could not be determined" case), not ``False``. If the cmdlet itself
is unavailable for any other reason, this falls back to the registry
value Microsoft's own Hardware Lab Kit test documentation reads
directly (``HKLM\\SYSTEM\\CurrentControlSet\\Control\\SecureBoot\\State\\
UEFISecureBootEnabled``) -- informally documented (a test-reference
page, not a guaranteed-stable public API), so it is only a fallback,
never the primary source.

Lid switch detection
---------------------
``PNP0C0D`` is the ACPI specification's defined Plug-and-Play hardware
ID for the lid device (confirmed directly against the ACPI 6.5
specification, uefi.org). Presence of a ``Win32_PnPEntity`` whose
``DeviceID`` contains this ACPI ID is a reliable, standards-based
signal that a lid switch exists -- independent of vendor.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import platform
from typing import Optional

from bios.models import FirmwareInformation, TPMState
from common.constants.logging import HARDWARE_LOGGER
from models.hardware import BIOSInspectionInfo

from . import is_windows, query_wmi_safe, run_process

# Logs through the dedicated "aquila.hardware" logger -- see
# hardware.battery's identical fix for why logging.getLogger(__name__)
# is wrong here.
logger = logging.getLogger(HARDWARE_LOGGER)

_CIMV2_NAMESPACE = r"root\cimv2"
_LID_DEVICE_QUERY = (
    "SELECT DeviceID FROM Win32_PnPEntity WHERE DeviceID LIKE '%PNP0C0D%'"
)

_GENERIC_PROVIDER_CLASS_NAMES = {"GenericUEFIProvider", "UnknownProvider"}


class BIOSDetector:
    """Detects firmware/BIOS facts not already covered by ``bios.detection``."""

    def detect(self) -> BIOSInspectionInfo:
        """
        Return a ``BIOSInspectionInfo`` record for the target system.

        Firmware identity and TPM state are delegated to the active
        ``bios`` provider (already selected and connected by
        ``bios.detection``); Secure Boot and lid-switch state are
        detected directly here.
        """

        from bios.detection import provider as active_provider

        try:
            selected_provider = active_provider()
        except Exception as exc:
            logger.warning("BIOS provider selection failed: %s", exc)
            return BIOSInspectionInfo()

        try:
            firmware = selected_provider.firmware_information()
        except Exception as exc:
            logger.warning("Firmware information collection failed: %s", exc)
            firmware = None

        tpm = self._tpm_state(selected_provider)

        return BIOSInspectionInfo(
            firmware=firmware if firmware is not None else FirmwareInformation(),
            tpm=tpm,
            secure_boot_enabled=self._detect_secure_boot(),
            lid_switch_present=self._detect_lid_switch(),
            management_interface_detected=self._management_interface(selected_provider),
        )

    @staticmethod
    def _tpm_state(selected_provider: object) -> TPMState:
        """
        Return TPM state from the active provider, preferring its
        richer ``tpm_state()`` extension (implemented by
        ``GenericUEFIProvider``, and any vendor provider that chooses
        to override it) and falling back to the base
        ``tpm_supported()``/``tpm_enabled()`` contract every provider
        implements, honestly, when the richer method is unavailable.
        """

        tpm_state_method = getattr(selected_provider, "tpm_state", None)
        if callable(tpm_state_method):
            try:
                result = tpm_state_method()
                if isinstance(result, TPMState):
                    return result
            except Exception as exc:
                logger.debug("Provider tpm_state() failed: %s", exc)

        try:
            present = bool(selected_provider.tpm_supported())  # type: ignore[attr-defined]
            enabled = bool(selected_provider.tpm_enabled()) if present else False  # type: ignore[attr-defined]
            return TPMState(present=present, enabled=enabled)
        except Exception as exc:
            logger.debug("Provider tpm_supported()/tpm_enabled() failed: %s", exc)
            return TPMState()

    @staticmethod
    def _management_interface(selected_provider: object) -> str:
        provider_class_name = type(selected_provider).__name__
        if provider_class_name in _GENERIC_PROVIDER_CLASS_NAMES:
            # No vendor-specific settings interface exists by
            # definition for these two fallback providers (see
            # ``bios.providers.generic_uefi``'s module docstring).
            return ""

        try:
            provider_name = str(selected_provider.provider_name())  # type: ignore[attr-defined]
        except Exception:
            return provider_class_name

        return provider_name

    @staticmethod
    def _detect_secure_boot() -> Optional[bool]:
        """
        Return Secure Boot state, or ``None`` when it cannot be
        determined (including "not applicable" -- Legacy BIOS systems
        have no Secure Boot state at all).
        """

        if not is_windows():
            return None

        code, stdout, stderr = run_process(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Confirm-SecureBootUEFI",
            ],
            timeout=15.0,
        )

        normalized_stdout = stdout.strip().lower()
        if code == 0 and normalized_stdout in ("true", "false"):
            return normalized_stdout == "true"

        # "Cmdlet not supported on this platform" is the documented
        # response on Legacy BIOS systems, and any other PowerShell
        # failure (missing powershell.exe, access restrictions) still
        # honestly falls through to the registry fallback below rather
        # than reporting a guessed state.
        logger.debug(
            "Confirm-SecureBootUEFI did not return a usable result "
            "(exit %s): %s",
            code,
            stderr.strip() or normalized_stdout,
        )

        return BIOSDetector._detect_secure_boot_from_registry()

    @staticmethod
    def _detect_secure_boot_from_registry() -> Optional[bool]:
        if platform.system() != "Windows":
            return None

        try:
            import winreg  # Windows-only stdlib module; imported lazily so this module still imports cleanly on non-Windows development/test platforms.
        except ImportError:
            return None

        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\SecureBoot\State",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "UEFISecureBootEnabled")
                return bool(int(value))
        except FileNotFoundError:
            # The SecureBoot\State key tree does not exist at all on
            # Legacy BIOS systems -- honestly "not applicable", not a
            # failure.
            return None
        except (OSError, ValueError) as exc:
            logger.debug("Secure Boot registry read failed: %s", exc)
            return None

    @staticmethod
    def _detect_lid_switch() -> Optional[bool]:
        """
        Return whether a lid switch (ACPI ``PNP0C0D`` device) is
        present. Only meaningful on portable systems; ``None`` is
        returned -- not ``False`` -- on any non-Windows platform or
        query failure, since absence-of-evidence is not evidence of
        absence for a query that simply could not run.
        """

        if not is_windows():
            return None

        # query_wmi_safe() already converts any backend failure to an
        # empty result, so an empty list here is indistinguishable
        # from "query ran but found nothing" -- both honestly resolve
        # to "no lid device confirmed" rather than a fabricated
        # affirmative.
        rows = query_wmi_safe(_CIMV2_NAMESPACE, _LID_DEVICE_QUERY)
        return bool(rows)


__all__ = ["BIOSDetector"]
