"""
Project Orion
=============

Configuration events.

Defines events related to configuration loading, validation,
saving, and runtime configuration changes.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from common.enums import EventSource, EventType
from common.events.event import Event


# =============================================================================
# Configuration Loading Events
# =============================================================================


class ConfigurationLoadingEvent(Event):
    """
    Published when configuration loading begins.
    """

    def __init__(self, configuration_name: str) -> None:
        super().__init__(
            event_type=EventType.CONFIGURATION_LOADING.name,
            source=EventSource.CONFIG_MANAGER.name,
            payload={
                "configuration_name": configuration_name,
            },
        )


class ConfigurationLoadedEvent(Event):
    """
    Published when a configuration has been loaded successfully.
    """

    def __init__(self, configuration_name: str) -> None:
        super().__init__(
            event_type=EventType.CONFIGURATION_LOADED.name,
            source=EventSource.CONFIG_MANAGER.name,
            payload={
                "configuration_name": configuration_name,
            },
        )


class ConfigurationLoadFailedEvent(Event):
    """
    Published when configuration loading fails.
    """

    def __init__(
        self,
        configuration_name: str,
        reason: str,
    ) -> None:
        super().__init__(
            event_type=EventType.CONFIGURATION_LOAD_FAILED.name,
            source=EventSource.CONFIG_MANAGER.name,
            payload={
                "configuration_name": configuration_name,
                "reason": reason,
            },
        )


# =============================================================================
# Configuration Validation Events
# =============================================================================


class ConfigurationValidationStartedEvent(Event):
    """
    Published before configuration validation begins.
    """

    def __init__(self, configuration_name: str) -> None:
        super().__init__(
            event_type=EventType.CONFIGURATION_VALIDATION_STARTED.name,
            source=EventSource.CONFIG_MANAGER.name,
            payload={
                "configuration_name": configuration_name,
            },
        )


class ConfigurationValidatedEvent(Event):
    """
    Published after configuration validation succeeds.
    """

    def __init__(self, configuration_name: str) -> None:
        super().__init__(
            event_type=EventType.CONFIGURATION_VALIDATED.name,
            source=EventSource.CONFIG_MANAGER.name,
            payload={
                "configuration_name": configuration_name,
            },
        )


class ConfigurationValidationFailedEvent(Event):
    """
    Published when configuration validation fails.
    """

    def __init__(
        self,
        configuration_name: str,
        reason: str,
    ) -> None:
        super().__init__(
            event_type=EventType.CONFIGURATION_VALIDATION_FAILED.name,
            source=EventSource.CONFIG_MANAGER.name,
            payload={
                "configuration_name": configuration_name,
                "reason": reason,
            },
        )


# =============================================================================
# Runtime Configuration Events
# =============================================================================


class ConfigurationChangedEvent(Event):
    """
    Published when a configuration value changes.
    """

    def __init__(
        self,
        configuration_name: str,
        key: str,
        old_value: object,
        new_value: object,
    ) -> None:
        super().__init__(
            event_type=EventType.CONFIGURATION_CHANGED.name,
            source=EventSource.CONFIG_MANAGER.name,
            payload={
                "configuration_name": configuration_name,
                "key": key,
                "old_value": old_value,
                "new_value": new_value,
            },
        )


class ConfigurationSavedEvent(Event):
    """
    Published after a configuration has been saved.
    """

    def __init__(self, configuration_name: str) -> None:
        super().__init__(
            event_type=EventType.CONFIGURATION_SAVED.name,
            source=EventSource.CONFIG_MANAGER.name,
            payload={
                "configuration_name": configuration_name,
            },
        )