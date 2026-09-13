"""
Project Aquila
=============

Temporary Artifact Cleanup

Implements REQ-BOOT-017 ("remove temporary installation artifacts
after successful deployment").

Exactly which files count as "temporary installation artifacts" is
Build-System/Provisioning-Engine-dependent (where the embedded Phase
Two first-boot script and Proxmox's automated-installer answer file
land is decided at USB-build time, by a subsystem not yet built) and
not fully knowable from Bootstrap alone. Rather than guess a location
and risk deleting something else that happens to live there, this
module works from an explicit, caller-supplied allow-list of paths --
conservative by construction: nothing is ever removed unless it was
named directly, and no wildcard/recursive deletion of an entire
directory tree is performed. The default list only covers what this
package's own modules could plausibly have created (a scratch
credentials file, were one ever added) -- currently empty, since no
module in this package writes one to disk; every secret already
flows through in-memory parameters, never a file.

``apt-get clean`` is offered as an opt-in step (default on) since it
is Debian's own standard, well-documented way to clear the package
cache REQ-PROV-008/010's package installation leaves behind -- freeing
disk space on a node with no further use for those archives.

Runs entirely within Phase Two.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from common.constants.logging import BOOTSTRAP_LOGGER

logger = logging.getLogger(BOOTSTRAP_LOGGER)

#: Paths this package's own modules could plausibly have created.
#: Currently empty -- see this module's docstring.
DEFAULT_CLEANUP_PATHS: tuple[Path, ...] = ()


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
class CleanupResult:
    """Outcome of REQ-BOOT-017's cleanup pass."""

    removed_paths: tuple[str, ...]
    apt_cache_cleared: bool
    detail: str


class ArtifactCleaner:
    """
    Removes temporary installation artifacts (REQ-BOOT-017) from an
    explicit, conservative allow-list -- see this module's docstring.
    """

    def __init__(
        self, *, command_runner: CommandRunner | None = None
    ) -> None:
        self._run = command_runner or _default_command_runner

    def clean(
        self,
        paths: Sequence[Path] = DEFAULT_CLEANUP_PATHS,
        *,
        clear_apt_cache: bool = True,
    ) -> CleanupResult:
        removed: list[str] = []

        for path in paths:
            try:
                if path.is_file() or path.is_symlink():
                    path.unlink()
                    removed.append(str(path))
                elif path.is_dir():
                    # Deliberately not recursive -- only an empty
                    # directory is removed, so a non-empty one (which
                    # would mean something unexpected is present) is
                    # left alone and logged rather than force-deleted.
                    path.rmdir()
                    removed.append(str(path))
            except OSError as exc:
                logger.warning(
                    "Could not remove temporary artifact %s: %s",
                    path,
                    exc,
                )

        apt_cleared = False
        if clear_apt_cache:
            apt_cleared = self._clear_apt_cache()

        detail = (
            f"Removed {len(removed)} artifact(s); apt cache "
            f"{'cleared' if apt_cleared else 'left as-is'}."
        )
        logger.info(detail)

        return CleanupResult(
            removed_paths=tuple(removed),
            apt_cache_cleared=apt_cleared,
            detail=detail,
        )

    def _clear_apt_cache(self) -> bool:
        result = self._run(["apt-get", "clean"])
        if result.returncode != 0:
            logger.warning(
                "'apt-get clean' failed (exit %d): %s",
                result.returncode,
                result.stderr.strip() or result.stdout.strip(),
            )
            return False
        return True


__all__ = ["ArtifactCleaner", "CleanupResult", "DEFAULT_CLEANUP_PATHS"]
