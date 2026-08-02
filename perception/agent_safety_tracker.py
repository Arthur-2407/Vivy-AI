"""
perception/agent_safety_tracker.py
==================================
Handles tracking of completed task steps in `.agent_progress.json`.
Supports resumable work — if the agent is stopped, it can pick up exactly
where it left off by calling resume_from_last() on startup.
"""

import os
import json
import time

PROGRESS_FILE = "d:/Vivy/.agent_progress.json"

STEPS = [
    # ── Phase 1 — Completed in previous session ──────────────────────────────
    "Safety Tracker Setup",
    "Screen capture JPEG quality upgrade",
    "Screen pipeline resampler and preprocessing upgrade",
    "Audio decoding stream accumulation implementation",
    "Dialogue routing triggers upgrade",
    "Reasoning leak prevention prompt upgrade",
    "System verification and testing",
    # ── Phase 2 — Current session (deep root-cause fixes) ─────────────────────
    "OCR truncation fix in perception_manager",
    "Context injector snapshot expansion",
    "Screen pipeline highlight detection",
    "Conversation intent router fix - is_perception_query_check",
    "Conversation classifier screen/audio_query categories",
    "Token budget boost for perception queries",
    "Agent safety tracker expansion",
    "Integration verification and testing",
]


def load_progress() -> dict:
    """Load the progress state from disk. Returns a fresh state if not found."""
    if not os.path.exists(PROGRESS_FILE):
        return {
            "current_step": STEPS[0],
            "steps_completed": [],
            "timestamp": time.time()
        }
    try:
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "current_step": STEPS[0],
            "steps_completed": [],
            "timestamp": time.time()
        }


def save_progress(current_step: str, completed_steps: list):
    """Persist the current progress to disk atomically."""
    data = {
        "current_step": current_step,
        "steps_completed": completed_steps,
        "timestamp": time.time()
    }
    try:
        tmp = PROGRESS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, PROGRESS_FILE)
    except Exception as e:
        print(f"[SafetyTracker] Error saving progress file: {e}")


def mark_step_complete(step_name: str):
    """Mark a named step as complete and advance current_step pointer."""
    progress = load_progress()
    completed = progress.get("steps_completed", [])
    if step_name not in completed:
        completed.append(step_name)

    # Determine the next pending step
    try:
        current_idx = STEPS.index(step_name)
    except ValueError:
        current_idx = -1

    next_step = (
        STEPS[current_idx + 1]
        if current_idx != -1 and current_idx + 1 < len(STEPS)
        else "Complete"
    )

    save_progress(next_step, completed)
    print(f"[SafetyTracker] Step '{step_name}' marked complete. Next: '{next_step}'.")


def resume_from_last() -> tuple[str, list]:
    """
    Return (current_step, completed_steps) so the agent knows exactly where
    to resume after an interruption.

    Usage:
        current, done = resume_from_last()
        if current not in done:
            # execute current step
            mark_step_complete(current)
    """
    progress = load_progress()
    current = progress.get("current_step", STEPS[0])
    completed = progress.get("steps_completed", [])
    # Guard: if current_step is "Complete", all steps are done
    if current == "Complete":
        print("[SafetyTracker] All steps already completed. Nothing to resume.")
    else:
        print(f"[SafetyTracker] Resuming from step: '{current}' "
              f"({len(completed)}/{len(STEPS)} steps done)")
    return current, completed


def get_pending_steps() -> list:
    """Return only the steps that have NOT yet been completed."""
    progress = load_progress()
    completed = set(progress.get("steps_completed", []))
    return [s for s in STEPS if s not in completed]


def is_step_done(step_name: str) -> bool:
    """Return True if the given step is already marked complete."""
    progress = load_progress()
    return step_name in progress.get("steps_completed", [])
