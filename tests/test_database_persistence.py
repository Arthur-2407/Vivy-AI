import os
import sys
import tempfile
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from database.db_manager import DatabaseManager

def test_database_manager_operations():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        db = DatabaseManager(db_path=db_path)

        # Log emotion snapshot
        db.log_emotion_snapshot({"primary_emotion": "joy", "joy": 85.0, "calmness": 60.0})
        snapshots = db.get_recent_emotion_snapshots(limit=5)
        assert len(snapshots) == 1
        assert snapshots[0]["primary_emotion"] == "joy"
        assert snapshots[0]["joy"] == 85.0

        # Log affection history
        db.log_affection_history(level=35.0, stage="Acquaintance", warmth=40.0, trust=35.0, familiarity=30.0, delta=0.1, reason="sustained chat")
        db.log_affection_history(level=36.0, stage="Acquaintance", warmth=42.0, trust=36.0, familiarity=31.0, delta=0.1, reason="compliment")

        history = db.get_recent_affection_history(limit=5)
        assert len(history) == 2

        # Test rollback helper
        rolled_back = db.rollback_last_affection()
        assert rolled_back["affection_level"] == 35.0

        rem_history = db.get_recent_affection_history(limit=5)
        assert len(rem_history) == 1

    finally:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception as _err:
                print(f"[test_database_persistence.py] Silenced exception: {_err}")
