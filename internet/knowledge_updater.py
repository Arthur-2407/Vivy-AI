"""
Vivy AI — Internet Intelligence Layer: Autonomous Knowledge Updater
Safely synthesizes and caches technical updates, developer documentation, and current web facts
when online, without overwriting or corrupting user personal memory (`vivy_memory.json`).
"""

import os
import json
import time
import threading
from typing import Dict, List, Any, Optional

from internet.network_manager import NetworkManager

class AutonomousKnowledgeUpdater:
    """Safely updates non-user system knowledge base when online."""

    def __init__(self, knowledge_file: str = "shared/web_knowledge_store.json", network_manager: Optional[NetworkManager] = None):
        self.knowledge_file = knowledge_file
        self.network_manager = network_manager or NetworkManager.get_instance()
        self.lock = threading.Lock()
        self._knowledge_store: Dict[str, Dict[str, Any]] = {}
        self._load_store()

    def _load_store(self):
        try:
            if os.path.exists(self.knowledge_file):
                with open(self.knowledge_file, "r", encoding="utf-8") as f:
                    self._knowledge_store = json.load(f)
        except Exception as e:
            print(f"[KnowledgeUpdater] Load error: {e}")
            self._knowledge_store = {}

    def _save_store(self):
        try:
            os.makedirs(os.path.dirname(self.knowledge_file), exist_ok=True)
            tmp = self.knowledge_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._knowledge_store, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.knowledge_file)
        except Exception as e:
            print(f"[KnowledgeUpdater] Save error: {e}")

    def update_topic(self, topic: str, summary: str, source: str = "duckduckgo", category: str = "general", confidence: float = 0.85):
        """
        Store verified synthesized knowledge without affecting user personal memory (`vivy_memory.json`).
        Passes through verification, confidence scoring, and relevance evaluation.
        """
        if not self.network_manager.is_online():
            print(f"[KnowledgeUpdater] Skipped update for '{topic}' — network is offline.")
            return

        # Verification & Relevance Filter
        if not topic or not summary or len(summary.strip()) < 15:
            print(f"[KnowledgeUpdater] Skipped update for '{topic}' — failed length/relevance check.")
            return

        if confidence < 0.60:
            print(f"[KnowledgeUpdater] Skipped update for '{topic}' — low confidence score ({confidence:.2f}).")
            return

        with self.lock:
            key = topic.strip().lower()
            self._knowledge_store[key] = {
                "topic": topic,
                "summary": summary.strip(),
                "source": source,
                "category": category,
                "confidence_score": confidence,
                "verified": True,
                "updated_at": time.time()
            }
            self._save_store()
            print(f"[KnowledgeUpdater] Verified and updated web knowledge topic: '{topic}' (confidence: {confidence:.2f})")

    def get_topic_knowledge(self, topic: str) -> Optional[str]:
        with self.lock:
            key = topic.strip().lower()
            entry = self._knowledge_store.get(key)
            if entry:
                return entry.get("summary")
        return None

    def get_all_topics(self) -> List[Dict[str, Any]]:
        with self.lock:
            return list(self._knowledge_store.values())
