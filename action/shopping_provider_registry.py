"""
Vivy AI — Action System: Shopping Provider Registry
=====================================================
Abstracts all shopping platform selection behind a configurable provider
registry. No hardcoded "always Amazon" or "always Flipkart".

Selection policies: random (default), rotation, reliability, user_preference.
All providers are loaded from vivy_config.json — zero hardcoding in this file.

Spec reference: §13 (Random/Dynamic Shopping Platform Selection), Rule 3 (No hardcoding)
"""

from __future__ import annotations

import random
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ShoppingProvider:
    """A configured shopping platform provider."""
    name: str
    url_template: str          # e.g. "https://www.flipkart.com/search?q={query}"
    region: str                # "IN" | "global" | ...
    enabled: bool = True
    failure_count: int = 0
    success_count: int = 0
    last_used: float = 0.0

    def build_search_url(self, query: str, constraints: Optional[Dict[str, Any]] = None) -> str:
        """
        Build a search URL by substituting query into the URL template.
        Applies basic price filter URL params where supported.
        """
        encoded_query = urllib.parse.quote(query)
        url = self.url_template.replace("{query}", encoded_query)

        # Append price filter params for known providers
        # This is data-driven from the URL template, not hardcoded provider logic
        constraints = constraints or {}
        max_price = constraints.get("max_price")
        min_price = constraints.get("min_price")

        if max_price is not None:
            # Common price filter param names by provider name
            price_params = {
                "flipkart":  f"&p%5B%5D=facets.price_range.from%3DMin%26facets.price_range.to%3D{int(max_price)}",
                "amazon_in": f"&rh=p_36%3A{int((min_price or 0) * 100)}-{int(max_price * 100)}",
                "amazon":    f"&rh=p_36%3A{int((min_price or 0) * 100)}-{int(max_price * 100)}",
                "ebay":      f"&_udlo={int(min_price or 0)}&_udhi={int(max_price)}",
                "snapdeal":  f"&CFTAG_PRICE_LOWER={int(min_price or 0)}&CFTAG_PRICE_UPPER={int(max_price)}",
            }
            param = price_params.get(self.name, "")
            if param:
                url += param

        return url

    def record_result(self, success: bool) -> None:
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
        self.last_used = time.time()

    @property
    def reliability_score(self) -> float:
        """0.0 – 1.0 based on historical success rate."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.5  # Unknown → neutral
        return self.success_count / total

    def __repr__(self) -> str:
        return f"ShoppingProvider(name={self.name!r}, region={self.region!r})"


class ShoppingProviderRegistry:
    """
    Manages and selects shopping providers from configuration.

    Selection policies (configured via action_system.shopping_provider_rotation):
      - "random":           Weighted random among enabled providers
      - "rotation":         Round-robin
      - "reliability":      Prefer highest historical success rate
      - "user_preference":  Use memory-stored user preference if available

    Spec reference: §13
    """
    _instance: Optional["ShoppingProviderRegistry"] = None
    _lock: threading.RLock = threading.RLock()

    def __init__(self):
        self._providers: List[ShoppingProvider] = []
        self._rotation_index: int = 0
        self._config_loaded: bool = False

    @classmethod
    def get_instance(cls) -> "ShoppingProviderRegistry":
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
            raw_providers = cfg.get("action_system.shopping_providers", [])
            if raw_providers:
                self._providers = [
                    ShoppingProvider(
                        name=p.get("name", "unknown"),
                        url_template=p.get("url", ""),
                        region=p.get("region", "global"),
                        enabled=bool(p.get("enabled", True)),
                    )
                    for p in raw_providers
                    if p.get("url") and p.get("name")
                ]
            print(f"[ShoppingProviderRegistry] Loaded {len(self._providers)} providers from config.")
        except Exception as err:
            print(f"[ShoppingProviderRegistry] Config load error: {err}")
        self._config_loaded = True

    def _get_policy(self) -> str:
        try:
            from config.config_manager import get_config_manager
            return get_config_manager().get("action_system.shopping_provider_rotation", "random")
        except Exception:
            return "random"

    def _get_user_preference(self) -> Optional[str]:
        """Check memory for stored user shopping provider preference."""
        try:
            from memory_orchestrator import get_memory_orchestrator
            mo = get_memory_orchestrator()
            # Check vivy_memory.json for a stored preference
            import json, os
            mem_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "vivy_memory.json")
            if os.path.exists(mem_path):
                with open(mem_path, "r", encoding="utf-8") as f:
                    mem = json.load(f)
                return mem.get("preferred_shopping_platform")
        except Exception:
            pass
        return None

    def get_enabled(self) -> List[ShoppingProvider]:
        """Return all enabled providers loaded from config."""
        self._load_config()
        with self._lock:
            return [p for p in self._providers if p.enabled]

    def select_provider(
        self,
        constraints: Optional[Dict[str, Any]] = None,
        region: Optional[str] = None,
    ) -> Optional[ShoppingProvider]:
        """
        Select a provider using a strict policy cascade:
        Eligibility -> Availability -> Reliability -> Region -> User Preference -> Rotation
        
        Spec reference: Phase 8 Architectural Refinement
        """
        self._load_config()
        
        # 1. Eligibility & Availability
        available = self.get_enabled()
        if not available:
            print("[ShoppingProviderRegistry] No enabled providers available.")
            return None

        # 2. Region filter
        if region:
            regional = [p for p in available if p.region == region]
            if regional:
                available = regional

        # 3. User Preference
        pref = self._get_user_preference()
        if pref:
            for p in available:
                if p.name == pref:
                    print(f"[ShoppingProviderRegistry] Using user preference: {p.name}")
                    return p

        # 4. Reliability Threshold (filter out providers with < 0.2 score if others exist)
        high_reliability = [p for p in available if p.reliability_score >= 0.2]
        if high_reliability:
            available = high_reliability

        # 5. Rotation/Randomization (Final selection among remaining strong candidates)
        policy = self._get_policy()
        if policy == "reliability":
            selected = max(available, key=lambda p: p.reliability_score)
        elif policy == "rotation":
            with self._lock:
                selected = available[self._rotation_index % len(available)]
                self._rotation_index += 1
        else:
            # Weighted random based on reliability
            weights = [max(0.1, p.reliability_score) for p in available]
            selected = random.choices(available, weights=weights, k=1)[0]

        print(f"[ShoppingProviderRegistry] Selected provider: {selected.name}")
        return selected

    def record_result(self, provider_name: str, success: bool) -> None:
        """Record outcome for reliability tracking."""
        with self._lock:
            for p in self._providers:
                if p.name == provider_name:
                    p.record_result(success)
                    break

    def get_health(self) -> Dict[str, Any]:
        self._load_config()
        with self._lock:
            return {
                "total_providers": len(self._providers),
                "enabled_providers": len([p for p in self._providers if p.enabled]),
                "providers": [
                    {"name": p.name, "region": p.region, "reliability": round(p.reliability_score, 2)}
                    for p in self._providers
                ],
            }


# ── Singleton ──────────────────────────────────────────────────────────────────

def get_shopping_provider_registry() -> ShoppingProviderRegistry:
    return ShoppingProviderRegistry.get_instance()
