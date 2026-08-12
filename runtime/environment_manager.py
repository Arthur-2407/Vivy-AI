"""
runtime/environment_manager.py
===============================
Vivy Runtime Environment Manager.

Responsibilities:
  - Discover and validate Python environments declared in runtime_registry.json.
  - Resolve the correct interpreter for a given environment by logical name.
  - Validate actual interpreter version and capabilities against declared expectations.
  - Report discrepancies clearly rather than silently falling back to an unrelated interpreter.

Design Principles:
  - The registry describes INTENT (ownership, expected capabilities, relative path).
  - This manager resolves REALITY (actual executable, actual Python version, actual CUDA status).
  - If reality diverges from intent, the discrepancy is reported at startup.
  - sys.executable is the correct choice when a child process belongs to the SAME environment
    as its parent. Use this manager only for CROSS-ENVIRONMENT subprocess launches.

Cross-environment subprocess rule:
  Same env:   use sys.executable  (web_server.py spawned from run_vivy.py in MAIN)
  Cross env:  use get_runtime_manager().get_python_executable("rvc")  (RVC workers)
              use get_runtime_manager().get_python_executable("avatar") (avatar bridge)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from typing import Any, Dict, List, Optional


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_PATH = os.path.join(BASE_DIR, "runtime", "runtime_registry.json")


class EnvironmentValidationResult:
    """Holds the result of validating a declared environment against reality."""

    def __init__(self, env_id: str):
        self.env_id = env_id
        self.valid = True
        self.warnings: List[str] = []
        self.errors: List[str] = []

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    def add_error(self, msg: str):
        self.errors.append(msg)
        self.valid = False

    def report(self):
        prefix = f"[RuntimeManager/{self.env_id}]"
        for w in self.warnings:
            print(f"{prefix} WARNING: {w}")
        for e in self.errors:
            print(f"{prefix} ERROR: {e}")
        if self.valid and not self.warnings:
            print(f"{prefix} OK — environment validated successfully.")


class EnvironmentInfo:
    """
    Resolved runtime information for a single named environment.
    Populated from the registry declaration + actual filesystem/interpreter checks.
    """

    def __init__(self, env_id: str, data: Dict[str, Any]):
        self.env_id = env_id
        self.relative_path: str = data.get("relative_path", "")
        self.owner: List[str] = data.get("owner", [])
        self.description: str = data.get("description", "")
        self.expected: Dict[str, Any] = data.get("expected", {})

        # Resolve absolute path using repository-relative discovery
        raw_path = os.path.join(BASE_DIR, self.relative_path.replace("/", os.sep))
        self.python_executable: str = raw_path

        # Resolved metadata (populated during validation)
        self.actual_python_version: Optional[str] = None
        self.actual_python_major: Optional[int] = None
        self.actual_python_minor: Optional[int] = None
        self.validation_result: Optional[EnvironmentValidationResult] = None

    @property
    def is_available(self) -> bool:
        """Returns True if the executable file exists on disk."""
        return os.path.exists(self.python_executable)

    def validate(self) -> EnvironmentValidationResult:
        """
        Validates the environment against the declared expectations.
        Checks:
          - Executable exists
          - Python version matches expected major/minor
          - CUDA availability if cuda_required=True
        Does NOT crash — all findings are returned as warnings/errors.
        """
        result = EnvironmentValidationResult(self.env_id)

        if not self.is_available:
            result.add_error(
                f"Interpreter not found at '{self.python_executable}'. "
                f"Expected relative path: '{self.relative_path}'."
            )
            self.validation_result = result
            return result

        # Probe Python version
        try:
            probe = subprocess.run(
                [self.python_executable, "-c",
                 "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                capture_output=True, text=True, timeout=10
            )
            if probe.returncode == 0:
                ver_str = probe.stdout.strip()
                parts = ver_str.split(".")
                self.actual_python_version = ver_str
                self.actual_python_major = int(parts[0])
                self.actual_python_minor = int(parts[1])
            else:
                result.add_warning(
                    f"Could not probe Python version: {probe.stderr.strip()[:200]}"
                )
        except Exception as e:
            result.add_warning(f"Version probe failed: {e}")

        # Check declared version expectation
        exp_major = self.expected.get("python_major")
        exp_minor = self.expected.get("python_minor")
        if exp_major is not None and self.actual_python_major is not None:
            if self.actual_python_major != exp_major:
                result.add_error(
                    f"Python major version mismatch: expected {exp_major}, "
                    f"got {self.actual_python_major}."
                )
        if exp_minor is not None and self.actual_python_minor is not None:
            if self.actual_python_minor != exp_minor:
                result.add_warning(
                    f"Python minor version mismatch: expected {exp_major}.{exp_minor}, "
                    f"got {self.actual_python_major}.{self.actual_python_minor}."
                )

        # Check CUDA if required
        if self.expected.get("cuda_required"):
            try:
                cuda_probe = subprocess.run(
                    [self.python_executable, "-c",
                     "import torch; print('cuda_available=' + str(torch.cuda.is_available()))"],
                    capture_output=True, text=True, timeout=30
                )
                if cuda_probe.returncode == 0:
                    cuda_ok = "cuda_available=True" in cuda_probe.stdout
                    if not cuda_ok:
                        result.add_error(
                            f"CUDA is declared required for '{self.env_id}' but "
                            f"torch.cuda.is_available() returned False. "
                            f"RVC training/inference will not use GPU."
                        )
                else:
                    result.add_warning(
                        f"CUDA probe failed (torch may not be installed): "
                        f"{cuda_probe.stderr.strip()[:200]}"
                    )
            except Exception as e:
                result.add_warning(f"CUDA probe exception: {e}")

        self.validation_result = result
        return result


class RuntimeManager:
    """
    Centralized manager for resolving and validating Python environments in Vivy.

    Singleton. Thread-safe. Loaded once at startup.

    Usage:
        from runtime.environment_manager import get_runtime_manager
        mgr = get_runtime_manager()

        # Cross-environment spawn (e.g., launching RVC workers):
        rvc_python = mgr.get_python_executable("rvc")

        # Same-environment spawn (e.g., web_server from run_vivy):
        use sys.executable directly.

        # Check environment health:
        mgr.print_startup_diagnostics()
    """

    _instance: Optional["RuntimeManager"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.registry: Dict[str, EnvironmentInfo] = {}
        self._load_registry()

    @classmethod
    def get_instance(cls) -> "RuntimeManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = RuntimeManager()
        return cls._instance

    def _load_registry(self):
        if not os.path.exists(REGISTRY_PATH):
            print(f"[RuntimeManager] WARNING: Registry not found at '{REGISTRY_PATH}'. "
                  f"All environment lookups will fall back to sys.executable.")
            return
        try:
            with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            envs = data.get("environments", {})
            for env_id, env_data in envs.items():
                self.registry[env_id] = EnvironmentInfo(env_id, env_data)
            print(f"[RuntimeManager] Loaded {len(self.registry)} environment(s) from registry.")
        except Exception as e:
            print(f"[RuntimeManager] ERROR loading registry: {e}")

    def get_python_executable(self, env_id: str, fallback_to_sys: bool = True) -> str:
        """
        Resolves the exact Python executable for a given environment ID.

        - If the declared environment exists and is available on disk, returns its path.
        - If the environment is not found in the registry or the executable is missing:
            - If fallback_to_sys=True (default): logs a warning and returns sys.executable.
            - If fallback_to_sys=False: raises FileNotFoundError.

        Note: For same-environment subprocesses, prefer sys.executable directly.
        This method is intended for cross-environment subprocess launches only.
        """
        env_info = self.registry.get(env_id)
        if env_info is not None:
            if env_info.is_available:
                return env_info.python_executable
            else:
                msg = (
                    f"[RuntimeManager] WARNING: Environment '{env_id}' is declared in the registry "
                    f"but its interpreter was not found at '{env_info.python_executable}'. "
                )
                if fallback_to_sys:
                    print(msg + f"Falling back to sys.executable='{sys.executable}'.")
                    return sys.executable
                else:
                    raise FileNotFoundError(
                        msg + "No fallback allowed (fallback_to_sys=False)."
                    )
        else:
            msg = f"[RuntimeManager] WARNING: Environment '{env_id}' is not declared in the registry. "
            if fallback_to_sys:
                print(msg + f"Falling back to sys.executable='{sys.executable}'.")
                return sys.executable
            else:
                raise KeyError(
                    msg + f"No fallback allowed. "
                    f"Available environments: {list(self.registry.keys())}"
                )

    def get_environment(self, env_id: str) -> Optional[EnvironmentInfo]:
        """Returns the EnvironmentInfo object for a given environment ID, or None."""
        return self.registry.get(env_id)

    def validate_all(self) -> Dict[str, EnvironmentValidationResult]:
        """
        Validates all declared environments against their actual state.
        Runs interpreter probes. Returns a dict of env_id -> ValidationResult.
        This is a blocking operation (spawns subprocess per environment).
        """
        results = {}
        for env_id, env_info in self.registry.items():
            results[env_id] = env_info.validate()
        return results

    def print_startup_diagnostics(self, validate: bool = False):
        """
        Prints a human-readable startup diagnostic report for all declared environments.
        If validate=True, performs full interpreter probes (slower but more informative).
        """
        print("\n" + "=" * 60)
        print("  Vivy Runtime Environment Diagnostics")
        print("=" * 60)
        for env_id, env_info in self.registry.items():
            status = "✓ AVAILABLE" if env_info.is_available else "✗ MISSING"
            print(f"  [{env_id:10s}] {status}")
            print(f"              Path  : {env_info.python_executable}")
            print(f"              Owners: {', '.join(env_info.owner)}")
            if validate and env_info.is_available:
                result = env_info.validate()
                if env_info.actual_python_version:
                    print(f"              Python: {env_info.actual_python_version}")
                result.report()
            elif not env_info.is_available:
                print(f"              Declared: {env_info.relative_path}")
        print("=" * 60 + "\n")


def get_runtime_manager() -> RuntimeManager:
    """Returns the process-level singleton RuntimeManager instance."""
    return RuntimeManager.get_instance()
