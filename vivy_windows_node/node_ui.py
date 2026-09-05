import tkinter as tk
from tkinter import ttk
import threading
import asyncio
import time

class VivyNodeUI:
    def __init__(self, root, agent):
        self.root = root
        self.agent = agent
        self.root.title(f"Vivy Node — {agent.node_id}")
        self.root.geometry("380x320")
        self.root.resizable(False, False)
        
        # Configure style
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TFrame", background="#1e1e1e")
        style.configure("TLabel", background="#1e1e1e", foreground="#ffffff", font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("TButton", font=("Segoe UI", 10))
        
        self.root.configure(bg="#1e1e1e")
        
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        ttk.Label(main_frame, text="Vivy Edge Node", style="Header.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        # Status Section
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(status_frame, text="Status:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.lbl_status = ttk.Label(status_frame, text="Initializing...", style="Status.TLabel")
        self.lbl_status.grid(row=0, column=1, sticky=tk.W, padx=10, pady=2)
        
        ttk.Label(status_frame, text="Hub:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.lbl_hub = ttk.Label(status_frame, text=f"{agent.hub_host}:{agent.hub_port}")
        self.lbl_hub.grid(row=1, column=1, sticky=tk.W, padx=10, pady=2)
        
        ttk.Label(status_frame, text="Latency:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.lbl_latency = ttk.Label(status_frame, text="0.0 ms")
        self.lbl_latency.grid(row=2, column=1, sticky=tk.W, padx=10, pady=2)
        
        # Capabilities Section
        ttk.Label(main_frame, text="Local Capabilities:", style="Header.TLabel").pack(anchor=tk.W, pady=(10, 5))
        
        caps_frame = ttk.Frame(main_frame)
        caps_frame.pack(fill=tk.X, pady=(0, 15))
        
        hw = agent._hardware
        caps = [
            ("Camera", hw.get("camera_available", False)),
            ("Microphone", hw.get("mic_available", False)),
            ("Speaker", hw.get("speaker_available", False)),
            ("GPU Acceleration", hw.get("gpu_available", False))
        ]
        
        for i, (name, available) in enumerate(caps):
            icon = "✓" if available else "✗"
            color = "#4ade80" if available else "#f87171"
            lbl = tk.Label(caps_frame, text=f"{icon} {name}", bg="#1e1e1e", fg=color, font=("Segoe UI", 9))
            lbl.grid(row=i//2, column=i%2, sticky=tk.W, padx=(0, 20), pady=2)
            
        # Controls
        controls_frame = ttk.Frame(main_frame)
        controls_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))
        
        self.btn_reconnect = ttk.Button(controls_frame, text="Reconnect", command=self.force_reconnect)
        self.btn_reconnect.pack(side=tk.LEFT, padx=(0, 10))
        
        self.btn_disconnect = ttk.Button(controls_frame, text="Disconnect", command=self.disconnect)
        self.btn_disconnect.pack(side=tk.LEFT)
        
        # Start update loop
        self.update_status()
        
    def force_reconnect(self):
        if self.agent._ws:
            # Closing the WS will trigger the reconnect loop in agent.run()
            asyncio.run_coroutine_threadsafe(self.agent._ws.close(), self.agent._loop)
            
    def disconnect(self):
        self.agent._running = False
        if self.agent._ws:
            asyncio.run_coroutine_threadsafe(self.agent._ws.close(), self.agent._loop)
        self.root.quit()
        
    def update_status(self):
        # Update connection status
        status = self.agent._status
        self.lbl_status.config(text=status.upper())
        if status == "connected":
            self.lbl_status.config(foreground="#4ade80")
        elif status in ("disconnected", "error"):
            self.lbl_status.config(foreground="#f87171")
        else:
            self.lbl_status.config(foreground="#fbbf24")
            
        # Update latency
        self.lbl_latency.config(text=f"{self.agent._latency_ms} ms")
        
        # Schedule next update
        self.root.after(1000, self.update_status)

def run_ui(agent):
    root = tk.Tk()
    app = VivyNodeUI(root, agent)
    # Handle window close
    root.protocol("WM_DELETE_WINDOW", app.disconnect)
    root.mainloop()
