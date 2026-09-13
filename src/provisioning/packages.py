"""
Project Aquila
=============

Historical placeholder -- superseded, not imported

This file predates the two-phase-boot architecture documented in
``provisioning/__init__.py``'s module docstring. It was originally
scaffolded on the assumption that Phase One (the WMI/Python code that
runs from WinPE) would install operating system packages itself.

Package selection (REQ-PROV-010) is, instead, expressed declaratively
through ``provisioning.answer_file.ProvisioningProfile`` and its
``first_boot_command``/``first_boot_ordering`` fields, which
``render_answer_file()`` writes into Proxmox's own answer file.
Installation is then performed entirely by Proxmox's own installer
during Phase Two, a separate Debian-based Linux environment this
Windows/WMI codebase cannot run inside.

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
