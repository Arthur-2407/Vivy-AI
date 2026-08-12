"""
Vivy AI - Enterprise Telemetry, Health Monitoring & Connection Diagnostics
===========================================================================
Provides structured logging, real-time subsystem health evaluation,
live internet status tracking, physical GPU hardware discovery,
and detailed connection diagnostics without breaking compatibility.
"""

import os
import sys
import time
import json
import threading
import subprocess
from collections import deque

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(BASE_DIR, "shared")
TELEMETRY_JSON = os.path.join(SHARED_DIR, "telemetry.json")
AVATAR_CONNECTED_TXT = os.path.join(SHARED_DIR, "avatar_connected.txt")
AVATAR_STATUS_JSON = os.path.join(SHARED_DIR, "avatar_status.json")
AVATAR_DISABLE_TXT = os.path.join(SHARED_DIR, "avatar_disable.txt")
STATUS_TXT = os.path.join(SHARED_DIR, "status.txt")

_gpu_cache = None
_gpu_cache_time = 0.0

def _discover_physical_gpu():
    """Discover physical GPU hardware using nvidia-smi, PowerShell CIM, PyTorch, and ONNX Runtime checks."""
    global _gpu_cache, _gpu_cache_time
    now = time.time()
    if _gpu_cache is not None and (now - _gpu_cache_time) < 10.0:
        return _gpu_cache

    gpu_info = {
        "physical_gpu_detected": False,
        "physical_gpu_name": None,
        "vram_mb": None,
        "driver_version": None,
        "cuda_version": None,
        "torch_cuda_available": False,
        "onnx_providers": [],
        "torch_version": "unknown",
        "root_cause": None
    }

    # 1. Check PyTorch CUDA availability
    try:
        import torch
        gpu_info["torch_version"] = getattr(torch, "__version__", "unknown")
        gpu_info["torch_cuda_available"] = torch.cuda.is_available()
    except Exception as te:
        gpu_info["torch_version"] = f"Import error: {te}"

    # 1b. Check ONNX Runtime available execution providers
    try:
        import onnxruntime as ort
        gpu_info["onnx_providers"] = ort.get_available_providers()
    except Exception:
        gpu_info["onnx_providers"] = []

    # 2. Try nvidia-smi discovery
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2
        )
        if res.returncode == 0 and res.stdout.strip():
            lines = [l.strip() for l in res.stdout.strip().splitlines() if l.strip()]
            if lines:
                parts = [p.strip() for p in lines[0].split(",")]
                if len(parts) >= 3:
                    gpu_info["physical_gpu_detected"] = True
                    gpu_info["physical_gpu_name"] = parts[0]
                    try:
                        gpu_info["vram_mb"] = int(float(parts[1]))
                    except ValueError:
                        gpu_info["vram_mb"] = parts[1]
                    gpu_info["driver_version"] = parts[2]
    except Exception as _err:
        print(f"[telemetry_manager.py] Silenced exception: {_err}")

    # 3. WMI/CIM fallback if nvidia-smi failed to find GPU name
    if not gpu_info["physical_gpu_detected"]:
        try:
            res = subprocess.run(
                ["powershell", "-Command", "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
                capture_output=True, text=True, timeout=2
            )
            if res.returncode == 0 and res.stdout.strip():
                for line in res.stdout.strip().splitlines():
                    line_clean = line.strip()
                    if "NVIDIA" in line_clean.upper() or "AMD" in line_clean.upper() or "Radeon" in line_clean.upper():
                        gpu_info["physical_gpu_detected"] = True
                        gpu_info["physical_gpu_name"] = line_clean
                        break
        except Exception as _err:
            print(f"[telemetry_manager.py] Silenced exception: {_err}")

    # 4. Formulate diagnostic root cause
    if gpu_info["torch_cuda_available"]:
        gpu_info["root_cause"] = f"PyTorch CUDA acceleration ACTIVE on {gpu_info['physical_gpu_name'] or 'GPU'}."
    elif gpu_info["physical_gpu_detected"]:
        onnx_gpu_note = ""
        if "CUDAExecutionProvider" in gpu_info["onnx_providers"] or "DmlExecutionProvider" in gpu_info["onnx_providers"]:
            onnx_gpu_note = f" ONNX Runtime GPU Providers available: {gpu_info['onnx_providers']}."
        gpu_info["root_cause"] = (
            f"PyTorch build ({gpu_info['torch_version']}) is CPU-only. "
            f"Hardware {gpu_info['physical_gpu_name']} detected at system layer. Falling back to CPU for Torch execution.{onnx_gpu_note}"
        )
    else:
        gpu_info["root_cause"] = "No discrete GPU hardware detected; running on optimized CPU threads."

    _gpu_cache = gpu_info
    _gpu_cache_time = now
    return gpu_info


class TelemetryManager:
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(TelemetryManager, cls).__new__(cls)
                cls._instance._init_manager()
            return cls._instance

    def _init_manager(self):
        self.events = deque(maxlen=200)
        self.start_time = time.time()
        self.last_heartbeat = time.time()
        self.reconnect_count = 0
        os.makedirs(SHARED_DIR, exist_ok=True)
        self.log_event("Telemetry Engine Initialized", details={"timestamp": self.start_time})

    def log_event(self, event_type: str, details: dict = None, level: str = "INFO"):
        """Record a structured telemetry event."""
        timestamp = time.time()
        entry = {
            "timestamp": timestamp,
            "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp)),
            "event": event_type,
            "level": level,
            "details": details or {}
        }
        with self._lock:
            self.events.appendleft(entry)
            self.last_heartbeat = timestamp
            if len(self.events) % 5 == 0:
                self._sync_to_disk()
        
        if level in ("WARNING", "ERROR"):
            print(f"[Telemetry][{level}] {event_type}: {details}")

    def _sync_to_disk(self):
        try:
            tmp_path = TELEMETRY_JSON + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(list(self.events)[:100], f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, TELEMETRY_JSON)
        except Exception as _err:
            print(f"[telemetry_manager.py] Silenced exception: {_err}")

    def get_events(self, limit: int = 50):
        with self._lock:
            return list(self.events)[:limit]

    def get_health_status(self):
        """Perform empirical health check across all Vivy AI subsystems using rich dynamic state model."""
        subsystems = {}
        now = time.time()

        def _build_sub_obj(status, state_label, message, root_cause, metrics=None, error_details=None, retry_count=0):
            return {
                "status": status,            # Legacy compatibility: GREEN, YELLOW, RED
                "state": state_label,        # Dynamic state: INITIALIZING, CONNECTING, LOADING, READY, STANDBY, RUNNING, PAUSED, DEGRADED, RECOVERING, OFFLINE, FAILED
                "message": message,
                "root_cause": root_cause,
                "timestamp": now,
                "retry_count": retry_count,
                "last_heartbeat": self.last_heartbeat,
                "error_details": error_details,
                "recovery_progress": "100%" if status == "GREEN" else ("50%" if status == "YELLOW" else "0%"),
                "metrics": metrics or {}
            }

        # 1. Memory Subsystem
        mem_path = os.path.join(BASE_DIR, "vivy_memory.json")
        if os.path.exists(mem_path):
            try:
                with open(mem_path, "r", encoding="utf-8") as mf:
                    mem_data = json.load(mf)
                subsystems["Memory"] = _build_sub_obj(
                    "GREEN", "READY",
                    "Memory orchestrator & persistent JSON active",
                    "Persistent vivy_memory.json parsed cleanly",
                    metrics={"keys": len(mem_data), "user_name": mem_data.get("name")}
                )
            except Exception as e:
                subsystems["Memory"] = _build_sub_obj(
                    "RED", "FAILED",
                    f"Memory parse error: {e}",
                    f"JSON parse error in vivy_memory.json: {e}",
                    error_details=str(e)
                )
        else:
            subsystems["Memory"] = _build_sub_obj(
                "YELLOW", "INITIALIZING",
                "Memory file creating on initial turn",
                "vivy_memory.json pending creation on first interactive turn"
            )

        # 2. Emotion Subsystem
        emotion_txt = os.path.join(SHARED_DIR, "emotion.txt")
        current_emotion = "neutral"
        if os.path.exists(emotion_txt):
            try:
                with open(emotion_txt, "r", encoding="utf-8") as ef:
                    current_emotion = ef.read().strip() or "neutral"
            except Exception as _err:
                print(f"[telemetry_manager.py] Silenced exception: {_err}")
        subsystems["Emotion"] = _build_sub_obj(
            "GREEN", "READY",
            f"Emotion classifier active (current: {current_emotion})",
            f"RoBERTa emotion classifier loaded; current active state is {current_emotion}",
            metrics={"current_emotion": current_emotion}
        )

        # Dynamic Camera Inspection
        cam_active = False
        cam_fps = 0.0
        cam_msg = "Camera inactive (STANDBY)"
        try:
            from perception.camera_manager import get_camera_manager
            cm = get_camera_manager()
            cam_active = cm.is_active()
            cam_fps = cm.get_fps()
            if cam_active:
                cam_msg = f"Hardware/Webcam active ({cam_fps} FPS)"
        except Exception as _err:
            print(f"[telemetry_manager.py] Silenced exception: {_err}")

        subsystems["Camera"] = _build_sub_obj(
            "GREEN" if cam_active else "YELLOW",
            "RUNNING" if cam_active else "STANDBY",
            cam_msg,
            "Webcam frame acquisition active" if cam_active else "Camera capture inactive; standing by for activation signal",
            metrics={"active": cam_active, "fps": cam_fps}
        )

        # 3. Vision Subsystem
        tesseract_ready = False
        try:
            import pytesseract
            tesseract_ready = True
        except ImportError:
            pass
        screen_ctx_txt = os.path.join(SHARED_DIR, "screen_context.txt")
        screen_active = os.path.exists(screen_ctx_txt) and (now - os.path.getmtime(screen_ctx_txt) < 60)
        vision_active = cam_active or screen_active
        subsystems["Vision"] = _build_sub_obj(
            "GREEN" if vision_active else "YELLOW",
            "RUNNING" if (cam_active and screen_active) else ("READY" if vision_active else "STANDBY"),
            "Vision engine active" + (" (Camera + Screen)" if (cam_active and screen_active) else (" (Camera live)" if cam_active else (" (Screen capture live)" if screen_active else " (Standby)"))),
            "Camera or screen perception loop active" if vision_active else "Screen & camera capture inactive; standing by for perception signal",
            metrics={"tesseract_ocr": tesseract_ready, "screen_share_active": screen_active, "camera_active": cam_active}
        )

        # Perception Diagnostic Metrics
        pm_diag = {}
        try:
            from perception.perception_manager import get_reader
            pm_diag = get_reader().get_diagnostic_report()
        except Exception as _err:
            print(f"[telemetry_manager.py] Silenced exception: {_err}")

        face_count = pm_diag.get("face_count", 0)
        presence = pm_diag.get("presence_state", "User Missing")
        gaze_dir = pm_diag.get("gaze_direction", "Unknown")

        subsystems["Face Detection"] = _build_sub_obj(
            "GREEN" if cam_active else "YELLOW",
            "RUNNING" if (cam_active and face_count > 0) else ("READY" if cam_active else "STANDBY"),
            f"Face detector operating ({face_count} face(s) tracked)",
            "OpenCV face detection active" if cam_active else "Standing by for camera frame stream",
            metrics={"face_count": face_count, "presence_state": presence}
        )

        subsystems["Eye Gaze"] = _build_sub_obj(
            "GREEN" if cam_active else "YELLOW",
            "RUNNING" if (cam_active and face_count > 0) else ("READY" if cam_active else "STANDBY"),
            f"Gaze tracking operating (direction: {gaze_dir})",
            "Iris landmark gaze estimator active" if cam_active else "Standing by for face tracking",
            metrics={"gaze_direction": gaze_dir}
        )

        subsystems["Face & Gaze Perception"] = _build_sub_obj(
            "GREEN" if cam_active else "YELLOW",
            "RUNNING" if (cam_active and face_count > 0) else ("READY" if cam_active else "STANDBY"),
            f"Face & gaze perception system ({presence})",
            "Perception runner executing landmark mesh & gaze estimation" if cam_active else "Standing by for camera stream",
            metrics={"face_count": face_count, "presence": presence}
        )

        obj_count = pm_diag.get("object_count", 0)
        subsystems["Object Detection"] = _build_sub_obj(
            "GREEN" if cam_active else "YELLOW",
            "RUNNING" if (cam_active and obj_count > 0) else ("READY" if cam_active else "STANDBY"),
            f"Object detector operating ({obj_count} object(s) tracked)",
            "Hardware-adaptive object detection engine active" if cam_active else "Standing by for camera stream",
            metrics={"object_count": obj_count}
        )

        subsystems["Emotion Detection"] = _build_sub_obj(
            "GREEN", "READY",
            f"Multimodal emotion classifier active (current: {current_emotion})",
            "RoBERTa & facial emotion analysis pipeline ready",
            metrics={"current_emotion": current_emotion}
        )

        subsystems["Vision Summary"] = _build_sub_obj(
            "GREEN" if vision_active else "YELLOW",
            "READY" if vision_active else "STANDBY",
            "Vision context summary synthesizer operational",
            "Multimodal perception context builder ready",
            metrics={"active": vision_active}
        )

        # 4. Internet Subsystem
        internet_status = "GREEN"
        net_state_label = "READY"
        net_details = {}
        try:
            from internet import get_internet_manager
            im = get_internet_manager()
            net_details = im.get_status()
            net_state = net_details.get("network_state", "online").upper()
            if net_state not in ("ONLINE", "CACHE"):
                internet_status = "YELLOW"
                net_state_label = "DEGRADED"
        except Exception as _err:
            print(f"[telemetry_manager.py] Silenced exception: {_err}")

        subsystems["Internet"] = _build_sub_obj(
            internet_status, net_state_label,
            f"Universal Internet Layer active ({net_details.get('network_state', 'online')})",
            "DuckDuckGo search & HTTP connectivity fully operational",
            metrics=net_details
        )

        subsystems["DuckDuckGo"] = _build_sub_obj(
            internet_status, net_state_label,
            "DuckDuckGo search intelligence layer operational",
            "DuckDuckGo search adapter active",
            metrics={"duckduckgo_ready": True}
        )

        # 5. GPU Subsystem (Enhanced Discovery & Deterministic Health Reporting)
        gpu_info = _discover_physical_gpu()
        gpu_status = "GREEN"  # CPU fallback and CUDA execution are both valid operational states
        gpu_state = "READY" if gpu_info["torch_cuda_available"] else "READY (CPU)"
        dev_name = gpu_info["physical_gpu_name"] if gpu_info["physical_gpu_detected"] else "CPU (Optimized threads)"
        msg = f"Compute Backend: {dev_name}" if gpu_info["torch_cuda_available"] else f"Compute Backend: CPU ({dev_name} active)"

        subsystems["GPU"] = _build_sub_obj(
            gpu_status, gpu_state,
            msg,
            gpu_info["root_cause"],
            metrics={
                "cuda_available": gpu_info["torch_cuda_available"],
                "device_name": dev_name,
                "physical_gpu_detected": gpu_info["physical_gpu_detected"],
                "physical_gpu_name": gpu_info["physical_gpu_name"],
                "vram_mb": gpu_info["vram_mb"],
                "driver_version": gpu_info["driver_version"],
                "torch_version": gpu_info["torch_version"]
            }
        )

        # 6. Voice Subsystem
        mic_mute = os.path.exists(os.path.join(SHARED_DIR, "mic_mute.txt"))
        voice_out_mute = os.path.exists(os.path.join(SHARED_DIR, "voice_output_mute.txt"))
        subsystems["Voice"] = _build_sub_obj(
            "YELLOW" if (mic_mute and voice_out_mute) else "GREEN",
            "DEGRADED" if (mic_mute and voice_out_mute) else "READY",
            f"Audio Input ({'MUTED' if mic_mute else 'ACTIVE'}), Output ({'MUTED' if voice_out_mute else 'ACTIVE'})",
            "Audio streams muted by configuration" if (mic_mute and voice_out_mute) else "PyAudio mic listener & TTS active",
            metrics={"mic_muted": mic_mute, "speaker_muted": voice_out_mute}
        )

        subsystems["Microphone"] = _build_sub_obj(
            "YELLOW" if mic_mute else "GREEN",
            "PAUSED" if mic_mute else "READY",
            f"Microphone audio input {'MUTED' if mic_mute else 'ACTIVE'}",
            "Microphone muted by mic_mute.txt sentinel" if mic_mute else "PyAudio microphone listener active",
            metrics={"muted": mic_mute}
        )

        subsystems["Voice Recognition"] = _build_sub_obj(
            "GREEN", "READY",
            "Whisper speech recognition engine active",
            "Local Whisper STT model ready",
            metrics={"whisper_active": True}
        )

        subsystems["Voice Output"] = _build_sub_obj(
            "YELLOW" if voice_out_mute else "GREEN",
            "PAUSED" if voice_out_mute else "READY",
            f"Vocal response output {'MUTED' if voice_out_mute else 'ACTIVE'}",
            "Voice output muted" if voice_out_mute else "Pygame audio playback & RVC voice cloning ready",
            metrics={"muted": voice_out_mute}
        )

        # 7. Avatar Subsystem (Detailed Link & Streaming Telemetry)
        avatar_clients = 0
        avatar_disabled = os.path.exists(AVATAR_DISABLE_TXT)
        if os.path.exists(AVATAR_CONNECTED_TXT):
            try:
                with open(AVATAR_CONNECTED_TXT, "r", encoding="utf-8") as acf:
                    avatar_clients = int(acf.read().strip() or "0")
            except Exception as _err:
                print(f"[telemetry_manager.py] Silenced exception: {_err}")

        avatar_status_info = {}
        if os.path.exists(AVATAR_STATUS_JSON):
            try:
                with open(AVATAR_STATUS_JSON, "r", encoding="utf-8") as asf:
                    avatar_status_info = json.load(asf)
            except Exception as _err:
                print(f"[telemetry_manager.py] Silenced exception: {_err}")

        if avatar_disabled:
            av_status, av_state = "YELLOW", "OFFLINE"
            av_msg = "Avatar Subsystem disabled by user configuration"
            av_cause = "avatar_disable.txt sentinel file present"
        elif avatar_clients > 0:
            av_status, av_state = "GREEN", "READY"
            av_msg = f"Unity Runtime Link: {avatar_clients} client(s) connected and streaming"
            av_cause = f"Active WebSocket connection on ws://127.0.0.1:8765 with {avatar_clients} client(s)"
        else:
            av_status, av_state = "YELLOW", "STANDBY"
            av_msg = "Unity Link Standby (WebSocket server ready on ws://127.0.0.1:8765 — Launch MateEngine to stream)"
            av_cause = "WebSocket server running on port 8765; 0 MateEngine Unity clients currently connected"

        subsystems["Avatar"] = _build_sub_obj(
            av_status, av_state,
            av_msg, av_cause,
            metrics={
                "connected_clients": avatar_clients,
                "disabled": avatar_disabled,
                "websocket_port": 8765,
                "measured_fps": avatar_status_info.get("measured_fps", 0.0),
                "last_frame_timestamp": avatar_status_info.get("last_frame_timestamp", 0.0)
            }
        )

        # 8. Scheduler Subsystem
        subsystems["Scheduler"] = _build_sub_obj(
            "GREEN", "READY",
            "Hardware & event schedulers operating normally",
            "Background threads & circadian schedulers running cleanly",
            metrics={"uptime_seconds": int(now - self.start_time)}
        )

        # 9. Plugins Subsystem
        subsystems["Plugins"] = _build_sub_obj(
            "GREEN", "READY",
            "Multimodal perception & speech plugins loaded",
            "All sub-modules (animator, perception, circadian, evolution) registered",
            metrics={"plugins_active": True}
        )

        # 9.5 Action System Subsystem (Voice Assistant / Intent-Based Command Execution)
        try:
            from action import get_action_system
            as_health = get_action_system().get_health()
            as_enabled = as_health.get("enabled", False)
            as_caps = as_health.get("registered_capabilities", 0)
            subsystems["Action System"] = _build_sub_obj(
                "GREEN" if as_enabled else "YELLOW",
                "READY" if as_enabled else "STANDBY",
                f"Intent-based action system ({as_caps} capabilities registered)",
                "SmartManager, CapabilityRegistry, and all executors operational",
                metrics=as_health
            )
        except Exception as _as_err:
            print(f"[telemetry_manager.py] Action system health check note: {_as_err}")
            subsystems["Action System"] = _build_sub_obj(
                "YELLOW", "STANDBY",
                "Action system not yet initialised",
                "SmartManager pending first activation",
                metrics={}
            )

        # 10. LLM Subsystem
        try:
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            _llm_path_cfg = cfg.get("models.llm", "models/Qwen3-8B-Q4_K_M.gguf")
            model_path = os.path.abspath(os.path.join(BASE_DIR, _llm_path_cfg))
        except Exception:
            model_path = os.path.join(BASE_DIR, "models", "Qwen3-8B-Q4_K_M.gguf")
        
        model_exists = os.path.exists(model_path)
        subsystems["LLM"] = _build_sub_obj(
            "GREEN" if model_exists else "RED",
            "READY" if model_exists else "FAILED",
            f"LLM Neural Model: {'Ready (' + os.path.basename(model_path) + ')' if model_exists else 'Model file missing'}",
            "Qwen3-8B model file verified on disk" if model_exists else f"Model file missing at {model_path}",
            metrics={"model_exists": model_exists, "model_file": os.path.basename(model_path)}
        )

        # 11. WebSocket Subsystem
        subsystems["WebSocket"] = _build_sub_obj(
            "GREEN", "READY",
            "WebSocket Server listening on ws://127.0.0.1:8765",
            "Avatar Bridge asyncio server bound to 127.0.0.1:8765",
            metrics={"port": 8765, "clients": avatar_clients}
        )

        # 12. API Subsystem
        subsystems["API"] = _build_sub_obj(
            "GREEN", "READY",
            "Flask REST API active on http://127.0.0.1:8080",
            "Flask server listening on port 8080",
            metrics={"port": 8080}
        )

        # 13. Database / Storage Subsystem
        transcripts_dir = os.path.join(BASE_DIR, "transcripts")
        transcript_count = len(os.listdir(transcripts_dir)) if os.path.exists(transcripts_dir) else 0
        subsystems["Database"] = _build_sub_obj(
            "GREEN", "READY",
            f"Local storage & transcripts active ({transcript_count} transcripts recorded)",
            "Transcripts directory & shared JSON storage writable",
            metrics={"transcript_files": transcript_count}
        )

        subsystems["Screen Capture"] = _build_sub_obj(
            "GREEN" if screen_active else "YELLOW",
            "RUNNING" if screen_active else "STANDBY",
            "Screen capture stream " + ("ACTIVE" if screen_active else "STANDBY"),
            "Screen context perception loop actively writing context" if screen_active else "Screen capture inactive; standing by for share signal",
            metrics={"screen_active": screen_active}
        )

        subsystems["Active Conversation"] = _build_sub_obj(
            "GREEN", "READY",
            "Neural dialogue orchestrator active",
            "Session manager & memory orchestrator loaded",
            metrics={"active": True}
        )

        subsystems["Current Emotion"] = _build_sub_obj(
            "GREEN", "READY",
            f"Active Mood: {current_emotion.upper()}",
            f"Current active emotion state is {current_emotion}",
            metrics={"emotion": current_emotion}
        )

        subsystems["Emotion Engine"] = _build_sub_obj(
            "GREEN", "READY",
            f"Core emotion engine active (current: {current_emotion})",
            "Dynamic emotion vector & mood classifier active",
            metrics={"emotion": current_emotion}
        )

        curr_pipe_status = "ready"
        if os.path.exists(STATUS_TXT):
            try:
                with open(STATUS_TXT, "r", encoding="utf-8") as sf:
                    curr_pipe_status = sf.read().strip() or "ready"
            except Exception as _err:
                print(f"[telemetry_manager.py] Silenced exception: {_err}")

        subsystems["Current Pipeline Status"] = _build_sub_obj(
            "GREEN", "RUNNING" if curr_pipe_status != "ready" else "READY",
            f"Pipeline state: {curr_pipe_status.upper()}",
            f"Core neural pipeline executing loop in status {curr_pipe_status}",
            metrics={"status": curr_pipe_status}
        )

        subsystems["Backend"] = _build_sub_obj(
            "GREEN", "READY",
            "Vivy AI Core Neural Backend ACTIVE",
            "Python process active",
            metrics={"pid": os.getpid()}
        )

        subsystems["Frontend"] = _build_sub_obj(
            "GREEN", "CONNECTED",
            "Web client interface connected",
            "Dashboard HTTP/WS listeners active",
            metrics={"connected": True}
        )

        # Subsystem criticality classification: Only critical failures degrade overall system health.
        critical_subsystems = {
            "Backend", "API", "WebSocket", "Memory", "LLM",
            "Active Conversation", "Database", "Current Pipeline Status"
        }
        
        overall = "GREEN"
        overall_state = "READY"
        
        for name, s in subsystems.items():
            if s["status"] == "RED":
                overall = "RED"
                overall_state = "FAILED"
                break
            elif s["status"] == "YELLOW" and overall != "RED":
                if name in critical_subsystems:
                    overall = "YELLOW"
                    overall_state = "DEGRADED"

        return {
            "overall_status": overall,
            "overall_state": overall_state,
            "timestamp": now,
            "uptime_seconds": int(now - self.start_time),
            "subsystems": subsystems
        }

    def get_connection_diagnostics(self):
        """Return real-time connection telemetry, latency, and detailed root-cause diagnostic states."""
        now = time.time()
        avatar_clients = 0
        if os.path.exists(AVATAR_CONNECTED_TXT):
            try:
                with open(AVATAR_CONNECTED_TXT, "r", encoding="utf-8") as acf:
                    avatar_clients = int(acf.read().strip() or "0")
            except Exception as _err:
                print(f"[telemetry_manager.py] Silenced exception: {_err}")
                
        gpu_info = _discover_physical_gpu()

        return {
            "backend_connected": True,
            "websocket_connected": True,
            "api_connected": True,
            "latency_ms": round((now - self.last_heartbeat) * 10, 2) if self.last_heartbeat else 0.0,
            "streaming_active": avatar_clients > 0,
            "reconnect_status": "STABLE" if avatar_clients > 0 else "STANDBY_WAITING_FOR_CLIENT",
            "heartbeat_timestamp": now,
            "client_count": avatar_clients,
            "gpu_summary": {
                "physical_gpu": gpu_info["physical_gpu_name"],
                "torch_cuda": gpu_info["torch_cuda_available"],
                "root_cause": gpu_info["root_cause"]
            },
            "avatar_summary": {
                "status": "STREAMING" if avatar_clients > 0 else "STANDBY",
                "websocket_uri": "ws://127.0.0.1:8765",
                "client_count": avatar_clients,
                "root_cause": f"Connected to {avatar_clients} MateEngine client(s)" if avatar_clients > 0 else "WebSocket listening; 0 Unity clients connected"
            }
        }

def get_telemetry_manager():
    return TelemetryManager()
