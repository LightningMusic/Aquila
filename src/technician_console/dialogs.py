"""
Project Aquila
=============

Technician Console: Dialogs

Every modal interaction point REQ-TC-012 ("prevent destructive
operations from beginning until all required operator confirmations
have been completed") and the ``workflows/`` callback Protocols
(``PreparationConfirmationProvider``, ``RecoveryDecisionProvider``,
``TargetDeviceSelector``) require, plus REQ-TC-008's log viewer and
REQ-TC-013's deployment summary display.

Threading contract
--------------------
Every ``*Dialog.run()`` classmethod/function in this module is a
blocking, main-thread-only Tkinter call (``Toplevel.wait_window()``).
None of them may be called directly from the background workflow
thread that actually runs a ``workflows.WorkflowManager.start_*_workflow()``
call. Instead, ``technician_console.main_window`` wraps each one in
``MainThreadBridge.call_blocking()`` so the worker thread that invokes
a ``workflows`` callback (for example, ``confirmation_provider``)
blocks on a real answer while the dialog itself runs safely on the Tk
main thread -- see ``technician_console.thread_bridge``'s module
docstring for why this split exists.

Cancellation
-------------
None of the callback Protocols this module's dialogs implement can
express "the technician cancelled" through their return type (each
must return a real, positive decision). Every dialog here instead
raises ``common.exceptions.application.AquilaCancelledError`` when the
technician clicks Cancel or closes the dialog window, which propagates
back through ``MainThreadBridge.call_blocking()`` to the worker thread
exactly as if the technician's own code had raised it -- caught by
``technician_console.main_window`` and reported as an operator-aborted
session rather than a crash.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from common.exceptions.application import AquilaCancelledError
from models.hardware.storage import StorageDevice
from preparation.confirmations import PreparationConfirmations
from recovery.browser import RecoveryEntry, RecoveryVolume, VolumeBrowser
from services.logging_service import LoggingService
from workflows.deployment_manager import WorkflowSummary
from workflows.preparation_manager import PreparationConfirmationRequest
from workflows.provisioning_manager import ProvisioningWorkflowResult
from workflows.recovery_manager import RecoveryDecision

from .progress import format_bytes

# ---------------------------------------------------------------------------
# Simple notice dialogs
# ---------------------------------------------------------------------------


def show_info(parent: tk.Misc, title: str, message: str) -> None:
    messagebox.showinfo(title, message, parent=parent)


def show_warning(parent: tk.Misc, title: str, message: str) -> None:
    messagebox.showwarning(title, message, parent=parent)


def show_error(parent: tk.Misc, title: str, message: str) -> None:
    messagebox.showerror(title, message, parent=parent)


# ---------------------------------------------------------------------------
# Modal scaffolding shared by every dialog below
# ---------------------------------------------------------------------------


class _ModalDialog(tk.Toplevel):
    """
    Common setup for every modal dialog in this module: transient over
    its parent, input-grabbed, closing the window (Alt+F4 / the title
    bar X) is treated identically to a Cancel button.
    """

    def __init__(self, parent: tk.Misc, title: str) -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._cancelled = True

        # Centered over the parent window rather than at a fixed
        # screen position -- REQ-TC-012's confirmations must be
        # impossible to miss, which a dialog opening off-screen or
        # behind the main window would undermine.
        self.update_idletasks()

    def _center_over_parent(self) -> None:
        self.update_idletasks()
        parent = self.master
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()  # type: ignore[union-attr]
            pw, ph = parent.winfo_width(), parent.winfo_height()  # type: ignore[union-attr]
        except tk.TclError:
            return
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + max(0, (pw - w) // 2)}+{py + max(0, (ph - h) // 2)}")

    def _on_close(self) -> None:
        self._cancelled = True
        self.destroy()

    def _finish(self, *, cancelled: bool) -> None:
        self._cancelled = cancelled
        self.destroy()

    def run(self) -> None:
        """Show the dialog modally and block until it closes."""

        self._center_over_parent()
        self.grab_set()
        self.wait_window(self)
        if self._cancelled:
            raise AquilaCancelledError(
                "The technician cancelled this step."
            )


# ---------------------------------------------------------------------------
# TargetDeviceSelector
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class TargetDeviceSelection:
    """
    The technician's response to :class:`TargetDeviceDialog`.

    ``devices`` is every device selected for sanitization
    (REQ-PREP-005) -- what ``workflows.deployment_manager
    .TargetDeviceSelector`` must return. ``provisioning_device`` is
    additionally set when the dialog was opened in provisioning mode:
    exactly one of ``devices``, the single disk Proxmox VE will be
    installed to (``ProvisioningWorkflowStage.run()``'s
    ``target_device`` parameter) -- Preparation may sanitize more
    devices than Provisioning installs to (REQ-PREP-013 vs. a single
    ``target_device``).
    """

    devices: tuple[StorageDevice, ...]
    provisioning_device: Optional[StorageDevice] = None


def _device_row(device: StorageDevice) -> tuple[str, ...]:
    return (
        device.model or "(unknown model)",
        device.serial_number or "(unknown serial)",
        device.device_type.value,
        format_bytes(device.capacity_bytes),
        device.device_path,
    )


class TargetDeviceDialog(_ModalDialog):
    """
    REQ-PREP-005: lets the technician choose which storage device(s)
    are eligible for this deployment session are actually the target.

    Only devices ``StorageInventory.eligible_for_deployment()`` already
    excluded removable/boot-media disks from are shown -- this dialog
    does not re-apply that safety filter, it trusts the caller to have
    already applied it (``workflows.deployment_manager
    .TargetDeviceSelector``'s own docstring: "the candidate list").
    """

    def __init__(
        self,
        parent: tk.Misc,
        devices: list[StorageDevice],
        *,
        require_provisioning_target: bool,
    ) -> None:
        super().__init__(
            parent,
            "Select Target Storage Device(s)"
            if require_provisioning_target
            else "Select Storage Device(s) to Sanitize",
        )
        self._devices = devices
        self._require_provisioning_target = require_provisioning_target
        self._result: Optional[TargetDeviceSelection] = None

        ttk.Label(
            self,
            text=(
                "Select every storage device to sanitize. "
                + (
                    "Then choose the one device Proxmox VE will be "
                    "installed to."
                    if require_provisioning_target
                    else ""
                )
            ),
            wraplength=520,
            justify="left",
        ).pack(fill="x", padx=10, pady=(10, 4))

        columns = ("model", "serial", "type", "capacity", "path")
        self._tree = ttk.Treeview(
            self,
            columns=columns,
            show="headings",
            selectmode="extended",
            height=min(8, max(3, len(devices))),
        )
        for column, heading, width in (
            ("model", "Model", 160),
            ("serial", "Serial Number", 140),
            ("type", "Type", 90),
            ("capacity", "Capacity", 90),
            ("path", "Device Path", 160),
        ):
            self._tree.heading(column, text=heading)
            self._tree.column(column, width=width, anchor="w")

        for index, device in enumerate(devices):
            self._tree.insert("", "end", iid=str(index), values=_device_row(device))

        self._tree.pack(fill="both", expand=True, padx=10, pady=4)
        self._tree.bind("<<TreeviewSelect>>", self._on_selection_changed)

        self._provisioning_var = tk.StringVar()
        if require_provisioning_target:
            target_row = ttk.Frame(self)
            target_row.pack(fill="x", padx=10, pady=(0, 4))
            ttk.Label(target_row, text="Install Proxmox VE to:").pack(side="left")
            self._provisioning_combo = ttk.Combobox(
                target_row,
                textvariable=self._provisioning_var,
                state="readonly",
                width=60,
            )
            self._provisioning_combo.pack(side="left", padx=(6, 0), fill="x", expand=True)

        button_row = ttk.Frame(self)
        button_row.pack(fill="x", padx=10, pady=10)
        ttk.Button(button_row, text="Cancel", command=self._on_cancel).pack(
            side="right"
        )
        self._ok_button = ttk.Button(
            button_row, text="Continue", command=self._on_continue, state="disabled"
        )
        self._ok_button.pack(side="right", padx=(0, 6))

    def _on_selection_changed(self, _event: object = None) -> None:
        selected_indices = [int(iid) for iid in self._tree.selection()]
        selected_devices = [self._devices[i] for i in selected_indices]

        if self._require_provisioning_target:
            labels = [
                f"{d.model or d.device_path} ({d.serial_number or 'no serial'})"
                for d in selected_devices
            ]
            self._provisioning_combo.configure(values=labels)
            if self._provisioning_var.get() not in labels:
                self._provisioning_var.set(labels[0] if labels else "")

        self._ok_button.configure(
            state="normal" if selected_devices else "disabled"
        )

    def _on_continue(self) -> None:
        selected_indices = [int(iid) for iid in self._tree.selection()]
        selected_devices = [self._devices[i] for i in selected_indices]
        if not selected_devices:
            return

        provisioning_device: Optional[StorageDevice] = None
        if self._require_provisioning_target:
            labels = [
                f"{d.model or d.device_path} ({d.serial_number or 'no serial'})"
                for d in selected_devices
            ]
            chosen = self._provisioning_var.get()
            if chosen not in labels:
                show_error(
                    self,
                    "Selection Required",
                    "Choose which selected device Proxmox VE will be "
                    "installed to.",
                )
                return
            provisioning_device = selected_devices[labels.index(chosen)]

        self._result = TargetDeviceSelection(
            devices=tuple(selected_devices),
            provisioning_device=provisioning_device,
        )
        self._finish(cancelled=False)

    def _on_cancel(self) -> None:
        self._finish(cancelled=True)

    def run(self) -> TargetDeviceSelection:  # type: ignore[override]
        super().run()
        assert self._result is not None
        return self._result


# ---------------------------------------------------------------------------
# RecoveryDecisionProvider
# ---------------------------------------------------------------------------


class RecoveryDialog(_ModalDialog):
    """
    REQ-REC-004/005/006/016: lets the technician browse discovered
    volumes and select files/directories to recover, or explicitly
    skip recovery with a typed acknowledgement.
    """

    def __init__(
        self,
        parent: tk.Misc,
        volumes: list[RecoveryVolume],
        volume_browser: VolumeBrowser,
    ) -> None:
        super().__init__(parent, "Data Recovery")
        self._volumes = volumes
        self._browser = volume_browser
        self._result: Optional[RecoveryDecision] = None

        #: REQ-REC-006: selections persist across navigation and
        #: across volumes, keyed by (volume.device_id, relative_path).
        self._selected: dict[tuple[str, str], tuple[RecoveryVolume, RecoveryEntry]] = {}
        self._current_volume: Optional[RecoveryVolume] = None
        self._current_relative_path = ""
        self._current_entries: dict[str, RecoveryEntry] = {}

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self._recover_tab = ttk.Frame(notebook)
        self._skip_tab = ttk.Frame(notebook)
        notebook.add(self._recover_tab, text="Recover Data")
        notebook.add(self._skip_tab, text="Skip Recovery")

        self._build_recover_tab()
        self._build_skip_tab()

        self._notebook = notebook

        button_row = ttk.Frame(self)
        button_row.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(button_row, text="Cancel", command=self._on_cancel).pack(
            side="right"
        )
        ttk.Button(button_row, text="Continue", command=self._on_continue).pack(
            side="right", padx=(0, 6)
        )

    # -- Recover tab ----------------------------------------------------

    def _build_recover_tab(self) -> None:
        top = ttk.Frame(self._recover_tab)
        top.pack(fill="x", padx=6, pady=6)

        ttk.Label(top, text="Volume:").pack(side="left")
        self._volume_var = tk.StringVar()
        volume_labels = [
            f"{v.volume_name or v.device_id} ({v.device_id}, "
            f"{format_bytes(v.free_capacity_bytes)} free)"
            for v in self._volumes
        ]
        self._volume_combo = ttk.Combobox(
            top,
            textvariable=self._volume_var,
            values=volume_labels,
            state="readonly",
            width=50,
        )
        self._volume_combo.pack(side="left", padx=(6, 0))
        self._volume_combo.bind("<<ComboboxSelected>>", self._on_volume_chosen)

        self._path_var = tk.StringVar(value="/")
        ttk.Label(self._recover_tab, textvariable=self._path_var, anchor="w").pack(
            fill="x", padx=6
        )

        columns = ("name", "size", "modified")
        self._entry_tree = ttk.Treeview(
            self._recover_tab,
            columns=columns,
            show="headings",
            selectmode="extended",
            height=10,
        )
        for column, heading, width in (
            ("name", "Name", 300),
            ("size", "Size", 90),
            ("modified", "Modified", 140),
        ):
            self._entry_tree.heading(column, text=heading)
            self._entry_tree.column(column, width=width, anchor="w")
        self._entry_tree.pack(fill="both", expand=True, padx=6, pady=4)
        self._entry_tree.bind("<Double-1>", self._on_entry_activated)

        nav_row = ttk.Frame(self._recover_tab)
        nav_row.pack(fill="x", padx=6)
        ttk.Button(nav_row, text="Up One Level", command=self._go_up).pack(
            side="left"
        )
        ttk.Button(
            nav_row, text="Select Highlighted", command=self._select_highlighted
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            nav_row, text="Clear All Selections", command=self._clear_selections
        ).pack(side="left", padx=(6, 0))

        self._selection_count_var = tk.StringVar(value="0 item(s) selected.")
        ttk.Label(self._recover_tab, textvariable=self._selection_count_var).pack(
            fill="x", padx=6, pady=(2, 0)
        )

        dest_row = ttk.Frame(self._recover_tab)
        dest_row.pack(fill="x", padx=6, pady=6)
        ttk.Label(dest_row, text="Recover to:").pack(side="left")
        self._destination_var = tk.StringVar()
        ttk.Entry(dest_row, textvariable=self._destination_var, width=45).pack(
            side="left", padx=(6, 6), fill="x", expand=True
        )
        ttk.Button(dest_row, text="Browse...", command=self._choose_destination).pack(
            side="left"
        )

        if self._volumes:
            self._volume_combo.current(0)
            self._on_volume_chosen()

    def _on_volume_chosen(self, _event: object = None) -> None:
        index = self._volume_combo.current()
        if index < 0:
            return
        self._current_volume = self._volumes[index]
        self._current_relative_path = ""
        self._refresh_entries()

    def _refresh_entries(self) -> None:
        if self._current_volume is None:
            return
        self._path_var.set(f"/{self._current_relative_path}")
        try:
            entries = self._browser.browse(
                self._current_volume, self._current_relative_path
            )
        except Exception as exc:  # noqa: BLE001 - shown to the technician verbatim
            show_error(self, "Could Not Browse Volume", str(exc))
            entries = []

        self._entry_tree.delete(*self._entry_tree.get_children())
        for entry in entries:
            key = (self._current_volume.device_id, entry.relative_path)
            marker = "[selected] " if key in self._selected else ""
            name = f"{marker}{entry.name}{'/' if entry.is_directory else ''}"
            size = "" if entry.is_directory or entry.size_bytes is None else format_bytes(
                entry.size_bytes
            )
            modified = (
                entry.modified_at.strftime("%Y-%m-%d %H:%M")
                if entry.modified_at is not None
                else ""
            )
            self._entry_tree.insert(
                "",
                "end",
                iid=entry.relative_path,
                values=(name, size, modified),
                tags=("dir" if entry.is_directory else "file",),
            )

        self._current_entries = {entry.relative_path: entry for entry in entries}

    def _on_entry_activated(self, _event: object = None) -> None:
        selection = self._entry_tree.selection()
        if not selection:
            return
        entry = self._current_entries.get(selection[0])
        if entry is not None and entry.is_directory:
            self._current_relative_path = entry.relative_path
            self._refresh_entries()

    def _select_highlighted(self) -> None:
        if self._current_volume is None:
            return
        for iid in self._entry_tree.selection():
            entry = self._current_entries.get(iid)
            if entry is None or not entry.readable:
                continue
            key = (self._current_volume.device_id, entry.relative_path)
            self._selected[key] = (self._current_volume, entry)
        self._refresh_entries()
        self._update_selection_count()

    def _clear_selections(self) -> None:
        self._selected.clear()
        self._refresh_entries()
        self._update_selection_count()

    def _go_up(self) -> None:
        if not self._current_relative_path:
            return
        parent = str(Path(self._current_relative_path).parent)
        self._current_relative_path = "" if parent in (".", "/") else parent
        self._refresh_entries()

    def _update_selection_count(self) -> None:
        self._selection_count_var.set(f"{len(self._selected)} item(s) selected.")

    def _choose_destination(self) -> None:
        chosen = filedialog.askdirectory(parent=self, mustexist=True)
        if chosen:
            self._destination_var.set(chosen)

    # -- Skip tab ---------------------------------------------------------

    def _build_skip_tab(self) -> None:
        ttk.Label(
            self._skip_tab,
            text=(
                "REQ-REC-016: skipping recovery requires an explicit, "
                "typed acknowledgement that no data will be recovered "
                "from this device before it is sanitized."
            ),
            wraplength=520,
            justify="left",
        ).pack(fill="x", padx=6, pady=(10, 6))

        ttk.Label(
            self._skip_tab,
            text='Type "I acknowledge no data will be recovered" to skip:',
        ).pack(fill="x", padx=6)
        self._skip_ack_var = tk.StringVar()
        ttk.Entry(self._skip_tab, textvariable=self._skip_ack_var, width=50).pack(
            fill="x", padx=6, pady=(2, 10)
        )

    # -- Continue / Cancel -------------------------------------------------

    def _on_continue(self) -> None:
        active_tab = self._notebook.index(self._notebook.select())

        if active_tab == 1:
            acknowledgement = self._skip_ack_var.get().strip()
            if not acknowledgement:
                show_error(
                    self,
                    "Acknowledgement Required",
                    "Type the acknowledgement phrase to skip recovery.",
                )
                return
            self._result = RecoveryDecision.skip_with_acknowledgement(
                acknowledgement
            )
            self._finish(cancelled=False)
            return

        if not self._selected:
            show_error(
                self,
                "No Files Selected",
                "Select at least one file or directory to recover, or "
                "switch to the Skip Recovery tab.",
            )
            return

        destination_text = self._destination_var.get().strip()
        if not destination_text:
            show_error(
                self,
                "Destination Required",
                "Choose a destination directory for recovered files.",
            )
            return

        selected_paths = [
            volume.root_path / entry.relative_path
            for volume, entry in self._selected.values()
        ]
        self._result = RecoveryDecision.recover(
            destination=Path(destination_text),
            selected_paths=selected_paths,
        )
        self._finish(cancelled=False)

    def _on_cancel(self) -> None:
        self._finish(cancelled=True)

    def run(self) -> RecoveryDecision:  # type: ignore[override]
        super().run()
        assert self._result is not None
        return self._result


# ---------------------------------------------------------------------------
# PreparationConfirmationProvider
# ---------------------------------------------------------------------------


class PreparationConfirmationDialog(_ModalDialog):
    """
    REQ-PREP-004/005/006/007/REQ-TC-012: the irreversible-operation
    confirmation gate. The OK button stays disabled until every
    checkbox is ticked *and* the erasure phrase is typed exactly --
    mirroring ``preparation.confirmations.validate_confirmations()``'s
    own rules exactly, so nothing this dialog allows through could
    fail that validation.

    NFR-USE-003 ("Irreversible actions shall require explicit operator
    confirmation"): storage sanitization is irreversible, so unlike an
    ordinary Yes/No prompt this dialog demands an affirmative action
    per confirmation (each checkbox, plus typing the exact erasure
    phrase) rather than accepting a single click through a default
    button.
    """

    def __init__(
        self, parent: tk.Misc, request: PreparationConfirmationRequest
    ) -> None:
        super().__init__(parent, "Confirm Storage Sanitization")
        self._request = request
        self._result: Optional[PreparationConfirmations] = None

        # NFR-USE-001 ("Operator prompts shall clearly distinguish
        # informational messages, warnings, and destructive
        # operations"): this bold, red banner is this dialog's own
        # distinct visual register for a *destructive* operation --
        # a third category beyond the info/warning severities
        # ``technician_console.status_panel.StatusPanel`` already
        # separates, reserved for exactly this kind of irreversible
        # confirmation gate.
        warning = ttk.Label(
            self,
            text="WARNING: THE FOLLOWING OPERATION IS IRREVERSIBLE.",
            foreground="#a4262c",
            font=("TkDefaultFont", 11, "bold"),
        )
        warning.pack(fill="x", padx=10, pady=(10, 4))

        summary_frame = ttk.Frame(self)
        summary_frame.pack(fill="both", expand=True, padx=10, pady=4)
        summary_text = tk.Text(summary_frame, height=10, wrap="word", state="normal")
        summary_text.insert("1.0", request.summary_text)
        summary_text.configure(state="disabled")
        summary_scroll = ttk.Scrollbar(
            summary_frame, orient="vertical", command=summary_text.yview
        )
        summary_text.configure(yscrollcommand=summary_scroll.set)
        summary_text.pack(side="left", fill="both", expand=True)
        summary_scroll.pack(side="right", fill="y")

        self._target_device_var = tk.BooleanVar(value=False)
        self._final_approval_var = tk.BooleanVar(value=False)
        self._additional_vars: list[tk.BooleanVar] = []

        checks_frame = ttk.Frame(self)
        checks_frame.pack(fill="x", padx=10, pady=(6, 0))

        ttk.Checkbutton(
            checks_frame,
            text=(
                "I confirm the target storage device(s) listed above "
                "are correct (REQ-PREP-005)."
            ),
            variable=self._target_device_var,
            command=self._refresh_ok_state,
        ).pack(anchor="w")

        extra_count = max(0, request.required_confirmation_count - 3)
        for index in range(extra_count):
            var = tk.BooleanVar(value=False)
            self._additional_vars.append(var)
            ttk.Checkbutton(
                checks_frame,
                text=f"Additional confirmation {index + 1} of {extra_count}.",
                variable=var,
                command=self._refresh_ok_state,
            ).pack(anchor="w")

        ttk.Checkbutton(
            checks_frame,
            text=(
                "I give final approval to begin sanitization now "
                "(REQ-PREP-004)."
            ),
            variable=self._final_approval_var,
            command=self._refresh_ok_state,
        ).pack(anchor="w")

        phrase_row = ttk.Frame(self)
        phrase_row.pack(fill="x", padx=10, pady=(8, 0))
        ttk.Label(
            phrase_row,
            text=(
                f'Type "{request.force_confirmation_phrase}" to '
                "acknowledge that ALL data on the selected device(s) "
                "will be PERMANENTLY ERASED (REQ-PREP-006):"
            ),
            wraplength=520,
            justify="left",
        ).pack(anchor="w")
        self._phrase_var = tk.StringVar()
        self._phrase_var.trace_add("write", lambda *_: self._refresh_ok_state())
        ttk.Entry(phrase_row, textvariable=self._phrase_var, width=30).pack(
            anchor="w", pady=(2, 0)
        )

        button_row = ttk.Frame(self)
        button_row.pack(fill="x", padx=10, pady=10)
        ttk.Button(button_row, text="Cancel", command=self._on_cancel).pack(
            side="right"
        )
        self._ok_button = ttk.Button(
            button_row,
            text="Begin Sanitization",
            command=self._on_continue,
            state="disabled",
        )
        self._ok_button.pack(side="right", padx=(0, 6))

    def _refresh_ok_state(self) -> None:
        ready = (
            self._target_device_var.get()
            and self._final_approval_var.get()
            and self._phrase_var.get() == self._request.force_confirmation_phrase
            and all(var.get() for var in self._additional_vars)
        )
        self._ok_button.configure(state="normal" if ready else "disabled")

    def _on_continue(self) -> None:
        self._result = PreparationConfirmations(
            target_device_confirmed=self._target_device_var.get(),
            erasure_acknowledgement_phrase=self._phrase_var.get(),
            final_approval=self._final_approval_var.get(),
            additional_confirmations=tuple(
                var.get() for var in self._additional_vars
            ),
        )
        self._finish(cancelled=False)

    def _on_cancel(self) -> None:
        self._finish(cancelled=True)

    def run(self) -> PreparationConfirmations:  # type: ignore[override]
        super().run()
        assert self._result is not None
        return self._result


# ---------------------------------------------------------------------------
# REQ-TC-008: log viewer
# ---------------------------------------------------------------------------


class LogViewerDialog(_ModalDialog):
    """REQ-TC-008: browse and export the deployment logs."""

    def __init__(self, parent: tk.Misc, logging_service: LoggingService) -> None:
        super().__init__(parent, "Deployment Logs")
        self._service = logging_service

        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Label(top, text="Log file:").pack(side="left")

        self._file_var = tk.StringVar()
        files = self._service.list_log_files()
        self._files = {f.name: f for f in files}
        self._combo = ttk.Combobox(
            top,
            textvariable=self._file_var,
            values=[f.name for f in files],
            state="readonly",
            width=40,
        )
        self._combo.pack(side="left", padx=(6, 0))
        self._combo.bind("<<ComboboxSelected>>", lambda _e: self._load_selected())

        ttk.Button(top, text="Export...", command=self._export).pack(
            side="right"
        )
        ttk.Button(top, text="Refresh", command=self._reload_file_list).pack(
            side="right", padx=(0, 6)
        )

        text_frame = ttk.Frame(self)
        text_frame.pack(fill="both", expand=True, padx=10, pady=4)
        self._text = tk.Text(text_frame, wrap="none", state="disabled", height=24)
        v_scroll = ttk.Scrollbar(
            text_frame, orient="vertical", command=self._text.yview
        )
        h_scroll = ttk.Scrollbar(
            self, orient="horizontal", command=self._text.xview
        )
        self._text.configure(
            yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set
        )
        self._text.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)
        h_scroll.pack(fill="x", padx=10)

        ttk.Button(self, text="Close", command=lambda: self._finish(cancelled=False)).pack(
            anchor="e", padx=10, pady=10
        )

        if files:
            self._combo.current(0)
            self._load_selected()

    def _reload_file_list(self) -> None:
        files = self._service.list_log_files()
        self._files = {f.name: f for f in files}
        self._combo.configure(values=[f.name for f in files])

    def _load_selected(self) -> None:
        name = self._file_var.get()
        if not name:
            return
        try:
            content = self._service.read_log(name, tail_lines=2000)
        except FileNotFoundError as exc:
            content = f"(could not read {name}: {exc})"
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("1.0", content)
        self._text.configure(state="disabled")

    def _export(self) -> None:
        chosen = filedialog.askdirectory(parent=self, mustexist=True)
        if not chosen:
            return
        try:
            manifest = self._service.export(Path(chosen))
        except Exception as exc:  # noqa: BLE001 - shown to the technician verbatim
            show_error(self, "Export Failed", str(exc))
            return
        show_info(
            self,
            "Logs Exported",
            f"Exported {len(manifest.files)} log file(s) to {chosen}.",
        )

    def run(self) -> None:  # type: ignore[override]
        # A pure viewer -- closing it is never a cancellation of
        # anything the caller needs to know about.
        self._center_over_parent()
        self.grab_set()
        self.wait_window(self)


# ---------------------------------------------------------------------------
# REQ-TC-013: deployment summary
# ---------------------------------------------------------------------------


def _format_duration(seconds: float) -> str:
    total = int(seconds)
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


class SummaryDialog(_ModalDialog):
    """
    REQ-TC-013: "generate a deployment summary upon completion of
    every deployment session" -- renders every stage's own
    ``.status_message`` in one place.
    """

    def __init__(self, parent: tk.Misc, summary: WorkflowSummary) -> None:
        title = "Deployment Complete" if not summary.aborted else "Deployment Halted"
        super().__init__(parent, title)

        header = ttk.Label(
            self,
            text=summary.status_message,
            font=("TkDefaultFont", 11, "bold"),
            foreground="#a4262c" if summary.aborted else "#1a7a1a",
            wraplength=560,
            justify="left",
        )
        header.pack(fill="x", padx=10, pady=(10, 6))

        text_frame = ttk.Frame(self)
        text_frame.pack(fill="both", expand=True, padx=10, pady=4)
        text = tk.Text(text_frame, wrap="word", state="normal", height=20)
        text.insert("1.0", _render_summary(summary))
        text.configure(state="disabled")
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        ttk.Button(self, text="Close", command=lambda: self._finish(cancelled=False)).pack(
            anchor="e", padx=10, pady=10
        )

    def run(self) -> None:  # type: ignore[override]
        self._center_over_parent()
        self.grab_set()
        self.wait_window(self)


def _render_summary(summary: WorkflowSummary) -> str:
    # NFR-REL-004 ("Deployment reports shall clearly identify the last
    # successfully completed stage"): each stage's summary field below
    # is ``None`` until that stage actually runs, so on an aborted
    # workflow the rendered text simply stops after the last stage
    # that populated one -- the following stage sections never appear
    # -- and ``summary.abort_reason`` (appended at the end, when set)
    # names what happened right after that point.
    lines: list[str] = []
    lines.append(f"Workflow: {summary.workflow_type.value}")
    lines.append(f"Node: {summary.node_name}")
    lines.append(
        f"Started: {summary.started_at.isoformat()}  "
        f"Completed: {summary.completed_at.isoformat()}"
    )
    lines.append(f"Duration: {_format_duration(summary.duration.total_seconds())}")
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

    provisioning_result: Optional[ProvisioningWorkflowResult] = (
        summary.provisioning_result
    )
    if provisioning_result is not None:
        lines.append(f"Provisioning: {provisioning_result.status_message}")
        if provisioning_result.identity_record is not None:
            record = provisioning_result.identity_record
            lines.append(f"  Node identifier: {record.node_identifier}")
            lines.append(f"  Assigned hostname: {record.hostname}")
        lines.append("")

    if summary.aborted and summary.abort_reason:
        lines.append(f"Halt reason: {summary.abort_reason}")

    return "\n".join(lines)


__all__ = [
    "LogViewerDialog",
    "PreparationConfirmationDialog",
    "RecoveryDialog",
    "SummaryDialog",
    "TargetDeviceDialog",
    "TargetDeviceSelection",
    "show_error",
    "show_info",
    "show_warning",
]
