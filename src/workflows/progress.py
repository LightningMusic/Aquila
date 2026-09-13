"""
Project Aquila
=============

Workflow Progress Reporting

Shared stage-transition progress type used by every
``workflows/*_manager.py`` adapter (REQ-TC-009: "display deployment
progress"; REQ-TC-010/011: "warnings/errors displayed separately from
informational messages"). Distinct from each engine's own
fine-grained ``ProgressCallback`` (``recovery.copier.ProgressCallback``,
``preparation.sanitizer.ProgressCallback``) -- those report
byte-level/file-level progress *within* one operation; a
``WorkflowStageEvent`` reports stage-level transitions *across* a
whole deployment workflow, which is what
``workflows.deployment_manager`` (and, eventually, a Technician
Console/CLI) actually needs to render REQ-TC-009's overall progress
display. Every ``workflows/*_manager.py`` adapter forwards an
engine's own fine-grained callback straight through unchanged (see
each module's own ``progress_callback`` passthrough parameter) rather
than wrapping it, so no detail is lost translating one shape into the
other -- ``WorkflowStageEvent`` only ever describes stage boundaries
and outcomes, never individual files or bytes.

New file added to ``workflows/`` beyond the pre-planned stub set
(``__init__.py``, ``application_manager.py``, ``bootstrap_manager.py``,
``deployment_manager.py``, ``inspection_manager.py``,
``preparation_manager.py``, ``provisioning_manager.py``,
``recovery_manager.py``, ``workflow_manager.py``). Justified the same
way ``common/constants/controller_api.py`` was in the previous
session: five sibling stage-adapter modules each need this exact
type, and duplicating it five times would be the same kind of
latent-drift risk that fix eliminated.

Severity levels
----------------
* ``"info"``: a routine stage transition (started/completed).
* ``"warning"``: REQ-TC-010 -- a non-fatal condition worth the
  technician's attention (for example, Bootstrap's
  battery-threshold-unsupported "record the limitation and continue"
  outcome).
* ``"error"``: REQ-TC-011 -- the workflow halted at this stage.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

#: The only severities a ``WorkflowStageEvent`` may carry, matching
#: REQ-TC-010/011's three-way distinction (informational messages,
#: warnings, errors).
SEVERITIES: tuple[str, ...] = ("info", "warning", "error")


@dataclass(slots=True, frozen=True)
class WorkflowStageEvent:
    """
    One stage-level transition or outcome within a deployment
    workflow.

    ``stage`` is a short, stable identifier (for example
    ``"inspection"``, ``"preparation.confirmation"``,
    ``"provisioning.handshake"``) rather than a free-form label, so a
    future Technician Console can key UI state off it directly instead
    of parsing ``message``.
    """

    stage: str
    message: str
    severity: str = "info"

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(
                f"WorkflowStageEvent.severity must be one of "
                f"{SEVERITIES}, got {self.severity!r}."
            )


#: Invoked once per stage-level transition. Never invoked for
#: fine-grained, within-operation progress -- see the module docstring.
WorkflowProgressCallback = Callable[[WorkflowStageEvent], None]


def emit(
    callback: Optional[WorkflowProgressCallback],
    stage: str,
    message: str,
    *,
    severity: str = "info",
    logger: Optional[logging.Logger] = None,
) -> None:
    """
    Report one stage-transition event, best-effort.

    Never lets a failing callback (for example, a Console UI update
    that raises) interrupt the underlying deployment workflow --
    exactly the same discipline every existing engine manager's own
    ``EventBus``-publishing ``_publish()`` helper already follows, for
    the same reason (event delivery is inherently best-effort).
    """

    if logger is not None:
        log_fn = {
            "info": logger.info,
            "warning": logger.warning,
            "error": logger.error,
        }[severity]
        log_fn("[%s] %s", stage, message)

    if callback is None:
        return

    try:
        callback(WorkflowStageEvent(stage=stage, message=message, severity=severity))
    except Exception:  # pragma: no cover - callback delivery is best-effort
        if logger is not None:
            logger.debug(
                "Workflow progress callback raised for stage '%s'.",
                stage,
                exc_info=True,
            )


__all__ = ["SEVERITIES", "WorkflowProgressCallback", "WorkflowStageEvent", "emit"]
