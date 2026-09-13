# -*- mode: python ; coding: utf-8 -*-
#
# Project Aquila
# =============
#
# PyInstaller spec for the real Aquila application (src/main.py), NOT
# to be confused with Project-Aquila-Demo.spec, which builds a
# separate, self-documented cosmetic marketing mockup unrelated to
# this codebase.
#
# Builds a single onefile executable, `aquila.exe`, that dispatches to
# whichever frontend the invocation asks for (see src/main.py's own
# docstring): no arguments launches the Technician Console GUI, a
# cli/ subcommand launches the flag-driven CLI, and `autorun` launches
# the deployment USB's own unattended boot flow.
#
# Why PyInstaller instead of bundling a raw embeddable Python
# distribution into the WinPE image (this project's original
# approach, in scripts/build_deployment_usb.ps1's first draft):
# PyInstaller's own dependency-collection machinery finds and bundles
# the pywintypes/pythoncom binary DLLs `wmi`/`pywin32` need
# automatically, rather than requiring a hand-copied venv
# site-packages tree to somehow work correctly inside an offline
# WinPE image with no pip and no install-time COM registration step.
# See docs/ADR/ (once a Build System ADR exists) and
# claude/aquila-project-status.md in the project for the full
# reasoning and its current verification status -- this has not yet
# been run against real Windows ADK tooling or real hardware.
#
# console=True is required, not a default left over from a template:
# `autorun` (src/cli/autorun.py) reads operator confirmations via
# input() and prints progress via stdout, both of which need a real
# console. The one accepted cosmetic cost is that launching the
# Technician Console GUI (no arguments) also briefly shows a console
# window behind it -- switching to console=False would silently break
# `autorun` and the flag-driven CLI's stdout output instead, which is
# the worse trade.
#
# Explicit hiddenimports below guard against a known, narrow
# PyInstaller/pywin32 packaging gotcha: `wmi` and `win32com` both
# reach a few of their own submodules (win32timezone chief among them)
# through means PyInstaller's static import analysis does not always
# see. Every bios/providers/*.py vendor provider, by contrast, is
# imported statically and unconditionally by bios/detection.py's own
# provider registry (verified directly against that file), so none of
# them need to be listed here -- PyInstaller's ordinary analysis
# already finds them.

hiddenimports = [
    "win32timezone",
    "win32com",
    "win32com.client",
    "wmi",
    "pythoncom",
    "pywintypes",
]

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='aquila',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
