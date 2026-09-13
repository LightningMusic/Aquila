"""
Project Aquila
=============

Technician Console: Workflow Selector

REQ-TC-006 ("provide access to the Device Retirement workflow") and
REQ-TC-007 ("provide access to the Aquila Node Provisioning
workflow") -- the two entry points into
``workflows.workflow_manager.WorkflowManager``.

Both workflows need a technician-supplied session label
(``node_name``, forwarded to every stage adapter for its own event/log
identity -- see ``workflows.deployment_manager``'s own docstring) before
either can start, so this panel collects it once rather than in two
separate places.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable


class WorkflowSelectorPanel(ttk.Frame):
    """REQ-TC-006/007's workflow launch panel."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        on_start_retirement: Callable[[str], None],
        on_start_provisioning: Callable[[str], None],
    ) -> None:
        super().__init__(parent)
        self._on_start_retirement = on_start_retirement
        self._on_start_provisioning = on_start_provisioning

        name_row = ttk.Frame(self)
        name_row.pack(fill="x", padx=4, pady=(4, 8))
        ttk.Label(name_row, text="Session label:").pack(side="left")
        self._node_name_var = tk.StringVar(value="")
        self._node_name_entry = ttk.Entry(
            name_row, textvariable=self._node_name_var, width=32
        )
        self._node_name_entry.pack(side="left", padx=(6, 0))

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=4, pady=(0, 4))

        self._retirement_button = ttk.Button(
            buttons,
            text="Device Retirement (REQ-TC-006)",
            command=self._start_retirement,
        )
        self._retirement_button.pack(side="left", fill="x", expand=True)

        self._provisioning_button = ttk.Button(
            buttons,
            text="Aquila Node Provisioning (REQ-TC-007)",
            command=self._start_provisioning,
        )
        self._provisioning_button.pack(
            side="left", fill="x", expand=True, padx=(6, 0)
        )

        self._hint_var = tk.StringVar(value="")
        ttk.Label(
            self, textvariable=self._hint_var, foreground="#a4262c"
        ).pack(fill="x", padx=4)

    def _node_name(self) -> str:
        return self._node_name_var.get().strip()

    def _start_retirement(self) -> None:
        node_name = self._node_name()
        if not node_name:
            self._hint_var.set("Enter a session label before starting a workflow.")
            self._node_name_entry.focus_set()
            return
        self._hint_var.set("")
        self._on_start_retirement(node_name)

    def _start_provisioning(self) -> None:
        node_name = self._node_name()
        if not node_name:
            self._hint_var.set("Enter a session label before starting a workflow.")
            self._node_name_entry.focus_set()
            return
        self._hint_var.set("")
        self._on_start_provisioning(node_name)

    def set_enabled(self, enabled: bool) -> None:
        """
        REQ-TC-012's session-level half of the confirmation gate: while
        a workflow is running, neither button (nor the label field) can
        start a second one -- ``workflows.workflow_manager
        .WorkflowManager`` also refuses this at the model layer
        (``WorkflowAlreadyRunningError``), so this is a defense-in-depth
        UI affordance, not the only thing preventing it.
        """

        state = "normal" if enabled else "disabled"
        self._retirement_button.configure(state=state)
        self._provisioning_button.configure(state=state)
        self._node_name_entry.configure(state=state)


__all__ = ["WorkflowSelectorPanel"]
