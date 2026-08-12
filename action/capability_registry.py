"""
Vivy AI — Action System: Capability Registry
=============================================
Plugin-style registry of executable capabilities. Each Capability has a
name, domain, risk level, executor callable, verifier callable, and
fallback policy. Adding a new capability requires only registering a
Capability object — the core engine does not change.

Spec reference: §24 (Capability Registry), §44 (Plugin/Skill Extensibility)
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from action.intent_model import RiskLevel


@dataclass
class Capability:
    """
    A single registered action capability.
    Spec reference: §24
    """
    name:        str                                # Unique identifier e.g. "play_local_media"
    domain:      str                                # ActionDomain value
    action:      str                                # ActionVerb value (or alias set)
    description: str                                # Human-readable description
    parameters:  Dict[str, Any] = field(default_factory=dict)   # Expected parameters schema
    prerequisites: List[str] = field(default_factory=list)      # Prerequisite capability names
    risk_level:  str = RiskLevel.LOW_RISK.value
    executor:    Optional[Callable] = None          # Callable: (intent, session) → ActionResult
    verifier:    Optional[Callable] = None          # Callable: (observation) → bool
    fallback:    Optional[str] = None               # Fallback capability name
    availability_check: Optional[Callable] = None  # Callable: () → bool

    def is_available(self) -> bool:
        if self.availability_check is None:
            return True
        try:
            return bool(self.availability_check())
        except Exception as err:
            print(f"[CapabilityRegistry] Availability check failed for '{self.name}': {err}")
            return False

    def __repr__(self) -> str:
        return (f"Capability(name={self.name!r}, domain={self.domain!r}, "
                f"action={self.action!r}, risk={self.risk_level})")


class CapabilityRegistry:
    """
    Thread-safe registry of all Vivy action capabilities.
    Spec reference: §24, §44
    """
    _instance: Optional["CapabilityRegistry"] = None
    _lock: threading.RLock = threading.RLock()

    def __init__(self):
        self._capabilities: Dict[str, Capability] = {}
        self._domain_index: Dict[str, List[str]] = {}  # domain → [capability names]
        self._action_index: Dict[str, List[str]] = {}  # action → [capability names]

    @classmethod
    def get_instance(cls) -> "CapabilityRegistry":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ── Registration ─────────────────────────────────────────────────────────

    def register(self, capability: Capability) -> None:
        """Register a capability. Overwrites any existing with same name."""
        with self._lock:
            self._capabilities[capability.name] = capability

            # Index by domain
            domain_caps = self._domain_index.setdefault(capability.domain, [])
            if capability.name not in domain_caps:
                domain_caps.append(capability.name)

            # Index by action (support comma-separated action aliases)
            for action_alias in capability.action.split(","):
                action_alias = action_alias.strip()
                action_caps = self._action_index.setdefault(action_alias, [])
                if capability.name not in action_caps:
                    action_caps.append(capability.name)

        print(f"[CapabilityRegistry] Registered capability: '{capability.name}' "
              f"(domain={capability.domain}, action={capability.action}, risk={capability.risk_level})")

    def unregister(self, name: str) -> bool:
        """Unregister a capability by name. Returns True if found and removed."""
        with self._lock:
            cap = self._capabilities.pop(name, None)
            if cap is None:
                return False
            # Clean indices
            self._domain_index.get(cap.domain, []).remove(name) if name in self._domain_index.get(cap.domain, []) else None
            for action_alias in cap.action.split(","):
                lst = self._action_index.get(action_alias.strip(), [])
                if name in lst:
                    lst.remove(name)
            return True

    # ── Discovery ─────────────────────────────────────────────────────────────

    def discover(
        self,
        domain: str,
        action: str,
        check_availability: bool = True,
    ) -> Optional[Capability]:
        """
        Find the best matching available capability for a given domain + action.
        Spec reference: §24
        """
        with self._lock:
            candidates: List[Capability] = []

            # Direct name lookup: "domain_action" convention
            direct_key = f"{domain}_{action}"
            if direct_key in self._capabilities:
                candidates.append(self._capabilities[direct_key])

            # Domain index
            for cap_name in self._domain_index.get(domain, []):
                cap = self._capabilities.get(cap_name)
                if cap and cap not in candidates:
                    for alias in cap.action.split(","):
                        if alias.strip() == action:
                            candidates.append(cap)
                            break

            # Action index fallback
            if not candidates:
                for cap_name in self._action_index.get(action, []):
                    cap = self._capabilities.get(cap_name)
                    if cap and cap not in candidates:
                        candidates.append(cap)

            if not candidates:
                return None

            # Filter by availability
            if check_availability:
                candidates = [c for c in candidates if c.is_available()]

            return candidates[0] if candidates else None

    def discover_by_name(self, name: str) -> Optional[Capability]:
        with self._lock:
            return self._capabilities.get(name)

    def list_all(self) -> List[Capability]:
        with self._lock:
            return list(self._capabilities.values())

    def list_by_domain(self, domain: str) -> List[Capability]:
        with self._lock:
            return [
                self._capabilities[n]
                for n in self._domain_index.get(domain, [])
                if n in self._capabilities
            ]

    def count(self) -> int:
        with self._lock:
            return len(self._capabilities)

    def check_availability(self, name: str) -> bool:
        cap = self.discover_by_name(name)
        return cap.is_available() if cap else False

    def get_health(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "registered_capabilities": self.count(),
                "domains": list(self._domain_index.keys()),
                "capabilities": [c.name for c in self._capabilities.values()],
            }


# ── Singleton accessor ─────────────────────────────────────────────────────────

def get_capability_registry() -> CapabilityRegistry:
    return CapabilityRegistry.get_instance()


# ── Built-in capability registration (called from action/__init__.py) ─────────

def _register_builtin_capabilities(registry: CapabilityRegistry) -> None:
    """
    Register all built-in capabilities.
    Each executor is imported lazily to avoid circular dependencies and allow
    the system to start even if an executor's optional dependency is missing.
    Spec reference: §24, §5 (Core Capabilities), §6 (Browser), §12 (Shopping)
    """

    # ── Media capabilities ────────────────────────────────────────────────────
    def _play_local_available() -> bool:
        try:
            from action.media_resolver import get_media_resolver
            return True
        except Exception:
            return False

    registry.register(Capability(
        name="play_local_media",
        domain="media",
        action="play,find,search",
        description="Search local filesystem for audio/video and play using OS default handler",
        risk_level=RiskLevel.LOW_RISK.value,
        availability_check=_play_local_available,
        fallback="play_online_media",
    ))

    registry.register(Capability(
        name="play_online_media",
        domain="media",
        action="play,search",
        description="Search online (YouTube/streaming) for audio/video and open in browser",
        risk_level=RiskLevel.LOW_RISK.value,
        fallback=None,
    ))

    registry.register(Capability(
        name="adjust_volume",
        domain="device",
        action="adjust,set",
        description="Adjust system or application audio volume",
        risk_level=RiskLevel.LOW_RISK.value,
    ))

    # ── File capabilities ─────────────────────────────────────────────────────
    registry.register(Capability(
        name="open_file",
        domain="file",
        action="open",
        description="Open a file using the OS default application handler",
        risk_level=RiskLevel.LOW_RISK.value,
        fallback=None,
    ))

    registry.register(Capability(
        name="open_folder",
        domain="file",
        action="open,list",
        description="Open a folder in Windows Explorer",
        risk_level=RiskLevel.LOW_RISK.value,
    ))

    registry.register(Capability(
        name="search_files",
        domain="file",
        action="search,find",
        description="Search for files matching criteria (name, type, date) in user filesystem",
        risk_level=RiskLevel.LOW_RISK.value,
    ))

    # ── Application capabilities ──────────────────────────────────────────────
    registry.register(Capability(
        name="open_app",
        domain="app",
        action="open,launch,start",
        description="Discover and launch an installed application",
        risk_level=RiskLevel.LOW_RISK.value,
    ))

    registry.register(Capability(
        name="close_app",
        domain="app",
        action="close,quit,exit",
        description="Close a running application",
        risk_level=RiskLevel.MEDIUM_RISK.value,
    ))

    registry.register(Capability(
        name="switch_app",
        domain="app",
        action="switch,focus,bring",
        description="Switch focus to a running application",
        risk_level=RiskLevel.LOW_RISK.value,
    ))

    # ── Browser capabilities ──────────────────────────────────────────────────
    registry.register(Capability(
        name="open_url",
        domain="browser",
        action="open,navigate,go",
        description="Open a URL in the discovered browser",
        risk_level=RiskLevel.LOW_RISK.value,
    ))

    registry.register(Capability(
        name="search_in_browser",
        domain="browser",
        action="search,find",
        description="Perform a web search in the browser via existing internet infrastructure",
        risk_level=RiskLevel.LOW_RISK.value,
    ))

    # ── Shopping capabilities ─────────────────────────────────────────────────
    registry.register(Capability(
        name="shop_search",
        domain="shopping",
        action="search,find,buy,open",
        description="Open a shopping provider and search for a product",
        risk_level=RiskLevel.LOW_RISK.value,
        fallback=None,
    ))

    registry.register(Capability(
        name="shop_filter",
        domain="shopping",
        action="filter,apply,budget",
        description="Apply constraints (budget, brand, quality) to current shopping results",
        risk_level=RiskLevel.LOW_RISK.value,
    ))

    registry.register(Capability(
        name="shop_open_product",
        domain="shopping",
        action="open,select,view",
        description="Open a specific product page from current candidates",
        risk_level=RiskLevel.LOW_RISK.value,
    ))

    registry.register(Capability(
        name="shop_recommend",
        domain="shopping",
        action="recommend,suggest,compare",
        description="Rank and explain product candidates based on observed facts",
        risk_level=RiskLevel.LOW_RISK.value,
    ))

    registry.register(Capability(
        name="shop_purchase",
        domain="shopping",
        action="purchase,buy,checkout,pay",
        description="Proceed to checkout / purchase (HIGH RISK — requires explicit confirmation)",
        risk_level=RiskLevel.HIGH_RISK.value,
        prerequisites=["shop_open_product"],
    ))

    # ── Device capabilities ───────────────────────────────────────────────────
    registry.register(Capability(
        name="inspect_devices",
        domain="device",
        action="list,inspect,find",
        description="List connected audio, display, and peripheral devices",
        risk_level=RiskLevel.LOW_RISK.value,
    ))

    print(f"[CapabilityRegistry] Built-in capabilities registered: {registry.count()}")
