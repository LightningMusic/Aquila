"""
Project Orion
=============

Virtualization Manager

Provides virtualization capability detection and management
for Project Orion.

This module sits above BIOSManager and is responsible for
determining whether a machine is capable of running modern
hypervisors such as Proxmox VE.

Responsibilities
----------------
• CPU virtualization detection
• Intel VT-x / AMD-V
• Intel VT-d / AMD IOMMU
• SLAT detection
• Nested virtualization support
• Hyper-V detection
• KVM detection
• Secure Boot
• TPM
• SR-IOV
• Readiness reporting
"""

from __future__ import annotations

import logging
import platform
import subprocess

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from bios.bios_manager import BIOSManager

logger = logging.getLogger(__name__)


# ==========================================================
# Enumerations
# ==========================================================

class CPUVendor(Enum):
    UNKNOWN = "unknown"
    INTEL = "intel"
    AMD = "amd"


class VirtualizationState(Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class HypervisorType(Enum):
    NONE = "none"
    HYPER_V = "hyper-v"
    KVM = "kvm"
    VMWARE = "vmware"
    VIRTUALBOX = "virtualbox"
    XEN = "xen"
    PROXMOX = "proxmox"
    OTHER = "other"


# ==========================================================
# Virtualization Status
# ==========================================================

@dataclass(slots=True)
class VirtualizationStatus:
    """
    Complete virtualization capability model.

    This represents both firmware capabilities and the
    operating system's view of the hardware.
    """

    cpu_vendor: CPUVendor = CPUVendor.UNKNOWN

    virtualization: VirtualizationState = (
        VirtualizationState.UNKNOWN
    )

    iommu: VirtualizationState = (
        VirtualizationState.UNKNOWN
    )

    slat: VirtualizationState = (
        VirtualizationState.UNKNOWN
    )

    nested_virtualization: VirtualizationState = (
        VirtualizationState.UNKNOWN
    )

    sriov: VirtualizationState = (
        VirtualizationState.UNKNOWN
    )

    tpm: VirtualizationState = (
        VirtualizationState.UNKNOWN
    )

    secure_boot: VirtualizationState = (
        VirtualizationState.UNKNOWN
    )

    hypervisor: HypervisorType = (
        HypervisorType.NONE
    )

    bios_virtualization_enabled: bool = False
    bios_iommu_enabled: bool = False

    cpu_virtualization_supported: bool = False
    iommu_supported: bool = False
    slat_supported: bool = False
    nested_supported: bool = False
    sriov_supported: bool = False

    proxmox_ready: bool = False

    warnings: list[str] = field(
        default_factory=list
    )

    notes: list[str] = field(
        default_factory=list
    )

    additional_information: dict[str, Any] = field(
        default_factory=dict
    )


# ==========================================================
# Virtualization Manager
# ==========================================================

class VirtualizationManager:
    """
    Controls virtualization readiness.

    BIOSManager
          │
          ▼
      Firmware State
          │
          ▼
    Virtualization Manager
          │
          ▼
    Proxmox Readiness
    """

    def __init__(
        self,
        bios_manager: BIOSManager,
    ) -> None:

        self._bios = bios_manager

        self._status = VirtualizationStatus()

        logger.info(
            "Virtualization Manager initialized."
        )

    # ======================================================
    # Properties
    # ======================================================

    @property
    def bios(self) -> BIOSManager:
        """
        Returns the BIOS manager.
        """

        return self._bios

    @property
    def status(self) -> VirtualizationStatus:
        """
        Returns the cached virtualization status.
        """

        return self._status

    # ======================================================
    # Initialization
    # ======================================================

    def initialize(self) -> bool:
        """
        Detect current virtualization capabilities.

        This method performs a complete scan of both
        firmware and operating-system capabilities.
        """

        logger.info(
            "Initializing Virtualization Manager..."
        )

        self._status = VirtualizationStatus()

        return True

    # ======================================================
    # Platform Helpers
    # ======================================================

    @staticmethod
    def operating_system() -> str:
        """
        Returns the operating system name.
        """

        return platform.system().lower()

    @staticmethod
    def is_windows() -> bool:

        return (
            platform.system().lower()
            == "windows"
        )

    @staticmethod
    def is_linux() -> bool:

        return (
            platform.system().lower()
            == "linux"
        )

    # ======================================================
    # Internal Helpers
    # ======================================================

    def _run(
        self,
        command: list[str],
    ) -> subprocess.CompletedProcess[str]:
        """
        Safely execute a subprocess command.
        """

        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

    def _add_warning(
        self,
        message: str,
    ) -> None:

        if message not in self._status.warnings:

            self._status.warnings.append(message)

    def _add_note(
        self,
        message: str,
    ) -> None:

        if message not in self._status.notes:

            self._status.notes.append(message)

    # ======================================================
    # Hardware Detection
    # ======================================================

    def detect_hardware(self) -> bool:
        """
        Perform a complete hardware virtualization scan.

        This is the primary entry point used during
        initialization.
        """

        logger.info(
            "Detecting virtualization capabilities..."
        )

        self._detect_cpu_vendor()
        self._detect_cpu_virtualization()
        self._detect_iommu()
        self._detect_slat()
        self._detect_nested_virtualization()
        self._detect_hypervisor()

        return True

    # ======================================================
    # CPU Vendor
    # ======================================================

    def _detect_cpu_vendor(self) -> None:

        logger.info(
            "Detecting CPU vendor..."
        )

        vendor = CPUVendor.UNKNOWN

        try:

            if self.is_windows():

                result = self._run(
                    [
                        "wmic",
                        "cpu",
                        "get",
                        "Manufacturer",
                    ]
                )

                output = result.stdout.lower()

            else:

                result = self._run(
                    [
                        "lscpu",
                    ]
                )

                output = result.stdout.lower()

            if "genuineintel" in output or "intel" in output:

                vendor = CPUVendor.INTEL

            elif "authenticamd" in output or "amd" in output:

                vendor = CPUVendor.AMD

        except Exception:

            logger.exception(
                "Unable to determine CPU vendor."
            )

        self._status.cpu_vendor = vendor

        logger.info(
            "CPU Vendor: %s",
            vendor.value,
        )

    # ======================================================
    # Intel VT-x / AMD-V
    # ======================================================

    def _detect_cpu_virtualization(self) -> None:

        logger.info(
            "Checking CPU virtualization..."
        )

        supported = False

        try:

            if self.is_windows():

                result = self._run(
                    [
                        "systeminfo",
                    ]
                )

                output = result.stdout.lower()

                supported = (
                    "virtualization enabled in firmware"
                    in output
                    or "vm monitor mode extensions"
                    in output
                )

            else:

                result = self._run(
                    [
                        "lscpu",
                    ]
                )

                output = result.stdout.lower()

                supported = (
                    "vmx" in output
                    or "svm" in output
                )

        except Exception:

            logger.exception(
                "Unable to detect CPU virtualization."
            )

        self._status.cpu_virtualization_supported = supported

        self._status.virtualization = (
            VirtualizationState.ENABLED
            if supported
            else VirtualizationState.UNSUPPORTED
        )

    # ======================================================
    # Intel VT-d / AMD IOMMU
    # ======================================================

    def _detect_iommu(self) -> None:

        logger.info(
            "Checking IOMMU support..."
        )

        supported = False

        try:

            if self.is_windows():

                result = self._run(
                    [
                        "powershell",
                        "-Command",
                        "Get-ComputerInfo",
                    ]
                )

                output = result.stdout.lower()

                supported = (
                    "dma remapping"
                    in output
                )

            else:

                result = self._run(
                    [
                        "dmesg",
                    ]
                )

                output = result.stdout.lower()

                supported = (
                    "iommu" in output
                    or "amd-vi" in output
                    or "intel-iommu" in output
                )

        except Exception:

            logger.exception(
                "Unable to detect IOMMU."
            )

        self._status.iommu_supported = supported

        self._status.iommu = (
            VirtualizationState.ENABLED
            if supported
            else VirtualizationState.UNSUPPORTED
        )

    # ======================================================
    # Second Level Address Translation
    # ======================================================

    def _detect_slat(self) -> None:

        logger.info(
            "Checking SLAT support..."
        )

        supported = False

        try:

            if self.is_windows():

                result = self._run(
                    [
                        "systeminfo",
                    ]
                )

                output = result.stdout.lower()

                supported = (
                    "second level address translation"
                    in output
                )

            else:

                result = self._run(
                    [
                        "lscpu",
                    ]
                )

                output = result.stdout.lower()

                supported = (
                    "ept" in output
                    or "npt" in output
                )

        except Exception:

            logger.exception(
                "Unable to detect SLAT."
            )

        self._status.slat_supported = supported

        self._status.slat = (
            VirtualizationState.ENABLED
            if supported
            else VirtualizationState.UNSUPPORTED
        )

    # ======================================================
    # Nested Virtualization
    # ======================================================

    def _detect_nested_virtualization(self) -> None:

        logger.info(
            "Checking nested virtualization..."
        )

        supported = False

        try:

            if self.is_linux():

                intel = (
                    "/sys/module/kvm_intel/parameters/nested"
                )

                amd = (
                    "/sys/module/kvm_amd/parameters/nested"
                )

                for file in (intel, amd):

                    try:

                        with open(file, "r") as f:

                            value = (
                                f.read()
                                .strip()
                                .lower()
                            )

                            if value in (
                                "1",
                                "y",
                                "yes",
                            ):

                                supported = True
                                break

                    except FileNotFoundError:
                        continue

            elif self.is_windows():

                result = self._run(
                    [
                        "systeminfo",
                    ]
                )

                output = result.stdout.lower()

                supported = (
                    "hyper-v requirements"
                    in output
                )

        except Exception:

            logger.exception(
                "Unable to determine nested virtualization."
            )

        self._status.nested_supported = supported

        self._status.nested_virtualization = (
            VirtualizationState.ENABLED
            if supported
            else VirtualizationState.UNKNOWN
        )

    # ======================================================
    # Hypervisor Detection
    # ======================================================

    def _detect_hypervisor(self) -> None:

        logger.info(
            "Detecting installed hypervisor..."
        )

        hypervisor = HypervisorType.NONE

        try:

            if self.is_linux():

                result = self._run(
                    [
                        "systemd-detect-virt",
                    ]
                )

                output = (
                    result.stdout
                    .strip()
                    .lower()
                )

                if output == "kvm":

                    hypervisor = HypervisorType.KVM

                elif output == "oracle":

                    hypervisor = HypervisorType.VIRTUALBOX

                elif output == "vmware":

                    hypervisor = HypervisorType.VMWARE

                elif output == "xen":

                    hypervisor = HypervisorType.XEN

            elif self.is_windows():

                result = self._run(
                    [
                        "systeminfo",
                    ]
                )

                output = result.stdout.lower()

                if "hyper-v requirements" in output:

                    hypervisor = HypervisorType.HYPER_V

        except Exception:

            logger.exception(
                "Unable to detect hypervisor."
            )

        self._status.hypervisor = hypervisor

        logger.info(
            "Detected hypervisor: %s",
            hypervisor.value,
        )

    # ======================================================
    # BIOS Integration
    # ======================================================

    def enable_virtualization(self) -> bool:
        """
        Enable Intel VT-x / AMD-V through the active BIOS
        provider.
        """

        logger.info("Enabling CPU virtualization...")

        provider = self._bios.provider

        if not provider.virtualization_supported():
            self._add_warning(
                "Virtualization is not supported by this firmware."
            )
            return False

        success = provider.enable_virtualization()

        if success:
            self._status.bios_virtualization_enabled = True
            self._status.virtualization = VirtualizationState.ENABLED

        return success

    def disable_virtualization(self) -> bool:
        """
        Disable Intel VT-x / AMD-V.
        """

        logger.info("Disabling CPU virtualization...")

        provider = self._bios.provider

        if not provider.virtualization_supported():
            return False

        success = provider.disable_virtualization()

        if success:
            self._status.bios_virtualization_enabled = False
            self._status.virtualization = VirtualizationState.DISABLED

        return success

    # ======================================================
    # IOMMU
    # ======================================================

    def enable_iommu(self) -> bool:
        """
        Enable Intel VT-d / AMD IOMMU.
        """

        logger.info("Enabling IOMMU...")

        provider = self._bios.provider

        if not provider.iommu_supported():
            self._add_warning(
                "IOMMU is not supported by this firmware."
            )
            return False

        success = provider.enable_iommu()

        if success:
            self._status.bios_iommu_enabled = True
            self._status.iommu = VirtualizationState.ENABLED

        return success

    def disable_iommu(self) -> bool:
        """
        Disable Intel VT-d / AMD IOMMU.
        """

        logger.info("Disabling IOMMU...")

        provider = self._bios.provider

        if not provider.iommu_supported():
            return False

        success = provider.disable_iommu()

        if success:
            self._status.bios_iommu_enabled = False
            self._status.iommu = VirtualizationState.DISABLED

        return success

    # ======================================================
    # SR-IOV
    # ======================================================

    def enable_sriov(self) -> bool:
        """
        Enable SR-IOV if supported.
        """

        logger.info("Enabling SR-IOV...")

        provider = self._bios.provider

        if not provider.sriov_supported():
            self._add_warning(
                "SR-IOV is not supported."
            )
            return False

        success = provider.enable_sriov()

        if success:
            self._status.sriov_supported = True
            self._status.sriov = VirtualizationState.ENABLED

        return success

    def disable_sriov(self) -> bool:
        """
        Disable SR-IOV.
        """

        logger.info("Disabling SR-IOV...")

        provider = self._bios.provider

        if not provider.sriov_supported():
            return False

        success = provider.disable_sriov()

        if success:
            self._status.sriov = VirtualizationState.DISABLED

        return success

    # ======================================================
    # TPM
    # ======================================================

    def enable_tpm(self) -> bool:
        """
        Enable TPM.
        """

        logger.info("Enabling TPM...")

        provider = self._bios.provider

        if not provider.tpm_supported():
            self._add_warning(
                "TPM is not supported."
            )
            return False

        success = provider.enable_tpm()

        if success:
            self._status.tpm = VirtualizationState.ENABLED

        return success

    def disable_tpm(self) -> bool:
        """
        Disable TPM.
        """

        logger.info("Disabling TPM...")

        provider = self._bios.provider

        if not provider.tpm_supported():
            return False

        success = provider.disable_tpm()

        if success:
            self._status.tpm = VirtualizationState.DISABLED

        return success

    # ======================================================
    # Secure Boot
    # ======================================================

    def enable_secure_boot(self) -> bool:
        """
        Enable Secure Boot.
        """

        logger.info("Enabling Secure Boot...")

        provider = self._bios.provider

        if not provider.secure_boot_supported():
            self._add_warning(
                "Secure Boot is not supported."
            )
            return False

        success = provider.enable_secure_boot()

        if success:
            self._status.secure_boot = (
                VirtualizationState.ENABLED
            )

        return success

    def disable_secure_boot(self) -> bool:
        """
        Disable Secure Boot.
        """

        logger.info("Disabling Secure Boot...")

        provider = self._bios.provider

        if not provider.secure_boot_supported():
            return False

        success = provider.disable_secure_boot()

        if success:
            self._status.secure_boot = (
                VirtualizationState.DISABLED
            )

        return success

    # ======================================================
    # Validation
    # ======================================================

    def validate(self) -> bool:
        """
        Validate the current virtualization configuration.

        Returns True if the firmware configuration is suitable
        for virtualization workloads.
        """

        logger.info(
            "Validating virtualization configuration..."
        )

        self._status.warnings.clear()

        if not self._status.cpu_virtualization_supported:
            self._add_warning(
                "CPU virtualization extensions are unavailable."
            )

        if not self._status.bios_virtualization_enabled:
            self._add_warning(
                "CPU virtualization is disabled in firmware."
            )

        if (
            self._status.iommu_supported
            and not self._status.bios_iommu_enabled
        ):
            self._add_warning(
                "IOMMU is supported but disabled."
            )

        if (
            self._status.virtualization
            != VirtualizationState.ENABLED
        ):
            return False

        return len(self._status.warnings) == 0
    
    # ======================================================
    # Proxmox Readiness
    # ======================================================

    def check_proxmox_readiness(self) -> bool:
        """
        Determine whether the current system is suitable
        for a Proxmox VE installation.
        """

        logger.info(
            "Checking Proxmox readiness..."
        )

        ready = True

        self._status.warnings.clear()
        self._status.notes.clear()

        # CPU Virtualization

        if not self._status.cpu_virtualization_supported:

            ready = False

            self._add_warning(
                "CPU virtualization extensions are unavailable."
            )

        if (
            self._status.virtualization
            != VirtualizationState.ENABLED
        ):

            ready = False

            self._add_warning(
                "Virtualization is disabled in firmware."
            )

        # IOMMU

        if self._status.iommu_supported:

            if (
                self._status.iommu
                != VirtualizationState.ENABLED
            ):

                self._add_warning(
                    "IOMMU is available but disabled."
                )

        else:

            self._add_note(
                "PCI passthrough will not be available."
            )

        # SLAT

        if not self._status.slat_supported:

            self._add_warning(
                "SLAT is unavailable. VM performance may be reduced."
            )

        # SR-IOV

        if not self._status.sriov_supported:

            self._add_note(
                "SR-IOV is unavailable."
            )

        # Secure Boot

        if (
            self._status.secure_boot
            == VirtualizationState.ENABLED
        ):

            self._add_note(
                "Secure Boot is enabled."
            )

        # TPM

        if (
            self._status.tpm
            == VirtualizationState.ENABLED
        ):

            self._add_note(
                "TPM detected."
            )

        self._status.proxmox_ready = ready

        return ready

    # ======================================================
    # Reporting
    # ======================================================

    def report(self) -> dict[str, Any]:
        """
        Produce a complete virtualization report.
        """

        return {
            "cpu_vendor":
                self._status.cpu_vendor.value,

            "virtualization":
                self._status.virtualization.value,

            "iommu":
                self._status.iommu.value,

            "slat":
                self._status.slat.value,

            "nested_virtualization":
                self._status.nested_virtualization.value,

            "sriov":
                self._status.sriov.value,

            "secure_boot":
                self._status.secure_boot.value,

            "tpm":
                self._status.tpm.value,

            "hypervisor":
                self._status.hypervisor.value,

            "cpu_virtualization_supported":
                self._status.cpu_virtualization_supported,

            "iommu_supported":
                self._status.iommu_supported,

            "slat_supported":
                self._status.slat_supported,

            "nested_supported":
                self._status.nested_supported,

            "sriov_supported":
                self._status.sriov_supported,

            "bios_virtualization_enabled":
                self._status.bios_virtualization_enabled,

            "bios_iommu_enabled":
                self._status.bios_iommu_enabled,

            "proxmox_ready":
                self._status.proxmox_ready,

            "warnings":
                list(self._status.warnings),

            "notes":
                list(self._status.notes),

            "additional_information":
                dict(
                    self._status.additional_information
                ),
        }

    def export(self) -> dict[str, Any]:
        """
        Export virtualization information for Orion
        deployment reports.
        """

        logger.info(
            "Exporting virtualization report..."
        )

        return self.report()

    # ======================================================
    # Refresh
    # ======================================================

    def refresh(self) -> bool:
        """
        Refresh every virtualization capability.
        """

        logger.info(
            "Refreshing virtualization status..."
        )

        self.initialize()

        self.detect_hardware()

        self.check_proxmox_readiness()

        return True

    # ======================================================
    # Helper Methods
    # ======================================================

    def virtualization_enabled(self) -> bool:

        return (
            self._status.virtualization
            == VirtualizationState.ENABLED
        )

    def iommu_enabled(self) -> bool:

        return (
            self._status.iommu
            == VirtualizationState.ENABLED
        )

    def slat_enabled(self) -> bool:

        return (
            self._status.slat
            == VirtualizationState.ENABLED
        )

    def nested_virtualization_enabled(self) -> bool:

        return (
            self._status.nested_virtualization
            == VirtualizationState.ENABLED
        )

    def secure_boot_enabled(self) -> bool:

        return (
            self._status.secure_boot
            == VirtualizationState.ENABLED
        )

    def tpm_enabled(self) -> bool:

        return (
            self._status.tpm
            == VirtualizationState.ENABLED
        )

    def current_hypervisor(self) -> HypervisorType:

        return self._status.hypervisor

    def warnings(self) -> list[str]:

        return list(self._status.warnings)

    def notes(self) -> list[str]:

        return list(self._status.notes)

    # ======================================================
    # String Representation
    # ======================================================

    def __repr__(self) -> str:

        return (
            f"{self.__class__.__name__}("
            f"vendor={self._status.cpu_vendor.value!r}, "
            f"virtualization={self._status.virtualization.value!r}, "
            f"proxmox_ready={self._status.proxmox_ready!r})"
        )

    def __str__(self) -> str:

        state = (
            "Ready"
            if self._status.proxmox_ready
            else "Not Ready"
        )

        return (
            f"Virtualization Manager "
            f"({state})"
        )