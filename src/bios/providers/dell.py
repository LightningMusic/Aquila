"""Dell BIOS provider for Project Aquila.

Backend preference:

1. Dell Command | Configure (CCTK)
2. Dell Command | Monitor WMI/CIM
3. Native operating-system firmware interfaces
4. DefaultProvider behavior

Administrative passwords are never written to Aquila logs. CCTK versions that
accept passwords only through command-line arguments may still expose those
arguments to privileged operating-system process inspection. WMI is preferred
where a suitable credential-aware method is available.
"""

from __future__ import annotations

import inspect
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import tempfile
import threading
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
    cast,
)

from ..models import (
    BIOSMode,
    BIOSVendor,
    BootDevice,
    BootDeviceType,
    FirmwareInformation,
    TPMState,
)
from .default import DefaultProvider


PROVIDER_VERSION = "2.4.0"

_DELL_WMI_NAMESPACES: Tuple[str, ...] = (
    r"root\dcim\sysman",
    r"root\dell\sysman",
)

_CCTK_NAMES: Tuple[str, ...] = (
    "cctk.exe",
    "cctk",
)

_CCTK_PATHS: Tuple[Path, ...] = (
    Path(r"C:\Program Files (x86)\Dell\Command Configure\X86_64\cctk.exe"),
    Path(r"C:\Program Files\Dell\Command Configure\X86_64\cctk.exe"),
    Path(r"C:\Program Files (x86)\Dell\CCTK\X86_64\cctk.exe"),
    Path("/opt/dell/dcc/cctk"),
    Path("/opt/dell/toolkit/bin/cctk"),
    Path("/usr/bin/cctk"),
    Path("/usr/sbin/cctk"),
)

_SECRET_OPTION_NAMES: Tuple[str, ...] = (
    "--adminpw",
    "--adminpwd",
    "--systempw",
    "--syspwd",
    "--hddpw",
    "--hddpwd",
    "--val-adminpw",
    "--valadminpw",
    "--valadminpwd",
    "--val-systempw",
    "--valsyspwd",
    "--val-hddpw",
    "--valhddpwd",
)

_TRUE_VALUES: Set[str] = {
    "1",
    "active",
    "activate",
    "activated",
    "enable",
    "enabled",
    "on",
    "present",
    "set",
    "true",
    "yes",
}

_FALSE_VALUES: Set[str] = {
    "0",
    "clear",
    "deactivate",
    "deactivated",
    "disable",
    "disabled",
    "false",
    "none",
    "not set",
    "off",
    "no",
}

_PROFILE_NAMES: Dict[str, str] = {
    "standard": "Standard",
    "expresscharge": "ExpressCharge",
    "express": "ExpressCharge",
    "adaptive": "Adaptive",
    "custom": "Custom",
    "primarilyac": "PrimarilyAC",
    "primarily ac": "PrimarilyAC",
}

_THERMAL_PROFILES: Dict[str, str] = {
    "optimized": "Optimized",
    "cool": "Cool",
    "quiet": "Quiet",
    "ultraperformance": "UltraPerformance",
    "ultra performance": "UltraPerformance",
}

_WAKE_STATES: Dict[str, str] = {
    "disabled": "Disabled",
    "lanorwlan": "LANorWLAN",
    "lan or wlan": "LANorWLAN",
    "lanonly": "LANOnly",
    "lan only": "LANOnly",
    "lanwithpxeboot": "LANwithPXEBoot",
    "lan with pxe boot": "LANwithPXEBoot",
}

_AC_RECOVERY_STATES: Dict[str, str] = {
    "off": "Off",
    "on": "On",
    "last": "Last",
    "laststate": "Last",
    "last state": "Last",
}


