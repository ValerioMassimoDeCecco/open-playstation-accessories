"""
HTTP Server and REST API for PlayStation Accessories.
Direct hardware communication endpoints.
Zero external dependencies, uses Python standard library.
"""

import http.server
import json
import os
import urllib.parse
from typing import Any, Dict


class ControllerAPIHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP handler serving the web UI and JSON REST endpoints."""

    controller_manager = None
    profile_manager = None
    static_dir = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=self.static_dir, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/status":
            self._send_json(self.controller_manager.get_status())
            return
        elif path == "/api/inputs":
            self._send_json(self.controller_manager.get_inputs())
            return
        elif path == "/api/profiles":
            data = {
                "profiles": self.profile_manager.get_all_profiles(),
                "slots": self.profile_manager.slots,
                "active_slot": self.profile_manager.active_slot
            }
            self._send_json(data)
            return

        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_json_body()

        if path == "/api/lightbar":
            r = body.get("r", 0)
            g = body.get("g", 112)
            b = body.get("b", 240)
            self.controller_manager.set_lightbar(r, g, b)
            self._send_json({"ok": True, "lightbar": {"r": r, "g": g, "b": b}})
            return

        elif path == "/api/rumble":
            left = body.get("left", 128)
            right = body.get("right", 128)
            duration = body.get("duration", 0.5)
            self.controller_manager.set_rumble(left, right, duration)
            self._send_json({"ok": True})
            return

        elif path == "/api/player_led":
            num = body.get("player_num", 1)
            self.controller_manager.set_player_led(num)
            self._send_json({"ok": True})
            return

        elif path == "/api/profiles/save":
            saved = self.profile_manager.save_profile(body)
            self._send_json({"ok": True, "profile": saved})
            return

        elif path == "/api/profiles/delete":
            pid = body.get("id")
            ok = self.profile_manager.delete_profile(pid)
            self._send_json({"ok": ok})
            return

        elif path == "/api/slots/assign":
            slot_key = body.get("slot")
            profile_id = body.get("profile_id")
            ok = self.profile_manager.assign_slot(slot_key, profile_id)
            self._send_json({"ok": ok})
            return

        elif path == "/api/slots/select":
            slot_key = body.get("slot")
            active_profile = self.profile_manager.set_active_slot(slot_key)
            if active_profile and "lightbar" in active_profile:
                lb = active_profile["lightbar"]
                self.controller_manager.set_lightbar(lb.get("r", 0), lb.get("g", 112), lb.get("b", 240))
            self._send_json({"ok": True, "active_slot": slot_key, "profile": active_profile})
            return

        self.send_response(404)
        self.end_headers()

    def _read_json_body(self) -> Dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 0:
                raw = self.rfile.read(length).decode("utf-8")
                return json.loads(raw)
        except Exception:
            pass
        return {}

    def _send_json(self, data: Any):
        content = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        return


def create_server(host: str, port: int, controller_manager, profile_manager, static_dir: str):
    ControllerAPIHandler.controller_manager = controller_manager
    ControllerAPIHandler.profile_manager = profile_manager
    ControllerAPIHandler.static_dir = static_dir

    server = http.server.ThreadingHTTPServer((host, port), ControllerAPIHandler)
    return server
