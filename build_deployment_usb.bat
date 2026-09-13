@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Project Aquila - Build Deployment USB
cd /d "%~dp0"

rem ============================================================================
rem Project Aquila -- Deployment USB builder (batch front end)
rem ============================================================================
rem
rem The single one-click entry point for turning this repository into a
rem bootable Aquila deployment USB. It is a convenience wrapper around
rem scripts\build_deployment_usb.ps1 (which does the real work -- see that
rem file's own header comment for the full technical explanation) that:
rem
rem   1. Requests administrator rights automatically (the underlying build
rem      steps -- mounting a WIM, adding Windows packages, writing a USB --
rem      all require them).
rem   2. Tries to load the Windows ADK's own command environment (so
rem      copype.cmd / Dism.exe / MakeWinPEMedia.cmd are on PATH) if the ADK
rem      is installed at its default location. If it isn't, this script
rem      says so plainly and tells you how to run it from the Start Menu's
rem      "Deployment and Imaging Tools Environment" shortcut instead.
rem   3. Installs this project's Python dependencies (including PyInstaller)
rem      the same way build_aquila_exe.bat does, so aquila.exe can be built
rem      from source automatically if you don't already have one built.
rem   4. Asks, in plain language, which USB drive to write to -- and
rem      requires you to type "YES" before anything destructive happens.
rem      (MakeWinPEMedia will still ask its own confirmation on top of this
rem      -- this project never scripts past a destructive confirmation.)
rem   5. Runs scripts\build_deployment_usb.ps1 with those answers.
rem
rem Requirements on THIS machine, before running this script:
rem   - The Windows ADK, with the WinPE add-on, installed
rem     (https://learn.microsoft.com/windows-hardware/get-started/adk-install)
rem   - Python 3.11+ (https://www.python.org/downloads/) or uv
rem     (https://docs.astral.sh/uv/)
rem   - A USB drive already partitioned and formatted as a WinPE boot
rem     partition (FAT32) -- see Microsoft's "Create bootable Windows PE
rem     media" documentation. This script does not partition a drive for
rem     you; that step is destructive and, per this project's own safety
rem     principle (GP-001), is left as an explicit, separate, un-scriptable
rem     action you take with your eyes open.
rem
rem Run this by double-clicking it. It will ask Windows for administrator
rem rights itself (you'll see a UAC prompt) -- you do not need to right-click
rem "Run as administrator" yourself, though doing so also works.
rem ============================================================================

echo.
echo ============================================================
echo  Project Aquila -- Deployment USB Builder
echo ============================================================
echo.
echo  This turns the repository at:
echo    %CD%
echo  into a bootable WinPE deployment USB: it builds aquila.exe
echo  from source if needed, assembles a WinPE image around it,
echo  and writes that image onto a USB drive you choose below.
echo.

rem ----------------------------------------------------------------------
rem Step 0: elevate if not already running as Administrator.
rem ----------------------------------------------------------------------

net session >nul 2>&1
if not errorlevel 1 goto :is_admin

echo This needs administrator rights. Requesting them now --
echo accept the prompt that appears (a new window will open here).
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs"
exit /b 0

:is_admin

rem ----------------------------------------------------------------------
rem Step 1: try to load the Windows ADK's own command environment. This
rem is a best-effort convenience only -- if the ADK is installed
rem somewhere other than the default location, Step 4 below will report
rem a clear, specific error naming exactly which tool it could not find.
rem ----------------------------------------------------------------------

echo [1/4] Looking for the Windows ADK command environment ...
set "ADK_ENV_SCRIPT=%ProgramFiles(x86)%\Windows Kits\10\Assessment and Deployment Kit\Deployment Tools\DandISetEnv.bat"
if exist "%ADK_ENV_SCRIPT%" (
    echo       Found it -- loading %ADK_ENV_SCRIPT%
    call "%ADK_ENV_SCRIPT%"
) else (
    echo       Not found at the default install location.
    echo       If Step 4 below fails saying copype/Dism/MakeWinPEMedia
    echo       were not found, close this window and instead run this
    echo       script from the Start Menu's "Deployment and Imaging
    echo       Tools Environment" shortcut ^(under Windows Kits^), which
    echo       sets this up correctly no matter where the ADK is installed.
)

rem ----------------------------------------------------------------------
rem Step 2: make sure this project's Python dependencies (PyInstaller
rem included) are installed -- the same logic as build_aquila_exe.bat.
rem ----------------------------------------------------------------------

echo.
echo [2/4] Preparing Python dependencies ...

where uv >nul 2>&1
if errorlevel 1 goto :no_uv

uv sync --all-extras
if errorlevel 1 (
    echo [ERROR] "uv sync --all-extras" failed. See the output above.
    goto :fail
)
goto :deps_ready

:no_uv
where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
    goto :have_python
)
where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto :have_python
)
echo [ERROR] No Python interpreter was found on PATH.
echo         Install Python 3.11+ from https://www.python.org/downloads/
echo         (or install uv from https://docs.astral.sh/uv/), then re-run this script.
goto :fail

:have_python
if exist ".venv\Scripts\python.exe" goto :venv_ready
echo       Creating a virtual environment at .venv ...
%PYTHON_CMD% -m venv .venv
if errorlevel 1 (
    echo [ERROR] Failed to create the virtual environment.
    goto :fail
)

:venv_ready
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip setuptools wheel >nul
pip install -e ".[dev]"
if errorlevel 1 (
    echo [ERROR] "pip install -e .[dev]" failed. See the output above.
    goto :fail
)

:deps_ready
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

rem ----------------------------------------------------------------------
rem Step 3: ask what to build onto, with an explicit typed confirmation
rem before anything destructive happens (GP-001 -- see the SRS).
rem ----------------------------------------------------------------------

echo.
echo [3/4] Where to build:
echo.
set "WORKDIR=C:\AquilaBuild\WinPE"
set /p "WORKDIR=  WinPE working folder [default: %WORKDIR%]: "

set "USBLETTER="
:ask_drive
set /p "USBLETTER=  USB drive letter to write to (just the letter, for example E, then press Enter): "
if "%USBLETTER%"=="" goto :ask_drive
if "%USBLETTER:~-1%"==":" set "USBLETTER=%USBLETTER:~0,-1%"

echo.
echo ############################################################
echo  About to ERASE AND REFORMAT drive %USBLETTER%:
echo  WinPE working folder: %WORKDIR%
echo ############################################################
echo.
set "CONFIRM="
set /p "CONFIRM=  Type YES (all capitals) to continue, or anything else to cancel: "
if not "%CONFIRM%"=="YES" (
    echo Cancelled. Nothing was written.
    goto :fail
)

rem ----------------------------------------------------------------------
rem Step 4: hand off to the real build script.
rem ----------------------------------------------------------------------

echo.
echo [4/4] Running scripts\build_deployment_usb.ps1 ...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_deployment_usb.ps1" -WorkDir "%WORKDIR%" -UsbDriveLetter "%USBLETTER%"
if errorlevel 1 (
    echo.
    echo [ERROR] The build script reported a failure -- see the PowerShell
    echo         output above for exactly which step failed.
    goto :fail
)

echo.
echo ============================================================
echo  Done. Drive %USBLETTER%: is now a bootable Aquila deployment USB.
echo  Boot a target machine from it to run Aquila.
echo ============================================================
echo.
endlocal
pause
exit /b 0

:fail
echo.
endlocal
pause
exit /b 1
