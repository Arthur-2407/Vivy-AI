import asyncio
import socket
import threading
import time

try:
    from winrt.windows.devices.bluetooth.advertisement import (
        BluetoothLEAdvertisementPublisher,
        BluetoothLEAdvertisement,
        BluetoothLEAdvertisementDataSection,
        BluetoothLEAdvertisementPublisherStatus
    )
    from winrt.windows.storage.streams import DataWriter
    WINRT_AVAILABLE = True
except ImportError:
    WINRT_AVAILABLE = False


class HubBleDiscovery:
    _instance = None
    _lock = threading.RLock()

    def __init__(self, port: int = 8800):
        self.port = port
        self.publisher = None

    @classmethod
    def get_instance(cls) -> "HubBleDiscovery":
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

    def start(self):
        if not WINRT_AVAILABLE:
            print("[BleDiscovery] WinRT not available. BLE advertising skipped.")
            return

        try:
            ip = self._get_local_ip()
            adv_name = f"VivyHub_{ip}_{self.port}"
            
            # Using WinRT to advertise
            adv = BluetoothLEAdvertisement()
            adv.local_name = adv_name[:29]  # BLE name limit is usually 29 bytes
            
            # Allow clients to connect (even though we don't handle GATT connections here, 
            # this makes the advertisement active and visible to most Android scanners)
            # adv.flags = 0x06 # General discoverable, BR/EDR not supported
            
            self.publisher = BluetoothLEAdvertisementPublisher(adv)
            self.publisher.start()
            print(f"[BleDiscovery] Broadcasting Vivy Hub via BLE Advertisement: {adv_name}")
        except Exception as e:
            print(f"[BleDiscovery] Failed to start BLE advertisement: {e}")

    def stop(self):
        if self.publisher:
            try:
                self.publisher.stop()
                print("[BleDiscovery] Stopped BLE advertisement.")
            except Exception:
                pass
            self.publisher = None
