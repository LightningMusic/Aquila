"""
Project Aquila
=============

Configuration Manager

Central entry point for the Configuration Engine (SRS Section 9.8,
REQ-CONF-001 through REQ-CONF-015). Loads, validates, and distributes
every Aquila configuration file, and is the only component in the
project that should construct a schema object directly from a file on
disk -- every other subsystem asks this manager for its configuration
rather than reading ``configs/*.yaml`` itself.

Responsibilities
-----------------
* Load configuration during application startup (REQ-CONF-001).
* Validate configuration schema before deployment begins, and refuse
  to hand back an invalid configuration (REQ-CONF-004, REQ-CONF-005).
* Provide validated configuration data to authorized subsystems
  (REQ-CONF-015) through typed accessors -- callers get a
  ``DeploymentConfig``/``NetworkConfig``/etc. dataclass, never a raw
  dictionary.
* Support saving configuration changes back to disk.
* Resolve secret values (cluster join tokens, Deployment Controller
  credentials) from environment variables rather than configuration
  files (REQ-SEC-008, REQ-SEC-009).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Generic, Optional, TypeVar

from common.exceptions.configuration import (
    ConfigurationError,
    ConfigurationValidationError,
)
from common.paths import (
    BENCHMARK_CONFIG,
    CLUSTER_CONFIG,
    CONTROLLER_CONFIG,
    DEPLOYMENT_CONFIG,
    LOGGING_CONFIG,
    NETWORK_CONFIG,
)
from config.loaders.json_loader import JSONConfigLoader
from config.loaders.yaml_loader import YAMLConfigLoader
from config.schemas.benchmark_schema import BenchmarkConfig
from config.schemas.cluster_schema import ClusterConfig
from config.schemas.controller_schema import ControllerConfig
from config.schemas.deployment_schema import DeploymentConfig
from config.schemas.logging_schema import LoggingConfig
from config.schemas.network_schema import NetworkConfig

if TYPE_CHECKING:
    # Imported only for type annotations below. Nothing in this module
    # constructs an EventBus -- the caller owns it and passes one in
    # -- so no runtime import is needed, and this stays resolvable
    # even in a context where ``common.events`` is unavailable.
    from common.events.bus import EventBus

try:
    from common.events.types.configuration import (
        ConfigurationLoadedEvent,
        ConfigurationLoadFailedEvent,
        ConfigurationLoadingEvent,
        ConfigurationSavedEvent,
        ConfigurationValidatedEvent,
        ConfigurationValidationFailedEvent,
        ConfigurationValidationStartedEvent,
    )
except ImportError:  # pragma: no cover - event system is optional

    class _NullEvent:
        """Fallback event used only if ``common.events`` cannot be
        imported. ``_publish`` never actually delivers one of these:
        it only builds an event when an ``EventBus`` was supplied,
        and supplying one requires ``common.events`` to have imported
        successfully in the first place. These stand-ins exist purely
        so the names below are always bound, which keeps this module
        importable -- and honestly typed -- even in that situation.
        """

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

    ConfigurationLoadedEvent = _NullEvent
    ConfigurationLoadFailedEvent = _NullEvent
    ConfigurationLoadingEvent = _NullEvent
    ConfigurationSavedEvent = _NullEvent
    ConfigurationValidatedEvent = _NullEvent
    ConfigurationValidationFailedEvent = _NullEvent
    ConfigurationValidationStartedEvent = _NullEvent

logger = logging.getLogger(__name__)

_SchemaT = TypeVar("_SchemaT")


@dataclass(frozen=True, slots=True)
class _ConfigEntry(Generic[_SchemaT]):
    """Registry entry describing one named configuration."""

    filename: str
    schema: type[_SchemaT]


#: Every configuration Aquila ships, keyed by the name callers use
#: with ``load()``/``get()``/``save()``. Extending Aquila with a new
#: configuration file means adding one entry here and one
#: ``config.schemas`` module -- nothing else in this manager changes
#: (SRS GP-007, Expandability).
_REGISTRY: dict[str, _ConfigEntry[Any]] = {
    "deployment": _ConfigEntry(DEPLOYMENT_CONFIG.name, DeploymentConfig),
    "network": _ConfigEntry(NETWORK_CONFIG.name, NetworkConfig),
    "cluster": _ConfigEntry(CLUSTER_CONFIG.name, ClusterConfig),
    "logging": _ConfigEntry(LOGGING_CONFIG.name, LoggingConfig),
    "benchmark": _ConfigEntry(BENCHMARK_CONFIG.name, BenchmarkConfig),
    "controller": _ConfigEntry(CONTROLLER_CONFIG.name, ControllerConfig),
}


class ConfigurationManager:
    """
    Loads, validates, and distributes Aquila configuration.

    A single instance is normally created during application startup
    (SRS Section 10.14, ``core.startup``) and registered with the
    ``ServiceContainer`` for other subsystems to resolve.
    """

    def __init__(
        self,
        configs_dir: Optional[Path] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        from common.paths import CONFIGS_DIR

        self._configs_dir = configs_dir or CONFIGS_DIR
        self._event_bus: Optional[EventBus] = event_bus

        self._yaml_loader = YAMLConfigLoader()
        self._json_loader = JSONConfigLoader()

        self._configs: dict[str, Any] = {}
        self._load_errors: dict[str, str] = {}
        self._initialized = False

    # ------------------------------------------------------------------
    # Service lifecycle (interfaces.service.Service)
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """
        Load and validate every registered configuration.

        Service-lifecycle entry point (``interfaces.service.Service``)
        so ``core.startup`` can bring every registered Aquila service
        up uniformly, alongside ``LogManager.initialize()`` and every
        future engine that follows the same contract. Equivalent to
        calling ``load_all()`` directly; per-configuration success or
        failure is still available afterward through ``load_errors()``
        and ``validate_all()`` exactly as before -- this method itself
        never raises for an individual configuration's failure, only
        records it (matching ``load_all()``'s own behavior).

        Idempotent: calling this again re-loads every configuration
        from disk, exactly like calling ``load_all()`` again would.
        """

        self.load_all()
        self._initialized = True

    def shutdown(self) -> None:
        """
        Release any resources this manager holds.

        A documented no-op: each loader (``YAMLConfigLoader``,
        ``JSONConfigLoader``) opens, reads or writes, and closes its
        file synchronously within a single call -- nothing is kept
        open between calls, so there is nothing to release here.
        Defined so ``ConfigurationManager`` satisfies the same
        ``Service`` lifecycle every other Aquila service does.
        """

        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        """Whether ``initialize()`` has completed."""

        return self._initialized

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self, name: str) -> Any:
        """
        Load, validate, and cache the named configuration.

        Returns the validated schema instance (for example a
        ``DeploymentConfig`` when ``name == "deployment"``).

        A missing or empty configuration file is not an error --
        Aquila ships every ``configs/*.yaml`` file able to be loaded
        as an empty document, in which case every field falls back to
        its documented default (GP-003, Configuration Over
        Hardcoding).

        Raises:
            KeyError:
                If ``name`` is not a registered configuration.
            ConfigurationError:
                If the file exists but cannot be parsed, or its
                contents fail schema validation.
        """

        entry = self._entry(name)
        path = self._configs_dir / entry.filename

        self._publish(
            lambda: ConfigurationLoadingEvent(configuration_name=name)
        )

        try:
            raw = self._read(path)
            config = entry.schema.from_dict(raw)
        except ConfigurationError as exc:
            self._load_errors[name] = str(exc)
            self._publish(
                lambda: ConfigurationLoadFailedEvent(
                    configuration_name=name,
                    reason=str(exc),
                )
            )
            raise
        except Exception as exc:
            self._load_errors[name] = str(exc)
            self._publish(
                lambda: ConfigurationLoadFailedEvent(
                    configuration_name=name,
                    reason=str(exc),
                )
            )
            raise ConfigurationValidationError(
                f"Configuration '{name}' failed validation: {exc}"
            ) from exc

        self._configs[name] = config
        self._load_errors.pop(name, None)

        self._publish(
            lambda: ConfigurationLoadedEvent(configuration_name=name)
        )

        logger.info("Loaded configuration '%s' from %s", name, path)

        return config

    def load_all(self) -> bool:
        """
        Load every registered configuration.

        Unlike ``load()``, a single configuration's failure does not
        stop the others from loading -- every configuration is
        attempted so that ``load_errors()`` can report a complete
        picture in one pass. Returns ``True`` only if every
        configuration loaded successfully (REQ-CONF-005: invalid
        configuration must prevent deployment from beginning, which
        callers enforce by checking this return value before
        proceeding).
        """

        all_succeeded = True

        for name in _REGISTRY:
            try:
                self.load(name)
            except Exception:
                all_succeeded = False
                logger.error(
                    "Configuration '%s' failed to load: %s",
                    name,
                    self._load_errors.get(name, "unknown error"),
                )

        return all_succeeded

    def reload(self, name: str) -> Any:
        """Discard the cached configuration and load it again."""

        self._configs.pop(name, None)

        return self.load(name)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_all(self) -> dict[str, str]:
        """
        Validate every registered configuration without raising.

        Returns a mapping of configuration name to error message for
        each configuration that failed to load or validate; a
        successful configuration is absent from the result. Intended
        for the Technician Console (REQ-TC-010/REQ-TC-011: warnings
        and errors are displayed, not raised as crashes) to present a
        pre-flight summary before a deployment workflow begins.
        """

        self._publish(
            lambda: ConfigurationValidationStartedEvent(
                configuration_name="*"
            )
        )

        errors: dict[str, str] = {}

        for name in _REGISTRY:
            try:
                self.load(name)
            except Exception as exc:
                errors[name] = str(exc)

        if errors:
            self._publish(
                lambda: ConfigurationValidationFailedEvent(
                    configuration_name="*",
                    reason="; ".join(
                        f"{name}: {message}"
                        for name, message in sorted(errors.items())
                    ),
                )
            )
        else:
            self._publish(
                lambda: ConfigurationValidatedEvent(
                    configuration_name="*"
                )
            )

        return errors

    def load_errors(self) -> dict[str, str]:
        """Return the most recent load error for each failed configuration."""

        return dict(self._load_errors)

    def is_loaded(self, name: str) -> bool:
        """Return whether the named configuration is currently cached."""

        return name in self._configs

    # ------------------------------------------------------------------
    # Saving
    # ------------------------------------------------------------------

    def save(self, name: str) -> None:
        """
        Persist the named configuration's current in-memory value.

        Raises:
            KeyError:
                If ``name`` is not a registered configuration, or has
                not been loaded.
            ConfigurationError:
                If the file cannot be written.
        """

        entry = self._entry(name)

        if name not in self._configs:
            raise KeyError(
                f"Configuration '{name}' has not been loaded; call "
                f"load('{name}') before save('{name}')."
            )

        path = self._configs_dir / entry.filename
        data = self._configs[name].to_dict()

        self._yaml_loader.save(path, data)

        self._publish(
            lambda: ConfigurationSavedEvent(configuration_name=name)
        )

        logger.info("Saved configuration '%s' to %s", name, path)

    # ------------------------------------------------------------------
    # Typed accessors (REQ-CONF-015)
    # ------------------------------------------------------------------

    def get_deployment_config(self) -> DeploymentConfig:
        """Return the deployment configuration, loading it if needed."""

        return self._get_or_load("deployment", DeploymentConfig)

    def get_network_config(self) -> NetworkConfig:
        """Return the network configuration, loading it if needed."""

        return self._get_or_load("network", NetworkConfig)

    def get_cluster_config(self) -> ClusterConfig:
        """Return the cluster configuration, loading it if needed."""

        return self._get_or_load("cluster", ClusterConfig)

    def get_logging_config(self) -> LoggingConfig:
        """Return the logging configuration, loading it if needed."""

        return self._get_or_load("logging", LoggingConfig)

    def get_benchmark_config(self) -> BenchmarkConfig:
        """Return the benchmark configuration, loading it if needed."""

        return self._get_or_load("benchmark", BenchmarkConfig)

    def get_controller_config(self) -> ControllerConfig:
        """Return the controller configuration, loading it if needed."""

        return self._get_or_load("controller", ControllerConfig)

    # ------------------------------------------------------------------
    # Secrets
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_secret(env_var_name: str) -> Optional[str]:
        """
        Resolve a secret value from the process environment.

        Configuration files store only the *name* of the environment
        variable holding a secret (see
        ``ClusterConfig.join_token_env_var`` and
        ``ControllerConfig.authentication_token_env_var``); this
        method performs the actual lookup at the point of use so a
        secret is never copied into a loaded configuration object,
        a report, or a log line derived from one.
        """

        value = os.environ.get(env_var_name)

        return value if value else None

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_all(self) -> dict[str, Any]:
        """
        Return every loaded configuration as plain dictionaries.

        Configurations that have not been loaded yet are loaded first.
        Values resolved through ``resolve_secret`` are never included
        -- only the environment variable *names* are, matching what
        is stored on disk.
        """

        return {
            name: self._get_or_load(name, entry.schema).to_dict()
            for name, entry in _REGISTRY.items()
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _entry(name: str) -> _ConfigEntry[Any]:
        try:
            return _REGISTRY[name]
        except KeyError as exc:
            raise KeyError(
                f"'{name}' is not a registered configuration. "
                f"Known configurations: "
                f"{', '.join(sorted(_REGISTRY))}."
            ) from exc

    def _read(self, path: Path) -> dict[str, Any]:
        if path.suffix.lower() == ".json":
            return self._json_loader.load(path)

        return self._yaml_loader.load(path)

    def _get_or_load(self, name: str, schema: type[_SchemaT]) -> _SchemaT:
        if name not in self._configs:
            self.load(name)

        return self._configs[name]

    def _publish(self, build_event: Callable[[], Any]) -> None:
        if self._event_bus is None:
            return

        try:
            self._event_bus.publish(build_event())
        except Exception:  # pragma: no cover - event delivery is best-effort
            logger.debug(
                "Failed to publish configuration event.", exc_info=True
            )

    # ------------------------------------------------------------------
    # Magic methods
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"loaded={sorted(self._configs)}, "
            f"errors={sorted(self._load_errors)})"
        )


__all__ = ["ConfigurationManager"]
