"""
Project Aquila
=============

CLI: Entry Point

``main()`` parses ``sys.argv`` (or an explicit ``argv``, for tests),
dispatches to the matching ``cli.commands.cmd_*`` function, and maps
whatever it raises (or returns) onto one of
``common.constants.deployment``'s exit codes -- the same convention
``workflows.deployment_manager``/``preparation``/``provisioning``
already define, extended here to the one layer that actually needed a
process exit code (a GUI has no equivalent concept; a script invoking
``aquila-cli`` does).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import sys
import traceback
from typing import Optional, Sequence

from common.constants.deployment import DEPLOYMENT_CANCELLED, DEPLOYMENT_ERROR
from common.exceptions.application import AquilaError

from . import arguments, commands

#: Maps a parsed ``argparse.Namespace``'s ``(command, logs_command)`` to
#: the ``cli.commands`` function that handles it. A dict rather than a
#: chain of ``if``/``elif`` so adding a future subcommand only means
#: adding one entry here and one ``add_parser()`` call in
#: ``cli.arguments``.
_LOGS_COMMANDS = {
    "list": commands.cmd_logs_list,
    "show": commands.cmd_logs_show,
    "export": commands.cmd_logs_export,
}

_COMMANDS = {
    "inspect": commands.cmd_inspect,
    "retire": commands.cmd_retire,
    "provision": commands.cmd_provision,
}


def main(argv: Optional[Sequence[str]] = None) -> int:
    """
    Parse arguments, run the requested subcommand, and return a
    process exit code.

    Never raises: every exception this function's own code or a
    ``cli.commands.cmd_*`` function can produce is caught here and
    turned into a stderr message plus one of
    ``common.constants.deployment``'s exit codes, so this is safe to
    call directly from a ``if __name__ == "__main__":`` block or a
    packaging entry point without an outer try/except.
    """

    parser = arguments.build_parser()
    args = parser.parse_args(argv)

    if args.command == "logs":
        handler = _LOGS_COMMANDS[args.logs_command]
    else:
        handler = _COMMANDS[args.command]

    try:
        return handler(args)
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return DEPLOYMENT_CANCELLED
    except commands.CliUsageError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        if args.debug:
            traceback.print_exc()
        return DEPLOYMENT_ERROR
    except AquilaError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        if args.debug:
            traceback.print_exc()
        return DEPLOYMENT_ERROR
    except Exception as exc:  # noqa: BLE001 - top-level, must not crash uncaught
        print(f"Unexpected error: {exc}", file=sys.stderr)
        if args.debug:
            traceback.print_exc()
        else:
            print("Re-run with --debug for a full traceback.", file=sys.stderr)
        return DEPLOYMENT_ERROR


__all__ = ["main"]
