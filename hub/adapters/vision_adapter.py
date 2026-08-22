"""
Vivy Hub - Vision Adapter
Bridges Hub remote requests into the local Vivy perception pipeline.
"""
import threading
import asyncio

class VisionAdapter:
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        # We would lazily import or get a reference to the local camera_manager or fusion_engine
        pass
        self._remote_sessions = {}

    @classmethod
    def get_instance(cls) -> "VisionAdapter":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance
            
    async def execute(self, payload: dict, device_id: str = "unknown") -> dict:
        """
        Takes image bytes from the payload, pushes it through local pipeline, returns gaze coords.
        """
        if "image" not in payload:
            return {"error": "Missing image in payload"}
            
        print("[VisionAdapter] Injecting remote frame into local perception pipeline...")
        # Get the global camera manager and run the process_frame contract
        # We run it with is_remote=True so it does not update the primary hub's global presence state!
        from perception.camera_manager import get_camera_manager, PerceptionSessionState
        manager = get_camera_manager()
        
        if device_id not in self._remote_sessions:
            self._remote_sessions[device_id] = PerceptionSessionState()
        session_state = self._remote_sessions[device_id]
        
        # This will synchronously run the ML models and return the perception state dict
        # without firing global events.
        import asyncio
        loop = asyncio.get_event_loop()
        system_state = await loop.run_in_executor(None, manager.process_frame, payload["image"], True, session_state)
        
        # Extract the fields required for vision.gaze
        gaze = system_state.get("gaze", {})
        
        return {
            "gaze_x": gaze.get("gaze_x", 0.0),
            "gaze_y": gaze.get("gaze_y", 0.0),
            "gaze_direction": gaze.get("gaze_direction", "Unknown"),
            "confidence": 0.95 if system_state.get("face_count", 0) > 0 else 0.0,
            "faces_detected": system_state.get("face_count", 0),
            "eye_contact_score": gaze.get("eye_contact_score", 0.0)
        }
