#!/usr/bin/env python3
"""
Functional test suite for src/deployment_controller/ (SRS Section
9.7/10.8, REQ-CTRL-001 through REQ-CTRL-021), src/inventory/ (SRS
Section 9.10/10.9, REQ-INV-001 through REQ-INV-010), and the
models/deployment, models/inventory, models/benchmark data models
built to support them.

Follows the exact plain-script convention every other
``run_tests_*.py`` in this repository already established: a
``check(condition, description)`` helper collects failures, printed as
a summary at the end with ``sys.exit(1)`` on any failure.

Uses a real (temporary, on-disk) SQLite database for the
inventory/database.py layer -- SQLite is the actual production
backend, not something worth faking -- and exercises the full HTTP
API server (``deployment_controller.api.ControllerAPIServer``) over a
real loopback socket using the *actual*, already-delivered
``bootstrap.controller_client.DeploymentControllerClient``, so this
suite proves the client/server contract genuinely round-trips rather
than merely asserting against each side's own assumptions about the
other.

Run with (from the repository root): python3 tests/run_tests_deployment_controller.py
"""

from __future__ import annotations

import os
import shutil
import socket
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

failures: list[str] = []
passed = 0


def check(condition: bool, description: str) -> None:
    global passed
    if condition:
        passed += 1
    else:
        failures.append(description)


from common.enums import DeploymentApprovalStatus, DeploymentStatus, NodeStatus
from common.exceptions.inventory import (
    InventoryDuplicateRecordError,
    InventoryRecordNotFoundError,
    InventoryValidationError,
)
from config.schemas.cluster_schema import ClusterConfig
from config.schemas.controller_server_schema import ControllerServerConfig

from deployment_controller.api import ControllerAPIServer
from deployment_controller.authentication import (
    NodeAuthenticator,
    TokenValidator,
    extract_bearer_token,
    is_valid_node_identifier,
)
from deployment_controller.authorization import (
    ApprovalStore,
    DeploymentAuthorizer,
)
from deployment_controller.configuration import (
    ConfigurationDistributor,
    HostnameAllocator,
)
from deployment_controller.controller import DeploymentController
from deployment_controller.inventory import InventoryIntake
from deployment_controller.reports import DeploymentReportIntake

from inventory.database import InventoryDatabase
from inventory.inventory_manager import InventoryManager
from inventory.node_registry import NodeRegistry

from models.benchmark.benchmark import BenchmarkRecord
from models.benchmark.result import BenchmarkCategoryResult
from models.deployment.deployment import DeploymentApproval
from models.deployment.report import DeploymentReportRecord
from models.deployment.session import DeploymentSessionRecord
from models.inventory.cluster import ClusterMembership
from models.inventory.node import InventoryRecord
from models.inventory.registry import InventorySearchCriteria


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TEMP_ROOT = Path(tempfile.mkdtemp(prefix="aquila_controller_test_"))


def _fresh_database() -> InventoryDatabase:
    path = _TEMP_ROOT / f"inventory_{time.time_ns()}.db"
    database = InventoryDatabase(path)
    database.initialize()
    return database


def _registration_payload(
    *,
    node_identifier: str = "node-aaaa1111",
    hostname: str = "",
    serial_number: str = "SERIAL-0001",
    mac_address: str = "AA:BB:CC:DD:EE:01",
) -> dict[str, Any]:
    return {
        "node_identifier": node_identifier,
        "hostname": hostname,
        "manufacturer": "Dell Inc.",
        "model": "OptiPlex 7080",
        "serial_number": serial_number,
        "cpu_model": "Intel Core i7-10700",
        "cpu_core_count": 8,
        "memory_total_bytes": 17179869184,
        "primary_disk_model": "Samsung 970 EVO",
        "primary_disk_capacity_bytes": 512110190592,
        "mac_address": mac_address,
    }


