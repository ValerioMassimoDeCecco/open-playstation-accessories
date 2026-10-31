"""
Open PlayStation Accessories - Main Entry Point.
Real Hardware Controller Supervisor & Local Web UI.
Zero simulation, zero telemetria, zero external dependencies.
"""

import os
import sys
import threading
import time
import webbrowser
from typing import Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.controller.hid_windows import enumerate_sony_devices
from app.controller.dualsense import DualSenseController
from app.profiles.manager import ProfileManager
from app.web.server import create_server


class ControllerManager:
    """
    Manages physical PlayStation controller hardware with real-time hot-plug detection.
    Zero demo mode: reflects only real connected hardware.
    """

    def __init__(self):
        self.physical_controller: Optional[DualSenseController] = None
        self._running = False
        self._lock = threading.Lock()

    def start(self):
        self._running = True
        threading.Thread(target=self._hotplug_worker, daemon=True).start()

    def stop(self):
        self._running = False
        with self._lock:
            if self.physical_controller:
                self.physical_controller.stop()
                self.physical_controller = None

    def _hotplug_worker(self):
        """Continuously checks for physical DualSense / DualSense Edge hardware connection."""
        while self._running:
            devices = enumerate_sony_devices()
            with self._lock:
                # Check if current controller connection was lost or closed
                if self.physical_controller and not self.physical_controller.state.get("connected", False):
                    print("\n[Hardware] Connessione controller interrotta.")
                    self.physical_controller.stop()
                    self.physical_controller = None

                current_path = self.physical_controller.path if self.physical_controller else None

                if devices:
                    target_dev = devices[0]  # USB is prioritized over BT
                    # Reconnect if controller changed or active path changed (e.g. unplugged USB -> switch to BT)
                    if not self.physical_controller or current_path != target_dev["path"]:
                        if self.physical_controller:
                            print(f"\n[Hardware] Cambio connessione rilevato -> {target_dev['name']}")
                            self.physical_controller.stop()
                            self.physical_controller = None

                        conn_type = "Bluetooth" if target_dev.get("is_bluetooth") else "USB"
                        print(f"\n[Hardware] Connessione a controller fisico ({conn_type}): {target_dev['name']}")
                        ctrl = DualSenseController(target_dev)
                        if ctrl.start():
                            self.physical_controller = ctrl
                            print(f"[Hardware] Comunicazione {conn_type} stabilita con successo!")
                elif self.physical_controller:
                    print("\n[Hardware] Controller disconnesso.")
                    self.physical_controller.stop()
                    self.physical_controller = None

            time.sleep(1.0)

    def get_status(self):
        with self._lock:
            if self.physical_controller and self.physical_controller.state.get("connected", False):
                s = self.physical_controller.state
                return {
                    "connected": True,
                    "model": s.get("model", "DualSense"),
                    "is_edge": s.get("is_edge", False),
                    "is_bluetooth": s.get("is_bluetooth", False),
                    "battery": s.get("battery", {}),
                    "lightbar": s.get("lightbar", {"r": 0, "g": 112, "b": 240})
                }
            return {
                "connected": False,
                "model": "In attesa di controller DualSense...",
                "is_edge": False,
                "is_bluetooth": False,
                "battery": {"level": 0, "charging": False, "full": False},
                "lightbar": {"r": 0, "g": 0, "b": 0}
            }

    def get_inputs(self):
        with self._lock:
            if self.physical_controller and self.physical_controller.state.get("connected", False):
                s = self.physical_controller.state
                return {
                    "sticks": s.get("sticks", {}),
                    "triggers": s.get("triggers", {}),
                    "buttons": s.get("buttons", {})
                }
            # Neutral / resting state when disconnected
            return {
                "sticks": {
                    "left": {"x": 128, "y": 128, "norm_x": 0.0, "norm_y": 0.0},
                    "right": {"x": 128, "y": 128, "norm_x": 0.0, "norm_y": 0.0}
                },
                "triggers": {"l2": 0, "r2": 0, "l2_norm": 0.0, "r2_norm": 0.0},
                "buttons": {}
            }

    def set_lightbar(self, r: int, g: int, b: int):
        with self._lock:
            if self.physical_controller:
                self.physical_controller.set_lightbar(r, g, b)

    def set_rumble(self, left: int, right: int, duration_sec: float = 0.5):
        with self._lock:
            if self.physical_controller:
                self.physical_controller.set_rumble(left, right, duration_sec)

    def set_player_led(self, player_num: int):
        with self._lock:
            if self.physical_controller:
                self.physical_controller.set_player_led(player_num)


def main():
    print("=" * 65)
    print("   PlayStation Accessories - Hardware Direct Control")
    print("=" * 65)

    storage_path = os.path.join(PROJECT_ROOT, "profiles.json")
    static_dir = os.path.join(CURRENT_DIR, "web", "static")

    profile_manager = ProfileManager(storage_path)
    controller_manager = ControllerManager()
    controller_manager.start()

    host = "127.0.0.1"
    port = 8080

    server = create_server(host, port, controller_manager, profile_manager, static_dir)
    url = f"http://{host}:{port}"

    print(f"\n[Server] Interfaccia Web avviata all'indirizzo: {url}")
    print("[Stato] In attesa del collegamento di un controller DualSense reale...")
    print("[Info] Apertura automatica nel browser predefinito...\n")

    threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Chiusura] Arresto server...")
        controller_manager.stop()
        server.shutdown()
        print("[Fine] Applicazione terminata.")


if __name__ == "__main__":
    main()
