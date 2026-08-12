"""
Vivy AI — Action System: Media Resolver
=========================================
Local-first media search. Discovers music/video files in OS user directories
without hardcoding paths. Falls back to online search via existing internet
infrastructure only when no local match is found.

Spec reference: §8 (Music Example), §9 (Local-First Resource Resolution)
"""

from __future__ import annotations

import os
import time
import difflib
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class MediaCandidate:
    """A discovered media file or online resource."""
    title: str                 # Display title (derived from filename)
    path: str                  # Absolute local path or URL
    media_type: str            # "audio" | "video" | "unknown"
    source: str                # "local" | "online"
    confidence: float          # 0.0 – 1.0 fuzzy-match confidence
    extension: str = ""
    size_bytes: int = 0
    modified: float = 0.0

    def is_local(self) -> bool:
        return self.source == "local"

    def __repr__(self) -> str:
        return (f"MediaCandidate(title={self.title!r}, source={self.source!r}, "
                f"confidence={self.confidence:.2f})")


# Extensions split by type for quick categorisation
_AUDIO_EXTS = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".wma", ".opus", ".ape"}
_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv", ".m4v"}


def _classify_extension(ext: str) -> str:
    ext = ext.lower()
    if ext in _AUDIO_EXTS:
        return "audio"
    if ext in _VIDEO_EXTS:
        return "video"
    return "unknown"


def _stem_to_title(stem: str) -> str:
    """Convert a filename stem to a display title."""
    # Remove common separators and leading track numbers
    import re
    title = re.sub(r"^[\d]+[.\-_\s]+", "", stem)  # strip leading "01 - "
    title = title.replace("_", " ").replace("-", " ").replace(".", " ")
    return title.strip()

def _extract_metadata(path: str) -> Dict[str, str]:
    """Phase 9: Extract ID3 metadata if mutagen is available."""
    try:
        import mutagen
        meta = mutagen.File(path, easy=True)
        if meta:
            return {
                "title": meta.get("title", [""])[0],
                "artist": meta.get("artist", [""])[0],
                "album": meta.get("album", [""])[0],
            }
    except Exception:
        pass
    return {"title": "", "artist": "", "album": ""}

