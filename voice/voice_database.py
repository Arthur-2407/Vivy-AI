"""
voice/voice_database.py
=======================
Persistent JSON Voice Identity Database for Vivy AI.
Instead of relying solely on static .pth filenames, stores detailed voice profile metadata:
  voice_id, name, model_filename, language_support, training_iterations, sample_rate, created, quality_score, favorite
Supports real-time querying, updates without restarts, and multi-dialect routing capability evaluation.
"""

import os
import json
import uuid
import time
import threading
from typing import Dict, List, Optional, Any

class VoiceDatabase:
    """Thread-safe JSON datastore managing all voice identities and trained model profiles."""

    def __init__(self, storage_path: Optional[str] = None):
        self._lock = threading.RLock()
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.storage_path = storage_path or os.path.join(base_dir, "shared", "voice_profiles_db.json")
        self.profiles: Dict[str, Dict[str, Any]] = {}
        self.load_database()
        self._ensure_default_profiles()

    def _ensure_default_profiles(self) -> None:
        """Populates baseline voice profiles if database is empty so users have immediate options."""
        with self._lock:
            defaults = [
                {
                    "voice_id": "vivy_anime_01",
                    "name": "Vivy Anime Girl",
                    "model_filename": "vivy_anime_female.pth",
                    "language_support": ["en", "ja", "hi", "es", "ru", "fr", "ko", "pt", "de", "zh", "it", "ar", "all"],
                    "training_iterations": 1,
                    "sample_rate": 48000,
                    "created": "2026-08-05T12:00:00Z",
                    "quality_score": 99,
                    "favorite": True,
                    "style_compatibility": ["Professional", "Soft", "Cheerful", "Calm", "Energetic"],
                    "gender": "female",
                    "vocal_character": "anime_girl",
                    "description": "Vibrant, expressive female anime vocal identity with automated emotional modulation & multilingual synthesis."
                }
            ]
            for d in defaults:
                vid = d["voice_id"]
                if vid not in self.profiles and not any(p["name"].lower() == d["name"].lower() for p in self.profiles.values()):
                    self.profiles[vid] = d
            self.save_database()

    def register_profile(
        self,
        name: str,
        model_filename: str,
        language_support: List[str],
        quality_score: int,
        training_iterations: int = 1,
        sample_rate: int = 48000,
        favorite: bool = False,
        style_compatibility: Optional[List[str]] = None,
        voice_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates or updates a voice profile in real time."""
        with self._lock:
            vid = voice_id or f"voice_{uuid.uuid4().hex[:8]}"
            profile = {
                "voice_id": vid,
                "name": name.strip(),
                "model_filename": model_filename,
                "language_support": language_support or ["en"],
                "training_iterations": training_iterations,
                "sample_rate": sample_rate,
                "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "quality_score": max(0, min(100, quality_score)),
                "favorite": favorite,
                "style_compatibility": style_compatibility or ["Soft", "Professional", "Cheerful", "Calm", "Energetic"]
            }
            self.profiles[vid] = profile
            self.save_database()
            return dict(profile)

    def update_profile(self, voice_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._lock:
            if voice_id in self.profiles:
                for k, v in updates.items():
                    if k != "voice_id":
                        self.profiles[voice_id][k] = v
                self.save_database()
                return dict(self.profiles[voice_id])
            return None

    def get_profile(self, voice_id_or_name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if voice_id_or_name in self.profiles:
                return dict(self.profiles[voice_id_or_name])
            for p in self.profiles.values():
                if p.get("name", "").lower() == voice_id_or_name.lower():
                    return dict(p)
            return None

    def list_profiles(self, language_filter: Optional[str] = None, min_quality: int = 0) -> List[Dict[str, Any]]:
        """Returns all voice profiles meeting language and quality criteria, ordered by favorites and score."""
        with self._lock:
            res = []
            for p in self.profiles.values():
                if p.get("quality_score", 0) >= min_quality:
                    if not language_filter or language_filter.lower() in [l.lower() for l in p.get("language_support", [])]:
                        res.append(dict(p))
            res.sort(key=lambda x: (not x.get("favorite", False), -x.get("quality_score", 0), x.get("name", "")))
            return res

    def delete_profile(self, voice_id: str) -> bool:
        with self._lock:
            if voice_id in self.profiles and voice_id != "vivy_anime_01":
                del self.profiles[voice_id]
                self.save_database()
                return True
            return False

    def save_database(self) -> None:
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
                tmp_path = self.storage_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump({"voices": self.profiles}, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self.storage_path)
            except Exception as e:
                print(f"[VoiceDatabase] Save error: {e}")

    def load_database(self) -> None:
        with self._lock:
            if os.path.exists(self.storage_path):
                try:
                    with open(self.storage_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if "voices" in data and isinstance(data["voices"], dict):
                            unwanted_ids = {"vivy_default_01", "emma_voice_02", "my_voice_03", "anime_voice_04", "soft_voice_05"}
                            unwanted_names = {"Vivy Default", "Emma", "My Voice", "Anime Voice", "Soft Voice"}
                            cleaned = {}
                            for k, v in data["voices"].items():
                                if k not in unwanted_ids and v.get("name") not in unwanted_names:
                                    cleaned[k] = v
                            self.profiles = cleaned
                except Exception as e:
                    print(f"[VoiceDatabase] Load warning: {e}")

# Singleton instance
_global_voice_db: Optional[VoiceDatabase] = None
_db_lock = threading.RLock()

def get_voice_database(storage_path: Optional[str] = None) -> VoiceDatabase:
    global _global_voice_db
    with _db_lock:
        if _global_voice_db is None or (storage_path and storage_path != _global_voice_db.storage_path):
            _global_voice_db = VoiceDatabase(storage_path=storage_path)
        return _global_voice_db
