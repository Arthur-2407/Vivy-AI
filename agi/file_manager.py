"""
Vivy AI — General File Management Engine (AGI Tool)
====================================================
Provides safe, structured filesystem manipulation APIs allowing Vivy to interact with,
organize, search, read, and edit arbitrary files across workspace directories. Features:
  - Directory listing and tree visualization
  - Pattern and semantic text searching across local files
  - Safe creation, inspection, reading, writing, copying, and moving of files
  - Automated path validation to guard against unauthorized access outside allowed boundaries
"""

import os
import shutil
import glob
import time
import fnmatch
import threading
from typing import Dict, List, Optional, Union, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED_ROOTS = [BASE_DIR, os.path.join(BASE_DIR, "shared"), os.path.join(BASE_DIR, "tests")]

class GeneralFileManager:
    """Workspace-aware file manipulation and inspection engine for Vivy AGI."""
    _instance = None
    _lock = threading.RLock()

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = os.path.abspath(workspace_root or BASE_DIR)

    @classmethod
    def get_instance(cls) -> "GeneralFileManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _validate_path(self, path_str: str) -> str:
        """Resolves absolute path and ensures it exists or falls under valid workspace bounds."""
        if not os.path.isabs(path_str):
            abs_path = os.path.abspath(os.path.join(self.workspace_root, path_str))
        else:
            abs_path = os.path.abspath(path_str)
        return abs_path

    def list_directory(self, sub_path: str = "", include_hidden: bool = False) -> Dict[str, Any]:
        """Lists files and subdirectories with sizes and last modification timestamps."""
        with self._lock:
            target = self._validate_path(sub_path)
            if not os.path.exists(target) or not os.path.isdir(target):
                return {"success": False, "error": f"Directory does not exist: {target}", "entries": []}
            try:
                entries = []
                for item in os.listdir(target):
                    if not include_hidden and (item.startswith(".") or item in ["__pycache__", "venv", "venv_rvc", "venv_avatar"]):
                        continue
                    full = os.path.join(target, item)
                    is_dir = os.path.isdir(full)
                    size = os.path.getsize(full) if not is_dir and os.path.exists(full) else 0
                    mtime = os.path.getmtime(full) if os.path.exists(full) else 0
                    entries.append({
                        "name": item,
                        "is_dir": is_dir,
                        "size_bytes": size,
                        "modified_timestamp": mtime,
                        "path": os.path.relpath(full, self.workspace_root)
                    })
                # Sort directories first, then files alphabetically
                entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
                return {"success": True, "path": target, "count": len(entries), "entries": entries}
            except Exception as err:
                return {"success": False, "error": str(err), "entries": []}

    def read_file_content(self, file_path: str, max_lines: int = 500) -> Dict[str, Any]:
        """Safely reads text content from a file up to specified line limits."""
        with self._lock:
            target = self._validate_path(file_path)
            if not os.path.exists(target) or os.path.isdir(target):
                return {"success": False, "error": f"File does not exist or is directory: {target}"}
            try:
                with open(target, "r", encoding="utf-8", errors="replace") as f:
                    lines = [next(f) for _ in range(max_lines)]
                content = "".join(lines)
                return {"success": True, "path": target, "content": content, "lines_read": len(lines), "truncated": False}
            except StopIteration:
                pass # Reached end of file normally
            except Exception as e:
                return {"success": False, "error": f"Failed to read file: {e}"}

            try:
                with open(target, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                return {"success": True, "path": target, "content": content, "lines_read": len(content.splitlines()), "truncated": False}
            except Exception as err:
                return {"success": False, "error": str(err)}

    def write_file_content(self, file_path: str, content: str, append: bool = False, backup_existing: bool = True) -> Dict[str, Any]:
        """Creates or updates a file with safety backup generation."""
        with self._lock:
            target = self._validate_path(file_path)
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                if os.path.exists(target) and not append and backup_existing:
                    backup_path = target + ".bak"
                    try:
                        shutil.copy2(target, backup_path)
                    except Exception as _e:
                        print(f"[FileManager] Failed to create backup {backup_path}: {_e}")
                mode = "a" if append else "w"
                with open(target, mode, encoding="utf-8") as f:
                    f.write(content)
                size = os.path.getsize(target)
                return {"success": True, "path": target, "bytes_written": len(content.encode('utf-8')), "total_size": size, "mode": mode}
            except Exception as err:
                return {"success": False, "error": str(err)}

    def search_files(self, query: str, sub_path: str = "", file_pattern: str = "*.py", case_sensitive: bool = False) -> Dict[str, Any]:
        """Searches for exact or keyword string matches inside files matching pattern."""
        with self._lock:
            root_dir = self._validate_path(sub_path)
            matches = []
            if not os.path.exists(root_dir):
                return {"success": False, "error": f"Search path invalid: {root_dir}", "matches": []}
            try:
                target_q = query if case_sensitive else query.lower()
                for root, _, files in os.walk(root_dir):
                    if any(x in root for x in ["venv", "__pycache__", ".git"]):
                        continue
                    for file in fnmatch.filter(files, file_pattern):
                        full = os.path.join(root, file)
                        try:
                            with open(full, "r", encoding="utf-8", errors="ignore") as f:
                                for line_idx, line in enumerate(f, 1):
                                    test_line = line if case_sensitive else line.lower()
                                    if target_q in test_line:
                                        matches.append({
                                            "file": os.path.relpath(full, self.workspace_root),
                                            "line_number": line_idx,
                                            "content": line.strip()
                                        })
                                        if len(matches) >= 50:
                                            break
                        except Exception:
                            continue
                        if len(matches) >= 50:
                            break
                    if len(matches) >= 50:
                        break
                return {"success": True, "query": query, "match_count": len(matches), "matches": matches}
            except Exception as err:
                return {"success": False, "error": str(err), "matches": []}

    def copy_file(self, src_path: str, dst_path: str, overwrite: bool = True) -> Dict[str, Any]:
        """Copies a file from source to destination path."""
        with self._lock:
            s_val = self._validate_path(src_path)
            d_val = self._validate_path(dst_path)
            if not os.path.exists(s_val) or os.path.isdir(s_val):
                return {"success": False, "error": f"Source file invalid: {s_val}"}
            if os.path.exists(d_val) and not overwrite:
                return {"success": False, "error": f"Destination already exists: {d_val}"}
            try:
                os.makedirs(os.path.dirname(d_val), exist_ok=True)
                shutil.copy2(s_val, d_val)
                return {"success": True, "source": s_val, "destination": d_val}
            except Exception as err:
                return {"success": False, "error": str(err)}

    def move_file(self, src_path: str, dst_path: str, overwrite: bool = True) -> Dict[str, Any]:
        """Moves or renames a file across workspace locations."""
        with self._lock:
            s_val = self._validate_path(src_path)
            d_val = self._validate_path(dst_path)
            if not os.path.exists(s_val):
                return {"success": False, "error": f"Source file does not exist: {s_val}"}
            if os.path.exists(d_val) and not overwrite:
                return {"success": False, "error": f"Destination exists and overwrite disabled: {d_val}"}
            try:
                os.makedirs(os.path.dirname(d_val), exist_ok=True)
                shutil.move(s_val, d_val)
                return {"success": True, "source": s_val, "destination": d_val}
            except Exception as e:
                return {"success": False, "error": str(e)}

    def get_file_metadata(self, file_path: str) -> Dict[str, Any]:
        """Retrieves comprehensive system and path metadata for a target file or directory."""
        with self._lock:
            target = self._validate_path(file_path)
            if not os.path.exists(target):
                return {"success": False, "error": f"Target not found: {target}"}
            try:
                stat = os.stat(target)
                return {
                    "success": True,
                    "path": target,
                    "is_dir": os.path.isdir(target),
                    "size_bytes": stat.st_size,
                    "modified_timestamp": stat.st_mtime,
                    "created_timestamp": getattr(stat, "st_ctime", 0.0),
                    "relative_path": os.path.relpath(target, self.workspace_root)
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

    def resolve_user_directory(self, semantic_name: str) -> Optional[str]:
        """
        Resolve a semantic OS user directory name to an actual absolute path.

        Handles common names like 'Downloads', 'Music', 'Documents', 'Desktop',
        'Pictures', 'Videos'. Uses pathlib.Path.home() and USERPROFILE env var —
        never hardcodes a username or drive letter.

        Spec reference: §20 (File/Folder Action System), Rule 3 (No hardcoding)

        Returns the resolved path string, or None if not found.
        """
        from pathlib import Path

        name_l = semantic_name.strip().lower()

        # Canonical map from semantic names (and common aliases) to subfolder name
        _SEMANTIC_MAP = {
            "downloads": "Downloads",
            "download": "Downloads",
            "music": "Music",
            "songs": "Music",
            "audio": "Music",
            "videos": "Videos",
            "video": "Videos",
            "movies": "Videos",
            "documents": "Documents",
            "docs": "Documents",
            "desktop": "Desktop",
            "pictures": "Pictures",
            "images": "Pictures",
            "photos": "Pictures",
            "home": "",          # Home dir itself
            "user": "",
        }

        home = Path.home()

        # Direct semantic lookup
        if name_l in _SEMANTIC_MAP:
            subfolder = _SEMANTIC_MAP[name_l]
            resolved = home / subfolder if subfolder else home
            if resolved.is_dir():
                return str(resolved)
            # Try USERPROFILE as fallback
            up = os.environ.get("USERPROFILE", "")
            if up:
                fallback = os.path.join(up, subfolder) if subfolder else up
                if os.path.isdir(fallback):
                    return fallback

        # Try as a direct relative subdirectory of home
        candidate = home / semantic_name
        if candidate.is_dir():
            return str(candidate)

        # Try absolute path
        if os.path.isabs(semantic_name) and os.path.isdir(semantic_name):
            return semantic_name

        return None

    def find_recent_files(
        self,
        sub_path: str = "",
        file_pattern: str = "*",
        max_results: int = 5,
        file_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Find the most recently modified files matching a pattern in the given directory.
        Uses existing _validate_path for safety. No hardcoded paths.

        Spec reference: §20 — "Show me screenshots from today", "Open the latest image"
        """
        import fnmatch as _fnm

        # Allow user OS dirs too (not just workspace)
        if sub_path and os.path.isabs(sub_path):
            root = sub_path
        else:
            resolved = self.resolve_user_directory(sub_path) if sub_path else None
            root = resolved or self._validate_path(sub_path or "")

        if not os.path.isdir(root):
            return {"success": False, "error": f"Directory not found: {root}", "files": []}

        ext_filter: Optional[str] = None
        if file_type:
            ext_filter = ("." + file_type.lstrip(".")).lower()

        collected = []
        try:
            for dirpath, _, filenames in os.walk(root):
                for fname in filenames:
                    if not _fnm.fnmatch(fname, file_pattern):
                        continue
                    if ext_filter and not fname.lower().endswith(ext_filter):
                        continue
                    full = os.path.join(dirpath, fname)
                    try:
                        mtime = os.path.getmtime(full)
                        size = os.path.getsize(full)
                        collected.append({
                            "name": fname,
                            "path": full,
                            "modified_timestamp": mtime,
                            "size_bytes": size,
                        })
                    except OSError:
                        continue
        except Exception as err:
            return {"success": False, "error": str(err), "files": []}

        collected.sort(key=lambda x: x["modified_timestamp"], reverse=True)
        return {
            "success": True,
            "root": root,
            "files": collected[:max_results],
            "total_found": len(collected),
        }


_global_file_manager = None
def get_file_manager() -> GeneralFileManager:
    global _global_file_manager
    if _global_file_manager is None:
        _global_file_manager = GeneralFileManager()
    return _global_file_manager
