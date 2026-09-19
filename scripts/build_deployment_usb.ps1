#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Project Aquila -- Build System: WinPE Deployment USB Builder

.DESCRIPTION
    Builds Project Aquila's bootable deployment USB (SRS Section
    9.15/10.14 -- the Build System, the one major piece of the SRS with
    no prior implementation at all). Assembles a WinPE-based boot
    environment that runs ``cli.autorun.run_autorun()`` automatically
    on boot (see ``src/cli/autorun.py``'s own docstring): plug the
    resulting USB into a target machine, boot from it, and it inspects
    the hardware, walks the operator through the recovery/wipe/install
    confirmations GP-001 requires, and finishes.

    This is a first, careful draft, grounded in Microsoft's own current
    WinPE documentation (Microsoft Learn: "Create bootable Windows PE
    media", "WinPE: Add packages (Optional Components Reference)",
    "Add or Remove Packages Offline Using DISM") rather than assumed --
    but it has NOT been executed or tested against real Windows ADK
    tooling or real hardware, for a structural reason: the session that
    wrote it has no shell access to a Windows machine and cannot boot
    physical hardware at all. Run it, capture the exact output of
    whichever step fails, and report that back -- this script should be
    expected to need at least one real iteration.

    REVISION NOTE (see docs/ADR/ADR-0003-Two-Phase-Deployment.md and
    claude/aquila-project-status.md in the project for the full
    history): the first draft of this script bundled a raw embeddable
    Python distribution plus a hand-copied venv site-packages tree into
    the WinPE image, and flagged a specific, unresolved risk: whether
    ``pywin32``/``wmi`` (needed by ``bios/``/``hardware/``'s WMI-based
    detection) would work correctly without
    ``pywin32_postinstall.py``'s COM registration step, which only
    makes sense against a *running* system, not an offline image.

    This revision replaces that approach entirely. Step 5 now installs
    a single PyInstaller-built executable, ``aquila.exe`` (see
    ``Aquila.spec`` at the repository root), instead of a Python
    interpreter plus a copied dependency tree. This is a strictly
    better approach, not just a different one: PyInstaller's own
    dependency-collection machinery finds and bundles the
    ``pywintypes``/``pythoncom`` binary DLLs ``wmi``/``pywin32`` need
    automatically as part of freezing the executable -- there is no
    site-packages tree to hand-copy, no ``._pth`` file to edit, and no
    reliance on a runtime registry-registration step that was never
    going to apply to an offline image anyway. This does not
    *eliminate* the original risk -- only a real boot test can do that
    -- but it removes an entire self-inflicted layer of it. If
    ``aquila.exe`` still cannot use WMI once booted inside WinPE, that
    is now a PyInstaller/pywin32-freezing question with a much larger
    body of prior art to debug against, not a bespoke problem unique to
    this script's own packaging choices.

.PARAMETER WorkDir
    Working directory for the WinPE file tree (copype's output). Reused
    across builds if the packages inside it don't need to change --
    delete it for a clean rebuild.

.PARAMETER AquilaExePath
    Path to a pre-built ``aquila.exe`` (PyInstaller onefile output,
    ``dist\aquila.exe`` after running ``pyinstaller Aquila.spec``
    from the repository root). When omitted, this script builds it
    itself by running ``pyinstaller`` against ``Aquila.spec`` -- see
    ``Invoke-PyInstallerBuild`` below -- which requires the ``dev``
    optional dependency group (``uv sync --all-extras``, or
    ``pip install pyinstaller``) to already be installed.

.PARAMETER UsbDriveLetter
    Drive letter (e.g. ``E``) of an already-formatted FAT32 WinPE
    partition on the target USB drive -- see Microsoft's own "Create
    bootable Windows PE media" documentation for partitioning a USB
    drive with diskpart first. This script does not partition or format
    a drive itself: that step is destructive to whatever is already on
    the USB, and warrants the same explicit, un-scriptable operator
    attention as any other irreversible action in this project (GP-001).

.EXAMPLE
    .\build_deployment_usb.ps1 `
        -WorkDir C:\AquilaBuild\WinPE `
        -UsbDriveLetter E

.EXAMPLE
    # Using an already-built exe instead of letting this script invoke
    # PyInstaller itself:
    .\build_deployment_usb.ps1 `
        -WorkDir C:\AquilaBuild\WinPE `
        -AquilaExePath C:\Aquila\dist\aquila.exe `
        -UsbDriveLetter E
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$WorkDir,

    [Parameter(Mandatory = $true)]
    [string]$UsbDriveLetter,

    # Repository root -- defaults to this script's own repo checkout,
    # resolved in the body rather than here. This is an advanced script
    # ([CmdletBinding()] with mandatory parameters), and PowerShell
    # evaluates parameter defaults during parameter binding, before the
    # script scope exists and $PSScriptRoot is populated -- so a default
    # referencing $PSScriptRoot binds to an empty string under the
    # `powershell -File` invocation build_deployment_usb.bat uses.
    [string]$RepoRoot,

    # Pre-built aquila.exe. If not supplied, built automatically from
    # $RepoRoot\Aquila.spec (see Invoke-PyInstallerBuild).
    [string]$AquilaExePath,

    [string]$Architecture = "amd64",

    # Optional: a folder of extracted (.inf-based) drivers to inject
    # into the boot image (Step 4, Add-Drivers) -- e.g. a wireless
    # NIC driver WinPE's inbox set doesn't already cover. Recurses
    # into subfolders. Left unset, Step 4 is skipped entirely.
    [string]$DriversDir,

    # Opt-in, dev/test only (see config.schemas.network_schema
    # .NetworkConfig.allow_wireless_provisioning's docstring) -- adds
    # WinPE's WiFi optional component so the image *can* associate to
    # a wireless network at all. Off by default: the finished-product
    # design is Ethernet-only, and this component (plus whatever
    # wireless driver -DriversDir supplies) has no reason to be in a
    # normal build.
    [switch]$IncludeWifiSupport,

    # Erase the target USB's entire partition table before writing,
    # leaving one active FAT32 partition spanning the disk.
    #
    # MakeWinPEMedia /UFD only runs "select volume / format / active"
    # -- it reformats the chosen *volume* and never touches the
    # partition table. A stick that previously held a multi-partition
    # layout therefore keeps its other partitions, and any bootloader
    # on them, which is enough to stop the target machine booting this
    # media at all (found the hard way on a Ventoy stick: its 32MB
    # VTOYEFI partition, with Ventoy's own EFI bootloader and GRUB,
    # survived the build and the target silently refused to boot).
    #
    # Off by default because it is destructive beyond the single
    # volume the operator named (GP-001).
    [switch]$CleanUsbDisk,

    # Add the WinPE-NetFX / WinPE-Scripting / WinPE-PowerShell chain on
    # top of WinPE-WMI. Aquila does not need any of it -- aquila.exe is
    # a self-contained native executable -- and it costs roughly 170MB
    # of the RAM disk WinPE boots into. Useful only when you want a
    # PowerShell prompt inside WinPE for debugging.
    [switch]$IncludePowerShell
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "=== $Message ===" -ForegroundColor Cyan
}

function Assert-AdkTooling {
    # copype/MakeWinPEMedia/Dism must already be on PATH -- this script
    # is meant to run from an elevated "Deployment and Imaging Tools
    # Environment" prompt (installed alongside the ADK + WinPE add-on),
    # exactly as Microsoft's own documentation directs; it does not
    # attempt to install the ADK itself.
    foreach ($tool in @("copype.cmd", "MakeWinPEMedia.cmd", "Dism.exe")) {
        $found = Get-Command $tool -ErrorAction SilentlyContinue
        if (-not $found) {
            throw (
                "'$tool' was not found on PATH. Run this script from an " +
                "elevated 'Deployment and Imaging Tools Environment' " +
                "prompt (Start Menu, under Windows Kits) -- confirm the " +
                "Windows ADK and the WinPE add-on are both installed " +
                "first (learn.microsoft.com/windows-hardware/get-started/adk-install)."
            )
        }
    }
}

# ---------------------------------------------------------------------------
# Step 0: build aquila.exe if a pre-built one wasn't supplied
# ---------------------------------------------------------------------------

function Invoke-PyInstallerBuild {
    param([string]$RepoRoot)

    Write-Step "Step 0: building aquila.exe (pyinstaller Aquila.spec)"

    $specPath = Join-Path $RepoRoot "Aquila.spec"
    if (-not (Test-Path $specPath)) {
        throw "Aquila.spec not found at $specPath."
    }

    $pyinstaller = Get-Command pyinstaller -ErrorAction SilentlyContinue
    if (-not $pyinstaller) {
        throw (
            "'pyinstaller' was not found on PATH. Install the project's " +
            "dev dependencies first (from ${RepoRoot}: " +
            "'uv sync --all-extras', or 'pip install pyinstaller' inside " +
            "the project's virtual environment)."
        )
    }

    Push-Location $RepoRoot
    try {
        # Out-Host for the same reason as Mount-BootImage's DISM call:
        # this function returns $builtExe, and PyInstaller's own output
        # would otherwise be returned with it.
        & pyinstaller Aquila.spec --noconfirm | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "pyinstaller exited with code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }

    # Aquila.spec passes a.binaries/a.datas directly into EXE(...) with no
    # COLLECT(...) step -- that's PyInstaller's "onefile" mode, which places
    # the single output executable directly at dist\<name>.exe, NOT
    # dist\<name>\<name>.exe (the "onedir" layout a COLLECT(...) step would
    # produce). Confirmed empirically against a real build on 2026-09-11:
    # an earlier draft of this script assumed the onedir path and failed
    # here even though PyInstaller had actually succeeded.
    $builtExe = Join-Path $RepoRoot "dist\aquila.exe"
    if (-not (Test-Path $builtExe)) {
        throw (
            "pyinstaller reported success but $builtExe does not exist -- " +
            "check Aquila.spec's 'name' setting matches this path, and that " +
            "it is still an EXE(...)-only ('onefile') spec."
        )
    }

    return $builtExe
}

# ---------------------------------------------------------------------------
# Step 1: copype -- create the working WinPE file tree
# ---------------------------------------------------------------------------

function New-WinPEWorkingTree {
    param([string]$WorkDir, [string]$Architecture)

    Write-Step "Step 1: copype -- creating the WinPE working tree at $WorkDir"

    if (Test-Path $WorkDir) {
        Write-Host "  $WorkDir already exists -- reusing it (delete it first for a clean rebuild)."
        return
    }

    & copype.cmd $Architecture $WorkDir
    if ($LASTEXITCODE -ne 0) {
        throw "copype.cmd exited with code $LASTEXITCODE."
    }
}

# ---------------------------------------------------------------------------
# Step 2: mount boot.wim
# ---------------------------------------------------------------------------

function Mount-BootImage {
    param([string]$WorkDir)

    $bootWim = Join-Path $WorkDir "media\sources\boot.wim"
    $mountDir = Join-Path $WorkDir "mount"

    Write-Step "Step 2: mounting $bootWim to $mountDir"

    if (-not (Test-Path $mountDir)) {
        New-Item -ItemType Directory -Path $mountDir | Out-Null
    }

    # Out-Host, not bare invocation: a PowerShell function returns
    # everything written to the output stream, so DISM's banner and
    # progress bar would otherwise be returned alongside $mountDir and
    # every later /Image:/MountDir: argument would be built from that
    # array instead of the path (DISM error 87).
    Dism /Mount-Image /ImageFile:$bootWim /Index:1 /MountDir:$mountDir | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Dism /Mount-Image exited with code $LASTEXITCODE."
    }

    return $mountDir
}

# ---------------------------------------------------------------------------
# Step 3: add WinPE optional components. WinPE-WMI is the only one
# Aquila needs -- bios/ and hardware/ detection is WMI-based.
#
# An earlier revision of this script also added WinPE-NetFX,
# WinPE-Scripting and WinPE-PowerShell, on the stated grounds that
# WinPE-WMI depended on them. That is backwards: Microsoft's own
# Optional Components Reference gives the chain as
# WinPE-WMI -> WinPE-NetFX -> WinPE-Scripting -> WinPE-PowerShell,
# i.e. WinPE-WMI is the foundational package the others depend on, and
# needs none of them. aquila.exe is a self-contained native executable
# with no .NET or PowerShell runtime requirement, so all three were
# pure weight: they grew boot.wim from 324MB to 498MB, and WinPE loads
# the whole of boot.wim into a RAM disk at boot -- 173MB of RAM spent
# on nothing, which matters on exactly the older, low-memory hardware
# this project exists to repurpose.
#
# -IncludePowerShell restores the full chain for anyone who wants a
# PowerShell-capable WinPE to debug in; it is not needed to run Aquila.
# ---------------------------------------------------------------------------

function Add-RequiredOptionalComponents {
    param(
        [string]$MountDir,
        [string]$Architecture,
        [switch]$IncludeWifiSupport,
        [switch]$IncludePowerShell
    )

    Write-Step "Step 3: adding WinPE optional components"

    $ocRoot = Join-Path ${env:ProgramFiles(x86)} `
        "Windows Kits\10\Assessment and Deployment Kit\Windows Preinstallation Environment\$Architecture\WinPE_OCs"

    if (-not (Test-Path $ocRoot)) {
        throw "WinPE Optional Components folder not found at $ocRoot -- confirm the WinPE add-on is installed."
    }

    # Order matters -- each depends on the ones before it (see this
    # module's docstring; DISM enforces the dependency and will name a
    # missing prerequisite if this list is ever wrong for a given ADK
    # version).
    $components = @("WinPE-WMI")

    if ($IncludePowerShell) {
        $components += @("WinPE-NetFX", "WinPE-Scripting", "WinPE-PowerShell")
    }

    if ($IncludeWifiSupport) {
        # WinPE-WiFi-Package (netsh wlan / WLAN AutoConfig) depends on
        # WinPE-Dot3Svc per Microsoft's WinPE Optional Components
        # Reference -- added last since WMI/NetFX/Scripting above are
        # not among its prerequisites, only WiFi's own. Dev/test only
        # -- see this script's -IncludeWifiSupport parameter and
        # networking.wifi's module docstring for why this exists and
        # why it defaults off.
        $components += @("WinPE-Dot3Svc", "WinPE-WiFi-Package")
    }

    foreach ($component in $components) {
        $cab = Join-Path $ocRoot "$component.cab"
        $langCab = Join-Path $ocRoot "en-us\$component`_en-us.cab"

        Write-Host "  Adding $component"
        Dism /Image:$MountDir /Add-Package /PackagePath:$cab
        if ($LASTEXITCODE -ne 0) {
            throw "Dism /Add-Package failed for $component (exit $LASTEXITCODE)."
        }

        if (Test-Path $langCab) {
            Write-Host "  Adding $component (en-us language pack)"
            Dism /Image:$MountDir /Add-Package /PackagePath:$langCab
            if ($LASTEXITCODE -ne 0) {
                throw "Dism /Add-Package failed for $component en-us (exit $LASTEXITCODE)."
            }
        }
    }
}

# ---------------------------------------------------------------------------
# Step 3b: enlarge WinPE's writable scratch space.
#
# WinPE runs from a RAM disk whose writable portion defaults to 32MB.
# aquila.exe is a PyInstaller *onefile* build, which unpacks its bundled
# DLLs into a temp directory on that RAM disk every time it starts, so
# 32MB is nowhere near enough: the unpack runs out of room part way
# through and PyInstaller reports a decompression failure rather than a
# disk-full error, e.g.
#   [PYI-1680:ERROR] Failed to extract VCRUNTIME140.dll:
#   decompression resulted in return code -3!
# which is what a real boot on a Dell Inspiron 5558 produced.
#
# 512MB is DISM's maximum and costs only RAM on the target machine.
# ---------------------------------------------------------------------------

function Set-ScratchSpace {
    param([string]$MountDir, [int]$SizeMB = 512)

    Write-Step "Step 3b: setting WinPE scratch space to ${SizeMB}MB"

    Dism /Image:$MountDir /Set-ScratchSpace:$SizeMB | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Dism /Set-ScratchSpace exited with code $LASTEXITCODE."
    }
}

