"""
Vivy Hub - Execution Orchestrator
Decides the optimal execution provider for a requested capability using a
resource-aware scoring algorithm. Never hardcodes providers by platform.
Fault class: Recoverable.
"""
from typing import Optional, Tuple
from hub.capability_router import CapabilityRouter
from hub.device_registry import DeviceRegistry
from hub.capability_manifest import ExecutionMode
from hub.capability_lease import LeaseManager
import time

HUB_PROTOCOL_VERSION = "1.0"

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

    def request_execution(
        self, capability_id: str, requesting_device_id: str
    ) -> Tuple[bool, Optional[str], ExecutionMode, Optional[str]]:
        """
        Requests execution of a capability.
        Returns: (success, executor_device_id, execution_mode, lease_id_if_remote)
        Uses resource-aware provider scoring — never platform-hardcoded.
        """
        manifest = self._router.discover_capability(capability_id)
        if not manifest:
            print(f"[ExecutionOrchestrator] Capability {capability_id} not found in registry.")
            return False, None, ExecutionMode.LOCAL, None

        requesting_device = self._registry.get_device(requesting_device_id)
        if not requesting_device:
            print(f"[ExecutionOrchestrator] Requesting device {requesting_device_id} not found.")
            return False, None, ExecutionMode.LOCAL, None

        # 1. Can the requesting device execute locally?
        if (ExecutionMode.LOCAL in manifest.execution_modes and
                self._router._can_device_execute(requesting_device, manifest)):
            print(f"[ExecutionOrchestrator] LOCAL execution for {capability_id} on {requesting_device_id}")
            return True, requesting_device_id, ExecutionMode.LOCAL, None

        # 2. Select best remote provider using resource-aware scoring
        if ExecutionMode.REMOTE in manifest.execution_modes:
            providers = self._router.get_providers_for_capability(capability_id)
            # Exclude requesting device (already failed local check)
            providers = [p for p in providers if p.device_id != requesting_device_id]

            if providers:
                # Score each candidate provider
                scored = [(p, self._score_provider(p, manifest)) for p in providers]
                # Filter out providers that fundamentally cannot execute (score < 0)
                scored = [x for x in scored if x[1] >= 0]
                
                if scored:
                    scored.sort(key=lambda x: x[1], reverse=True)  # Higher score = better
                    best_provider = scored[0][0]

                    lease = self._lease_manager.create_lease(
                        capability_id=capability_id,
                        requester_id=requesting_device_id,
                        executor_id=best_provider.device_id,
                    duration_sec=120.0
                )
                print(
                    f"[ExecutionOrchestrator] REMOTE execution for {capability_id} → "
                    f"{best_provider.device_id} (score={scored[0][1]:.2f})"
                )
                return True, best_provider.device_id, ExecutionMode.REMOTE, lease.lease_id

        # 3. No viable provider
        print(f"[ExecutionOrchestrator] No execution path for {capability_id} — degraded state.")
        return False, None, ExecutionMode.LOCAL, None

    def resolve_with_failover(
        self, capability_id: str, requesting_device_id: str,
        exclude_device_ids: Optional[list] = None
    ) -> Tuple[bool, Optional[str], ExecutionMode, Optional[str]]:
        """
        Like request_execution but excludes already-failed providers.
        Used for automatic failover on provider loss.
        """
        exclude_device_ids = exclude_device_ids or []
        manifest = self._router.discover_capability(capability_id)
        if not manifest:
            return False, None, ExecutionMode.LOCAL, None

        providers = self._router.get_providers_for_capability(capability_id)
        providers = [
            p for p in providers
            if p.device_id not in exclude_device_ids
            and p.device_id != requesting_device_id
            and self._is_alive(p.device_id)
        ]
        if not providers:
            print(f"[ExecutionOrchestrator] Failover: no alive providers for {capability_id}")
            return False, None, ExecutionMode.LOCAL, None

        scored = [(p, self._score_provider(p, manifest)) for p in providers]
        scored.sort(key=lambda x: x[1], reverse=True)
        best = scored[0][0]

        lease = self._lease_manager.create_lease(
            capability_id=capability_id,
            requester_id=requesting_device_id,
            executor_id=best.device_id,
            duration_sec=120.0
        )
        print(f"[ExecutionOrchestrator] Failover for {capability_id} → {best.device_id}")
        return True, best.device_id, ExecutionMode.REMOTE, lease.lease_id

    def _score_provider(self, provider, manifest) -> float:
        """
        Resource-aware provider scoring function.
        Higher is better. Never hardcodes device IDs or platform names.
        """
        score = 100.0

        # Primary host bonus — primary host has the full Vivy backend
        if getattr(provider.role, "value", "") == "primary_host":
            score += 50.0

        # GPU requirement
        req_gpu = manifest.requirements.get("gpu", "none")
        if req_gpu == "required":
            if not provider.gpu_available:
                return -999.0  # Cannot satisfy requirement
            vram_req = manifest.requirements.get("vram_mb", 0)
            if provider.vram_mb < vram_req:
                return -999.0
            score += min(provider.vram_mb / 1024.0, 20.0)  # up to 20 pts for VRAM
        elif req_gpu == "preferred":
            if provider.gpu_available:
                score += 15.0

        # RAM availability
        ram_req = manifest.requirements.get("ram_mb", 0)
        if provider.ram_mb < ram_req:
            return -999.0
        score += min(provider.ram_mb / 4096.0, 10.0)

        # CPU cores
        cpu_req = manifest.requirements.get("cpu_cores", 0)
        if provider.cpu_cores < cpu_req:
            return -999.0

        # Current load penalties — prefer idle providers
        cpu_load = getattr(provider, "current_cpu_pct", 0.0)
        gpu_load = getattr(provider, "current_gpu_pct", 0.0)
        score -= (cpu_load / 10.0)    # -10 pts at 100% CPU
        score -= (gpu_load / 20.0)    # -5 pts at 100% GPU

        # Battery penalty for mobile devices
        battery = getattr(provider, "battery_pct", 100.0)
        if battery < 20.0:
            score -= 30.0
        elif battery < 50.0:
            score -= 10.0

        # Thermal penalty
        thermal = getattr(provider, "thermal_state", "normal")
        if thermal == "hot":
            score -= 20.0
        elif thermal == "warm":
            score -= 5.0

        # Network latency penalty
        latency = getattr(provider, "network_latency_ms", 0.0)
        score -= min(latency / 10.0, 20.0)  # -2 pts per 20ms, max -20

        # LLM capability requirement
        if manifest.requirements.get("llm"):
            if not provider.local_llm:
                return -999.0
            score += 30.0

        return score

    def _is_alive(self, device_id: str, timeout_s: float = 30.0) -> bool:
        """Check if a device has sent a heartbeat recently."""
        device = self._registry.get_device(device_id)
        if not device:
            return False
        last_seen = getattr(device, "last_seen", 0.0)
        if last_seen == 0.0:
            # Device hasn't reported heartbeat — assume alive if newly registered
            return True
        return (time.time() - last_seen) < timeout_s
