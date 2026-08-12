"""
Vivy AI — Action System: Media Executor
========================================
Handles play/pause/stop/search media actions.
Implements local-first resolution with online fallback.

Local: MediaResolver → os.startfile / configured player
Online: InternetManager (existing DuckDuckGo infra) → build YouTube URL → BrowserExecutor

Spec reference: §8 (Music Example), §9 (Local-First Resource Resolution), §10 (DDG Integration)
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

from action.intent_model import ActionResult, IntentModel


class MediaExecutor:
    """Executes media play/search actions with local-first resolution."""

    _instance: Optional["MediaExecutor"] = None
    _lock: threading.RLock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "MediaExecutor":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def play(self, intent: IntentModel) -> ActionResult:
        """
        Play a media item. Local-first → online fallback.
        Spec reference: §8, §9
        """
        query = intent.target.strip()
        source_policy = intent.source  # "local_only" | "online_only" | "local_then_online"

        # ── Step 1: Local search (unless online_only) ──────────────────────────
        if source_policy != "online_only":
            local_result = self._try_local(query, intent)
            if local_result is not None:
                return local_result

        # ── Step 2: Online fallback (unless local_only) ────────────────────────
        if source_policy != "local_only":
            return self._try_online(query, intent)

        return ActionResult(
            success=False, domain="media", action="play", target=query,
            message=f"I couldn't find '{query}' locally and online search is disabled.",
            error="Not found locally; online fallback disabled",
        )

    def _try_local(self, query: str, intent: IntentModel) -> Optional[ActionResult]:
        """
        Search local filesystem for media. Returns ActionResult if found, else None.
        Spec reference: §8 steps 1-3
        """
        try:
            from action.media_resolver import get_media_resolver
            resolver = get_media_resolver()
            candidates = resolver.search_local(query, max_results=5)

            if not candidates:
                return None  # Signal: proceed to online fallback

            best = candidates[0]

            # If there are multiple close-confidence candidates, present them
            if len(candidates) > 1 and (candidates[0].confidence - candidates[1].confidence) < 0.10:
                # Ambiguous — store candidates and ask (§28 clarification policy)
                from action.action_session import get_action_session, save_action_session
                session = get_action_session()
                session.set_candidates([
                    {"_index": i + 1, "label": c.title, "path": c.path,
                     "confidence": round(c.confidence, 2), "type": c.media_type}
                    for i, c in enumerate(candidates[:5])
                ])
                save_action_session(session)
                names = "\n".join(
                    f"  {i+1}. {c.title}" for i, c in enumerate(candidates[:5])
                )
                return ActionResult(
                    success=True, domain="media", action="play", target=query,
                    message=f"I found several local matches for '{query}'. Which one?\n{names}",
                    candidates=session.candidates,
                )

            # Single clear match — play it
            play_result = resolver.play_local(best)
            if play_result.get("success"):
                time.sleep(1.5)  # Brief wait for player to open
                verified = self._verify_playback(best.path)
                return ActionResult(
                    success=True, domain="media", action="play", target=query,
                    message=f"Found '{best.title}' locally. Playing it now.",
                    verified=verified,
                    observation={"local_path": best.path, "title": best.title, "playback_verified": verified},
                )
            # Local file found but failed to open
            return ActionResult(
                success=False, domain="media", action="play", target=query,
                message=f"I found '{best.title}' but couldn't start playback.",
                error=play_result.get("error", "Playback launch failed"),
                fallback_used=False,
            )

        except Exception as err:
            print(f"[MediaExecutor] Local search error: {err}")
            return None

    def _try_online(self, query: str, intent: IntentModel) -> ActionResult:
        """
        Search online and open in browser using existing internet infrastructure.
        Spec reference: §8 steps 4-8, §10 (DuckDuckGo/Internet Integration)
        """
        try:
            from action.media_resolver import get_media_resolver
            url = get_media_resolver().build_online_search_url(query)

            from action.executors.browser_executor import get_browser_executor
            result = get_browser_executor().open_url(url)

            if result.success:
                return ActionResult(
                    success=True, domain="media", action="play", target=query,
                    message=f"I couldn't find '{query}' locally, so I opened a YouTube search for it.",
                    verified=result.verified,
                    fallback_used=True,
                    observation=result.observation,
                )
            return ActionResult(
                success=False, domain="media", action="play", target=query,
                message=f"I couldn't find '{query}' locally or open an online search.",
                error=result.error,
                fallback_used=True,
            )
        except Exception as err:
            return ActionResult(
                success=False, domain="media", action="play", target=query,
                message=f"I wasn't able to search for '{query}' online.",
                error=str(err),
                fallback_used=True,
            )

    def _verify_playback(self, file_path: str) -> bool:
        """
        Verify playback actually started by checking for a media player process.
        Uses ObservationAdapter process verification.
        Spec reference: §26 (Observation+Verification Loop), §38 (No false completion)
        """
        try:
            from action.observation_adapter import get_observation_adapter
            obs = get_observation_adapter()
            # Check for common media player processes
            for player in ["vlc", "wmplayer", "groove", "spotify", "mpc-hc", "mpc-be", "mpv", "aimp"]:
                if obs.verify_process_running(player):
                    return True
            # Also check foreground window title for media-related content
            state = obs.get_window_state()
            title = state.get("foreground_title", "").lower()
            from pathlib import Path
            stem = Path(file_path).stem.lower()
            if stem[:6] in title or any(p in title for p in ["media player", "vlc", "spotify", "groove"]):
                return True
        except Exception:
            pass
        return False

    def adjust_volume(self, intent: IntentModel) -> ActionResult:
        """
        Adjust system audio volume.
        Spec reference: §5 (adjust volume), §22 (Device Actions)
        """
        params = intent.parameters
        level = params.get("level")      # 0-100
        direction = params.get("direction")  # "up" | "down" | "mute" | "unmute"

        try:
            # Try pycaw (Windows COM audio API)
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from comtypes import CLSCTX_ALL
            import ctypes
            speakers = AudioUtilities.GetSpeakers()
            interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = interface.QueryInterface(IAudioEndpointVolume)
            if level is not None:
                scalar = max(0.0, min(1.0, float(level) / 100.0))
                volume.SetMasterVolumeLevelScalar(scalar, None)
                return ActionResult(
                    success=True, domain="device", action="adjust", target="volume",
                    message=f"Volume set to {int(level)}%.",
                    verified=True,
                )
            if direction == "mute":
                volume.SetMute(1, None)
                return ActionResult(success=True, domain="device", action="adjust", target="volume",
                                    message="Volume muted.", verified=True)
            if direction == "unmute":
                volume.SetMute(0, None)
                return ActionResult(success=True, domain="device", action="adjust", target="volume",
                                    message="Volume unmuted.", verified=True)
        except ImportError:
            pass
        except Exception as err:
            print(f"[MediaExecutor] pycaw volume error: {err}")

        # Fallback: Windows key simulation via ctypes
        try:
            import ctypes
            VK_VOLUME_UP   = 0xAF
            VK_VOLUME_DOWN = 0xAE
            VK_VOLUME_MUTE = 0xAD
            KEYEVENTF_KEYUP = 0x0002

            key = VK_VOLUME_UP if direction == "up" else (
                  VK_VOLUME_DOWN if direction == "down" else VK_VOLUME_MUTE)
            ctypes.windll.user32.keybd_event(key, 0, 0, 0)
            ctypes.windll.user32.keybd_event(key, 0, KEYEVENTF_KEYUP, 0)
            return ActionResult(
                success=True, domain="device", action="adjust", target="volume",
                message=f"Volume adjusted ({direction}).",
                verified=False,
            )
        except Exception as err:
            return ActionResult(
                success=False, domain="device", action="adjust", target="volume",
                message="I wasn't able to adjust the volume.",
                error=str(err),
            )

    def execute(self, intent: IntentModel) -> ActionResult:
        action = intent.action.lower()
        if action in ("play", "search", "find"):
            return self.play(intent)
        if action in ("adjust", "set") and "volume" in intent.target.lower():
            return self.adjust_volume(intent)
        return ActionResult(
            success=False, domain="media", action=action, target=intent.target,
            message=f"I don't know how to '{action}' for media.",
            error="Unsupported media action",
        )


def get_media_executor() -> MediaExecutor:
    return MediaExecutor.get_instance()
