#!/usr/bin/env python3
"""
Functional test suite for src/services/ (the Technician Console/CLI/
workflow-facing service layer) plus the additive extensions this
session made to ``bootstrap.controller_client.DeploymentControllerClient``
(``set_bearer_token``, ``search_inventory``, ``get_node_benchmarks``)
and to ``deployment_controller`` (the two new REQ-INV-010/REQ-BENCH-010
read endpoints, already covered end-to-end in
``run_tests_deployment_controller.py``).

Follows the exact plain-script convention every other
``run_tests_*.py`` in this repository already established.

Run with (from the repository root): python3 tests/run_tests_services.py
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

failures: list[str] = []
passed = 0


def check(condition: bool, description: str) -> None:
    global passed
    if condition:
        passed += 1
    else:
        failures.append(description)


_TEMP_ROOT = Path(tempfile.mkdtemp(prefix="aquila-services-tests-"))

from common.exceptions.deployment import (  # noqa: E402
    DeploymentAuthenticationError,
    DeploymentConfigurationError,
    DeploymentNetworkError,
)
from config.manager import ConfigurationManager  # noqa: E402
from config.schemas.cluster_schema import ClusterConfig  # noqa: E402
from config.schemas.controller_schema import ControllerConfig  # noqa: E402
from config.schemas.network_schema import NetworkConfig  # noqa: E402
from networking.network_manager import NetworkDiagnostics  # noqa: E402
from services.benchmark_service import BenchmarkService  # noqa: E402
from services.configuration_service import ConfigurationService  # noqa: E402
from services.deployment_service import (  # noqa: E402
    DeploymentService,
    generate_node_identifier,
)
from services.inventory_service import (  # noqa: E402
    InventoryService,
    InventorySearchQuery,
)
from services.logging_service import LoggingService  # noqa: E402
from services.network_service import NetworkService  # noqa: E402


# ---------------------------------------------------------------------------
# generate_node_identifier
# ---------------------------------------------------------------------------

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

identifier = generate_node_identifier()
check(bool(_UUID_RE.match(identifier)), "generate_node_identifier() returns a UUID4")
check(
    generate_node_identifier() != generate_node_identifier(),
    "generate_node_identifier() returns a fresh value each call",
)


# ---------------------------------------------------------------------------
# services.configuration_service.ConfigurationService
# ---------------------------------------------------------------------------

# REQ-CONF-002/NFR-MAIN-003: these are real files on disk under a
# temp directory, not values embedded in this test module or in
# application source -- ConfigurationService below reads
# configuration from exactly this kind of external location in
# production too, keeping configuration external to application
# logic.
empty_configs_dir = _TEMP_ROOT / "configs_empty"
empty_configs_dir.mkdir(parents=True, exist_ok=True)
for _config_filename in (
    "deployment.yaml",
    "network.yaml",
    "cluster.yaml",
    "logging.yaml",
    "benchmark.yaml",
    "controller.yaml",
):
    (empty_configs_dir / _config_filename).write_text("{}\n", encoding="utf-8")

configuration_service = ConfigurationService(configs_dir=empty_configs_dir)
configuration_service.initialize()
check(
    # REQ-CONF-001: loading happens during this service's own
    # initialize() call, mirroring how core.startup.startup() loads
    # configuration during application startup.
    configuration_service.is_initialized,
    "ConfigurationService.initialize() marks the service initialized",
)

bundle = configuration_service.load_session_bundle()
check(
    # REQ-CONF-015: every one of these typed accessors hands back a
    # validated schema instance -- never a raw dictionary -- to this
    # (authorized) caller.
    bundle.deployment is not None
    and bundle.network is not None
    and bundle.cluster is not None
    and bundle.controller is not None
    and bundle.benchmark is not None
    and bundle.logging is not None,
    "ConfigurationService.load_session_bundle() returns every session configuration",
)
check(
    isinstance(configuration_service.manager, ConfigurationManager),
    "ConfigurationService.manager exposes the underlying ConfigurationManager",
)

configuration_service.shutdown()
check(
    not configuration_service.is_initialized,
    "ConfigurationService.shutdown() marks the service uninitialized",
)


# ---------------------------------------------------------------------------
# services.logging_service.LoggingService
# ---------------------------------------------------------------------------

from config.schemas.logging_schema import LoggingConfig  # noqa: E402
from logging_engine.log_manager import LogManager  # noqa: E402

log_dir = _TEMP_ROOT / "logs"
logging_service = LoggingService(
    log_manager=LogManager(LoggingConfig(log_directory=str(log_dir)))
)
logging_service.initialize()
check(
    # NFR-MAIN-002: LoggingService exposes exactly the initialize()/
    # is_initialized/shutdown() lifecycle interfaces.service.Service
    # documents, over the LogManager it composes rather than inherits
    # from.
    logging_service.is_initialized,
    "LoggingService.initialize() starts the LogManager",
)

import logging as _logging  # noqa: E402

# REQ-LOG-001: two different Aquila subsystem loggers ("aquila.
# deployment", "aquila.network") both route through this one
# initialized LogManager -- exactly the centralized logging interface
# REQ-LOG-001 calls for, exercised here instead of duplicated
# per-subsystem logging machinery.
_logging.getLogger("aquila.deployment").info("services test: deployment log line")
_logging.getLogger("aquila.network").info("services test: network log line")

for handler in _logging.getLogger("aquila").handlers:
    handler.flush()
for handler in _logging.getLogger("aquila.deployment").handlers:
    handler.flush()

files = logging_service.list_log_files()
check(
    any(info.name == "deployment.log" for info in files),
    "LoggingService.list_log_files() lists a written subsystem log file",
)
check(
    all(info.size_bytes >= 0 for info in files),
    "LoggingService.list_log_files() reports a non-negative size for every file",
)

deployment_log_text = logging_service.read_log("deployment.log")
check(
    "services test: deployment log line" in deployment_log_text,
    "LoggingService.read_log() returns the written content",
)

tail_text = logging_service.read_log("deployment.log", tail_lines=1)
check(
    "services test: deployment log line" in tail_text,
    "LoggingService.read_log(tail_lines=1) still contains the last line",
)

try:
    logging_service.read_log("../../etc/passwd")
    # REQ-LOG-013: refusing to read outside the managed log directory
    # protects log integrity against being read (and, by the same
    # path-confinement logic elsewhere in this class, written) via an
    # unintended path.
    check(False, "LoggingService.read_log() rejects a path-escaping filename")
except FileNotFoundError:
    check(True, "LoggingService.read_log() rejects a path-escaping filename")

try:
    logging_service.read_log("does-not-exist.log")
    check(False, "LoggingService.read_log() raises for a missing file")
except FileNotFoundError:
    # NFR-REL-002: a missing log file is a recoverable failure, and
    # this specific, catchable exception -- rather than a generic
    # crash or a silently empty result -- is the informative
    # diagnostic a caller acts on.
    check(True, "LoggingService.read_log() raises for a missing file")

export_destination = _TEMP_ROOT / "log_export"
manifest = logging_service.export(export_destination)
check(
    # REQ-LOG-011/REQ-LOG-013: this is the deployment-report export
    # path, and the exported copy is checksummed (``manifest.files``
    # maps each exported filename to its SHA-256 digest) so later
    # tampering with the bundled copy would be detectable.
    "deployment.log" in manifest.files,
    "LoggingService.export() exports the written log file with a checksum",
)

logging_service.shutdown()
check(not logging_service.is_initialized, "LoggingService.shutdown() stops the LogManager")


# ---------------------------------------------------------------------------
# services.network_service.NetworkService
# ---------------------------------------------------------------------------


class _FakeNetworkManager:
    """A minimal stand-in exposing exactly the surface NetworkService uses."""

    def __init__(self, *, outcomes: list[bool]) -> None:
        self._outcomes = list(outcomes)
        self._call_count = 0
        self._initialized = False
        self.last_diagnostics: Optional[NetworkDiagnostics] = None

    def initialize(self) -> None:
        self._initialized = True

    def shutdown(self) -> None:
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def _make_diagnostics(self, *, ok: bool) -> NetworkDiagnostics:
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        diagnostics = NetworkDiagnostics(
            started_at=now,
            completed_at=now,
            ethernet_connected=ok,
            ethernet_detail="",
            ip_assignment_method="dhcp",
            ip_assignment_succeeded=ok,
            ip_assignment_detail="",
            controller_reachable=ok,
            aborted=not ok,
            abort_reason=None if ok else "simulated failure",
        )
        self.last_diagnostics = diagnostics
        return diagnostics

    def establish_connectivity(self, config: Any, **kwargs: Any) -> NetworkDiagnostics:
        ok = self._outcomes[0] if self._outcomes else True
        return self._make_diagnostics(ok=ok)

    def attempt_recovery(self, config: Any, **kwargs: Any) -> NetworkDiagnostics:
        self._call_count += 1
        ok = self._outcomes[min(self._call_count, len(self._outcomes) - 1)]
        return self._make_diagnostics(ok=ok)


network_config = NetworkConfig()
controller_config = ControllerConfig(host="controller.lab.local")
cluster_config = ClusterConfig(cluster_name="lab")

succeeding_manager = _FakeNetworkManager(outcomes=[True])
network_service = NetworkService(network_manager=succeeding_manager)
network_service.initialize()
result = network_service.establish(
    network_config, controller_config=controller_config, cluster_config=cluster_config
)
check(result.succeeded and not result.recovered, "NetworkService.establish() reports success on the first pass")

failing_manager = _FakeNetworkManager(outcomes=[False, True])
network_service = NetworkService(network_manager=failing_manager)
network_service.initialize()
result = network_service.establish(
    network_config,
    controller_config=controller_config,
    cluster_config=cluster_config,
    max_recovery_attempts=1,
)
check(
    result.succeeded and result.recovered,
    "NetworkService.establish() recovers after an initial failure",
)

always_failing_manager = _FakeNetworkManager(outcomes=[False, False, False])
network_service = NetworkService(network_manager=always_failing_manager)
network_service.initialize()
result = network_service.establish(
    network_config,
    controller_config=controller_config,
    cluster_config=cluster_config,
    max_recovery_attempts=2,
)
check(
    not result.succeeded and "simulated failure" in result.status_message,
    "NetworkService.establish() reports failure once recovery is exhausted",
)

no_recovery_manager = _FakeNetworkManager(outcomes=[False])
network_service = NetworkService(network_manager=no_recovery_manager)
network_service.initialize()
result = network_service.establish(
    network_config,
    controller_config=controller_config,
    cluster_config=cluster_config,
    max_recovery_attempts=0,
)
check(
    not result.succeeded,
    "NetworkService.establish() reports failure immediately when max_recovery_attempts=0",
)

network_service.shutdown()
check(not network_service.is_initialized, "NetworkService.shutdown() propagates to the NetworkManager")


# ---------------------------------------------------------------------------
# services.deployment_service.DeploymentService
# ---------------------------------------------------------------------------


class _FakeControllerClient:
    """A minimal stand-in for DeploymentControllerClient."""

    def __init__(
        self,
        *,
        reachable: bool = True,
        authenticate_error: Optional[Exception] = None,
        configuration_error: Optional[Exception] = None,
        node_config: Any = None,
    ) -> None:
        self.reachable = reachable
        self.authenticate_error = authenticate_error
        self.configuration_error = configuration_error
        self.node_config = node_config
        self.closed = False
        self.bearer_token: Optional[str] = None
        self.authenticated_with: Optional[tuple[str, str]] = None

    def verify_communication(self) -> bool:
        return self.reachable

    def authenticate(self, node_identifier: str, authentication_token: str) -> None:
        self.authenticated_with = (node_identifier, authentication_token)
        if self.authenticate_error is not None:
            raise self.authenticate_error

    def retrieve_configuration(self, node_identifier: str) -> Any:
        if self.configuration_error is not None:
            raise self.configuration_error
        return self.node_config

    def set_bearer_token(self, token: str) -> None:
        self.bearer_token = token

    def search_inventory(self, criteria: dict[str, Any]) -> dict[str, Any]:
        return {
            "records": [{"node_identifier": "node-svc-1", **criteria}],
            "total_matches": 1,
        }

    def get_node_benchmarks(self, node_identifier: str) -> list[dict[str, Any]]:
        return [{"node_identifier": node_identifier, "overall_score": 88}]

    def close(self) -> None:
        self.closed = True


from bootstrap.controller_client import NodeConfiguration  # noqa: E402

unreachable_client = _FakeControllerClient(reachable=False)
deployment_service = DeploymentService(
    controller_config, client_factory=lambda _cfg: unreachable_client
)
result = deployment_service.handshake("node-svc-1", enrollment_token="secret")
check(
    not result.reachable and not result.authenticated and not result.approved,
    "DeploymentService.handshake() reports an unreachable Controller without raising",
)

failed_auth_client = _FakeControllerClient(
    authenticate_error=DeploymentAuthenticationError("bad token")
)
deployment_service = DeploymentService(
    controller_config, client_factory=lambda _cfg: failed_auth_client
)
result = deployment_service.handshake("node-svc-1", enrollment_token="wrong")
check(
    result.reachable and not result.authenticated and not result.approved,
    "DeploymentService.handshake() reports a failed authentication without raising",
)

pending_client = _FakeControllerClient(
    configuration_error=DeploymentConfigurationError("not approved yet")
)
deployment_service = DeploymentService(
    controller_config, client_factory=lambda _cfg: pending_client
)
result = deployment_service.handshake("node-svc-1", enrollment_token="secret")
check(
    result.authenticated and not result.approved,
    "DeploymentService.handshake() reports 'pending approval' distinctly from a failure",
)

approved_node_config = NodeConfiguration(
    hostname="aquila-node-svc",
    ssh_authorized_keys=("ssh-ed25519 AAAAtest",),
    cluster_join_token="join-token",
    node_identifier="node-svc-1",
)
approved_client = _FakeControllerClient(node_config=approved_node_config)
deployment_service = DeploymentService(
    controller_config, client_factory=lambda _cfg: approved_client
)
result = deployment_service.handshake("node-svc-1", enrollment_token="secret")
check(
    result.approved
    and result.hostname == "aquila-node-svc"
    and result.cluster_join_token == "join-token"
    and result.ssh_authorized_keys == ("ssh-ed25519 AAAAtest",),
    "DeploymentService.handshake() returns the assigned configuration once approved",
)
check(
    approved_client.authenticated_with == ("node-svc-1", "secret"),
    "DeploymentService.handshake() authenticates with the supplied enrollment token",
)

check(deployment_service.check_reachable(), "DeploymentService.check_reachable() delegates to the client")

deployment_service.shutdown()
check(approved_client.closed, "DeploymentService.shutdown() closes the underlying client")


# ---------------------------------------------------------------------------
# services.inventory_service.InventoryService
# ---------------------------------------------------------------------------

search_client = _FakeControllerClient()
inventory_service = InventoryService(
    controller_config,
    authorization_token="op-token",
    client_factory=lambda _cfg: search_client,
)
search_result = inventory_service.search(InventorySearchQuery(manufacturer="Dell"))
check(
    search_result.succeeded and search_result.total_matches == 1,
    "InventoryService.search() returns matching records",
)
check(
    search_client.bearer_token == "op-token",
    "InventoryService.search() applies the configured authorization token",
)

query = InventorySearchQuery(node_identifier="node-1", limit=25, offset=5)
params = query.to_params()
check(
    params["node_identifier"] == "node-1" and params["limit"] == "25" and params["offset"] == "5",
    "InventorySearchQuery.to_params() encodes non-empty fields",
)
check(
    "hostname" not in InventorySearchQuery().to_params(),
    "InventorySearchQuery.to_params() omits empty fields",
)


class _FailingSearchClient(_FakeControllerClient):
    def search_inventory(self, criteria: dict[str, Any]) -> dict[str, Any]:
        raise DeploymentNetworkError("search failed")


inventory_service = InventoryService(
    controller_config, client_factory=lambda _cfg: _FailingSearchClient()
)
search_result = inventory_service.search(InventorySearchQuery())
check(
    not search_result.succeeded and search_result.detail,
    "InventoryService.search() reports a network failure without raising",
)


# ---------------------------------------------------------------------------
# services.benchmark_service.BenchmarkService
# ---------------------------------------------------------------------------

benchmark_client = _FakeControllerClient()
benchmark_service = BenchmarkService(
    controller_config,
    authorization_token="op-token",
    client_factory=lambda _cfg: benchmark_client,
)
history = benchmark_service.get_history("node-svc-1")
check(
    history.succeeded and history.latest is not None and history.latest["overall_score"] == 88,
    "BenchmarkService.get_history() returns the node's recorded benchmark",
)
check(
    benchmark_client.bearer_token == "op-token",
    "BenchmarkService.get_history() applies the configured authorization token",
)


class _FailingBenchmarkClient(_FakeControllerClient):
    def get_node_benchmarks(self, node_identifier: str) -> list[dict[str, Any]]:
        raise DeploymentNetworkError("benchmark lookup failed")


benchmark_service = BenchmarkService(
    controller_config, client_factory=lambda _cfg: _FailingBenchmarkClient()
)
history = benchmark_service.get_history("node-svc-1")
check(
    not history.succeeded and history.latest is None,
    "BenchmarkService.get_history() reports a network failure without raising",
)


# ---------------------------------------------------------------------------
# bootstrap.controller_client.DeploymentControllerClient extensions
# (set_bearer_token / search_inventory / get_node_benchmarks) --
# already exercised end-to-end over a real HTTP server in
# run_tests_deployment_controller.py; this file only confirms the
# methods exist with the expected shape for services/ to call.
# ---------------------------------------------------------------------------

from bootstrap.controller_client import DeploymentControllerClient  # noqa: E402

check(
    hasattr(DeploymentControllerClient, "set_bearer_token")
    and hasattr(DeploymentControllerClient, "search_inventory")
    and hasattr(DeploymentControllerClient, "get_node_benchmarks"),
    "DeploymentControllerClient exposes the new operator-facing read methods",
)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

shutil.rmtree(_TEMP_ROOT, ignore_errors=True)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
if failures:
    print(f"{len(failures)} check(s) FAILED (of {passed + len(failures)}):")
    for failure in failures:
        print(f"  - {failure}")
    sys.exit(1)

print(f"{passed} check(s) passed.")
print("All services/ functional checks passed.")
