import os
import sqlite3
import time
import json
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "shared", "vivy_state.db")

class DatabaseManager:
    """
    SQLite Database Manager for Vivy AI state persistence, metric snapshots,
    relationship milestones, loneliness tracking, and rollback capabilities.
    Operates thread-safely with connection pooling per thread.
    """
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _get_connection(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = self._get_connection()
        with conn:
            # Emotion snapshots table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS emotion_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    primary_emotion TEXT,
                    joy REAL DEFAULT 0,
                    curiosity REAL DEFAULT 0,
                    empathy REAL DEFAULT 0,
                    calmness REAL DEFAULT 0,
                    excitement REAL DEFAULT 0,
                    sadness REAL DEFAULT 0,
                    energy REAL DEFAULT 0,
                    frustration REAL DEFAULT 0,
                    confidence REAL DEFAULT 0,
                    anxiety REAL DEFAULT 0,
                    focus REAL DEFAULT 0,
                    playfulness REAL DEFAULT 0
                )
            """)

            # Affection history table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS affection_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    affection_level REAL NOT NULL,
                    stage_label TEXT NOT NULL,
                    warmth REAL DEFAULT 0,
                    trust REAL DEFAULT 0,
                    familiarity REAL DEFAULT 0,
                    delta REAL DEFAULT 0,
                    reason TEXT
                )
            """)

            # Relationship milestones table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS relationship_milestones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    milestone_name TEXT NOT NULL,
                    details TEXT,
                    stage_unlocked TEXT
                )
            """)

            # Loneliness history table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS loneliness_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    loneliness_level REAL NOT NULL,
                    social_drive TEXT NOT NULL,
                    gap_seconds REAL DEFAULT 0
                )
            """)

            # Circadian logs table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS circadian_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    phase_name TEXT NOT NULL,
                    energy REAL DEFAULT 0,
                    tone_label TEXT,
                    sleep_mode INTEGER DEFAULT 0
                )
            """)

            # Conversation metrics table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    user_words INTEGER DEFAULT 0,
                    vivy_words INTEGER DEFAULT 0,
                    dialogue_mode TEXT,
                    sentiment TEXT
                )
            """)

            # Planner decisions table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS planner_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    target_length TEXT,
                    question_prob REAL,
                    callback_prob REAL,
                    tone TEXT,
                    empathy_level REAL,
                    proactive_flag INTEGER DEFAULT 0
                )
            """)

            # Planner evaluations table (Phase 16 & 17 Post-Response Analysis)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS planner_evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    overall_score REAL NOT NULL,
                    topic_continuity REAL,
                    memory_accuracy REAL,
                    emotion_consistency REAL,
                    affection_consistency REAL,
                    loneliness_consistency REAL,
                    internet_utility REAL,
                    planner_success REAL,
                    personality_consistency REAL,
                    feedback_summary TEXT
                )
            """)

            # Cognitive Orchestration logs table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orchestrator_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    user_text TEXT,
                    reply_text TEXT,
                    topic TEXT,
                    stage TEXT,
                    primary_emotion TEXT,
                    search_used INTEGER DEFAULT 0,
                    latency_ms REAL
                )
            """)

    def log_emotion_snapshot(self, vector: dict):
        try:
            conn = self._get_connection()
            with conn:
                conn.execute("""
                    INSERT INTO emotion_snapshots (
                        timestamp, primary_emotion, joy, curiosity, empathy, calmness,
                        excitement, sadness, energy, frustration, confidence, anxiety, focus, playfulness
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    time.time(),
                    vector.get("primary_emotion", "calmness"),
                    vector.get("joy", 50.0),
                    vector.get("curiosity", 50.0),
                    vector.get("empathy", 50.0),
                    vector.get("calmness", 50.0),
                    vector.get("excitement", 50.0),
                    vector.get("sadness", 0.0),
                    vector.get("energy", 50.0),
                    vector.get("frustration", 0.0),
                    vector.get("confidence", 50.0),
                    vector.get("anxiety", 0.0),
                    vector.get("focus", 50.0),
                    vector.get("playfulness", 50.0)
                ))
        except Exception as e:
            print(f"[DatabaseManager] Failed to log emotion snapshot: {e}")

    def log_affection_history(self, level: float, stage: str, warmth: float, trust: float, familiarity: float, delta: float = 0.0, reason: str = ""):
        try:
            conn = self._get_connection()
            with conn:
                conn.execute("""
                    INSERT INTO affection_history (
                        timestamp, affection_level, stage_label, warmth, trust, familiarity, delta, reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (time.time(), level, stage, warmth, trust, familiarity, delta, reason))
        except Exception as e:
            print(f"[DatabaseManager] Failed to log affection history: {e}")

    def log_relationship_milestone(self, milestone: str, details: str = "", stage_unlocked: str = ""):
        try:
            conn = self._get_connection()
            with conn:
                conn.execute("""
                    INSERT INTO relationship_milestones (timestamp, milestone_name, details, stage_unlocked)
                    VALUES (?, ?, ?, ?)
                """, (time.time(), milestone, details, stage_unlocked))
        except Exception as e:
            print(f"[DatabaseManager] Failed to log relationship milestone: {e}")

    def log_loneliness_history(self, level: float, social_drive: str, gap_seconds: float = 0.0):
        try:
            conn = self._get_connection()
            with conn:
                conn.execute("""
                    INSERT INTO loneliness_history (timestamp, loneliness_level, social_drive, gap_seconds)
                    VALUES (?, ?, ?, ?)
                """, (time.time(), level, social_drive, gap_seconds))
        except Exception as e:
            print(f"[DatabaseManager] Failed to log loneliness history: {e}")

    def log_circadian_state(self, phase: str, energy: float, tone: str, sleep_mode: bool):
        try:
            conn = self._get_connection()
            with conn:
                conn.execute("""
                    INSERT INTO circadian_logs (timestamp, phase_name, energy, tone_label, sleep_mode)
                    VALUES (?, ?, ?, ?, ?)
                """, (time.time(), phase, energy, tone, 1 if sleep_mode else 0))
        except Exception as e:
            print(f"[DatabaseManager] Failed to log circadian state: {e}")

    def log_planner_decision(self, decision: dict):
        try:
            conn = self._get_connection()
            with conn:
                conn.execute("""
                    INSERT INTO planner_decisions (
                        timestamp, target_length, question_prob, callback_prob, tone, empathy_level, proactive_flag
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    time.time(),
                    decision.get("target_length", "medium"),
                    decision.get("question_probability", 0.35),
                    decision.get("callback_probability", 0.20),
                    decision.get("tone", "friendly"),
                    decision.get("empathy_level", 0.50),
                    1 if decision.get("proactive_engagement", False) else 0
                ))
        except Exception as e:
            print(f"[DatabaseManager] Failed to log planner decision: {e}")

    def get_recent_affection_history(self, limit: int = 20) -> list:
        try:
            conn = self._get_connection()
            cursor = conn.execute("SELECT * FROM affection_history ORDER BY timestamp DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[DatabaseManager] Failed to fetch affection history: {e}")
            return []

    def get_recent_emotion_snapshots(self, limit: int = 20) -> list:
        try:
            conn = self._get_connection()
            cursor = conn.execute("SELECT * FROM emotion_snapshots ORDER BY timestamp DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[DatabaseManager] Failed to fetch emotion snapshots: {e}")
            return []

    def log_planner_evaluation(self, eval_data: dict):
        try:
            conn = self._get_connection()
            with conn:
                conn.execute("""
                    INSERT INTO planner_evaluations (
                        timestamp, overall_score, topic_continuity, memory_accuracy,
                        emotion_consistency, affection_consistency, loneliness_consistency,
                        internet_utility, planner_success, personality_consistency, feedback_summary
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    time.time(),
                    eval_data.get("overall_score", 1.0),
                    eval_data.get("topic_continuity", 1.0),
                    eval_data.get("memory_accuracy", 1.0),
                    eval_data.get("emotion_consistency", 1.0),
                    eval_data.get("affection_consistency", 1.0),
                    eval_data.get("loneliness_consistency", 1.0),
                    eval_data.get("internet_utility", 1.0),
                    eval_data.get("planner_success", 1.0),
                    eval_data.get("personality_consistency", 1.0),
                    eval_data.get("feedback_summary", "Evaluation passed")
                ))
        except Exception as e:
            print(f"[DatabaseManager] Failed to log planner evaluation: {e}")

    def log_orchestrator_turn(self, user_text: str, reply_text: str, topic: str, stage: str, primary_emotion: str, search_used: bool, latency_ms: float):
        try:
            conn = self._get_connection()
            with conn:
                conn.execute("""
                    INSERT INTO orchestrator_logs (
                        timestamp, user_text, reply_text, topic, stage, primary_emotion, search_used, latency_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    time.time(), user_text[:200], reply_text[:200], topic, stage, primary_emotion, 1 if search_used else 0, latency_ms
                ))
        except Exception as e:
            print(f"[DatabaseManager] Failed to log orchestrator turn: {e}")

    def rollback_last_affection(self) -> dict:
        """Rollback helper: restores previous affection snapshot if available."""
        try:
            conn = self._get_connection()
            with conn:
                cursor = conn.execute("SELECT * FROM affection_history ORDER BY timestamp DESC LIMIT 2")
                rows = cursor.fetchall()
                if len(rows) >= 2:
                    conn.execute("DELETE FROM affection_history WHERE id = ?", (rows[0]["id"],))
                    return dict(rows[1])
        except Exception as e:
            print(f"[DatabaseManager] Failed to rollback affection: {e}")
        return {}

_global_db_manager = None
def get_db_manager() -> DatabaseManager:
    global _global_db_manager
    if _global_db_manager is None:
        _global_db_manager = DatabaseManager()
    return _global_db_manager
