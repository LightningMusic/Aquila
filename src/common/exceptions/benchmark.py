"""
Project Orion
=============

Benchmark Exceptions

Defines benchmark-related exceptions used throughout
Project Orion.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

from common.exceptions.application import OrionError


class BenchmarkError(OrionError):
    """
    Base class for all benchmark-related exceptions.
    """


class BenchmarkInitializationError(BenchmarkError):
    """
    Raised when a benchmark cannot be initialized.
    """


class BenchmarkConfigurationError(BenchmarkError):
    """
    Raised when benchmark configuration is invalid.
    """


class BenchmarkValidationError(BenchmarkError):
    """
    Raised when benchmark parameters fail validation.
    """


class BenchmarkExecutionError(BenchmarkError):
    """
    Raised when a benchmark fails during execution.
    """


class BenchmarkTimeoutError(BenchmarkError):
    """
    Raised when a benchmark exceeds its allowed runtime.
    """


class BenchmarkCancelledError(BenchmarkError):
    """
    Raised when a benchmark is cancelled.
    """


class BenchmarkResultError(BenchmarkError):
    """
    Raised when benchmark results are invalid,
    incomplete, or cannot be processed.
    """


class BenchmarkStorageError(BenchmarkError):
    """
    Raised when benchmark results cannot be saved
    or loaded.
    """


class BenchmarkHardwareError(BenchmarkError):
    """
    Raised when required hardware is unavailable
    or unsuitable for benchmarking.
    """


class CpuBenchmarkError(BenchmarkError):
    """
    Raised during CPU benchmark failures.
    """


class MemoryBenchmarkError(BenchmarkError):
    """
    Raised during memory benchmark failures.
    """


class StorageBenchmarkError(BenchmarkError):
    """
    Raised during storage benchmark failures.
    """


class NetworkBenchmarkError(BenchmarkError):
    """
    Raised during network benchmark failures.
    """


class ThermalBenchmarkError(BenchmarkError):
    """
    Raised when thermal conditions invalidate
    benchmark execution.
    """


class BenchmarkReportError(BenchmarkError):
    """
    Raised when benchmark reports cannot be
    generated.
    """


class BenchmarkExportError(BenchmarkError):
    """
    Raised when benchmark data cannot be exported.
    """


__all__ = [
    "BenchmarkCancelledError",
    "BenchmarkConfigurationError",
    "BenchmarkError",
    "BenchmarkExecutionError",
    "BenchmarkExportError",
    "BenchmarkHardwareError",
    "BenchmarkInitializationError",
    "BenchmarkReportError",
    "BenchmarkResultError",
    "BenchmarkStorageError",
    "BenchmarkTimeoutError",
    "BenchmarkValidationError",
    "CpuBenchmarkError",
    "MemoryBenchmarkError",
    "NetworkBenchmarkError",
    "StorageBenchmarkError",
    "ThermalBenchmarkError",
]