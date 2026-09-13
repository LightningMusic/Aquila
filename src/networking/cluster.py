"""
Project Aquila
=============

Proxmox Cluster Reachability Verification

Implements REQ-NET-010 ("The Networking Engine shall verify
communication with the target Proxmox cluster").

Scope note: this is a communication *reachability* check only -- a
TCP connect probe against the cluster's Proxmox API port (8006 by
default; see ``common.constants.proxmox.PROXMOX_API_PORT`` and
``config.schemas.cluster_schema``). It is deliberately distinct in
scope from ``bootstrap.cluster.ClusterEnrollment``, which performs the
actual Phase Two ``pvecm add``/``pvecm create`` cluster *join*
operation.

REQ-NET-010's own text is "verify communication with the target
Proxmox cluster" -- a reachability check, not "join the cluster" -- so
this module does not use the pre-built ``ClusterJoinStartedEvent`` /
``ClusterJoinedEvent`` / ``ClusterJoinFailedEvent`` event classes in
``common.events.types.networking``; those describe an actual join
operation and remain reserved for a possible future enrichment of
``bootstrap.cluster``. ``network_manager.py`` instead publishes the
generic ``ConnectivityTestStarted/Passed/FailedEvent`` pattern for
this check, consistent with every other REQ-NET-0xx reachability
check in this package.

Reuses ``networking.controller``'s TCP-probe primitives
(``HostReachabilityResult``, ``SocketProber``, ``DefaultSocketProber``)
-- the mechanics of "retry a TCP connect probe against a host/port"
are identical to REQ-NET-009's Deployment Controller check; only the
target and log/detail wording differ.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from common.constants.logging import NETWORK_LOGGER
from networking.controller import (
    DefaultSocketProber,
    HostReachabilityResult,
    SocketProber,
)

logger = logging.getLogger(NETWORK_LOGGER)


class ClusterReachabilityChecker:
    """
    Verifies communication with the target Proxmox cluster
    (REQ-NET-010) via a retried TCP connect probe against its API
    port.
    """

    def __init__(self, *, prober: SocketProber | None = None) -> None:
        self._prober = prober or DefaultSocketProber()

    def check(
        self,
        host: str,
        port: int,
        *,
        timeout_seconds: float,
        retry_count: int,
        retry_delay_seconds: float,
        sleep: Callable[[float], None] = time.sleep,
    ) -> HostReachabilityResult:
        """
        REQ-NET-010: verify communication with the target Proxmox
        cluster.

        ``sleep`` is a call-time parameter, matching
        ``networking.controller.ControllerReachabilityChecker.check()``
        and every other retry-based checker in this codebase.
        """

        if not host:
            detail = "No Proxmox cluster host is configured."
            logger.error(detail)
            return HostReachabilityResult(
                reachable=False, detail=detail, host=host, port=port
            )

        attempts = max(1, retry_count + 1)
        last_error = ""

        for attempt in range(attempts):
            try:
                self._prober.probe(host, port, timeout=timeout_seconds)
            except OSError as exc:
                last_error = str(exc)
                if attempt < attempts - 1:
                    logger.warning(
                        "Proxmox cluster unreachable (attempt %d/%d): "
                        "%s -- retrying in %.1fs.",
                        attempt + 1,
                        attempts,
                        last_error,
                        retry_delay_seconds,
                    )
                    sleep(retry_delay_seconds)
            else:
                detail = f"Proxmox cluster {host}:{port} is reachable."
                logger.info(detail)
                return HostReachabilityResult(
                    reachable=True, detail=detail, host=host, port=port
                )

        detail = (
            f"Proxmox cluster {host}:{port} was not reachable after "
            f"{attempts} attempt(s): {last_error}"
        )
        logger.error(detail)
        return HostReachabilityResult(
            reachable=False, detail=detail, host=host, port=port
        )


__all__ = ["ClusterReachabilityChecker"]
