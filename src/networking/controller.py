"""
Project Aquila
=============

Deployment Controller Reachability Verification

Implements REQ-NET-009 ("The Networking Engine shall verify
communication with the Deployment Controller").

This is the new authoritative implementation of a live Deployment
Controller reachability check within Aquila, generalized from the
TCP-probe logic
``provisioning.connectivity.ConnectivityChecker.check_controller_reachability()``
-- introduced before the Networking Engine existed; see that module's
own "Scope note" docstring, which flagged this exact consolidation.
This module takes a plain host/port rather than depending on
``config.schemas.controller_schema.ControllerConfig`` directly, so
``networking/`` has no dependency on ``provisioning/``'s
configuration schema -- callers translate their own configuration
object into a host/port pair.

``HostReachabilityResult``, ``SocketProber``, and
``DefaultSocketProber`` defined here are also reused by
``networking.cluster`` (REQ-NET-010) -- the mechanics of "retry a TCP
connect probe against a host/port" are identical for both checks;
only the target and log/detail wording differ.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import socket
import time
from dataclasses import dataclass
from typing import Callable, Protocol

from common.constants.logging import NETWORK_LOGGER

logger = logging.getLogger(NETWORK_LOGGER)


@dataclass(frozen=True, slots=True)
class HostReachabilityResult:
    """The outcome of one REQ-NET-009/010 live TCP reachability check."""

    reachable: bool
    detail: str
    host: str
    port: int


class SocketProber(Protocol):
    """
    Opens (and immediately closes) a TCP connection to a host/port.

    Mirrors ``provisioning.connectivity.ControllerSocketProber``
    exactly -- a narrow, single-purpose Protocol so functional tests
    can inject a fake prober rather than requiring a real Deployment
    Controller or Proxmox cluster to be reachable during verification.
    """

    def probe(self, host: str, port: int, *, timeout: float) -> None:
        """Raise ``OSError`` (or a subclass) if the connection cannot be made."""
        ...


class DefaultSocketProber:
    """Real TCP-connect probe via the standard library."""

    def probe(self, host: str, port: int, *, timeout: float) -> None:
        with socket.create_connection((host, port), timeout=timeout):
            pass


class ControllerReachabilityChecker:
    """
    Verifies communication with the Deployment Controller
    (REQ-NET-009) via a retried TCP connect probe.
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
        REQ-NET-009: verify communication with the Deployment
        Controller.

        ``sleep`` is a call-time parameter (not constructor-time),
        matching every other retry-based checker in this codebase
        (``networking.ethernet.EthernetChecker.check_link``, the
        original ``provisioning.connectivity.ConnectivityChecker``
        this module supersedes) -- a single checker instance can be
        reused across calls with a real ``time.sleep`` in production
        and a no-op injected only for the specific calls a test needs
        fast.
        """

        if not host:
            detail = "No Deployment Controller host is configured."
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
                        "Deployment Controller unreachable (attempt "
                        "%d/%d): %s -- retrying in %.1fs.",
                        attempt + 1,
                        attempts,
                        last_error,
                        retry_delay_seconds,
                    )
                    sleep(retry_delay_seconds)
            else:
                detail = f"Deployment Controller {host}:{port} is reachable."
                logger.info(detail)
                return HostReachabilityResult(
                    reachable=True, detail=detail, host=host, port=port
                )

        detail = (
            f"Deployment Controller {host}:{port} was not reachable "
            f"after {attempts} attempt(s): {last_error}"
        )
        logger.error(detail)
        return HostReachabilityResult(
            reachable=False, detail=detail, host=host, port=port
        )


__all__ = [
    "ControllerReachabilityChecker",
    "DefaultSocketProber",
    "HostReachabilityResult",
    "SocketProber",
]
