"""
Vivy Hub - UDP Discovery Service

Broadcasts the Hub's presence on ALL active local network interfaces,
including Wi-Fi, Ethernet, and Bluetooth PAN adapters.

This is critical for multi-transport operation: when an Android device
is connected via Bluetooth PAN, it uses a different subnet
(e.g. 169.254.x.x or a BT PAN subnet) and the Hub must broadcast
on that interface too, not just the primary Wi-Fi adapter.

The broadcast message format is: VIVY_HUB:<IP>:<PORT>
"""
import socket
import threading
import time
import ipaddress


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

    def _get_all_broadcast_addresses(self) -> list:
        """
        Enumerate all active network interfaces and return their broadcast addresses.
        Includes Wi-Fi, Ethernet, Bluetooth PAN, and any other IP interfaces.
        Excludes loopback.

        Returns a list of (local_ip, broadcast_addr) tuples.
        """
        results = []
        try:
            import netifaces  # optional: provides per-interface info
            for iface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(iface)
                if netifaces.AF_INET in addrs:
                    for addr_info in addrs[netifaces.AF_INET]:
                        ip = addr_info.get('addr', '')
                        netmask = addr_info.get('netmask', '')
                        if not ip or ip.startswith('127.'):
                            continue
                        broadcast = addr_info.get('broadcast', '')
                        if not broadcast:
                            # Compute broadcast from IP + netmask
                            try:
                                net = ipaddress.IPv4Network(f"{ip}/{netmask}", strict=False)
                                broadcast = str(net.broadcast_address)
                            except Exception:
                                broadcast = '255.255.255.255'
                        results.append((ip, broadcast))
        except ImportError:
            # netifaces not available — fall back to socket-based primary IP detection
            results = self._get_broadcast_fallback()
        except Exception as e:
            print(f"[UdpDiscovery] Interface enumeration error: {e}")
            results = self._get_broadcast_fallback()

        # Always include the universal broadcast as a fallback
        if not any(b == '255.255.255.255' for _, b in results):
            primary = self._get_primary_ip()
            if primary:
                results.append((primary, '255.255.255.255'))

        return results

    def _get_broadcast_fallback(self) -> list:
        """Fallback: detect primary IP and compute subnet broadcast."""
        primary = self._get_primary_ip()
        if not primary:
            return []
        results = [(primary, '255.255.255.255')]
        # Also compute subnet broadcast for the /24 assumption
        parts = primary.split('.')
        if len(parts) == 4:
            subnet_bcast = f"{parts[0]}.{parts[1]}.{parts[2]}.255"
            results.append((primary, subnet_bcast))
        return results

    def _get_primary_ip(self) -> str:
        """Get the primary outbound IP address."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip if not ip.startswith('127.') else ''

    def _broadcast_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        print(f"[UdpDiscovery] Broadcasting Hub presence on port {self.broadcast_port} (all interfaces)")

        while self.running:
            try:
                broadcast_targets = self._get_all_broadcast_addresses()
                for local_ip, bcast_addr in broadcast_targets:
                    message = f"VIVY_HUB:{local_ip}:{self.port}".encode('utf-8')
                    try:
                        sock.sendto(message, (bcast_addr, self.broadcast_port))
                    except Exception:
                        pass  # Skip failed interfaces silently
            except Exception as e:
                print(f"[UdpDiscovery] Broadcast loop error: {e}")

            time.sleep(2.0)

        sock.close()

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
