"""
Vivy AI — Error Recovery & Resilience Framework
================================================
Per Rule 10 of the Master Hyperprompt:
Fallback strategies, retry mechanisms with exponential backoff,
graceful degradation, and cascade failure isolation.
"""

from .error_recovery import ErrorRecoveryManager, get_recovery_manager, with_retry

__all__ = ["ErrorRecoveryManager", "get_recovery_manager", "with_retry"]
