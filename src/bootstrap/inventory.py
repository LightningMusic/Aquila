"""
Project Aquila
=============

Inventory Registration

Implements REQ-BOOT-014 ("register the node with the Aquila Inventory
System"), collecting REQ-INV-002's minimum inventory fields
(manufacturer, model, CPU, memory, storage, MAC address, serial
number).

Deliberately independent of Phase One's ``HardwareInspectionReport``
-- Bootstrap runs in a completely separate boot session (Phase Two,
the freshly-installed Linux node) from Inspection's WinPE/Windows
session, so there is no in-process object, and no *confirmed*
cross-phase file handoff, to reuse. This module re-collects the small
set of fields REQ-INV-002 actually requires directly from Linux,
using standard, well-documented commands (``dmidecode``, ``lscpu``,
``/proc/meminfo``, ``lsblk``, sysfs network interfaces) -- not a port
of ``hardware/``'s WMI-based detectors, which cannot run here.

This is a scope decision worth flagging, not a silent gap: a richer
alternative would have Provisioning upload the full Phase-One
``HardwareInspectionReport`` to the Deployment Controller during
REQ-PROV-004's controller-communication step, letting Bootstrap's
registration reconcile with (rather than re-derive) that data. That
upload doesn't currently exist in ``provisioning/connectivity.py``,
and adding it wasn't necessary to satisfy REQ-BOOT-014's literal
text, so it's called out in ``claude/aquila-project-status.md`` as a
possible future enrichment rather than built speculatively here.

Runs entirely within Phase Two.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from common.constants.logging import BOOTSTRAP_LOGGER

logger = logging.getLogger(BOOTSTRAP_LOGGER)

_SYS_NET_ROOT = Path("/sys/class/net")
_MEMINFO_PATH = Path("/proc/meminfo")


class CommandRunner(Protocol):
    """Runs a command and returns its completed process."""

    def __call__(
        self, args: list[str]
    ) -> subprocess.CompletedProcess[str]: ...


def _default_command_runner(
    args: list[str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        check=False,
    )


@dataclass(slots=True, frozen=True)
class NodeInventoryFacts:
    """REQ-INV-002's minimum inventory fields, Linux-collected."""

    manufacturer: str
    model: str
    serial_number: str
    cpu_model: str
    cpu_core_count: int
    memory_total_bytes: int
    primary_disk_model: str
    primary_disk_capacity_bytes: int
    mac_address: str

    def to_dict(self) -> dict[str, object]:
        return {
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial_number": self.serial_number,
            "cpu_model": self.cpu_model,
            "cpu_core_count": self.cpu_core_count,
            "memory_total_bytes": self.memory_total_bytes,
            "primary_disk_model": self.primary_disk_model,
            "primary_disk_capacity_bytes": (
                self.primary_disk_capacity_bytes
            ),
            "mac_address": self.mac_address,
        }


class InventoryCollector:
    """
    Collects REQ-INV-002's minimum inventory fields natively on
    Linux. Every individual lookup degrades to an empty/zero value
    (never raises) on hardware or environments where a given command
    is unavailable or its output is unexpected -- registration should
    proceed with whatever facts are actually collectible rather than
    fail outright over one missing field.
    """

    def __init__(
        self, *, command_runner: CommandRunner | None = None
    ) -> None:
        self._run = command_runner or _default_command_runner

    def collect(self) -> NodeInventoryFacts:
        manufacturer, model, serial = self._dmi_identity()
        cpu_model, cpu_cores = self._cpu_info()
        memory_bytes = self._memory_total_bytes()
        disk_model, disk_bytes = self._primary_disk()
        mac = self._primary_mac_address()

        return NodeInventoryFacts(
            manufacturer=manufacturer,
            model=model,
            serial_number=serial,
            cpu_model=cpu_model,
            cpu_core_count=cpu_cores,
            memory_total_bytes=memory_bytes,
            primary_disk_model=disk_model,
            primary_disk_capacity_bytes=disk_bytes,
            mac_address=mac,
        )

    def _dmidecode(self, keyword: str) -> str:
        result = self._run(["dmidecode", "-s", keyword])
        if result.returncode != 0:
            return ""
        # dmidecode emits comment lines starting with '#' for
        # inaccessible/unsupported fields.
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped
        return ""

    def _dmi_identity(self) -> tuple[str, str, str]:
        manufacturer = self._dmidecode("system-manufacturer")
        model = self._dmidecode("system-product-name")
        serial = self._dmidecode("system-serial-number")
        return manufacturer, model, serial

    def _cpu_info(self) -> tuple[str, int]:
        result = self._run(["lscpu"])
        if result.returncode != 0:
            return "", 0

        model = ""
        sockets = 1
        cores_per_socket = 0
        for line in result.stdout.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip()
            if key == "model name":
                model = value
            elif key == "socket(s)":
                sockets = self._safe_int(value, default=1)
            elif key == "core(s) per socket":
                cores_per_socket = self._safe_int(value, default=0)

        return model, sockets * cores_per_socket

    def _memory_total_bytes(self) -> int:
        if not _MEMINFO_PATH.exists():
            return 0
        try:
            for line in _MEMINFO_PATH.read_text(
                encoding="utf-8"
            ).splitlines():
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return self._safe_int(parts[1], default=0) * 1024
        except OSError:
            return 0
        return 0

    def _primary_disk(self) -> tuple[str, int]:
        result = self._run(
            [
                "lsblk",
                "-d",
                "-n",
                "-b",
                "-o",
                "NAME,MODEL,SIZE,TYPE",
            ]
        )
        if result.returncode != 0:
            return "", 0

        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 4 or parts[-1] != "disk":
                continue
            # NAME, [MODEL words...], SIZE, TYPE
            name = parts[0]
            disk_type = parts[-1]
            size = self._safe_int(parts[-2], default=0)
            model = " ".join(parts[1:-2]) if len(parts) > 3 else ""
            if name and disk_type == "disk":
                return model, size

        return "", 0

    def _primary_mac_address(self) -> str:
        if not _SYS_NET_ROOT.is_dir():
            return ""

        for interface in sorted(_SYS_NET_ROOT.iterdir()):
            if interface.name == "lo":
                continue
            address_file = interface / "address"
            try:
                address = address_file.read_text(
                    encoding="utf-8"
                ).strip()
            except OSError:
                continue
            if address and address != "00:00:00:00:00:00":
                return address

        return ""

    @staticmethod
    def _safe_int(value: str, *, default: int) -> int:
        try:
            return int(value.strip())
        except (TypeError, ValueError):
            return default


__all__ = ["InventoryCollector", "NodeInventoryFacts"]
