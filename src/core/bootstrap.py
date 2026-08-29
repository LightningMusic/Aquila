"""
Project Aquila
=============

Application Bootstrap

The one recommended way to stand up a fully wired Aquila
``Application``: a context manager that starts every core service on
entry (``core.startup.startup()``) and guarantees they're torn down
on exit (``core.shutdown.shutdown()``) -- including when the ``with``
block raises, so a failure partway through a deployment workflow
never leaves file handles or half-configured loggers behind.

Not to be confused with the SRS's Bootstrap Engine
(``src/bootstrap/``), which is the first-boot configuration subsystem
that runs on a *deployed node* after Provisioning (SRS Section 9.7,
REQ-BOOT-001 through REQ-BOOT-020). This module bootstraps the Aquila
*application itself* -- generic software startup/DI wiring, the term
used in its ordinary software-engineering sense.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from common.application import Application
from core.shutdown import shutdown
from core.startup import startup


@contextmanager
def bootstrap(
    *,
    configs_dir: Optional[Path] = None,
) -> Generator[Application, None, None]:
    """
    Start every core Aquila service, yield the running application,
    and guarantee shutdown afterward.

    Example
    -------
    ::

        with bootstrap() as app:
            log_manager = app.services.resolve(LogManager)
            log_manager.root_logger.info("Doing work.")
        # every service is already shut down here, even if the
        # block above raised.

    Parameters
    ----------
    configs_dir:
        Forwarded to ``core.startup.startup()``. Intended for tests.

    Raises
    ------
    AquilaInitializationError:
        If startup fails. Whatever *did* start successfully before
        the failure is still torn down before this propagates, since
        the ``finally`` below runs regardless of how the ``try``
        block that owns this generator exits.
    """

    app = Application()

    try:
        app, lifecycle = startup(app, configs_dir=configs_dir)
    except Exception:
        # startup() raised before returning -- the try/finally below
        # never gets a chance to run, so shutdown() is called here
        # instead, releasing whatever *did* register successfully
        # before the failure (startup() registers each service
        # immediately after initializing it, not all at the end).
        shutdown(app)
        raise

    try:
        yield app
    finally:
        shutdown(app, lifecycle)


__all__ = ["bootstrap"]
