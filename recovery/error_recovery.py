import time
import functools
import threading
from typing import Callable, Any, Dict, Optional, Type
from logging_framework.vivy_logger import get_logger

logger = get_logger("ErrorRecovery")

class ErrorRecoveryManager:
    """
    Error Recovery & Resilience Manager for Vivy AI (v1.0.0).
    Per Rule 10 of the Master Hyperprompt.

    Implements:
      - Fallback registration for missing clips/assets/data
      - Exponential backoff retry strategies
      - Cascade failure isolation
      - Default state recovery on corruption
    """
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self._fallbacks: Dict[str, Callable[[], Any]] = {}
        self._failure_counts: Dict[str, int] = {}

    @classmethod
    def get_instance(cls) -> "ErrorRecoveryManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def register_fallback(self, subsystem: str, fallback_func: Callable[[], Any]):
        with self._lock:
            self._fallbacks[subsystem] = fallback_func
            logger.info(f"Registered fallback strategy for subsystem '{subsystem}'")

    def execute_with_fallback(self, subsystem: str, primary_func: Callable[[], Any], default_val: Any = None) -> Any:
        try:
            res = primary_func()
            with self._lock:
                self._failure_counts[subsystem] = 0
            return res
        except Exception as ex:
            logger.error(f"Primary execution failed in subsystem '{subsystem}': {ex}", event_type="error_recovery")
            with self._lock:
                self._failure_counts[subsystem] = self._failure_counts.get(subsystem, 0) + 1

            if subsystem in self._fallbacks:
                try:
                    logger.warn(f"Executing registered fallback for subsystem '{subsystem}'")
                    return self._fallbacks[subsystem]()
                except Exception as fallback_ex:
                    logger.fatal(f"Fallback strategy also failed for subsystem '{subsystem}': {fallback_ex}")

            return default_val


def with_retry(max_retries: int = 3, initial_delay: float = 0.5, backoff_factor: float = 2.0, exceptions: tuple = (Exception,)):
    """Decorator to retry a function call with exponential backoff."""
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_err = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as err:
                    last_err = err
                    logger.warn(f"Function '{func.__name__}' attempt {attempt}/{max_retries} failed: {err}")
                    if attempt < max_retries:
                        time.sleep(delay)
                        delay *= backoff_factor
            logger.error(f"Function '{func.__name__}' failed all {max_retries} attempts.")
            raise last_err
        return wrapper
    return decorator


_global_recovery_mgr = None

def get_recovery_manager() -> ErrorRecoveryManager:
    global _global_recovery_mgr
    if _global_recovery_mgr is None:
        _global_recovery_mgr = ErrorRecoveryManager.get_instance()
    return _global_recovery_mgr
