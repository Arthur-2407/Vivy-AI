"""
circadian/__init__.py
======================
Vivy AI — Circadian Intelligence System package.

Public API:
    from circadian import get_state, get_modulation_prompt_fragment
    from circadian.hardware_manager import get_hardware_hint
"""

from circadian.circadian_engine import get_state, get_modulation_prompt_fragment

__all__ = [
    "get_state",
    "get_modulation_prompt_fragment",
]
