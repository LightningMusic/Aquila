"""
Project Aquila
=============

Deployment Controller / Inventory events.

Defines events published by the Deployment Controller (SRS Section
9.7/10.8, REQ-CTRL-*) and the Inventory System (SRS Section 9.10/10.9,
REQ-INV-*) as they authenticate, authorize, configure, and register
Aquila nodes. Follows the exact convention every other module in
``common.events.types`` already uses: plain subclassing of ``Event``,
a bare ``super().__init__(event_type=EventType.X.name,
source=EventSource.Y.name, payload={...})``.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from common.enums import EventSource, EventType
from common.events.event import Event

# =============================================================================
# Authentication (REQ-CTRL-001/002, REQ-SEC-002/006)
#
# REQ-SEC-015: security-related events are classified separately from
# ordinary inventory/lifecycle events at the *type* level, not only by
# which logger happens to record them -- ``NodeAuthenticatedEvent``,
# ``NodeAuthenticationFailedEvent``, ``NodeApprovedEvent``, and
# ``NodeDeniedEvent`` each carry their own dedicated ``EventType``
# member (``NODE_AUTHENTICATED``, ``NODE_AUTHENTICATION_FAILED``, ...),
# so a consumer of the structured event-log export
# (``logging_engine.formatter.StructuredFormatter``) can filter
# security events out of the shared stream by ``event_type`` alone.
# =============================================================================


class NodeAuthenticatedEvent(Event):
    """Published when a node successfully authenticates."""

    def __init__(self, node_identifier: str) -> None:
        super().__init__(
            event_type=EventType.NODE_AUTHENTICATED.name,
            source=EventSource.CONTROLLER_MANAGER.name,
            payload={"node_identifier": node_identifier},
        )


class NodeAuthenticationFailedEvent(Event):
    """Published when node authentication is rejected (REQ-SEC-006)."""

    def __init__(self, node_identifier: str, reason: str) -> None:
        super().__init__(
            event_type=EventType.NODE_AUTHENTICATION_FAILED.name,
            source=EventSource.CONTROLLER_MANAGER.name,
            payload={"node_identifier": node_identifier, "reason": reason},
        )


# =============================================================================
# Authorization (REQ-CTRL-016, REQ-SEC-004/007)
# =============================================================================


class NodeApprovedEvent(Event):
    """Published when a node's deployment is approved."""

    def __init__(self, node_identifier: str) -> None:
        super().__init__(
            event_type=EventType.NODE_APPROVED.name,
            source=EventSource.CONTROLLER_MANAGER.name,
            payload={"node_identifier": node_identifier},
        )


class NodeDeniedEvent(Event):
    """Published when a node's deployment is denied (REQ-SEC-007)."""

    def __init__(self, node_identifier: str, reason: str) -> None:
        super().__init__(
            event_type=EventType.NODE_DENIED.name,
            source=EventSource.CONTROLLER_MANAGER.name,
            payload={"node_identifier": node_identifier, "reason": reason},
        )


# =============================================================================
# Configuration Distribution (REQ-CTRL-006/007)
# =============================================================================


class NodeConfigurationIssuedEvent(Event):
    """Published when deployment configuration is handed to a node."""

    def __init__(self, node_identifier: str, hostname: str) -> None:
        super().__init__(
            event_type=EventType.NODE_CONFIGURATION_ISSUED.name,
            source=EventSource.CONTROLLER_MANAGER.name,
            payload={"node_identifier": node_identifier, "hostname": hostname},
        )


# =============================================================================
# Inventory (REQ-INV-001/004)
# =============================================================================


class NodeRegisteredEvent(Event):
    """Published when a node's inventory record is created."""

    def __init__(self, node_identifier: str, hostname: str) -> None:
        super().__init__(
            event_type=EventType.NODE_REGISTERED.name,
            source=EventSource.INVENTORY_MANAGER.name,
            payload={"node_identifier": node_identifier, "hostname": hostname},
        )


class NodeStatusChangedEvent(Event):
    """Published when a node's inventory status changes (REQ-INV-005)."""

    def __init__(
        self, node_identifier: str, previous_status: str, new_status: str
    ) -> None:
        super().__init__(
            event_type=EventType.NODE_STATUS_CHANGED.name,
            source=EventSource.INVENTORY_MANAGER.name,
            payload={
                "node_identifier": node_identifier,
                "previous_status": previous_status,
                "new_status": new_status,
            },
        )


class BenchmarkRecordedEvent(Event):
    """Published when a benchmark result is stored (REQ-INV-003)."""

    def __init__(self, node_identifier: str, overall_score: int) -> None:
        super().__init__(
            event_type=EventType.BENCHMARK_RECORDED.name,
            source=EventSource.INVENTORY_MANAGER.name,
            payload={
                "node_identifier": node_identifier,
                "overall_score": overall_score,
            },
        )


class DeploymentReportRecordedEvent(Event):
    """Published when a deployment completion report is stored
    (REQ-CTRL-015, REQ-INV-007)."""

    def __init__(self, node_identifier: str, status: str) -> None:
        super().__init__(
            event_type=EventType.DEPLOYMENT_REPORT_RECORDED.name,
            source=EventSource.INVENTORY_MANAGER.name,
            payload={"node_identifier": node_identifier, "status": status},
        )


# =============================================================================
# Controller Lifecycle
# =============================================================================


class ControllerStartedEvent(Event):
    """Published when the Deployment Controller API server starts."""

    def __init__(self, host: str, port: int) -> None:
        super().__init__(
            event_type=EventType.CONTROLLER_STARTED.name,
            source=EventSource.CONTROLLER_MANAGER.name,
            payload={"host": host, "port": port},
        )


class ControllerStoppedEvent(Event):
    """Published when the Deployment Controller API server stops."""

    def __init__(self) -> None:
        super().__init__(
            event_type=EventType.CONTROLLER_STOPPED.name,
            source=EventSource.CONTROLLER_MANAGER.name,
            payload={},
        )


__all__ = [
    "BenchmarkRecordedEvent",
    "ControllerStartedEvent",
    "ControllerStoppedEvent",
    "DeploymentReportRecordedEvent",
    "NodeApprovedEvent",
    "NodeAuthenticatedEvent",
    "NodeAuthenticationFailedEvent",
    "NodeConfigurationIssuedEvent",
    "NodeDeniedEvent",
    "NodeRegisteredEvent",
    "NodeStatusChangedEvent",
]
