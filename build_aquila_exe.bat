@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Project Aquila - Build aquila.exe
cd /d "%~dp0"

rem ============================================================================
rem Project Aquila -- aquila.exe build script
rem ============================================================================
rem
rem Builds the single self-contained aquila.exe (PyInstaller, see Aquila.spec
rem at the repository root) from source. This is the executable that runs on
rem the deployment USB (installed there by build_deployment_usb.bat) and can
rem also be run directly on an ordinary Windows desktop to try the Technician
rem Console GUI or the CLI without building a USB at all -- see README.md.
rem
rem What this script does, in order:
rem   1. Looks for "uv" (https://docs.astral.sh/uv/) and prefers it if found,
rem      since that's what this project's pyproject.toml is written for.
rem      Otherwise falls back to a plain Python virtual environment ("pip").
rem   2. Installs the project's dependencies, including PyInstaller (the
rem      "dev" extra in pyproject.toml).
rem   3. Runs PyInstaller against Aquila.spec.
rem   4. Reports exactly where the finished aquila.exe landed.
rem
rem Run this by double-clicking it from inside the Project Aquila repository
rem (the same folder as pyproject.toml and Aquila.spec). No administrator
rem rights are needed for this step -- only build_deployment_usb.bat (the
rem next step, which writes the USB) needs to run elevated.
rem ============================================================================

echo.
echo ============================================================
echo  Project Aquila -- Build aquila.exe
echo  Repository: %CD%
echo ============================================================
echo.

if exist "Aquila.spec" goto :have_spec
echo [ERROR] Aquila.spec was not found in %CD%.
echo         Run this script from inside the Project Aquila repository root.
goto :fail

:have_spec

rem ----------------------------------------------------------------------
rem Step 1: pick a dependency-install strategy -- uv, or venv + pip.
rem ----------------------------------------------------------------------

where uv >nul 2>&1
if errorlevel 1 goto :no_uv

echo [1/3] uv found on PATH. Installing dependencies with "uv sync --all-extras" ...
uv sync --all-extras
if errorlevel 1 (
    echo [ERROR] "uv sync --all-extras" failed. See the output above.
    goto :fail
)
set "PYINSTALLER_CMD=uv run pyinstaller"
goto :run_pyinstaller

:no_uv
echo [1/3] uv was not found on PATH. Falling back to a plain virtual environment + pip.

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
echo         Install Python 3.11 or newer from https://www.python.org/downloads/
echo         (or install uv from https://docs.astral.sh/uv/), then re-run this script.
goto :fail

:have_python
if exist ".venv\Scripts\python.exe" goto :venv_ready
echo       Creating a virtual environment at .venv ...
%PYTHON_CMD% -m venv .venv
if errorlevel 1 (
    echo [ERROR] Failed to create the virtual environment with "%PYTHON_CMD% -m venv .venv".
    goto :fail
)

:venv_ready
echo [2/3] Installing project dependencies into .venv (base requirements plus
echo       the "dev" extra, which includes PyInstaller) ...
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip setuptools wheel >nul
pip install -e ".[dev]"
if errorlevel 1 (
    echo [ERROR] "pip install -e .[dev]" failed. See the output above.
    goto :fail
)
set "PYINSTALLER_CMD=pyinstaller"

:run_pyinstaller
echo.
echo [3/3] Running PyInstaller against Aquila.spec ...
%PYINSTALLER_CMD% Aquila.spec --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller failed. See the output above.
    goto :fail
)

if not exist "dist\aquila.exe" (
    echo [ERROR] PyInstaller reported success, but dist\aquila.exe does not exist.
    echo         Check that Aquila.spec's "name" setting is still "aquila", and that
    echo         Aquila.spec is still an EXE^(...^)-only ^("onefile"^) spec -- if a COLLECT^(...^)
    echo         step is ever added, the output moves to dist\aquila\aquila.exe instead.
    goto :fail
)

echo.
echo ============================================================
echo  Done. aquila.exe was built at:
echo    %CD%\dist\aquila.exe
echo.
echo  Next step: to put this onto a bootable deployment USB, run
echo  build_deployment_usb.bat from a machine with the Windows ADK
echo  + WinPE add-on installed -- see README.md.
echo ============================================================
echo.
explorer /select,"%CD%\dist\aquila.exe" >nul 2>&1
endlocal
pause
exit /b 0

:fail
echo.
echo Build did not complete. See the [ERROR] message above for what to fix.
echo.
endlocal
pause
exit /b 1
