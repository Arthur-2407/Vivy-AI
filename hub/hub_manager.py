"""
Vivy Hub - Main Ecosystem Manager
Top-level orchestrator for the Vivy capability federation.
Configuration is driven entirely by vivy_config.json via ConfigManager.
"""
import threading
from hub.pairing_manager import PairingManager
from hub.device_registry import DeviceRegistry
from hub.capability_router import CapabilityRouter
from hub.execution_orchestrator import ExecutionOrchestrator
from hub.sync_manager import SyncManager
from hub.vital_monitor import VitalMonitor
from hub.smart_home.gateway import SmartHomeGateway

# Phase 1 Transport Additions
from hub.transport.discovery import HubDiscovery
from hub.transport.ble_discovery import HubBleDiscovery
from hub.transport.udp_discovery import HubUdpDiscovery
from hub.transport.websocket_server import HubWebSocketServer
from hub.transport.message_dispatcher import MessageDispatcher

class VivyHub:
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self.pairing = PairingManager.get_instance()
        self.registry = DeviceRegistry.get_instance()
        self.router = CapabilityRouter.get_instance()
        self.orchestrator = ExecutionOrchestrator.get_instance()
        self.sync = SyncManager.get_instance()
        self.vitals = VitalMonitor.get_instance()
        self.smart_home = SmartHomeGateway.get_instance()
        
        self.discovery = HubDiscovery.get_instance()
        self.ble_discovery = HubBleDiscovery.get_instance()
        self.udp_discovery = HubUdpDiscovery.get_instance()
        self.ws_server = HubWebSocketServer.get_instance()
        self.dispatcher = MessageDispatcher()
        
        # Link WS Server to Dispatcher
        self.ws_server.set_dispatcher(self.dispatcher.dispatch)
        
        self._is_running = False

    @classmethod
    def get_instance(cls) -> "VivyHub":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def start(self, disable_discovery=None, port=None):
        """Start all hub background services and event listeners.

        Port and discovery settings are read from vivy_config.json when not explicitly provided.
        Defaults: port=8800 (README-specified Hub WS port), discovery enabled.
        Note: port 8766 is reserved for the RVC Voice Cloning XML-RPC server.
        """
        with self._lock:
            if self._is_running:
                return
            self._is_running = True

            # Read configuration from ConfigManager (config-driven, no hardcoding)
            try:
                from config.config_manager import get_config_manager
                _cfg = get_config_manager()
                if port is None:
                    port = int(_cfg.get("hub.port", 8800))
                if disable_discovery is None:
                    disable_discovery = bool(_cfg.get("hub.disable_discovery", False))
            except Exception as _cfg_err:
                print(f"[VivyHub] Config read warning (using defaults): {_cfg_err}")
                if port is None:
                    port = 8800
                if disable_discovery is None:
                    disable_discovery = False

            self.discovery.port = port
            self.ble_discovery.port = port
            self.udp_discovery.port = port
            self.ws_server.port = port

            # 1. Initialize self as Primary Host in the registry
            from hub.device_identity import DeviceProfile, DeviceRole, TrustLevel
            primary_profile = DeviceProfile(
                device_id="vivy_primary_host",
                device_type="server",
                role=DeviceRole.PRIMARY_HOST,
                trust_level=TrustLevel.FULLY_AUTHORIZED,
                local_llm=True,
                local_vision=True,
                local_tts=True,
                operating_system="windows",
                remote_execution_allowed=False,
            )
            # Dynamically detect primary host hardware — never hardcode resource values
            try:
                import psutil
                primary_profile.cpu_cores = psutil.cpu_count(logical=False) or 4
                ram = psutil.virtual_memory()
                primary_profile.ram_mb = int(ram.total / (1024 * 1024))
            except Exception as _hw_err:
                print(f"[VivyHub] psutil hardware detection warning: {_hw_err}")
                primary_profile.cpu_cores = 4
                primary_profile.ram_mb = 8192
            try:
                import subprocess as _sp
                _nv = _sp.run(
                    ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=3
                )
                if _nv.returncode == 0:
                    vram_str = _nv.stdout.strip().split("\n")[0].strip()
                    primary_profile.vram_mb = int(vram_str)
                    primary_profile.gpu_available = True
            except Exception:
                pass
            self.registry.register_device(primary_profile)

            # 1b. Register ALL built-in capability manifests.
            # Every feature in Vivy is registered here so the capability router
            # and execution orchestrator can service any request from any node.
            # Removing a capability here does not remove it from the backend;
            # it only makes it invisible to the Hub routing layer.
            from hub.capability_manifest import CapabilityManifest, ExecutionMode, LatencyClass
            _R = ExecutionMode.REMOTE
            _L = ExecutionMode.LOCAL
            _RT = LatencyClass.REALTIME
            _IN = LatencyClass.INTERACTIVE
            _BG = LatencyClass.BACKGROUND

            _manifests = [
                # ── Vision ──────────────────────────────────────────────────
                CapabilityManifest("vision.gaze",        "1.0", "vivy.core", [_L, _R], _RT, {"gpu": "preferred"}, security_level="low"),
                CapabilityManifest("vision.face",        "1.0", "vivy.core", [_L, _R], _RT, {"gpu": "preferred"}, security_level="low"),
                CapabilityManifest("vision.emotion",     "1.0", "vivy.core", [_L, _R], _RT, {"gpu": "preferred"}, security_level="low"),
                CapabilityManifest("vision.objects",     "1.0", "vivy.core", [_L, _R], _RT, {"gpu": "preferred"}, security_level="low"),
                CapabilityManifest("vision.gestures",    "1.0", "vivy.core", [_L, _R], _RT, {"gpu": "preferred"}, security_level="low"),
                CapabilityManifest("vision.stream",      "1.0", "vivy.core", [_L, _R], _RT, {"gpu": "preferred"}, security_level="low"),
                CapabilityManifest("vision.all",         "1.0", "vivy.core", [_L, _R], _RT, {"gpu": "preferred"}, security_level="low"),
                # ── Audio ───────────────────────────────────────────────────
                CapabilityManifest("audio.stream",       "1.0", "vivy.core", [_L, _R], _RT, {}, security_level="low"),
                CapabilityManifest("audio.stt",          "1.0", "vivy.core", [_R],     _IN, {"cpu_cores": 2}, security_level="low"),
                CapabilityManifest("audio.tts",          "1.0", "vivy.core", [_R],     _IN, {"cpu_cores": 2}, security_level="low"),
                # ── Conversation ────────────────────────────────────────────
                CapabilityManifest("conversation.chat",    "1.0", "vivy.core", [_R], _IN, {"llm": True}, security_level="low"),
                CapabilityManifest("conversation.context", "1.0", "vivy.core", [_L, _R], _IN, {}, security_level="low"),
                CapabilityManifest("conversation.history", "1.0", "vivy.core", [_R], _IN, {}, security_level="low"),
                # ── Memory ──────────────────────────────────────────────────
                CapabilityManifest("memory.read",  "1.0", "vivy.core", [_R], _IN, {}, security_level="low"),
                CapabilityManifest("memory.write", "1.0", "vivy.core", [_R], _IN, {}, security_level="standard"),
                # ── Cognition ───────────────────────────────────────────────
                CapabilityManifest("cognition.state",      "1.0", "vivy.core", [_R], _BG, {}, security_level="low"),
                CapabilityManifest("cognition.blackboard", "1.0", "vivy.core", [_R], _BG, {}, security_level="low"),
                # ── Relationship ─────────────────────────────────────────────
                CapabilityManifest("relationship.read",  "1.0", "vivy.core", [_R], _BG, {}, security_level="low"),
                CapabilityManifest("affection.read",     "1.0", "vivy.core", [_R], _BG, {}, security_level="low"),
                # ── Action ──────────────────────────────────────────────────
                CapabilityManifest("action.request", "1.0", "vivy.core", [_R], _IN, {}, security_level="standard",
                                   permissions=["action.request"]),
                CapabilityManifest("action.confirm", "1.0", "vivy.core", [_R], _IN, {}, security_level="high",
                                   permissions=["action.confirm"]),
                CapabilityManifest("action.cancel",  "1.0", "vivy.core", [_R], _IN, {}, security_level="standard"),
                CapabilityManifest("action.history", "1.0", "vivy.core", [_R], _BG, {}, security_level="low"),
                # ── Internet ────────────────────────────────────────────────
                CapabilityManifest("internet.search", "1.0", "vivy.core", [_R], _IN, {}, security_level="low"),
                CapabilityManifest("internet.status", "1.0", "vivy.core", [_R], _BG, {}, security_level="low"),
                # ── Voice / RVC ─────────────────────────────────────────────
                CapabilityManifest("voice.profiles",       "1.0", "vivy.core", [_R], _BG, {}, security_level="low"),
                CapabilityManifest("voice.train",          "1.0", "vivy.core", [_R], _BG, {"gpu": "required", "vram_mb": 8000}, security_level="high",
                                   permissions=["voice.train"]),
                CapabilityManifest("voice.training_status","1.0", "vivy.core", [_R], _BG, {}, security_level="low"),
                CapabilityManifest("voice.switch",         "1.0", "vivy.core", [_R], _IN, {}, security_level="standard"),
                # ── Evolution ───────────────────────────────────────────────
                CapabilityManifest("evolution.status", "1.0", "vivy.core", [_R], _BG, {}, security_level="low"),
                # ── Telemetry / Health ───────────────────────────────────────
                CapabilityManifest("telemetry.read", "1.0", "vivy.core", [_R], _BG, {}, security_level="low"),
                CapabilityManifest("health.read",    "1.0", "vivy.core", [_R], _BG, {}, security_level="low"),
                # ── Configuration ────────────────────────────────────────────
                CapabilityManifest("config.read",  "1.0", "vivy.core", [_R], _BG, {}, security_level="low"),
                CapabilityManifest("config.write", "1.0", "vivy.core", [_R], _BG, {}, security_level="high",
                                   permissions=["config.write"]),
                # ── Avatar ───────────────────────────────────────────────────                
                CapabilityManifest("avatar.status", "1.0", "vivy.core", [_R], _BG, {}, security_level="low"),
                CapabilityManifest("avatar.frame",  "1.0", "vivy.core", [_R], _RT, {}, security_level="low"),
                # ── Screen Sharing ───────────────────────────────────────────
                CapabilityManifest("vision.screen_capture", "1.0", "vivy.core", [_R], _IN, {}, security_level="high",
                                   permissions=["vision.screen_capture"]),
                # ── Screen ───────────────────────────────────────────────────
                CapabilityManifest("screen.capture", "1.0", "vivy.core", [_R], _IN, {}, security_level="standard"),
                CapabilityManifest("screen.frame",   "1.0", "vivy.core", [_R], _RT, {}, security_level="standard"),
                # ── GPS (node-local, contributed by edge devices) ─────────────
                CapabilityManifest("gps.read",   "1.0", "vivy.node", [_L], _RT, {"gps": True}, security_level="low"),
                CapabilityManifest("gps.update", "1.0", "vivy.node", [_L], _RT, {"gps": True}, security_level="low"),
                # ── Hub introspection ─────────────────────────────────────────
                CapabilityManifest("hub.devices", "1.0", "vivy.core", [_R], _BG, {}, security_level="low"),
                # ── Session continuity ────────────────────────────────────────
                CapabilityManifest("session.state", "1.0", "vivy.core", [_R], _IN, {}, security_level="low"),
            ]
            for _m in _manifests:
                self.router.register_manifest(_m)
            print(f"[VivyHub] Registered {len(_manifests)} capability manifests.")


            # 2. Start Transport & Discovery
            self.ws_server.start()
            if not disable_discovery:
                self.discovery.start()
                self.ble_discovery.start()
                self.udp_discovery.start()

            # 3. Trigger Smart Home discovery
            self.smart_home.discover_devices()

            print(f"[VivyHub] Ecosystem Core initialized successfully on port {port}.")

    def stop(self):
        """Gracefully shutdown hub services."""
        with self._lock:
            self._is_running = False
            self.discovery.stop()
            self.ble_discovery.stop()
            self.udp_discovery.stop()
            self.ws_server.stop()
            print("[VivyHub] Ecosystem Core shut down.")
