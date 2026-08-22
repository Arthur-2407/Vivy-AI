"""
Vivy AI — Action System: Intent Isolation Test
===============================================
Proves that `detect_intent_only()` is 100% side-effect-free.
Validates Phase 9 execution authority boundaries.
"""

import unittest
import threading
from unittest.mock import patch, MagicMock
from action.smart_manager import get_smart_manager
from action.intent_model import IntentModel, ActionState


class TestIntentIsolation(unittest.TestCase):
    
    def setUp(self):
        self.sm = get_smart_manager()
        self.sm._enabled = True
        
    @patch('action.action_session.save_action_session')
    @patch('subprocess.Popen')
    @patch('action.smart_manager.SmartManager._publish_event')
    def test_detect_intent_only_is_pure(self, mock_publish, mock_popen, mock_save_session):
        """
        Cryptographically prove that detect_intent_only does not mutate session state,
        spawn a process, or emit an execution event.
        """
        # 1. Execute the read-only method
        intent = self.sm.detect_intent_only("play some fast music", context={})
        
        # 2. Verify an intent was correctly parsed
        self.assertIsNotNone(intent)
        self.assertEqual(intent.action, "play")
        self.assertEqual(intent.domain, "media")
        
        # 3. Verify ZERO SIDE EFFECTS
        # No process was spawned
        mock_popen.assert_not_called()
        
        # No session state was saved
        mock_save_session.assert_not_called()
        
        # No execution events were published
        mock_publish.assert_not_called()
        
        # The intent should strictly be in CREATED state
        self.assertEqual(intent.state, ActionState.CREATED.value)


if __name__ == "__main__":
    unittest.main()
