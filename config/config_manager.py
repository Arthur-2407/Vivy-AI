import os
import json
import time
import threading
from typing import Any, Dict, Optional

class ConfigManager:
    """
    Centralized Configuration System for Vivy AI (v1.0.0).
    Single source of truth for runtime configuration and feature flags.

    Supports:
      - Hierarchical key lookup (e.g. `get("pipeline.llm_temperature", 0.75)`)
      - Hot reload on file mtime change
      - Feature flag evaluations (`is_feature_enabled("procedural_breathing")`)
      - Thread safety
      - Backward compatibility with vivy_config.json
    """
    _instance = None
    _lock = threading.RLock()

    def __init__(self, config_path: Optional[str] = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config_path = config_path or os.path.join(base_dir, "vivy_config.json")
        self._config: Dict[str, Any] = {}
        self._feature_flags: Dict[str, bool] = {
            "procedural_breathing": True,
            "procedural_blinking": True,
            "procedural_saccades": True,
            "procedural_weight_shift": True,
            "emotion_modifier_layers": True,
            "structured_logging": True,
            "error_recovery": True,
            "behavior_tree": True,
            "hot_reload": True,
        }
        self._last_mtime: float = 0.0
        self._reload_thread: Optional[threading.Thread] = None
        self._running = False
        self.load_config()

    @classmethod
    def get_instance(cls, config_path: Optional[str] = None) -> "ConfigManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(config_path)
            return cls._instance

    def load_config(self) -> bool:
        with self._lock:
            if not os.path.exists(self.config_path):
                print(f"[ConfigManager] Config file not found at {self.config_path}. Using internal defaults.")
                return False
            try:
                mtime = os.path.getmtime(self.config_path)
                if mtime == self._last_mtime:
                    return True
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
                self._last_mtime = mtime
                # Extract any feature flags defined in config file
                if "feature_flags" in self._config:
                    self._feature_flags.update(self._config["feature_flags"])
                print(f"[ConfigManager] Successfully loaded configuration from {self.config_path}")
                return True
            except Exception as e:
                print(f"[ConfigManager] Failed to load config from {self.config_path}: {e}")
                return False

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation (e.g. 'pipeline.llm_temperature').
        """
        with self._lock:
            self._check_hot_reload()
            keys = key_path.split(".")
            curr = self._config
            for k in keys:
                if isinstance(curr, dict) and k in curr:
                    curr = curr[k]
                else:
                    return default
            return curr

    def set(self, key_path: str, value: Any) -> None:
        """Dynamically set a configuration value at runtime."""
        with self._lock:
            keys = key_path.split(".")
            curr = self._config
            for k in keys[:-1]:
                if k not in curr or not isinstance(curr[k], dict):
                    curr[k] = {}
                curr = curr[k]
            curr[keys[-1]] = value

    def is_feature_enabled(self, flag_name: str, default: bool = True) -> bool:
        """Evaluate whether a feature flag is enabled."""
        with self._lock:
            return self._feature_flags.get(flag_name, default)

    def set_feature_flag(self, flag_name: str, enabled: bool) -> None:
        """Set a feature flag state at runtime."""
        with self._lock:
            self._feature_flags[flag_name] = bool(enabled)

    def _check_hot_reload(self):
        if not self._config.get("pipeline", {}).get("enable_hot_reload", True):
            return
        if os.path.exists(self.config_path):
            try:
                mtime = os.path.getmtime(self.config_path)
                if mtime > self._last_mtime:
                    self.load_config()
            except Exception as _err:
                print(f"[config_manager.py] Silenced exception: {_err}")


_global_config_manager = None

def get_config_manager() -> ConfigManager:
    global _global_config_manager
    if _global_config_manager is None:
        _global_config_manager = ConfigManager.get_instance()
    return _global_config_manager
