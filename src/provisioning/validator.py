"""
Project Aquila
=============

Minimum Deployment Requirements Validator

Implements REQ-PROV-005 ("The Provisioning Engine shall verify that
the target system satisfies minimum deployment requirements") and
REQ-PROV-006 ("If minimum deployment requirements are not satisfied,
provisioning shall terminate and generate a deployment report").

REQ-PROV-005 lists five minimums, at minimum:

* Supported CPU architecture (NFR-PORT-001: x86-64).
* Sufficient system memory (``DeploymentConfig.minimum_memory_gb``).
* Supported storage device (``DeploymentConfig.minimum_storage_gb``,
  and a recognized ``StorageDeviceType``).
* Functional Ethernet interface (a physical, enabled Ethernet adapter
  present in the hardware inspection report).
* Hardware virtualization support (``DeploymentConfig
  .require_virtualization_support`` against ``VirtualizationInfo
  .is_usable``).

Report-based, not live
------------------------
This validator checks the already-completed ``HardwareInspectionReport``
(REQ-INS-025/027/028) -- it is deliberately a historical/report-based
check, not a live re-scan. REQ-PROV-002/003's Ethernet *connectivity*
requirement (a live, current-state check performed immediately before
provisioning begins, mirroring ``preparation.sanitizer``'s fresh
re-verification discipline) is a separate, later check --
``provisioning.connectivity.ConnectivityChecker``'s job, not this
module's -- because a report captured minutes or hours earlier cannot
honestly stand in for "is the cable plugged in right now".

Every check is reported individually (``RequirementCheck``), not
collapsed into a single pass/fail boolean, so REQ-PROV-006's
"generate a deployment report" can tell the technician exactly which
minimum was not met and why -- collapsing to one opaque failure
message would be exactly the kind of dishonest degradation this
project's "detect and report the real limitation, never guess"
convention (``preparation.sanitizer``'s ATA/NVMe refusal,
``inspection``'s honest empty-list-on-unsupported-platform
convention) exists to avoid.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from common.constants.logging import PROVISIONING_LOGGER
from config.schemas.deployment_schema import DeploymentConfig
from inspection.report import HardwareInspectionReport
from models.hardware.cpu import CPUArchitecture
from models.hardware.network import NetworkAdapterType
from models.hardware.storage import StorageDevice, StorageDeviceType

logger = logging.getLogger(PROVISIONING_LOGGER)

#: NFR-PORT-001: "Project Aquila shall support deployment on x86-64
#: systems." This is the SRS's only stated supported-architecture
#: value for Version 1.0 -- no other architecture is documented as
#: supported, so none is silently accepted here.
_SUPPORTED_ARCHITECTURES = (CPUArchitecture.X86_64,)

_BYTES_PER_GIB = 1024**3


@dataclass(slots=True, frozen=True)
class RequirementCheck:
    """The outcome of one REQ-PROV-005 minimum-requirement check."""

    name: str
    passed: bool
    detail: str


@dataclass(slots=True, frozen=True)
class MinimumRequirementsResult:
    """Every REQ-PROV-005 check performed for one provisioning attempt."""

    checks: tuple[RequirementCheck, ...] = ()

    @property
    def satisfied(self) -> bool:
        """REQ-PROV-006's gate: whether every minimum was met."""

        return all(check.passed for check in self.checks)

    @property
    def failed_checks(self) -> tuple[RequirementCheck, ...]:
        return tuple(check for check in self.checks if not check.passed)

    @property
    def summary(self) -> str:
        if self.satisfied:
            return "All minimum deployment requirements were satisfied."

        failures = "; ".join(
            f"{check.name}: {check.detail}" for check in self.failed_checks
        )
        return f"Minimum deployment requirements not satisfied -- {failures}"


