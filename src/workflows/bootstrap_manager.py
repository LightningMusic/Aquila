"""
Project Aquila
=============

Workflow: Bootstrap Stage

Thin orchestration-layer adapter around
``bootstrap.bootstrap_manager.BootstrapManager`` (SRS Section 10.7,
REQ-BOOT-001 through REQ-BOOT-020) for SRS Appendix B, Workflow B
(Aquila Node Provisioning)'s final stage.

Why this stage looks different from every other ``workflows/*_manager.py``
------------------------------------------------------------------------------
Every other stage in this package runs in **Phase One** (the
WinPE-hosted Technician Console), is driven interactively by a
technician, and reports progress through ``workflows.progress`` to a
live Console. Bootstrap runs in **Phase Two** -- a separate,
freshly-installed Proxmox Linux environment, invoked automatically by
Proxmox's own ``[first-boot]`` mechanism (see
``bootstrap.bootstrap_manager``'s own module docstring) -- with no
live Console process to report to at all (REQ-BOOT-001/021: "shall
execute automatically", "shall not require additional technician
interaction unless an unrecoverable error occurs"). This adapter
therefore:

* Takes no confirmation/approval gate (there is no operator present
  to gate on).
* Still emits ``WorkflowStageEvent``s through the same
  ``workflows.progress`` channel every other stage uses -- not for a
  live UI (none exists here), but so a caller that *does* have
  somewhere to send them (a local log, or a future headless
  reporting hook) can, without this module needing to know who's
  listening.
* Takes ``node_identifier``/``authentication_token``/``join_secret``
  as required, explicit parameters, exactly matching
  ``BootstrapManager.run()``'s own signature -- see that module's
  docstring, and ``workflows.provisioning_manager``'s module
  docstring's "still-open gap" note, for why nothing this package
  builds can hand these values across the Phase One/Phase Two boot
  boundary itself; whatever invokes this stage during Phase Two's
  first boot (the script Proxmox fetches per
  ``ProvisioningProfile.bootstrap_source_url``) is responsible for
  having already obtained them.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from bootstrap.bootstrap_manager import BootstrapManager, BootstrapSummary
from bootstrap.controller_client import DeploymentControllerClient
from common.constants.logging import WORKFLOW_LOGGER
from config.schemas.cluster_schema import ClusterConfig
from config.schemas.controller_schema import ControllerConfig
from config.schemas.deployment_schema import DeploymentConfig

from .progress import WorkflowProgressCallback, emit

if TYPE_CHECKING:
    from common.events.bus import EventBus

logger = logging.getLogger(WORKFLOW_LOGGER)

STAGE_NAME = "bootstrap"


class BootstrapWorkflowStage:
    """
    Runs the Bootstrap Engine as Workflow B's final, fully-automatic
    stage.

    Satisfies ``interfaces.service.Service``.
    """

    def __init__(
        self,
        *,
        bootstrap_manager: Optional[BootstrapManager] = None,
        event_bus: Optional["EventBus"] = None,
    ) -> None:
        self._manager = bootstrap_manager or BootstrapManager(event_bus=event_bus)
        self._initialized = False

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        self._manager.initialize()
        self._initialized = True

    def shutdown(self) -> None:
        self._manager.shutdown()
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def last_summary(self) -> Optional[BootstrapSummary]:
        return self._manager.last_summary

    # ------------------------------------------------------------------
    # Stage: Bootstrap (REQ-BOOT-001 through REQ-BOOT-020)
    # ------------------------------------------------------------------

    def run(
        self,
        *,
        node_identifier: str,
        authentication_token: str,
        controller_config: ControllerConfig,
        cluster_config: ClusterConfig,
        deployment_config: DeploymentConfig,
        join_secret: str,
        controller_client: Optional[DeploymentControllerClient] = None,
        workflow_progress_callback: Optional[WorkflowProgressCallback] = None,
    ) -> BootstrapSummary:
        """
        Run Phase Two's Bootstrap Engine to completion.

        Args:
            node_identifier, authentication_token, controller_config,
            cluster_config, deployment_config, join_secret,
            controller_client: Forwarded to ``BootstrapManager.run()``
                unchanged -- see that method's own docstring for the
                full REQ-BOOT-001 through -020 sequence this performs.
            workflow_progress_callback: Notified at stage start and
                completion (there is no finer-grained, per-sub-stage
                signal here -- ``BootstrapManager.run()`` itself
                already logs every sub-stage through
                ``BOOTSTRAP_LOGGER``, which is the primary record for
                a headless Phase Two run; see the module docstring).

        Does not raise for an ordinary sub-stage failure --
        ``BootstrapManager.run()`` already never propagates one
        (matching REQ-BOOT-021's "no technician interaction unless an
        unrecoverable error occurs": there is no technician to
        interact with here at all), reporting outcomes through
        ``BootstrapSummary.operational``/``.status`` instead.
        """

        if not self._initialized:
            self.initialize()

        emit(
            workflow_progress_callback,
            STAGE_NAME,
            f"Bootstrap started for node '{node_identifier}'.",
            logger=logger,
        )

        summary = self._manager.run(
            node_identifier=node_identifier,
            authentication_token=authentication_token,
            controller_config=controller_config,
            cluster_config=cluster_config,
            deployment_config=deployment_config,
            join_secret=join_secret,
            controller_client=controller_client,
        )

        if summary.operational:
            emit(
                workflow_progress_callback,
                STAGE_NAME,
                f"Bootstrap complete: node '{summary.hostname}' is "
                "operational.",
                logger=logger,
            )
        else:
            emit(
                workflow_progress_callback,
                STAGE_NAME,
                f"Bootstrap did not complete: {summary.abort_reason}",
                severity="error",
                logger=logger,
            )

        return summary

    # ------------------------------------------------------------------
    # Magic methods
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(initialized={self._initialized})"
        )


__all__ = ["STAGE_NAME", "BootstrapWorkflowStage"]
