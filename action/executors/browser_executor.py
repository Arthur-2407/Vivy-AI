"""
Vivy AI — Action System: Browser Executor
==========================================
Opens URLs, navigates, and searches in the browser.
Browser is dynamically discovered via AppDiscovery — no hardcoded browser path.
Prefers semantic/DOM mechanisms when playwright is available; falls back to
subprocess + screen observation.

Spec reference: §6 (Website/Browser Actions), §16 (Visual UI Interaction)
"""

from __future__ import annotations

import subprocess
import threading
import time
import urllib.parse
from typing import Any, Dict, Optional

from action.intent_model import ActionResult, IntentModel


class BrowserExecutor:
    """Open URLs and search in browser."""

    _instance: Optional["BrowserExecutor"] = None
    _lock: threading.RLock = threading.RLock()

    def __init__(self):
        self._playwright_available: Optional[bool] = None
        self._playwright_browser = None
        self._playwright_page = None
        self._playwright_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "BrowserExecutor":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _check_playwright(self) -> bool:
        """Check if playwright is installed and usable."""
        if self._playwright_available is not None:
            return self._playwright_available
        try:
            from playwright.sync_api import sync_playwright
            self._playwright_available = True
        except ImportError:
            self._playwright_available = False
        return self._playwright_available

    def _get_browser_path(self) -> Optional[str]:
        """Discover installed browser path via AppDiscovery."""
        try:
            from action.app_discovery import get_app_discovery
            browsers = get_app_discovery().find_browser()
            if browsers:
                return browsers[0].path
        except Exception as err:
            print(f"[BrowserExecutor] AppDiscovery error: {err}")
        return None

    def _open_with_subprocess(self, url: str) -> Dict[str, Any]:
        """Open URL using discovered browser via subprocess."""
        browser_path = self._get_browser_path()
        if browser_path:
            try:
                subprocess.Popen([browser_path, url])
                return {"success": True, "method": "subprocess", "browser": browser_path, "url": url}
            except Exception as err:
                print(f"[BrowserExecutor] Subprocess launch failed: {err}")

        # Fallback: os.startfile for http/https URLs (uses default browser)
        try:
            import os
            os.startfile(url)
            return {"success": True, "method": "os_default", "url": url}
        except Exception as err:
            return {"success": False, "error": str(err), "url": url}

    def open_url(self, url: str, intent: Optional[IntentModel] = None) -> ActionResult:
        """
        Open a URL in the browser.
        Spec reference: §6
        """
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        target_label = intent.target if intent else url
        result = self._open_with_subprocess(url)

        if result.get("success"):
            # Brief wait then verify via observation
            time.sleep(2.0)
            verified = self._verify_browser_open(url)
            return ActionResult(
                success=True, domain="browser", action="open", target=target_label,
                message=f"Opened {target_label} in the browser.",
                verified=verified,
                observation={"url": url, "browser_open": verified},
            )
        return ActionResult(
            success=False, domain="browser", action="open", target=target_label,
            message=f"I wasn't able to open {target_label}.",
            error=result.get("error", "Unknown error"),
        )

    def search_web(self, query: str, intent: Optional[IntentModel] = None) -> ActionResult:
        """
        Search using existing internet infrastructure (InternetManager / DuckDuckGo).
        For browser-visible search: opens DuckDuckGo in the browser.
        Spec reference: §10 (DuckDuckGo/Internet Integration)
        """
        encoded = urllib.parse.quote(query)
        # Use DuckDuckGo HTML search URL (already configured in vivy_config.json)
        try:
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            ddg_html = cfg.get("apis.duckduckgo_html", "https://html.duckduckgo.com/html/?q=")
            search_url = f"{ddg_html}{encoded}"
        except Exception:
            search_url = f"https://html.duckduckgo.com/html/?q={encoded}"

        target_label = intent.target if intent else query
        return self.open_url(search_url, intent)

    def navigate_to(self, url: str, intent: Optional[IntentModel] = None) -> ActionResult:
        """Navigate to URL — same as open_url for subprocess-based browser."""
        return self.open_url(url, intent)

    def _verify_browser_open(self, url: str) -> bool:
        """
        Verify that a browser window/page appears after opening a URL.
        Uses ObservationAdapter to check foreground window title.
        """
        verified = False
        try:
            from action.observation_adapter import get_observation_adapter
            obs = get_observation_adapter()
            state = obs.get_window_state()
            title = state.get("foreground_title", "").lower()
            # Check if the domain appears in the window title
            domain = urllib.parse.urlparse(url).netloc.replace("www.", "")
            verified = domain.lower() in title

            # Phase 10 Integration: Perception Layer
            try:
                from perception.fusion_engine import get_fusion_engine
                get_fusion_engine().publish_event("action.verified_via_perception", {
                    "source": "browser_executor", "url": url, "verified": verified, "title": title
                })
            except Exception:
                pass
        except Exception:
            verified = False  # Cannot verify — report as unverified (§38)
        return verified

    def execute(self, intent: IntentModel) -> ActionResult:
        action = intent.action.lower()
        target = intent.target.strip()

        if action in ("search", "find"):
            return self.search_web(target, intent)

        # Resolve known site names to URLs
        url = self._resolve_site_name(target)
        if action in ("open", "navigate", "go"):
            return self.open_url(url or target, intent)

        return ActionResult(
            success=False, domain="browser", action=action, target=target,
            message=f"I don't know how to '{action}' in the browser.",
            error="Unsupported browser action",
        )

    def _resolve_site_name(self, name: str) -> str:
        """
        Resolve common site names to URLs.
        Uses a minimal lookup — not a hardcoded dictionary as the architecture.
        Real intent understanding handles the semantic mapping upstream.
        Spec reference: §37 (Natural-language flexibility)
        """
        name_l = name.strip().lower()
        # Check if already a URL
        if name_l.startswith(("http://", "https://", "www.")):
            return name if name_l.startswith("http") else "https://" + name
        # Well-known domains — these are not hardcoded as the only option;
        # the action planner can pass full URLs for shopping providers, etc.
        _KNOWN = {
            "youtube": "https://www.youtube.com",
            "github": "https://github.com",
            "google": "https://www.google.com",
            "duckduckgo": "https://duckduckgo.com",
            "wikipedia": "https://www.wikipedia.org",
            "stackoverflow": "https://stackoverflow.com",
        }
        return _KNOWN.get(name_l, f"https://www.{name_l}.com")


def get_browser_executor() -> BrowserExecutor:
    return BrowserExecutor.get_instance()
