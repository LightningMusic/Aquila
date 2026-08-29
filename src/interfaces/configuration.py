"""
Project Aquila
=============

Configuration Interface

Structural contract satisfied by ``config.manager.ConfigurationManager``
(SRS Section 9.8, REQ-CONF-001 through REQ-CONF-015). Lets any
subsystem depend on "something that provides validated Aquila
configuration" -- for type annotations, for a test double, or for a
future alternate implementation -- without importing the concrete
``ConfigurationManager`` class or the loader/schema machinery behind
it (NFR-MAIN-002).

Defined as a ``typing.Protocol``: ``ConfigurationManager`` already
exists as a complete, tested, ordinary class with no base class, so
structural typing lets it satisfy this contract exactly as written,
with no inheritance change.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from config.schemas.benchmark_schema import BenchmarkConfig
from config.schemas.cluster_schema import ClusterConfig
from config.schemas.controller_schema import ControllerConfig
from config.schemas.deployment_schema import DeploymentConfig
from config.schemas.logging_schema import LoggingConfig
from config.schemas.network_schema import NetworkConfig
from interfaces.service import Service


@runtime_checkable
class ConfigurationProvider(Service, Protocol):
    """
    Loads, validates, and hands back typed Aquila configuration.

    Extends :class:`interfaces.service.Service`: a configuration
    provider is itself a service with an initialize/shutdown
    lifecycle (``ConfigurationManager.initialize()`` loads and
    validates every registered configuration; its ``shutdown()`` is a
    documented no-op, since it holds no unmanaged resources between
    calls).
    """

    def load(self, name: str) -> Any:
        """Load, validate, and cache the named configuration."""
        ...

    def load_all(self) -> bool:
        """
        Load every registered configuration.

        Returns ``True`` only if every one of them loaded
        successfully (REQ-CONF-005).
        """
        ...

    def reload(self, name: str) -> Any:
        """Discard the cached configuration and load it again."""
        ...

    def validate_all(self) -> dict[str, str]:
        """
        Validate every registered configuration without raising.

        Returns a mapping of configuration name to error message for
        each configuration that failed; a successful one is absent.
        """
        ...

    def load_errors(self) -> dict[str, str]:
        """Return the most recent load error for each failed configuration."""
        ...

    def is_loaded(self, name: str) -> bool:
        """Return whether the named configuration is currently cached."""
        ...

    def save(self, name: str) -> None:
        """Persist the named configuration's current in-memory value."""
        ...

    def get_deployment_config(self) -> DeploymentConfig:
        """Return the deployment configuration, loading it if needed."""
        ...

    def get_network_config(self) -> NetworkConfig:
        """Return the network configuration, loading it if needed."""
        ...

    def get_cluster_config(self) -> ClusterConfig:
        """Return the cluster configuration, loading it if needed."""
        ...

    def get_logging_config(self) -> LoggingConfig:
        """Return the logging configuration, loading it if needed."""
        ...

    def get_benchmark_config(self) -> BenchmarkConfig:
        """Return the benchmark configuration, loading it if needed."""
        ...

    def get_controller_config(self) -> ControllerConfig:
        """Return the controller configuration, loading it if needed."""
        ...

    @staticmethod
    def resolve_secret(env_var_name: str) -> Optional[str]:
        """
        Resolve a secret value from the process environment
        (REQ-SEC-008, REQ-SEC-009).
        """
        ...

    def export_all(self) -> dict[str, Any]:
        """Return every loaded configuration as plain dictionaries."""
        ...


__all__ = ["ConfigurationProvider"]
