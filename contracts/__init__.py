"""
Vivy AI × Mate Engine — Standardized Data Contracts Package (v1.0.0)
====================================================================
All inter-module communication must use formally defined data contracts.
Every data contract is a versioned, serializable, validated structure.
"""

CONTRACT_VERSION = "1.0.0"

from .emotion_state import EmotionState
from .animation_request import AnimationRequest
from .animation_response import AnimationResponse
from .behavior_state import BehaviorState
from .context_package import ContextPackage
from .cognitive_output import CognitiveOutput
from .diagnostic_event import DiagnosticEvent

__all__ = [
    "CONTRACT_VERSION",
    "EmotionState",
    "AnimationRequest",
    "AnimationResponse",
    "BehaviorState",
    "ContextPackage",
    "CognitiveOutput",
    "DiagnosticEvent",
]
