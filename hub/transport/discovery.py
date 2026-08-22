"""
Vivy Hub - Discovery Service (mDNS)
Broadcasts the Primary Hub's presence on the local network.
"""
from zeroconf import ServiceInfo, Zeroconf
import socket
import threading
import time

class HubDiscovery:
    _instance = None
    _lock = threading.RLock()

    def __init__(self, port: int = 8765):
        self.port = port
        self.zeroconf = Zeroconf()
        self.info = None

    @classmethod
    def get_instance(cls) -> "HubDiscovery":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def start(self):
        desc = {'service': 'vivy_hub', 'version': '1.0'}
        
        # Get local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
            
        self.info = ServiceInfo(
            "_vivy._tcp.local.",
            "Vivy Primary Hub._vivy._tcp.local.",
            addresses=[socket.inet_aton(ip)],
            port=self.port,
            properties=desc,
            server="vivy-hub.local.",
        )
        self.zeroconf.register_service(self.info)
        print(f"[HubDiscovery] Broadcasting Vivy Hub at {ip}:{self.port} via mDNS")

    def stop(self):
        if self.info:
            try:
                self.zeroconf.unregister_service(self.info)
            except Exception:
                pass
        self.zeroconf.close()
