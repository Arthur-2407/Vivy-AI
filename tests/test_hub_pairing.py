import unittest
from hub.pairing_manager import PairingManager
from hub.device_identity import TrustLevel

class TestHubPairing(unittest.TestCase):
    def setUp(self):
        self.pairing = PairingManager()

    def test_pairing_lifecycle(self):
        device_id = "test_phone_01"
        # 1. Initiate
        code = self.pairing.initiate_pairing(device_id)
        self.assertIsNotNone(code)
        
        # 2. Invalid code
        success, _ = self.pairing.complete_pairing(device_id, "wrong_code")
        self.assertFalse(success)
        
        # 3. Valid code
        success, key = self.pairing.complete_pairing(device_id, code)
        self.assertTrue(success)
        self.assertTrue(key.startswith("sk_"))
        
        # 4. Validate session
        self.assertTrue(self.pairing.validate_session(device_id, key))
        self.assertFalse(self.pairing.validate_session(device_id, "sk_invalid"))
        
        # 5. Revoke session
        self.pairing.revoke_session(device_id)
        self.assertFalse(self.pairing.validate_session(device_id, key))

if __name__ == "__main__":
    unittest.main()
