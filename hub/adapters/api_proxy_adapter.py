"""
Vivy Hub - API Proxy Adapter
Bridges Hub capability.request messages to the existing Flask REST API.
The Hub WebSocket is the authenticated boundary; the Flask server is called
as a local HTTP client from this adapter.
Fault class: Recoverable.
"""
import threading
import requests
import json
from typing import Any, Dict, Optional

HUB_API_BASE = "http://127.0.0.1:5000"  # dynamically overridden if web port changes

# Mapping from Hub capability_id to Flask endpoint + method
CAPABILITY_TO_ENDPOINT = {
    "conversation.chat":      ("POST", "/api/send"),
    "conversation.history":   ("GET",  "/api/history"),
    "memory.read":            ("GET",  "/api/memory"),
    "cognition.state":        ("GET",  "/api/cognitive/state"),
    "action.request":         ("GET",  "/api/action_state"),
    "action.confirm":         ("POST", "/api/action_confirm"),
    "action.cancel":          ("POST", "/api/action_cancel"),
    "action.history":         ("GET",  "/api/action_history"),
    "internet.search":        ("POST", "/api/internet/search"),
    "internet.status":        ("GET",  "/api/internet/status"),
    "voice.profiles":         ("GET",  "/api/voice/profiles"),       # was /api/voice/identities (404)
    "voice.train":            ("POST", "/api/voice/train"),
    "voice.training_status":  ("GET",  "/api/voice/train/progress"),  # was /api/voice/training_status (404)
    "voice.switch":           ("POST", "/api/voice/select"),           # was /api/voice/switch (404)
    "evolution.status":       ("GET",  "/api/evolution/status"),
    "telemetry.read":         ("GET",  "/api/telemetry"),
    "health.read":            ("GET",  "/api/health"),
    "config.read":            ("GET",  "/api/config"),
    "config.write":           ("POST", "/api/config"),
    "avatar.status":          ("GET",  "/api/avatar/status"),           # was /api/avatar/state (404)
    "screen.capture":         ("GET",  "/api/screen/screenshot"),
    "hub.devices":            ("GET",  "/api/hub/nodes"),
    "session.state":          ("GET",  "/api/session/state"),
    "relationship.read":      ("GET",  "/api/cognitive/state"),
    "affection.read":         ("GET",  "/api/cognitive/state"),
    "voice.preview_generate": ("POST", "/api/voice/preview_generate"),
    "voice.preview_audio":    ("GET",  "/api/voice/preview_audio"),
    "avatar.frame":           ("GET",  "/api/avatar/frame"),
    "screen.frame":           ("GET",  "/static/screen.png"),
}

# Payload transformations for POST requests where the Hub payload differs from the Flask body
PAYLOAD_TRANSFORMS = {
    "conversation.chat": lambda payload: {"text": payload.get("text", payload.get("message", ""))},
    "internet.search":   lambda payload: {"query": payload.get("query", payload.get("text", ""))},
    # Flask /api/voice/select expects {"voice": "...", "style": "..."}
    # Android sends {"identity_id": "..."} — normalize here
    "voice.switch":      lambda payload: {
        "voice": payload.get("identity_id", payload.get("voice", "")),
        "style":  payload.get("style", None)
    },
    "config.write":      lambda payload: payload,
    "action.confirm":    lambda payload: {"action_id": payload.get("action_id", "")},
    "action.cancel":     lambda payload: {"action_id": payload.get("action_id", "")},
}


class ApiProxyAdapter:
    _instance = None
    _lock = threading.RLock()
    _api_port: int = 5000

    @classmethod
    def get_instance(cls) -> "ApiProxyAdapter":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def set_api_port(cls, port: int):
        cls._api_port = port

    @property
    def base_url(self) -> str:
        try:
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            port = int(cfg.get("network.web_server_port", cfg.get("server.web_port", 8080)))
            return f"http://127.0.0.1:{port}"
        except Exception:
            return f"http://127.0.0.1:{self._api_port}"

    def can_handle(self, capability_id: str) -> bool:
        return capability_id in CAPABILITY_TO_ENDPOINT

    def execute(self, capability_id: str, payload: Dict[str, Any], device_id: str = "unknown",
                session_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Proxy a Hub capability request to the Flask REST API.
        Returns the JSON response dict, or an error dict on failure.
        """
        if capability_id not in CAPABILITY_TO_ENDPOINT:
            return {"error": f"No Flask route mapped for capability: {capability_id}"}

        method, path = CAPABILITY_TO_ENDPOINT[capability_id]
        url = self.base_url + path

        headers = {"Content-Type": "application/json"}
        if session_key:
            headers["X-Node-Session"] = session_key
        headers["X-Device-Id"] = device_id

        try:
            if method == "GET":
                resp = requests.get(url, headers=headers, timeout=30)
            else:
                # Transform payload to match Flask endpoint expectations
                transform = PAYLOAD_TRANSFORMS.get(capability_id)
                body = transform(payload) if transform else payload
                resp = requests.post(url, json=body, headers=headers, timeout=30)

            if resp.status_code == 200:
                content_type = resp.headers.get("Content-Type", "")
                if any(t in content_type for t in ("image/jpeg", "image/png", "audio/wav", "audio/mpeg", "audio/x-wav")):
                    import base64
                    encoded = base64.b64encode(resp.content).decode("utf-8")
                    key = "audio_b64" if "audio" in content_type else "frame_b64"
                    return {key: encoded, "content_type": content_type}
                
                data = resp.json()
                if isinstance(data, list):
                    return {"data": data}
                return data
            elif resp.status_code == 404:
                return {"error": f"Flask endpoint {path} not found (404). Check web_server.py."}
            else:
                return {"error": f"Flask returned {resp.status_code}", "body": resp.text[:500]}

        except requests.exceptions.ConnectionError:
            return {"error": "Cannot connect to Flask web_server. Is it running?"}
        except Exception as e:
            return {"error": f"ApiProxyAdapter exception: {str(e)}"}
