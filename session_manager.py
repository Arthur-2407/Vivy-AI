"""
Vivy AI — Session Isolation Manager (v1.0)
Manages user sessions, ensuring visible conversation history is isolated per execution/session
while preserving persistent long-term memory across restarts.
"""
import os
import sys
import time
import uuid
import json
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(BASE_DIR, "shared")

class UserSession:
    """Represents an isolated active user session."""
    def __init__(self, session_id: str = None):
        self.session_id = session_id or f"session_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        self.created_at = time.time()
        self.last_active = time.time()
        
        # Ephemeral session-isolated structures
        self.display_history = []     # Formatted strings or UI turns for active chat window
        self.session_messages = []    # Raw turns [{"role": "user"/"assistant", "content": "...", "timestamp": float}]
        self.temporary_context = {}   # Ephemeral turn state (active task, working notes)
        self.metadata = {
            "turn_count": 0,
            "input_modes": [],
            "last_emotion": "neutral"
        }

    def add_user_message(self, text: str, source: str = "text"):
        """Record user input turn in active session."""
        self.last_active = time.time()
        self.metadata["turn_count"] += 1
        if source not in self.metadata["input_modes"]:
            self.metadata["input_modes"].append(source)
            
        turn_entry = {
            "role": "user",
            "content": text,
            "source": source,
            "timestamp": self.last_active
        }
        self.session_messages.append(turn_entry)
        self.display_history.append(f"You: {text}")

    def add_assistant_reply(self, reply: str, emotion: str = "neutral"):
        """Record Vivy reply turn in active session."""
        self.last_active = time.time()
        self.metadata["last_emotion"] = emotion
        
        turn_entry = {
            "role": "assistant",
            "content": reply,
            "emotion": emotion,
            "timestamp": self.last_active
        }
        self.session_messages.append(turn_entry)
        self.display_history.append(f"Vivy: {reply}")

    def get_visible_history(self) -> list:
        """Return visible history turns for UI / CLI output."""
        return list(self.display_history)

    def get_recent_dialogue(self, max_turns: int = 10) -> list:
        """Return formatted dialogue history for context builder."""
        return list(self.display_history[-max_turns:])

    def clear_visible_history(self):
        """Clear visible chat history."""
        self.display_history.clear()

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "display_history": self.display_history,
            "session_messages": self.session_messages,
            "temporary_context": self.temporary_context,
            "metadata": self.metadata
        }

class SessionManager:
    """Global manager orchestrating user session lifecycle and session isolation."""
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self._current_session = None
        self._session_history_dir = os.path.join(SHARED_DIR, "sessions")
        os.makedirs(self._session_history_dir, exist_ok=True)
        self.start_new_session()

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def start_new_session(self) -> UserSession:
        """Create a fresh user session with completely isolated visible history."""
        with self._lock:
            if self._current_session is not None:
                self._save_session_archive(self._current_session)
                
            self._current_session = UserSession()
            print(f"[SessionManager] New session created: {self._current_session.session_id} (Visible history isolated)")
            return self._current_session

    def get_active_session(self) -> UserSession:
        with self._lock:
            if self._current_session is None:
                self._current_session = UserSession()
            return self._current_session

    def _save_session_archive(self, session: UserSession):
        """Archive closed session data for offline consolidation without polluting active UI chat."""
        try:
            filename = f"{session.session_id}.json"
            filepath = os.path.join(self._session_history_dir, filename)
            tmp_path = filepath + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, filepath)
        except Exception as e:
            print(f"[SessionManager] Error archiving session {session.session_id}: {e}")

    def shutdown(self):
        """Save pending session state on shutdown."""
        with self._lock:
            if self._current_session:
                self._save_session_archive(self._current_session)
                print(f"[SessionManager] Session {self._current_session.session_id} archived cleanly.")

def get_session_manager() -> SessionManager:
    return SessionManager.get_instance()
