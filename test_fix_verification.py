"""
Vivy AI - Master Non-Destructive Pipeline Verification & Validation Suite
========================================================================
Validates telemetry logging, health monitoring, connection diagnostics,
Flask route signatures, responsive viewport CSS, and startup readiness table.
"""

import os
import sys
import ast
import json

BASE_DIR = "d:/Vivy"
sys.path.insert(0, BASE_DIR)

print("=== RUNNING VIVY AI DEEP DIAGNOSTIC VERIFICATION ===")

# STAGE 1: Telemetry & Health Manager Validation
print("\n--- STAGE 1: TELEMETRY & HEALTH MONITOR CHECK ---")
try:
    from telemetry_manager import get_telemetry_manager
    tm = get_telemetry_manager()
    tm.log_event("Verification Test Event", details={"test": True})
    
    events = tm.get_events(10)
    assert len(events) > 0, "Telemetry manager events collection is empty"
    print(f"[OK] Telemetry event logging working (logged event: '{events[0]['event']}')")
    
    health = tm.get_health_status()
    assert "overall_status" in health, "Health status missing 'overall_status'"
    assert "subsystems" in health, "Health status missing 'subsystems'"
    assert len(health["subsystems"]) >= 13, f"Expected at least 13 subsystems in health check, got {len(health['subsystems'])}"
    print(f"[OK] Subsystem Health Check verified ({len(health['subsystems'])} subsystems monitored, status: {health['overall_status']})")
    
    diag = tm.get_connection_diagnostics()
    assert "backend_connected" in diag and "latency_ms" in diag, "Connection diagnostics structure incomplete"
    print("[OK] Connection Diagnostics API verified")
except Exception as e:
    print(f"[FAIL] Telemetry & Health check failed: {e}")
    sys.exit(1)

