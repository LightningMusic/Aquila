"""
Project Aquila
=============

Phase One -> Phase Two Boot Handoff

Implements REQ-PROV-016 ("reboot the system upon successful
completion of operating system installation" -- read here as
"handoff", see the note below) and REQ-PROV-017 ("validate deployment
media integrity before beginning installation").

Two-phase-boot architecture
------------------------------
Aquila's deployment media (``common.constants.deployment
.USB_PHASE_ONE_DIRECTORY`` / ``USB_PHASE_TWO_DIRECTORY``, "phase1" /
"phase2") already encodes a two-phase design this module makes
concrete: Phase One (Inspection, Recovery, Preparation, and this
Provisioning Engine) is a WinPE-hosted Aquila Technician Console --
everything built so far in this codebase is WMI/Python code that only
runs on Windows. Proxmox VE's own installer is a Debian-based Linux
environment; it cannot run from within WinPE. Phase Two is therefore a
*separate* boot session into Proxmox VE's own official installer
(embedded on the same deployment USB, prepared with
``proxmox-auto-install-assistant prepare-iso`` at Build-System/
USB-release time -- REQ-PROV-021's "unmodified, official Proxmox VE
installation"), triggered by this module via a one-time Windows boot
sequence change and a reboot, not run in-process.

What this module does and does not own
------------------------------------------
* Verifies the embedded Phase Two boot image has not been corrupted
  (REQ-PROV-017), against a checksum manifest in the standard
  ``sha256sum`` text format (``<hex-digest>  <relative-path>`` per
  line) -- a well-known, documented convention, not an
  Aquila-invented one.
* Triggers the one-time boot handoff via ``bcdedit /bootsequence
  {boot-entry-id} /addfirst`` (confirmed via Microsoft's own
  documentation, learn.microsoft.com/windows-hardware/drivers/devtest/
  bcdedit--bootsequence: "similar to /displayorder except it is used
  only the next time the computer starts. Afterwards, the computer
  reverts to the original display order.") -- the correct, minimal,
  officially documented mechanism for exactly this one-time-boot
  requirement.
* Triggers the reboot itself (REQ-PROV-016).

This module deliberately does NOT create the target BCD boot entry
(the identifier ``boot_entry_id`` names). Creating a real-mode BCD
entry for an embedded secondary boot image is lower-level BCD/
bootsector-entry-creation machinery this session's research could not
independently confirm the precise mechanics of against a primary
source, and GP-001 ("Automation shall never perform irreversible
actions without explicit operator authorization") together with this
project's honest-degradation convention (see
``preparation.sanitizer``'s ATA/NVMe decision) means this module will
not fabricate that mechanism. Registering the boot entry belongs to
the not-yet-built Build System subsystem, which already owns producing
the USB release artifact (SRS Section 9.15) and is the natural place
to create that entry once, at USB-build time -- this module only
*consumes* a pre-configured boot-entry identifier and invokes the
documented, supported command against it.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from common.constants.logging import PROVISIONING_LOGGER
from common.exceptions.deployment import DeploymentRebootError
from hardware import is_windows

logger = logging.getLogger(PROVISIONING_LOGGER)

#: Default REQ-PROV-017 checksum manifest filename, expected at the
#: root of the Phase Two boot-media directory in standard
#: ``sha256sum`` text format.
DEFAULT_MANIFEST_FILENAME = "manifest.sha256"


class BootSequenceError(DeploymentRebootError):
    """Raised when the one-time boot-sequence handoff cannot be set."""


class RebootTriggerError(DeploymentRebootError):
    """Raised when the reboot command itself fails."""


@dataclass(slots=True, frozen=True)
class MediaIntegrityResult:
    """The outcome of one REQ-PROV-017 boot-media integrity check."""

    verified: bool
    detail: str
    checked_files: tuple[str, ...] = ()
    failed_files: tuple[str, ...] = ()
    missing_files: tuple[str, ...] = ()


class BootMediaIntegrityChecker:
    """
    REQ-PROV-017: verifies every file listed in a checksum manifest
    under the Phase Two boot-media directory matches its recorded
    SHA-256 digest.
    """

    def verify(
        self,
        phase_two_directory: Path,
        *,
        manifest_filename: str = DEFAULT_MANIFEST_FILENAME,
    ) -> MediaIntegrityResult:
        manifest_path = phase_two_directory / manifest_filename
        if not manifest_path.is_file():
            detail = (
                f"No integrity manifest found at {manifest_path} -- "
                "REQ-PROV-017 requires validating deployment media "
                "integrity before beginning installation, and cannot "
                "do so without a manifest."
            )
            logger.error(detail)
            return MediaIntegrityResult(verified=False, detail=detail)

        entries = self._parse_manifest(manifest_path)
        if not entries:
            detail = (
                f"Integrity manifest at {manifest_path} contained no "
                "entries."
            )
            logger.error(detail)
            return MediaIntegrityResult(verified=False, detail=detail)

        checked: list[str] = []
        failed: list[str] = []
        missing: list[str] = []

        for relative_path, expected_digest in entries:
            target = phase_two_directory / relative_path
            if not target.is_file():
                missing.append(relative_path)
                continue

            actual_digest = self._sha256_of(target)
            checked.append(relative_path)
            if actual_digest.lower() != expected_digest.lower():
                failed.append(relative_path)

        verified = not failed and not missing
        if verified:
            detail = f"{len(checked)} file(s) verified against {manifest_path}."
            logger.info(detail)
        else:
            detail = (
                "Boot media integrity check failed -- "
                f"{len(failed)} mismatched, {len(missing)} missing "
                f"(of {len(entries)} manifest entries)."
            )
            logger.error(detail)

        return MediaIntegrityResult(
            verified=verified,
            detail=detail,
            checked_files=tuple(checked),
            failed_files=tuple(failed),
            missing_files=tuple(missing),
        )

    @staticmethod
    def _parse_manifest(manifest_path: Path) -> list[tuple[str, str]]:
        entries: list[tuple[str, str]] = []
        text = manifest_path.read_text(encoding="utf-8", errors="replace")
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            # Standard `sha256sum` output format: "<digest>  <path>" or
            # "<digest> *<path>" for binary mode.
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            digest, path = parts
            path = path.lstrip("*").strip()
            if not path:
                continue
            entries.append((path, digest))
        return entries

    @staticmethod
    def _sha256_of(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


class BootSequenceSetter(Protocol):
    """
    Sets a one-time next-boot entry.

    Kept as its own narrow Protocol -- like
    ``preparation.sanitizer.WmiMethodCaller`` -- both because it
    invokes an external, system-mutating command (never something a
    functional test should run for real) and because it is dangerous
    by construction: it changes what the machine boots into next.
    """

    def set_next_boot(self, boot_entry_id: str) -> None:
        """Raise ``BootSequenceError`` if the command fails."""
        ...


class _DefaultBootSequenceSetter:
    """Real ``bcdedit /bootsequence`` invocation."""

    def set_next_boot(self, boot_entry_id: str) -> None:
        if not is_windows():
            raise BootSequenceError(
                "Setting a one-time boot sequence requires Windows "
                "(bcdedit); the current platform is not supported."
            )

        result = subprocess.run(
            ["bcdedit", "/bootsequence", boot_entry_id, "/addfirst"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            check=False,
        )
        if result.returncode != 0:
            raise BootSequenceError(
                f"'bcdedit /bootsequence {boot_entry_id} /addfirst' "
                f"failed (exit {result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )


class Rebooter(Protocol):
    """Triggers an immediate system reboot. Dangerous by construction."""

    def reboot(self) -> None:
        """Raise ``RebootTriggerError`` if the command fails."""
        ...


class _DefaultRebooter:
    """Real ``shutdown /r`` invocation."""

    def reboot(self) -> None:
        if not is_windows():
            raise RebootTriggerError(
                "Rebooting requires Windows (shutdown /r); the current "
                "platform is not supported."
            )

        result = subprocess.run(
            ["shutdown", "/r", "/t", "0"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            check=False,
        )
        if result.returncode != 0:
            raise RebootTriggerError(
                f"'shutdown /r /t 0' failed (exit {result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )


class PhaseTwoHandoff:
    """
    Verifies Phase Two boot media (REQ-PROV-017) and, once
    provisioning is otherwise ready, triggers the one-time boot
    handoff and reboot into it (REQ-PROV-016).
    """

    def __init__(
        self,
        *,
        integrity_checker: BootMediaIntegrityChecker | None = None,
        boot_sequence_setter: BootSequenceSetter | None = None,
        rebooter: Rebooter | None = None,
    ) -> None:
        self._integrity_checker = integrity_checker or BootMediaIntegrityChecker()
        self._boot_sequence_setter = (
            boot_sequence_setter or _DefaultBootSequenceSetter()
        )
        self._rebooter = rebooter or _DefaultRebooter()

    def verify_media(
        self,
        phase_two_directory: Path,
        *,
        manifest_filename: str = DEFAULT_MANIFEST_FILENAME,
    ) -> MediaIntegrityResult:
        return self._integrity_checker.verify(
            phase_two_directory, manifest_filename=manifest_filename
        )

    def handoff(self, boot_entry_id: str) -> None:
        """
        Set the one-time next-boot entry and reboot.

        Raises:
            BootSequenceError: If ``boot_entry_id`` is empty, or the
                boot entry could not be set.
            RebootTriggerError: If the reboot command itself fails.
        """

        if not boot_entry_id.strip():
            raise BootSequenceError(
                "No Phase Two boot entry id was configured -- the "
                "Build System is responsible for creating this BCD "
                "entry at USB-build time and supplying its identifier."
            )

        logger.info("Setting one-time boot sequence to entry %s.", boot_entry_id)
        self._boot_sequence_setter.set_next_boot(boot_entry_id)

        logger.info("Rebooting to begin Phase Two (Proxmox VE installation).")
        self._rebooter.reboot()


__all__ = [
    "DEFAULT_MANIFEST_FILENAME",
    "BootMediaIntegrityChecker",
    "BootSequenceError",
    "BootSequenceSetter",
    "MediaIntegrityResult",
    "PhaseTwoHandoff",
    "RebootTriggerError",
    "Rebooter",
]
