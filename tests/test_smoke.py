"""
Smoke tests: they must pass on Windows, macOS and Linux without any hardware.

Run with:
    python -m unittest discover -s tests -t .
"""

import binascii
import json
import os
import struct
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.controller import hid_base
from app.controller.dualsense import DualSenseController
from app.main import ControllerManager
from app.profiles.manager import ProfileManager
from app.web.server import create_server


class FakeHIDDevice:
    """Captures output reports instead of touching real hardware."""

    def __init__(self):
        self.writes = []
        self.open_called = False
        self.closed = False

    def open(self):
        self.open_called = True
        return True

    def close(self):
        self.closed = True

    def read_input_report(self):
        return None

    def write_output_report(self, data):
        self.writes.append(bytes(data))
        return True


def make_controller(is_bluetooth=False, is_edge=False):
    info = {
        "path": "test:0x054C:0x0CE6",
        "vid": 0x054C,
        "pid": 0x0CE6 if not is_edge else 0x0DF2,
        "name": "DualSense Wireless Controller",
        "is_edge": is_edge,
        "is_bluetooth": is_bluetooth,
    }
    controller = DualSenseController(info)
    controller.hid = FakeHIDDevice()
    return controller


def usb_report(**overrides):
    report = bytearray(64)
    report[0] = 0x01
    report[1] = 128  # LX
    report[2] = 128  # LY
    report[3] = 128  # RX
    report[4] = 128  # RY
    report[5] = 0    # L2
    report[6] = 0    # R2
    report[7] = 0x00  # sequence number
    report[8] = 0x08  # buttons0: dpad released
    report[9] = 0x00  # buttons1
    report[10] = 0x00  # buttons2
    report[53] = 0x25  # battery: level 5 (50%), status 2 (full)
    for key, value in overrides.items():
        report[int(key[1:])] = value
    return bytes(report)


class BackendTests(unittest.TestCase):
    def test_backend_selection_is_safe(self):
        key = hid_base.platform_key()
        self.assertTrue(key)
        self.assertTrue(hid_base.backend_label())
        info = hid_base.get_platform_info()
        for field in ("os", "platform", "backend", "supported", "hint"):
            self.assertIn(field, info)
        self.assertEqual(info["platform"], key)

    def test_enumerate_never_raises(self):
        devices = hid_base.enumerate_sony_devices()
        self.assertIsInstance(devices, list)
        for device in devices:
            self.assertIn("path", device)
            self.assertIn("pid", device)
            self.assertIn("name", device)

    def test_factory_returns_usable_object(self):
        device = hid_base.create_hid_device("nonexistent:path", 0x054C, 0x0CE6, "Test")
        for method in ("open", "close", "read_input_report", "write_output_report"):
            self.assertTrue(callable(getattr(device, method)))
        # Opening a bogus path must fail gracefully, never raise.
        self.assertIn(device.open(), (True, False))
        device.close()

    def test_macos_backend_import_is_guarded(self):
        from app.controller import hid_macos  # noqa: F401  (must import anywhere)

        self.assertEqual(hid_macos.last_error() if sys.platform != "darwin" else "", "")

    def test_linux_backend_import_is_guarded(self):
        from app.controller import hid_linux  # noqa: F401

        self.assertIsInstance(hid_linux.enumerate_sony_devices(), list)


class ControllerManagerTests(unittest.TestCase):
    def test_status_and_inputs_without_hardware(self):
        manager = ControllerManager()
        status = manager.get_status()
        self.assertFalse(status["connected"])
        self.assertIn("platform", status)
        self.assertIn("version", status["platform"])
        self.assertFalse(status["data_flowing"])

        inputs = manager.get_inputs()
        self.assertEqual(inputs["sticks"]["left"]["x"], 128)
        self.assertEqual(inputs["triggers"]["l2"], 0)

        # Commands must be harmless when nothing is connected.
        manager.set_lightbar(1, 2, 3)
        manager.set_rumble(10, 10, 0.1)
        manager.set_player_led(2)