# ---------------------------------------------------------------------------
# Step 4: driver injection (optional) -- network/storage drivers a target
# machine's chipset needs that WinPE's own inbox driver set doesn't cover.
# Left as an explicit, opt-in step: most modern hardware needs nothing
# extra, and silently injecting a directory of unvetted drivers into every
# build is exactly the kind of unreviewed action GP-001 warns against.
# ---------------------------------------------------------------------------

function Add-Drivers {
    param([string]$MountDir, [string]$DriversDir)

    if (-not $DriversDir) {
        Write-Host "  (no -DriversDir given -- skipping driver injection)"
        return
    }

    Write-Step "Step 4: injecting drivers from $DriversDir"
    Dism /Image:$MountDir /Add-Driver /Driver:$DriversDir /Recurse
    if ($LASTEXITCODE -ne 0) {
        throw "Dism /Add-Driver exited with code $LASTEXITCODE."
    }
}

# ---------------------------------------------------------------------------
# Step 5: install aquila.exe + configs/ -- phase1/, matching
# common.media's expected layout (<media_root>/phase1/..., see
# common/constants/deployment.py). See this script's own docstring for
# why this no longer bundles a raw Python interpreter.
# ---------------------------------------------------------------------------

function Install-AquilaPayload {
    param(
        [string]$MountDir,
        [string]$RepoRoot,
        [string]$AquilaExePath
    )

    Write-Step "Step 5: installing aquila.exe + configs/"

    $aquilaRoot = Join-Path $MountDir "Aquila"
    $phase1Root = Join-Path $aquilaRoot "phase1"
    $phase2Root = Join-Path $aquilaRoot "phase2"

    foreach ($dir in @($aquilaRoot, $phase1Root, $phase2Root)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    # 5a. aquila.exe itself -- a single self-contained executable, no
    # separate Python runtime or dependency tree to place alongside it.
    Write-Host "  Copying $AquilaExePath"
    Copy-Item -Path $AquilaExePath -Destination (Join-Path $phase1Root "aquila.exe") -Force

    # 5b. configs/*.yaml -- kept as loose, operator-editable files next
    # to the executable rather than baked into the PyInstaller archive
    # (GP-003, REQ-CONF-002: configuration external to application
    # logic -- a technician can edit these directly on the mounted USB
    # without rebuilding aquila.exe at all).
    Write-Host "  Copying configs/"
    # Remove first: Copy-Item -Recurse onto an *existing* directory copies
    # the source folder inside it rather than over it, so re-running this
    # build against a reused -WorkDir would leave configs\configs\ (and
    # configs\configs\configs\ on the run after that).
    $configsDest = Join-Path $phase1Root "configs"
    if (Test-Path $configsDest) {
        Remove-Item $configsDest -Recurse -Force
    }
    Copy-Item -Path (Join-Path $RepoRoot "configs") -Destination $configsDest -Recurse -Force

    # 5c. Startnet.cmd -- WinPE's own startup script. wpeinit first
    # (Plug and Play/networking bring-up -- see Microsoft's own
    # "Wpeinit and Startnet.cmd" documentation), then Aquila's autorun.
    $startnetPath = Join-Path $MountDir "Windows\System32\Startnet.cmd"
    $startnetContent = @"
wpeinit
set AQUILA_MEDIA_ROOT=X:\Aquila
X:\Aquila\phase1\aquila.exe autorun
"@
    Set-Content -Path $startnetPath -Value $startnetContent -Encoding ASCII

    return @{ Phase1Root = $phase1Root; Phase2Root = $phase2Root }
}

# ---------------------------------------------------------------------------
# Step 6: unmount and commit
# ---------------------------------------------------------------------------

function Dismount-BootImage {
    param([string]$MountDir)

    Write-Step "Step 6: committing changes and unmounting $MountDir"
    Dism /Unmount-Image /MountDir:$MountDir /Commit
    if ($LASTEXITCODE -ne 0) {
        throw "Dism /Unmount-Image exited with code $LASTEXITCODE."
    }
}

# ---------------------------------------------------------------------------
# Step 6b: optionally erase the USB's whole partition table first
# ---------------------------------------------------------------------------

function Clear-UsbDisk {
    param([string]$UsbDriveLetter)

    Write-Step "Step 6b: erasing all partitions on the disk behind $UsbDriveLetter`:"

    $partition = Get-Partition -DriveLetter $UsbDriveLetter -ErrorAction Stop
    $disk = Get-Disk -Number $partition.DiskNumber -ErrorAction Stop

    # Refuse anything that is not an unremarkable USB stick. -CleanUsbDisk
    # destroys every partition on the disk, not just the named volume, so
    # a wrong drive letter here would be unrecoverable -- these three
    # checks are what stand between a typo and someone's system disk.
    if ($disk.BusType -ne "USB") {
        throw (
            "Refusing to clean disk $($disk.Number) ('$($disk.FriendlyName)'): " +
            "its bus type is '$($disk.BusType)', not USB. -CleanUsbDisk only " +
            "operates on USB media."
        )
    }
    if ($disk.IsSystem -or $disk.IsBoot) {
        throw (
            "Refusing to clean disk $($disk.Number) ('$($disk.FriendlyName)'): " +
            "it is the system and/or boot disk."
        )
    }

    Write-Host ("  Disk {0}: '{1}', {2:N1} GB, {3}" -f `
        $disk.Number, $disk.FriendlyName, ($disk.Size / 1GB), $disk.PartitionStyle)
    foreach ($existing in (Get-Partition -DiskNumber $disk.Number -ErrorAction SilentlyContinue)) {
        Write-Host ("    partition {0}: {1}{2:N0} MB" -f `
            $existing.PartitionNumber,
            $(if ($existing.DriveLetter) { "$($existing.DriveLetter): " } else { "" }),
            ($existing.Size / 1MB))
    }
    Write-Warning "Every partition listed above is about to be erased."

    # diskpart rather than Clear-Disk/New-Partition/Format-Volume:
    # Format-Volume refuses to create FAT32 above 32GB, while diskpart's
    # own "format fs=fat32 quick" does not -- and diskpart is already
    # this toolchain's formatting path (MakeWinPEMedia /UFD shells out
    # to it too).
    $script = Join-Path $env:TEMP "AquilaCleanUsbDisk.txt"
    @(
        "select disk $($disk.Number)"
        "clean"
        "create partition primary"
        "active"
        "format fs=fat32 quick label=`"AQUILA`""
        "assign letter=$UsbDriveLetter"
    ) | Set-Content -Path $script -Encoding ASCII

    try {
        & diskpart.exe /s $script | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "diskpart exited with code $LASTEXITCODE."
        }
    }
    finally {
        Remove-Item $script -Force -ErrorAction SilentlyContinue
    }

    # Windows needs a moment to surface the newly assigned letter before
    # MakeWinPEMedia's own "select volume=" can find it.
    Start-Sleep -Seconds 3
}

# ---------------------------------------------------------------------------
# Step 7: write bootable media to the USB drive
# ---------------------------------------------------------------------------

function Write-UsbMedia {
    param([string]$WorkDir, [string]$UsbDriveLetter, [switch]$DiskAlreadyCleaned)

    Write-Step "Step 7: writing bootable media to $UsbDriveLetter`:"

    if ($DiskAlreadyCleaned) {
        # /f (skip MakeWinPEMedia's own prompt) is used *only* on the
        # -CleanUsbDisk path. That is not a shortcut past an operator
        # decision: -CleanUsbDisk is itself an explicit opt-in to
        # destroying this entire disk, already confirmed and already
        # carried out in Step 6b, so the disk MakeWinPEMedia is about to
        # format is one the operator knowingly erased moments ago. Asking
        # again about a volume this script just created would be asking
        # about data that no longer exists. Without /f the prompt is also
        # unanswerable in practice here: diskpart consumes stdin, so a
        # queued answer never reaches `choice`.
        & MakeWinPEMedia.cmd /UFD /f $WorkDir "$UsbDriveLetter`:"
    }
    else {
        Write-Warning (
            "MakeWinPEMedia /UFD reformats $UsbDriveLetter`: -- confirm this " +
            "is the correct drive before continuing. This script does NOT " +
            "auto-confirm; it lets MakeWinPEMedia's own interactive prompt " +
            "stand (GP-001: no scripted shortcut past a destructive " +
            "confirmation)."
        )
        & MakeWinPEMedia.cmd /UFD $WorkDir "$UsbDriveLetter`:"
    }

    if ($LASTEXITCODE -ne 0) {
        throw "MakeWinPEMedia.cmd exited with code $LASTEXITCODE."
    }

    # Exit code 0 is not proof the media was written: declining
    # MakeWinPEMedia's format prompt ("UFD X: will not be formatted;
    # exiting.") also exits 0, which previously let this script report
    # "Deployment USB written" for a drive it had not touched. Verify
    # the boot files are actually present instead of trusting the code.
    foreach ($required in @("bootmgr", "sources\boot.wim", "EFI\BOOT\bootx64.efi")) {
        $path = Join-Path "$UsbDriveLetter`:" $required
        if (-not (Test-Path $path)) {
            throw (
                "MakeWinPEMedia reported success but $path is missing -- the " +
                "media was not written. If it printed 'will not be formatted', " +
                "its format confirmation was declined or could not be answered."
            )
        }
    }
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

Assert-AdkTooling

if (-not $AquilaExePath) {
    $AquilaExePath = Invoke-PyInstallerBuild -RepoRoot $RepoRoot
}
elseif (-not (Test-Path $AquilaExePath -PathType Leaf)) {
    throw "-AquilaExePath '$AquilaExePath' does not exist."
}

New-WinPEWorkingTree -WorkDir $WorkDir -Architecture $Architecture
$mountDir = Mount-BootImage -WorkDir $WorkDir

try {
    Add-RequiredOptionalComponents `
        -MountDir $mountDir `
        -Architecture $Architecture `
        -IncludeWifiSupport:$IncludeWifiSupport `
        -IncludePowerShell:$IncludePowerShell
    Set-ScratchSpace -MountDir $mountDir
    Add-Drivers -MountDir $mountDir -DriversDir $DriversDir
    Install-AquilaPayload `
        -MountDir $mountDir `
        -RepoRoot $RepoRoot `
        -AquilaExePath $AquilaExePath | Out-Null
}
finally {
    # Commit-on-success, but still unmount (without /Commit would also
    # work, but /Commit here means a failure partway through Step 5
    # doesn't silently discard everything Step 3 already added -- rerun
    # from a clean $WorkDir if a step fails and needs a fresh start).
    Dismount-BootImage -MountDir $mountDir
}

if ($CleanUsbDisk) {
    Clear-UsbDisk -UsbDriveLetter $UsbDriveLetter
}

Write-UsbMedia -WorkDir $WorkDir -UsbDriveLetter $UsbDriveLetter -DiskAlreadyCleaned:$CleanUsbDisk

Write-Step "Done"
Write-Host "Deployment USB written to $UsbDriveLetter`:. Boot a target machine from it to test."
