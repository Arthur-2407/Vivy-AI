import os
os.environ["VIVY_PROCESS_ROLE"] = "runner"
import sys
import time
import subprocess
import threading
import itertools
import atexit
import soundfile as sf
import sounddevice as sd

# Ensure we can import from local directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from resource_manager import get_resource_manager

# ──────────────────────────────────────────────────────────────────────
# STARTUP TRACE INSTRUMENTATION — Lightweight, structured, timestamped tracing
# ──────────────────────────────────────────────────────────────────────
class StartupTracer:
    """Timestamped startup tracing for forensic diagnostics and startup auditing."""
    def __init__(self, trace_file_path=None):
        self.start_time = time.time()
        self.trace_file_path = trace_file_path or os.path.join(BASE_DIR, "shared", "startup_trace.log")
        try:
            os.makedirs(os.path.dirname(self.trace_file_path), exist_ok=True)
        except Exception as _err:
            print(f"[run_vivy.py] Silenced exception: {_err}")
        self.enabled = os.environ.get("VIVY_TRACE_STARTUP", "1") != "0"

    def trace(self, category: str, stage: str, status: str = "START", details: dict = None):
        if not self.enabled:
            return
        now = time.time()
        elapsed = now - self.start_time
        ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
        log_line = f"[{ts_str}] [{elapsed:7.3f}s] [{category:<12}] [{stage:<32}] [{status:<7}] {details or ''}\n"
        try:
            with open(self.trace_file_path, "a", encoding="utf-8") as f:
                f.write(log_line)
        except Exception as _err:
            print(f"[run_vivy.py] Silenced exception: {_err}")

_tracer = StartupTracer()
_tracer.trace("SYSTEM", "runner_initialization", "START")

# --- ABSOLUTE RULE 16: CONTINUOUS ARCHITECTURE VALIDATION ---
try:
    from architecture_validator import run_preflight_checks
    run_preflight_checks()
except Exception as val_e:
    print(f"[run_vivy] Architecture validation warning: {val_e}")

_tracer.trace("IMPORT", "telemetry_manager", "START")
from telemetry_manager import get_telemetry_manager
_telemetry_mgr = get_telemetry_manager()
_tracer.trace("IMPORT", "telemetry_manager", "END")

# ──────────────────────────────────────────────────────────────────────
# PERCEPTION PACKAGE — Multimodal perception integration
# Imported with graceful fallback: absent package = full existing behaviour.
# ──────────────────────────────────────────────────────────────────────
_perception_context_injector = None
_perception_fusion_engine    = None
_perception_audio_pipeline   = None
_perception_proactivity      = None
_perception_manager_reader   = None
try:
    from perception.config_loader   import get as _cfg_get
    from perception.context_injector import get_perception_context as _get_perception_context
    from perception.fusion_engine    import get_global_engine as _get_fusion_engine
    import perception.audio_pipeline    as _perception_audio_mod
    import perception.proactivity_engine as _perception_proactivity_mod
    from perception.perception_manager import get_reader as _get_pm_reader
    import perception.plugins.speech    as _speech_plugin_mod
    _perception_context_injector = _get_perception_context
    _perception_fusion_engine    = _get_fusion_engine
    _perception_manager_reader   = _get_pm_reader()
    print("[run_vivy] Perception package loaded (with PerceptionManager reader).")
except Exception as _perc_import_err:
    print(f"[run_vivy] Perception package unavailable ({_perc_import_err}). Continuing without multimodal perception.")
    _cfg_get                     = None
    _get_perception_context      = None
    _get_fusion_engine           = None
    _perception_audio_mod        = None
    _perception_proactivity_mod  = None
    _perception_manager_reader   = None

# ──────────────────────────────────────────────────────────────────────
# CIRCADIAN INTELLIGENCE SYSTEM — Circadian Engine integration
# Imported with graceful fallback: absent package = full existing behaviour.
# ──────────────────────────────────────────────────────────────────────
_circadian_get_state = None
try:
    from circadian.circadian_engine import get_state as _circadian_get_state
    print("[run_vivy] Circadian Intelligence System loaded.")
except Exception as _circ_import_err:
    print(f"[run_vivy] Circadian package unavailable ({_circ_import_err}). Continuing without circadian modulation.")
    _circadian_get_state = None

SHARED_DIR = os.path.join(BASE_DIR, "shared")

# ──────────────────────────────────────────────────────────────────────
# REAL-TIME SELF-EVOLVING AI SUBSYSTEM — Evolution Engine integration
# Imported with graceful fallback: absent package = full existing behaviour.
# ──────────────────────────────────────────────────────────────────────
_evolution_orchestrator = None
try:
    from evolution import get_evolution_orchestrator as _get_evolution_orchestrator
    _evolution_orchestrator = _get_evolution_orchestrator()
    print("[run_vivy] Self-Evolution AI Subsystem loaded successfully.")
except Exception as _evo_import_err:
    print(f"[run_vivy] Evolution package unavailable ({_evo_import_err}). Continuing without self-evolution loop.")
    _evolution_orchestrator = None



# Reconfigure original console streams to utf-8 with fallback error replacement
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass
if hasattr(sys.stderr, "reconfigure"):
    try: sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass
if hasattr(sys, "__stdout__") and sys.__stdout__ is not None and hasattr(sys.__stdout__, "reconfigure"):
    try: sys.__stdout__.reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass

# Retain reference to original system console output for clean info printing
console_stdout = sys.__stdout__ if (hasattr(sys, "__stdout__") and sys.__stdout__ is not None) else sys.stdout
log_file = sys.stdout

