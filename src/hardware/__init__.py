"""
Project Aquila
=============

Hardware Detection Engines

Read-only hardware detection for the systems Aquila deploys onto
(REQ-INS-001 through REQ-INS-024: CPU, memory, storage, SMART,
network, virtualization, BIOS/firmware, battery). Each submodule
detects exactly one hardware category and returns the corresponding
model from ``models.hardware``; ``inspection/`` (next up) orchestrates
these detectors into a single hardware inspection report
(REQ-INS-025).

REQ-INS-026 is the governing constraint for every detector in this
package: "The Inspection Engine shall not modify firmware, storage
devices, operating system settings, or user data during inspection."
Every query here is read-only WMI/OS enumeration; nothing in this
package ever writes to a device, a registry key, or a file outside
its own process.

WMI access pattern
-------------------

This package intentionally reuses the exact dual-backend WMI pattern
already proven in ``bios.providers.generic_uefi``: first the
``wmi`` package (a thin, Pythonic wrapper), falling back to raw
``win32com.client`` COM automation when ``wmi`` is unavailable. Both
are optional dependencies that only exist on Windows; on any other
platform (including this development environment) every detector
here honestly reports empty/unsupported results rather than raising,
matching every other subsystem's cross-platform testability
convention.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import platform
import re
import subprocess
from typing import Any, Dict, List, Sequence, Tuple, cast

logger = logging.getLogger(__name__)

_SELECT_PATTERN = re.compile(
    r"(?is)\s*select\s+.+\s+from\s+[A-Za-z0-9_]+(?:\s+where\s+.+)?\s*"
)

# ``ASSOCIATORS OF`` is the standard WQL mechanism for walking a WMI
# association (for example: which physical disk backs a given logical
# drive letter). It is just as read-only as a ``SELECT`` -- it returns
# related instances, it never creates, modifies, or deletes one -- so
# it is allowed here under the same REQ-INS-026 constraint, alongside
# ``SELECT``, rather than reimplementing the same lookup through a
# second, less standard mechanism.
_ASSOCIATORS_PATTERN = re.compile(
    r"(?is)\s*associators\s+of\s+\{.+\}(?:\s+where\s+.+)?\s*"
)


class HardwareDetectionError(RuntimeError):
    """Raised when a hardware detector encounters an unrecoverable error."""


def is_windows() -> bool:
    """Return whether the current process is running on Windows."""

    return platform.system() == "Windows"


def query_wmi(namespace: str, query: str) -> List[Any]:
    """
    Execute a local, read-only WMI ``SELECT`` or ``ASSOCIATORS OF``
    query.

    Tries the ``wmi`` package first, then falls back to raw
    ``win32com.client`` COM automation -- the same two backends
    ``bios.providers.generic_uefi`` already relies on, so a system
    that can run one of Aquila's BIOS providers can also run every
    hardware detector in this package.

    Raises:
        ValueError: If ``query`` is not a read-only ``SELECT`` or
            ``ASSOCIATORS OF`` statement -- this package must never be
            used to execute a WMI method call (REQ-INS-026).
        HardwareDetectionError: If neither WMI backend is available or
            the query itself fails.
    """

    if not is_windows():
        return []

    if not (_SELECT_PATTERN.fullmatch(query) or _ASSOCIATORS_PATTERN.fullmatch(query)):
        raise ValueError(
            "Only read-only WMI SELECT/ASSOCIATORS OF queries are allowed."
        )

    try:
        import wmi  # type: ignore[import-untyped]

        connection = wmi.WMI(namespace=namespace)
        return list(connection.query(query))
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("Python WMI query failed in %s: %s", namespace, exc)
        raise HardwareDetectionError(str(exc)) from exc

    try:
        import win32com.client  # type: ignore[import-untyped]

        locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
        service = locator.ConnectServer(".", namespace)
        service.Security_.ImpersonationLevel = 3
        return list(service.ExecQuery(query, "WQL", 0x10 | 0x20))
    except ImportError as exc:
        raise HardwareDetectionError(
            "Neither the 'wmi' package nor 'win32com.client' is available "
            "-- hardware detection requires one of them on Windows."
        ) from exc
    except Exception as exc:
        logger.debug("COM WMI query failed in %s: %s", namespace, exc)
        raise HardwareDetectionError(str(exc)) from exc


def query_wmi_safe(namespace: str, query: str) -> List[Any]:
    """Run a WMI query and convert any backend failure to an empty result."""

    try:
        return query_wmi(namespace, query)
    except Exception as exc:
        logger.debug("WMI query was unavailable (%s): %s", query, exc)
        return []


def safe_property_value(row: Any, name: str) -> Any:
    """Read a WMI row property, tolerating both COM and ``wmi``-package rows."""

    try:
        if isinstance(row, dict):
            return cast(Dict[str, Any], row).get(name)

        return getattr(row, name, None)
    except Exception:
        return None


def first_property(rows: List[Any], name: str) -> str:
    """Return the first non-empty string value of ``name`` across ``rows``."""

    for row in rows:
        value = safe_property_value(row, name)
        if value:
            return str(value)

    return ""


def run_process(command: Sequence[str], *, timeout: float = 30.0) -> Tuple[int, str, str]:
    """
    Run a read-only subprocess without a shell and capture bounded output.

    Used only for the handful of hardware facts no WMI class exposes
    (for example, some firmware capability probes) -- never for a
    command that could modify system state, per REQ-INS-026.
    """

    try:
        process = subprocess.run(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=timeout,
            check=False,
        )
        return (process.returncode, process.stdout, process.stderr)
    except FileNotFoundError as exc:
        return (127, "", str(exc))
    except subprocess.TimeoutExpired:
        return (124, "", "Operation timed out.")
    except (OSError, ValueError) as exc:
        return (126, "", str(exc))


__all__ = [
    "HardwareDetectionError",
    "is_windows",
    "query_wmi",
    "query_wmi_safe",
    "safe_property_value",
    "first_property",
    "run_process",
]
