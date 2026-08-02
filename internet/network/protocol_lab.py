"""
Vivy AI — Protocol Understanding Lab & Packet Crafting Sandbox
============================================================
Enables Vivy to incrementally develop a deep understanding of networking without OS stack replacement:
  - **Packet Parser & Analyzer**: Unpacks hexadecimal and binary buffers into Ethernet, IPv4, TCP, and UDP structures.
  - **Packet Constructor**: Builds protocol packets via Scapy or native Python `struct` byte serialization.
  - **Custom DNS Client**: Low-level UDP socket DNS resolution engine.
  - **Custom HTTP Client**: Low-level TCP socket HTTP request/response line parser.
  - **TCP State-Machine Sandbox**: Simulates complete TCP handshake and termination transitions in an isolated lab environment.
"""

import time
import socket
import struct
import binascii
import threading
from typing import Dict, List, Any, Optional, Tuple

try:
    from scapy.all import Ether, IP, TCP, UDP, raw
    HAS_SCAPY = True
except Exception:
    HAS_SCAPY = False

class TCPStateMachine:
    """Isolated finite state machine simulating TCP lifecycle and edge cases."""
    VALID_STATES = ["CLOSED", "SYN_SENT", "SYN_RCVD", "ESTABLISHED", "FIN_WAIT_1", "FIN_WAIT_2", "CLOSE_WAIT", "CLOSING", "LAST_ACK", "TIME_WAIT"]

    def __init__(self, name: str = "Vivy-TCP-Sim"):
        self.name = name
        self.state = "CLOSED"
        self.seq_num = 1000
        self.ack_num = 0
        self.history: List[str] = ["CLOSED"]

    def transition(self, event: str) -> Dict[str, Any]:
        """Process an event (SEND_SYN, RCV_SYN_ACK, SEND_ACK, SEND_FIN, RCV_ACK, RCV_FIN) and transition state."""
        old_state = self.state
        msg = f"Processed event '{event}' in state {self.state}"

        if self.state == "CLOSED" and event == "SEND_SYN":
            self.state = "SYN_SENT"
            self.seq_num += 1
            msg = "Active Open: Sent SYN packet. Transitioning to SYN_SENT."
        elif self.state == "SYN_SENT" and event == "RCV_SYN_ACK":
            self.state = "ESTABLISHED"
            self.ack_num = 5001
            msg = "Received SYN-ACK from peer. Sent final ACK. Transitioning to ESTABLISHED (Connection Open)."
        elif self.state == "ESTABLISHED" and event == "SEND_FIN":
            self.state = "FIN_WAIT_1"
            self.seq_num += 1
            msg = "Initiating active close: Sent FIN. Transitioning to FIN_WAIT_1."
        elif self.state == "FIN_WAIT_1" and event == "RCV_ACK":
            self.state = "FIN_WAIT_2"
            msg = "Received ACK of FIN from peer. Transitioning to FIN_WAIT_2."
        elif self.state == "FIN_WAIT_2" and event == "RCV_FIN":
            self.state = "TIME_WAIT"
            self.ack_num += 1
            msg = "Received peer FIN. Sent ACK. Transitioning to TIME_WAIT."
        elif self.state == "TIME_WAIT" and event == "TIMEOUT_2MSL":
            self.state = "CLOSED"
            msg = "2MSL timer expired. Connection fully CLOSED."
        elif self.state == "ESTABLISHED" and event == "RCV_FIN":
            self.state = "CLOSE_WAIT"
            self.ack_num += 1
            msg = "Passive close: Received peer FIN. Sent ACK. Transitioning to CLOSE_WAIT."
        elif self.state == "CLOSE_WAIT" and event == "SEND_FIN":
            self.state = "LAST_ACK"
            self.seq_num += 1
            msg = "Sent application FIN. Transitioning to LAST_ACK."
        elif self.state == "LAST_ACK" and event == "RCV_ACK":
            self.state = "CLOSED"
            msg = "Received final ACK. Passive close complete. CLOSED."
        else:
            msg = f"Invalid or ignored transition event '{event}' in current state '{self.state}'."

        if old_state != self.state:
            self.history.append(self.state)

        return {
            "previous_state": old_state,
            "current_state": self.state,
            "event": event,
            "seq_num": self.seq_num,
            "ack_num": self.ack_num,
            "message": msg,
            "history": self.history
        }


