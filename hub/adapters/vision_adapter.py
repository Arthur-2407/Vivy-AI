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
            
    async def execute(self, payload: dict, device_id: str = "unknown", capability_id: str = "vision.gaze") -> dict:
        """
        Takes image bytes from the payload, pushes it through local pipeline, returns perception state.
        """
        if "image" not in payload:
            return {"error": "Missing image in payload"}
            
        print(f"[VisionAdapter] Injecting remote frame for {capability_id} into local perception pipeline...")
        from perception.camera_manager import get_camera_manager, PerceptionSessionState
        manager = get_camera_manager()
        
        if device_id not in self._remote_sessions:
            self._remote_sessions[device_id] = PerceptionSessionState()
        session_state = self._remote_sessions[device_id]
        
        import asyncio
        loop = asyncio.get_event_loop()
        system_state = await loop.run_in_executor(None, manager.process_frame, payload["image"], True, session_state)
        
        # If the request is for the full stream/perception, return everything
        if capability_id == "vision.stream" or capability_id == "vision.all":
            # Sanitize numpy arrays or non-serializable objects if any
            return {
                "faces_detected": system_state.get("face_count", 0),
                "gaze": system_state.get("gaze", {}),
                "emotion": system_state.get("emotion", "neutral"),
                "objects": system_state.get("objects", []),
                "gestures": system_state.get("gestures", [])
            }
            
        # Extract specific fields based on capability
        if capability_id == "vision.gaze":
            gaze = system_state.get("gaze", {})
            return {
                "gaze_x": gaze.get("gaze_x", 0.0),
                "gaze_y": gaze.get("gaze_y", 0.0),
                "gaze_direction": gaze.get("gaze_direction", "Unknown"),
                "confidence": 0.95 if system_state.get("face_count", 0) > 0 else 0.0,
                "faces_detected": system_state.get("face_count", 0),
                "eye_contact_score": gaze.get("eye_contact_score", 0.0)
            }
        elif capability_id == "vision.face":
            return {"faces_detected": system_state.get("face_count", 0)}
        elif capability_id == "vision.emotion":
            return {"emotion": system_state.get("emotion", "neutral")}
        elif capability_id == "vision.objects":
            return {"objects": system_state.get("objects", [])}
        elif capability_id == "vision.gestures":
            return {"gestures": system_state.get("gestures", [])}
            
        return {"error": f"Unknown vision capability {capability_id}"}
