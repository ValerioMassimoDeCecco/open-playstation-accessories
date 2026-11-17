"""
Open PlayStation Accessories - Main Entry Point (V3.0).

Real hardware controller supervisor + local web UI.
Zero simulation, zero telemetry, zero external dependencies.

Runs on Windows (SetupAPI), macOS (IOKit) and Linux (hidraw).
"""

import argparse
import errno
import os
import signal
import sys
import threading
import time
import webbrowser
from typing import Any, Dict, List, Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.controller.hid_base import (
    enumerate_sony_devices,
    get_platform_info,
    is_supported,
)
from app.controller.dualsense import DualSenseController
from app.profiles.manager import ProfileManager
from app.web.server import create_server

APP_VERSION = "3.0"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
FAILED_DEVICE_COOLDOWN = 6.0  # seconds before retrying a HID path that failed


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

def resolve_storage_path() -> str:
    """Finds a writable location for profiles.json.

    Uses the project folder when possible, otherwise the per-user application
    data folder (needed on macOS when the app runs from a read-only location).
    """
    env_override = os.environ.get("PLAYSTATION_ACCESSORIES_PROFILES")
    if env_override:
        return os.path.abspath(os.path.expanduser(env_override))

    project_file = os.path.join(PROJECT_ROOT, "profiles.json")
    try:
        if os.path.exists(project_file):
            if os.access(project_file, os.W_OK):
                return project_file
        elif os.access(PROJECT_ROOT, os.W_OK):
            return project_file
    except OSError:
        pass

    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        base = os.path.join(home, "Library", "Application Support", "PlayStationAccessories")
    elif sys.platform.startswith("win"):
        base = os.path.join(
            os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming"),
            "PlayStationAccessories",
        )
    else:
        base = os.path.join(
            os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config"),
            "playstation-accessories",
        )

    try:
        os.makedirs(base, exist_ok=True)
    except OSError:
        return project_file
    return os.path.join(base, "profiles.json")


# --------------------------------------------------------------------------- #
# Controller supervision
# --------------------------------------------------------------------------- #

