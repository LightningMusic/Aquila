"""
Project Aquila
=============

Network Adapter Detection

Implements REQ-INS-009 (enumerate all network adapters), REQ-INS-010
(identify wired Ethernet interfaces), REQ-INS-011 (detect wireless
networking interfaces), and REQ-INS-024 (verify Ethernet link status).

WMI sources: ``Win32_NetworkAdapter`` (``root\\cimv2``) for adapter
identity/type/speed, joined to ``Win32_NetworkAdapterConfiguration``
(same namespace, joined on ``Index``) for assigned IP addresses, and
to ``Win32_PnPSignedDriver`` (joined on device path, the same
substring-match technique ``hardware.smart`` uses to correlate
``Win32_DiskDrive`` with the SMART failure-prediction classes) for
driver version.

``Win32_NetworkAdapter.NetConnectionStatus`` is a confirmed, documented
14-value WMI enumeration (0=Disconnected through 13=Other); Aquila's
own ``common.enums.EthernetStatus`` intentionally models only three
coarse states (``UNPLUGGED``/``LINK_DETECTED``/``ACTIVE``), since that
is everything REQ-INS-024 and REQ-NET-003/004 need to decide whether
provisioning may proceed. The mapping from the 14 WMI values down to
those 3 states is documented at the mapping table below.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import re
from typing import Any, Dict

from common.enums import EthernetStatus
from models.hardware import NetworkAdapter, NetworkAdapterType

from . import query_wmi_safe, safe_property_value

_WMI_NAMESPACE = r"root\cimv2"

_ADAPTER_QUERY = (
    "SELECT Name, Description, AdapterType, MACAddress, PhysicalAdapter, "
    "NetEnabled, Speed, NetConnectionStatus, Index, PNPDeviceID "
    "FROM Win32_NetworkAdapter"
)
_CONFIG_QUERY = (
    "SELECT Index, IPAddress FROM Win32_NetworkAdapterConfiguration "
    "WHERE IPEnabled = TRUE"
)
_DRIVER_QUERY = "SELECT DeviceID, DriverVersion FROM Win32_PnPSignedDriver"

# Win32_NetworkAdapter.NetConnectionStatus -- confirmed WMI enumeration.
_STATUS_DISCONNECTED = 0
_STATUS_CONNECTING = 1
_STATUS_CONNECTED = 2
_STATUS_DISCONNECTING = 3
_STATUS_HARDWARE_NOT_PRESENT = 4
_STATUS_HARDWARE_DISABLED = 5
_STATUS_HARDWARE_MALFUNCTION = 6
_STATUS_MEDIA_DISCONNECTED = 7
_STATUS_AUTHENTICATING = 8
_STATUS_AUTHENTICATION_SUCCEEDED = 9
_STATUS_AUTHENTICATION_FAILED = 10
_STATUS_INVALID_ADDRESS = 11
_STATUS_CREDENTIALS_REQUIRED = 12
_STATUS_OTHER = 13

# The 14 confirmed NetConnectionStatus values, collapsed to Aquila's
# 3-state EthernetStatus. States implying no physical link at all map
# to UNPLUGGED; states implying a physical link that is not yet fully
# passing traffic map to LINK_DETECTED; only a fully connected or
# successfully authenticated link maps to ACTIVE.
_LINK_STATUS_MAP: Dict[int, EthernetStatus] = {
    _STATUS_DISCONNECTED: EthernetStatus.UNPLUGGED,
    _STATUS_CONNECTING: EthernetStatus.LINK_DETECTED,
    _STATUS_CONNECTED: EthernetStatus.ACTIVE,
    _STATUS_DISCONNECTING: EthernetStatus.LINK_DETECTED,
    _STATUS_HARDWARE_NOT_PRESENT: EthernetStatus.UNPLUGGED,
    _STATUS_HARDWARE_DISABLED: EthernetStatus.UNPLUGGED,
    _STATUS_HARDWARE_MALFUNCTION: EthernetStatus.UNPLUGGED,
    _STATUS_MEDIA_DISCONNECTED: EthernetStatus.UNPLUGGED,
    _STATUS_AUTHENTICATING: EthernetStatus.LINK_DETECTED,
    _STATUS_AUTHENTICATION_SUCCEEDED: EthernetStatus.ACTIVE,
    _STATUS_AUTHENTICATION_FAILED: EthernetStatus.LINK_DETECTED,
    _STATUS_INVALID_ADDRESS: EthernetStatus.LINK_DETECTED,
    _STATUS_CREDENTIALS_REQUIRED: EthernetStatus.LINK_DETECTED,
    _STATUS_OTHER: EthernetStatus.LINK_DETECTED,
}


class NetworkDetector:
    """Detects network adapters without modifying system or network state."""

    def detect(self) -> list[NetworkAdapter]:
        """
        Return every network adapter enumerated on the target system.

        Returns an empty list -- honestly, not a fabricated adapter --
        on any non-Windows platform or WMI failure.
        """

        adapter_rows = query_wmi_safe(_WMI_NAMESPACE, _ADAPTER_QUERY)
        config_rows = query_wmi_safe(_WMI_NAMESPACE, _CONFIG_QUERY)
        driver_rows = query_wmi_safe(_WMI_NAMESPACE, _DRIVER_QUERY)

        ip_by_index = self._index_ip_addresses(config_rows)

        return [
            self._adapter_from_row(row, ip_by_index, driver_rows)
            for row in adapter_rows
        ]

    @staticmethod
    def _index_ip_addresses(config_rows: list[Any]) -> Dict[int, list[str]]:
        indexed: Dict[int, list[str]] = {}
        for row in config_rows:
            raw_index = safe_property_value(row, "Index")
            try:
                index = int(raw_index) if raw_index is not None else None
            except (TypeError, ValueError):
                index = None
            if index is None:
                continue

            raw_ips = safe_property_value(row, "IPAddress")
            if raw_ips is None:
                continue

            # The ``wmi`` package returns tuples/lists natively; raw
            # COM automation returns a VARIANT array that behaves the
            # same way when iterated.
            try:
                ip_list = [str(ip) for ip in raw_ips if ip]
            except TypeError:
                ip_list = [str(raw_ips)]

            indexed[index] = ip_list

        return indexed

    def _adapter_from_row(
        self,
        row: object,
        ip_by_index: Dict[int, list[str]],
        driver_rows: list[Any],
    ) -> NetworkAdapter:
        name = str(safe_property_value(row, "Name") or "")
        description = str(safe_property_value(row, "Description") or "")
        adapter_type_raw = str(safe_property_value(row, "AdapterType") or "")

        adapter_type = self._classify(name, description, adapter_type_raw)

        raw_index = safe_property_value(row, "Index")
        try:
            index = int(raw_index) if raw_index is not None else None
        except (TypeError, ValueError):
            index = None

        speed_raw = safe_property_value(row, "Speed")
        speed_mbps: int | None = None
        if speed_raw:
            try:
                speed_mbps = int(int(speed_raw) / 1_000_000)
            except (TypeError, ValueError):
                speed_mbps = None

        status_raw = safe_property_value(row, "NetConnectionStatus")
        link_status: EthernetStatus | None = None
        if adapter_type is NetworkAdapterType.ETHERNET and status_raw is not None:
            try:
                link_status = _LINK_STATUS_MAP.get(int(status_raw))
            except (TypeError, ValueError):
                link_status = None

        pnp_device_id = str(safe_property_value(row, "PNPDeviceID") or "")

        return NetworkAdapter(
            name=name,
            description=description,
            adapter_type=adapter_type,
            mac_address=str(safe_property_value(row, "MACAddress") or ""),
            is_physical=bool(safe_property_value(row, "PhysicalAdapter")),
            is_enabled=bool(safe_property_value(row, "NetEnabled")),
            speed_mbps=speed_mbps,
            driver_version=self._driver_version(driver_rows, pnp_device_id),
            link_status=link_status,
            ip_addresses=ip_by_index.get(index, []) if index is not None else [],
        )

    @staticmethod
    def _classify(
        name: str, description: str, adapter_type_raw: str
    ) -> NetworkAdapterType:
        combined = f"{name} {description} {adapter_type_raw}".lower()

        if "bluetooth" in combined:
            return NetworkAdapterType.BLUETOOTH

        if re.search(r"\b(wireless|wi-?fi|802\.11|wlan)\b", combined):
            return NetworkAdapterType.WIRELESS

        if "loopback" in combined:
            return NetworkAdapterType.LOOPBACK

        if re.search(r"\b(virtual|vmware|hyper-v|vethernet|tap|tunnel)\b", combined):
            return NetworkAdapterType.VIRTUAL

        if "ethernet" in combined or "802.3" in combined:
            return NetworkAdapterType.ETHERNET

        return NetworkAdapterType.UNKNOWN

    @staticmethod
    def _driver_version(driver_rows: list[Any], pnp_device_id: str) -> str:
        if not pnp_device_id:
            return ""

        normalized_target = re.sub(r"[^0-9A-Za-z]", "", pnp_device_id).lower()
        if not normalized_target:
            return ""

        for row in driver_rows:
            device_id = str(safe_property_value(row, "DeviceID") or "")
            normalized_device_id = re.sub(r"[^0-9A-Za-z]", "", device_id).lower()
            if normalized_device_id == normalized_target:
                return str(safe_property_value(row, "DriverVersion") or "")

        return ""


__all__ = ["NetworkDetector"]
