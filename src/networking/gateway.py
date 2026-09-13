"""
Project Aquila
=============

Gateway Reachability Verification

Implements REQ-NET-007 ("The Networking Engine shall verify gateway
connectivity when required by deployment policy").

Uses a single ICMP echo request via the Windows ``ping.exe`` utility.
``ping``'s basic single-echo syntax (``-n <count>``, ``-w <timeout-ms>``)
has been stable across every Windows release since Windows 2000 and is
not vendor/version-sensitive the way the WMI method signatures and
netsh syntax in ``dhcp.py`` are -- so, unlike those, it was judged not
to need the same primary-source verification, consistent with
``hardware.is_windows()``'s established Windows-only guard used
throughout every Phase One subsystem.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Protocol

from common.constants.logging import NETWORK_LOGGER
from hardware import is_windows

logger = logging.getLogger(NETWORK_LOGGER)


@dataclass(frozen=True, slots=True)
class GatewayReachabilityResult:
    """The outcome of one REQ-NET-007 gateway reachability check."""

    reachable: bool
    gateway: str
    detail: str


class GatewayProber(Protocol):
    """Probes whether a single host responds to an ICMP echo request."""

    def probe(self, host: str, *, timeout_seconds: float) -> bool: ...


class _DefaultGatewayProber:
    """Real ICMP reachability probe via ``ping.exe``."""

    def probe(self, host: str, *, timeout_seconds: float) -> bool:
        if not is_windows():
            return False

        timeout_ms = max(1, int(timeout_seconds * 1000))
        try:
            process = subprocess.run(
                ["ping", "-n", "1", "-w", str(timeout_ms), host],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
                timeout=timeout_seconds + 5.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("ping to %s failed to execute: %s", host, exc)
            return False

        return process.returncode == 0


class GatewayChecker:
    """Verifies default-gateway reachability (REQ-NET-007)."""

    def __init__(self, *, prober: GatewayProber | None = None) -> None:
        self._prober = prober or _DefaultGatewayProber()

    def check(
        self,
        gateway: str,
        *,
        retry_count: int,
        retry_delay_seconds: float,
        timeout_seconds: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> GatewayReachabilityResult:
        """
        Ping ``gateway`` up to ``retry_count + 1`` times, honestly
        reporting failure if it never responds.

        ``sleep`` is a call-time parameter, matching
        ``networking.ethernet.EthernetChecker.check_link`` and every
        other retry-based checker in this package.
        """

        if not gateway:
            detail = "No gateway address was supplied to check."
            logger.warning(detail)
            return GatewayReachabilityResult(
                reachable=False, gateway=gateway, detail=detail
            )

        attempts = max(1, retry_count + 1)
        last_detail = f"Gateway {gateway} was not checked."

        for attempt in range(attempts):
            if self._prober.probe(gateway, timeout_seconds=timeout_seconds):
                detail = f"Gateway {gateway} is reachable."
                logger.info(detail)
                return GatewayReachabilityResult(
                    reachable=True, gateway=gateway, detail=detail
                )

            last_detail = f"Gateway {gateway} did not respond."
            if attempt < attempts - 1:
                logger.warning(
                    "Gateway %s unreachable (attempt %d/%d) -- "
                    "retrying in %.1fs.",
                    gateway,
                    attempt + 1,
                    attempts,
                    retry_delay_seconds,
                )
                sleep(retry_delay_seconds)

        logger.error(
            "Gateway connectivity check failed after %d attempt(s): %s",
            attempts,
            last_detail,
        )
        return GatewayReachabilityResult(
            reachable=False, gateway=gateway, detail=last_detail
        )


__all__ = ["GatewayChecker", "GatewayProber", "GatewayReachabilityResult"]
