"""
Project Aquila
=============

Battery Detection

Implements REQ-INS-020 (retrieve battery health information for
supported portable systems) and REQ-INS-021 (determine whether battery
charge threshold configuration is supported).

WMI sources
-----------
``Win32_Battery`` (``root\\cimv2``) is the primary, Microsoft-confirmed
source for presence, estimated charge/runtime, and
``BatteryStatus``/``DesignCapacity``/``FullChargeCapacity``. Design
capacity and cycle count are supplemented, when available, from the
ACPI Control Method Battery WMI classes in ``root\\wmi``
(``BatteryStaticData``/``BatteryCycleCount``) -- the same interface
Windows' own ``powercfg /batteryreport`` reads from. Those two classes
are not part of Microsoft's officially published WMI schema
documentation, so -- exactly like ``hardware.smart``'s
``MSStorageDriver_FailurePredictData`` parsing -- they are treated as
a best-effort supplement: a query failure or missing property falls
back to ``Win32_Battery``'s own value rather than raising or
fabricating data.

Charge-threshold support (REQ-INS-021) is a firmware capability, not
an operating-system one -- it is already correctly determined by the
active ``bios`` provider (``BIOSProvider.battery_charge_limit_supported()``),
so this detector asks that subsystem directly instead of re-deriving a
second, competing answer.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from typing import Any

from common.constants.logging import HARDWARE_LOGGER
from common.enums import BatteryHealth
from models.hardware import BatteryInfo

from . import query_wmi_safe, safe_property_value

# Logs through the dedicated "aquila.hardware" logger (not
# logging.getLogger(__name__), which would create an unrelated
# "hardware.battery" logger with no attached handler) so records
# actually land in LogManager's hardware.log file -- LogManager only
# attaches handlers to the exact logger names in
# common.constants.logging.
logger = logging.getLogger(HARDWARE_LOGGER)

_CIMV2_NAMESPACE = r"root\cimv2"
_ACPI_NAMESPACE = r"root\wmi"

_BATTERY_QUERY = (
    "SELECT DeviceID, Name, Chemistry, BatteryStatus, "
    "EstimatedChargeRemaining, EstimatedRunTime, DesignCapacity, "
    "FullChargeCapacity FROM Win32_Battery"
)
_STATIC_DATA_QUERY = (
    "SELECT InstanceName, DesignedCapacity, SerialNumber, ManufacturerName "
    "FROM BatteryStaticData"
)
_CYCLE_COUNT_QUERY = "SELECT InstanceName, CycleCount FROM BatteryCycleCount"

# Health-percent (full-charge / design capacity) thresholds. These are
# Aquila-defined operational thresholds -- no SMBIOS/ACPI standard
# defines them -- chosen to be conservative for hardware being
# prepared for a second-life production deployment.
_HEALTH_THRESHOLD_GOOD = 80.0
_HEALTH_THRESHOLD_FAIR = 50.0
_HEALTH_THRESHOLD_POOR = 20.0


class BatteryDetector:
    """Detects battery presence and health without modifying system state."""

    def detect(self) -> BatteryInfo:
        """
        Return a ``BatteryInfo`` record for the target system.

        Returns ``BatteryInfo(present=False)`` -- the correct, complete
        record for a desktop/server system or any detection failure --
        rather than raising.
        """

        rows = query_wmi_safe(_CIMV2_NAMESPACE, _BATTERY_QUERY)
        if not rows:
            return BatteryInfo(present=False)

        row = rows[0]
        device_id = str(safe_property_value(row, "DeviceID") or "")

        design_capacity_raw = safe_property_value(row, "DesignCapacity")
        full_charge_capacity_raw = safe_property_value(row, "FullChargeCapacity")

        design_capacity_mwh = (
            int(design_capacity_raw) if design_capacity_raw else None
        )
        full_charge_capacity_mwh = (
            int(full_charge_capacity_raw) if full_charge_capacity_raw else None
        )
        cycle_count: int | None = None

        static_row = self._match_acpi_instance(
            query_wmi_safe(_ACPI_NAMESPACE, _STATIC_DATA_QUERY), device_id
        )
        if static_row is not None:
            acpi_design_capacity = safe_property_value(static_row, "DesignedCapacity")
            if acpi_design_capacity:
                design_capacity_mwh = int(acpi_design_capacity)

        cycle_row = self._match_acpi_instance(
            query_wmi_safe(_ACPI_NAMESPACE, _CYCLE_COUNT_QUERY), device_id
        )
        if cycle_row is not None:
            acpi_cycle_count = safe_property_value(cycle_row, "CycleCount")
            if acpi_cycle_count is not None:
                cycle_count = int(acpi_cycle_count)

        health = self._compute_health(design_capacity_mwh, full_charge_capacity_mwh)

        return BatteryInfo(
            present=True,
            manufacturer="",  # Win32_Battery exposes no manufacturer field; ACPI BatteryStaticData.ManufacturerName is frequently blank/unreliable in practice and is intentionally not substituted here.
            serial_number="",
            chemistry=str(safe_property_value(row, "Chemistry") or ""),
            design_capacity_mwh=design_capacity_mwh,
            full_charge_capacity_mwh=full_charge_capacity_mwh,
            current_capacity_mwh=None,
            cycle_count=cycle_count,
            health=health,
            charge_threshold_supported=self._charge_threshold_supported(),
        )

    @staticmethod
    def _compute_health(
        design_capacity_mwh: int | None, full_charge_capacity_mwh: int | None
    ) -> BatteryHealth:
        if not design_capacity_mwh or full_charge_capacity_mwh is None:
            return BatteryHealth.UNKNOWN

        health_percent = (full_charge_capacity_mwh / design_capacity_mwh) * 100

        if health_percent >= _HEALTH_THRESHOLD_GOOD:
            return BatteryHealth.GOOD
        if health_percent >= _HEALTH_THRESHOLD_FAIR:
            return BatteryHealth.FAIR
        if health_percent >= _HEALTH_THRESHOLD_POOR:
            return BatteryHealth.POOR
        return BatteryHealth.REPLACE

    @staticmethod
    def _match_acpi_instance(rows: list[Any], device_id: str) -> Any | None:
        if not device_id or not rows:
            return None

        # ACPI battery InstanceName strings embed the PNP device path;
        # a single-battery system (the overwhelming majority of
        # laptops) has exactly one row in each class, so an unmatched
        # device_id still falls back to that row rather than reporting
        # nothing.
        if len(rows) == 1:
            return rows[0]

        normalized_target = "".join(ch for ch in device_id.lower() if ch.isalnum())
        for row in rows:
            instance_name = str(safe_property_value(row, "InstanceName") or "")
            normalized_instance = "".join(
                ch for ch in instance_name.lower() if ch.isalnum()
            )
            if normalized_target and normalized_target in normalized_instance:
                return row

        return None

    @staticmethod
    def _charge_threshold_supported() -> bool:
        try:
            from bios.detection import provider

            return bool(provider().battery_charge_limit_supported())
        except Exception as exc:
            logger.debug("Battery charge-limit capability query failed: %s", exc)
            return False


__all__ = ["BatteryDetector"]
