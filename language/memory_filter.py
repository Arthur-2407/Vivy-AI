"""
language/memory_filter.py
=========================
Step 3: Memory Extraction & Cross-Lingual Recall
Bridges semantic recall across language shifts so facts stated in English are
seamlessly retrieved when queried in Hindi, Odia, or Japanese.
"""

import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class CrossLingualMemoryFilter:
    """
    Normalizes conversational queries before sending to vector storage and relational memory,
    guaranteeing reliable cross-lingual retrieval without duplicating memory entries.
    """

    def __init__(self, config: Dict[str, Any] = None):
        self.enabled = True
        if config:
            self.enabled = config.get("cross_lingual_memory", True)

        # Conceptual cross-lingual query mapping dictionary (configurable & extensible)
        self._concept_map = {
            # Odia core conceptual queries
            "ମୋର ନାମ କଣ": "user name what is my name",
            "ମୋର ନାମ": "user name my name",
            "ତୁମେ କଣ କରୁଛ": "what are you doing status activity",
            "କେମିତି ଅଛ": "how are you greeting wellbeing",
            
            # Hindi core conceptual queries
            "मेरा नाम क्या है": "user name what is my name",
            "मेरा नाम": "user name my name",
            "कैसी हो": "how are you greeting wellbeing",
            "क्या कर रही हो": "what are you doing status activity",
            
            # Japanese core conceptual queries
            "私の名前は何ですか": "user name what is my name",
            "私の名前": "user name my name",
            "元気ですか": "how are you greeting wellbeing",
        }

    def normalize_query_for_retrieval(self, raw_query: str, detected_lang: str = "en") -> str:
        """
        Enriches non-English conversational queries with normalized conceptual keywords
        to maximize cosine similarity match rates against stored English memories.
        """
        if not self.enabled or not raw_query or detected_lang == "en":
            return raw_query

        cleaned = raw_query.strip(".,!?¿?।:;\n ")
        
        # Check explicit concept mappings first
        for local_phrase, eng_concept in self._concept_map.items():
            if local_phrase in cleaned or cleaned in local_phrase:
                logger.info(f"[CrossLingualMemory] Bridging '{cleaned}' -> concept '{eng_concept}'")
                return f"{raw_query} ({eng_concept})"

        # If language is non-English and contains interrogation markers, append generalized query keywords
        if any(w in cleaned for w in ["କଣ", "क्या", "कहाँ", "କେଉଁଠି", "何", "どこ", "who", "what", "where"]):
            return f"{raw_query} (user fact recall request)"

        return raw_query

    def post_process_memories(self, retrieved_memories: List[str], target_lang: str = "en") -> List[str]:
        """
        Ensures retrieved English memory summaries are framed cleanly for the target language response generator.
        """
        if not retrieved_memories or target_lang == "en":
            return retrieved_memories
        
        # Tag retrieved facts so the LLM knows to translate them naturally when constructing the reply
        formatted = []
        for mem in retrieved_memories:
            if not mem.startswith("[Fact]"):
                formatted.append(f"[Retrieved Fact to express in {target_lang.upper()}]: {mem}")
            else:
                formatted.append(mem)
        return formatted
