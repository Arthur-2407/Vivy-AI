"""
Vivy AI — Action System: UI Automation Package
===============================================
Abstracts UI automation to prioritize DOM/accessibility over OCR.
Includes BrowserAdapter, Win32Adapter, and VisionFallbackAdapter.
"""

from .base import UIAdapter, UIElement, UIState
from .browser_adapter import BrowserAdapter
from .vision_fallback_adapter import VisionFallbackAdapter

__all__ = ["UIAdapter", "UIElement", "UIState", "BrowserAdapter", "VisionFallbackAdapter"]
