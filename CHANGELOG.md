# Changelog

All notable changes to Project Aquila are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/), though it
has not reached a 1.0 release: every 0.x version may include breaking
changes.

## [Unreleased]

### Added

- `src/main.py` entry-point dispatcher: routes to the Technician Console
  (no arguments), the flag-driven CLI (`inspect`/`retire`/`provision`/
  `logs`), or the unattended boot flow (`autorun`).
- `src/cli/autorun.py`: the deployment USB's unattended entry point,
  intended to be the last line of `Startnet.cmd` on real boot media.
- First-draft Build System (`scripts/build_deployment_usb.ps1`) for
  producing the bootable WinPE deployment USB from this repository.
  Syntax-verified; not yet run against real Windows ADK tooling or
  hardware.
- Real project packaging metadata: `pyproject.toml`, `README.md`,
  `LICENSE` (MIT), this changelog.
- Architecture Decision Records under `docs/ADR/`.
- `tools/check_requirement_traceability.py`: cross-references every
  `REQ-*`/`NFR-*` identifier in the SRS against source code and test
  references (SRS Section 13.2's traceability requirement).
- CI workflow (`.github/workflows/`) running the full test suite and
  strict `pyright` type checking on every push and pull request.
- `build_aquila_exe.bat` and `build_deployment_usb.bat`: one-click batch
  entry points at the repository root, so building `aquila.exe` and then
  the bootable deployment USB no longer requires typing any PowerShell or
  `pyinstaller` commands by hand. `build_deployment_usb.bat` self-elevates,
  tries to load the Windows ADK's command environment automatically, and
  requires a typed `YES` confirmation before writing to a USB drive.

- `run_tests_*.py` (9 files) moved from the repository root to `tests/`,
  matching Appendix A's canonical layout. The repository root now keeps
  thin compatibility shims of the same filenames so `python
  run_tests_X.py` from the root keeps working unchanged; `tests/` is the
  real, maintained location going forward. `tools/check_requirement_traceability.py`
  needed no change -- its `tests/` test root already anticipated this.

### Changed

- `src/provisioning/{disk,installer,network,packages,reboot}.py`:
  previously empty placeholder files from before the two-phase-boot
  architecture (Phase One validates and hands off; Phase Two, driven by
  Proxmox's own installer, does the actual partitioning/installation/
  reboot) was finalized. Replaced with documented historical notes
  explaining why each responsibility now lives elsewhere, cross-referenced
  to the module that actually owns it.

### Fixed

- `scripts/build_deployment_usb.ps1` and `build_aquila_exe.bat` both
  checked for the built executable at `dist\aquila\aquila.exe`. That path
  is wrong: `Aquila.spec` builds a single-file ("onefile") executable,
  which PyInstaller places directly at `dist\aquila.exe`, not inside a
  `dist\aquila\` subfolder (that layout only happens with a `COLLECT(...)`
  step, which this spec doesn't have). Confirmed against a real build on
  2026-09-11: PyInstaller succeeded and produced `dist\aquila.exe`, but
  both scripts reported a false failure because they were checking the
  wrong path. Both now check `dist\aquila.exe`.

## [0.1.0] - 2026-06-28

Initial subsystem build-out: hardware inspection, data recovery, storage
preparation/sanitization, Proxmox provisioning (Phase One), cluster
bootstrap, the Deployment Controller, inventory, benchmarking, networking,
logging, and configuration management, each implemented and unit-tested in
isolation against the SRS. No end-to-end process entry point existed yet at
this point in history.
