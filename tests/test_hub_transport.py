import unittest
from hub.protocol.envelope import VivyMessage

class TestHubTransport(unittest.TestCase):
    def test_envelope_serialization(self):
        msg = VivyMessage(
            type="capability.request",
            device_id="test_node",
            capability="vision.gaze",
            payload={"test": 123}
        )
        j = msg.to_json()
        self.assertIn("vision.gaze", j)
        self.assertIn("test_node", j)
        
        msg2 = VivyMessage.from_json(j)
        self.assertEqual(msg2.type, "capability.request")
        self.assertEqual(msg2.payload["test"], 123)
        self.assertIsNotNone(msg2.message_id)

if __name__ == "__main__":
    unittest.main()
