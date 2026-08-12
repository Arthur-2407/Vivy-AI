"""
Vivy AI — Action System: UI Automation Base
============================================
Defines the abstraction for interacting with UI elements via DOM/Accessibility,
with a fallback to visual/OCR.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from abc import ABC, abstractmethod


@dataclass
class UIElement:
    """Represents an interactive element in a UI."""
    element_id: str
    label: str
    element_type: str = "unknown"  # 'button', 'link', 'input', 'product_card'
    properties: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0


@dataclass
class UIState:
    """Represents a snapshot of the UI."""
    app_name: str
    url_or_path: str
    elements: List[UIElement] = field(default_factory=list)
    raw_source: str = ""  # DOM or accessibility tree
    is_vision_fallback: bool = False


class UIAdapter(ABC):
    """Base class for UI automation adapters."""
    
    @abstractmethod
    def connect(self, target: str) -> bool:
        """Connect to the target application or browser."""
        pass

    @abstractmethod
    def get_state(self) -> UIState:
        """Capture the current UI state."""
        pass

    @abstractmethod
    def click(self, element: UIElement) -> bool:
        """Click or interact with an element."""
        pass

    @abstractmethod
    def type_text(self, element: UIElement, text: str) -> bool:
        """Type text into an input element."""
        pass
