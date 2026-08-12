"""
Vivy AI — Action System: Application Discovery
================================================
Dynamically discovers installed applications using an extensible
provider architecture (Start Menu, Registry, PATH, Configured overrides).

Spec reference: Phase 8 Architectural Refinement (Provider Pattern)
"""

from __future__ import annotations

import os
import sys
import glob
import time
import threading
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from abc import ABC, abstractmethod


@dataclass
class AppInfo:
    """Represents a discovered application."""
    name: str                    # Display name (from shortcut or exe stem)
    path: str                    # Absolute path to executable
    aliases: List[str] = field(default_factory=list)   # Alternative names / search keywords
    description: str = ""
    source: str = "unknown"      # E.g., "start_menu", "registry", "path", "known_apps"

    def __repr__(self) -> str:
        return f"AppInfo(name={self.name!r}, path={self.path!r})"


# ─── PROVIDER ABSTRACTIONS ─────────────────────────────────────────────────────

class ApplicationProvider(ABC):
    """Base class for all application discovery providers."""
    @abstractmethod
    def discover(self) -> List[AppInfo]:
        """Returns a list of applications discovered by this provider."""
        pass


class ConfiguredProvider(ApplicationProvider):
    """Loads explicit application paths from vivy_config.json."""
    def discover(self) -> List[AppInfo]:
        apps: List[AppInfo] = []
        try:
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            known_apps = cfg.get("action_system.known_apps", {}) or {}
            for name, path in known_apps.items():
                if os.path.isfile(path):
                    apps.append(AppInfo(
                        name=name,
                        path=path,
                        aliases=[name.lower()],
                        source="configured",
                    ))
        except Exception:
            pass
        return apps


