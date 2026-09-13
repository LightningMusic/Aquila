"""
Project Aquila
=============

Log Manager

Central orchestrator for the Logging Engine (SRS Section 9.9 and
10.12, REQ-LOG-001 through REQ-LOG-015). A single ``LogManager``
instance, created during application startup and registered with the
``ServiceContainer`` (SRS Section 10.14 -- mirrors how
``ConfigurationManager`` is wired in, see ``config.manager``), is the
only component that should attach handlers to an ``aquila.*`` logger;
every other subsystem just calls ``get_logger()`` or one of the named
accessors below and logs normally.

Responsibilities
-----------------
* Apply ``LoggingConfig`` (verbosity, retention, console/file output,
  redaction) to the root Aquila logger and to one dedicated, rotating
  log file per subsystem (REQ-LOG-001, REQ-LOG-014).
* Provide a typed accessor for every subsystem logger named in
  ``common.constants.logging`` -- REQ-LOG-004 through REQ-LOG-010 are
  fulfilled by *other* subsystems logging through these loggers; this
  manager's job is only to make sure every one of them is correctly
  configured before they do.
* Export the accumulated logs into a deployment report bundle, with a
  SHA-256 checksum of each exported file (REQ-LOG-011, REQ-LOG-013).
* Let a caller attach an additional handler to any managed logger
  without reaching into stdlib logging internals (REQ-LOG-015).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from common.constants.logging import (
    API_LOG_FILE,
    API_LOGGER,
    APPLICATION_LOG_FILE,
    BENCHMARK_LOG_FILE,
    BENCHMARK_LOGGER,
    BOOTSTRAP_LOG_FILE,
    BOOTSTRAP_LOGGER,
    CLI_LOG_FILE,
    CLI_LOGGER,
    DEPLOYMENT_LOG_FILE,
    DEPLOYMENT_LOGGER,
    EVENT_LOG_FILE,
    EVENT_LOGGER,
    GUI_LOG_FILE,
    GUI_LOGGER,
    HARDWARE_LOG_FILE,
    HARDWARE_LOGGER,
    INSPECTION_LOG_FILE,
    INSPECTION_LOGGER,
    INVENTORY_LOG_FILE,
    INVENTORY_LOGGER,
    NETWORK_LOG_FILE,
    NETWORK_LOGGER,
    PERFORMANCE_LOG_FILE,
    PERFORMANCE_LOGGER,
    PREPARATION_LOG_FILE,
    PREPARATION_LOGGER,
    PROVISIONING_LOG_FILE,
    PROVISIONING_LOGGER,
    RECOVERY_LOG_FILE,
    RECOVERY_LOGGER,
    ROOT_LOGGER,
    WORKFLOW_LOG_FILE,
    WORKFLOW_LOGGER,
)
from common.exceptions.application import (
    AquilaInitializationError,
    AquilaOperationError,
    AquilaValidationError,
)
from common.paths import LOG_DIR
from common.utils.filesystem import create_directory
from common.utils.hashing import sha256_file
from logging_engine.formatter import RedactingFilter
from logging_engine.handlers import (
    create_console_handler,
    create_file_handler,
    create_structured_file_handler,
)
from logging_engine.logger import get_logger

if TYPE_CHECKING:
    # Imported only for type annotations below. LogManager never
    # constructs an EventBus or a LoggingConfig itself -- the caller
    # owns both and passes them in -- so neither import needs to
    # succeed at runtime for this module to be importable.
    from common.events.bus import EventBus
    from config.schemas.logging_schema import LoggingConfig

try:
    from common.events.event import Event
except ImportError:  # pragma: no cover - event system is optional

    class _NullEvent:
        """Fallback used only if ``common.events`` cannot be
        imported. ``_publish`` never actually delivers one of these:
        it only builds an event when an ``EventBus`` was supplied,
        and supplying one requires ``common.events`` to have imported
        successfully in the first place. This stand-in exists purely
        so the name below is always bound, which keeps this module
        importable -- and honestly typed -- even in that situation.
        """

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

    Event = _NullEvent  # type: ignore[assignment,misc]

_module_logger = logging.getLogger(__name__)

_LEVEL_NAMES: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

#: Every dedicated per-subsystem logger the Logging Engine configures
#: with its own rotating file (SRS Appendix F), keyed by logger name.
#: Deliberately excludes ``APPLICATION_LOGGER`` and ``EVENT_LOGGER``:
#: the root Aquila logger already writes every propagated record --
#: from every logger below, plus anything logged directly against
#: ``aquila`` -- to ``APPLICATION_LOG_FILE`` as the aggregate
#: deployment-session log and to ``EVENT_LOG_FILE`` as the structured
#: export stream, so giving either of those two their own *additional*
#: per-subsystem file would just duplicate the same records under a
#: near-identical name with no benefit.
#: Foundational fix (``workflows/`` session): ``PREPARATION_LOGGER``/
#: ``PREPARATION_LOG_FILE`` already existed in
#: ``common.constants.logging`` (added when ``preparation/`` was
#: built, and every ``preparation/*.py`` module already logs through
#: ``PREPARATION_LOGGER``), but neither was ever imported or added to
#: this dict -- meaning ``preparation.log`` was never actually
#: created, and every record logged through ``PREPARATION_LOGGER``
#: only ever reached the root ``aquila`` logger's aggregate
#: ``application.log``/console output, never its own dedicated file.
#: Confirmed genuine (not intentional) by checking
#: ``services.logging_service.LoggingService.list_log_files()``,
#: which globs ``*.log`` in this manager's own log directory for
#: REQ-TC-008 -- a technician asking to see "the preparation log"
#: would have found nothing. Fixed here at the root rather than
#: worked around in ``services/``/``workflows/``. ``WORKFLOW_LOGGER``/
#: ``WORKFLOW_LOG_FILE`` (new, for the ``workflows/`` package this
#: session introduces) are wired in the same way from the start.
#: Per-subsystem dedicated file, one entry per requirement in
#: REQ-LOG-004 through REQ-LOG-010's "the Logging Engine shall record
#: X events" list: ``DEPLOYMENT_LOGGER`` is where deployment lifecycle
#: events (REQ-LOG-004) and deployment failures (REQ-LOG-006) both
#: land, ``INSPECTION_LOGGER`` is REQ-LOG-007's hardware inspection
#: results, ``PREPARATION_LOGGER`` is REQ-LOG-008's storage
#: sanitization operations, and ``PROVISIONING_LOGGER``/
#: ``BOOTSTRAP_LOGGER`` together are REQ-LOG-009's "Provisioning and
#: Bootstrap events" -- each gets its own rotating file below so a
#: technician (or ``LoggingService.list_log_files()``, REQ-TC-008) can
#: find "the preparation log" or "the inspection log" directly rather
#: than grepping one merged stream.
_SUBSYSTEM_LOG_FILES: dict[str, str] = {
    DEPLOYMENT_LOGGER: DEPLOYMENT_LOG_FILE,
    RECOVERY_LOGGER: RECOVERY_LOG_FILE,
    PREPARATION_LOGGER: PREPARATION_LOG_FILE,
    INSPECTION_LOGGER: INSPECTION_LOG_FILE,
    PROVISIONING_LOGGER: PROVISIONING_LOG_FILE,
    WORKFLOW_LOGGER: WORKFLOW_LOG_FILE,
    NETWORK_LOGGER: NETWORK_LOG_FILE,
    BENCHMARK_LOGGER: BENCHMARK_LOG_FILE,
    HARDWARE_LOGGER: HARDWARE_LOG_FILE,
    BOOTSTRAP_LOGGER: BOOTSTRAP_LOG_FILE,
    INVENTORY_LOGGER: INVENTORY_LOG_FILE,
    API_LOGGER: API_LOG_FILE,
    CLI_LOGGER: CLI_LOG_FILE,
    GUI_LOGGER: GUI_LOG_FILE,
    PERFORMANCE_LOGGER: PERFORMANCE_LOG_FILE,
}


@dataclass(frozen=True, slots=True)
class LogExportManifest:
    """
    Result of ``LogManager.export_logs()``.

    Records which log files were exported, when, and a SHA-256
    checksum of each exported copy (REQ-LOG-013) so a deployment
    report bundle produced later can verify none of them were altered
    after export.
    """

    destination: Path
    exported_at: datetime
    files: dict[str, str] = field(default_factory=lambda: {})

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary representation."""

        return {
            "destination": str(self.destination),
            "exported_at": self.exported_at.isoformat(),
            "files": dict(self.files),
        }


