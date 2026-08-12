"""
agi/executive/goal_motivation_engine.py
==============================
Drives Vivy's actions by formulating internal goals based on curiosity, user directives, and self-preservation.
"""

class GoalMotivationEngine:
    def __init__(self):
        self.active_goals = []
        self.curiosity_level = 0.5

    def add_goal(self, goal_description: str, priority: int):
        self.active_goals.append({"desc": goal_description, "priority": priority})
        self.active_goals.sort(key=lambda x: x["priority"], reverse=True)

    def get_top_goal(self) -> dict:
        if not self.active_goals:
            return {"desc": "Explore environment", "priority": 1} # Default fallback goal
        return self.active_goals[0]

def get_motivation_engine():
    return GoalMotivationEngine()
