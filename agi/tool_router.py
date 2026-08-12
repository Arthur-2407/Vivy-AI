"""
Vivy AI — Autonomous Tool Router & Invocation Engine (AGI Subsystem)
====================================================================
Unifies all generalized tools under an autonomous intelligent routing dispatch layer:
  - Sandboxed Python / Shell Code Execution
  - Workspace General File & Folder Management
  - Durable Job Scheduling & Long-Horizon Goal Check-Ins
  - Universal DuckDuckGo Internet Search Layer
  - Automated Architectural Self-Modification
"""

import os
import sys
import json
import threading
from typing import Dict, Any, Optional, List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

class AutonomousToolRouter:
    """Intelligent dynamic tool selection and execution routing engine."""
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self.available_tools = [
            "action_system",
            "code_execution",
            "file_management",
            "job_scheduling",
            "web_search",
            "self_modification"
        ]

    @classmethod
    def get_instance(cls) -> "AutonomousToolRouter":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def evaluate_and_invoke(self, query: str, context_plan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Analyzes user prompt or conversational turn plan to dynamically route and invoke
        the most applicable tool engine without hardcoded behavior locks.
        """
        with self._lock:
            q_lower = query.strip().lower()
            plan = context_plan or {}

            # 0. Action System Check (Voice Assistant / Intent-Based Command Execution)
            # SmartManager.try_route() returns {"handled": False} for non-action queries,
            # so all existing routing branches below are completely unaffected.
            # Spec reference: §27, integration with tool_router
            try:
                from action import get_action_system
                action_result = get_action_system().try_route(query, plan)
                if action_result.get("handled"):
                    return {
                        "tool_selected": "action_system",
                        "success":        action_result.get("success", False),
                        "result":         action_result,
                        "message":        action_result.get("message", ""),
                    }
            except Exception as _as_err:
                print(f"[ToolRouter] Action system routing note: {_as_err}")

            # 1. Code Execution Check
            if any(k in q_lower for k in ["run code", "execute python", "evaluate script", "calculate", "python code", "terminal command"]):
                try:
                    from agi.code_executor import get_code_executor
                    executor = get_code_executor()
                    if "code" in plan:
                        code_text = plan["code"]
                    else:
                        code_text = f"print('Executing evaluation for query:', {json.dumps(query)})"
                    res = executor.execute_python(code_text=code_text)
                    return {"tool_selected": "code_execution", "result": res, "success": res["success"]}
                except Exception as ce_err:
                    return {"tool_selected": "code_execution", "success": False, "error": str(ce_err)}

            # 2. File Management Check
            elif any(k in q_lower for k in ["list directory", "list folder", "read file", "write file", "search file", "browse file"]):
                try:
                    from agi.file_manager import get_file_manager
                    fm = get_file_manager()
                    if "list" in q_lower:
                        res = fm.list_directory("")
                    elif "search" in q_lower:
                        res = fm.search_files(query.split()[-1], file_pattern="*.py")
                    else:
                        res = fm.list_directory("")
                    return {"tool_selected": "file_management", "result": res, "success": res.get("success", True)}
                except Exception as fm_err:
                    return {"tool_selected": "file_management", "success": False, "error": str(fm_err)}

            # 3. Job Scheduling Check
            elif any(k in q_lower for k in ["schedule", "remind me", "recurring task", "timer"]):
                try:
                    from agi.job_scheduler import get_job_scheduler
                    js = get_job_scheduler()
                    j_id = js.schedule_once("User Requested Reminder", {"prompt": query}, delay_seconds=60.0)
                    return {"tool_selected": "job_scheduling", "result": {"job_id": j_id, "status": "scheduled"}, "success": True}
                except Exception as js_err:
                    return {"tool_selected": "job_scheduling", "success": False, "error": str(js_err)}

            # 4. Web Search Check (Phase 3 Integration)
            elif any(k in q_lower for k in ["search the web", "search internet", "look up", "research", "search duckduckgo", "google"]):
                try:
                    from internet.duckduckgo_provider import DuckDuckGoProvider
                    ddg = DuckDuckGoProvider()
                    search_query = query
                    for prefix in ["search the web for", "search internet for", "look up", "search duckduckgo for", "research", "google"]:
                        if prefix in q_lower:
                            idx = q_lower.find(prefix) + len(prefix)
                            search_query = query[idx:].strip()
                            break
                    res = ddg.search(search_query)
                    # Cap results to avoid blowing out prompt budget
                    capped_res = res[:3] if isinstance(res, list) else res
                    return {"tool_selected": "web_search", "result": capped_res, "success": True, "message": f"Web search results for: {search_query}"}
                except Exception as ws_err:
                    return {"tool_selected": "web_search", "success": False, "error": str(ws_err)}

            # 5. Self-Modification / Evolution Check
                try:
                    from agi.self_modification_engine import get_self_modification_engine
                    sme = get_self_modification_engine()
                    return {"tool_selected": "self_modification", "result": {"status": "Standby for staging file specification"}, "success": True}
                except Exception as sme_err:
                    return {"tool_selected": "self_modification", "success": False, "error": str(sme_err)}

            # Default: no intrusive tool invocation needed for conversational turns
            return {"tool_selected": "none", "success": True, "note": "Standard conversational or reasoning turn."}

_global_tool_router = None
def get_autonomous_tool_router() -> AutonomousToolRouter:
    global _global_tool_router
    if _global_tool_router is None:
        _global_tool_router = AutonomousToolRouter()
    return _global_tool_router
