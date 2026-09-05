"""
Vivy Windows Node — Hardware Detector
Automatically discovers and reports this machine's hardware capabilities
so the Hub Execution Orchestrator can make informed routing decisions.
Never hardcodes resource values — reads actual system state at runtime.
Fault class: Recoverable (all detection blocks are individually guarded).
"""
import platform
import subprocess
import shutil
import os
from typing import Dict, Any


def detect() -> Dict[str, Any]:
    """
    Perform a full hardware capability scan and return a profile dict
    matching the hub.device_identity.DeviceProfile field names.
    """
    info: Dict[str, Any] = {
        "platform": "windows",
        "operating_system": "windows",
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "cpu_cores": 1,
        "ram_mb": 1024,
        "vram_mb": 0,
        "gpu_available": False,
        "storage_mb": 0,
        "camera_available": False,
        "mic_available": False,
        "speaker_available": False,
        "display_available": True,
        "gps_available": False,
        "bluetooth_available": False,
        "battery_pct": 100.0,
        "thermal_state": "normal",
        "sensors": [],
        "supported_runtimes": [],
        "local_llm": False,
        "local_vision": False,
        "local_tts": False,
        "performance_class": "medium",
        "network_class": "unknown",
        "metadata": {}
    }

    # ── CPU ─────────────────────────────────────────────────────────────────
    try:
        import psutil
        info["cpu_cores"] = psutil.cpu_count(logical=False) or 1
        info["cpu_threads"] = psutil.cpu_count(logical=True) or 1
        ram = psutil.virtual_memory()
        info["ram_mb"] = int(ram.total / (1024 * 1024))
        info["ram_available_mb"] = int(ram.available / (1024 * 1024))

        # Battery state
        batt = psutil.sensors_battery()
        if batt is not None:
            info["battery_pct"] = round(batt.percent, 1)
            info["metadata"]["ac_power"] = batt.power_plugged
        else:
            info["battery_pct"] = 100.0  # Desktop — treat as always powered

        # Storage
        total_storage = 0
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                total_storage += usage.total
            except Exception:
                pass
        info["storage_mb"] = int(total_storage / (1024 * 1024))
    except Exception as e:
        info["metadata"]["psutil_error"] = str(e)

    # ── CPU model ────────────────────────────────────────────────────────────
    try:
        result = subprocess.run(
            ["wmic", "cpu", "get", "Name", "/value"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if line.startswith("Name="):
                info["metadata"]["cpu_model"] = line.split("=", 1)[1].strip()
                break
    except Exception:
        pass

    # ── GPU / VRAM (NVIDIA) ──────────────────────────────────────────────────
    try:
        nv = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,memory.total,utilization.gpu,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if nv.returncode == 0 and nv.stdout.strip():
            parts = nv.stdout.strip().split("\n")[0].split(",")
            if len(parts) >= 2:
                info["gpu_available"] = True
                info["metadata"]["gpu_model"] = parts[0].strip()
                info["vram_mb"] = int(parts[1].strip())
                if len(parts) >= 3:
                    info["current_gpu_pct"] = float(parts[2].strip())
                if len(parts) >= 4:
                    temp = float(parts[3].strip())
                    info["metadata"]["gpu_temp_c"] = temp
                    if temp >= 85:
                        info["thermal_state"] = "hot"
                    elif temp >= 75:
                        info["thermal_state"] = "warm"
    except Exception:
        pass

    # ── GPU (AMD / Intel — fallback via WMI) ────────────────────────────────
    if not info["gpu_available"]:
        try:
            result = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "Name,AdapterRAM", "/value"],
                capture_output=True, text=True, timeout=5
            )
            lines = result.stdout.splitlines()
            names, rams = [], []
            for line in lines:
                if line.startswith("Name=") and line.split("=", 1)[1].strip():
                    names.append(line.split("=", 1)[1].strip())
                if line.startswith("AdapterRAM=") and line.split("=", 1)[1].strip():
                    try:
                        rams.append(int(line.split("=", 1)[1].strip()) // (1024 * 1024))
                    except Exception:
                        pass
            if names:
                info["gpu_available"] = True
                info["metadata"]["gpu_model"] = names[0]
                if rams:
                    info["vram_mb"] = rams[0]
        except Exception:
            pass

    # ── Camera ───────────────────────────────────────────────────────────────
    try:
        import cv2
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if cap.isOpened():
            info["camera_available"] = True
            cap.release()
    except Exception:
        pass

    # ── Microphone ──────────────────────────────────────────────────────────
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        for i in range(pa.get_device_count()):
            dev = pa.get_device_info_by_index(i)
            if dev.get("maxInputChannels", 0) > 0:
                info["mic_available"] = True
                break
        pa.terminate()
    except Exception:
        pass

    # ── Speaker ─────────────────────────────────────────────────────────────
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        for i in range(pa.get_device_count()):
            dev = pa.get_device_info_by_index(i)
            if dev.get("maxOutputChannels", 0) > 0:
                info["speaker_available"] = True
                break
        pa.terminate()
    except Exception:
        pass

    # ── Bluetooth ───────────────────────────────────────────────────────────
    try:
        result = subprocess.run(
            ["wmic", "path", "Win32_PnPEntity", "where", "Caption like '%Bluetooth%'", "get", "Caption"],
            capture_output=True, text=True, timeout=5
        )
        if "Bluetooth" in result.stdout:
            info["bluetooth_available"] = True
            
        # Detect BT PAN adapter presence and connection status
        nic_result = subprocess.run(
            ["wmic", "nic", "where", "Name like '%Bluetooth Device (Personal Area Network)%'", "get", "NetConnectionStatus"],
            capture_output=True, text=True, timeout=5
        )
        if "2" in nic_result.stdout:
            info["metadata"]["bt_pan_connected"] = True
        elif nic_result.stdout.strip():
            info["metadata"]["bt_pan_present"] = True
    except Exception:
        pass

    # ── Installed runtimes ───────────────────────────────────────────────────
    runtimes = []
    try:
        import torch
        runtimes.append("pytorch")
        if torch.cuda.is_available():
            runtimes.append("cuda")
            info["gpu_available"] = True
    except ImportError:
        pass
    try:
        import openvino
        runtimes.append("openvino")
    except ImportError:
        pass
    try:
        import onnxruntime
        providers = onnxruntime.get_available_providers()
        runtimes.append("onnxruntime")
        if "CUDAExecutionProvider" in providers:
            runtimes.append("onnxruntime-cuda")
    except ImportError:
        pass
    info["supported_runtimes"] = runtimes

    # ── Local capability flags ────────────────────────────────────────────────
    info["local_llm"] = "cuda" in runtimes or info["vram_mb"] >= 6000
    info["local_vision"] = info["gpu_available"]
    info["local_tts"] = True  # CPU TTS always possible on Windows

    # ── Performance class ─────────────────────────────────────────────────────
    vram = info["vram_mb"]
    ram = info["ram_mb"]
    cores = info["cpu_cores"]
    if vram >= 12000 and ram >= 32000:
        info["performance_class"] = "high"
    elif vram >= 6000 or ram >= 16000 and cores >= 8:
        info["performance_class"] = "medium"
    else:
        info["performance_class"] = "low"

    return info


if __name__ == "__main__":
    import json
    profile = detect()
    print(json.dumps(profile, indent=2))
