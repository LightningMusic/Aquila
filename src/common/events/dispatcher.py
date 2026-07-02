"""
Project Orion
=============

Event Dispatcher

Responsible for delivering events to subscribed handlers.

The dispatcher itself is intentionally lightweight and contains no
application logic. Its sole responsibility is invoking registered
event handlers safely.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from threading import RLock
from typing import Any

from common.events.event import Event

logger = logging.getLogger(__name__)

EventHandler = Callable[[Event], None]


class EventDispatcher:
    """
    Dispatches events to registered subscribers.

    This class is thread-safe.

    EventBus owns an instance of EventDispatcher and delegates all
    subscription and publishing operations to it.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._lock = RLock()

    # -------------------------------------------------------------------------
    # Subscription Management
    # -------------------------------------------------------------------------

    def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> None:
        """
        Register a handler for an event type.
        """

        with self._lock:

            if handler not in self._handlers[event_type]:
                self._handlers[event_type].append(handler)

                logger.debug(
                    "Subscribed '%s' to '%s'.",
                    handler.__name__,
                    event_type,
                )

    def unsubscribe(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> None:
        """
        Remove a handler from an event type.
        """

        with self._lock:

            handlers = self._handlers.get(event_type)

            if handlers is None:
                return

            if handler in handlers:
                handlers.remove(handler)

                logger.debug(
                    "Unsubscribed '%s' from '%s'.",
                    handler.__name__,
                    event_type,
                )

            if not handlers:
                del self._handlers[event_type]

    # -------------------------------------------------------------------------
    # Event Dispatching
    # -------------------------------------------------------------------------

    def dispatch(
        self,
        event: Event,
    ) -> None:
        """
        Dispatch an event to all subscribers.

        Exceptions raised by one subscriber do not prevent the remaining
        subscribers from receiving the event.
        """

        with self._lock:
            handlers = tuple(
                self._handlers.get(event.event_type, ())
            )

        for handler in handlers:

            try:
                handler(event)

            except Exception:

                logger.exception(
                    "Event handler '%s' failed while processing '%s'.",
                    handler.__name__,
                    event.event_type,
                )

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    def clear(self) -> None:
        """
        Remove all registered handlers.
        """

        with self._lock:
            self._handlers.clear()

    def subscriber_count(
        self,
        event_type: str | None = None,
    ) -> int:
        """
        Return the number of subscribers.

        If an event type is provided, returns the number of handlers
        registered for that event.

        Otherwise returns the total number of registered handlers.
        """

        with self._lock:

            if event_type is not None:
                return len(self._handlers.get(event_type, ()))

            return sum(
                len(handlers)
                for handlers in self._handlers.values()
            )

    def registered_events(self) -> tuple[str, ...]:
        """
        Return all registered event types.
        """

        with self._lock:
            return tuple(sorted(self._handlers.keys()))

    # -------------------------------------------------------------------------
    # Magic Methods
    # -------------------------------------------------------------------------

    def __len__(self) -> int:
        """
        Return the total number of registered handlers.
        """

        return self.subscriber_count()

    def __contains__(
        self,
        event_type: str,
    ) -> bool:
        """
        Determine whether an event type has subscribers.
        """

        return event_type in self._handlers

    def __repr__(self) -> str:
        """
        Developer-friendly representation.
        """

        return (
            f"{self.__class__.__name__}("
            f"registered_events={len(self._handlers)}, "
            f"handlers={len(self)})"
        )