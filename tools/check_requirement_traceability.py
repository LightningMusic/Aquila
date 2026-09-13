#!/usr/bin/env python3
"""
Project Aquila
=============

Requirement Traceability Checker

Implements SRS Section 13.2's own requirement: "Every requirement
identifier (REQ-* and NFR-*) shall be traceable to: source code
implementation, test cases, release notes, deployment documentation.
This traceability shall be maintained throughout the project's
lifecycle."

This tool automates the two least subjective legs of that chain --
source code and test-case traceability -- by extracting every
requirement identifier the SRS itself defines, then checking whether
each one is cited (as plain text, the house convention already used
throughout ``src/*`` and ``run_tests_*.py``) anywhere in the source
tree and anywhere in the test suite. It does not, and cannot, judge
whether a citation reflects a *correct* implementation -- only whether
one was ever written down at all. A requirement with zero source
citations is a real, actionable gap: either the requirement was never
implemented, or it was implemented without anyone recording which code
satisfies it (itself a documentation defect GP-010 exists to prevent).
A requirement with zero test citations is a weaker signal -- some
requirements are exercised indirectly through a broader test rather
than cited by identifier -- and is reported separately rather than
folded into the same pass/fail bucket.

Usage:
    python tools/check_requirement_traceability.py
    python tools/check_requirement_traceability.py --strict
    python tools/check_requirement_traceability.py --format json

Exit codes:
    0 -- every requirement identifier has at least one source citation
         (and, under --strict, at least one test citation too).
    1 -- at least one requirement identifier has zero source citations
         (or, under --strict, zero test citations).
    2 -- the SRS document could not be read or contained no
         requirement identifiers at all (almost certainly a path
         problem, not a real empty-SRS state).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

#: Matches this SRS's own documented identifier format (Section 11.1):
#: "REQ-[Subsystem]-###", e.g. REQ-TC-001, REQ-INS-014. NFR identifiers
#: follow the same shape with a different prefix, e.g. NFR-PERF-001,
#: NFR-MAIN-005 (Section 12). Anchored to a Markdown H3 heading
#: ("### REQ-TC-001") so prose that merely *mentions* an identifier
#: in passing (as this docstring just did) is not miscounted as the
#: SRS defining a new one.
_SRS_HEADING_PATTERN = re.compile(r"^###\s+((?:REQ|NFR)-[A-Z]+-\d{3})\s*$", re.MULTILINE)

#: Matches a bare identifier anywhere in a source or test file's text
#: (docstrings, comments, and code both use the identifier as plain
#: text, e.g. "REQ-INS-025", never as a symbol).
_CITATION_PATTERN = re.compile(r"(?:REQ|NFR)-[A-Z]+-\d{3}")

_DEFAULT_SRS_PATH = Path("docs/SRS/Project-Aquila-SRS.md")
_DEFAULT_SRC_PATH = Path("src")
_DEFAULT_TEST_ROOTS = (Path("."), Path("tests"))
_TEST_FILE_GLOB = "run_tests_*.py"


@dataclass(frozen=True, slots=True)
class TraceabilityReport:
    """The result of one traceability check run."""

    all_ids: tuple[str, ...]
    missing_source: tuple[str, ...]
    missing_tests: tuple[str, ...]
    source_files_scanned: int
    test_files_scanned: int
    citations_by_id: dict[str, "_Citations"] = field(default_factory=dict)

    @property
    def fully_traced_count(self) -> int:
        return len(self.all_ids) - len(set(self.missing_source) | set(self.missing_tests))

    def to_dict(self) -> dict[str, object]:
        return {
            "total_requirements": len(self.all_ids),
            "source_files_scanned": self.source_files_scanned,
            "test_files_scanned": self.test_files_scanned,
            "missing_source_reference": list(self.missing_source),
            "missing_test_reference": list(self.missing_tests),
            "fully_traced_count": self.fully_traced_count,
        }


@dataclass(slots=True)
class _Citations:
    source_files: list[str]
    test_files: list[str]


def extract_requirement_ids(srs_text: str) -> list[str]:
    """
    Extract every REQ-*/NFR-* identifier the SRS defines as a
    heading, in document order, without duplicates (the current SRS
    has one known duplicate-section defect -- see
    ``provisioning/__init__.py``'s module docstring on the live
    repository -- so de-duplication here is load-bearing, not
    defensive).
    """

    seen: dict[str, None] = {}
    for match in _SRS_HEADING_PATTERN.finditer(srs_text):
        seen.setdefault(match.group(1), None)
    return list(seen.keys())


def _iter_python_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def _iter_test_files(test_roots: tuple[Path, ...]) -> list[Path]:
    files: dict[Path, None] = {}
    for root in test_roots:
        if not root.exists():
            continue
        if root == Path("."):
            # Only the top-level run_tests_*.py convention here --
            # rglob("*.py") on "." would re-scan src/ and everything
            # else under the repository root.
            for path in sorted(root.glob(_TEST_FILE_GLOB)):
                files.setdefault(path, None)
        else:
            for path in sorted(root.rglob("*.py")):
                files.setdefault(path, None)
    return list(files.keys())


def _scan_files_for_citations(files: list[Path]) -> dict[str, list[str]]:
    """Map each requirement identifier found to the file(s) citing it."""

    citations: dict[str, list[str]] = {}
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found_in_file: set[str] = set(_CITATION_PATTERN.findall(text))
        for identifier in found_in_file:
            citations.setdefault(identifier, []).append(str(path))
    return citations


def check_traceability(
    *,
    srs_path: Path = _DEFAULT_SRS_PATH,
    src_path: Path = _DEFAULT_SRC_PATH,
    test_roots: tuple[Path, ...] = _DEFAULT_TEST_ROOTS,
) -> TraceabilityReport:
    """
    Run a full traceability pass and return the resulting report.

    Raises:
        FileNotFoundError: If ``srs_path`` does not exist.
        ValueError: If ``srs_path`` exists but defines zero
            requirement identifiers (almost certainly means the
            heading pattern no longer matches the SRS's real
            formatting, not that the SRS is genuinely empty).
    """

    srs_text = srs_path.read_text(encoding="utf-8")
    all_ids = extract_requirement_ids(srs_text)
    if not all_ids:
        raise ValueError(
            f"No REQ-*/NFR-* identifiers found in {srs_path}. This almost "
            "certainly means the SRS's heading format changed and "
            "_SRS_HEADING_PATTERN needs updating, not that the "
            "specification is genuinely empty."
        )

    source_files = _iter_python_files(src_path)
    test_files = _iter_test_files(test_roots)

    source_citations = _scan_files_for_citations(source_files)
    test_citations = _scan_files_for_citations(test_files)

    citations_by_id: dict[str, _Citations] = {}
    missing_source: list[str] = []
    missing_tests: list[str] = []

    for identifier in all_ids:
        src_refs = source_citations.get(identifier, [])
        test_refs = test_citations.get(identifier, [])
        citations_by_id[identifier] = _Citations(
            source_files=src_refs, test_files=test_refs
        )
        if not src_refs:
            missing_source.append(identifier)
        if not test_refs:
            missing_tests.append(identifier)

    return TraceabilityReport(
        all_ids=tuple(all_ids),
        missing_source=tuple(missing_source),
        missing_tests=tuple(missing_tests),
        source_files_scanned=len(source_files),
        test_files_scanned=len(test_files),
        citations_by_id=citations_by_id,
    )


def _print_text_report(report: TraceabilityReport) -> None:
    print("=" * 70)
    print("Project Aquila -- Requirement Traceability Report (SRS 13.2)")
    print("=" * 70)
    print(f"Requirements defined in SRS: {len(report.all_ids)}")
    print(f"Source files scanned:        {report.source_files_scanned}")
    print(f"Test files scanned:          {report.test_files_scanned}")
    print(f"Fully traced (source+test):  {report.fully_traced_count}")
    print()

    if report.missing_source:
        print(f"MISSING SOURCE REFERENCE ({len(report.missing_source)}):")
        for identifier in report.missing_source:
            print(f"  - {identifier}")
        print()
    else:
        print("Every requirement has at least one source reference.")
        print()

    if report.missing_tests:
        print(f"MISSING TEST REFERENCE ({len(report.missing_tests)}):")
        for identifier in report.missing_tests:
            print(f"  - {identifier}")
        print()
    else:
        print("Every requirement has at least one test reference.")
        print()

    print("=" * 70)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check that every REQ-*/NFR-* identifier the SRS defines is "
            "cited somewhere in src/ and somewhere in the test suite "
            "(SRS Section 13.2)."
        )
    )
    parser.add_argument("--srs", type=Path, default=_DEFAULT_SRS_PATH)
    parser.add_argument("--src", type=Path, default=_DEFAULT_SRC_PATH)
    parser.add_argument(
        "--tests",
        type=Path,
        nargs="+",
        default=list(_DEFAULT_TEST_ROOTS),
        help=(
            "Roots to search for test files: '.' is scanned "
            f"non-recursively for the '{_TEST_FILE_GLOB}' convention; "
            "any other root is scanned recursively for all *.py files."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also fail (exit 1) if any requirement has zero test references.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
    )
    args = parser.parse_args(argv)

    try:
        report = check_traceability(
            srs_path=args.srs, src_path=args.src, test_roots=tuple(args.tests)
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2))
    else:
        _print_text_report(report)

    if report.missing_source:
        return 1
    if args.strict and report.missing_tests:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