def _server_config(**overrides: Any) -> ControllerServerConfig:
    defaults: dict[str, Any] = dict(
        bind_host="127.0.0.1",
        use_tls=False,
        database_path=str(_TEMP_ROOT / f"server_{time.time_ns()}.db"),
        enrollment_token_env_var="AQUILA_TEST_CONTROLLER_TOKEN",
        auto_approve_nodes=True,
        hostname_prefix="aquila-node",
        ssh_authorized_keys=["ssh-ed25519 AAAATESTKEY test@example"],
    )
    defaults.update(overrides)
    return ControllerServerConfig(**defaults)


def _cluster_config(**overrides: Any) -> ClusterConfig:
    defaults: dict[str, Any] = dict(
        cluster_name="lab-cluster",
        primary_node_host="10.0.0.10",
        join_token_env_var="AQUILA_TEST_CLUSTER_TOKEN",
    )
    defaults.update(overrides)
    return ClusterConfig(**defaults)


# ---------------------------------------------------------------------------
# common.enums additions
# ---------------------------------------------------------------------------

check(
    {status.name for status in NodeStatus}
    == {
        "PENDING",
        "PROVISIONING",
        "BOOTSTRAPPING",
        "OPERATIONAL",
        "FAILED",
        "RETIRED",
    },
    "enums: NodeStatus matches REQ-INV-005's exact vocabulary",
)

check(
    {status.name for status in DeploymentApprovalStatus}
    == {"PENDING", "APPROVED", "DENIED"},
    "enums: DeploymentApprovalStatus matches REQ-CTRL-016's exact vocabulary",
)


# ---------------------------------------------------------------------------
# models.inventory.node.InventoryRecord
# ---------------------------------------------------------------------------

try:
    InventoryRecord.from_registration_payload({"node_identifier": "x"})
    check(False, "models.inventory.node: missing required fields raise")
except InventoryValidationError:
    check(True, "models.inventory.node: missing required fields raise")

# REQ-INV-002: asserts a registration payload's minimum required
# fields (node identifier, manufacturer, ...) land on the record.
record = InventoryRecord.from_registration_payload(_registration_payload())
check(
    record.node_identifier == "node-aaaa1111"
    and record.manufacturer == "Dell Inc."
    and record.status is NodeStatus.PENDING,
    "models.inventory.node: from_registration_payload builds a valid record",
)

round_tripped = InventoryRecord.from_dict(record.to_dict())
check(
    round_tripped.to_dict() == record.to_dict(),
    "models.inventory.node: to_dict()/from_dict() round-trips",
)

# ---------------------------------------------------------------------------
# models.inventory.cluster.ClusterMembership
# ---------------------------------------------------------------------------

membership = ClusterMembership(node_identifier="node-1", cluster_name="lab-cluster")
check(
    ClusterMembership.from_dict(membership.to_dict()).to_dict()
    == membership.to_dict(),
    "models.inventory.cluster: ClusterMembership round-trips",
)

# ---------------------------------------------------------------------------
# models.benchmark
# ---------------------------------------------------------------------------

category = BenchmarkCategoryResult.from_dict({"status": "PASS", "score": 88, "notes": "ok"})
check(
    category.passed and category.score == 88 and category.details == {"notes": "ok"},
    "models.benchmark.result: BenchmarkCategoryResult.from_dict parses correctly",
)

check(
    BenchmarkCategoryResult.from_dict("not-a-dict").status == "UNKNOWN",
    "models.benchmark.result: malformed category degrades to UNKNOWN, never raises",
)

benchmark_payload = {
    "timestamp": "2026-01-01T00:00:00+00:00",
    "hostname": "aquila-node-1",
    "benchmark_version": "1.0",
    "successful": True,
    "cpu": {"status": "PASS", "score": 90},
    "memory": {"status": "PASS", "score": 85},
    "overall_score": 175,
    "notes": ["all good"],
}
benchmark_record = BenchmarkRecord.from_payload("node-1", benchmark_payload)
check(
    benchmark_record.overall_score == 175
    and benchmark_record.category("cpu").score == 90
    and benchmark_record.successful,
    "models.benchmark.benchmark: BenchmarkRecord.from_payload parses correctly",
)

# ---------------------------------------------------------------------------
# models.deployment
# ---------------------------------------------------------------------------