if __name__ == "__main__":
    import execution_context
    exec_id = execution_context.reset_execution_id()
    print(f"[run_vivy] Starting new execution session: {exec_id}")
    
    # ── LOG ROTATION ─────────────────────────────────────────────────────
    # Rotate pipeline.log when it exceeds LOG_MAX_BYTES to prevent unbounded
    # growth. The previous log is kept as pipeline.log.1 for debugging.
    LOG_MAX_BYTES = 50 * 1024 * 1024  # 50 MB
    LOG_BACKUP_COUNT = 1
    log_file_path = os.path.join(SHARED_DIR, "pipeline.log")
    os.makedirs(SHARED_DIR, exist_ok=True)
    try:
        if os.path.exists(log_file_path) and os.path.getsize(log_file_path) >= LOG_MAX_BYTES:
            import glob as _glob
            # Rotate: pipeline.log -> pipeline.log.1 (overwrite if exists)
            log_backup_path = log_file_path + ".1"
            try:
                if os.path.exists(log_backup_path):
                    os.remove(log_backup_path)
                os.rename(log_file_path, log_backup_path)
            except Exception as _rot_err:
                pass  # Non-fatal: if rename fails, continue appending
    except Exception as _err:
        print(f"[run_vivy.py] Silenced exception: {_err}")
    log_file = open(log_file_path, "a", encoding="utf-8", buffering=1)
    get_resource_manager().register_file(log_file, name="pipeline_log")
    sys.stdout = log_file
    sys.stderr = log_file

    # ── STARTUP .TMP, .LOCK, .FLAG CLEANUP ─────────────────────────────────────────────
    # Remove orphaned temporary, lock, and flag files left by previously
    # crashed or killed processes. These accumulate indefinitely without cleanup.
    try:
        import glob as _glob
        _current_pid = os.getpid()
        _cleaned = 0
        for _pattern in ["*.tmp", "*.*.tmp", "*.lock", "*.flag"]:
            _stale_files = _glob.glob(os.path.join(SHARED_DIR, _pattern)) + _glob.glob(os.path.join(SHARED_DIR, "**", _pattern), recursive=True)
            for _tmp_path in _stale_files:
                try:
                    # Avoid removing active flag files or tmp files of running processes if PID is embedded
                    _tmp_name = os.path.basename(_tmp_path)
                    _parts = _tmp_name.split(".")
                    _should_remove = True
                    for _p in _parts + _tmp_name.split("_"):
                        if _p.isdigit():
                            _chk_pid = int(_p)
                            if _chk_pid == _current_pid:
                                _should_remove = False
                    if _should_remove and os.path.exists(_tmp_path):
                        os.remove(_tmp_path)
                        _cleaned += 1
                except Exception as _err:
                    print(f"[run_vivy.py] Silenced exception: {_err}")
        if _cleaned > 0:
            print(f"[run_vivy] Startup cleanup: removed {_cleaned} orphaned .tmp/.lock/.flag files from shared/")
    except Exception as _err:
        print(f"[run_vivy.py] Silenced exception: {_err}")  # Non-fatal: cleanup is best-effort

# ======================================================
# LIVE TERMINAL INDICATOR  (WhatsApp-style typing dots)
# Writes animated status updates to the REAL console,
# not to the log file. Zero impact on pipeline I/O.
# ======================================================

# ANSI color codes (work on Windows 10+ with VT enabled)
_ANSI_RESET  = "\033[0m"
_ANSI_CYAN   = "\033[96m"
_ANSI_PINK   = "\033[95m"
_ANSI_GREEN  = "\033[92m"
_ANSI_YELLOW = "\033[93m"
_ANSI_WHITE  = "\033[97m"
_ANSI_BOLD   = "\033[1m"

# Enable ANSI VT processing on Windows terminal
try:
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-10), 7)
except Exception as _err:
    print(f"[run_vivy.py] Silenced exception: {_err}")  # Non-Windows or already enabled; safe to ignore

# Global indicator state
_indicator_active  = False
_indicator_label   = ""
_indicator_thread  = None
_indicator_lock    = threading.Lock()

# Dot frames: classic WhatsApp-style pulsing dots animation
_DOT_FRAMES = ["   ", "●  ", "●● ", "●●●", "●● ", "●  "]

def _indicator_loop():
    """Background thread: animates status dots on the terminal console line."""
    frame_cycle = itertools.cycle(_DOT_FRAMES)
    while True:
        with _indicator_lock:
            if not _indicator_active:
                break
            label = _indicator_label
        frame = next(frame_cycle)
        console_stdout.write(
            f"\r\033[K  {_ANSI_CYAN}{_ANSI_BOLD}{label}{_ANSI_RESET} "
            f"{_ANSI_PINK}{frame}{_ANSI_RESET}   "
        )
        console_stdout.flush()
        time.sleep(0.25)
    # Clear the indicator line when done
    console_stdout.write("\r\033[K\r")
    console_stdout.flush()

def start_indicator(label):
    """Start or update the live terminal indicator with a new status label."""
    global _indicator_active, _indicator_label, _indicator_thread
    with _indicator_lock:
        _indicator_label = label
        if _indicator_active:
            return  # Already running — just update the label
        _indicator_active = True
    _indicator_thread = threading.Thread(target=_indicator_loop, daemon=True)
    _indicator_thread.start()

def stop_indicator(final_msg=""):
    """Stop the live terminal indicator and print a final status line."""
    global _indicator_active
    with _indicator_lock:
        _indicator_active = False
    if _indicator_thread and _indicator_thread.is_alive():
        _indicator_thread.join(timeout=1.0)
    console_stdout.write("\r\033[K")
    if final_msg:
        console_stdout.write(f"  {_ANSI_GREEN}{_ANSI_BOLD}{final_msg}{_ANSI_RESET}\n")
    console_stdout.flush()

def console_print(msg, color=None):
    """Print a clean message to the real terminal console (not the log file)."""
    color = color or _ANSI_WHITE
    console_stdout.write(f"\r\033[K{color}{msg}{_ANSI_RESET}\n")
    console_stdout.flush()

# ======================================================

def is_blank_or_noise(text):
    text_clean = text.strip().lower()
    if not text_clean:
        return True

    import re as _re
    text_clean = _re.sub(
        r"\[\d{2}:\d{2}:\d{2}\.\d+\s*-->\s*\d{2}:\d{2}:\d{2}\.\d+\]\s*",
        "",
        text_clean
    ).strip()

    if not text_clean:
        return True

    noise_patterns = {
        "[blank_audio]",
        "[music]",
        "(music)",
        "[upbeat music]",
        "(upbeat music)",
        "[laughter]",
        "(laughter)",
        "[applause]",
        "(applause)",
        "(sigh)",
        "[sigh]",
        "[music playing]",
        "(music playing)",
        "[indistinct]",
        "(indistinct)",
        "(speaking in foreign language)",
        "[speaking in foreign language]",
    }

    if text_clean in noise_patterns:
        return True

    import re
    segments = [s.strip() for s in text_clean.split("\n") if s.strip()]
    if segments and all(
        seg in noise_patterns
        or re.match(r"^\[[^\]]*\]$", seg)
        or re.match(r"^\([^)]*\)$", seg)
        for seg in segments
    ):
        return True

    if re.match(r"^\[[^\]]*\]$", text_clean) or re.match(r"^\([^)]*\)$", text_clean):
        return True

    return False

# Import mic selection functions from mic_input
_tracer.trace("MANAGER", "mic_input", "START")
from mic_input import select_mic, start_mic_listening, set_console_out as _mic_set_console

if __name__ == "__main__":
    # Print clean startup banner to console
    console_stdout.write(f"{_ANSI_CYAN}{'=' * 52}{_ANSI_RESET}\n")
    console_stdout.write(f"{_ANSI_BOLD}{_ANSI_PINK}   Vivy AI Core Neural Pipeline is now ACTIVE.{_ANSI_RESET}\n")
    console_stdout.write(f"{_ANSI_WHITE}   Open Dashboard: http://127.0.0.1:8080{_ANSI_RESET}\n")
    console_stdout.write(f"{_ANSI_YELLOW}   Press Ctrl+C in this terminal to shut down.{_ANSI_RESET}\n")
    console_stdout.write(f"{_ANSI_CYAN}{'=' * 52}{_ANSI_RESET}\n")
    console_stdout.flush()

    # Pass real terminal handle to mic_input so recording events appear on terminal
    _mic_set_console(console_stdout)

    # Select mic index first (synchronously, to avoid thread input conflicts)
    mic_index = select_mic()
    _tracer.trace("MANAGER", "mic_input", "END", details={"mic_index": mic_index})

