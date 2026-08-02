"""
perception/vision_adapter.py
==============================
Pluggable vision model adapter layer.

Architecture:
  - BaseVisionAdapter  — interface contract
  - NullVisionAdapter  — default; returns "" instantly (zero overhead)
  - LlavaAdapter       — local llama-cpp vision model (GGUF)
  - ExternalApiAdapter — Gemini Vision / OpenAI Vision API

Selection is driven by vivy_config.json:
  {
    "models": { "vision": null },
    "screen_perception": { "vision_model_enabled": false }
  }

When vision_model_enabled is false OR models.vision is null,
NullVisionAdapter is used automatically. No code changes needed to
upgrade to a real vision model — just set the config keys.

Non-destructive: adding new adapters never affects existing code paths.
"""

from __future__ import annotations
import abc
import logging
import os
from typing import Any

try:
    from PIL import Image as _PIL_Image
except ImportError:
    _PIL_Image = None

from perception.plugins.interfaces import BaseVisionPlugin

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Base interface
# ─────────────────────────────────────────────────────────────────────────────
class BaseVisionAdapter(BaseVisionPlugin, abc.ABC):
    """Abstract base for all vision adapters."""

    @abc.abstractmethod
    def describe(self, image_bytes: bytes, prompt: str = "") -> str:
        """
        Analyse an image and return a semantic description string.

        Parameters
        ----------
        image_bytes : bytes
            Raw JPEG or PNG bytes of the image to analyse.
        prompt : str, optional
            Optional guidance prompt for the vision model.

        Returns
        -------
        str
            Human-readable semantic description, or "" on failure.
        """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Short identifier for logging."""

    def is_available(self) -> bool:
        """Return True if this adapter can currently serve requests."""
        return True


# ─────────────────────────────────────────────────────────────────────────────
# NullVisionAdapter — default, zero overhead
# ─────────────────────────────────────────────────────────────────────────────



# ─────────────────────────────────────────────────────────────────────────────
# NullVisionAdapter — default, zero overhead
# ─────────────────────────────────────────────────────────────────────────────
class NullVisionAdapter(BaseVisionAdapter):
    """
    Default adapter: does nothing, returns empty string instantly.
    Used when vision_model_enabled is False in config.
    """

    @property
    def name(self) -> str:
        return "null"

    def describe(self, image: Any, prompt: str = "") -> str:
        return ""

    def get_capabilities(self) -> list[str]:
        return []

    def is_available(self) -> bool:
        return True
# ─────────────────────────────────────────────────────────────────────────────
class LlavaAdapter(BaseVisionAdapter):
    """
    Local vision model via llama-cpp-python (supports LLaVA, moondream2,
    Qwen2.5-VL, and any multimodal GGUF).

    Config keys required:
      models.vision  = "path/to/model.gguf"

    The model is loaded lazily on first call to describe().
    """

    def __init__(self, model_path: str = None):
        if model_path is None:
            from perception.config_loader import get, get_absolute_path
            vision_model = get("models", "vision")
            model_path = get_absolute_path(vision_model) if vision_model else ""
        self._model_path = model_path
        self._llm = None
        self._available: bool | None = None

    @property
    def name(self) -> str:
        return "llava-local"

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        if not os.path.exists(self._model_path):
            logger.warning(f"[VisionAdapter] LLaVA model not found: {self._model_path}")
            self._available = False
            return False
        self._available = True
        return True

    def _load(self):
        if self._llm is not None:
            return
        try:
            from llama_cpp import Llama
            self._llm = Llama(
                model_path=self._model_path,
                n_ctx=2048,
                n_gpu_layers=-1,
                verbose=False,
                chat_format="llava-1-5",
            )
            logger.info(f"[VisionAdapter] LLaVA model loaded: {self._model_path}")
        except Exception as e:
            logger.error(f"[VisionAdapter] Failed to load LLaVA model: {e}")
            self._available = False
            raise

    def describe(self, image: Any, prompt: str = "") -> str:
        if not self.is_available():
            return ""
        try:
            self._load()
            import base64
            from io import BytesIO
            if _PIL_Image is not None and isinstance(image, _PIL_Image):
                buf = BytesIO()
                image.save(buf, format="JPEG", quality=70)
                img_bytes = buf.getvalue()
            else:
                img_bytes = image
                
            b64 = base64.b64encode(img_bytes).decode("ascii")
            user_prompt = prompt or (
                "Describe what is visible on this computer screen in detail. "
                "Include: the application type, any visible text, what the user is doing, "
                "and any notable visual elements."
            )
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": user_prompt},
                    ],
                }
            ]
            result = self._llm.create_chat_completion(messages=messages, max_tokens=256, temperature=0.1)
            text = result["choices"][0]["message"]["content"].strip()
            logger.debug(f"[VisionAdapter] LLaVA description: {text[:100]}...")
            return text
        except Exception as e:
            logger.error(f"[VisionAdapter] LLaVA describe() failed: {e}")
            return ""

    def get_capabilities(self) -> list[str]:
        return ["scene_understanding", "object_recognition", "ui_interpretation", "diagrams_charts", "code_windows", "browser_pages"]




# ─────────────────────────────────────────────────────────────────────────────
# ExternalApiAdapter — Gemini Vision / OpenAI Vision
# ─────────────────────────────────────────────────────────────────────────────
class ExternalApiAdapter(BaseVisionAdapter):
    """
    External API vision adapter.

    Supports:
      - Google Gemini Vision (provider="gemini")
      - OpenAI Vision (provider="openai")

    Config keys required in vivy_config.json (add these manually):
      {
        "vision_api": {
          "provider": "gemini",
          "api_key": "YOUR_KEY_HERE",
          "model": "gemini-1.5-flash"
        }
      }

    This adapter is only instantiated when explicitly configured.
    Never called by default.
    """

    def __init__(self, provider: str = None, api_key: str = None, model: str = None):
        if provider is None or api_key is None:
            from perception.config_loader import get
            vision_api = get("vision_api", default={})
            provider = provider or vision_api.get("provider", "")
            api_key = api_key or vision_api.get("api_key", "")
            model = model or vision_api.get("model", "gemini-1.5-flash")
            
        self._provider = provider.lower() if provider else ""
        self._api_key  = api_key
        self._model    = model

    @property
    def name(self) -> str:
        return f"external-api-{self._provider}"

    def is_available(self) -> bool:
        return bool(self._api_key) and bool(self._provider)

    def describe(self, image: Any, prompt: str = "") -> str:
        if not self.is_available():
            return ""
        
        from io import BytesIO
        if _PIL_Image is not None and isinstance(image, _PIL_Image):
            buf = BytesIO()
            image.save(buf, format="JPEG", quality=70)
            image_bytes = buf.getvalue()
        else:
            image_bytes = image

        user_prompt = prompt or (
            "Describe what is visible on this computer screen in detail. "
            "Include: the application type, visible text, user activity, and notable visual elements."
        )
        try:
            if self._provider == "gemini":
                return self._describe_gemini(image_bytes, user_prompt)
            elif self._provider == "openai":
                return self._describe_openai(image_bytes, user_prompt)
            else:
                logger.error(f"[VisionAdapter] Unknown provider: {self._provider}")
                return ""
        except Exception as e:
            logger.error(f"[VisionAdapter] External API call failed: {e}")
            return ""

    def get_capabilities(self) -> list[str]:
        return ["scene_understanding", "object_recognition", "ui_interpretation", "diagrams_charts", "code_windows", "browser_pages", "facial_expressions", "gestures"]

    def _describe_gemini(self, image_bytes: bytes, prompt: str) -> str:
        import base64
        import requests
        from perception.config_loader import get_config
        cfg = get_config()
        base_url = cfg.get("apis", {}).get("gemini_base", "https://generativelanguage.googleapis.com/v1beta/models/")
        
        b64 = base64.b64encode(image_bytes).decode("ascii")
        url = f"{base_url}{self._model}:generateContent?key={self._api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": "image/jpeg",
                                "data": b64
                            }
                        }
                    ]
                }
            ]
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=12)
        resp.raise_for_status()
        res_json = resp.json()
        try:
            return res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as err:
            logger.error(f"[VisionAdapter] Gemini response format mismatch or error: {err}. JSON: {res_json}")
            return ""

    def _describe_openai(self, image_bytes: bytes, prompt: str) -> str:
        import base64
        import requests
        b64 = base64.b64encode(image_bytes).decode("ascii")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }
            ],
            "max_tokens": 256,
        }
        from perception.config_loader import get_config
        cfg = get_config()
        url = cfg.get("apis", {}).get("openai_base", "https://api.openai.com/v1/chat/completions")
        
        resp = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


# ─────────────────────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────────────────────
def build_adapter() -> BaseVisionAdapter:
    """
    Factory: build the appropriate vision adapter from config.

    Priority:
      1. If vision_model_enabled is False → NullVisionAdapter
      2. If external api keys are available in config or env/dotenv → ExternalApiAdapter
      3. If models.vision is a valid path → LlavaAdapter
      4. Fallback → NullVisionAdapter

    Returns
    -------
    BaseVisionAdapter
        Always returns a valid adapter (NullVisionAdapter at minimum).
    """
    try:
        from perception.config_loader import get_config, get_absolute_path, get_project_root
        cfg = get_config()

        if not cfg.get("screen_perception", {}).get("vision_model_enabled", False):
            logger.info("[VisionAdapter] vision_model_enabled=false → using NullVisionAdapter")
            return NullVisionAdapter()

        # Check for external API config first
        vision_api = cfg.get("vision_api", {})
        provider = vision_api.get("provider")
        api_key  = vision_api.get("api_key")
        model    = vision_api.get("model", "gemini-1.5-flash")

        # Fallback to environment or .env file
        if not provider or not api_key:
            import os
            env_vars = {}
            try:
                env_path = os.path.join(get_project_root(), ".env")
                if os.path.exists(env_path):
                    with open(env_path, "r", encoding="utf-8") as env_f:
                        for line in env_f:
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                k, v = line.split("=", 1)
                                env_vars[k.strip()] = v.strip().strip("'\"")
            except Exception as _err:
                print(f"[vision_adapter.py] Silenced exception: {_err}")
            
            api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or env_vars.get("GEMINI_API_KEY") or env_vars.get("GOOGLE_API_KEY")
            if api_key:
                provider = "gemini"

        if provider and api_key:
            logger.info(f"[VisionAdapter] Building ExternalApiAdapter({provider}, model={model})")
            return ExternalApiAdapter(provider, api_key, model)

        # Fall back to local GGUF model
        vision_model = cfg.get("models", {}).get("vision")
        if vision_model:
            model_path = get_absolute_path(vision_model)
            logger.info(f"[VisionAdapter] Building LlavaAdapter({model_path})")
            adapter = LlavaAdapter(model_path)
            if adapter.is_available():
                return adapter
            logger.warning("[VisionAdapter] LLaVA model unavailable → falling back to NullVisionAdapter")

        logger.info("[VisionAdapter] No active vision configuration → using NullVisionAdapter")
        return NullVisionAdapter()

    except Exception as e:
        logger.error(f"[VisionAdapter] build_adapter() failed: {e}. Using NullVisionAdapter.")
        return NullVisionAdapter()


# Register plugins with ModelRouter
try:
    from perception.model_router import ModelRouter
    ModelRouter.register_plugin("vision", "null", NullVisionAdapter)
    ModelRouter.register_plugin("vision", "llava-local", LlavaAdapter)
    ModelRouter.register_plugin("vision", "external-api", ExternalApiAdapter)
except Exception as registry_err:
    logger.warning(f"[VisionAdapter] Failed to register plugins with ModelRouter: {registry_err}")