class MinimumRequirementsValidator:
    """
    Validates REQ-PROV-005's minimum deployment requirements against
    an already-completed hardware inspection report.
    """

    def validate(
        self,
        report: HardwareInspectionReport,
        deployment_config: DeploymentConfig,
        target_device: StorageDevice,
    ) -> MinimumRequirementsResult:
        """
        Return a check-by-check REQ-PROV-005 result.

        Args:
            report: The already-completed hardware inspection report
                (REQ-INS-025) to validate against.
            deployment_config: Supplies the configured minimums
                (``minimum_memory_gb``, ``minimum_storage_gb``,
                ``require_virtualization_support``).
            target_device: The specific storage device selected for
                this deployment (already sanitized by Preparation) --
                REQ-PROV-003(v1)/REQ-PROV-005's "sufficient storage
                capacity" is checked against this device, not merely
                the largest device in the system.
        """

        checks = (
            self._check_architecture(report),
            self._check_memory(report, deployment_config),
            self._check_storage(target_device, deployment_config),
            self._check_ethernet(report),
            self._check_virtualization(report, deployment_config),
        )

        result = MinimumRequirementsResult(checks=checks)

        if result.satisfied:
            logger.info("Minimum deployment requirements satisfied.")
        else:
            logger.warning(
                "Minimum deployment requirements NOT satisfied: %s",
                result.summary,
            )

        return result

    @staticmethod
    def _check_architecture(report: HardwareInspectionReport) -> RequirementCheck:
        architecture = report.cpu.data.architecture
        passed = architecture in _SUPPORTED_ARCHITECTURES
        return RequirementCheck(
            name="cpu_architecture",
            passed=passed,
            detail=(
                f"CPU architecture {architecture.value} is supported "
                "(NFR-PORT-001)."
                if passed
                else (
                    f"CPU architecture {architecture.value} is not "
                    "supported -- NFR-PORT-001 requires x86-64."
                )
            ),
        )

    @staticmethod
    def _check_memory(
        report: HardwareInspectionReport, deployment_config: DeploymentConfig
    ) -> RequirementCheck:
        required_bytes = deployment_config.minimum_memory_gb * _BYTES_PER_GIB
        actual_bytes = report.memory.data.total_capacity_bytes
        passed = actual_bytes >= required_bytes
        return RequirementCheck(
            name="system_memory",
            passed=passed,
            detail=(
                f"{actual_bytes / _BYTES_PER_GIB:.1f} GiB installed, "
                f"{deployment_config.minimum_memory_gb} GiB required."
            ),
        )

    @staticmethod
    def _check_storage(
        target_device: StorageDevice, deployment_config: DeploymentConfig
    ) -> RequirementCheck:
        required_bytes = deployment_config.minimum_storage_gb * _BYTES_PER_GIB
        type_recognized = target_device.device_type != StorageDeviceType.UNKNOWN
        capacity_sufficient = target_device.capacity_bytes >= required_bytes
        passed = type_recognized and capacity_sufficient

        if not type_recognized:
            detail = (
                f"Target device {target_device.device_path} has an "
                "unrecognized storage type -- REQ-PROV-005 requires a "
                "supported storage device."
            )
        else:
            detail = (
                f"Target device {target_device.device_path} "
                f"({target_device.device_type.value}): "
                f"{target_device.capacity_bytes / _BYTES_PER_GIB:.1f} GiB, "
                f"{deployment_config.minimum_storage_gb} GiB required."
            )

        return RequirementCheck(name="storage_capacity", passed=passed, detail=detail)

    @staticmethod
    def _check_ethernet(report: HardwareInspectionReport) -> RequirementCheck:
        adapters = report.network.data
        has_functional_ethernet = any(
            adapter.adapter_type is NetworkAdapterType.ETHERNET
            and adapter.is_physical
            and adapter.is_enabled
            for adapter in adapters
        )
        return RequirementCheck(
            name="ethernet_interface",
            passed=has_functional_ethernet,
            detail=(
                "A physical, enabled Ethernet adapter was detected."
                if has_functional_ethernet
                else (
                    "No physical, enabled Ethernet adapter was detected -- "
                    "REQ-PROV-005/REQ-NET-002 require one."
                )
            ),
        )

    @staticmethod
    def _check_virtualization(
        report: HardwareInspectionReport, deployment_config: DeploymentConfig
    ) -> RequirementCheck:
        if not deployment_config.require_virtualization_support:
            return RequirementCheck(
                name="virtualization_support",
                passed=True,
                detail=(
                    "Virtualization support is not required by the "
                    "current deployment configuration."
                ),
            )

        usable = report.virtualization.data.is_usable
        return RequirementCheck(
            name="virtualization_support",
            passed=usable,
            detail=(
                "Hardware virtualization is supported and enabled."
                if usable
                else (
                    "Hardware virtualization is not usable -- either the "
                    "CPU does not support it, or it is disabled in "
                    "firmware. REQ-PROV-005 requires it be usable "
                    "(supported and firmware-enabled)."
                )
            ),
        )


__all__ = [
    "MinimumRequirementsResult",
    "MinimumRequirementsValidator",
    "RequirementCheck",
]
