"""
Vivy AI — General Cognitive AI (AGI) Architecture Verification Suite
===================================================================
Rigorous test suite evaluating:
  1. Cognitive Blackboard (thread-safe shared memory & message bus)
  2. World Model & Dynamic Epistemic Graphs
  3. Semantic Knowledge Graph & Multihop Deduction
  4. Epistemic Belief Engine & Contradiction Discovery
  5. Meta-Cognition Reflexive Verification Loop
  6. Long-Horizon Planner & Objective Decomposition
  7. Skill System & Autonomous Capability Upgrades
  8. Continual Learning Engine & Curiosity Study Scheduling
  9. Safe Experiment Sandbox & Self-Improvement Evaluator
  10. Internal Counterfactual Simulation Engine
  11. End-to-End CognitiveOrchestrator AGI Integration
  12. Remedied Architectural Defects (BUG-01, BUG-02, BUG-04)
"""

import os
import sys
import json
import time
import unittest
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from agi.blackboard import CognitiveBlackboard, get_cognitive_blackboard
from agi.world_model import WorldModel, get_world_model
from agi.knowledge_graph import KnowledgeGraph, get_knowledge_graph
from agi.belief_engine import BeliefEngine, get_belief_engine
from agi.meta_cognition import MetaCognitionEngine, get_meta_cognition
from agi.long_horizon_planner import LongHorizonPlanner, get_long_horizon_planner
from agi.skill_system import SkillSystem, get_skill_system
from agi.learning_engine import LearningEngine, get_learning_engine
from agi.experiment_engine import ExperimentEngine, get_experiment_engine
from agi.simulation_engine import SimulationEngine, get_simulation_engine
from agi.cognitive_core import GeneralCognitiveCore, get_cognitive_core
from cognitive_orchestrator import get_cognitive_orchestrator
from emotion.emotion_engine import EmotionEngine