class ControllerManager:
    """Manages physical controllers with hot-plug detection (no demo mode)."""

    def __init__(self):
        self.physical_controller: Optional[DualSenseController] = None
        self._running = False
        self._lock = threading.RLock()
        self._failed_paths: Dict[str, float] = {}
        self._hint_printed_at = 0.0
        self.last_error = ""

    # -- lifecycle ---------------------------------------------------------- #

    def start(self):
        self._running = True
        threading.Thread(
            target=self._hotplug_worker, name="hotplug-worker", daemon=True
        ).start()

    def stop(self):
        self._running = False
        with self._lock:
            controller = self.physical_controller
            self.physical_controller = None
        if controller:
            try:
                controller.stop()
            except Exception:
                pass

    # -- internals ---------------------------------------------------------- #

    def _attach(self, controller: DualSenseController):
        with self._lock:
            self.physical_controller = controller

    def _detach(self, controller: Optional[DualSenseController], message: str):
        if controller is None:
            return
        with self._lock:
            if self.physical_controller is controller:
                self.physical_controller = None
        try:
            controller.stop()
        except Exception:
            pass
        print("\n[Hardware] %s" % message)

    def _pick(self, devices: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        now = time.time()
        # Drop expired cooldown entries.
        for path in [p for p, until in self._failed_paths.items() if until <= now]:
            self._failed_paths.pop(path, None)

        for device in devices:
            if device["path"] not in self._failed_paths:
                return device
        return None

    def _print_permission_hint(self):
        now = time.time()
        if now - self._hint_printed_at < 60.0:
            return
        self._hint_printed_at = now
        info = get_platform_info()
        hint = info.get("hint")
        if hint:
            print("\n[Suggerimento] %s" % hint)

    def _hotplug_worker(self):
        while self._running:
            try:
                devices = enumerate_sony_devices()
            except Exception:
                devices = []

            with self._lock:
                current = self.physical_controller

            # Controller lost / interface went silent.
            if current is not None and not current.state.get("connected", False):
                self._detach(current, "Connessione controller interrotta.")
                current = None

            if not devices:
                if current is not None:
                    self._detach(current, "Controller disconnesso.")
                self._sleep(1.0)
                continue

            target = self._pick(devices)
            if target is None:
                self._sleep(0.5)
                continue

            if current is not None and current.path == target["path"]:
                self._sleep(1.0)
                continue

            if current is not None:
                self._detach(
                    current,
                    "Cambio connessione rilevato -> %s" % target["name"],
                )

            connection = "Bluetooth" if target.get("is_bluetooth") else "USB"
            print(
                "\n[Hardware] Connessione a controller fisico (%s): %s"
                % (connection, target["name"])
            )

            controller = DualSenseController(target)
            started = False
            failure_detail = ""
            try:
                started = controller.start()
            except Exception as exc:
                failure_detail = str(exc)
                print("[Hardware] Errore durante l'apertura del controller: %s" % exc)

            if started:
                self._attach(controller)
                print(
                    "[Hardware] Comunicazione %s stabilita con successo!" % connection
                )
            else:
                detail = failure_detail
                if not detail:
                    try:
                        detail = controller.hid.last_error()  # type: ignore[attr-defined]
                    except Exception:
                        detail = ""
                self.last_error = detail or "Connessione HID non riuscita"
                try:
                    controller.stop()
                except Exception:
                    pass
                self._failed_paths[target["path"]] = time.time() + FAILED_DEVICE_COOLDOWN
                if detail:
                    print("[Hardware] Connessione non riuscita: %s" % detail)
                self._print_permission_hint()

            self._sleep(0.5)

    def _sleep(self, seconds: float):
        deadline = time.time() + seconds
        while self._running and time.time() < deadline:
            time.sleep(min(0.1, max(0.0, deadline - time.time())))

    # -- API ---------------------------------------------------------------- #

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            controller = self.physical_controller
            if controller and controller.state.get("connected", False):
                state = controller.state
                return {
                    "connected": True,
                    "model": state.get("model", "DualSense"),
                    "is_edge": state.get("is_edge", False),
                    "is_bluetooth": state.get("is_bluetooth", False),
                    "battery": state.get("battery", {}),
                    "lightbar": state.get("lightbar", {"r": 0, "g": 112, "b": 240}),
                    "platform": self._platform_payload(),
                    "data_flowing": controller.received_reports > 0,
                }

        return {
            "connected": False,
            "model": "In attesa di controller DualSense...",
            "is_edge": False,
            "is_bluetooth": False,
            "battery": {"level": 0, "charging": False, "full": False},
            "lightbar": {"r": 0, "g": 0, "b": 0},
            "platform": self._platform_payload(),
            "data_flowing": False,
        }

    def _platform_payload(self) -> Dict[str, Any]:
        info = get_platform_info()
        info["version"] = APP_VERSION
        if self.last_error and not info.get("error"):
            info["error"] = self.last_error
        return info

    def get_inputs(self) -> Dict[str, Any]:
        with self._lock:
            controller = self.physical_controller
            if controller and controller.state.get("connected", False):
                state = controller.state
                return {
                    "sticks": state.get("sticks", {}),
                    "triggers": state.get("triggers", {}),
                    "buttons": state.get("buttons", {}),
                }

        return {
            "sticks": {
                "left": {"x": 128, "y": 128, "norm_x": 0.0, "norm_y": 0.0},
                "right": {"x": 128, "y": 128, "norm_x": 0.0, "norm_y": 0.0},
            },
            "triggers": {"l2": 0, "r2": 0, "l2_norm": 0.0, "r2_norm": 0.0},
            "buttons": {},
        }

    def set_lightbar(self, r: int, g: int, b: int):
        with self._lock:
            controller = self.physical_controller
        if controller:
            try:
                controller.set_lightbar(r, g, b)
            except Exception as exc:
                self.last_error = str(exc)

    def set_rumble(self, left: int, right: int, duration_sec: float = 0.5):
        with self._lock:
            controller = self.physical_controller
        if controller:
            try:
                controller.set_rumble(left, right, duration_sec)
            except Exception as exc:
                self.last_error = str(exc)

    def set_player_led(self, player_num: int):
        with self._lock:
            controller = self.physical_controller
        if controller:
            try:
                controller.set_player_led(player_num)
            except Exception as exc:
                self.last_error = str(exc)


# --------------------------------------------------------------------------- #
# Server helpers
# --------------------------------------------------------------------------- #

def create_server_on_free_port(host, port, controller_manager, profile_manager, static_dir):
    """Binds the HTTP server, moving to the next port if the chosen one is busy."""
    last_error: Optional[OSError] = None
    for candidate in range(port, port + 20):
        try:
            return create_server(
                host, candidate, controller_manager, profile_manager, static_dir
            )
        except OSError as exc:
            last_error = exc
            if exc.errno not in (errno.EADDRINUSE, errno.EACCES):
                raise
    if last_error:
        raise last_error
    raise OSError("Nessuna porta libera disponibile")


def _banner(url: str, storage_path: str):
    info = get_platform_info()
    print("=" * 67)
    print("   PlayStation Accessories - Hardware Direct Control V%s" % APP_VERSION)
    print("=" * 67)
    print("   Sistema operativo : %s" % info["os"])
    print("   Backend HID       : %s" % info["backend"])
    print("   Profili salvati   : %s" % storage_path)
    print("=" * 67)
    print("\n[Server] Interfaccia Web avviata all'indirizzo: %s" % url)
    if not is_supported():
        print(
            "[Avviso] Sistema non supportato: l'interfaccia resta utilizzabile "
            "ma nessun controller potra essere rilevato."
        )
    elif info.get("hint"):
        print("[Info] %s" % info["hint"])
    print("[Stato] In attesa del collegamento di un controller PlayStation reale...")
    print("[Info] Premi CTRL+C per chiudere l'applicazione.\n")


def _install_signal_handlers(server):
    def _handler(_signum, _frame):
        threading.Thread(target=server.shutdown, daemon=True).start()

    for sig_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            pass


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="PlayStation Accessories - Open Source Edition (V%s)" % APP_VERSION
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="indirizzo di ascolto")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="porta HTTP")
    parser.add_argument(
        "--no-browser", action="store_true", help="non aprire il browser automaticamente"
    )
    parser.add_argument(
        "--profiles",
        default=None,
        help="percorso alternativo del file profiles.json",
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + APP_VERSION)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if args.profiles:
        os.environ["PLAYSTATION_ACCESSORIES_PROFILES"] = args.profiles

    storage_path = os.path.abspath(args.profiles) if args.profiles else resolve_storage_path()
    static_dir = os.path.join(CURRENT_DIR, "web", "static")

    profile_manager = ProfileManager(storage_path)
    controller_manager = ControllerManager()
    controller_manager.start()

    server = create_server_on_free_port(
        args.host, args.port, controller_manager, profile_manager, static_dir
    )

    host, port = server.server_address[0], server.server_address[1]
    display_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = "http://%s:%d" % (display_host, port)

    _banner(url, storage_path)

    if not args.no_browser:
        def _open():
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Timer(0.8, _open).start()

    _install_signal_handlers(server)

    exit_code = 0
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # pragma: no cover - defensive
        print("\n[Errore] %s" % exc)
        exit_code = 1
    finally:
        print("\n[Chiusura] Arresto server...")
        try:
            controller_manager.stop()
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass
        print("[Fine] Applicazione terminata.")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
