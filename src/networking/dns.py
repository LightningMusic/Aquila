"""
Project Aquila
=============

DNS Resolution Verification

Implements REQ-NET-008 ("The Networking Engine shall verify DNS
resolution when required").

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import time
from dataclasses import dataclass
from typing import Callable, Protocol

from common.constants.logging import NETWORK_LOGGER

logger = logging.getLogger(NETWORK_LOGGER)


@dataclass(frozen=True, slots=True)
class DNSResolutionResult:
    """The outcome of one REQ-NET-008 DNS resolution check."""

    resolved: bool
    hostname: str
    detail: str
    resolved_address: str = ""


class DNSResolver(Protocol):
    """Resolves a hostname to an IP address string."""

    def resolve(self, hostname: str) -> str: ...


class _DefaultDNSResolver:
    """Real DNS resolution via the standard library resolver."""

    def resolve(self, hostname: str) -> str:
        # family=0 (AF_UNSPEC) accepts either an A or AAAA result --
        # REQ-NET-008 only asks whether the name resolves, not which
        # address family answered.
        results = socket.getaddrinfo(hostname, None, family=socket.AF_UNSPEC)
        if not results:
            raise socket.gaierror(f"No address records for {hostname!r}.")
        return str(results[0][4][0])


class DNSResolutionChecker:
    """Verifies DNS resolution (REQ-NET-008)."""

    def __init__(self, *, resolver: DNSResolver | None = None) -> None:
        self._resolver = resolver or _DefaultDNSResolver()

    def check(
        self,
        hostname: str,
        *,
        retry_count: int,
        retry_delay_seconds: float,
        sleep: Callable[[float], None] = time.sleep,
    ) -> DNSResolutionResult:
        """
        Resolve ``hostname`` up to ``retry_count + 1`` times.

        ``sleep`` is a call-time parameter, matching every other
        retry-based checker in this package.

        ``hostname`` is caller-supplied -- ``network_manager.py``
        passes the Deployment Controller's or cluster's configured
        host, not an arbitrary well-known domain, so this check
        reflects whether *Aquila's own* dependencies are resolvable
        rather than whether the internet at large is reachable.

        If ``hostname`` is already a literal IP address, resolving it
        is meaningless -- this is honestly reported as "not
        applicable" (``resolved=True``) rather than either silently
        skipping the check or fabricating a DNS lookup that never
        happened.
        """

        if not hostname:
            detail = "No hostname was supplied to resolve."
            logger.warning(detail)
            return DNSResolutionResult(
                resolved=False, hostname=hostname, detail=detail
            )

        if _is_ip_literal(hostname):
            detail = (
                f"'{hostname}' is already a literal IP address -- DNS "
                "resolution is not applicable."
            )
            logger.info(detail)
            return DNSResolutionResult(
                resolved=True,
                hostname=hostname,
                detail=detail,
                resolved_address=hostname,
            )

        attempts = max(1, retry_count + 1)
        last_detail = f"'{hostname}' was not resolved."

        for attempt in range(attempts):
            try:
                address = self._resolver.resolve(hostname)
            except (socket.gaierror, OSError) as exc:
                last_detail = f"'{hostname}' failed to resolve: {exc}"
            else:
                detail = f"'{hostname}' resolved to {address}."
                logger.info(detail)
                return DNSResolutionResult(
                    resolved=True,
                    hostname=hostname,
                    detail=detail,
                    resolved_address=address,
                )

            if attempt < attempts - 1:
                logger.warning(
                    "DNS resolution failed (attempt %d/%d): %s -- "
                    "retrying in %.1fs.",
                    attempt + 1,
                    attempts,
                    last_detail,
                    retry_delay_seconds,
                )
                sleep(retry_delay_seconds)

        logger.error(
            "DNS resolution failed after %d attempt(s): %s",
            attempts,
            last_detail,
        )
        return DNSResolutionResult(
            resolved=False, hostname=hostname, detail=last_detail
        )


def _is_ip_literal(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


__all__ = ["DNSResolutionChecker", "DNSResolutionResult", "DNSResolver"]
