"""
Project Aquila
=============

Provisioning Engine

Phase One of Workflow B (Aquila Node Provisioning) -- SRS Section
10.6, REQ-PROV-001 through REQ-PROV-021.

SRS defect notice
--------------------
The current SRS document (``docs/SRS/Project-Aquila-SRS.md``) contains
two duplicate, back-to-back "# 11.6 Provisioning Engine Requirements"
sections, each independently defining REQ-PROV-001 through
REQ-PROV-021 with different substantive content (one framed around
"install Proxmox VE" directly; the other adding network/controller/
minimum-hardware preconditions and framing installation as "transform
prepared hardware into a fully configured node"). This package was
implemented against a merged union of both versions' requirements --
they are largely compatible, not contradictory, so no requirement from
either version was dropped. This is a genuine documentation defect
this codebase cannot fix directly (the SRS is synced from a separate
GitHub source); see ``claude/aquila-project-status.md`` for the full
side-by-side comparison and a recommendation to de-duplicate the
section in the source document.

Two-phase-boot architecture
------------------------------
Everything Aquila has built so far (``hardware``, ``inspection``,
``recovery``, ``preparation``, and this package) is WMI/Python code
that only runs on Windows (WinPE) -- Proxmox VE's own installer is a
separate, Debian-based Linux environment that cannot run from within
WinPE. This package therefore implements only Phase One's
contribution to provisioning: validating the target system, rendering
Proxmox's own official automated-installation answer file
(``answer.toml``), verifying the embedded Phase Two boot media, and
triggering a one-time boot handoff into it. The actual Proxmox VE
installation runs entirely within Phase Two, driven by Proxmox's own
installer against the rendered answer file -- see
``provisioning.boot_handoff`` and ``provisioning.report``'s module
docstrings for the full architectural reasoning, including how
REQ-BOOT-001's automatic Bootstrap Engine invocation is satisfied by
Proxmox's own confirmed ``[first-boot]`` answer-file mechanism rather
than any Aquila code running during Phase Two.

Public surface:

* :class:`provisioning.validator.MinimumRequirementsValidator` --
  REQ-PROV-005/006's report-based minimum-hardware checks.
* :class:`provisioning.connectivity.ConnectivityChecker` --
  REQ-PROV-002/003/004's live Ethernet/Controller checks.
* :class:`provisioning.answer_file.ProvisioningProfile` /
  :func:`provisioning.answer_file.render_answer_file` --
  REQ-PROV-007/010/012/013/015's ``answer.toml`` generation.
* :class:`provisioning.boot_handoff.PhaseTwoHandoff` --
  REQ-PROV-016/017's boot-media verification and boot handoff.
* :class:`provisioning.report.ProvisioningSummary` -- REQ-PROV-011/019's
  reporting.
* :class:`provisioning.provisioning_manager.ProvisioningManager` --
  the orchestrator that ties the above together; the only entry point
  a caller (the Technician Console, or a CLI workflow) should normally
  need.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from .answer_file import (
    SUPPORTED_FILESYSTEMS,
    ProvisioningProfile,
    ProvisioningProfileError,
    render_answer_file,
)
from .boot_handoff import (
    DEFAULT_MANIFEST_FILENAME,
    BootMediaIntegrityChecker,
    BootSequenceError,
    BootSequenceSetter,
    MediaIntegrityResult,
    PhaseTwoHandoff,
    RebootTriggerError,
    Rebooter,
)
from .connectivity import (
    ConnectivityChecker,
    ControllerReachabilityResult,
    ControllerSocketProber,
    EthernetCheckResult,
)
from .provisioning_manager import ProvisioningManager
from .report import ProvisioningSummary
from .validator import (
    MinimumRequirementsResult,
    MinimumRequirementsValidator,
    RequirementCheck,
)

__all__ = [
    "DEFAULT_MANIFEST_FILENAME",
    "SUPPORTED_FILESYSTEMS",
    "BootMediaIntegrityChecker",
    "BootSequenceError",
    "BootSequenceSetter",
    "ConnectivityChecker",
    "ControllerReachabilityResult",
    "ControllerSocketProber",
    "EthernetCheckResult",
    "MediaIntegrityResult",
    "MinimumRequirementsResult",
    "MinimumRequirementsValidator",
    "PhaseTwoHandoff",
    "ProvisioningManager",
    "ProvisioningProfile",
    "ProvisioningProfileError",
    "ProvisioningSummary",
    "RebootTriggerError",
    "Rebooter",
    "RequirementCheck",
    "render_answer_file",
]
