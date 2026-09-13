"""
Project Aquila
=============

Historical placeholder -- superseded, not imported

This file predates the two-phase-boot architecture documented in
``provisioning/__init__.py``'s module docstring. It was originally
scaffolded on the assumption that Phase One (the WMI/Python code that
runs from WinPE) would perform disk partitioning itself.

That is not how provisioning actually works: Phase One only *selects*
and *describes* the target disk (REQ-PROV-007) via
``provisioning.answer_file.ProvisioningProfile.disk_list`` /
``.disk_filter``, which ``render_answer_file()`` writes into Proxmox's
own ``[disk-setup]`` answer-file section. Partitioning itself is
performed entirely by Proxmox's own installer during Phase Two, a
separate Debian-based Linux environment this Windows/WMI codebase
cannot run inside.

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
