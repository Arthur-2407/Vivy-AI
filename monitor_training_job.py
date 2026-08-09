import urllib.request
import json
import time
import os
import subprocess
import psutil

URL_PROGRESS = "http://127.0.0.1:8080/api/voice/train/progress"
URL_ALERT = "http://127.0.0.1:8080/api/voice/train/alert"
REPORT_PATH = "d:\\Vivy\\shared\\training_diagnostic_report.json"
MAX_IDLE_SECONDS = 600

def get_gpu_memory():
    try:
        # returns in MiB
        result = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,nounits,noheader"],
            stderr=subprocess.STDOUT
        ).decode("utf-8").strip()
        lines = result.split("\n")
        return [int(x.strip()) for x in lines if x.strip().isdigit()]
    except Exception:
        return []

def send_alert(message):
    try:
        data = json.dumps({"message": message}).encode('utf-8')
        req = urllib.request.Request(URL_ALERT, data=data, headers={'Content-Type': 'application/json'}, method='POST')
        urllib.request.urlopen(req, timeout=3)
    except Exception as e:
        print(f"Failed to send alert: {e}")

def monitor():
    print("Starting Voice Training Monitor (with Real-time UI Alerts and CPU/GPU Metrics)...")
    history = []
    start_time = time.time()
    last_active_time = time.time()
    job_started = False
    
    current_stage = None
    stage_start_time = None
    stage_durations = {}
    metrics_log = []

    while True:
        try:
            req = urllib.request.Request(URL_PROGRESS)
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
        except Exception as e:
            print(f"Error fetching progress: {e}")
            time.sleep(5)
            if time.time() - last_active_time > MAX_IDLE_SECONDS:
                break
            continue
            
        progress = data.get("progress", {})
        status = progress.get("status", "idle")
        label = progress.get("stage_label", "")
        percent = progress.get("percent", 0)
        
        # Collect Metrics
        if job_started:
            cpu_usage = psutil.cpu_percent(interval=None)
            gpu_mems = get_gpu_memory()
            metrics_log.append({
                "time": time.time(),
                "stage": current_stage,
                "cpu_percent": cpu_usage,
                "gpu_memory_mib": gpu_mems
            })
        
        # Track stages
        if status in ("training", "queuing"):
            if not job_started:
                send_alert("Active monitoring started for Voice Training.")
            job_started = True
            last_active_time = time.time()
            if label != current_stage:
                if current_stage and stage_start_time:
                    duration = time.time() - stage_start_time
                    stage_durations[current_stage] = duration
                    print(f"Stage '{current_stage}' completed in {duration:.2f}s")
                    
                    # Real-time alert for skipping
                    if "Extraction" in current_stage and duration < 5.0:
                        send_alert(f"Warning: '{current_stage}' finished abnormally fast ({duration:.2f}s). Possible skipping.")
                    if "Pre-processing" in current_stage and duration < 2.0:
                        send_alert(f"Warning: '{current_stage}' finished abnormally fast ({duration:.2f}s). Possible skipping.")
                        
                current_stage = label
                stage_start_time = time.time()
                print(f"New Stage: {label} ({percent}%)")
                if label:
                    send_alert(f"Started Stage: {label}")
        
        if status in ("finished", "error"):
            if current_stage and stage_start_time:
                duration = time.time() - stage_start_time
                stage_durations[current_stage] = duration
            print(f"Training completed with status: {status}")
            send_alert(f"Training completed with status: {status}")
            
            # Generate Report
            report = {
                "status": status,
                "total_duration": time.time() - start_time,
                "stage_durations": stage_durations,
                "final_progress_state": progress,
                "warnings": [],
                "metrics_log": metrics_log
            }
            
            # Analyze for skipping/bypassing
            for st, dur in stage_durations.items():
                if "Extraction" in st and dur < 5.0:
                    report["warnings"].append(f"Abnormal speed detected in '{st}' (Duration: {dur:.2f}s). Potential bypass or skip.")
                if "Pre-processing" in st and dur < 2.0:
                    report["warnings"].append(f"Pre-processing completed abnormally fast ({dur:.2f}s).")
            
            with open(REPORT_PATH, "w") as f:
                json.dump(report, f, indent=4)
                
            print(f"Report saved to {REPORT_PATH}")
            break
            
        if not job_started and (time.time() - start_time > MAX_IDLE_SECONDS):
            print("Monitor timed out waiting for job to start.")
            break
            
        time.sleep(1)

if __name__ == "__main__":
    # Wait for web server API to come online in case it was restarted
    time.sleep(2)
    monitor()
