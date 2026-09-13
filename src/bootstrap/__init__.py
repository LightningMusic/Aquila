"""
Project Aquila
=============

Bootstrap Engine

Phase Two's first-boot process -- SRS Section 10.7, REQ-BOOT-001
through REQ-BOOT-020. Converts a freshly-installed Proxmox node into
a production-ready Aquila node: registers with the Deployment
Controller, applies its assigned configuration, joins the designated
Proxmox cluster, registers inventory, benchmarks the hardware, and
reports completion.

Two-phase-boot architecture (see ``provisioning``'s module docstring
for the full reasoning): every subsystem built before this one
(``hardware``, ``inspection``, ``recovery``, ``preparation``,
``provisioning``) is WMI/Python code that only runs on Windows
(WinPE). Bootstrap is the first subsystem that runs entirely within
**Phase Two** -- the freshly-installed, Debian-based Proxmox Linux
environment -- invoked by Proxmox's own confirmed ``[first-boot]``
answer-file mechanism, not by any Aquila Windows/WinPE code. Its
hardware/power-management interactions (REQ-BOOT-007 through -011)
therefore use standard Linux/systemd/IPMI tooling, not a port of
``bios/``'s WMI-based approach, which cannot run here.

Resolved SRS ambiguity: Appendix B's Workflow B diagram shows
"Cluster Enrollment -> Benchmark -> Inventory Registration", while
the numbered REQ-BOOT-012 through REQ-BOOT-016 (and REQ-BENCH-010/
REQ-INV-003, which require a node's inventory record to exist before
benchmark results can be associated with it) imply Inventory
Registration before Benchmark. Confirmed with the user this session:
built as Enrollment -> Inventory -> Benchmark, matching the numbered
order and the REQ-BENCH-010/REQ-INV-003 dependency, not the diagram.

Flagged architectural gap: Bootstrap's first Controller call
(REQ-BOOT-003's authentication) needs a ``node_identifier`` and
authentication token this node does not yet have a confirmed way to
obtain -- nothing in ``provisioning/`` as built establishes or passes
either value from Phase One into Phase Two. See
``bootstrap.bootstrap_manager``'s module docstring and
``claude/aquila-project-status.md`` for the full note.

Public surface:

* :class:`bootstrap.hostname.HostnameConfigurator` -- REQ-BOOT-005.
* :class:`bootstrap.ssh.SSHKeyInstaller` -- REQ-BOOT-006.
* :class:`bootstrap.power.SleepTargetManager` /
  :class:`bootstrap.power.LidBehaviorConfigurator` /
  :class:`bootstrap.power.PowerRecoveryConfigurator` --
  REQ-BOOT-007/008/011.
* :class:`bootstrap.battery.BatteryThresholdConfigurator` --
  REQ-BOOT-009/010.
* :class:`bootstrap.cluster.ClusterEnrollment` -- REQ-BOOT-012/013.
* :class:`bootstrap.inventory.InventoryCollector` -- REQ-BOOT-014.
* :class:`bootstrap.benchmark.BenchmarkInitiator` -- REQ-BOOT-015.
* :class:`bootstrap.controller_client.DeploymentControllerClient` --
  REQ-BOOT-002/003/004/016.
* :class:`bootstrap.cleanup.ArtifactCleaner` -- REQ-BOOT-017.
* :class:`bootstrap.bootstrap_manager.BootstrapManager` -- the
  orchestrator; the only entry point a first-boot script should
  normally need.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from .battery import BatteryThresholdConfigurator, BatteryThresholdResult
from .benchmark import BenchmarkInitiator, BenchmarkRunner
from .bootstrap_manager import (
    STATUS_FAILED,
    STATUS_OPERATIONAL,
    BootstrapManager,
    BootstrapSummary,
)
from .cleanup import ArtifactCleaner, CleanupResult, DEFAULT_CLEANUP_PATHS
from .cluster import (
    ClusterEnrollment,
    ClusterJoinResult,
    ClusterVerificationResult,
)
from .controller_client import DeploymentControllerClient, NodeConfiguration
from .hostname import HostnameConfigurator, HostnameResult
from .inventory import InventoryCollector, NodeInventoryFacts
from .power import (
    LidBehaviorConfigurator,
    LidBehaviorResult,
    PowerRecoveryConfigurator,
    PowerRecoveryResult,
    SleepTargetManager,
    SleepTargetResult,
)
from .ssh import SSHKeyInstallResult, SSHKeyInstaller

__all__ = [
    "DEFAULT_CLEANUP_PATHS",
    "STATUS_FAILED",
    "STATUS_OPERATIONAL",
    "ArtifactCleaner",
    "BatteryThresholdConfigurator",
    "BatteryThresholdResult",
    "BenchmarkInitiator",
    "BenchmarkRunner",
    "BootstrapManager",
    "BootstrapSummary",
    "CleanupResult",
    "ClusterEnrollment",
    "ClusterJoinResult",
    "ClusterVerificationResult",
    "DeploymentControllerClient",
    "HostnameConfigurator",
    "HostnameResult",
    "InventoryCollector",
    "LidBehaviorConfigurator",
    "LidBehaviorResult",
    "NodeConfiguration",
    "NodeInventoryFacts",
    "PowerRecoveryConfigurator",
    "PowerRecoveryResult",
    "SSHKeyInstallResult",
    "SSHKeyInstaller",
    "SleepTargetManager",
    "SleepTargetResult",
]
