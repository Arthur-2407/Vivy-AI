import unittest
from agi.executive.self_model import get_self_model
from agi.executive.goal_motivation_engine import get_motivation_engine
from agi.executive.agency_controller import get_agency_controller

class TestExecutiveAgency(unittest.TestCase):
    def test_self_model(self):
        model = get_self_model()
        state = model.get_state_summary()
        self.assertIn("helpful", state["identity"])
        self.assertTrue(state["capabilities"]["vision"])

    def test_goal_motivation_engine(self):
        engine = get_motivation_engine()
        engine.add_goal("Learn new skill", 10)
        engine.add_goal("Answer user", 5)
        top_goal = engine.get_top_goal()
        self.assertEqual(top_goal["desc"], "Learn new skill")

    def test_agency_controller(self):
        controller = get_agency_controller()
        # High motivation -> proactive
        mode = controller.determine_action_mode({"user_addressed_ai": False}, 0.8)
        self.assertEqual(mode, 'proactive')
        
        # User addressed -> react
        mode = controller.determine_action_mode({"user_addressed_ai": True}, 0.2)
        self.assertEqual(mode, 'react')

if __name__ == '__main__':
    unittest.main()