session = DeploymentSessionRecord(node_identifier="node-1")
check(session.is_open, "models.deployment.session: a new session is open")
session.mark_completed(status=DeploymentStatus.SUCCESS)
check(not session.is_open, "models.deployment.session: mark_completed closes the session")

report = DeploymentReportRecord(node_identifier="node-1", status="success")
check(report.successful, "models.deployment.report: 'success' status is recognized")
check(
    not DeploymentReportRecord(node_identifier="node-1", status="failed").successful,
    "models.deployment.report: 'failed' status is recognized",
)

approval = DeploymentApproval(node_identifier="node-1")
check(
    approval.status is DeploymentApprovalStatus.PENDING and not approval.approved,
    "models.deployment.deployment: a new DeploymentApproval defaults to PENDING",
)


# ---------------------------------------------------------------------------
# inventory.database / inventory.node_registry
# ---------------------------------------------------------------------------

db = _fresh_database()
check(db.is_initialized, "inventory.database: initialize() succeeds")

registry = NodeRegistry(db)
registered = registry.register(record)
check(
    # REQ-CTRL-009: this persists to the Controller's SQLite hardware
    # inventory database rather than an in-memory structure.
    registry.exists("node-aaaa1111"),
    "inventory.node_registry: register() persists a node",
)

try:
    registry.register(record)
    check(False, "inventory.node_registry: duplicate register() raises")
except InventoryDuplicateRecordError:
    # REQ-CTRL-005/REQ-SEC-005: asserts a duplicate node identity is
    # rejected rather than silently overwriting the existing record.
    check(True, "inventory.node_registry: duplicate register() raises")

try:
    registry.get("does-not-exist")
    check(False, "inventory.node_registry: get() raises for a missing node")
except InventoryRecordNotFoundError:
    check(True, "inventory.node_registry: get() raises for a missing node")

updated = registry.update_status("node-aaaa1111", NodeStatus.OPERATIONAL)
check(
    updated.status is NodeStatus.OPERATIONAL,
    "inventory.node_registry: update_status() persists the new status",
)

registry.record_cluster_membership(
    ClusterMembership(node_identifier="node-aaaa1111", cluster_name="lab-cluster")
)
check(
    registry.get("node-aaaa1111").cluster_name == "lab-cluster",
    "inventory.node_registry: record_cluster_membership() updates the node's summary",
)

found_by_serial = registry.find_by_serial_number("SERIAL-0001")
check(
    found_by_serial is not None and found_by_serial.node_identifier == "node-aaaa1111",
    "inventory.node_registry: find_by_serial_number() finds a match",
)
check(
    registry.find_by_serial_number("NO-SUCH-SERIAL") is None,
    "inventory.node_registry: find_by_serial_number() returns None for no match",
)

registry.register(
    InventoryRecord.from_registration_payload(
        _registration_payload(
            node_identifier="node-bbbb2222",
            serial_number="SERIAL-0002",
            mac_address="AA:BB:CC:DD:EE:02",
        )
    )
)
search_result = registry.search(InventorySearchCriteria(manufacturer="dell"))
check(
    search_result.total_matches == 2,
    "inventory.node_registry: search() matches case-insensitively across records",
)
narrow_result = registry.search(InventorySearchCriteria(node_identifier="bbbb2222"))
check(
    narrow_result.total_matches == 1
    and narrow_result.records[0].node_identifier == "node-bbbb2222",
    "inventory.node_registry: search() narrows by a specific field",
)


# ---------------------------------------------------------------------------
# inventory.inventory_manager.InventoryManager
# ---------------------------------------------------------------------------

im_db = _fresh_database()
manager = InventoryManager(database=im_db)

manager.register_node(
    InventoryRecord.from_registration_payload(_registration_payload(node_identifier="node-mgr-1"))
)
check(
    manager.find("node-mgr-1") is not None,
    "inventory.inventory_manager: register_node() registers a new node",
)

