"""
evolution/__init__.py
========================
Vivy AI — Autonomous Self-Evolution Engine Package

Integrates all 9 self-evolution layers into a unified, non-destructive loop:
Perception -> Adaptation -> Diagnosis -> Correction -> Consolidation -> Meta Learning -> Evolution -> Safety Validation -> Monitoring -> Repeat
"""

from __future__ import annotations
import os
import json
import time
import threading
from typing import Dict, List, Any, Optional

from evolution.perception_layer import get_perception_layer, Experience
from evolution.adaptation_engine import get_adaptation_engine
from evolution.diagnosis_engine import get_diagnosis_engine
from evolution.correction_engine import get_correction_engine
from evolution.consolidation_layer import get_consolidation_layer
from evolution.meta_learning import get_meta_learning_engine
from evolution.evolution_engine import get_evolution_engine
from evolution.governance_layer import get_governance_layer
from evolution.monitoring import get_continuous_monitor

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
_SHARED_DIR = os.path.join(_PROJECT_ROOT, "shared")
_STATE_PATH = os.path.join(_SHARED_DIR, "evolution_state.json")

class SelfEvolutionOrchestrator:
    """
    Unified Orchestrator implementing the full self-evolution loop for Vivy AI.
    Runs asynchronously on CPU without blocking dialogue latency or wasting GPU.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self.perception = get_perception_layer()
        self.adaptation = get_adaptation_engine()
        self.diagnosis = get_diagnosis_engine()
        self.correction = get_correction_engine()
        self.consolidation = get_consolidation_layer()
        self.meta_learning = get_meta_learning_engine()
        self.evolution = get_evolution_engine()
        self.governance = get_governance_layer()
        self.monitoring = get_continuous_monitor()
        self._active_loop_count = 0

    def step_evolution_loop(
        self,
        user_input: str,
        system_reply: str,
        emotion_label: str = "neutral",
        rie_score: float = 0.85,
        latency_seconds: float = 0.5,
        circadian_phase: str = "Afternoon"
    ) -> Dict[str, Any]:
        """
        Executes one full iteration of the Self-Evolution Loop.
        """
        t0 = time.time()

        # 1. Perception
        exp = self.perception.record_experience(
            user_input=user_input,
            system_reply=system_reply,
            emotion_label=emotion_label,
            rie_score=rie_score,
            latency_seconds=latency_seconds,
            circadian_phase=circadian_phase
        )

        # 2. Adaptation
        policy_snap = self.adaptation.process_adaptation_step()

        # 3. Diagnosis
        diag_report = self.diagnosis.diagnose_system_health()

        # 4. Correction
        micro_patch = self.correction.generate_correction(diag_report)

        # 5. Consolidation
        cons_result = self.consolidation.consolidate_experiences()

        # 6. Meta Learning
        meta_config = self.meta_learning.optimize_hyperparameters()

        # 7. Evolution (Runs during quiet circadian phases)
        evolved_candidate = self.evolution.run_evolution_cycle(circadian_phase=circadian_phase)

        # 8. Safety Validation & Deployment
        patch_applied = False
        if micro_patch:
            approved, audit_entry = self.governance.validate_and_approve(
                action_type="micro_patch",
                proposed_changes=micro_patch.parameter_changes,
                is_structural_change=False,
                reason=micro_patch.reason
            )
            if approved:
                patch_applied = self.correction.apply_patch(micro_patch)

        # 9. Continuous Monitoring
        telemetry = self.monitoring.collect_system_metrics()
        self.monitoring.write_telemetry_snapshot({"last_loop_duration_s": round(time.time() - t0, 4)})

        with self._lock:
            self._active_loop_count += 1

        state_summary = {
            "loop_count": self._active_loop_count,
            "last_step_timestamp": time.time(),
            "last_step_duration_s": round(time.time() - t0, 4),
            "experience_buffer_size": self.perception.get_buffer_size(),
            "confidence_score": self.adaptation.evaluate_confidence(self.perception.get_recent_experiences(20)),
            "diagnostic_status": "healthy" if not diag_report.anomaly_detected else "anomaly_detected",
            "active_policy": self.adaptation.get_active_policy(),
            "micro_patch_applied": patch_applied,
            "curriculum_stage": meta_config.curriculum_stage,
            "best_evolved_genome": evolved_candidate.genome_id if evolved_candidate else "none",
            "telemetry": telemetry
        }

        # Persist evolution_state.json for web_server dashboard
        try:
            os.makedirs(_SHARED_DIR, exist_ok=True)
            tmp = _STATE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state_summary, f, indent=2)
            os.replace(tmp, _STATE_PATH)
        except Exception as _err:
            print(f"[__init__.py] Silenced exception: {_err}")

        return state_summary

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "active_loop_count": self._active_loop_count,
                "experience_buffer_size": self.perception.get_buffer_size(),
                "active_policy": self.adaptation.get_active_policy(),
                "curriculum_stage": self.meta_learning.get_config().curriculum_stage,
                "audit_trail": self.governance.get_audit_trail(10)
            }

_global_orchestrator: Optional[SelfEvolutionOrchestrator] = None
_orchestrator_lock = threading.Lock()

def get_evolution_orchestrator() -> SelfEvolutionOrchestrator:
    global _global_orchestrator
    if _global_orchestrator is None:
        with _orchestrator_lock:
            if _global_orchestrator is None:
                _global_orchestrator = SelfEvolutionOrchestrator()
    return _global_orchestrator
