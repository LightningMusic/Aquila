"""
Project Aquila
=============

Application Shutdown

Tears down every core Aquila service started by ``core.startup``, in
the order that keeps logging available for as long as possible: every
other service is stopped first, then ``LogManager`` last, so its own
shutdown -- and every other service's -- ends up recorded in the log
it just finished writing.

NFR-REL-001 ("Unexpected subsystem failures shall not corrupt
deployment logs"): this ordering is exactly why ``LogManager`` goes
last -- if some other service's own teardown were to fail
unexpectedly while logging had already been shut down, that failure
would have nowhere safe to be recorded and could tear at a log file
mid-write; keeping the Logging Engine alive until everything else has
finished means a failure elsewhere during shutdown is still captured
by a fully intact logging system.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from typing import Optional, cast

from common.application import Application
from common.enums import ApplicationState
from config.manager import ConfigurationManager
from core.lifecycle import ApplicationLifecycle
from logging_engine.log_manager import LogManager

_module_logger = logging.getLogger(__name__)


def shutdown(
    app: Application,
    lifecycle: Optional[ApplicationLifecycle] = None,
) -> None:
    """
    Tear down every core Aquila service and stop the application.

    Safe to call on an application that only partially started (for
    example, after ``core.startup.startup()`` raised): each service
    is looked up with ``ServiceContainer.contains()`` first, so a
    service that never got registered is simply skipped rather than
    raising a ``KeyError``.

    Parameters
    ----------
    app:
        The application to tear down.

    lifecycle:
        The lifecycle ``core.startup.startup()`` returned alongside
        ``app``. When omitted, this looks it up from
        ``app.services`` (``startup()`` always registers it there),
        so a caller that only kept the ``Application`` reference can
        still call this correctly.
    """

    if lifecycle is None and app.services.contains(ApplicationLifecycle):
        lifecycle = app.services.resolve(ApplicationLifecycle)

    if lifecycle is not None and lifecycle.can_transition_to(
        ApplicationState.STOPPING
    ):
        lifecycle.transition_to(ApplicationState.STOPPING)

    log_manager: Optional[LogManager] = None

    if app.services.contains(LogManager):
        # ServiceContainer.resolve() returns Any; casting here (after
        # contains() already proved the type is registered) is what
        # lets pyright narrow `log_manager` from `Optional[LogManager]`
        # to `LogManager` for the rest of this function -- assigning a
        # bare `Any` wouldn't narrow away the `None` half on its own.
        log_manager = cast(LogManager, app.services.resolve(LogManager))
        log_manager.root_logger.info("%s shutting down.", app.name)

    if app.services.contains(ConfigurationManager):
        app.services.resolve(ConfigurationManager).shutdown()

    if log_manager is not None:
        log_manager.shutdown()
    else:  # pragma: no cover - only reachable if startup() never ran
        _module_logger.info("%s shutting down (no LogManager was registered).", app.name)

    app.stop()

    if lifecycle is not None and not lifecycle.is_terminal:
        lifecycle.transition_to(ApplicationState.STOPPED)


__all__ = ["shutdown"]
