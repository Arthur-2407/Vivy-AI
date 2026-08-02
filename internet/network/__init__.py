"""
Vivy AI — Network Intelligence, Embedded Tor & Smart Routing Package
====================================================================
Unified Application-Level Network Control Stack sitting above the OS:
  - TorManager: Invisible background Tor daemon startup and circuit management
  - ProxyManager: SOCKS5h encapsulation completely stopping local DNS leaks
  - RequestRouter: 4 Network Modes (Normal, Private, Hybrid, Offline) & Smart Routing
  - DuckDuckGoClient & OnionClient: Browserless internal search & automatic .onion routing
  - AddressBouncer: L2-L4 identity rotation every 45 seconds during website sessions
  - NetworkIntelligence & ProtocolLab: Real-time diagnostics & packet crafting
"""

from internet.network_manager import NetworkManager, NetworkState, get_network_manager
from internet.network.address_bouncer import AddressBouncer, get_address_bouncer
from internet.network.network_intelligence import NetworkIntelligence, get_network_intelligence
from internet.network.network_engine import NetworkEngine, get_network_engine
from internet.network.protocol_lab import ProtocolLab, get_protocol_lab, TCPStateMachine
from internet.network.tor_config import TorConfig, get_tor_config
from internet.network.tor_controller import TorController, get_tor_controller
from internet.network.tor_monitor import TorMonitor, get_tor_monitor
from internet.network.tor_identity import TorIdentity, get_tor_identity
from internet.network.tor_manager import TorManager, get_tor_manager
from internet.network.proxy_manager import ProxyManager, get_proxy_manager
from internet.network.dns_manager import DNSManager, get_dns_manager
from internet.network.connection_pool import ConnectionPool, get_connection_pool
from internet.network.network_security import NetworkSecurity, get_network_security
from internet.network.duckduckgo_client import DuckDuckGoClient, get_duckduckgo_client
from internet.network.onion_client import OnionClient, get_onion_client
from internet.network.request_router import RequestRouter, NetworkMode, get_request_router

__all__ = [
    "NetworkManager", "NetworkState", "get_network_manager",
    "AddressBouncer", "get_address_bouncer",
    "NetworkIntelligence", "get_network_intelligence",
    "NetworkEngine", "get_network_engine",
    "ProtocolLab", "get_protocol_lab", "TCPStateMachine",
    "TorConfig", "get_tor_config",
    "TorController", "get_tor_controller",
    "TorMonitor", "get_tor_monitor",
    "TorIdentity", "get_tor_identity",
    "TorManager", "get_tor_manager",
    "ProxyManager", "get_proxy_manager",
    "DNSManager", "get_dns_manager",
    "ConnectionPool", "get_connection_pool",
    "NetworkSecurity", "get_network_security",
    "DuckDuckGoClient", "get_duckduckgo_client",
    "OnionClient", "get_onion_client",
    "RequestRouter", "NetworkMode", "get_request_router"
]
