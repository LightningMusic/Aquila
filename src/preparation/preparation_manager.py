"""
Project Aquila
=============

Preparation Manager

Central orchestrator for the Preparation Engine (SRS Section 10.5,
REQ-PREP-001 through REQ-PREP-024). Coordinates
``preparation.confirmations.validate_confirmations`` (REQ-PREP-004
through -007), ``preparation.sanitizer.DiskSanitizer`` (REQ-PREP-008
through -016), and ``preparation.verifier.SanitizationVerifier``
(REQ-PREP-017/018), assembling their results into one
``preparation.report.PreparationSummary`` (REQ-PREP-002/019).

Follows the exact ``ConfigurationManager``/``InspectionManager``/
``RecoveryManager`` Manager/Service pattern: ``Service`` lifecycle,
``TYPE_CHECKING``-only ``EventBus`` import with a runtime try/except +
reused ``PreparationStartedEvent``/``PreparationCompletedEvent``
(``common.events.types.deployment`` already defines this exact pair --
nothing new needed here), best-effort ``_publish()``, and logging
through the dedicated ``aquila.preparation`` logger.

Why ``run()`` requires a ``RecoverySummary``
-----------------------------------------------
REQ-PREP-001 / REQ-REC-017 ("The Preparation Engine shall not begin
until the Recovery Engine has successfully completed or has been
intentionally skipped by the technician") is enforced the same way
``RecoveryManager.run()`` enforces its own REQ-REC-001 dependency on
``HardwareInspectionReport``: requiring a real ``RecoverySummary`` as a
parameter is structural proof recovery ran, and
``RecoverySummary.is_complete`` (recovery.report) is checked directly
-- it already distinguishes "ran to completion", "intentionally
skipped with acknowledgement", and "aborted", which is exactly what
REQ-PREP-001 needs to decide.

REQ-PREP-022/023: halting immediately
----------------------------------------
Any ``DiskSanitizerError`` raised by ``DiskSanitizer.sanitize()`` --
identity re-verification failure, removable/boot-media refusal, a WMI
backend that is entirely unavailable, or (always) an ATA/NVMe secure-
erase attempt -- is treated as an unrecoverable storage error
(REQ-PREP-022): the whole run halts immediately, no further devices in
``target_devices`` are touched, and the resulting ``PreparationSummary``
is marked ``aborted``. A verification failure (REQ-PREP-017/018,
``SanitizationRecord.succeeded is False``) halts the run the same way
-- REQ-PREP-018 says plainly that deployment "shall terminate" when
verification fails, not "skip this one device and continue".

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Callable, Optional

from common.constants.deployment import FORCE_CONFIRMATION_PHRASE
from common.constants.logging import PREPARATION_LOGGER
from common.enums import SanitizationMethod
from common.events.types.deployment import (
    PreparationCompletedEvent,
    PreparationStartedEvent,
)
from common.exceptions.deployment import (
    DeploymentConfigurationError,
    DeploymentPreparationError,
    DeploymentValidationError,
)
from config.schemas.deployment_schema import DeploymentConfig
from models.hardware.storage import StorageDevice, StorageInventory
from recovery.report import RecoverySummary

from .confirmations import PreparationConfirmations, validate_confirmations
from .report import PreparationSummary, SanitizationRecord
from .sanitizer import (
    DiskSanitizer,
    DiskSanitizerError,
    ProgressCallback,
    resolve_disk_number,
)
from .verifier import SanitizationVerifier

if TYPE_CHECKING:
    # Imported only for type annotations -- this module never
    # constructs an EventBus itself, the caller owns it and passes one
    # in (see recovery.recovery_manager's identical pattern for why
    # this stays a TYPE_CHECKING-only import).
    from common.events.bus import EventBus

logger = logging.getLogger(PREPARATION_LOGGER)


class PreparationManager:
    """
    Runs the Preparation Engine's storage-sanitization phase
    (SRS Section 10.5) and reports the result.
    """

    def __init__(
        self,
        event_bus: Optional["EventBus"] = None,
        *,
        sanitizer: DiskSanitizer | None = None,
        verifier: SanitizationVerifier | None = None,
    ) -> None:
        self._event_bus: Optional["EventBus"] = event_bus

        self._sanitizer = sanitizer or DiskSanitizer()
        self._verifier = verifier or SanitizationVerifier()

        self._last_summary: PreparationSummary | None = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Service lifecycle (interfaces.service.Service)
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """
        Mark the Preparation Engine ready.

        Like ``RecoveryManager``, there is no state to load ahead of
        time -- sanitization acts on live target-system state at the
        moment ``run()`` is called. Idempotent.
        """

        self._initialized = True

    def shutdown(self) -> None:
        """
        Release any resources this manager holds.

        A documented no-op: ``DiskSanitizer``/``SanitizationVerifier``
        both complete their work synchronously within a single call
        and hold nothing open between calls.
        """

        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def last_summary(self) -> PreparationSummary | None:
        """The most recently completed preparation run's summary, if any."""

        return self._last_summary

    # ------------------------------------------------------------------
    # Preparation (REQ-PREP-001 through REQ-PREP-024)
    # ------------------------------------------------------------------

    def run(
        self,
        recovery_summary: RecoverySummary,
        *,
        node_name: str,
        target_devices: list[StorageDevice],
        storage_inventory: StorageInventory,
        deployment_config: DeploymentConfig,
        confirmations: PreparationConfirmations,
        system_manufacturer: str = "",
        system_model: str = "",
        system_serial_number: str = "",
        deployment_workflow: str = "",
        operator_identity: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> PreparationSummary:
        """
        Sanitize every device in ``target_devices`` and return the
        resulting ``PreparationSummary``.

        Args:
            recovery_summary: The completed (or intentionally skipped)
                recovery summary proving REQ-PREP-001/REQ-REC-017's
                dependency is satisfied.
            node_name: Identifies the target system in published
                events, matching ``RecoveryManager.run()``'s
                ``node_name`` convention.
            target_devices: The storage device(s) to sanitize
                (REQ-PREP-005/013). Must be non-empty and every device
                must appear in ``storage_inventory
                .eligible_for_deployment()`` (REQ-PREP-012).
            storage_inventory: The full inventory ``target_devices``
                was selected from, used to independently re-check
                REQ-PREP-012 eligibility before any destructive action
                -- ``DiskSanitizer`` performs its own defense-in-depth
                check per device too, but a caller-level check here
                catches a bad selection before anything begins.
            deployment_config: Supplies ``confirmation_count``
                (REQ-PREP-007) and ``sanitization_method``
                (REQ-PREP-014).
            confirmations: The technician's actual confirmation
                responses (REQ-PREP-004 through -007), validated
                before any destructive action.
            system_manufacturer, system_model, system_serial_number,
            deployment_workflow: REQ-PREP-002's pre-flight summary
                facts, carried through to ``PreparationSummary``
                unchanged (this manager does not re-detect them --
                that is Inspection's responsibility).
            operator_identity: Optional technician identity for the
                sanitization report (REQ-PREP-019).
            progress_callback: Invoked as each device sanitizes
                (REQ-PREP-015).

        Raises:
            DeploymentPreparationError: If ``recovery_summary`` is not
                complete (REQ-PREP-001/REQ-REC-017).
            DeploymentValidationError: If ``target_devices`` is empty,
                contains a device not eligible for deployment
                (REQ-PREP-012), or ``confirmations`` does not satisfy
                REQ-PREP-004 through -007.
            DeploymentConfigurationError: If ``deployment_config
                .sanitization_method`` does not name a known
                ``SanitizationMethod`` (defensive; ``DeploymentConfig``
                itself already validates this at construction).
        """

        # REQ-PREP-001 / REQ-REC-017: structurally required, and
        # explicitly checked -- unlike RecoveryManager's dependency on
        # HardwareInspectionReport (which is proof-by-possession only),
        # RecoverySummary.is_complete carries real information this
        # check must actually read.
        if not recovery_summary.is_complete:
            raise DeploymentPreparationError(
                "Preparation cannot begin: recovery has not completed "
                "successfully or been intentionally skipped "
                f"(REQ-PREP-001/REQ-REC-017). Recovery status: "
                f"{recovery_summary.status_message}"
            )

        if not target_devices:
            raise DeploymentValidationError(
                "At least one target storage device must be selected "
                "(REQ-PREP-005)."
            )

        eligible_paths = {
            device.device_path for device in storage_inventory.eligible_for_deployment()
        }
        ineligible = [
            device.device_path
            for device in target_devices
            if device.device_path not in eligible_paths
        ]
        if ineligible:
            raise DeploymentValidationError(
                "The following target device(s) are not eligible for "
                "sanitization -- they are removable or boot media "
                f"(REQ-PREP-012): {', '.join(ineligible)}"
            )

        # REQ-PREP-004 through -007.
        validate_confirmations(
            confirmations,
            required_count=deployment_config.confirmation_count,
            force_phrase=FORCE_CONFIRMATION_PHRASE,
        )

        method = self._resolve_method(deployment_config)

        self._publish(lambda: PreparationStartedEvent(node_name=node_name))
        logger.info(
            "Preparation started: %d target device(s), method=%s.",
            len(target_devices),
            method.name,
        )

        started_at = datetime.now(UTC)
        records: list[SanitizationRecord] = []
        aborted = False
        abort_reason: str | None = None

        for device in target_devices:
            try:
                record = self._sanitize_one(device, method, progress_callback)
            except DiskSanitizerError as exc:
                # REQ-PREP-022: halt immediately on an unrecoverable
                # storage error -- no further devices are touched.
                aborted = True
                abort_reason = f"{device.device_path}: {exc}"
                logger.error(
                    "Preparation halted -- unrecoverable error "
                    "sanitizing %s: %s",
                    device.device_path,
                    exc,
                )
                break

            records.append(record)

            if not record.succeeded:
                # REQ-PREP-018: verification failure terminates the
                # whole run, not just this device.
                aborted = True
                abort_reason = (
                    f"{device.device_path}: sanitization or "
                    f"verification failed -- {record.verification_detail}"
                )
                logger.error(
                    "Preparation halted -- sanitization/verification "
                    "failed for %s: %s",
                    device.device_path,
                    record.verification_detail,
                )
                break

        completed_at = datetime.now(UTC)

        summary = PreparationSummary(
            started_at=started_at,
            completed_at=completed_at,
            system_manufacturer=system_manufacturer,
            system_model=system_model,
            system_serial_number=system_serial_number,
            deployment_workflow=deployment_workflow,
            recovery_status=recovery_summary.status_message,
            records=records,
            aborted=aborted,
            abort_reason=abort_reason,
            operator_identity=operator_identity,
        )
        self._last_summary = summary

        self._publish(lambda: PreparationCompletedEvent(node_name=node_name))

        # REQ-PREP-023: eligibility for provisioning is recorded here,
        # but REQ-PREP-024 means this method never acts on it --
        # PreparationSummary.all_succeeded is only ever read by a
        # caller (a future Provisioning Engine), never chained to
        # automatically from here.
        if summary.all_succeeded:
            logger.info("Preparation completed: %s", summary.status_message)
        else:
            logger.warning("Preparation INCOMPLETE: %s", summary.status_message)

        return summary

    # ------------------------------------------------------------------
    # Internal: one device's sanitize + verify (REQ-PREP-013 through -019)
    # ------------------------------------------------------------------

    def _sanitize_one(
        self,
        device: StorageDevice,
        method: SanitizationMethod,
        progress_callback: ProgressCallback | None,
    ) -> SanitizationRecord:
        execution = self._sanitizer.sanitize(
            device, method, progress_callback=progress_callback
        )

        disk_number = resolve_disk_number(device.device_path)
        verification = self._verifier.verify(device.device_path, disk_number, method)

        return SanitizationRecord(
            device_path=device.device_path,
            device_model=device.model,
            device_serial_number=device.serial_number,
            method=method,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            execution_succeeded=execution.succeeded,
            execution_message=execution.message,
            return_code=execution.return_code,
            verification_outcome=verification.outcome,
            verification_detail=verification.detail,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_method(deployment_config: DeploymentConfig) -> SanitizationMethod:
        try:
            return SanitizationMethod[deployment_config.sanitization_method.upper()]
        except KeyError as exc:
            raise DeploymentConfigurationError(
                "Unknown sanitization_method "
                f"'{deployment_config.sanitization_method}' -- expected "
                f"one of {[member.name.lower() for member in SanitizationMethod]}."
            ) from exc

    def _publish(self, build_event: Callable[[], Any]) -> None:
        if self._event_bus is None:
            return

        try:
            self._event_bus.publish(build_event())
        except Exception:  # pragma: no cover - event delivery is best-effort
            logger.debug("Failed to publish preparation event.", exc_info=True)

    # ------------------------------------------------------------------
    # Magic methods
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"initialized={self._initialized}, "
            f"has_summary={self._last_summary is not None})"
        )


__all__ = ["PreparationManager"]