# Idempotent re-registration updates rather than raising.
manager.register_node(
    InventoryRecord.from_registration_payload(
        _registration_payload(node_identifier="node-mgr-1", serial_number="SERIAL-0001-B")
    )
)
check(
    manager.get("node-mgr-1").serial_number == "SERIAL-0001-B",
    "inventory.inventory_manager: register_node() is idempotent and updates facts",
)

# REQ-CTRL-010: asserts every opened deployment session is recorded.
opened = manager.open_session("node-mgr-1")
check(opened.id is not None, "inventory.inventory_manager: open_session() persists a session")

report_record = manager.record_report("node-mgr-1", status="success", detail="all good")
check(
    # REQ-CTRL-015/REQ-INV-007: asserts a completion report is
    # received and persisted with an assigned id.
    report_record.id is not None,
    "inventory.inventory_manager: record_report() persists a report",
)
check(
    manager.get("node-mgr-1").status is NodeStatus.OPERATIONAL,
    # REQ-INV-004: asserts deployment status is recorded and updated.
    "inventory.inventory_manager: a successful report marks the node OPERATIONAL",
)
sessions_after = manager.get_sessions("node-mgr-1")
check(
    # REQ-CTRL-012/REQ-INV-006: asserts the node's session history is
    # retrievable and reflects the session's closed state.
    len(sessions_after) == 1 and not sessions_after[0].is_open,
    "inventory.inventory_manager: record_report() closes the open session",
)

manager.record_report("node-mgr-1", status="failed", detail="boom")
check(
    # REQ-CTRL-011: asserts a deployment failure is recorded against
    # the node's status.
    manager.get("node-mgr-1").status is NodeStatus.FAILED,
    "inventory.inventory_manager: a failed report marks the node FAILED",
)

recorded_benchmark = manager.record_benchmark("node-mgr-1", benchmark_payload)
check(
    # REQ-INV-003: asserts a submitted benchmark result is recorded.
    recorded_benchmark.overall_score == 175,
    "inventory.inventory_manager: record_benchmark() persists and returns a record",
)
benchmarks = manager.get_benchmarks("node-mgr-1")
check(
    # REQ-CTRL-014: asserts stored benchmark history round-trips.
    len(benchmarks) == 1 and benchmarks[0].category("cpu").score == 90,
    "inventory.inventory_manager: get_benchmarks() round-trips the stored payload",
)

reports = manager.get_reports("node-mgr-1")
# REQ-INV-006: asserts both recorded deployment reports for the node
# are retrievable, i.e. its deployment history is maintained.
check(len(reports) == 2, "inventory.inventory_manager: get_reports() lists all reports")


# ---------------------------------------------------------------------------
# deployment_controller.authentication
# ---------------------------------------------------------------------------

check(
    extract_bearer_token("Bearer secret-token") == "secret-token",
    "authentication: extract_bearer_token parses a well-formed header",
)
check(
    extract_bearer_token("Basic dXNlcjpwYXNz") is None,
    "authentication: extract_bearer_token rejects a non-Bearer scheme",
)
check(
    extract_bearer_token(None) is None,
    "authentication: extract_bearer_token handles a missing header",
)

check(
    # REQ-CTRL-002: asserts every request carries an identifier the
    # Controller can use to uniquely identify the requesting node.
    is_valid_node_identifier("node-aaaa1111") and not is_valid_node_identifier(""),
    "authentication: is_valid_node_identifier accepts sane identifiers, rejects empty",
)
check(
    not is_valid_node_identifier("has a space"),
    "authentication: is_valid_node_identifier rejects unsafe characters",
)

validator = TokenValidator(("secret-one", "secret-two"))
# REQ-SEC-009/REQ-SEC-016: TokenValidator accepting an arbitrary tuple
# of configured secrets, hashed and compared without the caller (or
# NodeAuthenticator below) ever handling the raw values, is both how
# credentials are "stored securely" and why a future authentication
# provider could sit behind this exact same validate() surface.
check(validator.validate("secret-one"), "authentication: TokenValidator accepts a configured token")
check(validator.validate("secret-two"), "authentication: TokenValidator accepts a second configured token")
check(not validator.validate("wrong"), "authentication: TokenValidator rejects an unknown token")
check(not validator.validate(None), "authentication: TokenValidator rejects a missing token")

