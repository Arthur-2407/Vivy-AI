"""
Vivy AI — Relationship Intelligence Layer (Relationship Dynamics Engine)
========================================================================
Serves as the emotional heart of Vivy, governing self-awareness, attachment theory,
non-linear affection progression, dynamic personality evolution, weighted experiential
memory, emotional continuity anticipation, and reflexive self-evaluation.
"""

from typing import Optional
from .relationship_engine import RelationshipEngine, get_relationship_engine
from .attachment_engine import AttachmentEngine
from .affection_progression import AffectionProgressionEngine
from .personality_evolution import PersonalityEvolutionEngine
from .emotional_continuity import EmotionalContinuityEngine
from .shared_history import SharedHistoryManager
from .intimacy_manager import IntimacyManager
from .interaction_style import InteractionStyleAdaptor
from .comfort_model import ComfortModel
from .relationship_memory import RelationshipMemoryManager

__all__ = [
    "RelationshipEngine",
    "get_relationship_engine",
    "AttachmentEngine",
    "AffectionProgressionEngine",
    "PersonalityEvolutionEngine",
    "EmotionalContinuityEngine",
    "SharedHistoryManager",
    "IntimacyManager",
    "InteractionStyleAdaptor",
    "ComfortModel",
    "RelationshipMemoryManager",
]
