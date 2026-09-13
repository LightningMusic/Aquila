"""
Project Aquila
=============

Benchmark Initiation

Implements REQ-BOOT-015 ("initiate hardware benchmarking after
successful cluster enrollment").

Per this session's confirmed ordering decision (resolving a real
ambiguity between Appendix B's Workflow B diagram and REQ-BOOT-012
through -016's numbered order -- see
``claude/aquila-project-status.md``), benchmarking runs *after*
inventory registration, not before: REQ-BENCH-010 ("Benchmark history
shall remain associated with the node inventory record") and
REQ-INV-003 ("The Inventory System shall record benchmark results")
both require the inventory record to already exist before a benchmark
result can be attached to it.

Thin wrapper around ``benchmark.benchmark_manager.BenchmarkManager``
-- the Benchmark Engine (SRS Section 10.10 / REQ-BENCH-001 through
-010) is already fully implemented; this module does not re-implement
CPU/GPU/memory/storage/network/thermal benchmarking, only initiates it
and reports the result, matching REQ-BOOT-015's own wording
("initiate", not "implement").

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

import logging
from typing import Protocol

from benchmark.benchmark_manager import BenchmarkManager
from benchmark.report import BenchmarkReport
from common.constants.logging import BOOTSTRAP_LOGGER

logger = logging.getLogger(BOOTSTRAP_LOGGER)


class BenchmarkRunner(Protocol):
    """The subset of ``BenchmarkManager`` this module depends on."""

    def run(self) -> BenchmarkReport: ...


class BenchmarkInitiator:
    """
    Initiates the Benchmark Engine and returns its report
    (REQ-BOOT-015).
    """

    def __init__(
        self, *, benchmark_runner: BenchmarkRunner | None = None
    ) -> None:
        self._runner = benchmark_runner or BenchmarkManager()

    def run(self) -> BenchmarkReport:
        """
        Execute the full benchmark suite.

        Never raises: ``BenchmarkManager.run()`` already isolates
        every individual benchmark's failure into a ``"FAILED"``
        entry within the returned report (REQ-BENCH-008, "Benchmark
        failures shall be reported separately from deployment
        failures") -- Bootstrap does not additionally fail deployment
        over a benchmark result, matching the Benchmark Engine's own
        overview: "Benchmarking shall not prevent the node from
        entering operational service."
        """

        report = self._runner.run()

        if report.successful:
            logger.info(
                "Benchmark completed successfully (overall score: "
                "%d).",
                report.overall_score,
            )
        else:
            logger.warning(
                "Benchmark completed with one or more failed "
                "categories (overall score: %d) -- deployment "
                "continues (REQ-BENCH-008).",
                report.overall_score,
            )

        return report


__all__ = ["BenchmarkInitiator", "BenchmarkRunner"]
