"""
Project Aquila
=============

Application Entry Point

``src/main.py`` is the one process both of Aquila's production
frontends are actually launched through: the Technician Console GUI
(``technician_console``, REQ-TC-001 -- launches automatically once the
deployment environment has booted) and the CLI (``cli``, for scripted
or scheduled invocations). Both packages already perform their own
complete service bring-up on their own (``technician_console.MainWindow``
and ``cli.commands.build_context`` each go through
``core.bootstrap.bootstrap()`` themselves, directly or by way of
``workflows.application_manager.ApplicationManager``) -- this module's
only job is deciding *which* frontend a given invocation wants and
handing off to it, then returning whatever exit code that frontend
produced.

This file was an empty, 0-byte placeholder until now. Nothing in this
repository previously called either frontend's entry point at all --
every frontend and workflow module that already existed was verified
directly (``run_tests_technician_console.py``, ``run_tests_cli.py``,
and friends), but no process had ever actually started Aquila as a
whole the way a technician or a script would. That gap is what this
module closes; it does not change any frontend's own behavior.

Dispatch rule
----------------
No command-line arguments (a plain double-click, or launching with no
arguments from a shell) launches the Technician Console
(``technician_console.run_console()``), matching REQ-TC-001's "launch
automatically" requirement and SRS Section 9.6's single
user-facing-application intent -- the behavior a technician testing
Aquila on their own desktop actually wants.

An invocation whose first argument is one of ``cli.arguments``'s own
top-level subcommand names (``inspect``, ``retire``, ``provision``,
``logs``) is handed to ``cli.run_cli()`` instead, so a scripted or
scheduled invocation (``aquila-cli inspect ...`` from a batch file or
another process) never launches a GUI window. This mirrors how
ordinary Windows tools that ship both a GUI and a script-friendly
command line (``msiexec``, for one) decide which mode to run in --
recognized arguments, not a separate binary -- and needs no new
configuration or packaging entry point of its own.

An invocation of exactly ``autorun`` is handed to
``cli.autorun.run_autorun()`` -- the deployment media's own
unattended-boot entry point (see that module's docstring), meant to be
the last line of ``Startnet.cmd`` on the actual bootable USB
(``python X:\\Aquila\\phase1\\src\\main.py autorun``). This is
deliberately its own explicit token rather than inferred from "no
arguments and running from real media": an environment variable a
technician sets for local testing should never silently change what a
bare double-click does.

The frontend packages are imported lazily, inside each branch, rather
than at module level: a machine with a broken ``cli`` import (a
missing dependency, say) should still be able to launch the GUI
console cleanly, and vice versa -- neither frontend's import errors
should be able to take the others down.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import sys
from typing import List, Optional

#: cli/'s own top-level subcommand names (``cli.arguments.build_parser()``).
#: Kept as a plain tuple here, rather than importing ``cli.arguments``
#: just to introspect it, so that choosing a frontend never requires
#: importing the other frontend's own dependencies first -- see the
#: "lazy import" note above.
_CLI_SUBCOMMANDS = ("inspect", "retire", "provision", "logs")


def main(argv: Optional[List[str]] = None) -> int:
    """
    Decide which frontend this invocation wants, run it, and return
    its own process exit code unchanged.

    Args:
        argv: Argument list to dispatch on, excluding the program
            name (i.e. ``sys.argv[1:]``'s shape). Defaults to the
            real ``sys.argv[1:]`` when omitted; exposed as a
            parameter so tests can dispatch without touching real
            process arguments.
    """

    args = sys.argv[1:] if argv is None else argv

    if args and args[0] == "autorun":
        from cli.autorun import run_autorun

        return run_autorun()

    if args and args[0] in _CLI_SUBCOMMANDS:
        from cli import run_cli

        return run_cli(args)

    from technician_console import run_console

    return run_console()


if __name__ == "__main__":
    sys.exit(main())
