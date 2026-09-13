"""
Project Aquila
=============

Configuration Service

The workflow-facing facade over ``config.manager.ConfigurationManager``.
A deployment workflow stage typically needs two to four different
configuration objects at once (Provisioning alone needs
``DeploymentConfig``, ``ControllerConfig``, and indirectly
``ClusterConfig``/``NetworkConfig`` for Network Validation) --
``SessionConfigBundle`` loads and validates every configuration a
deployment session can need in one call, so ``workflows/`` and
``technician_console/`` pull from one object instead of repeating
``ConfigurationManager.get_*_config()`` calls at every stage.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from config.manager import ConfigurationManager
from config.schemas.benchmark_schema import BenchmarkConfig
from config.schemas.cluster_schema import ClusterConfig
from config.schemas.controller_schema import ControllerConfig
from config.schemas.deployment_schema import DeploymentConfig
from config.schemas.logging_schema import LoggingConfig
from config.schemas.network_schema import NetworkConfig

if TYPE_CHECKING:
    from common.events.bus import EventBus


@dataclass(slots=True, frozen=True)
class SessionConfigBundle:
    """Every configuration a deployment session (Workflow A or B) can need."""

    deployment: DeploymentConfig
    network: NetworkConfig
    cluster: ClusterConfig
    controller: ControllerConfig
    benchmark: BenchmarkConfig
    logging: LoggingConfig


class ConfigurationService:
    """
    Facade over ``ConfigurationManager`` for the deployment workflow
    layer. Satisfies ``interfaces.service.Service`` by delegating
    lifecycle to the ``ConfigurationManager`` it wraps.
    """

    def __init__(
        self,
        *,
        configuration_manager: Optional[ConfigurationManager] = None,
        configs_dir: Optional[Path] = None,
        event_bus: Optional["EventBus"] = None,
    ) -> None:
        self._manager = configuration_manager or ConfigurationManager(
            configs_dir, event_bus
        )

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        self._manager.initialize()

    def shutdown(self) -> None:
        self._manager.shutdown()

    @property
    def is_initialized(self) -> bool:
        return self._manager.is_initialized

    @property
    def manager(self) -> ConfigurationManager:
        """The underlying manager, for a caller that needs ``save()``/
        ``reload()``/``resolve_secret()`` directly rather than through
        this facade's bundled convenience."""

        return self._manager

    # ------------------------------------------------------------------
    # REQ-TC's pre-flight configuration summary (REQ-CONF-015)
    # ------------------------------------------------------------------

    def load_session_bundle(self) -> SessionConfigBundle:
        """
        Load (or return already-loaded) every configuration a
        deployment session needs, as one bundle.

        Raises:
            ConfigurationError: If any configuration fails to load or
                validate (REQ-CONF-005) -- propagated rather than
                silently degraded, since a workflow must not begin
                against a configuration it cannot trust. A caller
                wanting a REQ-TC-010/011-style pre-flight warning
                instead of an exception should call
                ``self.manager.validate_all()`` first.
        """

        return SessionConfigBundle(
            deployment=self._manager.get_deployment_config(),
            network=self._manager.get_network_config(),
            cluster=self._manager.get_cluster_config(),
            controller=self._manager.get_controller_config(),
            benchmark=self._manager.get_benchmark_config(),
            logging=self._manager.get_logging_config(),
        )


__all__ = ["ConfigurationService", "SessionConfigBundle"]
