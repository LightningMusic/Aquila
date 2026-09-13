"""
Project Aquila
=============

Historical placeholder -- superseded, not imported

This file predates the two-phase-boot architecture documented in
``provisioning/__init__.py``'s module docstring. It was originally
scaffolded on the assumption that Phase One (the WMI/Python code that
runs from WinPE) would manage rebooting into the freshly-installed
operating system itself.

That reboot is, instead, Proxmox's own responsibility, controlled by
``provisioning.answer_file.ProvisioningProfile.reboot_mode``/
``.reboot_on_error`` (Proxmox's ``[global]`` answer-file keys). The one
reboot this codebase does trigger directly is the *earlier* one-time
boot-sequence handoff from Phase One into the Phase Two installer
media, implemented in
``provisioning.boot_handoff.PhaseTwoHandoff``/``Rebooter``
(REQ-PROV-016).

This module is not imported by ``provisioning/__init__.py`` or
anything else in the codebase, contains no logic, and is kept only so
a future repository cleanup pass has a clear paper trail for why it is
safe to delete rather than an unexplained empty file.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations
