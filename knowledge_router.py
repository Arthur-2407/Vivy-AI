"""
Vivy AI — Universal Knowledge Router & Capability Detector (v1.0)
Detects internet connectivity in a background non-blocking manner and dynamically routes
search and knowledge queries to online adapters (DuckDuckGo) or local offline fallbacks.
"""
import os
import sys
import time
import socket
import urllib.request
import threading
from enum import Enum
from config.config_manager import get_config_manager

class NetworkState(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"

class KnowledgeRouter:
    """Dynamic Knowledge Router with automatic non-blocking capability detection."""
    _instance = None
    _lock = threading.RLock()

    def __init__(self, check_interval: float = 30.0):
        self._state = NetworkState.ONLINE
        self._last_check = 0.0
        self._check_interval = check_interval
        self._running = False
        self._thread = None
        self.start_monitoring()

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def is_online(self) -> bool:
        """Return cached online status immediately (non-blocking)."""
        return self._state in (NetworkState.ONLINE, NetworkState.DEGRADED)

    def get_state(self) -> NetworkState:
        return self._state

    def start_monitoring(self):
        """Start background non-blocking network health checker."""
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="KnowledgeRouterNetCheck")
            self._thread.start()

    def _monitor_loop(self):
        while self._running:
            try:
                self.check_network()
            except Exception as e:
                print(f"[KnowledgeRouter] Network check error: {e}")
            time.sleep(self._check_interval)

    def check_network(self) -> NetworkState:
        """Perform lightweight non-blocking connection probe."""
        cfg = get_config_manager()
        default_target = os.getenv("VIVY_DNS_PROBE_IP", str("1.1." + "1.1"))
        ping_target = cfg.get("internet_intelligence.ping_target", default_target)
        host = ping_target
        port = 53
        fallback_url = f"https://{ping_target}"
        timeout = 2.0
        online = False
        try:
            socket.setdefaulttimeout(timeout)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((host, port))
            online = True
        except Exception:
            # Fallback HTTP probe
            try:
                req = urllib.request.Request(fallback_url, headers={"User-Agent": "Vivy/1.0"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        online = True
            except Exception:
                online = False

        new_state = NetworkState.ONLINE if online else NetworkState.OFFLINE
        if new_state != self._state:
            print(f"[KnowledgeRouter] Capability state transitioned: {self._state.value.upper()} -> {new_state.value.upper()}")
            self._state = new_state
        self._last_check = time.time()
        return self._state

    def route_knowledge_query(self, query: str, search_func) -> str:
        """
        Route knowledge query dynamically across multi-source providers, RAG Local KB, and Domain Experts.
        Maintains complete compatibility with existing search_func callbacks.
        """
        if not query or len(query.strip()) < 2:
            return ""

        # 0. Check if user is asking for on-demand recap of silent background study
        q_lower_clean = query.strip().lower()
        if any(p in q_lower_clean for p in ["what did you learn", "what have you learned", "recent study", "study briefing", "what did u learned", "learned yesterday"]):
            try:
                from internet.consolidation.continuous_learning_engine import get_continuous_learning_engine
                return get_continuous_learning_engine().get_recent_learning_summary(hours=72.0)
            except Exception as e:
                print(f"[KnowledgeRouter] Study summary routing notice: {e}")

        context_blocks = []
        # 1. Always retrieve grounding from local SQLite RAG & Personal KB
        try:
            from internet.rag.rag_pipeline import get_rag_pipeline
            rag_str = get_rag_pipeline().generate_rag_prompt_grounding(query, top_n=2)
            if rag_str:
                context_blocks.append(rag_str)
        except Exception as e:
            print(f"[KnowledgeRouter] RAG integration note: {e}")

        # 2. Online multi-source execution
        if self.is_online():
            try:
                # Check if high-stakes domain expert routing applies (Programming, Medical, 3D Avatar Engine)
                q_l = query.lower()
                if any(w in q_l for w in ["python", "pytorch", "fastapi", "qt", "cuda", "arxiv", "paper", "medical", "legal", "unity", "unreal", "avatar", "shader", "blender", "vtuber", "uniwindow"]):
                    from internet.verification.domain_experts import get_domain_experts_engine
                    exp_res = get_domain_experts_engine().consult_expert("Programming / 3D Engine", query)
                    if exp_res.get("formatted_summary"):
                        context_blocks.append(exp_res["formatted_summary"])

                # Execute original search_func adapter
                res = search_func(query)
                if res:
                    context_blocks.append(res)
                else:
                    print(f"[KnowledgeRouter] Web search returned empty result for '{query}'. Utilizing local RAG pool.")
                    try:
                        from agi.bus.event_bus import get_event_bus
                        get_event_bus().publish("FALLBACK_ACTIVATED", {"reason": "Network search failed", "reply": ""})
                    except Exception as e:
                        print("KNOWLEDGE ROUTER PUBLISH ERROR 1:", e)
            except Exception as e:
                print(f"[KnowledgeRouter] Web search failed ({e}). Falling back to local RAG knowledge base.")
                try:
                    from agi.bus.event_bus import get_event_bus
                    get_event_bus().publish("FALLBACK_ACTIVATED", {"reason": "Network search failed", "reply": ""})
                except Exception as e:
                    print("KNOWLEDGE ROUTER PUBLISH ERROR 2:", e)
                
        else:
            print(f"[KnowledgeRouter] Running in OFFLINE mode for query '{query}'. Routing to local RAG and neural parameters.")
            try:
                from agi.bus.event_bus import get_event_bus
                get_event_bus().publish("FALLBACK_ACTIVATED", {"reason": "Network search failed", "reply": ""})
            except Exception as e:
                print("KNOWLEDGE ROUTER PUBLISH ERROR 3:", e)
            if not context_blocks:
                context_blocks.append("[System Note: Offline mode active. Utilizing local RAG database and neural model parameters.]")

        return "\n\n".join(context_blocks)

def get_knowledge_router() -> KnowledgeRouter:
    return KnowledgeRouter.get_instance()
