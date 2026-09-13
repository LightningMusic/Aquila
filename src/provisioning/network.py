"""
Project Aquila
=============

Historical placeholder -- superseded, not imported

This file predates the two-phase-boot architecture documented in
``provisioning/__init__.py``'s module docstring. It was originally
scaffolded on the assumption that Phase One (the WMI/Python code that
runs from WinPE) would configure the deployed node's own networking
directly.

Phase One's real network-related responsibilities are, instead, split
across two purpose-built modules already implemented: verifying the
*deployment environment's* own Ethernet link and Deployment Controller
reachability before installation is authorized
(``provisioning.connectivity.ConnectivityChecker``, REQ-PROV-002/003/
004), and describing the *node's* post-install network configuration
(``provisioning.answer_file.ProvisioningProfile``'s ``[network]``
fields), which ``render_answer_file()`` writes into Proxmox's own
answer file for Proxmox's installer to apply during Phase Two.

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
