"""
Project Aquila
=============

Network Service

The workflow-facing facade over the Networking Engine
(``networking.network_manager.NetworkManager``, REQ-NET-001 through
REQ-NET-014). Reduces Workflow B's "Network Validation" stage (SRS
Appendix B) to a single call: ``establish()`` runs the full
connectivity-establishment sequence and, when it fails, one recovery
attempt, returning a workflow-friendly result rather than requiring
``workflows.provisioning_manager`` (not yet built) to know
``NetworkManager``'s internal establish/recover distinction itself
(GP-004: one clearly defined responsibility per module).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional

from common.constants.deployment import (
    NETWORK_RETRY_COUNT,
    NETWORK_RETRY_DELAY_SECONDS,
)
from common.constants.logging import NETWORK_LOGGER
from config.schemas.cluster_schema import ClusterConfig
from config.schemas.controller_schema import ControllerConfig
from config.schemas.network_schema import NetworkConfig
from networking.network_manager import NetworkDiagnostics, NetworkManager

if TYPE_CHECKING:
    from common.events.bus import EventBus

logger = logging.getLogger(NETWORK_LOGGER)


@dataclass(slots=True, frozen=True)
class NetworkValidationResult:
    """Workflow B's Network Validation stage outcome (Appendix B)."""

    succeeded: bool
    diagnostics: NetworkDiagnostics
    recovered: bool = False

    @property
    def status_message(self) -> str:
        return self.diagnostics.status_message


class NetworkService:
    """
    Facade over ``NetworkManager`` for the deployment workflow layer.
    Satisfies ``interfaces.service.Service``.
    """

    def __init__(
        self,
        event_bus: Optional["EventBus"] = None,
        *,
        network_manager: Optional[NetworkManager] = None,
    ) -> None:
        self._network_manager = network_manager or NetworkManager(event_bus)
        self._initialized = False

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        self._network_manager.initialize()
        self._initialized = True

    def shutdown(self) -> None:
        self._network_manager.shutdown()
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def last_diagnostics(self) -> Optional[NetworkDiagnostics]:
        return self._network_manager.last_diagnostics

    # ------------------------------------------------------------------
    # Workflow B: Network Validation
    # ------------------------------------------------------------------

    def establish(
        self,
        network_config: NetworkConfig,
        *,
        controller_config: ControllerConfig,
        cluster_config: Optional[ClusterConfig] = None,
        max_recovery_attempts: int = 1,
        retry_count: int = NETWORK_RETRY_COUNT,
        retry_delay_seconds: float = NETWORK_RETRY_DELAY_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> NetworkValidationResult:
        """
        Establish connectivity (REQ-NET-001 through -010), attempting
        recovery once (REQ-NET-011) if the first pass fails, and
        return a single pass/fail result for the calling workflow
        stage.
        """

        diagnostics = self._network_manager.establish_connectivity(
            network_config,
            controller_config=controller_config,
            cluster_config=cluster_config,
            retry_count=retry_count,
            retry_delay_seconds=retry_delay_seconds,
            sleep=sleep,
        )

        if diagnostics.overall_ok:
            return NetworkValidationResult(succeeded=True, diagnostics=diagnostics)

        if max_recovery_attempts <= 0:
            return NetworkValidationResult(succeeded=False, diagnostics=diagnostics)

        recovered_diagnostics = self._network_manager.attempt_recovery(
            network_config,
            controller_config=controller_config,
            cluster_config=cluster_config,
            max_attempts=max_recovery_attempts,
            retry_count=retry_count,
            retry_delay_seconds=retry_delay_seconds,
            sleep=sleep,
        )

        return NetworkValidationResult(
            succeeded=recovered_diagnostics.overall_ok,
            diagnostics=recovered_diagnostics,
            recovered=recovered_diagnostics.overall_ok,
        )


__all__ = ["NetworkService", "NetworkValidationResult"]
