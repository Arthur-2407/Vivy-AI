"""
Vivy AI — Action System: Observation Adapter
=============================================
Reads current UI/system state using the EXISTING perception infrastructure.
Never creates a second screen capture loop. All screen data comes from the
existing screen_pipeline.py frames via perception_manager.

Provides:
  - get_screen_text()     → Current OCR text from existing screen pipeline
  - get_window_state()    → Foreground window title and process
  - verify_process_running(name) → psutil process check
  - capture_ui_state()    → Structured UIState dict
  - extract_product_candidates(ocr_text) → Product list from shopping page OCR

Spec reference: §26 (Observation+Verification Loop), §16 (Visual UI Interaction)
"""

from __future__ import annotations

import os
import re
import threading
from typing import Any, Dict, List, Optional


class ObservationAdapter:
    """
    Observes current UI/system state using existing perception subsystem.
    Spec reference: §26
    """
    _instance: Optional["ObservationAdapter"] = None
    _lock: threading.RLock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "ObservationAdapter":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ── Screen text (from existing screen_pipeline.py) ────────────────────────

    def get_screen_text(self) -> str:
        """
        Return the most recent OCR text from the existing screen capture pipeline.
        Does NOT trigger a new capture — reads existing shared state.
        Spec reference: §16
        """
        # Primary: read from shared/screen_context.txt (written by screen_pipeline.py)
        try:
            import os
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            screen_ctx = os.path.join(base, "shared", "screen_context.txt")
            if os.path.exists(screen_ctx):
                with open(screen_ctx, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read().strip()
        except Exception as err:
            print(f"[ObservationAdapter] screen_context.txt read error: {err}")

        # Secondary: try perception_manager reader
        try:
            from perception.perception_manager import get_reader
            reader = get_reader()
            diag = reader.get_diagnostic_report()
            return diag.get("screen_text", "") or diag.get("ocr_text", "")
        except Exception:
            pass

        return ""

    # ── Window state ──────────────────────────────────────────────────────────

    def get_window_state(self) -> Dict[str, Any]:
        """
        Return information about the current foreground window.
        Uses pywinauto if available, otherwise ctypes.
        Spec reference: §26
        """
        state: Dict[str, Any] = {
            "foreground_title": "",
            "foreground_process": "",
            "foreground_hwnd": None,
        }

        # Try pywinauto
        try:
            from pywinauto import Desktop
            desktop = Desktop(backend="uia")
            fw = desktop.windows()
            for w in fw:
                try:
                    if w.is_active():
                        state["foreground_title"] = w.window_text()
                        state["foreground_process"] = w.process_id()
                        break
                except Exception:
                    continue
            return state
        except ImportError:
            pass
        except Exception as err:
            print(f"[ObservationAdapter] pywinauto error: {err}")

        # Fallback: ctypes GetForegroundWindow
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if hwnd:
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                state["foreground_title"] = buf.value
                state["foreground_hwnd"] = hwnd

                # Get process name
                import ctypes.wintypes
                pid = ctypes.wintypes.DWORD()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                try:
                    import psutil
                    proc = psutil.Process(pid.value)
                    state["foreground_process"] = proc.name()
                except Exception:
                    state["foreground_process"] = str(pid.value)
        except Exception as err:
            print(f"[ObservationAdapter] ctypes window error: {err}")

        return state

    # ── Process verification ───────────────────────────────────────────────────

    def verify_process_running(self, name: str) -> bool:
        """Check if any process with matching name is currently running."""
        name_l = name.lower()
        try:
            import psutil
            for proc in psutil.process_iter(["name"]):
                pname = (proc.info.get("name") or "").lower()
                if name_l in pname or pname in name_l:
                    return True
        except ImportError:
            # Fallback: tasklist
            try:
                import subprocess
                result = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {name}.exe"],
                    capture_output=True, text=True, timeout=3,
                )
                return name_l in result.stdout.lower()
            except Exception:
                pass
        return False

    # ── Structured UI state ───────────────────────────────────────────────────

    def capture_ui_state(self) -> Dict[str, Any]:
        """
        Return a structured snapshot of current UI state.
        Combines window state, OCR text, and perception diagnostics.
        Spec reference: §26
        """
        window = self.get_window_state()
        screen_text = self.get_screen_text()

        # Perception diagnostics
        perception_data: Dict[str, Any] = {}
        try:
            from perception.perception_manager import get_reader
            perception_data = get_reader().get_diagnostic_report()
        except Exception:
            pass

        return {
            "foreground_title":  window.get("foreground_title", ""),
            "foreground_process": window.get("foreground_process", ""),
            "screen_text":       screen_text,
            "has_screen_text":   bool(screen_text),
            "perception":        perception_data,
        }

    # ── Product candidate extraction ───────────────────────────────────────────

    def extract_product_candidates(self, ocr_text: str) -> List[Dict[str, Any]]:
        """
        Parse product candidates (name, price, rating) from shopping page OCR text.
        Uses heuristic patterns — not hardcoded to any one shopping site.
        Spec reference: §12, §14
        """
        if not ocr_text:
            return []

        candidates: List[Dict[str, Any]] = []
        lines = [l.strip() for l in ocr_text.splitlines() if l.strip()]

        # Price detection pattern (multi-currency)
        price_pattern = re.compile(
            r"(?:₹|Rs\.?|INR|USD|\$|€|£)\s*[\d,]+(?:\.\d{1,2})?|"
            r"[\d,]+(?:\.\d{1,2})?\s*(?:₹|Rs\.?|INR|USD|\$|€|£)"
        )
        # Rating pattern: "4.3", "★ 4.2", "4.5 out of 5"
        rating_pattern = re.compile(r"\b([1-5](?:\.\d)?)\s*(?:out\s+of\s+5|stars?|★)?")

        i = 0
        while i < len(lines):
            line = lines[i]
            # Skip very short lines (likely UI chrome, not product names)
            if len(line) < 8:
                i += 1
                continue

            # Look for a product-like line (title-case, > 10 chars, no price in it)
            is_title_line = (
                len(line) > 10
                and not price_pattern.search(line)
                and sum(1 for c in line if c.isupper()) > 0
            )

            if is_title_line:
                label = line
                price = ""
                rating = ""

                # Look ahead in the next few lines for price and rating
                for j in range(i + 1, min(i + 5, len(lines))):
                    next_line = lines[j]
                    pm = price_pattern.search(next_line)
                    if pm and not price:
                        price = pm.group(0).strip()
                    rm = rating_pattern.search(next_line)
                    if rm and not rating:
                        rv = float(rm.group(1))
                        if 1.0 <= rv <= 5.0:
                            rating = rm.group(1)

                candidates.append({
                    "label":  label,
                    "price":  price,
                    "rating": rating,
                    "url":    "",   # URL not available from OCR; will be filled by browser action
                })

                # Avoid duplicate entries for the same product block
                i += 4
            else:
                i += 1

        # Deduplicate by label similarity
        seen_labels: set = set()
        unique: List[Dict[str, Any]] = []
        for c in candidates:
            key = re.sub(r"\s+", " ", c["label"].lower()[:40])
            if key not in seen_labels:
                seen_labels.add(key)
                unique.append(c)

        return unique[:20]  # Cap at 20 candidates per screen


# ── Singleton ──────────────────────────────────────────────────────────────────

def get_observation_adapter() -> ObservationAdapter:
    return ObservationAdapter.get_instance()
