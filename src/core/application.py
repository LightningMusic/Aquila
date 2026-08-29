"""
Project Aquila
=============

Application Entry Logic

The operational entry point ``src/main.py`` will call once a
Technician Console or CLI workflow exists to hand off to (SRS Section
9.6/9.15, REQ-TC-001). Not to be confused with
``common.application.Application``, the DI-container/lifecycle class
this module brings up through ``core.bootstrap.bootstrap()`` --
``common/application.py`` owns *what* a running Aquila application
is; this module owns *what running Aquila actually does*.

No interactive frontend exists yet: ``src/technician_console/`` and
``src/cli/`` are still unimplemented stubs. ``run()`` below is not a
placeholder standing in for that -- it is the complete, correct
behavior for what exists in Aquila today: bring every core service
up, verify configuration loaded cleanly, report the result, and shut
down. That path keeps being exercised even once a frontend exists,
since both the Technician Console and the CLI workflow will start by
calling ``core.bootstrap.bootstrap()`` themselves.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from common.exceptions.application import AquilaInitializationError
from config.manager import ConfigurationManager
from core.bootstrap import bootstrap
from logging_engine.log_manager import LogManager

#: Process exit codes ``run()`` returns.
EXIT_OK = 0
EXIT_CONFIGURATION_ERROR = 1


def run(*, configs_dir: Optional[Path] = None) -> int:
    """
    Run Project Aquila.

    Brings up every core service (``core.bootstrap.bootstrap()``),
    reports any configuration problems, and shuts everything down
    cleanly before returning -- regardless of whether a frontend is
    registered.

    Returns
    -------
    ``EXIT_OK`` (0) if every configuration file loaded successfully;
    ``EXIT_CONFIGURATION_ERROR`` (1) if one or more did not, or if
    Aquila could not start at all (REQ-CONF-005: invalid configuration
    must prevent deployment from beginning -- a non-zero exit here is
    how a calling shell/service-manager finds that out). This never
    raises: it is the process entry point, so every failure mode ends
    in a returned exit code rather than a propagating exception.
    """

    try:
        with bootstrap(configs_dir=configs_dir) as app:
            log_manager = app.services.resolve(LogManager)
            config_manager = app.services.resolve(ConfigurationManager)

            exit_code = EXIT_OK
            load_errors = config_manager.load_errors()

            if load_errors:
                exit_code = EXIT_CONFIGURATION_ERROR

                log_manager.root_logger.error(
                    "%d configuration file(s) failed to load: %s",
                    len(load_errors),
                    ", ".join(sorted(load_errors)),
                )

            log_manager.root_logger.info(
                "No interactive frontend is registered yet (Technician "
                "Console / CLI workflow not yet implemented) -- core "
                "services verified and shutting down cleanly."
            )
    except AquilaInitializationError as exc:
        # A failure this fundamental (for example, a logging.yaml with
        # an invalid `level`) can happen before LogManager exists to
        # record it anywhere -- there is no log file yet to write to.
        # core.bootstrap.bootstrap() has already released whatever
        # partial state did start (its own try/except around
        # startup() guarantees that) before this propagates here, so
        # there is nothing left to clean up -- only to report.
        print(f"Aquila failed to start: {exc}", file=sys.stderr)
        return EXIT_CONFIGURATION_ERROR

    return exit_code


__all__ = ["EXIT_CONFIGURATION_ERROR", "EXIT_OK", "run"]
