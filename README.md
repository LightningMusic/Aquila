# Project Aquila

Automated, operator-supervised infrastructure provisioning for turning a pile
of surplus/commodity laptops and desktops into a managed Proxmox VE cluster.

Aquila is not an operating system and not a replacement for Proxmox. It is a
deployment platform: point it at a machine, and it inspects the hardware,
optionally recovers any personal data still on it, securely wipes the drive,
installs Proxmox VE, and enrolls the result as a node in your cluster —
mostly unattended, with the technician only asked to approve the
irreversible steps.

The full behavioral specification lives in
[`docs/SRS/Project-Aquila-SRS.md`](docs/SRS/Project-Aquila-SRS.md). Every
piece of behavior described below traces back to a requirement in that
document (`REQ-*`/`NFR-*`); nothing in this codebase should exist that isn't
justified by it, and nothing described there should go unimplemented without
that gap being tracked openly.

## Status

This is an active, in-development project, not a finished product. The
subsystems under `src/` (hardware inspection, data recovery, storage
sanitization, Proxmox provisioning, cluster bootstrap, the Deployment
Controller, inventory, benchmarking, logging, configuration) are each
implemented and unit-tested in isolation. The three real entry points —
the Technician Console GUI, the flag-driven CLI, and the unattended
`autorun` boot flow — exist and are wired together in `src/main.py`.

`aquila.exe` itself has been built successfully with PyInstaller on a real
Windows machine (via `build_aquila_exe.bat`). What has **not** yet
happened: a real end-to-end deployment run against physical target
hardware, and a tested build of the bootable USB deployment media --
`scripts/build_deployment_usb.ps1` (the WinPE/ADK imaging step) is still a
first draft that has not yet been run against real Windows ADK tooling.
Treat any claim of "done" for a subsystem as "done and tested in
isolation," not "verified on a real deployment."

## Quick start (development)

