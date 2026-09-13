"""
Project Aquila
=============

Functional tests for ``src/main.py`` -- the top-level process entry
point.

Scope note, matching this repository's own established convention
(``run_tests_cli.py``, ``run_tests_technician_console.py``): this
suite verifies ``main()``'s *dispatch* decision only -- which
frontend a given ``argv`` routes to, and that its return value is
passed through unchanged -- via lightweight fake ``cli``/
``technician_console`` modules injected into ``sys.modules``. It does
not exercise a real ``run_cli()``/``run_console()`` call (those are
already covered by ``run_tests_cli.py`` and
``run_tests_technician_console.py`` respectively), and deliberately
avoids importing the real ``technician_console`` package here, which
would require a working Tk/Tcl runtime this suite has no need to
depend on.

Run with:
    python tests/run_tests_main.py  (run from the repository root)
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

failures: list[str] = []


def check(condition: bool, description: str) -> None:
    if not condition:
        failures.append(description)
        print(f"FAIL: {description}")
    else:
        print(f"PASS: {description}")


def _install_fake_frontends(
    *, cli_exit: int = 0, console_exit: int = 0, autorun_exit: int = 0
):
    """
    Replace ``cli``/``cli.autorun``/``technician_console`` in
    ``sys.modules`` with minimal fakes recording how they were called,
    so ``main()`` can be exercised without any frontend's real
    dependencies (Tk, the real ``workflows`` stack, a real terminal for
    ``cli.autorun``'s ``input()`` prompts) present.
    """

    calls: dict[str, object] = {}

    fake_cli = types.ModuleType("cli")

    def _fake_run_cli(argv=None):
        calls["run_cli_argv"] = argv
        return cli_exit

    fake_cli.run_cli = _fake_run_cli  # type: ignore[attr-defined]

    fake_autorun = types.ModuleType("cli.autorun")

    def _fake_run_autorun():
        calls["run_autorun_called"] = True
        return autorun_exit

    fake_autorun.run_autorun = _fake_run_autorun  # type: ignore[attr-defined]
    fake_cli.autorun = fake_autorun  # type: ignore[attr-defined]

    fake_console = types.ModuleType("technician_console")

    def _fake_run_console():
        calls["run_console_called"] = True
        return console_exit

    fake_console.run_console = _fake_run_console  # type: ignore[attr-defined]

    sys.modules["cli"] = fake_cli
    sys.modules["cli.autorun"] = fake_autorun
    sys.modules["technician_console"] = fake_console
    return calls


def _remove_fake_frontends() -> None:
    sys.modules.pop("cli", None)
    sys.modules.pop("cli.autorun", None)
    sys.modules.pop("technician_console", None)
    sys.modules.pop("main", None)


def run() -> None:
    print("=" * 70)
    print("Project Aquila -- main.py entry-point dispatch tests")
    print("=" * 70)

    # --- No arguments: launches the Technician Console -----------------
    calls = _install_fake_frontends(console_exit=0)
    try:
        import main as main_module

        result = main_module.main([])
        check(calls.get("run_console_called") is True, "no argv launches the Technician Console")
        check("run_cli_argv" not in calls, "no argv never touches cli.run_cli")
        check(result == 0, "no-argv dispatch returns the console's own exit code")
    finally:
        _remove_fake_frontends()

    # --- 'autorun' routes to cli.autorun.run_autorun, not cli.run_cli or
    # the console -- and takes no argv of its own (run_autorun() has none).
    calls = _install_fake_frontends(autorun_exit=0)
    try:
        import main as main_module

        result = main_module.main(["autorun"])
        check(calls.get("run_autorun_called") is True, "'autorun' routes to cli.autorun.run_autorun")
        check("run_cli_argv" not in calls, "'autorun' never touches cli.run_cli")
        check("run_console_called" not in calls, "'autorun' never launches the Technician Console")
    finally:
        _remove_fake_frontends()

    calls = _install_fake_frontends(autorun_exit=3)
    try:
        import main as main_module

        result = main_module.main(["autorun"])
        check(result == 3, "'autorun's own exit code passes through main() unchanged")
    finally:
        _remove_fake_frontends()

    # --- argv=None (the real sys.argv[1:] shape) defaults to the console
    calls = _install_fake_frontends(console_exit=0)
    old_argv = sys.argv
    try:
        sys.argv = ["aquila"]
        import main as main_module

        result = main_module.main(None)
        check(calls.get("run_console_called") is True, "argv=None with a bare sys.argv launches the console")
    finally:
        sys.argv = old_argv
        _remove_fake_frontends()

    # --- Each cli/ subcommand name routes to cli.run_cli, not the console
    for subcommand in ("inspect", "retire", "provision", "logs"):
        calls = _install_fake_frontends(cli_exit=0)
        try:
            import main as main_module

            argv = [subcommand, "--some-flag"]
            main_module.main(argv)
            check(
                calls.get("run_cli_argv") == argv,
                f"'{subcommand}' as the first argument routes to cli.run_cli with argv unchanged",
            )
            check(
                "run_console_called" not in calls,
                f"'{subcommand}' dispatch never launches the Technician Console",
            )
        finally:
            _remove_fake_frontends()

    # --- An unrecognized first argument still falls through to the console
    # (main.py does its own arg validation nowhere -- an unknown token is
    # not a cli/ subcommand, so it is not this module's job to reject it;
    # the Technician Console (or a technician's own typo) is the one that
    # will report it, not a silent no-op here).
    calls = _install_fake_frontends(console_exit=0)
    try:
        import main as main_module

        main_module.main(["--not-a-known-subcommand"])
        check(
            calls.get("run_console_called") is True,
            "an unrecognized first argument still falls through to the console",
        )
    finally:
        _remove_fake_frontends()

    # --- Exit codes from each frontend pass through unchanged ----------
    calls = _install_fake_frontends(console_exit=1)
    try:
        import main as main_module

        result = main_module.main([])
        check(result == 1, "the console's non-zero exit code passes through main() unchanged")
    finally:
        _remove_fake_frontends()

    calls = _install_fake_frontends(cli_exit=2)
    try:
        import main as main_module

        result = main_module.main(["provision"])
        check(result == 2, "cli's non-zero exit code passes through main() unchanged")
    finally:
        _remove_fake_frontends()

    # --- __main__ guard: exits with main()'s return value ---------------
    main_src = (SRC.parent / "src" / "main.py").read_text(encoding="utf-8")
    check(
        'if __name__ == "__main__":' in main_src and "sys.exit(main())" in main_src,
        "the module's __main__ guard calls sys.exit(main())",
    )

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
