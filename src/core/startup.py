"""
Project Aquila
=============

Application Startup

Brings up every core Aquila service, in dependency order, and
registers each with the running ``common.application.Application``'s
``ServiceContainer``. This is what fills in
``Application.initialize()``'s "Future services" comment from the
outside, without modifying ``common/application.py`` itself (which
already fully owns creating and registering the ``EventBus``).

Startup order
--------------
1. ``Application.initialize()`` -- creates and registers the
   ``EventBus`` (existing, unchanged behavior).
2. ``ConfigurationManager`` -- depends on nothing but the event bus.
3. ``LogManager`` -- depends on ``ConfigurationManager`` for its
   ``LoggingConfig``.

Every future engine (Preparation, Provisioning, Bootstrap, Deployment
Controller, ...) is registered here the same way, after ``LogManager``
so its own startup can be logged.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from common.application import Application
from common.enums import ApplicationState
from common.exceptions.application import AquilaInitializationError
from config.manager import ConfigurationManager
from core.lifecycle import ApplicationLifecycle
from logging_engine.log_manager import LogManager


def startup(
    app: Optional[Application] = None,
    *,
    configs_dir: Optional[Path] = None,
) -> tuple[Application, ApplicationLifecycle]:
    """
    Bring up every core Aquila service and return the running
    application.

    Parameters
    ----------
    app:
        An existing ``Application`` to start up. When ``None`` (the
        common case), a new one is constructed. Accepting one lets a
        caller -- chiefly ``core.bootstrap.bootstrap()`` -- construct
        it and keep a reference before startup begins.

    configs_dir:
        Overrides where ``ConfigurationManager`` reads
        ``configs/*.yaml`` from. Intended for tests; production code
        should omit this and let ``ConfigurationManager`` default to
        ``common.paths.CONFIGS_DIR``.

    Returns
    -------
    The now-running ``Application`` and the ``ApplicationLifecycle``
    that tracked bringing it up (also registered into the
    application's own ``ServiceContainer``, so anything holding the
    ``Application`` can retrieve it later with
    ``app.services.resolve(ApplicationLifecycle)``).

    Raises
    ------
    AquilaInitializationError:
        If any service fails to initialize. The lifecycle is left in
        ``ApplicationState.FAILED`` when this happens -- callers that
        catch this should still call ``core.shutdown.shutdown(app)``
        to release whatever *did* start successfully, exactly as
        ``core.bootstrap.bootstrap()`` does.
    """

    if app is None:
        app = Application()

    # Application.initialize() creates and registers the EventBus;
    # safe to call even if the caller already did (it's a documented
    # no-op the second time).
    app.initialize()
    event_bus = app.event_bus

    lifecycle = ApplicationLifecycle(event_bus=event_bus)
    app.services.register_instance(ApplicationLifecycle, lifecycle)

    lifecycle.transition_to(ApplicationState.INITIALIZING)

    try:
        config_manager = ConfigurationManager(
            configs_dir=configs_dir,
            event_bus=event_bus,
        )
        config_manager.initialize()
        app.services.register_instance(ConfigurationManager, config_manager)

        logging_config = config_manager.get_logging_config()

        log_manager = LogManager(config=logging_config, event_bus=event_bus)
        log_manager.initialize()
        app.services.register_instance(LogManager, log_manager)

        log_manager.root_logger.info(
            "%s v%s starting up.", app.name, app.version
        )

        load_errors = config_manager.load_errors()

        if load_errors:
            for name, message in sorted(load_errors.items()):
                log_manager.root_logger.warning(
                    "Configuration '%s' failed to load: %s", name, message
                )

    except Exception as exc:
        lifecycle.transition_to(ApplicationState.FAILED)

        raise AquilaInitializationError(
            f"Aquila failed to start up: {exc}"
        ) from exc

    app.start()
    lifecycle.transition_to(ApplicationState.RUNNING)

    return app, lifecycle


__all__ = ["startup"]
