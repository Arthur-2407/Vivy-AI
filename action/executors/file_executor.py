"""
Vivy AI — Action System: File Executor
=======================================
Handles open-file, open-folder, search-files, and find-recent-files actions.
Wraps the existing agi/file_manager.py with OS-aware path expansion.

Security: uses GeneralFileManager._validate_path boundary for workspace files;
for OS user directories, uses the new resolve_user_directory() method.
No arbitrary shell execution. No hardcoded paths.

Spec reference: §20 (File/Folder Action System), §42 (Shell/OS Command Security)
"""

from __future__ import annotations

import os
import subprocess
import threading
from typing import Any, Dict, Optional

from action.intent_model import ActionResult, IntentModel, RiskLevel


class FileExecutor:
    """Executes file and folder actions."""

    _instance: Optional["FileExecutor"] = None
    _lock: threading.RLock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "FileExecutor":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ── Open file ─────────────────────────────────────────────────────────────

    def open_file(self, intent: IntentModel) -> ActionResult:
        """
        Open a file using the OS default application handler.
        Spec reference: §20
        """
        target = intent.target.strip()
        params = intent.parameters

        # If an absolute path was provided directly
        if os.path.isabs(target) and os.path.isfile(target):
            return self._launch_file(target, intent)

        # Resolve semantic directory
        from agi.file_manager import get_file_manager
        fm = get_file_manager()

        # Try user OS directories
        dir_path = fm.resolve_user_directory(target)
        if dir_path and os.path.isfile(dir_path):
            return self._launch_file(dir_path, intent)

        # Search for the file by name / pattern
        search_dir = params.get("search_dir", "")
        file_type = params.get("file_type", "")
        recent = params.get("recent", False)

        if recent or "latest" in target.lower() or "recent" in target.lower():
            result = fm.find_recent_files(
                sub_path=search_dir or "",
                file_type=file_type or "",
                max_results=5,
            )
            files = result.get("files", [])
            if files:
                best = files[0]
                return self._launch_file(best["path"], intent, note=f"(latest file found: {best['name']})")
            return ActionResult(
                success=False, domain="file", action="open", target=target,
                message=f"I couldn't find any recent {file_type or ''} files in {search_dir or 'your directories'}.",
                error="No matching files found",
            )

        # General file search
        search_result = fm.search_files(
            query=target,
            sub_path=search_dir or "",
            file_pattern=f"*{file_type}*" if file_type else "*",
        )
        matches = search_result.get("matches", [])
        if not matches:
            return ActionResult(
                success=False, domain="file", action="open", target=target,
                message=f"I couldn't find a file matching '{target}'.",
                error="File not found",
            )
        if len(matches) == 1:
            return self._launch_file(matches[0]["file"], intent)

        # Multiple matches — return as candidates for user selection (§28 clarification policy)
        from action.action_session import get_action_session, save_action_session
        session = get_action_session()
        session.set_candidates([
            {"_index": i + 1, "label": m["file"], "path": m["file"]}
            for i, m in enumerate(matches[:10])
        ])
        save_action_session(session)
        names = "\n".join(f"  {i+1}. {m['file']}" for i, m in enumerate(matches[:5]))
        return ActionResult(
            success=True, domain="file", action="open", target=target,
            message=f"I found {len(matches)} files matching '{target}'. Which one?\n{names}",
            candidates=session.candidates,
            requires_confirmation=False,
        )

    def _launch_file(self, path: str, intent: IntentModel, note: str = "") -> ActionResult:
        """Open file with OS default handler."""
        try:
            os.startfile(path)
            display = os.path.basename(path)
            msg = f"Opened '{display}'." + (f" {note}" if note else "")
            return ActionResult(
                success=True, domain="file", action="open", target=path,
                message=msg, verified=True,
                observation={"opened_path": path},
            )
        except Exception as err:
            return ActionResult(
                success=False, domain="file", action="open", target=path,
                message=f"I wasn't able to open '{os.path.basename(path)}'.",
                error=str(err),
            )

    # ── Open folder ───────────────────────────────────────────────────────────

    def open_folder(self, intent: IntentModel) -> ActionResult:
        """
        Open a folder in Windows Explorer.
        Spec reference: §20
        """
        target = intent.target.strip()
        from agi.file_manager import get_file_manager
        fm = get_file_manager()

        # Try semantic OS directory resolution
        resolved = fm.resolve_user_directory(target)
        if not resolved:
            # Try as literal path
            if os.path.isabs(target) and os.path.isdir(target):
                resolved = target
        if not resolved:
            return ActionResult(
                success=False, domain="file", action="open", target=target,
                message=f"I couldn't find a folder named '{target}'.",
                error="Folder not found",
            )

        try:
            subprocess.Popen(["explorer", resolved])
            return ActionResult(
                success=True, domain="file", action="open", target=resolved,
                message=f"Opened the '{os.path.basename(resolved)}' folder.",
                verified=True,
                observation={"opened_folder": resolved},
            )
        except Exception as err:
            return ActionResult(
                success=False, domain="file", action="open", target=resolved,
                message=f"I wasn't able to open the folder '{target}'.",
                error=str(err),
            )

    # ── Search files ──────────────────────────────────────────────────────────

    def search_files(self, intent: IntentModel) -> ActionResult:
        """
        Search for files matching criteria and return a candidate list.
        Spec reference: §20
        """
        from agi.file_manager import get_file_manager
        fm = get_file_manager()
        target = intent.target.strip()
        params = intent.parameters
        file_type = params.get("file_type", "")
        search_dir = params.get("search_dir", "")

        pattern = f"*.{file_type}" if file_type else "*"
        result = fm.search_files(
            query=target,
            sub_path=search_dir or "",
            file_pattern=pattern,
        )
        matches = result.get("matches", [])

        if not matches:
            return ActionResult(
                success=False, domain="file", action="search", target=target,
                message=f"I couldn't find any files matching '{target}'.",
                error="No matches found",
            )

        from action.action_session import get_action_session, save_action_session
        session = get_action_session()
        session.set_candidates([
            {"_index": i + 1, "label": m["file"], "path": m["file"]}
            for i, m in enumerate(matches[:10])
        ])
        save_action_session(session)
        names = "\n".join(f"  {i+1}. {m['file']}" for i, m in enumerate(matches[:5]))
        return ActionResult(
            success=True, domain="file", action="search", target=target,
            message=f"Found {len(matches)} file(s) matching '{target}':\n{names}",
            candidates=session.candidates,
        )

    def execute(self, intent: IntentModel) -> ActionResult:
        """Dispatch to the correct file action based on intent action verb."""
        action = intent.action.lower()
        if action in ("open",):
            if any(k in intent.target.lower() for k in ["folder", "directory", "dir"]):
                return self.open_folder(intent)
            return self.open_file(intent)
        if action in ("search", "find"):
            return self.search_files(intent)
        return ActionResult(
            success=False, domain="file", action=action, target=intent.target,
            message=f"I don't know how to '{action}' files yet.",
            error="Unsupported file action",
        )


def get_file_executor() -> FileExecutor:
    return FileExecutor.get_instance()
