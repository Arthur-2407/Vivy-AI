"""
evolution/diagnosis_engine.py
==================================
Vivy AI — Evolution Engine: Diagnosis Engine

Monitors runtime performance drift, detects operational anomalies, evaluates
uncertainty, performs counterfactual analysis, and localizes bottlenecks.
"""

from __future__ import annotations
import os
import time
import math
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from evolution.perception_layer import get_perception_layer

@dataclass
class DiagnosticReport:
    timestamp: float
    performance_drift_detected: bool
    anomaly_detected: bool
    uncertainty_score: float
    primary_bottleneck: str  # "none", "gpu_latency", "cpu_contention", "ipc_delay", "prompt_bloat"
    issues_found: List[str]
    metrics_summary: Dict[str, float]

class DiagnosisEngine:
    """
    Continuous diagnostic analyzer for Vivy AI pipeline.
    """
    def __init__(self, latency_threshold_s: float = 3.5, rie_min_threshold: float = 0.6):
        self._lock = threading.Lock()
        self._latency_threshold_s = latency_threshold_s
        self._rie_min_threshold = rie_min_threshold
        self._last_report: Optional[DiagnosticReport] = None

    def diagnose_system_health(self) -> DiagnosticReport:
        perception = get_perception_layer()
        experiences = perception.get_recent_experiences(30)
        telemetry = perception.get_telemetry_snapshot(20)

        now = time.time()
        issues = []
        bottleneck = "none"

        if not experiences:
            report = DiagnosticReport(
                timestamp=now,
                performance_drift_detected=False,
                anomaly_detected=False,
                uncertainty_score=0.0,
                primary_bottleneck="none",
                issues_found=[],
                metrics_summary={"avg_latency": 0.0, "avg_rie": 1.0}
            )
            return report

        latencies = [e.latency_seconds for e in experiences]
        rie_scores = [e.rie_score for e in experiences]
        avg_latency = sum(latencies) / len(latencies)
        avg_rie = sum(rie_scores) / len(rie_scores)

        # 1. Performance Drift Check
        drift_detected = avg_latency > self._latency_threshold_s

        # 2. Anomaly Check
        low_rie_count = sum(1 for r in rie_scores if r < self._rie_min_threshold)
        anomaly_detected = (low_rie_count / len(rie_scores)) > 0.2

        # 3. Failure Localization
        if drift_detected:
            issues.append(f"Average latency ({avg_latency:.2f}s) exceeded threshold ({self._latency_threshold_s:.2f}s)")
            if any(e.perception_context_len > 3000 for e in experiences):
                bottleneck = "prompt_bloat"
                issues.append("Excessive perception token budget injected into prompt")
            else:
                bottleneck = "gpu_latency"
                issues.append("LLM inference / model response delay on GPU")

        if anomaly_detected:
            issues.append(f"High frequency of low quality dialogue responses (RIE score < {self._rie_min_threshold})")

        # 4. Uncertainty Estimation
        variance = sum((l - avg_latency) ** 2 for l in latencies) / max(1, len(latencies))
        uncertainty = round(math.sqrt(variance), 4)

        report = DiagnosticReport(
            timestamp=now,
            performance_drift_detected=drift_detected,
            anomaly_detected=anomaly_detected,
            uncertainty_score=uncertainty,
            primary_bottleneck=bottleneck,
            issues_found=issues,
            metrics_summary={
                "avg_latency_s": round(avg_latency, 4),
                "avg_rie_score": round(avg_rie, 4),
                "sample_count": len(experiences)
            }
        )

        with self._lock:
            self._last_report = report

        return report

    def evaluate_counterfactual(self, prompt_length_reduction_pct: float = 0.2) -> Dict[str, Any]:
        """
        Counterfactual simulation:
        Estimates expected latency drop if prompt length were reduced by X%.
        """
        report = self.diagnose_system_health()
        current_latency = report.metrics_summary.get("avg_latency_s", 1.0)
        estimated_new_latency = max(0.2, current_latency * (1.0 - (prompt_length_reduction_pct * 0.5)))
        return {
            "prompt_length_reduction_pct": prompt_length_reduction_pct,
            "current_avg_latency_s": current_latency,
            "projected_latency_s": round(estimated_new_latency, 4),
            "expected_speedup_pct": round(((current_latency - estimated_new_latency) / max(0.001, current_latency)) * 100, 2)
        }

_global_diagnosis_engine: Optional[DiagnosisEngine] = None
_diagnosis_lock = threading.Lock()

def get_diagnosis_engine() -> DiagnosisEngine:
    global _global_diagnosis_engine
    if _global_diagnosis_engine is None:
        with _diagnosis_lock:
            if _global_diagnosis_engine is None:
                _global_diagnosis_engine = DiagnosisEngine()
    return _global_diagnosis_engine
