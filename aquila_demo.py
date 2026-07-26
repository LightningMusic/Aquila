"""
Project Aquila — Technician Console (MARKETING DEMO BUILD)
============================================================

This is a cosmetic, non-functional demo of the Technician Console
described in the Project Aquila SRS. It is intended ONLY for
marketing / sales demonstrations.

IMPORTANT:
    * This build DOES perform a small, genuine, READ-ONLY hardware scan
      (hostname, OS, CPU model, core count, RAM, disk space) using only
      the Python standard library, to show real detection working.
    * This build performs NO real disk formatting, installs, firmware
      changes, or network configuration changes.
    * This build does NOT write, modify, or delete any files on the
      host system (aside from normal Python/Tkinter startup).
    * Everything after the "LIVE SCAN COMPLETE" marker in the console
      is scripted and simulated with a timer, not a live system action.

To build a standalone .exe (Windows) for demo laptops/booths:

    pip install pyinstaller
    pyinstaller --onefile --windowed --name "Project-Aquila-Demo" aquila_demo.py

The resulting executable will be in the generated "dist" folder.

Author:
    Project Aquila Development Team
License:
    MIT
"""

from __future__ import annotations

import os
import platform
import random
import shutil
import socket
import subprocess
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk
from typing import Callable

# ----------------------------------------------------------------------
# Branding / Theme
# ----------------------------------------------------------------------

APP_NAME = "Project Aquila"
APP_TAGLINE = "Zero-Touch Infrastructure Provisioning"
APP_VERSION = "v1.0.0-demo"

BG_DARK = "#0d1117"
BG_PANEL = "#161b22"
BG_TERMINAL = "#010409"
FG_TEXT = "#c9d1d9"
FG_MUTED = "#8b949e"
ACCENT = "#58a6ff"
ACCENT_2 = "#3fb950"
WARN = "#d29922"
DANGER = "#f85149"

FONT_TITLE = ("Segoe UI", 22, "bold")
FONT_SUB = ("Segoe UI", 11)
FONT_BODY = ("Segoe UI", 10)
FONT_MONO = ("Consolas", 10)
FONT_MONO_BOLD = ("Consolas", 10, "bold")


# ----------------------------------------------------------------------
# Real, read-only hardware detection
# ----------------------------------------------------------------------
#
# Everything in this section actually inspects the machine the demo is
# running on. It never writes to disk, changes settings, or calls
# anything destructive — it only reads values the OS already exposes.
# If a value can't be determined on a given platform, it degrades to
# "Unknown" rather than guessing or failing.
# ----------------------------------------------------------------------

def _cpu_model_name() -> str:
    system = platform.system()

    try:
        if system == "Windows":
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            if name:
                return str(name).strip()

        elif system == "Linux":
            with open("/proc/cpuinfo", "r", encoding="utf-8") as handle:
                for line in handle:
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[1].strip()

        elif system == "Darwin":
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if result.stdout.strip():
                return result.stdout.strip()

    except Exception:
        pass

    return platform.processor() or platform.machine() or "Unknown CPU"


