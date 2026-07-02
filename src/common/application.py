"""
Project Orion
=============

Application

Defines the root application object for Project Orion.

The Application class owns the application's core infrastructure,
including the dependency injection container, configuration,
logging, and event bus.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from common.events.bus import EventBus
from common.service_container import ServiceContainer
from common.version import (
    APPLICATION_NAME,
    APPLICATION_VERSION,
    APPLICATION
)


class Application:
    """
    Root application object.

    Every major Orion subsystem is created from here.
    """

    def __init__(self) -> None:
        self._container = ServiceContainer()

        self._initialized = False
        self._running = False

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """
        Initialize the application.
        """

        if self._initialized:
            return

        #
        # Core Services
        #

        event_bus = EventBus()

        self._container.register_instance(
            EventBus,
            event_bus,
        )

        #
        # Future services
        #
        # ConfigurationManager
        # LogManager
        # WorkflowManager
        # DeploymentManager
        #

        self._initialized = True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Start the application.
        """

        if not self._initialized:
            self.initialize()

        self._running = True

    def stop(self) -> None:
        """
        Shut down the application.
        """

        self._running = False

    def run(self) -> None:
        """
        Run the application.

        This is the primary entry point used by main.py.
        """

        self.start()

        #
        # TODO:
        #
        # Start Technician Console
        # OR
        # Execute CLI Workflow
        #

    # ------------------------------------------------------------------
    # Service Resolution
    # ------------------------------------------------------------------

    @property
    def services(self) -> ServiceContainer:
        """
        Return the application's service container.
        """

        return self._container

    @property
    def event_bus(self) -> EventBus:
        """
        Return the global EventBus.
        """

        return self._container.resolve(EventBus)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Information
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return APPLICATION_NAME

    @property
    def version(self) -> str:
        return APPLICATION_VERSION

    # ------------------------------------------------------------------
    # Magic Methods
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"name='{self.name}', "
            f"version='{self.version}', "
            f"initialized={self.initialized}, "
            f"running={self.running})"
        )