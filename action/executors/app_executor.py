"""
Vivy AI — Action System: App Executor
=======================================
Handles open/launch, close, and switch application actions.
Uses AppDiscovery for dynamic path resolution — no hardcoded executable paths.
Verifies launch via psutil process inspection.

Spec reference: §21 (Application Action System), §26 (Observation+Verification Loop)
"""

from __future__ import annotations

import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

from action.intent_model import ActionResult, IntentModel


class AppExecutor:
    """Executes application open/close/switch actions."""

    _instance: Optional["AppExecutor"] = None
    _lock: threading.RLock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "AppExecutor":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _find_apps(self, name: str) -> list:
        """Resolve app name to AppInfo objects via AppDiscovery."""
        try:
            from action.app_discovery import get_app_discovery
            return get_app_discovery().find(name)
        except Exception as err:
            print(f"[AppExecutor] AppDiscovery error: {err}")
            return []

    def _is_process_running(self, exe_name: str) -> bool:
        """Check if a process with matching exe name is currently running."""
        try:
            import psutil
            exe_name_l = exe_name.lower()
            for proc in psutil.process_iter(["name"]):
                try:
                    if exe_name_l in (proc.info.get("name") or "").lower():
                        return True
                except Exception:
                    continue
        except ImportError:
            # psutil not available — try tasklist fallback
            try:
                result = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {exe_name}"],
                    capture_output=True, text=True, timeout=3
                )
                return exe_name.lower() in result.stdout.lower()
            except Exception:
                pass
        return False

    def _launch_app(self, app_path: str, app_name: str) -> ActionResult:
        """Launch an application and verify it started."""
        import os
        from pathlib import Path
        exe_stem = Path(app_path).stem

        try:
            subprocess.Popen([app_path], cwd=os.path.dirname(app_path))
        except Exception as err:
            return ActionResult(
                success=False, domain="app", action="open", target=app_name,
                message=f"I couldn't launch '{app_name}'.",
                error=str(err),
            )

        # Verify with retry — allow a few seconds for process to appear
        verified = False
        for _ in range(6):
            time.sleep(0.5)
            if self._is_process_running(exe_stem):
                verified = True
                break

        if verified:
            # Phase 10 Integration: Perception Layer
            try:
                from perception.fusion_engine import get_fusion_engine
                get_fusion_engine().publish_event("action.verified_via_perception", {
                    "source": "app_executor", "app": app_name, "verified": True
                })
            except Exception:
                pass
            return ActionResult(
                success=True, domain="app", action="open", target=app_name,
                message=f"Opened '{app_name}'.",
                verified=True,
                observation={"process": exe_stem, "running": True},
            )
        return ActionResult(
            success=True, domain="app", action="open", target=app_name,
            message=f"I launched '{app_name}', but I couldn't confirm it started within a few seconds.",
            verified=False,
            observation={"process": exe_stem, "running": False},
        )

    # ── Open app ──────────────────────────────────────────────────────────────

    def open_app(self, intent: IntentModel) -> ActionResult:
        """
        Discover and launch an installed application.
        Spec reference: §21, §28 (clarification if multiple candidates)
        """
        name = intent.target.strip()
        candidates = self._find_apps(name)

        if not candidates:
            return ActionResult(
                success=False, domain="app", action="open", target=name,
                message=f"I couldn't find an application called '{name}'. "
                        f"It may not be installed or discoverable.",
                error="Application not found",
            )

        # Single unambiguous match → launch directly
        if len(candidates) == 1:
            return self._launch_app(candidates[0].path, candidates[0].name)

        # Check if one is already running → bring it to focus instead
        running = [c for c in candidates if self._is_process_running(c.name)]
        if len(running) == 1:
            return self._switch_to_app(running[0].name)

        # Multiple candidates → ask user (§21, §28)
        from action.action_session import get_action_session, save_action_session
        session = get_action_session()
        session.set_candidates([
            {"_index": i + 1, "label": c.name, "path": c.path, "source": c.source}
            for i, c in enumerate(candidates[:5])
        ])
        save_action_session(session)
        names = "\n".join(f"  {i+1}. {c.name} ({c.source})" for i, c in enumerate(candidates[:5]))
        return ActionResult(
            success=True, domain="app", action="open", target=name,
            message=f"I found multiple applications matching '{name}'. Which one should I open?\n{names}",
            candidates=session.candidates,
            requires_confirmation=False,
        )

    # ── Close app ─────────────────────────────────────────────────────────────

    def close_app(self, intent: IntentModel) -> ActionResult:
        """
        Close a running application gracefully.
        Spec reference: §21, Risk: MEDIUM (changing system state)
        """
        name = intent.target.strip()
        candidates = self._find_apps(name)
        app_names = [c.name for c in candidates] if candidates else [name]

        try:
            import psutil
            killed = []
            for proc in psutil.process_iter(["pid", "name"]):
                pname = (proc.info.get("name") or "").lower()
                if any(a.lower() in pname or pname in a.lower() for a in [n.lower() for n in app_names]):
                    try:
                        proc.terminate()
                        killed.append(proc.info["name"])
                    except Exception:
                        pass
            if killed:
                return ActionResult(
                    success=True, domain="app", action="close", target=name,
                    message=f"Closed '{', '.join(set(killed))}'.",
                    verified=True,
                )
            return ActionResult(
                success=False, domain="app", action="close", target=name,
                message=f"I couldn't find a running instance of '{name}'.",
                error="Process not found",
            )
        except ImportError:
            # Fallback: taskkill
            try:
                for a in app_names:
                    subprocess.run(["taskkill", "/F", "/IM", f"{a}.exe"], capture_output=True)
                return ActionResult(
                    success=True, domain="app", action="close", target=name,
                    message=f"Sent close signal to '{name}'.",
                    verified=False,
                )
            except Exception as err:
                return ActionResult(
                    success=False, domain="app", action="close", target=name,
                    message=f"I wasn't able to close '{name}'.",
                    error=str(err),
                )

    # ── Switch app ────────────────────────────────────────────────────────────

    def switch_to(self, intent: IntentModel) -> ActionResult:
        """Switch focus to a running application."""
        return self._switch_to_app(intent.target.strip())

    def _switch_to_app(self, name: str) -> ActionResult:
        try:
            # Try pywinauto window focus
            try:
                from pywinauto import Desktop
                windows = Desktop(backend="uia").windows()
                for w in windows:
                    try:
                        title = w.window_text().lower()
                        if name.lower() in title:
                            w.set_focus()
                            return ActionResult(
                                success=True, domain="app", action="switch", target=name,
                                message=f"Switched to '{name}'.",
                                verified=True,
                            )
                    except Exception:
                        continue
            except ImportError:
                pass

            # Fallback: use ctypes to find foreground window by title
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, name)
            if hwnd:
                user32.SetForegroundWindow(hwnd)
                return ActionResult(
                    success=True, domain="app", action="switch", target=name,
                    message=f"Switched to '{name}'.",
                    verified=True,
                )

            return ActionResult(
                success=False, domain="app", action="switch", target=name,
                message=f"I couldn't find a window for '{name}' to switch to.",
                error="Window not found",
            )
        except Exception as err:
            return ActionResult(
                success=False, domain="app", action="switch", target=name,
                message=f"I wasn't able to switch to '{name}'.",
                error=str(err),
            )

    def execute(self, intent: IntentModel) -> ActionResult:
        action = intent.action.lower()
        if action in ("open", "launch", "start"):
            return self.open_app(intent)
        if action in ("close", "quit", "exit"):
            return self.close_app(intent)
        if action in ("switch", "focus", "bring"):
            return self.switch_to(intent)
        return ActionResult(
            success=False, domain="app", action=action, target=intent.target,
            message=f"I don't know how to '{action}' an application.",
            error="Unsupported app action",
        )


def get_app_executor() -> AppExecutor:
    return AppExecutor.get_instance()
