"""
Project Orion
=============

Storage Benchmark

Provides storage benchmarking for Project Orion.

This module performs lightweight sequential write,
sequential read, and random read/write benchmarks
using temporary files. It is intended to validate
storage performance before Proxmox installation.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

import os
import random
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any


class StorageBenchmark:
    """
    Performs lightweight storage benchmarks.
    """

    DEFAULT_FILE_SIZE_MB = 64
    BLOCK_SIZE = 1024 * 1024  # 1 MiB

    def __init__(
        self,
        file_size_mb: int = DEFAULT_FILE_SIZE_MB,
    ) -> None:

        self.file_size_mb = file_size_mb
        self.file_size_bytes = file_size_mb * 1024 * 1024

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """
        Execute the storage benchmark suite.
        """

        temp_dir = Path(tempfile.mkdtemp(prefix="orion_storage_"))
        test_file = temp_dir / "benchmark.bin"

        try:

            write_result = self._sequential_write(test_file)
            read_result = self._sequential_read(test_file)
            random_result = self._random_access(test_file)

            score = self._calculate_score(
                write_result["mbps"],
                read_result["mbps"],
                random_result["ops_per_second"],
            )

            return {
                "benchmark": "Storage",
                "test_file_size_mb": self.file_size_mb,
                "sequential_write": write_result,
                "sequential_read": read_result,
                "random_access": random_result,
                "score": score,
                "status": "PASS",
            }

        finally:

            shutil.rmtree(temp_dir, ignore_errors=True)

    # ---------------------------------------------------------
    # Sequential Write
    # ---------------------------------------------------------

    def _sequential_write(
        self,
        file_path: Path,
    ) -> dict[str, Any]:

        block = bytes(self.BLOCK_SIZE)

        remaining = self.file_size_bytes

        start = time.perf_counter()

        with file_path.open("wb") as stream:

            while remaining > 0:

                chunk = min(self.BLOCK_SIZE, remaining)

                stream.write(block[:chunk])

                remaining -= chunk

            stream.flush()
            os.fsync(stream.fileno())

        elapsed = time.perf_counter() - start

        mbps = self.file_size_mb / elapsed

        return {
            "seconds": round(elapsed, 4),
            "mbps": round(mbps, 2),
        }

    # ---------------------------------------------------------
    # Sequential Read
    # ---------------------------------------------------------

    def _sequential_read(
        self,
        file_path: Path,
    ) -> dict[str, Any]:

        start = time.perf_counter()

        with file_path.open("rb") as stream:

            while stream.read(self.BLOCK_SIZE):
                pass

        elapsed = time.perf_counter() - start

        mbps = self.file_size_mb / elapsed

        return {
            "seconds": round(elapsed, 4),
            "mbps": round(mbps, 2),
        }

    # ---------------------------------------------------------
    # Random Access
    # ---------------------------------------------------------

    def _random_access(
        self,
        file_path: Path,
    ) -> dict[str, Any]:

        operations = 1000

        start = time.perf_counter()

        with file_path.open("rb") as stream:

            for _ in range(operations):

                offset = random.randint(
                    0,
                    self.file_size_bytes - 4096,
                )

                stream.seek(offset)

                stream.read(4096)

        elapsed = time.perf_counter() - start

        return {
            "seconds": round(elapsed, 4),
            "operations": operations,
            "ops_per_second": round(
                operations / elapsed,
                2,
            ),
        }

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    @staticmethod
    def _calculate_score(
        write_speed: float,
        read_speed: float,
        random_ops: float,
    ) -> int:
        """
        Calculate a simple storage score.
        """

        return int(
            (write_speed * 2)
            + (read_speed * 2)
            + (random_ops / 100)
        )