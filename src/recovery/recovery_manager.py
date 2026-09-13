"""
Project Aquila
=============

Recovery Manager

Central orchestrator for the Recovery Engine (SRS Section 10.4,
REQ-REC-001 through REQ-REC-026). Coordinates
``recovery.browser.VolumeBrowser`` (volume discovery -- exposed for
the Technician Console to drive interactive browsing/selection, not
called from here), ``recovery.copier.RecoveryCopier`` (REQ-REC-006
through -011/018-020/023/025), and ``recovery.verifier.RecoveryVerifier``
(REQ-REC-012), assembling their results into one
``recovery.report.RecoverySummary`` (REQ-REC-014).

Follows the exact ``ConfigurationManager``/``LogManager``/
``InspectionManager`` Manager/Service pattern: ``Service`` lifecycle,
``TYPE_CHECKING``-only ``EventBus`` import with a runtime try/except +
``_NullEvent`` fallback, best-effort ``_publish()``, and logging
through the dedicated ``aquila.recovery`` logger.

Why ``run()`` requires a ``HardwareInspectionReport``
--------------------------------------------------------
REQ-REC-001 ("The Recovery Engine shall not begin unless the
Inspection Engine has completed successfully") is enforced
structurally, not by a separate boolean flag: the only way a caller
can obtain a ``HardwareInspectionReport`` at all is from
``inspection.inspector.InspectionManager.run()``, so requiring one as
a parameter *is* the REQ-REC-001 check. It doubles as real, useful
data -- ``inspection_report.storage.data`` (a ``StorageInventory``) is
exactly what ``VolumeBrowser.discover_volumes()`` needs to flag which
volumes sit on Aquila's own boot media, reusing an already-completed
detection pass instead of re-querying WMI for the same facts.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from common.constants.logging import RECOVERY_LOGGER
from common.exceptions.recovery import RecoveryValidationError
from inspection.report import HardwareInspectionReport

from .browser import RecoveryVolume, VolumeBrowser
from .copier import ProgressCallback, RecoveryCopier
from .report import RecoverySummary
from .verifier import RecoveryVerifier, VerificationOutcome

if TYPE_CHECKING:
    # Imported only for type annotations -- this module never
    # constructs an EventBus itself, the caller owns it and passes one
    # in (see inspection.inspector.InspectionManager's identical
    # pattern for why this stays a TYPE_CHECKING-only import).
    from common.events.bus import EventBus

try:
    from common.events.types.deployment import (
        RecoveryCompletedEvent,
        RecoveryStartedEvent,
    )
except ImportError:  # pragma: no cover - event system is optional

    class _NullEvent:
        """
        Fallback used only if ``common.events`` cannot be imported --
        see ``inspection.inspector``'s identical ``_NullEvent`` for
        the full rationale. ``_publish`` never actually delivers one
        of these.
        """

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

    RecoveryCompletedEvent = _NullEvent
    RecoveryStartedEvent = _NullEvent

#: Logs through the dedicated "aquila.recovery" logger -- LogManager
#: only attaches a file handler to the exact names in
#: common.constants.logging, not to logging.getLogger(__name__).
logger = logging.getLogger(RECOVERY_LOGGER)


class RecoveryManager:
    """
    Runs the Recovery Engine's device-retirement recovery phase
    (SRS Appendix B, Workflow A) and reports the result.
    """

    def __init__(
        self,
        event_bus: Optional["EventBus"] = None,
        *,
        volume_browser: VolumeBrowser | None = None,
        copier: RecoveryCopier | None = None,
        verifier: RecoveryVerifier | None = None,
    ) -> None:
        self._event_bus: Optional["EventBus"] = event_bus

        self._volume_browser = volume_browser or VolumeBrowser()
        self._copier = copier or RecoveryCopier()
        self._verifier = verifier or RecoveryVerifier()

        self._last_summary: RecoverySummary | None = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Service lifecycle (interfaces.service.Service)
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """
        Mark the Recovery Engine ready.

        Like ``InspectionManager``, there is no state to load ahead of
        time -- volume discovery and copying both act on live target-
        system state at the moment ``run()`` is called. Idempotent.
        """

        self._initialized = True

    def shutdown(self) -> None:
        """
        Release any resources this manager holds.

        A documented no-op: ``VolumeBrowser``/``RecoveryCopier``/
        ``RecoveryVerifier`` all complete their work synchronously
        within a single call and hold nothing open between calls.
        """

        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    # ------------------------------------------------------------------
    # Volume discovery (delegated, for the Technician Console)
    # ------------------------------------------------------------------

    def discover_volumes(
        self, inspection_report: HardwareInspectionReport
    ) -> list[RecoveryVolume]:
        """
        Discover readable volumes on the target system, so the
        Technician Console can present them (REQ-REC-004) before
        calling ``run()`` with the technician's eventual selection.
        """

        return self._volume_browser.discover_volumes(inspection_report.storage.data)

    # ------------------------------------------------------------------
    # Recovery (REQ-REC-001 through REQ-REC-026)
    # ------------------------------------------------------------------

    def run(
        self,
        inspection_report: HardwareInspectionReport,
        *,
        node_name: str,
        skip: bool = False,
        technician_acknowledgement: str | None = None,
        destination: Path | None = None,
        selected_paths: list[Path] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> RecoverySummary:
        """
        Run (or explicitly skip) the recovery phase.

        Args:
            inspection_report: The completed hardware inspection
                report proving REQ-REC-001's dependency is satisfied.
            node_name: Identifies the target system in published
                events. Recovery runs before the Deployment
                Controller has assigned a permanent node identity
                (that happens during Bootstrap), so callers typically
                pass a local identifier -- a serial number, asset tag,
                or hostname -- rather than a Controller-issued one.
            skip: REQ-REC-016's explicit skip path. Requires
                ``technician_acknowledgement``.
            technician_acknowledgement: Required, non-empty, when
                ``skip=True`` -- REQ-REC-016's "explicit technician
                acknowledgement before recovery is skipped".
            destination: Where selected files/directories are copied.
                Required unless ``skip=True``.
            selected_paths: The technician's selection from an earlier
                ``discover_volumes()``/``VolumeBrowser.browse()``
                session (REQ-REC-006). Required and non-empty unless
                ``skip=True`` -- a caller with nothing to recover must
                say so explicitly via ``skip=True`` rather than
                calling ``run()`` with an empty selection, so a
                RecoverySummary always distinguishes "nothing was
                selected, on purpose" (REQ-REC-015) from a
                configuration mistake.
            progress_callback: Invoked as files copy (REQ-REC-011).

        Raises:
            RecoveryValidationError: If ``skip=True`` without an
                acknowledgement, or if ``skip=False`` without a
                ``destination``/non-empty ``selected_paths``.
        """

        # ``inspection_report`` is not otherwise read here -- requiring
        # it as a parameter is itself the REQ-REC-001 check (see the
        # module docstring): only a caller holding a real, completed
        # HardwareInspectionReport can call this method at all.
        if skip:
            return self._run_skip(node_name, technician_acknowledgement)

        if destination is None:
            raise RecoveryValidationError(
                "A destination is required unless recovery is explicitly skipped."
            )

        if not selected_paths:
            raise RecoveryValidationError(
                "At least one file or directory must be selected, or "
                "recovery must be explicitly skipped (skip=True)."
            )

        return self._run_recovery(
            node_name,
            destination,
            selected_paths,
            progress_callback,
        )

    @property
    def last_summary(self) -> RecoverySummary | None:
        """The most recently completed recovery's summary, if any."""

        return self._last_summary

    # ------------------------------------------------------------------
    # Internal: skip path (REQ-REC-016)
    # ------------------------------------------------------------------

    def _run_skip(
        self, node_name: str, technician_acknowledgement: str | None
    ) -> RecoverySummary:
        if not technician_acknowledgement or not technician_acknowledgement.strip():
            raise RecoveryValidationError(
                "Skipping recovery requires an explicit, non-empty "
                "technician acknowledgement (REQ-REC-016)."
            )

        self._publish(lambda: RecoveryStartedEvent(node_name=node_name))
        logger.info(
            "Recovery skipped by technician acknowledgement: %s",
            technician_acknowledgement,
        )

        now = datetime.now(UTC)
        summary = RecoverySummary(
            started_at=now,
            completed_at=now,
            recovery_performed=False,
            skipped=True,
            skip_acknowledgement=technician_acknowledgement.strip(),
        )
        self._last_summary = summary

        self._publish(lambda: RecoveryCompletedEvent(node_name=node_name))

        return summary

    # ------------------------------------------------------------------
    # Internal: real recovery (REQ-REC-006 through -014/018-025)
    # ------------------------------------------------------------------

    def _run_recovery(
        self,
        node_name: str,
        destination: Path,
        selected_paths: list[Path],
        progress_callback: ProgressCallback | None,
    ) -> RecoverySummary:
        self._publish(lambda: RecoveryStartedEvent(node_name=node_name))
        # REQ-REC-021: every recovery operation is logged through the
        # dedicated "aquila.recovery" logger, starting here and
        # continuing through the per-failure/per-verification-failure
        # logging below and the final completion/incomplete log.
        logger.info(
            "Recovery started: %d selected path(s) -> %s",
            len(selected_paths),
            destination,
        )

        started_at = datetime.now(UTC)

        # REQ-REC-008: verified before any copying begins.
        self._copier.check_destination_space(selected_paths, destination)

        copy_result = self._copier.copy_selection(
            selected_paths, destination, progress_callback=progress_callback
        )

        # REQ-REC-022: every copy failure is logged (in addition to
        # being recorded in the eventual RecoverySummary), and likewise
        # for every verification failure logged just below.
        for failure in copy_result.failures:
            logger.warning(
                "Recovery could not copy %s: %s",
                failure.source_path,
                failure.message,
            )

        verification_results = self._verifier.verify_many(copy_result.copied_files)
        failed_verifications = [
            result
            for result in verification_results
            if result.outcome is not VerificationOutcome.VERIFIED
        ]
        for failed in failed_verifications:
            logger.error(
                "Recovery verification failed for %s (%s): %s",
                failed.source_path,
                failed.outcome.name,
                failed.detail,
            )

        completed_at = datetime.now(UTC)

        failure_messages = [
            f"{failure.source_path}: {failure.message}"
            for failure in copy_result.failures
        ] + [
            f"{failed.source_path}: {failed.outcome.name} - {failed.detail}"
            for failed in failed_verifications
        ]
        if copy_result.aborted and copy_result.abort_reason:
            failure_messages.append(f"Recovery aborted: {copy_result.abort_reason}")

        summary = RecoverySummary(
            started_at=started_at,
            completed_at=completed_at,
            recovery_performed=True,
            skipped=False,
            aborted=copy_result.aborted,
            abort_reason=copy_result.abort_reason,
            files_recovered=copy_result.files_copied,
            directories_recovered=copy_result.directories_copied,
            total_bytes_copied=copy_result.bytes_copied,
            files_skipped=len(copy_result.failures),
            files_failed_verification=len(failed_verifications),
            failure_messages=failure_messages,
        )
        self._last_summary = summary

        self._publish(lambda: RecoveryCompletedEvent(node_name=node_name))

        # REQ-REC-026: the technician must be informed of any
        # incomplete recovery before destructive operations (i.e.
        # Preparation) may begin -- logged prominently here so it is
        # visible in recovery.log regardless of whether the caller
        # also surfaces summary.status_message in the UI.
        if summary.is_complete:
            logger.info("Recovery completed: %s", summary.status_message)
        else:
            logger.warning("Recovery INCOMPLETE: %s", summary.status_message)

        return summary

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _publish(self, build_event: Callable[[], Any]) -> None:
        if self._event_bus is None:
            return

        try:
            self._event_bus.publish(build_event())
        except Exception:  # pragma: no cover - event delivery is best-effort
            logger.debug("Failed to publish recovery event.", exc_info=True)

    # ------------------------------------------------------------------
    # Magic methods
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"initialized={self._initialized}, "
            f"has_summary={self._last_summary is not None})"
        )


__all__ = ["RecoveryManager"]