class ProtocolLab:
    """Vivy AI Protocol Understanding & Packet Crafting Laboratory."""
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "ProtocolLab":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self.tcp_sandbox = TCPStateMachine("Vivy-Isolated-Lab")

    def parse_packet_bytes(self, hex_string_or_bytes: Any) -> Dict[str, Any]:
        """
        Dissects hexadecimal strings or byte streams into structured protocol layers:
        Ethernet (14 bytes) -> IPv4 (20 bytes) -> Transport (TCP/UDP).
        """
        result = {"status": "success", "layers": []}
        try:
            if isinstance(hex_string_or_bytes, str):
                data = binascii.unhexlify(hex_string_or_bytes.replace(" ", "").replace(":", ""))
            else:
                data = hex_string_or_bytes

            if len(data) >= 14:
                dst_mac = binascii.hexlify(data[0:6]).decode().upper()
                src_mac = binascii.hexlify(data[6:12]).decode().upper()
                eth_type = struct.unpack("!H", data[12:14])[0]
                dst_mac_str = ":".join(dst_mac[i:i+2] for i in range(0, 12, 2))
                src_mac_str = ":".join(src_mac[i:i+2] for i in range(0, 12, 2))
                result["layers"].append({
                    "layer": "Layer 2 Ethernet",
                    "dst_mac": dst_mac_str,
                    "src_mac": src_mac_str,
                    "ether_type": hex(eth_type)
                })

                # Check if IPv4 (0x0800) and enough bytes for IP header
                if eth_type == 0x0800 and len(data) >= 34:
                    ip_header = data[14:34]
                    iph = struct.unpack("!BBHHHBBH4s4s", ip_header)
                    version_ihl = iph[0]
                    ttl = iph[5]
                    protocol = iph[6]
                    src_ip = socket.inet_ntoa(iph[8])
                    dst_ip = socket.inet_ntoa(iph[9])
                    proto_name = "TCP" if protocol == 6 else ("UDP" if protocol == 17 else f"PROTO_{protocol}")
                    
                    result["layers"].append({
                        "layer": "Layer 3 IPv4",
                        "src_ip": src_ip,
                        "dst_ip": dst_ip,
                        "ttl": ttl,
                        "protocol": proto_name
                    })

                    # Parse Transport Layer
                    if protocol == 6 and len(data) >= 54:
                        tcp_header = data[34:54]
                        tcph = struct.unpack("!HHLLBBHHH", tcp_header)
                        sport, dport, seq, ack, offset_reserved, tcp_flags = tcph[0], tcph[1], tcph[2], tcph[3], tcph[4], tcph[5]
                        result["layers"].append({
                            "layer": "Layer 4 TCP",
                            "src_port": sport,
                            "dst_port": dport,
                            "sequence": seq,
                            "acknowledgement": ack,
                            "flags": hex(tcp_flags)
                        })
                    elif protocol == 17 and len(data) >= 42:
                        udp_header = data[34:42]
                        udph = struct.unpack("!HHHH", udp_header)
                        result["layers"].append({
                            "layer": "Layer 4 UDP",
                            "src_port": udph[0],
                            "dst_port": udph[1],
                            "length": udph[2],
                            "checksum": hex(udph[3])
                        })
            else:
                result["status"] = "buffer_too_short"
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
        return result

    def craft_custom_packet(self, src_mac: str, dst_mac: str, src_ip: str, dst_ip: str, proto: str = "TCP", dport: int = 80, payload: str = "VIVY") -> Dict[str, Any]:
        """
        Constructs a complete raw packet buffer using Scapy or fallback native Python struct packing.
        """
        report = {"protocol": proto, "src_ip": src_ip, "dst_ip": dst_ip, "dport": dport}
        if HAS_SCAPY:
            try:
                p = Ether(src=src_mac, dst=dst_mac) / IP(src=src_ip, dst=dst_ip)
                if proto == "TCP":
                    p = p / TCP(dport=dport, flags="S") / payload.encode()
                else:
                    p = p / UDP(dport=dport) / payload.encode()
                raw_bytes = raw(p)
                report["hex_dump"] = binascii.hexlify(raw_bytes).decode().upper()
                report["engine"] = "Scapy Native Assembler"
                report["byte_length"] = len(raw_bytes)
                return report
            except Exception:
                pass

        # Fallback Python struct assembler
        try:
            # Fake Ether + IP + UDP minimal byte layout
            eth_hdr = struct.pack("!6s6sH", b'\x00'*6, b'\xaa'*6, 0x0800)
            ip_hdr = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 28 + len(payload), 54321, 0, 64, 17 if proto == "UDP" else 6, 0, socket.inet_aton(src_ip), socket.inet_aton(dst_ip))
            l4_hdr = struct.pack("!HHHH", 50123, dport, 8 + len(payload), 0) if proto == "UDP" else struct.pack("!HHLLBBHHH", 50123, dport, 1000, 0, 0x50, 0x02, 8192, 0, 0)
            pkt = eth_hdr + ip_hdr + l4_hdr + payload.encode(errors="ignore")
            report["hex_dump"] = binascii.hexlify(pkt).decode().upper()
            report["engine"] = "Python Struct Low-Level Assembler"
            report["byte_length"] = len(pkt)
        except Exception as err:
            report["error"] = str(err)
        return report

    def custom_dns_resolve(self, domain: str, dns_server: str = "1.1.1.1", timeout: float = 2.0) -> Dict[str, Any]:
        """
        Implements a standalone custom DNS UDP client without relying on OS system resolving.
        Constructs RFC 1035 UDP query bytes and extracts resolved A records.
        """
        t0 = time.time()
        result = {"domain": domain, "server": dns_server, "status": "failed", "resolved_ips": []}
        try:
            # Construct transaction ID + DNS flags for standard recursion query
            tx_id = random_id = 0x5678
            flags = 0x0100 # Standard query, recursion desired
            header = struct.pack("!HHHHHH", tx_id, flags, 1, 0, 0, 0)
            
            # Format hostname into DNS QNAME layout (e.g. 3'www'7'example'3'com'0)
            qname_parts = []
            for label in domain.strip(".").split("."):
                qname_parts.append(struct.pack("!B", len(label)))
                qname_parts.append(label.encode("utf-8"))
            qname = b"".join(qname_parts) + b"\x00"
            question = qname + struct.pack("!HH", 1, 1) # Type A, Class IN
            query = header + question

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            sock.sendto(query, (dns_server, 53))
            resp, _ = sock.recvfrom(512)
            sock.close()

            latency_ms = (time.time() - t0) * 1000.0
            result["latency_ms"] = round(latency_ms, 2)

            # Simple answer verification and IP string fallback parsing
            if len(resp) > len(query) and resp[0:2] == struct.pack("!H", tx_id):
                result["status"] = "success"
                # If we got response bytes ending with IP A record format (last 4 bytes)
                if len(resp) >= 4:
                    result["resolved_ips"].append(socket.inet_ntoa(resp[-4:]))
        except Exception as e:
            result["error"] = str(e)
            result["latency_ms"] = round((time.time() - t0) * 1000.0, 2)
            # Fallback to gethostbyname if network firewall blocked custom UDP DNS probe
            try:
                ip = socket.gethostbyname(domain)
                result["resolved_ips"].append(ip)
                result["status"] = "success_via_fallback_resolver"
            except Exception:
                pass
        return result

    def custom_http_probe(self, host: str, path: str = "/", port: int = 80, timeout: float = 2.0) -> Dict[str, Any]:
        """
        Implements a low-level socket HTTP client sending raw protocol request bytes.
        """
        t0 = time.time()
        res = {"host": host, "port": port, "status_code": None, "headers": {}}
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((host, port))
            req = f"HEAD {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: VivyNet-ProtocolLab/1.0\r\nConnection: close\r\n\r\n"
            s.sendall(req.encode("utf-8"))
            
            data = s.recv(1024).decode("utf-8", errors="ignore")
            s.close()
            latency = (time.time() - t0) * 1000.0
            res["latency_ms"] = round(latency, 2)
            
            lines = data.split("\r\n")
            if lines and lines[0].startswith("HTTP/"):
                parts = lines[0].split(" ")
                if len(parts) >= 2 and parts[1].isdigit():
                    res["status_code"] = int(parts[1])
                res["status_line"] = lines[0]
            for l in lines[1:]:
                if ":" in l:
                    k, v = l.split(":", 1)
                    res["headers"][k.strip().lower()] = v.strip()
        except Exception as err:
            res["error"] = str(err)
            res["latency_ms"] = round((time.time() - t0) * 1000.0, 2)
        return res

    def simulate_tcp_handshake(self) -> List[Dict[str, Any]]:
        """Run a complete TCP 3-way handshake and active tear-down experiment in the sandbox."""
        sim = TCPStateMachine("Vivy-Experiment")
        logs = []
        logs.append(sim.transition("SEND_SYN"))      # Active open -> SYN_SENT
        logs.append(sim.transition("RCV_SYN_ACK"))   # Peer replies -> ESTABLISHED
        logs.append(sim.transition("SEND_FIN"))      # Teardown start -> FIN_WAIT_1
        logs.append(sim.transition("RCV_ACK"))       # Peer acknowledges -> FIN_WAIT_2
        logs.append(sim.transition("RCV_FIN"))       # Peer sends FIN -> TIME_WAIT
        logs.append(sim.transition("TIMEOUT_2MSL"))  # Timer expires -> CLOSED
        return logs

_global_lab = None
def get_protocol_lab() -> ProtocolLab:
    global _global_lab
    if _global_lab is None:
        _global_lab = ProtocolLab.get_instance()
    return _global_lab
