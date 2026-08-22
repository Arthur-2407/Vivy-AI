"""
Vivy Hub - Main Ecosystem Manager
Top-level orchestrator for the Vivy capability federation.
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

    def start(self, disable_discovery=False, port=8766):
        """Start all hub background services and event listeners."""
        with self._lock:
            if self._is_running:
                return
            self._is_running = True
            
            self.discovery.port = port
            self.ws_server.port = port
            
            # 1. Initialize self as Primary Host in the registry
            from hub.device_identity import DeviceProfile, DeviceRole, TrustLevel
            primary_profile = DeviceProfile(
                device_id="vivy_primary_host",
                device_type="server",
                role=DeviceRole.PRIMARY_HOST,
                trust_level=TrustLevel.FULLY_AUTHORIZED,
                cpu_cores=8,
                gpu_available=True,
                ram_mb=16384,
                vram_mb=8192,
                local_llm=True,
                local_vision=True,
                local_tts=True
            )
            self.registry.register_device(primary_profile)
            
            # 2. Start Transport & Discovery
            self.ws_server.start()
            if not disable_discovery:
                self.discovery.start()
            
            # 3. Trigger Smart Home discovery
            self.smart_home.discover_devices()
            
            print("[VivyHub] Ecosystem Core initialized successfully.")
            
    def stop(self):
        """Gracefully shutdown hub services."""
        with self._lock:
            self._is_running = False
            self.discovery.stop()
            self.ws_server.stop()
            print("[VivyHub] Ecosystem Core shut down.")
