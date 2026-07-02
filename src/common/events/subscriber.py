"""
Project Orion
=============

Subscriber Base Class

Defines the abstract interface for all event subscribers within
Project Orion.

Subscribers receive events published through the EventBus.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from common.events.event import Event


class EventSubscriber(ABC):
    """
    Base class for all event subscribers.

    Classes interested in receiving events should inherit from
    EventSubscriber and implement the handle_event() method.
    """

    @abstractmethod
    def handle_event(
        self,
        event: Event,
    ) -> None:
        """
        Handle a published event.

        Parameters
        ----------
        event:
            The event being delivered.
        """
        raise NotImplementedError

    def __call__(
        self,
        event: Event,
    ) -> None:
        """
        Allow subscribers to be used as callable handlers.

        This lets an EventSubscriber instance be registered directly
        with the EventDispatcher.
        """

        self.handle_event(event)

    @property
    def name(self) -> str:
        """
        Return the subscriber's class name.
        """

        return self.__class__.__name__

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"