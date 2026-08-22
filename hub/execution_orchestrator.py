"""
Vivy Hub - Execution Orchestrator
Decides the optimal execution mode (Local, Remote, Hybrid) for a requested capability.
"""
from typing import Optional, Tuple
from hub.capability_router import CapabilityRouter
from hub.device_registry import DeviceRegistry
from hub.capability_manifest import ExecutionMode
from hub.capability_lease import LeaseManager

class ExecutionOrchestrator:
    _instance = None

    def __init__(self):
        self._router = CapabilityRouter.get_instance()
        self._registry = DeviceRegistry.get_instance()
        self._lease_manager = LeaseManager.get_instance()
        
    @classmethod
    def get_instance(cls) -> "ExecutionOrchestrator":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def request_execution(self, capability_id: str, requesting_device_id: str) -> Tuple[bool, Optional[str], ExecutionMode, Optional[str]]:
        """
        Requests execution of a capability.
        Returns: (success, executor_device_id, execution_mode, lease_id_if_remote)
        """
        manifest = self._router.discover_capability(capability_id)
        if not manifest:
            print(f"[ExecutionOrchestrator] Capability {capability_id} not found.")
            return False, None, ExecutionMode.LOCAL, None
            
        requesting_device = self._registry.get_device(requesting_device_id)
        if not requesting_device:
            print(f"[ExecutionOrchestrator] Requesting device {requesting_device_id} not found.")
            return False, None, ExecutionMode.LOCAL, None
            
        # 1. Can the requesting device do it locally?
        if ExecutionMode.LOCAL in manifest.execution_modes and self._router._can_device_execute(requesting_device, manifest):
            print(f"[ExecutionOrchestrator] Decided LOCAL execution for {capability_id} on {requesting_device_id}")
            return True, requesting_device_id, ExecutionMode.LOCAL, None
            
        # 2. Cannot do locally, attempt delegation (Remote)
        if ExecutionMode.REMOTE in manifest.execution_modes:
            providers = self._router.get_providers_for_capability(capability_id)
            # Exclude the requesting device since we already know it can't execute it
            providers = [p for p in providers if p.device_id != requesting_device_id]
            
            if providers:
                # Rank providers (Primary Host preferred)
                providers.sort(key=lambda p: 0 if p.role.value == "primary_host" else 1)
                selected_provider = providers[0]
                
                # Issue a lease
                lease = self._lease_manager.create_lease(
                    capability_id=capability_id,
                    requester_id=requesting_device_id,
                    executor_id=selected_provider.device_id,
                    duration_sec=120.0
                )
                print(f"[ExecutionOrchestrator] Decided REMOTE execution for {capability_id}. Delegating to {selected_provider.device_id}")
                return True, selected_provider.device_id, ExecutionMode.REMOTE, lease.lease_id
                
        # 3. No available provider
        print(f"[ExecutionOrchestrator] Failed to find execution path for {capability_id}")
        return False, None, ExecutionMode.LOCAL, None
