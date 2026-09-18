"""
Project Aquila
=============

Provisioning Manager

Central orchestrator for Phase One of the Provisioning Engine (SRS
Section 10.6). See this package's ``__init__`` docstring for the full
REQ-PROV-* mapping and the note about the two duplicate
"# 11.6 Provisioning Engine Requirements" sections in the current SRS
document -- this manager implements the merged union of both.

Gate: REQ-PROV-001
---------------------
Provisioning does not begin until Preparation has completed
successfully (REQ-PROV-001, both SRS versions agree on this). Exactly
like ``PreparationManager.run()`` requires a real ``RecoverySummary``,
``ProvisioningManager.run()`` requires a real
``preparation.report.PreparationSummary`` and checks
``.all_succeeded`` directly -- structural proof plus a real status
check, matching the established convention.

Halting: mirrors ``PreparationManager``'s discipline
---------------------------------------------------------
Any check that fails (minimum requirements, connectivity, answer-file
rendering, boot-media integrity) halts the run before the one
genuinely irreversible step -- ``PhaseTwoHandoff.handoff()``'s
reboot -- is ever reached. REQ-PROV-006(v2)/-020(v1)/-012(v1): a
failure is recorded and diagnostic detail is preserved in
``ProvisioningSummary`` rather than the run silently stopping partway
with no explanation.

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

from common.constants.logging import PROVISIONING_LOGGER
from common.events.types.deployment import (
    ProvisioningCompletedEvent,
    ProvisioningStartedEvent,
)
from common.exceptions.deployment import DeploymentProvisioningError
from config.schemas.controller_schema import ControllerConfig
from config.schemas.deployment_schema import DeploymentConfig
from config.schemas.network_schema import NetworkConfig
from inspection.report import HardwareInspectionReport
from models.hardware.storage import StorageDevice
from preparation.report import PreparationSummary

from .answer_file import ProvisioningProfile, ProvisioningProfileError, render_answer_file
from .boot_handoff import (
    DEFAULT_MANIFEST_FILENAME,
    BootSequenceError,
    PhaseTwoHandoff,
)
from .connectivity import (
    ConnectivityChecker,
    ControllerReachabilityResult,
    EthernetCheckResult,
)
from .report import ProvisioningSummary
from .validator import MinimumRequirementsValidator

if TYPE_CHECKING:
    # Imported only for type annotations -- this module never
    # constructs an EventBus itself, the caller owns it and passes one
    # in (see preparation.preparation_manager's identical pattern for
    # why this stays a TYPE_CHECKING-only import).
    from common.events.bus import EventBus

logger = logging.getLogger(PROVISIONING_LOGGER)


class ProvisioningManager:
    """
    Runs Phase One of the Provisioning Engine (SRS Section 10.6) and
    reports the result.
    """

    def __init__(
        self,
        event_bus: Optional["EventBus"] = None,
        *,
        validator: MinimumRequirementsValidator | None = None,
        connectivity_checker: ConnectivityChecker | None = None,
        handoff: PhaseTwoHandoff | None = None,
    ) -> None:
        self._event_bus: Optional["EventBus"] = event_bus

        self._validator = validator or MinimumRequirementsValidator()
        self._connectivity_checker = connectivity_checker or ConnectivityChecker()
        self._handoff = handoff or PhaseTwoHandoff()

        self._last_summary: ProvisioningSummary | None = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Service lifecycle (interfaces.service.Service)
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Mark the Provisioning Engine ready. Idempotent."""

        self._initialized = True

    def shutdown(self) -> None:
        """Release any resources this manager holds. A documented no-op."""

        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def last_summary(self) -> ProvisioningSummary | None:
        """The most recently completed provisioning run's summary, if any."""

        return self._last_summary

    # ------------------------------------------------------------------
    # Provisioning (REQ-PROV-001 through REQ-PROV-021)
    # ------------------------------------------------------------------

    def run(
        self,
        preparation_summary: PreparationSummary,
        *,
        node_name: str,
        inspection_report: HardwareInspectionReport,
        deployment_config: DeploymentConfig,
        controller_config: ControllerConfig,
        target_device: StorageDevice,
        profile: ProvisioningProfile,
        root_password: str,
        phase_two_directory: Path,
        answer_file_destination: Path,
        boot_entry_id: str,
        manifest_filename: str = DEFAULT_MANIFEST_FILENAME,
        trigger_handoff: bool = True,
        connectivity_retry_count: int | None = None,
        connectivity_retry_delay_seconds: float | None = None,
        connectivity_sleep: Callable[[float], None] | None = None,
        network_config: NetworkConfig | None = None,
    ) -> ProvisioningSummary:
        """
        Validate, render, and (if every prerequisite passes) hand off
        to Phase Two.

        Args:
            preparation_summary: Proof REQ-PROV-001 is satisfied --
                checked via ``.all_succeeded``.
            node_name: Identifies the target system in published
                events (matches every other Manager's convention).
            inspection_report: The completed hardware inspection
                report REQ-PROV-005's checks run against.
            deployment_config: Supplies the configured minimums and
                sanitization/profile policy.
            controller_config: The Deployment Controller connection
                policy REQ-PROV-004 checks reachability against.
            target_device: The specific storage device Preparation
                sanitized -- REQ-PROV-005's storage check and the
                answer file's disk selection both use this.
            profile: The REQ-PROV-007/010/012/013/015 answer-file
                content.
            root_password: The node's root credential (or hash),
                already read by the caller from the environment
                variable ``profile.root_password_env_var`` names --
                see ``answer_file.render_answer_file`` for why this
                method never reads it itself.
            phase_two_directory: The Phase Two boot-media directory
                (``common.constants.deployment.USB_PHASE_TWO_
                DIRECTORY``) to verify (REQ-PROV-017).
            answer_file_destination: Where to write the rendered
                ``answer.toml`` (typically
                ``phase_two_directory / "answer.toml"``, kept as a
                separate parameter rather than always implied so an
                ``http``/``pxe`` fetch-mode deployment -- which serves
                the answer file from elsewhere, not from local media
                -- can point this wherever it needs to).
            boot_entry_id: The pre-registered BCD boot-entry
                identifier the Build System created at USB-build time
                (see ``provisioning.boot_handoff``'s module docstring
                for why this manager never creates it itself).
            manifest_filename: REQ-PROV-017's checksum manifest
                filename within ``phase_two_directory``.
            trigger_handoff: When ``False``, every check still runs
                and is reported, but the actual reboot is never
                triggered -- lets a caller (or a functional test)
                inspect ``ProvisioningSummary.ready_for_handoff``
                without rebooting the machine.
            connectivity_retry_count, connectivity_retry_delay_seconds,
            connectivity_sleep: Optional overrides passed straight
                through to both
                ``ConnectivityChecker.check_ethernet()`` and
                ``.check_controller_reachability()``. Left unset by
                default so both use
                ``common.constants.deployment.NETWORK_RETRY_COUNT``/
                ``NETWORK_RETRY_DELAY_SECONDS`` and the real
                ``time.sleep`` -- genuine production retry behavior.
                Exposed here (rather than hardcoded) both because a
                technician may need to tune it for slow-negotiating
                hardware, and so a functional test can inject
                ``connectivity_retry_count=0`` with a no-op sleep
                instead of a real multi-second wait, the same
                dependency-injection discipline every other
                live-system-touching call in this codebase already
                follows.
            network_config: Dev/test-only (see ``NetworkConfig
                .allow_wireless_provisioning``). Left ``None`` (the
                default), both the minimum-requirements check and the
                live connectivity re-check below are Ethernet-only,
                identical to every prior release.

        Raises:
            DeploymentProvisioningError: If ``preparation_summary`` is
                not ``all_succeeded`` (REQ-PROV-001).
        """

        if not preparation_summary.all_succeeded:
            raise DeploymentProvisioningError(
                "Provisioning cannot begin: preparation has not "
                "completed successfully (REQ-PROV-001). Preparation "
                f"status: {preparation_summary.status_message}"
            )

        self._publish(lambda: ProvisioningStartedEvent(node_name=node_name))
        logger.info("Provisioning started for node '%s'.", node_name)

        started_at = datetime.now(UTC)
        aborted = False
        abort_reason: str | None = None

        # Built once, applied to both connectivity calls below: an
        # override left unset (None) means "pass nothing", so
        # ConnectivityChecker's own defaults (the real
        # NETWORK_RETRY_COUNT/NETWORK_RETRY_DELAY_SECONDS constants
        # and the real time.sleep) apply, exactly as they would if
        # this manager had no override mechanism at all.
        connectivity_kwargs: dict[str, Any] = {}
        if connectivity_retry_count is not None:
            connectivity_kwargs["retry_count"] = connectivity_retry_count
        if connectivity_retry_delay_seconds is not None:
            connectivity_kwargs["retry_delay_seconds"] = connectivity_retry_delay_seconds
        if connectivity_sleep is not None:
            connectivity_kwargs["sleep"] = connectivity_sleep

        # Every check below only runs while the run has not already
        # aborted -- matching PreparationManager.run()'s "halt
        # immediately" discipline. This matters most for the two live
        # connectivity checks: each retries with a real delay
        # (NETWORK_RETRY_COUNT * NETWORK_RETRY_DELAY_SECONDS), and
        # there is no reason to spend that time once an earlier,
        # cheaper check has already determined the run cannot proceed.
        requirements_result = self._validator.validate(
            inspection_report, deployment_config, target_device, network_config
        )
        if not requirements_result.satisfied:
            aborted = True
            abort_reason = requirements_result.summary
            logger.error("Provisioning halted: %s", abort_reason)

        if not aborted:
            ethernet_result = self._connectivity_checker.check_ethernet(
                allow_wireless=(
                    network_config.allow_wireless_provisioning
                    if network_config is not None
                    else False
                ),
                **connectivity_kwargs,
            )
            if not ethernet_result.connected:
                aborted = True
                abort_reason = ethernet_result.detail
                logger.error("Provisioning halted: %s", abort_reason)
        else:
            ethernet_result = EthernetCheckResult(
                connected=False, detail="Ethernet connectivity was not checked."
            )

        if not aborted:
            controller_result = self._connectivity_checker.check_controller_reachability(
                controller_config, **connectivity_kwargs
            )
            if not controller_result.reachable:
                aborted = True
                abort_reason = controller_result.detail
                logger.error("Provisioning halted: %s", abort_reason)
        else:
            controller_result = ControllerReachabilityResult(
                reachable=False,
                detail="Deployment Controller reachability was not checked.",
                host=controller_config.host,
                port=controller_config.port,
            )

        answer_rendered = False
        answer_detail = "Answer file was not rendered."
        if not aborted:
            try:
                answer_toml = render_answer_file(profile, root_password)
                answer_file_destination.parent.mkdir(parents=True, exist_ok=True)
                answer_file_destination.write_text(answer_toml, encoding="utf-8")
                answer_rendered = True
                answer_detail = f"Answer file written to {answer_file_destination}."
                logger.info(answer_detail)
            except ProvisioningProfileError as exc:
                aborted = True
                abort_reason = str(exc)
                answer_detail = str(exc)
                logger.error("Provisioning halted: %s", abort_reason)
            except OSError as exc:
                aborted = True
                abort_reason = f"Could not write answer file: {exc}"
                answer_detail = abort_reason
                logger.error("Provisioning halted: %s", abort_reason)

        media_result = None
        if not aborted:
            media_result = self._handoff.verify_media(
                phase_two_directory, manifest_filename=manifest_filename
            )
            if not media_result.verified:
                aborted = True
                abort_reason = media_result.detail
                logger.error("Provisioning halted: %s", abort_reason)

        handoff_triggered = False
        handoff_detail = "Boot handoff was not triggered."
        ready_before_handoff = not aborted

        if ready_before_handoff and trigger_handoff:
            try:
                self._handoff.handoff(boot_entry_id)
                handoff_triggered = True
                handoff_detail = (
                    f"One-time boot sequence set to '{boot_entry_id}' "
                    "and reboot triggered."
                )
                logger.info(handoff_detail)
            except BootSequenceError as exc:
                aborted = True
                abort_reason = str(exc)
                handoff_detail = str(exc)
                logger.error("Provisioning halted: %s", abort_reason)
        elif ready_before_handoff:
            handoff_detail = (
                "All checks passed; handoff was not triggered "
                "(trigger_handoff=False)."
            )
            logger.info(handoff_detail)

        completed_at = datetime.now(UTC)

        summary = ProvisioningSummary(
            started_at=started_at,
            completed_at=completed_at,
            node_hostname=profile.node_hostname,
            target_device_path=target_device.device_path,
            requirements_satisfied=requirements_result.satisfied,
            requirements_detail=requirements_result.summary,
            ethernet_connected=ethernet_result.connected,
            ethernet_detail=ethernet_result.detail,
            controller_reachable=controller_result.reachable,
            controller_detail=controller_result.detail,
            answer_file_rendered=answer_rendered,
            answer_file_detail=answer_detail,
            media_integrity_verified=bool(media_result and media_result.verified),
            media_integrity_detail=(
                media_result.detail
                if media_result is not None
                else "Boot media integrity was not checked."
            ),
            handoff_triggered=handoff_triggered,
            handoff_detail=handoff_detail,
            aborted=aborted,
            abort_reason=abort_reason,
        )
        self._last_summary = summary

        self._publish(lambda: ProvisioningCompletedEvent(node_name=node_name))

        logger.info(
            "Provisioning finished for node '%s': %s",
            node_name,
            summary.status_message,
        )

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
            logger.debug("Failed to publish provisioning event.", exc_info=True)

    # ------------------------------------------------------------------
    # Magic methods
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"initialized={self._initialized}, "
            f"has_summary={self._last_summary is not None})"
        )


__all__ = ["ProvisioningManager"]
