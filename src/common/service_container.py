"""
Project Orion
=============

Service Container

Provides a lightweight dependency injection container for Project Orion.

The ServiceContainer owns singleton services used throughout the
application and provides a central mechanism for service registration
and retrieval.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ServiceContainer:
    """
    Lightweight dependency injection container.

    Services may be registered as either:

    • Singleton instances
    • Factory functions

    Factory functions are invoked only once and their resulting object
    is cached as a singleton.
    """

    def __init__(self) -> None:
        self._instances: dict[type[Any], Any] = {}
        self._factories: dict[type[Any], Callable[[], Any]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_instance(
        self,
        service_type: type[Any],
        instance: Any,
    ) -> None:
        """
        Register an existing singleton instance.
        """

        self._instances[service_type] = instance

    def register_factory(
        self,
        service_type: type[Any],
        factory: Callable[[], Any],
    ) -> None:
        """
        Register a lazy factory.

        The factory is executed the first time the service is requested.
        """

        self._factories[service_type] = factory

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(
        self,
        service_type: type[Any],
    ) -> Any:
        """
        Resolve a service.

        Returns the singleton instance associated with the requested
        service type.

        Raises:
            KeyError:
                If the service has not been registered.
        """

        # Existing singleton
        if service_type in self._instances:
            return self._instances[service_type]

        # Lazy singleton
        if service_type in self._factories:

            instance = self._factories[service_type]()

            self._instances[service_type] = instance

            return instance

        raise KeyError(
            f"Service '{service_type.__name__}' has not been registered."
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def contains(
        self,
        service_type: type[Any],
    ) -> bool:
        """
        Determine whether a service has been registered.
        """

        return (
            service_type in self._instances
            or service_type in self._factories
        )

    # ------------------------------------------------------------------
    # Removal
    # ------------------------------------------------------------------

    def unregister(
        self,
        service_type: type[Any],
    ) -> None:
        """
        Remove a registered service.
        """

        self._instances.pop(service_type, None)
        self._factories.pop(service_type, None)

    def clear(self) -> None:
        """
        Remove every registered service.
        """

        self._instances.clear()
        self._factories.clear()

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @property
    def registered_services(self) -> tuple[str, ...]:
        """
        Return the names of all registered service types.
        """

        services = {
            *self._instances.keys(),
            *self._factories.keys(),
        }

        return tuple(
            sorted(service.__name__ for service in services)
        )

    @property
    def count(self) -> int:
        """
        Return the number of registered service types.
        """

        return len(
            {
                *self._instances.keys(),
                *self._factories.keys(),
            }
        )

    # ------------------------------------------------------------------
    # Magic Methods
    # ------------------------------------------------------------------

    def __contains__(
        self,
        service_type: type[Any],
    ) -> bool:
        return self.contains(service_type)

    def __len__(self) -> int:
        return self.count

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"services={self.count})"
        )