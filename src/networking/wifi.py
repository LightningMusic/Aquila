"""
Project Aquila
=============

Wireless Fallback Connectivity (dev/test only)

**Not part of the finished-product design.** Aquila Node Provisioning
is specified and validated as an Ethernet-only workflow (SRS Section
9.13, REQ-NET-001 through REQ-NET-014) -- Ethernet is what a real
fleet deployment ships with, and nothing about corosync/cluster
networking downstream of Phase One assumes anything else. This module
exists solely so hardware without convenient Ethernet access yet (a
Chromebook, a laptop being tested away from a wired network) can still
exercise Phase One during development, exactly as
``NetworkConfig.allow_wireless_provisioning``'s own docstring
describes. It is never consulted unless a technician has explicitly
opted in via that flag.

Deliberately separate from ``networking.ethernet``
----------------------------------------------------
``hardware.network.NetworkDetector``'s ``NetworkAdapter.link_status``
is explicitly documented as meaningful only for
``NetworkAdapterType.ETHERNET`` -- WMI's ``NetConnectionStatus`` does
not reliably distinguish "radio associated to an SSID" from "adapter
enabled" for wireless hardware the way it does for a cabled link. Using
it for wireless would be exactly the kind of dishonest guess this
codebase's "detect and report the real limitation, never guess"
convention (``preparation.sanitizer``'s ATA/NVMe refusal,
``provisioning.validator``'s per-check reporting) exists to avoid.
Instead, this module shells out to ``netsh wlan``, the same tool
Windows' own Settings UI uses, and reports exactly what it says.

WPA2-PSK only. Open networks, WPA3, and 802.1X/enterprise
authentication are not supported -- this module refuses cleanly with a
clear error rather than silently degrading security or connecting to
the wrong kind of network.

Requires WinPE's WiFi optional component (``WinPE-WiFi-Package`` plus
its ``WinPE-Dot3Svc``/``WinPE-WMI`` dependencies) and a working driver
for the target machine's wireless chipset to already be present on the
boot media -- see ``scripts/build_deployment_usb.ps1``. Without both,
every method here reports a clear, honest failure rather than an
unexplained hang.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from common.constants.logging import NETWORK_LOGGER
from hardware import is_windows
from models.hardware.network import NetworkAdapter, NetworkAdapterType

logger = logging.getLogger(NETWORK_LOGGER)

_WLAN_PROFILE_TEMPLATE = """<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid}</name>
    <SSIDConfig>
        <SSID>
            <name>{ssid_hex}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>manual</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>WPA2PSK</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{password}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>
