import subprocess
import sys
import time
import os
import signal

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
python_exe = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
run_script = os.path.join(BASE_DIR, "run_vivy.py")
trace_log = os.path.join(BASE_DIR, "shared", "startup_trace.log")
pipeline_log = os.path.join(BASE_DIR, "shared", "pipeline.log")

# Clear past startup trace
if os.path.exists(trace_log):
    try: os.remove(trace_log)
    except Exception: pass

print(f"[TEST_RUNNER] Spawning {run_script} with {python_exe}...")
proc = subprocess.Popen(
    [python_exe, run_script],
    cwd=BASE_DIR,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
)

start_t = time.time()
ready_found = False

print("[TEST_RUNNER] Monitoring process startup for 10 seconds...")
try:
    for _ in range(20):
        time.sleep(0.5)
        if proc.poll() is not None:
            print(f"[TEST_RUNNER] Process exited prematurely with code {proc.returncode}")
            out, _ = proc.communicate()
            print(f"[TEST_RUNNER] Output:\n{out}")
            break
        
        # Check trace log
        if os.path.exists(trace_log):
            with open(trace_log, "r", encoding="utf-8") as tf:
                content = tf.read()
                if "pipeline_ready" in content:
                    ready_found = True
                    print(f"[TEST_RUNNER] SUCCESS: pipeline_ready trace found! Startup took {time.time() - start_t:.2f}s")
                    break

finally:
    if proc.poll() is None:
        print("[TEST_RUNNER] Sending Ctrl+C signal to process...")
        if os.name == 'nt':
            proc.send_signal(signal.CTRL_C_EVENT)
            time.sleep(1)
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=3)
        print("[TEST_RUNNER] Process terminated cleanly.")

print("\n--- STARTUP TRACE LOG ---")
if os.path.exists(trace_log):
    with open(trace_log, "r", encoding="utf-8") as tf:
        print(tf.read())
else:
    print("(Trace log not created)")

print("\n--- PIPELINE LOG (tail 20 lines) ---")
if os.path.exists(pipeline_log):
    with open(pipeline_log, "r", encoding="utf-8") as pf:
        lines = pf.readlines()
        print("".join(lines[-20:]))
