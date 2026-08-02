"""
Vivy AI — Centralized Configuration Management System
======================================================
Provides unified configuration loading, hot reload, feature flags,
and schema validation across all Python modules.
"""

from .config_manager import ConfigManager, get_config_manager

__all__ = ["ConfigManager", "get_config_manager"]
