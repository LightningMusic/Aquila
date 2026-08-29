"""
Project Aquila
=============

Preparation Confirmations

Implements REQ-PREP-004 (technician shall explicitly approve storage
sanitization before execution), REQ-PREP-005 (technician shall confirm
the selected target storage device), REQ-PREP-006 (technician shall
acknowledge that all selected storage devices will be permanently
erased), and REQ-PREP-007 (multiple independent confirmation prompts,
configurable, no fewer than three by default).

Design
-------
REQ-PREP-006's acknowledgement is not a checkbox: it must be typed as
the exact configured phrase (``common.constants.deployment
.FORCE_CONFIRMATION_PHRASE``, ``"ERASE"`` by default) -- a deliberate,
low-probability-of-accident action, the same principle used by many
destructive-by-design tools (``git push --force``, cloud consoles that
ask you to type a resource's name before deleting it). This is always
required, regardless of the configured ``confirmation_count`` --
REQ-PREP-006 states it unconditionally, unlike REQ-PREP-007's count,
which only governs *how many* prompts surround it.

``PreparationConfirmations.additional_confirmations`` exists to let a
site configure *more* than the three concrete, named confirmations
here (REQ-PREP-007: "The exact number and presentation of
confirmations shall be configurable") without inventing meaning for
what a fourth or fifth prompt represents -- the Technician Console
(not yet built) decides what those extra prompts ask the technician,
this module only requires that every one of them was answered
affirmatively.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field

from common.exceptions.deployment import DeploymentValidationError


@dataclass(slots=True, frozen=True)
class PreparationConfirmations:
    """
    The technician's actual responses to the pre-sanitization
    confirmation sequence.
    """

    #: REQ-PREP-005: the technician confirmed the displayed target
    #: storage device (REQ-PREP-002's summary) is the correct one.
    target_device_confirmed: bool = False

    #: REQ-PREP-006: must equal the configured force-confirmation
    #: phrase exactly (case-sensitive) to count.
    erasure_acknowledgement_phrase: str = ""

    #: REQ-PREP-004: the final, explicit "proceed" approval.
    final_approval: bool = False

    #: Additional site-configured confirmations (REQ-PREP-007), each
    #: required to be True.
    additional_confirmations: tuple[bool, ...] = field(default_factory=tuple)

    @property
    def total_confirmed_count(self) -> int:
        """
        How many of the confirmations here were actually given, for
        comparison against the configured ``confirmation_count``
        (REQ-PREP-007).
        """

        count = 0
        if self.target_device_confirmed:
            count += 1
        if self.erasure_acknowledgement_phrase:
            count += 1
        if self.final_approval:
            count += 1
        count += sum(1 for confirmed in self.additional_confirmations if confirmed)
        return count


def validate_confirmations(
    confirmations: PreparationConfirmations,
    *,
    required_count: int,
    force_phrase: str,
) -> None:
    """
    Validate a technician's confirmation responses before sanitization
    may begin.

    Raises:
        DeploymentValidationError: Naming the specific missing or
            incorrect confirmation, if any requirement is not met.
            Every check runs (rather than stopping at the first
            failure) so the technician sees every outstanding item at
            once instead of fixing them one at a time.
    """

    problems: list[str] = []

    if not confirmations.target_device_confirmed:
        problems.append(
            "REQ-PREP-005: the technician must confirm the selected "
            "target storage device."
        )

    if confirmations.erasure_acknowledgement_phrase != force_phrase:
        problems.append(
            "REQ-PREP-006: the technician must acknowledge permanent "
            f"erasure by typing the exact phrase '{force_phrase}'."
        )

    if not confirmations.final_approval:
        problems.append(
            "REQ-PREP-004: the technician must give final, explicit "
            "approval before sanitization begins."
        )

    if any(not confirmed for confirmed in confirmations.additional_confirmations):
        problems.append(
            "One or more additional configured confirmations were not "
            "given."
        )

    if confirmations.total_confirmed_count < required_count:
        problems.append(
            "REQ-PREP-007: at least "
            f"{required_count} confirmation(s) are required; only "
            f"{confirmations.total_confirmed_count} were given."
        )

    if problems:
        raise DeploymentValidationError(
            "Sanitization cannot begin -- outstanding confirmations: "
            + " | ".join(problems)
        )


__all__ = ["PreparationConfirmations", "validate_confirmations"]
