"""
Vivy AI — Topic Tracker & Conversation Stack Manager (v1.0)
Implements persistent topic nodes, subtopic hierarchy, active conversation stack,
completion condition tracking, and natural exit transitions.
"""

import time
import uuid
import re
import json
import threading
from typing import Dict, List, Optional, Any

class TopicNode:
    """Represents a single conversation topic node in the topic tree."""
    def __init__(self, name: str, parent_id: Optional[str] = None, importance: float = 0.5):
        self.topic_id = f"topic_{uuid.uuid4().hex[:8]}"
        self.name = name
        self.creation_time = time.time()
        self.recency_ts = time.time()
        self.importance = max(0.0, min(1.0, float(importance)))
        self.status = "active"  # "active", "waiting_user_reply", "paused", "resolved", "exited"
        self.parent_id = parent_id
        self.subtopics: List[str] = []
        self.waiting_question: Optional[str] = None
        self.expected_reply: Optional[str] = None
        self.completion_conditions: List[str] = []
        self.confidence = 0.8
        self.turn_count = 1

    def to_dict(self) -> dict:
        return {
            "topic_id": self.topic_id,
            "name": self.name,
            "creation_time": self.creation_time,
            "recency_ts": self.recency_ts,
            "importance": self.importance,
            "status": self.status,
            "parent_id": self.parent_id,
            "subtopics": list(self.subtopics),
            "waiting_question": self.waiting_question,
            "expected_reply": self.expected_reply,
            "completion_conditions": list(self.completion_conditions),
            "confidence": self.confidence,
            "turn_count": self.turn_count
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TopicNode":
        node = cls(name=data.get("name", "general"), parent_id=data.get("parent_id"))
        node.topic_id = data.get("topic_id", node.topic_id)
        node.creation_time = data.get("creation_time", time.time())
        node.recency_ts = data.get("recency_ts", time.time())
        node.importance = data.get("importance", 0.5)
        node.status = data.get("status", "active")
        node.subtopics = list(data.get("subtopics", []))
        node.waiting_question = data.get("waiting_question")
        node.expected_reply = data.get("expected_reply")
        node.completion_conditions = list(data.get("completion_conditions", []))
        node.confidence = data.get("confidence", 0.8)
        node.turn_count = data.get("turn_count", 1)
        return node


class ConversationStack:
    """
    Manages the active stack of conversation topics (depth up to max_depth).
    Example: Recipe -> Chicken -> Spicy Version -> Shopping List -> Cooking Tips
    Popping stack returns naturally to parent topic when a subtopic resolves.
    """
    def __init__(self, max_depth: int = 5):
        self.stack: List[str] = []  # List of topic_ids
        self.max_depth = max_depth

    def push(self, topic_id: str):
        if topic_id in self.stack:
            self.stack.remove(topic_id)
        self.stack.append(topic_id)
        if len(self.stack) > self.max_depth:
            self.stack.pop(0)

    def pop(self) -> Optional[str]:
        if self.stack:
            return self.stack.pop()
        return None

    def peek(self) -> Optional[str]:
        return self.stack[-1] if self.stack else None

    def get_stack_topics(self, topic_tree: Dict[str, TopicNode]) -> List[str]:
        result = []
        for tid in self.stack:
            if tid in topic_tree:
                result.append(topic_tree[tid].name)
        return result

    def to_list(self) -> List[str]:
        return list(self.stack)

    def load_from_list(self, data: List[str]):
        self.stack = list(data or [])[:self.max_depth]


class TopicTracker:
    """
    Persistent Topic Tracker and Subtopic Manager for Vivy AI.
    Integrates with long-term memory structures to track active topic, subtopics,
    topic depth, completion status, and topic stack transitions across dialogue turns.
    """
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self.topic_tree: Dict[str, TopicNode] = {}
        self.stack = ConversationStack(max_depth=5)
        self.active_topic_id: Optional[str] = None
        self.previous_topic_name: Optional[str] = None

    @classmethod
    def get_instance(cls) -> "TopicTracker":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def process_turn_topic(self, user_text: str, categories: List[str], mem: dict) -> dict:
        """
        Processes incoming user text and categories, updates topic state,
        manages conversation stack, and returns current topic context metadata.
        """
        with self._lock:
            categories = categories or []
            u_clean = user_text.strip().lower()
            
            # Load stored topic tree and stack from memory if available
            self._restore_from_memory(mem)

            # Heuristic Topic Extraction / Shift Detection
            extracted_topic = self._extract_topic_keyword(user_text, categories, mem)

            # Check if user explicitly changed topic ("let's talk about X", "change topic to Y", "by the way")
            explicit_shift = any(phrase in u_clean for phrase in [
                "let's talk about", "change topic", "by the way", "speaking of",
                "switch to", "different topic", "on another note"
            ])

            active_node = self.topic_tree.get(self.active_topic_id) if self.active_topic_id else None

            if not active_node or explicit_shift or (extracted_topic and active_node and extracted_topic.lower() != active_node.name.lower() and not self._is_subtopic_of(extracted_topic, active_node.name)):
                # Create or switch to new topic node
                parent_id = active_node.topic_id if (active_node and not explicit_shift) else None
                new_node = TopicNode(name=extracted_topic or "casual conversation", parent_id=parent_id)
                
                if parent_id and active_node:
                    active_node.subtopics.append(new_node.topic_id)
                    active_node.status = "paused"
                
                self.topic_tree[new_node.topic_id] = new_node
                if active_node:
                    self.previous_topic_name = active_node.name
                self.active_topic_id = new_node.topic_id
                self.stack.push(new_node.topic_id)
                active_node = new_node
            else:
                # Continue active topic
                active_node.recency_ts = time.time()
                active_node.turn_count += 1

            # Check completion condition / resolution
            resolution_keywords = ["thanks", "that answers it", "got it", "i see", "understood", "done", "next topic"]
            if any(rk in u_clean for rk in resolution_keywords) and active_node.turn_count > 1:
                active_node.status = "resolved"
                # Pop completed topic from stack
                popped_id = self.stack.pop()
                parent_id = active_node.parent_id
                if parent_id and parent_id in self.topic_tree:
                    self.active_topic_id = parent_id
                    parent_node = self.topic_tree[parent_id]
                    parent_node.status = "active"
                elif self.stack.peek():
                    self.active_topic_id = self.stack.peek()
                
            # Update memory dict
            self._sync_to_memory(mem)

            stack_topics = self.stack.get_stack_topics(self.topic_tree)
            current_topic_name = self.topic_tree[self.active_topic_id].name if self.active_topic_id in self.topic_tree else "general"

            return {
                "current_topic": current_topic_name,
                "previous_topic": self.previous_topic_name,
                "topic_stack": stack_topics,
                "topic_depth": len(stack_topics),
                "topic_status": active_node.status if active_node else "active",
                "subtopics": [self.topic_tree[st].name for st in active_node.subtopics if st in self.topic_tree] if active_node else [],
                "waiting_question": active_node.waiting_question if active_node else None,
                "expected_reply": active_node.expected_reply if active_node else None,
            }

    def register_waiting_question(self, question: str, expected_reply: Optional[str] = None):
        """Registers a pending question asked by Vivy for topic follow-up tracking."""
        with self._lock:
            if self.active_topic_id and self.active_topic_id in self.topic_tree:
                node = self.topic_tree[self.active_topic_id]
                node.waiting_question = question
                node.expected_reply = expected_reply
                node.status = "waiting_user_reply"

    def _extract_topic_keyword(self, user_text: str, categories: List[str], mem: dict) -> str:
        u = user_text.strip()
        u_lower = u.lower()

        # Check explicit topic shift regex
        m = re.search(r"(?:talk about|speaking of|switch to|regarding|topic of)\s+([a-zA-Z0-9\s]{3,25})(?:[.,!?]|$)", u, re.IGNORECASE)
        if m:
            return m.group(1).strip().capitalize()

        # Check domain categories
        category_topic_map = {
            "recipe": "Cooking & Recipes",
            "health": "Health & Well-being",
            "technical": "Technical & Programming",
            "knowledge": "General Knowledge",
            "food_need": "Food & Nutrition",
            "flirting": "Romance & Flirting",
            "comfort": "Emotional Support",
            "joke": "Humor & Entertainment",
            "greeting": "Greeting & Catching Up"
        }
        for cat in categories or []:
            if cat in category_topic_map:
                return category_topic_map[cat]

        # Use current memory topic if defined
        if mem.get("current_topic"):
            return mem.get("current_topic")

        return "General Conversation"

    def _is_subtopic_of(self, child_candidate: str, parent_topic: str) -> bool:
        c = child_candidate.lower()
        p = parent_topic.lower()
        if c == p:
            return True
        parent_sub_keywords = {
            "cooking & recipes": ["recipe", "ingredient", "spice", "chicken", "baking", "food", "kitchen"],
            "technical & programming": ["code", "python", "bug", "git", "api", "database", "ai"],
            "health & well-being": ["symptom", "pain", "doctor", "sleep", "medicine", "diet"]
        }
        keywords = parent_sub_keywords.get(p, [])
        return any(kw in c for kw in keywords)

    def _restore_from_memory(self, mem: dict):
        topic_data = mem.get("topic_tracker_state", {})
        if topic_data and isinstance(topic_data, dict):
            tree_data = topic_data.get("topic_tree", {})
            for tid, node_dict in tree_data.items():
                if tid not in self.topic_tree:
                    self.topic_tree[tid] = TopicNode.from_dict(node_dict)
            self.active_topic_id = topic_data.get("active_topic_id", self.active_topic_id)
            self.previous_topic_name = topic_data.get("previous_topic_name", self.previous_topic_name)
            self.stack.load_from_list(topic_data.get("conversation_stack", []))

    def _sync_to_memory(self, mem: dict):
        if self.active_topic_id and self.active_topic_id in self.topic_tree:
            mem["current_topic"] = self.topic_tree[self.active_topic_id].name
        
        stack_topics = self.stack.get_stack_topics(self.topic_tree)
        mem["conversation_stack"] = stack_topics
        mem["topic_tracker_state"] = {
            "active_topic_id": self.active_topic_id,
            "previous_topic_name": self.previous_topic_name,
            "conversation_stack": self.stack.to_list(),
            "topic_tree": {tid: node.to_dict() for tid, node in list(self.topic_tree.items())[-20:]}
        }

def get_topic_tracker() -> TopicTracker:
    return TopicTracker.get_instance()