class LogManager:
    """
    Configures and owns every Aquila logger.

    A single instance is normally created during application startup
    and registered with the ``ServiceContainer`` for other subsystems
    to resolve, exactly as ``ConfigurationManager`` is (SRS Section
    10.14).
    """

    def __init__(
        self,
        config: Optional["LoggingConfig"] = None,
        event_bus: Optional["EventBus"] = None,
    ) -> None:
        self._config: Optional["LoggingConfig"] = config
        self._event_bus: Optional["EventBus"] = event_bus

        self._log_directory: Path = LOG_DIR
        self._initialized = False

        self._console_handler: Optional[logging.Handler] = None
        self._root_file_handler: Optional[logging.Handler] = None
        self._event_file_handler: Optional[logging.Handler] = None
        self._subsystem_handlers: dict[str, logging.Handler] = {}

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize(self, config: Optional["LoggingConfig"] = None) -> None:
        """
        Apply configuration and attach every handler.

        Safe to call more than once: a later call tears down every
        handler this manager previously attached before reattaching
        fresh ones, so reconfiguring never leaks duplicate handlers
        (which would otherwise silently duplicate every log line).

        Raises:
            AquilaInitializationError:
                If no ``LoggingConfig`` was supplied here or to the
                constructor.
            AquilaValidationError:
                If the configuration's ``level`` is not one of
                DEBUG/INFO/WARNING/ERROR/CRITICAL.
        """

        if config is not None:
            self._config = config

        if self._config is None:
            raise AquilaInitializationError(
                "LogManager.initialize() requires a LoggingConfig -- "
                "none was supplied to the constructor or to this call."
            )

        if self._initialized:
            self._teardown()

        self._log_directory = (
            Path(self._config.log_directory)
            if self._config.log_directory
            else LOG_DIR
        )
        create_directory(self._log_directory)

        level = self._resolve_level(self._config.level)

        redacting_filter = (
            RedactingFilter() if self._config.redact_sensitive_fields else None
        )

        root = logging.getLogger(ROOT_LOGGER)
        root.setLevel(level)
        # Prevents Aquila's own records from also reaching Python's
        # true root logger (name ""), which some other library in the
        # process may have configured with its own handler(s) -- this
        # only stops "aquila" -> "" propagation. Every "aquila.*"
        # child logger still propagates up to "aquila" normally.
        root.propagate = False

        if self._config.console_output:
            self._console_handler = create_console_handler(level=level)

            if redacting_filter is not None:
                self._console_handler.addFilter(redacting_filter)

            root.addHandler(self._console_handler)

        if self._config.file_output:
            max_bytes = self._config.max_log_size_mb * 1024 * 1024

            self._root_file_handler = create_file_handler(
                self._log_directory / APPLICATION_LOG_FILE,
                level=level,
                max_bytes_per_file=max_bytes,
                backup_count=self._config.backup_count,
            )

            if redacting_filter is not None:
                self._root_file_handler.addFilter(redacting_filter)

            root.addHandler(self._root_file_handler)

            self._event_file_handler = create_structured_file_handler(
                self._log_directory / EVENT_LOG_FILE,
                level=level,
                max_bytes_per_file=max_bytes,
                backup_count=self._config.backup_count,
            )

            if redacting_filter is not None:
                self._event_file_handler.addFilter(redacting_filter)

            root.addHandler(self._event_file_handler)

            for logger_name, file_name in _SUBSYSTEM_LOG_FILES.items():
                subsystem_logger = logging.getLogger(logger_name)
                subsystem_logger.setLevel(level)

                handler = create_file_handler(
                    self._log_directory / file_name,
                    level=level,
                    max_bytes_per_file=max_bytes,
                    backup_count=self._config.backup_count,
                )

                if redacting_filter is not None:
                    handler.addFilter(redacting_filter)

                subsystem_logger.addHandler(handler)
                self._subsystem_handlers[logger_name] = handler

        self._initialized = True

        self._publish(
            lambda: Event(
                event_type="LoggingInitialized",
                source="logging_engine.log_manager",
                payload={
                    "level": self._config.level if self._config else None,
                    "log_directory": str(self._log_directory),
                },
            )
        )

        root.info(
            "Logging Engine initialized (level=%s, directory=%s).",
            self._config.level,
            self._log_directory,
        )

    def _teardown(self) -> None:
        root = logging.getLogger(ROOT_LOGGER)

        for handler in (
            self._console_handler,
            self._root_file_handler,
            self._event_file_handler,
        ):
            if handler is not None:
                root.removeHandler(handler)
                handler.close()

        self._console_handler = None
        self._root_file_handler = None
        self._event_file_handler = None

        for logger_name, handler in self._subsystem_handlers.items():
            subsystem_logger = logging.getLogger(logger_name)
            subsystem_logger.removeHandler(handler)
            handler.close()

        self._subsystem_handlers.clear()

    def shutdown(self) -> None:
        """
        Flush and close every handler this manager attached.

        Should be called once, late in application teardown (SRS
        Section 10.14), so buffered file handles are flushed cleanly
        -- important for a packaged executable, where an unflushed
        rotating file handler can lose the last few log lines if the
        process exits abruptly.
        """

        if not self._initialized:
            return

        self._teardown()
        self._initialized = False

    # ------------------------------------------------------------------
    # Verbosity (REQ-LOG-014)
    # ------------------------------------------------------------------

    def set_level(self, level: str) -> None:
        """
        Change verbosity at runtime without rebuilding handlers.
        """

        resolved = self._resolve_level(level)

        logging.getLogger(ROOT_LOGGER).setLevel(resolved)

        if self._console_handler is not None:
            self._console_handler.setLevel(resolved)

        for logger_name, handler in self._subsystem_handlers.items():
            logging.getLogger(logger_name).setLevel(resolved)
            handler.setLevel(resolved)

        if self._config is not None:
            self._config.level = level.upper()

    @staticmethod
    def _resolve_level(level: str) -> int:
        normalized = level.upper()

        if normalized not in _LEVEL_NAMES:
            raise AquilaValidationError(
                f"Unknown log level '{level}'. Valid levels: "
                f"{', '.join(sorted(_LEVEL_NAMES))}.",
                field="level",
                value=level,
            )

        return _LEVEL_NAMES[normalized]

    # ------------------------------------------------------------------
    # Logger Access (REQ-LOG-001)
    # ------------------------------------------------------------------

    def get_logger(self, name: Optional[str] = None) -> logging.Logger:
        """Return an Aquila logger by (bare or namespaced) name."""

        return get_logger(name)

    @property
    def root_logger(self) -> logging.Logger:
        return logging.getLogger(ROOT_LOGGER)

    @property
    def deployment_logger(self) -> logging.Logger:
        return logging.getLogger(DEPLOYMENT_LOGGER)

    @property
    def recovery_logger(self) -> logging.Logger:
        return logging.getLogger(RECOVERY_LOGGER)

    @property
    def preparation_logger(self) -> logging.Logger:
        return logging.getLogger(PREPARATION_LOGGER)

    @property
    def inspection_logger(self) -> logging.Logger:
        return logging.getLogger(INSPECTION_LOGGER)

    @property
    def provisioning_logger(self) -> logging.Logger:
        return logging.getLogger(PROVISIONING_LOGGER)

    @property
    def network_logger(self) -> logging.Logger:
        return logging.getLogger(NETWORK_LOGGER)

    @property
    def benchmark_logger(self) -> logging.Logger:
        return logging.getLogger(BENCHMARK_LOGGER)

    @property
    def hardware_logger(self) -> logging.Logger:
        return logging.getLogger(HARDWARE_LOGGER)

    @property
    def bootstrap_logger(self) -> logging.Logger:
        return logging.getLogger(BOOTSTRAP_LOGGER)

    @property
    def inventory_logger(self) -> logging.Logger:
        return logging.getLogger(INVENTORY_LOGGER)

    @property
    def api_logger(self) -> logging.Logger:
        return logging.getLogger(API_LOGGER)

    @property
    def cli_logger(self) -> logging.Logger:
        return logging.getLogger(CLI_LOGGER)

    @property
    def gui_logger(self) -> logging.Logger:
        return logging.getLogger(GUI_LOGGER)

    @property
    def performance_logger(self) -> logging.Logger:
        return logging.getLogger(PERFORMANCE_LOGGER)

    @property
    def event_logger(self) -> logging.Logger:
        return logging.getLogger(EVENT_LOGGER)

    @property
    def workflow_logger(self) -> logging.Logger:
        return logging.getLogger(WORKFLOW_LOGGER)

    # ------------------------------------------------------------------
    # Extension Point (REQ-LOG-015)
    # ------------------------------------------------------------------

    def add_handler(self, logger_name: str, handler: logging.Handler) -> None:
        """
        Attach an additional handler to a managed logger.

        Intended for a future centralized log aggregation integration
        (for example, a ``SysLogHandler`` or an HTTP forwarder)
        without requiring changes to this class.
        """

        logging.getLogger(logger_name).addHandler(handler)

    # ------------------------------------------------------------------
    # Export (REQ-LOG-011, REQ-LOG-013)
    # ------------------------------------------------------------------

    def export_logs(self, destination: Path) -> LogExportManifest:
        """
        Copy the current log files into ``destination`` for bundling
        into a deployment report, and compute a SHA-256 checksum of
        each exported file so the report bundle can later verify none
        of them were altered after export.

        Raises:
            AquilaOperationError:
                If no log files exist yet (``initialize()`` was never
                called, or was called with ``file_output`` disabled),
                or a file could not be copied.
        """

        if (
            not self._initialized
            or self._config is None
            or not self._config.file_output
        ):
            raise AquilaOperationError(
                "export_logs",
                "No log files to export -- LogManager was never "
                "initialized with file_output enabled.",
            )

        create_directory(destination)

        checksums: dict[str, str] = {}

        for log_file in sorted(self._log_directory.glob("*.log")):
            target = destination / log_file.name

            try:
                target.write_bytes(log_file.read_bytes())
                checksums[log_file.name] = sha256_file(target)

            except OSError as exc:
                raise AquilaOperationError(
                    "export_logs",
                    f"Could not export '{log_file.name}': {exc}",
                ) from exc

        manifest = LogExportManifest(
            destination=destination,
            exported_at=datetime.now(UTC),
            files=checksums,
        )

        self.root_logger.info(
            "Exported %d log file(s) to %s.",
            len(checksums),
            destination,
        )

        return manifest

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def log_directory(self) -> Path:
        return self._log_directory

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _publish(self, build_event: Callable[[], Any]) -> None:
        if self._event_bus is None:
            return

        try:
            self._event_bus.publish(build_event())
        except Exception:  # pragma: no cover - event delivery is best-effort
            _module_logger.debug(
                "Failed to publish logging event.", exc_info=True
            )

    # ------------------------------------------------------------------
    # Magic methods
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"initialized={self._initialized}, "
            f"directory={self._log_directory})"
        )


__all__ = ["LogExportManifest", "LogManager"]
