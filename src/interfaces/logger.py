"""
Project Aquila
=============

Logger Interface

Structural contract satisfied by ``logging_engine.log_manager.LogManager``
(SRS Section 9.9/10.12, REQ-LOG-001 through REQ-LOG-015). Lets any
subsystem depend on "something that configures and hands back Aquila
loggers" without importing the concrete ``LogManager`` class
(NFR-MAIN-002).

Defined as a ``typing.Protocol``: ``LogManager`` already exists as a
complete, tested, ordinary class with no base class, so structural
typing lets it satisfy this contract exactly as written, with no
inheritance change.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

from interfaces.service import Service

if TYPE_CHECKING:
    from config.schemas.logging_schema import LoggingConfig
    from logging_engine.log_manager import LogExportManifest


@runtime_checkable
class LoggerProvider(Service, Protocol):
    """
    Configures Aquila's loggers and hands them back by subsystem.

    Extends :class:`interfaces.service.Service`: a logger provider is
    itself a service with an initialize/shutdown lifecycle
    (``LogManager.initialize()`` attaches every configured handler;
    ``shutdown()`` flushes and closes them).
    """

    def initialize(self, config: Optional["LoggingConfig"] = None) -> None:
        """Apply configuration and attach every handler."""
        ...

    def set_level(self, level: str) -> None:
        """Change verbosity at runtime without rebuilding handlers."""
        ...

    def get_logger(self, name: Optional[str] = None) -> logging.Logger:
        """Return an Aquila logger by (bare or namespaced) name."""
        ...

    @property
    def root_logger(self) -> logging.Logger: ...

    @property
    def deployment_logger(self) -> logging.Logger: ...

    @property
    def recovery_logger(self) -> logging.Logger: ...

    @property
    def preparation_logger(self) -> logging.Logger: ...

    @property
    def inspection_logger(self) -> logging.Logger: ...

    @property
    def provisioning_logger(self) -> logging.Logger: ...

    @property
    def network_logger(self) -> logging.Logger: ...

    @property
    def benchmark_logger(self) -> logging.Logger: ...

    @property
    def hardware_logger(self) -> logging.Logger: ...

    @property
    def bootstrap_logger(self) -> logging.Logger: ...

    @property
    def inventory_logger(self) -> logging.Logger: ...

    @property
    def api_logger(self) -> logging.Logger: ...

    @property
    def cli_logger(self) -> logging.Logger: ...

    @property
    def gui_logger(self) -> logging.Logger: ...

    @property
    def performance_logger(self) -> logging.Logger: ...

    @property
    def event_logger(self) -> logging.Logger: ...

    @property
    def workflow_logger(self) -> logging.Logger: ...

    def add_handler(self, logger_name: str, handler: logging.Handler) -> None:
        """Attach an additional handler to a managed logger (REQ-LOG-015)."""
        ...

    def export_logs(self, destination: Path) -> "LogExportManifest":
        """
        Copy the current log files into ``destination`` for bundling
        into a deployment report (REQ-LOG-011).
        """
        ...

    @property
    def log_directory(self) -> Path: ...


__all__ = ["LoggerProvider"]
