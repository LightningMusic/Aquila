"""
Project Aquila
=============

Functional tests for ``cli.autorun`` -- the deployment media's
unattended-boot entry point.

Scope note, matching this repository's own established convention
(``run_tests_cli.py`` for ``cmd_retire``/``cmd_provision``,
``run_tests_technician_console.py`` for ``MainWindow``): this suite
covers every pure decision function directly (``parse_device_selection``,
the recovery-decision and confirmation-provider builders, via
dependency-injected fakes for ``VolumeBrowser``/``StorageDevice``/
``PreparationConfirmationRequest`` and a scripted ``input_fn``) and
:func:`cli.autorun.run_autorun`'s own top-level exception-to-exit-code
mapping (via a monkeypatched ``build_context``). It does not run
``_run_autorun_body`` end-to-end against a real ``WorkflowManager`` --
that would need real hardware-backed ``InspectionWorkflowStage``
detection unavailable in this Linux development container, the same
boundary every other subsystem's own test suite already respects.

Run with:
    python tests/run_tests_cli_autorun.py  (run from the repository root)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import cli.autorun as autorun  # noqa: E402
from cli.commands import CliUsageError  # noqa: E402
from common.constants.deployment import (  # noqa: E402
    DEPLOYMENT_CANCELLED,
    DEPLOYMENT_ERROR,
    FORCE_CONFIRMATION_PHRASE,
)
from common.exceptions.application import AquilaCancelledError  # noqa: E402

failures: list[str] = []


def check(condition: bool, description: str) -> None:
    if not condition:
        failures.append(description)
        print(f"FAIL: {description}")
    else:
        print(f"PASS: {description}")


def check_raises(exc_type, callable_, description: str) -> None:
    try:
        callable_()
    except exc_type:
        check(True, description)
        return
    except Exception as exc:  # noqa: BLE001
        check(False, f"{description} (raised {type(exc).__name__} instead of {exc_type.__name__})")
        return
    check(False, f"{description} (did not raise)")


def _scripted_input(*answers: str):
    remaining = list(answers)

    def _input(_prompt: str) -> str:
        if not remaining:
            raise AssertionError("scripted input exhausted -- test scripted too few answers")
        return remaining.pop(0)

    return _input


# ---------------------------------------------------------------------------
# parse_device_selection
# ---------------------------------------------------------------------------


def test_parse_device_selection() -> None:
    check(autorun.parse_device_selection("1", 3) == [0], "'1' selects index 0")
    check(autorun.parse_device_selection("1,3", 3) == [0, 2], "'1,3' selects indices 0 and 2")
    check(autorun.parse_device_selection(" 2 , 2 ", 3) == [1], "duplicate selections are de-duplicated")
    check(autorun.parse_device_selection("all", 4) == [0, 1, 2, 3], "'all' selects every index")
    check(autorun.parse_device_selection("ALL", 2) == [0, 1], "'all' is case-insensitive")
    check_raises(CliUsageError, lambda: autorun.parse_device_selection("", 3), "empty selection raises CliUsageError")
    check_raises(CliUsageError, lambda: autorun.parse_device_selection("0", 3), "'0' (out of range) raises CliUsageError")
    check_raises(CliUsageError, lambda: autorun.parse_device_selection("4", 3), "out-of-range number raises CliUsageError")
    check_raises(CliUsageError, lambda: autorun.parse_device_selection("x", 3), "non-numeric token raises CliUsageError")


# ---------------------------------------------------------------------------
# Fakes -- minimal stand-ins matching only the attributes autorun.py touches
# ---------------------------------------------------------------------------


class _FakeVolume:
    def __init__(self, device_id: str, root_path: Path):
        self.device_id = device_id
        self.root_path = root_path


class _FakeEntry:
    def __init__(self, relative_path: str, *, is_directory: bool, readable: bool = True):
        self.relative_path = relative_path
        self.is_directory = is_directory
        self.readable = readable


class _FakeBrowser:
    """Serves a fixed, flat file list for any volume it's asked to browse."""

    def __init__(self, files: List[str]):
        self._files = files

    def browse(self, _volume, relative_path: str = ""):
        if relative_path:
            return []
        return [_FakeEntry(name, is_directory=False) for name in self._files]


# ---------------------------------------------------------------------------
# build_recovery_decision_interactively
# ---------------------------------------------------------------------------


def test_recovery_no_volumes_auto_skips() -> None:
    decision = autorun.build_recovery_decision_interactively(
        _scripted_input(), _FakeBrowser([]), []
    )
    check(decision is not None, "no discovered volumes skips recovery without prompting")


def test_recovery_skip_requires_exact_phrase() -> None:
    volumes = [_FakeVolume("D:", Path("/mnt/d"))]
    check_raises(
        AquilaCancelledError,
        lambda: autorun.build_recovery_decision_interactively(
            _scripted_input("n", "not the phrase"), _FakeBrowser(["a.txt"]), volumes
        ),
        "skipping recovery with the wrong phrase raises AquilaCancelledError",
    )


def test_recovery_skip_with_correct_phrase() -> None:
    volumes = [_FakeVolume("D:", Path("/mnt/d"))]
    decision = autorun.build_recovery_decision_interactively(
        _scripted_input("n", FORCE_CONFIRMATION_PHRASE),
        _FakeBrowser(["a.txt"]),
        volumes,
    )
    check(decision is not None, "skipping recovery with the correct phrase returns a decision")