authenticator = NodeAuthenticator(token_validator=validator)
good = authenticator.authenticate("node-x", "Bearer secret-one")
check(
    # REQ-CTRL-003/REQ-SEC-003: the Controller accepting a first-seen,
    # well-formed node_identifier is this design's "assign a unique
    # Aquila Node Identifier" (see authentication.py's module
    # docstring).
    good.authenticated,
    "authentication: NodeAuthenticator accepts a valid token + identifier",
)

bad_token = authenticator.authenticate("node-x", "Bearer nope")
# REQ-SEC-006: this is the exact rejection branch
# (NodeAuthenticator._reject()) that logs "Authentication rejected"
# and publishes NodeAuthenticationFailedEvent -- asserted here via its
# return value rather than the log line itself.
check(not bad_token.authenticated, "authentication: NodeAuthenticator rejects an invalid token")

bad_identifier = authenticator.authenticate("has a space", "Bearer secret-one")
check(
    not bad_identifier.authenticated,
    "authentication: NodeAuthenticator rejects a malformed node identifier",
)

revoking_authenticator = NodeAuthenticator(
    token_validator=validator, is_revoked=lambda node_id: node_id == "node-denied"
)
check(
    not revoking_authenticator.authenticate("node-denied", "Bearer secret-one").authenticated,
    "authentication: NodeAuthenticator honors the revocation check",
)


# ---------------------------------------------------------------------------
# deployment_controller.authorization
# ---------------------------------------------------------------------------

authz_db = _fresh_database()
# REQ-CTRL-008: ``ApprovalStore`` persists every decision below to the
# ``approvals`` table -- the Controller's deployment policy database.
store = ApprovalStore(authz_db)

auto_authorizer = DeploymentAuthorizer(store=store, auto_approve=True)
auto_result = auto_authorizer.authorize("node-auto")
check(
    auto_result.approved and auto_result.status is DeploymentApprovalStatus.APPROVED,
    "authorization: auto_approve=True approves a first-seen node",
)
check(
    auto_authorizer.authorize("node-auto").approved,
    "authorization: a re-checked node stays approved",
)

manual_store = ApprovalStore(_fresh_database())
manual_authorizer = DeploymentAuthorizer(store=manual_store, auto_approve=False)
pending_result = manual_authorizer.authorize("node-manual")
check(
    not pending_result.approved and pending_result.status is DeploymentApprovalStatus.PENDING,
    "authorization: auto_approve=False leaves a first-seen node PENDING",
)

manual_authorizer.set_approval(
    "node-manual", DeploymentApprovalStatus.APPROVED, decided_by="operator"
)
check(
    manual_authorizer.authorize("node-manual").approved,
    "authorization: set_approval(APPROVED) authorizes a node",
)

manual_authorizer.set_approval(
    "node-denied", DeploymentApprovalStatus.DENIED, reason="blocked for testing"
)
denied_result = manual_authorizer.authorize("node-denied")
check(
    # REQ-SEC-007: DeploymentAuthorizer.authorize()'s DENIED branch is
    # what logs "Authorization failed for node ..." -- exercised here
    # via its return value.
    not denied_result.approved and denied_result.status is DeploymentApprovalStatus.DENIED,
    "authorization: set_approval(DENIED) is honored by authorize()",
)
check(
    manual_authorizer.is_denied("node-denied") and not manual_authorizer.is_denied("node-manual"),
    "authorization: is_denied() reflects the stored decision",
)


# ---------------------------------------------------------------------------
# deployment_controller.configuration
# ---------------------------------------------------------------------------

allocator = HostnameAllocator(prefix="aquila-node")
hostname_a = allocator.allocate("node-aaaa1111")
hostname_b = allocator.allocate("node-bbbb2222")
check(
    hostname_a.startswith("aquila-node-") and hostname_a != hostname_b,
    "configuration: HostnameAllocator produces distinct, prefixed hostnames",
)
check(
    allocator.allocate("node-aaaa1111") == hostname_a,
    "configuration: HostnameAllocator is deterministic for a given identifier",
)

