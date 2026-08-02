"""
evolution/correction_engine.py
==================================
Vivy AI — Evolution Engine: Correction Engine

Generates safe, constrained micro-patches and behavior corrections based on
diagnostic findings, ensuring seamless rollback preparation.
"""

from __future__ import annotations
import os
import json
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from evolution.diagnosis_engine import get_diagnosis_engine, DiagnosticReport

@dataclass
class MicroPatch:
    patch_id: str
    timestamp: float
    target_component: str
    parameter_changes: Dict[str, Any]
    reason: str
    applied: bool = False
    rollback_token: str = ""

class CorrectionEngine:
    """
    Automated Correction & Micro-Patch Generator.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._applied_patches: List[MicroPatch] = []
        self._rollback_stack: List[MicroPatch] = []

    def generate_correction(self, report: Optional[DiagnosticReport] = None) -> Optional[MicroPatch]:
        if report is None:
            report = get_diagnosis_engine().diagnose_system_health()

        if not report.performance_drift_detected and not report.anomaly_detected:
            return None

        now = time.time()
        patch_id = f"patch_{int(now * 1000)}"
        rollback_token = f"rb_{patch_id}"

        target = "context_injector"
        changes = {}
        reason = ""

        if report.primary_bottleneck == "prompt_bloat":
            target = "context_injector"
            changes = {"token_budget_cap": 800, "trim_stale_history": True}
            reason = "Diagnostic detected prompt_bloat latency; capping token budget."
        elif report.primary_bottleneck == "gpu_latency":
            target = "llm_config"
            changes = {"max_tokens_cap": 120, "temperature_modifier": -0.05}
            reason = "Diagnostic detected GPU inference delay; tightening max generation tokens."
        elif report.anomaly_detected:
            target = "dialogue_router"
            changes = {"rie_min_score": 0.82, "inject_empathy_hint": True}
            reason = "Diagnostic detected dialogue quality anomaly; raising RIE threshold."

        if not changes:
            return None

        patch = MicroPatch(
            patch_id=patch_id,
            timestamp=now,
            target_component=target,
            parameter_changes=changes,
            reason=reason,
            applied=False,
            rollback_token=rollback_token
        )

        with self._lock:
            self._applied_patches.append(patch)
            self._rollback_stack.append(patch)

        return patch

    def apply_patch(self, patch: MicroPatch) -> bool:
        """Mark patch as applied safely."""
        with self._lock:
            patch.applied = True
            return True

    def rollback_last_patch(self) -> Optional[MicroPatch]:
        """Roll back the most recent micro-patch."""
        with self._lock:
            if not self._rollback_stack:
                return None
            patch = self._rollback_stack.pop()
            patch.applied = False
            return patch

    def get_applied_patches(self) -> List[MicroPatch]:
        with self._lock:
            return [p for p in self._applied_patches if p.applied]

_global_correction_engine: Optional[CorrectionEngine] = None
_correction_lock = threading.Lock()

def get_correction_engine() -> CorrectionEngine:
    global _global_correction_engine
    if _global_correction_engine is None:
        with _correction_lock:
            if _global_correction_engine is None:
                _global_correction_engine = CorrectionEngine()
    return _global_correction_engine
