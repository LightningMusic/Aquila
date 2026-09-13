"""
Project Aquila
=============

Logging Service

The Technician Console-facing facade over the Logging Engine
(``logging_engine.log_manager.LogManager``): implements REQ-TC-008
("The Technician Console shall provide access to deployment logs"),
which ``LogManager`` itself does not expose directly -- it configures
and owns loggers/handlers (REQ-LOG-001 through -015), but has no
"list what's on disk" or "read this one back" API of its own, since
nothing needed one until the Console did.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from logging_engine.log_manager import LogExportManifest, LogManager

if TYPE_CHECKING:
    from config.schemas.logging_schema import LoggingConfig


@dataclass(slots=True, frozen=True)
class LogFileInfo:
    """One log file the Technician Console can display or export."""

    name: str
    path: Path
    size_bytes: int


class LoggingService:
    """
    Facade over ``LogManager`` for REQ-TC-008. Satisfies
    ``interfaces.service.Service`` by delegating lifecycle to the
    ``LogManager`` it wraps.
    """

    def __init__(
        self,
        *,
        log_manager: Optional[LogManager] = None,
        logging_config: Optional["LoggingConfig"] = None,
    ) -> None:
        self._log_manager = log_manager or LogManager(logging_config)

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        self._log_manager.initialize()

    def shutdown(self) -> None:
        self._log_manager.shutdown()

    @property
    def is_initialized(self) -> bool:
        return self._log_manager.is_initialized

    # ------------------------------------------------------------------
    # REQ-TC-008
    # ------------------------------------------------------------------

    def list_log_files(self) -> list[LogFileInfo]:
        """
        List every ``*.log`` file currently on disk in the Logging
        Engine's configured directory, newest first.
        """

        directory = self._log_manager.log_directory
        if not directory.exists():
            return []

        files = sorted(
            directory.glob("*.log"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

        return [
            LogFileInfo(name=path.name, path=path, size_bytes=path.stat().st_size)
            for path in files
        ]

    def read_log(self, name: str, *, tail_lines: Optional[int] = None) -> str:
        """
        Read one log file's contents by filename (as returned by
        :meth:`list_log_files`).

        ``tail_lines``, when given, returns only the last N lines --
        the common case for the Console displaying a live-updating
        log without loading a potentially large file in full.

        Raises:
            FileNotFoundError: If ``name`` does not resolve to a file
                inside the Logging Engine's log directory (also
                raised, deliberately, for a path that attempts to
                escape that directory).
        """

        directory = self._log_manager.log_directory.resolve()
        candidate = (directory / name).resolve()

        if candidate.parent != directory or not candidate.is_file():
            raise FileNotFoundError(
                f"No such log file: '{name}' in {directory}."
            )

        text = candidate.read_text(encoding="utf-8", errors="replace")

        if tail_lines is None:
            return text

        lines = text.splitlines()
        return "\n".join(lines[-tail_lines:])

    def export(self, destination: Path) -> LogExportManifest:
        """Export every current log file to ``destination`` (REQ-LOG-011)."""

        return self._log_manager.export_logs(destination)


__all__ = ["LogFileInfo", "LoggingService"]
