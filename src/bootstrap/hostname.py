"""
Project Aquila
=============

Hostname Configuration

Implements REQ-BOOT-005 ("configure the system hostname assigned by
the Deployment Controller").

Runs entirely within Phase Two -- the freshly-installed Linux node,
not the WinPE Technician Console -- so this uses standard Debian/
systemd tooling (``hostnamectl``), not WMI.

``hostnamectl set-hostname`` updates ``/etc/hostname`` (and the
transient/pretty hostnames) but does not touch ``/etc/hosts``, so a
freshly-set hostname commonly fails to resolve to 127.0.1.1 locally
until ``/etc/hosts`` is also updated -- a well-known Debian/systemd
gap, not an Aquila-specific quirk. This module does both.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from common.constants.logging import BOOTSTRAP_LOGGER
from common.exceptions.deployment import DeploymentConfigurationError

logger = logging.getLogger(BOOTSTRAP_LOGGER)

#: A conservative RFC 1123-style hostname pattern: letters, digits,
#: and hyphens, 1-63 characters per label, not starting/ending with a
#: hyphen. Deliberately stricter than what Linux itself will accept,
#: since this hostname is also used as the node's cluster/DNS name.
_HOSTNAME_PATTERN = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$"
)

_HOSTS_MARKER = "# Managed by Project Aquila Bootstrap Engine"


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
class HostnameResult:
    """Outcome of one REQ-BOOT-005 hostname-configuration attempt."""

    hostname: str
    applied: bool
    detail: str


def _validate_hostname(hostname: str) -> None:
    if not hostname or not _HOSTNAME_PATTERN.match(hostname):
        raise DeploymentConfigurationError(
            f"'{hostname}' is not a valid hostname label "
            "(letters, digits, hyphens only; 1-63 characters; must "
            "not start or end with a hyphen)."
        )


class HostnameConfigurator:
    """
    Applies the hostname the Deployment Controller assigned to this
    node (REQ-BOOT-005, REQ-CTRL-004).
    """

    def __init__(
        self,
        *,
        command_runner: CommandRunner | None = None,
        hosts_file: Path | None = None,
    ) -> None:
        self._run = command_runner or _default_command_runner
        self._hosts_file = hosts_file or Path("/etc/hosts")

    def configure(self, hostname: str) -> HostnameResult:
        """
        Set the node's hostname and its ``/etc/hosts`` loopback entry.

        Raises:
            DeploymentConfigurationError: If ``hostname`` is not a
                valid hostname label, or ``hostnamectl`` fails.
        """

        _validate_hostname(hostname)

        result = self._run(["hostnamectl", "set-hostname", hostname])
        if result.returncode != 0:
            detail = (
                f"'hostnamectl set-hostname {hostname}' failed "
                f"(exit {result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
            logger.error(detail)
            raise DeploymentConfigurationError(detail)

        self._update_hosts_file(hostname)

        detail = f"Hostname set to '{hostname}'."
        logger.info(detail)
        return HostnameResult(
            hostname=hostname, applied=True, detail=detail
        )

    def _update_hosts_file(self, hostname: str) -> None:
        """
        Ensure a ``127.0.1.1 <hostname>`` line exists in
        ``/etc/hosts``, replacing any prior Aquila-managed line.
        """

        try:
            existing = (
                self._hosts_file.read_text(encoding="utf-8")
                if self._hosts_file.exists()
                else ""
            )
        except OSError as exc:
            raise DeploymentConfigurationError(
                f"Could not read {self._hosts_file}: {exc}"
            ) from exc

        kept_lines = [
            line
            for line in existing.splitlines()
            if _HOSTS_MARKER not in line
        ]

        # Drop a trailing blank line so the marker line reads cleanly.
        while kept_lines and not kept_lines[-1].strip():
            kept_lines.pop()

        kept_lines.append(f"127.0.1.1\t{hostname}\t{_HOSTS_MARKER}")

        try:
            self._hosts_file.write_text(
                "\n".join(kept_lines) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            raise DeploymentConfigurationError(
                f"Could not write {self._hosts_file}: {exc}"
            ) from exc


__all__ = [
    "CommandRunner",
    "HostnameConfigurator",
    "HostnameResult",
]
