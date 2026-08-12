"""
Vivy AI — Action System Package
================================
Voice Assistant Action System / Intent-Based Command Execution.

Spec reference: §2 (Core Integration Rules), §24 (Capability Registry),
                §27 (Smart Manager)

Usage:
    from action import get_action_system
    result = get_action_system().try_route(query, context)
"""

from __future__ import annotations

import threading
from typing import Optional

# Lazy import guard — prevents circular import issues during startup
_action_system: Optional["SmartManager"] = None
_init_lock = threading.Lock()
_initialized = False


def get_action_system() -> "SmartManager":
    """
    Return the singleton SmartManager instance.
    Initialises the CapabilityRegistry with built-in capabilities on first call.
    Thread-safe, idempotent.
    """
    global _action_system, _initialized

    if _action_system is not None:
        return _action_system

    with _init_lock:
        if _action_system is not None:
            return _action_system

        try:
            from action.capability_registry import (
                get_capability_registry,
                _register_builtin_capabilities,
            )
            registry = get_capability_registry()

            if not _initialized:
                _register_builtin_capabilities(registry)
                _initialized = True

            from action.smart_manager import SmartManager
            _action_system = SmartManager.get_instance()

            print("[ActionSystem] Initialised: SmartManager + CapabilityRegistry ready.")

        except Exception as err:
            print(f"[ActionSystem] Initialisation error: {err}")
            # Return a minimal no-op manager so the rest of the system never crashes
            from action.smart_manager import SmartManager
            _action_system = SmartManager()
            _action_system._enabled = False

        return _action_system


__all__ = ["get_action_system"]