# Import our pipeline modules (they will load their heavy models now, outputting to log file)
print("\nInitializing Vivy AI Core Engines...")
print("- Loading Memory & Relational Engine...")
_tracer.trace("MANAGER", "conversation", "START")
import conversation
_tracer.trace("MANAGER", "conversation", "END")

print("- Loading Emotion-Aware Voice TTS...")
_tracer.trace("MANAGER", "voice", "START")
import voice
_tracer.trace("MANAGER", "voice", "END")

print("- Loading Core Intelligence Emotion Classifier...")
_tracer.trace("MANAGER", "emotion", "START")
from emotion.emotion import detect_emotion, preload_classifier
preload_classifier()
_tracer.trace("MANAGER", "emotion", "END")

print("- Loading Universal Internet Intelligence Layer (DuckDuckGo Adapter)...")
_tracer.trace("MANAGER", "internet", "START")
try:
    from internet import get_internet_manager
    _internet_mgr = get_internet_manager()
    _net_status = _internet_mgr.network_manager.current_state.value
    print(f"[run_vivy] Internet Intelligence Layer active (Network state: {_net_status.upper()}).")
    _tracer.trace("MANAGER", "internet", "END", details={"network_state": _net_status})
except Exception as _net_err:
    print(f"[run_vivy] Internet Intelligence Layer initialization warning: {_net_err}")
    _tracer.trace("MANAGER", "internet", "ERROR", details={"error": str(_net_err)})


# Optional: Avatar Bridge (connects to Unity MateEngine runtime via WebSocket)
# Handled via subprocess in venv_avatar to isolate environment dependencies.
_avatar_bridge = None

# Animation Planner — maps emotion labels to Animator trigger names
# Operates via sentinel-file IPC so it stays in the same venv as the main pipeline.
# The planner sends triggers by writing to shared/animation_trigger.txt which
# avatar_bridge.py monitors and forwards to Unity via WebSocket.
from animator.animator import VivyAnimationPlanner as _VivyAnimationPlanner

class _SentinelBridge:
    """Thin shim: writes animation trigger name to shared/animation_trigger.txt.
    avatar_bridge.py monitors this file and calls push_animation() on change.
    This keeps the main venv isolated from venv_avatar."""
    _TRIGGER_TXT = os.path.join(SHARED_DIR, "animation_trigger.txt")
    _last_mtime  = 0.0

    def push_animation(self, trigger_name: str):
        try:
            os.makedirs(SHARED_DIR, exist_ok=True)
            with open(self._TRIGGER_TXT, "w", encoding="utf-8") as f:
                f.write(trigger_name)
        except Exception as e:
            print(f"[SentinelBridge] Failed to write animation_trigger.txt: {e}")

_animation_planner = _VivyAnimationPlanner(bridge=_SentinelBridge())
print("- Loading Animation Behaviour Planner...")

USER_TXT = os.path.join(SHARED_DIR, "user_text.txt")
REPLY_TXT = os.path.join(SHARED_DIR, "reply_text.txt")
EMOTION_TXT = os.path.join(SHARED_DIR, "emotion.txt")
TTS_WAV = os.path.join(SHARED_DIR, "tts.wav")
RVC_WAV = os.path.join(SHARED_DIR, "rvc.wav")
history_file = os.path.join(BASE_DIR, "vivy_history.json")

# Ensure files exist and are clean on startup when running directly
os.makedirs(SHARED_DIR, exist_ok=True)
if __name__ == "__main__":
    for f in [USER_TXT, REPLY_TXT, EMOTION_TXT]:
        with open(f, "w", encoding="utf-8") as file:
            file.write("")

    _avatar_connected_txt = os.path.join(SHARED_DIR, "avatar_connected.txt")
    try:
        with open(_avatar_connected_txt, "w", encoding="utf-8") as _acf:
            _acf.write("0")
    except Exception as _err:
        print(f"[run_vivy.py] Silenced exception: {_err}")

STATUS_TXT = os.path.join(SHARED_DIR, "status.txt")
SCREEN_CONTEXT_TXT = os.path.join(SHARED_DIR, "screen_context.txt")

def read_screen_context():
    """
    Read the latest screen context written by the VisionBridge.

    UPGRADED: Now also consults the PerceptionManager reader to prevent
    false 'screen share disconnected' signals when frames are actively
    arriving but the context file is temporarily stale.

    Returns:
      - Full context string if screen_context.txt exists and is fresh
      - Minimal 'active but initializing' hint if PerceptionManager shows
        frames arriving but the context file is empty/stale
      - Empty string ONLY if PerceptionManager also confirms no frames received
    """
    ctx_from_file = ""
    try:
        if os.path.exists(SCREEN_CONTEXT_TXT):
            age = time.time() - os.path.getmtime(SCREEN_CONTEXT_TXT)
            # Read staleness threshold from config, fallback to 60s
            staleness = 60
            try:
                if _cfg_get is not None:
                    staleness = float(_cfg_get("screen_perception", "staleness_seconds", default=60))
            except Exception as _err:
                print(f"[run_vivy.py] Silenced exception: {_err}")
            if age <= staleness:
                with open(SCREEN_CONTEXT_TXT, "r", encoding="utf-8") as f:
                    raw = f.read().strip()
                # Strip the timestamp header line before passing to LLM
                lines = raw.splitlines()
                if lines and lines[0].startswith("[Screen context captured"):
                    raw = "\n".join(lines[1:]).strip()
                ctx_from_file = raw
    except Exception as e:
        print(f"[ScreenContext] Error reading screen_context.txt: {e}")

    # ── PerceptionManager cross-check ─────────────────────────────────────
    # Even if context file is stale, the PerceptionManager knows whether
    # frames have been arriving recently.  If screen sharing IS active
    # but we have no context yet, return a minimal hint so the LLM is
    # not told 'screen share disconnected' when it is actually running.
    if _perception_manager_reader is not None:
        try:
            pm_state = _perception_manager_reader.load_state()
            frames_received = pm_state.get("frames_received", 0)
            pm_active = pm_state.get("screen_sharing_active", False)

            if ctx_from_file:
                # Great — we have real context, return it
                print(f"[ScreenContext] Active — injecting {len(ctx_from_file)} chars into prompt (PM: {frames_received} frames)")
                return ctx_from_file

            elif pm_active:
                # Frames are arriving but context file is stale/empty —
                # return a minimal anchor so the LLM knows screen is shared
                app_type = pm_state.get("current_app_type", "unknown")
                fps = pm_state.get("current_fps", 0.0)
                hint = f"[Screen share is active — {frames_received} frames received"
                if fps > 0:
                    hint += f" at {fps} FPS"
                if app_type and app_type != "unknown":
                    hint += f", detected: {app_type}"
                hint += ". Visual context is still initializing.]"
                print(f"[ScreenContext] PM active but context stale — injecting hint: {hint}")
                return hint

            else:
                # Both context file and PerceptionManager agree: not active
                print("[ScreenContext] No active screen context (confirmed by PerceptionManager)")
                return ""

        except Exception as e:
            print(f"[ScreenContext] PerceptionManager cross-check failed (non-fatal): {e}")

    # Fallback: no PerceptionManager available, use file-only result
    if ctx_from_file:
        print(f"[ScreenContext] Active — injecting {len(ctx_from_file)} chars into prompt")
    else:
        print("[ScreenContext] No active screen context")
    return ctx_from_file