class DualSenseParserTests(unittest.TestCase):
    def test_usb_report_parsing(self):
        controller = make_controller()
        report = bytearray(usb_report())
        report[1] = 255
        report[2] = 0
        report[3] = 64
        report[4] = 192
        report[5] = 200
        report[6] = 100
        report[8] = 0x28  # buttons0: cross + dpad released
        report[9] = 0x01  # buttons1: L1
        report[10] = 0x02  # buttons2: touchpad
        report[53] = 0x15  # level 5, charging

        controller._parse_input_report(bytes(report))

        state = controller.state
        self.assertEqual(state["sticks"]["left"]["x"], 255)
        self.assertEqual(state["sticks"]["left"]["y"], 0)
        self.assertAlmostEqual(state["sticks"]["left"]["norm_x"], 0.992, places=3)
        self.assertEqual(state["triggers"]["l2"], 200)
        self.assertAlmostEqual(state["triggers"]["l2_norm"], 0.784, places=3)
        self.assertTrue(state["buttons"]["cross"])
        self.assertTrue(state["buttons"]["l1"])
        self.assertTrue(state["buttons"]["touchpad"])
        self.assertFalse(state["buttons"]["circle"])
        self.assertFalse(state["buttons"]["dpad_up"])
        self.assertEqual(state["battery"]["level"], 50)
        self.assertTrue(state["battery"]["charging"])
        self.assertFalse(state["battery"]["full"])

    def test_bluetooth_report_parsing(self):
        controller = make_controller(is_bluetooth=True)
        report = bytearray(78)
        report[0] = 0x31
        report[1] = 0x01  # BT sequence byte, parser uses base = 2
        report[2 + 0] = 10   # LX
        report[2 + 1] = 250  # LY
        report[2 + 4] = 255  # L2
        report[2 + 7] = 0x04  # circle (0x40) not set, dpad=4 (down)
        report[2 + 7] = 0x04 | 0x40  # circle + dpad down
        report[2 + 52] = 0x0A  # level 10 => 100%, discharging

        controller._parse_input_report(bytes(report))

        state = controller.state
        self.assertEqual(state["sticks"]["left"]["x"], 10)
        self.assertEqual(state["sticks"]["left"]["y"], 250)
        self.assertEqual(state["triggers"]["l2"], 255)
        self.assertTrue(state["buttons"]["circle"])
        self.assertTrue(state["buttons"]["dpad_down"])
        self.assertEqual(state["battery"]["level"], 100)
        self.assertFalse(state["battery"]["charging"])

    def test_garbage_reports_are_ignored(self):
        controller = make_controller()
        before = json.dumps(controller.state, sort_keys=True)
        controller._parse_input_report(b"")
        controller._parse_input_report(b"\x99" * 64)
        controller._parse_input_report(b"\x01\x02")
        self.assertEqual(before, json.dumps(controller.state, sort_keys=True))

    def test_edge_extra_buttons(self):
        controller = make_controller(is_edge=True)
        report = bytearray(usb_report())
        report[1 + 37] = 0x0F  # Fn left/right + both back paddles
        controller._parse_input_report(bytes(report))
        buttons = controller.state["buttons"]
        self.assertTrue(buttons["fn_left"])
        self.assertTrue(buttons["fn_right"])
        self.assertTrue(buttons["back_left"])
        self.assertTrue(buttons["back_right"])


class OutputReportTests(unittest.TestCase):
    def test_usb_lightbar_report(self):
        controller = make_controller()
        controller.set_lightbar(1, 2, 3)
        self.assertEqual(len(controller.hid.writes), 1)
        report = controller.hid.writes[0]
        self.assertEqual(len(report), 48)
        self.assertEqual(report[0], 0x02)
        self.assertEqual(tuple(report[44:47]), (1, 2, 3))

    def test_bluetooth_lightbar_report_has_valid_crc(self):
        controller = make_controller(is_bluetooth=True)
        controller.set_lightbar(9, 8, 7)
        report = controller.hid.writes[0]
        self.assertEqual(len(report), 78)
        self.assertEqual(report[0], 0x31)
        self.assertEqual(tuple(report[45:48]), (9, 8, 7))
        expected = binascii.crc32(b"\xA2" + report[:74]) & 0xFFFFFFFF
        self.assertEqual(struct.unpack_from("<I", report, 74)[0], expected)

    def test_rumble_and_player_led(self):
        controller = make_controller()
        controller.set_rumble(120, 33, 0)
        report = controller.hid.writes[-1]
        self.assertEqual(report[3], 33)   # right motor
        self.assertEqual(report[4], 120)  # left motor

        controller.set_player_led(3)
        report = controller.hid.writes[-1]
        self.assertEqual(report[39], 0x15)

    def test_clamping(self):
        controller = make_controller()
        controller.set_lightbar(999, -5, 12)
        report = controller.hid.writes[-1]
        self.assertEqual(tuple(report[44:47]), (255, 0, 12))


class HttpApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        storage = os.path.join(self.tmpdir.name, "profiles.json")
        static_dir = os.path.join(REPO_ROOT, "app", "web", "static")

        self.profile_manager = ProfileManager(storage)
        self.controller_manager = ControllerManager()
        self.server = create_server(
            "127.0.0.1", 0, self.controller_manager, self.profile_manager, static_dir
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        time.sleep(0.15)
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def get_json(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as response:
            self.assertEqual(response.status, 200)
            return json.loads(response.read().decode("utf-8"))

    def post_json(self, path, payload):
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base + path, data=data, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 200)
            return json.loads(response.read().decode("utf-8"))

    def test_status_endpoint(self):
        status = self.get_json("/api/status")
        self.assertIn("connected", status)
        self.assertIn("platform", status)
        self.assertIn(status["platform"]["os"], ("Windows", "macOS", "Linux"))

    def test_inputs_endpoint(self):
        inputs = self.get_json("/api/inputs")
        self.assertIn("sticks", inputs)
        self.assertIn("triggers", inputs)
        self.assertIn("buttons", inputs)

    def test_profiles_endpoint(self):
        data = self.get_json("/api/profiles")
        self.assertGreaterEqual(len(data["profiles"]), 1)
        self.assertIn("slot_1", data["slots"])

    def test_health_endpoint(self):
        data = self.get_json("/api/health")
        self.assertTrue(data["ok"])

    def test_static_index(self):
        with urllib.request.urlopen(self.base + "/", timeout=5) as response:
            body = response.read().decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("PlayStation Accessories", body)

    def test_lightbar_validation(self):
        data = self.post_json("/api/lightbar", {"r": 999, "g": -3, "b": "x"})
        self.assertTrue(data["ok"])
        self.assertEqual(data["lightbar"], {"r": 255, "g": 0, "b": 240})

    def test_player_led_and_rumble(self):
        self.assertTrue(self.post_json("/api/player_led", {"player_num": 9})["ok"])
        self.assertTrue(self.post_json("/api/rumble", {"left": 50, "right": 50})["ok"])

    def test_profile_roundtrip(self):
        profile = {
            "id": "",
            "name": "Test",
            "curve_type": "Linear",
            "left_stick": {"curve": "Linear", "deadzone": 2},
            "right_stick": {"curve": "Linear", "deadzone": 2},
            "triggers": {},
            "lightbar": {"r": 1, "g": 2, "b": 3},
            "button_mappings": {},
        }
        saved = self.post_json("/api/profiles/save", profile)
        self.assertTrue(saved["ok"])
        self.assertTrue(saved["profile"]["id"])

        assigned = self.post_json(
            "/api/slots/assign",
            {"slot": "slot_2", "profile_id": saved["profile"]["id"]},
        )
        self.assertTrue(assigned["ok"])

        selected = self.post_json("/api/slots/select", {"slot": "slot_2"})
        self.assertTrue(selected["ok"])
        self.assertEqual(selected["profile"]["id"], saved["profile"]["id"])

    def test_unknown_endpoint_returns_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post_json("/api/does-not-exist", {})
        self.assertEqual(ctx.exception.code, 404)


class FakeController:
    """Stand-in for DualSenseController used to exercise the hot-plug worker."""

    def __init__(self, device_info):
        self.path = device_info["path"]
        self.name = device_info["name"]
        self.is_bluetooth = device_info.get("is_bluetooth", False)
        self.received_reports = 1
        self.started = False
        self.stopped = False
        self.state = {
            "connected": False,
            "model": device_info["name"],
            "is_edge": False,
            "is_bluetooth": self.is_bluetooth,
            "battery": {"level": 80, "charging": False, "full": False},
            "lightbar": {"r": 0, "g": 112, "b": 240},
        }

    def start(self):
        self.started = True
        self.state["connected"] = True
        return True

    def stop(self):
        self.stopped = True
        self.state["connected"] = False

    def set_lightbar(self, r, g, b):
        self.state["lightbar"] = {"r": r, "g": g, "b": b}

    def set_rumble(self, left, right, duration=0.5):
        pass

    def set_player_led(self, num):
        pass


class HotPlugTests(unittest.TestCase):
    DEVICE = {
        "path": "fake:0x054C:0x0CE6",
        "vid": 0x054C,
        "pid": 0x0CE6,
        "name": "DualSense Wireless Controller",
        "is_edge": False,
        "is_bluetooth": False,
    }

    def test_controller_is_attached_and_released(self):
        manager = ControllerManager()
        with mock.patch("app.main.enumerate_sony_devices", return_value=[self.DEVICE]), \
             mock.patch("app.main.DualSenseController", FakeController):
            manager.start()
            self.addCleanup(manager.stop)
            for _ in range(60):
                if manager.get_status()["connected"]:
                    break
                time.sleep(0.05)
            status = manager.get_status()
            self.assertTrue(status["connected"])
            self.assertEqual(status["battery"]["level"], 80)
            manager.set_lightbar(1, 2, 3)
            self.assertEqual(manager.get_status()["lightbar"], {"r": 1, "g": 2, "b": 3})

    def test_failing_controller_does_not_crash_the_worker(self):
        class BrokenController(FakeController):
            def start(self):
                raise RuntimeError("boom")

        manager = ControllerManager()
        with mock.patch("app.main.enumerate_sony_devices", return_value=[self.DEVICE]), \
             mock.patch("app.main.DualSenseController", BrokenController):
            manager.start()
            self.addCleanup(manager.stop)
            time.sleep(0.3)
        self.assertFalse(manager.get_status()["connected"])
        self.assertIn("boom", manager.last_error)


class ProfileStorageTests(unittest.TestCase):
    def test_defaults_are_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ProfileManager(os.path.join(tmpdir, "profiles.json"))
            self.assertTrue(manager.get_all_profiles())
            self.assertEqual(manager.slots["slot_1"], "default")

    def test_default_profile_cannot_be_deleted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ProfileManager(os.path.join(tmpdir, "profiles.json"))
            self.assertFalse(manager.delete_profile("default"))

    def test_corrupted_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "profiles.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{ this is not json")
            manager = ProfileManager(path)
            self.assertTrue(manager.get_all_profiles())


if __name__ == "__main__":
    unittest.main()
