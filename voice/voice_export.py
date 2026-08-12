"""
voice/voice_export.py
=====================
Voice Identity Export, Import & Archival Utility for Vivy AI.
Enables custom trained RVC voice profiles and rich JSON metadata to be exported as unified bundles,
shared, or restored across machine environments cleanly.
"""

import os
import json
import zipfile
import shutil
from typing import Optional, Dict, Any

from .voice_database import get_voice_database

class VoiceExportManager:
    """Manages archiving and restoring complete custom voice identity bundles."""

    def __init__(self, export_dir: Optional[str] = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.export_dir = export_dir or os.path.join(base_dir, "shared", "exports", "voices")
        os.makedirs(self.export_dir, exist_ok=True)
        self.db = get_voice_database()

    def export_profile_bundle(self, voice_id: str) -> Optional[str]:
        """
        Packages a voice profile metadata JSON and any corresponding .pth weight file into a portable ZIP archive.
        Returns absolute path to generated .zip bundle.
        """
        profile = self.db.get_profile(voice_id)
        if not profile:
            return None

        safe_name = "".join(c for c in profile.get("name", "voice") if c.isalnum() or c in ("_", "-")).rstrip()
        zip_filename = f"{safe_name}_{voice_id[:8]}_export.zip"
        zip_path = os.path.join(self.export_dir, zip_filename)

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        weights_dir = os.path.join(base_dir, "rvc_cpu", "assets", "weights")
        model_filename = profile.get("model_filename", "")
        model_path = os.path.join(weights_dir, model_filename)

        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # Add profile json
                meta_str = json.dumps(profile, indent=2, ensure_ascii=False)
                zf.writestr(f"profile_{voice_id}.json", meta_str)
                
                # Add model weights if file exists on disk
                if os.path.exists(model_path):
                    zf.write(model_path, f"weights/{model_filename}")
            return zip_path
        except Exception as e:
            print(f"[VoiceExport] Export failed for {voice_id}: {e}")
            if os.path.exists(zip_path):
                try: os.remove(zip_path)
                except Exception as _e: print(f"[VoiceExport] Cleanup warning: {_e}")
            return None

    def import_profile_bundle(self, zip_path: str) -> Optional[Dict[str, Any]]:
        """Restores an exported voice profile archive into active database and weights repository."""
        if not os.path.exists(zip_path):
            return None

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        weights_dir = os.path.join(base_dir, "rvc_cpu", "assets", "weights")
        os.makedirs(weights_dir, exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                meta_names = [f for f in zf.namelist() if f.startswith("profile_") and f.endswith(".json")]
                if not meta_names:
                    return None
                
                meta_data = json.loads(zf.read(meta_names[0]).decode("utf-8"))
                
                # Extract weights if present
                for name in zf.namelist():
                    if name.startswith("weights/") and name.endswith(".pth"):
                        target_filename = os.path.basename(name)
                        target_path = os.path.join(weights_dir, target_filename)
                        with open(target_path, "wb") as wf:
                            wf.write(zf.read(name))
                        meta_data["model_filename"] = target_filename

                # Register imported voice identity
                res = self.db.register_profile(
                    name=meta_data.get("name", "Imported Voice"),
                    model_filename=meta_data.get("model_filename", "imported.pth"),
                    language_support=meta_data.get("language_support", ["en"]),
                    quality_score=meta_data.get("quality_score", 90),
                    training_iterations=meta_data.get("training_iterations", 1),
                    sample_rate=meta_data.get("sample_rate", 48000),
                    favorite=meta_data.get("favorite", False),
                    style_compatibility=meta_data.get("style_compatibility", ["Professional"]),
                    voice_id=meta_data.get("voice_id", None)
                )
                return res
        except Exception as e:
            print(f"[VoiceExport] Import error for {zip_path}: {e}")
            return None

_global_exporter = None

def get_voice_exporter() -> VoiceExportManager:
    global _global_exporter
    if _global_exporter is None:
        _global_exporter = VoiceExportManager()
    return _global_exporter
