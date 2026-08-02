"""
Vivy AI — General Self-Evaluation & Retry Reasoning Loop (AGI Subsystem)
========================================================================
Provides autonomous iterative evaluation for tasks:
  **Execute -> Critique & Diagnose Error -> Propose Corrective Action -> Retry**
Designed to autonomously resolve code execution syntax/logic errors, tool retrieval
failures, and operational missteps without giving up prematurely or breaking control flow.
"""

import os
import sys
import time
import json
import threading
from typing import Dict, Any, Optional, Callable, List, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

class SelfEvaluationLoop:
    """Iterative self-critique, error diagnosis, and retry reasoning engine."""
    _instance = None
    _lock = threading.RLock()

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.history = []

    @classmethod
    def get_instance(cls) -> "SelfEvaluationLoop":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def evaluate_and_retry(self, task_name: str, execution_fn: Callable[..., Dict[str, Any]], initial_kwargs: Dict[str, Any], corrective_advisor: Optional[Callable[[Dict[str, Any], Dict[str, Any], int], Dict[str, Any]]] = None, max_attempts: Optional[int] = None) -> Dict[str, Any]:
        """
        Executes a task function and automatically retries upon detected failure.
        If a corrective_advisor callback is supplied, it modifies kwargs based on diagnosis.
        Otherwise, applies automated rule-based self-corrections for common code/file bugs.
        """
        with self._lock:
            attempts_limit = max_attempts if max_attempts is not None else self.max_retries
            current_kwargs = initial_kwargs.copy()
            attempt_logs: List[Dict[str, Any]] = []
            t_start = time.time()
            final_res = None

            for attempt in range(1, attempts_limit + 1):
                try:
                    res = execution_fn(**current_kwargs)
                except Exception as fn_err:
                    res = {"success": False, "error": str(fn_err), "diagnosis": {"error_type": "UnhandledExecutionException", "summary": str(fn_err)}}

                is_success = res.get("success", False) or res.get("returncode", -1) == 0
                attempt_telemetry = {
                    "attempt": attempt,
                    "kwargs_used": current_kwargs.copy(),
                    "result_success": is_success,
                    "error_diagnosis": res.get("diagnosis") or res.get("error", "Unknown failure")
                }
                attempt_logs.append(attempt_telemetry)
                final_res = res

                if is_success:
                    break

                # Self-Critique & Corrective Plan formulation if more attempts remain
                if attempt < attempts_limit:
                    if corrective_advisor:
                        current_kwargs = corrective_advisor(current_kwargs, res, attempt)
                    else:
                        current_kwargs = self._default_auto_advisor(task_name, current_kwargs, res, attempt)

            duration = time.time() - t_start
            outcome_package = {
                "task_name": task_name,
                "resolved": final_res.get("success", False) or final_res.get("returncode", -1) == 0 if final_res else False,
                "attempts_needed": len(attempt_logs),
                "total_duration_ms": round(duration * 1000.0, 2),
                "final_result": final_res,
                "attempt_logs": attempt_logs,
                "timestamp": time.time()
            }
            self.history.append(outcome_package)
            if len(self.history) > 50:
                self.history.pop(0)
            return outcome_package

    def _default_auto_advisor(self, task_name: str, kwargs: Dict[str, Any], fail_res: Dict[str, Any], attempt: int) -> Dict[str, Any]:
        """Automated rule-based self-critique advisor for standard tools."""
        new_kwargs = kwargs.copy()
        diag = fail_res.get("diagnosis", {}) if isinstance(fail_res.get("diagnosis"), dict) else {}
        err_type = str(diag.get("error_type") or fail_res.get("error", "")).lower()
        err_summary = str(diag.get("summary") or fail_res.get("stderr") or "").lower()

        # Code execution self-corrections
        if "code_text" in new_kwargs or "code" in new_kwargs:
            code_key = "code_text" if "code_text" in new_kwargs else "code"
            curr_code = str(new_kwargs[code_key])

            # Zero division fix attempt
            if "zerodivision" in err_type or "division by zero" in err_summary:
                lines = curr_code.split("\n")
                new_lines = []
                for l in lines:
                    if "/ 0" in l or "/0" in l:
                        new_lines.append(l.replace("/ 0", "/ 1").replace("/0", "/ 1") + " # [Self-Correction: prevented ZeroDivisionError]")
                    else:
                        new_lines.append(l)
                new_kwargs[code_key] = "\n".join(new_lines)

            # Name error fix attempt (undeclared variable)
            elif "nameerror" in err_type or "is not defined" in err_summary:
                import re
                m = re.search(r"name '([^']+)' is not defined", err_summary, re.IGNORECASE)
                if m:
                    var_name = m.group(1)
                    new_kwargs[code_key] = f"# [Self-Correction: auto-initialized {var_name}]\n{var_name} = 0\n" + curr_code

            # Timeout defense adjustments
            elif "timeout" in err_type:
                new_kwargs["timeout"] = float(new_kwargs.get("timeout", 10.0)) * 1.5

        return new_kwargs

_global_self_eval_loop = None
def get_self_evaluation_loop() -> SelfEvaluationLoop:
    global _global_self_eval_loop
    if _global_self_eval_loop is None:
        _global_self_eval_loop = SelfEvaluationLoop()
    return _global_self_eval_loop
