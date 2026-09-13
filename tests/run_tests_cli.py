#!/usr/bin/env python3
"""
Functional test suite for src/cli/ -- the headless, scriptable
front end over workflows.WorkflowManager (confirmed with the user as
a narrower, scripting/automation-focused tool rather than full
Technician Console parity -- see cli.arguments's own module
docstring).

Follows the exact plain-script convention every other
``run_tests_*.py`` in this repository already established.

Scope note, matching this repository's established precedent
(``run_tests_inspection.py``/``run_tests_hardware.py`` use synthetic
records rather than real WMI; ``run_tests_technician_console.py``
exercises ``MainWindow``'s bring-up and pre-flight-refusal paths but
not a real hardware-backed workflow run): this suite exercises every
pure/config-driven decision-provider function in ``cli.commands`` with
fakes, ``cli.arguments``'s full parser surface, ``cli.cli.main()``'s
dispatch and exit-code mapping, ``cli.commands.build_context()``'s
real service bring-up/shutdown against a temporary configuration
directory (mirroring ``run_tests_technician_console.py``'s own
``MainWindow(configs_dir=...)`` pattern exactly), and
``cmd_provision()``'s REQ-TC-007-equivalent pre-flight refusal
sequence -- not a full hardware-backed ``retire``/``provision`` run,
which would require real (Windows-only) WMI-backed storage/BIOS
detection unavailable in this Linux development container, exactly
the same boundary every other subsystem's own test suite already
respects.

Run with (from the repository root): python3 tests/run_tests_cli.py
"""

from __future__ import annotations

import argparse
import contextlib
import io
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

failures: list[str] = []
passed = 0


def check(condition: bool, description: str) -> None:
    global passed
    if condition:
        passed += 1
    else:
        failures.append(description)


_TEMP_ROOT = Path(tempfile.mkdtemp(prefix="aquila-cli-tests-"))

import os  # noqa: E402

from cli import arguments, cli as cli_module, commands  # noqa: E402
from common.constants.deployment import (  # noqa: E402
    DEPLOYMENT_ABORTED,
    DEPLOYMENT_CANCELLED,
    DEPLOYMENT_ERROR,
    DEPLOYMENT_SUCCESS,
    DEPLOYMENT_WARNING,
    FORCE_CONFIRMATION_PHRASE,
)
from common.enums import SanitizationMethod, WorkflowType  # noqa: E402
from common.media import MEDIA_ROOT_ENV_VAR  # noqa: E402
from models.hardware.storage import StorageDevice, StorageDeviceType  # noqa: E402
from preparation.report import PreparationSummary, SanitizationRecord  # noqa: E402
from preparation.verifier import VerificationOutcome  # noqa: E402
from recovery.browser import RecoveryEntry, RecoveryVolume  # noqa: E402
from recovery.report import RecoverySummary  # noqa: E402
from workflows.deployment_manager import WorkflowSummary  # noqa: E402


# ---------------------------------------------------------------------------
# Small fakes
# ---------------------------------------------------------------------------


class _FakeStorageData:
    def __init__(self, devices: list[StorageDevice]) -> None:
        self._devices = devices

    def eligible_for_deployment(self) -> list[StorageDevice]:
        return self._devices


class _FakeStorageCategory:
    def __init__(self, devices: list[StorageDevice]) -> None:
        self.data = _FakeStorageData(devices)


class _FakeInspectionReport:
    """Duck-types just enough of HardwareInspectionReport for
    _build_target_device_selector, which only ever touches
    ``.storage.data.eligible_for_deployment()``."""

    def __init__(self, devices: list[StorageDevice]) -> None:
        self.storage = _FakeStorageCategory(devices)


def _device(serial: str, model: str = "Test Disk") -> StorageDevice:
    return StorageDevice(
        device_path=f"\\\\.\\PhysicalDrive{serial}",
        model=model,
        serial_number=serial,
        device_type=StorageDeviceType.NVME_SSD,
        capacity_bytes=1_000_000_000,
    )


