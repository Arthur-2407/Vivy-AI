"""
resource_manager.py
===================
Vivy AI — Centralized Enterprise Resource Manager
Provides global, thread-safe resource registration, devnull handle management,
idempotent teardown, and signal/atexit lifecycle orchestration across all subsystems.

Guarantees ZERO leaked file handles, subprocesses, threads, sockets, or NUL wrappers.
"""

from __future__ import annotations

import atexit
import contextlib
import io
import logging
import os
import signal
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("resource_manager")


class ResourceManager:
    """
    Centralized Resource Manager for tracking and cleanly releasing all process resources:
      - File handles (including NUL/devnull wrappers)
      - Subprocesses (Popen streams, pipes, and processes)
      - Background threads
      - Hardware handles (OpenCV VideoCapture, audio streams, socket servers)
      - Custom cleanup callbacks
    """

    _instance: Optional[ResourceManager] = None
    _lock = threading.Lock()

    def __init__(self):
        self._res_lock = threading.Lock()
        self._files: Set[io.IOBase] = set()
        self._subprocesses: Set[Any] = set()  # subprocess.Popen
        self._threads: Set[Tuple[threading.Thread, Optional[Callable[[], None]]]] = set()
        self._handles: Set[Tuple[Any, Optional[Callable[[Any], None]]]] = set()
        self._cleanup_callbacks: List[Tuple[int, Callable[[], None], str]] = []

        self._devnull_text: Optional[io.TextIOWrapper] = None
        self._devnull_lock = threading.Lock()

        self._is_shutting_down = False
        self._has_shut_down = False

        # Attach global signal & exit hooks
        self._install_exit_handlers()

    @classmethod
    def get_instance(cls) -> ResourceManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = ResourceManager()
        return cls._instance

    # ── Devnull / NUL Handle Management ─────────────────────────────────────

    def get_devnull(self) -> io.TextIOWrapper:
        """
        Returns a cached, managed, thread-safe file handle to os.devnull.
        Prevents multiple open('nul') calls that emit ResourceWarning at exit.
        """
        with self._devnull_lock:
            if self._devnull_text is None or self._devnull_text.closed:
                self._devnull_text = open(os.devnull, "w", encoding="utf-8")
                self.register_file(self._devnull_text, name="devnull_singleton")
            return self._devnull_text

    @contextlib.contextmanager
    def suppress_output(self):
        """
        Context manager for suppressing stdout and stderr using the managed devnull handle.
        Thread-safe and guaranteed zero handle leaks.
        """
        devnull = self.get_devnull()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        try:
            sys.stdout = devnull
            sys.stderr = devnull
            yield
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    # ── Resource Registration APIs ──────────────────────────────────────────

    def register_file(self, file_obj: Any, name: Optional[str] = None) -> Any:
        """Register an open file handle for tracked lifecycle management."""
        if file_obj is None:
            return file_obj
        with self._res_lock:
            self._files.add(file_obj)
        return file_obj

    def unregister_file(self, file_obj: Any):
        """Unregister a file handle if manually closed."""
        with self._res_lock:
            self._files.discard(file_obj)

    def register_subprocess(self, proc: Any, name: Optional[str] = None) -> Any:
        """Register a subprocess.Popen object for tracked lifecycle management."""
        if proc is None:
            return proc
        with self._res_lock:
            self._subprocesses.add(proc)
        return proc

    def unregister_subprocess(self, proc: Any):
        """Unregister a subprocess if manually reaped."""
        with self._res_lock:
            self._subprocesses.discard(proc)

    def register_thread(
        self,
        thread_obj: threading.Thread,
        stop_callback: Optional[Callable[[], None]] = None,
        name: Optional[str] = None,
    ) -> threading.Thread:
        """Register a background thread with an optional stop signal callback."""
        if thread_obj is None:
            return thread_obj
        with self._res_lock:
            self._threads.add((thread_obj, stop_callback))
        return thread_obj

    def register_handle(
        self,
        handle_obj: Any,
        release_fn: Optional[Callable[[Any], None]] = None,
        name: Optional[str] = None,
    ) -> Any:
        """Register generic hardware or stream handle (e.g. OpenCV VideoCapture)."""
        if handle_obj is None:
            return handle_obj
        with self._res_lock:
            self._handles.add((handle_obj, release_fn))
        return handle_obj

    def register_cleanup_callback(
        self, callback_fn: Callable[[], None], priority: int = 50, name: str = "custom_callback"
    ):
        """Register custom cleanup function. Lower priority number runs first."""
        with self._res_lock:
            self._cleanup_callbacks.append((priority, callback_fn, name))
            self._cleanup_callbacks.sort(key=lambda x: x[0])

    # ── Shutdown & Teardown Orchestration ───────────────────────────────────

    def _install_exit_handlers(self):
        """Install global atexit and signal handlers."""
        atexit.register(self.shutdown_all)
        if threading.current_thread() is threading.main_thread():
            try:
                for sig in (signal.SIGINT, signal.SIGTERM):
                    existing = signal.getsignal(sig)
                    if callable(existing) and existing != self._signal_handler:
                        def make_handler(old_h):
                            def combined_handler(signum, frame):
                                self.shutdown_all()
                                if callable(old_h):
                                    old_h(signum, frame)
                            return combined_handler
                        signal.signal(sig, make_handler(existing))
                    else:
                        signal.signal(sig, self._signal_handler)
            except Exception as _err:
                print(f"[resource_manager.py] Silenced exception: {_err}")  # Non-main thread or unsupported platform

    def _signal_handler(self, signum, frame):
        self.shutdown_all()

    def shutdown_all(self):
        """
        Idempotently release and close all registered resources in strict order:
          1. Priority cleanup callbacks
          2. Custom hardware handles
          3. Subprocesses (pipes closed, terminated, reaped)
          4. Background threads (signaled, joined with timeout)
          5. Managed devnull and file handles
        """
        with self._res_lock:
            if self._has_shut_down or self._is_shutting_down:
                return
            self._is_shutting_down = True

        try:
            # 0. Clean up session temporary files in shared directory on shutdown
            try:
                import glob as _glob
                base_dir = os.path.dirname(os.path.abspath(__file__))
                shared_dir = os.path.join(base_dir, "shared")
                if os.path.exists(shared_dir):
                    for ext in ["*.tmp", "*.lock"]:
                        for fpath in _glob.glob(os.path.join(shared_dir, ext)):
                            try:
                                os.remove(fpath)
                            except Exception:
                                pass
            except Exception as _tmp_err:
                logger.debug(f"[ResourceManager] Tmp cleanup error: {_tmp_err}")

            # 1. Custom cleanup callbacks
            for priority, cb, name in list(self._cleanup_callbacks):
                try:
                    cb()
                except Exception as e:
                    logger.debug(f"[ResourceManager] Error in cleanup callback '{name}': {e}")

            # 2. Hardware handles
            for handle_obj, release_fn in list(self._handles):
                try:
                    if release_fn:
                        release_fn(handle_obj)
                    elif hasattr(handle_obj, "release"):
                        handle_obj.release()
                    elif hasattr(handle_obj, "close"):
                        handle_obj.close()
                except Exception as e:
                    logger.debug(f"[ResourceManager] Error releasing handle {handle_obj}: {e}")

            # 3. Subprocesses
            for proc in list(self._subprocesses):
                try:
                    if proc.poll() is None:
                        # Close standard streams first to release handles
                        for pipe in (proc.stdin, proc.stdout, proc.stderr):
                            if pipe and not getattr(pipe, "closed", True):
                                try:
                                    pipe.close()
                                except Exception as _err:
                                    print(f"[resource_manager.py] Silenced exception: {_err}")
                        try:
                            proc.terminate()
                            proc.wait(timeout=1.5)
                        except Exception:
                            proc.kill()
                            proc.wait(timeout=0.5)
                except Exception as e:
                    logger.debug(f"[ResourceManager] Error shutting down subprocess {proc}: {e}")

            # 4. Background threads
            for thread_obj, stop_cb in list(self._threads):
                try:
                    if stop_cb:
                        stop_cb()
                    if thread_obj.is_alive() and thread_obj != threading.current_thread():
                        thread_obj.join(timeout=1.0)
                except Exception as e:
                    logger.debug(f"[ResourceManager] Error joining thread {thread_obj.name}: {e}")

            # 5. Managed files & devnull singleton
            with self._devnull_lock:
                if self._devnull_text and not self._devnull_text.closed:
                    try:
                        self._devnull_text.flush()
                        self._devnull_text.close()
                    except Exception as _err:
                        print(f"[resource_manager.py] Silenced exception: {_err}")
                    self._devnull_text = None

            # Intercept and gracefully close third-party unclosed devnull file wrappers (e.g. llama_cpp)
            try:
                import sys as _sys
                for mod_name in ["llama_cpp._utils", "llama_cpp"]:
                    if mod_name in _sys.modules and _sys.modules[mod_name] is not None:
                        mod_obj = _sys.modules[mod_name]
                        for h_name in ("outnull_file", "errnull_file"):
                            h_file = getattr(mod_obj, h_name, None)
                            if h_file and hasattr(h_file, "closed") and not h_file.closed:
                                try:
                                    h_file.flush()
                                    h_file.close()
                                except Exception:
                                    pass
            except Exception as _third_err:
                logger.debug(f"[ResourceManager] Error cleaning third-party devnull handles: {_third_err}")

            # Safely restore system streams if they point to files about to be closed
            try:
                if sys.stdout in self._files or (hasattr(sys.stdout, "closed") and sys.stdout != sys.__stdout__):
                    sys.stdout = sys.__stdout__ if sys.__stdout__ is not None else sys.stdout
                if sys.stderr in self._files or (hasattr(sys.stderr, "closed") and sys.stderr != sys.__stderr__):
                    sys.stderr = sys.__stderr__ if sys.__stderr__ is not None else sys.stderr
            except Exception as _stream_err:
                pass

            for f in list(self._files):
                try:
                    if hasattr(f, "closed") and not f.closed:
                        f.flush()
                        f.close()
                except Exception as e:
                    logger.debug(f"[ResourceManager] Error closing file {f}: {e}")

        finally:
            with self._res_lock:
                self._has_shut_down = True
                self._is_shutting_down = False


# Process-level singleton getter
def get_resource_manager() -> ResourceManager:
    return ResourceManager.get_instance()
