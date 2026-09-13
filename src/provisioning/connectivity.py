"""
Project Aquila
=============

Provisioning Connectivity Checks

Implements REQ-PROV-002 ("verify Ethernet connectivity before
beginning deployment"), REQ-PROV-003 ("if Ethernet connectivity is
unavailable, provisioning shall pause until connectivity has been
established"), and REQ-PROV-004 ("verify communication with the
Deployment Controller before operating system installation begins").

Deliberately separate from ``provisioning.validator``
---------------------------------------------------------
``provisioning.validator.MinimumRequirementsValidator`` checks the
already-completed ``HardwareInspectionReport`` -- a snapshot that can
be minutes or hours old by the time Provisioning actually runs.
REQ-PROV-002/003/004 are about *right now*: the Ethernet cable could
have been unplugged, or the Deployment Controller could be
unreachable, since Inspection ran. This module re-checks both live,
immediately before provisioning begins, mirroring the exact "fresh
re-verification" discipline
``preparation.sanitizer.DiskSanitizer._reverify_identity()`` already
established for storage identity.

Consolidation (post-Networking Engine)
-----------------------------------------
The Networking Engine (SRS Section 10.13, REQ-NET-001 through -014)
has since been built (``networking/``). This module no longer
reimplements the Ethernet-link retry loop or the Deployment Controller
TCP-reachability probe itself -- ``check_ethernet()`` now delegates to
:class:`networking.ethernet.EthernetChecker` (the new authoritative
implementation of REQ-NET-001 through REQ-NET-004) and
``check_controller_reachability()`` delegates to
:class:`networking.controller.ControllerReachabilityChecker`
(REQ-NET-009), which generalizes the exact TCP-probe logic that used
to live here. This module's own public API --
``ConnectivityChecker.check_ethernet()``/
``.check_controller_reachability()``, ``EthernetCheckResult``,
``ControllerReachabilityResult``, and ``ControllerSocketProber`` --
is preserved unchanged, so ``provisioning_manager.py`` and its
existing tests required no changes.

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

from common.constants.deployment import (
    NETWORK_RETRY_COUNT,
    NETWORK_RETRY_DELAY_SECONDS,
)
from common.constants.logging import PROVISIONING_LOGGER
from config.schemas.controller_schema import ControllerConfig
from hardware.network import NetworkDetector
from networking.controller import ControllerReachabilityChecker
from networking.ethernet import EthernetChecker

logger = logging.getLogger(PROVISIONING_LOGGER)


@dataclass(slots=True, frozen=True)
class EthernetCheckResult:
    """The outcome of one REQ-PROV-002/003 live Ethernet check."""

    connected: bool
    detail: str
    checked_adapter_names: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class ControllerReachabilityResult:
    """The outcome of one REQ-PROV-004 live Deployment Controller check."""

    reachable: bool
    detail: str
    host: str
    port: int


class ControllerSocketProber(Protocol):
    """
    Opens (and immediately closes) a TCP connection to a host/port.

    A narrow, single-purpose Protocol -- like
    ``preparation.sanitizer.WmiMethodCaller`` -- so functional tests
    can inject a fake prober rather than requiring a real Deployment
    Controller (a subsystem this codebase has not built yet) to be
    reachable during verification.
    """

    def probe(self, host: str, port: int, *, timeout: float) -> None:
        """Raise ``OSError`` (or a subclass) if the connection cannot be made."""
        ...


class _DefaultControllerSocketProber:
    """Real TCP-connect probe via the standard library."""

    def probe(self, host: str, port: int, *, timeout: float) -> None:
        with socket.create_connection((host, port), timeout=timeout):
            pass


class ConnectivityChecker:
    """
    Performs the live REQ-PROV-002/003/004 connectivity checks
    immediately before provisioning begins.
    """

    def __init__(
        self,
        *,
        network_detector: NetworkDetector | None = None,
        controller_prober: ControllerSocketProber | None = None,
    ) -> None:
        self._network_detector = network_detector or NetworkDetector()
        self._controller_prober = (
            controller_prober or _DefaultControllerSocketProber()
        )

    def check_ethernet(
        self,
        *,
        retry_count: int = NETWORK_RETRY_COUNT,
        retry_delay_seconds: float = NETWORK_RETRY_DELAY_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> EthernetCheckResult:
        """
        REQ-PROV-002/003: verify Ethernet connectivity is present right
        now, retrying up to ``retry_count`` times (REQ-PROV-003:
        "pause until connectivity has been established") before
        honestly reporting failure.

        ``retry_count``/``retry_delay_seconds`` default to
        ``common.constants.deployment.NETWORK_RETRY_COUNT``/
        ``NETWORK_RETRY_DELAY_SECONDS`` -- the same existing constants
        the rest of this codebase already defines for exactly this
        purpose, rather than introducing a second set of timing
        constants.

        Delegates to :class:`networking.ethernet.EthernetChecker` (the
        Networking Engine's REQ-NET-001 through REQ-NET-004
        implementation), adapting its ``EthernetLinkResult`` into this
        module's own, pre-existing ``EthernetCheckResult`` shape so
        every existing caller of this method is unaffected.
        """

        checker = EthernetChecker(network_detector=self._network_detector)
        result = checker.check_link(
            retry_count=retry_count,
            retry_delay_seconds=retry_delay_seconds,
            sleep=sleep,
        )
        return EthernetCheckResult(
            connected=result.connected,
            detail=result.detail,
            checked_adapter_names=result.checked_adapter_names,
        )

    def check_controller_reachability(
        self,
        controller_config: ControllerConfig,
        *,
        retry_count: int = NETWORK_RETRY_COUNT,
        retry_delay_seconds: float = NETWORK_RETRY_DELAY_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> ControllerReachabilityResult:
        """
        REQ-PROV-004: verify communication with the Deployment
        Controller.

        Delegates to
        :class:`networking.controller.ControllerReachabilityChecker`
        (the Networking Engine's REQ-NET-009 implementation, itself
        generalized from this exact TCP-probe logic), adapting its
        ``HostReachabilityResult`` into this module's own, pre-existing
        ``ControllerReachabilityResult`` shape so every existing caller
        of this method is unaffected. ``self._controller_prober``
        (``ControllerSocketProber``) is passed straight through --
        structurally identical to ``networking.controller.SocketProber``,
        so no adapter object is needed.
        """

        checker = ControllerReachabilityChecker(prober=self._controller_prober)
        result = checker.check(
            controller_config.host,
            controller_config.port,
            timeout_seconds=float(controller_config.connection_timeout_seconds),
            retry_count=retry_count,
            retry_delay_seconds=retry_delay_seconds,
            sleep=sleep,
        )
        return ControllerReachabilityResult(
            reachable=result.reachable,
            detail=result.detail,
            host=result.host,
            port=result.port,
        )


__all__ = [
    "ConnectivityChecker",
    "ControllerReachabilityResult",
    "ControllerSocketProber",
    "EthernetCheckResult",
]