def test_recovery_recover_all() -> None:
    volumes = [_FakeVolume("D:", Path("/mnt/d")), _FakeVolume("E:", Path("/mnt/e"))]
    decision = autorun.build_recovery_decision_interactively(
        _scripted_input("y", "all", "/mnt/backup"),
        _FakeBrowser(["a.txt", "b.txt"]),
        volumes,
    )
    check(decision is not None, "recovering 'all' volumes returns a decision")


def test_recovery_recover_no_readable_files() -> None:
    volumes = [_FakeVolume("D:", Path("/mnt/d"))]
    check_raises(
        CliUsageError,
        lambda: autorun.build_recovery_decision_interactively(
            _scripted_input("y", "all", "/mnt/backup"),
            _FakeBrowser([]),  # no files at all
            volumes,
        ),
        "recovering volumes with no readable files raises CliUsageError",
    )


def test_recovery_empty_destination_rejected() -> None:
    volumes = [_FakeVolume("D:", Path("/mnt/d"))]
    check_raises(
        CliUsageError,
        lambda: autorun.build_recovery_decision_interactively(
            _scripted_input("y", "all", ""),
            _FakeBrowser(["a.txt"]),
            volumes,
        ),
        "an empty recovery destination raises CliUsageError",
    )


# ---------------------------------------------------------------------------
# build_confirmation_provider_interactively
# ---------------------------------------------------------------------------


class _FakeConfirmationRequest:
    def __init__(self, *, required_confirmation_count: int = 3):
        self.summary_text = "About to erase: /dev/fake (FAKE-SERIAL)"
        self.required_confirmation_count = required_confirmation_count


def test_confirmation_declining_target_device_cancels() -> None:
    provider = autorun.build_confirmation_provider_interactively(_scripted_input("n"))
    check_raises(
        AquilaCancelledError,
        lambda: provider(_FakeConfirmationRequest()),
        "declining the target-device confirmation raises AquilaCancelledError",
    )


def test_confirmation_declining_final_approval_cancels() -> None:
    provider = autorun.build_confirmation_provider_interactively(
        _scripted_input("y", FORCE_CONFIRMATION_PHRASE, "n")
    )
    check_raises(
        AquilaCancelledError,
        lambda: provider(_FakeConfirmationRequest()),
        "declining final approval raises AquilaCancelledError",
    )


def test_confirmation_full_approval_succeeds() -> None:
    provider = autorun.build_confirmation_provider_interactively(
        _scripted_input("y", FORCE_CONFIRMATION_PHRASE, "y")
    )
    result = provider(_FakeConfirmationRequest())
    check(result.target_device_confirmed is True, "full approval sets target_device_confirmed")
    check(
        result.erasure_acknowledgement_phrase == FORCE_CONFIRMATION_PHRASE,
        "full approval carries the typed erasure phrase through unchanged",
    )
    check(result.final_approval is True, "full approval sets final_approval")
    check(result.additional_confirmations == (), "no extra confirmations needed when count == 3")


def test_confirmation_additional_confirmations_required() -> None:
    provider = autorun.build_confirmation_provider_interactively(
        _scripted_input("y", FORCE_CONFIRMATION_PHRASE, "y", "y", "y")
    )
    result = provider(_FakeConfirmationRequest(required_confirmation_count=5))
    check(
        result.additional_confirmations == (True, True),
        "2 extra confirmations are collected when required_confirmation_count is 5",
    )


def test_confirmation_declining_an_additional_confirmation_cancels() -> None:
    provider = autorun.build_confirmation_provider_interactively(
        _scripted_input("y", FORCE_CONFIRMATION_PHRASE, "n", "y")
    )
    check_raises(
        AquilaCancelledError,
        lambda: provider(_FakeConfirmationRequest(required_confirmation_count=4)),
        "declining one of the additional confirmations raises AquilaCancelledError",
    )


# ---------------------------------------------------------------------------
# run_autorun -- top-level exception-to-exit-code mapping
# ---------------------------------------------------------------------------


def test_run_autorun_maps_build_context_failure() -> None:
    def _raising_build_context(_configs_dir):
        raise CliUsageError("simulated startup failure")

    original = autorun.build_context
    autorun.build_context = _raising_build_context
    try:
        result = autorun.run_autorun(input_fn=_scripted_input())
        check(
            result == DEPLOYMENT_ERROR,
            "a build_context() failure returns DEPLOYMENT_ERROR without raising",
        )
    finally:
        autorun.build_context = original


def run() -> None:
    print("=" * 70)
    print("Project Aquila -- cli.autorun functional tests")
    print("=" * 70)

    test_parse_device_selection()
    test_recovery_no_volumes_auto_skips()
    test_recovery_skip_requires_exact_phrase()
    test_recovery_skip_with_correct_phrase()
    test_recovery_recover_all()
    test_recovery_recover_no_readable_files()
    test_recovery_empty_destination_rejected()
    test_confirmation_declining_target_device_cancels()
    test_confirmation_declining_final_approval_cancels()
    test_confirmation_full_approval_succeeds()
    test_confirmation_additional_confirmations_required()
    test_confirmation_declining_an_additional_confirmation_cancels()
    test_run_autorun_maps_build_context_failure()

    print("=" * 70)
    if failures:
        print(f"{len(failures)} check(s) FAILED:")
        for description in failures:
            print(f"  - {description}")
        sys.exit(1)
    else:
        print("All checks passed.")
        sys.exit(0)


if __name__ == "__main__":
    run()
