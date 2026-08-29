"""
Project Aquila
=============

Recovery Verification

Implements REQ-REC-012 (verify each copied file after transfer) and
REQ-REC-024 (report storage read errors separately from copy
verification failures).

Reuses ``common.utils.hashing`` (``sha256_file``/``verify_hash``)
rather than a second, competing hashing implementation -- exactly the
same convention ``common.utils.hashing``'s own docstring documents
("Recovery validation" is explicitly listed among its supported uses).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from common.constants.logging import RECOVERY_LOGGER
from common.utils.hashing import sha256_file, verify_hash

logger = logging.getLogger(RECOVERY_LOGGER)


class VerificationOutcome(Enum):
    """
    The result of verifying one copied file.

    Deliberately more granular than a plain pass/fail boolean:
    REQ-REC-024 requires a *storage read error* (the source or
    destination could not even be read for hashing) to be reported
    separately from a genuine *verification failure* (both were read,
    but their hashes disagree -- meaning the copy itself is corrupt).
    """

    VERIFIED = auto()
    MISMATCH = auto()
    SOURCE_UNREADABLE = auto()
    DESTINATION_UNREADABLE = auto()


@dataclass(slots=True, frozen=True)
class VerifiedFileResult:
    source_path: Path
    destination_path: Path
    outcome: VerificationOutcome
    source_hash: str | None
    destination_hash: str | None
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.outcome is VerificationOutcome.VERIFIED


class RecoveryVerifier:
    """Verifies copied files against their source via SHA-256 hashing."""

    def verify_file(
        self, source_path: Path, destination_path: Path
    ) -> VerifiedFileResult:
        try:
            source_hash = sha256_file(source_path)
        except OSError as exc:
            logger.warning(
                "Recovery verification could not read source %s: %s",
                source_path,
                exc,
            )
            return VerifiedFileResult(
                source_path=source_path,
                destination_path=destination_path,
                outcome=VerificationOutcome.SOURCE_UNREADABLE,
                source_hash=None,
                destination_hash=None,
                detail=str(exc),
            )

        try:
            destination_hash = sha256_file(destination_path)
        except OSError as exc:
            logger.warning(
                "Recovery verification could not read destination %s: %s",
                destination_path,
                exc,
            )
            return VerifiedFileResult(
                source_path=source_path,
                destination_path=destination_path,
                outcome=VerificationOutcome.DESTINATION_UNREADABLE,
                source_hash=source_hash,
                destination_hash=None,
                detail=str(exc),
            )

        if verify_hash(destination_hash, source_hash):
            return VerifiedFileResult(
                source_path=source_path,
                destination_path=destination_path,
                outcome=VerificationOutcome.VERIFIED,
                source_hash=source_hash,
                destination_hash=destination_hash,
            )

        logger.warning(
            "Recovery verification MISMATCH for %s -> %s",
            source_path,
            destination_path,
        )
        return VerifiedFileResult(
            source_path=source_path,
            destination_path=destination_path,
            outcome=VerificationOutcome.MISMATCH,
            source_hash=source_hash,
            destination_hash=destination_hash,
            detail="Source and destination hashes do not match.",
        )

    def verify_many(
        self, pairs: list[tuple[Path, Path]]
    ) -> list[VerifiedFileResult]:
        return [
            self.verify_file(source_path, destination_path)
            for source_path, destination_path in pairs
        ]


__all__ = ["RecoveryVerifier", "VerificationOutcome", "VerifiedFileResult"]
