"""
Vivy AI — Action System: System Executor
==========================================
Handles OS-level system actions like virtual desktop navigation.

Spec reference: §22 (Device/System Actions)
"""

from __future__ import annotations

import threading
from typing import Optional

from action.intent_model import ActionResult, IntentModel


class SystemExecutor:
    """Executes system-level intents."""

    _instance: Optional["SystemExecutor"] = None
    _lock: threading.RLock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "SystemExecutor":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def manage_system(self, intent: IntentModel) -> ActionResult:
        """Manage system-level OS interactions."""
        action = intent.action.lower()
        
        try:
            from action.windows_system_adapter import WindowsSystemAdapter
            
            success, msg = WindowsSystemAdapter.send_shortcut(action)
            if not success:
                return ActionResult(
                    success=False, domain="system", action=action, target=intent.target,
                    message=f"Unsupported system action: {action}",
                    error=msg
                )
                
            return ActionResult(
                success=True, domain="system", action=action, target=intent.target,
                message=msg, verified=True
            )
            
        except Exception as err:
            return ActionResult(
                success=False, domain="system", action=action, target=intent.target,
                message="I wasn't able to perform the system action.",
                error=str(err)
            )

    def execute(self, intent: IntentModel) -> ActionResult:
        action = intent.action.lower()
        supported_actions = (
            "show_desktop", "previous_desktop", "next_desktop", "task_view",
            "next_app", "previous_app", "screenshot", "volume_up", "volume_down",
            "mute_toggle", "escape", "cancel", "confirm", "like",
            "scroll_up", "scroll_down", "click",
            "task_view_prev", "task_view_next", "task_view_select"
        )
        if action in supported_actions:
            return self.manage_system(intent)
        return ActionResult(
            success=False, domain="system", action=action, target=intent.target,
            message=f"I don't know how to '{action}' for the system.",
            error="Unsupported system action",
        )


def get_system_executor() -> SystemExecutor:
    return SystemExecutor.get_instance()
