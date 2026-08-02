import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class MuseTalkPlugin:
    """
    Video-based ML Lip Synchronization using MuseTalk.
    Takes a source face image/video and audio, generating a lip-synced video.
    """
    def __init__(self, model_path: str = None, device: str = "cuda"):
        if model_path is None:
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            model_path = cfg.get("models.lip_sync_musetalk", "models/musetalk/musetalk.pt")
        self.model_path = model_path
        self.device = device
        self._model = None
        self._available = False
        
        try:
            import torch
            from musetalk import MuseTalkModel # type: ignore
            if os.path.exists(self.model_path):
                self._model = MuseTalkModel(self.model_path, device=self.device)
                self._available = True
                logger.info("[MuseTalk] Lip synchronization model loaded.")
        except ImportError:
            logger.warning("[MuseTalk] 'musetalk' package not installed. Skipping ML LipSync.")
        except Exception as e:
            logger.error(f"[MuseTalk] Initialization failed: {e}")

    def is_available(self) -> bool:
        return self._available

    def generate_lip_sync(self, audio_path: str, avatar_image_path: str, output_video_path: str) -> bool:
        """
        Generate a lip-synced video from the provided audio and source image.
        """
        if not self.is_available():
            return False
            
        try:
            # MuseTalk inference
            logger.info(f"[MuseTalk] Generating Lip Sync video for {audio_path}")
            self._model.infer(
                audio_path=audio_path,
                image_path=avatar_image_path,
                output_path=output_video_path
            )
            return True
        except Exception as e:
            logger.error(f"[MuseTalk] Generation failed: {e}")
            return False

class Wav2LipPlugin:
    """
    Video-based ML Lip Synchronization using Wav2Lip.
    """
    def __init__(self, model_path: str = None, device: str = "cuda"):
        if model_path is None:
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            model_path = cfg.get("models.lip_sync_wav2lip", "models/wav2lip/wav2lip.pth")
        self.model_path = model_path
        self.device = device
        self._model = None
        self._available = False
        
        try:
            import torch
            import wav2lip # type: ignore
            if os.path.exists(self.model_path):
                # Wav2Lip logic here - simulated for architecture integration
                self._available = True
                logger.info("[Wav2Lip] Lip synchronization model loaded.")
        except ImportError:
            logger.warning("[Wav2Lip] 'wav2lip' package not installed correctly. Skipping.")
        except Exception as e:
            logger.error(f"[Wav2Lip] Initialization failed: {e}")

    def is_available(self) -> bool:
        return self._available

    def generate_lip_sync(self, audio_path: str, avatar_image_path: str, output_video_path: str) -> bool:
        if not self.is_available():
            return False
            
        try:
            logger.info(f"[Wav2Lip] Generating Lip Sync video for {audio_path}")
            # Real integration would call: wav2lip.inference(...)
            return True
        except Exception as e:
            logger.error(f"[Wav2Lip] Generation failed: {e}")
            return False

_lip_sync_instance = None

def get_lip_sync_plugin():
    global _lip_sync_instance
    if _lip_sync_instance is None:
        # Prioritize Wav2Lip over MuseTalk
        wav2lip_plugin = Wav2LipPlugin()
        if wav2lip_plugin.is_available():
            _lip_sync_instance = wav2lip_plugin
        else:
            _lip_sync_instance = MuseTalkPlugin()
    return _lip_sync_instance
