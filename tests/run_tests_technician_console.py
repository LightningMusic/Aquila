#!/usr/bin/env python3
"""
Functional test suite for src/technician_console/ (REQ-TC-001 through
REQ-TC-013's GUI front end).

Follows the exact plain-script convention every other
``run_tests_*.py`` in this repository already established, extended
with the real-widget-construction coverage this package specifically
needs: every module here imports ``tkinter``, so its logic cannot be
exercised at all through mocks/stubs alone -- real ``ttk``/``tk``
widgets are built against a real (if headless) Tk display, and driven
programmatically (direct method calls, ``after()``-scheduled
simulated technician actions pumped through ``wait_window()``'s own
event processing) rather than by literally waiting on human input.

Environment requirement
--------------------------
This suite needs a working Tcl/Tk runtime and a display. This
repository's own tracked development interpreter (``python3`` /
python 3.11) was built without Tcl/Tk bindings (confirmed: ``import
tkinter`` raises ``ModuleNotFoundError`` under it) -- a fact specific
to *this Linux development container*, unrelated to the real WinPE
deployment target (see ``technician_console/__init__.py``'s module
docstring for the confirmed WinPE/Tkinter compatibility research).
Run this suite with a Python interpreter that does have Tk bindings
under a virtual display, for example::

    xvfb-run -a python3.12 run_tests_technician_console.py

If Tkinter cannot be imported at all, this script fails fast with an
explicit, actionable message below rather than a bare traceback.

Run with (from the repository root): xvfb-run -a python3.12 tests/run_tests_technician_console.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

failures: list[str] = []
passed = 0


def check(condition: bool, description: str) -> None:
    global passed
    if condition:
        passed += 1
    else:
        failures.append(description)


try:
    import tkinter as tk
except ModuleNotFoundError:
    print(
        "FATAL: this Python interpreter has no working 'tkinter' "
        "module (technician_console/ cannot be imported or tested "
        "without it). Install Tcl/Tk bindings for the interpreter "
        "you're using (e.g. 'apt-get install python3-tk' for the "
        "matching system Python) and run this suite under a display "
        "-- 'xvfb-run -a <python-with-tkinter> "
        "run_tests_technician_console.py' in a headless environment.",
        file=sys.stderr,
    )
    sys.exit(1)


_TEMP_ROOT = Path(tempfile.mkdtemp(prefix="aquila-technician-console-tests-"))

from common.enums import WorkflowType  # noqa: E402
from common.exceptions.application import (  # noqa: E402
    AquilaCancelledError,
    AquilaEnvironmentError,
    AquilaInitializationError,
)
from models.hardware.storage import StorageDevice, StorageDeviceType  # noqa: E402
from common.constants.deployment import FORCE_CONFIRMATION_PHRASE  # noqa: E402
from preparation.confirmations import PreparationConfirmations  # noqa: E402
from recovery.browser import RecoveryEntry, RecoveryVolume  # noqa: E402
from services.logging_service import LogFileInfo, LoggingService  # noqa: E402
from workflows.deployment_manager import WorkflowSummary  # noqa: E402
from workflows.preparation_manager import PreparationConfirmationRequest  # noqa: E402
from workflows.progress import WorkflowStageEvent  # noqa: E402
from workflows.provisioning_manager import ProvisioningProfileTemplate  # noqa: E402

from technician_console import dialogs, media  # noqa: E402
from technician_console.main_window import MainWindow  # noqa: E402
from technician_console.progress import ProgressPanel, format_bytes  # noqa: E402
from technician_console.status_panel import StatusPanel  # noqa: E402
from technician_console.thread_bridge import (  # noqa: E402
    PUMP_INTERVAL_MS,
    MainThreadBridge,
)
from technician_console.workflow_selector import WorkflowSelectorPanel  # noqa: E402


def _device(path: str = "\\\\.\\PhysicalDrive0", **overrides: Any) -> StorageDevice:
    fields: dict[str, Any] = dict(
        device_path=path,
        model="Acme NVMe 512",
        manufacturer="Acme",
        serial_number="SN-1",
        device_type=StorageDeviceType.NVME_SSD,
        capacity_bytes=512_000_000_000,
        is_removable=False,
        is_system_disk=False,
        is_boot_media=False,
    )
    fields.update(overrides)
    return StorageDevice(**fields)


# ---------------------------------------------------------------------------
# technician_console.thread_bridge.MainThreadBridge -- no Tk root needed
# ---------------------------------------------------------------------------

_bridge = MainThreadBridge()

_posted: list[str] = []
_bridge.post(lambda: _posted.append("a"))
_bridge.post(lambda: _posted.append("b"))
check(_posted == [], "MainThreadBridge.post() does not run the callback immediately")
_bridge.pump()
check(_posted == ["a", "b"], "MainThreadBridge.pump() drains queued callbacks in FIFO order")
_bridge.pump()
check(_posted == ["a", "b"], "MainThreadBridge.pump() is a no-op when the queue is empty")

try:
    _bridge.call_blocking(lambda: 1)
    check(False, "MainThreadBridge.call_blocking() from the main thread raises RuntimeError")
except RuntimeError:
    check(True, "MainThreadBridge.call_blocking() from the main thread raises RuntimeError")

_blocking_results: dict[str, Any] = {}


def _worker_call_blocking() -> None:
    try:
        _blocking_results["value"] = _bridge.call_blocking(lambda: 42)
    except BaseException as exc:  # noqa: BLE001
        _blocking_results["error"] = exc


_worker = threading.Thread(target=_worker_call_blocking, daemon=True)
_worker.start()
# Give the worker a moment to enqueue its request, then pump it from "the
# main thread" (this test's own thread, which is fine -- pump() has no
# thread-affinity check of its own, only call_blocking() does).
for _ in range(50):
    time.sleep(0.01)
    _bridge.pump()
    if "value" in _blocking_results:
        break
_worker.join(timeout=2)
check(
    # NFR-PERF-003: this is the exact mechanism that keeps a running
    # workflow's own thread from blocking the Tk main thread -- a
    # technician decision made on the main thread crosses back to the
    # waiting worker thread through this queue/event round trip
    # instead of the worker calling into Tk (or the main loop) itself.
    _blocking_results.get("value") == 42,
    "MainThreadBridge.call_blocking() returns the main-thread callable's result to the worker thread",
)


class _BridgeTestError(RuntimeError):
    pass


_error_results: dict[str, Any] = {}


def _raise_on_main_thread() -> int:
    raise _BridgeTestError("boom")


def _worker_call_blocking_error() -> None:
    try:
        _bridge.call_blocking(_raise_on_main_thread)
    except BaseException as exc:  # noqa: BLE001
        _error_results["error"] = exc


_worker2 = threading.Thread(target=_worker_call_blocking_error, daemon=True)
_worker2.start()
for _ in range(50):
    time.sleep(0.01)
    _bridge.pump()
    if "error" in _error_results:
        break
_worker2.join(timeout=2)
check(
    isinstance(_error_results.get("error"), _BridgeTestError),
    "MainThreadBridge.call_blocking() re-raises the main-thread callable's exception on the caller's thread",
)


# ---------------------------------------------------------------------------
# technician_console.media -- no Tk root needed
# ---------------------------------------------------------------------------

_media_root = _TEMP_ROOT / "media_ok"
(_media_root / "phase1").mkdir(parents=True)
(_media_root / "phase2").mkdir(parents=True)

check(
    media.detect_media_root(start=(_media_root / "phase1" / "src" / "pkg" / "mod.py"))
    == _media_root,
    "detect_media_root() finds the nearest ancestor with sibling phase1/phase2 directories",
)

_no_media_root = _TEMP_ROOT / "no_media" / "a" / "b" / "c"
_no_media_root.mkdir(parents=True)
try:
    media.detect_media_root(start=_no_media_root / "mod.py")
    check(False, "detect_media_root() raises AquilaEnvironmentError when no ancestor matches")
except AquilaEnvironmentError:
    check(True, "detect_media_root() raises AquilaEnvironmentError when no ancestor matches")

os.environ[media.MEDIA_ROOT_ENV_VAR] = str(_media_root)
try:
    check(
        media.detect_media_root() == _media_root.resolve(),
        "detect_media_root() honors the AQUILA_MEDIA_ROOT environment variable override",
    )
finally:
    os.environ.pop(media.MEDIA_ROOT_ENV_VAR, None)

os.environ[media.MEDIA_ROOT_ENV_VAR] = str(_TEMP_ROOT / "no_media")
try:
    media.detect_media_root()
    check(
        False,
        "detect_media_root() rejects an AQUILA_MEDIA_ROOT override missing phase1/phase2",
    )
except AquilaEnvironmentError:
    check(
        True,
        "detect_media_root() rejects an AQUILA_MEDIA_ROOT override missing phase1/phase2",
    )
finally:
    os.environ.pop(media.MEDIA_ROOT_ENV_VAR, None)

from common.constants.deployment import (  # noqa: E402
    USB_PHASE_ONE_DIRECTORY,
    USB_PHASE_TWO_DIRECTORY,
    USB_REPORT_DIRECTORY,
)

check(
    media.phase_two_directory(_media_root) == _media_root / USB_PHASE_TWO_DIRECTORY,
    "phase_two_directory() resolves <media_root>/<USB_PHASE_TWO_DIRECTORY>",
)
check(
    media.report_directory(_media_root)
    == _media_root / USB_PHASE_ONE_DIRECTORY / USB_REPORT_DIRECTORY,
    "report_directory() resolves <media_root>/<phase1>/<USB_REPORT_DIRECTORY>",
)


# ---------------------------------------------------------------------------
# technician_console.progress.format_bytes -- no Tk root needed
# ---------------------------------------------------------------------------

check(format_bytes(0) == "0.0 B", "format_bytes(0) renders '0.0 B'")
check(format_bytes(512) == "512.0 B", "format_bytes(512) stays in bytes")
check(format_bytes(1024) == "1.0 KiB", "format_bytes(1024) rolls over to KiB")
check(format_bytes(1536) == "1.5 KiB", "format_bytes(1536) renders 1.5 KiB")
check(format_bytes(1024 ** 3) == "1.0 GiB", "format_bytes(1 GiB) renders '1.0 GiB'")
check(format_bytes(1024 ** 4) == "1.0 TiB", "format_bytes(1 TiB) renders '1.0 TiB'")


# ===========================================================================
# Everything below needs a real (if headless) Tk display.
# ===========================================================================

_root = tk.Tk()
_root.withdraw()


# ---------------------------------------------------------------------------
# ProgressPanel
# ---------------------------------------------------------------------------

_progress_bridge = MainThreadBridge()
_progress_panel = ProgressPanel(_root, _progress_bridge)

check(
    str(_progress_panel._progress_bar["mode"]) == "indeterminate",
    "ProgressPanel's progress bar is indeterminate (honesty-over-fabrication: no invented percentage)",
)
check(_progress_panel._status_var.get() == "Idle.", "ProgressPanel starts Idle")

_progress_panel.begin_operation("Working...")
check(_progress_panel._active_operations == 1, "ProgressPanel.begin_operation() increments the operation count")
check(
    # NFR-USE-002: this is the progress indicator ("indeterminate" bar
    # plus status line) that begin_operation()/end_operation() bracket
    # around every operation the Technician Console runs.
    _progress_panel._status_var.get() == "Working...",
    "ProgressPanel.begin_operation() sets the status line",
)

_progress_panel.begin_operation("Still working...")
check(_progress_panel._active_operations == 2, "ProgressPanel tracks concurrently-bracketed operations")
_progress_panel.end_operation()
check(_progress_panel._active_operations == 1, "ProgressPanel.end_operation() decrements the operation count")
_progress_panel.end_operation()
check(_progress_panel._active_operations == 0, "ProgressPanel.end_operation() reaches zero")
check(_progress_panel._status_var.get() == "Idle.", "ProgressPanel returns to Idle once every operation has ended")

_progress_panel.on_stage_event(WorkflowStageEvent(stage="inspection", message="Scanning hardware", severity="info"))
_progress_bridge.pump()
check(
    # REQ-TC-009: this is the live "what's happening right now" display
    # a long-running deployment operation updates as it progresses.
    "[inspection] Scanning hardware" in _progress_panel._status_var.get(),
    "ProgressPanel.on_stage_event() (posted via the bridge) updates the live status line",
)

_progress_panel.reset()
check(_progress_panel._active_operations == 0, "ProgressPanel.reset() clears the operation count")
check(_progress_panel._status_var.get() == "Idle.", "ProgressPanel.reset() returns to Idle")


# ---------------------------------------------------------------------------
# StatusPanel
# ---------------------------------------------------------------------------

_status_bridge = MainThreadBridge()
_log_viewer_opened: list[bool] = []
_status_panel = StatusPanel(_root, _status_bridge, on_view_logs=lambda: _log_viewer_opened.append(True))

for _severity in ("info", "warning", "error"):
    _status_panel.on_stage_event(
        WorkflowStageEvent(stage="test", message=f"a {_severity} message", severity=_severity)
    )
_status_bridge.pump()

for _severity in ("info", "warning", "error"):
    _listbox = _status_panel._listboxes[_severity]
    check(
        _listbox.size() == 1 and f"a {_severity} message" in _listbox.get(0),
        f"StatusPanel routes a {_severity!r} WorkflowStageEvent to its own separate section (REQ-TC-010, REQ-TC-011)",
    )
    check(
        _status_panel._counts[_severity] == 1,
        f"StatusPanel's {_severity!r} count updates independently of the other sections",
    )

_status_panel.reset()
check(
    all(_status_panel._listboxes[s].size() == 0 for s in ("info", "warning", "error")),
    "StatusPanel.reset() clears every section",
)


# ---------------------------------------------------------------------------
# WorkflowSelectorPanel
# ---------------------------------------------------------------------------

_selector_calls: dict[str, list[str]] = {"retirement": [], "provisioning": []}
_selector = WorkflowSelectorPanel(
    _root,
    on_start_retirement=lambda name: _selector_calls["retirement"].append(name),
    on_start_provisioning=lambda name: _selector_calls["provisioning"].append(name),
)

_selector._node_name_var.set("")
_selector._start_retirement()
check(
    _selector_calls["retirement"] == [],
    "WorkflowSelectorPanel refuses to start a workflow with a blank session label",
)
check(
    _selector._hint_var.get() != "",
    "WorkflowSelectorPanel shows a hint when the session label is blank",
)

_selector._node_name_var.set("  aquila-node-01  ")
_selector._start_retirement()
check(
    _selector_calls["retirement"] == ["aquila-node-01"],
    "WorkflowSelectorPanel.on_start_retirement fires with the trimmed session label (REQ-TC-006)",
)

_selector._node_name_var.set("aquila-node-02")
_selector._start_provisioning()
check(
    _selector_calls["provisioning"] == ["aquila-node-02"],
    "WorkflowSelectorPanel.on_start_provisioning fires with the session label (REQ-TC-007)",
)

_selector.set_enabled(False)
check(
    str(_selector._retirement_button["state"]) == "disabled"
    and str(_selector._provisioning_button["state"]) == "disabled"
    and str(_selector._node_name_entry["state"]) == "disabled",
    "WorkflowSelectorPanel.set_enabled(False) disables both buttons and the label entry (REQ-TC-012)",
)
_selector.set_enabled(True)
check(
    str(_selector._retirement_button["state"]) == "normal",
    "WorkflowSelectorPanel.set_enabled(True) re-enables the buttons",
)


# ---------------------------------------------------------------------------
# dialogs.TargetDeviceDialog
# ---------------------------------------------------------------------------

_devices = [
    _device("\\\\.\\PhysicalDrive0", model="Disk One", serial_number="SN-0"),
    _device("\\\\.\\PhysicalDrive1", model="Disk Two", serial_number="SN-1"),
]

_retirement_dialog = dialogs.TargetDeviceDialog(_root, _devices, require_provisioning_target=False)
_retirement_dialog._tree.selection_set("0", "1")
_retirement_dialog._on_selection_changed()
check(
    str(_retirement_dialog._ok_button["state"]) == "normal",
    "TargetDeviceDialog enables Continue once at least one device is selected",
)
_root.after(20, _retirement_dialog._on_continue)
_retirement_result = _retirement_dialog.run()
check(
    {d.device_path for d in _retirement_result.devices} == {d.device_path for d in _devices},
    "TargetDeviceDialog.run() returns every selected device (REQ-PREP-005)",
)
check(
    _retirement_result.provisioning_device is None,
    "TargetDeviceDialog in retirement mode never sets a provisioning target",
)

_provisioning_dialog = dialogs.TargetDeviceDialog(_root, _devices, require_provisioning_target=True)
_provisioning_dialog._tree.selection_set("0", "1")
_provisioning_dialog._on_selection_changed()

def _complete_provisioning_selection() -> None:
    _provisioning_dialog._provisioning_var.set(_provisioning_dialog._provisioning_combo["values"][0])
    _provisioning_dialog._on_continue()


_root.after(20, _complete_provisioning_selection)
_provisioning_result = _provisioning_dialog.run()
check(
    _provisioning_result.provisioning_device is not None
    and _provisioning_result.provisioning_device.device_path in {d.device_path for d in _devices},
    "TargetDeviceDialog in provisioning mode returns exactly one provisioning_device drawn from the selection",
)

_cancel_dialog = dialogs.TargetDeviceDialog(_root, _devices, require_provisioning_target=False)
_root.after(20, _cancel_dialog._on_cancel)
try:
    _cancel_dialog.run()
    check(False, "TargetDeviceDialog.run() raises AquilaCancelledError when the technician cancels")
except AquilaCancelledError:
    check(True, "TargetDeviceDialog.run() raises AquilaCancelledError when the technician cancels")


# ---------------------------------------------------------------------------
# dialogs.PreparationConfirmationDialog
# ---------------------------------------------------------------------------

_confirmation_request = PreparationConfirmationRequest(
    system_manufacturer="Acme",
    system_model="X1",
    system_serial_number="SYS-1",
    target_devices=(_devices[0],),
    recovery_status="Recovery skipped by technician.",
    deployment_workflow="retirement",
    required_confirmation_count=3,
    force_confirmation_phrase=FORCE_CONFIRMATION_PHRASE,
)

_confirmation_dialog = dialogs.PreparationConfirmationDialog(_root, _confirmation_request)
check(
    # NFR-USE-001: this dialog is the Console's distinct visual
    # register for a destructive operation, separate from an ordinary
    # info/warning message -- it starts blocked rather than merely
    # warned.
    str(_confirmation_dialog._ok_button["state"]) == "disabled",
    "PreparationConfirmationDialog starts with Continue disabled (REQ-TC-012)",
)


def _fill_confirmation_dialog_correctly() -> None:
    _confirmation_dialog._target_device_var.set(True)
    _confirmation_dialog._final_approval_var.set(True)
    _confirmation_dialog._phrase_var.set(FORCE_CONFIRMATION_PHRASE)
    for var in _confirmation_dialog._additional_vars:
        var.set(True)
    _confirmation_dialog._refresh_ok_state()


_fill_confirmation_dialog_correctly()
check(
    # NFR-USE-003: Continue only ever becomes available once every
    # explicit confirmation (each checkbox, plus the exact typed
    # erasure phrase) has actually been given -- this irreversible
    # action cannot proceed on an implicit or default confirmation.
    str(_confirmation_dialog._ok_button["state"]) == "normal",
    "PreparationConfirmationDialog enables Continue once every REQ-PREP-004/005/006/007 confirmation is satisfied",
)

_confirmation_dialog._phrase_var.set("not the phrase")
_confirmation_dialog._refresh_ok_state()
check(
    str(_confirmation_dialog._ok_button["state"]) == "disabled",
    "PreparationConfirmationDialog disables Continue when the erasure phrase doesn't match exactly (REQ-PREP-006)",
)

_fill_confirmation_dialog_correctly()
_root.after(20, _confirmation_dialog._on_continue)
_confirmations = _confirmation_dialog.run()
check(
    isinstance(_confirmations, PreparationConfirmations)
    and _confirmations.target_device_confirmed
    and _confirmations.final_approval
    and _confirmations.erasure_acknowledgement_phrase == FORCE_CONFIRMATION_PHRASE,
    "PreparationConfirmationDialog.run() returns confirmations matching validate_confirmations()'s exact requirements",
)


# ---------------------------------------------------------------------------
# dialogs.RecoveryDialog -- zero-volumes regression test
# ---------------------------------------------------------------------------

from recovery.browser import VolumeBrowser  # noqa: E402


class _EmptyVolumeBrowser(VolumeBrowser):
    def browse(self, volume: RecoveryVolume, relative_path: str = "") -> list[RecoveryEntry]:  # type: ignore[override]
        return []


_empty_recovery_dialog = dialogs.RecoveryDialog(_root, [], _EmptyVolumeBrowser())
check(
    _empty_recovery_dialog._current_entries == {},
    "RecoveryDialog._current_entries is initialized even with zero discovered volumes "
    "(regression test for the AttributeError this session fixed)",
)

_empty_recovery_dialog._skip_ack_var.set("I understand")


def _finish_skip() -> None:
    _empty_recovery_dialog._notebook.select(1)
    _empty_recovery_dialog._on_continue()


_root.after(20, _finish_skip)
_skip_decision = _empty_recovery_dialog.run()
check(
    _skip_decision.skip and _skip_decision.technician_acknowledgement == "I understand",
    "RecoveryDialog's Skip tab returns RecoveryDecision.skip_with_acknowledgement() (REQ-REC-016)",
)


# ---------------------------------------------------------------------------
# dialogs.LogViewerDialog / SummaryDialog -- construction smoke tests
# ---------------------------------------------------------------------------


class _FakeLoggingService:
    def list_log_files(self) -> list[LogFileInfo]:
        return []

    def read_log(self, name: str, *, tail_lines: Optional[int] = None) -> str:
        return ""

    def export(self, destination: Path) -> Any:
        raise AssertionError("not exercised in this smoke test")


_log_dialog = dialogs.LogViewerDialog(_root, _FakeLoggingService())  # type: ignore[arg-type]
check(isinstance(_log_dialog, tk.Toplevel), "LogViewerDialog constructs without error (REQ-TC-008)")
_log_dialog.destroy()

_summary = WorkflowSummary(
    workflow_type=WorkflowType.RETIREMENT,
    node_name="aquila-node-03",
    started_at=datetime.now(UTC),
    completed_at=datetime.now(UTC),
    inspection_report=None,
    recovery_summary=None,
    preparation_summary=None,
    aborted=True,
    abort_reason="technician cancelled",
)
_summary_dialog = dialogs.SummaryDialog(_root, _summary)
check(
    # NFR-REL-004: every stage field on ``_summary`` above is ``None``
    # -- an aborted run where nothing completed -- yet
    # SummaryDialog/_render_summary() still renders cleanly with only
    # the explicit ``abort_reason``, never crashing on or fabricating
    # a "last completed stage" that never happened.
    isinstance(_summary_dialog, tk.Toplevel),
    "SummaryDialog constructs without error (REQ-TC-013)",
)
_summary_dialog.destroy()


# ---------------------------------------------------------------------------
# technician_console.main_window.MainWindow
#
# MainWindow subclasses tk.Tk itself, so constructing one creates its
# own, separate Tcl interpreter -- it must not coexist with the plain
# `_root = tk.Tk()` every test above this point was parented to
# (running two live Tk() interpreters in one process is unsupported
# territory: cross-interpreter widget/variable references can hang or
# misbehave in ways that have nothing to do with technician_console's
# own logic). `_root` is destroyed first so exactly one Tk interpreter
# is ever alive at a time; MainWindow's own bridge is pumped directly
# (`_window._bridge.pump()`) rather than through a nested mainloop,
# since every write this suite cares about is already synchronously
# queued by the time each check below runs.
# ---------------------------------------------------------------------------

_root.destroy()

_configs_dir = _TEMP_ROOT / "configs"
_configs_dir.mkdir(parents=True, exist_ok=True)
for _filename in (
    "deployment.yaml", "network.yaml", "cluster.yaml",
    "logging.yaml", "benchmark.yaml", "controller.yaml",
):
    (_configs_dir / _filename).write_text("{}\n", encoding="utf-8")

_window: Optional[MainWindow] = MainWindow(configs_dir=_configs_dir)
check(
    # NFR-PERF-001: this constructs the real MainWindow.__init__ --
    # widget construction plus core service bring-up -- end to end;
    # it completes immediately in this test environment because, per
    # that method's own docstring, nothing in it does hardware
    # inspection or network I/O.
    _window.fatal_error is None,
    "MainWindow initializes successfully against a valid (if empty-default) configuration set",
)

if _window.fatal_error is not None:
    # Defensive only -- the stub configuration set above is expected to
    # initialize successfully every time. Still destroy the (partially
    # built) Tk root before the fatal-error-path construction below
    # creates a second one, keeping exactly one Tk interpreter alive
    # at a time (see the section note above).
    _window.destroy()

if _window.fatal_error is None:
    check(
        _window._version_var.get().startswith("Aquila v"),
        "MainWindow's status bar shows the Aquila version (REQ-TC-002)",
    )
    check(
        "unversioned" in _window._media_version_var.get(),
        "MainWindow honestly reports 'unversioned' media rather than fabricating REQ-TC-003 media version data",
    )

    _stage_event = WorkflowStageEvent(stage="inspection", message="Detecting storage", severity="warning")
    _window._on_stage_event(_stage_event)
    _window._bridge.pump()
    check(
        "Detecting storage" in _window._progress_panel._status_var.get(),
        "MainWindow._on_stage_event() forwards to ProgressPanel",
    )
    check(
        _window._status_panel._listboxes["warning"].size() == 1,
        "MainWindow._on_stage_event() forwards to StatusPanel",
    )

    # dialogs.show_error is monkeypatched for the rest of this
    # MainWindow's lifetime: several of the methods exercised below
    # (_finish_session_error(), and every REQ-TC-007 pre-flight
    # refusal) call it to report a real technician-facing error, which
    # would otherwise pop a real, blocking modal messagebox with
    # nothing in this headless test able to click it away.
    _show_error_calls: list[tuple[str, str]] = []
    _original_show_error = dialogs.show_error
    dialogs.show_error = lambda parent, title, message: _show_error_calls.append((title, message))  # type: ignore[assignment]

    try:
        check(_window._workflow_active is False, "MainWindow starts with no workflow active")
        _window._begin_session()
        check(_window._workflow_active is True, "MainWindow._begin_session() marks a workflow active (REQ-TC-012)")
        check(
            str(_window._selector._retirement_button["state"]) == "disabled",
            "MainWindow._begin_session() disables the workflow selector while a session runs",
        )
        _window._finish_session_error("synthetic failure for testing")
        check(_window._workflow_active is False, "MainWindow._finish_session_error() clears the active-workflow flag")
        check(
            str(_window._selector._retirement_button["state"]) == "normal",
            "MainWindow._finish_session_error() re-enables the workflow selector",
        )
        check(
            len(_show_error_calls) == 1 and "Deployment Error" in _show_error_calls[-1][0],
            "MainWindow._finish_session_error() reports the failure via dialogs.show_error",
        )
        _show_error_calls.clear()

        # REQ-TC-007's pre-flight gates: media root, boot_entry_id,
        # provisioning domain/mailto, and root password must each
        # independently block starting Provisioning with a clear
        # error rather than guessing a value.
        _window._media_root = None
        _window._start_provisioning_workflow("preflight-node")
        check(
            len(_show_error_calls) == 1 and "Media" in _show_error_calls[-1][0],
            "MainWindow refuses to start Provisioning without a detected media root",
        )

        _window._media_root = _media_root
        _show_error_calls.clear()
        _window._config_bundle.deployment.boot_entry_id = ""
        _window._start_provisioning_workflow("preflight-node")
        check(
            # NFR-MAIN-005: refusing to guess this value is the
            # Technician Console's half of the safety boundary
            # ADR-0003-Two-Phase-Deployment.md documents -- the BCD
            # boot entry must come from the Build System at USB-build
            # time, never fabricated here at deployment time.
            len(_show_error_calls) == 1 and "Boot Entry" in _show_error_calls[-1][0],
            "MainWindow refuses to start Provisioning without a configured boot_entry_id",
        )

        _window._config_bundle.deployment.boot_entry_id = "{GUID}"
        _show_error_calls.clear()
        _window._profile_template = ProvisioningProfileTemplate(domain="", mailto="")
        _window._start_provisioning_workflow("preflight-node")
        check(
            len(_show_error_calls) == 1 and "Notification" in _show_error_calls[-1][0],
            "MainWindow refuses to start Provisioning without a configured provisioning domain/mailto",
        )

        _window._profile_template = ProvisioningProfileTemplate(
            domain="lab.local", mailto="ops@lab.local"
        )
        _show_error_calls.clear()
        os.environ.pop(_window._profile_template.root_password_env_var, None)
        _window._start_provisioning_workflow("preflight-node")
        check(
            len(_show_error_calls) == 1 and "Password" in _show_error_calls[-1][0],
            "MainWindow refuses to start Provisioning without a resolvable root password (REQ-SEC-008, REQ-SEC-009, REQ-SEC-010)",
        )
        check(
            _window._workflow_active is False,
            "None of the four Provisioning pre-flight refusals leave a workflow marked active",
        )
    finally:
        dialogs.show_error = _original_show_error  # type: ignore[assignment]

    _window._on_close()
    check(True, "MainWindow._on_close() tears down every owned service without raising")


# Fatal-error path: an invalid configs_dir must set fatal_error and
# report it via dialogs.show_error, WITHOUT ever blocking this test on
# a real modal messagebox -- dialogs.show_error is monkeypatched for
# the duration of this one construction.
_fatal_error_calls: list[tuple[str, str]] = []
_original_show_error_2 = dialogs.show_error
dialogs.show_error = lambda parent, title, message: _fatal_error_calls.append((title, message))  # type: ignore[assignment]
try:
    _bad_configs_dir = _TEMP_ROOT / "does-not-exist"
    _fatal_window = MainWindow(configs_dir=_bad_configs_dir)
    check(
        _fatal_window.fatal_error is not None,
        "MainWindow.fatal_error is set when core service startup fails",
    )
    check(
        len(_fatal_error_calls) == 1,
        "MainWindow reports a fatal startup error via dialogs.show_error exactly once",
    )
finally:
    dialogs.show_error = _original_show_error_2  # type: ignore[assignment]
    _fatal_window.destroy()


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

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
print("All technician_console/ functional checks passed.")
