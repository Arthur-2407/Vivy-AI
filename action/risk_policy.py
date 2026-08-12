"""
Vivy AI — Action System: Risk Policy
=====================================
Centralized authority for determining the risk level and authorization
requirements of an action intent. No executor may independently decide risk.

Spec reference: Phase 8 Architectural Refinements
"""

from __future__ import annotations
from typing import Dict, Any
from .intent_model import IntentModel, RiskLevel

# Hardcoded domain/action risk baseline
# Note: In a full deployment, this would be data-driven or ML-assisted.
_BASE_RISK_MAP = {
    # HIGH RISK: Financial, Destructive, Privacy
    ("shopping", "purchase"): RiskLevel.HIGH_RISK.value,
    ("shopping", "buy"): RiskLevel.HIGH_RISK.value,
    ("file", "delete"): RiskLevel.HIGH_RISK.value,
    ("file", "format"): RiskLevel.HIGH_RISK.value,
    ("device", "reset"): RiskLevel.HIGH_RISK.value,
    ("device", "shutdown"): RiskLevel.MEDIUM_RISK.value,
    ("device", "restart"): RiskLevel.MEDIUM_RISK.value,
    
    # MEDIUM RISK: State-changing but reversible or annoying
    ("app", "close"): RiskLevel.MEDIUM_RISK.value,
    ("app", "quit"): RiskLevel.MEDIUM_RISK.value,
    ("app", "uninstall"): RiskLevel.HIGH_RISK.value,
    ("browser", "close_tab"): RiskLevel.MEDIUM_RISK.value,
    
    # LOW RISK: Read-only or ephemeral
    ("shopping", "search"): RiskLevel.LOW_RISK.value,
    ("shopping", "recommend"): RiskLevel.LOW_RISK.value,
    ("file", "open"): RiskLevel.LOW_RISK.value,
    ("file", "find"): RiskLevel.LOW_RISK.value,
    ("media", "play"): RiskLevel.LOW_RISK.value,
    ("media", "pause"): RiskLevel.LOW_RISK.value,
    ("app", "open"): RiskLevel.LOW_RISK.value,
    ("app", "switch"): RiskLevel.LOW_RISK.value,
    ("browser", "open"): RiskLevel.LOW_RISK.value,
    ("browser", "search"): RiskLevel.LOW_RISK.value,
}

class RiskPolicy:
    """Evaluates the risk level of an action intent before execution."""
    
    @classmethod
    def evaluate(cls, intent: IntentModel) -> str:
        """
        Determines the risk level of the intent.
        Overrides any heuristic confidence with authoritative policy.
        """
        key = (intent.domain.lower(), intent.action.lower())
        
        # 1. Base map lookup
        risk = _BASE_RISK_MAP.get(key)
        
        # 2. Dynamic modifiers
        if not risk:
            # Assume medium risk for unknown state-changing actions
            risk = RiskLevel.MEDIUM_RISK.value
            
        # Update the intent in place for the executor to enforce
        intent.risk_level = risk
        
        # High risk always requires explicit user confirmation
        if risk == RiskLevel.HIGH_RISK.value:
            intent.confirmation_required = True
            
        return risk

def evaluate_risk(intent: IntentModel) -> str:
    return RiskPolicy.evaluate(intent)
