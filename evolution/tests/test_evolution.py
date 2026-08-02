"""
evolution/tests/test_evolution.py
======================================
Unit test suite for the Vivy AI Self-Evolution package.
"""

import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

class TestSelfEvolutionSubsystem(unittest.TestCase):
    def test_perception_layer(self):
        from evolution.perception_layer import get_perception_layer
        perc = get_perception_layer()
        exp = perc.record_experience(
            user_input="Hello Vivy",
            system_reply="Hi there!",
            emotion_label="happy",
            rie_score=0.9,
            latency_seconds=0.3
        )
        self.assertIsNotNone(exp.experience_id)
        self.assertGreater(perc.get_buffer_size(), 0)

    def test_adaptation_engine(self):
        from evolution.adaptation_engine import get_adaptation_engine
        engine = get_adaptation_engine()
        policy = engine.get_active_policy()
        self.assertIn("prompt_style", policy)

    def test_diagnosis_engine(self):
        from evolution.diagnosis_engine import get_diagnosis_engine
        diag = get_diagnosis_engine()
        report = diag.diagnose_system_health()
        self.assertIsNotNone(report.timestamp)

    def test_correction_engine(self):
        from evolution.correction_engine import get_correction_engine
        corr = get_correction_engine()
        patch = corr.generate_correction()
        # Non-fatal: if no drift detected, returns None
        self.assertTrue(patch is None or hasattr(patch, "patch_id"))

    def test_consolidation_layer(self):
        from evolution.consolidation_layer import get_consolidation_layer
        cons = get_consolidation_layer()
        res = cons.consolidate_experiences()
        self.assertIn("consolidated_count", res)

    def test_governance_layer(self):
        from evolution.governance_layer import get_governance_layer
        gov = get_governance_layer()
        appr, entry = gov.validate_and_approve("micro_patch", {"token_budget_cap": 800}, False, "test")
        self.assertTrue(appr)
        self.assertEqual(entry.status, "APPROVED")

    def test_orchestrator_loop(self):
        from evolution import get_evolution_orchestrator
        orch = get_evolution_orchestrator()
        result = orch.step_evolution_loop(
            user_input="Testing evolution",
            system_reply="Evolution active",
            emotion_label="neutral",
            rie_score=0.88,
            latency_seconds=0.4,
            circadian_phase="Afternoon"
        )
        self.assertIn("loop_count", result)
        self.assertGreaterEqual(result["loop_count"], 1)

if __name__ == "__main__":
    unittest.main()
