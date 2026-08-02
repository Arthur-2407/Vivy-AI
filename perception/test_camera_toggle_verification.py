import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from perception.camera_manager import get_camera_manager, is_camera_disabled, set_camera_disabled
from perception.perception_manager import get_writer, get_reader, _shared_dir

def test_camera_toggle_cross_process_sync():
    print("[TEST] Starting Camera Toggle Cross-Process Sync Verification...")
    cam = get_camera_manager()

    # Step 1: Explicitly enable and start camera
    set_camera_disabled(False)
    assert not is_camera_disabled(), "camera_disable.txt should not exist after set_camera_disabled(False)"
    
    # Step 2: Stop camera (Simulating UI "Turn Camera OFF")
    cam.stop_camera()
    assert is_camera_disabled(), "camera_disable.txt MUST exist after stop_camera()"
    assert not cam.is_active(), "cam.is_active() MUST return False when camera is disabled"
    print("[PASS] Camera stop creates camera_disable.txt and returns is_active() == False")

    # Step 3: Attempt start_camera() while disabled (Simulating run_vivy startup while disabled)
    started = cam.start_camera()
    assert not started, "start_camera() MUST return False when camera_disable.txt exists"
    assert not cam.is_active(), "cam.is_active() MUST remain False when start_camera() is blocked by sentinel"
    print("[PASS] Auto-start blocked successfully when camera is disabled")

    # Step 4: Re-enable camera and start (Simulating UI "Turn Camera ON")
    set_camera_disabled(False)
    assert not is_camera_disabled(), "camera_disable.txt removed"
    
    # Simulate frame ingestion
    ingested = cam.ingest_external_frame("data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=")
    assert ingested, "External frame ingestion should succeed when camera is enabled"
    assert cam.is_active(), "cam.is_active() MUST return True when frames arrive"
    print("[PASS] Camera re-enabled and active stream restored successfully")

    # Step 5: Stop camera clean-up
    cam.stop_camera()
    assert not cam.is_active(), "Camera stopped cleanly"
    print("[PASS] All Camera Toggle Verification assertions passed cleanly!")

if __name__ == "__main__":
    test_camera_toggle_cross_process_sync()
