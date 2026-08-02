"""
perception/__init__.py
========================
Vivy AI Multimodal Perception Package

Public API re-exports for convenient top-level imports.

All sub-modules are imported lazily to avoid circular dependencies
and to allow individual components to be used in isolation.
"""

__version__ = "1.0.0"
__author__ = "Vivy AI Systems"

# Lazy sub-module references — do not import at package level to avoid
# pulling in heavy dependencies (PIL, sounddevice) unless actually used.
# Callers import directly: from perception.fusion_engine import FusionEngine

__all__ = [
    "config_loader",
    "screen_pipeline",
    "vision_adapter",
    "audio_pipeline",
    "fusion_engine",
    "event_memory",
    "context_injector",
    "proactivity_engine",
    "perception_manager",
]
