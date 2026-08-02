"""
evolution/governance_layer.py
==================================
Vivy AI — Evolution Engine: Governance & Safety Layer

Enforces strict safety scoring, automated validation gates, audit logging,
canary deployment control, and instant rollback. Ensures structural modifications
are NEVER executed autonomously and require explicit user approval.
"""

from __future__ import annotations
import os
import json
import time
import threading
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
_SHARED_DIR = os.path.join(_PROJECT_ROOT, "shared")
_AUDIT_LOG_FILE = os.path.join(_SHARED_DIR, "evolution_audit.json")

@dataclass
class GovernanceAuditEntry:
    entry_id: str
    timestamp: float
    action_type: str  # "micro_patch", "policy_snapshot", "canary_deploy", "rollback", "structural_gate"
    safety_score: float
    status: str       # "APPROVED", "REJECTED_SAFETY", "REQUIRES_HUMAN_APPROVAL", "ROLLED_BACK"
    details: Dict[str, Any]
    reason: str

class GovernanceLayer:
    """
    Safety Guardrail & Audit System.
    """
    def __init__(self, min_safety_score: float = 0.90):
        self._lock = threading.Lock()
        self._min_safety_score = min_safety_score
        self._audit_log: List[GovernanceAuditEntry] = []
        self._load_audit_log()

    def _load_audit_log(self):
        if os.path.exists(_AUDIT_LOG_FILE):
            try:
                with open(_AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                    for item in raw_data:
                        self._audit_log.append(GovernanceAuditEntry(**item))
            except Exception as _err:
                print(f"[governance_layer.py] Silenced exception: {_err}")

    def _persist_audit_log(self):
        try:
            os.makedirs(_SHARED_DIR, exist_ok=True)
            tmp = _AUDIT_LOG_FILE + ".tmp"
            serialized = [asdict(entry) for entry in self._audit_log[-200:]]
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(serialized, f, indent=2)
            os.replace(tmp, _AUDIT_LOG_FILE)
        except Exception as _err:
            print(f"[governance_layer.py] Silenced exception: {_err}")

    def evaluate_safety_score(self, proposed_changes: Dict[str, Any]) -> float:
        """
        Calculate safety score for a proposed micro-patch or parameter modification.
        [0.0 - 1.0]. Zero score if code files or core APIs are touched.
        """
        # Rule check: Structural code modifications are strictly forbidden
        if "modify_code" in proposed_changes or "delete_file" in proposed_changes:
            return 0.0

        score = 1.0

        # Check parameter boundary limits
        if "max_tokens_cap" in proposed_changes and proposed_changes["max_tokens_cap"] < 20:
            score -= 0.3
        if "token_budget_cap" in proposed_changes and proposed_changes["token_budget_cap"] < 100:
            score -= 0.3
        if "rie_min_score" in proposed_changes and proposed_changes["rie_min_score"] < 0.5:
            score -= 0.4

        return round(max(0.0, score), 4)

    def validate_and_approve(
        self,
        action_type: str,
        proposed_changes: Dict[str, Any],
        is_structural_change: bool = False,
        reason: str = ""
    ) -> Tuple[bool, GovernanceAuditEntry]:
        """
        Validate proposed update against safety policies and record audit entry.
        """
        now = time.time()
        entry_id = f"gov_{int(now * 1000)}"

        if is_structural_change:
            entry = GovernanceAuditEntry(
                entry_id=entry_id,
                timestamp=now,
                action_type=action_type,
                safety_score=0.0,
                status="REQUIRES_HUMAN_APPROVAL",
                details=proposed_changes,
                reason="Structural modification requested; blocked pending human approval per Rule 1 & Rule 3."
            )
            with self._lock:
                self._audit_log.append(entry)
                self._persist_audit_log()
            return False, entry

        safety_score = self.evaluate_safety_score(proposed_changes)
        approved = safety_score >= self._min_safety_score
        status = "APPROVED" if approved else "REJECTED_SAFETY"

        entry = GovernanceAuditEntry(
            entry_id=entry_id,
            timestamp=now,
            action_type=action_type,
            safety_score=safety_score,
            status=status,
            details=proposed_changes,
            reason=reason if approved else f"Safety score ({safety_score}) below threshold ({self._min_safety_score})."
        )

        with self._lock:
            self._audit_log.append(entry)
            self._persist_audit_log()

        return approved, entry

    def record_rollback(self, patch_id: str, reason: str) -> GovernanceAuditEntry:
        now = time.time()
        entry = GovernanceAuditEntry(
            entry_id=f"rb_{int(now * 1000)}",
            timestamp=now,
            action_type="rollback",
            safety_score=1.0,
            status="ROLLED_BACK",
            details={"rolled_back_patch_id": patch_id},
            reason=reason
        )
        with self._lock:
            self._audit_log.append(entry)
            self._persist_audit_log()
        return entry

    def get_audit_trail(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return [asdict(e) for e in self._audit_log[-limit:]]

_global_governance_layer: Optional[GovernanceLayer] = None
_governance_lock = threading.Lock()

def get_governance_layer() -> GovernanceLayer:
    global _global_governance_layer
    if _global_governance_layer is None:
        with _governance_lock:
            if _global_governance_layer is None:
                _global_governance_layer = GovernanceLayer()
    return _global_governance_layer
