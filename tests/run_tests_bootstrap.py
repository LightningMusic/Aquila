#!/usr/bin/env python3
"""
Functional test suite for src/bootstrap/ (the Bootstrap Engine, Phase
Two's first-boot process).

Follows the exact plain-script convention established by
run_tests_preparation.py/run_tests_provisioning.py: a check(condition,
description) helper collects failures, printed as a summary at the end
with sys.exit(1) on any failure.

Every live-system-dependent operation (subprocess calls to
hostnamectl/systemctl/ipmitool/pvecm/dmidecode/lscpu/apt-get, sysfs
reads/writes, HTTP calls to the Deployment Controller) is exercised
through dependency injection -- this development environment is Linux
but has none of the real system state (no real Proxmox cluster, no
real BMC, no real Deployment Controller) that these modules touch in
production, and no real subprocess/sysfs/HTTP call should ever run in
a test.

Run with (from the repository root): python3 tests/run_tests_bootstrap.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
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


from common.exceptions.deployment import (
    DeploymentAuthenticationError,
    DeploymentClusterError,
    DeploymentConfigurationError,
    DeploymentReportError,
    DeploymentVerificationError,
)
from config.schemas.cluster_schema import ClusterConfig
from config.schemas.controller_schema import ControllerConfig
from config.schemas.deployment_schema import DeploymentConfig

from bootstrap.battery import BatteryThresholdConfigurator
from bootstrap.benchmark import BenchmarkInitiator
from bootstrap.bootstrap_manager import (
    STATUS_FAILED,
    STATUS_OPERATIONAL,
    BootstrapManager,
    BootstrapSummary,
)
from bootstrap.cleanup import ArtifactCleaner
from bootstrap.cluster import ClusterEnrollment
from bootstrap.controller_client import (
    DeploymentControllerClient,
    NodeConfiguration,
)
from bootstrap.hostname import HostnameConfigurator
from bootstrap.inventory import InventoryCollector
from bootstrap.power import (
    LidBehaviorConfigurator,
    PowerRecoveryConfigurator,
    SleepTargetManager,
)
from bootstrap.ssh import SSHKeyInstaller


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _proc(
    *, returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


class _ScriptedRunner:
    """
    A CommandRunner (the 1-arg ``args`` form used by hostname/ssh/
    power/battery/inventory/cleanup) that returns queued results in
    order and records every invocation.
    """

    def __init__(
        self, results: list[subprocess.CompletedProcess[str]]
    ) -> None:
        self._results = results
        self.calls: list[list[str]] = []

    def __call__(
        self, args: list[str]
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        index = min(len(self.calls) - 1, len(self._results) - 1)
        return self._results[index]


class _ScriptedClusterRunner:
    """
    A CommandRunner matching bootstrap.cluster's 3-arg (args,
    input_text, timeout) CommandRunner Protocol.
    """

    def __init__(
        self,
        results: list[
            subprocess.CompletedProcess[str] | subprocess.TimeoutExpired
        ],
    ) -> None:
        self._results = results
        self.calls: list[tuple[list[str], str | None, float | None]] = []

    def __call__(
        self,
        args: list[str],
        *,
        input_text: str | None,
        timeout: float | None,
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((args, input_text, timeout))
        index = min(len(self.calls) - 1, len(self._results) - 1)
        outcome = self._results[index]
        if isinstance(outcome, subprocess.TimeoutExpired):
            raise outcome
        return outcome


_sleep_calls: list[float] = []


def _fake_sleep(seconds: float) -> None:
    _sleep_calls.append(seconds)


def _deployment_config(**overrides: object) -> DeploymentConfig:
    return DeploymentConfig(**overrides)  # type: ignore[arg-type]


def _controller_config(**overrides: object) -> ControllerConfig:
    return ControllerConfig(**overrides)  # type: ignore[arg-type]


def _cluster_config(**overrides: object) -> ClusterConfig:
    return ClusterConfig(**overrides)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# hostname.HostnameConfigurator
# ---------------------------------------------------------------------------

with tempfile.TemporaryDirectory() as tmp:
    hosts_path = Path(tmp) / "hosts"
    hosts_path.write_text("127.0.0.1\tlocalhost\n", encoding="utf-8")

    ok_runner = _ScriptedRunner([_proc(returncode=0)])
    configurator = HostnameConfigurator(
        command_runner=ok_runner, hosts_file=hosts_path
    )
    result = configurator.configure("aquila-node-01")
    check(
        result.applied,
        "hostname: successful hostnamectl run reports applied "
        "(REQ-BOOT-005: configures the hostname assigned by the "
        "Deployment Controller)",
    )
    check(
        ok_runner.calls[0]
        == ["hostnamectl", "set-hostname", "aquila-node-01"],
        "hostname: hostnamectl invoked with set-hostname and the new name",
    )
    hosts_contents = hosts_path.read_text(encoding="utf-8")
    check(
        "127.0.1.1\taquila-node-01" in hosts_contents,
        "hostname: /etc/hosts gets a 127.0.1.1 line for the new hostname",
    )

    # Re-configuring replaces the prior Aquila-managed line rather than
    # duplicating it.
    result2 = configurator.configure("aquila-node-02")
    check(result2.applied, "hostname: re-configuration succeeds")
    hosts_contents2 = hosts_path.read_text(encoding="utf-8")
    check(
        hosts_contents2.count("Managed by Project Aquila Bootstrap Engine")
        == 1,
        "hostname: re-running configure() replaces, not duplicates, its "
        "/etc/hosts line",
    )
    check(
        "aquila-node-01" not in hosts_contents2,
        "hostname: the old hostname's /etc/hosts line is gone after "
        "re-configuration",
    )

    try:
        configurator.configure("-bad-start")
        check(False, "configure() should reject a hostname starting with '-'")
    except DeploymentConfigurationError:
        check(True, "hostname: rejects a hostname starting with a hyphen")

    try:
        configurator.configure("")
        check(False, "configure() should reject an empty hostname")
    except DeploymentConfigurationError:
        check(True, "hostname: rejects an empty hostname")

    failing_runner = _ScriptedRunner(
        [_proc(returncode=1, stderr="permission denied")]
    )
    failing_configurator = HostnameConfigurator(
        command_runner=failing_runner, hosts_file=hosts_path
    )
    try:
        failing_configurator.configure("aquila-node-03")
        check(False, "configure() should raise when hostnamectl fails")
    except DeploymentConfigurationError:
        check(True, "hostname: a failing hostnamectl call raises")


# ---------------------------------------------------------------------------
# ssh.SSHKeyInstaller
# ---------------------------------------------------------------------------

with tempfile.TemporaryDirectory() as tmp:
    ssh_dir = Path(tmp) / ".ssh"
    authorized_keys = ssh_dir / "authorized_keys"

    installer = SSHKeyInstaller(
        ssh_directory=ssh_dir, authorized_keys_path=authorized_keys
    )
    good_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5 operator@example"
    bogus_key = "not-a-real-key blah"
    ssh_result = installer.install([good_key, bogus_key])
    check(
        ssh_result.installed_count == 1,
        "ssh: exactly one recognized key is installed (REQ-BOOT-006: "
        "authorized SSH keys supplied by the Deployment Controller)",
    )
    check(
        ssh_result.rejected_keys == (bogus_key,),
        "ssh: the unrecognized key is reported as rejected, not installed",
    )
    check(
        authorized_keys.read_text(encoding="utf-8").strip() == good_key,
        "ssh: authorized_keys contains only the recognized key",
    )
    check(
        installer.verify_permissions(),
        "ssh: installed directory/file carry the required 0700/0600 modes",
    )

    try:
        installer.install([bogus_key])
        check(False, "install() should raise when zero keys are valid")
    except DeploymentConfigurationError:
        check(True, "ssh: raises when no supplied key is recognized")

    try:
        installer.install([])
        check(False, "install() should raise on an empty key list")
    except DeploymentConfigurationError:
        check(True, "ssh: raises on an empty key list")

    # A second install() call replaces rather than appends.
    other_key = "ssh-rsa AAAAB3NzaC1yc2E other@example"
    installer.install([other_key])
    check(
        authorized_keys.read_text(encoding="utf-8").strip() == other_key,
        "ssh: a second install() call replaces the prior authorized_keys "
        "content (declarative, not additive)",
    )


# ---------------------------------------------------------------------------
# power.SleepTargetManager / LidBehaviorConfigurator / PowerRecoveryConfigurator
# ---------------------------------------------------------------------------

ok_mask_runner = _ScriptedRunner([_proc(returncode=0)])
sleep_manager = SleepTargetManager(command_runner=ok_mask_runner)
sleep_result = sleep_manager.mask_all()
check(
    len(sleep_result.masked_targets) == 4,
    "power: mask_all() reports all 4 sleep/suspend targets masked "
    "(REQ-BOOT-007: configures OS power management per Aquila "
    "deployment policy)",
)
check(
    ok_mask_runner.calls[0][:2] == ["systemctl", "mask"],
    "power: mask_all() invokes 'systemctl mask'",
)

failing_mask_runner = _ScriptedRunner(
    [_proc(returncode=1, stderr="unit not found")]
)
try:
    SleepTargetManager(command_runner=failing_mask_runner).mask_all()
    check(False, "mask_all() should raise when systemctl mask fails")
except DeploymentConfigurationError:
    check(True, "power: mask_all() raises when systemctl mask fails")

with tempfile.TemporaryDirectory() as tmp:
    dropin_dir = Path(tmp) / "logind.conf.d"
    lid_runner = _ScriptedRunner([_proc(returncode=0)])
    lid_configurator = LidBehaviorConfigurator(
        dropin_directory=dropin_dir, command_runner=lid_runner
    )
    lid_result = lid_configurator.configure("ignore")
    check(
        lid_result.applied,
        "power: lid configuration reports applied (REQ-BOOT-008: "
        "configures laptop lid behavior to prevent unintended suspend)",
    )
    dropin_file = dropin_dir / "50-aquila-lid.conf"
    check(
        dropin_file.is_file()
        and "HandleLidSwitch=ignore" in dropin_file.read_text(
            encoding="utf-8"
        ),
        "power: lid drop-in file is written with the requested action",
    )
    check(
        lid_runner.calls[0]
        == ["systemctl", "restart", "systemd-logind"],
        "power: configure() restarts systemd-logind so the change takes "
        "effect immediately",
    )

    failing_restart_runner = _ScriptedRunner(
        [_proc(returncode=1, stderr="failed to restart")]
    )
    failing_lid_configurator = LidBehaviorConfigurator(
        dropin_directory=dropin_dir,
        command_runner=failing_restart_runner,
    )
    try:
        failing_lid_configurator.configure("ignore")
        check(
            False,
            "configure() should raise when systemd-logind restart fails",
        )
    except DeploymentConfigurationError:
        check(
            True,
            "power: raises when the systemd-logind restart command fails",
        )

# PowerRecoveryConfigurator: ipmitool not installed at all.
no_tool_configurator = PowerRecoveryConfigurator(
    command_runner=_ScriptedRunner([_proc(returncode=0)]),
    ipmi_device_candidates=(),
    ipmitool_path=None,
)
# which("ipmitool") will genuinely return None in this sandboxed test
# environment for a random unlikely-to-exist tool name check, but to
# keep this deterministic regardless of the host running the tests we
# don't rely on that -- ipmitool_path stays unset and no device
# candidates are configured, which alone is enough to report
# unsupported (an absent device is checked independent of the tool).
no_bmc_configurator = PowerRecoveryConfigurator(
    command_runner=_ScriptedRunner([_proc(returncode=0)]),
    ipmi_device_candidates=(Path("/nonexistent/ipmi-device-for-tests"),),
    ipmitool_path="ipmitool",
)
no_bmc_result = no_bmc_configurator.configure("always-on")
check(
    # NFR-PORT-003: an absent firmware/BMC power-recovery capability
    # (DeploymentConfig.power_recovery_policy) is reported unsupported
    # rather than failing deployment -- it is not required for safe
    # operation.
    not no_bmc_result.supported and not no_bmc_result.applied,
    "power: no local IPMI/BMC device present is reported unsupported, "
    "not an error",
)

with tempfile.TemporaryDirectory() as tmp:
    fake_ipmi_device = Path(tmp) / "ipmi0"
    fake_ipmi_device.write_text("", encoding="utf-8")

    ok_ipmi_runner = _ScriptedRunner([_proc(returncode=0)])
    present_configurator = PowerRecoveryConfigurator(
        command_runner=ok_ipmi_runner,
        ipmi_device_candidates=(fake_ipmi_device,),
        ipmitool_path="ipmitool",
    )
    present_result = present_configurator.configure("always-on")
    check(
        present_result.supported and present_result.applied,
        "power: a detected BMC with a successful ipmitool call applies "
        "the policy (REQ-BOOT-011: configures supported firmware power "
        "recovery behavior)",
    )
    check(
        ok_ipmi_runner.calls[0]
        == ["ipmitool", "chassis", "policy", "always-on"],
        "power: ipmitool invoked with 'chassis policy <policy>'",
    )

    failing_ipmi_runner = _ScriptedRunner(
        [_proc(returncode=1, stderr="command failed")]
    )
    failing_present_configurator = PowerRecoveryConfigurator(
        command_runner=failing_ipmi_runner,
        ipmi_device_candidates=(fake_ipmi_device,),
        ipmitool_path="ipmitool",
    )
    failing_present_result = failing_present_configurator.configure(
        "always-on"
    )
    check(
        failing_present_result.supported
        and not failing_present_result.applied,
        "power: a detected BMC whose ipmitool call fails reports "
        "supported-but-not-applied, and never raises (REQ-BOOT-010)",
    )


# ---------------------------------------------------------------------------
# battery.BatteryThresholdConfigurator
# ---------------------------------------------------------------------------

with tempfile.TemporaryDirectory() as tmp:
    power_supply_root = Path(tmp) / "power_supply"
    power_supply_root.mkdir()

    # BAT0: fully supports the generic charge-control attributes.
    bat0 = power_supply_root / "BAT0"
    bat0.mkdir()
    (bat0 / "charge_control_start_threshold").write_text(
        "0", encoding="utf-8"
    )
    (bat0 / "charge_control_end_threshold").write_text(
        "100", encoding="utf-8"
    )

    # BAT1: no charge-control attributes at all.
    bat1 = power_supply_root / "BAT1"
    bat1.mkdir()

    battery_configurator = BatteryThresholdConfigurator(
        power_supply_root=power_supply_root
    )
    discovered = battery_configurator.discover_batteries()
    check(
        len(discovered) == 2,
        "battery: discover_batteries() finds both BAT0 and BAT1",
    )

    battery_results = battery_configurator.configure(20, 80)
    check(
        len(battery_results) == 2,
        "battery: configure() returns one result per discovered battery",
    )

    bat0_result = next(
        r for r in battery_results if r.battery_name == "BAT0"
    )
    check(
        bat0_result.supported and bat0_result.applied,
        "battery: BAT0's supported thresholds are applied (REQ-BOOT-009: "
        "attempts to configure supported firmware battery charging "
        "thresholds)",
    )
    check(
        (bat0 / "charge_control_start_threshold").read_text(
            encoding="utf-8"
        )
        == "20"
        and (bat0 / "charge_control_end_threshold").read_text(
            encoding="utf-8"
        )
        == "80",
        "battery: BAT0's sysfs attributes actually receive the new "
        "threshold values",
    )

    bat1_result = next(
        r for r in battery_results if r.battery_name == "BAT1"
    )
    check(
        # NFR-PORT-002: hardware lacking a configured capability
        # (here, DeploymentConfig.battery_charge_start/end_threshold's
        # sysfs attributes) degrades gracefully -- reported
        # unsupported, never raised as an error.
        not bat1_result.supported and not bat1_result.applied,
        "battery: BAT1 (no charge-control attributes) is honestly "
        "reported unsupported, never raises",
    )

    no_battery_configurator = BatteryThresholdConfigurator(
        power_supply_root=Path(tmp) / "does-not-exist"
    )
    check(
        no_battery_configurator.configure(20, 80) == (),
        "battery: a system with no power-supply directory at all "
        "returns an empty result tuple, not an error",
    )


# ---------------------------------------------------------------------------
# cluster.ClusterEnrollment
# ---------------------------------------------------------------------------

# -- create (cluster_master) --------------------------------------------

create_runner = _ScriptedClusterRunner([_proc(returncode=0)])
create_enrollment = ClusterEnrollment(command_runner=create_runner)
create_result = create_enrollment.join(
    _cluster_config(node_role="cluster_master", cluster_name="lab-cluster"),
    "",
)
check(
    create_result.created_new_cluster and create_result.command_succeeded,
    "cluster: cluster_master role creates a new cluster via 'pvecm create' "
    "(REQ-BOOT-012: automatically enrolls the node into the designated "
    "Proxmox cluster)",
)
check(
    create_runner.calls[0][0] == ["pvecm", "create", "lab-cluster"],
    "cluster: 'pvecm create' invoked with the configured cluster name",
)

try:
    ClusterEnrollment(command_runner=_ScriptedClusterRunner([])).join(
        _cluster_config(node_role="cluster_master", cluster_name=""),
        "",
    )
    check(
        False,
        "join() should reject cluster_master with no cluster_name",
    )
except DeploymentClusterError:
    check(True, "cluster: cluster_master role requires a cluster_name")

# -- join_existing (cluster_member) --------------------------------------

join_runner = _ScriptedClusterRunner([_proc(returncode=0)])
join_enrollment = ClusterEnrollment(command_runner=join_runner)
join_result = join_enrollment.join(
    _cluster_config(
        node_role="cluster_member",
        primary_node_host="10.0.0.5",
        join_fingerprint="AA:BB",
    ),
    "s3cr3t",
)
check(
    not join_result.created_new_cluster and join_result.command_succeeded,
    "cluster: cluster_member role joins an existing cluster via "
    "'pvecm add'",
)
check(
    join_runner.calls[0][0]
    == ["pvecm", "add", "10.0.0.5", "--fingerprint", "AA:BB"],
    "cluster: 'pvecm add' includes --fingerprint when configured",
)
check(
    join_runner.calls[0][1] == "s3cr3t\n",
    "cluster: the join secret is piped to stdin, never passed as an "
    "argv argument (so it never appears in a process listing)",
)

try:
    ClusterEnrollment(command_runner=_ScriptedClusterRunner([])).join(
        _cluster_config(node_role="cluster_member", primary_node_host=""),
        "s3cr3t",
    )
    check(
        False,
        "join() should reject a cluster_member with no primary_node_host",
    )
except DeploymentClusterError:
    check(
        True,
        "cluster: cluster_member role requires a primary_node_host",
    )

try:
    ClusterEnrollment(command_runner=_ScriptedClusterRunner([])).join(
        _cluster_config(
            node_role="cluster_member", primary_node_host="10.0.0.5"
        ),
        "",
    )
    check(False, "join() should refuse an empty join_secret")
except DeploymentClusterError:
    check(
        True,
        "cluster: refuses to attempt an unauthenticated join with an "
        "empty join_secret",
    )

failing_join_runner = _ScriptedClusterRunner(
    [_proc(returncode=1, stderr="authentication failure")]
)
try:
    ClusterEnrollment(command_runner=failing_join_runner).join(
        _cluster_config(
            node_role="cluster_member", primary_node_host="10.0.0.5"
        ),
        "s3cr3t",
    )
    check(False, "join() should raise when 'pvecm add' fails")
except DeploymentClusterError:
    check(True, "cluster: raises when 'pvecm add' exits non-zero")

timeout_runner = _ScriptedClusterRunner(
    [subprocess.TimeoutExpired(cmd=["pvecm", "add"], timeout=120)]
)
try:
    ClusterEnrollment(command_runner=timeout_runner).join(
        _cluster_config(
            node_role="cluster_member", primary_node_host="10.0.0.5"
        ),
        "s3cr3t",
    )
    check(False, "join() should raise on a subprocess timeout")
except DeploymentClusterError:
    check(True, "cluster: a 'pvecm add' timeout is reported, not left hanging")

# -- verify ---------------------------------------------------------------

_sleep_calls.clear()
found_immediately_runner = _ScriptedClusterRunner(
    [_proc(returncode=0, stdout="1  x  A  aquila-node-01 (local)")]
)
verify_ok = ClusterEnrollment(
    command_runner=found_immediately_runner, sleep=_fake_sleep
).verify("aquila-node-01")
check(
    verify_ok.verified,
    "cluster: verify() succeeds (REQ-BOOT-013: verifies successful "
    "cluster enrollment) when the hostname is already present in "
    "'pvecm nodes'",
)
check(
    not _sleep_calls,
    "cluster: verify() does not sleep at all when the node is found on "
    "the first attempt",
)

_sleep_calls.clear()
retry_then_found_runner = _ScriptedClusterRunner(
    [
        _proc(returncode=0, stdout="1  x  A  other-node (local)"),
        _proc(returncode=0, stdout="1  x  A  other-node (local)\n2  x  A  aquila-node-02"),
    ]
)
retry_verify = ClusterEnrollment(
    command_runner=retry_then_found_runner, sleep=_fake_sleep
).verify("aquila-node-02")
check(
    retry_verify.verified,
    "cluster: verify() succeeds after retrying once the node appears",
)
check(
    len(_sleep_calls) == 1,
    "cluster: verify() sleeps exactly once between the two attempts "
    "that mattered",
)

_sleep_calls.clear()
never_found_runner = _ScriptedClusterRunner(
    [_proc(returncode=0, stdout="1  x  A  other-node (local)")]
)
try:
    ClusterEnrollment(
        command_runner=never_found_runner, sleep=_fake_sleep
    ).verify("aquila-node-99")
    check(
        False,
        "verify() should raise once all retries are exhausted without "
        "finding the node",
    )
except DeploymentVerificationError:
    check(
        True,
        "cluster: verify() raises DeploymentVerificationError after "
        "exhausting all retries (never trusts join()'s exit code alone)",
    )


# ---------------------------------------------------------------------------
# controller_client.DeploymentControllerClient
# ---------------------------------------------------------------------------


class _FakeApiClient:
    """
    A minimal stand-in for ``api.client.ApiClient`` implementing only
    the surface ``DeploymentControllerClient`` actually calls: get(),
    get_json(), post_json(), close(), and a ``session.headers`` dict.
    """

    class _Session:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}

    def __init__(
        self,
        *,
        get_raises: bool = False,
        get_json_result: Any = None,
        get_json_raises: bool = False,
        post_json_raises: bool = False,
    ) -> None:
        self.base_url = "https://controller.lab.local/api/v1"
        self.session = self._Session()
        self._get_raises = get_raises
        self._get_json_result = get_json_result
        self._get_json_raises = get_json_raises
        self._post_json_raises = post_json_raises
        self.post_calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    def get(self, endpoint: str) -> None:
        if self._get_raises:
            raise ConnectionError("unreachable")

    def get_json(
        self, endpoint: str, *, params: dict[str, Any] | None = None
    ) -> Any:
        if self._get_json_raises:
            raise ConnectionError("unreachable")
        return self._get_json_result

    def post_json(
        self, endpoint: str, *, json: dict[str, Any]
    ) -> None:
        if self._post_json_raises:
            raise ConnectionError("unreachable")
        self.post_calls.append((endpoint, json))

    def close(self) -> None:
        self.closed = True


ok_api = _FakeApiClient()
ok_client = DeploymentControllerClient(
    _controller_config(host="10.0.0.5"), api_client=ok_api  # type: ignore[arg-type]
)
check(
    ok_client.verify_communication(),
    "controller_client: verify_communication() (REQ-BOOT-002: verifies "
    "communication with the Deployment Controller) returns True when get() "
    "succeeds",
)

unreachable_api = _FakeApiClient(get_raises=True)
unreachable_client = DeploymentControllerClient(
    _controller_config(host="10.0.0.5"), api_client=unreachable_api  # type: ignore[arg-type]
)
check(
    # REQ-LOG-009/REQ-LOG-010: this is the exact branch of
    # verify_communication() that calls logger.error() through
    # BOOTSTRAP_LOGGER -- a Bootstrap event about communication with
    # the Deployment Controller -- exercised here via its return
    # value rather than the log line itself.
    not unreachable_client.verify_communication(),
    "controller_client: verify_communication() returns False (never "
    "raises) when the Controller is unreachable",
)

try:
    ok_client.authenticate("node-1", "")
    check(False, "authenticate() should reject an empty token")
except DeploymentAuthenticationError:
    check(
        True,
        "controller_client: authenticate() rejects an empty "
        "authentication token before ever calling the API",
    )

ok_client.authenticate("node-1", "tok3n")
check(
    ok_api.session.headers.get("Authorization") == "Bearer tok3n",
    "controller_client: authenticate() (REQ-BOOT-003: authenticates the "
    "node with the Deployment Controller) sets a Bearer Authorization "
    "header on the underlying session",
)
check(
    ok_api.post_calls
    and ok_api.post_calls[-1][0] == "nodes/authenticate",
    "controller_client: authenticate() posts to nodes/authenticate",
)

failing_auth_api = _FakeApiClient(post_json_raises=True)
failing_auth_client = DeploymentControllerClient(
    _controller_config(), api_client=failing_auth_api  # type: ignore[arg-type]
)
try:
    failing_auth_client.authenticate("node-1", "tok3n")
    check(False, "authenticate() should raise when the API call fails")
except DeploymentAuthenticationError:
    check(
        True,
        "controller_client: authenticate() wraps an API failure in "
        "DeploymentAuthenticationError",
    )

config_api = _FakeApiClient(
    get_json_result={
        "hostname": "aquila-node-01",
        "ssh_authorized_keys": ["ssh-ed25519 AAAA operator@example"],
        "cluster_join_token": "s3cr3t",
        "node_identifier": "node-1",
    }
)
config_client = DeploymentControllerClient(
    _controller_config(), api_client=config_api  # type: ignore[arg-type]
)
node_config = config_client.retrieve_configuration("node-1")
check(
    isinstance(node_config, NodeConfiguration)
    and node_config.hostname == "aquila-node-01"
    and node_config.ssh_authorized_keys
    == ("ssh-ed25519 AAAA operator@example",),
    "controller_client: retrieve_configuration() (REQ-BOOT-004: "
    "retrieves deployment configuration assigned to the node) parses a "
    "well-formed response into a NodeConfiguration",
)

no_hostname_api = _FakeApiClient(get_json_result={"hostname": ""})
no_hostname_client = DeploymentControllerClient(
    _controller_config(), api_client=no_hostname_api  # type: ignore[arg-type]
)
try:
    no_hostname_client.retrieve_configuration("node-1")
    check(
        False,
        "retrieve_configuration() should raise when no hostname is "
        "assigned",
    )
except DeploymentConfigurationError:
    check(
        True,
        "controller_client: retrieve_configuration() raises when the "
        "Controller assigns no hostname (REQ-CTRL-004)",
    )

non_dict_api = _FakeApiClient(get_json_result=["not", "a", "dict"])
non_dict_client = DeploymentControllerClient(
    _controller_config(), api_client=non_dict_api  # type: ignore[arg-type]
)
try:
    non_dict_client.retrieve_configuration("node-1")
    check(
        False,
        "retrieve_configuration() should raise on a non-object response",
    )
except DeploymentConfigurationError:
    check(
        True,
        "controller_client: retrieve_configuration() raises on a "
        "non-object (e.g. list) JSON response",
    )

ok_client.report_completion(
    "node-1", status=STATUS_OPERATIONAL, detail="all good"
)
check(
    ok_api.post_calls[-1][0] == "nodes/completion"
    and ok_api.post_calls[-1][1]["status"] == STATUS_OPERATIONAL,
    "controller_client: report_completion() (REQ-BOOT-016: reports "
    "deployment completion to the Deployment Controller) posts to "
    "nodes/completion with the given status",
)

failing_report_api = _FakeApiClient(post_json_raises=True)
failing_report_client = DeploymentControllerClient(
    _controller_config(), api_client=failing_report_api  # type: ignore[arg-type]
)
try:
    failing_report_client.report_completion(
        "node-1", status=STATUS_FAILED, detail="x"
    )
    check(False, "report_completion() should raise on API failure")
except DeploymentReportError:
    check(
        True,
        "controller_client: report_completion() wraps an API failure "
        "in DeploymentReportError",
    )

ok_client.register_inventory({"hostname": "aquila-node-01"})
check(
    ok_api.post_calls[-1][0] == "inventory/nodes",
    "controller_client: register_inventory() (REQ-BOOT-014: registers "
    "the node with the Aquila Inventory System) posts to inventory/nodes",
)

ok_client.submit_benchmark({"overall_score": 42})
check(
    ok_api.post_calls[-1][0] == "inventory/benchmarks",
    "controller_client: submit_benchmark() posts to inventory/benchmarks",
)

ok_client.close()
check(
    # REQ-SEC-013: closing the underlying ApiClient session is this
    # client's whole part in discarding the temporary bearer-token
    # credential it holds only in memory -- see close()'s own
    # docstring.
    ok_api.closed,
    "controller_client: close() closes the underlying ApiClient",
)

with DeploymentControllerClient(
    _controller_config(), api_client=_FakeApiClient()  # type: ignore[arg-type]
) as ctx_client:
    check(
        isinstance(ctx_client, DeploymentControllerClient),
        "controller_client: usable as a context manager",
    )


# ---------------------------------------------------------------------------
# inventory.InventoryCollector
# ---------------------------------------------------------------------------

with tempfile.TemporaryDirectory() as tmp:
    meminfo_path = Path(tmp) / "meminfo"
    meminfo_path.write_text(
        "MemTotal:       16384000 kB\nMemFree:        1000 kB\n",
        encoding="utf-8",
    )

    net_root = Path(tmp) / "net"
    lo_dir = net_root / "lo"
    lo_dir.mkdir(parents=True)
    (lo_dir / "address").write_text(
        "00:00:00:00:00:00\n", encoding="utf-8"
    )
    eth_dir = net_root / "eth0"
    eth_dir.mkdir()
    (eth_dir / "address").write_text(
        "AA:BB:CC:DD:EE:FF\n", encoding="utf-8"
    )

    def _inventory_runner(
        args: list[str],
    ) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["dmidecode", "-s"]:
            keyword = args[2]
            values = {
                "system-manufacturer": "Acme",
                "system-product-name": "TestBox 3000",
                "system-serial-number": "SN123456",
            }
            return _proc(returncode=0, stdout=values.get(keyword, ""))
        if args == ["lscpu"]:
            return _proc(
                returncode=0,
                stdout=(
                    "Model name:            Test CPU\n"
                    "Socket(s):             1\n"
                    "Core(s) per socket:    4\n"
                ),
            )
        if args[0] == "lsblk":
            return _proc(
                returncode=0,
                stdout="nvme0n1 TestSSD 256000000000 disk\n",
            )
        return _proc(returncode=1)

    collector = InventoryCollector(command_runner=_inventory_runner)

    # Patch the module-level sysfs roots this collector instance reads
    # from -- they're module constants, not constructor parameters, so
    # exercised via the collector's own private attribute-free reads
    # by pointing the constants at our fixtures for the duration of
    # this block.
    import bootstrap.inventory as inventory_module

    original_meminfo = inventory_module._MEMINFO_PATH
    original_net_root = inventory_module._SYS_NET_ROOT
    inventory_module._MEMINFO_PATH = meminfo_path
    inventory_module._SYS_NET_ROOT = net_root
    try:
        facts = collector.collect()
    finally:
        inventory_module._MEMINFO_PATH = original_meminfo
        inventory_module._SYS_NET_ROOT = original_net_root

    check(
        facts.manufacturer == "Acme" and facts.model == "TestBox 3000",
        "inventory: dmidecode-sourced manufacturer/model are collected",
    )
    check(
        facts.cpu_model == "Test CPU" and facts.cpu_core_count == 4,
        "inventory: lscpu-sourced CPU model and core count (sockets * "
        "cores/socket) are collected",
    )
    check(
        facts.memory_total_bytes == 16384000 * 1024,
        "inventory: /proc/meminfo's kB value is converted to bytes",
    )
    check(
        facts.primary_disk_model == "TestSSD"
        and facts.primary_disk_capacity_bytes == 256000000000,
        "inventory: lsblk's primary disk model/size are collected",
    )
    check(
        facts.mac_address == "AA:BB:CC:DD:EE:FF",
        "inventory: the loopback interface's all-zero MAC is skipped in "
        "favor of the real adapter's address",
    )

    facts_dict = facts.to_dict()
    check(
        facts_dict["manufacturer"] == "Acme"
        and facts_dict["mac_address"] == "AA:BB:CC:DD:EE:FF",
        "inventory: NodeInventoryFacts.to_dict() round-trips the "
        "collected fields",
    )

# Every lookup degrades honestly when the underlying commands fail.
def _always_failing_runner(
    args: list[str],
) -> subprocess.CompletedProcess[str]:
    return _proc(returncode=1)


degraded_collector = InventoryCollector(
    command_runner=_always_failing_runner
)
import bootstrap.inventory as inventory_module2

original_meminfo2 = inventory_module2._MEMINFO_PATH
original_net_root2 = inventory_module2._SYS_NET_ROOT
inventory_module2._MEMINFO_PATH = Path("/nonexistent/meminfo/for/tests")
inventory_module2._SYS_NET_ROOT = Path("/nonexistent/net/for/tests")
try:
    degraded_facts = degraded_collector.collect()
finally:
    inventory_module2._MEMINFO_PATH = original_meminfo2
    inventory_module2._SYS_NET_ROOT = original_net_root2

check(
    degraded_facts.manufacturer == ""
    and degraded_facts.cpu_core_count == 0
    and degraded_facts.memory_total_bytes == 0
    and degraded_facts.mac_address == "",
    "inventory: collect() never raises -- every failed lookup degrades "
    "to an empty/zero value",
)


# ---------------------------------------------------------------------------
# benchmark.BenchmarkInitiator
# ---------------------------------------------------------------------------

from benchmark.report import BenchmarkReport


class _StubBenchmarkRunner:
    def __init__(self, report: BenchmarkReport) -> None:
        self._report = report

    def run(self) -> BenchmarkReport:
        return self._report


successful_report = BenchmarkReport(
    successful=True, overall_score=1234
)
initiator = BenchmarkInitiator(
    benchmark_runner=_StubBenchmarkRunner(successful_report)
)
check(
    initiator.run() is successful_report,
    "benchmark: BenchmarkInitiator.run() (REQ-BOOT-015: initiates "
    "hardware benchmarking after successful cluster enrollment) returns "
    "the underlying BenchmarkManager-equivalent's report unchanged",
)

failed_report = BenchmarkReport(successful=False, overall_score=0)
failed_initiator = BenchmarkInitiator(
    benchmark_runner=_StubBenchmarkRunner(failed_report)
)
check(
    failed_initiator.run().successful is False,
    "benchmark: a failed-category report is returned as-is, not "
    "converted into a raised exception (REQ-BENCH-008)",
)


# ---------------------------------------------------------------------------
# cleanup.ArtifactCleaner
# ---------------------------------------------------------------------------

with tempfile.TemporaryDirectory() as tmp:
    scratch_file = Path(tmp) / "scratch.tmp"
    scratch_file.write_text("x", encoding="utf-8")
    empty_dir = Path(tmp) / "empty_scratch_dir"
    empty_dir.mkdir()
    missing_path = Path(tmp) / "does-not-exist.tmp"

    apt_runner = _ScriptedRunner([_proc(returncode=0)])
    cleaner = ArtifactCleaner(command_runner=apt_runner)
    cleanup_result = cleaner.clean(
        [scratch_file, empty_dir, missing_path], clear_apt_cache=True
    )
    check(
        not scratch_file.exists() and not empty_dir.exists(),
        "cleanup: an explicitly-listed file and empty directory are "
        "both removed (REQ-BOOT-017: removes temporary installation "
        "artifacts after successful deployment)",
    )
    check(
        len(cleanup_result.removed_paths) == 2,
        "cleanup: removed_paths reports exactly the 2 paths that "
        "actually existed and were removed",
    )
    check(
        cleanup_result.apt_cache_cleared,
        "cleanup: apt_cache_cleared reflects a successful 'apt-get clean'",
    )

    failing_apt_runner = _ScriptedRunner(
        [_proc(returncode=1, stderr="lock held")]
    )
    failing_cleaner = ArtifactCleaner(command_runner=failing_apt_runner)
    failing_cleanup_result = failing_cleaner.clean(
        [], clear_apt_cache=True
    )
    check(
        not failing_cleanup_result.apt_cache_cleared,
        "cleanup: a failing 'apt-get clean' is reported honestly, "
        "never raises",
    )

    no_op_result = ArtifactCleaner(
        command_runner=_ScriptedRunner([_proc(returncode=0)])
    ).clean([], clear_apt_cache=False)
    check(
        no_op_result.removed_paths == ()
        and not no_op_result.apt_cache_cleared,
        "cleanup: clear_apt_cache=False with an empty path list is a "
        "true no-op",
    )


# ---------------------------------------------------------------------------
# bootstrap_manager.BootstrapManager
# ---------------------------------------------------------------------------


def _good_node_config() -> NodeConfiguration:
    return NodeConfiguration(
        hostname="aquila-node-01",
        ssh_authorized_keys=("ssh-ed25519 AAAA operator@example",),
        cluster_join_token="s3cr3t",
        node_identifier="node-1",
    )


class _StubControllerClient:
    """
    A DeploymentControllerClient stand-in the manager's ``run()``
    accepts directly via its ``controller_client`` parameter --
    avoids constructing a real ApiClient/HTTP session in these tests.
    """

    def __init__(
        self,
        *,
        reachable: bool = True,
        auth_should_fail: bool = False,
        config_should_fail: bool = False,
        node_config: NodeConfiguration | None = None,
        inventory_should_fail: bool = False,
        completion_should_fail: bool = False,
    ) -> None:
        self.reachable = reachable
        self.auth_should_fail = auth_should_fail
        self.config_should_fail = config_should_fail
        self._node_config = node_config or _good_node_config()
        self.inventory_should_fail = inventory_should_fail
        self.completion_should_fail = completion_should_fail
        self.closed = False
        self.completion_calls: list[dict[str, Any]] = []
        self.inventory_payloads: list[dict[str, Any]] = []
        self.benchmark_payloads: list[dict[str, Any]] = []

    def verify_communication(self) -> bool:
        return self.reachable

    def authenticate(
        self, node_identifier: str, authentication_token: str
    ) -> None:
        if self.auth_should_fail:
            raise DeploymentAuthenticationError("simulated auth failure")

    def retrieve_configuration(
        self, node_identifier: str
    ) -> NodeConfiguration:
        if self.config_should_fail:
            raise DeploymentConfigurationError(
                "simulated configuration-retrieval failure"
            )
        return self._node_config

    def report_completion(
        self, node_identifier: str, *, status: str, detail: str
    ) -> None:
        if self.completion_should_fail:
            raise DeploymentReportError("simulated report failure")
        self.completion_calls.append(
            {"status": status, "detail": detail}
        )

    def register_inventory(self, payload: dict[str, Any]) -> None:
        if self.inventory_should_fail:
            raise DeploymentConfigurationError(
                "simulated inventory-registration failure"
            )
        self.inventory_payloads.append(payload)

    def submit_benchmark(self, payload: dict[str, Any]) -> None:
        self.benchmark_payloads.append(payload)

    def close(self) -> None:
        self.closed = True


def _stub_hostname_configurator(
    *, should_fail: bool = False
) -> HostnameConfigurator:
    runner = _ScriptedRunner(
        [_proc(returncode=1 if should_fail else 0)]
    )
    return HostnameConfigurator(
        command_runner=runner,
        hosts_file=Path(tempfile.mkstemp()[1]),
    )


def _stub_ssh_installer() -> SSHKeyInstaller:
    tmp_dir = Path(tempfile.mkdtemp())
    return SSHKeyInstaller(
        ssh_directory=tmp_dir / ".ssh",
        authorized_keys_path=tmp_dir / ".ssh" / "authorized_keys",
    )


def _always_ok_power_components() -> dict[str, Any]:
    return dict(
        sleep_target_manager=SleepTargetManager(
            command_runner=_ScriptedRunner([_proc(returncode=0)])
        ),
        lid_configurator=LidBehaviorConfigurator(
            dropin_directory=Path(tempfile.mkdtemp()),
            command_runner=_ScriptedRunner([_proc(returncode=0)]),
        ),
        battery_configurator=BatteryThresholdConfigurator(
            power_supply_root=Path(tempfile.mkdtemp())
        ),
        power_recovery_configurator=PowerRecoveryConfigurator(
            command_runner=_ScriptedRunner([_proc(returncode=0)]),
            ipmi_device_candidates=(),
        ),
        artifact_cleaner=ArtifactCleaner(
            command_runner=_ScriptedRunner([_proc(returncode=0)])
        ),
    )


def _manager(
    *,
    controller_client: _StubControllerClient | None = None,
    cluster_enrollment: ClusterEnrollment | None = None,
    inventory_collector: InventoryCollector | None = None,
    benchmark_initiator: BenchmarkInitiator | None = None,
    hostname_should_fail: bool = False,
) -> tuple[BootstrapManager, _StubControllerClient]:
    client = controller_client or _StubControllerClient()

    good_cluster_runner = _ScriptedClusterRunner(
        [
            _proc(returncode=0),  # join
            _proc(
                returncode=0,
                stdout="1  x  A  aquila-node-01 (local)",
            ),  # verify
        ]
    )

    manager = BootstrapManager(
        hostname_configurator=_stub_hostname_configurator(
            should_fail=hostname_should_fail
        ),
        ssh_installer=_stub_ssh_installer(),
        cluster_enrollment=(
            cluster_enrollment
            or ClusterEnrollment(
                command_runner=good_cluster_runner, sleep=_fake_sleep
            )
        ),
        inventory_collector=(
            inventory_collector
            or InventoryCollector(
                command_runner=lambda args: _proc(returncode=1)
            )
        ),
        benchmark_initiator=(
            benchmark_initiator
            or BenchmarkInitiator(
                benchmark_runner=_StubBenchmarkRunner(
                    BenchmarkReport(successful=True, overall_score=99)
                )
            )
        ),
        **_always_ok_power_components(),
    )
    return manager, client


def _run(
    manager: BootstrapManager, client: _StubControllerClient
) -> BootstrapSummary:
    return manager.run(
        node_identifier="node-1",
        authentication_token="tok3n",
        controller_config=_controller_config(host="10.0.0.5"),
        cluster_config=_cluster_config(
            node_role="cluster_member", primary_node_host="10.0.0.5"
        ),
        deployment_config=_deployment_config(),
        join_secret="s3cr3t",
        controller_client=client,  # type: ignore[arg-type]
    )


success_manager, success_client = _manager()
success_summary = _run(success_manager, success_client)
check(
    success_summary.operational and not success_summary.aborted,
    "bootstrap_manager: the full success path (REQ-BOOT-001: "
    "BootstrapManager.run() is the entry point invoked automatically "
    "after the first successful system boot) produces an operational, "
    "non-aborted summary",
)
check(
    success_summary.status == STATUS_OPERATIONAL,
    "bootstrap_manager: BootstrapSummary.status is 'operational' "
    "(REQ-BOOT-020: upon successful completion the node transitions "
    "into normal operational status) on success",
)
check(
    success_summary.hostname == "aquila-node-01",
    "bootstrap_manager: the summary's hostname comes from the "
    "Controller-assigned configuration",
)
check(
    success_summary.inventory_registered
    and success_client.inventory_payloads,
    "bootstrap_manager: inventory is registered with the Controller "
    "on the success path",
)
check(
    success_summary.benchmark_overall_score == 99
    and success_summary.benchmark_submitted,
    "bootstrap_manager: benchmark is run and submitted after inventory "
    "registration (this session's resolved ordering decision)",
)
check(
    success_client.completion_calls
    and success_client.completion_calls[-1]["status"]
    == STATUS_OPERATIONAL,
    "bootstrap_manager: completion is reported to the Controller with "
    "an operational status",
)
check(success_manager.last_summary is success_summary, "bootstrap_manager: last_summary reflects the most recent run")

# run() must not close a client the caller passed in itself -- only
# one it constructed on the caller's behalf.
check(
    not success_client.closed,
    "bootstrap_manager: run() never closes a controller_client the "
    "caller explicitly supplied (only one it constructed itself)",
)

round_tripped_summary = BootstrapSummary.from_dict(
    success_summary.to_dict()
)
check(
    round_tripped_summary.node_identifier
    == success_summary.node_identifier
    and round_tripped_summary.hostname == success_summary.hostname,
    "bootstrap_manager: BootstrapSummary (REQ-BOOT-018: the generated "
    "bootstrap completion report) round-trips through "
    "to_dict()/from_dict()",
)

# -- Required-stage failures halt the run -------------------------------

unreachable_manager, unreachable_client = _manager(
    controller_client=_StubControllerClient(reachable=False)
)
unreachable_summary = _run(unreachable_manager, unreachable_client)
check(
    unreachable_summary.aborted
    and not unreachable_summary.controller_reachable,
    "bootstrap_manager: an unreachable Deployment Controller aborts "
    "the run at the very first step",
)
check(
    not unreachable_summary.operational,
    "bootstrap_manager: an aborted run is never reported operational",
)

auth_fail_manager, auth_fail_client = _manager(
    controller_client=_StubControllerClient(auth_should_fail=True)
)
auth_fail_summary = _run(auth_fail_manager, auth_fail_client)
check(
    auth_fail_summary.aborted and not auth_fail_summary.authenticated,
    "bootstrap_manager: an authentication failure aborts the run",
)

config_fail_manager, config_fail_client = _manager(
    controller_client=_StubControllerClient(config_should_fail=True)
)
config_fail_summary = _run(config_fail_manager, config_fail_client)
check(
    config_fail_summary.aborted
    and not config_fail_summary.configuration_retrieved,
    "bootstrap_manager: a configuration-retrieval failure aborts the run",
)

hostname_fail_manager, hostname_fail_client = _manager(
    hostname_should_fail=True
)
hostname_fail_summary = _run(hostname_fail_manager, hostname_fail_client)
check(
    hostname_fail_summary.aborted,
    "bootstrap_manager: a hostname-configuration failure aborts the run",
)
check(
    hostname_fail_summary.cluster_join_result is None,
    "bootstrap_manager: once aborted on hostname, later required stages "
    "(cluster enrollment) are never attempted",
)

failing_cluster_runner = _ScriptedClusterRunner(
    [_proc(returncode=1, stderr="join refused")]
)
cluster_fail_manager, cluster_fail_client = _manager(
    cluster_enrollment=ClusterEnrollment(
        command_runner=failing_cluster_runner, sleep=_fake_sleep
    )
)
cluster_fail_summary = _run(cluster_fail_manager, cluster_fail_client)
check(
    cluster_fail_summary.aborted
    and cluster_fail_summary.cluster_verification_result is None,
    "bootstrap_manager: a cluster-join failure aborts before "
    "verification is even attempted",
)
check(
    not cluster_fail_client.inventory_payloads,
    "bootstrap_manager: inventory registration never runs once cluster "
    "enrollment has failed",
)

inventory_fail_manager, inventory_fail_client = _manager(
    controller_client=_StubControllerClient(inventory_should_fail=True)
)
inventory_fail_summary = _run(inventory_fail_manager, inventory_fail_client)
check(
    inventory_fail_summary.aborted
    and not inventory_fail_summary.inventory_registered,
    "bootstrap_manager: an inventory-registration failure aborts the run",
)
check(
    inventory_fail_summary.benchmark_overall_score is None,
    "bootstrap_manager: benchmarking never runs once inventory "
    "registration has failed (enforces this session's confirmed "
    "Enrollment -> Inventory -> Benchmark ordering)",
)

# -- Best-effort-stage failures never abort the run ----------------------


class _AlwaysExplodingBenchmarkRunner:
    def run(self) -> BenchmarkReport:
        raise RuntimeError("benchmark hardware fault")


benchmark_explode_manager, benchmark_explode_client = _manager(
    benchmark_initiator=BenchmarkInitiator(
        benchmark_runner=_AlwaysExplodingBenchmarkRunner()
    )
)
benchmark_explode_summary = _run(
    benchmark_explode_manager, benchmark_explode_client
)
check(
    benchmark_explode_summary.operational
    and not benchmark_explode_summary.aborted,
    "bootstrap_manager: a benchmark execution failure never aborts the "
    "run (REQ-BENCH-008: 'Benchmarking shall not prevent the node from "
    "entering operational service')",
)
check(
    benchmark_explode_summary.benchmark_overall_score is None
    and not benchmark_explode_summary.benchmark_submitted,
    "bootstrap_manager: a failed benchmark leaves the summary's "
    "benchmark fields honestly empty",
)

# A completion-report failure (the very last step) is logged, not fatal.
completion_fail_manager, completion_fail_client = _manager(
    controller_client=_StubControllerClient(completion_should_fail=True)
)
completion_fail_summary = _run(
    completion_fail_manager, completion_fail_client
)
check(
    completion_fail_summary.operational
    and not completion_fail_summary.completion_reported,
    "bootstrap_manager: a failed completion-report call never aborts "
    "an otherwise-successful run, and is honestly reflected as "
    "completion_reported=False",
)

# disable_sleep_targets=False means the sleep-target manager is never
# invoked at all -- verified through a manager whose sleep_target
# result must therefore be None.
no_sleep_disable_manager, no_sleep_disable_client = _manager()
no_sleep_summary = no_sleep_disable_manager.run(
    node_identifier="node-1",
    authentication_token="tok3n",
    controller_config=_controller_config(host="10.0.0.5"),
    cluster_config=_cluster_config(
        node_role="cluster_member", primary_node_host="10.0.0.5"
    ),
    deployment_config=_deployment_config(disable_sleep_targets=False),
    join_secret="s3cr3t",
    controller_client=no_sleep_disable_client,  # type: ignore[arg-type]
)
check(
    no_sleep_summary.sleep_target_result is None,
    "bootstrap_manager: disable_sleep_targets=False skips sleep-target "
    "masking entirely",
)

# battery thresholds are only attempted when both start and end are set.
no_battery_manager, no_battery_client = _manager()
no_battery_summary = _run(no_battery_manager, no_battery_client)
check(
    no_battery_summary.battery_results == (),
    "bootstrap_manager: battery-threshold configuration is skipped when "
    "no thresholds are configured (both None by default)",
)


# ---------------------------------------------------------------------------
# BootstrapSummary.operational -- best-effort stages never gate it
# ---------------------------------------------------------------------------

from datetime import UTC as _UTC
from datetime import datetime as _datetime

_now = _datetime.now(_UTC)

from bootstrap.hostname import HostnameResult
from bootstrap.ssh import SSHKeyInstallResult
from bootstrap.cluster import ClusterJoinResult, ClusterVerificationResult

minimal_operational_summary = BootstrapSummary(
    started_at=_now,
    completed_at=_now,
    node_identifier="node-1",
    hostname="aquila-node-01",
    controller_reachable=True,
    authenticated=True,
    configuration_retrieved=True,
    hostname_result=HostnameResult(
        hostname="aquila-node-01", applied=True, detail="ok"
    ),
    ssh_result=SSHKeyInstallResult(
        installed_count=1, rejected_keys=(), detail="ok"
    ),
    cluster_join_result=ClusterJoinResult(
        created_new_cluster=False,
        command_succeeded=True,
        detail="ok",
    ),
    cluster_verification_result=ClusterVerificationResult(
        verified=True, node_hostname="aquila-node-01", detail="ok"
    ),
    inventory_registered=True,
    # Every best-effort field left at its default (None/empty/False).
)
check(
    minimal_operational_summary.operational,
    "BootstrapSummary: operational is True when every required stage "
    "succeeded, even with every best-effort field at its default "
    "(REQ-BOOT-019: bootstrap is complete only after all required "
    "deployment stages have successfully completed)",
)

missing_ssh_summary = BootstrapSummary(
    started_at=_now,
    completed_at=_now,
    node_identifier="node-1",
    hostname="aquila-node-01",
    controller_reachable=True,
    authenticated=True,
    configuration_retrieved=True,
    hostname_result=HostnameResult(
        hostname="aquila-node-01", applied=True, detail="ok"
    ),
    ssh_result=SSHKeyInstallResult(
        installed_count=0, rejected_keys=(), detail="none installed"
    ),
    cluster_join_result=ClusterJoinResult(
        created_new_cluster=False,
        command_succeeded=True,
        detail="ok",
    ),
    cluster_verification_result=ClusterVerificationResult(
        verified=True, node_hostname="aquila-node-01", detail="ok"
    ),
    inventory_registered=True,
)
check(
    not missing_ssh_summary.operational,
    "BootstrapSummary: operational is False when zero SSH keys were "
    "installed, even though every other required stage succeeded",
)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print(f"\n{passed} check(s) passed.")
if failures:
    print(f"FAILED: {len(failures)} check(s) failed:\n")
    for description in failures:
        print(f"  - {description}")
    sys.exit(1)

print("All bootstrap/ functional checks passed.")
