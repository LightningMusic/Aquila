"""
Project Aquila
=============

CLI: Argument Parsing

Defines every ``aquila-cli`` subcommand's argument surface. Pure
argument definition -- no service bring-up, no workflow execution;
:mod:`cli.commands` is where a parsed ``argparse.Namespace`` actually
does something.

Design: a narrower, scripting/automation-focused front end, not full
Technician Console parity
--------------------------------------------------------------------
Confirmed with the user before building this package: unlike
``technician_console/`` (an interactive GUI presenting live dialogs
for every REQ-TC-012 decision point), ``cli/`` is deliberately scoped
as a leaner tool for scripted/unattended use -- every technician
decision a deployment workflow needs (which storage device(s), the
recovery decision, the REQ-PREP-004/005/006/007 confirmation sequence)
is answered from command-line flags supplied up front, not from
interactive terminal prompts. This keeps a scripted/scheduled
invocation of ``aquila-cli`` fully non-interactive by construction --
there is no prompt loop anywhere in this package.

GP-001 ("Safety Before Automation: Automation shall never perform
irreversible actions without explicit operator authorization") governs
the one place this design could go wrong: making destructive
confirmations *too* convenient to script would silently defeat the
principle the confirmations exist to enforce. This package resolves
that by making every REQ-PREP-004/005/006/007 confirmation flag
below required with no default value, and never adding a single
"--yes"/"--force-all" shortcut that supplies more than one of them at
once. A calling script must still spell out
``--confirm-target-device --confirm-proceed --erasure-acknowledgement
ERASE`` explicitly on every single invocation that reaches Preparation
-- an auditable, deliberate step baked into whatever automation
triggers it, not a silent default a forgotten/copied command line
could carry past a human's attention. This is a scripting tool for
*repeatable* deployments, not a way to make sanitization less
supervised than the Technician Console requires.

Recovery scope decision
--------------------------
``technician_console.dialogs.RecoveryDialog`` lets a technician browse
a volume's tree and hand-pick individual files. Rebuilding that same
interactive picker as a terminal UI would not be "narrower" -- it
would just be the same interactive-selection problem in a different
toolkit. This package instead supports exactly two non-interactive
recovery modes: skip (with the REQ-REC-016-required acknowledgement),
or recover *every* readable file from one or more entire discovered
volumes (``--recover-all``). Granular per-file selection remains a
Technician Console capability; documented here as a deliberate initial
scope decision (the same kind of documented scope decision this
project has already made elsewhere -- ``recovery/browser.py`` not
implementing browser-profile recovery, ``preparation/sanitizer.py``
never performing ATA/NVMe Secure Erase), not a gap.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from common.constants.deployment import FORCE_CONFIRMATION_PHRASE
from provisioning.boot_handoff import DEFAULT_MANIFEST_FILENAME

PROGRAM_NAME = "aquila-cli"


def _add_global_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--configs-dir",
        type=Path,
        default=None,
        help=(
            "Override the configuration directory (forwarded to "
            "ApplicationManager/ConfigurationManager). Defaults to "
            "this installation's ordinary configuration resolution."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help=(
            "Emit machine-readable JSON to stdout instead of "
            "human-readable text (progress lines still go to stderr "
            "either way)."
        ),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print full tracebacks for unexpected errors.",
    )


def _add_recovery_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group(
        "recovery (REQ-REC-004/005/006/016)",
        "Exactly one of --skip-recovery or --recover-all is required.",
    )
    group.add_argument(
        "--skip-recovery",
        action="store_true",
        help="Skip Recovery entirely -- requires --recovery-acknowledgement.",
    )
    group.add_argument(
        "--recovery-acknowledgement",
        metavar="TEXT",
        default=None,
        help=(
            "REQ-REC-016: a non-empty, explicit acknowledgement that "
            "no data will be recovered before this device is "
            "sanitized. Required with --skip-recovery."
        ),
    )
    group.add_argument(
        "--recover-all",
        action="store_true",
        help=(
            "Recover every readable file from the discovered volume(s) "
            "(or only --recover-volume, if given) to "
            "--recovery-destination before sanitizing."
        ),
    )
    group.add_argument(
        "--recovery-destination",
        type=Path,
        default=None,
        metavar="PATH",
        help="Destination directory for --recover-all. Required with it.",
    )
    group.add_argument(
        "--recover-volume",
        action="append",
        dest="recover_volumes",
        metavar="DEVICE_ID",
        default=None,
        help=(
            "Restrict --recover-all to this volume (for example 'D:'). "
            "May be given more than once. Defaults to every discovered "
            "volume."
        ),
    )


def _add_confirmation_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group(
        "sanitization confirmation (REQ-PREP-004/005/006/007, REQ-TC-012)",
        "Every flag below is required -- see this module's own "
        "docstring for why none of them may be defaulted or combined "
        "into a single shortcut flag.",
    )
    group.add_argument(
        "--confirm-target-device",
        action="store_true",
        required=True,
        help=(
            "REQ-PREP-005: confirm the device(s) named by "
            "--sanitize-device-serial are the correct target(s)."
        ),
    )
    group.add_argument(
        "--confirm-proceed",
        action="store_true",
        required=True,
        help="REQ-PREP-004: final, explicit approval to begin sanitization.",
    )
    group.add_argument(
        "--erasure-acknowledgement",
        metavar="PHRASE",
        required=True,
        help=(
            "REQ-PREP-006: must equal the configured force-confirmation "
            f"phrase exactly (case-sensitive) -- currently "
            f"'{FORCE_CONFIRMATION_PHRASE}'."
        ),
    )
    group.add_argument(
        "--additional-confirmations-count",
        type=int,
        default=0,
        metavar="N",
        help=(
            "REQ-PREP-007: how many additional site-configured "
            "confirmations (deployment.yaml's confirmation_count minus "
            "the 3 named ones above) to supply as affirmed. Must equal "
            "max(0, confirmation_count - 3) or the workflow refuses to "
            "start. Defaults to 0 (deployment.yaml's default "
            "confirmation_count of 3 needs no additional ones)."
        ),
    )


def _add_deployment_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--node-name",
        required=True,
        help="Identifies this deployment session in logs/reports.",
    )
    parser.add_argument(
        "--operator-identity",
        default=None,
        help="Recorded in the sanitization report (REQ-PREP-019), optional.",
    )
    parser.add_argument(
        "--sanitize-device-serial",
        action="append",
        dest="sanitize_device_serials",
        required=True,
        metavar="SERIAL",
        help=(
            "Serial number (exact match) of a storage device to "
            "sanitize (REQ-PREP-005). May be given more than once "
            "(REQ-PREP-013 permits sanitizing multiple devices in one "
            "session). Run 'aquila-cli inspect' first to list eligible "
            "devices and their serial numbers."
        ),
    )
    _add_recovery_arguments(parser)
    _add_confirmation_arguments(parser)


def _add_provisioning_profile_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("provisioning profile (REQ-PROV-015)")
    group.add_argument(
        "--provisioning-device-serial",
        default=None,
        metavar="SERIAL",
        help=(
            "Which --sanitize-device-serial Proxmox VE is installed "
            "to. Required when more than one --sanitize-device-serial "
            "is given; if exactly one is given, it is used by default."
        ),
    )
    group.add_argument(
        "--domain",
        default=None,
        help=(
            "Override deployment.yaml's provisioning_domain for this "
            "run. Defaults to the configured value; required (from "
            "either source) for Provisioning to start."
        ),
    )
    group.add_argument(
        "--mailto",
        default=None,
        help=(
            "Override deployment.yaml's provisioning_notification_email "
            "for this run. Defaults to the configured value; required "
            "(from either source) for Provisioning to start."
        ),
    )
    group.add_argument(
        "--root-password-env-var",
        default="AQUILA_NODE_ROOT_PASSWORD",
        help=(
            "Environment variable this process reads the node's root "
            "password from (REQ-SEC-008/009/010: never a command-line "
            "argument). Default: %(default)s."
        ),
    )
    group.add_argument(
        "--disk-list",
        default=None,
        metavar="DISK,DISK,...",
        help="Comma-separated explicit disk list, if not using --disk-filter-style selection.",
    )
    group.add_argument("--filesystem", default=None, metavar="FS")
    group.add_argument("--keyboard", default=None, metavar="LAYOUT")
    group.add_argument("--country", default=None, metavar="COUNTRY")
    group.add_argument("--timezone", default=None, metavar="TZ")
    group.add_argument(
        "--ip-assignment-method",
        default=None,
        choices=("dhcp", "static"),
        help="Default: dhcp (dataclass default).",
    )
    group.add_argument("--static-cidr", default=None, metavar="CIDR")
    group.add_argument("--static-gateway", default=None, metavar="ADDRESS")
    group.add_argument(
        "--static-dns",
        default=None,
        metavar="ADDR,ADDR,...",
        help="Comma-separated static DNS server list.",
    )
    group.add_argument("--reboot-on-error", action="store_true")
    group.add_argument("--subscription-key", default=None)
    group.add_argument(
        "--manifest-filename",
        default=DEFAULT_MANIFEST_FILENAME,
        help="Default: %(default)s.",
    )
    group.add_argument(
        "--no-trigger-handoff",
        action="store_true",
        help=(
            "Build the Phase Two answer file and node-identity record "
            "without actually rebooting into it -- useful for "
            "scripted dry runs/testing."
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description=(
            "Project Aquila -- headless, scriptable deployment front "
            "end over the same workflows.WorkflowManager the "
            "Technician Console drives (SRS Section 9.6/11.2). Every "
            "technician decision a workflow needs is supplied via "
            "flags, not interactive prompts -- see 'aquila-cli "
            "<command> --help'."
        ),
    )
    _add_global_arguments(parser)

    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Run a read-only hardware inspection (REQ-INS) and list eligible target devices.",
    )
    inspect_parser.add_argument("--node-name", default="cli-inspect")

    retire_parser = subparsers.add_parser(
        "retire",
        help="Run Workflow A: Device Retirement (SRS Appendix B).",
    )
    _add_deployment_arguments(retire_parser)

    provision_parser = subparsers.add_parser(
        "provision",
        help="Run Workflow B: Aquila Node Provisioning (SRS Appendix B).",
    )
    _add_deployment_arguments(provision_parser)
    _add_provisioning_profile_arguments(provision_parser)

    logs_parser = subparsers.add_parser(
        "logs", help="REQ-TC-008: list, show, or export deployment logs."
    )
    logs_subparsers = logs_parser.add_subparsers(dest="logs_command", required=True)

    logs_subparsers.add_parser("list", help="List available log files.")

    logs_show_parser = logs_subparsers.add_parser(
        "show", help="Print one log file's contents."
    )
    logs_show_parser.add_argument("name", help="Log file name, as shown by 'logs list'.")
    logs_show_parser.add_argument(
        "--tail",
        type=int,
        default=None,
        metavar="N",
        help="Print only the last N lines. Default: the whole file.",
    )

    logs_export_parser = logs_subparsers.add_parser(
        "export", help="Export every current log file (REQ-LOG-011)."
    )
    logs_export_parser.add_argument(
        "destination", type=Path, help="Destination directory."
    )

    return parser


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


__all__ = ["PROGRAM_NAME", "build_parser", "parse_args"]
