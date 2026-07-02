"""
Project Orion
=============

Deployment events.

Defines events published throughout the deployment lifecycle,
including recovery, preparation, provisioning, bootstrap,
completion, cancellation, and failure.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from common.enums import EventSource, EventType
from common.events.event import Event


# =============================================================================
# Deployment Lifecycle
# =============================================================================


class DeploymentStartedEvent(Event):
    """
    Published when deployment begins.
    """

    def __init__(
        self,
        node_name: str,
    ) -> None:
        super().__init__(
            event_type=EventType.DEPLOYMENT_STARTED.name,
            source=EventSource.DEPLOYMENT_MANAGER.name,
            payload={
                "node_name": node_name,
            },
        )


class DeploymentCompletedEvent(Event):
    """
    Published after deployment completes successfully.
    """

    def __init__(
        self,
        node_name: str,
    ) -> None:
        super().__init__(
            event_type=EventType.DEPLOYMENT_COMPLETED.name,
            source=EventSource.DEPLOYMENT_MANAGER.name,
            payload={
                "node_name": node_name,
            },
        )


class DeploymentFailedEvent(Event):
    """
    Published when deployment fails.
    """

    def __init__(
        self,
        node_name: str,
        reason: str,
    ) -> None:
        super().__init__(
            event_type=EventType.DEPLOYMENT_FAILED.name,
            source=EventSource.DEPLOYMENT_MANAGER.name,
            payload={
                "node_name": node_name,
                "reason": reason,
            },
        )


class DeploymentCancelledEvent(Event):
    """
    Published when deployment is cancelled.
    """

    def __init__(
        self,
        node_name: str,
        reason: str,
    ) -> None:
        super().__init__(
            event_type=EventType.DEPLOYMENT_CANCELLED.name,
            source=EventSource.DEPLOYMENT_MANAGER.name,
            payload={
                "node_name": node_name,
                "reason": reason,
            },
        )


# =============================================================================
# Recovery Phase
# =============================================================================


class RecoveryStartedEvent(Event):
    """
    Published when the recovery phase begins.
    """

    def __init__(
        self,
        node_name: str,
    ) -> None:
        super().__init__(
            event_type=EventType.RECOVERY_STARTED.name,
            source=EventSource.RECOVERY_MANAGER.name,
            payload={
                "node_name": node_name,
            },
        )


class RecoveryCompletedEvent(Event):
    """
    Published after the recovery phase completes.
    """

    def __init__(
        self,
        node_name: str,
    ) -> None:
        super().__init__(
            event_type=EventType.RECOVERY_COMPLETED.name,
            source=EventSource.RECOVERY_MANAGER.name,
            payload={
                "node_name": node_name,
            },
        )


# =============================================================================
# Preparation Phase
# =============================================================================


class PreparationStartedEvent(Event):
    """
    Published when the preparation phase begins.
    """

    def __init__(
        self,
        node_name: str,
    ) -> None:
        super().__init__(
            event_type=EventType.PREPARATION_STARTED.name,
            source=EventSource.PREPARATION_MANAGER.name,
            payload={
                "node_name": node_name,
            },
        )


class PreparationCompletedEvent(Event):
    """
    Published after the preparation phase completes.
    """

    def __init__(
        self,
        node_name: str,
    ) -> None:
        super().__init__(
            event_type=EventType.PREPARATION_COMPLETED.name,
            source=EventSource.PREPARATION_MANAGER.name,
            payload={
                "node_name": node_name,
            },
        )


# =============================================================================
# Provisioning Phase
# =============================================================================


class ProvisioningStartedEvent(Event):
    """
    Published when the provisioning phase begins.
    """

    def __init__(
        self,
        node_name: str,
    ) -> None:
        super().__init__(
            event_type=EventType.PROVISIONING_STARTED.name,
            source=EventSource.PROVISIONING_MANAGER.name,
            payload={
                "node_name": node_name,
            },
        )


class ProvisioningCompletedEvent(Event):
    """
    Published after the provisioning phase completes.
    """

    def __init__(
        self,
        node_name: str,
    ) -> None:
        super().__init__(
            event_type=EventType.PROVISIONING_COMPLETED.name,
            source=EventSource.PROVISIONING_MANAGER.name,
            payload={
                "node_name": node_name,
            },
        )


# =============================================================================
# Bootstrap Phase
# =============================================================================


class BootstrapStartedEvent(Event):
    """
    Published when node bootstrap begins.
    """

    def __init__(
        self,
        node_name: str,
    ) -> None:
        super().__init__(
            event_type=EventType.BOOTSTRAP_STARTED.name,
            source=EventSource.BOOTSTRAP_MANAGER.name,
            payload={
                "node_name": node_name,
            },
        )


class BootstrapCompletedEvent(Event):
    """
    Published after bootstrap completes successfully.
    """

    def __init__(
        self,
        node_name: str,
    ) -> None:
        super().__init__(
            event_type=EventType.BOOTSTRAP_COMPLETED.name,
            source=EventSource.BOOTSTRAP_MANAGER.name,
            payload={
                "node_name": node_name,
            },
        )