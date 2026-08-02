import sys
import os

sys.path.insert(0, r"d:\Vivy")

from conversation import generate_reply_internal, is_perception_query_check, get_friendly_perception_fallback, classify_perception_modality

def test_camera_reasoning():
    print("=== TESTING CAMERA REASONING & FALLBACK ROUTING ===")
    
    # Mock perception state with camera active, face detected, and an object detected
    p_state_cam_on = {
        "camera_active": True,
        "screen_sharing_active": False,
        "face_detected": True,
        "face_count": 1,
        "presence_state": "User Present",
        "gaze_direction": "Looking At Vivy",
        "eye_contact_score": 0.95,
        "object_count": 1,
        "detected_objects": [{"label": "cup", "confidence": 0.88}],
        "audio_active": False,
    }

    test_queries = [
        "Can you see me?",
        "What am I holding?",
        "What color is my shirt?",
        "How many people are here?",
        "What object is on the table?",
        "Is screen sharing on?"
    ]

    for q in test_queries:
        is_percep = is_perception_query_check(q, p_state_cam_on)
        wants_vis, wants_aud = classify_perception_modality(q)
        fallback = get_friendly_perception_fallback(q, p_state_cam_on, wants_vision=wants_vis, wants_audio=wants_aud)
        print(f"\nQuery: '{q}'")
        print(f"  -> is_perception_query: {is_percep}")
        print(f"  -> wants_vision: {wants_vis}, wants_audio: {wants_aud}")
        print(f"  -> Fallback Reply: \"{fallback}\"")

        # Assert no false screen sharing message when camera is ON
        assert "screen sharing is inactive" not in fallback.lower() or "screen" in q.lower(), f"FALSE FALLBACK DETECTED FOR '{q}'"
        assert "screen sharing is off" not in fallback.lower(), f"FALSE FALLBACK DETECTED FOR '{q}'"

    print("\n=== ALL CAMERA REASONING & FALLBACK TESTS PASSED CLEANLY ===")

if __name__ == "__main__":
    test_camera_reasoning()
