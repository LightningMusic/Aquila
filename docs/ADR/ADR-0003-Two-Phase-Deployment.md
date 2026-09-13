# ADR-0003: Two-Phase Deployment

## Status

Accepted

## Context

Workflow B (Aquila Node Provisioning) must install Proxmox VE on the
target machine (REQ-PROV-005 through REQ-PROV-021) and then bring up
Aquila's own Bootstrap Engine on first boot (REQ-BOOT-001 through
REQ-BOOT-020) to join the machine to the cluster.

Everything Aquila had built before this decision — hardware inspection,
data recovery, storage sanitization, and the beginning of provisioning —
is Python code built against the Windows WMI API, and runs from a WinPE
(Windows Preinstallation Environment) boot session, because WMI-based
firmware and hardware detection (`bios/`, `hardware/`) requires Windows.

Proxmox VE, however, is a Debian-based Linux distribution with its own
installer. That installer cannot run inside WinPE, and WinPE cannot host
a second, different operating system's install process within the same
boot session. A single-phase design — one boot environment doing
everything from inspection through a running Proxmox system — is not
technically possible with this combination of tooling.

## Decision

Provisioning is split across two boot phases carried on the same USB
deployment media:

- **Phase One** (WinPE, this codebase's `src/provisioning/` package):
  validates the target system against minimum requirements
  (`provisioning.validator.MinimumRequirementsValidator`), verifies
  Ethernet and Deployment Controller connectivity
  (`provisioning.connectivity.ConnectivityChecker`), renders Proxmox's
  own official automated-installation answer file
  (`provisioning.answer_file.render_answer_file`, producing
  `answer.toml`), verifies the Phase Two boot media's integrity
  (`provisioning.boot_handoff.BootMediaIntegrityChecker`), and — only
  once every prior check has passed — sets a one-time boot-sequence
  override and reboots into Phase Two
  (`provisioning.boot_handoff.PhaseTwoHandoff`).
- **Phase Two** (a separate, Proxmox-VE-based boot entry on the same
  USB, referenced by `boot_entry_id`): Proxmox's own official installer
  runs unattended, driven entirely by the `answer.toml` Phase One wrote.
  No Aquila Python code executes during Phase Two — REQ-BOOT-001's
  requirement that the Bootstrap Engine execute automatically on first
  boot of the *installed* system is satisfied by Proxmox's own
  confirmed `[first-boot]` answer-file mechanism, which is configured
  (via `ProvisioningProfile.first_boot_command`/
  `.first_boot_ordering`) to invoke Aquila's Bootstrap Engine once the
  installed operating system boots for the first time.

`src/provisioning/` therefore implements only Phase One. Responsibilities
that read as though they belong to Phase One at first glance — disk
partitioning, package installation, network configuration of the
*installed* node, and rebooting into the *installed* operating system —
are Proxmox's own responsibility during Phase Two, expressed
declaratively in the rendered answer file rather than imperatively in
Aquila code. (Several early, pre-this-decision placeholder files in
`src/provisioning/` — `disk.py`, `installer.py`, `network.py`,
`packages.py`, `reboot.py` — were scaffolded before this split was
finalized and are kept only as documented historical notes; see each
file's own docstring.)

## Consequences

- Aquila's own Python/WMI codebase never needs to run on Linux, and
  never needs to reimplement any part of what Proxmox's installer
  already does correctly and is officially supported to do.
- The BCD boot-entry (`boot_entry_id`) that switches from Phase One into
  Phase Two must be registered onto the USB media at build time by the
  Build System (`scripts/build_deployment_usb.ps1`) — Phase One's
  `PhaseTwoHandoff` deliberately never creates this entry itself, since
  doing so from inside a running WinPE session would itself be exactly
  the kind of destructive, hard-to-verify BCD manipulation GP-001
  (Safety Before Automation) exists to avoid. This is tracked as
  outstanding Build System work (see `claude/aquila-project-status.md`
  in the project for current status).
- A defect in the rendered `answer.toml` (an unsupported filesystem
  name, a malformed `[disk-setup]` filter, and so on) surfaces only once
  Phase Two's Proxmox installer actually reads it, not while Phase One
  is still running — `provisioning.answer_file.ProvisioningProfile`'s
  own validation exists specifically to catch as many of these as
  possible before that handoff ever happens, but cannot catch every
  installer-side validation Proxmox itself performs.
- Any future change to Proxmox's own answer-file format or installer
  behavior is an external dependency this codebase must track and
  update `provisioning.answer_file` against; it is not under Aquila's
  control.
