"""
Project Aquila
=============

CLI

A headless, scriptable front end over the same
``workflows.workflow_manager.WorkflowManager`` surface
``technician_console/`` drives -- confirmed with the user before
building this package as a *narrower, scripting/automation-focused*
tool rather than a full interactive parity with the Technician
Console: every technician decision a deployment workflow needs is
supplied via command-line flags (``cli.arguments``), answered
non-interactively (``cli.commands``), so a scripted or scheduled
invocation of ``aquila-cli`` never blocks on a terminal prompt. See
``cli.arguments``'s own module docstring for the full scope reasoning,
including why GP-001 ("Safety Before Automation") shapes the
sanitization-confirmation flags the way it does.

No SRS section names ``cli/`` directly -- Section 9.6's "Subsystems
shall not present independent interfaces to the operator" is written
with the Technician Console in mind, and this package does not violate
it: it does not add a second interactive interface competing with the
Console, it adds a non-interactive one for unattended/scripted use,
which the SRS is silent on rather than contradicting.

Package layout
----------------
* :mod:`cli.arguments` -- every subcommand's ``argparse`` surface.
* :mod:`cli.commands` -- each subcommand's implementation: service
  bring-up (:class:`cli.commands.CliContext`,
  :func:`cli.commands.build_context`), the config-driven
  ``workflows`` callback Protocols this package's counterpart to
  ``technician_console.dialogs``, and the REQ-TC-013-equivalent
  summary rendering.
* :mod:`cli.cli` -- :func:`cli.cli.main`, the argument-parse-and-
  dispatch entry point, mapping every outcome onto one of
  ``common.constants.deployment``'s process exit codes.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from typing import Optional, Sequence

from .arguments import PROGRAM_NAME, build_parser
from .cli import main as _main
from .commands import (
    CliContext,
    CliUsageError,
    build_context,
    cmd_inspect,
    cmd_logs_export,
    cmd_logs_list,
    cmd_logs_show,
    cmd_provision,
    cmd_retire,
)


def run_cli(argv: Optional[Sequence[str]] = None) -> int:
    """
    Parse ``argv`` (``sys.argv[1:]`` if omitted) and run the requested
    subcommand, returning a process exit code.

    The packaging entry point for ``aquila-cli`` should be
    ``sys.exit(run_cli())``.
    """

    return _main(argv)


__all__ = [
    "PROGRAM_NAME",
    "CliContext",
    "CliUsageError",
    "build_context",
    "build_parser",
    "cmd_inspect",
    "cmd_logs_export",
    "cmd_logs_list",
    "cmd_logs_show",
    "cmd_provision",
    "cmd_retire",
    "run_cli",
]
