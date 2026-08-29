"""
Project Aquila
=============

Inspection Manager

Central orchestrator for the Inspection Engine (SRS Section 10.3,
REQ-INS-001 through REQ-INS-028). Runs every hardware category's
``inspection/*.py`` inspector, publishes the corresponding
``common.events.types.hardware`` event for each category plus the
summary ``HardwareAssessmentCompletedEvent``, logs through the
dedicated ``aquila.inspection`` logger, and assembles the results into
one ``HardwareInspectionReport`` (REQ-INS-025).

A single instance is normally created during application startup,
after ``ConfigurationManager`` and ``LogManager`` (SRS Section 10.14,
mirrors how those two are wired in -- see ``config.manager`` and
``logging_engine.log_manager``), and registered with the
``ServiceContainer`` for the workflow that drives Aquila Node
Provisioning (SRS Appendix B, Workflow B) to resolve.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Optional

from common.constants.hardware import (
    GIB,
    MAX_PENDING_SECTORS,
    MAX_REALLOCATED_SECTORS,
    MAX_UNCORRECTABLE_SECTORS,
)
from common.constants.logging import INSPECTION_LOGGER
from common.enums import InspectionResult, SMARTStatus
from common.exceptions.hardware import HardwareDetectionError
from models.hardware import (
    BatteryInfo,
    BIOSInspectionInfo,
    CPUInfo,
    GPUInfo,
    MemoryInfo,
    NetworkAdapter,
    SMARTReport,
    StorageInventory,
    VirtualizationInfo,
)

from .battery import BatteryInspector
from .bios import BIOSInspector
from .cpu import CPUInspector
from .gpu import GPUInspector
from .memory import MemoryInspector
from .network import NetworkInspector
from .report import CategoryAssessment, HardwareInspectionReport
from .smart import SMARTInspector
from .storage import StorageInspector
from .virtualization import VirtualizationInspector

if TYPE_CHECKING:
    # Imported only for type annotations below. Nothing in this module
    # constructs an EventBus -- the caller owns it and passes one in
    # -- so no runtime import is needed, and this stays resolvable
    # even in a context where ``common.events`` is unavailable.
    from common.events.bus import EventBus

try:
    from common.events.types.hardware import (
        BatteryDetectedEvent,
        BatteryHealthWarningEvent,
        BIOSDetectedEvent,
        CPUDetectedEvent,
        HardwareAssessmentCompletedEvent,
        HardwareInspectionCompletedEvent,
        HardwareInspectionFailedEvent,
        HardwareInspectionStartedEvent,
        MemoryDetectedEvent,
        SMARTCheckCompletedEvent,
        StorageDetectedEvent,
        VirtualizationDetectedEvent,
    )
except ImportError:  # pragma: no cover - event system is optional

    class _NullEvent:
        """
        Fallback event used only if ``common.events`` cannot be
        imported. ``_publish`` never actually delivers one of these:
        it only builds an event when an ``EventBus`` was supplied,
        and supplying one requires ``common.events`` to have imported
        successfully in the first place. These stand-ins exist purely
        so the names below are always bound, which keeps this module
        importable -- and honestly typed -- even in that situation
        (the same convention ``config.manager`` and
        ``logging_engine.log_manager`` already establish).
        """

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

    BatteryDetectedEvent = _NullEvent
    BatteryHealthWarningEvent = _NullEvent
    BIOSDetectedEvent = _NullEvent
    CPUDetectedEvent = _NullEvent
    HardwareAssessmentCompletedEvent = _NullEvent
    HardwareInspectionCompletedEvent = _NullEvent
    HardwareInspectionFailedEvent = _NullEvent
    HardwareInspectionStartedEvent = _NullEvent
    MemoryDetectedEvent = _NullEvent
    SMARTCheckCompletedEvent = _NullEvent
    StorageDetectedEvent = _NullEvent
    VirtualizationDetectedEvent = _NullEvent

#: Logs through the dedicated ``aquila.inspection`` logger (not
#: ``logging.getLogger(__name__)``) so records land in
#: ``LogManager``'s ``inspection.log`` file -- ``LogManager`` only
#: attaches handlers to the exact logger names in
#: ``common.constants.logging``, and this module's own dotted name
#: (``inspection.inspector``) is not one of them.
logger = logging.getLogger(INSPECTION_LOGGER)


class InspectionManager:
    """
    Runs the complete hardware inspection pass (REQ-INS-025) and
    reports the result.
    """

    def __init__(
        self,
        event_bus: Optional["EventBus"] = None,
        *,
        cpu_inspector: CPUInspector | None = None,
        memory_inspector: MemoryInspector | None = None,
        storage_inspector: StorageInspector | None = None,
        smart_inspector: SMARTInspector | None = None,
        network_inspector: NetworkInspector | None = None,
        battery_inspector: BatteryInspector | None = None,
        virtualization_inspector: VirtualizationInspector | None = None,
        bios_inspector: BIOSInspector | None = None,
        gpu_inspector: GPUInspector | None = None,
    ) -> None:
        self._event_bus: Optional["EventBus"] = event_bus

        self._cpu_inspector = cpu_inspector or CPUInspector()
        self._memory_inspector = memory_inspector or MemoryInspector()
        self._storage_inspector = storage_inspector or StorageInspector()
        self._smart_inspector = smart_inspector or SMARTInspector()
        self._network_inspector = network_inspector or NetworkInspector()
        self._battery_inspector = battery_inspector or BatteryInspector()
        self._virtualization_inspector = (
            virtualization_inspector or VirtualizationInspector()
        )
        self._bios_inspector = bios_inspector or BIOSInspector()
        self._gpu_inspector = gpu_inspector or GPUInspector()

        self._last_report: HardwareInspectionReport | None = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Service lifecycle (interfaces.service.Service)
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """
        Mark the Inspection Engine ready.

        Unlike ``ConfigurationManager``/``LogManager``, there is no
        state to load ahead of time: every hardware detector queries
        live system state at the moment ``run()`` is called, since a
        cached inspection result could describe hardware that has
        since changed (REQ-PREP-008/009 -- a storage configuration
        change after inspection must trigger a new inspection, which
        only makes sense if inspection itself is never cached).
        Defined so ``InspectionManager`` satisfies the same
        ``Service`` lifecycle every other Aquila service does
        (NFR-MAIN-002), letting ``core.startup`` bring it up
        uniformly alongside ``ConfigurationManager`` and
        ``LogManager``.

        Idempotent: calling this again is always safe.
        """

        self._initialized = True

    def shutdown(self) -> None:
        """
        Release any resources this manager holds.

        A documented no-op: every ``hardware/*.py`` detector opens,
        queries, and closes its WMI connection synchronously within a
        single ``detect()`` call -- nothing is kept open between
        runs. Defined so ``InspectionManager`` satisfies the same
        ``Service`` lifecycle every other Aquila service does.
        """

        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    # ------------------------------------------------------------------
    # Inspection (REQ-INS-025)
    # ------------------------------------------------------------------

    def run(self) -> HardwareInspectionReport:
        """
        Run every hardware category inspector and assemble a complete
        ``HardwareInspectionReport``.

        An unexpected error in any single category is caught and
        recorded as a FAILing assessment for that category alone
        (REQ-INS-025: a report must always be produced) rather than
        aborting the whole pass -- every ``hardware/*.py`` detector
        already degrades to an honestly-empty result on ordinary
        detection failure, so this only guards against a genuine
        programming defect. ``HardwareDetectionError`` is raised, and
        ``HardwareInspectionFailedEvent`` published, only if assembling
        the report itself fails -- a case this defensive structure
        makes exceedingly unlikely, but one REQ-INS's own event
        vocabulary anticipates.
        """

        self._publish(lambda: HardwareInspectionStartedEvent())
        logger.info("Hardware inspection started.")

        try:
            cpu = self._safe_run("CPU", self._run_cpu, default_factory=CPUInfo)
            memory = self._safe_run(
                "Memory", self._run_memory, default_factory=MemoryInfo
            )
            storage = self._safe_run(
                "Storage", self._run_storage, default_factory=StorageInventory
            )
            smart = self._safe_run("SMART", self._run_smart, default_factory=list)
            network = self._safe_run(
                "Network", self._run_network, default_factory=list
            )
            battery = self._safe_run(
                "Battery", self._run_battery, default_factory=BatteryInfo
            )
            virtualization = self._safe_run(
                "Virtualization",
                lambda: self._run_virtualization(cpu.data),
                default_factory=VirtualizationInfo,
            )
            bios = self._safe_run(
                "BIOS", self._run_bios, default_factory=BIOSInspectionInfo
            )
            gpu = self._safe_run("GPU", self._run_gpu, default_factory=list)

            report = HardwareInspectionReport(
                cpu=cpu,
                memory=memory,
                storage=storage,
                smart=smart,
                network=network,
                battery=battery,
                virtualization=virtualization,
                bios=bios,
                gpu=gpu,
            )
        except Exception as exc:
            logger.error(
                "Hardware inspection could not be completed: %s", exc, exc_info=True
            )
            self._publish(lambda: HardwareInspectionFailedEvent(reason=str(exc)))
            raise HardwareDetectionError(
                f"Hardware inspection could not be completed: {exc}"
            ) from exc

        self._last_report = report

        self._publish(lambda: HardwareInspectionCompletedEvent())

        warnings = report.warning_count
        failures = report.failure_count
        passed = report.overall_result is InspectionResult.PASS

        self._publish(
            lambda: HardwareAssessmentCompletedEvent(
                passed=passed, warnings=warnings, failures=failures
            )
        )

        logger.info(
            "Hardware inspection completed: result=%s warnings=%d failures=%d",
            report.overall_result.name,
            warnings,
            failures,
        )

        return report

    @property
    def last_report(self) -> HardwareInspectionReport | None:
        """
        The most recently completed inspection report (REQ-INS-028:
        retained for the duration of the deployment session), or
        ``None`` if ``run()`` has not been called yet.
        """

        return self._last_report

    # ------------------------------------------------------------------
    # Per-category runners
    # ------------------------------------------------------------------

    def _run_cpu(self) -> CategoryAssessment[CPUInfo]:
        assessment = self._cpu_inspector.inspect()
        cpu_info = assessment.data

        self._publish(
            lambda: CPUDetectedEvent(
                manufacturer=cpu_info.manufacturer,
                model=cpu_info.model_name,
                cores=cpu_info.physical_cores,
                threads=cpu_info.logical_processors,
            )
        )
        self._log_assessment("CPU", assessment)

        return assessment

    def _run_memory(self) -> CategoryAssessment[MemoryInfo]:
        assessment = self._memory_inspector.inspect()
        memory_info = assessment.data

        self._publish(
            lambda: MemoryDetectedEvent(
                total_memory_gb=round(memory_info.total_capacity_bytes / GIB, 2),
                slot_count=memory_info.slots_total,
            )
        )
        self._log_assessment("Memory", assessment)

        return assessment

    def _run_storage(self) -> CategoryAssessment[StorageInventory]:
        assessment = self._storage_inspector.inspect()
        inventory = assessment.data

        self._publish(
            lambda: StorageDetectedEvent(device_count=len(inventory.devices))
        )
        self._log_assessment("Storage", assessment)

        return assessment

    def _run_smart(self) -> CategoryAssessment[list[SMARTReport]]:
        assessment = self._smart_inspector.inspect()
        reports = assessment.data

        failed_drives = sum(
            1
            for report in reports
            if report.supported
            and (
                report.status is SMARTStatus.FAILED
                or (report.reallocated_sector_count or 0) > MAX_REALLOCATED_SECTORS
                or (report.pending_sector_count or 0) > MAX_PENDING_SECTORS
                or (report.uncorrectable_sector_count or 0)
                > MAX_UNCORRECTABLE_SECTORS
            )
        )
        passed = failed_drives == 0

        self._publish(
            lambda: SMARTCheckCompletedEvent(
                passed=passed, failed_drives=failed_drives
            )
        )
        self._log_assessment("SMART", assessment)

        return assessment

    def _run_network(self) -> CategoryAssessment[list[NetworkAdapter]]:
        assessment = self._network_inspector.inspect()
        self._log_assessment("Network", assessment)

        return assessment

    def _run_battery(self) -> CategoryAssessment[BatteryInfo]:
        assessment = self._battery_inspector.inspect()
        battery_info = assessment.data

        health_percent = battery_info.health_percent

        self._publish(
            lambda: BatteryDetectedEvent(
                present=battery_info.present,
                # BatteryDetectedEvent.health_percent is a required
                # float; 0.0 stands in only when no ratio could be
                # computed at all (no battery present, or capacity
                # unknown) -- BatteryHealthWarningEvent below is what
                # actually signals a real low-health condition, so
                # this substitution never masks one.
                health_percent=health_percent if health_percent is not None else 0.0,
            )
        )

        if (
            assessment.result is not InspectionResult.PASS
            and health_percent is not None
        ):
            self._publish(
                lambda: BatteryHealthWarningEvent(health_percent=health_percent)
            )

        self._log_assessment("Battery", assessment)

        return assessment

    def _run_virtualization(
        self, cpu_info: CPUInfo
    ) -> CategoryAssessment[VirtualizationInfo]:
        assessment = self._virtualization_inspector.inspect(cpu_info)
        info = assessment.data

        self._publish(lambda: VirtualizationDetectedEvent(enabled=info.is_usable))
        self._log_assessment("Virtualization", assessment)

        return assessment

    def _run_bios(self) -> CategoryAssessment[BIOSInspectionInfo]:
        assessment = self._bios_inspector.inspect()
        info = assessment.data

        self._publish(
            lambda: BIOSDetectedEvent(
                vendor=info.firmware.vendor.value,
                version=info.firmware.bios_version,
            )
        )
        self._log_assessment("BIOS", assessment)

        return assessment

    def _run_gpu(self) -> CategoryAssessment[list[GPUInfo]]:
        assessment = self._gpu_inspector.inspect()
        self._log_assessment("GPU", assessment)

        return assessment

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _safe_run(
        self,
        category: str,
        runner: Callable[[], CategoryAssessment[Any]],
        *,
        default_factory: Callable[[], Any],
    ) -> CategoryAssessment[Any]:
        try:
            return runner()
        except Exception as exc:
            logger.error(
                "%s inspection raised an unexpected error: %s",
                category,
                exc,
                exc_info=True,
            )
            return CategoryAssessment(
                data=default_factory(),
                result=InspectionResult.FAIL,
                messages=[f"{category} inspection failed unexpectedly: {exc}"],
            )

    @staticmethod
    def _log_assessment(category: str, assessment: CategoryAssessment[Any]) -> None:
        reasons = "; ".join(assessment.messages) or "no reason recorded"

        if assessment.result is InspectionResult.FAIL:
            logger.warning("%s inspection FAILED: %s", category, reasons)
        elif assessment.result is InspectionResult.WARNING:
            logger.warning("%s inspection WARNING: %s", category, reasons)
        else:
            logger.info("%s inspection passed.", category)

    def _publish(self, build_event: Callable[[], Any]) -> None:
        if self._event_bus is None:
            return

        try:
            self._event_bus.publish(build_event())
        except Exception:  # pragma: no cover - event delivery is best-effort
            logger.debug("Failed to publish inspection event.", exc_info=True)

    # ------------------------------------------------------------------
    # Magic methods
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"initialized={self._initialized}, "
            f"has_report={self._last_report is not None})"
        )


__all__ = ["InspectionManager"]
