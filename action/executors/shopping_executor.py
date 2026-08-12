"""
Vivy AI — Action System: Shopping Executor
==========================================
Handles product search, filter, open-product, recommend, and purchase actions.
Uses ShoppingProviderRegistry for dynamic provider selection.
Enforces HIGH_RISK gate on any purchase/checkout action.
Reads product candidates from screen via ObservationAdapter.

Spec reference: §12 (Shopping/Product Assistant), §13 (Dynamic Provider Selection),
                §14 (Constraint Extraction), §19 (Risk Classification),
                §38 (No false completion claims)
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from action.intent_model import ActionResult, IntentModel, RiskLevel


class ShoppingExecutor:
    """Executes shopping search, filter, select, recommend, and purchase actions."""

    _instance: Optional["ShoppingExecutor"] = None
    _lock: threading.RLock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "ShoppingExecutor":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ── Shop Search ───────────────────────────────────────────────────────────

    def shop_search(self, intent: IntentModel) -> ActionResult:
        """
        1. Select provider via ShoppingProviderRegistry
        2. Build search URL and open in browser
        3. Wait for page to load
        4. Capture visible product candidates via ObservationAdapter
        5. Apply constraint filters (ConstraintExtractor)
        6. Store in ActionSession.candidates
        7. Return structured result

        Spec reference: §12, §13, §14
        """
        query = intent.target.strip()
        constraints = intent.constraints

        # ── Provider selection ──────────────────────────────────────────────────
        from action.shopping_provider_registry import get_shopping_provider_registry
        registry = get_shopping_provider_registry()
        provider = registry.select_provider(constraints=constraints)

        if not provider:
            return ActionResult(
                success=False, domain="shopping", action="search", target=query,
                message="No shopping providers are configured. Please check vivy_config.json.",
                error="No providers available",
            )

        search_url = provider.build_search_url(query, constraints)

        # ── Open browser ─────────────────────────────────────────────────────────
        from action.executors.browser_executor import get_browser_executor
        browser_result = get_browser_executor().open_url(search_url)

        if not browser_result.success:
            registry.record_result(provider.name, False)
            return ActionResult(
                success=False, domain="shopping", action="search", target=query,
                message=f"I couldn't open {provider.name} for your search.",
                error=browser_result.error,
            )

        registry.record_result(provider.name, True)

        # ── Wait for page ─────────────────────────────────────────────────────────
        wait_secs = 3.0
        try:
            from config.config_manager import get_config_manager
            wait_secs = float(get_config_manager().get("action_system.observation_wait_seconds", 3.0))
        except Exception:
            pass
        time.sleep(wait_secs)

        # ── Capture product candidates via screen OCR ──────────────────────────
        candidates = self._capture_product_candidates(query, constraints)

        # ── Store in ActionSession ─────────────────────────────────────────────
        from action.action_session import get_action_session, save_action_session
        session = get_action_session()
        session.current_application = provider.name
        session.current_page = search_url
        session.constraints = constraints
        session.set_candidates(candidates)
        save_action_session(session)

        if candidates:
            summary = self._format_candidates_summary(candidates[:5], constraints)
            return ActionResult(
                success=True, domain="shopping", action="search", target=query,
                message=(f"I opened {provider.name} and found results for '{query}'.\n"
                         f"{summary}\n"
                         f"Say a number or name to open a product, or tell me your budget to filter."),
                candidates=candidates,
                observation={"provider": provider.name, "url": search_url},
                verified=True,
            )

        # No OCR candidates — page likely still loading or OCR not active
        return ActionResult(
            success=True, domain="shopping", action="search", target=query,
            message=(f"I opened {provider.name} for '{query}'. "
                     f"I wasn't able to read the product listings yet — "
                     f"the screen capture may not be active. "
                     f"You can tell me the number or name of what you want to open."),
            observation={"provider": provider.name, "url": search_url},
            verified=False,
        )

    def _capture_product_candidates(
        self, query: str, constraints: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Capture product candidates from the current screen using ObservationAdapter.
        Applies constraint filters via ConstraintExtractor.
        Spec reference: §12, §14, §26
        """
        try:
            from action.observation_adapter import get_observation_adapter
            obs = get_observation_adapter()
            ui_state = obs.capture_ui_state()
            ocr_text = ui_state.get("screen_text", "")

            if not ocr_text:
                return []

            candidates = obs.extract_product_candidates(ocr_text)

            if candidates and constraints.get("has_budget"):
                from action.constraint_extractor import get_constraint_extractor
                candidates = get_constraint_extractor().apply_to_candidates(candidates, constraints)

            # Re-index after filter
            for i, c in enumerate(candidates):
                c["_index"] = i + 1

            return candidates
        except Exception as err:
            print(f"[ShoppingExecutor] Product capture error: {err}")
            return []

    def _format_candidates_summary(
        self, candidates: List[Dict[str, Any]], constraints: Dict[str, Any]
    ) -> str:
        lines = []
        for c in candidates:
            idx = c.get("_index", "?")
            label = c.get("label", "Unknown product")
            price = c.get("price", "")
            rating = c.get("rating", "")
            parts = [f"{idx}. {label}"]
            if price:
                parts.append(f"— {price}")
            if rating:
                parts.append(f"★ {rating}")
            lines.append(" ".join(parts))
        return "\n".join(lines) if lines else "No products read from screen yet."

    # ── Shop Filter ───────────────────────────────────────────────────────────

    def shop_filter(self, intent: IntentModel) -> ActionResult:
        """
        Apply or update constraint filters to current candidates.
        Spec reference: §14
        """
        from action.action_session import get_action_session, save_action_session
        session = get_action_session()

        if not session.candidates:
            return ActionResult(
                success=False, domain="shopping", action="filter", target=intent.target,
                message="I don't have any product results to filter yet. Try searching first.",
                error="No candidates to filter",
            )

        # Merge new constraints with existing
        new_constraints = intent.constraints or {}
        session.constraints.update(new_constraints)

        from action.constraint_extractor import get_constraint_extractor
        filtered = get_constraint_extractor().apply_to_candidates(
            session.candidates, session.constraints
        )

        session.set_candidates(filtered)
        save_action_session(session)

        if not filtered:
            return ActionResult(
                success=False, domain="shopping", action="filter", target=intent.target,
                message=f"No products matched your filter. "
                        f"Budget: {session.constraints.get('max_price', 'any')} "
                        f"{session.constraints.get('currency', '')}.",
            )

        summary = self._format_candidates_summary(filtered[:5], session.constraints)
        budget_str = (f"under {session.constraints.get('max_price')} {session.constraints.get('currency', '')}"
                      if session.constraints.get("max_price") else "no budget set")
        return ActionResult(
            success=True, domain="shopping", action="filter", target=intent.target,
            message=f"Filtered to {len(filtered)} products ({budget_str}):\n{summary}",
            candidates=filtered,
            verified=True,
        )

    # ── Open Product ──────────────────────────────────────────────────────────

    def shop_open_product(self, intent: IntentModel) -> ActionResult:
        """
        Open a specific product from the current candidate list.
        Spec reference: §17 (Visual-based selection), §29 (Contextual follow-up)
        """
        from action.action_session import get_action_session, save_action_session
        session = get_action_session()

        ref = intent.target.strip()
        item = session.resolve_candidate_reference(ref)

        if not item:
            return ActionResult(
                success=False, domain="shopping", action="open", target=ref,
                message=f"I couldn't identify '{ref}' from the current product list. "
                        f"Try saying the number (e.g., 'open the second one').",
                error="Candidate not resolved",
            )

        product_url = item.get("url") or item.get("path", "")
        if not product_url:
            return ActionResult(
                success=False, domain="shopping", action="open", target=ref,
                message=f"I found '{item.get('label', ref)}' but don't have its URL to open.",
                error="No URL for candidate",
            )

        from action.executors.browser_executor import get_browser_executor
        result = get_browser_executor().open_url(product_url)
        session.selected_item = item
        save_action_session(session)

        if result.success:
            return ActionResult(
                success=True, domain="shopping", action="open", target=ref,
                message=f"Opened '{item.get('label', ref)}' — {item.get('price', '')}.",
                verified=result.verified,
                observation={"selected_item": item},
            )
        return ActionResult(
            success=False, domain="shopping", action="open", target=ref,
            message=f"I couldn't open the product page for '{item.get('label', ref)}'.",
            error=result.error,
        )

    # ── Recommend ─────────────────────────────────────────────────────────────

    def shop_recommend(self, intent: IntentModel) -> ActionResult:
        """
        Rank and explain product candidates based on observed facts only.
        Uses RecommendationEngine.recommend_products().
        Spec reference: §12, §38 (only report observed info, never fabricate)
        """
        from action.action_session import get_action_session
        session = get_action_session()

        if not session.candidates:
            return ActionResult(
                success=False, domain="shopping", action="recommend", target=intent.target,
                message="I don't have any products to recommend yet. Try searching first.",
                error="No candidates",
            )

        try:
            from recommendation_engine import get_recommendation_engine
            ranked = get_recommendation_engine().recommend_products(
                session.candidates, session.constraints
            )
        except Exception:
            ranked = session.candidates  # Fallback: existing order

        ranked = ranked[:5]
        if not ranked:
            return ActionResult(
                success=False, domain="shopping", action="recommend", target=intent.target,
                message="I wasn't able to rank the products.",
            )

        # Build an honest recommendation summary from observed data only
        lines = []
        for i, c in enumerate(ranked):
            label = c.get("label", "Unknown")
            price = c.get("price", "")
            rating = c.get("rating", "")
            parts = [f"{i+1}. {label}"]
            if price:
                parts.append(f"({price})")
            if rating:
                parts.append(f"★ {rating}")
            lines.append(" ".join(parts))

        top = ranked[0]
        best_name = top.get("label", "the first option")
        best_price = top.get("price", "")
        rationale = f"Based on the prices and ratings I observed, I'd suggest {best_name}"
        if best_price:
            rationale += f" at {best_price}"
        rationale += "."

        return ActionResult(
            success=True, domain="shopping", action="recommend", target=intent.target,
            message=f"{rationale}\n\nAll options I found:\n" + "\n".join(lines),
            candidates=ranked,
            verified=True,
        )

    # ── Purchase (HIGH RISK gate) ──────────────────────────────────────────────

    def shop_purchase(self, intent: IntentModel) -> ActionResult:
        """
        Purchase is HIGH_RISK — always requires explicit user confirmation.
        This method raises the confirmation gate, never proceeds unilaterally.
        Spec reference: §19 (Risk Classification), §55 (User Confirmation)
        """
        from action.action_session import get_action_session, save_action_session
        session = get_action_session()
        item = session.selected_item or (session.candidates[0] if session.candidates else None)
        item_name = item.get("label", intent.target) if item else intent.target
        price = item.get("price", "unknown price") if item else "unknown price"

        confirmation_payload = {
            "action": "purchase",
            "item": item,
            "item_name": item_name,
            "price": price,
            "risk_level": RiskLevel.HIGH_RISK.value,
            "message": (f"This will proceed to checkout for '{item_name}' ({price}). "
                        f"This is a financial transaction. Are you sure?"),
        }

        session.set_pending_confirmation(confirmation_payload)
        save_action_session(session)

        return ActionResult(
            success=False, domain="shopping", action="purchase", target=intent.target,
            message=(f"To buy '{item_name}' ({price}), I need your explicit confirmation. "
                     f"Say 'yes, proceed' or 'confirm purchase' to continue. "
                     f"Say 'cancel' to stop."),
            requires_confirmation=True,
            confirmation_payload=confirmation_payload,
        )

    def execute(self, intent: IntentModel) -> ActionResult:
        action = intent.action.lower()
        if action in ("search", "find", "buy", "open") and intent.domain == "shopping":
            # "buy" without a specific product = search first
            if action == "buy" and not intent.parameters.get("product_selected"):
                return self.shop_search(intent)
            return self.shop_search(intent)
        if action in ("filter", "apply", "budget"):
            return self.shop_filter(intent)
        if action in ("select", "view") and intent.domain == "shopping":
            return self.shop_open_product(intent)
        if action in ("recommend", "suggest", "compare"):
            return self.shop_recommend(intent)
        if action in ("purchase", "checkout", "pay"):
            return self.shop_purchase(intent)
        return ActionResult(
            success=False, domain="shopping", action=action, target=intent.target,
            message=f"I don't know how to '{action}' for shopping.",
            error="Unsupported shopping action",
        )


def get_shopping_executor() -> ShoppingExecutor:
    return ShoppingExecutor.get_instance()