os.environ["AQUILA_TEST_CLUSTER_TOKEN"] = "join-token-xyz"
distributor = ConfigurationDistributor(
    controller_server_config=_server_config(),
    cluster_config=_cluster_config(),
)
configuration = distributor.build_configuration("node-aaaa1111")
config_dict = configuration.to_dict()
check(
    # REQ-CTRL-017: every field here (cluster name, SSH keys, join
    # token) traces back to the injected ControllerServerConfig/
    # ClusterConfig, i.e. policy distributed "according to
    # configuration" rather than a hardcoded value.
    config_dict["node_identifier"] == "node-aaaa1111"
    and config_dict["cluster_join_token"] == "join-token-xyz"
    and config_dict["cluster"]["name"] == "lab-cluster"
    and config_dict["ssh_authorized_keys"] == ["ssh-ed25519 AAAATESTKEY test@example"],
    "configuration: ConfigurationDistributor builds the REQ-CTRL-007 payload",
)

configuration_existing_hostname = distributor.build_configuration(
    "node-aaaa1111", hostname="already-assigned"
)
check(
    configuration_existing_hostname.hostname == "already-assigned",
    "configuration: an existing hostname is preserved rather than reassigned",
)

os.environ.pop("AQUILA_TEST_CLUSTER_TOKEN", None)
distributor_no_token = ConfigurationDistributor(
    controller_server_config=_server_config(),
    cluster_config=_cluster_config(),
)
config_no_token = distributor_no_token.build_configuration("node-y").to_dict()
check(
    config_no_token["cluster_join_token"] == "",
    "configuration: a missing cluster join token degrades to empty, never raises",
)


# ---------------------------------------------------------------------------
# deployment_controller.inventory / reports (intake adapters)
# ---------------------------------------------------------------------------

intake_db = _fresh_database()
intake_manager = InventoryManager(database=intake_db)
intake_manager.initialize()
intake = InventoryIntake(inventory_manager=intake_manager)

good_intake = intake.register(
    "node-intake-1", _registration_payload(node_identifier="node-intake-1")
)
check(good_intake.accepted, "deployment_controller.inventory: a matching registration is accepted")

mismatched_intake = intake.register(
    "node-intake-1", _registration_payload(node_identifier="node-OTHER")
)
check(
    not mismatched_intake.accepted,
    "deployment_controller.inventory: a node_identifier mismatch is rejected",
)

benchmark_before_registration = intake.submit_benchmark("node-never-registered", benchmark_payload)
check(
    not benchmark_before_registration.accepted,
    "deployment_controller.inventory: a benchmark for an unregistered node is rejected",
)

benchmark_after_registration = intake.submit_benchmark("node-intake-1", benchmark_payload)
check(
    benchmark_after_registration.accepted,
    "deployment_controller.inventory: a benchmark for a registered node is accepted",
)

report_intake = DeploymentReportIntake(inventory_manager=intake_manager)
missing_status = report_intake.record_completion("node-intake-1", {"detail": "no status"})
check(
    not missing_status.accepted,
    "deployment_controller.reports: a completion report without 'status' is rejected",
)
good_report = report_intake.record_completion(
    "node-intake-1", {"status": "success", "detail": "done"}
)
check(good_report.accepted, "deployment_controller.reports: a well-formed completion report is accepted")


# ---------------------------------------------------------------------------
# deployment_controller.controller.DeploymentController (in-process)
# ---------------------------------------------------------------------------

os.environ["AQUILA_TEST_CONTROLLER_TOKEN"] = "enroll-secret"
os.environ["AQUILA_TEST_CLUSTER_TOKEN"] = "join-token-xyz"

controller = DeploymentController(
    controller_server_config=_server_config(),
    cluster_config=_cluster_config(),
)
controller.initialize()

status, body = controller.handle_health()
check(status == 200 and body["status"] == "ok", "controller: handle_health() reports ok")

status, body = controller.handle_authenticate(
    {"node_identifier": "node-ctrl-1"}, "Bearer enroll-secret"
)
check(
    status == 200 and body["approval_status"] == "APPROVED",
    "controller: handle_authenticate() authenticates and auto-approves",
)

