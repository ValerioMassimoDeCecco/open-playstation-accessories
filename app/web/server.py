"""
HTTP Server and REST API for PlayStation Accessories.

Direct hardware communication endpoints. Zero external dependencies, standard
library only, identical behaviour on Windows, macOS and Linux.
"""

import http.server
import json
import os
import socket
import sys
import urllib.parse
from typing import Any, Dict


class ControllerAPIHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP handler serving the web UI and JSON REST endpoints."""

    controller_manager = None
    profile_manager = None
    static_dir = ""

    server_version = "PlayStationAccessories/3.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=self.static_dir, **kwargs)

    # -- helpers ------------------------------------------------------------ #

    def _platform_info(self) -> Dict[str, Any]:
        try:
            return self.controller_manager.get_status().get("platform", {})
        except Exception:
            return {}

    def _send_json(self, data: Any, status: int = 200):
        content = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_not_found(self, message: str = "Endpoint non trovato"):
        self._send_json({"ok": False, "error": message}, status=404)

    # -- HTTP verbs --------------------------------------------------------- #

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/status":
            self._send_json(self.controller_manager.get_status())
            return
        if path == "/api/inputs":
            self._send_json(self.controller_manager.get_inputs())
            return
        if path == "/api/platform":
            self._send_json(self._platform_info())
            return
        if path == "/api/profiles":
            self._send_json({
                "profiles": self.profile_manager.get_all_profiles(),
                "slots": self.profile_manager.slots,
                "active_slot": self.profile_manager.active_slot,
            })
            return
        if path == "/api/health":
            self._send_json({"ok": True, "platform": self._platform_info()})
            return
        if path.startswith("/api/"):
            self._send_not_found()
            return

        # Static files: never cache the SPA entry point so updates apply at once.
        try:
            return super().do_GET()
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_json_body()

        if path == "/api/lightbar":
            r = self._as_int(body.get("r"), 0, 0, 255)
            g = self._as_int(body.get("g"), 112, 0, 255)
            b = self._as_int(body.get("b"), 240, 0, 255)
            self.controller_manager.set_lightbar(r, g, b)
            self._send_json({"ok": True, "lightbar": {"r": r, "g": g, "b": b}})
            return

        if path == "/api/rumble":
            left = self._as_int(body.get("left"), 128, 0, 255)
            right = self._as_int(body.get("right"), 128, 0, 255)
            try:
                duration = float(body.get("duration", 0.5))
            except (TypeError, ValueError):
                duration = 0.5
            duration = max(0.0, min(10.0, duration))
            self.controller_manager.set_rumble(left, right, duration)
            self._send_json({"ok": True})
            return

        if path == "/api/player_led":
            num = self._as_int(body.get("player_num"), 1, 1, 4)
            self.controller_manager.set_player_led(num)
            self._send_json({"ok": True, "player_num": num})
            return

        if path == "/api/profiles/save":
            saved = self.profile_manager.save_profile(body)
            self._send_json({
                "ok": True,
                "profile": saved,
                "warning": self.profile_manager.last_save_error or "",
            })
            return

        if path == "/api/profiles/delete":
            profile_id = body.get("id")
            ok = self.profile_manager.delete_profile(profile_id)
            self._send_json({"ok": bool(ok)})
            return

        if path == "/api/slots/assign":
            slot_key = body.get("slot")
            profile_id = body.get("profile_id")
            ok = self.profile_manager.assign_slot(slot_key, profile_id)
            self._send_json({"ok": bool(ok)})
            return

        if path == "/api/slots/select":
            slot_key = body.get("slot")
            active_profile = self.profile_manager.set_active_slot(slot_key)
            if active_profile and "lightbar" in active_profile:
                lightbar = active_profile["lightbar"]
                self.controller_manager.set_lightbar(
                    lightbar.get("r", 0), lightbar.get("g", 112), lightbar.get("b", 240)
                )
            self._send_json({
                "ok": True,
                "active_slot": slot_key,
                "profile": active_profile,
            })
            return

        self._send_not_found()

    # -- request helpers ---------------------------------------------------- #

    @staticmethod
    def _as_int(value: Any, default: int, minimum: int, maximum: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        return max(minimum, min(maximum, number))

    def _read_json_body(self) -> Dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", 0))
            if 0 < length <= 1_000_000:
                raw = self.rfile.read(length).decode("utf-8")
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
        except (ValueError, UnicodeDecodeError, OSError):
            pass
        return {}

    def log_message(self, format, *args):
        return


class AccessoriesHTTPServer(http.server.ThreadingHTTPServer):
    """Threaded HTTP server that survives browser disconnections."""

    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError, socket.timeout)):
            return
        super().handle_error(request, client_address)


def create_server(host: str, port: int, controller_manager, profile_manager, static_dir: str):
    ControllerAPIHandler.controller_manager = controller_manager
    ControllerAPIHandler.profile_manager = profile_manager
    ControllerAPIHandler.static_dir = os.path.abspath(static_dir)

    return AccessoriesHTTPServer((host, port), ControllerAPIHandler)