Aquila targets Python 3.11+ and is managed with [`uv`](https://docs.astral.sh/uv/).

```powershell
# Install dependencies into .venv
uv sync

# Run the full test suite (each tests/run_tests_*.py is self-contained;
# hardware-facing tests fake out WMI/COM rather than touching real
# hardware, so this runs the same on any machine). Run from the
# repository root -- each file resolves src/ relative to its own
# location.
uv run python tests/run_tests_bootstrap.py
uv run python tests/run_tests_cli.py
uv run python tests/run_tests_cli_autorun.py
uv run python tests/run_tests_deployment_controller.py
uv run python tests/run_tests_main.py
uv run python tests/run_tests_networking.py
uv run python tests/run_tests_services.py
uv run python tests/run_tests_technician_console.py
uv run python tests/run_tests_workflows.py

# The old repo-root paths (run_tests_bootstrap.py, etc.) still work --
# they're now thin compatibility shims that just run the files above --
# but tests/ is the real, maintained location; edit those, not these.

# Strict static type checking (baseline: 0 new errors beyond the
# documented tkinter/ttk stub-precision findings — see
# claude/aquila-project-status.md in the project for the exact count)
uv run pyright src
```

### Running Aquila itself

`src/main.py` is the single process both frontends launch through. Which
frontend runs depends on how it's invoked:

```powershell
# No arguments: launches the Technician Console (GUI) -- for testing
# on your own desktop.
uv run python src/main.py

# A cli/ subcommand: scripted, flag-driven, no GUI.
uv run python src/main.py inspect --help
uv run python src/main.py retire --help
uv run python src/main.py provision --help
uv run python src/main.py logs --help

# 'autorun': the unattended flow the deployment USB actually runs.
# Only meaningful when pointed at real target hardware -- see the
# warning below before trying this on a machine you care about.
uv run python src/main.py autorun
```

**`autorun` and `retire`/`provision` perform irreversible storage
sanitization once approved.** Never run them against a machine whose data
you have not already backed up or don't intend to erase.

## How deployment media works

Version 1.0 supports two independent workflows (SRS Appendix B):

- **Workflow A — Device Retirement**: inspect, optionally recover data,
  securely wipe. No OS is installed. Used to safely retire hardware that
  won't become a node.
- **Workflow B — Aquila Node Provisioning**: inspect, validate, wipe,
  install Proxmox VE, and hand off to Proxmox's own installer running
  Aquila's rendered answer file, which in turn triggers Bootstrap
  (cluster enrollment, benchmarking, inventory registration) on first boot.

Both run from a bootable USB built from a WinPE (Windows Preinstallation
Environment) image — WinPE is what gives Aquila's Python/WMI-based hardware
inspection and recovery code somewhere to run *before* any OS is installed
on the target machine.

## Building the deployment USB

There are two things to build, in order: `aquila.exe` (the Windows
executable that actually runs), and then the bootable WinPE USB that
carries it. Two batch files at the repository root do this without
requiring you to type any PowerShell or `pyinstaller` commands by hand:

### 1. `build_aquila_exe.bat` — build the executable

Double-click it from inside this repository, on any Windows machine with
Python 3.11+ (or [`uv`](https://docs.astral.sh/uv/)) installed. No
administrator rights needed. It installs the project's dependencies into
a local `.venv`, runs PyInstaller against `Aquila.spec`, and tells you
where `aquila.exe` landed (`dist\aquila.exe` -- `Aquila.spec` builds a
single-file "onefile" executable, so it lands directly in `dist\`, not in
a `dist\aquila\` subfolder). You can also just run this `.exe` directly on
your own desktop afterward to try the Technician Console or the CLI
without touching a USB at all.

### 2. `build_deployment_usb.bat` — build and write the USB

Double-click it on a Windows machine that has the **Windows ADK, plus the
WinPE add-on,** installed
([download/install instructions](https://learn.microsoft.com/windows-hardware/get-started/adk-install)),
with a USB drive already partitioned and formatted as a WinPE boot
partition (see Microsoft's
[Create bootable Windows PE media](https://learn.microsoft.com/windows-hardware/manufacture/desktop/winpe-create-usb-bootable-drive)
for that one-time partitioning step — this script deliberately does not
do it for you, since it's destructive to whatever else is on the drive).

This script:

- asks Windows for administrator rights itself (accept the prompt);
- tries to load the ADK's own command environment automatically, and
  tells you exactly how to do it by hand (the Start Menu's "Deployment
  and Imaging Tools Environment" shortcut) if it can't find it;
- builds `aquila.exe` from source if you haven't already (same
  dependency setup as `build_aquila_exe.bat`);
- asks which USB drive letter to write to, and requires you to type
  `YES` before touching it — nothing is erased without that;
- assembles the WinPE image and writes it to that drive.

Both scripts print a clear `[ERROR]` line and pause before closing if a
step fails, so the window never just vanishes without telling you what to
fix.

Under the hood, `build_deployment_usb.bat` is a front end for
`scripts/build_deployment_usb.ps1` — see that script's own header comment
for the exact build steps and its current verification status (it has not
yet been run against real ADK tooling or real hardware; see "Status"
above). Use the `.ps1` directly if you want more control over its
parameters (a custom working directory, a pre-built `aquila.exe`, driver
injection, etc.) — run `Get-Help .\scripts\build_deployment_usb.ps1 -Full`
from PowerShell for all of them.

## Repository layout

```
src/                  Application source (see docs/SRS Appendix A for
                       the full subsystem-by-subsystem breakdown)
configs/               Deployment, cluster, network, logging, benchmark,
                       and controller configuration (YAML)
scripts/               Build System scripts (deployment USB creation)
build_aquila_exe.bat    Double-click to build aquila.exe from source
build_deployment_usb.bat Double-click to build + write the deployment USB
tools/                 Developer tooling (requirement traceability, etc.)
docs/                  SRS, Architecture Decision Records, roadmap
tests/                 The run_tests_*.py suites (real, maintained location).
                       The same filenames also exist at the repo root as
                       thin compatibility shims -- see "Quick start" above.
typings/               Local type stubs (wmi) for strict pyright checking
.github/workflows/      CI: test suite + strict type checking on every push
```

## License

MIT. See [`LICENSE`](LICENSE).