def _total_ram_bytes() -> int | None:
    system = platform.system()

    try:
        if system == "Windows":
            import ctypes

            class _MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = _MemoryStatusEx()
            status.dwLength = ctypes.sizeof(_MemoryStatusEx)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return int(status.ullTotalPhys)

        elif system == "Linux":
            with open("/proc/meminfo", "r", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("MemTotal:"):
                        kilobytes = int(line.split()[1])
                        return kilobytes * 1024

        elif system == "Darwin":
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if result.stdout.strip().isdigit():
                return int(result.stdout.strip())

    except Exception:
        return None

    return None


def real_scan_lines() -> list["LogLine"]:
    """
    Build a short block of log lines from values actually read off
    this machine. Read-only. No files written, nothing installed,
    nothing changed.
    """

    hostname = socket.gethostname()
    os_name = f"{platform.system()} {platform.release()}".strip()
    arch = platform.machine() or "Unknown"
    cpu = _cpu_model_name()
    logical_cores = os.cpu_count() or 0

    ram_bytes = _total_ram_bytes()
    ram_text = f"{ram_bytes / (1024 ** 3):.1f} GB" if ram_bytes else "Unknown"

    try:
        anchor = Path.home().anchor or os.sep
        usage = shutil.disk_usage(anchor)
        disk_text = (
            f"{usage.total / (1024 ** 3):.0f} GB total, "
            f"{usage.free / (1024 ** 3):.0f} GB free"
        )
    except Exception:
        disk_text = "Unknown"

    return [
        LogLine("[Inspection Engine] Performing LIVE scan of THIS computer...", "header", 0, 0),
        LogLine("  (every value below is read directly from your system right now)", "dim", 140, 0),
        LogLine(f"  -> Hostname: {hostname}", "ok", 220, 60),
        LogLine(f"  -> Operating System: {os_name} ({arch})", "ok", 200, 60),
        LogLine(f"  -> CPU: {cpu}", "ok", 200, 60),
        LogLine(f"  -> Logical Cores: {logical_cores}", "ok", 200, 60),
        LogLine(f"  -> Installed Memory: {ram_text}", "ok", 200, 60),
        LogLine(f"  -> System Drive: {disk_text}", "ok", 200, 60),
        LogLine("[Inspection Engine] LIVE SCAN COMPLETE.", "ok", 220, 0),
        LogLine("", "dim", 240, 0),
        LogLine(
            "  Everything from here on is SIMULATED, to demonstrate the full",
            "dim", 120, 0,
        ),
        LogLine(
            "  end-to-end workflow without installing or changing anything.",
            "dim", 60, 0,
        ),
        LogLine("", "dim", 260, 0),
    ]


# ----------------------------------------------------------------------
# Scripted log line model
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class LogLine:
    text: str
    tag: str = "info"          # info | ok | warn | danger | header | dim
    delay_ms: int = 260        # delay BEFORE this line prints
    jitter_ms: int = 140       # random +/- jitter added to delay


def _demo_notice() -> LogLine:
    return LogLine(
        "         (DEMO BUILD — no real hardware, disks, network, or "
        "firmware are touched)",
        "dim",
        120,
        0,
    )


# ----------------------------------------------------------------------
# Workflow A — Device Retirement (scripted)
# ----------------------------------------------------------------------

def workflow_device_retirement() -> list[LogLine]:
    return [
        LogLine("=== Project Aquila — Device Retirement Workflow ===", "header", 0, 0),
        _demo_notice(),
        LogLine("", "dim", 200, 0),
        LogLine("[Inspection Engine] Starting hardware inspection...", "info"),
        *real_scan_lines(),
        LogLine("[Inspection Engine] Reading SMART health data...  (simulated)", "info"),
        LogLine("  -> SMART Status: PASSED", "ok"),
        LogLine("[Inspection Engine] Detecting battery information...  (simulated)", "info"),
        LogLine("  -> Battery Health: 87%  (312 cycles)  [OK]", "ok"),
        LogLine("[Inspection Engine] Detecting firmware / BIOS...  (simulated)", "info"),
        LogLine("  -> Firmware: UEFI  Secure Boot: Enabled", "ok"),
        LogLine("[Inspection Engine] Hardware inspection complete.", "ok"),
        LogLine("[Inspection Engine] Inspection report generated.", "dim"),
        LogLine("", "dim", 200, 0),
        LogLine("[Recovery Engine] Launching optional data recovery...", "info"),
        LogLine("[Recovery Engine] Scanning readable storage volumes...", "info"),
        LogLine("  -> 1 volume found: C:\\  (NTFS, 476 GB)", "dim"),
        LogLine("[Recovery Engine] No recovery selected by technician.", "warn"),
        LogLine("[Recovery Engine] Recovery intentionally skipped.", "warn"),
        LogLine("", "dim", 200, 0),
        LogLine("[Preparation Engine] Launching storage preparation...", "info"),
        LogLine("  !! WARNING: All operations beyond this point are IRREVERSIBLE.", "danger"),
        LogLine("[Preparation Engine] Verifying target storage identity...", "info"),
        LogLine("  -> Device path, capacity, model, and serial match inspection.  [OK]", "ok"),
        LogLine("[Preparation Engine] Confirming device is not deployment media...", "info"),
        LogLine("  -> Confirmed: target is NOT the Aquila USB.  [OK]", "ok"),
        LogLine("[Preparation Engine] Awaiting operator confirmation x3...", "warn"),
        LogLine("  -> Confirmation 1/3: target device selected  (DEMO: auto-confirmed)", "dim"),
        LogLine("  -> Confirmation 2/3: data loss acknowledged  (DEMO: auto-confirmed)", "dim"),
        LogLine("  -> Confirmation 3/3: sanitization authorized (DEMO: auto-confirmed)", "dim"),
        LogLine("[Preparation Engine] Beginning sanitization (Method: Full Overwrite)...", "info", 320, 100),
        LogLine("  -> Progress: 10%", "dim", 260, 40),
        LogLine("  -> Progress: 35%", "dim", 260, 40),
        LogLine("  -> Progress: 62%", "dim", 260, 40),
        LogLine("  -> Progress: 88%", "dim", 260, 40),
        LogLine("  -> Progress: 100%", "dim", 260, 40),
        LogLine("[Preparation Engine] Verifying sanitization completion...", "info"),
        LogLine("  -> Verification: PASSED", "ok"),
        LogLine("[Preparation Engine] Sanitization report generated.", "dim"),
        LogLine("", "dim", 200, 0),
        LogLine("=== Device Retirement Complete ===", "header"),
        LogLine("System contains no recoverable customer data and is ready for reuse.", "ok"),
    ]


# ----------------------------------------------------------------------
# Workflow B — Aquila Node Provisioning (scripted)
# ----------------------------------------------------------------------

def workflow_node_provisioning() -> list[LogLine]:
    return [
        LogLine("=== Project Aquila — Node Provisioning Workflow ===", "header", 0, 0),
        _demo_notice(),
        LogLine("", "dim", 200, 0),
        LogLine("[Inspection Engine] Starting hardware inspection...", "info"),
        *real_scan_lines(),
        LogLine("  -> Virtualization: supported and ENABLED  [OK]  (simulated)", "ok"),
        LogLine("[Inspection Engine] Verifying minimum deployment requirements...", "info"),
        LogLine("  -> CPU / Memory / Storage / Ethernet / Virtualization: PASSED", "ok"),
        LogLine("", "dim", 200, 0),
        LogLine("[Networking Engine] Validating network connectivity...", "info"),
        LogLine("  -> Ethernet link detected: eth0  (1000 Mbps, full duplex)", "ok"),
        LogLine("  -> Acquiring address via DHCP...", "info", 320, 60),
        LogLine("  -> Assigned address: 192.168.1.114/24", "ok"),
        LogLine("  -> Gateway 192.168.1.1 reachable.  [OK]", "ok"),
        LogLine("  -> Deployment Controller reachable.  [OK]", "ok"),
        LogLine("", "dim", 200, 0),
        LogLine("[Technician Console] Awaiting operator authorization...", "warn"),
        LogLine("  -> Deployment authorized  (DEMO: auto-confirmed)", "dim"),
        LogLine("", "dim", 200, 0),
        LogLine("[Provisioning Engine] Partitioning target storage...", "info", 320, 80),
        LogLine("  -> GPT partition table created.", "dim"),
        LogLine("  -> EFI + root + swap partitions created.  [OK]", "ok"),
        LogLine("[Provisioning Engine] Installing Proxmox VE 9 (unattended)...", "info", 340, 100),
        LogLine("  -> Installing base system... 20%", "dim", 260, 40),
        LogLine("  -> Installing base system... 55%", "dim", 260, 40),
        LogLine("  -> Installing base system... 90%", "dim", 260, 40),
        LogLine("  -> Base installation complete.  [OK]", "ok"),
        LogLine("[Provisioning Engine] Installing Aquila bootstrap components...", "info"),
        LogLine("[Provisioning Engine] Applying deployment configuration...", "info"),
        LogLine("[Provisioning Engine] Configuring networking (bridge vmbr0)...", "info"),
        LogLine("[Provisioning Engine] Provisioning complete. Scheduling reboot...", "ok"),
        LogLine("", "dim", 260, 0),
        LogLine("        [ simulated reboot into installed system ]", "dim", 500, 0),
        LogLine("", "dim", 260, 0),
        LogLine("[Bootstrap Engine] First boot detected. Starting bootstrap...", "info"),
        LogLine("[Bootstrap Engine] Authenticating with Deployment Controller...", "info"),
        LogLine("  -> Node authenticated.  [OK]", "ok"),
        LogLine("[Bootstrap Engine] Retrieving assigned deployment configuration...", "info"),
        LogLine("  -> Hostname assigned: aquila-node-014", "ok"),
        LogLine("[Bootstrap Engine] Installing authorized SSH keys...", "info"),
        LogLine("[Bootstrap Engine] Configuring power / lid / battery policy...", "info"),
        LogLine("  -> Lid-close suspend disabled for server role.  [OK]", "ok"),
        LogLine("  -> Battery charge threshold set to 80%.  [OK]", "ok"),
        LogLine("[Bootstrap Engine] Enrolling node into cluster \"aquila-cluster\"...", "info", 320, 80),
        LogLine("  -> Cluster enrollment verified.  [OK]", "ok"),
        LogLine("[Bootstrap Engine] Registering node in Inventory System...", "info"),
        LogLine("  -> Node ID: AQL-00014 registered.  [OK]", "ok"),
        LogLine("[Benchmark Engine] Running hardware benchmark suite...", "info", 320, 100),
        LogLine("  -> CPU benchmark complete.", "dim", 240, 40),
        LogLine("  -> Memory benchmark complete.", "dim", 240, 40),
        LogLine("  -> Storage benchmark complete.", "dim", 240, 40),
        LogLine("  -> Network benchmark complete.", "dim", 240, 40),
        LogLine("  -> Overall benchmark score: 8420", "ok"),
        LogLine("[Bootstrap Engine] Reporting deployment completion...", "info"),
        LogLine("", "dim", 200, 0),
        LogLine("=== Node Provisioning Complete ===", "header"),
        LogLine("aquila-node-014 is now enrolled and operational.", "ok"),
    ]


WORKFLOWS: dict[str, Callable[[], list[LogLine]]] = {
    "retirement": workflow_device_retirement,
    "provisioning": workflow_node_provisioning,
}


# ----------------------------------------------------------------------
# UI: Terminal Panel
# ----------------------------------------------------------------------

class TerminalPanel(tk.Frame):
    """
    Fake console output panel. Prints scripted lines with small
    timed delays so it reads like a live process, without ever
    touching the real filesystem, network, or hardware.
    """

    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, bg=BG_TERMINAL)

        header = tk.Frame(self, bg="#21262d", height=30)
        header.pack(fill="x")
        for color in (DANGER, WARN, ACCENT_2):
            dot = tk.Label(header, text="\u25cf", fg=color, bg="#21262d",
                            font=("Segoe UI", 10))
            dot.pack(side="left", padx=(10 if color == DANGER else 4, 0), pady=6)
        tk.Label(
            header,
            text="technician-console — simulated output",
            fg=FG_MUTED,
            bg="#21262d",
            font=("Segoe UI", 9),
        ).pack(side="left", padx=10)

        body = tk.Frame(self, bg=BG_TERMINAL)
        body.pack(fill="both", expand=True)

        self.text = tk.Text(
            body,
            bg=BG_TERMINAL,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            font=FONT_MONO,
            wrap="word",
            padx=12,
            pady=10,
            relief="flat",
            state="disabled",
        )
        scrollbar = ttk.Scrollbar(body, command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.text.tag_configure("info", foreground=FG_TEXT, font=FONT_MONO)
        self.text.tag_configure("ok", foreground=ACCENT_2, font=FONT_MONO)
        self.text.tag_configure("warn", foreground=WARN, font=FONT_MONO)
        self.text.tag_configure("danger", foreground=DANGER, font=FONT_MONO_BOLD)
        self.text.tag_configure("header", foreground=ACCENT, font=FONT_MONO_BOLD)
        self.text.tag_configure("dim", foreground=FG_MUTED, font=FONT_MONO)

        self._pending_after_id: str | None = None

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def write_line(self, line: LogLine) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", line.text + "\n", line.tag)
        self.text.see("end")
        self.text.configure(state="disabled")

    def cancel_pending(self) -> None:
        if self._pending_after_id is not None:
            self.after_cancel(self._pending_after_id)
            self._pending_after_id = None

    def run_script(
        self,
        lines: list[LogLine],
        on_progress: Callable[[int, int], None] | None = None,
        on_complete: Callable[[], None] | None = None,
    ) -> None:
        self.cancel_pending()
        self.clear()

        total = len(lines)

        def step(index: int) -> None:
            if index >= total:
                if on_complete is not None:
                    on_complete()
                return

            line = lines[index]
            self.write_line(line)

            if on_progress is not None:
                on_progress(index + 1, total)

            next_line = lines[index + 1] if index + 1 < total else None
            delay = next_line.delay_ms if next_line else 0
            jitter = next_line.jitter_ms if next_line else 0
            delay = max(0, delay + (random.randint(-jitter, jitter) if jitter else 0))

            self._pending_after_id = self.after(delay, step, index + 1)

        self._pending_after_id = self.after(0, step, 0)


# ----------------------------------------------------------------------
# UI: Workflow Screen (runs a scripted workflow)
# ----------------------------------------------------------------------

class WorkflowScreen(tk.Frame):
    def __init__(self, parent: tk.Widget, controller: "AquilaDemoApp") -> None:
        super().__init__(parent, bg=BG_DARK)
        self.controller = controller

        top = tk.Frame(self, bg=BG_DARK)
        top.pack(fill="x", padx=24, pady=(20, 8))

        back_btn = tk.Button(
            top,
            text="\u2190 Back",
            command=self._go_back,
            bg=BG_PANEL,
            fg=FG_TEXT,
            activebackground="#21262d",
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_BODY,
            padx=14,
            pady=6,
            bd=0,
            cursor="hand2",
        )
        back_btn.pack(side="left")

        self.title_label = tk.Label(
            top, text="", bg=BG_DARK, fg=FG_TEXT, font=("Segoe UI", 15, "bold")
        )
        self.title_label.pack(side="left", padx=16)

        self.status_label = tk.Label(
            top, text="", bg=BG_DARK, fg=ACCENT, font=FONT_BODY
        )
        self.status_label.pack(side="right")

        self.progress = ttk.Progressbar(
            self, orient="horizontal", mode="determinate"
        )
        self.progress.pack(fill="x", padx=24, pady=(0, 10))

        self.terminal = TerminalPanel(self)
        self.terminal.pack(fill="both", expand=True, padx=24, pady=(0, 20))

        bottom = tk.Frame(self, bg=BG_DARK)
        bottom.pack(fill="x", padx=24, pady=(0, 20))

        self.rerun_btn = tk.Button(
            bottom,
            text="Run Again",
            command=self._start,
            bg=ACCENT,
            fg="#0d1117",
            activebackground="#79b8ff",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            padx=16,
            pady=8,
            bd=0,
            cursor="hand2",
        )
        self.rerun_btn.pack(side="right")

        tk.Label(
            bottom,
            text="DEMO MODE — simulated output only. No real system changes are made.",
            bg=BG_DARK,
            fg=FG_MUTED,
            font=("Segoe UI", 9, "italic"),
        ).pack(side="left")

        self._workflow_key: str | None = None

    def load(self, key: str, title: str) -> None:
        self._workflow_key = key
        self.title_label.configure(text=title)
        self._start()

    def _start(self) -> None:
        if self._workflow_key is None:
            return
        self.status_label.configure(text="RUNNING…", fg=WARN)
        self.progress["value"] = 0
        self.rerun_btn.configure(state="disabled")

        lines = WORKFLOWS[self._workflow_key]()

        def on_progress(done: int, total: int) -> None:
            self.progress["maximum"] = total
            self.progress["value"] = done

        def on_complete() -> None:
            self.status_label.configure(text="COMPLETE", fg=ACCENT_2)
            self.rerun_btn.configure(state="normal")

        self.terminal.run_script(lines, on_progress=on_progress, on_complete=on_complete)

    def _go_back(self) -> None:
        self.terminal.cancel_pending()
        self.controller.show_home()


# ----------------------------------------------------------------------
# UI: Home Screen
# ----------------------------------------------------------------------

class HomeScreen(tk.Frame):
    def __init__(self, parent: tk.Widget, controller: "AquilaDemoApp") -> None:
        super().__init__(parent, bg=BG_DARK)
        self.controller = controller

        header = tk.Frame(self, bg=BG_DARK)
        header.pack(fill="x", padx=40, pady=(40, 10))

        tk.Label(
            header, text=APP_NAME, bg=BG_DARK, fg=FG_TEXT, font=FONT_TITLE
        ).pack(anchor="w")
        tk.Label(
            header, text=APP_TAGLINE, bg=BG_DARK, fg=ACCENT, font=FONT_SUB
        ).pack(anchor="w", pady=(2, 0))
        tk.Label(
            header,
            text=f"Technician Console  \u2022  {APP_VERSION}  \u2022  DEMO BUILD",
            bg=BG_DARK,
            fg=FG_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(4, 0))

        divider = tk.Frame(self, bg="#21262d", height=1)
        divider.pack(fill="x", padx=40, pady=20)

        cards = tk.Frame(self, bg=BG_DARK)
        cards.pack(fill="both", expand=True, padx=40, pady=(0, 30))
        cards.columnconfigure(0, weight=1)
        cards.columnconfigure(1, weight=1)
        cards.rowconfigure(0, weight=1)

        self._make_card(
            cards,
            column=0,
            title="Device Retirement",
            description=(
                "Safely inspect a machine, optionally recover user data, "
                "then securely sanitize storage so the hardware can be "
                "reused or resold with no recoverable customer data."
            ),
            steps=["Inspection", "Recovery (optional)", "Secure Sanitization", "Verification"],
            accent=WARN,
            command=lambda: controller.start_workflow("retirement", "Device Retirement"),
        )

        self._make_card(
            cards,
            column=1,
            title="Aquila Node Provisioning",
            description=(
                "Validate hardware and network readiness, install Proxmox VE, "
                "bootstrap the operating system, and automatically enroll the "
                "node into the managed cluster."
            ),
            steps=["Inspection", "Network Validation", "Provisioning", "Bootstrap", "Cluster Enrollment"],
            accent=ACCENT,
            command=lambda: controller.start_workflow("provisioning", "Aquila Node Provisioning"),
        )

        tk.Label(
            self,
            text="This is a marketing demonstration build. No hardware, disks, "
                 "or network settings are read or modified.",
            bg=BG_DARK,
            fg=FG_MUTED,
            font=("Segoe UI", 9, "italic"),
        ).pack(pady=(0, 16))

    def _make_card(
        self,
        parent: tk.Widget,
        *,
        column: int,
        title: str,
        description: str,
        steps: list[str],
        accent: str,
        command: Callable[[], None],
    ) -> None:
        card = tk.Frame(parent, bg=BG_PANEL, padx=24, pady=22)
        card.grid(row=0, column=column, sticky="nsew", padx=12)

        tk.Label(
            card, text=title, bg=BG_PANEL, fg=FG_TEXT,
            font=("Segoe UI", 14, "bold"), anchor="w", justify="left",
        ).pack(fill="x")

        tk.Label(
            card, text=description, bg=BG_PANEL, fg=FG_MUTED,
            font=FONT_BODY, wraplength=340, justify="left", anchor="w",
        ).pack(fill="x", pady=(10, 16))

        steps_frame = tk.Frame(card, bg=BG_PANEL)
        steps_frame.pack(fill="x", pady=(0, 20))
        for step in steps:
            row = tk.Frame(steps_frame, bg=BG_PANEL)
            row.pack(fill="x", pady=2)
            tk.Label(row, text="\u25b8", bg=BG_PANEL, fg=accent, font=FONT_BODY).pack(side="left")
            tk.Label(row, text=step, bg=BG_PANEL, fg=FG_TEXT, font=FONT_BODY).pack(
                side="left", padx=(6, 0)
            )

        run_btn = tk.Button(
            card,
            text=f"Run {title} \u2192",
            command=command,
            bg=accent,
            fg="#0d1117",
            activebackground=accent,
            activeforeground="#0d1117",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            padx=16,
            pady=10,
            bd=0,
            cursor="hand2",
        )
        run_btn.pack(fill="x")


# ----------------------------------------------------------------------
# Application Shell
# ----------------------------------------------------------------------

class AquilaDemoApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title(f"{APP_NAME} — Technician Console (Demo)")
        self.geometry("1040x680")
        self.minsize(880, 600)
        self.configure(bg=BG_DARK)

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "TProgressbar",
            troughcolor=BG_PANEL,
            background=ACCENT,
            bordercolor=BG_PANEL,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
        )
        style.configure("TScrollbar", background=BG_PANEL, troughcolor=BG_TERMINAL)

        container = tk.Frame(self, bg=BG_DARK)
        container.pack(fill="both", expand=True)

        self.home_screen = HomeScreen(container, self)
        self.workflow_screen = WorkflowScreen(container, self)

        self.home_screen.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.workflow_screen.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.show_home()

    def show_home(self) -> None:
        self.home_screen.tkraise()

    def start_workflow(self, key: str, title: str) -> None:
        self.workflow_screen.load(key, title)
        self.workflow_screen.tkraise()


def main() -> None:
    app = AquilaDemoApp()
    app.mainloop()


if __name__ == "__main__":
    main()