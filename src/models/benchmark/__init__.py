"""
Project Aquila
=============

Benchmark Data Models

Typed representations of benchmark results as they cross the
Deployment Controller API boundary (REQ-BENCH-007) and are persisted
by the Inventory System (REQ-INV-003).

Author:
    Project Aquila Development Team

License:
    MIT
"""

from __future__ import annotations

from models.benchmark.benchmark import BenchmarkRecord
from models.benchmark.result import BenchmarkCategoryResult

__all__ = ["BenchmarkCategoryResult", "BenchmarkRecord"]
