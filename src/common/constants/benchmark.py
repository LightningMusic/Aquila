"""
Project Orion
=============

Benchmark Constants

Defines application-wide benchmark constants used throughout
Project Orion.

These values provide the default configuration for all
hardware benchmarking operations.

Author:
    Project Orion Development Team

License:
    MIT
"""

from __future__ import annotations

# ----------------------------------------------------------------------
# General
# ----------------------------------------------------------------------

BENCHMARK_VERSION = "1.0"

DEFAULT_WARMUP_SECONDS = 5

DEFAULT_DURATION_SECONDS = 60

DEFAULT_SAMPLE_INTERVAL_SECONDS = 1.0

DEFAULT_THREAD_COUNT = 0  # 0 = Automatic

# ----------------------------------------------------------------------
# Benchmark Types
# ----------------------------------------------------------------------

CPU_BENCHMARK = "cpu"

MEMORY_BENCHMARK = "memory"

STORAGE_BENCHMARK = "storage"

NETWORK_BENCHMARK = "network"

THERMAL_BENCHMARK = "thermal"

FULL_SYSTEM_BENCHMARK = "full"

# ----------------------------------------------------------------------
# CPU
# ----------------------------------------------------------------------

CPU_WARNING_TEMPERATURE_C = 80

CPU_CRITICAL_TEMPERATURE_C = 90

CPU_MAX_UTILIZATION_PERCENT = 100

CPU_IDLE_THRESHOLD_PERCENT = 10

# ----------------------------------------------------------------------
# Memory
# ----------------------------------------------------------------------

MEMORY_WARNING_PERCENT = 85

MEMORY_CRITICAL_PERCENT = 95

MEMORY_TEST_BLOCK_SIZE_MB = 256

# ----------------------------------------------------------------------
# Storage
# ----------------------------------------------------------------------

STORAGE_TEST_FILE_SIZE_MB = 1024

STORAGE_BLOCK_SIZE_KB = 1024

MIN_STORAGE_READ_MBPS = 100

MIN_STORAGE_WRITE_MBPS = 75

# ----------------------------------------------------------------------
# Network
# ----------------------------------------------------------------------

NETWORK_TEST_PACKET_SIZE = 1400

NETWORK_DEFAULT_PORT = 5201

NETWORK_TEST_DURATION_SECONDS = 30

MIN_NETWORK_SPEED_MBPS = 100

# ----------------------------------------------------------------------
# Thermal
# ----------------------------------------------------------------------

THERMAL_SAMPLE_INTERVAL_SECONDS = 2

THERMAL_COOLDOWN_SECONDS = 30

# ----------------------------------------------------------------------
# Benchmark Ratings
# ----------------------------------------------------------------------

RATING_EXCELLENT = "Excellent"

RATING_GOOD = "Good"

RATING_FAIR = "Fair"

RATING_POOR = "Poor"

RATING_FAILED = "Failed"

# ----------------------------------------------------------------------
# Score Thresholds
# ----------------------------------------------------------------------

SCORE_EXCELLENT = 90

SCORE_GOOD = 75

SCORE_FAIR = 60

SCORE_POOR = 40

# ----------------------------------------------------------------------
# Report Defaults
# ----------------------------------------------------------------------

DEFAULT_REPORT_PRECISION = 2

DEFAULT_GRAPH_WIDTH = 1200

DEFAULT_GRAPH_HEIGHT = 800

# ----------------------------------------------------------------------
# Units
# ----------------------------------------------------------------------

UNIT_CELSIUS = "°C"

UNIT_PERCENT = "%"

UNIT_MBPS = "MB/s"

UNIT_GBPS = "Gb/s"

UNIT_SECONDS = "s"

UNIT_GIGABYTES = "GB"

UNIT_MEGABYTES = "MB"

# ----------------------------------------------------------------------
# Public Exports
# ----------------------------------------------------------------------

__all__ = [
    "BENCHMARK_VERSION",
    "CPU_BENCHMARK",
    "CPU_CRITICAL_TEMPERATURE_C",
    "CPU_IDLE_THRESHOLD_PERCENT",
    "CPU_MAX_UTILIZATION_PERCENT",
    "CPU_WARNING_TEMPERATURE_C",
    "DEFAULT_DURATION_SECONDS",
    "DEFAULT_GRAPH_HEIGHT",
    "DEFAULT_GRAPH_WIDTH",
    "DEFAULT_REPORT_PRECISION",
    "DEFAULT_SAMPLE_INTERVAL_SECONDS",
    "DEFAULT_THREAD_COUNT",
    "DEFAULT_WARMUP_SECONDS",
    "FULL_SYSTEM_BENCHMARK",
    "MEMORY_BENCHMARK",
    "MEMORY_CRITICAL_PERCENT",
    "MEMORY_TEST_BLOCK_SIZE_MB",
    "MEMORY_WARNING_PERCENT",
    "MIN_NETWORK_SPEED_MBPS",
    "MIN_STORAGE_READ_MBPS",
    "MIN_STORAGE_WRITE_MBPS",
    "NETWORK_BENCHMARK",
    "NETWORK_DEFAULT_PORT",
    "NETWORK_TEST_DURATION_SECONDS",
    "NETWORK_TEST_PACKET_SIZE",
    "RATING_EXCELLENT",
    "RATING_FAILED",
    "RATING_FAIR",
    "RATING_GOOD",
    "RATING_POOR",
    "SCORE_EXCELLENT",
    "SCORE_FAIR",
    "SCORE_GOOD",
    "SCORE_POOR",
    "STORAGE_BENCHMARK",
    "STORAGE_BLOCK_SIZE_KB",
    "STORAGE_TEST_FILE_SIZE_MB",
    "THERMAL_BENCHMARK",
    "THERMAL_COOLDOWN_SECONDS",
    "THERMAL_SAMPLE_INTERVAL_SECONDS",
    "UNIT_CELSIUS",
    "UNIT_GBPS",
    "UNIT_GIGABYTES",
    "UNIT_MEGABYTES",
    "UNIT_MBPS",
    "UNIT_PERCENT",
    "UNIT_SECONDS",
]