class DellProvider(DefaultProvider):
    """Production Dell firmware provider."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize provider state without opening privileged resources."""
        super().__init__(*args, **kwargs)
        self._dell_logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}"
        )
        self._cctk_path: Optional[Path] = None
        self._wmi_namespace: Optional[str] = None
        self._wmi_handles: Dict[str, Any] = {}
        self._sysfs_root: Optional[Path] = None
        self._temporary_files: Set[Path] = set()
        self._attribute_cache: Dict[str, Any] = {}
        self._credential_buffers: List[bytearray] = []
        self._execution_lock = threading.RLock()
        self._connected = False
        self._closed = False

    # ------------------------------------------------------------------
    # Identity, detection, and lifecycle
    # ------------------------------------------------------------------

    def vendor(self) -> BIOSVendor:
        """Return the Dell vendor identifier."""
        return BIOSVendor.DELL

    def provider_name(self) -> str:
        """Return the stable provider name."""
        return "dell"

    def provider_version(self) -> str:
        """Return the Dell provider implementation version."""
        return PROVIDER_VERSION

    def detect(self) -> bool:
        """Return whether this system is confidently identified as Dell."""
        return self.detection_confidence() >= 0.8

    def detection_confidence(self) -> float:
        """Calculate a confidence score from independent Dell indicators."""
        manufacturer = self._system_value(
            "sys_vendor",
            "Manufacturer",
        )
        product = self._system_value(
            "product_name",
            "Model",
        )
        combined = f"{manufacturer} {product}".strip().lower()

        hypervisor_markers = (
            "qemu",
            "kvm",
            "vmware",
            "virtualbox",
            "xen",
            "hyper-v",
            "microsoft corporation virtual machine",
        )
        if any(marker in combined for marker in hypervisor_markers):
            return 0.0

        score = 0.0
        normalized_vendor = re.sub(r"[^a-z0-9]+", " ", manufacturer.lower())
        if normalized_vendor.strip() in {
            "dell",
            "dell inc",
            "dell computer corporation",
        }:
            score += 0.55
        elif re.search(r"\bdell\b", normalized_vendor):
            score += 0.45

        if self._has_dell_pci_vendor():
            score += 0.15

        service_tag = self._system_value(
            "product_serial",
            "SerialNumber",
        )
        if self._valid_service_tag(service_tag):
            score += 0.10

        cctk = self._locate_cctk()
        if cctk is not None:
            result = self._run_process(
                [str(cctk), "--version"],
                timeout=15.0,
            )
            version_text = f"{result[1]} {result[2]}".lower()
            if result[0] == 0 or "command configure" in version_text:
                score += 0.10

        if self._wmi_class_exists("DCIM_SystemView"):
            score += 0.10

        return min(score, 1.0)

    def connect(self) -> bool:
        """Discover and validate all available Dell management backends."""
        with self._execution_lock:
            if self._connected and self.is_connected():
                return True

            self._closed = False
            self._cctk_path = self._locate_cctk()

            dmi_root = Path("/sys/class/dmi/id")
            self._sysfs_root = dmi_root if dmi_root.is_dir() else None

            self._wmi_namespace = None
            if platform.system() == "Windows":
                for namespace in _DELL_WMI_NAMESPACES:
                    try:
                        rows = self._query_wmi(
                            namespace,
                            "SELECT * FROM DCIM_SystemView",
                        )
                    except Exception as exc:
                        self._dell_logger.debug(
                            "Dell WMI namespace unavailable: %s: %s",
                            namespace,
                            self._sanitize_text(str(exc)),
                        )
                        continue

                    self._wmi_namespace = namespace
                    if rows or self._wmi_namespace:
                        break

            cctk_ready = False
            if self._cctk_path is not None:
                code, stdout, stderr = self._run_cctk(["--version"])
                version_text = f"{stdout} {stderr}".lower()
                cctk_ready = (
                    code == 0
                    or "command configure" in version_text
                    or "cctk" in version_text
                )

            native_ready = self._sysfs_root is not None
            if platform.system() == "Windows":
                native_ready = bool(
                    self._query_wmi_safe(
                        r"root\cimv2",
                        "SELECT Manufacturer FROM Win32_ComputerSystem",
                    )
                )

            self._connected = bool(
                cctk_ready or self._wmi_namespace or native_ready
            )
            self._attribute_cache.clear()

            return self._connected

    def disconnect(self) -> None:
        """Release backends and securely discard transient provider state."""
        with self._execution_lock:
            self._remove_temporary_files()
            self._clear_credentials()
            self._attribute_cache.clear()
            self._wmi_handles.clear()
            self._wmi_namespace = None
            self._sysfs_root = None
            self._cctk_path = None
            self._connected = False

    def is_connected(self) -> bool:
        """Return whether at least one configured backend remains usable."""
        if not self._connected:
            return False

        if self._cctk_path is not None and self._cctk_path.is_file():
            return True

        if self._wmi_namespace is not None:
            return True

        if self._sysfs_root is not None and self._sysfs_root.is_dir():
            return True

        if platform.system() == "Windows":
            return bool(
                self._query_wmi_safe(
                    r"root\cimv2",
                    "SELECT Manufacturer FROM Win32_ComputerSystem",
                )
            )

        return False

    def refresh(self) -> bool:
        """Invalidate cached Dell attributes and force future live queries."""
        with self._execution_lock:
            self._attribute_cache.clear()
            try:
                parent_result = super().refresh()
            except (NotImplementedError, AttributeError):
                parent_result = True

            return bool(parent_result)

    # ------------------------------------------------------------------
    # Firmware inventory
    # ------------------------------------------------------------------

    def firmware_information(self) -> FirmwareInformation:
        """Return consolidated Dell firmware and hardware inventory."""
        if "firmware_information" in self._attribute_cache:
            cached = self._attribute_cache["firmware_information"]
            if isinstance(cached, FirmwareInformation):
                return cached

        system_rows = self._dell_wmi_rows("DCIM_SystemView")
        bios_rows = self._dell_wmi_rows("DCIM_BIOSElement")

        manufacturer = self._first_value(
            system_rows,
            ("Manufacturer", "SystemManufacturer"),
        ) or self._system_value("sys_vendor", "Manufacturer")
        model = self._first_value(
            system_rows,
            ("Model", "SystemModel", "ElementName"),
        ) or self._system_value("product_name", "Model")
        service_tag = self._first_value(
            system_rows,
            ("ServiceTag", "SerialNumber"),
        ) or self._system_value("product_serial", "SerialNumber")
        sku = self._first_value(
            system_rows,
            ("SystemSKU", "SKU", "SystemID"),
        ) or self._system_value("product_sku", "SystemSKUNumber")

        bios_version = self._first_value(
            bios_rows,
            ("Version", "BIOSVersion", "SMBIOSBIOSVersion"),
        )
        if not bios_version:
            bios_version = self._query_attribute(
                "biosver",
                aliases=("biosversion",),
            )
        if not bios_version:
            bios_version = self._system_value(
                "bios_version",
                "SMBIOSBIOSVersion",
                wmi_class="Win32_BIOS",
            )

        release_date = self._first_value(
            bios_rows,
            ("ReleaseDate", "BIOSReleaseDate"),
        )
        if not release_date:
            release_date = self._system_value(
                "bios_date",
                "ReleaseDate",
                wmi_class="Win32_BIOS",
            )

        asset_tag = self.get_asset_tag()
        ownership_tag = self.get_ownership_tag()

        revision = self._first_value(
            bios_rows,
            ("Revision", "BIOSRevision"),
        )
        rom_size = self._first_value(
            bios_rows,
            ("ROMSize", "Size"),
        )
        express_service_code = self._first_value(
            system_rows,
            ("ExpressServiceCode",),
        ) or self._service_tag_to_express_code(service_tag)
        board_revision = self._system_value(
            "board_version",
            "Version",
            wmi_class="Win32_BaseBoard",
        )
        chassis_type = self._first_value(
            system_rows,
            ("ChassisType", "SystemType"),
        )
        ec_version = self._query_first_attribute(
            ("embsataraid", "ecversion", "embeddedcontrollerversion")
        )
        me_version = self._query_first_attribute(
            ("meversion", "intelmeversion", "manageabilityengineversion")
        )
        pd_version = self._query_first_attribute(
            ("powerdeliveryversion", "pdversion", "typecpdversion")
        )
        supportassist_version = self._query_first_attribute(
            ("supportassistversion", "supportassistosrcvrversion")
        )

        gpu_vbios = self._gpu_vbios_versions()

        collected_at = datetime.now().astimezone()
        release = self._normalize_firmware_date(release_date)

        extensions: Dict[str, Any] = {
            "bios_revision": revision,
            "rom_size": rom_size,
            "service_tag": service_tag,
            "express_service_code": express_service_code,
            "asset_tag": asset_tag,
            "ownership_tag": ownership_tag,
            "board_revision": board_revision,
            "chassis_type": chassis_type,
            "management_engine_version": me_version,
            "power_delivery_firmware_version": pd_version,
            "supportassist_os_recovery_version": supportassist_version,
            "gpu_vbios_versions": gpu_vbios,
            "backend": self._active_backend_name(),
        }

        information = FirmwareInformation(
            vendor=BIOSVendor.DELL,
            mode=self.get_boot_mode(),
            firmware_interface=self._active_backend_name(),
            manufacturer=manufacturer or "Dell Inc.",
            product_name=model,
            model=model,
            serial_number=service_tag,
            system_uuid=self._system_value("product_uuid", "UUID"),
            sku=sku,
            bios_vendor=self._system_value(
                "bios_vendor",
                "Manufacturer",
                wmi_class="Win32_BIOS",
            ) or "Dell Inc.",
            bios_version=bios_version,
            bios_release_date=release,
            embedded_controller_version=ec_version,
            collected_at=collected_at,
            extensions=extensions,
            raw_data={
                "system_view": [
                    self._object_to_dict(row) for row in system_rows
                ],
                "bios_elements": [
                    self._object_to_dict(row) for row in bios_rows
                ],
            },
        )
        self._attribute_cache["firmware_information"] = information
        return information

    # ------------------------------------------------------------------
    # Boot management
    # ------------------------------------------------------------------

    def boot_order(self) -> List[BootDevice]:
        """Return the configured Dell boot order."""
        code, stdout, _ = self._run_cctk(["--bootorder"])
        if code == 0 and stdout.strip():
            devices = self._parse_boot_order(stdout)
            if devices:
                return devices

        rows = self._dell_wmi_rows("DCIM_BootConfigSetting")
        devices: List[BootDevice] = []
        for index, row in enumerate(rows):
            data = self._object_to_dict(row)
            name = self._mapping_value(
                data,
                ("ElementName", "InstanceID", "BootSource"),
            )
            if not name:
                continue

            identifier = self._mapping_value(
                data,
                ("InstanceID", "BootSource", "ElementName"),
            )
            enabled = self._coerce_bool(
                self._mapping_value(
                    data,
                    ("EnabledState", "IsEnabled", "Enabled"),
                ),
                default=True,
            )
            path = self._mapping_value(
                data,
                ("BootString", "DevicePath", "UEFIDevicePath"),
            )
            devices.append(
                BootDevice(
                    identifier=identifier or str(index),
                    name=name,
                    device_type=self._boot_device_type(name, path),
                    enabled=enabled,
                    priority=index,
                    path=path or None,
                    metadata={"source": "dell-wmi"},
                )
            )

        if devices:
            return devices

        try:
            return list(super().boot_order())
        except (NotImplementedError, AttributeError):
            return []

    def set_boot_order(
        self,
        devices: Sequence[Union[BootDevice, str]],
    ) -> bool:
        """Set the persistent Dell boot order."""
        names: List[str] = []
        for device in devices:
            if isinstance(device, BootDevice):
                names.append(device.identifier or device.name)
            else:
                normalized = str(device).strip()
                if normalized:
                    names.append(normalized)

        if not names:
            return False

        value = ",".join(names)
        if self._set_attribute("bootorder", value):
            self.refresh()
            return True

        return self._wmi_change_boot_order(names)

    def add_boot_device(self, device: BootDevice) -> bool:
        """Add a Dell UEFI boot entry."""
        name = device.name.strip()
        path = (device.path or "").strip()

        device_type_value = getattr(
            device.device_type,
            "value",
            device.device_type.name,
        )
        device_type = str(device_type_value).strip() or "UEFI"

        if not name or not path:
            return False

        value = ",".join(
            (
                name,
                path,
                device_type,
                "enable" if device.enabled else "disable",
            )
        )
        code, _, _ = self._run_cctk(
            [f"--addbootdevice={value}"],
        )

        if code == 0:
            self.refresh()
            return True

        return False

    def remove_boot_device(self, device: BootDevice) -> bool:
        """Remove a Dell firmware boot entry."""
        target = (device.identifier or device.name).strip()
        if not target:
            return False

        code, _, _ = self._run_cctk(
            [f"--delbootdevice={target}"],
        )
        if code == 0:
            self.refresh()
            return True

        return False



    def restore_default_boot_order(self) -> bool:
        """Restore Dell's default firmware boot order."""
        result = self._set_attribute("bootorder", "restoredefault")
        if result:
            self.refresh()
        return result

    def current_boot_device(self) -> BootDevice:
        """Return the boot entry used for the current operating-system boot."""
        boot_number = self._read_efi_boot_number("BootCurrent")
        devices = self.boot_order()

        if boot_number is not None:
            candidates = {
                f"boot{boot_number:04x}",
                f"{boot_number:04x}",
                str(boot_number),
            }

            for device in devices:
                identifier = device.identifier.casefold()
                if identifier in candidates or any(
                    candidate in identifier
                    for candidate in candidates
                ):
                    return device

        try:
            return super().current_boot_device()
        except (NotImplementedError, AttributeError):
            if devices:
                return devices[0]

            return self._unknown_boot_device()


    def next_boot_device(self) -> Optional[BootDevice]:
        """Return the configured Dell one-time boot target."""
        value = self._query_attribute(
            "val-onetimeboot",
            aliases=("onetimeboot", "bootnext"),
        )
        if not value or self._normalized(value) in {
            "",
            "clear",
            "disabled",
            "none",
            "not set",
        }:
            boot_number = self._read_efi_boot_number("BootNext")
            if boot_number is None:
                return None
            value = f"Boot{boot_number:04X}"
        devices = self.boot_order()
        normalized = self._normalized(value)
        for device in devices:
            identifiers = {
                self._normalized(device.identifier),
                self._normalized(device.name),
            }
            if normalized in identifiers or any(
                candidate and candidate in normalized
                for candidate in identifiers
            ):
                return device

        return BootDevice(
            identifier=value,
            name=value,
            device_type=self._boot_device_type(value, ""),
            enabled=True,
            priority=0,
            path=None,
            metadata={"source": "dell-onetimeboot"},
        )

    def set_next_boot_device(
        self,
        device: Union[BootDevice, str],
    ) -> bool:
        """Configure a Dell one-time boot target."""
        if isinstance(device, BootDevice):
            target = device.identifier or device.name
        else:
            target = device.strip()

        if not target:
            return False

        return self._set_attribute("val-onetimeboot", target)


    def clear_next_boot_device(self) -> bool:
        """Clear the Dell one-time boot target."""
        return self._set_attribute("val-onetimeboot", "clear")

    def get_boot_mode(self) -> BIOSMode:
        """Return the configured Dell boot mode."""
        value = self._query_attribute(
            "bootmode",
            aliases=("bootlist", "uefiboot"),
        )
        normalized = self._normalized(value)

        if "uefi" in normalized:
            return BIOSMode.UEFI
        if "legacy" in normalized or "bios" in normalized:
            return BIOSMode.LEGACY

        if Path("/sys/firmware/efi").exists():
            return BIOSMode.UEFI

        try:
            return super().bios_mode()
        except (NotImplementedError, AttributeError):
            return BIOSMode.LEGACY

    def set_boot_mode(self, mode: BIOSMode) -> bool:
        """Set the Dell firmware boot mode."""
        if mode == BIOSMode.UEFI:
            if not self._set_attribute("bootmode", "uefi"):
                return False
            self._set_attribute("legacyorom", "disable")
            return True

        if mode == BIOSMode.LEGACY:
            if not self._set_attribute("bootmode", "legacy"):
                return False
            self._set_attribute("legacyorom", "enable")
            return True

        return False

    def get_supportassist_os_recovery(self) -> bool:
        """Return whether SupportAssist OS Recovery is enabled."""
        return self._query_boolean_attribute(
            "supportassistosrcvr",
            aliases=("supportassistosrecovery",),
        )

    def set_supportassist_os_recovery(self, enabled: bool) -> bool:
        """Enable or disable SupportAssist OS Recovery."""
        return self._set_boolean_attribute(
            "supportassistosrcvr",
            enabled,
        )

    def get_biosconnect_status(self) -> bool:
        """Return whether Dell BIOSConnect is enabled."""
        return self._query_boolean_attribute("biosconnect")

    def set_biosconnect(self, enabled: bool) -> bool:
        """Enable or disable Dell BIOSConnect."""
        return self._set_boolean_attribute("biosconnect", enabled)

    # ------------------------------------------------------------------
    # Virtualization and hardware security
    # ------------------------------------------------------------------

    def vt_x_supported(self) -> bool:
        """Return whether the processor supports VT-x or AMD-V."""
        flags = self._cpu_flags()
        if {"vmx", "svm"} & flags:
            return True

        return self._wmi_bios_attribute_exists(
            ("virtualization", "virtualizationtechnology", "vt")
        )

    def vt_x_enabled(self) -> bool:
        """Return whether processor virtualization is enabled."""
        return self._query_boolean_attribute(
            "virtualization",
            aliases=("virtualizationtechnology", "vt"),
        )

    def set_vt_x(self, enable: bool) -> bool:
        """Enable or disable processor virtualization."""
        return self._set_boolean_attribute("virtualization", enable)

    def vt_d_supported(self) -> bool:
        """Return whether IOMMU or VT-d support is available."""
        if Path("/sys/kernel/iommu_groups").is_dir():
            return True

        if Path("/sys/class/iommu").is_dir():
            return True

        dmesg = self._native_command_output(
            ["dmesg"],
            timeout=8.0,
        ).lower()
        if any(
            marker in dmesg
            for marker in ("dmar:", "iommu", "amd-vi")
        ):
            return True

        return self._wmi_bios_attribute_exists(
            ("vt-d", "vtd", "iommu", "directedio")
        )

    def vt_d_enabled(self) -> bool:
        """Return whether Dell VT-d is enabled."""
        return self._query_boolean_attribute(
            "vt-d",
            aliases=("vtd", "directedio", "iommu"),
        )

    def set_vt_d(self, enable: bool) -> bool:
        """Enable or disable Dell VT-d."""
        return self._set_boolean_attribute("vt-d", enable)

    def sriov_enabled(self) -> bool:
        """Return whether SR-IOV is enabled in firmware."""
        return self._query_boolean_attribute(
            "sriov",
            aliases=("sriovglobalenable",),
        )

    def set_sriov(self, enable: bool) -> bool:
        """Enable or disable SR-IOV."""
        return self._set_boolean_attribute("sriov", enable)

    def dma_remapping_enabled(self) -> bool:
        """Return whether DMA remapping is enabled."""
        return self._query_boolean_attribute(
            "dmaremapping",
            aliases=("dmaremap",),
        )

    def set_dma_remapping(self, enable: bool) -> bool:
        """Enable or disable DMA remapping."""
        return self._set_boolean_attribute("dmaremapping", enable)

    def tpm_state(self) -> TPMState:
        """Return consolidated Dell TPM state."""
        rows = self._dell_wmi_rows("DCIM_TPMBIOSElement")
        data = self._object_to_dict(rows[0]) if rows else {}

        present = bool(rows)
        enabled = self._coerce_bool(
            self._mapping_value(
                data,
                ("EnabledState", "Enabled", "TPMEnabled"),
            ),
            default=self._query_boolean_attribute(
                "tpm",
                aliases=("tpmsecurity",),
            ),
        )
        activated = self._coerce_bool(
            self._mapping_value(
                data,
                ("Activated", "TPMActivated", "ActivationState"),
            ),
            default=self._query_boolean_attribute("tpmactivation"),
        )
        owned = self._coerce_bool(
            self._mapping_value(
                data,
                ("Owned", "TPMOwned", "OwnershipState"),
            ),
            default=False,
        )

        spec_version = self._mapping_value(
            data,
            ("SpecVersion", "Version", "TPMVersion"),
        )
        if not spec_version:
            spec_version = self._native_tpm_version()
        if spec_version:
            present = True

        values: Dict[str, Any] = {
            "present": present,
            "enabled": enabled,
            "activated": activated,
            "owned": owned,
            "spec_version": spec_version or "",
            "version": spec_version or "",
            "manufacturer": self._mapping_value(
                data,
                ("Manufacturer", "ManufacturerName"),
            ),
            "metadata": data,
        }
        return self._construct_model(TPMState, values)

    def enable_tpm(self) -> bool:
        """Enable and activate the Dell TPM."""
        if not self._set_attribute("tpm", "on"):
            return False
        return self._set_attribute("tpmactivation", "activate")

    def disable_tpm(self) -> bool:
        """Disable the Dell TPM."""
        return self._set_attribute("tpm", "off")

    def clear_tpm(self, password: Optional[str] = None) -> bool:
        """Request TPM clearing after validating the BIOS password."""
        if password and not self.verify_admin_password(password):
            return False

        return self._set_attribute(
            "tpmclear",
            "enable",
            admin_password=password,
        )

    def secure_boot_enabled(self) -> bool:
        """Return whether Secure Boot is enabled."""
        return self._query_boolean_attribute("secureboot")

    def set_secure_boot(self, enable: bool) -> bool:
        """Enable or disable Secure Boot."""
        return self._set_boolean_attribute("secureboot", enable)

    def get_secure_boot_mode(self) -> str:
        """Return the Dell Secure Boot operating mode."""
        value = self._query_attribute("securebootmode")
        return value or "Unknown"

    def chassis_intrusion_detected(self) -> bool:
        """Return whether chassis intrusion has been detected."""
        value = self._query_attribute("chassisintrusion")
        normalized = self._normalized(value)
        return any(
            marker in normalized
            for marker in ("detected", "tripped", "intruded", "alert")
        ) and not any(
            marker in normalized
            for marker in ("not detected", "clear", "normal")
        )

    def reset_chassis_intrusion(self) -> bool:
        """Clear the chassis-intrusion status."""
        return self._set_attribute("chassisintrusion", "clear")

    def get_computrace_status(self) -> str:
        """Return Absolute Persistence/Computrace status."""
        value = self._query_attribute("computrace")
        return value or "Unknown"

    def get_intel_boot_guard_status(self) -> Dict[str, Any]:
        """Return Intel Boot Guard status reported by Dell WMI."""
        queries = (
            "SELECT * FROM DCIM_BIOSElement",
            "SELECT * FROM DCIM_SoftwareIdentity",
        )
        result: Dict[str, Any] = {
            "supported": False,
            "enabled": False,
            "verified_boot": False,
            "measured_boot": False,
            "policy": "Unknown",
            "source": None,
        }

        for query in queries:
            rows = self._dell_wmi_query(query)
            for row in rows:
                data = self._object_to_dict(row)
                searchable = json.dumps(data, default=str).lower()
                if "boot guard" not in searchable and "bootguard" not in searchable:
                    continue

                result["supported"] = True
                result["source"] = "dell-wmi"
                result["enabled"] = self._coerce_bool(
                    self._mapping_value(
                        data,
                        ("Enabled", "EnabledState", "CurrentValue"),
                    ),
                    default=True,
                )
                result["verified_boot"] = self._coerce_bool(
                    self._mapping_value(
                        data,
                        ("VerifiedBoot", "VerificationEnabled"),
                    ),
                    default="verified" in searchable,
                )
                result["measured_boot"] = self._coerce_bool(
                    self._mapping_value(
                        data,
                        ("MeasuredBoot", "MeasurementEnabled"),
                    ),
                    default="measured" in searchable,
                )
                result["policy"] = self._mapping_value(
                    data,
                    ("Policy", "CurrentValue", "ElementName"),
                ) or "Unknown"
                result["raw"] = data
                return result

        value = self._query_first_attribute(
            ("bootguard", "intelbootguard")
        )
        if value:
            result.update(
                {
                    "supported": True,
                    "enabled": self._coerce_bool(value, default=True),
                    "policy": value,
                    "source": "cctk",
                }
            )

        return result

    def is_admin_password_set(self) -> bool:
        """Return whether a BIOS administrator password is configured."""
        return self._password_is_set("adminpw")

    def is_system_password_set(self) -> bool:
        """Return whether a system password is configured."""
        return self._password_is_set("systempw")

    def is_drive_password_set(self) -> bool:
        """Return whether an HDD or NVMe password is configured."""
        return self._password_is_set("hddpw")

    def verify_admin_password(self, password: str) -> bool:
        """Validate a BIOS administrator password non-destructively."""
        if not password:
            return not self.is_admin_password_set()

        code, _, _ = self._run_cctk(
            ["--biosver"],
            admin_password=password,
        )
        return code == 0

    def set_admin_password(
        self,
        current_password: Optional[str],
        new_password: str,
    ) -> bool:
        """Set or replace the Dell BIOS administrator password."""
        if not new_password:
            return False

        if self.is_admin_password_set():
            if not current_password:
                return False
            if not self.verify_admin_password(current_password):
                return False

        code, _, _ = self._run_cctk(
            [f"--adminpw={new_password}"],
            admin_password=current_password,
            secret_values=(new_password, current_password),
        )
        return code == 0

    # ------------------------------------------------------------------
    # Battery, power, wake, and thermal management
    # ------------------------------------------------------------------

    def get_battery_health(self) -> Dict[str, Any]:
        """Return Dell battery health and capacity information."""
        rows = self._dell_wmi_rows("DCIM_Battery")
        if not rows:
            rows = self._query_wmi_safe(
                r"root\cimv2",
                "SELECT * FROM Win32_Battery",
            )

        result: Dict[str, Any] = {
            "present": bool(rows),
            "health": "Unknown",
            "cycle_count": None,
            "charge_level": None,
            "design_capacity": None,
            "full_charge_capacity": None,
            "charge_profile": self.get_charge_profile(),
            "batteries": [],
        }

        for row in rows:
            data = self._object_to_dict(row)
            battery = {
                "name": self._mapping_value(
                    data,
                    ("ElementName", "Name", "DeviceID"),
                ),
                "health": self._mapping_value(
                    data,
                    ("HealthState", "BatteryHealth", "Status"),
                ),
                "cycle_count": self._coerce_int(
                    self._mapping_value(
                        data,
                        ("CycleCount", "BatteryCycleCount"),
                    )
                ),
                "charge_level": self._coerce_int(
                    self._mapping_value(
                        data,
                        (
                            "EstimatedChargeRemaining",
                            "ChargeLevel",
                            "RemainingCapacity",
                        ),
                    )
                ),
                "design_capacity": self._coerce_int(
                    self._mapping_value(
                        data,
                        ("DesignCapacity", "DesignedCapacity"),
                    )
                ),
                "full_charge_capacity": self._coerce_int(
                    self._mapping_value(
                        data,
                        (
                            "FullChargeCapacity",
                            "FullyChargedCapacity",
                        ),
                    )
                ),
            }
            result["batteries"].append(battery)

        if result["batteries"]:
            primary = result["batteries"][0]
            result.update(
                {
                    "health": primary["health"] or "Unknown",
                    "cycle_count": primary["cycle_count"],
                    "charge_level": primary["charge_level"],
                    "design_capacity": primary["design_capacity"],
                    "full_charge_capacity": primary[
                        "full_charge_capacity"
                    ],
                }
            )

        return result

    def get_charge_profile(self) -> str:
        """Return the Dell primary-battery charge profile."""
        value = self._query_attribute("primarybattchargecfg")
        if not value:
            return "Unknown"

        normalized = self._normalized(value)
        for key, profile in _PROFILE_NAMES.items():
            if key in normalized:
                return profile

        return value

    def set_charge_profile(
        self,
        profile: str,
        custom_start: Optional[int] = None,
        custom_stop: Optional[int] = None,
    ) -> bool:
        """Set the Dell primary-battery charge profile."""
        canonical = _PROFILE_NAMES.get(self._normalized(profile))
        if canonical is None:
            return False

        value = canonical
        if canonical == "Custom":
            if custom_start is None or custom_stop is None:
                return False
            if not 0 <= custom_start < custom_stop <= 100:
                return False
            value = f"Custom:{custom_start}-{custom_stop}"

        return self._set_attribute("primarybattchargecfg", value)

    def get_charge_limits(self) -> Tuple[int, int]:
        """Return custom Dell battery start and stop thresholds."""
        value = self._query_attribute("primarybattchargecfg")
        match = re.search(
            r"custom\s*[:=]?\s*(\d{1,3})\s*[-,]\s*(\d{1,3})",
            value,
            flags=re.IGNORECASE,
        )
        if not match:
            return (0, 100)

        start = max(0, min(100, int(match.group(1))))
        stop = max(0, min(100, int(match.group(2))))
        if start >= stop:
            return (0, 100)
        return (start, stop)

    def get_thermal_management_profile(self) -> str:
        """Return Dell's active thermal-management profile."""
        value = self._query_attribute("thermalmanagement")
        if not value:
            return "Unknown"

        canonical = _THERMAL_PROFILES.get(self._normalized(value))
        return canonical or value

    def set_thermal_management_profile(self, profile: str) -> bool:
        """Set Dell's thermal-management profile."""
        canonical = _THERMAL_PROFILES.get(self._normalized(profile))
        if canonical is None:
            return False
        return self._set_attribute("thermalmanagement", canonical)

    def get_wake_on_lan(self) -> str:
        """Return Dell Wake-on-LAN configuration."""
        value = self._query_attribute("wakeonlan")
        if not value:
            return "Unknown"

        canonical = _WAKE_STATES.get(self._normalized(value))
        return canonical or value

    def set_wake_on_lan(self, state: str) -> bool:
        """Set Dell Wake-on-LAN behavior."""
        canonical = _WAKE_STATES.get(self._normalized(state))
        if canonical is None:
            return False
        return self._set_attribute("wakeonlan", canonical)

    def get_ac_recovery(self) -> str:
        """Return Dell AC-power recovery behavior."""
        value = self._query_attribute("acrecovery")
        if not value:
            return "Unknown"

        canonical = _AC_RECOVERY_STATES.get(self._normalized(value))
        return canonical or value

    def set_ac_recovery(self, state: str) -> bool:
        """Set Dell AC-power recovery behavior."""
        canonical = _AC_RECOVERY_STATES.get(self._normalized(state))
        if canonical is None:
            return False
        return self._set_attribute("acrecovery", canonical)

    def configure_wake_sources(
        self,
        rtc: Optional[bool] = None,
        usb: Optional[bool] = None,
        lid: Optional[bool] = None,
    ) -> bool:
        """Configure supported Dell wake sources."""
        operations: List[Tuple[str, bool]] = []
        if rtc is not None:
            operations.append(("autoon", rtc))
        if usb is not None:
            operations.append(("usbwake", usb))
        if lid is not None:
            operations.append(("lidswitch", lid))

        if not operations:
            return True

        success = True
        for attribute, enabled in operations:
            if not self._set_boolean_attribute(attribute, enabled):
                success = False
        return success

    # ------------------------------------------------------------------
    # Fleet management and OEM extensions
    # ------------------------------------------------------------------

    def get_asset_tag(self) -> str:
        """Return the Dell asset tag."""
        return self._query_attribute("asset") or self._system_value(
            "chassis_asset_tag",
            "SMBIOSAssetTag",
            wmi_class="Win32_SystemEnclosure",
        )

    def set_asset_tag(
        self,
        tag: str,
        admin_password: Optional[str] = None,
    ) -> bool:
        """Set the Dell asset tag."""
        normalized = tag.strip()
        if not normalized or len(normalized) > 64:
            return False

        return self._set_attribute(
            "asset",
            normalized,
            admin_password=admin_password,
        )

    def get_ownership_tag(self) -> str:
        """Return the Dell ownership tag."""
        return self._query_attribute("ownershiptag")

    def set_ownership_tag(
        self,
        tag: str,
        admin_password: Optional[str] = None,
    ) -> bool:
        """Set the Dell ownership tag."""
        normalized = tag.strip()
        if not normalized or len(normalized) > 80:
            return False

        return self._set_attribute(
            "ownershiptag",
            normalized,
            admin_password=admin_password,
        )

    def export_configuration(
        self,
        format_type: str = "json",
    ) -> Union[str, Dict[str, Any]]:
        """Export Dell BIOS configuration as JSON, XML, or a dictionary."""
        requested = format_type.strip().lower()
        if requested not in {"dict", "json", "xml"}:
            raise ValueError(
                "format_type must be 'dict', 'json', or 'xml'"
            )

        suffix = ".xml" if requested == "xml" else ".ini"
        temporary = self._new_temporary_file(suffix)
        code, stdout, stderr = self._run_cctk(
            [f"--outfile={temporary}"],
        )

        structured: Dict[str, Any]
        if code == 0 and temporary.exists():
            raw = temporary.read_text(
                encoding="utf-8",
                errors="replace",
            )
            structured = self._parse_configuration_payload(raw)
        else:
            rows = self._dell_wmi_rows("DCIM_BIOSElement")
            structured = {
                "provider": self.provider_name(),
                "generated_at": datetime.now().astimezone().isoformat(),
                "attributes": [
                    self._object_to_dict(row) for row in rows
                ],
                "cctk_stdout": self._sanitize_text(stdout),
                "cctk_error": self._sanitize_text(stderr),
            }
            raw = ""

        if requested == "dict":
            return structured

        if requested == "json":
            return json.dumps(
                structured,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            )

        if raw.lstrip().startswith("<?xml") or raw.lstrip().startswith("<"):
            return raw

        return self._configuration_to_xml(structured)

    def import_configuration(
        self,
        config_data: Union[str, Dict[str, Any]],
        admin_password: Optional[str] = None,
    ) -> bool:
        """Import and apply a Dell BIOS configuration payload."""
        if isinstance(config_data, dict):
            payload = self._configuration_dict_to_cctk(config_data)
            suffix = ".ini"
        elif isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            config_data, str
        ):
            # Statically redundant given this method's declared
            # ``Union[str, Dict[str, Any]]`` signature, but genuinely
            # meaningful at runtime: ``config_data`` is frequently handed
            # in from a deserialized JSON/YAML configuration file, which
            # Python does not enforce against the type hint. The final
            # ``else`` branch below depends on this check having actually
            # run rather than being assumed true.
            candidate = Path(config_data).expanduser()
            if candidate.is_file():
                try:
                    payload = candidate.read_text(
                        encoding="utf-8",
                        errors="strict",
                    )
                except (OSError, UnicodeError):
                    return False
                suffix = candidate.suffix or ".ini"
            else:
                payload = config_data
                stripped = payload.lstrip()
                suffix = ".xml" if stripped.startswith("<") else ".ini"
        else:
            return False

        if not payload.strip():
            return False

        temporary = self._new_temporary_file(suffix)
        try:
            temporary.write_text(
                payload,
                encoding="utf-8",
                errors="strict",
            )
            self._restrict_file_permissions(temporary)

            code, _, _ = self._run_cctk(
                [f"--infile={temporary}"],
                admin_password=admin_password,
            )
            if code == 0:
                self.refresh()
                return True

            return self._apply_configuration_with_wmi(
                self._parse_configuration_payload(payload),
                admin_password=admin_password,
            )
        except (OSError, UnicodeError, ValueError) as exc:
            self._dell_logger.error(
                "Unable to import Dell BIOS configuration: %s",
                self._sanitize_text(str(exc)),
            )
            return False
        finally:
            self._delete_temporary_file(temporary)

    def get_dock_info(self) -> Dict[str, Any]:
        """Return information about connected Dell docking stations."""
        rows: List[Any] = []
        for class_name in (
            "DCIM_DockService",
            "DCIM_Dock",
            "DCIM_ExternalDeviceView",
        ):
            rows = self._dell_wmi_rows(class_name)
            if rows:
                break

        docks: List[Dict[str, Any]] = []
        for row in rows:
            data = self._object_to_dict(row)
            searchable = json.dumps(data, default=str).lower()
            if class_name == "DCIM_ExternalDeviceView" and not any(
                marker in searchable
                for marker in ("dock", "wd19", "wd22", "hd22")
            ):
                continue

            docks.append(
                {
                    "model": self._mapping_value(
                        data,
                        (
                            "Model",
                            "ProductName",
                            "ElementName",
                            "Name",
                        ),
                    ),
                    "service_tag": self._mapping_value(
                        data,
                        ("ServiceTag", "SerialNumber"),
                    ),
                    "firmware_version": self._mapping_value(
                        data,
                        (
                            "FirmwareVersion",
                            "Version",
                            "SoftwareVersion",
                        ),
                    ),
                    "power_delivery_state": self._mapping_value(
                        data,
                        (
                            "PowerDeliveryState",
                            "PowerState",
                            "OperationalStatus",
                        ),
                    ),
                    "connection_state": self._mapping_value(
                        data,
                        (
                            "ConnectionState",
                            "EnabledState",
                            "Status",
                        ),
                    ),
                    "raw": data,
                }
            )

        return {
            "connected": bool(docks),
            "count": len(docks),
            "docks": docks,
            "source": "dell-wmi" if docks else "unavailable",
        }

    def get_safebios_indicators(self) -> Dict[str, Any]:
        """Return available Dell SafeBIOS security indicators."""
        result: Dict[str, Any] = {
            "supported": False,
            "image_verification": "Unknown",
            "off_host_attestation": "Unknown",
            "bios_events": [],
            "source": None,
        }

        queries = (
            "SELECT * FROM DCIM_BIOSElement",
            "SELECT * FROM DCIM_SoftwareIdentity",
            "SELECT * FROM DCIM_RecordLog",
        )
        for query in queries:
            rows = self._dell_wmi_query(query)
            for row in rows:
                data = self._object_to_dict(row)
                searchable = json.dumps(data, default=str).lower()
                if not any(
                    marker in searchable
                    for marker in (
                        "safebios",
                        "safe bios",
                        "bios verification",
                        "off-host",
                        "off host",
                        "attestation",
                    )
                ):
                    continue

                result["supported"] = True
                result["source"] = "dell-wmi"

                verification = self._mapping_value(
                    data,
                    (
                        "ImageVerificationStatus",
                        "VerificationStatus",
                        "CurrentValue",
                    ),
                )
                if verification:
                    result["image_verification"] = verification

                attestation = self._mapping_value(
                    data,
                    (
                        "OffHostAttestationStatus",
                        "AttestationStatus",
                        "OperationalStatus",
                    ),
                )
                if attestation:
                    result["off_host_attestation"] = attestation

                result["bios_events"].append(data)

        verification_value = self._query_first_attribute(
            (
                "safebios",
                "biosimageverification",
                "biosverification",
            )
        )
        if verification_value:
            result["supported"] = True
            result["image_verification"] = verification_value
            result["source"] = result["source"] or "cctk"

        attestation_value = self._query_first_attribute(
            (
                "offhostbiosverification",
                "offhostattestation",
                "biosattestation",
            )
        )
        if attestation_value:
            result["supported"] = True
            result["off_host_attestation"] = attestation_value
            result["source"] = result["source"] or "cctk"

        return result

    # ------------------------------------------------------------------
    # Reporting and compliance
    # ------------------------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """Return a complete JSON-serializable Dell status summary."""
        firmware = self.firmware_information()
        tpm = self.tpm_state()
        boot_devices = self.boot_order()
        current_boot = self.current_boot_device()
        next_boot = self.next_boot_device()
        battery = self.get_battery_health()

        return {
            "provider": {
                "name": self.provider_name(),
                "version": self.provider_version(),
                "vendor": self._serialize_value(self.vendor()),
                "connected": self.is_connected(),
                "backend": self._active_backend_name(),
                "detection_confidence": self.detection_confidence(),
            },
            "identity": {
                "manufacturer": self._firmware_value(
                    firmware,
                    "manufacturer",
                ),
                "product_name": self._firmware_value(
                    firmware,
                    "product_name",
                ),
                "model": self._firmware_value(firmware, "model"),
                "service_tag": self._firmware_value(
                    firmware,
                    "serial_number",
                ),
                "system_uuid": self._firmware_value(
                    firmware,
                    "system_uuid",
                ),
                "sku": self._firmware_value(firmware, "sku"),
                "asset_tag": self.get_asset_tag(),
                "ownership_tag": self.get_ownership_tag(),
            },
            "firmware": self._serialize_value(firmware),
            "boot": {
                "mode": self._serialize_value(self.get_boot_mode()),
                "secure_boot_enabled": self.secure_boot_enabled(),
                "secure_boot_mode": self.get_secure_boot_mode(),
                "order": [
                    self._serialize_value(device)
                    for device in boot_devices
                ],
                "current": self._serialize_value(current_boot),
                "next": self._serialize_value(next_boot),
                "supportassist_os_recovery": (
                    self.get_supportassist_os_recovery()
                ),
                "biosconnect": self.get_biosconnect_status(),
            },
            "security": {
                "tpm": self._serialize_value(tpm),
                "admin_password_set": self.is_admin_password_set(),
                "system_password_set": self.is_system_password_set(),
                "drive_password_set": self.is_drive_password_set(),
                "chassis_intrusion_detected": (
                    self.chassis_intrusion_detected()
                ),
                "computrace_status": self.get_computrace_status(),
                "intel_boot_guard": (
                    self.get_intel_boot_guard_status()
                ),
                "safebios": self.get_safebios_indicators(),
            },
            "virtualization": {
                "vt_x_supported": self.vt_x_supported(),
                "vt_x_enabled": self.vt_x_enabled(),
                "vt_d_supported": self.vt_d_supported(),
                "vt_d_enabled": self.vt_d_enabled(),
                "sriov_enabled": self.sriov_enabled(),
                "dma_remapping_enabled": (
                    self.dma_remapping_enabled()
                ),
            },
            "power": {
                "battery": battery,
                "charge_profile": self.get_charge_profile(),
                "charge_limits": list(self.get_charge_limits()),
                "thermal_management_profile": (
                    self.get_thermal_management_profile()
                ),
                "wake_on_lan": self.get_wake_on_lan(),
                "ac_recovery": self.get_ac_recovery(),
            },
            "dock": self.get_dock_info(),
        }

    def report(self) -> Dict[str, Any]:
        """Return a structured Dell fleet-audit report."""
        summary = self.summary()
        diagnostics = self.run_diagnostics()

        return {
            "generated_at": datetime.now().astimezone().isoformat(),
            "provider": self.provider_name(),
            "provider_version": self.provider_version(),
            "summary": summary,
            "diagnostics": diagnostics,
            "health": {
                "healthy": diagnostics["compliant"],
                "critical_findings": diagnostics["critical_count"],
                "warning_findings": diagnostics["warning_count"],
            },
        }

    def export_markdown(self) -> str:
        """Return a human-readable Dell corporate fleet audit report."""
        report = self.report()
        summary = report["summary"]
        provider = summary["provider"]
        identity = summary["identity"]
        firmware = summary["firmware"]
        boot = summary["boot"]
        security = summary["security"]
        virtualization = summary["virtualization"]
        power = summary["power"]
        diagnostics = report["diagnostics"]

        # ``report()`` is assembled above from this class's own already-typed
        # accessors, but its return type is ``Dict[str, Any]`` -- the nested
        # sections are only known to be dict-shaped once inspected here, so
        # each is cast to the shape its own ``isinstance`` check confirmed
        # rather than letting "Unknown" spread through the rest of this
        # formatter.
        firmware_version = ""
        if isinstance(firmware, dict):
            typed_firmware = cast(Dict[str, Any], firmware)
            firmware_version = str(
                typed_firmware.get("bios_version")
                or typed_firmware.get("version")
                or ""
            )

        tpm_raw = security.get("tpm", {})
        tpm: Dict[str, Any] = (
            cast(Dict[str, Any], tpm_raw) if isinstance(tpm_raw, dict) else {}
        )

        charge_limits_raw = power.get("charge_limits", [0, 100])
        charge_limits: List[Any] = (
            cast(List[Any], charge_limits_raw)
            if isinstance(charge_limits_raw, list)
            and len(cast(List[Any], charge_limits_raw)) == 2
            else [0, 100]
        )

        lines = [
            "# Dell BIOS Fleet Audit",
            "",
            f"_Generated: {report['generated_at']}_",
            "",
            "## Provider",
            "",
            f"- **Provider:** {provider['name']}",
            f"- **Version:** {provider['version']}",
            f"- **Backend:** {provider['backend']}",
            f"- **Connected:** {provider['connected']}",
            (
                "- **Detection confidence:** "
                f"{provider['detection_confidence']:.2f}"
            ),
            "",
            "## System Identity",
            "",
            f"- **Manufacturer:** {identity['manufacturer']}",
            f"- **Product:** {identity['product_name']}",
            f"- **Model:** {identity['model']}",
            f"- **Service Tag:** {identity['service_tag']}",
            f"- **Asset Tag:** {identity['asset_tag']}",
            f"- **Ownership Tag:** {identity['ownership_tag']}",
            f"- **SKU:** {identity['sku']}",
            "",
            "## Firmware and Boot",
            "",
            f"- **BIOS version:** {firmware_version}",
            f"- **Boot mode:** {boot['mode']}",
            f"- **Secure Boot:** {boot['secure_boot_enabled']}",
            f"- **Secure Boot mode:** {boot['secure_boot_mode']}",
            (
                "- **SupportAssist OS Recovery:** "
                f"{boot['supportassist_os_recovery']}"
            ),
            f"- **BIOSConnect:** {boot['biosconnect']}",
            "",
            "## Security",
            "",
            f"- **TPM present:** {tpm.get('present', False)}",
            f"- **TPM enabled:** {tpm.get('enabled', False)}",
            f"- **TPM activated:** {tpm.get('activated', False)}",
            f"- **TPM version:** {tpm.get('spec_version', '')}",
            (
                "- **Administrator password set:** "
                f"{security['admin_password_set']}"
            ),
            (
                "- **System password set:** "
                f"{security['system_password_set']}"
            ),
            (
                "- **Drive password set:** "
                f"{security['drive_password_set']}"
            ),
            (
                "- **Chassis intrusion detected:** "
                f"{security['chassis_intrusion_detected']}"
            ),
            (
                "- **Absolute Persistence:** "
                f"{security['computrace_status']}"
            ),
            "",
            "## Virtualization",
            "",
            (
                "- **VT-x/AMD-V supported:** "
                f"{virtualization['vt_x_supported']}"
            ),
            (
                "- **VT-x/AMD-V enabled:** "
                f"{virtualization['vt_x_enabled']}"
            ),
            (
                "- **VT-d/IOMMU supported:** "
                f"{virtualization['vt_d_supported']}"
            ),
            (
                "- **VT-d/IOMMU enabled:** "
                f"{virtualization['vt_d_enabled']}"
            ),
            (
                "- **SR-IOV enabled:** "
                f"{virtualization['sriov_enabled']}"
            ),
            (
                "- **DMA remapping enabled:** "
                f"{virtualization['dma_remapping_enabled']}"
            ),
            "",
            "## Power and Thermal",
            "",
            f"- **Charge profile:** {power['charge_profile']}",
            (
                "- **Custom charge limits:** "
                f"{charge_limits[0]}–{charge_limits[1]}%"
            ),
            (
                "- **Thermal profile:** "
                f"{power['thermal_management_profile']}"
            ),
            f"- **Wake-on-LAN:** {power['wake_on_lan']}",
            f"- **AC recovery:** {power['ac_recovery']}",
            "",
            "## Compliance",
            "",
            f"- **Compliant:** {diagnostics['compliant']}",
            (
                "- **Critical findings:** "
                f"{diagnostics['critical_count']}"
            ),
            (
                "- **Warnings:** "
                f"{diagnostics['warning_count']}"
            ),
            "",
        ]

        findings = diagnostics.get("findings", [])
        if findings:
            lines.extend(
                [
                    "### Findings",
                    "",
                ]
            )
            for finding in findings:
                lines.append(
                    "- **{severity}** `{code}`: {message}".format(
                        severity=str(
                            finding.get("severity", "unknown")
                        ).upper(),
                        code=finding.get("code", "unknown"),
                        message=finding.get("message", ""),
                    )
                )
            lines.append("")

        return "\n".join(lines)

    def run_diagnostics(self) -> Dict[str, Any]:
        """Evaluate Dell firmware against a security baseline."""
        findings: List[Dict[str, Any]] = []

        tpm = self.tpm_state()
        tpm_data_raw = self._serialize_value(tpm)
        tpm_data: Dict[str, Any] = (
            cast(Dict[str, Any], tpm_data_raw)
            if isinstance(tpm_data_raw, dict)
            else {}
        )

        if not self._coerce_bool(tpm_data.get("present"), False):
            findings.append(
                {
                    "code": "tpm_missing",
                    "severity": "critical",
                    "message": "No TPM was detected.",
                    "remediation": "Verify that a TPM is installed.",
                }
            )
        elif not self._coerce_bool(tpm_data.get("enabled"), False):
            findings.append(
                {
                    "code": "tpm_disabled",
                    "severity": "critical",
                    "message": "The TPM is disabled in firmware.",
                    "remediation": "Enable and activate the TPM.",
                }
            )

        if not self.secure_boot_enabled():
            findings.append(
                {
                    "code": "secure_boot_disabled",
                    "severity": "critical",
                    "message": "Secure Boot is disabled.",
                    "remediation": (
                        "Enable UEFI boot and Secure Boot after validating "
                        "operating-system compatibility."
                    ),
                }
            )

        if self.get_boot_mode() != BIOSMode.UEFI:
            findings.append(
                {
                    "code": "legacy_boot_mode",
                    "severity": "warning",
                    "message": "Firmware is configured for legacy boot.",
                    "remediation": (
                        "Migrate the operating system to UEFI before "
                        "changing firmware boot mode."
                    ),
                }
            )

        if not self.is_admin_password_set():
            findings.append(
                {
                    "code": "admin_password_missing",
                    "severity": "warning",
                    "message": (
                        "No BIOS administrator password is configured."
                    ),
                    "remediation": (
                        "Configure a managed BIOS administrator password."
                    ),
                }
            )

        if self.vt_x_supported() and not self.vt_x_enabled():
            findings.append(
                {
                    "code": "virtualization_disabled",
                    "severity": "warning",
                    "message": (
                        "Processor virtualization is supported but disabled."
                    ),
                    "remediation": (
                        "Enable virtualization when required by policy."
                    ),
                }
            )

        if self.vt_d_supported() and not self.vt_d_enabled():
            findings.append(
                {
                    "code": "iommu_disabled",
                    "severity": "warning",
                    "message": (
                        "IOMMU/VT-d is supported but disabled."
                    ),
                    "remediation": (
                        "Enable VT-d/IOMMU for DMA isolation where "
                        "supported."
                    ),
                }
            )

        if self.chassis_intrusion_detected():
            findings.append(
                {
                    "code": "chassis_intrusion",
                    "severity": "critical",
                    "message": (
                        "Firmware reports a chassis-intrusion event."
                    ),
                    "remediation": (
                        "Inspect the system and clear the event only after "
                        "physical-security review."
                    ),
                }
            )

        computrace = self._normalized(self.get_computrace_status())
        if "permanently disabled" in computrace:
            findings.append(
                {
                    "code": "absolute_permanently_disabled",
                    "severity": "informational",
                    "message": (
                        "Absolute Persistence is permanently disabled."
                    ),
                    "remediation": (
                        "No firmware remediation is possible for this state."
                    ),
                }
            )

        critical_count = sum(
            finding["severity"] == "critical"
            for finding in findings
        )
        warning_count = sum(
            finding["severity"] == "warning"
            for finding in findings
        )

        return {
            "evaluated_at": datetime.now().astimezone().isoformat(),
            "baseline": "aquila-dell-enterprise",
            "compliant": critical_count == 0,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "finding_count": len(findings),
            "findings": findings,
        }

    # ------------------------------------------------------------------
    # CCTK and WMI execution
    # ------------------------------------------------------------------

    def _run_cctk(
        self,
        args: List[str],
        admin_password: Optional[str] = None,
        secret_values: Sequence[Optional[str]] = (),
    ) -> Tuple[int, str, str]:
        """Execute CCTK while redacting all credential-bearing data."""
        binary = self._cctk_path or self._locate_cctk()
        if binary is None:
            return (127, "", "Dell Command | Configure was not found.")

        command = [str(binary)]
        command.extend(str(argument) for argument in args)

        secrets = [
            value
            for value in secret_values
            if isinstance(value, str) and value
        ]
        if admin_password:
            secrets.append(admin_password)
            command.append(f"--val-adminpw={admin_password}")

        safe_command = self._sanitize_command(command, secrets)
        self._dell_logger.debug(
            "Executing Dell Command | Configure: %s",
            safe_command,
        )

        with self._execution_lock:
            code, stdout, stderr = self._run_process(
                command,
                timeout=120.0,
            )

        sanitized_stdout = self._sanitize_text(stdout, secrets)
        sanitized_stderr = self._sanitize_text(stderr, secrets)

        if code != 0:
            self._dell_logger.warning(
                "CCTK exited with status %s: %s",
                code,
                sanitized_stderr or sanitized_stdout,
            )

        return (code, sanitized_stdout, sanitized_stderr)

    def _run_process(
        self,
        command: Sequence[str],
        timeout: float,
    ) -> Tuple[int, str, str]:
        """Run a subprocess without a shell and capture bounded output."""
        environment = os.environ.copy()
        environment.update(
            {
                "LANG": "C",
                "LC_ALL": "C",
                "PYTHONIOENCODING": "utf-8",
            }
        )

        startupinfo: Optional[Any] = None
        creationflags = 0
        if platform.system() == "Windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0,
            )

        process: Optional[subprocess.Popen[str]] = None
        try:
            process = subprocess.Popen(
                list(command),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
                env=environment,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )
            stdout, stderr = process.communicate(timeout=timeout)
            return (
                int(process.returncode or 0),
                stdout[-1048576:],
                stderr[-1048576:],
            )
        except subprocess.TimeoutExpired:
            if process is not None:
                process.kill()
                stdout, stderr = process.communicate()
            else:
                stdout, stderr = "", ""
            return (
                124,
                stdout[-1048576:],
                (
                    stderr[-1048576:]
                    + "\nOperation timed out."
                ).strip(),
            )
        except (OSError, ValueError) as exc:
            return (126, "", self._sanitize_text(str(exc)))

    def _query_wmi(
        self,
        namespace: str,
        query: str,
    ) -> List[Any]:
        """Execute a local WMI query through available Windows bindings."""
        if platform.system() != "Windows":
            return []

        if not re.fullmatch(
            r"(?is)\s*select\s+.+\s+from\s+[A-Za-z0-9_]+"
            r"(?:\s+where\s+.+)?\s*",
            query,
        ):
            raise ValueError("Only read-only WMI SELECT queries are allowed.")

        with self._execution_lock:
            try:
                import wmi  # type: ignore[import-untyped]

                key = f"wmi:{namespace}"
                connection = self._wmi_handles.get(key)
                if connection is None:
                    connection = wmi.WMI(namespace=namespace)
                    self._wmi_handles[key] = connection
                return list(connection.query(query))
            except ImportError:
                pass
            except Exception as exc:
                self._dell_logger.debug(
                    "Python WMI query failed in %s: %s",
                    namespace,
                    self._sanitize_text(str(exc)),
                )

            try:
                import win32com.client  # type: ignore[import-untyped]

                key = f"com:{namespace}"
                service = self._wmi_handles.get(key)
                if service is None:
                    locator = win32com.client.Dispatch(
                        "WbemScripting.SWbemLocator"
                    )
                    service = locator.ConnectServer(
                        ".",
                        namespace,
                    )
                    service.Security_.ImpersonationLevel = 3
                    self._wmi_handles[key] = service

                return list(
                    service.ExecQuery(
                        query,
                        "WQL",
                        0x10 | 0x20,
                    )
                )
            except ImportError:
                return []
            except Exception as exc:
                self._dell_logger.debug(
                    "COM WMI query failed in %s: %s",
                    namespace,
                    self._sanitize_text(str(exc)),
                )
                return []

    def _query_wmi_safe(
        self,
        namespace: str,
        query: str,
    ) -> List[Any]:
        """Run a WMI query and convert backend failures to an empty result."""
        try:
            return self._query_wmi(namespace, query)
        except Exception as exc:
            self._dell_logger.debug(
                "WMI query was unavailable: %s",
                self._sanitize_text(str(exc)),
            )
            return []

    def _parse_cctk_output(
        self,
        raw_output: str,
    ) -> Dict[str, str]:
        """Parse Dell CCTK key/value and status output."""
        parsed: Dict[str, str] = {}
        current_key: Optional[str] = None

        for raw_line in raw_output.replace("\r", "\n").split("\n"):
            line = raw_line.strip()
            if not line:
                continue

            if re.match(
                r"^(cctk|dell command|copyright|usage|warning)\b",
                line,
                flags=re.IGNORECASE,
            ):
                continue

            match = re.match(
                r"^(?:--)?([^:=\t]+?)\s*(?:=|:|\t)\s*(.*)$",
                line,
            )
            if match:
                key = self._normalized_key(match.group(1))
                value = match.group(2).strip().strip('"')
                if key:
                    parsed[key] = value
                    current_key = key
                continue

            option_match = re.match(
                r"^--([A-Za-z0-9_-]+)\s+(.+)$",
                line,
            )
            if option_match:
                key = self._normalized_key(option_match.group(1))
                parsed[key] = option_match.group(2).strip().strip('"')
                current_key = key
                continue

            if current_key is not None:
                parsed[current_key] = (
                    f"{parsed[current_key]}\n{line}".strip()
                )
            else:
                parsed.setdefault("value", line)

        return parsed

    # ------------------------------------------------------------------
    # Backend helpers
    # ------------------------------------------------------------------

    def _locate_cctk(self) -> Optional[Path]:
        """Locate Dell Command | Configure."""
        if self._cctk_path is not None and self._cctk_path.is_file():
            return self._cctk_path

        environment_path = os.environ.get("AQUILA_CCTK_PATH", "")
        if environment_path:
            candidate = Path(environment_path).expanduser()
            if candidate.is_file():
                self._cctk_path = candidate.resolve()
                return self._cctk_path

        for executable_name in _CCTK_NAMES:
            resolved = shutil.which(executable_name)
            if resolved:
                candidate = Path(resolved)
                if candidate.is_file():
                    self._cctk_path = candidate.resolve()
                    return self._cctk_path

        for candidate in _CCTK_PATHS:
            if candidate.is_file():
                self._cctk_path = candidate.resolve()
                return self._cctk_path

        return None

    def _active_backend_name(self) -> str:
        """Return the highest-priority currently available backend."""
        if self._cctk_path is not None and self._cctk_path.is_file():
            return "dell-command-configure"
        if self._wmi_namespace is not None:
            return f"wmi:{self._wmi_namespace}"
        if self._sysfs_root is not None and self._sysfs_root.is_dir():
            return "sysfs"
        if platform.system() == "Windows":
            return r"wmi:root\cimv2"
        return "default"

    def _query_attribute(
        self,
        attribute: str,
        aliases: Sequence[str] = (),
    ) -> str:
        """Read a BIOS attribute through CCTK and then Dell WMI."""
        candidates = (attribute,) + tuple(aliases)
        cache_key = "attribute:" + "|".join(
            self._normalized_key(candidate)
            for candidate in candidates
        )
        cached = self._attribute_cache.get(cache_key)
        if isinstance(cached, str):
            return cached

        for candidate in candidates:
            code, stdout, _ = self._run_cctk(
                [f"--{candidate}"],
            )
            if code != 0:
                continue

            parsed = self._parse_cctk_output(stdout)
            normalized_candidate = self._normalized_key(candidate)
            value = parsed.get(normalized_candidate)

            if value is None and len(parsed) == 1:
                value = next(iter(parsed.values()))

            if value is None:
                meaningful_lines = [
                    line.strip()
                    for line in stdout.splitlines()
                    if line.strip()
                    and not re.match(
                        r"^(cctk|dell command|copyright|warning)\b",
                        line.strip(),
                        flags=re.IGNORECASE,
                    )
                ]
                if meaningful_lines:
                    value = meaningful_lines[-1]

            if value:
                cleaned = self._clean_attribute_value(
                    value,
                    candidate,
                )
                self._attribute_cache[cache_key] = cleaned
                return cleaned

        value = self._query_wmi_attribute(candidates)
        if value:
            self._attribute_cache[cache_key] = value
            return value

        return ""

    def _query_first_attribute(
        self,
        attributes: Sequence[str],
    ) -> str:
        """Return the first available Dell BIOS attribute value."""
        for attribute in attributes:
            value = self._query_attribute(attribute)
            if value:
                return value
        return ""

    def _query_boolean_attribute(
        self,
        attribute: str,
        aliases: Sequence[str] = (),
    ) -> bool:
        """Read and normalize a boolean Dell BIOS attribute."""
        value = self._query_attribute(attribute, aliases)
        return self._coerce_bool(value, default=False)

    def _set_boolean_attribute(
        self,
        attribute: str,
        enabled: bool,
        admin_password: Optional[str] = None,
    ) -> bool:
        """Set a Dell BIOS attribute using enable/disable syntax."""
        return self._set_attribute(
            attribute,
            "enable" if enabled else "disable",
            admin_password=admin_password,
        )

    def _set_attribute(
        self,
        attribute: str,
        value: str,
        admin_password: Optional[str] = None,
    ) -> bool:
        """Set a Dell BIOS attribute using the backend hierarchy."""
        normalized_attribute = attribute.strip().lstrip("-")
        if not normalized_attribute:
            return False

        if admin_password:
            if self._set_wmi_attribute(
                normalized_attribute,
                value,
                admin_password=admin_password,
            ):
                self.refresh()
                return True

        code, _, _ = self._run_cctk(
            [f"--{normalized_attribute}={value}"],
            admin_password=admin_password,
        )
        if code == 0:
            self.refresh()
            return True

        if self._set_wmi_attribute(
            normalized_attribute,
            value,
            admin_password=admin_password,
        ):
            self.refresh()
            return True

        return False

    def _query_wmi_attribute(
        self,
        candidates: Sequence[str],
    ) -> str:
        """Read a named BIOS attribute from Dell Command Monitor."""
        normalized_candidates = {
            self._normalized_key(candidate)
            for candidate in candidates
        }

        for class_name in (
            "DCIM_BIOSEnumeration",
            "DCIM_BIOSString",
            "DCIM_BIOSInteger",
            "DCIM_BIOSElement",
        ):
            rows = self._dell_wmi_rows(class_name)
            for row in rows:
                data = self._object_to_dict(row)
                name = self._mapping_value(
                    data,
                    (
                        "AttributeName",
                        "Name",
                        "ElementName",
                        "InstanceID",
                    ),
                )
                normalized_name = self._normalized_key(name)
                if not normalized_name:
                    continue

                if not any(
                    candidate == normalized_name
                    or candidate in normalized_name
                    or normalized_name in candidate
                    for candidate in normalized_candidates
                ):
                    continue

                value = self._mapping_value(
                    data,
                    (
                        "CurrentValue",
                        "CurrentValueName",
                        "Value",
                        "AttributeValue",
                        "PendingValue",
                    ),
                )
                if value:
                    return value

        return ""

    def _set_wmi_attribute(
        self,
        attribute: str,
        value: str,
        admin_password: Optional[str] = None,
    ) -> bool:
        """Set a Dell BIOS attribute through supported WMI service methods."""
        if platform.system() != "Windows":
            return False

        for namespace in self._preferred_wmi_namespaces():
            if self._set_wmi_attribute_with_python_wmi(
                namespace,
                attribute,
                value,
                admin_password,
            ):
                return True

            if self._set_wmi_attribute_with_com(
                namespace,
                attribute,
                value,
                admin_password,
            ):
                return True

        return False

    def _set_wmi_attribute_with_python_wmi(
        self,
        namespace: str,
        attribute: str,
        value: str,
        admin_password: Optional[str],
    ) -> bool:
        """Invoke Dell BIOS setters through the optional Python WMI module."""
        try:
            import wmi  # type: ignore[import-untyped]
        except ImportError:
            return False

        try:
            connection = wmi.WMI(namespace=namespace)
            service_classes = (
                "DCIM_BIOSService",
                "DCIM_BIOSServiceInterface",
            )

            for class_name in service_classes:
                try:
                    services = list(
                        connection.query(
                            f"SELECT * FROM {class_name}"
                        )
                    )
                except Exception:
                    continue

                for service in services:
                    for method_name in (
                        "SetAttribute",
                        "SetBIOSAttribute",
                        "SetBIOSAttributes",
                    ):
                        method = getattr(service, method_name, None)
                        if not callable(method):
                            continue

                        argument_sets: List[Dict[str, Any]] = [
                            {
                                "AttributeName": attribute,
                                "AttributeValue": value,
                            },
                            {
                                "Name": attribute,
                                "Value": value,
                            },
                            {
                                "Target": attribute,
                                "Value": value,
                            },
                        ]
                        if admin_password:
                            for arguments in argument_sets:
                                arguments.update(
                                    {
                                        "AuthorizationToken": (
                                            admin_password
                                        ),
                                        "Password": admin_password,
                                        "PasswordType": 1,
                                    }
                                )

                        for arguments in argument_sets:
                            try:
                                result = method(**arguments)
                            except (TypeError, ValueError):
                                continue
                            except Exception as exc:
                                self._dell_logger.debug(
                                    "Dell WMI setter failed: %s",
                                    self._sanitize_text(
                                        str(exc),
                                        (admin_password,),
                                    ),
                                )
                                continue

                            if self._wmi_result_succeeded(result):
                                return True
        except Exception as exc:
            self._dell_logger.debug(
                "Unable to initialize Dell WMI setter: %s",
                self._sanitize_text(
                    str(exc),
                    (admin_password,),
                ),
            )

        return False

    def _set_wmi_attribute_with_com(
        self,
        namespace: str,
        attribute: str,
        value: str,
        admin_password: Optional[str],
    ) -> bool:
        """Invoke Dell BIOS setters through native COM WMI."""
        try:
            import win32com.client  # type: ignore[import-untyped]
        except ImportError:
            return False

        try:
            locator = win32com.client.Dispatch(
                "WbemScripting.SWbemLocator"
            )
            service = locator.ConnectServer(".", namespace)
            service.Security_.ImpersonationLevel = 3

            for class_name in (
                "DCIM_BIOSService",
                "DCIM_BIOSServiceInterface",
            ):
                try:
                    services = list(
                        service.ExecQuery(
                            f"SELECT * FROM {class_name}",
                            "WQL",
                            0x10 | 0x20,
                        )
                    )
                except Exception:
                    continue

                for instance in services:
                    methods = getattr(instance, "Methods_", None)
                    if methods is None:
                        continue

                    for method_name in (
                        "SetAttribute",
                        "SetBIOSAttribute",
                        "SetBIOSAttributes",
                    ):
                        try:
                            method_definition = methods.Item(method_name)
                            input_parameters = (
                                method_definition.InParameters.SpawnInstance_()
                            )
                        except Exception:
                            continue

                        self._set_com_parameter(
                            input_parameters,
                            (
                                "AttributeName",
                                "Name",
                                "Target",
                            ),
                            attribute,
                        )
                        self._set_com_parameter(
                            input_parameters,
                            (
                                "AttributeValue",
                                "Value",
                                "CurrentValue",
                            ),
                            value,
                        )

                        if admin_password:
                            self._set_com_parameter(
                                input_parameters,
                                (
                                    "AuthorizationToken",
                                    "Password",
                                    "AdminPassword",
                                ),
                                admin_password,
                            )
                            self._set_com_parameter(
                                input_parameters,
                                ("PasswordType",),
                                1,
                            )

                        try:
                            output = service.ExecMethod(
                                instance.Path_.Path,
                                method_name,
                                input_parameters,
                            )
                        except Exception as exc:
                            self._dell_logger.debug(
                                "Dell COM setter failed: %s",
                                self._sanitize_text(
                                    str(exc),
                                    (admin_password,),
                                ),
                            )
                            continue

                        if self._wmi_result_succeeded(output):
                            return True
        except Exception as exc:
            self._dell_logger.debug(
                "Unable to initialize Dell COM setter: %s",
                self._sanitize_text(
                    str(exc),
                    (admin_password,),
                ),
            )

        return False

    @staticmethod
    def _set_com_parameter(
        parameters: Any,
        names: Sequence[str],
        value: Any,
    ) -> bool:
        """Set the first matching COM input parameter."""
        for name in names:
            try:
                parameters.Properties_.Item(name).Value = value
                return True
            except Exception:
                continue
        return False

    def _wmi_result_succeeded(self, result: Any) -> bool:
        """Normalize Dell WMI method return conventions."""
        if result is None:
            return True

        if isinstance(result, bool):
            return result

        if isinstance(result, int):
            return result == 0

        if isinstance(result, tuple):
            if not result:
                return True
            return self._coerce_int(result[0]) in (0, None)

        if isinstance(result, dict):
            return_value = self._mapping_value(
                cast(Dict[str, Any], result),
                (
                    "ReturnValue",
                    "return_value",
                    "Status",
                ),
            )
            return self._coerce_int(return_value) in (0, None)

        for name in (
            "ReturnValue",
            "return_value",
            "Status",
        ):
            try:
                return_value = getattr(result, name)
            except Exception:
                continue
            return self._coerce_int(return_value) in (0, None)

        try:
            return_value = result.Properties_.Item(
                "ReturnValue"
            ).Value
            return self._coerce_int(return_value) in (0, None)
        except Exception:
            return False

    def _preferred_wmi_namespaces(self) -> Tuple[str, ...]:
        """Return Dell namespaces with the connected namespace first."""
        namespaces: List[str] = []
        if self._wmi_namespace:
            namespaces.append(self._wmi_namespace)

        for namespace in _DELL_WMI_NAMESPACES:
            if namespace not in namespaces:
                namespaces.append(namespace)

        return tuple(namespaces)

    def _dell_wmi_rows(self, class_name: str) -> List[Any]:
        """Query a Dell WMI class in all supported namespaces."""
        if not re.fullmatch(r"[A-Za-z0-9_]+", class_name):
            return []

        return self._dell_wmi_query(
            f"SELECT * FROM {class_name}"
        )

    def _dell_wmi_query(self, query: str) -> List[Any]:
        """Run a read-only query against the first responsive Dell namespace."""
        for namespace in self._preferred_wmi_namespaces():
            rows = self._query_wmi_safe(namespace, query)
            if rows:
                if self._wmi_namespace is None:
                    self._wmi_namespace = namespace
                return rows
        return []

    def _wmi_class_exists(self, class_name: str) -> bool:
        """Return whether a Dell WMI class can be queried."""
        return bool(self._dell_wmi_rows(class_name))

    def _wmi_bios_attribute_exists(
        self,
        attributes: Sequence[str],
    ) -> bool:
        """Return whether any requested Dell BIOS attribute exists."""
        normalized = {
            self._normalized_key(attribute)
            for attribute in attributes
        }

        for class_name in (
            "DCIM_BIOSEnumeration",
            "DCIM_BIOSString",
            "DCIM_BIOSInteger",
            "DCIM_BIOSElement",
        ):
            for row in self._dell_wmi_rows(class_name):
                data = self._object_to_dict(row)
                name = self._mapping_value(
                    data,
                    (
                        "AttributeName",
                        "Name",
                        "ElementName",
                        "InstanceID",
                    ),
                )
                normalized_name = self._normalized_key(name)
                if any(
                    item == normalized_name
                    or item in normalized_name
                    or normalized_name in item
                    for item in normalized
                ):
                    return True

        return False

    def _system_value(
        self,
        sysfs_name: str,
        wmi_property: str,
        wmi_class: str = "Win32_ComputerSystem",
    ) -> str:
        """Read a native system value from sysfs or Win32 WMI."""
        cache_key = (
            f"system:{sysfs_name}:{wmi_class}:{wmi_property}"
        )
        cached = self._attribute_cache.get(cache_key)
        if isinstance(cached, str):
            return cached

        sysfs_path = Path("/sys/class/dmi/id") / sysfs_name
        try:
            if sysfs_path.is_file():
                value = sysfs_path.read_text(
                    encoding="utf-8",
                    errors="replace",
                ).strip().strip("\x00")
                if value:
                    self._attribute_cache[cache_key] = value
                    return value
        except OSError:
            pass

        if platform.system() == "Windows":
            if not re.fullmatch(r"[A-Za-z0-9_]+", wmi_class):
                return ""
            if not re.fullmatch(r"[A-Za-z0-9_]+", wmi_property):
                return ""

            rows = self._query_wmi_safe(
                r"root\cimv2",
                f"SELECT {wmi_property} FROM {wmi_class}",
            )
            value = self._first_value(rows, (wmi_property,))
            if value:
                self._attribute_cache[cache_key] = value
                return value

        return ""

    def _has_dell_pci_vendor(self) -> bool:
        """Return whether PCI vendor 1028 is present."""
        pci_root = Path("/sys/bus/pci/devices")
        if pci_root.is_dir():
            try:
                for vendor_file in pci_root.glob("*/vendor"):
                    value = vendor_file.read_text(
                        encoding="ascii",
                        errors="ignore",
                    ).strip().lower()
                    if value in {"0x1028", "1028"}:
                        return True
            except OSError:
                pass

        output = self._native_command_output(
            ["lspci", "-n"],
            timeout=10.0,
        )
        if re.search(r"\b1028:", output, flags=re.IGNORECASE):
            return True

        if platform.system() == "Windows":
            rows = self._query_wmi_safe(
                r"root\cimv2",
                (
                    "SELECT PNPDeviceID FROM Win32_PnPEntity "
                    "WHERE PNPDeviceID LIKE '%VEN_1028%'"
                ),
            )
            return bool(rows)

        return False

    @staticmethod
    def _valid_service_tag(value: str) -> bool:
        """Validate the standard Dell Service Tag representation."""
        return bool(
            re.fullmatch(
                r"[A-Za-z0-9]{5,7}",
                value.strip(),
            )
        )

    @staticmethod
    def _service_tag_to_express_code(service_tag: str) -> str:
        """Convert a base-36 Dell Service Tag to its decimal express code."""
        normalized = service_tag.strip().upper()
        if not DellProvider._valid_service_tag(normalized):
            return ""

        try:
            return str(int(normalized, 36))
        except ValueError:
            return ""

    def _gpu_vbios_versions(self) -> List[Dict[str, str]]:
        """Return available integrated and discrete GPU VBIOS versions."""
        rows = self._dell_wmi_rows("DCIM_VideoControllerView")
        if not rows:
            rows = self._query_wmi_safe(
                r"root\cimv2",
                (
                    "SELECT Name, VideoProcessor, DriverVersion, "
                    "AdapterCompatibility, PNPDeviceID "
                    "FROM Win32_VideoController"
                ),
            )

        result: List[Dict[str, str]] = []
        for row in rows:
            data = self._object_to_dict(row)
            name = self._mapping_value(
                data,
                ("Name", "ElementName", "VideoProcessor"),
            )
            version = self._mapping_value(
                data,
                (
                    "VBIOSVersion",
                    "VideoBIOSVersion",
                    "FirmwareVersion",
                    "DriverVersion",
                ),
            )
            if not name and not version:
                continue

            lower_name = name.lower()
            gpu_type = (
                "integrated"
                if any(
                    marker in lower_name
                    for marker in (
                        "intel",
                        "integrated",
                        "uhd",
                        "iris",
                    )
                )
                else "discrete"
            )
            result.append(
                {
                    "name": name,
                    "type": gpu_type,
                    "vbios_version": version,
                    "vendor": self._mapping_value(
                        data,
                        (
                            "AdapterCompatibility",
                            "Manufacturer",
                        ),
                    ),
                }
            )

        return result

    # ------------------------------------------------------------------
    # Boot helpers
    # ------------------------------------------------------------------

    def _parse_boot_order(self, output: str) -> List[BootDevice]:
        """Parse Dell CCTK boot-order output into domain objects."""
        devices: List[BootDevice] = []
        seen: Set[str] = set()
        priority = 0

        parsed = self._parse_cctk_output(output)
        candidate_lines: List[str] = []

        for key, value in parsed.items():
            if "bootorder" in key or "bootsequence" in key:
                candidate_lines.extend(
                    item.strip()
                    for item in re.split(r"[\n,;]", value)
                    if item.strip()
                )

        if not candidate_lines:
            candidate_lines = [
                line.strip()
                for line in output.splitlines()
                if line.strip()
                and not re.match(
                    r"^(cctk|dell command|copyright|warning)\b",
                    line.strip(),
                    flags=re.IGNORECASE,
                )
            ]

        expanded: List[str] = []
        for line in candidate_lines:
            if "," in line:
                expanded.extend(
                    part.strip()
                    for part in line.split(",")
                    if part.strip()
                )
            else:
                expanded.append(line)

        for line in expanded:
            match = re.match(
                r"^\s*(?:(\d+)[.)\]:-]?\s*)?"
                r"(?:(enabled|disabled|active|inactive)"
                r"\s*[:=-]?\s*)?"
                r"(.+?)\s*$",
                line,
                flags=re.IGNORECASE,
            )
            if not match:
                continue

            index_text = match.group(1)
            state_text = match.group(2) or ""
            remainder = match.group(3).strip()

            enabled = self._normalized(state_text) not in {
                "disabled",
                "inactive",
            }
            if re.search(
                r"__MATH_BLOCK_0__",
                remainder,
                flags=re.IGNORECASE,
            ):
                enabled = False

            remainder = re.sub(
                r"__MATH_BLOCK_1__",
                "",
                remainder,
                flags=re.IGNORECASE,
            ).strip()

            identifier = ""
            identifier_match = re.match(
                r"^(Boot[0-9A-Fa-f]{4}|[A-Za-z0-9_-]+)"
                r"\s*[:=]\s*(.+)$",
                remainder,
            )
            if identifier_match:
                identifier = identifier_match.group(1)
                name = identifier_match.group(2).strip()
            else:
                name = remainder
                identifier = re.sub(
                    r"[^A-Za-z0-9_.-]+",
                    "_",
                    name,
                ).strip("_")

            if not name:
                continue

            deduplication_key = (
                self._normalized_key(identifier)
                or self._normalized_key(name)
            )
            if deduplication_key in seen:
                continue
            seen.add(deduplication_key)

            parsed_priority = (
                int(index_text)
                if index_text is not None
                else priority
            )
            devices.append(
                BootDevice(
                    identifier=identifier or str(parsed_priority),
                    name=name,
                    device_type=self._boot_device_type(name, ""),
                    enabled=enabled,
                    priority=parsed_priority,
                    path=None,
                    metadata={"source": "cctk"},
                )
            )
            priority += 1

        def boot_priority(device: BootDevice) -> int:
            priority_value = device.priority
            if priority_value is None:
                return 2**31 - 1
            return priority_value
        
        devices.sort(key=boot_priority)
        return devices

    @staticmethod
    def _boot_device_type(name: str, path: str) -> BootDeviceType:
        """Classify a firmware boot entry using Aquila's domain enum."""
        combined = f"{name} {path}".casefold()

        if any(
            marker in combined
            for marker in ("nvme", "m.2", "pcie ssd")
        ):
            preferred_names = ("NVME", "NVMe")
            preferred_values = ("nvme",)
        elif any(
            marker in combined
            for marker in ("pxe", "network", "nic", "ipv4", "ipv6")
        ):
            preferred_names = ("PXE", "NETWORK")
            preferred_values = ("pxe", "network")
        elif any(
            marker in combined
            for marker in ("usb", "removable", "flash")
        ):
            preferred_names = ("USB", "REMOVABLE")
            preferred_values = ("usb", "removable")
        elif any(
            marker in combined
            for marker in ("cd", "dvd", "optical")
        ):
            preferred_names = ("CD", "CDROM", "OPTICAL")
            preferred_values = ("cd", "cdrom", "optical")
        elif any(
            marker in combined
            for marker in ("hdd", "hard drive", "sata", "ssd")
        ):
            preferred_names = ("HDD", "DISK", "STORAGE")
            preferred_values = ("hdd", "disk", "storage")
        elif any(
            marker in combined
            for marker in ("uefi", "\\efi\\", "/efi/")
        ):
            preferred_names = ("UEFI", "EFI")
            preferred_values = ("uefi", "efi")
        else:
            preferred_names = ("UNKNOWN", "OTHER")
            preferred_values = ("unknown", "other")

        normalized_names = {
            DellProvider._normalized_key(item)
            for item in preferred_names
        }
        normalized_values = {
            DellProvider._normalized_key(item)
            for item in preferred_values
        }

        for member in BootDeviceType:
            member_name = DellProvider._normalized_key(member.name)
            member_value = DellProvider._normalized_key(member.value)

            if (
                member_name in normalized_names
                or member_value in normalized_values
            ):
                return member

        for fallback_name in ("UNKNOWN", "OTHER"):
            fallback = getattr(BootDeviceType, fallback_name, None)
            if isinstance(fallback, BootDeviceType):
                return fallback

        return next(iter(BootDeviceType))


    def _wmi_change_boot_order(self, names: Sequence[str]) -> bool:
        """Attempt to change boot order using Dell WMI methods."""
        if platform.system() != "Windows" or not names:
            return False

        for namespace in self._preferred_wmi_namespaces():
            try:
                import wmi  # type: ignore[import-untyped]
            except ImportError:
                break

            try:
                connection = wmi.WMI(namespace=namespace)
                for class_name in (
                    "DCIM_BootService",
                    "DCIM_BootConfigSetting",
                ):
                    try:
                        instances = list(
                            connection.query(
                                f"SELECT * FROM {class_name}"
                            )
                        )
                    except Exception:
                        continue

                    for instance in instances:
                        for method_name in (
                            "ChangeBootOrder",
                            "SetBootOrder",
                            "SetBootSequence",
                        ):
                            method = getattr(
                                instance,
                                method_name,
                                None,
                            )
                            if not callable(method):
                                continue

                            argument_sets: Tuple[
                                Dict[str, Any],
                                ...,
                            ] = (
                                {"BootOrder": list(names)},
                                {"BootSequence": list(names)},
                                {"Source": list(names)},
                                {"Order": ",".join(names)},
                            )
                            for arguments in argument_sets:
                                try:
                                    result = method(**arguments)
                                except (TypeError, ValueError):
                                    continue
                                except Exception as exc:
                                    self._dell_logger.debug(
                                        "Dell WMI boot-order method "
                                        "failed: %s",
                                        self._sanitize_text(str(exc)),
                                    )
                                    continue

                                if self._wmi_result_succeeded(result):
                                    self.refresh()
                                    return True
            except Exception as exc:
                self._dell_logger.debug(
                    "Dell WMI boot-order service unavailable: %s",
                    self._sanitize_text(str(exc)),
                )

        return False

    @staticmethod
    def _read_efi_boot_number(variable_name: str) -> Optional[int]:
        """Read BootCurrent or BootNext from Linux EFI variables."""
        efivars = Path("/sys/firmware/efi/efivars")
        if not efivars.is_dir():
            return None

        try:
            candidates = list(efivars.glob(f"{variable_name}-*"))
        except OSError:
            return None

        for candidate in candidates:
            try:
                raw = candidate.read_bytes()
            except OSError:
                continue

            # efivarfs prepends four bytes of variable attributes.
            if len(raw) >= 6:
                return int.from_bytes(
                    raw[4:6],
                    byteorder="little",
                    signed=False,
                )

        return None

    # ------------------------------------------------------------------
    # Native hardware helpers
    # ------------------------------------------------------------------

    def _cpu_flags(self) -> Set[str]:
        """Return CPU feature flags exposed by the operating system."""
        flags: Set[str] = set()

        cpuinfo = Path("/proc/cpuinfo")
        try:
            if cpuinfo.is_file():
                text = cpuinfo.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
                for line in text.splitlines():
                    key, separator, value = line.partition(":")
                    if separator and key.strip().lower() in {
                        "flags",
                        "features",
                    }:
                        flags.update(value.lower().split())
        except OSError:
            pass

        if platform.system() == "Windows":
            rows = self._query_wmi_safe(
                r"root\cimv2",
                (
                    "SELECT VirtualizationFirmwareEnabled, "
                    "VMMonitorModeExtensions, SecondLevelAddressTranslation"
                    "Extensions FROM Win32_Processor"
                ),
            )
            for row in rows:
                data = self._object_to_dict(row)
                if self._coerce_bool(
                    self._mapping_value(
                        data,
                        ("VMMonitorModeExtensions",),
                    ),
                    default=False,
                ):
                    flags.add("vmx")
                if self._coerce_bool(
                    self._mapping_value(
                        data,
                        ("VirtualizationFirmwareEnabled",),
                    ),
                    default=False,
                ):
                    flags.add("virtualization_enabled")
                if self._coerce_bool(
                    self._mapping_value(
                        data,
                        ("SecondLevelAddressTranslationExtensions",),
                    ),
                    default=False,
                ):
                    flags.add("slat")

        return flags

    def _native_tpm_version(self) -> str:
        """Return a TPM specification version from native OS interfaces."""
        for candidate in (
            Path("/sys/class/tpm/tpm0/tpm_version_major"),
            Path("/sys/class/tpm/tpm0/device/tpm_version_major"),
        ):
            try:
                if candidate.is_file():
                    major = candidate.read_text(
                        encoding="ascii",
                        errors="ignore",
                    ).strip()
                    if major == "2":
                        return "2.0"
                    if major == "1":
                        return "1.2"
            except OSError:
                continue

        output = self._native_command_output(
            ["tpm2_getcap", "properties-fixed"],
            timeout=10.0,
        )
        if output:
            if re.search(
                r"TPM2_PT_FAMILY_INDICATOR|2\.0",
                output,
                flags=re.IGNORECASE,
            ):
                return "2.0"

        if platform.system() == "Windows":
            rows = self._query_wmi_safe(
                r"root\cimv2\Security\MicrosoftTpm",
                "SELECT SpecVersion FROM Win32_Tpm",
            )
            version = self._first_value(rows, ("SpecVersion",))
            if version:
                if "2.0" in version:
                    return "2.0"
                if "1.2" in version:
                    return "1.2"
                return version

        return ""

    def _native_command_output(
        self,
        command: Sequence[str],
        timeout: float,
    ) -> str:
        """Run an optional read-only native command."""
        if not command:
            return ""

        executable = shutil.which(command[0])
        if executable is None:
            return ""

        actual_command = [executable]
        actual_command.extend(command[1:])
        code, stdout, _ = self._run_process(
            actual_command,
            timeout=timeout,
        )
        return stdout if code == 0 else ""

    # ------------------------------------------------------------------
    # Configuration conversion
    # ------------------------------------------------------------------

    def _parse_configuration_payload(
        self,
        payload: str,
    ) -> Dict[str, Any]:
        """Convert CCTK INI, XML, or JSON configuration into a dictionary."""
        stripped = payload.strip()
        if not stripped:
            return {
                "provider": self.provider_name(),
                "attributes": {},
            }

        if stripped.startswith("{") or stripped.startswith("["):
            try:
                parsed_json = json.loads(stripped)
            except json.JSONDecodeError:
                parsed_json = None

            if isinstance(parsed_json, dict):
                return cast(Dict[str, Any], parsed_json)
            if isinstance(parsed_json, list):
                return {
                    "provider": self.provider_name(),
                    "attributes": cast(List[Any], parsed_json),
                }

        if stripped.startswith("<"):
            try:
                root = ET.fromstring(stripped)
            except ET.ParseError:
                root = None

            if root is not None:
                return {
                    "provider": self.provider_name(),
                    "format": "xml",
                    "root": root.tag,
                    "attributes": self._xml_element_to_data(root),
                }

        sections: Dict[str, Dict[str, str]] = {}
        current_section = "BIOS"
        sections[current_section] = {}

        for raw_line in payload.splitlines():
            line = raw_line.strip()
            if not line or line.startswith(("#", ";")):
                continue

            section_match = re.fullmatch(r"\[(.+)]", line)
            if section_match:
                current_section = section_match.group(1).strip()
                sections.setdefault(current_section, {})
                continue

            key, separator, value = line.partition("=")
            if not separator:
                key, separator, value = line.partition(":")
            if not separator:
                continue

            normalized_key = key.strip()
            if normalized_key:
                sections[current_section][normalized_key] = (
                    value.strip().strip('"')
                )

        return {
            "provider": self.provider_name(),
            "format": "cctk",
            "attributes": sections,
        }

    def _configuration_dict_to_cctk(
        self,
        configuration: Dict[str, Any],
    ) -> str:
        """Convert a structured configuration into CCTK INI syntax."""
        source: Any = configuration.get(
            "attributes",
            configuration,
        )
        lines: List[str] = []

        if isinstance(source, dict):
            typed_source = cast(Dict[str, Any], source)
            scalar_items: Dict[str, Any] = {}
            section_items: Dict[str, Dict[str, Any]] = {}

            for key, value in typed_source.items():
                if isinstance(value, dict):
                    section_items[str(key)] = cast(Dict[str, Any], value)
                elif isinstance(value, (str, int, float, bool)):
                    scalar_items[str(key)] = value

            if scalar_items:
                lines.append("[BIOS]")
                for key in sorted(scalar_items):
                    lines.append(
                        f"{key}={self._configuration_scalar(scalar_items[key])}"
                    )

            for section in sorted(section_items):
                lines.append(f"[{section}]")
                for key in sorted(section_items[section]):
                    value = section_items[section][key]
                    if isinstance(value, (str, int, float, bool)):
                        lines.append(
                            f"{key}={self._configuration_scalar(value)}"
                        )

        elif isinstance(source, list):
            lines.append("[BIOS]")
            for entry in cast(List[Any], source):
                if not isinstance(entry, dict):
                    continue
                typed_entry = cast(Dict[str, Any], entry)
                name = self._mapping_value(
                    typed_entry,
                    (
                        "AttributeName",
                        "Name",
                        "ElementName",
                    ),
                )
                value = self._mapping_value(
                    typed_entry,
                    (
                        "CurrentValue",
                        "Value",
                        "AttributeValue",
                    ),
                )
                if name:
                    lines.append(f"{name}={value}")

        return "\n".join(lines).strip() + ("\n" if lines else "")

    @staticmethod
    def _configuration_scalar(value: Any) -> str:
        """Format a scalar safely for a CCTK configuration file."""
        if isinstance(value, bool):
            return "Enabled" if value else "Disabled"

        text = str(value)
        text = text.replace("\r", " ").replace("\n", " ")
        if any(character in text for character in ("=", ";", "#")):
            return json.dumps(text, ensure_ascii=False)
        return text

    def _configuration_to_xml(
        self,
        configuration: Dict[str, Any],
    ) -> str:
        """Serialize a configuration dictionary as deterministic XML."""
        root = ET.Element("DellBIOSConfiguration")
        root.set("provider", self.provider_name())
        self._append_xml_value(root, "Configuration", configuration)

        try:
            ET.indent(root, space="  ")
        except AttributeError:
            pass

        return ET.tostring(
            root,
            encoding="unicode",
            xml_declaration=True,
        )

    def _append_xml_value(
        self,
        parent: ET.Element,
        name: str,
        value: Any,
    ) -> None:
        """Append a JSON-compatible value to an XML tree."""
        safe_name = re.sub(
            r"[^A-Za-z0-9_.-]+",
            "_",
            name,
        ).strip("_") or "item"

        element = ET.SubElement(parent, safe_name)
        if value is None:
            element.set("nil", "true")
            return

        if isinstance(value, dict):
            typed_value = cast(Dict[Any, Any], value)
            for key in sorted(typed_value, key=str):
                self._append_xml_value(
                    element,
                    str(key),
                    typed_value[key],
                )
            return

        if isinstance(value, (list, tuple, set)):
            for item in cast("List[Any] | tuple[Any, ...] | set[Any]", value):
                self._append_xml_value(element, "item", item)
            return

        if isinstance(value, bool):
            element.text = "true" if value else "false"
            return

        element.text = str(value)

    def _xml_element_to_data(self, element: ET.Element) -> Any:
        """Convert an XML element tree into JSON-compatible data."""
        children = list(element)
        if not children:
            if element.attrib:
                return {
                    "attributes": dict(element.attrib),
                    "text": (element.text or "").strip(),
                }
            return (element.text or "").strip()

        result: Dict[str, Any] = {}
        if element.attrib:
            result["@attributes"] = dict(element.attrib)

        for child in children:
            value = self._xml_element_to_data(child)
            if child.tag in result:
                existing = result[child.tag]
                if not isinstance(existing, list):
                    result[child.tag] = [existing]
                result[child.tag].append(value)
            else:
                result[child.tag] = value

        text = (element.text or "").strip()
        if text:
            result["#text"] = text

        return result

    def _apply_configuration_with_wmi(
        self,
        configuration: Dict[str, Any],
        admin_password: Optional[str],
    ) -> bool:
        """Apply scalar BIOS attributes using Dell WMI as a fallback."""
        # ``configuration`` originates from a parsed configuration payload
        # (JSON, XML-derived, or CCTK INI) whose shape is only known once
        # it has actually been inspected -- the surrounding ``isinstance``
        # checks are the real type discrimination, so the branches below
        # cast to the shape each one has already confirmed rather than
        # letting pyright's ``Any``-narrowed-to-bare-``dict``/``list``
        # inference spread "Unknown" through the rest of the method.
        attributes: Any = configuration.get(
            "attributes",
            configuration,
        )
        flattened: Dict[str, str] = {}

        if isinstance(attributes, dict):
            typed_attributes = cast(Dict[str, Any], attributes)
            for key, value in typed_attributes.items():
                if isinstance(value, dict):
                    typed_value = cast(Dict[str, Any], value)
                    for child_key, child_value in typed_value.items():
                        if isinstance(
                            child_value,
                            (str, int, float, bool),
                        ):
                            flattened[str(child_key)] = str(child_value)
                elif isinstance(value, (str, int, float, bool)):
                    flattened[str(key)] = str(value)

        elif isinstance(attributes, list):
            typed_entries = cast(List[Any], attributes)
            for entry in typed_entries:
                if not isinstance(entry, dict):
                    continue

                typed_entry = cast(Dict[str, Any], entry)
                name = self._mapping_value(
                    typed_entry,
                    (
                        "AttributeName",
                        "Name",
                        "ElementName",
                    ),
                )
                value = self._mapping_value(
                    typed_entry,
                    (
                        "CurrentValue",
                        "Value",
                        "AttributeValue",
                    ),
                )
                if name:
                    flattened[name] = value

        if not flattened:
            return False

        applied = 0
        for name, value in flattened.items():
            if self._set_wmi_attribute(
                name,
                value,
                admin_password=admin_password,
            ):
                applied += 1
            else:
                return False

        if applied:
            self.refresh()
        return applied == len(flattened)

    # ------------------------------------------------------------------
    # Temporary files and credentials
    # ------------------------------------------------------------------

    def _new_temporary_file(self, suffix: str) -> Path:
        """Create and track a private temporary configuration file."""
        descriptor, filename = tempfile.mkstemp(
            prefix="aquila-dell-",
            suffix=suffix,
        )
        os.close(descriptor)

        path = Path(filename)
        self._temporary_files.add(path)
        self._restrict_file_permissions(path)
        return path

    @staticmethod
    def _restrict_file_permissions(path: Path) -> None:
        """Restrict a temporary file to the current user where supported."""
        try:
            path.chmod(0o600)
        except OSError:
            return

    def _delete_temporary_file(self, path: Path) -> None:
        """Best-effort overwrite and deletion of a temporary file."""
        try:
            if path.is_file():
                size = path.stat().st_size
                if size > 0:
                    with path.open("r+b", buffering=0) as stream:
                        remaining = size
                        zero_block = b"\x00" * min(65536, size)
                        while remaining > 0:
                            chunk = zero_block[: min(len(zero_block), remaining)]
                            stream.write(chunk)
                            remaining -= len(chunk)
                        stream.flush()
                        try:
                            os.fsync(stream.fileno())
                        except OSError:
                            pass
                path.unlink(missing_ok=True)
        except OSError as exc:
            self._dell_logger.warning(
                "Unable to delete a Dell temporary file: %s",
                self._sanitize_text(str(exc)),
            )
        finally:
            self._temporary_files.discard(path)

    def _remove_temporary_files(self) -> None:
        """Delete every tracked Dell configuration file."""
        for path in tuple(self._temporary_files):
            self._delete_temporary_file(path)
        self._temporary_files.clear()

    def _remember_credential(self, secret: str) -> bytearray:
        """Create a mutable short-lived credential buffer."""
        buffer = bytearray(secret.encode("utf-8", errors="strict"))
        self._credential_buffers.append(buffer)
        return buffer

    def _clear_credentials(self) -> None:
        """Overwrite tracked mutable credential buffers and clear references."""
        for buffer in self._credential_buffers:
            for index in range(len(buffer)):
                buffer[index] = 0
        self._credential_buffers.clear()

        for attribute_name in (
            "_admin_password",
            "_system_password",
            "_drive_password",
            "_password",
        ):
            if hasattr(self, attribute_name):
                try:
                    setattr(self, attribute_name, None)
                except (AttributeError, TypeError):
                    continue

    # ------------------------------------------------------------------
    # Parsing, normalization, and serialization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalized(value: Any) -> str:
        """Return a case-folded, whitespace-normalized string."""
        return re.sub(
            r"\s+",
            " ",
            str(value or "").strip().casefold(),
        )

    @staticmethod
    def _normalized_key(value: Any) -> str:
        """Normalize a firmware attribute name for matching."""
        return re.sub(
            r"[^a-z0-9]+",
            "",
            str(value or "").casefold(),
        )

    def _clean_attribute_value(
        self,
        value: str,
        attribute: str,
    ) -> str:
        """Remove common CCTK decorations from an attribute value."""
        cleaned = value.strip().strip('"')
        prefix = re.compile(
            rf"^(?:--)?{re.escape(attribute)}\s*[:=]\s*",
            flags=re.IGNORECASE,
        )
        cleaned = prefix.sub("", cleaned).strip().strip('"')
        return cleaned

    def _password_is_set(self, attribute: str) -> bool:
        """Interpret Dell password-presence output without exposing secrets."""
        value = self._query_attribute(attribute)
        normalized = self._normalized(value)

        if not normalized:
            return False

        negative_markers = (
            "not set",
            "not installed",
            "not configured",
            "no password",
            "disabled",
            "clear",
            "none",
        )
        if any(marker in normalized for marker in negative_markers):
            return False

        positive_markers = (
            "set",
            "installed",
            "configured",
            "enabled",
            "password exists",
        )
        return any(
            marker in normalized
            for marker in positive_markers
        )

    @staticmethod
    def _coerce_bool(
        value: Any,
        default: bool = False,
    ) -> bool:
        """Convert firmware and WMI values to a boolean."""
        if value is None:
            return default

        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            return value != 0

        if isinstance(value, (list, tuple, set)):
            if not value:
                return default
            typed_value = cast(
                "list[Any] | tuple[Any, ...] | set[Any]", value
            )
            return DellProvider._coerce_bool(
                next(iter(typed_value)),
                default=default,
            )

        normalized = DellProvider._normalized(value)
        if normalized in _TRUE_VALUES:
            return True
        if normalized in _FALSE_VALUES:
            return False

        if any(
            marker in normalized
            for marker in (
                "not enabled",
                "not active",
                "not activated",
                "not present",
                "not set",
                "not configured",
                "permanently disabled",
            )
        ):
            return False

        if any(
            marker in normalized
            for marker in (
                "enabled",
                "active",
                "activated",
                "present",
                "configured",
            )
        ):
            return True

        return default

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        """Convert a firmware or WMI value to an integer."""
        if value is None or isinstance(value, bool):
            return None

        if isinstance(value, int):
            return value

        if isinstance(value, float):
            return int(value)

        match = re.search(
            r"[-+]?\d+",
            str(value).replace(",", ""),
        )
        if not match:
            return None

        try:
            return int(match.group(0))
        except ValueError:
            return None

    @staticmethod
    def _mapping_value(
        mapping: Dict[str, Any],
        names: Sequence[str],
    ) -> str:
        """Return the first nonempty mapping value matching any name."""
        normalized_mapping = {
            DellProvider._normalized_key(key): value
            for key, value in mapping.items()
        }

        for name in names:
            value = mapping.get(name)
            if value is None:
                value = normalized_mapping.get(
                    DellProvider._normalized_key(name)
                )

            if value is None:
                continue

            if isinstance(value, bytes):
                text = value.decode(
                    "utf-8",
                    errors="replace",
                ).strip()
            elif isinstance(value, (list, tuple, set)):
                typed_value = cast(
                    "list[Any] | tuple[Any, ...] | set[Any]", value
                )
                text = ", ".join(
                    str(item).strip()
                    for item in typed_value
                    if str(item).strip()
                )
            else:
                text = str(value).strip()

            if text:
                return text

        return ""

    def _first_value(
        self,
        rows: Sequence[Any],
        names: Sequence[str],
    ) -> str:
        """Return the first matching property from a sequence of rows."""
        for row in rows:
            value = self._mapping_value(
                self._object_to_dict(row),
                names,
            )
            if value:
                return value
        return ""

    def _object_to_dict(self, value: Any) -> Dict[str, Any]:
        """Convert WMI, COM, and mapping objects into plain dictionaries."""
        if value is None:
            return {}

        if isinstance(value, dict):
            return {
                str(key): self._safe_property_value(item)
                for key, item in cast(Dict[Any, Any], value).items()
            }

        result: Dict[str, Any] = {}

        properties = getattr(value, "properties", None)
        if isinstance(properties, dict):
            for key, item in cast(Dict[Any, Any], properties).items():
                result[str(key)] = self._safe_property_value(item)

        property_names = getattr(value, "_properties", None)
        if isinstance(property_names, (list, tuple, set)):
            typed_property_names = cast(
                "list[Any] | tuple[Any, ...] | set[Any]", property_names
            )
            for name in typed_property_names:
                try:
                    result[str(name)] = self._safe_property_value(
                        getattr(value, str(name))
                    )
                except Exception:
                    continue

        try:
            com_properties = value.Properties_
            for property_item in com_properties:
                try:
                    property_name = str(property_item.Name)
                    result[property_name] = self._safe_property_value(
                        property_item.Value
                    )
                except Exception:
                    continue
        except Exception:
            pass

        instance_state = getattr(value, "__dict__", None)
        if isinstance(instance_state, dict):
            for key, item in cast(Dict[Any, Any], instance_state).items():
                if str(key).startswith("_"):
                    continue
                result.setdefault(
                    str(key),
                    self._safe_property_value(item),
                )

        if result:
            return result

        for name in dir(value):
            if name.startswith("_"):
                continue

            try:
                item = getattr(value, name)
            except Exception:
                continue

            if callable(item):
                continue

            if isinstance(
                item,
                (
                    str,
                    int,
                    float,
                    bool,
                    bytes,
                    list,
                    tuple,
                    set,
                    dict,
                    date,
                    datetime,
                    type(None),
                ),
            ):
                result[name] = self._safe_property_value(item)

        return result

    def _safe_property_value(self, value: Any) -> Any:
        """Convert an arbitrary backend property to a safe plain value."""
        if value is None or isinstance(
            value,
            (str, int, float, bool),
        ):
            return value

        if isinstance(value, bytes):
            return value.decode(
                "utf-8",
                errors="replace",
            )

        if isinstance(value, (date, datetime)):
            return value.isoformat()

        if isinstance(value, dict):
            return {
                str(key): self._safe_property_value(item)
                for key, item in cast(Dict[Any, Any], value).items()
            }

        if isinstance(value, (list, tuple, set)):
            return [
                self._safe_property_value(item)
                for item in cast(
                    "list[Any] | tuple[Any, ...] | set[Any]", value
                )
            ]

        return str(value)

    @staticmethod
    def _normalize_firmware_date(
        value: str,
    ) -> Optional[date]:
        """Convert SMBIOS, WMI, or CCTK dates to a date object."""
        normalized = value.strip()
        if not normalized:
            return None

        # WMI CIM_DATETIME: YYYYMMDDHHMMSS.mmmmmmsUUU
        wmi_match = re.match(
            r"^(\d{4})(\d{2})(\d{2})\d{6}\.",
            normalized,
        )
        if wmi_match:
            try:
                return date(
                    int(wmi_match.group(1)),
                    int(wmi_match.group(2)),
                    int(wmi_match.group(3)),
                )
            except ValueError:
                return None

        formats = (
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%m/%d/%Y",
            "%m-%d-%Y",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%m/%d/%y",
            "%Y%m%d",
            "%b %d %Y",
            "%B %d %Y",
        )
        for format_string in formats:
            try:
                return datetime.strptime(
                    normalized,
                    format_string,
                ).date()
            except ValueError:
                continue

        iso_candidate = normalized.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(iso_candidate).date()
        except ValueError:
            return None

    @staticmethod
    def _construct_model(
        model_type: Any,
        values: Dict[str, Any],
    ) -> Any:
        """Construct a domain model using properties accepted by its API."""
        try:
            signature = inspect.signature(model_type)
        except (TypeError, ValueError):
            return model_type(**values)

        parameters = signature.parameters
        accepts_arbitrary_keywords = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )

        if accepts_arbitrary_keywords:
            return model_type(**values)

        accepted_values = {
            name: value
            for name, value in values.items()
            if name in parameters
        }

        return model_type(**accepted_values)

    @classmethod
    def _serialize_value(cls, value: Any) -> Any:
        """Convert Dell domain and backend values to JSON-safe data."""
        if value is None or isinstance(
            value,
            (str, int, float, bool),
        ):
            return value

        if isinstance(value, bytes):
            return f"<{len(value)} bytes>"

        if isinstance(value, (date, datetime)):
            return value.isoformat()

        enum_value = getattr(value, "value", None)
        if enum_value is not None and not callable(enum_value):
            return cls._serialize_value(enum_value)

        if isinstance(value, dict):
            return {
                str(key): cls._serialize_value(item)
                for key, item in cast(Dict[Any, Any], value).items()
            }

        if isinstance(value, (list, tuple, set, frozenset)):
            return [
                cls._serialize_value(item)
                for item in cast(
                    "list[Any] | tuple[Any, ...] | set[Any] | frozenset[Any]",
                    value,
                )
            ]

        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            try:
                return cls._serialize_value(model_dump())
            except Exception:
                return str(value)

        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            try:
                return cls._serialize_value(to_dict())
            except Exception:
                return str(value)

        dataclass_fields = getattr(
            value,
            "__dataclass_fields__",
            None,
        )
        if isinstance(dataclass_fields, dict):
            return {
                str(name): cls._serialize_value(
                    getattr(value, str(name))
                )
                for name in cast(Dict[Any, Any], dataclass_fields)
            }

        public_state = getattr(value, "__dict__", None)
        if isinstance(public_state, dict):
            return {
                str(key): cls._serialize_value(item)
                for key, item in cast(Dict[Any, Any], public_state).items()
                if not str(key).startswith("_")
            }

        return str(value)

    @staticmethod
    def _firmware_value(
        firmware: FirmwareInformation,
        name: str,
    ) -> Any:
        """Return a firmware model property without assuming model internals."""
        try:
            return getattr(firmware, name)
        except AttributeError:
            pass

        model_dump = getattr(firmware, "model_dump", None)
        if callable(model_dump):
            try:
                data = model_dump()
                if isinstance(data, dict):
                    return cast(Dict[str, Any], data).get(name, "")
            except Exception:
                return ""

        to_dict = getattr(firmware, "to_dict", None)
        if callable(to_dict):
            try:
                data = to_dict()
                if isinstance(data, dict):
                    return cast(Dict[str, Any], data).get(name, "")
            except Exception:
                return ""

        return ""

    def _sanitize_command(
        self,
        command: Sequence[str],
        secrets: Sequence[str] = (),
    ) -> str:
        """Return a command representation with credential values masked."""
        sanitized: List[str] = []
        redact_next = False

        for argument in command:
            text = str(argument)

            if redact_next:
                sanitized.append("<redacted>")
                redact_next = False
                continue

            option, separator, _ = text.partition("=")
            normalized_option = option.casefold()

            is_secret_option = any(
                normalized_option == secret_name.casefold()
                for secret_name in _SECRET_OPTION_NAMES
            )
            if is_secret_option:
                if separator:
                    sanitized.append(f"{option}=<redacted>")
                else:
                    sanitized.append(option)
                    redact_next = True
                continue

            sanitized.append(
                self._sanitize_text(
                    text,
                    secrets,
                )
            )

        return subprocess.list2cmdline(sanitized)

    def _sanitize_text(
        self,
        text: str,
        secrets: Sequence[Optional[str]] = (),
    ) -> str:
        """Redact firmware passwords and credential-bearing arguments."""
        sanitized = str(text)

        for secret in secrets:
            if secret:
                sanitized = sanitized.replace(
                    secret,
                    "<redacted>",
                )

        secret_option_pattern = "|".join(
            re.escape(option.lstrip("-"))
            for option in _SECRET_OPTION_NAMES
        )
        sanitized = re.sub(
            (
                rf"(?i)(--(?:{secret_option_pattern})"
                rf"(?:\s*=\s*|\s+))"
                rf"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
            ),
            r"\1<redacted>",
            sanitized,
        )

        sanitized = re.sub(
            (
                r"(?i)\b("
                r"admin(?:istrator)?[_ -]?password|"
                r"system[_ -]?password|"
                r"drive[_ -]?password|"
                r"hdd[_ -]?password|"
                r"nvme[_ -]?password|"
                r"authorizationtoken"
                r")\s*[:=]\s*"
                r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
            ),
            r"\1=<redacted>",
            sanitized,
        )

        return sanitized

    # ------------------------------------------------------------------
    # Lifecycle cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Securely release Dell provider resources.

        Cleanup is idempotent. Temporary configuration files are removed,
        mutable credential buffers are overwritten, cached values are
        discarded, and WMI handles are detached.
        """
        with self._execution_lock:
            if self._closed:
                self._remove_temporary_files()
                self._clear_credentials()
                self._wmi_handles.clear()
                return

            self.disconnect()

            try:
                super().close()
            except (AttributeError, NotImplementedError):
                self._connected = False
                self._closed = True
            finally:
                self._remove_temporary_files()
                self._clear_credentials()
                self._attribute_cache.clear()
                self._wmi_handles.clear()
                self._wmi_namespace = None
                self._sysfs_root = None
                self._cctk_path = None
                self._connected = False
                self._closed = True


__all__ = [
    "DellProvider",
    "PROVIDER_VERSION",
]

