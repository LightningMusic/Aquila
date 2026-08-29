"""
Project Aquila
=============

Preparation Engine

Storage sanitization for Workflow A (Device Retirement) and the
sanitization stage of Workflow B (Aquila Node Provisioning) --
SRS Section 10.5, REQ-PREP-001 through REQ-PREP-024.

REQ-PREP-001/REQ-REC-017 is this package's governing constraint:
Preparation never begins until Recovery has completed successfully or
been intentionally, acknowledgedly skipped
(``recovery.report.RecoverySummary.is_complete``), and never performs
a destructive operation without the technician's explicit,
multi-step confirmation (``preparation.confirmations
.validate_confirmations``, REQ-PREP-004 through -007).

Public surface:

* :class:`preparation.confirmations.PreparationConfirmations` /
  :func:`preparation.confirmations.validate_confirmations` --
  REQ-PREP-004 through -007's confirmation sequence.
* :class:`preparation.sanitizer.DiskSanitizer` -- REQ-PREP-008 through
  -016's actual sanitization operation.
* :class:`preparation.verifier.SanitizationVerifier` -- REQ-PREP-017/
  018's independent post-sanitization verification.
* :class:`preparation.report.PreparationSummary` /
  :class:`preparation.report.SanitizationRecord` -- REQ-PREP-002/019's
  pre-flight and post-sanitization reporting.
* :class:`preparation.preparation_manager.PreparationManager` -- the
  orchestrator that ties the above together; the only entry point a
  caller (the Technician Console, or a CLI workflow) should normally
  need.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from .confirmations import PreparationConfirmations, validate_confirmations
from .preparation_manager import PreparationManager
from .report import PreparationSummary, SanitizationRecord
from .sanitizer import (
    DiskSanitizer,
    DiskSanitizerError,
    ProgressCallback,
    SanitizationExecutionResult,
    SanitizationProgress,
    WmiClearResult,
    WmiMethodCaller,
    resolve_disk_number,
)
from .verifier import (
    RawDeviceReader,
    SanitizationVerificationResult,
    SanitizationVerifier,
    VerificationOutcome,
)

__all__ = [
    "DiskSanitizer",
    "DiskSanitizerError",
    "PreparationConfirmations",
    "PreparationManager",
    "PreparationSummary",
    "ProgressCallback",
    "RawDeviceReader",
    "SanitizationExecutionResult",
    "SanitizationProgress",
    "SanitizationRecord",
    "SanitizationVerificationResult",
    "SanitizationVerifier",
    "VerificationOutcome",
    "WmiClearResult",
    "WmiMethodCaller",
    "resolve_disk_number",
    "validate_confirmations",
]
