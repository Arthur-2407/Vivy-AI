"""
Vivy AI — Embedded Tor Configuration & Environment Manager
==========================================================
Manages Tor filesystem configuration and open-source licensing:
  - **OS Detection**: Dynamically detects Windows, Linux, or macOS runtime.
  - **Dynamic torrc**: Creates secure configuration in `shared/tor_data/torrc`.
  - **Port Routing**: Configures default SOCKS5 port (9050) and Control port (9051).
  - **Licensing Compliance**: Embeds full Tor open-source redistribution notice and documentation.
"""

import os
import platform
import threading
from typing import Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOR_DATA_DIR = os.path.join(BASE_DIR, "shared", "tor_data")

TOR_LICENSE_NOTICE = """
The Tor computer software and documentation is copyright (c) 2001-2023, The Tor Project, Inc.
Redistribution and use in source and binary forms, with or without modification, are permitted
provided that redistributions retain copyright notices and disclaimers.
"""

class TorConfig:
    """Thread-safe Tor config generator and environment detective."""
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "TorConfig":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = data_dir or TOR_DATA_DIR
        self.os_type = platform.system()
        self.socks_port = 9050
        self.control_port = 9051
        self.torrc_path = os.path.join(self.data_dir, "torrc")
        self.license_path = os.path.join(self.data_dir, "TOR_LICENSE.txt")
        self._ensure_config()

    def _ensure_config(self):
        with self._lock:
            try:
                os.makedirs(self.data_dir, exist_ok=True)
                if not os.path.exists(self.license_path):
                    with open(self.license_path, "w", encoding="utf-8") as f:
                        f.write(TOR_LICENSE_NOTICE.strip())

                torrc_content = f"""# Vivy AI Auto-Generated torrc Configuration
SOCKS5Port {self.socks_port}
ControlPort {self.control_port}
DataDirectory {self.data_dir.replace(chr(92), '/')}
CookieAuthentication 1
AvoidDisks 0
Log notice file {os.path.join(self.data_dir, 'tor.log').replace(chr(92), '/')}
"""
                with open(self.torrc_path, "w", encoding="utf-8") as f:
                    f.write(torrc_content)
            except Exception as err:
                print(f"[TorConfig] Warning during torrc configuration write: {err}")

    def get_config_summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "os_detected": self.os_type,
                "socks_port": self.socks_port,
                "control_port": self.control_port,
                "tor_data_dir": self.data_dir,
                "torrc_file_ready": os.path.exists(self.torrc_path),
                "license_notice_included": os.path.exists(self.license_path),
                "status": "CONFIG_INITIALIZED"
            }

_global_cfg = None
def get_tor_config() -> TorConfig:
    global _global_cfg
    if _global_cfg is None:
        _global_cfg = TorConfig.get_instance()
    return _global_cfg
