"""
Project Aquila
=============

SSH Key Installation

Implements REQ-BOOT-006 ("install authorized SSH keys supplied by the
Deployment Controller").

Proxmox VE's default install runs SSH as ``root`` with password
authentication typically still enabled; the Deployment Controller's
supplied keys are Aquila's own mechanism for authoritative,
centrally-managed operator access to every deployed node (REQ-CTRL-007
lists "SSH configuration" as part of the distributed deployment
configuration).

``AUTHORIZED_KEYS``/``SSH_DIRECTORY`` are reused from
``common.constants.proxmox`` rather than hardcoded again here.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import stat
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from common.constants.logging import BOOTSTRAP_LOGGER
from common.constants.proxmox import AUTHORIZED_KEYS, SSH_DIRECTORY
from common.exceptions.deployment import DeploymentConfigurationError

logger = logging.getLogger(BOOTSTRAP_LOGGER)

#: Directory mode 0700, file mode 0600 -- OpenSSH refuses to honor
#: ``authorized_keys`` (or its parent directory) if group/other write
#: permission is set. Standard, well-documented OpenSSH behavior.
_SSH_DIRECTORY_MODE = 0o700
_AUTHORIZED_KEYS_MODE = 0o600

#: The minimal, well-known set of OpenSSH public-key type prefixes.
#: Used only for a cheap sanity check (catch an obviously-malformed
#: key before it's written as the *sole* access mechanism to a
#: freshly-deployed node) -- not full key validation, which is
#: OpenSSH's own job at connection time.
_KNOWN_KEY_PREFIXES = (
    "ssh-rsa",
    "ssh-ed25519",
    "ssh-dss",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "sk-ssh-ed25519@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
)


@dataclass(slots=True, frozen=True)
class SSHKeyInstallResult:
    """Outcome of one REQ-BOOT-006 SSH-key-installation attempt."""

    installed_count: int
    rejected_keys: tuple[str, ...]
    detail: str


class SSHKeyInstaller:
    """
    Installs the Deployment Controller's authorized SSH keys for
    root, replacing whatever ``authorized_keys`` previously held.

    The Controller is treated as authoritative (REQ-CTRL-007): this
    is a declarative replace, not an append, so a key revoked on the
    Controller side is also removed from the node on the next
    Bootstrap run.
    """

    def __init__(
        self,
        *,
        ssh_directory: Path | None = None,
        authorized_keys_path: Path | None = None,
    ) -> None:
        self._ssh_directory = ssh_directory or Path(SSH_DIRECTORY)
        self._authorized_keys_path = (
            authorized_keys_path or Path(AUTHORIZED_KEYS)
        )

    def install(self, keys: Sequence[str]) -> SSHKeyInstallResult:
        """
        Write ``keys`` to ``authorized_keys`` with correct ownership
        and permissions.

        Raises:
            DeploymentConfigurationError: If no valid key remains
                after filtering, or the files/directory cannot be
                written.
        """

        valid: list[str] = []
        rejected: list[str] = []

        for raw in keys:
            line = raw.strip()
            if line and line.split(None, 1)[0] in _KNOWN_KEY_PREFIXES:
                valid.append(line)
            elif line:
                rejected.append(line)

        if not valid:
            raise DeploymentConfigurationError(
                "No recognizable OpenSSH public key was supplied by "
                "the Deployment Controller -- refusing to leave a "
                "deployed node with no key-based access configured."
            )

        try:
            self._ssh_directory.mkdir(parents=True, exist_ok=True)
            self._ssh_directory.chmod(_SSH_DIRECTORY_MODE)

            content = "\n".join(valid) + "\n"
            self._authorized_keys_path.write_text(
                content, encoding="utf-8"
            )
            self._authorized_keys_path.chmod(_AUTHORIZED_KEYS_MODE)
        except OSError as exc:
            raise DeploymentConfigurationError(
                f"Could not write {self._authorized_keys_path}: {exc}"
            ) from exc

        if rejected:
            logger.warning(
                "%d supplied SSH key(s) did not match a recognized "
                "OpenSSH public-key format and were not installed.",
                len(rejected),
            )

        detail = (
            f"{len(valid)} SSH key(s) installed to "
            f"{self._authorized_keys_path}."
        )
        logger.info(detail)

        return SSHKeyInstallResult(
            installed_count=len(valid),
            rejected_keys=tuple(rejected),
            detail=detail,
        )

    def verify_permissions(self) -> bool:
        """
        Confirm the installed files carry the permissions OpenSSH
        requires -- a cheap, independent post-install check.
        """

        try:
            dir_mode = stat.S_IMODE(
                self._ssh_directory.stat().st_mode
            )
            file_mode = stat.S_IMODE(
                self._authorized_keys_path.stat().st_mode
            )
        except OSError:
            return False

        return (
            dir_mode == _SSH_DIRECTORY_MODE
            and file_mode == _AUTHORIZED_KEYS_MODE
        )


__all__ = ["SSHKeyInstallResult", "SSHKeyInstaller"]
