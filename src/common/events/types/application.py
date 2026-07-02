"""
Project Orion
=============

Application lifecycle events.

This module defines events related to the Orion application's
startup, initialization, execution, and shutdown.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass

from common.events.event import Event


# =============================================================================
# Application Lifecycle
# =============================================================================


@dataclass(frozen=True, slots=True)
class ApplicationStartingEvent(Event):
    """
    Published immediately before Orion begins initialization.
    """

    def __init__(self) -> None:
        super().__init__(
            event_type="ApplicationStarting",
            source="core.application",
        )


@dataclass(frozen=True, slots=True)
class ApplicationStartedEvent(Event):
    """
    Published after Orion has successfully initialized.
    """

    def __init__(self) -> None:
        super().__init__(
            event_type="ApplicationStarted",
            source="core.application",
        )


@dataclass(frozen=True, slots=True)
class ApplicationStoppingEvent(Event):
    """
    Published immediately before shutdown begins.
    """

    def __init__(self) -> None:
        super().__init__(
            event_type="ApplicationStopping",
            source="core.application",
        )


@dataclass(frozen=True, slots=True)
class ApplicationStoppedEvent(Event):
    """
    Published after Orion has completed shutdown.
    """

    def __init__(self) -> None:
        super().__init__(
            event_type="ApplicationStopped",
            source="core.application",
        )


# =============================================================================
# Initialization Events
# =============================================================================


@dataclass(frozen=True, slots=True)
class InitializationStartedEvent(Event):
    """
    Published when the initialization sequence begins.
    """

    def __init__(self) -> None:
        super().__init__(
            event_type="InitializationStarted",
            source="core.startup",
        )


@dataclass(frozen=True, slots=True)
class InitializationCompletedEvent(Event):
    """
    Published when the initialization sequence completes.
    """

    def __init__(self) -> None:
        super().__init__(
            event_type="InitializationCompleted",
            source="core.startup",
        )


@dataclass(frozen=True, slots=True)
class InitializationFailedEvent(Event):
    """
    Published when application initialization fails.

    Args:
        reason:
            Description of the failure.
    """

    def __init__(
        self,
        reason: str,
    ) -> None:
        super().__init__(
            event_type="InitializationFailed",
            source="core.startup",
            payload={
                "reason": reason,
            },
        )


# =============================================================================
# Shutdown Events
# =============================================================================


@dataclass(frozen=True, slots=True)
class ShutdownStartedEvent(Event):
    """
    Published when shutdown begins.
    """

    def __init__(self) -> None:
        super().__init__(
            event_type="ShutdownStarted",
            source="core.shutdown",
        )


@dataclass(frozen=True, slots=True)
class ShutdownCompletedEvent(Event):
    """
    Published after shutdown has completed.
    """

    def __init__(self) -> None:
        super().__init__(
            event_type="ShutdownCompleted",
            source="core.shutdown",
        )


@dataclass(frozen=True, slots=True)
class ShutdownFailedEvent(Event):
    """
    Published when shutdown fails.

    Args:
        reason:
            Description of the failure.
    """

    def __init__(
        self,
        reason: str,
    ) -> None:
        super().__init__(
            event_type="ShutdownFailed",
            source="core.shutdown",
            payload={
                "reason": reason,
            },
        )