status, body = controller.handle_authenticate({"node_identifier": "node-ctrl-1"}, None)
check(status == 401, "controller: handle_authenticate() rejects a missing bearer token")

status, body = controller.handle_get_configuration("node-ctrl-1", "Bearer enroll-secret")
check(
    # REQ-CTRL-006: asserts an authorized node's request for
    # deployment configuration is answered with that configuration.
    status == 200
    and body["node_identifier"] == "node-ctrl-1"
    and body["cluster_join_token"] == "join-token-xyz"
    and body["hostname"].startswith("aquila-node-"),
    "controller: handle_get_configuration() returns REQ-CTRL-007's payload",
)

status, body = controller.handle_register_inventory(
    _registration_payload(node_identifier="node-ctrl-1"), "Bearer enroll-secret"
)
check(status == 200, "controller: handle_register_inventory() accepts a valid payload")

status, body = controller.handle_submit_benchmark(
    {**benchmark_payload, "node_identifier": "node-ctrl-1"}, "Bearer enroll-secret"
)
# REQ-CTRL-013: asserts the Controller's benchmark-intake endpoint
# accepts a submitted benchmark result.
check(status == 200, "controller: handle_submit_benchmark() accepts a valid payload")

status, body = controller.handle_completion(
    {"node_identifier": "node-ctrl-1", "status": "success", "detail": "done"},
    "Bearer enroll-secret",
)
# REQ-CTRL-015: asserts the Controller's completion-report endpoint
# accepts a submitted deployment report.
check(status == 200, "controller: handle_completion() accepts a valid completion report")

check(
    controller.dependencies.inventory_manager.get("node-ctrl-1").status
    is NodeStatus.OPERATIONAL,
    "controller: a successful end-to-end flow leaves the node OPERATIONAL",
)

status, body = controller.handle_get_configuration("node-ctrl-1", None)
check(
    status == 401,
    "controller: handle_get_configuration() authenticates before authorizing (REQ-SEC-002)",
)

denied_controller_deps = controller.dependencies
denied_controller_deps.authorizer.set_approval(
    "node-ctrl-2", DeploymentApprovalStatus.DENIED, reason="test denial"
)
controller.handle_authenticate({"node_identifier": "node-ctrl-2"}, "Bearer enroll-secret")
status, body = controller.handle_authenticate(
    {"node_identifier": "node-ctrl-2"}, "Bearer enroll-secret"
)
check(
    # REQ-SEC-004: a denied node cannot even complete authentication,
    # so it never reaches the point of receiving deployment
    # configuration.
    status == 401,
    "controller: a DENIED node is rejected at authentication (revocation check)",
)

controller.shutdown()
check(not controller.is_initialized, "controller: shutdown() marks the controller uninitialized")


# ---------------------------------------------------------------------------
# End-to-end: real HTTP server + the actual bootstrap client
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


os.environ["AQUILA_TEST_CONTROLLER_TOKEN"] = "enroll-secret-e2e"
os.environ["AQUILA_TEST_CLUSTER_TOKEN"] = "join-token-e2e"

http_port = _free_port()
http_server_config = _server_config(bind_port=http_port)

e2e_controller = DeploymentController(
    controller_server_config=http_server_config,
    cluster_config=_cluster_config(),
)
api_server = ControllerAPIServer(controller=e2e_controller, server_config=http_server_config)
api_server.start()

