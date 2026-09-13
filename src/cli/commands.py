"""
Project Aquila
=============

CLI: Commands

Implements every ``aquila-cli`` subcommand parsed by
:mod:`cli.arguments`. This module is this package's counterpart to
``technician_console.dialogs``: where that module answers every
``workflows`` callback Protocol (``PreparationConfirmationProvider``,
``RecoveryDecisionProvider``, ``TargetDeviceSelector``) by opening a
modal Tk dialog and blocking for a technician's click, the functions
here answer the exact same Protocols directly from an already-parsed
``argparse.Namespace`` -- no window, no event loop, nothing blocking
on terminal input. See ``cli.arguments``'s module docstring for the
design reasoning (narrower scripting/automation scope, confirmed with
the user, and why GP-001 shapes the confirmation flags the way it
does).

Service bring-up mirrors ``technician_console.main_window.MainWindow
.__init__``'s sequence (``ApplicationManager`` -> ``ConfigurationService``
-> ``config_manager.validate_all()`` -> ``LoggingService`` ->
``WorkflowManager``) exactly, just returned from :func:`build_context`
instead of stored on a Tk widget -- there is no reason for a headless
front end to duplicate that bring-up order, only to replace *how* it
reports failures (raising :class:`CliUsageError` for
``cli.cli.main()`` to print to stderr, rather than a Tk error dialog).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from common import media
from common.constants.deployment import (
    DEPLOYMENT_ABORTED,
    DEPLOYMENT_SUCCESS,
    DEPLOYMENT_WARNING,
)
from common.events.bus import EventBus
from common.exceptions.application import (
    AquilaEnvironmentError,
    AquilaInitializationError,
)
from common.utils.formatting import format_bytes
from config.manager import ConfigurationManager
from inspection.report import HardwareInspectionReport
from models.hardware.storage import StorageDevice
from preparation.confirmations import PreparationConfirmations
from preparation.sanitizer import SanitizationProgress
from recovery.browser import RecoveryVolume, VolumeBrowser
from recovery.copier import CopyProgress
from services.configuration_service import ConfigurationService, SessionConfigBundle
from services.logging_service import LoggingService
from workflows.application_manager import ApplicationManager
from workflows.deployment_manager import (
    RecoveryDecisionProvider,
    TargetDeviceSelector,
    WorkflowSummary,
)
from workflows.inspection_manager import InspectionWorkflowStage
from workflows.preparation_manager import (
    PreparationConfirmationProvider,
    PreparationConfirmationRequest,
)
from workflows.progress import WorkflowStageEvent
from workflows.provisioning_manager import ProvisioningProfileTemplate
from workflows.recovery_manager import RecoveryDecision
from workflows.workflow_manager import WorkflowManager


class CliUsageError(Exception):
    """
    A problem with the command line/environment itself (a missing
    device serial, an unmet configuration prerequisite, a mismatched
    confirmation count) -- distinct from an ``AquilaError`` raised by
    the workflow/engine layer, which is propagated unchanged instead
    of being wrapped in one of these. ``cli.cli.main()`` catches both,
    but this one specifically means "the technician needs to fix their
    command line or environment," not "the deployment itself failed."
    """


# ---------------------------------------------------------------------------
# Service bring-up (mirrors technician_console.main_window.MainWindow.__init__)
# ---------------------------------------------------------------------------


@dataclass
class CliContext:
    """Every service one ``aquila-cli`` invocation needs, bundled for cleanup."""

    app_manager: ApplicationManager
    configuration_service: ConfigurationService
    config_bundle: SessionConfigBundle
    logging_service: LoggingService
    workflow_manager: WorkflowManager
    event_bus: EventBus
    volume_browser: VolumeBrowser
    media_root: Optional[Path]
    validation_problems: dict[str, str]

    def close(self) -> None:
        self.workflow_manager.shutdown()
        self.logging_service.shutdown()
        self.configuration_service.shutdown()
        self.app_manager.shutdown()


def build_context(configs_dir: Optional[Path]) -> CliContext:
    """
    Bring up every core service one ``aquila-cli`` invocation needs.

    Raises:
        CliUsageError: If startup or configuration loading fails --
            the CLI equivalent of ``MainWindow``'s "Aquila Failed to
            Start"/"Configuration Failed to Load" error dialogs.
    """

    app_manager = ApplicationManager(configs_dir=configs_dir)
    try:
        app_manager.initialize()
    except AquilaInitializationError as exc:
        raise CliUsageError(f"Aquila failed to start: {exc}") from exc

    config_manager = app_manager.services.resolve(ConfigurationManager)
    event_bus = app_manager.services.resolve(EventBus)

    configuration_service = ConfigurationService(configuration_manager=config_manager)
    configuration_service.initialize()

    try:
        config_bundle = configuration_service.load_session_bundle()
    except Exception as exc:  # noqa: BLE001 - reported to the operator verbatim
        app_manager.shutdown()
        raise CliUsageError(f"Configuration failed to load: {exc}") from exc

    validation_problems = config_manager.validate_all()

    logging_service = LoggingService(logging_config=config_bundle.logging)
    logging_service.initialize()

    workflow_manager = WorkflowManager(event_bus=event_bus)
    workflow_manager.initialize()

    try:
        media_root: Optional[Path] = media.detect_media_root()
    except AquilaEnvironmentError:
        media_root = None

    return CliContext(
        app_manager=app_manager,
        configuration_service=configuration_service,
        config_bundle=config_bundle,
        logging_service=logging_service,
        workflow_manager=workflow_manager,
        event_bus=event_bus,
        volume_browser=VolumeBrowser(),
        media_root=media_root,
        validation_problems=validation_problems,
    )


# ---------------------------------------------------------------------------
# Progress reporting -- to stderr, so stdout stays reserved for the final
# summary (human-readable or --json)
# ---------------------------------------------------------------------------


def _print_stage_event(event: WorkflowStageEvent) -> None:
    print(f"[{event.severity}] [{event.stage}] {event.message}", file=sys.stderr)


def _print_recovery_progress(progress: CopyProgress) -> None:
    print(
        f"[recovery] {progress.current_path.name}: "
        f"{progress.files_copied_so_far} file(s), "
        f"{format_bytes(progress.bytes_copied_so_far)} so far",
        file=sys.stderr,
    )


def _print_sanitization_progress(progress: SanitizationProgress) -> None:
    print(
        f"[sanitization] {progress.device_path}: "
        f"{progress.stage} -- {progress.message}",
        file=sys.stderr,
    )


def _print_validation_warnings(problems: dict[str, str]) -> None:
    if not problems:
        return
    print(
        "Configuration warning(s) -- running on built-in defaults for:",
        file=sys.stderr,
    )
    for name, message in sorted(problems.items()):
        print(f"  - {name}: {message}", file=sys.stderr)


# ---------------------------------------------------------------------------
# TargetDeviceSelector (REQ-PREP-005) -- resolved from --sanitize-device-serial
# ---------------------------------------------------------------------------


def _select_devices_by_serial(
    devices: list[StorageDevice], serials: list[str]
) -> list[StorageDevice]:
    by_serial = {device.serial_number: device for device in devices if device.serial_number}
    chosen: list[StorageDevice] = []
    missing: list[str] = []
    for serial in serials:
        device = by_serial.get(serial)
        if device is None:
            missing.append(serial)
        else:
            chosen.append(device)

    if missing:
        available = ", ".join(sorted(by_serial)) or "(none)"
        raise CliUsageError(
            "No eligible storage device found with serial number(s): "
            f"{', '.join(missing)}. Eligible device serial number(s): "
            f"{available}. Run 'aquila-cli inspect' to list them."
        )

    return chosen


def _build_target_device_selector(serials: list[str]) -> TargetDeviceSelector:
    def selector(report: HardwareInspectionReport) -> list[StorageDevice]:
        eligible = report.storage.data.eligible_for_deployment()
        return _select_devices_by_serial(eligible, serials)

    return selector


def _resolve_provisioning_device(
    chosen_devices: list[StorageDevice], args: argparse.Namespace
) -> StorageDevice:
    if args.provisioning_device_serial:
        for device in chosen_devices:
            if device.serial_number == args.provisioning_device_serial:
                return device
        raise CliUsageError(
            "--provisioning-device-serial "
            f"{args.provisioning_device_serial!r} does not match any "
            "device selected via --sanitize-device-serial."
        )
    if len(chosen_devices) == 1:
        return chosen_devices[0]
    raise CliUsageError(
        "More than one --sanitize-device-serial was given -- "
        "--provisioning-device-serial is required to say which one "
        "Proxmox VE is installed to."
    )


# ---------------------------------------------------------------------------
# RecoveryDecisionProvider (REQ-REC-004/005/006/016) -- see cli.arguments's
# module docstring for the "skip, or recover whole volume(s)" scope decision.
# ---------------------------------------------------------------------------


def _validate_recovery_args(args: argparse.Namespace) -> None:
    if args.skip_recovery == args.recover_all:
        raise CliUsageError(
            "Exactly one of --skip-recovery or --recover-all is required."
        )
    if args.skip_recovery and not (args.recovery_acknowledgement or "").strip():
        raise CliUsageError(
            "--skip-recovery requires a non-empty --recovery-acknowledgement "
            "(REQ-REC-016)."
        )
    if args.recover_all and args.recovery_destination is None:
        raise CliUsageError("--recover-all requires --recovery-destination.")


def _collect_readable_paths(
    browser: VolumeBrowser, volume: RecoveryVolume, relative_path: str = ""
) -> list[Path]:
    """Recursively walk ``relative_path`` within ``volume``, collecting
    every readable file (REQ-REC-002/004/005) -- ``VolumeBrowser.browse()``
    only lists one directory's immediate contents at a time (REQ-REC-005),
    so a whole-volume recovery needs this to walk it."""

    paths: list[Path] = []
    for entry in browser.browse(volume, relative_path):
        if entry.is_directory:
            paths.extend(_collect_readable_paths(browser, volume, entry.relative_path))
        elif entry.readable:
            paths.append(volume.root_path / entry.relative_path)
    return paths


def _build_recovery_decision_provider(
    args: argparse.Namespace, browser: VolumeBrowser
) -> RecoveryDecisionProvider:
    def provider(
        _inspection_report: HardwareInspectionReport,
        volumes: list[RecoveryVolume],
    ) -> RecoveryDecision:
        if args.skip_recovery:
            return RecoveryDecision.skip_with_acknowledgement(
                args.recovery_acknowledgement.strip()
            )

        selected_volumes = volumes
        if args.recover_volumes:
            wanted = set(args.recover_volumes)
            available = {volume.device_id for volume in volumes}
            missing = wanted - available
            if missing:
                raise CliUsageError(
                    "--recover-volume named device(s) not discovered: "
                    f"{', '.join(sorted(missing))}. Discovered volume(s): "
                    f"{', '.join(sorted(available)) or '(none)'}."
                )
            selected_volumes = [v for v in volumes if v.device_id in wanted]

        selected_paths: list[Path] = []
        for volume in selected_volumes:
            selected_paths.extend(_collect_readable_paths(browser, volume))

        if not selected_paths:
            raise CliUsageError(
                "--recover-all found no readable files across the "
                "selected volume(s) -- nothing to recover. Use "
                "--skip-recovery (with --recovery-acknowledgement) if "
                "that is expected."
            )

        return RecoveryDecision.recover(
            destination=args.recovery_destination, selected_paths=selected_paths
        )

    return provider


# ---------------------------------------------------------------------------
# PreparationConfirmationProvider (REQ-PREP-004/005/006/007, REQ-TC-012)
# ---------------------------------------------------------------------------


def _build_confirmation_provider(
    args: argparse.Namespace,
) -> PreparationConfirmationProvider:
    def provider(
        request: PreparationConfirmationRequest,
    ) -> PreparationConfirmations:
        # REQ-PREP-002/003: shown even though nothing here is
        # interactive -- the operator (or whoever reviews this
        # invocation's captured output) must be able to see exactly
        # what was about to be destroyed and confirm the flags below
        # actually matched it.
        print(request.summary_text, file=sys.stderr)

        expected_extra = max(0, request.required_confirmation_count - 3)
        if args.additional_confirmations_count != expected_extra:
            raise CliUsageError(
                "--additional-confirmations-count "
                f"{args.additional_confirmations_count} does not match "
                "what deployment.yaml's confirmation_count "
                f"({request.required_confirmation_count}) requires "
                f"({expected_extra})."
            )

        return PreparationConfirmations(
            target_device_confirmed=args.confirm_target_device,
            erasure_acknowledgement_phrase=args.erasure_acknowledgement,
            final_approval=args.confirm_proceed,
            additional_confirmations=tuple(
                [True] * args.additional_confirmations_count
            ),
        )

    return provider


# ---------------------------------------------------------------------------
# Provisioning profile (REQ-PROV-015) -- mirrors
# technician_console.main_window's domain/mailto sourcing, plus the
# optional per-run overrides cli.arguments exposes.
# ---------------------------------------------------------------------------


def _build_profile_template(
    args: argparse.Namespace, *, domain: str, mailto: str
) -> ProvisioningProfileTemplate:
    kwargs: dict[str, Any] = {"domain": domain, "mailto": mailto}

    if args.root_password_env_var:
        kwargs["root_password_env_var"] = args.root_password_env_var
    if args.disk_list:
        kwargs["disk_list"] = tuple(
            item.strip() for item in args.disk_list.split(",") if item.strip()
        )
    if args.filesystem:
        kwargs["filesystem"] = args.filesystem
    if args.keyboard:
        kwargs["keyboard"] = args.keyboard
    if args.country:
        kwargs["country"] = args.country
    if args.timezone:
        kwargs["timezone"] = args.timezone
    if args.ip_assignment_method:
        kwargs["ip_assignment_method"] = args.ip_assignment_method
    if args.static_cidr:
        kwargs["static_cidr"] = args.static_cidr
    if args.static_gateway:
        kwargs["static_gateway"] = args.static_gateway
    if args.static_dns:
        kwargs["static_dns_servers"] = tuple(
            item.strip() for item in args.static_dns.split(",") if item.strip()
        )
    if args.reboot_on_error:
        kwargs["reboot_on_error"] = True
    if args.subscription_key:
        kwargs["subscription_key"] = args.subscription_key

    return ProvisioningProfileTemplate(**kwargs)


# ---------------------------------------------------------------------------
# REQ-TC-013-equivalent summary rendering
# ---------------------------------------------------------------------------


def _render_summary_text(summary: WorkflowSummary) -> str:
    lines: list[str] = []
    lines.append(f"Workflow: {summary.workflow_type.value}")
    lines.append(f"Node: {summary.node_name}")
    lines.append(
        f"Started: {summary.started_at.isoformat()}  "
        f"Completed: {summary.completed_at.isoformat()}"
    )
    lines.append(f"Duration: {summary.duration.total_seconds():.1f}s")
    lines.append("")

    if summary.inspection_report is not None:
        firmware = summary.inspection_report.bios.data.firmware
        lines.append(
            "Hardware: "
            f"{firmware.manufacturer or 'Unknown'} {firmware.model or 'Unknown'} "
            f"(serial: {firmware.serial_number or 'unknown'})"
        )
        lines.append(
            f"Inspection result: {summary.inspection_report.overall_result.name}"
        )
        lines.append("")

    if summary.recovery_summary is not None:
        lines.append(f"Recovery: {summary.recovery_summary.status_message}")
        lines.append("")

    if summary.preparation_summary is not None:
        prep = summary.preparation_summary
        lines.append(f"Preparation: {prep.status_message}")
        for record in prep.records:
            lines.append(
                f"  - {record.device_path} ({record.device_model}): "
                f"{record.method.value}, "
                f"{'succeeded' if record.succeeded else 'FAILED'}, "
                f"verification={record.verification_outcome.value}"
            )
        lines.append("")

    if summary.provisioning_result is not None:
        result = summary.provisioning_result
        lines.append(f"Provisioning: {result.status_message}")
        if result.identity_record is not None:
            lines.append(
                f"  Node identifier: {result.identity_record.node_identifier}"
            )
            lines.append(f"  Assigned hostname: {result.identity_record.hostname}")
        lines.append("")

    if summary.aborted and summary.abort_reason:
        lines.append(f"Halt reason: {summary.abort_reason}")

    return "\n".join(lines).rstrip("\n")


def _emit_summary(summary: WorkflowSummary, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary.to_dict(), indent=2, sort_keys=True, default=str))
    else:
        print(_render_summary_text(summary))


def _summary_exit_code(summary: WorkflowSummary, *, had_config_warnings: bool) -> int:
    if summary.aborted:
        return DEPLOYMENT_ABORTED
    if had_config_warnings:
        return DEPLOYMENT_WARNING
    return DEPLOYMENT_SUCCESS


# ---------------------------------------------------------------------------
# Subcommand: inspect
# ---------------------------------------------------------------------------


def cmd_inspect(args: argparse.Namespace) -> int:
    ctx = build_context(args.configs_dir)
    try:
        _print_validation_warnings(ctx.validation_problems)

        stage = InspectionWorkflowStage(event_bus=ctx.event_bus)
        stage.initialize()
        try:
            report = stage.run(
                node_name=args.node_name, progress_callback=_print_stage_event
            )
        finally:
            stage.shutdown()
    finally:
        ctx.close()

    eligible = report.storage.data.eligible_for_deployment()

    if args.json:
        payload = {
            "inspection_report": report.to_dict(),
            "eligible_target_devices": [
                {
                    "serial_number": device.serial_number,
                    "model": device.model,
                    "device_path": device.device_path,
                    "device_type": device.device_type.value,
                    "capacity_bytes": device.capacity_bytes,
                }
                for device in eligible
            ],
        }
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    else:
        firmware = report.bios.data.firmware
        print(
            "System: "
            f"{firmware.manufacturer or 'Unknown'} {firmware.model or 'Unknown'} "
            f"(serial: {firmware.serial_number or 'unknown'})"
        )
        print(f"Inspection result: {report.overall_result.name}")
        print()
        if eligible:
            print("Eligible target device(s) (REQ-PREP-005):")
            for device in eligible:
                print(
                    f"  - {device.model or '(unknown model)'} "
                    f"[serial: {device.serial_number or 'no serial'}] "
                    f"{format_bytes(device.capacity_bytes)} "
                    f"({device.device_path})"
                )
        else:
            print("No storage device eligible for deployment was detected.")

    return DEPLOYMENT_SUCCESS


# ---------------------------------------------------------------------------
# Subcommand: retire (Workflow A)
# ---------------------------------------------------------------------------


def cmd_retire(args: argparse.Namespace) -> int:
    _validate_recovery_args(args)

    ctx = build_context(args.configs_dir)
    try:
        _print_validation_warnings(ctx.validation_problems)

        summary = ctx.workflow_manager.start_retirement_workflow(
            node_name=args.node_name,
            recovery_decision_provider=_build_recovery_decision_provider(
                args, ctx.volume_browser
            ),
            target_device_selector=_build_target_device_selector(
                args.sanitize_device_serials
            ),
            deployment_config=ctx.config_bundle.deployment,
            confirmation_provider=_build_confirmation_provider(args),
            operator_identity=args.operator_identity,
            recovery_progress_callback=_print_recovery_progress,
            sanitization_progress_callback=_print_sanitization_progress,
            workflow_progress_callback=_print_stage_event,
        )
        had_warnings = bool(ctx.validation_problems)
    finally:
        ctx.close()

    _emit_summary(summary, as_json=args.json)
    return _summary_exit_code(summary, had_config_warnings=had_warnings)


# ---------------------------------------------------------------------------
# Subcommand: provision (Workflow B)
# ---------------------------------------------------------------------------


def cmd_provision(args: argparse.Namespace) -> int:
    _validate_recovery_args(args)

    ctx = build_context(args.configs_dir)
    try:
        if ctx.media_root is None:
            raise CliUsageError(
                "Could not determine the deployment media's root "
                "directory, so Provisioning cannot proceed (it needs "
                "to write the Phase Two answer file and node-identity "
                f"record). Set the {media.MEDIA_ROOT_ENV_VAR} "
                "environment variable to override detection."
            )

        boot_entry_id = ctx.config_bundle.deployment.boot_entry_id
        if not boot_entry_id:
            raise CliUsageError(
                "This deployment media's deployment.yaml does not set "
                "boot_entry_id -- the pre-registered BCD boot entry "
                "the Build System must stamp onto media at build "
                "time. Provisioning cannot hand off to Phase Two "
                "without it."
            )

        domain = args.domain or ctx.config_bundle.deployment.provisioning_domain
        mailto = (
            args.mailto or ctx.config_bundle.deployment.provisioning_notification_email
        )
        if not (domain and mailto):
            raise CliUsageError(
                "provisioning_domain and/or "
                "provisioning_notification_email are not set (neither "
                "in deployment.yaml nor via --domain/--mailto) -- both "
                "are required by the Proxmox VE installer "
                "(REQ-PROV-015's [global].fqdn / [global].mailto) and "
                "cannot be left blank or guessed on the node's behalf."
            )

        profile_template = _build_profile_template(args, domain=domain, mailto=mailto)

        root_password = ConfigurationManager.resolve_secret(
            profile_template.root_password_env_var
        )
        if not root_password:
            raise CliUsageError(
                f"Set the {profile_template.root_password_env_var} "
                "environment variable to the node's root credential "
                "before provisioning (REQ-SEC-008/009/010: never a "
                "command-line argument)."
            )

        _print_validation_warnings(ctx.validation_problems)

        # Provisioning's target-device pre-flight: identical reasoning
        # to technician_console.main_window's own standalone Inspection
        # pass -- see that module's docstring. start_provisioning_workflow()
        # requires a concrete StorageDevice up front, before Inspection
        # runs inside the real workflow call.
        preflight = InspectionWorkflowStage(event_bus=ctx.event_bus)
        preflight.initialize()
        try:
            preflight_report = preflight.run(
                node_name=f"{args.node_name}-preflight",
                progress_callback=_print_stage_event,
            )
        finally:
            preflight.shutdown()

        eligible = preflight_report.storage.data.eligible_for_deployment()
        chosen_devices = _select_devices_by_serial(
            eligible, args.sanitize_device_serials
        )
        provisioning_device = _resolve_provisioning_device(chosen_devices, args)

        phase_two_dir = media.phase_two_directory(ctx.media_root)
        report_dir = media.report_directory(ctx.media_root)

        summary = ctx.workflow_manager.start_provisioning_workflow(
            node_name=args.node_name,
            recovery_decision_provider=_build_recovery_decision_provider(
                args, ctx.volume_browser
            ),
            target_device_selector=lambda _report: chosen_devices,
            provisioning_target_device=provisioning_device,
            deployment_config=ctx.config_bundle.deployment,
            confirmation_provider=_build_confirmation_provider(args),
            controller_config=ctx.config_bundle.controller,
            network_config=ctx.config_bundle.network,
            cluster_config=ctx.config_bundle.cluster,
            profile_template=profile_template,
            root_password=root_password,
            phase_two_directory=phase_two_dir,
            answer_file_destination=phase_two_dir / "answer.toml",
            identity_record_destination=(
                report_dir / f"{args.node_name}-node-identity.json"
            ),
            boot_entry_id=boot_entry_id,
            manifest_filename=args.manifest_filename,
            trigger_handoff=not args.no_trigger_handoff,
            operator_identity=args.operator_identity,
            recovery_progress_callback=_print_recovery_progress,
            sanitization_progress_callback=_print_sanitization_progress,
            workflow_progress_callback=_print_stage_event,
        )
        had_warnings = bool(ctx.validation_problems)
    finally:
        ctx.close()

    _emit_summary(summary, as_json=args.json)
    return _summary_exit_code(summary, had_config_warnings=had_warnings)


# ---------------------------------------------------------------------------
# Subcommand: logs (REQ-TC-008)
# ---------------------------------------------------------------------------


def cmd_logs_list(args: argparse.Namespace) -> int:
    ctx = build_context(args.configs_dir)
    try:
        files = ctx.logging_service.list_log_files()
    finally:
        ctx.close()

    if args.json:
        print(
            json.dumps(
                [{"name": f.name, "size_bytes": f.size_bytes} for f in files],
                indent=2,
            )
        )
    elif files:
        for info in files:
            print(f"{info.name}\t{format_bytes(info.size_bytes)}")
    else:
        print("No log files found.")

    return DEPLOYMENT_SUCCESS


def cmd_logs_show(args: argparse.Namespace) -> int:
    ctx = build_context(args.configs_dir)
    try:
        try:
            content = ctx.logging_service.read_log(args.name, tail_lines=args.tail)
        except FileNotFoundError as exc:
            raise CliUsageError(str(exc)) from exc
    finally:
        ctx.close()

    print(content)
    return DEPLOYMENT_SUCCESS


def cmd_logs_export(args: argparse.Namespace) -> int:
    ctx = build_context(args.configs_dir)
    try:
        manifest = ctx.logging_service.export(args.destination)
    finally:
        ctx.close()

    print(f"Exported {len(manifest.files)} log file(s) to {args.destination}.")
    return DEPLOYMENT_SUCCESS


__all__ = [
    "CliContext",
    "CliUsageError",
    "build_context",
    "cmd_inspect",
    "cmd_logs_export",
    "cmd_logs_list",
    "cmd_logs_show",
    "cmd_provision",
    "cmd_retire",
]
