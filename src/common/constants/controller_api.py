"""
Project Aquila
=============

Deployment Controller API Route Constants

The single source of truth for the Deployment Controller's HTTP route
paths (relative to ``ControllerConfig.api_base_path`` /
``ControllerServerConfig.api_base_path``, which is the same
configured value on both the client and server side of this contract).

Both sides of this API previously hardcoded the same six literal path
strings independently: ``bootstrap.controller_client`` (the node/
Bootstrap-side client, REQ-BOOT-002/003/004/016) and
``deployment_controller.api`` (the server, REQ-CTRL-021). That
duplication was a latent defect risk -- a route renamed on one side
without the other would silently break at runtime rather than at
review time. This module is the fix: one authoritative set of route
names, imported by every client and server module instead of each
re-declaring its own copy.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

#: REQ-CTRL-021 / REQ-BOOT-002: Deployment Controller reachability.
HEALTH_ENDPOINT: str = "health"

#: REQ-BOOT-003 / REQ-CTRL-001.
AUTHENTICATE_ENDPOINT: str = "nodes/authenticate"

#: REQ-BOOT-004 / REQ-CTRL-006/007.
CONFIGURATION_ENDPOINT: str = "nodes/configuration"

#: REQ-BOOT-016 / REQ-CTRL-015.
COMPLETION_ENDPOINT: str = "nodes/completion"

#: REQ-BOOT-014 (POST, register) / REQ-INV-010 (GET, search).
INVENTORY_ENDPOINT: str = "inventory/nodes"

#: REQ-BOOT-015/REQ-BENCH-007 (POST, submit) / REQ-BENCH-010 (GET,
#: read a node's benchmark history).
BENCHMARK_ENDPOINT: str = "inventory/benchmarks"


__all__ = [
    "AUTHENTICATE_ENDPOINT",
    "BENCHMARK_ENDPOINT",
    "COMPLETION_ENDPOINT",
    "CONFIGURATION_ENDPOINT",
    "HEALTH_ENDPOINT",
    "INVENTORY_ENDPOINT",
]
