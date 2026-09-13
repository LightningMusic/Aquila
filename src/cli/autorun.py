"""
Project Aquila
=============

CLI: Unattended Boot Autorun

A third way to drive ``workflows.WorkflowManager``, alongside the
Technician Console GUI (``technician_console``, built for an operator
sitting in front of the machine clicking through dialogs) and the
flag-driven ``cli`` subcommands (``inspect``/``retire``/``provision``,
built for a script that already knows every answer before it starts).
Neither fits "plug the deployment USB into whatever computer we're
converting, and it inspects/recovers/wipes/installs with the operator
answering only the handful of unavoidable safety questions" -- the
experience actually wanted for the boot media (confirmed with the
user: this is not a Windows app run on a technician's own desktop; it
is what runs automatically when Aquila's own deployment USB boots a
*target* machine, in-RAM, no separate GUI toolkit needed).

This module is that: a single linear script, meant to be the last
line of ``Startnet.cmd`` on the deployment media (``python
X:\\Aquila\\phase1\\src\\main.py autorun``), that walks the operator
through exactly the decisions GP-001/REQ-PREP-004/005/006/007 require
an explicit human answer for -- which device(s), recover-or-skip,
retire-or-provision, the erasure phrase, a final go/no-go -- using
plain ``input()`` prompts at the WinPE console, and defaults or skips
every other decision ``cli``'s flags expose (provisioning profile
fields, ``--json``, etc.) rather than asking the operator to type them
out at a keyboard in front of the machine being converted.

Reuses ``cli.commands.build_context`` for service bring-up (identical
sequence to ``cmd_retire``/``cmd_provision``) but does **not** import
that module's progress-printing/summary helpers
(``_print_stage_event`` and friends) even though their bodies are
identical here -- they are underscore-prefixed precisely to mark them
as ``cli.commands``'s own internal detail, and importing another
module's private names across a package boundary is exactly the kind
of implementation-detail coupling SRS Section 9.1/GP-004 ("No
subsystem shall assume internal implementation details of another
subsystem") warns against. Each is under ten lines, so this module
defines its own copies rather than either breaking that encapsulation
or promoting them to `cli.commands`'s public API on this module's
behalf.

Cancellation
--------------
Answering "no" to any of the confirmation prompts below (the
target-device confirmation, an additional site-required confirmation,
the final go/no-go) raises
``common.exceptions.application.AquilaCancelledError`` from inside the
confirmation provider -- the same signal
``technician_console.dialogs`` raises on a Cancel click/window-close,
so an operator backing out here behaves identically to backing out of
the GUI Console. :func:`run_autorun` maps it (along with every other
error class ``cli.cli.main()`` handles) onto a
``common.constants.deployment`` exit code itself, since ``main.py``
dispatches straight to :func:`run_autorun` rather than through
``cli.cli.main()``.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from cli.commands import CliContext, CliUsageError, build_context
from common import media
from common.constants.deployment import (
    DEPLOYMENT_ABORTED,
    DEPLOYMENT_CANCELLED,
    DEPLOYMENT_ERROR,
    DEPLOYMENT_SUCCESS,
    DEPLOYMENT_WARNING,
    FORCE_CONFIRMATION_PHRASE,
)
from common.exceptions.application import AquilaCancelledError, AquilaError
from common.utils.formatting import format_bytes
from config.manager import ConfigurationManager
from inspection.report import HardwareInspectionReport
from models.hardware.storage import StorageDevice
from preparation.confirmations import PreparationConfirmations
from preparation.sanitizer import SanitizationProgress
from recovery.browser import RecoveryVolume, VolumeBrowser
from recovery.copier import CopyProgress
from workflows.deployment_manager import WorkflowSummary
from workflows.inspection_manager import InspectionWorkflowStage
from workflows.preparation_manager import PreparationConfirmationRequest
from workflows.progress import WorkflowStageEvent
from workflows.provisioning_manager import ProvisioningProfileTemplate
from workflows.recovery_manager import RecoveryDecision

#: The ``input()`` signature every prompt helper below takes -- overridden
#: in tests so this module never has to block on a real terminal to be
#: exercised.
InputFn = Callable[[str], str]


def _prompt(input_fn: InputFn, message: str) -> str:
    return input_fn(message).strip()


def _prompt_yes_no(input_fn: InputFn, message: str, *, default: bool) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    answer = _prompt(input_fn, message + suffix).lower()
    if not answer:
        return default
    return answer in ("y", "yes")


# ---------------------------------------------------------------------------
# Progress/summary printing -- see the module docstring for why these are
# this module's own copies rather than imports of cli.commands's private
# equivalents.
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


def _collect_readable_paths(
    browser: VolumeBrowser, volume: RecoveryVolume, relative_path: str = ""
) -> List[Path]:
    """Recursively walk ``relative_path`` within ``volume``, collecting
    every readable file (REQ-REC-002/004/005) -- identical in behavior to
    ``cli.commands._collect_readable_paths``; see the module docstring."""

    paths: List[Path] = []
    for entry in browser.browse(volume, relative_path):
        if entry.is_directory:
            paths.extend(_collect_readable_paths(browser, volume, entry.relative_path))
        elif entry.readable:
            paths.append(volume.root_path / entry.relative_path)
    return paths


def _render_summary_text(summary: WorkflowSummary) -> str:
    lines: List[str] = []
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
        lines.append(f"Inspection result: {summary.inspection_report.overall_result.name}")
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
            lines.append(f"  Node identifier: {result.identity_record.node_identifier}")
            lines.append(f"  Assigned hostname: {result.identity_record.hostname}")
        lines.append("")

    if summary.aborted and summary.abort_reason:
        lines.append(f"Halt reason: {summary.abort_reason}")

    return "\n".join(lines).rstrip("\n")


def _summary_exit_code(summary: WorkflowSummary, *, had_config_warnings: bool) -> int:
    if summary.aborted:
        return DEPLOYMENT_ABORTED
    if had_config_warnings:
        return DEPLOYMENT_WARNING
    return DEPLOYMENT_SUCCESS


# ---------------------------------------------------------------------------
# Device selection -- REQ-PREP-005, ALLOW_AUTOMATIC_DISK_SELECTION=False means
# this can never be inferred; an operator must pick from the list every time.
# ---------------------------------------------------------------------------


def parse_device_selection(raw: str, device_count: int) -> List[int]:
    """
    Parse a comma-separated 1-based selection string (``"1,3"``, or the
    literal ``"all"``) against ``device_count`` eligible devices.

    Returns 0-based indices. Raises ``CliUsageError`` on anything
    unparseable or out of range -- never guesses.
    """

    cleaned = raw.strip().lower()
    if not cleaned:
        raise CliUsageError("No device selected -- enter at least one number, or 'all'.")
    if cleaned == "all":
        return list(range(device_count))

    indices: List[int] = []
    for token in cleaned.split(","):
        token = token.strip()
        if not token.isdigit():
            raise CliUsageError(f"'{token}' is not a valid device number.")
        number = int(token)
        if not (1 <= number <= device_count):
            raise CliUsageError(
                f"{number} is out of range -- choose between 1 and {device_count}."
            )
        indices.append(number - 1)

    # De-duplicate while preserving the operator's own ordering.
    seen: set[int] = set()
    ordered: List[int] = []
    for index in indices:
        if index not in seen:
            seen.add(index)
            ordered.append(index)
    return ordered


def _select_devices_interactively(
    input_fn: InputFn, devices: List[StorageDevice]
) -> List[StorageDevice]:
    if not devices:
        raise CliUsageError(
            "No storage device eligible for deployment was detected on this "
            "machine -- nothing to retire or provision."
        )

    print("\nEligible target device(s):")
    for position, device in enumerate(devices, start=1):
        print(
            f"  [{position}] {device.model or '(unknown model)'} "
            f"[serial: {device.serial_number or 'no serial'}] "
            f"{format_bytes(device.capacity_bytes)} ({device.device_path})"
        )

    raw = _prompt(
        input_fn,
        "\nEnter the number(s) of the device(s) to use, comma-separated "
        "(or 'all'): ",
    )
    indices = parse_device_selection(raw, len(devices))
    return [devices[i] for i in indices]


def _select_provisioning_target(
    input_fn: InputFn, chosen_devices: List[StorageDevice]
) -> StorageDevice:
    if len(chosen_devices) == 1:
        return chosen_devices[0]

    print("\nMore than one device was selected -- which one gets Proxmox VE installed?")
    for position, device in enumerate(chosen_devices, start=1):
        print(f"  [{position}] {device.model or '(unknown model)'} ({device.device_path})")
    raw = _prompt(input_fn, "Enter one number: ")
    indices = parse_device_selection(raw, len(chosen_devices))
    if len(indices) != 1:
        raise CliUsageError("Exactly one provisioning target device is required.")
    return chosen_devices[indices[0]]


# ---------------------------------------------------------------------------
# Recovery decision (REQ-REC-004/005/006/016) -- same "skip, or recover whole
# volume(s)" scope as cli.commands (see that module's own docstring); the
# operator picks volumes from a printed list instead of a --recover-volume
# flag.
# ---------------------------------------------------------------------------


def build_recovery_decision_interactively(
    input_fn: InputFn,
    volume_browser: VolumeBrowser,
    volumes: List[RecoveryVolume],
) -> RecoveryDecision:
    if not volumes:
        acknowledgement = (
            "No readable data volumes were discovered on the target device(s) "
            "-- recovery skipped automatically, acknowledged by operator "
            f"at {datetime.now().isoformat(timespec='seconds')}."
        )
        print(f"\n{acknowledgement}")
        return RecoveryDecision.skip_with_acknowledgement(acknowledgement)

    print("\nDiscovered data volume(s):")
    for position, volume in enumerate(volumes, start=1):
        print(f"  [{position}] {volume.device_id} ({volume.root_path})")

    if not _prompt_yes_no(
        input_fn, "\nRecover data from these volume(s) before wiping?", default=True
    ):
        acknowledgement = _prompt(
            input_fn,
            f"Type '{FORCE_CONFIRMATION_PHRASE}' to confirm no data will be "
            "recovered before this device is sanitized (REQ-REC-016): ",
        )
        if acknowledgement != FORCE_CONFIRMATION_PHRASE:
            raise AquilaCancelledError(
                "Recovery-skip acknowledgement did not match -- aborted."
            )
        return RecoveryDecision.skip_with_acknowledgement(
            "Operator explicitly skipped recovery "
            f"({datetime.now().isoformat(timespec='seconds')})."
        )

    raw = _prompt(
        input_fn,
        "Enter volume number(s) to recover, comma-separated (or 'all'): ",
    )
    indices = parse_device_selection(raw, len(volumes))
    selected_volumes = [volumes[i] for i in indices]

    destination_raw = _prompt(
        input_fn, "Recovery destination path (another attached drive): "
    )
    if not destination_raw:
        raise CliUsageError("A recovery destination path is required.")
    destination = Path(destination_raw)

    selected_paths: List[Path] = []
    for volume in selected_volumes:
        selected_paths.extend(_collect_readable_paths(volume_browser, volume))

    if not selected_paths:
        raise CliUsageError(
            "The selected volume(s) have no readable files -- nothing to "
            "recover. Answer 'n' above to skip recovery instead."
        )

    return RecoveryDecision.recover(destination=destination, selected_paths=selected_paths)


# ---------------------------------------------------------------------------
# Preparation confirmation (REQ-PREP-004/005/006/007, REQ-TC-012)
# ---------------------------------------------------------------------------


def build_confirmation_provider_interactively(
    input_fn: InputFn,
) -> Callable[[PreparationConfirmationRequest], PreparationConfirmations]:
    def provider(request: PreparationConfirmationRequest) -> PreparationConfirmations:
        print(f"\n{request.summary_text}")
        print(
            "\nThis is the last step before permanent, irreversible data "
            "erasure begins."
        )

        target_confirmed = _prompt_yes_no(
            input_fn,
            "Confirm the device(s) listed above are the correct target(s)?",
            default=False,
        )
        if not target_confirmed:
            raise AquilaCancelledError("Target device not confirmed -- aborted.")

        typed_phrase = _prompt(
            input_fn,
            f"Type '{FORCE_CONFIRMATION_PHRASE}' to acknowledge permanent "
            "erasure: ",
        )

        extra_needed = max(0, request.required_confirmation_count - 3)
        additional: List[bool] = []
        for extra_index in range(extra_needed):
            additional.append(
                _prompt_yes_no(
                    input_fn,
                    f"Additional site-required confirmation {extra_index + 1} "
                    f"of {extra_needed} -- confirm?",
                    default=False,
                )
            )
        if extra_needed and not all(additional):
            raise AquilaCancelledError(
                "Not every additional site-required confirmation was given -- aborted."
            )

        final_approval = _prompt_yes_no(
            input_fn, "Proceed with sanitization now?", default=False
        )
        if not final_approval:
            raise AquilaCancelledError("Final approval declined -- aborted.")

        return PreparationConfirmations(
            target_device_confirmed=target_confirmed,
            erasure_acknowledgement_phrase=typed_phrase,
            final_approval=final_approval,
            additional_confirmations=tuple(additional),
        )

    return provider


# ---------------------------------------------------------------------------
# Main interactive flow
# ---------------------------------------------------------------------------


def _default_node_name() -> str:
    return f"aquila-{datetime.now():%Y%m%d-%H%M%S}"


def _run_autorun_body(ctx: CliContext, input_fn: InputFn) -> int:
    _print_validation_warnings(ctx.validation_problems)

    preflight = InspectionWorkflowStage(event_bus=ctx.event_bus)
    preflight.initialize()
    try:
        report: HardwareInspectionReport = preflight.run(
            node_name="autorun-preflight", progress_callback=_print_stage_event
        )
    finally:
        preflight.shutdown()

    firmware = report.bios.data.firmware
    print(
        f"\nSystem: {firmware.manufacturer or 'Unknown'} "
        f"{firmware.model or 'Unknown'} "
        f"(serial: {firmware.serial_number or 'unknown'})"
    )
    print(f"Inspection result: {report.overall_result.name}")

    eligible = report.storage.data.eligible_for_deployment()
    chosen_devices = _select_devices_interactively(input_fn, eligible)

    print(
        "\n[1] Retire only -- wipe the selected device(s), no OS install "
        "(SRS Appendix B, Workflow A)"
    )
    print(
        "[2] Provision -- wipe and install Proxmox VE, then enroll into "
        "the cluster (SRS Appendix B, Workflow B)"
    )
    mode = _prompt(input_fn, "Choose 1 or 2: ")
    if mode not in ("1", "2"):
        raise CliUsageError("Enter 1 or 2.")
    provisioning = mode == "2"

    provisioning_device: Optional[StorageDevice] = None
    profile_template: Optional[ProvisioningProfileTemplate] = None
    root_password: Optional[str] = None
    boot_entry_id = ""
    media_root: Optional[Path] = None

    if provisioning:
        # Fail fast on missing configuration -- same checks
        # cli.commands.cmd_provision makes -- before spending the
        # operator's time on recovery/confirmation prompts for a run
        # that cannot finish.
        boot_entry_id = ctx.config_bundle.deployment.boot_entry_id
        if not boot_entry_id:
            raise CliUsageError(
                "deployment.yaml does not set boot_entry_id -- the Build "
                "System must stamp this media with a pre-registered BCD "
                "boot entry before Provisioning can hand off to Phase Two."
            )
        domain = ctx.config_bundle.deployment.provisioning_domain
        mailto = ctx.config_bundle.deployment.provisioning_notification_email
        if not (domain and mailto):
            raise CliUsageError(
                "deployment.yaml does not set provisioning_domain and/or "
                "provisioning_notification_email -- both are required by "
                "the Proxmox VE installer (REQ-PROV-015) and cannot be "
                "left blank."
            )
        profile_template = ProvisioningProfileTemplate(domain=domain, mailto=mailto)
        root_password = ConfigurationManager.resolve_secret(
            profile_template.root_password_env_var
        )
        if not root_password:
            raise CliUsageError(
                f"Set the {profile_template.root_password_env_var} "
                "environment variable to the node's root credential before "
                "provisioning (REQ-SEC-008/009/010: never typed here)."
            )
        if ctx.media_root is None:
            raise CliUsageError(
                "Could not determine the deployment media's root directory "
                "-- Provisioning cannot write the Phase Two answer file. "
                f"Set {media.MEDIA_ROOT_ENV_VAR} to override detection."
            )
        media_root = ctx.media_root
        provisioning_device = _select_provisioning_target(input_fn, chosen_devices)

    node_name_raw = _prompt(input_fn, f"\nNode name [{_default_node_name()}]: ")
    node_name = node_name_raw or _default_node_name()

    operator_identity = (
        _prompt(input_fn, "Operator identity (optional, for the sanitization report): ")
        or None
    )

    def recovery_decision_provider(
        _report: HardwareInspectionReport, volumes: List[RecoveryVolume]
    ) -> RecoveryDecision:
        # ``volumes`` is discovered and supplied by the workflow itself
        # (the same shape ``cli.commands._build_recovery_decision_provider``
        # receives) -- this module never calls ``VolumeBrowser`` discovery
        # directly, only ``browse()`` (via ``_collect_readable_paths``) once
        # a volume has already been chosen.
        return build_recovery_decision_interactively(input_fn, ctx.volume_browser, volumes)

    confirmation_provider = build_confirmation_provider_interactively(input_fn)

    if provisioning:
        assert profile_template is not None
        assert provisioning_device is not None
        assert root_password is not None
        assert media_root is not None
        phase_two_dir = media.phase_two_directory(media_root)
        report_dir = media.report_directory(media_root)
        summary = ctx.workflow_manager.start_provisioning_workflow(
            node_name=node_name,
            recovery_decision_provider=recovery_decision_provider,
            target_device_selector=lambda _report: chosen_devices,
            provisioning_target_device=provisioning_device,
            deployment_config=ctx.config_bundle.deployment,
            confirmation_provider=confirmation_provider,
            controller_config=ctx.config_bundle.controller,
            network_config=ctx.config_bundle.network,
            cluster_config=ctx.config_bundle.cluster,
            profile_template=profile_template,
            root_password=root_password,
            phase_two_directory=phase_two_dir,
            answer_file_destination=phase_two_dir / "answer.toml",
            identity_record_destination=report_dir / f"{node_name}-node-identity.json",
            boot_entry_id=boot_entry_id,
            trigger_handoff=True,
            operator_identity=operator_identity,
            recovery_progress_callback=_print_recovery_progress,
            sanitization_progress_callback=_print_sanitization_progress,
            workflow_progress_callback=_print_stage_event,
        )
    else:
        summary = ctx.workflow_manager.start_retirement_workflow(
            node_name=node_name,
            recovery_decision_provider=recovery_decision_provider,
            target_device_selector=lambda _report: chosen_devices,
            deployment_config=ctx.config_bundle.deployment,
            confirmation_provider=confirmation_provider,
            operator_identity=operator_identity,
            recovery_progress_callback=_print_recovery_progress,
            sanitization_progress_callback=_print_sanitization_progress,
            workflow_progress_callback=_print_stage_event,
        )

    print(f"\n{_render_summary_text(summary)}")

    # A machine-readable copy always survives on the media too, regardless
    # of the human-readable console output above -- REQ-TC-013/REQ-LOG-011's
    # audit intent, for a session nobody was necessarily transcribing.
    if ctx.media_root is not None:
        try:
            report_dir = media.report_directory(ctx.media_root)
            report_dir.mkdir(parents=True, exist_ok=True)
            summary_path = report_dir / f"{node_name}-summary.json"
            summary_path.write_text(
                json.dumps(summary.to_dict(), indent=2, sort_keys=True, default=str),
                encoding="utf-8",
            )
            print(f"\nSummary written to {summary_path}")
        except OSError as exc:  # noqa: BLE001 - best-effort, never fatal here
            print(f"(Could not write the summary file: {exc})", file=sys.stderr)

    return _summary_exit_code(summary, had_config_warnings=bool(ctx.validation_problems))


def run_autorun(*, configs_dir: Optional[Path] = None, input_fn: InputFn = input) -> int:
    """
    The deployment media's unattended-boot entry point -- see the
    module docstring. Never raises: every failure mode this function's
    own code, ``build_context()``, or a workflow call can produce is
    caught here and turned into a printed message plus one of
    ``common.constants.deployment``'s exit codes, matching
    ``cli.cli.main()``'s own "never raises" contract (this function is
    reached directly from ``main.py``, not through ``cli.cli.main()``,
    so it owns that contract itself rather than inheriting it).
    """

    print("=" * 70)
    print("Project Aquila -- Deployment Autorun")
    print("=" * 70)

    try:
        ctx = build_context(configs_dir)
    except CliUsageError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return DEPLOYMENT_ERROR

    try:
        return _run_autorun_body(ctx, input_fn)
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return DEPLOYMENT_CANCELLED
    except AquilaCancelledError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return DEPLOYMENT_CANCELLED
    except CliUsageError as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return DEPLOYMENT_ERROR
    except AquilaError as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return DEPLOYMENT_ABORTED
    except Exception as exc:  # noqa: BLE001 - top-level, must not crash uncaught
        print(f"\nUnexpected error: {exc}", file=sys.stderr)
        traceback.print_exc()
        return DEPLOYMENT_ERROR
    finally:
        ctx.close()


__all__ = [
    "build_confirmation_provider_interactively",
    "build_recovery_decision_interactively",
    "parse_device_selection",
    "run_autorun",
]
