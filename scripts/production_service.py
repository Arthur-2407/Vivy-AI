#!/usr/bin/env python3
"""
Vivy-AI — Production Service Supervisor & Daemon Manager
Provides daemonized process management, watchdog supervision, graceful shutdown,
and lifecycle tracking for the complete Vivy-AI runtime stack.
"""

import sys
import os
import time
import psutil
import argparse
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SHARED_DIR = BASE_DIR / "shared"
LOGS_DIR = BASE_DIR / "logs"
PID_FILE = SHARED_DIR / "vivy_production.pid"
LOG_FILE = LOGS_DIR / "vivy_production.log"

SHARED_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)


def get_python_exe() -> str:
    venv_py = BASE_DIR / "venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        return str(venv_py)
    return sys.executable


def get_running_process() -> psutil.Process | None:
    # 1. Check via recorded PID file
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            if psutil.pid_exists(pid):
                proc = psutil.Process(pid)
                if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                    try:
                        cmd = " ".join(proc.cmdline()).lower()
                        if "python" in cmd and "run_vivy.py" in cmd:
                            return proc
                    except (psutil.AccessDenied, psutil.ZombieProcess):
                        if "python" in proc.name().lower():
                            return proc
        except Exception:
            pass

    # 2. Fallback: Scan process table for active run_vivy.py
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                name = proc.info.get('name', '').lower()
                cmdline = " ".join(proc.info.get('cmdline') or []).lower()
                if "python" in name and "run_vivy.py" in cmdline:
                    PID_FILE.write_text(str(proc.pid))
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass

    return None


def start_service(foreground: bool = False) -> int:
    proc = get_running_process()
    if proc:
        print(f"[Service] Vivy is already running (PID: {proc.pid})")
        return 0

    py_exe = get_python_exe()
    entrypoint = str(BASE_DIR / "run_vivy.py")

    print(f"[Service] Starting Vivy AI Production Runtime...")
    print(f"          Executable : {py_exe}")
    print(f"          Entrypoint : {entrypoint}")
    print(f"          Log file   : {LOG_FILE}")

    env = os.environ.copy()
    env["VIVY_PROCESS_ROLE"] = "runner"
    env["PYTHONUNBUFFERED"] = "1"

    if foreground:
        print("[Service] Running in foreground supervisor mode (Press Ctrl+C to stop)...")
        max_restarts = 10
        restart_count = 0
        while restart_count < max_restarts:
            start_time = time.time()
            with open(LOG_FILE, "a", encoding="utf-8") as out:
                sub = subprocess.Popen([py_exe, entrypoint], cwd=str(BASE_DIR), env=env, stdout=out, stderr=out)
                PID_FILE.write_text(str(sub.pid))
                print(f"[Service] Spawned instance PID: {sub.pid}")
                try:
                    ret = sub.wait()
                    print(f"[Service] Process exited with code {ret}")
                except KeyboardInterrupt:
                    print("\n[Service] Stopping supervisor and child process...")
                    stop_service()
                    break

            uptime = time.time() - start_time
            if uptime > 60:
                restart_count = 0
            else:
                restart_count += 1

            if restart_count >= max_restarts:
                print(f"[Service] Exceeded max rapid restarts ({max_restarts}). Terminating.")
                break
            time.sleep(2)
        return 0
    else:
        # Background daemon spawn via WMI on Windows to escape caller's job object
        if sys.platform == "win32":
            cmd_line = f'cmd.exe /c ""{py_exe}" "{entrypoint}" > "{LOG_FILE}" 2>&1"'
            ps_script = (
                f'$res = Invoke-CimMethod -ClassName Win32_Process -MethodName Create '
                f'-Arguments @{{CommandLine = \'{cmd_line}\'; CurrentDirectory = \'{str(BASE_DIR)}\'}}; '
                f'$res.ProcessId'
            )
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script],
                                 capture_output=True, text=True, check=True)
            wmi_pid_str = res.stdout.strip()
            print(f"[Service] WMI daemon launcher initiated (Launcher PID: {wmi_pid_str})")
        else:
            out_f = open(LOG_FILE, "a", encoding="utf-8")
            sub = subprocess.Popen([py_exe, entrypoint], cwd=str(BASE_DIR), env=env,
                                   stdin=subprocess.DEVNULL, stdout=out_f, stderr=out_f)
            PID_FILE.write_text(str(sub.pid))

        # Probe for the python process running run_vivy.py
        print("[Service] Waiting for Vivy runtime initialization...")
        for i in range(20):
            time.sleep(1)
            p = get_running_process()
            if p:
                print(f"[Service] Vivy AI runtime active (PID: {p.pid})")
                return 0

        print("[Service] Runtime started. Verifying background health...")
        return 0


def stop_service() -> int:
    proc = get_running_process()
    if proc:
        print(f"[Service] Stopping Vivy AI (PID: {proc.pid})...")
        try:
            children = proc.children(recursive=True)
            for child in children:
                try:
                    child.terminate()
                except Exception:
                    pass

            proc.terminate()
            try:
                proc.wait(timeout=6)
            except psutil.TimeoutExpired:
                print("[Service] Process did not terminate within timeout. Forcing kill...")
                for child in children:
                    try: child.kill()
                    except Exception: pass
                proc.kill()
                proc.wait(timeout=3)
        except Exception as e:
            print(f"[Service] Exception while stopping process: {e}")

    # Also terminate any lingering service processes on ports 8080, 8800, 8765, 8766
    for port in (8080, 8800, 8765, 8766):
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.laddr.port == port and conn.pid:
                    try:
                        p = psutil.Process(conn.pid)
                        p.terminate()
                    except Exception:
                        pass
        except Exception:
            pass

    if PID_FILE.exists():
        PID_FILE.unlink(missing_ok=True)

    print("[Service] Vivy AI stopped successfully.")
    return 0


def status_service() -> int:
    proc = get_running_process()
    if not proc:
        print("[Service] Status: STOPPED (No active process)")
        return 1

    try:
        cpu = proc.cpu_percent(interval=0.2)
        mem = proc.memory_info().rss / (1024 * 1024)
        uptime = time.time() - proc.create_time()
        print(f"[Service] Status: RUNNING")
        print(f"          PID    : {proc.pid}")
        print(f"          Uptime : {int(uptime)}s")
        print(f"          Memory : {mem:.1f} MB")
        print(f"          CPU    : {cpu:.1f}%")

        children = proc.children(recursive=False)
        print(f"          Subprocesses ({len(children)}):")
        for c in children:
            try:
                c_cmd = " ".join(c.cmdline()[:2])
                print(f"            - PID {c.pid:<6} {c.name():<12} {c_cmd}")
            except Exception:
                pass
        return 0
    except Exception as e:
        print(f"[Service] Status check error: {e}")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vivy-AI Production Service Supervisor")
    parser.add_argument("action", choices=["start", "stop", "restart", "status", "run"], help="Service action")
    parser.add_argument("--foreground", action="store_true", help="Run supervisor in foreground")

    args = parser.parse_args()

    if args.action == "start":
        sys.exit(start_service(foreground=args.foreground))
    elif args.action == "stop":
        sys.exit(stop_service())
    elif args.action == "restart":
        stop_service()
        time.sleep(2)
        sys.exit(start_service(foreground=args.foreground))
    elif args.action == "status":
        sys.exit(status_service())
    elif args.action == "run":
        sys.exit(start_service(foreground=True))
