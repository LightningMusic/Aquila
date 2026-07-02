"""
Project Orion
=============

Event Bus

Central publish/subscribe manager for Project Orion.

The EventBus provides a single application-wide interface for
publishing events and managing event subscriptions. It delegates
event delivery to the EventDispatcher while maintaining a bounded
history of recently published events.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable

from common.events.dispatcher import EventDispatcher
from common.events.event import Event

EventHandler = Callable[[Event], None]


class EventBus:
    """
    Central event bus for Project Orion.

    Responsibilities
    ----------------
    • Publish events.
    • Register subscribers.
    • Remove subscribers.
    • Maintain recent event history.
    • Delegate event delivery to EventDispatcher.

    This class should be instantiated once for the lifetime of the
    application.
    """

    DEFAULT_HISTORY_SIZE = 1000

    def __init__(
        self,
        history_size: int = DEFAULT_HISTORY_SIZE,
    ) -> None:
        self._dispatcher = EventDispatcher()

        self._history: deque[Event] = deque(
            maxlen=history_size,
        )

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish(
        self,
        event: Event,
    ) -> None:
        """
        Publish a single event.
        """

        self._history.append(event)

        self._dispatcher.dispatch(event)

    def publish_many(
        self,
        events: Iterable[Event],
    ) -> None:
        """
        Publish multiple events.
        """

        for event in events:
            self.publish(event)

    # ------------------------------------------------------------------
    # Subscription Management
    # ------------------------------------------------------------------

    def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> None:
        """
        Register an event handler.
        """

        self._dispatcher.subscribe(
            event_type,
            handler,
        )

    def unsubscribe(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> None:
        """
        Remove an event handler.
        """

        self._dispatcher.unsubscribe(
            event_type,
            handler,
        )

    def clear_subscribers(self) -> None:
        """
        Remove every registered subscriber.
        """

        self._dispatcher.clear()

    # ------------------------------------------------------------------
    # Event History
    # ------------------------------------------------------------------

    @property
    def history(self) -> tuple[Event, ...]:
        """
        Immutable snapshot of published events.
        """

        return tuple(self._history)

    def clear_history(self) -> None:
        """
        Remove all stored event history.
        """

        self._history.clear()

    @property
    def history_size(self) -> int:
        """
        Current number of stored events.
        """

        return len(self._history)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def registered_events(self) -> tuple[str, ...]:
        """
        Return all registered event types.
        """

        return self._dispatcher.registered_events()

    @property
    def subscriber_count(self) -> int:
        """
        Total number of registered handlers.
        """

        return len(self._dispatcher)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """
        Reset the EventBus to its initial state.
        """

        self.clear_history()
        self.clear_subscribers()

    # ------------------------------------------------------------------
    # Magic Methods
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        """
        Number of events currently stored.
        """

        return len(self._history)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"history={len(self._history)}, "
            f"subscribers={self.subscriber_count})"
        )