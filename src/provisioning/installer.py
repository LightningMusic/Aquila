"""
Project Aquila
=============

Historical placeholder -- superseded, not imported

This file predates the two-phase-boot architecture documented in
``provisioning/__init__.py``'s module docstring. It was originally
scaffolded on the assumption that Phase One (the WMI/Python code that
runs from WinPE) would drive the Proxmox VE installer itself.

That is not possible: Proxmox VE's installer is a separate,
Debian-based Linux environment that cannot run from within WinPE.
Phase One's actual contribution to installation is rendering Proxmox's
own automated-installation answer file
(``provisioning.answer_file.render_answer_file``) and verifying/
handing off to the Phase Two boot media that carries Proxmox's real
installer (``provisioning.boot_handoff.PhaseTwoHandoff``). The
installation itself runs entirely within Phase Two, driven by
Proxmox's own installer against that rendered answer file.

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
