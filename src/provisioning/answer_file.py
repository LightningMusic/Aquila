"""
Project Aquila
=============

Proxmox VE Automated-Installation Answer File

Implements REQ-PROV-007 (partition the target storage per Aquila
configuration), REQ-PROV-009 (configure the installed operating
system to automatically execute the Bootstrap Engine during first
boot -- one SRS "11.6" section's wording; the other section's
REQ-PROV-009 -- "install all required Aquila software components" --
is satisfied the same way, since the rendered ``[first-boot]`` block
below is what actually fetches and installs the Aquila Bootstrap
Engine onto the node), REQ-PROV-010 (install required OS packages per
deployment configuration -- via the rendered ``[first-boot]``
pointer), REQ-PROV-012 (configure networking per deployment policy),
REQ-PROV-013 (install required SSH configuration), REQ-PROV-014
(prepares the system for Bootstrap execution, and -- combined with
every other field here being rendered automatically from
``ProvisioningProfile`` -- means the technician is never required to
manually configure Proxmox after installation, satisfying both SRS
sections' REQ-PROV-014 wording), and REQ-PROV-015 (support deployment
profiles that define storage layout, partition scheme, filesystem,
package selection, and bootstrap configuration).

Generates ``answer.toml`` for Proxmox VE's own, official Automated
Installation mechanism (``proxmox-auto-install-assistant prepare-iso``,
documented at pve.proxmox.com/wiki/Automated_Installation) rather than
inventing an Aquila-specific installer -- this is what REQ-PROV-021
("utilize an unmodified, official Proxmox VE installation") requires:
Aquila supplies data to Proxmox's own supported automation, it does
not patch or replace the Proxmox installer itself.

Schema source and confidence
-------------------------------
Every section/key below (``[global]``, ``[network]``, ``[disk-setup]``,
``[first-boot]``) was confirmed against verbatim examples fetched
directly from the official wiki page earlier in this session's
research -- hyphenated/kebab-case throughout (a third-party GitHub
example using underscore-style keys was found and deliberately
discarded as non-authoritative once that confirmation was made).

Two decisions below are flagged as lower-confidence because a second,
follow-up fetch to recover additional verbatim worked examples was not
available for the remainder of this session (external fetch access
was exhausted). Both keep this module honestly degrading -- raising
``ProvisioningProfileError`` when the caller has not supplied enough
information, rather than guessing:

* ``[network]``'s ``cidr``/``gateway``/``dns`` value *types* for
  ``source = "from-answer"`` are rendered here as single strings
  (``dns`` space-joins multiple servers) based on the confirmed key
  names and Proxmox's classic installer's own single-string DNS
  convention. This should be spot-checked with
  ``proxmox-auto-install-assistant validate-answer`` before first
  real use.
* ``[disk-setup]``'s ``filter`` value is UDEV-property-keyed per the
  official schema, but this module never fabricates a specific UDEV
  property name (for example, guessing ``ID_SERIAL_SHORT``) it has
  not independently verified. By default this module selects the
  target disk with ``disk-list``, using a caller-supplied Linux-side
  device name -- Preparation/Inspection only ever see the
  Windows-side ``\\\\.\\PHYSICALDRIVEn`` path, which is not valid
  here. A caller that already knows a working UDEV filter for its
  hardware (for example, confirmed with ``proxmox-auto-install-
  assistant device-match``) may pass ``disk_filter`` instead and it
  is rendered verbatim.

Foundational fix (``workflows/`` session): ``[first-boot].ordering``
-------------------------------------------------------------------
An earlier session hardcoded ``ordering = "before-network"`` for the
``[first-boot]`` hook that runs ``BootstrapManager.run()``. Refetching
the official schema (pve.proxmox.com/wiki/Automated_Installation)
while designing ``workflows.provisioning_manager`` -- which is
responsible for making sure Bootstrap can actually reach the
Deployment Controller once it runs -- confirmed this was a genuine
bug, not a stylistic choice: ``"before-network"`` runs the hook
*before any networking devices are set up*, which would make
REQ-BOOT-002 ("verify communication with the Deployment Controller")
impossible to satisfy on the very first attempt. ``ProvisioningProfile``
now exposes ``first_boot_ordering`` (default ``"network-online"`` --
runs once network connectivity is established, still satisfying
REQ-BOOT-001's "automatically after the first successful system boot"
as tightly as the schema allows), validated against the three
official values (``before-network``/``network-online``/``fully-up``)
rather than left silently hardcoded, per GP-003.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from common.constants.deployment import DEFAULT_FILESYSTEM
from common.exceptions.deployment import DeploymentConfigurationError

#: Proxmox's own [disk-setup].filesystem choices, confirmed against
#: the official schema.
SUPPORTED_FILESYSTEMS: tuple[str, ...] = ("ext4", "xfs", "zfs", "btrfs")

#: Proxmox's own [global].reboot-mode choices, confirmed against the
#: official schema.
_REBOOT_MODES: tuple[str, ...] = ("reboot", "power-off")

#: Proxmox's own [disk-setup].filter-match choices, confirmed against
#: the official schema.
_FILTER_MATCH_MODES: tuple[str, ...] = ("any", "all")

_IP_ASSIGNMENT_METHODS: tuple[str, ...] = ("dhcp", "static")

#: Proxmox's own [first-boot].ordering choices, confirmed against the
#: official schema (Automated_Installation wiki page, fetched
#: directly): "before-network" runs before any networking devices are
#: set up, "network-online" runs after network connectivity has been
#: established, "fully-up" runs once the system is fully booted and
#: ready for normal operation. Proxmox's own default is "fully-up".
_FIRST_BOOT_ORDERINGS: tuple[str, ...] = (
    "before-network",
    "network-online",
    "fully-up",
)


class ProvisioningProfileError(DeploymentConfigurationError):
    """Raised when a ``ProvisioningProfile`` cannot be validated or rendered."""


@dataclass(slots=True, frozen=True)
class ProvisioningProfile:
    """
    Everything REQ-PROV-007/010/012/013/015 need to generate one
    node's ``answer.toml``.

    Not backed by a ``configs/*.yaml`` schema of its own -- Appendix D
    does not list a dedicated provisioning-profile configuration file,
    and several of these fields (root credentials, per-node hostname
    fragment, SSH keys) are node-specific facts the Technician Console
    supplies at deployment time, not a static policy file. Fields with
    Aquila-wide defaults (filesystem, keyboard, country, timezone) are
    still overridable per call, exactly like ``DeploymentConfig``'s
    own fields.

    Root credentials follow ``ControllerConfig
    .authentication_token_env_var``'s existing convention
    (REQ-SEC-008/009/010: never store a secret value directly) --
    ``root_password_env_var`` names an environment variable read by
    the *caller* at render time; this dataclass never holds the
    plaintext value itself.
    """

    node_hostname: str
    domain: str
    mailto: str

    target_device_serial: str
    disk_list: tuple[str, ...] = ()
    disk_filter: Mapping[str, tuple[str, ...]] | None = None
    disk_filter_match: str = "any"
    filesystem: str = DEFAULT_FILESYSTEM

    keyboard: str = "en-us"
    country: str = "us"
    timezone: str = "UTC"

    root_password_env_var: str = "AQUILA_NODE_ROOT_PASSWORD"
    root_password_is_hashed: bool = False
    root_ssh_keys: tuple[str, ...] = ()

    reboot_on_error: bool = False
    reboot_mode: str = "reboot"
    subscription_key: str | None = None

    ip_assignment_method: str = "dhcp"
    static_cidr: str | None = None
    static_gateway: str | None = None
    static_dns_servers: tuple[str, ...] = ()

    bootstrap_source_url: str | None = None
    bootstrap_cert_fingerprint: str | None = None
    first_boot_ordering: str = "network-online"

    def __post_init__(self) -> None:
        if not self.node_hostname.strip():
            raise ProvisioningProfileError(
                "ProvisioningProfile.node_hostname is required."
            )
        if not self.domain.strip():
            raise ProvisioningProfileError(
                "ProvisioningProfile.domain is required."
            )
        if "@" not in self.mailto:
            raise ProvisioningProfileError(
                "ProvisioningProfile.mailto must be a valid notification "
                "email address (REQ-PROV-015's [global].mailto is "
                "required)."
            )
        if not self.target_device_serial.strip():
            raise ProvisioningProfileError(
                "ProvisioningProfile.target_device_serial is required -- "
                "the answer file must identify the exact physical disk "
                "Preparation already sanitized."
            )

        if len(self.country) != 2:
            raise ProvisioningProfileError(
                "ProvisioningProfile.country must be a 2-letter country "
                "code, per the official [global].country schema."
            )

        if self.filesystem not in SUPPORTED_FILESYSTEMS:
            raise ProvisioningProfileError(
                f"Unsupported filesystem '{self.filesystem}' -- expected "
                f"one of {SUPPORTED_FILESYSTEMS}."
            )

        if self.reboot_mode not in _REBOOT_MODES:
            raise ProvisioningProfileError(
                f"Unsupported reboot_mode '{self.reboot_mode}' -- "
                f"expected one of {_REBOOT_MODES}."
            )

        if bool(self.disk_list) and bool(self.disk_filter):
            raise ProvisioningProfileError(
                "ProvisioningProfile.disk_list and disk_filter are "
                "mutually exclusive, matching Proxmox's own "
                "[disk-setup] schema."
            )
        if not self.disk_list and not self.disk_filter:
            raise ProvisioningProfileError(
                "ProvisioningProfile requires either disk_list or "
                "disk_filter -- the target disk must be explicitly "
                "identified before an irreversible installation begins."
            )
        if self.disk_filter_match not in _FILTER_MATCH_MODES:
            raise ProvisioningProfileError(
                f"Unsupported disk_filter_match "
                f"'{self.disk_filter_match}' -- expected one of "
                f"{_FILTER_MATCH_MODES}."
            )

        if self.ip_assignment_method not in _IP_ASSIGNMENT_METHODS:
            raise ProvisioningProfileError(
                "ProvisioningProfile.ip_assignment_method must be one of "
                f"{_IP_ASSIGNMENT_METHODS}."
            )
        if self.ip_assignment_method == "static" and not (
            self.static_cidr and self.static_gateway
        ):
            raise ProvisioningProfileError(
                "static_cidr and static_gateway are required when "
                "ip_assignment_method is 'static'."
            )

        if self.first_boot_ordering not in _FIRST_BOOT_ORDERINGS:
            raise ProvisioningProfileError(
                f"Unsupported first_boot_ordering "
                f"'{self.first_boot_ordering}' -- expected one of "
                f"{_FIRST_BOOT_ORDERINGS}."
            )


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_string_array(values: tuple[str, ...]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def render_answer_file(profile: ProvisioningProfile, root_password: str) -> str:
    """
    Render ``profile`` into a Proxmox VE ``answer.toml`` document.

    ``root_password`` is passed explicitly by the caller (read from
    whatever secret store or environment variable
    ``profile.root_password_env_var`` names) rather than read from the
    environment inside this function -- this keeps the module testable
    without a real environment variable, and keeps secret retrieval
    visibly the caller's responsibility (REQ-SEC-008/009/010).

    Raises:
        ProvisioningProfileError: If ``root_password`` is empty.
    """

    if not root_password:
        raise ProvisioningProfileError(
            "A root password (or hash) value is required to render an "
            "answer file -- REQ-SEC-008/009/010 forbid storing it "
            f"anywhere except the environment variable "
            f"'{profile.root_password_env_var}', which the caller must "
            "read and pass in explicitly."
        )

    lines: list[str] = []

    lines.append("[global]")
    lines.append(f"keyboard = {_toml_string(profile.keyboard)}")
    lines.append(f"country = {_toml_string(profile.country)}")
    lines.append(
        f"fqdn = {_toml_string(f'{profile.node_hostname}.{profile.domain}')}"
    )
    lines.append(f"mailto = {_toml_string(profile.mailto)}")
    lines.append(f"timezone = {_toml_string(profile.timezone)}")
    password_key = (
        "root-password-hashed" if profile.root_password_is_hashed else "root-password"
    )
    lines.append(f"{password_key} = {_toml_string(root_password)}")
    if profile.root_ssh_keys:
        lines.append(f"root-ssh-keys = {_toml_string_array(profile.root_ssh_keys)}")
    lines.append(f"reboot-on-error = {_toml_bool(profile.reboot_on_error)}")
    lines.append(f"reboot-mode = {_toml_string(profile.reboot_mode)}")
    if profile.subscription_key:
        lines.append(f"subscription-key = {_toml_string(profile.subscription_key)}")
    lines.append("")

    lines.append("[network]")
    if profile.ip_assignment_method == "dhcp":
        lines.append('source = "from-dhcp"')
    else:
        lines.append('source = "from-answer"')
        lines.append(f"cidr = {_toml_string(profile.static_cidr or '')}")
        lines.append(f"gateway = {_toml_string(profile.static_gateway or '')}")
        if profile.static_dns_servers:
            lines.append(
                f"dns = {_toml_string(' '.join(profile.static_dns_servers))}"
            )
    lines.append("")

    lines.append("[disk-setup]")
    lines.append(f"filesystem = {_toml_string(profile.filesystem)}")
    if profile.disk_list:
        lines.append(f"disk-list = {_toml_string_array(profile.disk_list)}")
    else:
        lines.append(f"filter-match = {_toml_string(profile.disk_filter_match)}")
    lines.append("")

    if profile.disk_filter:
        lines.append("[disk-setup.filter]")
        for key, values in profile.disk_filter.items():
            lines.append(f"{key} = {_toml_string_array(tuple(values))}")
        lines.append("")

    if profile.bootstrap_source_url:
        # [first-boot]: the confirmed, official mechanism by which
        # Proxmox's own installer invokes a script immediately after
        # the first successful boot -- this is what satisfies
        # REQ-BOOT-001 ("Bootstrap Engine shall execute automatically
        # after the first successful system boot") without requiring
        # any Aquila code to run during, or observe, Phase Two's
        # installation itself. See provisioning.report's module
        # docstring for the full architectural note.
        #
        # This same block is also this module's REQ-PROV-009 (configures
        # the installed OS to auto-execute -- and, via ``url``, fetches
        # and installs -- the Bootstrap Engine on first boot) and
        # REQ-PROV-014 (prepares the system for Bootstrap execution, so
        # the technician need not manually configure Proxmox afterward).
        lines.append("[first-boot]")
        lines.append('source = "from-url"')
        lines.append(f"ordering = {_toml_string(profile.first_boot_ordering)}")
        lines.append(f"url = {_toml_string(profile.bootstrap_source_url)}")
        if profile.bootstrap_cert_fingerprint:
            lines.append(
                "cert-fingerprint = "
                f"{_toml_string(profile.bootstrap_cert_fingerprint)}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "SUPPORTED_FILESYSTEMS",
    "ProvisioningProfile",
    "ProvisioningProfileError",
    "render_answer_file",
]
