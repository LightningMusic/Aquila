"""
Project Aquila
=============

Power Management, Lid Behavior, and Power-Recovery Configuration

Implements REQ-BOOT-007 (general OS power management), REQ-BOOT-008
(lid behavior), and REQ-BOOT-011 (firmware/BMC power-restore policy),
plus REQ-BOOT-010's non-fatal-when-unsupported principle as GP-008
generalizes it to every hardware-configuration requirement in this
group, not just battery thresholds.

Runs entirely within Phase Two (the freshly-installed Linux node), so
these use standard Debian/systemd/IPMI tooling, not the WMI-based
approach ``bios/`` uses on the WinPE side.

Research basis (this session, primary sources):

* ``systemctl mask`` on ``sleep.target``/``suspend.target``/
  ``hibernate.target``/``hybrid-sleep.target`` is systemd's own
  documented mechanism for unconditionally disabling all suspend/
  hibernate entry points system-wide -- standard practice on
  always-on servers, not an Aquila invention.
* ``HandleLidSwitch=ignore`` (systemd-logind.conf) is confirmed via
  systemd's own logind.conf documentation: "If ignore, logind will
  never handle these keys." A drop-in file under
  ``/etc/systemd/logind.conf.d/`` is used instead of editing
  ``logind.conf`` directly, so this doesn't clobber any other
  administrator-set option in the main file (systemd's own supported
  drop-in-merge mechanism).
* ``ipmitool chassis policy always-on|previous|always-off`` is
  confirmed via the openbmc/ipmitool project's own documentation as
  the standard command for reading/setting a BMC's AC-power-restore
  policy.

REQ-BOOT-011's honest capability gap: most of Aquila's target hardware
(SRS 1.2: "surplus and commodity hardware... home lab operators") has
no BMC/IPMI interface at all -- laptops and consumer desktops simply
don't ship one. This is the expected, common case, not a failure:
``PowerRecoveryConfigurator`` detects IPMI support first and honestly
reports "unsupported" rather than raising, exactly mirroring
``preparation.sanitizer``'s ATA/NVMe Secure Erase capability-detection
pattern.

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import Protocol

from common.constants.logging import BOOTSTRAP_LOGGER
from common.exceptions.deployment import DeploymentConfigurationError

logger = logging.getLogger(BOOTSTRAP_LOGGER)

#: systemd targets that, together, cover every suspend/hibernate
#: entry point (manual, lid-triggered, idle-triggered, and ACPI-
#: button-triggered all route through one of these).
_SLEEP_TARGETS = (
    "sleep.target",
    "suspend.target",
    "hibernate.target",
    "hybrid-sleep.target",
)

_LOGIND_DROPIN_FILENAME = "50-aquila-lid.conf"

#: Devices that indicate a local in-band IPMI/BMC interface is
#: present. Checked before ever invoking ipmitool, so an absent BMC
#: is detected cheaply and honestly rather than via a failed command.
_IPMI_DEVICE_CANDIDATES = (
    Path("/dev/ipmi0"),
    Path("/dev/ipmi/0"),
    Path("/dev/ipmidev/0"),
)


class CommandRunner(Protocol):
    """Runs a command and returns its completed process."""

    def __call__(
        self, args: list[str]
    ) -> subprocess.CompletedProcess[str]: ...


def _default_command_runner(
    args: list[str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        check=False,
    )


@dataclass(slots=True, frozen=True)
class SleepTargetResult:
    """Outcome of REQ-BOOT-007's sleep-target masking."""

    masked_targets: tuple[str, ...]
    detail: str