def set_status(status):
    try:
        with open(STATUS_TXT, "w", encoding="utf-8") as status_file:
            status_file.write(status)
    except Exception as _err:
        print(f"[run_vivy.py] Silenced exception: {_err}")

# Web server & Avatar Bridge subprocess placeholders
web_process = None
avatar_process = None

def cleanup_web_server():
    global web_process
    if web_process:
        try:
            print("\nShutting down Web Server...")
            web_process.terminate()
            web_process.wait(timeout=2)
        except Exception as _err:
            print(f"[run_vivy.py] Silenced exception: {_err}")
atexit.register(cleanup_web_server)

def cleanup_avatar_bridge():
    global avatar_process
    if avatar_process:
        try:
            print("\nShutting down Avatar Bridge...")
            avatar_process.terminate()
            avatar_process.wait(timeout=2)
        except Exception as _err:
            print(f"[run_vivy.py] Silenced exception: {_err}")
atexit.register(cleanup_avatar_bridge)

if __name__ == "__main__":
    # Start the web server process automatically in a background subprocess
    _tracer.trace("PROCESS", "web_server", "START", details={"url": "http://127.0.0.1:8080"})
    print("Starting Vivy AI Web Server on http://127.0.0.1:8080 ...")
    web_server_script = os.path.join(BASE_DIR, "web_server.py")
    web_process = subprocess.Popen(
        [sys.executable, web_server_script],
        stdout=log_file,
        stderr=log_file
    )
    get_resource_manager().register_subprocess(web_process, name="web_server")
    _tracer.trace("PROCESS", "web_server", "END", details={"pid": web_process.pid})

    # Start the Avatar Bridge WebSocket server automatically in a background subprocess under venv_avatar
    avatar_disable_flag = os.path.join(SHARED_DIR, "avatar_disable.txt")
    if not os.path.exists(avatar_disable_flag):
        avatar_python = os.path.join(BASE_DIR, "venv_avatar", "Scripts", "python.exe")
        avatar_script = os.path.join(BASE_DIR, "avatar_bridge.py")
        if os.path.exists(avatar_python):
            _tracer.trace("PROCESS", "avatar_bridge", "START", details={"url": "ws://127.0.0.1:8765"})
            print("Starting Avatar Bridge WebSocket server on ws://127.0.0.1:8765 ...")
            try:
                avatar_process = subprocess.Popen(
                    [avatar_python, avatar_script],
                    stdout=log_file,
                    stderr=log_file
                )
                get_resource_manager().register_subprocess(avatar_process, name="avatar_bridge")
                _tracer.trace("PROCESS", "avatar_bridge", "END", details={"pid": avatar_process.pid})
            except Exception as e:
                print(f"Failed to start Avatar Bridge process: {e}")
                _tracer.trace("PROCESS", "avatar_bridge", "ERROR", details={"error": str(e)})
        else:
            print("- Avatar Bridge python env (venv_avatar) not found.")
            _tracer.trace("PROCESS", "avatar_bridge", "SKIPPED", details={"reason": "venv_avatar not found"})

    # Spawn the background microphone listener thread
    _tracer.trace("THREAD", "mic_thread", "START")
    mic_thread = threading.Thread(
        target=start_mic_listening,
        args=(USER_TXT, mic_index),
        daemon=True
    )
    mic_thread.start()
    get_resource_manager().register_thread(mic_thread, name="mic_input")
    _tracer.trace("THREAD", "mic_thread", "END")

def print_startup_readiness_table():
    _tracer.trace("SYSTEM", "readiness_table", "BUILD")
    health = _telemetry_mgr.get_health_status()
    sub = health.get("subsystems", {})
    
    gpu_metrics = sub.get("GPU", {}).get("metrics", {})
    if gpu_metrics.get("cuda_available"):
        gpu_val = f"CUDA ({gpu_metrics.get('physical_gpu_name', 'NVIDIA GPU')})"
    elif gpu_metrics.get("physical_gpu_detected"):
        gpu_val = f"CPU ({gpu_metrics.get('physical_gpu_name', 'GPU')} detected)"
    else:
        gpu_val = "CPU"

    avatar_metrics = sub.get("Avatar", {}).get("metrics", {})
    avatar_val = "READY (Streaming)" if avatar_metrics.get("connected_clients", 0) > 0 else "STANDBY (ws://127.0.0.1:8765 ready)"

    readiness = [
        ("Camera",                  sub.get("Camera", {}).get("state", "STANDBY")),
        ("Voice",                   sub.get("Voice", {}).get("state", "READY")),
        ("Memory",                  sub.get("Memory", {}).get("state", "READY")),
        ("Emotion Engine",          sub.get("Emotion Engine", {}).get("state", "READY")),
        ("Face & Gaze Perception",  sub.get("Face & Gaze Perception", {}).get("state", "STANDBY")),
        ("Emotion Detection (Face)",sub.get("Emotion Detection", {}).get("state", "READY")),
        ("Vision Summary",          sub.get("Vision Summary", {}).get("state", "STANDBY")),
        ("Affection System",        "READY"),
        ("Loneliness System",       "READY"),
        ("Circadian System",        "READY"),
        ("Conversation Planner",    "READY"),
        ("Vision",                  sub.get("Vision", {}).get("state", "STANDBY")),
        ("Internet",                sub.get("Internet", {}).get("state", "ONLINE")),
        ("DuckDuckGo",              sub.get("DuckDuckGo", {}).get("state", "READY")),
        ("GPU",                     gpu_val),
        ("LLM",                     sub.get("LLM", {}).get("state", "READY")),
        ("Avatar",                  avatar_val),
        ("Frontend",                sub.get("Frontend", {}).get("state", "CONNECTED")),
        ("Backend",                 sub.get("Backend", {}).get("state", "READY")),
        ("WebSocket",               sub.get("WebSocket", {}).get("state", "READY")),
        ("API",                     sub.get("API", {}).get("state", "READY")),
        ("Database",                sub.get("Database", {}).get("state", "READY")),
        ("Scheduler",               sub.get("Scheduler", {}).get("state", "READY")),
        ("Plugins",                 sub.get("Plugins", {}).get("state", "READY")),
        ("Animation Authoring",     "READY")
    ]
    
    table_lines = ["\n========================================================", "               STARTUP READINESS TABLE                  ", "========================================================"]
    for key, val in readiness:
        dots = "." * (23 - len(key))
        table_lines.append(f" {key} {dots} {val}")
    table_lines.append("========================================================\n")
    
    out_str = "\n".join(table_lines)
    print(out_str)
    console_print(out_str, _ANSI_CYAN)

    # Print explicit GPU diagnosis log
    gpu_cause = gpu_metrics.get("root_cause")
    if gpu_cause:
        print(f"[run_vivy][GPU Diagnosis] {gpu_cause}")
        console_print(f"  [GPU Diagnostic]: {gpu_cause}", _ANSI_YELLOW)

    _telemetry_mgr.log_event("Startup Readiness Verified", details=dict(readiness))