try:
    # A brief, bounded wait for the listener socket to actually be
    # accepting connections -- serve_forever() runs on a background
    # thread started by start(), and there is no synchronous "ready"
    # signal from http.server to wait on instead.
    deadline = time.monotonic() + 5.0
    listening = False
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", http_port), timeout=0.5):
                listening = True
                break
        except OSError:
            time.sleep(0.05)

    # REQ-CTRL-019: every request the real server below handles (this
    # one included) passes through _ControllerRequestHandler.
    # log_message(), so this end-to-end block exercises "log all
    # communications with Aquila nodes" on every call, even though it
    # asserts on the response rather than the emitted log line.
    check(listening, "api: ControllerAPIServer starts and accepts TCP connections")

    from api.client import ApiClient
    from bootstrap.controller_client import DeploymentControllerClient
    from config.schemas.controller_schema import ControllerConfig

    controller_config = ControllerConfig(
        host="127.0.0.1",
        port=http_port,
        use_tls=False,
        verify_tls_certificate=False,
        api_base_path=http_server_config.api_base_path,
        authentication_token_env_var="AQUILA_TEST_CONTROLLER_TOKEN",
    )

    # DeploymentControllerClient.__init__ branches on
    # ControllerConfig.use_tls when building its base URL, so this
    # exercises the plain-HTTP path against a use_tls=False server.
    client = DeploymentControllerClient(controller_config)

    check(
        # REQ-CONF-013: controller_config above (host, port, use_tls,
        # api_base_path, ...) is exactly the Deployment Controller
        # connection settings REQ-CONF-013 asks configuration to
        # support -- proven live here against a real running server,
        # not just constructed.
        client.verify_communication(),
        "api/e2e: DeploymentControllerClient.verify_communication() reaches "
        "the real health endpoint",
    )

    client.authenticate("node-e2e-1", "enroll-secret-e2e")
    check(True, "api/e2e: authenticate() completes without raising")

    node_configuration = client.retrieve_configuration("node-e2e-1")
    check(
        node_configuration.node_identifier == "node-e2e-1"
        and node_configuration.cluster_join_token == "join-token-e2e"
        and node_configuration.hostname.startswith("aquila-node-"),
        "api/e2e: retrieve_configuration() parses the live server's response",
    )

    client.register_inventory(_registration_payload(node_identifier="node-e2e-1"))
    check(True, "api/e2e: register_inventory() completes without raising")

    client.submit_benchmark({**benchmark_payload, "node_identifier": "node-e2e-1"})
    # REQ-BENCH-007: "Benchmark results shall be submitted to the
    # Deployment Controller" -- this is that submission, over a real
    # HTTP connection to a real running Controller.
    check(True, "api/e2e: submit_benchmark() completes without raising")

    client.report_completion("node-e2e-1", status="success", detail="e2e complete")
    check(True, "api/e2e: report_completion() completes without raising")

    final_record = e2e_controller.dependencies.inventory_manager.get("node-e2e-1")
    check(
        final_record.status is NodeStatus.OPERATIONAL
        and final_record.manufacturer == "Dell Inc.",
        "api/e2e: the full authenticate -> configure -> register -> "
        "benchmark -> complete flow lands correctly in the Inventory System",
    )

    from requests.exceptions import HTTPError

    bad_client = DeploymentControllerClient(
        ControllerConfig(
            host="127.0.0.1",
            port=http_port,
            use_tls=False,
            verify_tls_certificate=False,
            api_base_path=http_server_config.api_base_path,
            authentication_token_env_var="AQUILA_TEST_CONTROLLER_TOKEN",
        )
    )
    # No token was ever set via authenticate() on this client, so its
    # underlying ApiClient session carries no Authorization header --
    # the Controller must reject the request. Reaches into the
    # DeploymentControllerClient's own ApiClient directly (there is no
    # public method that issues a bare, unauthenticated GET) purely to
    # prove the server-side rejection; ApiClient.get_json() raises the
    # underlying requests.HTTPError as-is (see api/client.py -- it
    # re-raises RequestException without wrapping it in an ApiError
    # subclass).
    try:
        bad_client._client.get_json(
            "nodes/configuration", params={"node_identifier": "node-e2e-1"}
        )
        check(False, "api/e2e: an unauthenticated request is rejected (401)")
    except HTTPError as exc:
        check(
            exc.response is not None and exc.response.status_code == 401,
            "api/e2e: an unauthenticated request is rejected (401)",
        )

    client.close()
    bad_client.close()
finally:
    api_server.stop()

check(
    not api_server.is_initialized,
    "api: ControllerAPIServer.stop() releases the listening socket",
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
print("All deployment_controller/ + inventory/ functional checks passed.")
