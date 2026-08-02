"""
perception/connectors/perception_connector.py
=============================================
Vivy AI — Perception Connector
Adapter that translates fused perception events into Vivy Core endpoints via WebSocket / HTTP.

Features:
  - WebSocket client connection to ws://127.0.0.1:8765/perception or ws://127.0.0.1:8080/perception
  - Fallback to HTTP POST endpoint http://127.0.0.1:8080/api/perception/push if WebSocket is unavailable
  - Thread-safe, non-blocking asynchronous event publishing
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Optional, Any, Dict

logger = logging.getLogger(__name__)

_WEBSOCKETS_AVAILABLE = False
try:
    import websockets
    _WEBSOCKETS_AVAILABLE = True
except ImportError:
    pass

_REQUESTS_AVAILABLE = False
try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    pass


class PerceptionConnector:
    """
    Client adapter for streaming perception events into Vivy Core.
    """

    def __init__(self, uri: str = "ws://127.0.0.1:8765/perception", http_fallback_url: str = "http://127.0.0.1:8080/api/perception/push"):
        self.uri = uri
        self.http_fallback_url = http_fallback_url
        self.ws = None
        self._is_connected = False
        self._lock = threading.Lock()

    async def connect(self):
        """Connect to WebSocket endpoint if available."""
        if not _WEBSOCKETS_AVAILABLE:
            logger.debug("[PerceptionConnector] websockets package unavailable; using HTTP fallback.")
            return

        try:
            self.ws = await asyncio.wait_for(websockets.connect(self.uri), timeout=2.0)
            self._is_connected = True
            logger.info(f"[PerceptionConnector] Connected to WebSocket at {self.uri}")
        except Exception as ex:
            logger.debug(f"[PerceptionConnector] WebSocket connection to {self.uri} failed ({ex}); will use HTTP fallback.")
            self.ws = None
            self._is_connected = False

    async def publish(self, message: str):
        """Publish JSON payload string via WebSocket, falling back to HTTP if needed."""
        if self.ws is not None and self._is_connected:
            try:
                await self.ws.send(message)
                return
            except Exception as ex:
                logger.debug(f"[PerceptionConnector] WebSocket send error: {ex}")
                self.ws = None
                self._is_connected = False

        # Attempt to reconnect or fall back to HTTP
        if _WEBSOCKETS_AVAILABLE:
            try:
                await self.connect()
                if self.ws is not None and self._is_connected:
                    await self.ws.send(message)
                    return
            except Exception as _err:
                print(f"[perception_connector.py] Silenced exception: {_err}")

        # HTTP Fallback
        self._publish_http_sync(message)

    def publish_event(self, event_dict: Dict[str, Any]):
        """Synchronous wrapper for publishing an event dictionary."""
        msg_str = json.dumps(event_dict, ensure_ascii=False)
        if _WEBSOCKETS_AVAILABLE and self.ws is not None and self._is_connected:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(self.publish(msg_str), loop)
                    return
            except Exception as _err:
                print(f"[perception_connector.py] Silenced exception: {_err}")

        self._publish_http_sync(msg_str)

    def _publish_http_sync(self, message: str):
        """Publish message payload to Vivy Core via HTTP POST."""
        if not _REQUESTS_AVAILABLE:
            return

        def _worker():
            try:
                payload = json.loads(message) if isinstance(message, str) else message
                resp = requests.post(self.http_fallback_url, json=payload, timeout=1.5)
                if resp.status_code == 200:
                    logger.debug("[PerceptionConnector] Event published via HTTP POST.")
            except Exception as ex:
                logger.debug(f"[PerceptionConnector] HTTP publish error: {ex}")

        threading.Thread(target=_worker, daemon=True).start()

    async def close(self):
        """Close WebSocket connection."""
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception as _err:
                print(f"[perception_connector.py] Silenced exception: {_err}")
            self.ws = None
            self._is_connected = False