class TestVivyAGISubsystems(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_cognitive_blackboard(self):
        bb = CognitiveBlackboard()
        bb.publish_state("test_channel", {"value": 42}, source_engine="UnitTest")
        state = bb.get_state("test_channel")
        self.assertIsNotNone(state)
        self.assertEqual(state["value"], 42)

        bb.assert_hypothesis("h_test", "User enjoys building AI", confidence=0.9, source_engine="UnitTest")
        hyp = bb.get_active_hypotheses()
        self.assertTrue(len(hyp) > 0)
        self.assertEqual(hyp[0]["proposition"], "User enjoys building AI")
        
        snap = bb.synthesize_cognitive_snapshot()
        self.assertIn("test_channel", snap)
        self.assertIn("active_hypotheses", snap)

    def test_02_world_model(self):
        path = os.path.join(self.temp_dir.name, "wm.json")
        wm = WorldModel(storage_path=path)
        wm.update_node("user", "current_topic_focus", "AGI Architecture", confidence=0.95)
        graph = wm.query_graph("user")
        self.assertEqual(graph.get("current_topic_focus"), "AGI Architecture")
        self.assertTrue(wm.save_to_disk())
        self.assertTrue(os.path.exists(path))

    def test_03_knowledge_graph_multihop(self):
        path = os.path.join(self.temp_dir.name, "kg.json")
        kg = KnowledgeGraph(storage_path=path)
        kg.add_triple("Vivy", "uses", "Python", confidence=1.0)
        kg.add_triple("Python", "powers", "General Cognition", confidence=1.0)
        hops = kg.query_multihop("Vivy", max_hops=2)
        self.assertTrue(len(hops) >= 2)
        self.assertTrue(any("General Cognition" in h for h in hops))

    def test_04_belief_engine_contradictions(self):
        path = os.path.join(self.temp_dir.name, "beliefs.json")
        be = BeliefEngine(storage_path=path)
        b1_id = be.assert_belief("User likes simple bots", confidence=0.8)
        b2_id = be.assert_belief("User hates simple bots", confidence=0.9)
        # Verify contradiction flagged and older belief confidence reduced
        self.assertIn(b1_id, be.beliefs[b2_id].get("contradictions", []))
        self.assertLess(be.beliefs[b1_id]["confidence"], 0.8)

    def test_05_meta_cognition_reflexive_loop(self):
        mc = MetaCognitionEngine()
        user_msg = "I have a terrible fever and feel really sad today."
        candidate = "That is noted. Have you checked the latest software update?"
        plan = {"tone": "empathetic", "relationship_stage": "Bonded"}
        mem = {}
        refined, telemetry = mc.evaluate_and_refine(user_msg, candidate, plan, mem)
        self.assertTrue(telemetry["was_refined"])
        self.assertTrue(any(w in refined.lower() for w in ["sorry", "hear you", "feel", "hope"]))

    def test_06_long_horizon_planner(self):
        path = os.path.join(self.temp_dir.name, "goals.json")
        lp = LongHorizonPlanner(storage_path=path)
        g_id = lp.create_goal(title="Build Cognitive Monologue", description="Implement deep internal narrative loops.", target_days=14)
        self.assertIsNotNone(g_id)
        self.assertIn(g_id, lp.goals)
        lp.update_task_progress(g_id, milestone_idx=0, task_idx=0, status="completed")
        self.assertGreater(lp.goals[g_id]["progress_percentage"], 0.0)

    def test_07_skill_system_progression(self):
        path = os.path.join(self.temp_dir.name, "skills.json")
        sk = SkillSystem(storage_path=path)
        # Advance xp until tier upgrade occurs
        sk.skills["test_skill"] = {"level": 1, "xp": 85.0, "next_tier_xp": 100.0, "success_rate": 0.8}
        res = sk.evaluate_and_upgrade_skill("test_skill", success=True, xp_gain=20.0)
        self.assertEqual(res["level"], 2)

    def test_08_continual_learning_curiosity(self):
        path = os.path.join(self.temp_dir.name, "learning.json")
        le = LearningEngine(storage_path=path)
        le.log_interaction_evaluation("What is differential geometric quantization?", "I do not know.", eval_score=0.4, topic="Quantum Topology")
        hint = le.get_curiosity_prompt_hint()
        self.assertIn("Quantum Topology", hint)

    def test_09_safe_experiment_sandbox(self):
        ee = ExperimentEngine()
        base = {"alpha": 0.5, "beta": 0.5}
        cand = {"alpha": 0.8, "beta": 0.7}
        deployed, cfg, b_score, c_score = ee.run_sandbox_experiment("parameter_test", base, cand)
        self.assertTrue(deployed)
        self.assertEqual(cfg["alpha"], 0.8)

    def test_10_internal_simulation(self):
        sim = SimulationEngine()
        plan_a = {"tone": "warm and deeply empathetic", "relationship_stage": "Bonded"}
        plan_b = {"tone": "brisk and purely analytical", "relationship_stage": "Bonded"}
        winner, label, scores = sim.simulate_and_select_plan("I am exhausted and everything failed today.", plan_a, plan_b, {})
        self.assertIn("Plan A", label)
        self.assertGreater(scores["score_a"], scores["score_b"])

    def test_11_cognitive_orchestrator_integration(self):
        orch = get_cognitive_orchestrator()
        mem = {"relationship": {"score": 55}, "name": "Partner"}
        res = orch.orchestrate_turn_planning("Can you help me fix this Python script?", ["code", "question"], mem)
        self.assertIn("plan", res)
        self.assertIn("agi_cognitive_grounding", res["plan"])
        
        post_res = orch.orchestrate_post_response("Thanks!", "You're very welcome!", res["plan"], mem)
        self.assertIsNotNone(post_res)

    def test_12_remediated_defects(self):
        # Verify BUG-02 fix in EmotionEngine GRU tensor handling
        ev_initial = {"joy": 50.0, "trust": 50.0, "anticipation": 50.0}
        emo = EmotionEngine(ev_initial)
        # Ensure update_vector does not throw dimension mismatch exceptions when calling GRU
        new_vec = emo.update_vector(["joke", "compliment"], {}, {})
        self.assertIn("joy", new_vec)
        self.assertGreater(new_vec.get("joy", 0), 45.0)

if __name__ == "__main__":
    unittest.main()
