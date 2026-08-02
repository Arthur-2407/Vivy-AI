"""
Vivy AI — Structured Logging & Diagnostics Framework
=====================================================
Structured log entries with severity levels, module categorization,
performance counters, and telemetry reporting.
"""

from .vivy_logger import VivyLogger, get_logger

__all__ = ["VivyLogger", "get_logger"]