"""


def _run_netsh(command: Sequence[str], *, timeout: float = 30.0) -> tuple[int, str, str]:
    """
    Run ``netsh`` without a shell and capture its output.

    A private helper local to this module, matching
    ``networking.dhcp``'s own identically-named, identically-shaped
    helper -- kept separate rather than shared because each module's
    mutating ``netsh`` surface (interface IP config there, WLAN
    profiles/connections here) is unrelated to the other's.
    """

    if not is_windows():
        return (
            127,
            "",
            "netsh is only available on Windows; the current platform "
            "is not supported.",
        )

    try:
        process = subprocess.run(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=timeout,
            check=False,
        )
        return (process.returncode, process.stdout, process.stderr)
    except FileNotFoundError as exc:
        return (127, "", str(exc))
    except subprocess.TimeoutExpired:
        return (124, "", "Operation timed out.")
    except (OSError, ValueError) as exc:
        return (126, "", str(exc))


@dataclass(frozen=True, slots=True)
class WirelessLinkResult:
    """The outcome of one wireless association check or connect attempt."""

    connected: bool
    ssid: str
    detail: str
    primary_adapter: NetworkAdapter | None = field(default=None)


class WirelessChecker:
    """
    Associates to a configured Wi-Fi network and verifies the result,
    via ``netsh wlan`` (REQ-NET's Ethernet-only scope has no
    requirement identifiers for this -- see this module's own
    docstring for why it exists anyway).
    """

    def interface_name(self) -> str | None:
        """
        The Windows interface alias ``netsh wlan`` reports (e.g.
        ``"Wi-Fi"``), or ``None`` if no wireless interface/driver is
        present -- the single most common reason this whole fallback
        can't be used: WinPE has no driver for this machine's Wi-Fi
        chipset. Returns only the first wireless interface found; a
        machine with more than one is not a case this module tries to
        disambiguate.
        """

        code, stdout, _stderr = _run_netsh(["netsh", "wlan", "show", "interfaces"])
        if code != 0:
            return None

        match = re.search(r"^\s*Name\s*:\s*(.+?)\s*$", stdout, re.MULTILINE)
        return match.group(1) if match else None

    def check_link(self) -> WirelessLinkResult:
        """
        Report whatever ``netsh wlan show interfaces`` says right now
        -- no connection attempt, just an honest read of current
        association state. Used both after :meth:`connect` and by
        ``provisioning.connectivity.ConnectivityChecker`` to re-verify
        the link is still up immediately before provisioning begins.
        """

        code, stdout, stderr = _run_netsh(["netsh", "wlan", "show", "interfaces"])
        if code != 0:
            return WirelessLinkResult(
                connected=False,
                ssid="",
                detail=(
                    "'netsh wlan show interfaces' failed -- the WinPE "
                    "WiFi optional component or a wireless driver is "
                    f"likely missing from this boot media ({stderr.strip() or 'no output'})."
                ),
            )

        name_match = re.search(r"^\s*Name\s*:\s*(.+?)\s*$", stdout, re.MULTILINE)
        state_match = re.search(r"^\s*State\s*:\s*(.+?)\s*$", stdout, re.MULTILINE)
        ssid_match = re.search(r"^\s*SSID\s*:\s*(.+?)\s*$", stdout, re.MULTILINE)

        connected = bool(state_match) and state_match.group(1).strip().lower() == "connected"
        ssid = ssid_match.group(1).strip() if ssid_match else ""

        if connected:
            adapter = NetworkAdapter(
                name=name_match.group(1).strip() if name_match else "Wi-Fi",
                description=f"Wireless (SSID: {ssid})",
                adapter_type=NetworkAdapterType.WIRELESS,
                is_physical=True,
                is_enabled=True,
            )
            return WirelessLinkResult(
                connected=True,
                ssid=ssid,
                detail=f"Wireless link active on SSID '{ssid}'.",
                primary_adapter=adapter,
            )

        return WirelessLinkResult(
            connected=False,
            ssid=ssid,
            detail="No wireless interface is currently associated to a network.",
        )

    def connect(
        self,
        ssid: str,
        password: str,
        *,
        retry_count: int,
        retry_delay_seconds: float,
        sleep: Callable[[float], None] = time.sleep,
    ) -> WirelessLinkResult:
        """
        Add a WPA2-PSK profile for ``ssid``/``password`` and connect,
        retrying the association check up to ``retry_count`` times
        (mirroring ``networking.ethernet.EthernetChecker.check_link``'s
        retry discipline) before honestly reporting failure.
        """

        interface = self.interface_name()
        if interface is None:
            return WirelessLinkResult(
                connected=False,
                ssid=ssid,
                detail=(
                    "No wireless network interface was found. The WinPE "
                    "WiFi optional component and/or a driver for this "
                    "machine's wireless chipset is missing from the "
                    "boot media."
                ),
            )

        profile_xml = _WLAN_PROFILE_TEMPLATE.format(
            ssid=_xml_escape(ssid),
            ssid_hex=ssid.encode("utf-8").hex(),
            password=_xml_escape(password),
        )

        profile_path = Path(tempfile.gettempdir()) / f"aquila-wlan-{uuid.uuid4().hex}.xml"
        try:
            profile_path.write_text(profile_xml, encoding="utf-8")

            add_code, _add_out, add_err = _run_netsh(
                [
                    "netsh",
                    "wlan",
                    "add",
                    "profile",
                    f"filename={profile_path}",
                    f"interface={interface}",
                ]
            )
            if add_code != 0:
                return WirelessLinkResult(
                    connected=False,
                    ssid=ssid,
                    detail=f"Failed to add the Wi-Fi profile for '{ssid}': {add_err.strip() or 'unknown netsh error'}.",
                )

            connect_code, _conn_out, connect_err = _run_netsh(
                [
                    "netsh",
                    "wlan",
                    "connect",
                    f"name={ssid}",
                    f"ssid={ssid}",
                    f"interface={interface}",
                ]
            )
            if connect_code != 0:
                return WirelessLinkResult(
                    connected=False,
                    ssid=ssid,
                    detail=f"Failed to connect to '{ssid}': {connect_err.strip() or 'unknown netsh error'}.",
                )
        finally:
            # Best-effort cleanup: never leave the plaintext key material
            # in a temp file longer than the single netsh call needs it.
            try:
                profile_path.unlink(missing_ok=True)
            except OSError:
                pass

        attempts = max(1, retry_count + 1)
        last_result = WirelessLinkResult(
            connected=False, ssid=ssid, detail="Wireless association was not checked."
        )
        for attempt in range(attempts):
            last_result = self.check_link()
            if last_result.connected and last_result.ssid == ssid:
                logger.info("Wireless connectivity confirmed: %s", last_result.detail)
                return last_result

            if attempt < attempts - 1:
                sleep(retry_delay_seconds)

        logger.warning(
            "Wireless connection to '%s' could not be confirmed: %s",
            ssid,
            last_result.detail,
        )
        return last_result


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


__all__ = ["WirelessChecker", "WirelessLinkResult"]
