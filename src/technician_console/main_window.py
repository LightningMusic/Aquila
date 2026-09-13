"""
Project Aquila
=============

Technician Console: Main Window

The Technician Console's single user-facing application window (SRS
Section 9.6: "The Technician Console shall serve as the single
user-facing application. Subsystems shall not present independent
interfaces to the operator."). Implements REQ-TC-001 through
REQ-TC-013 by composing every other module in this package around
``workflows.workflow_manager.WorkflowManager``.

Threading model
------------------
Every ``WorkflowManager.start_*_workflow()`` call runs on a dedicated
background ``threading.Thread`` -- never on the Tk main thread -- so
the window stays responsive for the whole deployment session
(NFR-PERF-003). Every callback a workflow invokes from that thread
(``recovery_progress_callback``, ``sanitization_progress_callback``,
``workflow_progress_callback``, and the three technician-decision
Protocols) crosses back onto the main thread through
``technician_console.thread_bridge.MainThreadBridge`` -- see that
module's own docstring for the mechanism.

Provisioning's target-device pre-flight
------------------------------------------
``workflows.workflow_manager.WorkflowManager.start_provisioning_workflow()``
requires a concrete ``provisioning_target_device: StorageDevice`` as an
ordinary, eagerly-evaluated parameter -- unlike ``target_device_selector``,
this is not a mid-workflow callback, so it must already be known
*before* the call starts, before Inspection has even run inside it.
This window resolves that by running a standalone, read-only
Inspection pass (``workflows.inspection_manager.InspectionWorkflowStage``,
constructed and used independently of the one
``WorkflowManager``/``DeploymentWorkflowManager`` owns internally --
safe to run twice, since REQ-INS-026 guarantees Inspection never
modifies anything) purely to populate
``technician_console.dialogs.TargetDeviceDialog`` before the real
workflow call begins. The chosen device(s) are then returned verbatim
by ``target_device_selector`` when the *real*, internal Inspection
pass invokes it -- re-validating that a selected device is still
physically present and unchanged is already
``preparation.preparation_manager``'s/``provisioning.provisioning_manager``'s
job (REQ-PREP-008/REQ-PREP-009/REQ-PREP-010), not this window's, so it
is not duplicated here.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional

from common.events.bus import EventBus
from common.exceptions.application import (
    AquilaCancelledError,
    AquilaEnvironmentError,
    AquilaInitializationError,
)
from common.exceptions.deployment import DeploymentValidationError
from common.version import APPLICATION
from config.manager import ConfigurationManager
from inspection.report import HardwareInspectionReport
from models.hardware.storage import StorageDevice
from preparation.confirmations import PreparationConfirmations
from provisioning.boot_handoff import DEFAULT_MANIFEST_FILENAME
from recovery.browser import RecoveryVolume, VolumeBrowser
from services.configuration_service import ConfigurationService, SessionConfigBundle
from services.logging_service import LoggingService
from workflows.application_manager import ApplicationManager
from workflows.deployment_manager import WorkflowSummary
from workflows.inspection_manager import InspectionWorkflowStage
from workflows.preparation_manager import PreparationConfirmationRequest
from workflows.progress import WorkflowStageEvent
from workflows.provisioning_manager import ProvisioningProfileTemplate
from workflows.recovery_manager import RecoveryDecision
from workflows.workflow_manager import WorkflowAlreadyRunningError, WorkflowManager

from . import dialogs, media
from .dialogs import TargetDeviceSelection
from .progress import ProgressPanel
from .status_panel import StatusPanel
from .thread_bridge import PUMP_INTERVAL_MS, MainThreadBridge
from .workflow_selector import WorkflowSelectorPanel


class MainWindow(tk.Tk):
    """The Technician Console's top-level window."""

    def __init__(self, *, configs_dir: Optional[Path] = None) -> None:
        super().__init__()
        self.title(f"{APPLICATION.name} Technician Console")
        self.geometry("960x720")
        self.minsize(800, 600)

        self.fatal_error: Optional[str] = None
        self._bridge = MainThreadBridge()

        # ------------------------------------------------------------------
        # REQ-TC-001: bring up every core service before anything else.
        #
        # NFR-PERF-001 ("The Technician Console should launch within 10
        # seconds"): everything __init__ does is widget construction
        # plus this lightweight config/service bring-up (parsing a
        # handful of small YAML files and attaching log handlers) --
        # no hardware inspection or network I/O runs during launch, so
        # nothing here scales with target-hardware size or Controller
        # reachability the way a 10-second budget would be at risk of.
        # ------------------------------------------------------------------
        self._app_manager = ApplicationManager(configs_dir=configs_dir)
        try:
            self._app_manager.initialize()
        except AquilaInitializationError as exc:
            self.fatal_error = str(exc)
            dialogs.show_error(self, "Aquila Failed to Start", self.fatal_error)
            return

        config_manager = self._app_manager.services.resolve(ConfigurationManager)
        self._config_manager = config_manager
        self._event_bus = self._app_manager.services.resolve(EventBus)

        self._configuration_service = ConfigurationService(
            configuration_manager=config_manager
        )
        self._configuration_service.initialize()

        try:
            self._config_bundle: SessionConfigBundle = (
                self._configuration_service.load_session_bundle()
            )
        except Exception as exc:  # noqa: BLE001 - reported to the technician verbatim
            self.fatal_error = str(exc)
            dialogs.show_error(
                self, "Configuration Failed to Load", self.fatal_error
            )
            return

        validation_problems = config_manager.validate_all()
        if validation_problems:
            dialogs.show_warning(
                self,
                "Configuration Warnings",
                "The following configuration file(s) failed validation "
                "and are running on their built-in defaults:\n\n"
                + "\n".join(
                    f"- {name}: {message}"
                    for name, message in sorted(validation_problems.items())
                ),
            )

        self._logging_service = LoggingService(
            logging_config=self._config_bundle.logging
        )
        self._logging_service.initialize()

        self._workflow_manager = WorkflowManager(event_bus=self._event_bus)
        self._workflow_manager.initialize()

        self._volume_browser = VolumeBrowser()
        self._profile_template = ProvisioningProfileTemplate(
            domain=self._config_bundle.deployment.provisioning_domain,
            mailto=self._config_bundle.deployment.provisioning_notification_email,
        )

        try:
            self._media_root: Optional[Path] = media.detect_media_root()
        except AquilaEnvironmentError:
            self._media_root = None

        self._workflow_active = False

        self._build_layout()
        self._start_clock()
        self.after(PUMP_INTERVAL_MS, self._pump)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        status_bar = ttk.Frame(self, relief="groove", borderwidth=1)
        status_bar.pack(fill="x")

        self._version_var = tk.StringVar()
        self._media_version_var = tk.StringVar()
        self._clock_var = tk.StringVar()
        self._target_var = tk.StringVar(value="Target computer: not yet detected.")

        ttk.Label(status_bar, textvariable=self._version_var).pack(
            side="left", padx=8, pady=4
        )
        ttk.Label(status_bar, textvariable=self._media_version_var).pack(
            side="left", padx=8, pady=4
        )
        ttk.Label(status_bar, textvariable=self._clock_var).pack(
            side="right", padx=8, pady=4
        )

        target_row = ttk.Frame(self)
        target_row.pack(fill="x")
        ttk.Label(target_row, textvariable=self._target_var, anchor="w").pack(
            fill="x", padx=8, pady=(4, 0)
        )

        self._selector = WorkflowSelectorPanel(
            self,
            on_start_retirement=self._start_retirement_workflow,
            on_start_provisioning=self._start_provisioning_workflow,
        )
        self._selector.pack(fill="x", padx=8, pady=8)

        self._progress_panel = ProgressPanel(self, self._bridge)
        self._progress_panel.pack(fill="x", padx=8, pady=(0, 8))

        self._status_panel = StatusPanel(
            self, self._bridge, on_view_logs=self._show_log_viewer
        )
        self._status_panel.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._refresh_status_bar()

    def _refresh_status_bar(self) -> None:
        self._version_var.set(f"Aquila v{self._app_manager.aquila_version}")
        media_version = self._app_manager.deployment_media_version
        self._media_version_var.set(
            f"Media: {media_version}" if media_version else "Media: (unversioned)"
        )
        target = self._app_manager.target_computer_summary
        if target:
            self._target_var.set(f"Target computer: {target}")

    def _start_clock(self) -> None:
        self._tick_clock()

    def _tick_clock(self) -> None:
        self._clock_var.set(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.after(1000, self._tick_clock)

    def _pump(self) -> None:
        self._bridge.pump()
        self.after(PUMP_INTERVAL_MS, self._pump)

    # ------------------------------------------------------------------
    # Combined REQ-TC-009/010/011 stage-event dispatcher
    # ------------------------------------------------------------------

    def _on_stage_event(self, event: WorkflowStageEvent) -> None:
        self._progress_panel.on_stage_event(event)
        self._status_panel.on_stage_event(event)

    # ------------------------------------------------------------------
    # REQ-TC-008
    # ------------------------------------------------------------------

    def _show_log_viewer(self) -> None:
        dialogs.LogViewerDialog(self, self._logging_service).run()

    # ------------------------------------------------------------------
    # REQ-TC-006: Device Retirement
    # ------------------------------------------------------------------

    def _start_retirement_workflow(self, node_name: str) -> None:
        self._begin_session()
        thread = threading.Thread(
            target=self._run_retirement_workflow,
            args=(node_name,),
            daemon=True,
            name="aquila-retirement-workflow",
        )
        thread.start()

    def _run_retirement_workflow(self, node_name: str) -> None:
        try:
            summary = self._workflow_manager.start_retirement_workflow(
                node_name=node_name,
                recovery_decision_provider=self._recovery_decision_provider,
                target_device_selector=self._retirement_target_device_selector,
                deployment_config=self._config_bundle.deployment,
                confirmation_provider=self._confirmation_provider,
                recovery_progress_callback=self._progress_panel.on_recovery_progress,
                sanitization_progress_callback=(
                    self._progress_panel.on_sanitization_progress
                ),
                workflow_progress_callback=self._on_stage_event,
            )
            self._bridge.post(lambda: self._finish_session(summary))
        except AquilaCancelledError:
            self._bridge.post(
                lambda: self._finish_session_cancelled("Device Retirement")
            )
        except WorkflowAlreadyRunningError as exc:
            self._bridge.post(lambda: self._finish_session_error(str(exc)))
        except Exception as exc:  # noqa: BLE001 - reported to the technician verbatim
            self._bridge.post(lambda: self._finish_session_error(str(exc)))

    def _retirement_target_device_selector(
        self, inspection_report: HardwareInspectionReport
    ) -> list[StorageDevice]:
        eligible = inspection_report.storage.data.eligible_for_deployment()
        selection: TargetDeviceSelection = self._bridge.call_blocking(
            lambda: dialogs.TargetDeviceDialog(
                self, eligible, require_provisioning_target=False
            ).run()
        )
        return list(selection.devices)

    # ------------------------------------------------------------------
    # REQ-TC-007: Aquila Node Provisioning
    # ------------------------------------------------------------------

    def _start_provisioning_workflow(self, node_name: str) -> None:
        if self._media_root is None:
            dialogs.show_error(
                self,
                "Deployment Media Not Detected",
                "Could not determine the deployment media's root "
                "directory, so Provisioning cannot proceed (it needs "
                "to write the Phase Two answer file and node-identity "
                f"record). Set the {media.MEDIA_ROOT_ENV_VAR} "
                "environment variable to override detection.",
            )
            return

        if not self._config_bundle.deployment.boot_entry_id:
            dialogs.show_error(
                self,
                "Boot Entry Not Configured",
                "This deployment media's 'deployment.yaml' does not "
                "set 'boot_entry_id' -- the pre-registered BCD boot "
                "entry the Build System must stamp onto media at "
                "build time. Provisioning cannot hand off to Phase "
                "Two without it.",
            )
            return

        if not (
            self._profile_template.domain and self._profile_template.mailto
        ):
            dialogs.show_error(
                self,
                "Installer Notification Settings Not Configured",
                "This deployment media's 'deployment.yaml' does not "
                "set 'provisioning_domain' and/or "
                "'provisioning_notification_email' -- both are "
                "required by the Proxmox VE installer (REQ-PROV-015's "
                "[global].fqdn domain suffix and [global].mailto "
                "notification address) and cannot be left blank or "
                "guessed on the node's behalf.",
            )
            return

        root_password = ConfigurationManager.resolve_secret(
            self._profile_template.root_password_env_var
        )
        if not root_password:
            dialogs.show_error(
                self,
                "Root Password Not Set",
                "Set the "
                f"{self._profile_template.root_password_env_var} "
                "environment variable to the node's root credential "
                "before provisioning (REQ-SEC-008/009/010: never "
                "typed into this window or stored in configuration).",
            )
            return

        self._begin_session()
        thread = threading.Thread(
            target=self._run_provisioning_workflow,
            args=(node_name, root_password),
            daemon=True,
            name="aquila-provisioning-workflow",
        )
        thread.start()

    def _run_provisioning_workflow(self, node_name: str, root_password: str) -> None:
        assert self._media_root is not None
        try:
            preflight = InspectionWorkflowStage(event_bus=self._event_bus)
            preflight.initialize()
            try:
                preflight_report = preflight.run(
                    node_name=f"{node_name}-preflight",
                    progress_callback=self._on_stage_event,
                )
            finally:
                preflight.shutdown()

            eligible = preflight_report.storage.data.eligible_for_deployment()
            if not eligible:
                raise DeploymentValidationError(
                    "No storage device eligible for deployment was "
                    "detected on this system."
                )

            selection: TargetDeviceSelection = self._bridge.call_blocking(
                lambda: dialogs.TargetDeviceDialog(
                    self, eligible, require_provisioning_target=True
                ).run()
            )
            chosen_devices = list(selection.devices)
            assert selection.provisioning_device is not None

            phase_two_dir = media.phase_two_directory(self._media_root)
            report_dir = media.report_directory(self._media_root)

            summary = self._workflow_manager.start_provisioning_workflow(
                node_name=node_name,
                recovery_decision_provider=self._recovery_decision_provider,
                target_device_selector=lambda _report: chosen_devices,
                provisioning_target_device=selection.provisioning_device,
                deployment_config=self._config_bundle.deployment,
                confirmation_provider=self._confirmation_provider,
                controller_config=self._config_bundle.controller,
                network_config=self._config_bundle.network,
                cluster_config=self._config_bundle.cluster,
                profile_template=self._profile_template,
                root_password=root_password,
                phase_two_directory=phase_two_dir,
                answer_file_destination=phase_two_dir / "answer.toml",
                identity_record_destination=(
                    report_dir / f"{node_name}-node-identity.json"
                ),
                boot_entry_id=self._config_bundle.deployment.boot_entry_id,
                manifest_filename=DEFAULT_MANIFEST_FILENAME,
                trigger_handoff=True,
                recovery_progress_callback=self._progress_panel.on_recovery_progress,
                sanitization_progress_callback=(
                    self._progress_panel.on_sanitization_progress
                ),
                workflow_progress_callback=self._on_stage_event,
            )
            self._bridge.post(lambda: self._finish_session(summary))
        except AquilaCancelledError:
            self._bridge.post(
                lambda: self._finish_session_cancelled("Aquila Node Provisioning")
            )
        except WorkflowAlreadyRunningError as exc:
            self._bridge.post(lambda: self._finish_session_error(str(exc)))
        except Exception as exc:  # noqa: BLE001 - reported to the technician verbatim
            self._bridge.post(lambda: self._finish_session_error(str(exc)))

    # ------------------------------------------------------------------
    # Shared technician-decision callbacks (both workflows)
    # ------------------------------------------------------------------

    def _recovery_decision_provider(
        self,
        inspection_report: HardwareInspectionReport,
        volumes: list[RecoveryVolume],
    ) -> RecoveryDecision:
        self._app_manager.record_target_computer(inspection_report)
        self._bridge.post(self._refresh_status_bar)
        return self._bridge.call_blocking(
            lambda: dialogs.RecoveryDialog(
                self, volumes, self._volume_browser
            ).run()
        )

    def _confirmation_provider(
        self, request: PreparationConfirmationRequest
    ) -> PreparationConfirmations:
        return self._bridge.call_blocking(
            lambda: dialogs.PreparationConfirmationDialog(self, request).run()
        )

    # ------------------------------------------------------------------
    # Session bracketing (REQ-TC-012, REQ-TC-013)
    # ------------------------------------------------------------------

    def _begin_session(self) -> None:
        self._workflow_active = True
        self._selector.set_enabled(False)
        self._progress_panel.reset()
        self._status_panel.reset()
        self._progress_panel.begin_operation("Starting deployment workflow...")

    def _finish_session(self, summary: WorkflowSummary) -> None:
        self._workflow_active = False
        self._selector.set_enabled(True)
        self._progress_panel.end_operation()
        dialogs.SummaryDialog(self, summary).run()

    def _finish_session_cancelled(self, workflow_label: str) -> None:
        self._workflow_active = False
        self._selector.set_enabled(True)
        self._progress_panel.end_operation()
        dialogs.show_warning(
            self,
            "Deployment Cancelled",
            f"The {workflow_label} workflow was cancelled by the "
            "technician. No deployment summary was generated.",
        )

    def _finish_session_error(self, message: str) -> None:
        self._workflow_active = False
        self._selector.set_enabled(True)
        self._progress_panel.end_operation()
        dialogs.show_error(self, "Deployment Error", message)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        if self._workflow_active:
            proceeding = messagebox.askyesno(
                "Deployment In Progress",
                "A deployment workflow is currently running. Closing "
                "the Technician Console now will not stop it safely. "
                "Close anyway?",
                parent=self,
            )
            if not proceeding:
                return

        try:
            self._workflow_manager.shutdown()
            self._logging_service.shutdown()
            self._configuration_service.shutdown()
            self._app_manager.shutdown()
        finally:
            self.destroy()


__all__ = ["MainWindow"]