class MediaResolver:
    """
    Resolves media requests via local filesystem search with online fallback.
    Uses metadata-aware scoring (Phase 9).
    Spec reference: §8, §9
    """
    _instance: Optional["MediaResolver"] = None
    _lock: threading.RLock = threading.RLock()

    def __init__(self):
        self._config_loaded = False
        self._media_extensions: set = set()
        self._extra_roots: List[str] = []

    @classmethod
    def get_instance(cls) -> "MediaResolver":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _load_config(self) -> None:
        if self._config_loaded:
            return
        try:
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            exts = cfg.get("action_system.media_extensions", [])
            self._media_extensions = set(e.lower() for e in exts) if exts else (
                _AUDIO_EXTS | _VIDEO_EXTS
            )
            self._extra_roots = cfg.get("action_system.media_search_roots", []) or []
        except Exception:
            self._media_extensions = _AUDIO_EXTS | _VIDEO_EXTS
            self._extra_roots = []
        self._config_loaded = True

    def _get_search_roots(self) -> List[str]:
        """
        Collect search directories without hardcoding.
        Uses configured roots, then falls back to OS user directories.
        """
        self._load_config()
        roots: List[str] = []

        for r in self._extra_roots:
            if os.path.isdir(r):
                roots.append(r)

        home = Path.home()
        candidate_dirs = [
            home / "Music",
            home / "Videos",
            home / "Downloads",
            home / "Desktop",
            home / "Documents",
        ]

        user_profile = os.environ.get("USERPROFILE", "")
        if user_profile:
            for sub in ("Music", "Videos", "Downloads", "Desktop", "Documents"):
                p = os.path.join(user_profile, sub)
                if os.path.isdir(p) and p not in roots:
                    candidate_dirs.append(Path(p))

        for d in candidate_dirs:
            s = str(d)
            if os.path.isdir(s) and s not in roots:
                roots.append(s)

        return roots

    def search_local(self, query: str, max_results: int = 5) -> List[MediaCandidate]:
        """
        Search local filesystem for media files matching query using metadata-aware scoring.
        Spec reference: Phase 9
        """
        self._load_config()
        query_l = query.strip().lower()
        if not query_l:
            return []

        roots = self._get_search_roots()
        candidates: List[MediaCandidate] = []

        for root in roots:
            try:
                for dirpath, _, filenames in os.walk(root):
                    if any(part.startswith(".") for part in Path(dirpath).parts):
                        continue
                    for fname in filenames:
                        ext = Path(fname).suffix.lower()
                        if ext not in self._media_extensions:
                            continue
                            
                        full_path = os.path.join(dirpath, fname)
                        stem = Path(fname).stem
                        title = _stem_to_title(stem)
                        title_l = title.lower()

                        # Fast fuzzy match on filename before doing expensive ID3 extraction
                        base_ratio = difflib.SequenceMatcher(None, query_l, title_l).ratio()
                        if query_l in title_l or title_l in query_l:
                            base_ratio = max(base_ratio, 0.6)
                            
                        # Only extract metadata if the filename has some remote relevance, 
                        # or if the query is an artist name, we might miss it. 
                        # To be safe but fast, we extract metadata if base_ratio > 0.2
                        ratio = base_ratio
                        meta = {"title": "", "artist": "", "album": ""}
                        
                        if base_ratio > 0.15:
                            meta = _extract_metadata(full_path)
                            meta_title_l = meta["title"].lower()
                            meta_artist_l = meta["artist"].lower()
                            meta_album_l = meta["album"].lower()
                            
                            # Boost based on precise semantic metadata
                            if query_l in meta_title_l or meta_title_l in query_l and meta_title_l:
                                ratio = max(ratio, 0.90)
                            if query_l in meta_artist_l or meta_artist_l in query_l and meta_artist_l:
                                ratio = max(ratio, 0.85)
                            if query_l in meta_album_l or meta_album_l in query_l and meta_album_l:
                                ratio = max(ratio, 0.80)
                                
                            meta_ratio = difflib.SequenceMatcher(None, query_l, f"{meta_artist_l} {meta_title_l}").ratio()
                            ratio = max(ratio, meta_ratio)

                        if ratio < 0.35:
                            continue

                        # Phase 8 multi-feature modifiers
                        if ext in ['.mp3', '.mp4', '.mkv', '.flac']:
                            ratio += 0.05
                        depth = len(Path(dirpath).parts)
                        ratio -= (depth * 0.01)

                        try:
                            stat = os.stat(full_path)
                            size = stat.st_size
                            mtime = stat.st_mtime
                        except OSError:
                            size, mtime = 0, 0.0

                        candidates.append(MediaCandidate(
                            title=meta["title"] or title,
                            path=full_path,
                            media_type=_classify_extension(ext),
                            source="local",
                            confidence=ratio,
                            extension=ext,
                            size_bytes=size,
                            modified=mtime,
                        ))
            except PermissionError:
                continue
            except Exception as err:
                print(f"[MediaResolver] Error scanning {root}: {err}")

        candidates.sort(key=lambda c: (-c.confidence, -c.modified))
        return candidates[:max_results]

    def play_local(self, candidate: MediaCandidate) -> Dict[str, Any]:
        """
        Launch local media using OS default handler (os.startfile).
        Falls back to configured media player if set.
        Spec reference: §8 step 3
        """
        try:
            from config.config_manager import get_config_manager
            preferred_player = get_config_manager().get("action_system.preferred_media_player", "")
        except Exception:
            preferred_player = ""

        if preferred_player and os.path.isfile(preferred_player):
            try:
                import subprocess
                subprocess.Popen([preferred_player, candidate.path])
                return {"success": True, "method": "preferred_player", "player": preferred_player}
            except Exception as err:
                print(f"[MediaResolver] Preferred player failed: {err}")

        try:
            os.startfile(candidate.path)
            return {"success": True, "method": "os_default"}
        except Exception as err:
            return {"success": False, "error": str(err)}

    def build_online_search_url(self, query: str) -> str:
        """
        Build a YouTube search URL for online fallback.
        Uses existing internet infrastructure search — does not create a new HTTP layer.
        Spec reference: §10 (DuckDuckGo/Internet Integration), §8 step 4
        """
        import urllib.parse
        encoded = urllib.parse.quote(query + " official audio")
        return f"https://www.youtube.com/results?search_query={encoded}"


# ── Singleton ──────────────────────────────────────────────────────────────────

def get_media_resolver() -> MediaResolver:
    return MediaResolver.get_instance()
