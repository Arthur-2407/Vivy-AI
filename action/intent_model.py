"""
Vivy AI — Action System: Intent Model
=======================================
Defines the structured intent representation that all action system components
use to communicate. No hardcoded command mappings — intents are discovered at
runtime from natural language.

Spec reference: §23 (Intent Model), §19 (Risk Classification)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RiskLevel(Enum):
    """Action risk classification per spec §19."""
    LOW_RISK    = "LOW_RISK"    # browsing, searching, opening, reading, filtering
    MEDIUM_RISK = "MEDIUM_RISK" # downloading, modifying files, changing settings, sending messages
    HIGH_RISK   = "HIGH_RISK"   # deleting data, purchasing, financial transactions, irreversible ops


class ActionState(Enum):
    """Action Lifecycle States (Phase 9)."""
    CREATED          = "CREATED"
    UNDERSTANDING    = "UNDERSTANDING"
    PLANNED          = "PLANNED"
    AUTHORIZED       = "AUTHORIZED"
    EXECUTING        = "EXECUTING"
    OBSERVING        = "OBSERVING"
    VERIFYING        = "VERIFYING"
    SUCCESS          = "SUCCESS"
    RETRYING         = "RETRYING"
    FALLBACK         = "FALLBACK"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    CANCELLED        = "CANCELLED"
    FAILED           = "FAILED"



class ActionDomain(Enum):
    """Top-level domain of an intent."""
    MEDIA    = "media"
    FILE     = "file"
    APP      = "app"
    BROWSER  = "browser"
    SHOPPING = "shopping"
    DEVICE   = "device"
    SYSTEM   = "system"
    UNKNOWN  = "unknown"


class ActionVerb(Enum):
    """Normalized action verbs."""
    PLAY     = "play"
    PAUSE    = "pause"
    STOP     = "stop"
    RESUME   = "resume"
    OPEN     = "open"
    CLOSE    = "close"
    FIND     = "find"
    SEARCH   = "search"
    NAVIGATE = "navigate"
    SELECT   = "select"
    BUY      = "buy"
    FILTER   = "filter"
    COMPARE  = "compare"
    RECOMMEND = "recommend"
    ADJUST   = "adjust"
    LIST     = "list"
    CREATE   = "create"
    SWITCH   = "switch"
    UNKNOWN  = "unknown"


@dataclass
class IntentModel:
    """
    Structured representation of a user intent.
    Populated by SmartManager.detect_intent() and consumed by ActionPlanner.

    Spec reference: §23
    """
    domain: str                        # ActionDomain value string
    action: str                        # ActionVerb value string
    target: str                        # e.g. "Let Me Down", "Downloads folder", "YouTube"
    source: str = "local_then_online"  # "local_only" | "online_only" | "local_then_online"

    # Structured constraints (budget, brand, quality, etc.)
    constraints: Dict[str, Any] = field(default_factory=dict)

    # Domain-specific parameters
    parameters: Dict[str, Any] = field(default_factory=dict)

    # Resolution context: refers to previous candidates, session state
    context: Dict[str, Any] = field(default_factory=dict)

    confidence: float = 0.0
    risk_level: str = RiskLevel.LOW_RISK.value
    confirmation_required: bool = False
    fallback_policy: str = "ask_user"   # "online_search" | "ask_user" | "none"
    expected_result: str = ""           # "playback_started" | "file_opened" | "page_loaded" | ...

    # Internal metadata
    raw_text: str = ""                  # Original user utterance
    detected_at: float = field(default_factory=time.time)
    is_followup: bool = False           # True if this refers to a prior action context
    state: str = ActionState.CREATED.value  # Current lifecycle state

    def to_dict(self) -> Dict[str, Any]:
        """Serialise for session storage and telemetry."""
        return {
            "domain":               self.domain,
            "action":               self.action,
            "target":               self.target,
            "source":               self.source,
            "constraints":          self.constraints,
            "parameters":           self.parameters,
            "context":              self.context,
            "confidence":           self.confidence,
            "risk_level":           self.risk_level,
            "confirmation_required": self.confirmation_required,
            "fallback_policy":      self.fallback_policy,
            "expected_result":      self.expected_result,
            "raw_text":             self.raw_text,
            "detected_at":          self.detected_at,
            "is_followup":          self.is_followup,
            "state":                self.state,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "IntentModel":
        return IntentModel(
            domain               = d.get("domain", ActionDomain.UNKNOWN.value),
            action               = d.get("action", ActionVerb.UNKNOWN.value),
            target               = d.get("target", ""),
            source               = d.get("source", "local_then_online"),
            constraints          = d.get("constraints", {}),
            parameters           = d.get("parameters", {}),
            context              = d.get("context", {}),
            confidence           = float(d.get("confidence", 0.0)),
            risk_level           = d.get("risk_level", RiskLevel.LOW_RISK.value),
            confirmation_required= bool(d.get("confirmation_required", False)),
            fallback_policy      = d.get("fallback_policy", "ask_user"),
            expected_result      = d.get("expected_result", ""),
            raw_text             = d.get("raw_text", ""),
            detected_at          = float(d.get("detected_at", time.time())),
            is_followup          = bool(d.get("is_followup", False)),
            state                = d.get("state", ActionState.CREATED.value),
        )

    def is_high_risk(self) -> bool:
        return self.risk_level == RiskLevel.HIGH_RISK.value

    def __repr__(self) -> str:
        return (f"IntentModel(domain={self.domain!r}, action={self.action!r}, "
                f"target={self.target!r}, confidence={self.confidence:.2f}, "
                f"risk={self.risk_level})")


@dataclass
class ActionResult:
    """
    Structured result returned from an action executor back to the conversation pipeline.
    The conversation layer transforms this into a natural language response.

    Spec reference: §35, §38 (no false completion)
    """
    success: bool
    domain: str
    action: str
    target: str
    message: str                          # Human-readable result description
    verified: bool = False                # True only if ObservationAdapter confirmed success
    requires_confirmation: bool = False   # True if HIGH_RISK gate was triggered
    confirmation_payload: Optional[Dict[str, Any]] = None
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    observation: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    recovery_attempted: bool = False
    fallback_used: bool = False
    telemetry: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    state: str = ActionState.SUCCESS.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success":               self.success,
            "domain":                self.domain,
            "action":                self.action,
            "target":                self.target,
            "message":               self.message,
            "verified":              self.verified,
            "requires_confirmation": self.requires_confirmation,
            "confirmation_payload":  self.confirmation_payload,
            "candidates":            self.candidates,
            "observation":           self.observation,
            "error":                 self.error,
            "recovery_attempted":    self.recovery_attempted,
            "fallback_used":         self.fallback_used,
            "telemetry":             self.telemetry,
            "timestamp":             self.timestamp,
            "state":                 self.state,
        }

    def to_natural_language(self) -> str:
        """
        Return a concise, honest natural language summary.
        Never claims success unless verified=True. (§38)
        """
        if self.requires_confirmation:
            return f"I need your confirmation before I proceed with: {self.message}"
        if self.success and self.verified:
            return self.message
        if self.success and not self.verified:
            return f"{self.message} (I initiated this but couldn't fully verify the result.)"
        if self.error:
            return f"I wasn't able to complete that. {self.message} Reason: {self.error}"
        return self.message
