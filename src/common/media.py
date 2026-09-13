"""
Project Aquila
=============

Deployment Media Layout

Answers one question no earlier module in this codebase answered:
"where, on the real filesystem, is the deployment media the currently
running Aquila front end (Technician Console or CLI) was launched
from?"

This is a genuinely different question from ``common.paths``'s
``PROJECT_ROOT``. ``common/paths.py``'s own docstring is explicit that
it defines "the Project Aquila directory structure" for the
*development repository* -- ``PROJECT_ROOT`` is computed by walking up
from ``common/paths.py``'s own location, which in a developer's clone
or a CI checkout is the git repository root. SRS Section 9.3/9.4 draw
a deliberate line between that repository and the deployment USB: "The
repository shall **not** depend upon the deployment USB for
development" / "The deployment USB shall be generated from the
repository during the release process" / "The USB shall contain only
the components necessary to execute deployment workflows" -- meaning
the media's own ``src/`` tree is a *build output*, laid out however
the not-yet-built Build System (SRS Section 9.15/10.14) decides to lay
it out, not a guaranteed mirror of the repository's own directory
names. Reusing ``PROJECT_ROOT`` here would silently conflate "the repo
this code was built from" with "the media this code is running from"
-- two different filesystems in production, that only happen to
coincide in a developer's own checkout.

What ``workflows.provisioning_manager.ProvisioningWorkflowStage.run()``
actually needs (see ``provisioning.provisioning_manager
.ProvisioningManager.run()``'s own docstring for
``phase_two_directory``) is the real, on-disk ``phase2`` directory
sitting at the deployment media's root -- confirmed against
``common.constants.deployment.USB_PHASE_TWO_DIRECTORY``/
``USB_REPORT_DIRECTORY`` (a bare directory *name*, not a path).

Moved here from ``technician_console/media.py`` (this session, while
building ``cli/``)
-----------------------------------------------------------------------
This logic originally lived in ``technician_console/media.py``,
documented at the time as "the first subsystem where 'which real
directory is this?' can no longer be deferred to a caller." That
reasoning still holds -- it just no longer implies *this specific
package* is the right home: ``cli/`` (built this session) needs the
exact same detection for the exact same reason (Provisioning must
write its rendered answer file and node-identity record to the real,
on-disk ``phase2``/``phase1`` directories, regardless of which front
end is driving the workflow). Having ``cli/`` import this from
``technician_console/`` would make a headless subsystem depend on a
Tkinter-based one for a capability that never touched Tkinter in the
first place -- exactly the kind of unnecessary cross-subsystem
coupling SRS Section 9.1/GP-004 (Modular Design: "No subsystem shall
assume internal implementation details of another subsystem") warns
against, and the same latent-drift-risk category already fixed
elsewhere in this project (``common/constants/filesystem.py``,
``common/constants/controller_api.py``,
``common/utils/formatting.format_bytes``) once a second consumer
appeared. Moved to ``common/`` -- genuinely shared, front-end-agnostic
infrastructure -- with zero behavior change.
``technician_console/media.py`` now re-exports from here instead of
defining its own copy, so ``technician_console/main_window.py`` needed
no changes.

Detection strategy
--------------------
1. ``AQUILA_MEDIA_ROOT`` environment variable, if set: used verbatim.
   This is both the standard escape hatch this project already uses
   everywhere a path needs to be overridable for tests (``Configuration
   Manager(configs_dir=...)``, ``ApplicationManager(media_root=...)``)
   and the documented answer for whatever the Build System's eventual
   real media layout turns out to be, if it differs from the heuristic
   below.
2. Otherwise, walk upward from this module's own on-disk location
   looking for the first ancestor directory that has *both* a
   ``phase1`` and a ``phase2`` subdirectory -- SRS Appendix A/Section
   9.4's documented top-level media layout. This succeeds unmodified
   for the most likely real Build System layout (the repository's
   ``src/`` tree, including this module, copied under
   ``<media_root>/phase1/src/...``, alongside a sibling ``phase2/``),
   without this module hardcoding an assumption about exactly how deep
   any particular caller's package sits within ``phase1/``.

Neither guesses a value: if both fail, :func:`detect_media_root` raises
``AquilaEnvironmentError`` rather than fabricating a path -- staging
Provisioning's answer file or node-identity record to a wrong location
is exactly the class of silent, hard-to-diagnose failure GP-005
(Observability) and GP-010 (Documentation First) exist to prevent, so
failing loudly here is the only safe behavior.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from common.constants.deployment import (
    USB_PHASE_ONE_DIRECTORY,
    USB_PHASE_TWO_DIRECTORY,
    USB_REPORT_DIRECTORY,
)
from common.exceptions.application import AquilaEnvironmentError

#: The environment variable ``detect_media_root()`` checks first --
#: see the module docstring.
MEDIA_ROOT_ENV_VAR = "AQUILA_MEDIA_ROOT"

#: How far to walk up from this module's own location before giving
#: up -- generous enough for any plausible ``phase1/<package>/<module>``
#: nesting depth without walking indefinitely up an unrelated
#: filesystem tree if the heuristic simply doesn't apply.
_MAX_WALK_UP = 12


def _has_media_layout(candidate: Path) -> bool:
    return (candidate / USB_PHASE_ONE_DIRECTORY).is_dir() and (
        candidate / USB_PHASE_TWO_DIRECTORY
    ).is_dir()


def detect_media_root(start: Optional[Path] = None) -> Path:
    """
    Resolve the deployment media's root directory -- see the module
    docstring for the detection strategy.

    Args:
        start: Where to begin the upward walk when the environment
            variable is unset. Defaults to this module's own resolved
            location. Exposed for tests, which run from a synthetic
            directory tree rather than this module's real location.

    Raises:
        AquilaEnvironmentError: If ``AQUILA_MEDIA_ROOT`` is unset and
            no ancestor of ``start`` has both a ``phase1`` and a
            ``phase2`` subdirectory.
    """

    override = os.environ.get(MEDIA_ROOT_ENV_VAR)
    if override:
        candidate = Path(override).resolve()
        if not _has_media_layout(candidate):
            raise AquilaEnvironmentError(
                f"{MEDIA_ROOT_ENV_VAR}={override!r} does not contain "
                f"both a '{USB_PHASE_ONE_DIRECTORY}' and a "
                f"'{USB_PHASE_TWO_DIRECTORY}' subdirectory -- refusing "
                "to guess the deployment media layout."
            )
        return candidate

    current = (start or Path(__file__)).resolve()
    for _ in range(_MAX_WALK_UP):
        current = current.parent
        if _has_media_layout(current):
            return current
        if current.parent == current:
            break

    raise AquilaEnvironmentError(
        "Could not detect the deployment media root: no ancestor "
        f"directory of {(start or Path(__file__)).resolve()} contains "
        f"both '{USB_PHASE_ONE_DIRECTORY}' and "
        f"'{USB_PHASE_TWO_DIRECTORY}' subdirectories, and "
        f"{MEDIA_ROOT_ENV_VAR} is not set. This is expected when "
        "running outside real deployment media (for example, from a "
        f"development checkout) -- set {MEDIA_ROOT_ENV_VAR} to point "
        "at a directory with the expected layout."
    )


def phase_two_directory(media_root: Path) -> Path:
    """``<media_root>/phase2`` -- REQ-PROV-017's boot-media directory."""

    return media_root / USB_PHASE_TWO_DIRECTORY


def report_directory(media_root: Path) -> Path:
    """
    ``<media_root>/phase1/<USB_REPORT_DIRECTORY>`` -- where a Phase One
    front end (Technician Console or CLI) writes its own session
    artifacts (the rendered answer file's sibling ``NodeIdentityRecord``,
    and REQ-TC-013's deployment summary), kept under ``phase1`` rather
    than at the media root directly since these are Phase One-produced
    records, distinct from the ``phase2`` boot-media payload itself.
    """

    return media_root / USB_PHASE_ONE_DIRECTORY / USB_REPORT_DIRECTORY


__all__ = [
    "MEDIA_ROOT_ENV_VAR",
    "detect_media_root",
    "phase_two_directory",
    "report_directory",
]