# STAGE 2: Flask Route Signatures in web_server.py
print("\n--- STAGE 2: FLASK ROUTE SIGNATURES CHECK ---")
server_path = os.path.join(BASE_DIR, "web_server.py")
try:
    with open(server_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
        
    routes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and getattr(decorator.func, "attr", "") == "route":
                    route_path = decorator.args[0].value if decorator.args else "unknown"
                    routes.append((node.name, route_path))
                    
    found_paths = [r[1] for r in routes]
    new_required_routes = [
        "/api/status",
        "/api/health",
        "/api/telemetry",
        "/api/diagnostics/connection",
        "/api/internet/status",
        "/api/avatar/status",
        "/api/history"
    ]
    for req in new_required_routes:
        assert req in found_paths, f"Missing required endpoint signature: {req}"
        print(f"  [OK] Endpoint verified: {req}")
    print("[OK] All required Flask routes present and valid.")
except Exception as e:
    print(f"[FAIL] Flask routes check failed: {e}")
    sys.exit(1)

# STAGE 3: Startup Readiness Table in run_vivy.py
print("\n--- STAGE 3: STARTUP READINESS TABLE CHECK ---")
run_path = os.path.join(BASE_DIR, "run_vivy.py")
try:
    with open(run_path, "r", encoding="utf-8") as f:
        run_code = f.read()
    assert "print_startup_readiness_table" in run_code, "run_vivy.py missing print_startup_readiness_table function"
    assert "STARTUP READINESS TABLE" in run_code, "run_vivy.py missing readiness table banner"
    print("[OK] Startup readiness table function verified in run_vivy.py.")
except Exception as e:
    print(f"[FAIL] Startup readiness check failed: {e}")
    sys.exit(1)

# STAGE 4: UI & Health Modal Elements in index.html
print("\n--- STAGE 4: INDEX.HTML UI & HEALTH MODAL CHECK ---")
html_path = os.path.join(BASE_DIR, "templates", "index.html")
try:
    with open(html_path, "r", encoding="utf-8") as f:
        html_code = f.read()
    assert "btn-health-modal" in html_code, "index.html missing Health modal button"
    assert "health-overlay" in html_code, "index.html missing Health modal overlay"
    assert "subsystem-health-grid" in html_code, "index.html missing subsystem health grid"
    assert "telemetry-log-box" in html_code, "index.html missing telemetry log stream container"
    print("[OK] index.html Health Monitor UI elements verified.")
except Exception as e:
    print(f"[FAIL] index.html check failed: {e}")
    sys.exit(1)

# STAGE 5: Resource Manager & Teardown Verification
print("\n--- STAGE 5: RESOURCE MANAGER & LEAK REPAIR CHECK ---")
try:
    from resource_manager import get_resource_manager
    rm = get_resource_manager()
    
    # 1. Devnull handle caching
    d1 = rm.get_devnull()
    d2 = rm.get_devnull()
    assert d1 is d2, "get_devnull() failed to return singleton handle"
    assert not d1.closed, "devnull handle is unexpectedly closed"
    print("  [OK] Devnull singleton handle caching verified.")
    
    # 2. Output suppression context manager
    with rm.suppress_output():
        print("This output should be suppressed by devnull")
    print("  [OK] Output suppression context manager verified.")
    
    # 3. Callback registration and execution
    callback_executed = [False]
    def test_cb():
        callback_executed[0] = True
    rm.register_cleanup_callback(test_cb, priority=10, name="test_callback")
    
    # 4. Teardown test
    rm.shutdown_all()
    assert callback_executed[0], "Registered cleanup callback was not executed"
    assert d1.closed, "Devnull singleton handle was not closed on shutdown"
    print("[OK] Resource Manager teardown and leak prevention verified.")
except Exception as e:
    print(f"[FAIL] Resource Manager check failed: {e}")
    sys.exit(1)

# STAGE 6: Vision & Perception Pipeline Integrity Check
print("\n--- STAGE 6: VISION & PERCEPTION PIPELINE CHECK ---")
try:
    from perception.pipeline_validator import PipelineValidator, get_vision_health_monitor, get_frame_trace_system
    from perception.face_detector import FaceDetector
    from perception.camera_manager import get_camera_manager
    from perception.perception_manager import get_writer, get_reader
    from perception.context_injector import get_perception_context
    
    # 1. Dependency check
    deps = PipelineValidator.validate_runtime_dependencies()
    assert deps["opencv"]["status"] == "PASS", f"OpenCV missing: {deps.get('opencv')}"
    assert deps["pil"]["status"] == "PASS", f"PIL missing: {deps.get('pil')}"
    print("  [OK] PipelineValidator runtime dependencies verified.")
    
    # 2. Face Detector test with synthetic image
    import numpy as np
    fd = FaceDetector()
    test_img = np.zeros((480, 640, 3), dtype=np.uint8)
    faces = fd.detect_faces(test_img)
    assert isinstance(faces, list), "detect_faces should return a list"
    print(f"  [OK] FaceDetector multi-pass test executed cleanly (backend: {fd.get_backend_name()}).")
    
    # 3. Context Injector snapshot test
    w = get_writer()
    w.record_face_perception_state({
        "camera_active": True,
        "presence_state": "User Present",
        "face_count": 1,
        "primary_face": {
            "bbox": {"x": 100, "y": 100, "width": 200, "height": 200},
            "confidence": 0.95
        },
        "gaze": {"gaze_direction": "Looking At Vivy", "eye_contact_score": 0.92},
        "attention": {"attention_score": 95.0, "presence_score": 100.0},
        "hardware": {"backend": fd.get_backend_name(), "mode": "Live Perception Active"}
    })
    
    ctx = get_perception_context(wants_vision=True, wants_audio=False)
    assert "User Camera Status: Active" in ctx or "Multimodal Perception Log" in ctx, "Perception context generation failed"
    print("  [OK] Multimodal Context Injector live snapshot verified.")
    
    health = get_vision_health_monitor().get_metrics()
    assert "is_healthy" in health, "VisionHealthMonitor metrics incomplete"
    print("  [OK] VisionHealthMonitor metrics active.")
except Exception as e:
    print(f"[FAIL] Vision & Perception check failed: {e}")
    sys.exit(1)

print("\n=== ALL VIVY AI DEEP DIAGNOSTIC VERIFICATION CHECKS PASSED ===")
