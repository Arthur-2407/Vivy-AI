import socket
import threading
import time

class HubUdpDiscovery:
    _instance = None
    _lock = threading.RLock()

    def __init__(self, port: int = 8800, broadcast_port: int = 8766):
        self.port = port
        self.broadcast_port = broadcast_port
        self.running = False
        self.thread = None

    @classmethod
    def get_instance(cls) -> "HubUdpDiscovery":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _get_local_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip

    def _broadcast_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        # Determine specific broadcast addresses if needed, but 255.255.255.255 is universal
        
        print(f"[UdpDiscovery] Broadcasting Vivy Hub presence on UDP port {self.broadcast_port}")
        
        while self.running:
            try:
                ip = self._get_local_ip()
                message = f"VIVY_HUB:{ip}:{self.port}".encode('utf-8')
                sock.sendto(message, ('255.255.255.255', self.broadcast_port))
                
                # Also try to send to subnet broadcast
                parts = ip.split('.')
                if len(parts) == 4:
                    subnet_bcast = f"{parts[0]}.{parts[1]}.{parts[2]}.255"
                    sock.sendto(message, (subnet_bcast, self.broadcast_port))
                    
            except Exception as e:
                # Silently ignore broadcast failures (e.g., interface down)
                pass
                
            time.sleep(2.0)
            
        sock.close()

    def start(self):
        if self.running: return
        self.running = True
        self.thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
