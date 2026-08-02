import os
import sys
import time
import json
import threading
from typing import Optional, Dict, Any
from contracts.diagnostic_event import DiagnosticEvent

SEVERITY_LEVELS = {
    "TRACE": 0,
    "DEBUG": 1,
    "INFO": 2,
    "WARN": 3,
    "ERROR": 4,
    "FATAL": 5,
}

class VivyLogger:
    """
    Structured Logging & Diagnostics System for Vivy AI (v1.0.0).
    Per Rule 11 of the Master Hyperprompt.

    Supports:
      - Structured log entries with severity levels
      - Module categorization tags
      - Profiling hooks and performance counters
      - Telemetry collection
      - Emission of DiagnosticEvent contracts
      - File logging and terminal output formatting
    """
    _instances: Dict[str, "VivyLogger"] = {}
    _lock = threading.RLock()
    _log_file = None

    def __init__(self, module_name: str = "General", min_level: str = "INFO"):
        self.module_name = module_name
        self.min_level = min_level.upper()
        self.metrics: Dict[str, float] = {}

    @classmethod
    def get_logger(cls, module_name: str = "General", min_level: str = "INFO") -> "VivyLogger":
        with cls._lock:
            if module_name not in cls._instances:
                cls._instances[module_name] = cls(module_name, min_level)
            return cls._instances[module_name]

    def _should_log(self, severity: str) -> bool:
        sev_val = SEVERITY_LEVELS.get(severity.upper(), 2)
        min_val = SEVERITY_LEVELS.get(self.min_level, 2)
        return sev_val >= min_val

    def log(self, severity: str, message: str, event_type: str = "general", details: Optional[Dict[str, Any]] = None, stack_context: str = "") -> DiagnosticEvent:
        event = DiagnosticEvent(
            timestamp=time.time(),
            module_id=self.module_name,
            event_type=event_type,
            severity=severity.upper(),
            message=message,
            stack_context=stack_context,
            metrics=details or {}
        )

        if self._should_log(severity):
            self._write_output(event)

        return event

    def trace(self, msg: str, **kwargs): return self.log("TRACE", msg, **kwargs)
    def debug(self, msg: str, **kwargs): return self.log("DEBUG", msg, **kwargs)
    def info(self, msg: str, **kwargs):  return self.log("INFO", msg, **kwargs)
    def warn(self, msg: str, **kwargs):  return self.log("WARN", msg, **kwargs)
    def error(self, msg: str, **kwargs): return self.log("ERROR", msg, **kwargs)
    def fatal(self, msg: str, **kwargs): return self.log("FATAL", msg, **kwargs)

    def log_metric(self, metric_name: str, value: float):
        with self._lock:
            self.metrics[metric_name] = value
            self.debug(f"Metric '{metric_name}' = {value}", event_type="metric", details={metric_name: value})

    def _write_output(self, event: DiagnosticEvent):
        ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(event.timestamp))
        log_line = f"[{ts_str}] [{event.severity:<5}] [{event.module_id:<15}] {event.message}"
        if event.metrics:
            log_line += f" | {json.dumps(event.metrics)}"
        print(log_line)


def get_logger(module_name: str = "General", min_level: str = "INFO") -> VivyLogger:
    return VivyLogger.get_logger(module_name, min_level)
