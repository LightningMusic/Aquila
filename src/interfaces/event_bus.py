"""
Project Aquila
=============

Event Bus Interface

Structural contract satisfied by ``common.events.bus.EventBus``. Lets
any subsystem depend on "something that publishes and delivers
Aquila events" without importing the concrete ``EventBus`` class
(NFR-MAIN-002) -- most usefully for the many optional
``event_bus: Optional[EventBus]`` constructor parameters throughout
this codebase (``config.manager.ConfigurationManager``,
``logging_engine.log_manager.LogManager``, and every future engine
that follows the same pattern), which only ever call ``publish()``.

This ``interfaces`` package as a whole is how NFR-MAIN-001 ("Project
Aquila shall utilize a modular software architecture") is realized in
code: every cross-cutting dependency a subsystem manager needs --
an event bus, a configuration provider, its own service lifecycle --
is expressed as a structural ``Protocol`` here rather than a concrete
import of another subsystem's class, so any one module can be
replaced or tested in isolation behind the same narrow contract.

Defined as a ``typing.Protocol``: ``EventBus`` lives in the
already-complete ``common`` package, which this project isn't
modifying, so a structural interface is the only way to document its
contract here without touching it.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol, runtime_checkable

from common.events.event import Event

EventHandler = Callable[[Event], None]


@runtime_checkable
class EventPublisher(Protocol):
    """
    The narrow "can publish an event" contract.

    This is the only capability most callers actually need --
    exactly what every optional ``event_bus`` constructor parameter
    in this codebase uses today -- so it is kept separate from
    :class:`EventBusProtocol` below rather than forcing every such
    caller to depend on the full subscription/history surface too.
    """

    def publish(self, event: Event) -> None:
        """Publish a single event."""
        ...


@runtime_checkable
class EventBusProtocol(EventPublisher, Protocol):
    """
    The full ``EventBus`` contract: publishing, subscription
    management, and bounded event history.
    """

    def publish_many(self, events: Iterable[Event]) -> None:
        """Publish multiple events."""
        ...

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register an event handler."""
        ...

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Remove an event handler."""
        ...

    def clear_subscribers(self) -> None:
        """Remove every registered subscriber."""
        ...

    @property
    def history(self) -> tuple[Event, ...]:
        """Immutable snapshot of published events."""
        ...

    def clear_history(self) -> None:
        """Remove all stored event history."""
        ...

    @property
    def history_size(self) -> int:
        """Current number of stored events."""
        ...

    @property
    def registered_events(self) -> tuple[str, ...]:
        """Return all registered event types."""
        ...

    @property
    def subscriber_count(self) -> int:
        """Total number of registered handlers."""
        ...

    def reset(self) -> None:
        """Reset the event bus to its initial state."""
        ...


__all__ = ["EventBusProtocol", "EventHandler", "EventPublisher"]
