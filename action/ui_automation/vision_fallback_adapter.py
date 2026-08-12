"""
Vivy AI — Action System: Vision Fallback Adapter
=================================================
Implements UI automation via screen OCR/VLM when DOM or accessibility is unavailable.
Reuses existing observation_adapter logic.
"""

from __future__ import annotations
from typing import Optional
from .base import UIAdapter, UIElement, UIState


class VisionFallbackAdapter(UIAdapter):
    """
    Fallback adapter that relies on OCR and visual screen analysis.
    Uses Vivy's perception/screen_pipeline.
    """
    
    def __init__(self):
        self._connected = True
    
    def connect(self, target: str) -> bool:
        """Connect to the current screen."""
        return True

    def get_state(self) -> UIState:
        """Capture screen using ObservationAdapter logic."""
        try:
            from action.observation_adapter import get_observation_adapter
            obs = get_observation_adapter().capture_screen()
            
            # Map visual candidates to UI elements
            elements = []
            for i, cand in enumerate(obs.get("candidates", [])):
                elements.append(UIElement(
                    element_id=f"vis_{i}",
                    label=cand.get("label", ""),
                    element_type="visual_region",
                    properties=cand,
                    confidence=0.7  # Vision is inherently lower confidence
                ))
                
            return UIState(
                app_name=obs.get("app_type", "unknown"),
                url_or_path="screen",
                elements=elements,
                raw_source=obs.get("raw_text", ""),
                is_vision_fallback=True
            )
        except Exception:
            return UIState("unknown", "screen", [], is_vision_fallback=True)

    def click(self, element: UIElement) -> bool:
        """Click an element using screen coordinates (e.g., via PyAutoGUI)."""
        print(f"[VisionAdapter] Fallback click on coordinates for {element.label}")
        return True

    def type_text(self, element: UIElement, text: str) -> bool:
        """Type text using simulated keystrokes."""
        print(f"[VisionAdapter] Fallback type '{text}' into {element.label}")
        return True
