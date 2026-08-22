import unittest
from hub.sync_manager import SyncManager
from hub.event_log import EventLog

class TestHubSync(unittest.TestCase):
    def setUp(self):
        self.sync = SyncManager()
        self.log = EventLog.get_instance()
        # Clear state
        self.log._events.clear()
        self.log._sequence_counter = 0

    def test_event_syncing(self):
        device_id = "tablet_01"
        self.sync.register_device(device_id, 0)
        
        # Add 3 events
        self.log.append_event("sess1", "laptop", "conversation.message", {"text": "hello"})
        self.log.append_event("sess1", "laptop", "avatar.emotion", {"emotion": "joy"})
        self.log.append_event("sess1", "laptop", "action.execute", {"intent": "play_media"})
        
        # Sync to tablet
        events = self.sync.sync_to_device(device_id)
        self.assertEqual(len(events), 3)
        self.assertEqual(self.sync._device_cursors[device_id], 3)
        
        # Sync again, should be empty
        events2 = self.sync.sync_to_device(device_id)
        self.assertEqual(len(events2), 0)

if __name__ == "__main__":
    unittest.main()