class SleepTargetManager:
    """
    Masks systemd's sleep/suspend/hibernate targets (REQ-BOOT-007).

    Masking (as opposed to merely disabling) links each target unit
    to ``/dev/null``, which prevents it from being started even as a
    dependency of some other unit -- the strongest, standard systemd
    guarantee available short of physically removing suspend support.
    """

    def __init__(
        self, *, command_runner: CommandRunner | None = None
    ) -> None:
        self._run = command_runner or _default_command_runner

    def mask_all(
        self, targets: tuple[str, ...] = _SLEEP_TARGETS
    ) -> SleepTargetResult:
        result = self._run(["systemctl", "mask", *targets])
        if result.returncode != 0:
            detail = (
                f"'systemctl mask {' '.join(targets)}' failed "
                f"(exit {result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
            logger.error(detail)
            raise DeploymentConfigurationError(detail)

        detail = f"Masked {len(targets)} sleep/suspend target(s)."
        logger.info(detail)
        return SleepTargetResult(
            masked_targets=targets, detail=detail
        )


@dataclass(slots=True, frozen=True)
class LidBehaviorResult:
    """Outcome of REQ-BOOT-008's lid-behavior configuration."""

    lid_action: str
    applied: bool
    detail: str


class LidBehaviorConfigurator:
    """
    Configures systemd-logind's lid-switch action (REQ-BOOT-008) via
    a drop-in file, then reloads systemd-logind so the change takes
    effect without a reboot.
    """

    def __init__(
        self,
        *,
        dropin_directory: Path | None = None,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self._dropin_directory = dropin_directory or Path(
            "/etc/systemd/logind.conf.d"
        )
        self._run = command_runner or _default_command_runner

    def configure(self, lid_action: str) -> LidBehaviorResult:
        dropin_path = self._dropin_directory / _LOGIND_DROPIN_FILENAME

        content = (
            "# Managed by Project Aquila Bootstrap Engine "
            "(REQ-BOOT-008)\n"
            "[Login]\n"
            f"HandleLidSwitch={lid_action}\n"
            f"HandleLidSwitchExternalPower={lid_action}\n"
            f"HandleLidSwitchDocked={lid_action}\n"
        )

        try:
            self._dropin_directory.mkdir(parents=True, exist_ok=True)
            dropin_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise DeploymentConfigurationError(
                f"Could not write {dropin_path}: {exc}"
            ) from exc

        result = self._run(
            ["systemctl", "restart", "systemd-logind"]
        )
        if result.returncode != 0:
            detail = (
                "'systemctl restart systemd-logind' failed (exit "
                f"{result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
            logger.error(detail)
            raise DeploymentConfigurationError(detail)

        detail = f"Lid-switch action set to '{lid_action}'."
        logger.info(detail)
        return LidBehaviorResult(
            lid_action=lid_action, applied=True, detail=detail
        )


@dataclass(slots=True, frozen=True)
class PowerRecoveryResult:
    """Outcome of REQ-BOOT-011's power-recovery-policy attempt."""

    supported: bool
    applied: bool
    policy: str
    detail: str


class PowerRecoveryConfigurator:
    """
    Configures the firmware/BMC's AC-power-restore policy
    (REQ-BOOT-011) when a local IPMI/BMC interface is present.

    Absent on most laptops/desktops -- see this module's docstring.
    Never raises for "no BMC present"; that's REQ-BOOT-010's
    non-fatal-when-unsupported principle, generalized per GP-008.
    """

    def __init__(
        self,
        *,
        command_runner: CommandRunner | None = None,
        ipmi_device_candidates: tuple[Path, ...] = (
            _IPMI_DEVICE_CANDIDATES
        ),
        ipmitool_path: str | None = None,
    ) -> None:
        self._run = command_runner or _default_command_runner
        self._ipmi_device_candidates = ipmi_device_candidates
        self._ipmitool_path = ipmitool_path

    def _ipmitool_available(self) -> bool:
        if self._ipmitool_path is not None:
            return True
        return which("ipmitool") is not None

    def _bmc_present(self) -> bool:
        return any(
            device.exists() for device in self._ipmi_device_candidates
        )

    def configure(self, policy: str) -> PowerRecoveryResult:
        if not self._ipmitool_available():
            detail = (
                "ipmitool is not installed -- power-recovery policy "
                "was not configured. This is expected on hardware "
                "without a BMC; deployment continues (REQ-BOOT-010)."
            )
            logger.info(detail)
            return PowerRecoveryResult(
                supported=False,
                applied=False,
                policy=policy,
                detail=detail,
            )

        if not self._bmc_present():
            detail = (
                "No local IPMI/BMC device was detected -- power-"
                "recovery policy was not configured. This is "
                "expected on commodity laptops/desktops; deployment "
                "continues (REQ-BOOT-010)."
            )
            logger.info(detail)
            return PowerRecoveryResult(
                supported=False,
                applied=False,
                policy=policy,
                detail=detail,
            )

        tool = self._ipmitool_path or "ipmitool"
        result = self._run([tool, "chassis", "policy", policy])

        if result.returncode != 0:
            detail = (
                f"'ipmitool chassis policy {policy}' failed (exit "
                f"{result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()} "
                "-- a BMC was detected but the policy could not be "
                "applied; deployment continues (REQ-BOOT-010)."
            )
            logger.warning(detail)
            return PowerRecoveryResult(
                supported=True,
                applied=False,
                policy=policy,
                detail=detail,
            )

        detail = f"Power-recovery policy set to '{policy}'."
        logger.info(detail)
        return PowerRecoveryResult(
            supported=True, applied=True, policy=policy, detail=detail
        )


__all__ = [
    "CommandRunner",
    "LidBehaviorConfigurator",
    "LidBehaviorResult",
    "PowerRecoveryConfigurator",
    "PowerRecoveryResult",
    "SleepTargetManager",
    "SleepTargetResult",
]