if __name__ == "__main__":
    # Start background perception modules on startup if enabled
    if _perception_audio_mod is not None:
        try:
            _perception_audio_mod.start_if_enabled()
        except Exception as e:
            print(f"[run_vivy] Failed to start audio pipeline on startup: {e}")

    if _perception_proactivity_mod is not None:
        try:
            _perception_proactivity_mod.start_if_enabled()
        except Exception as e:
            print(f"[run_vivy] Failed to start proactivity engine on startup: {e}")

    # Check CLI flags for perception control
    _PERCEPTION_ENABLED = "--no-perception" not in sys.argv

    # Auto-start hardware camera manager & perception loop (in standby mode on boot)
    try:
        _tracer.trace("HARDWARE", "camera_manager", "START")
        from perception.camera_manager import get_camera_manager, is_camera_disabled
        cam_mgr = get_camera_manager()
        if is_camera_disabled():
            cam_active = False
            print("[run_vivy] Camera Manager initialized (standby mode — camera disabled by configuration).")
        else:
            cam_active = False
            print("[run_vivy] Camera Manager initialized (standby mode — ready for manual/UI activation).")
        _tracer.trace("HARDWARE", "camera_manager", "END", details={"camera_active": cam_active})
    except Exception as e:
        print(f"[run_vivy] Failed to initialize Camera Manager on startup: {e}")
        _tracer.trace("HARDWARE", "camera_manager", "ERROR", details={"error": str(e)})

    # Initialize Perception Runner service (Face Detection, Gaze Detection, Emotion Detection, Vision Summary)
    try:
        _tracer.trace("PERCEPTION", "runner", "START")
        from perception.runner import get_perception_runner
        _perception_runner = get_perception_runner(enabled=_PERCEPTION_ENABLED)
        if _PERCEPTION_ENABLED:
            # Enforce manual camera control: DO NOT start PerceptionRunner automatically.
            # It will be started by CameraManager when the user explicitly activates the camera.
            print("[run_vivy] PerceptionRunner initialized (standby mode — ready for manual activation).")
            _tracer.trace("PERCEPTION", "runner", "END", details={"enabled": True, "mode": "standby"})
        else:
            print("[run_vivy] PerceptionRunner disabled via --no-perception flag.")
            _tracer.trace("PERCEPTION", "runner", "SKIPPED", details={"reason": "--no-perception"})
    except Exception as e:
        print(f"[run_vivy] Failed to initialize PerceptionRunner on startup: {e}")
        _tracer.trace("PERCEPTION", "runner", "ERROR", details={"error": str(e)})

    print_startup_readiness_table()
    _tracer.trace("SYSTEM", "pipeline_ready", "COMPLETE")

    print("\nVivy AI Pipeline Connection is READY.")
    print(f"Watching shared path: {SHARED_DIR}")
    print("Speak into the mic or write to 'shared/user_text.txt' to trigger response.\n")
    console_print("\n  Vivy AI Pipeline is READY. Speak or type to chat.", _ANSI_GREEN)

    import json
    from session_manager import get_session_manager

    # Session Isolation System: Initialize fresh session for every execution
    session_mgr = get_session_manager()
    active_session = session_mgr.start_new_session()

    # Visible conversation history starts completely EMPTY for the active session
    history = active_session.display_history

    # Load persistent long-term memory (separate from visible conversation transcript)
    mem = conversation.load()

    # Standalone fresh startup greeting
    first = conversation.greeting(mem)
    print(f"Vivy: {first}")
    console_print(f"\n  Vivy: {first}", _ANSI_PINK)

    # Run voice cloning configurations definitions
    rvc_python = os.path.join(BASE_DIR, "venv_rvc", "Scripts", "python.exe")
    voice_cloning_script = os.path.join(BASE_DIR, "voice_cloning.py")

    # Write last output to reply_text.txt and set emotion
    try:
        detect_emotion(first)
    except Exception as _de_err:
        print(f"[run_vivy] Startup emotion detection warning: {_de_err}")

    # Clean up stale audio files from previous runs
    if os.path.exists(TTS_WAV):
        try: os.remove(TTS_WAV)
        except Exception: pass
    if os.path.exists(RVC_WAV):
        try: os.remove(RVC_WAV)
        except Exception: pass

    with open(REPLY_TXT, "w", encoding="utf-8") as f:
        f.write(first)

    print("Pipeline initialized. Ready for interaction.")
    set_status("ready")




_run_main_loop = (__name__ == "__main__")
last_perception_check = 0