class StartMenuProvider(ApplicationProvider):
    """Discovers Windows Start Menu shortcut targets."""
    def discover(self) -> List[AppInfo]:
        apps: List[AppInfo] = []
        search_dirs = []

        # Per-user Start Menu
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            search_dirs.append(os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs"))

        # System-wide Start Menu
        programdata = os.environ.get("PROGRAMDATA", "C:\\ProgramData")
        if programdata:
            search_dirs.append(os.path.join(programdata, "Microsoft", "Windows", "Start Menu", "Programs"))

        for search_dir in search_dirs:
            if not os.path.isdir(search_dir):
                continue
            for lnk in glob.glob(os.path.join(search_dir, "**", "*.lnk"), recursive=True):
                try:
                    # Resolve .lnk target via PowerShell
                    result = subprocess.run(
                        ["powershell", "-Command",
                         f"(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}').TargetPath"],
                        capture_output=True, text=True, timeout=2
                    )
                    target = result.stdout.strip()
                    if target and os.path.isfile(target) and target.lower().endswith(".exe"):
                        stem = Path(lnk).stem
                        apps.append(AppInfo(
                            name=stem,
                            path=target,
                            aliases=[stem.lower(), Path(target).stem.lower()],
                            source="start_menu",
                        ))
                except Exception:
                    continue
        return apps


class RegistryProvider(ApplicationProvider):
    """Discovers apps registered in Windows App Paths registry keys."""
    def discover(self) -> List[AppInfo]:
        apps: List[AppInfo] = []
        try:
            import winreg
            reg_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    key = winreg.OpenKey(hive, reg_path)
                    i = 0
                    while True:
                        try:
                            sub_name = winreg.EnumKey(key, i)
                            sub_key = winreg.OpenKey(key, sub_name)
                            try:
                                exe_path, _ = winreg.QueryValueEx(sub_key, "")
                                exe_path = exe_path.strip().strip('"')
                                if exe_path and os.path.isfile(exe_path):
                                    stem = Path(sub_name).stem
                                    apps.append(AppInfo(
                                        name=stem,
                                        path=exe_path,
                                        aliases=[stem.lower(), Path(exe_path).stem.lower()],
                                        source="registry",
                                    ))
                            except Exception:
                                pass
                            finally:
                                winreg.CloseKey(sub_key)
                            i += 1
                        except OSError:
                            break
                    winreg.CloseKey(key)
                except Exception:
                    continue
        except ImportError:
            pass  # Not on Windows
        return apps


class PATHProvider(ApplicationProvider):
    """Discovers executables available in the system PATH."""
    def discover(self) -> List[AppInfo]:
        apps: List[AppInfo] = []
        seen: set = set()
        path_dirs = os.environ.get("PATH", "").split(os.pathsep)

        for d in path_dirs:
            if not os.path.isdir(d):
                continue
            try:
                for f in os.listdir(d):
                    if not f.lower().endswith(".exe"):
                        continue
                    full = os.path.join(d, f)
                    if full in seen:
                        continue
                    seen.add(full)
                    stem = Path(f).stem
                    apps.append(AppInfo(
                        name=stem,
                        path=full,
                        aliases=[stem.lower()],
                        source="path",
                    ))
            except PermissionError:
                continue
        return apps


# ─── ORCHESTRATOR ──────────────────────────────────────────────────────────────

class AppDiscovery:
    """
    Aggregates application discovery across multiple Extensible Providers.
    Results are cached with a configurable TTL.
    """
    _instance: Optional["AppDiscovery"] = None
    _lock: threading.RLock = threading.RLock()

    def __init__(self):
        self._cache: List[AppInfo] = []
        self._cache_time: float = 0.0
        self._cache_ttl: float = 300.0   # Updated from config on first call
        self._config_loaded = False

        # Register providers in priority order
        self._providers: List[ApplicationProvider] = [
            ConfiguredProvider(),
            StartMenuProvider(),
            RegistryProvider(),
            PATHProvider()
        ]

    @classmethod
    def get_instance(cls) -> "AppDiscovery":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _load_config(self) -> None:
        if self._config_loaded:
            return
        try:
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            self._cache_ttl = float(cfg.get("action_system.app_discovery_cache_ttl_seconds", 300))
        except Exception:
            pass
        self._config_loaded = True

    def _refresh_cache(self) -> None:
        """Rebuild app cache from all registered providers."""
        self._load_config()
        all_apps: List[AppInfo] = []
        seen_paths: set = set()

        for provider in self._providers:
            for app in provider.discover():
                if app.path not in seen_paths:
                    seen_paths.add(app.path)
                    all_apps.append(app)

        with self._lock:
            self._cache = all_apps
            self._cache_time = time.time()

        print(f"[AppDiscovery] Discovered {len(all_apps)} applications via providers.")

    def _ensure_cache(self) -> None:
        self._load_config()
        with self._lock:
            stale = (time.time() - self._cache_time) > self._cache_ttl
        if stale or not self._cache:
            self._refresh_cache()

    # ── Public interface ───────────────────────────────────────────────────────

    def find(self, name: str) -> List[AppInfo]:
        """
        Find applications matching a name or alias.
        Returns a ranked list — exact name matches first, then partial.
        """
        self._ensure_cache()
        name_l = name.strip().lower()

        exact: List[AppInfo] = []
        partial: List[AppInfo] = []

        with self._lock:
            for app in self._cache:
                all_names = [app.name.lower()] + [a.lower() for a in app.aliases]
                if name_l in all_names:
                    exact.append(app)
                elif any(name_l in n or n in name_l for n in all_names):
                    partial.append(app)

        return exact + partial

    def find_browser(self) -> List[AppInfo]:
        """
        Find installed browsers. Checks user config preferred_browser first,
        then falls back to browser_candidates list from config.
        """
        try:
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            preferred = cfg.get("action_system.preferred_browser", "")
            candidates = cfg.get("action_system.browser_candidates",
                                 ["chrome", "firefox", "msedge", "brave", "opera"])
        except Exception:
            preferred = ""
            candidates = ["chrome", "firefox", "msedge", "brave", "opera"]

        if preferred:
            results = self.find(preferred)
            if results:
                return results

        all_browsers: List[AppInfo] = []
        for name in candidates:
            found = self.find(name)
            for app in found:
                if app not in all_browsers:
                    all_browsers.append(app)

        return all_browsers

    def get_all(self) -> List[AppInfo]:
        self._ensure_cache()
        with self._lock:
            return list(self._cache)

    def invalidate_cache(self) -> None:
        with self._lock:
            self._cache_time = 0.0


# ── Singleton ──────────────────────────────────────────────────────────────────

def get_app_discovery() -> AppDiscovery:
    return AppDiscovery.get_instance()
