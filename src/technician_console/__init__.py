"""
Project Aquila
=============

Technician Console

The primary operator interface (SRS Section 9.6/10.2, REQ-TC-001
through REQ-TC-013): a single Tkinter application window that
launches automatically once the Aquila deployment environment has
finished booting, and serves as the technician's only entry point
into both deployment workflows (SRS Section 9.6: "Subsystems shall
not present independent interfaces to the operator").

Package layout
----------------
* :mod:`technician_console.main_window` -- the top-level window
  (``MainWindow``), composing every panel below around
  ``workflows.workflow_manager.WorkflowManager``.
* :mod:`technician_console.workflow_selector` -- REQ-TC-006/007's
  workflow launch panel.
* :mod:`technician_console.progress` -- REQ-TC-009/NFR-USE-002's live
  status line and indeterminate progress bar.
* :mod:`technician_console.status_panel` -- REQ-TC-008/010/011's
  accumulating, severity-separated message record and log-viewer
  entry point.
* :mod:`technician_console.dialogs` -- every modal dialog the
  Console's callbacks open (target-device selection, recovery
  browsing, preparation confirmations, the log viewer, and the final
  REQ-TC-013 deployment summary).
* :mod:`technician_console.thread_bridge` -- the worker-thread/main-
  thread marshaling mechanism every workflow callback crosses through.
* :mod:`technician_console.media` -- deployment-media root detection,
  needed by Provisioning to locate the real ``phase2`` directory and
  Phase One report directory on the running system.

Tkinter, and why this environment can run it
-----------------------------------------------
The Technician Console uses Tkinter (Python's standard-library GUI
toolkit) rather than a third-party GUI framework, keeping this
subsystem free of any new runtime dependency. Two facts, both
confirmed by research rather than assumed, make this workable within
Aquila's WinPE-based deployment environment:

1. WinPE officially supports running Win32 GUI applications --
   Microsoft's own WinPE documentation lists running "Applications,
   including Win32 application programming interfaces (APIs)" and
   adding "your own custom shell or GUI" among WinPE's supported
   capabilities.
2. Python's embeddable distribution for Windows does not bundle a
   working Tcl/Tk runtime -- confirmed against an upstream CPython
   issue in which accidental inclusion of the Tcl/Tk DLLs in a 3.13
   embeddable build was reverted as unintentional; the ``_tkinter``
   extension module itself has never been part of that distribution.

Point 2 means the deployment media's Python runtime must have the
Tcl/Tk runtime bundled alongside it explicitly (rather than relying on
the embeddable distribution to provide it). This is scoped, tracked
future work for the not-yet-built Build System (SRS Section
9.15/10.14), which is responsible for assembling everything under
``phase1`` -- consistent with this project's "record the limitation,
don't fabricate a fix for a subsystem that doesn't exist yet"
convention. It does not block developing or testing this package on
any ordinary desktop Python installation, which already includes a
working Tcl/Tk runtime.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .dialogs import (
    LogViewerDialog,
    PreparationConfirmationDialog,
    RecoveryDialog,
    SummaryDialog,
    TargetDeviceDialog,
    TargetDeviceSelection,
)
from .main_window import MainWindow
from .media import MEDIA_ROOT_ENV_VAR, detect_media_root, phase_two_directory, report_directory
from .progress import ProgressPanel, format_bytes
from .status_panel import StatusPanel
from .thread_bridge import MainThreadBridge
from .workflow_selector import WorkflowSelectorPanel


def run_console(*, configs_dir: Optional[Path] = None) -> int:
    """
    REQ-TC-001's entry point: construct :class:`MainWindow` and run
    it until the technician closes it or a fatal startup error is
    reported.

    ``MainWindow.__init__`` handles every fatal startup condition
    (service bring-up failure, configuration load failure) itself --
    showing the technician an error dialog and returning without
    completing layout construction, rather than raising -- so this
    function's only job is to notice that ``fatal_error`` was set and
    skip ``mainloop()`` in that case, rather than running an
    incompletely built window.

    Args:
        configs_dir: Optional override for the configuration
            directory, forwarded to
            ``workflows.application_manager.ApplicationManager``.
            Exposed for tests; production callers should omit it and
            rely on the default resolution
            ``ApplicationManager``/``config.manager.ConfigurationManager``
            already implement.

    Returns:
        A process exit code: ``0`` on an ordinary technician-initiated
        close, ``1`` if startup failed before the window could be
        shown.
    """

    window = MainWindow(configs_dir=configs_dir)
    if window.fatal_error is not None:
        return 1

    window.mainloop()
    return 0


__all__ = [
    "LogViewerDialog",
    "MEDIA_ROOT_ENV_VAR",
    "MainThreadBridge",
    "MainWindow",
    "PreparationConfirmationDialog",
    "ProgressPanel",
    "RecoveryDialog",
    "StatusPanel",
    "SummaryDialog",
    "TargetDeviceDialog",
    "TargetDeviceSelection",
    "WorkflowSelectorPanel",
    "detect_media_root",
    "format_bytes",
    "phase_two_directory",
    "report_directory",
    "run_console",
]
