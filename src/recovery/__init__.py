"""
Project Aquila
=============

Recovery Engine

Implements SRS Section 10.4 / REQ-REC-001 through REQ-REC-026:
optional, technician-supervised recovery of user data from a target
system's storage before Preparation's destructive sanitization begins
(SRS Appendix B, Workflow A).

Public API:

- ``VolumeBrowser`` / ``RecoveryVolume`` / ``RecoveryEntry``
  (``browser.py``) -- read-only volume discovery and filesystem
  browsing (REQ-REC-002 through -005).
- ``RecoveryCopier`` / ``CopySelectionResult`` / ``CopyFailure`` /
  ``CopyProgress`` (``copier.py``) -- technician-selected file/
  directory copying (REQ-REC-006 through -011/018-020/023/025).
- ``RecoveryVerifier`` / ``VerifiedFileResult`` /
  ``VerificationOutcome`` (``verifier.py``) -- post-copy verification
  (REQ-REC-012/024).
- ``RecoverySummary`` (``report.py``) -- the complete outcome of one
  recovery run (REQ-REC-014/015/026).
- ``RecoveryManager`` (``recovery_manager.py``) -- the orchestrator
  tying all of the above together (REQ-REC-001/016/017/021/022).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from .browser import RecoveryEntry, RecoveryVolume, VolumeBrowser
from .copier import (
    CopyFailure,
    CopyProgress,
    CopySelectionResult,
    ProgressCallback,
    RecoveryCopier,
)
from .recovery_manager import RecoveryManager
from .report import RecoverySummary
from .verifier import RecoveryVerifier, VerificationOutcome, VerifiedFileResult

__all__ = [
    "CopyFailure",
    "CopyProgress",
    "CopySelectionResult",
    "ProgressCallback",
    "RecoveryCopier",
    "RecoveryEntry",
    "RecoveryManager",
    "RecoverySummary",
    "RecoveryVerifier",
    "RecoveryVolume",
    "VerificationOutcome",
    "VerifiedFileResult",
    "VolumeBrowser",
]
