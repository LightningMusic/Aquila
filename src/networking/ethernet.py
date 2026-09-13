"""
Project Aquila
=============

Ethernet Detection and Link Verification

Implements REQ-NET-001 (enumerate all available network interfaces),
REQ-NET-002 (identify all Ethernet interfaces), REQ-NET-003 (determine
Ethernet link status), and REQ-NET-004 (verify that an Ethernet cable
is connected before provisioning begins).

Reuses ``hardware.network.NetworkDetector`` -- the same read-only WMI
detector Inspection already uses (REQ-INS-009 through REQ-INS-011,
REQ-INS-024) -- rather than a second, parallel adapter-enumeration
path. This is the authoritative implementation of a live Ethernet
check within Aquila; ``provisioning.connectivity.ConnectivityChecker
.check_ethernet()`` now delegates to :class:`EthernetChecker` instead
of duplicating this retry loop -- see that module's updated docstring
for the consolidation this class made possible.

Runs entirely within Phase One (the WinPE-hosted Technician Console),
the same environment ``hardware/`` targets -- REQ-NET's own Section
9.13/11.11 overview scopes Networking to Aquila Node Provisioning
(Workflow B), which is a Phase One responsibility ending at the boot
handoff into Phase Two.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from common.constants.logging import NETWORK_LOGGER
from common.enums import EthernetStatus
from hardware.network import NetworkDetector
from models.hardware.network import NetworkAdapter, NetworkAdapterType

logger = logging.getLogger(NETWORK_LOGGER)


@dataclass(slots=True, frozen=True)
class EthernetLinkResult:
    """The outcome of one REQ-NET-003/004 live Ethernet link check."""

    connected: bool
    detail: str
    checked_adapter_names: tuple[str, ...] = ()
    active_adapter_names: tuple[str, ...] = ()

    #: The specific adapter this result confirmed as active, when
    #: ``connected`` is ``True`` -- ``network_manager.py`` needs the
    #: real object (for its WMI ``interface_index``, MAC address, ...),
    #: not just its name, to proceed into REQ-NET-005 IP acquisition
    #: without a second, redundant detection pass.
    primary_adapter: NetworkAdapter | None = None


class EthernetChecker:
    """
    Enumerates network interfaces and verifies live Ethernet link
    status (REQ-NET-001 through REQ-NET-004).
    """

    def __init__(
        self, *, network_detector: NetworkDetector | None = None
    ) -> None:
        self._network_detector = network_detector or NetworkDetector()

    def enumerate_interfaces(self) -> tuple[NetworkAdapter, ...]:
        """REQ-NET-001: every network interface on the target system."""

        return tuple(self._network_detector.detect())

    def ethernet_interfaces(self) -> tuple[NetworkAdapter, ...]:
        """
        REQ-NET-002: the subset of :meth:`enumerate_interfaces` that
        are physical, enabled Ethernet adapters.
        """

        return tuple(
            adapter
            for adapter in self.enumerate_interfaces()
            if adapter.adapter_type is NetworkAdapterType.ETHERNET
            and adapter.is_physical
            and adapter.is_enabled
        )

    def check_link(
        self,
        *,
        retry_count: int,
        retry_delay_seconds: float,
        sleep: Callable[[float], None] = time.sleep,
    ) -> EthernetLinkResult:
        """
        REQ-NET-003/004: verify at least one Ethernet adapter reports
        an active link right now, retrying up to ``retry_count`` times
        before honestly reporting failure -- REQ-NET-004 requires this
        to hold "before provisioning begins", not merely at some
        earlier point in time.
        """

        attempts = max(1, retry_count + 1)
        last_result = EthernetLinkResult(
            connected=False,
            detail="Ethernet connectivity was not checked.",
        )

        for attempt in range(attempts):
            ethernet_adapters = self.ethernet_interfaces()
            active_adapters = tuple(
                adapter
                for adapter in ethernet_adapters
                if adapter.link_status is EthernetStatus.ACTIVE
            )

            if active_adapters:
                detail = (
                    "Ethernet link active on "
                    f"{', '.join(a.name for a in active_adapters)}."
                )
                logger.info("Ethernet connectivity confirmed: %s", detail)
                return EthernetLinkResult(
                    connected=True,
                    detail=detail,
                    checked_adapter_names=tuple(
                        a.name for a in ethernet_adapters
                    ),
                    active_adapter_names=tuple(
                        a.name for a in active_adapters
                    ),
                    primary_adapter=active_adapters[0],
                )

            if not ethernet_adapters:
                last_result = EthernetLinkResult(
                    connected=False,
                    detail=(
                        "No physical, enabled Ethernet adapter was "
                        "detected."
                    ),
                )
            else:
                last_result = EthernetLinkResult(
                    connected=False,
                    detail=(
                        "Ethernet adapter(s) detected but none report "
                        "an active link: "
                        f"{', '.join(a.name for a in ethernet_adapters)}."
                    ),
                    checked_adapter_names=tuple(
                        a.name for a in ethernet_adapters
                    ),
                )

            if attempt < attempts - 1:
                logger.warning(
                    "Ethernet not yet connected (attempt %d/%d): %s "
                    "-- retrying in %.1fs.",
                    attempt + 1,
                    attempts,
                    last_result.detail,
                    retry_delay_seconds,
                )
                sleep(retry_delay_seconds)

        logger.error(
            "Ethernet connectivity check failed after %d attempt(s): "
            "%s",
            attempts,
            last_result.detail,
        )
        return last_result


__all__ = ["EthernetChecker", "EthernetLinkResult"]