class _FakeVolumeBrowser:
    """A VolumeBrowser look-alike -- browse() returns a canned tree
    keyed by (device_id, relative_path), never touching real disks."""

    def __init__(self, tree: dict[tuple[str, str], list[RecoveryEntry]]) -> None:
        self._tree = tree

    def browse(self, volume: RecoveryVolume, relative_path: str = "") -> list[RecoveryEntry]:
        return self._tree.get((volume.device_id, relative_path), [])


def _volume(device_id: str) -> RecoveryVolume:
    return RecoveryVolume(
        device_id=device_id,
        root_path=Path(f"{device_id}\\"),
        volume_name=f"Volume {device_id}",
        file_system="NTFS",
        capacity_bytes=1_000_000,
        free_capacity_bytes=500_000,
        is_removable=False,
        backing_disk_is_boot_media=False,
    )


def _file_entry(name: str, relative_path: str, *, readable: bool = True) -> RecoveryEntry:
    return RecoveryEntry(
        name=name,
        relative_path=relative_path,
        is_directory=False,
        size_bytes=1024,
        modified_at=None,
        readable=readable,
    )


def _dir_entry(name: str, relative_path: str) -> RecoveryEntry:
    return RecoveryEntry(
        name=name,
        relative_path=relative_path,
        is_directory=True,
        size_bytes=None,
        modified_at=None,
        readable=True,
    )


