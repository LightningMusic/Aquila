"""
Project Aquila
=============

Technician Console: Progress Panel

REQ-TC-009 ("display deployment progress during long-running
operations") and NFR-USE-002 ("progress indicators shall be displayed
during all operations expected to exceed five seconds"). Renders two
distinct signals a running workflow produces (see
``workflows.progress``'s own module docstring for why they're kept
separate rather than unified):

* Stage-level ``WorkflowStageEvent``s (REQ-TC-009) -- the live "what's
  happening right now" status line.
* Fine-grained, within-operation progress -- ``recovery.copier
  .CopyProgress`` (REQ-REC-011) and ``preparation.sanitizer
  .SanitizationProgress`` (REQ-PREP-015) -- an indeterminate progress
  bar plus a live status line.

Neither ``CopyProgress`` nor ``SanitizationProgress`` carries a total
against which to compute a real percentage (``SanitizationProgress``'s
own docstring is explicit: ``MSFT_Disk.Clear()`` has no native
progress-percentage channel, and fabricating one "would violate this
project's honesty-over-fabrication convention just as surely as
reporting a fabricated success"). This panel therefore uses Tk's
*indeterminate* ``ttk.Progressbar`` mode (an animated, bouncing bar
with no implied percentage) rather than inventing a completion
fraction -- the same honesty discipline extended into the UI layer.

This panel deliberately renders only the *current* status line, not a
scrolling history -- REQ-TC-010/011's "warnings displayed separately
from informational messages" / "errors displayed separately from
warnings" is a distinct requirement calling for genuinely separate
display regions, not merely color-differentiated lines in one shared
feed, so that accumulating history lives in
:class:`technician_console.status_panel.StatusPanel` instead.
``technician_console.main_window`` registers one combined stage-event
handler that forwards each ``WorkflowStageEvent`` to both this panel
(for the live "what's happening right now" line) and to ``StatusPanel``
(for the accumulating, severity-separated record).

Every public ``on_*`` method here is a callback meant to be handed
directly to a ``workflows``/engine-manager call as its
``workflow_progress_callback``/``progress_callback`` argument, which
means it is invoked from the background workflow thread (see
``technician_console.thread_bridge``'s module docstring) -- each one
does no more than marshal its argument onto the main thread via
``MainThreadBridge.post()`` before touching any widget.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from common.utils.formatting import format_bytes
from preparation.sanitizer import SanitizationProgress
from recovery.copier import CopyProgress
from workflows.progress import WorkflowStageEvent

from .thread_bridge import MainThreadBridge

#: Status-line foreground color per ``workflows.progress.SEVERITIES``
#: value. Chosen for contrast against ``ttk``'s default light window
#: background.
_SEVERITY_COLOR: dict[str, str] = {
    "info": "#1a1a1a",
    "warning": "#8a5a00",
    "error": "#a4262c",
}


class ProgressPanel(ttk.Frame):
    """
    REQ-TC-009's progress display: an indeterminate progress bar with
    a live "what's happening right now" status line.
    """

    def __init__(self, parent: tk.Misc, bridge: MainThreadBridge) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._active_operations = 0

        self._status_var = tk.StringVar(value="Idle.")
        self._status_label = ttk.Label(
            self, textvariable=self._status_var, anchor="w"
        )
        self._status_label.pack(fill="x", padx=4, pady=(4, 0))

        self._progress_bar = ttk.Progressbar(self, mode="indeterminate")
        self._progress_bar.pack(fill="x", padx=4, pady=(2, 4))

    # ------------------------------------------------------------------
    # Callbacks -- invoked from the background workflow thread
    # ------------------------------------------------------------------

    def on_stage_event(self, event: WorkflowStageEvent) -> None:
        """A ``workflows.progress.WorkflowProgressCallback``."""

        self._bridge.post(lambda: self._render_stage_event(event))

    def on_recovery_progress(self, progress: CopyProgress) -> None:
        """A ``recovery.copier.ProgressCallback``."""

        message = (
            f"Copying: {progress.current_path.name} "
            f"({progress.files_copied_so_far} file(s), "
            f"{format_bytes(progress.bytes_copied_so_far)} so far)"
        )
        self._bridge.post(lambda: self._set_status(message))

    def on_sanitization_progress(self, progress: SanitizationProgress) -> None:
        """A ``preparation.sanitizer.ProgressCallback``."""

        message = f"{progress.device_path}: {progress.stage} -- {progress.message}"
        self._bridge.post(lambda: self._set_status(message))

    # ------------------------------------------------------------------
    # Operation bracketing -- called from the main thread by
    # technician_console.main_window around each blocking workflow call
    # ------------------------------------------------------------------

    def begin_operation(self, label: str) -> None:
        """Start the indeterminate progress bar. Main-thread only."""

        self._active_operations += 1
        self._set_status(label)
        self._progress_bar.start(interval=80)

    def end_operation(self) -> None:
        """
        Stop the indeterminate progress bar once every concurrently
        tracked operation has ended. Main-thread only.
        """

        self._active_operations = max(0, self._active_operations - 1)
        if self._active_operations == 0:
            self._progress_bar.stop()
            self._set_status("Idle.")

    def reset(self) -> None:
        """Return to the idle state for a fresh workflow session. Main-thread only."""

        self._active_operations = 0
        self._progress_bar.stop()
        self._set_status("Idle.", severity="info")

    # ------------------------------------------------------------------
    # Main-thread rendering
    # ------------------------------------------------------------------

    def _set_status(self, message: str, *, severity: str = "info") -> None:
        self._status_var.set(message)
        self._status_label.configure(
            foreground=_SEVERITY_COLOR.get(severity, _SEVERITY_COLOR["info"])
        )

    def _render_stage_event(self, event: WorkflowStageEvent) -> None:
        self._set_status(f"[{event.stage}] {event.message}", severity=event.severity)


__all__ = ["ProgressPanel", "format_bytes"]
