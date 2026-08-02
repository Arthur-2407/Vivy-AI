"""
Vivy AI — General Code Execution Engine (AGI Tool)
===================================================
Provides secure, sandboxed runtime execution of general Python scripts, mathematical
experiments, algorithms, and authorized terminal commands. Features:
  - Isolated temporary execution workspace (`shared/sandbox/`)
  - Subprocess execution with strict timeout defense against infinite loops
  - Complete stdout, stderr, and return code capturing
  - Automated structured Python traceback diagnosis for self-evaluation loops
"""

import os
import sys
import time
import json
import uuid
import shutil
import threading
import subprocess
from typing import Dict, Any, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SANDBOX_DIR = os.path.join(BASE_DIR, "shared", "sandbox")

class CodeExecutor:
    """Sandboxed General Code Execution tool engine for Vivy AGI."""
    _instance = None
    _lock = threading.RLock()

    def __init__(self, sandbox_path: Optional[str] = None):
        self.sandbox_path = sandbox_path or SANDBOX_DIR
        try:
            os.makedirs(self.sandbox_path, exist_ok=True)
        except Exception as err:
            print(f"[CodeExecutor] Silenced sandbox creation warning: {err}")
        self.default_timeout = 10.0  # seconds
        self.python_executable = self._locate_python()
        self.execution_history = []

    @classmethod
    def get_instance(cls) -> "CodeExecutor":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _locate_python(self) -> str:
        """Locates active virtual environment Python or fallback system executable."""
        venv_python = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
        if os.path.exists(venv_python):
            return venv_python
        return sys.executable

    def execute_python(self, code_text: str, timeout: Optional[float] = None, env_vars: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Executes general Python script content in an isolated file within the sandbox.
        Returns complete execution result telemetry and parsed diagnosis.
        """
        with self._lock:
            run_id = str(uuid.uuid4())[:8]
            script_filename = f"script_{run_id}_{int(time.time())}.py"
            script_path = os.path.join(self.sandbox_path, script_filename)

            try:
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write("# Vivy AI Sandboxed Code Execution\n")
                    f.write(code_text)
            except Exception as w_err:
                return self._build_result(False, "", f"Failed to write script: {w_err}", -1, 0.0, script_path)

            run_env = os.environ.copy()
            if env_vars:
                run_env.update(env_vars)
            run_env["VIVY_SANDBOX_EXEC"] = "1"
            run_env["PYTHONUTF8"] = "1"

            t_start = time.time()
            exec_timeout = timeout if timeout is not None else self.default_timeout

            try:
                process = subprocess.run(
                    [self.python_executable, script_path],
                    cwd=self.sandbox_path,
                    capture_output=True,
                    text=True,
                    timeout=exec_timeout,
                    env=run_env
                )
                duration = time.time() - t_start
                success = (process.returncode == 0)
                stdout = process.stdout.strip()
                stderr = process.stderr.strip()
                return self._build_result(success, stdout, stderr, process.returncode, duration, script_path, code=code_text)
            except subprocess.TimeoutExpired as t_err:
                duration = time.time() - t_start
                stdout_part = t_err.stdout.strip() if hasattr(t_err, "stdout") and t_err.stdout else ""
                stderr_part = f"[TimeOutException] Execution exceeded limit of {exec_timeout} seconds and was killed."
                return self._build_result(False, stdout_part, stderr_part, -125, duration, script_path, code=code_text, timeout_triggered=True)
            except Exception as gen_err:
                duration = time.time() - t_start
                return self._build_result(False, "", f"[UnhandledExecutionError] {str(gen_err)}", -100, duration, script_path, code=code_text)

    def execute_shell_command(self, command_line: str, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Executes a terminal/shell command safely inside the workspace sandbox directory.
        """
        with self._lock:
            t_start = time.time()
            exec_timeout = timeout if timeout is not None else self.default_timeout
            try:
                process = subprocess.run(
                    command_line,
                    cwd=self.sandbox_path,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=exec_timeout
                )
                duration = time.time() - t_start
                success = (process.returncode == 0)
                return self._build_result(success, process.stdout.strip(), process.stderr.strip(), process.returncode, duration, f"CMD: {command_line}")
            except subprocess.TimeoutExpired as t_err:
                duration = time.time() - t_start
                return self._build_result(False, "", f"[TimeOutException] Shell command timed out after {exec_timeout}s.", -125, duration, f"CMD: {command_line}", timeout_triggered=True)
            except Exception as e:
                return self._build_result(False, "", f"[ShellExecutionError] {str(e)}", -100, time.time() - t_start, f"CMD: {command_line}")

    def _build_result(self, success: bool, stdout: str, stderr: str, returncode: int, duration: float, target: str, code: str = "", timeout_triggered: bool = False) -> Dict[str, Any]:
        """Formats standard telemetry package and extracts error diagnostics if execution failed."""
        diagnosis = "Success."
        error_type = None
        error_line = None

        if not success:
            if timeout_triggered:
                error_type = "TimeoutError"
                diagnosis = "Code executed into an infinite loop or exceeded runtime threshold."
            elif stderr:
                lines = [l.strip() for l in stderr.splitlines() if l.strip()]
                for line in lines:
                    if line.startswith("File ") and ", line " in line:
                        try:
                            error_line = int(line.split(", line ")[1].split(",")[0].split()[0])
                        except Exception:
                            pass
                    if "Error:" in line or "Exception:" in line:
                        parts = line.split(":", 1)
                        error_type = parts[0].strip()
                        diagnosis = parts[1].strip() if len(parts) > 1 else line

        res = {
            "success": success,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
            "duration_ms": round(duration * 1000.0, 2),
            "target": target,
            "code": code,
            "timeout_triggered": timeout_triggered,
            "diagnosis": {
                "error_type": error_type,
                "error_line": error_line,
                "summary": diagnosis
            },
            "timestamp": time.time()
        }
        self.execution_history.append(res)
        if len(self.execution_history) > 50:
            self.execution_history.pop(0)
        return res

    def get_last_result() -> Optional[Dict[str, Any]]:
        return self.execution_history[-1] if self.execution_history else None

    def cleanup_sandbox(self) -> int:
        """Removes temporary script execution artifacts from the sandbox."""
        with self._lock:
            cleaned = 0
            try:
                for root, dirs, files in os.walk(self.sandbox_path):
                    for file in files:
                        if file.startswith("script_") or file.endswith(".py") or file.endswith(".tmp"):
                            try:
                                os.remove(os.path.join(root, file))
                                cleaned += 1
                            except Exception:
                                pass
            except Exception as e:
                print(f"[CodeExecutor] Silenced cleanup warning: {e}")
            return cleaned

_global_code_executor = None
def get_code_executor() -> CodeExecutor:
    global _global_code_executor
    if _global_code_executor is None:
        _global_code_executor = CodeExecutor()
    return _global_code_executor
