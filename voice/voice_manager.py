"""
voice/voice_manager.py
======================
Master Controller for Vivy AI's Voice Identity Management System.
All vocal synthesis, multilingual routing, RVC voice conversion, and real-time frontend UI updates
route through this authoritative manager:
  Need Voice -> Voice Manager -> Selected Voice -> voice_cloning.py
Ensures zero-restart live switching across conversations, web dashboards, and voice chat pipelines.
"""

import os
import time
import threading
from typing import Dict, Any, List, Optional

from .voice_database import get_voice_database, VoiceDatabase
from .voice_profiles import get_voice_profile_manager, VoiceProfileManager

class VoiceManager:
    """Master controller coordinating voice profiles, expressive styles, and real-time updates."""

    def __init__(self, db_path: Optional[str] = None):
        self._lock = threading.RLock()
        self.db = get_voice_database(storage_path=db_path)
        self.profile_mgr = get_voice_profile_manager()
        self.active_voice_id = "natural_anime_01"
        self.active_style = "Professional"
        self.live_event_queue: List[Dict[str, Any]] = []

    def get_active_voice(self) -> Dict[str, Any]:
        """Returns authoritative details of the currently selected voice identity and expressive style."""
        with self._lock:
            profile = self.db.get_profile(self.active_voice_id)
            if not profile:
                # Safe fallback to first available profile
                profs = self.db.list_profiles()
                if profs:
                    profile = profs[0]
                    self.active_voice_id = profs[0]["voice_id"]
                else:
                    profile = {
                        "voice_id": "natural_anime_01",
                        "name": "Natural Anime Girl",
                        "model_filename": "natural_anime_female.pth",
                        "language_support": ["en", "ja", "hi", "es", "ru", "fr", "ko", "pt", "de", "zh", "it", "ar", "all"],
                        "quality_score": 99
                    }
            
            style_params = self.profile_mgr.get_style_parameters(self.active_style)
            return {
                "voice_id": profile.get("voice_id", "natural_anime_01"),
                "name": profile.get("name", "Natural Anime Girl"),
                "model_filename": profile.get("model_filename", "natural_anime_female.pth"),
                "language_support": profile.get("language_support", ["en", "ja", "hi", "es", "ru", "fr", "all"]),
                "quality_score": profile.get("quality_score", 99),
                "active_style": self.active_style,
                "style_parameters": style_params,
                "timestamp": time.time()
            }

    def select_voice(self, voice_id_or_name: Optional[str] = None, style_name: Optional[str] = None) -> bool:
        """
        Instantly switch Vivy's active voice and/or style in real-time without restarting the server.
        """
        with self._lock:
            if voice_id_or_name:
                profile = self.db.get_profile(voice_id_or_name)
                if not profile:
                    print(f"[VoiceManager] Warning: Profile '{voice_id_or_name}' not found.")
                    return False
                self.active_voice_id = profile["voice_id"]
                name = profile["name"]
            else:
                prof = self.db.get_profile(self.active_voice_id)
                name = prof["name"] if prof else "Natural Anime Girl"

            if style_name and style_name in self.profile_mgr.list_styles():
                self.active_style = style_name
                self.profile_mgr.set_active_style(style_name)

            self.notify_realtime_event("voice_switched", {
                "voice_id": self.active_voice_id,
                "name": name,
                "active_style": self.active_style
            })
            print(f"[VoiceManager] Real-time voice switch successful: {name} ({self.active_style})")
            return True

    def set_expressive_style(self, style_name: str) -> bool:
        """Switch expressive style (Soft, Cheerful, Calm, Energetic, Professional) in real time."""
        with self._lock:
            success = self.profile_mgr.set_active_style(style_name)
            if success:
                self.active_style = style_name
                self.notify_realtime_event("style_switched", {"active_style": self.active_style})
            return success

    def set_vocal_style(self, style_name: str) -> bool:
        """Alias for set_expressive_style."""
        return self.set_expressive_style(style_name)

    def sync_with_relationship_and_mood(self, relationship_stage: str, conversation_mood: str, user_emotion: str = "") -> str:
        """Dynamically adjusts vocal delivery style to match companionship maturity and atmosphere."""
        with self._lock:
            chosen_style = self.profile_mgr.resolve_style_from_relationship_and_mood(
                relationship_stage=relationship_stage,
                mood=conversation_mood,
                user_emotion=user_emotion
            )
            self.active_style = chosen_style
            return chosen_style

    def notify_realtime_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        Broadcasts real-time events to frontend WebSockets and live polling queues.
        Ensures Voice List and UI refresh immediately after training or switching without restart.
        """
        with self._lock:
            event = {
                "type": event_type,
                "payload": payload,
                "timestamp": time.time()
            }
            self.live_event_queue.append(event)
            if len(self.live_event_queue) > 100:
                self.live_event_queue.pop(0)

            # Attempt WebSocket push if Avatar Bridge or WebServer WS is accessible
            try:
                # We save latest event to a lightweight sentinel file for cross-process polling
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                shared_dir = os.path.join(base_dir, "shared")
                os.makedirs(shared_dir, exist_ok=True)
                tmp_f = os.path.join(shared_dir, "last_voice_event.json.tmp")
                import json
                with open(tmp_f, "w", encoding="utf-8") as f:
                    json.dump(event, f, ensure_ascii=False)
                
                # Retry loop to bypass Windows file locks (WinError 5)
                target_f = os.path.join(shared_dir, "last_voice_event.json")
                for _ in range(5):
                    try:
                        os.replace(tmp_f, target_f)
                        break
                    except OSError:
                        time.sleep(0.05)
            except Exception as _e:
                print(f"[VoiceManager] Event file persistence warning: {_e}")

    def get_recent_events(self, since_timestamp: float = 0.0) -> List[Dict[str, Any]]:
        """Returns recent real-time voice modification events for UI sync."""
        with self._lock:
            return [e for e in self.live_event_queue if e["timestamp"] > since_timestamp]

    def check_language_support(self, lang_code: str, voice_id: Optional[str] = None) -> bool:
        """Checks if the active or specified voice natively supports the target dialect."""
        with self._lock:
            vid = voice_id or self.active_voice_id
            profile = self.db.get_profile(vid)
            if not profile:
                return False
            supported_langs = [l.lower() for l in profile.get("language_support", ["en"])]
            return lang_code.lower() in supported_langs or "all" in supported_langs

# Global Master Controller Singleton
_global_voice_mgr: Optional[VoiceManager] = None
_mgr_lock = threading.RLock()

def get_voice_manager(db_path: Optional[str] = None) -> VoiceManager:
    global _global_voice_mgr
    with _mgr_lock:
        if _global_voice_mgr is None:
            _global_voice_mgr = VoiceManager(db_path=db_path)
        return _global_voice_mgr
