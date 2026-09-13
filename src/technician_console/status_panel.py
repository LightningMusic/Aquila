"""
Project Aquila
=============

Technician Console: Status Panel

REQ-TC-010 ("display warnings separately from informational messages")
and REQ-TC-011 ("display errors separately from warnings") -- three
genuinely separate, accumulating display regions fed by the same
``WorkflowStageEvent`` stream every stage adapter in ``workflows/``
already emits (``workflows.progress.SEVERITIES``: ``"info"``,
``"warning"``, ``"error"`` map one-to-one onto the three sections
here). See ``technician_console.progress``'s module docstring for why
that panel renders only the live "current status" line while this one
owns the accumulating record.

Also hosts REQ-TC-008 ("the Technician Console shall provide access to
deployment logs"): a button opening
``technician_console.dialogs.LogViewerDialog``, backed by
``services.logging_service.LoggingService``.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import tkinter as tk
from datetime import UTC, datetime
from tkinter import ttk
from typing import Callable, Optional

from workflows.progress import WorkflowStageEvent

from .thread_bridge import MainThreadBridge

#: One (label, listbox background tint) pair per
#: ``workflows.progress.SEVERITIES`` value, in display order.
_SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("info", "Information", "#ffffff"),
    ("warning", "Warnings", "#fff8e6"),
    ("error", "Errors", "#fdecea"),
)


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%H:%M:%S")


class StatusPanel(ttk.Frame):
    """
    REQ-TC-010/011's three-way separated message display, plus
    REQ-TC-008's log-access entry point.
    """

    def __init__(
        self,
        parent: tk.Misc,
        bridge: MainThreadBridge,
        *,
        on_view_logs: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._listboxes: dict[str, tk.Listbox] = {}
        self._count_vars: dict[str, tk.StringVar] = {}
        self._counts: dict[str, int] = {severity: 0 for severity, _, _ in _SECTIONS}

        columns = ttk.Frame(self)
        columns.pack(fill="both", expand=True, padx=4, pady=4)

        for index, (severity, title, background) in enumerate(_SECTIONS):
            column = ttk.Frame(columns)
            column.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 4, 0))
            columns.columnconfigure(index, weight=1)
            columns.rowconfigure(0, weight=1)

            count_var = tk.StringVar(value=f"{title} (0)")
            self._count_vars[severity] = count_var
            ttk.Label(column, textvariable=count_var, anchor="w").pack(fill="x")

            list_frame = ttk.Frame(column)
            list_frame.pack(fill="both", expand=True)

            listbox = tk.Listbox(
                list_frame,
                height=8,
                background=background,
                activestyle="none",
                exportselection=False,
            )
            scrollbar = ttk.Scrollbar(
                list_frame, orient="vertical", command=listbox.yview
            )
            listbox.configure(yscrollcommand=scrollbar.set)
            listbox.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")

            self._listboxes[severity] = listbox

        button_row = ttk.Frame(self)
        button_row.pack(fill="x", padx=4, pady=(0, 4))
        ttk.Button(
            button_row,
            text="View Deployment Logs (REQ-TC-008)",
            command=(on_view_logs or (lambda: None)),
        ).pack(side="right")

    # ------------------------------------------------------------------
    # Callback -- invoked from the background workflow thread
    # ------------------------------------------------------------------

    def on_stage_event(self, event: WorkflowStageEvent) -> None:
        """A ``workflows.progress.WorkflowProgressCallback``."""

        self._bridge.post(lambda: self._append(event))

    # ------------------------------------------------------------------
    # Main-thread rendering
    # ------------------------------------------------------------------

    def _append(self, event: WorkflowStageEvent) -> None:
        listbox = self._listboxes[event.severity]
        listbox.insert("end", f"[{_timestamp()}] [{event.stage}] {event.message}")
        listbox.see("end")

        self._counts[event.severity] += 1
        title = dict((s, t) for s, t, _ in _SECTIONS)[event.severity]
        self._count_vars[event.severity].set(
            f"{title} ({self._counts[event.severity]})"
        )

    def reset(self) -> None:
        """Clear every section for a fresh workflow session. Main-thread only."""

        for severity, title, _ in _SECTIONS:
            self._listboxes[severity].delete(0, "end")
            self._counts[severity] = 0
            self._count_vars[severity].set(f"{title} (0)")


__all__ = ["StatusPanel"]
