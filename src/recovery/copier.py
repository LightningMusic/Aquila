"""
Project Aquila
=============

Recovery Copying

Implements REQ-REC-006 (select individual files or directories for
recovery), REQ-REC-007 (recovery to a technician-designated external
destination), REQ-REC-008 (verify sufficient destination free space
before beginning), REQ-REC-009 (preserve original directory
structure), REQ-REC-010 (preserve file timestamps), REQ-REC-011
(display recovery progress), REQ-REC-013 (report files that could not
be copied), REQ-REC-018/019/020 (never alter, delete, or modify the
metadata of source files), REQ-REC-023 (continue recovering remaining
accessible data when unreadable sectors are encountered), and
REQ-REC-025 (terminate immediately if the destination becomes
unavailable).

Source immutability (REQ-REC-018/019/020)
-------------------------------------------
Every operation in this module opens source files for reading only.
``common.utils.filesystem.copy_file`` (reused here rather than
duplicated) is a thin wrapper over ``shutil.copy2``, which itself only
reads the source -- nothing in this module's call graph ever opens a
source path for writing, renames it, or deletes it.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from common.constants.logging import RECOVERY_LOGGER
from common.exceptions.recovery import FileCopyError, InsufficientStorageError
from common.utils.filesystem import copy_file, create_directory

logger = logging.getLogger(RECOVERY_LOGGER)


@dataclass(slots=True, frozen=True)
class CopyFailure:
    """One file or directory that could not be copied (REQ-REC-013)."""

    source_path: Path
    message: str


@dataclass(slots=True, frozen=True)
class CopyProgress:
    """A progress snapshot reported during ``copy_selection()`` (REQ-REC-011)."""

    current_path: Path
    files_copied_so_far: int
    bytes_copied_so_far: int


ProgressCallback = Callable[[CopyProgress], None]


@dataclass(slots=True)
class CopySelectionResult:
    """The outcome of copying one technician-selected set of paths."""

    files_copied: int = 0
    directories_copied: int = 0
    bytes_copied: int = 0
    failures: list[CopyFailure] = field(default_factory=lambda: [])
    # Populated with (source_path, destination_path) for every file
    # that copied successfully, so the caller (RecoveryManager) can
    # hand each pair to RecoveryVerifier without re-deriving
    # destination layout itself.
    copied_files: list[tuple[Path, Path]] = field(default_factory=lambda: [])
    # REQ-REC-025: set when the destination became unavailable and the
    # remaining selection was never attempted. Everything recorded
    # above this point (files_copied, copied_files, ...) still
    # reflects real, completed work -- copy_selection() never raises
    # this condition out to the caller, so that partial progress is
    # not lost from the eventual RecoverySummary.
    aborted: bool = False
    abort_reason: str | None = None


class RecoveryCopier:
    """
    Copies technician-selected files/directories from a source volume
    to a technician-designated destination, never modifying the
    source.
    """

    # ------------------------------------------------------------------
    # Free-space check (REQ-REC-008)
    # ------------------------------------------------------------------

    def check_destination_space(
        self, selection: list[Path], destination: Path
    ) -> None:
        """
        Verify the destination has enough free space for every
        selected file/directory before any copying begins.

        Raises:
            InsufficientStorageError: If the required space exceeds
                what ``destination`` currently reports as free.
        """

        required_bytes = sum(self._path_size(path) for path in selection)

        create_directory(destination)
        usage = shutil.disk_usage(destination)

        if required_bytes > usage.free:
            raise InsufficientStorageError(
                f"Recovery requires {required_bytes} byte(s) but only "
                f"{usage.free} byte(s) are free at {destination}."
            )

    @classmethod
    def _path_size(cls, path: Path) -> int:
        try:
            if path.is_dir():
                return sum(
                    cls._file_size(child)
                    for child in path.rglob("*")
                    if child.is_file()
                )
            return cls._file_size(path)
        except OSError as exc:
            logger.debug("Could not size %s for space check: %s", path, exc)
            return 0

    @staticmethod
    def _file_size(path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0

    # ------------------------------------------------------------------
    # Copying (REQ-REC-006/007/009/010/011/013/018/019/020/023/025)
    # ------------------------------------------------------------------

    def copy_selection(
        self,
        selection: list[Path],
        destination: Path,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> CopySelectionResult:
        """
        Copy every path in ``selection`` into ``destination``,
        preserving each selected item's own name as the top-level
        entry under ``destination`` (REQ-REC-009: directory structure
        below that point is preserved via the recursive walk).

        A read failure on one source file (permission denied, an
        unreadable sector, ...) is recorded as a ``CopyFailure`` and
        recovery continues with the remaining files (REQ-REC-023). A
        write failure that indicates the destination itself has
        become unavailable (REQ-REC-025) instead raises immediately,
        aborting the whole operation -- these are fundamentally
        different conditions: one affects a single file, the other
        makes every subsequent copy meaningless.
        """

        result = CopySelectionResult()
        create_directory(destination)

        for source_path in selection:
            try:
                self._copy_one_selected_path(
                    source_path, destination, result, progress_callback
                )
            except FileCopyError as exc:
                # REQ-REC-025: the destination itself is unavailable --
                # stop attempting further files/directories rather
                # than raising hundreds of identical failures, but
                # keep everything already recorded in ``result``.
                logger.error(
                    "Recovery aborted: destination unavailable (%s)", exc
                )
                result.aborted = True
                result.abort_reason = str(exc)
                break

        return result

    def _copy_one_selected_path(
        self,
        source_path: Path,
        destination: Path,
        result: CopySelectionResult,
        progress_callback: ProgressCallback | None,
    ) -> None:
        destination_root = destination / source_path.name

        try:
            is_directory = source_path.is_dir()
        except OSError as exc:
            result.failures.append(
                CopyFailure(source_path=source_path, message=str(exc))
            )
            return

        if not is_directory:
            self._copy_file(
                source_path, destination_root, result, progress_callback
            )
            return

        result.directories_copied += 1
        try:
            create_directory(destination_root)
        except OSError as exc:
            result.failures.append(
                CopyFailure(
                    source_path=source_path,
                    message=f"Could not create destination directory: {exc}",
                )
            )
            return

        try:
            entries = list(source_path.rglob("*"))
        except OSError as exc:
            result.failures.append(
                CopyFailure(
                    source_path=source_path,
                    message=f"Could not enumerate directory contents: {exc}",
                )
            )
            return

        for entry in entries:
            relative = entry.relative_to(source_path)
            entry_destination = destination_root / relative

            try:
                entry_is_directory = entry.is_dir()
            except OSError as exc:
                result.failures.append(
                    CopyFailure(source_path=entry, message=str(exc))
                )
                continue

            if entry_is_directory:
                result.directories_copied += 1
                try:
                    create_directory(entry_destination)
                except OSError as exc:
                    result.failures.append(
                        CopyFailure(source_path=entry, message=str(exc))
                    )
                continue

            self._copy_file(entry, entry_destination, result, progress_callback)

    def _copy_file(
        self,
        source_path: Path,
        destination_path: Path,
        result: CopySelectionResult,
        progress_callback: ProgressCallback | None,
    ) -> None:
        self._verify_destination_available(destination_path)

        try:
            copy_file(source_path, destination_path)
        except (OSError, PermissionError) as exc:
            if not self._destination_root_exists(destination_path):
                # The destination volume itself disappeared mid-copy
                # (REQ-REC-025) -- this is not "one unreadable file",
                # it means every remaining copy will fail identically,
                # so the whole operation aborts here rather than
                # silently recording hundreds of individual failures.
                raise FileCopyError(
                    f"Destination became unavailable while copying "
                    f"{source_path}: {exc}"
                ) from exc

            logger.warning(
                "Recovery could not copy %s: %s", source_path, exc
            )
            result.failures.append(
                CopyFailure(source_path=source_path, message=str(exc))
            )
            return

        try:
            bytes_copied = destination_path.stat().st_size
        except OSError:
            bytes_copied = 0

        result.files_copied += 1
        result.bytes_copied += bytes_copied
        result.copied_files.append((source_path, destination_path))

        logger.debug("Recovered %s -> %s", source_path, destination_path)

        if progress_callback is not None:
            progress_callback(
                CopyProgress(
                    current_path=source_path,
                    files_copied_so_far=result.files_copied,
                    bytes_copied_so_far=result.bytes_copied,
                )
            )

    @staticmethod
    def _verify_destination_available(destination_path: Path) -> None:
        """
        Best-effort pre-check for REQ-REC-025: if the destination's
        parent directory tree has already vanished (for example, a
        removable destination drive was unplugged), fail fast with a
        clear reason instead of attempting -- and failing -- every
        remaining file individually with a less informative error.
        """

        parent = destination_path.parent
        try:
            create_directory(parent)
        except OSError as exc:
            raise FileCopyError(
                f"Destination directory {parent} is unavailable: {exc}"
            ) from exc

    @staticmethod
    def _destination_root_exists(destination_path: Path) -> bool:
        current = destination_path.parent
        try:
            return current.exists()
        except OSError:
            return False


__all__ = [
    "CopyFailure",
    "CopyProgress",
    "CopySelectionResult",
    "ProgressCallback",
    "RecoveryCopier",
]