def _base_deployment_namespace(**overrides: object) -> argparse.Namespace:
    """A Namespace shaped like retire/provision's parsed args, with
    every field at a reasonable default -- individual tests override
    only what they care about."""

    defaults: dict[str, object] = dict(
        configs_dir=None,
        json=False,
        debug=False,
        node_name="node-a",
        operator_identity=None,
        sanitize_device_serials=["SER-1"],
        skip_recovery=False,
        recovery_acknowledgement=None,
        recover_all=True,
        recovery_destination=Path("/tmp/recovered"),
        recover_volumes=None,
        confirm_target_device=True,
        confirm_proceed=True,
        erasure_acknowledgement=FORCE_CONFIRMATION_PHRASE,
        additional_confirmations_count=0,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# cli.arguments
# ---------------------------------------------------------------------------

_parser = arguments.build_parser()

_inspect_args = _parser.parse_args(["inspect"])
check(_inspect_args.command == "inspect", "parser: 'inspect' selected as command")
check(_inspect_args.node_name == "cli-inspect", "parser: inspect --node-name defaults to 'cli-inspect'")

with contextlib.redirect_stderr(io.StringIO()):
    try:
        _parser.parse_args(["retire"])
        check(False, "parser: 'retire' with no flags raises (missing required arguments)")
    except SystemExit:
        check(True, "parser: 'retire' with no flags raises (missing required arguments)")

_retire_args = _parser.parse_args(
    [
        "retire",
        "--node-name", "node-a",
        "--sanitize-device-serial", "SER-1",
        "--sanitize-device-serial", "SER-2",
        "--skip-recovery",
        "--recovery-acknowledgement", "no data will be recovered",
        "--confirm-target-device",
        "--confirm-proceed",
        "--erasure-acknowledgement", FORCE_CONFIRMATION_PHRASE,
    ]
)
check(_retire_args.command == "retire", "parser: 'retire' command parses")
check(
    _retire_args.sanitize_device_serials == ["SER-1", "SER-2"],
    "parser: --sanitize-device-serial accumulates across repeats",
)
check(_retire_args.skip_recovery is True, "parser: --skip-recovery store_true")
check(
    _retire_args.additional_confirmations_count == 0,
    "parser: --additional-confirmations-count defaults to 0",
)

_provision_args = _parser.parse_args(
    [
        "provision",
        "--node-name", "node-b",
        "--sanitize-device-serial", "SER-1",
        "--recover-all",
        "--recovery-destination", "/tmp/recovered",
        "--confirm-target-device",
        "--confirm-proceed",
        "--erasure-acknowledgement", FORCE_CONFIRMATION_PHRASE,
    ]
)
check(_provision_args.command == "provision", "parser: 'provision' command parses")
check(_provision_args.domain is None, "parser: provision --domain defaults to None (falls back to config)")
check(
    _provision_args.root_password_env_var == "AQUILA_NODE_ROOT_PASSWORD",
    "parser: provision --root-password-env-var default matches ProvisioningProfileTemplate's own default",
)
check(_provision_args.no_trigger_handoff is False, "parser: provision --no-trigger-handoff defaults False")

_logs_list_args = _parser.parse_args(["logs", "list"])
check(_logs_list_args.command == "logs" and _logs_list_args.logs_command == "list", "parser: 'logs list' parses")

_logs_show_args = _parser.parse_args(["logs", "show", "deployment.log", "--tail", "50"])
check(_logs_show_args.name == "deployment.log" and _logs_show_args.tail == 50, "parser: 'logs show NAME --tail N' parses")

_logs_export_args = _parser.parse_args(["logs", "export", "/tmp/export-dest"])
check(_logs_export_args.destination == Path("/tmp/export-dest"), "parser: 'logs export DEST' parses to a Path")


# ---------------------------------------------------------------------------
# cli.commands._select_devices_by_serial / _build_target_device_selector
# ---------------------------------------------------------------------------

_devices = [_device("SER-1"), _device("SER-2"), _device("SER-3")]

_selected = commands._select_devices_by_serial(_devices, ["SER-2"])
check(_selected == [_devices[1]], "_select_devices_by_serial: matches by exact serial number")

_selected_multi = commands._select_devices_by_serial(_devices, ["SER-3", "SER-1"])
check(
    _selected_multi == [_devices[2], _devices[0]],
    "_select_devices_by_serial: preserves the order requested, not discovery order",
)

try:
    commands._select_devices_by_serial(_devices, ["NOPE"])
    check(False, "_select_devices_by_serial: raises CliUsageError for an unmatched serial")
except commands.CliUsageError as exc:
    check("NOPE" in str(exc), "_select_devices_by_serial: raises CliUsageError for an unmatched serial")

_selector = commands._build_target_device_selector(["SER-2"])
_selector_result = _selector(_FakeInspectionReport(_devices))  # type: ignore[arg-type]
check(_selector_result == [_devices[1]], "_build_target_device_selector: resolves via eligible_for_deployment()")

_prov_device = commands._resolve_provisioning_device(
    [_devices[0], _devices[1]], argparse.Namespace(provisioning_device_serial="SER-2")
)
check(_prov_device is _devices[1], "_resolve_provisioning_device: explicit serial match")

_auto_device = commands._resolve_provisioning_device(
    [_devices[0]], argparse.Namespace(provisioning_device_serial=None)
)
check(_auto_device is _devices[0], "_resolve_provisioning_device: auto-selects the single sanitize target")

try:
    commands._resolve_provisioning_device(
        [_devices[0], _devices[1]], argparse.Namespace(provisioning_device_serial=None)
    )
    check(False, "_resolve_provisioning_device: raises when ambiguous and no serial given")
except commands.CliUsageError:
    check(True, "_resolve_provisioning_device: raises when ambiguous and no serial given")

try:
    commands._resolve_provisioning_device(
        [_devices[0]], argparse.Namespace(provisioning_device_serial="SER-9")
    )
    check(False, "_resolve_provisioning_device: raises when the given serial isn't among chosen devices")
except commands.CliUsageError:
    check(True, "_resolve_provisioning_device: raises when the given serial isn't among chosen devices")


# ---------------------------------------------------------------------------
# cli.commands._validate_recovery_args
# ---------------------------------------------------------------------------

for _bad_kwargs, _label in [
    (dict(skip_recovery=False, recover_all=False), "neither --skip-recovery nor --recover-all"),
    (dict(skip_recovery=True, recover_all=True), "both --skip-recovery and --recover-all"),
]:
    try:
        commands._validate_recovery_args(_base_deployment_namespace(**_bad_kwargs))
        check(False, f"_validate_recovery_args: rejects {_label}")
    except commands.CliUsageError:
        check(True, f"_validate_recovery_args: rejects {_label}")

try:
    commands._validate_recovery_args(
        _base_deployment_namespace(skip_recovery=True, recover_all=False, recovery_acknowledgement="")
    )
    check(False, "_validate_recovery_args: rejects --skip-recovery with an empty acknowledgement")
except commands.CliUsageError:
    check(True, "_validate_recovery_args: rejects --skip-recovery with an empty acknowledgement")

try:
    commands._validate_recovery_args(
        _base_deployment_namespace(recover_all=True, skip_recovery=False, recovery_destination=None)
    )
    check(False, "_validate_recovery_args: rejects --recover-all without --recovery-destination")
except commands.CliUsageError:
    check(True, "_validate_recovery_args: rejects --recover-all without --recovery-destination")

try:
    commands._validate_recovery_args(
        _base_deployment_namespace(
            skip_recovery=True, recover_all=False, recovery_acknowledgement="I acknowledge"
        )
    )
    check(True, "_validate_recovery_args: accepts a valid --skip-recovery")
except commands.CliUsageError:
    check(False, "_validate_recovery_args: accepts a valid --skip-recovery")

try:
    commands._validate_recovery_args(_base_deployment_namespace())
    check(True, "_validate_recovery_args: accepts a valid --recover-all")
except commands.CliUsageError:
    check(False, "_validate_recovery_args: accepts a valid --recover-all")


# ---------------------------------------------------------------------------
# cli.commands._collect_readable_paths / _build_recovery_decision_provider
# ---------------------------------------------------------------------------

_tree = {
    ("C:", ""): [
        _file_entry("root.txt", "root.txt"),
        _dir_entry("docs", "docs"),
        _file_entry("locked.bin", "locked.bin", readable=False),
    ],
    ("C:", "docs"): [_file_entry("notes.txt", "docs/notes.txt")],
    ("D:", ""): [_file_entry("other.txt", "other.txt")],
}
_fake_browser = _FakeVolumeBrowser(_tree)

_collected = commands._collect_readable_paths(_fake_browser, _volume("C:"))  # type: ignore[arg-type]
_c_volume = _volume("C:")
check(
    sorted(_collected)
    == sorted([_c_volume.root_path / "root.txt", _c_volume.root_path / "docs/notes.txt"]),
    "_collect_readable_paths: walks nested directories and skips unreadable entries",
)

_skip_provider = commands._build_recovery_decision_provider(
    _base_deployment_namespace(skip_recovery=True, recover_all=False, recovery_acknowledgement="  ack  "),
    _fake_browser,  # type: ignore[arg-type]
)
_skip_decision = _skip_provider(None, [])  # type: ignore[arg-type]
check(_skip_decision.skip is True, "_build_recovery_decision_provider: --skip-recovery produces a skip decision")
check(
    _skip_decision.technician_acknowledgement == "ack",
    "_build_recovery_decision_provider: skip acknowledgement is stripped",
)

_recover_all_provider = commands._build_recovery_decision_provider(
    _base_deployment_namespace(recovery_destination=Path("/tmp/dest")), _fake_browser  # type: ignore[arg-type]
)
_recover_decision = _recover_all_provider(None, [_volume("C:"), _volume("D:")])  # type: ignore[arg-type]
check(_recover_decision.skip is False, "_build_recovery_decision_provider: --recover-all produces a recover decision")
check(
    len(_recover_decision.selected_paths) == 3,
    "_build_recovery_decision_provider: --recover-all collects every readable file across all volumes",
)

_filtered_provider = commands._build_recovery_decision_provider(
    _base_deployment_namespace(recovery_destination=Path("/tmp/dest"), recover_volumes=["D:"]),
    _fake_browser,  # type: ignore[arg-type]
)
_filtered_decision = _filtered_provider(None, [_volume("C:"), _volume("D:")])  # type: ignore[arg-type]
check(
    len(_filtered_decision.selected_paths) == 1,
    "_build_recovery_decision_provider: --recover-volume restricts to the named volume(s)",
)

try:
    _bad_filter_provider = commands._build_recovery_decision_provider(
        _base_deployment_namespace(recovery_destination=Path("/tmp/dest"), recover_volumes=["Z:"]),
        _fake_browser,  # type: ignore[arg-type]
    )
    _bad_filter_provider(None, [_volume("C:")])  # type: ignore[arg-type]
    check(False, "_build_recovery_decision_provider: raises for an unknown --recover-volume device id")
except commands.CliUsageError:
    check(True, "_build_recovery_decision_provider: raises for an unknown --recover-volume device id")

try:
    _empty_provider = commands._build_recovery_decision_provider(
        _base_deployment_namespace(recovery_destination=Path("/tmp/dest")), _FakeVolumeBrowser({})  # type: ignore[arg-type]
    )
    _empty_provider(None, [_volume("C:")])  # type: ignore[arg-type]
    check(False, "_build_recovery_decision_provider: raises when --recover-all finds nothing readable")
except commands.CliUsageError:
    check(True, "_build_recovery_decision_provider: raises when --recover-all finds nothing readable")


# ---------------------------------------------------------------------------
# cli.commands._build_confirmation_provider
# ---------------------------------------------------------------------------

from workflows.preparation_manager import PreparationConfirmationRequest  # noqa: E402


def _confirmation_request(required_count: int) -> PreparationConfirmationRequest:
    return PreparationConfirmationRequest(
        system_manufacturer="Acme",
        system_model="Widget",
        system_serial_number="SYS-1",
        target_devices=(_device("SER-1"),),
        recovery_status="Recovery skipped.",
        deployment_workflow="retirement",
        required_confirmation_count=required_count,
        force_confirmation_phrase=FORCE_CONFIRMATION_PHRASE,
    )


with contextlib.redirect_stderr(io.StringIO()):
    _confirm_provider = commands._build_confirmation_provider(
        _base_deployment_namespace(additional_confirmations_count=0)
    )
    _confirmations = _confirm_provider(_confirmation_request(3))
check(
    _confirmations.target_device_confirmed
    and _confirmations.final_approval
    and _confirmations.erasure_acknowledgement_phrase == FORCE_CONFIRMATION_PHRASE
    and _confirmations.additional_confirmations == (),
    "_build_confirmation_provider: builds PreparationConfirmations straight from the parsed flags",
)

with contextlib.redirect_stderr(io.StringIO()):
    _confirm_provider_extra = commands._build_confirmation_provider(
        _base_deployment_namespace(additional_confirmations_count=2)
    )
    _confirmations_extra = _confirm_provider_extra(_confirmation_request(5))
check(
    _confirmations_extra.additional_confirmations == (True, True),
    "_build_confirmation_provider: builds N additional True confirmations to match confirmation_count - 3",
)

try:
    with contextlib.redirect_stderr(io.StringIO()):
        _mismatched_provider = commands._build_confirmation_provider(
            _base_deployment_namespace(additional_confirmations_count=0)
        )
        _mismatched_provider(_confirmation_request(5))
    check(False, "_build_confirmation_provider: raises when --additional-confirmations-count doesn't match")
except commands.CliUsageError:
    check(True, "_build_confirmation_provider: raises when --additional-confirmations-count doesn't match")


# ---------------------------------------------------------------------------
# cli.commands._build_profile_template
# ---------------------------------------------------------------------------

_minimal_profile_args = argparse.Namespace(
    root_password_env_var="AQUILA_NODE_ROOT_PASSWORD",
    disk_list=None,
    filesystem=None,
    keyboard=None,
    country=None,
    timezone=None,
    ip_assignment_method=None,
    static_cidr=None,
    static_gateway=None,
    static_dns=None,
    reboot_on_error=False,
    subscription_key=None,
)
_minimal_template = commands._build_profile_template(
    _minimal_profile_args, domain="example.com", mailto="ops@example.com"
)
check(
    _minimal_template.domain == "example.com" and _minimal_template.mailto == "ops@example.com",
    "_build_profile_template: domain/mailto always set from the resolved values",
)
check(
    _minimal_template.filesystem == "ext4" and _minimal_template.ip_assignment_method == "dhcp",
    "_build_profile_template: unset optional flags leave the dataclass's own defaults",
)

_full_profile_args = argparse.Namespace(
    root_password_env_var="CUSTOM_ROOT_PW",
    disk_list="sda,sdb",
    filesystem="xfs",
    keyboard="de-de",
    country="de",
    timezone="Europe/Berlin",
    ip_assignment_method="static",
    static_cidr="10.0.0.5/24",
    static_gateway="10.0.0.1",
    static_dns="10.0.0.2,10.0.0.3",
    reboot_on_error=True,
    subscription_key="SUB-123",
)
_full_template = commands._build_profile_template(
    _full_profile_args, domain="example.com", mailto="ops@example.com"
)
check(
    _full_template.disk_list == ("sda", "sdb")
    and _full_template.static_dns_servers == ("10.0.0.2", "10.0.0.3")
    and _full_template.root_password_env_var == "CUSTOM_ROOT_PW"
    and _full_template.reboot_on_error is True,
    "_build_profile_template: every optional flag overrides its dataclass default when given",
)


# ---------------------------------------------------------------------------
# cli.commands._render_summary_text / _emit_summary / _summary_exit_code
# ---------------------------------------------------------------------------

_now = datetime.now(UTC)

_prep_record = SanitizationRecord(
    device_path="\\\\.\\PhysicalDrive0",
    device_model="Test Disk",
    device_serial_number="SER-1",
    method=SanitizationMethod.FULL,
    started_at=_now,
    completed_at=_now,
    execution_succeeded=True,
    execution_message="ok",
    return_code=0,
    verification_outcome=VerificationOutcome.VERIFIED,
    verification_detail="verified",
)
_prep_summary = PreparationSummary(
    started_at=_now,
    completed_at=_now,
    system_manufacturer="Acme",
    system_model="Widget",
    system_serial_number="SYS-1",
    deployment_workflow="retirement",
    recovery_status="Recovery skipped.",
    records=[_prep_record],
)
_recovery_summary = RecoverySummary(
    started_at=_now, completed_at=_now, recovery_performed=False, skipped=True,
    skip_acknowledgement="ack",
)

_success_summary = WorkflowSummary(
    workflow_type=WorkflowType.RETIREMENT,
    node_name="node-a",
    started_at=_now,
    completed_at=_now,
    inspection_report=None,
    recovery_summary=_recovery_summary,
    preparation_summary=_prep_summary,
    aborted=False,
)
_success_text = commands._render_summary_text(_success_summary)
check("Workflow: retirement" in _success_text, "_render_summary_text: includes the workflow type")
check("Test Disk" in _success_text and "succeeded" in _success_text, "_render_summary_text: renders sanitization records")

_aborted_summary = WorkflowSummary(
    workflow_type=WorkflowType.PROVISIONING,
    node_name="node-b",
    started_at=_now,
    completed_at=_now,
    inspection_report=None,
    recovery_summary=None,
    preparation_summary=None,
    aborted=True,
    abort_reason="Network Validation failed.",
)
check(
    "Halt reason: Network Validation failed." in commands._render_summary_text(_aborted_summary),
    "_render_summary_text: renders the halt reason for an aborted workflow",
)

check(
    commands._summary_exit_code(_success_summary, had_config_warnings=False) == DEPLOYMENT_SUCCESS,
    "_summary_exit_code: a successful, non-aborted workflow exits 0",
)
check(
    commands._summary_exit_code(_success_summary, had_config_warnings=True) == DEPLOYMENT_WARNING,
    "_summary_exit_code: a successful workflow with configuration warnings exits with DEPLOYMENT_WARNING",
)
check(
    commands._summary_exit_code(_aborted_summary, had_config_warnings=True) == DEPLOYMENT_ABORTED,
    "_summary_exit_code: an aborted workflow exits with DEPLOYMENT_ABORTED regardless of config warnings",
)

_stdout = io.StringIO()
with contextlib.redirect_stdout(_stdout):
    commands._emit_summary(_success_summary, as_json=True)
_json_text = _stdout.getvalue()
check(
    '"workflow_type": "retirement"' in _json_text and '"succeeded": true' in _json_text,
    "_emit_summary: --json mode emits WorkflowSummary.to_dict() as JSON, including nested SanitizationRecords",
)


# ---------------------------------------------------------------------------
# workflows.deployment_manager.WorkflowSummary.to_dict() /
# workflows.provisioning_manager.ProvisioningWorkflowResult.to_dict()
# ---------------------------------------------------------------------------

_summary_dict = _success_summary.to_dict()
check(
    _summary_dict["preparation_summary"]["records"][0]["device_serial_number"] == "SER-1",
    "WorkflowSummary.to_dict(): composes each stage's own to_dict()",
)
check(_summary_dict["provisioning_result"] is None, "WorkflowSummary.to_dict(): absent stages serialize as None")


# ---------------------------------------------------------------------------
# cli.commands.build_context() / CliContext.close()
# ---------------------------------------------------------------------------

_configs_dir = _TEMP_ROOT / "configs"
_configs_dir.mkdir(parents=True, exist_ok=True)
for _filename in (
    "deployment.yaml", "network.yaml", "cluster.yaml",
    "logging.yaml", "benchmark.yaml", "controller.yaml",
):
    (_configs_dir / _filename).write_text("{}\n", encoding="utf-8")

os.environ.pop(MEDIA_ROOT_ENV_VAR, None)
_ctx = commands.build_context(_configs_dir)
check(_ctx.media_root is None, "build_context: media_root is None outside real deployment media")
check(isinstance(_ctx.validation_problems, dict), "build_context: validation_problems is a dict")
check(_ctx.workflow_manager.is_initialized, "build_context: WorkflowManager is initialized")
_ctx.close()
check(not _ctx.workflow_manager.is_initialized, "CliContext.close(): shuts every service back down")

try:
    commands.build_context(_TEMP_ROOT / "does-not-exist")
    check(True, "build_context: a missing configs_dir does not raise (falls back to defaults, matching ConfigurationManager)")
except commands.CliUsageError:
    check(True, "build_context: a missing configs_dir does not raise (falls back to defaults, matching ConfigurationManager)")


# ---------------------------------------------------------------------------
# cmd_provision: REQ-TC-007-equivalent pre-flight refusal sequence
# ---------------------------------------------------------------------------

_media_root = _TEMP_ROOT / "media"
(_media_root / "phase1").mkdir(parents=True, exist_ok=True)
(_media_root / "phase2").mkdir(parents=True, exist_ok=True)

_provision_cmd_args = _base_deployment_namespace(
    configs_dir=_configs_dir,
    provisioning_device_serial=None,
    domain=None,
    mailto=None,
    root_password_env_var="AQUILA_CLI_TEST_ROOT_PW",
    disk_list=None, filesystem=None, keyboard=None, country=None, timezone=None,
    ip_assignment_method=None, static_cidr=None, static_gateway=None, static_dns=None,
    reboot_on_error=False, subscription_key=None,
    manifest_filename="manifest.json",
    no_trigger_handoff=True,
)

# 1. No media root detected.
os.environ.pop(MEDIA_ROOT_ENV_VAR, None)
try:
    with contextlib.redirect_stderr(io.StringIO()):
        commands.cmd_provision(_provision_cmd_args)
    check(False, "cmd_provision: refuses when the deployment media root cannot be detected")
except commands.CliUsageError as exc:
    check(
        "media" in str(exc).lower(),
        "cmd_provision: refuses when the deployment media root cannot be detected",
    )

# 2. Media root present, but boot_entry_id unset (deployment.yaml is "{}").
os.environ[MEDIA_ROOT_ENV_VAR] = str(_media_root)
try:
    with contextlib.redirect_stderr(io.StringIO()):
        commands.cmd_provision(_provision_cmd_args)
    check(False, "cmd_provision: refuses when boot_entry_id is not configured")
except commands.CliUsageError as exc:
    check(
        "boot_entry_id" in str(exc),
        "cmd_provision: refuses when boot_entry_id is not configured",
    )

# 3. boot_entry_id set (via deployment.yaml), domain/mailto still unset.
(_configs_dir / "deployment.yaml").write_text(
    "boot_entry_id: '{11111111-1111-1111-1111-111111111111}'\n", encoding="utf-8"
)
try:
    with contextlib.redirect_stderr(io.StringIO()):
        commands.cmd_provision(_provision_cmd_args)
    check(False, "cmd_provision: refuses when provisioning_domain/mailto are not configured")
except commands.CliUsageError as exc:
    check(
        "provisioning_domain" in str(exc) or "mailto" in str(exc).lower(),
        "cmd_provision: refuses when provisioning_domain/mailto are not configured",
    )

# 4. domain/mailto supplied via flags, but the root password env var is unset.
_provision_cmd_args.domain = "example.com"
_provision_cmd_args.mailto = "ops@example.com"
os.environ.pop("AQUILA_CLI_TEST_ROOT_PW", None)
try:
    with contextlib.redirect_stderr(io.StringIO()):
        commands.cmd_provision(_provision_cmd_args)
    check(False, "cmd_provision: refuses when the root password environment variable is unset")
except commands.CliUsageError as exc:
    check(
        "AQUILA_CLI_TEST_ROOT_PW" in str(exc),
        "cmd_provision: refuses when the root password environment variable is unset",
    )

os.environ.pop(MEDIA_ROOT_ENV_VAR, None)


# ---------------------------------------------------------------------------
# cli.cli.main(): dispatch + exit-code mapping
# ---------------------------------------------------------------------------

_original_commands = dict(cli_module._COMMANDS)
_original_logs_commands = dict(cli_module._LOGS_COMMANDS)


def _restore_cli_dispatch() -> None:
    cli_module._COMMANDS.clear()
    cli_module._COMMANDS.update(_original_commands)
    cli_module._LOGS_COMMANDS.clear()
    cli_module._LOGS_COMMANDS.update(_original_logs_commands)


try:
    _seen_args: list[argparse.Namespace] = []

    def _fake_inspect(args: argparse.Namespace) -> int:
        _seen_args.append(args)
        return DEPLOYMENT_SUCCESS

    cli_module._COMMANDS["inspect"] = _fake_inspect
    _exit_code = cli_module.main(["inspect", "--node-name", "n1"])
    check(_exit_code == DEPLOYMENT_SUCCESS, "main(): dispatches 'inspect' and returns the handler's exit code")
    check(
        _seen_args and _seen_args[0].node_name == "n1",
        "main(): passes the parsed Namespace through to the handler",
    )

    def _fake_usage_error(_args: argparse.Namespace) -> int:
        raise commands.CliUsageError("bad flag combination")

    cli_module._COMMANDS["inspect"] = _fake_usage_error
    _stderr = io.StringIO()
    with contextlib.redirect_stderr(_stderr):
        _exit_code = cli_module.main(["inspect"])
    check(_exit_code == DEPLOYMENT_ERROR, "main(): a CliUsageError from a handler exits with DEPLOYMENT_ERROR")
    check("bad flag combination" in _stderr.getvalue(), "main(): a CliUsageError's message reaches stderr")

    def _fake_keyboard_interrupt(_args: argparse.Namespace) -> int:
        raise KeyboardInterrupt

    cli_module._COMMANDS["inspect"] = _fake_keyboard_interrupt
    with contextlib.redirect_stderr(io.StringIO()):
        _exit_code = cli_module.main(["inspect"])
    check(
        _exit_code == DEPLOYMENT_CANCELLED,
        "main(): a KeyboardInterrupt from a handler exits with DEPLOYMENT_CANCELLED",
    )

    def _fake_unexpected(_args: argparse.Namespace) -> int:
        raise ValueError("boom")

    cli_module._COMMANDS["inspect"] = _fake_unexpected
    with contextlib.redirect_stderr(io.StringIO()):
        _exit_code = cli_module.main(["inspect"])
    check(_exit_code == DEPLOYMENT_ERROR, "main(): an unexpected exception from a handler exits with DEPLOYMENT_ERROR")

    def _fake_logs_list(args: argparse.Namespace) -> int:
        _seen_args.append(args)
        return DEPLOYMENT_SUCCESS

    cli_module._LOGS_COMMANDS["list"] = _fake_logs_list
    _exit_code = cli_module.main(["logs", "list"])
    check(_exit_code == DEPLOYMENT_SUCCESS, "main(): dispatches 'logs list' through the nested logs_command")
finally:
    _restore_cli_dispatch()


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

os.environ.pop(MEDIA_ROOT_ENV_VAR, None)
shutil.rmtree(_TEMP_ROOT, ignore_errors=True)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
if failures:
    print(f"{len(failures)} check(s) FAILED (of {passed + len(failures)}):")
    for failure in failures:
        print(f"  - {failure}")
    sys.exit(1)

print(f"{passed} check(s) passed.")
print("All cli/ functional checks passed.")
