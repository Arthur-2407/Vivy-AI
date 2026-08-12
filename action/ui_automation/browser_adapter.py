"""
Vivy AI — Action System: Browser Adapter
=========================================
Implements UI automation via DOM semantics (Playwright/CDP) when available.
"""

from __future__ import annotations
from typing import Optional
from .base import UIAdapter, UIElement, UIState


class BrowserAdapter(UIAdapter):
    """
    DOM-first browser automation adapter.
    For this implementation, it's a stub that simulates DOM interaction.
    In a full deployment, this wraps Playwright or Selenium.
    """
    
    def __init__(self):
        self._connected = False
        self._url = ""
    
    def connect(self, target: str) -> bool:
        """Connect to a browser tab by URL or launch a new one."""
        self._url = target
        self._connected = True
        return True

    def get_state(self) -> UIState:
        """Capture DOM state and parse into semantic UI elements."""
        if not self._connected:
            return UIState("Browser", "", [])
            
        # Simulate DOM extraction of product elements (e.g., from Amazon/Flipkart)
        # In reality, this evaluates javascript to pull structured data.
        elements = [
            UIElement("prod_1", "Product A", "product_card", {"price": "$99", "rating": "4.5"}),
            UIElement("prod_2", "Product B", "product_card", {"price": "$129", "rating": "4.8"}),
        ]
        
        return UIState(
            app_name="Browser",
            url_or_path=self._url,
            elements=elements,
            raw_source="<html><body>...</body></html>",
            is_vision_fallback=False
        )

    def click(self, element: UIElement) -> bool:
        """Click an element using its DOM reference/selector."""
        print(f"[BrowserAdapter] Clicked element {element.element_id}")
        return True

    def type_text(self, element: UIElement, text: str) -> bool:
        """Type text into a DOM input."""
        print(f"[BrowserAdapter] Typed '{text}' into {element.element_id}")
        return True