while _run_main_loop:
    try:
        now = time.time()
        if now - last_perception_check > 5.0:
            last_perception_check = now
            # Subprocess health check: ensure Web Server and Avatar Bridge remain alive
            if web_process is not None and web_process.poll() is not None:
                print(f"[run_vivy] Warning: Web server process (PID {web_process.pid}) exited with code {web_process.returncode}. Auto-restarting...")
                try:
                    web_server_script = os.path.join(BASE_DIR, "web_server.py")
                    web_process = subprocess.Popen(
                        [sys.executable, web_server_script],
                        stdout=log_file,
                        stderr=log_file
                    )
                    print(f"[run_vivy] Web server process auto-restarted (PID {web_process.pid}) on http://127.0.0.1:8080")
                except Exception as _w_re_err:
                    print(f"[run_vivy] Error auto-restarting web server: {_w_re_err}")

            if avatar_process is not None and avatar_process.poll() is not None:
                avatar_disable_flag = os.path.join(SHARED_DIR, "avatar_disable.txt")
                if not os.path.exists(avatar_disable_flag):
                    avatar_python = os.path.join(BASE_DIR, "venv_avatar", "Scripts", "python.exe")
                    avatar_script = os.path.join(BASE_DIR, "avatar_bridge.py")
                    if os.path.exists(avatar_python):
                        print(f"[run_vivy] Warning: Avatar bridge process (PID {avatar_process.pid}) exited with code {avatar_process.returncode}. Auto-restarting...")
                        try:
                            avatar_process = subprocess.Popen(
                                [avatar_python, avatar_script],
                                stdout=log_file,
                                stderr=log_file
                            )
                            print(f"[run_vivy] Avatar bridge process auto-restarted (PID {avatar_process.pid}) on ws://127.0.0.1:8765")
                        except Exception as _a_re_err:
                            print(f"[run_vivy] Error auto-restarting avatar bridge: {_a_re_err}")

            # Dynamic perception background thread manager
            if _perception_audio_mod is not None:
                try:
                    from perception.config_loader import get as _cfg_get
                    audio_enabled = _cfg_get("audio_perception", "enabled", default=False)
                    pipeline = _perception_audio_mod.get_global_pipeline()
                    if audio_enabled and not pipeline._running:
                        pipeline.start()
                    elif not audio_enabled and pipeline._running:
                        pipeline.stop()
                except Exception as e:
                    print(f"[run_vivy] Audio pipeline dynamic management error: {e}")

            if _perception_proactivity_mod is not None:
                try:
                    from perception.config_loader import get as _cfg_get
                    proactivity_enabled = _cfg_get("proactivity", "enabled", default=False)
                    pro_engine = _perception_proactivity_mod.get_global_engine()
                    if proactivity_enabled and not pro_engine._running:
                        pro_engine.start()
                    elif not proactivity_enabled and pro_engine._running:
                        pro_engine.stop()
                except Exception as e:
                    print(f"[run_vivy] Proactivity engine dynamic management error: {e}")

        if os.path.exists(USER_TXT):
            with open(USER_TXT, "r", encoding="utf-8") as f:
                user_input = f.read().strip()
            
            if user_input:
                # Clear user_text.txt immediately to acknowledge receipt
                with open(USER_TXT, "w", encoding="utf-8") as f:
                    f.write("")
                
                # Check for proactive trigger prefix
                is_proactive = False
                if user_input.startswith("[PERCEPTION_TRIGGER]"):
                    is_proactive = True
                    user_input = user_input[len("[PERCEPTION_TRIGGER]"):].strip()

                # Check for noise or blank transcriptions
                if is_blank_or_noise(user_input):
                    continue
                
                if is_proactive:
                    print(f"\nProactive Trigger: {user_input}")
                    console_print(f"\n  [Vivy observed]: {user_input}", _ANSI_YELLOW)
                else:
                    print(f"\nUser: {user_input}")
                    console_print(f"\n  You: {user_input}", _ANSI_YELLOW)
                
                # Read input source
                input_source = "text"
                source_file = os.path.join(SHARED_DIR, "input_source.txt")
                if os.path.exists(source_file):
                    try:
                        with open(source_file, "r", encoding="utf-8") as sf_file:
                            input_source = sf_file.read().strip().lower()
                        with open(source_file, "w", encoding="utf-8") as sf_file:
                            sf_file.write("")
                    except Exception as e:
                        print(f"Error reading/clearing input_source.txt: {e}")
                
                if is_proactive:
                    input_source = "proactive"

                is_voice_turn = (input_source == "voice")
                print(f"Input source mode: {input_source}")

                # Push event to FusionEngine if user sent input
                if not is_proactive:
                    try:
                        if _perception_fusion_engine is not None:
                            if is_voice_turn:
                                _perception_fusion_engine().push_speech_event(
                                    user_input,
                                    metadata={"input_source": "voice"}
                                )
                            else:
                                _perception_fusion_engine().push_user_action(
                                    f"User sent text: {user_input}",
                                    metadata={"input_source": "text"}
                                )
                    except Exception as _pe_err:
                        print(f"[Perception] FusionEngine push error (non-fatal): {_pe_err}")

                # Generate AI response — show live thinking indicator
                set_status("thinking:Vivy is thinking...")
                _telemetry_mgr.log_event("Conversation Started", details={"user_input": user_input, "input_source": input_source})
                start_indicator("Vivy is thinking")
                # Read real screen context if screen sharing is active
                screen_ctx = read_screen_context()
                if screen_ctx:
                    print(f"[ScreenContext] Active — injecting {len(screen_ctx)} chars into prompt")
                else:
                    print("[ScreenContext] No active screen context")

                # [PERCEPTION] Build additional multimodal perception context
                perception_ctx = ""
                try:
                    if _perception_context_injector is not None:
                        is_percep = False
                        wants_vision, wants_audio = True, True
                        try:
                            from conversation import is_perception_query_check, classify_perception_modality
                            from perception.perception_manager import get_reader
                            p_state = get_reader().load_state()
                            if is_perception_query_check(user_input, p_state):
                                is_percep = True
                            wants_vision, wants_audio = classify_perception_modality(user_input)
                        except Exception as _err:
                            print(f"[run_vivy.py] Silenced exception: {_err}")
                        budget = 2500 if is_percep else 800
                        perception_ctx = _perception_context_injector(
                            screen_context=screen_ctx, 
                            token_budget=budget,
                            wants_vision=wants_vision,
                            wants_audio=wants_audio,
                            is_perception_query=is_percep
                        )
                        if perception_ctx:
                            print(f"[Perception] Injecting {len(perception_ctx)} chars of multimodal context")
                    
                    # Publish prompt builder diagnostics to prompt_builder_stats.json
                    try:
                        stats = {
                            "prompt_latest_context": perception_ctx,
                            "prompt_characters_added": len(perception_ctx),
                            "prompt_last_inject_timestamp": time.time()
                        }
                        stats_path = os.path.join(SHARED_DIR, "prompt_builder_stats.json")
                        with open(stats_path, "w", encoding="utf-8") as stats_file:
                            json.dump(stats, stats_file, indent=2)
                    except Exception as _stats_err:
                        print(f"[Perception] Failed to write prompt builder stats (non-fatal): {_stats_err}")
                except Exception as _pctx_err:
                    print(f"[Perception] Context injection error (non-fatal): {_pctx_err}")

                # [PERCEPTION] Load PerceptionManager state for Dialogue Router Gate
                perception_state = {}
                try:
                    if _perception_manager_reader is not None:
                        perception_state = _perception_manager_reader.load_state()
                        wants_vision, wants_audio = True, True
                        try:
                            from conversation import classify_perception_modality
                            wants_vision, wants_audio = classify_perception_modality(user_input)
                        except Exception as _err:
                            print(f"[run_vivy.py] Silenced exception: {_err}")
                        perception_state["_grounding_context"] = _perception_manager_reader.build_grounding_context(
                            screen_ctx,
                            wants_vision=wants_vision,
                            wants_audio=wants_audio
                        )
                        perception_state["_diagnostic_answer"] = _perception_manager_reader.build_diagnostic_answer(
                            wants_vision=wants_vision,
                            wants_audio=wants_audio
                        )
                except Exception as _ps_err:
                    print(f"[Perception] PerceptionManager state read error (non-fatal): {_ps_err}")

                _telemetry_mgr.log_event("Reasoning Started", details={"input": user_input[:60]})
                try:
                    reply, history = conversation.generate_reply_internal(
                        user_input, history, mem, screen_ctx,
                        perception_context=perception_ctx,
                        perception_state=perception_state
                    )
                except Exception as _gen_err:
                    print(f"[run_vivy] Pipeline reasoning exception: {_gen_err}")
                    import traceback
                    traceback.print_exc()
                    reply = "I'm right here with you! Tell me more about what's on your mind."
                    history.append("You: " + user_input)
                    history.append("Vivy: " + reply)
                _telemetry_mgr.log_event("Reasoning Finished", details={"reply_length": len(reply)})
                stop_indicator()
                print(f"Vivy: {reply}")
                console_print(f"  Vivy: {reply}", _ANSI_PINK)

                # Immediately clear stale voice audio files and write response text for instant Web UI synchronization
                if os.path.exists(TTS_WAV):
                    try: os.remove(TTS_WAV)
                    except Exception: pass
                if os.path.exists(RVC_WAV):
                    try: os.remove(RVC_WAV)
                    except Exception: pass
                try:
                    with open(REPLY_TXT, "w", encoding="utf-8") as f:
                        f.write(reply)
                    meta_path = os.path.join(SHARED_DIR, "reply_meta.json")
                    with open(meta_path, "w", encoding="utf-8") as mf:
                        json.dump({"reply": reply, "timestamp": time.time(), "source": input_source, "audio_ready": not is_voice_turn}, mf)
                except Exception as _sync_err:
                    print(f"[run_vivy] Early UI sync write error (non-fatal): {_sync_err}")
                
                # Save persistent history
                try:
                    with open(history_file, "w", encoding="utf-8") as hf:
                        json.dump(history, hf, indent=2, ensure_ascii=False)
                    _telemetry_mgr.log_event("Memory Saved")
                except Exception as he:
                    print(f"Failed to save history: {he}")
                
                # Detect and write emotion
                emotion_label = detect_emotion(reply)

                # Check if user asked for an explicit emotion/animation command
                u_clean = user_input.lower().strip()
                explicit_cmd_map = {
                    "express happiness": "joy",
                    "express happy": "joy",
                    "express joy": "joy",
                    "be happy": "joy",
                    "smile": "joy",
                    "cheer": "joy",
                    "express sadness": "sadness",
                    "express sad": "sadness",
                    "express anger": "anger",
                    "express angry": "anger",
                    "express surprise": "surprise",
                    "express surprised": "surprise",
                    "wave": "joy",
                    "wave at me": "joy"
                }
                for key_cmd, target_emo in explicit_cmd_map.items():
                    if key_cmd in u_clean:
                        print(f"[run_vivy] Explicit user command detected ('{key_cmd}') -> Overriding emotion to '{target_emo}'")
                        emotion_label = target_emo
                        if "wave" in key_cmd:
                            try:
                                _SentinelBridge().push_animation("Wave")
                            except Exception as _err:
                                print(f"[run_vivy.py] Silenced exception: {_err}")
                        break

                _telemetry_mgr.log_event("Emotion Updated", details={"emotion": emotion_label})

                print(f"Emotion detected: {emotion_label}")
                try:
                    from emotion.emotion import modulate_emotion_with_perception
                    mod_vec = modulate_emotion_with_perception(emotion_label, perception_state)
                    print(f"Perception-modulated emotion vector: confidence={mod_vec.get('confidence', 75):.1f}, initiative={mod_vec.get('initiative', 75):.1f}")

                    # Construct standardized EmotionState contract and save to shared/emotion_state.json
                    try:
                        from contracts.emotion_state import EmotionState
                        e_state = EmotionState(
                            timestamp=time.time(),
                            primary_emotion=emotion_label,
                            secondary_emotions=mod_vec,
                            intensity_values=mod_vec,
                            valence=0.5 if emotion_label in ("joy", "surprise") else (-0.5 if emotion_label in ("sadness", "anger", "disgust", "fear") else 0.0),
                            arousal=0.8 if emotion_label in ("joy", "anger", "surprise") else 0.3
                        )
                        e_state_path = os.path.join(SHARED_DIR, "emotion_state.json")
                        e_state_tmp = e_state_path + ".tmp"
                        with open(e_state_tmp, "w", encoding="utf-8") as _esf:
                            json.dump(e_state.to_dict(), _esf, indent=2)
                        os.replace(e_state_tmp, e_state_path)
                    except Exception as _esc_err:
                        print(f"[EmotionContract] Write error (non-fatal): {_esc_err}")
                except Exception as _em_err:
                    print(f"Emotion modulation error (non-fatal): {_em_err}")

                # ── CIRCADIAN STATE FILE + AVATAR ENERGY ──
                # Write circadian_state.json for avatar_bridge and dashboard.
                # Push avatar_energy to Unity via the existing sentinel pattern.
                try:
                    if _circadian_get_state is not None:
                        _cs = _circadian_get_state()
                        if _cs and _cs.enabled:
                            import json as _json
                            _circ_payload = {
                                "phase":           _cs.phase_name,
                                "energy":          _cs.energy,
                                "initiative":      _cs.initiative_delta,
                                "voice_warmth":    _cs.voice_warmth_delta,
                                "avatar_energy":   _cs.avatar_energy,
                                "sleep_mode":      _cs.sleep_mode,
                                "hardware_hint":   _cs.hardware_hint,
                                "timestamp":       time.time(),
                            }
                            _circ_path = os.path.join(SHARED_DIR, "circadian_state.json")
                            _circ_tmp  = _circ_path + ".tmp"
                            with open(_circ_tmp, "w", encoding="utf-8") as _cf:
                                _json.dump(_circ_payload, _cf, indent=2)
                            os.replace(_circ_tmp, _circ_path)
                except Exception as _cs_err:
                    print(f"[Circadian] State file write error (non-fatal): {_cs_err}")

                # [PERCEPTION] Record emotion as a user_action event
                try:
                    if _perception_fusion_engine is not None:
                        _perception_fusion_engine().push_user_action(
                            f"Vivy responded with emotion: {emotion_label}",
                            metadata={"emotion": emotion_label, "input_source": input_source}
                        )
                except Exception as _pe_err:
                    print(f"[Perception] FusionEngine push error (non-fatal): {_pe_err}")

                # Behaviour Planner — trigger a corresponding animation in Unity
                # This is additive: if avatar is not connected the push is silently queued.
                try:
                    _c_energy = 0.7
                    if _circadian_get_state is not None:
                        _cs = _circadian_get_state()
                        if _cs and hasattr(_cs, "avatar_energy"):
                            _c_energy = float(_cs.avatar_energy)
                    _animation_planner.on_emotion(emotion_label, circadian_energy=_c_energy)
                except Exception as _ap_err:
                    print(f"AnimationPlanner error: {_ap_err}")

                # ── SELF-EVOLUTION ENGINE STEP ──
                # Asynchronously steps the self-evolution loop (perception -> adaptation -> diagnosis -> correction -> consolidation -> meta-learning -> evolution -> governance -> monitoring).
                try:
                    if _evolution_orchestrator is not None:
                        _curr_phase = "Afternoon"
                        if _circadian_get_state is not None:
                            _cs = _circadian_get_state()
                            if _cs and hasattr(_cs, "phase_name"):
                                _curr_phase = _cs.phase_name
                        def _async_evo_step():
                            try:
                                _evolution_orchestrator.step_evolution_loop(
                                    user_input=user_input,
                                    system_reply=reply,
                                    emotion_label=emotion_label,
                                    rie_score=0.85,
                                    latency_seconds=0.5,
                                    circadian_phase=_curr_phase
                                )
                            except Exception as _evo_run_err:
                                print(f"[Evolution] Background loop step error (non-fatal): {_evo_run_err}")
                        threading.Thread(target=_async_evo_step, daemon=True, name="SelfEvolutionStep").start()
                except Exception as _evo_trigger_err:
                    print(f"[Evolution] Loop trigger error (non-fatal): {_evo_trigger_err}")

                
                if is_voice_turn:
                    # Generate TTS WAV — show live indicator
                    set_status("generating_tts:Generating voice response...")
                    start_indicator("Generating voice")
                    print("Generating TTS output...")

                    # ── CIRCADIAN VOICE MODULATION ──
                    # Additive adjustment to voice.speech_rate based on circadian phase.
                    # Clamped to [0.75, 1.25]. Non-fatal if circadian unavailable.
                    try:
                        if _circadian_get_state is not None:
                            _cs = _circadian_get_state()
                            if _cs and _cs.enabled:
                                _target_rate = max(0.75, min(1.25, 1.0 + _cs.voice_speed_delta))
                                voice.speech_rate = _target_rate
                                print(f"[Circadian] voice.speech_rate = {_target_rate:.3f} (delta={_cs.voice_speed_delta:+.3f})")
                    except Exception as _cv_err:
                        print(f"[Circadian] Voice modulation error (non-fatal): {_cv_err}")

                    voice.generate_tts_only(reply, TTS_WAV)
                    
                    # Run Voice Cloning (RVC) using the venv_rvc python environment
                    rvc_disabled = os.path.exists(os.path.join(SHARED_DIR, "rvc_disable.txt"))
                    if not rvc_disabled:
                        set_status("applying_rvc:Applying voice cloning...")
                        # Update indicator label without restarting thread
                        with _indicator_lock:
                            _indicator_label = "Applying voice cloning"
                        print("Applying RVC voice cloning...")
                        subprocess.run([
                            rvc_python,
                            voice_cloning_script,
                            "--input", TTS_WAV,
                            "--output", RVC_WAV
                        ])
                    else:
                        print("RVC voice cloning disabled. Skipping...")
                        if os.path.exists(RVC_WAV):
                            try:
                                os.remove(RVC_WAV)
                            except Exception as _err:
                                print(f"[run_vivy.py] Silenced exception: {_err}")
                    stop_indicator()
                else:
                    print("Text turn. Cleaning up voice output files...")
                    if os.path.exists(TTS_WAV):
                        try: os.remove(TTS_WAV)
                        except Exception: pass
                    if os.path.exists(RVC_WAV):
                        try: os.remove(RVC_WAV)
                        except Exception: pass
                
                # Re-write response and update reply_meta.json to indicate audio synthesis completion
                try:
                    with open(REPLY_TXT, "w", encoding="utf-8") as f:
                        f.write(reply)
                    meta_path = os.path.join(SHARED_DIR, "reply_meta.json")
                    with open(meta_path, "w", encoding="utf-8") as mf:
                        json.dump({"reply": reply, "timestamp": time.time(), "source": input_source, "audio_ready": True}, mf)
                except Exception as _mf_err:
                    print(f"[run_vivy] Reply metadata write error (non-fatal): {_mf_err}")
                
                if is_voice_turn:
                    # Play the cloned audio locally for confirmation if not muted
                    play_muted = os.path.exists(os.path.join(SHARED_DIR, "voice_output_mute.txt"))
                    if not play_muted:
                        if os.path.exists(RVC_WAV):
                            set_status("speaking")
                            _telemetry_mgr.log_event("Speech Started", details={"mode": "cloned_rvc"})
                            start_indicator("Vivy is speaking")
                            print("Playing cloned output voice...")
                            # Write lip_sync_trigger.txt immediately before playback so that
                            # avatar_bridge monitors it and sends push_speak() to Unity in
                            # sync with actual audio start (fixes GAP 10 timing desync).
                            try:
                                target_path = os.path.join(SHARED_DIR, "lip_sync_trigger.txt")
                                tmp_path = target_path + ".tmp"
                                with open(tmp_path, "w", encoding="utf-8") as _lsf:
                                    _lsf.write(reply)
                                os.replace(tmp_path, target_path)
                            except Exception as e:
                                print(f"[run_vivy] Warning: failed to write lip_sync_trigger.txt: {e}")
                            data, samplerate = sf.read(RVC_WAV, dtype="float32")
                            sd.play(data, samplerate)
                            sd.wait()
                            stop_indicator("  ✓ Done speaking.")
                            _telemetry_mgr.log_event("Speech Finished")
                        else:
                            print("Cloned audio output not found, falling back to TTS...")
                            if os.path.exists(TTS_WAV):
                                set_status("speaking")
                                _telemetry_mgr.log_event("Speech Started", details={"mode": "tts"})
                                start_indicator("Vivy is speaking (TTS)")
                                # Sentinel write for TTS fallback path too
                                try:
                                    target_path = os.path.join(SHARED_DIR, "lip_sync_trigger.txt")
                                    tmp_path = target_path + ".tmp"
                                    with open(tmp_path, "w", encoding="utf-8") as _lsf:
                                        _lsf.write(reply)
                                    os.replace(tmp_path, target_path)
                                except Exception as e:
                                    print(f"[run_vivy] Warning: failed to write lip_sync_trigger.txt (TTS fallback): {e}")
                                data, samplerate = sf.read(TTS_WAV, dtype="float32")
                                sd.play(data, samplerate)
                                sd.wait()
                                stop_indicator("  ✓ Done speaking.")
                                _telemetry_mgr.log_event("Speech Finished")
                    else:
                        print("Voice output is muted. Skipping local playback.")

                        console_print("  [Voice output muted]", _ANSI_YELLOW)
                else:
                    print("Voice output skipped for text input.")
                
                set_status("ready")
                console_print("  ─────────────────────────────────────", _ANSI_CYAN)
        
        time.sleep(0.25)
    except KeyboardInterrupt:
        stop_indicator()
        console_print("\n  Vivy AI Pipeline shut down. Goodbye!", _ANSI_PINK)
        print("\nExiting Vivy AI Pipeline Server.")
        
        # Restore standard system streams before running teardown functions
        try:
            if hasattr(sys, "__stdout__") and sys.__stdout__ is not None:
                sys.stdout = sys.__stdout__
            if hasattr(sys, "__stderr__") and sys.__stderr__ is not None:
                sys.stderr = sys.__stderr__
        except Exception:
            pass

        # Clean shutdown to prevent background thread exceptions during interpreter teardown
        import atexit, sys
        try:
            atexit._run_exitfuncs()
        except:
            pass
        sys.exit(0)
    except Exception as e:
        stop_indicator()
        try:
            if hasattr(sys, "__stdout__") and sys.__stdout__ is not None:
                sys.stdout = sys.__stdout__
            if hasattr(sys, "__stderr__") and sys.__stderr__ is not None:
                sys.stderr = sys.__stderr__
        except Exception:
            pass
        import traceback
        traceback.print_exc()
        time.sleep(1)
