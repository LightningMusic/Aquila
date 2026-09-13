"""
Project Aquila
=============

Workflow: Application Manager

REQ-TC-001 through REQ-TC-005's bring-up-and-status sequence: the
piece ``core.application.run()``'s own docstring already anticipates
("both the Technician Console and the CLI workflow will start by
calling ``core.bootstrap.bootstrap()`` themselves"). Where
``core.bootstrap.bootstrap()`` is a context manager meant for a single
``with`` block that starts every core service and guarantees they are
torn down when the block exits, a Technician Console or CLI process
needs the *same* startup/shutdown guarantee spread across its own
lifecycle (``initialize()`` at launch, ``shutdown()`` at exit) rather
than one enclosing block -- this module is that adapter, holding
``bootstrap()``'s context open via ``contextlib.ExitStack`` so it can
be entered and exited through ``interfaces.service.Service``'s
ordinary two-method lifecycle instead.

REQ-TC-002 vs. REQ-TC-003: two different "versions"
---------------------------------------------------------
REQ-TC-002 ("display the current Aquila software version") is
``common.version.APPLICATION.version`` -- always available the moment
the application starts. REQ-TC-003 ("display the current deployment
media version") is a *different* fact: which USB build/release this
specific media is, which will not always equal the software version
once the not-yet-built Build System exists (media gets rebuilt on its
own release cadence). No Build System exists yet to stamp a media
version marker anywhere, so :attr:`ApplicationManager
.deployment_media_version` reads an optional marker file, provided by
a future Build System, and returns ``None`` -- not a fabricated
value -- when it is absent, exactly the "record the limitation and
continue" convention ``bios/`` and ``provisioning.boot_handoff``
already establish for other not-yet-built dependencies.

REQ-TC-005: "the currently detected target computer"
------------------------------------------------------------
This is not available at bring-up -- it depends on
:mod:`workflows.inspection_manager` having already run. Rather than
this module re-deriving it (which would duplicate
``workflows.deployment_manager``'s own ``_extract_system_identity``
helper), a caller records it here once Inspection completes
(:meth:`ApplicationManager.record_target_computer`), so every other
REQ-TC-002 through -004 status fact and this one live behind the same
status-display surface a Console's status bar/header actually reads
from.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from common.application import Application
from common.constants.logging import WORKFLOW_LOGGER
from common.exceptions.application import AquilaStateError
from common.service_container import ServiceContainer
from common.version import APPLICATION
from core.bootstrap import bootstrap
from inspection.report import HardwareInspectionReport

logger = logging.getLogger(WORKFLOW_LOGGER)

#: REQ-TC-003's deployment media version marker, expected at the root
#: of the deployment media the Console is running from -- see the
#: module docstring for why this is optional. Not yet produced by any
#: build tooling (the Build System is not yet built).
DEFAULT_MEDIA_VERSION_FILENAME = "media-version.txt"


class ApplicationManager:
    """
    REQ-TC-001 through REQ-TC-005's bring-up-and-status layer.
    Satisfies ``interfaces.service.Service``.
    """

    def __init__(
        self,
        *,
        configs_dir: Optional[Path] = None,
        media_root: Optional[Path] = None,
        media_version_filename: str = DEFAULT_MEDIA_VERSION_FILENAME,
    ) -> None:
        self._configs_dir = configs_dir
        self._media_root = media_root
        self._media_version_filename = media_version_filename

        self._exit_stack: Optional[ExitStack] = None
        self._app: Optional[Application] = None
        self._started_at: Optional[datetime] = None
        self._target_computer_summary: Optional[str] = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Service lifecycle (REQ-TC-001)
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """
        Bring up every core Aquila service. Idempotent: calling this
        again first tears down whatever is currently running.
        """

        if self._initialized:
            self.shutdown()

        self._exit_stack = ExitStack()
        self._app = self._exit_stack.enter_context(
            bootstrap(configs_dir=self._configs_dir)
        )
        self._started_at = datetime.now(UTC)
        self._initialized = True

        logger.info(
            "%s v%s ready (REQ-TC-001).", APPLICATION.name, APPLICATION.version
        )

    def shutdown(self) -> None:
        if self._exit_stack is not None:
            self._exit_stack.close()

        self._exit_stack = None
        self._app = None
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    # ------------------------------------------------------------------
    # Service resolution
    # ------------------------------------------------------------------

    @property
    def application(self) -> Application:
        """The running ``common.application.Application``."""

        if self._app is None:
            raise AquilaStateError(
                "ApplicationManager has not been initialized -- call "
                "initialize() first."
            )
        return self._app

    @property
    def services(self) -> ServiceContainer:
        """
        The running application's ``ServiceContainer``, for resolving
        ``ConfigurationManager``, ``LogManager``, or any other
        registered core service.
        """

        return self.application.services

    # ------------------------------------------------------------------
    # REQ-TC-002: Aquila software version
    # ------------------------------------------------------------------

    @property
    def aquila_version(self) -> str:
        return APPLICATION.version

    # ------------------------------------------------------------------
    # REQ-TC-003: deployment media version
    # ------------------------------------------------------------------

    @property
    def deployment_media_version(self) -> Optional[str]:
        """
        The deployment media's own version marker, or ``None`` if no
        marker file is present -- see the module docstring.
        """

        if self._media_root is None:
            return None

        marker = self._media_root / self._media_version_filename
        if not marker.is_file():
            return None

        try:
            return marker.read_text(encoding="utf-8").strip() or None
        except OSError:
            logger.debug(
                "Could not read deployment media version marker at %s.",
                marker,
                exc_info=True,
            )
            return None

    # ------------------------------------------------------------------
    # REQ-TC-004: current date and time
    # ------------------------------------------------------------------

    @property
    def current_datetime(self) -> datetime:
        return datetime.now(UTC)

    @property
    def started_at(self) -> Optional[datetime]:
        return self._started_at

    # ------------------------------------------------------------------
    # REQ-TC-005: currently detected target computer
    # ------------------------------------------------------------------

    @property
    def target_computer_summary(self) -> Optional[str]:
        """
        A human-readable summary of the currently detected target
        computer, or ``None`` before Inspection has run -- see
        :meth:`record_target_computer`.
        """

        return self._target_computer_summary

    def record_target_computer(self, report: HardwareInspectionReport) -> None:
        """
        Record the target computer's identity from a completed
        inspection report (REQ-TC-005), typically called once
        ``workflows.inspection_manager.InspectionWorkflowStage.run()``
        returns.
        """

        firmware = report.bios.data.firmware
        manufacturer = firmware.manufacturer or "Unknown manufacturer"
        model = firmware.model or "Unknown model"
        serial = firmware.serial_number or "unknown serial"

        self._target_computer_summary = f"{manufacturer} {model} (serial: {serial})"

        logger.info(
            "Target computer detected: %s", self._target_computer_summary
        )

    # ------------------------------------------------------------------
    # Magic methods
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"initialized={self._initialized}, "
            f"version={self.aquila_version})"
        )


__all__ = ["DEFAULT_MEDIA_VERSION_FILENAME", "ApplicationManager"]
