"""
Project Orion
=============

Configuration Exceptions

Defines configuration-related exceptions used
throughout Project Orion.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from common.exceptions.application import OrionError


class ConfigurationError(OrionError):
    """
    Base class for all configuration-related exceptions.
    """


class ConfigurationInitializationError(ConfigurationError):
    """
    Raised when the configuration system cannot be
    initialized.
    """


class ConfigurationLoadError(ConfigurationError):
    """
    Raised when a configuration file cannot be loaded.
    """


class ConfigurationSaveError(ConfigurationError):
    """
    Raised when a configuration file cannot be saved.
    """


class ConfigurationFileNotFoundError(ConfigurationError):
    """
    Raised when a required configuration file
    does not exist.
    """


class ConfigurationDirectoryNotFoundError(ConfigurationError):
    """
    Raised when the configuration directory
    cannot be located.
    """


class ConfigurationParseError(ConfigurationError):
    """
    Raised when a configuration file contains
    invalid syntax.
    """


class ConfigurationValidationError(ConfigurationError):
    """
    Raised when configuration values fail
    validation.
    """


class ConfigurationSchemaError(ConfigurationError):
    """
    Raised when a configuration schema
    is invalid.
    """


class ConfigurationKeyError(ConfigurationError):
    """
    Raised when a required configuration
    key is missing.
    """


class ConfigurationValueError(ConfigurationError):
    """
    Raised when a configuration value
    is invalid.
    """


class ConfigurationTypeError(ConfigurationError):
    """
    Raised when a configuration value
    has an unexpected type.
    """


class ConfigurationPermissionError(ConfigurationError):
    """
    Raised when Orion cannot access a
    configuration file due to permissions.
    """


class ConfigurationReadOnlyError(ConfigurationError):
    """
    Raised when attempting to modify
    a read-only configuration.
    """


class ConfigurationVersionError(ConfigurationError):
    """
    Raised when a configuration file
    version is unsupported.
    """


class ConfigurationMigrationError(ConfigurationError):
    """
    Raised when migrating a configuration
    file fails.
    """


class ConfigurationEnvironmentError(ConfigurationError):
    """
    Raised when environment variables required
    by the configuration are missing or invalid.
    """


class ConfigurationOverrideError(ConfigurationError):
    """
    Raised when applying configuration
    overrides fails.
    """


class ConfigurationSerializationError(ConfigurationError):
    """
    Raised when configuration data
    cannot be serialized.
    """


class ConfigurationDeserializationError(ConfigurationError):
    """
    Raised when configuration data
    cannot be deserialized.
    """


__all__ = [
    "ConfigurationDeserializationError",
    "ConfigurationDirectoryNotFoundError",
    "ConfigurationEnvironmentError",
    "ConfigurationError",
    "ConfigurationFileNotFoundError",
    "ConfigurationInitializationError",
    "ConfigurationKeyError",
    "ConfigurationLoadError",
    "ConfigurationMigrationError",
    "ConfigurationOverrideError",
    "ConfigurationParseError",
    "ConfigurationPermissionError",
    "ConfigurationReadOnlyError",
    "ConfigurationSaveError",
    "ConfigurationSchemaError",
    "ConfigurationSerializationError",
    "ConfigurationTypeError",
    "ConfigurationValidationError",
    "ConfigurationValueError",
    "ConfigurationVersionError",
]