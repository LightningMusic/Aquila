"""
Project Aquila
=============

Base event definitions for Project Aquila.

All events published through the Aquila Event Bus inherit from Event.
Events are immutable and carry metadata that allows them to be traced
throughout the lifetime of the application.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class Event:
    """
    Base class for all Aquila events.

    Attributes:
        event_id:
            Globally unique identifier for this event.

        event_type:
            Human-readable event type.

        timestamp:
            UTC timestamp indicating when the event was created.

        source:
            Name of the subsystem that published the event.

        payload:
            Event-specific data.
    """

    event_type: str
    source: str

    payload: dict[str, Any] = field(default_factory=dict)

    event_id: UUID = field(default_factory=uuid4)

    timestamp: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    @property
    def name(self) -> str:
        """
        Return the event type.

        Returns:
            Event type string.
        """

        return self.event_type

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the event into a serializable dictionary.

        Returns:
            Dictionary representation of the event.
        """

        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "payload": self.payload,
        }

    def __str__(self) -> str:
        """
        Return a readable string representation.

        Returns:
            Human-readable event description.
        """

        return (
            f"{self.event_type} "
            f"(id={self.event_id}, "
            f"source={self.source})"
        )


# =============================================================================
# Common Aquila Events
# =============================================================================


@dataclass(frozen=True, slots=True)
class ApplicationStartedEvent(Event):
    """
    Raised after Aquila finishes initialization.
    """

    def __init__(self) -> None:
        super().__init__(
            event_type="ApplicationStarted",
            source="core.application",
        )


@dataclass(frozen=True, slots=True)
class ApplicationStoppingEvent(Event):
    """
    Raised immediately before Aquila begins shutdown.
    """

    def __init__(self) -> None:
        super().__init__(
            event_type="ApplicationStopping",
            source="core.application",
        )


@dataclass(frozen=True, slots=True)
class ConfigurationLoadedEvent(Event):
    """
    Raised when configuration has been successfully loaded.
    """

    def __init__(
        self,
        configuration_name: str,
    ) -> None:

        super().__init__(
            event_type="ConfigurationLoaded",
            source="config.manager",
            payload={
                "configuration": configuration_name,
            },
        )


@dataclass(frozen=True, slots=True)
class ServiceRegisteredEvent(Event):
    """
    Raised when a service is registered with the service container.
    """

    def __init__(
        self,
        service_name: str,
    ) -> None:

        super().__init__(
            event_type="ServiceRegistered",
            source="common.service_container",
            payload={
                "service": service_name,
            },
        )


@dataclass(frozen=True, slots=True)
class DeploymentStartedEvent(Event):
    """
    Raised when a deployment workflow begins.
    """

    def __init__(
        self,
        node_name: str,
    ) -> None:

        super().__init__(
            event_type="DeploymentStarted",
            source="managers.deployment_manager",
            payload={
                "node": node_name,
            },
        )


@dataclass(frozen=True, slots=True)
class DeploymentCompletedEvent(Event):
    """
    Raised when a deployment finishes successfully.
    """

    def __init__(
        self,
        node_name: str,
    ) -> None:

        super().__init__(
            event_type="DeploymentCompleted",
            source="managers.deployment_manager",
            payload={
                "node": node_name,
            },
        )


@dataclass(frozen=True, slots=True)
class ErrorEvent(Event):
    """
    Generic event used to broadcast application errors.
    """

    def __init__(
        self,
        source: str,
        message: str,
    ) -> None:

        super().__init__(
            event_type="Error",
            source=source,
            payload={
                "message": message,
            },
        )