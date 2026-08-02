"""
Vivy AI — Internet Intelligence Layer: Smart Search Planner
Determines search necessity, formulates query strategies, evaluates cache and local memory,
and coordinates offline-first fallback.
"""

import re
from typing import Tuple, List, Dict, Any, Optional

from internet.network_manager import NetworkManager, NetworkState
from internet.search_cache import SearchCache

class SmartSearchPlanner:
    """Intelligent planner for internet search execution and offline fallback."""

    def __init__(self, network_manager: Optional[NetworkManager] = None, cache: Optional[SearchCache] = None):
        self.network_manager = network_manager or NetworkManager.get_instance()
        self.cache = cache or SearchCache()

    def is_search_needed(self, user_input: str, categories: Optional[List[str]] = None) -> bool:
        """
        Determines whether internet search is necessary.
        Excludes personal companion queries and simple chit-chat.
        """
        if not user_input or len(user_input.strip()) < 2:
            return False

        text_lower = user_input.lower()
        cats = set(categories or [])

        # Pure companion phrases never trigger search
        pure_companion = {
            "greeting", "farewell", "compliment", "flirting",
            "intimacy", "comfort", "teasing", "mystery"
        }
        if cats and cats.issubset(pure_companion):
            return False

        personal_phrases = [
            "how are you", "how've you been", "do you like", "your favorite",
            "what do you think of me", "are you", "do you have", "can you tell me about yourself",
            "what are you doing", "what is your name", "who are you", "tell me about you"
        ]
        if any(p in text_lower for p in personal_phrases):
            return False

        search_keywords = [
            "who is", "who was", "what is", "what was", "where is", "where was",
            "current", "latest", "today", "weather", "news", "price", "stock",
            "how many", "tell me about", "who won", "president", "prime minister",
            "definition of", "meaning of", "vs", "versus", "date today", "time today",
            "release date", "when did", "when is", "score of", "winner of",
            "capital of", "population of", "how high", "how deep", "how far",
            "distance between", "how old is", "birthday of", "height of", "who wrote",
            "who directed", "cast of", "movie release", "stands for", "acronym",
            "how to cook", "recipe for", "how do i make", "ingredients for",
            "recommend a", "recommend some", "best movie", "best book", "best game", "good anime",
            "top 10", "suggest a", "suggest some", "symptom", "treatment", "cause", "medicine"
        ]

        if any(k in text_lower for k in search_keywords):
            return True

        if "?" in user_input and any(text_lower.strip().startswith(w) for w in ["what", "where", "when", "who", "why", "how"]):
            return True

        return False

    def plan_query(self, user_input: str, conversation_mode: str = "companion", symptoms: Optional[List[str]] = None) -> List[str]:
        """Formulate optimal search queries from user input and cognitive context."""
        queries = []

        if conversation_mode in ("health_priority", "health_continuation") and symptoms:
            if len(symptoms) >= 2:
                queries.append(f"{' and '.join(symptoms[:3])} together symptoms causes treatment")
            else:
                queries.append(f"{symptoms[0]} symptoms causes natural remedy treatment")
            return queries

        clean_input = user_input.strip()
        # Remove trailing question marks
        clean_input = clean_input.rstrip("?").strip()
        queries.append(clean_input)

        return queries

    def evaluate_offline_fallback(self, query: str, memory: Optional[Dict[str, Any]] = None) -> str:
        """
        Synthesize offline fallback context from cached search results or local memory
        when network connection is lost or degraded.
        """
        # 1. Check Search Cache
        results, is_stale = self.cache.get(query)
        if results:
            snippets = [r.to_formatted_snippet() for r in results[:3]]
            status_note = "[Offline Mode — using cached search results]" if not self.network_manager.is_online() else "[Cached Search Results]"
            return f"{status_note}\n" + "\n".join(snippets)

        # 2. Check local memory long term facts
        if memory and isinstance(memory, dict):
            long_term_facts = memory.get("long_term_facts", {})
            matching_facts = []
            for k, v in long_term_facts.items():
                if k.lower() in query.lower() or any(w in str(v).lower() for w in query.lower().split()):
                    matching_facts.append(f"- Memory fact ({k}): {v}")

            if matching_facts:
                return "[Offline Mode — using local memory facts]\n" + "\n".join(matching_facts)

        return "[Offline Mode — network unavailable and no cached results found]"
