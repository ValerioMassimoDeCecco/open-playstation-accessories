"""
DualSense & DualSense Edge hardware protocol implementation.
Parses physical HID input reports and formats HID output reports for lightbar, haptics,
trigger effects, and player LEDs.
"""

import binascii
import struct
import threading
import time
from typing import Optional, Dict, Any, Callable
from .hid_windows import WindowsHIDDevice


def compute_crc32(data: bytes) -> int:
    """Computes DualSense Bluetooth packet CRC32."""
    return binascii.crc32(data) & 0xFFFFFFFF


class DualSenseController:
    """
    Manages direct physical communication with a connected DualSense / DualSense Edge controller.
    """

    def __init__(self, device_info: Dict[str, Any]):
        self.device_info = device_info
        self.path = device_info["path"]
        self.name = device_info["name"]
        self.is_edge = device_info.get("is_edge", False)
        self.is_bluetooth = device_info.get("is_bluetooth", False)

        self.hid = WindowsHIDDevice(
            self.path,
            device_info["vid"],
            device_info["pid"],
            self.name
        )

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Controller state directly mirrors hardware
        self.state: Dict[str, Any] = {
            "connected": False,
            "model": self.name,
            "is_edge": self.is_edge,
            "is_bluetooth": self.is_bluetooth,
            "battery": {
                "level": 0,
                "charging": False,
                "full": False
            },
            "sticks": {
                "left": {"x": 128, "y": 128, "norm_x": 0.0, "norm_y": 0.0},
                "right": {"x": 128, "y": 128, "norm_x": 0.0, "norm_y": 0.0}
            },
            "triggers": {
                "l2": 0,
                "r2": 0,
                "l2_norm": 0.0,
                "r2_norm": 0.0
            },
            "buttons": {
                "cross": False,
                "circle": False,
                "square": False,
                "triangle": False,
                "dpad_up": False,
                "dpad_down": False,
                "dpad_left": False,
                "dpad_right": False,
                "l1": False,
                "r1": False,
                "l2": False,
                "r2": False,
                "l3": False,
                "r3": False,
                "create": False,
                "options": False,
                "ps": False,
                "touchpad": False,
                "mute": False,
                "fn_left": False,
                "fn_right": False,
                "back_left": False,
                "back_right": False
            },
            "lightbar": {
                "r": 0,
                "g": 112,
                "b": 240
            },
            "rumble": {
                "left": 0,
                "right": 0
            }
        }

        self._target_lightbar = (0, 112, 240)
        self._target_rumble = (0, 0)
        self._target_player_led = 0x04 # Player 1 (center)
        self._target_mic_led = 0

    def start(self) -> bool:
        """Opens physical HID device and starts polling thread."""
        if not self.hid.open():
            return False

        self._running = True
        self.state["connected"] = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

        # Set default PlayStation blue lightbar on connection
        self.set_lightbar(*self._target_lightbar)
        return True

    def stop(self):
        """Stops polling thread and closes HID handle."""
        self._running = False
        if self._thread and self._thread.is_alive() and threading.current_thread() != self._thread:
            self._thread.join(timeout=0.5)
        self.hid.close()
        self.state["connected"] = False

    def set_lightbar(self, r: int, g: int, b: int):
        """Sends real RGB lightbar command to controller hardware."""
        self._target_lightbar = (
            max(0, min(255, int(r))),
            max(0, min(255, int(g))),
            max(0, min(255, int(b)))
        )
        self.state["lightbar"] = {"r": r, "g": g, "b": b}
        self._send_output_report()

    def set_rumble(self, left: int, right: int, duration_sec: float = 0.0):
        """Drives real haptic vibration motors on physical controller."""
        self._target_rumble = (
            max(0, min(255, int(left))),
            max(0, min(255, int(right)))
        )
        self.state["rumble"] = {"left": left, "right": right}
        self._send_output_report()

        if duration_sec > 0:
            def _reset():
                time.sleep(duration_sec)
                self._target_rumble = (0, 0)
                self.state["rumble"] = {"left": 0, "right": 0}
                self._send_output_report()
            threading.Thread(target=_reset, daemon=True).start()

    def set_player_led(self, player_num: int):
        """Sets real player white LEDs under touchpad (1 to 4)."""
        mapping = {1: 0x04, 2: 0x0A, 3: 0x15, 4: 0x1B}
        self._target_player_led = mapping.get(player_num, 0x04)
        self._send_output_report()

    def _poll_loop(self):
        """Real-time physical polling loop."""
        failed_count = 0

        while self._running:
            report = self.hid.read_input_report()
            if report:
                failed_count = 0
                self._parse_input_report(report)
            else:
                failed_count += 1
                if failed_count > 40:
                    # Device disconnected or error
                    self.state["connected"] = False
                    break
                time.sleep(0.005)

    def _parse_input_report(self, data: bytes):
        """Parses hardware DualSense HID report 0x01 (USB/BT basic) or 0x31 (BT extended)."""
        if len(data) < 10:
            return

        report_id = data[0]
        if report_id == 0x01:
            base = 1
        elif report_id == 0x31:
            base = 2
        else:
            return

        try:
            # Analog Sticks
            lx = data[base + 0]
            ly = data[base + 1]
            rx = data[base + 2]
            ry = data[base + 3]

            # Analog Triggers
            l2_raw = data[base + 4]
            r2_raw = data[base + 5]

            # Digital Buttons
            b8 = data[base + 7]
            b9 = data[base + 8]
            b10 = data[base + 9]

            dpad_val = b8 & 0x0F
            dpad_map = {
                0: (True, False, False, False),   # Up
                1: (True, False, False, True),    # Up-Right
                2: (False, False, False, True),   # Right
                3: (False, True, False, True),    # Down-Right
                4: (False, True, False, False),   # Down
                5: (False, True, True, False),    # Down-Left
                6: (False, False, True, False),   # Left
                7: (True, False, True, False),    # Up-Left
                8: (False, False, False, False),  # Released
            }
            d_up, d_down, d_left, d_right = dpad_map.get(dpad_val, (False, False, False, False))

            # DualSense Edge extra buttons (Fn buttons & Back Paddles)
            fn_left = False
            fn_right = False
            back_left = False
            back_right = False

            if self.is_edge and len(data) > base + 37:
                edge_byte = data[base + 37]
                fn_left = bool(edge_byte & 0x01)
                fn_right = bool(edge_byte & 0x02)
                back_left = bool(edge_byte & 0x04)
                back_right = bool(edge_byte & 0x08)

            # Battery parsing (status[0] at offset 52 in payload)
            battery_pct = 0
            is_charging = False
            is_full = False

            if len(data) > base + 52:
                batt_byte = data[base + 52]
                level_raw = batt_byte & 0x0F
                status_raw = (batt_byte >> 4) & 0x0F

                battery_pct = min(100, level_raw * 10)
                is_charging = (status_raw == 0x01)
                is_full = (status_raw == 0x02)
                if is_full:
                    battery_pct = 100
                elif is_charging and battery_pct == 0:
                    battery_pct = 10

            with self._lock:
                self.state["sticks"]["left"] = {
                    "x": lx, "y": ly,
                    "norm_x": round((lx - 128) / 128.0, 3),
                    "norm_y": round((128 - ly) / 128.0, 3)
                }
                self.state["sticks"]["right"] = {
                    "x": rx, "y": ry,
                    "norm_x": round((rx - 128) / 128.0, 3),
                    "norm_y": round((128 - ry) / 128.0, 3)
                }
                self.state["triggers"]["l2"] = l2_raw
                self.state["triggers"]["r2"] = r2_raw
                self.state["triggers"]["l2_norm"] = round(l2_raw / 255.0, 3)
                self.state["triggers"]["r2_norm"] = round(r2_raw / 255.0, 3)

                self.state["buttons"].update({
                    "square": bool(b8 & 0x10),
                    "cross": bool(b8 & 0x20),
                    "circle": bool(b8 & 0x40),
                    "triangle": bool(b8 & 0x80),
                    "dpad_up": d_up,
                    "dpad_down": d_down,
                    "dpad_left": d_left,
                    "dpad_right": d_right,
                    "l1": bool(b9 & 0x01),
                    "r1": bool(b9 & 0x02),
                    "l2": bool(b9 & 0x04),
                    "r2": bool(b9 & 0x08),
                    "create": bool(b9 & 0x10),
                    "options": bool(b9 & 0x20),
                    "l3": bool(b9 & 0x40),
                    "r3": bool(b9 & 0x80),
                    "ps": bool(b10 & 0x01),
                    "touchpad": bool(b10 & 0x02),
                    "mute": bool(b10 & 0x04),
                    "fn_left": fn_left,
                    "fn_right": fn_right,
                    "back_left": back_left,
                    "back_right": back_right
                })

                self.state["battery"] = {
                    "level": battery_pct,
                    "charging": is_charging,
                    "full": is_full
                }
        except Exception:
            pass

    def _send_output_report(self):
        """Constructs and sends real output report to physical controller."""
        r, g, b = self._target_lightbar
        rumble_left, rumble_right = self._target_rumble

        if self.is_bluetooth:
            # Bluetooth Report 0x31 (78 bytes)
            report = bytearray(78)
            report[0] = 0x31
            report[1] = 0x02
            report[2] = 0x01 | 0x02
            report[3] = 0x01 | 0x02 | 0x04 | 0x10
            report[4] = rumble_right
            report[5] = rumble_left
            report[10] = self._target_mic_led
            report[40] = self._target_player_led
            report[45] = r
            report[46] = g
            report[47] = b

            crc = compute_crc32(bytes([0xA2]) + bytes(report[:74]))
            struct.pack_into("<I", report, 74, crc)
            self.hid.write_output_report(bytes(report))
        else:
            # USB Report 0x02 (48 bytes)
            report = bytearray(48)
            report[0] = 0x02
            report[1] = 0x01 | 0x02
            report[2] = 0x01 | 0x02 | 0x04 | 0x10
            report[3] = rumble_right
            report[4] = rumble_left
            report[9] = self._target_mic_led
            report[39] = self._target_player_led
            report[44] = r
            report[45] = g
            report[46] = b
            self.hid.write_output_report(bytes(report))
