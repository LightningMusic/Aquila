"""
Project Aquila
=============

Technician Console: Deployment Media Layout

Re-exports :mod:`common.media` -- see that module's own docstring for
the detection strategy and the full "why this moved" explanation.

This logic originally lived here, as ``technician_console/media.py``'s
own implementation. It moved to ``common/media.py`` once ``cli/``
(built this session) needed the exact same "which real directory is
this?" detection for the exact same reason (both front ends drive the
same ``workflows.provisioning_manager.ProvisioningWorkflowStage``,
which needs the real ``phase1``/``phase2`` directories regardless of
which front end is running it) -- duplicating it a second time would
have repeated the same latent-drift-risk pattern already fixed
elsewhere in this project (``common/constants/filesystem.py``,
``common/constants/controller_api.py``,
``common/utils/formatting.format_bytes``). This module now re-exports
the shared implementation rather than defining its own, so
``technician_console/main_window.py`` (which imports ``media`` from
this package and calls ``media.detect_media_root()``/
``media.phase_two_directory()``/``media.report_directory()``, and
reads ``media.MEDIA_ROOT_ENV_VAR``) needed no changes at all.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from common.media import (
    MEDIA_ROOT_ENV_VAR,
    detect_media_root,
    phase_two_directory,
    report_directory,
)

__all__ = [
    "MEDIA_ROOT_ENV_VAR",
    "detect_media_root",
    "phase_two_directory",
    "report_directory",
]
