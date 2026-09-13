"""
Project Aquila
=============

Services

The Technician Console/CLI/workflow-facing service layer: thin,
``interfaces.service.Service``-conforming facades that compose one or
more lower-level engine managers (``config.manager.
ConfigurationManager``, ``logging_engine.log_manager.LogManager``,
``networking.network_manager.NetworkManager``,
``bootstrap.controller_client.DeploymentControllerClient``) into a
single API surface shaped around what ``workflows/`` and
``technician_console/`` actually need, rather than requiring either
of those layers to depend on every engine's internals directly
(GP-004: one clearly defined responsibility per module).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from services.benchmark_service import BenchmarkHistory, BenchmarkService
from services.configuration_service import ConfigurationService, SessionConfigBundle
from services.deployment_service import (
    DeploymentService,
    NodeHandshakeResult,
    generate_node_identifier,
)
from services.inventory_service import (
    InventoryService,
    InventorySearchQuery,
    InventorySearchResults,
)
from services.logging_service import LogFileInfo, LoggingService
from services.network_service import NetworkService, NetworkValidationResult

__all__ = [
    "BenchmarkHistory",
    "BenchmarkService",
    "ConfigurationService",
    "DeploymentService",
    "InventoryService",
    "InventorySearchQuery",
    "InventorySearchResults",
    "LogFileInfo",
    "LoggingService",
    "NetworkService",
    "NetworkValidationResult",
    "NodeHandshakeResult",
    "SessionConfigBundle",
    "generate_node_identifier",
]
